"""Capability Profile install/init guidance — default-disabled preview + enable examples."""

from __future__ import annotations

import json
from pathlib import Path

from helpers import minimal_config_dict, write_control_yaml, write_doc
from vibe_control.cli import main
from vibe_control.components import (
    COMPONENT_CATALOG,
    build_component_config_guidance,
    resolve_component_runtime,
)
from vibe_control.config import template_path
from vibe_control.knowledge.doctor import build_knowledge_init_preview
from vibe_control.knowledge.notebooklm_provider import NotebookLMProvider, NotebookLMStatus
from vibe_control.task.beads_provider import BeadsProvider, BeadsStatus


class FakeNLM(NotebookLMProvider):
    def which(self):
        return "/tmp/fake-nlm"

    def status(self, *, probe_auth: bool = False) -> NotebookLMStatus:
        return NotebookLMStatus(
            installed=True, executable="/tmp/fake-nlm", version="x", message="ok"
        )


class FakeBeads(BeadsProvider):
    def which(self):
        return "/tmp/fake-bd"

    def status(self) -> BeadsStatus:
        return BeadsStatus(
            installed=True, executable="/tmp/fake-bd", version="x", message="ok"
        )

    def init_preview(self) -> BeadsStatus:
        st = self.status()
        st.init_available = True
        st.init_safe_mode = "skip_agents"
        st.recommended_init = "bd init --skip-agents"
        return st


def _write_repo(tmp_path):
    write_control_yaml(
        tmp_path,
        {
            **minimal_config_dict(enable_knowledge=False, enable_task=False),
            "project": {"id": "vibe-control", "name": "Vibe"},
        },
    )
    write_doc(tmp_path, "docs/project/vibe-control-spec.md", "# Spec\n")


def test_profile_preview_all_disabled_by_default():
    guidance = build_component_config_guidance()
    assert guidance["profile_preview"]["default_disabled"] is True
    assert guidance["profile_preview"]["readonly"] is True
    assert guidance["mutation"] is False
    assert guidance["auto_enable"] is False
    assert guidance["install_adapt_uninstall"] is False
    for cid, meta in COMPONENT_CATALOG.items():
        entry = guidance["components"][cid]
        assert entry["enabled"] is False
        assert entry["default_enabled"] is meta["default_enabled"] is False
        assert guidance["component_config_example"][cid]["enabled"] is False


def test_preview_marks_knowledge_task_available_enablable():
    guidance = build_component_config_guidance()
    for cid in ("knowledge", "task"):
        entry = guidance["components"][cid]
        assert entry["available"] is True
        assert entry["enablable"] is True
        assert entry["not_implemented"] is False
        assert entry["support_state"] == "supported"


def test_preview_marks_sdd_tdd_not_implemented():
    guidance = build_component_config_guidance()
    for cid in ("sdd", "tdd"):
        entry = guidance["components"][cid]
        assert entry["available"] is False
        assert entry["enablable"] is False
        assert entry["not_implemented"] is True
        assert entry["support_state"] == "not_supported_yet"
        assert entry.get("provider_hints_are_active") is False


def test_enable_examples_cover_knowledge_task_and_combined():
    guidance = build_component_config_guidance()
    examples = guidance["enable_examples"]
    ids = {ex["id"] for ex in examples}
    assert ids == {"enable_knowledge", "enable_task", "enable_knowledge_and_task"}
    for ex in examples:
        assert ex["diagnostic_only"] is True
        assert ex["mutation"] is False
        assert ex.get("prerequisites")
        assert "enabled: true" in ex["yaml_snippet"]
        assert "does not mutate" in ex["why"].lower() or "readonly" in ex["why"].lower()


def test_enable_examples_readonly_do_not_mutate_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_repo(tmp_path)
    cfg = tmp_path / ".vibe" / "control.yaml"
    before = cfg.read_text(encoding="utf-8")
    guidance = build_component_config_guidance()
    assert guidance["enable_examples"]
    after = cfg.read_text(encoding="utf-8")
    assert after == before
    # Examples resolve as config-valid when applied as resolver input (preview only).
    for ex in guidance["enable_examples"]:
        import yaml

        raw = yaml.safe_load(ex["yaml_snippet"])
        resolved = resolve_component_runtime(raw.get("components"))
        assert resolved["config_ok"] is True


