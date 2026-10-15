"""Local FTS knowledge provider adapter (independent of NotebookLM status path)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from vibe_control.config import ControlConfig
from vibe_control.json_envelope import next_action
from vibe_control.knowledge.ask_hygiene import evaluate_ask_hygiene
from vibe_control.knowledge.corpus import resolve_corpus_for_target
from vibe_control.knowledge.format_policy import apply_to_desired_corpus
from vibe_control.knowledge.local_fts.fingerprint import index_desired_fingerprint
from vibe_control.knowledge.local_fts.store import (
    LocalFtsStore,
    index_path,
    probe_sqlite_fts5,
    snapshot_from_corpus,
)
from vibe_control.knowledge.local_fts.purge import orphan_report_for_status


class LocalFtsProvider:
    name = "local_fts"

    def __init__(self, *, home: Path | None = None):
        self.home = home

    def _top_k(self, config: ControlConfig) -> int:
        local = config.knowledge.get("local_fts") or {}
        try:
            value = int(local.get("top_k", 8))
        except (TypeError, ValueError):
            value = 8
        return max(1, min(20, value))

    def _corpus_for_index(
        self,
        config: ControlConfig,
        *,
        repo_root: Path,
        notebook_alias: str | None,
    ):
        corpus, sync_scope = resolve_corpus_for_target(
            config,
            notebook_alias=notebook_alias,
            repo_root=repo_root,
        )
        narrowed, format_report = apply_to_desired_corpus(self.name, corpus)
        return narrowed, sync_scope, format_report

    def sqlite_probe(self) -> dict[str, Any]:
        return probe_sqlite_fts5()

    def status(
        self,
        config: ControlConfig,
        *,
        repo_root: Path,
        notebook_alias: str | None = None,
    ) -> dict[str, Any]:
        probe = probe_sqlite_fts5()
        if not probe.get("ok"):
            hygiene = evaluate_ask_hygiene(
                sync_state="unavailable",
                required_updates_count=1,
                candidate_count=0,
                orphan_managed_count=0,
            )
            return {
                "provider": self.name,
                "sync_state": "unavailable",
                "synced": False,
                "required_updates_count": 1,
                "required_updates": [{"op": "rebuild_index", "reason": probe.get("message")}],
                "candidate_count": 0,
                "orphan_managed_count": 0,
                "ask_hygiene": hygiene,
                "provider_ask_clean": False,
                "sqlite": probe,
                "target_ok": True,
                "available": False,
                "next_actions": [
                    next_action(
                        code="LOCAL_FTS_UNAVAILABLE",
                        command="vibe knowledge doctor --json",
                        mutation=False,
                        reason=str(probe.get("message") or "sqlite FTS5 unavailable"),
                    )
                ],
            }

        corpus, sync_scope, format_report = self._corpus_for_index(
            config, repo_root=repo_root, notebook_alias=notebook_alias
        )
        snapshot = snapshot_from_corpus(corpus, sync_scope=sync_scope, repo_root=repo_root)
        desired_fp = index_desired_fingerprint(snapshot)
        path = index_path(config.project_id, sync_scope, home=self.home)
        store = LocalFtsStore(path)
        meta = store.read_meta() if store.exists() else {}

        if not store.exists() or not meta:
            sync_state = "drift"
            required = 1
        elif (
            meta.get("schema_version") != "1"
            or meta.get("chunking_version") != "heading_v1"
            or meta.get("tokenizer") != "trigram"
        ):
            sync_state = "drift"
            required = 1
        elif meta.get("desired_fingerprint") != desired_fp:
            sync_state = "drift"
            required = 1
        else:
            # Verify document count matches.
            try:
                with store.connect() as con:
                    doc_count = int(con.execute("SELECT COUNT(*) AS c FROM documents").fetchone()["c"])
                    chunk_count = int(con.execute("SELECT COUNT(*) AS c FROM chunks").fetchone()["c"])
            except Exception:
                sync_state = "unavailable"
                required = 1
                doc_count = 0
                chunk_count = 0
            else:
                if doc_count != len(corpus.documents):
                    sync_state = "drift"
                    required = 1
                else:
                    sync_state = "synced"
                    required = 0
                meta = {**meta, "document_count": str(doc_count), "chunk_count": str(chunk_count)}

        hygiene = evaluate_ask_hygiene(
            sync_state=sync_state,
            required_updates_count=required,
            candidate_count=0,
            orphan_managed_count=0,
        )
        next_actions = []
        if sync_state != "synced":
            next_actions.append(
                next_action(
                    code="LOCAL_FTS_REBUILD_REQUIRED",
                    command="vibe knowledge sync --apply --json",
                    mutation=True,
                    reason="local_fts index missing or drifted; rebuild required",
                )
            )

        garbage = orphan_report_for_status(
            config, repo_root=repo_root, home=self.home
        )
        for action in garbage.get("next_actions") or []:
            next_actions.append(action)

        return {
            "provider": self.name,
            "sync_state": sync_state,
            "synced": sync_state == "synced",
            "required_updates_count": required,
            "required_updates": (
                [{"op": "rebuild_index", "reason": "fingerprint_or_missing"}]
                if required
                else []
            ),
            "candidate_count": 0,
            "orphan_managed_count": 0,
            "ask_hygiene": hygiene,
            "provider_ask_clean": bool(hygiene.get("provider_ask_clean")),
            "sqlite": probe,
            "target_ok": True,
            "available": sync_state != "unavailable",
            "index": {
                "exists": store.exists(),
                "path": str(path),
                "index_bytes": path.stat().st_size if store.exists() else 0,
                "desired_fingerprint": desired_fp,
                "index_fingerprint": meta.get("desired_fingerprint"),
                "snapshot_hash": snapshot.snapshot_hash,
                "sync_scope": sync_scope,
                "document_count": int(meta.get("document_count") or len(corpus.documents)),
                "chunk_count": int(meta.get("chunk_count") or 0),
                "chunking_version": meta.get("chunking_version"),
                "tokenizer": meta.get("tokenizer"),
            },
            "corpus_warnings": list(corpus.warnings),
            "format_policy": {
                "rejected_count": format_report.get("rejected_count") or 0,
                "rejected": list(format_report.get("rejected") or []),
                "allowed_extensions": list(format_report.get("allowed_extensions") or []),
            },
            "fts_garbage": {
                k: v for k, v in garbage.items() if k != "next_actions"
            },
            "next_actions": next_actions,
        }

    def sync(
        self,
        config: ControlConfig,
        *,
        repo_root: Path,
        apply: bool,
        notebook_alias: str | None = None,
    ) -> dict[str, Any]:
        status = self.status(config, repo_root=repo_root, notebook_alias=notebook_alias)
        if status.get("sync_state") == "unavailable" and not (
            status.get("sqlite") or {}
        ).get("ok"):
            return {
                "ok": False,
                "mutation": False,
                "dry_run": not apply,
                "provider": self.name,
                "sync_state": "unavailable",
                "message": (status.get("sqlite") or {}).get("message"),
                "next_actions": status.get("next_actions") or [],
            }

        corpus, sync_scope, format_report = self._corpus_for_index(
            config, repo_root=repo_root, notebook_alias=notebook_alias
        )
        snapshot = snapshot_from_corpus(corpus, sync_scope=sync_scope, repo_root=repo_root)
        path = index_path(config.project_id, sync_scope, home=self.home)
        plan = {
            "ops": [{"op": "rebuild_index", "sync_scope": sync_scope, "path": str(path)}],
            "document_count": len(corpus.documents),
            "desired_fingerprint": index_desired_fingerprint(snapshot),
            "format_skipped": list(format_report.get("rejected") or []),
        }
        if format_report.get("rejected"):
            for row in format_report["rejected"]:
                plan["ops"].append(
                    {
                        "op": "skip_unsupported_format",
                        "path": row["path"],
                        "reason": row["reason"],
                    }
                )
        if not apply:
            return {
                "ok": True,
                "mutation": False,
                "dry_run": True,
                "provider": self.name,
                "sync_state": status.get("sync_state"),
                "provider_ask_clean": False,
                "plan": plan,
                "format_policy": {
                    "rejected_count": format_report.get("rejected_count") or 0,
                    "allowed_extensions": list(
                        format_report.get("allowed_extensions") or []
                    ),
                },
                "status": status,
                "next_actions": [
                    next_action(
                        code="LOCAL_FTS_REBUILD_APPLY",
                        command="vibe knowledge sync --apply --json",
                        mutation=True,
                        reason="Review rebuild plan then apply",
                    )
                ],
            }

        store = LocalFtsStore(path)
        result = store.rebuild(
            project_id=config.project_id,
            sync_scope=sync_scope,
            corpus=corpus,
            snapshot=snapshot,
            repo_root=repo_root,
        )
        after = self.status(config, repo_root=repo_root, notebook_alias=notebook_alias)
        return {
            "ok": True,
            "mutation": True,
            "dry_run": False,
            "provider": self.name,
            "rebuild": result,
            "plan": plan,
            "format_policy": {
                "rejected_count": format_report.get("rejected_count") or 0,
                "rejected": list(format_report.get("rejected") or []),
                "allowed_extensions": list(format_report.get("allowed_extensions") or []),
            },
            "sync_state": after.get("sync_state"),
            "provider_ask_clean": after.get("provider_ask_clean"),
            "ask_hygiene": after.get("ask_hygiene"),
            "status": after,
            "next_actions": [],
        }

    def query(
        self,
        config: ControlConfig,
        *,
        repo_root: Path,
        question: str,
        notebook_alias: str | None = None,
    ) -> dict[str, Any]:
        status = self.status(config, repo_root=repo_root, notebook_alias=notebook_alias)
        if not status.get("provider_ask_clean"):
            return {
                "provider": self.name,
                "answer_mode": "evidence_retrieval",
                "mode": "degraded",
                "question": question,
                "answer": (
                    "local_fts index is not ask-clean. Rebuild required before evidence query."
                ),
                "sources": [],
                "provider_ask_clean": False,
                "sync_state": status.get("sync_state"),
                "ask_hygiene": status.get("ask_hygiene"),
                "index": status.get("index"),
                "next_actions": status.get("next_actions") or [],
            }

        corpus, sync_scope = resolve_corpus_for_target(
            config,
            notebook_alias=notebook_alias,
            repo_root=repo_root,
        )
        path = index_path(config.project_id, sync_scope, home=self.home)
        store = LocalFtsStore(path)
        hits = store.query(question, top_k=self._top_k(config))
        sources = [h.to_source_dict() for h in hits]
        if not sources:
            answer = (
                "No evidence chunks matched. Agent should treat as Evidence insufficient "
                "and consider vibe knowledge inventory --json."
            )
            next_actions = [
                next_action(
                    code="CHECK_CORPUS_INVENTORY",
                    command="vibe knowledge inventory --json",
                    mutation=False,
                    reason="No local_fts hits for question",
                )
            ]
        else:
            answer = (
                f"Found {len(sources)} evidence chunk(s). "
                "Agent must read cited line ranges and fill Facts/Constraints/MUST/Uncertainty. "
                "Vibe did not synthesize policy."
            )
            next_actions = []
        return {
            "provider": self.name,
            "answer_mode": "evidence_retrieval",
            "mode": "provider",
            "question": question,
            "answer": answer,
            "sources": sources,
            "provider_ask_clean": True,
            "sync_state": "synced",
            "ask_hygiene": status.get("ask_hygiene"),
            "index": status.get("index"),
            "corpus_document_count": len(corpus.documents),
            "next_actions": next_actions,
        }
