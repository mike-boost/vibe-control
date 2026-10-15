"""Status-aware knowledge query router (Phase 10). Readonly by default."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from vibe_control.config import load_config
from vibe_control.knowledge.ask_template import (
    SSOT_ASK_PERSONA,
    render_default_ask_prompt,
    repo_fallback_ask_metadata,
)
from vibe_control.knowledge.corpus import build_desired_corpus, resolve_desired_corpus
from vibe_control.knowledge.phase8_runtime import get_runtime
from vibe_control.knowledge.query_provenance import (
    append_inventory_hint,
    enrich_query_sources,
    looks_evidence_insufficient,
)
from vibe_control.knowledge.repo_provider import RepoProvider


def _load_receipt_for_provenance(
    runtime: Any,
    config: Any,
    *,
    notebook_alias: str | None,
    home: Path | None,
) -> dict[str, Any] | None:
    try:
        from vibe_control.knowledge.receipt_scope import load_or_migrate_receipt

        target, _ref = runtime.resolve_target(config, alias=notebook_alias)
        loaded = load_or_migrate_receipt(config.project_id, target, home=home)
        if loaded.ok and isinstance(loaded.data, dict):
            return loaded.data
    except Exception:
        return None
    return None


def _is_config_policy_question(question: str) -> bool:
    q = question.lower()
    return "config" in q and ("policy" in q or "require_commit_push" in q or "vibe-control.yaml" in q)


def route_knowledge_query(
    *,
    repo_root: Path,
    question: str,
    sync_state_override: str | None = None,
    provider: Any | None = None,
    ack_store: Any | None = None,
    home: Path | None = None,
    allow_config_policy: bool | None = None,
    notebook_alias: str | None = None,
) -> dict[str, Any]:
    config = load_config(repo_root)
    active = str(config.knowledge.get("provider") or "notebooklm").strip().lower()

    # local_fts: independent status/query path (do not use NLM evaluate_sync_status).
    if active == "local_fts" and provider is None:
        from vibe_control.knowledge.local_fts.provider import LocalFtsProvider

        rendered_prompt, ask_meta = render_default_ask_prompt(question)
        _ = rendered_prompt  # template still recorded in ask_meta for provenance
        local = LocalFtsProvider(home=home)
        raw = local.query(
            config,
            repo_root=repo_root,
            question=question,
            notebook_alias=notebook_alias,
        )
        sources = list(raw.get("sources") or [])
        next_actions = list(raw.get("next_actions") or [])
        if looks_evidence_insufficient(str(raw.get("answer") or ""), sources=sources) or not sources:
            next_actions = append_inventory_hint(next_actions)
        return {
            "ok": True,
            "mode": raw.get("mode") or "provider",
            "provider": "local_fts",
            "answer_mode": "evidence_retrieval",
            "project_id": config.project_id,
            "provider_target": None,
            "sync_state": raw.get("sync_state"),
            "synced": raw.get("sync_state") == "synced" and bool(raw.get("provider_ask_clean")),
            "answer": raw.get("answer") or "",
            "sources": sources,
            "warnings": list(raw.get("warnings") or []),
            "next_actions": next_actions,
            "config_as_policy": False,
            "config_synced_as_content": False,
            "ask_hygiene": raw.get("ask_hygiene") or {},
            "provider_ask_clean": bool(raw.get("provider_ask_clean")),
            "index": raw.get("index"),
            **ask_meta,
        }

    runtime = get_runtime(repo_root=repo_root, home=home)
    if ack_store is not None:
        runtime.ack_store = ack_store

    sync_state = sync_state_override
    ack_persistence = {"ack_store_kind": "none", "notebooklm_note_written": False}
    provider_target: dict[str, Any] | None = None
    status: dict[str, Any] = {}
    notebook_ref: str | None = None

    if sync_state is None:
        status = runtime.status(config, alias=notebook_alias)
        sync_state = str(status.get("sync_state") or "unavailable")
        ack_persistence = status.get("ack_persistence") or ack_persistence
        provider_target = status.get("target")
        try:
            _target, notebook_ref = runtime.resolve_target(config, alias=notebook_alias)
        except Exception:
            notebook_ref = None
    else:
        try:
            target, notebook_ref = runtime.resolve_target(config, alias=notebook_alias)
            provider_target = target.to_dict()
            info = getattr(runtime.ack_store, "persistence_info", None)
            if callable(info):
                ack_persistence = dict(info())
        except Exception:
            provider_target = None
            notebook_ref = None

    warnings: list[str] = []
    next_actions: list[str] = []
    config_as_policy = False
    if allow_config_policy is None:
        allow_config_policy = _is_config_policy_question(question)

    rendered_prompt, ask_meta = render_default_ask_prompt(question)

    # Readonly provider query only when synced
    if sync_state == "synced" and provider is None:
        from vibe_control.knowledge.notebooklm_provider import NotebookLMProvider

        provider = NotebookLMProvider()

    if sync_state == "synced" and provider is not None and hasattr(provider, "query"):
        try:
            query_kwargs: dict[str, Any] = {
                "persona": SSOT_ASK_PERSONA,
                "apply_ask_persona": True,
                "response_length": "shorter",
            }
            if notebook_ref:
                raw = provider.query(
                    rendered_prompt, notebook_ref=notebook_ref, **query_kwargs
                )
            else:
                raw = provider.query(rendered_prompt, **query_kwargs)
        except TypeError:
            # Test doubles / older providers may not accept persona kwargs.
            try:
                if notebook_ref:
                    raw = provider.query(rendered_prompt, notebook_ref=notebook_ref)
                else:
                    raw = provider.query(rendered_prompt)
            except TypeError:
                raw = provider.query(rendered_prompt)
        if raw.get("ok") is False:
            warnings.append(
                f"Provider query failed ({raw.get('code') or 'QUERY_FAILED'}); using repo fallback"
            )
            sync_state = "unavailable"
        else:
            try:
                # Prefer resolved target alias when status already bound a notebook.
                scoped_alias = notebook_alias
                if scoped_alias is None and isinstance(provider_target, dict):
                    scoped_alias = provider_target.get("notebook_alias")
                corpus_for_prov = resolve_desired_corpus(
                    config, notebook_alias=scoped_alias, repo_root=repo_root
                )
            except Exception:
                corpus_for_prov = None
                warnings.append(
                    "Desired corpus unavailable for citation enrichment; "
                    "sources may lack repo path/doc_id"
                )
            receipt_data = _load_receipt_for_provenance(
                runtime, config, notebook_alias=notebook_alias, home=home
            )
            sources = enrich_query_sources(
                list(raw.get("sources") or []),
                corpus=corpus_for_prov,
                receipt_data=receipt_data,
            )
            answer_text = str(raw.get("answer") or "")
            # Ask hygiene: synced alone is not enough if orphan leftovers remain.
            ask_hygiene: dict[str, Any] = {
                "provider_ask_clean": True,
                "condition": "clean",
                "rule": (
                    "provider_ask_clean requires sync_state=synced AND "
                    "required_updates_count=0 AND candidate_count=0"
                ),
            }
            try:
                from vibe_control.knowledge.ack_stores import LocalMirrorAckStore
                from vibe_control.knowledge.ask_hygiene import evaluate_ask_hygiene
                from vibe_control.knowledge.phase8_apply import plan_forward_sync_dry_run

                target_obj, ref = runtime.resolve_target(config, alias=notebook_alias)
                dry = plan_forward_sync_dry_run(
                    config,
                    repo_root=repo_root,
                    target=target_obj,
                    notebook_ref=ref,
                    provider=provider,
                    ack_store=LocalMirrorAckStore(config.project_id, home=home),
                    home=home,
                )
                orphan_ops = sum(
                    1 for o in (dry.get("operations") or []) if o.get("op") == "orphan_managed"
                )
                ask_hygiene = evaluate_ask_hygiene(
                    sync_state="synced",
                    required_updates_count=int(dry.get("required_updates_count") or 0),
                    candidate_count=orphan_ops,
                    orphan_managed_count=orphan_ops,
                )
                if not ask_hygiene.get("provider_ask_clean"):
                    warnings.append(
                        "Provider query returned an answer, but provider_ask_clean=false: "
                        "old non-current sources remain (ask pollution). "
                        "Run `vibe knowledge cleanup-candidates --json`."
                    )
                    next_actions.append("vibe knowledge cleanup-candidates --json")
            except Exception:
                # Hygiene probe must not break readonly query; leave clean unknown.
                ask_hygiene = {
                    "provider_ask_clean": False,
                    "condition": "hygiene_probe_failed",
                    "reasons": ["ask hygiene probe failed; do not claim provider ask clean"],
                }
                warnings.append("Ask hygiene probe failed; do not claim provider-backed ask is clean")

            if looks_evidence_insufficient(answer_text, sources=sources):
                next_actions = append_inventory_hint(next_actions)

            return {
                "ok": True,
                "mode": "available",
                "provider": "notebooklm",
                "project_id": config.project_id,
                "provider_target": provider_target,
                "sync_state": "synced",
                "synced": True,
                "ack_persistence": ack_persistence,
                "answer": answer_text,
                "sources": sources,
                "warnings": warnings,
                "next_actions": next_actions,
                "config_as_policy": False,
                "config_synced_as_content": False,
                "ask_hygiene": ask_hygiene,
                "provider_ask_clean": bool(ask_hygiene.get("provider_ask_clean")),
                **({"ask_persona": raw["ask_persona"]} if raw.get("ask_persona") else {}),
                **ask_meta,
            }

    if sync_state == "synced" and provider is None:
        # No injectable provider: fall back to repo with warning that provider query is unavailable in this context
        warnings.append("Provider query path unavailable in this runtime; using repo fallback")
        sync_state = "unavailable"

    if sync_state in {"pending", "drift", "target_mismatch"}:
        warnings.append(
            f"Knowledge sync_state={sync_state}; provider is not treated as current truth"
        )
        next_actions.append("vibe knowledge status --json")
        next_actions.append("vibe knowledge sync --apply --json")

    if sync_state == "unavailable":
        warnings.append("Provider unavailable or not current; answering in degraded repo fallback mode")

    scoped_alias = notebook_alias
    if scoped_alias is None and isinstance(provider_target, dict):
        scoped_alias = provider_target.get("notebook_alias")
    try:
        corpus = resolve_desired_corpus(
            config, notebook_alias=scoped_alias, repo_root=repo_root
        )
    except Exception:
        corpus = build_desired_corpus(config, repo_root=repo_root)
    repo = RepoProvider()
    # Keyword search uses raw question; ask policy metadata records equivalent local rules.
    repo_result = repo.query(question, config=config, repo_root=repo_root, corpus=corpus)
    data = repo_result.to_data()
    fallback_ask = repo_fallback_ask_metadata(question)
    fallback_actions = list(next_actions) if next_actions else list(repo_result.next_actions)

    if allow_config_policy and _is_config_policy_question(question):
        config_as_policy = True
        cfg_path = config.path
        excerpt = ""
        try:
            text = Path(cfg_path).read_text(encoding="utf-8")
            if "require_commit_push_for_ssot" in text:
                excerpt = "require_commit_push_for_ssot is configured under specs (policy evidence only)."
        except OSError:
            excerpt = "Config policy file could not be read."
        data["answer"] = (data.get("answer") or "") + ("\n" if data.get("answer") else "") + excerpt
        warnings.append("Config was read as policy evidence only; config is not sync content")

    mode = "degraded"
    if sync_state == "pending":
        mode = "pending"
    elif sync_state == "drift":
        mode = "drift"

    fallback_reason = data.get("fallback_reason") or f"sync_state={sync_state}"
    if sync_state in {"pending", "drift", "target_mismatch"}:
        fallback_reason = f"sync_state={sync_state}"

    answer_text = data.get("answer") or repo_result.answer
    sources = data.get("sources") or []
    if looks_evidence_insufficient(str(answer_text or ""), sources=sources) or not sources:
        # Repo fallback with no hits (or explicit insufficient) → check corpus selection.
        no_hit = any(
            isinstance(w, dict) and w.get("code") == "NO_EVIDENCE_FOUND"
            for w in (repo_result.warnings or [])
        )
        if no_hit or looks_evidence_insufficient(str(answer_text or ""), sources=sources):
            fallback_actions = append_inventory_hint(fallback_actions)

    return {
        "ok": True,
        "mode": mode,
        "provider": "repo",
        "project_id": config.project_id,
        "provider_target": provider_target,
        "sync_state": sync_state,
        "synced": False,
        "ack_persistence": ack_persistence,
        "answer": answer_text,
        "sources": sources,
        "warnings": list(warnings) + list(repo_result.warnings),
        "next_actions": fallback_actions,
        "config_as_policy": config_as_policy,
        "config_synced_as_content": False,
        "fallback_reason": fallback_reason,
        **fallback_ask,
    }
