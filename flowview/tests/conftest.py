"""Pytest bootstrap: make the repository root importable without installing MatFlow.

``python -m unittest discover`` already puts the top-level directory on ``sys.path``; pytest
needs the same guarantee so ``import flowview`` resolves when the suite is run from anywhere.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
