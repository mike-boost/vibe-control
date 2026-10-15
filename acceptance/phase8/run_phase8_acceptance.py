#!/usr/bin/env python3
"""Phase 8 acceptance: readonly contract + unit/integration pytest (no NotebookLM mutation)."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


PHASE8 = Path(__file__).resolve().parent
REPO_ROOT = PHASE8.parents[1]
sys.path.insert(0, str(REPO_ROOT / "acceptance"))
from lib.observed_output import save_observed  # noqa: E402

SPEC = REPO_ROOT / "docs" / "project" / "sync" / "phase8-ssot-snapshot-ack-sync-spec.md"


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


def save(name: str, payload: dict) -> None:
    save_observed(PHASE8, name, payload)


def main() -> int:
    print("Vibe Control Phase 8 Acceptance (readonly)")
    print(f"repo: {REPO_ROOT}")
    print()
    checks: list[CheckResult] = []

    checks.append(CheckResult("phase8 formal spec", SPEC.is_file(), SPEC.as_posix()))
    if SPEC.is_file():
        text = SPEC.read_text(encoding="utf-8")
        required = [
            "Notebook-Scoped Binding Receipt",
            "target_key_hash",
            "switch receipt",
            "Only provider binding metadata was reindexed",
            "auth_profile_hash = null",
        ]
        soft = [
            "ProviderTarget",
            "remote_ack",
            "TARGET_MISMATCH",
            "reindex-bindings",
            "upload_filename",
            "Phase 8.0 Test Spec",
            "P8-CLI-01",
        ]
        missing = [p for p in required + soft if p not in text]
        checks.append(
            CheckResult(
                "spec key phrases",
                len(missing) == 0,
                "ok" if not missing else f"missing={missing}",
            )
        )

    report = PHASE8 / "PHASE8_SSOT_SYNC_REPORT.md"
    checks.append(CheckResult("phase8 report", report.is_file(), "exists"))

    pytest_bin = REPO_ROOT / ".venv" / "bin" / "pytest"
    cmd = [
        str(pytest_bin if pytest_bin.is_file() else "pytest"),
        "-q",
        "tests/test_phase8_provider_target.py",
        "tests/test_phase8_snapshot.py",
        "tests/test_phase8_receipt_scope.py",
        "tests/test_phase8_sync_status.py",
        "tests/test_phase8_lifecycle.py",
        "tests/test_phase8_reindex.py",
        "tests/test_phase8_contract.py",
        "tests/test_phase8_cli.py",
        "tests/test_phase8_wiring.py",
    ]
    proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    out = (proc.stdout or "") + (proc.stderr or "")
    checks.append(
        CheckResult(
            "phase8 pytest unit+integration",
            proc.returncode == 0,
            out.strip().splitlines()[-1] if out.strip() else f"exit={proc.returncode}",
        )
    )
    save(
        "phase8-pytest.json",
        {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "tail": out.strip().splitlines()[-20:],
        },
    )

    # Explicit non-mutation guarantee for this acceptance entrypoint
    checks.append(
        CheckResult(
            "no real notebooklm mutation flags",
            True,
            "acceptance harness does not pass --apply/--allow-add/--real-smoke",
        )
    )

    print("Checks:")
    failed = 0
    for c in checks:
        mark = "PASS" if c.ok else "FAIL"
        print(f"  [{mark}] {c.name}: {c.detail}")
        if not c.ok:
            failed += 1
    print()
    if failed:
        print(f"Phase 8 acceptance FAILED ({failed} check(s))")
        return 1
    print("Phase 8 acceptance PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
