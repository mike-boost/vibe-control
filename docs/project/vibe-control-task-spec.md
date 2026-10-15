# Vibe Control Task Spec

**Document type:** Formal provider-layer spec (task / Beads)  
**Status:** v1.1 — local_embedded_ephemeral default task cache mode  
**Date:** 2026-07-15  
**Primary audience:** Coding agents, repository maintainers  
**Language policy:** Explanation in Chinese; code/commands/schemas in English.  
**Front/Core:** `docs/project/vibe-control-spec.md`  
**Companions:** `docs/project/vibe-control-knowledge-spec.md`,
`docs/project/vibe-control-hetu-spec.md` (code-structure; design)

---

## 1. Role / default mode

```text
default task mode = local_embedded_ephemeral

Repo SSOT specs     = truth for expected tasks
Beads               = local embedded, stage-scoped, agent-only task cache (derived)
provider_task_id    = binding result only (never source identity)
managed_key         = stable Vibe-managed task identity
FakeTaskProvider    = tests/local only
```

Beads is **not**:

- repo truth
- GitHub collaboration data
- durable project fact that must be committed
- team/shared/server/Dolt remote mode (out of current scope)

Phase/feature completion facts must be written to repo specs / `DECISION_LOG` / tests
**before** clearing the local task cache.

Agents use `vibe task *` / `vibe implementation *`; do not call raw `bd` by default.

---

## 2. TaskProvider

Core abstractions:

```text
TaskProvider
TaskRecord
ManagedMarker (vibe.task.v1)
ReconcileReport
ApplyPlan / ApplyOperation
task cache state (local_embedded_ephemeral)
```

Beads readonly default path: `list` / `show` / `ready` / `status` / `version` (never `--claim`).

`bd prime` remains allowlisted as a non-default provider-local context helper only.

---

## 3. Expected-task identity

Stable tuple:

```text
project_id
ssot_id
ssot_path
ssot_anchor
task_kind
```

```text
managed_key = hash(stable SSOT identity tuple)
title / relations / deps = never identity
```

Status-aware projection reads `phase_state` + `actionable` + `next_actionable_task`
from `docs/project/vibe-control-roadmap-state.md` (not from Front/Core body churn).
Completed anchors are never default next actionable tasks.
`vibe implementation next --json` reports `no_actionable_next_task=true` when none remain
(do not invent Phase 13). Explicit `vibe implementation prompt --task <completed-anchor>`
may return a safe envelope with completed / do not restart warning.

---

## 4. Marker (vibe.task.v1)

Prefer body/description footer. Includes managed_key, SSOT fields, hashes, `managed_by: vibe-control`.

---

## 5. Readonly reconcile

Categories: `matched` / `missing` / `stale` / `duplicate` / `conflict` / `unmanaged`.

Unavailable provider → `mode=unavailable`; do not invent real missing diffs.

CLI: `vibe task reconcile --dry-run --json --provider fake|beads`.

---

## 6. Default local ephemeral handling

| Category | Default handling |
|---|---|
| matched | ok |
| stale | update managed (safe convergence) |
| missing | create managed (safe convergence) |
| unmanaged | cache pollution → reset/regenerate preferred |
| duplicate | cache pollution → reset/regenerate preferred |
| conflict | cache pollution → reset/regenerate preferred |
| provider unavailable | block |

Do not design complex repair/adoption for default mode.
Do not ask the user ad hoc how to handle local ephemeral cache pollution.
CLI emits structured `next_actions` only.

Individual task delete is not the user-facing default. Prefer:

```text
vibe task cache reset --dry-run --json --provider beads
vibe task cache reset --apply --json --provider beads
# local_embedded_ephemeral only; clears Vibe-managed namespace then regenerates actionable projection
# team/shared/server modes fail closed; no per-conflict repair
```

---

## 7. Apply plan / safe convergence

Maps reconcile → operations (`create_managed` / `update_managed` / skips…).

Bound by `plan_binding_hash`.

Safe managed create/update may proceed when knowledge half is ready and the plan is
safe create/update only — **even if** full `product_ready=false` solely because the
task cache is not current (breaks circular dependency).

Live Beads still requires temporary dual gate + `--autonomous-managed`.

---

## 8. product_ready — task half + cache current

```text
task_available=true
task_readable=true
ready_queue_available=true (when probed)
task_cache_current=true
```

`task_cache_current` requires:

```text
missing=0, stale=0, duplicate=0, conflict=0, unmanaged=0
apply dry-run create=0, update=0, blocked=0
```

Closeout must not accept Beads stale as soft debt.

When not current, envelopes expose:

```text
task_cache_mode=local_embedded_ephemeral
task_cache_current=false
task_cache_action_required=true
safe_task_convergence_allowed=true|false
task_cache_reset_required=true|false
next_actions
```

---

## 9. Fields used by Phase 12 prompt generator

Prompt may include managed_key / ssot_anchor / readiness / task_cache fields.
When `task_cache_current=false`, prompt must **not** greenlight next implementation;
it must instruct convergence or reset/regenerate first.

---

## 10. Phase/dev specs

Historical detail: `docs/project/sync/phase11a-*.md`, `phase11b-*.md`, harness contracts.
Not default ChatGPT Project Sources.
