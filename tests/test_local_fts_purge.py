"""local_fts fts-purge: orphan/tmp cleanup + --all confirm gate."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from vibe_control.cli import main
from vibe_control.config import load_config
from vibe_control.knowledge.local_fts.fingerprint import scope_key_for_fs
from vibe_control.knowledge.local_fts.provider import LocalFtsProvider
from vibe_control.knowledge.local_fts.purge import (
    build_purge_plan,
    local_fts_root,
    run_fts_purge,
)
from vibe_control.knowledge.corpus import resolve_corpus_for_target


def _setup_repo(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    home.mkdir()
    (repo / "docs").mkdir(parents=True)
    (repo / ".config").mkdir(parents=True)
    (repo / "docs" / "spec.md").write_text(
        "# Spec\n\nApproval Matrix requires owner push approval.\n",
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
                "project": {"id": "local-fts-purge", "name": "local-fts-purge"},
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


def test_purge_orphans_and_tmp_dry_run_and_apply(tmp_path: Path, monkeypatch):
    repo, home = _setup_repo(tmp_path)
    monkeypatch.setenv("HOME", str(home))

    cfg = load_config(repo)
    LocalFtsProvider(home=home).sync(cfg, repo_root=repo, apply=True)

    _corpus, scope = resolve_corpus_for_target(cfg, notebook_alias=None, repo_root=repo)
    active_key = scope_key_for_fs(scope)
    root = local_fts_root(cfg.project_id, home=home)
    orphan = root / "orphan_scope"
    orphan.mkdir(parents=True)
    (orphan / "index.sqlite").write_bytes(b"x" * 32)
    tmp_file = root / "leftover.sqlite.tmp"
    tmp_file.write_bytes(b"tmp")
    in_scope_tmp = root / active_key / "index.sqlite.tmp"
    in_scope_tmp.write_bytes(b"tmp2")

    plan = build_purge_plan(cfg, repo_root=repo, home=home)
    kinds = {e.kind for e in plan.entries}
    assert "active" in kinds
    assert "orphan" in kinds
    assert "tmp" in kinds

    dry = run_fts_purge(repo_root=repo, apply=False, home=home)
    assert dry["ok"] is True
    assert dry["mutation"] is False
    assert (dry["data"]["plan"]["total_orphan_bytes"] or 0) > 0

    applied = run_fts_purge(repo_root=repo, apply=True, home=home)
    assert applied["ok"] is True
    assert applied["mutation"] is True
    assert not orphan.exists()
    assert not tmp_file.exists()
    assert not in_scope_tmp.exists()
    assert (root / active_key / "index.sqlite").exists()


def test_purge_all_requires_confirm(tmp_path: Path, monkeypatch):
    repo, home = _setup_repo(tmp_path)
    monkeypatch.setenv("HOME", str(home))
    cfg = load_config(repo)
    LocalFtsProvider(home=home).sync(cfg, repo_root=repo, apply=True)

    blocked = run_fts_purge(
        repo_root=repo, apply=True, purge_all=True, confirm_all=False, home=home
    )
    assert blocked["ok"] is False
    assert (blocked.get("error") or {}).get("code") == "FTS_PURGE_ALL_REQUIRES_CONFIRM"
    assert local_fts_root(cfg.project_id, home=home).is_dir()

    wiped = run_fts_purge(
        repo_root=repo, apply=True, purge_all=True, confirm_all=True, home=home
    )
    assert wiped["ok"] is True
    assert not local_fts_root(cfg.project_id, home=home).exists()


def test_fts_purge_cli_and_cleanup_candidates(tmp_path: Path, monkeypatch, capsys):
    repo, home = _setup_repo(tmp_path)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(repo)

    cfg = load_config(repo)
    LocalFtsProvider(home=home).sync(cfg, repo_root=repo, apply=True)
    orphan = local_fts_root(cfg.project_id, home=home) / "gone"
    orphan.mkdir()
    (orphan / "x.sqlite").write_bytes(b"abc")

    code = main(["knowledge", "fts-purge", "--dry-run", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["ok"] is True
    assert payload["data"]["dry_run"] is True

    code = main(["knowledge", "cleanup-candidates", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["data"]["provider"] == "local_fts"
    assert payload["data"]["candidate_count"] >= 1

    code = main(["knowledge", "remote-inventory", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["data"]["applicable"] is False

    code = main(["knowledge", "retry", "--dry-run", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["data"]["retry_equivalent"] == "local_fts_rebuild"
