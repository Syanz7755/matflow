"""Live-mode tests: the CLI against a real stdlib HTTP stub.

The rules this module pins:

* **offline is the default** — with ``--http`` absent, no subcommand opens a socket, not even when
  ``MATFLOW_API_URL`` points at a running stub, and the HTTP client is not imported at all;
* **live mode is real HTTP** — every assertion goes through a loopback ``http.server`` speaking the
  versioned ``matflow-http`` contract, so the transport, the URL building, the status handling and
  the payload mirroring are all exercised for real (no monkeypatched ``urlopen``);
* **a wrong backend is reported, never faked** — unreachable, mistyped, mismatched-contract, broken
  JSON and 404 answers each become a readable issue and the documented exit code;
* **the request carries only the user's own words** — the prompt the stub receives is checked
  against the prompt the user typed, including the long-prompt truncation path.

Only a stub is used: the real ``backend`` is never imported and no real server is ever contacted.
"""
from __future__ import annotations

import json
import socket
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Mapping

from .support import FlowViewTestCase, edge, graph_payload, node

CONTRACT = {"name": "matflow-http", "version": "1.0"}

LIVE_STATE = graph_payload(
    [node("load", status="completed"), node("qc", status="running")],
    [edge("e1", "load", "qc")],
    graph_id="live-graph",
    version=7,
)

DECISION: dict[str, Any] = {
    "decision_id": "decision-1",
    "task_id": "flowview-http-preview",
    "graph_version": 7,
    "candidates": [
        {"tool_id": "eis_basic_qc", "version": "1.0.0", "score": 1.0, "reasons": ["lexical match: eis, qc"]},
        {"tool_id": "raw_file_import", "version": "1.0.0", "score": 0.25, "reasons": ["weak match"]},
    ],
    "selected": [{"tool_id": "eis_basic_qc", "version": "1.0.0", "score": 1.0, "reasons": ["lexical match"]}],
    "confidence": 1.0,
    "rationale": "the only active compatible candidate",
    "requires_human_confirmation": False,
    "model_decisions": [],
    "summary": {"task_id": "task-live-0001", "status": "routed"},
}

SUMMARY: dict[str, Any] = {
    "task_id": "task-live-0001",
    "trace_id": "trace-stub-1",
    "status": "completed",
    "recorded_at": "2026-01-01T00:00:00Z",
    "user_prompt": "run basic EIS quality checks",
    "decision": {
        "selected": [{"tool_id": "eis_basic_qc"}],
        "confidence": 1.0,
        "requires_human_confirmation": False,
    },
    "result": {"status": "completed", "steps": [{"node_id": "load", "status": "completed"}]},
    "error_and_handling": {},
}


def closed_port() -> int:
    """A loopback port that nothing is listening on, so a connection is refused at once."""
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = int(probe.getsockname()[1])
    probe.close()
    return port


class StubBackend:
    """A minimal ``matflow-http`` server: enough of the contract for FlowView's four endpoints."""

    def __init__(
        self,
        *,
        state: Any = None,
        decision: Any = None,
        summaries: Mapping[str, Any] | None = None,
        data_types: Any = ("RawData", "TypedTable"),
        contract: Mapping[str, Any] | None = None,
        broken: Mapping[str, bytes] | None = None,
        capabilities_status: int = 200,
        redirects: Mapping[str, str] | None = None,
    ) -> None:
        self.state = LIVE_STATE if state is None else state
        self.decision = DECISION if decision is None else decision
        self.summaries = {"task-live-0001": SUMMARY} if summaries is None else dict(summaries)
        self.data_types = list(data_types)
        self.contract = dict(CONTRACT if contract is None else contract)
        self.broken = dict(broken or {})
        self.capabilities_status = capabilities_status
        self.redirects = dict(redirects or {})
        self.requests: list[tuple[str, str]] = []
        self.bodies: list[dict[str, Any]] = []
        self.last_task: dict[str, Any] | None = None
        self.port = 0
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    # -- lifecycle -----------------------------------------------------------------------
    def start(self) -> "StubBackend":
        stub = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args: Any) -> None:  # keep the test output readable
                pass

            def do_GET(self) -> None:  # noqa: N802 - http.server's API
                stub.handle(self, "GET")

            def do_POST(self) -> None:  # noqa: N802 - http.server's API
                stub.handle(self, "POST")

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = int(self._server.server_address[1])
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def paths(self) -> list[str]:
        return [path for _method, path in self.requests]

    def methods(self, path: str) -> list[str]:
        return [method for method, seen in self.requests if seen == path]

    # -- request handling ----------------------------------------------------------------
    def handle(self, handler: BaseHTTPRequestHandler, method: str) -> None:
        length = int(handler.headers.get("Content-Length") or 0)
        raw = handler.rfile.read(length) if length else b""
        self.requests.append((method, handler.path))
        if raw:
            try:
                self.bodies.append(json.loads(raw))
            except ValueError:
                self.bodies.append({})
        path = handler.path.split("?", 1)[0]
        if path in self.broken:
            self.send_raw(handler, 200, self.broken[path])
            return
        if path in self.redirects:
            target = self.redirects[path]
            handler.send_response(302)
            handler.send_header("Location", target)
            handler.send_header("Content-Length", "0")
            handler.end_headers()
            return
        if method == "GET" and path == "/api/capabilities":
            if self.capabilities_status != 200:
                self.send_json(handler, self.capabilities_status, {"detail": "capabilities are not available"})
                return
            self.send_json(
                handler,
                200,
                {
                    "api_contract": self.contract,
                    "server_version": "9.9.9",
                    "data_types": self.data_types,
                    "operations": {
                        "route": "POST /api/route",
                        "read_task_summary": "GET /api/task-summaries/{task_id}",
                    },
                },
            )
            return
        if method == "GET" and path == "/api/state":
            self.send_json(handler, 200, {"state": self.state, "registry": {}})
            return
        if method == "GET" and path.startswith("/api/task-summaries/"):
            record = self.summaries.get(path.rsplit("/", 1)[-1])
            if record is None:
                self.send_json(handler, 404, {"detail": "No persisted task summary exists for this task_id."})
                return
            self.send_json(handler, 200, record)
            return
        if method == "POST" and path == "/api/route":
            body = self.bodies[-1] if self.bodies else {}
            task = body.get("task") if isinstance(body, Mapping) else None
            self.last_task = dict(task) if isinstance(task, Mapping) else None
            self.send_json(handler, 200, self.decision)
            return
        self.send_json(handler, 404, {"detail": "no such endpoint"})

    def send_json(self, handler: BaseHTTPRequestHandler, status: int, payload: Any) -> None:
        self.send_raw(handler, status, json.dumps(payload).encode("utf-8"))

    def send_raw(self, handler: BaseHTTPRequestHandler, status: int, body: bytes) -> None:
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(body)))
        handler.send_header("X-Trace-ID", "trace-stub")
        handler.end_headers()
        handler.wfile.write(body)


