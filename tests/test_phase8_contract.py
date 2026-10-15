"""Phase 8.0 contract tests (Test Spec IDs). Fake provider only."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vibe_control.knowledge.pending_sync import (
    clear_pending_sync,
    pending_sync_exists,
    write_pending_sync,
)
from vibe_control.knowledge.provider_target import ProviderTarget
from vibe_control.knowledge.receipt_scope import pending_sync_path, scoped_receipt_path
from vibe_control.knowledge.remote_ack import FakeAckStore, read_ack
from vibe_control.knowledge.snapshot import binding_hash
from vibe_control.knowledge.sync_lifecycle_phase8 import (
    replace_item_with_receipt_switch,
    safe_delete_binding,
)
from vibe_control.knowledge.sync_status import evaluate_sync_status
from vibe_control.knowledge.managed_names import content_sha256_bytes, managed_name, upload_filename
from vibe_control.knowledge.reindex_bindings import reindex_bindings
from vibe_control.knowledge.snapshot import DesiredSnapshot, SnapshotItem


def _target(ref: str, alias: str = "OPM-test") -> ProviderTarget:
    return ProviderTarget.from_ref(
        provider="notebooklm", notebook_alias=alias, notebook_ref=ref
    )


class FakeListProvider:
    def __init__(self, sources=None, *, fail=False):
        self.sources = list(sources or [])
        self.fail = fail
        self.listed: list[str] = []
        self.mutations: list[tuple] = []

    def list_sources(self, *, notebook_ref: str) -> dict:
        self.listed.append(notebook_ref)
        if self.fail:
            raise RuntimeError("provider unavailable")
        return {"ok": True, "sources": list(self.sources)}

    def status(self) -> dict:
        if self.fail:
            return {"available": False, "code": "NOTEBOOKLM_UNAVAILABLE"}
        return {"available": True}


class FakeLifecycleProvider(FakeListProvider):
    def __init__(self, sources=None, *, verify_fail=False, delete_fail=False):
        super().__init__(sources)
        self.verify_fail = verify_fail
        self.delete_fail = delete_fail
        self._n = 0

    def add_file_source(self, *, notebook_ref: str, file_path: str, title: str) -> dict:
        self._n += 1
        sid = f"src-new-{self._n}"
        name = Path(file_path).name
        if not self.verify_fail:
            self.sources.append({"id": sid, "title": name, "status": "ready"})
        self.mutations.append(("add", sid))
        return {"ok": True, "result": {"source": {"id": sid, "title": name}}}

    def wait_source(self, *, notebook_ref: str, source_id: str, timeout: float = 120) -> dict:
        if self.verify_fail:
            return {"ok": False, "status": "timeout"}
        return {"ok": True, "status": "ready"}

    def get_source(self, *, notebook_ref: str, source_id: str) -> dict:
        if self.verify_fail:
            return {"ok": False, "found": False}
        for item in self.sources:
            if item.get("id") == source_id:
                return {"ok": True, "found": True, "source": item}
        return {"ok": False, "found": False}

    def delete_source(self, *, notebook_ref: str, source_id: str) -> dict:
        self.mutations.append(("delete", source_id))
        if self.delete_fail:
            return {"ok": False, "code": "DELETE_FAILED"}
        self.sources = [x for x in self.sources if x.get("id") != source_id]
        return {"ok": True}


@pytest.mark.unit
def test_P8_TARGET_01_same_source_id_different_targets_not_same_binding():
    a = _target("nb-a")
    b = _target("nb-b")
    assert a.target_key_hash != b.target_key_hash
    row_a = {
        "target_key_hash": a.target_key_hash,
        "doc_id": "doc",
        "content_sha256": "sha256:" + "a" * 64,
        "upload_hash": "a" * 12,
        "source_id_hash": "sha256:same",
        "ready": True,
    }
    row_b = dict(row_a)
    row_b["target_key_hash"] = b.target_key_hash
    assert binding_hash([row_a]) != binding_hash([row_b])


@pytest.mark.integration
def test_P8_STATUS_03_duplicate_managed_is_drift(tmp_path: Path):
    target = _target("nb-dup")
    item = SnapshotItem(doc_id="doc", path="d.md", content_sha256="sha256:" + "1" * 64)
    desired = DesiredSnapshot(
        project_id="p",
        sync_scope="ssot_files",
        items=[item],
        item_count=1,
        item_hashes_hash="sha256:x",
        snapshot_hash="sha256:y",
    )
    mname = managed_name("p", "doc")
    fname = upload_filename(mname, "1" * 64)
    binding = {
        "doc_id": "doc",
        "content_sha256": item.content_sha256,
        "upload_hash": "1" * 12,
        "upload_filename": fname,
        "managed_name": mname,
        "provider_source_id": "src-1",
        "source_id_hash": "sha256:s1",
        "ready": True,
    }
    receipt = scoped_receipt_path("p", target, home=tmp_path)
    receipt.parent.mkdir(parents=True)
    receipt.write_text(
        json.dumps(
            {
                "provider_target": target.to_dict(),
                "items": {"doc": binding},
                "cleanup_pending": [],
            }
        ),
        encoding="utf-8",
    )
    ack = {
        "target_key_hash": target.target_key_hash,
        "snapshot_hash": desired.snapshot_hash,
        "item_hashes_hash": desired.item_hashes_hash,
        "binding_hash": "sha256:ignored",
    }
    provider = FakeListProvider(
        [
            {"id": "src-1", "title": fname, "status": "ready"},
            {"id": "src-2", "title": fname, "status": "ready"},
        ]
    )
    status = evaluate_sync_status(
        project_id="p",
        target=target,
        desired=desired,
        remote_ack=ack,
        provider=provider,
        notebook_ref="nb-dup",
        home=tmp_path,
    )
    assert status["sync_state"] != "synced"
    assert status["sync_state"] in {"drift", "pending"}


@pytest.mark.integration
def test_P8_STATUS_04_unready_not_synced(tmp_path: Path):
    target = _target("nb-unready")
    item = SnapshotItem(doc_id="doc", path="d.md", content_sha256="sha256:" + "1" * 64)
    desired = DesiredSnapshot(
        project_id="p",
        sync_scope="ssot_files",
        items=[item],
        item_count=1,
        item_hashes_hash="sha256:x",
        snapshot_hash="sha256:y",
    )
    mname = managed_name("p", "doc")
    fname = upload_filename(mname, "1" * 64)
    binding = {
        "doc_id": "doc",
        "content_sha256": item.content_sha256,
        "upload_hash": "1" * 12,
        "upload_filename": fname,
        "managed_name": mname,
        "provider_source_id": "src-1",
        "source_id_hash": "sha256:s1",
        "ready": True,
    }
    path = scoped_receipt_path("p", target, home=tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"provider_target": target.to_dict(), "items": {"doc": binding}}),
        encoding="utf-8",
    )
    ack = {
        "target_key_hash": target.target_key_hash,
        "snapshot_hash": desired.snapshot_hash,
        "item_hashes_hash": desired.item_hashes_hash,
        "binding_hash": "sha256:z",
    }
    provider = FakeListProvider([{"id": "src-1", "title": fname, "status": "processing"}])
    status = evaluate_sync_status(
        project_id="p",
        target=target,
        desired=desired,
        remote_ack=ack,
        provider=provider,
        notebook_ref="nb-unready",
        home=tmp_path,
    )
    assert status["sync_state"] != "synced"


@pytest.mark.integration
def test_P8_STATUS_05_pending_marker_reports_pending(tmp_path: Path):
    target = _target("nb-pend")
    write_pending_sync(
        "p",
        target,
        reason="NOTEBOOKLM_UNAVAILABLE",
        home=tmp_path,
    )
    assert pending_sync_exists("p", target, home=tmp_path)
    desired = DesiredSnapshot(
        project_id="p",
        sync_scope="ssot_files",
        items=[],
        item_count=0,
        item_hashes_hash="sha256:" + "0" * 64,
        snapshot_hash="sha256:" + "1" * 64,
    )
    # empty receipt still missing -> pending should win or at least not synced
    path = scoped_receipt_path("p", target, home=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"provider_target": target.to_dict(), "items": {}, "cleanup_pending": []}),
        encoding="utf-8",
    )
    status = evaluate_sync_status(
        project_id="p",
        target=target,
        desired=desired,
        remote_ack={
            "target_key_hash": target.target_key_hash,
            "snapshot_hash": desired.snapshot_hash,
            "item_hashes_hash": desired.item_hashes_hash,
            "binding_hash": binding_hash([]),
        },
        provider=FakeListProvider([]),
        notebook_ref="nb-pend",
        home=tmp_path,
    )
    assert status["sync_state"] == "pending"


@pytest.mark.integration
def test_P8_STATUS_06_provider_unavailable_no_crash(tmp_path: Path):
    target = _target("nb-down")
    path = scoped_receipt_path("p", target, home=tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"provider_target": target.to_dict(), "items": {}, "cleanup_pending": []}),
        encoding="utf-8",
    )
    desired = DesiredSnapshot(
        project_id="p",
        sync_scope="ssot_files",
        items=[],
        item_count=0,
        item_hashes_hash="sha256:" + "0" * 64,
        snapshot_hash="sha256:" + "1" * 64,
    )
    status = evaluate_sync_status(
        project_id="p",
        target=target,
        desired=desired,
        remote_ack={
            "target_key_hash": target.target_key_hash,
            "snapshot_hash": desired.snapshot_hash,
            "item_hashes_hash": desired.item_hashes_hash,
            "binding_hash": binding_hash([]),
        },
        provider=FakeListProvider(fail=True),
        notebook_ref="nb-down",
        home=tmp_path,
    )
    assert status["sync_state"] in {"unavailable", "degraded"}
    assert status.get("synced") is False


@pytest.mark.unit
def test_P8_PROBE_02_title_prefix_insufficient_for_safe_delete():
    target = _target("nb-safe")
    receipt = {
        "provider_target": target.to_dict(),
        "items": {
            "doc": {
                "provider_source_id": "src-owned",
                "managed_name": "vibe__p__doc",
                "upload_filename": "vibe__p__doc__h__aaaaaaaaaaaa.md",
            }
        },
        "cleanup_pending": [],
    }
    result = safe_delete_binding(
        target=target,
        receipt=receipt,
        candidate_source_id="src-other",
        candidate_title="vibe__p__doc",  # title-only / prefix-like
        observed_ids={"src-other"},
    )
    assert result["ok"] is False
    assert result["code"] in {"NOT_RECEIPT_OWNED", "IDENTITY_MISMATCH", "UNSAFE_DELETE"}


@pytest.mark.unit
def test_P8_ACK_01_and_02_read_ack_is_target_scoped():
    store = FakeAckStore()
    a = _target("nb-a")
    b = _target("nb-b")
    store.write_ack(
        a,
        {
            "target_key_hash": a.target_key_hash,
            "snapshot_hash": "sha256:a",
            "item_hashes_hash": "sha256:ia",
            "binding_hash": "sha256:ba",
        },
    )
    assert read_ack(store, a)["snapshot_hash"] == "sha256:a"
    assert read_ack(store, b) is None


@pytest.mark.integration
def test_P8_LIFECYCLE_02_verify_fail_keeps_old(tmp_path: Path):
    target = _target("nb-vf")
    old_name = upload_filename(managed_name("p", "spec"), "a" * 64)
    provider = FakeLifecycleProvider(
        [{"id": "src-old", "title": old_name, "status": "ready"}],
        verify_fail=True,
    )
    new_file = tmp_path / "spec.md"
    new_file.write_text("new\n", encoding="utf-8")
    receipt = {
        "provider_target": target.to_dict(),
        "items": {
            "spec": {
                "provider_source_id": "src-old",
                "upload_filename": old_name,
                "content_sha256": "sha256:" + "a" * 64,
            }
        },
        "cleanup_pending": [],
    }
    result = replace_item_with_receipt_switch(
        provider,
        notebook_ref="nb-vf",
        target=target,
        project_id="p",
        doc_id="spec",
        path_str="spec.md",
        file_path=new_file,
        content_sha256=content_sha256_bytes(b"new\n"),
        receipt=receipt,
    )
    assert result["ok"] is False
    assert receipt["items"]["spec"]["provider_source_id"] == "src-old"
    assert any(x.get("id") == "src-old" for x in provider.sources)
    assert not any(m[0] == "delete" for m in provider.mutations)


@pytest.mark.integration
def test_P8_LIFECYCLE_03_cleanup_fail_keeps_cleanup_pending(tmp_path: Path):
    target = _target("nb-cf")
    old_sha = content_sha256_bytes(b"old\n")
    new_sha = content_sha256_bytes(b"new\n")
    mname = managed_name("p", "spec")
    old_name = upload_filename(mname, old_sha)
    provider = FakeLifecycleProvider(
        [{"id": "src-old", "title": old_name, "status": "ready"}],
        delete_fail=True,
    )
    new_file = tmp_path / "spec.md"
    new_file.write_bytes(b"new\n")
    receipt = {
        "provider_target": target.to_dict(),
        "items": {
            "spec": {
                "provider_source_id": "src-old",
                "upload_filename": old_name,
                "content_sha256": "sha256:" + old_sha,
            }
        },
        "cleanup_pending": [],
    }
    result = replace_item_with_receipt_switch(
        provider,
        notebook_ref="nb-cf",
        target=target,
        project_id="p",
        doc_id="spec",
        path_str="spec.md",
        file_path=new_file,
        content_sha256=new_sha,
        receipt=receipt,
    )
    assert result["ok"] is False
    assert result.get("code") == "CLEANUP_FAILED"
    assert any(x.get("provider_source_id") == "src-old" for x in receipt.get("cleanup_pending") or [])
    assert receipt["items"]["spec"]["provider_source_id"] != "src-old"


@pytest.mark.unit
def test_P8_PENDING_01_and_04_write_and_clear(tmp_path: Path):
    target = _target("nb-p")
    write_pending_sync("p", target, reason="SYNC_FAILED", home=tmp_path)
    path = pending_sync_path("p", target, home=tmp_path)
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["target_key_hash"] == target.target_key_hash
    clear_pending_sync("p", target, home=tmp_path)
    assert not path.is_file()


@pytest.mark.unit
def test_P8_PENDING_05_no_runjournal_sqlite_daemon():
    """Phase 8 NLM path must not grow RunJournal/daemon; local_fts may use sqlite3."""
    root = Path(__file__).resolve().parents[1] / "src" / "vibe_control"
    banned = ("RunJournal", "sqlite3.connect", "daemon=True")
    allowed_sqlite = root / "knowledge" / "local_fts"
    hits = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in banned:
            if token not in text:
                continue
            if token == "sqlite3.connect" and allowed_sqlite in path.parents:
                continue
            hits.append(f"{path.relative_to(root)}:{token}")
    assert hits == []


@pytest.mark.unit
def test_P8_REINDEX_04_insufficient_identity_fail_closed(tmp_path: Path):
    target = _target("nb-ri")
    provider = FakeListProvider([{"id": "x", "title": "Random User Doc.md", "status": "ready"}])
    result = reindex_bindings(
        project_id="p",
        target=target,
        notebook_ref="nb-ri",
        provider=provider,
        desired_docs=[{"doc_id": "a", "path": "a.md", "content_sha256": "sha256:" + "a" * 64}],
        home=tmp_path,
        repo_root=tmp_path,
        require_managed_identity=True,
    )
    assert result["ok"] is False
    assert result.get("code") in {"INSUFFICIENT_IDENTITY", "NO_MANAGED_BINDINGS"}


@pytest.mark.unit
def test_P8_LIFECYCLE_05_unmanaged_never_deleted():
    target = _target("nb-um")
    receipt = {"provider_target": target.to_dict(), "items": {}, "cleanup_pending": []}
    result = safe_delete_binding(
        target=target,
        receipt=receipt,
        candidate_source_id="user-1",
        candidate_title="My Notes.md",
        observed_ids={"user-1"},
    )
    assert result["ok"] is False
