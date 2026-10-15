# Core Control-Contract Hardening — Implementation Plan

**Status:** Executed (2026-07-22) — companion spec accepted  
**Companion spec:** `docs/project/sync/20260722-core-claim-grading-hardening-spec.md`  
**Goal:** Make operation mutation evidence and capability fail-closed behavior consistent
without adding a universal policy engine or changing existing approval semantics.

## Guardrails

- Follow `docs/harness/phase-execution-contract.md`.
- Run tests before and after changes.
- Do not change NotebookLM/Beads approval policy.
- Do not add a generic MutationGate, evidence grades, skills generation, or doctor
  self-certification.
- Preserve the existing boolean type of `mutation_intent`.
- Do not perform real provider mutation during implementation tests.

---

## Task 1 — Baseline and operation inventory

Inspect:

- `src/vibe_control/json_envelope.py`
- `src/vibe_control/evidence.py`
- `src/vibe_control/closeout_runner.py`
- `src/vibe_control/knowledge/remote_ops.py`
- `src/vibe_control/knowledge/phase8_apply.py`
- `src/vibe_control/task/apply_cli.py`
- `src/vibe_control/task/apply_engine.py`
- `src/vibe_control/task/beads_apply.py`
- `src/vibe_control/task/cache_reset.py`
- `src/vibe_control/progress_brief.py`
- `src/vibe_control/grill_session.py`
- `src/vibe_control/gateway.py`
- `src/vibe_control/evidence.py`
- diagnostics command boundary in `src/vibe_control/cli.py`

Run:

```bash
pytest -q tests/test_json_envelope.py tests/test_closeout_runner.py \
  tests/test_autonomous_managed_apply.py tests/test_task_cache_ephemeral_mode.py
```

Record which target commands currently set top-level `mutation`, which only set
`data.mutation`, and where partial effects can occur. Do not edit until the inventory
matches the bounded migration list in the spec.

**Exit:** baseline result recorded; no real provider calls.

---

## Task 2 — Add the operation-result helper

**Modify:** `src/vibe_control/json_envelope.py`  
**Test:** `tests/test_json_envelope.py`

TDD cases:

1. `attach_operation_result(..., mutation_intent=False, effects=[])` sets:
   `mutation_intent=false`, `mutation_performed=false`, `mutation=false`, empty effects.
2. one valid completed effect derives performed/alias true.
3. failed envelope + completed effect derives/requires `partial_success=true`.
4. invalid effect schema, unsafe target, and non-boolean intent are rejected.
5. effects are copied, not shared/mutated.
6. helper does not change readiness or next actions.

Run the focused test and confirm red before implementation, green after.

**Exit:** one policy-free helper exists; no approval logic moved.

---

## Task 3 — Normalize mutation command results

### 3A Closeout

**Modify:** `src/vibe_control/closeout_runner.py`  
**Test:** `tests/test_closeout_runner.py`

Replace manual top-level mutation assignments with the helper. Preserve:

- dry-run/blocked apply → no performed mutation;
- successful bounded sync → performed true;
- provider apply failure after reported effects → performed true + partial success/effects;
- closeout never auto-mutates Beads.

### 3B Knowledge command boundary

**Modify:** `src/vibe_control/knowledge/remote_ops.py`,
`src/vibe_control/knowledge/phase8_apply.py` recording path.  
**Tests:** existing sync/retry/partial-continue tests.

Do not put owner approval into `phase8_apply.py`. Record a completed effect only after the
corresponding provider/local-state call succeeds; do not treat `updated_or_attempted` as a
completed write. The Engine command boundary converts those facts into envelope evidence.

Test provider no-op separately from total no-op: receipt, ack, pending-state, or last-sync
report writes are completed local-state effects even when no remote source changed.
Add partial-path tests such as provider add success followed by wait/receipt/report failure.

### 3C Task apply/cache reset

