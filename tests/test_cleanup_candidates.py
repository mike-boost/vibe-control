"""Readonly cleanup-candidates listing (fake provider; no real NotebookLM mutation)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from helpers import write_doc, write_registry
from vibe_control.config import load_config
from vibe_control.knowledge.ack_stores import LocalMirrorAckStore
from vibe_control.knowledge.cleanup_candidates import list_cleanup_candidates
from vibe_control.knowledge.corpus import build_desired_corpus
from vibe_control.knowledge.managed_names import content_sha256_file, managed_name, upload_filename
from vibe_control.knowledge.provider_target import ProviderTarget
from vibe_control.knowledge.receipt_scope import scoped_receipt_path
from vibe_control.knowledge.remote_ack import write_ack
from vibe_control.knowledge.snapshot import (
    SnapshotItem,
    binding_hash,
    build_desired_snapshot,
    upload_hash_from_sha,
)


def _sid_hash(source_id: str) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(source_id.encode("utf-8")).hexdigest()[:16]


class FakeProvider:
    def __init__(self, sources: list[dict] | None = None):
        self.sources = list(sources or [])
        self.deleted: list[str] = []
        self.added: list[tuple[str, str]] = []
        self.list_calls = 0

    def list_sources(self, *, notebook_ref: str) -> dict:
        self.list_calls += 1
        return {"ok": True, "sources": list(self.sources)}

    def add_file_source(self, *, notebook_ref: str, file_path: str, title: str) -> dict:
        self.added.append((file_path, title))
        raise AssertionError("cleanup-candidates must not add sources")

    def delete_source(self, *, notebook_ref: str, source_id: str) -> dict:
        self.deleted.append(source_id)
        raise AssertionError("cleanup-candidates must not delete sources")

    def wait_source(self, *, notebook_ref: str, source_id: str, timeout: float = 120) -> dict:
        raise AssertionError("cleanup-candidates must not wait")

    def get_source(self, *, notebook_ref: str, source_id: str) -> dict:
        raise AssertionError("cleanup-candidates must not get")


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


def _write_synced_state(
    tmp: Path,
    home: Path,
    provider: FakeProvider,
    *,
    extra_sources: list[dict] | None = None,
    cleanup_pending: list[dict] | None = None,
) -> tuple[ProviderTarget, object]:
    config = load_config(tmp)
    target = ProviderTarget.from_ref(
        provider="notebooklm", notebook_alias="OPM-test", notebook_ref="nb-cleanup"
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
    sources.append(
        {
            "id": "sid-orphan-v05",
            "title": "vibe__vibe-control__vibe_control_v0_5_spec",
            "status": "ready",
        }
    )
    if extra_sources:
        sources.extend(extra_sources)
    provider.sources = sources
    receipt = {
        "schema_version": 1,
        "project_id": config.project_id,
        "sync_scope": "ssot_files",
        "provider": "notebooklm",
        "provider_target": target.to_dict(),
        "items": items,
        "cleanup_pending": list(cleanup_pending or []),
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


def test_synced_plus_orphan_lists_candidate_not_current_ssot(tmp_path: Path):
    _seed(tmp_path)
    home = tmp_path / "home"
    provider = FakeProvider()
    target, _desired = _write_synced_state(tmp_path, home, provider)
    config = load_config(tmp_path)

    result = list_cleanup_candidates(
        config,
        repo_root=tmp_path,
        target=target,
        notebook_ref="nb-cleanup",
        provider=provider,
        home=home,
    )

    assert result["ok"] is True
    assert result["mutation"] is False
    assert result["mode"] == "readonly"
    data = result["data"]
    assert data["required_updates_count"] == 0
    assert data["candidate_count"] >= 1
    assert "vibe_control_spec" in data["current_ssot_doc_ids"]
    assert "DECISION_LOG" in data["current_ssot_doc_ids"]

    orphans = [c for c in data["candidates"] if c["classification"] == "orphan_managed"]
    assert any(c.get("doc_id") == "vibe_control_v0_5_spec" for c in orphans)
    for c in data["candidates"]:
        assert c.get("doc_id") not in {"vibe_control_spec", "DECISION_LOG"} or c[
            "classification"
        ] in {"duplicate_managed", "cleanup_pending"}
    assert provider.deleted == []
    assert provider.added == []


def test_orphan_output_redacts_ids_and_has_owner_action(tmp_path: Path):
    _seed(tmp_path)
    home = tmp_path / "home"
    provider = FakeProvider()
    target, _ = _write_synced_state(tmp_path, home, provider)
    config = load_config(tmp_path)

    result = list_cleanup_candidates(
        config,
        repo_root=tmp_path,
        target=target,
        notebook_ref="nb-cleanup",
        provider=provider,
        home=home,
    )
    blob = json.dumps(result)
    assert "sid-orphan-v05" not in blob
    assert "nb-cleanup" not in blob
    orphan = next(c for c in result["data"]["candidates"] if c["doc_id"] == "vibe_control_v0_5_spec")
    assert orphan["candidate_id"].startswith("sha256:")
    assert orphan["source_id_hash"] == _sid_hash("sid-orphan-v05")
    assert orphan["safe_to_auto_delete"] is False
    assert orphan["delete_eligibility"] == "manual_only"
    assert "owner_action" in orphan
    assert "cleanup-candidates" in orphan["owner_action"]
    assert "provider_source_id" not in orphan
    assert "notebook_ref" not in orphan


def test_provider_unavailable_no_invented_candidates(tmp_path: Path):
    _seed(tmp_path)
    home = tmp_path / "home"
    provider = FakeProvider()
    target, _ = _write_synced_state(tmp_path, home, provider)

    class DownProvider(FakeProvider):
        def list_sources(self, *, notebook_ref: str) -> dict:
            return {"ok": False, "code": "PROVIDER_UNAVAILABLE", "message": "down"}

    down = DownProvider()
    # still need plan_forward_sync_dry_run to call list_sources successfully first...
    # plan_forward_sync_dry_run calls list_sources; if down, sources=[], then we call again.
    # For unavailable path in list_cleanup_candidates, the second list_sources fails.
    # But first call in plan also fails → empty sources → may invent nothing; then second fails.

    # Seed state then use provider that fails on list
    config = load_config(tmp_path)
    result = list_cleanup_candidates(
        config,
        repo_root=tmp_path,
        target=target,
        notebook_ref="nb-cleanup",
        provider=down,
        home=home,
    )
    assert result["ok"] is True
    assert result["mode"] == "unavailable"
    assert result["data"]["candidate_count"] == 0
    assert result["data"]["candidates"] == []
    assert any(
        (a.get("code") if isinstance(a, dict) else "") == "PROVIDER_UNAVAILABLE"
        for a in result["next_actions"]
    )


def test_target_mismatch_fail_closed(tmp_path: Path):
    _seed(tmp_path)
    home = tmp_path / "home"
    provider = FakeProvider()
    config = load_config(tmp_path)
    wrong = ProviderTarget.from_ref(
        provider="notebooklm", notebook_alias="OPM-test", notebook_ref="nb-OTHER"
    )
    # Legacy flat receipt bound to a different notebook → TARGET_MISMATCH on load
    from vibe_control.knowledge.receipt_scope import legacy_receipt_path

    legacy = legacy_receipt_path(config.project_id, home=home)
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "project_id": config.project_id,
                "notebook_ref_hash": "sha256:" + ("a" * 64),
                "provider_target": {
                    "provider": "notebooklm",
                    "notebook_alias": "OPM-test",
                    "target_key_hash": "sha256:" + ("b" * 64),
                },
                "items": {},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    provider.sources = [
        {"id": "sid-wrong", "title": "vibe__vibe-control__vibe_control_v0_5_spec", "status": "ready"}
    ]
    result = list_cleanup_candidates(
        config,
        repo_root=tmp_path,
        target=wrong,
        notebook_ref="nb-OTHER",
        provider=provider,
        home=home,
    )
    assert result["ok"] is False
    assert result["code"] == "TARGET_MISMATCH"
    assert result["mutation"] is False
    assert result["data"]["candidate_count"] == 0
    assert result["data"]["candidates"] == []
    assert "sid-wrong" not in json.dumps(result)


def test_cleanup_pending_receipt_owned_not_deleted(tmp_path: Path):
    _seed(tmp_path)
    home = tmp_path / "home"
    provider = FakeProvider()
    target, _ = _write_synced_state(
        tmp_path,
        home,
        provider,
        cleanup_pending=[
            {
                "doc_id": "DECISION_LOG",
                "provider_source_id": "sid-old-decision",
                "source_id_hash": _sid_hash("sid-old-decision"),
            }
        ],
    )
    config = load_config(tmp_path)
    result = list_cleanup_candidates(
        config,
        repo_root=tmp_path,
        target=target,
        notebook_ref="nb-cleanup",
        provider=provider,
        home=home,
    )
    pending = [c for c in result["data"]["candidates"] if c["classification"] == "cleanup_pending"]
    assert len(pending) == 1
    assert pending[0]["delete_eligibility"] == "receipt_owned_apply_possible"
    assert pending[0]["safe_to_auto_delete"] is False
    assert "sync --apply" in pending[0]["owner_action"] or "retry --apply" in pending[0]["owner_action"]
    assert provider.deleted == []
    assert any(
        (a.get("code") if isinstance(a, dict) else "") == "BOUNDED_APPLY_PENDING"
        for a in result["next_actions"]
    )


def test_duplicate_managed_listed_without_auto_delete(tmp_path: Path):
    _seed(tmp_path)
    home = tmp_path / "home"
    provider = FakeProvider()
    target, _ = _write_synced_state(
        tmp_path,
        home,
        provider,
        extra_sources=[
            {
                "id": "sid-dup-spec",
                "title": "vibe__vibe-control__vibe_control_spec__extra",
                "status": "ready",
            }
        ],
    )
    # Force parse: managed name with same doc slug - use hashed form of same doc
    # Extra source with managed name for same doc_id
    config = load_config(tmp_path)
    mname = managed_name(config.project_id, "vibe_control_spec")
    provider.sources.append(
        {"id": "sid-dup-spec-2", "title": f"{mname}__copy", "status": "ready"}
    )
    # Re-classify: parse_managed_name for vibe__vibe-control__vibe_control_spec__copy
    # parts: vibe, vibe-control, vibe_control_spec, copy -> doc_id = vibe_control_spec__copy
    # Better: use same managed name without hash
    provider.sources = [
        s for s in provider.sources if s.get("id") != "sid-dup-spec"
    ]
    provider.sources.append({"id": "sid-dup-spec-2", "title": mname, "status": "ready"})

    result = list_cleanup_candidates(
        config,
        repo_root=tmp_path,
        target=target,
        notebook_ref="nb-cleanup",
        provider=provider,
        home=home,
    )
    dups = [c for c in result["data"]["candidates"] if c["classification"] == "duplicate_managed"]
    assert len(dups) >= 1
    assert all(c["safe_to_auto_delete"] is False for c in dups)
    assert all(c["delete_eligibility"] == "manual_only" for c in dups)
    # current binding hash should not appear as duplicate
    assert all(c.get("source_id_hash") != _sid_hash("sid-vibe_control_spec") for c in dups)


def test_unmanaged_listed_as_manual_review(tmp_path: Path):
    _seed(tmp_path)
    home = tmp_path / "home"
    provider = FakeProvider()
    target, _ = _write_synced_state(
        tmp_path,
        home,
        provider,
        extra_sources=[{"id": "sid-user-note", "title": "Random User Notes", "status": "ready"}],
    )
    config = load_config(tmp_path)
    result = list_cleanup_candidates(
        config,
        repo_root=tmp_path,
        target=target,
        notebook_ref="nb-cleanup",
        provider=provider,
        home=home,
    )
    unmanaged = [c for c in result["data"]["candidates"] if c["classification"] == "unmanaged"]
    assert any(c.get("display_hint") == "Random User Notes" for c in unmanaged)
    assert all(c["safe_to_auto_delete"] is False for c in unmanaged)
    assert "sid-user-note" not in json.dumps(result)


def test_no_provider_delete_or_apply(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _seed(tmp_path)
    home = tmp_path / "home"
    provider = FakeProvider()
    target, _ = _write_synced_state(tmp_path, home, provider)
    config = load_config(tmp_path)

    apply_mock = MagicMock(side_effect=AssertionError("must not apply"))
    retry_mock = MagicMock(side_effect=AssertionError("must not retry apply"))
    monkeypatch.setattr(
        "vibe_control.knowledge.phase8_apply.apply_forward_sync", apply_mock
    )
    monkeypatch.setattr(
        "vibe_control.knowledge.phase8_apply.retry_forward_sync", retry_mock
    )

    result = list_cleanup_candidates(
        config,
        repo_root=tmp_path,
        target=target,
        notebook_ref="nb-cleanup",
        provider=provider,
        home=home,
    )
    assert result["ok"] is True
    assert result["mutation"] is False
    assert provider.deleted == []
    apply_mock.assert_not_called()
    retry_mock.assert_not_called()


def test_cli_envelope_fields_stable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _seed(tmp_path)
    home = tmp_path / "home"
    provider = FakeProvider()
    target, _ = _write_synced_state(tmp_path, home, provider)
    config = load_config(tmp_path)

    # Exercise remote_ops envelope shape via list_cleanup_candidates + envelope wrapper
    from vibe_control.json_envelope import success_envelope

    inner = list_cleanup_candidates(
        config,
        repo_root=tmp_path,
        target=target,
        notebook_ref="nb-cleanup",
        provider=provider,
        home=home,
    )
    env = success_envelope(
        command="vibe knowledge cleanup-candidates",
        project_id=config.project_id,
        data=inner["data"],
        warnings=inner.get("warnings") or [],
        next_actions=inner.get("next_actions") or [],
        mode=str(inner.get("mode") or "readonly"),
    )
    env["provider"] = inner["provider"]
    env["target_key_hash"] = inner["target_key_hash"]
    env["mutation"] = False

    for key in (
        "ok",
        "command",
        "project_id",
        "mode",
        "provider",
        "target_key_hash",
        "mutation",
        "data",
        "warnings",
        "next_actions",
    ):
        assert key in env
    assert env["ok"] is True
    assert env["mutation"] is False
    assert env["command"] == "vibe knowledge cleanup-candidates"
    assert env["data"]["candidate_count"] == len(env["data"]["candidates"])


def test_ask_hygiene_not_clean_with_orphan(tmp_path: Path):
    _seed(tmp_path)
    home = tmp_path / "home"
    provider = FakeProvider()
    target, _ = _write_synced_state(tmp_path, home, provider)
    config = load_config(tmp_path)
    result = list_cleanup_candidates(
        config,
        repo_root=tmp_path,
        target=target,
        notebook_ref="nb-cleanup",
        provider=provider,
        home=home,
    )
    hygiene = result["data"]["ask_hygiene"]
    assert hygiene["provider_ask_clean"] is False
    assert hygiene["condition"] == "orphan_pollution"
    assert result["data"]["candidate_count"] >= 1


def test_ask_hygiene_clean_when_no_candidates(tmp_path: Path):
    _seed(tmp_path)
    home = tmp_path / "home"
    provider = FakeProvider()
    target, _ = _write_synced_state(tmp_path, home, provider)
    provider.sources = [s for s in provider.sources if "v0_5" not in str(s.get("title"))]
    config = load_config(tmp_path)
    result = list_cleanup_candidates(
        config,
        repo_root=tmp_path,
        target=target,
        notebook_ref="nb-cleanup",
        provider=provider,
        home=home,
    )
    hygiene = result["data"]["ask_hygiene"]
    assert result["data"]["candidate_count"] == 0
    assert result["data"]["required_updates_count"] == 0
    assert hygiene["provider_ask_clean"] is True
    assert hygiene["condition"] == "clean"


def test_no_candidates_next_action(tmp_path: Path):
    _seed(tmp_path)
    home = tmp_path / "home"
    provider = FakeProvider()
    target, _ = _write_synced_state(tmp_path, home, provider)
    provider.sources = [s for s in provider.sources if "v0_5" not in str(s.get("title"))]
    config = load_config(tmp_path)
    result = list_cleanup_candidates(
        config,
        repo_root=tmp_path,
        target=target,
        notebook_ref="nb-cleanup",
        provider=provider,
        home=home,
    )
    assert result["data"]["candidate_count"] == 0
    assert any(
        (a.get("code") if isinstance(a, dict) else "") == "NO_CLEANUP_NEEDED"
        for a in result["next_actions"]
    )


def test_apply_with_orphan_present_does_not_delete_orphan(tmp_path: Path):
    """Current-SSOT apply must not delete orphan_managed leftovers."""
    from vibe_control.knowledge.ack_stores import LocalMirrorAckStore
    from vibe_control.knowledge.ask_hygiene import assert_apply_ops_are_current_ssot_bounded
    from vibe_control.knowledge.phase8_apply import apply_forward_sync, plan_forward_sync_dry_run

    _seed(tmp_path)
    home = tmp_path / "home"
    provider = FakeProvider()
    target, _ = _write_synced_state(tmp_path, home, provider)
    config = load_config(tmp_path)
    ack_store = LocalMirrorAckStore(config.project_id, home=home)
    dry = plan_forward_sync_dry_run(
        config,
        repo_root=tmp_path,
        target=target,
        notebook_ref="nb-cleanup",
        provider=provider,
        ack_store=ack_store,
        home=home,
    )
    assert any(o.get("op") == "orphan_managed" for o in dry.get("operations") or [])
    bound = assert_apply_ops_are_current_ssot_bounded(
        dry.get("operations") or [],
        desired_doc_ids={"vibe_control_spec", "DECISION_LOG"},
    )
    assert bound["ok"] is True
    # Synced content: apply should no-op desired docs and must not delete orphan
    applied = apply_forward_sync(
        config,
        repo_root=tmp_path,
        target=target,
        notebook_ref="nb-cleanup",
        provider=provider,
        ack_store=ack_store,
        home=home,
        command="vibe knowledge sync --apply",
    )
    assert applied.get("ok") is True
    assert provider.deleted == []
    assert any("v0_5" in str(s.get("title")) for s in provider.sources)
