"""Agent-facing operation disclosure — foundational, not feature-specific.

Product rule: every agent-callable operation that has modes, defaults, or
gated choices MUST expose a self-explanatory disclosure block in its JSON
envelope (and CLI help). Agents must be able to see:

1. what the default is
2. what choices exist
3. whether they can choose now
4. how to choose (exact flag / command)

TDD locks this via ``tests/test_agent_surface_disclosure.py``. New features
that add policy without disclosure fail the contract tests.
"""

from __future__ import annotations

from typing import Any

DISCLOSURE_SCHEMA = "vibe.agent_surface.operation_disclosure.v1"

# Operations that MUST appear with disclosure on knowledge status / sync dry-run.
REQUIRED_KNOWLEDGE_OPERATION_IDS = frozenset(
    {
        "knowledge.sync",
    }
)


def build_operation_disclosure(
    *,
    operation_id: str,
    summary: str,
    default_choice: str,
    choices: list[dict[str, Any]],
    agent_can_choose: bool,
    how_to_inspect: str,
) -> dict[str, Any]:
    """Build one operation disclosure block.

    ``choices`` items SHOULD include:
    - ``id``: stable choice id (e.g. fail_stop)
    - ``available``: bool — callable now?
    - ``how``: CLI fragment or null if unavailable
    - ``effect``: one-line consequence
    """
    return {
        "schema": DISCLOSURE_SCHEMA,
        "operation_id": operation_id,
        "summary": summary,
        "default": default_choice,
        "agent_can_choose": bool(agent_can_choose),
        "how_to_inspect": how_to_inspect,
        "choices": list(choices),
        "mutation": False,
    }


def knowledge_sync_disclosure(
    *,
    continue_flag_available: bool = True,
    batch_flag_available: bool = True,
    multi_wait_available: bool = True,
    api_ingest_available: bool = True,
    upload_concurrency_available: bool = True,
) -> dict[str, Any]:
    """Canonical disclosure for knowledge sync apply fault-tolerance + batch policy."""
    return build_operation_disclosure(
        operation_id="knowledge.sync",
        summary=(
            "Sync apply is idempotent per doc (receipt checkpoint). "
            "Default: fail_stop + batch_size=1 + wait_mode=serial + ingest_path=auto. "
            "Multi-file throughput: prefer API concurrent uploads "
            "(--ingest-path api --upload-concurrency 8 --batch-size N). "
            "CLI path cannot parallelize uploads."
        ),
        default_choice="fail_stop",
        agent_can_choose=True,
        how_to_inspect="vibe knowledge status --json | vibe knowledge sync --dry-run --json",
        choices=[
            {
                "id": "fail_stop",
                "available": True,
                "how": "vibe knowledge sync --apply --json",
                "effect": (
                    "Stop on first non-fatal item failure; successful items stay "
                    "checkpointed in receipt — retry does not re-upload them"
                ),
            },
            {
                "id": "partial_continue",
                "available": bool(continue_flag_available),
                "how": (
                    "vibe knowledge sync --apply --continue-on-item-error --json"
                    if continue_flag_available
                    else None
                ),
                "effect": (
                    "Continue after item_skippable/item_retryable failures; "
                    "emit item_failures; never claim synced while failures remain; "
                    "fatal_run still stops"
                ),
            },
            {
                "id": "batch_size",
                "available": bool(batch_flag_available),
                "how": (
                    "vibe knowledge sync --apply --batch-size 5 --json"
                    if batch_flag_available
                    else None
                ),
                "effect": (
                    "Add up to N creates before waiting (default 1=legacy serial; max 20). "
                    "For multi-file throughput use N >= upload_concurrency. "
                    "Replaces stay one-at-a-time for identity safety."
                ),
            },
            {
                "id": "wait_mode_serial",
                "available": True,
                "how": "vibe knowledge sync --apply --wait-mode serial --json",
                "effect": (
                    "CLI ingest: wait each pending source sequentially (default; safest). "
                    "Ignored when ingest_path=api (library multi-wait is used)."
                ),
            },
            {
                "id": "wait_mode_multi",
                "available": bool(multi_wait_available),
                "how": (
                    "vibe knowledge sync --apply --wait-mode multi --batch-size 5 --json"
                    if multi_wait_available
                    else None
                ),
                "effect": (
                    "CLI ingest only: concurrent in-process waits for the micro-batch "
                    "(CLI is single-id; Vibe coalesces). Does not parallelize uploads."
                ),
            },
            {
                "id": "ingest_path_auto",
                "available": True,
                "how": "vibe knowledge sync --apply --ingest-path auto --json",
                "effect": (
                    "Use Python API concurrent uploads when notebooklm is importable; "
                    "else CLI serial add (default)."
                ),
            },
            {
                "id": "ingest_path_api",
                "available": bool(api_ingest_available),
                "how": (
                    "vibe knowledge sync --apply --ingest-path api "
                    "--upload-concurrency 8 --batch-size 10 --json"
                    if api_ingest_available
                    else None
                ),
                "effect": (
                    "Force notebooklm-py concurrent add_file(wait=False) + wait_for_sources. "
                    "This is the multi-file throughput path."
                ),
            },
            {
                "id": "ingest_path_cli",
                "available": True,
                "how": "vibe knowledge sync --apply --ingest-path cli --json",
                "effect": (
                    "Force CLI subprocess source add (serial uploads). "
                    "Use only for diagnosis / API unavailable fallback."
                ),
            },
            {
                "id": "upload_concurrency",
                "available": bool(upload_concurrency_available and api_ingest_available),
                "how": (
                    "vibe knowledge sync --apply --upload-concurrency 8 --batch-size 10 --json"
                    if (upload_concurrency_available and api_ingest_available)
                    else None
                ),
                "effect": (
                    "Max in-flight single-file API uploads (default 8, max 16; "
                    "not a bulk multi-file RPC). "
                    "Only applies when ingest_path resolves to api."
                ),
            },
        ],
    )


def assert_disclosure_shape(block: dict[str, Any] | None) -> list[str]:
    """Return list of contract violations (empty = ok)."""
    errors: list[str] = []
    if not isinstance(block, dict):
        return ["disclosure missing or not an object"]
    if block.get("schema") != DISCLOSURE_SCHEMA:
        errors.append(f"schema must be {DISCLOSURE_SCHEMA}")
    for key in ("operation_id", "summary", "default", "agent_can_choose", "how_to_inspect", "choices"):
        if key not in block:
            errors.append(f"missing field: {key}")
    choices = block.get("choices")
    if not isinstance(choices, list) or not choices:
        errors.append("choices must be a non-empty list")
    else:
        for i, c in enumerate(choices):
            if not isinstance(c, dict):
                errors.append(f"choices[{i}] must be object")
                continue
            for k in ("id", "available", "effect"):
                if k not in c:
                    errors.append(f"choices[{i}] missing {k}")
    return errors


def collect_operation_disclosures(payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Index disclosures from envelope data.agent_surface.operations or data.scale.sync_policy."""
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(payload, dict):
        return out
    data = payload.get("data") if "data" in payload else payload
    if not isinstance(data, dict):
        return out
    surface = data.get("agent_surface")
    if isinstance(surface, dict):
        ops = surface.get("operations") or []
        if isinstance(ops, list):
            for op in ops:
                if isinstance(op, dict) and op.get("operation_id"):
                    out[str(op["operation_id"])] = op
    scale = data.get("scale")
    if isinstance(scale, dict):
        policy = scale.get("sync_policy")
        if isinstance(policy, dict) and policy.get("operation_id"):
            out[str(policy["operation_id"])] = policy
    return out
