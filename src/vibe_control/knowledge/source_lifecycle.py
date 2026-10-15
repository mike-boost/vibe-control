"""Provider-neutral source wait / verification lifecycle helpers."""

from __future__ import annotations

import time
from typing import Any, Callable

from vibe_control.knowledge.receipt import ReceiptStore


PROVIDER_NEUTRAL_STATUSES = (
    "ready",
    "processing",
    "preparing",
    "error",
    "unknown",
    "not_found",
    "timeout",
)


def normalize_status(value: str | None) -> str:
    text = (value or "unknown").strip().lower()
    if text in PROVIDER_NEUTRAL_STATUSES:
        return text
    if text in {"ok", "complete", "completed"}:
        return "ready"
    return "unknown"


def wait_for_source(
    source_id: str,
    *,
    poll_status: Callable[[str], dict[str, Any]],
    direct_wait: Callable[..., dict[str, Any]] | None = None,
    timeout_seconds: float = 120,
    interval_seconds: float = 3,
) -> dict[str, Any]:
    if direct_wait is not None:
        try:
            result = direct_wait(source_id, timeout=timeout_seconds, interval=interval_seconds)
            if result.get("ok") and normalize_status(result.get("status")) == "ready":
                return {
                    "ok": True,
                    "status": "ready",
                    "source_id": source_id,
                    "via": "direct_wait",
                }
            if normalize_status(result.get("status")) == "error":
                return {
                    "ok": False,
                    "status": "error",
                    "source_id": source_id,
                    "via": "direct_wait",
                }
            if result.get("code") == "SOURCE_WAIT_TIMEOUT" or normalize_status(
                result.get("status")
            ) == "timeout":
                return {
                    "ok": False,
                    "status": "timeout",
                    "code": "SOURCE_WAIT_TIMEOUT",
                    "source_id": source_id,
                    "via": "direct_wait",
                }
            elif result.get("ok") is False and result.get("status"):
                return {
                    "ok": False,
                    "status": normalize_status(result.get("status")),
                    "source_id": source_id,
                    "via": "direct_wait",
                    "code": result.get("code"),
                }
        except Exception:
            pass

    deadline = time.monotonic() + max(timeout_seconds, 0)
    last_status = "unknown"
    while True:
        probe = poll_status(source_id)
        if not probe.get("found", True):
            last_status = "not_found"
        else:
            last_status = normalize_status(probe.get("status"))
        if last_status == "ready":
            return {"ok": True, "status": "ready", "source_id": source_id, "via": "poll"}
        if last_status == "error":
            return {"ok": False, "status": "error", "source_id": source_id, "via": "poll"}
        if time.monotonic() >= deadline:
            return {
                "ok": False,
                "status": "timeout",
                "code": "SOURCE_WAIT_TIMEOUT",
                "source_id": source_id,
                "last_status": last_status,
                "via": "poll",
            }
        if interval_seconds > 0:
            time.sleep(interval_seconds)


def record_verified_add(
    store: ReceiptStore,
    *,
    verified: bool,
    project_id: str,
    provider: str,
    notebook_alias: str,
    notebook_ref_hash: str | None,
    doc_id: str,
    path_str: str,
    managed_name: str,
    current: dict[str, Any],
) -> dict[str, Any]:
    if not verified:
        return {"receipt_written": False, "reason": "verification_failed"}
    store.write_verified(
        project_id=project_id,
        provider=provider,
        notebook_alias=notebook_alias,
        notebook_ref_hash=notebook_ref_hash,
        doc_id=doc_id,
        path_str=path_str,
        managed_name=managed_name,
        current=current,
    )
    return {"receipt_written": True}


def identity_title_state(observed_title: str, *, managed_name: str, upload_filename: str) -> str | None:
    if observed_title == managed_name:
        return "exact"
    if observed_title == upload_filename:
        return "filename_fallback"
    return None
