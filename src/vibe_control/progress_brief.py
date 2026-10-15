"""Readonly Vibe Progress / Brief projections with embedded Evidence v1 (S1).

Projection-only: consumes existing Engine outputs; does not recompute readiness,
closeout, task cache, or roadmap next selection.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from vibe_control.evidence import EVIDENCE_VERSION, build_evidence_v1
from vibe_control.implementation.prompt import compute_implementation_ready
from vibe_control.json_envelope import attach_operation_result, next_action, success_envelope
from vibe_control.components import project_capability_guidance
from vibe_control.task.roadmap_state import load_roadmap_state

# Re-export for callers/tests that historically imported from this module.
__all__ = [
    "EVIDENCE_VERSION",
    "PROGRESS_SCHEMA",
    "BRIEF_VERSION",
    "build_evidence_v1",
    "build_progress",
    "build_brief",
    "derive_principal_blocker",
    "read_observed_head",
    "read_git_status_short",
]

PROGRESS_SCHEMA = "vibe.progress.v1"
BRIEF_VERSION = "vibe.brief.v1"


def _run_git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    return (result.stdout or "").strip()


def read_observed_head(repo_root: Path) -> str:
    return _run_git(repo_root, "rev-parse", "HEAD")


def read_git_status_short(repo_root: Path) -> str:
    return _run_git(repo_root, "status", "--short")


def _recorded_baseline_commit(repo_root: Path) -> str | None:
    try:
        state = load_roadmap_state(repo_root)
    except Exception:
        return None
    baseline = state.get("current_baseline") or {}
    value = baseline.get("baseline_commit")
    return str(value) if value else None


def _kp(status: dict[str, Any]) -> dict[str, Any]:
    return dict(status.get("knowledge_provider") or {})


def _project_shared_fields(
    *,
    status: dict[str, Any],
    next_selection: dict[str, Any],
) -> dict[str, Any]:
    """Project shared readiness/next fields from Engine sources only."""
    kp = _kp(status)
    components = dict(status.get("components") or {})
    cap = dict(status.get("capability_profile") or {})
    if "knowledge_enabled" in cap:
        knowledge_enabled = bool(cap.get("knowledge_enabled"))
        task_enabled = bool(cap.get("task_enabled"))
    elif components:
        knowledge_enabled = bool((components.get("knowledge") or {}).get("enabled"))
        task_enabled = bool((components.get("task") or {}).get("enabled"))
    else:
        # Legacy/fixture payloads without capability profile: keep raw provider gates.
        knowledge_enabled = True
        task_enabled = True
    raw_sync_state = kp.get("sync_state")
    raw_ask_clean = bool(kp.get("provider_ask_clean"))
    raw_cache = bool(status.get("task_cache_current"))
    # Capability Profile: disabled capabilities do not gate Progress/Brief readiness.
    sync_state = "synced" if not knowledge_enabled else raw_sync_state
    provider_ask_clean = True if not knowledge_enabled else raw_ask_clean
    task_cache_current = True if not task_enabled else raw_cache
    product_ready = bool(status.get("product_ready"))
    config_ok = bool(status.get("config_ok", True))
    provider_sync_required = bool(status.get("provider_sync_required"))
    closeout_complete = bool(status.get("closeout_complete"))
    blocked_reasons = list(status.get("blocked_reasons") or [])
    no_next = bool(next_selection.get("no_actionable_next_task"))
    next_task = next_selection.get("next_actionable_task")
    if no_next:
        next_task = None
    task_completed = False
    if next_task is None:
        task_completed = True
    implementation_ready = compute_implementation_ready(
        task_completed=task_completed,
        product_ready=product_ready,
        provider_sync_required=provider_sync_required,
        sync_state=sync_state,
        provider_ask_clean=provider_ask_clean,
        task_cache_current=task_cache_current,
        config_ok=config_ok,
        knowledge_enabled=knowledge_enabled,
        task_enabled=task_enabled,
    )
    return {
        "product_ready": product_ready,
        "config_ok": config_ok,
        "provider_sync_required": provider_sync_required,
        "sync_state": sync_state,
        "provider_ask_clean": provider_ask_clean,
        "knowledge_available": bool(kp.get("available")) if knowledge_enabled else True,
        "task_cache_current": task_cache_current,
        "closeout_complete": closeout_complete,
        "closeout_state": status.get("closeout_state"),
        "implementation_ready": implementation_ready,
        "next_actionable_task": next_task,
        "no_actionable_next_task": no_next,
        "blocked_reasons": blocked_reasons,
        "components": components,
        "capability_profile": dict(status.get("capability_profile") or {}),
        "capability_guidance": project_capability_guidance(
            components=components,
            capability_profile=dict(status.get("capability_profile") or {}),
        ),
        "knowledge_enabled": knowledge_enabled,
        "task_enabled": task_enabled,
    }


def _safe_next_action(shared: dict[str, Any], next_selection: dict[str, Any]) -> dict[str, Any]:
    knowledge_enabled = bool(shared.get("knowledge_enabled", True))
    task_enabled = bool(shared.get("task_enabled", True))
    if shared["provider_sync_required"] or not shared["closeout_complete"]:
        return next_action(
            code="RUN_BOUNDED_KNOWLEDGE_SYNC",
            command="vibe closeout run --dry-run --json",
            mutation=False,
            reason="SSOT closeout incomplete; prefer vibe closeout run before implementation",
        )
    if knowledge_enabled and (
        not shared["provider_ask_clean"] or shared["sync_state"] not in (None, "synced")
    ):
        return next_action(
            code="SSOT_CLOSEOUT_INCOMPLETE",
            command="vibe closeout run --dry-run --json",
            mutation=False,
            reason="Knowledge sync/ask hygiene not clean",
        )
    if task_enabled and not shared["task_cache_current"]:
        return next_action(
            code="TASK_CONVERGENCE_REQUIRED",
            command="vibe task apply --dry-run --json --provider beads",
            mutation=False,
            reason="Task cache not current; converge under Approval Matrix / Option A gates",
        )
    if shared["no_actionable_next_task"] or not shared["next_actionable_task"]:
        return next_action(
            code="NO_ACTIONABLE_NEXT_TASK",
            command="cat docs/project/vibe-control-roadmap-state.md",
            mutation=False,
            reason="Roadmap-state has no actionable next; do not invent Phase 13",
        )
    if shared["implementation_ready"]:
        task = shared["next_actionable_task"]
        return next_action(
            code="IMPLEMENTATION_PROMPT",
            command=f"vibe implementation prompt --task {task} --json",
            mutation=False,
            reason="Generate readonly prompt for current actionable task",
        )
    return next_action(
        code="CHECK_INTEGRATION_STATUS",
        command="vibe integration status --json",
        mutation=False,
        reason="Implementation not ready; inspect blocked_reasons",
    )


# safe_next_action.code → preferred substrings in existing blocked_reasons (order = priority).
# Projection only — does not invent readiness; falls back when reasons are empty.
_PRINCIPAL_REASON_PREFER: dict[str, tuple[str, ...]] = {
    "RUN_BOUNDED_KNOWLEDGE_SYNC": (
        "local_modifications_present",
        "provider_sync_required",
        "knowledge_sync",
        "ask_hygiene",
        "sync_state",
    ),
    "SSOT_CLOSEOUT_INCOMPLETE": (
        "ask_hygiene",
        "knowledge_sync",
        "provider_ask",
        "sync_state",
    ),
    "TASK_CONVERGENCE_REQUIRED": ("task_cache",),
    "NO_ACTIONABLE_NEXT_TASK": ("no_actionable",),
    "CHECK_INTEGRATION_STATUS": (),
    "CONTINUE_SELF_GRILL": ("self_grill_in_progress",),
}

_PRINCIPAL_FALLBACK: dict[str, str] = {
    "RUN_BOUNDED_KNOWLEDGE_SYNC": "closeout_incomplete",
    "SSOT_CLOSEOUT_INCOMPLETE": "closeout_incomplete",
    "TASK_CONVERGENCE_REQUIRED": "task_cache_not_current",
    "NO_ACTIONABLE_NEXT_TASK": "no_actionable_next_task",
    "CHECK_INTEGRATION_STATUS": "implementation_not_ready",
    "CONTINUE_SELF_GRILL": "self_grill_in_progress",
}

# Closeout / sync / task-cache blockers keep ownership of safe_next over grill pull-back.
_CLOSEOUT_OWNED_SAFE_CODES = frozenset(
    {
        "RUN_BOUNDED_KNOWLEDGE_SYNC",
        "SSOT_CLOSEOUT_INCOMPLETE",
        "TASK_CONVERGENCE_REQUIRED",
    }
)


def _apply_self_grill_pullback(
    *,
    repo_root: Path,
    shared: dict[str, Any],
    safe: dict[str, Any],
    next_actions: list[Any],
) -> tuple[dict[str, Any], list[Any], dict[str, Any] | None]:
    """When a local grill session is IN_PROGRESS, project pull-back (not readiness)."""
    from vibe_control.grill_session import active_in_progress
    from vibe_control.self_grill_contract import self_grill_continue_next_action

    sess = active_in_progress(repo_root)
    if not sess:
        return safe, next_actions, None

    if "self_grill_in_progress" not in shared["blocked_reasons"]:
        shared["blocked_reasons"] = [
            "self_grill_in_progress",
            *shared["blocked_reasons"],
        ]

    grill_next = self_grill_continue_next_action()
    grill_next = {
        **grill_next,
        "reason": (
            f"{grill_next.get('reason')} "
            f"[grill_id={sess.get('grill_id')} round_id={sess.get('round_id')}]"
        ),
    }

    actions = [a for a in next_actions if isinstance(a, dict)]
    others = [a for a in next_actions if not isinstance(a, dict)]
    without_grill = [a for a in actions if a.get("code") != "CONTINUE_SELF_GRILL"]

    if safe.get("code") in _CLOSEOUT_OWNED_SAFE_CODES:
        next_out: list[Any] = [safe, grill_next, *without_grill[1:], *others]
        return safe, next_out, sess

    next_out = [grill_next, *[a for a in without_grill if a.get("code") != safe.get("code")], *others]
    return grill_next, next_out, sess


def derive_principal_blocker(
    shared: dict[str, Any],
    safe: dict[str, Any],
) -> str | None:
    """Name the current principal blocker from existing projection outputs.

    Pure adapter over ``blocked_reasons`` + ``safe_next_action`` — not a second
    readiness engine. Returns None when safe_next is IMPLEMENTATION_PROMPT.
    """
    code = str((safe or {}).get("code") or "")
    if not code or code == "IMPLEMENTATION_PROMPT":
        return None
    reasons = [str(r) for r in (shared.get("blocked_reasons") or []) if r]
    for needle in _PRINCIPAL_REASON_PREFER.get(code, ()):
        for reason in reasons:
            if needle == reason or needle in reason:
                return reason
    if reasons:
        return reasons[0]
    return _PRINCIPAL_FALLBACK.get(code)


def _load_engine_sources(
    repo_root: Path,
    *,
    integration_status: dict[str, Any] | None,
    next_selection: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if integration_status is None:
        from vibe_control.integration import build_integration_status

        status = build_integration_status(
            repo_root=repo_root, probe_auth=False, probe_product=True
        )
    else:
        status = dict(integration_status)
    if next_selection is None:
        from vibe_control.task.projection import next_actionable_selection

        selection = next_actionable_selection(repo_root=repo_root)
    else:
        selection = dict(next_selection)
    return status, selection


def _apply_capability_gate_projection(shared: dict[str, Any]) -> None:
    """Re-apply Capability Profile effective gates after closeout overlays."""
    if not shared.get("knowledge_enabled", True):
        shared["sync_state"] = "synced"
        shared["provider_ask_clean"] = True
        shared["knowledge_available"] = True
    if not shared.get("task_enabled", True):
        shared["task_cache_current"] = True
    shared["implementation_ready"] = compute_implementation_ready(
        task_completed=bool(shared.get("no_actionable_next_task"))
        or not shared.get("next_actionable_task"),
        product_ready=bool(shared.get("product_ready")),
        provider_sync_required=bool(shared.get("provider_sync_required")),
        sync_state=shared.get("sync_state"),
        provider_ask_clean=shared.get("provider_ask_clean"),
        task_cache_current=bool(shared.get("task_cache_current")),
        config_ok=bool(shared.get("config_ok", True)),
        knowledge_enabled=bool(shared.get("knowledge_enabled", True)),
        task_enabled=bool(shared.get("task_enabled", True)),
    )


def build_progress(
    *,
    repo_root: Path,
    integration_status: dict[str, Any] | None = None,
    next_selection: dict[str, Any] | None = None,
    closeout_data: dict[str, Any] | None = None,
    observed_head: str | None = None,
    git_status_short: str | None = None,
    recorded_baseline_commit: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    status, selection = _load_engine_sources(
        repo_root,
        integration_status=integration_status,
        next_selection=next_selection,
    )
    head = observed_head if observed_head is not None else read_observed_head(repo_root)
    status_text = (
        git_status_short
        if git_status_short is not None
        else read_git_status_short(repo_root)
    )
    baseline = (
        recorded_baseline_commit
        if recorded_baseline_commit is not None
        else _recorded_baseline_commit(repo_root)
    )
    shared = _project_shared_fields(status=status, next_selection=selection)
    if closeout_data is None and status_text != "":
        # Match closeout dry-run fail-closed behavior when local mods are present.
        shared["closeout_complete"] = False
        shared["implementation_ready"] = False
        if "local_modifications_present" not in shared["blocked_reasons"]:
            shared["blocked_reasons"] = [
                "local_modifications_present",
                *shared["blocked_reasons"],
            ]
    elif closeout_data is not None:
        for key in (
            "closeout_complete",
            "implementation_ready",
            "provider_sync_required",
            "sync_state",
            "provider_ask_clean",
            "task_cache_current",
        ):
            if key in closeout_data:
                shared[key] = closeout_data[key]
        if closeout_data.get("blocked_reasons") is not None:
            shared["blocked_reasons"] = list(closeout_data.get("blocked_reasons") or [])
    elif closeout_data is None and integration_status is None:
        # Live path with clean tree: overlay closeout dry-run overlap fields.
        from vibe_control.closeout_runner import run_closeout

        closeout_env = run_closeout(repo_root=repo_root, apply=False)
        cdata = dict(closeout_env.get("data") or {})
        for key in (
            "closeout_complete",
            "implementation_ready",
            "provider_sync_required",
            "sync_state",
            "provider_ask_clean",
            "task_cache_current",
        ):
            if key in cdata:
                shared[key] = cdata[key]
    if status_text == "":
        _apply_capability_gate_projection(shared)
    safe = _safe_next_action(shared, selection)
    next_actions = [safe]
    # Preserve Engine next_actions when present (projection, not invention).
    for action in status.get("next_actions") or []:
        if isinstance(action, dict) and action.get("code") != safe.get("code"):
            next_actions.append(action)
    # Project Capability Profile enable/config guidance without replacing safe_next.
    for action in (shared.get("capability_guidance") or {}).get("next_actions") or []:
        if not isinstance(action, dict):
            continue
        code = action.get("code")
        if code and not any(
            isinstance(a, dict) and a.get("code") == code for a in next_actions
        ):
            next_actions.append(action)
    if not shared["no_actionable_next_task"] and shared["implementation_ready"]:
        # Ensure prompt next_action is present even if status had unrelated actions.
        if not any(
            a.get("code") == "IMPLEMENTATION_PROMPT"
            for a in next_actions
            if isinstance(a, dict)
        ):
            next_actions = [safe]
            for action in (shared.get("capability_guidance") or {}).get("next_actions") or []:
                if isinstance(action, dict) and action.get("code"):
                    next_actions.append(action)

    safe, next_actions, grill_sess = _apply_self_grill_pullback(
        repo_root=repo_root,
        shared=shared,
        safe=safe,
        next_actions=next_actions,
    )
    principal = derive_principal_blocker(shared, safe)

    generated_from = [
        "vibe integration status",
        "vibe implementation next",
        "vibe closeout run --dry-run (overlapping fields via integration closeout projection)",
        "compute_implementation_ready",
    ]
    steps = [
        "observe_git_head",
        "observe_git_status_short",
        "project_integration_status",
        "project_implementation_next",
        "derive_safe_next_action",
        "apply_self_grill_pullback",
        "derive_principal_blocker",
        "embed_evidence_v1",
    ]
    evidence = build_evidence_v1(
        operation="progress",
        mode="readonly_progress",
        observed_head_value=head,
        git_status_short_empty=status_text == "",
        generated_from=generated_from,
        steps=steps,
        blocked_reasons=shared["blocked_reasons"],
        next_actions=next_actions,
        run_id=run_id,
        recorded_baseline_commit=baseline,
        projected_fields=shared,
    )
    data = {
        "schema_version": PROGRESS_SCHEMA,
        "mutation": False,
        "observed_head": head,
        "git_status_short_empty": status_text == "",
        "recorded_baseline_commit": baseline,
        **shared,
        "safe_next_action": safe,
        "principal_blocker": principal,
        "next_actions": next_actions,
        "evidence": evidence,
    }
    if grill_sess is not None:
        data["grill_session"] = {
            "grill_id": grill_sess.get("grill_id"),
            "round_id": grill_sess.get("round_id"),
            "loop_status": grill_sess.get("loop_status"),
            "thesis": grill_sess.get("thesis"),
        }
    envelope = success_envelope(
        command="vibe progress",
        project_id=status.get("project_id"),
        mode="readonly_progress",
        data=data,
        warnings=list(status.get("warnings") or []),
        next_actions=next_actions,
    )
    return attach_operation_result(envelope, mutation_intent=False, effects=[])


def build_brief(
    *,
    repo_root: Path,
    integration_status: dict[str, Any] | None = None,
    next_selection: dict[str, Any] | None = None,
    closeout_data: dict[str, Any] | None = None,
    observed_head: str | None = None,
    git_status_short: str | None = None,
    recorded_baseline_commit: str | None = None,
    run_id: str | None = None,
    communication_mode: str | None = None,
) -> dict[str, Any]:
    status, selection = _load_engine_sources(
        repo_root,
        integration_status=integration_status,
        next_selection=next_selection,
    )
    head = observed_head if observed_head is not None else read_observed_head(repo_root)
    status_text = (
        git_status_short
        if git_status_short is not None
        else read_git_status_short(repo_root)
    )
    baseline = (
        recorded_baseline_commit
        if recorded_baseline_commit is not None
        else _recorded_baseline_commit(repo_root)
    )
    shared = _project_shared_fields(status=status, next_selection=selection)
    if closeout_data is not None:
        for key in (
            "closeout_complete",
            "implementation_ready",
            "provider_sync_required",
            "sync_state",
            "provider_ask_clean",
            "task_cache_current",
        ):
            if key in closeout_data:
                shared[key] = closeout_data[key]
        if closeout_data.get("blocked_reasons") is not None:
            shared["blocked_reasons"] = list(closeout_data.get("blocked_reasons") or [])
    elif status_text != "":
        shared["closeout_complete"] = False
        shared["implementation_ready"] = False
        if "local_modifications_present" not in shared["blocked_reasons"]:
            shared["blocked_reasons"] = [
                "local_modifications_present",
                *shared["blocked_reasons"],
            ]
    if status_text == "":
        _apply_capability_gate_projection(shared)
    safe = _safe_next_action(shared, selection)
    next_actions = [safe]
    communication_contract: dict[str, Any] | None = None
    opened_session: dict[str, Any] | None = None
    mode = str(communication_mode or "").strip().lower()
    if mode in {"self_grill", "grill"}:
        from vibe_control.grill_session import open_session
        from vibe_control.self_grill_contract import self_grill_contract_dict

        communication_contract = self_grill_contract_dict()
        opened_session = open_session(
            repo_root,
            thesis="self-grill interrogation via grill_brief",
            force_new=False,
        )
        summary = (
            "Self-grill communication mode: interrogate your own claims using "
            "communication_contract.required_reply_shape. Knowledge is probe-only. "
            f"Session {opened_session.get('grill_id')} round_id="
            f"{opened_session.get('round_id')}. Close with "
            "`vibe grill close --status EXHAUSTED|BLOCKED_ON_LIVE --json` before "
            "implementation prompt / sufficiency claims."
        )
        goal = "exhaust self-grill frontier (LOOP_STATUS=EXHAUSTED) before sufficiency claims"

    safe, next_actions, grill_sess = _apply_self_grill_pullback(
        repo_root=repo_root,
        shared=shared,
        safe=safe,
        next_actions=next_actions,
    )
    if opened_session is not None:
        grill_sess = opened_session
    principal = derive_principal_blocker(shared, safe)

    # Brief stays concise: do not expand enable/config guidance into next_actions
    # (full guidance lives on Progress/doctor; Brief only projects concise flags).
    anchor = selection.get("anchor") if isinstance(selection.get("anchor"), dict) else None
    task: dict[str, Any] | None = None
    if shared["next_actionable_task"] and anchor:
        task = {
            "ssot_anchor": anchor.get("ssot_anchor") or shared["next_actionable_task"],
            "title": anchor.get("title"),
            "task_kind": anchor.get("task_kind"),
            "phase_state": anchor.get("phase_state"),
            "actionable": bool(anchor.get("actionable")),
        }
    elif shared["next_actionable_task"]:
        task = {
            "ssot_anchor": shared["next_actionable_task"],
            "title": None,
            "task_kind": "implementation_task",
            "phase_state": "accepted",
            "actionable": True,
        }

    if communication_contract is None:
        if grill_sess is not None:
            summary = (
                f"Self-grill IN_PROGRESS ({grill_sess.get('grill_id')} "
                f"round_id={grill_sess.get('round_id')}). Continue claim table; "
                "do not take implementation prompt until EXHAUSTED/BLOCKED_ON_LIVE."
            )
            goal = "continue self-grill until LOOP_STATUS terminal"
        elif shared["implementation_ready"] and task:
            summary = (
                f"Current actionable task: {task['ssot_anchor']}. "
                f"Implementation is allowed. Run vibe implementation prompt --task "
                f"{task['ssot_anchor']} --json for the full coding-agent prompt."
            )
            goal = task.get("title") or task["ssot_anchor"]
        elif shared["no_actionable_next_task"]:
            summary = "No actionable next task. Do not invent Phase 13."
            goal = "none"
        else:
            summary = (
                "Implementation is not ready. Follow safe_next_action before coding. "
                f"Principal blocker: {principal or 'see blocked_reasons'}."
            )
            goal = "unblock readiness / closeout"

    constraints = [
        "Repo SSOT is truth; NotebookLM is derived; Beads provider_task_id is binding only",
        "Progress/Brief project Engine outputs only; do not recompute readiness",
        "Engine readiness and Capability Profile readiness are separate",
        "Disabled capabilities do not fail product_ready; enable via control.yaml preview only",
        "Readonly surfaces must not mutate providers, task cache, or config",
        "Do not invent Phase 13 or restart completed Component Runtime slices",
        "No sub-agent routing in current scope",
    ]
    required_checks = [
        "product_ready",
        "provider_sync_required=false",
        "provider_ask_clean",
        "task_cache_current",
        "closeout_complete",
        "implementation_ready",
    ]
    approval_requirements = [
        "local git commit/land for authorized implement/land/release work is agent-owned — never ask owner 'shall I commit?'",
        "git push requires explicit owner request",
        "NotebookLM mutation outside bounded closeout requires owner approval",
        "live Beads mutation requires Option A dual gate + --autonomous-managed",
        "unmanaged adoption / destructive delete forbidden by default",
    ]

    self_grill_mode = communication_contract is not None
    grill_effects: list[dict[str, Any]] = []
    if self_grill_mode and opened_session is not None:
        if str(opened_session.get("session_action") or "") == "created":
            grill_effects = [
                {
                    "kind": "local_state_write",
                    "target": "grill.session",
                    "status": "completed",
                },
                {
                    "kind": "local_state_write",
                    "target": "grill.active",
                    "status": "completed",
                },
            ]
    mutation_intent = bool(self_grill_mode)
    brief_mode = "local_runtime_write" if mutation_intent else "readonly_brief"

    evidence = build_evidence_v1(
        operation="brief",
        mode=brief_mode,
        observed_head_value=head,
        git_status_short_empty=status_text == "",
        generated_from=[
            "vibe integration status",
            "vibe implementation next",
            "compute_implementation_ready",
        ],
        steps=[
            "observe_git_head",
            "project_integration_status",
            "project_implementation_next",
            "build_short_brief",
            "apply_self_grill_pullback",
            "derive_principal_blocker",
            "embed_evidence_v1",
        ],
        blocked_reasons=shared["blocked_reasons"],
        next_actions=next_actions,
        run_id=run_id,
        recorded_baseline_commit=baseline,
        projected_fields=shared,
        mutation_intent=mutation_intent,
        effects=grill_effects,
        approval_class="local_runtime_write" if mutation_intent else "readonly",
    )
    data = {
        "brief_version": BRIEF_VERSION,
        "mutation": bool(grill_effects),
        "observed_head": head,
        "recorded_baseline_commit": baseline,
        "git_status_short_empty": status_text == "",
        "task": task,
        "implementation_ready": shared["implementation_ready"],
        "no_actionable_next_task": shared["no_actionable_next_task"],
        "next_actionable_task": shared["next_actionable_task"],
        "product_ready": shared["product_ready"],
        "provider_sync_required": shared["provider_sync_required"],
        "provider_ask_clean": shared["provider_ask_clean"],
        "task_cache_current": shared["task_cache_current"],
        "closeout_complete": shared["closeout_complete"],
        "blocked_reasons": shared["blocked_reasons"],
        "principal_blocker": principal,
        "capability_profile": shared.get("capability_profile") or {},
        "capability_guidance": project_capability_guidance(
            components=dict(shared.get("components") or {}),
            capability_profile=dict(shared.get("capability_profile") or {}),
            concise=True,
        ),
        "knowledge_enabled": shared.get("knowledge_enabled"),
        "task_enabled": shared.get("task_enabled"),
        "goal": goal,
        "summary": summary,
        "constraints": constraints,
        "required_checks": required_checks,
        "approval_requirements": approval_requirements,
        "safe_next_action": safe,
        "next_actions": next_actions,
        "evidence": evidence,
        "evidence_hash": evidence["evidence_hash"],
    }
    if communication_contract is not None:
        data["communication_mode"] = "self_grill"
        data["communication_contract"] = communication_contract
    if grill_sess is not None:
        data["grill_session"] = {
            "grill_id": grill_sess.get("grill_id"),
            "round_id": grill_sess.get("round_id"),
            "loop_status": grill_sess.get("loop_status"),
            "thesis": grill_sess.get("thesis"),
            "session_action": grill_sess.get("session_action"),
        }
    envelope = success_envelope(
        command="vibe brief",
        project_id=status.get("project_id"),
        mode=brief_mode,
        data=data,
        warnings=list(status.get("warnings") or []),
        next_actions=next_actions,
    )
    return attach_operation_result(
        envelope,
        mutation_intent=mutation_intent,
        effects=grill_effects,
    )


def format_brief_text(envelope: dict[str, Any]) -> str:
    data = dict(envelope.get("data") or {})
    task = data.get("task") or {}
    safe = data.get("safe_next_action") or {}
    lines = [
        "Vibe Brief (readonly)",
        f"observed_head: {data.get('observed_head')}",
        f"implementation_ready: {data.get('implementation_ready')}",
        f"goal: {data.get('goal')}",
        f"summary: {data.get('summary')}",
    ]
    if task:
        lines.append(f"task: {task.get('ssot_anchor')} — {task.get('title')}")
    else:
        lines.append("task: none")
    lines.append(f"safe_next_action: {safe.get('code')} -> {safe.get('command')}")
    lines.append("constraints:")
    for item in data.get("constraints") or []:
        lines.append(f"  - {item}")
    lines.append("required_checks:")
    for item in data.get("required_checks") or []:
        lines.append(f"  - {item}")
    return "\n".join(lines) + "\n"
