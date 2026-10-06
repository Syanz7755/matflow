"""Run a prompt-case suite through FlowView and save every rendered flow.

For each case in the suite this writes the prompt (Markdown + JSON), the deterministic
``--prompt`` routing flow, the written-down backend phase blueprint, and a recorded task's real
flow when the workspace has one. It also builds a single browseable index so the printed diagrams
can be reviewed without opening 60 files.

This is a report generator, not a test: it never fails the build, it records what happened.

    python -m flowview.tools.run_prompt_cases --suite examples/long_prompt_cases.json \
        --out examples/reports/prompt_flows
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .. import analysis
from ..codes import EXIT_OK, describe_exception
from ..model import FlowDocument

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SUITE = ROOT / "examples" / "long_prompt_cases.json"
DEFAULT_OUT = ROOT / "examples" / "reports" / "prompt_flows"
DEFAULT_FORMATS = ("mermaid", "text", "json")
MAX_STEM = 64


class _RenderOptions:
    """The option surface ``flowview.cli`` renderers expect, without building an ArgumentParser."""

    def __init__(self, fmt: str, *, width: int = 0, direction: str = "TD", no_color: bool = True, no_legend: bool = False) -> None:
        self.format = fmt
        self.width = width
        self.direction = direction
        self.no_color = no_color
        self.no_legend = no_legend
        self.verbose = False
        self.out = None
        self.strict = False


def _render(document: FlowDocument, fmt: str, *, width: int = 0, direction: str = "TD") -> str:
    from ..cli import _render as cli_render

    options = _RenderOptions(fmt, width=width, direction=direction)
    # Long prompts and long tool ids need more room than the CLI default, or the diagram hides the
    # very evidence the report exists to show.
    if fmt == "mermaid":
        from ..mermaid import MermaidRenderer

        return MermaidRenderer(direction=direction, max_label=72).render_document(document)
    return cli_render(document, options, None)


def _write(path: Path, text: str) -> Path:
    """Write UTF-8 with LF newlines preserved.

    ``Path.write_text`` translates ``\\n`` to the platform separator by default, which would make
    every saved prompt differ from its input on Windows — the opposite of what a report that quotes
    prompts verbatim must do.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = text if text.endswith("\n") else text + "\n"
    with path.open("w", encoding="utf-8", errors="backslashreplace", newline="\n") as handle:
        handle.write(payload)
    return path


def _slug(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in "-_" else "-" for char in str(value)).strip("-")
    return (cleaned or "case")[:MAX_STEM]


