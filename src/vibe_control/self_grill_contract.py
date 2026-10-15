"""Static self-grill communication contract (Engine projection; not a skill product)."""

from __future__ import annotations

from typing import Any

from vibe_control.json_envelope import next_action

# Contract SSOT: docs/project/sync/20260721-agent-self-grill-comm-contract.md
SELF_GRILL_CONTRACT_ID = "vibe.communication.self_grill.v1"

SELF_GRILL_STATUSES: tuple[str, ...] = (
    "PROVEN",
    "FALSIFIED",
    "PARTIAL",
    "OPEN",
    "DEFERRED_SLICE",
    "OWNER_DECISION",
)

SELF_GRILL_LOOP_STATUSES: tuple[str, ...] = (
    "IN_PROGRESS",
    "EXHAUSTED",
    "BLOCKED_ON_LIVE",
)

SELF_GRILL_REPLY_SHAPE = """\
THESIS: <one sentence under fire>
LOOP_STATUS: IN_PROGRESS | EXHAUSTED | BLOCKED_ON_LIVE

| id | claim | status | notebook | probe | evidence | next |
|----|-------|--------|----------|-------|----------|------|

Statuses: PROVEN | FALSIFIED | PARTIAL | OPEN | DEFERRED_SLICE | OWNER_DECISION
"""


def self_grill_contract_dict() -> dict[str, Any]:
    """Readonly catalog for describe / brief / gateway projection."""
    return {
        "contract_id": SELF_GRILL_CONTRACT_ID,
        "name": "self_grill",
        "purpose": (
            "Interrogate the agent's own claims until the frontier is empty; "
            "Knowledge is probe-only; never questionnaire the owner"
        ),
        "when_to_invoke": [
            "Owner distrusts RCA / fix / truth claim",
            "Hard bug or tidy one-line root cause",
            "First-principles / essential-link search",
            "Owner asks 审讯模式 / loop until no more shit found",
            "Tempted to claim safe-to-retry while Knowledge degraded",
        ],
        "when_not_to_invoke": [
            "Routine status / closeout / happy-path sync",
            "Ordinary knowledge Q&A",
        ],
        "required_reply_shape": SELF_GRILL_REPLY_SHAPE.strip(),
        "claim_statuses": list(SELF_GRILL_STATUSES),
        "loop_statuses": list(SELF_GRILL_LOOP_STATUSES),
        "rules": [
            "PARTIAL/OPEN must spawn children or stay on frontier",
            "PROVEN needs Knowledge envelope and/or repo paths — not chat memory",
            "allow_list length >= 2 => every Knowledge probe requires --notebook",
            "No cross-notebook ask; wrong notebook invalidates evidence for that claim",
            "Safe to retry / root cause proven only if sufficiency claims are PROVEN "
            "and LOOP_STATUS=EXHAUSTED",
            "Do not stop because Knowledge is degraded — continue with decidable claims",
        ],
        "knowledge_probes": [
            "vibe knowledge doctor [--notebook] --json",
            "vibe knowledge status [--notebook] --json",
            "vibe knowledge inventory [--notebook] --json",
            "vibe knowledge query --question-file <file> [--notebook] --json",
        ],
        "never_auto_run": [
            "vibe knowledge sync --apply",
            "vibe knowledge retry --apply",
        ],
        "entry_commands": [
            "vibe gateway --intent grill_brief --json",
            "vibe describe --json  # communication_contracts.self_grill",
            "vibe grill status --json",
            "vibe grill checkpoint --json",
            "vibe grill close --status EXHAUSTED|BLOCKED_ON_LIVE --json",
        ],
        "docs": [
            "docs/project/sync/20260721-agent-self-grill-comm-contract.md",
            "docs/project/sync/20260721-self-grill-session-loop-design.md",
        ],
        "non_goals": [
            "Installable vibe-self-grill skill",
            "Knowledge grill mode / CLI",
            "HSP as Engine capability",
            "Gateway-owned grill loop engine",
            "Grill as product_ready / closeout gate",
        ],
        "known_limitations_v1": [
            "Engine does not parse agent prose for claim tables (session is receipt + gates only)",
            "Aware path still requires grill_brief / describe / active session — not ambient",
            "One active grill per consumer repo in v1",
        ],
    }


def self_grill_continue_next_action() -> dict[str, Any]:
    """Pull-back next_action for active IN_PROGRESS grill (mutation false)."""
    return next_action(
        code="CONTINUE_SELF_GRILL",
        command="vibe grill status --json",
        mutation=False,
        reason=(
            "Self-grill in progress: fill THESIS/claim table per "
            "communication_contract.required_reply_shape; probe with Knowledge "
            "readonly commands (add --notebook when allow_list has 2+ entries); "
            "checkpoint/close via vibe grill …"
        ),
    )
