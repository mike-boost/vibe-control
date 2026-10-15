"""High-level SSOT closeout workflow driver (orchestration over existing primitives)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Callable

from vibe_control.closeout import PROJECT_SOURCES_ADVISOR_FILES, evaluate_ssot_closeout
from vibe_control.config import load_config
from vibe_control.git_land_contract import GIT_LAND_DIRTY_REASON
from vibe_control.json_envelope import (
    attach_operation_result,
    failure_envelope,
    next_action,
    success_envelope,
)
from vibe_control.knowledge.ask_hygiene import assert_apply_ops_are_current_ssot_bounded
from vibe_control.knowledge.corpus import resolve_desired_corpus
from vibe_control.task.cache import evaluate_task_cache_state

Deps = dict[str, Any]


def _finish_closeout(
    env: dict[str, Any],
    *,
    apply: bool,
    effects: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Attach operation evidence; keep nested data.mutation aliases aligned."""
    out = attach_operation_result(
        env,
        mutation_intent=bool(apply),
        effects=effects or [],
    )
    performed = bool(out["mutation_performed"])
    data = out.get("data")
    if isinstance(data, dict) and "mutation" in data:
        data["mutation"] = performed
    err = out.get("error")
    if isinstance(err, dict):
        details = err.get("details")
        if isinstance(details, dict) and "mutation" in details:
            details["mutation"] = performed
    return out


def _effects_from_sync_apply(applied: dict[str, Any]) -> list[dict[str, Any]]:
    """Prefer child envelope effects; otherwise record a completed sync write."""
    child = applied.get("effects")
    if isinstance(child, list) and child:
        return [e for e in child if isinstance(e, dict)]
    if applied.get("ok") or applied.get("mutation_performed") or applied.get("mutation"):
        return [
            {
                "kind": "provider_write",
                "target": "knowledge.sync",
                "status": "completed",
            }
        ]
    return []


