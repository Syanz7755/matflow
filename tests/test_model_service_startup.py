import json
import os
import shutil
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).parents[1]
START_SCRIPT = ROOT / "scripts" / "start_model_services.ps1"


class _GatewayHandler(BaseHTTPRequestHandler):
    readiness_status = 400
    expected_authorization = ""
    requests = []

    def do_GET(self):
        type(self).requests.append((self.path, self.headers.get("Authorization")))
        if self.path == "/health":
            self.send_response(200)
        elif self.path == "/v1/models" and self.headers.get("Authorization") == type(self).expected_authorization:
            self.send_response(type(self).readiness_status)
        else:
            self.send_response(401)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, format, *args):
        return


class ModelServiceStartupTests(unittest.TestCase):
    def setUp(self):
        _GatewayHandler.requests = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _GatewayHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def run_startup_check(self, readiness_status):
        powershell = shutil.which("powershell.exe")
        if not powershell:
            self.skipTest("PowerShell is required for the Windows model-service launcher")

        credential_name = "MATFLOW_TEST_GATEWAY_KEY"
        credential_value = "runtime-only-test-key"
        _GatewayHandler.readiness_status = readiness_status
        _GatewayHandler.expected_authorization = f"Bearer {credential_value}"
        origin = f"http://127.0.0.1:{self.server.server_port}"
        config = {
            "version": 1,
            "services": [{
                "id": "synthetic_gateway",
                "enabled": True,
                "mode": "test",
                "working_directory": ".",
                "executable": "powershell.exe",
                "arguments": ["-NoProfile", "-Command", "exit 0"],
                "required_environment": [credential_name],
                "health_url": origin + "/health",
                "readiness_url": origin + "/v1/models",
                "readiness_api_key_env": credential_name,
                "startup_timeout_seconds": 1,
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "services.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            environment = os.environ.copy()
            environment[credential_name] = credential_value
            return subprocess.run(
                [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(START_SCRIPT), "-ConfigPath", str(config_path)],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                timeout=10,
            ), credential_value

    def test_health_success_does_not_hide_authenticated_readiness_failure(self):
        result, credential = self.run_startup_check(readiness_status=400)

        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(("/v1/models", f"Bearer {credential}"), _GatewayHandler.requests)
        self.assertNotIn(credential, result.stdout + result.stderr)

    def test_authenticated_readiness_success_accepts_the_running_service(self):
        result, credential = self.run_startup_check(readiness_status=200)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(("/v1/models", f"Bearer {credential}"), _GatewayHandler.requests)
        self.assertIn("already ready", result.stdout)
        self.assertNotIn(credential, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
