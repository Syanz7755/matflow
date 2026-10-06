"""The Domain Package contract.

Platform Core stays domain-neutral: it owns typed workflows, the Tool lifecycle,
execution, review and audit. A Domain Package is a versioned extension that
contributes scientific data types, ToolSpecs, executors, declarative Recipes and
explicit compatibility migrations for legacy Tool IDs.

The minimum contract is a manifest plus those registrations. Nothing in Core
branches on a package id, and a workspace that composes no package exposes no
scientific-domain capability at all.
"""
from __future__ import annotations

import importlib.metadata
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping

from pydantic import BaseModel, Field

from ..analysis_recipes import AnalysisRecipe
from ..contracts import CORE_CONTRACT_VERSION, DataTypeDefinition, ToolSpec
from ..data_types import DataTypeRegistry
from ..executors import ExecutorRegistry

DOMAIN_PACKAGE_ENTRY_POINT_GROUP = "matflow.domain_packages"
LEGACY_REVIEW_POLICY_MIGRATION = "review_policy"

# The composition the shipped application enables. Platform Core itself loads
# nothing, so this stays a deployment choice rather than a Core default.
REFERENCE_PACKAGE_IDS: tuple[str, ...] = ("eis", "xrd", "ftir", "qe", "qe_demo")


class DomainPackageManifest(BaseModel):
    """The minimum declaration every loadable Domain Package publishes."""

    package_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    label: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=1000)
    core_contract: str = Field(default=CORE_CONTRACT_VERSION, pattern=r"^\d+\.\d+$")
    acceptance_tests: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()


def _no_executors(registry: ExecutorRegistry) -> None:
    return None


@dataclass(frozen=True)
class DomainPackage:
    """One versioned extension: declarations plus its executor registrations."""

    manifest: DomainPackageManifest
    data_types: Mapping[str, DataTypeDefinition] = field(default_factory=dict)
    tool_specs: Mapping[str, ToolSpec] = field(default_factory=dict)
    recipes: Mapping[str, AnalysisRecipe] = field(default_factory=dict)
    # Recipe domains this package owns. Core validates recipe *shape* only; the
    # vocabulary of domain names comes from here.
    recipe_domains: tuple[str, ...] = ()
    migrations: Mapping[str, str] = field(default_factory=dict)
    register_executors: Callable[[ExecutorRegistry], None] = _no_executors


class DomainPackageSet:
    """The packages one workspace composes, with conflict detection."""

    def __init__(self, packages: Iterable[DomainPackage] = ()):
        self._packages = tuple(packages)
        selected_ids = {package.manifest.package_id for package in self._packages}
        self._data_types: dict[str, DataTypeDefinition] = {}
        self._tool_specs: dict[str, ToolSpec] = {}
        self._recipes: dict[str, AnalysisRecipe] = {}
        self._recipe_domains: dict[str, str] = {}
        self._migrations: dict[str, str] = {}
        seen_ids: set[str] = set()
        for package in self._packages:
            package_id = package.manifest.package_id
            missing_packages = sorted(set(package.manifest.requires) - selected_ids)
            if missing_packages:
                raise ValueError(f"Domain package {package_id} requires package(s): {', '.join(missing_packages)}")
            if package_id in seen_ids:
                raise ValueError(f"Domain package declared twice: {package_id}")
            seen_ids.add(package_id)
            self._merge(self._data_types, package.data_types, "data type", package)
            self._merge(self._tool_specs, package.tool_specs, "tool", package)
            self._merge(self._recipes, package.recipes, "recipe", package)
            self._merge(self._migrations, package.migrations, "legacy tool id", package)
            for domain in package.recipe_domains:
                owner = self._recipe_domains.get(domain)
                if owner is not None:
                    raise ValueError(f"Recipe domain {domain} is already owned by domain package {owner}")
                self._recipe_domains[domain] = package.manifest.package_id
            for recipe_id, recipe in package.recipes.items():
                if recipe.recipe_id != recipe_id:
                    raise ValueError(f"Domain package {package_id} recipe key {recipe_id} does not match its recipe_id")
                if recipe.domain not in package.recipe_domains:
                    raise ValueError(f"Domain package {package_id} recipe {recipe_id} uses unowned domain {recipe.domain}")

    @staticmethod
    def _merge(target: dict[str, Any], incoming: Mapping[str, Any], kind: str, package: DomainPackage) -> None:
        for key, value in incoming.items():
            if key in target:
                raise ValueError(f"Domain package {package.manifest.package_id} redeclares {kind}: {key}")
            target[key] = value

    def packages(self) -> tuple[DomainPackage, ...]:
        return self._packages

    def package_ids(self) -> tuple[str, ...]:
        return tuple(package.manifest.package_id for package in self._packages)

    def data_types(self) -> dict[str, DataTypeDefinition]:
        return dict(self._data_types)

    def tool_specs(self) -> dict[str, ToolSpec]:
        return dict(self._tool_specs)

    def recipes(self) -> dict[str, AnalysisRecipe]:
        return dict(self._recipes)

    def recipe_domains(self) -> tuple[str, ...]:
        """Every recipe domain the loaded packages own, and nothing else."""
        return tuple(sorted(self._recipe_domains))

    def migrations(self) -> dict[str, str]:
        return dict(self._migrations)

    def legacy_tool_ids(self, migration: str = LEGACY_REVIEW_POLICY_MIGRATION) -> tuple[str, ...]:
        """Legacy Tool IDs this package set declares for one migration policy."""
        return tuple(sorted(key for key, policy in self._migrations.items() if policy == migration))

    def register_executors(self, registry: ExecutorRegistry) -> None:
        for package in self._packages:
            package.register_executors(registry)

    def legacy_view(self) -> dict[str, dict[str, Any]]:
        return {
            package_id: {
                "version": package.manifest.version,
                "label": package.manifest.label,
                "description": package.manifest.description,
                "core_contract": package.manifest.core_contract,
                "requires": sorted(package.manifest.requires),
                "data_types": sorted(package.data_types),
                "tools": sorted(package.tool_specs),
                "recipe_domains": sorted(package.recipe_domains),
                "recipes": sorted(package.recipes),
            }
            for package_id, package in ((package.manifest.package_id, package) for package in self._packages)
        }


