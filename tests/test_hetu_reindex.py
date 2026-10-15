"""Hetu reindex plan + confirmed apply (Task 6) — FakeHetuProvider only."""

from __future__ import annotations

from pathlib import Path

from vibe_control.hetu.binding import compute_repo_realpath_hash
from vibe_control.hetu.commands import (
    EFFECT_HETU_INDEX_BINDING,
    EFFECT_HETU_INDEX_REPOSITORY,
    build_hetu_reindex_apply,
    build_hetu_reindex_dry_run,
    context_from_fake_provider,
)
from vibe_control.hetu.models import ProviderStatusResult
from vibe_control.hetu.provider import FakeHetuProvider
from vibe_control.hetu.receipt import load_index_binding_receipt


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


def _apply_ctx(
    tmp_path: Path,
    *,
    provider: FakeHetuProvider | None = None,
    projects: list[dict] | None = None,
    config_values: dict[str, str] | None = None,
    observed_head: str = "abc123",
    git_dirty: bool = False,
    hetu_enabled: bool = True,
    provider_available: bool = True,
    provider_compatible: bool = True,
    watcher_state_observable: bool = True,
    refresh_git=None,
    write_receipt=None,
    configured_project: str | None = None,
    **kwargs: object,
):
    root = tmp_path / "repo"
    root.mkdir(exist_ok=True)
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    cfg = {"auto_watch": "false"} if config_values is None else config_values
    if projects is None:
        projects = [{"name": "demo", "root_path": str(root), "nodes": 10, "edges": 20}]
    prov = provider or _provider()
    if prov._repo_root is None:
        prov._repo_root = str(root.resolve())
    return context_from_fake_provider(
        repo_root=root,
        project_id="demo-project",
        provider=prov,
        projects=projects,
        config_values=cfg,
        configured_project=configured_project,
        receipt_missing=True,
        observed_head=observed_head,
        git_dirty=git_dirty,
        hetu_enabled=hetu_enabled,
        provider_available=provider_available,
        provider_compatible=provider_compatible,
        watcher_state_observable=watcher_state_observable,
        home=home,
        refresh_git=refresh_git,
        write_receipt=write_receipt,
        **kwargs,  # type: ignore[arg-type]
    ), root, home, cfg


def _plan_binding(ctx) -> str:
    dry = build_hetu_reindex_dry_run(ctx)
    assert dry["ok"] is True
    return dry["data"]["plan"]["plan_binding"]


def _assert_blocked_no_mutation(out: dict, *, code: str | None = None) -> None:
    assert out["ok"] is False
    assert out["mutation_intent"] is True
    assert out["mutation_performed"] is False
    assert out["mutation"] is False
    assert out["effects"] == []
    if code is not None:
        assert out["error"]["code"] == code


def _assert_partial(out: dict, *, code: str) -> None:
    assert out["ok"] is False
    assert out["partial_success"] is True
    assert out["mutation_intent"] is True
    assert out["mutation_performed"] is True
    assert out["mutation"] is True
    assert out["error"]["code"] == code
    assert EFFECT_HETU_INDEX_REPOSITORY in out["effects"]
    assert EFFECT_HETU_INDEX_BINDING not in out["effects"]
    assert out["error"]["details"]["index_state"] == "unverifiable"
    assert out["error"]["details"]["receipt_written"] is False


def test_reindex_apply_success_writes_receipt_and_effects(tmp_path: Path):
    ctx, root, home, _cfg = _apply_ctx(tmp_path)
    binding = _plan_binding(ctx)
    # Clear dry-run list_projects noise; apply must still succeed.
    assert isinstance(ctx.provider, FakeHetuProvider)
    ctx.provider.calls.clear()

    out = build_hetu_reindex_apply(
        ctx,
        expect_plan_binding=binding,
        confirm=True,
    )
    assert out["ok"] is True
    assert out["code"] == "HETU_REINDEX_APPLIED"
    assert out["mutation_intent"] is True
    assert out["mutation_performed"] is True
    assert out["mutation"] is True
    assert out["effects"] == [
        EFFECT_HETU_INDEX_REPOSITORY,
        EFFECT_HETU_INDEX_BINDING,
    ]
    assert out["data"]["receipt"]["written"] is True
    assert out["data"]["index"]["index_state"] == "ready"
    assert out["data"]["index"]["index_commit"] == "abc123"
    assert "reindex" in [c[0] for c in ctx.provider.calls]

    loaded = load_index_binding_receipt(
        "demo-project", provider="codebase_memory", home=home
    )
    assert loaded.ok is True
    assert loaded.receipt is not None
    assert loaded.receipt.index_commit == "abc123"
    assert loaded.receipt.provider_project == "demo"
    assert loaded.receipt.repo_realpath_hash == compute_repo_realpath_hash(root)
    assert loaded.receipt.auto_watch_effective is False
    assert loaded.receipt.persistence is False


