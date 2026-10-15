"""Component Runtime — fixed catalog config resolver + readonly adoption detect.

Reads ONLY ``components.<component_id>.enabled``. No plugins, providers, or adoption.
Slice 4 adoption detection is advisory/diagnostic only (never mutates config/providers).
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from typing import Any

COMPONENT_CATALOG: dict[str, dict[str, Any]] = {
    "knowledge": {
        "support_state": "supported",
        "default_enabled": False,
        "readiness_role": "optional_when_disabled",
        # Existing runtime binding (not Slice-5 future work).
        "bound_provider": "notebooklm",
        "existing_runtime": True,
    },
    "task": {
        "support_state": "supported",
        "default_enabled": False,
        "readiness_role": "optional_when_disabled",
        "bound_provider": "beads",
        "existing_runtime": True,
    },
    "hetu": {
        "support_state": "supported",
        "default_enabled": False,
        "readiness_role": "optional_when_disabled",
        "bound_provider": "codebase_memory",
        "provider_hints": ["codebase_memory", "codegraph"],
        "existing_runtime": True,
    },
    "sdd": {
        "support_state": "not_supported_yet",
        "default_enabled": False,
        "readiness_role": "fail_closed_if_enabled",
        # Front/Core provider_hints — future adjacent tools only (not bound providers).
        "provider_hints": ["openspec", "spec_kit"],
        "bound_provider": None,
        "existing_runtime": False,
    },
    "tdd": {
        "support_state": "not_supported_yet",
        "default_enabled": False,
        "readiness_role": "fail_closed_if_enabled",
        "provider_hints": ["superpowers"],
        "bound_provider": None,
        "existing_runtime": False,
    },
}

# Config-invalid reasons only — never classified as provider unavailable.
COMPONENT_BLOCK_REASONS: frozenset[str] = frozenset(
    {
        "required_component_disabled",
        "unsupported_component_enabled",
        "unknown_component_configured",
    }
)

# Provider-scoped names are NOT component IDs (Front/Core boundary).
_INVALID_PROVIDER_SCOPED_COMPONENT_IDS: tuple[str, ...] = (
    "knowledge.notebooklm",
    "tasks.beads",
    "specs.sdd",
    "method.superpowers",
    "hetu.codebase_memory",
    "hetu.codegraph",
    "hetu.fake",
)


def build_component_provider_boundaries() -> dict[str, Any]:
    """Readonly provider-boundary preparation for future component/provider integration.

    Slice 5 prep only: never installs, adapts, adopts, or live-integrates providers.
    provider_hints remain hints — not active providers.
    """
    boundaries: list[dict[str, Any]] = []
    for component_id, meta in COMPONENT_CATALOG.items():
        hints = list(meta.get("provider_hints") or [])
        existing_runtime = bool(meta.get("existing_runtime"))
        bound = meta.get("bound_provider")
        # Future-hint components never expose an active provider in this prep slice.
        live_integration = False
        mutation_allowed = False
        requires_future = not existing_runtime
        boundaries.append(
            {
                "component_id": component_id,
                "support_state": str(meta.get("support_state")),
                "readiness_role": str(meta.get("readiness_role")),
                "provider_hints": hints,
                "provider_hints_are_active": False,
                "active_provider": None,
                "bound_provider": bound,
                "existing_runtime": existing_runtime,
                "live_integration": live_integration,
                "mutation_allowed": mutation_allowed,
                "requires_future_acceptance": requires_future,
                "fail_closed": True,
            }
        )

    return {
        "provider_boundaries": boundaries,
        "diagnostic_only": True,
        "mutation": False,
        "live_integration": False,
        "mutation_allowed": False,
        "requires_future_acceptance": True,
        "fail_closed": True,
        "readiness_effect": "none",
        "note": (
            "Boundary preparation only. Existing knowledge/task runtimes unchanged. "
            "sdd/tdd provider_hints are not active providers and are not live-integrated. "
            "Unsupported integration attempts fail closed; not provider unavailable."
        ),
    }


def evaluate_provider_integration_request(
    *,
    component_id: str,
    provider_id: str,
    intent: str = "live_integrate",
) -> dict[str, Any]:
    """Fail-closed evaluator for unsupported future provider integration attempts.

    Pure function / stub surface — does not mutate config, providers, or readiness.
    Never classifies failures as provider unavailable or empty inventory.
    """
    base = {
        "ok": False,
        "fail_closed": True,
        "live_integration": False,
        "mutation_allowed": False,
        "requires_future_acceptance": True,
        "not_provider_unavailable": True,
        "empty_inventory": False,
        "component_id": component_id,
        "provider_id": provider_id,
        "intent": intent,
        "diagnostic_only": True,
        "mutation": False,
    }

    if component_id in _INVALID_PROVIDER_SCOPED_COMPONENT_IDS:
        return {
            **base,
            "reason_code": "provider_scoped_name_not_component_id",
            "why": (
                f"{component_id!r} is a provider/method-scoped name, not a component ID. "
                "Use fixed catalog ids only (knowledge, task, hetu, sdd, tdd). "
                "Provider-scoped names such as hetu.codebase_memory are not component IDs."
            ),
        }

    if component_id not in COMPONENT_CATALOG:
        return {
            **base,
            "reason_code": "unsupported_provider_integration",
            "why": (
                f"Unknown component {component_id!r}. "
                "This is unsupported provider integration (fail closed), "
                "not provider unavailable."
            ),
        }

    meta = COMPONENT_CATALOG[component_id]
    hints = list(meta.get("provider_hints") or [])
    bound = meta.get("bound_provider")

    if intent == "treat_hint_as_active_provider":
        return {
            **base,
            "reason_code": "provider_hint_not_active_provider",
            "why": (
                f"provider_hints for {component_id!r} are advisory only; "
                f"{provider_id!r} is not an active provider."
            ),
        }

    if intent == "adopt_detected_candidate":
        return {
            **base,
            "reason_code": "detected_candidate_not_adopted",
            "why": (
                "Slice 4 detection is advisory only. "
                f"Detected candidate {provider_id!r} is not adopted and not provider-bound."
            ),
        }

    # Any live_integrate / default unsupported path for future-hint providers.
    if intent in ("live_integrate", "integrate", "bind", "install", "adapt"):
        # Existing runtime bindings are already product surfaces — Slice 5 does not
        # re-open them as live-integration mutation paths.
        if bool(meta.get("existing_runtime")) and provider_id == bound:
            return {
                **base,
                "reason_code": "unsupported_provider_integration",
                "requires_future_acceptance": False,
                "why": (
                    f"{component_id}/{provider_id} already has existing_runtime binding; "
                    "Slice 5 does not expose a live re-integration mutation path."
                ),
            }
        if provider_id in hints or provider_id != bound:
            return {
                **base,
                "reason_code": "unsupported_provider_integration",
                "why": (
                    f"Live integration of {component_id}/{provider_id} is not implemented. "
                    "Requires a future accepted task/spec. Fail closed; "
                    "not provider unavailable; not empty inventory."
                ),
            }

    return {
        **base,
        "reason_code": "unsupported_provider_integration",
        "why": (
            f"Unsupported provider integration request "
            f"({component_id}/{provider_id}, intent={intent!r}). Fail closed."
        ),
    }


def build_component_adoption_detection(
    *,
    which: Callable[[str], str | None] | None = None,
) -> dict[str, Any]:
    """Readonly adjacency detection for Front/Core ``provider_hints``.

    Advisory only: never adopts tools, never writes config, never flips readiness,
    and never binds a detected binary as a Vibe provider.
    """
    which_fn = which or shutil.which
    candidates: list[dict[str, Any]] = []
    for component_id, meta in COMPONENT_CATALOG.items():
        hints = list(meta.get("provider_hints") or [])
        for candidate_id in hints:
            detection_status = "not_detected"
            detail: dict[str, Any] = {}
            try:
                found = which_fn(str(candidate_id))
                if found:
                    detection_status = "detected"
                    detail = {"probe": str(candidate_id), "path_present": True}
                else:
                    detection_status = "not_detected"
                    detail = {"probe": str(candidate_id), "path_present": False}
            except Exception as exc:  # noqa: BLE001 — advisory probe must not raise
                detection_status = "unavailable"
                detail = {
                    "probe": str(candidate_id),
                    "error_class": type(exc).__name__,
                    # Unavailable is distinct from empty inventory / not_detected.
                    "unavailable_reason": "detection_probe_failed",
                }
            candidates.append(
                {
                    "candidate_id": str(candidate_id),
                    "component_id": component_id,
                    "component_support_state": str(meta.get("support_state")),
                    "detection_status": detection_status,
                    "adopted": False,
                    "provider_bound": False,
                    "advisory": True,
                    "detail": detail,
                }
            )

    adoption = {
        "candidates": candidates,
        "diagnostic_only": True,
        "mutation": False,
        "adoption_performed": False,
        "readiness_effect": "none",
        # Explicitly distinguish "probe unavailable" from "no candidates / empty inventory".
        "empty_inventory": False,
        "note": (
            "Readonly adjacency report for Front/Core provider_hints only. "
            "Detected != adopted != provider-bound. Does not install, adapt, "
            "uninstall, enable sdd/tdd, or change product_ready/config_ok."
        ),
    }
    return {
        "component_adoption": adoption,
        "diagnostic_only": True,
        "mutation": False,
        "adoption_performed": False,
        "readiness_effect": "none",
    }


def build_component_config_guidance() -> dict[str, Any]:
    """Readonly template / init-preview Capability Profile guidance.

    Never mutates config, providers, NotebookLM, Beads, or task cache.
    Enable examples and invalid examples are educational only (diagnostic_only=true).
    """
    import yaml

    from vibe_control.json_envelope import next_action

    components: dict[str, Any] = {}
    example: dict[str, Any] = {}
    for component_id, meta in COMPONENT_CATALOG.items():
        enabled = bool(meta["default_enabled"])
        support_state = str(meta["support_state"])
        available = support_state == "supported"
        not_implemented = support_state == "not_supported_yet"
        entry = {
            "support_state": support_state,
            "default_enabled": enabled,
            "enabled": enabled,
            "available": available,
            "enablable": available,
            "not_implemented": not_implemented,
            "readiness_role": str(meta["readiness_role"]),
        }
        hints = list(meta.get("provider_hints") or [])
        if hints:
            entry["provider_hints"] = hints
            entry["provider_hints_are_active"] = False
        components[component_id] = entry
        example[component_id] = {"enabled": enabled}

    example_yaml = yaml.safe_dump(
        {"components": example},
        sort_keys=False,
        default_flow_style=False,
    ).strip()

    enable_examples: list[dict[str, Any]] = [
        {
            "id": "enable_knowledge",
            "yaml_snippet": (
                "components:\n"
                "  knowledge:\n"
                "    enabled: true\n"
                "  task:\n"
                "    enabled: false\n"
                "  hetu:\n"
                "    enabled: false\n"
                "  sdd:\n"
                "    enabled: false\n"
                "  tdd:\n"
                "    enabled: false\n"
            ),
            "enables": ["knowledge"],
            "prerequisites": [
                "NotebookLM CLI installed and authenticated",
                "knowledge target / notebook alias configured",
                "bounded sync + ask hygiene clean after enable",
            ],
            "why": (
                "knowledge is available/enablable (default disabled). "
                "Enabling enters NotebookLM readiness/sync/ask-hygiene gates. "
                "This example is readonly preview only — it does not mutate config."
            ),
            "diagnostic_only": True,
            "mutation": False,
        },
        {
            "id": "enable_task",
            "yaml_snippet": (
                "components:\n"
                "  knowledge:\n"
                "    enabled: false\n"
                "  task:\n"
                "    enabled: true\n"
                "  hetu:\n"
                "    enabled: false\n"
                "  sdd:\n"
                "    enabled: false\n"
                "  tdd:\n"
                "    enabled: false\n"
            ),
            "enables": ["task"],
            "prerequisites": [
                "Beads (bd) installed",
                "local_embedded_ephemeral task-cache readiness",
                "task cache current after enable (converge via vibe task CLI)",
            ],
            "why": (
                "task is available/enablable (default disabled). "
                "Enabling enters Beads/provider/task-cache gates. "
                "This example is readonly preview only — it does not mutate config."
            ),
            "diagnostic_only": True,
            "mutation": False,
        },
        {
            "id": "enable_knowledge_and_task",
            "yaml_snippet": (
                "components:\n"
                "  knowledge:\n"
                "    enabled: true\n"
                "  task:\n"
                "    enabled: true\n"
                "  hetu:\n"
                "    enabled: false\n"
                "  sdd:\n"
                "    enabled: false\n"
                "  tdd:\n"
                "    enabled: false\n"
            ),
            "enables": ["knowledge", "task"],
            "prerequisites": [
                "NotebookLM ready + sync/ask hygiene clean",
                "Beads/task-cache ready and current",
                "hetu/sdd/tdd remain disabled unless intentionally enabled",
            ],
            "why": (
                "Combined enable of supported capabilities only. "
                "Disabled hetu/sdd/tdd stay out of product readiness. "
                "Readonly preview — does not write control.yaml or call providers."
            ),
            "diagnostic_only": True,
            "mutation": False,
        },
    ]

    invalid_examples: list[dict[str, Any]] = [
        {
            "yaml_snippet": "components:\n  sdd:\n    enabled: true\n",
            "block_reason": "unsupported_component_enabled",
            "why": (
                "sdd is not_implemented / not_supported_yet; leave enabled=false. "
                "This is a config failure, not provider unavailable."
            ),
            "diagnostic_only": True,
        },
        {
            "yaml_snippet": "components:\n  tdd:\n    enabled: true\n",
            "block_reason": "unsupported_component_enabled",
            "why": (
                "tdd is not_implemented / not_supported_yet; leave enabled=false. "
                "This is a config failure, not provider unavailable."
            ),
            "diagnostic_only": True,
        },
        {
            "yaml_snippet": "components:\n  openspec:\n    enabled: true\n",
            "block_reason": "unknown_component_configured",
            "why": (
                "unknown keys under components fail closed. "
                "This is a config failure, not provider unavailable."
            ),
            "diagnostic_only": True,
        },
    ]
    for bad_id in _INVALID_PROVIDER_SCOPED_COMPONENT_IDS:
        invalid_examples.append(
            {
                "yaml_snippet": f"components:\n  {bad_id}:\n    enabled: true\n",
                "block_reason": "unknown_component_configured",
                "why": (
                    f"{bad_id!r} is a provider/method-scoped name, not a component ID. "
                    "Use fixed catalog ids only (knowledge, task, hetu, sdd, tdd). "
                    "This is a config failure, not provider unavailable."
                ),
                "diagnostic_only": True,
            }
        )

    next_actions = [
        next_action(
            code="REVIEW_DEFAULT_DISABLED_PROFILE",
            command="vibe doctor --json",
            mutation=False,
            reason=(
                "Fresh/default Capability Profile has all capabilities disabled. "
                "Inspect component_config_example before enabling anything."
            ),
        ),
        next_action(
            code="ENABLE_KNOWLEDGE_CONFIG_PREVIEW",
            command="vibe knowledge init-preview --json",
            mutation=False,
            reason=(
                "To enable knowledge: set components.knowledge.enabled=true in control.yaml "
                "(manual edit), then satisfy NotebookLM prerequisites. Guidance does not "
                "auto-enable or mutate providers."
            ),
        ),
        next_action(
            code="ENABLE_TASK_CONFIG_PREVIEW",
            command="vibe task init-preview --json",
            mutation=False,
            reason=(
                "To enable task: set components.task.enabled=true in control.yaml "
                "(manual edit), then satisfy Beads/task-cache prerequisites. Guidance does "
                "not auto-enable or run bd init."
            ),
        ),
        next_action(
            code="ENABLE_HETU_CONFIG_PREVIEW",
            command="vibe hetu doctor --json",
            mutation=False,
            reason=(
                "To enable hetu: set components.hetu.enabled=true in control.yaml "
                "(manual edit), then satisfy codebase-memory readiness + IndexBindingReceipt. "
                "Guidance does not auto-enable or reindex."
            ),
        ),
    ]

    capability_guidance = {
        "version": "vibe.capability_guidance.v1",
        "engine_readiness_separate": True,
        "source_of_truth": "engine",
        "recomputes_readiness": False,
        "mutation": False,
        "default_disabled": True,
        "disabled_do_not_fail_product_ready": True,
        "enabled_failures_produce_next_actions": True,
        "not_ssot_manager": True,
        "not_roadmap_manager": True,
        "summary": (
            "Engine readiness (config/product gates) is separate from Capability Profile "
            "readiness. Fresh/default profile disables all capabilities; disabled "
            "knowledge/task/hetu do not fail product_ready. Enabling knowledge/task/hetu adds "
            "provider gates; sdd/tdd are not_implemented and fail closed if enabled."
        ),
        "knowledge": {
            "available": True,
            "enablable": True,
            "enabled_by_default": False,
            "provider_when_enabled": "notebooklm",
        },
        "task": {
            "available": True,
            "enablable": True,
            "enabled_by_default": False,
            "provider_when_enabled": "beads",
        },
        "hetu": {
            "available": True,
            "enablable": True,
            "enabled_by_default": False,
            "provider_when_enabled": "codebase_memory",
        },
        "sdd": {
            "available": False,
            "enablable": False,
            "not_implemented": True,
            "support_state": "not_supported_yet",
            "fail_closed_if_enabled": True,
        },
        "tdd": {
            "available": False,
            "enablable": False,
            "not_implemented": True,
            "support_state": "not_supported_yet",
            "fail_closed_if_enabled": True,
        },
    }

    return {
        "profile_preview": {
            "version": "vibe.capability_profile.v1",
            "default_disabled": True,
            "readonly": True,
            "mutation": False,
            "auto_enable": False,
        },
        "capability_guidance": capability_guidance,
        "components": components,
        "component_config_example": example,
        "component_config_example_yaml": example_yaml,
        "component_config_guidance": (
            "Configure only components.<component_id>.enabled for the fixed catalog "
            "(knowledge, task, hetu, sdd, tdd). Fresh/default profile: all disabled. "
            "knowledge/task/hetu are available/enablable; enabling adds provider readiness "
            "gates. sdd/tdd are not_implemented (enabled=true fails closed). "
            "This surface is readonly/preview/diagnostic — no install/adapt/uninstall "
            "and no silent auto-enable."
        ),
        "enable_examples": enable_examples,
        "invalid_examples": invalid_examples,
        "next_actions": next_actions,
        "diagnostic_only": True,
        "mutation": False,
        "auto_enable": False,
        "install_adapt_uninstall": False,
    }


def project_capability_guidance(
    *,
    components: dict[str, Any] | None = None,
    capability_profile: dict[str, Any] | None = None,
    concise: bool = False,
) -> dict[str, Any]:
    """Project Capability Profile guidance for Progress/Brief/Describe/Gateway.

    Projection-only: does not probe providers or recompute product_ready.
    When concise=True (Brief), omit long summary and next_actions.
    """
    guidance = build_component_config_guidance()
    base = dict(guidance["capability_guidance"])
    comps = dict(components or {})
    cap = dict(capability_profile or {})
    knowledge_enabled = bool(
        cap.get("knowledge_enabled")
        if "knowledge_enabled" in cap
        else (comps.get("knowledge") or {}).get("enabled", False)
    )
    task_enabled = bool(
        cap.get("task_enabled")
        if "task_enabled" in cap
        else (comps.get("task") or {}).get("enabled", False)
    )
    hetu_enabled = bool(
        cap.get("hetu_enabled")
        if "hetu_enabled" in cap
        else (comps.get("hetu") or {}).get("enabled", False)
    )
    out = dict(base)
    out["knowledge"] = {
        **dict(base.get("knowledge") or {}),
        "enabled": knowledge_enabled,
    }
    out["task"] = {
        **dict(base.get("task") or {}),
        "enabled": task_enabled,
    }
    out["hetu"] = {
        **dict(base.get("hetu") or {}),
        "enabled": hetu_enabled,
    }
    out["capability_profile"] = {
        "default_disabled": bool(cap.get("default_disabled", True)),
        "engine_readiness_separate": bool(cap.get("engine_readiness_separate", True)),
        "knowledge_enabled": knowledge_enabled,
        "task_enabled": task_enabled,
        "hetu_enabled": hetu_enabled,
    }
    if concise:
        out.pop("summary", None)
        out["next_actions"] = []
        out["concise"] = True
        return out
    enable_actions: list[dict[str, Any]] = []
    for action in guidance.get("next_actions") or []:
        code = str(action.get("code") or "")
        if code == "REVIEW_DEFAULT_DISABLED_PROFILE":
            enable_actions.append(action)
        elif code == "ENABLE_KNOWLEDGE_CONFIG_PREVIEW" and not knowledge_enabled:
            enable_actions.append(action)
        elif code == "ENABLE_TASK_CONFIG_PREVIEW" and not task_enabled:
            enable_actions.append(action)
        elif code == "ENABLE_HETU_CONFIG_PREVIEW" and not hetu_enabled:
            enable_actions.append(action)
    out["next_actions"] = enable_actions
    return out


def enrich_capability_readiness(
    components: dict[str, Any],
    *,
    knowledge_available: bool = False,
    knowledge_target_ok: bool = False,
    sync_state: str = "unavailable",
    provider_ask_clean: bool = False,
    task_available: bool = False,
    task_readable: bool = False,
    task_cache_current: bool = False,
    hetu_available: bool = False,
    hetu_ready: bool = False,
    hetu_index_state: str | None = None,
) -> dict[str, Any]:
    """Annotate resolved components with ready/skipped from Engine probe fields."""
    out: dict[str, Any] = {}
    for component_id, raw in (components or {}).items():
        entry = dict(raw or {})
        enabled = bool(entry.get("enabled"))
        support_state = str(entry.get("support_state") or "")
        available = support_state == "supported"
        not_implemented = support_state == "not_supported_yet"
        ready: bool | None
        if not enabled:
            ready = None
        elif component_id == "knowledge":
            ready = bool(
                knowledge_available
                and knowledge_target_ok
                and sync_state == "synced"
                and provider_ask_clean
            )
        elif component_id == "task":
            ready = bool(task_available and task_readable and task_cache_current)
        elif component_id == "hetu":
            ready = bool(hetu_ready) or (
                bool(hetu_available) and str(hetu_index_state or "") == "ready"
            )
        elif not_implemented:
            ready = False
        else:
            ready = False
        entry.update(
            {
                "available": available,
                "not_implemented": not_implemented,
                "ready": ready,
                "checked": enabled,
                "skipped": not enabled,
            }
        )
        out[component_id] = entry
    return out


def capability_enabled(components: dict[str, Any] | None, component_id: str) -> bool:
    entry = (components or {}).get(component_id) or {}
    return bool(entry.get("enabled"))


def resolve_component_runtime(
    components_config: dict[str, Any] | None,
) -> dict[str, Any]:
    """Resolve fixed catalog + optional ``components`` mapping into config_ok status.

    ``components_config`` is the raw ``components:`` mapping from control.yaml, or None
    when the section is absent. Top-level ``knowledge`` / ``tasks`` / ``specs`` sections
    are never lifecycle gates and must not be passed here.

    Fresh/default (no section): all capabilities disabled.
    """
    blocked: list[str] = []
    configured = components_config if isinstance(components_config, dict) else None
    components: dict[str, Any] = {}

    if configured is not None:
        for key in configured:
            if key not in COMPONENT_CATALOG:
                if "unknown_component_configured" not in blocked:
                    blocked.append("unknown_component_configured")

    for component_id, meta in COMPONENT_CATALOG.items():
        default_enabled = bool(meta["default_enabled"])
        support_state = str(meta["support_state"])
        readiness_role = str(meta["readiness_role"])
        explicit = False
        enabled = default_enabled

        if configured is not None and component_id in configured:
            entry = configured.get(component_id)
            if isinstance(entry, dict) and "enabled" in entry:
                enabled = bool(entry.get("enabled"))
                explicit = True
            else:
                # Malformed known entry — fail closed as unknown/invalid config surface.
                if "unknown_component_configured" not in blocked:
                    blocked.append("unknown_component_configured")
                enabled = default_enabled
                explicit = True

            # Legacy role "required" still fail-closed if ever used; target profile
            # uses optional_when_disabled so disabling knowledge/task is valid.
            if explicit and readiness_role == "required" and enabled is False:
                if "required_component_disabled" not in blocked:
                    blocked.append("required_component_disabled")
            if (
                explicit
                and support_state == "not_supported_yet"
                and enabled is True
            ):
                if "unsupported_component_enabled" not in blocked:
                    blocked.append("unsupported_component_enabled")

        available = support_state == "supported"
        not_implemented = support_state == "not_supported_yet"
        components[component_id] = {
            "support_state": support_state,
            "default_enabled": default_enabled,
            "enabled": enabled,
            "available": available,
            "not_implemented": not_implemented,
            "ready": None,
            "readiness_role": readiness_role,
            "explicit": explicit,
            "checked": bool(enabled),
            "skipped": not bool(enabled),
        }

    config_ok = len(blocked) == 0
    knowledge_enabled = bool((components.get("knowledge") or {}).get("enabled"))
    task_enabled = bool((components.get("task") or {}).get("enabled"))
    hetu_enabled = bool((components.get("hetu") or {}).get("enabled"))
    any_enabled = any(bool((components.get(cid) or {}).get("enabled")) for cid in components)
    return {
        "config_ok": config_ok,
        "blocked_reasons": blocked,
        "components": components,
        "capability_profile": {
            "version": "vibe.capability_profile.v1",
            "default_disabled": not any_enabled,
            "engine_readiness_separate": True,
            "knowledge_enabled": knowledge_enabled,
            "task_enabled": task_enabled,
            "hetu_enabled": hetu_enabled,
        },
    }


def resolve_components_from_repo(
    repo_root: Any,
    *,
    config_path: Any | None = None,
) -> dict[str, Any]:
    """Load control.yaml (if present) and resolve component runtime state.

    ``config_path`` respects CLI ``--config`` / ``VIBE_CONTROL_CONFIG`` overrides.
    """
    from pathlib import Path

    from vibe_control.config import ConfigError, load_config

    root = Path(repo_root)
    try:
        config = load_config(root, config_path=config_path)
    except ConfigError:
        return resolve_component_runtime(None)
    raw_components = config.raw.get("components")
    if raw_components is None:
        return resolve_component_runtime(None)
    if not isinstance(raw_components, dict):
        return {
            "config_ok": False,
            "blocked_reasons": ["unknown_component_configured"],
            "components": resolve_component_runtime(None)["components"],
        }
    return resolve_component_runtime(raw_components)
