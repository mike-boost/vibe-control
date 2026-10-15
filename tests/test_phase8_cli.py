"""Phase 8 CLI production wiring tests (fake / isolated; no real NotebookLM mutation)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from helpers import write_doc, write_registry
from vibe_control.cli import main
from vibe_control.knowledge.remote_ack import FakeAckStore
from vibe_control.knowledge.phase8_runtime import Phase8Runtime


def _seed(tmp: Path) -> None:
    cfg = {
        "project": {"id": "vibe-control", "name": "Vibe Control"},
        "components": {
            "knowledge": {"enabled": True},
            "task": {"enabled": False},
            "sdd": {"enabled": False},
            "tdd": {"enabled": False},
        },
        "knowledge": {
            "provider": "notebooklm",
            "fallback_provider": "repo",
            "max_sources": 20,
            "warn_sources": 15,
            "authoritative_statuses": ["active"],
            "include_extra": [],
            "exclude_globs": ["**/archive/**"],
            "source_title_template": "[vibe:{project_id}:{doc_id}] {title}",
            "notebooks": {
                "default_alias": "OPM-test",
                "allow_list": [
                    {
                        "alias": "OPM-test",
                        "display_name": "OPM-test",
                        "ref_env": "NOTEBOOKLM_NOTEBOOK_OPM_TEST",
                        "allowed_operations": ["status", "sync", "retry", "query"],
                    }
                ],
            },
        },
        "specs": {
            "registry": "docs/project/spec-registry.yml",
            "required_fields": ["id", "status", "path"],
            "require_commit_push_for_ssot": True,
        },
        "tasks": {"provider": "beads"},
    }
    path = tmp / ".config" / "vibe-control.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    write_registry(
        tmp,
        [
            {
                "id": "active_spec",
                "title": "Active",
                "status": "active",
                "path": "docs/project/active.md",
            }
        ],
    )
    write_doc(tmp, "docs/project/active.md", "active body\n")


def _run(monkeypatch, tmp_path: Path, argv: list[str], capsys) -> tuple[int, dict]:
    monkeypatch.chdir(tmp_path)
    code = main(argv)
    return code, json.loads(capsys.readouterr().out)


@pytest.mark.integration
def test_P8_CLI_01_status_returns_sync_state(tmp_path: Path, monkeypatch, capsys):
    _seed(tmp_path)
    monkeypatch.setenv("NOTEBOOKLM_NOTEBOOK_OPM_TEST", "nb-cli-status")
    monkeypatch.setenv("VIBE_PHASE8_FAKE_PROVIDER", "unavailable")
    code, payload = _run(
        monkeypatch,
        tmp_path,
        ["knowledge", "status", "--json"],
        capsys,
    )
    assert code == 0
    assert payload["ok"] is True
    data = payload["data"]
    assert "sync_state" in data
    assert data["sync_state"] in {
        "synced",
        "pending",
        "drift",
        "unavailable",
        "degraded",
        "target_mismatch",
        "receipt_missing",
    }
    assert "not implemented" not in str(data.get("note", "")).lower()


@pytest.mark.integration
def test_P8_CLI_02_status_is_read_only(tmp_path: Path, monkeypatch, capsys):
    _seed(tmp_path)
    monkeypatch.setenv("NOTEBOOKLM_NOTEBOOK_OPM_TEST", "nb-cli-ro")
    counters = {"add": 0, "delete": 0, "write_ack": 0}

    class CountingAck(FakeAckStore):
        def write_ack(self, target, ack):  # type: ignore[override]
            counters["write_ack"] += 1
            return super().write_ack(target, ack)

    runtime = Phase8Runtime.for_tests(
        repo_root=tmp_path,
        home=tmp_path,
        ack_store=CountingAck(),
        provider_mode="readonly",
        mutation_counters=counters,
    )
    monkeypatch.setattr(
        "vibe_control.knowledge.phase8_runtime.get_runtime",
        lambda **kwargs: runtime,
    )
    code, payload = _run(
        monkeypatch,
        tmp_path,
        ["knowledge", "status", "--json"],
        capsys,
    )
    assert code == 0
    assert counters["add"] == 0
    assert counters["delete"] == 0
    assert counters["write_ack"] == 0
    assert payload["data"]["sync_state"] in {
        "synced",
        "pending",
        "drift",
        "unavailable",
        "degraded",
        "target_mismatch",
        "receipt_missing",
    }


@pytest.mark.integration
def test_P8_CLI_05_query_does_not_auto_mutate(tmp_path: Path, monkeypatch, capsys):
    _seed(tmp_path)
    monkeypatch.setenv("NOTEBOOKLM_NOTEBOOK_OPM_TEST", "nb-cli-q")
    q = tmp_path / "q.txt"
    q.write_text("active body", encoding="utf-8")
    counters = {"add": 0, "delete": 0, "write_ack": 0}
    runtime = Phase8Runtime.for_tests(
        repo_root=tmp_path,
        home=tmp_path,
        ack_store=FakeAckStore(),
        provider_mode="readonly",
        mutation_counters=counters,
    )
    monkeypatch.setattr(
        "vibe_control.knowledge.phase8_runtime.get_runtime",
        lambda **kwargs: runtime,
    )
    code, payload = _run(
        monkeypatch,
        tmp_path,
        ["knowledge", "query", "--question-file", str(q), "--json"],
        capsys,
    )
    assert code == 0
    assert counters["add"] == 0
    assert counters["delete"] == 0
    assert counters["write_ack"] == 0
    assert payload["mode"] in {"degraded", "local", "provider"}
    if payload["mode"] == "degraded":
        assert payload["data"]["provider"] == "repo"


@pytest.mark.unit
def test_P8_MUTATION_03_phase8_acceptance_has_no_mutation_flags():
    text = (
        Path(__file__).resolve().parents[1]
        / "acceptance"
        / "phase8"
        / "run_phase8_acceptance.py"
    ).read_text(encoding="utf-8")
    # Must not invoke mutation CLI flags; mentioning them in a "does not pass" string is ok.
    assert "sync --apply" not in text
    assert "seed-test-sources --allow-add" not in text
    assert "smoke replace --apply" not in text
    assert '["--apply"' not in text and " '--apply'" not in text
    assert "source add" not in text
    assert "source delete" not in text
