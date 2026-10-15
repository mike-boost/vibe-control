"""Managed_key derivation and ManagedMarker parse/render (Phase 11A)."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from vibe_control.task.models import ManagedMarker

MARKER_SCHEMA = "vibe.task.v1"
MARKER_FENCE_START = "```vibe.task.v1"
MARKER_FENCE_END = "```"

REQUIRED_MARKER_FIELDS = (
    "schema",
    "project_id",
    "task_provider",
    "managed_key",
    "ssot_id",
    "ssot_path",
    "ssot_anchor",
    "task_kind",
    "ssot_snapshot_hash",
    "source_item_hash",
    "managed_by",
)

_FENCE_RE = re.compile(
    r"```vibe\.task\.v1\s*\n(?P<body>.*?)\n```",
    re.DOTALL,
)


class MarkerError(ValueError):
    """Malformed or contradictory managed marker."""

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def sha256_hex(text: str | bytes) -> str:
    if isinstance(text, str):
        raw = text.encode("utf-8")
    else:
        raw = text
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def compute_managed_key(
    *,
    project_id: str,
    ssot_id: str,
    ssot_path: str,
    ssot_anchor: str,
    task_kind: str,
) -> str:
    """Derive managed_key from the stable SSOT identity tuple only."""
    payload = "\n".join(
        [
            f"project_id={project_id}",
            f"ssot_id={ssot_id}",
            f"ssot_path={ssot_path}",
            f"ssot_anchor={ssot_anchor}",
            f"task_kind={task_kind}",
        ]
    )
    return sha256_hex(payload)


def render_marker(marker: ManagedMarker) -> str:
    lines = [f"{key}: {marker.to_dict()[key]}" for key in REQUIRED_MARKER_FIELDS]
    body = "\n".join(lines)
    return f"{MARKER_FENCE_START}\n{body}\n{MARKER_FENCE_END}"


def _parse_kv_block(body: str) -> dict[str, str]:
    data: dict[str, str] = {}
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise MarkerError("MARKER_MALFORMED", f"expected key: value line, got {line!r}")
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            raise MarkerError("MARKER_MALFORMED", "empty marker key")
        data[key] = value
    return data


def parse_marker_from_text(text: str) -> ManagedMarker | None:
    """Return ManagedMarker if a fence is present; None if absent; raise MarkerError if malformed."""
    raw = text or ""
    if "```vibe.task.v1" not in raw:
        return None
    match = _FENCE_RE.search(raw)
    if not match:
        raise MarkerError("MARKER_MALFORMED", "vibe.task.v1 fence present but unparseable")
    data = _parse_kv_block(match.group("body"))
    missing = [k for k in REQUIRED_MARKER_FIELDS if k not in data or str(data[k]).strip() == ""]
    if missing:
        raise MarkerError(
            "MARKER_INCOMPLETE",
            f"marker missing required fields: {', '.join(missing)}",
            {"missing": missing},
        )
    if data["schema"] != MARKER_SCHEMA:
        raise MarkerError(
            "MARKER_SCHEMA",
            f"unsupported marker schema: {data['schema']}",
            {"schema": data["schema"]},
        )
    marker = ManagedMarker(
        schema=data["schema"],
        project_id=data["project_id"],
        task_provider=data["task_provider"],
        managed_key=data["managed_key"],
        ssot_id=data["ssot_id"],
        ssot_path=data["ssot_path"],
        ssot_anchor=data["ssot_anchor"],
        task_kind=data["task_kind"],
        ssot_snapshot_hash=data["ssot_snapshot_hash"],
        source_item_hash=data["source_item_hash"],
        managed_by=data["managed_by"],
    )
    expected_key = compute_managed_key(
        project_id=marker.project_id,
        ssot_id=marker.ssot_id,
        ssot_path=marker.ssot_path,
        ssot_anchor=marker.ssot_anchor,
        task_kind=marker.task_kind,
    )
    if marker.managed_key != expected_key:
        raise MarkerError(
            "MARKER_KEY_MISMATCH",
            "marker managed_key does not match identity tuple",
            {"managed_key": marker.managed_key, "expected_managed_key": expected_key},
        )
    return marker


def marker_from_expected(
    *,
    project_id: str,
    ssot_id: str,
    ssot_path: str,
    ssot_anchor: str,
    task_kind: str,
    ssot_snapshot_hash: str,
    source_item_hash: str,
    task_provider: str = "beads",
    managed_by: str = "vibe-control",
) -> ManagedMarker:
    key = compute_managed_key(
        project_id=project_id,
        ssot_id=ssot_id,
        ssot_path=ssot_path,
        ssot_anchor=ssot_anchor,
        task_kind=task_kind,
    )
    return ManagedMarker(
        schema=MARKER_SCHEMA,
        project_id=project_id,
        task_provider=task_provider,
        managed_key=key,
        ssot_id=ssot_id,
        ssot_path=ssot_path,
        ssot_anchor=ssot_anchor,
        task_kind=task_kind,
        ssot_snapshot_hash=ssot_snapshot_hash,
        source_item_hash=source_item_hash,
        managed_by=managed_by,
    )
