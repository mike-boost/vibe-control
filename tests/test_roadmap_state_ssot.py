"""Roadmap-state SSOT — inventory, projection, next selection, completed prompt."""

from __future__ import annotations

import json
from pathlib import Path

from helpers import write_doc
from vibe_control.config import load_config
from vibe_control.implementation.prompt import build_implementation_prompt
from vibe_control.knowledge.corpus import build_desired_corpus
from vibe_control.task.projection import (
    next_actionable_selection,
    project_actionable_expected_tasks,
    project_all_expected_tasks,
)
from vibe_control.task.roadmap_state import load_roadmap_state

SLICE2 = "roadmap.component_runtime_doctor_prompt_awareness"
SLICE3 = "roadmap.component_runtime_template_init_preview_guidance"
SLICE4 = "roadmap.component_runtime_readonly_adoption_detect"
SLICE5 = "roadmap.component_runtime_future_provider_integration"
CRCB = "roadmap.component_runtime_core_baseline"
PROGRESS_BRIEF = "roadmap.vibe_progress_brief_baseline"
GATEWAY = "roadmap.vibe_gateway_thin_router_contract"
DESCRIBE = "roadmap.vibe_describe_control_surface"
EVIDENCE = "roadmap.vibe_evidence_hardening"
RECOVERY = "roadmap.vibe_operation_recovery_design"
CONCEPT = "roadmap.vibe_product_concept_boundary_contract"
CAP_RUNTIME = "roadmap.vibe_capability_profile_runtime"
CAP_INSTALL = "roadmap.vibe_capability_profile_install_init_guidance"
CAP_DOCTOR = "roadmap.vibe_capability_profile_doctor_gateway_guidance"


