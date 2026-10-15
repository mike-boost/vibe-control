"""Phase 11A Slice 2 — Beads readonly adapter, provider flag, vibe-control skill."""

from __future__ import annotations

import json
from pathlib import Path

from helpers import minimal_config_dict, write_control_yaml, write_doc
from vibe_control.cli import main
from vibe_control.skills_manager import SKILL_NAMES, package_skills_root, skills_status
from vibe_control.task.beads_readonly import (
    ALLOWED_BD_SUBCOMMANDS,
    BeadsReadonlyError,
    BeadsReadonlyProvider,
    assert_readonly_bd_argv,
    parse_beads_list_json,
)
from vibe_control.task.marker import marker_from_expected, render_marker, sha256_hex
from vibe_control.task.projection import project_slice1_expected_tasks


FIXTURE_ISSUES = [
    {
        "id": "bd-11a",
        "title": "Phase 11A — SSOT Specs and Beads Readonly Reconcile",
        "description": "placeholder",
        "dependencies": ["bd-other"],
    },
    {
        "id": "bd-unmanaged",
        "title": "Random operator task",
        "description": "no marker here",
        "dependencies": [],
    },
]


def _runner_factory(payload: str, *, fail_code: int = 0):
    calls: list[list[str]] = []

    def _run(argv: list[str]) -> tuple[int, str, str]:
        calls.append(list(argv))
        if fail_code:
            return fail_code, "", "boom"
        if len(argv) >= 2 and argv[1] == "list":
            return 0, payload, ""
        if len(argv) >= 2 and argv[1] == "show":
            return 0, json.dumps(FIXTURE_ISSUES[0]), ""
        return 1, "", f"unexpected {argv}"

    return _run, calls


def test_P11A_S2_BD_ARGV_READONLY_ONLY():
    assert_readonly_bd_argv(["bd", "list", "--json"])
    assert_readonly_bd_argv(["/opt/bd", "show", "bd-1", "--json"])
    assert_readonly_bd_argv(["bd", "ready", "--json"])
    assert_readonly_bd_argv(["bd", "status", "--json"])
    for bad in ("init", "create", "update", "delete", "close"):
        try:
            assert_readonly_bd_argv(["bd", bad])
            assert False, f"expected forbid {bad}"
        except BeadsReadonlyError as exc:
            assert exc.code == "BD_MUTATION_FORBIDDEN"
    try:
        assert_readonly_bd_argv(["bd", "ready", "--json", "--claim"])
        assert False, "expected forbid --claim"
    except BeadsReadonlyError as exc:
        assert exc.code == "BD_MUTATION_FORBIDDEN"
    assert "list" in ALLOWED_BD_SUBCOMMANDS
    assert "show" in ALLOWED_BD_SUBCOMMANDS
    assert "ready" in ALLOWED_BD_SUBCOMMANDS
    assert "create" not in ALLOWED_BD_SUBCOMMANDS

def test_P11A_S2_PARSE_LIST_JSON_AND_MARKER(tmp_path):
    write_doc(tmp_path, "docs/project/vibe-control-spec.md", "spec\n")
    expected = project_slice1_expected_tasks(project_id="vibe-control", repo_root=tmp_path)[0]
    marker = marker_from_expected(
        project_id=expected.project_id,
        ssot_id=expected.ssot_id,
        ssot_path=expected.ssot_path,
        ssot_anchor=expected.ssot_anchor,
        task_kind=expected.task_kind,
        ssot_snapshot_hash=expected.ssot_snapshot_hash,
        source_item_hash=expected.source_item_hash,
    )
    issues = [
        {
            "id": "bd-11a",
            "title": expected.title,
            "description": "body\n" + render_marker(marker),
            "dependencies": [{"id": "bd-x"}],
        }
    ]
    tasks = parse_beads_list_json(json.dumps(issues))
    assert len(tasks) == 1
    assert tasks[0].provider_task_id == "bd-11a"
    assert "```vibe.task.v1" in tasks[0].description
    assert tasks[0].relations == ["bd-x"]


