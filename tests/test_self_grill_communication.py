"""Self-grill communication contract projected via describe / Gateway brief."""

from __future__ import annotations

import json
from pathlib import Path

from vibe_control.cli import main
from vibe_control.gateway import ROUTE_TABLE, normalize_intent, route_gateway
from vibe_control.self_grill_contract import (
    SELF_GRILL_CONTRACT_ID,
    self_grill_contract_dict,
)


def test_self_grill_contract_static_shape():
    c = self_grill_contract_dict()
    assert c["contract_id"] == SELF_GRILL_CONTRACT_ID
    assert "THESIS:" in c["required_reply_shape"]
    assert "PROVEN" in c["claim_statuses"]
    assert any("grill_brief" in x for x in c["entry_commands"])
    assert "Installable vibe-self-grill skill" in c["non_goals"]
    assert c.get("known_limitations_v1")
    assert any("prose" in x.lower() for x in c["known_limitations_v1"])


def test_describe_exposes_communication_contracts(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    code = main(["describe", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    contracts = payload["data"]["communication_contracts"]
    assert contracts["self_grill"]["contract_id"] == SELF_GRILL_CONTRACT_ID
    assert contracts["git_land"]["contract_id"] == "vibe.communication.git_land.v1"
    assert any("shall i commit" in r.lower() for r in contracts["git_land"]["rules"])
    assert (
        contracts["owner_plain_language"]["contract_id"]
        == "vibe.communication.owner_plain_language.v1"
    )
    assert any("黑话" in r or "plain" in r.lower() for r in contracts["owner_plain_language"]["rules"])
    guidance = " ".join(payload["data"]["knowledge_multi_notebook_guidance"])
    assert "grill_brief" in guidance
    assert "not a separate skill" in guidance.lower() or "not a separate skill" in guidance


def test_git_land_contract_static_shape():
    from vibe_control.git_land_contract import GIT_LAND_CONTRACT_ID, git_land_contract_dict

    c = git_land_contract_dict()
    assert c["contract_id"] == GIT_LAND_CONTRACT_ID
    assert c["dirty_tree_next_action_code"] == "COMMIT_OR_CLEAN_LOCAL_STATE"
    assert "never ask" in " ".join(c["rules"]).lower()


def test_gateway_normalizes_grill_aliases():
    assert normalize_intent("grill_brief") == "grill_brief"
    assert normalize_intent("self-grill") == "grill_brief"
    assert normalize_intent("grill") == "grill_brief"
    assert "grill_brief" in ROUTE_TABLE
    assert ROUTE_TABLE["grill_brief"]["mutation"] is True
    assert ROUTE_TABLE["grill_brief"]["delegate"] == "grill_brief"


def test_gateway_grill_brief_attaches_contract(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()

    def fake_grill_brief(*, repo_root: Path) -> dict:
        from vibe_control.json_envelope import success_envelope
        from vibe_control.self_grill_contract import (
            self_grill_continue_next_action,
            self_grill_contract_dict,
        )

        grill = self_grill_continue_next_action()
        return success_envelope(
            command="vibe brief",
            project_id="test",
            data={
                "communication_mode": "self_grill",
                "communication_contract": self_grill_contract_dict(),
                "safe_next_action": {
                    "code": "CHECK_PROGRESS",
                    "command": "vibe progress --json",
                    "mutation": False,
                    "reason": "test",
                },
                "next_actions": [grill],
            },
            next_actions=[grill],
        )

    out = route_gateway(
        intent="grill_brief",
        repo_root=tmp_path,
        delegates={"grill_brief": fake_grill_brief},
    )
    assert out["ok"] is True
    assert out.get("mutation_intent") is True
    assert out.get("mutation_performed") is False
    assert out.get("mutation") is False
    engine = out["data"]["engine_payload"]
    assert engine["data"]["communication_mode"] == "self_grill"
    assert engine["data"]["communication_contract"]["contract_id"] == SELF_GRILL_CONTRACT_ID
    assert engine["data"]["next_actions"][0]["code"] == "CONTINUE_SELF_GRILL"


def test_skills_install_does_not_include_self_grill():
    from vibe_control.skills_manager import SKILL_NAMES, package_skills_root

    assert "vibe-self-grill" not in SKILL_NAMES
    assert not (package_skills_root() / "vibe-self-grill").exists()
