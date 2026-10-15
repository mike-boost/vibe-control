"""Local receipt storage for Skill Assay."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vibe_control.skill_assay.constants import DEFAULT_ROOT_REL, SCHEMA_EVIDENCE, SCHEMA_META
from vibe_control.skill_assay.errors import SkillAssayError


def assay_root(repo_root: Path) -> Path:
    return (Path(repo_root) / DEFAULT_ROOT_REL).resolve()


def new_assay_id(*, host_id: str | None = None, now: datetime | None = None) -> str:
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%d-%H%M%S")
    host = "".join(ch if ch.isalnum() else "-" for ch in str(host_id or "").strip().lower())
    host = host.strip("-")
    if host:
        return f"assay-{host}-{stamp}"
    return f"assay-{stamp}"


def assay_dir(repo_root: Path, assay_id: str) -> Path:
    return assay_root(repo_root) / assay_id


def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SkillAssayError(
            "SKILL_ASSAY_RECEIPT_MISSING",
            f"receipt not found: {path}",
            {"path": path.as_posix()},
        )
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SkillAssayError(
            "SKILL_ASSAY_RECEIPT_INVALID",
            f"receipt must be a JSON object: {path}",
            {"path": path.as_posix()},
        )
    return raw


def write_meta(repo_root: Path, assay_id: str, meta: dict[str, Any]) -> Path:
    path = assay_dir(repo_root, assay_id) / "meta.json"
    payload = {"schema": SCHEMA_META, "assay_id": assay_id, **meta}
    write_json_atomic(path, payload)
    return path


def write_evidence(repo_root: Path, assay_id: str, evidence: dict[str, Any]) -> Path:
    path = assay_dir(repo_root, assay_id) / "evidence.json"
    payload = dict(evidence)
    payload.setdefault("schema", SCHEMA_EVIDENCE)
    payload["assay_id"] = assay_id
    write_json_atomic(path, payload)
    return path


def load_evidence(repo_root: Path, assay_id: str) -> dict[str, Any]:
    return read_json(assay_dir(repo_root, assay_id) / "evidence.json")


def write_analysis(repo_root: Path, assay_id: str, analysis: dict[str, Any]) -> Path:
    path = assay_dir(repo_root, assay_id) / "analysis.json"
    write_json_atomic(path, analysis)
    return path


def write_report(repo_root: Path, assay_id: str, report: dict[str, Any]) -> Path:
    path = assay_dir(repo_root, assay_id) / "report.json"
    write_json_atomic(path, report)
    return path


def write_owner_report_markdown(repo_root: Path, assay_id: str, markdown: str) -> Path:
    path = assay_dir(repo_root, assay_id) / "OWNER_REPORT.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown.rstrip() + "\n", encoding="utf-8")
    return path


def load_report(repo_root: Path, assay_id: str) -> dict[str, Any]:
    return read_json(assay_dir(repo_root, assay_id) / "report.json")
