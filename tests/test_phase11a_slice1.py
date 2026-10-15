"""Phase 11A Slice 1 — expected tasks, marker, fake provider, readonly reconcile, CLI."""

from __future__ import annotations

import json
from pathlib import Path

from helpers import minimal_config_dict, write_control_yaml, write_doc
from vibe_control.cli import main
from vibe_control.task.marker import (
    MarkerError,
    compute_managed_key,
    marker_from_expected,
    parse_marker_from_text,
    render_marker,
    sha256_hex,
)
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


def test_P11A_IDENTITY_001_managed_key_from_tuple_only():
    key = compute_managed_key(
        project_id="vibe-control",
        ssot_id="vibe_control_spec",
        ssot_path="docs/project/vibe-control-spec.md",
        ssot_anchor="roadmap.phase11a",
        task_kind="implementation_phase",
    )
    assert key.startswith("sha256:")
    assert len(key) == len("sha256:") + 64
    same = compute_managed_key(
        project_id="vibe-control",
        ssot_id="vibe_control_spec",
        ssot_path="docs/project/vibe-control-spec.md",
        ssot_anchor="roadmap.phase11a",
        task_kind="implementation_phase",
    )
    assert key == same


def test_P11A_IDENTITY_002_provider_task_id_not_required(tmp_path):
    from helpers import write_actionable_roadmap_state

    write_doc(tmp_path, "docs/project/vibe-control-spec.md", "# Spec\nPhase 11A\n")
    write_actionable_roadmap_state(tmp_path)
    expected = project_slice1_expected_tasks(project_id="vibe-control", repo_root=tmp_path)
    assert len(expected) >= 1
    assert all(e.managed_key.startswith("sha256:") for e in expected)
    assert all(e.actionable for e in expected)
    assert "roadmap.phase11a" not in {e.ssot_anchor for e in expected}
    assert "roadmap.phase11b.live_apply" in {e.ssot_anchor for e in expected}
    assert all(e.ssot_id == "vibe_control_spec" for e in expected)


def test_P11A_MARKER_001_parse_and_reject_malformed():
    marker = marker_from_expected(
        project_id="vibe-control",
        ssot_id="vibe_control_spec",
        ssot_path="docs/project/vibe-control-spec.md",
        ssot_anchor="roadmap.phase11a",
        task_kind="implementation_phase",
        ssot_snapshot_hash=sha256_hex("a"),
        source_item_hash=sha256_hex("b"),
    )
    text = render_marker(marker)
    parsed = parse_marker_from_text("intro\n" + text + "\nfooter")
    assert parsed is not None
    assert parsed.managed_key == marker.managed_key
    assert parse_marker_from_text("no marker here") is None
    bad = text.replace(marker.managed_key, "sha256:" + ("0" * 64))
    try:
        parse_marker_from_text(bad)
        assert False, "expected MarkerError"
    except MarkerError as exc:
        assert exc.code == "MARKER_KEY_MISMATCH"


def test_P11A_RECONCILE_missing_when_empty_provider(tmp_path):
    write_doc(tmp_path, "docs/project/vibe-control-spec.md", "spec\n")
    expected = project_slice1_expected_tasks(project_id="vibe-control", repo_root=tmp_path)
    report = reconcile_readonly(
        project_id="vibe-control",
        expected=expected,
        provider_tasks=[],
    )
    assert len(report.missing) == len(expected)
    assert report.matched == []
    assert report.mutation is False


def test_P11A_RECONCILE_matched(tmp_path):
    write_doc(tmp_path, "docs/project/vibe-control-spec.md", "spec body\n")
    expected = project_slice1_expected_tasks(project_id="vibe-control", repo_root=tmp_path)
    tasks = [
        TaskRecord(
            provider_task_id=f"bd-{i}",
            title=exp.title,
            description=_managed_description(exp),
        )
        for i, exp in enumerate(expected)
    ]
    report = reconcile_readonly(
        project_id="vibe-control",
        expected=expected,
        provider_tasks=tasks,
    )
    assert len(report.matched) == len(expected)
    assert report.missing == []
    assert report.duplicate == []
    assert report.stale == []
    assert report.conflict == []
    assert report.unmanaged == []


