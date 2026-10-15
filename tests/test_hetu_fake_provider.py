"""Deterministic FakeHetuProvider contract for later Hetu command tests."""

from __future__ import annotations

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
from vibe_control.hetu.provider import FakeHetuProvider, HetuProvider, ReindexResult


def test_fake_provider_satisfies_protocol():
    provider: HetuProvider = FakeHetuProvider()
    assert provider.name == "fake"


def test_status_search_trace_impact_architecture_reindex_deterministic():
    provider = FakeHetuProvider(
        status=ProviderStatusResult(
            provider="fake",
            provider_version="0.0.1",
            provider_project="demo",
            index_state="ready",
            index_commit="abc123",
            node_count=3,
            edge_count=2,
            auto_watch_effective=False,
            freshness_assurance="strict_receipt",
        ),
        search_hits=[
            SearchHit(qualified_name="pkg.a", path="a.py", start_line=1, end_line=2, score=0.9),
            SearchHit(qualified_name="pkg.b", path="b.py", start_line=3, end_line=4, score=0.5),
            SearchHit(qualified_name="pkg.c", path="c.py", start_line=5, end_line=6, score=0.1),
        ],
        trace=TraceResult(
            paths=[["pkg.a", "pkg.b"]],
            nodes=[
                TraceNode(qualified_name="pkg.a", path="a.py"),
                TraceNode(qualified_name="pkg.b", path="b.py"),
            ],
            edges=[TraceEdge(source="pkg.a", target="pkg.b", kind="calls")],
            truncated=False,
        ),
        impact=ImpactResult(
            symbols=[
                ImpactSymbol(qualified_name="pkg.a", path="a.py", risk=0.8, hops=1),
                ImpactSymbol(qualified_name="pkg.b", path="b.py", risk=0.2, hops=2),
            ],
            edges=[TraceEdge(source="pkg.a", target="pkg.b", kind="calls")],
            truncated=False,
        ),
        architecture=ArchitectureResult(
            clusters=[
                ArchitectureCluster(
                    name="core",
                    representatives=[TraceNode(qualified_name="pkg.a", path="a.py")],
                )
            ],
            truncated=False,
        ),
    )

    status = provider.status()
    assert status.index_state == "ready"
    assert status.provider_project == "demo"
    assert status.node_count == 3

    search = provider.search(query="pkg", limit=2)
    assert isinstance(search, SearchResult)
    assert search.returned == 2
    assert search.total == 3
    assert search.has_more is True
    assert search.truncated is True
    assert [h.qualified_name for h in search.items] == ["pkg.a", "pkg.b"]

    # Second call is identical (deterministic).
    search2 = provider.search(query="pkg", limit=2)
    assert search2.to_dict() == search.to_dict()

    trace = provider.trace(symbol="pkg.a", direction="outbound", depth=3)
    assert trace.paths == [["pkg.a", "pkg.b"]]
    assert len(trace.nodes) == 2

    impact = provider.impact(since=None, depth=2)
    assert [s.qualified_name for s in impact.symbols] == ["pkg.a", "pkg.b"]

    arch = provider.architecture()
    assert arch.clusters[0].name == "core"

    reindex = provider.reindex(mode="fast", persistence=False)
    assert isinstance(reindex, ReindexResult)
    assert reindex.ok is True
    assert reindex.mutation_performed is True
    assert reindex.index_mode == "fast"
    assert reindex.persistence is False
    assert reindex.provider_project == "demo"
    assert reindex.node_count >= 1


def test_fake_provider_records_calls_for_command_tests():
    provider = FakeHetuProvider()
    provider.status()
    provider.search(query="x", limit=5)
    provider.trace(symbol="a.b", direction="both", depth=2)
    provider.impact(since="HEAD~1", depth=1)
    provider.architecture()
    provider.reindex(mode="fast", persistence=False)
    assert [c[0] for c in provider.calls] == [
        "status",
        "search",
        "trace",
        "impact",
        "architecture",
        "reindex",
    ]
    assert provider.calls[1][1]["query"] == "x"
    assert provider.calls[1][1]["limit"] == 5
    assert provider.calls[2][1]["direction"] == "both"
    assert provider.calls[3][1]["since"] == "HEAD~1"


def test_fake_provider_default_status_is_ready_with_graph():
    provider = FakeHetuProvider()
    status = provider.status()
    assert status.provider == "fake"
    assert status.index_state == "ready"
    assert status.auto_watch_effective is False
    assert (status.node_count + status.edge_count) > 0


def test_fake_provider_reindex_updates_status_commit():
    provider = FakeHetuProvider()
    before = provider.status().index_commit
    result = provider.reindex(mode="fast", persistence=False, index_commit="deadbeef")
    assert result.ok is True
    assert result.index_commit == "deadbeef"
    assert provider.status().index_commit == "deadbeef"
    assert provider.status().index_commit != before or before == "deadbeef"


def test_fake_provider_can_simulate_unavailable():
    provider = FakeHetuProvider(
        status=ProviderStatusResult(
            provider="fake",
            provider_version=None,
            provider_project=None,
            index_state="unavailable",
            index_commit=None,
            node_count=0,
            edge_count=0,
            auto_watch_effective=None,
            reason="provider_unavailable",
        )
    )
    assert provider.status().index_state == "unavailable"


def test_fake_provider_rejects_non_fast_reindex_mode():
    provider = FakeHetuProvider()
    result = provider.reindex(mode="semantic", persistence=False)
    assert result.ok is False
    assert result.mutation_performed is False
    assert result.reason == "unsupported_index_mode"
