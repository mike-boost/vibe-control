"""Capability-specific fail-closed coverage (core control-contract hardening Task 5).

Mirrors predicates in product_readiness.finalize_product_ready / components —
does not invent a second readiness engine.
"""

from __future__ import annotations

from pathlib import Path

from vibe_control.components import resolve_component_runtime
from vibe_control.json_envelope import attach_operation_result, success_envelope
from vibe_control.product_readiness import build_probe_from_parts, readiness_next_actions
from vibe_control.progress_brief import build_progress
from vibe_control.task.cache import evaluate_task_cache_state


def _enabled_components(*, knowledge: bool = True, task: bool = True) -> dict:
    return resolve_component_runtime(
        {"knowledge": {"enabled": knowledge}, "task": {"enabled": task}}
    )["components"]


def _knowledge_ready_parts(**overrides):
    base = dict(
        knowledge_available=True,
        knowledge_target_ok=True,
        sync_state="synced",
        required_updates_count=0,
        candidate_count=0,
        orphan_managed_count=0,
        task_available=True,
        task_mode="readonly",
        task_readable=True,
        ready_queue_available=True,
        task_cache_current=True,
        components=_enabled_components(),
    )
    base.update(overrides)
    return base


def _assert_no_green_leak(probe, *, expect_ready: bool) -> None:
    assert probe.product_ready is expect_ready
    if not expect_ready:
        assert probe.blocked_reasons


def _assert_next_action_mutation_labels(actions: list) -> None:
    for action in actions:
        if isinstance(action, dict):
            assert "mutation" in action
            assert isinstance(action["mutation"], bool)


def _assert_current_command_readonly(probe) -> None:
    """Readiness projection / next-action assembly must not claim a write happened."""
    actions = readiness_next_actions(probe)
    _assert_next_action_mutation_labels(actions)
    status = {
        "project_id": "failclosed",
        "product_ready": probe.product_ready,
        "config_ok": probe.config_ok,
        "provider_sync_required": not probe.product_ready,
        "closeout_complete": probe.product_ready,
        "task_cache_current": probe.task_cache_current,
        "blocked_reasons": list(probe.blocked_reasons),
        "knowledge_provider": {
            "available": probe.knowledge_available,
            "target_ok": probe.knowledge_target_ok,
            "sync_state": probe.sync_state,
            "provider_ask_clean": probe.provider_ask_clean,
        },
        "task_provider": {
            "available": probe.task_available,
            "mode": probe.task_mode,
            "readable": probe.task_readable,
        },
        "components": dict(probe.components or {}),
        "capability_profile": {
            "knowledge_enabled": bool(
                ((probe.components or {}).get("knowledge") or {}).get("enabled")
            ),
            "task_enabled": bool(
                ((probe.components or {}).get("task") or {}).get("enabled")
            ),
        },
        "warnings": [],
        "next_actions": actions,
    }
    progress = build_progress(
        repo_root=Path("."),
        integration_status=status,
        next_selection={"no_actionable_next_task": True, "next_actionable_task": None},
        git_status_short="",
        observed_head="deadbeef",
    )
    assert progress.get("mutation_intent") is False
    assert progress.get("mutation_performed") is False
    assert progress.get("mutation") is False
    # Synthetic command boundary mirrors status readonly attach.
    cmd = attach_operation_result(
        success_envelope(
            command="vibe integration status",
            project_id="failclosed",
            mode="readonly",
            data={"product_ready": probe.product_ready},
            next_actions=actions,
        ),
        mutation_intent=False,
        effects=[],
    )
    assert cmd["mutation_intent"] is False
    assert cmd["mutation_performed"] is False
    assert cmd["mutation"] is False


# --- Knowledge ---


def test_knowledge_disabled_does_not_fail_product_ready():
    comps = _enabled_components(knowledge=False, task=False)
    probe = build_probe_from_parts(
        knowledge_available=False,
        knowledge_target_ok=False,
        sync_state="unavailable",
        task_available=False,
        task_mode="unavailable",
        task_readable=False,
        components=comps,
    )
    _assert_no_green_leak(probe, expect_ready=True)
    assert probe.blocked_reasons == []
    assert probe.components["knowledge"]["enabled"] is False
    actions = readiness_next_actions(probe)
    codes = [a.get("code") for a in actions if isinstance(a, dict)]
    assert "ENABLE_KNOWLEDGE_CAPABILITY" in codes
    _assert_current_command_readonly(probe)