def test_P11A_RECONCILE_duplicate(tmp_path):
    write_doc(tmp_path, "docs/project/vibe-control-spec.md", "spec\n")
    expected = project_slice1_expected_tasks(project_id="vibe-control", repo_root=tmp_path)
    exp = expected[0]
    desc = _managed_description(exp)
    tasks = [
        TaskRecord(provider_task_id="a", title="one", description=desc),
        TaskRecord(provider_task_id="b", title="two", description=desc),
        TaskRecord(
            provider_task_id="c",
            title=expected[1].title,
            description=_managed_description(expected[1]),
        ),
    ]
    report = reconcile_readonly(
        project_id="vibe-control",
        expected=expected,
        provider_tasks=tasks,
    )
    assert len(report.duplicate) == 1
    assert report.duplicate[0].managed_key == exp.managed_key
    assert set(report.duplicate[0].provider_task_ids) == {"a", "b"}
    assert len(report.matched) == 1


def test_P11A_RECONCILE_stale(tmp_path):
    write_doc(tmp_path, "docs/project/vibe-control-spec.md", "spec\n")
    expected = project_slice1_expected_tasks(project_id="vibe-control", repo_root=tmp_path)
    exp = expected[0]
    tasks = [
        TaskRecord(
            provider_task_id="stale-1",
            title=exp.title,
            description=_managed_description(
                exp,
                snapshot=sha256_hex("old-snapshot"),
                item=sha256_hex("old-item"),
            ),
        ),
        TaskRecord(
            provider_task_id="ok-2",
            title=expected[1].title,
            description=_managed_description(expected[1]),
        ),
    ]
    report = reconcile_readonly(
        project_id="vibe-control",
        expected=expected,
        provider_tasks=tasks,
    )
    assert len(report.stale) == 1
    assert report.stale[0].managed_key == exp.managed_key
    assert len(report.matched) == 1


def test_P11A_RECONCILE_conflict_malformed_marker(tmp_path):
    write_doc(tmp_path, "docs/project/vibe-control-spec.md", "spec\n")
    expected = project_slice1_expected_tasks(project_id="vibe-control", repo_root=tmp_path)
    tasks = [
        TaskRecord(
            provider_task_id="bad",
            title="broken",
            description="```vibe.task.v1\nschema: vibe.task.v1\nproject_id: x\n```",
        )
    ]
    report = reconcile_readonly(
        project_id="vibe-control",
        expected=expected,
        provider_tasks=tasks,
    )
    assert len(report.conflict) >= 1
    assert any(i.provider_task_ids == ["bad"] for i in report.conflict)
    assert len(report.missing) == len(expected)


def test_P11A_RECONCILE_unmanaged_and_title_not_identity(tmp_path):
    write_doc(tmp_path, "docs/project/vibe-control-spec.md", "spec\n")
    expected = project_slice1_expected_tasks(project_id="vibe-control", repo_root=tmp_path)
    tasks = [
        TaskRecord(
            provider_task_id="u1",
            title=expected[0].title,
            description="just a note",
            relations=["depends-on:something"],
        )
    ]
    report = reconcile_readonly(
        project_id="vibe-control",
        expected=expected,
        provider_tasks=tasks,
    )
    assert len(report.unmanaged) == 1
    assert report.unmanaged[0].titles == [expected[0].title]
    assert len(report.missing) == len(expected)
    assert report.matched == []


def test_P11A_RECONCILE_provider_task_id_alone_never_identity(tmp_path):
    write_doc(tmp_path, "docs/project/vibe-control-spec.md", "spec\n")
    expected = project_slice1_expected_tasks(project_id="vibe-control", repo_root=tmp_path)
    tasks = [
        TaskRecord(provider_task_id=expected[0].managed_key, title="x", description="")
    ]
    report = reconcile_readonly(
        project_id="vibe-control",
        expected=expected,
        provider_tasks=tasks,
    )
    assert len(report.unmanaged) == 1
    assert report.matched == []


