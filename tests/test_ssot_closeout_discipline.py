"""SSOT closeout discipline — commit alone must not greenlight implementation."""

from __future__ import annotations

from helpers import minimal_config_dict, write_control_yaml, write_doc
from vibe_control.closeout import evaluate_ssot_closeout
from vibe_control.components import resolve_component_runtime
from vibe_control.implementation.prompt import build_implementation_prompt
from vibe_control.integration import build_integration_status
from vibe_control.knowledge.notebooklm_provider import NotebookLMProvider, NotebookLMStatus
from vibe_control.product_readiness import build_probe_from_parts
from vibe_control.task.beads_provider import BeadsProvider, BeadsStatus


def _write_minimal_repo(tmp_path, *, knowledge_enabled: bool = True, task_enabled: bool = True):
    write_control_yaml(
        tmp_path,
        {
            **minimal_config_dict(),
            "project": {"id": "vibe-control", "name": "Vibe"},
            "components": {
                "knowledge": {"enabled": knowledge_enabled},
                "task": {"enabled": task_enabled},
                "sdd": {"enabled": False},
                "tdd": {"enabled": False},
            },
        },
    )
    write_doc(tmp_path, "docs/project/vibe-control-spec.md", "# Spec\n")
    write_doc(
        tmp_path,
        "docs/project/vibe-control-roadmap-state.md",
        """# Roadmap State

```yaml
roadmap_state_version: 1
next_actionable_task: roadmap.component_runtime_core_baseline
no_actionable_next_task: false
rules:
  do_not_invent_phase13: true
anchors:
  - ssot_anchor: roadmap.phase12
    task_kind: implementation_phase
    title: "Phase 12 — Implementation Prompt Generator"
    phase_state: completed
    actionable: false
  - ssot_anchor: roadmap.component_runtime_core_baseline
    task_kind: implementation_task
    title: "Component Runtime Core Baseline Slice 1"
    phase_state: accepted
    actionable: true
```
""",
    )


class _FakeNLM(NotebookLMProvider):
    def which(self):
        return "/tmp/fake-notebooklm"

    def status(self, *, probe_auth: bool = False) -> NotebookLMStatus:
        return NotebookLMStatus(
            installed=True,
            executable="/tmp/fake-notebooklm",
            version="fake",
            message="ok",
        )


class _FakeBeads(BeadsProvider):
    def which(self):
        return "/tmp/fake-bd"

    def status(self) -> BeadsStatus:
        return BeadsStatus(
            installed=True,
            executable="/tmp/fake-bd",
            version="fake",
            message="ok",
            init_safe_mode="skip_agents",
        )

    def init_preview(self) -> BeadsStatus:
        return self.status()


def test_active_ssot_drift_cannot_claim_product_ready_closeout():
    result = evaluate_ssot_closeout(
        ssot_or_include_extra_changed=True,
        ssot_committed=True,
        knowledge_synced=False,
        provider_ask_clean=False,
        product_ready=False,
        task_available=True,
        task_readable=True,
    )
    assert result["closeout_complete"] is False
    assert result["product_ready_claim_allowed"] is False
    assert result["provider_sync_required"] is True
    assert result["closeout_state"] == "ssot_change_committed_sync_required"
    assert result["closeout_state"] != "waiting_owner_project_sources"
    assert "UPDATE_CHATGPT_PROJECT_SOURCES" not in [a["code"] for a in result["next_actions"]]

    probe = build_probe_from_parts(
        knowledge_available=True,
        knowledge_target_ok=True,
        sync_state="drift",
        required_updates_count=1,
        task_available=True,
        task_mode="readonly",
        task_readable=True,
        ready_queue_available=True,
        task_cache_current=True,
        components=resolve_component_runtime(
            {"knowledge": {"enabled": True}, "task": {"enabled": True}}
        )["components"],
    )
    assert probe.product_ready is False
    assert any("sync_state" in r for r in probe.blocked_reasons)


