"""Phase 11B task apply CLI orchestration with knowledge coordination.

Option A autonomous managed Beads apply:
- Requires product_ready, safe managed plan, --autonomous-managed,
  VIBE_BEADS_LIVE_APPLY=1, and --confirm-beads-live-apply.
- Default gates never live-mutate Beads.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from vibe_control.config import ConfigError, load_config
from vibe_control.json_envelope import attach_operation_result, next_action
from vibe_control.product_readiness import (
    ProviderProbeResult,
    evaluate_product_readiness,
    readiness_next_actions,
)
from vibe_control.task.apply_engine import run_apply
from vibe_control.task.apply_models import ApplyPlan
from vibe_control.task.autonomy import (
    autonomy_next_actions,
    evaluate_autonomous_managed_eligibility,
    evaluate_managed_apply_safety,
)
from vibe_control.task.beads_apply import (
    AUTONOMOUS_MANAGED_FLAG,
    CONFIRM_CLI_FLAG,
    LIVE_APPLY_ENV,
    BeadsApplyBlocked,
    beads_live_apply_env_ok,
    execute_beads_apply_guarded,
    live_apply_gates_satisfied,
    subprocess_bd_runner,
)
from vibe_control.task.beads_readonly import BeadsReadonlyProvider
from vibe_control.task.projection import (
    project_completed_expected_tasks,
    project_slice1_expected_tasks,
)
from vibe_control.task.provider import FakeTaskProvider
from vibe_control.task.reconcile_cli import resolve_task_provider

ApplyCliMode = Literal["dry_run", "apply"]


def _finish_apply(
    envelope: dict[str, Any],
    *,
    mutation_intent: bool,
    effects: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Attach operation evidence; keep nested data.mutation aliases aligned."""
    out = attach_operation_result(
        envelope,
        mutation_intent=mutation_intent,
        effects=effects or [],
    )
    performed = bool(out["mutation_performed"])
    data = out.get("data")
    if isinstance(data, dict):
        data["mutation"] = performed
    err = out.get("error")
    if isinstance(err, dict):
        details = err.get("details")
        if isinstance(details, dict) and "mutation" in details:
            details["mutation"] = performed
    return out


def build_unavailable_apply_envelope(
    *,
    project_id: str,
    provider: str,
    reason: str,
    mutation_intent: bool = False,
) -> dict[str, Any]:
    plan = ApplyPlan(operations=[], expected_count=0, actual_count=0)
    data = {
        **plan.to_dict(),
        "provider_available": False,
        "reason": reason,
        "mutation": False,
    }
    return _finish_apply(
        {
            "ok": True,
            "command": "vibe task apply",
            "project_id": project_id,
            "mode": "unavailable",
            "provider": provider,
            "data": data,
            "warnings": [reason],
            "next_actions": [
                next_action(
                    code="BEADS_PROVIDER_UNAVAILABLE",
                    command="vibe task install-guide --json",
                    mutation=False,
                    reason="Install/configure Beads, then re-run apply dry-run",
                ),
                next_action(
                    code="TASK_APPLY_USE_FAKE",
                    command="vibe task apply --dry-run --json --provider fake",
                    mutation=False,
                    reason="Use fake provider for local plan verification",
                ),
                next_action(
                    code="TASK_PROVIDER_DIAGNOSIS",
                    command="vibe integration status --json",
                    mutation=False,
                    reason="Diagnose provider readiness; unavailable ≠ empty inventory",
                ),
            ],
        },
        mutation_intent=mutation_intent,
        effects=[],
    )


def _knowledge_gate_summary(probe: ProviderProbeResult | None, *, checked: bool, skipped: bool) -> dict[str, Any]:
    if skipped:
        return {
            "checked": False,
            "skipped": True,
            "reason": "strict provider-backed gate disabled (local/fake mode)",
        }
    if probe is None:
        return {"checked": checked, "skipped": False}
    return {
        "checked": checked,
        "skipped": False,
        "sync_state": probe.sync_state,
        "provider_ask_clean": probe.provider_ask_clean,
        "evidence_hash": probe.evidence_hash,
        "product_ready": probe.product_ready,
        "blocked_reasons": list(probe.blocked_reasons),
        "task_readable": probe.task_readable,
    }


