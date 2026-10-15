#!/usr/bin/env python3
"""Phase 3 acceptance runner — local integration bootstrap.

Does not require NotebookLM auth success or Beads installation.
Commands must degrade gracefully and emit valid JSON envelopes.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PHASE3_DIR = Path(__file__).resolve().parent
REPO_ROOT = PHASE3_DIR.parents[1]


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


def run_cli(args: list[str]) -> tuple[int, dict[str, Any] | None, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "vibe_control", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    stdout = (proc.stdout or "").strip()
    if not stdout:
        return proc.returncode, None, f"empty stdout; stderr={(proc.stderr or '').strip()}"
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return proc.returncode, None, f"invalid JSON: {exc}"
    return proc.returncode, payload, ""


def check_json_command(name: str, args: list[str], *, allow_fail: bool = True) -> CheckResult:
    code, payload, err = run_cli(args)
    if err:
        return CheckResult(name, False, err)
    if payload is None:
        return CheckResult(name, False, "missing payload")
    if "ok" not in payload or "command" not in payload:
        return CheckResult(name, False, "envelope missing ok/command")
    if not allow_fail and (code != 0 or not payload.get("ok")):
        return CheckResult(name, False, f"expected success, got code={code}")
    # Graceful degradation is success for Phase 3 acceptance
    detail = f"ok={payload.get('ok')} code={code}"
    if payload.get("error"):
        detail += f" error={payload['error'].get('code')}"
    return CheckResult(name, True, detail)


def main() -> int:
    print("Vibe Control Phase 3 Acceptance")
    print(f"repo: {REPO_ROOT}")
    print()

    checks = [
        check_json_command("integration status", ["integration", "status", "--json"], allow_fail=False),
        check_json_command("integration doctor", ["integration", "doctor", "--json"], allow_fail=False),
        check_json_command("knowledge auth-status", ["knowledge", "auth-status", "--json"]),
        check_json_command("knowledge login-guide", ["knowledge", "login-guide", "--json"], allow_fail=False),
        check_json_command("task install-guide", ["task", "install-guide", "--json"], allow_fail=False),
        check_json_command("task init-preview", ["task", "init-preview", "--json"]),
        check_json_command("skills status", ["skills", "status", "--json"], allow_fail=False),
        check_json_command(
            "skills install dry-run",
            ["skills", "install", "--dry-run", "--json"],
            allow_fail=False,
        ),
    ]

    # Structural assertions for integration status
    code, payload, err = run_cli(["integration", "status", "--json"])
    if payload and payload.get("ok"):
        nlm = (payload.get("data") or {}).get("notebooklm") or {}
        if nlm.get("safe_to_sync") is True:
            checks.append(CheckResult("safe_to_sync false", False, "safe_to_sync unexpectedly true"))
        else:
            checks.append(CheckResult("safe_to_sync false", True, "safe_to_sync=false"))
    else:
        checks.append(CheckResult("safe_to_sync false", False, err or "integration status failed"))

    width = max(len(c.name) for c in checks)
    failed = 0
    for check in checks:
        mark = "PASS" if check.ok else "FAIL"
        if not check.ok:
            failed += 1
        print(f"[{mark}] {check.name:<{width}}  {check.detail}")

    print()
    if failed:
        print(f"Phase 3 acceptance FAILED ({failed} check(s))")
        return 1
    print("Phase 3 acceptance PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
