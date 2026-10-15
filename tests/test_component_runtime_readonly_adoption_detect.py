"""Component Runtime Slice 4 — readonly adoption detection/reporting."""

from __future__ import annotations

import json

from helpers import minimal_config_dict, write_control_yaml, write_doc
from vibe_control.cli import main
from vibe_control.components import (
    COMPONENT_CATALOG,
    build_component_adoption_detection,
    resolve_component_runtime,
)
from vibe_control.integration import build_integration_status
from vibe_control.knowledge.doctor import build_knowledge_init_preview
from vibe_control.knowledge.notebooklm_provider import NotebookLMProvider, NotebookLMStatus
from vibe_control.product_readiness import build_probe_from_parts
from vibe_control.task.beads_provider import BeadsProvider, BeadsStatus


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


def _green_probe(**overrides):
    base = dict(
        knowledge_available=True,
        knowledge_target_ok=True,
        sync_state="synced",
        required_updates_count=0,
        candidate_count=0,
        orphan_managed_count=0,
        task_available=True,
        task_mode="readonly",
        task_readable=True,
        ready_queue_available=True,
        task_cache_current=True,
    )
    base.update(overrides)
    return build_probe_from_parts(**base)


def _write_repo(tmp_path, *, components=None):
    raw = {
        **minimal_config_dict(enable_knowledge=False, enable_task=False),
        "project": {"id": "vibe-control", "name": "Vibe"},
    }
    if components is not None:
        raw["components"] = components
    write_control_yaml(tmp_path, raw)
    write_doc(tmp_path, "docs/project/vibe-control-spec.md", "# Spec\n")
    write_doc(tmp_path, "docs/project/spec-registry.yml", "entries: []\n")


def test_adoption_candidates_derived_from_catalog_hints():
    report = build_component_adoption_detection(which=lambda _name: None)
    assert report["diagnostic_only"] is True
    assert report["mutation"] is False
    assert report["adoption_performed"] is False
    assert report["readiness_effect"] == "none"
    candidates = report["component_adoption"]["candidates"]
    ids = {c["candidate_id"] for c in candidates}
    assert ids == {"openspec", "spec_kit", "superpowers", "codebase_memory", "codegraph"}
    by_id = {c["candidate_id"]: c for c in candidates}
    assert by_id["openspec"]["component_id"] == "sdd"
    assert by_id["spec_kit"]["component_id"] == "sdd"
    assert by_id["superpowers"]["component_id"] == "tdd"
    assert by_id["codebase_memory"]["component_id"] == "hetu"
    assert by_id["codegraph"]["component_id"] == "hetu"
    for c in candidates:
        assert c["detection_status"] == "not_detected"
        assert c["adopted"] is False
        assert c["provider_bound"] is False
        assert c["advisory"] is True


def test_catalog_provider_hints_match_front_core():
    assert COMPONENT_CATALOG["sdd"]["provider_hints"] == ["openspec", "spec_kit"]
    assert COMPONENT_CATALOG["tdd"]["provider_hints"] == ["superpowers"]
    assert COMPONENT_CATALOG["hetu"]["provider_hints"] == ["codebase_memory", "codegraph"]
    assert not COMPONENT_CATALOG["knowledge"].get("provider_hints")
    assert not COMPONENT_CATALOG["task"].get("provider_hints")


def test_detected_candidate_remains_advisory_not_adopted():
    def fake_which(name: str):
        if name == "openspec":
            return "/tmp/fake-openspec"
        return None

    report = build_component_adoption_detection(which=fake_which)
    by_id = {c["candidate_id"]: c for c in report["component_adoption"]["candidates"]}
    assert by_id["openspec"]["detection_status"] == "detected"
    assert by_id["openspec"]["adopted"] is False
    assert by_id["openspec"]["provider_bound"] is False
    assert by_id["spec_kit"]["detection_status"] == "not_detected"
    assert report["adoption_performed"] is False
    assert report["readiness_effect"] == "none"
    runtime = resolve_component_runtime(None)
    assert runtime["config_ok"] is True
    assert runtime["components"]["sdd"]["enabled"] is False
    assert runtime["components"]["tdd"]["enabled"] is False


def test_unavailable_detection_is_not_empty_inventory():
    def boom(name: str):
        raise RuntimeError(f"probe failed for {name}")

    report = build_component_adoption_detection(which=boom)
    candidates = report["component_adoption"]["candidates"]
    assert candidates, "unavailable must still list candidates (not empty inventory)"
    assert all(c["detection_status"] == "unavailable" for c in candidates)
    assert all(c["adopted"] is False for c in candidates)
    assert report["component_adoption"]["empty_inventory"] is False
    assert report["adoption_performed"] is False


