"""Hardened Vibe Evidence v1 / S1 Ephemeral Operation Snapshot.

Strengthens schema consistency, redaction, and bounded trajectory fields while
preserving S1 semantics: ephemeral, not persisted, not a readiness engine.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from typing import Any

EVIDENCE_VERSION = "vibe.evidence.v1"
EVIDENCE_CLASS = "projected_ephemeral_s1"

# Material fields hashed for determinism. run_id is ephemeral and excluded.
_HASH_EXCLUDE = frozenset({"evidence_hash", "run_id"})

FORBIDDEN_EVIDENCE_PATTERNS: tuple[str, ...] = (
    r"notebooklm://",
    r"Authorization:\s*(?!\[REDACTED\])\S+",
    r"Bearer\s+(?!\[REDACTED\])\S+",
    r"cookie=(?!\[REDACTED\])\S+",
    r"Cookie:\s*(?!\[REDACTED\])\S+",
    r"provider_source_id\s*[:=]\s*(?!\[REDACTED\])\S+",
)


def _sha256_payload(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def redact_evidence_text(text: str) -> str:
    """Best-effort redaction for evidence-bound text fields."""
    out = text
    out = re.sub(r"notebooklm://\S+", "[REDACTED_NOTEBOOK_REF]", out, flags=re.IGNORECASE)
    out = re.sub(r"(?i)Authorization:\s*\S+(?:\s+\S+)*", "Authorization: [REDACTED]", out)
    out = re.sub(r"(?i)Bearer\s+\S+", "Bearer [REDACTED]", out)
    out = re.sub(r"(?i)cookie=\S+", "cookie=[REDACTED]", out)
    out = re.sub(
        r"(?i)provider_source_id\s*[:=]\s*\S+",
        "provider_source_id=[REDACTED]",
        out,
    )
    # Raw Beads-looking ids; hashed forms remain allowed.
    out = re.sub(r"\bvibe-control-[A-Za-z0-9_-]+\b", "[REDACTED_PROVIDER_TASK_ID]", out)
    return out


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_evidence_text(value)
    if isinstance(value, list):
        return [_redact_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _redact_value(v) for k, v in value.items()}
    return value


def build_evidence_v1(
    *,
    operation: str,
    mode: str,
    observed_head_value: str,
    git_status_short_empty: bool,
    generated_from: list[str],
    steps: list[str],
    blocked_reasons: list[str],
    next_actions: list[dict[str, Any]],
    run_id: str | None = None,
    base_head: str | None = None,
    recorded_baseline_commit: str | None = None,
    projected_fields: dict[str, Any] | None = None,
    mutation_intent: bool = False,
    effects: list[dict[str, Any]] | None = None,
    approval_class: str | None = None,
) -> dict[str, Any]:
    """Build hardened S1 evidence snapshot (ephemeral, not persisted)."""
    if not isinstance(mutation_intent, bool):
        raise TypeError("mutation_intent must be a bool")
    rid = run_id or str(uuid.uuid4())
    base = base_head if base_head is not None else observed_head_value
    redacted_blocked = _redact_value(list(blocked_reasons))
    redacted_next = _redact_value(list(next_actions))
    redacted_from = _redact_value(list(generated_from))
    redacted_steps = _redact_value(list(steps))
    completed_effects = [e for e in (effects or []) if isinstance(e, dict)]
    mutation_performed = bool(completed_effects)
    resolved_approval = approval_class or (
        "local_runtime_write" if mutation_intent else "readonly"
    )

    body: dict[str, Any] = {
        "evidence_version": EVIDENCE_VERSION,
        "evidence_class": EVIDENCE_CLASS,
        "run_id": rid,
        "operation": operation,
        "mode": mode,
        "base_head": base,
        "observed_head": observed_head_value,
        "recorded_baseline_commit": recorded_baseline_commit,
        "observed_head_vs_baseline": {
            "same": (
                recorded_baseline_commit is not None
                and str(recorded_baseline_commit) == str(observed_head_value)
            ),
            "note": "observed_head is current command evidence; baseline is recorded roadmap snapshot",
        },
        "git_status_short_empty": bool(git_status_short_empty),
        "generated_from": redacted_from,
        "source_surfaces": list(redacted_from),
        "steps": redacted_steps,
        "trajectory_bounded": True,
        "mutation": mutation_performed,
        "mutation_intent": mutation_intent,
        "mutation_performed": mutation_performed,
        "effects": completed_effects,
        "provider_mutation": False,
        "task_mutation": False,
        "config_mutation": False,
        "approval_class": resolved_approval,
        "persisted": mutation_performed,
        "source_of_truth": "engine",
        "facts_class": "projected",
        "blocked_reasons": redacted_blocked,
        "next_actions": redacted_next,
        "redaction": {
            "applied": True,
            "policy": "forbid_raw_notebook_refs_source_ids_secrets_raw_provider_task_ids",
            "provider_task_id": "binding_only_hashed_forms_allowed",
            "chatgpt_project_sources": (
                "external advisor context copies only; not product truth or closeout gate"
            ),
        },
        "authority": {
            "engine": "Vibe Control Engine",
            "repo_ssot": True,
            "evidence_is_not_ssot": True,
            "provider_task_id_is_identity": False,
        },
    }
    if projected_fields:
        # Pass-through projected Engine fields only — never recompute readiness.
        body["projected"] = {
            k: projected_fields.get(k)
            for k in (
                "product_ready",
                "provider_sync_required",
                "provider_ask_clean",
                "task_cache_current",
                "implementation_ready",
                "next_actionable_task",
                "no_actionable_next_task",
                "blocked_reasons",
            )
            if k in projected_fields
        }
        body["projected"] = _redact_value(body["projected"])

    hash_body = {k: v for k, v in body.items() if k not in _HASH_EXCLUDE}
    body["evidence_hash"] = _sha256_payload(hash_body)
    return body


def assert_no_forbidden_evidence_secrets(blob: str) -> None:
    for pattern in FORBIDDEN_EVIDENCE_PATTERNS:
        if re.search(pattern, blob, flags=re.IGNORECASE):
            raise AssertionError(f"forbidden evidence secret pattern matched: {pattern}")
    if 'provider_task_id": "vibe-control-' in blob:
        raise AssertionError("raw provider_task_id leaked into evidence")
    if '"notebook_ref"' in blob:
        raise AssertionError("notebook_ref leaked into evidence")
