"""Hetu status / doctor / readonly structural / reindex dry-run+apply command builders."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from vibe_control.hetu.binding import (
    ArtifactEvidence,
    BindingResolution,
    canonicalize_repo_root,
    compute_repo_realpath_hash,
    detect_codebase_memory_artifact,
    interpret_auto_watch,
    resolve_project_binding,
)
from vibe_control.hetu.models import (
    ArchitectureCluster,
    ArchitectureResult,
    ImpactResult,
    ImpactSymbol,
    IndexBindingReceipt,
    ProviderStatusResult,
    SearchHit,
    SearchResult,
    TraceEdge,
    TraceNode,
    TraceResult,
)
from vibe_control.hetu.provider import FakeHetuProvider, HetuProvider, ReindexResult
from vibe_control.hetu.receipt import (
    RECEIPT_SCHEMA,
    IndexBindingReceiptLoadResult,
    compute_binding_hash,
    load_index_binding_receipt,
    write_index_binding_receipt,
)
from vibe_control.hetu.state import HetuReadinessInputs, IndexStateEvaluation, evaluate_index_state
from vibe_control.json_envelope import (
    attach_operation_result,
    failure_envelope,
    next_action,
    success_envelope,
)

EFFECT_HETU_INDEX_REPOSITORY = {
    "kind": "provider_write",
    "target": "hetu.index_repository",
    "status": "completed",
}
EFFECT_HETU_INDEX_BINDING = {
    "kind": "local_state_write",
    "target": "hetu.index_binding",
    "status": "completed",
}

# Spec §9 query caps.
SEARCH_LIMIT_DEFAULT = 20
SEARCH_LIMIT_MAX = 50
TRACE_DEPTH_DEFAULT = 3
TRACE_DEPTH_MAX = 5
TRACE_MAX_PATHS = 50
TRACE_MAX_NODES = 200
TRACE_MAX_EDGES = 300
IMPACT_DEPTH_DEFAULT = 2
IMPACT_DEPTH_MAX = 5
IMPACT_MAX_SYMBOLS = 100
IMPACT_MAX_EDGES = 200
ARCH_MAX_CLUSTERS = 20
ARCH_MAX_REPS_PER_CLUSTER = 5
TRACE_DIRECTIONS = frozenset({"inbound", "outbound", "both"})


ListProjectsFn = Callable[[], list[dict[str, Any]]]
ConfigValuesFn = Callable[[], dict[str, str] | None]
ReceiptLoadFn = Callable[[], IndexBindingReceiptLoadResult]
IndexStatusFn = Callable[[str], ProviderStatusResult]
RefreshGitFn = Callable[[], tuple[str, bool]]
WriteReceiptFn = Callable[..., Path]


@dataclass
class HetuCommandContext:
    """Injected deps for Hetu commands.

    Readonly builders (status/doctor/query/reindex dry-run) must not mutate provider
    config/index. Reindex apply may call provider.reindex and write the binding receipt.
    """

    repo_root: Path
    project_id: str
    provider_id: str = "codebase_memory"
    provider_version: str | None = "0.9.0"
    index_mode: str = "fast"
    configured_project: str | None = None
    hetu_enabled: bool = False
    provider_available: bool = True
    provider_compatible: bool = True
    watcher_state_observable: bool = True
    list_projects: ListProjectsFn = field(default_factory=lambda: (lambda: []))
    config_values: ConfigValuesFn = field(default_factory=lambda: (lambda: {}))
    load_receipt: ReceiptLoadFn | None = None
    index_status: IndexStatusFn | None = None
    provider: HetuProvider | None = None
    observed_head: str = "unknown"
    git_dirty: bool = False
    artifact: ArtifactEvidence | None = None
    search_limit_default: int = SEARCH_LIMIT_DEFAULT
    trace_depth_default: int = TRACE_DEPTH_DEFAULT
    impact_depth_default: int = IMPACT_DEPTH_DEFAULT
    state_home: Path | None = None
    refresh_git: RefreshGitFn | None = None
    write_receipt: WriteReceiptFn | None = None
    # Mutation call counters for tests (must stay empty for readonly/dry-run).
    mutation_calls: list[str] = field(default_factory=list)

    def record_mutation(self, name: str) -> None:
        self.mutation_calls.append(name)

    def current_git(self) -> tuple[str, bool]:
        if self.refresh_git is not None:
            return self.refresh_git()
        return self.observed_head, bool(self.git_dirty)


def context_from_fake_provider(
    *,
    repo_root: Path | str,
    project_id: str,
    provider: FakeHetuProvider,
    projects: list[dict[str, Any]] | None = None,
    config_values: dict[str, str] | None = None,
    configured_project: str | None = None,
    hetu_enabled: bool = True,
    provider_available: bool = True,
    provider_compatible: bool = True,
    watcher_state_observable: bool = True,
    observed_head: str = "abc123",
    git_dirty: bool = False,
    receipt: IndexBindingReceipt | None = None,
    receipt_missing: bool = True,
    receipt_corrupt: bool = False,
    provider_id: str | None = None,
    provider_version: str | None = None,
    index_mode: str = "fast",
    artifact: ArtifactEvidence | None = None,
    home: Path | None = None,
    refresh_git: RefreshGitFn | None = None,
    write_receipt: WriteReceiptFn | None = None,
) -> HetuCommandContext:
    """Build a command context driven by FakeHetuProvider + injected inventory."""
    # Peek status without recording a command call (tests assert call lists).
    status = provider._status
    pid = provider_id or status.provider or provider.name
    version = provider_version if provider_version is not None else status.provider_version
    root = canonicalize_repo_root(repo_root)
    if projects is not None:
        provider.set_projects(list(projects))
    if provider._repo_root is None:
        provider._repo_root = str(root)

    def _load_receipt() -> IndexBindingReceiptLoadResult:
        if receipt_corrupt:
            return IndexBindingReceiptLoadResult(
                ok=False,
                code="RECEIPT_CORRUPTED",
                reason="invalid_json",
                message="Index binding receipt is corrupted or unreadable",
                relative_path=f"{project_id}/hetu/{pid}/index-binding.json",
            )
        if receipt_missing or receipt is None:
            if home is not None:
                return load_index_binding_receipt(project_id, provider=pid, home=home)
            return IndexBindingReceiptLoadResult(
                ok=False,
                code="RECEIPT_MISSING",
                reason="receipt_missing",
                message="Index binding receipt is missing",
                relative_path=f"{project_id}/hetu/{pid}/index-binding.json",
            )
        return IndexBindingReceiptLoadResult(
            ok=True,
            receipt=receipt,
            relative_path=f"{project_id}/hetu/{pid}/index-binding.json",
        )

    def _index_status(project: str) -> ProviderStatusResult:
        # Reuse fake status; stamp selected project name.
        base = provider.status()
        return ProviderStatusResult(
            provider=base.provider,
            provider_version=base.provider_version,
            provider_project=project,
            index_state=base.index_state,
            index_commit=base.index_commit,
            node_count=base.node_count,
            edge_count=base.edge_count,
            auto_watch_effective=base.auto_watch_effective,
            freshness_assurance=base.freshness_assurance,
            reason=base.reason,
        )

    cfg = config_values

    def _list_projects() -> list[dict[str, Any]]:
        return provider.list_projects()

    def _config_values() -> dict[str, str] | None:
        return None if cfg is None else dict(cfg)

    return HetuCommandContext(
        repo_root=root,
        project_id=project_id,
        provider_id=pid,
        provider_version=version,
        index_mode=index_mode,
        configured_project=configured_project,
        hetu_enabled=hetu_enabled,
        provider_available=provider_available,
        provider_compatible=provider_compatible,
        watcher_state_observable=watcher_state_observable,
        list_projects=_list_projects,
        config_values=_config_values,
        load_receipt=_load_receipt,
        index_status=_index_status,
        provider=provider,
        observed_head=observed_head,
        git_dirty=git_dirty,
        artifact=artifact,
        state_home=home,
        refresh_git=refresh_git,
        write_receipt=write_receipt,
    )


def _provider_index_status_str(status: ProviderStatusResult | None) -> str | None:
    if status is None:
        return None
    # ProviderStatusResult.index_state already maps ready/indexing/unavailable.
    if status.index_state == "indexing":
        return "indexing"
    if status.index_state == "ready":
        return "ready"
    return status.index_state


def _next_actions_for_state(
    *,
    evaluation: IndexStateEvaluation,
    binding: BindingResolution,
    auto_watch_effective: bool | None,
    watcher_compatible: bool,
    provider_id: str,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    state = evaluation.index_state
    reason = evaluation.reason

    if not watcher_compatible:
        actions.append(
            next_action(
                code="HETU_WATCHER_UNOBSERVABLE",
                command="vibe hetu doctor --json",
                mutation=False,
                reason=(
                    "Installed provider cannot expose effective auto_watch; "
                    "upgrade codebase-memory-mcp before strict Hetu readiness"
                ),
            )
        )

    if auto_watch_effective is not False and watcher_compatible:
        actions.append(
            next_action(
                code="HETU_AUTO_WATCH_MUST_BE_FALSE",
                command="codebase-memory-mcp config set auto_watch false",
                mutation=True,
                reason=(
                    "Strict Hetu readiness requires effective auto_watch=false; "
                    "Vibe recommends this owner-managed config change but will not run it"
                ),
            )
        )

    if state == "conflict_needs_choice" or binding.binding_conflict:
        actions.append(
            next_action(
                code="HETU_BINDING_CONFLICT",
                command="vibe config validate --json",
                mutation=False,
                reason=(
                    "Set hetu.codebase_memory.project to the exact provider project "
                    "whose root_path matches this repo"
                ),
            )
        )

    if state == "missing":
        actions.append(
            next_action(
                code="HETU_INDEX_MISSING",
                command="vibe hetu reindex --dry-run --json",
                mutation=False,
                reason="No matching provider project; preview a create/reindex plan",
            )
        )
    elif state == "stale":
        actions.append(
            next_action(
                code="HETU_INDEX_STALE",
                command="vibe hetu reindex --dry-run --json",
                mutation=False,
                reason="Index is stale vs Git HEAD/dirty tree; preview reindex plan",
            )
        )
    elif state == "unverifiable":
        if reason == "receipt_missing" or reason == "receipt_corrupt":
            actions.append(
                next_action(
                    code="HETU_INDEX_UNVERIFIABLE",
                    command="vibe hetu reindex --dry-run --json",
                    mutation=False,
                    reason=(
                        "Provider index exists but no valid IndexBindingReceipt; "
                        "confirmed reindex establishes freshness"
                    ),
                )
            )
        elif reason == "external_index_mutation_possible":
            # Watcher action already added above when auto_watch is not false.
            actions.append(
                next_action(
                    code="HETU_INDEX_UNVERIFIABLE",
                    command="vibe hetu status --json",
                    mutation=False,
                    reason="Re-check status after owner sets auto_watch=false",
                )
            )
        else:
            actions.append(
                next_action(
                    code="HETU_INDEX_UNVERIFIABLE",
                    command="vibe hetu doctor --json",
                    mutation=False,
                    reason="Index binding cannot prove freshness; run doctor for details",
                )
            )
    elif state == "unavailable":
        code = "HETU_PROVIDER_UNAVAILABLE"
        if reason == "provider_incompatible":
            code = "HETU_PROVIDER_INCOMPATIBLE"
        actions.append(
            next_action(
                code=code,
                command="vibe hetu doctor --json",
                mutation=False,
                reason=f"Hetu provider {provider_id} is unavailable or incompatible",
            )
        )
    elif state == "indexing":
        actions.append(
            next_action(
                code="HETU_INDEX_INDEXING",
                command="vibe hetu status --json",
                mutation=False,
                reason="Provider reports indexing in progress; re-check status later",
            )
        )
    elif state == "ready":
        actions.append(
            next_action(
                code="HETU_READY",
                command="vibe hetu search --query <str> --json",
                mutation=False,
                reason="Hetu index is strictly ready for bounded structural queries",
            )
        )

    # Stable dedupe by (code, command).
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for item in actions:
        key = (str(item.get("code")), str(item.get("command")))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _evaluate_with_context(
    ctx: HetuCommandContext,
) -> tuple[
    BindingResolution,
    IndexStateEvaluation,
    ProviderStatusResult | None,
    bool | None,
    bool,
    IndexBindingReceiptLoadResult,
    list[dict[str, Any]],
]:
    root = canonicalize_repo_root(ctx.repo_root)
    art = ctx.artifact if ctx.artifact is not None else detect_codebase_memory_artifact(root)

    projects: list[dict[str, Any]] = []
    if ctx.provider_available:
        try:
            projects = list(ctx.list_projects() or [])
        except Exception:
            projects = []

    binding = resolve_project_binding(
        repo_root=root,
        projects=projects,
        configured_project=ctx.configured_project,
        artifact=art,
    )

    auto_watch_effective, watcher_compatible, watcher_reason = interpret_auto_watch(
        config_values=ctx.config_values() if ctx.provider_available else None,
        watcher_state_observable=ctx.watcher_state_observable,
    )

    provider_compatible = bool(ctx.provider_compatible) and watcher_compatible
    provider_available = bool(ctx.provider_available)

    provider_status: ProviderStatusResult | None = None
    if (
        provider_available
        and provider_compatible
        and binding.selected_project
        and not binding.binding_conflict
    ):
        if ctx.index_status is not None:
            provider_status = ctx.index_status(binding.selected_project)
        elif ctx.provider is not None:
            provider_status = ctx.provider.status()

    if ctx.load_receipt is not None:
        receipt_load = ctx.load_receipt()
    else:
        receipt_load = load_index_binding_receipt(
            ctx.project_id,
            provider=ctx.provider_id,
        )

    receipt = receipt_load.receipt if receipt_load.ok else None
    receipt_missing = (not receipt_load.ok) and receipt_load.reason == "receipt_missing"
    receipt_corrupt = (not receipt_load.ok) and receipt_load.reason != "receipt_missing"

    node_count = int(provider_status.node_count) if provider_status else 0
    edge_count = int(provider_status.edge_count) if provider_status else 0
    if provider_status is None and binding.selected_project:
        # Fall back to candidate counts when status not fetched.
        for cand in binding.matching_candidates:
            if cand.name == binding.selected_project:
                node_count = cand.nodes
                edge_count = cand.edges
                break

    provider_index_status = _provider_index_status_str(provider_status)
    if provider_status is None and binding.selected_project and not binding.binding_conflict:
        # Existing project without calling provider status still counts as present.
        if node_count + edge_count > 0:
            provider_index_status = "ready"

    evaluation = evaluate_index_state(
        HetuReadinessInputs(
            provider_available=provider_available,
            provider_compatible=provider_compatible,
            binding_conflict=binding.binding_conflict,
            provider_project=binding.selected_project,
            provider_index_status=provider_index_status,
            node_count=node_count,
            edge_count=edge_count,
            provider=ctx.provider_id,
            provider_version=ctx.provider_version,
            index_mode=ctx.index_mode,
            auto_watch_effective=auto_watch_effective,
            observed_head=ctx.observed_head,
            git_dirty=ctx.git_dirty,
            receipt=receipt,
            receipt_corrupt=receipt_corrupt,
            receipt_missing=receipt_missing or receipt is None,
        )
    )

    # Prefer explicit watcher incompatibility reason on unavailable.
    if not watcher_compatible and evaluation.index_state == "unavailable":
        evaluation = IndexStateEvaluation(
            index_state="unavailable",
            reason="provider_incompatible",
            message=(
                "Provider cannot expose effective watcher state; "
                "strict Hetu readiness is incompatible until upgraded"
            ),
            freshness_assurance=None,
        )

    actions = _next_actions_for_state(
        evaluation=evaluation,
        binding=binding,
        auto_watch_effective=auto_watch_effective,
        watcher_compatible=watcher_compatible,
        provider_id=ctx.provider_id,
    )
    return (
        binding,
        evaluation,
        provider_status,
        auto_watch_effective,
        watcher_compatible,
        receipt_load,
        actions,
    )


def _status_data(
    *,
    ctx: HetuCommandContext,
    binding: BindingResolution,
    evaluation: IndexStateEvaluation,
    provider_status: ProviderStatusResult | None,
    auto_watch_effective: bool | None,
    watcher_compatible: bool,
    receipt_load: IndexBindingReceiptLoadResult,
) -> dict[str, Any]:
    receipt = receipt_load.receipt if receipt_load.ok else None
    index_commit = receipt.index_commit if receipt is not None else None
    node_count = int(provider_status.node_count) if provider_status else 0
    edge_count = int(provider_status.edge_count) if provider_status else 0
    if provider_status is None and binding.selected_project:
        for cand in binding.matching_candidates:
            if cand.name == binding.selected_project:
                node_count = cand.nodes
                edge_count = cand.edges
                break

    return {
        "hetu_enabled": bool(ctx.hetu_enabled),
        "git": {
            "observed_head": ctx.observed_head,
            "dirty": bool(ctx.git_dirty),
        },
        "index": {
            "index_commit": index_commit,
            "index_state": evaluation.index_state,
            "freshness_assurance": evaluation.freshness_assurance,
            "reason": evaluation.reason,
            "message": evaluation.message,
            "node_count": node_count,
            "edge_count": edge_count,
        },
        "provider": {
            "id": ctx.provider_id,
            "version": ctx.provider_version,
            "project": binding.selected_project,
            "available": bool(ctx.provider_available),
            "compatible": bool(ctx.provider_compatible) and watcher_compatible,
            "auto_watch_effective": auto_watch_effective,
            "watcher_state_observable": bool(ctx.watcher_state_observable)
            and watcher_compatible,
        },
        "binding": binding.to_public_dict(),
        "receipt": {
            "present": bool(receipt_load.ok and receipt is not None),
            "ok": bool(receipt_load.ok),
            "code": receipt_load.code,
            "reason": receipt_load.reason,
            "relative_path": receipt_load.relative_path,
        },
    }


def _assert_no_mutations(ctx: HetuCommandContext) -> None:
    # Defensive: status/doctor must never record mutation calls.
    if ctx.mutation_calls:
        raise RuntimeError(
            f"Hetu status/doctor must not mutate; saw calls={ctx.mutation_calls!r}"
        )
    if ctx.provider is not None and isinstance(ctx.provider, FakeHetuProvider):
        reindex_calls = [c for c in ctx.provider.calls if c[0] == "reindex"]
        if reindex_calls:
            raise RuntimeError("Hetu status/doctor must not call reindex")


def build_hetu_status(ctx: HetuCommandContext) -> dict[str, Any]:
    """Readonly Hetu status envelope. Never calls index_repository or config set."""
    (
        binding,
        evaluation,
        provider_status,
        auto_watch_effective,
        watcher_compatible,
        receipt_load,
        actions,
    ) = _evaluate_with_context(ctx)
    _assert_no_mutations(ctx)

    data = _status_data(
        ctx=ctx,
        binding=binding,
        evaluation=evaluation,
        provider_status=provider_status,
        auto_watch_effective=auto_watch_effective,
        watcher_compatible=watcher_compatible,
        receipt_load=receipt_load,
    )
    envelope = success_envelope(
        command="hetu.status",
        project_id=ctx.project_id,
        data=data,
        warnings=[],
        next_actions=actions,
    )
    if evaluation.index_state != "ready":
        envelope["code"] = {
            "missing": "HETU_INDEX_MISSING",
            "indexing": "HETU_INDEX_INDEXING",
            "stale": "HETU_INDEX_STALE",
            "unverifiable": "HETU_INDEX_UNVERIFIABLE",
            "unavailable": (
                "HETU_PROVIDER_INCOMPATIBLE"
                if evaluation.reason == "provider_incompatible"
                else "HETU_PROVIDER_UNAVAILABLE"
            ),
            "conflict_needs_choice": "HETU_BINDING_CONFLICT",
        }.get(evaluation.index_state, "HETU_NOT_READY")
        envelope["reason"] = evaluation.reason
    else:
        envelope["code"] = "HETU_READY"
        envelope["reason"] = None

    return attach_operation_result(envelope, mutation_intent=False, effects=[])


def build_hetu_doctor(ctx: HetuCommandContext) -> dict[str, Any]:
    """Readonly Hetu doctor. Recommends config changes; never runs them."""
    (
        binding,
        evaluation,
        provider_status,
        auto_watch_effective,
        watcher_compatible,
        receipt_load,
        actions,
    ) = _evaluate_with_context(ctx)
    _assert_no_mutations(ctx)

    status_data = _status_data(
        ctx=ctx,
        binding=binding,
        evaluation=evaluation,
        provider_status=provider_status,
        auto_watch_effective=auto_watch_effective,
        watcher_compatible=watcher_compatible,
        receipt_load=receipt_load,
    )

    config_values = ctx.config_values() if ctx.provider_available else None
    doctor_data = {
        **status_data,
        "doctor": {
            "readonly": True,
            "mutations": {
                "index_repository": False,
                "config_set": False,
                "note": (
                    "Hetu doctor never mutates provider index or config; "
                    "auto_watch guidance is recommendation-only"
                ),
            },
            "watcher": {
                "observable": bool(ctx.watcher_state_observable) and config_values is not None,
                "compatible": watcher_compatible,
                "auto_watch_effective": auto_watch_effective,
                "auto_watch_key_present": (
                    None
                    if config_values is None
                    else ("auto_watch" in config_values)
                ),
                "provider_default_when_absent": True,
                "recommended_command": "codebase-memory-mcp config set auto_watch false",
                "recommended_mutation_performed": False,
            },
            "compatibility": {
                "provider_available": bool(ctx.provider_available),
                "provider_compatible": bool(ctx.provider_compatible) and watcher_compatible,
                "watcher_state_observable": bool(ctx.watcher_state_observable),
            },
        },
    }

    # Ensure watcher recommendation is present when needed (doctor-specific emphasis).
    if auto_watch_effective is not False and watcher_compatible:
        has_watch_action = any(
            a.get("code") == "HETU_AUTO_WATCH_MUST_BE_FALSE" for a in actions
        )
        if not has_watch_action:
            actions.insert(
                0,
                next_action(
                    code="HETU_AUTO_WATCH_MUST_BE_FALSE",
                    command="codebase-memory-mcp config set auto_watch false",
                    mutation=True,
                    reason=(
                        "Strict Hetu readiness requires effective auto_watch=false; "
                        "Vibe recommends this owner-managed config change but will not run it"
                    ),
                ),
            )

    if not watcher_compatible:
        has_unobs = any(a.get("code") == "HETU_WATCHER_UNOBSERVABLE" for a in actions)
        if not has_unobs:
            actions.insert(
                0,
                next_action(
                    code="HETU_WATCHER_UNOBSERVABLE",
                    command="vibe hetu doctor --json",
                    mutation=False,
                    reason=(
                        "Installed provider cannot expose effective auto_watch; "
                        "upgrade codebase-memory-mcp before strict Hetu readiness"
                    ),
                ),
            )

    envelope = success_envelope(
        command="hetu.doctor",
        project_id=ctx.project_id,
        data=doctor_data,
        warnings=[],
        next_actions=actions,
    )
    envelope["code"] = {
        "missing": "HETU_INDEX_MISSING",
        "indexing": "HETU_INDEX_INDEXING",
        "ready": "HETU_READY",
        "stale": "HETU_INDEX_STALE",
        "unverifiable": "HETU_INDEX_UNVERIFIABLE",
        "unavailable": (
            "HETU_PROVIDER_INCOMPATIBLE"
            if evaluation.reason == "provider_incompatible"
            else "HETU_PROVIDER_UNAVAILABLE"
        ),
        "conflict_needs_choice": "HETU_BINDING_CONFLICT",
    }.get(evaluation.index_state, "HETU_NOT_READY")
    envelope["reason"] = evaluation.reason

    result = attach_operation_result(envelope, mutation_intent=False, effects=[])
    # Final readonly guarantee for callers/tests.
    doctor_block = result["data"]["doctor"]
    doctor_block["mutations"]["config_set"] = False
    doctor_block["mutations"]["index_repository"] = False
    doctor_block["watcher"]["recommended_mutation_performed"] = False
    return result


# ---------------------------------------------------------------------------
# Readonly structural queries + reindex dry-run (Task 5)
# ---------------------------------------------------------------------------


def clamp_int(value: int | None, *, default: int, lo: int, hi: int) -> int:
    if value is None:
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, number))


def normalize_repo_relative_path(path: str | None, repo_root: Path | str) -> str:
    """Normalize provider paths to repo-relative POSIX form (no absolute roots)."""
    if path is None:
        return ""
    text = str(path).strip().replace("\\", "/")
    if not text:
        return ""
    root = canonicalize_repo_root(repo_root)
    candidate = Path(text)
    try:
        if candidate.is_absolute():
            return candidate.resolve().relative_to(root).as_posix()
    except (OSError, ValueError):
        # Outside repo or unresolvable — strip absolute prefix if it matches root string.
        root_s = root.as_posix().rstrip("/")
        if text.startswith(root_s + "/"):
            return text[len(root_s) + 1 :]
        if text.startswith("/"):
            # Never leak absolute foreign paths; keep basename as last resort.
            return Path(text).name
    while text.startswith("./"):
        text = text[2:]
    return text.lstrip("/")


def _sort_key_risk_hops_name(
    *,
    risk: float | None,
    hops: int | None,
    qualified_name: str,
    path: str,
) -> tuple[Any, ...]:
    # risk desc (None last), hops asc (None last), then name/path.
    risk_key = (0, -float(risk)) if risk is not None else (1, 0.0)
    hops_key = (0, int(hops)) if hops is not None else (1, 0)
    return (risk_key, hops_key, qualified_name, path)


def _sort_search_hits(items: list[SearchHit]) -> list[SearchHit]:
    def key(hit: SearchHit) -> tuple[Any, ...]:
        score_key = (0, -float(hit.score)) if hit.score is not None else (1, 0.0)
        return (score_key, hit.qualified_name, hit.path)

    return sorted(items, key=key)


def _normalize_search_hit(hit: SearchHit, repo_root: Path) -> SearchHit:
    return SearchHit(
        qualified_name=hit.qualified_name,
        path=normalize_repo_relative_path(hit.path, repo_root),
        start_line=hit.start_line,
        end_line=hit.end_line,
        score=hit.score,
    )


def _normalize_trace_node(node: TraceNode, repo_root: Path) -> TraceNode:
    return TraceNode(
        qualified_name=node.qualified_name,
        path=normalize_repo_relative_path(node.path, repo_root),
        start_line=node.start_line,
        end_line=node.end_line,
    )


def _normalize_impact_symbol(symbol: ImpactSymbol, repo_root: Path) -> ImpactSymbol:
    return ImpactSymbol(
        qualified_name=symbol.qualified_name,
        path=normalize_repo_relative_path(symbol.path, repo_root),
        risk=symbol.risk,
        hops=symbol.hops,
    )


def apply_search_caps(
    result: SearchResult,
    *,
    repo_root: Path,
    limit: int,
) -> SearchResult:
    """Stable-sort + path-normalize + cap search results; disclose truncation."""
    normalized = [_normalize_search_hit(h, repo_root) for h in result.items]
    ordered = _sort_search_hits(normalized)
    capped = ordered[:limit]
    provider_total = result.total
    # Cap hit always truncates, even when provider total is unknown.
    hit_cap = len(ordered) > limit
    if provider_total is None:
        truncated = bool(result.truncated) or hit_cap
        has_more = bool(result.has_more) or hit_cap
        total: int | None = None
    else:
        truncated = bool(result.truncated) or hit_cap or provider_total > len(capped)
        has_more = truncated
        total = provider_total
    return SearchResult(
        items=capped,
        total=total,
        returned=len(capped),
        has_more=has_more,
        truncated=truncated,
    )


def apply_trace_caps(result: TraceResult, *, repo_root: Path) -> TraceResult:
    nodes = [_normalize_trace_node(n, repo_root) for n in result.nodes]
    # Stable: hop distance via path length for paths; name for nodes/edges.
    paths = sorted(
        [list(p) for p in result.paths],
        key=lambda p: (len(p), ",".join(p)),
    )
    nodes_sorted = sorted(nodes, key=lambda n: (n.qualified_name, n.path))
    edges_sorted = sorted(
        list(result.edges),
        key=lambda e: (e.source, e.target, e.kind or ""),
    )
    truncated = bool(result.truncated)
    if len(paths) > TRACE_MAX_PATHS:
        paths = paths[:TRACE_MAX_PATHS]
        truncated = True
    if len(nodes_sorted) > TRACE_MAX_NODES:
        nodes_sorted = nodes_sorted[:TRACE_MAX_NODES]
        truncated = True
    if len(edges_sorted) > TRACE_MAX_EDGES:
        edges_sorted = edges_sorted[:TRACE_MAX_EDGES]
        truncated = True
    return TraceResult(
        paths=paths,
        nodes=nodes_sorted,
        edges=edges_sorted,
        truncated=truncated,
    )


def apply_impact_caps(result: ImpactResult, *, repo_root: Path) -> ImpactResult:
    symbols = [_normalize_impact_symbol(s, repo_root) for s in result.symbols]
    symbols_sorted = sorted(
        symbols,
        key=lambda s: _sort_key_risk_hops_name(
            risk=s.risk,
            hops=s.hops,
            qualified_name=s.qualified_name,
            path=s.path,
        ),
    )
    edges_sorted = sorted(
        list(result.edges),
        key=lambda e: (e.source, e.target, e.kind or ""),
    )
    truncated = bool(result.truncated)
    if len(symbols_sorted) > IMPACT_MAX_SYMBOLS:
        symbols_sorted = symbols_sorted[:IMPACT_MAX_SYMBOLS]
        truncated = True
    if len(edges_sorted) > IMPACT_MAX_EDGES:
        edges_sorted = edges_sorted[:IMPACT_MAX_EDGES]
        truncated = True
    return ImpactResult(
        symbols=symbols_sorted,
        edges=edges_sorted,
        truncated=truncated,
        mode=result.mode,
        freshness_assurance=result.freshness_assurance,
        uncertainty=result.uncertainty,
    )


def apply_architecture_caps(
    result: ArchitectureResult,
    *,
    repo_root: Path,
) -> ArchitectureResult:
    clusters_in = sorted(result.clusters, key=lambda c: c.name)
    truncated = bool(result.truncated)
    if len(clusters_in) > ARCH_MAX_CLUSTERS:
        clusters_in = clusters_in[:ARCH_MAX_CLUSTERS]
        truncated = True
    clusters: list[ArchitectureCluster] = []
    for cluster in clusters_in:
        reps = sorted(
            [_normalize_trace_node(n, repo_root) for n in cluster.representatives],
            key=lambda n: (n.qualified_name, n.path),
        )
        if len(reps) > ARCH_MAX_REPS_PER_CLUSTER:
            reps = reps[:ARCH_MAX_REPS_PER_CLUSTER]
            truncated = True
        clusters.append(ArchitectureCluster(name=cluster.name, representatives=reps))
    return ArchitectureResult(clusters=clusters, truncated=truncated)


def _index_state_code(evaluation: IndexStateEvaluation) -> str:
    return {
        "missing": "HETU_INDEX_MISSING",
        "indexing": "HETU_INDEX_INDEXING",
        "ready": "HETU_READY",
        "stale": "HETU_INDEX_STALE",
        "unverifiable": "HETU_INDEX_UNVERIFIABLE",
        "unavailable": (
            "HETU_PROVIDER_INCOMPATIBLE"
            if evaluation.reason == "provider_incompatible"
            else "HETU_PROVIDER_UNAVAILABLE"
        ),
        "conflict_needs_choice": "HETU_BINDING_CONFLICT",
    }.get(evaluation.index_state, "HETU_NOT_READY")


def _dirty_only_impact_allowed(
    *,
    ctx: HetuCommandContext,
    evaluation: IndexStateEvaluation,
    receipt_load: IndexBindingReceiptLoadResult,
    binding: BindingResolution,
    auto_watch_effective: bool | None,
    watcher_compatible: bool,
    provider_status: ProviderStatusResult | None,
) -> bool:
    """Spec §8.1: dirty worktree alone may still run impact against clean receipt baseline."""
    if evaluation.index_state != "stale" or evaluation.reason != "dirty_worktree":
        return False
    if not ctx.git_dirty:
        return False
    receipt = receipt_load.receipt if receipt_load.ok else None
    if receipt is None:
        return False
    if receipt.index_commit != ctx.observed_head:
        return False
    # Reconstruct readiness inputs and prove clean tree would be ready.
    node_count = int(provider_status.node_count) if provider_status else 0
    edge_count = int(provider_status.edge_count) if provider_status else 0
    if provider_status is None and binding.selected_project:
        for cand in binding.matching_candidates:
            if cand.name == binding.selected_project:
                node_count = cand.nodes
                edge_count = cand.edges
                break
    provider_index_status = _provider_index_status_str(provider_status)
    if provider_status is None and binding.selected_project and not binding.binding_conflict:
        if node_count + edge_count > 0:
            provider_index_status = "ready"
    clean_eval = evaluate_index_state(
        HetuReadinessInputs(
            provider_available=bool(ctx.provider_available),
            provider_compatible=bool(ctx.provider_compatible) and watcher_compatible,
            binding_conflict=binding.binding_conflict,
            provider_project=binding.selected_project,
            provider_index_status=provider_index_status,
            node_count=node_count,
            edge_count=edge_count,
            provider=ctx.provider_id,
            provider_version=ctx.provider_version,
            index_mode=ctx.index_mode,
            auto_watch_effective=auto_watch_effective,
            observed_head=ctx.observed_head,
            git_dirty=False,
            receipt=receipt,
            receipt_corrupt=False,
            receipt_missing=False,
        )
    )
    return clean_eval.index_state == "ready"


def _query_gate(
    ctx: HetuCommandContext,
    *,
    op: str,
    allow_dirty_impact: bool = False,
    since: str | None = None,
) -> tuple[
    BindingResolution,
    IndexStateEvaluation,
    ProviderStatusResult | None,
    bool | None,
    bool,
    IndexBindingReceiptLoadResult,
    list[dict[str, Any]],
    bool,
    str | None,
]:
    """Return evaluation + whether provider query is allowed.

    ``degraded_dirty_impact`` is True when dirty-only impact exception applies.
    """
    (
        binding,
        evaluation,
        provider_status,
        auto_watch_effective,
        watcher_compatible,
        receipt_load,
        actions,
    ) = _evaluate_with_context(ctx)

    if evaluation.index_state == "ready":
        return (
            binding,
            evaluation,
            provider_status,
            auto_watch_effective,
            watcher_compatible,
            receipt_load,
            actions,
            True,
            None,
        )

    if (
        op == "impact"
        and allow_dirty_impact
        and since is None
        and _dirty_only_impact_allowed(
            ctx=ctx,
            evaluation=evaluation,
            receipt_load=receipt_load,
            binding=binding,
            auto_watch_effective=auto_watch_effective,
            watcher_compatible=watcher_compatible,
            provider_status=provider_status,
        )
    ):
        return (
            binding,
            evaluation,
            provider_status,
            auto_watch_effective,
            watcher_compatible,
            receipt_load,
            actions,
            True,
            "degraded_dirty",
        )

    return (
        binding,
        evaluation,
        provider_status,
        auto_watch_effective,
        watcher_compatible,
        receipt_load,
        actions,
        False,
        None,
    )


def _blocked_query_envelope(
    *,
    command: str,
    ctx: HetuCommandContext,
    binding: BindingResolution,
    evaluation: IndexStateEvaluation,
    provider_status: ProviderStatusResult | None,
    auto_watch_effective: bool | None,
    watcher_compatible: bool,
    receipt_load: IndexBindingReceiptLoadResult,
    actions: list[dict[str, Any]],
    message: str | None = None,
) -> dict[str, Any]:
    data = _status_data(
        ctx=ctx,
        binding=binding,
        evaluation=evaluation,
        provider_status=provider_status,
        auto_watch_effective=auto_watch_effective,
        watcher_compatible=watcher_compatible,
        receipt_load=receipt_load,
    )
    data["query_blocked"] = True
    code = _index_state_code(evaluation)
    envelope = failure_envelope(
        command=command,
        code=code,
        message=message
        or (
            f"Hetu {command} blocked: index_state={evaluation.index_state} "
            f"(reason={evaluation.reason})"
        ),
        details=data,
        project_id=ctx.project_id,
        next_actions=actions,
    )
    # Mirror status fields at top-level data for agent convenience.
    envelope["data"] = data
    envelope["reason"] = evaluation.reason
    return attach_operation_result(envelope, mutation_intent=False, effects=[])


def _truncation_next_action(*, command: str, kind: str) -> dict[str, Any]:
    return next_action(
        code="HETU_RESULT_TRUNCATED",
        command=command,
        mutation=False,
        reason=(
            f"Result hit {kind} caps; narrow the query (smaller limit/depth/symbol scope) "
            "and re-run — partial set is disclosed via truncated/has_more"
        ),
    )


def _require_provider(ctx: HetuCommandContext) -> HetuProvider | None:
    return ctx.provider


def build_hetu_search(
    ctx: HetuCommandContext,
    *,
    query: str,
    limit: int | None = None,
) -> dict[str, Any]:
    """Bounded search. Requires index_state=ready. Never mutates."""
    q = str(query or "").strip()
    if not q:
        return attach_operation_result(
            failure_envelope(
                command="hetu.search",
                code="HETU_INVALID_QUERY",
                message="--query must be a non-empty string",
                project_id=ctx.project_id,
                next_actions=[
                    next_action(
                        code="HETU_INVALID_QUERY",
                        command='vibe hetu search --query "<symbol or path>" --json',
                        mutation=False,
                        reason="Provide a non-empty BM25 search query",
                    )
                ],
            ),
            mutation_intent=False,
            effects=[],
        )

    clamped = clamp_int(
        limit,
        default=ctx.search_limit_default,
        lo=1,
        hi=SEARCH_LIMIT_MAX,
    )
    (
        binding,
        evaluation,
        provider_status,
        auto_watch_effective,
        watcher_compatible,
        receipt_load,
        actions,
        allowed,
        _mode,
    ) = _query_gate(ctx, op="search")
    if not allowed:
        return _blocked_query_envelope(
            command="hetu.search",
            ctx=ctx,
            binding=binding,
            evaluation=evaluation,
            provider_status=provider_status,
            auto_watch_effective=auto_watch_effective,
            watcher_compatible=watcher_compatible,
            receipt_load=receipt_load,
            actions=actions,
        )

    provider = _require_provider(ctx)
    if provider is None:
        return attach_operation_result(
            failure_envelope(
                command="hetu.search",
                code="HETU_PROVIDER_UNAVAILABLE",
                message="No Hetu provider injected for search",
                project_id=ctx.project_id,
            ),
            mutation_intent=False,
            effects=[],
        )

    raw = provider.search(query=q, limit=clamped)
    capped = apply_search_caps(raw, repo_root=ctx.repo_root, limit=clamped)
    status_data = _status_data(
        ctx=ctx,
        binding=binding,
        evaluation=evaluation,
        provider_status=provider_status,
        auto_watch_effective=auto_watch_effective,
        watcher_compatible=watcher_compatible,
        receipt_load=receipt_load,
    )
    next_actions = list(actions)
    if capped.truncated or capped.has_more:
        next_actions.append(
            _truncation_next_action(
                command=f'vibe hetu search --query "{q}" --limit {max(1, clamped // 2)} --json',
                kind="search",
            )
        )
    envelope = success_envelope(
        command="hetu.search",
        project_id=ctx.project_id,
        mode="readonly",
        data={
            **status_data,
            "query": q,
            "limit": clamped,
            "result": capped.to_dict(),
        },
        next_actions=next_actions,
    )
    envelope["code"] = "HETU_SEARCH_OK"
    envelope["reason"] = None
    return attach_operation_result(envelope, mutation_intent=False, effects=[])


def build_hetu_trace(
    ctx: HetuCommandContext,
    *,
    symbol: str,
    direction: str = "both",
    depth: int | None = None,
) -> dict[str, Any]:
    """Bounded trace. Requires index_state=ready. Never mutates."""
    sym = str(symbol or "").strip()
    direction_s = str(direction or "").strip().lower()
    if not sym:
        return attach_operation_result(
            failure_envelope(
                command="hetu.trace",
                code="HETU_INVALID_SYMBOL",
                message="--symbol must be a non-empty qualified name",
                project_id=ctx.project_id,
                next_actions=[
                    next_action(
                        code="HETU_INVALID_SYMBOL",
                        command="vibe hetu trace --symbol <qualified_name> --json",
                        mutation=False,
                        reason="Provide a non-empty qualified symbol name",
                    )
                ],
            ),
            mutation_intent=False,
            effects=[],
        )
    if direction_s not in TRACE_DIRECTIONS:
        return attach_operation_result(
            failure_envelope(
                command="hetu.trace",
                code="HETU_INVALID_DIRECTION",
                message="--direction must be inbound|outbound|both",
                details={"direction": direction},
                project_id=ctx.project_id,
                next_actions=[
                    next_action(
                        code="HETU_INVALID_DIRECTION",
                        command=(
                            "vibe hetu trace --symbol <qualified_name> "
                            "--direction inbound|outbound|both --json"
                        ),
                        mutation=False,
                        reason="Use inbound, outbound, or both",
                    )
                ],
            ),
            mutation_intent=False,
            effects=[],
        )

    clamped_depth = clamp_int(
        depth,
        default=ctx.trace_depth_default,
        lo=1,
        hi=TRACE_DEPTH_MAX,
    )
    (
        binding,
        evaluation,
        provider_status,
        auto_watch_effective,
        watcher_compatible,
        receipt_load,
        actions,
        allowed,
        _mode,
    ) = _query_gate(ctx, op="trace")
    if not allowed:
        return _blocked_query_envelope(
            command="hetu.trace",
            ctx=ctx,
            binding=binding,
            evaluation=evaluation,
            provider_status=provider_status,
            auto_watch_effective=auto_watch_effective,
            watcher_compatible=watcher_compatible,
            receipt_load=receipt_load,
            actions=actions,
        )

    provider = _require_provider(ctx)
    if provider is None:
        return attach_operation_result(
            failure_envelope(
                command="hetu.trace",
                code="HETU_PROVIDER_UNAVAILABLE",
                message="No Hetu provider injected for trace",
                project_id=ctx.project_id,
            ),
            mutation_intent=False,
            effects=[],
        )

    raw = provider.trace(
        symbol=sym,
        direction=direction_s,  # type: ignore[arg-type]
        depth=clamped_depth,
    )
    capped = apply_trace_caps(raw, repo_root=ctx.repo_root)
    status_data = _status_data(
        ctx=ctx,
        binding=binding,
        evaluation=evaluation,
        provider_status=provider_status,
        auto_watch_effective=auto_watch_effective,
        watcher_compatible=watcher_compatible,
        receipt_load=receipt_load,
    )
    next_actions = list(actions)
    if capped.truncated:
        next_actions.append(
            _truncation_next_action(
                command=(
                    f"vibe hetu trace --symbol {sym} --direction {direction_s} "
                    f"--depth {max(1, clamped_depth - 1)} --json"
                ),
                kind="trace path/node/edge",
            )
        )
    envelope = success_envelope(
        command="hetu.trace",
        project_id=ctx.project_id,
        mode="readonly",
        data={
            **status_data,
            "symbol": sym,
            "direction": direction_s,
            "depth": clamped_depth,
            "caps": {
                "max_paths": TRACE_MAX_PATHS,
                "max_nodes": TRACE_MAX_NODES,
                "max_edges": TRACE_MAX_EDGES,
            },
            "result": capped.to_dict(),
        },
        next_actions=next_actions,
    )
    envelope["code"] = "HETU_TRACE_OK"
    envelope["reason"] = None
    return attach_operation_result(envelope, mutation_intent=False, effects=[])


def build_hetu_impact(
    ctx: HetuCommandContext,
    *,
    since: str | None = None,
    depth: int | None = None,
) -> dict[str, Any]:
    """Bounded impact. Ready required; dirty-only degraded exception when since is None."""
    since_s = None if since is None else str(since).strip() or None
    clamped_depth = clamp_int(
        depth,
        default=ctx.impact_depth_default,
        lo=1,
        hi=IMPACT_DEPTH_MAX,
    )
    (
        binding,
        evaluation,
        provider_status,
        auto_watch_effective,
        watcher_compatible,
        receipt_load,
        actions,
        allowed,
        mode,
    ) = _query_gate(
        ctx,
        op="impact",
        allow_dirty_impact=True,
        since=since_s,
    )
    if not allowed:
        return _blocked_query_envelope(
            command="hetu.impact",
            ctx=ctx,
            binding=binding,
            evaluation=evaluation,
            provider_status=provider_status,
            auto_watch_effective=auto_watch_effective,
            watcher_compatible=watcher_compatible,
            receipt_load=receipt_load,
            actions=actions,
        )

    # --since requires strict ready (not dirty-only degraded).
    if since_s is not None and evaluation.index_state != "ready":
        return _blocked_query_envelope(
            command="hetu.impact",
            ctx=ctx,
            binding=binding,
            evaluation=evaluation,
            provider_status=provider_status,
            auto_watch_effective=auto_watch_effective,
            watcher_compatible=watcher_compatible,
            receipt_load=receipt_load,
            actions=actions,
            message=(
                "Hetu impact --since requires strict ready index_state; "
                "dirty-only degraded mode applies only to current worktree impact"
            ),
        )

    provider = _require_provider(ctx)
    if provider is None:
        return attach_operation_result(
            failure_envelope(
                command="hetu.impact",
                code="HETU_PROVIDER_UNAVAILABLE",
                message="No Hetu provider injected for impact",
                project_id=ctx.project_id,
            ),
            mutation_intent=False,
            effects=[],
        )

    raw = provider.impact(since=since_s, depth=clamped_depth)
    capped = apply_impact_caps(raw, repo_root=ctx.repo_root)
    degraded = mode == "degraded_dirty"
    if degraded:
        capped = replace(
            capped,
            mode="degraded",
            freshness_assurance="clean_baseline_plus_worktree_diff",
            uncertainty=(
                "current dirty code is not itself represented as a fresh graph"
            ),
        )

    status_data = _status_data(
        ctx=ctx,
        binding=binding,
        evaluation=evaluation,
        provider_status=provider_status,
        auto_watch_effective=auto_watch_effective,
        watcher_compatible=watcher_compatible,
        receipt_load=receipt_load,
    )
    if degraded:
        status_data = {
            **status_data,
            "index": {
                **status_data["index"],
                "index_state": "stale",
                "freshness_assurance": "clean_baseline_plus_worktree_diff",
                "reason": "dirty_worktree",
            },
            "impact_mode": "degraded",
            "uncertainty": capped.uncertainty,
        }

    next_actions = list(actions)
    if capped.truncated:
        next_actions.append(
            _truncation_next_action(
                command=(
                    "vibe hetu impact "
                    + (f"--since {since_s} " if since_s else "")
                    + f"--depth {max(1, clamped_depth - 1)} --json"
                ),
                kind="impact symbol/edge",
            )
        )
    envelope = success_envelope(
        command="hetu.impact",
        project_id=ctx.project_id,
        mode="readonly",
        data={
            **status_data,
            "since": since_s,
            "depth": clamped_depth,
            "caps": {
                "max_symbols": IMPACT_MAX_SYMBOLS,
                "max_edges": IMPACT_MAX_EDGES,
            },
            "result": capped.to_dict(),
        },
        next_actions=next_actions,
    )
    envelope["code"] = "HETU_IMPACT_OK" if not degraded else "HETU_IMPACT_DEGRADED"
    envelope["reason"] = None if not degraded else "dirty_worktree"
    return attach_operation_result(envelope, mutation_intent=False, effects=[])


def build_hetu_architecture(ctx: HetuCommandContext) -> dict[str, Any]:
    """Bounded architecture. Requires index_state=ready. Never mutates."""
    (
        binding,
        evaluation,
        provider_status,
        auto_watch_effective,
        watcher_compatible,
        receipt_load,
        actions,
        allowed,
        _mode,
    ) = _query_gate(ctx, op="architecture")
    if not allowed:
        return _blocked_query_envelope(
            command="hetu.architecture",
            ctx=ctx,
            binding=binding,
            evaluation=evaluation,
            provider_status=provider_status,
            auto_watch_effective=auto_watch_effective,
            watcher_compatible=watcher_compatible,
            receipt_load=receipt_load,
            actions=actions,
        )

    provider = _require_provider(ctx)
    if provider is None:
        return attach_operation_result(
            failure_envelope(
                command="hetu.architecture",
                code="HETU_PROVIDER_UNAVAILABLE",
                message="No Hetu provider injected for architecture",
                project_id=ctx.project_id,
            ),
            mutation_intent=False,
            effects=[],
        )

    raw = provider.architecture()
    capped = apply_architecture_caps(raw, repo_root=ctx.repo_root)
    status_data = _status_data(
        ctx=ctx,
        binding=binding,
        evaluation=evaluation,
        provider_status=provider_status,
        auto_watch_effective=auto_watch_effective,
        watcher_compatible=watcher_compatible,
        receipt_load=receipt_load,
    )
    next_actions = list(actions)
    if capped.truncated:
        next_actions.append(
            _truncation_next_action(
                command="vibe hetu architecture --json",
                kind="architecture cluster/representative",
            )
        )
    envelope = success_envelope(
        command="hetu.architecture",
        project_id=ctx.project_id,
        mode="readonly",
        data={
            **status_data,
            "caps": {
                "max_clusters": ARCH_MAX_CLUSTERS,
                "max_representatives_per_cluster": ARCH_MAX_REPS_PER_CLUSTER,
            },
            "result": capped.to_dict(),
        },
        next_actions=next_actions,
    )
    envelope["code"] = "HETU_ARCHITECTURE_OK"
    envelope["reason"] = None
    return attach_operation_result(envelope, mutation_intent=False, effects=[])


def compute_reindex_plan_binding(plan: dict[str, Any]) -> str:
    """Deterministic sha256 over dry-run plan fields (Task 5/6 binding)."""
    canonical = json.dumps(plan, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_reindex_plan_core(
    ctx: HetuCommandContext,
    *,
    binding: BindingResolution,
    auto_watch_effective: bool | None,
    watcher_compatible: bool,
    observed_head: str,
    git_dirty: bool,
) -> dict[str, Any]:
    create_project = binding.selected_project is None and not binding.binding_conflict
    return {
        "schema": "vibe.hetu.reindex_plan.v1",
        "observed_head": observed_head,
        "git_dirty": bool(git_dirty),
        "provider": ctx.provider_id,
        "provider_version": ctx.provider_version,
        "provider_project": binding.selected_project,
        "configured_project": ctx.configured_project,
        "index_mode": ctx.index_mode,
        "persistence": False,
        "auto_watch_effective": auto_watch_effective,
        "watcher_state_observable": bool(ctx.watcher_state_observable) and watcher_compatible,
        "create_project_if_missing": create_project,
        "repo_realpath_hash": binding.repo_realpath_hash,
    }


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _apply_blocked(
    ctx: HetuCommandContext,
    *,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    next_actions: list[dict[str, Any]] | None = None,
    effects: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    envelope = failure_envelope(
        command="hetu.reindex",
        code=code,
        message=message,
        details={
            "dry_run": False,
            "apply": True,
            **(details or {}),
        },
        project_id=ctx.project_id,
        next_actions=next_actions or [],
    )
    return attach_operation_result(
        envelope,
        mutation_intent=True,
        effects=list(effects or []),
    )


def _resolve_binding_snapshot(ctx: HetuCommandContext) -> tuple[
    BindingResolution,
    bool | None,
    bool,
]:
    root = canonicalize_repo_root(ctx.repo_root)
    art = ctx.artifact if ctx.artifact is not None else detect_codebase_memory_artifact(root)
    projects: list[dict[str, Any]] = []
    if ctx.provider_available:
        try:
            projects = list(ctx.list_projects() or [])
        except Exception:
            projects = []
    binding = resolve_project_binding(
        repo_root=root,
        projects=projects,
        configured_project=ctx.configured_project,
        artifact=art,
    )
    auto_watch_effective, watcher_compatible, _reason = interpret_auto_watch(
        config_values=ctx.config_values() if ctx.provider_available else None,
        watcher_state_observable=ctx.watcher_state_observable,
    )
    return binding, auto_watch_effective, watcher_compatible


def build_hetu_reindex_dry_run(ctx: HetuCommandContext) -> dict[str, Any]:
    """Readonly reindex plan. Never calls index_repository. Emits plan binding hash."""
    (
        binding,
        evaluation,
        provider_status,
        auto_watch_effective,
        watcher_compatible,
        receipt_load,
        actions,
    ) = _evaluate_with_context(ctx)
    _assert_no_mutations(ctx)

    status_data = _status_data(
        ctx=ctx,
        binding=binding,
        evaluation=evaluation,
        provider_status=provider_status,
        auto_watch_effective=auto_watch_effective,
        watcher_compatible=watcher_compatible,
        receipt_load=receipt_load,
    )

    observed_head, git_dirty = ctx.current_git()
    plan_core = build_reindex_plan_core(
        ctx,
        binding=binding,
        auto_watch_effective=auto_watch_effective,
        watcher_compatible=watcher_compatible,
        observed_head=observed_head,
        git_dirty=git_dirty,
    )
    plan_binding = compute_reindex_plan_binding(plan_core)

    blocked_reasons: list[str] = []
    if not ctx.hetu_enabled:
        blocked_reasons.append("hetu_disabled")
    if not ctx.provider_available:
        blocked_reasons.append("provider_unavailable")
    if not (ctx.provider_compatible and watcher_compatible):
        blocked_reasons.append("provider_incompatible")
    if binding.binding_conflict:
        blocked_reasons.append("binding_conflict")
    if git_dirty:
        blocked_reasons.append("git_dirty")
    if auto_watch_effective is not False:
        blocked_reasons.append("auto_watch_not_false")
    if not watcher_compatible:
        blocked_reasons.append("watcher_unobservable")

    apply_ready = len(blocked_reasons) == 0
    plan_actions = list(actions)
    if apply_ready:
        plan_actions = [
            next_action(
                code="HETU_REINDEX_APPLY",
                command=(
                    "vibe hetu reindex --apply "
                    f"--expect-plan-binding {plan_binding} "
                    "--confirm-hetu-reindex-apply --json"
                ),
                mutation=True,
                reason=(
                    "Dry-run plan is current; confirmed apply writes the "
                    "IndexBindingReceipt after provider index_repository"
                ),
            )
        ] + plan_actions
    elif "git_dirty" in blocked_reasons:
        plan_actions.insert(
            0,
            next_action(
                code="HETU_REINDEX_REQUIRES_CLEAN_GIT",
                command="git status --short",
                mutation=False,
                reason="Reindex apply requires a clean Git working tree",
            ),
        )

    # Ensure dry-run never called reindex on fake provider.
    if ctx.provider is not None and isinstance(ctx.provider, FakeHetuProvider):
        if any(c[0] == "reindex" for c in ctx.provider.calls):
            raise RuntimeError("Hetu reindex dry-run must not call provider.reindex")

    envelope = success_envelope(
        command="hetu.reindex",
        project_id=ctx.project_id,
        mode="dry-run",
        data={
            **status_data,
            "dry_run": True,
            "apply": False,
            "apply_ready": apply_ready,
            "blocked_reasons": blocked_reasons,
            "plan": {
                **plan_core,
                "plan_binding": plan_binding,
                "expect_plan_binding_flag": "--expect-plan-binding",
                "confirm_flag": "--confirm-hetu-reindex-apply",
            },
        },
        next_actions=plan_actions,
    )
    envelope["code"] = "HETU_REINDEX_DRY_RUN"
    envelope["reason"] = None if apply_ready else (
        blocked_reasons[0] if blocked_reasons else "not_apply_ready"
    )
    return attach_operation_result(envelope, mutation_intent=False, effects=[])


def build_hetu_reindex_apply(
    ctx: HetuCommandContext,
    *,
    expect_plan_binding: str | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    """Confirmed reindex apply (Task 6). Never requires product_ready or env dual gate."""
    dry_run_hint = [
        next_action(
            code="HETU_REINDEX_DRY_RUN",
            command="vibe hetu reindex --dry-run --json",
            mutation=False,
            reason="Preview reindex plan and plan_binding before confirmed apply",
        )
    ]

    if not ctx.hetu_enabled:
        return _apply_blocked(
            ctx,
            code="HETU_DISABLED",
            message="components.hetu.enabled is false; reindex apply is blocked",
            details={"blocked_reason": "hetu_disabled"},
            next_actions=[
                next_action(
                    code="ENABLE_HETU_CONFIG",
                    command="vibe doctor --json",
                    mutation=False,
                    reason="Enable Hetu in control.yaml before reindex apply",
                )
            ],
        )

    if not confirm:
        return _apply_blocked(
            ctx,
            code="HETU_REINDEX_CONFIRMATION_REQUIRED",
            message=(
                "Reindex apply requires explicit --confirm-hetu-reindex-apply "
                "(no VIBE_HETU_* environment dual gate)"
            ),
            details={
                "blocked_reason": "confirmation_absent",
                "confirm_flag": "--confirm-hetu-reindex-apply",
                "expect_plan_binding": expect_plan_binding,
            },
            next_actions=dry_run_hint,
        )

    expect = str(expect_plan_binding or "").strip()
    if not expect:
        return _apply_blocked(
            ctx,
            code="HETU_REINDEX_EXPECT_PLAN_BINDING_REQUIRED",
            message="Reindex apply requires --expect-plan-binding <sha256> from dry-run",
            details={
                "blocked_reason": "expect_plan_binding_missing",
                "expect_plan_binding_flag": "--expect-plan-binding",
            },
            next_actions=dry_run_hint,
        )

    if not ctx.provider_available or ctx.provider is None:
        return _apply_blocked(
            ctx,
            code="HETU_PROVIDER_UNAVAILABLE",
            message="Hetu provider is unavailable; cannot reindex",
            details={"blocked_reason": "provider_unavailable"},
            next_actions=dry_run_hint,
        )

    # Watcher observability / false precheck BEFORE any provider mutation.
    binding, auto_watch_effective, watcher_compatible = _resolve_binding_snapshot(ctx)
    if not ctx.provider_compatible or not watcher_compatible:
        return _apply_blocked(
            ctx,
            code="HETU_PROVIDER_INCOMPATIBLE",
            message=(
                "Hetu provider is incompatible or watcher state is unobservable; "
                "blocked before provider mutation"
            ),
            details={
                "blocked_reason": (
                    "watcher_unobservable"
                    if not watcher_compatible
                    else "provider_incompatible"
                ),
                "watcher_state_observable": bool(ctx.watcher_state_observable)
                and watcher_compatible,
                "auto_watch_effective": auto_watch_effective,
            },
            next_actions=dry_run_hint,
        )

    if auto_watch_effective is not False:
        return _apply_blocked(
            ctx,
            code="HETU_WATCHER_NOT_FALSE",
            message=(
                "Effective auto_watch must be false before reindex mutation; "
                "Vibe will not change provider config"
            ),
            details={
                "blocked_reason": (
                    "auto_watch_unknown"
                    if auto_watch_effective is None
                    else "auto_watch_true"
                ),
                "auto_watch_effective": auto_watch_effective,
            },
            next_actions=[
                next_action(
                    code="HETU_AUTO_WATCH_MUST_BE_FALSE",
                    command="codebase-memory-mcp config set auto_watch false",
                    mutation=True,
                    reason=(
                        "Owner-managed watcher disable recommended; "
                        "Vibe does not run this command"
                    ),
                )
            ],
        )

    if binding.binding_conflict:
        return _apply_blocked(
            ctx,
            code="HETU_BINDING_CONFLICT",
            message=binding.message or "Ambiguous provider project binding blocks reindex",
            details={
                "blocked_reason": "binding_conflict",
                "binding": binding.to_public_dict(),
            },
            next_actions=[
                next_action(
                    code="HETU_BINDING_CONFLICT",
                    command="vibe config validate --json",
                    mutation=False,
                    reason=(
                        "Set hetu.codebase_memory.project to the exact provider "
                        "project before reindex apply"
                    ),
                )
            ],
        )

    observed_head, git_dirty = ctx.current_git()
    ctx.observed_head = observed_head
    ctx.git_dirty = git_dirty
    if git_dirty:
        return _apply_blocked(
            ctx,
            code="HETU_REINDEX_GIT_DIRTY",
            message="Reindex apply requires a clean Git working tree",
            details={"blocked_reason": "git_dirty", "observed_head": observed_head},
            next_actions=[
                next_action(
                    code="HETU_REINDEX_REQUIRES_CLEAN_GIT",
                    command="git status --short",
                    mutation=False,
                    reason="Commit or stash local changes before confirmed reindex",
                )
            ],
        )

    plan_core = build_reindex_plan_core(
        ctx,
        binding=binding,
        auto_watch_effective=auto_watch_effective,
        watcher_compatible=watcher_compatible,
        observed_head=observed_head,
        git_dirty=git_dirty,
    )
    current_binding = compute_reindex_plan_binding(plan_core)
    if expect != current_binding:
        return _apply_blocked(
            ctx,
            code="HETU_REINDEX_PLAN_BINDING_MISMATCH",
            message=(
                "Current reindex plan binding does not match --expect-plan-binding; "
                "re-run dry-run and retry apply"
            ),
            details={
                "blocked_reason": "plan_binding_mismatch",
                "expect_plan_binding": expect,
                "current_plan_binding": current_binding,
                "plan": plan_core,
            },
            next_actions=dry_run_hint,
        )

    # --- provider mutation ---
    ctx.record_mutation("reindex")
    try:
        reindex_result = ctx.provider.reindex(
            mode="fast",
            persistence=False,
            index_commit=observed_head,
        )
    except Exception as exc:  # noqa: BLE001 - normalize provider crash before write
        return _apply_blocked(
            ctx,
            code="HETU_REINDEX_PROVIDER_FAILED",
            message=f"Provider reindex failed before receipt write: {exc}",
            details={"blocked_reason": "provider_failure_before_write"},
            next_actions=dry_run_hint,
        )

    if not isinstance(reindex_result, ReindexResult):
        return _apply_blocked(
            ctx,
            code="HETU_REINDEX_PROVIDER_FAILED",
            message="Provider reindex returned an unexpected result",
            details={"blocked_reason": "provider_failure_before_write"},
            next_actions=dry_run_hint,
        )

    if not reindex_result.ok or not reindex_result.mutation_performed:
        return _apply_blocked(
            ctx,
            code="HETU_REINDEX_PROVIDER_FAILED",
            message=reindex_result.message
            or "Provider reindex failed before receipt write",
            details={
                "blocked_reason": "provider_failure_before_write",
                "provider_reason": reindex_result.reason,
                "reindex": reindex_result.to_dict(),
            },
            next_actions=dry_run_hint,
        )

    effects: list[dict[str, Any]] = [dict(EFFECT_HETU_INDEX_REPOSITORY)]

    def _partial(
        *,
        code: str,
        message: str,
        blocked_reason: str,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return _apply_blocked(
            ctx,
            code=code,
            message=message,
            details={
                "blocked_reason": blocked_reason,
                "index_state": "unverifiable",
                "plan_binding": current_binding,
                "reindex": reindex_result.to_dict(),
                "receipt_written": False,
                **(extra or {}),
            },
            next_actions=dry_run_hint,
            effects=effects,
        )

    # Post-index: exact-root project resolution (zero-candidate create allowed).
    post_binding, post_watch, post_watcher_compatible = _resolve_binding_snapshot(ctx)
    if post_binding.binding_conflict or post_binding.selected_project is None:
        return _partial(
            code="HETU_REINDEX_POST_BINDING_FAILED",
            message=(
                post_binding.message
                or "Post-index provider project resolution failed "
                "(missing or multiple exact-root candidates)"
            ),
            blocked_reason=(
                "post_index_multiple_candidates"
                if post_binding.binding_conflict
                else "post_index_project_missing"
            ),
            extra={"binding": post_binding.to_public_dict()},
        )

    # Non-empty ready provider status.
    provider_status: ProviderStatusResult | None = None
    try:
        if ctx.index_status is not None:
            provider_status = ctx.index_status(post_binding.selected_project)
        else:
            provider_status = ctx.provider.status()
    except Exception as exc:  # noqa: BLE001
        return _partial(
            code="HETU_REINDEX_STATUS_FAILED",
            message=f"Post-index provider status failed: {exc}",
            blocked_reason="post_index_status_timeout",
            extra={"status_error": str(exc)},
        )

    if (
        provider_status is None
        or provider_status.index_state != "ready"
        or (int(provider_status.node_count) + int(provider_status.edge_count)) <= 0
    ):
        return _partial(
            code="HETU_REINDEX_STATUS_FAILED",
            message="Post-index provider status is not ready with a non-empty graph",
            blocked_reason="post_index_empty_or_not_ready",
            extra={
                "provider_status": None
                if provider_status is None
                else provider_status.to_dict()
            },
        )

    # Before/after HEAD race + clean tree.
    after_head, after_dirty = ctx.current_git()
    if after_dirty or after_head != observed_head:
        return _partial(
            code="HETU_REINDEX_GIT_RACE",
            message=(
                "Git HEAD or dirty state changed during reindex; "
                "receipt not written (index left unverifiable)"
            ),
            blocked_reason="git_race",
            extra={
                "base_head": observed_head,
                "after_head": after_head,
                "after_dirty": after_dirty,
            },
        )

    # Watcher recheck after mutation.
    if not post_watcher_compatible or post_watch is not False:
        return _partial(
            code="HETU_REINDEX_WATCHER_MISMATCH",
            message=(
                "Effective watcher/config no longer proves auto_watch=false after reindex; "
                "receipt not written"
            ),
            blocked_reason="watcher_or_config_mismatch",
            extra={
                "auto_watch_effective": post_watch,
                "watcher_state_observable": post_watcher_compatible,
            },
        )

    receipt = IndexBindingReceipt(
        schema=RECEIPT_SCHEMA,
        repo_identity=ctx.project_id,
        repo_realpath_hash=compute_repo_realpath_hash(ctx.repo_root),
        provider=ctx.provider_id,
        provider_project=str(post_binding.selected_project),
        provider_version=str(
            provider_status.provider_version
            or ctx.provider_version
            or reindex_result.provider_version
            or "unknown"
        ),
        index_mode=ctx.index_mode,
        persistence=False,
        index_commit=observed_head,
        git_status_short_empty=True,
        auto_watch_effective=False,
        node_count=int(provider_status.node_count),
        edge_count=int(provider_status.edge_count),
        bound_at=_utc_now_iso(),
    )
    receipt = receipt.with_binding_hash(compute_binding_hash(receipt))

    writer = ctx.write_receipt or write_index_binding_receipt
    try:
        writer(receipt, home=ctx.state_home, provider=ctx.provider_id)
    except Exception as exc:  # noqa: BLE001
        return _partial(
            code="HETU_REINDEX_RECEIPT_WRITE_FAILED",
            message=f"Provider reindex succeeded but receipt write failed: {exc}",
            blocked_reason="receipt_write_failed",
            extra={"receipt_error": str(exc)},
        )

    effects.append(dict(EFFECT_HETU_INDEX_BINDING))
    envelope = success_envelope(
        command="hetu.reindex",
        project_id=ctx.project_id,
        mode="apply",
        data={
            "dry_run": False,
            "apply": True,
            "apply_ready": True,
            "plan_binding": current_binding,
            "plan": plan_core,
            "reindex": reindex_result.to_dict(),
            "receipt": {
                "written": True,
                "relative_path": f"{ctx.project_id}/hetu/{ctx.provider_id}/index-binding.json",
                "binding_hash": receipt.binding_hash,
                "index_commit": receipt.index_commit,
                "provider_project": receipt.provider_project,
            },
            "git": {"observed_head": observed_head, "dirty": False},
            "index": {
                "index_commit": receipt.index_commit,
                "index_state": "ready",
                "freshness_assurance": "strict_receipt",
                "node_count": receipt.node_count,
                "edge_count": receipt.edge_count,
            },
            "provider": {
                "id": ctx.provider_id,
                "version": receipt.provider_version,
                "project": receipt.provider_project,
                "auto_watch_effective": False,
            },
        },
        next_actions=[
            next_action(
                code="HETU_STATUS",
                command="vibe hetu status --json",
                mutation=False,
                reason="Verify Hetu index_state=ready after confirmed reindex",
            )
        ],
    )
    envelope["code"] = "HETU_REINDEX_APPLIED"
    envelope["reason"] = None
    return attach_operation_result(envelope, mutation_intent=True, effects=effects)


def build_hetu_reindex_apply_stub(
    ctx: HetuCommandContext,
    *,
    expect_plan_binding: str | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    """Backward-compatible alias; Task 6 implements real apply."""
    return build_hetu_reindex_apply(
        ctx,
        expect_plan_binding=expect_plan_binding,
        confirm=confirm,
    )
