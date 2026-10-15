# Knowledge Sync — Batch Apply Design

**Status:** implemented (2026-07-18) — default remains serial `batch_size=1`  
**Mutation:** `sync|retry --apply [--batch-size N] [--wait-mode serial|multi]`  
**Depends on:** Slice A/B/C + agent-surface disclosure.

## Problem

Per-doc `add → wait → next` is `O(changed × wait)`. Tens of changes become hours.

## Implemented target

```text
plan → micro-batch of creates (N) → serial|multi wait → receipt checkpoint
     → verify / ack (or pending + item_failures)
```

Replaces stay one-at-a-time (identity lifecycle). Batching is **create pacing +
wait coalescing**, not a new identity model.

## Parameters

| Parameter | CLI | Default | Notes |
|---|---|---|---|
| `batch_size` | `--batch-size N` | `1` | Max creates before wait; capped at 20 |
| `wait_mode` | `--wait-mode serial\|multi` | `serial` | `multi` = concurrent in-process `wait_source` (CLI is single-id) |
| `batch_pace_ms` | (API only for now) | `0` | Optional sleep between batches |
| `continue_on_item_error` | existing flag | off | Composes with batching |

## Provider note

Pinned `notebooklm source wait` accepts **one** SOURCE_ID. Multi-wait is
implemented inside Vibe via concurrent single-id waits for the current
micro-batch — not a Temporal job, not a false claim of native multi-id CLI.

## Agent disclosure

`scale.sync_policy` / `agent_surface` list `batch_size` and `wait_mode_*`
choices with exact how-to commands. Dry-run `next_actions` include
`SYNC_BATCH_MULTI_WAIT`.

## Explicit non-goals

- Default CI / closeout enabling aggressive parallelism
- Raising `max_sources` as a substitute for batching
- Multi-notebook sharding
- Durable workflow engine