def compose_type_registry(
    package_set: DomainPackageSet,
    custom_types: Mapping[str, Any] | None = None,
) -> DataTypeRegistry:
    """Validate platform types together with package types and custom types.

    This is the single place that encodes the precedence rule: a workspace may
    add custom types, but it may never replace a type a loaded Domain Package
    owns.
    """
    package_types = {name: definition.model_dump() for name, definition in package_set.data_types().items()}
    custom = dict(custom_types or {})
    replaced = sorted(set(custom) & set(package_types))
    if replaced:
        raise ValueError(f"A custom data type cannot replace a Domain Package type: {', '.join(replaced)}")
    return DataTypeRegistry({**package_types, **custom})


def builtin_entry_points() -> dict[str, Callable[[], DomainPackage]]:
    """In-repository packages shipped with this build."""
    from .eis import build_package as build_eis
    from .qe import build_package as build_qe
    from .ftir import build_package as build_ftir
    from .xrd import build_package as build_xrd
    from .qe_demo import build_package as build_qe_demo

    return {"eis": build_eis, "xrd": build_xrd, "ftir": build_ftir, "qe": build_qe, "qe_demo": build_qe_demo}


class DomainPackageLoader:
    """Resolve package ids to factories and load them under a Core contract."""

    def __init__(self, entry_points: Mapping[str, Callable[[], DomainPackage]] | None = None):
        self._entry_points: dict[str, Callable[[], DomainPackage]] = dict(
            builtin_entry_points() if entry_points is None else entry_points
        )

    def register(self, package_id: str, factory: Callable[[], DomainPackage]) -> None:
        if package_id in self._entry_points:
            raise ValueError(f"Domain package already registered: {package_id}")
        self._entry_points[package_id] = factory

    def available(self) -> tuple[str, ...]:
        return tuple(sorted(set(self._entry_points) | set(self.discover_installed())))

    def discover_installed(self) -> tuple[str, ...]:
        """Independent distributions may advertise packages as entry points."""
        discovered: list[str] = []
        try:
            entry_points = importlib.metadata.entry_points()
        except Exception:  # pragma: no cover - metadata is unavailable in some embeds
            return ()
        selected = entry_points.select(group=DOMAIN_PACKAGE_ENTRY_POINT_GROUP) if hasattr(entry_points, "select") else []
        for entry_point in selected:
            discovered.append(entry_point.name)
            self._entry_points.setdefault(entry_point.name, entry_point.load())
        return tuple(sorted(discovered))

    def load(self, package_ids: Iterable[str], *, core_contract: str = CORE_CONTRACT_VERSION) -> DomainPackageSet:
        packages: list[DomainPackage] = []
        for package_id in package_ids:
            factory = self._entry_points.get(package_id)
            if factory is None:
                raise ValueError(f"Unknown domain package: {package_id}")
            package = factory()
            if package.manifest.package_id != package_id:
                raise ValueError(
                    f"Domain package entry point {package_id} declares package_id {package.manifest.package_id}"
                )
            if package.manifest.core_contract != core_contract:
                raise ValueError(
                    f"Domain package {package_id} requires Platform Core contract "
                    f"{package.manifest.core_contract}, this build provides {core_contract}"
                )
            packages.append(package)
        return DomainPackageSet(packages)


def load_domain_packages(
    package_ids: Iterable[str] = (),
    *,
    loader: DomainPackageLoader | None = None,
    core_contract: str = CORE_CONTRACT_VERSION,
) -> DomainPackageSet:
    """Load the named packages; an empty request composes an empty Core."""
    return (loader or DomainPackageLoader()).load(package_ids, core_contract=core_contract)
