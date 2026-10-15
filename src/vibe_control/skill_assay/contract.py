"""Static Skill Assay communication contract (Engine projection for agents)."""

from __future__ import annotations

from typing import Any

from vibe_control.json_envelope import next_action

SKILL_ASSAY_CONTRACT_ID = "vibe.communication.skill_assay.v1"

SKILL_ASSAY_WORKFLOW = """\
1. Entry: vibe gateway --intent skill_assay_brief --skill <dir> [--host <host>] --json
   (or vibe skill-assay brief --skill <dir> --json)
2. Require an explicit host: cursor | github-copilot (fake = tests only). Never auto-pick.
3. Doctor: vibe skill-assay doctor --host <host> --json
4. Diagnose dry-run then execute (default --runs 3):
   vibe skill-assay diagnose --skill <dir> --host <host> --scenario <yaml>|--prompt-file <file> --runs 3 --dry-run --json
   vibe skill-assay diagnose ... --execute --json
5. Agent writes analysis.json (hypotheses cite resolvable evidence_refs + current official docs + verdict)
6. Finalize: vibe skill-assay finalize --assay <id> --analysis-file analysis.json --json
7. Report: vibe skill-assay report --assay <id> --json

Report buckets: facts (CLI) | hypotheses (doc-backed) | unknowns (honest gaps)
Single-host without --baseline-host => causal_scope=single_host (no cross-host root-cause claim)
Never silent-fallback to fake when a real host fails.
"""


def skill_assay_contract_dict() -> dict[str, Any]:
    """Readonly catalog for describe / gateway / skill-assay brief."""
    return {
        "contract_id": SKILL_ASSAY_CONTRACT_ID,
        "name": "skill_assay",
        "purpose": (
            "Measure any local skill across coding-agent hosts: "
            "orchestrator collects evidence; agent cites current docs; "
            "CLI finalizes report. Not product_ready / closeout."
        ),
        "primary_operator": "coding_agent",
        "owner_utterance_examples": [
            "用 Vibe Control / Skill Assay 评估这个 skill 在 Cursor 上的表现",
            "用 skill-assay 看看这个 skill 在 GitHub Copilot 上怎么样",
            "assay this skill on fake first (tests only)",
        ],
        "when_to_invoke": [
            "Owner asks to assay / diagnose / measure a local skill on a named host",
            "Skill works in one host but looks worse in another",
            "Need structured evidence before deciding whether prose should become CLI",
        ],
        "when_not_to_invoke": [
            "Installing Vibe's own skills (use vibe skills status|install)",
            "Routine product_ready / closeout / knowledge sync",
            "Ordinary self-grill RCA (use grill_brief)",
            "Owner did not name cursor or github-copilot (ask which host; do not auto-pick)",
        ],
        "required_workflow": SKILL_ASSAY_WORKFLOW.strip(),
        "hosts_v1": ["cursor", "github-copilot", "fake"],
        "host_auth": {
            "cursor": "Reuse local `agent login` / `agent status`; never require CURSOR_API_KEY",
            "github-copilot": (
                "Reuse local Copilot CLI / gh login via use_logged_in_user; "
                "optional dep: pip install 'vibe-control[skill-assay-hosts]'"
            ),
            "fake": "In-process TDD host only; never silent production fallback",
        },
        "rules": [
            "Prefer Gateway skill_assay_brief as the agent entry when owner names skill-assay",
            "Owner must name cursor or github-copilot; never auto-select or run both silently",
            "Separate from vibe skills install — never confuse the two surfaces",
            "Default runs=3 independent fresh sessions; do not reuse one chat context",
            "Orchestrator evidence is authoritative; agent self-narration is supplemental",
            "Typed checks only — never execute arbitrary shell from untrusted skill sidecars",
            "facts vs hypotheses vs unknowns — docs support hypotheses only",
            "Without baseline host, do not claim cross-host root cause",
            "On host failure: keep original host id/error; never degrade to fake",
            "Not a components.* readiness capability; does not affect product_ready",
        ],
        "entry_commands": [
            "vibe gateway --intent skill_assay_brief --skill <dir> [--host <host>] --json",
            "vibe skill-assay brief --skill <dir> [--host <host>] --json",
            "vibe describe --json  # communication_contracts.skill_assay",
            "vibe skill-assay doctor --host <host> --json",
            "vibe skill-assay diagnose --skill <dir> --host <host> --prompt-file <file> --runs 3 --dry-run|--execute --json",
            "vibe skill-assay finalize --assay <id> --analysis-file <json> --json",
            "vibe skill-assay report --assay <id> --json",
        ],
        "never_auto_run": [
            "Do not auto-pick host when owner omitted cursor/github-copilot",
            "Do not fall back to fake when cursor/github-copilot doctor or execute fails",
        ],
        "docs": [
            "docs/project/sync/20260722-skill-assay-spec.md",
        ],
        "non_goals": [
            "Merge into vibe skills install group",
            "components.skill_assay readiness gate",
            "Auto-rewrite / repair of skills in v1",
            "LLM-as-judge quality without typed checks",
            "Fourth installable skill product for assay",
            "Cross-host --baseline-host root-cause attribution in v1",
        ],
        "known_limitations_v1": [
            "fake host is for local TDD only",
            "Cursor isolation is partial (ambient user skills possible)",
            "--baseline-host cross-host compare not implemented (fail closed)",
            "Gateway brief is guidance + next_actions; it does not spawn host runs by itself",
        ],
    }


def skill_assay_entry_next_actions(
    *,
    skill_path: str | None = None,
    host_id: str | None = None,
) -> list[dict[str, Any]]:
    skill = skill_path or "<skill-dir>"
    if not host_id:
        return [
            next_action(
                code="SKILL_ASSAY_HOST_REQUIRED",
                command="vibe skill-assay doctor --host cursor|github-copilot --json",
                mutation=False,
                reason="Owner must choose cursor or github-copilot before diagnose",
            )
        ]
    host = host_id
    return [
        next_action(
            code="SKILL_ASSAY_DOCTOR",
            command=f"vibe skill-assay doctor --host {host} --json",
            mutation=False,
            reason="Check whether the target host adapter is ready (login/CLI/SDK)",
        ),
        next_action(
            code="SKILL_ASSAY_DIAGNOSE_DRY_RUN",
            command=(
                f"vibe skill-assay diagnose --skill {skill} --host {host} "
                "--prompt-file <prompt.txt> --runs 3 --dry-run --json"
            ),
            mutation=False,
            reason="Plan N independent runs before any host execute",
        ),
        next_action(
            code="SKILL_ASSAY_DIAGNOSE_EXECUTE",
            command=(
                f"vibe skill-assay diagnose --skill {skill} --host {host} "
                "--prompt-file <prompt.txt> --runs 3 --execute --json"
            ),
            mutation=True,
            reason="Collect orchestrator evidence under runtime/vibe-skill-assay/",
        ),
        next_action(
            code="SKILL_ASSAY_FINALIZE",
            command=(
                "vibe skill-assay finalize --assay <assay-id> "
                "--analysis-file <analysis.json> --json"
            ),
            mutation=True,
            reason="After citing current official docs, finalize hypotheses against evidence",
        ),
    ]
