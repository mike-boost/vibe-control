"""llm-wiki provider stub."""

from __future__ import annotations

from typing import Any


class LlmWikiProvider:
    def status(self) -> dict[str, Any]:
        return {
            "ok": False,
            "code": "PROVIDER_NOT_IMPLEMENTED",
            "message": "llm-wiki provider is not implemented in Phase 4F",
            "provider": "llm-wiki",
        }
