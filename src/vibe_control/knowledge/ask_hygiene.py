"""Ask hygiene and bounded sync-recovery preflight (repo-owned safety rules)."""

from __future__ import annotations

from typing import Any


# Durable clean state for provider-backed ask (not prompt-only).
# synced alone is insufficient when leftover old sources remain.

DEFAULT_CLOSEOUT_SSOT_DOC_IDS = frozenset(
    {
        "vibe_control_spec",
        "vibe_control_knowledge_spec",
        "vibe_control_task_spec",
        "vibe_control_roadmap_state",
    }
)


def evaluate_ask_hygiene(
    *,
    sync_state: str | None,
    required_updates_count: int,
    candidate_count: int,
    orphan_managed_count: int = 0,
) -> dict[str, Any]:
    """Classify whether provider-backed ask may be declared clean.

    Clean requires:
    - sync_state == synced
    - required_updates_count == 0
    - candidate_count == 0
    - no orphan_managed leftovers
    """
    sync_state = str(sync_state or "unavailable")
    required = int(required_updates_count or 0)
    candidates = int(candidate_count or 0)
    orphans = int(orphan_managed_count or 0)

    reasons: list[str] = []
    condition = "unknown"

    if sync_state == "target_mismatch":
        condition = "target_mismatch"
        reasons.append("ProviderTarget mismatch; refuse ask-clean claims")
    elif sync_state == "unavailable":
        condition = "provider_unavailable"
        reasons.append("Provider unavailable; no ask-clean claim")
    elif candidates > 0 or orphans > 0:
        condition = "orphan_pollution"
        reasons.append(
            "Old non-current provider sources remain; provider-backed ask is polluted "
            "until owner removes them or explicitly accepts the risk"
        )
    elif sync_state == "drift" or required > 0:
        condition = "current_ssot_drift"
        reasons.append("Current SSOT drift; restore with bounded sync --apply after dry-run")
    elif sync_state == "synced" and required == 0 and candidates == 0 and orphans == 0:
        condition = "clean"
    elif sync_state in {"pending", "receipt_missing"}:
        condition = "current_ssot_drift"
        reasons.append(f"sync_state={sync_state}; not clean for provider ask")
    else:
        condition = "not_clean"
        reasons.append(f"sync_state={sync_state} is not a clean provider-ask state")

    provider_ask_clean = condition == "clean"
    return {
        "provider_ask_clean": provider_ask_clean,
        "condition": condition,
        "sync_state": sync_state,
        "required_updates_count": required,
        "candidate_count": candidates,
        "orphan_managed_count": orphans,
        "reasons": reasons,
        "rule": (
            "provider_ask_clean requires sync_state=synced AND "
            "required_updates_count=0 AND candidate_count=0 "
            "(synced alone is not enough if old sources remain)"
        ),
    }


def preflight_current_ssot_drift_recovery(
    *,
    sync_state: str | None,
    required_updates: list[dict[str, Any]] | None,
    operations: list[dict[str, Any]] | None,
    candidate_count: int,
    notebook_alias: str | None,
    expected_alias: str = "OPM-test",
    expected_doc_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Fail-closed preflight for bounded current-SSOT drift recovery apply.

    Approves only when:
    - candidate_count == 0 (orphan already cleaned or none)
    - sync_state == drift
    - required updates are exactly the expected current SSOT docs
    - dry-run has no orphan_managed op and no unmanaged delete
    - notebook alias matches expected target
    """
    expected_doc_ids = expected_doc_ids or set(DEFAULT_CLOSEOUT_SSOT_DOC_IDS)
    required_updates = list(required_updates or [])
    operations = list(operations or [])
    req_ids = sorted({str(u.get("doc_id")) for u in required_updates if u.get("doc_id")})
    expected_sorted = sorted(expected_doc_ids)

    blockers: list[str] = []
    if notebook_alias != expected_alias:
        blockers.append(f"notebook_alias={notebook_alias!r} != {expected_alias!r}")
    if int(candidate_count or 0) != 0:
        blockers.append("candidate_count must be 0 before SSOT drift recovery apply")
    if str(sync_state or "") != "drift":
        blockers.append(f"sync_state must be drift, got {sync_state!r}")
    if len(required_updates) != len(expected_doc_ids) or req_ids != expected_sorted:
        blockers.append(
            f"required updates must be exactly {expected_sorted}, got {req_ids}"
        )

    for op in operations:
        kind = str(op.get("op") or "")
        action = str(op.get("action") or "")
        if kind == "orphan_managed":
            blockers.append("dry-run still lists orphan_managed; refuse recovery apply")
        if kind in {"delete_unmanaged", "unmanaged_delete", "broad_cleanup"}:
            blockers.append(f"forbidden op {kind}")
        if "unmanaged" in kind and "delete" in kind:
            blockers.append(f"forbidden unmanaged delete op {kind}")
        if kind == "orphan_managed" and "delete" in action and "report_only" not in action:
            blockers.append("orphan delete action is forbidden")
        if kind in {"add_missing", "replace_required"}:
            doc_id = str(op.get("doc_id") or "")
            if doc_id and doc_id not in expected_doc_ids:
                blockers.append(f"required op for non-current doc_id={doc_id}")

    ok = not blockers
    return {
        "ok": ok,
        "code": "SSOT_DRIFT_RECOVERY_PREFLIGHT_OK" if ok else "SSOT_DRIFT_RECOVERY_BLOCKED",
        "blockers": blockers,
        "required_doc_ids": req_ids,
        "candidate_count": int(candidate_count or 0),
        "sync_state": sync_state,
        "notebook_alias": notebook_alias,
        "mutation_scope": "current_ssot_only" if ok else "blocked",
    }


def assert_apply_ops_are_current_ssot_bounded(
    operations: list[dict[str, Any]] | None,
    *,
    desired_doc_ids: set[str],
) -> dict[str, Any]:
    """Ensure dry-run/apply mutation ops only target current desired SSOT docs.

    Orphan report-only ops are allowed in dry-run output but must never become deletes.
    Auth/config/target changes and broad cleanup are never allowed via sync/retry apply.
    """
    operations = list(operations or [])
    violations: list[str] = []
    mutating = {"add_missing", "replace_required"}
    forbidden = {
        "delete_unmanaged",
        "unmanaged_delete",
        "broad_cleanup",
        "notebook_clean",
        "auth_change",
        "config_change",
        "target_change",
        "provider_auth_change",
        "provider_config_change",
        "provider_target_change",
    }
    for op in operations:
        kind = str(op.get("op") or "")
        action = str(op.get("action") or "")
        doc_id = op.get("doc_id")
        if kind in mutating and doc_id and str(doc_id) not in desired_doc_ids:
            violations.append(f"{kind} targets non-desired doc_id={doc_id}")
        if kind == "orphan_managed" and action != "report_only_no_delete":
            violations.append(f"orphan_managed action must be report_only_no_delete, got {action!r}")
        if kind in forbidden:
            violations.append(f"forbidden mutation op {kind}")
        if "unmanaged" in kind and "delete" in kind:
            violations.append(f"forbidden unmanaged delete op {kind}")
        if kind == "orphan_managed" and "delete" in action and "report_only" not in action:
            violations.append("orphan delete action is forbidden")
    return {
        "ok": not violations,
        "violations": violations,
        "desired_doc_ids": sorted(desired_doc_ids),
    }
