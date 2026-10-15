"""Component Runtime Core Baseline Slice 1 — config resolver + product_ready gating."""

from __future__ import annotations

import json

from helpers import minimal_config_dict, write_control_yaml, write_doc
from vibe_control.cli import main
from vibe_control.components import resolve_component_runtime
from vibe_control.integration import build_integration_status
from vibe_control.knowledge.notebooklm_provider import NotebookLMProvider, NotebookLMStatus
from vibe_control.product_readiness import build_probe_from_parts, evaluate_product_readiness
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


def _green_probe(**overrides):
    base = dict(
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
    )
    base.update(overrides)
    return build_probe_from_parts(**base)


def _write_repo(tmp_path, *, components=None):
    raw = {
        **minimal_config_dict(enable_knowledge=False, enable_task=False),
        "project": {"id": "vibe-control", "name": "Vibe"},
    }
    if components is not None:
        raw["components"] = components
    write_control_yaml(tmp_path, raw)
    write_doc(tmp_path, "docs/project/vibe-control-spec.md", "# Spec\n")
    write_doc(
        tmp_path,
        "docs/project/spec-registry.yml",
        "entries: []\n",
    )


def test_no_components_config_ok_true_and_defaults():
    result = resolve_component_runtime(None)
    assert result["config_ok"] is True
    assert result["blocked_reasons"] == []
    comps = result["components"]
    assert set(comps) == {"knowledge", "task", "hetu", "sdd", "tdd"}
    assert comps["knowledge"]["support_state"] == "supported"
    assert comps["knowledge"]["enabled"] is False
    assert comps["knowledge"]["readiness_role"] == "optional_when_disabled"
    assert comps["task"]["enabled"] is False
    assert comps["hetu"]["support_state"] == "supported"
    assert comps["hetu"]["enabled"] is False
    assert comps["hetu"]["readiness_role"] == "optional_when_disabled"
    assert comps["sdd"]["support_state"] == "not_supported_yet"
    assert comps["sdd"]["enabled"] is False
    assert comps["tdd"]["enabled"] is False


def test_knowledge_disabled_is_valid_default_profile():
    result = resolve_component_runtime({"knowledge": {"enabled": False}})
    assert result["config_ok"] is True
    assert result["blocked_reasons"] == []
    assert result["components"]["knowledge"]["enabled"] is False


def test_task_disabled_is_valid_default_profile():
    result = resolve_component_runtime({"task": {"enabled": False}})
    assert result["config_ok"] is True
    assert result["blocked_reasons"] == []
    assert result["components"]["task"]["enabled"] is False


def test_sdd_enabled_unsupported_component_enabled():
    result = resolve_component_runtime({"sdd": {"enabled": True}})
    assert result["config_ok"] is False
    assert "unsupported_component_enabled" in result["blocked_reasons"]
    assert "provider_unavailable" not in " ".join(result["blocked_reasons"])


def test_tdd_enabled_unsupported_component_enabled():
    result = resolve_component_runtime({"tdd": {"enabled": True}})
    assert result["config_ok"] is False
    assert "unsupported_component_enabled" in result["blocked_reasons"]


def test_sdd_and_tdd_explicitly_disabled_still_config_ok():
    result = resolve_component_runtime(
        {"sdd": {"enabled": False}, "tdd": {"enabled": False}}
    )
    assert result["config_ok"] is True
    assert result["blocked_reasons"] == []
    assert result["components"]["sdd"]["enabled"] is False
    assert result["components"]["tdd"]["enabled"] is False


def test_unknown_component_enabled_fail_closed():
    result = resolve_component_runtime({"widget": {"enabled": True}})
    assert result["config_ok"] is False
    assert "unknown_component_configured" in result["blocked_reasons"]


def test_unknown_component_disabled_fail_closed():
    result = resolve_component_runtime({"widget": {"enabled": False}})
    assert result["config_ok"] is False
    assert "unknown_component_configured" in result["blocked_reasons"]


def test_top_level_knowledge_tasks_specs_are_not_lifecycle_gates():
    # Resolver only reads components.*; top-level sections must not be passed in.
    result = resolve_component_runtime(None)
    assert result["config_ok"] is True
    # Explicitly ensure catalog ids are not confused with nested names
    result2 = resolve_component_runtime({})
    assert result2["config_ok"] is True
    assert "knowledge" in result2["components"]


