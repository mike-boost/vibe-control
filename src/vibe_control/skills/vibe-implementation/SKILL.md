---
name: vibe-implementation
description: Plan / Beads / task / checkpoint / resume workflows for Vibe Control.
---

# vibe-implementation

Thin intelligent router for implementation task workflows. Mechanics live in the `vibe` CLI — not here.

## Routing table

| Intent | Command | Auto-run? |
|---|---|---|
| Implementation workflow readiness | `vibe task doctor --json` | yes (readonly) |
| Task state | `vibe task status --json` | yes (readonly) |
| Beads binary missing | `vibe task install-guide --json` | yes (readonly) |
| `.beads` missing / not initialized | `vibe task init-preview --json` | yes (readonly) |
| Config check | `vibe config validate --json` / `vibe doctor --json` | yes (readonly) |
| Readonly SSOT vs task provider diff | `vibe task reconcile --dry-run --json` | yes (readonly) |
| Coding-agent implementation prompt | `vibe implementation prompt --task <selector> --json` | yes (readonly) |
| Create / import / apply | Phase 11B Option A autonomous managed path only | no (needs gates) |
| Explicit `bd init` | show `init-preview` only; never auto-run | **no** |

## Core rules

- Use `vibe task` commands for Beads-managed work.
- Interpret JSON envelopes (`next_actions` with `code` / `command` / `mutation` / `reason`).
- Auto-run only readonly commands (`mutation: false`).
- **Git land is agent work** for implement/land tasks: commit locally yourself; never ask “shall I commit?”. Push still needs explicit owner request (`communication_contracts.git_land`).
- Do not create GitHub Issues, GitHub Projects, or Jira tickets for V1 tasks.
- Do not create/import/apply tasks until Phase 11B with explicit `--apply`.
- Phase 11A `task reconcile --dry-run` reports only; it never creates/updates/deletes.
- Never run `bd init` or create Beads tasks automatically.
- If Beads is unavailable, report task provider unavailable and continue with explicit prompt-only fallback.
- Do not treat NotebookLM synced state as Beads truth.
- Do not treat Beads task id / title as source identity.

## Failure behavior

- Beads (`bd`) missing → `BEADS_NOT_INSTALLED`; run `install-guide`.
- `.beads` missing → `BEADS_NOT_INITIALIZED`; run `init-preview`.
- Protected operator-state files → refuse Beads-driven replacement.

## Do-not-do list

- Do not initialize or mutate Beads from this skill automatically.
- Do not open GitHub Issues / Projects / Jira for V1 managed tasks.
- Do not rewrite protected phase operator-state files via Beads.
- Do not hide provider unavailability behind fake task progress.
- Do not invent Phase 11B plan import / apply behavior.
- Do not call `bd` directly by default; use `vibe task` CLI.
