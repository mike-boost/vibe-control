# Spec — Hetu runtime MVP with codebase-memory-mcp

**Status:** Accepted (2026-07-22) — runtime MVP implemented (fake/unit gates; real reindex optional)  
**Date:** 2026-07-22  
**Document type:** Implementation-ready capability/provider spec  
**Audience:** owner + coding agents

**Related:**

- Accepted product decision: `docs/project/sync/20260719-hetu-capability-decision.md`
- Accepted design: `docs/project/vibe-control-hetu-spec.md`
- Front/Core: `docs/project/vibe-control-spec.md` (§ Capability Profile)
- Core evidence hardening:
  `docs/project/sync/20260722-core-claim-grading-hardening-spec.md`
- Mutation policy: `docs/harness/real-integration-mutation-contract.md`
- Test policy: `docs/harness/test-execution-contract.md`
- Primary provider: `DeusData/codebase-memory-mcp`
- Execution plan: `docs/project/plans/20260722-hetu-runtime-mvp-plan.md`

---

## 0. Decision

Ship Hetu as an optional, provider-backed code-structure capability:

```text
Provider engine: codebase-memory-mcp
Vibe owns: capability enablement, repo↔provider binding, freshness receipt,
           bounded output, fail-closed readiness, reindex approval, JSON envelope
Vibe does not own: parsing, graph construction, graph algorithms, code search engine
```

Delivery order:

1. fake provider locks the Vibe contract;
2. subprocess CLI adapter integrates codebase-memory-mcp;
3. real readonly smoke validates the adapter;
4. real reindex is validated only under an explicit mutation test approval.

---

## 1. Why this capability exists

Agents repeatedly pay a discovery tax and still miss callers, data-flow edges, and blast
radius. codebase-memory-mcp supplies structural intelligence, but it does not provide the
Vibe product contract:

- whether the graph can be tied to the current Git state;
- whether an enabled capability may be called ready;
- how a repo is safely bound to an existing provider project;
- how results are bounded for agent context;
- whether reindex was authorized and what it changed.

Hetu adds those controls without rebuilding the graph engine.

---

## 2. Locked decisions for owner review

| ID | Decision |
|---|---|
| D1 | Add component ID `hetu`; after this runtime lands it is `supported`, default disabled, `optional_when_disabled`. |
| D2 | Disabled Hetu is ignored. Enabled Hetu participates in `product_ready`; stale/unverifiable/unavailable Hetu cannot coexist with full product readiness. |
| D3 | Primary provider is `codebase_memory`; `fake` is test-only. `codegraph` remains a future hint, not an active adapter. |
| D4 | Real transport is `codebase-memory-mcp cli --json <tool> <json>` via an injected subprocess runner. No Python MCP SDK is added. |
| D5 | Vibe uses a local `IndexBindingReceipt`; provider `index_status` alone is insufficient because it does not return a Git commit. |
| D6 | v1 strict freshness requires clean Git, unchanged HEAD before/after reindex, matching receipt, compatible provider, provider status ready, and effective `auto_watch=false`. |
| D7 | Missing receipt or uncontrolled watcher yields `unverifiable`, never ready. HEAD/dirty mismatch yields `stale`. |
| D8 | Reindex apply requires Hetu enabled, compatible provider, safe current-repo plan, current plan binding, and explicit `--confirm-hetu-reindex-apply`; it does not require global `product_ready` and does not use an environment-variable dual gate. |
| D9 | Existing indexes are detected through `list_projects.root_path`; `.codebase-memory/` is optional evidence only. No existing index is silently bound to current HEAD. |
| D10 | v1 reindex uses `mode=fast`, `persistence=false`; semantic search is out of scope. |
| D11 | Readonly queries run only when Hetu is ready. They return bounded normalized results, never raw unbounded provider payloads. |
| D12 | Hetu does not auto-reindex during closeout in v1. If enabled and stale, closeout remains blocked and points to Hetu reindex dry-run. |
| D13 | Provider delete/wipe/install/config changes remain outside MVP and require separate explicit owner approval. |
| D14 | Cross-surface composition into brief/prompt is deferred. |

---

## 3. Capability and configuration

### 3.1 Component catalog

After all runtime slices and acceptance pass:

```python
"hetu": {
    "support_state": "supported",
    "default_enabled": False,
    "readiness_role": "optional_when_disabled",
    "bound_provider": "codebase_memory",
    "provider_hints": ["codebase_memory", "codegraph"],
    "existing_runtime": True,
}
```

During partial implementation, do not mark Hetu supported. The catalog flip is the final
runtime slice so an incomplete provider cannot be enabled.

