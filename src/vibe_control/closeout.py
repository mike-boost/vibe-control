"""SSOT closeout transaction evaluator (local/readonly design contract)."""

from __future__ import annotations

from typing import Any

from vibe_control.json_envelope import next_action

CLOSEOUT_STATES = (
    "no_ssot_change_product_ready",
    "ssot_change_committed_sync_required",
    "ssot_change_committed_sync_pending",
    "ssot_change_committed_synced_product_ready",
    "repo_only_degraded",
)

# Advisor-only: ChatGPT Project Sources are owner-managed external copies for
# advisor context freshness. Not a product closeout gate / CLI-observable state.
PROJECT_SOURCES_ADVISOR_FILES = (
    "docs/project/vibe-control-spec.md",
    "docs/project/vibe-control-knowledge-spec.md",
    "docs/project/vibe-control-task-spec.md",
    "docs/project/vibe-control-roadmap-state.md",
)

# Backward-compatible alias (advisory list only; never a closeout gate).
PROJECT_SOURCES_HANDOFF = PROJECT_SOURCES_ADVISOR_FILES


def evaluate_ssot_closeout(
    *,
    ssot_or_include_extra_changed: bool,
    ssot_committed: bool = True,
    sync_approved: bool = False,
    sync_attempted: bool = False,
    knowledge_synced: bool = False,
    provider_ask_clean: bool = False,
    knowledge_available: bool = False,
    knowledge_pending: bool = False,
    product_ready: bool = False,
    task_available: bool = False,
    task_readable: bool = False,
    repo_fallback_usable: bool = True,
) -> dict[str, Any]:
    """Evaluate Front/Core SSOT closeout transaction state.

    Pure local contract helper. Does not mutate providers.

    Commit alone is never closeout-complete. Active SSOT/include_extra changes require:
    bounded NotebookLM sync → product_ready probe → Beads/task-cache convergence when needed.

    ChatGPT Project Sources are owner-manual external advisor copies only; they are not
    a product closeout gate and are not CLI-observable.
    """
    warnings: list[str] = []
    next_actions: list[dict[str, Any]] = []
    provider_sync_required = False
    full_pass_allowed = False

    if not ssot_or_include_extra_changed:
        if product_ready and knowledge_synced and provider_ask_clean and task_available and task_readable:
            state = "no_ssot_change_product_ready"
            full_pass_allowed = True
        elif repo_fallback_usable and not product_ready:
            state = "repo_only_degraded"
            warnings.append("repo_fallback_usable_but_not_product_ready")
        else:
            state = "repo_only_degraded"
            warnings.append("providers_not_product_ready")
    else:
        providers_green = (
            knowledge_synced
            and provider_ask_clean
            and product_ready
            and task_available
            and task_readable
        )
        if not ssot_committed:
            state = "ssot_change_committed_sync_required"
            provider_sync_required = True
            warnings.append("ssot_change_not_from_fixed_committed_state")
        elif providers_green:
            state = "ssot_change_committed_synced_product_ready"
            full_pass_allowed = True
        elif sync_approved and (sync_attempted or knowledge_pending or not knowledge_available):
            state = "ssot_change_committed_sync_pending"
            provider_sync_required = True
            warnings.append("provider_sync_pending_or_unavailable")
        else:
            state = "ssot_change_committed_sync_required"
            provider_sync_required = True
            warnings.append("ssot_changed_provider_sync_required")

        if provider_sync_required:
            if not sync_approved:
                next_actions.append(
                    next_action(
                        code="RUN_BOUNDED_KNOWLEDGE_SYNC",
                        command="vibe closeout run --dry-run --json",
                        mutation=False,
                        reason=(
                            "Required SSOT closeout step: prefer `vibe closeout run` "
                            "(dry-run then --apply when inventory-bounded); "
                            "do not hand-assemble sync/status/task sequence"
                        ),
                    )
                )
                next_actions.append(
                    next_action(
                        code="RERUN_INTEGRATION_STATUS",
                        command="vibe integration status --json",
                        mutation=False,
                        reason="Verify product_ready after bounded closeout sync; do not claim done early",
                    )
                )
            else:
                next_actions.append(
                    next_action(
                        code="RETRY_OR_WAIT_PROVIDER_SYNC",
                        command="vibe knowledge status --json",
                        mutation=False,
                        reason=(
                            "Bounded sync attempted but provider incomplete/unavailable; "
                            "do not claim product_ready or implementation-ready"
                        ),
                    )
                )

    if full_pass_allowed and product_ready is False:
        full_pass_allowed = False
        warnings.append("full_pass_blocked_product_ready_false")

    closeout_complete = bool(full_pass_allowed)

    return {
        "closeout_state": state,
        "provider_sync_required": provider_sync_required,
        "full_pass_allowed": full_pass_allowed,
        "product_ready_claim_allowed": full_pass_allowed,
        "closeout_complete": closeout_complete,
        "chatgpt_project_sources": {
            "product_closeout_gate": False,
            "owner_manual_external_copy": True,
            "advisor_files": list(PROJECT_SOURCES_ADVISOR_FILES),
        },
        "mutation": False,
        "warnings": warnings,
        "next_actions": next_actions,
        "rules": {
            "repo_ssot_is_truth": True,
            "notebooklm_is_derived": True,
            "forward_only_sync": True,
            "no_provider_to_repo_recovery": True,
            "remote_ack_is_watermark_only": True,
            "status_query_doctor_readonly": True,
            "bounded_sync_apply_allowed_on_closeout": True,
            "bounded_sync_is_required_closeout_step": True,
            "commit_alone_is_not_closeout_complete": True,
            "non_bounded_sync_needs_explicit_approval": True,
            "repo_fallback_not_product_ready": True,
            "chatgpt_project_sources_owner_manual": True,
            "chatgpt_project_sources_not_product_closeout_gate": True,
        },
    }
