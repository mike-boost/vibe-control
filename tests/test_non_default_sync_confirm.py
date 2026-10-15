"""Non-default notebook sync --apply confirm gate."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from vibe_control.knowledge.notebooks import resolve_default_alias
from vibe_control.knowledge.remote_ops import cmd_knowledge_sync


def _write_multi_notebook_repo(tmp_path: Path) -> Path:
    (tmp_path / "docs" / "project").mkdir(parents=True)
    (tmp_path / ".config").mkdir()
    (tmp_path / "docs" / "project" / "spec-registry.yml").write_text(
        "- id: only\n  status: active\n  path: docs/a.md\n  title: A\n",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "a.md").write_text("# A", encoding="utf-8")
    cfg = {
        "project": {"id": "gate-demo", "name": "Gate"},
        "knowledge": {
            "provider": "notebooklm",
            "fallback_provider": "repo",
            "max_sources": 50,
            "warn_sources": 40,
            "authoritative_statuses": ["active"],
            "include_extra": [],
            "exclude_globs": [],
            "notebooks": {
                "default_alias": "main",
                "allow_list": [
                    {
                        "alias": "main",
                        "ref_env": "NOTEBOOKLM_NOTEBOOK_MAIN",
                        "allowed_operations": ["sync", "status", "query"],
                    },
                    {
                        "alias": "side",
                        "ref_env": "NOTEBOOKLM_NOTEBOOK_SIDE",
                        "path_prefixes": ["docs/"],
                        "allowed_operations": ["sync", "status", "query"],
                    },
                ],
            },
        },
        "specs": {
            "registry": "docs/project/spec-registry.yml",
            "required_fields": ["id", "status", "path"],
        },
        "tasks": {"provider": "beads"},
    }
    (tmp_path / ".config" / "vibe-control.yaml").write_text(
        yaml.safe_dump(cfg), encoding="utf-8"
    )
    (tmp_path / ".config" / ".env").write_text(
        "NOTEBOOKLM_NOTEBOOK_MAIN=nb-main\nNOTEBOOKLM_NOTEBOOK_SIDE=nb-side\n",
        encoding="utf-8",
    )
    return tmp_path


def test_non_default_apply_blocked_without_confirm(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = _write_multi_notebook_repo(tmp_path)
    monkeypatch.chdir(root)

    # Avoid real provider: dry-run path not used; apply should fail before provider work
    # if confirm missing. Still may touch provider after gate — gate must fire first.
    args = SimpleNamespace(
        dry_run=False,
        apply=True,
        notebook="side",
        confirm_non_default_sync=False,
        continue_on_item_error=False,
        batch_size=None,
        wait_mode=None,
        ingest_path=None,
        upload_concurrency=None,
        config=None,
    )
    out = cmd_knowledge_sync(root, args)
    assert out.get("ok") is False
    assert (out.get("error") or {}).get("code") == "NON_DEFAULT_NOTEBOOK_APPLY_REQUIRES_CONFIRM"
    # Blocked apply: intent true, no completed effects.
    assert out.get("mutation_intent") is True
    assert out.get("mutation_performed") is False
    assert out.get("mutation") is False
    assert out.get("effects") == []


def test_default_alias_helper(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = _write_multi_notebook_repo(tmp_path)
    monkeypatch.chdir(root)
    from vibe_control.config import load_config

    cfg = load_config(root)
    assert resolve_default_alias(cfg) == "main"
