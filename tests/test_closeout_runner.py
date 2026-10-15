"""Focused tests for vibe closeout run driver (orchestration only)."""

from __future__ import annotations

from pathlib import Path

from helpers import minimal_config_dict, write_control_yaml, write_doc
from vibe_control.closeout_runner import run_closeout
from vibe_control.cli import main
from vibe_control.implementation.prompt import build_implementation_prompt


def _status(
    *,
    sync_state: str = "synced",
    ask_clean: bool = True,
    provider_sync_required: bool = False,
    closeout_state: str = "no_ssot_change_product_ready",
    product_ready: bool = True,
    task_cache_current: bool = True,
    reconcile_counts: dict | None = None,
    apply_plan_counts: dict | None = None,
    knowledge_available: bool = True,
    target_ok: bool = True,
    blocked_reasons: list | None = None,
):
    counts = reconcile_counts or {
        "matched": 1,
        "missing": 0,
        "stale": 0,
        "duplicate": 0,
        "conflict": 0,
        "unmanaged": 0,
    }
    plan = apply_plan_counts or {"create": 0, "update": 0, "skip": 0, "blocked": 0}
    return {
        "project_id": "vibe-control",
        "product_ready": product_ready,
        "blocked_reasons": list(blocked_reasons or []),
        "closeout_state": closeout_state,
        "closeout_complete": bool(product_ready and ask_clean and task_cache_current),
        "provider_sync_required": provider_sync_required,
        "knowledge_provider": {
            "available": knowledge_available,
            "target_ok": target_ok,
            "sync_state": sync_state,
            "provider_ask_clean": ask_clean,
            "ask_hygiene": {
                "provider_ask_clean": ask_clean,
                "required_updates_count": 0 if sync_state == "synced" else 1,
                "candidate_count": 0,
                "orphan_managed_count": 0,
            },
        },
        "task_provider": {
            "available": True,
            "mode": "readonly",
            "readable": True,
            "ready_queue_available": True,
        },
        "task_cache_current": task_cache_current,
        "task_cache": {
            "task_cache_current": task_cache_current,
            "reconcile_counts": counts,
            "apply_plan_counts": plan,
            "safe_task_convergence_allowed": (not task_cache_current)
            and counts.get("missing", 0) > 0
            and counts.get("duplicate", 0) == 0,
            "task_cache_reset_required": (
                counts.get("duplicate", 0) + counts.get("conflict", 0) + counts.get("unmanaged", 0)
            )
            > 0,
        },
        "chatgpt_project_sources": {
            "product_closeout_gate": False,
            "owner_manual_external_copy": True,
            "advisor_files": [],
        },
        "warnings": [],
        "next_actions": [],
    }


def _deps(
    *,
    git: str = "",
    status_seq: list[dict],
    dry_run: dict | None = None,
    apply_result: dict | None = None,
    desired_ids: set[str] | None = None,
    apply_calls: list | None = None,
    next_task: str | None = "roadmap.test_closeout",
):
    statuses = list(status_seq)
    apply_calls = apply_calls if apply_calls is not None else []

    def git_status(_root: Path) -> str:
        return git

    def integration(_root: Path, **_kwargs):
        assert statuses, "unexpected extra integration status call"
        return statuses.pop(0)

    def plan_dry(_root: Path):
        return dict(
            dry_run
            or {
                "ok": True,
                "sync_state": "synced",
                "required_updates_count": 0,
                "operations": [{"op": "already_current", "doc_id": "a"}],
            }
        )

    def apply_sync(_root: Path):
        apply_calls.append("apply")
        return dict(apply_result or {"ok": True, "applied": True})

    def desired(_root: Path) -> set[str]:
        return set(desired_ids or {"a", "b"})

    def next_selection(*, repo_root: Path):  # noqa: ARG001
        if next_task is None:
            return {
                "next_actionable_task": None,
                "no_actionable_next_task": True,
            }
        return {
            "next_actionable_task": next_task,
            "no_actionable_next_task": False,
        }

    return {
        "git_status_short": git_status,
        "build_integration_status": integration,
        "plan_sync_dry_run": plan_dry,
        "apply_knowledge_sync": apply_sync,
        "desired_doc_ids": desired,
        "next_actionable_selection": next_selection,
        "_apply_calls": apply_calls,
        "_remaining_statuses": statuses,
    }


