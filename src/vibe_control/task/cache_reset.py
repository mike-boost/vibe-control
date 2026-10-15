"""Local embedded ephemeral task cache reset/regenerate."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Any

from vibe_control.config import ConfigError, load_config
from vibe_control.json_envelope import (
    attach_operation_result,
    failure_envelope,
    next_action,
    success_envelope,
)
from vibe_control.task.beads_apply import (
    build_bd_create_argv,
    build_managed_metadata,
    parse_bd_create_id,
)
from vibe_control.task.beads_cache_reset import (
    BeadsCacheResetError,
    classify_vibe_managed_tasks,
    clear_vibe_managed_beads_cache,
    redact_managed_rows,
    subprocess_bd_cache_runner,
)
from vibe_control.task.beads_readonly import BeadsReadonlyProvider
from vibe_control.task.cache import DEFAULT_TASK_CACHE_MODE
from vibe_control.task.marker import marker_from_expected, render_marker
from vibe_control.task.projection import project_actionable_expected_tasks
from vibe_control.task.provider import FakeTaskProvider
from vibe_control.task.apply_models import ApplyOperation


def _id_hash(provider_task_id: str | None) -> str | None:
    if not provider_task_id:
        return None
    digest = hashlib.sha256(provider_task_id.encode("utf-8")).hexdigest()[:12]
    return f"sha256:{digest}"


def _cache_reset_effect() -> dict[str, Any]:
    return {
        "kind": "task_write",
        "target": "task.cache_reset",
        "status": "completed",
    }


def _task_create_effect() -> dict[str, Any]:
    return {
        "kind": "task_write",
        "target": "task.create_managed",
        "status": "completed",
    }


def _finish_cache_reset(
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


def _unsupported_mode(mode: str, *, mutation_intent: bool) -> dict[str, Any]:
    return _finish_cache_reset(
        failure_envelope(
            command="vibe task cache reset",
            code="TASK_CACHE_MODE_UNSUPPORTED",
            message=f"Only {DEFAULT_TASK_CACHE_MODE} is supported; got {mode!r}",
            next_actions=[
                next_action(
                    code="USE_LOCAL_EPHEMERAL_MODE",
                    command="vibe task cache reset --dry-run --json --provider beads",
                    mutation=False,
                    reason="Team/shared/server modes are out of current scope",
                )
            ],
        ),
        mutation_intent=mutation_intent,
        effects=[],
    )


def _plan_payload(
    *,
    mode: str,
    provider_name: str,
    expected: list[Any],
    existing_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "mode": mode,
        "task_cache_mode": mode,
        "reset_scope": "vibe_managed_local_ephemeral_cache",
        "reset_kind": "full_vibe_namespace_reset",
        "clear_cache": True,
        "clear_record_count": len(existing_rows),
        "clear_anchors": [r.get("ssot_anchor") for r in existing_rows],
        "clear_managed_keys": [r.get("managed_key") for r in existing_rows],
        "clear_records": redact_managed_rows(existing_rows),
        "regenerate_managed_count": len(expected),
        "regenerate_anchors": [t.ssot_anchor for t in expected],
        "provider": provider_name,
        "operation_type": "cache_reset_regenerate",
    }


def _inventory_existing(*, provider_name: str, provider: Any | None) -> list[dict[str, Any]]:
    if provider is not None and hasattr(provider, "list_tasks"):
        tasks = list(provider.list_tasks())
        return classify_vibe_managed_tasks(tasks)
    if provider_name == "fake":
        return []
    if provider_name == "beads":
        readonly = BeadsReadonlyProvider()
        tasks = list(readonly.list_tasks())
        if not readonly.available:
            raise BeadsCacheResetError(
                "BEADS_UNAVAILABLE",
                readonly.last_error or "Beads readonly list unavailable",
            )
        return classify_vibe_managed_tasks(tasks)
    return []


def _regenerate_fake_after_clear(
    expected: list[Any],
    provider: FakeTaskProvider,
    *,
    completed_effects: list[dict[str, Any]],
) -> int:
    """Create managed tasks after cache clear; record each successful write."""
    created = 0
    for task in expected:
        description = render_marker(
            marker_from_expected(
                project_id=task.project_id,
                ssot_id=task.ssot_id,
                ssot_path=task.ssot_path,
                ssot_anchor=task.ssot_anchor,
                task_kind=task.task_kind,
                ssot_snapshot_hash=task.ssot_snapshot_hash,
                source_item_hash=task.source_item_hash,
            )
        )
        provider.create_managed(title=task.title, description=description)
        # Record each successful create before the next provider call.
        completed_effects.append(_task_create_effect())
        created += 1
    return created


def _regenerate_beads(
    expected: list[Any],
    *,
    bd_bin: str = "bd",
    completed_effects: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Create actionable managed tasks after cache clear (empty list = no-op)."""
    import subprocess

    created: list[dict[str, Any]] = []
    for task in expected:
        description = render_marker(
            marker_from_expected(
                project_id=task.project_id,
                ssot_id=task.ssot_id,
                ssot_path=task.ssot_path,
                ssot_anchor=task.ssot_anchor,
                task_kind=task.task_kind,
                ssot_snapshot_hash=task.ssot_snapshot_hash,
                source_item_hash=task.source_item_hash,
            )
        )
        op = ApplyOperation(
            op_type="create_managed",
            executable=True,
            title=task.title,
            description=description,
            reason="cache_reset_regenerate",
            managed_key=task.managed_key,
            project_id=task.project_id,
            ssot_id=task.ssot_id,
            ssot_path=task.ssot_path,
            ssot_anchor=task.ssot_anchor,
            task_kind=task.task_kind,
            ssot_snapshot_hash=task.ssot_snapshot_hash,
            source_item_hash=task.source_item_hash,
        )
        # metadata helper keeps identity linked; create argv from apply builders
        _ = build_managed_metadata(op)
        argv = build_bd_create_argv(op, bd_bin=bd_bin, silent=True)
        # create is allowed for regenerate after clear (not delete/close/claim)
        proc = subprocess.run(argv, capture_output=True, text=True, check=False, timeout=60.0)
        if proc.returncode != 0:
            raise BeadsCacheResetError(
                "BD_CACHE_RESET_REGENERATE_FAILED",
                "bd create failed during cache regenerate",
                {
                    "ssot_anchor": task.ssot_anchor,
                    "managed_key": task.managed_key,
                    "returncode": proc.returncode,
                    "mutation": bool(completed_effects),
                },
            )
        pid = parse_bd_create_id(proc.stdout or "", proc.stderr or "")
        # Record completed effect before the next provider call.
        completed_effects.append(_task_create_effect())
        created.append(
            {
                "ssot_anchor": task.ssot_anchor,
                "managed_key": task.managed_key,
                "provider_task_id_hash": _id_hash(pid),
            }
        )
    return created


