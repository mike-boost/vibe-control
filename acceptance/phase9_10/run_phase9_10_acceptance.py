#!/usr/bin/env python3
"""Phase 9/10 acceptance: publish→sync-state→query with fake/readonly providers (no NLM mutation)."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yaml


PHASE910 = Path(__file__).resolve().parent
REPO_ROOT = PHASE910.parents[1]
OBSERVED = PHASE910 / "observed"
SPEC = REPO_ROOT / "docs" / "project" / "sync" / "phase9-10-publish-query-spec.md"


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


def _git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout or f"git failed: {args}")
    return proc.stdout.strip()


def _seed_temp_repo(tmp: Path) -> Path:
    root = tmp / "repo"
    root.mkdir()
    bare = tmp / "bare.git"
    _git(tmp, "init", "--bare", str(bare))
    _git(root, "init")
    _git(root, "config", "user.email", "phase910@example.com")
    _git(root, "config", "user.name", "Phase910")
    cfg = {
        "project": {"id": "phase910", "name": "Phase910"},
        "components": {
            "knowledge": {"enabled": True},
            "task": {"enabled": False},
        },
        "knowledge": {
            "provider": "notebooklm",
            "fallback_provider": "repo",
            "max_sources": 20,
            "warn_sources": 15,
            "authoritative_statuses": ["active"],
            "include_extra": [],
            "exclude_globs": [
                "docs/program/plans/**",
                "runtime/**",
                "acceptance/**",
                ".beads/**",
            ],
            "source_title_template": "[vibe:{project_id}:{doc_id}] {title}",
            "notebooks": {
                "default_alias": "OPM-test",
                "allow_list": [
                    {
                        "alias": "OPM-test",
                        "display_name": "OPM-test",
                        "ref_env": "NOTEBOOKLM_NOTEBOOK_OPM_TEST",
                        "allowed_operations": ["status", "sync", "query"],
                    }
                ],
            },
        },
        "specs": {
            "registry": "docs/project/spec-registry.yml",
            "required_fields": ["id", "status", "path"],
            "require_commit_push_for_ssot": True,
        },
        "tasks": {"provider": "beads"},
    }
    (root / ".config").mkdir()
    (root / ".config" / "vibe-control.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
    registry = {
        "specs": [
            {
                "id": "active_spec",
                "title": "Active",
                "status": "active",
                "path": "docs/project/active.md",
            }
        ]
    }
    (root / "docs" / "project").mkdir(parents=True)
    (root / "docs" / "project" / "spec-registry.yml").write_text(
        yaml.safe_dump(registry), encoding="utf-8"
    )
    (root / "docs" / "project" / "active.md").write_text(
        "# Active\n\npublish acceptance body\n", encoding="utf-8"
    )
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "init")
    _git(root, "remote", "add", "origin", str(bare))
    _git(root, "push", "-u", "origin", "HEAD")
    return root


def main() -> int:
    print("Vibe Control Phase 9/10 Acceptance (readonly / fake)")
    print(f"repo: {REPO_ROOT}")
    print()
    checks: list[CheckResult] = []

    checks.append(CheckResult("phase9/10 formal spec", SPEC.is_file(), SPEC.as_posix()))
    if SPEC.is_file():
        text = SPEC.read_text(encoding="utf-8")
        required = [
            "Phase 9/10 Test Spec",
            "P9-VALIDATE-01",
            "P9-PUBLISH-01",
            "P10-QUERY-01",
            "P10-ENVELOPE-01",
            "partial_success",
        ]
        missing = [p for p in required if p not in text]
        checks.append(
            CheckResult(
                "spec test IDs",
                len(missing) == 0,
                "ok" if not missing else f"missing={missing}",
            )
        )

    pytest_bin = REPO_ROOT / ".venv" / "bin" / "pytest"
    py = str(REPO_ROOT / ".venv" / "bin" / "python") if (REPO_ROOT / ".venv" / "bin" / "python").is_file() else sys.executable
    cmd = [
        str(pytest_bin if pytest_bin.is_file() else "pytest"),
        "-q",
        "tests/test_phase9_publish.py",
        "tests/test_phase10_query.py",
    ]
    proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    out = (proc.stdout or "") + (proc.stderr or "")
    checks.append(
        CheckResult(
            "phase9/10 pytest",
            proc.returncode == 0,
            out.strip().splitlines()[-1] if out.strip() else f"exit={proc.returncode}",
        )
    )
    save(
        "phase9_10-pytest.json",
        {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "tail": out.strip().splitlines()[-20:],
        },
    )

    # End-to-end safe path in temp repo (A–G)
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from vibe_control.knowledge.query_router import route_knowledge_query
    from vibe_control.spec.publish import publish_spec, validate_spec_path

    with tempfile.TemporaryDirectory(prefix="vibe-p910-") as td:
        tmp = Path(td)
        root = _seed_temp_repo(tmp)

        # A. validate
        validated = validate_spec_path(root, "docs/project/active.md")
        checks.append(
            CheckResult(
                "A validate formal spec",
                bool(validated.get("ok")),
                json.dumps({"spec_id": validated.get("spec_id"), "code": validated.get("code")}),
            )
        )
        save("A-validate.json", validated)

        # B. dry-run
        dry = publish_spec(
            root,
            "docs/project/active.md",
            dry_run=True,
            already_pushed=True,
            allow_provider_sync=False,
        )
        checks.append(
            CheckResult(
                "B publish dry-run",
                bool(dry.get("ok")) and dry.get("dry_run") is True and dry.get("provider_mutated") is not True,
                json.dumps({"plan": dry.get("plan"), "pushed": dry.get("pushed")}),
            )
        )
        save("B-dry-run.json", dry)

        # C. already-pushed
        pub = publish_spec(
            root,
            "docs/project/active.md",
            dry_run=False,
            already_pushed=True,
            allow_provider_sync=False,
        )
        checks.append(
            CheckResult(
                "C already-pushed publish",
                bool(pub.get("ok"))
                and pub.get("committed") is False
                and pub.get("pushed") is False
                and bool(pub.get("authoritative_ref")),
                json.dumps(
                    {
                        "ref": pub.get("authoritative_ref"),
                        "committed": pub.get("committed"),
                        "pushed": pub.get("pushed"),
                    }
                ),
            )
        )
        save("C-already-pushed.json", pub)

        # D. partial_success when sync apply fails
        def boom(*_a, **_k):
            return {"ok": False, "code": "NOTEBOOKLM_UNAVAILABLE", "message": "down"}

        import vibe_control.spec.publish as pubmod

        orig = pubmod.apply_forward_sync
        pubmod.apply_forward_sync = boom  # type: ignore[assignment]
        try:
            import os

            os.environ["NOTEBOOKLM_NOTEBOOK_OPM_TEST"] = "nb-acc-partial"
            partial = publish_spec(
                root,
                "docs/project/active.md",
                dry_run=False,
                already_pushed=True,
                allow_provider_sync=True,
                provider="fake",
                home=tmp,
            )
        finally:
            pubmod.apply_forward_sync = orig  # type: ignore[assignment]
        checks.append(
            CheckResult(
                "D partial_success provider unavailable",
                bool(partial.get("partial_success")) and partial.get("failed") == "knowledge_sync",
                json.dumps(
                    {
                        "partial_success": partial.get("partial_success"),
                        "failed": partial.get("failed"),
                        "pending": partial.get("pending"),
                    }
                ),
            )
        )
        save("D-partial.json", partial)

        # E. query synced → fake provider
        class FakeQ:
            def query(self, question: str, **_k):
                return {
                    "ok": True,
                    "answer": f"fake:{question[:20]}",
                    "sources": [{"doc_id": "active_spec", "source_id": "RAW-SRC"}],
                }

            def add_file_source(self, **_k):
                raise RuntimeError("mutation forbidden")

            def delete_source(self, **_k):
                raise RuntimeError("mutation forbidden")

        synced = route_knowledge_query(
            repo_root=root,
            question="publish acceptance",
            sync_state_override="synced",
            provider=FakeQ(),
            home=tmp,
        )
        checks.append(
            CheckResult(
                "E query synced routes to provider",
                synced.get("provider") == "notebooklm" and synced.get("sync_state") == "synced",
                json.dumps({"provider": synced.get("provider"), "mode": synced.get("mode")}),
            )
        )
        save("E-query-synced.json", synced)

        # F. pending / unavailable → repo fallback
        pending = route_knowledge_query(
            repo_root=root,
            question="publish acceptance",
            sync_state_override="pending",
            home=tmp,
        )
        unavailable = route_knowledge_query(
            repo_root=root,
            question="publish acceptance",
            sync_state_override="unavailable",
            home=tmp,
        )
        checks.append(
            CheckResult(
                "F query pending/unavailable fallback",
                pending.get("provider") == "repo"
                and unavailable.get("provider") == "repo"
                and unavailable.get("mode") == "degraded",
                json.dumps(
                    {
                        "pending": pending.get("mode"),
                        "unavailable": unavailable.get("mode"),
                    }
                ),
            )
        )
        save(
            "F-query-fallback.json",
            {"pending": pending, "unavailable": unavailable},
        )

        # G. no provider mutation in default acceptance artifacts
        blob = json.dumps(
            {
                "A": validated,
                "B": dry,
                "C": pub,
                "D": partial,
                "E": synced,
                "F": {"pending": pending, "unavailable": unavailable},
            }
        )
        mutation_leak = any(
            token in blob
            for token in ("source add", "real-smoke", "notebooklm_note_written\": true")
        )
        checks.append(
            CheckResult(
                "G no provider mutation in acceptance",
                not mutation_leak and dry.get("provider_mutated") is not True,
                "ok" if not mutation_leak else "mutation tokens found",
            )
        )

    failed = [c for c in checks if not c.ok]
    print("Checks:")
    for c in checks:
        mark = "PASS" if c.ok else "FAIL"
        print(f"  [{mark}] {c.name}: {c.detail}")
    summary = {
        "ok": not failed,
        "passed": len(checks) - len(failed),
        "failed": len(failed),
        "checks": [{"name": c.name, "ok": c.ok, "detail": c.detail} for c in checks],
    }
    save("summary.json", summary)
    print()
    print(f"Result: {'PASS' if summary['ok'] else 'FAIL'} ({summary['passed']}/{len(checks)})")
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
