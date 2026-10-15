"""Phase 8 production runtime: status / target resolve / fake hooks for tests."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vibe_control.config import ControlConfig, load_config
from vibe_control.knowledge.corpus import build_desired_corpus, resolve_corpus_for_target
from vibe_control.knowledge.notebooks import require_notebook_ref
from vibe_control.knowledge.provider_target import ProviderTarget
from vibe_control.knowledge.remote_ack import AckStore, FakeAckStore, read_ack
from vibe_control.knowledge.snapshot import build_desired_snapshot
from vibe_control.knowledge.sync_status import evaluate_sync_status


class _UnavailableProvider:
    def list_sources(self, *, notebook_ref: str) -> dict[str, Any]:
        raise RuntimeError("NOTEBOOKLM_UNAVAILABLE")

    def status(self) -> dict[str, Any]:
        return {"available": False, "code": "NOTEBOOKLM_UNAVAILABLE"}


class _ReadonlyEmptyProvider:
    def __init__(self, counters: dict[str, int] | None = None):
        self.counters = counters if counters is not None else {"add": 0, "delete": 0}

    def list_sources(self, *, notebook_ref: str) -> dict[str, Any]:
        return {"ok": True, "sources": []}

    def add_file_source(self, *, notebook_ref: str, file_path: str, title: str) -> dict[str, Any]:
        self.counters["add"] = self.counters.get("add", 0) + 1
        raise RuntimeError("readonly provider refuses add")

    def delete_source(self, *, notebook_ref: str, source_id: str) -> dict[str, Any]:
        self.counters["delete"] = self.counters.get("delete", 0) + 1
        raise RuntimeError("readonly provider refuses delete")

    def status(self) -> dict[str, Any]:
        return {"available": True}


@dataclass
class Phase8Runtime:
    repo_root: Path
    home: Path | None = None
    ack_store: AckStore = field(default_factory=FakeAckStore)
    provider: Any = field(default_factory=_ReadonlyEmptyProvider)
    mutation_counters: dict[str, int] = field(default_factory=lambda: {"add": 0, "delete": 0, "write_ack": 0})
    notebook_ref: str | None = None
    notebook_alias: str | None = None

    @classmethod
    def for_tests(
        cls,
        *,
        repo_root: Path,
        home: Path | None = None,
        ack_store: AckStore | None = None,
        provider_mode: str = "readonly",
        mutation_counters: dict[str, int] | None = None,
    ) -> Phase8Runtime:
        counters = mutation_counters if mutation_counters is not None else {"add": 0, "delete": 0, "write_ack": 0}
        if provider_mode == "unavailable":
            provider: Any = _UnavailableProvider()
        else:
            provider = _ReadonlyEmptyProvider(counters)
        return cls(
            repo_root=repo_root,
            home=home,
            ack_store=ack_store or FakeAckStore(),
            provider=provider,
            mutation_counters=counters,
        )

    def resolve_target(self, config: ControlConfig, alias: str | None = None) -> tuple[ProviderTarget, str]:
        from vibe_control.knowledge.notebooks import allow_list_aliases

        try:
            aliases = allow_list_aliases(config)
        except Exception:
            aliases = []

        if self.notebook_ref and self.notebook_alias:
            if alias is not None and alias == self.notebook_alias:
                return (
                    ProviderTarget.from_ref(
                        provider="notebooklm",
                        notebook_alias=self.notebook_alias,
                        notebook_ref=self.notebook_ref,
                    ),
                    self.notebook_ref,
                )
            if alias is None and len(aliases) <= 1:
                return (
                    ProviderTarget.from_ref(
                        provider="notebooklm",
                        notebook_alias=self.notebook_alias,
                        notebook_ref=self.notebook_ref,
                    ),
                    self.notebook_ref,
                )
        entry, ref = require_notebook_ref(
            config,
            repo_root=self.repo_root,
            alias=alias,
            require_explicit_when_multi=True,
        )
        target = ProviderTarget.from_ref(
            provider="notebooklm",
            notebook_alias=entry.alias,
            notebook_ref=ref,
        )
        return target, ref

    def build_snapshot(self, config: ControlConfig, *, notebook_alias: str | None = None):
        alias = notebook_alias or self.notebook_alias
        corpus, sync_scope = resolve_corpus_for_target(
            config,
            notebook_alias=alias,
            repo_root=self.repo_root,
        )
        return build_desired_snapshot(
            project_id=config.project_id,
            sync_scope=sync_scope,
            documents=[{"doc_id": d.doc_id, "path": d.path} for d in corpus.documents],
            repo_root=self.repo_root,
        )

    def status(self, config: ControlConfig, *, alias: str | None = None) -> dict[str, Any]:
        try:
            target, ref = self.resolve_target(config, alias=alias)
        except Exception as exc:
            code = getattr(exc, "code", None) or "TARGET_UNRESOLVED"
            return {
                "sync_state": "unavailable",
                "synced": False,
                "code": code,
                "reasons": [str(exc)],
                "details": getattr(exc, "details", None) or {},
            }
        desired = self.build_snapshot(config, notebook_alias=target.notebook_alias)
        ack = read_ack(self.ack_store, target)
        status = evaluate_sync_status(
            project_id=config.project_id,
            target=target,
            desired=desired,
            remote_ack=ack,
            provider=self.provider,
            notebook_ref=ref,
            home=self.home,
        )
        info = getattr(self.ack_store, "persistence_info", None)
        status["ack_persistence"] = (
            dict(info())
            if callable(info)
            else {
                "ack_store_kind": getattr(self.ack_store, "ack_store_kind", "unknown"),
                "notebooklm_note_written": False,
                "notebooklm_note_available": False,
            }
        )
        return status


_RUNTIME: Phase8Runtime | None = None


def get_runtime(*, repo_root: Path, home: Path | None = None) -> Phase8Runtime:
    global _RUNTIME
    if _RUNTIME is not None:
        return _RUNTIME
    mode = os.environ.get("VIBE_PHASE8_FAKE_PROVIDER", "").strip().lower()
    if mode in {"unavailable", "readonly"}:
        return Phase8Runtime.for_tests(repo_root=repo_root, home=home, provider_mode=mode)

    # Production: readonly list_sources probe via NotebookLM adapter; no mutations.
    from vibe_control.config import load_config
    from vibe_control.knowledge.ack_stores import LocalMirrorAckStore
    from vibe_control.knowledge.notebooklm_provider import NotebookLMProvider
    from vibe_control.knowledge.notebooks import require_notebook_ref

    provider = NotebookLMProvider()
    project_id = "unknown"
    try:
        cfg = load_config(repo_root)
        project_id = cfg.project_id
        entry, ref = require_notebook_ref(
            cfg, repo_root=repo_root, alias=None, require_explicit_when_multi=False
        )
        runtime = Phase8Runtime(
            repo_root=repo_root,
            home=home,
            ack_store=LocalMirrorAckStore(project_id, home=home),
            provider=provider,
            notebook_ref=ref,
            notebook_alias=entry.alias,
        )
        return runtime
    except Exception:
        return Phase8Runtime(
            repo_root=repo_root,
            home=home,
            ack_store=LocalMirrorAckStore(project_id, home=home),
            provider=provider,
        )


def reset_runtime() -> None:
    global _RUNTIME
    _RUNTIME = None
