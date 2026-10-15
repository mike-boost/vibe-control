# Hetu Runtime MVP — Implementation Plan

**Status:** Executed (2026-07-22) — Tasks 1–8 landed; Task 9 real reindex deferred (fake/unit sufficient)  
**Companion spec:** `docs/project/sync/20260722-hetu-runtime-mvp-spec.md`  
**Goal:** Ship an optional Hetu capability backed by codebase-memory-mcp with provable
Git freshness, bounded structural results, and explicitly approved reindex.

## Guardrails

- Implement the core operation-result helper first.
- Follow all provider/mutation/test contracts listed in `AGENTS.md`.
- Fake/local tests first; no real reindex without explicit owner approval.
- Do not mark Hetu supported until the final readiness slice passes.
- Do not implement codegraph, semantic search, raw Cypher, auto-watch management,
  automatic closeout reindex, or prompt/brief composition.
- Invoke codebase-memory as an argv subprocess; never construct a shell command.

---

## Task 1 — Models, state evaluator, and receipt

**Create:**

- `src/vibe_control/hetu/__init__.py`
- `src/vibe_control/hetu/models.py`
- `src/vibe_control/hetu/state.py`
- `src/vibe_control/hetu/receipt.py`
- `tests/test_hetu_state.py`
- `tests/test_hetu_receipt.py`

Implement:

- index-state enum from the spec;
- provider status/query result models;
- `IndexBindingReceipt` schema, canonical hash, atomic read/write;
- pure strict-readiness evaluator.

TDD matrix:

- missing/indexing/ready/stale/unverifiable/unavailable/conflict;
- missing receipt;
- HEAD mismatch/dirty tree;
- provider version/project/mode mismatch;
- watcher true/unknown;
- valid strict-ready receipt;
- corrupt receipt fails closed without raising raw parser errors.

Run focused tests after each pure unit.

**Exit:** no CLI/provider calls; pure state transitions match the spec.

---

## Task 2 — Config and fake provider

**Create:** `src/vibe_control/hetu/provider.py`  
**Modify:** `src/vibe_control/config.py`  
**Tests:** `tests/test_hetu_config.py`, `tests/test_hetu_fake_provider.py`

Add the exact config schema/defaults/clamps from the spec. Implement a deterministic
`FakeHetuProvider` supporting status/search/trace/impact/architecture/reindex.

Keep production component status `not_supported_yet` during this task. Config parsing and
tests do not authorize enablement.

Negative cases:

- unknown provider;
- unsupported index mode;
- unsafe limits/timeouts;
- provider-scoped component ID;
- enabled Hetu before catalog flip remains fail-closed.

**Exit:** fake provider can drive all later command tests; no real binary required.

---

## Task 3 — codebase-memory subprocess adapter

**Create:** `src/vibe_control/hetu/codebase_memory_cli.py`  
**Add fixtures/tests:** `tests/fixtures/hetu/codebase_memory/`,
`tests/test_hetu_codebase_memory_cli.py`

Implement injected runner and argv:

```text
[binary, "cli", "--json", tool_name, json.dumps(args)]
```

Implement:

- binary/version/config/tool compatibility probes;
- stdout/stderr separation;
- direct/wrapped JSON parsing plus observed 0.8.1 leading `level=...` log prefixes;
- timeout/exit/error normalization;
- `CBM_ALLOWED_ROOT` on reindex;
- provider tool mapping.

Compatibility probing must not call `index_repository`; inspect bounded help/capability
output and defer the real mutation call to confirmed apply.

Fixtures must include:

- redacted captured 0.8.1 status/query outputs, including leading log + final JSON;
- accepted 0.9.x wrapped outputs;
- unavailable binary;
- missing tool/incompatible schema;
- timeout;
- invalid JSON;
- provider degraded/error.

Do not add an MCP SDK dependency.

**Exit:** unit adapter tests pass without real provider calls.

---

## Task 4 — Project binding, status, and doctor

**Create:** `src/vibe_control/hetu/commands.py`  
**Tests:** `tests/test_hetu_binding_status.py`,
`tests/test_hetu_doctor.py`

Implement:

- canonical current-repo resolution;
- `list_projects.root_path` matching;
- optional configured project validation;
- zero/one/multiple candidate behavior;
- optional artifact reporting without treating it as binding;
- receipt + provider + Git + watcher state evaluation;
- deterministic next actions and redaction.

Assertions:

- existing exact project without receipt → unverifiable;
- `.codebase-memory/` alone does not become ready;
- multiple candidates → conflict;
- absent `auto_watch` config is interpreted as provider default true;
- provider versions that cannot expose effective watcher state are strict-incompatible;
- doctor recommends config change but never runs it.

**Exit:** status/doctor are readonly and never call `index_repository` or config mutation.

---

## Task 5 — Readonly structural commands

**Modify:** Hetu command module and `src/vibe_control/cli.py`  
**Tests:** `tests/test_hetu_readonly_commands.py`

Wire:

- status/doctor;
- search;
- trace;
- impact;
- architecture;
- reindex dry-run.

Implement exact path/node/edge/symbol caps, stable sorting, and truncation metadata.
Normalize paths to repo-relative form. Block provider query calls unless index state is
ready, except dirty-only impact with a valid clean receipt baseline, which follows the
spec's explicit degraded contract.

Operation evidence:

```text
readonly/dry-run: mutation_intent=false
mutation_performed=false
mutation=false
```

