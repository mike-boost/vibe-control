"""Component Runtime Slice 5 — future provider integration boundary preparation."""

from __future__ import annotations

import json

from helpers import minimal_config_dict, write_control_yaml, write_doc
from vibe_control.cli import main
from vibe_control.components import (
    COMPONENT_CATALOG,
    build_component_adoption_detection,
    build_component_provider_boundaries,
    evaluate_provider_integration_request,
    resolve_component_runtime,
)
from vibe_control.integration import build_integration_status
from vibe_control.knowledge.doctor import build_knowledge_init_preview
from vibe_control.knowledge.notebooklm_provider import NotebookLMProvider, NotebookLMStatus
from vibe_control.product_readiness import build_probe_from_parts
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
        return BeadsStatus(installed=True, executable="/tmp/fake-bd", version="x", message="ok")

    def init_preview(self) -> BeadsStatus:
        return self.status()


def _write_repo(tmp_path, *, components=None):
    raw = {
        **minimal_config_dict(enable_knowledge=False, enable_task=False),
        "project": {"id": "vibe-control", "name": "Vibe"},
    }
    if components is not None:
        raw["components"] = components
    write_control_yaml(tmp_path, raw)
    write_doc(tmp_path, "docs/project/vibe-control-spec.md", "# Spec\n")
    write_doc(tmp_path, "docs/project/spec-registry.yml", "entries: []\n")


def test_provider_boundaries_report_sdd_tdd_hints_not_active():
    report = build_component_provider_boundaries()
    assert report["diagnostic_only"] is True
    assert report["mutation"] is False
    assert report["live_integration"] is False  # Slice 5 prep surface is not a live integrator
    assert report["mutation_allowed"] is False
    assert report["requires_future_acceptance"] is True
    assert report["fail_closed"] is True
    boundaries = report["provider_boundaries"]
    by_comp = {b["component_id"]: b for b in boundaries}
    assert set(by_comp) == set(COMPONENT_CATALOG)
    assert by_comp["sdd"]["provider_hints"] == ["openspec", "spec_kit"]
    assert by_comp["sdd"]["live_integration"] is False
    assert by_comp["sdd"]["mutation_allowed"] is False
    assert by_comp["sdd"]["requires_future_acceptance"] is True
    assert by_comp["sdd"]["active_provider"] is None
    assert by_comp["tdd"]["provider_hints"] == ["superpowers"]
    assert by_comp["tdd"]["live_integration"] is False
    assert by_comp["tdd"]["active_provider"] is None
    # Existing product providers remain reported as already-implemented bindings,
    # not as Slice-5 live integration work.
    assert by_comp["knowledge"]["bound_provider"] == "notebooklm"
    assert by_comp["knowledge"]["existing_runtime"] is True
    assert by_comp["task"]["bound_provider"] == "beads"
    assert by_comp["task"]["existing_runtime"] is True


def test_provider_hints_are_not_active_providers():
    report = build_component_provider_boundaries()
    for boundary in report["provider_boundaries"]:
        for hint in boundary.get("provider_hints") or []:
            assert hint != boundary.get("active_provider")
            # Future-hint components must not treat hints as the bound provider.
            # Existing-runtime components (e.g. hetu) may list the bound provider
            # alongside future hints such as codegraph.
            if not boundary.get("existing_runtime"):
                assert hint not in (boundary.get("bound_provider"),)
        assert boundary.get("provider_hints_are_active") is False


def test_fail_closed_sdd_openspec_live_integration():
    result = evaluate_provider_integration_request(
        component_id="sdd",
        provider_id="openspec",
        intent="live_integrate",
    )
    assert result["ok"] is False
    assert result["fail_closed"] is True
    assert result["reason_code"] == "unsupported_provider_integration"
    assert result["live_integration"] is False
    assert result["mutation_allowed"] is False
    assert result["requires_future_acceptance"] is True
    assert result["not_provider_unavailable"] is True
    assert result["empty_inventory"] is False


def test_fail_closed_sdd_spec_kit_and_tdd_superpowers():
    for component_id, provider_id in (
        ("sdd", "spec_kit"),
        ("tdd", "superpowers"),
    ):
        result = evaluate_provider_integration_request(
            component_id=component_id,
            provider_id=provider_id,
            intent="live_integrate",
        )
        assert result["ok"] is False
        assert result["fail_closed"] is True
        assert result["reason_code"] == "unsupported_provider_integration"
        assert "unavailable" not in result["reason_code"]


def test_fail_closed_unknown_pair_and_provider_scoped_ids():
    unknown = evaluate_provider_integration_request(
        component_id="sdd",
        provider_id="unknown_tool",
        intent="live_integrate",
    )
    assert unknown["ok"] is False
    assert unknown["fail_closed"] is True
    assert unknown["reason_code"] == "unsupported_provider_integration"

    for bad_id in (
        "knowledge.notebooklm",
        "tasks.beads",
        "specs.sdd",
        "method.superpowers",
    ):
        result = evaluate_provider_integration_request(
            component_id=bad_id,
            provider_id="anything",
            intent="live_integrate",
        )
        assert result["ok"] is False
        assert result["fail_closed"] is True
        assert result["reason_code"] == "provider_scoped_name_not_component_id"
        assert result["not_provider_unavailable"] is True


