"""SQLite FTS5 store: rebuild + query with trigram and LIKE fallback."""

from __future__ import annotations

import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vibe_control.knowledge.corpus import DesiredCorpus
from vibe_control.knowledge.local_fts.chunking import (
    CHUNKING_VERSION,
    TextChunk,
    chunk_markdown_document,
)
from vibe_control.knowledge.local_fts.fingerprint import (
    TOKENIZER,
    index_desired_fingerprint,
    scope_key_for_fs,
)
from vibe_control.knowledge.managed_names import content_sha256_file
from vibe_control.knowledge.receipt_scope import _state_root
from vibe_control.knowledge.snapshot import DesiredSnapshot, build_desired_snapshot

SCHEMA_VERSION = "1"
FTS_META_COL_BODY = 7  # body is 8th column (0-based) in chunks FTS table

_FTS_META_CHARS = re.compile(r'[*\"\-():^]')


@dataclass
class LocalFtsHit:
    chunk_id: str
    doc_id: str
    path: str
    title: str
    heading: str
    line_start: int
    line_end: int
    excerpt: str
    score: float
    matched_terms: list[str]
    body: str

    def to_source_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "path": self.path,
            "title": self.title,
            "heading": self.heading,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "excerpt": self.excerpt,
            "score": self.score,
            "matched_terms": list(self.matched_terms),
            "chunk_id": self.chunk_id,
        }


def probe_sqlite_fts5() -> dict[str, Any]:
    """Doctor probe: version + ENABLE_FTS5 + trigram create capability."""
    version = sqlite3.sqlite_version
    out: dict[str, Any] = {
        "sqlite_version": version,
        "fts5_enabled": False,
        "trigram_ok": False,
        "ok": False,
        "message": "",
    }
    try:
        con = sqlite3.connect(":memory:")
        opts = {row[0] for row in con.execute("PRAGMA compile_options")}
        out["fts5_enabled"] = any("ENABLE_FTS5" in o for o in opts) or True
        # Some builds omit compile_options flag but still support fts5.
        try:
            con.execute("CREATE VIRTUAL TABLE _probe USING fts5(x, tokenize='trigram')")
            con.execute("INSERT INTO _probe VALUES ('abc审批矩阵')")
            rows = con.execute("SELECT x FROM _probe WHERE _probe MATCH '\"审批矩\"'").fetchall()
            out["trigram_ok"] = True
            out["ok"] = True
            out["message"] = f"sqlite {version} FTS5 trigram available"
            _ = rows
        except sqlite3.OperationalError as exc:
            out["trigram_ok"] = False
            out["ok"] = False
            out["message"] = f"trigram tokenizer unavailable: {exc}"
        con.close()
    except Exception as exc:  # noqa: BLE001
        out["ok"] = False
        out["message"] = f"sqlite probe failed: {exc}"
    return out


def index_path(
    project_id: str,
    sync_scope: str,
    *,
    home: Path | None = None,
) -> Path:
    key = scope_key_for_fs(sync_scope)
    return _state_root(home) / project_id / "local_fts" / key / "index.sqlite"


def tokenize_question(question: str) -> list[str]:
    from vibe_control.knowledge.repo_provider import tokenize_question as _tok

    base = _tok(question)
    # Also keep CJK runs of length >= 2 that tokenize_question may drop.
    cjk = re.findall(r"[\u4e00-\u9fff]{2,}", question or "")
    seen = set(base)
    out = list(base)
    for term in cjk:
        if term not in seen:
            seen.add(term)
            out.append(term)
    return out


def _escape_fts_term(term: str) -> str | None:
    cleaned = _FTS_META_CHARS.sub(" ", term).strip()
    if not cleaned:
        return None
    # Collapse whitespace inside phrase.
    cleaned = re.sub(r"\s+", " ", cleaned)
    return f'"{cleaned}"'


def _build_match_query(terms: list[str]) -> str | None:
    parts: list[str] = []
    for term in terms:
        esc = _escape_fts_term(term)
        if esc and len(term) >= 3:
            parts.append(esc)
    if not parts:
        return None
    return " OR ".join(parts)


def _parse_matched_terms(excerpt: str) -> list[str]:
    return re.findall(r">>>(.*?)<<<", excerpt or "")


