"""Local knowledge sync receipt (provider runtime state, not repo SSOT)."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ReceiptError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def receipt_path(project_id: str, *, home: Path | None = None) -> Path:
    root = home if home is not None else Path(os.path.expanduser("~"))
    return root / ".agents" / "state" / "vibe-control" / project_id / "knowledge-sync.json"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _hash_id(value: str | None) -> str | None:
    if not value:
        return None
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _redact_doc(doc: dict[str, Any]) -> dict[str, Any]:
    out = dict(doc)
    current = dict(out.get("current") or {})
    if "provider_source_id" in current:
        current["source_id_hash"] = current.get("source_id_hash") or _hash_id(
            current.get("provider_source_id")
        )
        current.pop("provider_source_id", None)
    out["current"] = current
    history = []
    for item in out.get("history") or []:
        h = dict(item)
        if "provider_source_id" in h:
            h["source_id_hash"] = h.get("source_id_hash") or _hash_id(h.get("provider_source_id"))
            h.pop("provider_source_id", None)
        history.append(h)
    out["history"] = history
    return out


class ReceiptStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {
                "schema_version": 1,
                "project_id": None,
                "provider": None,
                "documents": {},
            }
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ReceiptError(
                "RECEIPT_CORRUPTED",
                f"Receipt JSON is corrupted: {self.path}",
                {"path": self.path.as_posix(), "error": str(exc)},
            ) from exc
        if not isinstance(data, dict):
            raise ReceiptError(
                "RECEIPT_CORRUPTED",
                "Receipt root must be an object",
                {"path": self.path.as_posix()},
            )
        data.setdefault("documents", {})
        return data

    def write_verified(
        self,
        *,
        project_id: str,
        provider: str,
        notebook_alias: str,
        notebook_ref_hash: str | None,
        doc_id: str,
        path_str: str,
        managed_name: str,
        current: dict[str, Any],
    ) -> dict[str, Any]:
        data = self.load()
        data["schema_version"] = 1
        data["project_id"] = project_id
        data["provider"] = provider
        data["notebook_alias"] = notebook_alias
        data["notebook_ref_hash"] = notebook_ref_hash
        data["updated_at"] = _now()
        documents = dict(data.get("documents") or {})
        existing = dict(documents.get(doc_id) or {})
        history = list(existing.get("history") or [])
        old_current = existing.get("current")
        if old_current:
            hist = dict(old_current)
            hist["state"] = "superseded"
            hist["superseded_at"] = _now()
            history.insert(0, hist)
        new_current = dict(current)
        new_current["source_id_hash"] = new_current.get("source_id_hash") or _hash_id(
            new_current.get("provider_source_id")
        )
        new_current["verified_at"] = new_current.get("verified_at") or _now()
        documents[doc_id] = {
            "doc_id": doc_id,
            "path": path_str,
            "managed_name": managed_name,
            "current": new_current,
            "history": history,
        }
        data["documents"] = documents
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return data


def status(project_id: str, *, home: Path | None = None) -> dict[str, Any]:
    path = receipt_path(project_id, home=home)
    if not path.is_file():
        return {
            "ok": True,
            "present": False,
            "path": path.as_posix(),
            "warnings": ["receipt missing (warning, not failure)"],
            "documents": {},
        }
    try:
        data = ReceiptStore(path).load()
    except ReceiptError as exc:
        return {
            "ok": False,
            "present": True,
            "code": exc.code,
            "message": exc.message,
            "path": path.as_posix(),
            "details": exc.details,
            "next_actions": [
                f"Inspect or remove corrupted receipt at {path}",
                "Re-run verified add after fixing receipt",
            ],
        }
    return {
        "ok": True,
        "present": True,
        "path": path.as_posix(),
        "schema_version": data.get("schema_version"),
        "project_id": data.get("project_id"),
        "provider": data.get("provider"),
        "notebook_alias": data.get("notebook_alias"),
        "updated_at": data.get("updated_at"),
        "document_count": len(data.get("documents") or {}),
        "warnings": [],
    }


def inspect(project_id: str, *, report_mode: bool = True, home: Path | None = None) -> dict[str, Any]:
    path = receipt_path(project_id, home=home)
    base = status(project_id, home=home)
    if not base.get("ok"):
        return base
    if not base.get("present"):
        return base
    data = ReceiptStore(path).load()
    docs = data.get("documents") or {}
    if report_mode:
        docs = {k: _redact_doc(v) for k, v in docs.items()}
        data = dict(data)
        data["documents"] = docs
        data.pop("notebook_ref", None)
    return {
        "ok": True,
        "present": True,
        "path": path.as_posix(),
        "report_mode": report_mode,
        "receipt": data,
    }


def load_receipt_dict(project_id: str, *, home: Path | None = None) -> dict[str, Any] | None:
    path = receipt_path(project_id, home=home)
    if not path.is_file():
        return None
    return ReceiptStore(path).load()


def receipt_source_index(receipt_data: dict[str, Any] | None) -> dict[str, str]:
    if not receipt_data:
        return {}
    index: dict[str, str] = {}
    for doc_id, doc in (receipt_data.get("documents") or {}).items():
        current = doc.get("current") or {}
        sid = current.get("provider_source_id")
        if sid:
            index[str(sid)] = str(doc_id)
    return index
