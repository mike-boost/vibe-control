"""API concurrent ingest adapter (fake client; no real NotebookLM)."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path

from vibe_control.knowledge.notebooklm_api_ingest import (
    bulk_add_files_and_wait,
    normalize_upload_concurrency,
    resolve_ingest_path,
)


def test_normalize_upload_concurrency_bounds():
    assert normalize_upload_concurrency(None) == 8
    assert normalize_upload_concurrency(0) == 8
    assert normalize_upload_concurrency(4) == 4
    assert normalize_upload_concurrency(8) == 8
    assert normalize_upload_concurrency(100) == 16


def test_resolve_ingest_path_auto():
    assert resolve_ingest_path("auto", api_available=True) == "api"
    assert resolve_ingest_path("auto", api_available=False) == "cli"
    assert resolve_ingest_path("cli", api_available=True) == "cli"
    assert resolve_ingest_path("api", api_available=True) == "api"


def test_resolve_ingest_path_api_requires_package():
    try:
        resolve_ingest_path("api", api_available=False)
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "not importable" in str(exc)


@dataclass
class _FakeSource:
    id: str


class _FakeSources:
    def __init__(self, *, delay: float = 0.12) -> None:
        self.delay = delay
        self.adds: list[str] = []
        self.max_inflight = 0
        self._inflight = 0
        self._n = 0

    async def add_file(self, notebook_id: str, file_path, *, title=None, wait=False, **kwargs):
        self._inflight += 1
        self.max_inflight = max(self.max_inflight, self._inflight)
        self.adds.append(str(file_path))
        try:
            await asyncio.sleep(self.delay)
            self._n += 1
            return _FakeSource(id=f"src-{self._n}")
        finally:
            self._inflight -= 1

    async def wait_for_sources(self, notebook_id: str, source_ids: list[str], timeout: float = 120.0, **kwargs):
        await asyncio.sleep(0.05)
        return [_FakeSource(id=s) for s in source_ids]

    async def wait_until_ready(self, notebook_id: str, source_id: str, timeout: float = 120.0, **kwargs):
        await asyncio.sleep(0.01)
        return _FakeSource(id=source_id)


class _FakeClient:
    def __init__(self, sources: _FakeSources) -> None:
        self.sources = sources


class _FakeCM:
    def __init__(self, client: _FakeClient) -> None:
        self._client = client

    async def __aenter__(self):
        return self._client

    async def __aexit__(self, *args):
        return False


def test_bulk_add_files_and_wait_is_concurrent(tmp_path: Path):
    files = []
    for i in range(4):
        p = tmp_path / f"f{i}.md"
        p.write_text(f"# {i}\n", encoding="utf-8")
        files.append(p)

    sources = _FakeSources(delay=0.12)

    def factory(_concurrency: int):
        return _FakeCM(_FakeClient(sources))

    t0 = time.perf_counter()
    out = bulk_add_files_and_wait(
        notebook_id="nb",
        items=[
            {"doc_id": f"d{i}", "file_path": str(files[i]), "title": f"t{i}"}
            for i in range(4)
        ],
        upload_concurrency=4,
        client_factory=factory,
    )
    elapsed = time.perf_counter() - t0
    assert out["ok"] is True
    assert out["ingest_path"] == "api_concurrent"
    assert out["upload_concurrency"] == 4
    assert len(out["results"]) == 4
    assert all(r.get("ok") and r.get("source_id") for r in out["results"])
    assert out["stage_ms"]["add"] > 0
    assert out["stage_ms"]["wait"] > 0
    # 4 * 0.12 serial ≈ 0.48s; concurrent should be closer to ~0.12 + wait
    assert elapsed < 0.4
    assert sources.max_inflight >= 2
