# Roadmap and Beads Readiness Proposal After Phase 10.5

**Document type:** Roadmap and readiness proposal  
**Status:** Historical proposal — superseded by accepted Phase 11A / 11B roadmap in `docs/project/vibe-control-spec.md` v0.9 and `docs/project/sync/phase11a-ssot-specs-beads-readonly-reconcile-spec.md`  
**Date:** 2026-07-14  
**Purpose:** Original decision frame after Phase 10.5; kept for history.

---

## 1. Current Situation

Phase 10.5 has been accepted as the current safe/default baseline.

Phase 10.5 strengthened the project in these areas:

```text
- skills + CLI boundary
- knowledge doctor / init-preview
- task doctor / task status
- structured next_actions
- skills install --apply gate
- knowledge retry gate
- skill routing tables
```

This is important progress, but it does not automatically mean the project should immediately start Beads plan import.

The next question is:

```text
Is Beads already ready to act as the Vibe Control implementation task provider?
```

If the answer is yes, Phase 11 spec can start.

If the answer is no, Beads setup / configuration / doctor / status should be hardened first.

---

## 2. Product Model

The accepted product model is:

```text
Vibe Control = skills + CLI

CLI = deterministic command surface, validation, state checks, provider adapters, JSON envelopes, tests
Skills = thin intelligent routers that call CLI and interpret JSON

Repo / git SSOT files = truth
NotebookLM / provider = derived read/query layer
Beads = implementation task provider
```

Beads should not be used as an unmanaged external tool from skills.

Beads should be pulled into the Vibe Control system through:

```text
- config
- CLI
- doctor / precheck
- status
- install-guide
- init-preview
- JSON envelope
- skill routing
- tests
- mutation gates
```

---

## 3. Main Concern

The current roadmap says the next major phase is:

```text
Phase 11 — Beads Plan Import / Reconcile Minimal
```

That may still be correct.

However, plan import / reconcile depends on a stronger foundation:

```text
1. task provider configuration is clear
2. config validation understands task provider settings
3. task doctor detects bd installed / missing
4. task doctor detects .beads present / missing / initialized
5. task status returns reliable ready / not_ready / unavailable
6. task commands emit structured next_actions
7. vibe-implementation skill routes setup issues safely
8. tests prove no bd init by default
9. tests prove no Beads task creation by default
10. task identity model is defined or ready to define
```

If these foundations are weak, Phase 11 plan import will be risky, confusing, or too broad.

---

## 4. Beads Readiness Standard

Before plan import, Beads readiness should cover at least these commands:

```text
vibe task doctor --json
vibe task status --json
vibe task install-guide --json
vibe task init-preview --json
```

These commands should make Beads state visible without mutation.

They should report:

```text
- task provider configured or missing
- bd binary present or missing
- bd version if available
- .beads directory present or missing
- repo initialized for Beads or not
- task status readable or not
- ready / not_ready / unavailable
- structured next_actions
- safe setup instructions
```

Readonly commands must not run:

```text
bd init
bd create
bd update
bd delete
bd sync
```

Use `.beads`, never `.beeds`.

---

## 5. Route Options

### Option A — Start Phase 11 spec now

Choose this only if current Beads setup / configuration / doctor / status is already strong enough.

Phase 11 would be:

```text
Phase 11 — Beads Plan Import / Reconcile Minimal
```

It should define:

```text
- valid input files
- task identity model
- Vibe-managed marker
- duplicate prevention
- unmanaged task protection
- dry-run behavior
- apply behavior
- reconcile report
- skill routing
- Test Spec before implementation
```

---

### Option B — Insert Phase 10.6

Choose this if Beads readiness is still not strong enough.

Possible phase:

```text
Phase 10.6 — Beads Setup, Configuration, Doctor, and Task Readiness
```

Scope:

```text
- strengthen tasks.provider config handling
- strengthen config validation
- strengthen task doctor
- strengthen task status
- verify .beads state detection
- verify bd version detection
- strengthen init-preview / install-guide
- strengthen structured next_actions
- strengthen vibe-implementation skill routing
- strengthen tests for no bd init / no task creation
```

Non-scope:

```text
- no Beads plan import apply
- no Beads task creation
- no bd init
- no broad Beads cleanup
- no workflow engine
- no daemon
- no SQLite
- no NotebookLM changes
```

---

### Option C — Split Phase 11 into 11A / 11B

Choose this if Beads setup is mostly ready, but task identity and readonly reconcile should be separated from apply.

Possible split:

```text
Phase 11A — Beads Setup / Identity / Readonly Reconcile
Phase 11B — Beads Plan Import / Apply
```

Phase 11A should define task identity and readonly reconcile first.

Phase 11B should add controlled apply later.

This option may be better than Phase 10.6 if the setup/doctor/status layer is already mostly complete, but plan import apply is still too early.

---

### Option D — Fix acceptance / test debt first

Choose this only if existing acceptance or test debt blocks safe Beads work.

Known issue:

```text
scripts/test-acceptance-readonly.sh can fail at Phase 6 when provider is drifted from SSOT,
because the old assertion expects already_current count.
```

Current assumption: this is probably not a blocker for Beads setup/config/doctor work.

The repo assessment should verify whether this assumption is correct.

---

### Option E — Other

Choose this if repo evidence shows a better route.

---

## 6. Proposed Direction

The proposed direction is:

```text
Do not start Beads plan import until Beads setup/configuration/doctor/status and task identity are proven.
```

Therefore the likely next route is one of:

```text
Option B — Insert Phase 10.6
```

or:

```text
Option C — Split Phase 11 into 11A / 11B
```

But this proposal should be evaluated against the actual repo state.

If the repo already proves Beads readiness is strong enough, Option A may be acceptable.

---

## 7. Questions To Answer

The assessment should answer these questions with repo evidence:

```text
1. Is Phase 10.5 enough to say Beads is now a first-class Vibe Control task provider?
2. Does task doctor check enough?
3. Does task status check enough?
4. Is .beads state detection deep enough?
5. Does config validation cover task provider configuration?
6. Does vibe-implementation skill route setup/precheck/status correctly?
7. Are tests strong enough to prevent accidental bd init or task creation?
8. Is there already a task identity model?
9. Should task identity be based on spec id, plan id, repo path, content hash, Vibe-managed marker, or Beads task id?
10. Should Phase 11 import from formal specs, implementation plans, or both?
11. Should Phase 11 apply be allowed to create tasks?
12. Should Phase 11 apply be allowed to update existing Vibe-managed tasks?
13. Should deletion be forbidden?
14. Should we start Phase 11 spec now, insert Phase 10.6, or split Phase 11A / 11B?
```

---

## 8. Expected Feedback

The feedback report should choose one:

```text
A. Start Phase 11 spec now
B. Insert Phase 10.6 — Beads Setup, Configuration, Doctor, and Task Readiness
C. Split into Phase 11A / 11B
D. Fix acceptance / test debt first
E. Other
```

The report should not hedge.

It should provide:

```text
- repo evidence
- evaluation of this proposal
- recommended route
- immediate next step
- decisions required from the project owner
```

No implementation should happen during this feedback task.
