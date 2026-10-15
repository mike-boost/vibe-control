#!/usr/bin/env python3
"""Phase 6 acceptance: replace smoke evidence checks (read-only by default)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PHASE6 = Path(__file__).resolve().parent
REPO_ROOT = PHASE6.parents[1]
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
    save_observed(PHASE6, name, payload)


def run_readonly_audit() -> int:
    print("Vibe Control Phase 6 Acceptance (read-only)")
    print(f"repo: {REPO_ROOT}")
    if acceptance_local_mode():
        print("mode: VIBE_ACCEPTANCE_LOCAL (skip real NotebookLM remote calls)")
    print()
    checks: list[CheckResult] = []

    report = PHASE6 / "PHASE6_REAL_REPLACE_SMOKE_REPORT.md"
    hist = PHASE6 / "observed"
    checks.append(CheckResult("phase6 report", report.is_file(), "exists"))
    checks.append(CheckResult("observed dir", hist.is_dir(), "historical tracked observed exists"))
    apply_obs = hist / "smoke-replace-apply.json"
    checks.append(CheckResult("apply evidence", apply_obs.is_file(), "exists"))

    if acceptance_local_mode():
        for name, out in (
            ("smoke dry-run", "acceptance-smoke-dry-run.json"),
            ("final inventory", "acceptance-remote-inventory.json"),
            ("sync dry-run", "acceptance-sync-dry-run.json"),
        ):
            checks.append(CheckResult(name, True, "skipped: VIBE_ACCEPTANCE_LOCAL"))
            save(out, {"ok": True, "skipped": True, "reason": "VIBE_ACCEPTANCE_LOCAL"})
    else:
        code, payload, err = run_cli(
            ["knowledge", "smoke", "replace", "--notebook", "OPM-test", "--dry-run", "--json"]
        )
        ok = bool(payload and payload.get("ok"))
        hashes = bool((payload or {}).get("data", {}).get("hashes_differ"))
        checks.append(CheckResult("smoke dry-run", ok and hashes, err or f"hashes_differ={hashes}"))
        if payload:
            save("acceptance-smoke-dry-run.json", payload)

        code, payload, err = run_cli(["knowledge", "remote-inventory", "--notebook", "OPM-test", "--json"])
        items = ((payload or {}).get("data") or {}).get("items") or []
        titles = {i.get("title") for i in items}
        checks.append(
            CheckResult(
                "final inventory",
                bool(payload and payload.get("ok") and isinstance(items, list)),
                err or f"titles={sorted(t for t in titles if t)} count={len(items)}",
            )
        )
        if payload:
            save("acceptance-remote-inventory.json", payload)

        code, payload, err = run_cli(["knowledge", "sync", "--notebook", "OPM-test", "--dry-run", "--json"])
        summary = ((payload or {}).get("data") or {}).get("summary") or {}
        dry_ok = bool(payload and payload.get("ok") is True)
        mutation = payload.get("mutation") if payload else None
        if mutation is None and payload:
            mutation = ((payload.get("data") or {}).get("mutation"))
        checks.append(
            CheckResult(
                "sync dry-run",
                dry_ok and mutation is not True,
                err or f"summary={summary} mutation={mutation}",
            )
        )
        if payload:
            save("acceptance-sync-dry-run.json", payload)

    code, payload, err = run_cli(["knowledge", "receipt", "status", "--json"])
    present = bool(payload and (payload.get("data") or {}).get("present"))
    count = ((payload or {}).get("data") or {}).get("document_count")
    checks.append(
        CheckResult(
            "production receipt",
            bool(payload and payload.get("ok") and present and isinstance(count, int) and count >= 1),
            err or f"present={present} document_count={count}",
        )
    )
    if payload:
        save("acceptance-receipt-status.json", payload)

    width = max(len(c.name) for c in checks)
    failed = 0
    for check in checks:
        mark = "PASS" if check.ok else "FAIL"
        if not check.ok:
            failed += 1
        print(f"[{mark}] {check.name:<{width}}  {check.detail}")
    print()
    if failed:
        print(f"Phase 6 acceptance FAILED ({failed} check(s))")
        return 1
    print("Phase 6 acceptance PASSED")
    print("NOTE: default runner is read-only; real smoke requires --real-smoke --apply")
    return 0


def run_real_smoke() -> int:
    print("Vibe Control Phase 6 REAL SMOKE (mutation)")
    print("Requires explicit --real-smoke --apply")
    code, payload, err = run_cli(
        [
            "knowledge",
            "smoke",
            "replace",
            "--notebook",
            "OPM-test",
            "--apply",
            "--cleanup",
            "--json",
        ]
    )
    if not payload:
        print(f"[FAIL] real smoke  {err}")
        return 1
    save("smoke-replace-apply-rerun.json", payload)
    if not payload.get("ok"):
        print(f"[FAIL] real smoke  {payload.get('error')}")
        return 1
    print("[PASS] real smoke apply+cleanup")
    return run_readonly_audit()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Phase 6 acceptance (read-only by default; real smoke is opt-in)"
    )
    parser.add_argument(
        "--real-smoke",
        action="store_true",
        help="Acknowledge intentional real NotebookLM smoke mutation",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="With --real-smoke, run knowledge smoke replace --apply --cleanup",
    )
    args = parser.parse_args(argv)

    if args.apply and not args.real_smoke:
        print(
            "REFUSED: --apply requires --real-smoke "
            "(default Phase 6 acceptance is read-only)",
            file=sys.stderr,
        )
        return 2
    if args.real_smoke and not args.apply:
        print(
            "REFUSED: --real-smoke requires --apply "
            "(use default runner for read-only audit)",
            file=sys.stderr,
        )
        return 2
    if args.real_smoke and args.apply:
        return run_real_smoke()
    return run_readonly_audit()


if __name__ == "__main__":
    raise SystemExit(main())
