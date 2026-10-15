"""Local self-grill session receipts (vibe.grill.session.v1).

Consumer-repo runtime only — not SSOT, not closeout, not Knowledge sync.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "vibe.grill.session.v1"
DEFAULT_ROOT_REL = "runtime/vibe-grill"
LOOP_STATUSES = frozenset({"IN_PROGRESS", "EXHAUSTED", "BLOCKED_ON_LIVE"})
ACTIVE_NAME = "active.json"


class GrillSessionError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def grill_root(repo_root: Path) -> Path:
    return (repo_root / DEFAULT_ROOT_REL).resolve()


def sessions_dir(repo_root: Path) -> Path:
    return grill_root(repo_root) / "sessions"


def active_path(repo_root: Path) -> Path:
    return grill_root(repo_root) / ACTIVE_NAME


def session_path(repo_root: Path, grill_id: str) -> Path:
    return sessions_dir(repo_root) / f"{grill_id}.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_grill_id(*, now: datetime | None = None) -> str:
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%d-%H%M%S")
    return f"grill-{stamp}"


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise GrillSessionError("GRILL_SESSION_INVALID", f"Invalid JSON object: {path}")
    return raw


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_active_pointer(repo_root: Path) -> str | None:
    data = _read_json(active_path(repo_root))
    if not data:
        return None
    gid = data.get("grill_id")
    return str(gid) if gid else None


def write_active_pointer(repo_root: Path, grill_id: str | None) -> None:
    _write_json(active_path(repo_root), {"grill_id": grill_id})


def load_session(repo_root: Path, grill_id: str) -> dict[str, Any]:
    path = session_path(repo_root, grill_id)
    data = _read_json(path)
    if not data:
        raise GrillSessionError(
            "GRILL_SESSION_NOT_FOUND",
            f"No grill session file for {grill_id}",
            {"grill_id": grill_id, "path": path.as_posix()},
        )
    return data


def load_active_session(repo_root: Path) -> dict[str, Any] | None:
    """Load the active grill session without repairing a dangling pointer.

    Readonly Progress/Brief must not clear ``active.json`` as a side effect.
    Explicit open/close/repair paths may overwrite the pointer intentionally.
    """
    gid = read_active_pointer(repo_root)
    if not gid:
        return None
    try:
        return load_session(repo_root, gid)
    except GrillSessionError:
        return None


def clear_dangling_active_pointer(repo_root: Path) -> bool:
    """Clear active.json when it points at a missing/invalid session. Returns True if cleared."""
    gid = read_active_pointer(repo_root)
    if not gid:
        return False
    try:
        load_session(repo_root, gid)
    except GrillSessionError:
        write_active_pointer(repo_root, None)
        return True
    return False


def active_in_progress(repo_root: Path) -> dict[str, Any] | None:
    sess = load_active_session(repo_root)
    if not sess:
        return None
    if str(sess.get("loop_status") or "") != "IN_PROGRESS":
        return None
    return sess


def open_session(
    repo_root: Path,
    *,
    thesis: str,
    force_new: bool = False,
) -> dict[str, Any]:
    thesis_s = str(thesis or "").strip()
    if not thesis_s:
        raise GrillSessionError("GRILL_THESIS_REQUIRED", "thesis is required to open a grill")

    # Explicit open may clear a dangling pointer before creating/reusing.
    clear_dangling_active_pointer(repo_root)
    current = load_active_session(repo_root)
    if current and str(current.get("loop_status")) == "IN_PROGRESS":
        if not force_new:
            reused = dict(current)
            reused["session_action"] = "reused"
            return reused
        # Force: close previous as blocked
        close_session(
            repo_root,
            status="BLOCKED_ON_LIVE",
            grill_id=str(current["grill_id"]),
            note="superseded by force-new open",
        )

    now = _utc_now()
    gid = new_grill_id()
    session = {
        "schema": SCHEMA,
        "grill_id": gid,
        "round_id": 0,
        "loop_status": "IN_PROGRESS",
        "thesis": thesis_s,
        "opened_at": now,
        "updated_at": now,
        "claim_count": 0,
        "note": None,
    }
    _write_json(session_path(repo_root, gid), session)
    write_active_pointer(repo_root, gid)
    created = dict(session)
    created["session_action"] = "created"
    return created


def checkpoint_session(
    repo_root: Path,
    *,
    round_id: int | None = None,
    loop_status: str | None = None,
    claim_count: int | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    sess = load_active_session(repo_root)
    if not sess:
        raise GrillSessionError("GRILL_NO_ACTIVE", "No active grill session")
    if str(sess.get("loop_status")) != "IN_PROGRESS":
        raise GrillSessionError(
            "GRILL_NOT_IN_PROGRESS",
            "Active session is not IN_PROGRESS; open a new grill or clear active",
            {"grill_id": sess.get("grill_id"), "loop_status": sess.get("loop_status")},
        )

    if round_id is not None:
        if int(round_id) < 0:
            raise GrillSessionError("GRILL_ROUND_INVALID", "round_id must be >= 0")
        sess["round_id"] = int(round_id)
    else:
        sess["round_id"] = int(sess.get("round_id") or 0) + 1

    if loop_status is not None:
        status = str(loop_status).strip().upper()
        if status not in LOOP_STATUSES:
            raise GrillSessionError(
                "GRILL_LOOP_STATUS_INVALID",
                f"loop_status must be one of {sorted(LOOP_STATUSES)}",
            )
        if status != "IN_PROGRESS":
            # Use close_session for terminal states
            return close_session(repo_root, status=status, note=note)
        sess["loop_status"] = status

    if claim_count is not None:
        sess["claim_count"] = max(0, int(claim_count))
    if note is not None:
        sess["note"] = note
    sess["updated_at"] = _utc_now()
    _write_json(session_path(repo_root, str(sess["grill_id"])), sess)
    return sess


def close_session(
    repo_root: Path,
    *,
    status: str,
    grill_id: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    status_u = str(status).strip().upper()
    if status_u not in {"EXHAUSTED", "BLOCKED_ON_LIVE"}:
        raise GrillSessionError(
            "GRILL_CLOSE_STATUS_INVALID",
            "close status must be EXHAUSTED or BLOCKED_ON_LIVE",
        )
    gid = grill_id or read_active_pointer(repo_root)
    if not gid:
        raise GrillSessionError("GRILL_NO_ACTIVE", "No active grill session to close")
    sess = load_session(repo_root, gid)
    sess["loop_status"] = status_u
    sess["updated_at"] = _utc_now()
    if note is not None:
        sess["note"] = note
    _write_json(session_path(repo_root, gid), sess)
    if read_active_pointer(repo_root) == gid:
        write_active_pointer(repo_root, None)
    return sess


def status_payload(repo_root: Path) -> dict[str, Any]:
    active = load_active_session(repo_root)
    in_prog = (
        active if active and str(active.get("loop_status")) == "IN_PROGRESS" else None
    )
    return {
        "root": DEFAULT_ROOT_REL,
        "active_grill_id": (active or {}).get("grill_id") if active else None,
        "in_progress": bool(in_prog),
        "session": active,
    }
