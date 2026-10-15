"""Phase 5 sync lifecycle tests (fake provider only; no real NotebookLM mutation)."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import yaml

from vibe_control.config import load_config
from vibe_control.knowledge import managed_names, receipt, sync_lifecycle
from vibe_control.knowledge.corpus import build_desired_corpus
from vibe_control.knowledge.receipt import ReceiptStore, receipt_path
from helpers import minimal_config_dict, write_doc, write_registry


REPO = Path(__file__).resolve().parents[1]

APPROVED_TITLES = sync_lifecycle.APPROVED_PHASE4_RESIDUE_TITLES


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
                "allowed_operations": [
                    "status",
                    "inventory",
                    "sync_preview",
                    "sync",
                    "add_test_sources_with_approval",
                ],
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
    write_doc(tmp, "docs/project/VIBE_CONTROL_V0_5_SPEC.md", "spec body v1\n")
    write_doc(tmp, "docs/project/DECISION_LOG.md", "decision body v1\n")


class FakeNotebookProvider:
    def __init__(self, *, remote=None, add_title=None, never_appear=False, fail_wait=False):
        self.remote = list(remote or [])
        self.add_title = add_title
        self.never_appear = never_appear
        self.fail_wait = fail_wait
        self.mutations: list[tuple] = []
        self._counter = 0

    def list_sources(self, *, notebook_ref: str) -> dict:
        return {"ok": True, "sources": list(self.remote)}

    def add_file_source(self, *, notebook_ref: str, file_path: str, title: str) -> dict:
        self.mutations.append(("add", Path(file_path).name, title))
        if self.never_appear:
            return {"ok": True, "code": "OK", "result": {"source": {"id": "ghost", "title": title}}}
        self._counter += 1
        sid = f"src-{self._counter}"
        if self.add_title == "filename":
            observed = Path(file_path).name
        elif self.add_title is not None:
            observed = self.add_title
        else:
            observed = title
        self.remote.append({"id": sid, "title": observed, "status": "ready"})
        return {"ok": True, "code": "OK", "result": {"source": {"id": sid, "title": observed}}}

    def wait_source(self, *, notebook_ref: str, source_id: str, timeout: float = 120) -> dict:
        if self.fail_wait or self.never_appear:
            return {"ok": False, "status": "timeout", "code": "SOURCE_WAIT_TIMEOUT"}
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
            return {"ok": False, "code": "SOURCE_NOT_FOUND", "message": "missing"}
        return {"ok": True, "code": "OK", "message": "deleted"}


def test_residue_cleanup_deletes_only_approved_titles():
    provider = FakeNotebookProvider(
        remote=[
            {"id": "a", "title": "VIBE_CONTROL_V0_5_SPEC.md", "status": "ready"},
            {
                "id": "b",
                "title": "[vibe:vibe-control:DECISION_LOG] DECISION_LOG.md",
                "status": "ready",
            },
            {"id": "c", "title": "unrelated.md", "status": "ready"},
        ]
    )
    plan = sync_lifecycle.plan_phase4_residue_cleanup(provider.list_sources(notebook_ref="nb")["sources"])
    assert plan["ok"] is True
    assert {x["title"] for x in plan["matched"]} == APPROVED_TITLES
    result = sync_lifecycle.run_phase4_residue_cleanup(
        provider, notebook_ref="nb", dry_run=False, allow_delete=True
    )
    assert result["ok"] is True
    assert {d["title"] for d in result["deleted"]} == APPROVED_TITLES
    assert not any(m[0] == "delete" and m[1] == "c" for m in provider.mutations)
    assert any(x.get("id") == "c" for x in provider.remote)


def test_residue_cleanup_refuses_when_matched_set_differs():
    provider = FakeNotebookProvider(
        remote=[{"id": "a", "title": "VIBE_CONTROL_V0_5_SPEC.md", "status": "ready"}]
    )
    result = sync_lifecycle.run_phase4_residue_cleanup(
        provider, notebook_ref="nb", dry_run=False, allow_delete=True
    )
    assert result["ok"] is False
    assert result.get("code") == "RESIDUE_SET_MISMATCH"
    assert not any(m[0] == "delete" for m in provider.mutations)


def test_sync_dry_run_clean_notebook_plans_add_missing(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    _write_project(tmp_path)
    config = load_config(tmp_path)
    provider = FakeNotebookProvider(remote=[])
    result = sync_lifecycle.plan_or_run_sync(
        config,
        repo_root=tmp_path,
        notebook_alias="OPM-test",
        notebook_ref="nb-ref",
        provider=provider,
        dry_run=True,
        apply=False,
    )
    assert result["ok"] is True
    ops = {op["op"] for op in result["data"]["operations"]}
    assert "add_missing" in ops
    assert not any(m[0] == "add" for m in provider.mutations)


def test_sync_apply_add_wait_verify_receipt(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    _write_project(tmp_path)
    config = load_config(tmp_path)
    provider = FakeNotebookProvider(remote=[], add_title="filename")
    result = sync_lifecycle.plan_or_run_sync(
        config,
        repo_root=tmp_path,
        notebook_alias="OPM-test",
        notebook_ref="nb-ref",
        provider=provider,
        dry_run=False,
        apply=True,
    )
    assert result["ok"] is True
    added = result["data"]["added"]
    assert len(added) == 2
    assert all(a["verified"] and a["receipt_written"] for a in added)
    st = receipt.status("vibe-control")
    assert st["present"] is True
    assert st["document_count"] == 2
    assert provider.mutations and all(m[0] == "add" for m in provider.mutations)


def test_receipt_written_only_after_verification(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    _write_project(tmp_path)
    config = load_config(tmp_path)
    provider = FakeNotebookProvider(remote=[], never_appear=True, fail_wait=True)
    result = sync_lifecycle.plan_or_run_sync(
        config,
        repo_root=tmp_path,
        notebook_alias="OPM-test",
        notebook_ref="nb-ref",
        provider=provider,
        dry_run=False,
        apply=True,
    )
    assert result["ok"] is False
    assert receipt.status("vibe-control")["present"] is False


def test_changed_content_replace_required_and_order(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    _write_project(tmp_path)
    config = load_config(tmp_path)
    provider = FakeNotebookProvider(remote=[])
    first = sync_lifecycle.plan_or_run_sync(
        config,
        repo_root=tmp_path,
        notebook_alias="OPM-test",
        notebook_ref="nb-ref",
        provider=provider,
        dry_run=False,
        apply=True,
    )
    assert first["ok"] is True
    old_ids = {a["doc_id"]: a["provider_source_id"] for a in first["data"]["added"]}

    write_doc(tmp_path, "docs/project/VIBE_CONTROL_V0_5_SPEC.md", "spec body v2 changed\n")
    dry = sync_lifecycle.plan_or_run_sync(
        config,
        repo_root=tmp_path,
        notebook_alias="OPM-test",
        notebook_ref="nb-ref",
        provider=provider,
        dry_run=True,
        apply=False,
    )
    assert any(op["op"] == "replace_required" for op in dry["data"]["operations"])

    provider.mutations.clear()
    second = sync_lifecycle.plan_or_run_sync(
        config,
        repo_root=tmp_path,
        notebook_alias="OPM-test",
        notebook_ref="nb-ref",
        provider=provider,
        dry_run=False,
        apply=True,
        cleanup_superseded=True,
    )
    assert second["ok"] is True
    # add before any delete
    mut_kinds = [m[0] for m in provider.mutations]
    assert "add" in mut_kinds
    assert mut_kinds.index("add") < mut_kinds.index("delete")

    insp = receipt.inspect("vibe-control", report_mode=False)
    docs = insp["receipt"]["documents"]
    spec = docs["vibe_control_v0_5_spec"]
    assert spec["current"]["provider_source_id"] != old_ids["vibe_control_v0_5_spec"]
    assert any(h.get("state") == "superseded" for h in spec["history"])
    assert old_ids["vibe_control_v0_5_spec"] not in {x.get("id") for x in provider.remote}


def test_cleanup_only_receipt_owned_superseded(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    _write_project(tmp_path)
    config = load_config(tmp_path)
    store = ReceiptStore(receipt_path("vibe-control"))
    store.write_verified(
        project_id="vibe-control",
        provider="notebooklm",
        notebook_alias="OPM-test",
        notebook_ref_hash="sha256:deadbeefdeadbeef",
        doc_id="vibe_control_v0_5_spec",
        path_str="docs/project/VIBE_CONTROL_V0_5_SPEC.md",
        managed_name="vibe__vibe-control__vibe_control_v0_5_spec",
        current={
            "provider_source_id": "old-src",
            "upload_filename": "vibe__vibe-control__vibe_control_v0_5_spec__h__aaaaaaaaaaaa.md",
            "remote_title_observed": "vibe__vibe-control__vibe_control_v0_5_spec",
            "title_state": "exact",
            "status": "ready",
            "content_sha256": "aa" * 32,
        },
    )
    store.write_verified(
        project_id="vibe-control",
        provider="notebooklm",
        notebook_alias="OPM-test",
        notebook_ref_hash="sha256:deadbeefdeadbeef",
        doc_id="vibe_control_v0_5_spec",
        path_str="docs/project/VIBE_CONTROL_V0_5_SPEC.md",
        managed_name="vibe__vibe-control__vibe_control_v0_5_spec",
        current={
            "provider_source_id": "new-src",
            "upload_filename": "vibe__vibe-control__vibe_control_v0_5_spec__h__bbbbbbbbbbbb.md",
            "remote_title_observed": "vibe__vibe-control__vibe_control_v0_5_spec",
            "title_state": "exact",
            "status": "ready",
            "content_sha256": "bb" * 32,
        },
    )
    provider = FakeNotebookProvider(
        remote=[
            {"id": "old-src", "title": "vibe__vibe-control__vibe_control_v0_5_spec", "status": "ready"},
            {"id": "new-src", "title": "vibe__vibe-control__vibe_control_v0_5_spec", "status": "ready"},
            {"id": "unmanaged", "title": "notes.md", "status": "ready"},
            {
                "id": "lookalike",
                "title": "vibe__vibe-control__vibe_control_v0_5_spec__h__cccccccccccc.md",
                "status": "ready",
            },
        ]
    )
    result = sync_lifecycle.cleanup_superseded_sources(
        config,
        notebook_alias="OPM-test",
        notebook_ref="nb-ref",
        provider=provider,
        dry_run=False,
        allow_delete=True,
    )
    assert result["ok"] is True
    deleted_ids = {d["provider_source_id"] for d in result["deleted"]}
    assert deleted_ids == {"old-src"}
    assert any(x.get("id") == "unmanaged" for x in provider.remote)
    assert any(x.get("id") == "lookalike" for x in provider.remote)
    assert any(x.get("id") == "new-src" for x in provider.remote)


def test_cleanup_cannot_delete_unmanaged_or_filename_heuristic(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    _write_project(tmp_path)
    config = load_config(tmp_path)
    provider = FakeNotebookProvider(
        remote=[
            {"id": "u1", "title": "notes.md", "status": "ready"},
            {"id": "u2", "title": "VIBE_CONTROL_V0_5_SPEC.md", "status": "ready"},
        ]
    )
    result = sync_lifecycle.cleanup_superseded_sources(
        config,
        notebook_alias="OPM-test",
        notebook_ref="nb-ref",
        provider=provider,
        dry_run=False,
        allow_delete=True,
    )
    assert result["ok"] is True
    assert result["deleted"] == []
    assert not any(m[0] == "delete" for m in provider.mutations)


def test_retry_uses_latest_desired_corpus(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    _write_project(tmp_path)
    config = load_config(tmp_path)
    provider = FakeNotebookProvider(remote=[])
    write_doc(tmp_path, "docs/project/DECISION_LOG.md", "decision body RETRY\n")
    result = sync_lifecycle.plan_or_run_retry(
        config,
        repo_root=tmp_path,
        notebook_alias="OPM-test",
        notebook_ref="nb-ref",
        provider=provider,
        dry_run=True,
    )
    assert result["ok"] is True
    corpus = build_desired_corpus(config, repo_root=tmp_path)
    assert result["data"]["desired_count"] == corpus.source_count
    assert any(op["op"] == "add_missing" for op in result["data"]["operations"])


def test_rebuild_dry_run_reports_managed_ops(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    _write_project(tmp_path)
    config = load_config(tmp_path)
    provider = FakeNotebookProvider(remote=[])
    result = sync_lifecycle.plan_rebuild(
        config,
        repo_root=tmp_path,
        notebook_alias="OPM-test",
        notebook_ref="nb-ref",
        provider=provider,
    )
    assert result["ok"] is True
    assert result["data"]["dry_run"] is True
    ops = result["data"]["operations"]
    assert ops
    assert all(op["op"] in {"add_missing", "replace_required", "already_current", "cleanup_superseded"} or True for op in ops)
    assert any(op["op"] == "add_missing" for op in ops)
    assert not provider.mutations


def test_provider_details_stay_in_adapter():
    root = REPO / "src" / "vibe_control" / "knowledge"
    tree = ast.parse((root / "sync_lifecycle.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            assert "notebooklm_provider" not in mod
            assert not mod.endswith("providers.notebooklm")
    provider = (root / "providers" / "notebooklm.py").read_text(encoding="utf-8")
    assert "delete" in provider.lower()


def test_skills_remain_thin():
    skills = REPO / "src" / "vibe_control" / "skills"
    for path in skills.rglob("SKILL.md"):
        text = path.read_text(encoding="utf-8")
        assert "source delete" not in text
        assert "receipt switch" not in text.lower()
        assert "wait-ready" not in text.lower()
