"""Source quota honesty helpers (NotebookLM plan caps vs knowledge.max_sources)."""

from __future__ import annotations

import json

from helpers import minimal_config_dict, write_control_yaml, write_doc, write_registry
from vibe_control.cli import main
from vibe_control.knowledge.source_quota import (
    DEFAULT_MAX_SOURCES,
    STANDARD_SOURCES_CAP,
    assess_source_quota,
)


def test_defaults_align_with_standard_cap():
    assert DEFAULT_MAX_SOURCES == STANDARD_SOURCES_CAP == 50


def test_assess_warns_when_max_exceeds_standard():
    out = assess_source_quota(max_sources=100, warn_sources=80, desired_count=2)
    assert out["max_sources_exceeds_standard"] is True
    assert "MAX_SOURCES_EXCEEDS_NOTEBOOKLM_STANDARD" in out["codes"]
    assert any("Standard cap" in w for w in out["warnings"])
    assert out["mutation"] is False


def test_assess_quiet_when_within_standard():
    out = assess_source_quota(max_sources=20, warn_sources=15, desired_count=2)
    assert out["max_sources_exceeds_standard"] is False
    assert "MAX_SOURCES_EXCEEDS_NOTEBOOKLM_STANDARD" not in out["codes"]


def test_assess_desired_near_warn():
    out = assess_source_quota(max_sources=50, warn_sources=10, desired_count=10)
    assert "DESIRED_NEAR_WARN_SOURCES" in out["codes"]


def test_assess_remote_over_standard():
    out = assess_source_quota(
        max_sources=50,
        warn_sources=40,
        desired_count=5,
        remote_source_count=50,
    )
    assert "REMOTE_NEAR_OR_OVER_STANDARD_CAP" in out["codes"]


def test_knowledge_doctor_includes_source_quota(tmp_path, monkeypatch, capsys):
    raw = minimal_config_dict(max_sources=100, warn_sources=80, enable_knowledge=True)
    raw["knowledge"]["notebooks"] = {
        "default_alias": "OPM-test",
        "allow_list": [
            {
                "alias": "OPM-test",
                "display_name": "OPM-test",
                "ref_env": "NOTEBOOKLM_NOTEBOOK_OPM_TEST",
                "allowed_operations": ["status"],
            }
        ],
    }
    write_control_yaml(tmp_path, raw)
    write_registry(tmp_path, [{"id": "s1", "status": "active", "path": "docs/a.md"}])
    write_doc(tmp_path, "docs/a.md", "# A\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NOTEBOOKLM_NOTEBOOK_OPM_TEST", "fake-ref")

    code = main(["knowledge", "doctor", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code in (0, 1)
    assert payload["ok"] is True or payload.get("error")
    # Doctor returns success_envelope when ok; failure otherwise — either way data carries quota
    data = payload.get("data") or (payload.get("error") or {}).get("details") or {}
    quota = data.get("source_quota") or {}
    assert quota.get("max_sources") == 100
    assert quota.get("max_sources_exceeds_standard") is True
    assert any("Standard cap" in w for w in (payload.get("warnings") or []))
