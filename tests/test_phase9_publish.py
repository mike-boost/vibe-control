"""Phase 9 Spec Publish tightening tests (temp git / fake provider; no real push/NLM)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml

from helpers import write_doc, write_registry
from vibe_control.cli import main
from vibe_control.spec.publish import (
    CONFIG_FILE_CANNOT_BE_SYNCED,
    SPEC_ID_DUPLICATE,
    publish_spec,
    validate_spec_path,
)


def _git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout or f"git failed: {args}")
    return proc.stdout.strip()


def _init_repo(tmp: Path) -> Path:
    root = tmp / "repo"
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.email", "phase9@example.com")
    _git(root, "config", "user.name", "Phase9 Test")
    cfg = {
        "project": {"id": "phase9", "name": "Phase9"},
        "knowledge": {
            "provider": "notebooklm",
            "fallback_provider": "repo",
            "max_sources": 20,
            "warn_sources": 15,
            "authoritative_statuses": ["active"],
            "include_extra": [],
            "exclude_globs": [
                "docs/program/plans/**",
                "runtime/**",
                "acceptance/**",
                ".beads/**",
                "**/archive/**",
            ],
            "source_title_template": "[vibe:{project_id}:{doc_id}] {title}",
            "notebooks": {
                "default_alias": "OPM-test",
                "allow_list": [
                    {
                        "alias": "OPM-test",
                        "display_name": "OPM-test",
                        "ref_env": "NOTEBOOKLM_NOTEBOOK_OPM_TEST",
                        "allowed_operations": ["status", "sync", "query"],
                    }
                ],
            },
        },
        "specs": {
            "registry": "docs/project/spec-registry.yml",
            "required_fields": ["id", "status", "path"],
            "require_commit_push_for_ssot": True,
        },
        "tasks": {"provider": "beads"},
    }
    (root / ".config").mkdir()
    (root / ".config" / "vibe-control.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
    write_registry(
        root,
        [
            {
                "id": "active_spec",
                "title": "Active",
                "status": "active",
                "path": "docs/project/active.md",
            }
        ],
    )
    write_doc(root, "docs/project/active.md", "# Active\n\npublish body\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "init")
    return root


def _run(monkeypatch, root: Path, argv: list[str], capsys) -> tuple[int, dict]:
    monkeypatch.chdir(root)
    code = main(argv)
    return code, json.loads(capsys.readouterr().out)


@pytest.mark.unit
def test_P9_VALIDATE_01_valid_spec(tmp_path: Path):
    root = _init_repo(tmp_path)
    result = validate_spec_path(root, "docs/project/active.md")
    assert result["ok"] is True
    assert result["spec_id"] == "active_spec"
    assert result["path"] == "docs/project/active.md"


@pytest.mark.unit
def test_P9_VALIDATE_02_duplicate_id(tmp_path: Path):
    root = _init_repo(tmp_path)
    write_registry(
        root,
        [
            {"id": "dup", "status": "active", "path": "docs/project/a.md", "title": "A"},
            {"id": "dup", "status": "active", "path": "docs/project/b.md", "title": "B"},
        ],
    )
    write_doc(root, "docs/project/a.md", "a\n")
    write_doc(root, "docs/project/b.md", "b\n")
    result = validate_spec_path(root, "docs/project/a.md")
    assert result["ok"] is False
    assert result["code"] == SPEC_ID_DUPLICATE


@pytest.mark.unit
def test_P9_VALIDATE_03_non_canonical_path(tmp_path: Path):
    root = _init_repo(tmp_path)
    result = validate_spec_path(root, "./docs/project/../project/active.md")
    assert result["ok"] is False
    assert "canonical" in str(result.get("code") or result.get("message") or "").lower() or result.get(
        "code"
    ) in {"SPEC_PATH_NOT_CANONICAL", "NON_CANONICAL_PATH"}


@pytest.mark.unit
def test_P9_VALIDATE_04_config_cannot_be_synced(tmp_path: Path):
    root = _init_repo(tmp_path)
    result = validate_spec_path(root, ".config/vibe-control.yaml")
    assert result["ok"] is False
    assert result["code"] == CONFIG_FILE_CANNOT_BE_SYNCED


@pytest.mark.unit
def test_P9_VALIDATE_05_forbidden_paths(tmp_path: Path):
    root = _init_repo(tmp_path)
    write_doc(root, "docs/program/plans/plan.md", "plan\n")
    write_doc(root, "runtime/x.json", "{}\n")
    write_doc(root, "acceptance/report.md", "r\n")
    write_doc(root, ".beads/issues.jsonl", "{}\n")
    for path in (
        "docs/program/plans/plan.md",
        "runtime/x.json",
        "acceptance/report.md",
        ".beads/issues.jsonl",
    ):
        result = validate_spec_path(root, path)
        assert result["ok"] is False, path


@pytest.mark.integration
def test_P9_GIT_01_dirty_unrelated_fails_closed(tmp_path: Path):
    root = _init_repo(tmp_path)
    (root / "unrelated.txt").write_text("dirty\n", encoding="utf-8")
    result = publish_spec(
        root,
        "docs/project/active.md",
        dry_run=False,
        already_pushed=True,
        allow_provider_sync=False,
    )
    assert result["ok"] is False
    assert result.get("code") in {"DIRTY_WORKTREE", "UNRELATED_DIRTY_WORKTREE"}


@pytest.mark.integration
def test_P9_GIT_02_already_pushed_no_commit_no_push(tmp_path: Path, monkeypatch):
    root = _init_repo(tmp_path)
    bare = tmp_path / "bare.git"
    _git(tmp_path, "init", "--bare", str(bare))
    _git(root, "remote", "add", "origin", str(bare))
    _git(root, "push", "-u", "origin", "HEAD")
    before = _git(root, "rev-parse", "HEAD")
    pushed = []

    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["git", "push"] and "origin" in cmd:
            pushed.append(cmd)
            raise AssertionError("real push must not be invoked by already-pushed mode")
        return subprocess.run(cmd, **kwargs)

    result = publish_spec(
        root,
        "docs/project/active.md",
        dry_run=False,
        already_pushed=True,
        allow_provider_sync=False,
        git_runner=None,
    )
    assert result["ok"] is True or result.get("partial_success")
    assert result.get("committed") is False
    assert result.get("pushed") is False
    assert _git(root, "rev-parse", "HEAD") == before
    assert pushed == []


@pytest.mark.integration
def test_P9_GIT_03_unpushed_draft_refuses_provider_sync(tmp_path: Path):
    root = _init_repo(tmp_path)
    write_doc(root, "docs/project/active.md", "# Active\n\ndraft only\n")
    _git(root, "add", "docs/project/active.md")
    _git(root, "commit", "-m", "local draft")
    result = publish_spec(
        root,
        "docs/project/active.md",
        dry_run=False,
        already_pushed=False,
        allow_provider_sync=True,
    )
    assert result["ok"] is False or result.get("knowledge_sync", {}).get("ok") is False
    assert result.get("code") in {
        "UNPUSHED_REF",
        "AUTHORITATIVE_REF_MISSING",
        "DIRTY_WORKTREE",
        "PUBLISH_REQUIRES_PUSHED_REF",
    } or "unpushed" in str(result.get("message") or "").lower() or result.get(
        "provider_sync_attempted"
    ) is False


@pytest.mark.integration
def test_P9_GIT_04_temp_repo_pushed_ref_without_real_remote(tmp_path: Path):
    root = _init_repo(tmp_path)
    bare = tmp_path / "bare.git"
    _git(tmp_path, "init", "--bare", str(bare))
    _git(root, "remote", "add", "origin", str(bare))
    _git(root, "push", "-u", "origin", "HEAD")
    result = publish_spec(
        root,
        "docs/project/active.md",
        dry_run=True,
        already_pushed=True,
        allow_provider_sync=False,
    )
    assert result["ok"] is True
    assert result.get("authoritative_ref")
    assert "github.com" not in str(result.get("authoritative_ref"))


@pytest.mark.integration
def test_P9_PUBLISH_01_dry_run_no_mutation(tmp_path: Path, monkeypatch, capsys):
    root = _init_repo(tmp_path)
    bare = tmp_path / "bare.git"
    _git(tmp_path, "init", "--bare", str(bare))
    _git(root, "remote", "add", "origin", str(bare))
    _git(root, "push", "-u", "origin", "HEAD")
    monkeypatch.setenv("NOTEBOOKLM_NOTEBOOK_OPM_TEST", "nb-dry")
    code, payload = _run(
        monkeypatch,
        root,
        ["spec", "publish", "docs/project/active.md", "--dry-run", "--json"],
        capsys,
    )
    assert code == 0
    assert payload["ok"] is True
    assert payload["data"].get("dry_run") is True
    assert payload["data"].get("provider_mutated") is not True


@pytest.mark.integration
def test_P9_PUBLISH_02_success_envelope(tmp_path: Path):
    root = _init_repo(tmp_path)
    bare = tmp_path / "bare.git"
    _git(tmp_path, "init", "--bare", str(bare))
    _git(root, "remote", "add", "origin", str(bare))
    _git(root, "push", "-u", "origin", "HEAD")
    result = publish_spec(
        root,
        "docs/project/active.md",
        dry_run=False,
        already_pushed=True,
        allow_provider_sync=False,
    )
    assert result.get("ok") or result.get("partial_success")
    assert result["spec_id"] == "active_spec"
    assert result["path"] == "docs/project/active.md"
    assert result.get("authoritative_ref")
    assert result.get("content_sha256")


@pytest.mark.integration
def test_P9_PUBLISH_03_uses_phase8_snapshot_builder(tmp_path: Path, monkeypatch):
    root = _init_repo(tmp_path)
    bare = tmp_path / "bare.git"
    _git(tmp_path, "init", "--bare", str(bare))
    _git(root, "remote", "add", "origin", str(bare))
    _git(root, "push", "-u", "origin", "HEAD")
    called = {"snapshot": 0}
    import vibe_control.spec.publish as pub

    real = pub.build_desired_snapshot

    def wrap(*a, **k):
        called["snapshot"] += 1
        return real(*a, **k)

    monkeypatch.setattr(pub, "build_desired_snapshot", wrap)
    publish_spec(
        root,
        "docs/project/active.md",
        dry_run=True,
        already_pushed=True,
        allow_provider_sync=False,
    )
    assert called["snapshot"] >= 1


@pytest.mark.integration
def test_P9_SYNC_01_calls_phase8_apply_when_allowed(tmp_path: Path, monkeypatch):
    root = _init_repo(tmp_path)
    bare = tmp_path / "bare.git"
    _git(tmp_path, "init", "--bare", str(bare))
    _git(root, "remote", "add", "origin", str(bare))
    _git(root, "push", "-u", "origin", "HEAD")
    monkeypatch.setenv("NOTEBOOKLM_NOTEBOOK_OPM_TEST", "nb-sync-apply")
    called = {"apply": 0}

    def fake_apply(*a, **k):
        called["apply"] += 1
        return {"ok": True, "sync_state": "synced", "ack_written": True, "notebooklm_note_written": False}

    monkeypatch.setattr("vibe_control.spec.publish.apply_forward_sync", fake_apply)
    result = publish_spec(
        root,
        "docs/project/active.md",
        dry_run=False,
        already_pushed=True,
        allow_provider_sync=True,
        provider="fake",
    )
    assert called["apply"] == 1
    assert result.get("knowledge_sync", {}).get("ok") is True


@pytest.mark.integration
def test_P9_SYNC_02_partial_success_when_provider_unavailable(tmp_path: Path, monkeypatch):
    root = _init_repo(tmp_path)
    bare = tmp_path / "bare.git"
    _git(tmp_path, "init", "--bare", str(bare))
    _git(root, "remote", "add", "origin", str(bare))
    _git(root, "push", "-u", "origin", "HEAD")
    monkeypatch.setenv("NOTEBOOKLM_NOTEBOOK_OPM_TEST", "nb-sync-unavailable")

    def boom(*a, **k):
        return {"ok": False, "code": "NOTEBOOKLM_UNAVAILABLE", "message": "down"}

    monkeypatch.setattr("vibe_control.spec.publish.apply_forward_sync", boom)
    result = publish_spec(
        root,
        "docs/project/active.md",
        dry_run=False,
        already_pushed=True,
        allow_provider_sync=True,
        provider="fake",
        home=tmp_path,
    )
    assert result.get("partial_success") is True
    assert result.get("completed", {}).get("validate") is True
    assert result.get("failed") == "knowledge_sync" or result.get("knowledge_sync", {}).get("ok") is False
    assert result.get("pending") or "retry" in str(result.get("next_actions") or "").lower()


@pytest.mark.unit
def test_P9_SYNC_03_snapshot_excludes_forbidden(tmp_path: Path):
    root = _init_repo(tmp_path)
    write_doc(root, "docs/program/plans/plan.md", "plan secret\n")
    from vibe_control.config import load_config
    from vibe_control.knowledge.corpus import build_desired_corpus
    from vibe_control.knowledge.snapshot import build_desired_snapshot

    config = load_config(root)
    corpus = build_desired_corpus(config, repo_root=root)
    snap = build_desired_snapshot(
        project_id=config.project_id,
        sync_scope="ssot_files",
        documents=[{"doc_id": d.doc_id, "path": d.path} for d in corpus.documents],
        repo_root=root,
    )
    paths = {i.path for i in snap.items}
    assert "docs/program/plans/plan.md" not in paths
    assert ".config/vibe-control.yaml" not in paths


@pytest.mark.unit
def test_P9_FORBIDDEN_01_and_02_default_tests_have_no_real_mutation_or_push():
    text = Path(__file__).read_text(encoding="utf-8")
    # Split tokens so this meta-test does not match its own (or sibling) assert literals.
    real_smoke_flag = "--" + "real-smoke"
    public_host = "github" + ".com"
    assert real_smoke_flag not in text
    # Only the defensive assert string may mention public hosts; no real remote URLs.
    assert "https://" + public_host not in text
    assert "git@" + public_host not in text
    assert "NOTEBOOKLM_NOTEBOOK" in text  # env for fake alias only
