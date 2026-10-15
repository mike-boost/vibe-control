# Phase 11A — SSOT Specs and Beads Readonly Reconcile

**Status:** Complete for readonly/default safe scope  
**Acceptance:** `acceptance/phase11a/run_phase11a_acceptance.py`  
**Date:** 2026-07-14  
**Depends on:** Phase 10.5 complete for safe/default scope  
**Blocks:** Phase 11B Beads Import / Apply  
**Local repo authoritative spec:** `docs/project/vibe-control-spec.md` (v0.9.1)  
**Implementation plan:** `docs/project/plans/phase11a-ssot-specs-beads-readonly-reconcile-plan.md`  
**Language policy:** Explanation in Chinese; code, commands, config keys, schemas, filenames, module names, and error codes in English.

---

## 0. Positioning

```text
Phase 11A is the next accepted phase after Phase 10.5.
It is readonly with respect to Beads mutation and does not require
real NotebookLM mutation for default acceptance.

Phase 11A proves:
  repo SSOT dogfood
  → knowledge readonly facts (including Knowledge Ask Template / vibe.knowledge.ask.v1)
  → agent reasoning / expected tasks
  → TaskProvider contract + fake provider tests
  → identity / marker / readonly reconcile

Phase 11B (later) may create/update managed Beads tasks with explicit --apply.
```

Phase 11A readonly/default safe scope is **complete** (acceptance + fast + acceptance-readonly + full-readonly gates).

Owner may manually export/upload `docs/project/vibe-control-spec.md` to ChatGPT Project Sources after related repo commits. Coding agents do not update ChatGPT Project Sources.

Ideal dogfood path (accepted):

```text
agent
  → skill(s)  [vibe-control front-door recommended; or compose vibe-knowledge + vibe-implementation]
  → vibe knowledge query / status / sync --dry-run
  → SSOT-backed facts
  → agent reasoning
  → expected implementation tasks (from repo SSOT identity)
  → vibe task reconcile --dry-run
  → readonly diff against task provider state
```

NotebookLM is an information source over SSOT files, not Beads truth and not an oracle for agent judgment.

---

## 1. Problem

After Phase 10.5:

```text
- Skills + CLI boundary exists (doctor / init-preview / --apply gates).
- Knowledge inventory/status/sync/query exist for SSOT → provider path.
- Beads setup/precheck CLI exists (task doctor/status/install-guide/init-preview).
- But:
  - active formal SSOT must be vibe-control-spec.md (registry alignment required)
  - no Beads task identity model from repo SSOT
  - no Vibe-managed marker contract
  - no readonly reconcile report
  - TASK_READY is shallow
  - plan import / apply not implemented (correctly deferred)
```

Without Phase 11A, agents would invent Beads identity and import behavior, or treat NotebookLM synced state as Beads truth.

---

## 2. Product Model

```text
Repo / git SSOT specs     = truth
NotebookLM / provider     = derived read/query layer
Beads                     = implementation task provider
vibe CLI                  = deterministic command surface
Skills                    = thin intelligent routers to CLI
```

Critical principles:

```text
NotebookLM synced is NOT Beads truth.
Repo SSOT specs ARE Beads truth.
Beads task id is binding result, not source identity.
```

---

## 3. Scope

```text
- Dogfood active repo SSOT (vibe-control-spec.md), including Phase 11A/11B roadmap content inside it
- Exercise knowledge workflow:
  config validate → inventory → desired_snapshot → status → sync --dry-run → query routing
- Define TaskProvider / TaskRecord / ManagedMarker / ReconcileReport abstractions
- Start with fake Beads provider tests before real bd list/show dependency
- Define expected-task identity from repo SSOT fields
- Define Vibe-managed marker (body/description footer; vibe.task.v1 schema)
- Define readonly reconcile classes:
  missing / duplicate / stale / conflict / unmanaged
- Extend CLI envelopes / skill routing for readonly reconcile (when implemented)
- Keep all Beads mutation and import --apply out of this phase
```

---

## 4. Non-Scope

```text
- Phase 11B Beads import / create / update / delete
- bd init
- unmanaged Beads task mutation or auto-adopt
- broad Beads cleanup
- daemon / SQLite / RunJournal / workflow replay
- NotebookLM → repo SSOT recovery
- mandatory knowledge sync --apply for Phase 11A acceptance
- claiming ChatGPT Project Sources were updated by coding agents
- packaging/install of vibe-control front-door skill as a required closeout of docs-only prep
  (recommended architecture; implementation later)
```

---

## 5. SSOT Spec Selection

### Active formal SSOT (required)

```text
vibe_control_spec → docs/project/vibe-control-spec.md  (status: active)
```

### Stable extra (allowed)

```text
docs/project/DECISION_LOG.md via knowledge.include_extra
```

