"""Local diagnostics bundle helpers (redacted; never upload)."""

from __future__ import annotations

import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vibe_control import __version__
from vibe_control.feedback import DEFAULT_ROOT_REL, FeedbackError, feedback_root

_SENSITIVE_KEY_RE = re.compile(
    r"(?i)(token|secret|password|passwd|cookie|authorization|api[_-]?key|"
    r"notebook_ref|notebook_id|source_id|provider_source_id|raw_ref|access_key)"
)


def redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if _SENSITIVE_KEY_RE.search(str(key)):
                out[key] = "[REDACTED]"
            else:
                out[key] = redact_value(item)
        return out
    if isinstance(value, list):
        return [redact_value(v) for v in value]
    if isinstance(value, str):
        # Long opaque ids that look like UUIDs in notebook contexts — keep short hash only
        if re.fullmatch(
            r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
            value,
        ):
            return f"[REDACTED_UUID:{value[:8]}…]"
        return value
    return value


def write_diagnostics_bundle(
    *,
    repo_root: Path,
    doctor_envelope: dict[str, Any],
    skills_status: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write a local redacted zip under runtime/vibe-feedback/diagnostics/."""
    root = feedback_root(repo_root) / "diagnostics"
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    entry = root / f"diag-{stamp}"
    entry.mkdir(parents=True, exist_ok=True)

    manifest = {
        "schema": "vibe.diagnostics.v1",
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "vibe_version": __version__,
        "redaction": {"policy": "vibe.feedback.redaction.v1", "confirmed": True},
        "share_policy": "voluntary_only_never_auto_upload",
        "files": ["manifest.json", "doctor-redacted.json", "skills-status-redacted.json"],
    }
    if extra:
        manifest["extra"] = redact_value(extra)

    doctor_path = entry / "doctor-redacted.json"
    skills_path = entry / "skills-status-redacted.json"
    manifest_path = entry / "manifest.json"

    doctor_path.write_text(
        json.dumps(redact_value(doctor_envelope), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    skills_path.write_text(
        json.dumps(redact_value(skills_status or {}), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    zip_path = root / f"vibe-diagnostics-{stamp}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for child in sorted(entry.rglob("*")):
            if child.is_file():
                zf.write(child, arcname=f"{entry.name}/{child.relative_to(entry).as_posix()}")

    return {
        "entry_dir": entry.as_posix(),
        "zip_path": zip_path.as_posix(),
        "relative_root": f"{DEFAULT_ROOT_REL}/diagnostics",
        "mutation": True,
        "upload": False,
        "share_policy": "voluntary_only_never_auto_upload",
    }


def attach_doctor_snippet(
    *,
    entry_dir: Path,
    feedback_yaml: Path,
    doctor_envelope: dict[str, Any],
) -> dict[str, Any]:
    """Write doctor-redacted.json next to feedback.yaml and update attachments."""
    import yaml

    if not feedback_yaml.is_file():
        raise FeedbackError(
            "FEEDBACK_FILE_NOT_FOUND",
            f"Feedback file not found: {feedback_yaml.as_posix()}",
        )
    snippet_name = "doctor-redacted.json"
    snippet_path = entry_dir / snippet_name
    snippet_path.write_text(
        json.dumps(redact_value(doctor_envelope), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    doc = yaml.safe_load(feedback_yaml.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise FeedbackError("FEEDBACK_YAML_INVALID", "Feedback YAML root must be a mapping")
    attachments = list(doc.get("attachments") or [])
    attachments = [a for a in attachments if not (isinstance(a, dict) and a.get("path") == snippet_name)]
    attachments.append({"path": snippet_name, "kind": "doctor_snippet"})
    doc["attachments"] = attachments
    feedback_yaml.write_text(
        yaml.safe_dump(doc, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return {
        "attachment_path": snippet_path.as_posix(),
        "attachments": attachments,
    }
