"""Hetu project binding + status (Task 4) — FakeHetuProvider / injected deps only."""

from __future__ import annotations

from pathlib import Path

from vibe_control.hetu.binding import (
    canonicalize_repo_root,
    compute_repo_realpath_hash,
    detect_codebase_memory_artifact,
    interpret_auto_watch,
    resolve_project_binding,
)
from vibe_control.hetu.commands import build_hetu_status, context_from_fake_provider
from vibe_control.hetu.models import IndexBindingReceipt, ProviderStatusResult
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


def test_canonicalize_and_hash_are_stable(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    canonical = canonicalize_repo_root(root)
    assert canonical == root.resolve()
    digest = compute_repo_realpath_hash(root)
    assert digest.startswith("sha256:")
    assert digest == compute_repo_realpath_hash(canonical)


def test_zero_candidates_missing(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    binding = resolve_project_binding(
        repo_root=root,
        projects=[{"name": "other", "root_path": str(tmp_path / "elsewhere"), "nodes": 1, "edges": 1}],
    )
    assert binding.selected_project is None
    assert binding.binding_conflict is False
    assert binding.reason == "provider_project_missing"


def test_one_exact_candidate_selected(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    binding = resolve_project_binding(
        repo_root=root,
        projects=[
            {"name": "demo", "root_path": str(root), "nodes": 5, "edges": 7},
            {"name": "other", "root_path": str(tmp_path / "other"), "nodes": 1, "edges": 1},
        ],
    )
    assert binding.selected_project == "demo"
    assert binding.binding_conflict is False
    assert len(binding.matching_candidates) == 1


def test_multiple_candidates_conflict(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    binding = resolve_project_binding(
        repo_root=root,
        projects=[
            {"name": "a", "root_path": str(root), "nodes": 1, "edges": 1},
            {"name": "b", "root_path": str(root), "nodes": 2, "edges": 2},
        ],
    )
    assert binding.selected_project is None
    assert binding.binding_conflict is True
    assert binding.reason == "multiple_root_matches"


def test_configured_project_validates_root(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    mismatch = resolve_project_binding(
        repo_root=root,
        projects=[{"name": "demo", "root_path": str(other), "nodes": 1, "edges": 1}],
        configured_project="demo",
    )
    assert mismatch.binding_conflict is True
    assert mismatch.reason == "configured_project_root_mismatch"

    missing = resolve_project_binding(
        repo_root=root,
        projects=[{"name": "demo", "root_path": str(root), "nodes": 1, "edges": 1}],
        configured_project="nope",
    )
    assert missing.binding_conflict is True
    assert missing.reason == "configured_project_not_found"

    ok = resolve_project_binding(
        repo_root=root,
        projects=[
            {"name": "a", "root_path": str(root), "nodes": 1, "edges": 1},
            {"name": "b", "root_path": str(root), "nodes": 2, "edges": 2},
        ],
        configured_project="b",
    )
    assert ok.binding_conflict is False
    assert ok.selected_project == "b"


def test_artifact_alone_does_not_become_ready(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    artifact_dir = root / ".codebase-memory"
    artifact_dir.mkdir()
    (artifact_dir / "graph.db.zst").write_bytes(b"fake")

    art = detect_codebase_memory_artifact(root)
    assert art.present is True
    assert art.relative_path == ".codebase-memory/graph.db.zst"

    provider = _provider()
    ctx = context_from_fake_provider(
        repo_root=root,
        project_id="demo-project",
        provider=provider,
        projects=[],  # no list_projects match
        config_values={"auto_watch": "false"},
        receipt_missing=True,
        artifact=art,
    )
    status = build_hetu_status(ctx)
    assert status["mutation_intent"] is False
    assert status["mutation_performed"] is False
    assert status["effects"] == []
    assert status["data"]["index"]["index_state"] == "missing"
    assert status["data"]["binding"]["artifact"]["present"] is True
    assert status["data"]["binding"]["artifact"]["binding"] is False
    assert status["data"]["index"]["index_state"] != "ready"
    assert "reindex" not in [c[0] for c in provider.calls]


def test_exact_project_without_receipt_unverifiable(tmp_path: Path):
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
        observed_head="abc123",
        git_dirty=False,
    )
    status = build_hetu_status(ctx)
    assert status["data"]["index"]["index_state"] == "unverifiable"
    assert status["data"]["index"]["reason"] == "receipt_missing"
    assert status["data"]["binding"]["selected_project"] == "demo"
    assert status["code"] == "HETU_INDEX_UNVERIFIABLE"
    assert status["mutation_intent"] is False
    assert status["effects"] == []
    assert any(a["code"] == "HETU_INDEX_UNVERIFIABLE" for a in status["next_actions"])


def test_multiple_candidates_status_conflict(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    provider = _provider()
    ctx = context_from_fake_provider(
        repo_root=root,
        project_id="demo-project",
        provider=provider,
        projects=[
            {"name": "a", "root_path": str(root), "nodes": 1, "edges": 1},
            {"name": "b", "root_path": str(root), "nodes": 2, "edges": 2},
        ],
        config_values={"auto_watch": "false"},
    )
    status = build_hetu_status(ctx)
    assert status["data"]["index"]["index_state"] == "conflict_needs_choice"
    assert status["code"] == "HETU_BINDING_CONFLICT"
    assert any(a["code"] == "HETU_BINDING_CONFLICT" for a in status["next_actions"])
    # Public binding never leaks absolute paths.
    payload = str(status["data"]["binding"])
    assert str(root) not in payload
    assert "/Users/" not in payload


def test_absent_auto_watch_interpreted_as_provider_default_true(tmp_path: Path):
    effective, compatible, reason = interpret_auto_watch(
        config_values={"auto_index": "false"},
        watcher_state_observable=True,
    )
    assert effective is True
    assert compatible is True
    assert reason is None

    root = tmp_path / "repo"
    root.mkdir()
    receipt = _receipt(
        provider_project="demo",
        repo_realpath_hash=compute_repo_realpath_hash(root),
    )
    provider = _provider()
    ctx = context_from_fake_provider(
        repo_root=root,
        project_id="demo-project",
        provider=provider,
        projects=[{"name": "demo", "root_path": str(root), "nodes": 10, "edges": 20}],
        config_values={"auto_index": "false"},  # auto_watch absent → default true
        receipt=receipt,
        receipt_missing=False,
        observed_head="abc123",
        git_dirty=False,
    )
    status = build_hetu_status(ctx)
    assert status["data"]["provider"]["auto_watch_effective"] is True
    assert status["data"]["index"]["index_state"] == "unverifiable"
    assert status["data"]["index"]["reason"] == "external_index_mutation_possible"


def test_ready_status_with_valid_receipt(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    receipt = _receipt(
        provider_project="demo",
        repo_realpath_hash=compute_repo_realpath_hash(root),
        auto_watch_effective=False,
    )
    provider = _provider()
    ctx = context_from_fake_provider(
        repo_root=root,
        project_id="demo-project",
        provider=provider,
        projects=[{"name": "demo", "root_path": str(root), "nodes": 10, "edges": 20}],
        config_values={"auto_watch": "false"},
        receipt=receipt,
        receipt_missing=False,
        observed_head="abc123",
        git_dirty=False,
    )
    status = build_hetu_status(ctx)
    assert status["ok"] is True
    assert status["data"]["index"]["index_state"] == "ready"
    assert status["data"]["index"]["freshness_assurance"] == "strict_receipt"
    assert status["mutation_intent"] is False
    assert status["mutation"] is False
    assert status["effects"] == []
    assert "reindex" not in [c[0] for c in provider.calls]


def test_status_never_calls_index_repository(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    provider = _provider()
    ctx = context_from_fake_provider(
        repo_root=root,
        project_id="demo-project",
        provider=provider,
        projects=[{"name": "demo", "root_path": str(root), "nodes": 1, "edges": 1}],
        config_values={"auto_watch": "false"},
    )
    build_hetu_status(ctx)
    assert all(c[0] != "reindex" for c in provider.calls)
    assert ctx.mutation_calls == []
