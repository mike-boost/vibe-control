"""Local embedded ephemeral task cache evaluation (default task mode)."""

from __future__ import annotations

from typing import Any

from vibe_control.json_envelope import next_action

DEFAULT_TASK_CACHE_MODE = "local_embedded_ephemeral"

POLLUTION_KEYS = ("duplicate", "conflict", "unmanaged")
DRIFT_KEYS = ("missing", "stale")


def evaluate_task_cache_state(
    *,
    reconcile_counts: dict[str, Any] | None = None,
    apply_plan_counts: dict[str, Any] | None = None,
    knowledge_ready: bool = False,
    task_available: bool = False,
    task_readable: bool = False,
    mode: str = DEFAULT_TASK_CACHE_MODE,
) -> dict[str, Any]:
    """Evaluate local ephemeral task cache currentness and next actions.

    Pure local contract helper. Does not mutate providers.
    """
    counts = {
        "matched": int((reconcile_counts or {}).get("matched") or 0),
        "missing": int((reconcile_counts or {}).get("missing") or 0),
        "stale": int((reconcile_counts or {}).get("stale") or 0),
        "duplicate": int((reconcile_counts or {}).get("duplicate") or 0),
        "conflict": int((reconcile_counts or {}).get("conflict") or 0),
        "unmanaged": int((reconcile_counts or {}).get("unmanaged") or 0),
    }
    plan = {
        "create": int((apply_plan_counts or {}).get("create") or 0),
        "update": int((apply_plan_counts or {}).get("update") or 0),
        "skip": int((apply_plan_counts or {}).get("skip") or 0),
        "blocked": int((apply_plan_counts or {}).get("blocked") or 0),
    }

    pollution = sum(counts[k] for k in POLLUTION_KEYS) > 0
    drift = sum(counts[k] for k in DRIFT_KEYS) > 0
    apply_pending = plan["create"] > 0 or plan["update"] > 0 or plan["blocked"] > 0

    task_cache_current = (
        task_available
        and task_readable
        and not pollution
        and not drift
        and plan["create"] == 0
        and plan["update"] == 0
        and plan["blocked"] == 0
    )

    # Safe create/update convergence: knowledge ready + readable + only missing/stale
    # (breaks product_ready circular dependency for Option A managed apply).
    safe_task_convergence_allowed = bool(
        knowledge_ready
        and task_available
        and task_readable
        and not pollution
        and (drift or plan["create"] > 0 or plan["update"] > 0)
        and plan["blocked"] == 0
    )

    task_cache_reset_required = bool(pollution and mode == DEFAULT_TASK_CACHE_MODE)
    task_cache_action_required = not task_cache_current

    warnings: list[str] = []
    next_actions: list[dict[str, Any]] = []

    if not task_available or not task_readable:
        warnings.append("task_provider_not_ready_for_cache")
        next_actions.append(
            next_action(
                code="TASK_PROVIDER_DIAGNOSIS",
                command="vibe task doctor --json",
                mutation=False,
                reason="Task provider must be available/readable before cache convergence",
            )
        )
    elif task_cache_reset_required:
        warnings.append("task_cache_pollution_reset_required")
        next_actions.append(
            next_action(
                code="TASK_CACHE_RESET_DRY_RUN",
                command="vibe task cache reset --dry-run --json",
                mutation=False,
                reason=(
                    "Local ephemeral cache pollution (unmanaged/duplicate/conflict); "
                    "prefer whole-cache reset/regenerate — not ad hoc repair or adoption"
                ),
            )
        )
    elif safe_task_convergence_allowed:
        warnings.append("task_cache_not_current_safe_convergence")
        next_actions.append(
            next_action(
                code="TASK_CACHE_CONVERGE_MANAGED",
                command=(
                    "vibe task apply --dry-run --json --provider beads"
                ),
                mutation=False,
                reason="Preview safe managed create/update to converge local task cache",
            )
        )
        next_actions.append(
            next_action(
                code="TASK_CACHE_CONVERGE_APPLY",
                command=(
                    "VIBE_BEADS_LIVE_APPLY=1 vibe task apply --apply --json "
                    "--provider beads --autonomous-managed --confirm-beads-live-apply"
                ),
                mutation=True,
                reason=(
                    "Safe managed create/update may proceed when knowledge is ready "
                    "(does not require full product_ready / task_cache_current)"
                ),
            )
        )
    elif not task_cache_current:
        warnings.append("task_cache_not_current")
        next_actions.append(
            next_action(
                code="TASK_RECONCILE_READONLY",
                command="vibe task reconcile --dry-run --json --provider beads",
                mutation=False,
                reason="Inspect task cache reconcile counts before implementation",
            )
        )

    return {
        "task_cache_mode": mode,
        "task_cache_current": task_cache_current,
        "task_cache_action_required": task_cache_action_required,
        "safe_task_convergence_allowed": safe_task_convergence_allowed,
        "task_cache_reset_required": task_cache_reset_required,
        "reconcile_counts": counts,
        "apply_plan_counts": plan,
        "apply_pending": apply_pending,
        "mutation": False,
        "warnings": warnings,
        "next_actions": next_actions,
        "rules": {
            "default_mode": DEFAULT_TASK_CACHE_MODE,
            "beads_is_local_ephemeral_cache": True,
            "beads_not_repo_truth": True,
            "beads_not_github_collaboration_data": True,
            "team_shared_mode_out_of_scope": True,
            "stale_is_not_soft_debt": True,
            "pollution_prefers_reset_regenerate": True,
        },
    }


def knowledge_half_ready_from_probe(probe: Any) -> bool:
    return bool(
        getattr(probe, "knowledge_available", False)
        and getattr(probe, "knowledge_target_ok", False)
        and getattr(probe, "sync_state", "") == "synced"
        and getattr(probe, "provider_ask_clean", False)
    )
