"""Contract and behavior tests for knowledge query (repo fallback)."""

from __future__ import annotations

import json
from pathlib import Path

from vibe_control.cli import main
from helpers import (
    minimal_config_dict,
    write_control_yaml,
    write_doc,
    write_registry,
)


def _run(monkeypatch, tmp_path: Path, argv: list[str], capsys) -> tuple[int, dict]:
    monkeypatch.chdir(tmp_path)
    code = main(argv)
    out = capsys.readouterr().out
    return code, json.loads(out)


def _seed_basic_repo(tmp_path: Path) -> None:
    raw = minimal_config_dict(
        include_extra=["docs/project/DECISION_LOG.md"],
    )
    write_control_yaml(tmp_path, raw)
    write_registry(
        tmp_path,
        [
            {
                "id": "active_spec",
                "status": "active",
                "path": "docs/project/active.md",
                "title": "Active Publish Spec",
            },
            {
                "id": "draft_spec",
                "status": "draft",
                "path": "docs/project/draft.md",
                "title": "Draft Spec",
            },
            {
                "id": "plan_spec",
                "status": "active",
                "path": "docs/program/plans/example.md",
                "title": "Plan Doc",
            },
        ],
    )
    write_doc(
        tmp_path,
        "docs/project/active.md",
        "# Active Publish Spec\n\nThis document describes how to publish the migration harness.\n",
    )
    write_doc(tmp_path, "docs/project/draft.md", "draft should not be searched publish secrets\n")
    write_doc(tmp_path, "docs/program/plans/example.md", "plan publish should be excluded\n")
    write_doc(tmp_path, "docs/project/DECISION_LOG.md", "Decision: keep publish flow explicit.\n")


def test_query_envelope_keys_stable(tmp_path: Path, monkeypatch, capsys):
    _seed_basic_repo(tmp_path)
    q = tmp_path / "q.txt"
    q.write_text("publish migration", encoding="utf-8")
    code, payload = _run(
        monkeypatch,
        tmp_path,
        ["knowledge", "query", "--question-file", str(q), "--json"],
        capsys,
    )
    assert code == 0
    assert payload["ok"] is True
    assert payload["command"] == "vibe knowledge query"
    assert payload["project_id"] == "migration-harness"
    assert payload["mode"] == "degraded"
    assert "data" in payload
    assert "warnings" in payload
    assert "next_actions" in payload
    assert payload["data"]["provider"] == "repo"


def test_missing_question_file(tmp_path: Path, monkeypatch, capsys):
    _seed_basic_repo(tmp_path)
    code, payload = _run(
        monkeypatch,
        tmp_path,
        ["knowledge", "query", "--question-file", "missing-q.txt", "--json"],
        capsys,
    )
    assert code == 1
    assert payload["ok"] is False
    assert payload["error"]["code"] == "QUESTION_FILE_NOT_FOUND"


def test_empty_question_file(tmp_path: Path, monkeypatch, capsys):
    _seed_basic_repo(tmp_path)
    q = tmp_path / "empty.txt"
    q.write_text("   \n", encoding="utf-8")
    code, payload = _run(
        monkeypatch,
        tmp_path,
        ["knowledge", "query", "--question-file", str(q), "--json"],
        capsys,
    )
    assert code == 1
    assert payload["ok"] is False
    assert payload["error"]["code"] == "QUESTION_EMPTY"


def test_missing_config(tmp_path: Path, monkeypatch, capsys):
    q = tmp_path / "q.txt"
    q.write_text("anything", encoding="utf-8")
    code, payload = _run(
        monkeypatch,
        tmp_path,
        ["knowledge", "query", "--question-file", str(q), "--json"],
        capsys,
    )
    assert code == 1
    assert payload["error"]["code"] == "CONFIG_NOT_FOUND"


def test_missing_registry(tmp_path: Path, monkeypatch, capsys):
    write_control_yaml(tmp_path, minimal_config_dict())
    q = tmp_path / "q.txt"
    q.write_text("publish", encoding="utf-8")
    code, payload = _run(
        monkeypatch,
        tmp_path,
        ["knowledge", "query", "--question-file", str(q), "--json"],
        capsys,
    )
    assert code == 1
    assert payload["error"]["code"] in {"REGISTRY_NOT_FOUND", "SPEC_REGISTRY_NOT_FOUND"}


