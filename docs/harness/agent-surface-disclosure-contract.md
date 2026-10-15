# Agent Surface Disclosure Contract

**Status:** foundational product contract (2026-07-18)  
**Audience:** coding agents + maintainers  
**Rule:** Features must be self-explanatory. Agents must be able to discover
defaults, available choices, and how to choose — without reading harness design
notes.

## Why this exists

TDD that only locks internal helpers can ship behavior that agents cannot see.
That is a product defect. Disclosure is a **base capability**, not a per-feature
afterthought.

## Required shape

Every agent-callable operation with modes / gated flags MUST emit:

```text
schema: vibe.agent_surface.operation_disclosure.v1
operation_id
summary
default
agent_can_choose
how_to_inspect
choices[]: { id, available, how, effect }
```

Helpers: `vibe_control.agent_surface`.

## Knowledge sync (current)

| Choice | Available | How |
|---|---|---|
| `fail_stop` (default) | yes | `sync --apply` |
| `partial_continue` | yes | `sync --apply --continue-on-item-error` |
| `wait_mode_serial` | yes (only wait mode) | (no flag yet) |

Surfaced on:

- `vibe knowledge status --json` → `data.agent_surface.operations` + `data.scale.sync_policy`
- `vibe knowledge sync --dry-run --json` → same via `data.scale.sync_policy`
- CLI help for `--continue-on-item-error`

## Fault-tolerance semantics (industry-aligned)

Bulk ingest best practice mapped to Vibe:

1. **Idempotent per-item upsert** — receipt content hash skip (already)
2. **Checkpoint after each success** — receipt write mid-loop (required)
3. **DLQ / item_failures** — failed docs listed; do not block replay of successes
4. **Continue remaining** — opt-in `--continue-on-item-error` for item classes
5. **Fatal still stops** — target/auth/scope errors
6. **Never claim synced** while item_failures remain or probe fails
7. **Retry only remaining work** — successes stay checkpointed

## TDD gate

`tests/test_agent_surface_disclosure.py` MUST fail if:

- knowledge status / sync dry-run omit `knowledge.sync` disclosure
- disclosure shape is incomplete
- `partial_continue` choice claims `available` without a `how` flag string

New policy features MUST extend this test (or an equivalent surface test), not
only add private modules.
