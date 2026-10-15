#!/usr/bin/env python3
"""Phase 5 acceptance: sync lifecycle checks (no real replace smoke)."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PHASE5 = Path(__file__).resolve().parent
REPO_ROOT = PHASE5.parents[1]
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
    save_observed(PHASE5, name, payload)


def main() -> int:
    print("Vibe Control Phase 5 Acceptance")
    print(f"repo: {REPO_ROOT}")
    if acceptance_local_mode():
        print("mode: VIBE_ACCEPTANCE_LOCAL (skip real NotebookLM remote calls)")
    print()
    checks: list[CheckResult] = []
    ops: list[dict[str, Any]] = []

    report = PHASE5 / "PHASE5_SYNC_LIFECYCLE_REPORT.md"
    checks.append(CheckResult("phase5 report", report.is_file(), "exists"))
    closeout = PHASE5 / "PHASE5_CLOSEOUT_AUDIT.md"
    checks.append(CheckResult("phase5 closeout audit", closeout.is_file(), "exists"))
    hist = PHASE5 / "observed"
    checks.append(CheckResult("observed dir", hist.is_dir(), "historical tracked observed exists"))

    code, payload, err = run_cli(["knowledge", "receipt", "status", "--json"])
    present = bool(payload and payload.get("ok") and (payload.get("data") or {}).get("present"))
    checks.append(CheckResult("receipt status", bool(payload and payload.get("ok")), err or f"present={present}"))
    if payload:
        save("acceptance-receipt-status.json", payload)

    if acceptance_local_mode():
        for name, out in (
            ("remote-inventory", "acceptance-remote-inventory.json"),
            ("sync dry-run", "acceptance-sync-dry-run.json"),
            ("retry dry-run", "acceptance-retry-dry-run.json"),
            ("rebuild dry-run", "acceptance-rebuild-dry-run.json"),
        ):
            checks.append(CheckResult(name, True, "skipped: VIBE_ACCEPTANCE_LOCAL"))
            save(out, {"ok": True, "skipped": True, "reason": "VIBE_ACCEPTANCE_LOCAL"})
    else:
        code, payload, err = run_cli(["knowledge", "remote-inventory", "--notebook", "OPM-test", "--json"])
        ok = bool(payload and payload.get("ok"))
        items = ((payload or {}).get("data") or {}).get("items") or []
        checks.append(CheckResult("remote-inventory", ok, err or f"items={len(items)}"))
        if payload:
            save("acceptance-remote-inventory.json", payload)

        code, payload, err = run_cli(["knowledge", "sync", "--notebook", "OPM-test", "--dry-run", "--json"])
        ops = ((payload or {}).get("data") or {}).get("operations") or []
        already = all(op.get("op") == "already_current" for op in ops) if ops else False
        checks.append(
            CheckResult(
                "sync dry-run",
                bool(payload and payload.get("ok")),
                err or f"ops={[(o.get('op'), o.get('doc_id')) for o in ops]} already_current={already}",
            )
        )
        if payload:
            save("acceptance-sync-dry-run.json", payload)

        code, payload, err = run_cli(["knowledge", "retry", "--notebook", "OPM-test", "--dry-run", "--json"])
        checks.append(CheckResult("retry dry-run", bool(payload and payload.get("ok")), err or "ok"))
        if payload:
            save("acceptance-retry-dry-run.json", payload)

        code, payload, err = run_cli(["knowledge", "rebuild", "--notebook", "OPM-test", "--dry-run", "--json"])
        checks.append(CheckResult("rebuild dry-run", bool(payload and payload.get("ok")), err or "ok"))
        if payload:
            save("acceptance-rebuild-dry-run.json", payload)

    code, payload, err = run_cli(["knowledge", "receipt", "inspect", "--json"])
    checks.append(CheckResult("receipt inspect", bool(payload and payload.get("ok")), err or "ok"))
    if payload:
        save("acceptance-receipt-inspect.json", payload)

    mutate_ops = {op.get("op") for op in ops} & {"delete", "update", "clean"}
    checks.append(CheckResult("dry-run no broad mutate", not mutate_ops, f"mutate_ops={sorted(mutate_ops)}"))

    width = max(len(c.name) for c in checks)
    failed = 0
    for check in checks:
        mark = "PASS" if check.ok else "FAIL"
        if not check.ok:
            failed += 1
        print(f"[{mark}] {check.name:<{width}}  {check.detail}")
    print()
    if failed:
        print(f"Phase 5 acceptance FAILED ({failed} check(s))")
        return 1
    print("Phase 5 acceptance PASSED")
    print("NOTE: this runner does not execute sync --apply or real replacement")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
