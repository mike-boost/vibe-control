"""Phase 8 unit tests: desired_snapshot and binding hashes."""

from __future__ import annotations

import pytest

from vibe_control.knowledge.snapshot import (
    SnapshotItem,
    binding_hash,
    build_desired_snapshot,
    item_hashes_hash,
    snapshot_hash,
    upload_hash_from_sha,
)


@pytest.mark.unit
def test_item_hashes_hash_order_independent_by_doc_id_sort():
    a = [
        SnapshotItem(doc_id="b", path="b.md", content_sha256="sha256:" + "b" * 64),
        SnapshotItem(doc_id="a", path="a.md", content_sha256="sha256:" + "a" * 64),
    ]
    b = list(reversed(a))
    assert item_hashes_hash(a) == item_hashes_hash(b)


@pytest.mark.unit
def test_snapshot_hash_changes_when_content_changes():
    items1 = [SnapshotItem(doc_id="x", path="x.md", content_sha256="sha256:" + "1" * 64)]
    items2 = [SnapshotItem(doc_id="x", path="x.md", content_sha256="sha256:" + "2" * 64)]
    s1 = snapshot_hash(project_id="vibe-control", sync_scope="ssot_files", items=items1)
    s2 = snapshot_hash(project_id="vibe-control", sync_scope="ssot_files", items=items2)
    assert s1 != s2


@pytest.mark.unit
def test_binding_hash_includes_target_key():
    items = [
        {
            "target_key_hash": "sha256:t1",
            "doc_id": "doc",
            "content_sha256": "sha256:" + "a" * 64,
            "upload_hash": "a" * 12,
            "source_id_hash": "sha256:s1",
            "ready": True,
        }
    ]
    h1 = binding_hash(items)
    items[0]["target_key_hash"] = "sha256:t2"
    h2 = binding_hash(items)
    assert h1 != h2


@pytest.mark.unit
def test_upload_hash_from_sha_is_sha12():
    assert upload_hash_from_sha("abcdef0123456789") == "abcdef012345"
    assert upload_hash_from_sha("sha256:abcdef0123456789") == "abcdef012345"


@pytest.mark.unit
def test_build_desired_snapshot_from_paths(tmp_path):
    doc = tmp_path / "docs" / "a.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("hello\n", encoding="utf-8")
    snap = build_desired_snapshot(
        project_id="vibe-control",
        sync_scope="ssot_files",
        documents=[{"doc_id": "a", "path": "docs/a.md"}],
        repo_root=tmp_path,
    )
    assert snap.item_count == 1
    assert snap.items[0].doc_id == "a"
    assert snap.items[0].content_sha256.startswith("sha256:") or len(snap.items[0].content_sha256) == 64
    assert snap.snapshot_hash.startswith("sha256:")
    assert snap.item_hashes_hash.startswith("sha256:")
