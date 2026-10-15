"""Evidence hardening — S1 schema consistency, determinism, redaction, projection-only."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from vibe_control.describe import build_describe
from vibe_control.evidence import (
    EVIDENCE_CLASS,
    EVIDENCE_VERSION,
    assert_no_forbidden_evidence_secrets,
    build_evidence_v1,
)
from vibe_control.gateway import route_gateway
from vibe_control.progress_brief import build_brief, build_progress


def _fixture_integration(**overrides):
    base = {
        "project_id": "vibe-control",
        "product_ready": True,
        "config_ok": True,
        "provider_sync_required": False,
        "task_cache_current": True,
        "closeout_complete": True,
        "closeout_state": "no_ssot_change_product_ready",
        "blocked_reasons": [],
        "knowledge_provider": {
            "available": True,
            "target_ok": True,
            "sync_state": "synced",
            "provider_ask_clean": True,
            "ask_hygiene": {
                "condition": "clean",
                "provider_ask_clean": True,
                "sync_state": "synced",
                "required_updates_count": 0,
                "candidate_count": 0,
                "orphan_managed_count": 0,
                "reasons": [],
            },
        },
        "task_cache": {
            "task_cache_current": True,
            "reconcile_counts": {
                "matched": 1,
                "missing": 0,
                "stale": 0,
                "duplicate": 0,
                "conflict": 0,
                "unmanaged": 0,
            },
            "apply_plan_counts": {
                "create": 0,
                "update": 0,
                "delete": 0,
                "skip": 0,
            },
        },
        "warnings": [],
        "next_actions": [],
    }
    base.update(overrides)
    return base


def _fixture_next(task="roadmap.vibe_evidence_hardening"):
    return {
        "no_actionable_next_task": False,
        "next_actionable_task": task,
        "anchor": {
            "ssot_anchor": task,
            "title": "Evidence hardening",
            "task_kind": "implementation_task",
            "phase_state": "accepted",
            "actionable": True,
        },
    }


def _common_kwargs(tmp_path, **extra):
    kwargs = dict(
        repo_root=tmp_path,
        integration_status=_fixture_integration(),
        next_selection=_fixture_next(),
        observed_head="deadbeef01",
        git_status_short="",
        recorded_baseline_commit="baseline00",
        run_id="run-evidence-1",
    )
    kwargs.update(extra)
    return kwargs


def test_evidence_schema_on_progress_brief_describe(tmp_path):
    progress = build_progress(**_common_kwargs(tmp_path))
    brief = build_brief(**_common_kwargs(tmp_path, run_id="run-brief"))
    describe = build_describe(
        repo_root=tmp_path,
        progress_envelope=progress,
        observed_head="deadbeef01",
        git_status_short="",
        run_id="run-describe",
    )
    for result, op in (
        (progress, "progress"),
        (brief, "brief"),
        (describe, "describe"),
    ):
        evidence = result["data"]["evidence"]
        assert evidence["evidence_version"] == EVIDENCE_VERSION
        assert evidence["evidence_class"] == EVIDENCE_CLASS
        assert evidence["operation"] == op
        assert evidence["generated_from"]
        assert evidence["source_surfaces"] == evidence["generated_from"]
        assert evidence["run_id"]
        assert evidence["base_head"] == "deadbeef01"
        assert evidence["observed_head"] == "deadbeef01"
        assert evidence["recorded_baseline_commit"] == "baseline00"
        assert evidence["observed_head_vs_baseline"]["same"] is False
        assert evidence["mutation"] is False
        assert evidence["mutation_intent"] is False
        assert evidence["mutation_performed"] is False
        assert evidence["provider_mutation"] is False
        assert evidence["task_mutation"] is False
        assert evidence["config_mutation"] is False
        assert evidence["persisted"] is False
        assert evidence["source_of_truth"] == "engine"
        assert evidence["facts_class"] == "projected"
        assert evidence["trajectory_bounded"] is True
        assert evidence["redaction"]["applied"] is True
        assert "advisor" in evidence["redaction"]["chatgpt_project_sources"]
        assert str(evidence["evidence_hash"]).startswith("sha256:")


def test_evidence_hash_deterministic_and_excludes_run_id(tmp_path):
    a = build_evidence_v1(
        operation="progress",
        mode="readonly_progress",
        observed_head_value="abc",
        git_status_short_empty=True,
        generated_from=["x"],
        steps=["s1"],
        blocked_reasons=[],
        next_actions=[],
        run_id="run-a",
        recorded_baseline_commit="base",
    )
    b = build_evidence_v1(
        operation="progress",
        mode="readonly_progress",
        observed_head_value="abc",
        git_status_short_empty=True,
        generated_from=["x"],
        steps=["s1"],
        blocked_reasons=[],
        next_actions=[],
        run_id="run-b",
        recorded_baseline_commit="base",
    )
    assert a["run_id"] != b["run_id"]
    assert a["evidence_hash"] == b["evidence_hash"]


def test_evidence_hash_changes_when_material_inputs_change():
    base_kw = dict(
        operation="progress",
        mode="readonly_progress",
        observed_head_value="abc",
        git_status_short_empty=True,
        generated_from=["x"],
        steps=["s1"],
        blocked_reasons=[],
        next_actions=[],
        run_id="same",
        recorded_baseline_commit="base",
    )
    a = build_evidence_v1(**base_kw)
    b = build_evidence_v1(**{**base_kw, "observed_head_value": "xyz"})
    assert a["evidence_hash"] != b["evidence_hash"]


def test_evidence_not_persisted(tmp_path):
    before = list(tmp_path.rglob("*"))
    build_progress(**_common_kwargs(tmp_path))
    build_brief(**_common_kwargs(tmp_path))
    after = list(tmp_path.rglob("*"))
    assert before == after


def test_observed_head_distinguished_from_baseline(tmp_path):
    result = build_progress(
        **_common_kwargs(
            tmp_path,
            observed_head="observed-head",
            recorded_baseline_commit="recorded-baseline",
        )
    )
    evidence = result["data"]["evidence"]
    assert evidence["observed_head"] == "observed-head"
    assert evidence["recorded_baseline_commit"] == "recorded-baseline"
    assert evidence["observed_head"] != evidence["recorded_baseline_commit"]
    assert evidence["observed_head_vs_baseline"]["same"] is False
    assert result["data"]["observed_head"] == "observed-head"
    assert result["data"]["recorded_baseline_commit"] == "recorded-baseline"


def test_evidence_projects_engine_fields_without_recompute(tmp_path):
    status = _fixture_integration(blocked_reasons=["example_block"])
    result = build_progress(**_common_kwargs(tmp_path, integration_status=status))
    evidence = result["data"]["evidence"]
    projected = evidence["projected"]
    assert projected["product_ready"] is True
    assert projected["provider_sync_required"] is False
    assert projected["provider_ask_clean"] is True
    assert projected["task_cache_current"] is True
    assert projected["implementation_ready"] is result["data"]["implementation_ready"]
    assert projected["blocked_reasons"] == result["data"]["blocked_reasons"]
    assert "product_ready" not in evidence


def test_evidence_preserves_ssot_anchor_identity(tmp_path):
    result = build_brief(**_common_kwargs(tmp_path))
    task = result["data"]["task"]
    assert task["ssot_anchor"] == "roadmap.vibe_evidence_hardening"
    assert "provider_task_id" not in (task or {})


def test_evidence_redacts_secrets_and_raw_ids():
    evidence = build_evidence_v1(
        operation="progress",
        mode="readonly_progress",
        observed_head_value="abc",
        git_status_short_empty=True,
        generated_from=["notebooklm://secret-notebook", "ok"],
        steps=["step"],
        blocked_reasons=[
            "Authorization: Bearer tokensecret",
            "cookie=sessioncookie",
            "provider_source_id=src-123",
            "raw vibe-control-abc123xyz",
        ],
        next_actions=[
            {
                "code": "X",
                "command": "vibe progress --json",
                "reason": "Bearer leaked-token-value",
            }
        ],
        run_id="r1",
    )
    blob = json.dumps(evidence, ensure_ascii=False)
    assert_no_forbidden_evidence_secrets(blob)
    assert "notebooklm://" not in blob
    assert "tokensecret" not in blob
    assert "sessioncookie" not in blob
    assert "src-123" not in blob
    assert "vibe-control-abc123xyz" not in blob
    assert "[REDACTED_NOTEBOOK_REF]" in blob
    assert "[REDACTED_PROVIDER_TASK_ID]" in blob


def test_progress_brief_redaction_surface(tmp_path):
    status = _fixture_integration(
        blocked_reasons=["leak notebooklm://nb-1 and Bearer secret-token"]
    )
    progress = build_progress(**_common_kwargs(tmp_path, integration_status=status))
    blob = json.dumps(progress["data"]["evidence"], ensure_ascii=False)
    assert_no_forbidden_evidence_secrets(blob)
    assert "notebooklm://" not in blob
    assert "secret-token" not in blob


def test_project_sources_advisor_only_in_evidence():
    evidence = build_evidence_v1(
        operation="describe",
        mode="readonly_describe",
        observed_head_value="h",
        git_status_short_empty=True,
        generated_from=["engine"],
        steps=["s"],
        blocked_reasons=[],
        next_actions=[],
    )
    assert evidence["source_of_truth"] == "engine"
    note = evidence["redaction"]["chatgpt_project_sources"]
    assert "advisor" in note
    assert "not product truth" in note


def test_gateway_attaches_hardened_evidence(tmp_path):
    progress = build_progress(**_common_kwargs(tmp_path))

    def _progress(**_kw):
        return progress

    result = route_gateway(
        intent="status",
        repo_root=tmp_path,
        delegates={"progress": _progress},
    )
    evidence = result["data"]["evidence"]
    assert evidence["operation"] == "gateway"
    assert evidence["evidence_class"] == EVIDENCE_CLASS
    assert evidence["mutation"] is False
    assert evidence["persisted"] is False
    assert evidence["source_of_truth"] == "engine"
    assert result["data"]["mutation"] is False
    assert result["mutation"] is False


def test_evidence_paths_do_not_call_apply_or_bd(tmp_path):
    forbidden = []

    def _guard(cmd, *args, **kwargs):
        joined = " ".join(str(c) for c in (cmd if isinstance(cmd, (list, tuple)) else [cmd]))
        for needle in (
            "closeout run --apply",
            "task apply --apply",
            "nlm ",
            "notebooklm",
            "bd ",
            "task cache reset",
        ):
            if needle in joined:
                forbidden.append(joined)
        import subprocess as sp

        return sp.CompletedProcess(cmd, 0, stdout="", stderr="")

    with patch("subprocess.run", side_effect=_guard):
        build_progress(
            repo_root=tmp_path,
            integration_status=_fixture_integration(),
            next_selection=_fixture_next(),
            observed_head="h",
            git_status_short="",
            recorded_baseline_commit="b",
            run_id="r",
        )
        build_brief(
            repo_root=tmp_path,
            integration_status=_fixture_integration(),
            next_selection=_fixture_next(),
            observed_head="h",
            git_status_short="",
            recorded_baseline_commit="b",
            run_id="r",
        )
    assert forbidden == []


def test_roadmap_promotes_recovery_after_capability_track_complete():
    from vibe_control.task.roadmap_state import load_roadmap_state

    state = load_roadmap_state(Path.cwd())
    by = {a["ssot_anchor"]: a for a in state["anchors"]}
    assert by["roadmap.vibe_evidence_hardening"]["phase_state"] == "completed"
    assert by["roadmap.vibe_product_concept_boundary_contract"]["phase_state"] == "completed"
    assert by["roadmap.vibe_product_concept_boundary_contract"]["actionable"] is False
    assert by["roadmap.vibe_capability_profile_runtime"]["phase_state"] == "completed"
    assert by["roadmap.vibe_capability_profile_runtime"]["actionable"] is False
    assert by["roadmap.vibe_capability_profile_doctor_gateway_guidance"]["phase_state"] == "completed"
    assert by["roadmap.vibe_capability_profile_doctor_gateway_guidance"]["actionable"] is False
    assert by["roadmap.vibe_operation_recovery_design"]["phase_state"] == "completed"
    assert by["roadmap.vibe_operation_recovery_design"]["actionable"] is False
    assert state["next_actionable_task"] is None
    assert "roadmap.phase13" not in by


def test_accepted_scope_documented_in_ssot():
    text = Path("docs/project/vibe-control-roadmap-state.md").read_text(encoding="utf-8")
    assert "roadmap.vibe_evidence_hardening" in text
    assert "strengthened Vibe Evidence schema/report consistency" in text
    assert "redaction hardening" in text
    assert "bounded trajectory fields" in text
    assert "S1 Ephemeral Operation Snapshot preserved" in text
    assert "persistent ledger" in text
    assert "workflow replay engine" in text
    assert "roadmap.vibe_operation_recovery_design" in text
    assert "roadmap.vibe_product_concept_boundary_contract" in text
    assert "roadmap.vibe_capability_profile_runtime" in text
    assert "roadmap.vibe_capability_profile_install_init_guidance" in text
    assert "roadmap.vibe_operation_recovery_design" in text
    assert "product concept boundary explicit and test-covered" in text
    assert "runtime explicitly unchanged until capability profile runtime slice" in text