### 3.2 Config schema

```yaml
components:
  hetu:
    enabled: false

hetu:
  provider: codebase_memory
  freshness_policy: strict
  codebase_memory:
    binary: codebase-memory-mcp
    project: null          # optional explicit project choice when detection is ambiguous
    index_mode: fast       # only fast in v1
    search_limit: 20       # clamp 1..50
    trace_depth: 3         # clamp 1..5
    impact_depth: 2        # clamp 1..5
    query_timeout_sec: 30  # clamp 5..120
    reindex_timeout_sec: 600
```

Rules:

- exactly one active Hetu provider;
- unknown provider/config values fail closed;
- `project` is a provider binding, never repo identity;
- Vibe never runs provider `install`, `update`, `uninstall`, or `config set`.

---

## 4. Provider transport contract

### 4.1 Adapter

`CodebaseMemoryCliAdapter` invokes argument arrays, never shell strings:

```text
codebase-memory-mcp cli --json index_status '{"project":"..."}'
```

The adapter MUST:

- discover the configured executable with `shutil.which` or an explicit path;
- capture stdout/stderr separately;
- apply query/reindex timeouts;
- parse direct JSON, outer CLI JSON, and nested `content[].text` JSON;
- tolerate observed 0.8.1 leading `level=...` log lines by selecting the final valid JSON
  record and surfacing discarded prefixes as redacted warnings; never silently accept
  arbitrary trailing garbage;
- normalize non-zero exit, timeout, invalid JSON, missing tool, and degraded indexing;
- report provider version from `codebase-memory-mcp --version`;
- set `CBM_ALLOWED_ROOT=<repo_realpath>` for reindex;
- never pass raw provider stderr/secrets into committed evidence.

### 4.2 Compatibility probe

Do not infer compatibility from version alone. Doctor probes:

1. executable/version;
2. `config list`;
3. `list_projects`;
4. required tool contract for:
   `index_status`, `search_graph`, `trace_path`, `detect_changes`,
   `get_architecture`, `index_repository`.

Unit fixtures MUST cover observed 0.8.1 and current 0.9.x output shapes. Unsupported or
missing required tools yield `provider_incompatible`, not empty inventory.

Doctor MUST NOT invoke `index_repository` to probe compatibility. Mutation-tool presence
is determined from bounded help/capability output and accepted fixtures; actual invocation
occurs only on confirmed reindex apply.

### 4.3 Tool mapping

| Hetu operation | Provider tool |
|---|---|
| status | `list_projects` + `index_status` |
| search | `search_graph` using BM25 query only |
| trace | `trace_path` |
| impact | `detect_changes` |
| architecture | `get_architecture` |
| reindex | `index_repository(mode="fast", persistence=false)` |

---

## 5. Repo/project binding

Repo identity remains Vibe/Git identity. Provider project names are bindings only.

Candidate resolution:

1. canonicalize current repo with `Path.resolve()`;
2. call `list_projects`;
3. compare canonical `root_path`;
4. if config specifies `hetu.codebase_memory.project`, require its root to match;
5. one exact candidate → selected candidate;
6. zero candidates → `missing`;
7. multiple/mismatched candidates → `conflict_needs_choice`.

`.codebase-memory/graph.db.zst` may be reported as an artifact candidate, but its presence
does not prove an active provider project or freshness.

No separate destructive adopt operation is required in v1:

- an exact existing candidate is preserved;
- it remains `unverifiable` until a confirmed incremental/fast reindex establishes a receipt;
- zero candidates is a valid reindex-create plan; after indexing, Vibe resolves the single
  exact-root provider project returned by `list_projects`;
- reindex does not delete the project or wipe artifacts;
- ambiguous candidates are resolved by owner config, not an ad hoc prompt in code.

---

## 6. IndexBindingReceipt

### 6.1 Location

```text
~/.agents/state/vibe-control/{project_id}/hetu/codebase_memory/index-binding.json
```

Write atomically. This is runtime evidence, not repo SSOT.

### 6.2 Schema

```json
{
  "schema": "vibe.hetu.index_binding.v1",
  "repo_identity": "<vibe project id>",
  "repo_realpath_hash": "sha256:...",
  "provider": "codebase_memory",
  "provider_project": "...",
  "provider_version": "0.9.0",
  "index_mode": "fast",
  "persistence": false,
  "index_commit": "<git HEAD>",
  "git_status_short_empty": true,
  "auto_watch_effective": false,
  "node_count": 1234,
  "edge_count": 5678,
  "bound_at": "...",
  "binding_hash": "sha256:..."
}
```

