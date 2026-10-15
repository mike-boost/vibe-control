"""Tests for local_fts markdown chunking (Read-aligned line numbers)."""

from __future__ import annotations

from vibe_control.knowledge.local_fts.chunking import (
    chunk_markdown_document,
    split_read_lines,
)


def test_split_read_lines_trailing_newline_keeps_empty_last():
    lines = split_read_lines("a\nb\n")
    assert lines == ["a", "b", ""]


def test_split_read_lines_crlf_normalized():
    lines = split_read_lines("a\r\nb\r\nc")
    assert lines == ["a", "b", "c"]


def test_split_read_lines_form_feed_not_line_break():
    lines = split_read_lines("a\x0cb\nc")
    assert lines == ["a\x0cb", "c"]


def test_heading_chunk_line_ranges():
    text = (
        "# Title\n"
        "\n"
        "Intro line\n"
        "\n"
        "## Approval Matrix\n"
        "\n"
        "- git push\n"
        "- destructive delete\n"
        "\n"
        "## Other\n"
        "tail\n"
    )
    chunks = chunk_markdown_document(
        doc_id="spec",
        path="docs/spec.md",
        title="Spec",
        text=text,
    )
    by_heading = {c.heading: c for c in chunks}
    assert "Approval Matrix" in by_heading
    am = by_heading["Approval Matrix"]
    assert am.line_start == 5
    assert "git push" in am.body
    # Section ends before ## Other
    assert am.line_end == 8 or "Other" not in am.body


def test_nested_heading_does_not_end_parent_early():
    text = "# A\n" "body\n" "## B\n" "inner\n" "### C\n" "deep\n" "## D\n" "next\n"
    chunks = chunk_markdown_document(
        doc_id="d", path="p.md", title="t", text=text
    )
    b = next(c for c in chunks if c.heading == "B")
    assert "deep" in b.body
    assert "next" not in b.body


def test_long_section_window_split():
    lines = ["# Big"] + [f"line {i}" for i in range(1, 200)]
    text = "\n".join(lines)
    chunks = chunk_markdown_document(
        doc_id="d", path="p.md", title="t", text=text
    )
    assert len(chunks) > 1
    assert all(c.line_end >= c.line_start for c in chunks)