class LiveModeTestCase(FlowViewTestCase, unittest.TestCase):
    """One stub backend per test; the CLI always runs as a subprocess against it."""

    def setUp(self) -> None:
        super().setUp()
        self.backend = StubBackend().start()
        self.addCleanup(self.backend.stop)
        self.url = self.backend.url


class OfflineDefaultTests(LiveModeTestCase):
    def test_offline_graph_never_contacts_a_running_backend(self):
        proc = self.run_cli("--format", "json", "graph")
        self.assert_exit(proc, 0)
        self.assertEqual(self.backend.requests, [], "offline mode opened a socket")

    def test_a_configured_backend_url_alone_does_not_switch_live_mode_on(self):
        """``MATFLOW_API_URL`` may point at a real server; it must not enable live mode by itself."""
        proc = self.run_cli("--format", "json", "graph", env_extra={"MATFLOW_API_URL": self.url})
        self.assert_exit(proc, 0)
        self.assertEqual(self.backend.requests, [], "the environment variable silently enabled live mode")

    def test_offline_commands_do_not_import_the_http_client(self):
        proc = self.run_bootstrap(
            "import sys\n"
            "from flowview.cli import main\n"
            "code = main(['graph', '--format', 'json'])\n"
            "leaked = [name for name in ('flowview.client', 'flowview.live') if name in sys.modules]\n"
            "print('LEAKED:' + ','.join(leaked) if leaked else 'NO-HTTP-MODULES')\n"
            "raise SystemExit(code)\n",
            blocked_backend=False,
        )
        self.assert_exit(proc, 0)
        self.assertIn("NO-HTTP-MODULES", proc.stdout)
        self.assert_no_traceback(proc)


class LiveGraphTests(LiveModeTestCase):
    def test_graph_http_mirrors_the_live_state(self):
        proc = self.run_cli("--format", "json", "graph", "--http", self.url)
        payload = json.loads(proc.stdout)
        self.assert_exit(proc, 0)
        self.assertEqual(self.node_ids(payload), ["load", "qc"])
        self.assertTrue(payload["document"]["source"].endswith("/api/state"), payload["document"]["source"])
        self.assertEqual(payload["document"]["meta"]["transport"], "http")
        self.assert_issue_code(payload, "http.live")
        self.assertEqual(self.backend.paths(), ["/api/capabilities", "/api/state"])
        self.assertEqual(self.backend.methods("/api/route"), [])

    def test_graph_http_honours_full(self):
        many = graph_payload([node(f"n{index}") for index in range(600)], [], graph_id="wide", version=1)
        backend = StubBackend(state=many).start()
        self.addCleanup(backend.stop)
        capped = self.run_cli("--format", "json", "graph", "--http", backend.url)
        self.assert_exit(capped, 0)
        capped_payload = json.loads(capped.stdout)
        self.assertEqual(len(self.node_ids(capped_payload)), 500)
        self.assertIn("nodes>500", str(capped_payload["document"]["truncated"]))
        full = self.run_cli("--format", "json", "graph", "--http", backend.url, "--full")
        self.assert_exit(full, 0)
        self.assertEqual(len(self.node_ids(json.loads(full.stdout))), 600)
        self.assertEqual(backend.paths().count("/api/state"), 2)

    def test_graph_http_renders_in_all_three_formats(self):
        for fmt in ("text", "mermaid", "json"):
            with self.subTest(fmt=fmt):
                proc = self.run_cli("graph", "--http", self.url, "--format", fmt)
                self.assert_exit(proc, 0)
                self.assert_no_traceback(proc)
                self.assertFalse(support_has_ansi(proc.stdout), f"{fmt} output carried ANSI escapes")

    def test_a_trailing_slash_in_the_url_does_not_double_the_separator(self):
        proc = self.run_cli("--format", "json", "graph", "--http", self.url + "/")
        self.assert_exit(proc, 0)
        self.assertEqual(self.backend.paths(), ["/api/capabilities", "/api/state"])

    def test_broken_state_json_is_exit_3(self):
        backend = StubBackend(broken={"/api/state": b"<html>not json</html>"}).start()
        self.addCleanup(backend.stop)
        proc = self.run_cli("--format", "json", "graph", "--http", backend.url)
        self.assert_exit(proc, 3)
        self.assert_issue_code(json.loads(proc.stdout), "http.state.invalid_json")
        self.assert_no_traceback(proc)


