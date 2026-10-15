"""Phase 12 — Implementation prompt generator (readonly)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from vibe_control.json_envelope import attach_operation_result, next_action
from vibe_control.task.projection import (
    next_actionable_selection,
    project_actionable_expected_tasks,
    project_all_expected_tasks,
)

PROMPT_SECTION_ORDER = (
    "task_goal",
    "repo_ssot_identity",
    "selected_task_anchor",
    "product_ready_summary",
    "component_runtime_readiness",
    "knowledge_readiness_summary",
    "task_reconcile_apply_summary",
    "hard_boundaries",
    "mutation_approvals",
    "required_tests_gates",
    "expected_final_report",
    "safety_confirmation",
    "final_git_status",
)


class PromptError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def _sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _id_hash(provider_task_id: str | None) -> str | None:
    if not provider_task_id:
        return None
    return "sha256:" + hashlib.sha256(provider_task_id.encode("utf-8")).hexdigest()[:12]


def resolve_expected_task(
    *,
    repo_root: Path,
    project_id: str,
    task_selector: str,
    allow_completed: bool = True,
):
    """Resolve task by selector.

    Default dogfood/next uses actionable-only projection elsewhere.
    Explicit --task may resolve completed anchors (safe envelope + warning).
    """
    actionable = project_actionable_expected_tasks(project_id=project_id, repo_root=repo_root)
    all_tasks = project_all_expected_tasks(project_id=project_id, repo_root=repo_root)
    sel = (task_selector or "").strip()
    if not sel:
        raise PromptError("TASK_SELECTOR_REQUIRED", "Pass --task managed_key|provider_task_id|ssot_anchor")
    matches = [t for t in actionable if t.managed_key == sel or t.ssot_anchor == sel]
    if not matches and allow_completed:
        matches = [t for t in all_tasks if t.managed_key == sel or t.ssot_anchor == sel]
    if len(matches) > 1:
        raise PromptError(
            "TASK_SELECTOR_AMBIGUOUS",
            f"Selector matches multiple expected tasks: {sel}",
            {
                "selector": sel,
                "matches": [
                    {"ssot_anchor": t.ssot_anchor, "managed_key": t.managed_key} for t in matches
                ],
            },
        )
    if len(matches) == 1:
        return matches[0]
    raise PromptError(
        "TASK_SELECTOR_NOT_FOUND",
        f"No expected task matches selector: {sel}",
        {
            "selector": sel,
            "actionable_anchors": [t.ssot_anchor for t in actionable],
            "known_anchors": [t.ssot_anchor for t in all_tasks],
        },
    )


def compute_implementation_ready(
    *,
    task_completed: bool,
    product_ready: bool | None,
    provider_sync_required: bool,
    sync_state: str | None,
    provider_ask_clean: bool | None,
    task_cache_current: bool,
    config_ok: bool | None = True,
    knowledge_enabled: bool = True,
    task_enabled: bool = True,
) -> bool:
    """True only when an actionable task may begin feature implementation.

    Completed tasks are never implementation-ready.
    Incomplete SSOT closeout / unsynced knowledge / unclean ask / stale task cache
    / invalid component config must not greenlight implementation.

    Knowledge/task provider gates apply only when the corresponding capability is
    enabled (Capability Profile default-disabled contract).
    """
    if task_completed:
        return False
    if config_ok is False:
        return False
    if provider_sync_required:
        return False
    if product_ready is False:
        return False
    if knowledge_enabled:
        if sync_state not in (None, "synced"):
            return False
        if provider_ask_clean is False:
            return False
    if task_enabled and not task_cache_current:
        return False
    return product_ready is True


def build_prompt_text(
    *,
    task: Any,
    readiness_summary: dict[str, Any],
    reconcile_counts: dict[str, Any],
    apply_plan_counts: dict[str, Any],
    provider_task_id_hash: str | None,
    knowledge_readiness: dict[str, Any] | None = None,
    provider_sync_required: bool = False,
    task_cache: dict[str, Any] | None = None,
    implementation_ready: bool | None = None,
) -> str:
    ready = readiness_summary.get("product_ready")
    blocked = readiness_summary.get("blocked_reasons") or []
    config_ok = readiness_summary.get("config_ok")
    if config_ok is None:
        config_ok = True
    components = dict(readiness_summary.get("components") or {})
    component_blocked = [
        r
        for r in blocked
        if r
        in {
            "required_component_disabled",
            "unsupported_component_enabled",
            "unknown_component_configured",
        }
    ]
    knowledge = dict(knowledge_readiness or {})
    knowledge.setdefault("sync_state", readiness_summary.get("sync_state"))
    knowledge.setdefault("provider_ask_clean", readiness_summary.get("provider_ask_clean"))
    cache = dict(task_cache or {})
    cache_current = bool(cache.get("task_cache_current", True))
    completed = (not bool(task.actionable)) or str(task.phase_state) == "completed"
    knowledge_enabled = bool((components.get("knowledge") or {}).get("enabled", True))
    task_enabled = bool((components.get("task") or {}).get("enabled", True))
    if implementation_ready is None:
        implementation_ready = compute_implementation_ready(
            task_completed=completed,
            product_ready=ready if isinstance(ready, bool) else None,
            provider_sync_required=provider_sync_required,
            sync_state=knowledge.get("sync_state"),
            provider_ask_clean=knowledge.get("provider_ask_clean"),
            task_cache_current=cache_current,
            config_ok=config_ok if isinstance(config_ok, bool) else True,
            knowledge_enabled=knowledge_enabled,
            task_enabled=task_enabled,
        )
    if completed:
        goal_lines = [
            "## Task goal",
            "WARNING: selected task is completed — do not restart.",
            f"Anchor: {task.ssot_anchor}",
            f"Title: {task.title}",
            "This envelope is for inspection/history only. Do not begin a new implementation of this phase.",
            "Follow docs/project/vibe-control-spec.md and companion knowledge/task / roadmap-state specs.",
            "Do not prefer chat memory over repo SSOT.",
        ]
    elif bool(getattr(task, "design_only", False)) and implementation_ready:
        goal_lines = [
            "## Task goal",
            f"Design / Evaluate: {task.title}",
            f"Anchor: {task.ssot_anchor}",
            "This is design_only work. Produce a design evaluation / design note only.",
            "Do not implement S2 lightweight ledger, operation recovery runtime, replay,",
            "workflow engine, or new provider/task mutation paths.",
            "Follow docs/project/vibe-control-spec.md and companion knowledge/task / roadmap-state specs.",
            "Do not prefer chat memory over repo SSOT.",
        ]
    elif implementation_ready:
        goal_lines = [
            "## Task goal",
            f"Implement: {task.title}",
            f"Anchor: {task.ssot_anchor}",
            "Follow docs/project/vibe-control-spec.md and companion knowledge/task / roadmap-state specs.",
            "Do not prefer chat memory over repo SSOT.",
        ]
    elif config_ok is False:
        goal_lines = [
            "## Task goal",
            "DO NOT start implementation — component config invalid (config_ok=false).",
            "Fix components.<component_id>.enabled; this is config failure, not provider unavailable.",
            f"Component blocked_reasons: {component_blocked or blocked}",
            f"Selected anchor (blocked until ready): {task.ssot_anchor}",
            f"Intended title after closeout: {task.title}",
            "Follow docs/project/vibe-control-spec.md and companion knowledge/task / roadmap-state specs.",
            "Do not prefer chat memory over repo SSOT.",
        ]
    else:
        goal_lines = [
            "## Task goal",
            "DO NOT start implementation — SSOT closeout / readiness incomplete.",
            "Commit alone is not closeout-complete. Do not claim done or begin feature work yet.",
            f"Selected anchor (blocked until ready): {task.ssot_anchor}",
            f"Intended title after closeout: {task.title}",
            "Required sequence: vibe closeout run --dry-run/--apply --json "
            "(bounded knowledge half), then task cache converge/reset if needed.",
            "Follow docs/project/vibe-control-spec.md and companion knowledge/task / roadmap-state specs.",
            "Do not prefer chat memory over repo SSOT.",
        ]
    lines = [
        "# Coding-agent implementation prompt (generated by vibe)",
        "",
        *goal_lines,
        "",
        "## Repo SSOT identity",
        f"- project_id: {task.project_id}",
        f"- ssot_id: {task.ssot_id}",
        f"- ssot_path: {task.ssot_path}",
        f"- ssot_snapshot_hash: {task.ssot_snapshot_hash}",
        f"- source_item_hash: {task.source_item_hash}",
        "",
        "## Selected task anchor",
        f"- title: {task.title}",
        f"- ssot_anchor: {task.ssot_anchor}",
        f"- task_kind: {task.task_kind}",
        f"- managed_key: {task.managed_key}",
        f"- phase_state: {task.phase_state}",
        f"- actionable: {task.actionable}",
        f"- design_only: {bool(getattr(task, 'design_only', False))}",
        f"- provider_task_id_hash: {provider_task_id_hash or 'null'} "
        "(binding lookup only — never source identity)",
        f"- implementation_ready: {implementation_ready}",
        "",
        "## product_ready summary",
        f"- product_ready: {ready}",
        f"- config_ok: {config_ok}",
        f"- blocked_reasons: {blocked}",
        f"- provider_sync_required: {provider_sync_required}",
        f"- task_cache_mode: {cache.get('task_cache_mode', 'local_embedded_ephemeral')}",
        f"- task_cache_current: {cache_current}",
        f"- task_cache_action_required: {cache.get('task_cache_action_required', not cache_current)}",
        f"- safe_task_convergence_allowed: {cache.get('safe_task_convergence_allowed')}",
        f"- task_cache_reset_required: {cache.get('task_cache_reset_required')}",
        "",
        "## Component runtime readiness",
        f"- config_ok: {config_ok}",
        f"- component_blocked_reasons: {component_blocked}",
        f"- components: {sorted(components.keys()) if components else []}",
    ]
    for cid in ("knowledge", "task", "sdd", "tdd"):
        meta = components.get(cid) or {}
        if meta:
            lines.append(
                f"- {cid}: enabled={meta.get('enabled')} "
                f"support_state={meta.get('support_state')} "
                f"readiness_role={meta.get('readiness_role')}"
            )
    lines.extend(
        [
            "- Component config failures are not provider unavailable.",
            "",
            "## Knowledge readiness summary",
            f"- sync_state: {knowledge.get('sync_state')}",
            f"- provider_ask_clean: {knowledge.get('provider_ask_clean')}",
            f"- knowledge_available: {knowledge.get('available')}",
            f"- knowledge_target_ok: {knowledge.get('target_ok')}",
            "- NotebookLM output is not truth; repo SSOT is truth.",
            "",
            "## Task reconcile / apply summary",
            f"- reconcile_counts: {reconcile_counts}",
            f"- apply_plan_counts: {apply_plan_counts}",
            "- provider_task_id / Beads task id is binding only; managed_key is identity.",
            "- Default Beads role is local_embedded_ephemeral task cache (not durable project truth).",
            "",
        ]
    )
    if not implementation_ready and not completed:
        lines.extend(
            [
                "## Required before implementation",
                "- Do not begin feature implementation while implementation_ready=false.",
                "- If config_ok=false: fix components.<component_id>.enabled "
                "(required_component_disabled / unsupported_component_enabled / "
                "unknown_component_configured). Do not treat as provider unavailable.",
                "- If provider_sync_required=true or knowledge is drift/pending/unavailable: "
                "finish bounded sync closeout "
                "(`vibe knowledge sync --dry-run/--apply` only when dry-run is inventory-bounded).",
                "- If task_cache_current=false: converge or reset the local ephemeral task cache first.",
                (
                    "- If safe_task_convergence_allowed=true: run vibe task apply dry-run, then "
                    "Option A managed apply for create/update only."
                ),
                (
                    "- If task_cache_reset_required=true: run "
                    "`vibe task cache reset --dry-run --json` then approved reset/regenerate "
                    "(prefer whole-cache reset; no ad hoc unmanaged adoption)."
                ),
                "- Stale Beads cache is not soft debt and is not closable as PASS.",
                "- Do not treat git commit alone as product closeout complete.",
                "",
            ]
        )
    if bool(getattr(task, "design_only", False)):
        lines.extend(
            [
                "## Design-only boundaries",
                "- design_only=true: deliver evaluation / design note only.",
                "- Do not implement S2 ledger, recovery runtime, replay, or workflow engine.",
                "- Do not invent Phase 13 or new product managers from this prompt.",
                "",
            ]
        )
    lines.extend(
        [
            "## Hard boundaries",
            "- Repo SSOT remains truth. Do not treat NotebookLM as truth or oracle.",
            "- Beads is local embedded ephemeral task cache by default; not GitHub/team truth.",
            "- Beads provider_task_id is binding result only; managed_key is stable identity.",
            "- Bounded NotebookLM sync --apply is a required SSOT closeout step when "
            "dry-run is limited to current active SSOT/default inventory; it is not optional chatter.",
            "- Do not run arbitrary retry --apply, unmanaged/orphan delete, broad cleanup, "
            "or auth/config/target changes.",
            "- Do not git push unless explicitly asked.",
            "- Do not run raw bd create/update/delete/close/claim; use vibe task CLI.",
            "- Do not delete Beads tasks individually as default UX; prefer cache reset/regenerate.",
            "- Do not auto-adopt unmanaged tasks.",
            "- Safe managed create/update may converge cache when knowledge is ready "
            "(full product_ready not required solely for that convergence).",
            "- Coding agents must not claim to update ChatGPT Project Sources "
            "(owner-manual external advisor copies; not a product closeout gate).",
            "",
            "## Mutation approvals required / not required",
            "- Not required for readonly status/reconcile/apply dry-run / implementation prompt.",
            "- Bounded current-SSOT closeout sync --apply is normal closeout when dry-run preconditions pass.",
            "- Required (owner / explicit): git push, destructive delete, unmanaged adoption,",
            "  non-deterministic conflict repair, broad cleanup, auth/config/target change,",
            "  NotebookLM mutation outside bounded closeout sync, arbitrary retry --apply.",
            "- Option A live Beads still needs --autonomous-managed + dual gate when mutating "
            "managed tasks.",
            "",
            "## Required tests / gates",
            "- Add/update focused pytest for the change.",
            "- Prefer scripts/test-closeout-local-fast.sh while iterating.",
            "- Before closeout claim: scripts/test-full-local-readonly.sh.",
            "- Default gates: local only; no real NotebookLM mutation; no Beads mutation unless "
            "Option A gates pass.",
            "",
            "## Expected final report fields",
            "- verdict",
            "- changed files / tests / exit codes",
            "- whether NotebookLM changed",
            "- whether Beads changed",
            "- whether git push happened",
            "- task_cache_current / product_ready / closeout_complete / implementation_ready",
            "- provider_sync_required if sync not completed in-task",
            "- ChatGPT Project Sources are not a product closeout gate "
            "(advisor-context only; owner manual)",
            "- final git status --short (local modification state)",
            "",
            "## Safety confirmation",
            "- No push unless explicitly asked.",
            "- No provider mutation unless explicitly approved or bounded closeout sync rules allow.",
            "- No raw provider refs / secrets in reports.",
            "",
            "## Final git status --short",
            "- After commit, `git status --short` must be empty before claiming local closeout.",
            "- Local commit alone does not complete provider sync or task-cache closeout.",
            "",
        ]
    )
    return "\n".join(lines)



def _degraded_signals(
    *,
    readiness: dict[str, Any],
    reconcile: dict[str, Any],
    apply_plan: dict[str, Any],
    provider_sync_required: bool,
    local_modifications_present: bool,
    task_cache: dict[str, Any] | None = None,
    knowledge_enabled: bool = True,
    task_enabled: bool = True,
) -> tuple[list[str], list[dict[str, Any]]]:
    warnings: list[str] = []
    actions: list[dict[str, Any]] = []
    cache = dict(task_cache or {})
    if readiness.get("config_ok") is False:
        warnings.append("config_ok=false")
    if readiness.get("product_ready") is False:
        warnings.append("product_ready=false")
        actions.append(
            next_action(
                code="CHECK_INTEGRATION_STATUS",
                command="vibe integration status --json",
                mutation=False,
                reason="Do not claim green PASS while product_ready is false",
            )
        )
    # Capability Profile: disabled knowledge/task raw probe noise is not a blocker.
    if task_enabled and cache.get("task_cache_current") is False:
        warnings.append("task_cache_not_current")
        for action in cache.get("next_actions") or []:
            if isinstance(action, dict):
                actions.append(action)
    if knowledge_enabled and readiness.get("sync_state") not in (None, "synced"):
        warnings.append(f"knowledge_unsynced:{readiness.get('sync_state')}")
    if knowledge_enabled and readiness.get("provider_ask_clean") is False:
        warnings.append("ask_hygiene_not_clean")
    if task_enabled and any(
        int(reconcile.get(k) or 0) > 0 for k in ("missing", "stale", "duplicate", "conflict")
    ):
        warnings.append("task_reconcile_mismatch")
    if task_enabled and int(apply_plan.get("blocked") or 0) > 0:
        warnings.append("task_apply_plan_blocked")
    if provider_sync_required:
        warnings.append("provider_sync_required")
        warnings.append("ssot_closeout_incomplete")
        actions.append(
            next_action(
                code="RUN_BOUNDED_KNOWLEDGE_SYNC",
                command="vibe closeout run --dry-run --json",
                mutation=False,
                reason=(
                    "SSOT/include_extra closeout incomplete: prefer `vibe closeout run` "
                    "for bounded NotebookLM sync orchestration. Blockers are provider "
                    "sync/ask hygiene and task-cache readiness — not ChatGPT Project Sources. "
                    "Do not claim done or start implementation yet."
                ),
            )
        )
    if local_modifications_present:
        warnings.append("local_modifications_present")
        from vibe_control.git_land_contract import GIT_LAND_DIRTY_REASON

        actions.append(
            next_action(
                code="COMMIT_OR_CLEAN_LOCAL_STATE",
                command="git status --short",
                mutation=False,
                reason=GIT_LAND_DIRTY_REASON,
            )
        )
    return warnings, actions


def build_implementation_prompt(
    *,
    repo_root: Path,
    task_selector: str,
    product_ready: bool | None = None,
    readiness_summary: dict[str, Any] | None = None,
    knowledge_readiness: dict[str, Any] | None = None,
    reconcile_counts: dict[str, Any] | None = None,
    apply_plan_counts: dict[str, Any] | None = None,
    provider_task_id: str | None = None,
    project_id: str = "vibe-control",
    redact_provider_ids: bool = True,
    notebook_ref_raw: str | None = None,  # accepted only to prove redaction; never emitted
    provider_sync_required: bool = False,
    local_modifications_present: bool = False,
    task_cache: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build readonly implementation prompt envelope. Never mutates providers."""
    from vibe_control.task.cache import evaluate_task_cache_state

    _ = notebook_ref_raw  # intentionally unused / never written into outputs
    from vibe_control.components import COMPONENT_BLOCK_REASONS, resolve_components_from_repo

    readiness = dict(readiness_summary or {})
    if product_ready is not None:
        readiness.setdefault("product_ready", product_ready)
    knowledge = dict(knowledge_readiness or {})
    knowledge.setdefault("sync_state", readiness.get("sync_state"))
    knowledge.setdefault("provider_ask_clean", readiness.get("provider_ask_clean"))
    knowledge.setdefault("available", readiness.get("knowledge_available"))
    knowledge.setdefault("target_ok", readiness.get("knowledge_target_ok"))
    reconcile = dict(
        reconcile_counts
        or {"matched": 0, "missing": 0, "stale": 0, "duplicate": 0, "conflict": 0, "unmanaged": 0}
    )
    apply_plan = dict(apply_plan_counts or {"create": 0, "update": 0, "skip": 0, "blocked": 0})

    # Always overlay repo component runtime (Slice 1 resolver) — SSOT for config_ok.
    component_runtime = resolve_components_from_repo(repo_root)
    readiness["config_ok"] = bool(component_runtime.get("config_ok"))
    readiness["components"] = dict(component_runtime.get("components") or {})
    blocked = list(readiness.get("blocked_reasons") or [])
    for reason in component_runtime.get("blocked_reasons") or []:
        if reason not in blocked:
            blocked.append(reason)
    readiness["blocked_reasons"] = blocked
    if readiness["config_ok"] is False:
        readiness["product_ready"] = False

    if task_cache is None:
        knowledge_ready = (
            knowledge.get("sync_state") == "synced" and knowledge.get("provider_ask_clean") is True
        )
        task_cache = evaluate_task_cache_state(
            reconcile_counts=reconcile,
            apply_plan_counts=apply_plan,
            knowledge_ready=bool(knowledge_ready),
            task_available=True,
            task_readable=True,
        )

    task = resolve_expected_task(
        repo_root=repo_root, project_id=project_id, task_selector=task_selector
    )
    # provider_task_id is lookup/binding context only — never identity.
    pid_hash = _id_hash(provider_task_id)
    completed = (not bool(task.actionable)) or str(task.phase_state) == "completed"
    comps = dict(readiness.get("components") or {})
    knowledge_enabled = bool((comps.get("knowledge") or {}).get("enabled", True))
    task_enabled = bool((comps.get("task") or {}).get("enabled", True))
    implementation_ready = compute_implementation_ready(
        task_completed=completed,
        product_ready=readiness.get("product_ready")
        if isinstance(readiness.get("product_ready"), bool)
        else None,
        provider_sync_required=provider_sync_required,
        sync_state=knowledge.get("sync_state"),
        provider_ask_clean=knowledge.get("provider_ask_clean"),
        task_cache_current=bool(task_cache.get("task_cache_current", True)),
        config_ok=bool(readiness.get("config_ok", True)),
        knowledge_enabled=knowledge_enabled,
        task_enabled=task_enabled,
    )
    prompt_text = build_prompt_text(
        task=task,
        readiness_summary=readiness,
        reconcile_counts=reconcile,
        apply_plan_counts=apply_plan,
        provider_task_id_hash=pid_hash,
        knowledge_readiness=knowledge,
        provider_sync_required=provider_sync_required,
        task_cache=task_cache,
        implementation_ready=implementation_ready,
    )

    task_identity: dict[str, Any] = {
        "project_id": task.project_id,
        "ssot_id": task.ssot_id,
        "ssot_path": task.ssot_path,
        "ssot_anchor": task.ssot_anchor,
        "task_kind": task.task_kind,
        "managed_key": task.managed_key,
    }
    task_context: dict[str, Any] = {
        "title": task.title,
        "phase_state": task.phase_state,
        "actionable": task.actionable,
        "design_only": bool(getattr(task, "design_only", False)),
        "ssot_snapshot_hash": task.ssot_snapshot_hash,
        "source_item_hash": task.source_item_hash,
        "provider_task_id_hash": pid_hash,
        # explicit: provider_task_id is not identity
        "provider_task_id_is_identity": False,
    }
    if not redact_provider_ids and provider_task_id:
        task_context["provider_task_id"] = provider_task_id

    # Compatibility alias used by older tests/callers
    task_payload = {**task_identity, **task_context}

    component_blocked_reasons = [
        r for r in readiness.get("blocked_reasons") or [] if r in COMPONENT_BLOCK_REASONS
    ]
    product_readiness = {
        "product_ready": readiness.get("product_ready"),
        "config_ok": readiness.get("config_ok"),
        "components": dict(readiness.get("components") or {}),
        "component_blocked_reasons": component_blocked_reasons,
        "blocked_reasons": list(readiness.get("blocked_reasons") or []),
        "provider_sync_required": provider_sync_required,
        "task_cache_current": task_cache.get("task_cache_current"),
        "task_cache_action_required": task_cache.get("task_cache_action_required"),
        "safe_task_convergence_allowed": task_cache.get("safe_task_convergence_allowed"),
        "task_cache_reset_required": task_cache.get("task_cache_reset_required"),
        "implementation_ready": implementation_ready,
        "closeout_blocking": (not implementation_ready) and (not completed),
    }
    knowledge_ready = {
        "sync_state": knowledge.get("sync_state"),
        "provider_ask_clean": knowledge.get("provider_ask_clean"),
        "available": knowledge.get("available"),
        "target_ok": knowledge.get("target_ok"),
    }
    warnings, next_actions = _degraded_signals(
        readiness=readiness,
        reconcile=reconcile,
        apply_plan=apply_plan,
        provider_sync_required=provider_sync_required,
        local_modifications_present=local_modifications_present,
        task_cache=task_cache,
        knowledge_enabled=knowledge_enabled,
        task_enabled=task_enabled,
    )
    if not implementation_ready and not completed:
        warnings.append("implementation_not_ready")
        next_actions.insert(
            0,
            next_action(
                code="SSOT_CLOSEOUT_INCOMPLETE",
                command="vibe integration status --json",
                mutation=False,
                reason=(
                    "Do not greenlight implementation while provider_sync_required, "
                    "knowledge drift/unclean ask, or task_cache_current=false"
                ),
            ),
        )
    selection = next_actionable_selection(repo_root=repo_root)
    if completed:
        warnings.append("task_completed_do_not_restart")
        next_actions.insert(
            0,
            next_action(
                code="TASK_COMPLETED_DO_NOT_RESTART",
                command="vibe implementation next --json",
                mutation=False,
                reason="Selected task is completed; do not restart; pick next actionable or report none",
            ),
        )

    return attach_operation_result(
        {
            "ok": True,
            "command": "vibe implementation prompt",
            "project_id": project_id,
            "mode": "readonly",
            "mutation": False,
            "data": {
                "task_identity": task_identity,
                "task_context": task_context,
                "design_only": bool(getattr(task, "design_only", False)),
                "task_completed": completed,
                "do_not_restart": completed,
                "implementation_ready": implementation_ready,
                "closeout_blocking": (not implementation_ready) and (not completed),
                "next_actionable_selection": selection,
                "no_actionable_next_task": bool(selection.get("no_actionable_next_task")),
                "product_readiness": product_readiness,
                "component_runtime": {
                    "config_ok": readiness.get("config_ok"),
                    "components": dict(readiness.get("components") or {}),
                    "blocked_reasons": component_blocked_reasons,
                },
                "knowledge_readiness": knowledge_ready,
                "task_cache": task_cache,
                "task_reconcile_summary": reconcile,
                "task_apply_plan_summary": apply_plan,
                "prompt": prompt_text,
                "prompt_sections": list(PROMPT_SECTION_ORDER),
                "prompt_hash": _sha256_text(prompt_text),
                # Compatibility aliases
                "task": task_payload,
                "readiness": readiness,
                "reconcile_counts": reconcile,
                "apply_plan_counts": apply_plan,
                "prompt_text": prompt_text,
                "sections": list(PROMPT_SECTION_ORDER),
            },
            "warnings": warnings,
            "next_actions": next_actions,
        },
        mutation_intent=False,
        effects=[],
    )
