"""Phase 11B apply engine (fake provider mutation; beads dual-gated elsewhere)."""

from __future__ import annotations

from typing import Any, Literal

from vibe_control.json_envelope import next_action
from vibe_control.task.apply_models import ApplyPlan, ApplyResult, EXECUTABLE_OP_TYPES
from vibe_control.task.apply_plan import build_apply_plan, compute_plan_binding_hash
from vibe_control.task.autonomy import autonomy_next_actions
from vibe_control.task.models import ExpectedTask
from vibe_control.task.reconcile import reconcile_readonly


ApplyMode = Literal["dry_run", "apply"]


def _task_write_effect(op_type: str) -> dict[str, Any]:
    return {
        "kind": "task_write",
        "target": f"task.{op_type}",
        "status": "completed",
    }


def run_apply(
    *,
    expected: list[ExpectedTask],
    provider: Any,
    mode: ApplyMode,
    project_id: str,
    provider_name: str,
    warnings: list[str] | None = None,
    knowledge_readiness: dict[str, Any] | None = None,
    expect_plan_binding: str | None = None,
    beads_confirm: bool = False,
    completed_expected: list[ExpectedTask] | None = None,
) -> ApplyResult:
    """Reconcile then plan; mutate only when mode=apply and provider supports it."""
    warn = list(warnings or [])
    kr = dict(knowledge_readiness or {})
    provider_tasks = list(provider.list_tasks())
    report = reconcile_readonly(
        project_id=project_id,
        expected=expected,
        provider_tasks=provider_tasks,
        provider_kind=provider_name,
        warnings=warn,
    )
    plan = build_apply_plan(
        report,
        expected=expected,
        completed_expected=completed_expected,
        knowledge_readiness=kr,
    )
    current_binding = compute_plan_binding_hash(expected)

    if expect_plan_binding and expect_plan_binding != current_binding:
        return ApplyResult(
            ok=False,
            mode="blocked",
            mutation=False,
            provider=provider_name,
            project_id=project_id,
            plan=plan,
            warnings=warn,
            code="STALE_APPLY_PLAN",
            message="SSOT snapshot changed since plan binding; regenerate apply plan",
            effects=[],
            next_actions=[
                next_action(
                    code="REGENERATE_APPLY_PLAN",
                    command=f"vibe task apply --dry-run --json --provider {provider_name}",
                    mutation=False,
                    reason="Re-run dry-run after SSOT change",
                )
            ],
        )

    if mode == "dry_run":
        return ApplyResult(
            ok=True,
            mode="dry_run",
            mutation=False,
            provider=provider_name,
            project_id=project_id,
            plan=plan,
            warnings=warn,
            effects=[],
            next_actions=autonomy_next_actions(plan, provider_name=provider_name),
        )

    # apply mode — beads always blocked here unless somehow routed elsewhere with dual gates
    if provider_name != "fake":
        return ApplyResult(
            ok=False,
            mode="blocked",
            mutation=False,
            provider=provider_name,
            project_id=project_id,
            plan=plan,
            warnings=warn,
            effects=[],
            code="BEADS_LIVE_APPLY_BLOCKED",
            message=(
                "Real Beads apply remains under temporary dual gate "
                "(VIBE_BEADS_LIVE_APPLY + --confirm-beads-live-apply); "
                "product path does not execute live bd create/update in this baseline"
            ),
            next_actions=[
                next_action(
                    code="BEADS_LIVE_APPLY_BLOCKED",
                    command="vibe task apply --dry-run --json --provider beads",
                    mutation=False,
                    reason=(
                        "Live Beads mutation is temporary dual-gated; "
                        "use dry-run or fake provider; do not ask user per managed op"
                    ),
                )
            ],
        )

    completed_effects: list[dict[str, Any]] = []
    for op in plan.operations:
        if not op.executable or op.op_type not in EXECUTABLE_OP_TYPES:
            continue
        try:
            if op.op_type == "create_managed":
                provider.create_managed(title=op.title, description=op.description or "")
            elif op.op_type == "update_managed":
                if not op.provider_task_id:
                    warn.append(f"skip update without provider_task_id for {op.managed_key}")
                    continue
                provider.update_managed(
                    provider_task_id=op.provider_task_id,
                    title=op.title,
                    description=op.description or "",
                )
            else:
                continue
        except Exception as exc:
            result_plan = ApplyPlan(
                operations=list(plan.operations),
                expected_count=report.expected_count,
                actual_count=len(provider.list_tasks()),
                plan_binding_hash=plan.plan_binding_hash,
                ssot_snapshot_identity=dict(plan.ssot_snapshot_identity),
                knowledge_readiness=dict(plan.knowledge_readiness),
                autonomy_policy=dict(plan.autonomy_policy),
            )
            return ApplyResult(
                ok=False,
                mode="blocked",
                mutation=bool(completed_effects),
                provider=provider_name,
                project_id=project_id,
                plan=result_plan,
                warnings=warn,
                effects=list(completed_effects),
                code="TASK_APPLY_PARTIAL_FAILURE",
                message=f"Task apply failed after partial writes: {exc}",
                next_actions=[
                    next_action(
                        code="TASK_RECONCILE_AFTER_PARTIAL_APPLY",
                        command=f"vibe task apply --dry-run --json --provider {provider_name}",
                        mutation=False,
                        reason="Reconcile after partial fake apply failure",
                    )
                ],
            )
        # Record completed effect before the next provider call.
        completed_effects.append(_task_write_effect(op.op_type))
        op.mutation = True

    result_plan = ApplyPlan(
        operations=list(plan.operations),
        expected_count=report.expected_count,
        actual_count=len(provider.list_tasks()),
        plan_binding_hash=plan.plan_binding_hash,
        ssot_snapshot_identity=dict(plan.ssot_snapshot_identity),
        knowledge_readiness=dict(plan.knowledge_readiness),
        autonomy_policy=dict(plan.autonomy_policy),
    )

    return ApplyResult(
        ok=True,
        mode="applied",
        mutation=bool(completed_effects),
        provider=provider_name,
        project_id=project_id,
        plan=result_plan,
        warnings=warn,
        effects=list(completed_effects),
        next_actions=[
            next_action(
                code="TASK_APPLY_DONE",
                command="vibe task apply --dry-run --json --provider fake",
                mutation=False,
                reason="Re-run dry-run to confirm fake provider state",
            )
        ],
    )
