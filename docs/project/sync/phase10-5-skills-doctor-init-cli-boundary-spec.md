# Phase 10.5 — Skills, Doctor, Init, and CLI Boundary Hardening

**Status:** Implemented + closeout-validated for safe/default scope (2026-07-14)  
**Closeout report:** `docs/project/reviews/20260714-phase10-5-closeout-validation.md`  
**Date:** 2026-07-14  
**Depends on:** Phase 8.0 / 9 / 10 closed for readonly/default safe scope  
**Blocks:** Phase 11A SSOT Specs and Beads Readonly Reconcile  
**Input evidence:** `docs/project/reviews/20260714-skills-cli-current-state-assessment.md`  
**Language policy:** Explanation in Chinese; code, commands, config keys, schemas, filenames, module names, and error codes in English.

---

## 0. Positioning

```text
Phase 10.5 is a small, required hardening phase before Phase 11.
It does not re-implement Phase 8 sync, Phase 9 publish, or Phase 10 query.
It hardens the product boundary:

  Vibe Control = skills + CLI
```

| Layer | Role |
|---|---|
| CLI | Deterministic command surface, validation, state checks, provider adapters, JSON envelopes, tests |
| Skills | Thin but intelligent routers: call CLI, interpret JSON envelopes, choose the next **safe** action |

Hard rules for this phase:

```text
1. Skills stay thin.
2. Skills may be intelligent routers.
3. Skills may automatically run readonly commands.
4. Skills must never automatically run mutation commands.
5. Core provider / sync / task logic belongs in CLI + tests.
6. CLI must emit enough stable JSON for skills to choose the next safe action.
7. All mutation requires explicit user approval and an explicit apply-style flag,
   unless an exception is deliberately documented (Phase 10.5 prefers no exception
   for skills install — see Option A).
```

Doctor / init / install model (canonical):

```text
doctor / precheck       = readonly health check
init-preview            = readonly setup plan
install-guide           = readonly human-readable setup guidance
install / init --apply  = controlled mutation
```

---

## 1. Current Problem

Evidence from assessment (`docs/project/reviews/20260714-skills-cli-current-state-assessment.md`):

```text
- Skills are correctly named (vibe-knowledge, vibe-implementation) and thin — good.
- Skills are not yet intelligent routers (no decision tables).
- knowledge CLI is relatively mature (status/sync/retry/reindex/query).
- task/Beads CLI is weak: task status returns NOT_IMPLEMENTED when bd is installed.
- Missing formal commands: knowledge doctor, knowledge init-preview, task doctor.
- skills install mutates by default (--dry-run preview only); no --apply gate.
- knowledge status has useful data.sync_state, but top-level next_actions are static.
- Stale “Phase 3 safe_to_sync=false” wording still appears in integration/provider paths.
```

Without Phase 10.5, Phase 11 agents will invent Beads/routing behavior outside CLI, violating the skills + CLI model.

---

## 2. Product Model: Skills + CLI

```text
Repo / git SSOT files     = truth
NotebookLM / provider     = derived read/query layer (current knowledge provider)
Repo fallback             = degraded read/query when provider is not current
Beads                     = current task provider (minimal until Phase 11)
vibe CLI                  = deterministic command surface
Skills                    = thin intelligent routers over CLI JSON envelopes
```

Provider names (NotebookLM, Beads) are **implementation details**. Skill abstraction stays product-oriented:

```text
vibe-knowledge        ≠ notebooklm-skill
vibe-implementation   ≠ beads-skill
```

Do not rename skills to provider-branded names.

---

## 3. Scope

In scope for Phase 10.5:

