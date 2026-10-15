"""Vibe Progress / Brief baseline — projection-only readonly surfaces + Evidence v1."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

from vibe_control.cli import main
from vibe_control.progress_brief import build_brief, build_progress


PROGRESS_BRIEF = "roadmap.vibe_progress_brief_baseline"
FORBIDDEN_SECRET_PATTERNS = (
    r"notebooklm://",
    r"Authorization:",
    r"Bearer\s+",
    r"cookie=",
    r"Cookie:",
    r"provider_source_id\s*[:=]",
)


def _git_head(repo_root: Path) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        text=True,
    ).strip()


def _git_status_short(repo_root: Path) -> str:
    return subprocess.check_output(
        ["git", "status", "--short"],
        cwd=repo_root,
        text=True,
    ).strip()


def _assert_no_secrets(blob: str) -> None:
    for pattern in FORBIDDEN_SECRET_PATTERNS:
        assert re.search(pattern, blob, flags=re.IGNORECASE) is None, pattern
    # Raw Beads provider ids look like vibe-control-xxx; hashes are allowed.
    assert "provider_task_id\": \"vibe-control-" not in blob
    assert "\"notebook_ref\"" not in blob


def _fixture_integration(
    *,
    product_ready: bool = True,
    config_ok: bool = True,
    provider_sync_required: bool = False,
    sync_state: str = "synced",
    provider_ask_clean: bool = True,
    task_cache_current: bool = True,
    closeout_complete: bool = True,
    blocked_reasons: list[str] | None = None,
) -> dict:
    return {
        "project_id": "vibe-control",
        "product_ready": product_ready,
        "config_ok": config_ok,
        "provider_sync_required": provider_sync_required,
        "task_cache_current": task_cache_current,
        "closeout_complete": closeout_complete,
        "closeout_state": (
            "no_ssot_change_product_ready" if closeout_complete else "ssot_change_committed_sync_required"
        ),
        "blocked_reasons": list(blocked_reasons or []),
        "knowledge_provider": {
            "available": sync_state != "unavailable",
            "target_ok": sync_state != "unavailable",
            "sync_state": sync_state,
            "provider_ask_clean": provider_ask_clean,
            "ask_hygiene": {
                "condition": "clean" if provider_ask_clean else "current_ssot_drift",
                "provider_ask_clean": provider_ask_clean,
                "sync_state": sync_state,
                "required_updates_count": 0,
                "candidate_count": 0,
                "orphan_managed_count": 0,
                "reasons": [],
            },
        },
        "task_cache": {
            "task_cache_current": task_cache_current,
            "reconcile_counts": {
                "matched": 1 if task_cache_current else 0,
                "missing": 0 if task_cache_current else 1,
                "stale": 0,
                "duplicate": 0,
                "conflict": 0,
                "unmanaged": 0,
            },
            "apply_plan_counts": {
                "create": 0 if task_cache_current else 1,
                "update": 0,
                "skip": 0,
                "blocked": 0,
            },
        },
        "next_actions": [],
        "warnings": [],
    }


def _fixture_next(
    *,
    next_task: str | None = PROGRESS_BRIEF,
    no_next: bool = False,
) -> dict:
    if no_next or next_task is None:
        return {
            "no_actionable_next_task": True,
            "next_actionable_task": None,
            "reason": "no_actionable_anchors",
            "do_not_invent_phase13": True,
        }
    return {
        "no_actionable_next_task": False,
        "next_actionable_task": next_task,
        "anchor": {
            "ssot_anchor": next_task,
            "task_kind": "implementation_task",
            "title": "Vibe Product Interface Slice 1 — readonly Progress / Brief baseline",
            "phase_state": "accepted",
            "actionable": True,
        },
        "do_not_invent_phase13": True,
    }


# --- Progress ---


def test_progress_cli_ok_mutation_false(monkeypatch, capsys):
    monkeypatch.chdir(Path.cwd())
    code = main(["progress", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["ok"] is True
    assert payload.get("mutation") is False
    assert payload["command"] == "vibe progress"
    assert payload["mode"] == "readonly_progress"
    data = payload["data"]
    assert data["schema_version"] == "vibe.progress.v1"
    assert data["mutation"] is False


def test_progress_includes_observed_head_and_git_clean(monkeypatch, capsys):
    root = Path.cwd()
    monkeypatch.chdir(root)
    before = _git_status_short(root)
    code = main(["progress", "--json"])
    after = _git_status_short(root)
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    data = payload["data"]
    assert data["observed_head"] == _git_head(root)
    assert data["git_status_short_empty"] is (before == "")
    assert before == after


def test_progress_shared_fields_equal_integration_status(monkeypatch, capsys):
    monkeypatch.chdir(Path.cwd())
    code_p = main(["progress", "--json"])
    progress = json.loads(capsys.readouterr().out)
    code_i = main(["integration", "status", "--json"])
    integ = json.loads(capsys.readouterr().out)
    assert code_p == 0 and code_i == 0
    pdata = progress["data"]
    idata = integ["data"]
    assert pdata["product_ready"] == idata["product_ready"]
    assert pdata["config_ok"] == idata["config_ok"]
    knowledge_enabled = bool(
        (idata.get("capability_profile") or {}).get("knowledge_enabled")
        if "knowledge_enabled" in (idata.get("capability_profile") or {})
        else ((idata.get("components") or {}).get("knowledge") or {}).get("enabled", True)
    )
    task_enabled = bool(
        (idata.get("capability_profile") or {}).get("task_enabled")
        if "task_enabled" in (idata.get("capability_profile") or {})
        else ((idata.get("components") or {}).get("task") or {}).get("enabled", True)
    )
    if knowledge_enabled:
        assert pdata["provider_ask_clean"] == idata["knowledge_provider"]["provider_ask_clean"]
        assert pdata["sync_state"] == idata["knowledge_provider"]["sync_state"]
    else:
        # Disabled knowledge: Progress projects effective gate values, not raw provider drift.
        assert pdata["provider_ask_clean"] is True
        assert pdata["sync_state"] == "synced"
        assert pdata["knowledge_enabled"] is False
    dirty = not pdata["git_status_short_empty"]
    if dirty:
        # Progress fail-closes closeout/implementation when git is dirty to match
        # closeout dry-run; integration closeout hint may still be true.
        assert pdata["closeout_complete"] is False
        assert pdata["implementation_ready"] is False
        assert "local_modifications_present" in pdata["blocked_reasons"]
    else:
        assert pdata["provider_sync_required"] == idata["provider_sync_required"]
        if task_enabled:
            assert pdata["task_cache_current"] == idata["task_cache_current"]
        else:
            assert pdata["task_cache_current"] is True
        assert pdata["closeout_complete"] == idata["closeout_complete"]
        assert pdata["blocked_reasons"] == idata["blocked_reasons"]


def test_progress_next_fields_equal_implementation_next(monkeypatch, capsys):
    monkeypatch.chdir(Path.cwd())
    code_p = main(["progress", "--json"])
    progress = json.loads(capsys.readouterr().out)
    code_n = main(["implementation", "next", "--json"])
    nxt = json.loads(capsys.readouterr().out)
    assert code_p == 0 and code_n == 0
    pdata = progress["data"]
    ndata = nxt["data"]
    assert pdata["next_actionable_task"] == ndata["next_actionable_task"]
    assert pdata["no_actionable_next_task"] == ndata["no_actionable_next_task"]


def test_progress_closeout_fields_overlap_closeout_dry_run(monkeypatch, capsys):
    root = Path.cwd()
    if _git_status_short(root):
        # Dirty tree: closeout dry-run fail-closes; assert Progress projects that overlay.
        closeout_data = {
            "closeout_complete": False,
            "provider_sync_required": True,
            "sync_state": "drift",
            "provider_ask_clean": False,
            "task_cache_current": False,
            "implementation_ready": False,
        }
        result = build_progress(
            repo_root=root,
            integration_status=_fixture_integration(
                product_ready=True,
                provider_sync_required=False,
                closeout_complete=True,
                task_cache_current=True,
            ),
            next_selection=_fixture_next(),
            closeout_data=closeout_data,
            observed_head=_git_head(root),
            git_status_short=_git_status_short(root),
        )
        pdata = result["data"]
        for key in closeout_data:
            assert pdata[key] == closeout_data[key], key
        return

    monkeypatch.chdir(root)
    code_p = main(["progress", "--json"])
    progress = json.loads(capsys.readouterr().out)
    code_c = main(["closeout", "run", "--dry-run", "--json"])
    closeout = json.loads(capsys.readouterr().out)
    assert code_p == 0 and code_c == 0
    pdata = progress["data"]
    cdata = closeout["data"]
    for key in (
        "closeout_complete",
        "provider_sync_required",
        "sync_state",
        "provider_ask_clean",
        "task_cache_current",
        "implementation_ready",
    ):
        assert pdata[key] == cdata[key], key


def test_progress_does_not_use_recorded_baseline_as_observed_head(tmp_path):
    fake_baseline = "deadbeef" * 5
    fake_head = "cafebabe" * 5
    result = build_progress(
        repo_root=tmp_path,
        integration_status=_fixture_integration(),
        next_selection=_fixture_next(),
        observed_head=fake_head,
        git_status_short="",
        recorded_baseline_commit=fake_baseline,
    )
    data = result["data"]
    assert data["observed_head"] == fake_head
    assert data["observed_head"] != fake_baseline
    assert data["recorded_baseline_commit"] == fake_baseline
    assert data["observed_head"] != data["recorded_baseline_commit"]


def test_progress_provider_unavailable_is_not_empty_inventory(tmp_path):
    integ = _fixture_integration(
        product_ready=False,
        sync_state="unavailable",
        provider_ask_clean=False,
        provider_sync_required=True,
        closeout_complete=False,
        task_cache_current=False,
        blocked_reasons=["knowledge_unavailable"],
    )
    integ["knowledge_provider"]["available"] = False
    integ["knowledge_provider"]["target_ok"] = False
    # Explicitly empty inventory must still surface unavailable, not "clean empty".
    integ["knowledge_provider"]["inventory_count"] = 0
    result = build_progress(
        repo_root=tmp_path,
        integration_status=integ,
        next_selection=_fixture_next(no_next=True),
        observed_head="abc",
        git_status_short="",
    )
    data = result["data"]
    assert data["sync_state"] == "unavailable"
    assert data["product_ready"] is False
    assert data["knowledge_available"] is False
    assert "empty" not in str(data.get("safe_next_action") or {}).lower()
    assert data["provider_ask_clean"] is False


def test_progress_redacts_secrets_and_raw_provider_ids(tmp_path):
    integ = _fixture_integration()
    integ["secret_notebook_ref"] = "notebooklm://secret-notebook-ref"
    integ["raw_cookie"] = "cookie=abc"
    integ["Authorization"] = "Bearer tok"
    result = build_progress(
        repo_root=tmp_path,
        integration_status=integ,
        next_selection=_fixture_next(),
        observed_head="abc",
        git_status_short="",
    )
    blob = json.dumps(result, ensure_ascii=False)
    _assert_no_secrets(blob)
    assert "notebooklm://secret-notebook-ref" not in blob
    assert "Bearer tok" not in blob


# --- Brief ---


def test_brief_cli_ok_mutation_false(monkeypatch, capsys):
    monkeypatch.chdir(Path.cwd())
    code = main(["brief", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["ok"] is True
    assert payload.get("mutation") is False
    assert payload["command"] == "vibe brief"
    assert payload["mode"] == "readonly_brief"
    data = payload["data"]
    assert data["brief_version"] == "vibe.brief.v1"
    assert data["mutation"] is False


def test_brief_returns_current_task_when_actionable(tmp_path):
    result = build_brief(
        repo_root=tmp_path,
        integration_status=_fixture_integration(),
        next_selection=_fixture_next(),
        observed_head="abc",
        git_status_short="",
    )
    data = result["data"]
    assert data["implementation_ready"] is True
    assert data["task"]["ssot_anchor"] == PROGRESS_BRIEF
    assert data["task"]["actionable"] is True
    assert "implementation prompt" in (data.get("summary") or "").lower() or (
        "vibe implementation prompt" in json.dumps(data.get("safe_next_action"))
    )


def test_brief_points_to_implementation_prompt_when_ready(tmp_path):
    result = build_brief(
        repo_root=tmp_path,
        integration_status=_fixture_integration(),
        next_selection=_fixture_next(),
        observed_head="abc",
        git_status_short="",
    )
    data = result["data"]
    assert data["implementation_ready"] is True
    safe = data["safe_next_action"]
    assert "implementation prompt" in safe["command"]
    assert PROGRESS_BRIEF in safe["command"]
    codes = [a["code"] for a in data["next_actions"] if isinstance(a, dict)]
    assert "IMPLEMENTATION_PROMPT" in codes


def test_brief_handles_no_actionable_task(tmp_path):
    result = build_brief(
        repo_root=tmp_path,
        integration_status=_fixture_integration(),
        next_selection=_fixture_next(no_next=True),
        observed_head="abc",
        git_status_short="",
    )
    data = result["data"]
    assert data["no_actionable_next_task"] is True
    assert data["task"] is None
    assert data["implementation_ready"] is False
    assert data["safe_next_action"]["code"] == "NO_ACTIONABLE_NEXT_TASK"


def test_brief_handles_blocked_readiness(tmp_path):
    result = build_brief(
        repo_root=tmp_path,
        integration_status=_fixture_integration(
            product_ready=False,
            provider_sync_required=True,
            sync_state="drift",
            provider_ask_clean=False,
            closeout_complete=False,
            task_cache_current=False,
            blocked_reasons=["knowledge_sync_state=drift", "task_cache_not_current"],
        ),
        next_selection=_fixture_next(),
        observed_head="abc",
        git_status_short="",
    )
    data = result["data"]
    assert data["implementation_ready"] is False
    assert data["safe_next_action"]["code"] in {
        "RUN_BOUNDED_KNOWLEDGE_SYNC",
        "SSOT_CLOSEOUT_INCOMPLETE",
        "TASK_CONVERGENCE_REQUIRED",
    }
    assert data["principal_blocker"] == "knowledge_sync_state=drift"
    assert "Implement:" not in (data.get("summary") or "")
    assert "Principal blocker:" in (data.get("summary") or "")


def test_derive_principal_blocker_prefers_matching_reason():
    from vibe_control.progress_brief import derive_principal_blocker

    shared = {
        "blocked_reasons": [
            "task_cache_not_current",
            "knowledge_sync_state=drift",
        ]
    }
    safe = {"code": "RUN_BOUNDED_KNOWLEDGE_SYNC"}
    assert derive_principal_blocker(shared, safe) == "knowledge_sync_state=drift"


def test_derive_principal_blocker_none_when_implementation_prompt():
    from vibe_control.progress_brief import derive_principal_blocker

    assert (
        derive_principal_blocker(
            {"blocked_reasons": []},
            {"code": "IMPLEMENTATION_PROMPT"},
        )
        is None
    )


def test_derive_principal_blocker_fallback_without_reasons():
    from vibe_control.progress_brief import derive_principal_blocker

    assert (
        derive_principal_blocker(
            {"blocked_reasons": []},
            {"code": "NO_ACTIONABLE_NEXT_TASK"},
        )
        == "no_actionable_next_task"
    )

@pytest.mark.parametrize(
    "kwargs",
    [
        {"provider_sync_required": True, "closeout_complete": False, "sync_state": "drift"},
        {"provider_ask_clean": False, "closeout_complete": False, "sync_state": "synced"},
        {
            "task_cache_current": False,
            "product_ready": False,
            "closeout_complete": False,
        },
        {"closeout_complete": False, "provider_sync_required": True},
    ],
)
def test_brief_does_not_greenlight_when_gates_fail(tmp_path, kwargs):
    integ = _fixture_integration(blocked_reasons=["blocked"], **kwargs)
    if kwargs.get("product_ready") is not False:
        integ["product_ready"] = False
    result = build_brief(
        repo_root=tmp_path,
        integration_status=integ,
        next_selection=_fixture_next(),
        observed_head="abc",
        git_status_short="",
    )
    assert result["data"]["implementation_ready"] is False
    assert result["data"]["safe_next_action"]["code"] != "IMPLEMENTATION_PROMPT"


def test_brief_is_shorter_than_implementation_prompt_and_has_constraints(monkeypatch, capsys):
    monkeypatch.chdir(Path.cwd())
    code_b = main(["brief", "--json"])
    brief = json.loads(capsys.readouterr().out)
    assert code_b == 0
    code_n = main(["implementation", "next", "--json"])
    nxt = json.loads(capsys.readouterr().out)
    assert code_n == 0
    assert (nxt.get("data") or {}).get("no_actionable_next_task") is True
    # No actionable next: compare Brief core against a completed-task prompt envelope.
    code_p = main(
        ["implementation", "prompt", "--task", "roadmap.vibe_operation_recovery_design", "--json"]
    )
    prompt = json.loads(capsys.readouterr().out)
    assert code_p == 0
    bdata = brief["data"]
    pdata = prompt["data"]
    assert pdata.get("task_completed") is True
    assert pdata.get("do_not_restart") is True
    # Compare Brief's agent-facing fields (exclude Evidence S1 overhead) to prompt text.
    core = {
        k: v
        for k, v in bdata.items()
        if k not in ("evidence", "evidence_hash")
    }
    brief_text = json.dumps(core, ensure_ascii=False)
    prompt_text = pdata.get("prompt") or ""
    assert len(brief_text) < len(prompt_text) or "No actionable next task" in (bdata.get("summary") or "")
    assert "prompt_sections" not in bdata
    assert isinstance(bdata.get("constraints"), list) and bdata["constraints"]
    assert isinstance(bdata.get("required_checks"), list) and bdata["required_checks"]
    assert isinstance(bdata.get("approval_requirements"), list) and bdata["approval_requirements"]
    cg = bdata.get("capability_guidance") or {}
    assert cg.get("concise") is True
    assert cg.get("engine_readiness_separate") is True


def test_brief_optional_text_format(monkeypatch, capsys):
    monkeypatch.chdir(Path.cwd())
    code = main(["brief", "--format", "text"])
    out = capsys.readouterr().out
    assert code == 0
    assert "Vibe Brief" in out or "brief" in out.lower()
    assert PROGRESS_BRIEF in out or "safe_next_action" in out or "Implement" in out or "next" in out


# --- Evidence / S1 ---


def test_evidence_fields_present_and_readonly(tmp_path):
    result = build_progress(
        repo_root=tmp_path,
        integration_status=_fixture_integration(),
        next_selection=_fixture_next(),
        observed_head="abc123",
        git_status_short="",
        run_id="run-fixed-1",
    )
    evidence = result["data"]["evidence"]
    assert evidence["evidence_version"] == "vibe.evidence.v1"
    assert evidence["run_id"] == "run-fixed-1"
    assert evidence["operation"] == "progress"
    assert evidence["mode"] == "readonly_progress"
    assert evidence["observed_head"] == "abc123"
    assert evidence["git_status_short_empty"] is True
    assert evidence["mutation_intent"] is False
    assert evidence["mutation_performed"] is False
    assert evidence["approval_class"] == "readonly"
    assert isinstance(evidence["steps"], list) and evidence["steps"]
    assert isinstance(evidence["generated_from"], list)
    assert "vibe integration status" in evidence["generated_from"]
    assert "vibe implementation next" in evidence["generated_from"]
    assert str(evidence["evidence_hash"]).startswith("sha256:")


def test_evidence_hash_deterministic(tmp_path):
    kwargs = dict(
        repo_root=tmp_path,
        integration_status=_fixture_integration(),
        next_selection=_fixture_next(),
        observed_head="abc123",
        git_status_short="",
        run_id="run-fixed-2",
    )
    a = build_progress(**kwargs)["data"]["evidence"]["evidence_hash"]
    b = build_progress(**kwargs)["data"]["evidence"]["evidence_hash"]
    assert a == b


def test_evidence_not_persisted_as_repo_truth(tmp_path):
    before = list(tmp_path.rglob("*"))
    build_progress(
        repo_root=tmp_path,
        integration_status=_fixture_integration(),
        next_selection=_fixture_next(),
        observed_head="abc",
        git_status_short="",
    )
    after = list(tmp_path.rglob("*"))
    assert before == after


def test_brief_evidence_operation_is_brief(tmp_path):
    result = build_brief(
        repo_root=tmp_path,
        integration_status=_fixture_integration(),
        next_selection=_fixture_next(),
        observed_head="abc",
        git_status_short="",
        run_id="run-brief-1",
    )
    evidence = result["data"]["evidence"]
    assert evidence["operation"] == "brief"
    assert evidence["mode"] == "readonly_brief"
    assert evidence["mutation_intent"] is False
    assert evidence["mutation_performed"] is False
    blob = json.dumps(result, ensure_ascii=False)
    _assert_no_secrets(blob)


# --- Regression anchors ---


def test_component_runtime_slices_still_completed():
    from vibe_control.task.roadmap_state import load_roadmap_state

    state = load_roadmap_state(Path.cwd())
    by = {a["ssot_anchor"]: a for a in state["anchors"]}
    for anchor in (
        "roadmap.component_runtime_core_baseline",
        "roadmap.component_runtime_doctor_prompt_awareness",
        "roadmap.component_runtime_template_init_preview_guidance",
        "roadmap.component_runtime_readonly_adoption_detect",
        "roadmap.component_runtime_future_provider_integration",
    ):
        assert by[anchor]["phase_state"] == "completed"
        assert by[anchor]["actionable"] is False
    assert "roadmap.phase13" not in by
    assert state["next_actionable_task"] is None