def test_closeout_complete_when_no_sync_needed_and_task_current():
    deps = _deps(status_seq=[_status()])
    env = run_closeout(repo_root=Path("."), apply=False, deps=deps)
    assert env["ok"] is True
    assert env["mutation"] is False
    assert env["mode"] == "dry-run"
    data = env["data"]
    assert data["closeout_complete"] is True
    assert data["implementation_ready"] is True
    assert data["next_required_action"] in {"none", "closeout_complete"}
    assert data["chatgpt_project_sources"]["product_closeout_gate"] is False
    assert "UPDATE_CHATGPT_PROJECT_SOURCES" not in [
        a.get("code") for a in data.get("next_actions") or []
    ]
    assert deps["_apply_calls"] == []


def test_drift_bounded_apply_runs_preflight_then_apply_then_restatus():
    apply_calls: list[str] = []
    pre = _status(
        sync_state="drift",
        ask_clean=False,
        provider_sync_required=True,
        closeout_state="ssot_change_committed_sync_required",
        product_ready=False,
        task_cache_current=False,
        reconcile_counts={
            "matched": 0,
            "missing": 1,
            "stale": 0,
            "duplicate": 0,
            "conflict": 0,
            "unmanaged": 0,
        },
        apply_plan_counts={"create": 1, "update": 0, "skip": 0, "blocked": 0},
        blocked_reasons=["knowledge_sync_state=drift"],
    )
    post = _status(
        sync_state="synced",
        ask_clean=True,
        provider_sync_required=False,
        closeout_state="ssot_change_committed_synced_product_ready",
        product_ready=False,
        task_cache_current=False,
        reconcile_counts={
            "matched": 0,
            "missing": 1,
            "stale": 0,
            "duplicate": 0,
            "conflict": 0,
            "unmanaged": 0,
        },
        apply_plan_counts={"create": 1, "update": 0, "skip": 0, "blocked": 0},
    )
    deps = _deps(
        status_seq=[pre, post],
        dry_run={
            "ok": True,
            "sync_state": "drift",
            "required_updates_count": 1,
            "operations": [{"op": "replace_required", "doc_id": "a"}],
        },
        apply_calls=apply_calls,
        desired_ids={"a"},
    )
    env = run_closeout(repo_root=Path("."), apply=True, deps=deps)
    assert env["ok"] is True
    assert env["mutation"] is True
    assert apply_calls == ["apply"]
    data = env["data"]
    assert "sync_dry_run" in data["actions_run"]
    assert "sync_apply" in data["actions_run"]
    assert "integration_status_post" in data["actions_run"]
    assert data["knowledge_closeout"]["applied"] is True
    assert data["knowledge_closeout"]["dry_run_bounded"] is True
    assert data["next_required_action"] == "task_convergence_required"
    assert data["closeout_complete"] is False
    assert data["implementation_ready"] is False


def test_unbounded_plan_stops_before_apply():
    apply_calls: list[str] = []
    deps = _deps(
        status_seq=[
            _status(
                sync_state="drift",
                ask_clean=False,
                provider_sync_required=True,
                product_ready=False,
                task_cache_current=True,
            )
        ],
        dry_run={
            "ok": True,
            "sync_state": "drift",
            "required_updates_count": 1,
            "operations": [
                {"op": "replace_required", "doc_id": "a"},
                {"op": "delete_unmanaged", "doc_id": "x"},
            ],
        },
        apply_calls=apply_calls,
        desired_ids={"a"},
    )
    env = run_closeout(repo_root=Path("."), apply=True, deps=deps)
    assert env["ok"] is False
    assert apply_calls == []
    data = env.get("data") or (env.get("error") or {}).get("details") or {}
    # contract fields may be on envelope data even when ok=false
    payload = env.get("data") if env.get("data") else data
    reasons = payload.get("blocked_reasons") or env.get("error", {}).get("details", {}).get(
        "blocked_reasons"
    ) or []
    joined = " ".join(str(r) for r in reasons) + str(env.get("error"))
    assert "unbounded" in joined.lower() or "scope" in joined.lower() or "unsafe" in joined.lower()
    assert apply_calls == []


