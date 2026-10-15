"""Agent task autonomy policy for Phase 11B apply plans (Option A).

Option A (this baseline):
- Safe Vibe-managed create/update may be agent-autonomous *policy-wise*
  (no per-op user questions).
- Live Beads execution still requires the temporary dual gate
  (VIBE_BEADS_LIVE_APPLY=1 AND --confirm-beads-live-apply) PLUS
  --autonomous-managed, product_ready, and a safe managed plan.
- Default local gates never set the live env and never mutate Beads.

Option B (future): replace dual gate with product_ready + safe-plan only.
"""

from __future__ import annotations

from typing import Any

from vibe_control.json_envelope import next_action
from vibe_control.task.apply_models import EXECUTABLE_OP_TYPES, ApplyPlan


UNSAFE_REPORT_OP_TYPES = frozenset(
    {
        "skip_unmanaged",
        "skip_duplicate",
        "skip_conflict",
        "blocked_repair_required",
        "skip_delete_forbidden",
        "skip_unavailable_provider",
    }
)

BLOCKING_UNSAFE_EXECUTABLE = frozenset(
    {
        "skip_unmanaged",
        "skip_duplicate",
        "skip_conflict",
        "blocked_repair_required",
        "skip_delete_forbidden",
        "skip_unavailable_provider",
    }
)


def build_autonomy_policy(plan: ApplyPlan) -> dict[str, Any]:
    """Summarize autonomy rules for envelopes."""
    by = plan.counts_by_op_type
    has_safe_managed = (by.get("create_managed", 0) + by.get("update_managed", 0)) > 0
    has_unsafe = any(by.get(k, 0) > 0 for k in UNSAFE_REPORT_OP_TYPES)
    safety = evaluate_managed_apply_safety(plan)
    return {
        "agent_facing": True,
        "option": "A",
        "user_asks_per_managed_op": False,
        "vibe_managed_create_update": "autonomous_when_knowledge_ready_and_safe_plan",
        "requires_product_ready": False,
        "allows_safe_task_cache_convergence_without_full_product_ready": True,
        "requires_current_plan_binding": True,
        "safe_managed_ops_only": True,
        "has_safe_managed_ops": has_safe_managed,
        "has_unsafe_ops": has_unsafe,
        "plan_safe_for_autonomous_managed": safety["ok"],
        "unmanaged": "skip_never_adopt",
        "duplicate_conflict": "skip_or_blocked_repair_required",
        "delete": "forbidden_by_default",
        "live_beads_gate": "temporary_dual_gate",
        "live_beads_gate_detail": (
            "Option A: live Beads requires VIBE_BEADS_LIVE_APPLY=1 AND "
            "--confirm-beads-live-apply AND --autonomous-managed AND "
            "product_ready AND safe managed plan. Default gates never set the env."
        ),
        "autonomous_managed_flag": "--autonomous-managed",
        "live_beads_execution": False,
        "option_b_delta": (
            "Option B would remove the dual gate and unlock live create/update from "
            "product_ready + safe-plan checks alone (needs stronger tests first)."
        ),
        "fake_provider_for_tests": True,
    }


def evaluate_managed_apply_safety(plan: ApplyPlan) -> dict[str, Any]:
    """Safe autonomous managed apply: executable ops are only create/update managed."""
    executable = [o for o in plan.operations if o.executable]
    unsafe_executable = [
        o
        for o in executable
        if o.op_type not in EXECUTABLE_OP_TYPES or o.op_type in BLOCKING_UNSAFE_EXECUTABLE
    ]
    # Also treat any executable non create/update as unsafe.
    non_managed = [o for o in executable if o.op_type not in {"create_managed", "update_managed"}]
    reasons: list[str] = []
    if non_managed:
        reasons.append(
            "executable_ops_not_only_managed_create_update:"
            + ",".join(sorted({o.op_type for o in non_managed}))
        )
    if unsafe_executable and not non_managed:
        reasons.append("unsafe_executable_ops_present")
    ok = len(executable) > 0 and not non_managed
    if len(executable) == 0:
        reasons.append("no_executable_managed_ops")
        ok = False
    return {
        "ok": ok,
        "executable_count": len(executable),
        "create_count": sum(1 for o in executable if o.op_type == "create_managed"),
        "update_count": sum(1 for o in executable if o.op_type == "update_managed"),
        "reasons": reasons,
        "recognized_as_autonomous_managed": ok,
    }


