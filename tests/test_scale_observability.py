"""Scale observability: last-sync-report + status/dry-run scale fields."""

from __future__ import annotations

import json
from pathlib import Path

from helpers import minimal_config_dict, write_control_yaml, write_doc, write_registry
from vibe_control.cli import main
from vibe_control.config import load_config
from vibe_control.knowledge.ack_stores import LocalMirrorAckStore
from vibe_control.knowledge.pending_sync import write_pending_sync
from vibe_control.knowledge.phase8_apply import apply_forward_sync, plan_forward_sync_dry_run
from vibe_control.knowledge.provider_target import ProviderTarget
from vibe_control.knowledge.scale_observability import (
    build_scale_observability,
    load_last_sync_report,
    write_last_sync_report,
)


def test_build_scale_observability_pending_and_report(tmp_path: Path):
    target = ProviderTarget.from_ref(
        provider="notebooklm", notebook_alias="OPM-test", notebook_ref="nb-scale"
    )
    write_pending_sync(
        "migration-harness",
        target,
        reason="ADD_FAILED",
        home=tmp_path,
        failed_doc_id="doc_a",
        elapsed_ms=1234,
        op="add",
    )
    write_last_sync_report(
        "migration-harness",
        target,
        ok=False,
        code="ADD_FAILED",
        message="add failed",
        desired_count=3,
        receipt_item_count=1,
        updated_or_attempted=1,
        elapsed_ms=1234,
        failed_doc_id="doc_a",
        home=tmp_path,
    )
    scale = build_scale_observability(
        project_id="migration-harness",
        target=target,
        desired_count=3,
        receipt_item_count=1,
        required_updates_count=2,
        probe={"missing": ["doc_b"], "unready": []},
        home=tmp_path,
    )
    assert scale["schema"] == "vibe.knowledge.scale.v1"
    assert scale["desired_count"] == 3
    assert scale["required_updates_count"] == 2
    assert scale["probe_missing_count"] == 1
    assert scale["probe_unready_count"] == 0
    assert scale["pending_sync"]["present"] is True
    assert scale["pending_sync"]["failed_doc_id"] == "doc_a"
    assert scale["pending_sync"]["elapsed_ms"] == 1234
    assert scale["last_sync_report"]["ok"] is False
    assert scale["last_sync_report"]["code"] == "ADD_FAILED"
    assert scale["mutation"] is False


def test_apply_writes_last_sync_report_on_success(tmp_path: Path, monkeypatch):
    raw = minimal_config_dict(max_sources=20, warn_sources=15, enable_knowledge=True)
    raw["knowledge"]["notebooks"] = {
        "default_alias": "OPM-test",
        "allow_list": [
            {
                "alias": "OPM-test",
                "display_name": "OPM-test",
                "ref_env": "NOTEBOOKLM_NOTEBOOK_OPM_TEST",
                "allowed_operations": ["status", "sync"],
            }
        ],
    }
    write_control_yaml(tmp_path, raw)
    write_registry(tmp_path, [{"id": "s1", "status": "active", "path": "docs/a.md"}])
    write_doc(tmp_path, "docs/a.md", "# A\n")
    monkeypatch.setenv("NOTEBOOKLM_NOTEBOOK_OPM_TEST", "nb-scale-ok")
    config = load_config(tmp_path)
    target = ProviderTarget.from_ref(
        provider="notebooklm", notebook_alias="OPM-test", notebook_ref="nb-scale-ok"
    )

    class OkProvider:
        def __init__(self) -> None:
            self.sources: list[dict] = []
            self._n = 0

        def list_sources(self, *, notebook_ref: str) -> dict:
            return {"ok": True, "sources": list(self.sources)}

        def add_file_source(self, *, notebook_ref: str, file_path: str, title: str) -> dict:
            self._n += 1
            sid = f"src-{self._n}"
            self.sources.append({"id": sid, "title": title, "status": "ready"})
            return {"ok": True, "result": {"source": {"id": sid, "title": title}}}

        def wait_source(self, *, notebook_ref: str, source_id: str, timeout: float = 120) -> dict:
            return {"ok": True, "status": "ready"}

        def delete_source(self, *, notebook_ref: str, source_id: str) -> dict:
            self.sources = [s for s in self.sources if s.get("id") != source_id]
            return {"ok": True}

        def get_source(self, *, notebook_ref: str, source_id: str) -> dict:
            for s in self.sources:
                if s.get("id") == source_id:
                    return {"ok": True, "found": True, "source": s}
            return {"ok": False, "found": False}

    provider = OkProvider()
    result = apply_forward_sync(
        config,
        repo_root=tmp_path,
        target=target,
        notebook_ref="nb-scale-ok",
        provider=provider,
        ack_store=LocalMirrorAckStore(config.project_id, home=tmp_path),
        home=tmp_path,
        command="vibe knowledge sync --apply",
    )
    assert result["ok"] is True
    assert result["scale"]["desired_count"] == 1
    assert result["elapsed_ms"] is not None
    report = load_last_sync_report(config.project_id, target, home=tmp_path)
    assert report is not None
    assert report["ok"] is True
    assert report["code"] == "SYNCED"
    assert report["desired_count"] == 1


