"""Phase 7 test execution contract and gate safety tests."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[1]


def test_agents_references_test_execution_contract():
    agents = (REPO / "AGENTS.md").read_text(encoding="utf-8")
    assert "docs/harness/test-execution-contract.md" in agents


def test_test_execution_contract_exists():
    path = REPO / "docs/harness/test-execution-contract.md"
    text = path.read_text(encoding="utf-8").lower()
    assert path.is_file()
    assert "fast" in text
    assert "serial" in text
    assert "acceptance" in text
    assert "pytest-xdist" in text or "xdist" in text
    assert "mutation" in text
    assert "observed-runtime" in text or "update_acceptance_observed" in text
    assert "nlm" in text or "notebooklm" in text


def test_pytest_config_defines_required_markers():
    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    for marker in (
        "unit",
        "integration",
        "acceptance",
        "real_notebooklm",
        "serial",
        "slow",
        "mutation",
    ):
        assert marker in text


def test_fast_script_uses_xdist_and_excludes_risky_markers():
    text = (REPO / "scripts/test-fast.sh").read_text(encoding="utf-8")
    assert "-n auto" in text
    assert "--dist=loadscope" in text
    assert "not serial" in text
    assert "not real_notebooklm" in text
    assert "not acceptance" in text
    assert "not slow" in text
    assert "not mutation" in text


def test_full_gate_does_not_run_mutation_acceptance():
    wrapper = (REPO / "scripts/test-full-readonly.sh").read_text(encoding="utf-8")
    local = (REPO / "scripts/test-full-local-readonly.sh").read_text(encoding="utf-8")
    assert "test-full-local-readonly.sh" in wrapper
    assert "VIBE_ACCEPTANCE_LOCAL=1" in local
    assert "test-acceptance-readonly.sh" in local
    assert "run_phase6_acceptance.py --" not in local
    acc = (REPO / "scripts/test-acceptance-readonly.sh").read_text(encoding="utf-8")
    assert "run_phase6_acceptance.py" in acc
    assert re.search(
        r'acceptance/phase6/run_phase6_acceptance\.py"?\s*$',
        acc,
        re.M,
    )
    assert "run_phase6_acceptance.py --real-smoke" not in acc
    assert "run_phase6_acceptance.py --apply" not in acc


def test_phase6_default_is_readonly_and_real_smoke_needs_flags():
    runner = REPO / "acceptance/phase6/run_phase6_acceptance.py"
    text = runner.read_text(encoding="utf-8")
    assert "--real-smoke" in text
    assert "read-only" in text.lower() or "readonly" in text.lower().replace("-", "")
    proc = subprocess.run(
        [sys.executable, str(runner), "--apply"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0
    assert "REFUSED" in (proc.stderr or proc.stdout)
    proc2 = subprocess.run(
        [sys.executable, str(runner), "--real-smoke"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc2.returncode != 0


def test_xdist_is_dev_dependency_not_runtime():
    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    runtime = text.split("[project.optional-dependencies]")[0]
    assert "pytest-xdist" not in runtime
    assert "pytest-xdist" in text
    assert "dev = [" in text


def test_acceptance_modules_are_marked_serial():
    conf = (REPO / "tests/conftest.py").read_text(encoding="utf-8")
    assert "test_phase2_acceptance.py" in conf
    assert "test_phase3_acceptance.py" in conf
    assert "pytest.mark.serial" in conf
    assert "pytest.mark.acceptance" in conf


def test_phase7_reports_have_no_raw_ids():
    report = REPO / "acceptance/phase7/TEST_EXECUTION_SPEED_REPORT.md"
    if not report.is_file():
        pytest.skip("report not written yet")
    text = report.read_text(encoding="utf-8")
    assert '"notebook_ref"' not in text
    assert '"provider_source_id"' not in text
    assert not re.search(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        text,
        re.I,
    )


def test_gate_scripts_exist_and_are_executable_bits_or_bash():
    for name in (
        "test-fast.sh",
        "test-serial.sh",
        "test-acceptance-readonly.sh",
        "test-full-readonly.sh",
        "test-closeout-local-fast.sh",
        "test-full-local-readonly.sh",
        "test-nlm-readonly-smoke.sh",
    ):
        path = REPO / "scripts" / name
        assert path.is_file()
        assert path.read_text(encoding="utf-8").startswith("#!/usr/bin/env bash")