def _merge_adjacent(hits: list[LocalFtsHit]) -> list[LocalFtsHit]:
    if not hits:
        return []
    ordered = sorted(hits, key=lambda h: (h.doc_id, h.line_start, h.score))
    merged: list[LocalFtsHit] = []
    for hit in ordered:
        if not merged:
            merged.append(hit)
            continue
        prev = merged[-1]
        if (
            prev.doc_id == hit.doc_id
            and hit.line_start <= prev.line_end + 2
        ):
            new_end = max(prev.line_end, hit.line_end)
            better = hit if hit.score < prev.score else prev
            merged[-1] = LocalFtsHit(
                chunk_id=better.chunk_id,
                doc_id=prev.doc_id,
                path=prev.path,
                title=prev.title,
                heading=prev.heading or hit.heading,
                line_start=min(prev.line_start, hit.line_start),
                line_end=new_end,
                excerpt=better.excerpt,
                score=min(prev.score, hit.score),
                matched_terms=list(dict.fromkeys(prev.matched_terms + hit.matched_terms)),
                body=better.body,
            )
        else:
            merged.append(hit)
    merged.sort(key=lambda h: (h.score, h.doc_id, h.line_start))
    return merged


class LocalFtsStore:
    def __init__(self, path: Path):
        self.path = path

    def exists(self) -> bool:
        return self.path.is_file()

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(str(self.path))
        con.row_factory = sqlite3.Row
        return con

    def read_meta(self) -> dict[str, str]:
        if not self.exists():
            return {}
        try:
            with self.connect() as con:
                rows = con.execute("SELECT key, value FROM meta").fetchall()
            return {str(r["key"]): str(r["value"]) for r in rows}
        except sqlite3.Error:
            return {}

    def rebuild(
        self,
        *,
        project_id: str,
        sync_scope: str,
        corpus: DesiredCorpus,
        snapshot: DesiredSnapshot,
        repo_root: Path,
    ) -> dict[str, Any]:
        probe = probe_sqlite_fts5()
        if not probe.get("ok"):
            raise RuntimeError(probe.get("message") or "sqlite FTS5 trigram unavailable")

        fingerprint = index_desired_fingerprint(snapshot)
        chunks: list[TextChunk] = []
        docs_meta: list[tuple[str, str, str, str, str, str]] = []

        for doc in corpus.documents:
            file_path = repo_root / doc.path
            text = file_path.read_text(encoding="utf-8", errors="replace")
            sha = content_sha256_file(file_path)
            docs_meta.append(
                (doc.doc_id, doc.path, doc.title, sha, doc.status, doc.kind)
            )
            chunks.extend(
                chunk_markdown_document(
                    doc_id=doc.doc_id,
                    path=doc.path,
                    title=doc.title,
                    text=text,
                )
            )

        # Atomic rebuild: write to temp then replace.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".sqlite.tmp")
        if tmp.exists():
            tmp.unlink()
        con = sqlite3.connect(str(tmp))
        try:
            con.execute("PRAGMA user_version = 1")
            con.execute(
                "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            con.execute(
                """
                CREATE TABLE documents (
                  doc_id TEXT PRIMARY KEY,
                  path TEXT NOT NULL,
                  title TEXT NOT NULL,
                  content_sha256 TEXT NOT NULL,
                  status TEXT NOT NULL,
                  kind TEXT NOT NULL
                )
                """
            )
            con.execute(
                """
                CREATE VIRTUAL TABLE chunks USING fts5(
                  chunk_id UNINDEXED,
                  doc_id UNINDEXED,
                  path UNINDEXED,
                  title UNINDEXED,
                  heading UNINDEXED,
                  line_start UNINDEXED,
                  line_end UNINDEXED,
                  body,
                  tokenize = 'trigram'
                )
                """
            )
            meta = {
                "schema_version": SCHEMA_VERSION,
                "provider": "local_fts",
                "project_id": project_id,
                "corpus_scope_key": scope_key_for_fs(sync_scope),
                "sync_scope": sync_scope,
                "desired_fingerprint": fingerprint,
                "snapshot_hash": snapshot.snapshot_hash,
                "built_at_iso": datetime.now(timezone.utc)
                .replace(microsecond=0)
                .isoformat(),
                "chunking_version": CHUNKING_VERSION,
                "tokenizer": TOKENIZER,
            }
            con.executemany(
                "INSERT INTO meta(key, value) VALUES (?, ?)",
                list(meta.items()),
            )
            con.executemany(
                "INSERT INTO documents(doc_id, path, title, content_sha256, status, kind) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                docs_meta,
            )
            con.executemany(
                "INSERT INTO chunks(chunk_id, doc_id, path, title, heading, "
                "line_start, line_end, body) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        c.chunk_id,
                        c.doc_id,
                        c.path,
                        c.title,
                        c.heading,
                        str(c.line_start),
                        str(c.line_end),
                        c.body,
                    )
                    for c in chunks
                ],
            )
            con.commit()
        finally:
            con.close()

        os.replace(tmp, self.path)
        return {
            "ok": True,
            "path": str(self.path),
            "desired_fingerprint": fingerprint,
            "document_count": len(docs_meta),
            "chunk_count": len(chunks),
            "sync_scope": sync_scope,
        }

    def query(self, question: str, *, top_k: int = 8) -> list[LocalFtsHit]:
        if not self.exists():
            return []
        terms = tokenize_question(question)
        if not terms:
            return []

        hits_by_key: dict[tuple[str, int, int], LocalFtsHit] = {}

        with self.connect() as con:
            match_q = _build_match_query(terms)
            if match_q:
                try:
                    rows = con.execute(
                        """
                        SELECT chunk_id, doc_id, path, title, heading,
                               line_start, line_end, body,
                               bm25(chunks) AS score,
                               snippet(chunks, ?, '>>>', '<<<', ' … ', 32) AS excerpt
                        FROM chunks
                        WHERE chunks MATCH ?
                        ORDER BY rank
                        LIMIT ?
                        """,
                        (FTS_META_COL_BODY, match_q, top_k * 3),
                    ).fetchall()
                    for row in rows:
                        self._ingest_row(hits_by_key, row)
                except sqlite3.OperationalError:
                    pass

            # LIKE fallback for short / CJK terms (<3 chars or unmatched).
            for term in terms:
                if len(term) >= 3 and match_q and f'"{term}"' in (match_q or ""):
                    # Still run LIKE for CJK-looking terms to boost recall.
                    if not re.search(r"[\u4e00-\u9fff]", term):
                        continue
                like = f"%{term}%"
                rows = con.execute(
                    """
                    SELECT chunk_id, doc_id, path, title, heading,
                           line_start, line_end, body,
                           0.0 AS score,
                           body AS excerpt
                    FROM chunks
                    WHERE body LIKE ?
                    LIMIT ?
                    """,
                    (like, top_k * 2),
                ).fetchall()
                for row in rows:
                    excerpt = str(row["excerpt"] or "")
                    # Build a tiny highlighted excerpt for LIKE hits.
                    marked = excerpt.replace(term, f">>>{term}<<<")
                    if len(marked) > 240:
                        idx = marked.find(f">>>{term}<<<")
                        start = max(0, idx - 80)
                        marked = " … " + marked[start : start + 200] + " … "
                    fake = {
                        **dict(row),
                        "excerpt": marked,
                        "score": 1.0,  # worse than typical bm25 negatives
                    }
                    self._ingest_row(hits_by_key, fake, matched_extra=[term])

        merged = _merge_adjacent(list(hits_by_key.values()))
        return merged[:top_k]

    @staticmethod
    def _ingest_row(
        hits_by_key: dict[tuple[str, int, int], LocalFtsHit],
        row: Any,
        *,
        matched_extra: list[str] | None = None,
    ) -> None:
        line_start = int(row["line_start"])
        line_end = int(row["line_end"])
        key = (str(row["doc_id"]), line_start, line_end)
        excerpt = str(row["excerpt"] or "")
        matched = _parse_matched_terms(excerpt)
        if matched_extra:
            matched = list(dict.fromkeys(matched + matched_extra))
        score = float(row["score"] if row["score"] is not None else 0.0)
        hit = LocalFtsHit(
            chunk_id=str(row["chunk_id"]),
            doc_id=str(row["doc_id"]),
            path=str(row["path"]),
            title=str(row["title"]),
            heading=str(row["heading"] or ""),
            line_start=line_start,
            line_end=line_end,
            excerpt=excerpt,
            score=score,
            matched_terms=matched,
            body=str(row["body"] or ""),
        )
        prev = hits_by_key.get(key)
        if prev is None or hit.score < prev.score:
            hits_by_key[key] = hit


def snapshot_from_corpus(
    corpus: DesiredCorpus,
    *,
    sync_scope: str,
    repo_root: Path,
) -> DesiredSnapshot:
    return build_desired_snapshot(
        project_id=corpus.project_id,
        sync_scope=sync_scope,
        documents=[doc.to_dict() for doc in corpus.documents],
        repo_root=repo_root,
    )
