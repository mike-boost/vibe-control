"""Ask hygiene and SSOT drift-recovery / bounded sync-apply guard contracts."""

from __future__ import annotations

from pathlib import Path

from vibe_control.knowledge.ask_hygiene import (
    DEFAULT_CLOSEOUT_SSOT_DOC_IDS,
    assert_apply_ops_are_current_ssot_bounded,
    evaluate_ask_hygiene,
    preflight_current_ssot_drift_recovery,
)


def test_synced_alone_not_clean_when_candidates_remain():
    result = evaluate_ask_hygiene(
        sync_state="synced",
        required_updates_count=0,
        candidate_count=1,
        orphan_managed_count=1,
    )
    assert result["provider_ask_clean"] is False
    assert result["condition"] == "orphan_pollution"


def test_clean_requires_synced_zero_required_zero_candidates():
    result = evaluate_ask_hygiene(
        sync_state="synced",
        required_updates_count=0,
        candidate_count=0,
        orphan_managed_count=0,
    )
    assert result["provider_ask_clean"] is True
    assert result["condition"] == "clean"


def test_current_ssot_drift_distinct_from_orphan_pollution():
    drift = evaluate_ask_hygiene(
        sync_state="drift",
        required_updates_count=2,
        candidate_count=0,
        orphan_managed_count=0,
    )
    assert drift["condition"] == "current_ssot_drift"
    assert drift["provider_ask_clean"] is False

    mismatch = evaluate_ask_hygiene(
        sync_state="target_mismatch",
        required_updates_count=0,
        candidate_count=0,
    )
    assert mismatch["condition"] == "target_mismatch"

    unavailable = evaluate_ask_hygiene(
        sync_state="unavailable",
        required_updates_count=0,
        candidate_count=0,
    )
    assert unavailable["condition"] == "provider_unavailable"


def test_preflight_ssot_drift_recovery_exact_match():
    desired = set(DEFAULT_CLOSEOUT_SSOT_DOC_IDS)
    required = [{"op": "replace_required", "doc_id": doc_id} for doc_id in sorted(desired)]
    result = preflight_current_ssot_drift_recovery(
        sync_state="drift",
        required_updates=required,
        operations=list(required),
        candidate_count=0,
        notebook_alias="OPM-test",
        expected_doc_ids=desired,
    )
    assert result["ok"] is True
    assert result["mutation_scope"] == "current_ssot_only"


def test_preflight_blocks_orphan_or_wrong_docs():
    desired = {"vibe_control_spec", "vibe_control_knowledge_spec"}
    blocked = preflight_current_ssot_drift_recovery(
        sync_state="drift",
        required_updates=[
            {"op": "replace_required", "doc_id": "vibe_control_spec"},
            {"op": "replace_required", "doc_id": "vibe_control_knowledge_spec"},
        ],
        operations=[
            {"op": "replace_required", "doc_id": "vibe_control_spec"},
            {
                "op": "orphan_managed",
                "doc_id": "vibe_control_v0_5_spec",
                "action": "report_only_no_delete",
            },
        ],
        candidate_count=0,
        notebook_alias="OPM-test",
        expected_doc_ids=desired,
    )
    assert blocked["ok"] is False
    assert blocked["code"] == "SSOT_DRIFT_RECOVERY_BLOCKED"

    blocked2 = preflight_current_ssot_drift_recovery(
        sync_state="drift",
        required_updates=[{"op": "replace_required", "doc_id": "vibe_control_spec"}],
        operations=[{"op": "replace_required", "doc_id": "vibe_control_spec"}],
        candidate_count=1,
        notebook_alias="OPM-test",
        expected_doc_ids={"vibe_control_spec"},
    )
    assert blocked2["ok"] is False


def test_preflight_blocks_target_mismatch_and_unavailable_states():
    desired = {"vibe_control_spec"}
    mismatch = preflight_current_ssot_drift_recovery(
        sync_state="drift",
        required_updates=[{"op": "replace_required", "doc_id": "vibe_control_spec"}],
        operations=[{"op": "replace_required", "doc_id": "vibe_control_spec"}],
        candidate_count=0,
        notebook_alias="WRONG-NOTEBOOK",
        expected_doc_ids=desired,
    )
    assert mismatch["ok"] is False
    assert any("notebook_alias" in b for b in mismatch["blockers"])

    unavailable = evaluate_ask_hygiene(
        sync_state="unavailable",
        required_updates_count=0,
        candidate_count=0,
    )
    assert unavailable["provider_ask_clean"] is False
    assert unavailable["condition"] == "provider_unavailable"


