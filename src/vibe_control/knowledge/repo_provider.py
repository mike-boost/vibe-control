"""Repo fallback knowledge provider — degraded local search only."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vibe_control.config import ControlConfig
from vibe_control.knowledge.corpus import CorpusDocument, DesiredCorpus, build_desired_corpus

STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "how",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "was",
        "what",
        "when",
        "where",
        "which",
        "who",
        "with",
    }
)

TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


@dataclass
class RepoProviderStatus:
    available: bool
    mode: str = "degraded_fallback"
    message: str = "Repo fallback provider is available for local file reads"

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "mode": self.mode,
            "message": self.message,
        }


@dataclass
class QuerySourceHit:
    doc_id: str
    path: str
    title: str
    status: str
    kind: str
    score: int
    matched_terms: list[str]
    excerpt: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "path": self.path,
            "title": self.title,
            "status": self.status,
            "kind": self.kind,
            "score": self.score,
            "matched_terms": list(self.matched_terms),
            "excerpt": self.excerpt,
        }


@dataclass
class RepoQueryResult:
    question: str
    answer: str
    sources: list[QuerySourceHit] = field(default_factory=list)
    warnings: list[Any] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)
    fallback_reason: str = "notebooklm_not_used_in_phase_2"

    def to_data(self) -> dict[str, Any]:
        return {
            "provider": "repo",
            "fallback_reason": self.fallback_reason,
            "question": self.question,
            "answer": self.answer,
            "sources": [s.to_dict() for s in self.sources],
        }


class RepoProvider:
    """Local filesystem fallback when NotebookLM is unavailable / unused."""

    name = "repo"

    def status(self, repo_root: Path | None = None) -> RepoProviderStatus:
        root = repo_root or Path.cwd()
        return RepoProviderStatus(
            available=root.is_dir(),
            message="Repo fallback provider ready for degraded query path",
        )

    def query(
        self,
        question: str,
        *,
        config: ControlConfig,
        repo_root: Path,
        corpus: DesiredCorpus | None = None,
        top_k: int = 5,
    ) -> RepoQueryResult:
        warnings: list[Any] = [
            "NotebookLM was not used. Result is based on repo fallback search."
        ]
        desired = corpus or build_desired_corpus(config, repo_root=repo_root)
        warnings.extend(desired.warnings)

        terms = tokenize_question(question)
        hits: list[QuerySourceHit] = []

        for doc in desired.documents:
            file_path = repo_root / doc.path
            if not file_path.is_file():
                # Already warned during corpus build for missing files.
                continue
            try:
                text = file_path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                warnings.append(f"unreadable file: {doc.path} ({exc})")
                continue

            hit = score_document(doc, text=text, terms=terms, question=question)
            if hit is not None:
                hits.append(hit)

        hits.sort(key=lambda item: (-item.score, item.doc_id))
        top = hits[:top_k]

        if not top:
            warnings.append(
                {
                    "code": "NO_EVIDENCE_FOUND",
                    "message": (
                        "Repo fallback search found no matching evidence "
                        "in the desired corpus."
                    ),
                }
            )
            return RepoQueryResult(
                question=question,
                answer="",
                sources=[],
                warnings=warnings,
                next_actions=[
                    "Verify the question terms or use NotebookLM after provider sync is implemented."
                ],
            )

        answer = (
            f"Repo fallback found evidence in {len(top)} source(s). "
            "This is a degraded local search result, not a NotebookLM semantic answer."
        )
        return RepoQueryResult(
            question=question,
            answer=answer,
            sources=top,
            warnings=warnings,
            next_actions=[],
        )


def tokenize_question(question: str) -> list[str]:
    tokens = [t.lower() for t in TOKEN_RE.findall(question)]
    return [t for t in tokens if len(t) > 2 and t not in STOP_WORDS]


def score_document(
    doc: CorpusDocument,
    *,
    text: str,
    terms: list[str],
    question: str,
) -> QuerySourceHit | None:
    if not terms and not question.strip():
        return None

    haystacks = {
        "title": doc.title.lower(),
        "path": doc.path.lower(),
        "doc_id": doc.doc_id.lower(),
        "content": text.lower(),
    }
    weights = {"title": 5, "path": 3, "doc_id": 3, "content": 1}

    score = 0
    matched: list[str] = []
    first_content_index: int | None = None

    phrase = " ".join(terms)
    if phrase and phrase in haystacks["content"]:
        score += 4
        matched.append(phrase)
        first_content_index = haystacks["content"].find(phrase)

    for term in terms:
        term_matched = False
        for field_name, hay in haystacks.items():
            count = hay.count(term)
            if count:
                score += weights[field_name] * count
                term_matched = True
                if field_name == "content" and first_content_index is None:
                    first_content_index = hay.find(term)
        if term_matched and term not in matched:
            matched.append(term)

    if score <= 0:
        return None

    excerpt = _excerpt(text, first_content_index)
    return QuerySourceHit(
        doc_id=doc.doc_id,
        path=doc.path,
        title=doc.title,
        status=doc.status,
        kind=doc.kind,
        score=score,
        matched_terms=matched,
        excerpt=excerpt,
    )


def _excerpt(text: str, index: int | None, radius: int = 80) -> str:
    compact = " ".join(text.split())
    if not compact:
        return ""
    if index is None:
        return compact[: radius * 2]
    # Map approximate index from lowercased original; fall back to start.
    start = max(0, index - radius)
    end = min(len(text), index + radius)
    snippet = text[start:end]
    snippet = " ".join(snippet.split())
    if start > 0:
        snippet = "…" + snippet
    if end < len(text):
        snippet = snippet + "…"
    return snippet
