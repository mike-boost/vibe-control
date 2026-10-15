"""Readonly reconcile: expected SSOT tasks vs TaskProvider (Phase 11A)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from vibe_control.task.marker import MarkerError, parse_marker_from_text
from vibe_control.task.models import (
    ExpectedTask,
    ReconcileItem,
    ReconcileReport,
    TaskRecord,
)
from vibe_control.task.provider import FakeTaskProvider


def reconcile_readonly(
    *,
    project_id: str,
    expected: list[ExpectedTask],
    provider_tasks: list[TaskRecord],
    provider_kind: str = "fake",
    warnings: list[str] | None = None,
) -> ReconcileReport:
    """Dry-run diff only. Never creates/updates/merges/repairs/adopts tasks."""
    report = ReconcileReport(
        project_id=project_id,
        expected_count=len(expected),
        provider_task_count=len(provider_tasks),
        provider_kind=provider_kind,
        warnings=list(warnings or []),
        mutation=False,
    )
    expected_by_key = {item.managed_key: item for item in expected}

    # managed_key -> list[(TaskRecord, marker_or_none, parse_error)]
    by_key: dict[str, list[tuple[TaskRecord, Any, MarkerError | None]]] = defaultdict(list)
    conflict_parse: list[ReconcileItem] = []
    unmanaged: list[ReconcileItem] = []

    for task in provider_tasks:
        body = task.description or ""
        try:
            marker = parse_marker_from_text(body)
        except MarkerError as exc:
            conflict_parse.append(
                ReconcileItem(
                    category="conflict",
                    reason=exc.message,
                    managed_key=None,
                    provider_task_ids=[task.provider_task_id or ""],
                    titles=[task.title],
                    details={"code": exc.code, **exc.details, "relations": list(task.relations)},
                )
            )
            continue
        if marker is None:
            unmanaged.append(
                ReconcileItem(
                    category="unmanaged",
                    reason="task has no valid Vibe-managed marker (title is not identity)",
                    managed_key=None,
                    provider_task_ids=[task.provider_task_id or ""],
                    titles=[task.title],
                    details={"relations": list(task.relations)},
                )
            )
            continue
        by_key[marker.managed_key].append((task, marker, None))

    report.conflict.extend(conflict_parse)
    report.unmanaged.extend(unmanaged)

    seen_keys: set[str] = set()

    for managed_key, expected_task in expected_by_key.items():
        seen_keys.add(managed_key)
        group = by_key.get(managed_key) or []
        if not group:
            report.missing.append(
                ReconcileItem(
                    category="missing",
                    reason="expected managed_key has no provider binding",
                    managed_key=managed_key,
                    expected=expected_task,
                )
            )
            continue
        if len(group) > 1:
            report.duplicate.append(
                ReconcileItem(
                    category="duplicate",
                    reason="multiple managed tasks map to the same managed_key",
                    managed_key=managed_key,
                    expected=expected_task,
                    provider_task_ids=[t.provider_task_id or "" for t, _, _ in group],
                    titles=[t.title for t, _, _ in group],
                )
            )
            continue

        task, marker, _ = group[0]
        # Identity fields must match expected for this key.
        if (
            marker.project_id != expected_task.project_id
            or marker.ssot_id != expected_task.ssot_id
            or marker.ssot_path != expected_task.ssot_path
            or marker.ssot_anchor != expected_task.ssot_anchor
            or marker.task_kind != expected_task.task_kind
        ):
            report.conflict.append(
                ReconcileItem(
                    category="conflict",
                    reason="marker identity fields disagree with expected task",
                    managed_key=managed_key,
                    expected=expected_task,
                    provider_task_ids=[task.provider_task_id or ""],
                    titles=[task.title],
                    details={"marker": marker.to_dict()},
                )
            )
            continue
        if (
            marker.ssot_snapshot_hash != expected_task.ssot_snapshot_hash
            or marker.source_item_hash != expected_task.source_item_hash
        ):
            report.stale.append(
                ReconcileItem(
                    category="stale",
                    reason="managed task hashes drift from expected SSOT snapshot/item hash",
                    managed_key=managed_key,
                    expected=expected_task,
                    provider_task_ids=[task.provider_task_id or ""],
                    titles=[task.title],
                    details={
                        "marker_ssot_snapshot_hash": marker.ssot_snapshot_hash,
                        "expected_ssot_snapshot_hash": expected_task.ssot_snapshot_hash,
                        "marker_source_item_hash": marker.source_item_hash,
                        "expected_source_item_hash": expected_task.source_item_hash,
                    },
                )
            )
            continue
        report.matched.append(
            ReconcileItem(
                category="matched",
                reason="managed task matches expected identity and hashes",
                managed_key=managed_key,
                expected=expected_task,
                provider_task_ids=[task.provider_task_id or ""],
                titles=[task.title],
            )
        )

    # Valid managed markers whose key is not in expected set.
    for managed_key, group in by_key.items():
        if managed_key in seen_keys:
            continue
        report.conflict.append(
            ReconcileItem(
                category="conflict",
                reason="managed_key not in expected SSOT projection set",
                managed_key=managed_key,
                provider_task_ids=[t.provider_task_id or "" for t, _, _ in group],
                titles=[t.title for t, _, _ in group],
                details={"unexpected_managed_key": True},
            )
        )

    report.mutation = False
    return report


def build_reconcile_report(
    *,
    project_id: str,
    expected: list[ExpectedTask],
    provider: FakeTaskProvider | Any,
    warnings: list[str] | None = None,
) -> ReconcileReport:
    tasks = list(provider.list_tasks())
    kind = getattr(provider, "name", "unknown")
    return reconcile_readonly(
        project_id=project_id,
        expected=expected,
        provider_tasks=tasks,
        provider_kind=str(kind),
        warnings=warnings,
    )
