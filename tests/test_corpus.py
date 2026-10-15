"""Tests for desired corpus generation."""

from pathlib import Path

import pytest
import yaml

from vibe_control.config import ControlConfig
from vibe_control.knowledge.corpus import (
    CorpusError,
    build_desired_corpus,
    format_source_title,
)
from vibe_control.spec.registry import SpecEntry


def _config(
    *,
    max_sources: int = 100,
    warn_sources: int = 80,
    include_extra: list[str] | None = None,
    exclude_globs: list[str] | None = None,
) -> ControlConfig:
    raw = {
        "project": {"id": "migration-harness", "name": "Migration-Harness"},
        "knowledge": {
            "provider": "notebooklm",
            "fallback_provider": "repo",
            "max_sources": max_sources,
            "warn_sources": warn_sources,
            "authoritative_statuses": ["active"],
            "include_extra": include_extra or [],
            "exclude_globs": exclude_globs or [],
            "source_title_template": "[vibe:{project_id}:{doc_id}] {title}",
        },
        "specs": {
            "registry": "docs/project/spec-registry.yml",
            "required_fields": ["id", "status", "path"],
        },
        "tasks": {"provider": "beads"},
    }
    return ControlConfig(
        raw=raw,
        path=Path(".vibe/control.yaml"),
        project_id="migration-harness",
        knowledge=raw["knowledge"],
        specs=raw["specs"],
        tasks=raw["tasks"],
    )


def test_source_title_template():
    title = format_source_title(
        "[vibe:{project_id}:{doc_id}] {title}",
        project_id="migration-harness",
        doc_id="spec-a",
        title="Alpha",
    )
    assert title == "[vibe:migration-harness:spec-a] Alpha"


def test_includes_active_specs_excludes_non_authoritative(tmp_path: Path):
    entries = [
        SpecEntry(
            id="spec-a",
            status="active",
            path="docs/a.md",
            title="Alpha",
            raw={"id": "spec-a", "status": "active", "path": "docs/a.md", "title": "Alpha"},
        ),
        SpecEntry(
            id="spec-b",
            status="draft",
            path="docs/b.md",
            title="Beta",
            raw={"id": "spec-b", "status": "draft", "path": "docs/b.md", "title": "Beta"},
        ),
    ]
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("# A", encoding="utf-8")
    (tmp_path / "docs" / "b.md").write_text("# B", encoding="utf-8")

    corpus = build_desired_corpus(
        _config(),
        repo_root=tmp_path,
        registry_entries=entries,
    )
    assert corpus.source_count == 1
    assert corpus.documents[0].doc_id == "spec-a"
    assert corpus.documents[0].source_title == "[vibe:migration-harness:spec-a] Alpha"


def test_include_extra_and_exclude_globs(tmp_path: Path):
    entries = [
        SpecEntry(
            id="spec-a",
            status="active",
            path="docs/a.md",
            raw={"id": "spec-a", "status": "active", "path": "docs/a.md"},
        ),
        SpecEntry(
            id="archived",
            status="active",
            path="docs/archive/old.md",
            raw={"id": "archived", "status": "active", "path": "docs/archive/old.md"},
        ),
    ]
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.md").write_text("a", encoding="utf-8")
    (docs / "extra.md").write_text("e", encoding="utf-8")
    archive = docs / "archive"
    archive.mkdir()
    (archive / "old.md").write_text("old", encoding="utf-8")

    corpus = build_desired_corpus(
        _config(
            include_extra=["docs/extra.md"],
            exclude_globs=["**/archive/**"],
        ),
        repo_root=tmp_path,
        registry_entries=entries,
    )
    ids = {d.doc_id for d in corpus.documents}
    assert "spec-a" in ids
    assert "extra" in ids
    assert "archived" not in ids


def test_warn_sources_warning(tmp_path: Path):
    entries = [
        SpecEntry(
            id=f"spec-{i}",
            status="active",
            path=f"docs/{i}.md",
            raw={"id": f"spec-{i}", "status": "active", "path": f"docs/{i}.md"},
        )
        for i in range(3)
    ]
    (tmp_path / "docs").mkdir()
    for i in range(3):
        (tmp_path / "docs" / f"{i}.md").write_text("x", encoding="utf-8")

    corpus = build_desired_corpus(
        _config(max_sources=10, warn_sources=3),
        repo_root=tmp_path,
        registry_entries=entries,
    )
    assert corpus.source_count == 3
    assert any("warn_sources" in w for w in corpus.warnings)


def test_max_sources_hard_stop(tmp_path: Path):
    entries = [
        SpecEntry(
            id=f"spec-{i}",
            status="active",
            path=f"docs/{i}.md",
            raw={"id": f"spec-{i}", "status": "active", "path": f"docs/{i}.md"},
        )
        for i in range(3)
    ]
    (tmp_path / "docs").mkdir()
    for i in range(3):
        (tmp_path / "docs" / f"{i}.md").write_text("x", encoding="utf-8")

    with pytest.raises(CorpusError) as exc:
        build_desired_corpus(
            _config(max_sources=3, warn_sources=2),
            repo_root=tmp_path,
            registry_entries=entries,
        )
    assert exc.value.code == "SOURCE_LIMIT_EXCEEDED"


def test_registry_file_missing_is_graceful(tmp_path: Path):
    raw = _config().raw
    config_dir = tmp_path / ".vibe"
    config_dir.mkdir()
    (config_dir / "control.yaml").write_text(yaml.safe_dump(raw), encoding="utf-8")
    config = ControlConfig(
        raw=raw,
        path=config_dir / "control.yaml",
        project_id="migration-harness",
        knowledge=raw["knowledge"],
        specs=raw["specs"],
        tasks=raw["tasks"],
    )
    with pytest.raises(CorpusError) as exc:
        build_desired_corpus(config, repo_root=tmp_path)
    assert exc.value.code == "REGISTRY_NOT_FOUND"
