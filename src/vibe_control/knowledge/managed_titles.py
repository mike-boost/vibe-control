"""Managed NotebookLM source title parsing/formatting."""

from __future__ import annotations

import re
from dataclasses import dataclass


MANAGED_TITLE_RE = re.compile(
    r"^\[vibe:(?P<project_id>[^:\]]+):(?P<doc_id>[^\]]+)\]\s*(?P<title>.*)$"
)


@dataclass
class ManagedTitle:
    project_id: str
    doc_id: str
    title: str

    @property
    def formatted(self) -> str:
        return format_managed_title(self.project_id, self.doc_id, self.title)


def format_managed_title(project_id: str, doc_id: str, title: str) -> str:
    return f"[vibe:{project_id}:{doc_id}] {title}"


def parse_managed_title(text: str) -> ManagedTitle | None:
    match = MANAGED_TITLE_RE.match((text or "").strip())
    if not match:
        return None
    return ManagedTitle(
        project_id=match.group("project_id"),
        doc_id=match.group("doc_id"),
        title=(match.group("title") or "").strip(),
    )
