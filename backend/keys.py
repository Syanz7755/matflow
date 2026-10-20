"""Stable identifiers derived from user-visible labels (any script, CJK included)."""
from __future__ import annotations

import hashlib
import re

_ASCII_SLUG = re.compile(r"[^a-z0-9_]+")
_LABEL_DROP = re.compile(r"[^\w \-]")
_SPACES = re.compile(r" +")


def node_key_from_label(label: str) -> str:
    """ASCII slug of the label when it has one (unchanged historical behaviour), otherwise a
    deterministic ``node_<8 hex of sha1(label)>`` so a pure-Chinese label still gets a usable key."""
    slug = _ASCII_SLUG.sub("_", label.lower()).strip("_")
    if slug:
        return slug
    stripped = label.strip()
    if not stripped:
        return ""
    return "node_" + hashlib.sha1(stripped.encode("utf-8")).hexdigest()[:8]


def label_from_message(message: str, *, limit: int = 48, default: str = "Derived Analysis") -> str:
    """A short display label from free text: Unicode letters, digits, ``_``, ``-`` and spaces are kept."""
    cleaned = _SPACES.sub(" ", _LABEL_DROP.sub("", message)).strip()
    return cleaned[:limit].strip() or default
