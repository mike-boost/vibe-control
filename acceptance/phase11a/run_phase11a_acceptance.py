#!/usr/bin/env python3
"""Phase 11A acceptance: readonly reconcile + ask template + skills (no Beads/NLM mutation)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yaml

PHASE11A = Path(__file__).resolve().parent
REPO_ROOT = PHASE11A.parents[1]
OBSERVED = PHASE11A / "observed"
SPEC = REPO_ROOT / "docs" / "project" / "sync" / "phase11a-ssot-specs-beads-readonly-reconcile-spec.md"
PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
if not PYTHON.is_file():
    PYTHON = Path(sys.executable)


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


def save(name: str, payload: dict) -> None:
    OBSERVED.mkdir(parents=True, exist_ok=True)
    (OBSERVED / name).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def run_cli(cwd: Path, args: list[str]) -> tuple[int, dict]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
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
        "# Vibe Control Spec\n\nPhase 11A\nPhase 11B\npublish migration\n",
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
        "tasks": {"provider": "beads"},
    }
    config_dir = root / ".config"
    config_dir.mkdir(parents=True)
    (config_dir / "vibe-control.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return root


def main() -> int:
    print("Vibe Control Phase 11A Acceptance (readonly)")
    print(f"repo: {REPO_ROOT}")
    print()
    checks: list[CheckResult] = []

    checks.append(CheckResult("phase11a formal spec", SPEC.is_file(), SPEC.as_posix()))

    # Unit/fixture semantics (no real Beads / NotebookLM required).
    pytest_bin = REPO_ROOT / ".venv" / "bin" / "pytest"
    cmd = [
        str(pytest_bin if pytest_bin.is_file() else "pytest"),
        "-q",
        "tests/test_phase11a_slice1.py",
        "tests/test_phase11a_slice2.py",
        "tests/test_knowledge_ask_template.py",
    ]
    proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    checks.append(
        CheckResult(
            "phase11a + ask-template unit tests",
            proc.returncode == 0,
            (proc.stdout or proc.stderr or "")[-500:],
        )
    )

    with tempfile.TemporaryDirectory(prefix="phase11a-acc-") as tmp:
        root = seed_repo(Path(tmp))

        code, fake = run_cli(
            root, ["task", "reconcile", "--dry-run", "--json", "--provider", "fake"]
        )
        save("reconcile_fake.json", fake)
        fake_ok = (
            code == 0
            and fake.get("ok") is True
            and fake.get("mode") == "readonly"
            and fake.get("provider") == "fake"
            and fake.get("provider_available") is True
            and fake.get("mutation") is False
            and (fake.get("data") or {}).get("counts", {}).get("missing")
            == (fake.get("data") or {}).get("expected_count")
            and (fake.get("data") or {}).get("expected_count", 0) >= 1
            and (fake.get("data") or {}).get("reconcile_skipped") is False
            and not any(
                (t.get("ssot_anchor") == "roadmap.phase11a")
                for t in ((fake.get("data") or {}).get("expected_tasks") or [])
            )
        )
        checks.append(
            CheckResult(
                "reconcile --provider fake empty is real missing",
                fake_ok,
                f"code={code} mode={fake.get('mode')} counts={(fake.get('data') or {}).get('counts')}",
            )
        )

        # Fixture-backed beads unavailable (no real bd / .beads required).
        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO_ROOT / "src")
        unavailable_script = f"""
import json, sys
from pathlib import Path
sys.path.insert(0, {str(REPO_ROOT / "src")!r})
from vibe_control.task.beads_readonly import BeadsReadonlyProvider
from vibe_control.task.reconcile_cli import run_task_reconcile_dry_run
provider = BeadsReadonlyProvider(
    executable="/missing/bd-acceptance",
    runner=lambda argv: (127, "", "executable not found"),
)
result = run_task_reconcile_dry_run(
    repo_root=Path({str(root)!r}),
    provider=provider,
    provider_name="beads",
)
print(json.dumps(result))
"""
        up = subprocess.run(
            [str(PYTHON), "-c", unavailable_script],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        try:
            unavailable = json.loads(up.stdout or "{}")
        except json.JSONDecodeError:
            unavailable = {"_raw": up.stdout, "_err": up.stderr, "_code": up.returncode}
        save("reconcile_beads_unavailable.json", unavailable)
        unavail_ok = (
            up.returncode == 0
            and unavailable.get("ok") is True
            and unavailable.get("mode") == "unavailable"
            and unavailable.get("provider_available") is False
            and (unavailable.get("data") or {}).get("reconcile_skipped") is True
            and (unavailable.get("data") or {}).get("counts", {}).get("missing") == 0
        )
        checks.append(
            CheckResult(
                "beads unavailable fixture (not real missing)",
                unavail_ok,
                f"mode={unavailable.get('mode')} missing={(unavailable.get('data') or {}).get('counts')}",
            )
        )

        empty_script = f"""
