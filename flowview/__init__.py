"""FlowView: a read-only CLI that prints the MatFlow backend flow.

The package is deliberately independent of ``backend.*``. Importing :mod:`flowview` must work
in an environment where the backend cannot be imported at all — that property is tested.
"""
from __future__ import annotations

from typing import Any

from . import analysis, codes
from .model import (
    FlowDocument,
    FlowEdge,
    FlowEvent,
    FlowGraph,
    FlowIssue,
    FlowNode,
    FlowPhase,
    FlowStep,
    FlowTrace,
    SourceStatus,
)

VERSION = "0.1.0"

__all__ = [
    "VERSION",
    "FlowDocument",
    "FlowEdge",
    "FlowEvent",
    "FlowGraph",
    "FlowIssue",
    "FlowNode",
    "FlowPhase",
    "FlowStep",
    "FlowTrace",
    "SourceStatus",
    "analysis",
    "codes",
    "main",
]


def main(argv: Any = None) -> int:
    """Entry point; imported lazily so ``import flowview`` stays free of CLI parsing."""
    from .cli import main as cli_main

    return cli_main(argv)
