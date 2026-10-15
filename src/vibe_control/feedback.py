"""Consumer-repo experience feedback artifacts (vibe.feedback.v1).

Not a task system. Local files only; never uploads.
"""

from __future__ import annotations

import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from vibe_control import __version__

SCHEMA = "vibe.feedback.v1"
REDACTION_POLICY = "vibe.feedback.redaction.v1"
FEEDBACK_KINDS = frozenset(
    {"pain", "owner_dissatisfaction", "bright_spot", "friction", "bug_signal"}
)
DEFAULT_ROOT_REL = "runtime/vibe-feedback"

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*\S+"),
    re.compile(r"(?i)(password|passwd|secret)\s*[:=]\s*\S+"),
    re.compile(r"(?i)bearer\s+[a-z0-9\-._~+/]+=*"),
    re.compile(r"-----BEGIN (?:RSA )?PRIVATE KEY-----"),
    re.compile(r"(?i)NOTEBOOKLM_NOTEBOOK[_A-Z0-9]*=\S+"),
    re.compile(r"(?i)https?://[^\s]*[?&](token|access_token|key)=[^\s&]+"),
)


class FeedbackError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def feedback_root(repo_root: Path) -> Path:
    return (repo_root / DEFAULT_ROOT_REL).resolve()


def new_feedback_id(*, now: datetime | None = None) -> str:
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%d-%H%M%S")
    return f"fb-{stamp}"


def redaction_checklist() -> list[str]:
    return [
        "Strip tokens, cookies, session material",
        "Strip .env / secret file contents",
        "Strip raw notebook refs / private provider source IDs",
        "Strip passwords, PATs, unnecessary personal emails",
        "Keep vibe version, envelope codes, capability booleans, expected vs actual",
        "Set redaction.confirmed: true only after review",
    ]


def init_preview(*, repo_root: Path) -> dict[str, Any]:
    root = feedback_root(repo_root)
    return {
        "schema": SCHEMA,
        "feedback_root": root.as_posix(),
        "feedback_root_relative": DEFAULT_ROOT_REL,
        "kinds": sorted(FEEDBACK_KINDS),
        "redaction_policy": REDACTION_POLICY,
        "redaction_checklist": redaction_checklist(),
        "share_policy": "voluntary_only_never_auto_upload",
        "not_a_task": True,
        "mutation": False,
    }


def _load_project_id(repo_root: Path) -> str | None:
    try:
        from vibe_control.config import load_config

        return load_config(repo_root).project_id
    except Exception:
        return None


def build_draft_document(
    *,
    kind: str,
    title: str,
    summary: str,
    desired: str = "",
    feedback_id: str | None = None,
    repo_root: Path,
    vibe_version: str | None = None,
    related_paths: list[str] | None = None,
    related_task_ids: list[str] | None = None,
    envelope_codes: list[str] | None = None,
) -> dict[str, Any]:
    if kind not in FEEDBACK_KINDS:
        raise FeedbackError(
            "FEEDBACK_KIND_INVALID",
            f"kind must be one of: {', '.join(sorted(FEEDBACK_KINDS))}",
            {"kind": kind},
        )
    title = title.strip()
    summary = summary.strip()
    if not title:
        raise FeedbackError("FEEDBACK_TITLE_EMPTY", "title is required")
    if not summary:
        raise FeedbackError("FEEDBACK_SUMMARY_EMPTY", "summary is required")

    fid = feedback_id or new_feedback_id()
    doc: dict[str, Any] = {
        "schema": SCHEMA,
        "id": fid,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "vibe_version": vibe_version or __version__,
        "consumer_project_id": _load_project_id(repo_root),
        "kind": kind,
        "title": title,
        "summary": summary,
        "context": {
            "commands": [],
            "envelope_codes": list(envelope_codes or []),
            "capability": {
                "knowledge_enabled": None,
                "task_enabled": None,
            },
            "related_paths": list(related_paths or []),
            "related_task_ids": list(related_task_ids or []),
        },
        "redaction": {
            "policy": REDACTION_POLICY,
            "confirmed": False,
        },
        "attachments": [],
    }
    if desired.strip():
        doc["desired"] = desired.strip()
    return doc


