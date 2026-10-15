"""Skill Assay brief — agent self-explain entry (readonly unless doctor only)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from vibe_control.json_envelope import attach_operation_result, success_envelope
from vibe_control.skill_assay.contract import (
    SKILL_ASSAY_CONTRACT_ID,
    skill_assay_contract_dict,
    skill_assay_entry_next_actions,
)
from vibe_control.skill_assay.errors import SkillAssayError
from vibe_control.skill_assay.registry import build_adapter_registry


def build_skill_assay_brief(
    *,
    repo_root: Path,
    skill_path: str | None = None,
    host_id: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Readonly brief: contract + optional skill/host binding + next_actions."""
    contract = skill_assay_contract_dict()
    host = (host_id or "").strip() or None
    skill = (skill_path or "").strip() or None

    skill_meta: dict[str, Any] | None = None
    if skill:
        path = Path(skill)
        if not path.is_absolute():
            path = (Path(repo_root) / path).resolve()
        else:
            path = path.resolve()
        skill_md = path / "SKILL.md"
        skill_meta = {
            "path": path.as_posix(),
            "exists": path.is_dir(),
            "skill_md_present": skill_md.is_file(),
            "skill_id": path.name if path.is_dir() else None,
        }
        if not skill_meta["exists"] or not skill_meta["skill_md_present"]:
            raise SkillAssayError(
                "SKILL_ASSAY_SKILL_MD_MISSING",
                "skill path must be a directory containing SKILL.md",
                skill_meta,
            )

    doctor_payload: dict[str, Any] | None = None
    if host:
        registry = build_adapter_registry(include_fake=True)
        if host not in registry:
            raise SkillAssayError(
                "SKILL_ASSAY_HOST_UNKNOWN",
                f"unknown host_id: {host}",
                {"host_id": host, "allowed": sorted(registry)},
            )
        result = registry[host].doctor()
        doctor_payload = {
            "host_id": result.host_id,
            "ok": result.ok,
            "support_state": result.support_state,
            "blockers": list(result.blockers),
            "details": dict(result.details),
        }

    next_actions = skill_assay_entry_next_actions(
        skill_path=skill_meta["path"] if skill_meta else None,
        host_id=host,
    )
    data = {
        "contract_id": SKILL_ASSAY_CONTRACT_ID,
        "communication_mode": "skill_assay",
        "communication_contract": contract,
        "skill": skill_meta,
        "host_doctor": doctor_payload,
        "agent_instruction": (
            "Owner asked for Skill Assay. Require an explicit host "
            "(cursor or github-copilot; fake is tests-only). "
            "Follow communication_contract.required_workflow. "
            "Start with doctor + diagnose --dry-run. Use --execute only after dry-run. "
            "Never fall back to fake when a real host fails. "
            "Write analysis from current official docs, then finalize. "
            "Talk to the owner in plain language; keep jargon in envelopes."
        ),
        "not_product_ready_gate": True,
        "not_vibe_skills_install": True,
    }
    return attach_operation_result(
        success_envelope(
            command="vibe skill-assay brief",
            project_id=project_id,
            mode="readonly_skill_assay_brief",
            data=data,
            next_actions=next_actions,
        ),
        mutation_intent=False,
        effects=[],
    )
