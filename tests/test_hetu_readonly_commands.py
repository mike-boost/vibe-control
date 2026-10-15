"""Hetu readonly structural commands + reindex dry-run (Task 5) — FakeHetuProvider only."""

from __future__ import annotations

from pathlib import Path

from vibe_control.hetu.binding import compute_repo_realpath_hash
from vibe_control.hetu.commands import (
    ARCH_MAX_CLUSTERS,
    ARCH_MAX_REPS_PER_CLUSTER,
    IMPACT_MAX_EDGES,
    IMPACT_MAX_SYMBOLS,
    SEARCH_LIMIT_MAX,
    TRACE_MAX_EDGES,
    TRACE_MAX_NODES,
    TRACE_MAX_PATHS,
    apply_architecture_caps,
    apply_impact_caps,
    apply_search_caps,
    apply_trace_caps,
    build_hetu_architecture,
    build_hetu_impact,
    build_hetu_reindex_dry_run,
    build_hetu_search,
    build_hetu_trace,
    clamp_int,
    compute_reindex_plan_binding,
    context_from_fake_provider,
    normalize_repo_relative_path,
)
from vibe_control.hetu.models import (
    ArchitectureCluster,
    ArchitectureResult,
    ImpactResult,
    ImpactSymbol,
    IndexBindingReceipt,
    ProviderStatusResult,
    SearchHit,
    SearchResult,
    TraceEdge,
    TraceNode,
    TraceResult,
)
from vibe_control.hetu.provider import FakeHetuProvider
from vibe_control.hetu.receipt import compute_binding_hash


SCHEMA = "vibe.hetu.index_binding.v1"


def _receipt(**overrides: object) -> IndexBindingReceipt:
    base = {
        "schema": SCHEMA,
        "repo_identity": "demo-project",
        "repo_realpath_hash": "sha256:" + ("a" * 64),
        "provider": "codebase_memory",
        "provider_project": "demo",
        "provider_version": "0.9.0",
        "index_mode": "fast",
        "persistence": False,
        "index_commit": "abc123",
        "git_status_short_empty": True,
        "auto_watch_effective": False,
        "node_count": 10,
        "edge_count": 20,
        "bound_at": "2026-07-22T00:00:00+00:00",
    }
    base.update(overrides)
    receipt = IndexBindingReceipt(**base)  # type: ignore[arg-type]
    return receipt.with_binding_hash(compute_binding_hash(receipt))


def _provider(**status_overrides: object) -> FakeHetuProvider:
    base = {
        "provider": "codebase_memory",
        "provider_version": "0.9.0",
        "provider_project": "demo",
        "index_state": "ready",
        "index_commit": "abc123",
        "node_count": 10,
        "edge_count": 20,
        "auto_watch_effective": False,
    }
    base.update(status_overrides)
    return FakeHetuProvider(status=ProviderStatusResult(**base))  # type: ignore[arg-type]


def _ready_ctx(
    tmp_path: Path,
    *,
    provider: FakeHetuProvider | None = None,
    git_dirty: bool = False,
    observed_head: str = "abc123",
    receipt: IndexBindingReceipt | None = None,
    hetu_enabled: bool = True,
    **kwargs: object,
):
    root = tmp_path / "repo"
    root.mkdir(exist_ok=True)
    prov = provider or _provider()
    recv = receipt or _receipt(
        provider_project="demo",
        repo_realpath_hash=compute_repo_realpath_hash(root),
        index_commit=observed_head,
    )
    return context_from_fake_provider(
        repo_root=root,
        project_id="demo-project",
        provider=prov,
        projects=[{"name": "demo", "root_path": str(root), "nodes": 10, "edges": 20}],
        config_values={"auto_watch": "false"},
        receipt=recv,
        receipt_missing=False,
        observed_head=observed_head,
        git_dirty=git_dirty,
        hetu_enabled=hetu_enabled,
        **kwargs,  # type: ignore[arg-type]
    )


def _assert_readonly(envelope: dict) -> None:
    assert envelope["mutation_intent"] is False
    assert envelope["mutation_performed"] is False
    assert envelope["mutation"] is False
    assert envelope["effects"] == []


# --- caps / normalize helpers ---


