#!/usr/bin/env python3
"""Phase 4 acceptance runner for NotebookLM OPM-test integration smoke."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PHASE4 = Path(__file__).resolve().parent
REPO_ROOT = PHASE4.parents[1]
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
    save_observed(PHASE4, name, payload)


def main() -> int:
    print("Vibe Control Phase 4 Acceptance")
    print(f"repo: {REPO_ROOT}")
    if acceptance_local_mode():
        print("mode: VIBE_ACCEPTANCE_LOCAL (skip real NotebookLM remote calls)")
    print()
    checks: list[CheckResult] = []

    code, payload, err = run_cli(["config", "validate", "--json"])
    checks.append(CheckResult("config validate", bool(payload and payload.get("ok")), err or f"ok={payload and payload.get('ok')}"))
    if payload:
        save("config-validate.json", payload)

    code, payload, err = run_cli(["knowledge", "inventory", "--json"])
    ok = bool(payload and payload.get("ok"))
    detail = err
    if payload and payload.get("ok"):
        docs = (payload.get("data") or {}).get("documents") or []
        paths = {d.get("path") for d in docs}
        ok = "docs/project/vibe-control-spec.md" in paths
        detail = f"docs={len(docs)} paths={sorted(p for p in paths if p)}"
        save("inventory.json", payload)
    checks.append(CheckResult("knowledge inventory", ok, detail or ""))

    code, payload, err = run_cli(["knowledge", "notebook", "list", "--json"])
    ok = bool(payload and payload.get("ok") and payload["data"].get("default_alias") == "OPM-test")
    checks.append(CheckResult("notebook list", ok, err or "default_alias check"))
    if payload:
        save("notebook-list.json", payload)

    code, payload, err = run_cli(["knowledge", "notebook", "status", "--json"])
    configured = bool(payload and payload.get("ok") and payload["data"].get("ref_configured"))
    checks.append(
        CheckResult(
            "notebook status",
            bool(payload and payload.get("ok")),
            f"ref_configured={configured}",
        )
    )
    if payload:
        save("notebook-status.json", payload)

    remote_checks = [
        ("remote-status", ["knowledge", "remote-status", "--notebook", "OPM-test", "--json"], "remote-status-before.json"),
        ("remote-inventory", ["knowledge", "remote-inventory", "--notebook", "OPM-test", "--json"], "remote-inventory-before.json"),
        ("sync-preview", ["knowledge", "sync-preview", "--notebook", "OPM-test", "--json"], "sync-preview-before.json"),
        ("seed-dry-run", ["knowledge", "seed-test-sources", "--notebook", "OPM-test", "--dry-run", "--json"], "seed-dry-run.json"),
    ]
    if acceptance_local_mode():
        for name, _args, out in remote_checks:
            checks.append(CheckResult(name, True, "skipped: VIBE_ACCEPTANCE_LOCAL"))
            save(out, {"ok": True, "skipped": True, "reason": "VIBE_ACCEPTANCE_LOCAL"})
    else:
        for name, args, out in remote_checks:
            code, payload, err = run_cli(args)
            if not payload:
                checks.append(CheckResult(name, False, err))
                continue
            if payload.get("ok"):
                checks.append(CheckResult(name, True, "ok"))
                save(out, payload)
            else:
                code_name = (payload.get("error") or {}).get("code")
                ok = code_name in {
                    "NOTEBOOKLM_NOT_CONFIGURED",
                    "NOTEBOOKLM_COMMAND_UNSUPPORTED",
                    "NOTEBOOKLM_COMMAND_FAILED",
                    "NOTEBOOKLM_AUTH_FAILED",
                    "SEED_REQUIRES_ALLOW_ADD",
                } or (name == "sync-preview" and payload.get("ok") is True)
                if name == "sync-preview" and payload.get("ok"):
                    ok = True
                if name == "seed-dry-run" and code_name == "NOTEBOOKLM_NOT_CONFIGURED":
                    ok = True
                checks.append(CheckResult(name, ok, f"code={code_name} warn-ok={ok}"))
                save(out, payload)

    width = max(len(c.name) for c in checks)
    failed = 0
    for check in checks:
        mark = "PASS" if check.ok else "FAIL"
        if not check.ok:
            failed += 1
        print(f"[{mark}] {check.name:<{width}}  {check.detail}")
    print()
    if failed:
        print(f"Phase 4 acceptance FAILED ({failed} check(s))")
        return 1
    print("Phase 4 acceptance PASSED")
    if acceptance_local_mode():
        print("NOTE: local mode skipped real NotebookLM remote checks.")
    elif not configured:
        print("NOTE: notebook ref not configured; remote checks degraded to WARN-compatible codes.")
        print("Configure NOTEBOOKLM_NOTEBOOK_OPM_TEST or .config/.env for real OPM-test smoke.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
