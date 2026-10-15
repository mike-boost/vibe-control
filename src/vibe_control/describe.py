"""Vibe Describe — readonly control-surface explanation over Engine outputs.

Describe explains authority map, command surfaces, mutation classes, component
catalog, and non-goals. It MUST NOT probe providers or recompute readiness.
Current-state fields are projected from Engine Progress only when provided or
when Progress is used as an accepted projection source.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from vibe_control.components import COMPONENT_CATALOG
from vibe_control.evidence import build_evidence_v1
from vibe_control.json_envelope import attach_operation_result, next_action, success_envelope
from vibe_control.progress_brief import (
    build_progress,
    read_git_status_short,
    read_observed_head,
)
from vibe_control.git_land_contract import git_land_contract_dict
from vibe_control.self_grill_contract import self_grill_contract_dict
from vibe_control.skill_assay.contract import skill_assay_contract_dict
from vibe_control.owner_plain_language_contract import owner_plain_language_contract_dict

DESCRIBE_VERSION = "vibe.describe.v1"

# Static catalogs — derived from repo code/contracts, not live provider probes.
READONLY_SURFACES: list[dict[str, Any]] = [
    {
        "name": "progress",
        "command": "vibe progress --json",
        "owns": "current control-state projection + safe next",
        "mutation": False,
    },
    {
        "name": "brief",
        "command": "vibe brief --json",
        "owns": "short action-oriented coding-agent brief",
        "mutation": False,
    },
    {
        "name": "describe",
        "command": "vibe describe --json",
        "owns": "authority map / surfaces / mutation classes / component catalog",
        "mutation": False,
    },
    {
        "name": "gateway",
        "command": "vibe gateway --intent <intent> --json",
        "owns": "thin intent routing to Engine surfaces",
        "mutation": False,
        "note": "Ordinary routes are readonly; grill_brief is local_runtime_write; skill_assay_brief is readonly entry",
    },
    {
        "name": "grill.status",
        "command": "vibe grill status --json",
        "owns": "readonly local self-grill session receipt",
        "mutation": False,
    },
    {
        "name": "skill_assay.doctor",
        "command": "vibe skill-assay doctor --host <host> --json",
        "owns": "Skill Assay host adapter readiness (not product_ready)",
        "mutation": False,
    },
    {
        "name": "skill_assay.brief",
        "command": "vibe skill-assay brief [--skill <dir>] [--host <host>] --json",
        "owns": "Skill Assay agent entry contract + next_actions",
        "mutation": False,
    },
    {
        "name": "skill_assay.report",
        "command": "vibe skill-assay report --assay <id> --json",
        "owns": "Skill Assay evidence/report re-read (local receipt)",
        "mutation": False,
    },
    {
        "name": "implementation.next",
        "command": "vibe implementation next --json",
        "owns": "next actionable roadmap-state selection",
        "mutation": False,
    },
    {
        "name": "implementation.prompt",
        "command": "vibe implementation prompt --task <selector> --json",
        "owns": "readonly coding-agent implementation prompt (blocked while grill IN_PROGRESS)",
        "mutation": False,
    },
    {
        "name": "integration.status",
        "command": "vibe integration status --json",
        "owns": "product_ready / provider / task-cache readiness envelope",
        "mutation": False,
    },
    {
        "name": "doctor",
        "command": "vibe doctor --json",
        "owns": "local environment / config readiness checks",
        "mutation": False,
    },
    {
        "name": "closeout.dry_run",
        "command": "vibe closeout run --dry-run --json",
        "owns": "readonly SSOT closeout orchestration",
        "mutation": False,
    },
    {
        "name": "hetu.status",
        "command": "vibe hetu status --json",
        "owns": "Hetu index freshness / binding / readiness (readonly)",
        "mutation": False,
    },
    {
        "name": "hetu.doctor",
        "command": "vibe hetu doctor --json",
        "owns": "Hetu provider compatibility + watcher guidance (readonly)",
        "mutation": False,
    },
    {
        "name": "hetu.search",
        "command": "vibe hetu search --query <str> --json",
        "owns": "bounded structural search when Hetu ready",
        "mutation": False,
    },
    {
        "name": "hetu.trace",
        "command": "vibe hetu trace --symbol <qn> --direction inbound|outbound|both --json",
        "owns": "bounded call/data-flow trace when Hetu ready",
        "mutation": False,
    },
    {
        "name": "hetu.impact",
        "command": "vibe hetu impact --json",
        "owns": "bounded blast-radius impact (ready or dirty-only degraded)",
        "mutation": False,
    },
    {
        "name": "hetu.architecture",
        "command": "vibe hetu architecture --json",
        "owns": "bounded architecture clusters when Hetu ready",
        "mutation": False,
    },
    {
        "name": "hetu.reindex.dry_run",
        "command": "vibe hetu reindex --dry-run --json",
        "owns": "Hetu reindex plan + plan-binding hash (no mutation)",
        "mutation": False,
    },
]

MUTATION_SURFACES: list[dict[str, Any]] = [
    {
        "name": "gateway.grill_brief",
        "command": "vibe gateway --intent grill_brief --json",
        "mutation_class": "local_runtime_write",
        "requires_explicit_approval": False,
        "gateway_auto_run": False,
        "auto_run_from_describe": False,
        "note": (
            "mutation_intent=true; mutation_performed only when a new session/active "
            "pointer is written (reuse without write is performed=false)"
        ),
    },
    {
        "name": "grill.checkpoint",
        "command": "vibe grill checkpoint --json",
        "mutation_class": "local_runtime_write",
        "requires_explicit_approval": False,
        "gateway_auto_run": False,
        "auto_run_from_describe": False,
    },
    {
        "name": "grill.close",
        "command": "vibe grill close --status EXHAUSTED|BLOCKED_ON_LIVE --json",
        "mutation_class": "local_runtime_write",
        "requires_explicit_approval": False,
        "gateway_auto_run": False,
        "auto_run_from_describe": False,
    },
    {
        "name": "diagnostics.bundle",
        "command": "vibe diagnostics bundle --redacted --json",
        "mutation_class": "local_runtime_write",
        "requires_explicit_approval": False,
        "gateway_auto_run": False,
        "auto_run_from_describe": False,
    },
    {
        "name": "skill_assay.diagnose",
        "command": "vibe skill-assay diagnose --skill <dir> --host <host> --prompt-file <file> --execute --json",
        "mutation_class": "local_runtime_write",
        "requires_explicit_approval": False,
        "gateway_auto_run": False,
        "auto_run_from_describe": False,
        "note": "Independent of vibe skills install; local assay receipts only",
    },
    {
        "name": "skill_assay.finalize",
        "command": "vibe skill-assay finalize --assay <id> --analysis-file <json> --json",
        "mutation_class": "local_runtime_write",
        "requires_explicit_approval": False,
        "gateway_auto_run": False,
        "auto_run_from_describe": False,
    },
    {
        "name": "closeout.apply",
        "command": "vibe closeout run --apply --json",
        "mutation_class": "bounded_knowledge_closeout",
        "requires_explicit_approval": True,
        "gateway_auto_run": False,
        "auto_run_from_describe": False,
    },
    {
        "name": "task.apply",
        "command": "vibe task apply --apply --json --provider beads",
        "mutation_class": "task_provider_mutation",
        "requires_explicit_approval": True,
        "gateway_auto_run": False,
        "auto_run_from_describe": False,
    },
    {
        "name": "task.cache_reset",
        "command": "vibe task cache reset --apply --json --provider beads",
        "mutation_class": "local_ephemeral_task_cache_reset",
        "requires_explicit_approval": True,
        "gateway_auto_run": False,
        "auto_run_from_describe": False,
    },
    {
        "name": "knowledge.sync_apply",
        "command": "vibe knowledge sync --apply --json",
        "mutation_class": "knowledge_provider_mutation",
        "requires_explicit_approval": True,
        "gateway_auto_run": False,
        "auto_run_from_describe": False,
        "note": "Prefer bounded vibe closeout run --apply over raw knowledge sync apply",
    },
    {
        "name": "hetu.reindex.apply",
        "command": (
            "vibe hetu reindex --apply --expect-plan-binding <sha256> "
            "--confirm-hetu-reindex-apply --json"
        ),
        "mutation_class": "hetu_provider_mutation",
        "requires_explicit_approval": True,
        "gateway_auto_run": False,
        "auto_run_from_describe": False,
        "note": "Closeout never auto-reindexes; requires plan binding + confirm flag",
    },
]

# Bounded migration: these command envelopes expose mutation_intent / mutation_performed /
# compatibility mutation / effects via attach_operation_result. Other commands keep
# legacy behavior until a future accepted slice.
OPERATION_EVIDENCE_NORMALIZED_COMMANDS: list[str] = [
    "vibe closeout run",
    "vibe knowledge sync",
    "vibe knowledge retry",
    "vibe task apply",
    "vibe task cache reset",
    "vibe task reconcile",
    "vibe diagnostics bundle",
    "vibe skill-assay doctor / diagnose / finalize / report",
    "vibe gateway (incl. grill_brief)",
    "vibe brief / progress",
    "vibe describe",
    "vibe doctor",
    "vibe integration status",
    "vibe knowledge status / query",
    "vibe implementation prompt",
    "vibe hetu status / doctor / search / trace / impact / architecture / reindex",
]

OPERATION_EVIDENCE_CONTRACT: dict[str, Any] = {
    "helper": "vibe_control.json_envelope.attach_operation_result",
    "mutation_intent": "bool — true when the invoke path is an apply/write path (even if blocked)",
    "mutation_performed": "bool — derived from completed effects[]; callers cannot contradict",
    "mutation": "compat alias of mutation_performed (top-level)",
    "effects": {
        "schema": {
            "kind": "provider_write|task_write|local_state_write|repo_write|config_write",
            "target": "redacted stable surface name (no secrets/home paths)",
            "status": "completed",
        },
        "meaning": "completed side effects only, not planned ops",
    },
    "partial_success": "ok=false with non-empty effects requires partial_success=true",
    "approval": "capability-specific; no universal MutationGate",
    "normalized_commands": OPERATION_EVIDENCE_NORMALIZED_COMMANDS,
    "non_claim": "Describe does not claim every legacy CLI command is normalized",
}

ENGINE_SURFACES: list[dict[str, Any]] = [
    *READONLY_SURFACES,
    *[
        {
            "name": m["name"],
            "command": m["command"],
            "owns": m["mutation_class"],
            "mutation": True,
        }
        for m in MUTATION_SURFACES
    ],
]

DESCRIBE_NON_GOALS: list[str] = [
    "product health or readiness computation",
    "provider mutation",
    "provider registry or plugin framework",
    "second readiness engine",
    "workflow engine",
    "S2/S3 persistent ledger",
    "sub-agent routing",
    "Phase 13 invention",
    "cross-notebook knowledge ask / answer merge",
    "automatic notebook routing from question text",
    "installable self-grill skill / skill sprawl for communication modes",
]

KNOWLEDGE_PROVIDER_SELECTION_GUIDANCE: list[str] = [
    "Set knowledge.provider explicitly in .config (local_fts or notebooklm).",
    "Vibe never auto-switches providers; doctor only probes the active one.",
    "local_fts: zero-cost SQLite FTS5 retrieval with path+line ranges; agent reasons.",
    "notebooklm: optional derived synthesis ask when account/CLI available.",
    "fallback_provider=repo is degraded only and never product_ready alone.",
    "Switching providers does not migrate state; the new active starts at drift until sync.",
    "product_ready knowledge half is satisfied by the active provider when synced+ask-clean.",
]

KNOWLEDGE_MULTI_NOTEBOOK_GUIDANCE: list[str] = [
    "One notebook may be enough for small curated corpora.",
    "When source count approaches plan caps, or ask mixes unrelated domains, "
    "configure additional allow_list notebooks with per-notebook SSOT selectors "
    "(path_prefixes / include_extra / exclude_globs / corpus_mode).",
    "With exactly one allow_list entry, --notebook may be omitted; "
    "with two or more, --notebook is required for sync/query/status/inventory/doctor.",
    "Vibe does not choose categories; the agent decides aliases and selector values.",
    "Cross-notebook ask is not supported.",
    "product_ready / bounded closeout track default_alias only.",
    "Non-default sync --apply requires --confirm-non-default-sync.",
    "Hard-bug / RCA distrust / first-principles: "
    "`vibe gateway --intent grill_brief --json` opens/resumes a local grill session "
    "(runtime/vibe-grill); Progress pulls CONTINUE while IN_PROGRESS; "
    "`vibe implementation prompt` fail-closed until `vibe grill close`; "
    "not a separate skill to switch to.",
]


def _component_catalog_static() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for component_id, meta in COMPONENT_CATALOG.items():
        out[component_id] = {
            "support_state": meta.get("support_state"),
            "readiness_role": meta.get("readiness_role"),
            "default_enabled": meta.get("default_enabled"),
            "bound_provider": meta.get("bound_provider"),
            "existing_runtime": bool(meta.get("existing_runtime")),
            "provider_hints": list(meta.get("provider_hints") or []),
            "provider_hints_are_active": False,
        }
    return out


COMPONENT_CATALOG_STATIC = _component_catalog_static()


def _project_from_progress(progress_envelope: dict[str, Any]) -> dict[str, Any]:
    data = dict(progress_envelope.get("data") or {})
    safe = data.get("safe_next_action")
    if not isinstance(safe, dict):
        for item in progress_envelope.get("next_actions") or []:
            if isinstance(item, dict) and item.get("code"):
                safe = item
                break
    return {
        "product_ready": data.get("product_ready"),
        "config_ok": data.get("config_ok"),
        "provider_sync_required": data.get("provider_sync_required"),
        "sync_state": data.get("sync_state"),
        "provider_ask_clean": data.get("provider_ask_clean"),
        "task_cache_current": data.get("task_cache_current"),
        "closeout_complete": data.get("closeout_complete"),
        "implementation_ready": data.get("implementation_ready"),
        "next_actionable_task": data.get("next_actionable_task"),
        "no_actionable_next_task": data.get("no_actionable_next_task"),
        "blocked_reasons": list(data.get("blocked_reasons") or []),
        "safe_next_action": dict(safe) if isinstance(safe, dict) else None,
        "observed_head": data.get("observed_head"),
        "components": dict(data.get("components") or {}),
        "capability_profile": dict(data.get("capability_profile") or {}),
        "capability_guidance": dict(data.get("capability_guidance") or {}),
        "knowledge_enabled": data.get("knowledge_enabled"),
        "task_enabled": data.get("task_enabled"),
    }


def build_describe(
    *,
    repo_root: Path,
    progress_envelope: dict[str, Any] | None = None,
    observed_head: str | None = None,
    git_status_short: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Build readonly Describe envelope.

    When ``progress_envelope`` is omitted, Progress is used as the accepted
    projection source. Describe does not independently probe NotebookLM/Beads.
    """
    root = Path(repo_root)
    if progress_envelope is None:
        progress_envelope = build_progress(repo_root=root)
    projected = _project_from_progress(progress_envelope)
    head = observed_head if observed_head is not None else read_observed_head(root)
    status_text = (
        git_status_short
        if git_status_short is not None
        else read_git_status_short(root)
    )

    safe = projected.get("safe_next_action")
    if not isinstance(safe, dict):
        safe = next_action(
            code="CHECK_PROGRESS",
            command="vibe progress --json",
            mutation=False,
            reason="No safe_next projected from Engine Progress",
        )
    next_actions = [dict(safe)]

    authority = {
        "engine": "Vibe Control Engine",
        "gateway_skills": "thin routers to Engine CLI only",
        "repo_ssot": True,
        "notebooklm": "optional derived knowledge provider; not SSOT",
        "local_fts": (
            "optional/default-capable free derived retrieval index (SQLite FTS5); not SSOT"
        ),
        "beads": "local_embedded_ephemeral task cache; provider_task_id is binding only",
        "hetu": (
            "optional code-structure capability (codebase_memory); "
            "IndexBindingReceipt + strict freshness; default disabled"
        ),
        "chatgpt_project_sources": (
            "external advisor context copies only; not a product closeout gate"
        ),
        "describe": "readonly explanation / projection; never owns readiness or mutation",
        "capability_profile": (
            "Engine-owned default-disabled profile; Engine readiness and capability "
            "readiness are separate; disabled capabilities do not fail product_ready"
        ),
        "provider_task_id": "binding result only; never source identity",
        "chatgpt_project_sources_required": False,
    }
    authority_map = {
        "engine": authority["engine"],
        "gateway_skills": authority["gateway_skills"],
        "repo_ssot": "docs/project/* specs + vibe-control-roadmap-state.md",
        "notebooklm": authority["notebooklm"],
        "local_fts": authority["local_fts"],
        "beads": authority["beads"],
        "hetu": authority["hetu"],
        "chatgpt_project_sources": authority["chatgpt_project_sources"],
        "describe": authority["describe"],
        "capability_profile": authority["capability_profile"],
    }

    evidence = build_evidence_v1(
        operation="describe",
        mode="readonly_describe",
        observed_head_value=head,
        git_status_short_empty=status_text == "",
        generated_from=[
            "static control-surface catalogs",
            "COMPONENT_CATALOG (static)",
            "vibe progress (projection source)",
        ],
        steps=[
            "load_static_authority_and_surfaces",
            "load_static_component_catalog",
            "project_progress_envelope",
            "embed_evidence_v1",
        ],
        blocked_reasons=list(projected.get("blocked_reasons") or []),
        next_actions=next_actions,
        run_id=run_id,
        recorded_baseline_commit=(
            (progress_envelope.get("data") or {}).get("recorded_baseline_commit")
            if isinstance(progress_envelope.get("data"), dict)
            else None
        ),
        projected_fields=projected,
    )

    data = {
        "describe_version": DESCRIBE_VERSION,
        "describe": True,
        "surface": "describe",
        "mutation": False,
        "source_of_truth": "engine",
        "facts_embedded": False,
        "probe_policy": "static_or_projection_sources_only",
        "evidence_class": "projected_ephemeral_s1",
        "authority": authority,
        "authority_map": authority_map,
        "engine_surfaces": list(ENGINE_SURFACES),
        "readonly_surfaces": list(READONLY_SURFACES),
        "mutation_surfaces": list(MUTATION_SURFACES),
        "operation_evidence": dict(OPERATION_EVIDENCE_CONTRACT),
        "component_catalog": dict(COMPONENT_CATALOG_STATIC),
        "capability_guidance": dict(projected.get("capability_guidance") or {}),
        "non_goals": list(DESCRIBE_NON_GOALS),
        "knowledge_provider_selection_guidance": list(KNOWLEDGE_PROVIDER_SELECTION_GUIDANCE),
        "knowledge_multi_notebook_guidance": list(KNOWLEDGE_MULTI_NOTEBOOK_GUIDANCE),
        "communication_contracts": {
            "self_grill": self_grill_contract_dict(),
            "skill_assay": skill_assay_contract_dict(),
            "git_land": git_land_contract_dict(),
            "owner_plain_language": owner_plain_language_contract_dict(),
        },
        "projected": projected,
        "safe_next": dict(safe),
        "next_actions": next_actions,
        "observed_head": head,
        "git_status_short_empty": status_text == "",
        "progress_command": "vibe progress --json",
        "evidence": evidence,
        "evidence_hash": evidence["evidence_hash"],
        "summary": (
            "Describe explains Engine-owned control surfaces, authority, mutation classes, "
            "operation evidence (mutation_intent/mutation_performed), and component catalog. "
            "Current readiness/next fields are projected from Engine Progress only — Describe "
            "does not recompute them. Capability Profile guidance is projection-only "
            "(Engine vs capability readiness are separate). Approval remains capability-specific."
        ),
    }
    envelope = success_envelope(
        command="vibe describe",
        project_id=progress_envelope.get("project_id"),
        mode="readonly_describe",
        data=data,
        warnings=list(progress_envelope.get("warnings") or []),
        next_actions=next_actions,
    )
    return attach_operation_result(envelope, mutation_intent=False, effects=[])
