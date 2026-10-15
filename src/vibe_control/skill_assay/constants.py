"""Skill Assay schema / path constants."""

from __future__ import annotations

SCHEMA_SCENARIO = "vibe.skill_assay.scenario.v1"
SCHEMA_TRACE = "vibe.skill_assay.trace.v1"
SCHEMA_EVIDENCE = "vibe.skill_assay.evidence.v1"
SCHEMA_ANALYSIS = "vibe.skill_assay.analysis.v1"
SCHEMA_REPORT = "vibe.skill_assay.report.v1"
SCHEMA_META = "vibe.skill_assay.meta.v1"

DEFAULT_ROOT_REL = "runtime/vibe-skill-assay"
DEFAULT_RUNS = 3
MIN_RUNS = 2
MAX_RUNS = 5

HOST_IDS = frozenset({"cursor", "github-copilot", "fake"})
TYPED_CHECK_KINDS = frozenset(
    {
        "file_exists",
        "json_schema",
        "text_match",
        "assistant_text_match",
        "git_diff",
        "exit_status",
    }
)
CAUSAL_SCOPES = frozenset({"single_host", "cross_host"})
EXECUTION_PROFILES = frozenset({"response_only", "workspace_sandbox"})
SUPPORT_STATES = frozenset({"supported", "experimental", "unverified", "unavailable"})
ASSISTANT_TEXT_LIMIT = 8000
