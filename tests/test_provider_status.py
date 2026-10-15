"""PATH-only provider status tests (no real NotebookLM / Beads required)."""

from __future__ import annotations

from vibe_control.knowledge.notebooklm_provider import NotebookLMProvider
from vibe_control.task.beads_provider import BeadsProvider


def test_notebooklm_status_uses_path_lookup_only(monkeypatch):
    monkeypatch.setattr(
        "vibe_control.knowledge.notebooklm_provider.shutil.which",
        lambda name: "/tmp/fake-notebooklm" if name == "notebooklm" else None,
    )
    status = NotebookLMProvider().status()
    assert status.installed is True
    assert status.executable == "/tmp/fake-notebooklm"

    monkeypatch.setattr(
        "vibe_control.knowledge.notebooklm_provider.shutil.which",
        lambda name: None,
    )
    status = NotebookLMProvider().status()
    assert status.installed is False
    assert status.executable is None


def test_beads_status_uses_path_lookup_only(monkeypatch):
    monkeypatch.setattr(
        "vibe_control.task.beads_provider.shutil.which",
        lambda name: "/tmp/fake-bd" if name == "bd" else None,
    )
    status = BeadsProvider().status()
    assert status.installed is True
    assert status.executable == "/tmp/fake-bd"

    monkeypatch.setattr(
        "vibe_control.task.beads_provider.shutil.which",
        lambda name: None,
    )
    status = BeadsProvider().status()
    assert status.installed is False
