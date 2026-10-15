"""Phase 6 real replace smoke tests (fake provider; no real NotebookLM mutation)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

from vibe_control.cli import build_parser
from vibe_control.config import load_config
from vibe_control.knowledge import managed_names, receipt, replace_smoke
from vibe_control.knowledge.receipt import ReceiptStore, receipt_path
from helpers import minimal_config_dict, write_doc, write_registry


REPO = Path(__file__).resolve().parents[1]


def _cfg_dict() -> dict:
    raw = minimal_config_dict(
        include_extra=["docs/project/DECISION_LOG.md"],
        max_sources=20,
        warn_sources=15,
    )
    raw["project"] = {"id": "vibe-control", "name": "Vibe Control"}
    raw["knowledge"]["notebooks"] = {
        "default_alias": "OPM-test",
        "allow_list": [
            {
                "alias": "OPM-test",
                "display_name": "OPM-test",
                "ref_env": "NOTEBOOKLM_NOTEBOOK_OPM_TEST",
                "allowed_operations": ["status", "inventory", "sync", "smoke"],
            }
        ],
    }
    return raw


def _write_project(tmp: Path) -> None:
    cfg = tmp / ".config" / "vibe-control.yaml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(yaml.safe_dump(_cfg_dict()), encoding="utf-8")
    write_registry(
        tmp,
        [
            {
                "id": "vibe_control_v0_5_spec",
                "title": "Vibe Control v0.5 Spec",
                "status": "active",
                "path": "docs/project/VIBE_CONTROL_V0_5_SPEC.md",
            }
        ],
    )
    write_doc(tmp, "docs/project/VIBE_CONTROL_V0_5_SPEC.md", "spec body\n")
    write_doc(tmp, "docs/project/DECISION_LOG.md", "decision body\n")


class FakeNotebookProvider:
    def __init__(self, *, remote=None):
        self.remote = list(remote or [])
        self.mutations: list[tuple] = []
        self._counter = 0

    def list_sources(self, *, notebook_ref: str) -> dict:
        return {"ok": True, "sources": list(self.remote)}

    def add_file_source(self, *, notebook_ref: str, file_path: str, title: str) -> dict:
        self.mutations.append(("add", Path(file_path).name, title))
        self._counter += 1
        sid = f"smoke-{self._counter}"
        observed = title
        self.remote.append({"id": sid, "title": observed, "status": "ready"})
        return {"ok": True, "code": "OK", "result": {"source": {"id": sid, "title": observed}}}

    def wait_source(self, *, notebook_ref: str, source_id: str, timeout: float = 120) -> dict:
        return {"ok": True, "status": "ready"}

    def get_source(self, *, notebook_ref: str, source_id: str) -> dict:
        for item in self.remote:
            if item.get("id") == source_id:
                return {"ok": True, "found": True, "source": item}
        return {"ok": False, "found": False, "status": "not_found"}

    def delete_source(self, *, notebook_ref: str, source_id: str) -> dict:
        self.mutations.append(("delete", source_id))
        before = len(self.remote)
        self.remote = [x for x in self.remote if x.get("id") != source_id]
        if len(self.remote) == before:
            return {"ok": False, "code": "SOURCE_NOT_FOUND"}
        return {"ok": True, "code": "OK"}


def test_smoke_command_is_internal_in_help():
    text = (REPO / "src/vibe_control/cli.py").read_text(encoding="utf-8")
    assert "smoke" in text
    assert "INTERNAL" in text or "ACCEPTANCE" in text
    parser = build_parser()
    ns = parser.parse_args(["knowledge", "smoke", "replace", "--dry-run", "--json"])
    assert getattr(ns, "apply", False) is False


def test_smoke_dry_run_no_mutation(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    _write_project(tmp_path)
    config = load_config(tmp_path)
    provider = FakeNotebookProvider(
        remote=[
            {"id": "real-1", "title": "vibe__vibe-control__vibe_control_v0_5_spec", "status": "ready"},
            {"id": "real-2", "title": "vibe__vibe-control__decision_log", "status": "ready"},
        ]
    )
    result = replace_smoke.plan_or_run(
        config,
        notebook_alias="OPM-test",
        notebook_ref="nb-ref",
        provider=provider,
        dry_run=True,
        apply=False,
        cleanup=False,
        home=tmp_path / "home",
    )
    assert result["ok"] is True
    assert result["data"]["dry_run"] is True
    assert provider.mutations == []


def test_smoke_apply_requires_apply_flag(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    _write_project(tmp_path)
    config = load_config(tmp_path)
    provider = FakeNotebookProvider(remote=[])
    result = replace_smoke.plan_or_run(
        config,
        notebook_alias="OPM-test",
        notebook_ref="nb-ref",
        provider=provider,
        dry_run=False,
        apply=False,
        cleanup=False,
        home=tmp_path / "home",
    )
    assert result["ok"] is False
    assert result.get("code") == "SMOKE_REQUIRES_APPLY_OR_DRY_RUN"


def test_cleanup_requires_cleanup_flag_semantics(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    _write_project(tmp_path)
    config = load_config(tmp_path)
    # With apply but without cleanup: leaves final smoke current in place
    provider = FakeNotebookProvider(
        remote=[
            {"id": "real-1", "title": "vibe__vibe-control__vibe_control_v0_5_spec", "status": "ready"},
            {"id": "real-2", "title": "vibe__vibe-control__decision_log", "status": "ready"},
        ]
    )
    result = replace_smoke.plan_or_run(
        config,
        notebook_alias="OPM-test",
        notebook_ref="nb-ref",
        provider=provider,
        dry_run=False,
        apply=True,
        cleanup=False,
        home=tmp_path / "home",
    )
    assert result["ok"] is True
    assert result["data"]["final_smoke_deleted"] is False
    titles = {x.get("title") for x in provider.remote}
    assert managed_names.managed_name("vibe-control", replace_smoke.SMOKE_DOC_ID) in titles


def test_smoke_uses_isolated_receipt_not_production(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    _write_project(tmp_path)
    config = load_config(tmp_path)
    # Seed production receipt
    prod = ReceiptStore(receipt_path("vibe-control", home=tmp_path / "home"))
    prod.write_verified(
        project_id="vibe-control",
        provider="notebooklm",
        notebook_alias="OPM-test",
        notebook_ref_hash="sha256:deadbeefdeadbeef",
        doc_id="vibe_control_v0_5_spec",
        path_str="docs/project/VIBE_CONTROL_V0_5_SPEC.md",
        managed_name="vibe__vibe-control__vibe_control_v0_5_spec",
        current={"provider_source_id": "real-1", "content_sha256": "aa" * 32, "status": "ready"},
    )
    provider = FakeNotebookProvider(
        remote=[
            {"id": "real-1", "title": "vibe__vibe-control__vibe_control_v0_5_spec", "status": "ready"},
            {"id": "real-2", "title": "vibe__vibe-control__decision_log", "status": "ready"},
        ]
    )
    result = replace_smoke.plan_or_run(
        config,
        notebook_alias="OPM-test",
        notebook_ref="nb-ref",
        provider=provider,
        dry_run=False,
        apply=True,
        cleanup=True,
        home=tmp_path / "home",
    )
    assert result["ok"] is True
    smoke_path = replace_smoke.smoke_receipt_path("vibe-control", home=tmp_path / "home")
    assert smoke_path != receipt_path("vibe-control", home=tmp_path / "home")
    # production receipt untouched document set
    prod_data = ReceiptStore(receipt_path("vibe-control", home=tmp_path / "home")).load()
    assert set(prod_data["documents"]) == {"vibe_control_v0_5_spec"}
    assert replace_smoke.SMOKE_DOC_ID not in prod_data["documents"]


def test_v1_v2_hashes_differ_and_replace_order(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    _write_project(tmp_path)
    config = load_config(tmp_path)
    provider = FakeNotebookProvider(
        remote=[
            {"id": "real-1", "title": "vibe__vibe-control__vibe_control_v0_5_spec", "status": "ready"},
            {"id": "real-2", "title": "vibe__vibe-control__decision_log", "status": "ready"},
        ]
    )
    result = replace_smoke.plan_or_run(
        config,
        notebook_alias="OPM-test",
        notebook_ref="nb-ref",
        provider=provider,
        dry_run=False,
        apply=True,
        cleanup=True,
        home=tmp_path / "home",
    )
    assert result["ok"] is True
    data = result["data"]
    assert data["v1"]["content_sha256"] != data["v2"]["content_sha256"]
    kinds = [m[0] for m in provider.mutations]
    # add v1, add v2, delete v1, delete v2
    assert kinds.count("add") == 2
    assert kinds.index("add") < kinds.index("delete")
    first_delete = kinds.index("delete")
    assert kinds[:first_delete].count("add") == 2
    assert data["v1"]["provider_source_id"] != data["v2"]["provider_source_id"]
    assert data["receipt_switched"] is True
    assert data["v1_superseded"] is True
    assert data["superseded_deleted"] is True
    assert data["final_smoke_deleted"] is True


def test_cleanup_refuses_unmanaged_and_protected(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    _write_project(tmp_path)
    config = load_config(tmp_path)
    provider = FakeNotebookProvider(
        remote=[
            {"id": "real-1", "title": "vibe__vibe-control__vibe_control_v0_5_spec", "status": "ready"},
            {"id": "u1", "title": "notes.md", "status": "ready"},
        ]
    )
    # Attempt direct unsafe delete helpers
    refused = replace_smoke.safe_delete_smoke_source(
        provider,
        notebook_ref="nb-ref",
        source_id="real-1",
        allowed_ids={"smoke-only"},
        protected_ids={"real-1"},
    )
    assert refused["ok"] is False
    refused2 = replace_smoke.safe_delete_smoke_source(
        provider,
        notebook_ref="nb-ref",
        source_id="u1",
        allowed_ids={"smoke-only"},
        protected_ids={"real-1"},
    )
    assert refused2["ok"] is False
    assert not any(m[0] == "delete" for m in provider.mutations)


def test_cleanup_refuses_title_prefix_bulk():
    assert replace_smoke.allows_title_prefix_bulk_delete() is False


def test_final_inventory_requires_original_managed(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    _write_project(tmp_path)
    config = load_config(tmp_path)
    provider = FakeNotebookProvider(
        remote=[
            {"id": "real-1", "title": "vibe__vibe-control__vibe_control_v0_5_spec", "status": "ready"},
            {"id": "real-2", "title": "vibe__vibe-control__decision_log", "status": "ready"},
        ]
    )
    result = replace_smoke.plan_or_run(
        config,
        notebook_alias="OPM-test",
        notebook_ref="nb-ref",
        provider=provider,
        dry_run=False,
        apply=True,
        cleanup=True,
        home=tmp_path / "home",
    )
    assert result["ok"] is True
    final_titles = set(result["data"]["final_inventory_titles"])
    assert "vibe__vibe-control__vibe_control_v0_5_spec" in final_titles
    assert "vibe__vibe-control__decision_log" in final_titles
    assert managed_names.managed_name("vibe-control", replace_smoke.SMOKE_DOC_ID) not in final_titles


def test_smoke_content_versions_differ():
    v1 = replace_smoke.SMOKE_CONTENT_V1.encode("utf-8")
    v2 = replace_smoke.SMOKE_CONTENT_V2.encode("utf-8")
    assert hashlib.sha256(v1).hexdigest() != hashlib.sha256(v2).hexdigest()
    assert "v1" in replace_smoke.SMOKE_CONTENT_V1
    assert "v2" in replace_smoke.SMOKE_CONTENT_V2


def test_phase6_report_has_no_raw_source_ids():
    import re

    report = (REPO / "acceptance/phase6/PHASE6_REAL_REPLACE_SMOKE_REPORT.md").read_text(
        encoding="utf-8"
    )
    assert "phase6_replace_smoke" in report
    assert "already_current=2" in report or "already_current=2" in report.replace(" ", "")
    assert '"provider_source_id"' not in report
    assert not re.search(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        report,
        re.I,
    )
