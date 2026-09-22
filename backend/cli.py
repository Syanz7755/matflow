"""Command line entry point for the local MatFlow demo."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from urllib import request as urlrequest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def configured_litellm_gateway_key(config_path: Path) -> str:
    """Return the local gateway key from the single project configuration source."""
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    key = config.get("general_settings", {}).get("master_key")
    if not isinstance(key, str) or not key.strip():
        raise RuntimeError("config/litellm.yaml must set general_settings.master_key.")
    return key


def diagnose() -> int:
    """Print actionable checks without making changes."""
    checks = [
        ("Python", f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"),
        ("uv environment", str(ROOT / ".venv")),
        ("Project root", str(ROOT)),
        ("Node.js", shutil.which("node") or "not found"),
        ("npm", shutil.which("npm") or "not found"),
        ("Frontend packages", "installed" if (ROOT / "frontend" / "node_modules").exists() else "missing; run matflow install-frontend"),
    ]
    for label, value in checks:
        print(f"{label:18} {value}")
    try:
        from fastapi import __version__ as fastapi_version
        import numpy, pandas
        print(f"FastAPI             {fastapi_version}")
        print(f"NumPy / Pandas      {numpy.__version__} / {pandas.__version__}")
    except ImportError as exc:
        print(f"Python packages     missing: {exc.name}; run python -m pip install -e .")
        return 1
    return 0


def install_frontend() -> int:
    npm = shutil.which("npm")
    if not npm:
        print("Node.js/npm was not found. Activate the Conda environment created from environment.yml.", file=sys.stderr)
        return 1
    command = [npm, "ci"] if (ROOT / "frontend" / "package-lock.json").exists() else [npm, "install"]
    return subprocess.call(command, cwd=ROOT / "frontend")


def start() -> int:
    if diagnose():
        return 1
    if not (ROOT / "frontend" / "node_modules").exists():
        print("Frontend packages are missing. Run: matflow install-frontend", file=sys.stderr)
        return 1
    litellm_config = ROOT / "config" / "litellm.yaml"
    litellm = None
    if not os.environ.get("SJTU_ZHIYUAN_API_KEY"):
        print("SJTU_ZHIYUAN_API_KEY is not set; LiteLLM will start but upstream requests will fail.", file=sys.stderr)
    try:
        with urlrequest.urlopen("http://127.0.0.1:4000/health/readiness", timeout=1):
            gateway_ready = True
    except Exception:
        gateway_ready = False
    if not gateway_ready:
        litellm = subprocess.Popen([sys.executable, "-m", "litellm", "--config", str(litellm_config), "--port", "4000"], cwd=ROOT)
        for _ in range(30):
            try:
                with urlrequest.urlopen("http://127.0.0.1:4000/health/readiness", timeout=1):
                    break
            except Exception:
                if litellm.poll() is not None:
                    raise RuntimeError("LiteLLM proxy exited during startup. Check its console output.")
                time.sleep(1)
        else:
            litellm.terminate()
            raise RuntimeError("LiteLLM proxy did not become ready on http://127.0.0.1:4000.")

    os.environ.setdefault("MATFLOW_LITELLM_API_KEY", configured_litellm_gateway_key(litellm_config))
    api = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.main:app", "--port", "8000"], cwd=ROOT, env=os.environ.copy())
    try:
        print("MatFlow is starting. Open the Vite URL below (normally http://localhost:5173).")
        return subprocess.call([shutil.which("npm") or "npm", "run", "dev"], cwd=ROOT / "frontend")
    except KeyboardInterrupt:
        return 0
    finally:
        api.terminate()
        try:
            api.wait(timeout=5)
        except subprocess.TimeoutExpired:
            api.kill()
        if litellm is not None:
            litellm.terminate()
            try:
                litellm.wait(timeout=5)
            except subprocess.TimeoutExpired:
                litellm.kill()


def main() -> int:
    parser = argparse.ArgumentParser(prog="matflow", description="Local Materials Graph Demo")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("diagnose", help="check Conda, Python and frontend readiness")
    commands.add_parser("install-frontend", help="install locked frontend packages")
    commands.add_parser("start", help="start the API and visual workflow editor")
    args = parser.parse_args()
    return {"diagnose": diagnose, "install-frontend": install_frontend, "start": start}[args.command]()


if __name__ == "__main__":
    raise SystemExit(main())
