"""CLI envelopes for multi-notebook alias resolution."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from vibe_control.cli import main


def _multi_repo(tmp_path: Path) -> None:
    (tmp_path / "docs" / "project").mkdir(parents=True)
    (tmp_path / ".config").mkdir()
    (tmp_path / "docs" / "project" / "spec-registry.yml").write_text(
        "- id: only\n  status: active\n  path: docs/a.md\n  title: A\n",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "a.md").write_text("# A", encoding="utf-8")
    cfg = {
        "project": {"id": "cli-multi", "name": "CLI Multi"},
        "components": {
            "knowledge": {"enabled": True},
            "task": {"enabled": False},
        },
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
                        "allowed_operations": ["inventory", "status", "query"],
                    },
                    {
                        "alias": "side",
                        "ref_env": "NOTEBOOKLM_NOTEBOOK_SIDE",
                        "path_prefixes": ["docs/"],
                        "allowed_operations": ["inventory", "status", "query"],
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


def test_inventory_multi_notebook_omit_alias_fails(tmp_path, monkeypatch, capsys):
    _multi_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    code = main(["knowledge", "inventory", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code != 0
    assert payload.get("ok") is False
    assert (payload.get("error") or {}).get("code") == "NOTEBOOK_ALIAS_REQUIRED"


def test_inventory_multi_notebook_with_alias_ok(tmp_path, monkeypatch, capsys):
    _multi_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    code = main(["knowledge", "inventory", "--notebook", "side", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload.get("ok") is True
    data = payload.get("data") or {}
    assert data.get("notebook_alias") == "side"
    assert "path_prefixes" in (data.get("selector_summary") or {})
