"""Query router + CLI paths for knowledge.provider=local_fts."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from vibe_control.cli import main
from vibe_control.config import load_config
from vibe_control.knowledge.local_fts.provider import LocalFtsProvider
from vibe_control.knowledge.query_router import route_knowledge_query


def _setup_local_fts_repo(tmp_path: Path) -> tuple[Path, Path]:
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
        "## Special chars\n"
        "\n"
        'Terms like "quoted" and (parentheses) appear here.\n',
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


def _setup_notebooklm_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "nlm-repo"
    (repo / "docs" / "project").mkdir(parents=True)
    (repo / ".config").mkdir(parents=True)
    (repo / "docs" / "project" / "active.md").write_text(
        "# Active\n\npublish migration body\n",
        encoding="utf-8",
    )
    (repo / "docs" / "project" / "spec-registry.yml").write_text(
        yaml.safe_dump(
            [
                {
                    "id": "active_spec",
                    "status": "active",
                    "path": "docs/project/active.md",
                    "title": "Active",
                }
            ]
        ),
        encoding="utf-8",
    )
    (repo / ".config" / "vibe-control.yaml").write_text(
        yaml.safe_dump(
            {
                "project": {"id": "nlm-test", "name": "nlm-test"},
                "components": {"knowledge": {"enabled": True}, "task": {"enabled": False}},
                "knowledge": {
                    "provider": "notebooklm",
                    "fallback_provider": "repo",
                    "max_sources": 20,
                    "warn_sources": 15,
                    "authoritative_statuses": ["active"],
                    "include_extra": [],
                    "exclude_globs": [],
                    "notebooks": {
                        "default_alias": "OPM-test",
                        "allow_list": [
                            {
                                "alias": "OPM-test",
                                "display_name": "OPM-test",
                                "ref_env": "NOTEBOOKLM_NOTEBOOK_OPM_TEST",
                                "allowed_operations": ["status", "query"],
                            }
                        ],
                    },
                },
                "specs": {
                    "registry": "docs/project/spec-registry.yml",
                    "required_fields": ["id", "status", "path"],
                },
                "tasks": {"provider": "fake"},
            }
        ),
        encoding="utf-8",
    )
    return repo


def _use_home(monkeypatch, home: Path) -> None:
    monkeypatch.setenv("HOME", str(home))


def _run_cli(
    monkeypatch,
    repo: Path,
    home: Path,
    argv: list[str],
    capsys,
) -> tuple[int, dict]:
    _use_home(monkeypatch, home)
    monkeypatch.chdir(repo)
    code = main(argv)
    return code, json.loads(capsys.readouterr().out)


def _sync_local_fts(repo: Path, home: Path) -> None:
    cfg = load_config(repo)
    LocalFtsProvider(home=home).sync(cfg, repo_root=repo, apply=True)


def _next_action_commands(next_actions: list) -> list[str]:
    cmds: list[str] = []
    for item in next_actions or []:
        if isinstance(item, dict):
            cmds.append(str(item.get("command") or ""))
        else:
            cmds.append(str(item))
    return cmds


def test_route_knowledge_query_local_fts_after_sync(tmp_path: Path):
    repo, home = _setup_local_fts_repo(tmp_path)
    _sync_local_fts(repo, home)

    result = route_knowledge_query(
        repo_root=repo,
        question="owner approval push",
        home=home,
    )

    assert result["ok"] is True
    assert result["provider"] == "local_fts"
    assert result["answer_mode"] == "evidence_retrieval"
    assert result["sync_state"] == "synced"
    assert result["synced"] is True
    assert result["provider_ask_clean"] is True
    assert result["sources"]
    hit = result["sources"][0]
    assert hit["path"] == "docs/spec.md"
    assert isinstance(hit["line_start"], int) and hit["line_start"] >= 1
    assert isinstance(hit["line_end"], int) and hit["line_end"] >= hit["line_start"]


def test_route_knowledge_query_drift_degraded_with_rebuild_hint(tmp_path: Path):
    repo, home = _setup_local_fts_repo(tmp_path)
    _sync_local_fts(repo, home)

    (repo / "docs" / "spec.md").write_text("# Spec\n\nchanged content\n", encoding="utf-8")

    result = route_knowledge_query(
        repo_root=repo,
        question="changed",
        home=home,
    )

    assert result["provider"] == "local_fts"
    assert result["mode"] == "degraded"
    assert result["sources"] == []
    assert result["provider_ask_clean"] is False
    assert result["sync_state"] == "drift"
    cmds = _next_action_commands(result.get("next_actions") or [])
    assert any("sync --apply" in c for c in cmds)


def test_cli_knowledge_sync_dry_run_and_apply(tmp_path: Path, monkeypatch, capsys):
    repo, home = _setup_local_fts_repo(tmp_path)
    _use_home(monkeypatch, home)

    code, dry = _run_cli(
        monkeypatch,
        repo,
        home,
        ["knowledge", "sync", "--dry-run", "--json"],
        capsys,
    )
    assert code == 0
    assert dry["ok"] is True
    assert dry["command"] == "vibe knowledge sync"
    assert dry["mutation"] is False
    assert dry["data"]["provider"] == "local_fts"
    assert dry["data"]["plan"]["ops"][0]["op"] == "rebuild_index"

    code, applied = _run_cli(
        monkeypatch,
        repo,
        home,
        ["knowledge", "sync", "--apply", "--json"],
        capsys,
    )
    assert code == 0
    assert applied["ok"] is True
    assert applied["mutation"] is True
    assert applied["data"]["sync_state"] == "synced"
    assert applied["data"]["provider_ask_clean"] is True


def test_cli_knowledge_status_before_and_after_sync(tmp_path: Path, monkeypatch, capsys):
    repo, home = _setup_local_fts_repo(tmp_path)
    _use_home(monkeypatch, home)

    code, before = _run_cli(
        monkeypatch,
        repo,
        home,
        ["knowledge", "status", "--json"],
        capsys,
    )
    assert code == 0
    assert before["ok"] is True
    assert before["data"]["sync_state"] == "drift"
    assert before["data"]["synced"] is False
    assert before["data"]["notebooklm"]["auth_state"] == "not_applicable"

    _sync_local_fts(repo, home)

    code, after = _run_cli(
        monkeypatch,
        repo,
        home,
        ["knowledge", "status", "--json"],
        capsys,
    )
    assert code == 0
    assert after["data"]["sync_state"] == "synced"
    assert after["data"]["synced"] is True


def test_cli_knowledge_query_question_file(tmp_path: Path, monkeypatch, capsys):
    repo, home = _setup_local_fts_repo(tmp_path)
    _sync_local_fts(repo, home)

    q = repo / "question.txt"
    q.write_text("owner approval push", encoding="utf-8")

    code, payload = _run_cli(
        monkeypatch,
        repo,
        home,
        ["knowledge", "query", "--question-file", str(q), "--json"],
        capsys,
    )

    assert code == 0
    assert payload["ok"] is True
    assert payload["command"] == "vibe knowledge query"
    assert payload["data"]["provider"] == "local_fts"
    assert payload["data"]["sync_state"] == "synced"
    assert payload["data"]["sources"]
    hit = payload["data"]["sources"][0]
    assert hit["path"] == "docs/spec.md"
    assert hit["line_start"] >= 1
    assert hit["line_end"] >= hit["line_start"]


def test_fts_meta_char_questions_do_not_crash(tmp_path: Path, monkeypatch, capsys):
    repo, home = _setup_local_fts_repo(tmp_path)
    _sync_local_fts(repo, home)

    meta_questions = [
        '"quoted term" (parentheses)',
        'approval "push" AND (matrix)',
        '*wildcard* -minus- :colon:',
    ]
    for question in meta_questions:
        routed = route_knowledge_query(repo_root=repo, question=question, home=home)
        assert routed["ok"] is True
        assert routed["provider"] == "local_fts"

    q = repo / "meta-q.txt"
    q.write_text(meta_questions[0], encoding="utf-8")
    code, payload = _run_cli(
        monkeypatch,
        repo,
        home,
        ["knowledge", "query", "--question-file", str(q), "--json"],
        capsys,
    )
    assert code == 0
    assert payload["ok"] is True
    assert payload["data"]["provider"] == "local_fts"


def test_notebooklm_unsynced_uses_repo_fallback_not_local_fts(
    tmp_path: Path, monkeypatch
):
    repo = _setup_notebooklm_repo(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.delenv("NOTEBOOKLM_NOTEBOOK_OPM_TEST", raising=False)

    result = route_knowledge_query(
        repo_root=repo,
        question="publish migration",
        home=tmp_path / "home",
    )

    assert result["provider"] == "repo"
    assert result["provider"] != "local_fts"
    assert result.get("answer_mode") != "evidence_retrieval"
    assert result.get("synced") is not True