class LivePromptTests(LiveModeTestCase):
    def test_flow_prompt_http_prints_the_backend_decision(self):
        prompt = "run basic EIS quality checks on the uploaded dataset"
        proc = self.run_cli("--format", "json", "flow", "--prompt", prompt, "--http", self.url)
        self.assert_exit(proc, 0)
        payload = json.loads(proc.stdout)
        self.assertEqual([phase["name"] for phase in payload["phases"]], ["prompt", "candidates", "decision"])
        self.assertEqual(payload["document"]["meta"]["task_id"], "task-live-0001")
        self.assert_issue_code(payload, "http.live")
        self.assert_issue_code(payload, "http.route_recorded")
        decision_steps = payload["phases"][2]["steps"]
        self.assertTrue(decision_steps[0]["name"].startswith("selected eis_basic_qc"), decision_steps[0])
        self.assertEqual(self.backend.methods("/api/route"), ["POST"])
        self.assertEqual(payload["phases"][0]["steps"][0]["detail"], prompt)

    def test_the_live_request_carries_only_the_users_own_prompt(self):
        prompt = "run basic EIS quality checks"
        self.assert_exit(self.run_cli("flow", "--prompt", prompt, "--http", self.url), 0)
        task = self.backend.last_task
        self.assertIsNotNone(task, "the stub received no routing request")
        assert task is not None  # for type checkers
        self.assertEqual(task["user_message"], prompt)
        self.assertTrue(prompt.startswith(task["user_message"]))
        self.assertEqual(task["available_input_types"], ["RawData", "TypedTable"])
        self.assertEqual(task["graph_version"], 7)
        self.assertEqual(task["task_id"], "flowview-http-preview")

    def test_a_long_prompt_is_truncated_to_the_backend_limit_and_disclosed(self):
        prompt = ("EIS 阻抗谱质检要求：样品编号 S-2026-014，频率 0.01 Hz 到 1 MHz。" * 120) + " eis qc"
        self.assertGreater(len(prompt), 4000)
        proc = self.run_cli("--format", "json", "flow", "--prompt", prompt, "--http", self.url)
        self.assert_exit(proc, 0)
        payload = json.loads(proc.stdout)
        sent = (self.backend.last_task or {}).get("user_message", "")
        self.assertEqual(len(sent), 4000)
        self.assertTrue(prompt.startswith(sent), "the request did not carry the prompt's own prefix")
        self.assert_issue_code(payload, "http.prompt_truncated_for_backend")
        self.assertEqual(payload["phases"][0]["steps"][0]["detail"], prompt)

    def test_input_types_the_backend_does_not_report_are_dropped_with_a_warning(self):
        backend = StubBackend(data_types=["RawData"]).start()
        self.addCleanup(backend.stop)
        proc = self.run_cli("--format", "json", "flow", "--prompt", "run eis qc", "--http", backend.url)
        self.assert_exit(proc, 0)
        self.assert_issue_code(json.loads(proc.stdout), "http.unknown_input_type")
        self.assertEqual((backend.last_task or {}).get("available_input_types"), ["RawData"])

    def test_a_cjk_only_prompt_is_sent_verbatim(self):
        prompt = "请对这个阻抗谱数据做基础质检"
        proc = self.run_cli("--format", "json", "flow", "--prompt", prompt, "--http", self.url)
        self.assert_exit(proc, 0)
        self.assertEqual((self.backend.last_task or {}).get("user_message"), prompt)
        self.assertEqual(json.loads(proc.stdout)["phases"][0]["steps"][0]["detail"], prompt)

    def test_an_empty_prompt_is_a_usage_error_not_a_request(self):
        proc = self.run_cli("flow", "--prompt", "   ", "--http", self.url)
        self.assert_exit(proc, 2)
        self.assertEqual(self.backend.requests, [], "an empty prompt still contacted the backend")
        self.assert_stderr_code(proc, "cli.empty_prompt")


