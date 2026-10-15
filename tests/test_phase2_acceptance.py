"""Phase 2 acceptance coverage over the durable fixture pack."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from vibe_control.cli import main

REPO_ROOT = Path(__file__).resolve().parents[1]
PHASE2 = REPO_ROOT / "acceptance" / "phase2"
FIXTURE = PHASE2 / "fixtures" / "migration-harness-mini"
QUESTION = PHASE2 / "questions" / "publish-question.txt"
RUNNER = PHASE2 / "run_phase2_acceptance.py"

EXCLUDED_PATHS = {
    "docs/project/SUPERSEDED_SPEC.md",
    "docs/program/plans/EXCLUDED_PLAN.md",
    "docs/phases/phase3/plans/EXCLUDED_PHASE_PLAN.md",
    "docs/dashboard/EXCLUDED_DASHBOARD.md",
    "docs/archive/EXCLUDED_ARCHIVE.md",
}


def _cli(monkeypatch, capsys, argv: list[str]) -> tuple[int, dict]:
    monkeypatch.chdir(FIXTURE)
    code = main(argv)
    payload = json.loads(capsys.readouterr().out)
    return code, payload


def test_fixture_config_validates(monkeypatch, capsys):
    code, payload = _cli(monkeypatch, capsys, ["config", "validate", "--json"])
    assert code == 0
    assert payload["ok"] is True
    assert payload["project_id"] == "migration-harness"


def test_fixture_inventory_includes_active_and_decision_log(monkeypatch, capsys):
    code, payload = _cli(monkeypatch, capsys, ["knowledge", "inventory", "--json"])
    assert code == 0
    paths = {d["path"] for d in payload["data"]["documents"]}
    assert "docs/project/ACTIVE_SPEC.md" in paths
    assert "docs/project/DECISION_LOG.md" in paths


def test_fixture_inventory_excludes_superseded_and_dynamic_docs(monkeypatch, capsys):
    _, payload = _cli(monkeypatch, capsys, ["knowledge", "inventory", "--json"])
    paths = {d["path"] for d in payload["data"]["documents"]}
    assert paths.isdisjoint(EXCLUDED_PATHS)
    ids = {d["doc_id"] for d in payload["data"]["documents"]}
    assert "superseded_legacy_spec" not in ids


def test_fixture_query_finds_active_spec_evidence(monkeypatch, capsys):
    code, payload = _cli(
        monkeypatch,
        capsys,
        ["knowledge", "query", "--question-file", str(QUESTION), "--json"],
    )
    assert code == 0
    assert payload["ok"] is True
    assert payload["mode"] == "degraded"
    assert payload["data"]["provider"] == "repo"
    paths = {s["path"] for s in payload["data"]["sources"]}
    assert "docs/project/ACTIVE_SPEC.md" in paths


def test_fixture_query_does_not_search_excluded_files(monkeypatch, capsys):
    _, payload = _cli(
        monkeypatch,
        capsys,
        ["knowledge", "query", "--question-file", str(QUESTION), "--json"],
    )
    paths = {s["path"] for s in payload["data"]["sources"]}
    assert paths.isdisjoint(EXCLUDED_PATHS)
    blob = json.dumps(payload)
    for secret in (
        "SUPERSEDED_SHOULD_NOT_MATCH",
        "EXCLUDED_PROGRAM_PLAN_SHOULD_NOT_MATCH",
        "EXCLUDED_PHASE_PLAN_SHOULD_NOT_MATCH",
        "EXCLUDED_DASHBOARD_SHOULD_NOT_MATCH",
        "EXCLUDED_ARCHIVE_SHOULD_NOT_MATCH",
    ):
        assert secret not in blob


def test_fixture_query_is_degraded_repo_fallback(monkeypatch, capsys):
    _, payload = _cli(
        monkeypatch,
        capsys,
        ["knowledge", "query", "--question-file", str(QUESTION), "--json"],
    )
    assert payload["mode"] == "degraded"
    assert payload["data"]["provider"] == "repo"
    assert payload["data"]["fallback_reason"] == "notebooklm_not_used_in_phase_2"


def test_acceptance_script_exits_zero():
    proc = subprocess.run(
        [sys.executable, str(RUNNER)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
    assert "Phase 2 acceptance PASSED" in proc.stdout


def test_acceptance_command_outputs_parse_as_json():
    commands = [
        ["doctor", "--json"],
        ["config", "validate", "--json"],
        ["knowledge", "inventory", "--json"],
        ["knowledge", "status", "--json"],
        ["knowledge", "query", "--question-file", str(QUESTION), "--json"],
    ]
    for args in commands:
        proc = subprocess.run(
            [sys.executable, "-m", "vibe_control", *args],
            cwd=FIXTURE,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, f"{args}: {proc.stderr}"
        payload = json.loads(proc.stdout)
        assert "ok" in payload
        assert "command" in payload
