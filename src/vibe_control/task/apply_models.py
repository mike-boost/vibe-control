"""Phase 11B apply plan / result models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from vibe_control.json_envelope import attach_operation_result

ApplyOpType = Literal[
    "create_managed",
    "update_managed",
    "skip_completed",
    "optional_backfill_completed",
    "skip_unmanaged",
    "skip_duplicate",
    "skip_conflict",
    "blocked_repair_required",
    "skip_delete_forbidden",
    "skip_unavailable_provider",
]

EXECUTABLE_OP_TYPES = frozenset({"create_managed", "update_managed"})


@dataclass
class ApplyOperation:
    op_type: ApplyOpType
    managed_key: str | None
    ssot_id: str | None
    ssot_path: str | None
    ssot_anchor: str | None
    task_kind: str | None
    title: str
    reason: str
    executable: bool
    mutation: bool = False
    project_id: str | None = None
    ssot_snapshot_hash: str | None = None
    source_item_hash: str | None = None
    phase_state: str | None = None
    actionable: bool | None = None
    provider_task_id: str | None = None
    provider_task_id_hash: str | None = None
    description: str | None = None
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None

    def to_dict(self, *, redact_provider_ids: bool = True) -> dict[str, Any]:
        out: dict[str, Any] = {
            "op_type": self.op_type,
            "managed_key": self.managed_key,
            "project_id": self.project_id,
            "ssot_id": self.ssot_id,
            "ssot_path": self.ssot_path,
            "ssot_anchor": self.ssot_anchor,
            "task_kind": self.task_kind,
            "ssot_snapshot_hash": self.ssot_snapshot_hash,
            "source_item_hash": self.source_item_hash,
            "phase_state": self.phase_state,
            "actionable": self.actionable,
            "title": self.title,
            "reason": self.reason,
            "executable": self.executable,
            "mutation": self.mutation,
        }
        if self.provider_task_id_hash:
            out["provider_task_id_hash"] = self.provider_task_id_hash
        elif self.provider_task_id and not redact_provider_ids:
            out["provider_task_id"] = self.provider_task_id
        if self.before is not None:
            out["before"] = dict(self.before)
        if self.after is not None:
            out["after"] = dict(self.after)
        return out


@dataclass
class ApplyPlan:
    operations: list[ApplyOperation] = field(default_factory=list)
    expected_count: int = 0
    actual_count: int = 0
    plan_binding_hash: str | None = None
    ssot_snapshot_identity: dict[str, Any] = field(default_factory=dict)
    knowledge_readiness: dict[str, Any] = field(default_factory=dict)
    autonomy_policy: dict[str, Any] = field(default_factory=dict)

    @property
    def counts(self) -> dict[str, int]:
        create = sum(1 for o in self.operations if o.op_type == "create_managed")
        update = sum(1 for o in self.operations if o.op_type == "update_managed")
        skip = sum(
            1
            for o in self.operations
            if o.op_type.startswith("skip_")
            or o.op_type in {"optional_backfill_completed", "blocked_repair_required"}
        )
        blocked = sum(
            1
            for o in self.operations
            if o.op_type in {"skip_unavailable_provider", "blocked_repair_required"}
        )
        return {"create": create, "update": update, "skip": skip, "blocked": blocked}

    @property
    def counts_by_op_type(self) -> dict[str, int]:
        """Explicit separation of create/update/skip categories for apply plans."""
        keys = (
            "create_managed",
            "update_managed",
            "skip_completed",
            "optional_backfill_completed",
            "skip_unmanaged",
            "skip_duplicate",
            "skip_conflict",
            "blocked_repair_required",
            "skip_delete_forbidden",
            "skip_unavailable_provider",
        )
        return {k: sum(1 for o in self.operations if o.op_type == k) for k in keys}

    def to_dict(self, *, redact_provider_ids: bool = True) -> dict[str, Any]:
        return {
            "expected_count": self.expected_count,
            "actual_count": self.actual_count,
            "plan": self.counts,
            "plan_by_op_type": self.counts_by_op_type,
            "plan_binding_hash": self.plan_binding_hash,
            "ssot_snapshot_identity": dict(self.ssot_snapshot_identity),
            "knowledge_readiness": dict(self.knowledge_readiness),
            "autonomy_policy": dict(self.autonomy_policy),
            "operations": [o.to_dict(redact_provider_ids=redact_provider_ids) for o in self.operations],
        }


@dataclass
class ApplyResult:
    ok: bool
    mode: str
    mutation: bool
    provider: str
    project_id: str
    plan: ApplyPlan
    warnings: list[str] = field(default_factory=list)
    next_actions: list[dict[str, Any]] = field(default_factory=list)
    message: str | None = None
    code: str | None = None
    effects: list[dict[str, Any]] = field(default_factory=list)

    def to_envelope(self) -> dict[str, Any]:
        """Build command envelope; mutation_* derived from completed effects only."""
        # dry_run is planning only; blocked/applied are apply-path outcomes.
        mutation_intent = self.mode != "dry_run"
        data = self.plan.to_dict(redact_provider_ids=True)
        data["mutation"] = bool(self.effects)
        envelope: dict[str, Any] = {
            "ok": self.ok,
            "command": "vibe task apply",
            "project_id": self.project_id,
            "mode": self.mode,
            "provider": self.provider,
            "data": data,
            "warnings": list(self.warnings),
            "next_actions": list(self.next_actions),
        }
        if self.code or self.message:
            envelope["code"] = self.code
            envelope["message"] = self.message
        out = attach_operation_result(
            envelope,
            mutation_intent=mutation_intent,
            effects=list(self.effects),
        )
        performed = bool(out["mutation_performed"])
        out_data = out.get("data")
        if isinstance(out_data, dict):
            out_data["mutation"] = performed
        return out
