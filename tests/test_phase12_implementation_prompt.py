"""Phase 12 Implementation Prompt Generator — failing tests first."""

from __future__ import annotations

from pathlib import Path

import pytest
from helpers import minimal_config_dict, write_control_yaml, write_doc


def _repo(tmp_path: Path) -> Path:
    write_control_yaml(
        tmp_path,
        {**minimal_config_dict(), "project": {"id": "vibe-control", "name": "Vibe"}},
    )
    write_doc(
        tmp_path,
        "docs/project/vibe-control-spec.md",
        "# Spec\nPhase 12 Implementation Prompt Generator\n",
    )
    return tmp_path


def test_P12_SPEC_01_spec_exists():
    text = Path("docs/project/sync/phase12-implementation-prompt-generator-spec.md").read_text(
        encoding="utf-8"
    )
    assert "vibe implementation prompt" in text
    assert "managed_key" in text
    assert "product_ready" in text
    assert "NotebookLM" in text
    assert "mutation=false" in text or "mutation: false" in text.lower() or "Readonly only" in text


def test_P12_GEN_01_resolve_by_ssot_anchor(tmp_path):
    from vibe_control.implementation.prompt import build_implementation_prompt

    root = _repo(tmp_path)
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
            "matched": 5,
            "missing": 0,
            "stale": 0,
            "duplicate": 0,
            "conflict": 0,
            "unmanaged": 0,
        },
        apply_plan_counts={"create": 0, "update": 0, "skip": 4, "blocked": 0},
        provider_task_id="vibe-control-sxm",
    )
    assert result["ok"] is True
    assert result["mutation"] is False
    assert result["data"]["task"]["ssot_anchor"] == "roadmap.phase12"
    assert result["data"]["task"]["managed_key"].startswith("sha256:")
    assert "prompt_text" in result["data"]
    assert result["data"]["prompt_hash"].startswith("sha256:")


def test_P12_GEN_02_resolve_by_managed_key(tmp_path):
    from vibe_control.implementation.prompt import build_implementation_prompt
    from vibe_control.task.projection import project_actionable_expected_tasks

    root = _repo(tmp_path)
    expected = project_actionable_expected_tasks(project_id="vibe-control", repo_root=root)
    p12 = next(t for t in expected if t.ssot_anchor == "roadmap.phase12")
    result = build_implementation_prompt(
        repo_root=root,
        task_selector=p12.managed_key,
        product_ready=True,
        readiness_summary={"product_ready": True, "blocked_reasons": []},
        reconcile_counts={"matched": 1, "missing": 0, "stale": 0, "duplicate": 0, "conflict": 0, "unmanaged": 0},
        apply_plan_counts={"create": 0, "update": 0, "skip": 0, "blocked": 0},
    )
    assert result["data"]["task"]["managed_key"] == p12.managed_key
    assert result["data"]["task"]["ssot_anchor"] == "roadmap.phase12"


def test_P12_GEN_03_prompt_contains_required_sections(tmp_path):
    from vibe_control.implementation.prompt import build_implementation_prompt

    root = _repo(tmp_path)
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
        reconcile_counts={"matched": 5, "missing": 0, "stale": 0, "duplicate": 0, "conflict": 0, "unmanaged": 0},
        apply_plan_counts={"create": 0, "update": 0, "skip": 4, "blocked": 0},
        provider_task_id="vibe-control-sxm",
    )
    text = result["data"]["prompt_text"]
    assert "docs/project/vibe-control-spec.md" in text
    assert "roadmap.phase12" in text
    assert "product_ready" in text
    assert "Hard boundaries" in text or "hard boundaries" in text.lower()
    assert "test-closeout-local-fast" in text
    assert "Final report" in text or "final report" in text.lower()
    assert "Do not treat NotebookLM" in text or "NotebookLM is not truth" in text


def test_P12_GEN_04_identity_and_redaction(tmp_path):
    from vibe_control.implementation.prompt import build_implementation_prompt

    root = _repo(tmp_path)
    result = build_implementation_prompt(
        repo_root=root,
        task_selector="roadmap.phase12",
        product_ready=True,
        readiness_summary={"product_ready": True, "blocked_reasons": []},
        reconcile_counts={"matched": 1, "missing": 0, "stale": 0, "duplicate": 0, "conflict": 0, "unmanaged": 0},
        apply_plan_counts={"create": 0, "update": 0, "skip": 0, "blocked": 0},
        provider_task_id="vibe-control-sxm",
        notebook_ref_raw="notebooklm://secret-notebook-ref",
    )
    blob = str(result)
    text = result["data"]["prompt_text"]
    assert "managed_key" in text or result["data"]["task"]["managed_key"]
    assert "notebooklm://secret-notebook-ref" not in blob
    assert "binding result" in text.lower() or "not source identity" in text.lower()


