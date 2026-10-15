"""Target-scoped desired corpus (multi-notebook selectors)."""

from __future__ import annotations

from pathlib import Path

import pytest

from vibe_control.config import ControlConfig, validate_config_dict
from vibe_control.knowledge.corpus import (
    CorpusError,
    build_desired_corpus,
    resolve_desired_corpus,
)
from vibe_control.knowledge.notebooks import (
    NotebookError,
    resolve_operation_alias,
)
from vibe_control.spec.registry import SpecEntry


def _base_raw(
    *,
    allow_list: list[dict] | None = None,
    include_extra: list[str] | None = None,
    max_sources: int = 100,
) -> dict:
    notebooks = None
    if allow_list is not None:
        notebooks = {
            "default_alias": allow_list[0]["alias"],
            "allow_list": allow_list,
        }
    return {
        "project": {"id": "demo", "name": "Demo"},
        "knowledge": {
            "provider": "notebooklm",
            "fallback_provider": "repo",
            "max_sources": max_sources,
            "warn_sources": min(80, max_sources),
            "authoritative_statuses": ["active"],
            "include_extra": include_extra or [],
            "exclude_globs": [],
            "source_title_template": "[vibe:{project_id}:{doc_id}] {title}",
            **({"notebooks": notebooks} if notebooks else {}),
        },
        "specs": {
            "registry": "docs/project/spec-registry.yml",
            "required_fields": ["id", "status", "path"],
        },
        "tasks": {"provider": "beads"},
    }


def _config(raw: dict) -> ControlConfig:
    return ControlConfig(
        raw=raw,
        path=Path(".config/vibe-control.yaml"),
        project_id="demo",
        knowledge=raw["knowledge"],
        specs=raw["specs"],
        tasks=raw["tasks"],
    )


def _entries() -> list[SpecEntry]:
    return [
        SpecEntry(
            id="spec-a",
            status="active",
            path="docs/specs/a.md",
            title="A",
            raw={"id": "spec-a", "status": "active", "path": "docs/specs/a.md"},
        ),
        SpecEntry(
            id="spec-b",
            status="active",
            path="docs/ops/b.md",
            title="B",
            raw={"id": "spec-b", "status": "active", "path": "docs/ops/b.md"},
        ),
    ]


def _touch(root: Path) -> None:
    (root / "docs" / "specs").mkdir(parents=True)
    (root / "docs" / "ops").mkdir(parents=True)
    (root / "docs" / "specs" / "a.md").write_text("# A", encoding="utf-8")
    (root / "docs" / "ops" / "b.md").write_text("# B", encoding="utf-8")
    (root / "docs" / "ops" / "runbook.md").write_text("# RB", encoding="utf-8")


def test_no_notebooks_resolve_equals_global(tmp_path: Path):
    _touch(tmp_path)
    cfg = _config(_base_raw())
    global_c = build_desired_corpus(cfg, repo_root=tmp_path, registry_entries=_entries())
    scoped = resolve_desired_corpus(
        cfg, notebook_alias=None, repo_root=tmp_path, registry_entries=_entries()
    )
    assert [d.doc_id for d in scoped.documents] == [d.doc_id for d in global_c.documents]


def test_inherit_path_prefixes_filters(tmp_path: Path):
    _touch(tmp_path)
    raw = _base_raw(
        allow_list=[
            {
                "alias": "spec",
                "ref_env": "NOTEBOOKLM_NOTEBOOK_SPEC",
                "corpus_mode": "inherit",
                "path_prefixes": ["docs/specs/"],
            },
            {
                "alias": "ops",
                "ref_env": "NOTEBOOKLM_NOTEBOOK_OPS",
                "corpus_mode": "inherit",
                "path_prefixes": ["docs/ops/"],
            },
        ]
    )
    cfg = _config(raw)
    spec = resolve_desired_corpus(
        cfg, notebook_alias="spec", repo_root=tmp_path, registry_entries=_entries()
    )
    ops = resolve_desired_corpus(
        cfg, notebook_alias="ops", repo_root=tmp_path, registry_entries=_entries()
    )
    assert [d.doc_id for d in spec.documents] == ["spec-a"]
    assert [d.doc_id for d in ops.documents] == ["spec-b"]
    assert spec.notebook_alias == "spec"
    assert ops.selector_summary["path_prefixes"] == ["docs/ops/"]


def test_replace_uses_only_entry_include_extra(tmp_path: Path):
    _touch(tmp_path)
    raw = _base_raw(
        include_extra=["docs/specs/a.md"],
        allow_list=[
            {
                "alias": "ops",
                "ref_env": "NOTEBOOKLM_NOTEBOOK_OPS",
                "corpus_mode": "replace",
                "include_extra": ["docs/ops/runbook.md"],
                "path_prefixes": ["docs/ops/"],
            }
        ],
    )
    cfg = _config(raw)
    ops = resolve_desired_corpus(
        cfg, notebook_alias="ops", repo_root=tmp_path, registry_entries=_entries()
    )
    assert [d.path for d in ops.documents] == ["docs/ops/runbook.md"]
    assert "spec-a" not in {d.doc_id for d in ops.documents}


def test_inherit_empty_knobs_equals_global(tmp_path: Path):
    _touch(tmp_path)
    raw = _base_raw(
        allow_list=[
            {"alias": "main", "ref_env": "NOTEBOOKLM_NOTEBOOK_MAIN"},
        ]
    )
    cfg = _config(raw)
    global_c = build_desired_corpus(cfg, repo_root=tmp_path, registry_entries=_entries())
    scoped = resolve_desired_corpus(
        cfg, notebook_alias="main", repo_root=tmp_path, registry_entries=_entries()
    )
    assert [d.doc_id for d in scoped.documents] == [d.doc_id for d in global_c.documents]


