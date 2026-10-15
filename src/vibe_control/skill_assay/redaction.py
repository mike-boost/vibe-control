"""Secret redaction for Skill Assay receipts."""

from __future__ import annotations

import re
from typing import Any

_SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)\bbearer\s+\S+"), "[REDACTED_BEARER]"),
    (re.compile(r"(?i)(authorization:\s*)\S+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)\b(ghp_|gho_|ghu_|ghs_|ghr_|github_pat_)[A-Za-z0-9_]{8,}"), "[REDACTED]"),
    (re.compile(r"(?i)\b(sk-[A-Za-z0-9]{16,})"), "[REDACTED]"),
    (re.compile(r"(?i)\b(cursor_?[A-Za-z0-9]{16,})"), "[REDACTED]"),
    (
        re.compile(
            r"(?i)(COPILOT_GITHUB_TOKEN|GH_TOKEN|GITHUB_TOKEN|CURSOR_API_KEY)\s*=\s*\S+"
        ),
        r"\1=[REDACTED]",
    ),
    (re.compile(r"(?i)(https?://)([^/\s:@]+):([^/\s@]+)@"), r"\1[REDACTED]:[REDACTED]@"),
)

_HOME_PATH = re.compile(r"(?i)(/(?:Users|home)/)([^/\s]+)")
DEFAULT_TEXT_LIMIT = 4000
DEFAULT_EVENT_LIMIT = 80


def redact_text(text: str, *, limit: int = DEFAULT_TEXT_LIMIT) -> str:
    out = text or ""
    for pattern, repl in _SECRET_PATTERNS:
        out = pattern.sub(repl, out)
    out = _HOME_PATH.sub(r"\1[REDACTED_USER]", out)
    if len(out) > limit:
        out = out[:limit] + "\n...[truncated]"
    return out


def redact_value(value: Any, *, depth: int = 0) -> Any:
    if depth > 6:
        return "[REDACTED_DEPTH]"
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact_value(v, depth=depth + 1) for v in value[:DEFAULT_EVENT_LIMIT]]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in list(value.items())[:DEFAULT_EVENT_LIMIT]:
            lowered = str(key).lower()
            if any(
                tok in lowered
                for tok in ("token", "password", "secret", "authorization", "cookie")
            ):
                out[str(key)] = "[REDACTED]"
            else:
                out[str(key)] = redact_value(item, depth=depth + 1)
        return out
    return value


def truncate_events(
    events: list[dict[str, Any]], *, limit: int = DEFAULT_EVENT_LIMIT
) -> list[dict[str, Any]]:
    cleaned = [redact_value(e) for e in events if isinstance(e, dict)]
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit] + [{"type": "truncated", "dropped": len(cleaned) - limit}]
