"""Local integration status / doctor aggregation + product readiness."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from vibe_control.closeout import evaluate_ssot_closeout
from vibe_control.config import find_project_root, load_config, ConfigError, primary_control_path
from vibe_control.knowledge.corpus import build_desired_corpus, CorpusError
from vibe_control.knowledge.notebooklm_provider import NotebookLMProvider
from vibe_control.knowledge.repo_provider import RepoProvider
from vibe_control.product_readiness import (
    ProviderProbeResult,
    evaluate_product_readiness,
    readiness_next_actions,
)
from vibe_control.skills_manager import skills_readiness, skills_status
from vibe_control.task.beads_provider import BeadsProvider


def _attach_closeout_hint(probe: ProviderProbeResult, *, fallback_ready: bool) -> dict[str, Any]:
    """Surface SSOT closeout transaction fields without mutating providers.

    When sync is not synced / ask unclean, treat as sync-required after local SSOT change
    unless product_ready is already true (no_ssot_change_product_ready path).

    Disabled knowledge/task capabilities are treated as satisfied for closeout gates
    (Capability Profile: provider closeout applies only when enabled).

    Project Sources are not CLI-observable and are never a product closeout gate.
    """
    from vibe_control.components import capability_enabled

    knowledge_on = capability_enabled(probe.components, "knowledge")
    task_on = capability_enabled(probe.components, "task")

    if knowledge_on:
        kp_synced = probe.sync_state == "synced" and probe.provider_ask_clean
        ask_clean = probe.provider_ask_clean
        knowledge_available = probe.knowledge_available
        ssot_change_hint = probe.sync_state in {"drift", "pending"} or (
            probe.sync_state == "synced" and not probe.provider_ask_clean
        )
    else:
        kp_synced = True
        ask_clean = True
        knowledge_available = True
        ssot_change_hint = False

    task_available = probe.task_available if task_on else True
    task_readable = probe.task_readable if task_on else True

    changed = bool(ssot_change_hint and not probe.product_ready)
    return evaluate_ssot_closeout(
        ssot_or_include_extra_changed=changed,
        ssot_committed=True,
        sync_approved=False,
        sync_attempted=False,
        knowledge_synced=kp_synced,
        provider_ask_clean=ask_clean,
        knowledge_available=knowledge_available,
        knowledge_pending=bool(knowledge_on and probe.sync_state == "pending"),
        product_ready=probe.product_ready,
        task_available=task_available,
        task_readable=task_readable,
        repo_fallback_usable=fallback_ready,
    )

def build_integration_status(
    *,
    repo_root: Path | None = None,
    notebooklm: NotebookLMProvider | None = None,
    beads: BeadsProvider | None = None,
    probe_auth: bool = False,
    probe_product: bool = True,
    product_probe: ProviderProbeResult | None = None,
    knowledge_parts: dict[str, Any] | None = None,
    task_parts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = repo_root or find_project_root()
    nlm = (notebooklm or NotebookLMProvider()).status(probe_auth=probe_auth)
    bd = (beads or BeadsProvider()).status()
    if bd.installed:
        preview = (beads or BeadsProvider()).init_preview()
        bd.init_available = preview.init_available
        bd.init_safe_mode = preview.init_safe_mode
        bd.recommended_init = preview.recommended_init
        bd.help_flags = preview.help_flags
        bd.message = preview.message or bd.message

    skills = skills_status()
    skills_guide = skills_readiness()
    config_found = primary_control_path(root).is_file() or (
        (root / ".vibe" / "control.yaml").is_file()
    )
    fallback_ready = False
    project_id = None
    if config_found:
        try:
            config = load_config(root)
            project_id = config.project_id
            corpus = build_desired_corpus(config, repo_root=root)
            _ = corpus.source_count
            fallback_ready = True
        except (ConfigError, CorpusError):
            fallback_ready = RepoProvider().status(root).available and config_found

    nlm_data = nlm.to_dict()
    nlm_data["safe_to_sync"] = False

    if product_probe is not None:
        probe = product_probe
    elif probe_product:
        probe = evaluate_product_readiness(
            repo_root=root,
            knowledge=knowledge_parts,
            task=task_parts,
            probe=knowledge_parts is None or task_parts is None,
        )
    else:
        probe = evaluate_product_readiness(
            repo_root=root,
            knowledge=knowledge_parts
            or {
                "available": False,
                "target_ok": False,
                "sync_state": "unavailable",
                "warnings": ["product probe skipped"],
            },
            task=task_parts
            or {
                "available": bool(bd.installed),
                "mode": "path_only" if bd.installed else "unavailable",
                "readable": False,
                "ready_queue_available": None,
                "warnings": ["task deep probe skipped"],
            },
            probe=False,
        )

    from vibe_control.components import resolve_components_from_repo
    from vibe_control.product_readiness import finalize_product_ready

    component_runtime = resolve_components_from_repo(root)
    probe.config_ok = bool(component_runtime.get("config_ok"))
    probe.components = dict(component_runtime.get("components") or {})
    # Re-finalize so product_ready / blocked_reasons honor component gates.
    probe.blocked_reasons = list(component_runtime.get("blocked_reasons") or [])
    probe = finalize_product_ready(probe)

    readiness = probe.to_dict()
    closeout = _attach_closeout_hint(probe, fallback_ready=fallback_ready)
    cache = probe.task_cache or {}
    warnings = list(probe.warnings)
    warnings.extend(list(closeout.get("warnings") or []))
    warnings.extend(list(cache.get("warnings") or []))
    next_actions = list(closeout.get("next_actions") or [])
    for action in cache.get("next_actions") or []:
        if isinstance(action, dict):
            next_actions.append(action)

    return {
        "project_id": project_id,
        "notebooklm": nlm_data,
        "beads": bd.to_dict(),
        "skills": skills,
        "skills_readiness": {
            "installed": skills_guide.get("installed"),
            "condition": skills_guide.get("condition"),
            "missing": skills_guide.get("missing"),
            "mismatch": skills_guide.get("mismatch"),
        },
        "repo": {
            "project_root": root.as_posix(),
            "config_found": config_found,
            "fallback_ready": fallback_ready,
            "fallback_is_product_ready": False,
        },
        "product_ready": probe.product_ready,
        "blocked_reasons": list(probe.blocked_reasons),
        "config_ok": bool(getattr(probe, "config_ok", True)),
        "components": dict(getattr(probe, "components", None) or readiness.get("components") or {}),
        "capability_profile": readiness.get("capability_profile")
        or {
            "version": "vibe.capability_profile.v1",
            "default_disabled": True,
            "engine_readiness_separate": True,
        },
        "knowledge_provider": readiness["knowledge_provider"],
        "task_provider": readiness["task_provider"],
        "hetu_enabled": bool(getattr(probe, "hetu_enabled", False)),
        "hetu_available": bool(getattr(probe, "hetu_available", False)),
        "hetu_ready": (
            bool(getattr(probe, "hetu_ready", False))
            if bool(getattr(probe, "hetu_enabled", False))
            else None
        ),
        "hetu_index_state": getattr(probe, "hetu_index_state", None),
        "hetu_provider": getattr(probe, "hetu_provider", None),
        "hetu_index_commit": getattr(probe, "hetu_index_commit", None),
        "hetu_observed_head": getattr(probe, "hetu_observed_head", None),
        "hetu": readiness.get("hetu")
        or {
            "enabled": bool(getattr(probe, "hetu_enabled", False)),
            "available": bool(getattr(probe, "hetu_available", False)),
            "ready": (
                bool(getattr(probe, "hetu_ready", False))
                if bool(getattr(probe, "hetu_enabled", False))
                else None
            ),
            "index_state": getattr(probe, "hetu_index_state", None),
            "provider": getattr(probe, "hetu_provider", None),
            "index_commit": getattr(probe, "hetu_index_commit", None),
            "observed_head": getattr(probe, "hetu_observed_head", None),
        },
        "task_cache_mode": cache.get("task_cache_mode") or "local_embedded_ephemeral",
        "task_cache_current": bool(cache.get("task_cache_current", probe.task_cache_current)),
        "task_cache_action_required": bool(cache.get("task_cache_action_required", not probe.task_cache_current)),
        "safe_task_convergence_allowed": bool(cache.get("safe_task_convergence_allowed")),
        "task_cache_reset_required": bool(cache.get("task_cache_reset_required")),
        "task_cache": cache,
        "provider_probe": {
            "evidence_hash": probe.evidence_hash,
            "probed": probe.probed,
        },
        "closeout_state": closeout.get("closeout_state"),
        "closeout_complete": bool(closeout.get("closeout_complete")),
        "provider_sync_required": closeout.get("provider_sync_required"),
        "chatgpt_project_sources": closeout.get("chatgpt_project_sources")
        or {
            "product_closeout_gate": False,
            "owner_manual_external_copy": True,
            "advisor_files": [],
        },
        "warnings": warnings,
        "next_actions": next_actions,
    }


def build_integration_doctor(
    *,
    repo_root: Path | None = None,
    notebooklm: NotebookLMProvider | None = None,
    beads: BeadsProvider | None = None,
) -> dict[str, Any]:
    root = repo_root or find_project_root()
    warnings: list[str] = []
    next_actions: list[Any] = []

    status = build_integration_status(
        repo_root=root,
        notebooklm=notebooklm,
        beads=beads,
        probe_auth=True,
        probe_product=True,
    )

    package_root = Path(__file__).resolve().parent
    checkout_root = None
    for candidate in (package_root, *package_root.parents):
        if (candidate / "acceptance" / "phase2").is_dir():
            checkout_root = candidate
            break
    phase2_fixture = (
        (checkout_root / "acceptance/phase2/fixtures/migration-harness-mini/.vibe/control.yaml")
        if checkout_root
        else Path("missing")
    )

    nlm = status["notebooklm"]
    bd = status["beads"]
    skills = status["skills"]
    skills_guide = skills_readiness()

    if not nlm.get("installed"):
        warnings.append("NotebookLM CLI not installed")
        next_actions.append("Install NotebookLM CLI, then run knowledge login-guide")
    elif nlm.get("auth_state") in {"auth_failed", "command_failed"}:
        warnings.append(f"NotebookLM auth state: {nlm.get('auth_state')}")
        next_actions.append("Run notebooklm login, then knowledge auth-status --json")
    elif nlm.get("auth_state") == "command_unsupported":
        warnings.append("NotebookLM auth check unsupported")
        next_actions.append("Run `notebooklm --help` and inspect auth/session commands.")

    if not bd.get("installed"):
        warnings.append("Beads CLI (bd) not installed")
        next_actions.append("Run python -m vibe_control task install-guide --json")
    elif bd.get("init_safe_mode") == "unavailable":
        warnings.append("bd init lacks --skip-agents/--stealth; manual review required")
        next_actions.append("Review bd init --help before any init")

    warnings.extend(list(skills_guide.get("warnings") or []))
    for action in skills_guide.get("next_actions") or []:
        if action not in next_actions:
            next_actions.append(action)

    if not status["repo"].get("config_found"):
        warnings.append("No control.yaml at project root")
        next_actions.append("Copy template to .config/vibe-control.yaml for the target repo")

    if not status.get("product_ready"):
        warnings.append(
            "product_ready=false; repo fallback is degraded read, not full product readiness"
        )
        for action in readiness_next_actions(
            evaluate_product_readiness(
                repo_root=root,
                knowledge={
                    "available": (status.get("knowledge_provider") or {}).get("available"),
                    "target_ok": (status.get("knowledge_provider") or {}).get("target_ok"),
                    "sync_state": (status.get("knowledge_provider") or {}).get("sync_state")
                    or "unavailable",
                    "required_updates_count": (
                        ((status.get("knowledge_provider") or {}).get("ask_hygiene") or {}).get(
                            "required_updates_count"
                        )
                        or 0
                    ),
                    "candidate_count": (
                        ((status.get("knowledge_provider") or {}).get("ask_hygiene") or {}).get(
                            "candidate_count"
                        )
                        or 0
                    ),
                    "orphan_managed_count": (
                        ((status.get("knowledge_provider") or {}).get("ask_hygiene") or {}).get(
                            "orphan_managed_count"
                        )
                        or 0
                    ),
                },
                task={
                    "available": (status.get("task_provider") or {}).get("available"),
                    "mode": (status.get("task_provider") or {}).get("mode") or "unavailable",
                    "readable": (status.get("task_provider") or {}).get("readable"),
                    "ready_queue_available": (status.get("task_provider") or {}).get(
                        "ready_queue_available"
                    ),
                },
                probe=False,
            )
        ):
            next_actions.append(action.get("command") if isinstance(action, dict) else action)

    next_actions.append(
        "Real provider mutation requires explicit apply approval and product_ready providers"
    )
    warnings.extend(list(status.get("warnings") or []))

    return {
        "python_version": sys.version.split()[0],
        "project_root": root.as_posix(),
        "phase2_fixture_present": phase2_fixture.is_file(),
        "phase2_fixture_path": phase2_fixture.as_posix(),
        "integration": status,
        "product_ready": status.get("product_ready"),
        "blocked_reasons": list(status.get("blocked_reasons") or []),
        "notebooklm_auth": {
            "auth_checked": nlm.get("auth_checked"),
            "auth_state": nlm.get("auth_state"),
            "details": nlm.get("auth_details"),
        },
        "beads_init_safety": {
            "installed": bd.get("installed"),
            "init_safe_mode": bd.get("init_safe_mode"),
            "recommended_init": bd.get("recommended_init"),
            "help_flags": bd.get("help_flags"),
        },
        "skills": skills,
        "warnings": warnings,
        "next_actions": next_actions,
    }
