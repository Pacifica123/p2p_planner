#!/usr/bin/env python3
"""Zero-config Docker bootstrap for p2pKanban.

The module deliberately uses only the Python standard library. Docker Compose
owns the application runtime; this wrapper chooses a free web port, starts the
stack, waits for its public health endpoint and records only non-secret state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Sequence


TOOL_VERSION = "1.1.0"
STATE_VERSION = 2
COMPOSE_PROJECT = "p2pkanban-bootstrap"
COMPOSE_RELATIVE_PATH = Path("deploy/bootstrap/compose.yaml")
STATE_RELATIVE_PATH = Path(".dev-bootstrap/container-stack.json")
BUILD_INFO_FILENAME = "BUILD_INFO.json"
UPDATE_LOCK_RELATIVE_PATH = Path(".dev-bootstrap/update.lock")
UPDATE_RELEASES_RELATIVE_PATH = Path(".dev-bootstrap/releases")
UPDATE_BACKUPS_RELATIVE_PATH = Path(".dev-bootstrap/backups")
UPDATE_REPORTS_RELATIVE_PATH = Path(".dev-bootstrap/update-reports")
DEFAULT_WEB_PORT = 8080
DEFAULT_TIMEOUT_SECONDS = 900
DEFAULT_UPDATE_BRANCH = "main"
DEFAULT_MIN_FREE_SPACE_BYTES = 2 * 1024 * 1024 * 1024
MAX_UPDATE_ARCHIVE_BYTES = 512 * 1024 * 1024


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


def read_json_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def read_version(source_root: Path) -> str:
    try:
        value = (source_root / "VERSION").read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise BootstrapError(f"Не удалось прочитать VERSION в обновлении: {exc}") from exc
    if not value or any(character.isspace() for character in value):
        raise BootstrapError("Файл VERSION в обновлении пуст или содержит пробелы.")
    return value


def relative_state_path(project_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError as exc:
        raise BootstrapError(
            "Bootstrap отказался сохранять путь обновления вне каталога проекта."
        ) from exc


def resolve_state_path(project_root: Path, value: object) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = Path(value)
    if candidate.is_absolute():
        return None
    resolved = (project_root / candidate).resolve()
    releases_root = (project_root / UPDATE_RELEASES_RELATIVE_PATH).resolve()
    try:
        resolved.relative_to(releases_root)
    except ValueError:
        return None
    return resolved


def active_source_root(project_root: Path, state: dict[str, Any]) -> Path:
    candidate = resolve_state_path(project_root, state.get("activeSourceRoot"))
    if candidate and (candidate / COMPOSE_RELATIVE_PATH).is_file():
        return candidate
    return project_root


def configured_image_tag(state: dict[str, Any]) -> str:
    value = state.get("imageTag")
    return value if isinstance(value, str) and value.strip() else "local"


def safe_identifier(value: str, *, fallback: str = "update") -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip(".-").lower()
    return (normalized or fallback)[:48]


def source_fingerprint(source_root: Path) -> str:
    digest = hashlib.sha256()
    exact_candidates = (
        Path("VERSION"),
        Path("bootstrap.py"),
        Path("tools/container_bootstrap.py"),
        Path("backend/Cargo.toml"),
        Path("backend/Cargo.lock"),
        Path("backend/build.rs"),
        Path("frontend/package.json"),
        Path("frontend/package-lock.json"),
        Path("frontend/index.html"),
        Path("frontend/vite.config.ts"),
    )
    runtime_trees = (
        Path("deploy/bootstrap"),
        Path("backend/config"),
        Path("backend/crates"),
        Path("backend/migrations"),
        Path("backend/src"),
        Path("frontend/public"),
        Path("frontend/src"),
    )

    candidates = set(exact_candidates)
    for relative_root in runtime_trees:
        tree = source_root / relative_root
        if tree.is_dir():
            candidates.update(
                path.relative_to(source_root)
                for path in tree.rglob("*")
                if path.is_file()
            )

    for relative in sorted(candidates, key=lambda path: path.as_posix()):
        path = source_root / relative
        if not path.is_file():
            continue
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def validate_update_source(source_root: Path) -> str:
    required = (
        COMPOSE_RELATIVE_PATH,
        Path("backend/Cargo.toml"),
        Path("frontend/package.json"),
        Path("bootstrap.py"),
        Path("tools/container_bootstrap.py"),
    )
    missing = [path.as_posix() for path in required if not (source_root / path).is_file()]
    if missing:
        raise BootstrapError(
            "Полученный источник обновления неполный. Не хватает: "
            + ", ".join(missing)
        )
    return read_version(source_root)


def current_build_info(project_root: Path, state: dict[str, Any]) -> dict[str, Any]:
    active = active_source_root(project_root, state)
    return read_json_object(active / BUILD_INFO_FILENAME) or read_json_object(
        project_root / BUILD_INFO_FILENAME
    )


def normalize_github_repository(value: str) -> str | None:
    candidate = value.strip()
    ssh_match = re.fullmatch(r"git@github\.com:([^/]+)/([^/]+?)(?:\.git)?", candidate)
    if ssh_match:
        return f"https://github.com/{ssh_match.group(1)}/{ssh_match.group(2)}"

    try:
        parsed = urllib.parse.urlparse(candidate)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or parsed.hostname != "github.com":
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 2:
        return None
    owner, repository = parts
    repository = repository.removesuffix(".git")
    if not owner or not repository:
        return None
    return f"https://github.com/{owner}/{repository}"


def git_output(project_root: Path, *arguments: str, timeout: int = 60) -> str | None:
    git = shutil.which("git")
    if not git:
        return None
    result = run_capture(
        [git, *arguments],
        cwd=project_root,
        env=os.environ.copy(),
        timeout=timeout,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def discover_update_repository(
    project_root: Path,
    state: dict[str, Any],
    explicit: str | None,
) -> str | None:
    candidates: list[object] = [
        explicit,
        state.get("updateRepository"),
        current_build_info(project_root, state).get("gitRepository"),
        git_output(project_root, "remote", "get-url", "origin"),
    ]
    for candidate in candidates:
        if not isinstance(candidate, str):
            continue
        normalized = normalize_github_repository(candidate)
        if normalized:
            return normalized
    return None


def github_branch_archive_url(repository: str, branch: str) -> str:
    normalized = normalize_github_repository(repository)
    if not normalized:
        raise BootstrapError(
            "Первая версия updater поддерживает только GitHub-репозитории вида "
            "https://github.com/owner/repository."
        )
    owner_repo = normalized.removeprefix("https://github.com/")
    quoted_branch = urllib.parse.quote(branch, safe="")
    return f"https://github.com/{owner_repo}/archive/refs/heads/{quoted_branch}.zip"


def safe_extract_zip(archive_path: Path, destination: Path) -> Path:
    destination_resolved = destination.resolve()
    with zipfile.ZipFile(archive_path) as archive:
        file_members = [item for item in archive.infolist() if not item.is_dir()]
        if not file_members:
            raise BootstrapError("Архив обновления пуст.")
        for item in archive.infolist():
            target = (destination / item.filename).resolve()
            try:
                target.relative_to(destination_resolved)
            except ValueError as exc:
                raise BootstrapError(
                    "Архив обновления содержит небезопасный путь."
                ) from exc
            if item.file_size > MAX_UPDATE_ARCHIVE_BYTES:
                raise BootstrapError("Один из файлов обновления слишком большой.")
        archive.extractall(destination)

    roots = {
        Path(item.filename).parts[0]
        for item in file_members
        if Path(item.filename).parts
    }
    if len(roots) == 1:
        nested = destination / next(iter(roots))
        if nested.is_dir():
            return nested
    return destination


def copy_source_tree(source: Path, destination: Path) -> None:
    ignored_names = {
        ".git",
        ".dev-bootstrap",
        "__pycache__",
        "node_modules",
        "target",
        "dist",
        "playwright-report",
        "test-results",
    }

    def ignore(_directory: str, names: list[str]) -> set[str]:
        return {name for name in names if name in ignored_names}

    shutil.copytree(source, destination, ignore=ignore)


def download_update_archive(url: str, destination: Path) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/zip",
            "User-Agent": f"p2pKanban-bootstrap/{TOOL_VERSION}",
        },
    )
    digest = hashlib.sha256()
    total = 0
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > MAX_UPDATE_ARCHIVE_BYTES:
                raise BootstrapError("Архив обновления превышает допустимый размер.")
            with destination.open("wb") as stream:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_UPDATE_ARCHIVE_BYTES:
                        raise BootstrapError(
                            "Архив обновления превышает допустимый размер."
                        )
                    digest.update(chunk)
                    stream.write(chunk)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise BootstrapError(
            f"Не удалось скачать обновление с GitHub: {exc}"
        ) from exc
    return digest.hexdigest()


@contextmanager
def update_lock(project_root: Path) -> Iterator[None]:
    lock_path = project_root / UPDATE_LOCK_RELATIVE_PATH
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "pid": os.getpid(),
        "createdAt": iso_now(),
    }
    try:
        descriptor = os.open(
            lock_path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
    except FileExistsError as exc:
        existing = read_json_object(lock_path)
        details = (
            f" PID {existing.get('pid')}, запуск {existing.get('createdAt')}."
            if existing
            else ""
        )
        raise BootstrapError(
            "Другое обновление уже выполняется или оставило lock-файл."
            + details
            + " Если процесса уже нет, удалите .dev-bootstrap/update.lock."
        ) from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False)
            stream.write("\n")
        yield
    finally:
        try:
            lock_path.unlink()
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


def compose_environment(
    web_port: int,
    bind_address: str,
    image_tag: str = "local",
) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "P2PKANBAN_WEB_PORT": str(web_port),
            "P2PKANBAN_BIND_ADDRESS": bind_address,
            "P2PKANBAN_IMAGE_TAG": safe_identifier(image_tag, fallback="local"),
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
    source_root: Path,
    *arguments: str,
    allow_missing_docker: bool = False,
) -> list[str]:
    return [
        docker_executable(allow_missing=allow_missing_docker),
        "compose",
        "--project-name",
        COMPOSE_PROJECT,
        "--file",
        str(source_root / COMPOSE_RELATIVE_PATH),
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


def validate_compose(source_root: Path, env: dict[str, str]) -> None:
    command = compose_command(source_root, "config", "--quiet")
    result = run_capture(command, cwd=source_root, env=env, timeout=60)
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
    source_root: Path,
    env: dict[str, str],
    *,
    tail: int = 120,
) -> None:
    for arguments in (
        ("ps", "--all"),
        ("logs", "--no-color", "--tail", str(tail)),
    ):
        result = run_capture(
            compose_command(source_root, *arguments),
            cwd=source_root,
            env=env,
            timeout=60,
        )
        if result.stdout.strip():
            print(result.stdout.rstrip(), file=sys.stderr)


def require_free_space(project_root: Path) -> None:
    free = shutil.disk_usage(project_root).free
    if free < DEFAULT_MIN_FREE_SPACE_BYTES:
        gib = free / (1024 * 1024 * 1024)
        raise BootstrapError(
            f"Для безопасной сборки и backup осталось слишком мало места "
            f"({gib:.1f} ГиБ). Освободите хотя бы 2 ГиБ."
        )


def run_source_self_check(source_root: Path, env: dict[str, str]) -> None:
    checker = source_root / "tools/check_zero_config_bootstrap.py"
    if not checker.is_file():
        return
    result = run_capture(
        [sys.executable, "-B", str(checker)],
        cwd=source_root,
        env=env,
        timeout=180,
    )
    if result.returncode != 0:
        raise BootstrapError(
            "Встроенная проверка нового bootstrap завершилась ошибкой.\n"
            + result.stdout.strip()
        )


def create_database_backup(
    source_root: Path,
    project_root: Path,
    env: dict[str, str],
    backup_id: str,
) -> tuple[Path, dict[str, int]]:
    backup_dir = project_root / UPDATE_BACKUPS_RELATIVE_PATH / backup_id
    backup_dir.mkdir(parents=True, exist_ok=False)
    dump_path = backup_dir / "p2pkanban.dump"
    command = compose_command(
        source_root,
        "exec",
        "-T",
        "postgres",
        "pg_dump",
        "--username",
        "p2pkanban",
        "--dbname",
        "p2pkanban",
        "--format=custom",
        "--no-owner",
        "--no-privileges",
    )
    try:
        with dump_path.open("wb") as stream:
            completed = subprocess.run(
                command,
                cwd=str(source_root),
                env=env,
                stdout=stream,
                stderr=subprocess.PIPE,
                timeout=300,
                check=False,
            )
    except (OSError, subprocess.TimeoutExpired) as exc:
        shutil.rmtree(backup_dir, ignore_errors=True)
        raise BootstrapError(f"Не удалось создать backup PostgreSQL: {exc}") from exc
    if completed.returncode != 0 or not dump_path.is_file() or dump_path.stat().st_size == 0:
        details = completed.stderr.decode("utf-8", errors="replace").strip()
        shutil.rmtree(backup_dir, ignore_errors=True)
        raise BootstrapError(
            "PostgreSQL backup завершился ошибкой."
            + (f"\n{details}" if details else "")
        )

    counts = database_counts(source_root, env)
    manifest = {
        "schemaVersion": 1,
        "createdAt": iso_now(),
        "format": "pg_dump custom",
        "file": dump_path.name,
        "sha256": file_sha256(dump_path),
        "counts": counts,
    }
    (backup_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return dump_path, counts


def database_counts(source_root: Path, env: dict[str, str]) -> dict[str, int]:
    query = (
        "select json_build_object("
        "'users',(select count(*) from users),"
        "'workspaces',(select count(*) from workspaces),"
        "'boards',(select count(*) from boards),"
        "'cards',(select count(*) from cards)"
        ")::text;"
    )
    result = run_capture(
        compose_command(
            source_root,
            "exec",
            "-T",
            "postgres",
            "psql",
            "--username",
            "p2pkanban",
            "--dbname",
            "p2pkanban",
            "--tuples-only",
            "--no-align",
            "--command",
            query,
        ),
        cwd=source_root,
        env=env,
        timeout=60,
    )
    if result.returncode != 0:
        raise BootstrapError(
            "Не удалось проверить количество пользователей и досок перед обновлением."
        )
    try:
        value = json.loads(result.stdout.strip())
    except json.JSONDecodeError as exc:
        raise BootstrapError(
            "PostgreSQL вернул неожиданный результат контрольной проверки."
        ) from exc
    if not isinstance(value, dict):
        raise BootstrapError("Контрольная проверка PostgreSQL вернула неверный формат.")
    return {
        key: int(value.get(key, 0))
        for key in ("users", "workspaces", "boards", "cards")
    }


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tag_running_images(
    source_root: Path,
    env: dict[str, str],
    rollback_tag: str,
) -> None:
    docker = docker_executable()
    for service, repository in (
        ("backend", "p2pkanban/backend"),
        ("web", "p2pkanban/web"),
    ):
        container = run_capture(
            compose_command(source_root, "ps", "--quiet", service),
            cwd=source_root,
            env=env,
            timeout=30,
        )
        container_id = container.stdout.strip()
        if container.returncode != 0 or not container_id:
            raise BootstrapError(
                f"Не найден запущенный контейнер {service}; сначала запустите p2pKanban."
            )
        image = run_capture(
            [docker, "inspect", "--format", "{{.Image}}", container_id],
            cwd=source_root,
            env=env,
            timeout=30,
        )
        image_id = image.stdout.strip()
        if image.returncode != 0 or not image_id:
            raise BootstrapError(f"Не удалось определить image контейнера {service}.")
        tagged = run_capture(
            [docker, "image", "tag", image_id, f"{repository}:{rollback_tag}"],
            cwd=source_root,
            env=env,
            timeout=60,
        )
        if tagged.returncode != 0:
            raise BootstrapError(
                f"Не удалось сохранить rollback-тег для контейнера {service}."
            )


def assert_counts_preserved(before: dict[str, int], after: dict[str, int]) -> None:
    decreased = [
        f"{key}: {before[key]} → {after.get(key, 0)}"
        for key in before
        if after.get(key, 0) < before[key]
    ]
    if decreased:
        raise BootstrapError(
            "После обновления уменьшилось количество основных сущностей: "
            + ", ".join(decreased)
        )


def write_update_report(
    project_root: Path,
    report_id: str,
    payload: dict[str, Any],
) -> Path:
    directory = project_root / UPDATE_REPORTS_RELATIVE_PATH
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{report_id}.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def install_launcher_update(
    project_root: Path,
    source_root: Path,
    update_id: str,
) -> str | None:
    backup_root = (
        project_root / ".dev-bootstrap" / "launcher-backups" / update_id
    )
    pairs = (
        (project_root / "tools/container_bootstrap.py", source_root / "tools/container_bootstrap.py"),
        (project_root / "bootstrap.py", source_root / "bootstrap.py"),
    )
    try:
        backup_root.mkdir(parents=True, exist_ok=False)
        for destination, _source in pairs:
            relative = destination.relative_to(project_root)
            backup = backup_root / relative
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(destination, backup)
        for destination, source in pairs:
            temporary = destination.with_name(f"{destination.name}.update-tmp")
            shutil.copy2(source, temporary)
            os.replace(temporary, destination)
    except OSError as exc:
        return str(exc)
    return None


def prepare_update_source(
    args: argparse.Namespace,
    project_root: Path,
    state: dict[str, Any],
    staging_parent: Path,
) -> tuple[Path, dict[str, Any]]:
    if args.source_dir:
        source = Path(args.source_dir).expanduser().resolve()
        if not source.is_dir():
            raise BootstrapError(f"Каталог обновления не найден: {source}")
        staging = staging_parent / "source"
        copy_source_tree(source, staging)
        version = validate_update_source(staging)
        fingerprint = source_fingerprint(staging)
        return staging, {
            "kind": "local-directory",
            "repository": None,
            "branch": None,
            "revision": fingerprint,
            "version": version,
        }

    branch = args.branch or str(state.get("updateBranch") or DEFAULT_UPDATE_BRANCH)
    repository = discover_update_repository(
        project_root,
        state,
        args.repository,
    )
    if not repository:
        raise BootstrapError(
            "Не удалось определить GitHub-репозиторий. Для первой настройки "
            "выполните: python bootstrap.py update "
            "--repository https://github.com/owner/repository"
        )

    archive_path = staging_parent / "source.zip"
    archive_sha = download_update_archive(
        github_branch_archive_url(repository, branch),
        archive_path,
    )
    extracted_parent = staging_parent / "extracted"
    extracted_parent.mkdir()
    extracted = safe_extract_zip(archive_path, extracted_parent)
    staging = staging_parent / "source"
    os.replace(extracted, staging)
    version = validate_update_source(staging)
    build_info = read_json_object(staging / BUILD_INFO_FILENAME)
    revision = str(build_info.get("gitCommit") or archive_sha)
    return staging, {
        "kind": "github-branch",
        "repository": repository,
        "branch": branch,
        "revision": revision,
        "archiveSha256": archive_sha,
        "version": version,
    }


def stack_state(
    *,
    web_port: int,
    bind_address: str,
    status: str,
    previous: dict[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    created_at = (previous or {}).get("createdAt") or iso_now()
    result: dict[str, Any] = dict(previous or {})
    result.update(
        {
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
    )
    result.pop("lastError", None)
    if error:
        result["lastError"] = error
    return result


def command_start(args: argparse.Namespace, project_root: Path) -> int:
    previous = load_state(project_root)
    source_root = active_source_root(project_root, previous)
    web_port = choose_web_port(args.port, previous)
    previous_listen = "lan" if previous.get("bindAddress") == "0.0.0.0" else "local"
    listen = args.listen or previous_listen
    bind_address = listen_to_bind_address(listen)
    public_url = f"http://127.0.0.1:{web_port}"
    health_url = f"{public_url}/healthz"
    env = compose_environment(
        web_port,
        bind_address,
        configured_image_tag(previous),
    )
    up_arguments = ["up", "--detach", "--remove-orphans"]
    if not args.no_build:
        up_arguments.append("--build")
    command = compose_command(
        source_root,
        *up_arguments,
        allow_missing_docker=args.dry_run,
    )

    if args.dry_run:
        print("План zero-config запуска:")
        print(f"- Web: {public_url}")
        print(f"- Доступ: {'локальная сеть' if listen == 'lan' else 'только этот компьютер'}")
        print("- PostgreSQL, роль, БД и секреты создаются внутри Docker.")
        if source_root != project_root:
            print(
                "- Код: активная проверенная версия из "
                f"{relative_state_path(project_root, source_root)}"
            )
        print(f"- Команда: {display_command(command)}")
        if shutil.which("docker") is None:
            print("- Docker сейчас не найден; реальный запуск потребует Docker Compose v2.")
        return 0

    ensure_docker_ready(source_root, env)
    validate_compose(source_root, env)

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
        cwd=str(source_root),
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
        print_compose_diagnostics(source_root, env)
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
        print_compose_diagnostics(source_root, env)
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
    source_root = active_source_root(project_root, state)
    web_port = configured_web_port(state)
    bind_address = str(state.get("bindAddress") or "127.0.0.1")
    env = compose_environment(web_port, bind_address, configured_image_tag(state))
    public_url = f"http://127.0.0.1:{web_port}"

    ensure_docker_ready(source_root, env)
    result = run_capture(
        compose_command(source_root, "ps", "--all"),
        cwd=source_root,
        env=env,
        timeout=60,
    )
    if result.stdout.strip():
        print(result.stdout.rstrip())
    print(f"\nWeb: {'доступен' if http_ready(public_url + '/healthz') else 'не отвечает'}")
    print(f"URL: {public_url}")
    print(f"Версия: {state.get('appVersion') or read_version(source_root)}")
    if state.get("lastUpdateReport"):
        print(f"Последнее обновление: {state['lastUpdateReport']}")
    return 0 if result.returncode == 0 else 1


def command_logs(args: argparse.Namespace, project_root: Path) -> int:
    state = load_state(project_root)
    source_root = active_source_root(project_root, state)
    web_port = configured_web_port(state)
    bind_address = str(state.get("bindAddress") or "127.0.0.1")
    env = compose_environment(web_port, bind_address, configured_image_tag(state))
    ensure_docker_ready(source_root, env)
    arguments = ["logs", "--tail", str(args.tail)]
    if args.follow:
        arguments.append("--follow")
    try:
        return subprocess.run(
            compose_command(source_root, *arguments),
            cwd=str(source_root),
            env=env,
            check=False,
        ).returncode
    except KeyboardInterrupt:
        return 130


def command_stop(args: argparse.Namespace, project_root: Path) -> int:
    state = load_state(project_root)
    source_root = active_source_root(project_root, state)
    web_port = configured_web_port(state)
    bind_address = str(state.get("bindAddress") or "127.0.0.1")
    env = compose_environment(web_port, bind_address, configured_image_tag(state))
    command = compose_command(
        source_root,
        "down",
        "--remove-orphans",
        allow_missing_docker=args.dry_run,
    )
    if args.dry_run:
        print(display_command(command))
        print("БД и секреты сохранятся в Docker volumes.")
        return 0

    ensure_docker_ready(source_root, env)
    completed = subprocess.run(
        command,
        cwd=str(source_root),
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
    source_root = active_source_root(project_root, state)
    web_port = configured_web_port(state)
    bind_address = str(state.get("bindAddress") or "127.0.0.1")
    env = compose_environment(web_port, bind_address, configured_image_tag(state))
    command = compose_command(
        source_root,
        "down",
        "--volumes",
        "--remove-orphans",
        allow_missing_docker=args.dry_run,
    )
    if args.dry_run:
        print(display_command(command))
        print("Будут удалены контейнеры, локальная БД и сгенерированные секреты.")
        return 0

    ensure_docker_ready(source_root, env)
    completed = subprocess.run(
        command,
        cwd=str(source_root),
        env=env,
        check=False,
    )
    if completed.returncode != 0:
        raise BootstrapError("Docker не смог удалить stack volumes.")
    remove_state(project_root)
    print("Локальные контейнеры, БД и секреты p2pKanban удалены.")
    return 0


def command_update(args: argparse.Namespace, project_root: Path) -> int:
    state = load_state(project_root)
    current_source = active_source_root(project_root, state)
    current_version = str(state.get("appVersion") or read_version(current_source))
    web_port = configured_web_port(state)
    bind_address = str(state.get("bindAddress") or "127.0.0.1")
    public_url = f"http://127.0.0.1:{web_port}"
    current_env = compose_environment(
        web_port,
        bind_address,
        configured_image_tag(state),
    )

    releases_root = project_root / UPDATE_RELEASES_RELATIVE_PATH
    releases_root.mkdir(parents=True, exist_ok=True)
    incoming = releases_root / f".incoming-{int(time.time())}-{os.getpid()}"
    final_base: Path | None = None
    switched_successfully = False

    with update_lock(project_root):
        try:
            incoming.mkdir()
            source_root, source_metadata = prepare_update_source(
                args,
                project_root,
                state,
                incoming,
            )
            target_version = str(source_metadata["version"])
            target_revision = str(source_metadata["revision"])
            revision_short = safe_identifier(target_revision[:12], fallback="source")
            update_id = (
                f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-"
                f"{safe_identifier(target_version)}-{revision_short}"
            )
            final_base = releases_root / update_id
            if final_base.exists():
                raise BootstrapError(
                    f"Каталог обновления уже существует: {final_base.name}"
                )
            os.replace(incoming, final_base)
            source_root = final_base / "source"
            for temporary_name in ("source.zip", "extracted"):
                temporary_path = final_base / temporary_name
                if temporary_path.is_dir():
                    shutil.rmtree(temporary_path, ignore_errors=True)
                else:
                    try:
                        temporary_path.unlink()
                    except FileNotFoundError:
                        pass

            if (
                not args.force
                and state.get("activeRevision") == target_revision
                and state.get("appVersion") == target_version
            ):
                shutil.rmtree(final_base, ignore_errors=True)
                print(
                    f"Обновление не требуется: уже используется "
                    f"{target_version} ({revision_short})."
                )
                return 0

            target_image_tag = safe_identifier(
                f"{target_version}-{revision_short}",
                fallback="update",
            )
            target_env = compose_environment(
                web_port,
                bind_address,
                target_image_tag,
            )

            if args.dry_run:
                print("План обновления p2pKanban:")
                print(f"- Сейчас: {current_version}")
                print(f"- Источник: {source_metadata['kind']}")
                if source_metadata.get("repository"):
                    print(
                        f"- GitHub: {source_metadata['repository']} "
                        f"({source_metadata['branch']})"
                    )
                print(f"- Получено: {target_version} ({revision_short})")
                print("- Работающий stack не меняется до окончания новой сборки.")
                print("- Перед переключением будет создан PostgreSQL backup.")
                print("- БД и секреты останутся в прежних Docker volumes.")
                print("- При ошибке readiness вернутся старые backend/web images.")
                shutil.rmtree(final_base, ignore_errors=True)
                return 0

            ensure_docker_ready(current_source, current_env)
            require_free_space(project_root)
            if not http_ready(public_url + "/healthz"):
                raise BootstrapError(
                    "Текущий p2pKanban не отвечает. Сначала выполните "
                    "python bootstrap.py start, затем повторите update."
                )

            validate_compose(source_root, target_env)
            run_source_self_check(source_root, target_env)

            print(
                f"Собираю p2pKanban {target_version}. "
                "Текущая версия продолжает работать."
            )
            build = subprocess.run(
                compose_command(
                    source_root,
                    "build",
                    "--pull",
                    "backend",
                    "web",
                ),
                cwd=str(source_root),
                env=target_env,
                check=False,
            )
            if build.returncode != 0:
                raise BootstrapError(
                    "Новые images не собрались. Работающий stack не изменён."
                )

            backup_id = f"update-{update_id}"
            print("Создаю backup PostgreSQL перед переключением.")
            dump_path, counts_before = create_database_backup(
                current_source,
                project_root,
                current_env,
                backup_id,
            )

            rollback_tag = safe_identifier(
                f"rollback-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
                fallback="rollback",
            )
            tag_running_images(current_source, current_env, rollback_tag)

            report: dict[str, Any] = {
                "schemaVersion": 1,
                "toolVersion": TOOL_VERSION,
                "status": "switching",
                "startedAt": iso_now(),
                "from": {
                    "version": current_version,
                    "sourceRoot": relative_state_path(project_root, current_source)
                    if current_source != project_root
                    else None,
                    "imageTag": configured_image_tag(state),
                },
                "to": {
                    **source_metadata,
                    "sourceRoot": relative_state_path(project_root, source_root),
                    "imageTag": target_image_tag,
                },
                "backup": {
                    "path": relative_state_path(project_root, dump_path),
                    "sha256": file_sha256(dump_path),
                    "counts": counts_before,
                },
                "volumesRemoved": False,
            }

            print("Переключаю backend и web на новую версию.")
            switched = subprocess.run(
                compose_command(
                    source_root,
                    "up",
                    "--detach",
                    "--no-build",
                    "--remove-orphans",
                ),
                cwd=str(source_root),
                env=target_env,
                check=False,
            )
            ready = switched.returncode == 0 and wait_until_ready(
                public_url + "/healthz",
                args.timeout_seconds,
            )

            if not ready:
                rollback_env = compose_environment(
                    web_port,
                    bind_address,
                    rollback_tag,
                )
                print(
                    "Новая версия не прошла readiness. "
                    "Возвращаю предыдущие images.",
                    file=sys.stderr,
                )
                subprocess.run(
                    compose_command(
                        current_source,
                        "up",
                        "--detach",
                        "--no-build",
                        "--remove-orphans",
                    ),
                    cwd=str(current_source),
                    env=rollback_env,
                    check=False,
                )
                rollback_ready = wait_until_ready(
                    public_url + "/healthz",
                    min(args.timeout_seconds, 180),
                )
                report.update(
                    {
                        "status": "rolled_back",
                        "finishedAt": iso_now(),
                        "rollbackReady": rollback_ready,
                    }
                )
                report_path = write_update_report(project_root, update_id, report)
                shutil.rmtree(final_base, ignore_errors=True)
                raise BootstrapError(
                    "Обновление отменено, предыдущая версия "
                    + ("снова доступна." if rollback_ready else "не прошла readiness.")
                    + f" Отчёт: {relative_state_path(project_root, report_path)}"
                )

            try:
                counts_after = database_counts(source_root, target_env)
                assert_counts_preserved(counts_before, counts_after)
            except BootstrapError as verification_error:
                rollback_env = compose_environment(
                    web_port,
                    bind_address,
                    rollback_tag,
                )
                subprocess.run(
                    compose_command(
                        current_source,
                        "up",
                        "--detach",
                        "--no-build",
                        "--remove-orphans",
                    ),
                    cwd=str(current_source),
                    env=rollback_env,
                    check=False,
                )
                rollback_ready = wait_until_ready(
                    public_url + "/healthz",
                    min(args.timeout_seconds, 180),
                )
                report.update(
                    {
                        "status": "rolled_back",
                        "finishedAt": iso_now(),
                        "rollbackReady": rollback_ready,
                        "verificationError": str(verification_error),
                    }
                )
                report_path = write_update_report(project_root, update_id, report)
                shutil.rmtree(final_base, ignore_errors=True)
                raise BootstrapError(
                    f"{verification_error} Предыдущие images возвращены. "
                    f"Отчёт: {relative_state_path(project_root, report_path)}"
                ) from verification_error
            switched_successfully = True

            previous_source_relative = (
                relative_state_path(project_root, current_source)
                if current_source != project_root
                else None
            )
            history = list(state.get("releaseHistory") or [])
            history.append(
                {
                    "updatedAt": iso_now(),
                    "fromVersion": current_version,
                    "fromRevision": state.get("activeRevision"),
                    "previousSourceRoot": previous_source_relative,
                    "previousImageTag": rollback_tag,
                    "toVersion": target_version,
                    "toRevision": target_revision,
                    "sourceRoot": relative_state_path(project_root, source_root),
                    "imageTag": target_image_tag,
                    "backup": relative_state_path(project_root, dump_path),
                }
            )

            next_state = stack_state(
                web_port=web_port,
                bind_address=bind_address,
                status="running",
                previous=state,
            )
            next_state.update(
                {
                    "activeSourceRoot": relative_state_path(
                        project_root,
                        source_root,
                    ),
                    "activeRevision": target_revision,
                    "appVersion": target_version,
                    "imageTag": target_image_tag,
                    "updateRepository": source_metadata.get("repository")
                    or state.get("updateRepository"),
                    "updateBranch": source_metadata.get("branch")
                    or state.get("updateBranch")
                    or DEFAULT_UPDATE_BRANCH,
                    "releaseHistory": history[-10:],
                }
            )

            report.update(
                {
                    "status": "succeeded",
                    "finishedAt": iso_now(),
                    "countsAfter": counts_after,
                    "healthUrl": public_url + "/healthz",
                }
            )
            report_path = write_update_report(project_root, update_id, report)
            next_state["lastUpdateReport"] = relative_state_path(
                project_root,
                report_path,
            )
            write_state(project_root, next_state)

            launcher_warning = install_launcher_update(
                project_root,
                source_root,
                update_id,
            )

            print("\np2pKanban обновлён.")
            print(f"Версия: {current_version} → {target_version}")
            print(f"Открыть: {public_url}")
            print(f"Backup: {relative_state_path(project_root, dump_path)}")
            print(f"Отчёт: {relative_state_path(project_root, report_path)}")
            print("Вернуть прошлую версию: python bootstrap.py rollback")
            if launcher_warning:
                print(
                    "Stack обновлён, но launcher не смог обновить собственные "
                    f"файлы: {launcher_warning}",
                    file=sys.stderr,
                )
            return 0
        except Exception:
            if incoming.exists():
                shutil.rmtree(incoming, ignore_errors=True)
            if final_base and final_base.exists() and not switched_successfully:
                shutil.rmtree(final_base, ignore_errors=True)
            raise


def command_rollback(args: argparse.Namespace, project_root: Path) -> int:
    state = load_state(project_root)
    history = list(state.get("releaseHistory") or [])
    candidate = next(
        (
            item
            for item in reversed(history)
            if isinstance(item, dict) and not item.get("rolledBackAt")
        ),
        None,
    )
    if candidate is None:
        raise BootstrapError("Нет предыдущего успешного обновления для rollback.")

    current_source = active_source_root(project_root, state)
    previous_source = (
        resolve_state_path(project_root, candidate.get("previousSourceRoot"))
        or project_root
    )
    previous_image_tag = str(candidate.get("previousImageTag") or "")
    if not previous_image_tag:
        raise BootstrapError("В истории обновления нет сохранённого rollback image.")
    if not (previous_source / COMPOSE_RELATIVE_PATH).is_file():
        raise BootstrapError("Исходники предыдущей версии больше не найдены.")

    web_port = configured_web_port(state)
    bind_address = str(state.get("bindAddress") or "127.0.0.1")
    public_url = f"http://127.0.0.1:{web_port}"
    current_env = compose_environment(
        web_port,
        bind_address,
        configured_image_tag(state),
    )
    previous_env = compose_environment(
        web_port,
        bind_address,
        previous_image_tag,
    )
    rollback_id = f"rollback-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    with update_lock(project_root):
        if args.dry_run:
            print("План rollback:")
            print(
                f"- Версия: {state.get('appVersion') or read_version(current_source)} "
                f"→ {candidate.get('fromVersion') or read_version(previous_source)}"
            )
            print("- Перед переключением будет создан новый PostgreSQL backup.")
            print("- PostgreSQL volume автоматически не восстанавливается.")
            return 0

        ensure_docker_ready(current_source, current_env)
        if not http_ready(public_url + "/healthz"):
            raise BootstrapError(
                "Текущий stack не отвечает; безопасный rollback остановлен."
            )
        dump_path, counts_before = create_database_backup(
            current_source,
            project_root,
            current_env,
            rollback_id,
        )

        switched = subprocess.run(
            compose_command(
                previous_source,
                "up",
                "--detach",
                "--no-build",
                "--remove-orphans",
            ),
            cwd=str(previous_source),
            env=previous_env,
            check=False,
        )
        if switched.returncode != 0 or not wait_until_ready(
            public_url + "/healthz",
            args.timeout_seconds,
        ):
            subprocess.run(
                compose_command(
                    current_source,
                    "up",
                    "--detach",
                    "--no-build",
                    "--remove-orphans",
                ),
                cwd=str(current_source),
                env=current_env,
                check=False,
            )
            raise BootstrapError(
                "Предыдущая версия не прошла readiness; текущие images возвращены."
            )

        try:
            counts_after = database_counts(previous_source, previous_env)
            assert_counts_preserved(counts_before, counts_after)
        except BootstrapError as verification_error:
            subprocess.run(
                compose_command(
                    current_source,
                    "up",
                    "--detach",
                    "--no-build",
                    "--remove-orphans",
                ),
                cwd=str(current_source),
                env=current_env,
                check=False,
            )
            wait_until_ready(public_url + "/healthz", min(args.timeout_seconds, 180))
            raise BootstrapError(
                f"Rollback не прошёл контроль данных: {verification_error}. "
                "Текущие images возвращены."
            ) from verification_error
        candidate["rolledBackAt"] = iso_now()

        next_state = stack_state(
            web_port=web_port,
            bind_address=bind_address,
            status="running",
            previous=state,
        )
        if previous_source == project_root:
            next_state.pop("activeSourceRoot", None)
        else:
            next_state["activeSourceRoot"] = relative_state_path(
                project_root,
                previous_source,
            )
        next_state.update(
            {
                "imageTag": previous_image_tag,
                "appVersion": candidate.get("fromVersion")
                or read_version(previous_source),
                "activeRevision": candidate.get("fromRevision"),
                "releaseHistory": history,
            }
        )
        report = {
            "schemaVersion": 1,
            "toolVersion": TOOL_VERSION,
            "status": "succeeded",
            "kind": "rollback",
            "finishedAt": iso_now(),
            "fromVersion": state.get("appVersion"),
            "toVersion": next_state.get("appVersion"),
            "backup": relative_state_path(project_root, dump_path),
            "countsBefore": counts_before,
            "countsAfter": counts_after,
            "databaseRestored": False,
        }
        report_path = write_update_report(project_root, rollback_id, report)
        next_state["lastUpdateReport"] = relative_state_path(
            project_root,
            report_path,
        )
        write_state(project_root, next_state)
        print(
            f"Предыдущая версия {next_state['appVersion']} снова запущена. "
            "БД не восстанавливалась и осталась на текущем состоянии."
        )
        print(f"Backup перед rollback: {relative_state_path(project_root, dump_path)}")
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

    update = subparsers.add_parser(
        "update",
        help="Безопасно обновить backend и web, сохранив БД и секреты.",
    )
    update.add_argument(
        "--repository",
        help=(
            "GitHub-репозиторий. Нужен один раз, если адрес не встроен "
            "в release bundle и рядом нет Git remote."
        ),
    )
    update.add_argument(
        "--branch",
        default=None,
        help=f"Ветка обновления, по умолчанию {DEFAULT_UPDATE_BRANCH}.",
    )
    update.add_argument(
        "--source-dir",
        help="Локальный каталог новой версии для теста или разработки.",
    )
    update.add_argument(
        "--force",
        action="store_true",
        help="Повторить обновление, даже если revision уже активна.",
    )
    update.add_argument(
        "--dry-run",
        action="store_true",
        help="Получить и проверить источник, но не запускать Docker.",
    )
    update.add_argument(
        "--timeout-seconds",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="Сколько ждать readiness новой версии.",
    )
    update.set_defaults(func=command_update)

    rollback = subparsers.add_parser(
        "rollback",
        help="Вернуть images предыдущей версии без восстановления старой БД.",
    )
    rollback.add_argument(
        "--dry-run",
        action="store_true",
        help="Показать план без изменения stack.",
    )
    rollback.add_argument(
        "--timeout-seconds",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="Сколько ждать readiness предыдущей версии.",
    )
    rollback.set_defaults(func=command_rollback)

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