def test_invalid_sdd_tdd_unknown_provider_scoped_diagnostic_only():
    guidance = build_component_config_guidance()
    invalid = guidance["invalid_examples"]
    assert all(ex.get("diagnostic_only") is True for ex in invalid)
    reasons = {ex.get("block_reason") for ex in invalid}
    assert "unsupported_component_enabled" in reasons
    assert "unknown_component_configured" in reasons
    blob = json.dumps(invalid)
    assert "sdd" in blob and "enabled: true" in blob
    assert "tdd" in blob
    assert "openspec" in blob
    assert "knowledge.notebooklm" in blob
    assert "tasks.beads" in blob
    assert "specs.sdd" in blob
    assert "method.superpowers" in blob
    assert "not provider unavailable" in blob.lower()
    # Enable examples must not be classified as invalid block reasons.
    assert all(ex.get("block_reason") for ex in invalid)


def test_guidance_next_actions_are_readonly_config_prerequisites():
    guidance = build_component_config_guidance()
    actions = guidance["next_actions"]
    codes = {a["code"] for a in actions}
    assert "REVIEW_DEFAULT_DISABLED_PROFILE" in codes
    assert "ENABLE_KNOWLEDGE_CONFIG_PREVIEW" in codes
    assert "ENABLE_TASK_CONFIG_PREVIEW" in codes
    assert all(a.get("mutation") is False for a in actions)
    joined = json.dumps(actions).lower()
    assert "auto-enable" in joined or "does not auto-enable" in joined
    assert "openspec" not in joined
    assert "superpowers" not in joined


def test_template_still_default_disabled():
    raw = __import__("yaml").safe_load(template_path().read_text(encoding="utf-8"))
    comps = raw["components"]
    assert comps["knowledge"]["enabled"] is False
    assert comps["task"]["enabled"] is False
    assert comps["sdd"]["enabled"] is False
    assert comps["tdd"]["enabled"] is False


def test_doctor_and_init_previews_expose_profile_guidance(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)
    _write_repo(tmp_path)
    monkeypatch.setattr("vibe_control.cli.NotebookLMProvider", FakeNLM)
    monkeypatch.setattr("vibe_control.cli.BeadsProvider", FakeBeads)

    code = main(["doctor", "--json"])
    doctor = json.loads(capsys.readouterr().out)
    assert code == 0
    d = doctor["data"]
    assert d["profile_preview"]["default_disabled"] is True
    assert d["enable_examples"]
    assert d["auto_enable"] is False
    assert d["install_adapt_uninstall"] is False
    assert any(a.get("code") == "ENABLE_KNOWLEDGE_CONFIG_PREVIEW" for a in doctor["next_actions"])

    preview = build_knowledge_init_preview(repo_root=tmp_path, notebooklm=FakeNLM())
    pdata = preview["data"]
    assert pdata["profile_preview"]["default_disabled"] is True
    assert len(pdata["enable_examples"]) == 3
    assert pdata["mutation"] is False

    code_t = main(["task", "init-preview", "--json"])
    task = json.loads(capsys.readouterr().out)
    assert code_t == 0
    td = task["data"]
    assert td["profile_preview"]["default_disabled"] is True
    assert td["components"]["knowledge"]["enablable"] is True
    assert td["components"]["sdd"]["not_implemented"] is True
    assert td["mutation"] is False


def test_no_provider_mutation_in_readonly_guidance_paths(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_repo(tmp_path)
    before = {p.as_posix() for p in tmp_path.rglob("*") if p.is_file()}
    build_component_config_guidance()
    build_knowledge_init_preview(repo_root=tmp_path, notebooklm=FakeNLM())
    after = {p.as_posix() for p in tmp_path.rglob("*") if p.is_file()}
    assert after == before


def test_roadmap_marks_install_init_completed_and_doctor_completed():
    from vibe_control.task.roadmap_state import load_roadmap_state

    state = load_roadmap_state(Path.cwd())
    assert state["next_actionable_task"] is None
    by = {a["ssot_anchor"]: a for a in state["anchors"]}
    assert by["roadmap.vibe_capability_profile_install_init_guidance"]["phase_state"] == "completed"
    assert by["roadmap.vibe_capability_profile_install_init_guidance"]["actionable"] is False
    assert by["roadmap.vibe_capability_profile_doctor_gateway_guidance"]["phase_state"] == "completed"
    assert by["roadmap.vibe_capability_profile_doctor_gateway_guidance"]["actionable"] is False
    assert by["roadmap.vibe_capability_profile_runtime"]["phase_state"] == "completed"
    assert "roadmap.phase13" not in by
