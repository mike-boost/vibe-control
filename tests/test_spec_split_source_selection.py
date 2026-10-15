"""Spec split / source-selection tests for three-layer formal specs."""

from __future__ import annotations

from pathlib import Path

import yaml

from vibe_control.config import load_config
from vibe_control.knowledge.corpus import build_desired_corpus
from vibe_control.spec.registry import load_registry, validate_entries


def test_registry_includes_three_active_formal_specs():
    result = load_registry(Path("docs/project/spec-registry.yml"))
    assert result.errors == []
    by_id = {e.id: e for e in result.entries}
    assert by_id["vibe_control_spec"].status == "active"
    assert by_id["vibe_control_spec"].path == "docs/project/vibe-control-spec.md"
    assert by_id["vibe_control_knowledge_spec"].status == "active"
    assert by_id["vibe_control_knowledge_spec"].path == "docs/project/vibe-control-knowledge-spec.md"
    assert by_id["vibe_control_task_spec"].status == "active"
    assert by_id["vibe_control_task_spec"].path == "docs/project/vibe-control-task-spec.md"
    assert by_id["vibe_control_roadmap_state"].status == "active"
    assert by_id["vibe_control_roadmap_state"].path == "docs/project/vibe-control-roadmap-state.md"
    assert "old_vibe_control_draft" not in by_id
    assert not Path("docs/project/OLD_VIBE_CONTROL_DRAFT.md").exists()


def test_inventory_includes_active_specs_plus_roadmap_state_not_sync_phase_docs():
    root = Path.cwd()
    config = load_config(root)
    corpus = build_desired_corpus(config, repo_root=root)
    paths = [d.path for d in corpus.documents]
    joined = "\n".join(paths)
    assert "docs/project/vibe-control-spec.md" in paths
    assert "docs/project/vibe-control-knowledge-spec.md" in paths
    assert "docs/project/vibe-control-task-spec.md" in paths
    assert "docs/project/vibe-control-roadmap-state.md" in paths
    assert "docs/project/DECISION_LOG.md" not in paths
    assert all("/sync/" not in p for p in paths)
    assert ".config/vibe-control.yaml" not in joined
    assert "spec-registry.yml" not in joined
    assert corpus.source_count == 4


def test_phase_sync_docs_not_selected_by_default_registry():
    result = load_registry(Path("docs/project/spec-registry.yml"))
    selected, _warnings, errors = validate_entries(
        result.entries,
        required_fields=["id", "status", "path"],
        authoritative_statuses=["active"],
    )
    assert not errors or all("missing" not in e for e in errors) or selected
    for entry in selected:
        assert entry.path is not None
        assert "/sync/" not in entry.path
        assert not entry.path.startswith("docs/project/sync/")


def test_front_core_spec_points_to_companions():
    text = Path("docs/project/vibe-control-spec.md").read_text(encoding="utf-8")
    assert "vibe-control-knowledge-spec.md" in text
    assert "vibe-control-task-spec.md" in text
    assert "ssot_change_committed_sync_required" in text
    assert "vibe implementation prompt" in text
    assert "external advisor context copies" in text.lower()
    assert "not a product closeout gate" in text.lower()
    assert "waiting_owner_project_sources" in text  # explicitly rejected as a state
    assert "owner Project Sources handoff" not in text
    assert "missing Project Sources handoff" not in text
    assert "ChatGPT" not in text
    for term in (
        "Vibe Control Engine",
        "Vibe Gateway",
        "Vibe Progress",
        "Vibe Describe",
        "Vibe Brief",
        "Vibe Evidence",
        "S1 Ephemeral Operation Snapshot",
    ):
        assert term in text
    assert "no second readiness" in text.lower()
    assert "no sub-agent support" in text.lower()


def test_knowledge_spec_external_advisor_copies_not_closeout_gate():
    text = Path("docs/project/vibe-control-knowledge-spec.md").read_text(encoding="utf-8")
    assert "NOT a product closeout gate" in text or "not a product closeout gate" in text.lower()
    assert "external advisor context copies" in text.lower()
    assert "not blocked on external advisor context copies" in text.lower()
    assert "ChatGPT" not in text
    assert "waiting_owner_project_sources" in text  # explicitly rejected
    assert "sync reads repo SSOT" in text or "default inventory" in text


def test_registry_yaml_shape():
    data = yaml.safe_load(Path("docs/project/spec-registry.yml").read_text(encoding="utf-8"))
    ids = [e["id"] for e in data["entries"]]
    assert ids.count("vibe_control_spec") == 1
    assert "vibe_control_knowledge_spec" in ids
    assert "vibe_control_task_spec" in ids
    assert "vibe_control_roadmap_state" in ids
