"""Markdown heading/section chunking with Read-aligned line numbers."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

CHUNKING_VERSION = "heading_v1"
MAX_SECTION_LINES = 120
WINDOW_LINES = 80
WINDOW_OVERLAP = 16

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


@dataclass(frozen=True)
class TextChunk:
    chunk_id: str
    doc_id: str
    path: str
    title: str
    heading: str
    line_start: int
    line_end: int
    body: str


def normalize_newlines(text: str) -> str:
    """Normalize CRLF to LF; keep other control chars as content (not line breaks)."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def split_read_lines(text: str) -> list[str]:
    """Split like Cursor Read (1-based over ``split('\\n')``), after CRLF normalize."""
    return normalize_newlines(text).split("\n")


def _chunk_id(doc_id: str, line_start: int, line_end: int, heading: str) -> str:
    raw = f"{doc_id}\n{line_start}\n{line_end}\n{heading}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def _emit_windows(
    *,
    doc_id: str,
    path: str,
    title: str,
    heading: str,
    lines: list[str],
    start: int,
    end: int,
) -> list[TextChunk]:
    """Emit one or more chunks for lines[start:end] (0-based slice end exclusive)."""
    length = end - start
    if length <= 0:
        return []
    body_probe = "\n".join(lines[start:end]).strip()
    if not body_probe:
        return []

    if length <= MAX_SECTION_LINES:
        body = "\n".join(lines[start:end])
        return [
            TextChunk(
                chunk_id=_chunk_id(doc_id, start + 1, end, heading),
                doc_id=doc_id,
                path=path,
                title=title,
                heading=heading,
                line_start=start + 1,
                line_end=end,
                body=body,
            )
        ]

    out: list[TextChunk] = []
    cursor = start
    while cursor < end:
        win_end = min(cursor + WINDOW_LINES, end)
        body = "\n".join(lines[cursor:win_end])
        if body.strip():
            out.append(
                TextChunk(
                    chunk_id=_chunk_id(doc_id, cursor + 1, win_end, heading),
                    doc_id=doc_id,
                    path=path,
                    title=title,
                    heading=heading,
                    line_start=cursor + 1,
                    line_end=win_end,
                    body=body,
                )
            )
        if win_end >= end:
            break
        cursor = max(cursor + 1, win_end - WINDOW_OVERLAP)
    return out


def chunk_markdown_document(
    *,
    doc_id: str,
    path: str,
    title: str,
    text: str,
) -> list[TextChunk]:
    lines = split_read_lines(text)
    if not lines or (len(lines) == 1 and lines[0] == ""):
        return []

    headings: list[tuple[int, int, str]] = []  # (line_idx0, level, title)
    for idx, line in enumerate(lines):
        match = _HEADING_RE.match(line)
        if match:
            level = len(match.group(1))
            headings.append((idx, level, match.group(2).strip()))

    if not headings:
        return _emit_windows(
            doc_id=doc_id,
            path=path,
            title=title,
            heading="",
            lines=lines,
            start=0,
            end=len(lines),
        )

    chunks: list[TextChunk] = []
    first_heading_idx = headings[0][0]
    if first_heading_idx > 0:
        chunks.extend(
            _emit_windows(
                doc_id=doc_id,
                path=path,
                title=title,
                heading="(preamble)",
                lines=lines,
                start=0,
                end=first_heading_idx,
            )
        )

    for i, (start_idx, level, heading_title) in enumerate(headings):
        end_idx = len(lines)
        for j in range(i + 1, len(headings)):
            next_idx, next_level, _ = headings[j]
            if next_level <= level:
                end_idx = next_idx
                break
        chunks.extend(
            _emit_windows(
                doc_id=doc_id,
                path=path,
                title=title,
                heading=heading_title,
                lines=lines,
                start=start_idx,
                end=end_idx,
            )
        )
    return chunks
