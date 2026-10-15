# Vibe Control Hetu Spec

**Document type:** Formal provider-layer spec (hetu / code-structure providers)  
**Status:** v0.2 — **Accepted design + runtime MVP shipped** (see
`docs/project/sync/20260722-hetu-runtime-mvp-spec.md`; fake/unit gates; real reindex optional)  
**Date:** 2026-07-22  
**Primary audience:** Coding agents, repository maintainers  
**Language policy:** Explanation in Chinese; code/commands/schemas in English.  
**Front/Core:** `docs/project/vibe-control-spec.md`  
**Decision (accepted):** `docs/project/sync/20260719-hetu-capability-decision.md`  
**Companions:** `docs/project/vibe-control-knowledge-spec.md`,
`docs/project/vibe-control-task-spec.md`

---

## 0. What this is / is not

```text
Hetu (this spec)
  = Vibe-owned code-structure understanding capability
  = gated CLI control plane over swappable structural providers
  = peer to Knowledge and Task (not a Workflow engine)

Hetu is NOT:
  - a docs / MUST ask surface (→ Knowledge)
  - a task / next-work surface (→ Task)
  - a lightweight agent workflow engine
  - a reimplementation of codebase-memory / codegraph / LSP
  - a multimodal “code + PDFs + meetings” graph (Graphify-class → not primary)
  - a product_ready dependency until runtime is accepted and wired
  - site trailer mythology as product scope
```

**一句话：** Provider 提供代码结构图；Vibe 保证 agent 用图时别瞎、别越权、失败别装绿，并把 git 新鲜度/影响面收进同一信封。

Until CLI exists, agents MUST NOT claim Hetu is shipped or that `product_ready`
requires Hetu.

---

## 1. Role / truth model

```text
Repo working tree + git refs     = change coordinates (HEAD, dirty, since/base)
Structural provider graph        = derived index of symbols / edges / clusters
Hetu CLI envelopes               = control-plane truth for readiness + queries
Agent chat memory                = never product evidence

index_commit / index watermark   = binding that graph was built for a git identity
provider project id / artifact   = binding only (never repo SSOT identity)
```

Forward direction:

```text
repo code (+ git) → provider index → Hetu readonly queries
```

Forbidden recovery:

```text
provider graph → rewrite repo source of truth
provider metadata → invent git HEAD / dirty state
chat summary → claim impact / callers as proven
```

---

## 2. Capability placement

Target Capability Profile component ID (Front/Core acceptance still required):

```text
hetu
```

```text
Do NOT reuse sdd | tdd as Hetu.
Do NOT enable hetu by default on fresh installs.
Disabled hetu MUST NOT fail Engine product_ready by itself
  (same optional_when_disabled pattern as knowledge/task).
```

When enabled:

```text
hetu readiness = provider present + index state interpretable
               + freshness policy applied for “ready” claims
```

---

## 3. Provider model

### Abstractions

```text
HetuProvider          = adapter behind the capability
IndexRecord           = project binding + index_commit + status
StructuralQuery       = search | trace | architecture | … (provider-mapped)
ImpactQuery           = git scope + graph blast radius
ReindexPlan           = dry-run / apply mutation plan
FakeHetuProvider      = tests / local only
```

### Provider catalog (policy)

