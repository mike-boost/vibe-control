"""Micro-batch + multi wait coalescing (fake provider; no real NotebookLM)."""

from __future__ import annotations

import time
from pathlib import Path

import yaml

from helpers import write_doc, write_registry
from vibe_control.config import load_config
from vibe_control.knowledge.ack_stores import LocalMirrorAckStore
from vibe_control.knowledge.batch_wait import normalize_batch_size, wait_many
from vibe_control.knowledge.phase8_apply import apply_forward_sync
from vibe_control.knowledge.provider_target import ProviderTarget


def test_normalize_batch_size_bounds():
    assert normalize_batch_size(None) == 1
    assert normalize_batch_size(0) == 1
    assert normalize_batch_size(5) == 5
    assert normalize_batch_size(100) == 20


def test_wait_many_multi_is_concurrent():
    started: dict[str, float] = {}

    def slow_wait(*, notebook_ref: str, source_id: str, timeout: float = 120) -> dict:
        started[source_id] = time.monotonic()
        time.sleep(0.15)
        return {"ok": True, "status": "ready"}

    t0 = time.monotonic()
    out = wait_many(
        slow_wait,
        notebook_ref="nb",
        source_ids=["a", "b", "c"],
        wait_mode="multi",
    )
    elapsed = time.monotonic() - t0
    assert set(out) == {"a", "b", "c"}
    assert all(v.get("ok") for v in out.values())
    # Concurrent should beat 3 * 0.15 serial (~0.45s)
    assert elapsed < 0.4