```text
- Formalize doctor / init-preview / install-guide / --apply gate matrix
- Add vibe knowledge doctor --json
- Add vibe knowledge init-preview --json
- Add vibe task doctor --json
- Harden vibe task status --json (ready / not_ready / unavailable; no NOT_IMPLEMENTED when bd installed)
- Structured or stable state-specific next_actions for skill routing
- Upgrade SKILL.md files to thin decision routers (tables only; no duplicated business logic)
- Introduce skills install --apply gate (Option A)
- Remove or replace misleading stale “Phase 3 safe_to_sync remains false” messaging
- Align retry/sync flag defaults documentation (and prefer consistent fail-closed behavior)
- Test Spec + default-gate tests (fake/readonly only)
- Update local repo authoritative spec to list Phase 10.5 as required before Phase 11A
```

---

## 4. Non-Scope

Explicitly out of scope:

```text
- Phase 11A / 11B Beads identity, readonly reconcile, import / apply
- Phase 12 implementation prompt generator
- Real NotebookLM source add/delete/update/rename/clean in default gates
- bd init mutation from vibe CLI (CLI may preview only; never auto-init)
- Creating Beads tasks
- Native NotebookLM remote note read/write (Phase 8.1)
- Rewriting Phase 8 apply lifecycle / receipt identity model
- Broad cleanup, unmanaged source delete, daemon, SQLite, RunJournal
- Renaming skills to provider-branded names
```

---

## 5. Skill Inventory and Naming

| Skill | Abstraction | Current provider detail (non-dominant) |
|---|---|---|
| `vibe-knowledge` | knowledge / SSOT files / desired_snapshot / ProviderTarget / query / sync router | NotebookLM |
| `vibe-implementation` | task / implementation workflow / checkpoint-resume router | Beads |

Rules:

```text
- Exactly these product skills remain in V1 packaging (SKILL_NAMES):
  vibe-control, vibe-knowledge, vibe-implementation
  (Phase 10.5 shipped two skills; Phase 11A Slice 2 adds vibe-control front-door)
- Repo-owned sources live under src/vibe_control/skills/<name>/SKILL.md.
- Install target remains ~/.agents/skills (symlink preferred).
- Skills must not grow into long static manuals.
- Skills must include explicit routing tables (see §8).
- Skills must call CLI and interpret JSON envelopes; they must not reimplement
  sync_state, receipt, ProviderTarget, Beads probe, or git safety rules.
```

---

## 6. CLI Command Contract

### 6.1 Readonly commands (skills may auto-run)

```bash
vibe doctor --json
vibe config validate --json
vibe integration status --json
vibe integration doctor --json
vibe skills status --json
vibe knowledge doctor --json
vibe knowledge init-preview --json
vibe knowledge status --json
vibe knowledge inventory --json
vibe knowledge auth-status --json
vibe knowledge login-guide --json
vibe knowledge sync --dry-run --json
vibe knowledge sync-preview --json
vibe knowledge reindex-bindings --dry-run --json   # add dry-run if not present; otherwise document readonly default carefully
vibe task doctor --json
vibe task status --json
vibe task install-guide --json
vibe task init-preview --json
```

Also readonly (already exist; skills may use when relevant):

```bash
vibe knowledge query --question-file <file> --json
vibe knowledge remote-status --json
vibe knowledge remote-inventory --json
vibe knowledge receipt status --json
vibe config inspect --json
```

### 6.2 Mutation commands (skills must never auto-run)

```bash
vibe knowledge sync --apply --json
vibe knowledge retry --apply --json
vibe skills install --apply --json
vibe task init --apply --json          # NOT required in Phase 10.5; document as future-only if added later
```

Related existing mutation paths (unchanged ownership; still never skill-auto):

```bash
vibe spec publish ... --sync-apply --json
acceptance-only seed / smoke / residue helpers
```

### 6.3 skills install --apply gate (Option A — preferred)

```text
Option A (required for Phase 10.5 unless implementation proves unsafe):
  - vibe skills install --dry-run --json     → plan only
  - vibe skills install --apply --json       → controlled mutation (symlink/copy)
  - vibe skills install --json (no flag)     → fail closed with
      code=SKILLS_INSTALL_REQUIRES_DRY_RUN_OR_APPLY
    OR emit compatibility warning + refuse mutation (must not silently mutate)

Compatibility:
  - Old “default mutates” behavior is removed for safety alignment with knowledge sync.
  - Document migration in Project Source / README when implementing.
```