class LiveTaskTests(LiveModeTestCase):
    def test_flow_http_task_replays_one_live_record(self):
        proc = self.run_cli("--format", "json", "flow", "--task", "task-live-0001", "--http", self.url)
        self.assert_exit(proc, 0)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["document"]["meta"]["transport"], "http")
        self.assertEqual(payload["document"]["meta"]["task_id"], "task-live-0001")
        self.assertTrue(payload["document"]["source"].endswith("/api/task-summaries/task-live-0001"))
        self.assertIn("/api/task-summaries/task-live-0001", self.backend.paths())

    def test_summary_http_task_replays_one_live_record(self):
        proc = self.run_cli("--format", "json", "summary", "--task", "task-live-0001", "--http", self.url)
        self.assert_exit(proc, 0)
        self.assertEqual(json.loads(proc.stdout)["document"]["meta"]["task_id"], "task-live-0001")

    def test_a_missing_live_task_is_exit_3_with_a_readable_issue(self):
        proc = self.run_cli("--format", "json", "flow", "--task", "nope", "--http", self.url)
        self.assert_exit(proc, 3)
        self.assert_issue_code(json.loads(proc.stdout), "http.task_summary.http_error")
        self.assert_no_traceback(proc)

    def test_a_summary_list_cannot_be_read_over_http(self):
        proc = self.run_cli("summary", "--http", self.url)
        self.assert_exit(proc, 2)
        self.assert_stderr_code(proc, "cli.http_needs_task")
        self.assertEqual(self.backend.requests, [], "the unsupported request was still attempted")


class LiveFailureTests(LiveModeTestCase):
    def test_unreachable_backend_is_exit_3(self):
        url = f"http://127.0.0.1:{closed_port()}"
        proc = self.run_cli("--format", "json", "graph", "--http", url)
        self.assert_exit(proc, 3)
        self.assert_issue_code(json.loads(proc.stdout), "http.unreachable")
        self.assert_no_traceback(proc)

    def test_a_mistyped_http_value_is_a_diagnosis_not_an_internal_error(self):
        proc = self.run_cli("graph", "--http", "not-a-url")
        self.assert_exit(proc, 3)
        self.assert_no_traceback(proc)
        self.assertIn("http(s)", proc.combined)

    def test_backend_unavailable_is_still_a_single_json_document(self):
        url = f"http://127.0.0.1:{closed_port()}"
        for command in (
            ("graph", "--http", url),
            ("flow", "--prompt", "run eis qc", "--http", url),
            ("flow", "--task", "task-1", "--http", url),
            ("summary", "--task", "task-1", "--http", url),
            ("doctor", "--http", url),
        ):
            with self.subTest(command=command[0], args=command[1:]):
                proc = self.run_cli("--format", "json", *command)
                self.assert_exit(proc, 3)
                payload = json.loads(proc.stdout)  # exactly one document, or this raises
                self.assertTrue(payload["issues"], "the failure carried no issue")
                self.assert_no_traceback(proc)

    def test_contract_mismatch_warns_and_strict_turns_it_into_a_failure(self):
        backend = StubBackend(contract={"name": "other-api", "version": "2.0"}).start()
        self.addCleanup(backend.stop)
        proc = self.run_cli("--format", "json", "graph", "--http", backend.url)
        self.assert_exit(proc, 0)
        self.assert_issue_code(json.loads(proc.stdout), "http.contract_mismatch")
        strict = self.run_cli("--format", "json", "graph", "--http", backend.url, "--strict")
        self.assert_exit(strict, 3)

    def test_an_unknown_endpoint_answer_is_not_mistaken_for_a_graph(self):
        backend = StubBackend(state="not an object").start()
        self.addCleanup(backend.stop)
        proc = self.run_cli("--format", "json", "graph", "--http", backend.url)
        self.assert_exit(proc, 3)
        self.assert_issue_code(json.loads(proc.stdout), "http.state_missing")


class LiveOptionContractTests(LiveModeTestCase):
    def test_http_cannot_be_combined_with_local_sources(self):
        cases = (
            (("graph", "--http", self.url, "--graph-file", str(self.tmp / "g.json")), "cli.conflicting_sources"),
            (("flow", "--http", self.url, "--from-file", str(self.tmp / "t.jsonl")), "cli.conflicting_sources"),
            (("flow", "--http", self.url, "--blueprint"), "cli.http_needs_source"),
            (("summary", "--http", self.url, "--file", str(self.tmp / "s.jsonl")), "cli.conflicting_sources"),
        )
        for argv, code in cases:
            with self.subTest(argv=argv):
                proc = self.run_cli(*argv)
                self.assert_exit(proc, 2)
                self.assert_stderr_code(proc, code)
        self.assertEqual(self.backend.requests, [], "a rejected combination still opened a socket")

    def test_http_is_equivalent_before_and_after_the_subcommand(self):
        url = f"http://127.0.0.1:{closed_port()}"
        pre = self.run_cli("--http", url, "--format", "json", "graph")
        post = self.run_cli("graph", "--http", url, "--format", "json")
        self.assertEqual(pre.returncode, post.returncode)
        self.assertEqual(pre.stdout, post.stdout, "--http placement changed the document")

    def test_http_timeout_is_accepted_in_both_placements(self):
        pre = self.run_cli("--http", self.url, "--http-timeout", "2.5", "--format", "json", "graph")
        post = self.run_cli("graph", "--http", self.url, "--http-timeout", "2.5", "--format", "json")
        self.assert_exit(pre, 0)
        self.assert_exit(post, 0)
        self.assertEqual(pre.stdout, post.stdout)

    def test_a_non_finite_timeout_neither_hangs_nor_crashes(self):
        # Negative values must use `--http-timeout=-5`: argparse treats a leading "-" as another
        # option, which is a usage error rather than a timeout value.
        for argv in (
            ("--http-timeout", "nan"),
            ("--http-timeout", "inf"),
            ("--http-timeout", "0"),
            ("--http-timeout=-5",),
        ):
            with self.subTest(argv=argv):
                proc = self.run_cli("graph", "--http", self.url, *argv, "--format", "json")
                self.assert_exit(proc, 0)
                self.assert_no_traceback(proc)

    def test_a_bad_http_timeout_does_not_break_the_command(self):
        proc = self.run_cli("graph", "--http", self.url, "--http-timeout", "soon", "--format", "json")
        self.assert_exit(proc, 2)
        self.assert_stderr_code(proc, "cli.usage")


