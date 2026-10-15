"""Human-readable doctor default text (user validation path)."""

from __future__ import annotations

import json

from vibe_control.cli import format_doctor_text, main


def test_doctor_default_is_human_text(capsys, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    code = main(["doctor"])
    out = capsys.readouterr().out
    assert code == 0
    assert "vibe doctor" in out
    assert "config_ok" in out
    assert "mutation" in out
    assert not out.lstrip().startswith("{")


def test_doctor_json_still_envelope(capsys, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    code = main(["doctor", "--json"])
    out = capsys.readouterr().out
    assert code == 0
    payload = json.loads(out)
    assert payload["ok"] is True
    assert payload["command"] == "vibe doctor"
    assert "_emit_text" not in payload
    assert "capability_profile" in payload["data"]


def test_format_doctor_text_includes_core_fields():
    text = format_doctor_text(
        {
            "ok": True,
            "project_id": "demo",
            "warnings": [],
            "data": {
                "config_ok": True,
                "mutation": False,
                "capability_profile": {"default_disabled": True},
                "components": {
                    "knowledge": {"enabled": False, "available": True},
                    "task": {"enabled": False, "available": True},
                },
                "notebooklm": {"installed": False, "auth_state": "not_checked"},
                "beads": {"installed": False},
                "skills": {"installed": False, "condition": "missing"},
            },
        }
    )
    assert "demo" in text
    assert "default_disabled=True" in text
    assert "skills:" in text
    assert "condition=missing" in text


def test_doctor_json_includes_skills_readiness(capsys, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VIBE_SKILLS_ROOT", str(tmp_path / "skills"))
    code = main(["doctor", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    skills = payload["data"]["skills"]
    assert skills["condition"] == "missing"
    assert skills["installed"] is False
    assert any("skills install" in a for a in payload.get("next_actions") or [])