def test_roadmap_state_file_loads_in_repo():
    root = Path.cwd()
    state = load_roadmap_state(root)
    assert state["no_actionable_next_task"] is True
    assert state["next_actionable_task"] is None
    assert state["rules"]["do_not_invent_phase13"] is True
    by = {a["ssot_anchor"]: a for a in state["anchors"]}
    assert "roadmap.phase13" not in by
    assert by["roadmap.phase11a"]["actionable"] is False
    assert by["roadmap.phase11b"]["actionable"] is False
    assert by["roadmap.phase12"]["phase_state"] == "completed"
    assert by["roadmap.phase12"]["actionable"] is False
    scope = by["roadmap.phase12"]["completed_scope"]
    assert "implementation prompt generator" in scope
    assert "Phase 12 sample prompt validated" in scope
    crcb = by[CRCB]
    assert crcb["task_kind"] == "implementation_task"
    assert crcb["title"] == "Component Runtime Core Baseline Slice 1"
    assert crcb["phase_state"] == "completed"
    assert crcb["actionable"] is False
    crcb_scope = crcb["completed_scope"]
    assert "fixed component catalog (knowledge, task, sdd, tdd)" in crcb_scope
    assert "product_ready requires config_ok=true" in crcb_scope
    s2 = by[SLICE2]
    assert s2["phase_state"] == "completed"
    assert s2["actionable"] is False
    s2_scope = s2["completed_scope"]
    assert "vibe doctor surfaces config_ok, components, component blocked_reasons" in s2_scope
    assert "config_ok=false blocks implementation greenlight (no Implement: / equivalent)" in s2_scope
    s3 = by[SLICE3]
    assert s3["phase_state"] == "completed"
    assert s3["actionable"] is False
    s3_scope = s3["completed_scope"]
    assert "template/init-preview guidance for valid components.<id>.enabled shape" in s3_scope
    assert "invalid config examples diagnostic-only" in s3_scope
    assert "focused template/init-preview guidance tests" in s3_scope
    s4 = by[SLICE4]
    assert s4["phase_state"] == "completed"
    assert s4["actionable"] is False
    s4_scope = s4["completed_scope"]
    assert "readonly detection/reporting for component-adjacent tools/surfaces" in s4_scope
    assert "advisory/diagnostic only" in s4_scope
    assert "detected candidate is not adopted and not provider-bound" in s4_scope
    assert "focused readonly adoption detection tests" in s4_scope
    s5 = by[SLICE5]
    assert s5["phase_state"] == "completed"
    assert s5["actionable"] is False
    s5_scope = s5["completed_scope"]
    assert "minimal provider-boundary preparation" in s5_scope
    assert "explicit fail-closed mutation boundaries" in s5_scope
    assert "provider_hints are not active providers" in s5_scope
    assert "unsupported provider integration fails closed" in s5_scope
    progress = by[PROGRESS_BRIEF]
    assert progress["task_kind"] == "implementation_task"
    assert progress["phase_state"] == "completed"
    assert progress["actionable"] is False
    progress_scope = progress["completed_scope"]
    assert "vibe progress --json" in progress_scope
    assert "vibe brief --json" in progress_scope
    assert "optional vibe brief --format text" in progress_scope
    assert "Progress projects existing Engine outputs only" in progress_scope
    assert "focused Progress / Brief tests" in progress_scope
    gateway = by[GATEWAY]
    assert gateway["phase_state"] == "completed"
    assert gateway["actionable"] is False
    gateway_scope = gateway["completed_scope"]
    assert "vibe gateway --intent ... --json thin intent router" in gateway_scope
    assert any("delegates to existing Engine surfaces only" in item for item in gateway_scope)
    assert any("focused Gateway thin-router tests" in item for item in gateway_scope)
    describe = by[DESCRIBE]
    assert describe["phase_state"] == "completed"
    assert describe["actionable"] is False
    describe_scope = describe["completed_scope"]
    assert "vibe describe --json" in describe_scope
    assert "readonly control-surface description" in describe_scope
    assert "static/projection-only source policy" in describe_scope
    assert "focused Describe tests" in describe_scope
    evidence = by[EVIDENCE]
    assert evidence["phase_state"] == "completed"
    assert evidence["actionable"] is False
    evidence_scope = evidence["completed_scope"]
    assert "strengthened Vibe Evidence schema/report consistency" in evidence_scope
    assert "redaction hardening" in evidence_scope
    assert "bounded trajectory fields" in evidence_scope
    assert "S1 Ephemeral Operation Snapshot preserved" in evidence_scope
    assert "no persistent ledger" in evidence_scope
    assert "no workflow replay engine" in evidence_scope
    assert "focused evidence tests" in evidence_scope
    recovery = by[RECOVERY]
    assert recovery["phase_state"] == "completed"
    assert recovery["actionable"] is False
    assert recovery["design_only"] is True
    recovery_scope = recovery["completed_scope"]
    assert "design evaluation completed" in recovery_scope
    assert "no S2 implementation" in recovery_scope
    assert "S1 remains sufficient for current observable recovery needs" in recovery_scope
    assert "future S2 requires separate owner acceptance" in recovery_scope
    concept = by[CONCEPT]
    assert concept["phase_state"] == "completed"
    assert concept["actionable"] is False
    concept_scope = concept["completed_scope"]
    assert "product concept boundary explicit and test-covered" in concept_scope
    assert "target Capability Profile contract (all disabled by default)" in concept_scope
    assert "runtime explicitly unchanged until capability profile runtime slice" in concept_scope
    cap_runtime = by[CAP_RUNTIME]
    assert cap_runtime["phase_state"] == "completed"
    assert cap_runtime["actionable"] is False
    cap_scope = cap_runtime["completed_scope"]
    assert "runtime default-disabled capability profile" in cap_scope
    assert "knowledge/task available but disabled by default" in cap_scope
    assert "disabled capabilities do not fail product readiness" in cap_scope
    assert "enabled knowledge checks NotebookLM readiness/sync/ask hygiene" in cap_scope
    assert "enabled task checks Beads/provider/cache readiness" in cap_scope
    assert "sdd/tdd enabled fail closed as not implemented/unsupported" in cap_scope
    assert "unknown/provider-scoped component ids fail closed" in cap_scope
    assert "Engine readiness separate from capability readiness" in cap_scope
    assert "projections do not implement second readiness engine" in cap_scope
    assert "focused capability profile runtime tests" in cap_scope
    install = by[CAP_INSTALL]
    assert install["phase_state"] == "completed"
    assert install["actionable"] is False
    install_scope = install["completed_scope"]
    assert "fresh/default disabled profile guidance" in install_scope
    assert "knowledge/task available + enable/config guidance" in install_scope
    assert "sdd/tdd not_implemented guidance" in install_scope
    assert "invalid examples diagnostic-only" in install_scope
    assert "no provider mutation / no install/adapt/uninstall" in install_scope
    assert "focused install/init/profile guidance tests" in install_scope
    doctor = by[CAP_DOCTOR]
    assert doctor["phase_state"] == "completed"
    assert doctor["actionable"] is False
    doctor_scope = doctor["completed_scope"]
    assert "doctor/gateway/describe surfaces explain Engine vs capability readiness" in doctor_scope
    assert "next_actions for enable prerequisites without becoming SSOT/roadmap managers" in doctor_scope
    assert "redaction and mutation=false preserved on readonly paths" in doctor_scope
    assert "progress/brief expose concise capability guidance" in doctor_scope
    assert "gateway thin-routes Engine capability_guidance without recomputation" in doctor_scope
    assert "focused doctor/gateway/describe/progress/brief guidance tests" in doctor_scope
    roadmap_text = Path("docs/project/vibe-control-roadmap-state.md").read_text(encoding="utf-8")
    spec_text = Path("docs/project/vibe-control-spec.md").read_text(encoding="utf-8")
    assert "design_only: true" in roadmap_text
    assert "vibe progress --json" in roadmap_text
    assert "Capability Profile" in spec_text
    assert "SSOT manager" in spec_text or "SSOT management product" in spec_text
    assert "roadmap manager" in spec_text
    assert "workflow engine" in spec_text
    assert "all capabilities disabled" in spec_text or "all capabilities disabled by default" in spec_text
    assert "does NOT own generic SSOT management" in spec_text
    assert "thin routers to Engine surfaces" in spec_text
    assert "runtime unchanged until" in spec_text
    assert Path(
        "docs/project/sync/vibe-product-concept-capability-profile-tdd-plan.md"
    ).is_file()
    assert "fresh_default_profile" in Path(
        "docs/project/sync/vibe-product-concept-capability-profile-tdd-plan.md"
    ).read_text(encoding="utf-8")
    assert "vibe brief --json" in roadmap_text
    assert "Evidence v1 / S1 ephemeral operation snapshot fields" in roadmap_text
    assert "vibe gateway --intent" in roadmap_text
    assert "vibe describe --json" in roadmap_text
    assert f"sequence_after: {PROGRESS_BRIEF}" in roadmap_text
    assert f"sequence_after: {GATEWAY}" in roadmap_text
    assert f"sequence_after: {DESCRIBE}" in roadmap_text
    assert f"sequence_after: {CONCEPT}" in roadmap_text
    assert f"sequence_after: {CAP_RUNTIME}" in roadmap_text
    assert f"sequence_after: {CAP_INSTALL}" in roadmap_text
    assert f"sequence_after: {CAP_DOCTOR}" in roadmap_text
    assert "roadmap.vibe_product_concept_boundary_contract" in roadmap_text
    assert "roadmap.vibe_capability_profile_runtime" in roadmap_text
    baseline = state["current_baseline"]
    assert baseline is not None
    assert baseline["baseline_state"] == "stable"
    assert baseline["last_closeout_verdict"] == "STABLE_BASELINE_ACCEPTED"
    assert baseline["baseline_commit"] == "92699f9"
    assert baseline["git_pushed"] is False
    snap = baseline["status_snapshot"]
    assert snap["product_ready"] is True
    assert snap["provider_sync_required"] is False
    assert snap["task_cache_current"] is True
    # Historical baseline snapshot may still record a prior empty-next moment.
    assert snap["no_actionable_next_task"] is True


