#!/usr/bin/env python3
"""Phase 2 acceptance runner for Vibe Control.

Runs CLI commands against the migration-harness-mini fixture and asserts
product-level behavior for degraded repo fallback.

Usage:
  python acceptance/phase2/run_phase2_acceptance.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PHASE2_DIR = Path(__file__).resolve().parent
REPO_ROOT = PHASE2_DIR.parents[1]
FIXTURE_ROOT = PHASE2_DIR / "fixtures" / "migration-harness-mini"
QUESTION_FILE = PHASE2_DIR / "questions" / "publish-question.txt"


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


def run_cli(args: list[str], *, cwd: Path) -> tuple[int, dict[str, Any] | None, str]:
    cmd = [sys.executable, "-m", "vibe_control", *args]
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    stdout = proc.stdout.strip()
    if not stdout:
        return proc.returncode, None, f"empty stdout; stderr={proc.stderr.strip()}"
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return proc.returncode, None, f"invalid JSON: {exc}; stdout={stdout[:200]}"
    return proc.returncode, payload, ""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def check_version() -> CheckResult:
    proc = subprocess.run(
        [sys.executable, "-m", "vibe_control", "--version"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    text = (proc.stdout or proc.stderr).strip()
    ok = proc.returncode == 0 and text.startswith("vibe-control 0.")
    return CheckResult(
        "version",
        ok,
        text if ok else f"unexpected version output: {text!r}",
    )


def check_doctor() -> CheckResult:
    code, payload, err = run_cli(["doctor", "--json"], cwd=FIXTURE_ROOT)
    try:
        require(err == "", err)
        require(payload is not None, "doctor payload missing")
        require(payload.get("ok") is True, "doctor not ok")
        require(payload.get("command") == "vibe doctor", "doctor command mismatch")
        data = payload.get("data") or {}
        require(data.get("control_yaml_exists") is True, "fixture control.yaml not detected")
        require(isinstance(data.get("notebooklm"), dict), "notebooklm status missing")
        # Missing NotebookLM must not break doctor
        require("installed" in data["notebooklm"], "notebooklm.installed missing")
    except AssertionError as exc:
        return CheckResult("doctor", False, str(exc))
    return CheckResult("doctor", True, "ok")


def check_config_validate() -> CheckResult:
    code, payload, err = run_cli(["config", "validate", "--json"], cwd=FIXTURE_ROOT)
    try:
        require(err == "", err)
        require(code == 0, f"exit code {code}")
        require(payload and payload.get("ok") is True, "validate failed")
        require(payload.get("project_id") == "migration-harness", "project_id mismatch")
    except AssertionError as exc:
        return CheckResult("config validate", False, str(exc))
    return CheckResult("config validate", True, "ok")


def check_inventory() -> tuple[CheckResult, dict[str, Any] | None]:
    code, payload, err = run_cli(["knowledge", "inventory", "--json"], cwd=FIXTURE_ROOT)
    try:
        require(err == "", err)
        require(code == 0, f"exit code {code}")
        require(payload and payload.get("ok") is True, "inventory not ok")
        docs = (payload.get("data") or {}).get("documents") or []
        paths = {d.get("path") for d in docs}
        ids = {d.get("doc_id") for d in docs}
        require("docs/project/ACTIVE_SPEC.md" in paths, "active spec missing from inventory")
        require("docs/project/DECISION_LOG.md" in paths, "decision log missing from inventory")
        require("docs/project/SUPERSEDED_SPEC.md" not in paths, "superseded included")
        require("docs/program/plans/EXCLUDED_PLAN.md" not in paths, "program plan included")
        require(
            "docs/phases/phase3/plans/EXCLUDED_PHASE_PLAN.md" not in paths,
            "phase plan included",
        )
        require("docs/dashboard/EXCLUDED_DASHBOARD.md" not in paths, "dashboard included")
        require("docs/archive/EXCLUDED_ARCHIVE.md" not in paths, "archive included")
        require("active_publish_spec" in ids, "active_publish_spec id missing")
        require("superseded_legacy_spec" not in ids, "superseded id present")
    except AssertionError as exc:
        return CheckResult("knowledge inventory", False, str(exc)), payload
    return CheckResult("knowledge inventory", True, f"{len(docs)} docs"), payload


def check_status() -> CheckResult:
    code, payload, err = run_cli(["knowledge", "status", "--json"], cwd=FIXTURE_ROOT)
    try:
        require(err == "", err)
        require(code == 0, f"exit code {code}")
        require(payload and payload.get("ok") is True, "status not ok")
        data = payload.get("data") or {}
        require(data.get("synced") is False, "synced must be false in Phase 2")
        require(isinstance(data.get("notebooklm"), dict), "notebooklm block missing")
        require(isinstance(data.get("fallback"), dict), "fallback block missing")
        require(data["fallback"].get("ready") is True, "fallback should be ready in fixture")
    except AssertionError as exc:
        return CheckResult("knowledge status", False, str(exc))
    return CheckResult("knowledge status", True, "synced=false; fallback ready")


def check_query() -> CheckResult:
    if not QUESTION_FILE.is_file():
        return CheckResult("knowledge query", False, f"missing question file: {QUESTION_FILE}")
    code, payload, err = run_cli(
        ["knowledge", "query", "--question-file", str(QUESTION_FILE), "--json"],
        cwd=FIXTURE_ROOT,
    )
    try:
        require(err == "", err)
        require(code == 0, f"exit code {code}")
        require(payload and payload.get("ok") is True, "query not ok")
        require(payload.get("mode") == "degraded", "mode must be degraded")
        data = payload.get("data") or {}
        require(data.get("provider") == "repo", "provider must be repo")
        sources = data.get("sources") or []
        require(sources, "expected at least one source hit")
        paths = {s.get("path") for s in sources}
        require("docs/project/ACTIVE_SPEC.md" in paths, "active spec not found by query")
        forbidden = {
            "docs/project/SUPERSEDED_SPEC.md",
            "docs/program/plans/EXCLUDED_PLAN.md",
            "docs/phases/phase3/plans/EXCLUDED_PHASE_PLAN.md",
            "docs/dashboard/EXCLUDED_DASHBOARD.md",
            "docs/archive/EXCLUDED_ARCHIVE.md",
        }
        require(paths.isdisjoint(forbidden), f"excluded paths leaked into query: {paths & forbidden}")
        blob = json.dumps(payload)
        for secret in (
            "SUPERSEDED_SHOULD_NOT_MATCH",
            "EXCLUDED_PROGRAM_PLAN_SHOULD_NOT_MATCH",
            "EXCLUDED_PHASE_PLAN_SHOULD_NOT_MATCH",
            "EXCLUDED_DASHBOARD_SHOULD_NOT_MATCH",
            "EXCLUDED_ARCHIVE_SHOULD_NOT_MATCH",
        ):
            require(secret not in blob, f"excluded secret leaked: {secret}")
    except AssertionError as exc:
        return CheckResult("knowledge query", False, str(exc))
    return CheckResult(
        "knowledge query",
        True,
        f"{len(sources)} source(s); provider=repo; mode=degraded",
    )


def main() -> int:
    print("Vibe Control Phase 2 Acceptance")
    print(f"fixture: {FIXTURE_ROOT}")
    print(f"python:  {sys.executable}")
    print()

    if not FIXTURE_ROOT.is_dir():
        print(f"FAIL: fixture missing: {FIXTURE_ROOT}")
        return 1

    checks = [
        check_version(),
        check_doctor(),
        check_config_validate(),
    ]
    inventory_result, _ = check_inventory()
    checks.append(inventory_result)
    checks.append(check_status())
    checks.append(check_query())

    width = max(len(c.name) for c in checks)
    failed = 0
    for check in checks:
        mark = "PASS" if check.ok else "FAIL"
        if not check.ok:
            failed += 1
        print(f"[{mark}] {check.name:<{width}}  {check.detail}")

    print()
    if failed:
        print(f"Phase 2 acceptance FAILED ({failed} check(s))")
        return 1
    print("Phase 2 acceptance PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
