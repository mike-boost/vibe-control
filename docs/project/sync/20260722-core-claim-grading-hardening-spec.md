# Spec — Core control-contract hardening

**Status:** Accepted (2026-07-22) — core hardening implemented  
**Date:** 2026-07-22  
**Document type:** Implementation-ready core hardening spec  
**Audience:** owner + coding agents

**Related:**

- Front/Core: `docs/project/vibe-control-spec.md` (§5.4 S1 snapshot, §5.5 projection/safety)
- Mutation policy: `docs/harness/real-integration-mutation-contract.md`
- Test policy: `docs/harness/test-execution-contract.md`
- Existing evidence: `src/vibe_control/evidence.py`
- Existing envelopes: `src/vibe_control/json_envelope.py`
- Execution plan: `docs/project/plans/20260722-core-control-contract-hardening-plan.md`

---

## 0. Decision

Strengthen the existing control contract without creating a second policy framework:

```text
1. Reuse S1 fields: mutation_intent + mutation_performed.
2. Keep `mutation` only as a compatibility alias of mutation_performed.
3. Prove readonly commands do not call mutation paths.
4. Test each capability against its own real readiness state machine.
5. Keep existing capability-specific approval rules; do not build a universal MutationGate.
```

This spec does **not** introduce evidence grades, new mutation classes, platform-agent
profile generation, or runtime claims about test coverage.

---

## 1. Problem

The product rules already exist, but their runtime representation is inconsistent:

1. Front/Core requires `mutation_intent` and `mutation_performed`; many command envelopes
   expose only an ad hoc `mutation` boolean or place it under `data`.
2. A blocked apply, a no-op apply, and a partial provider write cannot be represented
   correctly by “apply command = mutation true.”
3. Readonly behavior is required by formal contracts, but coverage is spread across tests.
4. Knowledge and Task use different readiness states; a generic Cartesian state matrix
   would invent invalid states and mishandle disabled capabilities.

---

## 2. Locked decisions for owner review

| ID | Decision |
|---|---|
| D1 | `mutation_intent` remains the existing S1 boolean: true when this invocation requests an apply/mutation path, even if authorization or a later precondition blocks it. |
| D2 | `mutation_performed` is derived from completed `effects[]`; callers cannot provide a contradictory boolean. |
| D3 | Top-level `mutation` remains temporarily and MUST equal `mutation_performed`; existing nested `data.mutation` aliases are not removed in this slice. |
| D4 | Blocked apply: intent=`true`, performed=`false`. Apply with zero completed effects: performed=`false`. Failure after any completed effect: performed=`true`, `partial_success=true`. |
| D5 | Every command in the bounded migration list must attach operation evidence explicitly; no silent default may label an apply path readonly. |
| D6 | Approval rules remain capability-specific and keep current public mutation classes. No universal gate is added. |
| D7 | Readiness tests follow actual capability predicates, including enabled/disabled state. |
| D8 | Runtime doctor reports current facts only. Test coverage stays in pytest/acceptance evidence. |
| D9 | Existing skills install/alignment behavior is unchanged. |
| D10 | No new capability ID and no sdd/tdd/external/ego-lite work is included. |

---

## 3. Operation evidence contract

Every migrated JSON command envelope in §4.2 MUST expose:

```json
{
  "mutation_intent": false,
  "mutation_performed": false,
  "mutation": false,
  "effects": []
}
```

Rules:

- `mutation == mutation_performed` during the compatibility period.
- Existing nested `data.mutation` fields may remain for current consumers, but must agree
  with top-level performed evidence.
- `effects[]` lists completed side effects, not planned operations.
- Minimal effect schema:

  ```json
  {"kind": "provider_write|task_write|local_state_write|repo_write|config_write",
   "target": "redacted stable surface name",
   "status": "completed"}
  ```

  `target` MUST NOT contain secrets, raw provider IDs, or absolute home paths.
- A failure after any write sets `mutation_performed=true`; it must not erase completed
  effects merely because the final result failed.
- `next_actions[].mutation` keeps its existing meaning: whether executing the suggested
  action may mutate. It is not the current command result.
- Existing `mode` remains command-specific and is not used as mutation evidence.
- Commands whose purpose inherently writes local state (for example diagnostics bundle
  creation or opening a self-grill session) set intent true even without an `--apply` flag.

