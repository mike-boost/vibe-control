"""Hetu product_ready / closeout participation (Task 7).

Exit criterion: no state may report hetu.ready=false while full configured-system
product_ready=true. Closeout never auto-reindexes.
"""

from __future__ import annotations

from pathlib import Path

from vibe_control.closeout_runner import run_closeout
from vibe_control.components import (
    COMPONENT_CATALOG,
    enrich_capability_readiness,
    resolve_component_runtime,
)
from vibe_control.product_readiness import (
    build_probe_from_parts,
    finalize_product_ready,
    readiness_next_actions,
)


def _base_components(*, hetu_enabled: bool = False) -> dict:
    """Knowledge/task disabled so Hetu gate is isolated."""
    resolved = resolve_component_runtime(
        {
            "knowledge": {"enabled": False},
            "task": {"enabled": False},
            "hetu": {"enabled": hetu_enabled},
            "sdd": {"enabled": False},
            "tdd": {"enabled": False},
        }
    )
    assert resolved["config_ok"] is True
    return resolved["components"]


def _ready_probe_parts(**overrides):
    base = dict(
        knowledge_available=False,
        knowledge_target_ok=False,
        sync_state="unavailable",
        task_available=False,
        task_mode="unavailable",
        task_readable=False,
        task_cache_current=True,
        components=_base_components(hetu_enabled=False),
        hetu_enabled=False,
        hetu_available=False,
        hetu_ready=False,
        hetu_index_state=None,
        hetu_provider=None,
        hetu_index_commit=None,
        hetu_observed_head=None,
    )
    base.update(overrides)
    return base


def _hetu_status_fixture(
    *,
    enabled: bool = True,
    ready: bool = True,
    index_state: str = "ready",
    blocked: list[str] | None = None,
    product_ready: bool | None = None,
):
    comps = _base_components(hetu_enabled=enabled)
    if enabled:
        comps = enrich_capability_readiness(
            comps,
            hetu_available=ready,
            hetu_ready=ready,
            hetu_index_state=index_state,
        )
    pr = product_ready if product_ready is not None else (ready or not enabled)
    return {
        "project_id": "vibe-control",
        "product_ready": pr,
        "blocked_reasons": list(blocked or ([] if pr else [f"hetu_index_{index_state}"])),
        "closeout_state": "no_ssot_change_product_ready",
        "closeout_complete": pr,
        "provider_sync_required": False,
        "config_ok": True,
        "components": comps,
        "capability_profile": {
            "knowledge_enabled": False,
            "task_enabled": False,
            "hetu_enabled": enabled,
        },
        "hetu_enabled": enabled,
        "hetu_available": ready if enabled else False,
        "hetu_ready": ready if enabled else None,
        "hetu_index_state": index_state if enabled else None,
        "hetu_provider": "codebase_memory" if enabled else None,
        "hetu_index_commit": "abc" if ready else None,
        "hetu_observed_head": "abc" if enabled else None,
        "knowledge_provider": {
            "available": True,
            "target_ok": True,
            "sync_state": "synced",
            "provider_ask_clean": True,
            "ask_hygiene": {
                "provider_ask_clean": True,
                "required_updates_count": 0,
                "candidate_count": 0,
                "orphan_managed_count": 0,
            },
        },
        "task_provider": {
            "available": True,
            "mode": "readonly",
            "readable": True,
            "ready_queue_available": True,
        },
        "task_cache_current": True,
        "task_cache": {
            "task_cache_current": True,
            "reconcile_counts": {
                "matched": 1,
                "missing": 0,
                "stale": 0,
                "duplicate": 0,
                "conflict": 0,
                "unmanaged": 0,
            },
            "apply_plan_counts": {"create": 0, "update": 0, "skip": 0, "blocked": 0},
            "safe_task_convergence_allowed": False,
            "task_cache_reset_required": False,
        },
        "chatgpt_project_sources": {
            "product_closeout_gate": False,
            "owner_manual_external_copy": True,
            "advisor_files": [],
        },
        "warnings": [],
        "next_actions": [],
    }


def _closeout_deps(status: dict):
    apply_calls: list[str] = []

    def integration(_root: Path, **_kwargs):
        return dict(status)

    def next_selection(*, repo_root: Path):  # noqa: ARG001
        return {
            "next_actionable_task": "roadmap.test_closeout",
            "no_actionable_next_task": False,
        }

    return {
        "git_status_short": lambda _r: "",
        "build_integration_status": integration,
        "plan_sync_dry_run": lambda _r: {
            "ok": True,
            "sync_state": "synced",
            "required_updates_count": 0,
            "operations": [{"op": "already_current", "doc_id": "a"}],
        },
        "apply_knowledge_sync": lambda _r: apply_calls.append("knowledge") or {"ok": True},
        "desired_doc_ids": lambda _r: {"a"},
        "next_actionable_selection": next_selection,
        "_apply_calls": apply_calls,
    }


