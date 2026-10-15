"""Pure Hetu index-state / strict-readiness evaluator (no CLI or provider I/O)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from vibe_control.hetu.models import IndexBindingReceipt, IndexState


@dataclass(frozen=True)
class HetuReadinessInputs:
    """Observed facts for evaluating index_state. Pure data; no side effects."""

    provider_available: bool
    provider_compatible: bool
    binding_conflict: bool
    provider_project: str | None
    provider_index_status: str | None
    node_count: int
    edge_count: int
    provider: str
    provider_version: str | None
    index_mode: str | None
    auto_watch_effective: bool | None
    observed_head: str
    git_dirty: bool
    receipt: IndexBindingReceipt | None = None
    receipt_corrupt: bool = False
    receipt_missing: bool = False


@dataclass(frozen=True)
class IndexStateEvaluation:
    index_state: IndexState
    reason: str | None = None
    message: str | None = None
    freshness_assurance: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "index_state": self.index_state,
            "reason": self.reason,
            "message": self.message,
            "freshness_assurance": self.freshness_assurance,
        }


def is_strict_ready(evaluation: IndexStateEvaluation) -> bool:
    return evaluation.index_state == "ready"


def evaluate_index_state(inputs: HetuReadinessInputs) -> IndexStateEvaluation:
    """Fail-closed strict readiness evaluator matching the Hetu runtime MVP spec."""

    if not inputs.provider_available or not inputs.provider_compatible:
        return IndexStateEvaluation(
            index_state="unavailable",
            reason="provider_unavailable" if not inputs.provider_available else "provider_incompatible",
            message="Hetu provider is unavailable or incompatible",
        )

    if inputs.binding_conflict:
        return IndexStateEvaluation(
            index_state="conflict_needs_choice",
            reason="binding_conflict",
            message="Multiple or mismatched provider project candidates require an explicit choice",
        )

    if not inputs.provider_project:
        return IndexStateEvaluation(
            index_state="missing",
            reason="provider_project_missing",
            message="No matching provider project/index for the current repo",
        )

    if inputs.provider_index_status == "indexing":
        return IndexStateEvaluation(
            index_state="indexing",
            reason="provider_indexing",
            message="Provider reports indexing in progress",
        )

    if inputs.receipt_corrupt:
        return IndexStateEvaluation(
            index_state="unverifiable",
            reason="receipt_corrupt",
            message="Index binding receipt is corrupted or invalid",
        )

    if inputs.receipt_missing or inputs.receipt is None:
        return IndexStateEvaluation(
            index_state="unverifiable",
            reason="receipt_missing",
            message="Provider index exists but no IndexBindingReceipt proves Git freshness",
        )

    receipt = inputs.receipt

    if inputs.auto_watch_effective is not False:
        return IndexStateEvaluation(
            index_state="unverifiable",
            reason="external_index_mutation_possible",
            message="Effective auto_watch is true or unknown; strict readiness requires false",
        )

    if receipt.auto_watch_effective is not False:
        return IndexStateEvaluation(
            index_state="unverifiable",
            reason="external_index_mutation_possible",
            message="Receipt records auto_watch_effective other than false",
        )

    if receipt.provider != inputs.provider:
        return IndexStateEvaluation(
            index_state="unverifiable",
            reason="provider_mismatch",
            message="Receipt provider does not match active Hetu provider",
        )

    if receipt.provider_version != inputs.provider_version:
        return IndexStateEvaluation(
            index_state="unverifiable",
            reason="provider_version_mismatch",
            message="Receipt provider version does not match observed provider version",
        )

    if receipt.provider_project != inputs.provider_project:
        return IndexStateEvaluation(
            index_state="unverifiable",
            reason="provider_project_mismatch",
            message="Receipt provider project does not match observed project binding",
        )

    if receipt.index_mode != inputs.index_mode:
        return IndexStateEvaluation(
            index_state="unverifiable",
            reason="index_mode_mismatch",
            message="Receipt index_mode does not match observed/configured mode",
        )

    if inputs.provider_index_status != "ready" or (inputs.node_count + inputs.edge_count) <= 0:
        return IndexStateEvaluation(
            index_state="unverifiable",
            reason="empty_graph" if (inputs.node_count + inputs.edge_count) <= 0 else "provider_not_ready",
            message="Provider index is not ready with a non-zero graph",
        )

    if receipt.index_commit != inputs.observed_head:
        return IndexStateEvaluation(
            index_state="stale",
            reason="head_mismatch",
            message="Receipt index_commit does not match observed Git HEAD",
        )

    if inputs.git_dirty or not receipt.git_status_short_empty:
        return IndexStateEvaluation(
            index_state="stale",
            reason="dirty_worktree",
            message="Working tree is dirty; strict freshness requires a clean Git status",
        )

    return IndexStateEvaluation(
        index_state="ready",
        reason=None,
        message=None,
        freshness_assurance="strict_receipt",
    )
