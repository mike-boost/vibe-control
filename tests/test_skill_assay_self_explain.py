"""Skill Assay self-explain: describe contract + Gateway brief entry."""

from __future__ import annotations

import json
from pathlib import Path

from vibe_control.cli import main
from vibe_control.gateway import ROUTE_TABLE, normalize_intent, route_gateway
from vibe_control.skill_assay.contract import (
    SKILL_ASSAY_CONTRACT_ID,
    skill_assay_contract_dict,
)


def test_skill_assay_contract_static_shape() -> None:
    c = skill_assay_contract_dict()
    assert c["contract_id"] == SKILL_ASSAY_CONTRACT_ID
    assert c["primary_operator"] == "coding_agent"
    assert any("skill_assay_brief" in x for x in c["entry_commands"])
    assert any("vibe skills" in x.lower() for x in c["when_not_to_invoke"])
    assert "facts" in c["required_workflow"].lower()


def test_describe_exposes_skill_assay_contract(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    code = main(["describe", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    contracts = payload["data"]["communication_contracts"]
    assert contracts["skill_assay"]["contract_id"] == SKILL_ASSAY_CONTRACT_ID
    names = {s["name"] for s in payload["data"]["readonly_surfaces"]}
    assert "skill_assay.brief" in names
    assert "skill_assay.doctor" in names


def test_gateway_skill_assay_aliases() -> None:
    assert normalize_intent("skill_assay_brief") == "skill_assay_brief"
    assert normalize_intent("skill-assay") == "skill_assay_brief"
    assert normalize_intent("assay") == "skill_assay_brief"
    assert "skill_assay_brief" in ROUTE_TABLE
    assert ROUTE_TABLE["skill_assay_brief"]["mutation"] is False


def test_gateway_skill_assay_brief_with_skill(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    skill = tmp_path / "owner-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("# Owner Skill\n", encoding="utf-8")

    env = route_gateway(
        intent="skill-assay",
        repo_root=tmp_path,
        skill=str(skill),
        host="fake",
    )
    assert env["ok"] is True
    assert env["mutation_intent"] is False
    data = env["data"]["engine_payload"]["data"]
    assert data["communication_mode"] == "skill_assay"
    assert data["skill"]["skill_md_present"] is True
    assert data["host_doctor"]["support_state"] == "supported"
    codes = {a["code"] for a in env["data"]["engine_payload"]["next_actions"]}
    assert "SKILL_ASSAY_DOCTOR" in codes
    assert "SKILL_ASSAY_DIAGNOSE_EXECUTE" in codes


def test_gateway_skill_assay_brief_requires_host(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    skill = tmp_path / "owner-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("# Owner Skill\n", encoding="utf-8")
    env = route_gateway(
        intent="skill-assay",
        repo_root=tmp_path,
        skill=str(skill),
    )
    assert env["ok"] is True
    codes = {a["code"] for a in env["data"]["engine_payload"]["next_actions"]}
    assert codes == {"SKILL_ASSAY_HOST_REQUIRED"}


def test_skill_assay_brief_cli(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    skill = tmp_path / "cli-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("# X\n", encoding="utf-8")
    code = main(
        [
            "skill-assay",
            "brief",
            "--skill",
            str(skill),
            "--host",
            "fake",
            "--json",
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["data"]["communication_contract"]["contract_id"] == SKILL_ASSAY_CONTRACT_ID