### Required examples

| Case | mutation_intent | performed | partial_success |
|---|---:|---:|---:|
| status/query/doctor | false | false | false |
| sync/reindex dry-run | false | false | false |
| apply blocked before authorization | true | false | false |
| authorized apply blocked by a later precondition | true | false | false |
| apply succeeds with writes | true | true | false |
| apply with zero completed effects | true | false | false |
| apply writes, then fails | true | true | true |

---

## 4. Implementation boundary

### 4.1 Shared envelope helper

Extend `src/vibe_control/json_envelope.py` with one small helper:

```python
def attach_operation_result(
    envelope: dict[str, Any],
    *,
    mutation_intent: bool,
    effects: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ...
```

The helper:

- sets the four top-level fields from §3;
- requires actual boolean inputs (reject strings/integers rather than coercing them);
- validates and redacts the minimal effect schema;
- derives `mutation_performed` and compatibility `mutation` from completed effects;
- if `ok=false` and effects are non-empty, requires/sets `partial_success=true`;
- does not make approval decisions or recompute readiness.

Do not add a second generic mutation-policy module.

### 4.2 Commands migrated in this slice

Migrate the high-value control surfaces, not every historical helper in one pass:

1. `vibe closeout run`
2. `vibe knowledge sync` / `retry`
3. `vibe task apply`
4. `vibe task cache reset`
5. diagnostics bundle writes
6. self-grill `gateway --intent grill_brief` / session-open behavior
7. readonly status/query/doctor/describe/ordinary gateway/brief/implementation-prompt envelopes
8. Hetu commands when Hetu lands

Other commands keep compatibility behavior until touched by a future accepted slice.
`vibe describe --json` MUST disclose this bounded migration, not claim every legacy
command is already normalized.

### 4.3 Policy placement

- Knowledge bounded closeout remains governed by
  `real-integration-mutation-contract.md`; do not route it through Beads policy.
- A Knowledge provider no-op does not imply zero effects: receipt, ack, pending-state, or
  last-sync report writes are `local_state_write` effects and make performed true.
- Beads keeps `evaluate_autonomous_managed_eligibility`, including
  `task_readable` and `safe_task_convergence_allowed`.
- Provider execution modules do not decide owner/session approval.
- Provider execution loops may record completed effects after successful calls; recording
  effects is evidence collection, not approval policy.
- Approval checks stay at Engine command boundaries.

---

## 5. Readonly invariant

For commands declared readonly:

```text
mutation_intent = false
mutation_performed = false
mutation = false
```

Tests MUST also prove that Vibe did not call:

- provider mutation methods;
- repo/config/receipt/cache write helpers;
- task provider create/update/delete;
- knowledge sync/apply paths.

The invariant concerns Vibe-controlled side effects. Provider-internal caches/logging are
reported separately when unavoidable; they must not be mislabeled as a Vibe-approved
provider mutation.

`gateway --intent grill_brief` is not unconditionally readonly: opening a new local
self-grill session writes session JSON and an active pointer. It uses the existing
`local_runtime_write` class, `mutation_intent=true`; reuse with no new write may report
`mutation_performed=false`. Ordinary Gateway/Brief routes remain readonly.

Readonly Progress/Brief inspection MUST NOT repair a dangling self-grill active pointer.
It reports the stale pointer and a next action; cleanup/repair occurs only on an explicit
local-write path.

---

## 6. Fail-closed branch coverage

Build tests from the actual predicates, not shared state names.

### Knowledge

- disabled → skipped, not a product-ready failure;
- enabled + unavailable/target mismatch/drift/pending/receipt missing/ask unclean → not ready;
- enabled + active provider synced and ask-clean → ready.

### Task

- disabled → skipped, not a product-ready failure;
- enabled + provider unavailable/unreadable/cache stale → not ready;
- duplicate/conflict/unmanaged → reset/repair guidance, never fake current;
- enabled + readable + cache current → ready.

### Hetu

Added by the Hetu runtime spec after its state model is accepted.

Each blocked branch asserts:

- no green readiness leak;
- deterministic reason code;
- valid `next_actions`;
- current command performed no hidden mutation.

---

## 7. CLI self-explanation

