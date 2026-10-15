"""Stable JSON envelope helpers for vibe CLI --json output."""

from __future__ import annotations

from typing import Any

WarningItem = str | dict[str, Any]
NextActionItem = str | dict[str, Any]

EFFECT_KINDS = frozenset(
    {
        "provider_write",
        "task_write",
        "local_state_write",
        "repo_write",
        "config_write",
    }
)


def _is_unsafe_effect_target(target: str) -> bool:
    """Reject targets that look like secrets, absolute home paths, or raw IDs."""
    text = target.strip()
    if not text:
        return True
    lowered = text.lower()
    if any(token in lowered for token in ("secret", "password", "token", "apikey", "api_key")):
        return True
    if text.startswith(("~/", "/Users/", "/home/", "C:\\Users\\", "C:/Users/")):
        return True
    if text.startswith("/") and not text.startswith(
        ("knowledge.", "task.", "hetu.", "grill.", "skill_assay.")
    ):
        # Absolute filesystem paths are not stable surface names.
        return True
    return False


def _normalize_effects(effects: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if effects is None:
        return []
    if not isinstance(effects, list):
        raise TypeError("effects must be a list or None")
    normalized: list[dict[str, Any]] = []
    for index, effect in enumerate(effects):
        if not isinstance(effect, dict):
            raise TypeError(f"effects[{index}] must be a dict")
        kind = effect.get("kind")
        target = effect.get("target")
        status = effect.get("status")
        if kind not in EFFECT_KINDS:
            raise ValueError(f"effects[{index}].kind must be one of {sorted(EFFECT_KINDS)}")
        if not isinstance(target, str):
            raise ValueError(f"effects[{index}].target must be a string")
        if status != "completed":
            raise ValueError(f"effects[{index}].status must be 'completed'")
        if _is_unsafe_effect_target(target):
            raise ValueError(f"effects[{index}].target is unsafe or not a stable surface name")
        # Copy only the minimal schema; ignore extra keys.
        normalized.append({"kind": kind, "target": target, "status": "completed"})
    return normalized


def attach_operation_result(
    envelope: dict[str, Any],
    *,
    mutation_intent: bool,
    effects: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Attach operation mutation evidence to a command envelope.

    Derives mutation_performed/mutation from completed effects. Does not decide
    approval or readiness.
    """
    if not isinstance(mutation_intent, bool):
        raise TypeError("mutation_intent must be a bool")
    if not isinstance(envelope, dict):
        raise TypeError("envelope must be a dict")

    normalized_effects = _normalize_effects(effects)
    mutation_performed = bool(normalized_effects)
    out = dict(envelope)
    out["mutation_intent"] = mutation_intent
    out["mutation_performed"] = mutation_performed
    out["mutation"] = mutation_performed
    out["effects"] = normalized_effects
    if out.get("ok") is False and mutation_performed:
        out["partial_success"] = True
    return out


def next_action(
    *,
    code: str,
    command: str,
    mutation: bool,
    reason: str,
) -> dict[str, Any]:
    """Canonical machine-readable next_action object for skill routing."""
    return {
        "code": code,
        "command": command,
        "mutation": bool(mutation),
        "reason": reason,
    }


def normalize_next_actions(items: list[NextActionItem] | None) -> list[NextActionItem]:
    if not items:
        return []
    return list(items)


def success_envelope(
    *,
    command: str,
    project_id: str | None,
    data: dict[str, Any] | list[Any] | None = None,
    warnings: list[WarningItem] | None = None,
    next_actions: list[NextActionItem] | None = None,
    mode: str = "local",
) -> dict[str, Any]:
    return {
        "ok": True,
        "command": command,
        "project_id": project_id,
        "mode": mode,
        "data": {} if data is None else data,
        "warnings": [] if warnings is None else list(warnings),
        "next_actions": normalize_next_actions(next_actions),
    }


def failure_envelope(
    *,
    command: str,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    project_id: str | None = None,
    warnings: list[WarningItem] | None = None,
    next_actions: list[NextActionItem] | None = None,
    partial_success: bool = False,
) -> dict[str, Any]:
    return {
        "ok": False,
        "partial_success": partial_success,
        "command": command,
        "project_id": project_id,
        "error": {
            "code": code,
            "message": message,
            "details": {} if details is None else details,
        },
        "warnings": [] if warnings is None else list(warnings),
        "next_actions": normalize_next_actions(next_actions),
    }


def not_implemented_envelope(
    *,
    command: str,
    project_id: str | None = None,
    message: str | None = None,
    next_actions: list[NextActionItem] | None = None,
) -> dict[str, Any]:
    return failure_envelope(
        command=command,
        code="NOT_IMPLEMENTED",
        message=message or f"{command} is not implemented in this scaffold pass",
        project_id=project_id,
        next_actions=next_actions
        or [
            next_action(
                code="NOT_IMPLEMENTED",
                command="vibe doctor --json",
                mutation=False,
                reason="Command is not implemented in this phase",
            )
        ],
    )
