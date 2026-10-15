"""Phase 8 remaining production wiring tests (fake provider; no real mutation)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from helpers import write_doc, write_registry
from vibe_control.cli import main
from vibe_control.config import load_config
from vibe_control.knowledge.managed_names import content_sha256_file, managed_name, upload_filename
from vibe_control.knowledge.pending_sync import pending_sync_exists, write_pending_sync
from vibe_control.knowledge.phase8_apply import apply_forward_sync, retry_forward_sync
from vibe_control.knowledge.provider_target import ProviderTarget
from vibe_control.knowledge.receipt_scope import scoped_receipt_path
from vibe_control.knowledge.remote_ack import FakeAckStore, read_ack, write_ack
from vibe_control.knowledge.snapshot import build_desired_snapshot
from vibe_control.knowledge.corpus import build_desired_corpus
from vibe_control.knowledge.notebooklm_probe import NotebookLMReadonlyProbe
from vibe_control.knowledge.remote_ack_guard import assert_ack_write_allowed


class RecordingProvider:
    def __init__(self, sources=None):
        self.sources = list(sources or [])
        self.calls: list[tuple] = []
        self._n = 0

    def list_sources(self, *, notebook_ref: str) -> dict:
        self.calls.append(("list_sources", notebook_ref))
        return {"ok": True, "sources": list(self.sources)}

    def get_source(self, *, notebook_ref: str, source_id: str) -> dict:
        self.calls.append(("get_source", notebook_ref, source_id))
        for item in self.sources:
            if item.get("id") == source_id:
                return {
                    "ok": True,
                    "found": True,
                    "source": {**item, "body": "SHOULD_NEVER_BE_READ"},
                }
        return {"ok": False, "found": False}

    def add_file_source(self, *, notebook_ref: str, file_path: str, title: str) -> dict:
        self.calls.append(("add", Path(file_path).name, title))
        self._n += 1
        sid = f"src-{self._n}"
        # Prefer managed title for identity; matches NotebookLM managed_name path.
        self.sources.append({"id": sid, "title": title or Path(file_path).name, "status": "ready"})
        return {"ok": True, "result": {"source": {"id": sid, "title": title}}}

    def wait_source(self, *, notebook_ref: str, source_id: str, timeout: float = 120) -> dict:
        self.calls.append(("wait", source_id))
        return {"ok": True, "status": "ready"}

    def delete_source(self, *, notebook_ref: str, source_id: str) -> dict:
        self.calls.append(("delete", source_id))
        self.sources = [x for x in self.sources if x.get("id") != source_id]
        return {"ok": True}


def _seed(tmp: Path) -> None:
    cfg = {
        "project": {"id": "vibe-control", "name": "Vibe Control"},
        "knowledge": {
            "provider": "notebooklm",
            "fallback_provider": "repo",
            "max_sources": 20,
            "warn_sources": 15,
            "authoritative_statuses": ["active"],
            "include_extra": [],
            "exclude_globs": ["**/archive/**"],
            "source_title_template": "[vibe:{project_id}:{doc_id}] {title}",
            "notebooks": {
                "default_alias": "OPM-test",
                "allow_list": [
                    {
                        "alias": "OPM-test",
                        "display_name": "OPM-test",
                        "ref_env": "NOTEBOOKLM_NOTEBOOK_OPM_TEST",
                        "allowed_operations": [
                            "status",
                            "sync",
                            "retry",
                            "rebuild",
                            "reindex_bindings",
                        ],
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
                "id": "active_spec",
                "title": "Active",
                "status": "active",
                "path": "docs/project/active.md",
            }
        ],
    )
    write_doc(tmp, "docs/project/active.md", "active body v1\n")


@pytest.mark.integration
def test_P8_REAL_PROBE_list_sources_only_never_reads_body(tmp_path: Path):
    _seed(tmp_path)
    target = ProviderTarget.from_ref(
        provider="notebooklm", notebook_alias="OPM-test", notebook_ref="nb-probe"
    )
    config = load_config(tmp_path)
    corpus = build_desired_corpus(config, repo_root=tmp_path)
    doc = corpus.documents[0]
    sha = content_sha256_file(tmp_path / doc.path)
    fname = upload_filename(managed_name(config.project_id, doc.doc_id), sha)
    provider = RecordingProvider(
        [{"id": "src-1", "title": fname, "status": "ready"}]
    )
    probe = NotebookLMReadonlyProbe(provider)
    result = probe.probe(
        notebook_ref="nb-probe",
        target=target,
        project_id=config.project_id,
        repo_root=tmp_path,
        home=tmp_path,
    )
    assert result["ok"] is True or result.get("sync_state") in {
        "drift",
        "receipt_missing",
        "synced",
    }
    assert not any(c[0] == "get_source" for c in provider.calls)
    assert any(c[0] == "list_sources" for c in provider.calls)
    assert all(c[0] != "add" and c[0] != "delete" for c in provider.calls)


@pytest.mark.unit
def test_P8_ACK_NOTE_write_blocked_outside_mutation_path():
    with pytest.raises(PermissionError):
        assert_ack_write_allowed(command="vibe knowledge status")
    with pytest.raises(PermissionError):
        assert_ack_write_allowed(command="vibe knowledge query")
    with pytest.raises(PermissionError):
        assert_ack_write_allowed(command="vibe knowledge doctor")
    assert_ack_write_allowed(command="vibe knowledge sync --apply")
    assert_ack_write_allowed(command="vibe knowledge retry --apply")


@pytest.mark.integration
def test_P8_ACK_NOTE_foreign_target_ignored_and_write_after_verify(tmp_path: Path):
    store = FakeAckStore()
    a = ProviderTarget.from_ref(provider="notebooklm", notebook_alias="A", notebook_ref="nb-a")
    b = ProviderTarget.from_ref(provider="notebooklm", notebook_alias="B", notebook_ref="nb-b")
    write_ack(
        store,
        a,
        {
            "snapshot_hash": "sha256:a",
            "item_hashes_hash": "sha256:ia",
            "binding_hash": "sha256:ba",
        },
    )
    assert read_ack(store, b) is None
    assert read_ack(store, a)["snapshot_hash"] == "sha256:a"


@pytest.mark.integration
def test_P8_APPLY_RETRY_scoped_pending_and_latest_snapshot(tmp_path: Path, monkeypatch):
    _seed(tmp_path)
    monkeypatch.setenv("NOTEBOOKLM_NOTEBOOK_OPM_TEST", "nb-apply")
    config = load_config(tmp_path)
    target = ProviderTarget.from_ref(
        provider="notebooklm", notebook_alias="OPM-test", notebook_ref="nb-apply"
    )
    provider = RecordingProvider()
    ack = FakeAckStore()

    # First apply creates binding + ack, clears pending if any
    write_pending_sync("vibe-control", target, reason="PREV", home=tmp_path)
    result = apply_forward_sync(
        config,
        repo_root=tmp_path,
        target=target,
        notebook_ref="nb-apply",
        provider=provider,
        ack_store=ack,
        home=tmp_path,
        command="vibe knowledge sync --apply",
    )
    assert result["ok"] is True
    assert not pending_sync_exists("vibe-control", target, home=tmp_path)
    assert scoped_receipt_path("vibe-control", target, home=tmp_path).is_file()
    assert read_ack(ack, target) is not None
    assert result.get("notebooklm_note_written") is False
    assert result.get("ack_store_kind") in {"fake", "local_mirror"}
    assert any(c[0] == "add" for c in provider.calls)

    # Change SSOT while "pending" then retry must sync final content only
    write_doc(tmp_path, "docs/project/active.md", "active body FINAL\n")
    write_pending_sync("vibe-control", target, reason="OUTAGE", home=tmp_path)
    provider.calls.clear()
    retry = retry_forward_sync(
        config,
        repo_root=tmp_path,
        target=target,
        notebook_ref="nb-apply",
        provider=provider,
        ack_store=ack,
        home=tmp_path,
        command="vibe knowledge retry --apply",
    )
    assert retry["ok"] is True
    assert retry.get("replayed_history") is False
    assert not pending_sync_exists("vibe-control", target, home=tmp_path)
    # Replace path should have added new version (final snapshot), not five historical ops
    add_calls = [c for c in provider.calls if c[0] == "add"]
    assert len(add_calls) <= 2  # one replace for the changed doc
    receipt = json.loads(
        scoped_receipt_path("vibe-control", target, home=tmp_path).read_text(encoding="utf-8")
    )
    final_sha = content_sha256_file(tmp_path / "docs/project/active.md")
    item = receipt["items"]["active_spec"]
    assert item["content_sha256"].endswith(final_sha) or final_sha in item["content_sha256"]


@pytest.mark.integration
def test_P8_APPLY_writes_pending_on_failure(tmp_path: Path, monkeypatch):
    _seed(tmp_path)
    monkeypatch.setenv("NOTEBOOKLM_NOTEBOOK_OPM_TEST", "nb-fail")
    config = load_config(tmp_path)
    target = ProviderTarget.from_ref(
        provider="notebooklm", notebook_alias="OPM-test", notebook_ref="nb-fail"
    )

    class FailAdd(RecordingProvider):
        def add_file_source(self, *, notebook_ref: str, file_path: str, title: str) -> dict:
            self.calls.append(("add", "fail"))
            return {"ok": False, "message": "boom"}

    result = apply_forward_sync(
        config,
        repo_root=tmp_path,
        target=target,
        notebook_ref="nb-fail",
        provider=FailAdd(),
        ack_store=FakeAckStore(),
        home=tmp_path,
        command="vibe knowledge sync --apply",
    )
    assert result["ok"] is False
    assert pending_sync_exists("vibe-control", target, home=tmp_path)


@pytest.mark.integration
def test_P8_REINDEX_CLI_alias_and_rebuild_compat(tmp_path: Path, monkeypatch, capsys):
    _seed(tmp_path)
    monkeypatch.setenv("NOTEBOOKLM_NOTEBOOK_OPM_TEST", "nb-reindex")
    monkeypatch.chdir(tmp_path)

    # Inject fake list via runtime-compatible env + monkeypatch command path
    from vibe_control.knowledge import remote_ops

    class FakeNLM:
        def list_sources(self, *, notebook_ref: str) -> dict:
            return {"ok": True, "sources": []}

    monkeypatch.setattr(remote_ops, "NotebookLMProvider", lambda: FakeNLM())

    code = main(["knowledge", "reindex-bindings", "--notebook", "OPM-test", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["ok"] is True
    assert out["data"].get("ssot_restored") is False
    assert "binding" in str(out["data"].get("message", "")).lower() or out["data"].get(
        "reindexed"
    ) is not False

    code2 = main(["knowledge", "rebuild", "--notebook", "OPM-test", "--json"])
    out2 = json.loads(capsys.readouterr().out)
    assert code2 == 0
    assert out2["ok"] is True
    assert out2["data"].get("ssot_restored") is False
    assert out2["command"] in {
        "vibe knowledge rebuild",
        "vibe knowledge reindex-bindings",
    }
