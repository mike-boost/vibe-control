"""Guard: remote_ack writes only on explicit mutation commands."""

from __future__ import annotations

_ALLOWED_WRITE_PREFIXES = (
    "vibe knowledge sync --apply",
    "vibe knowledge retry --apply",
    "vibe spec publish",
)


def assert_ack_write_allowed(*, command: str) -> None:
    text = (command or "").strip()
    if any(text.startswith(prefix) or text == prefix for prefix in _ALLOWED_WRITE_PREFIXES):
        return
    # also allow exact apply forms without spaces quirks
    normalized = " ".join(text.split())
    if normalized in {
        "vibe knowledge sync --apply",
        "vibe knowledge retry --apply",
    } or normalized.startswith("vibe spec publish"):
        return
    raise PermissionError(
        f"write_ack is forbidden for command {command!r}; "
        "allowed only after verified sync/retry/publish mutation paths"
    )
