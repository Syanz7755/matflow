"""Command line entry point for the MatFlow backend server."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FRONTEND_ROOT = ROOT.parent / "matflow-frontend"
UI_MANIFEST = "matflow-ui.json"


def configured_litellm_gateway_key(config_path: Path) -> str:
    """Return the local gateway key from the project configuration."""
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    key = config.get("general_settings", {}).get("master_key")
    if not isinstance(key, str) or not key.strip():
        raise RuntimeError("config/litellm.yaml must set general_settings.master_key.")
    return key


class LauncherError(RuntimeError):
    """A user-actionable launcher configuration or startup failure."""


def _port_available(host: str, port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((host, port))
        return True
    except OSError:
        return False


def _wait_for_url(url: str, process: subprocess.Popen[Any], timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise LauncherError(f"Process exited before becoming ready: {url}")
        try:
            with urlrequest.urlopen(url, timeout=1):
                return
        except (OSError, urlerror.URLError):
            time.sleep(0.2)
    raise LauncherError(f"Timed out waiting for {url}")


def _stop(process: subprocess.Popen[Any] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def select_ui(requested: str | None, *, interactive: bool | None = None) -> str:
    if requested:
        return requested
    is_interactive = sys.stdin.isatty() and sys.stdout.isatty() if interactive is None else interactive
    if not is_interactive:
        return "none"
    print("Choose a MatFlow UI:")
    print("  1. WebUI")
    print("  2. None (backend only)")
    try:
        answer = input("Selection [1]: ").strip().lower()
    except EOFError:
        return "none"
    return "none" if answer in {"2", "none", "n"} else "webui"


def resolve_frontend_root(explicit: str | None = None) -> Path:
    candidate = explicit or os.getenv("MATFLOW_WEBUI_DIR") or str(DEFAULT_FRONTEND_ROOT)
    return Path(candidate).expanduser().resolve()


def load_ui_manifest(frontend_root: Path, client_id: str = "webui") -> dict[str, Any]:
    path = frontend_root / UI_MANIFEST
    if not path.is_file():
        raise LauncherError(f"UI manifest not found: {path}")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LauncherError(f"UI manifest is not valid JSON: {path}: {exc}") from exc
    if manifest.get("schema_version") != 1 or not isinstance(manifest.get("clients"), dict):
        raise LauncherError("UI manifest must use schema_version 1 and define clients")
    client = manifest["clients"].get(client_id)
    if not isinstance(client, dict):
        raise LauncherError(f"UI manifest does not define client '{client_id}'")
    required = {"command", "working_directory", "url", "health_url"}
    missing = required - set(client)
    if missing:
        raise LauncherError(f"UI client '{client_id}' is missing: {', '.join(sorted(missing))}")
    if not isinstance(client["command"], list) or not client["command"] or not all(isinstance(item, str) and item for item in client["command"]):
        raise LauncherError("UI command must be a non-empty string array")
    if not isinstance(client.get("environment", {}), dict):
        raise LauncherError("UI environment must be an object")
    return client


def _render(value: str, variables: dict[str, str]) -> str:
    try:
        return value.format_map(variables)
    except KeyError as exc:
        raise LauncherError(f"Unknown UI manifest variable: {exc.args[0]}") from exc


def _ui_process(frontend_root: Path, client: dict[str, Any], variables: dict[str, str]) -> tuple[subprocess.Popen[Any], str, str]:
    working_directory = (frontend_root / _render(client["working_directory"], variables)).resolve()
    if frontend_root != working_directory and frontend_root not in working_directory.parents:
        raise LauncherError("UI working_directory escapes the frontend repository")
    if not working_directory.is_dir():
        raise LauncherError(f"UI working directory does not exist: {working_directory}")
    command = [_render(item, variables) for item in client["command"]]
    executable = shutil.which(command[0])
    if not executable:
        raise LauncherError(f"UI executable was not found on PATH: {command[0]}")
    command[0] = executable
    environment = os.environ.copy()
    environment.update({key: _render(str(value), variables) for key, value in client.get("environment", {}).items()})
    url = _render(client["url"], variables)
    health_url = _render(client["health_url"], variables)
    return subprocess.Popen(command, cwd=working_directory, env=environment), url, health_url


def diagnose(ui: str = "none", ui_path: str | None = None) -> int:
    checks = [
        ("Python", f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"),
        ("Project root", str(ROOT)),
        ("Data root", os.getenv("MATFLOW_DATA_ROOT", str(ROOT / "data"))),
    ]
    try:
        import fastapi
        import numpy
        import pandas
        checks.extend([("FastAPI", fastapi.__version__), ("NumPy / Pandas", f"{numpy.__version__} / {pandas.__version__}")])
    except ImportError as exc:
        checks.append(("Python packages", f"missing: {exc.name}"))
        for label, value in checks:
            print(f"{label:18} {value}")
        return 1
    if ui == "webui":
        try:
            root = resolve_frontend_root(ui_path)
            load_ui_manifest(root)
            checks.extend([("Frontend root", str(root)), ("WebUI manifest", "valid")])
        except LauncherError as exc:
            checks.append(("WebUI", str(exc)))
            for label, value in checks:
                print(f"{label:18} {value}")
            return 1
    for label, value in checks:
        print(f"{label:18} {value}")
    return 0


def start(*, ui: str | None, ui_path: str | None, host: str, port: int, ui_port: int) -> int:
    selected = select_ui(ui)
    if selected == "none":
        return subprocess.call([sys.executable, "-m", "uvicorn", "backend.main:app", "--host", host, "--port", str(port)], cwd=ROOT)
    frontend_root = resolve_frontend_root(ui_path)
    client = load_ui_manifest(frontend_root)
    if not _port_available(host, port):
        raise LauncherError(f"Backend port is already in use: {host}:{port}")
    if not _port_available("127.0.0.1", ui_port):
        raise LauncherError(f"WebUI port is already in use: 127.0.0.1:{ui_port}")
    api_origin = f"http://{host}:{port}"
    api_url = f"{api_origin}/api"
    ui_origin = f"http://127.0.0.1:{ui_port}"
    variables = {"api_origin": api_origin, "api_url": api_url, "backend_host": host, "backend_port": str(port), "ui_origin": ui_origin, "ui_port": str(ui_port)}
    api_environment = os.environ.copy()
    configured_origins = [item.strip() for item in api_environment.get("MATFLOW_CORS_ORIGINS", "").split(",") if item.strip()]
    if ui_origin not in configured_origins:
        configured_origins.append(ui_origin)
    api_environment["MATFLOW_CORS_ORIGINS"] = ",".join(configured_origins)
    api: subprocess.Popen[Any] | None = None
    frontend: subprocess.Popen[Any] | None = None
    try:
        api = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.main:app", "--host", host, "--port", str(port)], cwd=ROOT, env=api_environment)
        _wait_for_url(f"{api_url}/capabilities", api)
        frontend, url, health_url = _ui_process(frontend_root, client, variables)
        _wait_for_url(health_url, frontend)
        print(f"MatFlow backend: {api_url}")
        print(f"MatFlow WebUI:   {url}")
        while True:
            if api.poll() is not None:
                raise LauncherError("MatFlow backend exited unexpectedly")
            frontend_code = frontend.poll()
            if frontend_code is not None:
                if frontend_code == 0:
                    return 0
                raise LauncherError(f"MatFlow WebUI exited with status {frontend_code}")
            time.sleep(0.25)
    except KeyboardInterrupt:
        return 0
    finally:
        _stop(frontend)
        _stop(api)


def main() -> int:
    parser = argparse.ArgumentParser(prog="matflow", description="MatFlow authoritative backend server")
    commands = parser.add_subparsers(dest="command", required=True)
    diagnose_parser = commands.add_parser("diagnose", help="check backend and optional WebUI readiness")
    diagnose_parser.add_argument("--ui", choices=("webui", "none"), default="none")
    diagnose_parser.add_argument("--ui-path")
    start_parser = commands.add_parser("start", help="start the backend and optionally a selected UI")
    start_parser.add_argument("--ui", choices=("webui", "none"))
    start_parser.add_argument("--ui-path")
    start_parser.add_argument("--host", default="127.0.0.1")
    start_parser.add_argument("--port", type=int, default=8000)
    start_parser.add_argument("--ui-port", type=int, default=5173)
    serve_parser = commands.add_parser("serve", help="compatibility alias for start --ui none")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    try:
        if args.command == "diagnose":
            return diagnose(args.ui, args.ui_path)
        if args.command == "serve":
            return start(ui="none", ui_path=None, host=args.host, port=args.port, ui_port=5173)
        return start(ui=args.ui, ui_path=args.ui_path, host=args.host, port=args.port, ui_port=args.ui_port)
    except LauncherError as exc:
        print(f"MatFlow startup failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
