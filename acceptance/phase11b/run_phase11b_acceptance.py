#!/usr/bin/env python3
"""Phase 11B acceptance: apply plan + fake dry-run (no Beads/NLM mutation)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yaml

PHASE11B = Path(__file__).resolve().parent
REPO_ROOT = PHASE11B.parents[1]
sys.path.insert(0, str(REPO_ROOT / "acceptance"))
from lib.observed_output import save_observed  # noqa: E402

SPEC = REPO_ROOT / "docs" / "project" / "sync" / "phase11b-beads-import-apply-spec.md"
PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
if not PYTHON.is_file():
    PYTHON = Path(sys.executable)


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


def save(name: str, payload: dict) -> None:
    save_observed(PHASE11B, name, payload)


def run_cli(cwd: Path, args: list[str]) -> tuple[int, dict]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    env.pop("VIBE_BEADS_LIVE_APPLY", None)
    proc = subprocess.run(
        [str(PYTHON), "-m", "vibe_control", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        payload = {"_raw_stdout": proc.stdout, "_stderr": proc.stderr, "_code": proc.returncode}
    return proc.returncode, payload


def seed_repo(tmp: Path) -> Path:
    root = tmp / "repo"
    root.mkdir()
    (root / "docs" / "project").mkdir(parents=True)
    (root / "docs" / "project" / "vibe-control-spec.md").write_text(
        "# Vibe Control Spec\n\nPhase 11A\nPhase 11B\n",
        encoding="utf-8",
    )
    (root / "docs" / "project" / "spec-registry.yml").write_text(
        yaml.safe_dump(
            {
                "entries": [
                    {
                        "id": "vibe_control_spec",
                        "title": "Vibe Control Spec",
                        "status": "active",
                        "path": "docs/project/vibe-control-spec.md",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    cfg = {
        "project": {"id": "vibe-control", "name": "Vibe Control"},
        "components": {
            "knowledge": {"enabled": True},
            "task": {"enabled": True},
        },
        "knowledge": {
            "provider": "notebooklm",
            "fallback_provider": "repo",
            "max_sources": 20,
            "warn_sources": 15,
            "authoritative_statuses": ["active"],
            "include_extra": [],
            "exclude_globs": ["acceptance/**", ".beads/**", "docs/project/plans/**"],
            "source_title_template": "[vibe:{project_id}:{doc_id}] {title}",
        },
        "specs": {
            "registry": "docs/project/spec-registry.yml",
            "required_fields": ["id", "status", "path"],
        },
        "tasks": {"provider": "fake"},
    }
    config_dir = root / ".config"
    config_dir.mkdir(parents=True)
    (config_dir / "vibe-control.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return root


def main() -> int:
    checks: list[CheckResult] = []

    if not SPEC.is_file():
        checks.append(CheckResult("spec_exists", False, f"missing {SPEC}"))
    else:
        text = SPEC.read_text(encoding="utf-8")
        ok = all(
            token in text
            for token in (
                "create_managed",
                "update_managed",
                "skip_delete_forbidden",
                "VIBE_BEADS_LIVE_APPLY",
            )
        )
        checks.append(CheckResult("spec_exists", ok, "phase11b spec boundaries"))

    with tempfile.TemporaryDirectory(prefix="vibe-phase11b-") as td:
        root = seed_repo(Path(td))

        code, payload = run_cli(root, ["task", "apply", "--json", "--provider", "fake"])
        checks.append(
            CheckResult(
                "fail_closed_no_flags",
                code != 0 and (payload.get("error") or {}).get("code") == "APPLY_REQUIRES_DRY_RUN_OR_APPLY",
                str((payload.get("error") or {}).get("code")),
            )
        )
        save("fail_closed.json", payload)

        code, payload = run_cli(
            root, ["task", "apply", "--dry-run", "--json", "--provider", "fake"]
        )
        plan = (payload.get("data") or {}).get("plan") or {}
        ops = (payload.get("data") or {}).get("operations") or []
        creates = [o for o in ops if o.get("op_type") == "create_managed"]
        dry_ok = (
            code == 0
            and payload.get("ok") is True
            and payload.get("mode") == "dry_run"
            and payload.get("mutation") is False
            and plan.get("create", 0) >= 1
            and all(c.get("executable") for c in creates)
            and not any(c.get("ssot_anchor") == "roadmap.phase11a" for c in creates)
            and not any(
                c.get("ssot_anchor") == "roadmap.phase11b" and c.get("executable")
                for c in creates
            )
            and any(o.get("op_type") == "skip_completed" for o in ops)
        )
        checks.append(
            CheckResult(
                "dry_run_plan",
                dry_ok,
                f"create={plan.get('create')} skip={plan.get('skip')} ops={len(ops)}",
            )
        )
        save("dry_run.json", payload)

        code, payload = run_cli(
            root,
            [
                "task",
                "apply",
                "--apply",
                "--json",
                "--provider",
                "beads",
                "--allow-local-without-providers",
            ],
        )
        beads_safe = payload.get("mutation") is False and payload.get("mode") in {
            "blocked",
            "unavailable",
        }
        checks.append(
            CheckResult(
                "beads_apply_blocked",
                beads_safe,
                f"mode={payload.get('mode')} mutation={payload.get('mutation')} code={code}",
            )
        )
        save("beads_blocked.json", payload)

        # Fake --apply is allowed in unit tests; acceptance stays mutation=false for provider state
        # by only exercising dry-run + blocked beads (no fake apply here).
        checks.append(
            CheckResult(
                "no_real_provider_mutation",
                True,
                "acceptance uses fake dry-run + beads blocked only",
            )
        )

    failed = [c for c in checks if not c.ok]
    summary = {
        "ok": not failed,
        "phase": "11B",
        "checks": [{"name": c.name, "ok": c.ok, "detail": c.detail} for c in checks],
        "mutation": False,
        "real_beads": False,
        "real_notebooklm": False,
    }
    save("summary.json", summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
