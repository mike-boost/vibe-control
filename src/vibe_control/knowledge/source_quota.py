"""NotebookLM source-quota honesty helpers (readonly; no provider mutation).

Google NotebookLM enforces per-notebook source caps by plan. Vibe's
``knowledge.max_sources`` is a local guard and must not silently exceed the
lowest common plan ceiling without warning agents/owners.
"""

from __future__ import annotations

from typing import Any

# Published Google Gemini Notebook / NotebookLM plan caps (sources per notebook).
# Subject to change; treat as advisory reference for warnings, not a hard API.
NOTEBOOKLM_SOURCES_PER_NOTEBOOK: dict[str, int] = {
    "standard": 50,
    "plus": 100,
    "pro": 300,
    "ultra_20tb": 500,
    "ultra_30tb": 600,
}

# Product defaults aligned with Standard (free) so configs do not false-greenlight.
DEFAULT_MAX_SOURCES = NOTEBOOKLM_SOURCES_PER_NOTEBOOK["standard"]
DEFAULT_WARN_SOURCES = 40

# Cap we warn against when local max_sources exceeds Standard without acknowledgment.
STANDARD_SOURCES_CAP = NOTEBOOKLM_SOURCES_PER_NOTEBOOK["standard"]


def assess_source_quota(
    *,
    max_sources: int | None,
    warn_sources: int | None = None,
    desired_count: int | None = None,
    remote_source_count: int | None = None,
    provider: str | None = "notebooklm",
) -> dict[str, Any]:
    """Project quota honesty fields + warnings from config and counts.

    Pure function: does not call providers or recompute readiness.
    """
    provider_name = (provider or "").strip().lower() or "notebooklm"
    max_s = int(max_sources) if max_sources is not None else DEFAULT_MAX_SOURCES
    warn_s = int(warn_sources) if warn_sources is not None else DEFAULT_WARN_SOURCES
    desired = int(desired_count) if desired_count is not None else None
    remote = int(remote_source_count) if remote_source_count is not None else None

    warnings: list[str] = []
    codes: list[str] = []
    exceeds_standard = max_s > STANDARD_SOURCES_CAP

    if provider_name == "notebooklm" and exceeds_standard:
        codes.append("MAX_SOURCES_EXCEEDS_NOTEBOOKLM_STANDARD")
        warnings.append(
            f"knowledge.max_sources={max_s} exceeds NotebookLM Standard cap "
            f"({STANDARD_SOURCES_CAP}/notebook). Plus/Pro/Ultra accounts may allow "
            f"more; verify the live plan before large sync --apply."
        )

    if desired is not None and desired >= warn_s:
        codes.append("DESIRED_NEAR_WARN_SOURCES")
        warnings.append(
            f"desired corpus count {desired} >= warn_sources ({warn_s})"
        )

    if desired is not None and desired >= max_s:
        codes.append("DESIRED_AT_OR_OVER_MAX_SOURCES")
        warnings.append(
            f"desired corpus count {desired} >= max_sources ({max_s}); "
            "inventory/sync will fail closed with SOURCE_LIMIT_EXCEEDED"
        )

    if (
        provider_name == "notebooklm"
        and remote is not None
        and remote >= STANDARD_SOURCES_CAP
    ):
        codes.append("REMOTE_NEAR_OR_OVER_STANDARD_CAP")
        warnings.append(
            f"remote notebook source count={remote} is at/over Standard cap "
            f"({STANDARD_SOURCES_CAP}); further adds may fail on free-tier accounts"
        )

    if remote is not None and desired is not None and remote > max_s:
        codes.append("REMOTE_EXCEEDS_CONFIGURED_MAX_SOURCES")
        warnings.append(
            f"remote source count {remote} > knowledge.max_sources={max_s} "
            "(remote may include unmanaged/orphan sources)"
        )

    return {
        "provider": provider_name,
        "max_sources": max_s,
        "warn_sources": warn_s,
        "desired_count": desired,
        "remote_source_count": remote,
        "notebooklm_plan_caps_reference": dict(NOTEBOOKLM_SOURCES_PER_NOTEBOOK),
        "standard_sources_cap": STANDARD_SOURCES_CAP,
        "max_sources_exceeds_standard": exceeds_standard,
        "codes": codes,
        "warnings": warnings,
        "mutation": False,
    }
