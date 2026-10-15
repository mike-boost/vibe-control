"""Acceptance observed-output routing: default must not overwrite tracked observed/."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "acceptance"))
from lib.observed_output import (  # noqa: E402
    UPDATE_ENV,
    resolve_observed_dir,
    save_observed,
    tracked_observed_path,
    update_tracked_observed_enabled,
)


PHASE4 = ROOT / "acceptance" / "phase4"


def test_default_save_writes_runtime_not_tracked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(UPDATE_ENV, raising=False)
    phase = tmp_path / "phaseX"
    phase.mkdir()
    tracked = phase / "observed"
    tracked.mkdir()
    sentinel = tracked / "keep.json"
    sentinel.write_text('{"keep": true}\n', encoding="utf-8")

    out = save_observed(phase, "inventory.json", {"ok": True, "n": 1})
    assert out.parent.name == "observed-runtime"
    assert out.is_file()
    assert json.loads(out.read_text())["ok"] is True
    assert sentinel.read_text() == '{"keep": true}\n'
    assert not (tracked / "inventory.json").exists()
    assert update_tracked_observed_enabled() is False


def test_explicit_update_writes_tracked_observed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(UPDATE_ENV, "1")
    phase = tmp_path / "phaseY"
    phase.mkdir()
    out = save_observed(phase, "inventory.json", {"ok": True})
    assert out == tracked_observed_path(phase, "inventory.json")
    assert out.parent.name == "observed"
    assert update_tracked_observed_enabled() is True


def test_resolve_observed_dir_defaults_to_runtime(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(UPDATE_ENV, raising=False)
    assert resolve_observed_dir(PHASE4).name == "observed-runtime"
    monkeypatch.setenv(UPDATE_ENV, "1")
    assert resolve_observed_dir(PHASE4).name == "observed"


def test_phase4_default_save_does_not_touch_tracked(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Import phase4 save path semantics via helper used by runner."""
    monkeypatch.delenv(UPDATE_ENV, raising=False)
    # Use real phase4 dir name layout under tmp
    phase = tmp_path / "phase4"
    (phase / "observed").mkdir(parents=True)
    before = {"a": 1}
    tracked = phase / "observed" / "inventory.json"
    tracked.write_text(json.dumps(before), encoding="utf-8")
    save_observed(phase, "inventory.json", {"ok": True, "fresh": True})
    assert json.loads(tracked.read_text()) == before
