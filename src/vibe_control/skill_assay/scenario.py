"""Scenario loading for Skill Assay."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from vibe_control.skill_assay.constants import (
    EXECUTION_PROFILES,
    SCHEMA_SCENARIO,
    TYPED_CHECK_KINDS,
)
from vibe_control.skill_assay.errors import SkillAssayError


def load_scenario(path: Path) -> dict[str, Any]:
    raw_path = Path(path)
    if not raw_path.is_file():
        raise SkillAssayError(
            "SKILL_ASSAY_SCENARIO_MISSING",
            f"scenario file not found: {path}",
            {"path": str(path)},
        )
    data = yaml.safe_load(raw_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SkillAssayError(
            "SKILL_ASSAY_SCENARIO_INVALID",
            "scenario must be a YAML mapping",
            {"path": str(path)},
        )
    schema = str(data.get("schema") or "")
    if schema and schema != SCHEMA_SCENARIO:
        raise SkillAssayError(
            "SKILL_ASSAY_SCENARIO_SCHEMA_INVALID",
            f"scenario schema must be {SCHEMA_SCENARIO}",
            {"schema": schema},
        )
    prompt = str(data.get("prompt") or "").strip()
    if not prompt:
        raise SkillAssayError(
            "SKILL_ASSAY_SCENARIO_PROMPT_REQUIRED",
            "scenario.prompt is required",
            {"path": str(path)},
        )
    checks = data.get("checks") or []
    if checks is None:
        checks = []
    if not isinstance(checks, list):
        raise SkillAssayError(
            "SKILL_ASSAY_SCENARIO_INVALID",
            "scenario.checks must be a list",
        )
    normalized_checks: list[dict[str, Any]] = []
    for index, check in enumerate(checks):
        if not isinstance(check, dict):
            raise SkillAssayError(
                "SKILL_ASSAY_SCENARIO_INVALID",
                f"checks[{index}] must be a mapping",
            )
        kind = str(check.get("kind") or "").strip()
        if kind not in TYPED_CHECK_KINDS:
            raise SkillAssayError(
                "SKILL_ASSAY_CHECK_KIND_INVALID",
                f"unsupported check kind: {kind!r}",
                {"kind": kind, "allowed": sorted(TYPED_CHECK_KINDS)},
            )
        normalized_checks.append(dict(check))

    profile = str(data.get("execution_profile") or "response_only").strip()
    if profile not in EXECUTION_PROFILES:
        raise SkillAssayError(
            "SKILL_ASSAY_EXECUTION_PROFILE_INVALID",
            f"unsupported execution_profile: {profile!r}",
            {"execution_profile": profile, "allowed": sorted(EXECUTION_PROFILES)},
        )
    return {
        "schema": SCHEMA_SCENARIO,
        "prompt": prompt,
        "timeout_seconds": int(data.get("timeout_seconds") or 300),
        "model": data.get("model"),
        "execution_profile": profile,
        "target_repo": (
            str(data.get("target_repo")).strip() if data.get("target_repo") else None
        ),
        "checks": normalized_checks,
        "expected_fields": list(data.get("expected_fields") or []),
    }


def scenario_from_prompt_file(path: Path) -> dict[str, Any]:
    text = Path(path).read_text(encoding="utf-8").strip()
    if not text:
        raise SkillAssayError(
            "SKILL_ASSAY_PROMPT_EMPTY",
            "prompt file is empty",
            {"path": str(path)},
        )
    return {
        "schema": SCHEMA_SCENARIO,
        "prompt": text,
        "timeout_seconds": 300,
        "model": None,
        "execution_profile": "response_only",
        "target_repo": None,
        "checks": [],
        "expected_fields": [],
    }
