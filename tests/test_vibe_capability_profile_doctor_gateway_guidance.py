"""Capability Profile doctor/gateway/describe/progress/brief guidance surfaces."""

from __future__ import annotations

import json
from pathlib import Path

from helpers import minimal_config_dict, write_control_yaml, write_doc
from vibe_control.cli import main
from vibe_control.components import (
    build_component_config_guidance,
    project_capability_guidance,
    resolve_component_runtime,
)
from vibe_control.describe import build_describe
from vibe_control.gateway import route_gateway
from vibe_control.product_readiness import build_probe_from_parts
from vibe_control.progress_brief import build_brief, build_progress


SENSITIVE_MARKERS = (
    "notebooklm://",
    "source_id",
    "Bearer ",
    "cookie=",
    "Authorization:",
    "private_ref",
)


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


def _default_disabled_status(**overrides):
    comps = resolve_component_runtime(None)
    status = {
        "ok": True,
        "product_ready": True,
        "config_ok": True,
        "provider_sync_required": False,
        "sync_state": "synced",
        "provider_ask_clean": True,
        "task_cache_current": True,
        "closeout_complete": True,
        "closeout_state": "complete",
        "blocked_reasons": [],
        "warnings": [],
        "next_actions": [],
        "project_id": "vibe-control",
        "components": comps["components"],
        "capability_profile": comps["capability_profile"],
        "knowledge_provider": {"available": False},
        "task_provider": {"available": False},
    }
    status.update(overrides)
    return status


def _next_selection(task="roadmap.vibe_capability_profile_doctor_gateway_guidance"):
    return {
        "next_actionable_task": task,
        "no_actionable_next_task": task is None,
        "anchor": {
            "ssot_anchor": task,
            "title": "doctor/gateway guidance",
            "task_kind": "implementation_task",
            "phase_state": "accepted",
            "actionable": True,
        }
        if task
        else None,
    }


def test_capability_guidance_structure_default_disabled():
    guidance = build_component_config_guidance()
    cg = guidance["capability_guidance"]
    assert cg["version"] == "vibe.capability_guidance.v1"
    assert cg["engine_readiness_separate"] is True
    assert cg["source_of_truth"] == "engine"
    assert cg["recomputes_readiness"] is False
    assert cg["mutation"] is False
    assert cg["default_disabled"] is True
    assert cg["disabled_do_not_fail_product_ready"] is True
    assert cg["knowledge"]["available"] is True
    assert cg["knowledge"]["enablable"] is True
    assert cg["knowledge"]["enabled_by_default"] is False
    assert cg["task"]["available"] is True
    assert cg["task"]["enablable"] is True
    assert cg["sdd"]["not_implemented"] is True
    assert cg["sdd"]["support_state"] == "not_supported_yet"
    assert cg["tdd"]["not_implemented"] is True
    assert cg["tdd"]["fail_closed_if_enabled"] is True


def test_project_capability_guidance_filters_enable_actions_when_enabled():
    comps = resolve_component_runtime(
        {
            "knowledge": {"enabled": True},
            "task": {"enabled": False},
            "sdd": {"enabled": False},
            "tdd": {"enabled": False},
        }
    )
    projected = project_capability_guidance(
        components=comps["components"],
        capability_profile=comps["capability_profile"],
    )
    codes = {a["code"] for a in projected["next_actions"]}
    assert "ENABLE_KNOWLEDGE_CONFIG_PREVIEW" not in codes
    assert "ENABLE_TASK_CONFIG_PREVIEW" in codes
    assert projected["knowledge"]["enabled"] is True
    assert projected["task"]["enabled"] is False


def test_disabled_capabilities_do_not_fail_product_ready():
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
    assert "knowledge_provider_unavailable" not in probe.blocked_reasons
    assert "task_provider_unavailable" not in probe.blocked_reasons


def test_enabled_capability_failure_produces_next_actions():
    from vibe_control.product_readiness import readiness_next_actions

    comps = resolve_component_runtime(
        {
            "knowledge": {"enabled": True},
            "task": {"enabled": False},
            "sdd": {"enabled": False},
            "tdd": {"enabled": False},
        }
    )["components"]
    probe = build_probe_from_parts(
        knowledge_available=False,
        knowledge_target_ok=False,
        sync_state="unavailable",
        task_available=False,
        task_mode="unavailable",
        task_readable=False,
        task_cache_current=True,
        components=comps,
    )
    assert probe.product_ready is False
    assert "knowledge_provider_unavailable" in probe.blocked_reasons
    actions = readiness_next_actions(probe)
    codes = {a.get("code") for a in actions if isinstance(a, dict)}
    assert "KNOWLEDGE_PROVIDER_DIAGNOSIS" in codes
    assert all(a.get("mutation") is False for a in actions if isinstance(a, dict))


