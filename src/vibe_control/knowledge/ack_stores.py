"""Provider-side remote_ack stores (NotebookLM note + local mirror fallback)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from vibe_control.knowledge.provider_target import ProviderTarget
from vibe_control.knowledge.receipt_scope import scoped_state_dir
from vibe_control.knowledge.remote_ack import FakeAckStore
from vibe_control.knowledge.remote_ack_guard import assert_ack_write_allowed


def remote_ack_mirror_path(
    project_id: str, target: ProviderTarget, *, home: Path | None = None
) -> Path:
    return scoped_state_dir(project_id, target, home=home) / "remote-ack.json"


class LocalMirrorAckStore:
    """Target-scoped ack watermark mirrored locally.

    Phase 8.0 uses this when NotebookLM note CLI is unavailable. It is still
    target-scoped and never consulted across notebook targets.

    Important: this is NOT a NotebookLM remote note. Callers must expose
    ack_store_kind=local_mirror and notebooklm_note_written=false.
    """

    ack_store_kind = "local_mirror"
    notebooklm_note_written = False

    def __init__(self, project_id: str, *, home: Path | None = None, command: str | None = None):
        self.project_id = project_id
        self.home = home
        self.command = command
        self.write_count = 0

    def persistence_info(self) -> dict[str, Any]:
        return {
            "ack_store_kind": "local_mirror",
            "notebooklm_note_written": False,
            "notebooklm_note_available": False,
            "note": "Ack watermark stored in target-scoped local mirror; not a NotebookLM remote note.",
        }

    def read_ack(self, target: ProviderTarget) -> dict[str, Any] | None:
        path = remote_ack_mirror_path(self.project_id, target, home=self.home)
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        if data.get("target_key_hash") and data["target_key_hash"] != target.target_key_hash:
            return None
        return data

    def write_ack(self, target: ProviderTarget, ack: dict[str, Any]) -> None:
        if self.command:
            assert_ack_write_allowed(command=self.command)
        payload = dict(ack)
        payload["target_key_hash"] = target.target_key_hash
        payload["notebook_alias"] = target.notebook_alias
        payload["notebook_ref_hash"] = target.notebook_ref_hash
        payload["provider"] = target.provider
        path = remote_ack_mirror_path(self.project_id, target, home=self.home)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp, path)
        self.write_count += 1


class NotebookLMNoteAckStore:
    """Attempt NotebookLM note read/write; fall back to local mirror.

    Note operations are best-effort. Failures do not invent cross-target acks.
    """

    ACK_DOC_ID = "remote_ack"

    def __init__(
        self,
        project_id: str,
        provider: Any,
        *,
        notebook_ref: str,
        home: Path | None = None,
        command: str | None = None,
    ):
        self.project_id = project_id
        self.provider = provider
        self.notebook_ref = notebook_ref
        self.mirror = LocalMirrorAckStore(project_id, home=home, command=command)
        self.command = command
        self.write_count = 0

    def _managed_title(self) -> str:
        from vibe_control.knowledge.managed_names import managed_name

        return managed_name(self.project_id, self.ACK_DOC_ID)

    def read_ack(self, target: ProviderTarget) -> dict[str, Any] | None:
        # Prefer local mirror for deterministic Phase 8.0; optionally confirm note exists.
        mirrored = self.mirror.read_ack(target)
        if mirrored is not None:
            return mirrored
        # Readonly probe of note/source list for managed ack title (metadata only).
        list_fn = getattr(self.provider, "list_sources", None)
        if list_fn is None:
            return None
        try:
            listed = list_fn(notebook_ref=self.notebook_ref)
        except Exception:
            return None
        title = self._managed_title()
        for src in listed.get("sources") or []:
            if str(src.get("title") or "") == title or str(src.get("title") or "").startswith(title):
                # Presence alone is not a full ack; without note body API, fall through.
                break
        return None

    def write_ack(self, target: ProviderTarget, ack: dict[str, Any]) -> None:
        if self.command:
            assert_ack_write_allowed(command=self.command)
        # Phase 8.0: NotebookLM native note CLI is unavailable / not wired.
        # Persist target-scoped local mirror only. Do not claim a remote note write.
        self.mirror.write_ack(target, ack)
        self.write_count += 1
        self._last_note_written = False

    def persistence_info(self) -> dict[str, Any]:
        return {
            "ack_store_kind": "local_mirror",
            "notebooklm_note_written": False,
            "notebooklm_note_available": False,
            "note": (
                "Phase 8.0 uses target-scoped local ack mirror fallback. "
                "No NotebookLM remote note was written."
            ),
        }


__all__ = [
    "FakeAckStore",
    "LocalMirrorAckStore",
    "NotebookLMNoteAckStore",
    "remote_ack_mirror_path",
]
