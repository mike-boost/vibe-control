"""Readonly NotebookLM probe adapter: list_sources metadata only."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from vibe_control.knowledge.corpus import build_desired_corpus
from vibe_control.config import ControlConfig, load_config
from vibe_control.knowledge.provider_target import ProviderTarget
from vibe_control.knowledge.receipt_scope import load_or_migrate_receipt, scoped_receipt_path
from vibe_control.knowledge.snapshot import build_desired_snapshot
from vibe_control.knowledge.sync_status import evaluate_sync_status


class ListOnlyProvider(Protocol):
    def list_sources(self, *, notebook_ref: str) -> dict[str, Any]: ...


class NotebookLMReadonlyProbe:
    """Probe using provider list_sources only; never get_source body."""

    def __init__(self, provider: ListOnlyProvider):
        self.provider = provider

    def probe(
        self,
        *,
        notebook_ref: str,
        target: ProviderTarget,
        project_id: str,
        repo_root: Path,
        home: Path | None = None,
        remote_ack: dict[str, Any] | None = None,
        config: ControlConfig | None = None,
    ) -> dict[str, Any]:
        cfg = config or load_config(repo_root)
        corpus = build_desired_corpus(cfg, repo_root=repo_root)
        desired = build_desired_snapshot(
            project_id=project_id,
            sync_scope="ssot_files",
            documents=[{"doc_id": d.doc_id, "path": d.path} for d in corpus.documents],
            repo_root=repo_root,
        )
        # Readonly contract: always touch list_sources metadata, never get_source body.
        listed = self.provider.list_sources(notebook_ref=notebook_ref)
        _ = listed
        # Ensure receipt path exists for evaluate path semantics; do not mutate provider.
        _ = scoped_receipt_path(project_id, target, home=home)
        _ = load_or_migrate_receipt(project_id, target, home=home)
        status = evaluate_sync_status(
            project_id=project_id,
            target=target,
            desired=desired,
            remote_ack=remote_ack,
            provider=self.provider,
            notebook_ref=notebook_ref,
            home=home,
        )
        status["readonly"] = True
        status["ok"] = status.get("sync_state") == "synced"
        status["listed_ok"] = bool(listed.get("ok", True))
        return status
