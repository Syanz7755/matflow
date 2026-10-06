"""The mirror model must be total: ``from_dict`` never raises and round-trips exactly.

``to_dict() -> from_dict()`` stability is what lets ``--format json`` be fed back into FlowView
(a documented workflow), and totality is what keeps a corrupt / hostile payload from crashing
the printer.
"""
from __future__ import annotations

import json
import unittest

from flowview.model import (
    FlowDocument,
    FlowEdge,
    FlowEvent,
    FlowGraph,
    FlowIssue,
    FlowNode,
    FlowPhase,
    FlowPort,
    FlowStep,
    FlowTrace,
    SourceStatus,
)
from flowview.tests.support import FlowViewTestCase

ISSUE = FlowIssue(
    severity="warning",
    code="graph.dangling_edge",
    message="Edge e1 points outside the graph: a -> b",
    where="data/graph_state.json",
    hint="The graph and its edges were recorded at different times.",
    detail="KeyError: 'b'",
)
PORT_IN = FlowPort(name="in", data_type="Dataset")
PORT_OUT = FlowPort(name="out", data_type="Dataset")
NODE = FlowNode(
    id="n1",
    label="Node one",
    tool_id="tool.one",
    tool_version="1.2.3",
    category="io",
    status="completed",
    params={"alpha": 1, "nested": {"b": [1, 2], "c": None}, "flag": True, "ratio": 0.5},
    input_ports=(PORT_IN,),
    output_ports=(PORT_OUT,),
    error=None,
    issues=(ISSUE,),
    position=(1.5, -2.0),
    known_tool=True,
    review_after_run=True,
)
NODE_2 = FlowNode(id="n2", label="Node two", status="running")
EDGE = FlowEdge(
    id="e1",
    source="n1",
    target="n2",
    source_port="out",
    target_port="in",
    data_type="Dataset",
    dangling=False,
    duplicate_input=False,
)
GRAPH = FlowGraph(
    graph_id="g-1",
    version=7,
    nodes=(NODE, NODE_2),
    edges=(EDGE,),
    source="data/graph_state.json",
    issues=(ISSUE,),
    truncated=("nodes>500",),
)
STEP = FlowStep(name="route.decide", status="running", detail="backend.main:route", error=None, node_id="n1", tools=("tool.one",))
PHASE = FlowPhase(name="route", title="Route", steps=(STEP,), error=None)
EVENT = FlowEvent(
    index=3,
    phase="route",
    name="route.decide",
    status="error",
    detail="decide() returned an error",
    error="ValueError: boom",
    node_id="n1",
    tool_id="tool.one",
)
TRACE = FlowTrace(
    events=(EVENT,),
    task_id="t1",
    trace_id="tr1",
    source="data/audit/trace.jsonl",
    phases=(PHASE,),
    issues=(ISSUE,),
)
DOCUMENT = FlowDocument(
    title="MatFlow flow",
    source="data/graph_state.json",
    graph=GRAPH,
    trace=TRACE,
    phases=(PHASE,),
    issues=(ISSUE,),
    meta={"modes": "graph,trace", "graph_version": "7"},
    truncated=("nodes>500",),
)
SOURCE = SourceStatus(
    name="graph state",
    path="data/graph_state.json",
    exists=True,
    readable=True,
    bytes=1024,
    modified="2024-01-01T00:00:00+00:00",
    detail="ok",
)

SAMPLES = {
    FlowIssue: ISSUE,
    FlowPort: PORT_IN,
    FlowNode: NODE,
    FlowEdge: EDGE,
    FlowGraph: GRAPH,
    FlowStep: STEP,
    FlowPhase: PHASE,
    FlowEvent: EVENT,
    FlowTrace: TRACE,
    FlowDocument: DOCUMENT,
    SourceStatus: SOURCE,
}

JUNK_PAYLOADS = (
    {},
    None,
    [],
    (),
    42,
    -1.5,
    True,
    "a bare string",
    b"bytes",
    {"id": {"nested": "not a string"}},
    {"nodes": 5, "edges": "x", "version": "seven"},
    {"status": [], "severity": {}, "position": "middle", "params": "no", "meta": 9},
    {"events": 3, "phases": {}, "steps": [1], "issues": [None, 5, {"severity": 7}]},
    {"truncated": {"x": 1}, "input_ports": "x", "output_ports": [None], "tools": {"a": 1}},
    {"graph": {"nodes": "x"}, "trace": {"events": "y"}, "source": [], "title": None},
    [{"id": "inner"}],
    {"known_tool": "maybe", "review_after_run": "perhaps", "dangling": "yes", "duplicate_input": 3},
    {"bytes": "not-an-int", "exists": "yes", "readable": []},
)


