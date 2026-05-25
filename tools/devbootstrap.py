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
    python tools/devbootstrap.py check-backend
    python tools/devbootstrap.py start-backend
    python tools/devbootstrap.py prepare-frontend
    python tools/devbootstrap.py start-frontend
    python tools/devbootstrap.py up
    python tools/devbootstrap.py smoke
    python tools/devbootstrap.py status
    python tools/devbootstrap.py stop
    python tools/devbootstrap.py self-check

The tool intentionally uses only Python standard library modules.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import zipfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TOOL_VERSION = "2.0.0-draft"
STATE_VERSION = 1
REPORT_SCHEMA_VERSION = 1
TIMEOUT_POLICY = {
    "probe_command": 5,
    "port_probe": 0.4,
    "http_probe": 1.5,
    "postgres_ready": 60,
    "cargo_metadata": 60,
    "cargo_check": 240,
    "backend_ready": 180,
    "npm_install": 300,
    "frontend_ready": 120,
    "smoke_step": 600,
    "up_step": 120,
    "stop_grace": 10,
    "release_gate": 600,
}
BOOTSTRAP_DIR_NAME = ".dev-bootstrap"
FRONTEND_PREPARE_DEP_MODES = ("never", "missing", "stale", "missing-or-stale", "always")
DEFAULT_FRONTEND_PREPARE_DEP_MODE = "stale"
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


def run_probe_command(command: list[str], *, timeout: int = TIMEOUT_POLICY["probe_command"]) -> tuple[bool, str | None]:
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


def probe_port(name: str, port: int, host: str = "127.0.0.1", timeout: float = TIMEOUT_POLICY["port_probe"]) -> PortProbe:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return PortProbe(name=name, host=host, port=port, open=True)
    except OSError as exc:
        return PortProbe(name=name, host=host, port=port, open=False, error=str(exc))


def probe_http(name: str, url: str, timeout: float = TIMEOUT_POLICY["http_probe"]) -> HttpProbe:
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


def popen_process_group_kwargs() -> dict[str, Any]:
    """Return cross-platform kwargs that make later owned-process stop safer.

    POSIX starts a new session so `stop` can terminate the process group.
    Windows starts a new process group when the flag is available; `stop` then
    still uses PID-based termination because Python stdlib does not expose a
    complete process-tree API there.
    """
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        return {"creationflags": creationflags} if creationflags else {}
    return {"start_new_session": True}


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


def result_status_from_payload(payload: dict[str, Any]) -> str:
    failures = payload.get("failures")
    warnings = payload.get("warnings")
    classification = str(payload.get("classification") or "")
    if isinstance(failures, list) and failures:
        return "failed"
    if classification in {"failed", "partial", "invalid_project_root", "state_invalid"}:
        return "failed"
    if isinstance(warnings, list) and warnings:
        return "warning"
    if classification in {"planned", "dry_run"}:
        return classification
    return "ok"


def write_report_json(path: Path, result: Any, *, command: str) -> None:
    payload = as_jsonable(result)
    if not isinstance(payload, dict):
        payload = {"value": payload}
    payload.setdefault("schemaVersion", REPORT_SCHEMA_VERSION)
    payload.setdefault("toolVersion", payload.get("tool_version", TOOL_VERSION))
    payload.setdefault("generatedAt", payload.get("generated_at"))
    payload.setdefault("command", command)
    payload.setdefault("status", result_status_from_payload(payload))
    write_json(path, payload)


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
    write_report_json(report_dir / "diagnose.json", result, command="diagnose")
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
    write_report_json(report_dir / f"{command}.json", result, command=command)
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
    write_report_json(report_dir / f"{command}.json", result, command=command)
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


@dataclass
class BackendCheck:
    code: str
    status: str
    message: str
    evidence: str | None = None


@dataclass
class BackendAction:
    code: str
    status: str
    message: str
    command: str | None = None
    evidence: str | None = None


@dataclass
class BackendResult:
    generated_at: str
    tool_version: str
    project_root: str | None
    invoked_from: str
    mode: str
    dry_run: bool = False
    backend_host: str | None = None
    backend_port: int | None = None
    backend_port_parse_error: str | None = None
    backend_port_probe: PortProbe | None = None
    health: list[HttpProbe] = field(default_factory=list)
    state_backend: dict[str, Any] = field(default_factory=dict)
    cargo_version: ProcessProbe | None = None
    rustc_version: ProcessProbe | None = None
    cargo_metadata: ProcessProbe | None = None
    cargo_check: ProcessProbe | None = None
    process_pid: int | None = None
    process_alive: bool | None = None
    process_returncode: int | None = None
    run_id: str | None = None
    log_path: str | None = None
    classification: str = "unknown"
    checks: list[BackendCheck] = field(default_factory=list)
    actions: list[BackendAction] = field(default_factory=list)
    failures: list[dict[str, str]] = field(default_factory=list)
    warnings: list[dict[str, str]] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)
    report_dir: str | None = None


def backend_effective_env(project_root: Path) -> dict[str, str]:
    return effective_env_values_for(project_root, "backend")


def parse_backend_host_port(project_root: Path) -> tuple[str, int, str | None]:
    values = backend_effective_env(project_root)
    host = values.get("APP__HOST", "127.0.0.1") or "127.0.0.1"
    raw_port = values.get("APP__PORT", str(DEFAULT_PORTS["backend"])) or str(DEFAULT_PORTS["backend"])
    try:
        port = int(raw_port)
    except ValueError:
        return host, DEFAULT_PORTS["backend"], f"APP__PORT is not an integer: {raw_port}"
    if port <= 0 or port > 65535:
        return host, DEFAULT_PORTS["backend"], f"APP__PORT is outside TCP port range: {raw_port}"
    return host, port, None


def http_probe_host(bind_host: str | None) -> str:
    if bind_host in {None, "", "0.0.0.0", "::", "[::]"}:
        return "127.0.0.1"
    return str(bind_host)


def backend_health_urls(host: str | None, port: int | None) -> dict[str, str]:
    probe_host = http_probe_host(host)
    probe_port = port or DEFAULT_PORTS["backend"]
    return {
        "backend_health_root": f"http://{probe_host}:{probe_port}/health",
        "backend_health_api": f"http://{probe_host}:{probe_port}/api/v1/health",
    }


def probe_backend_health(host: str | None, port: int | None, *, timeout: float = 1.5) -> list[HttpProbe]:
    return [probe_http(name, url, timeout=timeout) for name, url in backend_health_urls(host, port).items()]


def backend_health_ready(probes: list[HttpProbe]) -> bool:
    expected = {"backend_health_root", "backend_health_api"}
    seen = {probe.name for probe in probes if probe.reachable and probe.status and 200 <= probe.status < 300}
    return expected.issubset(seen)


def command_output_text(probe: ProcessProbe | None) -> str:
    if probe is None:
        return ""
    return "\n".join(part for part in [probe.stdout, probe.stderr, probe.error or ""] if part).strip()


def tail_text(text: str, *, max_chars: int = 12000) -> str:
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def read_log_tail(path: Path | None, *, max_chars: int = 20000) -> str:
    if path is None or not path.exists():
        return ""
    try:
        return tail_text(path.read_text(encoding="utf-8", errors="replace"), max_chars=max_chars)
    except OSError as exc:
        return f"<could not read log: {exc}>"


def sanitize_backend_log(text: str, project_root: Path | None = None) -> str:
    if not text:
        return ""
    cleaned = text
    if project_root is not None:
        db_url = backend_effective_env(project_root).get("DATABASE__URL")
        if db_url:
            cleaned = cleaned.replace(db_url, mask_database_url(db_url))
            try:
                parsed = urllib.parse.urlsplit(db_url)
                if parsed.password:
                    cleaned = cleaned.replace(urllib.parse.unquote(parsed.password), "***")
            except Exception:
                pass
    return "\n".join(cleaned.strip().splitlines()[-40:])


def classify_backend_failure(text: str, default: str) -> str:
    lower = text.lower()
    if "address already in use" in lower or "os error 98" in lower or "os error 10048" in lower:
        return "port_conflict"
    if "migration" in lower and "missing in the resolved migrations" in lower:
        return "migration_drift"
    if "migration" in lower and ("failed" in lower or "error" in lower):
        return "migration_failed"
    if "password authentication failed" in lower or "authentication failed" in lower:
        return "postgres_auth_failed"
    if "database" in lower and "does not exist" in lower:
        return "database_missing"
    if "connection refused" in lower or "could not connect" in lower or "connection error" in lower:
        return "postgres_unavailable"
    if "could not compile" in lower or "compilation failed" in lower or "error[" in lower:
        return "cargo_check_failed"
    if "timeout" in lower:
        return "backend_health_timeout"
    return default


def run_backend_command_probe(
    name: str,
    command: list[str],
    *,
    project_root: Path,
    cwd: Path,
    timeout: int,
    log_path: Path | None = None,
) -> ProcessProbe:
    probe = run_process_probe(name, command, cwd=cwd, timeout=timeout)
    if log_path is not None:
        lines = [
            f"$ {command_as_text(command)}",
            f"cwd: {rel(cwd, project_root)}",
            f"exit: {probe.returncode if probe.returncode is not None else probe.error or '<none>'}",
            "",
            "## stdout",
            probe.stdout or "<empty>",
            "",
            "## stderr",
            probe.stderr or probe.error or "<empty>",
            "",
        ]
        log_path.write_text("\n".join(lines), encoding="utf-8")
    return probe


def state_backend_entry(project_root: Path) -> dict[str, Any]:
    state = read_json(project_root / BOOTSTRAP_DIR_NAME / "state.json")
    processes = state.get("processes") if isinstance(state.get("processes"), dict) else {}
    backend = processes.get("backend") if isinstance(processes.get("backend"), dict) else {}
    if not backend:
        return {}
    pid_raw = backend.get("pid")
    try:
        pid = int(pid_raw)
    except (TypeError, ValueError):
        pid = -1
    backend = dict(backend)
    backend["alive"] = pid_alive(pid)
    return backend


def update_process_state(
    project_root: Path,
    *,
    process_name: str,
    pid: int,
    cwd: Path,
    command: list[str],
    started_at: str,
    run_id_value: str,
    log_path: Path | None,
    report_dir: Path | None,
) -> None:
    state_path = project_root / BOOTSTRAP_DIR_NAME / "state.json"
    state = read_json(state_path)
    if "_error" in state:
        state = {}
    processes = state.get("processes") if isinstance(state.get("processes"), dict) else {}
    processes[process_name] = {
        "pid": pid,
        "cwd": rel(cwd, project_root),
        "command": command_as_text(command),
        "startedAt": started_at,
        "runId": run_id_value,
        "logPath": rel(log_path, project_root) if log_path else None,
    }
    state["version"] = STATE_VERSION
    state["activeRunId"] = run_id_value
    state["processes"] = processes
    last_reports = state.get("lastReports") if isinstance(state.get("lastReports"), list) else []
    if report_dir is not None:
        last_reports.append(rel(report_dir, project_root))
        state["lastReports"] = last_reports[-20:]
    state_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(state_path, state)


def build_backend_result(project_root: Path | None, invoked_from: Path, *, mode: str, dry_run: bool = False) -> BackendResult:
    result = BackendResult(
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

    host, port, port_error = parse_backend_host_port(project_root)
    result.backend_host = host
    result.backend_port = port
    result.backend_port_parse_error = port_error
    result.backend_port_probe = probe_port("backend", port, host=http_probe_host(host))
    result.health = probe_backend_health(host, port)
    result.state_backend = state_backend_entry(project_root)
    result.cargo_version = run_process_probe("cargo_version", ["cargo", "--version"], cwd=project_root, timeout=8)
    result.rustc_version = run_process_probe("rustc_version", ["rustc", "--version"], cwd=project_root, timeout=8)

    if port_error:
        result.warnings.append({"code": "backend_port_parse", "message": port_error})
    if result.state_backend:
        if result.state_backend.get("alive"):
            result.warnings.append(
                {
                    "code": "backend_process_registered",
                    "message": f"state.json already contains alive backend pid={result.state_backend.get('pid')}.",
                }
            )
        else:
            result.warnings.append(
                {
                    "code": "backend_stale_process",
                    "message": f"state.json contains stale backend pid={result.state_backend.get('pid')}; it is not alive.",
                }
            )
    return result


def add_backend_preflight_checks(result: BackendResult) -> None:
    if result.cargo_version:
        status = "ok" if process_probe_ok(result.cargo_version) else "fail"
        result.checks.append(BackendCheck("cargo_version", status, "Cargo availability check.", first_output_line(result.cargo_version)))
    if result.rustc_version:
        status = "ok" if process_probe_ok(result.rustc_version) else "fail"
        result.checks.append(BackendCheck("rustc_version", status, "Rust compiler availability check.", first_output_line(result.rustc_version)))
    if result.backend_port_probe:
        status = "warn" if result.backend_port_probe.open else "ok"
        message = f"Backend TCP port {result.backend_port_probe.host}:{result.backend_port_probe.port} is {'open' if result.backend_port_probe.open else 'closed/free'}."
        evidence = "tcp connect succeeded" if result.backend_port_probe.open else (result.backend_port_probe.error or "")
        result.checks.append(BackendCheck("backend_port_preflight", status, message, evidence))
    if result.health:
        for probe in result.health:
            status = "ok" if probe.reachable and probe.status and 200 <= probe.status < 300 else "warn"
            evidence = probe.error or (f"{probe.duration_ms} ms" if probe.duration_ms is not None else None)
            message = f"{probe.url} returned HTTP {probe.status}." if probe.reachable else f"{probe.url} is not reachable."
            result.checks.append(BackendCheck(probe.name, status, message, evidence))


def finalize_backend_check_classification(result: BackendResult, project_root: Path, *, operation: str) -> None:
    add_backend_preflight_checks(result)
    if not process_probe_ok(result.cargo_version):
        result.classification = "missing_prerequisite"
        result.failures.append({"code": "missing_cargo", "message": "cargo is not available on PATH."})
        result.next_actions.append("Install Rust/Cargo or use a shell where cargo is available, then rerun check-backend.")
        return
    if not process_probe_ok(result.rustc_version):
        result.classification = "missing_prerequisite"
        result.failures.append({"code": "missing_rustc", "message": "rustc is not available on PATH."})
        result.next_actions.append("Install Rust toolchain or repair PATH, then rerun check-backend.")
        return
    if result.cargo_metadata is not None:
        status = "ok" if process_probe_ok(result.cargo_metadata) else "fail"
        result.checks.append(BackendCheck("cargo_metadata", status, "cargo metadata completed.", first_output_line(result.cargo_metadata)))
        if not process_probe_ok(result.cargo_metadata):
            text = command_output_text(result.cargo_metadata)
            result.classification = classify_backend_failure(text, "cargo_metadata_failed")
            result.failures.append({"code": result.classification, "message": "cargo metadata failed."})
            result.next_actions.append("Review cargo-metadata.log and Cargo.toml/Cargo.lock before trying to run the backend.")
            return
    if result.cargo_check is not None:
        status = "ok" if process_probe_ok(result.cargo_check) else "fail"
        result.checks.append(BackendCheck("cargo_check", status, "cargo check completed.", first_output_line(result.cargo_check)))
        if not process_probe_ok(result.cargo_check):
            text = command_output_text(result.cargo_check)
            result.classification = classify_backend_failure(text, "cargo_check_failed")
            result.failures.append({"code": result.classification, "message": "cargo check failed."})
            result.next_actions.append("Fix the Rust compile error from cargo-check.log. Do not start backend until cargo check passes.")
            return
    if operation == "check-backend":
        result.classification = "backend_check_ok"
        result.next_actions.append("Backend compile preflight passed. Continue with `python tools/devbootstrap.py start-backend` when PostgreSQL is ready.")


def render_backend_report(result: BackendResult) -> str:
    lines: list[str] = []
    lines.append(f"# devbootstrap {result.mode} report")
    lines.append("")
    lines.append(f"- Generated at: `{result.generated_at}`")
    lines.append(f"- Tool version: `{result.tool_version}`")
    lines.append(f"- Invoked from: `{result.invoked_from}`")
    lines.append(f"- Project root: `{result.project_root or 'not found'}`")
    lines.append(f"- Classification: `{result.classification}`")
    lines.append(f"- Dry run: `{result.dry_run}`")
    if result.backend_host is not None and result.backend_port is not None:
        lines.append(f"- Backend bind/probe: `{result.backend_host}:{result.backend_port}`")
    if result.process_pid is not None:
        lines.append(f"- Backend PID: `{result.process_pid}`")
    if result.log_path:
        lines.append(f"- Backend log: `{result.log_path}`")
    lines.append("")

    lines.append("## Checks")
    lines.append("")
    if result.checks:
        lines.append("| Status | Code | Message | Evidence |")
        lines.append("|---|---|---|---|")
        for check in result.checks:
            evidence = (check.evidence or "").replace("\n", "<br>")
            lines.append(f"| {check.status} | `{check.code}` | {check.message} | `{evidence}` |")
    else:
        lines.append("No checks recorded.")
    lines.append("")

    lines.append("## Actions")
    lines.append("")
    if result.actions:
        for action in result.actions:
            command = f" `{action.command}`" if action.command else ""
            evidence = f" Evidence: `{action.evidence}`" if action.evidence else ""
            lines.append(f"- **{action.status}** `{action.code}` — {action.message}{command}.{evidence}")
    else:
        lines.append("No actions were executed.")
    lines.append("")

    lines.append("## Findings")
    lines.append("")
    if not result.failures and not result.warnings:
        lines.append("- No backend findings.")
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
        lines.append("- Continue with the next devbootstrap phase.")
    lines.append("")
    return "\n".join(lines)


def write_backend_reports(project_root: Path, result: BackendResult, command: str, report_dir: Path | None = None) -> Path:
    if report_dir is None:
        report_dir = create_report_dir(project_root, command)
    result.report_dir = rel(report_dir, project_root)
    write_report_json(report_dir / f"{command}.json", result, command=command)
    (report_dir / "report.md").write_text(render_backend_report(result), encoding="utf-8")
    return report_dir


def print_backend_summary(result: BackendResult) -> None:
    print_header(f"devbootstrap {result.mode}")
    print(f"Tool version: {result.tool_version}")
    print(f"Project root: {result.project_root or 'not found'}")
    print(f"Classification: {result.classification}")
    if result.backend_host is not None and result.backend_port is not None:
        print(f"Backend target: {result.backend_host}:{result.backend_port}")
    if result.process_pid is not None:
        alive_text = "alive" if result.process_alive else "not alive"
        print(f"Backend process: pid={result.process_pid} {alive_text}")
    print("\nChecks:")
    for check in result.checks:
        evidence = f" — {check.evidence}" if check.evidence else ""
        print(f"  - {check.status.upper()} {check.code}: {check.message}{evidence}")
    if result.actions:
        print("\nActions:")
        for action in result.actions:
            command = f" — {action.command}" if action.command else ""
            evidence = f" — {action.evidence}" if action.evidence else ""
            print(f"  - {action.status.upper()} {action.code}: {action.message}{command}{evidence}")
    if result.failures or result.warnings:
        print("\nFindings:")
        for failure in result.failures:
            print(f"  - FAIL {failure['code']}: {failure['message']}")
        for warning in result.warnings:
            print(f"  - WARN {warning['code']}: {warning['message']}")
    else:
        print("\nFindings: no backend findings")
    if result.next_actions:
        print("\nNext safe actions:")
        for action in result.next_actions:
            print(f"  - {action}")
    if result.report_dir:
        print(f"\nReport: {result.report_dir}/report.md")


def command_check_backend(args: argparse.Namespace) -> int:
    invoked_from = Path.cwd()
    project_root = find_project_root(invoked_from)
    result = build_backend_result(project_root, invoked_from, mode="check-backend", dry_run=args.dry_run)
    report_dir: Path | None = None
    if project_root is not None and not args.no_write_report:
        report_dir = create_report_dir(project_root, "check-backend")
        result.report_dir = rel(report_dir, project_root)
    if project_root is not None:
        backend_dir = project_root / "backend"
        if args.dry_run:
            result.actions.append(BackendAction("cargo_metadata", "planned", "Would run cargo metadata for backend.", "cargo metadata --format-version 1 --no-deps"))
            result.actions.append(BackendAction("cargo_check", "planned", "Would run cargo check for backend.", "cargo check"))
            result.classification = "dry_run"
            result.next_actions.append("Run without --dry-run to execute cargo metadata and cargo check.")
            add_backend_preflight_checks(result)
        else:
            metadata_log = report_dir / "cargo-metadata.log" if report_dir else None
            check_log = report_dir / "cargo-check.log" if report_dir else None
            result.cargo_metadata = run_backend_command_probe(
                "cargo_metadata",
                ["cargo", "metadata", "--format-version", "1", "--no-deps"],
                project_root=project_root,
                cwd=backend_dir,
                timeout=args.metadata_timeout_seconds,
                log_path=metadata_log,
            )
            if process_probe_ok(result.cargo_metadata):
                result.cargo_check = run_backend_command_probe(
                    "cargo_check",
                    ["cargo", "check"],
                    project_root=project_root,
                    cwd=backend_dir,
                    timeout=args.timeout_seconds,
                    log_path=check_log,
                )
            finalize_backend_check_classification(result, project_root, operation="check-backend")
    if project_root is not None and not args.no_write_report:
        write_backend_reports(project_root, result, "check-backend", report_dir)
    print_backend_summary(result)
    if args.json:
        print("\nJSON:")
        print(json.dumps(as_jsonable(result), ensure_ascii=False, indent=2))
    return 1 if result.failures and not args.dry_run else 0


def launch_backend_process(project_root: Path, report_dir: Path) -> tuple[subprocess.Popen[Any], Path]:
    backend_dir = project_root / "backend"
    log_path = report_dir / "backend.log"
    log_handle = log_path.open("ab", buffering=0)
    header = f"\n== devbootstrap start-backend {iso_now()} ==\n$ cargo run\ncwd: {rel(backend_dir, project_root)}\n\n".encode("utf-8", errors="replace")
    log_handle.write(header)
    try:
        process = subprocess.Popen(
            ["cargo", "run"],
            cwd=str(backend_dir),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            **popen_process_group_kwargs(),
        )
    except Exception:
        log_handle.close()
        raise
    # The child keeps the file descriptor open. The parent can close its copy.
    log_handle.close()
    return process, log_path


def wait_for_backend_health(process: subprocess.Popen[Any], host: str | None, port: int | None, *, timeout_seconds: int) -> tuple[bool, list[HttpProbe], int | None]:
    deadline = time.monotonic() + timeout_seconds
    last_probes: list[HttpProbe] = []
    while time.monotonic() < deadline:
        returncode = process.poll()
        last_probes = probe_backend_health(host, port, timeout=1.0)
        if backend_health_ready(last_probes):
            return True, last_probes, returncode
        if returncode is not None:
            return False, last_probes, returncode
        time.sleep(1.0)
    return False, last_probes, process.poll()


def command_start_backend(args: argparse.Namespace) -> int:
    invoked_from = Path.cwd()
    project_root = find_project_root(invoked_from)
    result = build_backend_result(project_root, invoked_from, mode="start-backend", dry_run=args.dry_run)
    report_dir: Path | None = None
    if project_root is not None and (not args.no_write_report or not args.dry_run):
        report_dir = create_report_dir(project_root, "start-backend")
        result.report_dir = rel(report_dir, project_root)

    if project_root is not None:
        add_backend_preflight_checks(result)
        if backend_health_ready(result.health):
            result.classification = "backend_already_running"
            result.actions.append(BackendAction("start_backend_noop", "ok", "Backend health is already reachable; cargo run was not started."))
            result.next_actions.append("Continue with frontend phases or run smoke checks.")
        elif result.backend_port_probe and result.backend_port_probe.open:
            result.classification = "port_conflict"
            result.failures.append({"code": "port_conflict", "message": "Backend port is open but health endpoints are not healthy. devbootstrap will not kill a foreign process."})
            result.next_actions.append("Inspect the process on the backend port manually, or stop the old backend you own and rerun start-backend.")
        elif not process_probe_ok(result.cargo_version):
            result.classification = "missing_prerequisite"
            result.failures.append({"code": "missing_cargo", "message": "cargo is not available on PATH."})
            result.next_actions.append("Install Rust/Cargo or use a shell where cargo is available, then rerun start-backend.")
        elif args.dry_run:
            result.classification = "dry_run"
            result.actions.append(BackendAction("cargo_run", "planned", "Would start backend with cargo run and wait for health.", "cargo run"))
            result.next_actions.append("Run without --dry-run when PostgreSQL is ready.")
        else:
            command = ["cargo", "run"]
            run_id_value = run_id("start-backend")
            result.run_id = run_id_value
            try:
                process, log_path = launch_backend_process(project_root, report_dir or create_report_dir(project_root, "start-backend"))
                if result.report_dir is None:
                    result.report_dir = rel(log_path.parent, project_root)
                result.process_pid = process.pid
                result.log_path = rel(log_path, project_root)
                result.actions.append(BackendAction("cargo_run", "started", "Started backend process with cargo run.", command_as_text(command), f"pid={process.pid}"))
                ready, probes, returncode = wait_for_backend_health(process, result.backend_host, result.backend_port, timeout_seconds=args.timeout_seconds)
                result.health = probes
                result.process_returncode = returncode
                result.process_alive = process.poll() is None
                if ready:
                    result.classification = "backend_started"
                    result.checks.append(BackendCheck("backend_health_wait", "ok", "Backend health endpoints became ready.", f"timeout={args.timeout_seconds}s"))
                    update_process_state(
                        project_root,
                        process_name="backend",
                        pid=process.pid,
                        cwd=project_root / "backend",
                        command=command,
                        started_at=result.generated_at,
                        run_id_value=run_id_value,
                        log_path=log_path,
                        report_dir=log_path.parent,
                    )
                    result.next_actions.append("Backend is running. Continue with frontend preparation/start phases.")
                else:
                    log_tail = sanitize_backend_log(read_log_tail(log_path), project_root)
                    default = "backend_start_failed" if returncode is not None else "backend_health_timeout"
                    result.classification = classify_backend_failure(log_tail, default)
                    result.checks.append(BackendCheck("backend_health_wait", "fail", "Backend health endpoints did not become ready.", f"timeout={args.timeout_seconds}s"))
                    result.failures.append({"code": result.classification, "message": "Backend did not reach healthy state after cargo run."})
                    if result.process_alive:
                        update_process_state(
                            project_root,
                            process_name="backend",
                            pid=process.pid,
                            cwd=project_root / "backend",
                            command=command,
                            started_at=result.generated_at,
                            run_id_value=run_id_value,
                            log_path=log_path,
                            report_dir=log_path.parent,
                        )
                        result.next_actions.append("Backend process is still alive but health timed out. Inspect backend.log, then run `python tools/devbootstrap.py stop` if the tracked backend must be cleaned up.")
                    else:
                        result.next_actions.append("Inspect backend.log for the classified failure before retrying.")
            except FileNotFoundError:
                result.classification = "missing_prerequisite"
                result.failures.append({"code": "missing_cargo", "message": "cargo run could not be started because cargo was not found."})
            except OSError as exc:
                result.classification = "backend_start_failed"
                result.failures.append({"code": "backend_start_failed", "message": f"Could not start cargo run: {exc}"})
    if project_root is not None and report_dir is not None:
        write_backend_reports(project_root, result, "start-backend", report_dir)
    print_backend_summary(result)
    if args.json:
        print("\nJSON:")
        print(json.dumps(as_jsonable(result), ensure_ascii=False, indent=2))
    return 1 if result.failures and not args.dry_run else 0


@dataclass
class FrontendCheck:
    code: str
    status: str
    message: str
    evidence: str | None = None


@dataclass
class FrontendAction:
    code: str
    status: str
    message: str
    command: str | None = None
    evidence: str | None = None


@dataclass
class FrontendResult:
    generated_at: str
    tool_version: str
    project_root: str | None
    invoked_from: str
    mode: str
    dry_run: bool = False
    frontend_host: str = "127.0.0.1"
    frontend_port: int = 5173
    frontend_url: str | None = None
    api_base_url: str | None = None
    package_json_exists: bool = False
    package_lock_exists: bool = False
    node_modules_exists: bool = False
    package_scripts: dict[str, str] = field(default_factory=dict)
    package_json_hash: str | None = None
    package_lock_hash: str | None = None
    install_marker_path: str | None = None
    install_marker_valid: bool = False
    install_command: list[str] = field(default_factory=list)
    node_version: ProcessProbe | None = None
    npm_version: ProcessProbe | None = None
    frontend_port_probe: PortProbe | None = None
    frontend_root_probe: HttpProbe | None = None
    api_probe: HttpProbe | None = None
    backend_health: list[HttpProbe] = field(default_factory=list)
    state_frontend: dict[str, Any] = field(default_factory=dict)
    process_pid: int | None = None
    process_alive: bool | None = None
    process_returncode: int | None = None
    run_id: str | None = None
    log_path: str | None = None
    detected_urls: list[str] = field(default_factory=list)
    npm_install: ProcessProbe | None = None
    classification: str = "unknown"
    checks: list[FrontendCheck] = field(default_factory=list)
    actions: list[FrontendAction] = field(default_factory=list)
    failures: list[dict[str, str]] = field(default_factory=list)
    warnings: list[dict[str, str]] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)
    report_dir: str | None = None


def frontend_effective_env(project_root: Path) -> dict[str, str]:
    return effective_env_values_for(project_root, "frontend")


def frontend_install_marker_path(project_root: Path) -> Path:
    return project_root / BOOTSTRAP_DIR_NAME / "frontend-install.json"


def sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def read_frontend_package(project_root: Path) -> tuple[dict[str, Any], str | None]:
    package_path = project_root / "frontend" / "package.json"
    try:
        data = json.loads(package_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, "frontend/package.json is missing"
    except json.JSONDecodeError as exc:
        return {}, f"frontend/package.json is not valid JSON: {exc}"
    if not isinstance(data, dict):
        return {}, "frontend/package.json root is not an object"
    return data, None


def frontend_scripts_from_package(package_data: dict[str, Any]) -> dict[str, str]:
    scripts = package_data.get("scripts")
    if not isinstance(scripts, dict):
        return {}
    return {str(key): str(value) for key, value in scripts.items()}


def parse_frontend_host_port(project_root: Path) -> tuple[str, int, str | None]:
    values = frontend_effective_env(project_root)
    host = values.get("VITE_DEV_HOST") or values.get("VITE_HOST") or "127.0.0.1"
    raw_port = values.get("VITE_DEV_PORT") or values.get("VITE_PORT") or str(DEFAULT_PORTS["frontend"])
    try:
        port = int(raw_port)
    except ValueError:
        return host, DEFAULT_PORTS["frontend"], f"Frontend port is not an integer: {raw_port}"
    if port <= 0 or port > 65535:
        return host, DEFAULT_PORTS["frontend"], f"Frontend port is outside TCP port range: {raw_port}"
    return host, port, None


def frontend_root_url(host: str, port: int) -> str:
    return f"http://{http_probe_host(host)}:{port}/"


def frontend_api_health_url(api_base_url: str | None) -> str | None:
    if not api_base_url:
        return None
    base = api_base_url.rstrip("/")
    if not base:
        return None
    return f"{base}/health"


def load_frontend_install_marker(project_root: Path) -> dict[str, Any]:
    return read_json(frontend_install_marker_path(project_root))


def normalize_frontend_prepare_dep_mode(value: str | None) -> str:
    mode = (value or DEFAULT_FRONTEND_PREPARE_DEP_MODE).strip().lower()
    if mode == "missing-or-stale":
        return "stale"
    if mode not in FRONTEND_PREPARE_DEP_MODES:
        return DEFAULT_FRONTEND_PREPARE_DEP_MODE
    return mode


def process_probe_version_value(probe: ProcessProbe | None) -> str | None:
    if not process_probe_ok(probe):
        return None
    return first_output_line(probe)


def frontend_install_platform_fingerprint() -> dict[str, str]:
    return {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python": platform.python_version(),
    }


def frontend_install_marker_mismatch_reasons(
    project_root: Path,
    package_json_hash: str | None,
    package_lock_hash: str | None,
    *,
    node_version: str | None = None,
    npm_version: str | None = None,
) -> list[str]:
    marker_path = frontend_install_marker_path(project_root)
    node_modules_path = project_root / "frontend" / "node_modules"
    marker = load_frontend_install_marker(project_root)
    reasons: list[str] = []
    if not node_modules_path.is_dir():
        reasons.append("frontend/node_modules is missing")
    if not marker_path.is_file():
        reasons.append("frontend install marker is missing")
        return reasons
    if "_error" in marker:
        reasons.append(f"frontend install marker cannot be read: {marker.get('_error')}")
        return reasons
    if marker.get("packageJsonSha256") != package_json_hash:
        reasons.append("frontend/package.json hash differs from install marker")
    if marker.get("packageLockSha256") != package_lock_hash:
        reasons.append("frontend/package-lock.json hash differs from install marker")
    marker_platform = marker.get("platform") if isinstance(marker.get("platform"), dict) else {}
    current_platform = frontend_install_platform_fingerprint()
    for key in ["system", "machine"]:
        if marker_platform.get(key) != current_platform.get(key):
            reasons.append(f"platform {key} differs from install marker")
    if node_version and marker.get("nodeVersion") != node_version:
        reasons.append("Node.js version differs from install marker")
    if npm_version and marker.get("npmVersion") != npm_version:
        reasons.append("npm version differs from install marker")
    return reasons


def frontend_install_marker_matches(
    project_root: Path,
    package_json_hash: str | None,
    package_lock_hash: str | None,
    *,
    node_version: str | None = None,
    npm_version: str | None = None,
) -> bool:
    return not frontend_install_marker_mismatch_reasons(
        project_root,
        package_json_hash,
        package_lock_hash,
        node_version=node_version,
        npm_version=npm_version,
    )


def write_frontend_install_marker(project_root: Path, result: FrontendResult, command: list[str], *, install_mode: str) -> None:
    marker_path = frontend_install_marker_path(project_root)
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker = {
        "version": STATE_VERSION,
        "generatedAt": iso_now(),
        "toolVersion": TOOL_VERSION,
        "command": command_as_text(command),
        "commandList": command,
        "installMode": install_mode,
        "packageManager": "npm",
        "packageJsonSha256": result.package_json_hash,
        "packageLockSha256": result.package_lock_hash,
        "nodeVersion": process_probe_version_value(result.node_version),
        "npmVersion": process_probe_version_value(result.npm_version),
        "platform": frontend_install_platform_fingerprint(),
    }
    write_json(marker_path, marker)


def frontend_install_command(project_root: Path) -> list[str]:
    if (project_root / "frontend" / "package-lock.json").is_file():
        return ["npm", "ci"]
    return ["npm", "install"]


def frontend_prepare_should_install(result: FrontendResult, mode: str) -> tuple[bool, str]:
    normalized = normalize_frontend_prepare_dep_mode(mode)
    if normalized == "always":
        return True, "prepare mode is always"
    if normalized == "never":
        return False, "prepare mode is never"
    if normalized == "missing":
        if not result.node_modules_exists:
            return True, "frontend/node_modules is missing"
        return False, "prepare mode is missing and frontend/node_modules already exists"
    if not frontend_dependencies_current(result):
        return True, "frontend dependencies are missing or stale"
    return False, "frontend dependencies are current"


def state_process_entry(project_root: Path, process_name: str) -> dict[str, Any]:
    state = read_json(project_root / BOOTSTRAP_DIR_NAME / "state.json")
    processes = state.get("processes") if isinstance(state.get("processes"), dict) else {}
    entry = processes.get(process_name) if isinstance(processes.get(process_name), dict) else {}
    if not entry:
        return {}
    pid_raw = entry.get("pid")
    try:
        pid = int(pid_raw)
    except (TypeError, ValueError):
        pid = -1
    entry = dict(entry)
    entry["alive"] = pid_alive(pid)
    return entry


def build_frontend_result(project_root: Path | None, invoked_from: Path, *, mode: str, dry_run: bool = False) -> FrontendResult:
    result = FrontendResult(
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

    host, port, port_error = parse_frontend_host_port(project_root)
    result.frontend_host = host
    result.frontend_port = port
    result.frontend_url = frontend_root_url(host, port)
    values = frontend_effective_env(project_root)
    result.api_base_url = values.get("VITE_API_BASE_URL")

    package_data, package_error = read_frontend_package(project_root)
    result.package_json_exists = (project_root / "frontend" / "package.json").is_file()
    result.package_lock_exists = (project_root / "frontend" / "package-lock.json").is_file()
    result.node_modules_exists = (project_root / "frontend" / "node_modules").is_dir()
    result.package_scripts = frontend_scripts_from_package(package_data)
    result.package_json_hash = sha256_file(project_root / "frontend" / "package.json")
    result.package_lock_hash = sha256_file(project_root / "frontend" / "package-lock.json")
    result.install_marker_path = rel(frontend_install_marker_path(project_root), project_root)
    result.install_command = frontend_install_command(project_root)
    result.node_version = run_process_probe("node_version", ["node", "--version"], cwd=project_root, timeout=8)
    result.npm_version = run_process_probe("npm_version", ["npm", "--version"], cwd=project_root, timeout=8)
    result.install_marker_valid = frontend_install_marker_matches(
        project_root,
        result.package_json_hash,
        result.package_lock_hash,
        node_version=process_probe_version_value(result.node_version),
        npm_version=process_probe_version_value(result.npm_version),
    )
    result.frontend_port_probe = probe_port("frontend", port, host=http_probe_host(host))
    result.frontend_root_probe = probe_http("frontend_root", result.frontend_url)
    api_health = frontend_api_health_url(result.api_base_url)
    if api_health:
        result.api_probe = probe_http("frontend_api_base_health", api_health)
    backend_host, backend_port, _ = parse_backend_host_port(project_root)
    result.backend_health = probe_backend_health(backend_host, backend_port)
    result.state_frontend = state_process_entry(project_root, "frontend")

    if port_error:
        result.warnings.append({"code": "frontend_port_parse", "message": port_error})
    if package_error:
        result.failures.append({"code": "frontend_package_invalid", "message": package_error})
    if result.state_frontend:
        if result.state_frontend.get("alive"):
            result.warnings.append(
                {
                    "code": "frontend_process_registered",
                    "message": f"state.json already contains alive frontend pid={result.state_frontend.get('pid')}.",
                }
            )
        else:
            result.warnings.append(
                {
                    "code": "frontend_stale_process",
                    "message": f"state.json contains stale frontend pid={result.state_frontend.get('pid')}; it is not alive.",
                }
            )
    return result


def add_frontend_preflight_checks(result: FrontendResult, project_root: Path | None = None) -> None:
    if result.node_version:
        status = "ok" if process_probe_ok(result.node_version) else "fail"
        result.checks.append(FrontendCheck("node_version", status, "Node.js availability check.", first_output_line(result.node_version)))
    if result.npm_version:
        status = "ok" if process_probe_ok(result.npm_version) else "fail"
        result.checks.append(FrontendCheck("npm_version", status, "npm availability check.", first_output_line(result.npm_version)))
    result.checks.append(
        FrontendCheck(
            "package_json",
            "ok" if result.package_json_exists else "fail",
            "frontend/package.json presence check.",
        )
    )
    result.checks.append(
        FrontendCheck(
            "package_lock",
            "ok" if result.package_lock_exists else "warn",
            "frontend/package-lock.json presence check; npm ci is preferred when it exists.",
        )
    )
    dev_script = result.package_scripts.get("dev")
    result.checks.append(
        FrontendCheck(
            "frontend_dev_script",
            "ok" if dev_script else "fail",
            "package.json contains scripts.dev for Vite startup.",
            dev_script,
        )
    )
    result.checks.append(
        FrontendCheck(
            "node_modules",
            "ok" if result.node_modules_exists else "warn",
            "frontend/node_modules presence check.",
            "install marker valid" if result.install_marker_valid else "install marker missing or stale",
        )
    )
    if result.frontend_port_probe:
        status = "warn" if result.frontend_port_probe.open else "ok"
        message = f"Frontend TCP port {result.frontend_port_probe.host}:{result.frontend_port_probe.port} is {'open' if result.frontend_port_probe.open else 'closed/free'}."
        evidence = "tcp connect succeeded" if result.frontend_port_probe.open else (result.frontend_port_probe.error or "")
        result.checks.append(FrontendCheck("frontend_port_preflight", status, message, evidence))
    if result.frontend_root_probe:
        status = "ok" if result.frontend_root_probe.reachable and result.frontend_root_probe.status and 200 <= result.frontend_root_probe.status < 500 else "warn"
        message = f"{result.frontend_root_probe.url} returned HTTP {result.frontend_root_probe.status}." if result.frontend_root_probe.reachable else f"{result.frontend_root_probe.url} is not reachable."
        result.checks.append(FrontendCheck("frontend_root", status, message, result.frontend_root_probe.error))
    add_frontend_api_checks(result, project_root)


def add_frontend_api_checks(result: FrontendResult, project_root: Path | None) -> None:
    api_base = result.api_base_url or ""
    if not api_base:
        result.checks.append(FrontendCheck("frontend_api_base_url", "warn", "VITE_API_BASE_URL is missing from effective frontend env."))
        result.warnings.append({"code": "frontend_api_base_missing", "message": "VITE_API_BASE_URL is missing; browser requests may use an unintended fallback."})
        return
    if api_base.rstrip("/").endswith("/api/v1"):
        result.checks.append(FrontendCheck("frontend_api_base_path", "ok", "VITE_API_BASE_URL ends with /api/v1.", api_base))
    else:
        result.checks.append(FrontendCheck("frontend_api_base_path", "warn", "VITE_API_BASE_URL should normally end with /api/v1.", api_base))
        result.warnings.append({"code": "frontend_api_base_path", "message": "VITE_API_BASE_URL does not end with /api/v1."})
    if project_root is not None:
        _, backend_port, _ = parse_backend_host_port(project_root)
        api_port = parse_url_port(api_base)
        if str(api_port) == str(backend_port):
            result.checks.append(FrontendCheck("frontend_api_backend_port_match", "ok", "VITE_API_BASE_URL points to the configured backend port.", f"api={api_port}, backend={backend_port}"))
        else:
            result.checks.append(FrontendCheck("frontend_api_backend_port_match", "warn", "VITE_API_BASE_URL does not point to the configured backend port.", f"api={api_port}, backend={backend_port}"))
            result.warnings.append({"code": "frontend_api_backend_mismatch", "message": f"VITE_API_BASE_URL port {api_port} does not match backend APP__PORT {backend_port}."})
    if result.api_probe:
        status = "ok" if result.api_probe.reachable and result.api_probe.status and 200 <= result.api_probe.status < 300 else "warn"
        message = f"{result.api_probe.url} returned HTTP {result.api_probe.status}." if result.api_probe.reachable else f"{result.api_probe.url} is not reachable."
        result.checks.append(FrontendCheck("frontend_api_health", status, message, result.api_probe.error))
        if status != "ok":
            result.warnings.append({"code": "frontend_api_unreachable", "message": "Backend API health derived from VITE_API_BASE_URL is not reachable yet."})


def frontend_dependencies_current(result: FrontendResult) -> bool:
    return bool(result.node_modules_exists and result.install_marker_valid)


def render_frontend_report(result: FrontendResult) -> str:
    lines: list[str] = []
    lines.append(f"# devbootstrap {result.mode} report")
    lines.append("")
    lines.append(f"- Generated at: `{result.generated_at}`")
    lines.append(f"- Tool version: `{result.tool_version}`")
    lines.append(f"- Invoked from: `{result.invoked_from}`")
    lines.append(f"- Project root: `{result.project_root or 'not found'}`")
    lines.append(f"- Dry run: `{result.dry_run}`")
    lines.append(f"- Frontend URL: `{result.frontend_url or '<unknown>'}`")
    lines.append(f"- API base URL: `{result.api_base_url or '<missing>'}`")
    if result.process_pid is not None:
        lines.append(f"- Frontend PID: `{result.process_pid}`")
    if result.log_path:
        lines.append(f"- Frontend log: `{result.log_path}`")
    lines.append(f"- Classification: `{result.classification}`")
    lines.append("")

    lines.append("## Package")
    lines.append("")
    lines.append(f"- `frontend/package.json`: `{result.package_json_exists}`")
    lines.append(f"- `frontend/package-lock.json`: `{result.package_lock_exists}`")
    lines.append(f"- `frontend/node_modules`: `{result.node_modules_exists}`")
    lines.append(f"- Install marker: `{result.install_marker_path}` valid=`{result.install_marker_valid}`")
    lines.append(f"- Install command: `{command_as_text(result.install_command)}`")
    lines.append(f"- package.json SHA-256: `{result.package_json_hash or '<missing>'}`")
    lines.append(f"- package-lock.json SHA-256: `{result.package_lock_hash or '<missing>'}`")
    lines.append(f"- Platform fingerprint: `{frontend_install_platform_fingerprint()}`")
    lines.append("")
    lines.append("### Scripts")
    lines.append("")
    if result.package_scripts:
        for name, script in sorted(result.package_scripts.items()):
            lines.append(f"- `{name}`: `{script}`")
    else:
        lines.append("- No package scripts discovered.")
    lines.append("")

    lines.append("## Checks")
    lines.append("")
    if result.checks:
        lines.append("| Code | Status | Message | Evidence |")
        lines.append("|---|---|---|---|")
        for check in result.checks:
            lines.append(f"| `{check.code}` | {check.status} | {check.message} | `{check.evidence or ''}` |")
    else:
        lines.append("- No frontend checks recorded.")
    lines.append("")

    lines.append("## Actions")
    lines.append("")
    if result.actions:
        lines.append("| Code | Status | Message | Command | Evidence |")
        lines.append("|---|---|---|---|---|")
        for action in result.actions:
            lines.append(f"| `{action.code}` | {action.status} | {action.message} | `{action.command or ''}` | `{action.evidence or ''}` |")
    else:
        lines.append("- No frontend actions recorded.")
    lines.append("")

    if result.detected_urls:
        lines.append("## Detected dev server URLs")
        lines.append("")
        for url in result.detected_urls:
            lines.append(f"- `{url}`")
        lines.append("")

    lines.append("## Findings")
    lines.append("")
    if not result.failures and not result.warnings:
        lines.append("- No frontend findings.")
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
        lines.append("- Continue with the next devbootstrap phase.")
    lines.append("")
    return "\n".join(lines)


def write_frontend_reports(project_root: Path, result: FrontendResult, command: str, report_dir: Path | None = None) -> Path:
    if report_dir is None:
        report_dir = create_report_dir(project_root, command)
    result.report_dir = rel(report_dir, project_root)
    write_report_json(report_dir / f"{command}.json", result, command=command)
    (report_dir / "report.md").write_text(render_frontend_report(result), encoding="utf-8")
    return report_dir


def print_frontend_summary(result: FrontendResult) -> None:
    print_header(f"devbootstrap {result.mode}")
    print(f"Tool version: {result.tool_version}")
    print(f"Project root: {result.project_root or 'not found'}")
    print(f"Frontend URL: {result.frontend_url or '<unknown>'}")
    print(f"API base URL: {result.api_base_url or '<missing>'}")
    print(f"Classification: {result.classification}")
    if result.process_pid is not None:
        alive_text = "alive" if result.process_alive else "not alive"
        print(f"Frontend process: pid={result.process_pid} {alive_text}")
    if result.log_path:
        print(f"Log: {result.log_path}")
    if result.checks:
        print("\nChecks:")
        for check in result.checks:
            evidence = f" — {check.evidence}" if check.evidence else ""
            print(f"  - {check.status.upper()} {check.code}: {check.message}{evidence}")
    if result.actions:
        print("\nActions:")
        for action in result.actions:
            command = f" [{action.command}]" if action.command else ""
            evidence = f" — {action.evidence}" if action.evidence else ""
            print(f"  - {action.status.upper()} {action.code}: {action.message}{command}{evidence}")
    if result.failures or result.warnings:
        print("\nFindings:")
        for failure in result.failures:
            print(f"  - FAIL {failure['code']}: {failure['message']}")
        for warning in result.warnings:
            print(f"  - WARN {warning['code']}: {warning['message']}")
    else:
        print("\nFindings: no frontend findings")
    if result.report_dir:
        print(f"\nReport: {result.report_dir}/report.md")


def command_prepare_frontend(args: argparse.Namespace) -> int:
    invoked_from = Path.cwd()
    project_root = find_project_root(invoked_from)
    install_mode = "always" if args.force_install else normalize_frontend_prepare_dep_mode(getattr(args, "install_mode", None))
    result = build_frontend_result(project_root, invoked_from, mode="prepare-frontend", dry_run=args.dry_run)
    report_dir: Path | None = None
    if project_root is not None and not args.no_write_report:
        report_dir = create_report_dir(project_root, "prepare-frontend")
    if project_root is not None:
        add_frontend_preflight_checks(result, project_root)
        should_install, install_reason = frontend_prepare_should_install(result, install_mode)
        result.actions.append(
            FrontendAction(
                "dependency_prepare_policy",
                "ok",
                f"Dependency preparation mode is `{install_mode}`.",
                evidence=install_reason,
            )
        )
        if not process_probe_ok(result.node_version):
            result.classification = "missing_prerequisite"
            result.failures.append({"code": "missing_node", "message": "node is not available on PATH."})
            result.next_actions.append("Install Node.js or use a shell where node/npm are available, then rerun prepare-frontend.")
        elif not process_probe_ok(result.npm_version):
            result.classification = "missing_prerequisite"
            result.failures.append({"code": "missing_npm", "message": "npm is not available on PATH."})
            result.next_actions.append("Install npm or repair PATH, then rerun prepare-frontend.")
        elif not result.package_json_exists:
            result.classification = "frontend_package_invalid"
            result.next_actions.append("Restore frontend/package.json from the project archive before installing dependencies.")
        elif not should_install and frontend_dependencies_current(result):
            result.classification = "frontend_dependencies_current"
            result.actions.append(FrontendAction("npm_install_noop", "ok", "frontend/node_modules matches the devbootstrap install marker; install skipped.", evidence=install_reason))
            result.next_actions.append("Frontend dependencies look current. Continue with `python tools/devbootstrap.py start-frontend`.")
        elif not should_install:
            result.classification = "frontend_dependencies_stale" if result.node_modules_exists else "frontend_dependencies_missing"
            result.failures.append({"code": result.classification, "message": f"Frontend dependencies are not current and prepare mode `{install_mode}` did not permit installation."})
            result.next_actions.append("Rerun with `--install-mode=stale` or `--force-install` to repair missing/stale frontend dependencies.")
        elif not result.package_lock_exists and not args.allow_npm_install_without_lock:
            result.classification = "frontend_lockfile_missing"
            result.failures.append({"code": "frontend_lockfile_missing", "message": "frontend/package-lock.json is missing; devbootstrap will not fall back to npm install without explicit opt-in."})
            result.next_actions.append("Restore package-lock.json, or rerun with `--allow-npm-install-without-lock` when creating/updating the lockfile is intentional.")
        elif args.dry_run:
            result.classification = "frontend_prepare_planned"
            result.actions.append(FrontendAction("npm_install", "planned", "Would install frontend dependencies.", command_as_text(result.install_command), install_reason))
            result.next_actions.append("Run without --dry-run to install/update frontend dependencies.")
        else:
            before_package_hash = sha256_file(project_root / "frontend" / "package.json")
            before_lock_hash = sha256_file(project_root / "frontend" / "package-lock.json")
            log_path = report_dir / "npm-install.log" if report_dir is not None else None
            result.actions.append(FrontendAction("npm_install", "started", "Installing frontend dependencies.", command_as_text(result.install_command), install_reason))
            result.npm_install = run_frontend_command_probe(
                "npm_install",
                result.install_command,
                project_root=project_root,
                cwd=project_root / "frontend",
                timeout=args.timeout_seconds,
                log_path=log_path,
            )
            after_package_hash = sha256_file(project_root / "frontend" / "package.json")
            after_lock_hash = sha256_file(project_root / "frontend" / "package-lock.json")
            if not process_probe_ok(result.npm_install):
                result.classification = classify_frontend_failure(command_output_text(result.npm_install), "frontend_install_failed")
                result.failures.append({"code": result.classification, "message": "Frontend dependency installation failed."})
                result.next_actions.append("Inspect npm-install.log, fix npm/network/lockfile issues, then rerun prepare-frontend.")
            elif before_package_hash != after_package_hash:
                result.classification = "frontend_manifest_changed_by_install"
                result.failures.append({"code": result.classification, "message": "npm install changed frontend/package.json; release-gates will not hide manifest changes."})
                result.next_actions.append("Inspect frontend/package.json changes and commit/fix them in a separate patch before rerunning release-gates.")
            elif before_lock_hash != after_lock_hash:
                result.classification = "frontend_lockfile_changed_by_install"
                result.failures.append({"code": result.classification, "message": "npm install changed frontend/package-lock.json; release-gates will not hide lockfile changes."})
                result.next_actions.append("Inspect package-lock.json changes and commit/fix them in a separate patch before rerunning release-gates.")
            else:
                result.package_json_hash = after_package_hash
                result.package_lock_hash = after_lock_hash
                result.node_modules_exists = (project_root / "frontend" / "node_modules").is_dir()
                if not result.node_modules_exists:
                    result.classification = "frontend_dependencies_missing"
                    result.failures.append({"code": result.classification, "message": "npm command succeeded but frontend/node_modules is still missing."})
                else:
                    result.install_marker_valid = True
                    write_frontend_install_marker(project_root, result, result.install_command, install_mode=install_mode)
                    result.actions.append(FrontendAction("install_marker", "ok", "Updated frontend install marker.", evidence=result.install_marker_path))
                    result.classification = "frontend_dependencies_ready"
                    result.next_actions.append("Frontend dependencies are ready. Continue with `python tools/devbootstrap.py start-frontend`.")
    if project_root is not None and report_dir is not None:
        write_frontend_reports(project_root, result, "prepare-frontend", report_dir)
    print_frontend_summary(result)
    if args.json:
        print("\nJSON:")
        print(json.dumps(as_jsonable(result), ensure_ascii=False, indent=2))
    return 1 if result.failures and not args.dry_run else 0



def run_frontend_command_probe(
    name: str,
    command: list[str],
    *,
    project_root: Path,
    cwd: Path,
    timeout: int,
    log_path: Path | None = None,
) -> ProcessProbe:
    probe = run_process_probe(name, command, cwd=cwd, timeout=timeout, env_extra={"PYTHONDONTWRITEBYTECODE": "1"})
    if log_path is not None:
        lines = [
            f"$ {command_as_text(command)}",
            f"cwd: {rel(cwd, project_root)}",
            f"exit: {probe.returncode if probe.returncode is not None else probe.error or '<none>'}",
            "",
            "## stdout",
            sanitize_frontend_log(probe.stdout, project_root) or "<empty>",
            "",
            "## stderr",
            sanitize_frontend_log(probe.stderr or probe.error or "", project_root) or "<empty>",
            "",
        ]
        log_path.write_text("\n".join(lines), encoding="utf-8")
    return probe



def launch_frontend_process(project_root: Path, report_dir: Path, host: str, port: int) -> tuple[subprocess.Popen[Any], Path, list[str]]:
    frontend_dir = project_root / "frontend"
    log_path = report_dir / "frontend.log"
    command = ["npm", "run", "dev", "--", "--host", host, "--port", str(port), "--strictPort"]
    with log_path.open("ab") as log_file:
        header = f"\n== devbootstrap start-frontend {iso_now()} ==\n$ {command_as_text(command)}\ncwd: {rel(frontend_dir, project_root)}\n\n".encode("utf-8", errors="replace")
        log_file.write(header)
        log_file.flush()
        process = subprocess.Popen(
            command,
            cwd=str(frontend_dir),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            **popen_process_group_kwargs(),
        )
    return process, log_path, command


def frontend_ready(probe: HttpProbe | None) -> bool:
    return bool(probe and probe.reachable and probe.status is not None and 200 <= probe.status < 500)


def wait_for_frontend_root(process: subprocess.Popen[Any], url: str, *, timeout_seconds: int) -> tuple[bool, HttpProbe | None, int | None]:
    deadline = time.monotonic() + timeout_seconds
    last_probe: HttpProbe | None = None
    while time.monotonic() < deadline:
        returncode = process.poll()
        last_probe = probe_http("frontend_root", url, timeout=1.0)
        if frontend_ready(last_probe):
            return True, last_probe, returncode
        if returncode is not None:
            return False, last_probe, returncode
        time.sleep(1.0)
    return False, last_probe, process.poll()


def extract_frontend_urls(log_text: str) -> list[str]:
    urls = re.findall(r"https?://[^\s'\"<>]+", log_text)
    cleaned: list[str] = []
    for url in urls:
        url = url.rstrip(".,)")
        if url not in cleaned:
            cleaned.append(url)
    return cleaned[:10]


def sanitize_frontend_log(text: str, project_root: Path | None = None) -> str:
    if not text:
        return ""
    cleaned = text
    if project_root is not None:
        api_base = frontend_effective_env(project_root).get("VITE_API_BASE_URL")
        if api_base and is_secret_key("VITE_API_BASE_URL"):
            cleaned = cleaned.replace(api_base, "***")
    return "\n".join(cleaned.strip().splitlines()[-60:])


def classify_frontend_failure(text: str, default: str) -> str:
    lower = text.lower()
    if "eaddrinuse" in lower or "address already in use" in lower:
        return "frontend_port_conflict"
    if "missing script" in lower or "script not found" in lower:
        return "frontend_script_missing"
    if "cannot find module" in lower or "module not found" in lower:
        return "frontend_dependency_missing"
    if any(token in lower for token in ["econnreset", "etimedout", "eai_again", "enotfound", "socket timeout", "network timeout"]):
        return "dependency_network_unavailable"
    if "npm err!" in lower and "network" in lower:
        return "dependency_network_unavailable"
    if "npm ci" in lower and any(fragment in lower for fragment in ["package-lock", "lock file", "missing from", "can only install"]):
        return "frontend_lockfile_mismatch"
    if "eresolve" in lower or "unable to resolve dependency tree" in lower:
        return "frontend_dependency_conflict"
    if "enoent" in lower and "package.json" in lower:
        return "frontend_package_invalid"
    return default


def command_start_frontend(args: argparse.Namespace) -> int:
    invoked_from = Path.cwd()
    project_root = find_project_root(invoked_from)
    result = build_frontend_result(project_root, invoked_from, mode="start-frontend", dry_run=args.dry_run)
    report_dir: Path | None = None
    if project_root is not None and (not args.no_write_report or not args.dry_run):
        report_dir = create_report_dir(project_root, "start-frontend")
    if project_root is not None:
        add_frontend_preflight_checks(result, project_root)
        if not process_probe_ok(result.node_version):
            result.classification = "missing_prerequisite"
            result.failures.append({"code": "missing_node", "message": "node is not available on PATH."})
            result.next_actions.append("Install Node.js or use a shell where node/npm are available, then rerun start-frontend.")
        elif not process_probe_ok(result.npm_version):
            result.classification = "missing_prerequisite"
            result.failures.append({"code": "missing_npm", "message": "npm is not available on PATH."})
            result.next_actions.append("Install npm or repair PATH, then rerun start-frontend.")
        elif not result.package_scripts.get("dev"):
            result.classification = "frontend_script_missing"
            result.failures.append({"code": "frontend_script_missing", "message": "frontend/package.json does not contain scripts.dev."})
            result.next_actions.append("Restore the frontend dev script before trying to start Vite.")
        elif not result.node_modules_exists:
            result.classification = "frontend_dependencies_missing"
            result.failures.append({"code": "frontend_dependencies_missing", "message": "frontend/node_modules is missing."})
            result.next_actions.append("Run `python tools/devbootstrap.py prepare-frontend` first.")
        elif result.frontend_root_probe and frontend_ready(result.frontend_root_probe):
            result.classification = "frontend_already_running"
            result.actions.append(FrontendAction("start_frontend_noop", "ok", "Frontend root is already reachable; npm run dev was not started."))
            result.next_actions.append("Frontend is reachable. Continue with browser/manual checks or the future smoke phase.")
        elif result.frontend_port_probe and result.frontend_port_probe.open:
            result.classification = "frontend_port_conflict"
            result.failures.append({"code": "frontend_port_conflict", "message": "Frontend port is open but the frontend root probe is not healthy. devbootstrap will not kill a foreign process."})
            result.next_actions.append("Inspect the process on the Vite port manually, or stop the old frontend you own and rerun start-frontend.")
        elif args.dry_run:
            command = ["npm", "run", "dev", "--", "--host", result.frontend_host, "--port", str(result.frontend_port), "--strictPort"]
            result.classification = "frontend_start_planned"
            result.actions.append(FrontendAction("npm_run_dev", "planned", "Would start Vite dev server and wait for frontend root.", command_as_text(command)))
            result.next_actions.append("Run without --dry-run to start frontend.")
        else:
            run_id_value = run_id("start-frontend")
            try:
                process, log_path, command = launch_frontend_process(project_root, report_dir or create_report_dir(project_root, "start-frontend"), result.frontend_host, result.frontend_port)
                result.process_pid = process.pid
                result.process_alive = pid_alive(process.pid)
                result.run_id = run_id_value
                result.log_path = rel(log_path, project_root)
                result.actions.append(FrontendAction("npm_run_dev", "started", "Started frontend process with npm run dev.", command_as_text(command), f"pid={process.pid}"))
                ready, probe, returncode = wait_for_frontend_root(process, result.frontend_url or frontend_root_url(result.frontend_host, result.frontend_port), timeout_seconds=args.timeout_seconds)
                result.frontend_root_probe = probe
                result.process_returncode = returncode
                result.process_alive = pid_alive(process.pid) if returncode is None else False
                result.detected_urls = extract_frontend_urls(read_log_tail(log_path))
                if ready:
                    result.classification = "frontend_started"
                    result.checks.append(FrontendCheck("frontend_root_wait", "ok", "Frontend root became reachable.", f"timeout={args.timeout_seconds}s"))
                    update_process_state(
                        project_root,
                        process_name="frontend",
                        pid=process.pid,
                        cwd=project_root / "frontend",
                        command=command,
                        started_at=result.generated_at,
                        run_id_value=run_id_value,
                        log_path=log_path,
                        report_dir=log_path.parent,
                    )
                    result.next_actions.append("Frontend is running. Continue with browser/manual checks or the future smoke phase.")
                else:
                    log_tail = sanitize_frontend_log(read_log_tail(log_path), project_root)
                    default = "frontend_start_failed" if returncode is not None else "frontend_health_timeout"
                    result.classification = classify_frontend_failure(log_tail, default)
                    result.checks.append(FrontendCheck("frontend_root_wait", "fail", "Frontend root did not become reachable.", f"timeout={args.timeout_seconds}s"))
                    result.failures.append({"code": result.classification, "message": "Frontend did not reach ready state after npm run dev."})
                    if result.process_alive:
                        update_process_state(
                            project_root,
                            process_name="frontend",
                            pid=process.pid,
                            cwd=project_root / "frontend",
                            command=command,
                            started_at=result.generated_at,
                            run_id_value=run_id_value,
                            log_path=log_path,
                            report_dir=log_path.parent,
                        )
                        result.next_actions.append("Frontend process is still alive but root timed out. Inspect frontend.log, then run `python tools/devbootstrap.py stop` if the tracked frontend must be cleaned up.")
                    else:
                        result.next_actions.append("Inspect frontend.log for the classified failure before retrying.")
            except FileNotFoundError:
                result.classification = "missing_prerequisite"
                result.failures.append({"code": "missing_npm", "message": "npm run dev could not be started because npm was not found."})
            except OSError as exc:
                result.classification = "frontend_start_failed"
                result.failures.append({"code": "frontend_start_failed", "message": f"Could not start npm run dev: {exc}"})
    if project_root is not None and report_dir is not None:
        write_frontend_reports(project_root, result, "start-frontend", report_dir)
    print_frontend_summary(result)
    if args.json:
        print("\nJSON:")
        print(json.dumps(as_jsonable(result), ensure_ascii=False, indent=2))
    return 1 if result.failures and not args.dry_run else 0



@dataclass
class SmokeStep:
    name: str
    status: str
    message: str
    classification: str = "unknown"
    command: list[str] = field(default_factory=list)
    returncode: int | None = None
    log_path: str | None = None
    duration_ms: int | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class SmokeResult:
    generated_at: str
    tool_version: str
    project_root: str | None
    invoked_from: str
    level: str
    allow_dev_db_write: bool
    report_dir: str | None = None
    backend_urls: dict[str, str] = field(default_factory=dict)
    frontend_url: str | None = None
    api_base_url: str | None = None
    database_url: DatabaseUrlProbe | None = None
    test_database_url_present: bool = False
    steps: list[SmokeStep] = field(default_factory=list)
    failures: list[dict[str, str]] = field(default_factory=list)
    warnings: list[dict[str, str]] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)
    classification: str = "unknown"


def smoke_command_display(command: list[str]) -> str:
    return " ".join(command)


def smoke_log_path(report_dir: Path, step_name: str, suffix: str = "log") -> Path:
    index = len(list(report_dir.glob("*.log"))) + len(list(report_dir.glob("*.json"))) + 1
    return report_dir / f"{index:02d}_{step_name}.{suffix}"


def write_smoke_probe_log(project_root: Path, report_dir: Path, step_name: str, payload: dict[str, Any]) -> str:
    path = smoke_log_path(report_dir, step_name, "json")
    write_json(path, payload)
    return rel(path, project_root)


def run_smoke_process_step(
    *,
    project_root: Path,
    report_dir: Path,
    name: str,
    command: list[str],
    cwd: Path,
    timeout_seconds: int,
    env_extra: dict[str, str] | None = None,
) -> SmokeStep:
    started = time.monotonic()
    log_path = smoke_log_path(report_dir, name, "log")
    probe = run_process_probe(name, command, cwd=cwd, timeout=timeout_seconds, env_extra=env_extra)
    duration_ms = int((time.monotonic() - started) * 1000)
    stdout = probe.stdout or ""
    stderr = probe.stderr or probe.error or ""
    log_path.write_text(
        "\n".join(
            [
                f"$ {smoke_command_display(command)}",
                f"cwd: {rel(cwd, project_root)}",
                f"exit: {probe.returncode if probe.returncode is not None else probe.error or '<none>'}",
                f"duration_ms: {duration_ms}",
                "",
                "## stdout",
                stdout or "<empty>",
                "",
                "## stderr",
                stderr or "<empty>",
                "",
            ]
        ),
        encoding="utf-8",
    )
    if not probe.available:
        return SmokeStep(
            name=name,
            status="failed",
            message=f"required command is unavailable: {command[0]}",
            classification="missing_prerequisite",
            command=command,
            returncode=probe.returncode,
            log_path=rel(log_path, project_root),
            duration_ms=duration_ms,
        )
    if probe.returncode == 0:
        return SmokeStep(
            name=name,
            status="ok",
            message="step completed",
            classification="ok",
            command=command,
            returncode=probe.returncode,
            log_path=rel(log_path, project_root),
            duration_ms=duration_ms,
        )
    output = "\n".join(part for part in [stdout, stderr] if part)
    if probe.error == "timeout":
        classification = f"{name}_timeout"
        message = f"step timed out after {timeout_seconds}s"
    else:
        classification = classify_smoke_process_failure(name, output)
        message = "step failed; see log"
    return SmokeStep(
        name=name,
        status="failed",
        message=message,
        classification=classification,
        command=command,
        returncode=probe.returncode,
        log_path=rel(log_path, project_root),
        duration_ms=duration_ms,
    )


def classify_smoke_process_failure(name: str, output: str) -> str:
    lower = output.lower()
    if "command not found" in lower or "not found on path" in lower:
        return "missing_prerequisite"
    if "connection refused" in lower or "failed to fetch" in lower or "networkerror" in lower:
        return "runtime_unreachable"
    if "unauthorized" in lower or "authentication is required" in lower:
        return "auth_flow_failed"
    if "playwright" in lower and ("browser" in lower or "install" in lower):
        return "browser_smoke_prerequisite"
    if "failed" in lower or "error" in lower:
        return f"{name}_failed"
    return f"{name}_failed"


def add_smoke_step(result: SmokeResult, step: SmokeStep) -> bool:
    result.steps.append(step)
    if step.status == "failed":
        result.failures.append({"code": step.classification, "message": f"{step.name}: {step.message}"})
        if result.classification == "unknown":
            result.classification = step.classification
        if step.log_path:
            result.next_actions.append(f"Inspect `{step.log_path}` before rerunning `python tools/devbootstrap.py smoke --level {result.level}`.")
        return False
    return True


def smoke_expected_base_url(project_root: Path) -> str:
    frontend_env = frontend_effective_env(project_root)
    api_base = frontend_env.get("VITE_API_BASE_URL")
    if api_base:
        return api_base.rstrip("/")
    host, port, _ = parse_backend_host_port(project_root)
    return f"http://{http_probe_host(host)}:{port}/api/v1"


def build_smoke_result(project_root: Path | None, invoked_from: Path, *, level: str, allow_dev_db_write: bool) -> SmokeResult:
    result = SmokeResult(
        generated_at=iso_now(),
        tool_version=TOOL_VERSION,
        project_root=str(project_root) if project_root else None,
        invoked_from=str(invoked_from),
        level=level,
        allow_dev_db_write=allow_dev_db_write,
    )
    if project_root is None:
        result.classification = "invalid_project_root"
        result.failures.append({"code": "invalid_project_root", "message": "Could not find project root."})
        result.next_actions.append("Run this command from the project root, tools/, backend/ or frontend/ directory.")
        return result

    host, port, _ = parse_backend_host_port(project_root)
    result.backend_urls = backend_health_urls(host, port)
    frontend_host, frontend_port, _ = parse_frontend_host_port(project_root)
    result.frontend_url = frontend_root_url(frontend_host, frontend_port)
    result.api_base_url = smoke_expected_base_url(project_root)
    db_url = os.environ.get("TEST_DATABASE_URL") or backend_effective_env(project_root).get("TEST_DATABASE_URL") or backend_effective_env(project_root).get("DATABASE__URL")
    result.database_url = parse_database_url_probe(db_url)
    result.test_database_url_present = bool(os.environ.get("TEST_DATABASE_URL") or backend_effective_env(project_root).get("TEST_DATABASE_URL"))
    return result


def add_quick_smoke(project_root: Path, report_dir: Path, result: SmokeResult) -> bool:
    host, port, _ = parse_backend_host_port(project_root)
    backend_probes = probe_backend_health(host, port, timeout=2.0)
    frontend_host, frontend_port, _ = parse_frontend_host_port(project_root)
    frontend_url = frontend_root_url(frontend_host, frontend_port)
    frontend_probe = probe_http("frontend_root", frontend_url, timeout=2.0)
    result.backend_urls = backend_health_urls(host, port)
    result.frontend_url = frontend_url
    payload = {
        "backend": as_jsonable(backend_probes),
        "frontend": as_jsonable(frontend_probe),
    }
    log_rel = write_smoke_probe_log(project_root, report_dir, "quick_http", payload)
    backend_ok = backend_health_ready(backend_probes)
    frontend_ok = frontend_ready(frontend_probe)
    if backend_ok and frontend_ok:
        return add_smoke_step(
            result,
            SmokeStep(
                name="quick_http",
                status="ok",
                message="backend health and frontend root are reachable",
                classification="ok",
                log_path=log_rel,
                details={"backend_ok": backend_ok, "frontend_ok": frontend_ok},
            ),
        )
    classification = "runtime_unreachable"
    if not backend_ok and frontend_ok:
        classification = "backend_unreachable"
    elif backend_ok and not frontend_ok:
        classification = "frontend_unreachable"
    return add_smoke_step(
        result,
        SmokeStep(
            name="quick_http",
            status="failed",
            message="backend/frontend HTTP probes are not all healthy",
            classification=classification,
            log_path=log_rel,
            details={"backend_ok": backend_ok, "frontend_ok": frontend_ok},
        ),
    )


def add_smoke_db_guard(project_root: Path, report_dir: Path, result: SmokeResult) -> bool:
    db_probe = result.database_url
    db_name = db_probe.database if db_probe else None
    payload = {
        "testDatabaseUrlPresent": result.test_database_url_present,
        "allowDevDbWrite": result.allow_dev_db_write,
        "database": as_jsonable(db_probe),
        "reason": "backend smoke creates/updates data through the live backend API",
    }
    log_rel = write_smoke_probe_log(project_root, report_dir, "db_write_guard", payload)
    if result.test_database_url_present:
        result.warnings.append(
            {
                "code": "test_database_url_present",
                "message": "TEST_DATABASE_URL is present. Verify the already running backend was started against the intended test database.",
            }
        )
        return add_smoke_step(
            result,
            SmokeStep(
                name="db_write_guard",
                status="ok",
                message="TEST_DATABASE_URL is present; write-capable smoke may proceed",
                classification="ok",
                log_path=log_rel,
                details={"database": db_name},
            ),
        )
    if result.allow_dev_db_write:
        if db_name == "p2p_planner":
            result.warnings.append(
                {
                    "code": "smoke_writes_dev_database",
                    "message": "Smoke is allowed to write to the regular p2p_planner database by explicit --allow-dev-db-write.",
                }
            )
        return add_smoke_step(
            result,
            SmokeStep(
                name="db_write_guard",
                status="ok",
                message="--allow-dev-db-write was provided; write-capable smoke may proceed",
                classification="ok",
                log_path=log_rel,
                details={"database": db_name},
            ),
        )
    return add_smoke_step(
        result,
        SmokeStep(
            name="db_write_guard",
            status="failed",
            message="standard/full smoke may write data; set TEST_DATABASE_URL or pass --allow-dev-db-write",
            classification="smoke_db_write_guard",
            log_path=log_rel,
            details={"database": db_name},
        ),
    )


def add_backend_python_smoke(project_root: Path, report_dir: Path, result: SmokeResult, *, timeout_seconds: int) -> bool:
    smoke_path = project_root / "backend" / "tests" / "smoke_core_api.py"
    if not smoke_path.is_file():
        return add_smoke_step(
            result,
            SmokeStep(
                name="backend_python_smoke",
                status="failed",
                message="backend/tests/smoke_core_api.py is missing",
                classification="backend_smoke_missing",
            ),
        )
    env_extra = {"BASE_URL": (result.api_base_url or smoke_expected_base_url(project_root)).rstrip("/")}
    if os.environ.get("TEST_DATABASE_URL"):
        env_extra["TEST_DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
    step = run_smoke_process_step(
        project_root=project_root,
        report_dir=report_dir,
        name="backend_python_smoke",
        command=[sys.executable, "tests/smoke_core_api.py"],
        cwd=project_root / "backend",
        timeout_seconds=timeout_seconds,
        env_extra=env_extra,
    )
    if step.status == "failed" and step.classification == "backend_python_smoke_failed":
        step.classification = "backend_smoke_failed"
    return add_smoke_step(result, step)


def add_frontend_unit_smoke(project_root: Path, report_dir: Path, result: SmokeResult, *, timeout_seconds: int) -> bool:
    package_data, package_error = read_frontend_package(project_root)
    if package_error:
        return add_smoke_step(
            result,
            SmokeStep("frontend_test_run", "failed", package_error, classification="frontend_package_invalid"),
        )
    scripts = frontend_scripts_from_package(package_data)
    if "test:run" not in scripts:
        return add_smoke_step(
            result,
            SmokeStep("frontend_test_run", "failed", "package.json does not define scripts.test:run", classification="frontend_test_script_missing"),
        )
    step = run_smoke_process_step(
        project_root=project_root,
        report_dir=report_dir,
        name="frontend_test_run",
        command=["npm", "run", "test:run"],
        cwd=project_root / "frontend",
        timeout_seconds=timeout_seconds,
    )
    if step.status == "failed" and step.classification == "frontend_test_run_failed":
        step.classification = "frontend_tests_failed"
    return add_smoke_step(result, step)


def add_browser_smoke(project_root: Path, report_dir: Path, result: SmokeResult, *, timeout_seconds: int) -> bool:
    package_data, package_error = read_frontend_package(project_root)
    if package_error:
        return add_smoke_step(
            result,
            SmokeStep("browser_smoke", "failed", package_error, classification="frontend_package_invalid"),
        )
    scripts = frontend_scripts_from_package(package_data)
    if "test:browser" not in scripts:
        return add_smoke_step(
            result,
            SmokeStep("browser_smoke", "failed", "package.json does not define scripts.test:browser", classification="browser_smoke_script_missing"),
        )
    step = run_smoke_process_step(
        project_root=project_root,
        report_dir=report_dir,
        name="browser_smoke",
        command=["npm", "run", "test:browser"],
        cwd=project_root / "frontend",
        timeout_seconds=timeout_seconds,
    )
    if step.status == "failed" and step.classification == "browser_smoke_failed":
        output_tail = read_log_tail(project_root / step.log_path if step.log_path else None)
        if "playwright" in output_tail.lower() and "install" in output_tail.lower():
            step.classification = "browser_smoke_prerequisite"
    return add_smoke_step(result, step)


def render_smoke_report(result: SmokeResult) -> str:
    lines: list[str] = []
    lines.append("# devbootstrap smoke report")
    lines.append("")
    lines.append(f"- Generated at: `{result.generated_at}`")
    lines.append(f"- Tool version: `{result.tool_version}`")
    lines.append(f"- Project root: `{result.project_root or 'not found'}`")
    lines.append(f"- Invoked from: `{result.invoked_from}`")
    lines.append(f"- Level: `{result.level}`")
    lines.append(f"- Allow dev DB write: `{result.allow_dev_db_write}`")
    lines.append(f"- Classification: `{result.classification}`")
    lines.append("")
    lines.append("## Runtime targets")
    lines.append("")
    for name, url in result.backend_urls.items():
        lines.append(f"- `{name}`: `{url}`")
    if result.frontend_url:
        lines.append(f"- `frontend`: `{result.frontend_url}`")
    if result.api_base_url:
        lines.append(f"- `api base`: `{result.api_base_url}`")
    if result.database_url:
        lines.append(f"- `database`: `{result.database_url.masked_url or '<missing>'}`")
        lines.append(f"- `database name`: `{result.database_url.database or '<unknown>'}`")
    lines.append(f"- `TEST_DATABASE_URL present`: `{result.test_database_url_present}`")
    lines.append("")
    lines.append("## Steps")
    lines.append("")
    lines.append("| Step | Status | Classification | Return | Duration | Log | Message |")
    lines.append("|---|---|---|---:|---:|---|---|")
    for step in result.steps:
        ret = "" if step.returncode is None else str(step.returncode)
        duration = "" if step.duration_ms is None else str(step.duration_ms)
        log = f"`{step.log_path}`" if step.log_path else ""
        lines.append(f"| `{step.name}` | {step.status} | `{step.classification}` | {ret} | {duration} ms | {log} | {step.message} |")
    lines.append("")
    lines.append("## Findings")
    lines.append("")
    if not result.failures and not result.warnings:
        lines.append("- No blocking findings from smoke gates.")
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
    elif result.classification == "ok":
        lines.append("- Smoke gates passed for the selected level.")
    else:
        lines.append("- Inspect the step logs above and rerun smoke after fixing the classified issue.")
    lines.append("")
    return "\n".join(lines)


def write_smoke_reports(project_root: Path, result: SmokeResult, report_dir: Path, run_id_value: str) -> None:
    result.report_dir = rel(report_dir, project_root)
    write_report_json(report_dir / "smoke.json", result, command="smoke")
    (report_dir / "report.md").write_text(render_smoke_report(result), encoding="utf-8")
    append_report_to_state(project_root, report_dir, run_id_value)


def print_smoke_summary(result: SmokeResult) -> None:
    print_header("devbootstrap smoke")
    print(f"Tool version: {result.tool_version}")
    print(f"Project root: {result.project_root or 'not found'}")
    print(f"Level: {result.level}")
    print(f"Classification: {result.classification}")
    if result.backend_urls or result.frontend_url:
        print("\nRuntime targets:")
        for name, url in result.backend_urls.items():
            print(f"  - {name}: {url}")
        if result.frontend_url:
            print(f"  - frontend: {result.frontend_url}")
    print("\nSteps:")
    for step in result.steps:
        suffix = f" — {step.log_path}" if step.log_path else ""
        print(f"  - {step.status.upper()} {step.name}: {step.message}{suffix}")
    if result.failures or result.warnings:
        print("\nFindings:")
        for failure in result.failures:
            print(f"  - FAIL {failure['code']}: {failure['message']}")
        for warning in result.warnings:
            print(f"  - WARN {warning['code']}: {warning['message']}")
    else:
        print("\nFindings: no blocking findings from smoke gates")
    if result.next_actions:
        print("\nNext safe actions:")
        for action in result.next_actions:
            print(f"  - {action}")
    if result.report_dir:
        print(f"\nReport: {result.report_dir}/report.md")


def command_smoke(args: argparse.Namespace) -> int:
    invoked_from = Path.cwd()
    project_root = find_project_root(invoked_from)
    result = build_smoke_result(project_root, invoked_from, level=args.level, allow_dev_db_write=args.allow_dev_db_write)
    report_dir: Path | None = None
    if project_root is not None:
        if args.no_write_report:
            report_dir = Path(tempfile.mkdtemp(prefix="devbootstrap-smoke-"))
        else:
            smoke_run_id = run_id("smoke")
            report_dir = project_root / BOOTSTRAP_DIR_NAME / "runs" / smoke_run_id
            report_dir.mkdir(parents=True, exist_ok=False)
            result.report_dir = rel(report_dir, project_root)

    keep_going = not result.failures and project_root is not None and report_dir is not None
    if keep_going:
        keep_going = add_quick_smoke(project_root, report_dir, result)
    if keep_going and args.level in {"standard", "full"}:
        keep_going = add_smoke_db_guard(project_root, report_dir, result)
    if keep_going and args.level in {"standard", "full"}:
        keep_going = add_backend_python_smoke(project_root, report_dir, result, timeout_seconds=args.timeout_seconds)
    if keep_going and args.level in {"standard", "full"}:
        keep_going = add_frontend_unit_smoke(project_root, report_dir, result, timeout_seconds=args.timeout_seconds)
    if keep_going and args.level == "full":
        keep_going = add_browser_smoke(project_root, report_dir, result, timeout_seconds=args.timeout_seconds)

    if result.classification == "unknown":
        result.classification = "ok" if keep_going else "failed"
    if result.classification == "ok":
        result.next_actions.append("Selected smoke gates passed. Continue manual validation or run a higher --level if needed.")
    if project_root is not None and report_dir is not None and not args.no_write_report:
        write_smoke_reports(project_root, result, report_dir, smoke_run_id)
    print_smoke_summary(result)
    if args.json:
        print("\nJSON:")
        print(json.dumps(as_jsonable(result), ensure_ascii=False, indent=2))
    return 1 if result.failures else 0


@dataclass
class UpStep:
    name: str
    status: str
    message: str
    command: list[str] = field(default_factory=list)
    returncode: int | None = None
    log_path: str | None = None
    duration_ms: int | None = None
    blocking: bool = True
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class UpResult:
    generated_at: str
    tool_version: str
    project_root: str | None
    invoked_from: str
    dry_run: bool
    smoke_level: str
    yes: bool
    run_id: str
    report_dir: str | None = None
    backend_urls: dict[str, str] = field(default_factory=dict)
    frontend_url: str | None = None
    steps: list[UpStep] = field(default_factory=list)
    failures: list[dict[str, str]] = field(default_factory=list)
    warnings: list[dict[str, str]] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)
    classification: str = "unknown"


def append_report_to_state(project_root: Path, report_dir: Path, run_id_value: str) -> None:
    state_path = project_root / BOOTSTRAP_DIR_NAME / "state.json"
    state = read_json(state_path)
    if "_error" in state:
        state = {}
    state["version"] = STATE_VERSION
    state["activeRunId"] = run_id_value
    processes = state.get("processes") if isinstance(state.get("processes"), dict) else {}
    state["processes"] = processes
    last_reports = state.get("lastReports") if isinstance(state.get("lastReports"), list) else []
    last_reports.append(rel(report_dir, project_root))
    state["lastReports"] = last_reports[-20:]
    state_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(state_path, state)


def up_command_display(command: list[str]) -> str:
    return " ".join(command)


def run_up_subcommand(
    *,
    project_root: Path,
    report_dir: Path,
    step_name: str,
    command: list[str],
    timeout_seconds: int,
) -> UpStep:
    started = time.monotonic()
    log_path = report_dir / f"{len(list(report_dir.glob('*.log'))) + 1:02d}_{step_name}.log"
    full_command = [sys.executable, str(project_root / "tools" / "devbootstrap.py"), *command]
    try:
        completed = subprocess.run(
            full_command,
            cwd=str(project_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            check=False,
        )
        stdout = safe_decode(completed.stdout)
        stderr = safe_decode(completed.stderr)
        duration_ms = int((time.monotonic() - started) * 1000)
        log_path.write_text(
            "\n".join(
                [
                    f"$ {up_command_display(full_command)}",
                    f"cwd: {project_root}",
                    f"exit: {completed.returncode}",
                    f"duration_ms: {duration_ms}",
                    "",
                    "## stdout",
                    stdout or "<empty>",
                    "",
                    "## stderr",
                    stderr or "<empty>",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        status = "ok" if completed.returncode == 0 else "failed"
        message = "step completed" if completed.returncode == 0 else "step failed; see log"
        return UpStep(
            name=step_name,
            status=status,
            message=message,
            command=full_command,
            returncode=completed.returncode,
            log_path=rel(log_path, project_root),
            duration_ms=duration_ms,
        )
    except subprocess.TimeoutExpired as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        log_path.write_text(
            "\n".join(
                [
                    f"$ {up_command_display(full_command)}",
                    f"cwd: {project_root}",
                    "exit: timeout",
                    f"duration_ms: {duration_ms}",
                    "",
                    "## stdout",
                    safe_decode(exc.stdout) or "<empty>",
                    "",
                    "## stderr",
                    safe_decode(exc.stderr) or "<empty>",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return UpStep(
            name=step_name,
            status="failed",
            message=f"step timed out after {timeout_seconds}s; see log",
            command=full_command,
            returncode=None,
            log_path=rel(log_path, project_root),
            duration_ms=duration_ms,
        )
    except OSError as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        log_path.write_text(
            f"$ {up_command_display(full_command)}\ncwd: {project_root}\nerror: {exc}\n",
            encoding="utf-8",
        )
        return UpStep(
            name=step_name,
            status="failed",
            message=f"could not execute step: {exc}",
            command=full_command,
            returncode=None,
            log_path=rel(log_path, project_root),
            duration_ms=duration_ms,
        )


def add_up_step(result: UpResult, step: UpStep) -> bool:
    result.steps.append(step)
    if step.status == "failed":
        result.failures.append({"code": f"up_{step.name}_failed", "message": step.message})
        result.classification = f"failed_at_{step.name}"
        result.next_actions.append(f"Inspect `{step.log_path}` and rerun `python tools/devbootstrap.py {step.name.replace('_', '-')}` or `up` after fixing the issue.")
        return False
    if step.status == "warn":
        result.warnings.append({"code": f"up_{step.name}_warning", "message": step.message})
    return True


def add_up_skipped_step(result: UpResult, name: str, message: str) -> None:
    result.steps.append(UpStep(name=name, status="skipped", message=message, blocking=False))


def run_up_smoke(project_root: Path, report_dir: Path, result: UpResult, *, dry_run: bool, allow_dev_db_write: bool, timeout_seconds: int) -> bool:
    if result.smoke_level == "none":
        add_up_skipped_step(result, "smoke", "smoke-level=none; smoke gates skipped")
        return True
    if dry_run:
        result.steps.append(UpStep("smoke", "planned", f"would run smoke --level {result.smoke_level}", blocking=True))
        return True
    command = ["smoke", "--level", result.smoke_level, "--no-write-report", "--json", "--timeout-seconds", str(timeout_seconds)]
    if allow_dev_db_write:
        command.append("--allow-dev-db-write")
    step = run_up_subcommand(
        project_root=project_root,
        report_dir=report_dir,
        step_name="smoke",
        command=command,
        timeout_seconds=timeout_seconds + 30,
    )
    return add_up_step(result, step)


def render_up_report(result: UpResult) -> str:
    lines: list[str] = []
    lines.append("# devbootstrap up report")
    lines.append("")
    lines.append(f"- Generated at: `{result.generated_at}`")
    lines.append(f"- Tool version: `{result.tool_version}`")
    lines.append(f"- Project root: `{result.project_root or 'not found'}`")
    lines.append(f"- Invoked from: `{result.invoked_from}`")
    lines.append(f"- Run ID: `{result.run_id}`")
    lines.append(f"- Dry run: `{result.dry_run}`")
    lines.append(f"- Smoke level: `{result.smoke_level}`")
    lines.append(f"- Classification: `{result.classification}`")
    if result.backend_urls:
        lines.append("")
        lines.append("## Runtime URLs")
        lines.append("")
        for name, url in result.backend_urls.items():
            lines.append(f"- `{name}`: `{url}`")
        if result.frontend_url:
            lines.append(f"- `frontend`: `{result.frontend_url}`")
    lines.append("")
    lines.append("## Pipeline steps")
    lines.append("")
    lines.append("| Step | Status | Return | Duration | Log | Message |")
    lines.append("|---|---|---:|---:|---|---|")
    for step in result.steps:
        ret = "" if step.returncode is None else str(step.returncode)
        duration = "" if step.duration_ms is None else str(step.duration_ms)
        log = f"`{step.log_path}`" if step.log_path else ""
        lines.append(f"| `{step.name}` | {step.status} | {ret} | {duration} ms | {log} | {step.message} |")
    lines.append("")
    lines.append("## Findings")
    lines.append("")
    if not result.failures and not result.warnings:
        lines.append("- No blocking findings from up pipeline.")
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
    elif result.classification == "ok":
        lines.append("- Open the frontend URL and continue manual development checks.")
        lines.append("- Use `python tools/devbootstrap.py status` to inspect tracked processes.")
    else:
        lines.append("- Inspect the step logs above and rerun `python tools/devbootstrap.py up` after fixing the issue.")
    lines.append("")
    return "\n".join(lines)


def write_up_reports(project_root: Path, result: UpResult, report_dir: Path) -> None:
    result.report_dir = rel(report_dir, project_root)
    write_report_json(report_dir / "up.json", result, command="up")
    (report_dir / "report.md").write_text(render_up_report(result), encoding="utf-8")
    append_report_to_state(project_root, report_dir, result.run_id)


def print_up_summary(result: UpResult) -> None:
    print_header("devbootstrap up")
    print(f"Tool version: {result.tool_version}")
    print(f"Project root: {result.project_root or 'not found'}")
    print(f"Classification: {result.classification}")
    print(f"Dry run: {result.dry_run}")
    if result.backend_urls or result.frontend_url:
        print("\nRuntime URLs:")
        for name, url in result.backend_urls.items():
            print(f"  - {name}: {url}")
        if result.frontend_url:
            print(f"  - frontend: {result.frontend_url}")
    print("\nSteps:")
    for step in result.steps:
        suffix = f" — {step.log_path}" if step.log_path else ""
        print(f"  - {step.status.upper()} {step.name}: {step.message}{suffix}")
    if result.failures or result.warnings:
        print("\nFindings:")
        for failure in result.failures:
            print(f"  - FAIL {failure['code']}: {failure['message']}")
        for warning in result.warnings:
            print(f"  - WARN {warning['code']}: {warning['message']}")
    else:
        print("\nFindings: no blocking findings from up pipeline")
    if result.next_actions:
        print("\nNext safe actions:")
        for action in result.next_actions:
            print(f"  - {action}")
    if result.report_dir:
        print(f"\nReport: {result.report_dir}/report.md")


def command_up(args: argparse.Namespace) -> int:
    invoked_from = Path.cwd()
    project_root = find_project_root(invoked_from)
    run_id_value = run_id("up")
    result = UpResult(
        generated_at=iso_now(),
        tool_version=TOOL_VERSION,
        project_root=str(project_root) if project_root else None,
        invoked_from=str(invoked_from),
        dry_run=args.dry_run,
        smoke_level=args.smoke_level,
        yes=args.yes,
        run_id=run_id_value,
    )
    if project_root is None:
        result.classification = "invalid_project_root"
        result.failures.append({"code": "invalid_project_root", "message": "Could not find project root."})
        result.next_actions.append("Run this command from the project root, tools/, backend/ or frontend/ directory.")
        print_up_summary(result)
        if args.json:
            print("\nJSON:")
            print(json.dumps(as_jsonable(result), ensure_ascii=False, indent=2))
        return 1

    report_dir = project_root / BOOTSTRAP_DIR_NAME / "runs" / run_id_value
    report_dir.mkdir(parents=True, exist_ok=False)
    result.report_dir = rel(report_dir, project_root)

    timeout = max(30, args.step_timeout_seconds)
    pipeline: list[tuple[str, list[str], int]] = [
        ("diagnose", ["diagnose", "--no-write-report", "--json"], timeout),
        ("plan", ["plan", "--no-write-report", "--json"], timeout),
    ]

    if args.dry_run:
        pipeline.append(("prepare_env", ["plan", "--no-write-report", "--json"], timeout))
    else:
        pipeline.append(("prepare_env", ["prepare-env", "--no-write-report", "--json"], timeout))

    if args.skip_db_start:
        pipeline.append(("start_db", ["__skip__", "--skip-db-start was provided"], 0))
    else:
        command = ["start-db", "--no-write-report", "--json", "--timeout-seconds", str(args.db_timeout_seconds)]
        if args.dry_run:
            command.insert(1, "--dry-run")
        pipeline.append(("start_db", command, args.db_timeout_seconds + 30))

    if args.skip_cargo_check:
        pipeline.append(("check_backend", ["__skip__", "--skip-cargo-check was provided"], 0))
    else:
        command = ["check-backend", "--no-write-report", "--json", "--timeout-seconds", str(args.cargo_check_timeout_seconds)]
        if args.dry_run:
            command.insert(1, "--dry-run")
        pipeline.append(("check_backend", command, args.cargo_check_timeout_seconds + 30))

    if args.skip_backend_start:
        pipeline.append(("start_backend", ["__skip__", "--skip-backend-start was provided"], 0))
    else:
        command = ["start-backend", "--no-write-report", "--json", "--timeout-seconds", str(args.backend_timeout_seconds)]
        if args.dry_run:
            command.insert(1, "--dry-run")
        pipeline.append(("start_backend", command, args.backend_timeout_seconds + 30))

    if args.skip_install:
        pipeline.append(("prepare_frontend", ["__skip__", "--skip-install was provided"], 0))
    else:
        command = ["prepare-frontend", "--no-write-report", "--json", "--timeout-seconds", str(args.npm_timeout_seconds)]
        if args.dry_run:
            command.insert(1, "--dry-run")
        pipeline.append(("prepare_frontend", command, args.npm_timeout_seconds + 30))

    if args.skip_frontend_start:
        pipeline.append(("start_frontend", ["__skip__", "--skip-frontend-start was provided"], 0))
    else:
        command = ["start-frontend", "--no-write-report", "--json", "--timeout-seconds", str(args.frontend_timeout_seconds)]
        if args.dry_run:
            command.insert(1, "--dry-run")
        pipeline.append(("start_frontend", command, args.frontend_timeout_seconds + 30))

    keep_going = True
    for step_name, command, step_timeout in pipeline:
        if not keep_going:
            add_up_skipped_step(result, step_name, "skipped because an earlier blocking step failed")
            continue
        if command and command[0] == "__skip__":
            add_up_skipped_step(result, step_name, command[1] if len(command) > 1 else "step skipped")
            continue
        step = run_up_subcommand(
            project_root=project_root,
            report_dir=report_dir,
            step_name=step_name,
            command=command,
            timeout_seconds=step_timeout,
        )
        if args.dry_run and step_name == "prepare_env" and step.status == "ok":
            step.status = "planned"
            step.message = "would create missing env files from examples; see env plan log"
        keep_going = add_up_step(result, step)

    if keep_going:
        keep_going = run_up_smoke(
            project_root,
            report_dir,
            result,
            dry_run=args.dry_run,
            allow_dev_db_write=args.allow_dev_db_write,
            timeout_seconds=args.smoke_timeout_seconds,
        )
    else:
        add_up_skipped_step(result, "smoke", "skipped because an earlier blocking step failed")

    if result.classification == "unknown":
        result.classification = "dry_run" if args.dry_run else "ok"
    if result.classification == "ok":
        host, port, _ = parse_backend_host_port(project_root)
        result.backend_urls = backend_health_urls(host, port)
        frontend_host, frontend_port, _ = parse_frontend_host_port(project_root)
        result.frontend_url = frontend_root_url(frontend_host, frontend_port)
        result.next_actions.append("Backend and frontend look alive. Continue manual checks or run `python tools/devbootstrap.py smoke --level standard`.")
    write_up_reports(project_root, result, report_dir)
    print_up_summary(result)
    if args.json:
        print("\nJSON:")
        print(json.dumps(as_jsonable(result), ensure_ascii=False, indent=2))
    return 1 if result.failures and not args.dry_run else 0


@dataclass
class GateSpec:
    name: str
    cwd: str
    command: list[str] = field(default_factory=list)
    description: str = ""
    required: bool = True
    timeout_seconds: int = TIMEOUT_POLICY["release_gate"]
    env_extra: dict[str, str] = field(default_factory=dict)
    not_implemented_reason: str | None = None
    skip_reason: str | None = None
    skip_status: str = "skipped_prerequisite"
    skip_classification: str = "skipped_prerequisite"
    internal_check: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class GateResult:
    name: str
    status: str
    classification: str
    message: str
    cwd: str
    command: list[str] = field(default_factory=list)
    required: bool = True
    returncode: int | None = None
    duration_ms: int | None = None
    log_path: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ManagedTestDatabaseState:
    enabled: bool
    retention: str
    run_id: str
    status: str = "disabled"
    classification: str = "disabled"
    message: str = "managed test database is disabled"
    backend: str = "native-psql"
    created_at: str | None = None
    source: str | None = None
    database_name: str | None = None
    database_url: str | None = None
    masked_database_url: str | None = None
    maintenance_url: str | None = None
    masked_maintenance_url: str | None = None
    metadata_path: str | None = None
    cleanup_command: str | None = None
    create_command: list[str] = field(default_factory=list)
    drop_command: list[str] = field(default_factory=list)
    dump_command: list[str] = field(default_factory=list)
    dump_path: str | None = None
    retained: bool | None = None
    failure_code: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReleaseGatesManagedRuntimeProcess:
    name: str
    process: subprocess.Popen[Any]
    log_path: Path
    command: list[str]
    cwd: Path
    host: str
    port: int
    url: str


@dataclass
class ManagedRuntimeState:
    enabled: bool
    run_id: str
    status: str = "disabled"
    classification: str = "disabled"
    message: str = "managed runtime is disabled"
    backend_host: str = "127.0.0.1"
    backend_port: int | None = None
    frontend_host: str = "127.0.0.1"
    frontend_port: int | None = None
    backend_api_base_url: str | None = None
    backend_health_url: str | None = None
    frontend_url: str | None = None
    database_source: str | None = None
    masked_database_url: str | None = None
    started_at: str | None = None
    stopped_at: str | None = None
    backend_pid: int | None = None
    frontend_pid: int | None = None
    runtime_state_path: str | None = None
    env_diff_path: str | None = None
    managed_urls_path: str | None = None
    backend_log_path: str | None = None
    frontend_log_path: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReleaseGatesResult:
    generated_at: str
    tool_version: str
    project_root: str | None
    invoked_from: str
    run_id: str
    dry_run: bool
    timeout_seconds: int
    report_dir: str | None = None
    archive_path: str | None = None
    managed_test_db: ManagedTestDatabaseState | None = None
    managed_runtime: ManagedRuntimeState | None = None
    overall_status: str = "unknown"
    classification: str = "unknown"
    gates: list[GateResult] = field(default_factory=list)
    findings: list[dict[str, str]] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)


RELEASE_GATES_ARCHIVE_EXCLUDED_PARTS = {
    ".git",
    ".venv",
    "node_modules",
    "target",
    "dist",
    "build",
    "coverage",
    "__pycache__",
    ".pytest_cache",
}
RELEASE_GATES_ARCHIVE_EXCLUDED_NAMES = {".env"}
RELEASE_GATES_ARCHIVE_EXCLUDED_SUFFIXES = (".pyc", ".pyo", ".sqlite", ".sqlite3", ".db", ".tsbuildinfo")
CLEAN_MACHINE_PROFILES = ("dry", "deps", "runtime", "clean-machine-dry", "clean-machine-deps", "clean-machine-runtime")
CLEAN_MACHINE_RETENTION_POLICIES = ("delete-always", "keep-on-failure", "keep-always")
DEFAULT_CLEAN_MACHINE_PROFILE = "dry"
DEFAULT_CLEAN_MACHINE_RETENTION = "keep-on-failure"
CLEAN_MACHINE_REQUIRED_PATHS = [
    "backend/Cargo.toml",
    "backend/build.rs",
    "backend/migrations",
    "frontend/package.json",
    "frontend/package-lock.json",
    "docker-compose.dev.yml",
    "README.md",
    "tools/devbootstrap.py",
]


def release_gate_command_display(command: list[str]) -> str:
    return " ".join(command)


def release_gate_log_path(logs_dir: Path, index: int, step_name: str) -> Path:
    safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", step_name).strip("._") or "gate"
    return logs_dir / f"{index:02d}_{safe_name}.log"


def release_gate_sanitize_output(project_root: Path | None, text: str) -> str:
    if not text:
        return ""
    cleaned = text
    values: dict[str, str] = {}
    if project_root is not None:
        for relative in ["backend/.env", "backend/.env.example", "frontend/.env.local", "frontend/.env.example"]:
            parsed, _ = parse_env_file(project_root / relative)
            values.update(parsed)
    for key, value in os.environ.items():
        if is_secret_key(key):
            values.setdefault(key, value)
    for key, value in values.items():
        if not value:
            continue
        masked = mask_value(key, value)
        if masked != value:
            cleaned = cleaned.replace(value, masked)
            if key.upper() in {"DATABASE__URL", "DATABASE_URL"}:
                try:
                    parsed = urllib.parse.urlsplit(value)
                    if parsed.password:
                        cleaned = cleaned.replace(urllib.parse.unquote(parsed.password), "***")
                except Exception:
                    pass
    cleaned = re.sub(r"(postgres(?:ql)?://[^:\s/@]+:)[^@\s]+(@)", r"\1***\2", cleaned)
    return cleaned


def rust_test_output_has_ignored_tests(output: str) -> bool:
    for match in re.finditer(r"(?:^|[;\s])([1-9]\d*)\s+ignored\b", output, flags=re.IGNORECASE | re.MULTILINE):
        try:
            if int(match.group(1)) > 0:
                return True
        except ValueError:
            continue
    return False


def classify_gate_output(name: str, stdout: str, stderr: str, error: str | None, returncode: int | None) -> tuple[str, str, str]:
    output = "\n".join(part for part in [stdout, stderr, error or ""] if part)
    lower = output.lower()
    if error == "timeout":
        return "timeout", f"{name}_timeout", "gate timed out"
    if returncode == 0:
        if "test result:" in lower and rust_test_output_has_ignored_tests(output):
            return "partial_pass", "critical_tests_ignored", "command exited 0, but one or more Rust tests were ignored"
        return "ok", "ok", "gate completed"
    if "playwright" in lower and ("browser" in lower or "install" in lower or "executable doesn't exist" in lower or "please run" in lower):
        return "infra_failed", "browser_smoke_prerequisite", "Playwright browser prerequisite appears to be missing"
    if name in {"frontend_prepare_dependencies", "playwright_install", "backend_dependency_warmup"} and any(token in lower for token in ["econnreset", "etimedout", "eai_again", "enotfound", "socket timeout", "network timeout", "failed to download"]):
        return "infra_failed", "dependency_network_unavailable", "dependency network/cache prerequisite is unavailable"
    if name == "frontend_prepare_dependencies" and "npm ci" in lower and any(fragment in lower for fragment in ["package-lock", "lock file", "missing from", "can only install"]):
        return "infra_failed", "frontend_lockfile_mismatch", "frontend lockfile is out of sync with package.json"
    if "command not found" in lower or "not found on path" in lower or "no such file or directory" in lower:
        return "infra_failed", "missing_prerequisite", "required command or file is unavailable"
    if "connection refused" in lower or "networkerror" in lower or "failed to fetch" in lower:
        return "infra_failed", "runtime_unreachable", "runtime prerequisite is unreachable"
    return "failed", f"{name}_failed", "gate failed; see log"


def run_gate_process_step(
    *,
    project_root: Path,
    logs_dir: Path,
    index: int,
    spec: GateSpec,
    timeout_seconds: int,
    dry_run: bool = False,
) -> GateResult:
    log_path = release_gate_log_path(logs_dir, index, spec.name)
    cwd = project_root / spec.cwd if spec.cwd else project_root
    if spec.skip_reason:
        message = spec.skip_reason
        log_path.write_text(
            "\n".join(
                [
                    f"# {spec.name}",
                    f"status: {spec.skip_status}",
                    f"classification: {spec.skip_classification}",
                    f"cwd: {spec.cwd or '.'}",
                    f"reason: {message}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return GateResult(
            name=spec.name,
            status=spec.skip_status,
            classification=spec.skip_classification,
            message=message,
            cwd=spec.cwd or ".",
            command=spec.command,
            required=spec.required,
            log_path=rel(log_path, project_root),
            details=spec.details,
        )
    if spec.not_implemented_reason:
        message = spec.not_implemented_reason
        log_path.write_text(
            "\n".join(
                [
                    f"# {spec.name}",
                    "status: not_implemented",
                    f"cwd: {spec.cwd or '.'}",
                    f"reason: {message}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return GateResult(
            name=spec.name,
            status="not_implemented",
            classification="not_implemented",
            message=message,
            cwd=spec.cwd or ".",
            command=spec.command,
            required=spec.required,
            log_path=rel(log_path, project_root),
            details=spec.details,
        )
    if dry_run:
        command_text = release_gate_command_display(spec.command) if spec.command else f"internal:{spec.internal_check or spec.name}"
        log_path.write_text(
            "\n".join(
                [
                    f"$ {command_text}",
                    f"cwd: {spec.cwd or '.'}",
                    "status: planned",
                    "reason: --dry-run was provided; command was not executed",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return GateResult(
            name=spec.name,
            status="planned",
            classification="dry_run",
            message="would run gate command",
            cwd=spec.cwd or ".",
            command=spec.command,
            required=spec.required,
            log_path=rel(log_path, project_root),
            details=spec.details,
        )
    if spec.internal_check:
        return run_release_gate_internal_step(
            project_root=project_root,
            logs_dir=logs_dir,
            index=index,
            spec=spec,
            timeout_seconds=timeout_seconds,
        )
    started = time.monotonic()
    env_extra = {"PYTHONDONTWRITEBYTECODE": "1"}
    env_extra.update(spec.env_extra)
    probe = run_process_probe(spec.name, spec.command, cwd=cwd, timeout=timeout_seconds, env_extra=env_extra)
    duration_ms = int((time.monotonic() - started) * 1000)
    stdout = release_gate_sanitize_output(project_root, probe.stdout or "")
    stderr = release_gate_sanitize_output(project_root, probe.stderr or probe.error or "")
    status, classification, message = classify_gate_output(spec.name, stdout, stderr, probe.error, probe.returncode)
    if not probe.available:
        status, classification, message = "infra_failed", "missing_prerequisite", f"required command is unavailable: {spec.command[0]}"
    log_path.write_text(
        "\n".join(
            [
                f"$ {release_gate_command_display(spec.command)}",
                f"cwd: {spec.cwd or '.'}",
                f"exit: {probe.returncode if probe.returncode is not None else probe.error or '<none>'}",
                f"duration_ms: {duration_ms}",
                f"status: {status}",
                f"classification: {classification}",
                "",
                "## stdout",
                stdout or "<empty>",
                "",
                "## stderr",
                stderr or "<empty>",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return GateResult(
        name=spec.name,
        status=status,
        classification=classification,
        message=message,
        cwd=spec.cwd or ".",
        command=spec.command,
        required=spec.required,
        returncode=probe.returncode,
        duration_ms=duration_ms,
        log_path=rel(log_path, project_root),
        details=spec.details,
    )



def postgres_quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def release_gate_safe_managed_db_name(tool_version: str, run_id_value: str) -> str:
    version = re.sub(r"[^a-zA-Z0-9]+", "_", tool_version).strip("_").lower() or "tool"
    timestamp = now_utc().strftime("%Y%m%d_%H%M%S")
    digest = hashlib.sha256(f"{run_id_value}|{timestamp}|{os.getpid()}".encode("utf-8")).hexdigest()[:8]
    name = f"p2pkanban_rg_{version}_{timestamp}_{digest}"
    return re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_")[:63]


def release_gate_database_url_source(project_root: Path) -> tuple[str | None, str | None]:
    for key in ["DATABASE__URL", "DATABASE_URL"]:
        value = os.environ.get(key)
        if value:
            return value, f"environment {key}"
    backend_values = backend_effective_env(project_root)
    for key in ["DATABASE__URL", "DATABASE_URL"]:
        value = backend_values.get(key)
        if value:
            return value, f"backend effective env {key}"
    return None, None


def replace_database_name_in_url(value: str, database_name: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    path = "/" + urllib.parse.quote(database_name, safe="")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, parsed.fragment))


def release_gate_managed_db_env(database_url: str) -> dict[str, str]:
    return {
        "DATABASE__URL": database_url,
        "DATABASE_URL": database_url,
        "TEST_DATABASE_URL": database_url,
    }


def release_gate_managed_db_cleanup_command(maintenance_url: str, database_name: str) -> str:
    env = psql_env_from_database_url(maintenance_url)
    visible_env = []
    for key in ["PGHOST", "PGPORT", "PGUSER", "PGDATABASE"]:
        if env.get(key):
            visible_env.append(f"{key}={env[key]}")
    quoted = postgres_quote_identifier(database_name)
    sql = f"DROP DATABASE IF EXISTS {quoted};"
    return " ".join([*visible_env, "psql", "-X", "-v", "ON_ERROR_STOP=1", "-c", repr(sql)]).strip()



def managed_test_db_public_payload(state: ManagedTestDatabaseState) -> dict[str, Any]:
    payload = as_jsonable(state)
    # Raw PostgreSQL URLs may contain passwords. Reports and patchable bundles should only
    # expose masked URLs; the live in-memory state keeps raw URLs only for subprocess env.
    payload["database_url"] = state.masked_database_url
    payload["maintenance_url"] = state.masked_maintenance_url
    details = payload.get("details")
    if isinstance(details, dict):
        for key in ["databaseUrl", "maintenanceUrl"]:
            if key in details and isinstance(details[key], str):
                details[key] = mask_database_url(details[key])
    return payload


def classify_managed_db_psql_failure(probe: ProcessProbe, db_url: str | None) -> str:
    text = sanitize_postgres_output("\n".join(part for part in [probe.stderr, probe.stdout, probe.error or ""] if part), db_url).lower()
    if not probe.available:
        return "postgres_client_missing"
    if "permission denied to create database" in text or "must be member" in text or "permission denied" in text:
        return "postgres_createdb_permission_denied"
    if "password authentication failed" in text or "authentication failed" in text or ("role" in text and "does not exist" in text):
        return "postgres_auth_failed"
    if "could not connect" in text or "connection refused" in text or "no such file" in text:
        return "postgres_unavailable"
    if "timeout" in text:
        return "postgres_connect_timeout"
    if "already exists" in text:
        return "managed_test_db_name_collision"
    return "managed_test_db_psql_failed"


def build_release_gates_managed_test_database(
    project_root: Path,
    run_dir: Path,
    *,
    run_id_value: str,
    retention: str,
    dry_run: bool,
    start_db_if_needed: bool,
) -> ManagedTestDatabaseState:
    state = ManagedTestDatabaseState(enabled=True, retention=retention, run_id=run_id_value, created_at=iso_now())
    metadata_path = run_dir / "managed-test-db.json"
    state.metadata_path = rel(metadata_path, project_root)

    source_url, source = release_gate_database_url_source(project_root)
    state.source = source
    if not source_url:
        state.status = "infra_failed"
        state.classification = "managed_test_db_source_missing"
        state.message = "DATABASE__URL/DATABASE_URL is absent; cannot derive PostgreSQL connection target for managed test DB."
        return state

    source_probe = parse_database_url_probe(source_url)
    state.details["sourceUrl"] = source_probe.masked_url
    state.details["sourceWarnings"] = source_probe.warnings
    if source_probe.warnings or source_probe.scheme not in {"postgres", "postgresql"}:
        state.status = "infra_failed"
        state.classification = "managed_test_db_source_invalid"
        state.message = "DATABASE__URL/DATABASE_URL is not a complete PostgreSQL URL."
        return state

    database_name = release_gate_safe_managed_db_name(TOOL_VERSION, run_id_value)
    database_url = replace_database_name_in_url(source_url, database_name)
    maintenance_url = replace_database_name_in_url(source_url, "postgres")
    state.database_name = database_name
    state.database_url = database_url
    state.masked_database_url = mask_database_url(database_url)
    state.maintenance_url = maintenance_url
    state.masked_maintenance_url = mask_database_url(maintenance_url)
    state.cleanup_command = release_gate_managed_db_cleanup_command(maintenance_url, database_name)
    create_sql = f"CREATE DATABASE {postgres_quote_identifier(database_name)};"
    state.create_command = ["psql", "-X", "-v", "ON_ERROR_STOP=1", "-Atc", create_sql]
    drop_sql = f"DROP DATABASE IF EXISTS {postgres_quote_identifier(database_name)};"
    state.drop_command = ["psql", "-X", "-v", "ON_ERROR_STOP=1", "-Atc", drop_sql]

    if dry_run:
        state.status = "planned"
        state.classification = "dry_run"
        state.message = "would create managed PostgreSQL test database"
        write_json(metadata_path, managed_test_db_public_payload(state))
        return state

    if start_db_if_needed:
        db_port = source_probe.port or DEFAULT_PORTS["postgres"]
        db_host = source_probe.host or "127.0.0.1"
        if not probe_port("managed_test_db_postgres_port", db_port, host=db_host).open:
            pg_result = build_postgres_result(project_root, Path.cwd(), mode="start-db")
            apply_start_db(pg_result, project_root, timeout_seconds=TIMEOUT_POLICY["postgres_ready"])
            state.details["startDbIfNeeded"] = as_jsonable(pg_result.actions)

    if shutil.which("psql") is None:
        state.status = "infra_failed"
        state.classification = "postgres_client_missing"
        state.message = "psql is not available on PATH; managed test DB cannot be created safely."
        write_json(metadata_path, managed_test_db_public_payload(state))
        return state

    ready_probe = probe_pg_isready(maintenance_url, project_root)
    state.details["pgIsReady"] = as_jsonable(ready_probe)
    if not process_probe_ok(ready_probe):
        state.status = "infra_failed"
        state.classification = classify_managed_db_psql_failure(ready_probe, maintenance_url)
        state.message = "PostgreSQL maintenance target is not reachable."
        write_json(metadata_path, managed_test_db_public_payload(state))
        return state

    env_extra = psql_env_from_database_url(maintenance_url)
    create_probe = run_process_probe("managed_test_db_create", state.create_command, cwd=project_root, timeout=30, env_extra=env_extra)
    create_probe.stdout = sanitize_postgres_output(create_probe.stdout, maintenance_url)
    create_probe.stderr = sanitize_postgres_output(create_probe.stderr, maintenance_url)
    state.details["createProbe"] = as_jsonable(create_probe)
    if not process_probe_ok(create_probe):
        state.status = "infra_failed"
        state.classification = classify_managed_db_psql_failure(create_probe, maintenance_url)
        state.message = "Failed to create managed PostgreSQL test database."
        write_json(metadata_path, managed_test_db_public_payload(state))
        return state

    state.status = "ok"
    state.classification = "managed_test_db_created"
    state.message = "managed PostgreSQL test database created"
    write_json(metadata_path, managed_test_db_public_payload(state))
    return state


def release_gates_managed_db_prepare_result(project_root: Path, logs_dir: Path, index: int, state: ManagedTestDatabaseState) -> GateResult:
    log_path = release_gate_log_path(logs_dir, index, "managed_test_db_prepare")
    lines = [
        "# managed_test_db_prepare",
        f"status: {state.status}",
        f"classification: {state.classification}",
        f"retention: {state.retention}",
        f"database: {state.database_name or '<none>'}",
        f"url: {state.masked_database_url or '<none>'}",
        f"maintenance_url: {state.masked_maintenance_url or '<none>'}",
        f"metadata: {state.metadata_path or '<none>'}",
        f"cleanup: {state.cleanup_command or '<none>'}",
        f"message: {state.message}",
        "",
        json.dumps(managed_test_db_public_payload(state), ensure_ascii=False, indent=2),
        "",
    ]
    log_path.write_text("\n".join(lines), encoding="utf-8")
    return GateResult(
        name="managed_test_db_prepare",
        status=state.status,
        classification=state.classification,
        message=state.message,
        cwd=".",
        command=state.create_command,
        required=True,
        log_path=rel(log_path, project_root),
        details=managed_test_db_public_payload(state),
    )



def managed_runtime_public_payload(state: ManagedRuntimeState) -> dict[str, Any]:
    payload = as_jsonable(state)
    # Managed runtime never exposes raw database URLs. Only the masked copy is stored.
    if isinstance(payload.get("details"), dict):
        details = payload["details"]
        for key, value in list(details.items()):
            if isinstance(value, str) and value.startswith(("postgres://", "postgresql://")):
                details[key] = mask_database_url(value)
    return payload


def find_available_tcp_port(host: str = "127.0.0.1") -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def build_managed_runtime_state(project_root: Path, run_dir: Path, run_id_value: str) -> ManagedRuntimeState:
    backend_host = "127.0.0.1"
    frontend_host = "127.0.0.1"
    backend_port = find_available_tcp_port(backend_host)
    frontend_port = find_available_tcp_port(frontend_host)
    if frontend_port == backend_port:
        frontend_port = find_available_tcp_port(frontend_host)
    state = ManagedRuntimeState(
        enabled=True,
        run_id=run_id_value,
        status="planned",
        classification="managed_runtime_planned",
        message="managed backend/frontend runtime is planned",
        backend_host=backend_host,
        backend_port=backend_port,
        frontend_host=frontend_host,
        frontend_port=frontend_port,
        backend_api_base_url=f"http://{backend_host}:{backend_port}/api/v1",
        backend_health_url=f"http://{backend_host}:{backend_port}/api/v1/health",
        frontend_url=f"http://{frontend_host}:{frontend_port}/",
        runtime_state_path=rel(run_dir / "logs" / "runtime-state.json", project_root),
        env_diff_path=rel(run_dir / "logs" / "runtime-env-diff.md", project_root),
        managed_urls_path=rel(run_dir / "logs" / "managed-urls.env", project_root),
    )
    return state


def release_gate_managed_runtime_database_url(
    project_root: Path,
    *,
    managed_test_db_url: str | None,
    allow_dev_db_write: bool,
) -> tuple[str | None, str]:
    if managed_test_db_url:
        return managed_test_db_url, "managed ephemeral test database"
    test_db_url, test_db_source = release_gate_explicit_test_database_url(project_root)
    if test_db_url:
        return test_db_url, test_db_source or "TEST_DATABASE_URL"
    if allow_dev_db_write:
        source_url, source = release_gate_database_url_source(project_root)
        if source_url:
            return source_url, source or "configured backend database"
    return None, "managed runtime needs --managed-test-db, TEST_DATABASE_URL, or explicit --allow-dev-db-write"


def release_gate_managed_browser_env(state: ManagedRuntimeState) -> dict[str, str]:
    env: dict[str, str] = {}
    if state.backend_api_base_url:
        env["VITE_API_BASE_URL"] = state.backend_api_base_url.rstrip("/")
    if state.frontend_url:
        env["PLAYWRIGHT_BASE_URL"] = state.frontend_url.rstrip("/")
        env["PLAYWRIGHT_WEB_SERVER_URL"] = state.frontend_url.rstrip("/")
    if state.frontend_host:
        env["PLAYWRIGHT_FRONTEND_HOST"] = state.frontend_host
    if state.frontend_port:
        env["PLAYWRIGHT_FRONTEND_PORT"] = str(state.frontend_port)
    return env


def write_release_gates_runtime_files(
    project_root: Path,
    logs_dir: Path,
    state: ManagedRuntimeState,
    *,
    backend_env_diff: dict[str, str] | None = None,
    frontend_env_diff: dict[str, str] | None = None,
) -> None:
    state.runtime_state_path = rel(logs_dir / "runtime-state.json", project_root)
    state.env_diff_path = rel(logs_dir / "runtime-env-diff.md", project_root)
    state.managed_urls_path = rel(logs_dir / "managed-urls.env", project_root)
    write_json(logs_dir / "runtime-state.json", managed_runtime_public_payload(state))

    url_lines = [
        f"MANAGED_BACKEND_API_BASE_URL={state.backend_api_base_url or ''}",
        f"MANAGED_BACKEND_HEALTH_URL={state.backend_health_url or ''}",
        f"MANAGED_FRONTEND_URL={state.frontend_url or ''}",
    ]
    (logs_dir / "managed-urls.env").write_text("\n".join(url_lines) + "\n", encoding="utf-8")

    lines = ["# Managed runtime environment diff", ""]
    for title, values in [("Backend", backend_env_diff or {}), ("Frontend", frontend_env_diff or {})]:
        lines.append(f"## {title}")
        lines.append("")
        if not values:
            lines.append("- <none>")
        else:
            for key in sorted(values):
                value = values[key]
                if is_secret_key(key) or key in {"DATABASE__URL", "DATABASE_URL", "TEST_DATABASE_URL"}:
                    value = mask_value(key, value)
                    if key in {"DATABASE__URL", "DATABASE_URL", "TEST_DATABASE_URL"}:
                        value = mask_database_url(values[key])
                lines.append(f"- `{key}` = `{value}`")
        lines.append("")
    (logs_dir / "runtime-env-diff.md").write_text("\n".join(lines), encoding="utf-8")


def release_gates_managed_runtime_plan_result(project_root: Path, logs_dir: Path, index: int, state: ManagedRuntimeState) -> GateResult:
    log_path = release_gate_log_path(logs_dir, index, "managed_runtime_plan")
    state.status = "planned"
    state.classification = "dry_run"
    state.message = "would start isolated backend/frontend runtime on dynamic ports"
    write_release_gates_runtime_files(project_root, logs_dir, state)
    log_path.write_text(
        "\n".join(
            [
                "# managed_runtime_plan",
                "status: planned",
                "classification: dry_run",
                f"backend_api_base_url: {state.backend_api_base_url}",
                f"frontend_url: {state.frontend_url}",
                f"runtime_state: {state.runtime_state_path}",
                "",
                json.dumps(managed_runtime_public_payload(state), ensure_ascii=False, indent=2),
                "",
            ]
        ),
        encoding="utf-8",
    )
    return GateResult(
        name="managed_runtime_plan",
        status="planned",
        classification="dry_run",
        message=state.message,
        cwd=".",
        command=[sys.executable, "tools/devbootstrap.py", "release-gates", "--managed-runtime"],
        log_path=rel(log_path, project_root),
        details=managed_runtime_public_payload(state),
    )


def release_gates_managed_runtime_db_unavailable_result(
    project_root: Path,
    logs_dir: Path,
    index: int,
    state: ManagedRuntimeState,
    reason: str,
) -> GateResult:
    log_path = release_gate_log_path(logs_dir, index, "managed_runtime_db")
    state.status = "infra_failed"
    state.classification = "managed_runtime_db_unavailable"
    state.message = reason
    write_release_gates_runtime_files(project_root, logs_dir, state)
    log_path.write_text(
        "\n".join(
            [
                "# managed_runtime_db",
                "status: infra_failed",
                "classification: managed_runtime_db_unavailable",
                f"reason: {reason}",
                f"runtime_state: {state.runtime_state_path}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return GateResult(
        name="managed_runtime_db",
        status="infra_failed",
        classification="managed_runtime_db_unavailable",
        message=reason,
        cwd=".",
        command=[],
        required=True,
        log_path=rel(log_path, project_root),
        details=managed_runtime_public_payload(state),
    )

def start_release_gates_managed_backend(
    project_root: Path,
    logs_dir: Path,
    index: int,
    state: ManagedRuntimeState,
    database_url: str,
    timeout_seconds: int,
) -> tuple[GateResult, ReleaseGatesManagedRuntimeProcess | None]:
    log_path = release_gate_log_path(logs_dir, index, "managed_backend_start")
    host = state.backend_host
    port = state.backend_port or DEFAULT_PORTS["backend"]
    health_before = probe_backend_health(host, port, timeout=0.8)
    port_probe = probe_port("managed_backend", port, host=http_probe_host(host), timeout=0.4)
    details: dict[str, Any] = {
        "maskedDatabaseUrl": mask_database_url(database_url),
        "host": host,
        "port": port,
        "apiBaseUrl": state.backend_api_base_url,
        "healthBefore": as_jsonable(health_before),
        "portBefore": as_jsonable(port_probe),
    }
    if backend_health_ready(health_before) or port_probe.open:
        message = "Selected managed backend port is already occupied; release-gates will not reuse or kill a foreign/live backend."
        state.status = "infra_failed"
        state.classification = "managed_backend_port_occupied"
        state.message = message
        write_release_gates_runtime_files(project_root, logs_dir, state)
        log_path.write_text("\n".join(["# managed_backend_start", "status: infra_failed", "classification: managed_backend_port_occupied", message, ""]), encoding="utf-8")
        return GateResult(
            name="managed_backend_start",
            status="infra_failed",
            classification="managed_backend_port_occupied",
            message=message,
            cwd="backend",
            command=["cargo", "run"],
            log_path=rel(log_path, project_root),
            details=details,
        ), None
    if shutil.which("cargo") is None:
        message = "cargo is not available on PATH; managed backend cannot be started."
        state.status = "infra_failed"
        state.classification = "missing_cargo"
        state.message = message
        write_release_gates_runtime_files(project_root, logs_dir, state)
        log_path.write_text("\n".join(["# managed_backend_start", "status: infra_failed", "classification: missing_cargo", message, ""]), encoding="utf-8")
        return GateResult(
            name="managed_backend_start",
            status="infra_failed",
            classification="missing_cargo",
            message=message,
            cwd="backend",
            command=["cargo", "run"],
            log_path=rel(log_path, project_root),
            details=details,
        ), None

    backend_dir = project_root / "backend"
    backend_log_path = logs_dir / f"{index:02d}_managed_backend_process.log"
    command = ["cargo", "run"]
    backend_env_diff = release_gate_managed_db_env(database_url)
    backend_env_diff.update({"APP__HOST": host, "APP__PORT": str(port), "PYTHONDONTWRITEBYTECODE": "1"})
    frontend_env_diff = release_gate_managed_browser_env(state)
    state.backend_log_path = rel(backend_log_path, project_root)
    state.masked_database_url = mask_database_url(database_url)
    write_release_gates_runtime_files(project_root, logs_dir, state, backend_env_diff=backend_env_diff, frontend_env_diff=frontend_env_diff)

    log_handle = backend_log_path.open("ab", buffering=0)
    header = "\n".join(
        [
            f"== managed release-gates backend {iso_now()} ==",
            f"$ {command_as_text(command)}",
            f"cwd: {rel(backend_dir, project_root)}",
            f"APP__HOST: {host}",
            f"APP__PORT: {port}",
            f"DATABASE__URL: {mask_database_url(database_url)}",
            "",
        ]
    ).encode("utf-8", errors="replace")
    log_handle.write(header)
    env = os.environ.copy()
    env.update(backend_env_diff)
    started = time.monotonic()
    try:
        process = subprocess.Popen(
            command,
            cwd=str(backend_dir),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            env=env,
            **popen_process_group_kwargs(),
        )
    except OSError as exc:
        log_handle.close()
        message = f"Could not start managed backend: {exc}"
        state.status = "infra_failed"
        state.classification = "backend_start_failed"
        state.message = message
        write_release_gates_runtime_files(project_root, logs_dir, state, backend_env_diff=backend_env_diff, frontend_env_diff=frontend_env_diff)
        log_path.write_text("\n".join(["# managed_backend_start", "status: infra_failed", "classification: backend_start_failed", message, ""]), encoding="utf-8")
        return GateResult(
            name="managed_backend_start",
            status="infra_failed",
            classification="backend_start_failed",
            message=message,
            cwd="backend",
            command=command,
            log_path=rel(log_path, project_root),
            details=details,
        ), None
    finally:
        try:
            log_handle.close()
        except Exception:
            pass

    state.backend_pid = process.pid
    state.started_at = state.started_at or iso_now()
    ready, probes, returncode = wait_for_backend_health(process, host, port, timeout_seconds=timeout_seconds)
    duration_ms = int((time.monotonic() - started) * 1000)
    details.update({"pid": process.pid, "healthAfter": as_jsonable(probes), "processReturncode": returncode, "processLog": rel(backend_log_path, project_root)})
    if ready:
        message = "managed backend started against the selected test database on a dynamic port"
        status = "ok"
        classification = "managed_backend_started"
        state.status = "backend_started"
        state.classification = classification
        state.message = message
        runtime_process = ReleaseGatesManagedRuntimeProcess(
            name="backend",
            process=process,
            log_path=backend_log_path,
            command=command,
            cwd=backend_dir,
            host=host,
            port=port,
            url=state.backend_api_base_url or f"http://{host}:{port}/api/v1",
        )
    else:
        log_tail = sanitize_backend_log(read_log_tail(backend_log_path), project_root)
        classification = classify_backend_failure(log_tail, "backend_health_timeout" if returncode is None else "backend_start_failed")
        message = "managed backend did not become healthy; see managed backend process log"
        status = "infra_failed" if classification in {"postgres_unavailable", "database_missing", "postgres_auth_failed", "backend_health_timeout", "missing_prerequisite"} else "failed"
        state.status = status
        state.classification = classification
        state.message = message
        runtime_process = None
        if process.poll() is None:
            try:
                send_signal_to_owned_process(process.pid, signal.SIGTERM)
                wait_until_dead(process.pid, 5)
            except OSError:
                pass
    write_release_gates_runtime_files(project_root, logs_dir, state, backend_env_diff=backend_env_diff, frontend_env_diff=frontend_env_diff)
    log_path.write_text(
        "\n".join(
            [
                "# managed_backend_start",
                f"status: {status}",
                f"classification: {classification}",
                f"duration_ms: {duration_ms}",
                f"process_log: {rel(backend_log_path, project_root)}",
                f"message: {message}",
                "",
                json.dumps(details, ensure_ascii=False, indent=2),
                "",
            ]
        ),
        encoding="utf-8",
    )
    return GateResult(
        name="managed_backend_start",
        status=status,
        classification=classification,
        message=message,
        cwd="backend",
        command=command,
        returncode=returncode,
        duration_ms=duration_ms,
        log_path=rel(log_path, project_root),
        details=details,
    ), runtime_process

def managed_frontend_http_ready(probe: HttpProbe | None) -> bool:
    return bool(probe and probe.reachable and probe.status is not None and 200 <= probe.status < 300)


def wait_for_managed_frontend_root(process: subprocess.Popen[Any], url: str, *, timeout_seconds: int) -> tuple[bool, HttpProbe | None, int | None]:
    deadline = time.monotonic() + timeout_seconds
    last_probe: HttpProbe | None = None
    while time.monotonic() < deadline:
        returncode = process.poll()
        last_probe = probe_http("managed_frontend_root", url, timeout=1.0)
        if managed_frontend_http_ready(last_probe):
            return True, last_probe, returncode
        if returncode is not None:
            return False, last_probe, returncode
        time.sleep(1.0)
    return False, last_probe, process.poll()


def start_release_gates_managed_frontend(
    project_root: Path,
    logs_dir: Path,
    index: int,
    state: ManagedRuntimeState,
    timeout_seconds: int,
) -> tuple[GateResult, ReleaseGatesManagedRuntimeProcess | None]:
    log_path = release_gate_log_path(logs_dir, index, "managed_frontend_start")
    host = state.frontend_host
    port = state.frontend_port or DEFAULT_PORTS["frontend"]
    frontend_url = state.frontend_url or f"http://{host}:{port}/"
    root_before = probe_http("managed_frontend_root", frontend_url, timeout=0.8)
    port_probe = probe_port("managed_frontend", port, host=http_probe_host(host), timeout=0.4)
    details: dict[str, Any] = {
        "host": host,
        "port": port,
        "frontendUrl": frontend_url,
        "apiBaseUrl": state.backend_api_base_url,
        "rootBefore": as_jsonable(root_before),
        "portBefore": as_jsonable(port_probe),
    }
    if managed_frontend_http_ready(root_before) or port_probe.open:
        message = "Selected managed frontend port is already occupied; release-gates will not reuse or kill a foreign/live frontend."
        state.status = "infra_failed"
        state.classification = "managed_frontend_port_occupied"
        state.message = message
        write_release_gates_runtime_files(project_root, logs_dir, state)
        log_path.write_text("\n".join(["# managed_frontend_start", "status: infra_failed", "classification: managed_frontend_port_occupied", message, ""]), encoding="utf-8")
        return GateResult(
            name="managed_frontend_start",
            status="infra_failed",
            classification="managed_frontend_port_occupied",
            message=message,
            cwd="frontend",
            command=["npm", "run", "dev"],
            log_path=rel(log_path, project_root),
            details=details,
        ), None
    if shutil.which("npm") is None:
        message = "npm is not available on PATH; managed frontend cannot be started."
        state.status = "infra_failed"
        state.classification = "missing_npm"
        state.message = message
        write_release_gates_runtime_files(project_root, logs_dir, state)
        log_path.write_text("\n".join(["# managed_frontend_start", "status: infra_failed", "classification: missing_npm", message, ""]), encoding="utf-8")
        return GateResult(
            name="managed_frontend_start",
            status="infra_failed",
            classification="missing_npm",
            message=message,
            cwd="frontend",
            command=["npm", "run", "dev"],
            log_path=rel(log_path, project_root),
            details=details,
        ), None

    frontend_dir = project_root / "frontend"
    frontend_log_path = logs_dir / f"{index:02d}_managed_frontend_process.log"
    command = ["npm", "run", "dev", "--", "--host", host, "--port", str(port), "--strictPort"]
    backend_env_diff: dict[str, str] = {}
    frontend_env_diff = release_gate_managed_browser_env(state)
    frontend_env_diff["PYTHONDONTWRITEBYTECODE"] = "1"
    state.frontend_log_path = rel(frontend_log_path, project_root)
    write_release_gates_runtime_files(project_root, logs_dir, state, backend_env_diff=backend_env_diff, frontend_env_diff=frontend_env_diff)

    log_handle = frontend_log_path.open("ab", buffering=0)
    header = "\n".join(
        [
            f"== managed release-gates frontend {iso_now()} ==",
            f"$ {command_as_text(command)}",
            f"cwd: {rel(frontend_dir, project_root)}",
            f"VITE_API_BASE_URL: {state.backend_api_base_url or '<none>'}",
            f"frontend_url: {frontend_url}",
            "",
        ]
    ).encode("utf-8", errors="replace")
    log_handle.write(header)
    env = os.environ.copy()
    env.update(frontend_env_diff)
    started = time.monotonic()
    try:
        process = subprocess.Popen(
            command,
            cwd=str(frontend_dir),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            env=env,
            **popen_process_group_kwargs(),
        )
    except OSError as exc:
        log_handle.close()
        message = f"Could not start managed frontend: {exc}"
        state.status = "infra_failed"
        state.classification = "frontend_start_failed"
        state.message = message
        write_release_gates_runtime_files(project_root, logs_dir, state, frontend_env_diff=frontend_env_diff)
        log_path.write_text("\n".join(["# managed_frontend_start", "status: infra_failed", "classification: frontend_start_failed", message, ""]), encoding="utf-8")
        return GateResult(
            name="managed_frontend_start",
            status="infra_failed",
            classification="frontend_start_failed",
            message=message,
            cwd="frontend",
            command=command,
            log_path=rel(log_path, project_root),
            details=details,
        ), None
    finally:
        try:
            log_handle.close()
        except Exception:
            pass

    state.frontend_pid = process.pid
    state.started_at = state.started_at or iso_now()
    ready, probe, returncode = wait_for_managed_frontend_root(process, frontend_url, timeout_seconds=timeout_seconds)
    duration_ms = int((time.monotonic() - started) * 1000)
    details.update({"pid": process.pid, "rootAfter": as_jsonable(probe), "processReturncode": returncode, "processLog": rel(frontend_log_path, project_root)})
    if ready:
        message = "managed frontend started on a dynamic port with managed backend API base URL"
        status = "ok"
        classification = "managed_frontend_started"
        state.status = "runtime_started"
        state.classification = classification
        state.message = message
        runtime_process = ReleaseGatesManagedRuntimeProcess(
            name="frontend",
            process=process,
            log_path=frontend_log_path,
            command=command,
            cwd=frontend_dir,
            host=host,
            port=port,
            url=frontend_url,
        )
    else:
        log_tail = sanitize_frontend_log(read_log_tail(frontend_log_path), project_root)
        classification = classify_frontend_failure(log_tail, "frontend_health_timeout" if returncode is None else "frontend_start_failed")
        message = "managed frontend did not become healthy; see managed frontend process log"
        status = "infra_failed" if classification in {"frontend_health_timeout", "frontend_dependency_missing", "frontend_port_conflict", "dependency_network_unavailable", "missing_prerequisite"} else "failed"
        state.status = status
        state.classification = classification
        state.message = message
        runtime_process = None
        if process.poll() is None:
            try:
                send_signal_to_owned_process(process.pid, signal.SIGTERM)
                wait_until_dead(process.pid, 5)
            except OSError:
                pass
    write_release_gates_runtime_files(project_root, logs_dir, state, frontend_env_diff=frontend_env_diff)
    log_path.write_text(
        "\n".join(
            [
                "# managed_frontend_start",
                f"status: {status}",
                f"classification: {classification}",
                f"duration_ms: {duration_ms}",
                f"process_log: {rel(frontend_log_path, project_root)}",
                f"message: {message}",
                "",
                json.dumps(details, ensure_ascii=False, indent=2),
                "",
            ]
        ),
        encoding="utf-8",
    )
    return GateResult(
        name="managed_frontend_start",
        status=status,
        classification=classification,
        message=message,
        cwd="frontend",
        command=command,
        returncode=returncode,
        duration_ms=duration_ms,
        log_path=rel(log_path, project_root),
        details=details,
    ), runtime_process


def stop_release_gates_managed_process(project_root: Path, logs_dir: Path, index: int, runtime_process: ReleaseGatesManagedRuntimeProcess) -> GateResult:
    log_path = release_gate_log_path(logs_dir, index, f"managed_{runtime_process.name}_stop")
    started = time.monotonic()
    action = "stopped"
    error = None
    if runtime_process.process.poll() is None:
        try:
            send_signal_to_owned_process(runtime_process.process.pid, signal.SIGTERM)
            if not wait_until_dead(runtime_process.process.pid, TIMEOUT_POLICY["stop_grace"]):
                send_signal_to_owned_process(runtime_process.process.pid, getattr(signal, "SIGKILL", signal.SIGTERM))
                if wait_until_dead(runtime_process.process.pid, 5):
                    action = "force_stopped"
                else:
                    action = "failed"
                    error = "process still alive after force kill"
        except OSError as exc:
            action = "failed"
            error = str(exc)
    else:
        action = "already_exited"
    duration_ms = int((time.monotonic() - started) * 1000)
    status = "ok" if action in {"stopped", "force_stopped", "already_exited"} else "infra_failed"
    classification = f"managed_{runtime_process.name}_stopped" if status == "ok" else f"managed_{runtime_process.name}_stop_failed"
    message = f"managed {runtime_process.name} stopped" if status == "ok" else f"managed {runtime_process.name} stop failed"
    lines = [
        f"# managed_{runtime_process.name}_stop",
        f"status: {status}",
        f"classification: {classification}",
        f"pid: {runtime_process.process.pid}",
        f"action: {action}",
        f"duration_ms: {duration_ms}",
        f"process_log: {rel(runtime_process.log_path, project_root)}",
    ]
    if error:
        lines.append(f"error: {error}")
    lines.append("")
    log_path.write_text("\n".join(lines), encoding="utf-8")
    return GateResult(
        name=f"managed_{runtime_process.name}_stop",
        status=status,
        classification=classification,
        message=message,
        cwd=rel(runtime_process.cwd, project_root),
        command=["SIGTERM", str(runtime_process.process.pid)],
        duration_ms=duration_ms,
        log_path=rel(log_path, project_root),
        details={"pid": runtime_process.process.pid, "action": action, "processLog": rel(runtime_process.log_path, project_root), "error": error},
    )


def release_gates_skip_for_managed_runtime_unavailable(project_root: Path, logs_dir: Path, index: int, spec: GateSpec, reason: str) -> GateResult:
    log_path = release_gate_log_path(logs_dir, index, spec.name)
    message = f"Skipped because managed runtime is unavailable: {reason}"
    log_path.write_text(
        "\n".join(
            [
                f"# {spec.name}",
                "status: skipped_prerequisite",
                "classification: managed_runtime_unavailable",
                f"cwd: {spec.cwd or '.'}",
                f"reason: {message}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return GateResult(
        name=spec.name,
        status="skipped_prerequisite",
        classification="managed_runtime_unavailable",
        message=message,
        cwd=spec.cwd or ".",
        command=spec.command,
        required=spec.required,
        log_path=rel(log_path, project_root),
        details=spec.details,
    )


def finalize_release_gates_managed_test_database(
    project_root: Path,
    logs_dir: Path,
    index: int,
    state: ManagedTestDatabaseState,
    *,
    release_succeeded: bool,
    dump_on_failure: bool,
) -> GateResult:
    log_path = release_gate_log_path(logs_dir, index, "managed_test_db_retention")
    if state.status == "planned":
        state.retained = None
        state.message = "would apply managed test DB retention after release-gates"
        status = "planned"
        classification = "dry_run"
        message = state.message
    elif state.status != "ok" or not state.database_name or not state.maintenance_url:
        status = "skipped_prerequisite"
        classification = "managed_test_db_not_created"
        message = "managed test DB was not created; retention step skipped"
    else:
        should_drop = state.retention == "drop-always" or (state.retention == "keep-on-failure" and release_succeeded)
        should_keep = not should_drop
        if dump_on_failure and not release_succeeded:
            dump_path = logs_dir.parent / f"{state.database_name}.dump"
            state.dump_path = rel(dump_path, project_root)
            state.dump_command = ["pg_dump", "--format=custom", "--file", str(dump_path), state.database_name]
            if shutil.which("pg_dump") is not None:
                dump_env = psql_env_from_database_url(state.database_url or "")
                dump_probe = run_process_probe("managed_test_db_dump", state.dump_command, cwd=project_root, timeout=120, env_extra=dump_env)
                state.details["dumpProbe"] = as_jsonable(dump_probe)
            else:
                state.details["dumpProbe"] = {"available": False, "error": "pg_dump not found on PATH"}
        if should_keep:
            state.retained = True
            state.message = "managed test DB kept by retention policy"
            status = "ok"
            classification = "managed_test_db_retained"
            message = state.message
        else:
            env_extra = psql_env_from_database_url(state.maintenance_url)
            drop_probe = run_process_probe("managed_test_db_drop", state.drop_command, cwd=project_root, timeout=30, env_extra=env_extra)
            drop_probe.stdout = sanitize_postgres_output(drop_probe.stdout, state.maintenance_url)
            drop_probe.stderr = sanitize_postgres_output(drop_probe.stderr, state.maintenance_url)
            state.details["dropProbe"] = as_jsonable(drop_probe)
            if process_probe_ok(drop_probe):
                state.retained = False
                state.message = "managed test DB dropped by retention policy"
                status = "ok"
                classification = "managed_test_db_dropped"
                message = state.message
            else:
                state.retained = True
                state.failure_code = classify_managed_db_psql_failure(drop_probe, state.maintenance_url)
                state.message = "failed to drop managed test DB; it was left for manual cleanup"
                status = "infra_failed"
                classification = state.failure_code or "managed_test_db_drop_failed"
                message = state.message
    if state.metadata_path:
        metadata_path = project_root / state.metadata_path
        write_json(metadata_path, managed_test_db_public_payload(state))
    log_path.write_text(
        "\n".join(
            [
                "# managed_test_db_retention",
                f"status: {status}",
                f"classification: {classification}",
                f"retention: {state.retention}",
                f"release_succeeded: {release_succeeded}",
                f"retained: {state.retained}",
                f"database: {state.database_name or '<none>'}",
                f"cleanup: {state.cleanup_command or '<none>'}",
                f"message: {message}",
                "",
                json.dumps(managed_test_db_public_payload(state), ensure_ascii=False, indent=2),
                "",
            ]
        ),
        encoding="utf-8",
    )
    return GateResult(
        name="managed_test_db_retention",
        status=status,
        classification=classification,
        message=message,
        cwd=".",
        command=state.drop_command if state.drop_command else [],
        required=True,
        log_path=rel(log_path, project_root),
        details=managed_test_db_public_payload(state),
    )

def release_gate_database_env(project_root: Path) -> tuple[dict[str, str], str | None]:
    env_extra: dict[str, str] = {}
    if os.environ.get("TEST_DATABASE_URL"):
        env_extra["TEST_DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
        return env_extra, "environment TEST_DATABASE_URL"
    if os.environ.get("DATABASE_URL"):
        env_extra["TEST_DATABASE_URL"] = os.environ["DATABASE_URL"]
        return env_extra, "environment DATABASE_URL mapped to TEST_DATABASE_URL"

    backend_values, _ = parse_env_file(project_root / "backend" / ".env")
    for key in ["TEST_DATABASE_URL", "DATABASE__URL", "DATABASE_URL"]:
        value = backend_values.get(key)
        if value:
            env_extra["TEST_DATABASE_URL"] = value
            return env_extra, f"backend env {key} mapped to TEST_DATABASE_URL"
    return env_extra, None


def release_gate_explicit_test_database_url(project_root: Path) -> tuple[str | None, str | None]:
    if os.environ.get("TEST_DATABASE_URL"):
        return os.environ["TEST_DATABASE_URL"], "environment TEST_DATABASE_URL"
    backend_values, _ = parse_env_file(project_root / "backend" / ".env")
    if backend_values.get("TEST_DATABASE_URL"):
        return backend_values["TEST_DATABASE_URL"], "backend env TEST_DATABASE_URL"
    return None, None


def release_gate_smoke_env(project_root: Path) -> dict[str, str]:
    env_extra = {"BASE_URL": smoke_expected_base_url(project_root).rstrip("/")}
    test_db_url, _ = release_gate_explicit_test_database_url(project_root)
    if test_db_url:
        env_extra["TEST_DATABASE_URL"] = test_db_url
    return env_extra


def release_gate_smoke_allowed(project_root: Path, allow_dev_db_write: bool) -> tuple[bool, str]:
    if allow_dev_db_write:
        return True, "--allow-dev-db-write was provided"
    _, db_source = release_gate_explicit_test_database_url(project_root)
    if db_source:
        return True, db_source
    return False, "backend Python smoke writes through the live backend API; set TEST_DATABASE_URL or pass --allow-dev-db-write"


def playwright_browser_cache_roots(project_root: Path) -> list[Path]:
    roots: list[Path] = []
    configured = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if configured == "0":
        roots.append(project_root / "frontend" / "node_modules" / "playwright-core" / ".local-browsers")
    elif configured:
        roots.append(Path(configured).expanduser())

    home = Path.home()
    if platform.system().lower().startswith("win"):
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            roots.append(Path(local_app_data) / "ms-playwright")
    elif platform.system().lower() == "darwin":
        roots.append(home / "Library" / "Caches" / "ms-playwright")
    else:
        roots.append(home / ".cache" / "ms-playwright")
    return list(dict.fromkeys(roots))


def playwright_chromium_executable_present(project_root: Path) -> tuple[bool, list[str]]:
    evidence: list[str] = []
    executable_names = {"chrome", "chrome.exe", "headless_shell", "headless_shell.exe", "chromium", "chromium.exe"}
    for root in playwright_browser_cache_roots(project_root):
        evidence.append(str(root))
        if not root.exists():
            continue
        try:
            for path in root.rglob("*"):
                if path.is_file() and path.name in executable_names and "chrom" in path.as_posix().lower():
                    return True, evidence + [str(path)]
        except OSError as exc:
            evidence.append(f"could not inspect {root}: {exc}")
    return False, evidence


def frontend_package_has_dependency(package_data: dict[str, Any], dependency_name: str) -> bool:
    for field_name in ["dependencies", "devDependencies", "peerDependencies", "optionalDependencies"]:
        value = package_data.get(field_name)
        if isinstance(value, dict) and dependency_name in value:
            return True
    return False


def release_gate_frontend_dependency_status(project_root: Path) -> tuple[bool, str | None, dict[str, Any]]:
    package_data, package_error = read_frontend_package(project_root)
    package_json_path = project_root / "frontend" / "package.json"
    package_lock_path = project_root / "frontend" / "package-lock.json"
    node_modules_path = project_root / "frontend" / "node_modules"
    marker_path = frontend_install_marker_path(project_root)
    package_json_hash = sha256_file(package_json_path)
    package_lock_hash = sha256_file(package_lock_path)
    node_probe = run_process_probe("node_version", ["node", "--version"], cwd=project_root, timeout=8)
    npm_probe = run_process_probe("npm_version", ["npm", "--version"], cwd=project_root, timeout=8)
    node_version = process_probe_version_value(node_probe)
    npm_version = process_probe_version_value(npm_probe)
    marker = load_frontend_install_marker(project_root)
    marker_reasons = frontend_install_marker_mismatch_reasons(
        project_root,
        package_json_hash,
        package_lock_hash,
        node_version=node_version,
        npm_version=npm_version,
    )
    marker_valid = not marker_reasons
    marker_error = marker.get("_error") if isinstance(marker, dict) else None
    details: dict[str, Any] = {
        "packageError": package_error,
        "packageJsonExists": package_json_path.is_file(),
        "packageLockExists": package_lock_path.is_file(),
        "nodeModulesExists": node_modules_path.is_dir(),
        "installMarkerPath": rel(marker_path, project_root),
        "installMarkerExists": marker_path.is_file(),
        "installMarkerValid": marker_valid,
        "installMarkerMismatchReasons": marker_reasons,
        "installMarkerError": marker_error,
        "packageJsonSha256": package_json_hash,
        "packageLockSha256": package_lock_hash,
        "markerPackageJsonSha256": marker.get("packageJsonSha256") if isinstance(marker, dict) else None,
        "markerPackageLockSha256": marker.get("packageLockSha256") if isinstance(marker, dict) else None,
        "markerNodeVersion": marker.get("nodeVersion") if isinstance(marker, dict) else None,
        "markerNpmVersion": marker.get("npmVersion") if isinstance(marker, dict) else None,
        "nodeVersion": node_version,
        "npmVersion": npm_version,
        "platform": frontend_install_platform_fingerprint(),
        "markerPlatform": marker.get("platform") if isinstance(marker, dict) else None,
        "installCommand": release_gate_command_display(frontend_install_command(project_root)),
    }
    findings: list[str] = []
    if package_error:
        findings.append(package_error)
    if not process_probe_ok(node_probe):
        findings.append("node is not available on PATH")
    if not process_probe_ok(npm_probe):
        findings.append("npm is not available on PATH")
    if not package_lock_path.is_file():
        findings.append("frontend/package-lock.json is missing")
    findings.extend(marker_reasons)

    _ = package_data
    if findings:
        reason = "; ".join(findings) + "; run `python tools/devbootstrap.py release-gates --prepare-deps` or `python tools/devbootstrap.py prepare-frontend --install-mode=stale` before frontend gates."
        return False, reason, details
    return True, None, details

def release_gate_frontend_dependency_skip_spec(
    *,
    name: str,
    command: list[str],
    description: str,
    reason: str,
    details: dict[str, Any],
    timeout_seconds: int = 600,
) -> GateSpec:
    return GateSpec(
        name=name,
        cwd="frontend",
        command=command,
        description=description,
        timeout_seconds=timeout_seconds,
        skip_status="infra_failed",
        skip_classification="frontend_dependencies_missing",
        skip_reason=reason,
        details=details,
    )


def release_gate_path_has_text(path: Path, required_fragments: list[str]) -> tuple[bool, list[str], str]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return False, required_fragments, f"{path.as_posix()} is missing"
    missing = [fragment for fragment in required_fragments if fragment not in text]
    if missing:
        return False, missing, "missing required fragments: " + ", ".join(missing)
    return True, [], f"{len(required_fragments)} required fragments found"


def release_gate_check_readme_startup_commands(project_root: Path) -> tuple[str, str, str, list[str], dict[str, Any]]:
    required = [
        "python tools/devbootstrap.py release-gates",
        "python tools/devbootstrap.py up --dry-run",
        "python tools/devbootstrap.py smoke --level quick",
    ]
    ok, missing, message = release_gate_path_has_text(project_root / "README.md", required)
    lines = ["# README startup commands gate", f"status: {'ok' if ok else 'failed'}", message]
    if missing:
        lines.append("missing:")
        lines.extend(f"- {item}" for item in missing)
    details = {"path": "README.md", "requiredFragments": required, "missingFragments": missing}
    if ok:
        return "ok", "ok", "README contains current devbootstrap startup/release-gates commands", lines, details
    return "failed", "readme_startup_commands_missing", message, lines, details


def release_gate_check_known_limitations(project_root: Path) -> tuple[str, str, str, list[str], dict[str, Any]]:
    candidates = [
        project_root / "docs" / "product" / "v1-known-limitations.md",
        project_root / "docs" / "product" / "release-notes-v1.md",
        project_root / "docs" / "product" / "v1-release-notes.md",
    ]
    required_any = ["Known limitations", "Ограничения", "known limitations", "limitations"]
    evidence: list[str] = ["# release notes / known limitations gate"]
    found_path: Path | None = None
    found_text = ""
    for path in candidates:
        if not path.exists():
            evidence.append(f"missing: {path.relative_to(project_root).as_posix()}")
            continue
        text = path.read_text(encoding="utf-8")
        if any(fragment in text for fragment in required_any):
            found_path = path
            found_text = text
            break
        evidence.append(f"present_without_required_marker: {path.relative_to(project_root).as_posix()}")
    details = {"candidatePaths": [path.relative_to(project_root).as_posix() for path in candidates], "foundPath": rel(found_path, project_root) if found_path else None}
    if found_path is None:
        message = "No release notes / known limitations document with an explicit limitations marker was found."
        evidence.extend(["status: failed", message])
        return "failed", "release_notes_known_limitations_missing", message, evidence, details
    important_markers = ["real backend browser", "clean-machine", "release-gates"]
    missing_markers = [marker for marker in important_markers if marker.lower() not in found_text.lower()]
    details["missingRecommendedMarkers"] = missing_markers
    if missing_markers:
        message = "Known limitations document exists but misses release-gates-specific markers: " + ", ".join(missing_markers)
        evidence.extend(["status: failed", message])
        return "failed", "release_notes_known_limitations_incomplete", message, evidence, details
    message = f"Known limitations document found: {found_path.relative_to(project_root).as_posix()}"
    evidence.extend(["status: ok", message])
    return "ok", "ok", message, evidence, details


def release_gate_check_v1_checklist(project_root: Path) -> tuple[str, str, str, list[str], dict[str, Any]]:
    required = [
        "## 7. Testing and release gates",
        "`cargo test`",
        "`python tests/smoke_core_api.py`",
        "`npm run build`",
        "`npm run test:run`",
        "`npm run test:browser`",
        "Browser smoke проверяет реальный backend path",
        "Clean-machine quickstart проверен",
    ]
    path = project_root / "docs" / "product" / "v1-remaining-checklist.md"
    ok, missing, message = release_gate_path_has_text(path, required)
    lines = ["# v1 remaining checklist release-gates gate", f"status: {'ok' if ok else 'failed'}", message]
    if missing:
        lines.append("missing:")
        lines.extend(f"- {item}" for item in missing)
    details = {"path": "docs/product/v1-remaining-checklist.md", "requiredFragments": required, "missingFragments": missing}
    if ok:
        return "ok", "ok", "v1 remaining checklist contains the Testing and release gates matrix", lines, details
    return "failed", "v1_remaining_checklist_release_gates_missing", message, lines, details


def normalize_clean_machine_profile(value: str | None) -> str:
    normalized = (value or DEFAULT_CLEAN_MACHINE_PROFILE).strip().lower().replace("_", "-")
    if normalized.startswith("clean-machine-"):
        normalized = normalized.removeprefix("clean-machine-")
    if normalized not in {"dry", "deps", "runtime"}:
        raise ValueError(f"unknown clean-machine profile: {value}")
    return normalized


def release_gate_clean_machine_excluded_names() -> set[str]:
    return {
        ".git",
        BOOTSTRAP_DIR_NAME,
        ".venv",
        "node_modules",
        "target",
        "dist",
        "build",
        "coverage",
        "__pycache__",
        ".pytest_cache",
    }


def release_gate_clean_machine_ignore_factory(project_root: Path, exclusions: list[str]):
    excluded_names = release_gate_clean_machine_excluded_names()

    def ignore(directory: str, names: list[str]) -> set[str]:
        ignored: set[str] = set()
        directory_path = Path(directory)
        try:
            directory_relative = directory_path.relative_to(project_root).as_posix()
        except ValueError:
            directory_relative = "."
        for name in names:
            path = directory_path / name
            relative = name if directory_relative == "." else f"{directory_relative}/{name}"
            reason: str | None = None
            if name in excluded_names:
                reason = "generated/local state directory"
            elif name in {".env", ".env.local"} or (name.startswith(".env.") and name != ".env.example"):
                reason = "local environment file"
            elif name.endswith(RELEASE_GATES_ARCHIVE_EXCLUDED_SUFFIXES):
                reason = "generated artifact suffix"
            elif directory_path.name == "release" and name.endswith((".zip", ".exe")):
                reason = "large release payload"
            if reason:
                ignored.add(name)
                exclusions.append(f"{relative} — {reason}")
        return ignored

    return ignore


def release_gate_clean_machine_ignore(directory: str, names: list[str]) -> set[str]:
    # Backward-compatible ignore callback for older internal callers.
    return release_gate_clean_machine_ignore_factory(Path(directory), [])(directory, names)


def clean_machine_file_list(clean_root: Path) -> list[str]:
    files: list[str] = []
    for path in sorted(clean_root.rglob("*")):
        if path.is_file():
            files.append(path.relative_to(clean_root).as_posix())
    return files


def clean_machine_required_path_results(clean_root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    checks: list[dict[str, Any]] = []
    missing: list[str] = []
    for relative in CLEAN_MACHINE_REQUIRED_PATHS:
        path = clean_root / relative
        exists = path.exists()
        kind = "directory" if path.is_dir() else "file" if path.is_file() else "missing"
        checks.append({"path": relative, "exists": exists, "kind": kind})
        if not exists:
            missing.append(relative)
    return checks, missing


def release_gate_clean_machine_commands(profile: str) -> list[list[str]]:
    normalized = normalize_clean_machine_profile(profile)
    commands = [
        [sys.executable, "tools/devbootstrap.py", "self-check", "--no-write-report"],
        [sys.executable, "tools/devbootstrap.py", "diagnose", "--no-write-report"],
        [sys.executable, "tools/devbootstrap.py", "plan", "--no-write-report"],
        [sys.executable, "tools/devbootstrap.py", "prepare-env", "--no-write-report"],
        [
            sys.executable,
            "tools/devbootstrap.py",
            "up",
            "--dry-run",
            "--skip-db-start",
            "--skip-cargo-check",
            "--skip-install",
            "--skip-backend-start",
            "--skip-frontend-start",
            "--smoke-level",
            "none",
            "--step-timeout-seconds",
            "30",
            "--db-timeout-seconds",
            "5",
            "--cargo-check-timeout-seconds",
            "5",
            "--backend-timeout-seconds",
            "5",
            "--npm-timeout-seconds",
            "5",
            "--frontend-timeout-seconds",
            "5",
            "--smoke-timeout-seconds",
            "5",
        ],
    ]
    if normalized in {"deps", "runtime"}:
        commands.extend(
            [
                [sys.executable, "tools/devbootstrap.py", "prepare-frontend", "--install-mode=stale", "--no-write-report"],
                ["cargo", "test", "--no-run"],
            ]
        )
    if normalized == "runtime":
        commands.append(
            [
                sys.executable,
                "tools/devbootstrap.py",
                "release-gates",
                "--managed-test-db",
                "--managed-runtime",
                "--prepare-deps",
                "--test-db-retention=drop-always",
            ]
        )
    return commands


def run_clean_machine_command(
    *,
    clean_root: Path,
    command: list[str],
    timeout_seconds: int,
) -> dict[str, Any]:
    cwd = clean_root / "backend" if command[:3] == ["cargo", "test", "--no-run"] else clean_root
    started = time.monotonic()
    probe = run_process_probe(
        "clean_machine_sandbox",
        command,
        cwd=cwd,
        timeout=timeout_seconds,
        env_extra={"PYTHONDONTWRITEBYTECODE": "1"},
    )
    duration_ms = int((time.monotonic() - started) * 1000)
    stdout = release_gate_sanitize_output(clean_root, probe.stdout or "")
    stderr = release_gate_sanitize_output(clean_root, probe.stderr or probe.error or "")
    status, classification, message = classify_gate_output("clean_machine_sandbox", stdout, stderr, probe.error, probe.returncode)
    if not probe.available:
        status, classification, message = "infra_failed", "missing_prerequisite", f"required command is unavailable: {command[0]}"
    return {
        "command": command,
        "cwd": rel(cwd, clean_root),
        "returncode": probe.returncode,
        "durationMs": duration_ms,
        "status": status,
        "classification": classification,
        "message": message,
        "stdout": stdout,
        "stderr": stderr,
        "error": probe.error,
    }


def write_clean_machine_bundle(
    *,
    project_root: Path,
    clean_logs_dir: Path,
    payload: dict[str, Any],
    commands: list[dict[str, Any]],
    file_list: list[str],
    exclusions: list[str],
) -> None:
    clean_logs_dir.mkdir(parents=True, exist_ok=True)
    write_json(clean_logs_dir / "clean-machine.json", payload)
    (clean_logs_dir / "file-list.txt").write_text("\n".join(file_list) + ("\n" if file_list else ""), encoding="utf-8")
    (clean_logs_dir / "exclusions.txt").write_text("\n".join(exclusions) + ("\n" if exclusions else ""), encoding="utf-8")
    command_lines: list[str] = []
    for item in commands:
        command_lines.extend(
            [
                f"$ {release_gate_command_display(item['command'])}",
                f"cwd: {item['cwd']}",
                f"exit: {item['returncode'] if item['returncode'] is not None else item.get('error') or '<none>'}",
                f"duration_ms: {item['durationMs']}",
                f"status: {item['status']}",
                f"classification: {item['classification']}",
                "stdout:",
                item.get("stdout") or "<empty>",
                "stderr:",
                item.get("stderr") or "<empty>",
                "",
            ]
        )
    (clean_logs_dir / "commands.log").write_text("\n".join(command_lines), encoding="utf-8")
    report_lines = [
        "# clean-machine sandbox gate",
        "",
        f"- Status: `{payload['status']}`",
        f"- Classification: `{payload['classification']}`",
        f"- Profile: `{payload['profile']}`",
        f"- Sandbox: `{payload['sandboxPath']}`",
        f"- Retention: `{payload['retention']}`",
        f"- Kept: `{payload['kept']}`",
        f"- Cleanup: `{payload['cleanupCommand'] or '<none>'}`",
        f"- File count: `{len(file_list)}`",
        f"- Exclusions: `{len(exclusions)}`",
        "",
        "## Required files",
        "",
    ]
    for item in payload.get("requiredFiles", []):
        report_lines.append(f"- {'OK' if item['exists'] else 'MISSING'} `{item['path']}` ({item['kind']})")
    report_lines.extend(["", "## Commands", ""])
    for item in commands:
        report_lines.append(f"- `{release_gate_command_display(item['command'])}` — `{item['status']}` / `{item['classification']}`")
    report_lines.extend(["", "See also `commands.log`, `file-list.txt`, `exclusions.txt` and `clean-machine.json`.", ""])
    (clean_logs_dir / "report.md").write_text("\n".join(report_lines), encoding="utf-8")


def run_release_gate_clean_machine_sandbox_step(
    *,
    project_root: Path,
    logs_dir: Path,
    index: int,
    spec: GateSpec,
    timeout_seconds: int,
) -> GateResult:
    log_path = release_gate_log_path(logs_dir, index, spec.name)
    clean_logs_dir = logs_dir / "clean-machine"
    profile = normalize_clean_machine_profile(str(spec.details.get("cleanMachineProfile") or DEFAULT_CLEAN_MACHINE_PROFILE))
    retention = str(spec.details.get("cleanMachineRetention") or DEFAULT_CLEAN_MACHINE_RETENTION)
    if retention not in CLEAN_MACHINE_RETENTION_POLICIES:
        retention = DEFAULT_CLEAN_MACHINE_RETENTION
    started = time.monotonic()
    sandbox_parent = Path(tempfile.mkdtemp(prefix=f"devbootstrap-clean-machine-{spec.details.get('runId', 'run')}-"))
    clean_root = sandbox_parent / project_root.name
    exclusions: list[str] = []
    commands: list[dict[str, Any]] = []
    file_list: list[str] = []
    status = "ok"
    classification = "ok"
    message = "clean-machine sandbox completed"
    kept = False
    cleanup_command = f"rm -rf {sandbox_parent}"
    required_results: list[dict[str, Any]] = []
    missing_required: list[str] = []
    try:
        shutil.copytree(project_root, clean_root, ignore=release_gate_clean_machine_ignore_factory(project_root, exclusions))
        file_list = clean_machine_file_list(clean_root)
        required_results, missing_required = clean_machine_required_path_results(clean_root)
        if missing_required:
            status = "failed"
            classification = "clean_machine_required_files_missing"
            message = "clean-machine sandbox is missing required files: " + ", ".join(missing_required)
        else:
            for command in release_gate_clean_machine_commands(profile):
                item = run_clean_machine_command(clean_root=clean_root, command=command, timeout_seconds=timeout_seconds)
                commands.append(item)
                if item["status"] != "ok":
                    status = item["status"]
                    classification = item["classification"]
                    message = item["message"]
                    break
    except Exception as exc:
        status = "failed"
        classification = "clean_machine_sandbox_error"
        message = f"clean-machine sandbox raised {exc.__class__.__name__}: {exc}"
    finally:
        kept = retention == "keep-always" or (retention == "keep-on-failure" and status != "ok")
        if not kept:
            shutil.rmtree(sandbox_parent, ignore_errors=True)
    duration_ms = int((time.monotonic() - started) * 1000)
    payload = {
        "status": status,
        "classification": classification,
        "message": message,
        "profile": profile,
        "retention": retention,
        "sandboxPath": str(sandbox_parent),
        "projectCopy": str(clean_root),
        "kept": kept,
        "cleanupCommand": cleanup_command if kept else None,
        "durationMs": duration_ms,
        "requiredFiles": required_results,
        "missingRequiredFiles": missing_required,
        "commands": [
            {key: value for key, value in item.items() if key not in {"stdout", "stderr"}}
            for item in commands
        ],
        "bundleFiles": {
            "report": rel(clean_logs_dir / "report.md", project_root),
            "json": rel(clean_logs_dir / "clean-machine.json", project_root),
            "fileList": rel(clean_logs_dir / "file-list.txt", project_root),
            "exclusions": rel(clean_logs_dir / "exclusions.txt", project_root),
            "commandsLog": rel(clean_logs_dir / "commands.log", project_root),
        },
    }
    write_clean_machine_bundle(
        project_root=project_root,
        clean_logs_dir=clean_logs_dir,
        payload=payload,
        commands=commands,
        file_list=file_list,
        exclusions=exclusions,
    )
    log_path.write_text(
        "\n".join(
            [
                f"# {spec.name}",
                f"internal_check: {spec.internal_check}",
                f"cwd: {spec.cwd or '.'}",
                f"duration_ms: {duration_ms}",
                f"status: {status}",
                f"classification: {classification}",
                f"profile: {profile}",
                f"sandbox: {sandbox_parent}",
                f"kept: {kept}",
                f"cleanup: {cleanup_command if kept else '<deleted>'}",
                f"report: {rel(clean_logs_dir / 'report.md', project_root)}",
                f"json: {rel(clean_logs_dir / 'clean-machine.json', project_root)}",
                f"commands_log: {rel(clean_logs_dir / 'commands.log', project_root)}",
                "",
                message,
                "",
            ]
        ),
        encoding="utf-8",
    )
    details = dict(spec.details)
    details.update(payload)
    return GateResult(
        name=spec.name,
        status=status,
        classification=classification,
        message=message,
        cwd=spec.cwd or ".",
        command=spec.command,
        required=spec.required,
        duration_ms=duration_ms,
        log_path=rel(log_path, project_root),
        details=details,
    )


def release_gate_run_clean_machine_quickstart(project_root: Path, timeout_seconds: int) -> tuple[str, str, str, list[str], dict[str, Any]]:
    # Compatibility shim for older internal check names. The full implementation is
    # run_release_gate_clean_machine_sandbox_step(), which can write the structured
    # logs/clean-machine bundle.
    evidence = ["# clean-machine quickstart gate", "superseded by clean_machine_sandbox"]
    details = {"profile": DEFAULT_CLEAN_MACHINE_PROFILE}
    return "ok", "ok", "clean-machine quickstart compatibility shim", evidence, details


def run_release_gate_internal_check(project_root: Path, spec: GateSpec, timeout_seconds: int) -> tuple[str, str, str, list[str], dict[str, Any]]:
    if spec.internal_check == "docs_readme_startup_commands_present":
        return release_gate_check_readme_startup_commands(project_root)
    if spec.internal_check == "docs_release_notes_known_limitations_present":
        return release_gate_check_known_limitations(project_root)
    if spec.internal_check == "docs_v1_remaining_checklist_release_gates_present":
        return release_gate_check_v1_checklist(project_root)
    if spec.internal_check == "clean_machine_quickstart":
        return release_gate_run_clean_machine_quickstart(project_root, timeout_seconds)
    return "failed", "unknown_internal_gate", f"unknown internal release gate: {spec.internal_check}", [f"unknown internal release gate: {spec.internal_check}"], {}


def run_release_gate_internal_step(
    *,
    project_root: Path,
    logs_dir: Path,
    index: int,
    spec: GateSpec,
    timeout_seconds: int,
) -> GateResult:
    if spec.internal_check == "clean_machine_sandbox":
        return run_release_gate_clean_machine_sandbox_step(
            project_root=project_root,
            logs_dir=logs_dir,
            index=index,
            spec=spec,
            timeout_seconds=timeout_seconds,
        )
    log_path = release_gate_log_path(logs_dir, index, spec.name)
    started = time.monotonic()
    try:
        status, classification, message, lines, details = run_release_gate_internal_check(project_root, spec, timeout_seconds)
    except Exception as exc:
        status = "failed"
        classification = "internal_gate_error"
        message = f"internal gate raised {exc.__class__.__name__}: {exc}"
        lines = [message]
        details = {}
    duration_ms = int((time.monotonic() - started) * 1000)
    merged_details = dict(spec.details)
    merged_details.update(details)
    log_path.write_text(
        "\n".join(
            [
                f"# {spec.name}",
                f"internal_check: {spec.internal_check}",
                f"cwd: {spec.cwd or '.'}",
                f"duration_ms: {duration_ms}",
                f"status: {status}",
                f"classification: {classification}",
                "",
                *lines,
                "",
            ]
        ),
        encoding="utf-8",
    )
    return GateResult(
        name=spec.name,
        status=status,
        classification=classification,
        message=message,
        cwd=spec.cwd or ".",
        command=spec.command,
        required=spec.required,
        duration_ms=duration_ms,
        log_path=rel(log_path, project_root),
        details=merged_details,
    )


def build_release_gate_specs(
    project_root: Path,
    *,
    allow_dev_db_write: bool = False,
    install_playwright_browsers: bool = False,
    include_real_backend_browser: bool = False,
    real_backend_browser_spec: str = "e2e/smoke/real-backend.smoke.spec.ts",
    include_clean_machine: bool = False,
    clean_machine_profile: str = DEFAULT_CLEAN_MACHINE_PROFILE,
    clean_machine_retention: str = DEFAULT_CLEAN_MACHINE_RETENTION,
    dry_run: bool = False,
    managed_test_db_url: str | None = None,
    managed_test_db_requested: bool = False,
    managed_runtime_requested: bool = False,
    managed_backend_api_base_url: str | None = None,
    managed_frontend_url: str | None = None,
    managed_frontend_host: str | None = None,
    managed_frontend_port: int | None = None,
) -> list[GateSpec]:
    specs: list[GateSpec] = [
        GateSpec(
            name="self_check",
            cwd=".",
            command=[sys.executable, "tools/devbootstrap.py", "self-check", "--no-write-report", "--json"],
            description="Run devbootstrap internal stdlib fixtures before aggregating release-gates.",
            timeout_seconds=120,
        ),
        GateSpec(
            name="diagnose",
            cwd=".",
            command=[sys.executable, "tools/devbootstrap.py", "diagnose", "--no-write-report", "--json"],
            description="Capture read-only environment diagnostics for the release-gates bundle.",
            timeout_seconds=120,
        ),
        GateSpec(
            name="backend_cargo_test_default",
            cwd="backend",
            command=["cargo", "test"],
            description="Run the default Rust test profile and detect ignored critical tests.",
            timeout_seconds=900,
        ),
    ]

    if managed_test_db_url:
        db_env_extra = release_gate_managed_db_env(managed_test_db_url)
        db_source = "managed ephemeral test database"
    else:
        db_env_extra, db_source = release_gate_database_env(project_root)
    if db_source or dry_run:
        details = {"databaseEnvSource": db_source, "managedTestDb": bool(managed_test_db_url)}
        if managed_test_db_url:
            details["maskedDatabaseUrl"] = mask_database_url(managed_test_db_url)
        if dry_run and not db_source:
            details["dryRunPrerequisiteBypassed"] = True
        specs.append(
            GateSpec(
                name="backend_cargo_test_db_ignored",
                cwd="backend",
                command=["cargo", "test", "--", "--include-ignored"],
                description="Force ignored DB integration tests to run with TEST_DATABASE_URL.",
                timeout_seconds=900,
                env_extra=db_env_extra,
                details=details,
            )
        )
    else:
        reason = "TEST_DATABASE_URL is absent and no DATABASE__URL/DATABASE_URL was found in backend env; DB integration tests cannot be executed safely."
        classification = "db_test_prerequisite_missing"
        if managed_test_db_requested:
            reason = "--managed-test-db was requested, but managed test DB was not created; DB integration tests cannot run safely."
            classification = "managed_test_db_unavailable"
        specs.append(
            GateSpec(
                name="backend_cargo_test_db_ignored",
                cwd="backend",
                command=["cargo", "test", "--", "--include-ignored"],
                description="Force ignored DB integration tests to run with TEST_DATABASE_URL.",
                skip_reason=reason,
                skip_classification=classification,
                details={"databaseEnvSource": None, "managedTestDbRequested": managed_test_db_requested},
            )
        )

    if managed_test_db_url:
        smoke_allowed, smoke_reason = True, "managed ephemeral test database"
        smoke_env = release_gate_smoke_env(project_root)
        smoke_env.update(release_gate_managed_db_env(managed_test_db_url))
        if managed_backend_api_base_url:
            smoke_env["BASE_URL"] = managed_backend_api_base_url.rstrip("/")
    elif managed_test_db_requested:
        smoke_allowed = False
        smoke_reason = "--managed-test-db was requested, but managed test DB was not created; backend smoke cannot run safely."
        smoke_env = release_gate_smoke_env(project_root)
    else:
        smoke_allowed, smoke_reason = release_gate_smoke_allowed(project_root, allow_dev_db_write)
        smoke_env = release_gate_smoke_env(project_root)
        if managed_backend_api_base_url:
            smoke_env["BASE_URL"] = managed_backend_api_base_url.rstrip("/")
    for smoke_name in ["backend_python_smoke_first", "backend_python_smoke_second"]:
        if smoke_allowed or dry_run:
            details = {"smokePermission": smoke_reason, "managedTestDb": bool(managed_test_db_url), "managedRuntime": managed_runtime_requested}
            if managed_test_db_url:
                details["maskedDatabaseUrl"] = mask_database_url(managed_test_db_url)
            if managed_backend_api_base_url:
                details["baseUrl"] = managed_backend_api_base_url.rstrip("/")
            if dry_run and not smoke_allowed:
                details["dryRunPrerequisiteBypassed"] = True
            specs.append(
                GateSpec(
                    name=smoke_name,
                    cwd="backend",
                    command=[sys.executable, "tests/smoke_core_api.py"],
                    description="Run backend black-box smoke against the live backend API; second run checks idempotency.",
                    timeout_seconds=900,
                    env_extra=smoke_env,
                    details=details,
                )
            )
        else:
            specs.append(
                GateSpec(
                    name=smoke_name,
                    cwd="backend",
                    command=[sys.executable, "tests/smoke_core_api.py"],
                    description="Run backend black-box smoke against the live backend API; second run checks idempotency.",
                    skip_reason=smoke_reason,
                    skip_classification="managed_test_db_unavailable" if managed_test_db_requested else "smoke_db_write_guard",
                    details={"smokePermission": smoke_reason, "managedTestDbRequested": managed_test_db_requested},
                )
            )

    frontend_deps_ready, frontend_deps_reason, frontend_deps_details = release_gate_frontend_dependency_status(project_root)
    frontend_build_details = {"frontendDependencies": frontend_deps_details}
    frontend_test_details = {"frontendDependencies": frontend_deps_details}
    if dry_run or frontend_deps_ready:
        if dry_run and not frontend_deps_ready:
            frontend_build_details["dryRunPrerequisiteBypassed"] = True
            frontend_test_details["dryRunPrerequisiteBypassed"] = True
        specs.extend(
            [
                GateSpec(
                    name="frontend_build",
                    cwd="frontend",
                    command=["npm", "run", "build"],
                    description="Run TypeScript/Vite production build.",
                    timeout_seconds=600,
                    details=frontend_build_details,
                ),
                GateSpec(
                    name="frontend_unit_integration",
                    cwd="frontend",
                    command=["npm", "run", "test:run"],
                    description="Run Vitest unit/integration tests.",
                    timeout_seconds=600,
                    details=frontend_test_details,
                ),
            ]
        )
    else:
        dependency_reason = frontend_deps_reason or "frontend dependencies are missing or stale; run `python tools/devbootstrap.py prepare-frontend --force-install` before release-gates."
        specs.extend(
            [
                release_gate_frontend_dependency_skip_spec(
                    name="frontend_build",
                    command=["npm", "run", "build"],
                    description="Run TypeScript/Vite production build.",
                    reason=dependency_reason,
                    details=frontend_build_details,
                ),
                release_gate_frontend_dependency_skip_spec(
                    name="frontend_unit_integration",
                    command=["npm", "run", "test:run"],
                    description="Run Vitest unit/integration tests.",
                    reason=dependency_reason,
                    details=frontend_test_details,
                ),
            ]
        )

    package_data, package_error = read_frontend_package(project_root)
    scripts = frontend_scripts_from_package(package_data) if not package_error else {}
    playwright_dependency_present = bool(package_data) and frontend_package_has_dependency(package_data, "@playwright/test")
    playwright_node_package_present = (project_root / "frontend" / "node_modules" / "@playwright" / "test").exists()
    chromium_present, chromium_evidence = playwright_chromium_executable_present(project_root)
    browser_details = {
        "packageError": package_error,
        "scriptPresent": "test:browser" in scripts,
        "dependencyPresent": playwright_dependency_present,
        "nodePackagePresent": playwright_node_package_present,
        "chromiumExecutablePresent": chromium_present,
        "checkedBrowserCacheRoots": chromium_evidence,
        "frontendDependencies": frontend_deps_details,
        "managedRuntime": managed_runtime_requested,
    }
    browser_env: dict[str, str] = {}
    if managed_backend_api_base_url:
        browser_env["VITE_API_BASE_URL"] = managed_backend_api_base_url.rstrip("/")
        browser_details["apiBaseUrl"] = managed_backend_api_base_url.rstrip("/")
    if managed_frontend_url:
        browser_env["PLAYWRIGHT_BASE_URL"] = managed_frontend_url.rstrip("/")
        browser_env["PLAYWRIGHT_WEB_SERVER_URL"] = managed_frontend_url.rstrip("/")
        browser_details["frontendUrl"] = managed_frontend_url.rstrip("/")
    if managed_frontend_host:
        browser_env["PLAYWRIGHT_FRONTEND_HOST"] = managed_frontend_host
    if managed_frontend_port:
        browser_env["PLAYWRIGHT_FRONTEND_PORT"] = str(managed_frontend_port)

    if not frontend_deps_ready and not dry_run:
        specs.append(
            release_gate_frontend_dependency_skip_spec(
                name="frontend_browser_smoke",
                command=["npm", "run", "test:browser"],
                description="Run Playwright browser smoke.",
                reason=frontend_deps_reason or "frontend dependencies are missing or stale; run `python tools/devbootstrap.py prepare-frontend --force-install` before release-gates.",
                details=browser_details,
            )
        )
    elif dry_run and not package_error and "test:browser" in scripts and playwright_dependency_present:
        browser_details["dryRunPrerequisiteBypassed"] = not playwright_node_package_present or not chromium_present
        specs.append(
            GateSpec(
                name="frontend_browser_smoke",
                cwd="frontend",
                command=["npm", "run", "test:browser"],
                description="Run Playwright browser smoke.",
                timeout_seconds=600,
                env_extra=browser_env,
                details=browser_details,
            )
        )
    elif package_error:
        specs.append(
            GateSpec(
                name="frontend_browser_smoke",
                cwd="frontend",
                command=["npm", "run", "test:browser"],
                description="Run Playwright browser smoke.",
                skip_status="infra_failed",
                skip_classification="frontend_package_invalid",
                skip_reason=package_error,
                details=browser_details,
            )
        )
    elif "test:browser" not in scripts:
        specs.append(
            GateSpec(
                name="frontend_browser_smoke",
                cwd="frontend",
                command=["npm", "run", "test:browser"],
                description="Run Playwright browser smoke.",
                skip_status="failed",
                skip_classification="browser_smoke_script_missing",
                skip_reason="frontend/package.json does not define scripts.test:browser",
                details=browser_details,
            )
        )
    elif not playwright_dependency_present or not playwright_node_package_present:
        specs.append(
            GateSpec(
                name="frontend_browser_smoke",
                cwd="frontend",
                command=["npm", "run", "test:browser"],
                description="Run Playwright browser smoke.",
                skip_status="infra_failed",
                skip_classification="browser_smoke_prerequisite",
                skip_reason="Playwright package is not installed in frontend/node_modules; run prepare-frontend or npm ci first.",
                details=browser_details,
            )
        )
    elif not chromium_present and install_playwright_browsers:
        specs.append(
            GateSpec(
                name="playwright_install",
                cwd="frontend",
                command=["npx", "playwright", "install", "chromium"],
                description="Install Playwright Chromium browser binaries because --install-playwright-browsers was provided.",
                timeout_seconds=900,
                details=browser_details,
            )
        )
        specs.append(
            GateSpec(
                name="frontend_browser_smoke",
                cwd="frontend",
                command=["npm", "run", "test:browser"],
                description="Run Playwright browser smoke after explicit browser install attempt.",
                timeout_seconds=600,
                env_extra=browser_env,
                details=browser_details,
            )
        )
    elif not chromium_present:
        specs.append(
            GateSpec(
                name="frontend_browser_smoke",
                cwd="frontend",
                command=["npm", "run", "test:browser"],
                description="Run Playwright browser smoke.",
                skip_status="infra_failed",
                skip_classification="browser_smoke_prerequisite",
                skip_reason="Playwright Chromium browser executable is missing; rerun with --install-playwright-browsers or run npx playwright install manually.",
                details=browser_details,
            )
        )
    else:
        specs.append(
            GateSpec(
                name="frontend_browser_smoke",
                cwd="frontend",
                command=["npm", "run", "test:browser"],
                description="Run Playwright browser smoke.",
                timeout_seconds=600,
                env_extra=browser_env,
                details=browser_details,
            )
        )

    real_backend_spec = Path(real_backend_browser_spec)
    real_backend_spec_project_path = project_root / "frontend" / real_backend_spec
    if managed_test_db_url:
        real_backend_allowed, real_backend_reason = True, "managed ephemeral test database"
    elif managed_test_db_requested:
        real_backend_allowed = False
        real_backend_reason = "--managed-test-db was requested, but managed test DB was not created; real-backend browser smoke cannot run safely."
    else:
        real_backend_allowed, real_backend_reason = release_gate_smoke_allowed(project_root, allow_dev_db_write)
    real_backend_details = {
        "specPath": real_backend_spec.as_posix(),
        "specExists": real_backend_spec_project_path.exists(),
        "writePermission": real_backend_reason,
        "requiresNoPageRouteMocks": True,
        "mockedBrowserSmokeDoesNotSatisfyThisGate": True,
        "managedTestDb": bool(managed_test_db_url),
        "managedRuntime": managed_runtime_requested,
    }
    if managed_backend_api_base_url:
        real_backend_details["apiBaseUrl"] = managed_backend_api_base_url.rstrip("/")
    if managed_frontend_url:
        real_backend_details["frontendUrl"] = managed_frontend_url.rstrip("/")
    if managed_test_db_url:
        real_backend_details["maskedDatabaseUrl"] = mask_database_url(managed_test_db_url)
    if real_backend_spec_project_path.exists() and (include_real_backend_browser or dry_run) and (real_backend_allowed or dry_run):
        if dry_run and not real_backend_allowed:
            real_backend_details["dryRunPrerequisiteBypassed"] = True
        specs.append(
            GateSpec(
                name="browser_real_backend_path",
                cwd="frontend",
                command=["npm", "run", "test:browser:real-backend"],
                description="Run the dedicated Playwright browser path against a live backend without page.route API mocks.",
                timeout_seconds=900,
                env_extra=browser_env,
                details=real_backend_details,
            )
        )
    elif real_backend_spec_project_path.exists() and not include_real_backend_browser:
        specs.append(
            GateSpec(
                name="browser_real_backend_path",
                cwd="frontend",
                command=["npm", "run", "test:browser:real-backend"],
                description="Dedicated real-backend Playwright path exists but is opt-in because it writes through the live backend.",
                skip_reason="Pass --include-real-backend-browser plus TEST_DATABASE_URL or --allow-dev-db-write to execute this write-capable browser gate.",
                skip_classification="real_backend_browser_opt_in_required",
                details=real_backend_details,
            )
        )
    elif real_backend_spec_project_path.exists():
        specs.append(
            GateSpec(
                name="browser_real_backend_path",
                cwd="frontend",
                command=["npm", "run", "test:browser:real-backend"],
                description="Dedicated real-backend Playwright path exists but cannot run without explicit write permission.",
                skip_reason=real_backend_reason,
                skip_classification="managed_test_db_unavailable" if managed_test_db_requested else "real_backend_browser_write_guard",
                details=real_backend_details,
            )
        )
    else:
        specs.append(
            GateSpec(
                name="browser_real_backend_path",
                cwd="frontend",
                command=["npm", "run", "test:browser:real-backend"],
                description="Dedicated real-backend Playwright path without API mocks.",
                not_implemented_reason="Dedicated real-backend browser spec is missing; mocked browser smoke must not close this checklist item.",
                details=real_backend_details,
            )
        )

    specs.extend(
        [
            GateSpec(
                name="readme_startup_commands_present",
                cwd=".",
                command=[],
                description="Check that README documents current devbootstrap startup and release-gates commands.",
                internal_check="docs_readme_startup_commands_present",
            ),
            GateSpec(
                name="release_notes_known_limitations_present",
                cwd=".",
                command=[],
                description="Check that release notes / known limitations are present and explicit.",
                internal_check="docs_release_notes_known_limitations_present",
            ),
            GateSpec(
                name="v1_remaining_checklist_release_gates_present",
                cwd=".",
                command=[],
                description="Check that v1 remaining checklist still contains Testing and release gates.",
                internal_check="docs_v1_remaining_checklist_release_gates_present",
            ),
        ]
    )

    normalized_clean_machine_profile = normalize_clean_machine_profile(clean_machine_profile)
    if include_clean_machine:
        specs.append(
            GateSpec(
                name="clean_machine_sandbox",
                cwd=".",
                command=[],
                description="Run a clean-machine sandbox copy with generated/local state excluded and a profile-specific quickstart path.",
                timeout_seconds=1800 if normalized_clean_machine_profile == "runtime" else 1200 if normalized_clean_machine_profile == "deps" else 900,
                internal_check="clean_machine_sandbox",
                details={
                    "cleanMachineProfile": normalized_clean_machine_profile,
                    "cleanMachineRetention": clean_machine_retention,
                },
            )
        )
    else:
        specs.append(
            GateSpec(
                name="clean_machine_sandbox",
                cwd=".",
                command=[],
                description="Optional clean-machine sandbox gate.",
                required=False,
                skip_status="skipped_optional",
                skip_classification="clean_machine_optional_not_requested",
                skip_reason="Clean-machine sandbox is optional; pass --include-clean-machine to run it in a temporary project copy.",
                details={"cleanMachineProfile": normalized_clean_machine_profile},
            )
        )
    return specs


def release_gates_overall_status(gates: list[GateResult], *, dry_run: bool) -> tuple[str, str]:
    if dry_run:
        return "dry_run", "release_gates_dry_run"
    statuses = {gate.status for gate in gates if gate.required}
    if "failed" in statuses:
        return "failed", "release_gates_failed"
    if "timeout" in statuses:
        return "failed", "release_gates_timeout"
    if "infra_failed" in statuses:
        return "infra_failed", "release_gates_infra_failed"
    if "not_implemented" in statuses or "skipped_prerequisite" in statuses:
        return "incomplete", "release_gates_incomplete"
    if "partial_pass" in statuses:
        return "partial_pass", "release_gates_partial_pass"
    if statuses and statuses.issubset({"ok"}):
        return "ok", "release_gates_ok"
    return "unknown", "release_gates_unknown"


def release_gates_next_action_for_code(code: str) -> str | None:
    actions = {
        "frontend_dependencies_missing": "Run `python tools/devbootstrap.py release-gates --prepare-deps` to let release-gates install missing/stale frontend dependencies before frontend gates, or run `python tools/devbootstrap.py prepare-frontend --install-mode=stale` first.",
        "frontend_dependencies_stale": "Run `python tools/devbootstrap.py release-gates --prepare-deps` or `python tools/devbootstrap.py prepare-frontend --install-mode=stale` to refresh the frontend install marker after package/lockfile/runtime changes.",
        "frontend_lockfile_mismatch": "Fix frontend/package-lock.json in a separate patch, then rerun release-gates; release-gates will not silently update lockfiles.",
        "dependency_network_unavailable": "Restore network/package-cache access and rerun dependency preparation; this is an infrastructure failure, not a product test failure.",
        "browser_smoke_prerequisite": "Install Playwright browser prerequisites by rerunning with `--install-playwright-browsers` or by running `cd frontend && npx playwright install chromium`.",
        "db_test_prerequisite_missing": "Prepare a write-safe test DB, export `TEST_DATABASE_URL`, or rerun with `python tools/devbootstrap.py release-gates --managed-test-db`; see `docs/dev-bootstrap/release-gates-test-database.md`.",
        "managed_test_db_source_missing": "Set backend `DATABASE__URL`/`DATABASE_URL` or copy `backend/.env.example` to `backend/.env`, then rerun `release-gates --managed-test-db`.",
        "managed_test_db_source_invalid": "Fix backend `DATABASE__URL`/`DATABASE_URL`; managed test DB needs a complete PostgreSQL URL with host, port, database and user.",
        "postgres_client_missing": "Install PostgreSQL client tools (`psql`, optionally `pg_dump`) or use a shell where they are on PATH before rerunning `release-gates --managed-test-db`.",
        "postgres_createdb_permission_denied": "Use a PostgreSQL role with CREATEDB privilege or start the project compose PostgreSQL and rerun `release-gates --managed-test-db --start-db-if-needed`.",
        "postgres_unavailable": "Start PostgreSQL first, or rerun with `--managed-test-db --start-db-if-needed` to allow devbootstrap to start the project compose PostgreSQL when the configured port is closed.",
        "managed_test_db_unavailable": "Inspect the `managed_test_db_prepare` gate log, fix PostgreSQL capability, then rerun `release-gates --managed-test-db`.",
        "managed_runtime_db_unavailable": "Use `--managed-test-db`, set TEST_DATABASE_URL, or explicitly pass `--allow-dev-db-write` before running `release-gates --managed-runtime`.",
        "managed_backend_port_occupied": "Rerun release-gates; managed runtime uses dynamic ports and refuses to reuse a foreign/live backend if the selected port races.",
        "managed_frontend_port_occupied": "Rerun release-gates; managed runtime uses dynamic ports and refuses to reuse a foreign/live frontend if the selected port races.",
        "managed_runtime_unavailable": "Inspect managed runtime start gates and `logs/runtime-state.json`, then rerun after fixing backend/frontend startup failures.",
        "managed_backend_unavailable": "Inspect `managed_backend_start` and the managed backend process log, then rerun after freeing the backend port and fixing startup failures.",
        "managed_frontend_started": "Managed frontend started; continue with browser gates.",
        "smoke_db_write_guard": "For backend Python smoke, restart the live backend against the test DB and set `TEST_DATABASE_URL`; use `--allow-dev-db-write` only when the configured dev DB is disposable.",
        "real_backend_browser_opt_in_required": "After frontend deps and write-safe DB are ready, add `--include-real-backend-browser` to run the no-mock browser path.",
        "real_backend_browser_write_guard": "Set `TEST_DATABASE_URL` and restart backend against that DB before running `--include-real-backend-browser`, or consciously pass `--allow-dev-db-write`.",
        "runtime_unreachable": "Run `python tools/devbootstrap.py status`; if backend/frontend ports are stale or foreign, run `python tools/devbootstrap.py stop` for tracked processes and restart with `python tools/devbootstrap.py up`.",
        "frontend_port_conflict": "Inspect the process occupying the frontend port; devbootstrap will not kill a foreign process automatically. Use `status`, `stop`, then `up` when it is your tracked process.",
        "clean_machine_optional_not_requested": "For final release review, rerun with `--include-clean-machine` after required gates are no longer blocked.",
    }
    return actions.get(code)


def release_gates_add_unique_action(actions: list[str], action: str, seen: set[str]) -> None:
    if action not in seen:
        actions.append(action)
        seen.add(action)


def finalize_release_gates_result(result: ReleaseGatesResult) -> None:
    result.overall_status, result.classification = release_gates_overall_status(result.gates, dry_run=result.dry_run)
    result.findings.clear()
    for gate in result.gates:
        if gate.status not in {"ok", "planned"}:
            severity = "warn" if (not gate.required or gate.status in {"partial_pass", "not_implemented", "skipped_prerequisite", "skipped_optional"}) else "fail"
            result.findings.append(
                {
                    "severity": severity,
                    "code": gate.classification,
                    "message": f"{gate.name}: {gate.message}",
                }
            )
    result.next_actions.clear()
    seen_actions: set[str] = set()
    if result.dry_run:
        release_gates_add_unique_action(result.next_actions, "Run `python tools/devbootstrap.py release-gates` without --dry-run to execute implemented gates and create a fresh bundle.", seen_actions)
    elif result.overall_status == "ok":
        release_gates_add_unique_action(result.next_actions, "Configured release-gates passed; continue with later release validation or manual review.", seen_actions)
    else:
        priority = [
            "managed_test_db_source_missing",
            "managed_test_db_source_invalid",
            "postgres_client_missing",
            "postgres_createdb_permission_denied",
            "postgres_unavailable",
            "managed_test_db_unavailable",
            "managed_runtime_db_unavailable",
            "managed_runtime_unavailable",
            "managed_backend_port_occupied",
            "managed_frontend_port_occupied",
            "managed_backend_unavailable",
            "frontend_dependencies_missing",
            "browser_smoke_prerequisite",
            "db_test_prerequisite_missing",
            "smoke_db_write_guard",
            "real_backend_browser_write_guard",
            "real_backend_browser_opt_in_required",
            "runtime_unreachable",
            "frontend_port_conflict",
            "clean_machine_optional_not_requested",
        ]
        codes = {finding["code"] for finding in result.findings}
        for code in priority:
            if code in codes:
                action = release_gates_next_action_for_code(code)
                if action:
                    release_gates_add_unique_action(result.next_actions, action, seen_actions)
        if result.overall_status == "incomplete":
            release_gates_add_unique_action(result.next_actions, "Resolve skipped prerequisites, run opt-in real-backend browser/clean-machine gates when needed, or implement missing release-gates before treating this as a full v1 release signal.", seen_actions)
        if not result.next_actions:
            release_gates_add_unique_action(result.next_actions, "Inspect release-gates logs and fix the classified finding before rerunning.", seen_actions)


def render_release_gates_summary(result: ReleaseGatesResult) -> str:
    lines: list[str] = []
    lines.append("# release-gates summary")
    lines.append("")
    lines.append(f"Overall: {result.overall_status}")
    lines.append(f"Classification: {result.classification}")
    lines.append(f"Generated: {result.generated_at}")
    lines.append(f"Dry run: {result.dry_run}")
    lines.append(f"Project root: {result.project_root or 'not found'}")
    if result.managed_test_db and result.managed_test_db.enabled:
        lines.append(f"Managed test DB: {result.managed_test_db.status} / {result.managed_test_db.classification}")
        lines.append(f"Managed DB name: {result.managed_test_db.database_name or '<none>'}")
        lines.append(f"Managed DB URL: {result.managed_test_db.masked_database_url or '<none>'}")
        lines.append(f"Managed DB retention: {result.managed_test_db.retention}; retained={result.managed_test_db.retained}")
        lines.append(f"Managed DB cleanup: {result.managed_test_db.cleanup_command or '<none>'}")
    if result.managed_runtime and result.managed_runtime.enabled:
        lines.append(f"Managed runtime: {result.managed_runtime.status} / {result.managed_runtime.classification}")
        lines.append(f"Managed backend: {result.managed_runtime.backend_api_base_url or '<none>'}")
        lines.append(f"Managed frontend: {result.managed_runtime.frontend_url or '<none>'}")
        lines.append(f"Managed runtime state: {result.managed_runtime.runtime_state_path or '<none>'}")
    lines.append(f"Report dir: {result.report_dir or '<not written>'}")
    if result.archive_path:
        lines.append(f"Archive: {result.archive_path}")
    lines.append("")
    for gate in result.gates:
        lines.append(f"> {release_gate_command_display(gate.command) if gate.command else gate.name}")
        lines.append(f"status: {gate.status}")
        lines.append(f"classification: {gate.classification}")
        lines.append(f"reason: {gate.message}")
        if gate.log_path:
            lines.append(f"log: {gate.log_path}")
        lines.append("")
    return "\n".join(lines)


def render_release_gates_report(result: ReleaseGatesResult) -> str:
    lines: list[str] = []
    lines.append("# devbootstrap release-gates report")
    lines.append("")
    lines.append(f"- Generated at: `{result.generated_at}`")
    lines.append(f"- Tool version: `{result.tool_version}`")
    lines.append(f"- Project root: `{result.project_root or 'not found'}`")
    lines.append(f"- Invoked from: `{result.invoked_from}`")
    lines.append(f"- Overall status: `{result.overall_status}`")
    lines.append(f"- Classification: `{result.classification}`")
    lines.append(f"- Dry run: `{result.dry_run}`")
    if result.archive_path:
        lines.append(f"- Archive: `{result.archive_path}`")
    if result.managed_test_db and result.managed_test_db.enabled:
        lines.append("")
        lines.append("## Managed test database")
        lines.append("")
        lines.append(f"- Status: `{result.managed_test_db.status}`")
        lines.append(f"- Classification: `{result.managed_test_db.classification}`")
        lines.append(f"- Database: `{result.managed_test_db.database_name or '<none>'}`")
        lines.append(f"- URL: `{result.managed_test_db.masked_database_url or '<none>'}`")
        lines.append(f"- Retention: `{result.managed_test_db.retention}`")
        lines.append(f"- Retained: `{result.managed_test_db.retained}`")
        lines.append(f"- Metadata: `{result.managed_test_db.metadata_path or '<none>'}`")
        lines.append(f"- Cleanup: `{result.managed_test_db.cleanup_command or '<none>'}`")
    if result.managed_runtime and result.managed_runtime.enabled:
        lines.append("")
        lines.append("## Managed runtime")
        lines.append("")
        lines.append(f"- Status: `{result.managed_runtime.status}`")
        lines.append(f"- Classification: `{result.managed_runtime.classification}`")
        lines.append(f"- Backend API: `{result.managed_runtime.backend_api_base_url or '<none>'}`")
        lines.append(f"- Backend health: `{result.managed_runtime.backend_health_url or '<none>'}`")
        lines.append(f"- Frontend: `{result.managed_runtime.frontend_url or '<none>'}`")
        lines.append(f"- Backend PID: `{result.managed_runtime.backend_pid or '<none>'}`")
        lines.append(f"- Frontend PID: `{result.managed_runtime.frontend_pid or '<none>'}`")
        lines.append(f"- Runtime state: `{result.managed_runtime.runtime_state_path or '<none>'}`")
        lines.append(f"- Env diff: `{result.managed_runtime.env_diff_path or '<none>'}`")
        lines.append(f"- Managed URLs: `{result.managed_runtime.managed_urls_path or '<none>'}`")
    lines.append("")
    lines.append("## Gates")
    lines.append("")
    lines.append("| Gate | Status | Classification | Command | Log |")
    lines.append("|---|---|---|---|---|")
    for gate in result.gates:
        command = release_gate_command_display(gate.command) if gate.command else gate.name
        log = f"`{gate.log_path}`" if gate.log_path else ""
        lines.append(f"| `{gate.name}` | {gate.status} | `{gate.classification}` | `{command}` | {log} |")
    lines.append("")
    lines.append("## Findings")
    lines.append("")
    if result.findings:
        for finding in result.findings:
            lines.append(f"- **{finding['severity'].upper()}** `{finding['code']}` — {finding['message']}")
    else:
        lines.append("- No blocking findings from configured release-gates.")
    lines.append("")
    lines.append("## Next safe actions")
    lines.append("")
    for action in result.next_actions:
        lines.append(f"- {action}")
    lines.append("")
    return "\n".join(lines)


def release_gates_json_payload(result: ReleaseGatesResult) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "command": "release-gates",
        "toolVersion": result.tool_version,
        "generatedAt": result.generated_at,
        "projectRoot": result.project_root,
        "invokedFrom": result.invoked_from,
        "runId": result.run_id,
        "dryRun": result.dry_run,
        "timeoutSeconds": result.timeout_seconds,
        "overallStatus": result.overall_status,
        "classification": result.classification,
        "reportDir": result.report_dir,
        "archivePath": result.archive_path,
        "managedTestDb": managed_test_db_public_payload(result.managed_test_db) if result.managed_test_db else None,
        "managedRuntime": managed_runtime_public_payload(result.managed_runtime) if result.managed_runtime else None,
        "gates": [as_jsonable(gate) for gate in result.gates],
        "findings": result.findings,
        "nextActions": result.next_actions,
    }


def release_gates_archive_excluded(path: Path, root: Path, archive_path: Path) -> bool:
    if path == archive_path:
        return True
    if path.suffix == ".zip" and path.name.startswith("release-gates_"):
        return True
    try:
        relative = path.relative_to(root)
    except ValueError:
        return True
    if any(part in RELEASE_GATES_ARCHIVE_EXCLUDED_PARTS for part in relative.parts):
        return True
    if path.name in RELEASE_GATES_ARCHIVE_EXCLUDED_NAMES:
        return True
    if path.name.startswith(".env."):
        return True
    if path.suffix in RELEASE_GATES_ARCHIVE_EXCLUDED_SUFFIXES:
        return True
    return False


def create_release_gates_archive(run_dir: Path, archive_path: Path) -> None:
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(run_dir.rglob("*")):
            if path.is_dir() or release_gates_archive_excluded(path, run_dir, archive_path):
                continue
            zf.write(path, path.relative_to(run_dir).as_posix())


def write_release_gates_reports(project_root: Path, result: ReleaseGatesResult, run_dir: Path) -> None:
    result.report_dir = rel(run_dir, project_root)
    timestamp = now_utc().strftime("%Y%m%d_%H%M%S")
    archive_path = run_dir / f"release-gates_{timestamp}.zip"
    result.archive_path = rel(archive_path, project_root)
    (run_dir / "summary.txt").write_text(render_release_gates_summary(result), encoding="utf-8")
    (run_dir / "release-gates.md").write_text(render_release_gates_report(result), encoding="utf-8")
    write_json(run_dir / "release-gates.json", release_gates_json_payload(result))
    create_release_gates_archive(run_dir, archive_path)
    append_report_to_state(project_root, run_dir, result.run_id)


def print_release_gates_summary(result: ReleaseGatesResult) -> None:
    print_header("devbootstrap release-gates")
    print(f"Tool version: {result.tool_version}")
    print(f"Project root: {result.project_root or 'not found'}")
    print(f"Overall: {result.overall_status}")
    print(f"Classification: {result.classification}")
    print(f"Dry run: {result.dry_run}")
    if result.managed_runtime and result.managed_runtime.enabled:
        print("\nManaged runtime:")
        print(f"  - backend: {result.managed_runtime.backend_api_base_url or '<none>'}")
        print(f"  - frontend: {result.managed_runtime.frontend_url or '<none>'}")
        print(f"  - state: {result.managed_runtime.runtime_state_path or '<not written>'}")
    print("\nGates:")
    for gate in result.gates:
        suffix = f" — {gate.log_path}" if gate.log_path else ""
        print(f"  - {gate.status.upper()} {gate.name}: {gate.message}{suffix}")
    if result.findings:
        print("\nFindings:")
        for finding in result.findings:
            print(f"  - {finding['severity'].upper()} {finding['code']}: {finding['message']}")
    if result.next_actions:
        print("\nNext safe actions:")
        for action in result.next_actions:
            print(f"  - {action}")
    if result.report_dir:
        print(f"\nReport: {result.report_dir}/release-gates.md")
    if result.archive_path:
        print(f"Archive: {result.archive_path}")


def command_release_gates(args: argparse.Namespace) -> int:
    invoked_from = Path.cwd()
    project_root = find_project_root(invoked_from)
    run_id_value = run_id("release-gates")
    result = ReleaseGatesResult(
        generated_at=iso_now(),
        tool_version=TOOL_VERSION,
        project_root=str(project_root) if project_root else None,
        invoked_from=str(invoked_from),
        run_id=run_id_value,
        dry_run=args.dry_run,
        timeout_seconds=args.timeout_seconds,
    )
    if project_root is None:
        result.overall_status = "failed"
        result.classification = "invalid_project_root"
        result.findings.append({"severity": "fail", "code": "invalid_project_root", "message": "Could not find project root."})
        result.next_actions.append("Run this command from the project root, tools/, backend/ or frontend/ directory.")
        print_release_gates_summary(result)
        if args.json:
            print("\nJSON:")
            print(json.dumps(release_gates_json_payload(result), ensure_ascii=False, indent=2))
        return 1

    if args.output_dir:
        output_dir = Path(args.output_dir)
        if not output_dir.is_absolute():
            output_dir = project_root / output_dir
        run_dir = output_dir
        run_id_value = run_dir.name
        result.run_id = run_id_value
    else:
        run_dir = project_root / BOOTSTRAP_DIR_NAME / "runs" / run_id_value
    logs_dir = run_dir / "logs"
    run_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    next_gate_index = 1
    managed_test_db_url: str | None = None
    if args.managed_test_db:
        managed_state = build_release_gates_managed_test_database(
            project_root,
            run_dir,
            run_id_value=run_id_value,
            retention=args.test_db_retention,
            dry_run=args.dry_run,
            start_db_if_needed=args.start_db_if_needed,
        )
        result.managed_test_db = managed_state
        result.gates.append(release_gates_managed_db_prepare_result(project_root, logs_dir, next_gate_index, managed_state))
        next_gate_index += 1
        if managed_state.database_url and managed_state.status in {"ok", "planned"}:
            managed_test_db_url = managed_state.database_url

    effective_managed_runtime = bool(args.managed_runtime or args.managed_test_db)
    managed_runtime_state: ManagedRuntimeState | None = None
    managed_runtime_db_url: str | None = None
    managed_runtime_db_reason: str | None = None
    if effective_managed_runtime:
        managed_runtime_state = build_managed_runtime_state(project_root, run_dir, run_id_value)
        result.managed_runtime = managed_runtime_state
        managed_runtime_db_url, managed_runtime_db_reason = release_gate_managed_runtime_database_url(
            project_root,
            managed_test_db_url=managed_test_db_url,
            allow_dev_db_write=args.allow_dev_db_write,
        )
        managed_runtime_state.database_source = managed_runtime_db_reason
        if managed_runtime_db_url:
            managed_runtime_state.masked_database_url = mask_database_url(managed_runtime_db_url)
        if args.dry_run:
            result.gates.append(release_gates_managed_runtime_plan_result(project_root, logs_dir, next_gate_index, managed_runtime_state))
            next_gate_index += 1
        elif not managed_runtime_db_url:
            result.gates.append(
                release_gates_managed_runtime_db_unavailable_result(
                    project_root,
                    logs_dir,
                    next_gate_index,
                    managed_runtime_state,
                    managed_runtime_db_reason or "managed runtime database target is unavailable",
                )
            )
            next_gate_index += 1

    if args.prepare_deps is not None:
        prepare_deps_mode = normalize_frontend_prepare_dep_mode(args.prepare_deps)
    elif args.prepare_frontend:
        prepare_deps_mode = DEFAULT_FRONTEND_PREPARE_DEP_MODE
    else:
        prepare_deps_mode = "never"
    if prepare_deps_mode != "never":
        prepare_spec = GateSpec(
            name="frontend_prepare_dependencies",
            cwd=".",
            command=[
                sys.executable,
                "tools/devbootstrap.py",
                "prepare-frontend",
                f"--install-mode={prepare_deps_mode}",
                "--no-write-report",
            ],
            description="Install or verify frontend npm dependencies before building release-gates frontend specs.",
            timeout_seconds=TIMEOUT_POLICY["npm_install"],
            details={"prepareDepsMode": prepare_deps_mode, "compatPrepareFrontendFlag": bool(args.prepare_frontend)},
        )
        effective_timeout = min(args.timeout_seconds, prepare_spec.timeout_seconds) if args.timeout_seconds > 0 else prepare_spec.timeout_seconds
        result.gates.append(
            run_gate_process_step(
                project_root=project_root,
                logs_dir=logs_dir,
                index=next_gate_index,
                spec=prepare_spec,
                timeout_seconds=effective_timeout,
                dry_run=args.dry_run,
            )
        )
        next_gate_index += 1

        backend_warmup_spec = GateSpec(
            name="backend_dependency_warmup",
            cwd="backend",
            command=["cargo", "test", "--no-run"],
            description="Warm backend Cargo dependencies/build artifacts to separate dependency or compile failures from test failures.",
            timeout_seconds=900,
            details={"prepareDepsMode": prepare_deps_mode},
        )
        effective_timeout = min(args.timeout_seconds, backend_warmup_spec.timeout_seconds) if args.timeout_seconds > 0 else backend_warmup_spec.timeout_seconds
        result.gates.append(
            run_gate_process_step(
                project_root=project_root,
                logs_dir=logs_dir,
                index=next_gate_index,
                spec=backend_warmup_spec,
                timeout_seconds=effective_timeout,
                dry_run=args.dry_run,
            )
        )
        next_gate_index += 1

    specs = build_release_gate_specs(
        project_root,
        allow_dev_db_write=args.allow_dev_db_write,
        install_playwright_browsers=args.install_playwright_browsers,
        include_real_backend_browser=args.include_real_backend_browser,
        real_backend_browser_spec=args.real_backend_browser_spec,
        include_clean_machine=args.include_clean_machine,
        clean_machine_profile=args.clean_machine_profile,
        clean_machine_retention=args.clean_machine_retention,
        dry_run=args.dry_run,
        managed_test_db_url=managed_test_db_url,
        managed_test_db_requested=args.managed_test_db,
        managed_runtime_requested=effective_managed_runtime,
        managed_backend_api_base_url=managed_runtime_state.backend_api_base_url if managed_runtime_state else None,
        managed_frontend_url=managed_runtime_state.frontend_url if managed_runtime_state else None,
        managed_frontend_host=managed_runtime_state.frontend_host if managed_runtime_state else None,
        managed_frontend_port=managed_runtime_state.frontend_port if managed_runtime_state else None,
    )

    for spec in specs:
        if spec.internal_check == "clean_machine_sandbox":
            spec.details.setdefault("runId", run_id_value)

    managed_backend: ReleaseGatesManagedRuntimeProcess | None = None
    managed_frontend: ReleaseGatesManagedRuntimeProcess | None = None
    managed_backend_start_failed: str | None = None
    managed_frontend_start_failed: str | None = None
    managed_backend_gate_names = {"backend_python_smoke_first", "backend_python_smoke_second", "browser_real_backend_path", "frontend_browser_smoke"}
    managed_frontend_gate_names = {"frontend_browser_smoke", "browser_real_backend_path"}

    for spec in specs:
        requires_managed_runtime = effective_managed_runtime and spec.name in managed_backend_gate_names and not args.dry_run and not spec.skip_reason and not spec.not_implemented_reason
        if requires_managed_runtime:
            if not managed_runtime_state or not managed_runtime_db_url:
                result.gates.append(
                    release_gates_skip_for_managed_runtime_unavailable(project_root, logs_dir, next_gate_index, spec, managed_runtime_db_reason or "managed runtime database target is unavailable")
                )
                next_gate_index += 1
                continue
            if managed_backend is None and managed_backend_start_failed is None:
                start_timeout = min(args.timeout_seconds, TIMEOUT_POLICY["backend_ready"]) if args.timeout_seconds > 0 else TIMEOUT_POLICY["backend_ready"]
                start_gate, managed_backend = start_release_gates_managed_backend(
                    project_root,
                    logs_dir,
                    next_gate_index,
                    managed_runtime_state,
                    managed_runtime_db_url,
                    start_timeout,
                )
                result.gates.append(start_gate)
                next_gate_index += 1
                if managed_backend is None:
                    managed_backend_start_failed = start_gate.classification
            if managed_backend_start_failed:
                result.gates.append(
                    release_gates_skip_for_managed_runtime_unavailable(project_root, logs_dir, next_gate_index, spec, managed_backend_start_failed)
                )
                next_gate_index += 1
                continue
            if spec.name in managed_frontend_gate_names and managed_frontend is None and managed_frontend_start_failed is None:
                frontend_timeout = min(args.timeout_seconds, TIMEOUT_POLICY["frontend_ready"]) if args.timeout_seconds > 0 else TIMEOUT_POLICY["frontend_ready"]
                start_gate, managed_frontend = start_release_gates_managed_frontend(
                    project_root,
                    logs_dir,
                    next_gate_index,
                    managed_runtime_state,
                    frontend_timeout,
                )
                result.gates.append(start_gate)
                next_gate_index += 1
                if managed_frontend is None:
                    managed_frontend_start_failed = start_gate.classification
            if spec.name in managed_frontend_gate_names and managed_frontend_start_failed:
                result.gates.append(
                    release_gates_skip_for_managed_runtime_unavailable(project_root, logs_dir, next_gate_index, spec, managed_frontend_start_failed)
                )
                next_gate_index += 1
                continue

        effective_timeout = min(args.timeout_seconds, spec.timeout_seconds) if args.timeout_seconds > 0 else spec.timeout_seconds
        result.gates.append(
            run_gate_process_step(
                project_root=project_root,
                logs_dir=logs_dir,
                index=next_gate_index,
                spec=spec,
                timeout_seconds=effective_timeout,
                dry_run=args.dry_run,
            )
        )
        next_gate_index += 1

    if managed_frontend is not None:
        result.gates.append(stop_release_gates_managed_process(project_root, logs_dir, next_gate_index, managed_frontend))
        next_gate_index += 1
    if managed_backend is not None:
        result.gates.append(stop_release_gates_managed_process(project_root, logs_dir, next_gate_index, managed_backend))
        next_gate_index += 1
    if managed_runtime_state is not None:
        if not args.dry_run:
            managed_runtime_state.stopped_at = iso_now()
            if managed_runtime_state.classification in {"managed_frontend_started", "managed_backend_started", "managed_frontend_stopped", "managed_backend_stopped"}:
                managed_runtime_state.status = "stopped"
                managed_runtime_state.classification = "managed_runtime_stopped"
                managed_runtime_state.message = "managed runtime was stopped after release-gates"
        write_release_gates_runtime_files(project_root, logs_dir, managed_runtime_state)

    finalize_release_gates_result(result)

    if result.managed_test_db is not None:
        retention_gate = finalize_release_gates_managed_test_database(
            project_root,
            logs_dir,
            next_gate_index,
            result.managed_test_db,
            release_succeeded=result.overall_status == "ok",
            dump_on_failure=args.dump_test_db_on_failure,
        )
        result.gates.append(retention_gate)
        finalize_release_gates_result(result)

    write_release_gates_reports(project_root, result, run_dir)
    print_release_gates_summary(result)
    if args.json:
        print("\nJSON:")
        print(json.dumps(release_gates_json_payload(result), ensure_ascii=False, indent=2))
    return 1 if result.overall_status not in {"ok", "dry_run"} else 0


def stop_target_from_entry(project_root: Path, name: str, entry: dict[str, Any]) -> StopTarget:
    pid_value = entry.get("pid")
    try:
        pid = int(pid_value)
    except (TypeError, ValueError):
        pid = None
    target = StopTarget(
        name=name,
        pid=pid,
        cwd=entry.get("cwd") if isinstance(entry.get("cwd"), str) else None,
        command=entry.get("command") if isinstance(entry.get("command"), str) else None,
        log_path=entry.get("logPath") if isinstance(entry.get("logPath"), str) else None,
        run_id=entry.get("runId") if isinstance(entry.get("runId"), str) else None,
        alive_before=pid_alive(pid or -1),
    )
    verify_stop_target(project_root, target)
    return target


def expected_process_cwd(project_root: Path, name: str) -> Path | None:
    if name == "backend":
        return (project_root / "backend").resolve()
    if name == "frontend":
        return (project_root / "frontend").resolve()
    return None


def verify_stop_target(project_root: Path, target: StopTarget) -> None:
    if target.name not in {"backend", "frontend"}:
        target.verification_status = "unsupported_process"
        target.verification_evidence = "devbootstrap only stops tracked backend/frontend processes"
        return
    if target.pid is None or target.pid <= 0:
        target.verification_status = "invalid_pid"
        target.verification_evidence = f"stored pid is invalid: {target.pid!r}"
        return
    if not target.alive_before:
        target.verification_status = "stale_pid"
        target.verification_evidence = "stored pid is not alive"
        return
    expected_cwd = expected_process_cwd(project_root, target.name)
    stored_cwd = ((project_root / target.cwd).resolve() if target.cwd else None)
    expected_word = "cargo" if target.name == "backend" else "npm"
    stored_command_ok = bool(target.command and expected_word in target.command.lower())
    stored_cwd_ok = bool(stored_cwd and expected_cwd and stored_cwd == expected_cwd)
    if os.name != "nt" and (Path("/proc") / str(target.pid)).exists():
        actual_cwd, actual_cmd, detail_error = procfs_process_details(target.pid)
        actual_cwd_ok = bool(actual_cwd and expected_cwd and Path(actual_cwd).resolve() == expected_cwd)
        actual_cmd_text = (actual_cmd or "").lower()
        command_hint_ok = expected_word in actual_cmd_text or stored_command_ok
        evidence_parts = [f"expected_cwd={expected_cwd}"]
        if actual_cwd:
            evidence_parts.append(f"actual_cwd={actual_cwd}")
        if actual_cmd:
            evidence_parts.append(f"actual_cmd={actual_cmd[:240]}")
        if detail_error:
            evidence_parts.append(detail_error)
        target.verification_evidence = "; ".join(evidence_parts)
        if actual_cwd_ok and command_hint_ok:
            target.verification_status = "owned"
        elif actual_cwd is None and command_hint_ok and stored_cwd_ok:
            target.verification_status = "owned_limited"
            target.verification_evidence += "; procfs cwd unavailable, fell back to state cwd plus process command hint"
        else:
            target.verification_status = "mismatch"
        return
    if stored_cwd_ok and stored_command_ok:
        target.verification_status = "owned_limited"
        target.verification_evidence = "procfs command/cwd verification is unavailable; using state cwd+command guard"
    else:
        target.verification_status = "mismatch"
        target.verification_evidence = f"stored cwd/command do not match expected {target.name} process"


def send_signal_to_owned_process(pid: int, sig: int) -> None:
    if os.name != "nt":
        try:
            os.killpg(pid, sig)
            return
        except ProcessLookupError:
            return
        except OSError:
            # Older devbootstrap runs did not necessarily create a process group.
            pass
    os.kill(pid, sig)


def wait_until_dead(pid: int, timeout_seconds: int) -> bool:
    deadline = time.monotonic() + max(0, timeout_seconds)
    while time.monotonic() <= deadline:
        if not pid_alive(pid):
            return True
        time.sleep(0.25)
    return not pid_alive(pid)


def stop_owned_target(target: StopTarget, *, timeout_seconds: int, dry_run: bool, force: bool) -> None:
    if target.verification_status == "stale_pid":
        target.action = "stale_removed"
        target.alive_after = False
        return
    if target.verification_status not in {"owned", "owned_limited"}:
        target.action = "skipped"
        target.alive_after = target.alive_before
        target.error = "process did not pass ownership verification"
        return
    if target.pid is None:
        target.action = "skipped"
        target.error = "invalid pid"
        return
    if dry_run:
        target.action = "planned_stop"
        target.alive_after = target.alive_before
        return
    try:
        send_signal_to_owned_process(target.pid, signal.SIGTERM)
    except ProcessLookupError:
        target.action = "stale_removed"
        target.alive_after = False
        return
    except OSError as exc:
        target.action = "failed"
        target.error = f"SIGTERM failed: {exc}"
        target.alive_after = pid_alive(target.pid)
        return
    if wait_until_dead(target.pid, timeout_seconds):
        target.action = "stopped"
        target.alive_after = False
        return
    if not force:
        target.action = "timeout"
        target.alive_after = pid_alive(target.pid)
        target.error = "process did not exit before timeout; force kill disabled"
        return
    kill_signal = getattr(signal, "SIGKILL", signal.SIGTERM)
    try:
        send_signal_to_owned_process(target.pid, kill_signal)
    except ProcessLookupError:
        target.action = "stale_removed"
        target.alive_after = False
        return
    except OSError as exc:
        target.action = "failed"
        target.error = f"force kill failed: {exc}"
        target.alive_after = pid_alive(target.pid)
        return
    if wait_until_dead(target.pid, min(5, max(1, timeout_seconds))):
        target.action = "force_stopped"
        target.alive_after = False
    else:
        target.action = "failed"
        target.alive_after = pid_alive(target.pid)
        target.error = "process still alive after force kill"


def stop_compose_postgres(project_root: Path, *, include_db: bool, dry_run: bool, timeout_seconds: int) -> StopDbAction:
    if not include_db:
        return StopDbAction(status="skipped", message="PostgreSQL compose service is left running by default; pass --include-db to stop it.")
    compose_command, detection = detect_compose_command(project_root)
    if not process_probe_ok(detection):
        return StopDbAction(status="unavailable", message="Docker Compose is not available, so devbootstrap cannot stop postgres service.", evidence=first_output_line(detection))
    command = compose_base_command(compose_command, project_root) + ["stop", POSTGRES_SERVICE_NAME]
    if dry_run:
        return StopDbAction(status="planned", command=command_as_text(command), message="Would stop docker compose postgres service without removing volumes.")
    probe = run_process_probe("compose_stop_postgres", command, cwd=project_root, timeout=max(10, timeout_seconds))
    status = "stopped" if process_probe_ok(probe) else "failed"
    evidence = first_output_line(probe)
    message = "Stopped docker compose postgres service without removing volumes." if status == "stopped" else "Docker compose postgres stop failed."
    return StopDbAction(status=status, command=command_as_text(command), message=message, evidence=evidence)


def build_stop_result(project_root: Path | None, invoked_from: Path, args: argparse.Namespace) -> StopResult:
    run_id_value = run_id("stop")
    result = StopResult(
        generated_at=iso_now(),
        tool_version=TOOL_VERSION,
        project_root=str(project_root) if project_root else None,
        invoked_from=str(invoked_from),
        dry_run=args.dry_run,
        include_db=args.include_db,
        force=not args.no_force,
        timeout_seconds=args.timeout_seconds,
        run_id=run_id_value,
    )
    if project_root is None:
        result.classification = "invalid_project_root"
        result.failures.append({"code": "invalid_project_root", "message": "Could not find project root."})
        return result
    state_path, state, processes = process_table_state(project_root)
    if "_error" in state:
        result.classification = "state_invalid"
        result.failures.append({"code": "state_invalid", "message": f"Could not read state file {rel(state_path, project_root)}: {state.get('_error')}"})
        return result
    if not processes:
        result.warnings.append({"code": "no_tracked_processes", "message": "state.json does not contain tracked backend/frontend processes."})
    for name, entry in processes.items():
        target = stop_target_from_entry(project_root, name, entry)
        stop_owned_target(target, timeout_seconds=args.timeout_seconds, dry_run=args.dry_run, force=not args.no_force)
        result.targets.append(target)
        if target.action in {"skipped", "timeout", "failed"}:
            result.warnings.append({"code": f"{name}_{target.action}", "message": target.error or f"{name} was not stopped."})
    result.db_action = stop_compose_postgres(project_root, include_db=args.include_db, dry_run=args.dry_run, timeout_seconds=args.timeout_seconds)
    if result.db_action.status == "failed":
        result.warnings.append({"code": "postgres_stop_failed", "message": result.db_action.evidence or result.db_action.message})
    # Probe common runtime surfaces after requested stop attempt.
    backend_host, backend_port, _ = parse_backend_host_port(project_root)
    frontend_host, frontend_port, _ = parse_frontend_host_port(project_root)
    db_url = effective_env_values_for(project_root, "backend").get("DATABASE__URL") or effective_env_values_for(project_root, "backend").get("DATABASE_URL")
    db_probe = parse_database_url_probe(db_url)
    if db_probe.host and db_probe.port:
        result.ports_after.append(probe_port("postgres", db_probe.port, host=db_probe.host))
    result.ports_after.append(probe_port("backend", backend_port, host=http_probe_host(backend_host)))
    result.ports_after.append(probe_port("frontend", frontend_port, host=http_probe_host(frontend_host)))
    result.http_after.extend(probe_backend_health(backend_host, backend_port, timeout=0.6))
    result.http_after.append(probe_http("frontend_root", frontend_root_url(frontend_host, frontend_port), timeout=0.6))
    if any(t.action in {"failed", "timeout", "skipped"} for t in result.targets):
        result.classification = "partial"
    elif args.dry_run:
        result.classification = "planned"
    else:
        result.classification = "stopped"
    if any(t.action == "skipped" and t.verification_status == "mismatch" for t in result.targets):
        result.next_actions.append("Inspect skipped tracked PIDs manually; devbootstrap refused to stop them because ownership verification failed.")
    if any(p.open for p in result.ports_after if p.name in {"backend", "frontend"}):
        result.next_actions.append("A backend/frontend port is still open after stop. If it is not a tracked process, inspect it manually before retrying up.")
    if result.db_action and result.db_action.status == "skipped":
        result.next_actions.append("Run `python tools/devbootstrap.py stop --include-db` only when you intentionally want to stop the compose postgres service.")
    if not result.next_actions:
        result.next_actions.append("Run `python tools/devbootstrap.py status` to confirm the environment is clean.")
    return result


def render_stop_report(result: StopResult) -> str:
    lines: list[str] = []
    lines.append("# devbootstrap stop report")
    lines.append("")
    lines.append(f"- Generated at: `{result.generated_at}`")
    lines.append(f"- Tool version: `{result.tool_version}`")
    lines.append(f"- Project root: `{result.project_root or 'not found'}`")
    lines.append(f"- Invoked from: `{result.invoked_from}`")
    lines.append(f"- Run ID: `{result.run_id}`")
    lines.append(f"- Dry run: `{result.dry_run}`")
    lines.append(f"- Include DB: `{result.include_db}`")
    lines.append(f"- Classification: `{result.classification}`")
    lines.append("")
    lines.append("## Tracked process actions")
    lines.append("")
    lines.append("| Name | PID | Alive before | Verification | Action | Alive after | Evidence |")
    lines.append("|---|---:|---|---|---|---|---|")
    if result.targets:
        for target in result.targets:
            lines.append(
                f"| `{target.name}` | {target.pid if target.pid is not None else ''} | {target.alive_before} | "
                f"{target.verification_status} | {target.action} | {target.alive_after} | `{target.verification_evidence or target.error or ''}` |"
            )
    else:
        lines.append("| | | | | no tracked processes | | |")
    lines.append("")
    lines.append("## PostgreSQL compose action")
    lines.append("")
    if result.db_action:
        lines.append(f"- Status: `{result.db_action.status}`")
        if result.db_action.command:
            lines.append(f"- Command: `{result.db_action.command}`")
        lines.append(f"- Message: {result.db_action.message}")
        if result.db_action.evidence:
            lines.append(f"- Evidence: `{result.db_action.evidence}`")
    else:
        lines.append("- Not evaluated.")
    lines.append("")
    lines.append("## Ports after stop")
    lines.append("")
    lines.append("| Name | Address | Status | Evidence |")
    lines.append("|---|---|---|---|")
    for port in result.ports_after:
        status = "open" if port.open else "closed/unreachable"
        lines.append(f"| {port.name} | `{port.host}:{port.port}` | {status} | `{port.error or ''}` |")
    lines.append("")
    lines.append("## HTTP after stop")
    lines.append("")
    lines.append("| Name | URL | Status | Evidence |")
    lines.append("|---|---|---|---|")
    for probe in result.http_after:
        status = f"HTTP {probe.status}" if probe.reachable and probe.status is not None else "unreachable"
        lines.append(f"| {probe.name} | `{probe.url}` | {status} | `{probe.error or f'{probe.duration_ms} ms'}` |")
    lines.append("")
    lines.append("## Findings")
    lines.append("")
    if not result.failures and not result.warnings:
        lines.append("- No blocking findings from stop.")
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


def write_stop_reports(project_root: Path, result: StopResult, report_dir: Path) -> None:
    result.report_dir = rel(report_dir, project_root)
    write_report_json(report_dir / "stop.json", result, command="stop")
    (report_dir / "report.md").write_text(render_stop_report(result), encoding="utf-8")


def update_state_after_stop(project_root: Path, result: StopResult, report_dir: Path) -> None:
    if result.dry_run:
        append_report_to_state(project_root, report_dir, result.run_id)
        return
    state_path, state, processes = process_table_state(project_root)
    if "_error" in state:
        return
    removable = {target.name for target in result.targets if target.action in {"stopped", "force_stopped", "stale_removed"}}
    for name in removable:
        processes.pop(name, None)
    state["version"] = STATE_VERSION
    state["processes"] = processes
    if not processes and state.get("activeRunId"):
        state["activeRunId"] = None
    last_reports = state.get("lastReports") if isinstance(state.get("lastReports"), list) else []
    last_reports.append(rel(report_dir, project_root))
    state["lastReports"] = last_reports[-20:]
    state_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(state_path, state)


def print_stop_summary(result: StopResult) -> None:
    print_header("devbootstrap stop")
    print(f"Tool version: {result.tool_version}")
    print(f"Project root: {result.project_root or 'not found'}")
    print(f"Classification: {result.classification}")
    print(f"Dry run: {result.dry_run}")
    print(f"Include DB: {result.include_db}")
    if result.targets:
        print("\nTracked processes:")
        for target in result.targets:
            print(
                f"  - {target.name}: pid={target.pid} alive_before={target.alive_before} "
                f"verify={target.verification_status} action={target.action} alive_after={target.alive_after}"
            )
            if target.error:
                print(f"    error: {target.error}")
    else:
        print("\nTracked processes: none")
    if result.db_action:
        command = f" command={result.db_action.command}" if result.db_action.command else ""
        print(f"\nPostgres: {result.db_action.status} — {result.db_action.message}{command}")
    if result.ports_after:
        print("\nPorts after stop:")
        for port in result.ports_after:
            status = "open" if port.open else "closed"
            print(f"  - {port.name} {port.host}:{port.port}: {status}")
    if result.failures or result.warnings:
        print("\nFindings:")
        for failure in result.failures:
            print(f"  - FAIL {failure['code']}: {failure['message']}")
        for warning in result.warnings:
            print(f"  - WARN {warning['code']}: {warning['message']}")
    else:
        print("\nFindings: no blocking findings from stop")
    if result.next_actions:
        print("\nNext safe actions:")
        for action in result.next_actions:
            print(f"  - {action}")
    if result.report_dir:
        print(f"\nReport: {result.report_dir}/report.md")


def command_stop(args: argparse.Namespace) -> int:
    invoked_from = Path.cwd()
    project_root = find_project_root(invoked_from)
    result = build_stop_result(project_root, invoked_from, args)
    report_dir: Path | None = None
    if project_root is not None and not args.no_write_report:
        report_dir = create_report_dir(project_root, "stop")
        write_stop_reports(project_root, result, report_dir)
        update_state_after_stop(project_root, result, report_dir)
    print_stop_summary(result)
    if args.json:
        print("\nJSON:")
        print(json.dumps(as_jsonable(result), ensure_ascii=False, indent=2))
    return 1 if result.failures or any(t.action in {"failed", "timeout"} for t in result.targets) else 0


def build_status_snapshot(project_root: Path) -> dict[str, Any]:
    state = summarize_state(project_root)
    backend_host, backend_port, backend_warning = parse_backend_host_port(project_root)
    frontend_host, frontend_port, frontend_warning = parse_frontend_host_port(project_root)
    backend_probe_host = http_probe_host(backend_host)
    frontend_probe_host = http_probe_host(frontend_host)
    db_env = effective_env_values_for(project_root, "backend")
    db_url = db_env.get("DATABASE__URL") or db_env.get("DATABASE_URL")
    db_probe = parse_database_url_probe(db_url)
    ports: list[PortProbe] = []
    if db_probe.host and db_probe.port:
        ports.append(probe_port("postgres", db_probe.port, host=db_probe.host))
    ports.append(probe_port("backend", backend_port, host=backend_probe_host))
    ports.append(probe_port("frontend", frontend_port, host=frontend_probe_host))
    http = probe_backend_health(backend_host, backend_port, timeout=0.8)
    http.append(probe_http("frontend_root", frontend_root_url(frontend_host, frontend_port), timeout=0.8))
    compose_command, compose_detection = detect_compose_command(project_root)
    compose_status = probe_compose_status(project_root, compose_command) if process_probe_ok(compose_detection) else compose_detection
    warnings = [warning for warning in [backend_warning, frontend_warning] if warning]
    return {
        "projectRoot": str(project_root),
        "state": state,
        "ports": as_jsonable(ports),
        "http": as_jsonable(http),
        "composeStatus": as_jsonable(compose_status),
        "warnings": warnings,
    }


def print_status_snapshot(snapshot: dict[str, Any]) -> None:
    print(f"Project root: {snapshot.get('projectRoot')}")
    state = snapshot.get("state", {})
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
    print("\nPorts:")
    for port in snapshot.get("ports", []):
        status = "open" if port.get("open") else "closed"
        print(f"  - {port.get('name')} {port.get('host')}:{port.get('port')}: {status}")
    print("\nHTTP:")
    for probe in snapshot.get("http", []):
        if probe.get("reachable"):
            print(f"  - {probe.get('name')}: HTTP {probe.get('status')} ({probe.get('duration_ms')} ms)")
        else:
            print(f"  - {probe.get('name')}: unreachable")
    compose = snapshot.get("composeStatus") or {}
    if compose:
        compose_state = "ok" if compose.get("returncode") == 0 else "unavailable" if not compose.get("available") else f"exit {compose.get('returncode')}"
        print(f"\nCompose postgres: {compose_state} — {first_output_line(ProcessProbe(**compose)) if isinstance(compose, dict) and {'name','command','available'}.issubset(compose.keys()) else compose.get('error', '')}")
    reports = state.get("lastReports") or []
    if reports:
        print("\nLast reports:")
        for report in reports[-5:]:
            print(f"  - {report}")
    warnings = snapshot.get("warnings") or []
    if warnings:
        print("\nWarnings:")
        for warning in warnings:
            print(f"  - {warning}")

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
    snapshot = build_status_snapshot(project_root)
    print_status_snapshot(snapshot)
    if args.json:
        print("\nJSON:")
        print(json.dumps(snapshot, ensure_ascii=False, indent=2))
    return 0



@dataclass
class SelfCheckCase:
    name: str
    status: str
    message: str
    evidence: str | None = None


@dataclass
class SelfCheckResult:
    generated_at: str
    tool_version: str
    project_root: str | None
    invoked_from: str
    cases: list[SelfCheckCase] = field(default_factory=list)
    failures: list[dict[str, str]] = field(default_factory=list)
    warnings: list[dict[str, str]] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)
    classification: str = "unknown"
    report_dir: str | None = None


def self_check_case(result: SelfCheckResult, name: str, func: Any) -> None:
    try:
        evidence = func()
    except AssertionError as exc:
        message = str(exc) or "assertion failed"
        result.cases.append(SelfCheckCase(name=name, status="fail", message=message))
        result.failures.append({"code": name, "message": message})
    except Exception as exc:
        message = f"unexpected error: {exc}"
        result.cases.append(SelfCheckCase(name=name, status="fail", message=message, evidence=exc.__class__.__name__))
        result.failures.append({"code": name, "message": message})
    else:
        result.cases.append(SelfCheckCase(name=name, status="ok", message="passed", evidence=evidence))


def case_self_check_version_and_timeout_policy() -> str:
    assert TOOL_VERSION == "2.0.0-draft", f"expected TOOL_VERSION 2.0.0-draft, got {TOOL_VERSION}"
    required = {
        "probe_command",
        "port_probe",
        "http_probe",
        "postgres_ready",
        "cargo_metadata",
        "cargo_check",
        "backend_ready",
        "npm_install",
        "frontend_ready",
        "smoke_step",
        "up_step",
        "stop_grace",
        "release_gate",
    }
    missing = sorted(required.difference(TIMEOUT_POLICY))
    assert not missing, "missing timeout policy keys: " + ", ".join(missing)
    for key, value in TIMEOUT_POLICY.items():
        assert isinstance(value, (int, float)) and value > 0, f"timeout {key} must be positive"
    return f"{len(TIMEOUT_POLICY)} timeout defaults checked"


def case_self_check_env_parser_and_masking() -> str:
    with tempfile.TemporaryDirectory(prefix="devbootstrap-selfcheck-env-") as tmp:
        env_file = Path(tmp) / ".env"
        env_file.write_text(
            "\n".join(
                [
                    "# comment",
                    "APP_NAME=p2p",
                    "export QUOTED='hello world'",
                    "SECRET_TOKEN=super-secret",
                    "DATABASE__URL=postgres://planner:pw@localhost:5432/p2p_planner",
                    "BROKEN_LINE",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        values, warnings = parse_env_file(env_file)
    assert values["APP_NAME"] == "p2p"
    assert values["QUOTED"] == "hello world"
    assert values["SECRET_TOKEN"] == "super-secret"
    assert warnings and "ignored non KEY=VALUE line" in warnings[0]
    assert mask_value("SECRET_TOKEN", values["SECRET_TOKEN"]) == "***"
    masked_db = mask_value("DATABASE__URL", values["DATABASE__URL"])
    assert "pw" not in masked_db and ":***@" in masked_db, masked_db
    return "env parser warnings and secret masking checked"


def case_self_check_database_url_parse() -> str:
    probe = parse_database_url_probe("postgres://planner:secret@127.0.0.1:15432/p2p_planner_dev?sslmode=disable")
    assert probe.raw_present is True
    assert probe.scheme == "postgres"
    assert probe.host == "127.0.0.1"
    assert probe.port == 15432
    assert probe.database == "p2p_planner_dev"
    assert probe.username == "planner"
    assert probe.has_password is True
    assert probe.masked_url and "secret" not in probe.masked_url
    return f"{probe.host}:{probe.port}/{probe.database}"


def case_self_check_failure_classifiers() -> str:
    assert classify_backend_failure("error: address already in use", "x") == "port_conflict"
    assert classify_backend_failure("migration 6 was previously applied but is missing in the resolved migrations", "x") == "migration_drift"
    assert classify_backend_failure("database foo does not exist", "x") == "database_missing"
    assert classify_frontend_failure("Error: Cannot find module '@vitejs/plugin-react'", "x") == "frontend_dependency_missing"
    assert classify_smoke_process_failure("quick", "NetworkError when attempting to fetch resource") == "runtime_unreachable"
    psql = ProcessProbe(name="psql", command=["psql"], available=True, returncode=2, stderr="password authentication failed for user planner")
    assert classify_psql_failure(psql, None) == "auth_failed"
    return "backend/frontend/postgres/smoke classifiers checked"


def case_self_check_project_discovery() -> str:
    with tempfile.TemporaryDirectory(prefix="devbootstrap-selfcheck-root-") as tmp:
        root = Path(tmp) / "project"
        for relative in ["backend", "frontend", "docs", "tools"]:
            (root / relative).mkdir(parents=True, exist_ok=True)
        (root / "docker-compose.dev.yml").write_text("services: {}\n", encoding="utf-8")
        found_from_tools = find_project_root(root / "tools")
        found_from_nested = find_project_root(Path(tmp))
    assert found_from_tools == root.resolve()
    assert found_from_nested == root.resolve()
    return "root discovery from tools/ and parent workspace checked"


def case_self_check_env_diff() -> str:
    with tempfile.TemporaryDirectory(prefix="devbootstrap-selfcheck-plan-") as tmp:
        root = Path(tmp)
        (root / "backend").mkdir()
        (root / "frontend").mkdir()
        (root / "docs").mkdir()
        (root / "docker-compose.dev.yml").write_text("services: {}\n", encoding="utf-8")
        (root / "backend" / ".env.example").write_text("DATABASE__URL=postgres://u:p@localhost:5432/a\nHTTP__HOST=127.0.0.1\n", encoding="utf-8")
        (root / "backend" / ".env").write_text("DATABASE__URL=postgres://u:p@localhost:5432/b\nEXTRA_KEY=yes\n", encoding="utf-8")
        (root / "frontend" / ".env.example").write_text("VITE_API_BASE_URL=http://127.0.0.1:18080/api/v1\n", encoding="utf-8")
        result = build_env_plan(root, root, mode="plan")
    backend = next(item for item in result.files if item.name == "backend")
    frontend = next(item for item in result.files if item.name == "frontend")
    assert "HTTP__HOST" in backend.missing_keys
    assert "EXTRA_KEY" in backend.extra_keys
    assert frontend.target_exists is False
    assert any(action.code == "create_env_file" and action.path == "frontend/.env.local" for action in result.actions)
    return "env diff detects missing, extra and absent target files"


def case_self_check_report_json_contract() -> str:
    with tempfile.TemporaryDirectory(prefix="devbootstrap-selfcheck-report-") as tmp:
        path = Path(tmp) / "fixture.json"
        write_report_json(
            path,
            {
                "generated_at": iso_now(),
                "tool_version": TOOL_VERSION,
                "failures": [],
                "warnings": [],
            },
            command="self-check-fixture",
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schemaVersion"] == REPORT_SCHEMA_VERSION
    assert payload["command"] == "self-check-fixture"
    assert payload["toolVersion"] == TOOL_VERSION
    assert payload["status"] == "ok"
    assert payload.get("generatedAt")
    return "schemaVersion/command/toolVersion/status/generatedAt envelope checked"


def case_self_check_report_markdown_contract() -> str:
    result = DiagnoseResult(
        generated_at=iso_now(),
        tool_version=TOOL_VERSION,
        project_root=None,
        invoked_from="self-check",
        platform={"system": platform.system(), "python": sys.version.split()[0]},
    )
    rendered = render_report(result)
    required_sections = ["# devbootstrap diagnose report", "## Findings", "## Next safe actions"]
    for section in required_sections:
        assert section in rendered, f"missing report section {section}"
    return "minimal report.md sections checked"


def case_self_check_release_gates_json_envelope() -> str:
    result = ReleaseGatesResult(
        generated_at="2026-05-24T00:00:00+00:00",
        tool_version=TOOL_VERSION,
        project_root="/tmp/project",
        invoked_from="/tmp/project",
        run_id="selfcheck-release-gates",
        dry_run=False,
        timeout_seconds=123,
        report_dir=".dev-bootstrap/runs/selfcheck-release-gates",
        archive_path=".dev-bootstrap/runs/selfcheck-release-gates/release-gates_selfcheck.zip",
        overall_status="ok",
        classification="release_gates_ok",
        gates=[GateResult(name="fixture_gate", status="ok", classification="ok", message="gate completed", cwd=".", command=["true"], log_path="logs/01_fixture_gate.log")],
    )
    payload = release_gates_json_payload(result)
    assert payload["schemaVersion"] == 1
    assert payload["command"] == "release-gates"
    assert payload["toolVersion"] == TOOL_VERSION
    assert payload["overallStatus"] == "ok"
    assert payload["archivePath"].endswith(".zip")
    assert payload["gates"][0]["name"] == "fixture_gate"
    return "release-gates JSON envelope checked"


def case_self_check_release_gates_summary_rendering() -> str:
    result = ReleaseGatesResult(
        generated_at="2026-05-24T00:00:00+00:00",
        tool_version=TOOL_VERSION,
        project_root="/tmp/project",
        invoked_from="/tmp/project",
        run_id="selfcheck-release-gates",
        dry_run=True,
        timeout_seconds=123,
        overall_status="dry_run",
        classification="release_gates_dry_run",
        gates=[GateResult(name="frontend_build", status="planned", classification="dry_run", message="would run gate command", cwd="frontend", command=["npm", "run", "build"], log_path="logs/07_frontend_build.log")],
    )
    rendered = render_release_gates_summary(result)
    assert "# release-gates summary" in rendered
    assert "Overall: dry_run" in rendered
    assert "> npm run build" in rendered
    assert "logs/07_frontend_build.log" in rendered
    return "release-gates summary rendering checked"


def case_self_check_release_gates_archive_exclusions() -> str:
    with tempfile.TemporaryDirectory(prefix="devbootstrap-selfcheck-rg-archive-") as tmp:
        root = Path(tmp) / "run"
        (root / "logs").mkdir(parents=True)
        (root / "logs" / "01_ok.log").write_text("ok\n", encoding="utf-8")
        (root / "summary.txt").write_text("summary\n", encoding="utf-8")
        (root / "__pycache__").mkdir()
        (root / "__pycache__" / "bad.pyc").write_bytes(b"bad")
        (root / ".pytest_cache").mkdir()
        (root / ".pytest_cache" / "bad").write_text("bad", encoding="utf-8")
        (root / "node_modules").mkdir()
        (root / "node_modules" / "bad.txt").write_text("bad", encoding="utf-8")
        (root / ".env").write_text("SECRET=bad", encoding="utf-8")
        (root / "frontend.tsbuildinfo").write_text("generated", encoding="utf-8")
        archive_path = root / "release-gates_selfcheck.zip"
        create_release_gates_archive(root, archive_path)
        with zipfile.ZipFile(archive_path) as zf:
            names = set(zf.namelist())
    assert "summary.txt" in names
    assert "logs/01_ok.log" in names
    forbidden = [
        name
        for name in names
        if "__pycache__" in name
        or ".pytest_cache" in name
        or "node_modules" in name
        or name == ".env"
        or name.endswith((".pyc", ".tsbuildinfo"))
    ]
    assert not forbidden, "forbidden archive entries: " + ", ".join(sorted(forbidden))
    return "release-gates archive exclusion rules checked"


def case_self_check_release_gates_ignored_classifier() -> str:
    stdout = "test result: ok. 12 passed; 0 failed; 2 ignored; 0 measured; 0 filtered out"
    status, classification, message = classify_gate_output("backend_cargo_test_default", stdout, "", None, 0)
    assert status == "partial_pass"
    assert classification == "critical_tests_ignored"
    assert "ignored" in message
    return "ignored Rust tests classifier checked"


def case_self_check_release_gates_playwright_classifier() -> str:
    stderr = "Error: browserType.launch: Executable doesn't exist. Please run: npx playwright install"
    status, classification, message = classify_gate_output("frontend_browser_smoke", "", stderr, None, 1)
    assert status == "infra_failed"
    assert classification == "browser_smoke_prerequisite"
    assert "Playwright" in message
    return "Playwright missing-browser classifier checked"



def case_self_check_managed_test_db_url_derivation() -> str:
    source = "postgres://planner:secret@127.0.0.1:15432/p2p_planner_dev?sslmode=disable"
    managed = replace_database_name_in_url(source, "p2pkanban_rg_test")
    maintenance = replace_database_name_in_url(source, "postgres")
    assert managed == "postgres://planner:secret@127.0.0.1:15432/p2pkanban_rg_test?sslmode=disable"
    assert maintenance == "postgres://planner:secret@127.0.0.1:15432/postgres?sslmode=disable"
    env = release_gate_managed_db_env(managed)
    assert env["DATABASE__URL"] == managed
    assert env["DATABASE_URL"] == managed
    assert env["TEST_DATABASE_URL"] == managed
    assert "secret" not in mask_database_url(managed)
    return "managed test DB URL derivation and env override checked"


def case_self_check_managed_test_db_specs() -> str:
    with tempfile.TemporaryDirectory(prefix="devbootstrap-selfcheck-rg-managed-") as tmp:
        root = Path(tmp)
        (root / "backend").mkdir()
        (root / "frontend").mkdir()
        (root / "docs").mkdir()
        (root / "docker-compose.dev.yml").write_text("services: {}\n", encoding="utf-8")
        (root / "backend" / ".env.example").write_text("DATABASE__URL=postgres://u:p@127.0.0.1:5432/dev\n", encoding="utf-8")
        (root / "frontend" / "package.json").write_text(json.dumps({"scripts": {}, "devDependencies": {}}), encoding="utf-8")
        (root / "frontend" / "package-lock.json").write_text("{}", encoding="utf-8")
        managed_url = "postgres://u:p@127.0.0.1:5432/p2pkanban_rg_selfcheck"
        specs = build_release_gate_specs(root, managed_test_db_url=managed_url, managed_test_db_requested=True)
        by_name = {spec.name: spec for spec in specs}
    db_spec = by_name["backend_cargo_test_db_ignored"]
    smoke_spec = by_name["backend_python_smoke_first"]
    assert db_spec.env_extra["TEST_DATABASE_URL"] == managed_url
    assert db_spec.env_extra["DATABASE__URL"] == managed_url
    assert smoke_spec.env_extra["TEST_DATABASE_URL"] == managed_url
    assert smoke_spec.details["managedTestDb"] is True
    return "release-gates managed DB specs carry safe env overrides"


def case_self_check_managed_runtime_specs() -> str:
    with tempfile.TemporaryDirectory(prefix="devbootstrap-selfcheck-rg-runtime-") as tmp:
        root = Path(tmp)
        (root / "backend").mkdir()
        (root / "frontend").mkdir()
        (root / "docs").mkdir()
        (root / "docker-compose.dev.yml").write_text("services: {}\n", encoding="utf-8")
        (root / "backend" / ".env.example").write_text("DATABASE__URL=postgres://u:p@127.0.0.1:5432/dev\n", encoding="utf-8")
        (root / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test:browser": "playwright test"}, "devDependencies": {"@playwright/test": "1.55.0"}}), encoding="utf-8")
        (root / "frontend" / "package-lock.json").write_text("{}", encoding="utf-8")
        api_base = "http://127.0.0.1:39001/api/v1"
        frontend_url = "http://127.0.0.1:39002/"
        specs = build_release_gate_specs(
            root,
            allow_dev_db_write=True,
            managed_runtime_requested=True,
            managed_backend_api_base_url=api_base,
            managed_frontend_url=frontend_url,
            managed_frontend_host="127.0.0.1",
            managed_frontend_port=39002,
            dry_run=True,
        )
        by_name = {spec.name: spec for spec in specs}
    smoke_spec = by_name["backend_python_smoke_first"]
    browser_spec = by_name["frontend_browser_smoke"]
    assert smoke_spec.env_extra["BASE_URL"] == api_base
    assert browser_spec.env_extra["VITE_API_BASE_URL"] == api_base
    assert browser_spec.env_extra["PLAYWRIGHT_BASE_URL"] == frontend_url.rstrip("/")
    assert browser_spec.env_extra["PLAYWRIGHT_FRONTEND_PORT"] == "39002"
    return "release-gates managed runtime specs carry dynamic URL env overrides"


def case_self_check_release_gates_frontend_dependency_preflight() -> str:
    with tempfile.TemporaryDirectory(prefix="devbootstrap-selfcheck-rg-frontend-") as tmp:
        root = Path(tmp)
        frontend = root / "frontend"
        frontend.mkdir()
        (root / "backend").mkdir()
        (frontend / "package.json").write_text(
            json.dumps(
                {
                    "scripts": {
                        "build": "tsc -b && vite build",
                        "test:run": "vitest run",
                        "test:browser": "playwright test e2e/smoke/auth-and-workspaces.smoke.spec.ts",
                    },
                    "devDependencies": {"@playwright/test": "1.55.0"},
                }
            ),
            encoding="utf-8",
        )
        (frontend / "package-lock.json").write_text("{}", encoding="utf-8")
        specs = build_release_gate_specs(root)
        by_name = {spec.name: spec for spec in specs}
    for name in ["frontend_build", "frontend_unit_integration", "frontend_browser_smoke"]:
        spec = by_name[name]
        assert spec.skip_status == "infra_failed", name
        assert spec.skip_classification == "frontend_dependencies_missing", name
        assert "--prepare-deps" in (spec.skip_reason or ""), name
    return "release-gates frontend dependency preflight checked"


def case_self_check_frontend_prepare_modes() -> str:
    with tempfile.TemporaryDirectory(prefix="devbootstrap-selfcheck-frontend-modes-") as tmp:
        root = Path(tmp)
        frontend = root / "frontend"
        frontend.mkdir(parents=True)
        result = FrontendResult(
            generated_at=iso_now(),
            tool_version=TOOL_VERSION,
            project_root=str(root),
            invoked_from=str(root),
            mode="prepare-frontend",
            package_json_exists=True,
            package_lock_exists=True,
            node_modules_exists=False,
            install_marker_valid=False,
        )
        assert frontend_prepare_should_install(result, "missing")[0] is True
        result.node_modules_exists = True
        assert frontend_prepare_should_install(result, "missing")[0] is False
        assert frontend_prepare_should_install(result, "stale")[0] is True
        assert normalize_frontend_prepare_dep_mode("missing-or-stale") == "stale"
    return "frontend dependency preparation modes checked"


def case_self_check_clean_machine_profiles() -> str:
    dry = release_gate_clean_machine_commands("dry")
    deps = release_gate_clean_machine_commands("deps")
    runtime = release_gate_clean_machine_commands("runtime")
    assert any(command[:3] == [sys.executable, "tools/devbootstrap.py", "up"] and "--dry-run" in command for command in dry)
    assert not any(command[:3] == ["cargo", "test", "--no-run"] for command in dry)
    assert any(command[:3] == ["cargo", "test", "--no-run"] for command in deps)
    assert any("release-gates" in command and "--managed-runtime" in command for command in runtime)
    assert normalize_clean_machine_profile("clean-machine-dry") == "dry"
    return "clean-machine sandbox profiles and command plan checked"


def case_self_check_release_gates_targeted_next_actions() -> str:
    result = ReleaseGatesResult(
        generated_at="2026-05-24T00:00:00+00:00",
        tool_version=TOOL_VERSION,
        project_root="/tmp/project",
        invoked_from="/tmp/project",
        run_id="selfcheck-release-gates-actions",
        dry_run=False,
        timeout_seconds=123,
        gates=[
            GateResult(
                name="frontend_build",
                status="infra_failed",
                classification="frontend_dependencies_missing",
                message="frontend/node_modules is missing",
                cwd="frontend",
                command=["npm", "run", "build"],
            ),
            GateResult(
                name="backend_cargo_test_db_ignored",
                status="skipped_prerequisite",
                classification="db_test_prerequisite_missing",
                message="TEST_DATABASE_URL is absent",
                cwd="backend",
                command=["cargo", "test", "--", "--include-ignored"],
            ),
        ],
    )
    finalize_release_gates_result(result)
    joined = "\n".join(result.next_actions)
    assert result.overall_status == "infra_failed"
    assert "--prepare-deps" in joined
    assert "TEST_DATABASE_URL" in joined
    assert "release-gates-test-database.md" in joined
    return "targeted release-gates next actions checked"


def case_self_check_release_gates_keep_going_behavior() -> str:
    with tempfile.TemporaryDirectory(prefix="devbootstrap-selfcheck-rg-keepgoing-") as tmp:
        root = Path(tmp)
        logs = root / "logs"
        logs.mkdir()
        first = run_gate_process_step(
            project_root=root,
            logs_dir=logs,
            index=1,
            spec=GateSpec(name="first_missing_command", cwd=".", command=["definitely-missing-devbootstrap-command-xyz"]),
            timeout_seconds=5,
        )
        second = run_gate_process_step(
            project_root=root,
            logs_dir=logs,
            index=2,
            spec=GateSpec(name="second_still_runs", cwd=".", command=[sys.executable, "-c", "print('ok')"]),
            timeout_seconds=5,
        )
    assert first.status == "infra_failed"
    assert second.status == "ok"
    assert first.log_path and second.log_path
    overall, classification = release_gates_overall_status([first, second], dry_run=False)
    assert overall == "infra_failed"
    assert classification == "release_gates_infra_failed"
    return "keep-going execution after a failed prerequisite checked"


def build_self_check_result(project_root: Path | None, invoked_from: Path) -> SelfCheckResult:
    result = SelfCheckResult(
        generated_at=iso_now(),
        tool_version=TOOL_VERSION,
        project_root=str(project_root) if project_root else None,
        invoked_from=str(invoked_from),
    )
    self_check_case(result, "version_and_timeout_policy", case_self_check_version_and_timeout_policy)
    self_check_case(result, "env_parser_and_masking", case_self_check_env_parser_and_masking)
    self_check_case(result, "database_url_parse", case_self_check_database_url_parse)
    self_check_case(result, "failure_classifiers", case_self_check_failure_classifiers)
    self_check_case(result, "project_discovery", case_self_check_project_discovery)
    self_check_case(result, "env_diff", case_self_check_env_diff)
    self_check_case(result, "report_json_contract", case_self_check_report_json_contract)
    self_check_case(result, "report_markdown_contract", case_self_check_report_markdown_contract)
    self_check_case(result, "release_gates_json_envelope", case_self_check_release_gates_json_envelope)
    self_check_case(result, "release_gates_summary_rendering", case_self_check_release_gates_summary_rendering)
    self_check_case(result, "release_gates_archive_exclusions", case_self_check_release_gates_archive_exclusions)
    self_check_case(result, "release_gates_ignored_classifier", case_self_check_release_gates_ignored_classifier)
    self_check_case(result, "release_gates_playwright_classifier", case_self_check_release_gates_playwright_classifier)
    self_check_case(result, "managed_test_db_url_derivation", case_self_check_managed_test_db_url_derivation)
    self_check_case(result, "managed_test_db_specs", case_self_check_managed_test_db_specs)
    self_check_case(result, "managed_runtime_specs", case_self_check_managed_runtime_specs)
    self_check_case(result, "release_gates_frontend_dependency_preflight", case_self_check_release_gates_frontend_dependency_preflight)
    self_check_case(result, "frontend_prepare_modes", case_self_check_frontend_prepare_modes)
    self_check_case(result, "clean_machine_profiles", case_self_check_clean_machine_profiles)
    self_check_case(result, "release_gates_targeted_next_actions", case_self_check_release_gates_targeted_next_actions)
    self_check_case(result, "release_gates_keep_going_behavior", case_self_check_release_gates_keep_going_behavior)
    if result.failures:
        result.classification = "failed"
        result.next_actions.append("Fix failing self-check cases before using devbootstrap as the v1 routine entrypoint.")
    else:
        result.classification = "ok"
        result.next_actions.append("devbootstrap internal fixtures passed; run `python tools/devbootstrap.py diagnose` or `up --dry-run` next.")
    return result


def render_self_check_report(result: SelfCheckResult) -> str:
    lines: list[str] = []
    lines.append("# devbootstrap self-check report")
    lines.append("")
    lines.append(f"- Generated at: `{result.generated_at}`")
    lines.append(f"- Tool version: `{result.tool_version}`")
    lines.append(f"- Project root: `{result.project_root or 'not found'}`")
    lines.append(f"- Invoked from: `{result.invoked_from}`")
    lines.append(f"- Classification: `{result.classification}`")
    lines.append("")
    lines.append("## Cases")
    lines.append("")
    lines.append("| Case | Status | Message | Evidence |")
    lines.append("|---|---|---|---|")
    for case in result.cases:
        lines.append(f"| `{case.name}` | {case.status} | {case.message} | `{case.evidence or ''}` |")
    lines.append("")
    lines.append("## Findings")
    lines.append("")
    if not result.failures and not result.warnings:
        lines.append("- No blocking findings from self-check.")
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


def write_self_check_reports(project_root: Path, result: SelfCheckResult) -> Path:
    report_dir = create_report_dir(project_root, "self-check")
    result.report_dir = rel(report_dir, project_root)
    write_report_json(report_dir / "self-check.json", result, command="self-check")
    (report_dir / "report.md").write_text(render_self_check_report(result), encoding="utf-8")
    append_report_to_state(project_root, report_dir, report_dir.name)
    return report_dir


def print_self_check_summary(result: SelfCheckResult) -> None:
    print_header("devbootstrap self-check")
    print(f"Tool version: {result.tool_version}")
    print(f"Project root: {result.project_root or 'not found'}")
    print(f"Classification: {result.classification}")
    print("\nCases:")
    for case in result.cases:
        evidence = f" ({case.evidence})" if case.evidence else ""
        print(f"  - {case.status.upper()} {case.name}: {case.message}{evidence}")
    if result.next_actions:
        print("\nNext actions:")
        for action in result.next_actions:
            print(f"  - {action}")


def command_self_check(args: argparse.Namespace) -> int:
    invoked_from = Path.cwd()
    project_root = find_project_root(invoked_from)
    result = build_self_check_result(project_root, invoked_from)
    if project_root is not None and not args.no_write_report:
        write_self_check_reports(project_root, result)
    print_self_check_summary(result)
    if args.json:
        print("\nJSON:")
        print(json.dumps(as_jsonable(result), ensure_ascii=False, indent=2))
    return 1 if result.failures else 0

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
    start_db.add_argument("--timeout-seconds", type=int, default=TIMEOUT_POLICY["postgres_ready"], help="How long to wait for PostgreSQL readiness after compose start.")
    start_db.add_argument("--no-write-report", action="store_true", help="Do not create .dev-bootstrap report files.")
    start_db.add_argument("--json", action="store_true", help="Also print machine-readable JSON to stdout.")
    start_db.set_defaults(func=command_start_db)

    check_backend = subparsers.add_parser("check-backend", help="Run backend Rust preflight checks: cargo metadata and cargo check.")
    check_backend.add_argument("--dry-run", action="store_true", help="Show what would be checked without running cargo metadata/check.")
    check_backend.add_argument("--metadata-timeout-seconds", type=int, default=TIMEOUT_POLICY["cargo_metadata"], help="Timeout for cargo metadata.")
    check_backend.add_argument("--timeout-seconds", type=int, default=TIMEOUT_POLICY["cargo_check"], help="Timeout for cargo check.")
    check_backend.add_argument("--no-write-report", action="store_true", help="Do not create .dev-bootstrap report files.")
    check_backend.add_argument("--json", action="store_true", help="Also print machine-readable JSON to stdout.")
    check_backend.set_defaults(func=command_check_backend)

    start_backend = subparsers.add_parser("start-backend", help="Start backend with cargo run, capture logs and wait for health.")
    start_backend.add_argument("--dry-run", action="store_true", help="Show what would be started without running cargo run.")
    start_backend.add_argument("--timeout-seconds", type=int, default=TIMEOUT_POLICY["backend_ready"], help="How long to wait for backend health after cargo run.")
    start_backend.add_argument("--no-write-report", action="store_true", help="Skip report files when used with --dry-run; real start still writes logs/state.")
    start_backend.add_argument("--json", action="store_true", help="Also print machine-readable JSON to stdout.")
    start_backend.set_defaults(func=command_start_backend)


    prepare_frontend = subparsers.add_parser("prepare-frontend", help="Install or verify frontend npm dependencies with a devbootstrap marker.")
    prepare_frontend.add_argument("--dry-run", action="store_true", help="Show whether npm ci/install would run without changing node_modules.")
    prepare_frontend.add_argument("--force-install", action="store_true", help="Compatibility alias for --install-mode=always.")
    prepare_frontend.add_argument("--install-mode", choices=["never", "missing", "stale", "missing-or-stale", "always"], default=DEFAULT_FRONTEND_PREPARE_DEP_MODE, help="Dependency preparation policy: never, missing, stale/missing-or-stale, or always.")
    prepare_frontend.add_argument("--allow-npm-install-without-lock", action="store_true", help="Allow fallback to npm install when frontend/package-lock.json is absent; disabled by default for reproducibility.")
    prepare_frontend.add_argument("--timeout-seconds", type=int, default=TIMEOUT_POLICY["npm_install"], help="Timeout for npm ci/install.")
    prepare_frontend.add_argument("--no-write-report", action="store_true", help="Do not create .dev-bootstrap report files.")
    prepare_frontend.add_argument("--json", action="store_true", help="Also print machine-readable JSON to stdout.")
    prepare_frontend.set_defaults(func=command_prepare_frontend)

    start_frontend = subparsers.add_parser("start-frontend", help="Start frontend with npm run dev, capture logs and wait for Vite root.")
    start_frontend.add_argument("--dry-run", action="store_true", help="Show what would be started without running npm run dev.")
    start_frontend.add_argument("--timeout-seconds", type=int, default=TIMEOUT_POLICY["frontend_ready"], help="How long to wait for frontend root after npm run dev.")
    start_frontend.add_argument("--no-write-report", action="store_true", help="Skip report files when used with --dry-run; real start still writes logs/state.")
    start_frontend.add_argument("--json", action="store_true", help="Also print machine-readable JSON to stdout.")
    start_frontend.set_defaults(func=command_start_frontend)

    plan = subparsers.add_parser("plan", help="Build a safe env/bootstrap plan without changing files.")
    plan.add_argument("--no-write-report", action="store_true", help="Do not create .dev-bootstrap report files.")
    plan.add_argument("--json", action="store_true", help="Also print machine-readable JSON to stdout.")
    plan.set_defaults(func=command_plan)

    prepare_env = subparsers.add_parser("prepare-env", help="Create missing env files from examples without overwriting existing files.")
    prepare_env.add_argument("--add-missing-keys", action="store_true", help="Append missing keys from examples to existing env files after creating a timestamped backup.")
    prepare_env.add_argument("--no-write-report", action="store_true", help="Do not create .dev-bootstrap report files.")
    prepare_env.add_argument("--json", action="store_true", help="Also print machine-readable JSON to stdout.")
    prepare_env.set_defaults(func=command_prepare_env)

    up = subparsers.add_parser("up", help="Run the safe one-command dev environment pipeline.")
    up.add_argument("--dry-run", action="store_true", help="Show the up pipeline without changing env files or starting processes.")
    up.add_argument("--skip-install", action="store_true", help="Skip frontend dependency installation/preparation.")
    up.add_argument("--skip-cargo-check", action="store_true", help="Skip cargo metadata/check before backend start.")
    up.add_argument("--skip-db-start", action="store_true", help="Skip compose-assisted PostgreSQL start.")
    up.add_argument("--skip-backend-start", action="store_true", help="Skip backend process start; useful for clean-machine dry planning.")
    up.add_argument("--skip-frontend-start", action="store_true", help="Skip frontend process start; useful for clean-machine dry planning.")
    up.add_argument("--smoke-level", choices=["quick", "standard", "full", "none"], default="quick", help="Smoke level after startup. Phase 7 implements quick, standard and full smoke gates.")
    up.add_argument("--yes", action="store_true", help="Allow non-destructive automatic steps; this never permits DB reset or killing foreign processes.")
    up.add_argument("--step-timeout-seconds", type=int, default=TIMEOUT_POLICY["up_step"], help="Timeout for short diagnose/plan/prepare-env steps.")
    up.add_argument("--db-timeout-seconds", type=int, default=TIMEOUT_POLICY["postgres_ready"], help="Timeout for start-db readiness.")
    up.add_argument("--cargo-check-timeout-seconds", type=int, default=TIMEOUT_POLICY["cargo_check"], help="Timeout for cargo check.")
    up.add_argument("--backend-timeout-seconds", type=int, default=TIMEOUT_POLICY["backend_ready"], help="Timeout for backend health after cargo run.")
    up.add_argument("--npm-timeout-seconds", type=int, default=TIMEOUT_POLICY["npm_install"], help="Timeout for npm ci/install.")
    up.add_argument("--frontend-timeout-seconds", type=int, default=TIMEOUT_POLICY["frontend_ready"], help="Timeout for frontend readiness after npm run dev.")
    up.add_argument("--smoke-timeout-seconds", type=int, default=TIMEOUT_POLICY["smoke_step"], help="Timeout for smoke substeps launched by up.")
    up.add_argument("--allow-dev-db-write", action="store_true", help="Allow standard/full smoke to write through the live backend API to the configured dev database.")
    up.add_argument("--json", action="store_true", help="Also print machine-readable JSON to stdout.")
    up.set_defaults(func=command_up)


    smoke = subparsers.add_parser("smoke", help="Run post-start smoke gates with clear failure classification.")
    smoke.add_argument("--level", choices=["quick", "standard", "full"], default="quick", help="quick probes HTTP; standard adds backend Python smoke and frontend tests; full adds browser smoke.")
    smoke.add_argument("--allow-dev-db-write", action="store_true", help="Allow backend smoke to write to the configured dev database when TEST_DATABASE_URL is not present.")
    smoke.add_argument("--timeout-seconds", type=int, default=TIMEOUT_POLICY["smoke_step"], help="Timeout for each command-based smoke substep.")
    smoke.add_argument("--no-write-report", action="store_true", help="Do not create a standalone smoke report; step logs may still be temporary for command execution.")
    smoke.add_argument("--json", action="store_true", help="Also print machine-readable JSON to stdout.")
    smoke.set_defaults(func=command_smoke)

    release_gates = subparsers.add_parser("release-gates", help="Run keep-going release-gates scaffold and create a shareable report bundle.")
    release_gates.add_argument("--dry-run", action="store_true", help="Create a planned release-gates bundle without executing gate commands.")
    release_gates.add_argument("--timeout-seconds", type=int, default=TIMEOUT_POLICY["release_gate"], help="Maximum timeout for each implemented gate command.")
    release_gates.add_argument("--output-dir", help="Write the run directory to this path instead of .dev-bootstrap/runs/<run-id>.")
    release_gates.add_argument("--allow-dev-db-write", action="store_true", help="Allow backend Python smoke to write through the configured live backend API when TEST_DATABASE_URL is not present.")
    release_gates.add_argument("--managed-runtime", action="store_true", help="Start isolated backend/frontend processes on dynamic ports for write-capable release-gates instead of using live ports.")
    release_gates.add_argument("--managed-test-db", action="store_true", help="Create a disposable PostgreSQL database for DB-writing release-gates and run managed gates against it.")
    release_gates.add_argument("--test-db-retention", choices=["drop-always", "keep-on-failure", "keep-always"], default="keep-on-failure", help="Retention policy for --managed-test-db. Default keeps failed runs for investigation and drops successful runs.")
    release_gates.add_argument("--keep-test-db", choices=["on-failure", "always", "never"], help="Compatibility alias for --test-db-retention: on-failure, always or never.")
    release_gates.add_argument("--start-db-if-needed", action="store_true", help="With --managed-test-db, start the project docker compose PostgreSQL service if the configured PostgreSQL port is closed.")
    release_gates.add_argument("--dump-test-db-on-failure", action="store_true", help="With --managed-test-db, try pg_dump into the run directory when release-gates fail and the DB is retained.")
    release_gates.add_argument("--prepare-frontend", action="store_true", help="Compatibility alias for --prepare-deps=stale.")
    release_gates.add_argument("--prepare-deps", nargs="?", const=DEFAULT_FRONTEND_PREPARE_DEP_MODE, choices=["never", "missing", "stale", "missing-or-stale", "always"], help="Prepare frontend/backend dependencies before release gates. Bare --prepare-deps uses stale/missing-or-stale mode.")
    release_gates.add_argument("--install-playwright-browsers", action="store_true", help="Run npx playwright install chromium when browser binaries are missing before browser smoke.")
    release_gates.add_argument("--include-real-backend-browser", action="store_true", help="Run the dedicated write-capable real-backend Playwright path when its spec and prerequisites exist.")
    release_gates.add_argument("--real-backend-browser-spec", default="e2e/smoke/real-backend.smoke.spec.ts", help="Frontend-relative Playwright spec path for the real-backend browser gate.")
    release_gates.add_argument("--include-clean-machine", action="store_true", help="Run the optional clean-machine sandbox gate in a temporary project copy.")
    release_gates.add_argument("--clean-machine-profile", choices=CLEAN_MACHINE_PROFILES, default=DEFAULT_CLEAN_MACHINE_PROFILE, help="Clean-machine sandbox strictness: dry, deps or runtime. The clean-machine-* aliases are accepted too.")
    release_gates.add_argument("--clean-machine-retention", choices=CLEAN_MACHINE_RETENTION_POLICIES, default=DEFAULT_CLEAN_MACHINE_RETENTION, help="Whether to delete or keep the clean-machine sandbox after the gate.")
    release_gates.add_argument("--json", action="store_true", help="Also print machine-readable JSON to stdout.")
    release_gates.set_defaults(func=command_release_gates)

    status = subparsers.add_parser("status", help="Show devbootstrap runtime state, process liveness, ports and health probes.")
    status.add_argument("--json", action="store_true", help="Also print machine-readable JSON to stdout.")
    status.set_defaults(func=command_status)

    stop = subparsers.add_parser("stop", help="Stop only devbootstrap-tracked backend/frontend processes, and optionally compose postgres.")
    stop.add_argument("--include-db", action="store_true", help="Also stop docker compose postgres service without removing volumes.")
    stop.add_argument("--dry-run", action="store_true", help="Show what would be stopped without terminating processes or compose services.")
    stop.add_argument("--timeout-seconds", type=int, default=TIMEOUT_POLICY["stop_grace"], help="Graceful stop timeout before force kill for owned processes.")
    stop.add_argument("--no-force", action="store_true", help="Do not force kill owned processes after the graceful timeout.")
    stop.add_argument("--no-write-report", action="store_true", help="Do not create .dev-bootstrap stop report files.")
    stop.add_argument("--json", action="store_true", help="Also print machine-readable JSON to stdout.")
    stop.set_defaults(func=command_stop)

    self_check = subparsers.add_parser("self-check", help="Run devbootstrap internal v1 hardening fixtures without external packages.")
    self_check.add_argument("--no-write-report", action="store_true", help="Do not create .dev-bootstrap self-check report files.")
    self_check.add_argument("--json", action="store_true", help="Also print machine-readable JSON to stdout.")
    self_check.set_defaults(func=command_self_check)

    return parser

def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "keep_test_db", None):
        args.test_db_retention = {"on-failure": "keep-on-failure", "always": "keep-always", "never": "drop-always"}[args.keep_test_db]
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