def _seed(tmp: Path) -> None:
    cfg = {
        "project": {"id": "batch-sync", "name": "Batch"},
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
    entries = []
    for i in range(4):
        doc_id = f"d{i}"
        rel = f"docs/{doc_id}.md"
        write_doc(tmp, rel, f"# {doc_id}\n")
        entries.append({"id": doc_id, "status": "active", "path": rel})
    write_registry(tmp, entries)


class RecordingProvider:
    def __init__(self) -> None:
        self.sources: list[dict] = []
        self._n = 0
        self.wait_calls: list[str] = []
        self.wait_batches: list[list[str]] = []
        self._inflight: list[str] = []

    def list_sources(self, *, notebook_ref: str) -> dict:
        return {"ok": True, "sources": list(self.sources)}

    def add_file_source(self, *, notebook_ref: str, file_path: str, title: str) -> dict:
        self._n += 1
        sid = f"src-{self._n}"
        self.sources.append({"id": sid, "title": title, "status": "ready"})
        self._inflight.append(sid)
        return {"ok": True, "result": {"source": {"id": sid, "title": title}}}

    def wait_source(self, *, notebook_ref: str, source_id: str, timeout: float = 120) -> dict:
        self.wait_calls.append(source_id)
        # Snapshot current inflight at first wait of a flush window is hard;
        # record call order only.
        return {"ok": True, "status": "ready"}

    def delete_source(self, *, notebook_ref: str, source_id: str) -> dict:
        self.sources = [s for s in self.sources if s.get("id") != source_id]
        return {"ok": True}

    def get_source(self, *, notebook_ref: str, source_id: str) -> dict:
        for s in self.sources:
            if s.get("id") == source_id:
                return {"ok": True, "found": True, "source": s}
        return {"ok": False, "found": False}


def test_apply_batch_size_flushes_before_wait(tmp_path: Path, monkeypatch):
    _seed(tmp_path)
    monkeypatch.setenv("NOTEBOOKLM_NOTEBOOK_OPM_TEST", "nb-batch")
    config = load_config(tmp_path)
    target = ProviderTarget.from_ref(
        provider="notebooklm", notebook_alias="OPM-test", notebook_ref="nb-batch"
    )
    provider = RecordingProvider()
    result = apply_forward_sync(
        config,
        repo_root=tmp_path,
        target=target,
        notebook_ref="nb-batch",
        provider=provider,
        ack_store=LocalMirrorAckStore(config.project_id, home=tmp_path),
        home=tmp_path,
        command="vibe knowledge sync --apply",
        batch_size=2,
        wait_mode="serial",
    )
    assert result["ok"] is True
    assert result["batch_size"] == 2
    assert result["wait_mode"] == "serial"
    assert result["scale"]["batches_flushed"] == 2  # 4 creates / batch 2
    assert len(provider.wait_calls) == 4
    assert len(provider.sources) == 4


def test_apply_default_batch_size_is_one(tmp_path: Path, monkeypatch):
    _seed(tmp_path)
    monkeypatch.setenv("NOTEBOOKLM_NOTEBOOK_OPM_TEST", "nb-batch1")
    config = load_config(tmp_path)
    target = ProviderTarget.from_ref(
        provider="notebooklm", notebook_alias="OPM-test", notebook_ref="nb-batch1"
    )
    provider = RecordingProvider()
    result = apply_forward_sync(
        config,
        repo_root=tmp_path,
        target=target,
        notebook_ref="nb-batch1",
        provider=provider,
        ack_store=LocalMirrorAckStore(config.project_id, home=tmp_path),
        home=tmp_path,
        command="vibe knowledge sync --apply",
    )
    assert result["ok"] is True
    assert result["batch_size"] == 1
    assert result["scale"]["batches_flushed"] == 4
    assert result["ingest_path"] == "cli_serial"
    assert "stage_ms" in result["scale"]


class BulkRecordingProvider(RecordingProvider):
    def __init__(self) -> None:
        super().__init__()
        self.bulk_calls: list[list[str]] = []
        self.upload_concurrency_seen: list[int] = []

    def supports_api_bulk_create(self) -> bool:
        return True

    def bulk_create_and_wait(
        self,
        *,
        notebook_ref: str,
        items: list[dict],
        upload_concurrency: int = 4,
        wait_timeout: float = 120.0,
    ) -> dict:
        self.bulk_calls.append([str(i.get("doc_id")) for i in items])
        self.upload_concurrency_seen.append(int(upload_concurrency))
        results = []
        for item in items:
            self._n += 1
            sid = f"src-{self._n}"
            title = str(item.get("title") or "")
            self.sources.append({"id": sid, "title": title, "status": "ready"})
            results.append(
                {
                    "doc_id": item.get("doc_id"),
                    "ok": True,
                    "source_id": sid,
                    "add_ms": 1,
                }
            )
        return {
            "ok": True,
            "ingest_path": "api_concurrent",
            "stage_ms": {"add": 10, "wait": 5},
            "results": results,
            "upload_concurrency": upload_concurrency,
        }


def test_apply_api_bulk_create_path(tmp_path: Path, monkeypatch):
    _seed(tmp_path)
    monkeypatch.setenv("NOTEBOOKLM_NOTEBOOK_OPM_TEST", "nb-api-bulk")
    config = load_config(tmp_path)
    target = ProviderTarget.from_ref(
        provider="notebooklm", notebook_alias="OPM-test", notebook_ref="nb-api-bulk"
    )
    provider = BulkRecordingProvider()
    result = apply_forward_sync(
        config,
        repo_root=tmp_path,
        target=target,
        notebook_ref="nb-api-bulk",
        provider=provider,
        ack_store=LocalMirrorAckStore(config.project_id, home=tmp_path),
        home=tmp_path,
        command="vibe knowledge sync --apply",
        ingest_path="api",
        upload_concurrency=4,
        batch_size=4,
    )
    assert result["ok"] is True
    assert result["ingest_path"] == "api_concurrent"
    assert result["upload_concurrency"] == 4
    assert result["scale"]["stage_ms"]["add"] == 10
    assert result["scale"]["stage_ms"]["wait"] == 5
    assert len(provider.bulk_calls) == 1
    assert len(provider.bulk_calls[0]) == 4
    assert provider.upload_concurrency_seen == [4]
    assert provider.wait_calls == []  # API path does not use CLI wait_source
    assert len(provider.sources) == 4
