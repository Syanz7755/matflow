"""Explicit, offline reference-case demos.

Demo entry points in this module select a pinned case directly.  They do not
route a prompt, ask an LLM to plan a workflow, or submit work to a scheduler.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .domain_packages.qe_demo import build_demo_patch
from .workspace_runtime import WorkspaceRuntime

QE_MGO_PROMPT = "For pristine MgO SCF, generate QE input and report convergence and total energy."
QE_MGO_FIXTURES = (
    ("qe_input", "qe_mgo_scf.in"),
    ("qe_stdout", "qe_mgo_scf.log"),
)


class DemoArchiveError(RuntimeError):
    """The requested demo archive cannot be created safely or completely."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fixture_records() -> list[dict[str, Any]]:
    fixture_root = Path(__file__).with_name("domain_packages") / "qe_demo_fixtures"
    return [
        {
            "role": role,
            "packaged_path": f"backend/domain_packages/qe_demo_fixtures/{name}",
            "sha256": _sha256(fixture_root / name),
        }
        for role, name in QE_MGO_FIXTURES
    ]


def run_qe_mgo_demo(output: Path) -> dict[str, Any]:
    """Run the pinned MgO replay case into a brand-new archive directory."""
    destination = output.expanduser().resolve()
    try:
        destination.mkdir()
    except FileExistsError as exc:
        raise DemoArchiveError(f"Refusing to overwrite existing path: {destination}") from exc
    except FileNotFoundError as exc:
        raise DemoArchiveError(f"Output parent does not exist: {destination.parent}") from exc

    runtime = WorkspaceRuntime(destination, packages=("qe", "qe_demo"))
    if runtime.data_root != destination and destination not in runtime.data_root.parents:
        raise DemoArchiveError(
            "The active MATFLOW_DATA_ROOT points outside the new demo archive; unset it and retry."
        )
    patch = build_demo_patch(runtime.read_state().version, QE_MGO_PROMPT)
    runtime.apply_graph_patch(patch)
    outcome = runtime.execute_workflow(restart=True)
    if not outcome["ok"] or outcome["stopped"]:
        raise DemoArchiveError(f"QE MgO demo did not complete: {outcome['errors']}")

    nodes = {node["id"]: node for node in outcome["state"]["nodes"]}
    input_result = nodes["qe-demo-input"]["output"]
    parsed_result = nodes["qe-demo-result"]["output"]
    workspace_path = runtime.data_root.relative_to(destination).as_posix()
    summary = {
        "schema_version": 1,
        "demo_id": "qe-mgo",
        "title": "Pristine MgO QE SCF historical replay",
        "case_selection": {
            "mode": "explicit_pinned_case",
            "prompt": QE_MGO_PROMPT,
            "llm_planning": False,
            "keyword_routing": False,
        },
        "execution": {
            "mode": "historical_output_replay",
            "offline": True,
            "llm_called": False,
            "hpc_submitted": False,
            "ok": outcome["ok"],
            "stopped": outcome["stopped"],
        },
        "workflow": {
            "workspace_path": workspace_path,
            "graph_state": f"{workspace_path}/graph_state.json",
            "version": outcome["state"]["version"],
            "revision": outcome["state"]["revision"],
            "node_count": len(outcome["state"]["nodes"]),
            "edge_count": len(outcome["state"]["edges"]),
            "node_statuses": {node_id: node["status"] for node_id, node in nodes.items()},
        },
        "result": {
            "atom_count": input_result["atom_count"],
            "convergence": parsed_result["convergence"],
            "iterations": parsed_result["iterations"],
            "energy": parsed_result["energy"],
            "provenance": parsed_result["provenance"],
        },
        "sources": _fixture_records(),
        "limitations": [
            "This is a replay of one packaged historical QE output, not a new QE calculation.",
            "No pseudopotential files are bundled or validated by this replay.",
            "The fixed case does not establish transferability to other structures, settings, or materials.",
        ],
    }
    (destination / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary
