"""Hetu models: index state, binding receipt, provider status, bounded query results."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Literal


INDEX_STATES: tuple[str, ...] = (
    "missing",
    "indexing",
    "ready",
    "stale",
    "unverifiable",
    "unavailable",
    "conflict_needs_choice",
)

IndexState = Literal[
    "missing",
    "indexing",
    "ready",
    "stale",
    "unverifiable",
    "unavailable",
    "conflict_needs_choice",
]


@dataclass(frozen=True)
class IndexBindingReceipt:
    """Local Hetu↔provider binding receipt (runtime state, not repo SSOT)."""

    schema: str
    repo_identity: str
    repo_realpath_hash: str
    provider: str
    provider_project: str
    provider_version: str
    index_mode: str
    persistence: bool
    index_commit: str
    git_status_short_empty: bool
    auto_watch_effective: bool
    node_count: int
    edge_count: int
    bound_at: str
    binding_hash: str | None = None

    def with_binding_hash(self, binding_hash: str) -> IndexBindingReceipt:
        return replace(self, binding_hash=binding_hash)

    def canonical_payload(self) -> dict[str, Any]:
        """Fields covered by binding_hash (excludes binding_hash itself)."""
        return {
            "schema": self.schema,
            "repo_identity": self.repo_identity,
            "repo_realpath_hash": self.repo_realpath_hash,
            "provider": self.provider,
            "provider_project": self.provider_project,
            "provider_version": self.provider_version,
            "index_mode": self.index_mode,
            "persistence": self.persistence,
            "index_commit": self.index_commit,
            "git_status_short_empty": self.git_status_short_empty,
            "auto_watch_effective": self.auto_watch_effective,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "bound_at": self.bound_at,
        }

    def to_dict(self) -> dict[str, Any]:
        out = self.canonical_payload()
        out["binding_hash"] = self.binding_hash
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IndexBindingReceipt:
        return cls(
            schema=str(data["schema"]),
            repo_identity=str(data["repo_identity"]),
            repo_realpath_hash=str(data["repo_realpath_hash"]),
            provider=str(data["provider"]),
            provider_project=str(data["provider_project"]),
            provider_version=str(data["provider_version"]),
            index_mode=str(data["index_mode"]),
            persistence=bool(data["persistence"]),
            index_commit=str(data["index_commit"]),
            git_status_short_empty=bool(data["git_status_short_empty"]),
            auto_watch_effective=bool(data["auto_watch_effective"]),
            node_count=int(data["node_count"]),
            edge_count=int(data["edge_count"]),
            bound_at=str(data["bound_at"]),
            binding_hash=None if data.get("binding_hash") is None else str(data["binding_hash"]),
        )


@dataclass(frozen=True)
class ProviderStatusResult:
    provider: str
    provider_version: str | None
    provider_project: str | None
    index_state: IndexState
    index_commit: str | None
    node_count: int
    edge_count: int
    auto_watch_effective: bool | None
    freshness_assurance: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "provider_version": self.provider_version,
            "provider_project": self.provider_project,
            "index_state": self.index_state,
            "index_commit": self.index_commit,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "auto_watch_effective": self.auto_watch_effective,
            "freshness_assurance": self.freshness_assurance,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class SearchHit:
    qualified_name: str
    path: str
    start_line: int | None = None
    end_line: int | None = None
    score: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "qualified_name": self.qualified_name,
            "path": self.path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "score": self.score,
        }


@dataclass(frozen=True)
class SearchResult:
    items: list[SearchHit] = field(default_factory=list)
    total: int | None = None
    returned: int = 0
    has_more: bool = False
    truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": [item.to_dict() for item in self.items],
            "total": self.total,
            "returned": self.returned,
            "has_more": self.has_more,
            "truncated": self.truncated,
        }


@dataclass(frozen=True)
class TraceNode:
    qualified_name: str
    path: str
    start_line: int | None = None
    end_line: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "qualified_name": self.qualified_name,
            "path": self.path,
            "start_line": self.start_line,
            "end_line": self.end_line,
        }


@dataclass(frozen=True)
class TraceEdge:
    source: str
    target: str
    kind: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"source": self.source, "target": self.target, "kind": self.kind}


@dataclass(frozen=True)
class TraceResult:
    paths: list[list[str]] = field(default_factory=list)
    nodes: list[TraceNode] = field(default_factory=list)
    edges: list[TraceEdge] = field(default_factory=list)
    truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "paths": [list(path) for path in self.paths],
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "truncated": self.truncated,
        }


@dataclass(frozen=True)
class ImpactSymbol:
    qualified_name: str
    path: str
    risk: float | None = None
    hops: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "qualified_name": self.qualified_name,
            "path": self.path,
            "risk": self.risk,
            "hops": self.hops,
        }


@dataclass(frozen=True)
class ImpactResult:
    symbols: list[ImpactSymbol] = field(default_factory=list)
    edges: list[TraceEdge] = field(default_factory=list)
    truncated: bool = False
    mode: str | None = None
    freshness_assurance: str | None = None
    uncertainty: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbols": [symbol.to_dict() for symbol in self.symbols],
            "edges": [edge.to_dict() for edge in self.edges],
            "truncated": self.truncated,
            "mode": self.mode,
            "freshness_assurance": self.freshness_assurance,
            "uncertainty": self.uncertainty,
        }


@dataclass(frozen=True)
class ArchitectureCluster:
    name: str
    representatives: list[TraceNode] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "representatives": [node.to_dict() for node in self.representatives],
        }


@dataclass(frozen=True)
class ArchitectureResult:
    clusters: list[ArchitectureCluster] = field(default_factory=list)
    truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "clusters": [cluster.to_dict() for cluster in self.clusters],
            "truncated": self.truncated,
        }
