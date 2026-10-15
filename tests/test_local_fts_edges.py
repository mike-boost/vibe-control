"""Edge-case coverage for local_fts chunking, fingerprint, and store internals."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from vibe_control.knowledge.corpus import CorpusDocument, DesiredCorpus
from vibe_control.knowledge.local_fts import fingerprint as fp_mod
from vibe_control.knowledge.local_fts.chunking import (
    WINDOW_LINES,
    WINDOW_OVERLAP,
    chunk_markdown_document,
)
from vibe_control.knowledge.local_fts.fingerprint import (
    CHUNKING_VERSION,
    index_desired_fingerprint,
    scope_key_for_fs,
)
from vibe_control.knowledge.local_fts.store import (
    LocalFtsHit,
    LocalFtsStore,
    _build_match_query,
    _escape_fts_term,
    _merge_adjacent,
    index_path,
    probe_sqlite_fts5,
    snapshot_from_corpus,
    tokenize_question,
)


def _doc(
    *,
    doc_id: str = "spec",
    path: str = "docs/spec.md",
    title: str = "Spec",
) -> CorpusDocument:
    return CorpusDocument(
        doc_id=doc_id,
        path=path,
        title=title,
        status="active",
        kind="spec",
        source_policy="managed",
        source_title=f"{title} ({doc_id})",
    )


def _corpus(repo_root: Path, *, docs: list[CorpusDocument] | None = None) -> DesiredCorpus:
    return DesiredCorpus(
        project_id="edge-test",
        documents=docs or [_doc()],
        source_count=1,
    )


def _rebuild(
    store: LocalFtsStore,
    repo_root: Path,
    corpus: DesiredCorpus,
    *,
    sync_scope: str = "ssot_files",
) -> dict:
    snapshot = snapshot_from_corpus(corpus, sync_scope=sync_scope, repo_root=repo_root)
    return store.rebuild(
        project_id=corpus.project_id,
        sync_scope=sync_scope,
        corpus=corpus,
        snapshot=snapshot,
        repo_root=repo_root,
    )


@pytest.fixture
def fts_ok():
    probe = probe_sqlite_fts5()
    if not probe.get("ok"):
        pytest.skip(probe.get("message") or "sqlite FTS5 unavailable")
    return probe


def test_empty_and_whitespace_files_produce_no_chunks():
    assert chunk_markdown_document(doc_id="d", path="p.md", title="t", text="") == []
    assert chunk_markdown_document(doc_id="d", path="p.md", title="t", text="   \n\n  \t\n") == []


def test_empty_file_rebuild_is_safe(tmp_path: Path, fts_ok):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "empty.md").write_text("   \n\n  \n", encoding="utf-8")
    corpus = _corpus(
        repo,
        docs=[_doc(doc_id="empty", path="empty.md", title="Empty")],
    )
    store = LocalFtsStore(tmp_path / "index.sqlite")
    result = _rebuild(store, repo, corpus)
    assert result["ok"] is True
    assert result["chunk_count"] == 0
    assert result["document_count"] == 1
    assert store.query("anything") == []


def test_scope_key_for_fs_replaces_colon():
    assert scope_key_for_fs("ssot_files:alias") == "ssot_files_alias"
    assert scope_key_for_fs("ssot_files/foo:bar") == "ssot_files_foo_bar"


def test_index_path_uses_scope_key(tmp_path: Path):
    path = index_path("proj", "ssot_files:alias", home=tmp_path)
    assert "ssot_files_alias" in str(path)
    assert ":" not in path.name


def test_fingerprint_changes_when_snapshot_hash_changes(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.md").write_text("# A\n\nalpha\n", encoding="utf-8")
    corpus = _corpus(repo, docs=[_doc(path="a.md")])
    snap1 = snapshot_from_corpus(corpus, sync_scope="ssot_files", repo_root=repo)
    fp1 = index_desired_fingerprint(snap1)

    (repo / "a.md").write_text("# A\n\nbeta changed\n", encoding="utf-8")
    snap2 = snapshot_from_corpus(corpus, sync_scope="ssot_files", repo_root=repo)
    fp2 = index_desired_fingerprint(snap2)

    assert snap1.snapshot_hash != snap2.snapshot_hash
    assert fp1 != fp2


def test_fingerprint_changes_when_chunking_version_changes(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.md").write_text("# A\n", encoding="utf-8")
    corpus = _corpus(repo, docs=[_doc(path="a.md")])
    snapshot = snapshot_from_corpus(corpus, sync_scope="ssot_files", repo_root=repo)
    baseline = index_desired_fingerprint(snapshot)

    with patch.object(fp_mod, "CHUNKING_VERSION", "heading_v2_test"):
        bumped = index_desired_fingerprint(snapshot)

    assert baseline != bumped
    assert CHUNKING_VERSION == "heading_v1"


def test_tokenize_question_cjk_two_char_and_english_special_chars():
    terms = tokenize_question("任务缓存 product_ready() git-push")
    assert "任务缓存" in terms
    assert "product_ready" in terms
    assert "git" in terms
    assert "push" in terms


def test_escape_fts_term_strips_special_chars():
    assert _escape_fts_term("product_ready()") == '"product_ready"'
    assert _escape_fts_term('"quoted"') == '"quoted"'
    assert _escape_fts_term("***") is None


def test_build_match_query_skips_short_terms():
    q = _build_match_query(["任务", "ab", "product"])
    assert q is not None
    assert '"product"' in q
    assert "任务" not in q


def test_query_special_chars_do_not_throw(tmp_path: Path, fts_ok):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "spec.md").write_text(
        "# Spec\n\n"
        "The product_ready flag gates autonomy.\n"
        "Also mentions quoted policy text.\n",
        encoding="utf-8",
    )
    corpus = _corpus(repo, docs=[_doc(path="spec.md")])
    store = LocalFtsStore(tmp_path / "index.sqlite")
    _rebuild(store, repo, corpus)

    hits_paren = store.query('product_ready()')
    assert hits_paren, "expected hit for product_ready() question"
    assert any("product_ready" in h.body for h in hits_paren)

    hits_quote = store.query('"quoted" policy')
    assert hits_quote, 'expected hit for "quoted" style question'


def test_like_fallback_for_two_char_cjk(tmp_path: Path, fts_ok):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "spec.md").write_text(
        "# Spec\n\n"
        "## 任务\n\n"
        "任务缓存必须为 true。\n",
        encoding="utf-8",
    )
    corpus = _corpus(repo, docs=[_doc(path="spec.md")])
    store = LocalFtsStore(tmp_path / "index.sqlite")
    _rebuild(store, repo, corpus)

    hits = store.query("任务")
    assert hits, "expected LIKE fallback for 2-char CJK term"
    assert any("任务" in h.matched_terms or "任务" in h.excerpt for h in hits)


def test_idempotent_rebuild_same_fingerprint(tmp_path: Path, fts_ok):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "docs").mkdir()
    (repo / "docs" / "spec.md").write_text("# Spec\n\nstable content\n", encoding="utf-8")
    corpus = _corpus(repo)
    store = LocalFtsStore(tmp_path / "index.sqlite")

    first = _rebuild(store, repo, corpus)
    second = _rebuild(store, repo, corpus)

    assert first["desired_fingerprint"] == second["desired_fingerprint"]
    meta = store.read_meta()
    assert meta.get("desired_fingerprint") == first["desired_fingerprint"]
    assert first["chunk_count"] == second["chunk_count"]


def test_window_split_produces_overlapping_chunks():
    body_lines = [f"content line {i}" for i in range(1, 130)]
    text = "# Big Section\n" + "\n".join(body_lines)
    chunks = chunk_markdown_document(doc_id="d", path="p.md", title="t", text=text)
    assert len(chunks) >= 2

    chunks = sorted(chunks, key=lambda c: c.line_start)
    first, second = chunks[0], chunks[1]
    assert second.line_start <= first.line_end, "windows should overlap"
    assert first.line_end - second.line_start + 1 >= WINDOW_OVERLAP

    span = first.line_end - first.line_start + 1
    assert span <= WINDOW_LINES


def test_long_section_emits_multiple_chunks_with_expected_stride():
    lines = ["# Section"] + [f"row {i}" for i in range(1, 200)]
    chunks = chunk_markdown_document(
        doc_id="d", path="p.md", title="t", text="\n".join(lines)
    )
    assert len(chunks) > 1
    ordered = sorted(chunks, key=lambda c: c.line_start)
    for prev, nxt in zip(ordered, ordered[1:]):
        assert nxt.line_start > prev.line_start
        assert nxt.line_start <= prev.line_end


def test_merge_adjacent_unit():
    base = dict(
        doc_id="d1",
        path="p.md",
        title="t",
        heading="h",
        excerpt="",
        matched_terms=[],
        body="",
    )
    a = LocalFtsHit(
        chunk_id="a",
        line_start=10,
        line_end=20,
        score=-1.0,
        **base,
    )
    b = LocalFtsHit(
        chunk_id="b",
        line_start=21,
        line_end=30,
        score=-2.0,
        **base,
    )
    merged = _merge_adjacent([b, a])
    assert len(merged) == 1
    assert merged[0].line_start == 10
    assert merged[0].line_end == 30


def test_query_merges_adjacent_window_hits(tmp_path: Path, fts_ok):
    repo = tmp_path / "repo"
    repo.mkdir()
    lines = ["# Long"]
    lines.append("findme anchor at top")
    lines.extend(f"filler {i}" for i in range(2, 85))
    lines.append("findme anchor deep")
    lines.extend(f"tail {i}" for i in range(86, 150))
    (repo / "long.md").write_text("\n".join(lines), encoding="utf-8")

    corpus = _corpus(repo, docs=[_doc(doc_id="long", path="long.md", title="Long")])
    store = LocalFtsStore(tmp_path / "index.sqlite")
    rebuild = _rebuild(store, repo, corpus)
    assert rebuild["chunk_count"] >= 2

    hits = store.query("findme")
    assert hits, "expected hits for findme"
    if len(hits) == 1:
        assert hits[0].line_end - hits[0].line_start > WINDOW_LINES // 2