def test_dirty_git_stops_before_apply():
    apply_calls: list[str] = []
    deps = _deps(
        git=" M docs/project/vibe-control-spec.md",
        status_seq=[
            _status(
                sync_state="drift",
                ask_clean=False,
                provider_sync_required=True,
                product_ready=False,
            )
        ],
        dry_run={
            "ok": True,
            "sync_state": "drift",
            "required_updates_count": 1,
            "operations": [{"op": "replace_required", "doc_id": "a"}],
        },
        apply_calls=apply_calls,
        desired_ids={"a"},
    )
    env = run_closeout(repo_root=Path("."), apply=True, deps=deps)
    assert env["ok"] is False
    assert apply_calls == []
    assert env["mutation"] is False
    code = (env.get("error") or {}).get("code")
    assert code in {"GIT_DIRTY", "LOCAL_MODIFICATIONS_PRESENT"}
    payload = env.get("data") or {}
    assert payload.get("next_required_action") == "clean_git_status" or code == "GIT_DIRTY"


def test_provider_unavailable_stops_without_apply():
    apply_calls: list[str] = []
    deps = _deps(
        status_seq=[
            _status(
                sync_state="unavailable",
                ask_clean=False,
                provider_sync_required=True,
                product_ready=False,
                knowledge_available=False,
                target_ok=False,
                blocked_reasons=["knowledge_unavailable"],
            )
        ],
        apply_calls=apply_calls,
    )
    env = run_closeout(repo_root=Path("."), apply=True, deps=deps)
    assert env["ok"] is False
    assert apply_calls == []
    payload = env.get("data") or {}
    assert payload.get("next_required_action") in {
        "provider_unavailable",
        "fix_knowledge_provider",
    } or (env.get("error") or {}).get("code") in {
        "PROVIDER_UNAVAILABLE",
        "KNOWLEDGE_PROVIDER_UNAVAILABLE",
    }


def test_knowledge_clean_task_missing_requires_convergence():
    deps = _deps(
        status_seq=[
            _status(
                sync_state="synced",
                ask_clean=True,
                provider_sync_required=False,
                product_ready=False,
                task_cache_current=False,
                reconcile_counts={
                    "matched": 0,
                    "missing": 1,
                    "stale": 0,
                    "duplicate": 0,
                    "conflict": 0,
                    "unmanaged": 0,
                },
                apply_plan_counts={"create": 1, "update": 0, "skip": 0, "blocked": 0},
            )
        ]
    )
    env = run_closeout(repo_root=Path("."), apply=False, deps=deps)
    assert env["ok"] is True
    assert env["mutation"] is False
    data = env["data"]
    assert data["next_required_action"] == "task_convergence_required"
    assert data["closeout_complete"] is False
    assert data["implementation_ready"] is False
    assert data["task_closeout"]["convergence_required"] is True
    assert deps["_apply_calls"] == []


def test_task_pollution_blocks_without_auto_repair():
    deps = _deps(
        status_seq=[
            _status(
                sync_state="synced",
                ask_clean=True,
                provider_sync_required=False,
                product_ready=False,
                task_cache_current=False,
                reconcile_counts={
                    "matched": 0,
                    "missing": 0,
                    "stale": 0,
                    "duplicate": 1,
                    "conflict": 0,
                    "unmanaged": 1,
                },
                apply_plan_counts={"create": 0, "update": 0, "skip": 0, "blocked": 0},
            )
        ]
    )
    env = run_closeout(repo_root=Path("."), apply=False, deps=deps)
    data = env["data"]
    assert data["closeout_complete"] is False
    assert data["implementation_ready"] is False
    assert data["next_required_action"] in {
        "task_cache_reset_required",
        "task_pollution_blocked",
    }
    assert deps["_apply_calls"] == []
    codes = [a.get("code") for a in data.get("next_actions") or []]
    assert "TASK_CACHE_RESET_DRY_RUN" in codes or any("RESET" in str(c) for c in codes)


