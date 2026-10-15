# Phase 11A — SSOT Specs and Beads Readonly Reconcile Plan

**Status:** Accepted roadmap plan / Phase 11A readonly closeout complete (incl. Knowledge Ask Template + full readonly gate); Phase 11B not authorized  
**Date:** 2026-07-14  
**Phase spec:** `docs/project/sync/phase11a-ssot-specs-beads-readonly-reconcile-spec.md`  
**Local repo authoritative spec:** `docs/project/vibe-control-spec.md` (v0.9.1)  
**Companion assessment:** `docs/project/reviews/20260714-phase11a-route-recovery-and-assessment.md`  
**Does not authorize:** starting Phase 11A implementation in this prep commit

---

## 1. Objective

```text
1. Dogfood active repo SSOT (vibe-control-spec.md), including 11A/11B roadmap content inside it.
2. Exercise knowledge workflow for SSOT-backed facts:
   inventory → desired_snapshot → status → sync --dry-run → query
3. Define TaskProvider abstractions + fake provider tests first.
4. Define expected-task identity / managed_key / Vibe-managed marker.
5. Define readonly reconcile report (never fixes in 11A).
6. Keep all Beads mutation and plan import apply out of Phase 11A.
```

Ideal dogfood path:

```text
agent → skill(s) → knowledge readonly CLI → SSOT-backed facts
  → agent reasoning → expected tasks → task reconcile --dry-run
```

Product model:

```text
Repo / git SSOT specs     = truth
NotebookLM / provider     = derived read/query layer
Beads                     = implementation task provider
vibe CLI                  = deterministic command surface
Skills                    = thin intelligent routers to CLI
```

```text
NotebookLM synced is NOT Beads truth.
Repo SSOT specs ARE Beads truth.
provider_task_id is binding result, not source identity.
```

---

## 2. Non-Scope

```text
- Phase 11B plan import apply
- Beads task create / update / delete
- bd init
- unmanaged Beads task mutation / auto-adopt
- broad Beads cleanup
- daemon / SQLite / RunJournal / workflow replay
- NotebookLM → repo SSOT recovery
- mandatory real NotebookLM mutation smoke
- updating ChatGPT Project Sources (owner may upload local spec manually)
```

---

## 3. Current Baseline

### Accepted / implemented

```text
Phase 10.5 closeout
knowledge doctor / init-preview
task doctor / status / install-guide / init-preview
structured next_actions
skills install --apply gate
knowledge retry fail-closed
two packaged skills: vibe-knowledge, vibe-implementation
```

### SSOT / registry

```text
active: vibe_control_spec → docs/project/vibe-control-spec.md
include_extra: docs/project/DECISION_LOG.md
```

### Beads baseline (pre-11A implementation)

```text
setup/precheck CLI exists
no TaskProvider / identity / reconcile CLI
TASK_READY shallow
plan_import.implemented=false
```

---

## 4. Proposed Workflow

```text
SSOT selection (registry + include_extra)
  → desired_snapshot
  → knowledge status / sync --dry-run / query
  → agent reasoning over SSOT-backed facts
  → expected tasks (project_id/ssot_id/ssot_path/ssot_anchor/task_kind → managed_key)
  → readonly reconcile vs TaskProvider
  → report missing/duplicate/stale/conflict/unmanaged
  → stop (no apply)
```

---

## 5. SSOT Spec Structure

```text
Keep docs/project/ as home for the formal local repo authoritative spec + registry.
Active formal SSOT content (including Phase 11A/11B roadmap) is dogfood input.
Phase sync/plan/review files are not default SSOT.
```

---

## 6. Config / Registry Model

```text
specs.registry + authoritative_statuses  → formal specs
knowledge.include_extra                  → explicit stable docs
knowledge.exclude_globs                  → exclusions
```

---

## 7. Knowledge Sync Exercise

```text
config validate → inventory → status → sync --dry-run → query
```

```text
knowledge sync --apply is NOT required for Phase 11A acceptance.
```

---

## 8. Beads Identity Model

```text
project_id / ssot_id / ssot_path / ssot_anchor / task_kind
managed_key = derived from that tuple
provider_task_id = binding result only
title = display only
relations = provider data; do not replace managed_key
```

---

## 9. Vibe-Managed Marker

Prefer body/description footer; `vibe.task.v1` field set (see phase spec §9).

---

## 10. Readonly Reconcile Model

Dry-run diff only; never create/update/merge/repair/adopt in Phase 11A.

---

## 11. CLI Command Surface

Reuse knowledge/task doctor/status. Future: `task identity preview`, `task reconcile --dry-run`.

---

## 12. Skill Routing Changes

```text
Current: vibe-knowledge + vibe-implementation + vibe-control front-door
Never auto-run --apply / bd init
Do not call NotebookLM or bd directly by default
```

---

## 13. JSON Envelope Requirements

Phase 10.5 structured next_actions; Phase 11A reconcile advisories use `mutation: false`.

---

## 14. Test Spec

See phase spec §14 (`P11A-*`). Prefer fake TaskProvider fixtures first.

---

## 15. Acceptance Criteria

See phase spec §15.

---

## 16. Open Decisions

```text
1. managed_key canonical encoding
2. plan docs in identity scope later?
3. marker footer fencing
4. duplicate / stale / conflict detail rules
5. live bd probe always vs fake-first (fake-first accepted)
6. Phase 6 acceptance drift timing
7. 11B create/update defaults (lean yes + --apply)
8. delete remains forbidden?
9. CLI command final names
10. when to package vibe-control front-door
```

Locked:

```text
identity tuple; managed_key; binding-only provider_task_id;
marker body/footer preference; readonly never fixes;
unmanaged skip/warn; delete forbidden; sync --apply not 11A acceptance gate
```

---

## 17. Risks

```text
1. Treating NotebookLM synced as Beads readiness
2. Calling bd directly from agents
3. Title/relations used as identity
4. Reconcile without fake provider tests
5. Collapsing 11A+11B into one apply phase
6. Skill packaging lag for vibe-control front-door
```

---

## 18. Implementation Sequence

```text
0. Spec prep clarifications (this session) — stop
1. Next implementation session: fake TaskProvider + identity/marker/reconcile
2. Readonly acceptance
3. Separate Phase 11B session later
```

Owner may manually export/upload `docs/project/vibe-control-spec.md` to ChatGPT Project Sources after this repo commit.

---

**End of Phase 11A Plan (Accepted roadmap / Not implemented)**
