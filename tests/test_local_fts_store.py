"""Tests for local_fts store rebuild/query (trigram + LIKE + fingerprints)."""

from __future__ import annotations

from pathlib import Path

import yaml

from vibe_control.config import load_config
from vibe_control.knowledge.local_fts.provider import LocalFtsProvider
from vibe_control.knowledge.local_fts.store import probe_sqlite_fts5


def _setup_repo(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    home.mkdir()
    (repo / "docs").mkdir(parents=True)
    (repo / ".config").mkdir(parents=True)
    (repo / "docs" / "spec.md").write_text(
        "# Spec\n"
        "\n"
        "## Approval Matrix\n"
        "\n"
        "需要 owner approval 才能 git push。\n"
        "\n"
        "## 任务缓存\n"
        "\n"
        "task_cache_current 必须为 true。\n",
        encoding="utf-8",
    )
    (repo / "docs" / "spec-registry.yml").write_text(
        yaml.safe_dump(
            [
                {
                    "id": "spec",
                    "status": "active",
                    "path": "docs/spec.md",
                    "title": "Spec",
                }
            ]
        ),
        encoding="utf-8",
    )
    (repo / ".config" / "vibe-control.yaml").write_text(
        yaml.safe_dump(
            {
                "project": {"id": "local-fts-test", "name": "local-fts-test"},
                "components": {"knowledge": {"enabled": True}, "task": {"enabled": False}},
                "knowledge": {
                    "provider": "local_fts",
                    "fallback_provider": "repo",
                    "max_sources": 20,
                    "warn_sources": 15,
                    "authoritative_statuses": ["active"],
                    "include_from": "docs/spec-registry.yml",
                    "include_extra": [],
                    "exclude_globs": [],
                    "local_fts": {"top_k": 8},
                },
                "specs": {
                    "registry": "docs/spec-registry.yml",
                    "required_fields": ["id", "status", "path"],
                },
                "tasks": {"provider": "fake"},
            }
        ),
        encoding="utf-8",
    )
    return repo, home


def test_sqlite_probe_ok():
    probe = probe_sqlite_fts5()
    assert probe["ok"] is True
    assert probe["trigram_ok"] is True


def test_rebuild_and_query_english_and_cjk(tmp_path: Path):
    repo, home = _setup_repo(tmp_path)
    cfg = load_config(repo)
    provider = LocalFtsProvider(home=home)

    dry = provider.sync(cfg, repo_root=repo, apply=False)
    assert dry["mutation"] is False
    assert dry["plan"]["ops"][0]["op"] == "rebuild_index"

    applied = provider.sync(cfg, repo_root=repo, apply=True)
    assert applied["ok"] is True
    assert applied["sync_state"] == "synced"
    assert applied["provider_ask_clean"] is True

    status = provider.status(cfg, repo_root=repo)
    assert status["sync_state"] == "synced"

    q = provider.query(cfg, repo_root=repo, question="owner approval push")
    assert q["provider_ask_clean"] is True
    assert q["sources"]
    hit = q["sources"][0]
    assert hit["path"] == "docs/spec.md"
    assert hit["line_start"] >= 1
    assert hit["line_end"] >= hit["line_start"]

    q2 = provider.query(cfg, repo_root=repo, question="任务")
    assert q2["sources"], "expected LIKE fallback hit for 2-char CJK"


def test_drift_after_content_change(tmp_path: Path):
    repo, home = _setup_repo(tmp_path)
    cfg = load_config(repo)
    provider = LocalFtsProvider(home=home)
    provider.sync(cfg, repo_root=repo, apply=True)
    assert provider.status(cfg, repo_root=repo)["sync_state"] == "synced"

    (repo / "docs" / "spec.md").write_text("# Spec\n\nchanged\n", encoding="utf-8")
    status = provider.status(cfg, repo_root=repo)
    assert status["sync_state"] == "drift"
    dirty = provider.query(cfg, repo_root=repo, question="changed")
    assert dirty["mode"] == "degraded"
    assert dirty["sources"] == []
