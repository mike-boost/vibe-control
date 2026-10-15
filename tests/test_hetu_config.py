"""Hetu config schema/defaults/clamps (Task 2) — parsing does not authorize enablement."""

from __future__ import annotations

from vibe_control.components import (
    COMPONENT_CATALOG,
    evaluate_provider_integration_request,
    resolve_component_runtime,
)
from vibe_control.config import (
    DEFAULT_HETU_CONFIG,
    parse_hetu_config,
    validate_config_dict,
    validate_hetu_config_dict,
)


def _minimal_valid_raw(**overrides):
    raw = {
        "project": {"id": "demo", "name": "Demo"},
        "knowledge": {
            "provider": "local_fts",
            "fallback_provider": "repo",
            "max_sources": 50,
            "warn_sources": 40,
            "authoritative_statuses": ["active"],
        },
        "specs": {"registry": "docs/project/spec-registry.yml", "required_fields": ["id"]},
        "tasks": {"provider": "beads"},
    }
    raw.update(overrides)
    return raw


def test_defaults_match_spec():
    cfg = parse_hetu_config(None)
    assert cfg.provider == "codebase_memory"
    assert cfg.freshness_policy == "strict"
    assert cfg.codebase_memory.binary == "codebase-memory-mcp"
    assert cfg.codebase_memory.project is None
    assert cfg.codebase_memory.index_mode == "fast"
    assert cfg.codebase_memory.search_limit == 20
    assert cfg.codebase_memory.trace_depth == 3
    assert cfg.codebase_memory.impact_depth == 2
    assert cfg.codebase_memory.query_timeout_sec == 30
    assert cfg.codebase_memory.reindex_timeout_sec == 600
    assert DEFAULT_HETU_CONFIG.provider == "codebase_memory"


def test_absent_hetu_section_is_valid_and_uses_defaults():
    raw = _minimal_valid_raw()
    assert validate_config_dict(raw) == []
    assert validate_hetu_config_dict(None) == []
    assert validate_hetu_config_dict({}) == []
    cfg = parse_hetu_config({})
    assert cfg.to_dict()["provider"] == "codebase_memory"
    assert cfg.to_dict()["codebase_memory"]["search_limit"] == 20


def test_explicit_valid_hetu_section_parses():
    raw = {
        "provider": "codebase_memory",
        "freshness_policy": "strict",
        "codebase_memory": {
            "binary": "/opt/codebase-memory-mcp",
            "project": "demo-proj",
            "index_mode": "fast",
            "search_limit": 40,
            "trace_depth": 5,
            "impact_depth": 1,
            "query_timeout_sec": 60,
            "reindex_timeout_sec": 900,
        },
    }
    assert validate_hetu_config_dict(raw) == []
    cfg = parse_hetu_config(raw)
    assert cfg.codebase_memory.binary == "/opt/codebase-memory-mcp"
    assert cfg.codebase_memory.project == "demo-proj"
    assert cfg.codebase_memory.search_limit == 40
    assert cfg.codebase_memory.reindex_timeout_sec == 900


def test_unknown_provider_fail_closed():
    errors = validate_hetu_config_dict({"provider": "codegraph"})
    assert errors
    assert any("provider" in e for e in errors)
    errors2 = validate_hetu_config_dict({"provider": "unknown_tool"})
    assert errors2


def test_fake_provider_allowed_for_tests_only():
    assert validate_hetu_config_dict({"provider": "fake"}) == []
    cfg = parse_hetu_config({"provider": "fake"})
    assert cfg.provider == "fake"


def test_unsupported_index_mode_fail_closed():
    errors = validate_hetu_config_dict(
        {"codebase_memory": {"index_mode": "semantic"}}
    )
    assert errors
    assert any("index_mode" in e for e in errors)


def test_unsupported_freshness_policy_fail_closed():
    errors = validate_hetu_config_dict({"freshness_policy": "allow_dirty_query"})
    assert errors
    assert any("freshness_policy" in e for e in errors)


def test_unsafe_limits_and_timeouts_fail_closed():
    cases = [
        {"codebase_memory": {"search_limit": 0}},
        {"codebase_memory": {"search_limit": 51}},
        {"codebase_memory": {"trace_depth": 0}},
        {"codebase_memory": {"trace_depth": 6}},
        {"codebase_memory": {"impact_depth": 0}},
        {"codebase_memory": {"impact_depth": 6}},
        {"codebase_memory": {"query_timeout_sec": 4}},
        {"codebase_memory": {"query_timeout_sec": 121}},
        {"codebase_memory": {"reindex_timeout_sec": 29}},
        {"codebase_memory": {"reindex_timeout_sec": 3601}},
    ]
    for raw in cases:
        errors = validate_hetu_config_dict(raw)
        assert errors, f"expected fail-closed for {raw}"


def test_boundary_clamps_accepted():
    for raw in (
        {"codebase_memory": {"search_limit": 1}},
        {"codebase_memory": {"search_limit": 50}},
        {"codebase_memory": {"trace_depth": 1}},
        {"codebase_memory": {"trace_depth": 5}},
        {"codebase_memory": {"impact_depth": 1}},
        {"codebase_memory": {"impact_depth": 5}},
        {"codebase_memory": {"query_timeout_sec": 5}},
        {"codebase_memory": {"query_timeout_sec": 120}},
        {"codebase_memory": {"reindex_timeout_sec": 30}},
        {"codebase_memory": {"reindex_timeout_sec": 3600}},
    ):
        assert validate_hetu_config_dict(raw) == [], raw


def test_invalid_hetu_section_type_and_nested_mapping():
    assert validate_hetu_config_dict("nope")  # type: ignore[arg-type]
    assert validate_hetu_config_dict({"codebase_memory": "nope"})


def test_validate_config_dict_includes_hetu_errors():
    raw = _minimal_valid_raw(hetu={"provider": "codegraph"})
    errors = validate_config_dict(raw)
    assert any("hetu" in e for e in errors)


def test_provider_scoped_component_id_fail_closed():
    result = evaluate_provider_integration_request(
        component_id="hetu.codebase_memory",
        provider_id="codebase_memory",
        intent="live_integrate",
    )
    assert result["ok"] is False
    assert result["fail_closed"] is True
    assert result["reason_code"] == "provider_scoped_name_not_component_id"

    resolved = resolve_component_runtime({"hetu.codebase_memory": {"enabled": True}})
    assert resolved["config_ok"] is False
    assert "unknown_component_configured" in resolved["blocked_reasons"]


def test_enabled_hetu_supported_default_disabled():
    """After catalog flip: hetu is supported, default disabled, enableable."""
    assert "hetu" in COMPONENT_CATALOG
    assert COMPONENT_CATALOG["hetu"]["support_state"] == "supported"
    assert COMPONENT_CATALOG["hetu"]["default_enabled"] is False
    resolved = resolve_component_runtime({"hetu": {"enabled": True}})
    assert resolved["config_ok"] is True
    assert resolved["components"]["hetu"]["enabled"] is True
    resolved_off = resolve_component_runtime({"hetu": {"enabled": False}})
    assert resolved_off["config_ok"] is True
    assert resolved_off["components"]["hetu"]["enabled"] is False
    fresh = resolve_component_runtime(None)
    assert fresh["components"]["hetu"]["enabled"] is False
