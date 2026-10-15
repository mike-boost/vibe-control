"""Bounded micro-batch + wait coalescing for knowledge sync apply."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Literal

WaitMode = Literal["serial", "multi"]

DEFAULT_BATCH_SIZE = 1
MAX_BATCH_SIZE = 20  # align with notebooklm-py MAX_BATCH_URLS spirit
DEFAULT_WAIT_MODE: WaitMode = "serial"
DEFAULT_BATCH_PACE_MS = 0


def normalize_batch_size(value: int | None) -> int:
    if value is None:
        return DEFAULT_BATCH_SIZE
    n = int(value)
    if n < 1:
        return DEFAULT_BATCH_SIZE
    return min(n, MAX_BATCH_SIZE)


def normalize_wait_mode(value: str | None) -> WaitMode:
    v = str(value or DEFAULT_WAIT_MODE).strip().lower()
    return "multi" if v == "multi" else "serial"


def wait_many(
    wait_one: Callable[..., dict[str, Any]],
    *,
    notebook_ref: str,
    source_ids: list[str],
    wait_mode: WaitMode = DEFAULT_WAIT_MODE,
    timeout: float = 120,
) -> dict[str, dict[str, Any]]:
    """Wait for many source ids.

    ``serial``: sequential wait_one calls.
    ``multi``: concurrent wait_one calls (CLI is single-id; we coalesce in-process).
    """
    ids = [str(s) for s in source_ids if s]
    if not ids:
        return {}
    mode = normalize_wait_mode(wait_mode)
    if mode != "multi" or len(ids) == 1:
        out: dict[str, dict[str, Any]] = {}
        for sid in ids:
            out[sid] = wait_one(notebook_ref=notebook_ref, source_id=sid, timeout=timeout)
        return out

    out = {}
    with ThreadPoolExecutor(max_workers=min(len(ids), MAX_BATCH_SIZE)) as pool:
        futures = {
            pool.submit(wait_one, notebook_ref=notebook_ref, source_id=sid, timeout=timeout): sid
            for sid in ids
        }
        for fut in as_completed(futures):
            sid = futures[fut]
            try:
                out[sid] = fut.result()
            except Exception as exc:  # provider transport
                out[sid] = {"ok": False, "code": "WAIT_FAILED", "message": str(exc)}
    return out
