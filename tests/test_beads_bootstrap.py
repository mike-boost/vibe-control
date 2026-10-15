"""Beads install-guide and init-preview tests."""

from __future__ import annotations

import json

from vibe_control.cli import main


def test_install_guide_when_bd_missing(monkeypatch, capsys):
    monkeypatch.setattr(
        "vibe_control.task.beads_provider.shutil.which",
        lambda name: "/usr/bin/npm" if name == "npm" else None,
    )
    code = main(["task", "install-guide", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["ok"] is True
    assert payload["data"]["installed"] is False
    assert any(o["id"] == "A" for o in payload["data"]["options"])


def test_init_preview_missing_bd(monkeypatch, capsys):
    monkeypatch.setattr(
        "vibe_control.task.beads_provider.shutil.which",
        lambda name: None,
    )
    code = main(["task", "init-preview", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["error"]["code"] == "BEADS_NOT_INSTALLED"


def test_init_preview_recommends_skip_agents(monkeypatch, capsys):
    monkeypatch.setattr(
        "vibe_control.task.beads_provider.shutil.which",
        lambda name: "/tmp/bd" if name == "bd" else None,
    )

    def fake_run(argv, timeout=15.0):
        if "--version" in argv:
            return 0, "bd 1.0\n", ""
        if "init" in argv and "--help" in argv:
            return 0, "Usage: bd init [--skip-agents] [--stealth]\n", ""
        return 0, "", ""

    monkeypatch.setattr(
        "vibe_control.task.beads_provider._default_run",
        fake_run,
    )
    code = main(["task", "init-preview", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["data"]["recommended_init"] == "bd init --skip-agents"
    assert payload["data"]["init_safe_mode"] == "skip_agents"


def test_init_preview_recommends_stealth(monkeypatch, capsys):
    monkeypatch.setattr(
        "vibe_control.task.beads_provider.shutil.which",
        lambda name: "/tmp/bd" if name == "bd" else None,
    )

    def fake_run(argv, timeout=15.0):
        if "--version" in argv:
            return 0, "bd 1.0\n", ""
        if "init" in argv and "--help" in argv:
            return 0, "Usage: bd init [--stealth]\n", ""
        return 0, "", ""

    monkeypatch.setattr(
        "vibe_control.task.beads_provider._default_run",
        fake_run,
    )
    code = main(["task", "init-preview", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["data"]["recommended_init"] == "bd init --stealth"
    assert payload["data"]["init_safe_mode"] == "stealth"


def test_init_preview_warns_unsafe(monkeypatch, capsys):
    monkeypatch.setattr(
        "vibe_control.task.beads_provider.shutil.which",
        lambda name: "/tmp/bd" if name == "bd" else None,
    )

    def fake_run(argv, timeout=15.0):
        if "--version" in argv:
            return 0, "bd 1.0\n", ""
        if "init" in argv and "--help" in argv:
            return 0, "Usage: bd init\nInitializes beads and may update AGENTS.md\n", ""
        return 0, "", ""

    monkeypatch.setattr(
        "vibe_control.task.beads_provider._default_run",
        fake_run,
    )
    code = main(["task", "init-preview", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["error"]["code"] == "BEADS_INIT_UNSAFE"
