"""Acceptance wrapper for Phase 8 readonly harness."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "acceptance" / "phase8" / "run_phase8_acceptance.py"


@pytest.mark.acceptance
@pytest.mark.serial
@pytest.mark.slow
def test_phase8_acceptance_readonly():
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