Absolute repo paths may exist in local provider output but are not emitted in committed
reports. Receipt/output uses the Vibe project ID and path hash.

### 6.3 Establishing a receipt

Reindex apply:

1. verify Hetu enabled and provider compatible;
2. require effective `auto_watch=false` **before any provider mutation**;
3. require clean Git;
4. capture `base_head` and current config/provider/project/watcher binding;
5. verify `--expect-plan-binding` from the prior dry-run;
6. invoke `index_repository` using `repo_path` (zero candidates may create);
7. re-run `list_projects`, require one exact-root project, then require non-empty ready status;
8. re-read Git and require same HEAD + clean tree;
9. re-read effective watcher config and require it still false;
10. atomically write receipt.

Dry-run performs steps 1–4 and includes effective watcher state in its plan hash. If the
installed provider cannot expose effective watcher state (observed with 0.8.1), strict
reindex is incompatible and blocks before mutation with upgrade/config guidance.

If provider indexing succeeded but any post-index step 7–10 fails:

- `mutation_intent=true`;
- `mutation_performed=true`;
- `partial_success=true`;
- index state becomes `unverifiable`;
- effects record provider index mutation and whether receipt was written.

### 6.4 Watcher rule

codebase-memory defaults `auto_watch=true` when unset. Strict readiness requires the owner
to configure it explicitly false outside Vibe:

```bash
codebase-memory-mcp config set auto_watch false
```

Vibe doctor may recommend this command with `mutation=true`, but MUST NOT run it. Missing,
unknown, or true effective watcher state yields:

```text
index_state=unverifiable
reason=external_index_mutation_possible
```

---

## 7. Index state and readiness

States:

```text
missing
indexing
ready
stale
unverifiable
unavailable
conflict_needs_choice
```

State rules:

| State | Condition |
|---|---|
| `missing` | no matching provider project/index |
| `indexing` | provider reports indexing |
| `ready` | all strict checks below pass |
| `stale` | receipt exists but HEAD changed or working tree is dirty |
| `unverifiable` | provider graph exists but receipt/watcher/version binding cannot prove freshness |
| `unavailable` | binary/provider/tool/schema failure |
| `conflict_needs_choice` | configured/multiple candidate binding conflict |

Enabled Hetu is ready iff:

```text
provider compatible
AND one repo/project binding
AND provider index_status == ready with non-zero graph
AND valid IndexBindingReceipt
AND receipt provider/version/project/config matches
AND receipt index_commit == observed HEAD
AND git status is clean
AND effective auto_watch == false
```

`product_ready` behavior:

- Hetu disabled → ignored;
- Hetu enabled + ready → Hetu gate passes;
- Hetu enabled + any other state → `product_ready=false` with a deterministic reason.

This amends the accepted design's temporary “not in product_ready until runtime accepted”
rule: this runtime acceptance is the point at which enabled Hetu becomes a real gate.

---

## 8. CLI surface

### 8.1 Readonly

```text
vibe hetu status --json
vibe hetu doctor --json
vibe hetu search --query <str> [--limit N] --json
vibe hetu trace --symbol <qualified_name> --direction inbound|outbound|both [--depth N] --json
vibe hetu impact [--since <ref>] [--depth N] --json
vibe hetu architecture --json
vibe hetu reindex --dry-run --json
```

All expose:

```text
mutation_intent=false
mutation_performed=false
mutation=false
data.git.observed_head
data.git.dirty
data.index.index_commit
data.index.index_state
data.index.freshness_assurance
data.provider.id/version/project
```

Structural query commands require `index_state=ready`. Other states return a blocked
envelope with deterministic `next_actions`; they do not query a stale graph, except for
the explicit dirty-impact case below.

#### Dirty working-tree impact

The default `impact` use case is the current staged/unstaged diff. It is allowed only when:

- a valid strict receipt exists;
- receipt `index_commit == observed_head`;
- provider/version/project/watcher checks still pass;
- the sole non-ready reason is a dirty working tree.

In that case `impact` runs against the clean receipt baseline and returns:

```text
mode=degraded
index_state=stale
freshness_assurance=clean_baseline_plus_worktree_diff
uncertainty=current dirty code is not itself represented as a fresh graph
```

Search/trace/architecture remain blocked while dirty. HEAD mismatch, unverifiable,
unavailable, or conflict states also block impact. `impact --since <ref>` remains available
when the strict ready state passes.

### 8.2 Reindex apply

```text
vibe hetu reindex --apply --expect-plan-binding <sha256> \
  --confirm-hetu-reindex-apply --json
```

