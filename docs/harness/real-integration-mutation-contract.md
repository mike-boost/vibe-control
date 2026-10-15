# Real Integration Mutation Contract

Short rules for any **real** provider mutation. Classify mutations; do not treat every
provider call the same.

## Product framing

Vibe Control is agent-facing and provider-backed. Humans approve **boundary-level**
mutations; agents self-manage normal readonly work and (when CLI rules allow) safe
Vibe-managed task ops. Safety is enforced by CLI + tests + harness — not prompt wording alone.

## Mutation classes

### A. NotebookLM / knowledge mutations

Real NotebookLM mutations include:

- `source add` / `delete` / `rename` / `clean` / `update`
- `vibe knowledge sync --apply`
- `vibe knowledge retry --apply`
- `seed-test-sources --allow-add`
- acceptance-only residue cleanup that deletes remote sources
- acceptance-only `knowledge smoke replace --apply`

Read-only probes (`remote-inventory`, sync dry-run, receipt status/inspect, source wait,
`cleanup-candidates`) are **not** mutations and must never hidden-mutate.

**Bounded current-SSOT closeout sync** (`sync --dry-run` → `sync --apply` limited to current
active SSOT / default inventory expected updates, with committed SSOT and empty
`git status --short`) is a **normal closeout action** under Front/Core / Knowledge specs —
not a separate per-run owner-approval ceremony.

Still require explicit owner approval (or an explicitly scoped phase prompt) for:

- unmanaged / orphan delete
- broad cleanup / notebook clean
- target / config / auth changes
- retry of arbitrary pending provider state
- provider mutation outside current active SSOT / default inventory
- destructive operations outside receipt-owned superseded cleanup

### B. Beads / task mutations

| Class | Default | Notes |
|---|---|---|
| Readonly list/show/ready/status/reconcile/apply dry-run | allowed | no mutation |
| Fake provider create/update (`--provider fake`) | allowed in tests / local | not real Beads |
| Vibe-managed create/update (real Beads) | **Option A:** dual-gated + `--autonomous-managed` + product_ready + safe plan | intended agent autonomy; default gates never live-mutate |
| Unmanaged adoption | forbidden without owner approval | `skip_unmanaged` |
| Duplicate / conflict repair (non-deterministic) | block / repair-plan | `skip_*` / `blocked_repair_required` + `next_actions` |
| Destructive delete / close-as-delete | forbidden by default | `skip_delete_forbidden` |
| `--claim` | forbidden in Vibe adapters | never |

### B2. Hetu / codebase-memory mutations

| Class | Default | Notes |
|---|---|---|
| status / doctor / search / trace / impact / architecture / reindex dry-run | allowed | readonly / plan only |
| reindex `--apply` | owner-confirmed | requires `--expect-plan-binding` + `--confirm-hetu-reindex-apply`; no env dual gate; no global `product_ready` requirement |
| auto_watch config changes | owner-approved | doctor may recommend; never auto-mutate provider config |
| Closeout auto-reindex | forbidden | closeout reports blockers only |

### C. Other boundary mutations (always owner-approved)

- git push
- provider config changes
- broad cleanup / notebook clean

## Approval and scope

**Bounded current-SSOT closeout sync** may run under product closeout rules without a second
owner-approval ceremony when dry-run preconditions pass (see Front/Core / Knowledge specs).

Every **other Class A / C** mutation must be either:

1. explicitly approved by the user in the current conversation, or
2. explicitly scoped by the current phase prompt

For **Class B real Beads create/update**: keep temporary dual gates until autonomous live
apply is productized with focused tests. Do not remove gates casually. Do not invent
per-op user questions for unmanaged/duplicate/conflict — emit CLI envelopes.

For **Class B2 Hetu reindex**: confirmation flags on the apply command are the gate;
default local gates rely on fake/unit coverage (`real_hetu` excluded).

If unsure, **stop and report before mutating**.

## Logging

- Every real mutation must be logged in the phase acceptance report.
- Accidental mutations must be logged, explained, cleaned if safe, and verified with inventory after cleanup.
- Final inventory must be captured after mutation phases.

## Cleanup limits

- Never run broad notebook `clean`.
- Delete only:
  - exact approved titles (acceptance residue helpers), or
  - receipt-owned `superseded` managed source IDs after receipt switch
- Never delete unmanaged sources.
- Never delete by filename heuristic or title prefix alone.

## Redaction

Committed reports must redact:

- raw notebook refs
- raw source IDs
- cookies / tokens / credentials / auth headers / browser storage

Raw source IDs may exist only in local receipt state, not in committed reports.

## ChatGPT Project Sources

Coding agents must not claim to update ChatGPT Project Sources. Owner uploads
`docs/project/vibe-control-spec.md` (and related SSOT docs) manually when needed.
