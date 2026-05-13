#!/usr/bin/env python3
"""
devbootstrap — local development diagnostics and bootstrap helpers for p2p_planner.

Commands:
    python tools/devbootstrap.py diagnose
    python tools/devbootstrap.py diagnose --no-write-report
    python tools/devbootstrap.py plan
    python tools/devbootstrap.py prepare-env
    python tools/devbootstrap.py start-db
    python tools/devbootstrap.py diagnose --section postgres
    python tools/devbootstrap.py status

The tool intentionally uses only Python standard library modules.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TOOL_VERSION = "0.3.0-phase3"
STATE_VERSION = 1
BOOTSTRAP_DIR_NAME = ".dev-bootstrap"
DEFAULT_PORTS = {
    "postgres": 5432,
    "backend": 18080,
    "frontend": 5173,
}
REQUIRED_PROJECT_PATHS = [
    "backend",
    "frontend",
    "docs",
    "docker-compose.dev.yml",
    "backend/Cargo.toml",
    "backend/.env.example",
    "backend/build.rs",
    "backend/migrations",
    "frontend/package.json",
    "frontend/package-lock.json",
    "frontend/.env.example",
    "docs/dev-bootstrap/dev-autodeployer-v1-development-plan.md",
]
OPTIONAL_PROJECT_PATHS = [
    "tools/devctl.py",
    "docs/devctl/devctl-patch-conveyor-spec.md",
    "backend/tests/smoke_core_api.py",
    "frontend/playwright.config.ts",
]
TOOL_COMMANDS = {
    "python": [sys.executable, "--version"],
    "git": ["git", "--version"],
    "cargo": ["cargo", "--version"],
    "rustc": ["rustc", "--version"],
    "node": ["node", "--version"],
    "npm": ["npm", "--version"],
    "docker": ["docker", "--version"],
    "docker_compose": ["docker", "compose", "version"],
    "docker_compose_legacy": ["docker-compose", "version"],
    "psql": ["psql", "--version"],
    "pg_isready": ["pg_isready", "--version"],
}
COMPOSE_FILE = "docker-compose.dev.yml"
POSTGRES_SERVICE_NAME = "postgres"
POSTGRES_CONTAINER_NAME = "p2p-planner-postgres-dev"

HEALTH_URLS = {
    "backend_health_root": "http://127.0.0.1:18080/health",
    "backend_health_api": "http://127.0.0.1:18080/api/v1/health",
    "frontend_root": "http://127.0.0.1:5173/",
}
ENV_CONTRACTS = {
    "backend": {
        "example": "backend/.env.example",
        "target": "backend/.env",
        "description": "Backend runtime environment",
    },
    "frontend": {
        "example": "frontend/.env.example",
        "target": "frontend/.env.local",
        "description": "Frontend Vite local environment",
    },
}
SECRET_KEY_MARKERS = (
    "SECRET",
    "PASSWORD",
    "TOKEN",
    "COOKIE",
    "DATABASE__URL",
    "DATABASE_URL",
)


@dataclass
class CommandProbe:
    name: str
    command: list[str]
    available: bool
    path: str | None = None
    version: str | None = None
    error: str | None = None


@dataclass
class PortProbe:
    name: str
    host: str
    port: int
    open: bool
    error: str | None = None


@dataclass
class HttpProbe:
    name: str
    url: str
    reachable: bool
    status: int | None = None
    error: str | None = None
    duration_ms: int | None = None


@dataclass
class ProjectPathProbe:
    path: str
    exists: bool
    kind: str
    required: bool


@dataclass
class EnvFileProbe:
    name: str
    description: str
    example_path: str
    target_path: str
    example_exists: bool
    target_exists: bool
    example_keys: list[str]
    target_keys: list[str]
    missing_keys: list[str]
    extra_keys: list[str]
    masked_values: dict[str, str]
    parse_warnings: list[str] = field(default_factory=list)


@dataclass
class EnvConsistencyCheck:
    code: str
    status: str
    message: str
    evidence: str | None = None


@dataclass
class EnvAction:
    code: str
    status: str
    message: str
    path: str | None = None


@dataclass
class EnvPlanResult:
    generated_at: str
    tool_version: str
    project_root: str | None
    invoked_from: str
    mode: str
    files: list[EnvFileProbe] = field(default_factory=list)
    checks: list[EnvConsistencyCheck] = field(default_factory=list)
    actions: list[EnvAction] = field(default_factory=list)
    failures: list[dict[str, str]] = field(default_factory=list)
    warnings: list[dict[str, str]] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)
    report_dir: str | None = None


@dataclass
class DatabaseUrlProbe:
    raw_present: bool
    masked_url: str | None = None
    scheme: str | None = None
    host: str | None = None
    port: int | None = None
    database: str | None = None
    username: str | None = None
    has_password: bool = False
    warnings: list[str] = field(default_factory=list)


@dataclass
class ProcessProbe:
    name: str
    command: list[str]
    available: bool
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    error: str | None = None


@dataclass
class PostgresCheck:
    code: str
    status: str
    message: str
    evidence: str | None = None


@dataclass
class PostgresAction:
    code: str
    status: str
    message: str
    command: str | None = None
    evidence: str | None = None


@dataclass
class PostgresResult:
    generated_at: str
    tool_version: str
    project_root: str | None
    invoked_from: str
    mode: str
    dry_run: bool = False
    database_url: DatabaseUrlProbe | None = None
    port: PortProbe | None = None
    psql: ProcessProbe | None = None
    pg_isready: ProcessProbe | None = None
    docker: ProcessProbe | None = None
    docker_daemon: ProcessProbe | None = None
    compose: ProcessProbe | None = None
    compose_command: list[str] = field(default_factory=list)
    compose_status: ProcessProbe | None = None
    docker_health: ProcessProbe | None = None
    classification: str = "unknown"
    checks: list[PostgresCheck] = field(default_factory=list)
    actions: list[PostgresAction] = field(default_factory=list)
    failures: list[dict[str, str]] = field(default_factory=list)
    warnings: list[dict[str, str]] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)
    report_dir: str | None = None


@dataclass
class DiagnoseResult:
    generated_at: str
    tool_version: str
    project_root: str | None
    invoked_from: str
    platform: dict[str, str]
    paths: list[ProjectPathProbe] = field(default_factory=list)
    tools: list[CommandProbe] = field(default_factory=list)
    ports: list[PortProbe] = field(default_factory=list)
    http: list[HttpProbe] = field(default_factory=list)
    state: dict[str, Any] = field(default_factory=dict)
    failures: list[dict[str, str]] = field(default_factory=list)
    warnings: list[dict[str, str]] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)
    report_dir: str | None = None


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return now_utc().isoformat(timespec="seconds")


def run_id(command: str) -> str:
    return now_utc().strftime("%Y%m%d_%H%M%S_") + command


def safe_decode(data: bytes | str | None) -> str:
    if data is None:
        return ""
    if isinstance(data, str):
        return data
    return data.decode("utf-8", errors="replace")


def print_header(title: str) -> None:
    print(f"\n== {title} ==")


def rel(path: Path, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except Exception:
        return str(path)


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        return {"_error": f"invalid json: {exc}"}
    if isinstance(data, dict):
        return data
    return {"_error": "json root is not an object"}


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def looks_like_project_root(path: Path) -> bool:
    return (
        (path / "backend").is_dir()
        and (path / "frontend").is_dir()
        and (path / "docs").is_dir()
        and (path / "docker-compose.dev.yml").is_file()
    )


def find_project_root(start: Path) -> Path | None:
    current = start.resolve()
    if current.is_file():
        current = current.parent
    for candidate in [current, *current.parents]:
        if looks_like_project_root(candidate):
            return candidate
        nested = candidate / "project"
        if looks_like_project_root(nested):
            return nested.resolve()
    return None


def project_path_probe(project_root: Path, relative_path: str, *, required: bool) -> ProjectPathProbe:
    path = project_root / relative_path
    if path.is_dir():
        kind = "dir"
    elif path.is_file():
        kind = "file"
    else:
        kind = "missing"
    return ProjectPathProbe(path=relative_path, exists=path.exists(), kind=kind, required=required)


def command_display(command: list[str]) -> str:
    return " ".join(command)


def run_probe_command(command: list[str], *, timeout: int = 5) -> tuple[bool, str | None]:
    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return False, "command not found"
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except OSError as exc:
        return False, str(exc)
    output = (safe_decode(completed.stdout).strip() or safe_decode(completed.stderr).strip()).splitlines()
    text = output[0] if output else f"exit code {completed.returncode}"
    if completed.returncode != 0:
        return False, text
    return True, text


def probe_tool(name: str, command: list[str]) -> CommandProbe:
    executable = command[0]
    path = sys.executable if executable == sys.executable else shutil.which(executable)
    if not path:
        return CommandProbe(name=name, command=command, available=False, error="not found on PATH")
    ok, text = run_probe_command(command)
    if ok:
        return CommandProbe(name=name, command=command, available=True, path=path, version=text)
    return CommandProbe(name=name, command=command, available=False, path=path, error=text)


def probe_port(name: str, port: int, host: str = "127.0.0.1", timeout: float = 0.4) -> PortProbe:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return PortProbe(name=name, host=host, port=port, open=True)
    except OSError as exc:
        return PortProbe(name=name, host=host, port=port, open=False, error=str(exc))


def probe_http(name: str, url: str, timeout: float = 1.5) -> HttpProbe:
    started = time.monotonic()
    try:
        request = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            duration_ms = int((time.monotonic() - started) * 1000)
            return HttpProbe(name=name, url=url, reachable=True, status=response.status, duration_ms=duration_ms)
    except urllib.error.HTTPError as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        # HTTP reached the server even if the response is not 2xx.
        return HttpProbe(name=name, url=url, reachable=True, status=exc.code, error=str(exc), duration_ms=duration_ms)
    except Exception as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        return HttpProbe(name=name, url=url, reachable=False, error=str(exc), duration_ms=duration_ms)


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def summarize_state(project_root: Path) -> dict[str, Any]:
    state_path = project_root / BOOTSTRAP_DIR_NAME / "state.json"
    state = read_json(state_path)
    processes = state.get("processes") if isinstance(state.get("processes"), dict) else {}
    process_summary: dict[str, Any] = {}
    for name, value in processes.items():
        if not isinstance(value, dict):
            continue
        pid_raw = value.get("pid")
        try:
            pid = int(pid_raw)
        except (TypeError, ValueError):
            pid = -1
        process_summary[name] = {
            "pid": pid_raw,
            "alive": pid_alive(pid),
            "cwd": value.get("cwd"),
            "command": value.get("command"),
            "runId": value.get("runId"),
        }
    return {
        "statePath": rel(state_path, project_root),
        "exists": state_path.exists(),
        "valid": "_error" not in state,
        "error": state.get("_error"),
        "version": state.get("version"),
        "activeRunId": state.get("activeRunId"),
        "processes": process_summary,
        "lastReports": state.get("lastReports", []),
    }


def build_diagnose(project_root: Path | None, invoked_from: Path) -> DiagnoseResult:
    result = DiagnoseResult(
        generated_at=iso_now(),
        tool_version=TOOL_VERSION,
        project_root=str(project_root) if project_root else None,
        invoked_from=str(invoked_from),
        platform={
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "python": sys.version.split()[0],
            "pythonExecutable": sys.executable,
        },
    )

    if project_root is None:
        result.failures.append(
            {
                "code": "invalid_project_root",
                "message": "Could not find a project root containing backend/, frontend/, docs/ and docker-compose.dev.yml.",
            }
        )
        result.next_actions.append("Run this command from the project root, tools/, backend/ or frontend/ directory.")
        result.tools = [probe_tool(name, command) for name, command in TOOL_COMMANDS.items()]
        return result

    result.paths.extend(project_path_probe(project_root, path, required=True) for path in REQUIRED_PROJECT_PATHS)
    result.paths.extend(project_path_probe(project_root, path, required=False) for path in OPTIONAL_PROJECT_PATHS)
    result.tools = [probe_tool(name, command) for name, command in TOOL_COMMANDS.items()]
    result.ports = [probe_port(name, port) for name, port in DEFAULT_PORTS.items()]
    result.http = [probe_http(name, url) for name, url in HEALTH_URLS.items()]
    result.state = summarize_state(project_root)

    missing_required = [path.path for path in result.paths if path.required and not path.exists]
    if missing_required:
        result.failures.append(
            {
                "code": "missing_project_files",
                "message": "Required project files or directories are missing: " + ", ".join(missing_required),
            }
        )
        result.next_actions.append("Verify that the archive was extracted completely and that you are using the latest project state.")

    for tool in result.tools:
        if not tool.available and tool.name in {"cargo", "rustc", "node", "npm"}:
            result.warnings.append(
                {
                    "code": "missing_prerequisite",
                    "message": f"{tool.name} is not available; later phases will not be able to build or run all project layers.",
                }
            )
    if not any(tool.name == "docker" and tool.available for tool in result.tools):
        result.warnings.append(
            {
                "code": "docker_unavailable",
                "message": "Docker is not available; future start-db may need an existing PostgreSQL instead of compose.",
            }
        )

    backend_health = next((probe for probe in result.http if probe.name == "backend_health_api"), None)
    frontend_health = next((probe for probe in result.http if probe.name == "frontend_root"), None)
    if backend_health and not backend_health.reachable:
        result.next_actions.append("Backend is not reachable on http://127.0.0.1:18080 yet; this is expected before start-backend/up phases.")
    if frontend_health and not frontend_health.reachable:
        result.next_actions.append("Frontend is not reachable on http://127.0.0.1:5173 yet; this is expected before start-frontend/up phases.")

    return result


def as_jsonable(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return {key: as_jsonable(getattr(value, key)) for key in value.__dataclass_fields__}
    if isinstance(value, list):
        return [as_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): as_jsonable(item) for key, item in value.items()}
    return value


def create_report_dir(project_root: Path, command: str) -> Path:
    report_dir = project_root / BOOTSTRAP_DIR_NAME / "runs" / run_id(command)
    report_dir.mkdir(parents=True, exist_ok=False)
    return report_dir


def render_report(result: DiagnoseResult) -> str:
    lines: list[str] = []
    lines.append("# devbootstrap diagnose report")
    lines.append("")
    lines.append(f"- Generated at: `{result.generated_at}`")
    lines.append(f"- Tool version: `{result.tool_version}`")
    lines.append(f"- Invoked from: `{result.invoked_from}`")
    lines.append(f"- Project root: `{result.project_root or 'not found'}`")
    lines.append("")

    lines.append("## Platform")
    lines.append("")
    for key, value in result.platform.items():
        lines.append(f"- `{key}`: `{value}`")
    lines.append("")

    lines.append("## Project files")
    lines.append("")
    lines.append("| Status | Required | Kind | Path |")
    lines.append("|---|---:|---|---|")
    for item in result.paths:
        status = "OK" if item.exists else "MISSING"
        required = "yes" if item.required else "no"
        lines.append(f"| {status} | {required} | {item.kind} | `{item.path}` |")
    if not result.paths:
        lines.append("Project root was not found, so file checks were skipped.")
    lines.append("")

    lines.append("## Tools")
    lines.append("")
    lines.append("| Tool | Status | Version / error | Path |")
    lines.append("|---|---|---|---|")
    for tool in result.tools:
        status = "OK" if tool.available else "MISSING"
        version = tool.version or tool.error or ""
        path = tool.path or ""
        lines.append(f"| {tool.name} | {status} | `{version}` | `{path}` |")
    lines.append("")

    lines.append("## Ports")
    lines.append("")
    lines.append("| Name | Address | Status | Evidence |")
    lines.append("|---|---|---|---|")
    for port in result.ports:
        status = "open" if port.open else "closed/unreachable"
        evidence = "tcp connect succeeded" if port.open else (port.error or "")
        lines.append(f"| {port.name} | `{port.host}:{port.port}` | {status} | `{evidence}` |")
    if not result.ports:
        lines.append("Port checks were skipped because project root was not found.")
    lines.append("")

    lines.append("## HTTP probes")
    lines.append("")
    lines.append("| Name | URL | Status | Evidence |")
    lines.append("|---|---|---|---|")
    for probe in result.http:
        status = f"HTTP {probe.status}" if probe.reachable and probe.status is not None else "unreachable"
        evidence = probe.error or f"{probe.duration_ms} ms"
        lines.append(f"| {probe.name} | `{probe.url}` | {status} | `{evidence}` |")
    if not result.http:
        lines.append("HTTP probes were skipped because project root was not found.")
    lines.append("")

    lines.append("## State")
    lines.append("")
    if result.state:
        lines.append(f"- State file: `{result.state.get('statePath')}`")
        lines.append(f"- Exists: `{result.state.get('exists')}`")
        lines.append(f"- Valid: `{result.state.get('valid')}`")
        lines.append(f"- Active run: `{result.state.get('activeRunId')}`")
        processes = result.state.get("processes", {})
        if processes:
            lines.append("")
            lines.append("| Process | PID | Alive | Command | CWD |")
            lines.append("|---|---:|---|---|---|")
            for name, process in processes.items():
                lines.append(
                    f"| {name} | {process.get('pid')} | {process.get('alive')} | "
                    f"`{process.get('command')}` | `{process.get('cwd')}` |"
                )
        else:
            lines.append("- No registered devbootstrap-owned processes.")
    else:
        lines.append("State was not checked.")
    lines.append("")

    lines.append("## Findings")
    lines.append("")
    if not result.failures and not result.warnings:
        lines.append("- No blocking findings from phase 1 diagnostics.")
    for failure in result.failures:
        lines.append(f"- **FAIL** `{failure['code']}` — {failure['message']}")
    for warning in result.warnings:
        lines.append(f"- **WARN** `{warning['code']}` — {warning['message']}")
    lines.append("")

    lines.append("## Next safe actions")
    lines.append("")
    if result.next_actions:
        for action in result.next_actions:
            lines.append(f"- {action}")
    else:
        lines.append("- Continue with the next devbootstrap phase or run project checks manually.")
    lines.append("")
    return "\n".join(lines)


def write_reports(project_root: Path, result: DiagnoseResult, command: str) -> Path:
    report_dir = create_report_dir(project_root, command)
    result.report_dir = rel(report_dir, project_root)
    write_json(report_dir / "diagnose.json", as_jsonable(result))
    (report_dir / "report.md").write_text(render_report(result), encoding="utf-8")
    return report_dir




def is_secret_key(key: str) -> bool:
    upper = key.upper()
    return any(marker in upper for marker in SECRET_KEY_MARKERS)


def mask_database_url(value: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(value)
    except Exception:
        return "***"
    if not parsed.scheme or not parsed.netloc:
        return "***"
    username = urllib.parse.unquote(parsed.username or "")
    password = parsed.password
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    if username and password is not None:
        netloc = f"{username}:***@{host}{port}"
    elif username:
        netloc = f"{username}@{host}{port}"
    else:
        netloc = f"{host}{port}"
    return urllib.parse.urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))


def mask_value(key: str, value: str) -> str:
    if key.upper() in {"DATABASE__URL", "DATABASE_URL"}:
        return mask_database_url(value)
    if is_secret_key(key):
        return "***" if value else ""
    return value


def parse_env_file(path: Path) -> tuple[dict[str, str], list[str]]:
    values: dict[str, str] = {}
    warnings: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return values, warnings
    except UnicodeDecodeError as exc:
        return values, [f"could not decode as UTF-8: {exc}"]

    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            warnings.append(f"line {line_number}: ignored non KEY=VALUE line")
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            warnings.append(f"line {line_number}: ignored empty key")
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value
    return values, warnings


def env_effective_values(example_values: dict[str, str], target_values: dict[str, str]) -> dict[str, str]:
    effective = dict(example_values)
    effective.update(target_values)
    return effective


def parse_url_port(url: str) -> int | None:
    try:
        parsed = urllib.parse.urlsplit(url)
    except Exception:
        return None
    if parsed.port:
        return parsed.port
    if parsed.scheme == "http":
        return 80
    if parsed.scheme == "https":
        return 443
    return None


def parse_url_origin(url: str) -> str | None:
    try:
        parsed = urllib.parse.urlsplit(url)
    except Exception:
        return None
    if not parsed.scheme or not parsed.netloc:
        return None
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def build_env_file_probe(project_root: Path, name: str, contract: dict[str, str]) -> tuple[EnvFileProbe, dict[str, str], dict[str, str]]:
    example_rel = contract["example"]
    target_rel = contract["target"]
    example_path = project_root / example_rel
    target_path = project_root / target_rel
    example_values, example_warnings = parse_env_file(example_path)
    target_values, target_warnings = parse_env_file(target_path)

    example_keys = sorted(example_values)
    target_keys = sorted(target_values)
    missing_keys = sorted(key for key in example_keys if key not in target_values) if target_path.exists() else example_keys
    extra_keys = sorted(key for key in target_keys if key not in example_values)
    effective = env_effective_values(example_values, target_values)
    masked_values = {key: mask_value(key, value) for key, value in sorted(effective.items())}
    warnings: list[str] = []
    warnings.extend(f"example: {message}" for message in example_warnings)
    warnings.extend(f"target: {message}" for message in target_warnings)

    return (
        EnvFileProbe(
            name=name,
            description=contract["description"],
            example_path=example_rel,
            target_path=target_rel,
            example_exists=example_path.exists(),
            target_exists=target_path.exists(),
            example_keys=example_keys,
            target_keys=target_keys,
            missing_keys=missing_keys,
            extra_keys=extra_keys,
            masked_values=masked_values,
            parse_warnings=warnings,
        ),
        example_values,
        target_values,
    )


def check_env_consistency(
    backend_example: dict[str, str],
    backend_target: dict[str, str],
    frontend_example: dict[str, str],
    frontend_target: dict[str, str],
) -> list[EnvConsistencyCheck]:
    checks: list[EnvConsistencyCheck] = []
    backend = env_effective_values(backend_example, backend_target)
    frontend = env_effective_values(frontend_example, frontend_target)

    app_host = backend.get("APP__HOST", "127.0.0.1")
    app_port = backend.get("APP__PORT", "18080")
    try:
        int(app_port)
        checks.append(
            EnvConsistencyCheck(
                code="backend_port_parse",
                status="ok",
                message="APP__PORT is a valid integer.",
                evidence=f"APP__HOST={app_host}, APP__PORT={app_port}",
            )
        )
    except ValueError:
        checks.append(
            EnvConsistencyCheck(
                code="backend_port_parse",
                status="fail",
                message="APP__PORT is not a valid integer.",
                evidence=f"APP__PORT={app_port}",
            )
        )

    database_url = backend.get("DATABASE__URL", "")
    if database_url:
        try:
            parsed_db = urllib.parse.urlsplit(database_url)
            db_name = parsed_db.path.lstrip("/") or "<missing>"
            if parsed_db.scheme and parsed_db.hostname and db_name != "<missing>":
                checks.append(
                    EnvConsistencyCheck(
                        code="database_url_shape",
                        status="ok",
                        message="DATABASE__URL has scheme, host and database name.",
                        evidence=mask_database_url(database_url),
                    )
                )
            else:
                checks.append(
                    EnvConsistencyCheck(
                        code="database_url_shape",
                        status="warn",
                        message="DATABASE__URL is present but looks incomplete.",
                        evidence=mask_database_url(database_url),
                    )
                )
        except Exception as exc:
            checks.append(
                EnvConsistencyCheck(
                    code="database_url_shape",
                    status="fail",
                    message="DATABASE__URL could not be parsed.",
                    evidence=str(exc),
                )
            )
    else:
        checks.append(
            EnvConsistencyCheck(
                code="database_url_shape",
                status="fail",
                message="DATABASE__URL is missing.",
            )
        )

    api_base = frontend.get("VITE_API_BASE_URL", "")
    if api_base:
        api_port = parse_url_port(api_base)
        if str(api_port) == str(app_port):
            checks.append(
                EnvConsistencyCheck(
                    code="frontend_api_backend_port_match",
                    status="ok",
                    message="VITE_API_BASE_URL points to the configured backend port.",
                    evidence=f"VITE_API_BASE_URL={api_base}, APP__PORT={app_port}",
                )
            )
        else:
            checks.append(
                EnvConsistencyCheck(
                    code="frontend_api_backend_port_match",
                    status="warn",
                    message="VITE_API_BASE_URL does not point to the configured backend port.",
                    evidence=f"VITE_API_BASE_URL={api_base}, APP__PORT={app_port}",
                )
            )
        if api_base.rstrip("/").endswith("/api/v1"):
            checks.append(
                EnvConsistencyCheck(
                    code="frontend_api_base_path",
                    status="ok",
                    message="VITE_API_BASE_URL ends with /api/v1.",
                    evidence=api_base,
                )
            )
        else:
            checks.append(
                EnvConsistencyCheck(
                    code="frontend_api_base_path",
                    status="warn",
                    message="VITE_API_BASE_URL should normally end with /api/v1 for this project.",
                    evidence=api_base,
                )
            )
    else:
        checks.append(
            EnvConsistencyCheck(
                code="frontend_api_base_path",
                status="fail",
                message="VITE_API_BASE_URL is missing.",
            )
        )

    allowed_origins = split_csv(backend.get("HTTP__CORS_ALLOWED_ORIGINS", ""))
    expected_origins = {"http://localhost:5173", "http://127.0.0.1:5173"}
    present_expected = sorted(expected_origins.intersection(allowed_origins))
    if present_expected:
        checks.append(
            EnvConsistencyCheck(
                code="cors_frontend_origin",
                status="ok",
                message="CORS allowed origins include a default Vite dev origin.",
                evidence=", ".join(present_expected),
            )
        )
    else:
        checks.append(
            EnvConsistencyCheck(
                code="cors_frontend_origin",
                status="warn",
                message="CORS allowed origins do not include the default Vite dev origins.",
                evidence=backend.get("HTTP__CORS_ALLOWED_ORIGINS", "<missing>"),
            )
        )

    dev_header_auth = backend.get("AUTH__ENABLE_DEV_HEADER_AUTH", "").strip().lower()
    if dev_header_auth == "false":
        checks.append(
            EnvConsistencyCheck(
                code="dev_header_auth_baseline",
                status="ok",
                message="AUTH__ENABLE_DEV_HEADER_AUTH=false baseline is preserved.",
            )
        )
    elif dev_header_auth == "true":
        checks.append(
            EnvConsistencyCheck(
                code="dev_header_auth_baseline",
                status="warn",
                message="AUTH__ENABLE_DEV_HEADER_AUTH=true; keep this local-only and do not treat it as beta/self-host baseline.",
            )
        )
    else:
        checks.append(
            EnvConsistencyCheck(
                code="dev_header_auth_baseline",
                status="warn",
                message="AUTH__ENABLE_DEV_HEADER_AUTH is missing or not explicitly false.",
                evidence=f"AUTH__ENABLE_DEV_HEADER_AUTH={backend.get('AUTH__ENABLE_DEV_HEADER_AUTH', '<missing>')}",
            )
        )

    return checks


def build_env_plan(project_root: Path | None, invoked_from: Path, *, mode: str) -> EnvPlanResult:
    result = EnvPlanResult(
        generated_at=iso_now(),
        tool_version=TOOL_VERSION,
        project_root=str(project_root) if project_root else None,
        invoked_from=str(invoked_from),
        mode=mode,
    )
    if project_root is None:
        result.failures.append(
            {
                "code": "invalid_project_root",
                "message": "Could not find a project root containing backend/, frontend/, docs/ and docker-compose.dev.yml.",
            }
        )
        result.next_actions.append("Run this command from the project root, tools/, backend/ or frontend/ directory.")
        return result

    parsed: dict[str, tuple[dict[str, str], dict[str, str]]] = {}
    for name, contract in ENV_CONTRACTS.items():
        probe, example_values, target_values = build_env_file_probe(project_root, name, contract)
        result.files.append(probe)
        parsed[name] = (example_values, target_values)
        if not probe.example_exists:
            result.failures.append(
                {
                    "code": "missing_env_example",
                    "message": f"Required env example is missing: {probe.example_path}",
                }
            )
        if not probe.target_exists:
            result.actions.append(
                EnvAction(
                    code="create_env_file",
                    status="planned" if mode == "plan" else "pending",
                    message=f"Create {probe.target_path} from {probe.example_path}.",
                    path=probe.target_path,
                )
            )
        elif probe.missing_keys:
            result.actions.append(
                EnvAction(
                    code="env_missing_keys",
                    status="manual" if mode == "plan" else "skipped",
                    message=(
                        f"{probe.target_path} exists but misses {len(probe.missing_keys)} key(s): "
                        + ", ".join(probe.missing_keys)
                    ),
                    path=probe.target_path,
                )
            )
        else:
            result.actions.append(
                EnvAction(
                    code="env_file_ok",
                    status="ok",
                    message=f"{probe.target_path} exists and contains all example keys.",
                    path=probe.target_path,
                )
            )
        if probe.extra_keys:
            result.warnings.append(
                {
                    "code": "env_extra_keys",
                    "message": f"{probe.target_path} contains extra key(s): " + ", ".join(probe.extra_keys),
                }
            )
        for warning in probe.parse_warnings:
            result.warnings.append(
                {
                    "code": "env_parse_warning",
                    "message": f"{probe.target_path}: {warning}",
                }
            )

    backend_example, backend_target = parsed.get("backend", ({}, {}))
    frontend_example, frontend_target = parsed.get("frontend", ({}, {}))
    result.checks = check_env_consistency(backend_example, backend_target, frontend_example, frontend_target)
    for check in result.checks:
        if check.status == "fail":
            result.failures.append({"code": check.code, "message": check.message})
        elif check.status == "warn":
            result.warnings.append({"code": check.code, "message": check.message})

    if any(action.code == "create_env_file" for action in result.actions):
        result.next_actions.append("Run `python tools/devbootstrap.py prepare-env` to create missing local env files from examples.")
    if any(action.code == "env_missing_keys" for action in result.actions):
        result.next_actions.append(
            "Review missing env keys. Existing files are not overwritten; use `prepare-env --add-missing-keys` to append example defaults with a backup."
        )
    if not result.next_actions:
        result.next_actions.append("Env baseline looks ready for later start-db/start-backend/start-frontend phases.")
    return result


def backup_file(path: Path) -> Path:
    stamp = now_utc().strftime("%Y%m%d_%H%M%S")
    backup = path.with_name(path.name + f".bootstrap-backup.{stamp}")
    shutil.copy2(path, backup)
    return backup


def append_missing_env_keys(target_path: Path, example_values: dict[str, str], target_values: dict[str, str]) -> list[str]:
    missing = [key for key in example_values if key not in target_values]
    if not missing:
        return []
    lines = ["", f"# Added by devbootstrap on {iso_now()} from env example."]
    for key in missing:
        lines.append(f"{key}={example_values[key]}")
    with target_path.open("a", encoding="utf-8", newline="") as handle:
        handle.write("\n".join(lines) + "\n")
    return missing


def apply_prepare_env(project_root: Path, *, add_missing_keys: bool) -> list[EnvAction]:
    actions: list[EnvAction] = []
    for name, contract in ENV_CONTRACTS.items():
        example_path = project_root / contract["example"]
        target_path = project_root / contract["target"]
        if not example_path.exists():
            actions.append(
                EnvAction(
                    code="missing_env_example",
                    status="failed",
                    message=f"Cannot prepare {contract['target']} because {contract['example']} is missing.",
                    path=contract["target"],
                )
            )
            continue
        if not target_path.exists():
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(example_path, target_path)
            actions.append(
                EnvAction(
                    code="created_env_file",
                    status="done",
                    message=f"Created {contract['target']} from {contract['example']}.",
                    path=contract["target"],
                )
            )
            continue
        example_values, _ = parse_env_file(example_path)
        target_values, _ = parse_env_file(target_path)
        missing = [key for key in example_values if key not in target_values]
        if missing and add_missing_keys:
            backup = backup_file(target_path)
            appended = append_missing_env_keys(target_path, example_values, target_values)
            actions.append(
                EnvAction(
                    code="appended_missing_env_keys",
                    status="done",
                    message=(
                        f"Appended {len(appended)} missing key(s) to {contract['target']} after backup "
                        f"{rel(backup, project_root)}: " + ", ".join(appended)
                    ),
                    path=contract["target"],
                )
            )
        elif missing:
            actions.append(
                EnvAction(
                    code="missing_env_keys_not_modified",
                    status="skipped",
                    message=(
                        f"{contract['target']} exists and misses {len(missing)} key(s), but existing env files are not changed "
                        "without --add-missing-keys."
                    ),
                    path=contract["target"],
                )
            )
        else:
            actions.append(
                EnvAction(
                    code="env_file_unchanged",
                    status="ok",
                    message=f"{contract['target']} already exists and contains all example keys.",
                    path=contract["target"],
                )
            )
    return actions


def render_env_report(result: EnvPlanResult) -> str:
    title = "devbootstrap prepare-env report" if result.mode == "prepare-env" else "devbootstrap plan report"
    lines: list[str] = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"- Generated at: `{result.generated_at}`")
    lines.append(f"- Tool version: `{result.tool_version}`")
    lines.append(f"- Mode: `{result.mode}`")
    lines.append(f"- Invoked from: `{result.invoked_from}`")
    lines.append(f"- Project root: `{result.project_root or 'not found'}`")
    lines.append("")

    lines.append("## Env files")
    lines.append("")
    lines.append("| Name | Example | Target | Target exists | Missing keys | Extra keys |")
    lines.append("|---|---|---|---|---:|---:|")
    for item in result.files:
        lines.append(
            f"| {item.name} | `{item.example_path}` | `{item.target_path}` | {item.target_exists} | "
            f"{len(item.missing_keys)} | {len(item.extra_keys)} |"
        )
    if not result.files:
        lines.append("Env files were not checked because project root was not found.")
    lines.append("")

    for item in result.files:
        lines.append(f"### {item.name}: {item.description}")
        lines.append("")
        lines.append(f"- Example exists: `{item.example_exists}`")
        lines.append(f"- Target exists: `{item.target_exists}`")
        if item.missing_keys:
            lines.append("- Missing keys: `" + "`, `".join(item.missing_keys) + "`")
        else:
            lines.append("- Missing keys: none")
        if item.extra_keys:
            lines.append("- Extra keys: `" + "`, `".join(item.extra_keys) + "`")
        else:
            lines.append("- Extra keys: none")
        if item.parse_warnings:
            lines.append("- Parse warnings:")
            for warning in item.parse_warnings:
                lines.append(f"  - {warning}")
        lines.append("")
        lines.append("Masked effective values:")
        lines.append("")
        lines.append("| Key | Value |")
        lines.append("|---|---|")
        for key, value in item.masked_values.items():
            lines.append(f"| `{key}` | `{value}` |")
        if not item.masked_values:
            lines.append("| _none_ | _none_ |")
        lines.append("")

    lines.append("## Consistency checks")
    lines.append("")
    lines.append("| Status | Code | Message | Evidence |")
    lines.append("|---|---|---|---|")
    for check in result.checks:
        lines.append(f"| {check.status} | `{check.code}` | {check.message} | `{check.evidence or ''}` |")
    if not result.checks:
        lines.append("| skipped | `no_project_root` | Checks were skipped. | |")
    lines.append("")

    lines.append("## Actions")
    lines.append("")
    if result.actions:
        for action in result.actions:
            path = f" `{action.path}`" if action.path else ""
            lines.append(f"- `{action.status}` `{action.code}`{path} — {action.message}")
    else:
        lines.append("- No actions.")
    lines.append("")

    lines.append("## Findings")
    lines.append("")
    if not result.failures and not result.warnings:
        lines.append("- No blocking env findings.")
    for failure in result.failures:
        lines.append(f"- **FAIL** `{failure['code']}` — {failure['message']}")
    for warning in result.warnings:
        lines.append(f"- **WARN** `{warning['code']}` — {warning['message']}")
    lines.append("")

    lines.append("## Next safe actions")
    lines.append("")
    for action in result.next_actions:
        lines.append(f"- {action}")
    lines.append("")
    return "\n".join(lines)


def write_env_reports(project_root: Path, result: EnvPlanResult, command: str) -> Path:
    report_dir = create_report_dir(project_root, command)
    result.report_dir = rel(report_dir, project_root)
    write_json(report_dir / f"{command}.json", as_jsonable(result))
    (report_dir / "report.md").write_text(render_env_report(result), encoding="utf-8")
    return report_dir


def print_env_summary(result: EnvPlanResult) -> None:
    print_header(f"devbootstrap {result.mode}")
    print(f"Tool version: {result.tool_version}")
    print(f"Project root: {result.project_root or 'not found'}")
    if result.files:
        print("\nEnv files:")
        for item in result.files:
            print(
                f"  - {item.name}: target={'exists' if item.target_exists else 'missing'}, "
                f"missing_keys={len(item.missing_keys)}, extra_keys={len(item.extra_keys)}"
            )
    if result.checks:
        print("\nConsistency:")
        for check in result.checks:
            label = check.status.upper()
            print(f"  - {label} {check.code}: {check.message}")
    if result.actions:
        print("\nActions:")
        for action in result.actions:
            print(f"  - {action.status.upper()} {action.code}: {action.message}")
    if result.failures or result.warnings:
        print("\nFindings:")
        for failure in result.failures:
            print(f"  - FAIL {failure['code']}: {failure['message']}")
        for warning in result.warnings:
            print(f"  - WARN {warning['code']}: {warning['message']}")
    else:
        print("\nFindings: no blocking env findings")
    if result.next_actions:
        print("\nNext safe actions:")
        for action in result.next_actions:
            print(f"  - {action}")
    if result.report_dir:
        print(f"\nReport: {result.report_dir}/report.md")


def command_plan(args: argparse.Namespace) -> int:
    invoked_from = Path.cwd()
    project_root = find_project_root(invoked_from)
    result = build_env_plan(project_root, invoked_from, mode="plan")
    if project_root is not None and not args.no_write_report:
        write_env_reports(project_root, result, "plan")
    print_env_summary(result)
    if args.json:
        print("\nJSON:")
        print(json.dumps(as_jsonable(result), ensure_ascii=False, indent=2))
    return 1 if any(failure.get("code") == "invalid_project_root" for failure in result.failures) else 0


def command_prepare_env(args: argparse.Namespace) -> int:
    invoked_from = Path.cwd()
    project_root = find_project_root(invoked_from)
    if project_root is None:
        result = build_env_plan(project_root, invoked_from, mode="prepare-env")
        print_env_summary(result)
        return 1
    applied_actions = apply_prepare_env(project_root, add_missing_keys=args.add_missing_keys)
    result = build_env_plan(project_root, invoked_from, mode="prepare-env")
    result.actions = applied_actions + result.actions
    if not any(action.status == "failed" for action in applied_actions):
        result.next_actions.insert(0, "Run `python tools/devbootstrap.py plan` to review the effective masked env baseline.")
    if not args.no_write_report:
        write_env_reports(project_root, result, "prepare-env")
    print_env_summary(result)
    if args.json:
        print("\nJSON:")
        print(json.dumps(as_jsonable(result), ensure_ascii=False, indent=2))
    return 1 if any(action.status == "failed" for action in applied_actions) else 0


def run_process_probe(
    name: str,
    command: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 10,
    env_extra: dict[str, str] | None = None,
) -> ProcessProbe:
    executable = command[0]
    if shutil.which(executable) is None and executable != sys.executable:
        return ProcessProbe(name=name, command=command, available=False, error="not found on PATH")
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
            env=env,
        )
    except FileNotFoundError:
        return ProcessProbe(name=name, command=command, available=False, error="command not found")
    except subprocess.TimeoutExpired as exc:
        return ProcessProbe(
            name=name,
            command=command,
            available=True,
            returncode=None,
            stdout=safe_decode(exc.stdout).strip(),
            stderr=safe_decode(exc.stderr).strip(),
            error="timeout",
        )
    except OSError as exc:
        return ProcessProbe(name=name, command=command, available=False, error=str(exc))
    return ProcessProbe(
        name=name,
        command=command,
        available=True,
        returncode=completed.returncode,
        stdout=safe_decode(completed.stdout).strip(),
        stderr=safe_decode(completed.stderr).strip(),
    )


def process_probe_ok(probe: ProcessProbe | None) -> bool:
    return bool(probe and probe.available and probe.returncode == 0)


def first_output_line(probe: ProcessProbe | None) -> str:
    if probe is None:
        return ""
    text = probe.stdout or probe.stderr or probe.error or ""
    return text.splitlines()[0] if text else ""


def command_as_text(command: list[str] | None) -> str:
    return " ".join(command or [])


def effective_env_values_for(project_root: Path, name: str) -> dict[str, str]:
    contract = ENV_CONTRACTS[name]
    example_values, _ = parse_env_file(project_root / contract["example"])
    target_values, _ = parse_env_file(project_root / contract["target"])
    return env_effective_values(example_values, target_values)


def default_port_for_database_scheme(scheme: str | None) -> int | None:
    if scheme in {"postgres", "postgresql"}:
        return 5432
    return None


def parse_database_url_probe(value: str | None) -> DatabaseUrlProbe:
    if not value:
        return DatabaseUrlProbe(raw_present=False, warnings=["DATABASE__URL is missing or empty"])
    warnings: list[str] = []
    try:
        parsed = urllib.parse.urlsplit(value)
    except Exception as exc:
        return DatabaseUrlProbe(raw_present=True, masked_url="***", warnings=[f"could not parse DATABASE__URL: {exc}"])
    scheme = parsed.scheme or None
    host = parsed.hostname or None
    port = parsed.port or default_port_for_database_scheme(scheme)
    database = parsed.path.lstrip("/") or None
    username = urllib.parse.unquote(parsed.username or "") or None
    if scheme not in {"postgres", "postgresql"}:
        warnings.append(f"unexpected database URL scheme: {scheme or '<missing>'}")
    if not host:
        warnings.append("database host is missing")
    if not port:
        warnings.append("database port is missing")
    if not database:
        warnings.append("database name is missing")
    if not username:
        warnings.append("database username is missing")
    return DatabaseUrlProbe(
        raw_present=True,
        masked_url=mask_database_url(value),
        scheme=scheme,
        host=host,
        port=port,
        database=database,
        username=username,
        has_password=parsed.password is not None,
        warnings=warnings,
    )


def psql_env_from_database_url(value: str) -> dict[str, str]:
    parsed = urllib.parse.urlsplit(value)
    env: dict[str, str] = {}
    if parsed.hostname:
        env["PGHOST"] = parsed.hostname
    if parsed.port:
        env["PGPORT"] = str(parsed.port)
    elif default_port_for_database_scheme(parsed.scheme):
        env["PGPORT"] = str(default_port_for_database_scheme(parsed.scheme))
    if parsed.username:
        env["PGUSER"] = urllib.parse.unquote(parsed.username)
    if parsed.password is not None:
        env["PGPASSWORD"] = urllib.parse.unquote(parsed.password)
    database = parsed.path.lstrip("/")
    if database:
        env["PGDATABASE"] = database
    return env


def sanitize_postgres_output(text: str, db_url: str | None) -> str:
    if not text:
        return ""
    cleaned = text.strip()
    if db_url:
        cleaned = cleaned.replace(db_url, mask_database_url(db_url))
        try:
            parsed = urllib.parse.urlsplit(db_url)
            if parsed.password:
                cleaned = cleaned.replace(urllib.parse.unquote(parsed.password), "***")
        except Exception:
            pass
    return "\n".join(cleaned.splitlines()[:6])


def classify_psql_failure(probe: ProcessProbe, db_url: str | None) -> str:
    text = sanitize_postgres_output((probe.stderr or probe.stdout or probe.error or ""), db_url).lower()
    if "password authentication failed" in text or "authentication failed" in text:
        return "auth_failed"
    if "role" in text and "does not exist" in text:
        return "auth_failed"
    if "database" in text and "does not exist" in text:
        return "db_missing"
    if "connection refused" in text or "could not connect" in text:
        return "port_closed"
    if "timeout" in text:
        return "connect_timeout"
    return "psql_failed"


def probe_psql_database(db_url: str | None, project_root: Path) -> ProcessProbe:
    if not db_url:
        return ProcessProbe(name="psql", command=["psql"], available=False, error="DATABASE__URL is missing")
    env_extra = psql_env_from_database_url(db_url)
    command = ["psql", "-X", "-v", "ON_ERROR_STOP=1", "-Atc", "select current_database() || '|' || current_user"]
    probe = run_process_probe("psql", command, cwd=project_root, timeout=8, env_extra=env_extra)
    probe.stdout = sanitize_postgres_output(probe.stdout, db_url)
    probe.stderr = sanitize_postgres_output(probe.stderr, db_url)
    return probe


def probe_pg_isready(db_url: str | None, project_root: Path) -> ProcessProbe:
    if not db_url:
        return ProcessProbe(name="pg_isready", command=["pg_isready"], available=False, error="DATABASE__URL is missing")
    env_extra = psql_env_from_database_url(db_url)
    command = ["pg_isready"]
    if "PGHOST" in env_extra:
        command.extend(["-h", env_extra["PGHOST"]])
    if "PGPORT" in env_extra:
        command.extend(["-p", env_extra["PGPORT"]])
    if "PGUSER" in env_extra:
        command.extend(["-U", env_extra["PGUSER"]])
    if "PGDATABASE" in env_extra:
        command.extend(["-d", env_extra["PGDATABASE"]])
    probe = run_process_probe("pg_isready", command, cwd=project_root, timeout=8, env_extra=env_extra)
    probe.stdout = sanitize_postgres_output(probe.stdout, db_url)
    probe.stderr = sanitize_postgres_output(probe.stderr, db_url)
    return probe


def detect_compose_command(project_root: Path) -> tuple[list[str], ProcessProbe]:
    docker_compose = run_process_probe("docker_compose", ["docker", "compose", "version"], cwd=project_root, timeout=8)
    if process_probe_ok(docker_compose):
        return ["docker", "compose"], docker_compose
    legacy = run_process_probe("docker_compose_legacy", ["docker-compose", "version"], cwd=project_root, timeout=8)
    if process_probe_ok(legacy):
        return ["docker-compose"], legacy
    evidence_parts = []
    for probe in (docker_compose, legacy):
        evidence = first_output_line(probe)
        if evidence:
            evidence_parts.append(f"{probe.name}: {evidence}")
    return [], ProcessProbe(
        name="compose",
        command=["docker", "compose", "version"],
        available=False,
        error="; ".join(evidence_parts) or "Docker Compose is not available",
    )


def compose_base_command(compose_command: list[str], project_root: Path) -> list[str]:
    return [*compose_command, "-f", str(project_root / COMPOSE_FILE)]


def probe_compose_status(project_root: Path, compose_command: list[str]) -> ProcessProbe:
    if not compose_command:
        return ProcessProbe(name="compose_status", command=[], available=False, error="compose command is unavailable")
    command = [*compose_base_command(compose_command, project_root), "ps", POSTGRES_SERVICE_NAME]
    return run_process_probe("compose_status", command, cwd=project_root, timeout=12)


def probe_postgres_container_health(project_root: Path) -> ProcessProbe:
    command = ["docker", "inspect", "--format", "{{json .State.Health}}", POSTGRES_CONTAINER_NAME]
    return run_process_probe("docker_health", command, cwd=project_root, timeout=8)


def classify_postgres_state(
    db_url_probe: DatabaseUrlProbe | None,
    port_probe: PortProbe | None,
    psql_probe: ProcessProbe | None,
) -> str:
    if db_url_probe is None or not db_url_probe.raw_present or db_url_probe.warnings:
        return "database_url_invalid"
    if psql_probe and process_probe_ok(psql_probe):
        return "ready"
    if port_probe and not port_probe.open:
        return "port_closed"
    if psql_probe and psql_probe.available and psql_probe.returncode not in (0, None):
        return classify_psql_failure(psql_probe, db_url_probe.masked_url)
    if port_probe and port_probe.open and (psql_probe is None or not psql_probe.available):
        return "port_open_unverified"
    return "unknown"


def build_postgres_checks(result: PostgresResult, db_url: str | None) -> None:
    if result.database_url is None or not result.database_url.raw_present:
        result.checks.append(PostgresCheck("database_url", "fail", "DATABASE__URL is missing."))
    elif result.database_url.warnings:
        result.checks.append(
            PostgresCheck(
                "database_url",
                "warn",
                "DATABASE__URL was parsed but has suspicious fields.",
                "; ".join(result.database_url.warnings),
            )
        )
    else:
        result.checks.append(
            PostgresCheck(
                "database_url",
                "ok",
                "DATABASE__URL points to a PostgreSQL target.",
                f"host={result.database_url.host}, port={result.database_url.port}, db={result.database_url.database}, user={result.database_url.username}, url={result.database_url.masked_url}",
            )
        )

    if result.port:
        result.checks.append(
            PostgresCheck(
                "postgres_tcp_port",
                "ok" if result.port.open else "warn",
                f"TCP port {result.port.host}:{result.port.port} is {'open' if result.port.open else 'closed/unreachable'}.",
                "tcp connect succeeded" if result.port.open else (result.port.error or ""),
            )
        )

    if result.psql:
        if process_probe_ok(result.psql):
            result.checks.append(PostgresCheck("psql_probe", "ok", "psql can connect and run a tiny query.", result.psql.stdout))
        elif not result.psql.available:
            result.checks.append(PostgresCheck("psql_probe", "warn", "psql is not available; auth/db-name validation is limited.", result.psql.error))
        else:
            result.checks.append(
                PostgresCheck(
                    "psql_probe",
                    "fail",
                    "psql could not connect to the configured database.",
                    result.psql.stderr or result.psql.stdout or result.psql.error,
                )
            )

    if result.pg_isready:
        if process_probe_ok(result.pg_isready):
            result.checks.append(PostgresCheck("pg_isready", "ok", "pg_isready reports PostgreSQL as accepting connections.", result.pg_isready.stdout))
        elif not result.pg_isready.available:
            result.checks.append(PostgresCheck("pg_isready", "warn", "pg_isready is not available; readiness fallback skipped.", result.pg_isready.error))
        else:
            result.checks.append(PostgresCheck("pg_isready", "warn", "pg_isready did not report a ready server.", result.pg_isready.stderr or result.pg_isready.stdout))

    if result.compose_status:
        status = "ok" if process_probe_ok(result.compose_status) else "warn"
        result.checks.append(PostgresCheck("compose_status", status, "docker compose service status probe completed.", result.compose_status.stdout or result.compose_status.stderr or result.compose_status.error))
    if result.docker_health:
        status = "ok" if process_probe_ok(result.docker_health) else "warn"
        result.checks.append(PostgresCheck("docker_health", status, "Docker container health probe completed.", result.docker_health.stdout or result.docker_health.stderr or result.docker_health.error))


def build_postgres_result(project_root: Path | None, invoked_from: Path, *, mode: str, dry_run: bool = False) -> PostgresResult:
    result = PostgresResult(
        generated_at=iso_now(),
        tool_version=TOOL_VERSION,
        project_root=str(project_root) if project_root else None,
        invoked_from=str(invoked_from),
        mode=mode,
        dry_run=dry_run,
    )
    if project_root is None:
        result.classification = "invalid_project_root"
        result.failures.append({"code": "invalid_project_root", "message": "Could not find project root."})
        result.next_actions.append("Run this command from the project root, tools/, backend/ or frontend/ directory.")
        return result

    backend_env = effective_env_values_for(project_root, "backend")
    db_url = backend_env.get("DATABASE__URL")
    result.database_url = parse_database_url_probe(db_url)
    host = result.database_url.host or "127.0.0.1"
    port = result.database_url.port or DEFAULT_PORTS["postgres"]
    result.port = probe_port("postgres", port, host=host)
    result.psql = probe_psql_database(db_url, project_root)
    result.pg_isready = probe_pg_isready(db_url, project_root)
    result.docker = run_process_probe("docker", ["docker", "--version"], cwd=project_root, timeout=8)
    result.docker_daemon = run_process_probe("docker_daemon", ["docker", "info", "--format", "{{.ServerVersion}}"], cwd=project_root, timeout=12)
    result.compose_command, result.compose = detect_compose_command(project_root)
    if result.compose_command:
        result.compose_status = probe_compose_status(project_root, result.compose_command)
    if process_probe_ok(result.docker):
        result.docker_health = probe_postgres_container_health(project_root)

    result.classification = classify_postgres_state(result.database_url, result.port, result.psql)
    build_postgres_checks(result, db_url)

    if result.classification == "ready":
        result.next_actions.append("PostgreSQL is reachable. Continue with `python tools/devbootstrap.py check-backend` in Phase 4.")
    elif result.classification == "port_closed":
        result.next_actions.append("PostgreSQL port is closed. Run `python tools/devbootstrap.py start-db` to try docker compose postgres.")
    elif result.classification == "port_open_unverified":
        result.warnings.append({"code": "postgres_unverified", "message": "Port is open, but psql is unavailable, so auth/db-name were not verified."})
        result.next_actions.append("Install psql or verify DATABASE__URL manually before backend startup.")
    elif result.classification in {"auth_failed", "db_missing"}:
        result.failures.append({"code": result.classification, "message": "Configured PostgreSQL is reachable but does not accept the configured credentials/database."})
        result.next_actions.append("Fix backend/.env DATABASE__URL or prepare the expected database/user before starting backend.")
    elif result.classification == "database_url_invalid":
        result.failures.append({"code": "database_url_invalid", "message": "DATABASE__URL is missing or invalid."})
        result.next_actions.append("Run `python tools/devbootstrap.py prepare-env` and review backend/.env.")
    else:
        result.warnings.append({"code": "postgres_state_unknown", "message": "PostgreSQL state could not be classified confidently."})
        result.next_actions.append("Review the report evidence before starting backend.")
    return result


def refresh_postgres_after_start(result: PostgresResult, project_root: Path, db_url: str | None) -> None:
    if not result.database_url:
        return
    host = result.database_url.host or "127.0.0.1"
    port = result.database_url.port or DEFAULT_PORTS["postgres"]
    result.port = probe_port("postgres", port, host=host)
    result.psql = probe_psql_database(db_url, project_root)
    result.pg_isready = probe_pg_isready(db_url, project_root)
    if result.compose_command:
        result.compose_status = probe_compose_status(project_root, result.compose_command)
    if process_probe_ok(result.docker):
        result.docker_health = probe_postgres_container_health(project_root)
    result.classification = classify_postgres_state(result.database_url, result.port, result.psql)
    result.checks = []
    build_postgres_checks(result, db_url)


def apply_start_db(result: PostgresResult, project_root: Path, *, timeout_seconds: int) -> None:
    backend_env = effective_env_values_for(project_root, "backend")
    db_url = backend_env.get("DATABASE__URL")

    if result.classification == "ready":
        result.actions.append(PostgresAction("start_db_noop", "ok", "Configured PostgreSQL is already reachable; compose start skipped."))
        return
    if result.classification not in {"port_closed"}:
        result.actions.append(
            PostgresAction(
                "start_db_skipped",
                "skipped",
                "Port is not closed, so devbootstrap will not start compose to avoid interfering with an existing/foreign PostgreSQL.",
            )
        )
        return
    if result.dry_run:
        compose_cmd = result.compose_command or ["docker", "compose"]
        command = [*compose_base_command(compose_cmd, project_root), "up", "-d", POSTGRES_SERVICE_NAME]
        result.actions.append(PostgresAction("compose_up", "planned", "Would start postgres through docker compose because the configured port is closed.", command_as_text(command)))
        if not process_probe_ok(result.docker):
            result.warnings.append({"code": "docker_unavailable", "message": "Docker CLI is unavailable right now; real start-db would fail until Docker is installed."})
        elif not process_probe_ok(result.docker_daemon):
            result.warnings.append({"code": "docker_daemon_unavailable", "message": "Docker daemon is unavailable right now; real start-db would fail until Docker is running."})
        if not result.compose_command:
            result.warnings.append({"code": "compose_unavailable", "message": "Docker Compose is unavailable right now; real start-db would fail until Compose is installed."})
        return
    if not process_probe_ok(result.docker):
        result.failures.append({"code": "docker_unavailable", "message": "Docker CLI is unavailable; cannot start compose postgres."})
        result.actions.append(PostgresAction("compose_up", "failed", "Docker CLI is unavailable."))
        return
    if not process_probe_ok(result.docker_daemon):
        evidence = first_output_line(result.docker_daemon)
        result.failures.append({"code": "docker_daemon_unavailable", "message": "Docker daemon is unavailable; cannot start compose postgres."})
        result.actions.append(PostgresAction("compose_up", "failed", "Docker daemon is unavailable.", evidence=evidence))
        return
    if not result.compose_command:
        result.failures.append({"code": "compose_unavailable", "message": "Docker Compose is unavailable; cannot start compose postgres."})
        result.actions.append(PostgresAction("compose_up", "failed", "Docker Compose is unavailable.", evidence=first_output_line(result.compose)))
        return

    command = [*compose_base_command(result.compose_command, project_root), "up", "-d", POSTGRES_SERVICE_NAME]
    started = run_process_probe("compose_up", command, cwd=project_root, timeout=max(30, timeout_seconds))
    if process_probe_ok(started):
        result.actions.append(PostgresAction("compose_up", "done", "Started postgres through docker compose.", command_as_text(command), started.stdout or started.stderr))
    else:
        result.failures.append({"code": "compose_up_failed", "message": "docker compose up failed."})
        result.actions.append(PostgresAction("compose_up", "failed", "docker compose up failed.", command_as_text(command), started.stderr or started.stdout or started.error))
        return

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        refresh_postgres_after_start(result, project_root, db_url)
        if result.classification == "ready" or (result.port and result.port.open and not result.psql.available):
            break
        time.sleep(2)
    refresh_postgres_after_start(result, project_root, db_url)
    if result.classification == "ready":
        result.actions.append(PostgresAction("wait_postgres", "done", "PostgreSQL became queryable before timeout."))
    elif result.port and result.port.open and result.psql and not result.psql.available:
        result.actions.append(PostgresAction("wait_postgres", "partial", "PostgreSQL TCP port opened, but psql is unavailable for auth/db verification."))
    else:
        result.failures.append({"code": "postgres_wait_timeout", "message": "PostgreSQL did not become ready before timeout."})
        result.actions.append(PostgresAction("wait_postgres", "failed", f"Timed out after {timeout_seconds} seconds.", evidence=result.classification))


def render_postgres_report(result: PostgresResult) -> str:
    lines: list[str] = []
    title = "devbootstrap start-db report" if result.mode == "start-db" else "devbootstrap postgres diagnose report"
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"- Generated at: `{result.generated_at}`")
    lines.append(f"- Tool version: `{result.tool_version}`")
    lines.append(f"- Mode: `{result.mode}`")
    lines.append(f"- Dry run: `{result.dry_run}`")
    lines.append(f"- Invoked from: `{result.invoked_from}`")
    lines.append(f"- Project root: `{result.project_root or 'not found'}`")
    lines.append(f"- Classification: `{result.classification}`")
    lines.append("")

    lines.append("## Database target")
    lines.append("")
    if result.database_url:
        lines.append(f"- URL: `{result.database_url.masked_url or '<missing>'}`")
        lines.append(f"- Host: `{result.database_url.host or '<missing>'}`")
        lines.append(f"- Port: `{result.database_url.port or '<missing>'}`")
        lines.append(f"- Database: `{result.database_url.database or '<missing>'}`")
        lines.append(f"- User: `{result.database_url.username or '<missing>'}`")
        lines.append(f"- Password present: `{result.database_url.has_password}`")
        if result.database_url.warnings:
            lines.append("- Warnings:")
            for warning in result.database_url.warnings:
                lines.append(f"  - {warning}")
    else:
        lines.append("Database URL was not parsed.")
    lines.append("")

    lines.append("## Probes")
    lines.append("")
    lines.append("| Probe | Status | Evidence |")
    lines.append("|---|---|---|")
    if result.port:
        lines.append(f"| TCP `{result.port.host}:{result.port.port}` | {'open' if result.port.open else 'closed'} | `{result.port.error or 'tcp connect succeeded'}` |")
    for name, probe in [
        ("psql", result.psql),
        ("pg_isready", result.pg_isready),
        ("docker", result.docker),
        ("docker daemon", result.docker_daemon),
        ("compose", result.compose),
        ("compose status", result.compose_status),
        ("docker health", result.docker_health),
    ]:
        if probe is None:
            continue
        if not probe.available:
            status = "unavailable"
        elif probe.returncode == 0:
            status = "ok"
        elif probe.returncode is None:
            status = "unknown"
        else:
            status = f"exit {probe.returncode}"
        evidence = probe.stdout or probe.stderr or probe.error or ""
        lines.append(f"| {name} | {status} | `{evidence}` |")
    lines.append("")

    lines.append("## Checks")
    lines.append("")
    lines.append("| Status | Code | Message | Evidence |")
    lines.append("|---|---|---|---|")
    for check in result.checks:
        lines.append(f"| {check.status} | `{check.code}` | {check.message} | `{check.evidence or ''}` |")
    if not result.checks:
        lines.append("| skipped | `no_checks` | Checks were skipped. | |")
    lines.append("")

    lines.append("## Actions")
    lines.append("")
    if result.actions:
        for action in result.actions:
            command = f" command=`{action.command}`" if action.command else ""
            evidence = f" Evidence: `{action.evidence}`" if action.evidence else ""
            lines.append(f"- `{action.status}` `{action.code}` — {action.message}{command}.{evidence}")
    else:
        lines.append("- No actions.")
    lines.append("")

    lines.append("## Findings")
    lines.append("")
    if not result.failures and not result.warnings:
        lines.append("- No blocking PostgreSQL findings.")
    for failure in result.failures:
        lines.append(f"- **FAIL** `{failure['code']}` — {failure['message']}")
    for warning in result.warnings:
        lines.append(f"- **WARN** `{warning['code']}` — {warning['message']}")
    lines.append("")

    lines.append("## Next safe actions")
    lines.append("")
    for action in result.next_actions:
        lines.append(f"- {action}")
    lines.append("")
    return "\n".join(lines)


def write_postgres_reports(project_root: Path, result: PostgresResult, command: str) -> Path:
    report_dir = create_report_dir(project_root, command)
    result.report_dir = rel(report_dir, project_root)
    write_json(report_dir / f"{command}.json", as_jsonable(result))
    (report_dir / "report.md").write_text(render_postgres_report(result), encoding="utf-8")
    return report_dir


def print_postgres_summary(result: PostgresResult) -> None:
    print_header(f"devbootstrap {result.mode}")
    print(f"Tool version: {result.tool_version}")
    print(f"Project root: {result.project_root or 'not found'}")
    print(f"Classification: {result.classification}")
    if result.database_url:
        print(
            "Database: "
            f"host={result.database_url.host or '<missing>'} "
            f"port={result.database_url.port or '<missing>'} "
            f"db={result.database_url.database or '<missing>'} "
            f"user={result.database_url.username or '<missing>'} "
            f"url={result.database_url.masked_url or '<missing>'}"
        )
    if result.port:
        print(f"TCP: {result.port.host}:{result.port.port} {'open' if result.port.open else 'closed'}")
    print("\nChecks:")
    for check in result.checks:
        label = check.status.upper()
        evidence = f" — {check.evidence}" if check.evidence else ""
        print(f"  - {label} {check.code}: {check.message}{evidence}")
    if result.actions:
        print("\nActions:")
        for action in result.actions:
            print(f"  - {action.status.upper()} {action.code}: {action.message}")
    if result.failures or result.warnings:
        print("\nFindings:")
        for failure in result.failures:
            print(f"  - FAIL {failure['code']}: {failure['message']}")
        for warning in result.warnings:
            print(f"  - WARN {warning['code']}: {warning['message']}")
    else:
        print("\nFindings: no blocking PostgreSQL findings")
    if result.next_actions:
        print("\nNext safe actions:")
        for action in result.next_actions:
            print(f"  - {action}")
    if result.report_dir:
        print(f"\nReport: {result.report_dir}/report.md")


def command_diagnose_postgres(args: argparse.Namespace) -> int:
    invoked_from = Path.cwd()
    project_root = find_project_root(invoked_from)
    result = build_postgres_result(project_root, invoked_from, mode="diagnose-postgres")
    if project_root is not None and not args.no_write_report:
        write_postgres_reports(project_root, result, "diagnose-postgres")
    print_postgres_summary(result)
    if args.json:
        print("\nJSON:")
        print(json.dumps(as_jsonable(result), ensure_ascii=False, indent=2))
    return 1 if result.classification == "invalid_project_root" else 0


def command_start_db(args: argparse.Namespace) -> int:
    invoked_from = Path.cwd()
    project_root = find_project_root(invoked_from)
    result = build_postgres_result(project_root, invoked_from, mode="start-db", dry_run=args.dry_run)
    if project_root is not None:
        apply_start_db(result, project_root, timeout_seconds=args.timeout_seconds)
    if project_root is not None and not args.no_write_report:
        write_postgres_reports(project_root, result, "start-db")
    print_postgres_summary(result)
    if args.json:
        print("\nJSON:")
        print(json.dumps(as_jsonable(result), ensure_ascii=False, indent=2))
    return 1 if result.failures and not args.dry_run else 0

def print_diagnose_summary(result: DiagnoseResult) -> None:
    print_header("devbootstrap diagnose")
    print(f"Tool version: {result.tool_version}")
    print(f"Project root: {result.project_root or 'not found'}")
    print(f"Platform: {result.platform.get('system')} {result.platform.get('release')} ({result.platform.get('machine')})")

    missing = [item.path for item in result.paths if item.required and not item.exists]
    if missing:
        print(f"Required files: MISSING ({len(missing)})")
        for path in missing:
            print(f"  - {path}")
    elif result.project_root:
        print("Required files: OK")

    print("\nTools:")
    for tool in result.tools:
        status = "OK" if tool.available else "MISSING"
        details = tool.version if tool.available else tool.error
        print(f"  - {tool.name}: {status}" + (f" — {details}" if details else ""))

    if result.ports:
        print("\nPorts:")
        for port in result.ports:
            status = "open" if port.open else "closed"
            print(f"  - {port.name} {port.host}:{port.port}: {status}")

    if result.http:
        print("\nHTTP:")
        for probe in result.http:
            if probe.reachable:
                print(f"  - {probe.name}: HTTP {probe.status} ({probe.duration_ms} ms)")
            else:
                print(f"  - {probe.name}: unreachable")

    if result.failures or result.warnings:
        print("\nFindings:")
        for failure in result.failures:
            print(f"  - FAIL {failure['code']}: {failure['message']}")
        for warning in result.warnings:
            print(f"  - WARN {warning['code']}: {warning['message']}")
    else:
        print("\nFindings: no blocking findings from phase 1 diagnostics")

    if result.report_dir:
        print(f"\nReport: {result.report_dir}/report.md")


def command_diagnose(args: argparse.Namespace) -> int:
    if getattr(args, "section", "all") == "postgres":
        return command_diagnose_postgres(args)
    invoked_from = Path.cwd()
    project_root = find_project_root(invoked_from)
    result = build_diagnose(project_root, invoked_from)
    if project_root is not None and not args.no_write_report:
        write_reports(project_root, result, "diagnose")
    print_diagnose_summary(result)
    if args.json:
        print("\nJSON:")
        print(json.dumps(as_jsonable(result), ensure_ascii=False, indent=2))
    return 1 if any(failure.get("code") == "invalid_project_root" for failure in result.failures) else 0


def command_status(args: argparse.Namespace) -> int:
    invoked_from = Path.cwd()
    project_root = find_project_root(invoked_from)
    print_header("devbootstrap status")
    if project_root is None:
        print("Project root: not found")
        print("State: unavailable")
        return 1
    state = summarize_state(project_root)
    print(f"Project root: {project_root}")
    print(f"State file: {state.get('statePath')}")
    print(f"State exists: {state.get('exists')}")
    print(f"State valid: {state.get('valid')}")
    if state.get("error"):
        print(f"State error: {state.get('error')}")
    print(f"Active run: {state.get('activeRunId')}")
    processes = state.get("processes", {})
    if processes:
        print("\nRegistered processes:")
        for name, process in processes.items():
            print(
                f"  - {name}: pid={process.get('pid')} alive={process.get('alive')} "
                f"command={process.get('command')} cwd={process.get('cwd')}"
            )
    else:
        print("Registered processes: none")
    reports = state.get("lastReports") or []
    if reports:
        print("\nLast reports:")
        for report in reports[-5:]:
            print(f"  - {report}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="devbootstrap",
        description="Local development environment diagnostics for p2p_planner.",
    )
    parser.add_argument("--version", action="version", version=f"devbootstrap {TOOL_VERSION}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    diagnose = subparsers.add_parser("diagnose", help="Run read-only environment diagnostics.")
    diagnose.add_argument("--section", choices=["all", "postgres"], default="all", help="Limit diagnostics to a specific subsystem.")
    diagnose.add_argument("--no-write-report", action="store_true", help="Do not create .dev-bootstrap report files.")
    diagnose.add_argument("--json", action="store_true", help="Also print machine-readable JSON to stdout.")
    diagnose.set_defaults(func=command_diagnose)

    start_db = subparsers.add_parser("start-db", help="Diagnose PostgreSQL and start docker compose postgres when the configured port is closed.")
    start_db.add_argument("--dry-run", action="store_true", help="Show the planned compose action without starting containers.")
    start_db.add_argument("--timeout-seconds", type=int, default=60, help="How long to wait for PostgreSQL readiness after compose start.")
    start_db.add_argument("--no-write-report", action="store_true", help="Do not create .dev-bootstrap report files.")
    start_db.add_argument("--json", action="store_true", help="Also print machine-readable JSON to stdout.")
    start_db.set_defaults(func=command_start_db)

    plan = subparsers.add_parser("plan", help="Build a safe env/bootstrap plan without changing files.")
    plan.add_argument("--no-write-report", action="store_true", help="Do not create .dev-bootstrap report files.")
    plan.add_argument("--json", action="store_true", help="Also print machine-readable JSON to stdout.")
    plan.set_defaults(func=command_plan)

    prepare_env = subparsers.add_parser("prepare-env", help="Create missing env files from examples without overwriting existing files.")
    prepare_env.add_argument("--add-missing-keys", action="store_true", help="Append missing keys from examples to existing env files after creating a timestamped backup.")
    prepare_env.add_argument("--no-write-report", action="store_true", help="Do not create .dev-bootstrap report files.")
    prepare_env.add_argument("--json", action="store_true", help="Also print machine-readable JSON to stdout.")
    prepare_env.set_defaults(func=command_prepare_env)

    status = subparsers.add_parser("status", help="Show devbootstrap runtime state if it exists.")
    status.set_defaults(func=command_status)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
