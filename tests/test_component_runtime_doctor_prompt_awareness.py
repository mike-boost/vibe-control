"""Component Runtime Slice 2 — doctor + implementation prompt awareness."""

from __future__ import annotations

import json

from helpers import minimal_config_dict, write_control_yaml, write_doc
from vibe_control.cli import main
from vibe_control.implementation.prompt import build_implementation_prompt
from vibe_control.knowledge.notebooklm_provider import NotebookLMProvider, NotebookLMStatus
from vibe_control.product_readiness import evaluate_product_readiness
from vibe_control.task.beads_provider import BeadsProvider, BeadsStatus

SLICE2 = "roadmap.component_runtime_doctor_prompt_awareness"


class FakeNLM(NotebookLMProvider):
    def which(self):
        return "/tmp/fake-nlm"

    def status(self, *, probe_auth: bool = False) -> NotebookLMStatus:
        return NotebookLMStatus(
            installed=True, executable="/tmp/fake-nlm", version="x", message="ok"
        )


class FakeBeads(BeadsProvider):
    def which(self):
        return "/tmp/fake-bd"

    def status(self) -> BeadsStatus:
        return BeadsStatus(installed=True, executable="/tmp/fake-bd", version="x", message="ok")

    def init_preview(self) -> BeadsStatus:
        return self.status()


def _write_repo(tmp_path, *, components=None, actionable_slice2: bool = True):
    raw = {
        **minimal_config_dict(enable_knowledge=False, enable_task=False),
        "project": {"id": "vibe-control", "name": "Vibe"},
    }
    if components is not None:
        raw["components"] = components
    write_control_yaml(tmp_path, raw)
    write_doc(tmp_path, "docs/project/vibe-control-spec.md", "# Spec\n")
    write_doc(tmp_path, "docs/project/spec-registry.yml", "entries: []\n")
    phase = "accepted" if actionable_slice2 else "completed"
    actionable = "true" if actionable_slice2 else "false"
    write_doc(
        tmp_path,
        "docs/project/vibe-control-roadmap-state.md",
        f"""# Roadmap

```yaml
roadmap_state_version: 1
next_actionable_task: {SLICE2 if actionable_slice2 else "null"}
no_actionable_next_task: {"false" if actionable_slice2 else "true"}
rules:
  do_not_invent_phase13: true
anchors:
  - ssot_anchor: {SLICE2}
    task_kind: implementation_task
    title: "Component Runtime Slice 2 — Doctor / implementation prompt awareness"
    phase_state: {phase}
    actionable: {actionable}
```
""",
    )


