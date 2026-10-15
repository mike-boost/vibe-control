"""Hardening tests for inventory exclude_globs."""

from __future__ import annotations

from pathlib import Path

from vibe_control.knowledge.corpus import build_desired_corpus, path_matches_glob
from vibe_control.spec.registry import SpecEntry
from helpers import control_config_from_dict, minimal_config_dict, write_doc


EXCLUDED_PATHS = [
    "docs/program/plans/example.md",
    "docs/phases/phase3/plans/example.md",
    "docs/superpowers/plans/example.md",
    "docs/dashboard/example.md",
    "some/archive/example.md",
]


def test_path_matches_template_exclude_globs():
    patterns = minimal_config_dict()["knowledge"]["exclude_globs"]
    for path in EXCLUDED_PATHS:
        assert any(path_matches_glob(path, pat) for pat in patterns), path


def test_corpus_excludes_template_glob_paths(tmp_path: Path):
    raw = minimal_config_dict(include_extra=[])
    config = control_config_from_dict(raw)
    entries = []
    for idx, path in enumerate(EXCLUDED_PATHS):
        write_doc(tmp_path, path, f"content {idx}\n")
        entries.append(
            SpecEntry(
                id=f"ex-{idx}",
                status="active",
                path=path,
                title=f"Ex {idx}",
                raw={"id": f"ex-{idx}", "status": "active", "path": path},
            )
        )
    # one included control doc
    write_doc(tmp_path, "docs/keep.md", "keep me\n")
    entries.append(
        SpecEntry(
            id="keep",
            status="active",
            path="docs/keep.md",
            title="Keep",
            raw={"id": "keep", "status": "active", "path": "docs/keep.md"},
        )
    )

    corpus = build_desired_corpus(config, repo_root=tmp_path, registry_entries=entries)
    paths = {d.path for d in corpus.documents}
    assert paths == {"docs/keep.md"}
    for excluded in EXCLUDED_PATHS:
        assert excluded not in paths
