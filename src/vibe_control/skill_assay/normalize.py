"""Normalize host run outputs into comparable Skill Assay fields."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from vibe_control.skill_assay.redaction import redact_text

_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", re.DOTALL | re.IGNORECASE)
_JSON_OBJECT = re.compile(r"(\{.*\})", re.DOTALL)


def sha256_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def extract_json_object(text: str) -> dict[str, Any] | None:
    raw = text or ""
    for match in _JSON_FENCE.finditer(raw):
        try:
            parsed = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    match = _JSON_OBJECT.search(raw)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def load_artifact_json(artifact_dir: Path, rel: str = "out.json") -> dict[str, Any] | None:
    path = Path(artifact_dir) / rel
    if not path.is_file():
        return None
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def normalize_fields(
    *,
    assistant_text: str,
    artifact_dir: Path,
    scenario: dict[str, Any],
    base_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build comparable fields from artifact JSON and/or assistant text."""
    fields: dict[str, Any] = dict(base_fields or {})
    artifact = load_artifact_json(Path(artifact_dir))
    if artifact:
        fields.update(artifact)
    from_text = extract_json_object(assistant_text)
    if from_text:
        # Artifact wins on key collisions; fill missing only.
        for key, value in from_text.items():
            fields.setdefault(key, value)

    expected = list(scenario.get("expected_fields") or [])
    for key in expected:
        fields.setdefault(key, None)

    redacted = redact_text(assistant_text or "")
    fields.setdefault("assistant_text_sha256", sha256_text(redacted))
    fields.setdefault("assistant_nonempty", bool(redacted.strip()))
    return fields
