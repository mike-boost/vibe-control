"""Status-aware expected-task projection from roadmap-state SSOT."""

from __future__ import annotations

from pathlib import Path

from helpers import write_actionable_roadmap_state, write_doc
from vibe_control.task.apply_engine import run_apply
from vibe_control.task.apply_plan import build_apply_plan
from vibe_control.task.projection import (
    next_actionable_selection,
    project_actionable_expected_tasks,
    project_completed_expected_tasks,
    project_expected_tasks,
    project_slice1_expected_tasks,
)
from vibe_control.task.provider import FakeTaskProvider
from vibe_control.task.reconcile import reconcile_readonly


def _repo_actionable(tmp_path: Path) -> Path:
    write_doc(
        tmp_path,
        "docs/project/vibe-control-spec.md",
        "# Spec\nPhase 11A complete\nPhase 11B baseline\nPhase 12\n",
    )
    write_actionable_roadmap_state(tmp_path)
    return tmp_path


def _repo_completed_only(tmp_path: Path) -> Path:
    write_doc(tmp_path, "docs/project/vibe-control-spec.md", "# Spec\n")
    write_doc(
        tmp_path,
        "docs/project/vibe-control-roadmap-state.md",
        """# Roadmap State

```yaml
roadmap_state_version: 1
next_actionable_task: null
no_actionable_next_task: true
anchors:
  - ssot_anchor: roadmap.phase11a
    task_kind: implementation_phase
    title: "Phase 11A"
    phase_state: completed
    actionable: false
  - ssot_anchor: roadmap.phase11b
    task_kind: implementation_phase
    title: "Phase 11B"
    phase_state: completed
    actionable: false
  - ssot_anchor: roadmap.phase12
    task_kind: implementation_phase
    title: "Phase 12"
    phase_state: completed
    actionable: false
```
""",
    )
    return tmp_path


def test_completed_phase11a_not_executable_create(tmp_path):
    root = _repo_actionable(tmp_path)
    actionable = project_actionable_expected_tasks(project_id="vibe-control", repo_root=root)
    completed = project_completed_expected_tasks(project_id="vibe-control", repo_root=root)
    assert all(t.ssot_anchor != "roadmap.phase11a" for t in actionable)
    assert any(t.ssot_anchor == "roadmap.phase11a" and not t.actionable for t in completed)
    report = reconcile_readonly(
        project_id="vibe-control",
        expected=actionable,
        provider_tasks=[],
    )
    plan = build_apply_plan(report, expected=actionable, completed_expected=completed)
    creates = [o for o in plan.operations if o.op_type == "create_managed"]
    assert not any(o.ssot_anchor == "roadmap.phase11a" for o in creates)
    assert all(o.executable for o in creates)
    skips = [o for o in plan.operations if o.op_type == "skip_completed"]
    assert any(o.ssot_anchor == "roadmap.phase11a" for o in skips)
    assert all(not o.executable for o in skips)


def test_historical_completed_reported_as_skip_or_backfill(tmp_path):
    root = _repo_actionable(tmp_path)
    completed = project_completed_expected_tasks(project_id="vibe-control", repo_root=root)
    actionable = project_actionable_expected_tasks(project_id="vibe-control", repo_root=root)
    report = reconcile_readonly(project_id="vibe-control", expected=actionable, provider_tasks=[])
    plan = build_apply_plan(report, expected=actionable, completed_expected=completed)
    kinds = {o.op_type for o in plan.operations}
    assert "skip_completed" in kinds
    assert "optional_backfill_completed" in kinds
    assert any(
        o.ssot_anchor == "roadmap.phase11b" and o.op_type == "skip_completed" for o in plan.operations
    )
    by = plan.counts_by_op_type
    assert by["skip_completed"] >= 2
    assert by["optional_backfill_completed"] >= 2
    assert by["create_managed"] == len(actionable)


def test_remaining_11b_is_concrete_actionable_tasks(tmp_path):
    root = _repo_actionable(tmp_path)
    actionable = project_actionable_expected_tasks(project_id="vibe-control", repo_root=root)
    anchors = {t.ssot_anchor for t in actionable}
    assert "roadmap.phase11b" not in anchors
    assert "roadmap.phase11b.live_apply" in anchors
    assert "roadmap.phase11b.post_create_verify" in anchors
    assert "roadmap.phase11b.update_path_validation" in anchors
    assert "roadmap.phase11b.provider_closeout" in anchors
    for t in actionable:
        assert t.actionable
        assert t.phase_state in {"actionable", "pending"}
        assert t.managed_key
        assert t.ssot_id == "vibe_control_spec"
        assert t.ssot_path == "docs/project/vibe-control-spec.md"


def test_phase12_completed_not_actionable_in_production_state(tmp_path):
    root = _repo_completed_only(tmp_path)
    actionable = project_actionable_expected_tasks(project_id="vibe-control", repo_root=root)
    assert all(t.ssot_anchor != "roadmap.phase12" for t in actionable)
    all_tasks = project_expected_tasks(project_id="vibe-control", repo_root=root)
    p12 = next(t for t in all_tasks if t.ssot_anchor == "roadmap.phase12")
    assert p12.phase_state == "completed"
    assert p12.actionable is False
    selection = next_actionable_selection(repo_root=root)
    assert selection["no_actionable_next_task"] is True
    assert selection["next_actionable_task"] is None


def test_phase12_pending_projected_as_actionable_when_state_says_so(tmp_path):
    root = _repo_actionable(tmp_path)
    actionable = project_actionable_expected_tasks(project_id="vibe-control", repo_root=root)
    p12 = [t for t in actionable if t.ssot_anchor == "roadmap.phase12"]
    assert len(p12) == 1
    assert p12[0].phase_state == "pending"
    assert p12[0].actionable is True


