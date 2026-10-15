"""Target-scoped remote_ack stores (Phase 8 watermark)."""

from __future__ import annotations

from typing import Any, Protocol

from vibe_control.knowledge.provider_target import ProviderTarget


class AckStore(Protocol):
    def read_ack(self, target: ProviderTarget) -> dict[str, Any] | None: ...

    def write_ack(self, target: ProviderTarget, ack: dict[str, Any]) -> None: ...


class FakeAckStore:
    """In-memory ack store keyed by target_key_hash (tests / fake provider)."""

    ack_store_kind = "fake"
    notebooklm_note_written = False

    def __init__(self) -> None:
        self._by_target: dict[str, dict[str, Any]] = {}
        self.write_count = 0

    def read_ack(self, target: ProviderTarget) -> dict[str, Any] | None:
        return self._by_target.get(target.target_key_hash)

    def write_ack(self, target: ProviderTarget, ack: dict[str, Any]) -> None:
        payload = dict(ack)
        payload["target_key_hash"] = target.target_key_hash
        payload["notebook_alias"] = target.notebook_alias
        payload["notebook_ref_hash"] = target.notebook_ref_hash
        payload["provider"] = target.provider
        self._by_target[target.target_key_hash] = payload
        self.write_count += 1

    def persistence_info(self) -> dict[str, Any]:
        return {
            "ack_store_kind": self.ack_store_kind,
            "notebooklm_note_written": False,
            "notebooklm_note_available": False,
        }


def read_ack(store: AckStore, target: ProviderTarget) -> dict[str, Any] | None:
    """Resolve target first; never scan other targets."""
    ack = store.read_ack(target)
    if ack is None:
        return None
    if ack.get("target_key_hash") and ack["target_key_hash"] != target.target_key_hash:
        return None
    return ack


def write_ack(store: AckStore, target: ProviderTarget, ack: dict[str, Any]) -> dict[str, Any]:
    store.write_ack(target, ack)
    info = getattr(store, "persistence_info", None)
    if callable(info):
        return dict(info())
    return {
        "ack_store_kind": getattr(store, "ack_store_kind", "unknown"),
        "notebooklm_note_written": bool(getattr(store, "notebooklm_note_written", False)),
        "notebooklm_note_available": False,
    }