### Must not be default SSOT

```text
docs/project/sync/*.md
docs/project/plans/**
docs/project/reviews/**
docs/harness/**
tests/**
scripts/**
acceptance/**
.beads/**
.config/**
runtime/**
agent logs
```

Historical `docs/project/VIBE_CONTROL_V0_5_SPEC.md` is removed from the repo and must not be active SSOT.

---

## 6. Config / Registry Contract

```text
specs.registry + authoritative_statuses (active) → formal specs
knowledge.include_extra → explicit stable docs
knowledge.exclude_globs → exclusions
```

Rules:

```text
- Do not invent registry fields outside existing schema (id, title, status, path).
- Use status values already supported (active / superseded).
- Config files select sources; config files are never sync content.
- Phase sync specs are not default SSOT unless explicitly added later.
```

---

## 7. Knowledge Dogfood Workflow

Required Phase 11A verification path:

```text
1. vibe config validate --json
2. vibe knowledge inventory --json
3. desired_snapshot construction (via inventory/status/doctor internals or publish path)
4. vibe knowledge status --json
5. vibe knowledge sync --dry-run --json
6. vibe knowledge query --question-file <file> --json (status-aware routing)
```

Semantics:

```text
- Query/status/sync --dry-run return SSOT-backed facts, constraints, and associations.
- Agent still performs reasoning and expected-task derivation.
- NotebookLM/provider is derived read/query over SSOT files — not an oracle,
  and not Beads task truth.
- Phase 11A/11B roadmap content lives inside the active SSOT file and is dogfood input.
  Phase sync/plan/review files are NOT default SSOT.
```

Acceptance default:

```text
knowledge sync --apply is NOT required for Phase 11A acceptance.
Real NotebookLM mutation requires separate explicit bounded approval.
```

---

## 8. TaskProvider Contract and Beads Identity Model

### 8.1 TaskProvider abstractions

```text
Beads = task provider
bd    = provider CLI (adapter detail), not agent-facing product interface

Core logic uses:
  TaskProvider
  TaskRecord
  ManagedMarker
  ReconcileReport

Beads adapter may later call bd list / bd show readonly.
Phase 11A starts with fake provider tests before real bd output.
Agents must not call bd directly by default.
```

### 8.2 Expected-task identity

Stable source identity (repo SSOT → expected task):

```text
project_id
ssot_id
ssot_path
ssot_anchor
task_kind
```

```text
managed_key      = derived from the stable SSOT identity tuple
provider_task_id = Beads task id = binding result only
title            = display only (never identity)
relations/deps   = provider data; must not replace managed_key
```

Not identity inputs:

```text
NotebookLM source_id
NotebookLM synced bool alone
raw notebook ref alone
Beads task id alone
task title alone
```

---

## 9. Vibe-Managed Marker

Requirements:

```text
- Deterministic and machine-detectable from readonly provider inspection
- Prefer task body/description footer over title
- Versioned schema (vibe.task.v1)
- Maps to managed_key / SSOT identity fields
- Does not require mutating unmanaged tasks to classify them
```

Accepted example schema:

```text
schema: vibe.task.v1
project_id: vibe-control
task_provider: beads
managed_key: sha256:...
ssot_id: vibe_control_spec
ssot_path: docs/project/vibe-control-spec.md
ssot_anchor: roadmap.phase11a
task_kind: implementation_phase
ssot_snapshot_hash: sha256:...
source_item_hash: sha256:...
managed_by: vibe-control
```

Exact serialization delimiters remain an implementation detail; field set above is accepted prep default.

---

## 10. Readonly Reconcile Model

```text
readonly reconcile = dry-run diff between:
  expected tasks derived from repo SSOT
  actual tasks read from TaskProvider
```

Report classes (minimum):

```text
missing     — expected managed_key has no provider binding
duplicate   — multiple managed tasks map to same managed_key
stale       — managed task exists but snapshot/item/path/anchor drift
conflict    — marker present but identity fields disagree
unmanaged   — provider task without Vibe-managed marker (detect only)
```

Phase 11A does **not** fix:

```text
missing   → does not create
stale     → does not update
duplicate → does not merge
conflict  → does not repair
unmanaged → does not mutate or adopt
```

Unmanaged policy (accepted default): detect + skip/warn; never mutate.  
Delete policy (accepted default): forbidden.

Readonly reconcile must not call `bd init` / create / update / delete.

---

## 11. CLI Command Surface

### Existing (reuse in 11A)

```bash
vibe config validate --json
vibe knowledge inventory --json
vibe knowledge status --json
vibe knowledge sync --dry-run --json
vibe knowledge query --question-file <file> --json
vibe task doctor --json
vibe task status --json
vibe task install-guide --json
vibe task init-preview --json
```

