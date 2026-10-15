"""Vibe Describe control surface — readonly explanation; no second readiness engine."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from vibe_control.cli import main
from vibe_control.describe import (
    COMPONENT_CATALOG_STATIC,
    ENGINE_SURFACES,
    MUTATION_SURFACES,
    READONLY_SURFACES,
    build_describe,
)

DESCRIBE = "roadmap.vibe_describe_control_surface"
RECOVERY = "roadmap.vibe_operation_recovery_design"
CONCEPT = "roadmap.vibe_product_concept_boundary_contract"
CAP_RUNTIME = "roadmap.vibe_capability_profile_runtime"
CAP_INSTALL = "roadmap.vibe_capability_profile_install_init_guidance"
CAP_DOCTOR = "roadmap.vibe_capability_profile_doctor_gateway_guidance"
FORBIDDEN_SECRET_PATTERNS = (
    r"notebooklm://",
    r"Authorization:",
    r"Bearer\s+",
    r"cookie=",
    r"Cookie:",
    r"provider_source_id\s*[:=]",
)


def _assert_no_secrets(blob: str) -> None:
    for pattern in FORBIDDEN_SECRET_PATTERNS:
        assert re.search(pattern, blob, flags=re.IGNORECASE) is None, pattern
    assert "provider_task_id\": \"vibe-control-" not in blob
    assert "\"notebook_ref\"" not in blob


def _progress_envelope(**overrides: Any) -> dict[str, Any]:
    data = {
        "schema_version": "vibe.progress.v1",
        "mutation": False,
        "product_ready": True,
        "provider_sync_required": False,
        "provider_ask_clean": True,
        "task_cache_current": True,
        "closeout_complete": True,
        "implementation_ready": True,
        "next_actionable_task": DESCRIBE,
        "no_actionable_next_task": False,
        "blocked_reasons": [],
        "safe_next_action": {
            "code": "IMPLEMENTATION_PROMPT",
            "command": f"vibe implementation prompt --task {DESCRIBE} --json",
            "mutation": False,
            "reason": "test",
        },
    }
    data.update(overrides)
    return {
        "ok": True,
        "command": "vibe progress",
        "mutation": False,
        "mode": "readonly_progress",
        "data": data,
        "warnings": [],
        "next_actions": [data["safe_next_action"]],
    }


def test_static_surface_catalogs_are_readonly():
    assert all(s["mutation"] is False for s in READONLY_SURFACES)
    assert any(m["name"] == "gateway.grill_brief" for m in MUTATION_SURFACES)
    assert any(s["command"].startswith("vibe closeout run --apply") for s in MUTATION_SURFACES)
    assert any(s["name"] == "progress" for s in ENGINE_SURFACES)
    assert "knowledge" in COMPONENT_CATALOG_STATIC
    assert "hetu" in COMPONENT_CATALOG_STATIC
    assert COMPONENT_CATALOG_STATIC["hetu"]["support_state"] == "supported"
    assert COMPONENT_CATALOG_STATIC["hetu"]["default_enabled"] is False
    assert any(s["name"] == "hetu.status" for s in READONLY_SURFACES)
    assert any(m["name"] == "hetu.reindex.apply" for m in MUTATION_SURFACES)
    assert COMPONENT_CATALOG_STATIC["sdd"]["provider_hints_are_active"] is False


def test_describe_cli_ok_mutation_false(monkeypatch, capsys):
    monkeypatch.chdir(Path.cwd())
    code = main(["describe", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["ok"] is True
    assert payload.get("mutation") is False
    assert payload["command"] == "vibe describe"
    data = payload["data"]
    assert data["describe"] is True
    assert data["mutation"] is False
    assert data["source_of_truth"] == "engine"
    assert data["facts_embedded"] is False
    assert data["authority"]["repo_ssot"] is True
    blob = json.dumps(payload, ensure_ascii=False)
    _assert_no_secrets(blob)
    assert "ChatGPT Project Sources were updated" not in blob


def test_describe_identifies_project_sources_as_advisor_only(tmp_path: Path):
    result = build_describe(
        repo_root=tmp_path,
        progress_envelope=_progress_envelope(),
    )
    auth = result["data"]["authority"]
    assert "advisor" in auth["chatgpt_project_sources"].lower()
    assert auth.get("chatgpt_project_sources_required") is not True


def test_describe_lists_engine_surfaces_without_hardcoded_roadmap_facts():
    src = Path("src/vibe_control/describe.py").read_text(encoding="utf-8")
    assert "roadmap.vibe_describe_control_surface" not in src
    assert "roadmap.phase13" not in src
    assert "next_actionable_task =" not in src
    result = build_describe(
        repo_root=Path.cwd(),
        progress_envelope=_progress_envelope(),
    )
    names = {s["name"] for s in result["data"]["engine_surfaces"]}
    assert {"progress", "brief", "gateway", "implementation.next", "closeout.dry_run"} <= names


def test_describe_projects_safe_next_from_engine_not_recompute(tmp_path: Path):
    progress = _progress_envelope(
        product_ready=False,
        implementation_ready=False,
        blocked_reasons=["task_cache_not_current"],
        safe_next_action={
            "code": "TASK_CONVERGENCE_REQUIRED",
            "command": "vibe task apply --dry-run --json --provider beads",
            "mutation": False,
            "reason": "from engine",
        },
    )
    result = build_describe(repo_root=tmp_path, progress_envelope=progress)
    data = result["data"]
    assert data["projected"]["product_ready"] is False
    assert data["projected"]["implementation_ready"] is False
    assert data["projected"]["blocked_reasons"] == ["task_cache_not_current"]
    assert data["safe_next"]["code"] == "TASK_CONVERGENCE_REQUIRED"
    # Describe must not invent flipped readiness fields at top level.
    assert data.get("product_ready") is None
    assert data.get("implementation_ready") is None


def test_describe_represents_no_actionable_next(tmp_path: Path):
    progress = _progress_envelope(
        next_actionable_task=None,
        no_actionable_next_task=True,
        implementation_ready=False,
        safe_next_action={
            "code": "NO_ACTIONABLE_NEXT_TASK",
            "command": "cat docs/project/vibe-control-roadmap-state.md",
            "mutation": False,
            "reason": "none",
        },
    )
    result = build_describe(repo_root=tmp_path, progress_envelope=progress)
    assert result["data"]["projected"]["no_actionable_next_task"] is True
    assert result["data"]["projected"]["next_actionable_task"] is None
    assert result["data"]["safe_next"]["code"] == "NO_ACTIONABLE_NEXT_TASK"


def test_describe_represents_blocked_state(tmp_path: Path):
    progress = _progress_envelope(
        product_ready=False,
        provider_sync_required=True,
        provider_ask_clean=False,
        blocked_reasons=["knowledge_sync_state=drift"],
        implementation_ready=False,
        safe_next_action={
            "code": "RUN_BOUNDED_KNOWLEDGE_SYNC",
            "command": "vibe closeout run --dry-run --json",
            "mutation": False,
            "reason": "drift",
        },
    )
    result = build_describe(repo_root=tmp_path, progress_envelope=progress)
    proj = result["data"]["projected"]
    assert proj["provider_sync_required"] is True
    assert proj["provider_ask_clean"] is False
    assert "knowledge_sync_state=drift" in proj["blocked_reasons"]


def test_describe_does_not_recompute_readiness_fields(tmp_path: Path):
    progress = _progress_envelope(
        product_ready=False,
        provider_sync_required=True,
        provider_ask_clean=False,
        task_cache_current=False,
        implementation_ready=False,
    )
    result = build_describe(repo_root=tmp_path, progress_envelope=progress)
    proj = result["data"]["projected"]
    assert proj["product_ready"] is False
    assert proj["provider_sync_required"] is True
    assert proj["provider_ask_clean"] is False
    assert proj["task_cache_current"] is False
    assert proj["implementation_ready"] is False


def test_describe_provider_task_id_binding_only(tmp_path: Path):
    result = build_describe(
        repo_root=tmp_path,
        progress_envelope=_progress_envelope(),
    )
    auth = result["data"]["authority"]
    assert "binding" in auth["provider_task_id"].lower()
    assert result["data"].get("task_identity") is None
    assert result["data"].get("ssot_anchor") is None


def test_describe_explains_authority_mutation_and_components(tmp_path: Path):
    result = build_describe(
        repo_root=tmp_path,
        progress_envelope=_progress_envelope(),
    )
    data = result["data"]
    assert "authority_map" in data
    assert data["authority_map"]["engine"] == "Vibe Control Engine"
    assert isinstance(data["readonly_surfaces"], list) and data["readonly_surfaces"]
    assert isinstance(data["mutation_surfaces"], list) and data["mutation_surfaces"]
    assert all(m.get("gateway_auto_run") is False for m in data["mutation_surfaces"])
    catalog = data["component_catalog"]
    assert catalog["knowledge"]["support_state"] == "supported"
    assert catalog["tdd"]["provider_hints"] == ["superpowers"]
    assert catalog["tdd"]["provider_hints_are_active"] is False
    assert "non_goals" in data and "product health or readiness computation" in data["non_goals"]


def test_describe_does_not_probe_providers(tmp_path: Path, monkeypatch):
    calls: list[str] = []

    def boom(*_a: Any, **_k: Any) -> Any:
        calls.append("probed")
        raise AssertionError("Describe must not probe providers directly")

    monkeypatch.setattr(
        "vibe_control.knowledge.providers.notebooklm.NotebookLMProvider",
        boom,
        raising=False,
    )
    # Injected progress only — no live Engine probe path.
    result = build_describe(
        repo_root=tmp_path,
        progress_envelope=_progress_envelope(),
    )
    assert result["ok"] is True
    assert calls == []
    assert result["data"]["probe_policy"] == "static_or_projection_sources_only"


def test_describe_evidence_projected_and_readonly(tmp_path: Path):
    result = build_describe(
        repo_root=tmp_path,
        progress_envelope=_progress_envelope(),
        observed_head="abc123",
        git_status_short="",
        run_id="run-describe-1",
    )
    evidence = result["data"]["evidence"]
    assert evidence["operation"] == "describe"
    assert evidence["mode"] == "readonly_describe"
    assert evidence["mutation_intent"] is False
    assert evidence["mutation_performed"] is False
    assert evidence["run_id"] == "run-describe-1"
    assert "evidence_hash" in evidence
    assert result["data"]["evidence_class"] == "projected_ephemeral_s1"


def test_describe_refuses_to_claim_mutation_routes(tmp_path: Path):
    result = build_describe(
        repo_root=tmp_path,
        progress_envelope=_progress_envelope(),
    )
    blob = json.dumps(result, ensure_ascii=False)
    assert "vibe closeout run --apply" in blob  # listed as mutation class
    assert result["data"]["mutation"] is False
    assert all(
        s.get("auto_run_from_describe") is False for s in result["data"]["mutation_surfaces"]
    )


def test_progress_brief_gateway_still_select_capability_runtime(monkeypatch, capsys):
    monkeypatch.chdir(Path.cwd())
    code = main(["progress", "--json"])
    progress = json.loads(capsys.readouterr().out)
    assert code == 0
    assert progress["data"]["next_actionable_task"] is None

    code = main(["brief", "--json"])
    brief = json.loads(capsys.readouterr().out)
    assert code == 0
    assert brief["data"]["task"] is None or brief["data"]["next_actionable_task"] is None

    code = main(["gateway", "--intent", "what_next", "--json"])
    gw = json.loads(capsys.readouterr().out)
    assert code == 0
    assert gw["data"]["engine_payload"]["data"]["next_actionable_task"] is None
