"""design_only prompt/projection hygiene + disabled capability warning hygiene."""

from __future__ import annotations

from pathlib import Path

from helpers import minimal_config_dict, write_control_yaml, write_doc
from vibe_control.implementation.prompt import build_implementation_prompt
from vibe_control.task.projection import next_actionable_selection, project_all_expected_tasks
from vibe_control.task.roadmap_state import load_roadmap_state

RECOVERY = "roadmap.vibe_operation_recovery_design"


def _write_design_only_repo(tmp_path: Path, *, actionable: bool = True) -> Path:
    write_control_yaml(
        tmp_path,
        {
            **minimal_config_dict(),
            "project": {"id": "vibe-control", "name": "Vibe"},
            "components": {
                "knowledge": {"enabled": False},
                "task": {"enabled": False},
                "sdd": {"enabled": False},
                "tdd": {"enabled": False},
            },
        },
    )
    write_doc(tmp_path, "docs/project/vibe-control-spec.md", "# Spec\n")
    phase = "accepted" if actionable else "completed"
    act = "true" if actionable else "false"
    next_line = (
        f"next_actionable_task: {RECOVERY}\nno_actionable_next_task: false"
        if actionable
        else "next_actionable_task: null\nno_actionable_next_task: true"
    )
    write_doc(
        tmp_path,
        "docs/project/vibe-control-roadmap-state.md",
        f"""# Roadmap State

```yaml
roadmap_state_version: 1
{next_line}
rules:
  do_not_invent_phase13: true
anchors:
  - ssot_anchor: {RECOVERY}
    task_kind: implementation_task
    title: "Vibe Product Interface Slice 5 — operation recovery design"
    phase_state: {phase}
    actionable: {act}
    design_only: true
```
""",
    )
    return tmp_path


def test_roadmap_loader_projects_design_only_on_completed_recovery():
    state = load_roadmap_state(Path.cwd())
    by = {a["ssot_anchor"]: a for a in state["anchors"]}
    assert by[RECOVERY]["design_only"] is True
    assert by[RECOVERY]["actionable"] is False
    assert by[RECOVERY]["phase_state"] == "completed"
    assert state["next_actionable_task"] is None
    assert state["no_actionable_next_task"] is True
    assert by["roadmap.phase12"]["design_only"] is False


def test_expected_task_projection_includes_design_only_completed():
    tasks = project_all_expected_tasks(project_id="vibe-control", repo_root=Path.cwd())
    by = {t.ssot_anchor: t for t in tasks}
    assert by[RECOVERY].design_only is True
    assert by[RECOVERY].actionable is False
    assert by["roadmap.phase12"].design_only is False


def test_next_selection_is_empty_after_recovery_closeout():
    selection = next_actionable_selection(repo_root=Path.cwd())
    assert selection["no_actionable_next_task"] is True
    assert selection["next_actionable_task"] is None


def test_design_only_prompt_says_design_not_implement(tmp_path):
    root = _write_design_only_repo(tmp_path, actionable=True)
    result = build_implementation_prompt(
        repo_root=root,
        task_selector=RECOVERY,
        product_ready=True,
        readiness_summary={
            "product_ready": True,
            "sync_state": "synced",
            "provider_ask_clean": True,
            "blocked_reasons": [],
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
        task_cache={
            "task_cache_current": True,
            "task_cache_action_required": False,
            "safe_task_convergence_allowed": False,
            "task_cache_reset_required": False,
        },
    )
    assert result["ok"] is True
    assert result["mutation"] is False
    data = result["data"]
    assert data["design_only"] is True
    assert data["task_context"]["design_only"] is True
    assert data["implementation_ready"] is True
    prompt = data["prompt"]
    assert "Design / Evaluate:" in prompt
    assert "Implement:" not in prompt
    assert "design_only: True" in prompt
    assert "Do not implement S2" in prompt or "do not implement S2" in prompt.lower()
    assert "workflow engine" in prompt.lower()


def test_disabled_capability_raw_noise_not_prompt_blockers(tmp_path):
    """Raw knowledge/task drift must not look like blockers when capabilities disabled."""
    root = _write_design_only_repo(tmp_path, actionable=True)
    result = build_implementation_prompt(
        repo_root=root,
        task_selector=RECOVERY,
        product_ready=True,
        readiness_summary={
            "product_ready": True,
            "sync_state": "drift",
            "provider_ask_clean": False,
            "blocked_reasons": [],
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
            "conflict": 1,
            "unmanaged": 0,
        },
        apply_plan_counts={"create": 1, "update": 0, "skip": 0, "blocked": 0},
        task_cache={
            "task_cache_current": False,
            "task_cache_action_required": True,
            "safe_task_convergence_allowed": False,
            "task_cache_reset_required": True,
        },
        provider_sync_required=False,
    )
    assert result["ok"] is True
    data = result["data"]
    comps = (data.get("component_runtime") or {}).get("components") or {}
    assert (comps.get("knowledge") or {}).get("enabled") is False
    assert (comps.get("task") or {}).get("enabled") is False
    assert data["implementation_ready"] is True
    warnings = set(result.get("warnings") or [])
    assert "task_cache_not_current" not in warnings
    assert "ask_hygiene_not_clean" not in warnings
    assert "task_reconcile_mismatch" not in warnings
    assert not any(w.startswith("knowledge_unsynced:") for w in warnings)
    assert "Implement:" not in data["prompt"]
    assert "Design / Evaluate:" in data["prompt"]


def test_completed_recovery_prompt_do_not_restart():
    result = build_implementation_prompt(
        repo_root=Path.cwd(),
        task_selector=RECOVERY,
        product_ready=True,
        readiness_summary={
            "product_ready": True,
            "sync_state": "synced",
            "provider_ask_clean": True,
            "blocked_reasons": [],
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
        task_cache={
            "task_cache_current": True,
            "task_cache_action_required": False,
            "safe_task_convergence_allowed": False,
            "task_cache_reset_required": False,
        },
    )
    assert result["ok"] is True
    data = result["data"]
    assert data["task_completed"] is True
    assert data["do_not_restart"] is True
    assert data["implementation_ready"] is False
    assert data["design_only"] is True
    assert data["no_actionable_next_task"] is True
    assert "Implement:" not in data["prompt"]
    assert "WARNING: selected task is completed" in data["prompt"]