### Future Phase 11A commands (illustrative; not implemented yet)

```bash
vibe task identity preview --json
vibe task reconcile --dry-run --json
```

Must not appear in Phase 11A:

```bash
vibe task import --apply
automated bd init / create / update / delete
```

---

## 12. Skill Routing

Recommended Phase 11 layout (Slice 2 packaged):

```text
vibe-control         = thin front-door workflow order router (no provider logic)
vibe-knowledge       = SSOT-backed facts → knowledge CLI
vibe-implementation  = task workflow → task CLI (readonly in 11A)
```

### `vibe-knowledge`

```text
Prefer inventory/status/doctor/init-preview before claiming SSOT readiness.
Use query for SSOT-backed facts only; never treat NotebookLM as oracle/Beads truth.
Use sync --dry-run when user asks sync without explicit apply.
Never auto-run sync --apply / retry --apply.
```

### `vibe-implementation`

```text
Keep setup routing (doctor/status/install-guide/init-preview).
Route readonly reconcile once CLI exists.
No auto bd init; no inventing apply; Phase 11B only for mutation with explicit --apply.
```

### `vibe-control` (recommended; not packaged yet)

```text
Compose knowledge readonly path before task reconcile dry-run.
Keep skills thin; do not embed provider/adapters.
```

Soft debt: Phase 10.5 text said “exactly two skills”; Phase 11A Slice 2 supersedes packaging to three skills including `vibe-control`.
---

## 13. JSON Envelope Requirements

Reuse Phase 10.5 structured `next_actions`:

```json
{
  "code": "BEADS_RECONCILE_MISSING",
  "command": "vibe task reconcile --dry-run --json",
  "mutation": false,
  "reason": "SSOT identity has no managed Beads binding"
}
```

Phase 11A next_actions for reconcile paths must use `mutation: false`.

---

## 14. Test Spec

### Slice 2 (implemented)

```text
Scope: BeadsReadonlyProvider (bd list/show only), --provider fake|beads,
       vibe-control front-door packaging, skill contract tests,
       Superpowers comparison note
Out of Slice 2: Phase 11B apply, real NotebookLM mutation, worktrees/subagents
```

### Slice 1 (implemented / still required)

```text
Scope: expected-task projection (roadmap.phase11a / roadmap.phase11b),
       managed_key, ManagedMarker parse, FakeTaskProvider, readonly reconcile,
       vibe task reconcile --dry-run --json
Out of Slice 1: real bd list/show adapter, Phase 11B apply, vibe-control front-door packaging
```

### P11A-SSOT-SELECT-001

```text
Purpose: Active formal inventory includes vibe-control-spec.md
Setup: registry marks vibe_control_spec active; v0.5 not active
Command / action: vibe knowledge inventory --json
Expected result: docs/project/vibe-control-spec.md present; VIBE_CONTROL_V0_5_SPEC.md absent as active
Mutation allowed?: no
```

### P11A-SSOT-EXCLUDE-001

```text
Purpose: Default exclusions keep plans/reviews/sync/config/.beads out of SSOT
Setup: default config + registry
Command / action: inventory / desired_snapshot build
Expected result: excluded paths not selected unless explicitly configured
Mutation allowed?: no
```

### P11A-SNAPSHOT-001

```text
Purpose: desired_snapshot builds from selected SSOT files
Setup: valid config + active registry entry + DECISION_LOG include_extra
Command / action: knowledge doctor / status / publish dry path that builds snapshot
Expected result: snapshot includes selected ids/paths/hashes; config not included
Mutation allowed?: no
```

### P11A-KNOWLEDGE-STATUS-001

```text
Purpose: knowledge status emits state-specific next_actions
Setup: fixture or live readonly status
Command / action: vibe knowledge status --json
Expected result: sync_state + structured next_actions; no pretend synced without evidence
Mutation allowed?: no
```

### P11A-KNOWLEDGE-DRYRUN-001

```text
Purpose: sync --dry-run does not mutate provider
Setup: allow-listed notebook env or fixture adapter
Command / action: vibe knowledge sync --dry-run --json
Expected result: preview/plan only; no source add/update/delete
Mutation allowed?: no
```

### P11A-QUERY-ROUTE-001

```text
Purpose: query respects synced/pending/drift/unavailable routing
Setup: fixtures covering each sync_state
Command / action: vibe knowledge query --question-file <file> --json
Expected result: mode/provider match status; pending/drift not look like synced
Mutation allowed?: no
```

### P11A-IDENTITY-001

```text
Purpose: identity derived from repo SSOT fields only
Setup: SSOT candidate docs / anchors
Command / action: identity preview (future CLI) or unit builder
Expected result: identity includes project_id/ssot_id/ssot_path/ssot_anchor/task_kind; managed_key derived
Mutation allowed?: no
```