# --- Catalog / defaults ---


def test_hetu_catalog_supported_default_disabled():
    assert "hetu" in COMPONENT_CATALOG
    meta = COMPONENT_CATALOG["hetu"]
    assert meta["support_state"] == "supported"
    assert meta["default_enabled"] is False
    assert meta["readiness_role"] == "optional_when_disabled"
    assert meta["bound_provider"] == "codebase_memory"
    assert meta["existing_runtime"] is True
    resolved = resolve_component_runtime(None)
    assert resolved["config_ok"] is True
    assert resolved["components"]["hetu"]["enabled"] is False
    assert resolved["capability_profile"]["hetu_enabled"] is False


def test_fresh_resolve_with_explicit_hetu_disabled_ok():
    resolved = resolve_component_runtime({"hetu": {"enabled": False}})
    assert resolved["config_ok"] is True
    assert resolved["components"]["hetu"]["enabled"] is False


# --- Disabled: no readiness effect ---


def test_hetu_disabled_does_not_fail_product_ready():
    probe = build_probe_from_parts(**_ready_probe_parts())
    assert probe.product_ready is True
    assert probe.hetu_enabled is False
    assert probe.blocked_reasons == []
    assert not any(r.startswith("hetu_") for r in probe.blocked_reasons)
    assert probe.components["hetu"]["enabled"] is False
    assert probe.components["hetu"]["ready"] is None
    assert probe.components["hetu"]["skipped"] is True


def test_hetu_disabled_ignores_non_ready_probe_fields():
    """Even if probe fields look bad, disabled Hetu must not block product_ready."""
    probe = build_probe_from_parts(
        **_ready_probe_parts(
            hetu_enabled=False,
            hetu_available=False,
            hetu_ready=False,
            hetu_index_state="stale",
            hetu_provider="codebase_memory",
        )
    )
    assert probe.product_ready is True
    assert probe.blocked_reasons == []


# --- Enabled ready ---


def test_hetu_enabled_ready_passes_product_ready():
    comps = _base_components(hetu_enabled=True)
    probe = build_probe_from_parts(
        **_ready_probe_parts(
            components=comps,
            hetu_enabled=True,
            hetu_available=True,
            hetu_ready=True,
            hetu_index_state="ready",
            hetu_provider="codebase_memory",
            hetu_index_commit="deadbeef",
            hetu_observed_head="deadbeef",
        )
    )
    assert probe.product_ready is True
    assert probe.blocked_reasons == []
    assert probe.hetu_ready is True
    assert probe.components["hetu"]["ready"] is True
    d = probe.to_dict()
    assert d["capability_profile"]["hetu_enabled"] is True
    assert d["hetu"]["enabled"] is True
    assert d["hetu"]["ready"] is True
    assert d["hetu"]["index_state"] == "ready"


# --- Enabled non-ready states block ---


def test_hetu_enabled_each_non_ready_blocks_product_ready():
    cases = [
        ("unavailable", False, "hetu_provider_unavailable", None),
        ("unavailable", False, "hetu_provider_incompatible", "provider_incompatible"),
        ("missing", False, "hetu_index_missing", None),
        ("indexing", False, "hetu_index_indexing", None),
        ("stale", True, "hetu_index_stale", None),
        ("unverifiable", True, "hetu_index_unverifiable", None),
        ("conflict_needs_choice", True, "hetu_binding_conflict", None),
    ]
    for index_state, available, reason, reason_detail in cases:
        comps = _base_components(hetu_enabled=True)
        probe = build_probe_from_parts(
            **_ready_probe_parts(
                components=comps,
                hetu_enabled=True,
                hetu_available=available,
                hetu_ready=False,
                hetu_index_state=index_state,
                hetu_provider="codebase_memory",
                hetu_block_reason=reason_detail,
            )
        )
        assert probe.product_ready is False, index_state
        assert reason in probe.blocked_reasons, (index_state, probe.blocked_reasons)
        assert probe.hetu_ready is False
        assert probe.components["hetu"]["ready"] is False
        # Exit criterion: never green while hetu not ready.
        assert not (probe.hetu_ready is False and probe.product_ready is True)