def draft_feedback(
    *,
    repo_root: Path,
    kind: str,
    title: str,
    summary: str,
    desired: str = "",
    feedback_id: str | None = None,
    related_paths: list[str] | None = None,
    related_task_ids: list[str] | None = None,
    envelope_codes: list[str] | None = None,
) -> dict[str, Any]:
    doc = build_draft_document(
        kind=kind,
        title=title,
        summary=summary,
        desired=desired,
        feedback_id=feedback_id,
        repo_root=repo_root,
        related_paths=related_paths,
        related_task_ids=related_task_ids,
        envelope_codes=envelope_codes,
    )
    fid = str(doc["id"])
    entry_dir = feedback_root(repo_root) / fid
    entry_dir.mkdir(parents=True, exist_ok=True)
    path = entry_dir / "feedback.yaml"
    if path.exists():
        raise FeedbackError(
            "FEEDBACK_EXISTS",
            f"Feedback artifact already exists: {path.as_posix()}",
            {"path": path.as_posix()},
        )
    path.write_text(
        yaml.safe_dump(doc, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    readme = entry_dir / "REDACTION.md"
    readme.write_text(
        "# Redaction checklist\n\n"
        + "\n".join(f"- [ ] {item}" for item in redaction_checklist())
        + "\n\nSet `redaction.confirmed: true` in feedback.yaml only after review.\n"
        "Sharing with the Vibe team is voluntary. Never auto-upload.\n",
        encoding="utf-8",
    )
    return {
        "id": fid,
        "path": path.as_posix(),
        "entry_dir": entry_dir.as_posix(),
        "document": doc,
        "mutation": True,
        "upload": False,
        "next_hint": "Review REDACTION.md, set redaction.confirmed: true, then vibe feedback validate",
    }


def _walk_strings(value: Any) -> list[str]:
    out: list[str] = []
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, dict):
        for v in value.values():
            out.extend(_walk_strings(v))
    elif isinstance(value, list):
        for v in value:
            out.extend(_walk_strings(v))
    return out


def find_secret_hits(document: dict[str, Any]) -> list[str]:
    hits: list[str] = []
    for text in _walk_strings(document):
        for pat in _SECRET_PATTERNS:
            if pat.search(text):
                hits.append(pat.pattern)
                break
    return hits


def load_feedback_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FeedbackError(
            "FEEDBACK_FILE_NOT_FOUND",
            f"Feedback file not found: {path.as_posix()}",
            {"path": path.as_posix()},
        )
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise FeedbackError(
            "FEEDBACK_YAML_INVALID",
            f"Could not parse feedback YAML: {exc}",
            {"path": path.as_posix()},
        ) from exc
    if not isinstance(raw, dict):
        raise FeedbackError(
            "FEEDBACK_YAML_INVALID",
            "Feedback YAML root must be a mapping",
            {"path": path.as_posix()},
        )
    return raw


def resolve_feedback_path(repo_root: Path, path_or_id: str) -> Path:
    candidate = Path(path_or_id)
    if candidate.is_file():
        return candidate.resolve()
    root = feedback_root(repo_root)
    by_id = root / path_or_id / "feedback.yaml"
    if by_id.is_file():
        return by_id
    as_rel = (repo_root / path_or_id).resolve()
    if as_rel.is_file():
        return as_rel
    raise FeedbackError(
        "FEEDBACK_FILE_NOT_FOUND",
        f"Could not resolve feedback path or id: {path_or_id}",
        {"path_or_id": path_or_id, "tried": [by_id.as_posix()]},
    )


def validate_feedback_document(document: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if document.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA}")
    kind = document.get("kind")
    if kind not in FEEDBACK_KINDS:
        errors.append("kind invalid")
    if not str(document.get("title") or "").strip():
        errors.append("title required")
    if not str(document.get("summary") or "").strip():
        errors.append("summary required")
    if not str(document.get("id") or "").strip():
        errors.append("id required")

    redaction = document.get("redaction")
    if not isinstance(redaction, dict):
        errors.append("redaction object required")
        confirmed = False
    else:
        if redaction.get("policy") != REDACTION_POLICY:
            errors.append(f"redaction.policy must be {REDACTION_POLICY}")
        confirmed = bool(redaction.get("confirmed"))
        if not confirmed:
            errors.append("redaction.confirmed must be true before validate/pack/share")

    secret_hits = find_secret_hits(document)
    if secret_hits:
        errors.append("possible secrets detected; redact before confirming")

    return {
        "ok": not errors,
        "errors": errors,
        "redaction_confirmed": confirmed,
        "secret_hit_patterns": secret_hits,
        "checklist": redaction_checklist(),
    }


def validate_feedback(*, repo_root: Path, path_or_id: str) -> dict[str, Any]:
    path = resolve_feedback_path(repo_root, path_or_id)
    document = load_feedback_yaml(path)
    result = validate_feedback_document(document)
    result["path"] = path.as_posix()
    result["id"] = document.get("id")
    result["mutation"] = False
    result["upload"] = False
    return result


def pack_feedback(*, repo_root: Path, path_or_id: str) -> dict[str, Any]:
    path = resolve_feedback_path(repo_root, path_or_id)
    document = load_feedback_yaml(path)
    check = validate_feedback_document(document)
    if not check["ok"]:
        raise FeedbackError(
            "FEEDBACK_VALIDATE_FAILED",
            "Feedback must validate before pack",
            {"errors": check["errors"], "path": path.as_posix()},
        )
    entry_dir = path.parent
    fid = str(document.get("id") or entry_dir.name)
    zip_path = feedback_root(repo_root) / f"vibe-feedback-{fid}.zip"
    feedback_root(repo_root).mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for child in sorted(entry_dir.rglob("*")):
            if child.is_file():
                zf.write(child, arcname=f"{fid}/{child.relative_to(entry_dir).as_posix()}")
    return {
        "id": fid,
        "zip_path": zip_path.as_posix(),
        "source_dir": entry_dir.as_posix(),
        "mutation": True,
        "upload": False,
        "share_policy": "voluntary_only_never_auto_upload",
    }
