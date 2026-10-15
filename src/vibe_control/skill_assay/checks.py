"""Typed acceptance checks for Skill Assay (no arbitrary shell)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from vibe_control.skill_assay.constants import TYPED_CHECK_KINDS
from vibe_control.skill_assay.errors import SkillAssayError


def run_typed_checks(
    checks: list[dict[str, Any]],
    *,
    artifact_dir: Path,
    exit_status: int | None = None,
    git_diff_text: str | None = None,
    assistant_text: str | None = None,
) -> list[dict[str, Any]]:
    artifact_root = Path(artifact_dir).resolve()
    results: list[dict[str, Any]] = []
    for index, check in enumerate(checks):
        kind = str(check.get("kind") or "")
        if kind not in TYPED_CHECK_KINDS:
            raise SkillAssayError(
                "SKILL_ASSAY_CHECK_KIND_INVALID",
                f"unsupported check kind: {kind!r}",
                {"kind": kind},
            )
        fact_id = f"checks[{index}]"
        if kind == "file_exists":
            rel = str(check.get("path") or "")
            target = _safe_join(artifact_root, rel)
            results.append(
                {
                    "fact_id": fact_id,
                    "kind": kind,
                    "path": rel,
                    "pass": target.is_file(),
                }
            )
        elif kind == "text_match":
            rel = str(check.get("path") or "")
            needle = str(check.get("contains") or "")
            target = _safe_join(artifact_root, rel)
            passed = False
            if target.is_file():
                passed = needle in target.read_text(encoding="utf-8", errors="replace")
            results.append(
                {
                    "fact_id": fact_id,
                    "kind": kind,
                    "path": rel,
                    "contains": needle,
                    "pass": passed,
                }
            )
        elif kind == "assistant_text_match":
            needle = str(check.get("contains") or "")
            text = assistant_text or ""
            results.append(
                {
                    "fact_id": fact_id,
                    "kind": kind,
                    "contains": needle,
                    "pass": bool(needle) and needle in text,
                }
            )
        elif kind == "json_schema":
            # Minimal: file exists and is valid JSON object/array.
            # Optional required keys when provided as list[str].
            rel = str(check.get("path") or "")
            required = check.get("required") or []
            target = _safe_join(artifact_root, rel)
            passed = False
            if target.is_file():
                try:
                    parsed = json.loads(target.read_text(encoding="utf-8"))
                    if isinstance(parsed, dict):
                        if isinstance(required, list) and required:
                            passed = all(str(k) in parsed for k in required)
                        else:
                            passed = True
                    else:
                        passed = isinstance(parsed, list) and not required
                except json.JSONDecodeError:
                    passed = False
            results.append(
                {
                    "fact_id": fact_id,
                    "kind": kind,
                    "path": rel,
                    "required": list(required) if isinstance(required, list) else [],
                    "pass": passed,
                }
            )
        elif kind == "exit_status":
            expected = int(check.get("equals", 0))
            results.append(
                {
                    "fact_id": fact_id,
                    "kind": kind,
                    "equals": expected,
                    "actual": exit_status,
                    "pass": exit_status == expected,
                }
            )
        elif kind == "git_diff":
            contains = str(check.get("contains") or "")
            text = git_diff_text or ""
            results.append(
                {
                    "fact_id": fact_id,
                    "kind": kind,
                    "contains": contains,
                    "pass": contains in text if contains else bool(text),
                }
            )
        else:  # pragma: no cover - guarded by TYPED_CHECK_KINDS
            raise SkillAssayError(
                "SKILL_ASSAY_CHECK_KIND_INVALID",
                f"unsupported check kind: {kind!r}",
            )
    return results


def _safe_join(root: Path, rel: str) -> Path:
    if not rel or rel.startswith(("/", "\\")) or ".." in Path(rel).parts:
        raise SkillAssayError(
            "SKILL_ASSAY_PATH_ESCAPE",
            f"path escapes artifact directory: {rel!r}",
            {"path": rel},
        )
    candidate = (root / rel).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise SkillAssayError(
            "SKILL_ASSAY_PATH_ESCAPE",
            f"path escapes artifact directory: {rel!r}",
            {"path": rel},
        ) from exc
    return candidate
