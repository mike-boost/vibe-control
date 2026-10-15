#!/usr/bin/env python3
"""Phase 4F acceptance: harness lifecycle read-only checks (no --allow-add)."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PHASE4F = Path(__file__).resolve().parent
REPO_ROOT = PHASE4F.parents[1]
sys.path.insert(0, str(REPO_ROOT / "acceptance"))
from lib.observed_output import acceptance_local_mode, save_observed  # noqa: E402


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
        return proc.returncode, None, f"empty stdout stderr={(proc.stderr or '')[:200]}"
    try:
        return proc.returncode, json.loads(stdout), ""
    except json.JSONDecodeError as exc:
        return proc.returncode, None, f"invalid json: {exc}"


def save(name: str, payload: dict[str, Any]) -> None:
    save_observed(PHASE4F, name, payload)


def main() -> int:
    print("Vibe Control Phase 4F Acceptance")
    print(f"repo: {REPO_ROOT}")
    if acceptance_local_mode():
        print("mode: VIBE_ACCEPTANCE_LOCAL (skip real NotebookLM remote calls)")
    print()
    checks: list[CheckResult] = []

    agents = REPO_ROOT / "AGENTS.md"
    checks.append(CheckResult("AGENTS.md", agents.is_file(), "exists"))
    for rel in (
        "docs/harness/knowledge-provider-boundary.md",
        "docs/harness/notebooklm-source-lifecycle-contract.md",
        "docs/harness/receipt-state-contract.md",
    ):
        path = REPO_ROOT / rel
        checks.append(CheckResult(rel, path.is_file(), "exists"))

    code, payload, err = run_cli(["knowledge", "receipt", "status", "--json"])
    ok = bool(payload and payload.get("ok"))
    checks.append(CheckResult("receipt status", ok, err or f"present={(payload or {}).get('data', {}).get('present')}"))
    if payload:
        save("receipt-status-before.json", payload)

    if acceptance_local_mode():
        for name, out in (
            ("remote-inventory", "remote-inventory-before.json"),
            ("sync-preview", "sync-preview.json"),
            ("seed-dry-run", "seed-dry-run.json"),
        ):
            checks.append(CheckResult(name, True, "skipped: VIBE_ACCEPTANCE_LOCAL"))
            save(out, {"ok": True, "skipped": True, "reason": "VIBE_ACCEPTANCE_LOCAL"})
    else:
        code, payload, err = run_cli(["knowledge", "remote-inventory", "--notebook", "OPM-test", "--json"])
        ok = bool(payload and (payload.get("ok") or (payload.get("error") or {}).get("code")))
        checks.append(CheckResult("remote-inventory", ok, err or "ok-or-graceful"))
        if payload:
            save("remote-inventory-before.json", payload)

        code, payload, err = run_cli(["knowledge", "sync-preview", "--notebook", "OPM-test", "--json"])
        ok = bool(payload and payload.get("ok"))
        summary = ((payload or {}).get("data") or {}).get("summary")
        ops = ((payload or {}).get("data") or {}).get("operations") or []
        no_mutate = not any(op.get("op") in {"delete", "update", "clean"} for op in ops)
        checks.append(CheckResult("sync-preview", ok and no_mutate, f"summary={summary} no_mutate={no_mutate}"))
        if payload:
            save("sync-preview.json", payload)

        code, payload, err = run_cli(
            ["knowledge", "seed-test-sources", "--notebook", "OPM-test", "--dry-run", "--json"]
        )
        ok = bool(payload and payload.get("ok"))
        checks.append(CheckResult("seed-dry-run", ok, err or "dry-run"))
        if payload:
            save("seed-dry-run.json", payload)

    code, payload, err = run_cli(["knowledge", "receipt", "status", "--json"])
    if payload:
        save("receipt-status-after.json", payload)
    checks.append(CheckResult("receipt status after", bool(payload and payload.get("ok")), "ok"))

    width = max(len(c.name) for c in checks)
    failed = 0
    for check in checks:
        mark = "PASS" if check.ok else "FAIL"
        if not check.ok:
            failed += 1
        print(f"[{mark}] {check.name:<{width}}  {check.detail}")
    print()
    if failed:
        print(f"Phase 4F acceptance FAILED ({failed} check(s))")
        return 1
    print("Phase 4F acceptance PASSED")
    print("NOTE: this runner never executes seed-test-sources --allow-add")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
