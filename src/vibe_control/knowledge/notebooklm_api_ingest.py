"""NotebookLM Python API concurrent file ingest (multi-file throughput path).

CLI ``source add`` is single-file and serial when invoked one-by-one.
notebooklm-py already exposes the correct pipeline:

  concurrent add_file(wait=False) ≤ max_concurrent_uploads
  → one wait_for_sources(ids)

This module is the load-bearing adapter for knowledge multi-file sync.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any, Callable, Literal

# Measured sweet spot on SE ~150–200KB corpus (2026-07-18): 8 ≈ 12, both beat 4.
# Cap remains 16; this is in-flight single-file uploads, not a bulk RPC.
DEFAULT_UPLOAD_CONCURRENCY = 8
MAX_UPLOAD_CONCURRENCY = 16
IngestPath = Literal["auto", "api", "cli"]


def normalize_upload_concurrency(value: int | None) -> int:
    if value is None:
        return DEFAULT_UPLOAD_CONCURRENCY
    n = int(value)
    if n < 1:
        return DEFAULT_UPLOAD_CONCURRENCY
    return min(n, MAX_UPLOAD_CONCURRENCY)


def normalize_ingest_path(value: str | None) -> IngestPath:
    v = str(value or "auto").strip().lower()
    if v in ("api", "cli"):
        return v  # type: ignore[return-value]
    return "auto"


def notebooklm_api_available() -> bool:
    try:
        from notebooklm import NotebookLMClient  # noqa: F401

        return True
    except Exception:
        return False


def resolve_ingest_path(
    requested: str | None,
    *,
    api_available: bool | None = None,
) -> Literal["api", "cli"]:
    """Resolve auto|api|cli into a concrete path."""
    path = normalize_ingest_path(requested)
    available = notebooklm_api_available() if api_available is None else bool(api_available)
    if path == "cli":
        return "cli"
    if path == "api":
        if not available:
            raise RuntimeError(
                "ingest_path=api requested but notebooklm Python package is not importable"
            )
        return "api"
    return "api" if available else "cli"


ClientFactory = Callable[[int], Any]


async def _bulk_add_and_wait(
    client: Any,
    *,
    notebook_id: str,
    items: list[dict[str, Any]],
    wait_timeout: float,
) -> dict[str, Any]:
    """Run concurrent add_file(wait=False) then wait_for_sources.

    ``items`` entries: ``doc_id``, ``file_path``, ``title``.
    """

    async def add_one(item: dict[str, Any]) -> dict[str, Any]:
        doc_id = str(item.get("doc_id") or "")
        file_path = Path(str(item.get("file_path") or ""))
        title = str(item.get("title") or "")
        t0 = time.perf_counter()
        try:
            src = await client.sources.add_file(
                notebook_id,
                file_path,
                title=title,
                wait=False,
            )
            sid = getattr(src, "id", None) or (src.get("id") if isinstance(src, dict) else None)
            if not sid:
                return {
                    "doc_id": doc_id,
                    "ok": False,
                    "code": "ADD_FAILED",
                    "message": "add_file returned no source id",
                    "add_ms": int((time.perf_counter() - t0) * 1000),
                }
            return {
                "doc_id": doc_id,
                "ok": True,
                "source_id": str(sid),
                "add_ms": int((time.perf_counter() - t0) * 1000),
            }
        except Exception as exc:
            return {
                "doc_id": doc_id,
                "ok": False,
                "code": "ADD_FAILED",
                "message": str(exc),
                "add_ms": int((time.perf_counter() - t0) * 1000),
            }

    t_add0 = time.perf_counter()
    results: list[dict[str, Any]] = list(await asyncio.gather(*[add_one(i) for i in items]))
    add_ms = int((time.perf_counter() - t_add0) * 1000)

    ok_ids = [str(r["source_id"]) for r in results if r.get("ok") and r.get("source_id")]
    t_wait0 = time.perf_counter()
    wait_message: str | None = None
    if ok_ids:
        try:
            await client.sources.wait_for_sources(
                notebook_id,
                ok_ids,
                timeout=float(wait_timeout),
            )
        except Exception:
            # Per-id fallback so one slow/failed source does not discard siblings blindly.
            for r in results:
                if not r.get("ok") or not r.get("source_id"):
                    continue
                try:
                    await client.sources.wait_until_ready(
                        notebook_id,
                        str(r["source_id"]),
                        timeout=float(wait_timeout),
                    )
                except Exception as exc:
                    r["ok"] = False
                    r["code"] = "WAIT_FAILED"
                    r["message"] = str(exc)
                    wait_message = str(exc)
    wait_ms = int((time.perf_counter() - t_wait0) * 1000)

    all_ok = bool(results) and all(bool(r.get("ok")) for r in results)
    return {
        "ok": all_ok,
        "ingest_path": "api_concurrent",
        "stage_ms": {"add": add_ms, "wait": wait_ms},
        "results": results,
        "wait_message": wait_message,
    }


def bulk_add_files_and_wait(
    *,
    notebook_id: str,
    items: list[dict[str, Any]],
    upload_concurrency: int | None = None,
    wait_timeout: float = 120.0,
    client_factory: ClientFactory | None = None,
) -> dict[str, Any]:
    """Sync entry: concurrent API uploads + multi-id wait with stage timers.

    ``client_factory(concurrency)`` may return an async context manager yielding a client
    (tests inject fakes). Default uses ``NotebookLMClient.from_storage``.
    """
    if not items:
        return {
            "ok": True,
            "ingest_path": "api_concurrent",
            "stage_ms": {"add": 0, "wait": 0},
            "results": [],
            "upload_concurrency": normalize_upload_concurrency(upload_concurrency),
        }

    concurrency = normalize_upload_concurrency(upload_concurrency)

    async def _run() -> dict[str, Any]:
        if client_factory is not None:
            cm = client_factory(concurrency)
            async with cm as client:
                out = await _bulk_add_and_wait(
                    client,
                    notebook_id=notebook_id,
                    items=items,
                    wait_timeout=wait_timeout,
                )
        else:
            from notebooklm import NotebookLMClient

            async with NotebookLMClient.from_storage(
                max_concurrent_uploads=concurrency
            ) as client:
                out = await _bulk_add_and_wait(
                    client,
                    notebook_id=notebook_id,
                    items=items,
                    wait_timeout=wait_timeout,
                )
        out["upload_concurrency"] = concurrency
        return out

    return asyncio.run(_run())
