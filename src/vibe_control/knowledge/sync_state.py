"""Knowledge sync state helpers (scaffold stub)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SyncState:
    """Placeholder for future NotebookLM sync state. Not persisted yet."""

    project_id: str | None = None
    synced: bool = False
    provider: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "synced": self.synced,
            "provider": self.provider,
            "details": dict(self.details),
            "note": "sync state is not implemented in this scaffold pass",
        }


def load_sync_state(project_id: str | None = None) -> SyncState:
    return SyncState(project_id=project_id, synced=False, provider=None)
