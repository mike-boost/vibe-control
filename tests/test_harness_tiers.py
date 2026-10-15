"""Harness tier scripts + parallel marker policy."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_closeout_fast_script_excludes_real_nlm_and_uses_xdist_via_fast():
    closeout = _read("scripts/test-closeout-local-fast.sh")
    fast = _read("scripts/test-fast.sh")
    assert "test-fast.sh" in closeout
    assert "real_notebooklm" in closeout
    assert "-n auto" in fast
    assert "not real_notebooklm" in fast
    assert "not serial" in fast
    assert "remote-inventory" not in closeout
    assert "knowledge query" not in closeout


def test_full_local_readonly_sets_local_acceptance_and_skips_real_nlm():
    text = _read("scripts/test-full-local-readonly.sh")
    assert "VIBE_ACCEPTANCE_LOCAL=1" in text
    assert "not real_notebooklm" in text
    assert "test-nlm-readonly-smoke" not in text
    assert "remote-inventory" not in text


def test_full_readonly_wrapper_is_local_only():
    text = _read("scripts/test-full-readonly.sh")
    assert "test-full-local-readonly.sh" in text
    assert "test-nlm-readonly-smoke" in text  # documented pointer
    assert "remote-inventory" not in text


def test_nlm_smoke_is_explicit_and_readonly():
    text = _read("scripts/test-nlm-readonly-smoke.sh")
    assert "knowledge status" in text
    assert "cleanup-candidates" in text
    assert "knowledge query" in text
    assert "--apply" not in text
    assert "retry --apply" not in text


def test_fast_marker_expression_excludes_serial_provider_shared():
    text = _read("scripts/test-fast.sh")
    assert (
        '-m "not serial and not real_notebooklm and not real_hetu and not acceptance '
        'and not slow and not mutation and not real_skill_host"'
    ) in text
    closeout = _read("scripts/test-closeout-local-fast.sh")
    assert "not real_hetu" in closeout
    full = _read("scripts/test-full-local-readonly.sh")
    assert "not real_hetu" in full


def test_hetu_smoke_scripts_exist_and_reindex_is_gated():
    readonly = _read("scripts/test-hetu-readonly-smoke.sh")
    reindex = _read("scripts/test-hetu-reindex-smoke.sh")
    assert "hetu doctor" in readonly
    assert "hetu status" in readonly
    assert "--apply" not in readonly
    assert "Refuse" in reindex or "owner-gated" in reindex
    assert "exit 2" in reindex


def test_ask_hygiene_clean_contract_still_encoded():
    from vibe_control.knowledge.ask_hygiene import evaluate_ask_hygiene

    clean = evaluate_ask_hygiene(
        sync_state="synced",
        required_updates_count=0,
        candidate_count=0,
        orphan_managed_count=0,
    )
    assert clean["provider_ask_clean"] is True
    polluted = evaluate_ask_hygiene(
        sync_state="synced",
        required_updates_count=0,
        candidate_count=1,
        orphan_managed_count=1,
    )
    assert polluted["provider_ask_clean"] is False
    assert polluted["condition"] == "orphan_pollution"
