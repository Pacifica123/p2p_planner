#!/usr/bin/env python3
"""Static and executable checks for the zero-config bootstrap patch."""

from __future__ import annotations

import argparse
import ast
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def service_block(compose_text: str, service_name: str) -> str:
    marker = f"  {service_name}:\n"
    start = compose_text.find(marker)
    require(start >= 0, f"compose service is missing: {service_name}")
    remainder = compose_text[start + len(marker) :]
    boundaries = [
        index
        for name in ("bootstrap-init", "postgres", "backend", "web")
        if name != service_name
        for index in [remainder.find(f"\n  {name}:\n")]
        if index >= 0
    ]
    end = min(boundaries) if boundaries else len(remainder)
    return remainder[:end]


def check_python() -> None:
    for relative in ("bootstrap.py", "tools/container_bootstrap.py"):
        path = ROOT / relative
        ast.parse(path.read_text(encoding="utf-8"), filename=relative)

    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "bootstrap.py",
            "start",
            "--dry-run",
            "--no-open",
            "--port",
            "18088",
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    require(result.returncode == 0, result.stdout)
    require("http://127.0.0.1:18088" in result.stdout, result.stdout)
    require("POSTGRES" not in result.stdout or "внутри Docker" in result.stdout, result.stdout)


def check_compose_contract() -> None:
    compose_path = ROOT / "deploy/bootstrap/compose.yaml"
    text = compose_path.read_text(encoding="utf-8")
    postgres = service_block(text, "postgres")
    backend = service_block(text, "backend")
    web = service_block(text, "web")
    init = service_block(text, "bootstrap-init")

    require("POSTGRES_PASSWORD_FILE:" in postgres, "PostgreSQL must use a secret file")
    require("POSTGRES_USER: p2pkanban" in postgres, "managed PostgreSQL role is missing")
    require("POSTGRES_DB: p2pkanban" in postgres, "managed PostgreSQL DB is missing")
    require("\n    ports:" not in postgres, "PostgreSQL must not publish a host port")
    require("\n    ports:" not in backend, "backend must not publish a host port")
    require("\n    ports:" in web, "web gateway must publish the only host port")
    require("service_completed_successfully" in init + postgres + backend, "init ordering is missing")
    require("bootstrap_secrets:" in text, "persistent secret volume is missing")
    require("postgres_data:" in text, "persistent PostgreSQL volume is missing")
    require("VITE_API_BASE_URL: /api/v1" in web, "frontend API must be same-origin")
    require("change-me" not in text.lower(), "compose contains a placeholder secret")
    require("POSTGRES_PASSWORD:" not in text, "compose must not embed a DB password")
    require("AUTH__JWT_SECRET:" not in text, "compose must not embed a JWT secret")


def check_images_and_proxy() -> None:
    required = (
        "deploy/bootstrap/init-secrets.sh",
        "deploy/bootstrap/backend-entrypoint.sh",
        "deploy/bootstrap/backend.Dockerfile",
        "deploy/bootstrap/frontend.Dockerfile",
        "deploy/bootstrap/nginx.conf",
    )
    for relative in required:
        require((ROOT / relative).is_file(), f"missing {relative}")

    entrypoint = (ROOT / "deploy/bootstrap/backend-entrypoint.sh").read_text(encoding="utf-8")
    require("DATABASE__URL=" in entrypoint, "backend entrypoint does not construct DATABASE__URL")
    require("AUTH__JWT_SECRET=" in entrypoint, "backend entrypoint does not load JWT secret")
    require("echo \"$" not in entrypoint, "entrypoint may print a secret")

    nginx = (ROOT / "deploy/bootstrap/nginx.conf").read_text(encoding="utf-8")
    require("location /api/" in nginx, "Nginx API proxy is missing")
    require("proxy_pass http://backend:18080" in nginx, "Nginx backend target is wrong")
    require("try_files $uri $uri/ /index.html" in nginx, "SPA fallback is missing")


def check_manifest_and_readme() -> None:
    cargo = tomllib.loads((ROOT / "backend/Cargo.toml").read_text(encoding="utf-8"))
    require(
        cargo.get("package", {}).get("default-run") == "p2p-planner-backend",
        "Cargo default-run does not select the backend binary",
    )

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    require("python bootstrap.py" in readme, "README has no primary bootstrap command")
    require("docs/deployment/zero-config-bootstrap-v1.md" in readme, "README has no bootstrap runbook link")
    require(len(readme.splitlines()) <= 220, "README became dense again")


def optional_compose_validation() -> None:
    docker = shutil.which("docker")
    if not docker:
        print("SKIP docker compose config: docker CLI is not installed")
        return
    version = subprocess.run(
        [docker, "compose", "version"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if version.returncode != 0:
        print("SKIP docker compose config: Compose v2 is not available")
        return
    env = os.environ.copy()
    env.update(
        {
            "P2PKANBAN_WEB_PORT": "18088",
            "P2PKANBAN_BIND_ADDRESS": "127.0.0.1",
        }
    )
    result = subprocess.run(
        [
            docker,
            "compose",
            "--project-name",
            "p2pkanban-bootstrap-check",
            "--file",
            "deploy/bootstrap/compose.yaml",
            "config",
            "--quiet",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    require(result.returncode == 0, result.stdout)
    print("OK docker compose config")


def check_frontend_production_build() -> None:
    npm = shutil.which("npm")
    require(npm is not None, "npm is required for --frontend-build")
    source = ROOT / "frontend"
    with tempfile.TemporaryDirectory(prefix="p2pkanban-bootstrap-frontend-") as raw:
        temporary = Path(raw)
        checkout = temporary / "frontend"
        checkout.mkdir()
        for name in (
            "package.json",
            "package-lock.json",
            "tsconfig.json",
            "tsconfig.node.json",
            "vite.config.ts",
            "index.html",
        ):
            shutil.copy2(source / name, checkout / name)
        shutil.copytree(source / "src", checkout / "src")

        env = os.environ.copy()
        env.update(
            {
                "NPM_CONFIG_CACHE": str(temporary / "npm-cache"),
                "VITE_API_BASE_URL": "/api/v1",
                "VITE_ENABLE_PROJECT_ROADMAP_SEED": "true",
            }
        )
        for command in ([npm, "ci"], [npm, "run", "build"]):
            result = subprocess.run(
                command,
                cwd=checkout,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            require(result.returncode == 0, result.stdout)
        require((checkout / "dist/index.html").is_file(), "frontend dist/index.html is missing")
    print("OK frontend production build with /api/v1")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--frontend-build",
        action="store_true",
        help="Also run npm ci and the production Vite build in a temporary copy.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    checks = (
        ("python CLI", check_python),
        ("compose isolation and secrets", check_compose_contract),
        ("container images and gateway", check_images_and_proxy),
        ("Cargo and README contract", check_manifest_and_readme),
        ("optional Compose parser", optional_compose_validation),
    )
    for name, check in checks:
        check()
        if not name.startswith("optional"):
            print(f"OK {name}")
    if args.frontend_build:
        check_frontend_production_build()
    print("zero-config bootstrap checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