def test_reindex_apply_zero_candidate_creates_then_binds(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    provider = _provider(provider_project="created-demo")
    provider._repo_root = str(root.resolve())
    provider.set_projects([])
    ctx = context_from_fake_provider(
        repo_root=root,
        project_id="demo-project",
        provider=provider,
        projects=[],
        config_values={"auto_watch": "false"},
        receipt_missing=True,
        observed_head="abc123",
        git_dirty=False,
        hetu_enabled=True,
        home=home,
    )
    binding = _plan_binding(ctx)
    assert ctx.provider is not None
    out = build_hetu_reindex_apply(ctx, expect_plan_binding=binding, confirm=True)
    assert out["ok"] is True
    assert out["data"]["receipt"]["provider_project"] == "created-demo"
    assert any(
        Path(str(p["root_path"])).resolve() == root.resolve()
        for p in provider.list_projects()
    )


def test_apply_blocked_hetu_disabled(tmp_path: Path):
    ctx, *_ = _apply_ctx(tmp_path, hetu_enabled=False)
    out = build_hetu_reindex_apply(
        ctx, expect_plan_binding="sha256:dead", confirm=True
    )
    _assert_blocked_no_mutation(out, code="HETU_DISABLED")
    assert "reindex" not in [c[0] for c in ctx.provider.calls]  # type: ignore[union-attr]


def test_apply_blocked_confirmation_absent(tmp_path: Path):
    ctx, *_ = _apply_ctx(tmp_path)
    binding = _plan_binding(ctx)
    out = build_hetu_reindex_apply(ctx, expect_plan_binding=binding, confirm=False)
    _assert_blocked_no_mutation(out, code="HETU_REINDEX_CONFIRMATION_REQUIRED")
    assert "reindex" not in [c[0] for c in ctx.provider.calls]  # type: ignore[union-attr]


def test_apply_blocked_dirty_git(tmp_path: Path):
    ctx, *_ = _apply_ctx(tmp_path, git_dirty=True)
    # Dirty dry-run still emits a binding; apply must refuse before mutation.
    dry = build_hetu_reindex_dry_run(ctx)
    assert dry["data"]["apply_ready"] is False
    binding = dry["data"]["plan"]["plan_binding"]
    out = build_hetu_reindex_apply(ctx, expect_plan_binding=binding, confirm=True)
    _assert_blocked_no_mutation(out, code="HETU_REINDEX_GIT_DIRTY")
    assert "reindex" not in [c[0] for c in ctx.provider.calls]  # type: ignore[union-attr]


def test_apply_blocked_stale_plan_hash(tmp_path: Path):
    ctx, *_ = _apply_ctx(tmp_path)
    binding = _plan_binding(ctx)
    ctx.observed_head = "changed-head"
    out = build_hetu_reindex_apply(ctx, expect_plan_binding=binding, confirm=True)
    _assert_blocked_no_mutation(out, code="HETU_REINDEX_PLAN_BINDING_MISMATCH")
    assert "reindex" not in [c[0] for c in ctx.provider.calls]  # type: ignore[union-attr]


def test_apply_blocked_provider_unavailable(tmp_path: Path):
    ctx, *_ = _apply_ctx(tmp_path, provider_available=False)
    out = build_hetu_reindex_apply(
        ctx, expect_plan_binding="sha256:x", confirm=True
    )
    _assert_blocked_no_mutation(out, code="HETU_PROVIDER_UNAVAILABLE")


def test_apply_blocked_provider_incompatible(tmp_path: Path):
    ctx, *_ = _apply_ctx(tmp_path, provider_compatible=False)
    binding = _plan_binding(ctx)
    out = build_hetu_reindex_apply(ctx, expect_plan_binding=binding, confirm=True)
    _assert_blocked_no_mutation(out, code="HETU_PROVIDER_INCOMPATIBLE")
    assert "reindex" not in [c[0] for c in ctx.provider.calls]  # type: ignore[union-attr]


def test_apply_blocked_ambiguous_project(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    projects = [
        {"name": "a", "root_path": str(root), "nodes": 1, "edges": 1},
        {"name": "b", "root_path": str(root), "nodes": 1, "edges": 1},
    ]
    ctx, *_rest = _apply_ctx(tmp_path, projects=projects)
    dry = build_hetu_reindex_dry_run(ctx)
    binding = dry["data"]["plan"]["plan_binding"]
    out = build_hetu_reindex_apply(ctx, expect_plan_binding=binding, confirm=True)
    _assert_blocked_no_mutation(out, code="HETU_BINDING_CONFLICT")
    assert "reindex" not in [c[0] for c in ctx.provider.calls]  # type: ignore[union-attr]


def test_apply_blocked_provider_failure_before_write(tmp_path: Path):
    provider = _provider()
    provider.reindex_fail_reason = "index_repository_failed"
    ctx, *_ = _apply_ctx(tmp_path, provider=provider)
    binding = _plan_binding(ctx)
    out = build_hetu_reindex_apply(ctx, expect_plan_binding=binding, confirm=True)
    _assert_blocked_no_mutation(out, code="HETU_REINDEX_PROVIDER_FAILED")
    assert "reindex" in [c[0] for c in provider.calls]


def test_apply_blocked_watcher_true_before_write(tmp_path: Path):
    cfg = {"auto_watch": "true"}
    ctx, *_ = _apply_ctx(tmp_path, config_values=cfg)
    dry = build_hetu_reindex_dry_run(ctx)
    binding = dry["data"]["plan"]["plan_binding"]
    out = build_hetu_reindex_apply(ctx, expect_plan_binding=binding, confirm=True)
    _assert_blocked_no_mutation(out, code="HETU_WATCHER_NOT_FALSE")
    assert "reindex" not in [c[0] for c in ctx.provider.calls]  # type: ignore[union-attr]


def test_apply_blocked_watcher_unknown_before_write(tmp_path: Path):
    cfg = {"auto_watch": "maybe"}
    ctx, *_ = _apply_ctx(tmp_path, config_values=cfg)
    dry = build_hetu_reindex_dry_run(ctx)
    binding = dry["data"]["plan"]["plan_binding"]
    out = build_hetu_reindex_apply(ctx, expect_plan_binding=binding, confirm=True)
    _assert_blocked_no_mutation(out, code="HETU_WATCHER_NOT_FALSE")
    assert out["error"]["details"]["blocked_reason"] == "auto_watch_unknown"


def test_apply_blocked_watcher_unobservable_before_write(tmp_path: Path):
    ctx, *_ = _apply_ctx(tmp_path, watcher_state_observable=False)
    dry = build_hetu_reindex_dry_run(ctx)
    binding = dry["data"]["plan"]["plan_binding"]
    out = build_hetu_reindex_apply(ctx, expect_plan_binding=binding, confirm=True)
    _assert_blocked_no_mutation(out, code="HETU_PROVIDER_INCOMPATIBLE")
    assert out["error"]["details"]["blocked_reason"] == "watcher_unobservable"
    assert "reindex" not in [c[0] for c in ctx.provider.calls]  # type: ignore[union-attr]


def test_apply_blocked_missing_expect_plan_binding(tmp_path: Path):
    ctx, *_ = _apply_ctx(tmp_path)
    out = build_hetu_reindex_apply(ctx, expect_plan_binding=None, confirm=True)
    _assert_blocked_no_mutation(out, code="HETU_REINDEX_EXPECT_PLAN_BINDING_REQUIRED")


def test_apply_blocked_mismatched_expect_plan_binding(tmp_path: Path):
    ctx, *_ = _apply_ctx(tmp_path)
    _plan_binding(ctx)
    out = build_hetu_reindex_apply(
        ctx, expect_plan_binding="sha256:" + ("0" * 64), confirm=True
    )
    _assert_blocked_no_mutation(out, code="HETU_REINDEX_PLAN_BINDING_MISMATCH")


def test_partial_provider_success_then_git_changes(tmp_path: Path):
    state = {"dirty": False, "head": "abc123"}

    def refresh_git():
        return state["head"], state["dirty"]

    provider = _provider()
    provider.after_reindex = lambda: state.__setitem__("dirty", True)
    ctx, *_ = _apply_ctx(tmp_path, provider=provider, refresh_git=refresh_git)
    binding = _plan_binding(ctx)
    out = build_hetu_reindex_apply(ctx, expect_plan_binding=binding, confirm=True)
    _assert_partial(out, code="HETU_REINDEX_GIT_RACE")


def test_partial_provider_success_then_status_timeout(tmp_path: Path):
    provider = _provider()
    provider.post_reindex_status_timeout = True
    ctx, *_ = _apply_ctx(tmp_path, provider=provider)
    binding = _plan_binding(ctx)
    out = build_hetu_reindex_apply(ctx, expect_plan_binding=binding, confirm=True)
    _assert_partial(out, code="HETU_REINDEX_STATUS_FAILED")
    assert out["error"]["details"]["blocked_reason"] == "post_index_status_timeout"


def test_partial_provider_success_then_empty_graph(tmp_path: Path):
    provider = _provider()
    provider.post_reindex_empty_graph = True
    ctx, *_ = _apply_ctx(tmp_path, provider=provider)
    binding = _plan_binding(ctx)
    out = build_hetu_reindex_apply(ctx, expect_plan_binding=binding, confirm=True)
    _assert_partial(out, code="HETU_REINDEX_STATUS_FAILED")
    assert out["error"]["details"]["blocked_reason"] == "post_index_empty_or_not_ready"


def test_partial_provider_success_then_multiple_candidates(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir(exist_ok=True)
    provider = _provider()

    def after():
        provider._projects.append(
            {
                "name": "demo-dup",
                "root_path": str(root.resolve()),
                "nodes": 1,
                "edges": 1,
            }
        )

    provider.after_reindex = after
    ctx, *_ = _apply_ctx(
        tmp_path,
        provider=provider,
        projects=[{"name": "demo", "root_path": str(root), "nodes": 10, "edges": 20}],
    )
    binding = _plan_binding(ctx)
    out = build_hetu_reindex_apply(ctx, expect_plan_binding=binding, confirm=True)
    _assert_partial(out, code="HETU_REINDEX_POST_BINDING_FAILED")
    assert out["error"]["details"]["blocked_reason"] == "post_index_multiple_candidates"


def test_partial_provider_success_then_watcher_config_mismatch(tmp_path: Path):
    cfg = {"auto_watch": "false"}
    provider = _provider()
    provider.after_reindex = lambda: cfg.__setitem__("auto_watch", "true")
    ctx, *_ = _apply_ctx(tmp_path, provider=provider, config_values=cfg)
    binding = _plan_binding(ctx)
    out = build_hetu_reindex_apply(ctx, expect_plan_binding=binding, confirm=True)
    _assert_partial(out, code="HETU_REINDEX_WATCHER_MISMATCH")


def test_partial_provider_success_then_receipt_write_failure(tmp_path: Path):
    def boom(*_args, **_kwargs):
        raise OSError("disk full")

    ctx, *_ = _apply_ctx(tmp_path, write_receipt=boom)
    binding = _plan_binding(ctx)
    out = build_hetu_reindex_apply(ctx, expect_plan_binding=binding, confirm=True)
    _assert_partial(out, code="HETU_REINDEX_RECEIPT_WRITE_FAILED")


def test_apply_never_requires_product_ready_or_env_dual_gate(tmp_path: Path):
    ctx, *_ = _apply_ctx(tmp_path)
    binding = _plan_binding(ctx)
    # No product_ready field consulted; no VIBE_HETU_* env required.
    out = build_hetu_reindex_apply(ctx, expect_plan_binding=binding, confirm=True)
    assert out["ok"] is True
    assert "product_ready" not in out.get("data", {})
    assert "VIBE_HETU" not in str(out)


def test_cli_reindex_apply_flags_parse():
    from vibe_control.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(
        [
            "hetu",
            "reindex",
            "--apply",
            "--expect-plan-binding",
            "sha256:abc",
            "--confirm-hetu-reindex-apply",
            "--json",
        ]
    )
    assert args.apply is True
    assert args.expect_plan_binding == "sha256:abc"
    assert args.confirm_hetu_reindex_apply is True
    assert callable(getattr(args, "handler", None))
