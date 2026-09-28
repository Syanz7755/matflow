"""Command line entry point for the local MatFlow demo."""
from __future__ import annotations

import argparse
import json
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


def _dsh_home() -> Path:
    return Path(os.environ.get("DSH_HOME", Path.home() / ".dsh")).resolve()


def diagnose(check_dsh: bool = False, profile: str = "matflow") -> int:
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
    if check_dsh:
        dsh = shutil.which("dsh")
        profile_dir = _dsh_home() / "profiles" / profile
        print(f"DSH                 {dsh or 'not found'}")
        print(f"DSH profile         {profile_dir if profile_dir.exists() else 'missing; run matflow configure-dsh'}")
        if not dsh or not profile_dir.exists():
            return 1
        try:
            subprocess.run([dsh, "--profile", profile, "--dump-config"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, timeout=30)
            print("DSH MatFlow config  valid")
        except (subprocess.SubprocessError, OSError) as exc:
            print(f"DSH MatFlow config  invalid: {exc}", file=sys.stderr)
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


def serve() -> int:
    """Run only the MatFlow HTTP/MCP server."""
    return subprocess.call([sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000"], cwd=ROOT)


def _dsh_patch() -> str:
    return """# Managed by `matflow configure-dsh`; dedicated MatFlow profile only.
- insert:
    - id: mcp-matflow
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: matflow
        transport: streamable-http
        url: http://127.0.0.1:8000/mcp
        headers: {}
        toolCallTimeoutMs: 180000
        failOnStartupError: true
        reconnect:
          enabled: true
          initialDelayMs: 500
          maxDelayMs: 30000
          maxAttempts: 10

    - id: matflow-dsh-integration
      name: '@matflow/dsh-integration'
      config:
        apiBaseUrl: http://127.0.0.1:8000
"""


def configure_dsh(profile: str = "matflow", dry_run: bool = False) -> int:
    """Create an isolated, idempotent DSH Web profile for MatFlow."""
    if not profile or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for char in profile):
        print("DSH profile names may contain only letters, numbers, '-' and '_'.", file=sys.stderr)
        return 2
    dsh = shutil.which("dsh")
    if not dsh:
        print("dsh was not found on PATH.", file=sys.stderr)
        return 1
    profile_dir = _dsh_home() / "profiles" / profile
    patch_path = profile_dir / "cordis.patch.yml"
    package_path = profile_dir / "package.json"
    desired_patch = _dsh_patch()
    print(f"Profile: {profile_dir}")
    print("Will create from the shipped web profile, install the local MatFlow integration, and own only mcp-matflow plus matflow-dsh-integration rows.")
    if dry_run:
        print(desired_patch)
        return 0
    if not profile_dir.exists():
        subprocess.run([dsh, "--profile", profile, "--from-default-profile", "web", "--dump-config"], check=True, stdout=subprocess.DEVNULL)
    if not package_path.exists():
        print(f"DSH did not create {package_path}.", file=sys.stderr)
        return 1
    current_patch = patch_path.read_text(encoding="utf-8") if patch_path.exists() else "[]\n"
    meaningful_patch = "\n".join(line for line in current_patch.splitlines() if line.strip() and not line.lstrip().startswith("#")).strip()
    if meaningful_patch not in {"", "[]"} and "Managed by `matflow configure-dsh`" not in current_patch:
        print(f"Refusing to overwrite non-MatFlow profile patch: {patch_path}", file=sys.stderr)
        return 1
    backup = patch_path.with_suffix(".yml.bak")
    if patch_path.exists() and not backup.exists():
        shutil.copy2(patch_path, backup)
    package_backup = package_path.with_suffix(".json.bak")
    if not package_backup.exists():
        shutil.copy2(package_path, package_backup)
    patch_path.write_text(desired_patch, encoding="utf-8")
    integration = (ROOT / "integrations" / "dsh").resolve()
    subprocess.run([dsh, "plugin", "--profile", profile, "add", "@deepseek-ai/dsh-mcp-client@0.1.5-rc.1", str(integration)], check=True)
    package = json.loads(package_path.read_text(encoding="utf-8"))
    expected = {"@deepseek-ai/dsh-mcp-client", "@matflow/dsh-integration"}
    if not expected.issubset(package.get("dependencies", {})):
        print("DSH plugin installation did not record both required packages.", file=sys.stderr)
        return 1
    subprocess.run([dsh, "--profile", profile, "--dump-config"], check=True, stdout=subprocess.DEVNULL)
    print(f"Configured DSH profile '{profile}'. Start it with: matflow start-dsh --profile {profile}")
    return 0


def start_dsh(profile: str = "matflow") -> int:
    if diagnose(check_dsh=True, profile=profile):
        return 1
    dsh = shutil.which("dsh") or "dsh"
    api = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000"], cwd=ROOT)
    try:
        for _ in range(30):
            try:
                with urlrequest.urlopen("http://127.0.0.1:8000/api/capabilities", timeout=1):
                    break
            except Exception:
                if api.poll() is not None: return api.returncode or 1
                time.sleep(0.25)
        else:
            print("MatFlow did not become ready on http://127.0.0.1:8000.", file=sys.stderr)
            return 1
        return subprocess.call([dsh, "--profile", profile], cwd=ROOT)
    finally:
        api.terminate()
        try: api.wait(timeout=5)
        except subprocess.TimeoutExpired: api.kill()


def main() -> int:
    parser = argparse.ArgumentParser(prog="matflow", description="Local Materials Graph Demo")
    commands = parser.add_subparsers(dest="command", required=True)
    diagnose_parser = commands.add_parser("diagnose", help="check Python, frontend, and optional DSH readiness")
    diagnose_parser.add_argument("--dsh", action="store_true", help="also validate the local MatFlow DSH profile")
    diagnose_parser.add_argument("--profile", default="matflow")
    commands.add_parser("install-frontend", help="install locked frontend packages")
    commands.add_parser("start", help="start the API and visual workflow editor")
    commands.add_parser("serve", help="start only the HTTP and MCP server")
    configure = commands.add_parser("configure-dsh", help="create an isolated local DSH profile for MatFlow")
    configure.add_argument("--profile", default="matflow")
    configure.add_argument("--dry-run", action="store_true")
    start_dsh_parser = commands.add_parser("start-dsh", help="start MatFlow MCP and the DSH Web profile")
    start_dsh_parser.add_argument("--profile", default="matflow")
    args = parser.parse_args()
    if args.command == "diagnose": return diagnose(args.dsh, args.profile)
    if args.command == "configure-dsh": return configure_dsh(args.profile, args.dry_run)
    if args.command == "start-dsh": return start_dsh(args.profile)
    return {"install-frontend": install_frontend, "start": start, "serve": serve}[args.command]()


if __name__ == "__main__":
    raise SystemExit(main())
