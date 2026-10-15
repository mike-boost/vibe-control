"""Unit tests for scripts/extract-release-notes.py."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "extract-release-notes.py"


def _load():
    spec = importlib.util.spec_from_file_location("extract_release_notes", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_extract_section_isolates_one_version():
    mod = _load()
    changelog = """# Changelog

## [0.5.2] — internal

Tag: `v0.5.2`.

### Added

- two

## [0.5.1] — internal

Tag: `v0.5.1`.

### Added

- one
"""
    section = mod.extract_section(changelog, "0.5.1")
    assert "one" in section
    assert "two" not in section
    assert "0.5.2" not in section


def test_format_github_notes_has_summary_and_install():
    mod = _load()
    notes = mod.format_github_notes(
        version="0.5.1",
        section="Tag: `v0.5.1`.\n\n### Added\n\n- one\n",
    )
    assert notes.startswith("## Summary\n")
    assert "### Added" in notes
    assert "git checkout v0.5.1" in notes
    assert "Tag:" not in notes
    assert "CHANGELOG.md" in notes


def test_live_changelog_has_extractable_latest():
    mod = _load()
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    # Latest section in file must extract without error
    first = text.split("## [", 1)[1].split("]", 1)[0]
    section = mod.extract_section(text, first)
    assert section.strip()
    notes = mod.format_github_notes(version=first, section=section)
    assert f"git checkout v{first}" in notes
