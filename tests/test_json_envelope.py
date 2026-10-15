"""Tests for JSON envelope helpers."""

import pytest

from vibe_control.json_envelope import (
    attach_operation_result,
    failure_envelope,
    next_action,
    success_envelope,
)


def test_success_envelope_shape():
    envelope = success_envelope(
        command="vibe config validate",
        project_id="migration-harness",
        data={"valid": True},
    )
    assert envelope == {
        "ok": True,
        "command": "vibe config validate",
        "project_id": "migration-harness",
        "mode": "local",
        "data": {"valid": True},
        "warnings": [],
        "next_actions": [],
    }


def test_failure_envelope_shape():
    envelope = failure_envelope(
        command="vibe config validate",
        code="CONFIG_NOT_FOUND",
        message="missing",
        details={"expected_path": ".vibe/control.yaml"},
    )
    assert envelope["ok"] is False
    assert envelope["partial_success"] is False
    assert envelope["project_id"] is None
    assert envelope["error"]["code"] == "CONFIG_NOT_FOUND"
    assert envelope["error"]["message"] == "missing"
    assert envelope["error"]["details"]["expected_path"] == ".vibe/control.yaml"
    assert envelope["warnings"] == []
    assert envelope["next_actions"] == []


def test_next_action_helper():
    item = next_action(
        code="CONFIG_NOT_FOUND",
        command="vibe knowledge init-preview --json",
        mutation=False,
        reason="missing",
    )
    assert item["mutation"] is False
    assert item["code"] == "CONFIG_NOT_FOUND"
    assert item["command"] == "vibe knowledge init-preview --json"


def test_attach_operation_result_readonly_empty_effects():
    envelope = success_envelope(command="vibe doctor", project_id="p")
    out = attach_operation_result(envelope, mutation_intent=False, effects=[])
    assert out["mutation_intent"] is False
    assert out["mutation_performed"] is False
    assert out["mutation"] is False
    assert out["effects"] == []


def test_attach_operation_result_derives_performed_from_effect():
    envelope = success_envelope(command="vibe closeout run", project_id="p")
    effect = {
        "kind": "local_state_write",
        "target": "knowledge.last_sync_report",
        "status": "completed",
    }
    out = attach_operation_result(envelope, mutation_intent=True, effects=[effect])
    assert out["mutation_intent"] is True
    assert out["mutation_performed"] is True
    assert out["mutation"] is True
    assert out["effects"] == [effect]
    assert out["effects"] is not envelope.get("effects")


def test_attach_operation_result_failed_with_effects_sets_partial_success():
    envelope = failure_envelope(
        command="vibe knowledge sync",
        code="SYNC_APPLY_FAILED",
        message="wait failed",
        project_id="p",
    )
    effect = {
        "kind": "provider_write",
        "target": "knowledge.source_add",
        "status": "completed",
    }
    out = attach_operation_result(envelope, mutation_intent=True, effects=[effect])
    assert out["ok"] is False
    assert out["partial_success"] is True
    assert out["mutation_performed"] is True
    assert out["mutation"] is True
    assert out["effects"] == [effect]


def test_attach_operation_result_copies_effects_list():
    envelope = success_envelope(command="vibe task apply", project_id="p")
    effects = [
        {"kind": "task_write", "target": "task.create_managed", "status": "completed"}
    ]
    out = attach_operation_result(envelope, mutation_intent=True, effects=effects)
    effects.append(
        {"kind": "task_write", "target": "task.update_managed", "status": "completed"}
    )
    assert len(out["effects"]) == 1


def test_attach_operation_result_rejects_non_boolean_intent():
    envelope = success_envelope(command="vibe doctor", project_id="p")
    with pytest.raises(TypeError):
        attach_operation_result(envelope, mutation_intent="false", effects=[])  # type: ignore[arg-type]


def test_attach_operation_result_rejects_invalid_effect_schema():
    envelope = success_envelope(command="vibe doctor", project_id="p")
    with pytest.raises(ValueError):
        attach_operation_result(
            envelope,
            mutation_intent=True,
            effects=[{"kind": "provider_write", "target": "x"}],
        )


def test_attach_operation_result_rejects_unsafe_effect_target():
    envelope = success_envelope(command="vibe doctor", project_id="p")
    with pytest.raises(ValueError):
        attach_operation_result(
            envelope,
            mutation_intent=True,
            effects=[
                {
                    "kind": "local_state_write",
                    "target": "/home/example-user/.agents/state/secret",
                    "status": "completed",
                }
            ],
        )


def test_attach_operation_result_preserves_next_actions_and_data():
    actions = [
        next_action(
            code="REVIEW",
            command="vibe doctor --json",
            mutation=False,
            reason="noop",
        )
    ]
    envelope = success_envelope(
        command="vibe doctor",
        project_id="p",
        data={"product_ready": True},
        next_actions=actions,
    )
    out = attach_operation_result(envelope, mutation_intent=False, effects=[])
    assert out["data"]["product_ready"] is True
    assert out["next_actions"] == actions
    # Helper must not invent readiness fields
    assert "blocked_reasons" not in out
    assert "product_ready" not in out