Preconditions:

- `components.hetu.enabled=true`;
- provider compatible;
- candidate binding unambiguous (zero candidates may create; multiple/mismatched candidates block);
- clean Git;
- caller supplies the dry-run plan hash through `--expect-plan-binding`;
- plan hash still binds HEAD/config/provider/project/mode/watcher state;
- explicit confirmation flag.

Global `product_ready` is not required because reindex is the recovery path that makes
Hetu ready. No `VIBE_HETU_*` environment gate is introduced.

Provider delete/wipe remains unsupported by this command.

Any `--apply` invocation reports `mutation_intent=true`, including a blocked invocation;
whether `mutation_performed` becomes true depends on actual provider/receipt effects.

---

## 9. Bounded result contracts

Vibe normalizes and caps provider output:

- search: default 20, max 50; expose `total`, `returned`, `has_more`, `truncated`;
- trace: depth default 3, max 5; max 50 paths / 200 nodes / 300 edges; tests excluded;
- impact: depth default 2, max 5; max 100 symbols / 200 edges;
- architecture: max 20 clusters, max 5 representative nodes per cluster;
- every item keeps provider-qualified identity, repo-relative path, and line coordinates
  when supplied;
- raw Cypher and raw unbounded provider payloads are not exposed in MVP.

If provider reports more data, return truncation metadata and a narrower-query
`next_action`; do not silently present a partial set as complete.

Ordering before truncation is stable: risk descending (when present), then hop/distance
ascending, then qualified name/path. If the provider does not return an exact total,
`total=null`; hitting a cap still sets `truncated=true`.

---

## 10. product_ready and closeout

Extend `ProviderProbeResult`, component readiness enrichment, integration status, evidence
hash, and projections with:

```text
hetu_enabled
hetu_available
hetu_ready
hetu_index_state
hetu_provider
hetu_index_commit
hetu_observed_head
```

When enabled, Hetu state contributes blocked reasons such as:

```text
hetu_provider_unavailable
hetu_provider_incompatible
hetu_index_missing
hetu_index_stale
hetu_index_unverifiable
hetu_binding_conflict
```

Closeout v1:

- never auto-runs Hetu reindex;
- if enabled Hetu is not ready, `closeout_complete=false`;
- next action is Hetu status/doctor or reindex dry-run;
- Knowledge and Task semantics remain unchanged.

---

## 11. Mutation policy

Allowed autonomously:

- status/doctor/search/trace/impact/architecture;
- reindex dry-run.

Requires explicit owner approval:

- reindex apply;
- changing provider config, including `auto_watch`;
- choosing a conflicting provider project;
- installing/updating provider binary;
- switching active provider.

Unsupported/forbidden in MVP:

- delete/wipe provider project or graph artifact;
- dual-active providers;
- arbitrary provider raw-tool passthrough.

Unsafe states emit deterministic reason/next actions; implementation code does not invent
free-form owner questions.

---

## 12. Implementation slices (TDD)

Do not flip the catalog to supported until Slice G passes.

### Slice A — Pure models and fake provider

Create Hetu models, state evaluator, receipt model/hash, and `FakeHetuProvider`.

Tests cover every index state, strict readiness predicate, result caps, and operation
evidence fields.

### Slice B — Config and component preparation

Parse/validate §3 config while Hetu remains `not_supported_yet` internally. Add guidance
and invalid-config tests without enabling real runtime yet.

### Slice C — Subprocess CLI adapter

Implement `CodebaseMemoryCliAdapter` with an injected runner.

Tests use captured 0.8.1/0.9.x direct/wrapped JSON, stderr, timeout, incompatible tool,
degraded index, and malformed payload fixtures.

### Slice D — Binding/status/doctor

Implement canonical root matching, conflict handling, watcher probe, receipt validation,
status and doctor. No mutation.

### Slice E — Readonly structural queries

Implement search/trace/impact/architecture normalization and limits. Verify blocked states
never call provider query tools.

### Slice F — Reindex dry-run/apply

Implement plan hash and confirmed apply sequence from §6.3. Unit tests cover blocked,
success, no receipt, Git race, provider success followed by receipt failure, and effects.

### Slice G — Readiness integration and catalog flip

Extend `components.py`, `product_readiness.py`, `integration.py`, closeout projections,
Describe/Gateway guidance, evidence hash, docs, and tests. Only now set Hetu `supported`.

### Slice H — Acceptance

