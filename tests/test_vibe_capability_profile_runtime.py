"""Capability Profile runtime — default-disabled, enable-gated readiness."""

from __future__ import annotations

import json
from pathlib import Path

from helpers import minimal_config_dict, write_control_yaml, write_doc
from vibe_control.cli import main
from vibe_control.components import (
    COMPONENT_CATALOG,
    resolve_component_runtime,
)
from vibe_control.product_readiness import build_probe_from_parts, evaluate_product_readiness


def _enabled_components(*, knowledge: bool = False, task: bool = False, **extra):
    comps = {
        "knowledge": {"enabled": knowledge},
        "task": {"enabled": task},
        "sdd": {"enabled": False},
        "tdd": {"enabled": False},
    }
    comps.update(extra)
    return resolve_component_runtime(comps)["components"]


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


# --- A. Fresh/default profile ---


def test_catalog_defaults_all_disabled():
    for cid, meta in COMPONENT_CATALOG.items():
        assert meta["default_enabled"] is False, cid


def test_no_components_config_all_disabled():
    result = resolve_component_runtime(None)
    assert result["config_ok"] is True
    assert result["blocked_reasons"] == []
    comps = result["components"]
    for cid in ("knowledge", "task", "hetu", "sdd", "tdd"):
        assert comps[cid]["enabled"] is False
        assert comps[cid]["skipped"] is True
        assert comps[cid]["checked"] is False
    assert comps["knowledge"]["available"] is True
    assert comps["task"]["available"] is True
    assert comps["hetu"]["available"] is True
    assert comps["sdd"]["not_implemented"] is True
    assert comps["tdd"]["not_implemented"] is True
    assert result["capability_profile"]["default_disabled"] is True
    assert result["capability_profile"]["hetu_enabled"] is False


def test_default_disabled_providers_unavailable_still_product_ready():
    probe = build_probe_from_parts(
        knowledge_available=False,
        knowledge_target_ok=False,
        sync_state="unavailable",
        task_available=False,
        task_mode="unavailable",
        task_readable=False,
        task_cache_current=False,
        components=resolve_component_runtime(None)["components"],
    )
    assert probe.product_ready is True
    assert probe.blocked_reasons == []
    assert "knowledge_provider_unavailable" not in probe.blocked_reasons
    assert "task_provider_unavailable" not in probe.blocked_reasons


def test_default_disabled_repo_evaluate_product_ready(tmp_path, monkeypatch):
    monkeypatch.setenv("VIBE_SKILLS_ROOT", str(tmp_path / "skills"))
    _write_repo(tmp_path, components=None)
    probe = evaluate_product_readiness(
        repo_root=tmp_path,
        knowledge={
            "available": False,
            "target_ok": False,
            "sync_state": "unavailable",
            "required_updates_count": 0,
            "candidate_count": 0,
            "orphan_managed_count": 0,
        },
        task={
            "available": False,
            "mode": "unavailable",
            "readable": False,
            "ready_queue_available": None,
        },
        task_cache={"task_cache_current": False},
        probe=False,
        probe_task_cache_state=False,
    )
    assert probe.config_ok is True
    assert probe.product_ready is True
    assert probe.components["knowledge"]["enabled"] is False
    assert probe.components["task"]["enabled"] is False


# --- B. Enabled knowledge ---


def test_knowledge_enabled_provider_ready_passes():
    comps = _enabled_components(knowledge=True)
    probe = build_probe_from_parts(
        knowledge_available=True,
        knowledge_target_ok=True,
        sync_state="synced",
        task_available=False,
        task_mode="unavailable",
        task_readable=False,
        components=comps,
    )
    assert probe.product_ready is True
    assert probe.components["knowledge"]["ready"] is True


def test_knowledge_enabled_unavailable_fails():
    comps = _enabled_components(knowledge=True)
    probe = build_probe_from_parts(
        knowledge_available=False,
        knowledge_target_ok=False,
        sync_state="unavailable",
        task_available=True,
        task_mode="readonly",
        task_readable=True,
        components=comps,
    )
    assert probe.product_ready is False
    assert "knowledge_provider_unavailable" in probe.blocked_reasons