def test_prompt_still_blocks_when_closeout_incomplete(tmp_path):
    write_control_yaml(
        tmp_path,
        {**minimal_config_dict(), "project": {"id": "vibe-control", "name": "Vibe"}},
    )
    write_doc(tmp_path, "docs/project/vibe-control-spec.md", "# Spec\n")
    write_doc(
        tmp_path,
        "docs/project/vibe-control-roadmap-state.md",
        """# Roadmap

```yaml
roadmap_state_version: 1
next_actionable_task: roadmap.component_runtime_core_baseline
no_actionable_next_task: false
rules:
  do_not_invent_phase13: true
anchors:
  - ssot_anchor: roadmap.phase12
    task_kind: implementation_phase
    title: "Phase 12"
    phase_state: completed
    actionable: false
  - ssot_anchor: roadmap.component_runtime_core_baseline
    task_kind: implementation_task
    title: "CRCB"
    phase_state: accepted
    actionable: true
```
""",
    )
    result = build_implementation_prompt(
        repo_root=tmp_path,
        task_selector="roadmap.component_runtime_core_baseline",
        product_ready=False,
        readiness_summary={
            "product_ready": False,
            "sync_state": "drift",
            "provider_ask_clean": False,
            "blocked_reasons": ["knowledge_sync_state=drift"],
        },
        knowledge_readiness={
            "sync_state": "drift",
            "provider_ask_clean": False,
            "available": True,
            "target_ok": True,
        },
        reconcile_counts={
            "matched": 0,
            "missing": 1,
            "stale": 0,
            "duplicate": 0,
            "conflict": 0,
            "unmanaged": 0,
        },
        apply_plan_counts={"create": 1, "update": 0, "skip": 0, "blocked": 0},
        provider_sync_required=True,
    )
    data = result["data"]
    assert data["implementation_ready"] is False
    assert "Implement:" not in data["prompt"].split("## Selected task anchor")[0]
    assert "owner Project Sources handoff" not in data["prompt"]


def test_chatgpt_project_sources_never_gate_in_closeout_runner():
    deps = _deps(
        status_seq=[
            _status(
                sync_state="drift",
                ask_clean=False,
                provider_sync_required=True,
                product_ready=False,
            )
        ],
        dry_run={
            "ok": True,
            "sync_state": "drift",
            "required_updates_count": 1,
            "operations": [{"op": "replace_required", "doc_id": "a"}],
        },
        desired_ids={"a"},
    )
    env = run_closeout(repo_root=Path("."), apply=False, deps=deps)
    data = env["data"]
    assert data["chatgpt_project_sources"]["product_closeout_gate"] is False
    assert data["next_required_action"] != "update_chatgpt_project_sources"
    assert "UPDATE_CHATGPT_PROJECT_SOURCES" not in [
        a.get("code") for a in data.get("next_actions") or []
    ]
    blocked = " ".join(str(r) for r in data.get("blocked_reasons") or [])
    assert "project_sources" not in blocked.lower()
    assert "chatgpt" not in blocked.lower()


def test_cli_closeout_run_dry_run_wired(monkeypatch, tmp_path, capsys):
    write_control_yaml(tmp_path, minimal_config_dict())
    monkeypatch.chdir(tmp_path)

    def fake_run(*, repo_root, apply=False, deps=None):
        return {
            "ok": True,
            "command": "vibe closeout run",
            "project_id": "migration-harness",
            "mode": "dry-run",
            "mutation": False,
            "data": {
                "closeout_complete": False,
                "implementation_ready": False,
                "next_required_action": "clean_git_status",
                "chatgpt_project_sources": {"product_closeout_gate": False},
            },
            "warnings": [],
            "next_actions": [],
        }

    monkeypatch.setattr("vibe_control.closeout_runner.run_closeout", fake_run)
    code = main(["closeout", "run", "--dry-run", "--json"])
    out = capsys.readouterr().out
    assert code == 0
    assert "vibe closeout run" in out
    assert '"mutation": false' in out