def test_integration_status_drift_blocks_via_provider_not_project_sources(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("VIBE_SKILLS_ROOT", str(tmp_path / "skills"))
    _write_minimal_repo(tmp_path)
    data = build_integration_status(
        repo_root=tmp_path,
        notebooklm=_FakeNLM(),
        beads=_FakeBeads(),
        probe_product=False,
        knowledge_parts={
            "available": True,
            "target_ok": True,
            "sync_state": "drift",
            "required_updates_count": 1,
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
    assert data["closeout_state"] == "ssot_change_committed_sync_required"
    assert data["closeout_state"] != "waiting_owner_project_sources"
    assert data["closeout_complete"] is False
    assert data["provider_sync_required"] is True
    assert data["product_ready"] is False
    assert any("drift" in r for r in data["blocked_reasons"])
    assert data["chatgpt_project_sources"]["product_closeout_gate"] is False
    assert "project_sources_handoff" not in data
    codes = [a["code"] for a in data["next_actions"]]
    assert "UPDATE_CHATGPT_PROJECT_SOURCES" not in codes
    assert codes[0] == "RUN_BOUNDED_KNOWLEDGE_SYNC"


def test_prompt_blocked_when_provider_sync_required(tmp_path):
    _write_minimal_repo(tmp_path)
    result = build_implementation_prompt(
        repo_root=tmp_path,
        task_selector="roadmap.component_runtime_core_baseline",
        product_ready=False,
        readiness_summary={
            "product_ready": False,
            "sync_state": "drift",
            "provider_ask_clean": False,
            "blocked_reasons": ["knowledge_sync_state=drift"],
        },
        knowledge_readiness={
            "sync_state": "drift",
            "provider_ask_clean": False,
            "available": True,
            "target_ok": True,
        },
        reconcile_counts={
            "matched": 0,
            "missing": 1,
            "stale": 0,
            "duplicate": 0,
            "conflict": 0,
            "unmanaged": 0,
        },
        apply_plan_counts={"create": 1, "update": 0, "skip": 0, "blocked": 0},
        provider_sync_required=True,
    )
    data = result["data"]
    assert data["task_identity"]["ssot_anchor"] == "roadmap.component_runtime_core_baseline"
    assert data["task_completed"] is False
    assert data["implementation_ready"] is False
    assert data["closeout_blocking"] is True
    assert "Implement:" not in data["prompt"].split("## Selected task anchor")[0]
    assert "DO NOT start implementation" in data["prompt"]
    assert "owner Project Sources handoff" not in data["prompt"]
    assert "UPDATE_CHATGPT_PROJECT_SOURCES" not in data["prompt"]
    assert "provider_sync_required" in result["warnings"]
    assert "implementation_not_ready" in result["warnings"]
    assert any(a.get("code") == "SSOT_CLOSEOUT_INCOMPLETE" for a in result["next_actions"])
    assert not any(
        a.get("code") in {"UPDATE_CHATGPT_PROJECT_SOURCES", "OWNER_PROJECT_SOURCES_THEN_BOUNDED_SYNC"}
        for a in result["next_actions"]
    )
    assert any(a.get("code") == "RUN_BOUNDED_KNOWLEDGE_SYNC" for a in result["next_actions"])
    assert "provider_task_id" not in data["task_identity"]
    assert "notebooklm://" not in data["prompt"].lower()
    assert "source_id" not in data["prompt"].lower()


def test_prompt_blocked_when_task_cache_not_current(tmp_path):
    _write_minimal_repo(tmp_path)
    result = build_implementation_prompt(
        repo_root=tmp_path,
        task_selector="roadmap.component_runtime_core_baseline",
        product_ready=True,
        readiness_summary={
            "product_ready": True,
            "sync_state": "synced",
            "provider_ask_clean": True,
            "blocked_reasons": [],
        },
        knowledge_readiness={
            "sync_state": "synced",
            "provider_ask_clean": True,
            "available": True,
            "target_ok": True,
        },
        reconcile_counts={
            "matched": 0,
            "missing": 1,
            "stale": 0,
            "duplicate": 0,
            "conflict": 0,
            "unmanaged": 0,
        },
        apply_plan_counts={"create": 1, "update": 0, "skip": 0, "blocked": 0},
        provider_sync_required=False,
    )
    data = result["data"]
    assert data["product_readiness"]["task_cache_current"] is False
    assert data["implementation_ready"] is False
    assert data["closeout_blocking"] is True
    assert "Implement:" not in data["prompt"].split("## Selected task anchor")[0]
    assert "task_cache_not_current" in result["warnings"]


def test_phase12_completed_still_do_not_restart(tmp_path):
    _write_minimal_repo(tmp_path)
    result = build_implementation_prompt(
        repo_root=tmp_path,
        task_selector="roadmap.phase12",
        product_ready=True,
        readiness_summary={
            "product_ready": True,
            "sync_state": "synced",
            "provider_ask_clean": True,
            "blocked_reasons": [],
        },
        knowledge_readiness={
            "sync_state": "synced",
            "provider_ask_clean": True,
            "available": True,
            "target_ok": True,
        },
        reconcile_counts={
            "matched": 0,
            "missing": 0,
            "stale": 0,
            "duplicate": 0,
            "conflict": 0,
            "unmanaged": 0,
        },
        apply_plan_counts={"create": 0, "update": 0, "skip": 1, "blocked": 0},
        provider_sync_required=False,
    )
    data = result["data"]
    assert data["task_completed"] is True
    assert data["do_not_restart"] is True
    assert data["implementation_ready"] is False
    assert "task_completed_do_not_restart" in result["warnings"]
    assert "WARNING: selected task is completed" in data["prompt"]
    assert data["next_actionable_selection"]["next_actionable_task"] == (
        "roadmap.component_runtime_core_baseline"
    )


def test_crcb_remains_next_but_not_greenlit_while_closeout_incomplete(tmp_path):
    _write_minimal_repo(tmp_path)
    result = build_implementation_prompt(
        repo_root=tmp_path,
        task_selector="roadmap.component_runtime_core_baseline",
        product_ready=False,
        readiness_summary={
            "product_ready": False,
            "sync_state": "drift",
            "provider_ask_clean": True,
            "blocked_reasons": ["knowledge_sync_state=drift"],
        },
        knowledge_readiness={
            "sync_state": "drift",
            "provider_ask_clean": True,
            "available": True,
            "target_ok": True,
        },
        reconcile_counts={
            "matched": 0,
            "missing": 0,
            "stale": 0,
            "duplicate": 0,
            "conflict": 0,
            "unmanaged": 0,
        },
        apply_plan_counts={"create": 0, "update": 0, "skip": 0, "blocked": 0},
        provider_sync_required=True,
    )
    data = result["data"]
    assert data["no_actionable_next_task"] is False
    assert (
        data["next_actionable_selection"]["next_actionable_task"]
        == "roadmap.component_runtime_core_baseline"
    )
    assert data["implementation_ready"] is False
    assert data["closeout_blocking"] is True
    assert "owner Project Sources handoff" not in data["prompt"]