class LiveDoctorTests(LiveModeTestCase):
    def test_doctor_reports_a_healthy_live_backend(self):
        proc = self.run_cli("doctor", "--http", self.url)
        self.assert_exit(proc, 0)
        self.assertIn("Live backend (--http)", proc.stdout)
        self.assertIn("matflow-http 1.0", proc.stdout)
        self.assertIn("9.9.9", proc.stdout)
        self.assert_no_traceback(proc)

    def test_doctor_reports_an_unreachable_live_backend_as_a_problem(self):
        proc = self.run_cli("doctor", "--http", f"http://127.0.0.1:{closed_port()}")
        self.assert_exit(proc, 3)
        self.assertIn("FAIL reachable", proc.stdout)
        self.assertIn("http.unreachable", proc.stdout)

    def test_doctor_json_carries_the_live_phase(self):
        proc = self.run_cli("doctor", "--http", self.url, "--format", "json")
        self.assert_exit(proc, 0)
        payload = json.loads(proc.stdout)
        names = [phase["name"] for phase in payload["phases"]]
        self.assertIn("live", names)
        self.assertEqual(payload["document"]["meta"]["live_contract_ok"], "true")


class LiveReadOnlyTests(LiveModeTestCase):
    def test_live_commands_write_nothing_into_the_workspace(self):
        from .support import tree_entries

        self.write_graph(LIVE_STATE)
        before = tree_entries(self.data_dir)
        for argv in (
            ("graph", "--http", self.url),
            ("graph", "--http", self.url, "--format", "json", "--out", str(self.tmp / "out.json")),
            ("flow", "--prompt", "run eis qc", "--http", self.url),
            ("summary", "--task", "task-live-0001", "--http", self.url),
            ("doctor", "--http", self.url),
        ):
            self.run_cli(*argv)
        after = {entry for entry in tree_entries(self.data_dir)}
        self.assertEqual(before, after, "a live command wrote into the workspace data directory")

    def test_the_live_default_input_types_match_the_offline_preview(self):
        """A live and an offline preview of one prompt must differ by transport, not by context."""
        from flowview import backend_adapter, live

        self.assertEqual(live.DEFAULT_INPUT_TYPES, backend_adapter._DEFAULT_INPUT_TYPES)


class JsonOutFailureTests(FlowViewTestCase, unittest.TestCase):
    def test_a_failed_out_still_prints_one_document_in_json_mode(self):
        proc = self.run_cli("--format", "json", "graph", "--out", str(self.tmp))
        self.assert_exit(proc, 3)
        payload = json.loads(proc.stdout)
        self.assert_issue_code(payload, "cli.out_failed")
        self.assertEqual(payload["flowview_schema"], "1.0")
        self.assertIn("cannot write", proc.stderr)
        self.assert_no_traceback(proc)

    def test_a_failed_out_prints_no_document_in_text_mode(self):
        proc = self.run_cli("--format", "text", "graph", "--out", str(self.tmp))
        self.assert_exit(proc, 3)
        self.assertEqual(proc.stdout, "", "text mode wrote a document after --out failed")
        self.assertIn("cannot write", proc.stderr)

    def test_a_failed_out_inside_a_live_command_is_also_one_document(self):
        backend = StubBackend().start()
        self.addCleanup(backend.stop)
        proc = self.run_cli("--format", "json", "graph", "--http", backend.url, "--out", str(self.tmp))
        self.assert_exit(proc, 3)
        payload = json.loads(proc.stdout)
        self.assert_issue_code(payload, "cli.out_failed")


