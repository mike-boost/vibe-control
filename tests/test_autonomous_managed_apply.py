"""Option A autonomous managed Beads apply policy tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from helpers import minimal_config_dict, write_actionable_roadmap_state, write_control_yaml, write_doc
from vibe_control.components import resolve_component_runtime
from vibe_control.product_readiness import build_probe_from_parts
from vibe_control.task.apply_cli import run_task_apply
from vibe_control.task.apply_models import ApplyOperation, ApplyPlan
from vibe_control.task.apply_plan import build_apply_plan, compute_plan_binding_hash
from vibe_control.task.autonomy import (
    evaluate_autonomous_managed_eligibility,
    evaluate_managed_apply_safety,
)
from vibe_control.task.beads_apply import (
    assert_no_forbidden_mutation_argv,
    build_bd_create_argv,
    build_bd_update_argv,
    execute_beads_apply_guarded,
)
from vibe_control.task.projection import (
    project_actionable_expected_tasks,
    project_completed_expected_tasks,
)
from vibe_control.task.provider import FakeTaskProvider
from vibe_control.task.reconcile import reconcile_readonly


def _repo(tmp_path: Path) -> Path:
    write_control_yaml(
        tmp_path,
        {**minimal_config_dict(), "project": {"id": "vibe-control", "name": "Vibe"}},
    )
    write_doc(tmp_path, "docs/project/vibe-control-spec.md", "# Spec\nPhase 11B\nPhase 12\n")
    write_actionable_roadmap_state(tmp_path)
    return tmp_path


def _safe_plan(tmp_path: Path) -> ApplyPlan:
    root = _repo(tmp_path)
    expected = project_actionable_expected_tasks(project_id="vibe-control", repo_root=root)
    completed = project_completed_expected_tasks(project_id="vibe-control", repo_root=root)
    report = reconcile_readonly(project_id="vibe-control", expected=expected, provider_tasks=[])
    return build_apply_plan(report, expected=expected, completed_expected=completed)


def test_safe_plan_recognized_as_autonomous_managed(tmp_path):
    plan = _safe_plan(tmp_path)
    safety = evaluate_managed_apply_safety(plan)
    assert safety["ok"] is True
    assert safety["recognized_as_autonomous_managed"] is True
    assert safety["create_count"] >= 1
    assert not any(
        o.ssot_anchor in {"roadmap.phase11a", "roadmap.phase11b"} and o.executable
        for o in plan.operations
        if o.op_type == "create_managed"
    )


def test_completed_shells_non_executable(tmp_path):
    plan = _safe_plan(tmp_path)
    creates = [o for o in plan.operations if o.op_type == "create_managed" and o.executable]
    assert not any(o.ssot_anchor == "roadmap.phase11a" for o in creates)
    assert not any(o.ssot_anchor == "roadmap.phase11b" for o in creates)
    assert any(o.op_type == "skip_completed" for o in plan.operations)


def test_product_ready_false_blocks_real_beads_apply(tmp_path, monkeypatch):
    monkeypatch.setenv("VIBE_BEADS_LIVE_APPLY", "1")
    root = _repo(tmp_path)
    probe = build_probe_from_parts(
        knowledge_available=True,
        knowledge_target_ok=True,
        sync_state="synced",
        task_available=True,
        task_mode="readonly",
        task_readable=True,
        ready_queue_available=True,
    )
    # Force not product_ready via unsynced probe instead
    probe = build_probe_from_parts(
        knowledge_available=False,
        knowledge_target_ok=False,
        sync_state="unavailable",
        task_available=True,
        task_mode="readonly",
        task_readable=True,
        components=resolve_component_runtime(
            {"knowledge": {"enabled": True}, "task": {"enabled": True}}
        )["components"],
    )
    assert probe.product_ready is False
    env = run_task_apply(
        repo_root=root,
        mode="apply",
        provider_name="beads",
        provider=FakeTaskProvider([]),
        strict_providers=True,
        knowledge_probe=probe,
        beads_confirm=True,
        autonomous_managed=True,
        beads_runner=lambda argv: {"returncode": 0, "provider_task_id": "bd-x"},
    )
    assert env["mode"] == "blocked"
    assert env["mutation"] is False
    assert env["error"]["code"] in {"KNOWLEDGE_PROVIDER_NOT_READY", "PRODUCT_NOT_READY"}


def test_stale_plan_binding_blocks_real_beads_apply(tmp_path, monkeypatch):
    monkeypatch.setenv("VIBE_BEADS_LIVE_APPLY", "1")
    root = _repo(tmp_path)
    expected = project_actionable_expected_tasks(project_id="vibe-control", repo_root=root)
    probe = build_probe_from_parts(
        knowledge_available=True,
        knowledge_target_ok=True,
        sync_state="synced",
        task_available=True,
        task_mode="readonly",
        task_readable=True,
        ready_queue_available=True,
    )
    # Ensure product_ready true
    assert probe.product_ready is True
    env = run_task_apply(
        repo_root=root,
        mode="apply",
        provider_name="beads",
        provider=FakeTaskProvider([]),
        strict_providers=True,
        knowledge_probe=probe,
        beads_confirm=True,
        autonomous_managed=True,
        expect_plan_binding="sha256:" + "0" * 64,
        beads_runner=lambda argv: {"returncode": 0, "provider_task_id": "bd-x"},
    )
    assert env["mode"] == "blocked"
    assert env["mutation"] is False
    assert env["error"]["code"] == "STALE_APPLY_PLAN"
    # binding differs from current
    assert compute_plan_binding_hash(expected) != "sha256:" + "0" * 64


def test_unsafe_executable_blocks_eligibility():
    plan = ApplyPlan(
        operations=[
            ApplyOperation(
                op_type="skip_conflict",
                managed_key="sha256:" + "a" * 64,
                ssot_id="vibe_control_spec",
                ssot_path="docs/project/vibe-control-spec.md",
                ssot_anchor="x",
                task_kind="t",
                title="conflict",
                reason="conflict",
                executable=True,
            )
        ]
    )
    safety = evaluate_managed_apply_safety(plan)
    assert safety["ok"] is False
    elig = evaluate_autonomous_managed_eligibility(
        plan,
        product_ready=True,
        task_readable=True,
        beads_confirm=True,
        env_ok=True,
        autonomous_managed=True,
    )
    assert elig["eligible"] is False
    assert "safe_managed_plan" in elig["missing"]


def test_autonomous_managed_live_path_with_fake_runner(tmp_path, monkeypatch):
    monkeypatch.setenv("VIBE_BEADS_LIVE_APPLY", "1")
    root = _repo(tmp_path)
    probe = build_probe_from_parts(
        knowledge_available=True,
        knowledge_target_ok=True,
        sync_state="synced",
        task_available=True,
        task_mode="readonly",
        task_readable=True,
        ready_queue_available=True,
    )
    assert probe.product_ready is True
    recorded: list[list[str]] = []

    def runner(argv: list[str]):
        recorded.append(list(argv))
        return {"returncode": 0, "provider_task_id": f"bd-gen-{len(recorded)}"}

    env = run_task_apply(
        repo_root=root,
        mode="apply",
        provider_name="beads",
        provider=FakeTaskProvider([]),
        strict_providers=True,
        knowledge_probe=probe,
        beads_confirm=True,
        autonomous_managed=True,
        beads_runner=runner,
    )
    assert env["ok"] is True
    assert env["mode"] == "applied"
    assert env["mutation"] is True
    assert recorded
    assert all(r[1] == "create" for r in recorded)
    assert all("--metadata" in r for r in recorded)
    assert all("delete" not in r and "close" not in r and "--claim" not in r for r in recorded)
    live = env["data"]["live_results"]
    assert len(live) == len(recorded)
    assert all(x.get("provider_task_id") for x in live)


def test_dual_gate_without_autonomous_managed_blocks(tmp_path, monkeypatch):
    monkeypatch.setenv("VIBE_BEADS_LIVE_APPLY", "1")
    root = _repo(tmp_path)
    probe = build_probe_from_parts(
        knowledge_available=True,
        knowledge_target_ok=True,
        sync_state="synced",
        task_available=True,
        task_mode="readonly",
        task_readable=True,
        ready_queue_available=True,
    )
    env = run_task_apply(
        repo_root=root,
        mode="apply",
        provider_name="beads",
        provider=FakeTaskProvider([]),
        strict_providers=True,
        knowledge_probe=probe,
        beads_confirm=True,
        autonomous_managed=False,
        beads_runner=lambda argv: {"returncode": 0, "provider_task_id": "bd-x"},
    )
    assert env["mode"] == "blocked"
    assert env["mutation"] is False
    assert "--autonomous-managed" in env["error"]["message"]


def test_provider_id_binding_only_not_identity(tmp_path):
    root = _repo(tmp_path)
    tasks = project_actionable_expected_tasks(project_id="vibe-control", repo_root=root)
    assert all(t.managed_key.startswith("sha256:") for t in tasks)
    assert all(not t.managed_key.startswith("bd-") for t in tasks)


def test_bd_argv_never_builds_delete_close_claim():
    op = ApplyOperation(
        op_type="create_managed",
        managed_key="sha256:" + "a" * 64,
        project_id="vibe-control",
        ssot_id="vibe_control_spec",
        ssot_path="docs/project/vibe-control-spec.md",
        ssot_anchor="roadmap.phase11b.live_apply",
        task_kind="implementation_task",
        title="t",
        reason="missing",
        executable=True,
        description="d",
    )
    create = build_bd_create_argv(op, silent=True)
    assert_no_forbidden_mutation_argv(create)
    assert "--metadata" in create
    assert "--spec-id" in create
    assert "--silent" in create
    upd = ApplyOperation(
        op_type="update_managed",
        managed_key=op.managed_key,
        project_id=op.project_id,
        ssot_id=op.ssot_id,
        ssot_path=op.ssot_path,
        ssot_anchor=op.ssot_anchor,
        task_kind=op.task_kind,
        title="t2",
        reason="stale",
        executable=True,
        description="d2",
        provider_task_id="bd-1",
    )
    update = build_bd_update_argv(upd)
    assert_no_forbidden_mutation_argv(update)
    for argv in (create, update):
        assert "delete" not in argv
        assert "close" not in argv
        assert "--claim" not in argv


def test_unsafe_next_actions_not_ad_hoc_user_approval(tmp_path):
    from vibe_control.task.autonomy import autonomy_next_actions

    plan = _safe_plan(tmp_path)
    # inject skip_conflict for next_actions coverage
    plan.operations.append(
        ApplyOperation(
            op_type="skip_conflict",
            managed_key="sha256:" + "b" * 64,
            ssot_id="vibe_control_spec",
            ssot_path="docs/project/vibe-control-spec.md",
            ssot_anchor="x",
            task_kind="t",
            title="c",
            reason="conflict",
            executable=False,
        )
    )
    actions = autonomy_next_actions(plan, provider_name="beads")
    codes = {a.get("code") for a in actions}
    assert "REPAIR_PLAN_REQUIRED" in codes
    blob = str(actions).lower()
    assert "please confirm" not in blob
    assert "ask the user" not in blob


def test_default_gates_do_not_live_mutate(tmp_path, monkeypatch):
    monkeypatch.delenv("VIBE_BEADS_LIVE_APPLY", raising=False)
    root = _repo(tmp_path)
    probe = build_probe_from_parts(
        knowledge_available=True,
        knowledge_target_ok=True,
        sync_state="synced",
        task_available=True,
        task_mode="readonly",
        task_readable=True,
        ready_queue_available=True,
    )
    called = []
    env = run_task_apply(
        repo_root=root,
        mode="apply",
        provider_name="beads",
        provider=FakeTaskProvider([]),
        strict_providers=True,
        knowledge_probe=probe,
        beads_confirm=False,
        autonomous_managed=False,
        beads_runner=lambda argv: called.append(argv) or {"returncode": 0},
    )
    assert env["mutation"] is False
    assert called == []
    assert env["mode"] == "blocked"