def run_task_cache_reset(
    *,
    repo_root: Path,
    apply: bool = False,
    provider_name: str = "fake",
    mode: str = DEFAULT_TASK_CACHE_MODE,
    provider: Any | None = None,
    bd_runner: Any | None = None,
) -> dict[str, Any]:
    """Plan or apply whole local ephemeral Vibe-managed task cache reset + regenerate."""
    mutation_intent = bool(apply)
    if mode != DEFAULT_TASK_CACHE_MODE:
        return _unsupported_mode(mode, mutation_intent=mutation_intent)

    try:
        config = load_config(repo_root)
        project_id = config.project_id
    except ConfigError as exc:
        return _finish_cache_reset(
            failure_envelope(
                command="vibe task cache reset",
                code=exc.code or "CONFIG_INVALID",
                message=exc.message,
            ),
            mutation_intent=mutation_intent,
            effects=[],
        )

    expected = project_actionable_expected_tasks(project_id=project_id, repo_root=repo_root)

    try:
        existing_rows = _inventory_existing(provider_name=provider_name, provider=provider)
    except BeadsCacheResetError as exc:
        return _finish_cache_reset(
            failure_envelope(
                command="vibe task cache reset",
                code=exc.code,
                message=exc.message,
                project_id=project_id,
                details={**exc.details, "mutation": False},
            ),
            mutation_intent=mutation_intent,
            effects=[],
        )

    plan = _plan_payload(
        mode=mode,
        provider_name=provider_name,
        expected=expected,
        existing_rows=existing_rows,
    )

    if not apply:
        return _finish_cache_reset(
            success_envelope(
                command="vibe task cache reset",
                project_id=project_id,
                mode="dry_run",
                data={
                    "task_cache_mode": mode,
                    "plan": plan,
                    "mutation": False,
                    "note": (
                        "Whole Vibe-managed local ephemeral cache reset/regenerate; "
                        "not per-conflict repair; not team/shared/server mode"
                    ),
                },
                next_actions=[
                    next_action(
                        code="TASK_CACHE_RESET_APPLY",
                        command=f"vibe task cache reset --apply --json --provider {provider_name}",
                        mutation=True,
                        reason=(
                            "Explicit --apply clears Vibe-managed local ephemeral Beads cache "
                            "then regenerates from actionable roadmap-state projection"
                        ),
                    )
                ],
            ),
            mutation_intent=False,
            effects=[],
        )

    # --- apply ---
    completed_effects: list[dict[str, Any]] = []

    if provider_name == "fake":
        use = provider if isinstance(provider, FakeTaskProvider) else FakeTaskProvider()
        # Prefer inventory from provided provider before clear
        if provider is not None and hasattr(provider, "list_tasks"):
            existing_rows = classify_vibe_managed_tasks(list(provider.list_tasks()))
            plan = _plan_payload(
                mode=mode,
                provider_name=provider_name,
                expected=expected,
                existing_rows=existing_rows,
            )
        cleared = len(existing_rows)
        try:
            if hasattr(use, "clear"):
                use.clear()
            if cleared > 0:
                # Record clear only after it completes, before regenerate writes.
                completed_effects.append(_cache_reset_effect())
            created = _regenerate_fake_after_clear(
                expected, use, completed_effects=completed_effects
            )
        except Exception as exc:
            return _finish_cache_reset(
                failure_envelope(
                    command="vibe task cache reset",
                    code="TASK_CACHE_RESET_PARTIAL_FAILURE",
                    message=f"Cache reset failed after partial writes: {exc}",
                    project_id=project_id,
                    details={"mutation": bool(completed_effects)},
                ),
                mutation_intent=True,
                effects=completed_effects,
            )
        return _finish_cache_reset(
            success_envelope(
                command="vibe task cache reset",
                project_id=project_id,
                mode="mutation",
                data={
                    "task_cache_mode": mode,
                    "reset_scope": plan["reset_scope"],
                    "cleared": True,
                    "cleared_count": cleared,
                    "regenerated": created,
                    "regenerated_records": [
                        {"ssot_anchor": t.ssot_anchor, "managed_key": t.managed_key}
                        for t in expected
                    ],
                    "plan": plan,
                    "mutation": bool(completed_effects),
                },
            ),
            mutation_intent=True,
            effects=completed_effects,
        )

    if provider_name != "beads":
        return _finish_cache_reset(
            failure_envelope(
                command="vibe task cache reset",
                code="TASK_CACHE_PROVIDER_UNSUPPORTED",
                message=f"Unsupported provider for cache reset: {provider_name!r}",
                project_id=project_id,
                details={"mutation": False},
            ),
            mutation_intent=True,
            effects=[],
        )

    bd_bin = shutil.which("bd") or "bd"
    clear_result: dict[str, Any] | None = None
    try:
        # Re-list live for apply authenticity
        readonly = BeadsReadonlyProvider()
        live_tasks = list(readonly.list_tasks())
        if not readonly.available:
            raise BeadsCacheResetError(
                "BEADS_UNAVAILABLE",
                readonly.last_error or "Beads unavailable for cache reset",
            )
        clear_result = clear_vibe_managed_beads_cache(
            tasks=live_tasks,
            runner=bd_runner or subprocess_bd_cache_runner,
            bd_bin=bd_bin,
        )
        # Clear succeeded (including no-op empty inventory); record only real deletes.
        if int(clear_result.get("cleared_count") or 0) > 0:
            completed_effects.append(_cache_reset_effect())
        regenerated = _regenerate_beads(
            expected, bd_bin=bd_bin, completed_effects=completed_effects
        )
    except BeadsCacheResetError as exc:
        # Preserve completed clear effects when regenerate fails (partial success).
        return _finish_cache_reset(
            failure_envelope(
                command="vibe task cache reset",
                code=exc.code,
                message=exc.message,
                project_id=project_id,
                details={**exc.details, "mutation": bool(completed_effects)},
            ),
            mutation_intent=True,
            effects=completed_effects,
        )

    return _finish_cache_reset(
        success_envelope(
            command="vibe task cache reset",
            project_id=project_id,
            mode="mutation",
            data={
                "task_cache_mode": mode,
                "reset_scope": plan["reset_scope"],
                "reset_kind": plan["reset_kind"],
                "cleared": True,
                "cleared_count": clear_result["cleared_count"],
                "cleared_records": clear_result["records"],
                "cleared_anchors": clear_result["anchors"],
                "cleared_managed_keys": clear_result["managed_keys"],
                "regenerated": len(regenerated),
                "regenerated_records": regenerated,
                "plan": plan,
                "mutation": bool(completed_effects),
            },
        ),
        mutation_intent=True,
        effects=completed_effects,
    )
