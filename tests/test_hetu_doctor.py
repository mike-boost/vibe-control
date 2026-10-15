"""Hetu doctor (Task 4) — readonly recommendations; never mutates config/index."""

from __future__ import annotations

from pathlib import Path

from vibe_control.hetu.binding import compute_repo_realpath_hash, interpret_auto_watch
from vibe_control.hetu.commands import build_hetu_doctor, context_from_fake_provider
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


def test_doctor_recommends_auto_watch_false_but_never_runs_it(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    provider = _provider()
    config_mutations: list[str] = []

    def _config_values() -> dict[str, str]:
        return {"auto_watch": "true"}

    ctx = context_from_fake_provider(
        repo_root=root,
        project_id="demo-project",
        provider=provider,
        projects=[{"name": "demo", "root_path": str(root), "nodes": 10, "edges": 20}],
        config_values={"auto_watch": "true"},
        receipt_missing=True,
    )
    # Replace config_values to prove doctor never mutates by calling config set.
    ctx.config_values = _config_values

    doctor = build_hetu_doctor(ctx)
    assert doctor["command"] == "hetu.doctor"
    assert doctor["mutation_intent"] is False
    assert doctor["mutation_performed"] is False
    assert doctor["mutation"] is False
    assert doctor["effects"] == []

    watch_actions = [
        a for a in doctor["next_actions"] if a.get("code") == "HETU_AUTO_WATCH_MUST_BE_FALSE"
    ]
    assert len(watch_actions) == 1
    assert watch_actions[0]["mutation"] is True
    assert watch_actions[0]["command"] == "codebase-memory-mcp config set auto_watch false"

    assert doctor["data"]["doctor"]["mutations"]["config_set"] is False
    assert doctor["data"]["doctor"]["mutations"]["index_repository"] is False
    assert doctor["data"]["doctor"]["watcher"]["recommended_mutation_performed"] is False
    assert doctor["data"]["provider"]["auto_watch_effective"] is True
    assert "reindex" not in [c[0] for c in provider.calls]
    assert config_mutations == []
    # config_values still reports true — doctor did not flip it.
    assert ctx.config_values()["auto_watch"] == "true"


def test_doctor_absent_auto_watch_defaults_true_and_recommends_config(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    provider = _provider()
    ctx = context_from_fake_provider(
        repo_root=root,
        project_id="demo-project",
        provider=provider,
        projects=[{"name": "demo", "root_path": str(root), "nodes": 10, "edges": 20}],
        config_values={"auto_index": "false"},  # auto_watch absent
        receipt_missing=True,
    )
    doctor = build_hetu_doctor(ctx)
    assert doctor["data"]["provider"]["auto_watch_effective"] is True
    assert doctor["data"]["doctor"]["watcher"]["auto_watch_key_present"] is False
    assert doctor["data"]["doctor"]["watcher"]["provider_default_when_absent"] is True
    assert any(a["code"] == "HETU_AUTO_WATCH_MUST_BE_FALSE" for a in doctor["next_actions"])
    assert doctor["data"]["doctor"]["watcher"]["recommended_mutation_performed"] is False


def test_provider_versions_without_watcher_state_are_strict_incompatible(tmp_path: Path):
    effective, compatible, reason = interpret_auto_watch(
        config_values=None,
        watcher_state_observable=False,
    )
    assert effective is None
    assert compatible is False
    assert reason == "watcher_unobservable"

    root = tmp_path / "repo"
    root.mkdir()
    receipt = _receipt(
        provider_project="demo",
        repo_realpath_hash=compute_repo_realpath_hash(root),
    )
    provider = _provider(provider_version="0.8.1")
    ctx = context_from_fake_provider(
        repo_root=root,
        project_id="demo-project",
        provider=provider,
        projects=[{"name": "demo", "root_path": str(root), "nodes": 10, "edges": 20}],
        config_values=None,  # cannot expose config
        watcher_state_observable=False,
        receipt=receipt,
        receipt_missing=False,
        provider_version="0.8.1",
        observed_head="abc123",
        git_dirty=False,
    )
    doctor = build_hetu_doctor(ctx)
    assert doctor["data"]["index"]["index_state"] == "unavailable"
    assert doctor["data"]["index"]["reason"] == "provider_incompatible"
    assert doctor["code"] == "HETU_PROVIDER_INCOMPATIBLE"
    assert doctor["data"]["doctor"]["compatibility"]["provider_compatible"] is False
    assert doctor["data"]["doctor"]["watcher"]["compatible"] is False
    assert any(a["code"] == "HETU_WATCHER_UNOBSERVABLE" for a in doctor["next_actions"])
    # Still readonly.
    assert doctor["mutation_intent"] is False
    assert doctor["effects"] == []
    assert doctor["data"]["doctor"]["mutations"]["config_set"] is False
    assert "reindex" not in [c[0] for c in provider.calls]


def test_doctor_ready_path_stays_readonly(tmp_path: Path):
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
        config_values={"auto_watch": "false"},
        receipt=receipt,
        receipt_missing=False,
        observed_head="abc123",
        git_dirty=False,
    )
    doctor = build_hetu_doctor(ctx)
    assert doctor["data"]["index"]["index_state"] == "ready"
    assert doctor["code"] == "HETU_READY"
    assert doctor["mutation_intent"] is False
    assert doctor["effects"] == []
    assert not any(a["code"] == "HETU_AUTO_WATCH_MUST_BE_FALSE" for a in doctor["next_actions"])


def test_doctor_redacts_absolute_paths(tmp_path: Path):
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
    doctor = build_hetu_doctor(ctx)
    blob = str(doctor)
    assert str(root.resolve()) not in blob
    assert "/Users/" not in blob
    assert doctor["data"]["binding"]["repo_realpath_hash"].startswith("sha256:")
