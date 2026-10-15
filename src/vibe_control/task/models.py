"""Phase 11A task identity, marker, provider, and reconcile models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


ReconcileCategory = Literal[
    "matched",
    "missing",
    "duplicate",
    "stale",
    "conflict",
    "unmanaged",
]


PhaseState = Literal[
    "completed",
    "baseline_complete",
    "actionable",
    "pending",
]


@dataclass(frozen=True)
class ExpectedTask:
    project_id: str
    ssot_id: str
    ssot_path: str
    ssot_anchor: str
    task_kind: str
    managed_key: str
    title: str
    ssot_snapshot_hash: str
    source_item_hash: str
    phase_state: PhaseState = "actionable"
    actionable: bool = True
    design_only: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "ssot_id": self.ssot_id,
            "ssot_path": self.ssot_path,
            "ssot_anchor": self.ssot_anchor,
            "task_kind": self.task_kind,
            "managed_key": self.managed_key,
            "title": self.title,
            "ssot_snapshot_hash": self.ssot_snapshot_hash,
            "source_item_hash": self.source_item_hash,
            "phase_state": self.phase_state,
            "actionable": self.actionable,
            "design_only": self.design_only,
        }


@dataclass(frozen=True)
class ManagedMarker:
    schema: str
    project_id: str
    task_provider: str
    managed_key: str
    ssot_id: str
    ssot_path: str
    ssot_anchor: str
    task_kind: str
    ssot_snapshot_hash: str
    source_item_hash: str
    managed_by: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "project_id": self.project_id,
            "task_provider": self.task_provider,
            "managed_key": self.managed_key,
            "ssot_id": self.ssot_id,
            "ssot_path": self.ssot_path,
            "ssot_anchor": self.ssot_anchor,
            "task_kind": self.task_kind,
            "ssot_snapshot_hash": self.ssot_snapshot_hash,
            "source_item_hash": self.source_item_hash,
            "managed_by": self.managed_by,
        }


@dataclass
class TaskRecord:
    provider_task_id: str | None = None
    title: str = ""
    description: str = ""
    relations: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_task_id": self.provider_task_id,
            "title": self.title,
            "description": self.description,
            "relations": list(self.relations),
        }


@dataclass
class ReconcileItem:
    category: ReconcileCategory
    reason: str
    managed_key: str | None = None
    expected: ExpectedTask | None = None
    provider_task_ids: list[str] = field(default_factory=list)
    titles: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "reason": self.reason,
            "managed_key": self.managed_key,
            "expected": None if self.expected is None else self.expected.to_dict(),
            "provider_task_ids": list(self.provider_task_ids),
            "titles": list(self.titles),
            "details": dict(self.details),
        }


@dataclass
class ReconcileReport:
    project_id: str
    expected_count: int
    provider_task_count: int
    matched: list[ReconcileItem] = field(default_factory=list)
    missing: list[ReconcileItem] = field(default_factory=list)
    duplicate: list[ReconcileItem] = field(default_factory=list)
    stale: list[ReconcileItem] = field(default_factory=list)
    conflict: list[ReconcileItem] = field(default_factory=list)
    unmanaged: list[ReconcileItem] = field(default_factory=list)
    mutation: bool = False
    provider_kind: str = "fake"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "expected_count": self.expected_count,
            "provider_task_count": self.provider_task_count,
            "matched": [x.to_dict() for x in self.matched],
            "missing": [x.to_dict() for x in self.missing],
            "duplicate": [x.to_dict() for x in self.duplicate],
            "stale": [x.to_dict() for x in self.stale],
            "conflict": [x.to_dict() for x in self.conflict],
            "unmanaged": [x.to_dict() for x in self.unmanaged],
            "counts": {
                "matched": len(self.matched),
                "missing": len(self.missing),
                "duplicate": len(self.duplicate),
                "stale": len(self.stale),
                "conflict": len(self.conflict),
                "unmanaged": len(self.unmanaged),
            },
            "mutation": False,
            "provider_kind": self.provider_kind,
            "warnings": list(self.warnings),
        }


class TaskProvider(Protocol):
    """Readonly task provider. Must not create/update/delete tasks."""

    name: str

    def list_tasks(self) -> list[TaskRecord]:
        ...
