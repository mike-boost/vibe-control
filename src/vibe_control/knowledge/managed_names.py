"""Provider-neutral managed name and upload filename helpers."""

from __future__ import annotations

import re


_SEP_RE = re.compile(r"[^a-zA-Z0-9_-]+")
_MULTI_US = re.compile(r"_+")
_MULTI_HY = re.compile(r"-+")


def slug_project(project_id: str) -> str:
    text = (project_id or "").strip().lower()
    text = _SEP_RE.sub("-", text)
    text = _MULTI_HY.sub("-", text).strip("-")
    return text or "project"


def slug_doc(doc_id: str) -> str:
    text = (doc_id or "").strip().lower()
    text = _SEP_RE.sub("_", text)
    text = _MULTI_US.sub("_", text).strip("_")
    return text or "doc"


def managed_name(project_id: str, doc_id: str) -> str:
    return f"vibe__{slug_project(project_id)}__{slug_doc(doc_id)}"


def upload_filename(
    managed: str,
    content_sha256: str,
    *,
    extension: str = ".md",
) -> str:
    """Build upload basename: vibe__…__h__<sha12><extension>.

    ``extension`` should include the leading dot (e.g. ``.pdf``). Defaults to
    ``.md`` for backward compatibility. Provider format policy decides which
    extensions are allowed before upload.
    """
    raw = (content_sha256 or "").strip().lower()
    if raw.startswith("sha256:"):
        raw = raw[len("sha256:") :]
    sha12 = raw[:12]
    if len(sha12) != 12 or any(c not in "0123456789abcdef" for c in sha12):
        raise ValueError("content_sha256 must provide at least 12 hex chars")
    ext = extension if extension.startswith(".") else f".{extension}"
    ext = ext.lower()
    if ext == ".":
        ext = ".md"
    return f"{managed}__h__{sha12}{ext}"


def parse_managed_name(title: str) -> dict[str, str] | None:
    text = (title or "").strip()
    # Strip a trailing file extension so hashed names parse for .md/.pdf/…
    if "." in text.rsplit("/", 1)[-1]:
        stem, _dot, _ext = text.rpartition(".")
        if stem and _ext and "/" not in _ext and len(_ext) <= 10:
            text = stem
    parts = text.split("__")
    if len(parts) < 3 or parts[0] != "vibe":
        return None
    project_id = parts[1]
    # hashed form: vibe__proj__doc__h__sha12
    if len(parts) >= 5 and parts[-2] == "h":
        doc_id = "__".join(parts[2:-2])
        return {
            "project_id": project_id,
            "doc_id": doc_id,
            "kind": "hashed_filename",
            "sha12": parts[-1],
        }
    doc_id = "__".join(parts[2:])
    return {"project_id": project_id, "doc_id": doc_id, "kind": "name"}


def content_sha256_bytes(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def content_sha256_file(path) -> str:
    from pathlib import Path

    return content_sha256_bytes(Path(path).read_bytes())
