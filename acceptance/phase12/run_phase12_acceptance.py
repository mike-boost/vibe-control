#!/usr/bin/env python3
"""Phase 12 local/readonly acceptance — fake/readonly only; no provider mutation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from vibe_control.implementation.prompt import (  # noqa: E402
    PROMPT_SECTION_ORDER,
    PromptError,
    build_implementation_prompt,
)
from vibe_control.closeout import evaluate_ssot_closeout  # noqa: E402


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "ok": ok, "detail": detail}


def main() -> int:
    checks: list[dict] = []
    # Use real repo for projection of roadmap.phase12
    repo = ROOT
    try:
        env = build_implementation_prompt(
            repo_root=repo,
            task_selector="roadmap.phase12",
            product_ready=False,
            readiness_summary={
                "product_ready": False,
                "sync_state": "drift",
                "provider_ask_clean": False,
                "blocked_reasons": ["knowledge_sync_state=drift"],
            },
            reconcile_counts={
                "matched": 0,
                "missing": 0,
                "stale": 1,
                "duplicate": 0,
                "conflict": 0,
                "unmanaged": 0,
            },
            apply_plan_counts={"create": 0, "update": 0, "skip": 0, "blocked": 0},
            provider_task_id="fake-binding-id",
            provider_sync_required=True,
            notebook_ref_raw="notebooklm://must-not-leak",
        )
        blob = json.dumps(env, ensure_ascii=False)
        checks.append(_check("mutation_false", env.get("mutation") is False))
        checks.append(_check("has_prompt", bool(env["data"].get("prompt"))))
        checks.append(
            _check(
                "prompt_sections_ordered",
                env["data"].get("prompt_sections") == list(PROMPT_SECTION_ORDER),
            )
        )
        checks.append(_check("no_raw_notebook_ref", "notebooklm://must-not-leak" not in blob))
        checks.append(_check("has_task_identity", "managed_key" in env["data"]["task_identity"]))
        checks.append(
            _check(
                "provider_id_not_identity",
                env["data"]["task_context"].get("provider_task_id_is_identity") is False,
            )
        )
        checks.append(_check("degraded_warnings", "product_ready=false" in env.get("warnings", [])))
        checks.append(
            _check(
                "completed_do_not_restart",
                env["data"].get("task_completed") is True
                and "task_completed_do_not_restart" in env.get("warnings", []),
            )
        )
    except Exception as exc:  # noqa: BLE001
        checks.append(_check("build_prompt", False, str(exc)))

    try:
        build_implementation_prompt(
            repo_root=repo,
            task_selector="roadmap.does-not-exist",
            product_ready=True,
            readiness_summary={"product_ready": True, "blocked_reasons": []},
        )
        checks.append(_check("missing_selector_fails", False, "expected PromptError"))
    except PromptError as exc:
        checks.append(_check("missing_selector_fails", exc.code == "TASK_SELECTOR_NOT_FOUND"))

    closeout = evaluate_ssot_closeout(
        ssot_or_include_extra_changed=True,
        sync_approved=False,
        product_ready=False,
        knowledge_synced=False,
    )
    checks.append(
        _check(
            "closeout_sync_required",
            closeout["provider_sync_required"] is True
            and closeout["closeout_state"] == "ssot_change_committed_sync_required",
        )
    )

    failed = [c for c in checks if not c["ok"]]
    print(json.dumps({"ok": not failed, "checks": checks, "failed": failed}, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
