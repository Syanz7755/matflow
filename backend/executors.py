"""The executor seam: one registry between validated nodes and their execution.

Platform Core registers only domain-neutral executors here. A Domain Package
contributes its own executors through the same registry, so no scientific
branch is compiled into Core and an unloaded package simply resolves nothing.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol

from .contracts import GraphState, Node, ToolSpec


class ExecutorHost(Protocol):
    """The narrow runtime surface an executor is allowed to call.

    Keeping this surface explicit is what stops a domain executor from reaching
    around validation, auditing or the authoritative workspace API.
    """

    @property
    def model_adapter_configured(self) -> bool: ...

    def complete_with_model(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]: ...

    def node_input(self, state: GraphState, node_id: str, port: str) -> Node: ...

    def node_inputs(self, state: GraphState, node_id: str, port: str) -> list[Node]: ...

    def dataset_frame(self, upload_id: str) -> Any: ...

    def inspect_dataset(self, upload_id: str) -> dict[str, Any]: ...

    def data_type_registry(self) -> Any: ...


@dataclass(frozen=True)
class NodeExecution:
    """Everything one executor may read for a single node run."""

    runtime: ExecutorHost
    state: GraphState
    node: Node
    spec: ToolSpec


@dataclass(frozen=True)
class ExecutionOutcome:
    """An executor's output plus an optional control-plane request.

    `stop` cancels downstream work, which is how a data-driven conditional gate
    prevents the rest of the graph from running on a failed quality report.
    """

    output: dict[str, Any]
    stop: bool = False


Executor = Callable[[NodeExecution], "dict[str, Any] | ExecutionOutcome"]


class ToolExecutionError(ValueError):
    """A user-facing execution failure with a stable machine-readable code."""

    def __init__(self, code: str, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable

# Namespaces the platform itself owns. A hand-built registry may not inject them,
# so a caller cannot shadow a platform or package executor by construction.
RESERVED_EXECUTOR_NAMESPACES: tuple[str, ...] = ("builtin:", "custom:", "recipe:")


class ExecutorRegistry:
    """Resolve one ``executor_ref`` to the single callable that owns it."""

    def __init__(
        self,
        executors: Mapping[str, Executor] | None = None,
        prefixes: Mapping[str, Executor] | None = None,
    ):
        self._executors: dict[str, Executor] = {}
        self._prefixes: dict[str, Executor] = {}
        # Construction goes through the same guard rails as registration, and a
        # hand-built registry additionally may not claim a reserved namespace.
        for ref, executor in (executors or {}).items():
            if ref.startswith(RESERVED_EXECUTOR_NAMESPACES):
                raise ValueError(f"Executor reference is reserved by the platform: {ref}")
            self.register(ref, executor)
        for prefix, executor in (prefixes or {}).items():
            if prefix in RESERVED_EXECUTOR_NAMESPACES:
                raise ValueError(f"Executor prefix is reserved by the platform: {prefix}")
            self.register_prefix(prefix, executor)

    def register(self, ref: str, executor: Executor) -> None:
        if not ref or ":" not in ref:
            raise ValueError("An executor reference must be namespaced, for example 'builtin:raw_file_import'")
        if ref in self._executors:
            raise ValueError(f"Executor already registered: {ref}")
        self._executors[ref] = executor

    def register_prefix(self, prefix: str, executor: Executor) -> None:
        """Register a family whose members cannot be enumerated in advance.

        Declarative ``recipe:`` tools are created per proposal, so their refs are
        resolved by prefix instead of by enumeration.
        """
        if not prefix.endswith(":"):
            raise ValueError("An executor prefix must end with ':'")
        if prefix in self._prefixes:
            raise ValueError(f"Executor prefix already registered: {prefix}")
        self._prefixes[prefix] = executor

    def resolve(self, ref: str | None) -> Executor:
        if ref:
            exact = self._executors.get(ref)
            if exact is not None:
                return exact
            for prefix, executor in sorted(self._prefixes.items(), key=lambda item: -len(item[0])):
                if ref.startswith(prefix):
                    return executor
        raise ValueError("No executor registered for this node")

    def refs(self) -> tuple[str, ...]:
        return tuple(sorted((*self._executors, *(f"{prefix}*" for prefix in self._prefixes))))

    @classmethod
    def platform(cls) -> "ExecutorRegistry":
        """The domain-neutral executors every workspace composes."""
        from .builtin_executors import register_platform_executors

        registry = cls()
        register_platform_executors(registry)
        return registry
