"""Hetu provider protocol and deterministic FakeHetuProvider (no real binary)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Literal, Protocol

from vibe_control.hetu.models import (
    ArchitectureCluster,
    ArchitectureResult,
    ImpactResult,
    ImpactSymbol,
    ProviderStatusResult,
    SearchHit,
    SearchResult,
    TraceEdge,
    TraceNode,
    TraceResult,
)

TraceDirection = Literal["inbound", "outbound", "both"]
AfterReindexHook = Callable[[], None]


@dataclass(frozen=True)
class ReindexResult:
    """Normalized reindex outcome for fake/real adapters."""

    ok: bool
    mutation_performed: bool
    provider_project: str | None = None
    provider_version: str | None = None
    index_commit: str | None = None
    index_mode: str = "fast"
    persistence: bool = False
    node_count: int = 0
    edge_count: int = 0
    reason: str | None = None
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "mutation_performed": self.mutation_performed,
            "provider_project": self.provider_project,
            "provider_version": self.provider_version,
            "index_commit": self.index_commit,
            "index_mode": self.index_mode,
            "persistence": self.persistence,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "reason": self.reason,
            "message": self.message,
        }


class HetuProvider(Protocol):
    """Structural provider behind the Hetu capability."""

    name: str

    def status(self) -> ProviderStatusResult:
        ...

    def search(self, *, query: str, limit: int = 20) -> SearchResult:
        ...

    def trace(
        self,
        *,
        symbol: str,
        direction: TraceDirection = "both",
        depth: int = 3,
    ) -> TraceResult:
        ...

    def impact(self, *, since: str | None = None, depth: int = 2) -> ImpactResult:
        ...

    def architecture(self) -> ArchitectureResult:
        ...

    def reindex(
        self,
        *,
        mode: str = "fast",
        persistence: bool = False,
        index_commit: str | None = None,
    ) -> ReindexResult:
        ...


def _default_status() -> ProviderStatusResult:
    return ProviderStatusResult(
        provider="fake",
        provider_version="0.0.1-fake",
        provider_project="fake-project",
        index_state="ready",
        index_commit="fakehead0001",
        node_count=2,
        edge_count=1,
        auto_watch_effective=False,
        freshness_assurance="strict_receipt",
    )


def _default_search_hits() -> list[SearchHit]:
    return [
        SearchHit(
            qualified_name="fake.mod.alpha",
            path="src/fake/alpha.py",
            start_line=1,
            end_line=10,
            score=1.0,
        ),
        SearchHit(
            qualified_name="fake.mod.beta",
            path="src/fake/beta.py",
            start_line=11,
            end_line=20,
            score=0.5,
        ),
    ]


def _default_trace() -> TraceResult:
    return TraceResult(
        paths=[["fake.mod.alpha", "fake.mod.beta"]],
        nodes=[
            TraceNode(qualified_name="fake.mod.alpha", path="src/fake/alpha.py", start_line=1),
            TraceNode(qualified_name="fake.mod.beta", path="src/fake/beta.py", start_line=11),
        ],
        edges=[TraceEdge(source="fake.mod.alpha", target="fake.mod.beta", kind="calls")],
        truncated=False,
    )


def _default_impact() -> ImpactResult:
    return ImpactResult(
        symbols=[
            ImpactSymbol(
                qualified_name="fake.mod.alpha",
                path="src/fake/alpha.py",
                risk=0.9,
                hops=1,
            ),
            ImpactSymbol(
                qualified_name="fake.mod.beta",
                path="src/fake/beta.py",
                risk=0.4,
                hops=2,
            ),
        ],
        edges=[TraceEdge(source="fake.mod.alpha", target="fake.mod.beta", kind="calls")],
        truncated=False,
    )


def _default_architecture() -> ArchitectureResult:
    return ArchitectureResult(
        clusters=[
            ArchitectureCluster(
                name="fake-core",
                representatives=[
                    TraceNode(qualified_name="fake.mod.alpha", path="src/fake/alpha.py"),
                ],
            )
        ],
        truncated=False,
    )


class FakeHetuProvider:
    """In-memory Hetu provider for unit/command tests. No real binary required."""

    name = "fake"

    def __init__(
        self,
        *,
        status: ProviderStatusResult | None = None,
        search_hits: list[SearchHit] | None = None,
        trace: TraceResult | None = None,
        impact: ImpactResult | None = None,
        architecture: ArchitectureResult | None = None,
        unknown_search_total: bool = False,
        uncapped_search: bool = False,
        projects: list[dict[str, Any]] | None = None,
        repo_root: Path | str | None = None,
        reindex_fail_reason: str | None = None,
        reindex_fail_message: str | None = None,
        post_reindex_empty_graph: bool = False,
        post_reindex_status_timeout: bool = False,
        after_reindex: AfterReindexHook | None = None,
    ) -> None:
        self._status = status if status is not None else _default_status()
        self._search_hits = list(search_hits if search_hits is not None else _default_search_hits())
        self._trace = trace if trace is not None else _default_trace()
        self._impact = impact if impact is not None else _default_impact()
        self._architecture = architecture if architecture is not None else _default_architecture()
        self._unknown_search_total = bool(unknown_search_total)
        self._uncapped_search = bool(uncapped_search)
        self._projects: list[dict[str, Any]] = list(projects or [])
        self._repo_root = str(Path(repo_root).resolve()) if repo_root is not None else None
        self.reindex_fail_reason = reindex_fail_reason
        self.reindex_fail_message = reindex_fail_message
        self.post_reindex_empty_graph = bool(post_reindex_empty_graph)
        self.post_reindex_status_timeout = bool(post_reindex_status_timeout)
        self.after_reindex = after_reindex
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._reindex_succeeded = False

    def list_projects(self) -> list[dict[str, Any]]:
        self.calls.append(("list_projects", {}))
        return [dict(row) for row in self._projects]

    def set_projects(self, projects: list[dict[str, Any]]) -> None:
        self._projects = [dict(row) for row in projects]

    def status(self) -> ProviderStatusResult:
        self.calls.append(("status", {}))
        if self._reindex_succeeded and self.post_reindex_status_timeout:
            raise TimeoutError("FakeHetuProvider simulated status timeout after reindex")
        return self._status

    def search(self, *, query: str, limit: int = 20) -> SearchResult:
        self.calls.append(("search", {"query": query, "limit": limit}))
        # Deterministic filter: empty query matches all; otherwise substring match.
        q = str(query or "").strip().lower()
        if q:
            matched = [
                hit
                for hit in self._search_hits
                if q in hit.qualified_name.lower() or q in hit.path.lower()
            ]
        else:
            matched = list(self._search_hits)
        # uncapped_search: return full match set so command-layer caps can be tested.
        if self._uncapped_search:
            items = list(matched)
            truncated = False
            has_more = False
        else:
            capped = max(0, int(limit))
            items = matched[:capped]
            truncated = len(matched) > len(items)
            has_more = truncated
        total: int | None = None if self._unknown_search_total else len(matched)
        return SearchResult(
            items=items,
            total=total,
            returned=len(items),
            has_more=has_more,
            truncated=truncated,
        )

    def trace(
        self,
        *,
        symbol: str,
        direction: TraceDirection = "both",
        depth: int = 3,
    ) -> TraceResult:
        self.calls.append(
            ("trace", {"symbol": symbol, "direction": direction, "depth": depth})
        )
        return self._trace

    def impact(self, *, since: str | None = None, depth: int = 2) -> ImpactResult:
        self.calls.append(("impact", {"since": since, "depth": depth}))
        return self._impact

    def architecture(self) -> ArchitectureResult:
        self.calls.append(("architecture", {}))
        return self._architecture

    def reindex(
        self,
        *,
        mode: str = "fast",
        persistence: bool = False,
        index_commit: str | None = None,
    ) -> ReindexResult:
        self.calls.append(
            (
                "reindex",
                {
                    "mode": mode,
                    "persistence": persistence,
                    "index_commit": index_commit,
                },
            )
        )
        if str(mode).strip().lower() != "fast":
            return ReindexResult(
                ok=False,
                mutation_performed=False,
                index_mode=str(mode),
                persistence=bool(persistence),
                reason="unsupported_index_mode",
                message="FakeHetuProvider only supports mode=fast in MVP",
            )
        if persistence:
            return ReindexResult(
                ok=False,
                mutation_performed=False,
                index_mode="fast",
                persistence=True,
                reason="unsupported_persistence",
                message="FakeHetuProvider only supports persistence=false in MVP",
            )
        if self.reindex_fail_reason:
            return ReindexResult(
                ok=False,
                mutation_performed=False,
                index_mode="fast",
                persistence=False,
                reason=str(self.reindex_fail_reason),
                message=self.reindex_fail_message
                or f"FakeHetuProvider reindex failed: {self.reindex_fail_reason}",
            )

        new_commit = index_commit or "fakehead-reindexed"
        project_name = self._status.provider_project or "fake-project"
        if self._repo_root is not None:
            matching = [
                row
                for row in self._projects
                if str(row.get("root_path") or "").strip()
                and Path(str(row["root_path"])).resolve() == Path(self._repo_root).resolve()
            ]
            if not matching:
                self._projects.append(
                    {
                        "name": project_name,
                        "root_path": self._repo_root,
                        "nodes": max(1, self._status.node_count),
                        "edges": max(1, self._status.edge_count),
                    }
                )
            elif self._status.provider_project is None:
                project_name = str(matching[0].get("name") or project_name)

        node_count = max(1, self._status.node_count)
        edge_count = max(1, self._status.edge_count)
        if self.post_reindex_empty_graph:
            node_count = 0
            edge_count = 0

        self._status = replace(
            self._status,
            provider_project=project_name,
            index_state="ready",
            index_commit=new_commit,
            node_count=node_count,
            edge_count=edge_count,
            reason=None,
        )
        self._reindex_succeeded = True
        if self.after_reindex is not None:
            self.after_reindex()
        return ReindexResult(
            ok=True,
            mutation_performed=True,
            provider_project=self._status.provider_project,
            provider_version=self._status.provider_version,
            index_commit=new_commit,
            index_mode="fast",
            persistence=False,
            node_count=self._status.node_count,
            edge_count=self._status.edge_count,
        )
