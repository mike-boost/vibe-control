"""Provider-backed product readiness and probe evidence (Phase 8.1).

Vibe Control is provider-backed for core product workflows:
- Active knowledge.provider (local_fts or notebooklm) unavailable / drift / unclean ask
  → not product_ready (when knowledge capability enabled)
- Beads unavailable → not product_ready (when task capability enabled)
- repo fallback may be degraded read, never full product readiness
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vibe_control.json_envelope import next_action
from vibe_control.knowledge.ask_hygiene import evaluate_ask_hygiene


@dataclass
class ProviderProbeResult:
    """Reusable evidence object within a single command run (not cross-run cache)."""

    knowledge_available: bool = False
    knowledge_target_ok: bool = False
    sync_state: str = "unavailable"
    ask_hygiene: dict[str, Any] = field(default_factory=dict)
    provider_ask_clean: bool = False
    task_available: bool = False
    task_mode: str = "unavailable"
    task_readable: bool = False
    ready_queue_available: bool | None = None
    task_cache: dict[str, Any] = field(default_factory=dict)
    task_cache_current: bool = True
    config_ok: bool = True
    components: dict[str, Any] = field(default_factory=dict)
    product_ready: bool = False
    blocked_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    evidence_hash: str = ""
    probed: bool = False
    # Hetu (optional capability; ignored when disabled)
    hetu_enabled: bool = False
    hetu_available: bool = False
    hetu_ready: bool = False
    hetu_index_state: str | None = None
    hetu_provider: str | None = None
    hetu_index_commit: str | None = None
    hetu_observed_head: str | None = None
    hetu_block_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "knowledge_provider": {
                "available": self.knowledge_available,
                "target_ok": self.knowledge_target_ok,
                "sync_state": self.sync_state,
                "ask_hygiene": {
                    "condition": (self.ask_hygiene or {}).get("condition"),
                    **{
                        k: v
                        for k, v in (self.ask_hygiene or {}).items()
                        if k != "condition"
                    },
                },
                "provider_ask_clean": self.provider_ask_clean,
            },
            "task_provider": {
                "available": self.task_available,
                "mode": self.task_mode,
                "readable": self.task_readable,
                "ready_queue_available": self.ready_queue_available,
            },
            "hetu": {
                "enabled": self.hetu_enabled,
                "available": self.hetu_available,
                "ready": self.hetu_ready if self.hetu_enabled else None,
                "index_state": self.hetu_index_state,
                "provider": self.hetu_provider,
                "index_commit": self.hetu_index_commit,
                "observed_head": self.hetu_observed_head,
            },
            "task_cache": dict(self.task_cache or {}),
            "task_cache_current": self.task_cache_current,
            "config_ok": self.config_ok,
            "components": dict(self.components or {}),
            "capability_profile": {
                "version": "vibe.capability_profile.v1",
                "default_disabled": True,
                "engine_readiness_separate": True,
                "knowledge_enabled": bool(
                    ((self.components or {}).get("knowledge") or {}).get("enabled")
                ),
                "task_enabled": bool(
                    ((self.components or {}).get("task") or {}).get("enabled")
                ),
                "hetu_enabled": bool(
                    ((self.components or {}).get("hetu") or {}).get("enabled")
                ),
            },
            "product_ready": self.product_ready,
            "blocked_reasons": list(self.blocked_reasons),
            "evidence_hash": self.evidence_hash,
            "probed": self.probed,
        }


def hetu_blocked_reason_for_state(
    *,
    index_state: str | None,
    block_detail: str | None = None,
) -> str | None:
    """Map Hetu index_state (+ optional detail) to a product_ready blocked reason."""
    if index_state is None or index_state == "ready":
        return None
    detail = str(block_detail or "")
    if index_state == "unavailable":
        if detail in {"provider_incompatible", "hetu_provider_incompatible"}:
            return "hetu_provider_incompatible"
        return "hetu_provider_unavailable"
    mapping = {
        "missing": "hetu_index_missing",
        "indexing": "hetu_index_indexing",
        "stale": "hetu_index_stale",
        "unverifiable": "hetu_index_unverifiable",
        "conflict_needs_choice": "hetu_binding_conflict",
    }
    return mapping.get(index_state, "hetu_index_unverifiable")


def _evidence_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def finalize_product_ready(probe: ProviderProbeResult) -> ProviderProbeResult:
    """Compute product_ready and blocked_reasons from probe fields.

    Knowledge/task/hetu provider gates apply only when the corresponding capability is
    enabled. Disabled capabilities do not fail product readiness.
    """
    from vibe_control.components import (
        capability_enabled,
        enrich_capability_readiness,
        resolve_component_runtime,
    )

    # Empty components → fresh/default catalog (all disabled).
    if not probe.components:
        probe.components = dict(resolve_component_runtime(None)["components"] or {})

    reasons: list[str] = []
    if probe.config_ok is False:
        for reason in probe.blocked_reasons:
            if reason in {
                "required_component_disabled",
                "unsupported_component_enabled",
                "unknown_component_configured",
            }:
                reasons.append(reason)
        # Ensure config failures always surface even if blocked_reasons was empty.
        if not reasons and probe.blocked_reasons:
            reasons.extend(list(probe.blocked_reasons))
        elif not reasons:
            reasons.append("unknown_component_configured")

    knowledge_on = capability_enabled(probe.components, "knowledge")
    task_on = capability_enabled(probe.components, "task")
    hetu_on = capability_enabled(probe.components, "hetu")
    probe.hetu_enabled = hetu_on

    if knowledge_on:
        if not probe.knowledge_available:
            reasons.append("knowledge_provider_unavailable")
        elif not probe.knowledge_target_ok:
            reasons.append("knowledge_target_not_ok")
        if probe.sync_state != "synced":
            reasons.append(f"knowledge_sync_state={probe.sync_state}")
        if not probe.provider_ask_clean:
            condition = (probe.ask_hygiene or {}).get("condition") or "not_clean"
            reasons.append(f"ask_hygiene={condition}")

    if task_on:
        if not probe.task_available:
            reasons.append("task_provider_unavailable")
        elif not probe.task_readable:
            reasons.append("task_provider_not_readable")
        if not probe.task_cache_current:
            reasons.append("task_cache_not_current")

    if hetu_on:
        # Enabled Hetu is ready only when strict index_state=ready.
        if probe.hetu_index_state == "ready" and probe.hetu_ready:
            pass
        else:
            # Normalize ready flag from state when callers only set index_state.
            if probe.hetu_index_state == "ready":
                probe.hetu_ready = True
            else:
                probe.hetu_ready = False
                mapped = hetu_blocked_reason_for_state(
                    index_state=probe.hetu_index_state or "unavailable",
                    block_detail=probe.hetu_block_reason,
                )
                if mapped:
                    reasons.append(mapped)
    else:
        # Disabled: clear readiness participation; do not invent probe noise.
        probe.hetu_ready = False

    # Deduplicate while preserving order.
    probe.blocked_reasons = list(dict.fromkeys(reasons))
    probe.product_ready = len(probe.blocked_reasons) == 0 and probe.config_ok is True
    if probe.components:
        probe.components = enrich_capability_readiness(
            probe.components,
            knowledge_available=probe.knowledge_available,
            knowledge_target_ok=probe.knowledge_target_ok,
            sync_state=probe.sync_state,
            provider_ask_clean=probe.provider_ask_clean,
            task_available=probe.task_available,
            task_readable=probe.task_readable,
            task_cache_current=probe.task_cache_current,
            hetu_available=probe.hetu_available,
            hetu_ready=probe.hetu_ready if hetu_on else False,
            hetu_index_state=probe.hetu_index_state,
        )
    probe.evidence_hash = _evidence_hash(
        {
            "config_ok": probe.config_ok,
            "knowledge_enabled": knowledge_on,
            "task_enabled": task_on,
            "hetu_enabled": hetu_on,
            "knowledge_available": probe.knowledge_available,
            "knowledge_target_ok": probe.knowledge_target_ok,
            "sync_state": probe.sync_state,
            "provider_ask_clean": probe.provider_ask_clean,
            "task_available": probe.task_available,
            "task_readable": probe.task_readable,
            "ready_queue_available": probe.ready_queue_available,
            "task_cache_current": probe.task_cache_current,
            "hetu_available": probe.hetu_available,
            "hetu_ready": probe.hetu_ready if hetu_on else None,
            "hetu_index_state": probe.hetu_index_state,
            "blocked_reasons": probe.blocked_reasons,
        }
    )
    probe.probed = True
    return probe


def build_probe_from_parts(
    *,
    knowledge_available: bool,
    knowledge_target_ok: bool,
    sync_state: str,
    required_updates_count: int = 0,
    candidate_count: int = 0,
    orphan_managed_count: int = 0,
    task_available: bool,
    task_mode: str,
    task_readable: bool,
    ready_queue_available: bool | None = None,
    task_cache_current: bool = True,
    task_cache: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    config_ok: bool = True,
    components: dict[str, Any] | None = None,
    component_blocked_reasons: list[str] | None = None,
    hetu_enabled: bool = False,
    hetu_available: bool = False,
    hetu_ready: bool = False,
    hetu_index_state: str | None = None,
    hetu_provider: str | None = None,
    hetu_index_commit: str | None = None,
    hetu_observed_head: str | None = None,
    hetu_block_reason: str | None = None,
) -> ProviderProbeResult:
    hygiene = evaluate_ask_hygiene(
        sync_state=sync_state,
        required_updates_count=required_updates_count,
        candidate_count=candidate_count,
        orphan_managed_count=orphan_managed_count,
    )
    probe = ProviderProbeResult(
        knowledge_available=knowledge_available,
        knowledge_target_ok=knowledge_target_ok,
        sync_state=sync_state,
        ask_hygiene=hygiene,
        provider_ask_clean=bool(hygiene.get("provider_ask_clean")),
        task_available=task_available,
        task_mode=task_mode,
        task_readable=task_readable,
        ready_queue_available=ready_queue_available,
        task_cache_current=task_cache_current,
        task_cache=dict(task_cache or {}),
        config_ok=config_ok,
        components=dict(components or {}),
        blocked_reasons=list(component_blocked_reasons or []),
        warnings=list(warnings or []),
        hetu_enabled=hetu_enabled,
        hetu_available=hetu_available,
        hetu_ready=hetu_ready,
        hetu_index_state=hetu_index_state,
        hetu_provider=hetu_provider,
        hetu_index_commit=hetu_index_commit,
        hetu_observed_head=hetu_observed_head,
        hetu_block_reason=hetu_block_reason,
    )
    return finalize_product_ready(probe)


def probe_knowledge_readiness(repo_root: Path) -> dict[str, Any]:
    """Important-node knowledge probe (active provider; may call real NotebookLM)."""
    from vibe_control.config import ConfigError, load_config

    out: dict[str, Any] = {
        "available": False,
        "target_ok": False,
        "sync_state": "unavailable",
        "required_updates_count": 0,
        "candidate_count": 0,
        "orphan_managed_count": 0,
        "warnings": [],
    }
    try:
        config = load_config(repo_root)
    except ConfigError as exc:
        out["warnings"].append(exc.message)
        return out

    active = str(config.knowledge.get("provider") or "notebooklm").strip().lower()
    if active == "local_fts":
        from vibe_control.knowledge.local_fts.provider import LocalFtsProvider

        try:
            status = LocalFtsProvider().status(config, repo_root=repo_root, notebook_alias=None)
        except Exception as exc:  # noqa: BLE001
            out["warnings"].append(f"local_fts status probe failed: {exc}")
            return out
        sync_state = str(status.get("sync_state") or "unavailable")
        out["sync_state"] = sync_state
        out["available"] = bool(status.get("available")) and sync_state != "unavailable"
        out["target_ok"] = bool(status.get("target_ok", True)) and sync_state != "unavailable"
        out["required_updates_count"] = int(status.get("required_updates_count") or 0)
        out["candidate_count"] = int(status.get("candidate_count") or 0)
        out["orphan_managed_count"] = int(status.get("orphan_managed_count") or 0)
        return out

    from vibe_control.knowledge.phase8_runtime import get_runtime

    try:
        runtime = get_runtime(repo_root=repo_root)
        status = runtime.status(config, alias=None)
    except Exception as exc:  # noqa: BLE001 — probe must fail closed
        out["warnings"].append(f"knowledge status probe failed: {exc}")
        return out

    sync_state = str(status.get("sync_state") or "unavailable")
    out["sync_state"] = sync_state
    out["available"] = sync_state != "unavailable"
    target = status.get("target") or {}
    out["target_ok"] = bool(target) and sync_state not in {"target_mismatch", "unavailable"}
    # Prefer explicit counts when present on status / probe payloads.
    probe = status.get("probe") or {}
    out["required_updates_count"] = int(
        status.get("required_updates_count")
        or len(status.get("required_updates") or [])
        or probe.get("missing_count")
        or 0
    )
    candidates = status.get("cleanup_candidates") or status.get("candidates") or []
    if isinstance(candidates, list):
        out["candidate_count"] = len(candidates)
    else:
        out["candidate_count"] = int(status.get("candidate_count") or 0)
    out["orphan_managed_count"] = int(
        status.get("orphan_managed_count")
        or len(status.get("orphan_managed") or [])
        or 0
    )
    return out


def probe_task_readiness(repo_root: Path) -> dict[str, Any]:
    """Important-node Beads readonly probe (list + ready semantics; no mutation)."""
    from vibe_control.task.beads_readonly import BeadsReadonlyProvider

    provider = BeadsReadonlyProvider()
    out: dict[str, Any] = {
        "available": False,
        "mode": "unavailable",
        "readable": False,
        "ready_queue_available": None,
        "warnings": [],
        "task_count": None,
        "ready_count": None,
    }
    if not provider.which():
        out["warnings"].append("bd not found on PATH")
        return out

    # Probe inventory — parse failure must not look like empty inventory.
    tasks = provider.list_tasks()
    if not provider.available:
        out["warnings"].extend(list(provider.warnings or []))
        out["mode"] = "unavailable"
        return out

    out["available"] = True
    out["readable"] = True
    out["mode"] = "readonly"
    out["task_count"] = len(tasks)

    ready = provider.list_ready_tasks()
    if provider.ready_queue_ok is False:
        out["ready_queue_available"] = False
        out["warnings"].extend(
            [w for w in (provider.warnings or []) if "ready" in w.lower()]
        )
    elif provider.ready_queue_ok is True:
        out["ready_queue_available"] = True
        out["ready_count"] = len(ready)
    else:
        out["ready_queue_available"] = None
    return out


def probe_task_cache(
    repo_root: Path,
    *,
    knowledge_ready: bool,
    task_available: bool,
    task_readable: bool,
) -> dict[str, Any]:
    """Readonly reconcile + apply dry-run to evaluate local ephemeral task cache."""
    from vibe_control.task.apply_cli import run_task_apply
    from vibe_control.task.cache import evaluate_task_cache_state
    from vibe_control.task.reconcile_cli import run_task_reconcile_dry_run

    counts = {
        "matched": 0,
        "missing": 0,
        "stale": 0,
        "duplicate": 0,
        "conflict": 0,
        "unmanaged": 0,
    }
    plan = {"create": 0, "update": 0, "skip": 0, "blocked": 0}
    warnings: list[str] = []
    try:
        rec = run_task_reconcile_dry_run(repo_root=repo_root, provider_name="beads")
        data = rec.get("data") or {}
        if isinstance(data.get("counts"), dict):
            counts = {**counts, **data["counts"]}
        if not rec.get("ok"):
            warnings.append("task_reconcile_probe_failed")
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"task_reconcile_probe_failed: {exc}")
    try:
        apply_env = run_task_apply(
            repo_root=repo_root,
            mode="dry_run",
            provider_name="beads",
            strict_providers=False,
        )
        plan_data = ((apply_env.get("data") or {}).get("plan")) or {}
        if isinstance(plan_data, dict):
            plan = {**plan, **plan_data}
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"task_apply_dry_run_probe_failed: {exc}")

    state = evaluate_task_cache_state(
        reconcile_counts=counts,
        apply_plan_counts=plan,
        knowledge_ready=knowledge_ready,
        task_available=task_available,
        task_readable=task_readable,
    )
    state["warnings"] = list(state.get("warnings") or []) + warnings
    return state


def probe_hetu_readiness(repo_root: Path) -> dict[str, Any]:
    """Readonly Hetu readiness probe (status evaluation only; never reindexes).

    Callers must only invoke when components.hetu.enabled=true. Failures map to
    unavailable rather than raising.
    """
    out: dict[str, Any] = {
        "enabled": True,
        "available": False,
        "ready": False,
        "index_state": "unavailable",
        "provider": None,
        "index_commit": None,
        "observed_head": None,
        "block_detail": None,
        "warnings": [],
    }
    try:
        from vibe_control.config import ConfigError, load_config, parse_hetu_config
        from vibe_control.hetu.binding import canonicalize_repo_root
        from vibe_control.hetu.commands import HetuCommandContext, build_hetu_status
        from vibe_control.hetu.provider import FakeHetuProvider
        from vibe_control.hetu.receipt import load_index_binding_receipt
        from vibe_control.progress_brief import read_git_status_short, read_observed_head
    except Exception as exc:  # noqa: BLE001
        out["warnings"].append(f"hetu probe import failed: {exc}")
        return out

    try:
        config = load_config(repo_root)
    except ConfigError as exc:
        out["warnings"].append(exc.message)
        return out

    hetu_cfg = parse_hetu_config(config.hetu if isinstance(config.hetu, dict) else {})
    provider_id = hetu_cfg.provider
    out["provider"] = provider_id
    root = canonicalize_repo_root(repo_root)
    observed_head = read_observed_head(root) or "unknown"
    git_dirty = bool(read_git_status_short(root).strip())
    out["observed_head"] = observed_head

    configured_project = hetu_cfg.codebase_memory.project
    provider_version: str | None = None
    provider_available = True
    provider_compatible = True
    watcher_observable = True
    projects: list[dict[str, Any]] = []
    config_values: dict[str, str] | None = {}
    provider: Any = None
    receipt_provider = provider_id if provider_id != "fake" else "fake"

    if provider_id == "fake":
        provider = FakeHetuProvider(
            repo_root=root,
            projects=[
                {
                    "name": configured_project or "fake-project",
                    "root_path": str(root),
                    "nodes": 2,
                    "edges": 1,
                }
            ],
        )
        provider_version = provider._status.provider_version
        projects = provider.list_projects()
        config_values = {"auto_watch": "false"}
    else:
        try:
            from vibe_control.hetu.codebase_memory_cli import (
                CodebaseMemoryCliAdapter,
                CodebaseMemoryCliError,
            )

            adapter = CodebaseMemoryCliAdapter(
                binary=hetu_cfg.codebase_memory.binary,
                project=configured_project,
                repo_root=root,
                query_timeout_sec=hetu_cfg.codebase_memory.query_timeout_sec,
                reindex_timeout_sec=hetu_cfg.codebase_memory.reindex_timeout_sec,
            )
            provider = adapter
            try:
                compat = adapter.probe_compatibility()
                provider_version = compat.provider_version
                provider_compatible = bool(compat.compatible)
                projects = list(compat.projects or [])
                config_values = compat.config_values
                watcher_observable = compat.config_values is not None
                provider_available = True
                if not provider_compatible:
                    out["block_detail"] = "provider_incompatible"
            except CodebaseMemoryCliError as exc:
                provider_available = False
                provider_compatible = False
                watcher_observable = False
                config_values = None
                out["warnings"].append(f"hetu provider probe failed: {exc}")
                if getattr(exc, "code", "") == "provider_incompatible":
                    out["block_detail"] = "provider_incompatible"
        except Exception as exc:  # noqa: BLE001
            out["warnings"].append(f"hetu provider probe failed: {exc}")
            return out

    def _list_projects() -> list[dict[str, Any]]:
        if provider is not None and hasattr(provider, "list_projects"):
            return list(provider.list_projects())
        return list(projects)

    def _config_values() -> dict[str, str] | None:
        return None if config_values is None else dict(config_values)

    def _index_status(project: str):
        if provider is None:
            raise RuntimeError("provider missing")
        if hasattr(provider, "project"):
            try:
                provider.project = project  # type: ignore[attr-defined]
            except Exception:
                pass
        return provider.status()

    ctx = HetuCommandContext(
        repo_root=root,
        project_id=str(config.project_id),
        provider_id=provider_id if provider_id != "fake" else "fake",
        provider_version=provider_version,
        index_mode=hetu_cfg.codebase_memory.index_mode,
        configured_project=configured_project,
        hetu_enabled=True,
        provider_available=provider_available,
        provider_compatible=provider_compatible,
        watcher_state_observable=watcher_observable,
        list_projects=_list_projects,
        config_values=_config_values,
        load_receipt=lambda: load_index_binding_receipt(
            str(config.project_id),
            provider=receipt_provider,
        ),
        index_status=_index_status,
        provider=provider,
        observed_head=observed_head,
        git_dirty=git_dirty,
    )
    try:
        status = build_hetu_status(ctx)
    except Exception as exc:  # noqa: BLE001
        out["warnings"].append(f"hetu status probe failed: {exc}")
        return out

    data = status.get("data") or {}
    index = data.get("index") or {}
    provider_info = data.get("provider") or {}
    index_state = str(index.get("index_state") or "unavailable")
    out["index_state"] = index_state
    out["index_commit"] = index.get("index_commit")
    out["observed_head"] = (data.get("git") or {}).get("observed_head") or observed_head
    out["provider"] = provider_info.get("id") or provider_id
    out["available"] = bool(provider_info.get("available"))
    out["ready"] = index_state == "ready"
    reason = status.get("reason") or index.get("reason")
    if reason:
        out["block_detail"] = str(reason)
    return out


def evaluate_product_readiness(
    *,
    repo_root: Path,
    knowledge: dict[str, Any] | None = None,
    task: dict[str, Any] | None = None,
    task_cache: dict[str, Any] | None = None,
    hetu: dict[str, Any] | None = None,
    probe: bool = True,
    probe_task_cache_state: bool = True,
) -> ProviderProbeResult:
    """Build ProviderProbeResult for product readiness.

    When probe=True and parts are omitted, runs important-node probes once and reuses.
    Disabled Hetu never triggers a provider probe.
    """
    warnings: list[str] = []
    if knowledge is None:
        if probe:
            knowledge = probe_knowledge_readiness(repo_root)
        else:
            knowledge = {
                "available": False,
                "target_ok": False,
                "sync_state": "unavailable",
                "required_updates_count": 0,
                "candidate_count": 0,
                "orphan_managed_count": 0,
                "warnings": ["knowledge probe skipped"],
            }
    if task is None:
        if probe:
            task = probe_task_readiness(repo_root)
        else:
            task = {
                "available": False,
                "mode": "unavailable",
                "readable": False,
                "ready_queue_available": None,
                "warnings": ["task probe skipped"],
            }

    warnings.extend(list(knowledge.get("warnings") or []))
    warnings.extend(list(task.get("warnings") or []))

    hygiene_preview = evaluate_ask_hygiene(
        sync_state=str(knowledge.get("sync_state") or "unavailable"),
        required_updates_count=int(knowledge.get("required_updates_count") or 0),
        candidate_count=int(knowledge.get("candidate_count") or 0),
        orphan_managed_count=int(knowledge.get("orphan_managed_count") or 0),
    )
    knowledge_ready = bool(
        knowledge.get("available")
        and knowledge.get("target_ok")
        and str(knowledge.get("sync_state") or "") == "synced"
        and hygiene_preview.get("provider_ask_clean")
    )
    if task_cache is None and probe and probe_task_cache_state and bool(task.get("available")):
        task_cache = probe_task_cache(
            repo_root,
            knowledge_ready=knowledge_ready,
            task_available=bool(task.get("available")),
            task_readable=bool(task.get("readable")),
        )
    elif task_cache is None:
        task_cache = {
            "task_cache_mode": "local_embedded_ephemeral",
            "task_cache_current": True,
            "task_cache_action_required": False,
            "safe_task_convergence_allowed": False,
            "task_cache_reset_required": False,
        }

    warnings.extend(list(task_cache.get("warnings") or []))

    from vibe_control.components import capability_enabled, resolve_components_from_repo

    component_runtime = resolve_components_from_repo(repo_root)
    components = dict(component_runtime.get("components") or {})
    hetu_on = capability_enabled(components, "hetu")

    if not hetu_on:
        # Disabled → no probe and no readiness effect.
        hetu = {
            "enabled": False,
            "available": False,
            "ready": False,
            "index_state": None,
            "provider": None,
            "index_commit": None,
            "observed_head": None,
            "block_detail": None,
            "warnings": [],
        }
    elif hetu is None:
        if probe:
            hetu = probe_hetu_readiness(repo_root)
        else:
            hetu = {
                "enabled": True,
                "available": False,
                "ready": False,
                "index_state": "unavailable",
                "provider": None,
                "index_commit": None,
                "observed_head": None,
                "block_detail": None,
                "warnings": ["hetu probe skipped"],
            }
    warnings.extend(list((hetu or {}).get("warnings") or []))

    result = build_probe_from_parts(
        knowledge_available=bool(knowledge.get("available")),
        knowledge_target_ok=bool(knowledge.get("target_ok")),
        sync_state=str(knowledge.get("sync_state") or "unavailable"),
        required_updates_count=int(knowledge.get("required_updates_count") or 0),
        candidate_count=int(knowledge.get("candidate_count") or 0),
        orphan_managed_count=int(knowledge.get("orphan_managed_count") or 0),
        task_available=bool(task.get("available")),
        task_mode=str(task.get("mode") or "unavailable"),
        task_readable=bool(task.get("readable")),
        ready_queue_available=task.get("ready_queue_available"),
        task_cache_current=bool(task_cache.get("task_cache_current")),
        task_cache=task_cache,
        warnings=warnings,
        config_ok=bool(component_runtime.get("config_ok")),
        components=components,
        component_blocked_reasons=list(component_runtime.get("blocked_reasons") or []),
        hetu_enabled=hetu_on,
        hetu_available=bool((hetu or {}).get("available")),
        hetu_ready=bool((hetu or {}).get("ready")),
        hetu_index_state=(hetu or {}).get("index_state"),
        hetu_provider=(hetu or {}).get("provider"),
        hetu_index_commit=(hetu or {}).get("index_commit"),
        hetu_observed_head=(hetu or {}).get("observed_head"),
        hetu_block_reason=(hetu or {}).get("block_detail"),
    )
    return result


def readiness_next_actions(probe: ProviderProbeResult) -> list[dict[str, Any]]:
    from vibe_control.components import capability_enabled

    actions: list[dict[str, Any]] = []
    knowledge_on = capability_enabled(probe.components, "knowledge")
    task_on = capability_enabled(probe.components, "task")
    hetu_on = capability_enabled(probe.components, "hetu")

    if not knowledge_on:
        actions.append(
            next_action(
                code="ENABLE_KNOWLEDGE_CAPABILITY",
                command="vibe doctor --json",
                mutation=False,
                reason=(
                    "knowledge capability is disabled (target default). "
                    "Enable components.knowledge.enabled=true after NotebookLM prerequisites."
                ),
            )
        )
    elif not probe.knowledge_available or probe.sync_state == "unavailable":
        actions.append(
            next_action(
                code="KNOWLEDGE_PROVIDER_DIAGNOSIS",
                command="vibe knowledge status --json",
                mutation=False,
                reason="Diagnose NotebookLM provider availability before business guesses",
            )
        )
    elif probe.sync_state in {"drift", "pending", "receipt_missing"}:
        actions.append(
            next_action(
                code="KNOWLEDGE_SYNC_DRY_RUN",
                command="vibe knowledge sync --dry-run --json",
                mutation=False,
                reason="Preview provider sync; do not apply without owner approval",
            )
        )
    if knowledge_on and not probe.provider_ask_clean:
        actions.append(
            next_action(
                code="ASK_HYGIENE",
                command="vibe knowledge cleanup-candidates --json",
                mutation=False,
                reason="Inspect ask hygiene / cleanup candidates (no auto-delete)",
            )
        )
    if not task_on:
        actions.append(
            next_action(
                code="ENABLE_TASK_CAPABILITY",
                command="vibe doctor --json",
                mutation=False,
                reason=(
                    "task capability is disabled (target default). "
                    "Enable components.task.enabled=true after Beads/task-cache prerequisites."
                ),
            )
        )
    elif not probe.task_available:
        actions.append(
            next_action(
                code="TASK_PROVIDER_DIAGNOSIS",
                command="vibe task doctor --json",
                mutation=False,
                reason="Diagnose Beads provider before treating inventory as empty",
            )
        )
    else:
        actions.append(
            next_action(
                code="TASK_RECONCILE_READONLY",
                command="vibe task reconcile --dry-run --json --provider beads",
                mutation=False,
                reason="Readonly Beads reconcile",
            )
        )
    if hetu_on and not probe.hetu_ready:
        actions.append(
            next_action(
                code="HETU_STATUS",
                command="vibe hetu status --json",
                mutation=False,
                reason="Diagnose Hetu index freshness before treating the graph as ready",
            )
        )
        actions.append(
            next_action(
                code="HETU_REINDEX_DRY_RUN",
                command="vibe hetu reindex --dry-run --json",
                mutation=False,
                reason=(
                    "Preview confirmed Hetu reindex plan; closeout never auto-reindexes. "
                    "Apply requires --confirm-hetu-reindex-apply."
                ),
            )
        )
    if not probe.product_ready:
        actions.append(
            next_action(
                code="PRODUCT_NOT_READY",
                command="vibe integration status --json",
                mutation=False,
                reason="Repo fallback is not full product readiness; fix blocked_reasons",
            )
        )
    # Task-cache next_actions only matter when task capability is enabled.
    if task_on:
        cache = probe.task_cache or {}
        for action in cache.get("next_actions") or []:
            if isinstance(action, dict):
                actions.append(action)
    return actions
