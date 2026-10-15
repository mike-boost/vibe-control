"""Phase 10.5 — Skills, Doctor, Init, and CLI Boundary Hardening tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vibe_control.cli import main
from vibe_control.json_envelope import next_action
from vibe_control.skills_manager import SKILL_NAMES, package_skills_root
from vibe_control.task.beads_provider import BeadsProvider, BeadsStatus

from helpers import minimal_config_dict, write_control_yaml, write_doc, write_registry

SKILLS_ROOT = package_skills_root()


def _assert_structured_next_actions(items: list) -> None:
    assert items, "expected next_actions"
    for item in items:
        assert isinstance(item, dict), f"expected structured next_action, got {item!r}"
        for key in ("code", "command", "mutation", "reason"):
            assert key in item
        assert isinstance(item["mutation"], bool)


def test_P10_5_SKILL_NAME_001_provider_neutral_names():
    assert SKILL_NAMES == ("vibe-control", "vibe-knowledge", "vibe-implementation")
    names = {p.name for p in SKILLS_ROOT.iterdir() if p.is_dir()}
    assert names == {"vibe-control", "vibe-knowledge", "vibe-implementation"}
    assert "notebooklm-skill" not in names
    assert "beads-skill" not in names


def test_P10_5_SKILL_ROUTER_001_knowledge_routing_table():
    text = (SKILLS_ROOT / "vibe-knowledge" / "SKILL.md").read_text(encoding="utf-8")
    assert "vibe knowledge doctor --json" in text
    assert "vibe knowledge status --json" in text
    assert "vibe knowledge init-preview --json" in text
    assert "vibe knowledge query --question-file" in text
    assert "vibe knowledge sync --dry-run --json" in text
    assert "vibe knowledge sync --apply --json" in text
    assert "Never auto-run" in text or "Auto-run only when" in text
    assert "Do not auto-run `sync --apply`" in text or "sync --apply" in text
    assert "mutation: true" in text or "mutation: false" in text


def test_P10_5_SKILL_ROUTER_002_implementation_routing_table():
    text = (SKILLS_ROOT / "vibe-implementation" / "SKILL.md").read_text(encoding="utf-8")
    assert "vibe task doctor --json" in text
    assert "vibe task status --json" in text
    assert "vibe task install-guide --json" in text
    assert "vibe task init-preview --json" in text
    assert ".beads" in text
    assert ".beeds" not in text
    assert "Phase 11" in text
    assert "Never run `bd init`" in text or "never auto-run" in text.lower()


def test_P10_5_CLI_KNOWLEDGE_DOCTOR_001_readonly(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    write_control_yaml(
        tmp_path,
        {
            **minimal_config_dict(),
            "knowledge": {
                **minimal_config_dict()["knowledge"],
                "notebooks": {
                    "default_alias": "OPM-test",
                    "allow_list": [
                        {
                            "alias": "OPM-test",
                            "display_name": "OPM-test",
                            "ref_env": "NOTEBOOKLM_NOTEBOOK_OPM_TEST",
                            "purpose": "test",
                            "allowed_operations": ["status"],
                        }
                    ],
                },
            },
        },
    )
    write_registry(tmp_path, [{"id": "s1", "status": "active", "path": "docs/a.md"}])
    write_doc(tmp_path, "docs/a.md", "# A\n")
    monkeypatch.setenv("NOTEBOOKLM_NOTEBOOK_OPM_TEST", "fake-notebook-ref")

    code = main(["knowledge", "doctor", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "vibe knowledge doctor"
    assert payload["mode"] == "readonly"
    assert "data" in payload
    assert payload["data"]["depth"] == "shallow"
    assert payload["data"]["config"]["exists"] is True
    assert payload["data"]["desired_snapshot"]["build_ok"] is True
    _assert_structured_next_actions(payload["next_actions"])
    # readonly: no mutation flags required for doctor itself
    assert all(not a.get("mutation") for a in payload["next_actions"])


def test_P10_5_CLI_KNOWLEDGE_INIT_001_readonly(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    code = main(["knowledge", "init-preview", "--json"])
    payload = json.loads(capsys.readouterr().out)
    # missing config still returns a plan envelope
    assert payload["command"] == "vibe knowledge init-preview"
    assert payload["mode"] == "readonly"
    assert payload["ok"] is True
    steps = payload["data"]["steps"]
    assert steps
    _assert_structured_next_actions(payload["next_actions"])
    assert all(not a.get("mutation") for a in payload["next_actions"])
    # mutation advisories may exist in steps but must be labeled
    for step in steps:
        assert "mutation" in step
        if step["mutation"]:
            assert "--apply" in step["command"]


def test_P10_5_CLI_TASK_DOCTOR_001(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    write_control_yaml(tmp_path)
    monkeypatch.setattr(
        "vibe_control.task.doctor.BeadsProvider.which",
        lambda self: None,
    )
    code = main(["task", "doctor", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["ok"] is True
    assert payload["mode"] == "readonly"
    assert "BEADS_NOT_INSTALLED" in payload["data"]["codes"]
    _assert_structured_next_actions(payload["next_actions"])
    assert any(a["code"] == "BEADS_NOT_INSTALLED" for a in payload["next_actions"])


def test_P10_5_CLI_TASK_STATUS_001_no_not_implemented(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    write_control_yaml(tmp_path)
    beads = tmp_path / ".beads"
    beads.mkdir()
    (beads / "config.yaml").write_text("x: 1\n", encoding="utf-8")

    class FakeBeads(BeadsProvider):
        def which(self):
            return "/tmp/fake-bd"

        def status(self) -> BeadsStatus:
            return BeadsStatus(
                installed=True,
                executable="/tmp/fake-bd",
                version="bd fake",
                message="ok",
            )

    monkeypatch.setattr("vibe_control.task.doctor.BeadsProvider", FakeBeads)
    code = main(["task", "status", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["ok"] is True
    assert (payload.get("error") or {}).get("code") != "NOT_IMPLEMENTED"
    assert payload["data"]["readiness"] == "ready"
    assert payload["data"]["initialized"] is True
    assert payload["data"]["beads_dir_present"] is True
    _assert_structured_next_actions(payload["next_actions"])


def test_P10_5_ENVELOPE_NEXT_ACTIONS_001_helper_shape():
    item = next_action(
        code="CONFIG_NOT_FOUND",
        command="vibe knowledge init-preview --json",
        mutation=False,
        reason="Config is missing.",
    )
    assert item == {
        "code": "CONFIG_NOT_FOUND",
        "command": "vibe knowledge init-preview --json",
        "mutation": False,
        "reason": "Config is missing.",
    }


def test_P10_5_MUTATION_GATE_001_sync_and_retry(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    write_control_yaml(tmp_path)
    code = main(["knowledge", "sync", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["error"]["code"] == "SYNC_REQUIRES_DRY_RUN_OR_APPLY"
    _assert_structured_next_actions(payload["next_actions"])
    assert any(a["mutation"] is False and "dry-run" in a["command"] for a in payload["next_actions"])
    assert any(a["mutation"] is True and "--apply" in a["command"] for a in payload["next_actions"])

    code = main(["knowledge", "retry", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["error"]["code"] == "RETRY_REQUIRES_DRY_RUN_OR_APPLY"
    _assert_structured_next_actions(payload["next_actions"])


def test_P10_5_RETRY_DRY_RUN_001(tmp_path, monkeypatch, capsys):
    """retry --dry-run is accepted (not fail-closed) and remains non-mutating path."""
    monkeypatch.chdir(tmp_path)
    cfg = {
        **minimal_config_dict(),
        "knowledge": {
            **minimal_config_dict()["knowledge"],
            "notebooks": {
                "default_alias": "OPM-test",
                "allow_list": [
                    {
                        "alias": "OPM-test",
                        "display_name": "OPM-test",
                        "ref_env": "NOTEBOOKLM_NOTEBOOK_OPM_TEST",
                        "purpose": "test",
                        "allowed_operations": ["status", "sync", "retry"],
                    }
                ],
            },
        },
    }
    write_control_yaml(tmp_path, cfg)
    write_registry(tmp_path, [{"id": "s1", "status": "active", "path": "docs/a.md"}])
    write_doc(tmp_path, "docs/a.md", "# A\n")
    monkeypatch.setenv("NOTEBOOKLM_NOTEBOOK_OPM_TEST", "fake-notebook-ref")
    monkeypatch.setenv("VIBE_PHASE8_FAKE_PROVIDER", "readonly")

    code = main(["knowledge", "retry", "--dry-run", "--json"])
    payload = json.loads(capsys.readouterr().out)
    # May succeed or fail on fixture details, but must NOT be RETRY_REQUIRES_*
    assert (payload.get("error") or {}).get("code") != "RETRY_REQUIRES_DRY_RUN_OR_APPLY"
    if payload.get("ok"):
        assert payload["data"].get("dry_run") is True or "operations" in payload["data"]


def test_P10_5_SKILLS_INSTALL_GATE_001(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("VIBE_SKILLS_ROOT", str(tmp_path / "skills"))
    code = main(["skills", "install", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["error"]["code"] == "SKILLS_INSTALL_REQUIRES_DRY_RUN_OR_APPLY"
    assert not (tmp_path / "skills" / "vibe-knowledge").exists()
    _assert_structured_next_actions(payload["next_actions"])

    code = main(["skills", "install", "--dry-run", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["mode"] == "dry_run"
    assert payload["data"]["dry_run"] is True
    assert not (tmp_path / "skills" / "vibe-knowledge").exists()

    code = main(["skills", "install", "--apply", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["mode"] == "mutation"
    assert (tmp_path / "skills" / "vibe-knowledge").is_symlink()


def test_P10_5_RETRY_GATE_001(capsys):
    code = main(["knowledge", "retry", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["error"]["code"] == "RETRY_REQUIRES_DRY_RUN_OR_APPLY"


def test_P10_5_KNOWLEDGE_DOCTOR_DEEP_DEFERRED(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    write_control_yaml(tmp_path)
    write_registry(tmp_path, [{"id": "s1", "status": "active", "path": "docs/a.md"}])
    write_doc(tmp_path, "docs/a.md", "# A\n")
    code = main(["knowledge", "doctor", "--deep", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["data"]["depth"] == "shallow"
    assert payload["data"]["deep_requested"] is True
    assert payload["data"]["deep_supported"] is False
    assert any("deferred" in w.lower() for w in payload.get("warnings") or [])


def test_P10_5_STATUS_STATE_SPECIFIC_NEXT_ACTIONS(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    cfg = {
        **minimal_config_dict(),
        "knowledge": {
            **minimal_config_dict()["knowledge"],
            "notebooks": {
                "default_alias": "OPM-test",
                "allow_list": [
                    {
                        "alias": "OPM-test",
                        "display_name": "OPM-test",
                        "ref_env": "NOTEBOOKLM_NOTEBOOK_OPM_TEST",
                        "purpose": "test",
                        "allowed_operations": ["status"],
                    }
                ],
            },
        },
    }
    write_control_yaml(tmp_path, cfg)
    write_registry(tmp_path, [{"id": "s1", "status": "active", "path": "docs/a.md"}])
    write_doc(tmp_path, "docs/a.md", "# A\n")
    monkeypatch.setenv("NOTEBOOKLM_NOTEBOOK_OPM_TEST", "fake-ref")
    monkeypatch.setenv("VIBE_PHASE8_FAKE_PROVIDER", "readonly")
    code = main(["knowledge", "status", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    _assert_structured_next_actions(payload["next_actions"])
    assert all(isinstance(a, dict) for a in payload["next_actions"])
    # Not the old static three-string-only contract
    assert not any(isinstance(a, str) for a in payload["next_actions"])


def test_P10_5_PENDING_RETRY_HINT_USES_DRY_RUN():
    text = Path("src/vibe_control/knowledge/pending_sync.py").read_text(encoding="utf-8")
    assert 'next_action: str = "vibe knowledge retry --json"' not in text
    assert "retry --dry-run --json" in text
    text2 = Path("src/vibe_control/spec/publish.py").read_text(encoding="utf-8")
    assert '"vibe knowledge retry --json"' not in text2
    assert "retry --dry-run --json" in text2


def test_P10_5_NO_REAL_NOTEBOOKLM_MUTATION_001():
    # Phase 10.5 doctor/init/task modules must not call NotebookLM mutation APIs.
    paths = [
        Path("src/vibe_control/knowledge/doctor.py"),
        Path("src/vibe_control/task/doctor.py"),
    ]
    forbidden = ("add_file_source", "delete_source", "source add", "--allow-add")
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, f"{path} contains {token!r}"


def test_P10_5_NO_BEADS_TASK_CREATE_001(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    write_control_yaml(tmp_path)
    monkeypatch.setattr(
        "vibe_control.task.doctor.BeadsProvider.which",
        lambda self: "/tmp/fake-bd",
    )
    monkeypatch.setattr(
        "vibe_control.task.doctor.BeadsProvider.status",
        lambda self: BeadsStatus(
            installed=True, executable="/tmp/fake-bd", version="x", message="ok"
        ),
    )
    code = main(["task", "doctor", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["data"]["mutations"]["task_create"] is False
    assert payload["data"]["mutations"]["bd_init"] is False


def test_P10_5_STALE_PHASE3_MESSAGE_001():
    roots = [
        Path("src/vibe_control/cli.py"),
        Path("src/vibe_control/integration.py"),
        Path("src/vibe_control/knowledge/notebooklm_provider.py"),
    ]
    for path in roots:
        text = path.read_text(encoding="utf-8")
        assert "safe_to_sync remains false in Phase 3" not in text


def test_P10_5_SKILLS_THIN_AND_NO_AUTO_MUTATION():
    for name in ("vibe-control", "vibe-knowledge", "vibe-implementation"):
        text = (SKILLS_ROOT / name / "SKILL.md").read_text(encoding="utf-8")
        assert len(text.splitlines()) < 120
        assert "Routing table" in text
    knowledge = (SKILLS_ROOT / "vibe-knowledge" / "SKILL.md").read_text(encoding="utf-8")
    assert "Do not auto-run `sync --apply`" in knowledge or "never auto-run" in knowledge.lower()
    assert "**no**" in knowledge and "sync --apply" in knowledge
    implementation = (SKILLS_ROOT / "vibe-implementation" / "SKILL.md").read_text(encoding="utf-8")
    assert "Never run `bd init`" in implementation or "never auto-run" in implementation.lower()
    front = (SKILLS_ROOT / "vibe-control" / "SKILL.md").read_text(encoding="utf-8")
    assert "Never call NotebookLM directly" in front or "Never call NotebookLM" in front
    assert "Never call `bd` directly" in front
    assert "Never auto-run `--apply`" in front or "Never auto-run" in front