Test high-degree results above caps, unknown totals, empty results, pagination hints,
invalid symbols/directions, dirty-only degraded impact, and all other stale/unverifiable
blocking.

**Exit:** fake-provider command contract is complete and token-bounded.

---

## Task 6 — Reindex plan and confirmed apply

**Tests:** `tests/test_hetu_reindex.py`

Implement:

- dry-run plan and deterministic hash over HEAD/config/provider/project/mode/watcher;
- emit a binding hash and require apply CLI
  `--expect-plan-binding <sha256> --confirm-hetu-reindex-apply`;
- watcher observability/false precheck before any provider mutation;
- enabled/provider/binding/clean-Git/current-plan checks;
- fast/no-persistence `index_repository`;
- zero-candidate create followed by exact-root project resolution;
- before/after HEAD race check;
- non-empty provider status check;
- watcher recheck;
- atomic receipt write;
- actual effects and partial-success reporting.

Every `--apply` invocation sets `mutation_intent=true`; blocked/no-op paths keep
`mutation_performed=false`.

Required failure cases:

- Hetu disabled;
- confirmation absent;
- dirty Git;
- stale plan hash;
- provider unavailable/incompatible;
- ambiguous project;
- provider failure before write;
- watcher true/unknown/unobservable before write;
- missing/mismatched `--expect-plan-binding`;
- provider success then Git changes;
- provider success then status timeout/empty graph/post-index multiple candidates;
- provider success then watcher/config mismatch;
- provider success then receipt write failure.

Never require global product readiness and never add an environment dual gate.

**Exit:** fake reindex A+B contract is complete; no real provider mutation performed.

---

## Task 7 — Readiness, closeout, and final catalog flip

**Modify:**

- `src/vibe_control/components.py`
- `src/vibe_control/product_readiness.py`
- `src/vibe_control/integration.py`
- `src/vibe_control/closeout_runner.py`
- `src/vibe_control/describe.py`
- `src/vibe_control/gateway.py` only where it projects Engine data
- `src/vibe_control/templates/control.yaml`
- corresponding tests

Add Hetu fields/reasons to probe result, evidence hash, integration status, component
enrichment, and closeout.

TDD:

- disabled Hetu → no probe/readiness effect;
- enabled ready → product-ready gate passes;
- each non-ready state → product-ready and closeout blocked;
- closeout never auto-reindexes;
- Knowledge/Task regression behavior unchanged.

Only after all focused tests pass:

- add `hetu` to the fixed catalog as supported;
- update capability profile examples;
- ensure fresh installs still default disabled.

**Exit:** no state can report `hetu.ready=false` while full configured-system
`product_ready=true`.

---

## Task 8 — Docs, package metadata, and local acceptance

**Modify:**

- `pyproject.toml` (`real_hetu` marker and product description)
- `README.md`
- `docs/configuration.md`
- `docs/harness/test-execution-contract.md`
- `docs/harness/real-integration-mutation-contract.md`
- `docs/harness/provider-readiness-probe-policy.md`
- `docs/harness/ssot-closeout-transaction-contract.md`
- `docs/harness/receipt-state-contract.md`
- `docs/project/vibe-control-spec.md`
- `docs/project/vibe-control-hetu-spec.md`
- `docs/project/PRODUCT_THINKING_INDEX.md`
- `AGENTS.md`
- `scripts/test-fast.sh`, `scripts/test-full-local-readonly.sh`, and acceptance selectors

**Add:** `scripts/test-hetu-readonly-smoke.sh`,
`scripts/test-hetu-reindex-smoke.sh`.

Run:

```bash
pytest -q -m "not real_notebooklm and not real_hetu and not mutation"
scripts/test-closeout-local-fast.sh
scripts/test-full-local-readonly.sh
git diff --check
```

Readonly smoke is explicit/serial and does not mutate. Reindex smoke must require both
`real_hetu` and `mutation` classification plus current owner approval; do not run it merely
because the script exists.

Add `real_hetu` to pytest markers and explicitly exclude it from normal fast/full local
selectors, just like `real_notebooklm`. The optional smoke script invokes it directly.

**Exit:** all local/fake gates pass, docs match runtime, no real mutation claimed.

---

## Task 9 — Real provider evidence before shipped claim

This task is a separate approved execution window.

Use an isolated temporary Git repo, temporary Vibe state root, temporary
`CBM_CACHE_DIR`, and an external test config with `components.hetu.enabled=true`. Do not
enable Hetu in the tracked dogfood config merely to run the smoke.

1. Record binary version and prove effective watcher state is observable; upgrade first if
   the installed version cannot expose it.
2. Under the temporary provider cache only, set `auto_watch=false` as explicit approved
   test setup; do not change the user's normal provider config.
3. Create/commit the tiny fixture repo and verify its Git status is clean.
4. Run real readonly preflight (expected missing/unverifiable before index).
5. With explicit owner approval, run one bounded reindex smoke against the fixture repo
   using the emitted `--expect-plan-binding`.
6. Verify receipt, HEAD, clean Git, unique provider root binding, bounded query, and no
   delete/persistence or non-temporary config changes.
7. Record mutation/effects in the acceptance report and remove temporary state.
8. Re-run full local readonly gate.

**Exit:** only after this task may release notes claim real codebase-memory readonly +
reindex support. Without it, report fake/unit + real-readonly evidence only.