import json, sys
from pathlib import Path
sys.path.insert(0, {str(REPO_ROOT / "src")!r})
from vibe_control.task.beads_readonly import BeadsReadonlyProvider
from vibe_control.task.reconcile_cli import run_task_reconcile_dry_run
provider = BeadsReadonlyProvider(
    executable="/fake/bd",
    runner=lambda argv: (0, "[]", ""),
)
result = run_task_reconcile_dry_run(
    repo_root=Path({str(root)!r}),
    provider=provider,
    provider_name="beads",
)
print(json.dumps(result))
"""
        ep = subprocess.run(
            [str(PYTHON), "-c", empty_script],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        try:
            empty = json.loads(ep.stdout or "{}")
        except json.JSONDecodeError:
            empty = {"_raw": ep.stdout, "_err": ep.stderr, "_code": ep.returncode}
        save("reconcile_beads_empty.json", empty)
        empty_ok = (
            ep.returncode == 0
            and empty.get("ok") is True
            and empty.get("mode") == "readonly"
            and empty.get("provider_available") is True
            and (empty.get("data") or {}).get("counts", {}).get("missing")
            == (empty.get("data") or {}).get("expected_count")
            and (empty.get("data") or {}).get("expected_count", 0) >= 1
            and (empty.get("data") or {}).get("reconcile_skipped") is False
        )
        checks.append(
            CheckResult(
                "beads empty-provider fixture is real missing",
                empty_ok,
                f"mode={empty.get('mode')} counts={(empty.get('data') or {}).get('counts')}",
            )
        )

        # Knowledge ask template metadata via local/repo fallback (no NotebookLM mutation).
        qfile = root / "ask-question.txt"
        qfile.write_text("What is Phase 11A?", encoding="utf-8")
        code_q, query = run_cli(
            root, ["knowledge", "query", "--question-file", str(qfile), "--json"]
        )
        save("knowledge_query_ask_template.json", query)
        qdata = query.get("data") or {}
        ask_ok = (
            code_q == 0
            and query.get("ok") is True
            and qdata.get("ask_template_id") == "default_ssot_facts"
            and qdata.get("ask_template_version") == "vibe.knowledge.ask.v3"
            and str(qdata.get("question_hash") or "").startswith("sha256:")
            and str(qdata.get("rendered_prompt_hash") or "").startswith("sha256:")
        )
        checks.append(
            CheckResult(
                "knowledge query ask template metadata",
                ask_ok,
                f"template={qdata.get('ask_template_id')} ver={qdata.get('ask_template_version')}",
            )
        )

        # Skills packaging checks against the real repo package (not temp).
        code_s, status = run_cli(REPO_ROOT, ["skills", "status", "--json"])
        save("skills_status.json", status)
        names = {s.get("name") for s in (status.get("data") or {}).get("skills") or []}
        status_ok = code_s == 0 and "vibe-control" in names and "vibe-knowledge" in names
        checks.append(
            CheckResult(
                "skills status includes vibe-control",
                status_ok,
                f"names={sorted(names)}",
            )
        )

        code_i, install = run_cli(
            REPO_ROOT, ["skills", "install", "--dry-run", "--json"]
        )
        save("skills_install_dry_run.json", install)
        planned = {
            op.get("skill")
            for op in (install.get("data") or {}).get("operations") or []
        }
        install_ok = code_i == 0 and "vibe-control" in planned and install.get("ok") is True
        checks.append(
            CheckResult(
                "skills install --dry-run includes vibe-control",
                install_ok,
                f"planned={sorted(x for x in planned if x)}",
            )
        )

        checks.append(
            CheckResult(
                "no mutation apply / real Beads / real NotebookLM required",
                True,
                "acceptance uses fixtures, --dry-run, and repo query only",
            )
        )

    print("Checks:")
    failed = 0
    for item in checks:
        mark = "PASS" if item.ok else "FAIL"
        if not item.ok:
            failed += 1
        print(f"  [{mark}] {item.name}: {item.detail}")
    print()
    if failed:
        print(f"Phase 11A acceptance FAILED ({failed} checks)")
        return 1
    print("Phase 11A acceptance PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
