"""The reference composition that the shipped application enables.

Platform Core composes no scientific package by itself. Tests that exercise the
EIS reference capability opt in here, exactly as `backend.main` does, so the
Domain Package boundary is proven instead of bypassed.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.data_types import DataTypeRegistry
from backend.domain_packages import REFERENCE_PACKAGE_IDS, compose_type_registry, load_domain_packages
from backend.tool_registry import ToolRegistry
from backend.workspace_runtime import WorkspaceRuntime

PACKAGES = REFERENCE_PACKAGE_IDS


def registry(
    custom_nodes: dict[str, dict[str, Any]] | None = None,
    type_registry: DataTypeRegistry | None = None,
) -> ToolRegistry:
    """The shipped tool catalog: platform tools plus the reference packages.

    Package tools are validated against the type registry, so the package types
    must be composed in as well — exactly what WorkspaceRuntime does.
    """
    packages = load_domain_packages(PACKAGES)
    return ToolRegistry(
        custom_nodes,
        type_registry or compose_type_registry(packages),
        package_specs=packages.tool_specs(),
    )


def workspace(root: Path, **kwargs: Any) -> WorkspaceRuntime:
    """A workspace composed like the shipped application."""
    kwargs.setdefault("packages", PACKAGES)
    return WorkspaceRuntime(root, **kwargs)