def _blocked_beads(
    *,
    project_id: str,
    plan: ApplyPlan,
    code: str,
    message: str,
    details: dict[str, Any],
    warnings: list[str],
    kr_summary: dict[str, Any],
) -> dict[str, Any]:
    """Apply-path block before/without completed writes (intent=true, no effects)."""
    details_out = dict(details)
    details_out["mutation"] = False
    data = {
        **plan.to_dict(),
        "knowledge_readiness": kr_summary,
        "eligibility": details.get("eligibility"),
        "mutation": False,
    }
    return _finish_apply(
        {
            "ok": False,
            "command": "vibe task apply",
            "project_id": project_id,
            "mode": "blocked",
            "provider": "beads",
            "error": {"code": code, "message": message, "details": details_out},
            "data": data,
            "warnings": warnings,
            "next_actions": autonomy_next_actions(plan, provider_name="beads"),
        },
        mutation_intent=True,
        effects=[],
    )


def run_task_apply(
    *,
    repo_root: Path,
    mode: ApplyCliMode,
    provider_name: str | None = None,
    provider: Any | None = None,
    strict_providers: bool | None = None,
    expect_plan_binding: str | None = None,
    beads_confirm: bool = False,
    autonomous_managed: bool = False,
    knowledge_probe: ProviderProbeResult | None = None,
    skip_knowledge_probe: bool = False,
    beads_runner: Any | None = None,
) -> dict[str, Any]:
    root = repo_root
    warnings: list[str] = []
    mutation_intent = mode == "apply"
    try:
        config = load_config(root)
        project_id = config.project_id
        config_provider = str((config.tasks or {}).get("provider") or "") or None
    except ConfigError as exc:
        return _finish_apply(
            {
                "ok": False,
                "command": "vibe task apply",
                "code": exc.code or "CONFIG_INVALID",
                "message": exc.message,
                "project_id": None,
                "mode": "unavailable",
                "provider": None,
                "data": {"mutation": False},
                "warnings": [],
                "next_actions": [
                    next_action(
                        code="CONFIG_REQUIRED",
                        command="vibe config validate --json",
                        mutation=False,
                        reason="Load project config before task apply",
                    )
                ],
            },
            mutation_intent=mutation_intent,
            effects=[],
        )

    expected = project_slice1_expected_tasks(project_id=project_id, repo_root=root)
    completed_expected = project_completed_expected_tasks(project_id=project_id, repo_root=root)

    if provider is not None:
        use_provider = provider
        # Explicit CLI/provider_name wins so tests can inject FakeTaskProvider inventory
        # while exercising the beads apply policy path.
        provider_kind = str(provider_name or getattr(provider, "name", "unknown"))
    else:
        provider_kind, use_provider, resolve_warnings = resolve_task_provider(
            provider_name=provider_name,
            config_provider=config_provider,
        )
        warnings.extend(resolve_warnings)

    if strict_providers is None:
        strict = provider_kind == "beads"
    else:
        strict = bool(strict_providers)

    knowledge_checked = False
    knowledge_skipped = False
    probe = knowledge_probe

    if not strict:
        knowledge_skipped = True
        if probe is not None:
            knowledge_checked = True
            knowledge_skipped = False
    else:
        if probe is None and not skip_knowledge_probe:
            probe = evaluate_product_readiness(repo_root=root, probe=True)
        knowledge_checked = True
        if probe is not None and (
            not probe.knowledge_available
            or probe.sync_state
            in {"unavailable", "drift", "pending", "receipt_missing", "target_mismatch"}
            or not probe.provider_ask_clean
        ):
            kr = _knowledge_gate_summary(probe, checked=True, skipped=False)
            return _finish_apply(
                {
                    "ok": False,
                    "command": "vibe task apply",
                    "project_id": project_id,
                    "mode": "blocked",
                    "provider": provider_kind,
                    "error": {
                        "code": "KNOWLEDGE_PROVIDER_NOT_READY",
                        "message": (
                            "Provider-backed task apply blocked: knowledge provider "
                            "unavailable, unsynced, or ask hygiene not clean"
                        ),
                        "details": {"knowledge_readiness": kr, "mutation": False},
                    },
                    "data": {
                        "expected_count": len(expected),
                        "actual_count": 0,
                        "plan": {"create": 0, "update": 0, "skip": 0, "blocked": 0},
                        "operations": [],
                        "knowledge_readiness": kr,
                        "ssot_snapshot_identity": {
                            "expected_count": len(expected),
                        },
                        "mutation": False,
                    },
                    "warnings": list(probe.warnings) + list(warnings),
                    "next_actions": readiness_next_actions(probe),
                },
                mutation_intent=mutation_intent,
                effects=[],
            )

    if isinstance(use_provider, BeadsReadonlyProvider):
        _ = use_provider.list_tasks()
        provider_available = bool(use_provider.available)
        warnings.extend(list(use_provider.warnings or []))
    elif provider_kind == "fake" and provider is None:
        provider_available = True
        warnings.append("Using FakeTaskProvider (in-memory); safe for local dry-run/apply tests")
    else:
        provider_available = True

    kr_summary = _knowledge_gate_summary(
        probe, checked=knowledge_checked, skipped=knowledge_skipped
    )

    if not provider_available:
        env = build_unavailable_apply_envelope(
            project_id=project_id,
            provider=provider_kind,
            reason="Task provider unavailable; apply skipped (not a real empty Beads inventory)",
            mutation_intent=mutation_intent,
        )
        env["data"]["expected_count"] = len(expected)
        env["data"]["knowledge_readiness"] = kr_summary
        env["warnings"] = list(dict.fromkeys([*warnings, *env["warnings"]]))
        return env

    if mode == "apply" and provider_kind == "beads":
        result = run_apply(
            expected=expected,
            provider=use_provider,
            mode="dry_run",  # plan against current inventory; live path mutates below
            project_id=project_id,
            provider_name="beads",
            warnings=warnings,
            knowledge_readiness=kr_summary,
            expect_plan_binding=expect_plan_binding,
            beads_confirm=beads_confirm,
            completed_expected=completed_expected,
        )
        plan = result.plan
        if result.mode == "blocked" and result.code == "STALE_APPLY_PLAN":
            return _blocked_beads(
                project_id=project_id,
                plan=plan,
                code="STALE_APPLY_PLAN",
                message=result.message or "SSOT snapshot changed since plan binding",
                details={"plan_binding_ok": False},
                warnings=warnings,
                kr_summary=kr_summary,
            )

        product_ready = bool(probe.product_ready) if probe is not None else False
        task_readable = bool(probe.task_readable) if probe is not None else provider_available
        from vibe_control.task.cache import knowledge_half_ready_from_probe

        knowledge_half = (
            knowledge_half_ready_from_probe(probe) if probe is not None else False
        )
        by = plan.counts_by_op_type
        pollution = (
            int(by.get("skip_unmanaged", 0))
            + int(by.get("skip_duplicate", 0))
            + int(by.get("skip_conflict", 0))
            + int(by.get("blocked_repair_required", 0))
        )
        safety_preview = evaluate_managed_apply_safety(plan)
        safe_task_convergence_allowed = bool(
            knowledge_half
            and task_readable
            and safety_preview["ok"]
            and pollution == 0
            and (
                int(by.get("create_managed", 0)) + int(by.get("update_managed", 0))
            )
            > 0
        )
        if probe is not None and not product_ready and not safe_task_convergence_allowed:
            return _blocked_beads(
                project_id=project_id,
                plan=plan,
                code="PRODUCT_NOT_READY",
                message=(
                    "Real Beads apply blocked: product_ready=false and "
                    "safe_task_convergence_allowed=false"
                ),
                details={
                    "product_ready": False,
                    "safe_task_convergence_allowed": False,
                    "blocked_reasons": list(probe.blocked_reasons),
                    "eligibility": evaluate_autonomous_managed_eligibility(
                        plan,
                        product_ready=False,
                        task_readable=task_readable,
                        beads_confirm=beads_confirm,
                        env_ok=beads_live_apply_env_ok(),
                        autonomous_managed=autonomous_managed,
                        safe_task_convergence_allowed=False,
                    ),
                },
                warnings=warnings + list(probe.warnings),
                kr_summary=kr_summary,
            )

        safety = safety_preview
        if not safety["ok"]:
            return _blocked_beads(
                project_id=project_id,
                plan=plan,
                code="UNSAFE_MANAGED_PLAN",
                message=(
                    "Real Beads apply blocked: executable ops are not exclusively "
                    "safe Vibe-managed create/update"
                ),
                details={"safety": safety},
                warnings=warnings,
                kr_summary=kr_summary,
            )

        eligibility = evaluate_autonomous_managed_eligibility(
            plan,
            product_ready=product_ready,
            task_readable=task_readable,
            beads_confirm=beads_confirm,
            env_ok=beads_live_apply_env_ok(),
            autonomous_managed=autonomous_managed,
            plan_binding_ok=True,
            safe_task_convergence_allowed=safe_task_convergence_allowed,
        )
        plan.autonomy_policy = {
            **plan.autonomy_policy,
            "eligibility": eligibility,
            "option": "A",
        }

        if not eligibility["eligible"]:
            return _blocked_beads(
                project_id=project_id,
                plan=plan,
                code="BEADS_LIVE_APPLY_BLOCKED",
                message=(
                    "Option A live Beads apply blocked; missing: "
                    + ", ".join(eligibility["missing"])
                ),
                details={
                    "env_gate": LIVE_APPLY_ENV,
                    "confirm_flag": CONFIRM_CLI_FLAG,
                    "autonomous_managed_flag": AUTONOMOUS_MANAGED_FLAG,
                    "gates_satisfied": live_apply_gates_satisfied(confirm=beads_confirm),
                    "live_execution": False,
                    "eligibility": eligibility,
                    "option": "A",
                    "option_b_delta": (
                        "Option B would remove dual gate after stronger tests; "
                        "unlock from product_ready + safe-plan alone"
                    ),
                },
                warnings=warnings,
                kr_summary=kr_summary,
            )

        # Eligible: execute live create/update via verified argv builders only.
        runner = beads_runner or subprocess_bd_runner
        try:
            recorded = execute_beads_apply_guarded(
                plan.operations,
                runner=runner,
                confirm=True,
                silent_create=True,
            )
        except BeadsApplyBlocked as exc:
            return _blocked_beads(
                project_id=project_id,
                plan=plan,
                code=exc.code,
                message=exc.message,
                details=dict(exc.details),
                warnings=warnings,
                kr_summary=kr_summary,
            )

        # Completed effects only (returncode==0 / successful write).
        completed_effects = [
            r["effect"] for r in recorded if isinstance(r.get("effect"), dict)
        ]
        failed = [r for r in recorded if isinstance(r.get("returncode"), int) and r["returncode"] != 0]
        envelope: dict[str, Any] = {
            "ok": len(failed) == 0,
            "command": "vibe task apply",
            "project_id": project_id,
            "mode": "applied" if not failed else "blocked",
            "provider": "beads",
            "data": {
                **plan.to_dict(redact_provider_ids=True),
                "knowledge_readiness": kr_summary,
                "eligibility": eligibility,
                "live_results": [
                    {
                        "op_type": r.get("op_type"),
                        "ssot_anchor": r.get("ssot_anchor"),
                        "managed_key": r.get("managed_key"),
                        "argv_verb": r.get("argv_verb"),
                        "returncode": r.get("returncode"),
                        "provider_task_id_hash": r.get("provider_task_id_hash"),
                        # Raw provider ids included for owner report; redacted in plan ops.
                        "provider_task_id": r.get("provider_task_id"),
                    }
                    for r in recorded
                ],
                "mutation": bool(completed_effects),
            },
            "warnings": warnings,
            "next_actions": [
                next_action(
                    code="TASK_RECONCILE_AFTER_APPLY",
                    command="vibe task reconcile --dry-run --json --provider beads",
                    mutation=False,
                    reason="Verify managed tasks matched after autonomous managed apply",
                )
            ],
        }
        if failed:
            envelope["error"] = {
                "code": "BEADS_LIVE_APPLY_PARTIAL_FAILURE",
                "message": "One or more live Beads operations failed",
                "details": {
                    "failed_count": len(failed),
                    "mutation": bool(completed_effects),
                },
            }
        return _finish_apply(
            envelope,
            mutation_intent=True,
            effects=completed_effects,
        )

    result = run_apply(
        expected=expected,
        provider=use_provider,
        mode=mode,
        project_id=project_id,
        provider_name=provider_kind,
        warnings=warnings,
        knowledge_readiness=kr_summary,
        expect_plan_binding=expect_plan_binding,
        beads_confirm=beads_confirm,
        completed_expected=completed_expected,
    )
    return result.to_envelope()
