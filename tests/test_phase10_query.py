"""Phase 10 Knowledge Query contract polish (fake/readonly; no provider mutation)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from helpers import write_doc, write_registry
from vibe_control.cli import main
from vibe_control.knowledge.phase8_runtime import Phase8Runtime
from vibe_control.knowledge.query_router import route_knowledge_query
from vibe_control.knowledge.remote_ack import FakeAckStore
from vibe_control.knowledge.provider_target import ProviderTarget


def _seed(tmp: Path) -> None:
    cfg = {
        "project": {"id": "phase10", "name": "Phase10"},
        "knowledge": {
            "provider": "notebooklm",
            "fallback_provider": "repo",
            "max_sources": 20,
            "warn_sources": 15,
            "authoritative_statuses": ["active"],
            "include_extra": ["docs/project/DECISION_LOG.md"],
            "exclude_globs": [
                "docs/program/plans/**",
                "runtime/**",
                "acceptance/**",
                ".beads/**",
                "**/archive/**",
            ],
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
                "title": "Active Publish Spec",
                "status": "active",
                "path": "docs/project/active.md",
            }
        ],
    )
    write_doc(tmp, "docs/project/active.md", "# Active Publish Spec\n\npublish migration body\n")
    write_doc(tmp, "docs/project/DECISION_LOG.md", "Decision: keep publish explicit.\n")
    write_doc(tmp, "docs/program/plans/secret-plan.md", "plan should not be searched xyzzy\n")
    write_doc(tmp, "runtime/state.json", '{"x":1}\n')
    write_doc(tmp, "acceptance/report.md", "acceptance leak token\n")
    write_doc(tmp, ".beads/issues.jsonl", "beads leak\n")


class CountingProvider:
    def __init__(self):
        self.calls: list[tuple] = []
        self.mutations = {"add": 0, "delete": 0, "write_ack": 0}

    def list_sources(self, *, notebook_ref: str) -> dict:
        self.calls.append(("list_sources", notebook_ref))
        return {"ok": True, "sources": []}

    def query(self, question: str, **kwargs) -> dict:
        self.calls.append(("query", question))
        return {
            "ok": True,
            "answer": f"provider answer for: {question[:40]}",
            "sources": [{"doc_id": "active_spec", "source_id": "RAW-SOURCE-ID-SECRET"}],
        }

    def add_file_source(self, **kwargs):
        self.mutations["add"] += 1
        raise RuntimeError("query must not add")

    def delete_source(self, **kwargs):
        self.mutations["delete"] += 1
        raise RuntimeError("query must not delete")


def _run(monkeypatch, tmp: Path, argv: list[str], capsys) -> tuple[int, dict]:
    monkeypatch.chdir(tmp)
    code = main(argv)
    return code, json.loads(capsys.readouterr().out)


@pytest.mark.integration
def test_P10_QUERY_01_synced_routes_to_provider(tmp_path: Path, monkeypatch):
    _seed(tmp_path)
    monkeypatch.setenv("NOTEBOOKLM_NOTEBOOK_OPM_TEST", "nb-q1")
    provider = CountingProvider()
    result = route_knowledge_query(
        repo_root=tmp_path,
        question="publish migration",
        sync_state_override="synced",
        provider=provider,
        home=tmp_path,
    )
    assert result["ok"] is True
    assert result["provider"] == "notebooklm"
    assert result["sync_state"] == "synced"
    assert any(c[0] == "query" for c in provider.calls)


@pytest.mark.integration
def test_P10_QUERY_02_and_READONLY_no_mutation(tmp_path: Path, monkeypatch):
    _seed(tmp_path)
    monkeypatch.setenv("NOTEBOOKLM_NOTEBOOK_OPM_TEST", "nb-q2")
    provider = CountingProvider()
    ack = FakeAckStore()
    route_knowledge_query(
        repo_root=tmp_path,
        question="publish",
        sync_state_override="synced",
        provider=provider,
        ack_store=ack,
        home=tmp_path,
    )
    assert provider.mutations["add"] == 0
    assert provider.mutations["delete"] == 0
    assert ack.write_count == 0


@pytest.mark.integration
def test_P10_QUERY_03_pending_fallback(tmp_path: Path, monkeypatch):
    _seed(tmp_path)
    result = route_knowledge_query(
        repo_root=tmp_path,
        question="publish migration",
        sync_state_override="pending",
        home=tmp_path,
    )
    assert result["sync_state"] == "pending"
    assert result["provider"] == "repo"
    assert result["mode"] in {"degraded", "pending"}
    assert result.get("warnings")


@pytest.mark.integration
def test_P10_QUERY_04_drift_not_synced(tmp_path: Path, monkeypatch):
    _seed(tmp_path)
    result = route_knowledge_query(
        repo_root=tmp_path,
        question="publish",
        sync_state_override="drift",
        home=tmp_path,
    )
    assert result["sync_state"] == "drift"
    assert result.get("synced") is not True
    assert result["provider"] == "repo"


@pytest.mark.integration
def test_P10_QUERY_05_unavailable_degraded(tmp_path: Path, monkeypatch):
    _seed(tmp_path)
    result = route_knowledge_query(
        repo_root=tmp_path,
        question="publish migration",
        sync_state_override="unavailable",
        home=tmp_path,
    )
    assert result["mode"] == "degraded"
    assert result["provider"] == "repo"
    assert "degraded" in " ".join(result.get("warnings") or []).lower() or result["mode"] == "degraded"


@pytest.mark.integration
def test_P10_QUERY_06_target_mismatch_blocks_provider(tmp_path: Path, monkeypatch):
    _seed(tmp_path)
    provider = CountingProvider()
    result = route_knowledge_query(
        repo_root=tmp_path,
        question="publish",
        sync_state_override="target_mismatch",
        provider=provider,
        home=tmp_path,
    )
    assert result["sync_state"] == "target_mismatch"
    assert not any(c[0] == "query" for c in provider.calls)
    assert result["provider"] == "repo"


@pytest.mark.integration
def test_P10_FALLBACK_01_and_02_ssot_only(tmp_path: Path, monkeypatch, capsys):
    _seed(tmp_path)
    q = tmp_path / "q.txt"
    q.write_text("xyzzy", encoding="utf-8")
    code, payload = _run(
        monkeypatch,
        tmp_path,
        ["knowledge", "query", "--question-file", str(q), "--json"],
        capsys,
    )
    assert code == 0
    text = json.dumps(payload)
    assert "xyzzy" not in text or payload["data"].get("sources") == []
    # plan path must not appear as hit
    sources = payload.get("data", {}).get("sources") or []
    paths = [s.get("path") for s in sources]
    assert not any(p and "plans/" in p for p in paths)
    assert not any(p and p.startswith("runtime/") for p in paths)
    assert not any(p and p.startswith("acceptance/") for p in paths)
    assert not any(p and ".beads" in (p or "") for p in paths)


@pytest.mark.integration
def test_P10_FALLBACK_03_config_policy_question(tmp_path: Path, monkeypatch):
    _seed(tmp_path)
    result = route_knowledge_query(
        repo_root=tmp_path,
        question="What does require_commit_push_for_ssot mean in config policy?",
        sync_state_override="unavailable",
        allow_config_policy=True,
        home=tmp_path,
    )
    assert result["provider"] == "repo"
    assert result.get("config_as_policy") is True
    assert result.get("config_synced_as_content") is False


@pytest.mark.integration
def test_P10_ENVELOPE_01_synced_fields(tmp_path: Path, monkeypatch):
    _seed(tmp_path)
    provider = CountingProvider()
    result = route_knowledge_query(
        repo_root=tmp_path,
        question="publish",
        sync_state_override="synced",
        provider=provider,
        home=tmp_path,
    )
    assert "sync_state" in result
    assert "provider_target" in result
    assert "ack_persistence" in result
    assert "sources" in result
    assert "warnings" in result


@pytest.mark.integration
def test_P10_ENVELOPE_02_degraded(tmp_path: Path, monkeypatch):
    _seed(tmp_path)
    result = route_knowledge_query(
        repo_root=tmp_path,
        question="publish",
        sync_state_override="unavailable",
        home=tmp_path,
    )
    assert result["mode"] == "degraded"
    assert result["provider"] == "repo"


@pytest.mark.integration
def test_P10_ENVELOPE_03_redacts_raw_ids(tmp_path: Path, monkeypatch):
    _seed(tmp_path)
    provider = CountingProvider()
    result = route_knowledge_query(
        repo_root=tmp_path,
        question="publish",
        sync_state_override="synced",
        provider=provider,
        home=tmp_path,
    )
    blob = json.dumps(result)
    assert "RAW-SOURCE-ID-SECRET" not in blob