def test_doctor_exposes_capability_guidance_without_failing_readiness(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)
    _write_repo(tmp_path)
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

    monkeypatch.setattr("vibe_control.cli.NotebookLMProvider", FakeNLM)
    monkeypatch.setattr("vibe_control.cli.BeadsProvider", FakeBeads)

    code = main(["doctor", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    data = payload["data"]
    cg = data["capability_guidance"]
    assert cg["default_disabled"] is True
    assert cg["engine_readiness_separate"] is True
    assert cg["disabled_do_not_fail_product_ready"] is True
    assert cg["knowledge"]["enablable"] is True
    assert cg["sdd"]["not_implemented"] is True
    assert data["mutation"] is False
    assert data["auto_enable"] is False
    assert any(
        a.get("code") == "ENABLE_KNOWLEDGE_CONFIG_PREVIEW" for a in payload["next_actions"]
    )
    blob = json.dumps(payload).lower()
    for marker in SENSITIVE_MARKERS:
        assert marker.lower() not in blob


def test_progress_and_brief_expose_concise_capability_guidance(tmp_path):
    status = _default_disabled_status()
    selection = _next_selection()
    progress = build_progress(
        repo_root=tmp_path,
        integration_status=status,
        next_selection=selection,
        closeout_data={
            "closeout_complete": True,
            "implementation_ready": True,
            "provider_sync_required": False,
            "sync_state": "synced",
            "provider_ask_clean": True,
            "task_cache_current": True,
            "blocked_reasons": [],
        },
        observed_head="abc",
        git_status_short="",
        recorded_baseline_commit="abc",
    )
    pdata = progress["data"]
    assert pdata["mutation"] is False
    cg = pdata["capability_guidance"]
    assert cg["engine_readiness_separate"] is True
    assert cg["default_disabled"] is True
    assert cg["knowledge"]["enabled"] is False
    assert cg["sdd"]["not_implemented"] is True
    codes = {a["code"] for a in pdata["next_actions"]}
    assert "IMPLEMENTATION_PROMPT" in codes or pdata["safe_next_action"]["code"] == "IMPLEMENTATION_PROMPT"
    assert "ENABLE_KNOWLEDGE_CONFIG_PREVIEW" in codes
    # Progress is not the full implementation prompt.
    assert "accepted_scope" not in pdata
    assert "Implement:" not in json.dumps(pdata)

    brief = build_brief(
        repo_root=tmp_path,
        integration_status=status,
        next_selection=selection,
        closeout_data={
            "closeout_complete": True,
            "implementation_ready": True,
            "provider_sync_required": False,
            "sync_state": "synced",
            "provider_ask_clean": True,
            "task_cache_current": True,
            "blocked_reasons": [],
        },
        observed_head="abc",
        git_status_short="",
        recorded_baseline_commit="abc",
    )
    bdata = brief["data"]
    assert bdata["mutation"] is False
    assert bdata["capability_guidance"]["engine_readiness_separate"] is True
    assert bdata["capability_guidance"].get("concise") is True
    assert bdata["capability_guidance"].get("next_actions") == []
    assert any("Capability Profile" in c or "capability" in c.lower() for c in bdata["constraints"])
    assert "Implement:" not in bdata["summary"]


def test_describe_projection_only_includes_capability_guidance(tmp_path):
    status = _default_disabled_status()
    progress = build_progress(
        repo_root=tmp_path,
        integration_status=status,
        next_selection=_next_selection(None),
        closeout_data={
            "closeout_complete": True,
            "implementation_ready": False,
            "provider_sync_required": False,
            "sync_state": "synced",
            "provider_ask_clean": True,
            "task_cache_current": True,
            "blocked_reasons": [],
        },
        observed_head="abc",
        git_status_short="",
        recorded_baseline_commit="abc",
    )
    describe = build_describe(repo_root=tmp_path, progress_envelope=progress)
    data = describe["data"]
    assert data["mutation"] is False
    assert data["source_of_truth"] == "engine"
    assert data["facts_embedded"] is False
    assert data["capability_guidance"]["recomputes_readiness"] is False
    assert data["projected"]["capability_guidance"]["default_disabled"] is True
    assert "capability_profile" in data["authority"]
    assert "separate" in data["authority"]["capability_profile"].lower()
    # Projection identity: readiness fields match progress, not recomputed.
    assert data["projected"]["product_ready"] is progress["data"]["product_ready"]
    assert data["projected"]["capability_profile"] == progress["data"]["capability_profile"]


def test_gateway_delegates_capability_guidance_without_recompute(tmp_path):
    status = _default_disabled_status()
    progress = build_progress(
        repo_root=tmp_path,
        integration_status=status,
        next_selection=_next_selection(),
        closeout_data={
            "closeout_complete": True,
            "implementation_ready": True,
            "provider_sync_required": False,
            "sync_state": "synced",
            "provider_ask_clean": True,
            "task_cache_current": True,
            "blocked_reasons": [],
        },
        observed_head="abc",
        git_status_short="",
        recorded_baseline_commit="abc",
    )

    def progress_fn(*, repo_root):
        return progress

    result = route_gateway(
        intent="status",
        repo_root=tmp_path,
        delegates={"progress": progress_fn},
    )
    data = result["data"]
    assert data["source_of_truth"] == "engine"
    assert data["gateway"] is True
    assert data["mutation"] is False
    engine = data["engine_payload"]
    assert engine["data"]["capability_guidance"]["engine_readiness_separate"] is True
    assert engine["data"]["capability_guidance"] is progress["data"]["capability_guidance"]
    # Gateway must not invent a second readiness engine.
    assert "product_ready" not in data or data.get("product_ready") is None or (
        data.get("product_ready") == engine["data"]["product_ready"]
    )
    assert data.get("recomputes_readiness") is not True


def test_readonly_surfaces_do_not_mutate_repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_repo(tmp_path)
    before = {p.as_posix(): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    status = _default_disabled_status()
    selection = _next_selection()
    progress = build_progress(
        repo_root=tmp_path,
        integration_status=status,
        next_selection=selection,
        closeout_data={
            "closeout_complete": True,
            "implementation_ready": True,
            "provider_sync_required": False,
            "sync_state": "synced",
            "provider_ask_clean": True,
            "task_cache_current": True,
            "blocked_reasons": [],
        },
        observed_head="abc",
        git_status_short="",
        recorded_baseline_commit="abc",
    )
    build_brief(
        repo_root=tmp_path,
        integration_status=status,
        next_selection=selection,
        closeout_data={
            "closeout_complete": True,
            "implementation_ready": True,
            "provider_sync_required": False,
            "sync_state": "synced",
            "provider_ask_clean": True,
            "task_cache_current": True,
            "blocked_reasons": [],
        },
        observed_head="abc",
        git_status_short="",
        recorded_baseline_commit="abc",
    )
    build_describe(repo_root=tmp_path, progress_envelope=progress)
    route_gateway(
        intent="status",
        repo_root=tmp_path,
        delegates={"progress": lambda *, repo_root: progress},
    )
    build_component_config_guidance()
    after = {p.as_posix(): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert after == before


def test_redaction_no_raw_provider_refs_in_guidance_blob():
    guidance = build_component_config_guidance()
    projected = project_capability_guidance()
    blob = json.dumps({"g": guidance, "p": projected}).lower()
    for marker in SENSITIVE_MARKERS:
        assert marker.lower() not in blob
    assert "nlm login" not in blob
    assert "bd init" in blob or "enable" in blob  # safe command hints ok


def test_roadmap_marks_doctor_gateway_completed_and_promotes_recovery():
    from vibe_control.task.roadmap_state import load_roadmap_state

    state = load_roadmap_state(Path.cwd())
    assert state["next_actionable_task"] is None
    by = {a["ssot_anchor"]: a for a in state["anchors"]}
    assert by["roadmap.vibe_capability_profile_doctor_gateway_guidance"]["actionable"] is False
    assert by["roadmap.vibe_capability_profile_doctor_gateway_guidance"]["phase_state"] == "completed"
    assert by["roadmap.vibe_operation_recovery_design"]["actionable"] is False
    assert by["roadmap.vibe_operation_recovery_design"]["phase_state"] == "completed"
