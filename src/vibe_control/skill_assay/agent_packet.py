"""Single-file agent handoff packet for Skill Assay folders."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vibe_control.skill_assay.storage import assay_dir, write_json_atomic


def build_agent_packet(report: dict[str, Any], *, repo_root: Path) -> dict[str, Any]:
    assay_id = str(report.get("assay_id") or "")
    root = assay_dir(repo_root, assay_id)
    return {
        "schema": "vibe.skill_assay.agent_packet.v1",
        "purpose": (
            "Load this file in a coding agent to improve the assayed skill. "
            "Treat OWNER_REPORT.html as human context; this packet is authoritative for agents."
        ),
        "assay_id": assay_id,
        "host_id": report.get("host_id"),
        "skill_hint": "Inspect snapshot/ under the assay folder for the exact skill tree that was tested.",
        "verdicts": [
            {
                "id": h.get("id"),
                "verdict": h.get("verdict"),
                "claim": h.get("claim"),
                "evidence_refs": h.get("evidence_refs"),
            }
            for h in list(report.get("hypotheses") or [])
            if isinstance(h, dict)
        ],
        "facts": list(report.get("facts") or []),
        "unknowns": list(report.get("unknowns") or []),
        "checks_summary": dict(report.get("checks_summary") or {}),
        "local_paths": {
            "assay_dir": root.as_posix(),
            "owner_html": (root / "OWNER_REPORT.html").as_posix(),
            "report_json": (root / "report.json").as_posix(),
            "evidence_json": (root / "evidence.json").as_posix(),
            "runs_glob": (root / "runs" / "*.assistant_text").as_posix(),
        },
        "suggested_agent_actions": [
            "Read OWNER_REPORT.html conclusions and unknowns first.",
            "Diff skill instructions against failing or partial verdicts.",
            "Propose minimal skill/doc/script changes; do not invent evidence the assay did not collect.",
            "If business-quality was unknown, ask for a deeper assay with a real target repository.",
        ],
        "generated_at": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
    }


def write_agent_packet(repo_root: Path, assay_id: str, packet: dict[str, Any]) -> Path:
    path = assay_dir(repo_root, assay_id) / "AGENT_PACKET.json"
    write_json_atomic(path, packet)
    return path