Option B (documented exception keeping default mutation) is **rejected** by this spec unless a later decision explicitly overrides §18.

---

## 7. Doctor / Init / Install Model

| Command family | Semantics | Mutation |
|---|---|---|
| `* doctor` | Readonly health / precheck aggregation | no |
| `* init-preview` | Readonly setup plan with next steps | no |
| `* install-guide` | Readonly human install guidance | no |
| `* install --apply` / `* init --apply` / `sync --apply` / `retry --apply` | Controlled mutation | yes, explicit only |

Layering guidance for skills:

```text
Global shallow check     → vibe doctor --json
Integration deep check   → vibe integration doctor --json (auth probe ok)
Knowledge domain check   → vibe knowledge doctor --json
Task domain check        → vibe task doctor --json
Knowledge setup plan     → vibe knowledge init-preview --json
Task setup plan          → vibe task init-preview --json
Tool install guidance    → vibe task install-guide --json / vibe knowledge login-guide --json
```

`init-preview` must never upload, never write provider sources, never run `bd init`, never write `~/.agents/skills`.

---

## 8. Skill Autonomy Rules

### 8.1 Global autonomy

```text
ALLOWED without extra user approval:
  readonly doctor / status / validate / auth-status / login-guide /
  install-guide / init-preview / sync-preview / sync --dry-run / query

FORBIDDEN without explicit user request to set up / install / initialize / sync / retry / apply:
  sync --apply
  retry --apply
  skills install --apply
  bd init (or vibe task init --apply if ever added)
  any real NotebookLM source add/delete/update/rename/clean
  creating Beads tasks
```

A skill may **recommend** a mutation command in `next_actions` / user-facing text only when the user explicitly asked for that class of action.

### 8.2 `vibe-knowledge` routing table

| User intent | Skill action | Mutation |
|---|---|---|
| Ask whether knowledge is ready | `vibe knowledge doctor --json` | no |
| Ask whether NotebookLM / provider is synced | `vibe knowledge status --json` | no |
| Ask a knowledge question | `vibe knowledge query --question-file <file> --json` (CLI router handles provider/fallback); if setup failure, explain envelope `next_actions` | no |
| Ask to sync **without** explicit mutation approval | `vibe knowledge sync --dry-run --json` (or `sync-preview`); show plan; require explicit approval before `--apply` | no |
| Explicitly ask to sync / apply | `vibe knowledge sync --apply --json` | yes (user-approved) |
| Ask to retry failed sync **without** explicit mutation | dry-run/preview path only (`retry` without `--apply` must remain non-mutating) | no |
| Explicitly ask to retry / apply failed sync | `vibe knowledge retry --apply --json` | yes (user-approved) |
| Auth / setup problem | `vibe knowledge init-preview --json` and/or `auth-status` / `login-guide` | no |
| Receipt missing / binding drift (user asks how to repair) | recommend `reindex-bindings` dry-run/readonly plan first; `--apply`-style repair only if user explicitly requests | default no |
| Inventory / SSOT listing | `vibe knowledge inventory --json` | no |

### 8.3 `vibe-implementation` routing table

| User intent | Skill action | Mutation |
|---|---|---|
| Ask whether implementation workflow is ready | `vibe task doctor --json` | no |
| Ask task status | `vibe task status --json` | no |
| Beads binary missing | `vibe task install-guide --json` | no |
| `.beads` missing / not initialized | `vibe task init-preview --json` | no |
| Explicitly ask to initialize Beads | show `init-preview` recommendation; **do not** auto-run `bd init`; require explicit user approval outside Phase 10.5 auto-routing | no auto |
| Ask to create / import / reconcile implementation plan | report Phase 11 not yet implemented; point to Phase 11 spec when present | no |
| Config validation needed | `vibe config validate --json` / `vibe doctor --json` | no |

Typo note: directory is `.beads`, never `.beeds`.

