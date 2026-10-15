"""Partial-continue failure classification (design lock; apply still fail-stop)."""

from __future__ import annotations

from typing import Any, Literal

FailureClass = Literal["fatal_run", "item_retryable", "item_skippable", "verify_aggregate"]

DEFAULT_SYNC_MODE = "fail_stop"
PARTIAL_CONTINUE_MODE = "partial_continue"
PARTIAL_CONTINUE_FLAG = "--continue-on-item-error"

# Codes observed / reserved for knowledge sync apply / retry.
FATAL_RUN_CODES = frozenset(
    {
        "TARGET_MISMATCH",
        "APPLY_SCOPE_VIOLATION",
        "SYNC_EXCEPTION",
        "AUTH_REQUIRED",
        "CONFIG_INVALID",
        "PROVIDER_UNAVAILABLE",
    }
)
ITEM_RETRYABLE_CODES = frozenset(
    {
        "WAIT_FAILED",
        "PROVIDER_TIMEOUT",
        "RATE_LIMITED",
    }
)
ITEM_SKIPPABLE_CODES = frozenset(
    {
        "ADD_FAILED",
        "REPLACE_FAILED",
        "MISSING_LOCAL_FILE",
        "UPLOAD_FAILED",
    }
)
VERIFY_AGGREGATE_CODES = frozenset(
    {
        "VERIFY_FAILED",
    }
)


def classify_item_failure(code: str | None, *, doc_id: str | None = None) -> FailureClass:
    """Classify a sync failure code for future partial-continue gating.

    Unknown codes with a doc_id default to item_skippable (continue-eligible when
    opt-in). Unknown codes without doc_id default to fatal_run.
    """
    c = str(code or "").strip().upper()
    if c in FATAL_RUN_CODES:
        return "fatal_run"
    if c in VERIFY_AGGREGATE_CODES:
        return "verify_aggregate"
    if c in ITEM_RETRYABLE_CODES:
        return "item_retryable"
    if c in ITEM_SKIPPABLE_CODES:
        return "item_skippable"
    if doc_id:
        return "item_skippable"
    return "fatal_run"


def should_stop_run(*, mode: str, failure_class: FailureClass) -> bool:
    """Return True when the run must stop given mode + class.

    Default product mode is fail_stop: any failure stops.
    partial_continue only continues for item_retryable / item_skippable.
    """
    mode = str(mode or DEFAULT_SYNC_MODE)
    if mode != PARTIAL_CONTINUE_MODE:
        return True
    return failure_class in {"fatal_run", "verify_aggregate"}


def build_item_failure(
    *,
    doc_id: str | None,
    op: str | None,
    code: str,
    message: str | None = None,
    elapsed_ms: int | None = None,
) -> dict[str, Any]:
    failure_class = classify_item_failure(code, doc_id=doc_id)
    return {
        "schema": "vibe.knowledge.item_failure.v1",
        "doc_id": doc_id,
        "op": op,
        "code": code,
        "class": failure_class,
        "message": message,
        "elapsed_ms": elapsed_ms,
        "mutation": False,
    }
