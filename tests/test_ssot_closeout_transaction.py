"""SSOT closeout transaction contract tests (local/readonly)."""

from __future__ import annotations

from pathlib import Path

from vibe_control.closeout import (
    CLOSEOUT_STATES,
    PROJECT_SOURCES_ADVISOR_FILES,
    evaluate_ssot_closeout,
)


def test_closeout_no_ssot_change_product_ready():
    result = evaluate_ssot_closeout(
        ssot_or_include_extra_changed=False,
        knowledge_synced=True,
        provider_ask_clean=True,
        product_ready=True,
        task_available=True,
        task_readable=True,
    )
    assert result["closeout_state"] == "no_ssot_change_product_ready"
    assert result["provider_sync_required"] is False
    assert result["full_pass_allowed"] is True
    assert result["mutation"] is False


def test_closeout_ssot_changed_no_sync_approval():
    result = evaluate_ssot_closeout(
        ssot_or_include_extra_changed=True,
        ssot_committed=True,
        sync_approved=False,
        knowledge_synced=False,
        provider_ask_clean=False,
        product_ready=False,
        task_available=True,
        task_readable=True,
    )
    assert result["closeout_state"] == "ssot_change_committed_sync_required"
    assert result["provider_sync_required"] is True
    assert result["full_pass_allowed"] is False
    assert result["closeout_complete"] is False
    assert "waiting_owner_project_sources" not in CLOSEOUT_STATES
    assert result["closeout_state"] != "waiting_owner_project_sources"
    assert result["chatgpt_project_sources"]["product_closeout_gate"] is False
    codes = [a["code"] for a in result["next_actions"]]
    assert "UPDATE_CHATGPT_PROJECT_SOURCES" not in codes
    assert codes[0] == "RUN_BOUNDED_KNOWLEDGE_SYNC"
    assert "RUN_BOUNDED_KNOWLEDGE_SYNC" in codes
    assert result["rules"]["commit_alone_is_not_closeout_complete"] is True
    assert result["rules"]["bounded_sync_is_required_closeout_step"] is True
    assert result["rules"]["chatgpt_project_sources_not_product_closeout_gate"] is True


def test_closeout_ssot_changed_sync_required_not_project_sources_gate():
    result = evaluate_ssot_closeout(
        ssot_or_include_extra_changed=True,
        ssot_committed=True,
        sync_approved=False,
        knowledge_synced=False,
        product_ready=False,
        task_available=True,
        task_readable=True,
    )
    assert result["closeout_state"] == "ssot_change_committed_sync_required"
    assert result["provider_sync_required"] is True
    assert result["closeout_complete"] is False
    codes = [a["code"] for a in result["next_actions"]]
    assert "UPDATE_CHATGPT_PROJECT_SOURCES" not in codes
    assert "RUN_BOUNDED_KNOWLEDGE_SYNC" in codes
    assert "waiting_owner_project_sources" not in result["warnings"]
    assert "chatgpt_project_sources_manual_handoff_required" not in result["warnings"]


def test_closeout_ssot_changed_provider_unavailable_pending():
    result = evaluate_ssot_closeout(
        ssot_or_include_extra_changed=True,
        ssot_committed=True,
        sync_approved=True,
        sync_attempted=True,
        knowledge_available=False,
        knowledge_pending=True,
        knowledge_synced=False,
        product_ready=False,
        task_available=True,
        task_readable=True,
    )
    assert result["closeout_state"] == "ssot_change_committed_sync_pending"
    assert result["provider_sync_required"] is True
    assert result["full_pass_allowed"] is False
    assert result["product_ready_claim_allowed"] is False


def test_closeout_synced_product_ready():
    result = evaluate_ssot_closeout(
        ssot_or_include_extra_changed=True,
        ssot_committed=True,
        sync_approved=True,
        knowledge_synced=True,
        provider_ask_clean=True,
        knowledge_available=True,
        product_ready=True,
        task_available=True,
        task_readable=True,
    )
    assert result["closeout_state"] == "ssot_change_committed_synced_product_ready"
    assert result["provider_sync_required"] is False
    assert result["full_pass_allowed"] is True
    assert result["closeout_complete"] is True


def test_closeout_repo_only_degraded():
    result = evaluate_ssot_closeout(
        ssot_or_include_extra_changed=False,
        product_ready=False,
        knowledge_synced=False,
        repo_fallback_usable=True,
        task_available=False,
    )
    assert result["closeout_state"] == "repo_only_degraded"
    assert result["full_pass_allowed"] is False
    assert result["rules"]["repo_fallback_not_product_ready"] is True
    assert result["rules"]["forward_only_sync"] is True
    assert result["rules"]["no_provider_to_repo_recovery"] is True


def test_closeout_rules_preserve_knowledge_design():
    result = evaluate_ssot_closeout(ssot_or_include_extra_changed=True, product_ready=False)
    rules = result["rules"]
    assert rules["repo_ssot_is_truth"] is True
    assert rules["notebooklm_is_derived"] is True
    assert rules["remote_ack_is_watermark_only"] is True
    assert rules["status_query_doctor_readonly"] is True
    assert rules["bounded_sync_apply_allowed_on_closeout"] is True
    assert rules["non_bounded_sync_needs_explicit_approval"] is True
    assert rules["chatgpt_project_sources_owner_manual"] is True
    assert rules["chatgpt_project_sources_not_product_closeout_gate"] is True


def test_chatgpt_project_sources_advisor_files_match_active_specs():
    assert "docs/project/vibe-control-spec.md" in PROJECT_SOURCES_ADVISOR_FILES
    assert "docs/project/vibe-control-knowledge-spec.md" in PROJECT_SOURCES_ADVISOR_FILES
    assert "docs/project/vibe-control-task-spec.md" in PROJECT_SOURCES_ADVISOR_FILES
    assert "docs/project/vibe-control-roadmap-state.md" in PROJECT_SOURCES_ADVISOR_FILES
    assert "docs/project/DECISION_LOG.md" not in PROJECT_SOURCES_ADVISOR_FILES
    assert not any("/sync/" in p for p in PROJECT_SOURCES_ADVISOR_FILES)
    for path in PROJECT_SOURCES_ADVISOR_FILES:
        assert Path(path).is_file()
    result = evaluate_ssot_closeout(ssot_or_include_extra_changed=True, product_ready=False)
    assert result["chatgpt_project_sources"]["advisor_files"] == list(PROJECT_SOURCES_ADVISOR_FILES)
    assert result["chatgpt_project_sources"]["product_closeout_gate"] is False