**Modify:** `src/vibe_control/task/apply_cli.py`,
`src/vibe_control/task/apply_engine.py`, `src/vibe_control/task/beads_apply.py`,
`src/vibe_control/task/cache_reset.py`.  
**Tests:** `tests/test_autonomous_managed_apply.py`,
`tests/test_task_cache_ephemeral_mode.py`, apply tests.

Capture each completed create/update effect before the next provider call. If a later call
raises, return/raise a structured partial result that preserves completed effects; the
command boundary emits performed=true and partial_success=true. Preserve `task_readable`
and `safe_task_convergence_allowed`.

Keep existing nested `data.mutation` aliases where tests/consumers rely on them, and assert
they agree with top-level `mutation_performed`.

### 3D Diagnostics writes

Normalize the diagnostics command envelope; do not alter redaction or bundle content.

### 3E Self-grill session writes

**Modify:** `src/vibe_control/progress_brief.py`, `src/vibe_control/gateway.py`,
`src/vibe_control/evidence.py` and, where needed to expose created/reused state,
`src/vibe_control/grill_session.py`.

`gateway --intent grill_brief` uses the existing `local_runtime_write` class. New session/
active-pointer writes produce effects; reusing without a write does not. Outer Gateway,
Engine payload, and nested S1 evidence must agree.

Make readonly `load_active_session`/Progress/Brief stop repairing a dangling `active.json`
pointer. It reports stale state without writing; explicit session-open/repair may write.

**Exit:** blocked, no-op, successful, and partial-effect paths have correct booleans and
effects; existing approval tests remain green.

---

## Task 4 — Readonly no-hidden-mutation contract

**Add:** `tests/test_readonly_operation_contract.py`

Cover the bounded set:

- status/query/doctor/describe;
- ordinary Gateway brief/status/why-blocked routes (exclude `grill_brief`);
- implementation prompt;
- closeout dry-run;
- knowledge sync dry-run;
- task reconcile/apply dry-run.

Use monkeypatched provider/repo/config/receipt/cache write sentinels that fail if called.
Assert:

```text
mutation_intent == false
mutation_performed == false
mutation == false
```

Do not attempt to prove provider-internal logging/cache behavior through filesystem-wide
snapshots.

Include a dangling self-grill active-pointer fixture and prove ordinary Progress/Brief does
not rewrite it.

**Exit:** every declared readonly command in scope has a direct no-write test.

---

## Task 5 — Capability-specific fail-closed coverage

**Add:** `tests/test_capability_failclosed_contract.py`

Reuse existing fixture builders; do not create another readiness engine.

Knowledge cases:

- disabled;
- unavailable;
- target mismatch;
- drift/pending/receipt missing;
- ask unclean;
- clean ready.

Task cases:

- disabled;
- unavailable/unreadable;
- cache stale;
- duplicate/conflict/unmanaged reset path;
- clean ready.

Assert deterministic blocked reasons, no green leak, next-action mutation labels, and no
current-command mutation.

**Exit:** tests mirror actual predicates in `product_readiness.py` and `components.py`.

---

## Task 6 — Describe/docs and verification

**Modify:**

- existing evidence/mutation section in `src/vibe_control/describe.py`;
- `docs/project/vibe-control-spec.md`;
- affected command docs/tests.

Describe must state:

- `mutation_intent` and `mutation_performed` are booleans;
- `mutation` is the performed compatibility alias;
- which command set has been normalized;
- approval remains capability-specific.

Do not add a new `claim_grading` surface. Do not make doctor claim tests passed.

Run:

```bash
pytest -q -m "not real_notebooklm and not real_hetu and not mutation"
scripts/test-closeout-local-fast.sh
scripts/test-full-local-readonly.sh
git diff --check
```

Review changed docs for secrets/absolute paths and confirm no provider mutation occurred.

**Exit:** full local readonly gate passes; companion spec acceptance criteria are checked
line by line; implementation can be landed under repository git rules.
