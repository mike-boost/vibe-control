"""Provider-neutral remote source identity classification."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from vibe_control.knowledge.managed_names import parse_managed_name, slug_doc, slug_project
from vibe_control.knowledge.managed_titles import parse_managed_title


MANAGED_CLASSES = {
    "managed_by_receipt",
    "managed_by_name",
    "managed_by_hashed_filename",
    "legacy_managed",
}


def _map_doc_id(slug: str, desired_doc_ids: set[str]) -> str | None:
    for doc_id in desired_doc_ids:
        if slug_doc(doc_id) == slug:
            return doc_id
    return None


def classify_title(
    title: str,
    *,
    project_id: str,
    desired_doc_ids: set[str],
    path_hints: dict[str, str] | None = None,
) -> dict[str, Any]:
    path_hints = path_hints or {}
    parsed = parse_managed_name(title)
    if parsed and parsed["project_id"] == slug_project(project_id):
        mapped = _map_doc_id(parsed["doc_id"], desired_doc_ids) or parsed["doc_id"]
        classification = (
            "managed_by_hashed_filename"
            if parsed.get("kind") == "hashed_filename"
            else "managed_by_name"
        )
        return {
            "classification": classification,
            "doc_id": mapped,
            "project_id": project_id,
            "title": title,
        }

    legacy = parse_managed_title(title)
    if legacy and legacy.project_id == project_id:
        return {
            "classification": "legacy_managed",
            "doc_id": legacy.doc_id,
            "project_id": project_id,
            "title": title,
        }

    for doc_id, path in path_hints.items():
        if Path(path).name == title:
            return {
                "classification": "possible_managed_by_legacy_filename",
                "doc_id": doc_id,
                "project_id": project_id,
                "title": title,
            }

    return {
        "classification": "unmanaged",
        "doc_id": None,
        "project_id": None,
        "title": title,
    }


def classify_remote_source(
    source: dict[str, Any],
    *,
    project_id: str,
    desired_doc_ids: set[str],
    receipt_source_ids: dict[str, str] | None = None,
    path_hints: dict[str, str] | None = None,
) -> dict[str, Any]:
    receipt_source_ids = receipt_source_ids or {}
    source_id = source.get("id") or source.get("source_id")
    title = str(source.get("title") or source.get("name") or "")
    if source_id and str(source_id) in receipt_source_ids:
        return {
            "classification": "managed_by_receipt",
            "doc_id": receipt_source_ids[str(source_id)],
            "project_id": project_id,
            "title": title,
            "source_id": str(source_id),
        }
    result = classify_title(
        title,
        project_id=project_id,
        desired_doc_ids=desired_doc_ids,
        path_hints=path_hints,
    )
    result["source_id"] = None if source_id is None else str(source_id)
    return result


def classify_inventory(
    sources: list[Any],
    *,
    project_id: str,
    desired_doc_ids: set[str],
    path_hints: dict[str, str] | None = None,
    receipt_source_ids: dict[str, str] | None = None,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    by_doc: dict[str, list[dict[str, Any]]] = {}
    desired_slugs = {slug_doc(d) for d in desired_doc_ids}
    for source in sources:
        if hasattr(source, "title"):
            raw = {"id": getattr(source, "source_id", None), "title": source.title}
        else:
            raw = dict(source)
        item = classify_remote_source(
            raw,
            project_id=project_id,
            desired_doc_ids=desired_doc_ids,
            receipt_source_ids=receipt_source_ids,
            path_hints=path_hints,
        )
        items.append(item)
        doc_id = item.get("doc_id")
        if doc_id and item["classification"] in MANAGED_CLASSES:
            by_doc.setdefault(str(doc_id), []).append(item)

    duplicates = [
        {"doc_id": doc_id, "count": len(vals), "sources": vals}
        for doc_id, vals in by_doc.items()
        if len(vals) > 1
    ]
    orphans = [
        item
        for item in items
        if item["classification"] in MANAGED_CLASSES
        and item.get("doc_id")
        and slug_doc(str(item["doc_id"])) not in desired_slugs
    ]
    return {
        "items": items,
        "duplicate_managed": duplicates,
        "duplicate_managed_count": len(duplicates),
        "orphan_managed": orphans,
        "orphan_managed_count": len(orphans),
        "managed_count": sum(1 for i in items if i["classification"] in MANAGED_CLASSES),
        "unmanaged_count": sum(1 for i in items if i["classification"] == "unmanaged"),
        "possible_legacy_count": sum(
            1 for i in items if i["classification"] == "possible_managed_by_legacy_filename"
        ),
    }


def legacy_possible_blocks_add(classified: dict[str, Any], *, doc_id: str) -> bool:
    target = slug_doc(doc_id)
    for item in classified.get("items") or []:
        if item.get("classification") != "possible_managed_by_legacy_filename":
            continue
        if slug_doc(str(item.get("doc_id") or "")) == target:
            return True
    return False
