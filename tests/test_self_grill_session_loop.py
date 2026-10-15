"""Self-grill session loop: open → pull-back → prompt gate → close."""

from __future__ import annotations

import json
from pathlib import Path

from vibe_control.cli import main
from vibe_control.grill_session import (
    active_in_progress,
    close_session,
    open_session,
    read_active_pointer,
)
from vibe_control.implementation.cli import run_implementation_prompt
from vibe_control.progress_brief import build_brief, build_progress
from vibe_control.self_grill_contract import SELF_GRILL_CONTRACT_ID, self_grill_contract_dict


def _mini_repo(tmp_path: Path) -> Path:
    import yaml

    (tmp_path / ".git").mkdir()
    (tmp_path / "docs" / "project").mkdir(parents=True)
    (tmp_path / "docs" / "project" / "spec-registry.yml").write_text(
        "- id: only\n  status: active\n  path: docs/a.md\n  title: A\n",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "a.md").write_text("# A", encoding="utf-8")
    cfg = {
        "project": {"id": "test-grill", "name": "Test Grill"},
        "components": {
            "knowledge": {"enabled": False},
            "task": {"enabled": False},
            "sdd": {"enabled": False},
            "tdd": {"enabled": False},
        },
        "knowledge": {
            "provider": "notebooklm",
            "fallback_provider": "repo",
            "max_sources": 10,
            "warn_sources": 8,
            "authoritative_statuses": ["active"],
        },
        "specs": {
            "registry": "docs/project/spec-registry.yml",
            "required_fields": ["id"],
        },
        "tasks": {"provider": "beads"},
    }
    (tmp_path / ".config").mkdir()
    (tmp_path / ".config" / "vibe-control.yaml").write_text(
        yaml.safe_dump(cfg), encoding="utf-8"
    )
    return tmp_path


def test_self_grill_contract_lists_session_surfaces():
    c = self_grill_contract_dict()
    assert c["contract_id"] == SELF_GRILL_CONTRACT_ID
    assert any("grill status" in x for x in c["entry_commands"])
    assert any("session loop" in d or "session-loop" in d for d in c["docs"])
    # Session loop landed — limitations no longer claim missing Progress pull-back
    assert not any("No mid-course Progress pull-back" in x for x in c["known_limitations_v1"])


def test_open_session_round_zero(tmp_path):
    root = _mini_repo(tmp_path)
    sess = open_session(root, thesis="why is X broken")
    assert sess["round_id"] == 0
    assert sess["loop_status"] == "IN_PROGRESS"
    assert read_active_pointer(root) == sess["grill_id"]
    assert (root / "runtime/vibe-grill/sessions" / f"{sess['grill_id']}.json").is_file()
    # Resume same session
    again = open_session(root, thesis="ignored while active")
    assert again["grill_id"] == sess["grill_id"]