def test_P12_GEN_05_provider_id_hashed_in_envelope(tmp_path):
    from vibe_control.implementation.prompt import build_implementation_prompt

    root = _repo(tmp_path)
    result = build_implementation_prompt(
        repo_root=root,
        task_selector="roadmap.phase12",
        product_ready=True,
        readiness_summary={"product_ready": True, "blocked_reasons": []},
        reconcile_counts={"matched": 1, "missing": 0, "stale": 0, "duplicate": 0, "conflict": 0, "unmanaged": 0},
        apply_plan_counts={"create": 0, "update": 0, "skip": 0, "blocked": 0},
        provider_task_id="vibe-control-sxm",
        redact_provider_ids=True,
    )
    task = result["data"]["task"]
    assert task.get("provider_task_id") is None
    assert task.get("provider_task_id_hash", "").startswith("sha256:")


def test_P12_GEN_06_unknown_selector_fails(tmp_path):
    from vibe_control.implementation.prompt import PromptError, build_implementation_prompt

    root = _repo(tmp_path)
    with pytest.raises(PromptError) as exc:
        build_implementation_prompt(
            repo_root=root,
            task_selector="roadmap.does-not-exist",
            product_ready=True,
            readiness_summary={"product_ready": True, "blocked_reasons": []},
            reconcile_counts={"matched": 0, "missing": 0, "stale": 0, "duplicate": 0, "conflict": 0, "unmanaged": 0},
            apply_plan_counts={"create": 0, "update": 0, "skip": 0, "blocked": 0},
        )
    assert exc.value.code == "TASK_SELECTOR_NOT_FOUND"


def test_P12_CLI_01_readonly_json(tmp_path, monkeypatch, capsys):
    from vibe_control.cli import main

    root = _repo(tmp_path)
    monkeypatch.chdir(root)
    code = main(
        [
            "implementation",
            "prompt",
            "--task",
            "roadmap.phase12",
            "--json",
            "--skip-provider-probe",
        ]
    )
    out = capsys.readouterr().out
    payload = __import__("json").loads(out)
    assert code == 0
    assert payload.get("ok") is True
    assert payload.get("mutation") is False
    assert payload.get("command") == "vibe implementation prompt"
    data = payload.get("data") or {}
    assert "prompt_text" in data
    assert "prompt" in data
    assert "task_identity" in data
    assert "prompt_sections" in data


def test_P12_GEN_07_contract_envelope_fields(tmp_path):
    from vibe_control.implementation.prompt import PROMPT_SECTION_ORDER, build_implementation_prompt

    root = _repo(tmp_path)
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
        knowledge_readiness={"sync_state": "drift", "provider_ask_clean": False, "available": True, "target_ok": True},
        reconcile_counts={"matched": 0, "missing": 0, "stale": 5, "duplicate": 0, "conflict": 0, "unmanaged": 0},
        apply_plan_counts={"create": 0, "update": 0, "skip": 0, "blocked": 1},
        provider_task_id="vibe-control-sxm",
        provider_sync_required=True,
    )
    data = result["data"]
    assert data["task_identity"]["ssot_anchor"] == "roadmap.phase12"
    assert data["task_identity"]["managed_key"].startswith("sha256:")
    assert "ssot_path" in data["task_identity"]
    # Primary contract fields must exist; aliases are compatibility-only
    assert "prompt" in data and data["prompt"]
    assert data["prompt_sections"] == list(PROMPT_SECTION_ORDER)
    assert data.get("prompt_text") == data["prompt"]  # alias only
    assert "task" in data  # compatibility alias
    assert data["task_context"]["provider_task_id_is_identity"] is False
    assert "provider_task_id" not in data["task_context"]
    assert data["product_readiness"]["product_ready"] is False
    assert data["product_readiness"]["provider_sync_required"] is True
    assert data["knowledge_readiness"]["sync_state"] == "drift"
    assert data["task_reconcile_summary"]["stale"] == 5
    assert data["task_apply_plan_summary"]["blocked"] == 1
    assert data["prompt"] == data["prompt_text"]
    assert data["prompt_sections"] == list(PROMPT_SECTION_ORDER)
    assert "product_ready=false" in result["warnings"]
    assert "provider_sync_required" in result["warnings"]
    assert result["next_actions"]
    text = data["prompt"]
    for heading in (
        "Task goal",
        "Repo SSOT identity",
        "Selected task anchor",
        "product_ready summary",
        "Knowledge readiness summary",
        "Hard boundaries",
        "Safety confirmation",
        "Final git status --short",
    ):
        assert heading in text


def test_P12_GEN_08_provider_task_id_not_identity(tmp_path):
    from vibe_control.implementation.prompt import build_implementation_prompt

    root = _repo(tmp_path)
    result = build_implementation_prompt(
        repo_root=root,
        task_selector="roadmap.phase12",
        product_ready=True,
        readiness_summary={"product_ready": True, "blocked_reasons": []},
        reconcile_counts={"matched": 1, "missing": 0, "stale": 0, "duplicate": 0, "conflict": 0, "unmanaged": 0},
        apply_plan_counts={"create": 0, "update": 0, "skip": 0, "blocked": 0},
        provider_task_id="vibe-control-sxm",
    )
    assert result["data"]["task_identity"]["managed_key"]
    assert result["data"]["task_identity"]["ssot_anchor"] == "roadmap.phase12"
    assert "provider_task_id" not in result["data"]["task_identity"]
    assert result["data"]["task_context"]["provider_task_id_is_identity"] is False
