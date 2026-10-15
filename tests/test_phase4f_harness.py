"""Harness contract tests for Phase 4F (docs + boundary statements)."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_agents_md_exists_and_points_to_harness_docs():
    agents = (REPO / "AGENTS.md").read_text(encoding="utf-8")
    assert "docs/harness/knowledge-provider-boundary.md" in agents
    assert "docs/harness/notebooklm-source-lifecycle-contract.md" in agents
    assert "docs/harness/receipt-state-contract.md" in agents
    assert "Do not mutate NotebookLM unless the task explicitly requests" in agents
    assert "Run tests before and after changes" in agents


def test_harness_docs_exist_and_key_contracts():
    boundary = (REPO / "docs/harness/knowledge-provider-boundary.md").read_text(encoding="utf-8")
    lifecycle = (REPO / "docs/harness/notebooklm-source-lifecycle-contract.md").read_text(
        encoding="utf-8"
    )
    receipt = (REPO / "docs/harness/receipt-state-contract.md").read_text(encoding="utf-8")

    assert "provider-neutral" in boundary.lower() or "Provider-neutral" in boundary
    assert "must not" in boundary.lower() or "must not" in boundary
    assert "Skills" in boundary

    assert "add-new -> wait-ready -> verify-identity -> switch-receipt" in lifecycle
    assert "vibe__{project_id_slug}__{doc_id_slug}" in lifecycle
    assert "Still forbidden" in lifecycle or "Phase 4F forbids" in lifecycle
    assert "delete unmanaged" in lifecycle.lower() or "unmanaged" in lifecycle.lower()

    assert "~/.agents/state/vibe-control/<project-id>/knowledge-sync.json" in receipt
    assert "must not be committed" in receipt.lower() or "must not be committed" in receipt
