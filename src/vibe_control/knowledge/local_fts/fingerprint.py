"""Fingerprint helpers for local_fts index freshness."""

from __future__ import annotations

from vibe_control.knowledge.provider_target import canonical_json, sha256_hex
from vibe_control.knowledge.snapshot import DesiredSnapshot

CHUNKING_VERSION = "heading_v1"
TOKENIZER = "trigram"


def index_desired_fingerprint(snapshot: DesiredSnapshot) -> str:
    """Bind DesiredSnapshot.snapshot_hash to local chunking/tokenizer policy."""
    return sha256_hex(
        canonical_json(
            {
                "snapshot_hash": snapshot.snapshot_hash,
                "chunking_version": CHUNKING_VERSION,
                "tokenizer": TOKENIZER,
            }
        )
    )


def scope_key_for_fs(sync_scope: str) -> str:
    """Filesystem-safe form of sync_scope_for_corpus output."""
    return (sync_scope or "ssot_files").replace(":", "_").replace("/", "_")
