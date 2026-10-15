"""CLI orchestration for Phase 12 implementation prompt (readonly)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from vibe_control.config import ConfigError, load_config
from vibe_control.implementation.prompt import PromptError, build_implementation_prompt, resolve_expected_task
from vibe_control.json_envelope import failure_envelope, next_action
from vibe_control.task.reconcile_cli import run_task_reconcile_dry_run


def _looks_like_provider_id(selector: str) -> bool:
    s = selector.strip()
    if s.startswith("sha256:"):
        return False
    if s.startswith("roadmap."):
        return False
    return bool(s)


def _binding_from_reconcile(
    *,
    repo_root: Path,
    selector: str,
) -> tuple[str | None, str | None, dict[str, int] | None]:
    """Return (ssot_anchor_or_managed_key, provider_task_id, counts) when selector is a binding id."""
    env = run_task_reconcile_dry_run(repo_root=repo_root, provider_name="beads")
    data = env.get("data") or {}
    counts = data.get("counts") if isinstance(data.get("counts"), dict) else None
    for category in ("matched", "stale", "missing", "duplicate", "conflict"):
        for item in data.get(category) or []:
            if not isinstance(item, dict):
                continue
            ids = item.get("provider_task_ids") or []
            if selector in ids:
                exp = item.get("expected") or {}
                key = exp.get("managed_key") or exp.get("ssot_anchor")
                return key, selector, counts  # type: ignore[return-value]
    return None, None, counts


def run_implementation_prompt(
    *,
    repo_root: Path,
    task_selector: str,
    include_provider_probe: bool = True,
) -> dict[str, Any]:
    root = repo_root
    try:
        config = load_config(root)
        project_id = config.project_id
    except ConfigError as exc:
        return failure_envelope(
            command="vibe implementation prompt",
            code=exc.code or "CONFIG_INVALID",
            message=exc.message,
            next_actions=[
                next_action(
                    code="CONFIG_REQUIRED",
                    command="vibe config validate --json",
                    mutation=False,
                    reason="Load project config before implementation prompt",
                )
            ],
        )

    readiness: dict[str, Any] = {
        "product_ready": None,
        "sync_state": None,
        "provider_ask_clean": None,
        "blocked_reasons": [],
        "probed": False,
    }
    task_cache_from_probe: dict[str, Any] = {}
    reconcile_counts = {
        "matched": 0,
        "missing": 0,
        "stale": 0,
        "duplicate": 0,
        "conflict": 0,
        "unmanaged": 0,
    }
    apply_plan_counts = {"create": 0, "update": 0, "skip": 0, "blocked": 0}

    from vibe_control.grill_session import active_in_progress

    grill = active_in_progress(root)
    if grill is not None:
        return failure_envelope(
            command="vibe implementation prompt",
            code="SELF_GRILL_IN_PROGRESS",
            message=(
                f"Self-grill session {grill.get('grill_id')} is IN_PROGRESS "
                f"(round_id={grill.get('round_id')}); close it before implementation prompt"
            ),
            details={
                "grill_id": grill.get("grill_id"),
                "round_id": grill.get("round_id"),
                "loop_status": grill.get("loop_status"),
                "thesis": grill.get("thesis"),
            },
            project_id=project_id,
            next_actions=[
                next_action(
                    code="GRILL_STATUS",
                    command="vibe grill status --json",
                    mutation=False,
                    reason="Inspect active self-grill session",
                ),
                next_action(
                    code="GRILL_CHECKPOINT",
                    command="vibe grill checkpoint --json",
                    mutation=True,
                    reason="Advance round_id while still IN_PROGRESS",
                ),
                next_action(
                    code="GRILL_CLOSE_EXHAUSTED",
                    command="vibe grill close --status EXHAUSTED --json",
                    mutation=True,
                    reason="End grill when frontier is empty",
                ),
                next_action(
                    code="KNOWLEDGE_DOCTOR",
                    command="vibe knowledge doctor --json",
                    mutation=False,
                    reason="Readonly Knowledge probe while grilling",
                ),
            ],
        )

    if include_provider_probe:
        try:
            from vibe_control.product_readiness import evaluate_product_readiness

            probe = evaluate_product_readiness(repo_root=root, probe=True)
            readiness = {
                "product_ready": probe.product_ready,
                "sync_state": probe.sync_state,
                "provider_ask_clean": probe.provider_ask_clean,
                "blocked_reasons": list(probe.blocked_reasons),
                "knowledge_available": probe.knowledge_available,
                "knowledge_target_ok": probe.knowledge_target_ok,
                "config_ok": bool(getattr(probe, "config_ok", True)),
                "components": dict(getattr(probe, "components", None) or {}),
                "probed": True,
            }
            task_cache_from_probe = dict(probe.task_cache or {})
            if isinstance(task_cache_from_probe.get("reconcile_counts"), dict):
                reconcile_counts = {**reconcile_counts, **task_cache_from_probe["reconcile_counts"]}
            if isinstance(task_cache_from_probe.get("apply_plan_counts"), dict):
                apply_plan_counts = {**apply_plan_counts, **task_cache_from_probe["apply_plan_counts"]}
        except Exception as exc:  # noqa: BLE001 — prompt remains useful without probe
            readiness["probed"] = False
            readiness["blocked_reasons"] = [f"readiness_probe_skipped: {exc}"]

    provider_task_id: str | None = None
    selector = task_selector.strip()

    try:
        resolve_expected_task(repo_root=root, project_id=project_id, task_selector=selector)
        resolved_selector = selector
    except PromptError:
        if not _looks_like_provider_id(selector):
            return failure_envelope(
                command="vibe implementation prompt",
                code="TASK_SELECTOR_NOT_FOUND",
                message=f"No expected task matches selector: {selector}",
                project_id=project_id,
                next_actions=[
                    next_action(
                        code="TASK_RECONCILE",
                        command="vibe task reconcile --dry-run --json --provider beads",
                        mutation=False,
                        reason="List matched managed tasks and anchors",
                    )
                ],
            )
        if not include_provider_probe:
            return failure_envelope(
                command="vibe implementation prompt",
                code="TASK_SELECTOR_NOT_FOUND",
                message=(
                    f"Provider task id lookup requires provider probe; "
                    f"selector not an expected anchor/managed_key: {selector}"
                ),
                project_id=project_id,
            )
        key, provider_task_id, counts = _binding_from_reconcile(repo_root=root, selector=selector)
        if counts:
            reconcile_counts = {**reconcile_counts, **counts}
        if not key:
            return failure_envelope(
                command="vibe implementation prompt",
                code="TASK_SELECTOR_NOT_FOUND",
                message=f"Provider task id not bound to an expected managed task: {selector}",
                project_id=project_id,
            )
        resolved_selector = key
    else:
        if include_provider_probe and not task_cache_from_probe:
            try:
                env_b = run_task_reconcile_dry_run(repo_root=root, provider_name="beads")
                data_b = env_b.get("data") or {}
                if isinstance(data_b.get("counts"), dict):
                    reconcile_counts = {**reconcile_counts, **data_b["counts"]}
                for item in data_b.get("matched") or []:
                    exp = (item or {}).get("expected") or {}
                    if (
                        exp.get("ssot_anchor") == resolved_selector
                        or exp.get("managed_key") == resolved_selector
                    ):
                        ids = item.get("provider_task_ids") or []
                        if ids:
                            provider_task_id = ids[0]
                        break
            except Exception:  # noqa: BLE001
                pass

    if include_provider_probe and not task_cache_from_probe:
        try:
            from vibe_control.task.apply_cli import run_task_apply

            apply_env = run_task_apply(
                repo_root=root,
                mode="dry_run",
                provider_name="fake",
                strict_providers=False,
            )
            plan = ((apply_env.get("data") or {}).get("plan")) or {}
            if isinstance(plan, dict):
                apply_plan_counts = {**apply_plan_counts, **plan}
        except Exception:  # noqa: BLE001
            pass

    knowledge_readiness = {
        "sync_state": readiness.get("sync_state"),
        "provider_ask_clean": readiness.get("provider_ask_clean"),
        "available": readiness.get("knowledge_available"),
        "target_ok": readiness.get("knowledge_target_ok"),
    }
    provider_sync_required = bool(
        readiness.get("product_ready") is False
        and readiness.get("sync_state") in ("drift", "pending", "unavailable")
    )
    try:
        return build_implementation_prompt(
            repo_root=root,
            task_selector=resolved_selector,
            project_id=project_id,
            readiness_summary=readiness,
            knowledge_readiness=knowledge_readiness,
            reconcile_counts=reconcile_counts,
            apply_plan_counts=apply_plan_counts,
            provider_task_id=provider_task_id,
            redact_provider_ids=True,
            provider_sync_required=provider_sync_required,
            task_cache=task_cache_from_probe or None,
        )
    except PromptError as exc:
        return failure_envelope(
            command="vibe implementation prompt",
            code=exc.code,
            message=exc.message,
            details=exc.details,
            project_id=project_id,
        )