`vibe describe --json` extends the existing mutation/evidence surface only:

- document `mutation_intent`, `mutation_performed`, compatibility `mutation`;
- link each existing public mutation class to its governing contract;
- state the bounded migration scope from §4.2.

Do not add a new `claim_grading` product block.

`vibe doctor --json` remains a current-state probe. It MUST NOT report pytest coverage,
claim that matrices passed, or recompute policy from documentation.

---

## 8. TDD implementation slices

### Slice A — Operation-result helper

**Tests:** extend `tests/test_json_envelope.py`

- valid intent/result combinations;
- alias equality;
- performed derived from completed effects;
- performed/effects/partial_success inconsistency rejected or normalized as §4.1 requires;
- effect target redaction/validation;
- partial effect preservation;
- invalid intent rejected.

**Code:** `src/vibe_control/json_envelope.py`

### Slice B — Mutation command correctness

**Tests:** focused closeout, knowledge apply, task apply/cache reset, diagnostics tests.

- blocked/apply-with-zero-effects remains performed=false;
- successful write is performed=true;
- partial write failure preserves effects and partial_success.

**Code:** command boundaries plus Task execution loops where completed effects would
otherwise be lost; provider adapters remain approval-policy-free.

### Slice C — Readonly contract

**Tests:** add `tests/test_readonly_operation_contract.py`.

Use injected sentinels/mocks to prove declared readonly surfaces do not call write paths.

### Slice D — Capability-specific fail-closed coverage

**Tests:** add `tests/test_capability_failclosed_contract.py`.

Cover the branches in §6, including disabled behavior.

### Slice E — Describe and docs

Update existing Describe evidence/mutation surfaces and formal docs. Do not add doctor
test-coverage output.

---

## 9. File touch list

Expected:

- `src/vibe_control/json_envelope.py`
- command boundaries in `src/vibe_control/cli.py`
- `src/vibe_control/closeout_runner.py`
- relevant knowledge command-boundary modules
- `src/vibe_control/knowledge/phase8_apply.py` only to record effects after successful
  provider/local-state writes (never to decide approval)
- `src/vibe_control/task/apply_cli.py`
- `src/vibe_control/task/apply_engine.py`
- `src/vibe_control/task/beads_apply.py`
- `src/vibe_control/task/cache_reset.py`
- `src/vibe_control/progress_brief.py`
- `src/vibe_control/grill_session.py` only if needed to return created/reused effect facts
- `src/vibe_control/gateway.py`
- `src/vibe_control/evidence.py` to project actual operation evidence instead of
  hard-coding readonly for `grill_brief`
- `src/vibe_control/describe.py`
- focused tests from §8
- `docs/project/vibe-control-spec.md`

Not expected:

- new universal mutation gate module;
- `src/vibe_control/skills_manager.py`;
- `src/vibe_control/diagnostics.py` merely to report test coverage;
- sdd/tdd/provider integrations.

---

## 10. Acceptance criteria

1. Migrated commands expose correct intent, performed result, compatibility alias, effects.
2. Partial writes cannot be reported as `mutation_performed=false`.
3. Readonly contract tests prove no Vibe mutation path was called.
4. Knowledge/Task fail-closed tests follow their real enabled-state predicates.
5. Existing Beads safe convergence and bounded Knowledge closeout behavior are unchanged.
6. Describe explains the contract without claiming runtime test coverage.
7. Fast local and full local readonly gates pass.

---

## 11. Non-goals

- Generic evidence scoring or A/B/C grades
- Universal mutation authorization engine
- Reclassifying existing public mutation classes
- Multi-platform agent profile generation
- New capability IDs or provider integrations
- Runtime doctor self-certifying CI/test coverage

---

## 12. Owner review checklist

- [ ] Accept D1–D10
- [ ] Confirm `mutation` remains an alias of actual performed effects
- [ ] Confirm capability-specific policy remains in place
- [ ] Confirm bounded migration rather than whole-CLI rewrite
- [ ] After acceptance, implementation follows Slices A→E without redesign

---

## 13. Status history

| Date | Status | Note |
|---|---|---|
| 2026-07-22 | Proposed | Initial draft |
| 2026-07-22 | Proposed | Rewritten after repository and independent review; removed universal gate, invented grades, skills generation, and doctor self-certification |
