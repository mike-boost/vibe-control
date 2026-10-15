"""Provider readiness, Beads dual-gate, and knowledge/task coordination."""

from __future__ import annotations

import json

import pytest

from helpers import minimal_config_dict, write_control_yaml, write_doc
from vibe_control.cli import main
from vibe_control.components import resolve_component_runtime
from vibe_control.integration import build_integration_status
from vibe_control.knowledge.notebooklm_provider import NotebookLMProvider, NotebookLMStatus
from vibe_control.product_readiness import (
    build_probe_from_parts,
    evaluate_product_readiness,
    finalize_product_ready,
    ProviderProbeResult,
)
from vibe_control.task.apply_cli import run_task_apply
from vibe_control.task.apply_plan import compute_plan_binding_hash
from vibe_control.task.beads_apply import (
    BeadsApplyBlocked,
    execute_beads_apply_guarded,
    live_apply_gates_satisfied,
)
from vibe_control.task.beads_readonly import BeadsReadonlyError, BeadsReadonlyProvider, assert_readonly_bd_argv
from vibe_control.task.projection import project_slice1_expected_tasks
from vibe_control.task.provider import FakeTaskProvider
from vibe_control.task.beads_provider import BeadsProvider, BeadsStatus


class FakeNLM(NotebookLMProvider):
    def which(self):
        return "/tmp/fake-nlm"

    def status(self, *, probe_auth: bool = False) -> NotebookLMStatus:
        return NotebookLMStatus(installed=True, executable="/tmp/fake-nlm", version="x", message="ok")


class FakeBeads(BeadsProvider):
    def which(self):
        return "/tmp/fake-bd"

    def status(self) -> BeadsStatus:
        return BeadsStatus(installed=True, executable="/tmp/fake-bd", version="x", message="ok")

    def init_preview(self) -> BeadsStatus:
        return self.status()


def test_product_ready_false_when_provider_unavailable():
    comps = resolve_component_runtime(
        {"knowledge": {"enabled": True}, "task": {"enabled": True}}
    )["components"]
    probe = build_probe_from_parts(
        knowledge_available=False,
        knowledge_target_ok=False,
        sync_state="unavailable",
        task_available=False,
        task_mode="unavailable",
        task_readable=False,
        components=comps,
    )
    assert probe.product_ready is False
    assert "knowledge_provider_unavailable" in probe.blocked_reasons


def test_product_ready_false_on_drift():
    comps = resolve_component_runtime({"knowledge": {"enabled": True}})["components"]
    probe = build_probe_from_parts(
        knowledge_available=True,
        knowledge_target_ok=True,
        sync_state="drift",
        required_updates_count=1,
        task_available=True,
        task_mode="readonly",
        task_readable=True,
        ready_queue_available=True,
        components=comps,
    )
    assert probe.product_ready is False
    assert any("sync_state" in r for r in probe.blocked_reasons)


def test_repo_fallback_not_product_ready(tmp_path, monkeypatch):
    monkeypatch.setenv("VIBE_SKILLS_ROOT", str(tmp_path / "skills"))
    write_control_yaml(
        tmp_path,
        {
            **minimal_config_dict(),
            "project": {"id": "vibe-control", "name": "Vibe"},
            "components": {"knowledge": {"enabled": True}},
        },
    )
    write_doc(tmp_path, "docs/project/vibe-control-spec.md", "# Spec\n")
    data = build_integration_status(
        repo_root=tmp_path,
        notebooklm=FakeNLM(),
        beads=FakeBeads(),
        probe_product=False,
        knowledge_parts={
            "available": False,
            "target_ok": False,
            "sync_state": "unavailable",
        },
        task_parts={"available": True, "mode": "readonly", "readable": True},
    )
    assert data["repo"]["fallback_is_product_ready"] is False
    assert data["product_ready"] is False
    assert data["components"]["knowledge"]["enabled"] is True


def test_task_unavailable_not_empty_inventory():
    provider = BeadsReadonlyProvider(
        executable="/missing/bd",
        runner=lambda argv: (127, "", "missing"),
    )
    tasks = provider.list_tasks()
    assert tasks == []
    assert provider.available is False


def test_ready_parse_failure_not_empty_ready():
    def runner(argv):
        if argv[1] == "list":
            return 0, "[]", ""
        if argv[1] == "ready":
            return 0, "not-json", ""
        return 1, "", "bad"

    provider = BeadsReadonlyProvider(runner=runner, executable="/fake/bd")
    assert provider.list_tasks() == []
    assert provider.available is True
    ready = provider.list_ready_tasks()
    assert ready == []
    assert provider.ready_queue_ok is False