def test_inventory_includes_roadmap_state_not_sync_or_decision_log_by_default():
    root = Path.cwd()
    config = load_config(root)
    corpus = build_desired_corpus(config, repo_root=root)
    paths = [d.path for d in corpus.documents]
    assert "docs/project/vibe-control-spec.md" in paths
    assert "docs/project/vibe-control-knowledge-spec.md" in paths
    assert "docs/project/vibe-control-task-spec.md" in paths
    assert "docs/project/vibe-control-roadmap-state.md" in paths
    assert "docs/project/DECISION_LOG.md" not in paths
    assert all("/sync/" not in p for p in paths)
    assert corpus.source_count == 4


def test_product_tracks_have_no_actionable_next_after_recovery_closeout():
    root = Path.cwd()
    actionable = project_actionable_expected_tasks(project_id="vibe-control", repo_root=root)
    assert [task.ssot_anchor for task in actionable] == []
    all_tasks = project_all_expected_tasks(project_id="vibe-control", repo_root=root)
    p12 = next(t for t in all_tasks if t.ssot_anchor == "roadmap.phase12")
    assert p12.actionable is False
    assert p12.phase_state == "completed"
    for anchor in (
        CRCB,
        SLICE2,
        SLICE3,
        SLICE4,
        SLICE5,
        PROGRESS_BRIEF,
        GATEWAY,
        DESCRIBE,
        EVIDENCE,
        CONCEPT,
        CAP_RUNTIME,
        CAP_INSTALL,
        CAP_DOCTOR,
        RECOVERY,
    ):
        t = next(x for x in all_tasks if x.ssot_anchor == anchor)
        assert t.actionable is False
        assert t.phase_state == "completed"
    recovery = next(x for x in all_tasks if x.ssot_anchor == RECOVERY)
    assert recovery.actionable is False
    assert recovery.phase_state == "completed"
    assert recovery.design_only is True
    assert all(t.ssot_anchor != "roadmap.phase13" for t in all_tasks)


