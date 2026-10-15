"""Tolerant parser for docs/project/spec-registry.yml."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class SpecEntry:
    id: str
    status: str | None = None
    path: str | None = None
    title: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class RegistryParseResult:
    entries: list[SpecEntry]
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    source_path: Path | None = None


def _extract_entry_list(data: Any) -> tuple[list[Any], list[str]]:
    warnings: list[str] = []
    if data is None:
        return [], ["registry is empty"]
    if isinstance(data, list):
        return data, warnings
    if isinstance(data, dict):
        for key in ("entries", "specs", "items"):
            value = data.get(key)
            if isinstance(value, list):
                return value, warnings
        # dict keyed by id
        if all(isinstance(v, dict) for v in data.values()):
            entries = []
            for key, value in data.items():
                item = dict(value)
                item.setdefault("id", key)
                entries.append(item)
            return entries, warnings
        warnings.append("unrecognized dict registry shape; no entries extracted")
        return [], warnings
    warnings.append(f"unsupported registry root type: {type(data).__name__}")
    return [], warnings


def parse_registry_data(data: Any) -> RegistryParseResult:
    raw_entries, warnings = _extract_entry_list(data)
    entries: list[SpecEntry] = []
    errors: list[str] = []

    for index, item in enumerate(raw_entries):
        if not isinstance(item, dict):
            warnings.append(f"skipping non-mapping registry entry at index {index}")
            continue
        entry_id = item.get("id")
        if entry_id is None or str(entry_id).strip() == "":
            errors.append(f"registry entry at index {index} missing id")
            continue
        entries.append(
            SpecEntry(
                id=str(entry_id),
                status=None if item.get("status") is None else str(item.get("status")),
                path=None if item.get("path") is None else str(item.get("path")),
                title=None if item.get("title") is None else str(item.get("title")),
                raw=dict(item),
            )
        )

    seen: dict[str, int] = {}
    for entry in entries:
        if entry.id in seen:
            errors.append(f"duplicate id: {entry.id}")
        else:
            seen[entry.id] = 1

    return RegistryParseResult(entries=entries, warnings=warnings, errors=errors)


def load_registry(path: Path) -> RegistryParseResult:
    if not path.is_file():
        return RegistryParseResult(
            entries=[],
            errors=[f"registry file not found: {path.as_posix()}"],
            source_path=path,
        )
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    result = parse_registry_data(data)
    result.source_path = path
    return result


def validate_entries(
    entries: list[SpecEntry],
    *,
    required_fields: list[str],
    authoritative_statuses: list[str] | None = None,
) -> tuple[list[SpecEntry], list[str], list[str]]:
    """Validate entries. Returns (active_for_corpus, warnings, errors)."""
    warnings: list[str] = []
    errors: list[str] = []
    authoritative = set(authoritative_statuses or ["active"])
    selected: list[SpecEntry] = []

    for entry in entries:
        missing: list[str] = []
        for field_name in required_fields:
            value = entry.raw.get(field_name)
            if value is None or (isinstance(value, str) and value.strip() == ""):
                missing.append(field_name)
        if missing:
            msg = f"entry {entry.id} missing required fields: {', '.join(missing)}"
            if "path" in missing:
                errors.append(msg)
            else:
                warnings.append(msg)
        elif not entry.path:
            errors.append(f"entry {entry.id} missing path")
        if entry.status in authoritative:
            selected.append(entry)

    return selected, warnings, errors
