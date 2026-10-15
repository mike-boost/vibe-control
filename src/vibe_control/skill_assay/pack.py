"""Pack a Skill Assay folder into a shareable zip."""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any

from vibe_control.skill_assay.errors import SkillAssayError
from vibe_control.skill_assay.storage import assay_dir


def pack_assay(
    *,
    repo_root: Path,
    assay_id: str,
    output_path: Path | None = None,
) -> dict[str, Any]:
    root = assay_dir(repo_root, assay_id)
    if not root.is_dir():
        raise SkillAssayError(
            "SKILL_ASSAY_RECEIPT_MISSING",
            f"assay folder not found: {root}",
            {"assay_id": assay_id},
        )
    out = (
        Path(output_path)
        if output_path is not None
        else (root.parent / f"{assay_id}.zip")
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                zf.write(path, arcname=f"{assay_id}/{path.relative_to(root).as_posix()}")
    return {
        "assay_id": assay_id,
        "zip_path": out.resolve().as_posix(),
        "includes_owner_html": (root / "OWNER_REPORT.html").is_file(),
        "includes_agent_packet": (root / "AGENT_PACKET.json").is_file(),
    }
