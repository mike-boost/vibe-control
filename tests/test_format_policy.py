"""Tests for per-provider Knowledge file format policy."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import yaml

from vibe_control.config import load_config
from vibe_control.knowledge.corpus import CorpusDocument, DesiredCorpus
from vibe_control.knowledge.format_policy import (
    LOCAL_FTS_EXTENSIONS,
    NOTEBOOKLM_EXTENSIONS,
    apply_to_desired_corpus,
    filter_documents_for_provider,
    is_path_allowed,
    partition_paths,
    reject_reason,
)
from vibe_control.knowledge.local_fts.provider import LocalFtsProvider
from vibe_control.knowledge.managed_names import parse_managed_name, upload_filename
from vibe_control.knowledge.phase8_apply import plan_forward_sync_dry_run
from vibe_control.knowledge.provider_target import ProviderTarget


def test_local_fts_allows_markdown_rejects_pdf_and_images():
    assert is_path_allowed("local_fts", "docs/a.md") is True
    assert is_path_allowed("local_fts", "docs/a.markdown") is True
    assert is_path_allowed("local_fts", "docs/a.txt") is True
    assert is_path_allowed("local_fts", "docs/A.MD") is True  # case-insensitive
    assert is_path_allowed("local_fts", "docs/a.pdf") is False
    assert is_path_allowed("local_fts", "docs/a.png") is False
    assert is_path_allowed("local_fts", "docs/a.docx") is False
    assert is_path_allowed("local_fts", "docs/noext") is False
    assert ".md" in LOCAL_FTS_EXTENSIONS


def test_notebooklm_allows_gemini_ui_formats_rejects_unknown():
    assert is_path_allowed("notebooklm", "a.pdf") is True
    assert is_path_allowed("notebooklm", "a.docx") is True
    assert is_path_allowed("notebooklm", "a.csv") is True
    assert is_path_allowed("notebooklm", "a.pptx") is True
    assert is_path_allowed("notebooklm", "a.epub") is True
    assert is_path_allowed("notebooklm", "a.png") is True
    assert is_path_allowed("notebooklm", "a.mp3") is True
    assert is_path_allowed("notebooklm", "a.mp4") is True
    assert is_path_allowed("notebooklm", "a.md") is True
    assert is_path_allowed("notebooklm", "a.exe") is False
    assert is_path_allowed("notebooklm", "a.py") is False
    assert is_path_allowed("unknown_provider", "a.md") is False
    assert ".pdf" in NOTEBOOKLM_EXTENSIONS
    assert ".png" in NOTEBOOKLM_EXTENSIONS
    assert ".mp3" in NOTEBOOKLM_EXTENSIONS


def test_partition_and_filter_documents():
    part = partition_paths("local_fts", ["a.md", "b.pdf", "c.txt"])
    assert part["allowed_count"] == 2
    assert part["rejected_count"] == 1
    assert part["rejected"][0]["path"] == "b.pdf"
    assert "local_fts" in reject_reason("local_fts", "b.pdf")

    docs = [
        SimpleNamespace(doc_id="1", path="a.md"),
        SimpleNamespace(doc_id="2", path="x.pptx"),
    ]
    filtered = filter_documents_for_provider("local_fts", docs)
    assert [d.doc_id for d in filtered["documents"]] == ["1"]
    assert filtered["rejected_count"] == 1


def test_apply_to_desired_corpus_adds_warnings_and_keeps_original():
    original = DesiredCorpus(
        project_id="p",
        documents=[
            CorpusDocument("a", "a.md", "A", "active", "spec", "registry", "A"),
            CorpusDocument("b", "b.pdf", "B", "active", "spec", "registry", "B"),
        ],
        source_count=2,
    )
    narrowed, report = apply_to_desired_corpus("local_fts", original)
    assert narrowed.source_count == 1
    assert report["rejected_count"] == 1
    assert any("format_skipped" in w for w in narrowed.warnings)
    # input corpus not mutated
    assert original.source_count == 2
    assert len(original.documents) == 2


def test_upload_filename_keeps_real_extension_and_parses():
    for ext in (".pdf", ".docx", ".png", ".md"):
        name = upload_filename("vibe__p__d", "a" * 64, extension=ext)
        assert name.endswith(ext)
        assert "__h__" in name
        parsed = parse_managed_name(name)
        assert parsed is not None
        assert parsed["doc_id"] == "d"
        assert parsed["kind"] == "hashed_filename"


def _fmt_repo(tmp_path: Path, *, provider: str) -> tuple[Path, Path]:
    repo = tmp_path / f"repo-{provider}"
    home = tmp_path / f"home-{provider}"
    home.mkdir()
    (repo / "docs").mkdir(parents=True)
    (repo / ".config").mkdir()
    (repo / "docs" / "ok.md").write_text("# Ok\n\nhello matrix\n", encoding="utf-8")
    (repo / "docs" / "nope.pdf").write_bytes(b"%PDF-1.4 fake")
    (repo / "docs" / "also.exe").write_bytes(b"MZ")
    (repo / "docs" / "spec-registry.yml").write_text(
        yaml.safe_dump(
            [
                {"id": "ok", "status": "active", "path": "docs/ok.md", "title": "Ok"},
                {"id": "nope", "status": "active", "path": "docs/nope.pdf", "title": "Nope"},
                {"id": "exe", "status": "active", "path": "docs/also.exe", "title": "Exe"},
            ]
        ),
        encoding="utf-8",
    )
    (repo / ".config" / "vibe-control.yaml").write_text(
        yaml.safe_dump(
            {
                "project": {"id": f"fmt-{provider}", "name": f"fmt-{provider}"},
                "components": {"knowledge": {"enabled": True}, "task": {"enabled": False}},
                "knowledge": {
                    "provider": provider,
                    "fallback_provider": "repo",
                    "max_sources": 20,
                    "warn_sources": 15,
                    "authoritative_statuses": ["active"],
                    "include_from": "docs/spec-registry.yml",
                    "include_extra": [],
                    "exclude_globs": [],
                },
                "specs": {
                    "registry": "docs/spec-registry.yml",
                    "required_fields": ["id", "status", "path"],
                },
                "tasks": {"provider": "fake"},
            }
        ),
        encoding="utf-8",
    )
    return repo, home


def test_local_fts_sync_and_status_skip_unsupported(tmp_path: Path, monkeypatch):
    repo, home = _fmt_repo(tmp_path, provider="local_fts")
    monkeypatch.setenv("HOME", str(home))
    cfg = load_config(repo)

    dry = LocalFtsProvider(home=home).sync(cfg, repo_root=repo, apply=False)
    assert dry.get("ok") is True
    plan = dry.get("plan") or {}
    assert any(op.get("op") == "skip_unsupported_format" for op in plan.get("ops") or [])
    assert len(plan.get("format_skipped") or []) == 2  # pdf + exe

    out = LocalFtsProvider(home=home).sync(cfg, repo_root=repo, apply=True)
    assert out.get("ok") is True
    assert (out.get("format_policy") or {}).get("rejected_count") == 2
    assert len((out.get("plan") or {}).get("format_skipped") or []) == 2

    status = LocalFtsProvider(home=home).status(cfg, repo_root=repo)
    fp = status.get("format_policy") or {}
    assert fp.get("rejected_count") == 2
    paths = {r.get("path") for r in (fp.get("rejected") or [])}
    assert "docs/nope.pdf" in paths
    assert "docs/also.exe" in paths
    assert (status.get("index") or {}).get("document_count") == 1
    assert status.get("sync_state") == "synced"


def test_notebooklm_dry_run_skips_exe_keeps_pdf(tmp_path: Path, monkeypatch):
    repo, home = _fmt_repo(tmp_path, provider="notebooklm")
    monkeypatch.setenv("HOME", str(home))
    cfg = load_config(repo)
    target = ProviderTarget.from_ref(
        provider="notebooklm",
        notebook_alias="main",
        notebook_ref="nb-fmt-test",
    )

    class FakeProvider:
        def list_sources(self, *, notebook_ref: str):
            return {"ok": True, "sources": []}

    plan = plan_forward_sync_dry_run(
        cfg,
        repo_root=repo,
        target=target,
        notebook_ref="nb-fmt-test",
        provider=FakeProvider(),
        home=home,
    )
    assert plan.get("ok") is True
    ops = plan.get("operations") or []
    skips = [o for o in ops if o.get("op") == "skip_unsupported_format"]
    assert len(skips) == 1
    assert skips[0].get("path") == "docs/also.exe"
    # pdf is allowed for notebooklm — should be planned as add_missing, not skip
    assert not any(
        o.get("op") == "skip_unsupported_format" and o.get("path") == "docs/nope.pdf"
        for o in ops
    )
    adds = [o for o in ops if o.get("op") == "add_missing"]
    add_paths = {o.get("path") for o in adds}
    assert "docs/ok.md" in add_paths
    assert "docs/nope.pdf" in add_paths
    assert "docs/also.exe" not in add_paths
    # upload name keeps .pdf extension
    pdf_add = next(o for o in adds if o.get("path") == "docs/nope.pdf")
    assert str(pdf_add.get("upload_filename") or "").endswith(".pdf")
    fp = plan.get("format_policy") or {}
    assert fp.get("rejected_count") == 1
