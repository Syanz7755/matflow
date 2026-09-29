"""Deterministic, bounded previews for workflow outputs.

Preview rendering never executes model-authored HTML or browser code.  It only
normalizes data into one of the small transport shapes documented in
docs/NODE_PREVIEW_SPEC.md.
"""
from __future__ import annotations

import json
from typing import Any

from .contracts import PreviewRule, ToolSpec


def _bounded_json(value: Any, *, depth: int = 0, max_depth: int = 5, max_items: int = 40) -> Any:
    if depth >= max_depth:
        return "…"
    if isinstance(value, dict):
        items = list(value.items())[:max_items]
        result = {str(key): _bounded_json(item, depth=depth + 1, max_depth=max_depth, max_items=max_items) for key, item in items}
        if len(value) > max_items: result["…"] = f"{len(value) - max_items} more fields"
        return result
    if isinstance(value, list):
        result = [_bounded_json(item, depth=depth + 1, max_depth=max_depth, max_items=max_items) for item in value[:max_items]]
        if len(value) > max_items: result.append(f"… {len(value) - max_items} more items")
        return result
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _fallback_rule(output: dict[str, Any]) -> PreviewRule:
    if isinstance(output.get("preview"), list): return PreviewRule(renderer="table_head")
    if isinstance(output.get("text"), str) or isinstance(output.get("message"), str): return PreviewRule(renderer="text")
    return PreviewRule(renderer="json_tree")


def build_preview(output: dict[str, Any] | None, spec: ToolSpec) -> dict[str, Any] | None:
    if not output:
        return None
    output_kind = str(output.get("kind") or "")
    port = next((name for name, kind in spec.outputs.items() if kind == output_kind), next(iter(spec.outputs), "output"))
    rule = spec.preview_spec.outputs.get(port) or _fallback_rule(output)
    if rule.renderer == "table_head":
        rows = output.get("preview") if isinstance(output.get("preview"), list) else output.get("rows")
        if not isinstance(rows, list):
            return {"kind": "json_tree", "port": port, "data": _bounded_json(output), "fallback": True}
        bounded = []
        for row in rows[:rule.max_rows]:
            if isinstance(row, dict): bounded.append(dict(list(row.items())[:rule.max_columns]))
            else: bounded.append(row)
        return {"kind": "table", "port": port, "rows": bounded, "truncated": len(rows) > len(bounded)}
    if rule.renderer == "text":
        raw = output.get("text", output.get("message", json.dumps(output, ensure_ascii=False, default=str)))
        text = str(raw)
        return {"kind": "text", "port": port, "text": text[:rule.max_characters], "truncated": len(text) > rule.max_characters}
    if rule.renderer == "image":
        image = output.get("image") or output.get("artifact")
        if isinstance(image, dict) and image.get("mime_type") in {"image/png", "image/jpeg", "image/webp"} and isinstance(image.get("url"), str):
            return {"kind": "image", "port": port, "mime_type": image["mime_type"], "url": image["url"]}
        return {"kind": "json_tree", "port": port, "data": _bounded_json(output), "fallback": True}
    return {"kind": "json_tree", "port": port, "data": _bounded_json(output)}
