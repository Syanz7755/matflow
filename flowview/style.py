"""Terminal styling, colour detection, and East-Asian-aware width helpers for FlowView text."""
from __future__ import annotations

import os
import re
import sys
import unicodedata
from typing import Any

_RESET = "\x1b[0m"

# ANSI SGR codes per status word. Words are always printed by the renderers; colour is extra.
STATUS_CODES: dict[str, str] = {
    "ready": "36",
    "running": "34",
    "completed": "32",
    "waiting": "33",
    "error": "31",
    "cancelled": "35",
    "unknown": "90",
    # step-only vocabulary, kept here so phase timelines colour consistently with nodes
    "pending": "36",
    "skipped": "90",
}
ISSUE_CODES: dict[str, str] = {"info": "36", "warning": "33", "error": "31"}

_ANSI_RE = re.compile("\x1b\\[[0-9;?]*[ -/]*[@-~]")
_AMBIGUOUS_WIDE = frozenset({"W", "F"})
_ZERO_WIDTH_CATEGORIES = frozenset({"Mn", "Me", "Cf", "Cc", "Cs"})


def _as_text(value: Any) -> str:
    """Best-effort text conversion: never raises, and ``None`` becomes an empty string."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return str(value)
    except Exception:  # noqa: BLE001 - width helpers must never be the reason printing fails
        return ""


def strip_ansi(text: Any) -> str:
    """Remove ANSI escape sequences so measuring and escaping see visible characters only."""
    return _ANSI_RE.sub("", _as_text(text))


class Style:
    """ANSI helpers. ``Style(enabled=False)`` is byte-identical to no styling at all."""

    __slots__ = ("enabled",)

    def __init__(self, enabled: bool = False) -> None:
        try:
            self.enabled = bool(enabled)
        except Exception:  # noqa: BLE001 - a broken flag must degrade to plain text
            self.enabled = False

    def _wrap(self, text: Any, code: str) -> str:
        body = _as_text(text)
        if not self.enabled or not body:
            return body
        try:
            return f"\x1b[{code}m{body}{_RESET}"
        except Exception:  # noqa: BLE001
            return body

    def bold(self, text: str) -> str:
        """Bold when enabled; otherwise the text unchanged."""
        return self._wrap(text, "1")

    def dim(self, text: str) -> str:
        """Dimmed when enabled; otherwise the text unchanged."""
        return self._wrap(text, "2")

    def status(self, text: str, status: str) -> str:
        """Colour a status word when enabled; unknown statuses stay plain."""
        code = STATUS_CODES.get(_as_text(status).strip().lower())
        return self._wrap(text, code) if code else _as_text(text)

    def issue(self, text: str, severity: str) -> str:
        """Colour an issue line by severity when enabled; unknown severities stay plain."""
        code = ISSUE_CODES.get(_as_text(severity).strip().lower())
        return self._wrap(text, code) if code else _as_text(text)


def color_enabled(stream: Any | None = None, override: bool | None = None) -> bool:
    """Decide whether ANSI colour may be used. Never raises.

    Precedence: an explicit ``override``, then ``NO_COLOR`` (any value, because colour is
    opt-in and an ambiguous environment must resolve to plain text), then ``TERM=dumb``, then
    the stream: a stream that is missing or is not a tty never receives escape sequences.
    """
    try:
        if override is not None:
            return bool(override)
        if "NO_COLOR" in os.environ:
            return False
        if (os.environ.get("TERM") or "").strip().lower() == "dumb":
            return False
        target = stream if stream is not None else sys.stdout
        isatty = getattr(target, "isatty", None)
        if not callable(isatty):
            return False
        return bool(isatty())
    except Exception:  # noqa: BLE001 - colour must never break the printer
        return False


def _char_width(ch: str) -> int:
    """Display cells for one character: 0 for controls/combining, 2 for wide/fullwidth."""
    code = ord(ch)
    if code == 0:
        return 0
    if code < 32 or 0x7F <= code < 0xA0:
        return 0
    try:
        if unicodedata.combining(ch):
            return 0
        category = unicodedata.category(ch)
    except Exception:  # noqa: BLE001
        return 1
    if category in _ZERO_WIDTH_CATEGORIES:
        return 0
    try:
        return 2 if unicodedata.east_asian_width(ch) in _AMBIGUOUS_WIDE else 1
    except Exception:  # noqa: BLE001
        return 1


def display_width(text: Any) -> int:
    """Printable width of ``text`` in terminal cells, ignoring ANSI escapes and combining marks."""
    total = 0
    for ch in strip_ansi(text):
        total += _char_width(ch)
    return total


def pad(text: Any, width: int) -> str:
    """Right-pad ``text`` with spaces to ``width`` cells; never shortens and never raises."""
    body = _as_text(text)
    try:
        target = int(width)
    except Exception:  # noqa: BLE001
        return body
    if target <= 0:
        return body
    missing = target - display_width(body)
    return body + " " * missing if missing > 0 else body


def truncate(text: Any, width: int) -> str:
    """Cut ``text`` to ``width`` cells, appending ``…`` when something was removed."""
    body = _as_text(text)
    try:
        target = int(width)
    except Exception:  # noqa: BLE001
        return body
    if target <= 0:
        return ""
    if display_width(body) <= target:
        return body
    if target == 1:
        return "\u2026"
    plain = strip_ansi(body)
    budget = target - 1
    kept: list[str] = []
    used = 0
    for ch in plain:
        size = _char_width(ch)
        if used + size > budget:
            break
        kept.append(ch)
        used += size
    return "".join(kept) + "\u2026"


def _hard_split(token: str, width: int) -> list[str]:
    """Split one over-long token into chunks of at most ``width`` display cells."""
    chunks: list[str] = []
    current: list[str] = []
    used = 0
    for ch in token:
        size = _char_width(ch)
        if current and used + size > width:
            chunks.append("".join(current))
            current = []
            used = 0
        current.append(ch)
        used += size
    if current:
        chunks.append("".join(current))
    return chunks or [""]


def wrap(text: Any, width: int) -> list[str]:
    """Word-wrap ``text`` to ``width`` cells, honouring newlines, indentation and long words."""
    body = strip_ansi(_as_text(text)).replace("\r\n", "\n").replace("\r", "\n")
    try:
        target = int(width)
    except Exception:  # noqa: BLE001
        return [body]
    if target <= 0:
        return [body]
    lines: list[str] = []
    for paragraph in body.split("\n"):
        stripped = paragraph.lstrip(" \t")
        indent = paragraph[: len(paragraph) - len(stripped)]
        available = target - display_width(indent)
        if not stripped:
            lines.append("")
            continue
        if available < 8:
            indent = ""
            available = target
        current = ""
        for word in stripped.split(" "):
            candidate = word if not current else f"{current} {word}"
            if display_width(candidate) <= available:
                current = candidate
                continue
            if current:
                lines.append(indent + current)
                current = ""
            if display_width(word) > available:
                chunks = _hard_split(word, available)
                lines.extend(indent + chunk for chunk in chunks[:-1])
                current = chunks[-1]
            else:
                current = word
        lines.append(indent + current)
    return lines or [""]


def can_encode(stream: Any | None = None, text: str | None = None) -> bool:
    """Whether ``stream`` can encode box-drawing text (FlowView falls back to ASCII when not)."""
    probe = text if text is not None else "\u2500\u2502\u250c\u2510\u2514\u2518\u251c\u2524\u252c\u2534\u253c\u2026"
    target = stream if stream is not None else sys.stdout
    encoding: Any = None
    try:
        encoding = getattr(target, "encoding", None)
        if not encoding:
            buffer = getattr(target, "buffer", None)
            encoding = getattr(buffer, "encoding", None)
        if not encoding:
            # No declared encoding: trust it only if it still looks like a writable stream.
            if not callable(getattr(target, "write", None)):
                return False
            encoding = "utf-8"  # in-memory streams hold anything
        _as_text(probe).encode(str(encoding))
    except Exception:  # noqa: BLE001 - any failure means "do not risk unencodable glyphs"
        return False
    return True


def summary_symbols(stream: Any | None = None) -> dict[str, str]:
    """The small glyph set renderers need; ASCII variants when the stream cannot encode."""
    if can_encode(stream):
        return {"ellipsis": "\u2026", "bullet": "\u2022", "rule": "\u2500", "dot": "\u00b7"}
    return {"ellipsis": "...", "bullet": "*", "rule": "=", "dot": "."}


__all__ = [
    "ISSUE_CODES",
    "STATUS_CODES",
    "Style",
    "can_encode",
    "color_enabled",
    "display_width",
    "pad",
    "strip_ansi",
    "summary_symbols",
    "truncate",
    "wrap",
]