class RoundTwoRegressionTests(LiveModeTestCase):
    """Cases a first adversarial pass found: each one used to exit 1, or lied about the backend."""

    DEEP = b'{"nested":' * 5000 + b"1" + b"}" * 5000

    def test_deeply_nested_answers_are_exit_3_not_exit_1(self):
        cases = (
            ("/api/capabilities", ("graph",)),
            ("/api/state", ("graph",)),
            ("/api/route", ("flow", "--prompt", "run eis qc")),
        )
        for path, command in cases:
            backend = StubBackend(broken={path: self.DEEP}).start()
            self.addCleanup(backend.stop)
            with self.subTest(path=path):
                proc = self.run_cli("--format", "json", "--http", backend.url, *command)
                self.assert_exit(proc, 3)
                payload = json.loads(proc.stdout)
                codes = " ".join(str(issue["code"]) for issue in payload["issues"])
                self.assertIn("invalid_json", codes, codes)
                self.assertNotIn("flowview.internal_error", codes)
                self.assert_no_traceback(proc)

    def test_a_non_finite_graph_version_is_tolerated(self):
        backend = StubBackend(state=graph_payload([node("a")], [], version=float("nan"))).start()
        self.addCleanup(backend.stop)
        prompt = self.run_cli("--format", "json", "flow", "--prompt", "run eis qc", "--http", backend.url)
        self.assert_exit(prompt, 0)
        payload = json.loads(prompt.stdout)
        self.assertIn("graph_version 0", " ".join(str(step["detail"]) for step in payload["phases"][0]["steps"]))
        self.assert_no_traceback(prompt)
        graph = self.run_cli("--format", "json", "graph", "--http", backend.url)
        self.assert_exit(graph, 0)

    def test_an_http_error_on_capabilities_is_not_called_unreachable(self):
        backend = StubBackend(capabilities_status=404).start()
        self.addCleanup(backend.stop)
        proc = self.run_cli("--format", "json", "graph", "--http", backend.url)
        self.assert_exit(proc, 3)
        payload = json.loads(proc.stdout)
        codes = [str(issue["code"]) for issue in payload["issues"]]
        self.assertIn("http.capabilities.http_error", codes)
        self.assertNotIn("http.unreachable", codes)
        self.assertNotIn("Cannot reach", proc.stdout + proc.stderr)
        # Nothing was routed, so nothing may claim the backend recorded a summary.
        self.assertNotIn("http.route_recorded", codes)
        doctor = self.run_cli("doctor", "--http", backend.url)
        self.assert_exit(doctor, 3)
        self.assertIn("HTTP 404", doctor.stdout)
        self.assertIn("ok   reachable", doctor.stdout)

    def test_a_broken_route_answer_still_discloses_the_backend_write(self):
        backend = StubBackend(broken={"/api/route": b"<html>not json</html>"}).start()
        self.addCleanup(backend.stop)
        proc = self.run_cli("--format", "json", "flow", "--prompt", "run eis qc", "--http", backend.url)
        self.assert_exit(proc, 3)
        payload = json.loads(proc.stdout)
        codes = [str(issue["code"]) for issue in payload["issues"]]
        self.assertIn("http.route.invalid_json", codes)
        self.assertIn("http.route_recorded", codes)
        disclosure = next(issue for issue in payload["issues"] if issue["code"] == "http.route_recorded")
        self.assertEqual(disclosure["severity"], "warning", "an unknown side effect must not read as neutral")

    def test_the_disclosure_is_an_info_note_when_the_record_is_known(self):
        proc = self.run_cli("--format", "json", "flow", "--prompt", "run eis qc", "--http", self.url)
        self.assert_exit(proc, 0)
        payload = json.loads(proc.stdout)
        disclosure = next(issue for issue in payload["issues"] if issue["code"] == "http.route_recorded")
        self.assertEqual(disclosure["severity"], "info")
        self.assertIn("task-live-0001", disclosure["message"])


class JsonUsageErrorTests(FlowViewTestCase, unittest.TestCase):
    """The "one JSON document on stdout" invariant must survive argparse-level failures too."""

    def test_a_usage_error_in_json_mode_is_still_one_document(self):
        for argv in (
            ("--format", "json", "frobnicate"),
            ("--format", "json"),
            ("graph", "--format", "json", "--width", "wide"),
        ):
            with self.subTest(argv=argv):
                proc = self.run_cli(*argv)
                self.assert_exit(proc, 2)
                payload = json.loads(proc.stdout)
                self.assertEqual(payload["flowview_schema"], "1.0")
                self.assertTrue(payload["issues"])
                self.assertEqual(
                    payload["exit_code_hint"],
                    proc.returncode,
                    "the document promised a different exit status than the process returned",
                )
                self.assert_no_traceback(proc)

    def test_a_usage_error_in_text_mode_still_writes_nothing_to_stdout(self):
        proc = self.run_cli("frobnicate")
        self.assert_exit(proc, 2)
        self.assertEqual(proc.stdout, "")
        self.assertIn("cli.usage", proc.stderr)

    def test_no_subcommand_in_text_mode_still_prints_help(self):
        proc = self.run_cli()
        self.assert_exit(proc, 2)
        self.assertIn("usage:", proc.stdout)


