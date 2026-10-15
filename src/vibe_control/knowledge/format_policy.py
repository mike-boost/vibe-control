"""Per-provider Knowledge file-format policy.

Knowledge is one capability with two providers. Each provider only accepts
formats it can actually use. Corpus listing stays broad; sync/index filters here.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any, Iterable

# local_fts: UTF-8 text + markdown heading chunking only.
LOCAL_FTS_EXTENSIONS: frozenset[str] = frozenset({".md", ".markdown", ".txt"})

# notebooklm / Gemini Notebook upload tip (UI "Supported file types", 2026-07).
# Keep in sync with product UI; do not pretend local_fts can read these.
NOTEBOOKLM_DOCUMENT_EXTENSIONS: frozenset[str] = frozenset(
    {".pdf", ".txt", ".md", ".markdown", ".docx", ".csv", ".pptx", ".epub"}
)
NOTEBOOKLM_IMAGE_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".avif",
        ".bmp",
        ".gif",
        ".ico",
        ".jp2",
        ".png",
        ".webp",
        ".tif",
        ".tiff",
        ".heic",
        ".heif",
        ".jpeg",
        ".jpg",
        ".jpe",
    }
)
NOTEBOOKLM_AV_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".3g2",
        ".3gp",
        ".aac",
        ".aif",
        ".aifc",
        ".aiff",
        ".amr",
        ".au",
        ".avi",
        ".cda",
        ".m4a",
        ".mid",
        ".mp3",
        ".mp4",
        ".mpeg",
        ".ogg",
        ".opus",
        ".ra",
        ".ram",
        ".snd",
        ".wav",
        ".wma",
    }
)
NOTEBOOKLM_EXTENSIONS: frozenset[str] = (
    NOTEBOOKLM_DOCUMENT_EXTENSIONS
    | NOTEBOOKLM_IMAGE_EXTENSIONS
    | NOTEBOOKLM_AV_EXTENSIONS
)

_PROVIDER_EXTENSIONS: dict[str, frozenset[str]] = {
    "local_fts": LOCAL_FTS_EXTENSIONS,
    "notebooklm": NOTEBOOKLM_EXTENSIONS,
}


def normalize_provider(provider: str | None) -> str:
    return str(provider or "").strip().lower()


def extension_of(path: str | Path) -> str:
    """Lowercase suffix including dot; empty if none."""
    suffix = PurePosixPath(str(path).replace("\\", "/")).suffix.lower()
    return suffix


def allowed_extensions(provider: str | None) -> frozenset[str]:
    key = normalize_provider(provider)
    return _PROVIDER_EXTENSIONS.get(key, frozenset())


def is_path_allowed(provider: str | None, path: str | Path) -> bool:
    key = normalize_provider(provider)
    if key not in _PROVIDER_EXTENSIONS:
        return False
    ext = extension_of(path)
    if not ext:
        return False
    return ext in _PROVIDER_EXTENSIONS[key]


def reject_reason(provider: str | None, path: str | Path) -> str:
    key = normalize_provider(provider)
    ext = extension_of(path) or "(无扩展名)"
    if key == "local_fts":
        return (
            f"{path}: local_fts 只接受文本 {sorted(LOCAL_FTS_EXTENSIONS)}，"
            f"当前是 {ext}"
        )
    if key == "notebooklm":
        return (
            f"{path}: notebooklm（Gemini Notebook）不接受扩展名 {ext}；"
            f"允许文档/图片/音视频见 format_policy.NOTEBOOKLM_EXTENSIONS"
        )
    return f"{path}: 未知 knowledge.provider={provider!r}，无法判定格式"


def partition_paths(
    provider: str | None,
    paths: Iterable[str],
) -> dict[str, Any]:
    """Split paths into allowed vs rejected for the active provider."""
    allowed: list[str] = []
    rejected: list[dict[str, str]] = []
    for raw in paths:
        path = str(raw)
        if is_path_allowed(provider, path):
            allowed.append(path)
        else:
            rejected.append({"path": path, "reason": reject_reason(provider, path)})
    return {
        "provider": normalize_provider(provider),
        "allowed_paths": allowed,
        "rejected": rejected,
        "allowed_count": len(allowed),
        "rejected_count": len(rejected),
        "allowed_extensions": sorted(allowed_extensions(provider)),
    }


def filter_documents_for_provider(
    provider: str | None,
    documents: Iterable[Any],
) -> dict[str, Any]:
    """Filter corpus documents; keep objects that expose ``.path``."""
    docs = list(documents)
    allowed_docs: list[Any] = []
    rejected: list[dict[str, str]] = []
    for doc in docs:
        path = str(getattr(doc, "path", "") or "")
        if is_path_allowed(provider, path):
            allowed_docs.append(doc)
        else:
            rejected.append({"path": path, "reason": reject_reason(provider, path)})
    return {
        "provider": normalize_provider(provider),
        "documents": allowed_docs,
        "rejected": rejected,
        "allowed_count": len(allowed_docs),
        "rejected_count": len(rejected),
        "allowed_extensions": sorted(allowed_extensions(provider)),
    }


def apply_to_desired_corpus(provider: str | None, corpus: Any) -> tuple[Any, dict[str, Any]]:
    """Return a corpus copy with unsupported paths removed + filter report.

    Does not mutate the input corpus. Adds ``format_skipped: …`` warnings.
    """
    report = filter_documents_for_provider(provider, list(corpus.documents))
    warnings = list(getattr(corpus, "warnings", None) or [])
    for row in report["rejected"]:
        warnings.append(f"format_skipped: {row['reason']}")
    # Late import avoids circular type coupling at module import time.
    from vibe_control.knowledge.corpus import DesiredCorpus

    narrowed = DesiredCorpus(
        project_id=corpus.project_id,
        documents=list(report["documents"]),
        source_count=len(report["documents"]),
        warnings=warnings,
        notebook_alias=getattr(corpus, "notebook_alias", None),
        selector_summary=dict(getattr(corpus, "selector_summary", None) or {}),
    )
    return narrowed, report
