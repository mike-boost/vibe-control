"""Phase 8 unit tests: target-scoped receipt paths and legacy migration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vibe_control.knowledge.provider_target import ProviderTarget
from vibe_control.knowledge.receipt_scope import (
    TARGET_MISMATCH,
    legacy_receipt_path,
    load_or_migrate_receipt,
    pending_sync_path,
    scoped_receipt_path,
)


def _target(alias: str = "OPM-test", ref: str = "nb-aaa") -> ProviderTarget:
    return ProviderTarget.from_ref(
        provider="notebooklm",
        notebook_alias=alias,
        notebook_ref=ref,
    )


@pytest.mark.unit
def test_scoped_paths_include_provider_and_target_key(tmp_path: Path):
    target = _target()
    receipt = scoped_receipt_path("vibe-control", target, home=tmp_path)
    pending = pending_sync_path("vibe-control", target, home=tmp_path)
    assert f"/notebooklm/{target.target_key_hash}/knowledge-sync.json" in receipt.as_posix()
    assert f"/notebooklm/{target.target_key_hash}/pending-sync.json" in pending.as_posix()
    assert receipt.parent == pending.parent


@pytest.mark.unit
def test_legacy_flat_receipt_matching_target_migrates(tmp_path: Path):
    target = _target(ref="nb-match")
    legacy = legacy_receipt_path("vibe-control", home=tmp_path)
    legacy.parent.mkdir(parents=True)
    legacy.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "project_id": "vibe-control",
                "provider": "notebooklm",
                "notebook_alias": "OPM-test",
                "notebook_ref_hash": target.notebook_ref_hash,
                "documents": {"doc": {"path": "x.md"}},
            }
        ),
        encoding="utf-8",
    )
    result = load_or_migrate_receipt("vibe-control", target, home=tmp_path)
    assert result.ok is True
    assert result.migrated is True
    assert result.code is None
    scoped = scoped_receipt_path("vibe-control", target, home=tmp_path)
    assert scoped.is_file()
    data = json.loads(scoped.read_text(encoding="utf-8"))
    assert data["provider_target"]["target_key_hash"] == target.target_key_hash


@pytest.mark.unit
def test_legacy_flat_receipt_mismatch_returns_target_mismatch(tmp_path: Path):
    current = _target(ref="nb-new")
    other = _target(ref="nb-old")
    legacy = legacy_receipt_path("vibe-control", home=tmp_path)
    legacy.parent.mkdir(parents=True)
    legacy.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "project_id": "vibe-control",
                "provider": "notebooklm",
                "notebook_alias": "OPM-test",
                "notebook_ref_hash": other.notebook_ref_hash,
                "documents": {},
            }
        ),
        encoding="utf-8",
    )
    result = load_or_migrate_receipt("vibe-control", current, home=tmp_path)
    assert result.ok is False
    assert result.code == TARGET_MISMATCH
    assert not scoped_receipt_path("vibe-control", current, home=tmp_path).is_file()


@pytest.mark.unit
def test_scoped_receipt_preferred_over_legacy(tmp_path: Path):
    target = _target(ref="nb-1")
    scoped = scoped_receipt_path("vibe-control", target, home=tmp_path)
    scoped.parent.mkdir(parents=True)
    scoped.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "project_id": "vibe-control",
                "provider": "notebooklm",
                "provider_target": target.to_dict(),
                "items": {"a": {"path": "a.md"}},
            }
        ),
        encoding="utf-8",
    )
    legacy = legacy_receipt_path("vibe-control", home=tmp_path)
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(
        json.dumps({"notebook_ref_hash": "sha256:other", "documents": {"bad": {}}}),
        encoding="utf-8",
    )
    result = load_or_migrate_receipt("vibe-control", target, home=tmp_path)
    assert result.ok is True
    assert result.migrated is False
    assert "a" in (result.data or {}).get("items", {})