---

## 9. JSON Envelope Requirements

Compatible with current envelope shape (`ok`, `command`, `project_id`, `mode`, `data`, `error`, `warnings`, `next_actions`, optional `partial_success`).

Phase 10.5 requires **machine-readable next actions** sufficient for skill routing.

### 9.1 Target shape

```json
{
  "ok": true,
  "command": "vibe knowledge doctor",
  "project_id": "vibe-control",
  "mode": "readonly",
  "data": {},
  "warnings": [],
  "next_actions": [
    {
      "code": "CONFIG_CREATE_REQUIRED",
      "command": "vibe knowledge init-preview --json",
      "mutation": false,
      "reason": "Primary control config is missing"
    }
  ],
  "error": null
}
```

Compatibility allowance:

```text
- Existing string next_actions MAY remain during transition if duplicated structured
  objects are also present, OR strings must follow a stable parseable convention.
- Preferred end state: list of objects with {code, command, mutation, reason}.
- mode SHOULD distinguish: readonly | dry_run | mutation | degraded | unavailable
  (existing modes like local/pending/drift may map into data.sync_state + mode).
```

### 9.2 Required state-specific next_action codes

At least these codes must be producible by the relevant doctor/status/init-preview commands:

| Code | Typical command producers | mutation in recommended next step |
|---|---|---|
| `CONFIG_NOT_FOUND` | config validate, knowledge doctor, init-preview | false (point to template / init-preview) |
| `PROVIDER_UNAVAILABLE` | knowledge/task doctor, status | false |
| `NOTEBOOK_ALIAS_UNRESOLVED` | knowledge doctor / init-preview | false |
| `AUTH_MISSING` | knowledge doctor / auth-status / init-preview | false (login-guide) |
| `RECEIPT_MISSING` | knowledge status / doctor | false by default; may recommend reindex/sync with mutation=true only as advisory when user already asked to repair |
| `PENDING_SYNC_EXISTS` | knowledge status / doctor | false unless user asked to retry/apply |
| `DRIFT_EXISTS` | knowledge status / doctor | false unless user asked to sync/apply |
| `TARGET_MISMATCH` | knowledge status / doctor | false (fail closed; do not mutate wrong target) |
| `BEADS_NOT_INSTALLED` | task doctor / status / install-guide | false |
| `BEADS_NOT_INITIALIZED` | task doctor / status / init-preview | false |
| `TASK_PROVIDER_NOT_CONFIGURED` | task doctor / status | false |

`knowledge status` must stop emitting only the same three static string next_actions regardless of `data.sync_state`. State-specific codes above are mandatory for Phase 10.5 acceptance.

---

## 10. Knowledge-Side Requirements

### 10.1 `vibe knowledge doctor --json` (new, readonly)

Aggregated domain precheck. Must not mutate provider or local binding receipts.

`data` SHOULD include (names indicative; keep nested objects stable):

```text
- config.exists / config.valid / config.path
- project_id
- knowledge provider configured (adapter present)
- notebook.allow_list_present
- notebook.default_alias
- notebook.default_alias_resolves
- notebook.ref_env_present (without printing raw secret values)
- provider.adapter_import_ok
- auth probe summary (reuse auth-status semantics; redact secrets)
- remote probe/inventory summary when safe (readonly); else skipped + reason
- desired_snapshot.build_ok / snapshot_hash (or build error code)
- receipt.present
- pending_sync.present
- sync_state summary for resolved ProviderTarget
```

`next_actions` must be state-specific (§9.2).

### 10.2 `vibe knowledge init-preview --json` (new, readonly)

Readonly setup plan. Must not upload, must not write receipts, must not login automatically.

Must produce next steps for:

```text
- missing config
- missing notebook alias
- missing env/ref
- missing auth
- missing receipt
- pending sync
- drift
```

Each step lists a recommended **readonly** command first; mutation commands appear only as `mutation: true` advisories clearly labeled as requiring explicit user approval.

