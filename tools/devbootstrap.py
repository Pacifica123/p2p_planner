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


def frontend_install_marker_matches(project_root: Path, package_json_hash: str | None, package_lock_hash: str | None) -> bool:
    marker = load_frontend_install_marker(project_root)
    if "_error" in marker:
        return False
    return (
        marker.get("packageJsonSha256") == package_json_hash
        and marker.get("packageLockSha256") == package_lock_hash
        and bool((project_root / "frontend" / "node_modules").is_dir())
    )


def write_frontend_install_marker(project_root: Path, result: FrontendResult, command: list[str]) -> None:
    marker_path = frontend_install_marker_path(project_root)
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker = {
        "version": STATE_VERSION,
        "generatedAt": iso_now(),
        "toolVersion": TOOL_VERSION,
        "command": command_as_text(command),
        "packageJsonSha256": result.package_json_hash,
        "packageLockSha256": result.package_lock_hash,
    }
    write_json(marker_path, marker)


def frontend_install_command(project_root: Path) -> list[str]:
    if (project_root / "frontend" / "package-lock.json").is_file():
        return ["npm", "ci"]
    return ["npm", "install"]


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
    result.install_marker_valid = frontend_install_marker_matches(project_root, result.package_json_hash, result.package_lock_hash)
    result.install_command = frontend_install_command(project_root)
    result.node_version = run_process_probe("node_version", ["node", "--version"], cwd=project_root, timeout=8)
    result.npm_version = run_process_probe("npm_version", ["npm", "--version"], cwd=project_root, timeout=8)
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
    result = build_frontend_result(project_root, invoked_from, mode="prepare-frontend", dry_run=args.dry_run)
    report_dir: Path | None = None
    if project_root is not None and not args.no_write_report:
        report_dir = create_report_dir(project_root, "prepare-frontend")
    if project_root is not None:
        add_frontend_preflight_checks(result, project_root)
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
        elif frontend_dependencies_current(result) and not args.force_install:
            result.classification = "frontend_dependencies_current"
            result.actions.append(FrontendAction("npm_install_noop", "ok", "frontend/node_modules matches the devbootstrap install marker; install skipped."))
            result.next_actions.append("Frontend dependencies look current. Continue with `python tools/devbootstrap.py start-frontend`.")
        elif args.dry_run:
            result.classification = "frontend_prepare_planned"
            result.actions.append(FrontendAction("npm_install", "planned", "Would install frontend dependencies.", command_as_text(result.install_command)))
            result.next_actions.append("Run without --dry-run to install/update frontend dependencies.")
        else:
            log_path = report_dir / "npm-install.log" if report_dir is not None else None
            result.actions.append(FrontendAction("npm_install", "started", "Installing frontend dependencies.", command_as_text(result.install_command)))
            result.npm_install = run_frontend_command_probe(
                "npm_install",
                result.install_command,
                project_root=project_root,
                cwd=project_root / "frontend",
                timeout=args.timeout_seconds,
                log_path=log_path,
            )
            if process_probe_ok(result.npm_install):
                result.classification = "frontend_dependencies_ready"
                result.node_modules_exists = (project_root / "frontend" / "node_modules").is_dir()
                result.install_marker_valid = True
                write_frontend_install_marker(project_root, result, result.install_command)
                result.actions.append(FrontendAction("install_marker", "ok", "Updated frontend install marker.", evidence=result.install_marker_path))
                result.next_actions.append("Frontend dependencies are ready. Continue with `python tools/devbootstrap.py start-frontend`.")
            else:
                result.classification = classify_frontend_failure(command_output_text(result.npm_install), "frontend_install_failed")
                result.failures.append({"code": result.classification, "message": "Frontend dependency installation failed."})
                result.next_actions.append("Inspect npm-install.log, fix npm/network/lockfile issues, then rerun prepare-frontend.")
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
    probe = run_process_probe(name, command, cwd=cwd, timeout=timeout)
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
    if "npm err!" in lower and "network" in lower:
        return "frontend_npm_network_failed"
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
RELEASE_GATES_ARCHIVE_EXCLUDED_SUFFIXES = (".pyc", ".pyo", ".sqlite", ".sqlite3", ".db")


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


def classify_gate_output(name: str, stdout: str, stderr: str, error: str | None, returncode: int | None) -> tuple[str, str, str]:
    output = "\n".join(part for part in [stdout, stderr, error or ""] if part)
    lower = output.lower()
    if error == "timeout":
        return "timeout", f"{name}_timeout", "gate timed out"
    if returncode == 0:
        if "ignored" in lower and "test result:" in lower:
            return "partial_pass", "critical_tests_ignored", "command exited 0, but output mentions ignored tests"
        return "ok", "ok", "gate completed"
    if "playwright" in lower and ("browser" in lower or "install" in lower or "executable doesn't exist" in lower):
        return "infra_failed", "browser_smoke_prerequisite", "Playwright browser prerequisite appears to be missing"
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
        )
    if dry_run:
        command_text = release_gate_command_display(spec.command)
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
    )


def build_release_gate_specs(project_root: Path) -> list[GateSpec]:
    return [
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
            name="release_gates_matrix",
            cwd=".",
            command=[],
            description="Placeholder for backend/frontend/browser/docs release gates planned in phases 3-6.",
            not_implemented_reason="Phase 1/2 implements the keep-going runner and report bundle only; backend/frontend/browser/docs gates are intentionally reserved for later phases.",
        ),
    ]


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
    if "not_implemented" in statuses:
        return "incomplete", "release_gates_incomplete"
    if "partial_pass" in statuses:
        return "partial_pass", "release_gates_partial_pass"
    if statuses and statuses.issubset({"ok"}):
        return "ok", "release_gates_ok"
    return "unknown", "release_gates_unknown"


