"""Phase 4 config / notebook / sync-preview tests (no real NotebookLM)."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from vibe_control.cli import main
from vibe_control.config import discover_config_path, load_config, validate_config_dict
from vibe_control.knowledge.corpus import build_desired_corpus
from vibe_control.knowledge.managed_titles import format_managed_title, parse_managed_title
from vibe_control.knowledge.sync_preview import (
    RemoteSource,
    build_sync_preview,
    classify_remote_inventory,
    plan_seed_adds,
)
from helpers import control_config_from_dict, minimal_config_dict, write_control_yaml, write_doc, write_registry


def _phase4_config_dict() -> dict:
    raw = minimal_config_dict(
        include_extra=["docs/project/DECISION_LOG.md"],
        max_sources=20,
        warn_sources=15,
    )
    raw["project"] = {"id": "vibe-control", "name": "Vibe Control"}
    raw["knowledge"]["notebooks"] = {
        "default_alias": "OPM-test",
        "allow_list": [
            {
                "alias": "OPM-test",
                "display_name": "OPM-test",
                "ref_env": "NOTEBOOKLM_NOTEBOOK_OPM_TEST",
                "purpose": "phase4_integration_test",
                "allowed_operations": [
                    "status",
                    "inventory",
                    "sync_preview",
                    "add_test_sources_with_approval",
                ],
            }
        ],
    }
    return raw


def test_primary_config_discovered(tmp_path: Path, monkeypatch):
    raw = _phase4_config_dict()
    cfg = tmp_path / ".config" / "vibe-control.yaml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(yaml.safe_dump(raw), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VIBE_CONTROL_CONFIG", raising=False)
    path = discover_config_path(repo_root=tmp_path)
    assert path == cfg.resolve()
    assert load_config(tmp_path).project_id == "vibe-control"


def test_env_config_override(tmp_path: Path, monkeypatch):
    raw = _phase4_config_dict()
    custom = tmp_path / "custom.yaml"
    custom.write_text(yaml.safe_dump(raw), encoding="utf-8")
    monkeypatch.setenv("VIBE_CONTROL_CONFIG", str(custom))
    path = discover_config_path(repo_root=tmp_path)
    assert path == custom.resolve()


def test_legacy_vibe_config_supported(tmp_path: Path, monkeypatch):
    raw = _phase4_config_dict()
    write_control_yaml(tmp_path, raw)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VIBE_CONTROL_CONFIG", raising=False)
    path = discover_config_path(repo_root=tmp_path)
    assert path.name == "control.yaml"
    assert path.parent.name == ".vibe"


def test_missing_config_error(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VIBE_CONTROL_CONFIG", raising=False)
    code = main(["config", "validate", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["error"]["code"] == "CONFIG_NOT_FOUND"


def test_notebooks_config_validates():
    assert validate_config_dict(_phase4_config_dict()) == []


def test_notebook_list_and_unresolved_status(tmp_path: Path, monkeypatch, capsys):
    raw = _phase4_config_dict()
    cfg = tmp_path / ".config" / "vibe-control.yaml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(yaml.safe_dump(raw), encoding="utf-8")
    write_registry(tmp_path, [])
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("NOTEBOOKLM_NOTEBOOK_OPM_TEST", raising=False)
    monkeypatch.delenv("VIBE_CONTROL_CONFIG", raising=False)
    code = main(["knowledge", "notebook", "list", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["data"]["default_alias"] == "OPM-test"
    assert payload["data"]["allow_list"][0]["ref_configured"] is False

    code = main(["knowledge", "notebook", "status", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["data"]["ref_configured"] is False


def test_notebook_status_resolves_env_and_local_file(tmp_path: Path, monkeypatch, capsys):
    raw = _phase4_config_dict()
    cfg = tmp_path / ".config" / "vibe-control.yaml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(yaml.safe_dump(raw), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VIBE_CONTROL_CONFIG", raising=False)

    monkeypatch.setenv("NOTEBOOKLM_NOTEBOOK_OPM_TEST", "nb-from-env")
    code = main(["knowledge", "notebook", "status", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["data"]["ref_configured"] is True
    assert payload["data"]["ref_source"] == "env:NOTEBOOKLM_NOTEBOOK_OPM_TEST"
    assert "nb-from-env" not in json.dumps(payload)  # raw ref not printed

    monkeypatch.delenv("NOTEBOOKLM_NOTEBOOK_OPM_TEST")
    (tmp_path / ".config" / ".env").write_text(
        "NOTEBOOKLM_NOTEBOOK_OPM_TEST=nb-from-file\n",
        encoding="utf-8",
    )
    code = main(["knowledge", "notebook", "status", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["data"]["ref_configured"] is True
    assert payload["data"]["ref_source"] == "file:.config/.env"


def test_unknown_notebook_alias_rejected(tmp_path: Path, monkeypatch, capsys):
    raw = _phase4_config_dict()
    cfg = tmp_path / ".config" / "vibe-control.yaml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(yaml.safe_dump(raw), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    code = main(["knowledge", "notebook", "status", "--notebook", "NOPE", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["error"]["code"] == "NOTEBOOK_ALIAS_UNKNOWN"


def test_project_corpus_rules(tmp_path: Path):
    # Use real project-like layout under tmp
    raw = _phase4_config_dict()
    cfg = tmp_path / ".config" / "vibe-control.yaml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(yaml.safe_dump(raw), encoding="utf-8")
    write_registry(
        tmp_path,
        [
            {
                "id": "vibe_control_v0_5_spec",
                "title": "Vibe Control v0.5 Spec",
                "status": "active",
                "path": "docs/project/VIBE_CONTROL_V0_5_SPEC.md",
            },
            {
                "id": "old_vibe_control_draft",
                "title": "Old",
                "status": "superseded",
                "path": "docs/project/OLD_VIBE_CONTROL_DRAFT.md",
            },
            {
                "id": "plan_doc",
                "title": "Plan",
                "status": "active",
                "path": "docs/program/plans/EXCLUDED_PLAN.md",
            },
        ],
    )
    write_doc(tmp_path, "docs/project/VIBE_CONTROL_V0_5_SPEC.md", "spec")
    write_doc(tmp_path, "docs/project/OLD_VIBE_CONTROL_DRAFT.md", "old")
    write_doc(tmp_path, "docs/program/plans/EXCLUDED_PLAN.md", "plan")
    write_doc(tmp_path, "docs/project/DECISION_LOG.md", "decision")
    write_doc(tmp_path, "docs/dashboard/EXCLUDED_DASHBOARD.md", "dash")
    write_doc(tmp_path, "docs/archive/EXCLUDED_ARCHIVE.md", "arch")
    config = load_config(tmp_path)
    corpus = build_desired_corpus(config, repo_root=tmp_path)
    paths = {d.path for d in corpus.documents}
    assert "docs/project/VIBE_CONTROL_V0_5_SPEC.md" in paths
    assert "docs/project/DECISION_LOG.md" in paths
    assert "docs/project/OLD_VIBE_CONTROL_DRAFT.md" not in paths
    assert "docs/program/plans/EXCLUDED_PLAN.md" not in paths


def test_managed_title_parse_and_classify():
    title = format_managed_title("vibe-control", "vibe_control_v0_5_spec", "Spec")
    parsed = parse_managed_title(title)
    assert parsed is not None
    assert parsed.doc_id == "vibe_control_v0_5_spec"
    sources = [
        RemoteSource(source_id="1", title=title),
        RemoteSource(source_id="2", title="User note"),
        RemoteSource(source_id="3", title="[vibe:vibe-control:orphan] Orphan"),
        RemoteSource(source_id="4", title=title),
    ]
    classified = classify_remote_inventory(
        sources,
        project_id="vibe-control",
        desired_doc_ids={"vibe_control_v0_5_spec"},
    )
    assert classified["unmanaged_count"] == 1
    assert classified["orphan_managed_count"] == 1
    assert classified["duplicate_managed_count"] == 1


def test_sync_preview_ops(tmp_path: Path):
    raw = _phase4_config_dict()
    config = control_config_from_dict(raw, path=tmp_path / ".config" / "vibe-control.yaml")
    write_doc(tmp_path, "docs/project/VIBE_CONTROL_V0_5_SPEC.md", "spec body")
    write_doc(tmp_path, "docs/project/DECISION_LOG.md", "decision")
    write_registry(
        tmp_path,
        [
            {
                "id": "vibe_control_v0_5_spec",
                "title": "Spec",
                "status": "active",
                "path": "docs/project/VIBE_CONTROL_V0_5_SPEC.md",
            }
        ],
    )
    empty = build_sync_preview(
        config,
        repo_root=tmp_path,
        notebook_alias="OPM-test",
        remote_sources=[],
    )
    assert empty["summary"].get("add", 0) >= 1
    assert empty["safe_to_sync"] is False

    present_title = format_managed_title("vibe-control", "vibe_control_v0_5_spec", "Spec")
    present = build_sync_preview(
        config,
        repo_root=tmp_path,
        notebook_alias="OPM-test",
        remote_sources=[RemoteSource(source_id="1", title=present_title)],
    )
    assert present["summary"].get("already_present_needs_verification", 0) >= 1

    blocked = build_sync_preview(
        config,
        repo_root=tmp_path,
        notebook_alias="OPM-test",
        remote_sources=None,
        blocked_reason="NOTEBOOKLM_NOT_CONFIGURED",
    )
    assert blocked["summary"].get("blocked") == 1

    planned = plan_seed_adds(empty)
    assert planned
    assert all(p["path"] in {
        "docs/project/VIBE_CONTROL_V0_5_SPEC.md",
        "docs/project/DECISION_LOG.md",
    } for p in planned)


def test_seed_requires_allow_add(tmp_path: Path, monkeypatch, capsys):
    raw = _phase4_config_dict()
    cfg = tmp_path / ".config" / "vibe-control.yaml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(yaml.safe_dump(raw), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NOTEBOOKLM_NOTEBOOK_OPM_TEST", "nb-test")
    code = main(["knowledge", "seed-test-sources", "--notebook", "OPM-test", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["error"]["code"] == "SEED_REQUIRES_ALLOW_ADD"