### 10.3 Existing knowledge commands (hardening only)

```text
- knowledge status: state-specific next_actions; keep target-scoped sync_state
- knowledge sync: keep fail-closed without --dry-run/--apply
- knowledge retry: prefer same fail-closed model as sync (no silent default apply);
  if default dry-run remains, document it and ensure skill table uses it safely
- reindex-bindings: add --dry-run if missing; never restores SSOT files from provider
- inventory: continues to list selected SSOT files; may optionally include snapshot_hash
- query: remains status-aware readonly; no auto mutation
```

### 10.4 Stale Phase 3 messaging

Replace misleading `safe_to_sync remains false in Phase 3` user-facing next_actions/messages with accurate post–Phase 8 semantics, e.g.:

```text
safe_to_sync is false until explicit sync --apply is approved and gates pass;
auth availability alone does not authorize mutation.
```

---

## 11. Task/Beads-Side Requirements

### 11.1 `vibe task doctor --json` (new, readonly)

Must detect at least:

```text
- task provider configured or missing (config-level)
- beads binary present or missing
- beads version if available
- .beads directory present or missing
- whether repo appears initialized for Beads
- whether task status can be read (without creating tasks)
```

Emit codes such as `BEADS_NOT_INSTALLED`, `BEADS_NOT_INITIALIZED`, `TASK_PROVIDER_NOT_CONFIGURED` with readonly `next_actions` (`install-guide` / `init-preview`).

### 11.2 `vibe task status --json` (harden)

```text
MUST NOT return NOT_IMPLEMENTED when bd is installed.
MUST return readiness:
  - ready
  - not_ready
  - unavailable
with reasons + next_actions.
MUST NOT create Beads tasks.
MUST NOT run bd init.
MAY report .beads presence and binary version.
Phase 11 import/reconcile fields remain absent or explicitly not_implemented_phase=11.
```

### 11.3 Keep existing readonly task commands

```bash
vibe task install-guide --json
vibe task init-preview --json
```

Semantics unchanged: guidance/preview only; no install/init mutation from vibe CLI in Phase 10.5.

### 11.4 Phase 11 boundary

Any user request for plan import / reconcile must get a stable response pointing to Phase 11 — not a fake Beads workflow inside Phase 10.5.

---

## 12. Mutation Safety Rules

```text
1. Skills may auto-run readonly commands only (§6.1 / §8).
2. Skills must never auto-run mutation commands (§6.2).
3. CLI mutation requires explicit --apply (or --sync-apply for publish), except
   acceptance-only helpers which remain gated and forbidden in default gates.
4. skills install follows Option A (--apply required).
5. Default gates: no real NotebookLM mutation; no Beads task creation; no bd init.
6. No unmanaged source delete; no broad cleanup.
7. No push unless current user prompt explicitly approves.
8. Redact secrets / raw notebook refs / raw source IDs in committed reports and user-facing JSON where required by harness.
```

---

## 13. Required CLI Changes

Implementation checklist (code later; this is the contract):

```text
[ ] Add cmd: knowledge doctor
[ ] Add cmd: knowledge init-preview
[ ] Add cmd: task doctor
[ ] Harden cmd: task status (ready/not_ready/unavailable)
[ ] skills install: require --dry-run or --apply (Option A)
[ ] knowledge status: state-specific next_actions (§9.2)
[ ] Prefer structured next_actions objects on doctor/status/init-preview envelopes
[ ] Align retry flag UX with sync (document + test)
[ ] Add reindex-bindings --dry-run if needed for skill-safe repair preview
[ ] Fix stale Phase 3 safe_to_sync messaging
[ ] Wire argparse help + README/Project Source command lists
```

No Phase 11 import CLI in this phase.

---

## 14. Required Skill Changes

### 14.1 `vibe-knowledge/SKILL.md`