def test_knowledge_unavailable_blocks():
    probe = build_probe_from_parts(
        **_knowledge_ready_parts(
            knowledge_available=False,
            knowledge_target_ok=False,
            sync_state="unavailable",
            components=_enabled_components(knowledge=True, task=False),
            task_available=True,
            task_readable=True,
        )
    )
    _assert_no_green_leak(probe, expect_ready=False)
    assert "knowledge_provider_unavailable" in probe.blocked_reasons
    actions = readiness_next_actions(probe)
    assert any(
        isinstance(a, dict) and a.get("code") == "KNOWLEDGE_PROVIDER_DIAGNOSIS"
        for a in actions
    )
    _assert_current_command_readonly(probe)


def test_knowledge_target_mismatch_blocks():
    probe = build_probe_from_parts(
        **_knowledge_ready_parts(
            knowledge_available=True,
            knowledge_target_ok=False,
            sync_state="target_mismatch",
            components=_enabled_components(knowledge=True, task=False),
        )
    )
    _assert_no_green_leak(probe, expect_ready=False)
    assert "knowledge_target_not_ok" in probe.blocked_reasons
    assert "knowledge_sync_state=target_mismatch" in probe.blocked_reasons
    _assert_current_command_readonly(probe)


def test_knowledge_drift_pending_receipt_missing_block():
    for sync_state in ("drift", "pending", "receipt_missing"):
        probe = build_probe_from_parts(
            **_knowledge_ready_parts(
                sync_state=sync_state,
                required_updates_count=1 if sync_state == "drift" else 0,
                components=_enabled_components(knowledge=True, task=False),
            )
        )
        _assert_no_green_leak(probe, expect_ready=False)
        assert f"knowledge_sync_state={sync_state}" in probe.blocked_reasons
        actions = readiness_next_actions(probe)
        assert any(
            isinstance(a, dict) and a.get("code") == "KNOWLEDGE_SYNC_DRY_RUN"
            for a in actions
        )
        _assert_current_command_readonly(probe)


def test_knowledge_ask_unclean_blocks():
    probe = build_probe_from_parts(
        **_knowledge_ready_parts(
            sync_state="synced",
            required_updates_count=2,
            components=_enabled_components(knowledge=True, task=False),
        )
    )
    _assert_no_green_leak(probe, expect_ready=False)
    assert probe.provider_ask_clean is False
    assert any(r.startswith("ask_hygiene=") for r in probe.blocked_reasons)
    actions = readiness_next_actions(probe)
    assert any(
        isinstance(a, dict) and a.get("code") == "ASK_HYGIENE" for a in actions
    )
    _assert_current_command_readonly(probe)


def test_knowledge_clean_ready():
    probe = build_probe_from_parts(
        **_knowledge_ready_parts(
            components=_enabled_components(knowledge=True, task=False),
        )
    )
    _assert_no_green_leak(probe, expect_ready=True)
    assert probe.blocked_reasons == []
    assert probe.provider_ask_clean is True
    _assert_current_command_readonly(probe)


# --- Task ---


def test_task_disabled_does_not_fail_product_ready():
    comps = _enabled_components(knowledge=False, task=False)
    probe = build_probe_from_parts(
        knowledge_available=True,
        knowledge_target_ok=True,
        sync_state="synced",
        task_available=False,
        task_mode="unavailable",
        task_readable=False,
        task_cache_current=False,
        components=comps,
    )
    _assert_no_green_leak(probe, expect_ready=True)
    assert "task_provider_unavailable" not in probe.blocked_reasons
    assert "task_cache_not_current" not in probe.blocked_reasons
    actions = readiness_next_actions(probe)
    codes = [a.get("code") for a in actions if isinstance(a, dict)]
    assert "ENABLE_TASK_CAPABILITY" in codes
    _assert_current_command_readonly(probe)