1. full fake/local test suite;
2. optional real readonly smoke (`real_hetu`, serial, no mutation);
3. separately approved real reindex smoke (`real_hetu` + `mutation`) before claiming real
   reindex shipped;
4. full local readonly gate and sensitive-data scan.

Real reindex smoke uses an isolated temporary Git repo, temporary Vibe state root,
temporary `CBM_CACHE_DIR`, and external test config with Hetu enabled. It MUST NOT enable
Hetu in the tracked dogfood config or change the user's normal provider config.

---

## 13. Expected file changes

New:

- `src/vibe_control/hetu/__init__.py`
- `src/vibe_control/hetu/models.py`
- `src/vibe_control/hetu/provider.py`
- `src/vibe_control/hetu/receipt.py`
- `src/vibe_control/hetu/state.py`
- `src/vibe_control/hetu/codebase_memory_cli.py`
- `src/vibe_control/hetu/commands.py`
- focused tests/fixtures under `tests/`
- `scripts/test-hetu-readonly-smoke.sh`
- `scripts/test-hetu-reindex-smoke.sh`

Modify:

- `src/vibe_control/config.py`
- `src/vibe_control/components.py`
- `src/vibe_control/product_readiness.py`
- `src/vibe_control/integration.py`
- `src/vibe_control/closeout_runner.py`
- `src/vibe_control/cli.py`
- `src/vibe_control/describe.py`
- `src/vibe_control/gateway.py` only for projection/guidance, not provider logic
- `src/vibe_control/templates/control.yaml` and component-template tests
- `pyproject.toml` test markers and package description
- `scripts/test-fast.sh`, `scripts/test-full-local-readonly.sh` and test selectors so
  `real_hetu` is excluded from normal local gates
- `README.md`, `docs/configuration.md`
- `docs/harness/test-execution-contract.md`
- `docs/harness/real-integration-mutation-contract.md`
- `docs/harness/provider-readiness-probe-policy.md`
- `docs/harness/ssot-closeout-transaction-contract.md`
- `docs/harness/receipt-state-contract.md`
- Front/Core, Hetu formal spec, Product Thinking Index, `AGENTS.md`

No runtime MCP SDK dependency is expected.

---

## 14. Acceptance criteria

1. Disabled Hetu has no provider probe and no readiness effect.
2. Enabled Hetu cannot be product-ready unless strict receipt/provider/Git/watcher checks pass.
3. Existing provider index without receipt is `unverifiable`, never silently bound.
4. `auto_watch` true/unknown prevents strict ready; Vibe does not change provider config.
5. Reindex dry-run blocks before mutation when watcher state cannot be proved false.
6. Zero-candidate reindex resolves exactly one post-index root match before writing receipt;
   every post-index failure preserves partial effects and leaves state unverifiable.
7. Adapter works against accepted 0.8.1/0.9.x fixtures and normalizes failures.
8. Search/trace/architecture never query when state is not ready; dirty-only impact follows
   the explicit degraded contract.
9. Search/trace/impact/architecture outputs are bounded and disclose truncation.
10. Reindex recovery does not require global product readiness or an environment dual gate.
11. Git changes during reindex prevent receipt binding and are reported as partial effects.
12. Enabled stale/unavailable Hetu blocks product readiness and closeout; disabled Hetu does not.
13. No provider delete/wipe/install/config mutation is implemented.
14. Real readonly and explicitly approved real reindex evidence exist before real provider
    A+B is claimed shipped.

---

## 15. Non-goals

- Graph engine, parser, LSP, embeddings, or Cypher implementation
- Semantic search in v1
- codegraph adapter
- auto-watch management
- raw provider-tool proxy
- automatic closeout reindex
- brief/prompt impact composition
- sdd/tdd/external/web capabilities
- full Git frontend

---

## 16. Owner review checklist

- [ ] Accept D1–D14
- [ ] Confirm enabled Hetu participates in product readiness
- [ ] Confirm strict mode requires owner-managed `auto_watch=false`
- [ ] Confirm no silent adoption without a Vibe receipt
- [ ] Confirm subprocess CLI transport and `fast`/no-persistence defaults
- [ ] Confirm reindex uses one explicit confirmation flag, no environment dual gate
- [ ] Confirm real mutation smoke is required before claiming reindex shipped
- [ ] After acceptance, implementation follows Slices A→H without redesign

---

## 17. Status history

| Date | Status | Note |
|---|---|---|
| 2026-07-22 | Proposed | Initial runtime draft |
| 2026-07-22 | Proposed | Rewritten after live provider and independent review; closed readiness, receipt, watcher, CLI transport, binding, recovery, bounded-output, and real-test gaps |
