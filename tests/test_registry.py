"""Tests for tolerant spec registry parsing."""

from vibe_control.spec.registry import parse_registry_data, validate_entries


def test_list_like_registry():
    data = [
        {"id": "spec-a", "status": "active", "path": "docs/a.md", "title": "A"},
        {"id": "spec-b", "status": "draft", "path": "docs/b.md"},
    ]
    result = parse_registry_data(data)
    assert len(result.entries) == 2
    assert result.entries[0].id == "spec-a"
    assert result.errors == []


def test_dict_like_registry_with_entries_key():
    data = {
        "entries": [
            {"id": "spec-a", "status": "active", "path": "docs/a.md"},
        ]
    }
    result = parse_registry_data(data)
    assert len(result.entries) == 1
    assert result.entries[0].path == "docs/a.md"


def test_dict_keyed_by_id():
    data = {
        "spec-a": {"status": "active", "path": "docs/a.md", "title": "A"},
    }
    result = parse_registry_data(data)
    assert result.entries[0].id == "spec-a"


def test_duplicate_ids_reported():
    data = [
        {"id": "dup", "status": "active", "path": "a.md"},
        {"id": "dup", "status": "active", "path": "b.md"},
    ]
    result = parse_registry_data(data)
    assert any("duplicate id" in e for e in result.errors)


def test_validate_entries_requires_path():
    from vibe_control.spec.registry import SpecEntry

    entries = [SpecEntry(id="x", status="active", path=None, raw={"id": "x", "status": "active"})]
    selected, warnings, errors = validate_entries(
        entries,
        required_fields=["id", "status", "path"],
        authoritative_statuses=["active"],
    )
    assert selected  # still selected by status
    assert any("missing" in e for e in errors)
