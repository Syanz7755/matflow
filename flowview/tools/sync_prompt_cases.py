"""Synchronise a prompt suite's recorded route facts with what the backend actually decides.

The suite keeps both a human expectation (``expected_route``) and the last observed result
(``observed_route``), so a report can say "this case is misrouted" instead of quietly accepting
whatever the retriever produced.

    python -m flowview.tools.sync_prompt_cases --suite examples/long_prompt_cases.json
    python -m flowview.tools.sync_prompt_cases --suite examples/long_prompt_cases.json --write
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SUITE = ROOT / "examples" / "long_prompt_cases.json"


def observe(prompt: str) -> dict[str, Any]:
    from ..backend_adapter import _runtime  # noqa: PLC2701 - deliberate: reuse the adapter's loader
    from .. import backend_adapter

    workspace, base = _runtime(None)
    routing = backend_adapter._import_module("backend.routing")
    contracts = backend_adapter._import_module("backend.contracts")
    registry = workspace.registry()
    task = contracts.TaskState(
        task_id="suite-sync",
        user_message=prompt,
        graph_version=0,
        available_input_types=["RawData", "TypedTable"],
    )
    decision = routing.DecisionRouter().decide(task, registry)
    selected = [candidate.tool_id for candidate in getattr(decision, "selected", ()) or ()]
    candidates = [candidate.tool_id for candidate in getattr(decision, "candidates", ()) or ()]
    return {
        "selected": selected,
        "candidate_count": len(candidates),
        "candidates": candidates[:8],
        "confidence": round(float(getattr(decision, "confidence", 0.0) or 0.0), 4),
        "requires_human_confirmation": bool(getattr(decision, "requires_human_confirmation", False)),
        "rationale": str(getattr(decision, "rationale", "") or ""),
    }


def update(case: Mapping[str, Any]) -> dict[str, Any]:
    observed = observe(str(case.get("prompt") or ""))
    expectation = case.get("expected_route")
    if expectation is None:
        expectation = case.get("expected_registered_id")
    expectation = str(expectation) if expectation else "(none)"
    observed_selected = observed["selected"][0] if observed["selected"] else "(none)"
    missing = case.get("registered_capability") == "missing"
    updated = dict(case)
    updated["expected_route"] = expectation
    updated["observed_route"] = observed
    if expectation == observed_selected:
        updated["route_verdict"] = "as_expected"
    elif missing:
        updated["route_verdict"] = "expected_unsupported"
    else:
        updated["route_verdict"] = "misrouted"
    updated.pop("expected_registered_id", None)
    return updated


def load_suite(path: Path) -> dict[str, Any]:
    """Read a suite, converting every failure into a clear message and exit code 3."""
    if not path.exists():
        raise SystemExit(f"Suite not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Suite is not valid JSON: {path}: line {exc.lineno}, column {exc.colno}: {exc.msg}")
    except (OSError, UnicodeDecodeError) as exc:
        raise SystemExit(f"Suite could not be read: {path}: {exc}")
    if not isinstance(payload, dict) or not isinstance(payload.get("cases"), list):
        raise SystemExit(f"Suite must be a JSON object with a 'cases' array: {path}")
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m flowview.tools.sync_prompt_cases")
    parser.add_argument("--suite", default=str(DEFAULT_SUITE))
    parser.add_argument("--write", action="store_true", help="write the file back (default: dry report)")
    args = parser.parse_args(list(argv) if argv is not None else None)

    path = Path(args.suite).expanduser()
    try:
        suite = load_suite(path)
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        return 3
    updated_cases = []
    for case in suite["cases"]:
        if not isinstance(case, Mapping) or not str(case.get("prompt") or "").strip():
            print(f"skipped a case without a usable prompt: {case!r}"[:200], file=sys.stderr)
            updated_cases.append(case)
            continue
        updated = update(case)
        updated_cases.append(updated)
        print(f"{updated.get('case_id', '?'):<36} {updated['route_verdict']:<22} selected={updated['observed_route']['selected']}")

    if args.write:
        suite["cases"] = updated_cases
        # LF preserved so a prompt that is quoted verbatim stays byte-identical.
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(suite, ensure_ascii=False, indent=2) + "\n")
        print(f"\nwrote {path}")
    else:
        print("\n(dry run; pass --write to persist)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