def test_dogfood_next_selects_no_actionable_after_recovery_closeout():
    root = Path.cwd()
    selection = next_actionable_selection(repo_root=root)
    assert selection["no_actionable_next_task"] is True
    assert selection["next_actionable_task"] is None
    assert selection["next_actionable_task"] != CAP_DOCTOR
    assert selection["next_actionable_task"] != CAP_INSTALL
    assert selection["next_actionable_task"] != CAP_RUNTIME
    assert selection["next_actionable_task"] != CONCEPT
    assert selection["next_actionable_task"] != EVIDENCE
    assert selection["next_actionable_task"] != DESCRIBE
    assert selection["next_actionable_task"] != GATEWAY
    assert selection["next_actionable_task"] != PROGRESS_BRIEF
    assert selection["next_actionable_task"] != CRCB
    assert selection["next_actionable_task"] != SLICE2
    assert selection["next_actionable_task"] != SLICE3
    assert selection["next_actionable_task"] != SLICE4
    assert selection["next_actionable_task"] != SLICE5
    assert selection["next_actionable_task"] != "roadmap.phase12"
    assert selection["next_actionable_task"] != "roadmap.phase13"

def test_explicit_operation_recovery_prompt_warns_completed_do_not_restart():
    root = Path.cwd()
    result = build_implementation_prompt(
        repo_root=root,
        task_selector=RECOVERY,
        product_ready=True,
        readiness_summary={
            "product_ready": True,
            "sync_state": "synced",
            "provider_ask_clean": True,
            "blocked_reasons": [],
        },
        reconcile_counts={
            "matched": 0,
            "missing": 0,
            "stale": 0,
            "duplicate": 0,
            "conflict": 0,
            "unmanaged": 0,
        },
        apply_plan_counts={"create": 0, "update": 0, "skip": 0, "blocked": 0},
    )
    assert result["ok"] is True
    assert result["mutation"] is False
    assert result["data"]["task_completed"] is True
    assert result["data"]["do_not_restart"] is True
    assert result["data"]["implementation_ready"] is False
    assert result["data"]["design_only"] is True
    assert result["data"]["next_actionable_selection"]["next_actionable_task"] is None
    assert result["data"]["no_actionable_next_task"] is True
    assert "Implement:" not in result["data"]["prompt"]
    assert "WARNING: selected task is completed" in result["data"]["prompt"]


def test_explicit_capability_doctor_prompt_warns_completed_do_not_restart():
    root = Path.cwd()
    result = build_implementation_prompt(
        repo_root=root,
        task_selector=CAP_DOCTOR,
        product_ready=True,
        readiness_summary={
            "product_ready": True,
            "sync_state": "synced",
            "provider_ask_clean": True,
            "blocked_reasons": [],
        },
        reconcile_counts={
            "matched": 0,
            "missing": 0,
            "stale": 0,
            "duplicate": 0,
            "conflict": 0,
            "unmanaged": 0,
        },
        apply_plan_counts={"create": 0, "update": 0, "skip": 0, "blocked": 0},
    )
    assert result["ok"] is True
    assert result["mutation"] is False
    assert result["data"]["task_completed"] is True
    assert result["data"]["do_not_restart"] is True
    assert result["data"]["next_actionable_selection"]["next_actionable_task"] is None
    assert "Implement:" not in result["data"]["prompt"]
    assert "WARNING: selected task is completed" in result["data"]["prompt"]


def test_explicit_capability_install_prompt_warns_completed_do_not_restart():
    root = Path.cwd()
    result = build_implementation_prompt(
        repo_root=root,
        task_selector=CAP_INSTALL,
        product_ready=True,
        readiness_summary={
            "product_ready": True,
            "sync_state": "synced",
            "provider_ask_clean": True,
            "blocked_reasons": [],
        },
        reconcile_counts={
            "matched": 0,
            "missing": 0,
            "stale": 0,
            "duplicate": 0,
            "conflict": 0,
            "unmanaged": 0,
        },
        apply_plan_counts={"create": 0, "update": 0, "skip": 0, "blocked": 0},
    )
    assert result["ok"] is True
    assert result["mutation"] is False
    assert result["data"]["task_completed"] is True
    assert result["data"]["do_not_restart"] is True
    assert result["data"]["next_actionable_selection"]["next_actionable_task"] is None
    assert "Implement:" not in result["data"]["prompt"]
    assert "WARNING: selected task is completed" in result["data"]["prompt"]


def test_explicit_capability_runtime_prompt_warns_completed_do_not_restart():
    root = Path.cwd()
    result = build_implementation_prompt(
        repo_root=root,
        task_selector=CAP_RUNTIME,
        product_ready=True,
        readiness_summary={
            "product_ready": True,
            "sync_state": "synced",
            "provider_ask_clean": True,
            "blocked_reasons": [],
        },
        reconcile_counts={
            "matched": 0,
            "missing": 0,
            "stale": 0,
            "duplicate": 0,
            "conflict": 0,
            "unmanaged": 0,
        },
        apply_plan_counts={"create": 0, "update": 0, "skip": 0, "blocked": 0},
    )
    assert result["ok"] is True
    assert result["mutation"] is False
    assert result["data"]["task_completed"] is True
    assert result["data"]["do_not_restart"] is True
    assert result["data"]["no_actionable_next_task"] is True
    assert result["data"]["next_actionable_selection"]["next_actionable_task"] is None
    assert "Implement:" not in result["data"]["prompt"]
    assert "task_completed_do_not_restart" in result["warnings"]
    assert "WARNING: selected task is completed" in result["data"]["prompt"]


def test_explicit_phase12_prompt_warns_completed_do_not_restart():
    root = Path.cwd()
    result = build_implementation_prompt(
        repo_root=root,
        task_selector="roadmap.phase12",
        product_ready=True,
        readiness_summary={
            "product_ready": True,
            "sync_state": "synced",
            "provider_ask_clean": True,
            "blocked_reasons": [],
        },
        reconcile_counts={
            "matched": 0,
            "missing": 0,
            "stale": 0,
            "duplicate": 0,
            "conflict": 0,
            "unmanaged": 0,
        },
        apply_plan_counts={"create": 0, "update": 0, "skip": 0, "blocked": 0},
    )
    assert result["ok"] is True
    assert result["mutation"] is False
    assert result["data"]["task_completed"] is True
    assert result["data"]["do_not_restart"] is True
    assert result["data"]["no_actionable_next_task"] is True
    assert result["data"]["next_actionable_selection"]["next_actionable_task"] is None
    assert "task_completed_do_not_restart" in result["warnings"]
    assert "do not restart" in result["data"]["prompt"].lower()
    assert "WARNING: selected task is completed" in result["data"]["prompt"]
    assert "provider_task_id_is_identity" in result["data"]["task_context"]
    assert result["data"]["task_context"]["provider_task_id_is_identity"] is False