def test_exit_criterion_no_product_ready_with_hetu_not_ready():
    comps = _base_components(hetu_enabled=True)
    for index_state in (
        "missing",
        "indexing",
        "stale",
        "unverifiable",
        "unavailable",
        "conflict_needs_choice",
    ):
        probe = build_probe_from_parts(
            **_ready_probe_parts(
                components=comps,
                hetu_enabled=True,
                hetu_available=index_state not in {"unavailable"},
                hetu_ready=False,
                hetu_index_state=index_state,
                hetu_provider="codebase_memory",
            )
        )
        assert probe.hetu_ready is False
        assert probe.product_ready is False


def test_hetu_readiness_next_actions_when_blocked():
    comps = _base_components(hetu_enabled=True)
    probe = build_probe_from_parts(
        **_ready_probe_parts(
            components=comps,
            hetu_enabled=True,
            hetu_available=True,
            hetu_ready=False,
            hetu_index_state="stale",
            hetu_provider="codebase_memory",
        )
    )
    actions = readiness_next_actions(probe)
    codes = [a.get("code") for a in actions if isinstance(a, dict)]
    assert "HETU_STATUS" in codes or "HETU_REINDEX_DRY_RUN" in codes
    for a in actions:
        if isinstance(a, dict) and a.get("code") in {
            "HETU_STATUS",
            "HETU_DOCTOR",
            "HETU_REINDEX_DRY_RUN",
        }:
            assert a.get("mutation") is False
            assert "hetu" in str(a.get("command") or "")


# --- Closeout ---


def test_closeout_disabled_hetu_unaffected():
    status = _hetu_status_fixture(enabled=False, ready=False, index_state="missing", blocked=[])
    status["product_ready"] = True
    status["blocked_reasons"] = []
    deps = _closeout_deps(status)
    env = run_closeout(repo_root=Path("."), apply=False, deps=deps)
    assert env["ok"] is True
    data = env["data"]
    assert data["closeout_complete"] is True
    assert not any("hetu" in str(r) for r in data.get("blocked_reasons") or [])
    assert deps["_apply_calls"] == []


def test_closeout_enabled_ready_hetu_passes():
    status = _hetu_status_fixture(enabled=True, ready=True, index_state="ready", blocked=[])
    deps = _closeout_deps(status)
    env = run_closeout(repo_root=Path("."), apply=False, deps=deps)
    assert env["ok"] is True
    assert env["data"]["closeout_complete"] is True
    assert deps["_apply_calls"] == []


def test_closeout_enabled_non_ready_blocks_and_never_reindexes():
    for index_state, reason in (
        ("stale", "hetu_index_stale"),
        ("missing", "hetu_index_missing"),
        ("unverifiable", "hetu_index_unverifiable"),
        ("unavailable", "hetu_provider_unavailable"),
        ("conflict_needs_choice", "hetu_binding_conflict"),
    ):
        status = _hetu_status_fixture(
            enabled=True,
            ready=False,
            index_state=index_state,
            blocked=[reason],
            product_ready=False,
        )
        deps = _closeout_deps(status)
        env = run_closeout(repo_root=Path("."), apply=False, deps=deps)
        data = env["data"]
        assert data["closeout_complete"] is False, index_state
        assert reason in data["blocked_reasons"] or any(
            "hetu" in str(r) for r in data["blocked_reasons"]
        ), (index_state, data["blocked_reasons"])
        codes = [a.get("code") for a in data.get("next_actions") or []]
        assert any(
            c in {"HETU_STATUS", "HETU_DOCTOR", "HETU_REINDEX_DRY_RUN"} for c in codes
        ), codes
        # Never auto-reindex / never knowledge apply as a substitute.
        assert deps["_apply_calls"] == []
        cmds = " ".join(str(a.get("command") or "") for a in data.get("next_actions") or [])
        assert "--apply" not in cmds or "reindex --apply" not in cmds
        assert "hetu reindex --apply" not in cmds


def test_finalize_maps_index_states_to_blocked_reasons():
    """Direct finalize path (same mapping closeout/integration rely on)."""
    from vibe_control.product_readiness import ProviderProbeResult

    comps = _base_components(hetu_enabled=True)
    probe = ProviderProbeResult(
        components=comps,
        config_ok=True,
        hetu_enabled=True,
        hetu_available=True,
        hetu_ready=False,
        hetu_index_state="stale",
        hetu_provider="codebase_memory",
    )
    finalize_product_ready(probe)
    assert probe.product_ready is False
    assert "hetu_index_stale" in probe.blocked_reasons
