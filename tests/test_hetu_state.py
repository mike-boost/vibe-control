"""Pure Hetu index-state / strict-readiness evaluator matrix."""

from __future__ import annotations

from vibe_control.hetu.models import (
    INDEX_STATES,
    IndexBindingReceipt,
    IndexState,
    ProviderStatusResult,
)
from vibe_control.hetu.receipt import compute_binding_hash
from vibe_control.hetu.state import (
    HetuReadinessInputs,
    evaluate_index_state,
    is_strict_ready,
)


SCHEMA = "vibe.hetu.index_binding.v1"


def _receipt(**overrides: object) -> IndexBindingReceipt:
    base = {
        "schema": SCHEMA,
        "repo_identity": "demo-project",
        "repo_realpath_hash": "sha256:" + ("a" * 64),
        "provider": "codebase_memory",
        "provider_project": "demo",
        "provider_version": "0.9.0",
        "index_mode": "fast",
        "persistence": False,
        "index_commit": "abc123",
        "git_status_short_empty": True,
        "auto_watch_effective": False,
        "node_count": 10,
        "edge_count": 20,
        "bound_at": "2026-07-22T00:00:00+00:00",
    }
    base.update(overrides)
    receipt = IndexBindingReceipt(**base)  # type: ignore[arg-type]
    return receipt.with_binding_hash(compute_binding_hash(receipt))


def _inputs(**overrides: object) -> HetuReadinessInputs:
    receipt = _receipt()
    base: dict[str, object] = {
        "provider_available": True,
        "provider_compatible": True,
        "binding_conflict": False,
        "provider_project": "demo",
        "provider_index_status": "ready",
        "node_count": 10,
        "edge_count": 20,
        "provider": "codebase_memory",
        "provider_version": "0.9.0",
        "index_mode": "fast",
        "auto_watch_effective": False,
        "observed_head": "abc123",
        "git_dirty": False,
        "receipt": receipt,
        "receipt_corrupt": False,
        "receipt_missing": False,
    }
    base.update(overrides)
    return HetuReadinessInputs(**base)  # type: ignore[arg-type]


def test_index_states_match_spec():
    assert INDEX_STATES == (
        "missing",
        "indexing",
        "ready",
        "stale",
        "unverifiable",
        "unavailable",
        "conflict_needs_choice",
    )
    for state in INDEX_STATES:
        assert state in IndexState.__args__  # type: ignore[attr-defined]


def test_provider_status_result_model():
    status = ProviderStatusResult(
        provider="codebase_memory",
        provider_version="0.9.0",
        provider_project="demo",
        index_state="ready",
        index_commit="abc123",
        node_count=10,
        edge_count=20,
        auto_watch_effective=False,
        freshness_assurance="strict_receipt",
    )
    payload = status.to_dict()
    assert payload["provider"] == "codebase_memory"
    assert payload["index_state"] == "ready"
    assert "repo_realpath" not in payload
    assert "~/" not in str(payload)
    assert "/Users/" not in str(payload)


def test_evaluate_missing_when_no_provider_project():
    result = evaluate_index_state(_inputs(provider_project=None, receipt=None, receipt_missing=True))
    assert result.index_state == "missing"
    assert not is_strict_ready(result)


def test_evaluate_indexing():
    result = evaluate_index_state(_inputs(provider_index_status="indexing", receipt=None, receipt_missing=True))
    assert result.index_state == "indexing"
    assert not is_strict_ready(result)


def test_evaluate_unavailable_when_provider_down():
    result = evaluate_index_state(_inputs(provider_available=False))
    assert result.index_state == "unavailable"
    assert not is_strict_ready(result)


def test_evaluate_unavailable_when_incompatible():
    result = evaluate_index_state(_inputs(provider_compatible=False))
    assert result.index_state == "unavailable"
    assert not is_strict_ready(result)


def test_evaluate_conflict():
    result = evaluate_index_state(_inputs(binding_conflict=True))
    assert result.index_state == "conflict_needs_choice"
    assert not is_strict_ready(result)


def test_evaluate_missing_receipt_unverifiable():
    result = evaluate_index_state(_inputs(receipt=None, receipt_missing=True))
    assert result.index_state == "unverifiable"
    assert result.reason == "receipt_missing"
    assert not is_strict_ready(result)


def test_evaluate_corrupt_receipt_unverifiable_without_parser_leak():
    result = evaluate_index_state(_inputs(receipt=None, receipt_corrupt=True, receipt_missing=False))
    assert result.index_state == "unverifiable"
    assert result.reason == "receipt_corrupt"
    assert "JSONDecodeError" not in (result.message or "")
    assert "Expecting value" not in (result.message or "")
    assert not is_strict_ready(result)


def test_evaluate_head_mismatch_stale():
    result = evaluate_index_state(_inputs(observed_head="other"))
    assert result.index_state == "stale"
    assert result.reason == "head_mismatch"
    assert not is_strict_ready(result)


def test_evaluate_dirty_tree_stale():
    result = evaluate_index_state(_inputs(git_dirty=True))
    assert result.index_state == "stale"
    assert result.reason == "dirty_worktree"
    assert not is_strict_ready(result)


def test_evaluate_provider_version_mismatch_unverifiable():
    result = evaluate_index_state(_inputs(provider_version="0.8.1"))
    assert result.index_state == "unverifiable"
    assert result.reason == "provider_version_mismatch"
    assert not is_strict_ready(result)


def test_evaluate_provider_project_mismatch_unverifiable():
    result = evaluate_index_state(_inputs(provider_project="other"))
    assert result.index_state == "unverifiable"
    assert result.reason == "provider_project_mismatch"
    assert not is_strict_ready(result)


def test_evaluate_index_mode_mismatch_unverifiable():
    result = evaluate_index_state(_inputs(index_mode="full"))
    assert result.index_state == "unverifiable"
    assert result.reason == "index_mode_mismatch"
    assert not is_strict_ready(result)


def test_evaluate_watcher_true_unverifiable():
    result = evaluate_index_state(_inputs(auto_watch_effective=True))
    assert result.index_state == "unverifiable"
    assert result.reason == "external_index_mutation_possible"
    assert not is_strict_ready(result)


def test_evaluate_watcher_unknown_unverifiable():
    result = evaluate_index_state(_inputs(auto_watch_effective=None))
    assert result.index_state == "unverifiable"
    assert result.reason == "external_index_mutation_possible"
    assert not is_strict_ready(result)


def test_evaluate_zero_graph_not_ready():
    result = evaluate_index_state(_inputs(node_count=0, edge_count=0))
    assert result.index_state == "unverifiable"
    assert result.reason == "empty_graph"
    assert not is_strict_ready(result)


def test_evaluate_valid_strict_ready():
    result = evaluate_index_state(_inputs())
    assert result.index_state == "ready"
    assert result.reason is None
    assert is_strict_ready(result)
    assert result.freshness_assurance == "strict_receipt"


def test_conflict_beats_missing_receipt():
    result = evaluate_index_state(
        _inputs(binding_conflict=True, receipt=None, receipt_missing=True)
    )
    assert result.index_state == "conflict_needs_choice"


def test_unavailable_beats_conflict():
    result = evaluate_index_state(_inputs(provider_available=False, binding_conflict=True))
    assert result.index_state == "unavailable"