def test_explicit_slice5_prompt_warns_completed_do_not_restart():
    root = Path.cwd()
    result = build_implementation_prompt(
        repo_root=root,
        task_selector=SLICE5,
        product_ready=True,
        readiness_summary={
            "product_ready": True,
            "sync_state": "synced",
            "provider_ask_clean": True,
            "blocked_reasons": [],
        },
        reconcile_counts={
            "matched": 0,
            "missing": 0,
            "stale": 0,
            "duplicate": 0,
            "conflict": 0,
            "unmanaged": 0,
        },
        apply_plan_counts={"create": 0, "update": 0, "skip": 0, "blocked": 0},
    )
    assert result["ok"] is True
    assert result["mutation"] is False
    assert result["data"]["task_completed"] is True
    assert result["data"]["do_not_restart"] is True
    assert "Slice 5" in str(result["data"]["task"]["title"])
    assert "Implement:" not in result["data"]["prompt"]
    assert "task_completed_do_not_restart" in result["warnings"]
    assert "WARNING: selected task is completed" in result["data"]["prompt"]


def test_explicit_slice4_prompt_warns_completed_do_not_restart():
    root = Path.cwd()
    result = build_implementation_prompt(
        repo_root=root,
        task_selector=SLICE4,
        product_ready=True,
        readiness_summary={
            "product_ready": True,
            "sync_state": "synced",
            "provider_ask_clean": True,
            "blocked_reasons": [],
        },
        reconcile_counts={
            "matched": 0,
            "missing": 0,
            "stale": 0,
            "duplicate": 0,
            "conflict": 0,
            "unmanaged": 0,
        },
        apply_plan_counts={"create": 0, "update": 0, "skip": 0, "blocked": 0},
    )
    assert result["ok"] is True
    assert result["mutation"] is False
    assert result["data"]["task_completed"] is True
    assert result["data"]["do_not_restart"] is True
    assert "Slice 4" in str(result["data"]["task"]["title"])
    assert "Implement:" not in result["data"]["prompt"]
    assert "task_completed_do_not_restart" in result["warnings"]
    assert "WARNING: selected task is completed" in result["data"]["prompt"]


def test_explicit_slice3_prompt_warns_completed_do_not_restart():
    root = Path.cwd()
    result = build_implementation_prompt(
        repo_root=root,
        task_selector=SLICE3,
        product_ready=True,
        readiness_summary={
            "product_ready": True,
            "sync_state": "synced",
            "provider_ask_clean": True,
            "blocked_reasons": [],
        },
        reconcile_counts={
            "matched": 0,
            "missing": 0,
            "stale": 0,
            "duplicate": 0,
            "conflict": 0,
            "unmanaged": 0,
        },
        apply_plan_counts={"create": 0, "update": 0, "skip": 0, "blocked": 0},
    )
    assert result["ok"] is True
    assert result["mutation"] is False
    assert result["data"]["task_completed"] is True
    assert result["data"]["do_not_restart"] is True
    assert "Slice 3" in str(result["data"]["task"]["title"])
    assert "Implement:" not in result["data"]["prompt"]
    assert "task_completed_do_not_restart" in result["warnings"]
    assert "WARNING: selected task is completed" in result["data"]["prompt"]


def test_explicit_slice2_prompt_warns_completed_do_not_restart():
    root = Path.cwd()
    result = build_implementation_prompt(
        repo_root=root,
        task_selector=SLICE2,
        product_ready=True,
        readiness_summary={
            "product_ready": True,
            "sync_state": "synced",
            "provider_ask_clean": True,
            "blocked_reasons": [],
        },
        reconcile_counts={
            "matched": 0,
            "missing": 0,
            "stale": 0,
            "duplicate": 0,
            "conflict": 0,
            "unmanaged": 0,
        },
        apply_plan_counts={"create": 0, "update": 0, "skip": 0, "blocked": 0},
    )
    assert result["ok"] is True
    assert result["mutation"] is False
    assert result["data"]["task_completed"] is True
    assert result["data"]["do_not_restart"] is True
    assert "Slice 2" in str(result["data"]["task"]["title"])
    assert "Implement:" not in result["data"]["prompt"]
    assert "task_completed_do_not_restart" in result["warnings"]
    assert "WARNING: selected task is completed" in result["data"]["prompt"]


