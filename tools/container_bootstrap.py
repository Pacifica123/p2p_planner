#!/usr/bin/env python3
"""Zero-config Docker bootstrap for p2pKanban.

The module deliberately uses only the Python standard library. Docker Compose
owns the application runtime; this wrapper chooses a free web port, starts the
stack, waits for its public health endpoint and records only non-secret state.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


TOOL_VERSION = "1.0.0"
STATE_VERSION = 1
COMPOSE_PROJECT = "p2pkanban-bootstrap"
COMPOSE_RELATIVE_PATH = Path("deploy/bootstrap/compose.yaml")
STATE_RELATIVE_PATH = Path(".dev-bootstrap/container-stack.json")
DEFAULT_WEB_PORT = 8080
DEFAULT_TIMEOUT_SECONDS = 900


class BootstrapError(RuntimeError):
    """Expected user-facing bootstrap failure."""


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def find_project_root(start: Path) -> Path | None:
    candidate = start.resolve()
    for current in (candidate, *candidate.parents):
        if (
            (current / COMPOSE_RELATIVE_PATH).is_file()
            and (current / "backend/Cargo.toml").is_file()
            and (current / "frontend/package.json").is_file()
        ):
            return current
    return None


def load_state(project_root: Path) -> dict[str, Any]:
    path = project_root / STATE_RELATIVE_PATH
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def write_state(project_root: Path, state: dict[str, Any]) -> None:
    path = project_root / STATE_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def remove_state(project_root: Path) -> None:
    path = project_root / STATE_RELATIVE_PATH
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def is_port_available(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def choose_web_port(requested: int | None, state: dict[str, Any]) -> int:
    if requested is not None:
        if not 1 <= requested <= 65535:
            raise BootstrapError("Порт должен быть числом от 1 до 65535.")
        return requested

    previous = state.get("webPort")
    if isinstance(previous, int) and 1 <= previous <= 65535:
        return previous

    for port in range(DEFAULT_WEB_PORT, DEFAULT_WEB_PORT + 101):
        if is_port_available(port):
            return port
    raise BootstrapError(
        f"Не найден свободный web-порт в диапазоне "
        f"{DEFAULT_WEB_PORT}–{DEFAULT_WEB_PORT + 100}."
    )


def configured_web_port(state: dict[str, Any]) -> int:
    previous = state.get("webPort")
    if isinstance(previous, int) and 1 <= previous <= 65535:
        return previous
    return DEFAULT_WEB_PORT


def listen_to_bind_address(listen: str) -> str:
    return "0.0.0.0" if listen == "lan" else "127.0.0.1"


def compose_environment(web_port: int, bind_address: str) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "P2PKANBAN_WEB_PORT": str(web_port),
            "P2PKANBAN_BIND_ADDRESS": bind_address,
        }
    )
    return env


def docker_executable(*, allow_missing: bool = False) -> str:
    executable = shutil.which("docker")
    if executable:
        return executable
    if allow_missing:
        return "docker"
    raise BootstrapError(
        "Docker не найден. Установите Docker Desktop либо Docker Engine "
        "с Compose v2 и повторите команду."
    )


def compose_command(
    project_root: Path,
    *arguments: str,
    allow_missing_docker: bool = False,
) -> list[str]:
    return [
        docker_executable(allow_missing=allow_missing_docker),
        "compose",
        "--project-name",
        COMPOSE_PROJECT,
        "--file",
        str(project_root / COMPOSE_RELATIVE_PATH),
        *arguments,
    ]


def display_command(command: Sequence[str]) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline(list(command))
    return shlex.join(command)


def run_capture(
    command: Sequence[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout: int = 60,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        cwd=str(cwd),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )


def ensure_docker_ready(project_root: Path, env: dict[str, str]) -> None:
    docker = docker_executable()
    version = run_capture(
        [docker, "compose", "version"],
        cwd=project_root,
        env=env,
        timeout=20,
    )
    if version.returncode != 0:
        raise BootstrapError(
            "Docker Compose v2 недоступен. Обновите Docker и повторите запуск."
        )

    daemon = run_capture(
        [docker, "info", "--format", "{{.ServerVersion}}"],
        cwd=project_root,
        env=env,
        timeout=30,
    )
    if daemon.returncode != 0:
        raise BootstrapError(
            "Docker установлен, но его движок не запущен. Запустите Docker "
            "Desktop или docker service и повторите команду."
        )


def validate_compose(project_root: Path, env: dict[str, str]) -> None:
    command = compose_command(project_root, "config", "--quiet")
    result = run_capture(command, cwd=project_root, env=env, timeout=60)
    if result.returncode != 0:
        details = result.stdout.strip()
        raise BootstrapError(
            "Docker Compose не принял deploy/bootstrap/compose.yaml."
            + (f"\n{details}" if details else "")
        )


def http_ready(url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return 200 <= response.status < 300
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def wait_until_ready(url: str, timeout_seconds: int) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if http_ready(url):
            return True
        time.sleep(2)
    return False


def print_compose_diagnostics(
    project_root: Path,
    env: dict[str, str],
    *,
    tail: int = 120,
) -> None:
    for arguments in (
        ("ps", "--all"),
        ("logs", "--no-color", "--tail", str(tail)),
    ):
        result = run_capture(
            compose_command(project_root, *arguments),
            cwd=project_root,
            env=env,
            timeout=60,
        )
        if result.stdout.strip():
            print(result.stdout.rstrip(), file=sys.stderr)


def stack_state(
    *,
    web_port: int,
    bind_address: str,
    status: str,
    previous: dict[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    created_at = (previous or {}).get("createdAt") or iso_now()
    result: dict[str, Any] = {
        "schemaVersion": STATE_VERSION,
        "toolVersion": TOOL_VERSION,
        "composeProject": COMPOSE_PROJECT,
        "composeFile": COMPOSE_RELATIVE_PATH.as_posix(),
        "webPort": web_port,
        "bindAddress": bind_address,
        "url": f"http://127.0.0.1:{web_port}",
        "status": status,
        "createdAt": created_at,
        "updatedAt": iso_now(),
    }
    if error:
        result["lastError"] = error
    return result


def command_start(args: argparse.Namespace, project_root: Path) -> int:
    previous = load_state(project_root)
    web_port = choose_web_port(args.port, previous)
    previous_listen = "lan" if previous.get("bindAddress") == "0.0.0.0" else "local"
    listen = args.listen or previous_listen
    bind_address = listen_to_bind_address(listen)
    public_url = f"http://127.0.0.1:{web_port}"
    health_url = f"{public_url}/healthz"
    env = compose_environment(web_port, bind_address)
    up_arguments = ["up", "--detach", "--remove-orphans"]
    if not args.no_build:
        up_arguments.append("--build")
    command = compose_command(
        project_root,
        *up_arguments,
        allow_missing_docker=args.dry_run,
    )

    if args.dry_run:
        print("План zero-config запуска:")
        print(f"- Web: {public_url}")
        print(f"- Доступ: {'локальная сеть' if listen == 'lan' else 'только этот компьютер'}")
        print("- PostgreSQL, роль, БД и секреты создаются внутри Docker.")
        print(f"- Команда: {display_command(command)}")
        if shutil.which("docker") is None:
            print("- Docker сейчас не найден; реальный запуск потребует Docker Compose v2.")
        return 0

    ensure_docker_ready(project_root, env)
    validate_compose(project_root, env)

    if args.port is not None:
        previous_port = previous.get("webPort")
        same_owned_port = previous_port == web_port
        if not same_owned_port and not is_port_available(web_port):
            raise BootstrapError(
                f"Порт {web_port} уже занят. Уберите --port или выберите другой."
            )

    write_state(
        project_root,
        stack_state(
            web_port=web_port,
            bind_address=bind_address,
            status="starting",
            previous=previous,
        ),
    )

    print("Запускаю p2pKanban. Первый запуск может занять несколько минут.")
    completed = subprocess.run(
        command,
        cwd=str(project_root),
        env=env,
        check=False,
    )
    if completed.returncode != 0:
        message = "Docker Compose не смог собрать или запустить контейнеры."
        write_state(
            project_root,
            stack_state(
                web_port=web_port,
                bind_address=bind_address,
                status="failed",
                previous=previous,
                error=message,
            ),
        )
        print_compose_diagnostics(project_root, env)
        raise BootstrapError(message)

    if not wait_until_ready(health_url, args.timeout_seconds):
        message = (
            f"Контейнеры запущены, но web-интерфейс не стал доступен за "
            f"{args.timeout_seconds} секунд."
        )
        write_state(
            project_root,
            stack_state(
                web_port=web_port,
                bind_address=bind_address,
                status="unhealthy",
                previous=previous,
                error=message,
            ),
        )
        print_compose_diagnostics(project_root, env)
        raise BootstrapError(message)

    write_state(
        project_root,
        stack_state(
            web_port=web_port,
            bind_address=bind_address,
            status="running",
            previous=previous,
        ),
    )

    print("\np2pKanban запущен.")
    print(f"Открыть: {public_url}")
    if listen == "lan":
        print(
            "Для другого устройства в доверенной локальной сети используйте "
            "IP этого компьютера и тот же порт."
        )
        print("Не публикуйте этот HTTP-порт напрямую в интернет.")
    print("Остановить: python bootstrap.py stop")
    print("Логи:      python bootstrap.py logs")

    if not args.no_open:
        webbrowser.open(public_url)
    return 0


def command_status(args: argparse.Namespace, project_root: Path) -> int:
    state = load_state(project_root)
    web_port = configured_web_port(state)
    bind_address = str(state.get("bindAddress") or "127.0.0.1")
    env = compose_environment(web_port, bind_address)
    public_url = f"http://127.0.0.1:{web_port}"

    ensure_docker_ready(project_root, env)
    result = run_capture(
        compose_command(project_root, "ps", "--all"),
        cwd=project_root,
        env=env,
        timeout=60,
    )
    if result.stdout.strip():
        print(result.stdout.rstrip())
    print(f"\nWeb: {'доступен' if http_ready(public_url + '/healthz') else 'не отвечает'}")
    print(f"URL: {public_url}")
    return 0 if result.returncode == 0 else 1


def command_logs(args: argparse.Namespace, project_root: Path) -> int:
    state = load_state(project_root)
    web_port = configured_web_port(state)
    bind_address = str(state.get("bindAddress") or "127.0.0.1")
    env = compose_environment(web_port, bind_address)
    ensure_docker_ready(project_root, env)
    arguments = ["logs", "--tail", str(args.tail)]
    if args.follow:
        arguments.append("--follow")
    try:
        return subprocess.run(
            compose_command(project_root, *arguments),
            cwd=str(project_root),
            env=env,
            check=False,
        ).returncode
    except KeyboardInterrupt:
        return 130


def command_stop(args: argparse.Namespace, project_root: Path) -> int:
    state = load_state(project_root)
    web_port = configured_web_port(state)
    bind_address = str(state.get("bindAddress") or "127.0.0.1")
    env = compose_environment(web_port, bind_address)
    command = compose_command(
        project_root,
        "down",
        "--remove-orphans",
        allow_missing_docker=args.dry_run,
    )
    if args.dry_run:
        print(display_command(command))
        print("БД и секреты сохранятся в Docker volumes.")
        return 0

    ensure_docker_ready(project_root, env)
    completed = subprocess.run(
        command,
        cwd=str(project_root),
        env=env,
        check=False,
    )
    if completed.returncode != 0:
        raise BootstrapError("Не удалось остановить контейнеры p2pKanban.")

    write_state(
        project_root,
        stack_state(
            web_port=web_port,
            bind_address=bind_address,
            status="stopped",
            previous=state,
        ),
    )
    print("p2pKanban остановлен. БД и секреты сохранены.")
    return 0


def command_reset(args: argparse.Namespace, project_root: Path) -> int:
    if not args.yes:
        raise BootstrapError(
            "Reset безвозвратно удаляет локальную БД. "
            "Если это точно нужно, повторите: python bootstrap.py reset --yes"
        )

    state = load_state(project_root)
    web_port = configured_web_port(state)
    bind_address = str(state.get("bindAddress") or "127.0.0.1")
    env = compose_environment(web_port, bind_address)
    command = compose_command(
        project_root,
        "down",
        "--volumes",
        "--remove-orphans",
        allow_missing_docker=args.dry_run,
    )
    if args.dry_run:
        print(display_command(command))
        print("Будут удалены контейнеры, локальная БД и сгенерированные секреты.")
        return 0

    ensure_docker_ready(project_root, env)
    completed = subprocess.run(
        command,
        cwd=str(project_root),
        env=env,
        check=False,
    )
    if completed.returncode != 0:
        raise BootstrapError("Docker не смог удалить stack volumes.")
    remove_state(project_root)
    print("Локальные контейнеры, БД и секреты p2pKanban удалены.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bootstrap.py",
        description="Zero-config Docker bootstrap для p2pKanban.",
    )
    parser.add_argument("--version", action="version", version=TOOL_VERSION)
    subparsers = parser.add_subparsers(dest="command")

    start = subparsers.add_parser("start", help="Собрать и запустить весь stack.")
    start.add_argument("--port", type=int, help="Явно выбрать внешний web-порт.")
    start.add_argument(
        "--listen",
        choices=["local", "lan"],
        default=None,
        help="local: только этот компьютер; lan: доверенная локальная сеть.",
    )
    start.add_argument("--no-build", action="store_true", help="Не пересобирать образы.")
    start.add_argument("--no-open", action="store_true", help="Не открывать браузер.")
    start.add_argument("--dry-run", action="store_true", help="Показать план без запуска Docker.")
    start.add_argument(
        "--timeout-seconds",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="Сколько ждать первого запуска web-контейнера.",
    )
    start.set_defaults(func=command_start)

    status = subparsers.add_parser("status", help="Показать контейнеры и доступность web.")
    status.set_defaults(func=command_status)

    logs = subparsers.add_parser("logs", help="Показать логи контейнеров.")
    logs.add_argument("--tail", type=int, default=150, help="Количество последних строк.")
    logs.add_argument("--follow", "-f", action="store_true", help="Продолжать вывод новых строк.")
    logs.set_defaults(func=command_logs)

    stop = subparsers.add_parser("stop", help="Остановить stack, сохранив данные.")
    stop.add_argument("--dry-run", action="store_true", help="Показать команду без остановки.")
    stop.set_defaults(func=command_stop)

    reset = subparsers.add_parser("reset", help="Удалить stack вместе с локальной БД.")
    reset.add_argument("--yes", action="store_true", help="Подтвердить безвозвратное удаление данных.")
    reset.add_argument("--dry-run", action="store_true", help="Показать команду без удаления.")
    reset.set_defaults(func=command_reset)

    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    project_root: Path | None = None,
) -> int:
    arguments = list(argv if argv is not None else sys.argv[1:])
    if not arguments:
        arguments = ["start"]

    parser = build_parser()
    args = parser.parse_args(arguments)
    if not hasattr(args, "func"):
        parser.print_help()
        return 2

    root = project_root.resolve() if project_root else find_project_root(Path.cwd())
    if root is None:
        print(
            "Не найден корень p2pKanban с deploy/bootstrap/compose.yaml.",
            file=sys.stderr,
        )
        return 2

    try:
        return int(args.func(args, root))
    except BootstrapError as exc:
        print(f"\nЗапуск остановлен: {exc}", file=sys.stderr)
        return 1
    except subprocess.TimeoutExpired:
        print(
            "\nЗапуск остановлен: Docker слишком долго не отвечал.",
            file=sys.stderr,
        )
        return 1
    except KeyboardInterrupt:
        print("\nОстановлено пользователем.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
