"""NotebookLM provider adapter.

CLI command handling for NotebookLM (`source add` / `list` / `get` / `wait` / `delete`)
is implemented in this provider layer. The concrete class lives in
`vibe_control.knowledge.notebooklm_provider` for import compatibility and is
re-exported here so harness boundary tests can locate provider-owned commands.
"""

from __future__ import annotations

from vibe_control.knowledge.notebooklm_provider import (  # noqa: F401
    NotebookLMProvider,
    NotebookLMStatus,
)

# Explicit command surface owned by this provider (not skills / neutral layer).
NOTEBOOKLM_SOURCE_COMMANDS = (
    "notebooklm source add",
    "notebooklm source list",
    "notebooklm source get",
    "notebooklm source wait",
    "notebooklm source delete",
)

__all__ = ["NotebookLMProvider", "NotebookLMStatus", "NOTEBOOKLM_SOURCE_COMMANDS"]
