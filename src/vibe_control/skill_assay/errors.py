"""Skill Assay domain errors."""

from __future__ import annotations

from typing import Any


class SkillAssayError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