def test_slice1_alias_returns_actionable_only(tmp_path):
    root = _repo_actionable(tmp_path)
    alias = project_slice1_expected_tasks(project_id="vibe-control", repo_root=root)
    full = project_expected_tasks(project_id="vibe-control", repo_root=root)
    assert all(t.actionable for t in alias)
    assert len(alias) < len(full)
    assert "roadmap.phase11a" not in {t.ssot_anchor for t in alias}


def test_apply_dry_run_no_completed_executable(tmp_path):
    root = _repo_actionable(tmp_path)
    expected = project_actionable_expected_tasks(project_id="vibe-control", repo_root=root)
    completed = project_completed_expected_tasks(project_id="vibe-control", repo_root=root)
    result = run_apply(
        expected=expected,
        provider=FakeTaskProvider([]),
        mode="dry_run",
        project_id="vibe-control",
        provider_name="fake",
        completed_expected=completed,
    )
    creates = [o for o in result.plan.operations if o.op_type == "create_managed" and o.executable]
    assert creates
    assert not any(o.ssot_anchor in {"roadmap.phase11a", "roadmap.phase11b"} for o in creates)
    assert any(o.op_type == "skip_completed" for o in result.plan.operations)
    for op in creates:
        assert op.phase_state in {"actionable", "pending"}
        assert op.actionable is True


def test_real_beads_apply_remains_gated(tmp_path, monkeypatch, capsys):
    import json

    from helpers import minimal_config_dict, write_control_yaml
    from vibe_control.cli import main

    monkeypatch.delenv("VIBE_BEADS_LIVE_APPLY", raising=False)
    monkeypatch.chdir(tmp_path)
    write_control_yaml(
        tmp_path,
        {**minimal_config_dict(), "project": {"id": "vibe-control", "name": "Vibe"}},
    )
    _repo_actionable(tmp_path)
    code = main(
        [
            "task",
            "apply",
            "--apply",
            "--json",
            "--provider",
            "beads",
            "--allow-local-without-providers",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload.get("mutation") is False
    assert payload.get("mode") in {"blocked", "unavailable"}
    assert code != 0 or payload.get("ok") is False or payload.get("mode") in {"blocked", "unavailable"}


def test_strict_provider_readiness_still_required(tmp_path):
    from helpers import minimal_config_dict, write_control_yaml
    from vibe_control.product_readiness import build_probe_from_parts
    from vibe_control.task.apply_cli import run_task_apply

    write_control_yaml(
        tmp_path,
        {**minimal_config_dict(), "project": {"id": "vibe-control", "name": "Vibe"}},
    )
    _repo_actionable(tmp_path)
    probe = build_probe_from_parts(
        knowledge_available=False,
        knowledge_target_ok=False,
        sync_state="unavailable",
        task_available=True,
        task_mode="readonly",
        task_readable=True,
    )
    env = run_task_apply(
        repo_root=tmp_path,
        mode="dry_run",
        provider_name="fake",
        provider=FakeTaskProvider([]),
        strict_providers=True,
        knowledge_probe=probe,
    )
    assert env["mode"] == "blocked"
    assert env["mutation"] is False
    assert env["error"]["code"] == "KNOWLEDGE_PROVIDER_NOT_READY"


def test_apply_output_redacted_and_stable(tmp_path):
    root = _repo_actionable(tmp_path)
    expected = project_actionable_expected_tasks(project_id="vibe-control", repo_root=root)
    completed = project_completed_expected_tasks(project_id="vibe-control", repo_root=root)
    result = run_apply(
        expected=expected,
        provider=FakeTaskProvider([]),
        mode="dry_run",
        project_id="vibe-control",
        provider_name="fake",
        completed_expected=completed,
    )
    env = result.to_envelope()
    blob = str(env)
    assert "provider_task_id" not in blob or "provider_task_id_hash" in blob
    assert env["data"]["plan_by_op_type"]["create_managed"] == len(expected)
    assert env["data"]["plan_by_op_type"]["skip_completed"] >= 2
    assert list(env["data"]["plan_by_op_type"].keys())[0] == "create_managed"
    policy = env["data"]["autonomy_policy"]
    assert policy["user_asks_per_managed_op"] is False
    assert policy["live_beads_execution"] is False
    assert policy["live_beads_gate"] == "temporary_dual_gate"
    assert any(a.get("code") == "AUTONOMOUS_MANAGED_APPLY" for a in env["next_actions"])


def test_title_change_does_not_change_managed_identity(tmp_path):
    from vibe_control.task.marker import compute_managed_key

    root = _repo_actionable(tmp_path)
    tasks = project_actionable_expected_tasks(project_id="vibe-control", repo_root=root)
    t = tasks[0]
    key_a = compute_managed_key(
        project_id=t.project_id,
        ssot_id=t.ssot_id,
        ssot_path=t.ssot_path,
        ssot_anchor=t.ssot_anchor,
        task_kind=t.task_kind,
    )
    key_b = compute_managed_key(
        project_id=t.project_id,
        ssot_id=t.ssot_id,
        ssot_path=t.ssot_path,
        ssot_anchor=t.ssot_anchor,
        task_kind=t.task_kind,
    )
    assert key_a == key_b == t.managed_key
    assert t.title


def test_provider_id_not_source_identity(tmp_path):
    root = _repo_actionable(tmp_path)
    tasks = project_actionable_expected_tasks(project_id="vibe-control", repo_root=root)
    assert all(t.managed_key.startswith("sha256:") for t in tasks)
    assert all("bd-" not in t.managed_key for t in tasks)
