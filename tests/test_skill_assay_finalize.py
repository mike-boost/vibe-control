"""TDD: Skill Assay analysis finalize (red first)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vibe_control.skill_assay.adapters.fake import FakeHostAdapter
from vibe_control.skill_assay.errors import SkillAssayError
from vibe_control.skill_assay.finalize import finalize_assay
from vibe_control.skill_assay.orchestrator import run_diagnose


def _prep_evidence(tmp_path: Path) -> str:
    skill = tmp_path / "demo-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("# Demo\n", encoding="utf-8")
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("go\n", encoding="utf-8")
    result = run_diagnose(
        repo_root=tmp_path,
        skill_path=skill,
        host_id="fake",
        prompt_file=prompt,
        runs=2,
        execute=True,
        adapters={"fake": FakeHostAdapter()},
    )
    return str(result["assay_id"])


def test_finalize_rejects_hypothesis_without_evidence_ref(tmp_path: Path) -> None:
    assay_id = _prep_evidence(tmp_path)
    analysis = {
        "schema": "vibe.skill_assay.analysis.v1",
        "hypotheses": [
            {
                "id": "h1",
                "claim": "host drops arrays",
                "evidence_refs": [],
                "doc_citations": [
                    {
                        "host": "fake",
                        "source": "official_docs",
                        "ref": "https://example.com",
                        "fetch_date": "2026-07-22",
                        "doc_version": "2026-07",
                    }
                ],
            }
        ],
        "unknowns": [],
    }
    path = tmp_path / "analysis.json"
    path.write_text(json.dumps(analysis), encoding="utf-8")
    with pytest.raises(SkillAssayError) as exc:
        finalize_assay(repo_root=tmp_path, assay_id=assay_id, analysis_path=path)
    assert exc.value.code == "SKILL_ASSAY_ANALYSIS_EVIDENCE_REF_REQUIRED"


def test_finalize_writes_report(tmp_path: Path) -> None:
    assay_id = _prep_evidence(tmp_path)
    analysis = {
        "schema": "vibe.skill_assay.analysis.v1",
        "hypotheses": [
            {
                "id": "h1",
                "claim": "stable ok field suggests skill loaded",
                "verdict": "pass",
                "evidence_refs": ["stability.stable_fields", "runs/0.assistant_text"],
                "doc_citations": [
                    {
                        "host": "fake",
                        "source": "official_docs",
                        "ref": "https://example.com/docs",
                        "fetch_date": "2026-07-22",
                        "doc_version": "test",
                    }
                ],
            }
        ],
        "unknowns": ["host_internal_reason"],
    }
    path = tmp_path / "analysis.json"
    path.write_text(json.dumps(analysis), encoding="utf-8")
    report = finalize_assay(repo_root=tmp_path, assay_id=assay_id, analysis_path=path)
    assert report["schema"] == "vibe.skill_assay.report.v1"
    assert report["assay_id"] == assay_id
    assert report["causal_scope"] == "single_host"
    assert report["hypotheses"][0]["verdict"] == "pass"
    assert "checks_summary" in report
    assert report["run_excerpts"]
    assert (tmp_path / "runtime/vibe-skill-assay" / assay_id / "report.json").is_file()
    assert (tmp_path / "runtime/vibe-skill-assay" / assay_id / "OWNER_REPORT.html").is_file()
    assert (tmp_path / "runtime/vibe-skill-assay" / assay_id / "AGENT_PACKET.json").is_file()
    assert report.get("owner_html_relative")
    assert report.get("agent_packet_relative")


def test_finalize_rejects_invalid_evidence_ref(tmp_path: Path) -> None:
    assay_id = _prep_evidence(tmp_path)
    analysis = {
        "schema": "vibe.skill_assay.analysis.v1",
        "hypotheses": [
            {
                "id": "h1",
                "claim": "bad ref",
                "verdict": "fail",
                "evidence_refs": ["does.not.exist"],
                "doc_citations": [
                    {
                        "host": "fake",
                        "source": "official_docs",
                        "ref": "https://example.com/docs",
                        "fetch_date": "2026-07-22",
                        "doc_version": "test",
                    }
                ],
            }
        ],
        "unknowns": [],
    }
    path = tmp_path / "analysis.json"
    path.write_text(json.dumps(analysis), encoding="utf-8")
    with pytest.raises(SkillAssayError) as exc:
        finalize_assay(repo_root=tmp_path, assay_id=assay_id, analysis_path=path)
    assert exc.value.code == "SKILL_ASSAY_ANALYSIS_EVIDENCE_REF_INVALID"