class FromDictTotalityTests(unittest.TestCase):
    def test_every_constructor_survives_every_junk_payload(self):
        for cls, _sample in SAMPLES.items():
            for payload in JUNK_PAYLOADS:
                with self.subTest(cls=cls.__name__, payload=repr(payload)[:60]):
                    result = cls.from_dict(payload)
                    self.assertIsInstance(result, cls)

    def test_nested_junk_in_a_graph_keeps_going(self):
        graph = FlowGraph.from_dict(
            {
                "graph_id": 5,
                "version": "x",
                "nodes": [{"id": "ok"}, "not-a-node", None, 3, {"id": {"bad": True}}],
                "edges": [{"id": "e", "source": "ok", "target": "ok"}, "nope", None],
                "truncated": [1, None, "cap"],
                "issues": [{"severity": "catastrophe", "code": 7}],
            }
        )
        self.assertIsInstance(graph.graph_id, str)
        self.assertTrue(graph.graph_id)
        self.assertEqual(graph.version, 0)
        self.assertEqual(graph.nodes[0].id, "ok")
        self.assertEqual(len(graph.nodes), 5)
        self.assertEqual(graph.edges[0].id, "e")
        self.assertEqual(len(graph.edges), 3)
        self.assertEqual(graph.truncated, ("1", "", "cap"))

    def test_unknown_status_degrades_to_unknown_and_never_completed(self):
        self.assertEqual(FlowNode.from_dict({"id": "a", "status": "success"}).status, "unknown")
        self.assertEqual(FlowNode.from_dict({"id": "a", "status": "finished"}).status, "unknown")
        self.assertEqual(FlowNode.from_dict({"id": "a"}).status, "unknown")
        self.assertEqual(FlowStep.from_dict({"name": "s", "status": "done"}).status, "unknown")
        self.assertEqual(FlowEvent.from_dict({"status": "finished"}).status, "unknown")

    def test_missing_text_fields_fall_back_to_something_printable(self):
        node = FlowNode.from_dict({})
        self.assertTrue(node.id)
        self.assertTrue(node.display)
        issue = FlowIssue.from_dict({})
        self.assertTrue(issue.message)
        self.assertTrue(issue.code)
        self.assertEqual(FlowIssue.from_dict({"severity": "catastrophe"}).severity, "warning")

    def test_from_dict_output_is_usable_by_renderers_inputs(self):
        node = FlowNode.from_dict({"id": "a", "label": "", "params": {"x": [1, {"y": None}]}})
        self.assertEqual(node.display, "a")
        self.assertEqual(node.params, {"x": [1, {"y": None}]})
        graph = FlowGraph.from_dict({"nodes": [{"id": "a", "status": "completed"}]})
        self.assertEqual(graph.node("a").status, "completed")
        self.assertIsNone(graph.node("missing"))


class RoundTripTests(unittest.TestCase):
    def test_to_dict_then_from_dict_is_exact_for_every_type(self):
        for cls, sample in SAMPLES.items():
            with self.subTest(cls=cls.__name__):
                payload = sample.to_dict()
                self.assertIsInstance(payload, dict)
                restored = cls.from_dict(payload)
                self.assertEqual(restored, sample)
                self.assertEqual(restored.to_dict(), payload)

    def test_to_dict_is_json_safe(self):
        for cls, sample in SAMPLES.items():
            with self.subTest(cls=cls.__name__):
                json.dumps(sample.to_dict())

    def test_key_order_follows_field_order(self):
        for cls, sample in SAMPLES.items():
            with self.subTest(cls=cls.__name__):
                payload = sample.to_dict()
                self.assertEqual(list(payload), [field.name for field in sample.__dataclass_fields__.values()])

    def test_round_trip_through_real_json_text(self):
        text = json.dumps(DOCUMENT.to_dict())
        restored = FlowDocument.from_dict(json.loads(text))
        self.assertEqual(restored, DOCUMENT)
        self.assertEqual(restored.to_dict(), json.loads(text))

    def test_document_digest_fields_survive_the_round_trip(self):
        restored = FlowDocument.from_dict(DOCUMENT.to_dict())
        self.assertEqual(restored.error_count, DOCUMENT.error_count)
        self.assertEqual(restored.warning_count, DOCUMENT.warning_count)
        self.assertEqual(restored.all_issues(), DOCUMENT.all_issues())
        self.assertIsNotNone(restored.graph)
        self.assertIsNotNone(restored.trace)

    def test_none_parts_stay_none(self):
        document = FlowDocument(title="bare", source="none")
        restored = FlowDocument.from_dict(document.to_dict())
        self.assertIsNone(restored.graph)
        self.assertIsNone(restored.trace)
        self.assertEqual(restored, document)

    def test_wrong_typed_parts_do_not_become_empty_objects(self):
        restored = FlowDocument.from_dict({"title": "x", "source": "y", "graph": "nope", "trace": 5})
        self.assertIsNone(restored.graph)
        self.assertIsNone(restored.trace)


class LoaderIntegrationRoundTripTests(FlowViewTestCase, unittest.TestCase):
    """A document produced by the real loader must survive the JSON round trip unchanged."""

    def test_loaded_document_round_trips(self):
        from flowview.loader import read_graph

        self.write_graph(
            {
                "graph_id": "integration",
                "version": 4,
                "nodes": [
                    {"id": "a", "label": "A", "tool_id": "tool.a", "status": "completed"},
                    {"id": "b", "label": "B", "status": "error", "output": {"error": "boom"}},
                ],
                "edges": [{"id": "e", "source": "a", "target": "b"}],
            }
        )
        document = read_graph()
        payload = document.to_dict()
        self.assertEqual(FlowDocument.from_dict(payload).to_dict(), payload)
        json.dumps(payload)

    def test_loaded_document_from_payload_matches_from_dict(self):
        from flowview.analysis import build_document
        from flowview.loader import graph_from_payload

        graph = graph_from_payload({"nodes": [{"id": "a", "status": "ready"}], "edges": []})
        document = build_document(title="T", source="s", graph=graph)
        self.assertEqual(FlowDocument.from_dict(document.to_dict()), document)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
