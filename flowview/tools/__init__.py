"""Support scripts for FlowView (report generators, one-off renderers).

Nothing in here is imported by the CLI or by the tests: `python -m flowview` keeps working when
this package is deleted. Each module is a runnable tool with its own ``--help``.
"""
from __future__ import annotations

__all__ = ["run_prompt_cases"]