### P11A-IDENTITY-002

```text
Purpose: provider_task_id is not required for candidate identity
Setup: candidate without Beads binding
Command / action: identity preview / unit builder
Expected result: candidate identity valid without provider_task_id; title not used as identity
Mutation allowed?: no
```

### P11A-MARKER-001

```text
Purpose: Vibe-managed marker is detectable without mutating unmanaged tasks
Setup: fixture managed + unmanaged task records
Command / action: marker detector
Expected result: managed true/false classification correct
Mutation allowed?: no
```

### P11A-RECONCILE-001

```text
Purpose: readonly reconcile reports five classes
Setup: fixtures for missing/duplicate/stale/conflict/unmanaged
Command / action: vibe task reconcile --dry-run --json (future)
Expected result: all five classes represented when present; counts stable
Mutation allowed?: no
```

### P11A-READONLY-001

```text
Purpose: reconcile/doctor/status never call bd init/create/update/delete
Setup: mocked Beads probe
Command / action: doctor/status/reconcile dry-run
Expected result: no mutation calls; envelopes mutation=false
Mutation allowed?: no
```

### P11A-NO-APPLY-001

```text
Purpose: Phase 11A has no import --apply surface
Setup: CLI help / argparse inventory
Command / action: inspect CLI surface
Expected result: no task import --apply command in 11A
Mutation allowed?: no
```

### P11A-SKILL-001

```text
Purpose: vibe-implementation routes readonly reconcile; forbids auto mutation
Setup: skill content tests
Command / action: content assertions / router table checks
Expected result: readonly routes present; no auto bd init/create/apply
Mutation allowed?: no
```

---

## 15. Acceptance Criteria

```text
[ ] SSOT selection for dogfood inventory-verified (vibe-control-spec.md active)
[ ] desired_snapshot builds for selected SSOT files
[ ] knowledge status / sync --dry-run / query routing evidenced
[x] TaskProvider + fake provider tests land before real bd dependency
[x] Expected-task identity (project_id/ssot_id/ssot_path/ssot_anchor/task_kind + managed_key) test-locked
[x] Vibe-managed marker (body/footer; vibe.task.v1) detection test-locked
[x] readonly reconcile reports missing/duplicate/stale/conflict/unmanaged without fixing
[x] no Beads create/update/delete/init in Phase 11A
[x] no claim that Phase 11B is done
[x] skills remain thin routers (optional vibe-control front-door packaging may land with impl)
[x] default gates pass without real NotebookLM/Beads mutation
```

Phase 11A readonly/default safe scope acceptance is complete. Phase 11B is not started.

---

## 16. Open Decisions

Still open for implementation:

```text
1. Exact managed_key hash serialization bytes / canonical encoding
2. Whether plan docs may enter identity scope later (default: specs-first / SSOT-content anchors)
3. Marker footer delimiters / exact text fencing
4. Duplicate definition details (same managed_key vs same ssot_path+anchor different hash)
5. Stale definition details (snapshot/item hash vs path/anchor drift)
6. Conflict definition details
7. Whether readonly reconcile requires live bd list probe always (fake provider first)
8. Whether Phase 6 acceptance drift debt is fixed before/during/after 11A impl
9. Phase 11B: allow create? allow update managed? (defaults lean yes with --apply)
10. Confirm delete remains forbidden in 11B unless separately accepted
11. Future command names for identity preview / reconcile
12. When to expand skills packaging to install vibe-control front-door
```

Accepted defaults already locked:

```text
- Repo SSOT specs are truth; NotebookLM is derived read/query
- Provider_task_id / Beads task id is binding result only
- Title is display only; relations do not replace managed_key
- Marker prefers body/description footer; vibe.task.v1 field set accepted
- Unmanaged: detect + skip/warn; never mutate / never auto-adopt
- Delete forbidden by default
- knowledge sync --apply not required for 11A acceptance
- Phase 11A readonly reconcile never fixes
- Phase 11B for import/apply with explicit --apply
- Fake TaskProvider tests before real bd dependency
- Agent goes through skills → vibe CLI (not raw NotebookLM / not raw bd by default)
```

---

## 17. Implementation Sequence

```text
0. Spec prep clarifications (docs) — accepted; not implemented
1. Owner starts implementation session
2. Tests first: TaskProvider fake + identity + marker + reconcile readonly contracts
3. CLI surface for identity preview + reconcile --dry-run
4. Skill routing updates (+ optional vibe-control front-door packaging)
5. Knowledge dogfood evidence (dry-run default)
6. Readonly acceptance
7. Stop — Phase 11B separate
```

---

**End of Phase 11A Spec (Accepted scope / Not implemented)**