def load_suite(path: Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(payload, Mapping) or not isinstance(payload.get("cases"), list):
        raise ValueError(f"Suite {path} must be a JSON object with a 'cases' array.")
    return dict(payload)


def _case_meta(case: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: case[key]
        for key in (
            "case_id",
            "domain",
            "language",
            "intent",
            "fixture_hint",
            "expected_route",
            "registered_capability",
            "route_expectation_note",
            "route_verdict",
            "why_long",
            "notes",
        )
        if case.get(key) is not None
    }


def _route_facts(document: FlowDocument) -> dict[str, Any]:
    """Read the decision back out of the rendered document so the index can summarise it."""
    selected: list[str] = []
    candidates: list[str] = []
    confidence: str | None = None
    rationale: str | None = None
    confirmation = bool(document.meta.get("confirmation") == "yes")
    retriever_tokens: str | None = document.meta.get("retriever_tokens")
    cjk_characters: str | None = document.meta.get("cjk_characters")
    for phase in document.phases:
        for step in phase.steps:
            if phase.name == "candidates" and step.tools:
                candidates.append(step.tools[0])
            if phase.name == "decision":
                if step.tools:
                    selected.extend(step.tools)
                detail = step.detail or ""
                if "confidence " in detail:
                    confidence = detail.split("confidence ", 1)[1].split(";", 1)[0].strip()
                if "rationale: " in detail:
                    rationale = detail.split("rationale: ", 1)[1].strip()
            if step.name == "retriever tokenisation" and step.detail:
                detail = step.detail
                if retriever_tokens is None and "ASCII token(s)," in detail:
                    retriever_tokens = detail.split("ASCII token(s),", 1)[0].rsplit(":", 1)[-1].strip()
                if cjk_characters is None and "CJK character(s)" in detail:
                    cjk_characters = detail.split("CJK character(s)", 1)[0].rsplit(",", 1)[-1].strip()
    return {
        "selected": selected,
        "candidates": candidates,
        "confidence": confidence,
        "rationale": rationale,
        "requires_human_confirmation": confirmation,
        "retriever_tokens": retriever_tokens,
        "cjk_characters": cjk_characters,
    }


def _case_markdown(case: Mapping[str, Any], index: int) -> str:
    meta = _case_meta(case)
    lines = [
        f"# Case {index}: `{case.get('case_id')}`",
        "",
        f"- domain: `{meta.get('domain', '?')}`",
        f"- language: `{meta.get('language', '?')}`",
        f"- intent: `{meta.get('intent', '?')}`",
    ]
    if meta.get("fixture_hint"):
        lines.append(f"- fixture hint: `{meta['fixture_hint']}`")
    if meta.get("expected_route"):
        lines.append(f"- expected route: `{meta['expected_route']}` (capability {meta.get('registered_capability', '?')})")
    if meta.get("route_verdict"):
        lines.append(f"- last observed route verdict: **{meta['route_verdict']}**")
    observed = case.get("observed_route") or {}
    if observed:
        lines.append(
            f"- last observed selection: `{', '.join(observed.get('selected') or []) or '(none)'}` "
            f"(confidence {observed.get('confidence')}, {observed.get('candidate_count', 0)} candidate(s))"
        )
    if meta.get("route_expectation_note"):
        lines.append(f"- route expectation: {meta['route_expectation_note']}")
    if meta.get("why_long"):
        lines.append(f"- why this prompt is long: {meta['why_long']}")
    if meta.get("notes"):
        lines.append(f"- note: {meta['notes']}")
    lines += [
        "",
        f"Prompt length: {len(str(case.get('prompt', '')))} characters.",
        "",
        "## Input prompt",
        "",
        "```text",
        str(case.get("prompt", "")),
        "```",
        "",
    ]
    return "\n".join(lines)


def render_case(case: Mapping[str, Any], out_dir: Path, formats: Sequence[str], *, index: int = 0) -> dict[str, Any]:
    """Render one case and return its index record."""
    from ..backend_adapter import dry_route

    case_id = str(case.get("case_id") or "case")
    prompt = str(case.get("prompt") or "")
    case_dir = out_dir / _slug(case_id)
    expected = str(case.get("expected_route") or "(none)")
    record: dict[str, Any] = {
        "case_id": case_id,
        **_case_meta(case),
        "index": index,
        "prompt_characters": len(prompt),
        "outputs": {},
        "errors": [],
    }
    _write(case_dir / "prompt.md", _case_markdown(case, index))

    document = dry_route(prompt)
    facts = _route_facts(document)
    record["route"] = facts
    selected = facts["selected"][0] if facts["selected"] else "(none)"
    if selected == expected:
        record["verdict"] = "as_expected"
    elif case.get("registered_capability") == "missing":
        record["verdict"] = "expected_unsupported"
    else:
        record["verdict"] = "misrouted"
    record["diagnosed_errors"] = [issue.code for issue in document.all_issues() if issue.severity == "error"]
    record["diagnosed_warnings"] = [issue.code for issue in document.all_issues() if issue.severity == "warning"]
    for fmt in formats:
        try:
            text = _render(document, fmt, width=100)
            name = "flow-prompt.mermaid" if fmt == "mermaid" else f"flow-prompt.{fmt}.txt"
            _write(case_dir / name, text)
            record["outputs"][f"flow-prompt.{fmt}"] = len(text)
        except Exception as exc:  # noqa: BLE001 - a report generator records, never fails
            record["errors"].append(f"{fmt}: {describe_exception(exc)}")
    return record


def render_blueprint(out_dir: Path, formats: Sequence[str]) -> dict[str, Any]:
    """The written-down runtime lifecycle, rendered once as a stage reference."""
    from ..phases import blueprint_document

    document = blueprint_document()
    stage_dir = out_dir / "_stages"
    written: dict[str, int] = {}
    for fmt in formats:
        try:
            text = _render(document, fmt, width=110)
            name = "blueprint.mermaid" if fmt == "mermaid" else f"blueprint.{fmt}.txt"
            _write(stage_dir / name, text)
            written[f"blueprint.{fmt}"] = len(text)
        except Exception as exc:  # noqa: BLE001
            print(f"blueprint {fmt} failed: {exc}", file=sys.stderr)
    # Per-phase extraction so one long file is not the only way to read the lifecycle.
    per_phase: list[dict[str, Any]] = []
    for index, phase in enumerate(document.phases, 1):
        phase_doc = analysis.build_document(
            title=f"{document.title} — phase {index}: {phase.title}",
            source=document.source,
            phases=(phase,),
            meta={"stage_index": str(index), "stage_name": phase.name, "stage_title": phase.title},
            modes=("stages",),
        )
        stem = f"stage-{index:02d}-{_slug(phase.name)}"
        _write(stage_dir / f"{stem}.txt", _render(phase_doc, "text", width=110))
        _write(stage_dir / f"{stem}.mermaid", _render(phase_doc, "mermaid"))
        per_phase.append(
            {
                "index": index,
                "name": phase.name,
                "title": phase.title,
                "steps": len(phase.steps),
                "status": analysis.phase_status(phase),
                "files": [f"_stages/{stem}.txt", f"_stages/{stem}.mermaid"],
            }
        )
    return {"files": written, "phases": per_phase}


def render_recorded_task(out_dir: Path, formats: Sequence[str]) -> dict[str, Any] | None:
    """A real recorded task: its prompt and its actual route/execute/outcome stages."""
    from ..loader import default_summary_path
    from ..tasks import load_task_summaries

    path = default_summary_path()
    if not path.exists():
        return None
    documents = load_task_summaries(path)
    if not documents:
        return None
    # The newest record that actually carries a decision is the most interesting one.
    chosen: FlowDocument | None = None
    for document in reversed(documents):
        if document.meta.get("status") in {"routed", "waiting", "completed", "failed"}:
            chosen = document
            break
    if chosen is None:
        chosen = documents[-1]

    task_dir = out_dir / "_task"
    written: dict[str, int] = {}
    for fmt in formats:
        try:
            text = _render(chosen, fmt, width=110)
            name = "recorded-task.mermaid" if fmt == "mermaid" else f"recorded-task.{fmt}.txt"
            _write(task_dir / name, text)
            written[f"recorded-task.{fmt}"] = len(text)
        except Exception as exc:  # noqa: BLE001
            print(f"recorded task {fmt} failed: {exc}", file=sys.stderr)
    for index, phase in enumerate(chosen.phases, 1):
        phase_doc = analysis.build_document(
            title=f"Recorded task — stage {index}: {phase.title}",
            source=chosen.source,
            phases=(phase,),
            meta=dict(chosen.meta) | {"stage_index": str(index), "stage_name": phase.name},
            modes=("stages",),
        )
        stem = f"task-stage-{index:02d}-{_slug(phase.name)}"
        _write(task_dir / f"{stem}.txt", _render(phase_doc, "text", width=110))
        _write(task_dir / f"{stem}.mermaid", _render(phase_doc, "mermaid"))
    _write(task_dir / "task-record.json", json.dumps(chosen.to_dict(), ensure_ascii=False, indent=2))
    return {
        "task_id": chosen.meta.get("task_id"),
        "trace_id": chosen.meta.get("trace_id"),
        "status": chosen.meta.get("status"),
        "prompt": chosen.meta.get("prompt") or _first_prompt(chosen),
        "source": chosen.source,
        "files": written,
    }


def _prompts_markdown(suite: Mapping[str, Any], records: Sequence[Mapping[str, Any]]) -> str:
    """Every input prompt in full, next to its rendered flow, in one file."""
    lines = [
        f"# Full input prompts — {suite.get('suite_id', 'suite')}",
        "",
        f"All {len(records)} prompts, verbatim, in suite order. Sizes: "
        + ", ".join(f"`{record['case_id']}`={record.get('prompt_characters', 0)}" for record in records) + ".",
        "",
        "| # | case_id | chars | flow |",
        "| --- | --- | --- | --- |",
    ]
    for index, record in enumerate(records, 1):
        lines.append(
            f"| {index} | `{record['case_id']}` | {record.get('prompt_characters', 0)} | "
            f"[mermaid]({record['case_id']}/flow-prompt.mermaid) · [text]({record['case_id']}/flow-prompt.text.txt) |"
        )
    lines.append("")
    for index, record in enumerate(records, 1):
        route = record.get("route") or {}
        lines += [
            "---",
            "",
            f"## {index}. `{record['case_id']}` — {record.get('prompt_characters', 0)} characters",
            "",
            f"- domain `{record.get('domain', '?')}` · language `{record.get('language', '?')}` · intent `{record.get('intent', '?')}`",
            f"- expected route `{record.get('expected_route', '?')}` · selected `{', '.join(route.get('selected') or []) or '(none)'}` · verdict **{record.get('verdict', '?')}**",
            f"- printed flow: [mermaid]({record['case_id']}/flow-prompt.mermaid) · [text]({record['case_id']}/flow-prompt.text.txt) · [json]({record['case_id']}/flow-prompt.json.txt)",
            "",
            "```text",
            str(record.get("prompt_full", record.get("prompt_preview", ""))).strip(),
            "```",
            "",
        ]
    return "\n".join(lines)


def _first_prompt(document: FlowDocument) -> str:
    for phase in document.phases:
        for step in phase.steps:
            if step.name.lower().startswith("prompt") and step.detail:
                return step.detail
    return ""


def _index_markdown(suite: Mapping[str, Any], records: Sequence[Mapping[str, Any]], stages: Mapping[str, Any], task: Mapping[str, Any] | None) -> str:
    verdicts: dict[str, int] = {}
    for record in records:
        verdicts[record.get("verdict", "unknown")] = verdicts.get(record.get("verdict", "unknown"), 0) + 1
    misrouted = [record for record in records if record.get("verdict") == "misrouted"]
    false_matches = [record for record in records if record.get("verdict") == "expected_unsupported" and (record.get("route") or {}).get("selected")]

    lines = [
        f"# Long-prompt flow outputs — {suite.get('suite_id', 'suite')}",
        "",
        str(suite.get("purpose", "")).strip(),
        "",
        f"- cases: **{len(records)}**",
        f"- total prompt text: **{sum(record.get('prompt_characters', 0) for record in records)} characters**",
        f"- scope: {suite.get('scope', '')}",
        "- routing mode: deterministic lexical retriever, JEV model router disabled, nothing persisted (offline, reproducible)",
        f"- verdicts: " + ", ".join(f"{name}={count}" for name, count in sorted(verdicts.items())),
        "",
        "## How to read this directory",
        "",
        "- `<case_id>/prompt.md` — the exact input prompt, with its metadata and route expectation.",
        "- `<case_id>/flow-prompt.mermaid` — the route flow as a Mermaid flowchart (paste into any Mermaid viewer).",
        "- `<case_id>/flow-prompt.text.txt` — the same flow as terminal tables.",
        "- `<case_id>/flow-prompt.json.txt` — the same flow as a single JSON document.",
        "- `_stages/` — the written-down backend runtime lifecycle, whole and per stage.",
        "- `_task/` — one real recorded task from `data/audit/task_summaries.jsonl`, whole and per stage.",
        "",
        "## Routing observations (these are backend findings, not printer findings)",
        "",
        "The printed flow is a faithful record of what the backend decided, so a wrong route shows up here",
        "as a wrong route — not as a printer bug. Two classes appear in this suite:",
        "",
        f"- **misrouted** ({len(misrouted)}): a matching tool IS registered and active, yet another tool was selected.",
        f"- **false match on a missing capability** ({len(false_matches)}): no tool for this request is registered, yet one was selected anyway.",
        "",
        "Root cause visible in every `flow-prompt.text.txt` under the `retriever tokenisation` step:",
        "`backend/routing.py` tokenises with `[a-z0-9]+`, so CJK text contributes **zero** tokens. A long Chinese",
        "prompt is therefore almost invisible to lexical retrieval, and whatever Latin fragments it contains",
        "(file names, column headers, units) decide the route. That is why a 595-character EIS request lands on",
        "`ebrick_case05_import` instead of `eis_basic_qc`.",
        "",
    ]
    if misrouted or false_matches:
        lines += [
            "| case_id | expected | selected | class | evidence |",
            "| --- | --- | --- | --- | --- |",
        ]
        for record in [*misrouted, *false_matches]:
            route = record.get("route") or {}
            selected = ", ".join(route.get("selected") or []) or "(none)"
            lines.append(
                f"| `{record['case_id']}` | `{record.get('expected_route')}` | `{selected}` | "
                f"{record.get('verdict')} | [{record['case_id']} text]({record['case_id']}/flow-prompt.text.txt) |"
            )
        lines.append("")

    lines += [
        "## Prompt index",
        "",
        "| # | case_id | domain | lang | intent | chars | expected | selected | verdict | files |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for index, record in enumerate(records, 1):
        route = record.get("route") or {}
        selected = ", ".join(route.get("selected") or []) or "(none)"
        files = f"[flow]({record['case_id']}/flow-prompt.mermaid) · [text]({record['case_id']}/flow-prompt.text.txt)"
        lines.append(
            f"| {index} | `{record['case_id']}` | {record.get('domain', '?')} | {record.get('language', '?')} | "
            f"{record.get('intent', '?')} | {record.get('prompt_characters', 0)} | `{record.get('expected_route', '?')}` | "
            f"`{selected}` | {record.get('verdict', '?')} | {files} |"
        )
    lines += [
        "",
        "## Route summary",
        "",
        "| case_id | candidates | selected | confidence | confirmation | retriever tokens | CJK chars | rationale |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for record in records:
        route = record.get("route") or {}
        rationale = (route.get("rationale") or "").replace("|", "\\|")
        tokens = route.get("retriever_tokens", record.get("retriever_tokens", "?"))
        cjk = route.get("cjk_characters", record.get("cjk_characters", "?"))
        lines.append(
            f"| `{record['case_id']}` | {len(route.get('candidates') or [])} | "
            f"`{', '.join(route.get('selected') or []) or '(none)'}` | {route.get('confidence') or '?'} | "
            f"{'yes' if route.get('requires_human_confirmation') else 'no'} | {tokens} | {cjk} | {rationale} |"
        )

    if task:
        lines += [
            "",
            "## Recorded task (real data)",
            "",
            f"- task_id: `{task.get('task_id')}`",
            f"- trace_id: `{task.get('trace_id')}`",
            f"- status: `{task.get('status')}`",
            f"- source: `{task.get('source')}`",
            f"- prompt: {task.get('prompt') or '(not recorded in this summary)'}",
            f"- files: [flow](_task/recorded-task.mermaid) · [text](_task/recorded-task.text.txt) · [record](_task/task-record.json)",
        ]

    lines += [
        "",
        "## Backend stage reference",
        "",
        f"- whole lifecycle: [{stages['files'] and '_stages/blueprint.mermaid'}](_stages/blueprint.mermaid) · [_stages/blueprint.text.txt](_stages/blueprint.text.txt)",
        "",
        "| stage | name | title | steps | status | files |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for phase in stages.get("phases", []):
        lines.append(
            f"| {phase['index']} | `{phase['name']}` | {phase['title']} | {phase['steps']} | {phase['status']} | "
            f"[text]({phase['files'][0]}) · [mermaid]({phase['files'][1]}) |"
        )
    lines += [
        "",
        "## Case notes and prompts",
        "",
    ]
    for index, record in enumerate(records, 1):
        lines.append(f"### {index}. `{record['case_id']}`")
        lines.append("")
        if record.get("why_long"):
            lines.append(f"*{record['why_long']}*")
            lines.append("")
        if record.get("errors"):
            lines.append(f"Render warnings: {'; '.join(record['errors'])}")
            lines.append("")
        lines.append(f"Prompt ({record.get('prompt_characters', 0)} characters) — full text in [{record['case_id']}/prompt.md]({record['case_id']}/prompt.md):")
        lines.append("")
        lines.append("```text")
        lines.append(str(record.get("prompt_preview", "")).strip())
        lines.append("```")
        lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Render every case in the suite. Returns 0 unless the suite itself is unusable."""
    parser = argparse.ArgumentParser(
        prog="python -m flowview.tools.run_prompt_cases",
        description="Run a long-prompt case suite through FlowView and save every printed flow.",
    )
    parser.add_argument("--suite", default=str(DEFAULT_SUITE), help="case suite JSON (default: examples/long_prompt_cases.json)")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="output directory (default: examples/reports/prompt_flows)")
    parser.add_argument("--formats", default=",".join(DEFAULT_FORMATS), help="comma-separated formats to save")
    parser.add_argument("--limit", type=int, default=0, help="render only the first N cases (0 = all)")
    parser.add_argument("--no-task", action="store_true", help="skip the recorded-task section")
    parser.add_argument("--quiet", action="store_true", help="only print the summary line")
    args = parser.parse_args(list(argv) if argv is not None else None)

    suite_path = Path(args.suite).expanduser()
    out_dir = Path(args.out).expanduser()
    formats = tuple(item.strip() for item in str(args.formats).split(",") if item.strip())
    if not formats:
        print("No formats requested.", file=sys.stderr)
        return 2
    if not suite_path.exists():
        print(f"Suite not found: {suite_path}", file=sys.stderr)
        return 3

    from ..cli import configure_stdout

    configure_stdout()
    suite = load_suite(suite_path)
    cases = list(suite["cases"])
    if args.limit and args.limit > 0:
        cases = cases[: args.limit]

    records: list[dict[str, Any]] = []
    for index, case in enumerate(cases, 1):
        record = render_case(case, out_dir, formats, index=index)
        prompt = str(case.get("prompt") or "")
        record["prompt_full"] = prompt
        record["prompt_preview"] = prompt if len(prompt) <= 600 else prompt[:600].rstrip() + " …"
        records.append(record)
        if not args.quiet:
            route = record.get("route") or {}
            print(
                f"[{index:>2}/{len(cases)}] {record['case_id']:<34} "
                f"{record['prompt_characters']:>5} chars -> {', '.join(route.get('selected') or []) or '(none)':<28} "
                f"{record.get('verdict', '?')}"
            )

    stages = render_blueprint(out_dir, formats)
    task = None if args.no_task else render_recorded_task(out_dir, formats)

    index_md = _index_markdown(suite, records, stages, task)
    index_path = _write(out_dir / "INDEX.md", index_md)
    # The prompts are large, so keep the report payload free of them and give the reader one file
    # that holds every input verbatim.
    prompts_path = _write(out_dir / "PROMPTS.md", _prompts_markdown(suite, records))
    report_records = [{key: value for key, value in record.items() if key != "prompt_full"} for record in records]
    report = {
        "suite": str(suite_path),
        "suite_id": suite.get("suite_id"),
        "generated_by": "flowview.tools.run_prompt_cases",
        "routing_mode": "lexical DecisionRouter, JEV model router disabled, nothing persisted",
        "formats": list(formats),
        "cases": report_records,
        "stages": stages,
        "recorded_task": task,
    }
    report_path = _write(out_dir / "run-report.json", json.dumps(report, ensure_ascii=False, indent=2))
    print()
    print(f"cases rendered : {len(records)}")
    print(f"characters     : {sum(record['prompt_characters'] for record in records)} across all prompts")
    print(f"index          : {index_path}")
    print(f"prompts        : {prompts_path}")
    print(f"report         : {report_path}")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