def test_P11A_S2_PROVIDER_INVOKES_ONLY_LIST(tmp_path):
    runner, calls = _runner_factory(json.dumps(FIXTURE_ISSUES))
    provider = BeadsReadonlyProvider(runner=runner, executable="/fake/bd")
    tasks = provider.list_tasks()
    assert provider.available is True
    assert len(tasks) == 2
    assert calls
    assert all(c[1] == "list" for c in calls)
    assert all(c[1] not in {"init", "create", "update", "delete"} for c in calls)


def test_P11A_S2_MISSING_BD_SAFE():
    provider = BeadsReadonlyProvider(
        executable="/missing/bd-not-installed",
        runner=lambda argv: (127, "", "executable not found"),
    )
    tasks = provider.list_tasks()
    assert tasks == []
    assert provider.available is False
    assert provider.warnings


def test_P11A_S2_CLI_PROVIDER_FAKE(tmp_path, monkeypatch, capsys):
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
    assert payload["command"] == "vibe task reconcile"
    assert payload["project_id"] == "vibe-control"
    assert payload["mode"] == "readonly"
    assert payload["provider"] == "fake"
    assert payload["provider_available"] is True
    assert payload["mutation"] is False
    data = payload["data"]
    assert data["provider"] == "fake"
    assert data["provider_available"] is True
    assert data["mutation"] is False
    assert data["provider_read_ok"] is True
    assert data["reconcile_skipped"] is False
    assert data["counts"]["missing"] == data["expected_count"]
    assert "matched" in data["counts"]
    assert payload["warnings"] is not None
    assert payload["next_actions"]


