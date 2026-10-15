"""Git land communication contract — agent owns local commit; never ask owner."""

from __future__ import annotations

from typing import Any

GIT_LAND_CONTRACT_ID = "vibe.communication.git_land.v1"

# Shared reason text for COMMIT_OR_CLEAN_LOCAL_STATE next_actions.
GIT_LAND_DIRTY_REASON = (
    "Agent-owned git land: inspect `git status`/`git diff`, run relevant gates, then "
    "commit changes that belong to the current authorized implementation/land task. "
    "Never ask the owner whether to commit or offer 'shall I commit?'. "
    "Unrelated dirty files → diagnose/report; do not stall waiting for commit permission. "
    "git push still requires explicit owner request. "
    "Commit alone is not closeout-complete — re-run `vibe closeout run` after a clean tree."
)


def git_land_contract_dict() -> dict[str, Any]:
    """Readonly catalog for describe / brief awareness."""
    return {
        "contract_id": GIT_LAND_CONTRACT_ID,
        "name": "git_land",
        "purpose": (
            "Local git commit/land is agent work for authorized implementation/land/"
            "release tasks; never questionnaire the owner about committing"
        ),
        "rules": [
            "Never ask the owner whether to land changes",
            "Never offer 'shall I commit?' or stall waiting for commit permission",
            "When the task is implement/land/release: inspect, test, commit as part of the job",
            "git push requires explicit owner request (or an explicit release task that includes push)",
            "No force-push; never update git config",
            "Commit alone ≠ product closeout — still need provider sync/ask + task-cache via closeout",
            "Provider/config/Beads mutations stay under Approval Matrix — local commit is not those",
        ],
        "dirty_tree_next_action_code": "COMMIT_OR_CLEAN_LOCAL_STATE",
        "dirty_tree_reason": GIT_LAND_DIRTY_REASON,
        "entry_commands": [
            "vibe describe --json  # communication_contracts.git_land",
            "git status --short",
            "git diff",
            "vibe closeout run --dry-run --json  # after clean tree",
        ],
        "docs": [
            "AGENTS.md",
            "docs/harness/phase-execution-contract.md",
            "docs/harness/ssot-closeout-transaction-contract.md",
        ],
        "non_goals": [
            "Auto-push without owner/release intent",
            "Treating commit as NotebookLM/Beads closeout complete",
            "Asking owner to run git for agent-owned land work",
        ],
    }
