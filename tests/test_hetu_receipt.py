"""IndexBindingReceipt schema, hash, and atomic IO."""

from __future__ import annotations

import json
from pathlib import Path

from vibe_control.hetu.models import IndexBindingReceipt
from vibe_control.hetu.receipt import (
    RECEIPT_SCHEMA,
    IndexBindingReceiptLoadResult,
    compute_binding_hash,
    index_binding_receipt_path,
    load_index_binding_receipt,
    receipt_relative_path,
    write_index_binding_receipt,
)


def _make_receipt(**overrides: object) -> IndexBindingReceipt:
    base = {
        "schema": RECEIPT_SCHEMA,
        "repo_identity": "demo-project",
        "repo_realpath_hash": "sha256:" + ("b" * 64),
        "provider": "codebase_memory",
        "provider_project": "demo",
        "provider_version": "0.9.0",
        "index_mode": "fast",
        "persistence": False,
        "index_commit": "deadbeef",
        "git_status_short_empty": True,
        "auto_watch_effective": False,
        "node_count": 3,
        "edge_count": 4,
        "bound_at": "2026-07-22T01:00:00+00:00",
    }
    base.update(overrides)
    receipt = IndexBindingReceipt(**base)  # type: ignore[arg-type]
    return receipt.with_binding_hash(compute_binding_hash(receipt))


def test_receipt_path_under_runtime_state(tmp_path: Path):
    path = index_binding_receipt_path("demo-project", home=tmp_path)
    assert path == tmp_path / ".agents" / "state" / "vibe-control" / "demo-project" / "hetu" / "codebase_memory" / "index-binding.json"
    rel = receipt_relative_path("demo-project")
    assert rel == "demo-project/hetu/codebase_memory/index-binding.json"
    assert not rel.startswith("/")
    assert "~" not in rel


def test_canonical_binding_hash_stable_and_excludes_hash_field():
    receipt = _make_receipt()
    h1 = compute_binding_hash(receipt)
    h2 = compute_binding_hash(receipt)
    assert h1 == h2
    assert h1.startswith("sha256:")
    assert len(h1) == len("sha256:") + 64
    assert receipt.binding_hash == h1

    # Mutating a covered field changes the hash.
    other = _make_receipt(index_commit="changed")
    assert compute_binding_hash(other) != h1


def test_atomic_write_and_roundtrip(tmp_path: Path):
    receipt = _make_receipt()
    path = write_index_binding_receipt(receipt, home=tmp_path)
    assert path.is_file()
    assert not path.with_suffix(path.suffix + ".tmp").exists()

    loaded = load_index_binding_receipt("demo-project", home=tmp_path)
    assert isinstance(loaded, IndexBindingReceiptLoadResult)
    assert loaded.ok is True
    assert loaded.receipt is not None
    assert loaded.receipt.to_dict() == receipt.to_dict()
    assert loaded.relative_path == "demo-project/hetu/codebase_memory/index-binding.json"
    # Public load result must not advertise absolute home paths.
    payload = loaded.to_dict()
    assert "relative_path" in payload
    assert "absolute_home_path" not in payload
    assert "path" not in payload
    assert "~/.agents" not in json.dumps(payload)
    assert str(Path.home()) not in json.dumps(payload)


def test_missing_receipt_load_fail_closed(tmp_path: Path):
    loaded = load_index_binding_receipt("demo-project", home=tmp_path)
    assert loaded.ok is False
    assert loaded.code == "RECEIPT_MISSING"
    assert loaded.receipt is None
    assert loaded.relative_path == "demo-project/hetu/codebase_memory/index-binding.json"


def test_corrupt_receipt_fails_closed_without_raw_parser_errors(tmp_path: Path):
    path = index_binding_receipt_path("demo-project", home=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not-json", encoding="utf-8")

    loaded = load_index_binding_receipt("demo-project", home=tmp_path)
    assert loaded.ok is False
    assert loaded.code == "RECEIPT_CORRUPTED"
    assert loaded.receipt is None
    message = loaded.message or ""
    assert "JSONDecodeError" not in message
    assert "Expecting" not in message
    payload = loaded.to_dict()
    assert "JSONDecodeError" not in json.dumps(payload)


def test_invalid_schema_or_hash_mismatch_corrupt(tmp_path: Path):
    receipt = _make_receipt()
    bad = receipt.to_dict()
    bad["binding_hash"] = "sha256:" + ("0" * 64)
    path = index_binding_receipt_path("demo-project", home=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bad, indent=2) + "\n", encoding="utf-8")

    loaded = load_index_binding_receipt("demo-project", home=tmp_path)
    assert loaded.ok is False
    assert loaded.code == "RECEIPT_CORRUPTED"
    assert loaded.reason == "binding_hash_mismatch"

    bad_schema = receipt.to_dict()
    bad_schema["schema"] = "wrong"
    path.write_text(json.dumps(bad_schema, indent=2) + "\n", encoding="utf-8")
    loaded2 = load_index_binding_receipt("demo-project", home=tmp_path)
    assert loaded2.ok is False
    assert loaded2.code == "RECEIPT_CORRUPTED"
    assert loaded2.reason == "schema_mismatch"


def test_receipt_public_fields_omit_absolute_paths():
    receipt = _make_receipt()
    payload = receipt.to_dict()
    assert "repo_realpath" not in payload
    assert payload["repo_realpath_hash"].startswith("sha256:")
    assert all("/Users/" not in str(v) for v in payload.values())
    assert all("~/" not in str(v) for v in payload.values())
