"""Desired knowledge corpus generation from config + registry."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from vibe_control.config import ControlConfig
from vibe_control.knowledge.source_quota import DEFAULT_MAX_SOURCES, DEFAULT_WARN_SOURCES
from vibe_control.spec.registry import SpecEntry, load_registry, validate_entries


class CorpusError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


@dataclass
class CorpusDocument:
    doc_id: str
    path: str
    title: str
    status: str
    kind: str
    source_policy: str
    source_title: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "path": self.path,
            "title": self.title,
            "status": self.status,
            "kind": self.kind,
            "source_policy": self.source_policy,
            "source_title": self.source_title,
        }


@dataclass
class DesiredCorpus:
    project_id: str
    documents: list[CorpusDocument] = field(default_factory=list)
    source_count: int = 0
    warnings: list[str] = field(default_factory=list)
    notebook_alias: str | None = None
    selector_summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "project_id": self.project_id,
            "documents": [d.to_dict() for d in self.documents],
            "source_count": self.source_count,
            "warnings": list(self.warnings),
        }
        if self.notebook_alias is not None:
            out["notebook_alias"] = self.notebook_alias
        if self.selector_summary:
            out["selector_summary"] = dict(self.selector_summary)
        return out


def path_matches_glob(path: str, pattern: str) -> bool:
    """Match POSIX-ish relative paths against gitignore-like globs with `**`."""
    posix = path.replace("\\", "/").lstrip("./")
    normalized_pattern = pattern.replace("\\", "/")

    try:
        if PurePosixPath(posix).match(normalized_pattern):
            return True
    except ValueError:
        pass

    # PurePosixPath.match is anchored to the full path; also try as recursive suffix.
    if normalized_pattern.startswith("**/"):
        suffix = normalized_pattern[3:]
        try:
            if PurePosixPath(posix).match(suffix):
                return True
            if PurePosixPath(posix).match("**/" + suffix):
                return True
        except ValueError:
            pass
        parts = posix.split("/")
        for i in range(len(parts)):
            candidate = "/".join(parts[i:])
            try:
                if PurePosixPath(candidate).match(suffix) or PurePosixPath(candidate).match(
                    "**/" + suffix
                ):
                    return True
            except ValueError:
                continue

    return False


def matches_any_exclude(path: str, exclude_globs: list[str]) -> bool:
    return any(path_matches_glob(path, pattern) for pattern in exclude_globs)


def format_source_title(
    template: str,
    *,
    project_id: str,
    doc_id: str,
    title: str,
) -> str:
    return template.format(project_id=project_id, doc_id=doc_id, title=title)


def _doc_from_spec(
    entry: SpecEntry,
    *,
    project_id: str,
    title_template: str,
) -> CorpusDocument:
    title = entry.title or entry.id
    path = entry.path or ""
    return CorpusDocument(
        doc_id=entry.id,
        path=path,
        title=title,
        status=entry.status or "active",
        kind="spec",
        source_policy="must_include",
        source_title=format_source_title(
            title_template,
            project_id=project_id,
            doc_id=entry.id,
            title=title,
        ),
    )


def _doc_from_extra(
    path: str,
    *,
    project_id: str,
    title_template: str,
) -> CorpusDocument:
    doc_id = Path(path).stem
    title = Path(path).name
    return CorpusDocument(
        doc_id=doc_id,
        path=path,
        title=title,
        status="curated",
        kind="extra",
        source_policy="include_extra",
        source_title=format_source_title(
            title_template,
            project_id=project_id,
            doc_id=doc_id,
            title=title,
        ),
    )


def build_desired_corpus(
    config: ControlConfig,
    *,
    repo_root: Path | None = None,
    registry_entries: list[SpecEntry] | None = None,
    enforce_limits: bool = True,
) -> DesiredCorpus:
    root = repo_root if repo_root is not None else Path.cwd()
    knowledge = config.knowledge
    specs = config.specs
    warnings: list[str] = []

    authoritative = list(knowledge.get("authoritative_statuses") or ["active"])
    required_fields = list(specs.get("required_fields") or ["id", "status", "path"])
    exclude_globs = list(knowledge.get("exclude_globs") or [])
    title_template = str(
        knowledge.get("source_title_template")
        or "[vibe:{project_id}:{doc_id}] {title}"
    )
    max_sources = int(knowledge.get("max_sources") or DEFAULT_MAX_SOURCES)
    warn_sources = int(knowledge.get("warn_sources") or DEFAULT_WARN_SOURCES)

    if registry_entries is None:
        registry_rel = specs.get("registry") or knowledge.get("include_from")
        if not registry_rel:
            raise CorpusError(
                "REGISTRY_PATH_MISSING",
                "No specs.registry (or knowledge.include_from) configured",
            )
        registry_path = root / str(registry_rel)
        parsed = load_registry(registry_path)
        warnings.extend(parsed.warnings)
        if parsed.errors and not parsed.entries:
            if any("not found" in e for e in parsed.errors):
                raise CorpusError(
                    "REGISTRY_NOT_FOUND",
                    parsed.errors[0],
                    {"path": registry_path.as_posix(), "errors": parsed.errors},
                )
            raise CorpusError(
                "REGISTRY_INVALID",
                "Registry could not be parsed into entries",
                {"path": registry_path.as_posix(), "errors": parsed.errors},
            )
        warnings.extend(parsed.errors)
        entries = parsed.entries
    else:
        entries = registry_entries

    selected, val_warnings, val_errors = validate_entries(
        entries,
        required_fields=required_fields,
        authoritative_statuses=authoritative,
    )
    warnings.extend(val_warnings)
    warnings.extend(val_errors)

    documents: list[CorpusDocument] = []
    seen_paths: set[str] = set()

    for entry in selected:
        if not entry.path:
            continue
        if matches_any_exclude(entry.path, exclude_globs):
            warnings.append(f"excluded by glob: {entry.path}")
            continue
        doc = _doc_from_spec(
            entry,
            project_id=config.project_id,
            title_template=title_template,
        )
        documents.append(doc)
        seen_paths.add(entry.path.replace("\\", "/"))
        file_path = root / entry.path
        if not file_path.is_file():
            warnings.append(f"missing file: {entry.path}")

    for extra in knowledge.get("include_extra") or []:
        extra_path = str(extra)
        if matches_any_exclude(extra_path, exclude_globs):
            warnings.append(f"excluded extra by glob: {extra_path}")
            continue
        normalized = extra_path.replace("\\", "/")
        if normalized in seen_paths:
            continue
        doc = _doc_from_extra(
            extra_path,
            project_id=config.project_id,
            title_template=title_template,
        )
        documents.append(doc)
        seen_paths.add(normalized)
        if not (root / extra_path).is_file():
            warnings.append(f"missing file: {extra_path}")

    source_count = len(documents)
    warnings_out = list(warnings)
    if enforce_limits:
        _enforce_source_limits(
            documents,
            max_sources=max_sources,
            warn_sources=warn_sources,
            warnings=warnings_out,
        )

    return DesiredCorpus(
        project_id=config.project_id,
        documents=documents,
        source_count=source_count,
        warnings=warnings_out,
    )


def _path_matches_any_prefix(path: str, prefixes: list[str]) -> bool:
    normalized = path.replace("\\", "/").lstrip("./")
    for raw in prefixes:
        prefix = str(raw).replace("\\", "/").lstrip("./")
        if not prefix:
            continue
        if not prefix.endswith("/"):
            # Allow both "docs/specs" and "docs/specs/" as directory prefixes.
            if normalized == prefix or normalized.startswith(prefix + "/"):
                return True
            continue
        if normalized.startswith(prefix):
            return True
    return False


def _selector_fields(entry: dict[str, Any] | None) -> dict[str, Any]:
    if not entry:
        return {
            "corpus_mode": "inherit",
            "path_prefixes": [],
            "include_extra": [],
            "exclude_globs": [],
        }
    mode = str(entry.get("corpus_mode") or "inherit").strip().lower() or "inherit"
    return {
        "corpus_mode": mode,
        "path_prefixes": [str(x) for x in (entry.get("path_prefixes") or [])],
        "include_extra": [str(x) for x in (entry.get("include_extra") or [])],
        "exclude_globs": [str(x) for x in (entry.get("exclude_globs") or [])],
    }


def _find_allow_list_entry(config: ControlConfig, alias: str) -> dict[str, Any] | None:
    notebooks = config.knowledge.get("notebooks")
    if not isinstance(notebooks, dict):
        return None
    for item in notebooks.get("allow_list") or []:
        if isinstance(item, dict) and str(item.get("alias")) == alias:
            return item
    return None


def _enforce_source_limits(
    documents: list[CorpusDocument],
    *,
    max_sources: int,
    warn_sources: int,
    warnings: list[str],
) -> None:
    source_count = len(documents)
    if source_count >= max_sources:
        raise CorpusError(
            "SOURCE_LIMIT_EXCEEDED",
            f"Desired corpus has {source_count} sources; max_sources={max_sources}",
            {
                "source_count": source_count,
                "max_sources": max_sources,
                "warn_sources": warn_sources,
            },
        )
    if source_count >= warn_sources:
        warnings.append(
            f"source count {source_count} >= warn_sources ({warn_sources})"
        )


def resolve_desired_corpus(
    config: ControlConfig,
    *,
    notebook_alias: str | None = None,
    repo_root: Path | None = None,
    registry_entries: list[SpecEntry] | None = None,
) -> DesiredCorpus:
    """Resolve desired corpus, optionally scoped to a notebook allow_list entry.

    When ``notebook_alias`` is None or notebooks are not configured, behavior
    matches :func:`build_desired_corpus` (global selector).
    """
    root = repo_root if repo_root is not None else Path.cwd()
    knowledge = config.knowledge
    title_template = str(
        knowledge.get("source_title_template")
        or "[vibe:{project_id}:{doc_id}] {title}"
    )
    max_sources = int(knowledge.get("max_sources") or DEFAULT_MAX_SOURCES)
    warn_sources = int(knowledge.get("warn_sources") or DEFAULT_WARN_SOURCES)

    entry = _find_allow_list_entry(config, notebook_alias) if notebook_alias else None
    selector = _selector_fields(entry if notebook_alias else None)
    summary = {
        "corpus_mode": selector["corpus_mode"],
        "path_prefixes": list(selector["path_prefixes"]),
        "include_extra": list(selector["include_extra"]),
        "exclude_globs": list(selector["exclude_globs"]),
    }

    if notebook_alias is None or entry is None:
        corpus = build_desired_corpus(
            config, repo_root=root, registry_entries=registry_entries
        )
        if notebook_alias is not None:
            corpus.notebook_alias = notebook_alias
            corpus.selector_summary = summary
        return corpus

    mode = selector["corpus_mode"]
    if mode not in ("inherit", "replace"):
        raise CorpusError(
            "INVALID_CORPUS_MODE",
            f"Unsupported corpus_mode {mode!r}; use inherit or replace",
            {"notebook_alias": notebook_alias, "corpus_mode": mode},
        )

    warnings: list[str] = []
    documents: list[CorpusDocument] = []
    seen_paths: set[str] = set()

    if mode == "inherit":
        base = build_desired_corpus(
            config,
            repo_root=root,
            registry_entries=registry_entries,
            enforce_limits=False,
        )
        warnings.extend(base.warnings)
        for doc in base.documents:
            documents.append(doc)
            seen_paths.add(doc.path.replace("\\", "/"))
    else:
        # replace: only entry.include_extra (no global registry / global extras)
        pass

    for extra_path in selector["include_extra"]:
        if matches_any_exclude(extra_path, selector["exclude_globs"]):
            warnings.append(f"excluded entry extra by glob: {extra_path}")
            continue
        normalized = extra_path.replace("\\", "/")
        if normalized in seen_paths:
            continue
        doc = _doc_from_extra(
            extra_path,
            project_id=config.project_id,
            title_template=title_template,
        )
        documents.append(doc)
        seen_paths.add(normalized)
        if not (root / extra_path).is_file():
            warnings.append(f"missing file: {extra_path}")

    if selector["exclude_globs"]:
        kept: list[CorpusDocument] = []
        for doc in documents:
            if matches_any_exclude(doc.path, selector["exclude_globs"]):
                warnings.append(f"excluded by entry glob: {doc.path}")
                continue
            kept.append(doc)
        documents = kept

    if selector["path_prefixes"]:
        kept = []
        for doc in documents:
            if _path_matches_any_prefix(doc.path, selector["path_prefixes"]):
                kept.append(doc)
            else:
                warnings.append(f"filtered by path_prefixes: {doc.path}")
        documents = kept

    # Drop global "source count >= warn" noise from base when we re-check below.
    warnings = [w for w in warnings if not w.startswith("source count ")]
    _enforce_source_limits(
        documents,
        max_sources=max_sources,
        warn_sources=warn_sources,
        warnings=warnings,
    )

    return DesiredCorpus(
        project_id=config.project_id,
        documents=documents,
        source_count=len(documents),
        warnings=warnings,
        notebook_alias=notebook_alias,
        selector_summary=summary,
    )


def sync_scope_for_corpus(
    notebook_alias: str | None,
    selector_summary: dict[str, Any] | None = None,
) -> str:
    """Stable sync_scope for snapshots.

    Unscoped / inherit-with-empty-knobs keeps legacy ``ssot_files`` so existing
    receipts do not false-drift. Custom selectors use ``ssot_files:<alias>``.
    """
    summary = selector_summary or {}
    if not notebook_alias:
        return "ssot_files"
    mode = str(summary.get("corpus_mode") or "inherit").strip().lower() or "inherit"
    has_knobs = bool(
        summary.get("path_prefixes")
        or summary.get("include_extra")
        or summary.get("exclude_globs")
        or mode == "replace"
    )
    if not has_knobs:
        return "ssot_files"
    return f"ssot_files:{notebook_alias}"


def resolve_corpus_for_target(
    config: ControlConfig,
    *,
    notebook_alias: str | None,
    repo_root: Path | None = None,
    registry_entries: list[SpecEntry] | None = None,
) -> tuple[DesiredCorpus, str]:
    corpus = resolve_desired_corpus(
        config,
        notebook_alias=notebook_alias,
        repo_root=repo_root,
        registry_entries=registry_entries,
    )
    scope = sync_scope_for_corpus(
        corpus.notebook_alias or notebook_alias,
        corpus.selector_summary,
    )
    return corpus, scope

