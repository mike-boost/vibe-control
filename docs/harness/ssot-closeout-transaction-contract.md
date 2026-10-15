# SSOT Closeout Transaction Contract

**Status:** harness enforcement (local/readonly + prompt/status gates)  
**Surface:** `vibe closeout run --json` (preferred), `evaluate_ssot_closeout`,
`vibe integration status --json`, `vibe implementation prompt --json`

## Problem this prevents

Agents must **not** treat an active SSOT / `include_extra` **git commit alone** as
product closeout complete while:

- bounded NotebookLM sync is still required (`provider_sync_required` / drift / ask unclean), or
- `task_cache_current=false`

Product closeout is based only on committed repo SSOT, empty `git status --short`,
NotebookLM/local_fts provider sync/ask hygiene, Beads task-cache state, and —
when Hetu is enabled — Hetu index readiness (closeout **never** auto-reindexes).

ChatGPT Project Sources are owner-manual **external advisor copies** for advisor
context freshness. They are **not** repo state, not NotebookLM sync sources, not
CLI-observable, and **not** a product closeout gate.

## Transaction sequence

```text
commit active SSOT/include_extra (clean git status --short)
  → vibe closeout run --dry-run --json   (preferred orchestration entry)
  → vibe closeout run --apply --json     (bounded knowledge sync only when dry-run safe)
  → if task_cache_current=false: explicit Beads convergence (never auto by closeout driver)
```

**Who commits:** the coding agent, for authorized implement/land work — never ask the
owner whether to commit. Dirty-tree `COMMIT_OR_CLEAN_LOCAL_STATE` means agent inspects,
lands task-owned changes, or diagnoses unrelated dirt; it does **not** mean ask permission.
`git push` remains explicit-owner. Commit alone is still not closeout-complete.

Agents should consume `vibe closeout run --json` instead of hand-assembling
`knowledge sync` / `integration status` / `task reconcile` sequences.

Bounded NotebookLM sync is **normal closeout**, not optional follow-up.
Closeout `--apply` never mutates Beads, never auto-reindexes Hetu, and never gates
on ChatGPT Project Sources.

## CLI fields

| Field | Meaning |
|---|---|
| `closeout_state` | includes `ssot_change_committed_sync_required`, `ssot_change_committed_sync_pending`, … |
| `closeout_complete` | true only when full pass / product-ready claim allowed |
| `provider_sync_required` | true until knowledge half is synced+ask-clean for the change |
| `implementation_ready` | prompt greenlight; false when closeout/readiness incomplete |
| `closeout_blocking` | actionable task selected but must not start feature work |
| `chatgpt_project_sources.product_closeout_gate` | always `false` (advisor metadata only) |

`waiting_owner_project_sources` is **removed** from product closeout states.
`UPDATE_CHATGPT_PROJECT_SOURCES` is **not** a product closeout next_action.

## Implementation prompt rule

`vibe implementation prompt` must **not** emit a normal `Implement:` goal when any of:

- `provider_sync_required=true`
- knowledge `sync_state` is drift/pending/unavailable
- `provider_ask_clean=false`
- `task_cache_current=false`
- `product_ready=false`

Blocked reasons must come from provider/task readiness — never from ChatGPT Project
Sources handoff.

Completed anchors still return completed / do-not-restart (never restart Phase 12).

## Unsafe mutation stops (unchanged)

Before any NotebookLM mutation, dry-run must fail closed on:

- unmanaged/orphan delete
- broad cleanup
- target/auth/config change
- unexpected source outside current inventory
- provider unavailable / target mismatch
- raw provider ref exposure in reportable output

## Non-goals

- Does not auto-detect or gate on ChatGPT Project Sources upload success
- Does not auto-run sync --apply
- Does not invent Phase 13
- Does not implement Component Runtime Core Baseline
