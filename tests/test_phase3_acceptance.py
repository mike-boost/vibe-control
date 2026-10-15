"""Phase 3 acceptance coverage."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PHASE3 = REPO_ROOT / "acceptance" / "phase3"
RUNNER = PHASE3 / "run_phase3_acceptance.py"
REPORT = PHASE3 / "PHASE3_ACCEPTANCE_REPORT.md"
PHASE2_RUNNER = REPO_ROOT / "acceptance" / "phase2" / "run_phase2_acceptance.py"


def test_phase3_acceptance_script_exits_zero():
    proc = subprocess.run(
        [sys.executable, str(RUNNER)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
    assert "Phase 3 acceptance PASSED" in proc.stdout


def test_phase3_report_has_spec_alignment_table():
    text = REPORT.read_text(encoding="utf-8")
    assert "# Phase 3 Acceptance Report" in text
    assert "## Spec Alignment" in text
    assert "Repository is SSOT" in text
    assert "No source mutation by default" in text


def test_phase2_acceptance_still_passes():
    proc = subprocess.run(
        [sys.executable, str(PHASE2_RUNNER)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
