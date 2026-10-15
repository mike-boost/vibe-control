"""Phase 8 unit: reindex-bindings never restores SSOT content."""

from __future__ import annotations

from pathlib import Path

import pytest

from vibe_control.knowledge.provider_target import ProviderTarget
from vibe_control.knowledge.reindex_bindings import reindex_bindings


class FakeReindexProvider:
    def __init__(self, sources: list[dict]):
        self.sources = sources

    def list_sources(self, *, notebook_ref: str) -> dict:
        return {"ok": True, "sources": list(self.sources)}


@pytest.mark.unit
def test_reindex_bindings_writes_receipt_only(tmp_path: Path):
    target = ProviderTarget.from_ref(
        provider="notebooklm", notebook_alias="OPM-test", notebook_ref="nb-reindex"
    )
    ssot = tmp_path / "docs" / "a.md"
    ssot.parent.mkdir(parents=True)
    original = "local ssot body\n"
    ssot.write_text(original, encoding="utf-8")

    provider = FakeReindexProvider(
        [
            {
                "id": "src-1",
                "title": "vibe__vibe-control__a__h__aaaaaaaaaaaa.md",
                "status": "ready",
            }
        ]
    )
    result = reindex_bindings(
        project_id="vibe-control",
        target=target,
        notebook_ref="nb-reindex",
        provider=provider,
        desired_docs=[{"doc_id": "a", "path": "docs/a.md", "content_sha256": "sha256:" + "a" * 64}],
        home=tmp_path,
        repo_root=tmp_path,
    )
    assert result["ok"] is True
    assert result["ssot_restored"] is False
    assert "Only provider binding metadata was reindexed" in result["message"]
    assert ssot.read_text(encoding="utf-8") == original
    assert result["receipt_path"]
