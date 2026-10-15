"""TDD: Skill Assay typed checks reject arbitrary shell (red first)."""

from __future__ import annotations

from pathlib import Path

import pytest

from vibe_control.skill_assay.checks import run_typed_checks
from vibe_control.skill_assay.errors import SkillAssayError
from vibe_control.skill_assay.scenario import load_scenario


def test_scenario_rejects_shell_probe(tmp_path: Path) -> None:
    path = tmp_path / "scenario.yaml"
    path.write_text(
        "schema: vibe.skill_assay.scenario.v1\n"
        "prompt: do thing\n"
        "checks:\n"
        "  - kind: shell\n"
        "    command: rm -rf /\n",
        encoding="utf-8",
    )
    with pytest.raises(SkillAssayError) as exc:
        load_scenario(path)
    assert exc.value.code == "SKILL_ASSAY_CHECK_KIND_INVALID"


def test_file_exists_check(tmp_path: Path) -> None:
    art = tmp_path / "artifact"
    art.mkdir()
    (art / "out.json").write_text("{}\n", encoding="utf-8")
    results = run_typed_checks(
        [{"kind": "file_exists", "path": "out.json"}],
        artifact_dir=art,
    )
    assert results == [
        {
            "fact_id": "checks[0]",
            "kind": "file_exists",
            "path": "out.json",
            "pass": True,
        }
    ]


def test_assistant_text_match(tmp_path: Path) -> None:
    art = tmp_path / "artifact"
    art.mkdir()
    results = run_typed_checks(
        [{"kind": "assistant_text_match", "contains": "Mode: execute"}],
        artifact_dir=art,
        assistant_text="Mode: execute\n## Status\nok\n",
    )
    assert results[0]["pass"] is True
    assert results[0]["fact_id"] == "checks[0]"


def test_file_exists_rejects_path_escape(tmp_path: Path) -> None:
    art = tmp_path / "artifact"
    art.mkdir()
    with pytest.raises(SkillAssayError) as exc:
        run_typed_checks(
            [{"kind": "file_exists", "path": "../secret.txt"}],
            artifact_dir=art,
        )
    assert exc.value.code == "SKILL_ASSAY_PATH_ESCAPE"