def test_P11A_S2_CLI_PROVIDER_BEADS(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    write_control_yaml(
        tmp_path,
        {**minimal_config_dict(), "project": {"id": "vibe-control", "name": "Vibe"}},
    )
    write_doc(tmp_path, "docs/project/vibe-control-spec.md", "spec\n")

    expected = project_slice1_expected_tasks(project_id="vibe-control", repo_root=tmp_path)
    issues = []
    for exp in expected:
        marker = marker_from_expected(
            project_id=exp.project_id,
            ssot_id=exp.ssot_id,
            ssot_path=exp.ssot_path,
            ssot_anchor=exp.ssot_anchor,
            task_kind=exp.task_kind,
            ssot_snapshot_hash=exp.ssot_snapshot_hash,
            source_item_hash=exp.source_item_hash,
        )
        issues.append(
            {
                "id": f"id-{exp.ssot_anchor}",
                "title": exp.title,
                "description": render_marker(marker),
                "dependencies": [],
            }
        )

    runner, calls = _runner_factory(json.dumps(issues))

    import vibe_control.task.reconcile_cli as reconcile_cli

    real_resolve = reconcile_cli.resolve_task_provider

    def _resolve(*, provider_name, config_provider):
        if (provider_name or "").lower() == "beads":
            return "beads", BeadsReadonlyProvider(runner=runner, executable="/fake/bd"), []
        return real_resolve(provider_name=provider_name, config_provider=config_provider)

    monkeypatch.setattr(reconcile_cli, "resolve_task_provider", _resolve)
    code = main(["task", "reconcile", "--dry-run", "--json", "--provider", "beads"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["mode"] == "readonly"
    assert payload["provider"] == "beads"
    assert payload["provider_available"] is True
    assert payload["mutation"] is False
    data = payload["data"]
    assert data["provider"] == "beads"
    assert data["provider_available"] is True
    assert data["mutation"] is False
    assert data["counts"]["matched"] == data["expected_count"]
    assert data["reconcile_skipped"] is False
    assert all(c[1] == "list" for c in calls)


def test_P11A_S2_BEADS_UNAVAILABLE_NOT_REAL_MISSING(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    write_control_yaml(
        tmp_path,
        {**minimal_config_dict(), "project": {"id": "vibe-control", "name": "Vibe"}},
    )
    write_doc(tmp_path, "docs/project/vibe-control-spec.md", "spec\n")

    import vibe_control.task.reconcile_cli as reconcile_cli

    def _resolve(*, provider_name, config_provider):
        provider = BeadsReadonlyProvider(
            executable="/missing/bd",
            runner=lambda argv: (127, "", "executable not found"),
        )
        return "beads", provider, []

    monkeypatch.setattr(reconcile_cli, "resolve_task_provider", _resolve)
    code = main(["task", "reconcile", "--dry-run", "--json", "--provider", "beads"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["mode"] == "unavailable"
    assert payload["provider"] == "beads"
    assert payload["provider_available"] is False
    assert payload["mutation"] is False
    data = payload["data"]
    assert data["reconcile_skipped"] is True
    assert data["provider_read_ok"] is False
    assert data["counts"]["missing"] == 0
    assert data["missing"] == []
    assert data["expected_count"] >= 1
    assert any(a["code"] == "BEADS_PROVIDER_UNAVAILABLE" for a in payload["next_actions"])
    assert not any(a["code"] == "PHASE11B_APPLY_PENDING" for a in payload["next_actions"])


def test_P11A_S2_BEADS_EMPTY_AVAILABLE_IS_REAL_MISSING(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    write_control_yaml(
        tmp_path,
        {**minimal_config_dict(), "project": {"id": "vibe-control", "name": "Vibe"}},
    )
    write_doc(tmp_path, "docs/project/vibe-control-spec.md", "spec\n")

    import vibe_control.task.reconcile_cli as reconcile_cli

    def _resolve(*, provider_name, config_provider):
        provider = BeadsReadonlyProvider(
            executable="/fake/bd",
            runner=lambda argv: (0, "[]", ""),
        )
        return "beads", provider, []

    monkeypatch.setattr(reconcile_cli, "resolve_task_provider", _resolve)
    code = main(["task", "reconcile", "--dry-run", "--json", "--provider", "beads"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["mode"] == "readonly"
    assert payload["provider_available"] is True
    assert payload["mutation"] is False
    data = payload["data"]
    assert data["provider_read_ok"] is True
    assert data["reconcile_skipped"] is False
    assert data["counts"]["missing"] == data["expected_count"]
    assert any(a["code"] == "PHASE11B_APPLY_PENDING" for a in payload["next_actions"])


def test_P11A_S2_VIBE_CONTROL_SKILL_PACKAGED(tmp_path, monkeypatch, capsys):
    assert "vibe-control" in SKILL_NAMES
    assert (package_skills_root() / "vibe-control" / "SKILL.md").is_file()
    text = (package_skills_root() / "vibe-control" / "SKILL.md").read_text(encoding="utf-8")
    assert "vibe knowledge status --json" in text
    assert "vibe knowledge query --question-file" in text
    assert "vibe knowledge sync --dry-run --json" in text
    assert "vibe task reconcile --dry-run --json" in text
    assert "Never call NotebookLM directly" in text or "Never call NotebookLM" in text
    assert "Never call `bd` directly" in text
    assert "Never auto-run `--apply`" in text or "Never auto-run" in text
    assert "Mandatory Phase 11A workflow" in text
    lower = text.lower()
    assert "worktree" not in lower
    assert "subagent" not in lower

    root = tmp_path / "skills"
    monkeypatch.setenv("VIBE_SKILLS_ROOT", str(root))
    status_code = main(["skills", "status", "--json"])
    status_payload = json.loads(capsys.readouterr().out)
    assert status_code == 0
    names = {s["name"] for s in status_payload["data"]["skills"]}
    assert names == {"vibe-control", "vibe-knowledge", "vibe-implementation"}

    dry_code = main(["skills", "install", "--dry-run", "--json"])
    dry_payload = json.loads(capsys.readouterr().out)
    assert dry_code == 0
    planned = {op["skill"] for op in dry_payload["data"]["operations"]}
    assert "vibe-control" in planned


def test_P11A_S2_SUPERPOWERS_COMPARISON_NOTE_EXISTS():
    path = Path("docs/project/reviews/20260714-phase11a-superpowers-skill-comparison.md")
    text = path.read_text(encoding="utf-8")
    assert "Adopt" in text
    assert "Reject" in text
    assert "worktree" in text.lower()
    assert "subagent" in text.lower()
    assert "Do not copy Superpowers business logic" in text
    assert "vibe-control" in text


def test_P11A_S2_BD_LIST_FAIL_UNAVAILABLE(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    write_control_yaml(
        tmp_path,
        {**minimal_config_dict(), "project": {"id": "vibe-control", "name": "Vibe"}},
    )
    write_doc(tmp_path, "docs/project/vibe-control-spec.md", "spec\n")

    import vibe_control.task.reconcile_cli as reconcile_cli

    def _resolve(*, provider_name, config_provider):
        provider = BeadsReadonlyProvider(
            executable="/fake/bd",
            runner=lambda argv: (2, "", "permission denied reading issues"),
        )
        return "beads", provider, []

    monkeypatch.setattr(reconcile_cli, "resolve_task_provider", _resolve)
    code = main(["task", "reconcile", "--dry-run", "--json", "--provider", "beads"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["mode"] == "unavailable"
    assert payload["provider_available"] is False
    data = payload["data"]
    assert data["reconcile_skipped"] is True
    assert data["provider_read_ok"] is False
    assert data["counts"]["missing"] == 0
    assert any("permission denied" in w.lower() or "bd list failed" in w.lower() for w in payload["warnings"])
    assert any(a["code"] == "BEADS_PROVIDER_UNAVAILABLE" for a in payload["next_actions"])


def test_P11A_S2_BD_LIST_MALFORMED_JSON(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    write_control_yaml(
        tmp_path,
        {**minimal_config_dict(), "project": {"id": "vibe-control", "name": "Vibe"}},
    )
    write_doc(tmp_path, "docs/project/vibe-control-spec.md", "spec\n")

    import vibe_control.task.reconcile_cli as reconcile_cli

    def _resolve(*, provider_name, config_provider):
        provider = BeadsReadonlyProvider(
            executable="/fake/bd",
            runner=lambda argv: (0, "{not-json", ""),
        )
        return "beads", provider, []

    monkeypatch.setattr(reconcile_cli, "resolve_task_provider", _resolve)
    code = main(["task", "reconcile", "--dry-run", "--json", "--provider", "beads"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["ok"] is True
    assert payload["mode"] == "unavailable"
    assert payload["provider_available"] is False
    assert payload["data"]["counts"]["missing"] == 0
    assert payload["warnings"]


def test_P11A_S2_BD_SHOW_FAIL_DEGRADED_WARNING(tmp_path):
    calls: list[list[str]] = []

    def _run(argv: list[str]) -> tuple[int, str, str]:
        calls.append(list(argv))
        if argv[1] == "list":
            return 0, json.dumps([{"id": "bd-1", "title": "t", "description": ""}]), ""
        if argv[1] == "show":
            return 1, "", "show failed"
        return 1, "", "unexpected"

    provider = BeadsReadonlyProvider(
        executable="/fake/bd",
        runner=_run,
        enrich_with_show=True,
    )
    tasks = provider.list_tasks()
    assert provider.available is True
    assert len(tasks) == 1
    assert any("bd show failed" in w for w in provider.warnings)
    assert any(c[1] == "show" for c in calls)
    assert all(c[1] in {"list", "show"} for c in calls)


def test_P11A_S2_RECONCILE_NEVER_REACHES_FORBIDDEN(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    write_control_yaml(
        tmp_path,
        {**minimal_config_dict(), "project": {"id": "vibe-control", "name": "Vibe"}},
    )
    write_doc(tmp_path, "docs/project/vibe-control-spec.md", "spec\n")
    seen: list[list[str]] = []

    def _run(argv: list[str]) -> tuple[int, str, str]:
        seen.append(list(argv))
        # Attempt mutation would be rejected by assert_readonly_bd_argv before runner
        # if adapter constructed forbidden argv; prove only list is used.
        assert argv[1] == "list"
        assert isinstance(argv, list)
        return 0, "[]", ""

    import vibe_control.task.reconcile_cli as reconcile_cli

    def _resolve(*, provider_name, config_provider):
        return "beads", BeadsReadonlyProvider(runner=_run, executable="/fake/bd"), []

    monkeypatch.setattr(reconcile_cli, "resolve_task_provider", _resolve)
    code = main(["task", "reconcile", "--dry-run", "--json", "--provider", "beads"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert seen
    assert all(isinstance(c, list) for c in seen)
    assert all(c[1] == "list" for c in seen)
    forbidden = {"init", "create", "update", "delete", "import", "sync"}
    assert all(c[1] not in forbidden for c in seen)


def test_P11A_S2_REQUIRES_DRY_RUN_NO_PROVIDER_CALL(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    write_control_yaml(
        tmp_path,
        {**minimal_config_dict(), "project": {"id": "vibe-control", "name": "Vibe"}},
    )
    write_doc(tmp_path, "docs/project/vibe-control-spec.md", "spec\n")
    calls: list[list[str]] = []

    import vibe_control.task.reconcile_cli as reconcile_cli

    def _resolve(*, provider_name, config_provider):
        def _run(argv: list[str]) -> tuple[int, str, str]:
            calls.append(list(argv))
            return 0, "[]", ""

        return "beads", BeadsReadonlyProvider(runner=_run, executable="/fake/bd"), []

    monkeypatch.setattr(reconcile_cli, "resolve_task_provider", _resolve)
    code = main(["task", "reconcile", "--json", "--provider", "beads"])
    payload = json.loads(capsys.readouterr().out)
    assert code != 0
    assert payload["error"]["code"] == "RECONCILE_REQUIRES_DRY_RUN"
    assert calls == []


def test_P11A_S2_CLI_ENVELOPE_FIELDS_FAKE(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    write_control_yaml(
        tmp_path,
        {**minimal_config_dict(), "project": {"id": "vibe-control", "name": "Vibe"}},
    )
    write_doc(tmp_path, "docs/project/vibe-control-spec.md", "spec\n")
    code = main(["task", "reconcile", "--dry-run", "--json", "--provider", "fake"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    for key in (
        "ok",
        "command",
        "project_id",
        "mode",
        "provider",
        "provider_available",
        "mutation",
        "data",
        "warnings",
        "next_actions",
    ):
        assert key in payload
    assert payload["mutation"] is False
    counts = payload["data"]["counts"]
    for key in ("matched", "missing", "duplicate", "stale", "conflict", "unmanaged"):
        assert key in counts


def test_P11A_S2_KNOWLEDGE_SKILL_ASK_TEMPLATE():
    text = Path("src/vibe_control/skills/vibe-knowledge/SKILL.md").read_text(encoding="utf-8")
    assert (
        "Knowledge Ask Template" in text
        or "vibe.knowledge.ask.v3" in text
        or "vibe.knowledge.ask.v2" in text
        or "vibe.knowledge.ask.v1" in text
    )
    assert "sync --apply" in text
    assert "retry --apply" in text
    assert "**no**" in text.lower() or "only when user explicitly asks" in text
    assert "Do not auto-run `sync --apply`" in text or "Do not auto-run" in text


def test_P11A_S2_VIBE_CONTROL_SKILL_CONTRACT():
    text = Path("src/vibe_control/skills/vibe-control/SKILL.md").read_text(encoding="utf-8")
    assert "vibe knowledge query" in text
    assert "vibe task reconcile --dry-run --json" in text
    lower = text.lower()
    assert "knowledge" in lower and "reconcile" in lower
    assert "notebooklm" in lower
    assert "bd" in lower
    assert "--apply" in text
