"""Concept boundary + Capability Profile target contract — SSOT/tests only."""

from __future__ import annotations

from pathlib import Path

from vibe_control.task.projection import (
    next_actionable_selection,
    project_actionable_expected_tasks,
)
from vibe_control.task.roadmap_state import load_roadmap_state

CONCEPT = "roadmap.vibe_product_concept_boundary_contract"
CAP_RUNTIME = "roadmap.vibe_capability_profile_runtime"
CAP_INSTALL = "roadmap.vibe_capability_profile_install_init_guidance"
CAP_DOCTOR = "roadmap.vibe_capability_profile_doctor_gateway_guidance"
RECOVERY = "roadmap.vibe_operation_recovery_design"

REQUIRED_TDD_CASES = (
    "fresh_default_profile",
    "enable_knowledge",
    "enable_task",
    "unsupported_sdd_tdd",
    "gateway_skills_thin_routing",
    "init_profile_preview",
    "project_sources_not_product_gate",
    "provider_unavailable",
)


def test_concept_boundary_completed_and_no_actionable_next():
    state = load_roadmap_state(Path.cwd())
    by = {a["ssot_anchor"]: a for a in state["anchors"]}
    assert state["next_actionable_task"] is None
    assert state["no_actionable_next_task"] is True
    assert by[CONCEPT]["phase_state"] == "completed"
    assert by[CONCEPT]["actionable"] is False
    scope = by[CONCEPT]["completed_scope"]
    assert "product concept boundary explicit and test-covered" in scope
    assert "target Capability Profile contract (all disabled by default)" in scope
    assert "runtime explicitly unchanged until capability profile runtime slice" in scope
    assert by[CAP_RUNTIME]["phase_state"] == "completed"
    assert by[CAP_RUNTIME]["actionable"] is False
    assert by[CAP_INSTALL]["phase_state"] == "completed"
    assert by[CAP_INSTALL]["actionable"] is False
    assert by[CAP_DOCTOR]["phase_state"] == "completed"
    assert by[CAP_DOCTOR]["actionable"] is False
    assert by[RECOVERY]["phase_state"] == "completed"
    assert by[RECOVERY]["actionable"] is False
    assert "roadmap.phase13" not in by


def test_completed_anchors_not_actionable():
    actionable = project_actionable_expected_tasks(
        project_id="vibe-control", repo_root=Path.cwd()
    )
    assert [t.ssot_anchor for t in actionable] == []
    selection = next_actionable_selection(repo_root=Path.cwd())
    assert selection["next_actionable_task"] is None
    assert selection["next_actionable_task"] != CAP_INSTALL
    assert selection["next_actionable_task"] != CAP_RUNTIME
    assert selection["next_actionable_task"] != CONCEPT
    assert selection["next_actionable_task"] != CAP_DOCTOR


def test_front_core_concept_boundary_and_target_profile():
    spec = Path("docs/project/vibe-control-spec.md").read_text(encoding="utf-8")
    assert "Engine + Gateway + Knowledge + Task + Hetu + Capability Profile" in spec
    assert "thin routers to Engine surfaces" in spec
    assert "SSOT manager" in spec or "SSOT management product" in spec
    assert "roadmap manager" in spec
    assert "workflow engine" in spec
    assert "dogfood" in spec
    assert "source-task" in spec or "source/task" in spec
    assert "≠ external product features" in spec or "≠ external customer-facing" in spec
    assert "does NOT own generic SSOT management" in spec
    assert "managed_key" in spec
    assert "≠ roadmap.* string prefix as identity" in spec
    assert "Engine readiness" in spec and "Capability readiness" in spec
    assert "knowledge | task | hetu | sdd | tdd" in spec
    assert "all capabilities disabled by default" in spec
    assert "available / enablable" in spec
    assert "NOT a product_ready failure" in spec
    assert (
        "knowledge.provider readiness" in spec
        or "NotebookLM readiness" in spec
        or "active knowledge.provider readiness" in spec
    )
    assert "task-cache readiness" in spec or "task-cache" in spec
    assert "not implemented" in spec
    assert "fail closed" in spec
    assert "runtime unchanged until" in spec
    assert "roadmap.vibe_capability_profile_runtime" in spec
    assert "Project Sources" in spec or "ChatGPT Project Sources" in spec
    assert "closeout gate" in spec or "product gate" in spec
    assert "vibe-control-hetu-spec.md" in spec
    assert "design-accepted peer capability" in spec or "Hetu" in spec


def test_tdd_plan_names_required_cases():
    plan = Path(
        "docs/project/sync/vibe-product-concept-capability-profile-tdd-plan.md"
    ).read_text(encoding="utf-8")
    for case in REQUIRED_TDD_CASES:
        assert case in plan, case
    assert "Gateway/Skills" in plan or "gateway_skills_thin_routing" in plan
    assert "closeout" in plan.lower()
    assert "mutation" in plan.lower()
    assert "Project Sources" in plan or "project_sources_not_product_gate" in plan
