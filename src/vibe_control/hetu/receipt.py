"""IndexBindingReceipt path helpers, canonical hash, and atomic read/write."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vibe_control.hetu.models import IndexBindingReceipt


RECEIPT_SCHEMA = "vibe.hetu.index_binding.v1"
DEFAULT_PROVIDER = "codebase_memory"


def _state_root(home: Path | None = None) -> Path:
    root = home if home is not None else Path(os.path.expanduser("~"))
    return root / ".agents" / "state" / "vibe-control"


def receipt_relative_path(
    project_id: str,
    *,
    provider: str = DEFAULT_PROVIDER,
) -> str:
    """Public relative path under the vibe-control runtime state root."""
    return f"{project_id}/hetu/{provider}/index-binding.json"


def index_binding_receipt_path(
    project_id: str,
    *,
    provider: str = DEFAULT_PROVIDER,
    home: Path | None = None,
) -> Path:
    return _state_root(home) / receipt_relative_path(project_id, provider=provider)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_binding_hash(receipt: IndexBindingReceipt) -> str:
    payload = receipt.canonical_payload()
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    return "sha256:" + digest


def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


@dataclass(frozen=True)
class IndexBindingReceiptLoadResult:
    """Public load result uses relative_path only (no absolute home paths)."""

    ok: bool
    receipt: IndexBindingReceipt | None = None
    code: str | None = None
    reason: str | None = None
    message: str | None = None
    relative_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "receipt": None if self.receipt is None else self.receipt.to_dict(),
            "code": self.code,
            "reason": self.reason,
            "message": self.message,
            "relative_path": self.relative_path,
        }


def write_index_binding_receipt(
    receipt: IndexBindingReceipt,
    *,
    home: Path | None = None,
    provider: str | None = None,
) -> Path:
    """Atomically write a hashed receipt under runtime state. Returns filesystem path."""
    active_provider = provider or receipt.provider or DEFAULT_PROVIDER
    if receipt.schema != RECEIPT_SCHEMA:
        raise ValueError(f"unsupported receipt schema: {receipt.schema}")
    hashed = receipt if receipt.binding_hash else receipt.with_binding_hash(compute_binding_hash(receipt))
    expected = compute_binding_hash(hashed)
    if hashed.binding_hash != expected:
        hashed = hashed.with_binding_hash(expected)
    path = index_binding_receipt_path(hashed.repo_identity, provider=active_provider, home=home)
    _write_json_atomic(path, hashed.to_dict())
    return path


def load_index_binding_receipt(
    project_id: str,
    *,
    provider: str = DEFAULT_PROVIDER,
    home: Path | None = None,
) -> IndexBindingReceiptLoadResult:
    """Load receipt fail-closed. Never raises raw JSON parser exceptions to callers."""
    relative = receipt_relative_path(project_id, provider=provider)
    path = index_binding_receipt_path(project_id, provider=provider, home=home)
    if not path.is_file():
        return IndexBindingReceiptLoadResult(
            ok=False,
            code="RECEIPT_MISSING",
            reason="receipt_missing",
            message="Index binding receipt is missing",
            relative_path=relative,
        )

    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return IndexBindingReceiptLoadResult(
            ok=False,
            code="RECEIPT_CORRUPTED",
            reason="invalid_json",
            message="Index binding receipt is corrupted or unreadable",
            relative_path=relative,
        )

    if not isinstance(data, dict):
        return IndexBindingReceiptLoadResult(
            ok=False,
            code="RECEIPT_CORRUPTED",
            reason="invalid_root",
            message="Index binding receipt root must be an object",
            relative_path=relative,
        )

    schema = data.get("schema")
    if schema != RECEIPT_SCHEMA:
        return IndexBindingReceiptLoadResult(
            ok=False,
            code="RECEIPT_CORRUPTED",
            reason="schema_mismatch",
            message="Index binding receipt schema is unsupported or missing",
            relative_path=relative,
        )

    required = (
        "repo_identity",
        "repo_realpath_hash",
        "provider",
        "provider_project",
        "provider_version",
        "index_mode",
        "persistence",
        "index_commit",
        "git_status_short_empty",
        "auto_watch_effective",
        "node_count",
        "edge_count",
        "bound_at",
        "binding_hash",
    )
    missing = [key for key in required if key not in data]
    if missing:
        return IndexBindingReceiptLoadResult(
            ok=False,
            code="RECEIPT_CORRUPTED",
            reason="missing_fields",
            message="Index binding receipt is missing required fields",
            relative_path=relative,
        )

    try:
        receipt = IndexBindingReceipt.from_dict(data)
    except (KeyError, TypeError, ValueError):
        return IndexBindingReceiptLoadResult(
            ok=False,
            code="RECEIPT_CORRUPTED",
            reason="invalid_fields",
            message="Index binding receipt fields are invalid",
            relative_path=relative,
        )

    expected = compute_binding_hash(receipt)
    if receipt.binding_hash != expected:
        return IndexBindingReceiptLoadResult(
            ok=False,
            code="RECEIPT_CORRUPTED",
            reason="binding_hash_mismatch",
            message="Index binding receipt hash does not match canonical payload",
            relative_path=relative,
        )

    return IndexBindingReceiptLoadResult(
        ok=True,
        receipt=receipt,
        relative_path=relative,
    )
