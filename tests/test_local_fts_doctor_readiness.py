"""Doctor, product_readiness probe, and describe guidance for local_fts."""

from __future__ import annotations

from pathlib import Path

import yaml

from vibe_control.config import load_config, validate_config, validate_config_dict
from vibe_control.describe import build_describe
from vibe_control.knowledge.doctor import build_knowledge_doctor
from vibe_control.knowledge.local_fts.provider import LocalFtsProvider
from vibe_control.product_readiness import probe_knowledge_readiness


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
        "需要 owner approval 才能 git push。\n",
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


def _progress_envelope() -> dict:
    return {
        "ok": True,
        "command": "vibe progress",
        "project_id": "local-fts-test",
        "data": {
            "product_ready": False,
            "config_ok": True,
            "provider_sync_required": True,
            "sync_state": "drift",
            "provider_ask_clean": False,
            "task_cache_current": True,
            "blocked_reasons": [],
            "knowledge_enabled": True,
            "task_enabled": False,
        },
        "warnings": [],
        "next_actions": [],
    }


def test_doctor_local_fts_no_index_not_ready(tmp_path: Path, monkeypatch):
    repo, home = _setup_repo(tmp_path)
    monkeypatch.setenv("HOME", str(home))

    result = build_knowledge_doctor(repo_root=repo)
    data = result["data"]

    assert result["ok"] is False
    assert data["ready"] is False
    assert data["provider"]["name"] == "local_fts"
    assert "SYNC_NOT_CLEAN" in data["codes"]
    assert data["auth"]["auth_state"] == "not_applicable"
    assert data["provider"]["binary"]["auth_state"] == "not_applicable"
    assert data["local_fts"]["sqlite"]["ok"] is True
    assert data["local_fts"]["index_exists"] is False
    assert data["sync"]["sync_state"] == "drift"
    assert data["sync"]["synced"] is False


def test_doctor_local_fts_ready_after_sync(tmp_path: Path, monkeypatch):
    repo, home = _setup_repo(tmp_path)
    monkeypatch.setenv("HOME", str(home))
    cfg = load_config(repo)

    provider = LocalFtsProvider()
    applied = provider.sync(cfg, repo_root=repo, apply=True)
    assert applied["ok"] is True
    assert applied["sync_state"] == "synced"

    result = build_knowledge_doctor(repo_root=repo)
    data = result["data"]

    assert result["ok"] is True
    assert data["ready"] is True
    assert "SYNC_NOT_CLEAN" not in data["codes"]
    assert data["sync"]["sync_state"] == "synced"
    assert data["sync"]["synced"] is True
    assert data["local_fts"]["index_exists"] is True
    assert data["auth"]["auth_state"] == "not_applicable"


def test_probe_knowledge_readiness_local_fts_before_and_after_rebuild(
    tmp_path: Path, monkeypatch
):
    repo, home = _setup_repo(tmp_path)
    monkeypatch.setenv("HOME", str(home))
    cfg = load_config(repo)

    before = probe_knowledge_readiness(repo)
    assert before["sync_state"] == "drift"
    assert before["available"] is True
    assert before["target_ok"] is True
    assert before["required_updates_count"] >= 1

    LocalFtsProvider().sync(cfg, repo_root=repo, apply=True)

    after = probe_knowledge_readiness(repo)
    assert after["sync_state"] == "synced"
    assert after["available"] is True
    assert after["target_ok"] is True
    assert after["required_updates_count"] == 0


def test_build_describe_includes_local_fts_guidance(tmp_path: Path):
    repo, _home = _setup_repo(tmp_path)

    result = build_describe(repo_root=repo, progress_envelope=_progress_envelope())
    data = result["data"]

    guidance = data["knowledge_provider_selection_guidance"]
    assert isinstance(guidance, list)
    assert len(guidance) >= 3
    joined = "\n".join(guidance)
    assert "local_fts" in joined
    assert "notebooklm" in joined

    assert "local_fts" in data["authority"]
    assert "local_fts" in data["authority_map"]
    assert "SQLite FTS5" in data["authority"]["local_fts"]


def test_config_rejects_unknown_knowledge_provider(tmp_path: Path):
    repo, _home = _setup_repo(tmp_path)
    cfg_path = repo / ".config" / "vibe-control.yaml"
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    raw["knowledge"]["provider"] = "meilisearch"
    cfg_path.write_text(yaml.safe_dump(raw), encoding="utf-8")

    errors = validate_config_dict(raw)
    assert any("knowledge.provider" in e for e in errors)

    config = load_config(repo)
    assert any("knowledge.provider" in e for e in validate_config(config))