def test_config_rejects_bad_corpus_mode():
    raw = _base_raw(
        allow_list=[
            {
                "alias": "main",
                "ref_env": "NOTEBOOKLM_NOTEBOOK_MAIN",
                "corpus_mode": "merge",
            }
        ]
    )
    errors = validate_config_dict(raw)
    assert any("corpus_mode" in e for e in errors)


def test_resolve_operation_alias_single_omittable():
    raw = _base_raw(
        allow_list=[{"alias": "only", "ref_env": "NOTEBOOKLM_NOTEBOOK_ONLY"}]
    )
    cfg = _config(raw)
    assert resolve_operation_alias(cfg, None) == "only"
    assert resolve_operation_alias(cfg, "only") == "only"


def test_resolve_operation_alias_multi_requires_explicit():
    raw = _base_raw(
        allow_list=[
            {"alias": "a", "ref_env": "NOTEBOOKLM_NOTEBOOK_A"},
            {"alias": "b", "ref_env": "NOTEBOOKLM_NOTEBOOK_B"},
        ]
    )
    cfg = _config(raw)
    with pytest.raises(NotebookError) as ei:
        resolve_operation_alias(cfg, None)
    assert ei.value.code == "NOTEBOOK_ALIAS_REQUIRED"
    assert resolve_operation_alias(cfg, "b") == "b"


def test_sync_scope_legacy_when_empty_knobs_scoped_when_prefixes(tmp_path: Path):
    from vibe_control.knowledge.corpus import resolve_corpus_for_target, sync_scope_for_corpus

    _touch(tmp_path)
    raw = _base_raw(
        allow_list=[
            {"alias": "main", "ref_env": "NOTEBOOKLM_NOTEBOOK_MAIN"},
            {
                "alias": "spec",
                "ref_env": "NOTEBOOKLM_NOTEBOOK_SPEC",
                "path_prefixes": ["docs/specs/"],
            },
        ]
    )
    cfg = _config(raw)
    _c_main, scope_main = resolve_corpus_for_target(
        cfg, notebook_alias="main", repo_root=tmp_path, registry_entries=_entries()
    )
    _c_spec, scope_spec = resolve_corpus_for_target(
        cfg, notebook_alias="spec", repo_root=tmp_path, registry_entries=_entries()
    )
    assert scope_main == "ssot_files"
    assert scope_spec == "ssot_files:spec"
    assert sync_scope_for_corpus(None, {}) == "ssot_files"


def test_dry_run_plans_differ_per_notebook_corpus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Fake provider: different selectors ⇒ different dry-run desired doc sets."""
    from vibe_control.knowledge.phase8_apply import plan_forward_sync_dry_run
    from vibe_control.knowledge.provider_target import ProviderTarget
    from vibe_control.knowledge.remote_ack import FakeAckStore

    class FakeProvider:
        def list_sources(self, *, notebook_ref: str) -> dict:
            return {"ok": True, "sources": []}

    _touch(tmp_path)
    (tmp_path / "docs" / "project").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "project" / "spec-registry.yml").write_text(
        "- id: spec-a\n  status: active\n  path: docs/specs/a.md\n  title: A\n"
        "- id: spec-b\n  status: active\n  path: docs/ops/b.md\n  title: B\n",
        encoding="utf-8",
    )
    raw = _base_raw(
        allow_list=[
            {
                "alias": "spec",
                "ref_env": "NOTEBOOKLM_NOTEBOOK_SPEC",
                "path_prefixes": ["docs/specs/"],
                "allowed_operations": ["sync"],
            },
            {
                "alias": "ops",
                "ref_env": "NOTEBOOKLM_NOTEBOOK_OPS",
                "path_prefixes": ["docs/ops/"],
                "allowed_operations": ["sync"],
            },
        ]
    )
    cfg = _config(raw)
    monkeypatch.setenv("NOTEBOOKLM_NOTEBOOK_SPEC", "nb-spec")
    monkeypatch.setenv("NOTEBOOKLM_NOTEBOOK_OPS", "nb-ops")
    home = tmp_path / "home"
    home.mkdir()
    provider = FakeProvider()
    ack = FakeAckStore()

    spec_target = ProviderTarget.from_ref(
        provider="notebooklm", notebook_alias="spec", notebook_ref="nb-spec"
    )
    ops_target = ProviderTarget.from_ref(
        provider="notebooklm", notebook_alias="ops", notebook_ref="nb-ops"
    )
    dry_spec = plan_forward_sync_dry_run(
        cfg,
        repo_root=tmp_path,
        target=spec_target,
        notebook_ref="nb-spec",
        provider=provider,
        ack_store=ack,
        home=home,
    )
    dry_ops = plan_forward_sync_dry_run(
        cfg,
        repo_root=tmp_path,
        target=ops_target,
        notebook_ref="nb-ops",
        provider=provider,
        ack_store=ack,
        home=home,
    )
    assert dry_spec.get("ok") is True
    assert dry_ops.get("ok") is True
    assert dry_spec.get("sync_scope") == "ssot_files:spec"
    assert dry_ops.get("sync_scope") == "ssot_files:ops"
    spec_ids = {
        o["doc_id"]
        for o in (dry_spec.get("operations") or [])
        if o.get("op") in {"add_missing", "replace_required", "already_current"}
    }
    ops_ids = {
        o["doc_id"]
        for o in (dry_ops.get("operations") or [])
        if o.get("op") in {"add_missing", "replace_required", "already_current"}
    }
    assert spec_ids == {"spec-a"}
    assert ops_ids == {"spec-b"}
    assert dry_spec.get("snapshot_hash") != dry_ops.get("snapshot_hash")