```text
- Keep thin (prefer ≤ ~120 lines; tables over prose)
- Embed §8.2 routing table
- List readonly auto-allowed commands and mutation forbid list
- Use primary config path .config/vibe-control.yaml (mention legacy .vibe/control.yaml only as compatibility)
- Do not duplicate sync_state / receipt / ProviderTarget logic
- Explicit: recommend --apply only when user asked to sync/retry/apply/setup mutation
```

### 14.2 `vibe-implementation/SKILL.md`

```text
- Keep thin
- Embed §8.3 routing table
- Include task doctor / status / install-guide / init-preview
- Explicit Phase 11 deferral for plan import / reconcile
- Never auto bd init / never create tasks
```

### 14.3 Install packaging

```text
- SKILL_NAMES unchanged
- skills status remains readonly
- skills install mutation only with --apply after Option A
```

---

## 15. Required Test Spec

**Principle:** Test Spec is part of the spec. Implementation follows tests.  
Mutation column: `none` | `local-state-only` | `fake-provider` | `forbidden-in-default-gates`

| ID | Purpose | Setup | Command | Expected result | Mutation allowed? |
|---|---|---|---|---|---|
| P10_5-SKILL-NAME-001 | Provider-neutral skill names | packaged skills root | read SKILL.md + `skills status` | only `vibe-knowledge` / `vibe-implementation`; no notebooklm-skill/beads-skill | no |
| P10_5-SKILL-ROUTER-001 | knowledge routing table present | packaged `vibe-knowledge` | content contract test | SKILL.md contains doctor/status/query/sync --dry-run vs --apply decision rows | no |
| P10_5-SKILL-ROUTER-002 | implementation routing table present | packaged `vibe-implementation` | content contract test | SKILL.md contains task doctor/status/install-guide/init-preview; Phase 11 deferral; forbids auto bd init | no |
| P10_5-CLI-KNOWLEDGE-DOCTOR-001 | knowledge doctor readonly precheck | temp repo + config fixture | `knowledge doctor --json` | `ok` or structured failure; aggregates config/provider/notebook/auth/snapshot/receipt/pending/sync_state; no provider mutation | no |
| P10_5-CLI-KNOWLEDGE-INIT-001 | knowledge init-preview plan only | missing config or missing auth fixture | `knowledge init-preview --json` | readonly next steps; no upload; no receipt write | no |
| P10_5-CLI-TASK-DOCTOR-001 | task doctor detects beads/.beads | fake PATH + temp `.beads` presence matrix | `task doctor --json` | codes for missing binary / missing `.beads` / ready path; no bd init | no |
| P10_5-CLI-TASK-STATUS-001 | task status not stub when bd installed | mock bd on PATH | `task status --json` | `ready`/`not_ready`/`unavailable` — **not** `NOT_IMPLEMENTED`; no task create | no |
| P10_5-ENVELOPE-NEXT-ACTIONS-001 | state-specific next_actions | fixtures for drift/pending/receipt_missing/config missing | `knowledge status` / doctor / init-preview | codes from §9.2 present; not static three-string-only | no |
| P10_5-MUTATION-GATE-001 | sync/retry require explicit apply | fake provider | `knowledge sync` / `retry` without flags | fail closed or non-mutating dry-run per documented contract; never silent apply | no |
| P10_5-SKILLS-INSTALL-GATE-001 | skills install Option A | `VIBE_SKILLS_ROOT` temp | `skills install --json` without flags | refuses mutation; `--dry-run` plans; `--apply` writes symlink | `--apply` only (local symlink; not NotebookLM) |
| P10_5-NO-REAL-NOTEBOOKLM-MUTATION-001 | default gates stay clean | unit/acceptance readonly suite | phase 10.5 tests + fast gate | no real source add/delete/update | forbidden-in-default-gates |
| P10_5-NO-BEADS-TASK-CREATE-001 | no Beads task creation | task doctor/status tests | task commands | no `bd create` / equivalent | no |
| P10_5-STALE-PHASE3-MESSAGE-001 | remove misleading Phase 3 sync wording | integration doctor / provider status strings | doctor/status envelopes | no `safe_to_sync remains false in Phase 3` user-facing next_action | no |