def _git_status_short(repo_root: Path) -> str:
    result = subprocess.run(
        ["git", "status", "--short"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    return (result.stdout or "").strip()


def _closeout_notebook_alias(repo_root: Path) -> str | None:
    """Closeout always binds to default_alias (product gate), never side notebooks."""
    config = load_config(repo_root)
    notebooks = config.knowledge.get("notebooks")
    if not isinstance(notebooks, dict):
        return None
    from vibe_control.knowledge.notebooks import resolve_default_alias

    return resolve_default_alias(config)


def _desired_doc_ids(repo_root: Path) -> set[str]:
    config = load_config(repo_root)
    alias = _closeout_notebook_alias(repo_root)
    corpus = resolve_desired_corpus(config, notebook_alias=alias, repo_root=repo_root)
    return {d.doc_id for d in corpus.documents}


def _default_integration_status(repo_root: Path) -> dict[str, Any]:
    from vibe_control.integration import build_integration_status

    return build_integration_status(repo_root=repo_root, probe_auth=False, probe_product=True)


def _default_plan_sync_dry_run(repo_root: Path) -> dict[str, Any]:
    from types import SimpleNamespace

    from vibe_control.knowledge.remote_ops import cmd_knowledge_sync

    alias = _closeout_notebook_alias(repo_root)
    env = cmd_knowledge_sync(
        repo_root,
        SimpleNamespace(
            dry_run=True,
            apply=False,
            notebook=alias,
            confirm_non_default_sync=False,
        ),
    )
    if env.get("ok"):
        data = dict(env.get("data") or {})
        data["ok"] = True
        return data
    return {
        "ok": False,
        "code": (env.get("error") or {}).get("code") or "SYNC_DRY_RUN_FAILED",
        "message": (env.get("error") or {}).get("message") or "sync dry-run failed",
        "details": (env.get("error") or {}).get("details") or {},
        "operations": [],
        "required_updates_count": 0,
        "sync_state": "unavailable",
    }


def _default_apply_knowledge_sync(repo_root: Path) -> dict[str, Any]:
    from types import SimpleNamespace

    from vibe_control.knowledge.remote_ops import cmd_knowledge_sync

    alias = _closeout_notebook_alias(repo_root)
    env = cmd_knowledge_sync(
        repo_root,
        SimpleNamespace(
            dry_run=False,
            apply=True,
            notebook=alias,
            confirm_non_default_sync=False,
        ),
    )
    if env.get("ok"):
        data = dict(env.get("data") or {})
        data["ok"] = True
        data["applied"] = True
        if isinstance(env.get("effects"), list):
            data["effects"] = list(env["effects"])
        if "mutation_performed" in env:
            data["mutation_performed"] = bool(env["mutation_performed"])
        if "mutation" in env:
            data["mutation"] = bool(env["mutation"])
        return data
    details = dict((env.get("error") or {}).get("details") or {})
    out = {
        "ok": False,
        "code": (env.get("error") or {}).get("code") or "SYNC_APPLY_FAILED",
        "message": (env.get("error") or {}).get("message") or "sync apply failed",
        "details": details,
        "applied": False,
    }
    if isinstance(env.get("effects"), list):
        out["effects"] = list(env["effects"])
    if "mutation_performed" in env:
        out["mutation_performed"] = bool(env["mutation_performed"])
    if "mutation" in env:
        out["mutation"] = bool(env["mutation"])
    return out


def _kp(status: dict[str, Any]) -> dict[str, Any]:
    return dict(status.get("knowledge_provider") or {})


def _hetu_capability_enabled(status: dict[str, Any]) -> bool:
    """Hetu is optional; absent profile/components means disabled (not legacy-on)."""
    cap = status.get("capability_profile") or {}
    if "hetu_enabled" in cap:
        return bool(cap.get("hetu_enabled"))
    if "hetu_enabled" in status:
        return bool(status.get("hetu_enabled"))
    comps = status.get("components") or {}
    if "hetu" in comps:
        return bool((comps.get("hetu") or {}).get("enabled"))
    return False


def _hetu_ready(status: dict[str, Any]) -> bool:
    if "hetu_ready" in status and status.get("hetu_ready") is not None:
        return bool(status.get("hetu_ready"))
    hetu = status.get("hetu") or {}
    if isinstance(hetu, dict) and "ready" in hetu and hetu.get("ready") is not None:
        return bool(hetu.get("ready"))
    return str(status.get("hetu_index_state") or "") == "ready"


def _hetu_closeout_blockers(status: dict[str, Any]) -> list[str]:
    """Blocked reasons for enabled non-ready Hetu. Never triggers reindex."""
    if not _hetu_capability_enabled(status):
        return []
    if _hetu_ready(status):
        return []
    existing = [
        str(r)
        for r in (status.get("blocked_reasons") or [])
        if str(r).startswith("hetu_")
    ]
    if existing:
        return existing
    from vibe_control.product_readiness import hetu_blocked_reason_for_state

    mapped = hetu_blocked_reason_for_state(
        index_state=str(status.get("hetu_index_state") or "unavailable"),
        block_detail=None,
    )
    return [mapped] if mapped else ["hetu_index_unverifiable"]


def _hetu_closeout_next_actions() -> list[dict[str, Any]]:
    return [
        next_action(
            code="HETU_STATUS",
            command="vibe hetu status --json",
            mutation=False,
            reason="Diagnose Hetu index freshness; closeout never auto-reindexes",
        ),
        next_action(
            code="HETU_REINDEX_DRY_RUN",
            command="vibe hetu reindex --dry-run --json",
            mutation=False,
            reason=(
                "Preview confirmed Hetu reindex plan. Apply requires "
                "--confirm-hetu-reindex-apply; closeout will not run it."
            ),
        ),
    ]


def _capability_enabled(status: dict[str, Any], name: str) -> bool:
    """Return whether a Capability Profile capability is enabled.

    Absent capability_profile/components (legacy fixtures) defaults to enabled so
    existing closeout knowledge/task gates remain in force.
    """
    if name == "hetu":
        return _hetu_capability_enabled(status)
    cap = status.get("capability_profile") or {}
    key = f"{name}_enabled"
    if key in cap:
        return bool(cap.get(key))
    comps = status.get("components") or {}
    if name in comps:
        return bool((comps.get(name) or {}).get("enabled"))
    return True


def _knowledge_needs_sync(status: dict[str, Any]) -> bool:
    if not _capability_enabled(status, "knowledge"):
        return False
    kp = _kp(status)
    sync_state = str(kp.get("sync_state") or "unavailable")
    ask_clean = bool(kp.get("provider_ask_clean"))
    if status.get("provider_sync_required"):
        return True
    if sync_state in {"drift", "pending", "unavailable", "receipt_missing", "target_mismatch"}:
        return True
    if not ask_clean:
        return True
    return False


def _is_provider_unavailable(status: dict[str, Any]) -> bool:
    if not _capability_enabled(status, "knowledge"):
        return False
    kp = _kp(status)
    sync_state = str(kp.get("sync_state") or "unavailable")
    if not kp.get("available"):
        return True
    if sync_state in {"unavailable", "target_mismatch"}:
        return True
    if kp.get("target_ok") is False and sync_state != "synced":
        return sync_state in {"unavailable", "target_mismatch"} or not kp.get("available")
    return sync_state == "unavailable"


def _advisor_meta(status: dict[str, Any] | None = None) -> dict[str, Any]:
    existing = (status or {}).get("chatgpt_project_sources")
    if isinstance(existing, dict) and existing.get("product_closeout_gate") is False:
        return {
            "product_closeout_gate": False,
            "owner_manual_external_copy": True,
            "advisor_files": list(existing.get("advisor_files") or PROJECT_SOURCES_ADVISOR_FILES),
        }
    return {
        "product_closeout_gate": False,
        "owner_manual_external_copy": True,
        "advisor_files": list(PROJECT_SOURCES_ADVISOR_FILES),
    }


def _payload_base(
    *,
    status: dict[str, Any],
    actions_run: list[str],
    blocked_reasons: list[str],
    warnings: list[str],
    next_actions: list[dict[str, Any]],
    next_required_action: str,
    knowledge_closeout: dict[str, Any],
    task_closeout: dict[str, Any],
    closeout_complete: bool,
    implementation_ready: bool,
    safe_to_continue: bool,
    mutation: bool,
) -> dict[str, Any]:
    kp = _kp(status)
    sync_state = knowledge_closeout.get("sync_state", kp.get("sync_state"))
    ask_clean = bool(
        knowledge_closeout.get("provider_ask_clean", kp.get("provider_ask_clean"))
    )
    cache_current = bool(
        task_closeout.get(
            "task_cache_current", status.get("task_cache_current")
        )
    )
    return {
        "closeout_state": status.get("closeout_state"),
        "closeout_complete": closeout_complete,
        "implementation_ready": implementation_ready,
        "provider_sync_required": bool(status.get("provider_sync_required")),
        "sync_state": sync_state,
        "provider_ask_clean": ask_clean,
        "task_cache_current": cache_current,
        "knowledge_closeout": knowledge_closeout,
        "task_closeout": task_closeout,
        "actions_run": list(actions_run),
        "blocked_reasons": list(blocked_reasons),
        "warnings": list(warnings),
        "next_actions": list(next_actions),
        "next_required_action": next_required_action,
        "safe_to_continue": safe_to_continue,
        "chatgpt_project_sources": _advisor_meta(status),
        "mutation": mutation,
    }


def _task_closeout_from_status(status: dict[str, Any], *, knowledge_ready: bool) -> dict[str, Any]:
    if not _capability_enabled(status, "task"):
        return {
            "task_cache_current": True,
            "reconcile_counts": {},
            "apply_plan_counts": {},
            "convergence_required": False,
            "reset_required": False,
            "safe_task_convergence_allowed": False,
            "capability_skipped": True,
        }
    cache = dict(status.get("task_cache") or {})
    counts = dict(cache.get("reconcile_counts") or {})
    plan = dict(cache.get("apply_plan_counts") or {})
    tp = dict(status.get("task_provider") or {})
    evaluated = evaluate_task_cache_state(
        reconcile_counts=counts,
        apply_plan_counts=plan,
        knowledge_ready=knowledge_ready,
        task_available=bool(tp.get("available")),
        task_readable=bool(tp.get("readable")),
    )
    current = bool(status.get("task_cache_current", evaluated.get("task_cache_current")))
    pollution = any(int(counts.get(k) or 0) > 0 for k in ("duplicate", "conflict", "unmanaged"))
    return {
        "task_cache_current": current,
        "reconcile_counts": counts or evaluated.get("reconcile_counts") or {},
        "apply_plan_counts": plan or evaluated.get("apply_plan_counts") or {},
        "convergence_required": (not current) and not pollution,
        "reset_required": bool(evaluated.get("task_cache_reset_required") or pollution),
        "safe_task_convergence_allowed": bool(evaluated.get("safe_task_convergence_allowed")),
    }


def run_closeout(
    *,
    repo_root: Path,
    apply: bool = False,
    deps: Deps | None = None,
) -> dict[str, Any]:
    """Run high-level SSOT closeout orchestration.

    Default (apply=False): readonly dry-run — no NotebookLM apply, no Beads mutation.
    apply=True: may perform bounded knowledge sync --apply only after fail-closed checks.
    Never auto-runs live Beads apply. Never gates on ChatGPT Project Sources.
    """
    root = Path(repo_root)
    d = deps or {}
    git_status_short: Callable[[Path], str] = d.get("git_status_short") or _git_status_short
    build_status: Callable[..., dict[str, Any]] = (
        d.get("build_integration_status") or _default_integration_status
    )
    plan_dry: Callable[[Path], dict[str, Any]] = d.get("plan_sync_dry_run") or _default_plan_sync_dry_run
    apply_sync: Callable[[Path], dict[str, Any]] = (
        d.get("apply_knowledge_sync") or _default_apply_knowledge_sync
    )
    desired_ids_fn: Callable[[Path], set[str]] = d.get("desired_doc_ids") or _desired_doc_ids

    actions_run: list[str] = []
    warnings: list[str] = []
    next_actions: list[dict[str, Any]] = []
    blocked_reasons: list[str] = []
    mode = "apply" if apply else "dry-run"
    mutation = False
    completed_effects: list[dict[str, Any]] = []
    command = "vibe closeout run"

    actions_run.append("git_status_check")
    dirty = git_status_short(root)
    if dirty:
        blocked_reasons.append("local_modifications_present")
        payload = {
            "closeout_state": "ssot_change_committed_sync_required",
            "closeout_complete": False,
            "implementation_ready": False,
            "provider_sync_required": True,
            "sync_state": None,
            "provider_ask_clean": False,
            "task_cache_current": False,
            "knowledge_closeout": {
                "sync_state": None,
                "provider_ask_clean": False,
                "required_updates_count": 0,
                "dry_run_bounded": False,
                "applied": False,
            },
            "task_closeout": {
                "task_cache_current": False,
                "reconcile_counts": {},
                "apply_plan_counts": {},
                "convergence_required": False,
            },
            "actions_run": actions_run,
            "blocked_reasons": blocked_reasons,
            "warnings": warnings,
            "next_actions": [
                next_action(
                    code="COMMIT_OR_CLEAN_LOCAL_STATE",
                    command="git status --short",
                    mutation=False,
                    reason=GIT_LAND_DIRTY_REASON,
                )
            ],
            "next_required_action": "clean_git_status",
            "safe_to_continue": False,
            "chatgpt_project_sources": _advisor_meta(),
            "mutation": False,
        }
        if apply:
            env = failure_envelope(
                command=command,
                code="GIT_DIRTY",
                message="Closeout apply refused: git status --short is not empty",
                details={"git_status_short": dirty, **payload},
                project_id=None,
                warnings=warnings,
                next_actions=payload["next_actions"],
            )
            env["mode"] = mode
            env["data"] = payload
            return _finish_closeout(env, apply=apply, effects=completed_effects)
        # dry-run still reports the blocker without claiming complete
        env = success_envelope(
            command=command,
            project_id=None,
            mode=mode,
            data=payload,
            warnings=warnings + ["local_modifications_present"],
            next_actions=payload["next_actions"],
        )
        return _finish_closeout(env, apply=apply, effects=completed_effects)

    actions_run.append("integration_status")
    status = build_status(root)
    project_id = status.get("project_id")

    knowledge_closeout = {
        "sync_state": _kp(status).get("sync_state"),
        "provider_ask_clean": bool(_kp(status).get("provider_ask_clean")),
        "required_updates_count": int(
            ((_kp(status).get("ask_hygiene") or {}).get("required_updates_count")) or 0
        ),
        "dry_run_bounded": True,
        "applied": False,
    }

    if _is_provider_unavailable(status):
        blocked_reasons.extend(list(status.get("blocked_reasons") or []))
        blocked_reasons.append("provider_unavailable")
        task_closeout = _task_closeout_from_status(status, knowledge_ready=False)
        payload = _payload_base(
            status=status,
            actions_run=actions_run,
            blocked_reasons=list(dict.fromkeys(blocked_reasons)),
            warnings=warnings + list(status.get("warnings") or []),
            next_actions=[
                next_action(
                    code="KNOWLEDGE_DOCTOR",
                    command="vibe knowledge doctor --json",
                    mutation=False,
                    reason="Knowledge provider unavailable or target mismatch",
                )
            ],
            next_required_action="provider_unavailable",
            knowledge_closeout=knowledge_closeout,
            task_closeout=task_closeout,
            closeout_complete=False,
            implementation_ready=False,
            safe_to_continue=False,
            mutation=False,
        )
        env = failure_envelope(
            command=command,
            code="PROVIDER_UNAVAILABLE",
            message="Closeout stopped: knowledge provider unavailable or target mismatch",
            details=payload,
            project_id=project_id,
            warnings=payload["warnings"],
            next_actions=payload["next_actions"],
        )
        env["mode"] = mode
        env["data"] = payload
        return _finish_closeout(env, apply=apply, effects=completed_effects)

    dry_run_ops: list[dict[str, Any]] = []
    dry_run_bounded = True

    if _knowledge_needs_sync(status):
        actions_run.append("sync_dry_run")
        dry = plan_dry(root)
        if not dry.get("ok"):
            blocked_reasons.append("sync_dry_run_failed")
            task_closeout = _task_closeout_from_status(status, knowledge_ready=False)
            knowledge_closeout.update(
                {
                    "sync_state": dry.get("sync_state") or _kp(status).get("sync_state"),
                    "provider_ask_clean": False,
                    "required_updates_count": int(dry.get("required_updates_count") or 0),
                    "dry_run_bounded": False,
                    "applied": False,
                }
            )
            payload = _payload_base(
                status=status,
                actions_run=actions_run,
                blocked_reasons=blocked_reasons,
                warnings=warnings,
                next_actions=[
                    next_action(
                        code="KNOWLEDGE_SYNC_DRY_RUN",
                        command="vibe knowledge sync --dry-run --json",
                        mutation=False,
                        reason="Sync dry-run failed during closeout preflight",
                    )
                ],
                next_required_action="fix_knowledge_provider",
                knowledge_closeout=knowledge_closeout,
                task_closeout=task_closeout,
                closeout_complete=False,
                implementation_ready=False,
                safe_to_continue=False,
                mutation=False,
            )
            env = failure_envelope(
                command=command,
                code=str(dry.get("code") or "SYNC_DRY_RUN_FAILED"),
                message=str(dry.get("message") or "closeout sync dry-run failed"),
                details=payload,
                project_id=project_id,
                next_actions=payload["next_actions"],
            )
            env["mode"] = mode
            env["data"] = payload
            return _finish_closeout(env, apply=apply, effects=completed_effects)

        dry_run_ops = list(dry.get("operations") or [])
        desired_ids = desired_ids_fn(root)
        bound = assert_apply_ops_are_current_ssot_bounded(dry_run_ops, desired_doc_ids=desired_ids)
        dry_run_bounded = bool(bound.get("ok"))
        knowledge_closeout.update(
            {
                "sync_state": dry.get("sync_state") or _kp(status).get("sync_state"),
                "provider_ask_clean": False,
                "required_updates_count": int(dry.get("required_updates_count") or 0),
                "dry_run_bounded": dry_run_bounded,
                "applied": False,
            }
        )

        if not dry_run_bounded:
            blocked_reasons.append("sync_plan_unbounded_or_unsafe")
            for v in bound.get("violations") or []:
                blocked_reasons.append(str(v))
            task_closeout = _task_closeout_from_status(status, knowledge_ready=False)
            payload = _payload_base(
                status=status,
                actions_run=actions_run,
                blocked_reasons=list(dict.fromkeys(blocked_reasons)),
                warnings=warnings,
                next_actions=[
                    next_action(
                        code="OWNER_APPROVAL_FOR_NON_BOUNDED_SYNC",
                        command="vibe knowledge sync --dry-run --json",
                        mutation=False,
                        reason="Dry-run is not bounded to current active SSOT/default inventory",
                    )
                ],
                next_required_action="bounded_sync_required_or_owner_approval",
                knowledge_closeout=knowledge_closeout,
                task_closeout=task_closeout,
                closeout_complete=False,
                implementation_ready=False,
                safe_to_continue=False,
                mutation=False,
            )
            if apply:
                env = failure_envelope(
                    command=command,
                    code="APPLY_SCOPE_VIOLATION",
                    message="Closeout apply refused: sync dry-run is unbounded or unsafe",
                    details=payload,
                    project_id=project_id,
                    next_actions=payload["next_actions"],
                )
                env["mode"] = mode
                env["data"] = payload
                return _finish_closeout(env, apply=apply, effects=completed_effects)
            env = success_envelope(
                command=command,
                project_id=project_id,
                mode=mode,
                data=payload,
                warnings=warnings + ["sync_plan_unbounded_or_unsafe"],
                next_actions=payload["next_actions"],
            )
            return _finish_closeout(env, apply=apply, effects=completed_effects)

        if apply:
            actions_run.append("sync_apply")
            applied = apply_sync(root)
            if not applied.get("ok"):
                completed_effects.extend(_effects_from_sync_apply(applied))
                blocked_reasons.append("sync_apply_failed")
                task_closeout = _task_closeout_from_status(status, knowledge_ready=False)
                knowledge_closeout["applied"] = False
                payload = _payload_base(
                    status=status,
                    actions_run=actions_run,
                    blocked_reasons=blocked_reasons,
                    warnings=warnings,
                    next_actions=[
                        next_action(
                            code="KNOWLEDGE_SYNC_APPLY",
                            command="vibe knowledge sync --apply --json",
                            mutation=True,
                            reason="Bounded closeout sync apply failed",
                        )
                    ],
                    next_required_action="retry_bounded_knowledge_sync",
                    knowledge_closeout=knowledge_closeout,
                    task_closeout=task_closeout,
                    closeout_complete=False,
                    implementation_ready=False,
                    safe_to_continue=False,
                    mutation=bool(completed_effects),
                )
                env = failure_envelope(
                    command=command,
                    code=str(applied.get("code") or "SYNC_APPLY_FAILED"),
                    message=str(applied.get("message") or "closeout sync apply failed"),
                    details=payload,
                    project_id=project_id,
                    next_actions=payload["next_actions"],
                )
                env["mode"] = mode
                env["data"] = payload
                return _finish_closeout(env, apply=apply, effects=completed_effects)
            completed_effects.extend(_effects_from_sync_apply(applied))
            mutation = bool(completed_effects)
            knowledge_closeout["applied"] = True
            actions_run.append("integration_status_post")
            status = build_status(root)
            knowledge_closeout["sync_state"] = _kp(status).get("sync_state")
            knowledge_closeout["provider_ask_clean"] = bool(_kp(status).get("provider_ask_clean"))
            knowledge_closeout["required_updates_count"] = int(
                ((_kp(status).get("ask_hygiene") or {}).get("required_updates_count")) or 0
            )
        else:
            next_actions.append(
                next_action(
                    code="RUN_CLOSEOUT_APPLY",
                    command="vibe closeout run --apply --json",
                    mutation=True,
                    reason=(
                        "Dry-run is bounded to current SSOT/default inventory; "
                        "run closeout --apply for knowledge half"
                    ),
                )
            )

    # Refresh task half from current status (post-apply if any)
    kp = _kp(status)
    knowledge_on = _capability_enabled(status, "knowledge")
    if not knowledge_on:
        knowledge_ready = True
        knowledge_closeout = {
            **knowledge_closeout,
            "provider_ask_clean": True,
            "sync_state": "synced",
            "capability_skipped": True,
            "required_updates_count": 0,
        }
    else:
        knowledge_ready = (
            str(kp.get("sync_state")) == "synced"
            and bool(kp.get("provider_ask_clean"))
            and not bool(status.get("provider_sync_required"))
        )
        # If we still need sync and did not apply, knowledge is not ready
        if _knowledge_needs_sync(status) and not knowledge_closeout.get("applied"):
            knowledge_ready = False

    task_closeout = _task_closeout_from_status(status, knowledge_ready=knowledge_ready)
    warnings.extend(list(status.get("warnings") or []))

    if not knowledge_ready:
        if not next_actions:
            next_actions.append(
                next_action(
                    code="RUN_BOUNDED_KNOWLEDGE_SYNC",
                    command="vibe closeout run --apply --json",
                    mutation=True,
                    reason="Knowledge half of closeout is not clean",
                )
            )
        next_required = "run_bounded_knowledge_sync"
        if not knowledge_closeout.get("dry_run_bounded", True):
            next_required = "bounded_sync_required_or_owner_approval"
        closeout_complete = False
        implementation_ready = False
        safe_to_continue = bool(knowledge_closeout.get("dry_run_bounded")) and not apply
        payload = _payload_base(
            status=status,
            actions_run=actions_run,
            blocked_reasons=list(dict.fromkeys(blocked_reasons + list(status.get("blocked_reasons") or []))),
            warnings=list(dict.fromkeys(warnings)),
            next_actions=next_actions,
            next_required_action=next_required,
            knowledge_closeout=knowledge_closeout,
            task_closeout=task_closeout,
            closeout_complete=closeout_complete,
            implementation_ready=implementation_ready,
            safe_to_continue=safe_to_continue,
            mutation=mutation,
        )
        # Align closeout_state via evaluator when possible
        hint = evaluate_ssot_closeout(
            ssot_or_include_extra_changed=True,
            knowledge_synced=False,
            provider_ask_clean=False,
            product_ready=False,
            task_available=True,
            task_readable=True,
        )
        payload["closeout_state"] = status.get("closeout_state") or hint.get("closeout_state")
        env = success_envelope(
            command=command,
            project_id=project_id,
            mode=mode,
            data=payload,
            warnings=payload["warnings"],
            next_actions=next_actions,
        )
        return _finish_closeout(env, apply=apply, effects=completed_effects)

    # Knowledge clean — task half
    if task_closeout.get("reset_required"):
        next_required = "task_cache_reset_required"
        next_actions.append(
            next_action(
                code="TASK_CACHE_RESET_DRY_RUN",
                command="vibe task cache reset --dry-run --json",
                mutation=False,
                reason=(
                    "Task cache pollution (duplicate/conflict/unmanaged); "
                    "no automatic repair — prefer reset/regenerate"
                ),
            )
        )
        blocked_reasons.append("task_cache_pollution")
        payload = _payload_base(
            status=status,
            actions_run=actions_run,
            blocked_reasons=list(dict.fromkeys(blocked_reasons)),
            warnings=list(dict.fromkeys(warnings)),
            next_actions=next_actions,
            next_required_action=next_required,
            knowledge_closeout=knowledge_closeout,
            task_closeout=task_closeout,
            closeout_complete=False,
            implementation_ready=False,
            safe_to_continue=False,
            mutation=mutation,
        )
        env = success_envelope(
            command=command,
            project_id=project_id,
            mode=mode,
            data=payload,
            warnings=payload["warnings"],
            next_actions=next_actions,
        )
        return _finish_closeout(env, apply=apply, effects=completed_effects)

    if not task_closeout.get("task_cache_current"):
        next_required = "task_convergence_required"
        next_actions.append(
            next_action(
                code="TASK_CONVERGENCE_REQUIRED",
                command="vibe task apply --dry-run --json --provider beads",
                mutation=False,
                reason=(
                    "Knowledge half clean; task cache not current. "
                    "Run Beads convergence under Approval Matrix / Option A gates — "
                    "closeout driver never auto-mutates Beads"
                ),
            )
        )
        payload = _payload_base(
            status=status,
            actions_run=actions_run,
            blocked_reasons=list(dict.fromkeys(blocked_reasons + ["task_cache_not_current"])),
            warnings=list(dict.fromkeys(warnings)),
            next_actions=next_actions,
            next_required_action=next_required,
            knowledge_closeout=knowledge_closeout,
            task_closeout={**task_closeout, "convergence_required": True},
            closeout_complete=False,
            implementation_ready=False,
            safe_to_continue=True,
            mutation=mutation,
        )
        env = success_envelope(
            command=command,
            project_id=project_id,
            mode=mode,
            data=payload,
            warnings=payload["warnings"],
            next_actions=next_actions,
        )
        return _finish_closeout(env, apply=apply, effects=completed_effects)

    # Hetu half — report blockers only; never auto-reindex.
    hetu_blockers = _hetu_closeout_blockers(status)
    if hetu_blockers:
        next_required = "hetu_reindex_required"
        next_actions.extend(_hetu_closeout_next_actions())
        payload = _payload_base(
            status=status,
            actions_run=actions_run,
            blocked_reasons=list(dict.fromkeys(blocked_reasons + hetu_blockers)),
            warnings=list(dict.fromkeys(warnings)),
            next_actions=next_actions,
            next_required_action=next_required,
            knowledge_closeout=knowledge_closeout,
            task_closeout=task_closeout,
            closeout_complete=False,
            implementation_ready=False,
            safe_to_continue=True,
            mutation=mutation,
        )
        payload["hetu_closeout"] = {
            "enabled": True,
            "ready": False,
            "index_state": status.get("hetu_index_state"),
            "auto_reindex": False,
            "note": "Closeout never auto-reindexes Hetu; run reindex dry-run then confirmed apply",
        }
        env = success_envelope(
            command=command,
            project_id=project_id,
            mode=mode,
            data=payload,
            warnings=payload["warnings"],
            next_actions=next_actions,
        )
        return _finish_closeout(env, apply=apply, effects=completed_effects)

    # Full closeout complete — implementation_ready shares Progress semantics
    # (gates clear AND an actionable next task exists).
    from vibe_control.implementation.prompt import compute_implementation_ready
    from vibe_control.task.projection import next_actionable_selection as _default_next_selection

    knowledge_on = _capability_enabled(status, "knowledge")
    task_on = _capability_enabled(status, "task")
    select_next = d.get("next_actionable_selection") or _default_next_selection
    selection = select_next(repo_root=root)
    no_next = bool(selection.get("no_actionable_next_task")) or not selection.get(
        "next_actionable_task"
    )
    implementation_ready = compute_implementation_ready(
        task_completed=no_next,
        product_ready=bool(status.get("product_ready")),
        provider_sync_required=bool(status.get("provider_sync_required")),
        sync_state="synced",
        provider_ask_clean=True,
        task_cache_current=True
        if not task_on
        else bool(task_closeout.get("task_cache_current")),
        config_ok=bool(status.get("config_ok", True)),
        knowledge_enabled=knowledge_on,
        task_enabled=task_on,
    )
    payload = _payload_base(
        status=status,
        actions_run=actions_run,
        blocked_reasons=[],
        warnings=list(dict.fromkeys(warnings)),
        next_actions=[],
        next_required_action="none",
        knowledge_closeout={
            **knowledge_closeout,
            "provider_ask_clean": True,
            "sync_state": "synced",
        },
        task_closeout={**task_closeout, "convergence_required": False},
        closeout_complete=True,
        implementation_ready=implementation_ready,
        safe_to_continue=True,
        mutation=mutation,
    )
    payload["closeout_state"] = status.get("closeout_state") or "no_ssot_change_product_ready"
    env = success_envelope(
        command=command,
        project_id=project_id,
        mode=mode,
        data=payload,
        warnings=payload["warnings"],
        next_actions=[],
    )
    return _finish_closeout(env, apply=apply, effects=completed_effects)
