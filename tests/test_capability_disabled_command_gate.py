"""Capability-disabled knowledge/task commands skip provider work."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from vibe_control.cli import main


def _write_disabled_repo(tmp_path: Path) -> None:
    cfg = {
        "project": {"id": "cap-gate", "name": "Cap Gate"},
        "components": {
            "knowledge": {"enabled": False},
            "task": {"enabled": False},
            "sdd": {"enabled": False},
            "tdd": {"enabled": False},
        },
        "knowledge": {
            "provider": "notebooklm",
            "fallback_provider": "repo",
            "max_sources": 10,
            "warn_sources": 8,
            "authoritative_statuses": ["active"],
        },
        "specs": {"registry": "docs/project/spec-registry.yml", "required_fields": ["id"]},
        "tasks": {"provider": "beads"},
    }
    (tmp_path / ".config").mkdir(parents=True)
    (tmp_path / ".config" / "vibe-control.yaml").write_text(
        yaml.safe_dump(cfg), encoding="utf-8"
    )


def test_knowledge_doctor_skips_when_disabled(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    _write_disabled_repo(tmp_path)
    code = main(["knowledge", "doctor", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["ok"] is True
    assert payload["data"]["capability_disabled"] is True
    assert payload["data"]["skipped"] is True
    assert payload["data"]["mutation"] is False
    assert "notebooklm" not in payload["data"]


def test_task_doctor_skips_when_disabled(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    _write_disabled_repo(tmp_path)
    code = main(["task", "doctor", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["data"]["capability_disabled"] is True
    assert payload["data"]["component_id"] == "task"


def test_knowledge_status_skips_when_disabled(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    _write_disabled_repo(tmp_path)
    code = main(["knowledge", "status", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["data"]["skipped"] is True


def test_config_override_enables_knowledge_gate(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    _write_disabled_repo(tmp_path)
    enabled = yaml.safe_load((tmp_path / ".config" / "vibe-control.yaml").read_text())
    enabled["components"]["knowledge"]["enabled"] = True
    alt = tmp_path / "enabled-knowledge.yaml"
    alt.write_text(yaml.safe_dump(enabled), encoding="utf-8")

    code = main(["knowledge", "doctor", "--json", "--config", str(alt)])
    payload = json.loads(capsys.readouterr().out)
    assert code in (0, 1)  # may be not-ready, but must not skip as disabled
    assert payload["data"].get("capability_disabled") is not True
    assert payload["data"].get("skipped") is not True

    code_d = main(["doctor", "--json", "--config", str(alt)])
    doctor = json.loads(capsys.readouterr().out)
    assert code_d == 0
    assert doctor["data"]["capability_profile"]["knowledge_enabled"] is True
    assert doctor["data"]["capability_profile"]["task_enabled"] is False