class HostilePayloadTotalityTests(LiveModeTestCase):
    """Values JSON can carry that Python cannot always convert must never exit 1.

    Two sizes matter: a 401-digit integer parses fine but overflows ``float()`` and ``str()``-based
    limits are not yet reached, while a 5001-digit integer exceeds CPython's 4300-digit integer
    string limit, so ``json.loads`` itself refuses it.
    """

    BIG = b"1" + b"0" * 400
    MONSTER = b"1" + b"0" * 5000
    GZIP = b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\x03not-json-at-all"

    def test_a_401_digit_number_is_mirrored_without_a_crash(self):
        raw = (
            b'{"candidates": [{"tool_id": "eis_basic_qc", "version": "1.0.0", "score": '
            + self.BIG
            + b', "reasons": []}], "selected": [], "confidence": '
            + self.BIG
            + b', "rationale": "big", "requires_human_confirmation": false, "model_decisions": [], '
            b'"summary": {"task_id": "task-big"}}'
        )
        backend = StubBackend(broken={"/api/route": raw}).start()
        self.addCleanup(backend.stop)
        proc = self.run_cli("--format", "json", "flow", "--prompt", "run eis qc", "--http", backend.url)
        self.assert_exit(proc, 0)
        payload = json.loads(proc.stdout)
        details = " ".join(str(step["detail"]) for step in payload["phases"][1]["steps"])
        self.assertIn("not scored", details)
        self.assertIn("not recorded", " ".join(str(step["detail"]) for step in payload["phases"][2]["steps"]))
        self.assert_no_traceback(proc)

    def test_a_401_digit_graph_version_and_position_do_not_break_the_graph(self):
        raw = (
            b'{"state": {"graph_id": "hostile", "version": '
            + self.BIG
            + b', "nodes": [{"id": "n1", "label": "n1", "tool_id": "tool.n1", "status": "ready", '
            b'"position": {"x": ' + self.BIG + b', "y": ' + self.BIG + b'}}], "edges": []}}'
        )
        backend = StubBackend(broken={"/api/state": raw}).start()
        self.addCleanup(backend.stop)
        proc = self.run_cli("--format", "json", "graph", "--http", backend.url)
        self.assert_exit(proc, 0)
        payload = json.loads(proc.stdout)
        self.assertIn("n1", self.node_ids(payload))
        self.assert_no_traceback(proc)

    def test_a_401_digit_task_summary_id_and_confidence_stay_readable(self):
        raw = (
            b'{"task_id": '
            + self.BIG
            + b', "status": "completed", "user_prompt": "run eis qc", "decision": {"confidence": '
            + self.BIG
            + b'}, "result": {}, "error_and_handling": {}}'
        )
        backend = StubBackend(broken={"/api/task-summaries/task-big": raw}).start()
        self.addCleanup(backend.stop)
        proc = self.run_cli("--format", "json", "flow", "--task", "task-big", "--http", backend.url)
        self.assert_exit(proc, 0)
        json.loads(proc.stdout)
        self.assert_no_traceback(proc)
        self.assertNotIn("flowview.internal_error", proc.stdout)

    def test_a_5001_digit_number_is_reported_as_unparsable(self):
        """CPython refuses the integer at parse time, so exit 3 with a diagnosis is the honest result."""
        cases = (
            ("/api/capabilities", ("graph",)),
            ("/api/state", ("graph",)),
            ("/api/route", ("flow", "--prompt", "run eis qc")),
        )
        body = b'{"value": ' + self.MONSTER + b"}"
        for path, command in cases:
            backend = StubBackend(broken={path: body}).start()
            self.addCleanup(backend.stop)
            with self.subTest(path=path):
                proc = self.run_cli("--format", "json", "--http", backend.url, *command)
                self.assert_exit(proc, 3)
                payload = json.loads(proc.stdout)
                codes = " ".join(str(issue["code"]) for issue in payload["issues"])
                self.assertIn("invalid_json", codes)
                self.assertNotIn("flowview.internal_error", codes)
                self.assert_no_traceback(proc)

    def test_a_non_utf8_body_is_invalid_json_not_an_internal_error(self):
        cases = (
            ("/api/capabilities", ("graph",), "invalid_json"),
            ("/api/state", ("graph",), "invalid_json"),
            ("/api/route", ("flow", "--prompt", "run eis qc"), "invalid_json"),
        )
        for path, command, suffix in cases:
            backend = StubBackend(broken={path: self.GZIP}).start()
            self.addCleanup(backend.stop)
            with self.subTest(path=path):
                proc = self.run_cli("--format", "json", "--http", backend.url, *command)
                self.assert_exit(proc, 3)
                payload = json.loads(proc.stdout)
                codes = " ".join(str(issue["code"]) for issue in payload["issues"])
                self.assertIn(suffix, codes)
                self.assertNotIn("flowview.internal_error", codes)
                self.assert_no_traceback(proc)


    def test_an_offline_graph_file_with_an_unparsable_number_is_exit_3(self):
        path = self.write_file(
            "monster.json",
            '{"graph_id": "x", "version": ' + "1" + "0" * 5000 + ', "nodes": [], "edges": []}',
        )
        proc = self.run_cli("--format", "json", "graph", "--graph-file", str(path))
        self.assert_exit(proc, 3)
        self.assert_issue_code(json.loads(proc.stdout), "graph.invalid_json")
        self.assert_no_traceback(proc)


class DisclosureAccuracyTests(LiveModeTestCase):
    def test_a_request_that_was_never_sent_carries_no_disclosure(self):
        """A lone surrogate cannot be serialised, so no POST happens and nothing may claim otherwise."""
        body = (
            "import sys\n"
            "from flowview.cli import main\n"
            "code = main(['flow', '--prompt', 'run eis\\ud800qc', '--http', sys.argv[1], '--format', 'json'])\n"
            "print('CODE', code)\n"
        )
        proc = self.run_bootstrap(body, self.url, blocked_backend=False)
        self.assert_no_traceback(proc)
        self.assertIn("CODE 3", proc.stdout)
        self.assertIn("http.unserialisable_request", proc.stdout)
        self.assertNotIn("http.route_recorded", proc.stdout)
        self.assertEqual(self.backend.methods("/api/route"), [], "a request was sent for an unserialisable body")

    def test_doctor_never_calls_a_mistyped_origin_reachable(self):
        proc = self.run_cli("doctor", "--http", "not-a-url")
        self.assert_exit(proc, 3)
        self.assertIn("FAIL reachable", proc.stdout)
        self.assertNotIn("ok   reachable", proc.stdout)
        self.assertIn("http(s)", proc.stdout)