def finalize_release_gates_result(result: ReleaseGatesResult) -> None:
    result.overall_status, result.classification = release_gates_overall_status(result.gates, dry_run=result.dry_run)
    result.findings.clear()
    for gate in result.gates:
        if gate.status not in {"ok", "planned"}:
            severity = "warn" if gate.status in {"partial_pass", "not_implemented"} else "fail"
            result.findings.append(
                {
                    "severity": severity,
                    "code": gate.classification,
                    "message": f"{gate.name}: {gate.message}",
                }
            )
    result.next_actions.clear()
    if result.dry_run:
        result.next_actions.append("Run `python tools/devbootstrap.py release-gates` without --dry-run to execute implemented gates and create a fresh bundle.")
    elif result.overall_status == "incomplete":
        result.next_actions.append("Implement Phase 3+ gates before treating release-gates as a full v1 release signal.")
    elif result.overall_status == "ok":
        result.next_actions.append("Configured release-gates passed; continue with later release validation or manual review.")
    else:
        result.next_actions.append("Inspect release-gates logs and fix the classified finding before rerunning.")


def render_release_gates_summary(result: ReleaseGatesResult) -> str:
    lines: list[str] = []
    lines.append("# release-gates summary")
    lines.append("")
    lines.append(f"Overall: {result.overall_status}")
    lines.append(f"Classification: {result.classification}")
    lines.append(f"Generated: {result.generated_at}")
    lines.append(f"Dry run: {result.dry_run}")
    lines.append(f"Project root: {result.project_root or 'not found'}")
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

    specs = build_release_gate_specs(project_root)
    for index, spec in enumerate(specs, start=1):
        effective_timeout = min(args.timeout_seconds, spec.timeout_seconds) if args.timeout_seconds > 0 else spec.timeout_seconds
        result.gates.append(
            run_gate_process_step(
                project_root=project_root,
                logs_dir=logs_dir,
                index=index,
                spec=spec,
                timeout_seconds=effective_timeout,
                dry_run=args.dry_run,
            )
        )
    finalize_release_gates_result(result)
    write_release_gates_reports(project_root, result, run_dir)
    print_release_gates_summary(result)
    if args.json:
        print("\nJSON:")
        print(json.dumps(release_gates_json_payload(result), ensure_ascii=False, indent=2))
    if result.dry_run:
        return 0
    return 0 if result.overall_status == "ok" else 1


@dataclass
class StopTarget:
    name: str
    pid: int | None
    cwd: str | None
    command: str | None
    log_path: str | None = None
    run_id: str | None = None
    alive_before: bool = False
    alive_after: bool | None = None
    verification_status: str = "unknown"
    verification_evidence: str = ""
    action: str = "pending"
    error: str | None = None


@dataclass
class StopDbAction:
    status: str
    command: str | None = None
    message: str = ""
    evidence: str | None = None


@dataclass
class StopResult:
    generated_at: str
    tool_version: str
    project_root: str | None
    invoked_from: str
    dry_run: bool
    include_db: bool
    force: bool
    timeout_seconds: int
    run_id: str
    classification: str = "unknown"
    targets: list[StopTarget] = field(default_factory=list)
    db_action: StopDbAction | None = None
    ports_after: list[PortProbe] = field(default_factory=list)
    http_after: list[HttpProbe] = field(default_factory=list)
    failures: list[dict[str, str]] = field(default_factory=list)
    warnings: list[dict[str, str]] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)
    report_dir: str | None = None


def process_table_state(project_root: Path) -> tuple[Path, dict[str, Any], dict[str, dict[str, Any]]]:
    state_path = project_root / BOOTSTRAP_DIR_NAME / "state.json"
    state = read_json(state_path)
    if "_error" in state:
        return state_path, state, {}
    processes_raw = state.get("processes") if isinstance(state.get("processes"), dict) else {}
    processes: dict[str, dict[str, Any]] = {}
    for name, entry in processes_raw.items():
        if isinstance(name, str) and isinstance(entry, dict):
            processes[name] = dict(entry)
    return state_path, state, processes


def procfs_process_details(pid: int) -> tuple[str | None, str | None, str | None]:
    proc_dir = Path("/proc") / str(pid)
    if not proc_dir.exists():
        return None, None, "procfs entry not found"
    actual_cwd: str | None = None
    actual_cmd: str | None = None
    errors: list[str] = []
    try:
        actual_cwd = str(Path(os.readlink(proc_dir / "cwd")).resolve())
    except OSError as exc:
        errors.append(f"cwd unavailable: {exc}")
    try:
        raw = (proc_dir / "cmdline").read_bytes()
        parts = [part.decode("utf-8", errors="replace") for part in raw.split(b"\0") if part]
        actual_cmd = " ".join(parts)
    except OSError as exc:
        errors.append(f"cmdline unavailable: {exc}")
    return actual_cwd, actual_cmd, "; ".join(errors) if errors else None


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
    prepare_frontend.add_argument("--force-install", action="store_true", help="Run npm ci/install even when the install marker looks current.")
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
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
