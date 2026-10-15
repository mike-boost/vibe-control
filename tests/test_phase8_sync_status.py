"""Phase 8 integration tests: probe + sync status (fake provider only)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from helpers import write_doc, write_registry
from vibe_control.config import load_config
from vibe_control.knowledge.corpus import build_desired_corpus
from vibe_control.knowledge.managed_names import managed_name, upload_filename
from vibe_control.knowledge.provider_target import ProviderTarget
from vibe_control.knowledge.receipt_scope import scoped_receipt_path
from vibe_control.knowledge.snapshot import (
    binding_hash,
    build_desired_snapshot,
    upload_hash_from_sha,
)
from vibe_control.knowledge.sync_status import (
    evaluate_sync_status,
    probe_managed_sources,
)


def _source_id_hash(source_id: str) -> str:
    # Match receipt fingerprint style used by Phase 8 probe/binding_hash.
    import hashlib

    return "sha256:" + hashlib.sha256(source_id.encode("utf-8")).hexdigest()[:16]


class FakeProbeProvider:
    def __init__(self, sources: list[dict] | None = None):
        self.sources = list(sources or [])
        self.listed_notebooks: list[str] = []

    def list_sources(self, *, notebook_ref: str) -> dict:
        self.listed_notebooks.append(notebook_ref)
        return {"ok": True, "sources": list(self.sources)}


def _project(tmp: Path) -> None:
    cfg = {
        "project": {"id": "vibe-control", "name": "Vibe Control"},
        "knowledge": {
            "provider": "notebooklm",
            "fallback_provider": "repo",
            "max_sources": 20,
            "warn_sources": 15,
            "authoritative_statuses": ["active"],
            "include_extra": ["docs/project/DECISION_LOG.md"],
            "exclude_globs": ["**/archive/**"],
            "source_title_template": "[vibe:{project_id}:{doc_id}] {title}",
            "notebooks": {
                "default_alias": "OPM-test",
                "allow_list": [
                    {
                        "alias": "OPM-test",
                        "display_name": "OPM-test",
                        "ref_env": "NOTEBOOKLM_NOTEBOOK_OPM_TEST",
                        "allowed_operations": ["status", "sync"],
                    }
                ],
            },
        },
        "specs": {
            "registry": "docs/project/spec-registry.yml",
            "required_fields": ["id", "status", "path"],
            "require_commit_push_for_ssot": True,
        },
        "tasks": {"provider": "beads"},
    }
    path = tmp / ".config" / "vibe-control.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    write_registry(
        tmp,
        [
            {
                "id": "vibe_control_v0_5_spec",
                "title": "Spec",
                "status": "active",
                "path": "docs/project/VIBE_CONTROL_V0_5_SPEC.md",
            }
        ],
    )
    write_doc(tmp, "docs/project/VIBE_CONTROL_V0_5_SPEC.md", "spec v1\n")
    write_doc(tmp, "docs/project/DECISION_LOG.md", "decision v1\n")


def _snapshot(tmp: Path):
    config = load_config(tmp)
    corpus = build_desired_corpus(config, repo_root=tmp)
    return build_desired_snapshot(
        project_id=config.project_id,
        sync_scope="ssot_files",
        documents=[{"doc_id": d.doc_id, "path": d.path} for d in corpus.documents],
        repo_root=tmp,
    )


def _bindings_for(tmp: Path, target: ProviderTarget, *, source_ids: dict[str, str]):
    snap = _snapshot(tmp)
    rows = []
    for item in snap.items:
        sha = item.content_sha256.replace("sha256:", "")
        mname = managed_name("vibe-control", item.doc_id)
        fname = upload_filename(mname, sha)
        sid = source_ids[item.doc_id]
        rows.append(
            {
                "target_key_hash": target.target_key_hash,
                "doc_id": item.doc_id,
                "content_sha256": item.content_sha256,
                "upload_hash": upload_hash_from_sha(sha),
                "source_id_hash": _source_id_hash(sid),
                "ready": True,
                "provider_source_id": sid,
                "managed_name": mname,
                "upload_filename": fname,
                "path": item.path,
            }
        )
    return snap, rows


@pytest.mark.integration
def test_probe_uses_upload_filename_not_body(tmp_path: Path, monkeypatch):
    _project(tmp_path)
    monkeypatch.setenv("NOTEBOOKLM_NOTEBOOK_OPM_TEST", "nb-probe")
    target = ProviderTarget.from_ref(
        provider="notebooklm", notebook_alias="OPM-test", notebook_ref="nb-probe"
    )
    snap, rows = _bindings_for(
        tmp_path,
        target,
        source_ids={
            "vibe_control_v0_5_spec": "src-1",
            "DECISION_LOG": "src-2",
        },
    )
    remote = [
        {"id": r["provider_source_id"], "title": r["upload_filename"], "status": "ready"}
        for r in rows
    ]
    provider = FakeProbeProvider(remote)
    probe = probe_managed_sources(
        provider,
        notebook_ref="nb-probe",
        target=target,
        desired=snap,
        expected_bindings={r["doc_id"]: r for r in rows},
    )
    assert probe.ok is True
    assert probe.missing == []
    assert probe.duplicates == []
    assert probe.binding_hash == binding_hash(
        [
            {
                "target_key_hash": r["target_key_hash"],
                "doc_id": r["doc_id"],
                "content_sha256": r["content_sha256"],
                "upload_hash": r["upload_hash"],
                "source_id_hash": r["source_id_hash"],
                "ready": True,
            }
            for r in rows
        ]
    )
    assert provider.listed_notebooks == ["nb-probe"]


@pytest.mark.integration
def test_status_not_synced_when_ack_ok_but_probe_misses(tmp_path: Path, monkeypatch):
    _project(tmp_path)
    monkeypatch.setenv("NOTEBOOKLM_NOTEBOOK_OPM_TEST", "nb-1")
    target = ProviderTarget.from_ref(
        provider="notebooklm", notebook_alias="OPM-test", notebook_ref="nb-1"
    )
    snap, rows = _bindings_for(
        tmp_path,
        target,
        source_ids={"vibe_control_v0_5_spec": "src-1", "DECISION_LOG": "src-2"},
    )
    # receipt present
    receipt_path = scoped_receipt_path("vibe-control", target, home=tmp_path)
    receipt_path.parent.mkdir(parents=True)
    receipt_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "project_id": "vibe-control",
                "provider": "notebooklm",
                "provider_target": target.to_dict(),
                "snapshot_hash": snap.snapshot_hash,
                "binding_hash": binding_hash(
                    [
                        {
                            "target_key_hash": r["target_key_hash"],
                            "doc_id": r["doc_id"],
                            "content_sha256": r["content_sha256"],
                            "upload_hash": r["upload_hash"],
                            "source_id_hash": r["source_id_hash"],
                            "ready": True,
                        }
                        for r in rows
                    ]
                ),
                "items": {r["doc_id"]: r for r in rows},
                "cleanup_pending": [],
            }
        ),
        encoding="utf-8",
    )
    ack = {
        "schema_version": 1,
        "project_id": "vibe-control",
        "sync_scope": "ssot_files",
        "provider": "notebooklm",
        "target_key_hash": target.target_key_hash,
        "notebook_alias": "OPM-test",
        "notebook_ref_hash": target.notebook_ref_hash,
        "snapshot_hash": snap.snapshot_hash,
        "item_hashes_hash": snap.item_hashes_hash,
        "binding_hash": binding_hash(
            [
                {
                    "target_key_hash": r["target_key_hash"],
                    "doc_id": r["doc_id"],
                    "content_sha256": r["content_sha256"],
                    "upload_hash": r["upload_hash"],
                    "source_id_hash": r["source_id_hash"],
                    "ready": True,
                }
                for r in rows
            ]
        ),
    }
    # probe only sees one source
    keep = next(r for r in rows if r["doc_id"] == "vibe_control_v0_5_spec")
    provider = FakeProbeProvider(
        [{"id": keep["provider_source_id"], "title": keep["upload_filename"], "status": "ready"}]
    )
    status = evaluate_sync_status(
        project_id="vibe-control",
        target=target,
        desired=snap,
        remote_ack=ack,
        provider=provider,
        notebook_ref="nb-1",
        home=tmp_path,
    )
    assert status["sync_state"] != "synced"
    assert status["sync_state"] in {"drift", "missing"}


@pytest.mark.integration
def test_status_synced_when_target_ack_probe_match(tmp_path: Path, monkeypatch):
    _project(tmp_path)
    monkeypatch.setenv("NOTEBOOKLM_NOTEBOOK_OPM_TEST", "nb-ok")
    target = ProviderTarget.from_ref(
        provider="notebooklm", notebook_alias="OPM-test", notebook_ref="nb-ok"
    )
    snap, rows = _bindings_for(
        tmp_path,
        target,
        source_ids={"vibe_control_v0_5_spec": "src-1", "DECISION_LOG": "src-2"},
    )
    bhash = binding_hash(
        [
            {
                "target_key_hash": r["target_key_hash"],
                "doc_id": r["doc_id"],
                "content_sha256": r["content_sha256"],
                "upload_hash": r["upload_hash"],
                "source_id_hash": r["source_id_hash"],
                "ready": True,
            }
            for r in rows
        ]
    )
    receipt_path = scoped_receipt_path("vibe-control", target, home=tmp_path)
    receipt_path.parent.mkdir(parents=True)
    receipt_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "project_id": "vibe-control",
                "provider": "notebooklm",
                "provider_target": target.to_dict(),
                "snapshot_hash": snap.snapshot_hash,
                "binding_hash": bhash,
                "items": {r["doc_id"]: r for r in rows},
                "cleanup_pending": [],
            }
        ),
        encoding="utf-8",
    )
    ack = {
        "schema_version": 1,
        "project_id": "vibe-control",
        "sync_scope": "ssot_files",
        "provider": "notebooklm",
        "target_key_hash": target.target_key_hash,
        "notebook_alias": "OPM-test",
        "notebook_ref_hash": target.notebook_ref_hash,
        "snapshot_hash": snap.snapshot_hash,
        "item_hashes_hash": snap.item_hashes_hash,
        "binding_hash": bhash,
    }
    provider = FakeProbeProvider(
        [{"id": r["provider_source_id"], "title": r["upload_filename"], "status": "ready"} for r in rows]
    )
    status = evaluate_sync_status(
        project_id="vibe-control",
        target=target,
        desired=snap,
        remote_ack=ack,
        provider=provider,
        notebook_ref="nb-ok",
        home=tmp_path,
    )
    assert status["sync_state"] == "synced"


@pytest.mark.integration
def test_status_receipt_missing_not_synced(tmp_path: Path, monkeypatch):
    _project(tmp_path)
    monkeypatch.setenv("NOTEBOOKLM_NOTEBOOK_OPM_TEST", "nb-miss")
    target = ProviderTarget.from_ref(
        provider="notebooklm", notebook_alias="OPM-test", notebook_ref="nb-miss"
    )
    snap = _snapshot(tmp_path)
    ack = {
        "target_key_hash": target.target_key_hash,
        "notebook_ref_hash": target.notebook_ref_hash,
        "snapshot_hash": snap.snapshot_hash,
        "item_hashes_hash": snap.item_hashes_hash,
        "binding_hash": "sha256:" + "0" * 64,
    }
    status = evaluate_sync_status(
        project_id="vibe-control",
        target=target,
        desired=snap,
        remote_ack=ack,
        provider=FakeProbeProvider([]),
        notebook_ref="nb-miss",
        home=tmp_path,
    )
    assert status["sync_state"] != "synced"
    assert status.get("code") == "RECEIPT_MISSING" or "receipt" in str(status.get("reasons", [])).lower()


@pytest.mark.integration
def test_multi_notebook_target_a_synced_not_imply_b(tmp_path: Path, monkeypatch):
    _project(tmp_path)
    monkeypatch.setenv("NOTEBOOKLM_NOTEBOOK_OPM_TEST", "nb-a")
    target_a = ProviderTarget.from_ref(
        provider="notebooklm", notebook_alias="OPM-test", notebook_ref="nb-a"
    )
    target_b = ProviderTarget.from_ref(
        provider="notebooklm", notebook_alias="OPM-test", notebook_ref="nb-b"
    )
    snap, rows = _bindings_for(
        tmp_path,
        target_a,
        source_ids={"vibe_control_v0_5_spec": "src-1", "DECISION_LOG": "src-2"},
    )
    bhash = binding_hash(
        [
            {
                "target_key_hash": r["target_key_hash"],
                "doc_id": r["doc_id"],
                "content_sha256": r["content_sha256"],
                "upload_hash": r["upload_hash"],
                "source_id_hash": r["source_id_hash"],
                "ready": True,
            }
            for r in rows
        ]
    )
    path_a = scoped_receipt_path("vibe-control", target_a, home=tmp_path)
    path_a.parent.mkdir(parents=True)
    path_a.write_text(
        json.dumps(
            {
                "provider_target": target_a.to_dict(),
                "snapshot_hash": snap.snapshot_hash,
                "binding_hash": bhash,
                "items": {r["doc_id"]: r for r in rows},
                "cleanup_pending": [],
            }
        ),
        encoding="utf-8",
    )
    ack_a = {
        "target_key_hash": target_a.target_key_hash,
        "notebook_ref_hash": target_a.notebook_ref_hash,
        "snapshot_hash": snap.snapshot_hash,
        "item_hashes_hash": snap.item_hashes_hash,
        "binding_hash": bhash,
    }
    provider = FakeProbeProvider(
        [{"id": r["provider_source_id"], "title": r["upload_filename"], "status": "ready"} for r in rows]
    )
    status_a = evaluate_sync_status(
        project_id="vibe-control",
        target=target_a,
        desired=snap,
        remote_ack=ack_a,
        provider=provider,
        notebook_ref="nb-a",
        home=tmp_path,
    )
    status_b = evaluate_sync_status(
        project_id="vibe-control",
        target=target_b,
        desired=snap,
        remote_ack=ack_a,  # wrong target ack deliberately
        provider=provider,
        notebook_ref="nb-b",
        home=tmp_path,
    )
    assert status_a["sync_state"] == "synced"
    assert status_b["sync_state"] != "synced"
