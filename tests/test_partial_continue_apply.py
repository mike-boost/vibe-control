"""Partial-continue + receipt checkpoint fault tolerance (fake provider)."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from helpers import write_doc, write_registry
from vibe_control.config import load_config
from vibe_control.knowledge.ack_stores import LocalMirrorAckStore
from vibe_control.knowledge.phase8_apply import apply_forward_sync
from vibe_control.knowledge.provider_target import ProviderTarget
from vibe_control.knowledge.receipt_scope import scoped_receipt_path


def _seed(tmp: Path) -> None:
    cfg = {
        "project": {"id": "ft-sync", "name": "FT"},
        "components": {"knowledge": {"enabled": True}, "task": {"enabled": False}},
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
            {"id": "a", "status": "active", "path": "docs/a.md"},
            {"id": "b", "status": "active", "path": "docs/b.md"},
            {"id": "c", "status": "active", "path": "docs/c.md"},
        ],
    )
    write_doc(tmp, "docs/a.md", "# A\n")
    write_doc(tmp, "docs/b.md", "# B\n")
    write_doc(tmp, "docs/c.md", "# C\n")


class SelectiveFailProvider:
    """Fails add for managed doc_id b; succeeds a and c."""

    def __init__(self) -> None:
        self.sources: list[dict] = []
        self._n = 0
        self.add_calls: list[str] = []
        from vibe_control.knowledge.managed_names import managed_name

        self._fail_title = managed_name("ft-sync", "b")

    def list_sources(self, *, notebook_ref: str) -> dict:
        return {"ok": True, "sources": list(self.sources)}

    def add_file_source(self, *, notebook_ref: str, file_path: str, title: str) -> dict:
        self.add_calls.append(title)
        if title == self._fail_title:
            return {"ok": False, "result": {"source": {}}}
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


def test_fail_stop_checkpoints_success_before_stop(tmp_path: Path, monkeypatch):
    _seed(tmp_path)
    monkeypatch.setenv("NOTEBOOKLM_NOTEBOOK_OPM_TEST", "nb-ft")
    config = load_config(tmp_path)
    target = ProviderTarget.from_ref(
        provider="notebooklm", notebook_alias="OPM-test", notebook_ref="nb-ft"
    )
    provider = SelectiveFailProvider()
    result = apply_forward_sync(
        config,
        repo_root=tmp_path,
        target=target,
        notebook_ref="nb-ft",
        provider=provider,
        ack_store=LocalMirrorAckStore(config.project_id, home=tmp_path),
        home=tmp_path,
        command="vibe knowledge sync --apply",
        continue_on_item_error=False,
    )
    assert result["ok"] is False
    assert result["code"] == "ADD_FAILED"
    receipt_path = scoped_receipt_path(config.project_id, target, home=tmp_path)
    assert receipt_path.is_file()
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    # Doc a should be checkpointed even though b failed and c never ran.
    assert "a" in receipt.get("items", {})
    assert "b" not in receipt.get("items", {})
    assert "c" not in receipt.get("items", {})
    effects = result.get("effects") or []
    kinds = {(e.get("kind"), e.get("target")) for e in effects}
    assert ("provider_write", "knowledge.notebooklm") in kinds
    assert ("local_state_write", "knowledge.sync") in kinds
    assert ("local_state_write", "knowledge.last_sync_report") in kinds


def test_partial_continue_finishes_remaining_and_dlq(tmp_path: Path, monkeypatch):
    _seed(tmp_path)
    monkeypatch.setenv("NOTEBOOKLM_NOTEBOOK_OPM_TEST", "nb-ft2")
    config = load_config(tmp_path)
    target = ProviderTarget.from_ref(
        provider="notebooklm", notebook_alias="OPM-test", notebook_ref="nb-ft2"
    )
    provider = SelectiveFailProvider()
    result = apply_forward_sync(
        config,
        repo_root=tmp_path,
        target=target,
        notebook_ref="nb-ft2",
        provider=provider,
        ack_store=LocalMirrorAckStore(config.project_id, home=tmp_path),
        home=tmp_path,
        command="vibe knowledge sync --apply",
        continue_on_item_error=True,
    )
    assert result["ok"] is False
    assert result["code"] == "PARTIAL_ITEM_FAILURES"
    assert result["sync_mode"] == "partial_continue"
    failures = result.get("item_failures") or []
    assert len(failures) == 1
    assert failures[0]["doc_id"] == "b"
    assert failures[0]["code"] == "ADD_FAILED"
    effects = result.get("effects") or []
    assert any(
        e.get("kind") == "provider_write" and e.get("target") == "knowledge.notebooklm"
        for e in effects
    )
    assert any(
        e.get("kind") == "local_state_write"
        and e.get("target") == "knowledge.last_sync_report"
        for e in effects
    )
    receipt = json.loads(
        scoped_receipt_path(config.project_id, target, home=tmp_path).read_text(encoding="utf-8")
    )
    assert "a" in receipt["items"]
    assert "c" in receipt["items"]
    assert "b" not in receipt["items"]
    # Retry without continue should only attempt remaining (b), not re-add a/c.
    class Fixed(SelectiveFailProvider):
        def add_file_source(self, *, notebook_ref: str, file_path: str, title: str) -> dict:
            self.add_calls.append(title)
            self._n += 1
            sid = f"src-{self._n}"
            self.sources.append({"id": sid, "title": title, "status": "ready"})
            return {"ok": True, "result": {"source": {"id": sid, "title": title}}}

    fixed = Fixed()
    fixed.sources = list(provider.sources)
    fixed._n = len(provider.sources)
    retry = apply_forward_sync(
        config,
        repo_root=tmp_path,
        target=target,
        notebook_ref="nb-ft2",
        provider=fixed,
        ack_store=LocalMirrorAckStore(config.project_id, home=tmp_path),
        home=tmp_path,
        command="vibe knowledge sync --apply",
        continue_on_item_error=False,
    )
    assert retry["ok"] is True
    assert len(fixed.add_calls) == 1
    from vibe_control.knowledge.managed_names import managed_name

    assert fixed.add_calls[0] == managed_name("ft-sync", "b")