def test_detected_candidate_not_treated_as_adopted_provider():
    adoption = build_component_adoption_detection(
        which=lambda name: "/tmp/fake-openspec" if name == "openspec" else None
    )
    by_id = {c["candidate_id"]: c for c in adoption["component_adoption"]["candidates"]}
    assert by_id["openspec"]["detection_status"] == "detected"
    assert by_id["openspec"]["adopted"] is False
    assert by_id["openspec"]["provider_bound"] is False
    result = evaluate_provider_integration_request(
        component_id="sdd",
        provider_id="openspec",
        intent="adopt_detected_candidate",
    )
    assert result["ok"] is False
    assert result["fail_closed"] is True
    assert result["reason_code"] == "detected_candidate_not_adopted"
    assert result["mutation_allowed"] is False


def test_treating_provider_hints_as_active_fails_closed():
    result = evaluate_provider_integration_request(
        component_id="tdd",
        provider_id="superpowers",
        intent="treat_hint_as_active_provider",
    )
    assert result["ok"] is False
    assert result["fail_closed"] is True
    assert result["reason_code"] == "provider_hint_not_active_provider"


def test_boundary_prep_does_not_flip_readiness():
    report = build_component_provider_boundaries()
    assert report["readiness_effect"] == "none"
    runtime = resolve_component_runtime(None)
    probe = build_probe_from_parts(
        knowledge_available=True,
        knowledge_target_ok=True,
        sync_state="synced",
        required_updates_count=0,
        candidate_count=0,
        orphan_managed_count=0,
        task_available=True,
        task_mode="readonly",
        task_readable=True,
        ready_queue_available=True,
        task_cache_current=True,
        config_ok=runtime["config_ok"],
        components=runtime["components"],
        component_blocked_reasons=runtime["blocked_reasons"],
    )
    assert probe.product_ready is True
    assert probe.config_ok is True
    assert runtime["components"]["sdd"]["enabled"] is False
    assert runtime["components"]["tdd"]["enabled"] is False


def test_doctor_exposes_provider_boundaries(tmp_path, monkeypatch, capsys):
    _write_repo(tmp_path)
    cfg = tmp_path / ".vibe" / "control.yaml"
    before = cfg.read_text(encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("vibe_control.cli.NotebookLMProvider", FakeNLM)
    monkeypatch.setattr("vibe_control.cli.BeadsProvider", FakeBeads)
    code = main(["doctor", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload.get("mutation") is not True
    data = payload["data"]
    assert data["config_ok"] is True
    assert "components" in data
    assert "component_blocked_reasons" in data
    assert "component_adoption" in data
    boundaries = data["provider_boundaries"]
    assert data["mutation_allowed"] is False
    assert data["requires_future_acceptance"] is True
    assert data["fail_closed"] is True
    assert data["live_integration"] is False
    by_comp = {b["component_id"]: b for b in boundaries}
    assert by_comp["sdd"]["live_integration"] is False
    assert by_comp["tdd"]["provider_hints"] == ["superpowers"]
    assert cfg.read_text(encoding="utf-8") == before


def test_init_preview_exposes_provider_boundaries(tmp_path, monkeypatch):
    _write_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    envelope = build_knowledge_init_preview(repo_root=tmp_path, notebooklm=FakeNLM())
    assert envelope["mutation"] is False
    data = envelope["data"]
    assert data["diagnostic_only"] is True
    assert data["mutation"] is False
    assert data["mutation_allowed"] is False
    assert data["requires_future_acceptance"] is True
    assert data["fail_closed"] is True
    assert data["live_integration"] is False
    assert data["provider_boundaries"]
    assert data["component_config_example"]["sdd"]["enabled"] is False


def test_integration_status_unaffected_by_boundary_prep(tmp_path, monkeypatch):
    monkeypatch.setenv("VIBE_SKILLS_ROOT", str(tmp_path / "skills"))
    _write_repo(tmp_path)
    data = build_integration_status(
        repo_root=tmp_path,
        notebooklm=FakeNLM(),
        beads=FakeBeads(),
        probe_product=False,
        knowledge_parts={
            "available": True,
            "target_ok": True,
            "sync_state": "synced",
            "required_updates_count": 0,
            "candidate_count": 0,
            "orphan_managed_count": 0,
        },
        task_parts={
            "available": True,
            "mode": "readonly",
            "readable": True,
            "ready_queue_available": True,
        },
    )
    assert data["config_ok"] is True
    assert set(data["components"]) == {"knowledge", "task", "hetu", "sdd", "tdd"}
    assert data["components"]["sdd"]["enabled"] is False
    assert data["product_ready"] is True
