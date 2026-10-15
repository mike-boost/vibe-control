"""Phase 8 status/dry-run consistency (fake provider; no real NotebookLM mutation)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from helpers import write_doc, write_registry
from vibe_control.config import load_config
from vibe_control.knowledge.ack_stores import LocalMirrorAckStore
from vibe_control.knowledge.corpus import build_desired_corpus
from vibe_control.knowledge.managed_names import content_sha256_file, managed_name, upload_filename
from vibe_control.knowledge.phase8_apply import plan_forward_sync_dry_run
from vibe_control.knowledge.provider_target import ProviderTarget
from vibe_control.knowledge.receipt_scope import scoped_receipt_path
from vibe_control.knowledge.remote_ack import write_ack
from vibe_control.knowledge.snapshot import (
    SnapshotItem,
    binding_hash,
    build_desired_snapshot,
    upload_hash_from_sha,
)
from vibe_control.knowledge.sync_status import evaluate_sync_status


def _sid_hash(source_id: str) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(source_id.encode("utf-8")).hexdigest()[:16]


class FakeProvider:
    def __init__(self, sources: list[dict] | None = None):
        self.sources = list(sources or [])
        self.deleted: list[str] = []
        self.added: list[tuple[str, str]] = []

    def list_sources(self, *, notebook_ref: str) -> dict:
        return {"ok": True, "sources": list(self.sources)}

    def add_file_source(self, *, notebook_ref: str, file_path: str, title: str) -> dict:
        self.added.append((file_path, title))
        raise AssertionError("dry-run must not add sources")

    def delete_source(self, *, notebook_ref: str, source_id: str) -> dict:
        self.deleted.append(source_id)
        raise AssertionError("dry-run must not delete sources")

    def wait_source(self, *, notebook_ref: str, source_id: str, timeout: float = 120) -> dict:
        raise AssertionError("dry-run must not wait")

    def get_source(self, *, notebook_ref: str, source_id: str) -> dict:
        raise AssertionError("dry-run must not get")

    def query(self, question: str, *, notebook_ref: str | None = None, **kwargs) -> dict:
        return {
            "ok": True,
            "answer": f"facts-only answer for: {question[:40]}",
            "sources": [{"doc_id": "vibe_control_spec", "source_id": "RAW-SECRET"}],
        }


def _seed(tmp: Path) -> None:
    cfg = {
        "project": {"id": "vibe-control", "name": "Vibe Control"},
        "knowledge": {
            "provider": "notebooklm",
            "fallback_provider": "repo",
            "max_sources": 20,
            "warn_sources": 15,
            "authoritative_statuses": ["active"],
            "include_extra": ["docs/project/DECISION_LOG.md"],
            "exclude_globs": ["**/archive/**", "docs/project/plans/**", "docs/project/reviews/**"],
            "source_title_template": "[vibe:{project_id}:{doc_id}] {title}",
            "notebooks": {
                "default_alias": "OPM-test",
                "allow_list": [
                    {
                        "alias": "OPM-test",
                        "display_name": "OPM-test",
                        "ref_env": "NOTEBOOKLM_NOTEBOOK_OPM_TEST",
                        "allowed_operations": ["status", "sync", "retry", "query"],
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
                "id": "vibe_control_spec",
                "title": "Vibe Control Spec",
                "status": "active",
                "path": "docs/project/vibe-control-spec.md",
            }
        ],
    )
    write_doc(tmp, "docs/project/vibe-control-spec.md", "Phase 11A complete\nPhase 11B not started\n")
    write_doc(tmp, "docs/project/DECISION_LOG.md", "Decision: dogfood sync.\n")


def _write_synced_state(tmp: Path, home: Path, provider: FakeProvider) -> tuple[ProviderTarget, object]:
    config = load_config(tmp)
    target = ProviderTarget.from_ref(
        provider="notebooklm", notebook_alias="OPM-test", notebook_ref="nb-consistency"
    )
    corpus = build_desired_corpus(config, repo_root=tmp)
    desired = build_desired_snapshot(
        project_id=config.project_id,
        sync_scope="ssot_files",
        documents=[{"doc_id": d.doc_id, "path": d.path} for d in corpus.documents],
        repo_root=tmp,
    )
    items: dict = {}
    sources: list[dict] = []
    rows: list[dict] = []
    for doc in corpus.documents:
        path = tmp / doc.path
        sha = content_sha256_file(path)
        content_sha = SnapshotItem._norm_sha(sha)
        mname = managed_name(config.project_id, doc.doc_id)
        fname = upload_filename(mname, sha)
        sid = f"sid-{doc.doc_id}"
        items[doc.doc_id] = {
            "path": doc.path,
            "content_sha256": content_sha,
            "provider_source_id": sid,
            "source_id_hash": _sid_hash(sid),
            "managed_name": mname,
            "upload_filename": fname,
            "upload_hash": upload_hash_from_sha(sha),
            "ready": True,
        }
        sources.append({"id": sid, "title": fname, "status": "ready"})
        rows.append(
            {
                "target_key_hash": target.target_key_hash,
                "doc_id": doc.doc_id,
                "content_sha256": content_sha,
                "upload_hash": upload_hash_from_sha(sha),
                "source_id_hash": _sid_hash(sid),
                "ready": True,
            }
        )
    # orphan old v0_5 on remote only
    sources.append(
        {
            "id": "sid-orphan-v05",
            "title": "vibe__vibe-control__vibe_control_v0_5_spec",
            "status": "ready",
        }
    )
    provider.sources = sources
    receipt = {
        "schema_version": 1,
        "project_id": config.project_id,
        "sync_scope": "ssot_files",
        "provider": "notebooklm",
        "provider_target": target.to_dict(),
        "items": items,
        "cleanup_pending": [],
        "snapshot_hash": desired.snapshot_hash,
        "binding_hash": binding_hash(rows),
    }
    scoped = scoped_receipt_path(config.project_id, target, home=home)
    scoped.parent.mkdir(parents=True, exist_ok=True)
    scoped.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    ack_store = LocalMirrorAckStore(config.project_id, home=home)
    write_ack(
        ack_store,
        target,
        {
            "schema_version": 1,
            "provider_contract": "vibe.knowledge.provider.v1",
            "project_id": config.project_id,
            "sync_scope": "ssot_files",
            "provider": "notebooklm",
            "target_key_hash": target.target_key_hash,
            "notebook_alias": target.notebook_alias,
            "notebook_ref_hash": target.notebook_ref_hash,
            "snapshot_hash": desired.snapshot_hash,
            "item_hashes_hash": desired.item_hashes_hash,
            "binding_hash": binding_hash(rows),
        },
    )
    return target, desired


def test_status_synced_dry_run_clean_for_current_ssot(tmp_path: Path):
    from vibe_control.knowledge.remote_ack import read_ack

    _seed(tmp_path)
    home = tmp_path / "home"
    provider = FakeProvider()
    target, desired = _write_synced_state(tmp_path, home, provider)
    config = load_config(tmp_path)
    ack_store = LocalMirrorAckStore(config.project_id, home=home)
    status = evaluate_sync_status(
        project_id=config.project_id,
        target=target,
        desired=desired,
        remote_ack=read_ack(ack_store, target),
        provider=provider,
        notebook_ref="nb-consistency",
        home=home,
    )
    assert status["sync_state"] == "synced"
    assert status["synced"] is True

    dry = plan_forward_sync_dry_run(
        config,
        repo_root=tmp_path,
        target=target,
        notebook_ref="nb-consistency",
        provider=provider,
        ack_store=ack_store,
        home=home,
    )
    assert dry["ok"] is True
    assert dry["planner"] == "phase8"
    assert dry["synced"] is True
    assert dry["required_updates_count"] == 0
    ops = {(o["op"], o.get("doc_id")) for o in dry["operations"]}
    assert ("already_current", "vibe_control_spec") in ops
    assert ("already_current", "DECISION_LOG") in ops
    assert ("replace_required", "vibe_control_spec") not in ops
    assert ("replace_required", "DECISION_LOG") not in ops
    assert ("orphan_managed", "vibe_control_v0_5_spec") in ops
    orphan = next(o for o in dry["operations"] if o["op"] == "orphan_managed")
    assert orphan["action"] == "report_only_no_delete"
    assert provider.deleted == []
    assert provider.added == []


def test_orphan_does_not_force_replace_required(tmp_path: Path):
    _seed(tmp_path)
    home = tmp_path / "home"
    provider = FakeProvider()
    target, _desired = _write_synced_state(tmp_path, home, provider)
    config = load_config(tmp_path)
    ack_store = LocalMirrorAckStore(config.project_id, home=home)
    dry = plan_forward_sync_dry_run(
        config,
        repo_root=tmp_path,
        target=target,
        notebook_ref="nb-consistency",
        provider=provider,
        ack_store=ack_store,
        home=home,
    )
    required_docs = {r["doc_id"] for r in dry["required_updates"]}
    assert "vibe_control_v0_5_spec" not in required_docs
    assert dry["summary"].get("orphan_managed") == 1


def test_dry_run_does_not_use_legacy_receipt_when_scoped_synced(tmp_path: Path):
    """Legacy flat receipt can be stale; Phase 8 dry-run must use scoped receipt."""
    _seed(tmp_path)
    home = tmp_path / "home"
    provider = FakeProvider()
    target, _desired = _write_synced_state(tmp_path, home, provider)
    # Poison legacy flat receipt with outdated DECISION_LOG hash
    legacy = home / ".agents" / "state" / "vibe-control" / "vibe-control" / "knowledge-sync.json"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "project_id": "vibe-control",
                "documents": {
                    "DECISION_LOG": {
                        "doc_id": "DECISION_LOG",
                        "current": {
                            "content_sha256": "sha256:" + ("0" * 64),
                            "provider_source_id": "legacy-sid",
                        },
                    }
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    config = load_config(tmp_path)
    ack_store = LocalMirrorAckStore(config.project_id, home=home)
    dry = plan_forward_sync_dry_run(
        config,
        repo_root=tmp_path,
        target=target,
        notebook_ref="nb-consistency",
        provider=provider,
        ack_store=ack_store,
        home=home,
    )
    assert dry["required_updates_count"] == 0
    assert ("already_current", "DECISION_LOG") in {(o["op"], o.get("doc_id")) for o in dry["operations"]}


def test_query_ask_template_on_provider_path(tmp_path: Path, monkeypatch):
    from vibe_control.knowledge.ask_template import ASK_TEMPLATE_VERSION, DEFAULT_ASK_TEMPLATE_ID
    from vibe_control.knowledge.query_router import route_knowledge_query

    _seed(tmp_path)
    monkeypatch.setenv("NOTEBOOKLM_NOTEBOOK_OPM_TEST", "nb-q")

    class CapturingProvider(FakeProvider):
        def __init__(self):
            super().__init__()
            self.questions: list[str] = []

        def query(self, question: str, *, notebook_ref: str | None = None, **kwargs) -> dict:
            self.questions.append(question)
            return {"ok": True, "answer": "provider facts", "sources": []}

    provider = CapturingProvider()
    result = route_knowledge_query(
        repo_root=tmp_path,
        question="What is Phase 11A status?",
        sync_state_override="synced",
        provider=provider,
        home=tmp_path / "home",
    )
    assert result["provider"] == "notebooklm"
    assert result["ask_template_id"] == DEFAULT_ASK_TEMPLATE_ID
    assert result["ask_template_version"] == ASK_TEMPLATE_VERSION
    assert result["question_hash"].startswith("sha256:")
    assert result["rendered_prompt_hash"].startswith("sha256:")
    assert provider.questions
    assert "Answer only from SSOT-backed source content" in provider.questions[0]


def test_retry_apply_receipt_owned_only_no_unmanaged_delete(tmp_path: Path):
    """VERIFY_FAILED recovery replaces receipt-owned current SSOT; never deletes unmanaged."""
    from vibe_control.knowledge.sync_lifecycle_phase8 import replace_item_with_receipt_switch

    _seed(tmp_path)

    class RecordingProvider(FakeProvider):
        def __init__(self):
            super().__init__(
                sources=[
                    {
                        "id": "owned-decision",
                        "title": "vibe__vibe-control__decision_log__h__aaaaaaaaaaaa.md",
                    },
                    {"id": "unmanaged-1", "title": "Random operator note"},
                ]
            )
            self.next_id = 100

        def add_file_source(self, *, notebook_ref: str, file_path: str, title: str) -> dict:
            self.added.append((file_path, title))
            self.next_id += 1
            sid = f"new-{self.next_id}"
            fname = Path(file_path).name
            self.sources.append({"id": sid, "title": fname, "status": "ready"})
            return {"ok": True, "result": {"source": {"id": sid, "title": fname}}}

        def wait_source(self, *, notebook_ref: str, source_id: str, timeout: float = 120) -> dict:
            return {"ok": True, "status": "ready"}

        def get_source(self, *, notebook_ref: str, source_id: str) -> dict:
            return {"ok": True, "found": True, "source": {"id": source_id, "status": "ready"}}

        def delete_source(self, *, notebook_ref: str, source_id: str) -> dict:
            self.deleted.append(source_id)
            self.sources = [s for s in self.sources if s.get("id") != source_id]
            return {"ok": True}

    rec = RecordingProvider()
    target = ProviderTarget.from_ref(
        provider="notebooklm", notebook_alias="OPM-test", notebook_ref="nb-retry"
    )
    config = load_config(tmp_path)
    receipt = {
        "schema_version": 1,
        "project_id": config.project_id,
        "provider_target": target.to_dict(),
        "items": {
            "DECISION_LOG": {
                "path": "docs/project/DECISION_LOG.md",
                "content_sha256": "sha256:" + ("a" * 64),
                "provider_source_id": "owned-decision",
                "source_id_hash": _sid_hash("owned-decision"),
                "managed_name": managed_name(config.project_id, "DECISION_LOG"),
                "upload_filename": "vibe__vibe-control__decision_log__h__aaaaaaaaaaaa.md",
                "ready": True,
            }
        },
        "cleanup_pending": [],
    }
    path = tmp_path / "docs/project/DECISION_LOG.md"
    result = replace_item_with_receipt_switch(
        rec,
        notebook_ref="nb-retry",
        target=target,
        project_id=config.project_id,
        doc_id="DECISION_LOG",
        path_str="docs/project/DECISION_LOG.md",
        file_path=path,
        content_sha256=content_sha256_file(path),
        receipt=receipt,
    )
    assert result.get("ok") is True
    assert "owned-decision" in rec.deleted
    assert "unmanaged-1" not in rec.deleted
    assert any(s.get("id") == "unmanaged-1" for s in rec.sources)
