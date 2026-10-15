"""Query provenance helpers: map provider citations → repo paths; insufficient-evidence hints.

Readonly. Does not mutate providers or receipts.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from vibe_control.knowledge.corpus import DesiredCorpus

_INSUFFICIENT_MARKERS = (
    "evidence insufficient",
    "insufficient evidence",
    "no evidence in sources",
    "not found in the sources",
    "not stated in the sources",
    "not present in the sources",
    "sources do not contain",
    "cannot find evidence",
)

_INVENTORY_ACTION: dict[str, Any] = {
    "code": "CHECK_CORPUS_INVENTORY",
    "command": "vibe knowledge inventory --json",
    "mutation": False,
    "reason": (
        "Evidence insufficient or no matching sources; "
        "check whether the authority is in the desired corpus "
        "(registry active + include_extra)"
    ),
}


def _sid_hash(value: str | None) -> str | None:
    if not value:
        return None
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def receipt_provider_sid_index(receipt_data: dict[str, Any] | None) -> dict[str, str]:
    """Map provider_source_id → doc_id from scoped or legacy receipt shapes."""
    if not receipt_data:
        return {}
    index: dict[str, str] = {}
    items = receipt_data.get("items")
    if isinstance(items, dict):
        for doc_id, row in items.items():
            if not isinstance(row, dict):
                continue
            sid = row.get("provider_source_id")
            if sid:
                index[str(sid)] = str(doc_id)
    documents = receipt_data.get("documents")
    if isinstance(documents, dict):
        for doc_id, row in documents.items():
            if not isinstance(row, dict):
                continue
            current = row.get("current") if isinstance(row.get("current"), dict) else row
            sid = current.get("provider_source_id")
            if sid:
                index[str(sid)] = str(doc_id)
    return index


def enrich_query_sources(
    raw_sources: list[dict[str, Any]],
    *,
    corpus: DesiredCorpus | None,
    receipt_data: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Attach doc_id / path / title when receipt + corpus can resolve a citation.

    Always redacts raw provider_source_id / source_id to source_id_hash.
    Preserves citation_number and cited_text when present.
    """
    by_doc = {d.doc_id: d for d in (corpus.documents if corpus else [])}
    sid_to_doc = receipt_provider_sid_index(receipt_data)
    out: list[dict[str, Any]] = []

    for src in raw_sources:
        if not isinstance(src, dict):
            continue
        row = dict(src)
        raw_sid = None
        for key in ("source_id", "provider_source_id", "notebook_ref", "id"):
            if key in row and row[key]:
                raw_sid = str(row.pop(key))
                break
        if raw_sid:
            row["source_id_hash"] = _sid_hash(raw_sid)

        doc_id = row.get("doc_id")
        if not doc_id and raw_sid and raw_sid in sid_to_doc:
            doc_id = sid_to_doc[raw_sid]
        if not doc_id and row.get("source_id_hash"):
            # Match receipt rows that already stored only hashes (rare on load).
            want = str(row["source_id_hash"])
            for sid, mapped in sid_to_doc.items():
                if _sid_hash(sid) == want:
                    doc_id = mapped
                    break

        if doc_id:
            row["doc_id"] = str(doc_id)
            doc = by_doc.get(str(doc_id))
            if doc is not None:
                row.setdefault("path", doc.path)
                row.setdefault("title", doc.title)
                row.setdefault("kind", doc.kind)
                row.setdefault("status", doc.status)

        # Normalize citation fields from notebooklm-py references shape.
        if "cited_text" not in row and row.get("excerpt"):
            row["cited_text"] = row.get("excerpt")
        if "citation_number" in row and row["citation_number"] is not None:
            try:
                row["citation_number"] = int(row["citation_number"])
            except (TypeError, ValueError):
                pass

        out.append(row)
    return out


def looks_evidence_insufficient(answer: str, *, sources: list[Any] | None = None) -> bool:
    text = (answer or "").strip().lower()
    if not text:
        return not bool(sources)
    if any(marker in text for marker in _INSUFFICIENT_MARKERS):
        return True
    # Structured Uncertainty section that only says insufficient.
    if re.search(r"uncertainty:\s*evidence insufficient", text):
        return True
    return False


def inventory_next_action() -> dict[str, Any]:
    return dict(_INVENTORY_ACTION)


def append_inventory_hint(next_actions: list[Any]) -> list[Any]:
    """Append CHECK_CORPUS_INVENTORY once if missing."""
    out = list(next_actions)
    for item in out:
        if isinstance(item, dict) and item.get("code") == "CHECK_CORPUS_INVENTORY":
            return out
        if isinstance(item, str) and "knowledge inventory" in item:
            return out
    out.append(inventory_next_action())
    return out