| id (draft) | Role | MVP |
|---|---|---|
| `codebase_memory` | Primary target ([DeusData/codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp)) | Yes (direction) |
| `codegraph` | Swappable second ([colbymchenry/codegraph](https://github.com/colbymchenry/codegraph)) | Adapter later |
| `fake` | Deterministic tests | Yes (before real) |

**Active provider rule:** exactly **one** active structural provider per repo profile.
Dual-active query fan-out is forbidden by default.

**Not primary providers:** Graphify-class multimodal graphs; proprietary IDE indexes;
pure vector RAG as the main backend.

Vibe MUST NOT reimplement tree-sitter / call-graph engines inside Engine.

---

## 4. Index states

`index_state` values (target JSON):

```text
missing
indexing
ready
stale
unavailable
conflict_needs_choice
```

| State | Meaning |
|---|---|
| `missing` | capability enabled but no usable index/artifact |
| `indexing` | mutation in flight |
| `ready` | provider reports usable index **and** freshness policy passes |
| `stale` | index exists but lags HEAD and/or dirty policy |
| `unavailable` | provider binary/MCP/config missing or broken |
| `conflict_needs_choice` | multiple candidate installs detected; owner/agent must choose adopt path |

Freshness inputs (minimum):

```text
observed_head
index_commit
dirty (bool)
freshness_policy (e.g. allow_dirty_query | require_clean | warn_dirty)
```

`ready` MUST NOT be claimed when `index_state=stale` unless an explicit
degraded mode is set and reported (`mode=degraded`).

---

## 5. Git fusion contract

Hetu CLI MAY invoke git for coordinates and change sets.

**In scope**

```text
HEAD / observed_head
dirty detection (git status --short or equivalent)
diff file set vs base_ref / since
pass change set into provider impact (e.g. detect_changes)
bind index_commit on successful reindex
```

**Out of scope**

```text
git push / fetch / rebase / history rewrite
interactive conflict resolution
blame narrative as a first-class Hetu product surface
```

Default impact scope (target):

```text
vibe hetu impact --json
  → vs HEAD (unstaged+staged as policy allows)
vibe hetu impact --since <ref> --json
  → vs git ref / date understood by provider+git
```

Every impact / structural “ready” envelope SHOULD include:

```text
data.git.observed_head
data.git.dirty
data.git.base_ref          # when applicable
data.index.index_commit
data.index.index_state
```

---

## 6. Adopt existing installs

Consumer repos may already have Beads-like or graph tooling installed
(`.codebase-memory/`, `.codegraph/`, MCP client config, etc.).

Required flow:

```text
1. detect     → doctor/status lists candidates (paths, provider hints)
2. choose     → next_actions; agent prompts owner
                skip | readonly bind | enable+adopt
3. adopt      → Vibe owns control plane; PRESERVE config + index data
4. fail closed → unresolved conflict_needs_choice ≠ ready
```

Forbidden by default:

```text
silent reinit that deletes existing graph artifacts
forcing a second full index when an adoptable artifact exists
```

Same adopt pattern SHOULD stay aligned with Task’s “existing Beads” reality:
detect → choose → gate; do not wipe.

---

## 7. CLI surface (target; not shipped)

Naming is target contract; flags may refine in implementation.

### Readonly (MVP A) — `mutation: false`

```text
vibe hetu status --json
vibe hetu doctor --json
vibe hetu search --query <str> --json
vibe hetu trace --symbol <str> --direction inbound|outbound|both --json
vibe hetu impact [--since <ref>] --json
vibe hetu architecture --json
```

Optional later readonly:

```text
vibe hetu snippet --qualified-name <str> --json
```

### Mutations (MVP B) — explicit apply

```text
vibe hetu reindex --dry-run --json
vibe hetu reindex --apply --json
```

Dangerous provider ops (delete project, wipe artifact) require **explicit owner
approval** class — never agent-autonomous by default.

### Learning / self-explain

```text
vibe --help / vibe hetu --help
vibe describe --json          # must list hetu when catalog accepts it
vibe doctor --json            # capability guidance when enabled/disabled
```

Skills remain thin routers to these commands. Do not put provider tool zoos in skills.

---

## 8. Envelope / evidence rules

All Hetu commands emit the standard Vibe envelope family:

```text
ok
code
mutation
reason
next_actions[]
data.*
```

Structural answers are **facts under graph+git constraints**, not narratives.
When the provider cannot prove a path/caller, say so (`uncertainty` /
empty result + reason) — do not invent edges.

Redaction: committed reports MUST NOT include provider secrets, raw auth,
or unnecessary absolute home paths when a repo-relative form exists.

Evidence alignment (with Front/Core S1 snapshot philosophy):

```text
run_id / command / mode
base_head / observed_head
index_commit / index_state
provider id
mutation intent/result
```

---

## 9. Approval matrix (Hetu slice)

**Agent-autonomous when CLI allows (readonly):**

```text
status / doctor / search / trace / impact / architecture
reindex --dry-run
```

**Explicit owner approval:**

```text
reindex --apply outside agreed dogfood/autonomy policy (initial default: owner ask)
delete / wipe provider project or on-disk graph artifact
provider / auth / binary install that mutates machine-wide MCP config
switching active provider when it would orphan or dual-bind indexes
```

**Unsafe → skip/block + next_actions (no ad hoc Q&A):**

```text
conflict_needs_choice
provider unavailable
index missing while claiming ready
stale index while claiming product-structural certainty
```

---

## 10. product_ready / closeout interaction

**v0.1 rule (until runtime acceptance):**

```text
Hetu MUST NOT participate in product_ready or closeout_complete.
Knowledge + Task halves remain as today.
```

**Future target (only after Front/Core accepts):**

```text
If components.hetu.enabled=false → ignore hetu for product_ready
If enabled=true → require interpretable provider + policy-defined freshness
                 for any claim that “structure understanding is ready”
Hetu never replaces knowledge ask hygiene or task_cache_current
```

Cross-surface compose (brief / implementation prompt auto-impact) is **slice C**
and out of this MVP contract.

---

## 11. Division vs Knowledge / Task

| Need | Use |
|---|---|
| MUST / decision / policy from SSOT | `vibe knowledge …` |
| Next work / Beads readiness | `vibe task …` / path A `bd …` |
| Callers, impact, architecture seams | `vibe hetu …` (when shipped) |
| Workflow / dep chains | Task + Beads — **not** Hetu |

Agents may **read both** Knowledge and Hetu results; Hetu MUST NOT merge them
into one fuzzy answer API.

---

## 12. MVP acceptance sketch (pre-roadmap)

Design is accepted when this spec + decision note are linked from Front/Core
and Product thinking index.

**Runtime MVP (future anchor) must prove:**

1. Fake provider tests for status/impact envelopes + freshness fields  
2. Readonly commands fail closed on missing/stale/unavailable  
3. `reindex --dry-run/--apply` mutation flags correct  
4. Adopt detect path does not wipe fixtures  
5. Disabled capability does not break existing knowledge/task dogfood  

---

## 13. Non-goals (normative)

```text
no workflow engine
no second NotebookLM
no Beads graph reimplementation
no default dual provider fan-out
no full git frontend
no scenario menu productization
no shipped claims without CLI + tests
```

---

## 14. Phase / research docs

`docs/project/sync/20260719-hetu-capability-decision.md` remains the accepted
strategy note. Landscape star counts and competitor tables there are research,
not runtime requirements.

`docs/project/sync/*.md` (other) stay implementation/history detail — not default
Knowledge inventory unless explicitly selected.
