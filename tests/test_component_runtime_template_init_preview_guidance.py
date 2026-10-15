"""Component Runtime Slice 3 — template / init-preview component config guidance."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from vibe_control.cli import main
from vibe_control.components import (
    COMPONENT_CATALOG,
    build_component_config_guidance,
)
from vibe_control.config import template_path
from vibe_control.knowledge.doctor import build_knowledge_init_preview
from vibe_control.knowledge.notebooklm_provider import NotebookLMProvider, NotebookLMStatus


class FakeNLM(NotebookLMProvider):
    def which(self):
        return "/tmp/fake-nlm"

    def status(self, *, probe_auth: bool = False) -> NotebookLMStatus:
        return NotebookLMStatus(
            installed=True, executable="/tmp/fake-nlm", version="x", message="ok"
        )


def test_guidance_builder_default_shape_from_catalog():
    guidance = build_component_config_guidance()
    assert guidance["diagnostic_only"] is True
    assert guidance["mutation"] is False
    comps = guidance["components"]
    assert set(comps) == set(COMPONENT_CATALOG)
    assert comps["knowledge"]["enabled"] is False
    assert comps["knowledge"]["support_state"] == "supported"
    assert comps["knowledge"]["readiness_role"] == "optional_when_disabled"
    assert comps["task"]["enabled"] is False
    assert comps["sdd"]["enabled"] is False
    assert comps["sdd"]["support_state"] == "not_supported_yet"
    assert comps["tdd"]["enabled"] is False
    assert comps["tdd"]["support_state"] == "not_supported_yet"
    example = guidance["component_config_example"]
    assert example["knowledge"]["enabled"] is False
    assert example["task"]["enabled"] is False
    assert example["sdd"]["enabled"] is False
    assert example["tdd"]["enabled"] is False
    yaml_text = guidance["component_config_example_yaml"]
    assert "knowledge:" in yaml_text
    assert "enabled: false" in yaml_text
    assert "sdd:" in yaml_text


def test_guidance_invalid_examples_are_diagnostic_only():
    guidance = build_component_config_guidance()
    invalid = guidance["invalid_examples"]
    assert guidance["diagnostic_only"] is True
    assert all(ex.get("diagnostic_only") is True for ex in invalid)
    reasons = {ex.get("block_reason") for ex in invalid if ex.get("block_reason")}
    assert "unsupported_component_enabled" in reasons
    assert "unknown_component_configured" in reasons
    assert "required_component_disabled" not in reasons
    joined = json.dumps(invalid)
    assert "sdd" in joined and "enabled: true" in joined
    assert "tdd" in joined and "enabled: true" in joined
    assert "knowledge.notebooklm" in joined or "tasks.beads" in joined
    # Explicitly distinguish config failure from provider unavailable.
    assert any("not provider unavailable" in str(ex.get("why", "")).lower() for ex in invalid)
    assert "knowledge_provider_unavailable" not in joined
    assert "task_provider_unavailable" not in joined


def test_guidance_matches_catalog_defaults_no_drift():
    guidance = build_component_config_guidance()
    for cid, meta in COMPONENT_CATALOG.items():
        g = guidance["components"][cid]
        assert g["support_state"] == meta["support_state"]
        assert g["enabled"] is meta["default_enabled"]
        assert g["readiness_role"] == meta["readiness_role"]
        assert guidance["component_config_example"][cid]["enabled"] is meta["default_enabled"]


def test_control_yaml_template_includes_components_defaults():
    path = template_path()
    assert path.is_file()
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert "components" in raw
    comps = raw["components"]
    assert comps["knowledge"]["enabled"] is False
    assert comps["task"]["enabled"] is False
    assert comps["sdd"]["enabled"] is False
    assert comps["tdd"]["enabled"] is False
    text = path.read_text(encoding="utf-8")
    assert "not_supported_yet" in text or "optional" in text.lower()


def test_doctor_exposes_component_config_guidance(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("vibe_control.cli.NotebookLMProvider", FakeNLM)
    from vibe_control.task.beads_provider import BeadsProvider, BeadsStatus

    class FakeBeads(BeadsProvider):
        def which(self):
            return "/tmp/fake-bd"

        def status(self) -> BeadsStatus:
            return BeadsStatus(
                installed=True, executable="/tmp/fake-bd", version="x", message="ok"
            )

    monkeypatch.setattr("vibe_control.cli.BeadsProvider", FakeBeads)
    code = main(["doctor", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    data = payload["data"]
    assert data["config_ok"] is True
    assert "component_config_example" in data
    assert data["component_config_example"]["knowledge"]["enabled"] is False
    assert data["component_config_example"]["sdd"]["enabled"] is False
    assert data.get("diagnostic_only") is True
    assert data.get("mutation") is False
    invalid = data["invalid_examples"]
    assert any(ex["block_reason"] == "unsupported_component_enabled" for ex in invalid)
    assert any(ex["block_reason"] == "unknown_component_configured" for ex in invalid)
    assert not any(ex.get("block_reason") == "required_component_disabled" for ex in invalid)


def test_knowledge_init_preview_includes_component_guidance(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = build_knowledge_init_preview(repo_root=tmp_path, notebooklm=FakeNLM())
    data = result["data"]
    assert data.get("diagnostic_only") is True
    assert data.get("mutation") is False
    example = data["component_config_example"]
    assert example["task"]["enabled"] is False
    assert example["tdd"]["enabled"] is False
    invalid = data["invalid_examples"]
    assert invalid
    assert all(ex.get("diagnostic_only") is True for ex in invalid)


def test_guidance_readonly_does_not_write_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    before = {p.as_posix() for p in tmp_path.rglob("*") if p.is_file()}
    build_component_config_guidance()
    build_knowledge_init_preview(repo_root=tmp_path, notebooklm=FakeNLM())
    after = {p.as_posix() for p in tmp_path.rglob("*") if p.is_file()}
    assert after == before


def test_disabled_optional_unsupported_not_treated_as_error_in_guidance():
    guidance = build_component_config_guidance()
    # Default example itself must resolve config_ok
    from vibe_control.components import resolve_component_runtime

    resolved = resolve_component_runtime(guidance["component_config_example"])
    assert resolved["config_ok"] is True
    assert resolved["blocked_reasons"] == []
    # Guidance should not list default-disabled sdd/tdd as errors
    for ex in guidance["invalid_examples"]:
        assert not (
            ex.get("block_reason") == "unsupported_component_enabled"
            and "enabled: false" in ex.get("yaml_snippet", "")
        )