def test_query_finds_active_by_content(tmp_path: Path, monkeypatch, capsys):
    _seed_basic_repo(tmp_path)
    q = tmp_path / "q.txt"
    q.write_text("migration harness publish", encoding="utf-8")
    code, payload = _run(
        monkeypatch,
        tmp_path,
        ["knowledge", "query", "--question-file", str(q), "--json"],
        capsys,
    )
    assert code == 0
    sources = payload["data"]["sources"]
    assert any(s["doc_id"] == "active_spec" for s in sources)
    assert all(s["doc_id"] != "draft_spec" for s in sources)
    assert all("plans" not in s["path"] for s in sources)


def test_query_finds_by_title_or_path(tmp_path: Path, monkeypatch, capsys):
    _seed_basic_repo(tmp_path)
    q = tmp_path / "q.txt"
    q.write_text("Active Publish Spec", encoding="utf-8")
    _, payload = _run(
        monkeypatch,
        tmp_path,
        ["knowledge", "query", "--question-file", str(q), "--json"],
        capsys,
    )
    assert any(s["doc_id"] == "active_spec" for s in payload["data"]["sources"])


def test_query_includes_extra_docs(tmp_path: Path, monkeypatch, capsys):
    _seed_basic_repo(tmp_path)
    q = tmp_path / "q.txt"
    q.write_text("Decision keep publish flow", encoding="utf-8")
    _, payload = _run(
        monkeypatch,
        tmp_path,
        ["knowledge", "query", "--question-file", str(q), "--json"],
        capsys,
    )
    assert any(s["path"] == "docs/project/DECISION_LOG.md" for s in payload["data"]["sources"])


def test_missing_included_file_is_warning_not_crash(tmp_path: Path, monkeypatch, capsys):
    raw = minimal_config_dict(include_extra=["docs/project/MISSING.md"])
    write_control_yaml(tmp_path, raw)
    write_registry(
        tmp_path,
        [
            {
                "id": "active_spec",
                "status": "active",
                "path": "docs/project/active.md",
                "title": "Active",
            }
        ],
    )
    write_doc(tmp_path, "docs/project/active.md", "publish content here\n")
    q = tmp_path / "q.txt"
    q.write_text("publish", encoding="utf-8")
    code, payload = _run(
        monkeypatch,
        tmp_path,
        ["knowledge", "query", "--question-file", str(q), "--json"],
        capsys,
    )
    assert code == 0
    assert payload["ok"] is True
    warning_text = json.dumps(payload["warnings"])
    assert "MISSING.md" in warning_text or "missing" in warning_text.lower()


def test_no_evidence_found(tmp_path: Path, monkeypatch, capsys):
    _seed_basic_repo(tmp_path)
    q = tmp_path / "q.txt"
    q.write_text("zzzznotavalidtermqqq", encoding="utf-8")
    code, payload = _run(
        monkeypatch,
        tmp_path,
        ["knowledge", "query", "--question-file", str(q), "--json"],
        capsys,
    )
    assert code == 0
    assert payload["ok"] is True
    assert payload["mode"] == "degraded"
    assert payload["data"]["provider"] == "repo"
    assert payload["data"]["answer"] == ""
    assert payload["data"]["sources"] == []
    codes = [
        w.get("code") if isinstance(w, dict) else None for w in payload["warnings"]
    ]
    assert "NO_EVIDENCE_FOUND" in codes


def test_source_fields_and_sort_order(tmp_path: Path, monkeypatch, capsys):
    write_control_yaml(tmp_path, minimal_config_dict(include_extra=[]))
    write_registry(
        tmp_path,
        [
            {
                "id": "weak",
                "status": "active",
                "path": "docs/weak.md",
                "title": "Weak",
            },
            {
                "id": "strong",
                "status": "active",
                "path": "docs/strong.md",
                "title": "Strong Publish Publish Publish",
            },
        ],
    )
    write_doc(tmp_path, "docs/weak.md", "mentions publish once\n")
    write_doc(
        tmp_path,
        "docs/strong.md",
        "publish publish publish migration harness details\n",
    )
    q = tmp_path / "q.txt"
    q.write_text("publish migration", encoding="utf-8")
    _, payload = _run(
        monkeypatch,
        tmp_path,
        ["knowledge", "query", "--question-file", str(q), "--json"],
        capsys,
    )
    sources = payload["data"]["sources"]
    assert sources
    required = {"doc_id", "path", "title", "score", "matched_terms", "excerpt"}
    assert required.issubset(sources[0].keys())
    scores = [s["score"] for s in sources]
    assert scores == sorted(scores, reverse=True)
    assert payload["mode"] == "degraded"
    assert payload["data"]["provider"] == "repo"