def test_apply_ops_allowed_for_current_default_inventory_only():
    desired = set(DEFAULT_CLOSEOUT_SSOT_DOC_IDS)
    ok = assert_apply_ops_are_current_ssot_bounded(
        [
            {"op": "replace_required", "doc_id": "vibe_control_spec"},
            {"op": "add_missing", "doc_id": "vibe_control_roadmap_state"},
            {
                "op": "orphan_managed",
                "doc_id": "decision_log",
                "action": "report_only_no_delete",
            },
        ],
        desired_doc_ids=desired,
    )
    assert ok["ok"] is True


def test_apply_ops_blocks_unexpected_source_outside_inventory():
    desired = set(DEFAULT_CLOSEOUT_SSOT_DOC_IDS)
    bad = assert_apply_ops_are_current_ssot_bounded(
        [{"op": "replace_required", "doc_id": "docs_project_sync_phase8"}],
        desired_doc_ids=desired,
    )
    assert bad["ok"] is False
    assert any("non-desired" in v for v in bad["violations"])


def test_apply_ops_blocks_unmanaged_orphan_delete_and_broad_cleanup():
    desired = set(DEFAULT_CLOSEOUT_SSOT_DOC_IDS)
    cases = [
        [{"op": "delete_unmanaged", "doc_id": "x"}],
        [{"op": "unmanaged_delete", "doc_id": "x"}],
        [{"op": "broad_cleanup"}],
        [{"op": "notebook_clean"}],
        [{"op": "orphan_managed", "doc_id": "x", "action": "delete_now"}],
        [{"op": "orphan_managed", "doc_id": "x", "action": "delete_orphan"}],
    ]
    for ops in cases:
        bad = assert_apply_ops_are_current_ssot_bounded(ops, desired_doc_ids=desired)
        assert bad["ok"] is False, ops


def test_apply_ops_blocks_auth_config_target_change_ops():
    desired = set(DEFAULT_CLOSEOUT_SSOT_DOC_IDS)
    for kind in (
        "auth_change",
        "config_change",
        "target_change",
        "provider_auth_change",
        "provider_config_change",
        "provider_target_change",
    ):
        bad = assert_apply_ops_are_current_ssot_bounded(
            [{"op": kind}],
            desired_doc_ids=desired,
        )
        assert bad["ok"] is False, kind


def test_readonly_knowledge_commands_do_not_call_provider_apply():
    """status/query/doctor/inventory/sync dry-run must not invoke apply_forward_sync."""
    root = Path(__file__).resolve().parents[1] / "src" / "vibe_control"
    readonly_files = [
        root / "cli.py",
        root / "knowledge" / "doctor.py",
        root / "knowledge" / "query_router.py",
        root / "knowledge" / "sync_status.py",
    ]
    for path in readonly_files:
        text = path.read_text(encoding="utf-8")
        # Handlers may mention sync --apply as next_action text, but must not call apply.
        assert "apply_forward_sync(" not in text
        assert "retry_forward_sync(" not in text

    remote = (root / "knowledge" / "remote_ops.py").read_text(encoding="utf-8")
    # sync --apply and retry --apply both must fail closed on scope violation.
    assert 'code="APPLY_SCOPE_VIOLATION"' in remote
    assert remote.count("assert_apply_ops_are_current_ssot_bounded") >= 2
    assert "retry --apply refused: dry-run ops are not bounded to current SSOT" in remote


def test_reportable_hygiene_output_has_no_raw_provider_refs():
    result = evaluate_ask_hygiene(
        sync_state="synced",
        required_updates_count=0,
        candidate_count=0,
        orphan_managed_count=0,
    )
    blob = str(result)
    assert "notebooklm://" not in blob
    assert "NOTEBOOKLM_NOTEBOOK=" not in blob