def test_knowledge_enabled_drift_or_ask_unclean_fails():
    comps = _enabled_components(knowledge=True)
    drift = build_probe_from_parts(
        knowledge_available=True,
        knowledge_target_ok=True,
        sync_state="drift",
        required_updates_count=1,
        task_available=False,
        task_mode="unavailable",
        task_readable=False,
        components=comps,
    )
    assert drift.product_ready is False
    assert any("sync_state" in r for r in drift.blocked_reasons)

    unclean = build_probe_from_parts(
        knowledge_available=True,
        knowledge_target_ok=True,
        sync_state="synced",
        required_updates_count=0,
        candidate_count=2,
        orphan_managed_count=1,
        task_available=False,
        task_mode="unavailable",
        task_readable=False,
        components=comps,
    )
    # orphan/candidate may flip ask hygiene depending on evaluate_ask_hygiene
    if not unclean.provider_ask_clean:
        assert unclean.product_ready is False
        assert any("ask_hygiene" in r for r in unclean.blocked_reasons)


# --- C. Enabled task ---


def test_task_enabled_cache_current_passes():
    comps = _enabled_components(task=True)
    probe = build_probe_from_parts(
        knowledge_available=False,
        knowledge_target_ok=False,
        sync_state="unavailable",
        task_available=True,
        task_mode="readonly",
        task_readable=True,
        task_cache_current=True,
        components=comps,
    )
    assert probe.product_ready is True
    assert probe.components["task"]["ready"] is True


def test_task_enabled_unavailable_fails_not_empty_inventory():
    comps = _enabled_components(task=True)
    probe = build_probe_from_parts(
        knowledge_available=False,
        knowledge_target_ok=False,
        sync_state="unavailable",
        task_available=False,
        task_mode="unavailable",
        task_readable=False,
        components=comps,
    )
    assert probe.product_ready is False
    assert "task_provider_unavailable" in probe.blocked_reasons
    assert "empty_inventory" not in " ".join(probe.blocked_reasons)


def test_task_enabled_cache_stale_fails():
    comps = _enabled_components(task=True)
    probe = build_probe_from_parts(
        knowledge_available=False,
        knowledge_target_ok=False,
        sync_state="unavailable",
        task_available=True,
        task_mode="readonly",
        task_readable=True,
        task_cache_current=False,
        components=comps,
    )
    assert probe.product_ready is False
    assert "task_cache_not_current" in probe.blocked_reasons


# --- D. Unsupported ---


def test_sdd_tdd_enabled_fail_closed():
    for cid in ("sdd", "tdd"):
        result = resolve_component_runtime({cid: {"enabled": True}})
        assert result["config_ok"] is False
        assert "unsupported_component_enabled" in result["blocked_reasons"]
        probe = build_probe_from_parts(
            knowledge_available=False,
            knowledge_target_ok=False,
            sync_state="unavailable",
            task_available=False,
            task_mode="unavailable",
            task_readable=False,
            config_ok=False,
            components=result["components"],
            component_blocked_reasons=result["blocked_reasons"],
        )
        assert probe.product_ready is False
        assert "unsupported_component_enabled" in probe.blocked_reasons


def test_sdd_tdd_disabled_no_impact():
    result = resolve_component_runtime(
        {"sdd": {"enabled": False}, "tdd": {"enabled": False}}
    )
    assert result["config_ok"] is True
    probe = build_probe_from_parts(
        knowledge_available=False,
        knowledge_target_ok=False,
        sync_state="unavailable",
        task_available=False,
        task_mode="unavailable",
        task_readable=False,
        components=result["components"],
    )
    assert probe.product_ready is True


# --- E. Unknown / provider-scoped ---


def test_unknown_and_provider_scoped_fail_closed():
    for key in (
        "widget",
        "knowledge.notebooklm",
        "tasks.beads",
        "specs.sdd",
        "method.superpowers",
    ):
        result = resolve_component_runtime({key: {"enabled": True}})
        assert result["config_ok"] is False
        assert "unknown_component_configured" in result["blocked_reasons"]