def test_claim_flag_forbidden_in_readonly():
    with pytest.raises(BeadsReadonlyError):
        assert_readonly_bd_argv(["bd", "ready", "--claim", "--json"])


def test_dual_gate_env_only_blocked(monkeypatch):
    monkeypatch.setenv("VIBE_BEADS_LIVE_APPLY", "1")
    assert live_apply_gates_satisfied(confirm=False) is False
    with pytest.raises(BeadsApplyBlocked):
        execute_beads_apply_guarded([], runner=lambda a: None, confirm=False)


def test_dual_gate_confirm_only_blocked(monkeypatch):
    monkeypatch.delenv("VIBE_BEADS_LIVE_APPLY", raising=False)
    assert live_apply_gates_satisfied(confirm=True) is False


def test_apply_plan_has_binding_hash(tmp_path):
    write_doc(tmp_path, "docs/project/vibe-control-spec.md", "# Spec\n")
    expected = project_slice1_expected_tasks(project_id="vibe-control", repo_root=tmp_path)
    binding = compute_plan_binding_hash(expected)
    assert binding.startswith("sha256:")
    from vibe_control.task.apply_engine import run_apply

    result = run_apply(
        expected=expected,
        provider=FakeTaskProvider([]),
        mode="dry_run",
        project_id="vibe-control",
        provider_name="fake",
        knowledge_readiness={"checked": False, "skipped": True},
    )
    assert result.plan.plan_binding_hash == binding
    assert result.plan.knowledge_readiness.get("skipped") is True


def test_stale_plan_binding_blocked(tmp_path):
    write_doc(tmp_path, "docs/project/vibe-control-spec.md", "# Spec\n")
    expected = project_slice1_expected_tasks(project_id="vibe-control", repo_root=tmp_path)
    from vibe_control.task.apply_engine import run_apply

    result = run_apply(
        expected=expected,
        provider=FakeTaskProvider([]),
        mode="apply",
        project_id="vibe-control",
        provider_name="fake",
        expect_plan_binding="sha256:" + "0" * 64,
    )
    assert result.ok is False
    assert result.mode == "blocked"
    assert result.code == "STALE_APPLY_PLAN"


def test_strict_beads_apply_blocked_when_knowledge_unready(tmp_path):
    write_control_yaml(
        tmp_path,
        {**minimal_config_dict(), "project": {"id": "vibe-control", "name": "Vibe"}},
    )
    write_doc(tmp_path, "docs/project/vibe-control-spec.md", "# Spec\n")
    probe = build_probe_from_parts(
        knowledge_available=False,
        knowledge_target_ok=False,
        sync_state="unavailable",
        task_available=True,
        task_mode="readonly",
        task_readable=True,
        components=resolve_component_runtime({"knowledge": {"enabled": True}})[
            "components"
        ],
    )
    env = run_task_apply(
        repo_root=tmp_path,
        mode="dry_run",
        provider_name="fake",
        provider=FakeTaskProvider([]),
        strict_providers=True,
        knowledge_probe=probe,
    )
    assert env["mode"] == "blocked"
    assert env["mutation"] is False
    assert env["error"]["code"] == "KNOWLEDGE_PROVIDER_NOT_READY"
    assert any(
        (a.get("code") if isinstance(a, dict) else "") == "KNOWLEDGE_PROVIDER_DIAGNOSIS"
        or "knowledge" in str(a).lower()
        for a in env.get("next_actions") or []
    )


def test_fake_apply_allowed_without_strict(tmp_path):
    write_control_yaml(
        tmp_path,
        {**minimal_config_dict(), "project": {"id": "vibe-control", "name": "Vibe"}},
    )
    write_doc(tmp_path, "docs/project/vibe-control-spec.md", "# Spec\n")
    env = run_task_apply(
        repo_root=tmp_path,
        mode="dry_run",
        provider_name="fake",
        provider=FakeTaskProvider([]),
        strict_providers=False,
    )
    assert env["ok"] is True
    assert env["mode"] == "dry_run"
    assert env["data"]["knowledge_readiness"]["skipped"] is True


def test_probe_evidence_reused_hash_stable():
    a = build_probe_from_parts(
        knowledge_available=True,
        knowledge_target_ok=True,
        sync_state="synced",
        task_available=True,
        task_mode="readonly",
        task_readable=True,
        ready_queue_available=True,
    )
    b = finalize_product_ready(
        ProviderProbeResult(
            knowledge_available=True,
            knowledge_target_ok=True,
            sync_state="synced",
            ask_hygiene=a.ask_hygiene,
            provider_ask_clean=True,
            task_available=True,
            task_mode="readonly",
            task_readable=True,
            ready_queue_available=True,
        )
    )
    assert a.evidence_hash == b.evidence_hash
    assert a.product_ready is True
