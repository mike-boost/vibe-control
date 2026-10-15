# Knowledge Sync — Partial Continue Contract

**Status:** implemented (2026-07-18) — default remain fail_stop; opt-in continue wired  
**Mutation:** `sync|retry --apply [--continue-on-item-error]`  
**Related:** `agent_surface.py`, `partial_continue.py`, `phase8_apply.py`,
`docs/harness/agent-surface-disclosure-contract.md`

## Problem

Without checkpoint + optional continue, one corrupt/unreadable file can block a
batch and force re-work of already-uploaded docs.

## Product rule (load-bearing)

```text
Default mode = fail_stop
Optional mode = partial_continue   # --continue-on-item-error
Both modes checkpoint receipt after each successful item
```

Partial continue MUST NOT become the silent default. Closeout and
`provider_ask_clean` remain fail-closed until the run finishes and verify passes
with zero `item_failures`.

## Modes

| Mode | Flag | Behavior |
|---|---|---|
| `fail_stop` | (default) | First item failure → pending + last-sync-report → exit non-ok; **successes already checkpointed** |
| `partial_continue` | `--continue-on-item-error` | Skip non-fatal item failures; finish remaining; emit `item_failures` DLQ |

## Failure classes

| Class | Examples | fail_stop | partial_continue |
|---|---|---|---|
| `fatal_run` | `TARGET_MISMATCH`, `APPLY_SCOPE_VIOLATION`, auth/config, systemic exception w/o doc_id | stop | stop |
| `item_retryable` | `WAIT_FAILED`, timeout, rate limit | stop | record + continue |
| `item_skippable` | `ADD_FAILED`, `MISSING_LOCAL_FILE`, replace failure | stop | record + continue |
| `verify_aggregate` | Final probe fail | stop | stop |

## Industry mapping

| Practice | Vibe |
|---|---|
| Idempotent upsert | content-hash skip + managed identity |
| Checkpoint after success | receipt write per item |
| DLQ | `item_failures[]` + pending/last-sync-report |
| Continue batch | `--continue-on-item-error` |
| Never claim success with failures | `ok=false`, no ack while failures remain |

## Agent disclosure

See `agent-surface-disclosure-contract.md`. Status / dry-run expose
`scale.sync_policy` + `agent_surface.operations` so agents can choose.

## Explicit non-goals

- Silent default flip to continue
- Temporal job queue
- Multi-wait batching (separate design; still serial wait)
- Auto orphan delete