def test_explicit_crcb_prompt_warns_completed_do_not_restart():
    root = Path.cwd()
    result = build_implementation_prompt(
        repo_root=root,
        task_selector=CRCB,
        product_ready=True,
        readiness_summary={
            "product_ready": True,
            "sync_state": "synced",
            "provider_ask_clean": True,
            "blocked_reasons": [],
        },
        reconcile_counts={
            "matched": 0,
            "missing": 0,
            "stale": 0,
            "duplicate": 0,
            "conflict": 0,
            "unmanaged": 0,
        },
        apply_plan_counts={"create": 0, "update": 0, "skip": 0, "blocked": 0},
    )
    assert result["ok"] is True
    assert result["mutation"] is False
    assert result["data"]["task_completed"] is True
    assert result["data"]["do_not_restart"] is True
    assert result["data"]["task"]["title"] == "Component Runtime Core Baseline Slice 1"
    assert "Implement:" not in result["data"]["prompt"]
    assert "task_completed_do_not_restart" in result["warnings"]
    assert "WARNING: selected task is completed" in result["data"]["prompt"]


def test_implementation_next_cli(monkeypatch, capsys):
    from vibe_control.cli import main

    monkeypatch.chdir(Path.cwd())
    code = main(["implementation", "next", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["ok"] is True
    assert payload.get("mutation") is not True
    data = payload["data"]
    assert data["no_actionable_next_task"] is True
    assert data["next_actionable_task"] is None
    assert data["do_not_invent_phase13"] is True
    assert data.get("anchor") in (None, {})


def test_explicit_describe_prompt_warns_completed_do_not_restart():
    root = Path.cwd()
    result = build_implementation_prompt(
        repo_root=root,
        task_selector=DESCRIBE,
        product_ready=True,
        readiness_summary={
            "product_ready": True,
            "sync_state": "synced",
            "provider_ask_clean": True,
            "blocked_reasons": [],
        },
        reconcile_counts={
            "matched": 0,
            "missing": 0,
            "stale": 0,
            "duplicate": 0,
            "conflict": 0,
            "unmanaged": 0,
        },
        apply_plan_counts={"create": 0, "update": 0, "skip": 0, "blocked": 0},
    )
    assert result["ok"] is True
    assert result["mutation"] is False
    assert result["data"]["task_completed"] is True
    assert result["data"]["do_not_restart"] is True
    assert result["data"]["no_actionable_next_task"] is True
    assert result["data"]["next_actionable_selection"]["next_actionable_task"] is None
    assert "Implement:" not in result["data"]["prompt"]
    assert "task_completed_do_not_restart" in result["warnings"]
    assert "WARNING: selected task is completed" in result["data"]["prompt"]


def test_explicit_evidence_prompt_warns_completed_do_not_restart():
    root = Path.cwd()
    result = build_implementation_prompt(
        repo_root=root,
        task_selector=EVIDENCE,
        product_ready=True,
        readiness_summary={
            "product_ready": True,
            "sync_state": "synced",
            "provider_ask_clean": True,
            "blocked_reasons": [],
        },
        reconcile_counts={
            "matched": 0,
            "missing": 0,
            "stale": 0,
            "duplicate": 0,
            "conflict": 0,
            "unmanaged": 0,
        },
        apply_plan_counts={"create": 0, "update": 0, "skip": 0, "blocked": 0},
    )
    assert result["ok"] is True
    assert result["mutation"] is False
    assert result["data"]["task_completed"] is True
    assert result["data"]["do_not_restart"] is True
    assert result["data"]["no_actionable_next_task"] is True
    assert result["data"]["next_actionable_selection"]["next_actionable_task"] is None
    assert "Implement:" not in result["data"]["prompt"]
    assert "task_completed_do_not_restart" in result["warnings"]
    assert "WARNING: selected task is completed" in result["data"]["prompt"]


def test_explicit_concept_prompt_warns_completed_do_not_restart():
    root = Path.cwd()
    result = build_implementation_prompt(
        repo_root=root,
        task_selector=CONCEPT,
        product_ready=True,
        readiness_summary={
            "product_ready": True,
            "sync_state": "synced",
            "provider_ask_clean": True,
            "blocked_reasons": [],
        },
        reconcile_counts={
            "matched": 0,
            "missing": 0,
            "stale": 0,
            "duplicate": 0,
            "conflict": 0,
            "unmanaged": 0,
        },
        apply_plan_counts={"create": 0, "update": 0, "skip": 0, "blocked": 0},
    )
    assert result["ok"] is True
    assert result["mutation"] is False
    assert result["data"]["task_completed"] is True
    assert result["data"]["do_not_restart"] is True
    assert result["data"]["no_actionable_next_task"] is True
    assert result["data"]["next_actionable_selection"]["next_actionable_task"] is None
    assert "Implement:" not in result["data"]["prompt"]
    assert "task_completed_do_not_restart" in result["warnings"]
    assert "WARNING: selected task is completed" in result["data"]["prompt"]


def test_explicit_gateway_prompt_warns_completed_do_not_restart():
    root = Path.cwd()
    result = build_implementation_prompt(
        repo_root=root,
        task_selector=GATEWAY,
        product_ready=True,
        readiness_summary={
            "product_ready": True,
            "sync_state": "synced",
            "provider_ask_clean": True,
            "blocked_reasons": [],
        },
        reconcile_counts={
            "matched": 0,
            "missing": 0,
            "stale": 0,
            "duplicate": 0,
            "conflict": 0,
            "unmanaged": 0,
        },
        apply_plan_counts={"create": 0, "update": 0, "skip": 0, "blocked": 0},
    )
    assert result["ok"] is True
    assert result["mutation"] is False
    assert result["data"]["task_completed"] is True
    assert result["data"]["do_not_restart"] is True
    assert result["data"]["no_actionable_next_task"] is True
    assert result["data"]["next_actionable_selection"]["next_actionable_task"] is None
    assert "Implement:" not in result["data"]["prompt"]
    assert "task_completed_do_not_restart" in result["warnings"]
    assert "WARNING: selected task is completed" in result["data"]["prompt"]


def test_explicit_progress_brief_prompt_warns_completed_do_not_restart():
    root = Path.cwd()
    result = build_implementation_prompt(
        repo_root=root,
        task_selector=PROGRESS_BRIEF,
        product_ready=True,
        readiness_summary={
            "product_ready": True,
            "sync_state": "synced",
            "provider_ask_clean": True,
            "blocked_reasons": [],
        },
        reconcile_counts={
            "matched": 0,
            "missing": 0,
            "stale": 0,
            "duplicate": 0,
            "conflict": 0,
            "unmanaged": 0,
        },
        apply_plan_counts={"create": 0, "update": 0, "skip": 0, "blocked": 0},
    )
    assert result["ok"] is True
    assert result["mutation"] is False
    assert result["data"]["task_completed"] is True
    assert result["data"]["do_not_restart"] is True
    assert result["data"]["no_actionable_next_task"] is True
    assert result["data"]["next_actionable_selection"]["next_actionable_task"] is None
    assert "Implement:" not in result["data"]["prompt"]
    assert "task_completed_do_not_restart" in result["warnings"]
    assert "do not restart" in result["data"]["prompt"].lower()
    assert "WARNING: selected task is completed" in result["data"]["prompt"]


def test_product_ready_and_task_cache_fields_still_present_on_completed_prompt():
    """Do not invent green readiness; fields must remain explicit on completed envelope."""
    root = Path.cwd()
    result = build_implementation_prompt(
        repo_root=root,
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
        apply_plan_counts={"create": 0, "update": 1, "skip": 0, "blocked": 0},
        provider_sync_required=True,
    )
    pr = result["data"]["product_readiness"]
    assert pr["product_ready"] is False
    assert "task_cache_current" in pr
    assert result["data"]["task_completed"] is True


def test_tmp_completed_state_no_invented_phase13(tmp_path):
    write_doc(tmp_path, "docs/project/vibe-control-spec.md", "# Spec\n")
    write_doc(
        tmp_path,
        "docs/project/vibe-control-roadmap-state.md",
        """# Roadmap State

```yaml
roadmap_state_version: 1
next_actionable_task: null
no_actionable_next_task: true
anchors:
  - ssot_anchor: roadmap.phase12
    task_kind: implementation_phase
    title: "Phase 12"
    phase_state: completed
    actionable: false
```
""",
    )
    selection = next_actionable_selection(repo_root=tmp_path)
    assert selection["no_actionable_next_task"] is True
    assert selection["next_actionable_task"] is None
    actionable = project_actionable_expected_tasks(project_id="vibe-control", repo_root=tmp_path)
    assert actionable == []