def test_task_unavailable_unreadable_blocks():
    probe = build_probe_from_parts(
        **_knowledge_ready_parts(
            knowledge_available=True,
            sync_state="synced",
            task_available=False,
            task_mode="unavailable",
            task_readable=False,
            components=_enabled_components(knowledge=False, task=True),
        )
    )
    _assert_no_green_leak(probe, expect_ready=False)
    assert "task_provider_unavailable" in probe.blocked_reasons
    actions = readiness_next_actions(probe)
    assert any(
        isinstance(a, dict) and a.get("code") == "TASK_PROVIDER_DIAGNOSIS"
        for a in actions
    )
    _assert_current_command_readonly(probe)

    unreadable = build_probe_from_parts(
        **_knowledge_ready_parts(
            task_available=True,
            task_mode="readonly",
            task_readable=False,
            components=_enabled_components(knowledge=False, task=True),
        )
    )
    _assert_no_green_leak(unreadable, expect_ready=False)
    assert "task_provider_not_readable" in unreadable.blocked_reasons
    _assert_current_command_readonly(unreadable)


def test_task_cache_stale_blocks():
    cache = evaluate_task_cache_state(
        reconcile_counts={
            "matched": 0,
            "missing": 0,
            "stale": 3,
            "duplicate": 0,
            "conflict": 0,
            "unmanaged": 0,
        },
        apply_plan_counts={"create": 0, "update": 3, "skip": 0, "blocked": 0},
        knowledge_ready=True,
        task_available=True,
        task_readable=True,
    )
    assert cache["task_cache_current"] is False
    probe = build_probe_from_parts(
        **_knowledge_ready_parts(
            task_cache_current=False,
            task_cache=cache,
            components=_enabled_components(knowledge=False, task=True),
        )
    )
    _assert_no_green_leak(probe, expect_ready=False)
    assert "task_cache_not_current" in probe.blocked_reasons
    actions = readiness_next_actions(probe)
    _assert_next_action_mutation_labels(actions)
    # Suggested converge apply may be mutation=true; current command remains false.
    assert any(
        isinstance(a, dict) and a.get("mutation") is True for a in actions
    ) or any(
        isinstance(a, dict) and a.get("code") == "TASK_CACHE_CONVERGE_APPLY"
        for a in (cache.get("next_actions") or [])
    )
    _assert_current_command_readonly(probe)


def test_task_duplicate_conflict_unmanaged_reset_path():
    for key in ("duplicate", "conflict", "unmanaged"):
        counts = {
            "matched": 0,
            "missing": 0,
            "stale": 0,
            "duplicate": 0,
            "conflict": 0,
            "unmanaged": 0,
        }
        counts[key] = 2
        cache = evaluate_task_cache_state(
            reconcile_counts=counts,
            apply_plan_counts={"create": 0, "update": 0, "skip": 0, "blocked": 0},
            knowledge_ready=True,
            task_available=True,
            task_readable=True,
        )
        assert cache["task_cache_reset_required"] is True
        assert cache["task_cache_current"] is False
        codes = [a["code"] for a in cache["next_actions"] if isinstance(a, dict)]
        assert "TASK_CACHE_RESET_DRY_RUN" in codes
        for action in cache["next_actions"]:
            if isinstance(action, dict) and action.get("code") == "TASK_CACHE_RESET_DRY_RUN":
                assert action["mutation"] is False
        probe = build_probe_from_parts(
            **_knowledge_ready_parts(
                task_cache_current=False,
                task_cache=cache,
                components=_enabled_components(knowledge=False, task=True),
            )
        )
        _assert_no_green_leak(probe, expect_ready=False)
        assert "task_cache_not_current" in probe.blocked_reasons
        _assert_current_command_readonly(probe)


def test_task_clean_ready():
    cache = evaluate_task_cache_state(
        reconcile_counts={
            "matched": 4,
            "missing": 0,
            "stale": 0,
            "duplicate": 0,
            "conflict": 0,
            "unmanaged": 0,
        },
        apply_plan_counts={"create": 0, "update": 0, "skip": 2, "blocked": 0},
        knowledge_ready=True,
        task_available=True,
        task_readable=True,
    )
    assert cache["task_cache_current"] is True
    probe = build_probe_from_parts(
        **_knowledge_ready_parts(
            task_cache_current=True,
            task_cache=cache,
            components=_enabled_components(knowledge=False, task=True),
        )
    )
    _assert_no_green_leak(probe, expect_ready=True)
    assert probe.blocked_reasons == []
    _assert_current_command_readonly(probe)