def test_not_detected_does_not_block_product_ready():
    report = build_component_adoption_detection(which=lambda _n: None)
    assert all(
        c["detection_status"] == "not_detected"
        for c in report["component_adoption"]["candidates"]
    )
    runtime = resolve_component_runtime(None)
    probe = _green_probe(
        config_ok=runtime["config_ok"],
        components=runtime["components"],
        component_blocked_reasons=runtime["blocked_reasons"],
    )
    assert probe.product_ready is True
    assert probe.config_ok is True


def test_detected_does_not_flip_product_ready_or_config_ok():
    def fake_which(name: str):
        return f"/tmp/fake-{name}"

    report = build_component_adoption_detection(which=fake_which)
    assert any(
        c["detection_status"] == "detected"
        for c in report["component_adoption"]["candidates"]
    )
    runtime = resolve_component_runtime(None)
    probe = _green_probe(
        config_ok=runtime["config_ok"],
        components=runtime["components"],
        component_blocked_reasons=runtime["blocked_reasons"],
    )
    assert probe.product_ready is True
    assert probe.config_ok is True
    assert report["readiness_effect"] == "none"


def test_doctor_exposes_readonly_adoption_detection(tmp_path, monkeypatch, capsys):
    _write_repo(tmp_path)
    cfg = tmp_path / ".vibe" / "control.yaml"
    before = cfg.read_text(encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("vibe_control.cli.NotebookLMProvider", FakeNLM)
    monkeypatch.setattr("vibe_control.cli.BeadsProvider", FakeBeads)
    monkeypatch.setattr(
        "vibe_control.components.shutil.which",
        lambda name: "/tmp/fake-openspec" if name == "openspec" else None,
    )
    code = main(["doctor", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload.get("mutation") is not True
    data = payload["data"]
    assert data["config_ok"] is True
    assert "components" in data
    assert "component_blocked_reasons" in data
    assert data["diagnostic_only"] is True
    assert data["mutation"] is False
    adoption = data["component_adoption"]
    assert data["adoption_performed"] is False
    assert data["readiness_effect"] == "none"
    assert adoption["diagnostic_only"] is True
    assert adoption["mutation"] is False
    assert adoption["adoption_performed"] is False
    assert adoption["empty_inventory"] is False
    candidates = adoption["candidates"]
    by_id = {c["candidate_id"]: c for c in candidates}
    assert by_id["openspec"]["detection_status"] == "detected"
    assert by_id["openspec"]["adopted"] is False
    assert by_id["spec_kit"]["detection_status"] == "not_detected"
    assert by_id["superpowers"]["detection_status"] == "not_detected"
    assert cfg.read_text(encoding="utf-8") == before
    assert data["components"]["sdd"]["enabled"] is False
    assert data["components"]["tdd"]["enabled"] is False


def test_init_preview_exposes_readonly_adoption_detection(tmp_path, monkeypatch):
    _write_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "vibe_control.components.shutil.which",
        lambda _name: None,
    )
    envelope = build_knowledge_init_preview(
        repo_root=tmp_path,
        notebooklm=FakeNLM(),
    )
    assert envelope["mutation"] is False
    data = envelope["data"]
    assert data["mutation"] is False
    assert data["diagnostic_only"] is True
    assert data["adoption_performed"] is False
    assert data["readiness_effect"] == "none"
    adoption = data["component_adoption"]
    assert adoption["mutation"] is False
    assert all(c["detection_status"] == "not_detected" for c in adoption["candidates"])
    assert all(c["adopted"] is False for c in adoption["candidates"])


def test_integration_status_unaffected_by_adoption_detection(tmp_path, monkeypatch):
    monkeypatch.setenv("VIBE_SKILLS_ROOT", str(tmp_path / "skills"))
    _write_repo(tmp_path)
    monkeypatch.setattr(
        "vibe_control.components.shutil.which",
        lambda name: f"/tmp/{name}",
    )
    data = build_integration_status(
        repo_root=tmp_path,
        notebooklm=FakeNLM(),
        beads=FakeBeads(),
        probe_product=False,
        knowledge_parts={
            "available": True,
            "target_ok": True,
            "sync_state": "synced",
            "required_updates_count": 0,
            "candidate_count": 0,
            "orphan_managed_count": 0,
        },
        task_parts={
            "available": True,
            "mode": "readonly",
            "readable": True,
            "ready_queue_available": True,
        },
    )
    assert data["config_ok"] is True
    assert set(data["components"]) == {"knowledge", "task", "hetu", "sdd", "tdd"}
    assert data["components"]["sdd"]["enabled"] is False
    assert data["components"]["tdd"]["enabled"] is False
    assert data["product_ready"] is True
