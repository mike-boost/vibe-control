"""Readonly no-hidden-mutation contract (core control-contract hardening Task 4)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import yaml

from helpers import (
    minimal_config_dict,
    write_actionable_roadmap_state,
    write_control_yaml,
    write_doc,
    write_registry,
)
from vibe_control.closeout_runner import run_closeout
from vibe_control.cli import (
    _build_doctor_envelope,
    cmd_integration_status,
    cmd_knowledge_query,
    cmd_knowledge_status,
)
from vibe_control.describe import build_describe
from vibe_control.gateway import route_gateway
from vibe_control.grill_session import active_path, grill_root
from vibe_control.implementation.prompt import build_implementation_prompt
from vibe_control.knowledge.remote_ops import cmd_knowledge_sync
from vibe_control.progress_brief import build_brief, build_progress
from vibe_control.task.apply_cli import run_task_apply
from vibe_control.task.provider import FakeTaskProvider
from vibe_control.task.reconcile_cli import run_task_reconcile_dry_run


def _assert_readonly(envelope: dict) -> None:
    """Migrated readonly surfaces must expose explicit false mutation evidence."""
    assert envelope.get("mutation_intent") is False
    assert envelope.get("mutation_performed") is False
    assert envelope.get("mutation") is False
    assert envelope.get("effects") == []


def _fail_write(*_args, **_kwargs):
    raise AssertionError("readonly path must not call write helper")


def _install_write_sentinels(monkeypatch) -> None:
    monkeypatch.setattr(
        "vibe_control.grill_session.write_active_pointer", _fail_write
    )
    monkeypatch.setattr(
        "vibe_control.grill_session.clear_dangling_active_pointer", _fail_write
    )
    monkeypatch.setattr(
        "vibe_control.knowledge.pending_sync.write_pending_sync", _fail_write
    )
    monkeypatch.setattr(
        "vibe_control.knowledge.scale_observability.write_last_sync_report",
        _fail_write,
    )
    monkeypatch.setattr(
        "vibe_control.knowledge.remote_ack.write_ack", _fail_write
    )


def _status_fixture(**overrides) -> dict:
    base = {
        "project_id": "readonly-contract",
        "product_ready": True,
        "config_ok": True,
        "provider_sync_required": False,
        "closeout_complete": True,
        "task_cache_current": True,
        "blocked_reasons": [],
        "knowledge_provider": {
            "sync_state": "synced",
            "provider_ask_clean": True,
            "available": True,
            "target_ok": True,
        },
        "capability_profile": {
            "knowledge_enabled": False,
            "task_enabled": False,
        },
        "components": {
            "knowledge": {"enabled": False},
            "task": {"enabled": False},
        },
        "warnings": [],
        "next_actions": [],
    }
    base.update(overrides)
    return base


def _mini_repo(tmp_path: Path, *, enable_knowledge: bool = False, enable_task: bool = False) -> Path:
    (tmp_path / ".git").mkdir()
    write_registry(
        tmp_path,
        [{"id": "only", "status": "active", "path": "docs/a.md", "title": "A"}],
    )
    write_doc(tmp_path, "docs/a.md", "# A\n")
    write_actionable_roadmap_state(tmp_path)
    write_control_yaml(
        tmp_path,
        {
            **minimal_config_dict(
                enable_knowledge=enable_knowledge,
                enable_task=enable_task,
            ),
            "project": {"id": "readonly-contract", "name": "Readonly Contract"},
        },
    )
    return tmp_path


def _local_fts_repo(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    home.mkdir()
    (repo / "docs").mkdir(parents=True)
    (repo / ".config").mkdir(parents=True)
    (repo / "docs" / "spec.md").write_text("# Spec\nbody\n", encoding="utf-8")
    (repo / "docs" / "spec-registry.yml").write_text(
        yaml.safe_dump(
            [{"id": "spec", "status": "active", "path": "docs/spec.md", "title": "Spec"}]
        ),
        encoding="utf-8",
    )
    (repo / ".config" / "vibe-control.yaml").write_text(
        yaml.safe_dump(
            {
                "project": {"id": "local-fts-ro", "name": "local-fts-ro"},
                "components": {
                    "knowledge": {"enabled": True},
                    "task": {"enabled": False},
                },
                "knowledge": {
                    "provider": "local_fts",
                    "fallback_provider": "repo",
                    "max_sources": 20,
                    "warn_sources": 15,
                    "authoritative_statuses": ["active"],
                    "include_from": "docs/spec-registry.yml",
                    "include_extra": [],
                    "exclude_globs": [],
                    "local_fts": {"top_k": 8},
                },
                "specs": {
                    "registry": "docs/spec-registry.yml",
                    "required_fields": ["id", "status", "path"],
                },
                "tasks": {"provider": "fake"},
            }
        ),
        encoding="utf-8",
    )
    return repo, home


def test_doctor_describe_status_query_readonly(tmp_path, monkeypatch):
    root = _mini_repo(tmp_path, enable_knowledge=True)
    monkeypatch.chdir(root)
    _install_write_sentinels(monkeypatch)

    doctor = _build_doctor_envelope(argparse.Namespace(config=None))
    _assert_readonly(doctor)

    progress = build_progress(
        repo_root=root,
        integration_status=_status_fixture(),
        next_selection={"no_actionable_next_task": True, "next_actionable_task": None},
        git_status_short="",
        observed_head="deadbeef",
    )
    describe = build_describe(repo_root=root, progress_envelope=progress)
    _assert_readonly(describe)

    status = cmd_integration_status(argparse.Namespace())
    _assert_readonly(status)

    k_status = cmd_knowledge_status(argparse.Namespace(config=None, notebook=None))
    _assert_readonly(k_status)

    qfile = root / "q.txt"
    qfile.write_text("what is A?", encoding="utf-8")
    query = cmd_knowledge_query(
        argparse.Namespace(config=None, notebook=None, question_file=str(qfile))
    )
    _assert_readonly(query)


def test_ordinary_gateway_brief_status_why_blocked_readonly(tmp_path, monkeypatch):
    root = _mini_repo(tmp_path)
    monkeypatch.chdir(root)
    _install_write_sentinels(monkeypatch)

    delegates = {
        "progress": lambda **_kw: build_progress(
            repo_root=root,
            integration_status=_status_fixture(),
            next_selection={"no_actionable_next_task": True, "next_actionable_task": None},
            git_status_short="",
            observed_head="deadbeef",
        ),
        "brief": lambda **_kw: build_brief(
            repo_root=root,
            integration_status=_status_fixture(),
            next_selection={"no_actionable_next_task": True, "next_actionable_task": None},
            git_status_short="",
            observed_head="deadbeef",
        ),
    }
    for intent in ("status", "brief", "why_blocked"):
        out = route_gateway(intent=intent, repo_root=root, delegates=delegates)
        _assert_readonly(out)
        assert out.get("data", {}).get("intent") != "grill_brief"


def test_implementation_prompt_readonly(tmp_path, monkeypatch):
    root = _mini_repo(tmp_path)
    monkeypatch.chdir(root)
    _install_write_sentinels(monkeypatch)
    env = build_implementation_prompt(
        repo_root=root,
        task_selector="roadmap.phase11b.live_apply",
        product_ready=True,
        readiness_summary={"product_ready": True, "blocked_reasons": []},
        knowledge_readiness={
            "sync_state": "synced",
            "provider_ask_clean": True,
            "available": True,
            "target_ok": True,
        },
    )
    _assert_readonly(env)


def test_closeout_dry_run_readonly(tmp_path, monkeypatch):
    root = _mini_repo(tmp_path)
    monkeypatch.chdir(root)
    apply_calls: list[str] = []

    def apply_sync(_root: Path):
        apply_calls.append("apply")
        raise AssertionError("closeout dry-run must not apply knowledge sync")

    deps = {
        "git_status_short": lambda _root: "",
        "build_integration_status": lambda _root, **_kw: _status_fixture(
            closeout_state="no_ssot_change_product_ready",
            task_provider={
                "available": True,
                "mode": "readonly",
                "readable": True,
                "ready_queue_available": True,
            },
            task_cache={
                "task_cache_current": True,
                "reconcile_counts": {
                    "matched": 1,
                    "missing": 0,
                    "stale": 0,
                    "duplicate": 0,
                    "conflict": 0,
                    "unmanaged": 0,
                },
                "apply_plan_counts": {"create": 0, "update": 0, "skip": 0, "blocked": 0},
            },
            chatgpt_project_sources={
                "product_closeout_gate": False,
                "owner_manual_external_copy": True,
                "advisor_files": [],
            },
        ),
        "plan_sync_dry_run": lambda _root: {
            "ok": True,
            "sync_state": "synced",
            "required_updates_count": 0,
            "operations": [{"op": "already_current", "doc_id": "a"}],
        },
        "apply_knowledge_sync": apply_sync,
        "desired_doc_ids": lambda _root: {"a"},
        "next_actionable_selection": lambda **_kw: {
            "next_actionable_task": None,
            "no_actionable_next_task": True,
        },
    }
    env = run_closeout(repo_root=root, apply=False, deps=deps)
    _assert_readonly(env)
    assert apply_calls == []


def test_knowledge_sync_dry_run_readonly(tmp_path, monkeypatch):
    repo, home = _local_fts_repo(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))

    def boom_sync(self, *args, **kwargs):
        apply = bool(kwargs.get("apply", False))
        if apply:
            raise AssertionError("sync dry-run must not apply local_fts rebuild")
        return {
            "ok": True,
            "provider": "local_fts",
            "dry_run": True,
            "plan": {"ops": [{"op": "rebuild_index"}]},
            "sync_state": "drift",
            "synced": False,
        }

    monkeypatch.setattr(
        "vibe_control.knowledge.local_fts.provider.LocalFtsProvider.sync",
        boom_sync,
    )
    _install_write_sentinels(monkeypatch)
    args = SimpleNamespace(
        config=None,
        notebook=None,
        dry_run=True,
        apply=False,
        continue_partial=False,
        confirm_non_default=False,
    )
    out = cmd_knowledge_sync(repo, args)
    _assert_readonly(out)


def test_task_reconcile_and_apply_dry_run_readonly(tmp_path, monkeypatch):
    root = _mini_repo(tmp_path, enable_task=True)
    monkeypatch.chdir(root)
    _install_write_sentinels(monkeypatch)

    provider = FakeTaskProvider([])

    def boom_create(*_a, **_k):
        raise AssertionError("dry-run must not create tasks")

    def boom_update(*_a, **_k):
        raise AssertionError("dry-run must not update tasks")

    monkeypatch.setattr(provider, "create_managed", boom_create)
    monkeypatch.setattr(provider, "update_managed", boom_update)

    reconcile = run_task_reconcile_dry_run(
        repo_root=root, provider=provider, provider_name="fake"
    )
    _assert_readonly(reconcile)

    apply_env = run_task_apply(
        repo_root=root,
        mode="dry_run",
        provider=provider,
        provider_name="fake",
        skip_knowledge_probe=True,
    )
    _assert_readonly(apply_env)


def test_dangling_self_grill_active_pointer_not_rewritten(tmp_path, monkeypatch):
    root = _mini_repo(tmp_path)
    monkeypatch.chdir(root)
    grill_root(root).mkdir(parents=True, exist_ok=True)
    pointer = active_path(root)
    # Bypass helper so we can still sentinel-patch write_active_pointer later.
    pointer.write_text(
        json.dumps({"grill_id": "grill-missing-session"}, indent=2) + "\n",
        encoding="utf-8",
    )
    before = pointer.read_text(encoding="utf-8")
    assert "grill-missing-session" in before

    writes: list[object] = []

    def track_write(repo_root, grill_id):
        writes.append((repo_root, grill_id))
        raise AssertionError("readonly progress/brief must not rewrite active.json")

    monkeypatch.setattr(
        "vibe_control.grill_session.write_active_pointer", track_write
    )
    monkeypatch.setattr(
        "vibe_control.grill_session.clear_dangling_active_pointer",
        lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("readonly must not clear dangling active pointer")
        ),
    )

    progress = build_progress(
        repo_root=root,
        integration_status=_status_fixture(),
        next_selection={"no_actionable_next_task": True, "next_actionable_task": None},
        git_status_short="",
        observed_head="deadbeef",
    )
    brief = build_brief(
        repo_root=root,
        integration_status=_status_fixture(),
        next_selection={"no_actionable_next_task": True, "next_actionable_task": None},
        git_status_short="",
        observed_head="deadbeef",
    )
    _assert_readonly(progress)
    _assert_readonly(brief)
    assert writes == []
    assert pointer.is_file()
    assert pointer.read_text(encoding="utf-8") == before