def test_P11A_FAKE_PROVIDER_list_tasks():
    provider = FakeTaskProvider([TaskRecord(provider_task_id="1", title="t")])
    assert provider.name == "fake"
    assert len(provider.list_tasks()) == 1


def test_P11A_CLI_RECONCILE_requires_dry_run(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    write_control_yaml(
        tmp_path,
        {**minimal_config_dict(), "project": {"id": "vibe-control", "name": "Vibe"}},
    )
    write_doc(tmp_path, "docs/project/vibe-control-spec.md", "spec\n")
    code = main(["task", "reconcile", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code != 0
    assert payload["ok"] is False
    assert payload["error"]["code"] == "RECONCILE_REQUIRES_DRY_RUN"


def test_P11A_CLI_RECONCILE_DRY_RUN_001(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    write_control_yaml(
        tmp_path,
        {**minimal_config_dict(), "project": {"id": "vibe-control", "name": "Vibe"}},
    )
    write_doc(tmp_path, "docs/project/vibe-control-spec.md", "spec\n")
    code = main(["task", "reconcile", "--dry-run", "--json", "--provider", "fake"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["ok"] is True
    assert payload["mode"] == "readonly"
    data = payload["data"]
    assert data["mutation"] is False
    assert data["expected_count"] == len(project_slice1_expected_tasks(project_id="vibe-control", repo_root=tmp_path))
    assert data["provider_task_count"] == 0
    assert data["counts"]["missing"] == data["expected_count"]
    assert all(not a.get("mutation") for a in payload["next_actions"])


def test_P11A_NO_MUTATION_PATHS_001():
    reconcile_src = Path("src/vibe_control/task/reconcile.py").read_text(encoding="utf-8")
    assert "bd create" not in reconcile_src
    assert "bd update" not in reconcile_src
    assert "bd delete" not in reconcile_src
    assert "bd init" not in reconcile_src
    cli_src = Path("src/vibe_control/cli.py").read_text(encoding="utf-8")
    assert "cmd_task_reconcile" in cli_src
    assert "RECONCILE_REQUIRES_DRY_RUN" in cli_src


def test_P11A_SKILL_ROUTES_RECONCILE():
    text = Path("src/vibe_control/skills/vibe-implementation/SKILL.md").read_text(encoding="utf-8")
    assert "vibe task reconcile --dry-run --json" in text
    assert "Phase 11B" in text
    assert "bd create" not in text.lower() or "not raw `bd`" in text or "Do not call `bd` directly" in text


def test_P11A_RECONCILE_stale_source_item_hash_only(tmp_path):
    write_doc(tmp_path, "docs/project/vibe-control-spec.md", "spec\n")
    expected = project_slice1_expected_tasks(project_id="vibe-control", repo_root=tmp_path)
    exp = expected[0]
    tasks = [
        TaskRecord(
            provider_task_id="stale-item",
            title=exp.title,
            description=_managed_description(exp, item=sha256_hex("old-item-only")),
        ),
        TaskRecord(
            provider_task_id="ok-2",
            title=expected[1].title,
            description=_managed_description(expected[1]),
        ),
    ]
    report = reconcile_readonly(
        project_id="vibe-control",
        expected=expected,
        provider_tasks=tasks,
    )
    assert len(report.stale) == 1
    assert report.stale[0].managed_key == exp.managed_key


def test_P11A_RECONCILE_contradictory_marker_identity(tmp_path):
    write_doc(tmp_path, "docs/project/vibe-control-spec.md", "spec\n")
    expected = project_slice1_expected_tasks(project_id="vibe-control", repo_root=tmp_path)
    exp = expected[0]
    marker = marker_from_expected(
        project_id=exp.project_id,
        ssot_id=exp.ssot_id,
        ssot_path=exp.ssot_path,
        ssot_anchor=exp.ssot_anchor,
        task_kind=exp.task_kind,
        ssot_snapshot_hash=exp.ssot_snapshot_hash,
        source_item_hash=exp.source_item_hash,
    )
    body = render_marker(marker).replace(
        f"ssot_anchor: {exp.ssot_anchor}",
        "ssot_anchor: roadmap.phase99",
    )
    tasks = [TaskRecord(provider_task_id="c1", title=exp.title, description=body)]
    report = reconcile_readonly(
        project_id="vibe-control",
        expected=expected,
        provider_tasks=tasks,
    )
    assert len(report.conflict) >= 1
    assert report.matched == []


def test_P11A_RECONCILE_order_independent(tmp_path):
    write_doc(tmp_path, "docs/project/vibe-control-spec.md", "spec\n")
    expected = project_slice1_expected_tasks(project_id="vibe-control", repo_root=tmp_path)
    tasks_fwd = [
        TaskRecord(
            provider_task_id=f"bd-{i}",
            title=exp.title,
            description=_managed_description(exp),
        )
        for i, exp in enumerate(expected)
    ]
    tasks_rev = list(reversed(tasks_fwd))
    a = reconcile_readonly(project_id="vibe-control", expected=expected, provider_tasks=tasks_fwd)
    b = reconcile_readonly(project_id="vibe-control", expected=expected, provider_tasks=tasks_rev)
    assert a.to_dict()["counts"] == b.to_dict()["counts"]
    assert {m.managed_key for m in a.matched} == {m.managed_key for m in b.matched}


def test_P11A_RECONCILE_marker_field_order_independent(tmp_path):
    write_doc(tmp_path, "docs/project/vibe-control-spec.md", "spec\n")
    expected = project_slice1_expected_tasks(project_id="vibe-control", repo_root=tmp_path)
    exp = expected[0]
    marker = marker_from_expected(
        project_id=exp.project_id,
        ssot_id=exp.ssot_id,
        ssot_path=exp.ssot_path,
        ssot_anchor=exp.ssot_anchor,
        task_kind=exp.task_kind,
        ssot_snapshot_hash=exp.ssot_snapshot_hash,
        source_item_hash=exp.source_item_hash,
    )
    # Reverse field order inside fence body.
    lines = [f"{k}: {marker.to_dict()[k]}" for k in reversed(list(marker.to_dict().keys()))]
    reordered = "```vibe.task.v1\n" + "\n".join(lines) + "\n```"
    parsed = parse_marker_from_text(reordered)
    assert parsed is not None
    assert parsed.managed_key == exp.managed_key
    tasks = [
        TaskRecord(provider_task_id="r1", title=exp.title, description=reordered),
        *[
            TaskRecord(
                provider_task_id=f"r{i + 2}",
                title=exp_i.title,
                description=_managed_description(exp_i),
            )
            for i, exp_i in enumerate(expected[1:])
        ],
    ]
    report = reconcile_readonly(
        project_id="vibe-control",
        expected=expected,
        provider_tasks=tasks,
    )
    assert len(report.matched) == len(expected)


def test_P11A_RECONCILE_relations_never_replace_managed_key(tmp_path):
    write_doc(tmp_path, "docs/project/vibe-control-spec.md", "spec\n")
    expected = project_slice1_expected_tasks(project_id="vibe-control", repo_root=tmp_path)
    exp = expected[0]
    tasks = [
        TaskRecord(
            provider_task_id="rel-1",
            title=exp.title,
            description=_managed_description(exp),
            relations=[expected[1].managed_key, "bd-other"],
        )
    ]
    report = reconcile_readonly(
        project_id="vibe-control",
        expected=expected,
        provider_tasks=tasks,
    )
    assert len(report.matched) == 1
    assert report.matched[0].managed_key == exp.managed_key
    assert len(report.missing) == len(expected) - 1