def test_product_ready_requires_config_ok(tmp_path, monkeypatch):
    monkeypatch.setenv("VIBE_SKILLS_ROOT", str(tmp_path / "skills"))
    _write_repo(tmp_path, components={"sdd": {"enabled": True}})
    probe = evaluate_product_readiness(
        repo_root=tmp_path,
        knowledge={
            "available": True,
            "target_ok": True,
            "sync_state": "synced",
            "required_updates_count": 0,
            "candidate_count": 0,
            "orphan_managed_count": 0,
        },
        task={
            "available": True,
            "mode": "readonly",
            "readable": True,
            "ready_queue_available": True,
        },
        task_cache={
            "task_cache_current": True,
            "reconcile_counts": {
                "matched": 1,
                "missing": 0,
                "stale": 0,
                "duplicate": 0,
                "conflict": 0,
                "unmanaged": 0,
            },
            "apply_plan_counts": {"create": 0, "update": 0, "skip": 0, "blocked": 0},
        },
        probe=False,
        probe_task_cache_state=False,
    )
    assert probe.config_ok is False
    assert probe.product_ready is False
    assert "unsupported_component_enabled" in probe.blocked_reasons
    assert not any("unavailable" in r for r in probe.blocked_reasons)


def test_no_components_skips_provider_gates_when_unavailable(tmp_path, monkeypatch):
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
    assert probe.blocked_reasons == []
    assert probe.components["knowledge"]["enabled"] is False


def test_integration_status_exposes_config_ok_and_components(tmp_path, monkeypatch):
    monkeypatch.setenv("VIBE_SKILLS_ROOT", str(tmp_path / "skills"))
    _write_repo(tmp_path, components={"tdd": {"enabled": True}})
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
    assert "config_ok" in data
    assert "components" in data
    assert data["config_ok"] is False
    assert data["product_ready"] is False
    assert "unsupported_component_enabled" in data["blocked_reasons"]
    assert set(data["components"]) == {"knowledge", "task", "hetu", "sdd", "tdd"}
    assert not any("unavailable" in r for r in data["blocked_reasons"])


def test_cli_integration_status_includes_component_fields(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("VIBE_SKILLS_ROOT", str(tmp_path / "skills"))
    _write_repo(tmp_path, components=None)
    monkeypatch.chdir(tmp_path)

    def fake_status(**kwargs):
        return {
            "project_id": "vibe-control",
            "notebooklm": {"installed": False, "safe_to_sync": False},
            "beads": {"installed": False},
            "skills": {"installed": False, "skills": [], "source_exists": True},
            "repo": {
                "project_root": str(tmp_path),
                "config_found": True,
                "fallback_ready": True,
                "fallback_is_product_ready": False,
            },
            "product_ready": True,
            "blocked_reasons": [],
            "config_ok": True,
            "components": {
                "knowledge": {"support_state": "supported", "enabled": False},
                "task": {"support_state": "supported", "enabled": False},
                "hetu": {"support_state": "supported", "enabled": False},
                "sdd": {"support_state": "not_supported_yet", "enabled": False},
                "tdd": {"support_state": "not_supported_yet", "enabled": False},
            },
            "knowledge_provider": {
                "available": True,
                "target_ok": True,
                "sync_state": "synced",
                "provider_ask_clean": True,
                "ask_hygiene": {},
            },
            "task_provider": {
                "available": True,
                "mode": "readonly",
                "readable": True,
                "ready_queue_available": True,
            },
            "task_cache_mode": "local_embedded_ephemeral",
            "task_cache_current": True,
            "task_cache_action_required": False,
            "safe_task_convergence_allowed": False,
            "task_cache_reset_required": False,
            "task_cache": {},
            "provider_probe": {"evidence_hash": "x", "probed": True},
            "closeout_state": "no_ssot_change_product_ready",
            "closeout_complete": True,
            "provider_sync_required": False,
            "chatgpt_project_sources": {"product_closeout_gate": False},
            "warnings": [],
            "next_actions": [],
        }

    monkeypatch.setattr("vibe_control.integration.build_integration_status", fake_status)
    code = main(["integration", "status", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["data"]["config_ok"] is True
    assert "components" in payload["data"]