def test_grill_brief_opens_session(tmp_path, monkeypatch, capsys):
    root = _mini_repo(tmp_path)
    monkeypatch.chdir(root)
    code = main(["gateway", "--intent", "grill_brief", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["ok"] is True
    engine = payload["data"]["engine_payload"]
    data = engine["data"]
    assert data["communication_mode"] == "self_grill"
    assert data["grill_session"]["round_id"] == 0
    assert data["grill_session"]["loop_status"] == "IN_PROGRESS"
    assert "self_grill_in_progress" in data["blocked_reasons"]
    assert data["safe_next_action"]["code"] == "CONTINUE_SELF_GRILL"
    assert active_in_progress(root) is not None


def test_progress_pullback_while_in_progress(tmp_path):
    root = _mini_repo(tmp_path)
    open_session(root, thesis="pullback")
    env = build_progress(
        repo_root=root,
        integration_status={
            "project_id": "test-grill",
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
        },
        next_selection={
            "no_actionable_next_task": True,
            "next_actionable_task": None,
        },
        git_status_short="",
        observed_head="deadbeef",
        closeout_data={
            "closeout_complete": True,
            "implementation_ready": False,
            "provider_sync_required": False,
            "sync_state": "synced",
            "provider_ask_clean": True,
            "task_cache_current": True,
            "blocked_reasons": [],
        },
    )
    data = env["data"]
    assert "self_grill_in_progress" in data["blocked_reasons"]
    assert data["safe_next_action"]["code"] == "CONTINUE_SELF_GRILL"
    assert data["grill_session"]["loop_status"] == "IN_PROGRESS"


def test_closeout_blocker_keeps_safe_next_over_grill(tmp_path):
    root = _mini_repo(tmp_path)
    open_session(root, thesis="closeout wins")
    env = build_progress(
        repo_root=root,
        integration_status={
            "project_id": "test-grill",
            "product_ready": False,
            "config_ok": True,
            "provider_sync_required": True,
            "closeout_complete": False,
            "task_cache_current": False,
            "blocked_reasons": ["provider_sync_required"],
            "knowledge_provider": {
                "sync_state": "drift",
                "provider_ask_clean": False,
                "available": True,
            },
            "capability_profile": {
                "knowledge_enabled": True,
                "task_enabled": True,
            },
            "components": {
                "knowledge": {"enabled": True},
                "task": {"enabled": True},
            },
            "warnings": [],
            "next_actions": [],
        },
        next_selection={"no_actionable_next_task": True, "next_actionable_task": None},
        git_status_short="",
        observed_head="deadbeef",
        closeout_data={
            "closeout_complete": False,
            "implementation_ready": False,
            "provider_sync_required": True,
            "blocked_reasons": ["provider_sync_required"],
        },
    )
    data = env["data"]
    assert data["safe_next_action"]["code"] == "RUN_BOUNDED_KNOWLEDGE_SYNC"
    assert "self_grill_in_progress" in data["blocked_reasons"]
    assert any(
        isinstance(a, dict) and a.get("code") == "CONTINUE_SELF_GRILL"
        for a in data["next_actions"]
    )


def test_implementation_prompt_blocked_then_allowed(tmp_path, monkeypatch, capsys):
    root = _mini_repo(tmp_path)
    open_session(root, thesis="block prompt")
    blocked = run_implementation_prompt(
        repo_root=root,
        task_selector="roadmap.anything",
        include_provider_probe=False,
    )
    assert blocked["ok"] is False
    assert blocked["error"]["code"] == "SELF_GRILL_IN_PROGRESS"

    close_session(root, status="EXHAUSTED")
    # After close, grill gate lifts (may still fail for other reasons)
    after = run_implementation_prompt(
        repo_root=root,
        task_selector="roadmap.anything",
        include_provider_probe=False,
    )
    assert after.get("error", {}).get("code") != "SELF_GRILL_IN_PROGRESS"

    monkeypatch.chdir(root)
    code = main(["grill", "status", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["data"]["in_progress"] is False


def test_grill_cli_checkpoint_and_close(tmp_path, monkeypatch, capsys):
    root = _mini_repo(tmp_path)
    monkeypatch.chdir(root)
    open_session(root, thesis="cli")

    code = main(["grill", "checkpoint", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["data"]["session"]["round_id"] == 1
    assert out["data"]["session"]["loop_status"] == "IN_PROGRESS"

    code = main(["grill", "close", "--status", "EXHAUSTED", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["data"]["session"]["loop_status"] == "EXHAUSTED"
    assert out["data"]["active_cleared"] is True
    assert active_in_progress(root) is None


def test_plain_brief_pulls_back_when_session_active(tmp_path):
    root = _mini_repo(tmp_path)
    open_session(root, thesis="plain brief")
    env = build_brief(
        repo_root=root,
        integration_status={
            "project_id": "test-grill",
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
        },
        next_selection={"no_actionable_next_task": True, "next_actionable_task": None},
        git_status_short="",
        observed_head="deadbeef",
        closeout_data={
            "closeout_complete": True,
            "provider_sync_required": False,
            "blocked_reasons": [],
        },
    )
    data = env["data"]
    assert data.get("communication_mode") is None  # plain brief, not grill_brief
    assert data["safe_next_action"]["code"] == "CONTINUE_SELF_GRILL"
    assert data["grill_session"]["loop_status"] == "IN_PROGRESS"
