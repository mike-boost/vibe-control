---
name: vibe-control
description: Front-door workflow router for Vibe Control (Gateway thin router to Engine CLI).
---

# vibe-control

Thin front-door / Gateway workflow router only. Mechanics live in the `vibe` CLI — not here.
Do not put provider implementation logic in this skill.
Gateway / Skills never own repo facts, readiness, provider state, task identity, or mutation approval.

## Preferred Gateway routes (readonly)

Prefer `vibe gateway --intent ... --json` when choosing an Engine surface. Gateway is a thin
intent router: it delegates to Engine and preserves Engine JSON evidence (`source_of_truth=engine`).

| Intent | Command | Auto-run? |
|---|---|---|
| status / readiness | `vibe gateway --intent status --json` | yes (readonly) |
| what next | `vibe gateway --intent what_next --json` | yes (readonly) |
| implementation prompt | `vibe gateway --intent get_prompt --task <selector> --json` | yes (readonly) |
| why blocked | `vibe gateway --intent why_blocked --json` | yes (readonly) |
| summary | `vibe gateway --intent summary --json` | yes (readonly) |
| short brief | `vibe gateway --intent brief --json` | yes (readonly) |
| describe control surface | `vibe describe --json` | yes (readonly) |
| experience feedback (pain/bright spot) | `vibe feedback init-preview --json` then draft/validate/pack | init-preview yes; draft/pack only when owner asks to record feedback |
| hard-bug / RCA distrust / first-principles | `vibe gateway --intent grill_brief --json` | yes (opens/resumes local grill session + contract) |
| grill status / checkpoint / close | `vibe grill status|checkpoint|close … --json` | status yes; checkpoint/close when grilling |
| skill assay (owner names Cursor or GitHub Copilot) | `vibe gateway --intent skill_assay_brief --skill <dir> --host <cursor\|github-copilot> --json` | yes (readonly contract + next_actions; then doctor/diagnose/finalize; never silent fake fallback) |
| prepare closeout | `vibe gateway --intent prepare_closeout --json` | yes (readonly dry-run) |
| verify after work | `vibe gateway --intent verify_after_work --json` | yes (readonly dry-run) |

Gateway refuses mutation/raw-provider intents (`closeout_apply`, `task_apply`, `raw_bd`, etc.).
Never auto-run `vibe closeout run --apply` from Gateway.
Route success is not Engine success: always check `data.engine_payload.ok` (and outer `ok`).
`why_blocked` is Progress pass-through — read `engine_payload.data.blocked_reasons` (or Gateway
`data.blocked_reasons` pointer). Alias `closeout` maps to readonly dry-run only.
Do not use a `doctor` Gateway intent; call Engine doctor surfaces directly.

## Mandatory Phase 11A workflow

This workflow is mandatory for confirmed Phase 11A readonly dogfood only.
Do not invent other mandatory workflows.

```text
1. Knowledge readonly facts (via vibe-knowledge / vibe knowledge CLI)
2. Agent reasoning and expected-task derivation (agent-owned)
3. Task readonly reconcile (via vibe-implementation / vibe task reconcile --dry-run)
4. Report evidence + next_action (no --apply)
```

## Routing table

| Step | Intent | Command | Auto-run? |
|---|---|---|---|
| 0 | Gateway status (preferred front door) | `vibe gateway --intent status --json` | yes (readonly) |
| 0a | SSOT closeout orchestration (preferred) | `vibe closeout run --dry-run --json` | yes (readonly) |
| 0b | Bounded knowledge closeout apply | `vibe closeout run --apply --json` | **no** — only when user/task explicitly asks |
| 1a | ProviderTarget sync state | `vibe knowledge status --json` | yes (readonly) |
| 1b | SSOT-backed question | `vibe knowledge query --question-file <file> --json` | yes (readonly) |
| 1c | Sync preview without mutation | `vibe knowledge sync --dry-run --json` | yes (readonly) |
| 1d | Optional inventory / doctor | `vibe knowledge inventory --json` / `vibe knowledge doctor --json` | yes (readonly) |
| 2 | Agent reasoning | (no CLI — agent derives expected tasks from SSOT facts) | n/a |
| 3a | Task readiness | `vibe task doctor --json` / `vibe task status --json` | yes (readonly) |
| 3b | Readonly reconcile | `vibe task reconcile --dry-run --json` | yes (readonly) |
| 4 | Evidence / next action | interpret JSON envelopes; stop | yes (readonly) |

Optional provider selection:

```bash
vibe task reconcile --dry-run --json --provider fake
vibe task reconcile --dry-run --json --provider beads
```

## Core rules

- Skills stay thin; call CLI and interpret JSON envelopes (`code` / `command` / `mutation` / `reason`).
- Auto-run only when `mutation: false`.
- Never auto-run `--apply` (including `vibe closeout run --apply`).
- Prefer `vibe closeout run --dry-run --json` over hand-assembling sync/status/task steps.
- **Git land is agent work:** for implement/land/release tasks, inspect/diff/test/commit locally yourself — never ask the owner “shall I commit?” or stall for commit permission. `git push` still needs explicit owner request. See `vibe describe --json` → `communication_contracts.git_land`.
- **对 owner 说人话：** 不用未解释的黑话（managed / ask-clean / product_ready 等）。见 `communication_contracts.owner_plain_language`。
- Experience feedback (`vibe feedback …`) is not a task; draft/pack only when owner asks; never upload.
- Never call NotebookLM directly.
- Never call `bd` directly.
- Never run `bd init`, Beads create/update/delete, or knowledge sync/retry `--apply`
  outside an explicit closeout `--apply` / Approval Matrix path.
- NotebookLM synced is not Beads truth.
- Repo SSOT specs are truth for expected tasks.
- Beads task id is binding result only.

## Do-not-do list

- Do not embed sync/reconcile algorithms in this skill.
- Do not hard-code unknown future workflows as mandatory.
- Do not package additional skills just to mirror other skill ecosystems.
- Do not start long autonomous multi-agent runs from this skill.