def test_doctor_default_valid_config_ok(tmp_path, monkeypatch, capsys):
    _write_repo(tmp_path, components=None)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("vibe_control.cli.NotebookLMProvider", FakeNLM)
    monkeypatch.setattr("vibe_control.cli.BeadsProvider", FakeBeads)
    code = main(["doctor", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["ok"] is True
    data = payload["data"]
    assert data["config_ok"] is True
    assert set(data["components"]) == {"knowledge", "task", "hetu", "sdd", "tdd"}
    assert data["components"]["knowledge"]["enabled"] is False
    assert data["components"]["task"]["enabled"] is False
    reasons = data.get("component_blocked_reasons") or []
    assert reasons == []
    assert not any("unavailable" in str(r) for r in reasons)


def test_doctor_sdd_enabled_unsupported(tmp_path, monkeypatch, capsys):
    _write_repo(tmp_path, components={"sdd": {"enabled": True}})
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("vibe_control.cli.NotebookLMProvider", FakeNLM)
    monkeypatch.setattr("vibe_control.cli.BeadsProvider", FakeBeads)
    code = main(["doctor", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    data = payload["data"]
    assert data["config_ok"] is False
    assert "unsupported_component_enabled" in data["component_blocked_reasons"]
    blob = json.dumps(payload).lower()
    assert "provider_unavailable" not in blob
    assert "knowledge_provider_unavailable" not in data["component_blocked_reasons"]


def test_doctor_knowledge_disabled_is_valid(tmp_path, monkeypatch, capsys):
    _write_repo(tmp_path, components={"knowledge": {"enabled": False}})
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("vibe_control.cli.NotebookLMProvider", FakeNLM)
    monkeypatch.setattr("vibe_control.cli.BeadsProvider", FakeBeads)
    code = main(["doctor", "--json"])
    payload = json.loads(capsys.readouterr().out)
    data = payload["data"]
    assert data["config_ok"] is True
    assert "required_component_disabled" not in data["component_blocked_reasons"]
    assert data["components"]["knowledge"]["enabled"] is False


def test_doctor_unknown_component(tmp_path, monkeypatch, capsys):
    _write_repo(tmp_path, components={"openspec": {"enabled": True}})
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("vibe_control.cli.NotebookLMProvider", FakeNLM)
    monkeypatch.setattr("vibe_control.cli.BeadsProvider", FakeBeads)
    code = main(["doctor", "--json"])
    payload = json.loads(capsys.readouterr().out)
    data = payload["data"]
    assert data["config_ok"] is False
    assert "unknown_component_configured" in data["component_blocked_reasons"]


def test_doctor_component_failure_not_provider_unavailable(tmp_path, monkeypatch, capsys):
    _write_repo(tmp_path, components={"tdd": {"enabled": True}})
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("vibe_control.cli.NotebookLMProvider", FakeNLM)
    monkeypatch.setattr("vibe_control.cli.BeadsProvider", FakeBeads)
    main(["doctor", "--json"])
    payload = json.loads(capsys.readouterr().out)
    data = payload["data"]
    assert data["config_ok"] is False
    joined = " ".join(data["component_blocked_reasons"])
    assert "unsupported_component_enabled" in joined
    assert "unavailable" not in joined
    # Provider status fields remain separate (presence ≠ config failure class).
    assert "notebooklm" in data
    assert "beads" in data


def _green_readiness(**overrides):
    base = {
        "product_ready": True,
        "sync_state": "synced",
        "provider_ask_clean": True,
        "blocked_reasons": [],
        "knowledge_available": True,
        "knowledge_target_ok": True,
        "config_ok": True,
    }
    base.update(overrides)
    return base


def test_prompt_default_valid_includes_implement_and_component_fields(tmp_path):
    _write_repo(tmp_path, components=None)
    result = build_implementation_prompt(
        repo_root=tmp_path,
        task_selector=SLICE2,
        product_ready=True,
        readiness_summary=_green_readiness(),
        knowledge_readiness={
            "sync_state": "synced",
            "provider_ask_clean": True,
            "available": True,
            "target_ok": True,
        },
        reconcile_counts={
            "matched": 1,
            "missing": 0,
            "stale": 0,
            "duplicate": 0,
            "conflict": 0,
            "unmanaged": 0,
        },
        apply_plan_counts={"create": 0, "update": 0, "skip": 0, "blocked": 0},
        provider_sync_required=False,
    )
    data = result["data"]
    assert data["implementation_ready"] is True
    assert "Implement:" in data["prompt"]
    pr = data["product_readiness"]
    assert pr.get("config_ok") is True
    assert "components" in pr or "component_runtime" in data
    comps = pr.get("components") or (data.get("component_runtime") or {}).get("components")
    assert set(comps) == {"knowledge", "task", "hetu", "sdd", "tdd"}
    assert "config_ok" in data["prompt"]
    # Redaction
    blob = data["prompt"].lower()
    assert "notebooklm://" not in blob
    assert "source_id" not in blob
    assert "bd-" not in blob  # raw beads-ish ids


def test_prompt_sdd_enabled_blocks_greenlight(tmp_path):
    _write_repo(tmp_path, components={"sdd": {"enabled": True}})
    probe = evaluate_product_readiness(
        repo_root=tmp_path,
        knowledge={
            "available": True,
            "target_ok": True,
            "sync_state": "synced",
            "required_updates_count": 0,
            "candidate_count": 0,
            "orphan_managed_count": 0,
        },
        task={
            "available": True,
            "mode": "readonly",
            "readable": True,
            "ready_queue_available": True,
        },
        probe=False,
    )
    assert probe.config_ok is False
    assert probe.product_ready is False
    result = build_implementation_prompt(
        repo_root=tmp_path,
        task_selector=SLICE2,
        readiness_summary={
            "product_ready": probe.product_ready,
            "sync_state": probe.sync_state,
            "provider_ask_clean": True,
            "blocked_reasons": list(probe.blocked_reasons),
            "config_ok": probe.config_ok,
            "components": dict(probe.components),
        },
        knowledge_readiness={
            "sync_state": "synced",
            "provider_ask_clean": True,
            "available": True,
            "target_ok": True,
        },
        reconcile_counts={
            "matched": 1,
            "missing": 0,
            "stale": 0,
            "duplicate": 0,
            "conflict": 0,
            "unmanaged": 0,
        },
        apply_plan_counts={"create": 0, "update": 0, "skip": 0, "blocked": 0},
        provider_sync_required=False,
        task_cache={"task_cache_current": True},
    )
    data = result["data"]
    assert data["implementation_ready"] is False
    assert "Implement:" not in data["prompt"]
    assert "unsupported_component_enabled" in data["prompt"]
    assert data["product_readiness"]["config_ok"] is False


def test_prompt_knowledge_disabled_does_not_require_component_block(tmp_path):
    _write_repo(tmp_path, components={"knowledge": {"enabled": False}})
    result = build_implementation_prompt(
        repo_root=tmp_path,
        task_selector=SLICE2,
        readiness_summary=_green_readiness(
            product_ready=True,
            config_ok=True,
            blocked_reasons=[],
        ),
        knowledge_readiness={
            "sync_state": "synced",
            "provider_ask_clean": True,
            "available": True,
            "target_ok": True,
        },
        reconcile_counts={
            "matched": 1,
            "missing": 0,
            "stale": 0,
            "duplicate": 0,
            "conflict": 0,
            "unmanaged": 0,
        },
        apply_plan_counts={"create": 0, "update": 0, "skip": 0, "blocked": 0},
        provider_sync_required=False,
        task_cache={"task_cache_current": True},
    )
    data = result["data"]
    assert data["product_readiness"]["config_ok"] is True
    assert "required_component_disabled" not in (data.get("prompt") or "")


def test_prompt_unknown_component_blocks_greenlight(tmp_path):
    _write_repo(tmp_path, components={"openspec": {"enabled": False}})
    result = build_implementation_prompt(
        repo_root=tmp_path,
        task_selector=SLICE2,
        # Intentionally omit config_ok — builder must resolve from repo.
        readiness_summary=_green_readiness(product_ready=True, config_ok=True),
        knowledge_readiness={
            "sync_state": "synced",
            "provider_ask_clean": True,
            "available": True,
            "target_ok": True,
        },
        reconcile_counts={
            "matched": 1,
            "missing": 0,
            "stale": 0,
            "duplicate": 0,
            "conflict": 0,
            "unmanaged": 0,
        },
        apply_plan_counts={"create": 0, "update": 0, "skip": 0, "blocked": 0},
        provider_sync_required=False,
        task_cache={"task_cache_current": True},
    )
    data = result["data"]
    assert data["implementation_ready"] is False
    assert "Implement:" not in data["prompt"]
    assert "unknown_component_configured" in data["prompt"]
    assert data["product_readiness"]["config_ok"] is False


def test_prompt_redacts_provider_ids_and_secrets(tmp_path):
    _write_repo(tmp_path, components=None)
    result = build_implementation_prompt(
        repo_root=tmp_path,
        task_selector=SLICE2,
        readiness_summary=_green_readiness(),
        knowledge_readiness={
            "sync_state": "synced",
            "provider_ask_clean": True,
            "available": True,
            "target_ok": True,
        },
        reconcile_counts={
            "matched": 1,
            "missing": 0,
            "stale": 0,
            "duplicate": 0,
            "conflict": 0,
            "unmanaged": 0,
        },
        apply_plan_counts={"create": 0, "update": 0, "skip": 0, "blocked": 0},
        provider_task_id="vibe-control-RAW-SECRET-ID",
        redact_provider_ids=True,
        notebook_ref_raw="notebooklm://secret-notebook-ref",
        provider_sync_required=False,
        task_cache={"task_cache_current": True},
    )
    prompt = result["data"]["prompt"]
    blob = json.dumps(result["data"])
    assert "vibe-control-RAW-SECRET-ID" not in blob
    assert "notebooklm://secret-notebook-ref" not in blob
    assert "provider_task_id_hash" in prompt
    assert result["data"]["task_context"]["provider_task_id_is_identity"] is False
