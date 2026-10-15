"""local_fts multi-notebook corpus isolation + closeout rebuild path."""

from __future__ import annotations

from pathlib import Path

import yaml

from vibe_control.closeout_runner import run_closeout
from vibe_control.config import load_config
from vibe_control.knowledge.local_fts.fingerprint import scope_key_for_fs
from vibe_control.knowledge.local_fts.provider import LocalFtsProvider
from vibe_control.knowledge.local_fts.store import index_path
from vibe_control.knowledge.corpus import resolve_corpus_for_target


def _multi_local_fts_repo(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    home.mkdir()
    (repo / "docs" / "main").mkdir(parents=True)
    (repo / "docs" / "side").mkdir(parents=True)
    (repo / ".config").mkdir(parents=True)
    (repo / "docs" / "main" / "a.md").write_text(
        "# Main only\n\nunique_main_token approval.\n", encoding="utf-8"
    )
    (repo / "docs" / "side" / "b.md").write_text(
        "# Side only\n\nunique_side_token matrix.\n", encoding="utf-8"
    )
    (repo / "docs" / "spec-registry.yml").write_text(
        yaml.safe_dump(
            [
                {
                    "id": "main_doc",
                    "status": "active",
                    "path": "docs/main/a.md",
                    "title": "Main",
                },
                {
                    "id": "side_doc",
                    "status": "active",
                    "path": "docs/side/b.md",
                    "title": "Side",
                },
            ]
        ),
        encoding="utf-8",
    )
    (repo / ".config" / "vibe-control.yaml").write_text(
        yaml.safe_dump(
            {
                "project": {"id": "local-fts-multi", "name": "local-fts-multi"},
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
                    "notebooks": {
                        "default_alias": "main",
                        "allow_list": [
                            {
                                "alias": "main",
                                "ref_env": "NOTEBOOKLM_NOTEBOOK_MAIN",
                                "path_prefixes": ["docs/main/"],
                                "allowed_operations": ["inventory", "status", "query", "sync"],
                            },
                            {
                                "alias": "side",
                                "ref_env": "NOTEBOOKLM_NOTEBOOK_SIDE",
                                "path_prefixes": ["docs/side/"],
                                "allowed_operations": ["inventory", "status", "query", "sync"],
                            },
                        ],
                    },
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


def test_multi_notebook_indexes_are_isolated(tmp_path: Path, monkeypatch):
    repo, home = _multi_local_fts_repo(tmp_path)
    monkeypatch.setenv("HOME", str(home))
    cfg = load_config(repo)
    provider = LocalFtsProvider(home=home)

    provider.sync(cfg, repo_root=repo, apply=True, notebook_alias="main")
    provider.sync(cfg, repo_root=repo, apply=True, notebook_alias="side")

    _c1, scope_main = resolve_corpus_for_target(
        cfg, notebook_alias="main", repo_root=repo
    )
    _c2, scope_side = resolve_corpus_for_target(
        cfg, notebook_alias="side", repo_root=repo
    )
    assert scope_main != scope_side
    path_main = index_path(cfg.project_id, scope_main, home=home)
    path_side = index_path(cfg.project_id, scope_side, home=home)
    assert path_main != path_side
    assert path_main.exists() and path_side.exists()
    assert scope_key_for_fs(scope_main) in str(path_main)
    assert scope_key_for_fs(scope_side) in str(path_side)

    main_hits = provider.query(
        cfg, repo_root=repo, question="unique_main_token", notebook_alias="main"
    )
    side_hits = provider.query(
        cfg, repo_root=repo, question="unique_main_token", notebook_alias="side"
    )
    sources_main = main_hits.get("sources") or []
    sources_side = side_hits.get("sources") or []
    assert any("unique_main_token" in (s.get("excerpt") or "") for s in sources_main)
    assert not any("unique_main_token" in (s.get("excerpt") or "") for s in sources_side)


def test_closeout_apply_rebuilds_local_fts(tmp_path: Path, monkeypatch):
    repo, home = _multi_local_fts_repo(tmp_path)
    # Simplify to single-scope default for closeout (omit alias requirement).
    cfg_path = repo / ".config" / "vibe-control.yaml"
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    data["knowledge"].pop("notebooks", None)
    data["project"]["id"] = "local-fts-closeout"
    cfg_path.write_text(yaml.safe_dump(data), encoding="utf-8")

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(repo)

    cfg = load_config(repo)
    _corpus, scope = resolve_corpus_for_target(cfg, notebook_alias=None, repo_root=repo)
    path = index_path(cfg.project_id, scope, home=home)
    assert not path.exists()

    result = run_closeout(
        repo_root=repo,
        apply=True,
        deps={"git_status_short": lambda _root: ""},
    )
    assert result.get("ok") is True
    assert path.exists(), f"expected local_fts index after closeout: {result}"
    kc = (result.get("data") or {}).get("knowledge_closeout") or {}
    assert kc.get("applied") is True or path.exists()
