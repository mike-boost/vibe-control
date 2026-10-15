# Phase 11B — Beads Import / Apply Spec

**Status:** Option A autonomous managed apply productized — temporary dual gate retained  
**Depends on:** Phase 11A readonly reconcile (`vibe task reconcile --dry-run`)

## 1. Product framing

Vibe Control is an **agent-facing, provider-backed** product:

- Agents self-manage normal Vibe-managed create/update via CLI/harness (no per-op user ceremony).
- Humans approve boundary-level decisions (NLM sync apply, push, delete, unmanaged adoption, etc.).
- Repo SSOT is truth; Beads is the local persistent task provider; fake provider is tests-only.
- Provider ids are binding results; `managed_key` is stable identity.

## 2. Option A vs Option B

| | Option A (this baseline) | Option B (future) |
|---|---|---|
| Safe managed create/update policy | autonomous when product_ready + safe plan | same |
| Live Beads unlock | dual gate + `--autonomous-managed` + product_ready + safe plan | product_ready + safe plan only |
| Default gates | never set live env / never mutate | same |
| Unsafe ops | skip/block/repair-plan + next_actions | same |

**Remaining delta to Option B:** remove `VIBE_BEADS_LIVE_APPLY` + `--confirm-beads-live-apply` after stronger integration tests prove safe-plan + readiness alone is sufficient.

## 3. Autonomous managed apply requirements

Live apply is allowed only when ALL hold:

1. `product_ready=true` (knowledge synced + ask-clean; task readable/ready)
2. `plan_binding_hash` current (or omitted)
3. executable ops are only `create_managed` / `update_managed`
4. no executable unmanaged/duplicate/conflict/delete
5. `--autonomous-managed`
6. `--confirm-beads-live-apply`
7. `VIBE_BEADS_LIVE_APPLY=1`

CLI:

```text
VIBE_BEADS_LIVE_APPLY=1 vibe task apply --apply --json --provider beads \
  --autonomous-managed --confirm-beads-live-apply
```

## 4. Status-aware projection

| Catalog entry | actionable | Default apply |
|---|---|---|
| `roadmap.phase11a` | no | skip_completed / optional_backfill_completed |
| `roadmap.phase11b` (shell) | no | skip_completed / optional_backfill_completed |
| `roadmap.phase11b.live_apply` | yes | create_managed if missing |
| `roadmap.phase11b.post_create_verify` | yes | create_managed if missing |
| `roadmap.phase11b.update_path_validation` | yes | create_managed if missing |
| `roadmap.phase11b.provider_closeout` | yes | create_managed if missing |
| `roadmap.phase12` | yes (pending) | create_managed if missing |

## 5. Unsafe cases

- unmanaged → `skip_unmanaged` (never adopt)
- duplicate → `skip_duplicate`
- conflict → `skip_conflict` + `blocked_repair_required`
- delete → `skip_delete_forbidden`
- All emit structured `next_actions` (never ad hoc user Q&A)

## 6. Fake-provider first

Implement and prove apply against `FakeTaskProvider` before any live Beads.
Fake provider is tests/local only; real Beads is the local persistent task provider.

## 7. bd argv boundary

Verified against `bd` 1.1.0 help:

- create: `--description`, `--metadata`, `--spec-id`, `--silent`
- update: `--title`, `--description`, `--metadata`, `--spec-id`
- never: `delete`, `close`, `--claim`

## 8. Acceptance

`acceptance/phase11b/run_phase11b_acceptance.py`: fake/local only; pops `VIBE_BEADS_LIVE_APPLY`; no real Beads mutation in default gates.

## 9. Owner / Project Source note

Coding agents must not claim to update ChatGPT Project Sources.
