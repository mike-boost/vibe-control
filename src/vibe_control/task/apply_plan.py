"""Build Phase 11B ApplyPlan from Phase 11A ReconcileReport."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from vibe_control.task.apply_models import ApplyOperation, ApplyPlan
from vibe_control.task.autonomy import build_autonomy_policy
from vibe_control.task.marker import marker_from_expected, render_marker
from vibe_control.task.models import ExpectedTask, ReconcileItem, ReconcileReport


def _hash_provider_id(provider_task_id: str | None) -> str | None:
    if not provider_task_id:
        return None
    digest = hashlib.sha256(provider_task_id.encode("utf-8")).hexdigest()[:12]
    return f"sha256:{digest}"


def compute_plan_binding_hash(expected: list[ExpectedTask]) -> str:
    """Bind apply plan to current SSOT expected-task snapshot identity."""
    rows = [
        {
            "managed_key": e.managed_key,
            "ssot_id": e.ssot_id,
            "ssot_path": e.ssot_path,
            "ssot_anchor": e.ssot_anchor,
            "ssot_snapshot_hash": e.ssot_snapshot_hash,
            "source_item_hash": e.source_item_hash,
        }
        for e in sorted(expected, key=lambda x: x.managed_key)
    ]
    raw = json.dumps(rows, sort_keys=True, ensure_ascii=False)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def ssot_snapshot_identity(expected: list[ExpectedTask]) -> dict[str, Any]:
    hashes = sorted({e.ssot_snapshot_hash for e in expected})
    return {
        "expected_count": len(expected),
        "ssot_snapshot_hashes": hashes,
        "plan_binding_hash": compute_plan_binding_hash(expected),
    }


def _expected_fields(expected: ExpectedTask | None) -> dict[str, Any]:
    if expected is None:
        return {
            "managed_key": None,
            "project_id": None,
            "ssot_id": None,
            "ssot_path": None,
            "ssot_anchor": None,
            "task_kind": None,
            "ssot_snapshot_hash": None,
            "source_item_hash": None,
            "phase_state": None,
            "actionable": None,
            "title": "",
        }
    return {
        "managed_key": expected.managed_key,
        "project_id": expected.project_id,
        "ssot_id": expected.ssot_id,
        "ssot_path": expected.ssot_path,
        "ssot_anchor": expected.ssot_anchor,
        "task_kind": expected.task_kind,
        "ssot_snapshot_hash": expected.ssot_snapshot_hash,
        "source_item_hash": expected.source_item_hash,
        "phase_state": expected.phase_state,
        "actionable": expected.actionable,
        "title": expected.title,
    }


def _description_for_expected(expected: ExpectedTask) -> str:
    marker = marker_from_expected(
        project_id=expected.project_id,
        ssot_id=expected.ssot_id,
        ssot_path=expected.ssot_path,
        ssot_anchor=expected.ssot_anchor,
        task_kind=expected.task_kind,
        ssot_snapshot_hash=expected.ssot_snapshot_hash,
        source_item_hash=expected.source_item_hash,
    )
    return f"{expected.title}\n\n" + render_marker(marker)


def _from_missing(item: ReconcileItem) -> ApplyOperation:
    fields = _expected_fields(item.expected)
    # Status-aware: completed / baseline shells never become open create_managed.
    if item.expected is not None and not item.expected.actionable:
        # Prefer explicit skip_completed as the default non-executable category.
        return ApplyOperation(
            op_type="skip_completed",
            reason=(
                f"phase_state={item.expected.phase_state}; completed/baseline work is not "
                "default open create_managed (optional backfill only)"
            ),
            executable=False,
            description=None,
            **fields,
        )
    desc = _description_for_expected(item.expected) if item.expected else None
    return ApplyOperation(
        op_type="create_managed",
        reason=item.reason,
        executable=True,
        description=desc,
        **fields,
    )


def _skip_completed_task(expected: ExpectedTask) -> list[ApplyOperation]:
    fields = _expected_fields(expected)
    return [
        ApplyOperation(
            op_type="skip_completed",
            reason=(
                f"phase_state={expected.phase_state}; not an open create_managed target "
                "by default"
            ),
            executable=False,
            **fields,
        ),
        ApplyOperation(
            op_type="optional_backfill_completed",
            reason=(
                "Optional historical backfill into Beads is out of default apply path; "
                "requires explicit owner-approved backfill workflow"
            ),
            executable=False,
            **fields,
        ),
    ]


def _from_stale(item: ReconcileItem) -> ApplyOperation:
    fields = _expected_fields(item.expected)
    desc = _description_for_expected(item.expected) if item.expected else None
    pid = item.provider_task_ids[0] if item.provider_task_ids else None
    before = {
        "title": item.titles[0] if item.titles else None,
        "ssot_snapshot_hash": (item.details or {}).get("marker_ssot_snapshot_hash"),
        "source_item_hash": (item.details or {}).get("marker_source_item_hash"),
    }
    after = None
    if item.expected is not None:
        after = {
            "title": item.expected.title,
            "ssot_snapshot_hash": item.expected.ssot_snapshot_hash,
            "source_item_hash": item.expected.source_item_hash,
        }
    return ApplyOperation(
        op_type="update_managed",
        reason=item.reason,
        executable=True,
        provider_task_id=pid,
        provider_task_id_hash=_hash_provider_id(pid),
        description=desc,
        before=before,
        after=after,
        **fields,
    )


def _skip(
    op_type: str,
    item: ReconcileItem,
    *,
    title_fallback: str = "",
) -> ApplyOperation:
    fields = _expected_fields(item.expected)
    if not fields["title"]:
        fields["title"] = item.titles[0] if item.titles else title_fallback
    if fields["managed_key"] is None:
        fields["managed_key"] = item.managed_key
    pid = item.provider_task_ids[0] if item.provider_task_ids else None
    return ApplyOperation(
        op_type=op_type,  # type: ignore[arg-type]
        reason=item.reason,
        executable=False,
        provider_task_id=pid,
        provider_task_id_hash=_hash_provider_id(pid),
        **fields,
    )


def build_apply_plan(
    report: ReconcileReport,
    *,
    expected: list[ExpectedTask] | None = None,
    completed_expected: list[ExpectedTask] | None = None,
    knowledge_readiness: dict[str, Any] | None = None,
) -> ApplyPlan:
    """Map readonly reconcile categories to apply operations. No mutation."""
    ops: list[ApplyOperation] = []

    for item in report.missing:
        ops.append(_from_missing(item))
    for item in report.stale:
        # Stale completed shells still must not mutate by default.
        if item.expected is not None and not item.expected.actionable:
            ops.extend(_skip_completed_task(item.expected))
            continue
        ops.append(_from_stale(item))
    for item in report.duplicate:
        ops.append(_skip("skip_duplicate", item))
    for item in report.unmanaged:
        ops.append(_skip("skip_unmanaged", item, title_fallback="unmanaged"))
    for item in report.conflict:
        details = item.details or {}
        if details.get("unexpected_managed_key"):
            ops.append(_skip("skip_delete_forbidden", item, title_fallback="unexpected managed"))
        else:
            ops.append(_skip("skip_conflict", item, title_fallback="conflict"))
            # Deterministic repair-plan signal — never ad hoc user Q&A / never mutate.
            repair = _skip("blocked_repair_required", item, title_fallback="conflict repair")
            repair.reason = (
                f"{item.reason}; blocked_repair_required — review plan next_actions; "
                "do not mutate until deterministic repair is approved at boundary level"
            )
            ops.append(repair)

    # Always surface completed/baseline catalog entries as non-executable skips,
    # even when they are intentionally excluded from reconcile expected set.
    seen_completed: set[str] = {
        o.managed_key for o in ops if o.managed_key and o.op_type in {
            "skip_completed",
            "optional_backfill_completed",
        }
    }
    for task in completed_expected or []:
        if task.managed_key in seen_completed:
            continue
        ops.extend(_skip_completed_task(task))
        seen_completed.add(task.managed_key)

    expected_list = expected or [
        item.expected for item in (report.missing + report.stale + report.matched + report.duplicate)
        if item.expected is not None
    ]
    by_key: dict[str, ExpectedTask] = {}
    for e in list(expected_list) + list(completed_expected or []):
        by_key[e.managed_key] = e
    expected_deduped = list(by_key.values())
    identity = ssot_snapshot_identity(expected_deduped) if expected_deduped else {
        "expected_count": report.expected_count,
        "ssot_snapshot_hashes": [],
        "plan_binding_hash": None,
    }

    plan = ApplyPlan(
        operations=ops,
        expected_count=report.expected_count,
        actual_count=report.provider_task_count,
        plan_binding_hash=identity.get("plan_binding_hash"),
        ssot_snapshot_identity=identity,
        knowledge_readiness=dict(knowledge_readiness or {}),
    )
    plan.autonomy_policy = build_autonomy_policy(plan)
    return plan
