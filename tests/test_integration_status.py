"""Tests for integration status aggregation."""

from __future__ import annotations

import json

from vibe_control.cli import main
from vibe_control.integration import build_integration_status
from vibe_control.knowledge.notebooklm_provider import NotebookLMProvider, NotebookLMStatus
from vibe_control.task.beads_provider import BeadsProvider, BeadsStatus


class FakeNLM(NotebookLMProvider):
    def __init__(self, installed: bool):
        super().__init__(runner=lambda argv: (0, "", ""))
        self._installed = installed

    def which(self):
        return "/tmp/fake-notebooklm" if self._installed else None

    def status(self, *, probe_auth: bool = False) -> NotebookLMStatus:
        if not self._installed:
            return NotebookLMStatus(
                installed=False,
                executable=None,
                message="missing",
            )
        return NotebookLMStatus(
            installed=True,
            executable="/tmp/fake-notebooklm",
            version="fake",
            message="ok",
        )


class FakeBeads(BeadsProvider):
    def __init__(self, installed: bool):
        super().__init__(runner=lambda argv: (0, "", ""))
        self._installed = installed

    def which(self):
        return "/tmp/fake-bd" if self._installed else None

    def status(self) -> BeadsStatus:
        if not self._installed:
            return BeadsStatus(installed=False, executable=None, message="missing")
        return BeadsStatus(
            installed=True,
            executable="/tmp/fake-bd",
            version="fake",
            message="ok",
            init_safe_mode="unknown",
        )

    def init_preview(self) -> BeadsStatus:
        return BeadsStatus(
            installed=True,
            executable="/tmp/fake-bd",
            version="fake",
            message="skip",
            init_available=True,
            init_safe_mode="skip_agents",
            recommended_init="bd init --skip-agents",
            help_flags={"skip_agents": True, "stealth": False},
        )


def test_integration_status_notebooklm_installed(monkeypatch, tmp_path):
    monkeypatch.setenv("VIBE_SKILLS_ROOT", str(tmp_path / "skills"))
    data = build_integration_status(
        repo_root=tmp_path,
        notebooklm=FakeNLM(True),
        beads=FakeBeads(False),
        probe_product=False,
        knowledge_parts={
            "available": False,
            "target_ok": False,
            "sync_state": "unavailable",
        },
        task_parts={"available": False, "mode": "unavailable", "readable": False},
    )
    assert data["notebooklm"]["installed"] is True
    assert data["notebooklm"]["safe_to_sync"] is False
    assert data["beads"]["installed"] is False
    # Default-disabled capability profile: unavailable providers do not fail readiness.
    assert data["product_ready"] is True
    assert data["components"]["knowledge"]["enabled"] is False
    assert data["components"]["task"]["enabled"] is False
    assert data["repo"]["fallback_is_product_ready"] is False


def test_integration_status_notebooklm_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("VIBE_SKILLS_ROOT", str(tmp_path / "skills"))
    data = build_integration_status(
        repo_root=tmp_path,
        notebooklm=FakeNLM(False),
        beads=FakeBeads(False),
        probe_product=False,
        knowledge_parts={
            "available": False,
            "target_ok": False,
            "sync_state": "unavailable",
        },
        task_parts={"available": False, "mode": "unavailable", "readable": False},
    )
    assert data["notebooklm"]["installed"] is False
    assert data["notebooklm"]["safe_to_sync"] is False


def test_integration_status_beads_installed(tmp_path, monkeypatch):
    monkeypatch.setenv("VIBE_SKILLS_ROOT", str(tmp_path / "skills"))
    data = build_integration_status(
        repo_root=tmp_path,
        notebooklm=FakeNLM(False),
        beads=FakeBeads(True),
        probe_product=False,
        knowledge_parts={
            "available": True,
            "target_ok": True,
            "sync_state": "synced",
            "required_updates_count": 0,
            "candidate_count": 0,
            "orphan_managed_count": 0,
        },
        task_parts={
            "available": True,
            "mode": "readonly",
            "readable": True,
            "ready_queue_available": True,
        },
    )
    assert data["beads"]["installed"] is True
    assert data["beads"]["init_safe_mode"] == "skip_agents"
    assert data["product_ready"] is True


def test_integration_status_includes_skills(tmp_path, monkeypatch):
    monkeypatch.setenv("VIBE_SKILLS_ROOT", str(tmp_path / "skills"))
    data = build_integration_status(
        repo_root=tmp_path,
        notebooklm=FakeNLM(False),
        beads=FakeBeads(False),
        probe_product=False,
        knowledge_parts={"available": False, "target_ok": False, "sync_state": "unavailable"},
        task_parts={"available": False, "mode": "unavailable", "readable": False},
    )
    assert "skills" in data
    assert data["skills"]["source_exists"] is True
    assert data["skills"]["installed"] is False
    assert len(data["skills"]["skills"]) == 3
    assert {s["name"] for s in data["skills"]["skills"]} == {
        "vibe-control",
        "vibe-knowledge",
        "vibe-implementation",
    }


def test_integration_status_never_safe_to_sync(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("VIBE_SKILLS_ROOT", str(tmp_path / "skills"))
    monkeypatch.chdir(tmp_path)
    code = main(["integration", "status", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["ok"] is True
    assert payload["data"]["notebooklm"]["safe_to_sync"] is False
