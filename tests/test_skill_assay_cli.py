"""CLI integration tests for vibe skill-assay."""

from __future__ import annotations

import json
from pathlib import Path

from vibe_control.cli import main


def _skill(tmp_path: Path) -> Path:
    skill = tmp_path / "cli-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("# CLI Skill\n", encoding="utf-8")
    return skill


def test_skill_assay_doctor_fake(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    code = main(["skill-assay", "doctor", "--host", "fake", "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["mutation_intent"] is False
    assert payload["data"]["support_state"] == "supported"


def test_skill_assay_diagnose_dry_run_and_execute(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    skill = _skill(tmp_path)
    prompt = tmp_path / "p.txt"
    prompt.write_text("do it\n", encoding="utf-8")
    code = main(
        [
            "skill-assay",
            "diagnose",
            "--skill",
            str(skill),
            "--host",
            "fake",
            "--prompt-file",
            str(prompt),
            "--runs",
            "3",
            "--dry-run",
            "--json",
        ]
    )
    assert code == 0
    dry = json.loads(capsys.readouterr().out)
    assert dry["ok"] is True
    assert dry["data"]["dry_run"] is True
    assert dry["effects"] == []

    code = main(
        [
            "skill-assay",
            "diagnose",
            "--skill",
            str(skill),
            "--host",
            "fake",
            "--prompt-file",
            str(prompt),
            "--runs",
            "3",
            "--execute",
            "--json",
        ]
    )
    assert code == 0
    exe = json.loads(capsys.readouterr().out)
    assert exe["ok"] is True
    assert exe["mutation_performed"] is True
    assert exe["effects"][0]["target"] == "skill_assay.evidence"
    assay_id = exe["data"]["assay_id"]

    code = main(["skill-assay", "report", "--assay", assay_id, "--json"])
    assert code == 0
    rep = json.loads(capsys.readouterr().out)
    assert rep["ok"] is True
    assert rep["mutation_intent"] is False
    assert rep["data"]["kind"] == "evidence"


def test_skill_assay_doctor_cursor_reports_blockers(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    from vibe_control.skill_assay.adapters import HostDoctorResult

    monkeypatch.chdir(tmp_path)

    def fake_doctor(self):  # noqa: ANN001
        del self
        return HostDoctorResult(
            host_id="cursor",
            ok=False,
            support_state="unavailable",
            blockers=["SKILL_ASSAY_CURSOR_AUTH_REQUIRED"],
        )

    monkeypatch.setattr(
        "vibe_control.skill_assay.adapters.cursor.CursorHostAdapter.doctor",
        fake_doctor,
    )
    code = main(["skill-assay", "doctor", "--host", "cursor", "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["data"]["ok"] is False
    assert payload["data"]["support_state"] == "unavailable"
    assert "SKILL_ASSAY_CURSOR_AUTH_REQUIRED" in payload["data"]["blockers"]