# --- F. CLI visibility / regression ---


def test_integration_exposes_capability_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("VIBE_SKILLS_ROOT", str(tmp_path / "skills"))
    _write_repo(tmp_path, components=None)
    from vibe_control.integration import build_integration_status
    from vibe_control.knowledge.notebooklm_provider import NotebookLMProvider, NotebookLMStatus
    from vibe_control.task.beads_provider import BeadsProvider, BeadsStatus

    class FakeNLM(NotebookLMProvider):
        def which(self):
            return None

        def status(self, *, probe_auth: bool = False) -> NotebookLMStatus:
            return NotebookLMStatus(
                installed=False, executable=None, message="missing"
            )

    class FakeBeads(BeadsProvider):
        def which(self):
            return None

        def status(self) -> BeadsStatus:
            return BeadsStatus(installed=False, executable=None, message="missing")

        def init_preview(self) -> BeadsStatus:
            return self.status()

    status = build_integration_status(
        repo_root=tmp_path,
        notebooklm=FakeNLM(),
        beads=FakeBeads(),
        probe_auth=False,
        probe_product=False,
        knowledge_parts={
            "available": False,
            "target_ok": False,
            "sync_state": "unavailable",
        },
        task_parts={
            "available": False,
            "mode": "unavailable",
            "readable": False,
        },
    )
    assert status["product_ready"] is True
    assert status["config_ok"] is True
    assert status["components"]["knowledge"]["enabled"] is False
    assert status["components"]["knowledge"]["available"] is True
    assert status["capability_profile"]["default_disabled"] is True
    blob = json.dumps(status)
    assert "openspec" not in blob.lower() or "provider_hints" in blob


def test_doctor_shows_disabled_available(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    _write_repo(tmp_path, components=None)
    from vibe_control.knowledge.notebooklm_provider import NotebookLMProvider, NotebookLMStatus
    from vibe_control.task.beads_provider import BeadsProvider, BeadsStatus

    class FakeNLM(NotebookLMProvider):
        def which(self):
            return None

        def status(self, *, probe_auth: bool = False) -> NotebookLMStatus:
            return NotebookLMStatus(
                installed=False, executable=None, message="missing"
            )

    class FakeBeads(BeadsProvider):
        def which(self):
            return None

        def status(self) -> BeadsStatus:
            return BeadsStatus(installed=False, executable=None, message="missing")

        def init_preview(self) -> BeadsStatus:
            return self.status()

    monkeypatch.setattr("vibe_control.cli.NotebookLMProvider", FakeNLM)
    monkeypatch.setattr("vibe_control.cli.BeadsProvider", FakeBeads)
    code = main(["doctor", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    data = payload["data"]
    assert data["config_ok"] is True
    assert data["components"]["knowledge"]["enabled"] is False
    assert data["components"]["task"]["enabled"] is False
    assert data["component_config_example"]["knowledge"]["enabled"] is False


def test_roadmap_marks_capability_runtime_completed_and_promotes_install():
    from vibe_control.task.roadmap_state import load_roadmap_state

    state = load_roadmap_state(Path.cwd())
    assert state["next_actionable_task"] is None
    by = {a["ssot_anchor"]: a for a in state["anchors"]}
    assert by["roadmap.vibe_capability_profile_runtime"]["phase_state"] == "completed"
    assert by["roadmap.vibe_capability_profile_runtime"]["actionable"] is False
    assert by["roadmap.vibe_capability_profile_install_init_guidance"]["phase_state"] == "completed"
    assert by["roadmap.vibe_capability_profile_install_init_guidance"]["actionable"] is False
    assert by["roadmap.vibe_capability_profile_doctor_gateway_guidance"]["actionable"] is False
    assert by["roadmap.vibe_product_concept_boundary_contract"]["phase_state"] == "completed"
    assert "roadmap.phase13" not in by