Additional recommended (optional but useful) IDs if time allows:

```text
P10_5-RETRY-FLAG-CONSISTENCY-001
P10_5-REINDEX-DRY-RUN-001
P10_5-STRUCTURED-NEXT-ACTION-SCHEMA-001
```

---

## 16. Acceptance Criteria

Phase 10.5 is **complete** only when all of the following are true:

```text
[x] New Phase 10.5 spec exists at
    docs/project/sync/phase10-5-skills-doctor-init-cli-boundary-spec.md
    (this file — spec landing)
[x] Project Source references Phase 10.5 as required before Phase 11
[x] knowledge doctor / init-preview contract implemented per this spec
[x] task doctor / status hardening implemented per this spec
[x] skill routing tables landed in both SKILL.md files
[x] JSON next_action requirements satisfied for §9.2 codes
[x] mutation gate policy explicit in CLI (including skills install Option A)
[x] Test Spec (this §15) has corresponding tests before/with implementation
[x] Default gates: no real NotebookLM mutation required
[x] Default gates: no Beads task creation required
[x] No Phase 11 plan import implemented
[x] scripts/test-fast.sh (or documented equivalent) passes for new tests
[x] Stale Phase 3 safe_to_sync messaging removed or corrected
```

Implementation landed 2026-07-14. Remaining open items in §18 stay as follow-ups, not blockers.

---

## 17. Implementation Notes

```text
1. Follow docs/harness/phase-execution-contract.md and test-execution-contract.md.
2. Prefer scripts/test-fast.sh while iterating; scripts/test-full-readonly.sh before closeout claim.
3. Keep provider quirks inside adapters (NotebookLM / Beads).
4. Reuse existing auth-status / login-guide / sync-preview / init-preview building blocks
   inside new doctor/init-preview aggregators — do not fork divergent status logic.
5. knowledge doctor should call the same sync_state computation as knowledge status
   for the resolved ProviderTarget (single source of truth).
6. task doctor should own .beads detection; BeadsProvider may grow a readonly probe helper.
7. Do not invent sub-phases under 10.5 unless a real blocker appears.
8. Update docs/project/DECISION_LOG.md when Option A ships or if Option A is overridden.
9. Correct CLI entrypoint docs to mention `.venv/bin/python -m vibe_control.cli` when needed.
```

Suggested implementation order:

```text
1. Tests first for envelope codes + skills install gate + task status readiness
2. CLI doctor/init-preview/status hardening
3. Skill markdown routing tables
4. Stale message cleanup
5. Readonly acceptance smoke (no real provider mutation)
6. Project Source closeout notes when implementation completes
```

---

## 18. Open Decisions

Resolved for this spec:

```text
- Phase 10.5 is required before Phase 11.
- Keep skill names vibe-knowledge / vibe-implementation.
- Add knowledge doctor, knowledge init-preview, task doctor.
- Keep task install-guide / task init-preview.
- Skills may auto-run readonly commands; must not auto-run mutations.
- Prefer skills install Option A (--apply gate).
```

Still open (implementation may need a short decision note):

```text
1. Structured next_actions objects vs dual string+object compatibility window length.
2. Whether knowledge retry without flags should fail closed (like sync) or keep default dry-run.
3. Whether reindex-bindings currently mutates local receipt always — exact --dry-run semantics.
4. Whether vibe task init --apply will ever exist, or bd init remains forever outside vibe CLI.
5. How much remote probe knowledge doctor should do by default vs --deep flag (auth already costly).
```

Do **not** block Phase 10.5 start on items 1–5 if defaults in this spec are followed:

```text
Default stance:
  (1) structured objects required on new doctor/init-preview; status upgraded in same phase
  (2) prefer fail-closed parity with sync
  (3) dry-run must not write receipt
  (4) no task init --apply in 10.5
  (5) doctor may omit expensive remote probe unless --deep / integration doctor already covered
```

---

**End of Phase 10.5 Spec**
