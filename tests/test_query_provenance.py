"""Tests for query provenance enrichment and inventory hints."""

from __future__ import annotations

from pathlib import Path

import yaml

from helpers import write_doc, write_registry
from vibe_control.knowledge.ask_template import ASK_TEMPLATE_VERSION
from vibe_control.knowledge.corpus import CorpusDocument, DesiredCorpus
from vibe_control.knowledge.query_provenance import (
    append_inventory_hint,
    enrich_query_sources,
    looks_evidence_insufficient,
)
from vibe_control.knowledge.query_router import route_knowledge_query


def _corpus() -> DesiredCorpus:
    return DesiredCorpus(
        project_id="prov",
        documents=[
            CorpusDocument(
                doc_id="active_spec",
                path="docs/project/active.md",
                title="Active Spec",
                status="active",
                kind="spec",
                source_policy="must_include",
                source_title="[vibe:prov:active_spec] Active Spec",
            )
        ],
        source_count=1,
    )


def test_enrich_maps_provider_sid_to_path():
    receipt = {
        "items": {
            "active_spec": {
                "path": "docs/project/active.md",
                "provider_source_id": "sid-abc",
            }
        }
    }
    enriched = enrich_query_sources(
        [
            {
                "source_id": "sid-abc",
                "citation_number": 1,
                "cited_text": "publish migration body",
            }
        ],
        corpus=_corpus(),
        receipt_data=receipt,
    )
    assert len(enriched) == 1
    row = enriched[0]
    assert row["doc_id"] == "active_spec"
    assert row["path"] == "docs/project/active.md"
    assert row["title"] == "Active Spec"
    assert row["citation_number"] == 1
    assert row["cited_text"] == "publish migration body"
    assert "source_id" not in row
    assert row["source_id_hash"].startswith("sha256:")


def test_looks_evidence_insufficient_phrase():
    assert looks_evidence_insufficient(
        "Uncertainty:\nEvidence insufficient — rate limit not in SSOT"
    )
    assert not looks_evidence_insufficient(
        "Facts:\nFooter MUST include year\nSources:\n- Active Spec §Footer",
        sources=[{"path": "docs/project/active.md"}],
    )


def test_append_inventory_hint_once():
    actions = append_inventory_hint([])
    assert actions[0]["code"] == "CHECK_CORPUS_INVENTORY"
    assert actions[0]["mutation"] is False
    assert "inventory" in actions[0]["command"]
    again = append_inventory_hint(actions)
    assert len(again) == 1


def _seed(tmp: Path) -> None:
    cfg = {
        "project": {"id": "ask-prov", "name": "Ask"},
        "components": {
            "knowledge": {"enabled": True},
            "task": {"enabled": False},
        },
        "knowledge": {
            "provider": "notebooklm",
            "fallback_provider": "repo",
            "max_sources": 20,
            "warn_sources": 15,
            "authoritative_statuses": ["active"],
            "include_extra": [],
            "exclude_globs": ["**/archive/**"],
            "source_title_template": "[vibe:{project_id}:{doc_id}] {title}",
            "notebooks": {
                "default_alias": "OPM-test",
                "allow_list": [
                    {
                        "alias": "OPM-test",
                        "display_name": "OPM-test",
                        "ref_env": "NOTEBOOKLM_NOTEBOOK_OPM_TEST",
                        "allowed_operations": ["status", "query"],
                    }
                ],
            },
        },
        "specs": {
            "registry": "docs/project/spec-registry.yml",
            "required_fields": ["id", "status", "path"],
            "require_commit_push_for_ssot": True,
        },
        "tasks": {"provider": "beads"},
    }
    path = tmp / ".config" / "vibe-control.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    write_registry(
        tmp,
        [
            {
                "id": "active_spec",
                "title": "Active Spec",
                "status": "active",
                "path": "docs/project/active.md",
            }
        ],
    )
    write_doc(tmp, "docs/project/active.md", "# Active Spec\n\npublish migration body\n")


class _ProvProvider:
    def __init__(self, answer: str, sources: list[dict]):
        self.answer = answer
        self.sources = sources
        self.mutations = {"add": 0, "delete": 0, "cleanup": 0}

    def query(self, question: str, **kwargs) -> dict:
        return {"ok": True, "answer": self.answer, "sources": list(self.sources)}

    def list_sources(self, *, notebook_ref: str) -> dict:
        return {"ok": True, "sources": []}


def test_provider_path_enriches_and_hints_inventory(tmp_path: Path, monkeypatch):
    _seed(tmp_path)
    monkeypatch.setenv("NOTEBOOKLM_NOTEBOOK_OPM_TEST", "nb-prov")
    # Seed scoped receipt so sid maps to doc.
    from vibe_control.config import load_config
    from vibe_control.knowledge.phase8_runtime import get_runtime
    from vibe_control.knowledge.receipt_scope import scoped_receipt_path
    import json

    config = load_config(tmp_path)
    runtime = get_runtime(repo_root=tmp_path, home=tmp_path)
    target, _ = runtime.resolve_target(config, alias=None)
    receipt_path = scoped_receipt_path(config.project_id, target, home=tmp_path)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "items": {
                    "active_spec": {
                        "path": "docs/project/active.md",
                        "provider_source_id": "sid-live-1",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    provider = _ProvProvider(
        answer="Uncertainty:\nEvidence insufficient for API rate limit",
        sources=[
            {
                "source_id": "sid-live-1",
                "citation_number": 1,
                "cited_text": "publish migration body",
            }
        ],
    )
    result = route_knowledge_query(
        repo_root=tmp_path,
        question="What is the API rate limit?",
        sync_state_override="synced",
        provider=provider,
        home=tmp_path,
    )
    assert result["ask_template_version"] == ASK_TEMPLATE_VERSION
    assert result["ask_template_version"] == "vibe.knowledge.ask.v3"
    src = result["sources"][0]
    assert src["doc_id"] == "active_spec"
    assert src["path"] == "docs/project/active.md"
    assert "source_id" not in src
    codes = [
        a.get("code") if isinstance(a, dict) else None for a in result["next_actions"]
    ]
    assert "CHECK_CORPUS_INVENTORY" in codes


def test_repo_fallback_no_hit_hints_inventory(tmp_path: Path):
    _seed(tmp_path)
    result = route_knowledge_query(
        repo_root=tmp_path,
        question="xyzzy-unique-token-not-in-corpus-qqq",
        sync_state_override="unavailable",
        home=tmp_path,
    )
    assert result["provider"] == "repo"
    assert result["sources"] == []
    codes = [
        a.get("code") if isinstance(a, dict) else None for a in result["next_actions"]
    ]
    assert "CHECK_CORPUS_INVENTORY" in codes
