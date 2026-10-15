"""Vibe Gateway — thin intent router to existing Engine surfaces.

Gateway owns intent normalization and routing only. It does not store repo facts,
recompute readiness, mutate providers/task cache, or become a second state engine.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from vibe_control.evidence import build_evidence_v1
from vibe_control.json_envelope import (
    attach_operation_result,
    failure_envelope,
    next_action,
    success_envelope,
)
from vibe_control.progress_brief import read_git_status_short, read_observed_head

GATEWAY_VERSION = "vibe.gateway.v1"

# Canonical readonly routes (accepted Gateway scope).
ROUTE_TABLE: dict[str, dict[str, Any]] = {
    "status": {
        "engine_command": "vibe progress --json",
        "engine_surface": "progress",
        "delegate": "progress",
        "mutation": False,
        "reason": "Status/readiness projection via Engine Progress",
    },
    "what_next": {
        "engine_command": "vibe implementation next --json",
        "engine_surface": "implementation.next",
        "delegate": "next",
        "mutation": False,
        "reason": "Next actionable task from roadmap-state projection",
    },
    "get_prompt": {
        "engine_command": "vibe implementation prompt --task <selector> --json",
        "engine_surface": "implementation.prompt",
        "delegate": "prompt",
        "mutation": False,
        "reason": "Readonly implementation prompt from Engine",
    },
    "why_blocked": {
        "engine_command": "vibe progress --json",
        "engine_surface": "progress",
        "delegate": "progress",
        "mutation": False,
        "reason": "Blocked reasons projected from Engine Progress",
    },
    "summary": {
        "engine_command": "vibe progress --json",
        "engine_surface": "progress",
        "delegate": "progress",
        "mutation": False,
        "reason": "Current-state summary via Engine Progress",
    },
    "brief": {
        "engine_command": "vibe brief --json",
        "engine_surface": "brief",
        "delegate": "brief",
        "mutation": False,
        "reason": "Short action-oriented brief via Engine Brief",
    },
    "prepare_closeout": {
        "engine_command": "vibe closeout run --dry-run --json",
        "engine_surface": "closeout.dry_run",
        "delegate": "closeout",
        "mutation": False,
        "reason": "Readonly closeout dry-run only (Gateway never applies)",
    },
    "verify_after_work": {
        "engine_command": "vibe closeout run --dry-run --json",
        "engine_surface": "closeout.dry_run",
        "delegate": "closeout",
        "mutation": False,
        "reason": "Readonly post-work verification via closeout dry-run",
    },
    "grill_brief": {
        "engine_command": "vibe brief --json",
        "engine_surface": "brief",
        "delegate": "grill_brief",
        "mutation": True,
        "reason": (
            "Brief projection plus self-grill communication contract "
            "(local_runtime_write when opening a new session; Knowledge probe-only)"
        ),
    },
    "skill_assay_brief": {
        "engine_command": "vibe skill-assay brief --json",
        "engine_surface": "skill_assay.brief",
        "delegate": "skill_assay_brief",
        "mutation": False,
        "reason": (
            "Skill Assay agent entry: communication contract + next_actions "
            "(optional --skill / --host binding; does not execute host runs)"
        ),
    },
}

INTENT_ALIASES: dict[str, str] = {
    "status": "status",
    "readiness": "status",
    "what_next": "what_next",
    "what-next": "what_next",
    "next": "what_next",
    "get_prompt": "get_prompt",
    "get-prompt": "get_prompt",
    "prompt": "get_prompt",
    "why_blocked": "why_blocked",
    "why-blocked": "why_blocked",
    "blocked": "why_blocked",
    "summary": "summary",
    "progress": "summary",
    "brief": "brief",
    "prepare_closeout": "prepare_closeout",
    "prepare-closeout": "prepare_closeout",
    "closeout": "prepare_closeout",
    "verify_after_work": "verify_after_work",
    "verify-after-work": "verify_after_work",
    "verify": "verify_after_work",
    "grill_brief": "grill_brief",
    "grill-brief": "grill_brief",
    "self_grill": "grill_brief",
    "self-grill": "grill_brief",
    "grill": "grill_brief",
    "skill_assay_brief": "skill_assay_brief",
    "skill-assay-brief": "skill_assay_brief",
    "skill_assay": "skill_assay_brief",
    "skill-assay": "skill_assay_brief",
    "assay": "skill_assay_brief",
    "assay_brief": "skill_assay_brief",
}

# Explicit fail-closed mutation / raw-provider intents (stub refusal only).
FORBIDDEN_INTENTS: dict[str, str] = {
    "closeout_apply": "Gateway refuses closeout apply; use explicit Engine closeout with approval",
    "task_apply": "Gateway refuses task apply; use explicit Engine task apply with approval",
    "cache_reset_apply": "Gateway refuses task cache reset apply",
    "raw_bd": "Gateway refuses raw bd; use vibe task CLI surfaces only",
    "raw_provider": "Gateway refuses raw provider commands",
    "notebooklm_apply": "Gateway refuses NotebookLM mutation",
    "knowledge_sync_apply": "Gateway refuses knowledge sync apply; use bounded closeout Engine path",
}

DelegateMap = dict[str, Callable[..., dict[str, Any]]]


def normalize_intent(intent: str) -> str | None:
    key = str(intent or "").strip().lower().replace(" ", "_")
    if not key:
        return None
    if key in FORBIDDEN_INTENTS:
        return key
    return INTENT_ALIASES.get(key)


def _default_progress(*, repo_root: Path) -> dict[str, Any]:
    from vibe_control.progress_brief import build_progress

    return build_progress(repo_root=repo_root)


def _default_brief(*, repo_root: Path) -> dict[str, Any]:
    from vibe_control.progress_brief import build_brief

    return build_brief(repo_root=repo_root)


def _default_grill_brief(*, repo_root: Path) -> dict[str, Any]:
    from vibe_control.progress_brief import build_brief

    return build_brief(repo_root=repo_root, communication_mode="self_grill")


def _default_skill_assay_brief(
    *,
    repo_root: Path,
    skill: str | None = None,
    host: str | None = None,
) -> dict[str, Any]:
    from vibe_control.skill_assay.brief import build_skill_assay_brief

    return build_skill_assay_brief(repo_root=repo_root, skill_path=skill, host_id=host)


def _default_next(*, repo_root: Path) -> dict[str, Any]:
    from vibe_control.implementation.next import build_implementation_next

    return build_implementation_next(repo_root=repo_root)


def _default_prompt(*, repo_root: Path, task_selector: str) -> dict[str, Any]:
    from vibe_control.implementation.cli import run_implementation_prompt

    return run_implementation_prompt(
        repo_root=repo_root,
        task_selector=task_selector,
        include_provider_probe=True,
    )


def _default_closeout(*, repo_root: Path, apply: bool = False) -> dict[str, Any]:
    from vibe_control.closeout_runner import run_closeout

    # Gateway hard-binds apply=False for prepare/verify routes.
    del apply
    return run_closeout(repo_root=repo_root, apply=False)


def _resolve_task_selector(
    *,
    repo_root: Path,
    task: str | None,
    delegates: DelegateMap,
) -> tuple[str | None, dict[str, Any] | None]:
    if task and str(task).strip():
        return str(task).strip(), None
    next_fn = delegates.get("next") or (lambda **kw: _default_next(repo_root=kw["repo_root"]))
    next_env = next_fn(repo_root=repo_root)
    next_data = dict(next_env.get("data") or {})
    selector = next_data.get("next_actionable_task")
    if selector:
        return str(selector), next_env
    return None, next_env


def _safe_next_from_engine(engine_payload: dict[str, Any]) -> dict[str, Any] | None:
    data = engine_payload.get("data")
    if isinstance(data, dict):
        safe = data.get("safe_next_action")
        if isinstance(safe, dict) and safe.get("code"):
            return dict(safe)
    for item in engine_payload.get("next_actions") or []:
        if isinstance(item, dict) and item.get("code"):
            return dict(item)
    return None


def route_gateway(
    *,
    intent: str,
    repo_root: Path,
    task: str | None = None,
    skill: str | None = None,
    host: str | None = None,
    delegates: DelegateMap | None = None,
) -> dict[str, Any]:
    """Route an intent to an Engine surface and wrap Engine evidence."""
    root = Path(repo_root)
    delegates = dict(delegates or {})
    original = str(intent or "").strip()
    normalized = normalize_intent(original)

    if normalized is None:
        return failure_envelope(
            command="vibe gateway",
            code="GATEWAY_UNKNOWN_INTENT",
            message=f"Unknown Gateway intent: {original!r}",
            next_actions=[
                next_action(
                    code="GATEWAY_STATUS",
                    command="vibe gateway --intent status --json",
                    mutation=False,
                    reason="List-safe status route via Engine Progress",
                )
            ],
        )

    if normalized in FORBIDDEN_INTENTS:
        refused = failure_envelope(
            command="vibe gateway",
            code="GATEWAY_ROUTE_REFUSED",
            message=FORBIDDEN_INTENTS[normalized],
            details={
                "intent": original,
                "route": normalized,
                "source_of_truth": "engine",
                "facts_embedded": False,
                "mutation_allowed": False,
            },
            next_actions=[
                next_action(
                    code="USE_ENGINE_READONLY",
                    command="vibe gateway --intent status --json",
                    mutation=False,
                    reason="Prefer Gateway readonly routes; mutation requires explicit Engine apply",
                )
            ],
        )
        refused["mutation"] = False
        return attach_operation_result(refused, mutation_intent=False, effects=[])

    route_meta = ROUTE_TABLE[normalized]
    engine_command = str(route_meta["engine_command"])
    engine_surface = str(route_meta["engine_surface"])
    delegate_name = str(route_meta["delegate"])

    if delegate_name == "progress":
        progress_fn = delegates.get("progress") or (
            lambda **kw: _default_progress(repo_root=kw["repo_root"])
        )
        engine_payload = progress_fn(repo_root=root)
    elif delegate_name == "brief":
        brief_fn = delegates.get("brief") or (
            lambda **kw: _default_brief(repo_root=kw["repo_root"])
        )
        engine_payload = brief_fn(repo_root=root)
    elif delegate_name == "grill_brief":
        grill_fn = delegates.get("grill_brief") or (
            lambda **kw: _default_grill_brief(repo_root=kw["repo_root"])
        )
        engine_payload = grill_fn(repo_root=root)
    elif delegate_name == "skill_assay_brief":
        assay_fn = delegates.get("skill_assay_brief") or (
            lambda **kw: _default_skill_assay_brief(
                repo_root=kw["repo_root"],
                skill=kw.get("skill"),
                host=kw.get("host"),
            )
        )
        engine_payload = assay_fn(repo_root=root, skill=skill, host=host)
        if skill:
            engine_command = (
                f"vibe skill-assay brief --skill {skill}"
                + (f" --host {host}" if host else "")
                + " --json"
            )
    elif delegate_name == "next":
        next_fn = delegates.get("next") or (
            lambda **kw: _default_next(repo_root=kw["repo_root"])
        )
        engine_payload = next_fn(repo_root=root)
    elif delegate_name == "prompt":
        selector, next_env = _resolve_task_selector(
            repo_root=root, task=task, delegates=delegates
        )
        if not selector:
            refused = failure_envelope(
                command="vibe gateway",
                code="GATEWAY_TASK_REQUIRED",
                message="get_prompt requires --task or an actionable next task from Engine",
                details={"next_payload": (next_env or {}).get("data")},
                next_actions=[
                    next_action(
                        code="IMPLEMENTATION_NEXT",
                        command="vibe implementation next --json",
                        mutation=False,
                        reason="Discover next actionable task from Engine",
                    )
                ],
            )
            refused["mutation"] = False
            return attach_operation_result(refused, mutation_intent=False, effects=[])
        engine_command = f"vibe implementation prompt --task {selector} --json"
        prompt_fn = delegates.get("prompt") or (
            lambda **kw: _default_prompt(
                repo_root=kw["repo_root"], task_selector=kw["task_selector"]
            )
        )
        engine_payload = prompt_fn(repo_root=root, task_selector=selector)
    elif delegate_name == "closeout":
        closeout_fn = delegates.get("closeout") or (
            lambda **kw: _default_closeout(repo_root=kw["repo_root"], apply=False)
        )
        # Always force apply=False even if a custom delegate accepts the kw.
        engine_payload = closeout_fn(repo_root=root, apply=False)
    else:  # pragma: no cover - static table guard
        return failure_envelope(
            command="vibe gateway",
            code="GATEWAY_INTERNAL_ROUTE_ERROR",
            message=f"No delegate for route {normalized}",
        )

    if not isinstance(engine_payload, dict):
        return failure_envelope(
            command="vibe gateway",
            code="GATEWAY_ENGINE_PAYLOAD_INVALID",
            message="Engine delegate returned a non-object payload",
        )

    # Pass through Engine mutation evidence. Gateway itself does not invent writes;
    # grill_brief may report local_runtime_write via Engine payload.
    engine_intent = engine_payload.get("mutation_intent")
    if not isinstance(engine_intent, bool):
        engine_intent = bool(route_meta.get("mutation")) and bool(
            engine_payload.get("mutation") or engine_payload.get("mutation_performed")
        )
        if normalized == "grill_brief":
            # Opening a self-grill session has write intent even when reused (no effect).
            engine_intent = True
        elif not route_meta.get("mutation"):
            engine_intent = False
    engine_effects: list[dict[str, Any]] = []
    raw_effects = engine_payload.get("effects")
    if isinstance(raw_effects, list):
        engine_effects = [e for e in raw_effects if isinstance(e, dict)]
    engine_mutation = bool(engine_payload.get("mutation_performed", engine_payload.get("mutation", False)))
    if engine_effects:
        engine_mutation = True
    safe_next = _safe_next_from_engine(engine_payload)
    next_actions = list(engine_payload.get("next_actions") or [])
    if safe_next and not any(
        isinstance(a, dict) and a.get("code") == safe_next.get("code") for a in next_actions
    ):
        next_actions = [safe_next, *next_actions]
    if not next_actions and safe_next:
        next_actions = [safe_next]

    warnings = list(engine_payload.get("warnings") or [])
    warnings.append("gateway_thin_router: source_of_truth=engine; facts_embedded=false")
    # Route success is not Engine success — consumers must check engine_payload.ok.
    engine_ok = bool(engine_payload.get("ok", True))
    if not engine_ok:
        warnings.append("gateway_engine_failed: outer ok=false mirrors engine_payload.ok")

    engine_data = engine_payload.get("data") if isinstance(engine_payload.get("data"), dict) else {}
    observed = str(engine_data.get("observed_head") or read_observed_head(root))
    baseline = engine_data.get("recorded_baseline_commit")
    git_empty = engine_data.get("git_status_short_empty")
    if git_empty is None:
        git_empty = read_git_status_short(root) == ""
    gateway_mode = (
        "local_runtime_write" if normalized == "grill_brief" else "readonly_gateway"
    )
    gateway_evidence = build_evidence_v1(
        operation="gateway",
        mode=gateway_mode,
        observed_head_value=observed,
        git_status_short_empty=bool(git_empty),
        generated_from=[
            f"gateway route:{normalized}",
            engine_command,
            "engine_payload (pass-through)",
        ],
        steps=[
            "normalize_intent",
            "route_to_engine_delegate",
            "wrap_engine_payload",
            "embed_evidence_v1",
        ],
        blocked_reasons=list(engine_data.get("blocked_reasons") or []),
        next_actions=next_actions,
        recorded_baseline_commit=str(baseline) if baseline else None,
        projected_fields={
            k: engine_data.get(k)
            for k in (
                "product_ready",
                "provider_sync_required",
                "provider_ask_clean",
                "task_cache_current",
                "implementation_ready",
                "next_actionable_task",
                "no_actionable_next_task",
                "blocked_reasons",
            )
            if k in engine_data
        }
        or None,
        mutation_intent=engine_intent,
        effects=engine_effects,
        approval_class="local_runtime_write" if engine_intent else "readonly",
    )

    data = {
        "gateway_version": GATEWAY_VERSION,
        "gateway": True,
        "route": normalized,
        "intent": original,
        "engine_command": engine_command,
        "engine_surface": engine_surface,
        "engine_payload": engine_payload,
        "source_of_truth": "engine",
        "facts_embedded": False,
        "mutation": engine_mutation,
        "engine_reported_mutation": engine_mutation,
        "safe_next": safe_next,
        "evidence": gateway_evidence,
        "evidence_hash": gateway_evidence["evidence_hash"],
        "authority": {
            "engine": "Vibe Control Engine",
            "gateway": "thin intent router only",
            "repo_ssot": True,
            "chatgpt_project_sources": (
                "external advisor context copies only; not a product closeout gate"
            ),
            "provider_task_id": "binding result only; never source identity",
        },
    }
    # why_blocked: pass-through Engine blocked_reasons only (no recomputation).
    if normalized == "why_blocked":
        if isinstance(engine_data, dict):
            data["blocked_reasons"] = list(engine_data.get("blocked_reasons") or [])
            data["blocked_reasons_source"] = "engine_payload.data.blocked_reasons"

    if engine_ok:
        envelope = success_envelope(
            command="vibe gateway",
            project_id=(
                engine_payload.get("project_id") if isinstance(engine_payload, dict) else None
            ),
            mode=gateway_mode,
            data=data,
            warnings=warnings,
            next_actions=next_actions,
        )
        out = attach_operation_result(
            envelope,
            mutation_intent=engine_intent,
            effects=engine_effects,
        )
        if isinstance(out.get("data"), dict):
            out["data"]["mutation"] = out["mutation_performed"]
        return out

    failed = failure_envelope(
        command="vibe gateway",
        code="GATEWAY_ENGINE_FAILED",
        message="Engine surface returned ok=false; Gateway preserves engine_payload for review",
        details=data,
        project_id=(
            engine_payload.get("project_id") if isinstance(engine_payload, dict) else None
        ),
        warnings=warnings,
        next_actions=next_actions,
    )
    failed["data"] = data
    out = attach_operation_result(
        failed,
        mutation_intent=engine_intent,
        effects=engine_effects,
    )
    if isinstance(out.get("data"), dict):
        out["data"]["mutation"] = out["mutation_performed"]
    return out