def evaluate_autonomous_managed_eligibility(
    plan: ApplyPlan,
    *,
    product_ready: bool,
    task_readable: bool,
    beads_confirm: bool,
    env_ok: bool,
    autonomous_managed: bool,
    plan_binding_ok: bool = True,
    safe_task_convergence_allowed: bool = False,
) -> dict[str, Any]:
    """Eligibility for Option A live autonomous managed Beads apply.

    Safe task-cache convergence may proceed when knowledge is ready even if
    full product_ready is false solely because the local ephemeral cache is not current.
    """
    safety = evaluate_managed_apply_safety(plan)
    missing: list[str] = []
    ready_gate = bool(product_ready or safe_task_convergence_allowed)
    if not ready_gate:
        missing.append("product_ready_or_safe_task_convergence")
    if not task_readable:
        missing.append("task_provider_readable")
    if not plan_binding_ok:
        missing.append("plan_binding_hash")
    if not safety["ok"]:
        missing.append("safe_managed_plan")
    if not autonomous_managed:
        missing.append("--autonomous-managed")
    if not env_ok:
        missing.append("VIBE_BEADS_LIVE_APPLY=1")
    if not beads_confirm:
        missing.append("--confirm-beads-live-apply")
    eligible = not missing
    return {
        "eligible": eligible,
        "option": "A",
        "missing": missing,
        "safety": safety,
        "product_ready": product_ready,
        "safe_task_convergence_allowed": safe_task_convergence_allowed,
        "task_readable": task_readable,
        "plan_binding_ok": plan_binding_ok,
        "autonomous_managed": autonomous_managed,
        "dual_gate_ok": bool(env_ok and beads_confirm),
    }


def autonomy_next_actions(plan: ApplyPlan, *, provider_name: str) -> list[dict[str, Any]]:
    """Deterministic next_actions (no ad hoc user Q&A wording)."""
    actions: list[dict[str, Any]] = []
    by = plan.counts_by_op_type
    safety = evaluate_managed_apply_safety(plan)

    actions.append(
        next_action(
            code="TASK_APPLY_DRY_RUN",
            command=f"vibe task apply --dry-run --json --provider {provider_name}",
            mutation=False,
            reason="Plan only; inspect plan_by_op_type and autonomy_policy",
        )
    )

    if safety["recognized_as_autonomous_managed"]:
        actions.append(
            next_action(
                code="AUTONOMOUS_MANAGED_APPLY",
                command=(
                    "VIBE_BEADS_LIVE_APPLY=1 vibe task apply --apply --json "
                    "--provider beads --autonomous-managed --confirm-beads-live-apply"
                ),
                mutation=True,
                reason=(
                    "Option A: safe managed create/update may proceed when knowledge is ready "
                    "and plan is safe (full product_ready not required solely for task-cache "
                    "convergence); temporary dual gate + --autonomous-managed still required "
                    "for live Beads"
                ),
            )
        )
        actions.append(
            next_action(
                code="TASK_APPLY_FAKE_SAFE_MANAGED",
                command="vibe task apply --apply --json --provider fake",
                mutation=True,
                reason="Local/fake path for tests without live Beads",
            )
        )

    if by.get("skip_unmanaged", 0):
        actions.append(
            next_action(
                code="SKIP_UNMANAGED",
                command="vibe task reconcile --dry-run --json --provider beads",
                mutation=False,
                reason="Unmanaged tasks are never auto-adopted; review skip_unmanaged ops",
            )
        )
    if by.get("skip_duplicate", 0) or by.get("skip_conflict", 0) or by.get(
        "blocked_repair_required", 0
    ):
        actions.append(
            next_action(
                code="REPAIR_PLAN_REQUIRED",
                command="vibe task apply --dry-run --json --provider beads",
                mutation=False,
                reason=(
                    "Duplicate/conflict requires deterministic repair-plan review; "
                    "do not ad hoc ask user; do not mutate unsafe items"
                ),
            )
        )
    if by.get("skip_delete_forbidden", 0):
        actions.append(
            next_action(
                code="DELETE_FORBIDDEN",
                command="vibe task apply --dry-run --json --provider beads",
                mutation=False,
                reason="Destructive delete remains forbidden by default",
            )
        )

    actions.append(
        next_action(
            code="LIVE_BEADS_OPTION_A_GATE",
            command="vibe integration status --json",
            mutation=False,
            reason=(
                "Option A keeps temporary dual gate; Option B would unlock from "
                "product_ready + safe-plan alone after stronger tests"
            ),
        )
    )
    return actions
