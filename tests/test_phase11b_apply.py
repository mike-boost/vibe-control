"""Phase 11B — Beads import/apply plan, fake apply, beads boundary (no live bd mutation)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from helpers import minimal_config_dict, write_control_yaml, write_doc
from vibe_control.cli import main
from vibe_control.task.apply_models import ApplyOperation
from vibe_control.task.apply_plan import build_apply_plan
from vibe_control.task.beads_apply import (
    BeadsApplyBlocked,
    build_bd_create_argv,
    build_bd_update_argv,
    execute_beads_apply_guarded,
)
from vibe_control.task.marker import marker_from_expected, parse_marker_from_text, render_marker
from vibe_control.task.models import ManagedMarker, TaskRecord
from vibe_control.task.projection import project_slice1_expected_tasks
from vibe_control.task.provider import FakeTaskProvider
from vibe_control.task.reconcile import reconcile_readonly


def _managed_description(expected, *, snapshot: str | None = None, item: str | None = None) -> str:
    marker = marker_from_expected(
        project_id=expected.project_id,
        ssot_id=expected.ssot_id,
        ssot_path=expected.ssot_path,
        ssot_anchor=expected.ssot_anchor,
        task_kind=expected.task_kind,
        ssot_snapshot_hash=snapshot if snapshot is not None else expected.ssot_snapshot_hash,
        source_item_hash=item if item is not None else expected.source_item_hash,
    )
    if snapshot is not None or item is not None:
        stale = ManagedMarker(
            schema=marker.schema,
            project_id=marker.project_id,
            task_provider=marker.task_provider,
            managed_key=marker.managed_key,
            ssot_id=marker.ssot_id,
            ssot_path=marker.ssot_path,
            ssot_anchor=marker.ssot_anchor,
            task_kind=marker.task_kind,
            ssot_snapshot_hash=snapshot if snapshot is not None else marker.ssot_snapshot_hash,
            source_item_hash=item if item is not None else marker.source_item_hash,
            managed_by=marker.managed_by,
        )
        return "Task body\n\n" + render_marker(stale)
    return "Task body\n\n" + render_marker(marker)


def _repo(tmp_path: Path) -> Path:
    write_doc(tmp_path, "docs/project/vibe-control-spec.md", "# Spec\nPhase 11B\n")
    return tmp_path


def _reconcile(tmp_path: Path, provider_tasks: list[TaskRecord]):
    expected = project_slice1_expected_tasks(project_id="vibe-control", repo_root=tmp_path)
    report = reconcile_readonly(
        project_id="vibe-control",
        expected=expected,
        provider_tasks=provider_tasks,
    )
    return expected, report


# --- Spec ---


def test_P11B_SPEC_01_spec_exists_with_boundaries():
    text = Path("docs/project/sync/phase11b-beads-import-apply-spec.md").read_text(encoding="utf-8")
    assert "create_managed" in text
    assert "update_managed" in text
    assert "skip_delete_forbidden" in text
    assert "skip_unmanaged" in text
    assert "VIBE_BEADS_LIVE_APPLY" in text
    assert "never adopt" in text.lower()
    assert "Fake-provider" in text or "fake-provider" in text.lower()


# --- Plan from reconcile ---


def test_P11B_PLAN_01_missing_create_managed(tmp_path):
    expected, report = _reconcile(_repo(tmp_path), [])
    plan = build_apply_plan(
        report,
        expected=expected,
        completed_expected=__import__(
            "vibe_control.task.projection", fromlist=["project_completed_expected_tasks"]
        ).project_completed_expected_tasks(project_id="vibe-control", repo_root=tmp_path),
    )
    creates = [o for o in plan.operations if o.op_type == "create_managed"]
    assert len(creates) == len(report.missing)
    assert all(o.executable for o in creates)
    assert plan.counts["create"] == len(report.missing)
    assert not any(o.ssot_anchor == "roadmap.phase11a" for o in creates)
    assert any(o.op_type == "skip_completed" for o in plan.operations)

def test_P11B_PLAN_02_stale_update_managed(tmp_path):
    repo = _repo(tmp_path)
    expected, report = _reconcile(
        repo,
        [
            TaskRecord(
                provider_task_id=f"bd-{e.ssot_anchor}",
                title=e.title,
                description=_managed_description(e, snapshot="sha256:" + "0" * 64),
            )
            for e in project_slice1_expected_tasks(project_id="vibe-control", repo_root=repo)
        ],
    )
    plan = build_apply_plan(report)
    updates = [o for o in plan.operations if o.op_type == "update_managed"]
    assert len(updates) == len(report.stale)
    assert all(o.executable for o in updates)
    assert all(o.before is not None and o.after is not None for o in updates)
    assert len(expected) >= 1


def test_P11B_PLAN_03_duplicate_skip(tmp_path):
    repo = _repo(tmp_path)
    expected = project_slice1_expected_tasks(project_id="vibe-control", repo_root=repo)
    e0 = expected[0]
    desc = _managed_description(e0)
    _, report = _reconcile(
        repo,
        [
            TaskRecord(provider_task_id="a", title=e0.title, description=desc),
            TaskRecord(provider_task_id="b", title=e0.title, description=desc),
        ],
    )
    plan = build_apply_plan(report)
    skips = [o for o in plan.operations if o.op_type == "skip_duplicate"]
    assert skips
    assert all(not o.executable for o in skips)


def test_P11B_PLAN_04_conflict_skip(tmp_path):
    repo = _repo(tmp_path)
    expected = project_slice1_expected_tasks(project_id="vibe-control", repo_root=repo)
    e0 = expected[0]
    # Key mismatch vs identity → MarkerError → conflict
    bad = ManagedMarker(
        schema="vibe.task.v1",
        project_id=e0.project_id,
        task_provider="beads",
        managed_key="sha256:" + "f" * 64,
        ssot_id=e0.ssot_id,
        ssot_path=e0.ssot_path,
        ssot_anchor=e0.ssot_anchor,
        task_kind=e0.task_kind,
        ssot_snapshot_hash=e0.ssot_snapshot_hash,
        source_item_hash=e0.source_item_hash,
        managed_by="vibe-control",
    )
    _, report = _reconcile(
        repo,
        [
            TaskRecord(
                provider_task_id="x",
                title=e0.title,
                description="body\n\n" + render_marker(bad),
            )
        ],
    )
    plan = build_apply_plan(report)
    assert any(o.op_type == "skip_conflict" and not o.executable for o in plan.operations)
    assert any(o.op_type == "blocked_repair_required" and not o.executable for o in plan.operations)
    assert plan.autonomy_policy.get("duplicate_conflict") == "skip_or_blocked_repair_required"
    assert any(
        a.get("code") == "REPAIR_PLAN_REQUIRED"
        for a in __import__(
            "vibe_control.task.autonomy", fromlist=["autonomy_next_actions"]
        ).autonomy_next_actions(plan, provider_name="fake")
    )


def test_P11B_PLAN_05_unmanaged_skip(tmp_path):
    repo = _repo(tmp_path)
    _, report = _reconcile(
        repo,
        [TaskRecord(provider_task_id="u1", title="Human task", description="no marker")],
    )
    plan = build_apply_plan(report)
    skips = [o for o in plan.operations if o.op_type == "skip_unmanaged"]
    assert skips
    assert all(not o.executable for o in skips)


def test_P11B_PLAN_06_delete_forbidden(tmp_path):
    repo = _repo(tmp_path)
    expected = project_slice1_expected_tasks(project_id="vibe-control", repo_root=repo)
    extra = expected[0]
    marker = marker_from_expected(
        project_id=extra.project_id,
        ssot_id="other_ssot",
        ssot_path="docs/other.md",
        ssot_anchor="other.anchor",
        task_kind="implementation_phase",
        ssot_snapshot_hash=extra.ssot_snapshot_hash,
        source_item_hash=extra.source_item_hash,
    )
    _, report = _reconcile(
        repo,
        [
            TaskRecord(
                provider_task_id="orphan",
                title="Orphan managed",
                description="body\n\n" + render_marker(marker),
            )
        ],
    )
    plan = build_apply_plan(report)
    assert any(o.op_type == "skip_delete_forbidden" and not o.executable for o in plan.operations)


def test_P11B_PLAN_07_unavailable_no_invented_missing():
    from vibe_control.task.apply_cli import build_unavailable_apply_envelope

    env = build_unavailable_apply_envelope(
        project_id="vibe-control",
        provider="beads",
        reason="provider unavailable",
    )
    assert env["mode"] == "unavailable"
    assert env["mutation"] is False
    assert env["data"]["operations"] == []
    assert env["data"]["plan"]["create"] == 0


def test_P11B_PLAN_08_no_executable_ok(tmp_path):
    repo = _repo(tmp_path)
    expected = project_slice1_expected_tasks(project_id="vibe-control", repo_root=repo)
    _, report = _reconcile(
        repo,
        [
            TaskRecord(
                provider_task_id=f"bd-{e.ssot_anchor}",
                title=e.title,
                description=_managed_description(e),
            )
            for e in expected
        ],
    )
    plan = build_apply_plan(report)
    assert plan.counts["create"] == 0
    assert plan.counts["update"] == 0
    assert not any(o.executable for o in plan.operations)


# --- Dry-run / apply ---


def test_P11B_DRY_01_dry_run_no_fake_mutation(tmp_path):
    repo = _repo(tmp_path)
    expected = project_slice1_expected_tasks(project_id="vibe-control", repo_root=repo)
    provider = FakeTaskProvider([])
    before = len(provider.list_tasks())
    from vibe_control.task.apply_engine import run_apply

    result = run_apply(
        expected=expected,
        provider=provider,
        mode="dry_run",
        project_id="vibe-control",
        provider_name="fake",
    )
    assert result.mutation is False
    assert result.mode == "dry_run"
    assert len(provider.list_tasks()) == before


def test_P11B_APPLY_01_apply_mutates_fake_create_update(tmp_path):
    repo = _repo(tmp_path)
    expected = project_slice1_expected_tasks(project_id="vibe-control", repo_root=repo)
    e0, e1 = expected[0], expected[1]
    provider = FakeTaskProvider(
        [
            TaskRecord(
                provider_task_id="bd-stale",
                title="old title",
                description=_managed_description(e0, snapshot="sha256:" + "0" * 64),
            )
        ]
    )
    from vibe_control.task.apply_engine import run_apply

    result = run_apply(
        expected=expected,
        provider=provider,
        mode="apply",
        project_id="vibe-control",
        provider_name="fake",
    )
    assert result.mutation is True
    assert result.mode == "applied"
    tasks = provider.list_tasks()
    assert len(tasks) >= 2
    keys = set()
    for t in tasks:
        m = parse_marker_from_text(t.description or "")
        if m is not None:
            keys.add(m.managed_key)
    assert e0.managed_key in keys
    assert e1.managed_key in keys


def test_P11B_GATE_01_cli_no_flags_fail_closed(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    write_control_yaml(
        tmp_path,
        {**minimal_config_dict(), "project": {"id": "vibe-control", "name": "Vibe"}},
    )
    write_doc(tmp_path, "docs/project/vibe-control-spec.md", "# Spec\n")
    code = main(["task", "apply", "--json", "--provider", "fake"])
    payload = json.loads(capsys.readouterr().out)
    assert code != 0
    assert payload["error"]["code"] == "APPLY_REQUIRES_DRY_RUN_OR_APPLY"


def test_P11B_CLI_dry_run_envelope(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    write_control_yaml(
        tmp_path,
        {**minimal_config_dict(), "project": {"id": "vibe-control", "name": "Vibe"}},
    )
    write_doc(tmp_path, "docs/project/vibe-control-spec.md", "# Spec\nPhase 11B\n")
    code = main(["task", "apply", "--dry-run", "--json", "--provider", "fake"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "vibe task apply"
    assert payload["mode"] == "dry_run"
    assert payload["mutation"] is False
    assert "plan" in payload["data"]
    assert "operations" in payload["data"]


def test_P11B_CLI_apply_fake(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    write_control_yaml(
        tmp_path,
        {**minimal_config_dict(), "project": {"id": "vibe-control", "name": "Vibe"}},
    )
    write_doc(tmp_path, "docs/project/vibe-control-spec.md", "# Spec\nPhase 11B\n")
    code = main(["task", "apply", "--apply", "--json", "--provider", "fake"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mutation"] is True
    assert payload["mode"] == "applied"
    assert payload["provider"] == "fake"


# --- Identity / safety ---


def test_P11B_ID_01_managed_key_not_provider_id(tmp_path):
    _, report = _reconcile(_repo(tmp_path), [])
    plan = build_apply_plan(report)
    for op in plan.operations:
        if op.op_type == "create_managed":
            assert op.managed_key.startswith("sha256:")
            assert op.provider_task_id is None


def test_P11B_ID_02_title_change_same_identity(tmp_path):
    repo = _repo(tmp_path)
    expected = project_slice1_expected_tasks(project_id="vibe-control", repo_root=repo)
    e0 = expected[0]
    _, report = _reconcile(
        repo,
        [
            TaskRecord(
                provider_task_id="bd-1",
                title="Different title",
                description=_managed_description(e0),
            )
        ],
    )
    # Title is not identity: matching hashes → matched, not a new managed_key.
    assert any(i.managed_key == e0.managed_key and i.category == "matched" for i in report.matched)
    plan = build_apply_plan(report)
    assert not any(
        o.op_type == "create_managed" and o.managed_key == e0.managed_key for o in plan.operations
    )


# --- Beads boundary ---


def test_P11B_BEADS_01_create_argv_builder():
    op = ApplyOperation(
        op_type="create_managed",
        managed_key="sha256:" + "a" * 64,
        project_id="vibe-control",
        ssot_id="vibe_control_spec",
        ssot_path="docs/project/vibe-control-spec.md",
        ssot_anchor="roadmap.phase11b",
        task_kind="implementation_phase",
        ssot_snapshot_hash="sha256:" + "b" * 64,
        source_item_hash="sha256:" + "c" * 64,
        title="Phase 11B",
        reason="missing",
        executable=True,
        description="body with marker",
    )
    argv = build_bd_create_argv(op)
    assert argv[0] == "bd"
    assert "create" in argv
    assert "--metadata" in argv
    assert "--spec-id" in argv
    assert "vibe_control_spec" in argv
    assert "delete" not in argv
    assert "--claim" not in argv
    meta = argv[argv.index("--metadata") + 1]
    assert "managed_key" in meta
    assert "ssot_snapshot_hash" in meta


def test_P11B_BEADS_02_update_argv_builder():
    op = ApplyOperation(
        op_type="update_managed",
        managed_key="sha256:" + "a" * 64,
        project_id="vibe-control",
        ssot_id="vibe_control_spec",
        ssot_path="docs/project/vibe-control-spec.md",
        ssot_anchor="roadmap.phase11b",
        task_kind="implementation_phase",
        ssot_snapshot_hash="sha256:" + "b" * 64,
        source_item_hash="sha256:" + "c" * 64,
        title="Phase 11B",
        reason="stale",
        executable=True,
        provider_task_id="bd-abc",
        description="updated body",
    )
    argv = build_bd_update_argv(op)
    assert argv[0] == "bd"
    assert "update" in argv
    assert "--metadata" in argv
    assert "--spec-id" in argv
    assert "delete" not in argv
    assert "--claim" not in argv
    assert "bd-abc" in argv


def test_P11B_BEADS_03_live_apply_blocked_without_approval(monkeypatch):
    monkeypatch.delenv("VIBE_BEADS_LIVE_APPLY", raising=False)
    op = ApplyOperation(
        op_type="create_managed",
        managed_key="sha256:" + "a" * 64,
        project_id="vibe-control",
        ssot_id="vibe_control_spec",
        ssot_path="docs/project/vibe-control-spec.md",
        ssot_anchor="roadmap.phase11b",
        task_kind="implementation_phase",
        title="Phase 11B",
        reason="missing",
        executable=True,
        description="body",
    )
    with pytest.raises(BeadsApplyBlocked):
        execute_beads_apply_guarded([op], runner=lambda argv: None, confirm=True)
    monkeypatch.setenv("VIBE_BEADS_LIVE_APPLY", "1")
    with pytest.raises(BeadsApplyBlocked):
        execute_beads_apply_guarded([op], runner=lambda argv: None, confirm=False)


def test_P11B_BEADS_03b_env_and_confirm_records_argv_only(monkeypatch):
    monkeypatch.setenv("VIBE_BEADS_LIVE_APPLY", "1")
    recorded: list[list[str]] = []
    op = ApplyOperation(
        op_type="create_managed",
        managed_key="sha256:" + "a" * 64,
        project_id="vibe-control",
        ssot_id="vibe_control_spec",
        ssot_path="docs/project/vibe-control-spec.md",
        ssot_anchor="roadmap.phase11b",
        task_kind="implementation_phase",
        ssot_snapshot_hash="sha256:" + "b" * 64,
        source_item_hash="sha256:" + "c" * 64,
        title="Phase 11B",
        reason="missing",
        executable=True,
        description="body",
    )
    out = execute_beads_apply_guarded(
        [op],
        runner=lambda argv: recorded.append(list(argv)) or {"returncode": 0, "provider_task_id": "bd-test1"},
        confirm=True,
    )
    assert len(out) == 1
    assert recorded[0][1] == "create"
    assert "--metadata" in recorded[0]
    assert "--silent" in recorded[0]
    assert "delete" not in recorded[0]
    assert "close" not in recorded[0]
    assert "--claim" not in recorded[0]
    assert out[0]["provider_task_id"] == "bd-test1"

def test_P11B_BEADS_04_delete_not_implemented():
    from vibe_control.task import beads_apply

    assert not hasattr(beads_apply, "build_bd_delete_argv")


def test_P11B_CLI_beads_apply_blocked(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("VIBE_BEADS_LIVE_APPLY", raising=False)
    monkeypatch.chdir(tmp_path)
    write_control_yaml(
        tmp_path,
        {**minimal_config_dict(), "project": {"id": "vibe-control", "name": "Vibe"}},
    )
    write_doc(tmp_path, "docs/project/vibe-control-spec.md", "# Spec\nPhase 11B\n")
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
    if payload.get("mode") == "blocked":
        assert payload.get("ok") is False