def test_dry_run_includes_scale(tmp_path: Path, monkeypatch):
    raw = minimal_config_dict(max_sources=20, warn_sources=15, enable_knowledge=True)
    raw["knowledge"]["notebooks"] = {
        "default_alias": "OPM-test",
        "allow_list": [
            {
                "alias": "OPM-test",
                "display_name": "OPM-test",
                "ref_env": "NOTEBOOKLM_NOTEBOOK_OPM_TEST",
                "allowed_operations": ["status", "sync"],
            }
        ],
    }
    write_control_yaml(tmp_path, raw)
    write_registry(tmp_path, [{"id": "s1", "status": "active", "path": "docs/a.md"}])
    write_doc(tmp_path, "docs/a.md", "# A\n")
    monkeypatch.setenv("NOTEBOOKLM_NOTEBOOK_OPM_TEST", "nb-scale-dry")
    config = load_config(tmp_path)
    target = ProviderTarget.from_ref(
        provider="notebooklm", notebook_alias="OPM-test", notebook_ref="nb-scale-dry"
    )

    class DryProvider:
        def list_sources(self, *, notebook_ref: str) -> dict:
            return {"ok": True, "sources": []}

        def add_file_source(self, *, notebook_ref: str, file_path: str, title: str) -> dict:
            raise AssertionError("dry-run must not mutate")

        def delete_source(self, *, notebook_ref: str, source_id: str) -> dict:
            raise AssertionError("dry-run must not mutate")

        def wait_source(self, *, notebook_ref: str, source_id: str, timeout: float = 120) -> dict:
            raise AssertionError("dry-run must not mutate")

    dry = plan_forward_sync_dry_run(
        config,
        repo_root=tmp_path,
        target=target,
        notebook_ref="nb-scale-dry",
        provider=DryProvider(),
        ack_store=LocalMirrorAckStore(config.project_id, home=tmp_path),
        home=tmp_path,
    )
    assert dry["ok"] is True
    scale = dry["scale"]
    assert scale["schema"] == "vibe.knowledge.scale.v1"
    assert scale["desired_count"] == 1
    assert scale["required_updates_count"] >= 1
    assert scale["mutation"] is False


def test_knowledge_status_includes_scale(tmp_path: Path, monkeypatch, capsys):
    from vibe_control.knowledge.phase8_runtime import reset_runtime

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
    scale = (payload.get("data") or {}).get("scale") or {}
    assert scale.get("schema") == "vibe.knowledge.scale.v1"
    assert scale.get("desired_count") == 1
    assert scale.get("mutation") is False
    reset_runtime()
