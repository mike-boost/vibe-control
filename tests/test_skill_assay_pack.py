"""Pack + HTML owner report tests."""

from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile

from vibe_control.skill_assay.adapters.fake import FakeHostAdapter
from vibe_control.skill_assay.finalize import finalize_assay
from vibe_control.skill_assay.orchestrator import run_diagnose
from vibe_control.skill_assay.pack import pack_assay


def test_finalize_writes_html_and_pack_zip(tmp_path: Path) -> None:
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
    assay_id = str(result["assay_id"])
    assert assay_id.startswith("assay-fake-")
    analysis = {
        "schema": "vibe.skill_assay.analysis.v1",
        "hypotheses": [
            {
                "id": "h1",
                "claim": "loaded",
                "verdict": "pass",
                "evidence_refs": ["stability.stable_fields"],
                "doc_citations": [
                    {
                        "source": "official_docs",
                        "ref": "https://example.com",
                        "fetch_date": "2026-07-22",
                    }
                ],
            }
        ],
        "unknowns": [],
    }
    path = tmp_path / "analysis.json"
    path.write_text(json.dumps(analysis), encoding="utf-8")
    report = finalize_assay(repo_root=tmp_path, assay_id=assay_id, analysis_path=path)
    html = (tmp_path / "runtime/vibe-skill-assay" / assay_id / "OWNER_REPORT.html").read_text(
        encoding="utf-8"
    )
    assert "给人看" in html
    assert "Skill Assay 报告" in html
    packed = pack_assay(repo_root=tmp_path, assay_id=assay_id)
    zip_path = Path(packed["zip_path"])
    assert zip_path.is_file()
    with ZipFile(zip_path) as zf:
        names = zf.namelist()
    assert any(n.endswith("OWNER_REPORT.html") for n in names)
    assert any(n.endswith("AGENT_PACKET.json") for n in names)
    assert report["owner_html_relative"].endswith("OWNER_REPORT.html")