class CredentialRefusalTests(LiveModeTestCase):
    SECRET = "secretpw"

    def credentialed(self) -> str:
        return f"http://user:{self.SECRET}@127.0.0.1:{self.backend.port}"

    def test_credentials_in_http_are_refused_before_anything_is_sent(self):
        proc = self.run_cli("--format", "json", "graph", "--http", self.credentialed())
        self.assert_exit(proc, 2)
        self.assert_stderr_code(proc, "cli.http_credentials")
        self.assertNotIn(self.SECRET, proc.stdout + proc.stderr, "the credential leaked into the output")
        self.assertEqual(self.backend.requests, [], "a credentialed URL was still sent")

    def test_credentials_in_the_environment_variable_are_refused_too(self):
        proc = self.run_cli("--format", "json", "graph", "--http", env_extra={"MATFLOW_API_URL": self.credentialed()})
        self.assert_exit(proc, 2)
        self.assert_stderr_code(proc, "cli.http_credentials")
        self.assertNotIn(self.SECRET, proc.stdout + proc.stderr)
        self.assertEqual(self.backend.requests, [])

    def test_the_transport_refuses_credentials_and_withholds_the_origin(self):
        from flowview import client

        result = client.request_json("GET", f"http://user:{self.SECRET}@127.0.0.1:{self.backend.port}/api/state")
        self.assertFalse(result.ok)
        self.assertEqual(result.url, "(origin withheld)")
        self.assertIsNotNone(result.issue)
        assert result.issue is not None
        self.assertTrue(result.issue.code.endswith(".credentials_not_supported"))
        self.assertNotIn(self.SECRET, result.issue.message)
        self.assertEqual(self.backend.requests, [])


class OutputFailureHonestyTests(FlowViewTestCase, unittest.TestCase):
    def test_a_usage_error_plus_a_failed_out_keeps_both_facts_and_the_right_code(self):
        backend = StubBackend().start()
        self.addCleanup(backend.stop)
        proc = self.run_cli("summary", "--format", "json", "--out", str(self.tmp), "--http", backend.url)
        self.assert_exit(proc, 2)
        payload = json.loads(proc.stdout)
        codes = [str(issue["code"]) for issue in payload["issues"]]
        self.assertIn("cli.out_failed", codes)
        self.assertIn("cli.http_needs_task", codes, "the original diagnosis was lost")
        self.assertEqual(payload["exit_code_hint"], 2, "the document contradicted the process exit code")

    def test_json_is_only_emitted_when_json_is_the_effective_format(self):
        proc = self.run_cli("graph", "--format", "json", "--format", "text", "--width", "wide")
        self.assert_exit(proc, 2)
        self.assertEqual(proc.stdout, "", "JSON was emitted although the last --format was text")


class ThirdPassRegressionTests(LiveModeTestCase):
    """Findings from the third adversarial pass: argv values, latent echoes, redirect hops."""

    def test_an_option_value_that_looks_like_a_format_flag_is_not_a_format_request(self):
        for argv in (
            ("flow", "--prompt", "--format=json", "graph"),
            ("graph", "--search", "--format=json", "--width", "wide"),
        ):
            with self.subTest(argv=argv):
                proc = self.run_cli(*argv)
                self.assert_exit(proc, 2)
                self.assertEqual(proc.stdout, "", "JSON was emitted for a --format inside an option value")

    def test_a_text_mode_usage_error_still_emits_json_when_json_was_asked_for(self):
        proc = self.run_cli("graph", "--format=json", "--width", "wide")
        self.assert_exit(proc, 2)
        self.assertEqual(json.loads(proc.stdout)["flowview_schema"], "1.0")

    def test_the_document_never_echoes_a_credentialed_origin(self):
        from flowview import live

        secret = "toplevelsecret"
        document = live.probe_document(f"http://user:{secret}@127.0.0.1:1")
        rendered = json.dumps(document.to_dict())
        self.assertNotIn(secret, rendered)
        self.assertEqual(document.source, "(origin withheld)")
        self.assertEqual(document.meta["base"], "(origin withheld)")
        self.assertEqual(document.meta["reachable"], "false")
        reachable = document.phases[0].steps[0]
        self.assertEqual(reachable.status, "error", "a refused origin was reported as reached")

    def test_a_redirect_is_refused_instead_of_followed(self):
        backend = StubBackend(redirects={"/api/capabilities": "http://127.0.0.1:1/api/capabilities"}).start()
        self.addCleanup(backend.stop)
        proc = self.run_cli("--format", "json", "graph", "--http", backend.url)
        self.assert_exit(proc, 3)
        payload = json.loads(proc.stdout)
        message = " ".join(str(issue["message"]) for issue in payload["issues"])
        self.assertIn("does not follow redirects", message)
        self.assert_no_traceback(proc)


def support_has_ansi(text: str) -> bool:
    """Local copy so this module does not depend on the shared helper's exact name."""
    return "\x1b" in text


if __name__ == "__main__":  # pragma: no cover - convenience only
    unittest.main()
