"""TDD: Skill Assay storage + orchestrator with fake host (red first)."""

from __future__ import annotations

from pathlib import Path

import pytest

from vibe_control.skill_assay.adapters.fake import FakeHostAdapter
from vibe_control.skill_assay.constants import DEFAULT_ROOT_REL, SCHEMA_EVIDENCE
from vibe_control.skill_assay.errors import SkillAssayError
from vibe_control.skill_assay.orchestrator import run_diagnose
from vibe_control.skill_assay.storage import assay_root, load_evidence, new_assay_id


def _skill(tmp_path: Path) -> Path:
    skill = tmp_path / "demo-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("# Demo\n\nWrite out.json with {\"ok\": true}.\n", encoding="utf-8")
    return skill


def test_assay_root_relative(tmp_path: Path) -> None:
    root = assay_root(tmp_path)
    assert root == (tmp_path / DEFAULT_ROOT_REL).resolve()


def test_diagnose_dry_run_no_receipt(tmp_path: Path) -> None:
    skill = _skill(tmp_path)
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("produce out.json\n", encoding="utf-8")
    result = run_diagnose(
        repo_root=tmp_path,
        skill_path=skill,
        host_id="fake",
        prompt_file=prompt,
        runs=3,
        execute=False,
        adapters={"fake": FakeHostAdapter()},
    )
    assert result["dry_run"] is True
    assert result["planned_runs"] == 3
    assert not (tmp_path / DEFAULT_ROOT_REL).exists()


def test_diagnose_execute_writes_evidence_with_three_sessions(tmp_path: Path) -> None:
    skill = _skill(tmp_path)
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("produce out.json\n", encoding="utf-8")
    adapter = FakeHostAdapter(
        field_sequence=[
            {"ok": True, "nonce": "a"},
            {"ok": True, "nonce": "b"},
            {"ok": True, "nonce": "a"},
        ]
    )
    result = run_diagnose(
        repo_root=tmp_path,
        skill_path=skill,
        host_id="fake",
        prompt_file=prompt,
        runs=3,
        execute=True,
        adapters={"fake": adapter},
    )
    assert result["dry_run"] is False
    assert result["runs"] == 3
    assert result["causal_scope"] == "single_host"
    assert result["schema"] == SCHEMA_EVIDENCE
    evidence = load_evidence(tmp_path, result["assay_id"])
    session_ids = [r["session_id"] for r in evidence["run_summaries"]]
    assert len(set(session_ids)) == 3
    assert "nonce" in evidence["stability"]["unstable_fields"]
    assert "ok" in evidence["stability"]["stable_fields"]
    assert (tmp_path / DEFAULT_ROOT_REL / result["assay_id"] / "evidence.json").is_file()
    assistant = (
        tmp_path / DEFAULT_ROOT_REL / result["assay_id"] / "runs" / "0.assistant_text"
    )
    assert assistant.is_file()
    assert "Mode: execute" in assistant.read_text(encoding="utf-8")
    assert any(f.startswith("assistant_nonempty=") for f in evidence["facts"])
    workspace_skill = (
        tmp_path
        / DEFAULT_ROOT_REL
        / result["assay_id"]
        / "workspaces"
        / "run-0"
        / ".cursor"
        / "skills"
        / "demo-skill"
        / "SKILL.md"
    )
    assert workspace_skill.is_file()


def test_diagnose_assistant_text_match_check(tmp_path: Path) -> None:
    skill = _skill(tmp_path)
    scenario = tmp_path / "scenario.yaml"
    scenario.write_text(
        "schema: vibe.skill_assay.scenario.v1\n"
        "prompt: produce structured reply\n"
        "execution_profile: response_only\n"
        "checks:\n"
        "  - kind: assistant_text_match\n"
        '    contains: "Mode: execute"\n'
        "  - kind: file_exists\n"
        "    path: out.json\n",
        encoding="utf-8",
    )
    result = run_diagnose(
        repo_root=tmp_path,
        skill_path=skill,
        host_id="fake",
        scenario_path=scenario,
        runs=2,
        execute=True,
        adapters={"fake": FakeHostAdapter()},
    )
    assert all(batch[0]["pass"] for batch in result["checks"])
    assert result["checks_summary"]["pass_rate"] == 1.0


def test_diagnose_rejects_unknown_host(tmp_path: Path) -> None:
    skill = _skill(tmp_path)
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("x\n", encoding="utf-8")
    with pytest.raises(SkillAssayError) as exc:
        run_diagnose(
            repo_root=tmp_path,
            skill_path=skill,
            host_id="nope",
            prompt_file=prompt,
            runs=3,
            execute=False,
            adapters={"fake": FakeHostAdapter()},
        )
    assert exc.value.code == "SKILL_ASSAY_HOST_UNKNOWN"


def test_new_assay_id_prefix() -> None:
    assert new_assay_id().startswith("assay-")
    assert new_assay_id(host_id="cursor").startswith("assay-cursor-")
    assert new_assay_id(host_id="github-copilot").startswith("assay-github-copilot-")
