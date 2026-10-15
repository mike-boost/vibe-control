"""Skills install/status tests — symlink-first, fake HOME via VIBE_SKILLS_ROOT."""

from __future__ import annotations

import json
from pathlib import Path

from vibe_control.cli import main
from vibe_control.skills_manager import (
    install_skills,
    package_skills_root,
    skills_readiness,
    skills_status,
)


def test_skills_status_not_installed(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("VIBE_SKILLS_ROOT", str(tmp_path / "skills"))
    code = main(["skills", "status", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["data"]["installed"] is False
    assert payload["data"]["preferred_mode"] == "symlink"
    assert all(s["install_mode"] == "missing" for s in payload["data"]["skills"])


def test_skills_install_dry_run_reports_symlink(tmp_path, monkeypatch, capsys):
    root = tmp_path / "skills"
    monkeypatch.setenv("VIBE_SKILLS_ROOT", str(root))
    code = main(["skills", "install", "--dry-run", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["data"]["dry_run"] is True
    assert payload["data"]["mode"] == "symlink"
    assert len(payload["data"]["operations"]) == 3
    assert all(op["action"] == "symlink" for op in payload["data"]["operations"])
    assert {op["skill"] for op in payload["data"]["operations"]} == {
        "vibe-control",
        "vibe-knowledge",
        "vibe-implementation",
    }
    assert not (root / "vibe-knowledge").exists()


def test_skills_install_creates_symlinks(tmp_path, monkeypatch, capsys):
    root = tmp_path / "skills"
    unrelated = root / "other-skill" / "SKILL.md"
    unrelated.parent.mkdir(parents=True)
    unrelated.write_text("keep me", encoding="utf-8")
    monkeypatch.setenv("VIBE_SKILLS_ROOT", str(root))

    code = main(["skills", "install", "--apply", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["data"]["mode"] == "symlink"

    knowledge = root / "vibe-knowledge"
    implementation = root / "vibe-implementation"
    front = root / "vibe-control"
    assert knowledge.is_symlink()
    assert implementation.is_symlink()
    assert front.is_symlink()
    assert knowledge.resolve() == (package_skills_root() / "vibe-knowledge").resolve()
    assert front.resolve() == (package_skills_root() / "vibe-control").resolve()
    assert unrelated.read_text(encoding="utf-8") == "keep me"

    status = skills_status(install_root=root)
    assert status["installed"] is True
    for skill in status["skills"]:
        assert skill["install_mode"] == "symlink"
        assert skill["target_is_symlink"] is True
        assert skill["points_to_source"] is True
        assert skill["content_matches"] is True


def test_skills_status_detects_symlinks(tmp_path, monkeypatch, capsys):
    root = tmp_path / "skills"
    monkeypatch.setenv("VIBE_SKILLS_ROOT", str(root))
    install_skills(install_root=root, mode="symlink")
    code = main(["skills", "status", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["data"]["installed"] is True
    assert all(s["points_to_source"] is True for s in payload["data"]["skills"])


def test_existing_correct_symlink_is_noop(tmp_path, monkeypatch, capsys):
    root = tmp_path / "skills"
    monkeypatch.setenv("VIBE_SKILLS_ROOT", str(root))
    install_skills(install_root=root, mode="symlink")
    code = main(["skills", "install", "--apply", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert all(op.get("noop") or op.get("result") == "noop" for op in payload["data"]["operations"])


def test_mismatched_symlink_refused_without_force(tmp_path, monkeypatch, capsys):
    root = tmp_path / "skills"
    root.mkdir(parents=True)
    wrong = tmp_path / "other-source"
    wrong.mkdir()
    (wrong / "SKILL.md").write_text("wrong", encoding="utf-8")
    target = root / "vibe-knowledge"
    target.symlink_to(wrong, target_is_directory=True)
    monkeypatch.setenv("VIBE_SKILLS_ROOT", str(root))

    code = main(["skills", "install", "--apply", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["error"]["code"] == "SKILL_TARGET_EXISTS"
    assert target.is_symlink()
    assert target.resolve() == wrong.resolve()


def test_copied_directory_reported_as_copy_with_warning(tmp_path, monkeypatch):
    root = tmp_path / "skills"
    source = package_skills_root() / "vibe-knowledge"
    target = root / "vibe-knowledge"
    target.mkdir(parents=True)
    (target / "SKILL.md").write_text(
        (source / "SKILL.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    status = skills_status(install_root=root)
    knowledge = next(s for s in status["skills"] if s["name"] == "vibe-knowledge")
    assert knowledge["install_mode"] == "copy"
    assert knowledge["target_is_symlink"] is False
    assert any("symlink" in w.lower() for w in knowledge["warnings"])
    assert status["installed"] is False


def test_unrelated_skills_not_touched(tmp_path, monkeypatch, capsys):
    root = tmp_path / "skills"
    keep = root / "chrome-dev-layout-review" / "SKILL.md"
    keep.parent.mkdir(parents=True)
    keep.write_text("unrelated", encoding="utf-8")
    monkeypatch.setenv("VIBE_SKILLS_ROOT", str(root))
    code = main(["skills", "install", "--apply", "--json"])
    assert code == 0
    assert keep.read_text(encoding="utf-8") == "unrelated"
    assert set(p.name for p in root.iterdir()) >= {
        "chrome-dev-layout-review",
        "vibe-control",
        "vibe-knowledge",
        "vibe-implementation",
    }


def test_force_replaces_mismatch_with_symlink(tmp_path, monkeypatch, capsys):
    root = tmp_path / "skills"
    monkeypatch.setenv("VIBE_SKILLS_ROOT", str(root))
    for name in ("vibe-control", "vibe-knowledge", "vibe-implementation"):
        d = root / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text("stale copy", encoding="utf-8")

    code = main(["skills", "install", "--force", "--apply", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    for name in ("vibe-control", "vibe-knowledge", "vibe-implementation"):
        target = root / name
        assert target.is_symlink()
        assert target.resolve() == (package_skills_root() / name).resolve()


def test_skills_install_no_flag_fails_closed(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("VIBE_SKILLS_ROOT", str(tmp_path / "skills"))
    code = main(["skills", "install", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["error"]["code"] == "SKILLS_INSTALL_REQUIRES_DRY_RUN_OR_APPLY"


def test_skills_readiness_missing_and_mismatch(tmp_path, monkeypatch):
    root = tmp_path / "skills"
    monkeypatch.setenv("VIBE_SKILLS_ROOT", str(root))
    missing = skills_readiness(install_root=root)
    assert missing["condition"] == "missing"
    assert missing["installed"] is False
    assert "vibe skills install --apply --json" in missing["next_actions"]

    wrong = tmp_path / "other"
    wrong.mkdir()
    (wrong / "SKILL.md").write_text("x", encoding="utf-8")
    root.mkdir(parents=True)
    for name in ("vibe-control", "vibe-knowledge", "vibe-implementation"):
        (root / name).symlink_to(wrong, target_is_directory=True)
    mismatched = skills_readiness(install_root=root)
    assert mismatched["condition"] == "mismatch"
    assert "vibe skills install --apply --force --json" in mismatched["next_actions"]

    install_skills(install_root=root, mode="symlink", force=True)
    aligned = skills_readiness(install_root=root)
    assert aligned["condition"] == "aligned"
    assert aligned["installed"] is True
    assert aligned["next_actions"] == []
