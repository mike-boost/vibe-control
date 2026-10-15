"""Lock partial-continue + batch-apply design contracts (no live mutation)."""

from __future__ import annotations

from pathlib import Path

from vibe_control.knowledge.partial_continue import (
    DEFAULT_SYNC_MODE,
    PARTIAL_CONTINUE_FLAG,
    PARTIAL_CONTINUE_MODE,
    build_item_failure,
    classify_item_failure,
    should_stop_run,
)

ROOT = Path(__file__).resolve().parents[1]


def test_default_mode_is_fail_stop():
    assert DEFAULT_SYNC_MODE == "fail_stop"
    assert PARTIAL_CONTINUE_MODE == "partial_continue"
    assert PARTIAL_CONTINUE_FLAG == "--continue-on-item-error"


def test_classify_fatal_and_item_classes():
    assert classify_item_failure("TARGET_MISMATCH") == "fatal_run"
    assert classify_item_failure("APPLY_SCOPE_VIOLATION") == "fatal_run"
    assert classify_item_failure("WAIT_FAILED", doc_id="a") == "item_retryable"
    assert classify_item_failure("ADD_FAILED", doc_id="a") == "item_skippable"
    assert classify_item_failure("VERIFY_FAILED") == "verify_aggregate"
    assert classify_item_failure("WEIRD", doc_id="x") == "item_skippable"
    assert classify_item_failure("WEIRD") == "fatal_run"


def test_should_stop_respects_modes():
    assert should_stop_run(mode="fail_stop", failure_class="item_skippable") is True
    assert should_stop_run(mode="partial_continue", failure_class="item_skippable") is False
    assert should_stop_run(mode="partial_continue", failure_class="item_retryable") is False
    assert should_stop_run(mode="partial_continue", failure_class="fatal_run") is True
    assert should_stop_run(mode="partial_continue", failure_class="verify_aggregate") is True


def test_item_failure_record_schema():
    row = build_item_failure(
        doc_id="doc_a",
        op="add",
        code="ADD_FAILED",
        message="add failed",
        elapsed_ms=12,
    )
    assert row["schema"] == "vibe.knowledge.item_failure.v1"
    assert row["class"] == "item_skippable"
    assert row["mutation"] is False


def test_partial_continue_contract_doc_locks_default():
    text = (ROOT / "docs/harness/knowledge-sync-partial-continue-contract.md").read_text(
        encoding="utf-8"
    )
    assert "Default mode = fail_stop" in text
    assert "--continue-on-item-error" in text
    assert "provider_ask_clean" in text
    assert "checkpoint" in text.lower() or "Checkpoint" in text


def test_batch_apply_design_is_design_only():
    text = (ROOT / "docs/harness/knowledge-sync-batch-apply-design.md").read_text(encoding="utf-8")
    assert "--batch-size" in text
    assert "--wait-mode" in text
    assert "serial" in text
    assert "Temporal" in text
    assert "implemented" in text.lower() or "Landed" in text or "default remains" in text