def test_clamp_and_path_normalize(tmp_path: Path):
    assert clamp_int(None, default=20, lo=1, hi=50) == 20
    assert clamp_int(0, default=20, lo=1, hi=50) == 1
    assert clamp_int(99, default=20, lo=1, hi=50) == 50
    root = tmp_path / "repo"
    root.mkdir()
    abs_path = str(root / "src" / "a.py")
    assert normalize_repo_relative_path(abs_path, root) == "src/a.py"
    assert normalize_repo_relative_path("./src/b.py", root) == "src/b.py"


def test_search_caps_unknown_total_and_truncation(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    hits = [
        SearchHit(qualified_name=f"pkg.s{i:02d}", path=f"/abs/{i}.py", score=1.0 - i * 0.01)
        for i in range(10)
    ]
    raw = SearchResult(items=hits, total=None, returned=10, has_more=False, truncated=False)
    capped = apply_search_caps(raw, repo_root=root, limit=3)
    assert capped.total is None
    assert capped.returned == 3
    assert capped.truncated is True
    assert capped.has_more is True
    assert all(not h.path.startswith("/") for h in capped.items)


def test_trace_impact_architecture_high_degree_caps(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    paths = [[f"n{i}", f"n{i + 1}"] for i in range(TRACE_MAX_PATHS + 5)]
    nodes = [
        TraceNode(qualified_name=f"n{i}", path=f"/x/{i}.py")
        for i in range(TRACE_MAX_NODES + 10)
    ]
    edges = [
        TraceEdge(source=f"n{i}", target=f"n{i + 1}", kind="calls")
        for i in range(TRACE_MAX_EDGES + 7)
    ]
    trace = apply_trace_caps(
        TraceResult(paths=paths, nodes=nodes, edges=edges, truncated=False),
        repo_root=root,
    )
    assert len(trace.paths) == TRACE_MAX_PATHS
    assert len(trace.nodes) == TRACE_MAX_NODES
    assert len(trace.edges) == TRACE_MAX_EDGES
    assert trace.truncated is True

    symbols = [
        ImpactSymbol(qualified_name=f"s{i}", path=f"p{i}.py", risk=i / 200, hops=i % 5)
        for i in range(IMPACT_MAX_SYMBOLS + 20)
    ]
    iedges = [
        TraceEdge(source=f"s{i}", target=f"s{i + 1}") for i in range(IMPACT_MAX_EDGES + 3)
    ]
    impact = apply_impact_caps(
        ImpactResult(symbols=symbols, edges=iedges, truncated=False),
        repo_root=root,
    )
    assert len(impact.symbols) == IMPACT_MAX_SYMBOLS
    assert len(impact.edges) == IMPACT_MAX_EDGES
    assert impact.truncated is True
    # Stable risk-desc ordering before truncation.
    risks = [s.risk for s in impact.symbols]
    assert risks == sorted(risks, reverse=True)

    clusters = [
        ArchitectureCluster(
            name=f"c{i:02d}",
            representatives=[
                TraceNode(qualified_name=f"r{j}", path=f"r{j}.py")
                for j in range(ARCH_MAX_REPS_PER_CLUSTER + 3)
            ],
        )
        for i in range(ARCH_MAX_CLUSTERS + 4)
    ]
    arch = apply_architecture_caps(
        ArchitectureResult(clusters=clusters, truncated=False),
        repo_root=root,
    )
    assert len(arch.clusters) == ARCH_MAX_CLUSTERS
    assert all(len(c.representatives) == ARCH_MAX_REPS_PER_CLUSTER for c in arch.clusters)
    assert arch.truncated is True


# --- search ---


def test_search_ready_empty_and_pagination_hint(tmp_path: Path):
    hits = [
        SearchHit(qualified_name=f"pkg.m{i}", path=f"m{i}.py", score=float(100 - i))
        for i in range(8)
    ]
    provider = FakeHetuProvider(
        status=_provider().status(),
        search_hits=hits,
        uncapped_search=True,
    )
    ctx = _ready_ctx(tmp_path, provider=provider)
    empty = build_hetu_search(ctx, query="zzz-no-match", limit=5)
    _assert_readonly(empty)
    assert empty["ok"] is True
    assert empty["data"]["result"]["returned"] == 0
    assert empty["data"]["result"]["total"] == 0
    assert empty["data"]["result"]["truncated"] is False

    provider2 = FakeHetuProvider(
        status=_provider().status(),
        search_hits=hits,
        uncapped_search=True,
        unknown_search_total=True,
    )
    ctx2 = _ready_ctx(tmp_path, provider=provider2)
    out = build_hetu_search(ctx2, query="pkg", limit=3)
    _assert_readonly(out)
    assert out["ok"] is True
    assert out["data"]["result"]["total"] is None
    assert out["data"]["result"]["returned"] == 3
    assert out["data"]["result"]["truncated"] is True
    assert out["data"]["limit"] == 3
    assert any(a["code"] == "HETU_RESULT_TRUNCATED" for a in out["next_actions"])
    assert out["data"]["limit"] <= SEARCH_LIMIT_MAX


def test_search_invalid_query_and_blocked_states(tmp_path: Path):
    ctx = _ready_ctx(tmp_path)
    bad = build_hetu_search(ctx, query="   ")
    assert bad["ok"] is False
    assert bad["error"]["code"] == "HETU_INVALID_QUERY"
    _assert_readonly(bad)
    assert "search" not in [c[0] for c in ctx.provider.calls]  # type: ignore[union-attr]

    root = tmp_path / "stale"
    root.mkdir()
    provider = _provider()
    ctx_stale = context_from_fake_provider(
        repo_root=root,
        project_id="demo-project",
        provider=provider,
        projects=[{"name": "demo", "root_path": str(root), "nodes": 10, "edges": 20}],
        config_values={"auto_watch": "false"},
        receipt=_receipt(
            provider_project="demo",
            repo_realpath_hash=compute_repo_realpath_hash(root),
            index_commit="oldhead",
        ),
        receipt_missing=False,
        observed_head="abc123",
        git_dirty=False,
    )
    blocked = build_hetu_search(ctx_stale, query="pkg")
    assert blocked["ok"] is False
    assert blocked["error"]["code"] == "HETU_INDEX_STALE"
    _assert_readonly(blocked)
    assert "search" not in [c[0] for c in provider.calls]

    ctx_unv = context_from_fake_provider(
        repo_root=root,
        project_id="demo-project",
        provider=provider,
        projects=[{"name": "demo", "root_path": str(root), "nodes": 10, "edges": 20}],
        config_values={"auto_watch": "false"},
        receipt_missing=True,
    )
    blocked2 = build_hetu_search(ctx_unv, query="pkg")
    assert blocked2["ok"] is False
    assert blocked2["error"]["code"] == "HETU_INDEX_UNVERIFIABLE"
    assert "search" not in [c[0] for c in provider.calls]


def test_search_blocked_when_dirty(tmp_path: Path):
    provider = _provider()
    ctx = _ready_ctx(tmp_path, provider=provider, git_dirty=True)
    out = build_hetu_search(ctx, query="pkg")
    assert out["ok"] is False
    assert out["error"]["code"] == "HETU_INDEX_STALE"
    assert "search" not in [c[0] for c in provider.calls]


# --- trace ---


def test_trace_invalid_symbol_direction_and_caps(tmp_path: Path):
    nodes = [
        TraceNode(qualified_name=f"n{i}", path=f"/abs/n{i}.py")
        for i in range(TRACE_MAX_NODES + 2)
    ]
    edges = [TraceEdge(source=f"n{i}", target=f"n{i + 1}") for i in range(TRACE_MAX_EDGES + 2)]
    paths = [[f"n{i}", f"n{i + 1}"] for i in range(TRACE_MAX_PATHS + 2)]
    provider = FakeHetuProvider(
        status=_provider().status(),
        trace=TraceResult(paths=paths, nodes=nodes, edges=edges, truncated=False),
    )
    ctx = _ready_ctx(tmp_path, provider=provider)
    assert build_hetu_trace(ctx, symbol="", direction="both")["error"]["code"] == (
        "HETU_INVALID_SYMBOL"
    )
    assert build_hetu_trace(ctx, symbol="a.b", direction="sideways")["error"]["code"] == (
        "HETU_INVALID_DIRECTION"
    )
    assert "trace" not in [c[0] for c in provider.calls]

    ok = build_hetu_trace(ctx, symbol="n0", direction="outbound", depth=9)
    _assert_readonly(ok)
    assert ok["ok"] is True
    assert ok["data"]["depth"] == 5  # clamped
    assert len(ok["data"]["result"]["paths"]) == TRACE_MAX_PATHS
    assert len(ok["data"]["result"]["nodes"]) == TRACE_MAX_NODES
    assert len(ok["data"]["result"]["edges"]) == TRACE_MAX_EDGES
    assert ok["data"]["result"]["truncated"] is True
    assert all(
        not n["path"].startswith("/") for n in ok["data"]["result"]["nodes"]
    )


def test_trace_blocked_unverifiable(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    provider = _provider()
    ctx = context_from_fake_provider(
        repo_root=root,
        project_id="demo-project",
        provider=provider,
        projects=[{"name": "demo", "root_path": str(root), "nodes": 1, "edges": 1}],
        config_values={"auto_watch": "false"},
        receipt_missing=True,
    )
    out = build_hetu_trace(ctx, symbol="a.b")
    assert out["ok"] is False
    assert out["error"]["code"] == "HETU_INDEX_UNVERIFIABLE"
    assert "trace" not in [c[0] for c in provider.calls]


# --- impact ---


def test_impact_ready_and_high_degree(tmp_path: Path):
    symbols = [
        ImpactSymbol(qualified_name=f"s{i}", path=f"/r/s{i}.py", risk=1.0 - i * 0.001, hops=i)
        for i in range(IMPACT_MAX_SYMBOLS + 5)
    ]
    edges = [
        TraceEdge(source=f"s{i}", target=f"s{i + 1}") for i in range(IMPACT_MAX_EDGES + 5)
    ]
    provider = FakeHetuProvider(
        status=_provider().status(),
        impact=ImpactResult(symbols=symbols, edges=edges, truncated=False),
    )
    ctx = _ready_ctx(tmp_path, provider=provider)
    out = build_hetu_impact(ctx, depth=2)
    _assert_readonly(out)
    assert out["ok"] is True
    assert out["code"] == "HETU_IMPACT_OK"
    assert len(out["data"]["result"]["symbols"]) == IMPACT_MAX_SYMBOLS
    assert len(out["data"]["result"]["edges"]) == IMPACT_MAX_EDGES
    assert out["data"]["result"]["truncated"] is True
    assert any(a["code"] == "HETU_RESULT_TRUNCATED" for a in out["next_actions"])


def test_dirty_only_degraded_impact_allowed(tmp_path: Path):
    provider = _provider()
    ctx = _ready_ctx(tmp_path, provider=provider, git_dirty=True)
    # search/trace/architecture blocked
    assert build_hetu_search(ctx, query="x")["ok"] is False
    assert build_hetu_trace(ctx, symbol="a.b")["ok"] is False
    assert build_hetu_architecture(ctx)["ok"] is False
    assert "search" not in [c[0] for c in provider.calls]
    assert "trace" not in [c[0] for c in provider.calls]
    assert "architecture" not in [c[0] for c in provider.calls]

    out = build_hetu_impact(ctx)
    _assert_readonly(out)
    assert out["ok"] is True
    assert out["code"] == "HETU_IMPACT_DEGRADED"
    assert out["data"]["index"]["index_state"] == "stale"
    assert out["data"]["index"]["freshness_assurance"] == "clean_baseline_plus_worktree_diff"
    assert out["data"]["result"]["mode"] == "degraded"
    assert "impact" in [c[0] for c in provider.calls]


def test_dirty_impact_blocked_with_since_or_head_mismatch(tmp_path: Path):
    provider = _provider()
    ctx = _ready_ctx(tmp_path, provider=provider, git_dirty=True)
    blocked_since = build_hetu_impact(ctx, since="HEAD~1")
    assert blocked_since["ok"] is False
    assert "impact" not in [c[0] for c in provider.calls]

    root = tmp_path / "headmis"
    root.mkdir()
    provider2 = _provider()
    ctx2 = context_from_fake_provider(
        repo_root=root,
        project_id="demo-project",
        provider=provider2,
        projects=[{"name": "demo", "root_path": str(root), "nodes": 10, "edges": 20}],
        config_values={"auto_watch": "false"},
        receipt=_receipt(
            provider_project="demo",
            repo_realpath_hash=compute_repo_realpath_hash(root),
            index_commit="old",
        ),
        receipt_missing=False,
        observed_head="new",
        git_dirty=True,
    )
    blocked_head = build_hetu_impact(ctx2)
    assert blocked_head["ok"] is False
    assert blocked_head["error"]["code"] == "HETU_INDEX_STALE"
    assert "impact" not in [c[0] for c in provider2.calls]


def test_impact_blocked_unverifiable(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    provider = _provider()
    ctx = context_from_fake_provider(
        repo_root=root,
        project_id="demo-project",
        provider=provider,
        projects=[{"name": "demo", "root_path": str(root), "nodes": 10, "edges": 20}],
        config_values={"auto_watch": "false"},
        receipt_missing=True,
        git_dirty=True,
    )
    out = build_hetu_impact(ctx)
    assert out["ok"] is False
    assert out["error"]["code"] == "HETU_INDEX_UNVERIFIABLE"
    assert "impact" not in [c[0] for c in provider.calls]


# --- architecture ---


def test_architecture_ready_and_empty(tmp_path: Path):
    provider = FakeHetuProvider(
        status=_provider().status(),
        architecture=ArchitectureResult(clusters=[], truncated=False),
    )
    ctx = _ready_ctx(tmp_path, provider=provider)
    out = build_hetu_architecture(ctx)
    _assert_readonly(out)
    assert out["ok"] is True
    assert out["data"]["result"]["clusters"] == []
    assert out["data"]["result"]["truncated"] is False


# --- reindex dry-run / apply stub ---


def test_reindex_dry_run_emits_plan_binding_no_mutation(tmp_path: Path):
    provider = _provider()
    ctx = _ready_ctx(tmp_path, provider=provider, hetu_enabled=True)
    out = build_hetu_reindex_dry_run(ctx)
    _assert_readonly(out)
    assert out["ok"] is True
    assert out["code"] == "HETU_REINDEX_DRY_RUN"
    plan = out["data"]["plan"]
    assert plan["plan_binding"].startswith("sha256:")
    assert plan["index_mode"] == "fast"
    assert plan["persistence"] is False
    assert plan["observed_head"] == "abc123"
    assert compute_reindex_plan_binding(
        {k: v for k, v in plan.items() if k not in {"plan_binding", "expect_plan_binding_flag", "confirm_flag"}}
    ) == plan["plan_binding"]
    assert "reindex" not in [c[0] for c in provider.calls]
    assert out["data"]["apply_ready"] is True


def test_reindex_dry_run_blocks_dirty_and_watcher(tmp_path: Path):
    ctx = _ready_ctx(tmp_path, git_dirty=True)
    out = build_hetu_reindex_dry_run(ctx)
    _assert_readonly(out)
    assert out["data"]["apply_ready"] is False
    assert "git_dirty" in out["data"]["blocked_reasons"]

    root = tmp_path / "watch"
    root.mkdir()
    provider = _provider()
    ctx2 = context_from_fake_provider(
        repo_root=root,
        project_id="demo-project",
        provider=provider,
        projects=[{"name": "demo", "root_path": str(root), "nodes": 10, "edges": 20}],
        config_values={"auto_watch": "true"},
        receipt=_receipt(
            provider_project="demo",
            repo_realpath_hash=compute_repo_realpath_hash(root),
        ),
        receipt_missing=False,
        observed_head="abc123",
        git_dirty=False,
        hetu_enabled=True,
    )
    out2 = build_hetu_reindex_dry_run(ctx2)
    assert "auto_watch_not_false" in out2["data"]["blocked_reasons"]
    assert "reindex" not in [c[0] for c in provider.calls]


def test_cli_hetu_surface_parses():
    from vibe_control.cli import build_parser

    parser = build_parser()
    for argv in (
        ["hetu", "status", "--json"],
        ["hetu", "doctor", "--json"],
        ["hetu", "search", "--query", "foo", "--json"],
        ["hetu", "trace", "--symbol", "a.b", "--direction", "inbound", "--json"],
        ["hetu", "impact", "--json"],
        ["hetu", "architecture", "--json"],
        ["hetu", "reindex", "--dry-run", "--json"],
        [
            "hetu",
            "reindex",
            "--apply",
            "--expect-plan-binding",
            "sha256:abc",
            "--confirm-hetu-reindex-apply",
            "--json",
        ],
    ):
        args = parser.parse_args(argv)
        assert callable(getattr(args, "handler", None))
