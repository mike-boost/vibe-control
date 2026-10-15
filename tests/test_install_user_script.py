"""User installer script exists and is documented as the no-pipx path."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "install-user.sh"


def test_install_user_script_is_executable():
    assert INSTALLER.is_file()
    mode = INSTALLER.stat().st_mode
    assert mode & stat.S_IXUSR


def test_install_user_help():
    out = subprocess.check_output([str(INSTALLER), "--help"], text=True)
    assert "upgrade" in out.lower()
    assert "uninstall" in out.lower()
    assert "status" in out.lower()
    assert "recreate" in out.lower()
    assert "VIBE_SKIP_SKILLS" in out


def test_install_upgrade_status_uninstall_in_temp_prefix(tmp_path: Path):
    prefix = tmp_path / ".local"
    skills_root = tmp_path / "agents-skills"
    env = {
        **os.environ,
        "VIBE_USER_PREFIX": str(prefix),
        "VIBE_SKILLS_ROOT": str(skills_root),
    }
    subprocess.check_call([str(INSTALLER)], cwd=ROOT, env=env)
    vibe = prefix / "bin" / "vibe"
    assert vibe.is_symlink() or vibe.is_file()
    ver1 = subprocess.check_output([str(vibe), "--version"], text=True)
    assert "vibe-control" in ver1
    assert (skills_root / "vibe-knowledge").is_symlink()

    # Second run is upgrade path.
    subprocess.check_call([str(INSTALLER), "--upgrade"], cwd=ROOT, env=env)
    ver2 = subprocess.check_output([str(vibe), "--version"], text=True)
    assert "vibe-control" in ver2

    status = subprocess.check_output([str(INSTALLER), "--status"], cwd=ROOT, env=env, text=True)
    assert "venv:" in status
    assert str(prefix) in status or "link:" in status

    subprocess.check_call([str(INSTALLER), "--uninstall"], cwd=ROOT, env=env)
    assert not vibe.exists()


def test_install_can_skip_skills(tmp_path: Path):
    prefix = tmp_path / ".local"
    skills_root = tmp_path / "agents-skills"
    env = {
        **os.environ,
        "VIBE_USER_PREFIX": str(prefix),
        "VIBE_SKILLS_ROOT": str(skills_root),
        "VIBE_SKIP_SKILLS": "1",
    }
    subprocess.check_call([str(INSTALLER)], cwd=ROOT, env=env)
    assert not (skills_root / "vibe-knowledge").exists()


def test_readme_leads_with_source_installer():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "./scripts/install-user.sh" in readme
    assert readme.index("./scripts/install-user.sh") < readme.index("pipx install")
    assert "--upgrade" in readme or "upgrade" in readme.lower()
