"""Foundation TDD: agent-surface disclosure must be visible on knowledge surfaces."""

from __future__ import annotations

import json
from pathlib import Path

from helpers import minimal_config_dict, write_control_yaml, write_doc, write_registry
from vibe_control.agent_surface import (
    DISCLOSURE_SCHEMA,
    REQUIRED_KNOWLEDGE_OPERATION_IDS,
    assert_disclosure_shape,
    collect_operation_disclosures,
    knowledge_sync_disclosure,
)
from vibe_control.cli import main
from vibe_control.knowledge.phase8_runtime import reset_runtime

ROOT = Path(__file__).resolve().parents[1]


def test_knowledge_sync_disclosure_shape():
    block = knowledge_sync_disclosure(continue_flag_available=True)
    assert assert_disclosure_shape(block) == []
    assert block["schema"] == DISCLOSURE_SCHEMA
    assert block["default"] == "fail_stop"
    assert block["agent_can_choose"] is True
    by_id = {c["id"]: c for c in block["choices"]}
    assert by_id["partial_continue"]["available"] is True
    assert "--continue-on-item-error" in str(by_id["partial_continue"]["how"])
    assert by_id["batch_size"]["available"] is True
    assert "--batch-size" in str(by_id["batch_size"]["how"])
    assert by_id["wait_mode_multi"]["available"] is True
    assert "--wait-mode multi" in str(by_id["wait_mode_multi"]["how"])
    assert by_id["ingest_path_api"]["available"] is True
    assert "--ingest-path api" in str(by_id["ingest_path_api"]["how"])
    assert by_id["upload_concurrency"]["available"] is True
    assert "--upload-concurrency" in str(by_id["upload_concurrency"]["how"])
    assert "concurrent" in block["summary"].lower() or "multi-file" in block["summary"].lower()


def test_disclosure_contract_doc_exists():
    text = (ROOT / "docs/harness/agent-surface-disclosure-contract.md").read_text(encoding="utf-8")
    assert "vibe.agent_surface.operation_disclosure.v1" in text
    assert "base capability" in text.lower() or "foundational" in text.lower()


def test_knowledge_status_exposes_sync_disclosure(tmp_path, monkeypatch, capsys):
    raw = minimal_config_dict(max_sources=20, warn_sources=15, enable_knowledge=True)
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
    monkeypatch.setenv("VIBE_PHASE8_FAKE_PROVIDER", "readonly")
    reset_runtime()

    code = main(["knowledge", "status", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code in (0, 1)
    assert payload.get("ok") is True
    found = collect_operation_disclosures(payload)
    for op_id in REQUIRED_KNOWLEDGE_OPERATION_IDS:
        assert op_id in found, f"missing disclosure for {op_id}"
        assert assert_disclosure_shape(found[op_id]) == []
    scale = (payload.get("data") or {}).get("scale") or {}
    assert assert_disclosure_shape(scale.get("sync_policy")) == []
    reset_runtime()


def test_cli_help_mentions_continue_flag():
    import vibe_control.cli as cli_mod

    # argparse help text is defined on the sync parser
    text = Path(cli_mod.__file__).read_text(encoding="utf-8")
    assert "--continue-on-item-error" in text
    assert "--batch-size" in text
    assert "--wait-mode" in text
    assert "--ingest-path" in text
    assert "--upload-concurrency" in text
    assert "fail_stop" in text or "partial continue" in text.lower()
