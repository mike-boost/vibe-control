# Vibe Control Spec (Front / Core)

**Document type:** Local repo Front/Core formal SSOT  
**Status:** v0.11.0 — Vibe Product Concept Boundary + Capability Profile Track accepted
**Date:** 2026-07-17  
**Primary audience:** Coding agents, repository maintainers  
**Language policy:** Explanation in Chinese; code, commands, schemas, filenames in English.

---

## 0. What this file is

```text
docs/project/vibe-control-spec.md
  = Front/Core product contract (active formal SSOT)

Companion formal specs (also active):
  docs/project/vibe-control-knowledge-spec.md
  docs/project/vibe-control-task-spec.md
  docs/project/vibe-control-hetu-spec.md       # code-structure capability (design; runtime later)
  docs/project/vibe-control-feedback-spec.md   # experience-signal capture (not tasks)
  docs/project/vibe-control-roadmap-state.md   # high-churn phase_state / next task

Decision log (optional history; not default inventory / external advisor copy set):
  docs/project/DECISION_LOG.md

External advisor context copies (§10)
  = owner-managed external copies only
  = NOT repo state, NOT NotebookLM sync source, NOT CLI-observable
  = NOT a product closeout gate
  = coding agents must NOT claim to observe or update them
```

---

## 1. Product one-page

Vibe Control is an **agent-facing, provider-backed** control product.

```text
Primary operator  = coding agent (vibe CLI + harness)
Human role        = boundaries + Approval Matrix decisions
Repo / git SSOT   = truth
Knowledge provider = exactly one of {local_fts, notebooklm} (derived; owner-selected)
Beads              = task provider (derived)
Repo fallback      = degraded read only (NOT product_ready)
Skills             = thin routers to CLI
```

### Knowledge provider selection (v1 accepted)

```text
Who selects?     Owner sets knowledge.provider in .config (explicit).
                 Doctor probes availability; CLI never auto-switches providers.
Active rule:     knowledge.provider is the sole active knowledge provider.
                 fallback_provider=repo is degraded only — never promotes to product_ready
                 and never silently replaces local_fts when dirty.
Equivalence:     local_fts synced+ask-clean OR notebooklm synced+ask-clean
                 each satisfies the knowledge half of product_ready.
                 Do not mix halves across providers in one probe.
Switching:       Per-provider state is independent (SQLite index vs NLM receipt).
                 Switching provider does not migrate old state; new active starts at drift
                 until its own sync/rebuild succeeds.
Describe:        knowledge_provider_selection_guidance explains why/how to choose.
```

### Product concept boundary (accepted)

```text
Vibe product surface =
  Engine + Gateway + Knowledge + Task + Hetu + Capability Profile
  (Hetu = design-accepted peer capability; runtime/CLI not shipped yet)

Gateway / Skills =
  thin routers to Engine surfaces only
  (no second readiness engine; no stored product truth)

Vibe product is NOT:
  - an SSOT manager / SSOT management product
  - a roadmap manager
  - a workflow engine

Repo SSOT / roadmap-state / roadmap.* anchors =
  this repo's dogfood / source-task patterns
  (self-development operator workflow)
  ≠ external product features
  ≠ product API surface for customers

Product may consume configured source paths /
  selected SSOT inventory for Knowledge sync,
  but does NOT own generic SSOT management.

Stable task identity =
  SSOT identity / managed_key
  ≠ roadmap.* string prefix as identity
  ≠ provider_task_id as identity

Project Sources =
  external advisor context copies only
  ≠ product truth / closeout gate
```

Critical principles:

```text
NotebookLM synced ≠ Beads truth
Repo SSOT = Beads expected-task truth
provider_task_id = binding only
managed_key = stable task identity
Unavailable / drift / provider_ask_clean=false → never green product_ready
```

### Spec map

| Layer | File | Owns |
|---|---|---|
| Front/Core | `vibe-control-spec.md` | product model, Product Interface & State Contract, Approval Matrix, workflow, product_ready summary, Phase 12 front contract, SSOT closeout states |
| Knowledge | `vibe-control-knowledge-spec.md` | SSOT selection, sync lifecycle, ack/receipt, query, ask hygiene, knowledge half of closeout |
| Task | `vibe-control-task-spec.md` | projection identity, managed_key, reconcile/apply, Option A live gate, task fields for prompts |
| Hetu | `vibe-control-hetu-spec.md` | code-structure capability; index freshness; git fusion; provider adopt; CLI target (runtime not shipped) |
| Feedback | `vibe-control-feedback-spec.md` | experience-signal artifacts (pain / dissatisfaction / bright spot); redaction; voluntary share; **not** tasks |
| Roadmap state | `vibe-control-roadmap-state.md` | high-churn `phase_state` / `actionable` / `next_actionable_task` (projection reads here) |
| Decisions | `DECISION_LOG.md` | short decision history only — not current actionable state; not default inventory |
| Phase/dev | `docs/project/sync/*.md`, `docs/harness/*` | historical / implementation detail — not default knowledge inventory / external advisor copy set |

---

## 2. Role model / source hierarchy

**Product truth / closeout layers** (CLI-observable):

```text
1. Local repo committed SSOT (formal active specs + include_extra)
2. NotebookLM ProviderTarget (derived sync of selected repo SSOT / default inventory)
3. Beads task provider / task-cache state (derived bindings for expected tasks)
```

**External advisor copies (outside product closeout):**

```text
External advisor context copies
  = owner-managed copies of selected repo files
  = may affect external advisor context freshness only
  = must NOT affect product_ready, closeout_complete, provider_sync_required,
    or implementation readiness
```

Do not confuse product layers with advisor copies.

NotebookLM sync always sources from layer 1 (fixed local repo SSOT selection /
default inventory). It never reads or writes external advisor context copies.

---

## 3. Approval Matrix

**Agent-autonomous when CLI allows (no per-op user ceremony):**

```text
- readonly status / query / reconcile / doctor / integration / implementation prompt
- Skill Assay: `vibe skill-assay doctor|report` (readonly); `diagnose --dry-run`
- Skill Assay: `diagnose --execute` / `finalize` write local receipts only
  (`runtime/vibe-skill-assay/`); not product_ready / closeout. Live Cursor/Copilot
  hosts require installed SDKs and a `supported` adapter (else fail closed as unverified).
- fake provider task apply (tests)
- Vibe-managed create/update POLICY when product_ready + current plan binding + safe managed ops only
- Bounded NotebookLM sync --apply during normal SSOT closeout when preconditions pass
  (committed SSOT, empty git status --short, dry-run limited to current active SSOT /
  default inventory expected updates only)
```

**Option A live Beads (still temporary dual-gated):**

```text
--apply --provider beads --autonomous-managed --confirm-beads-live-apply
+ VIBE_BEADS_LIVE_APPLY=1
+ product_ready + safe managed plan
Default gates never set the live env.
```

**Explicit owner approval required:**

```text
- NotebookLM mutation outside bounded current-SSOT/default-inventory closeout sync
- NotebookLM unmanaged/orphan delete
- NotebookLM broad cleanup / notebook clean
- NotebookLM retry --apply of arbitrary pending provider state
- provider config / secrets / auth / target changes
- git push
- destructive delete
- unmanaged task adoption
- non-deterministic conflict repair
- live Beads when outside Option A / local-ephemeral cache-reset gates
```

**Unsafe task cases → CLI skip/block/repair-plan + next_actions (never ad hoc Q&A).**

`status` / `query` / `doctor` / `inventory` / `sync --dry-run` remain readonly and must never
hidden-mutate. Bounded sync apply is an explicit `--apply` closeout step, not a side effect
of readonly commands.
---

## 4. High-level workflow

```text
repo SSOT
  → knowledge inventory / status / sync --dry-run / query (status-aware)
  → agent reasoning over SSOT-backed facts
  → expected tasks (status-aware projection)
  → task reconcile --dry-run
  → task apply plan / Option A managed apply when approved by gates
  → vibe implementation prompt --task …  (Phase 12)
```

---

## 5. Vibe Product Interface & State Contract

本节定义 Vibe 面向主编码代理（`main coding agent`）的产品接口与最小状态控制合同。
Vibe 不依赖任何外部聊天产品或 advisor 平台。当前范围不支持 sub-agent，
不支持 agent-to-agent handoff，也不引入 sub-agent routing。

```text
Primary user = main coding agent
No sub-agent support in current scope
No platform-specific product dependency
```

### 5.1 Vibe Control Engine

`Vibe Control Engine`（Vibe 权威控制引擎）是 repo-owned authoritative control
engine。它拥有：

```text
- SSOT resolution
- product readiness / config readiness
- SSOT closeout
- task projection
- provider and task gates
- JSON envelopes
- mutation classification
```

Engine 现有 Knowledge 与 Task runtime semantics 保持不变。本 track 只定义新的
产品接口、只读投影与证据合同，不重写现有 provider、readiness、closeout 或 task
行为。

### 5.2 Vibe Gateway

`Vibe Gateway`（Vibe 薄入口）是面向主编码代理的 thin intent router。它只选择
Engine surface，并摘要 Engine 输出。

Gateway MUST NOT：

```text
- store current repo facts
- compute or override readiness
- mutate providers or task cache
- create tasks or roadmap anchors
- route to sub-agents
- become a second state engine
```

Gateway 需要 mutation 时，只能把明确意图路由到现有 Engine `--apply` surface；
mutation scope、approval 和 fail-closed 判断仍由 Engine 拥有。

### 5.3 Readonly projections

`Vibe Progress`（Vibe 进度投影）回答：“项目现在在哪里，下一条安全动作是什么？”
它只投影现有 Engine 输出，包括当前 HEAD、readiness、closeout、task cache 与
roadmap next 状态。

`Vibe Brief`（Vibe 短工作简报）为主编码代理提供简短、可行动的下一步。它比
`vibe implementation prompt` 更短，并可正常返回 `no-next`、`blocked` 或
`closeout-required`。

`Vibe Describe`（Vibe 控制面说明）只读说明 authority map、command surfaces、
mutation classes、component catalog 与 non-goals。它 MUST NOT probe 或计算
product health/readiness。

`Vibe Evidence`（Vibe 证据合同）绑定本次观察或操作的 HEAD、command、mode、
steps、mutation intent/result、hashes、tests、provider/task effects 与 final state。

### 5.4 S1 Ephemeral Operation Snapshot

`S1 Ephemeral Operation Snapshot`（S1 临时操作快照）是当前接受的最小
state-control strategy。每个 command / operation 的证据快照至少包含：

```text
run_id
base_head
observed_head
operation
steps
mutation_intent
mutation_performed
next_actions
blocked_reasons
evidence_hash
```

Migrated JSON command envelopes（见 `vibe describe --json` → `operation_evidence`）
additionally expose top-level:

```text
mutation_intent      # bool — apply/write path even if blocked
mutation_performed   # bool — derived from completed effects[]
mutation             # compatibility alias of mutation_performed
effects[]            # completed writes only: {kind,target,status:"completed"}
```

Rules:

- `mutation == mutation_performed` during the compatibility period.
- Nested `data.mutation` aliases must agree with top-level performed evidence.
- `ok=false` with non-empty completed effects requires `partial_success=true`.
- Approval remains capability-specific (no universal MutationGate).
- `gateway --intent grill_brief` is `local_runtime_write`, not unconditionally readonly.
- Ordinary Progress/Brief MUST NOT repair a dangling self-grill active pointer.

S1 不是 persistent workflow ledger，不是 repo truth，不保存跨 run provider truth，
也不提供通用 replay。`S2 lightweight ledger` 延后到
`roadmap.vibe_operation_recovery_design` 做 design-only 评估；
`S3 workflow engine` 在当前范围明确拒绝。

### 5.5 Projection and safety rules

```text
Projection-only:
  Progress / Describe / Brief / Evidence MUST consume authoritative Engine outputs.

No second readiness engine:
  They MUST NOT recompute product_ready, config_ok, provider_sync_required,
  provider_ask_clean, task_cache_current, closeout_complete, roadmap next/actionable,
  blocked_reasons, mutation, or next_actions.

Observed state:
  observed_head MUST be current command evidence and MUST be distinguished from any
  recorded_baseline_head / historical roadmap snapshot.

Readonly:
  Readonly surfaces MUST expose mutation_intent=false, mutation_performed=false,
  mutation=false and MUST NOT hidden-mutate repo, NotebookLM, Beads, provider
  receipts, task cache, or self-grill active pointers.
```

Current non-goals: sub-agents; handoff; persistent ledger; workflow engine;
roadmap manager product; SSOT management product; platform-specific
product dependencies; SDD/TDD provider expansion; live OpenSpec / Spec Kit / Superpowers
integration; changing existing Knowledge or Task runtime semantics in activation-only
commits.

---

## 6. product_ready (summary)

### Capability Profile — target contract (accepted; runtime later)

`Capability Profile`（能力配置面）是 Vibe 产品面的一部分。它描述仓库可启用的
capability surfaces，并与 Engine readiness 分离。

```text
Engine readiness     = repo/CLI/control truth (config parse, closeout gates, envelopes)
Capability readiness = per-capability enablement + provider checks when enabled

They MUST NOT be collapsed into one gate that forces every capability on.
```

Capability catalog (IDs unchanged):

```text
knowledge | task | hetu | sdd | tdd
```

**Target profile (accepted contract — not yet runtime):**

```text
Fresh / default target:
  all capabilities disabled by default

knowledge / task:
  support_state = supported (available / enablable)
  may be enabled after config prerequisites
  enabled knowledge → check active knowledge.provider readiness / sync / ask hygiene
                      (local_fts or notebooklm; never repo fallback alone)
  enabled task → check Beads / provider / task-cache readiness
  disabled → NOT a product_ready failure

sdd / tdd:
  support_state = not_supported_yet (not implemented)
  enabled=true → fail closed (unsupported_component_enabled family)
  no provider mutation / install / harness recovery
```

```text
TARGET contract only — runtime unchanged until
roadmap.vibe_capability_profile_runtime lands.

Current Component Runtime Slice-1+ Capability Profile runtime:
  knowledge/task default_enabled=false (optional_when_disabled);
  provider gates apply only when enabled.
Do not treat disabled knowledge/task as config invalid.
```

### Components (config-gated status language)

Components are **config-gated capability surfaces**, not dynamic plugins. This subsection
defines status language only; runtime behavior is unchanged until a later implementation.

#### Component identity and naming

```text
Component IDs = stable first-class capability-surface names
              = simple lowercase identifiers (nouns or established abbreviations)
Current IDs   = knowledge | task | hetu | sdd | tdd

Lifecycle gate (first runtime baseline ONLY):
  components.<component_id>.enabled

Disallowed as component IDs / lifecycle keys:
  specs.sdd | knowledge.notebooklm | tasks.beads | method.superpowers
  (and any nested / provider-scoped name)
```

#### Component vs provider vs existing config sections

```text
component  = Vibe-owned capability surface
provider   = implementation behind a component (hint or future binding)

knowledge → provider notebooklm
task      → provider beads (mode=local_embedded_ephemeral)
sdd       → provider null today; hints openspec, spec_kit
tdd       → provider null today; hints superpowers

Provider names are NOT component IDs unless separately accepted as a Vibe-owned surface.

Existing top-level sections remain their current domains — NOT lifecycle gates:
  knowledge:  knowledge provider configuration
  tasks:      task provider configuration
  specs:      SSOT registry metadata (NOT the sdd component)
```

| id | support_state | default_enabled | provider | readiness_role |
|---|---|---|---|---|
| knowledge | supported | false | notebooklm | optional_when_disabled |
| task | supported | false | beads (`mode=local_embedded_ephemeral`) | optional_when_disabled |
| sdd | not_supported_yet | false | null (`provider_hints`: openspec, spec_kit) | fail_closed_if_enabled |
| tdd | not_supported_yet | false | null (`provider_hints`: superpowers) | fail_closed_if_enabled |

```text
Runtime (Capability Profile): fresh installs / absent components section default
all disabled. Disabled capabilities do not fail product readiness. Enabling
knowledge/task adds provider checks; enabling sdd/tdd fails closed.
```

```text
disabled_by_default     = inactive, not checked, not a product_ready input, not an error
not_supported_yet       = Vibe has not implemented the surface
no components config    → config_ok true; all capabilities disabled (target profile)
```

If a known `not_supported_yet` component is **explicitly enabled** via
`components.<id>.enabled=true`, fail closed:

```text
config_ok=false
product_ready=false   (full configured-system readiness)
block_reason=unsupported_component_enabled
no provider / install / harness mutation
do NOT classify as provider unavailable
```

#### Component admission (catalog growth)

A new component may enter the catalog only when the accepted spec defines all of:

```text
component_id
purpose / owned capability surface
support_state
default_enabled
readiness_role
provider boundary or provider_hints
mutation boundary
fail-closed behavior
minimal JSON / status contract
non-goals
tests or harness expectations for runtime implementation
```

Non-goals here: adoption detect; OpenSpec / Spec Kit / Superpowers integration;
install/adapt/uninstall; provider registry / plugin framework; harness auto-merge;
Phase 13 acceptance; changing existing Knowledge/Task runtime behavior.

### Component Runtime Core Baseline (future implementation guidance)

Runtime baseline = implement the **minimal executable rules** for the status language above.
It does **not** implement OpenSpec, Spec Kit, Superpowers, adoption detect,
install/adapt/uninstall, or new provider integrations.

**Slice 1 historical runtime baseline:**

```text
- fixed component catalog (knowledge, task, sdd, tdd)
- component config resolver reading ONLY components.<component_id>.enabled
- config_ok
- unsupported_component_enabled fail-closed
- product_ready precondition: config_ok=true
- minimal integration status JSON: data.config_ok, data.components
- blocked_reasons may include unsupported_component_enabled,
  required_component_disabled, or unknown_component_configured
- focused tests
```

Defaults stay as in the table above. Capability Profile runtime rules:

```text
explicit components.knowledge.enabled=false or components.task.enabled=false
  → valid; capability skipped; does not fail product readiness
  → provider checks apply only when that capability is enabled

any unknown component entry under components:
  → fail closed (block_reason=unknown_component_configured)
  → regardless of enabled true/false
  (keep first baseline simple; no warning-only unknown keys)

unsupported_component_enabled
  → known not_supported_yet component explicitly enabled only

no components config
  → config_ok implicitly true; all capabilities disabled (target profile)
disabled optional not_supported_yet
  → does not affect product_ready
explicitly enabled not_supported_yet
  → config_ok=false, product_ready=false
  → config invalid — NOT provider unavailable
```

**Landing order → accepted continuation track (roadmap-state owns current next):**

```text
Slice 1  Component Runtime Core Baseline   ← completed (roadmap.component_runtime_core_baseline)
Slice 2  Doctor / implementation prompt awareness   ← completed (roadmap.component_runtime_doctor_prompt_awareness)
Slice 3  Template / init-preview guidance           ← completed (roadmap.component_runtime_template_init_preview_guidance)
Slice 4  readonly adoption detect                   ← completed (roadmap.component_runtime_readonly_adoption_detect)
Slice 5  future provider integration                ← completed (roadmap.component_runtime_future_provider_integration)
```

Current actionable status and promotion order live in
`docs/project/vibe-control-roadmap-state.md`. Coding agents implement one current
anchor at a time; do not invent Phase 13; do not restart completed Component Runtime
Slice 1–5.

Non-goals (until separately accepted beyond this track): OpenSpec / Spec Kit / Superpowers
integration; install/adapt/uninstall; provider registry / plugin framework;
harness auto-merge; Phase 13 acceptance.

`default task mode = local_embedded_ephemeral`

Beads is a **local stage-scoped agent task cache** by default — not durable project truth,
not GitHub collaboration data, and not a team/shared/server mode (out of current scope).

`product_ready=true` requires knowledge half **and** task half **and** task cache current:

```text
knowledge: available, target_ok, synced, provider_ask_clean
task provider: available, readable, ready_queue available (when probed)
task_cache_current: true
blocked_reasons empty
```

`task_cache_current` means:

```text
reconcile: missing=0, stale=0, duplicate=0, conflict=0, unmanaged=0
apply dry-run: create=0, update=0, blocked=0
```

Closeout must **not** accept “Beads stale as soft debt”.

If task cache is not current:

```text
product_ready=false
task_cache_current=false
task_cache_action_required=true
safe_task_convergence_allowed=true|false
task_cache_reset_required=true|false
+ next_actions
```

Safe create/update convergence may proceed when knowledge is ready even if full
`product_ready` is false solely because the cache is not current (no circular dependency).

Probe important nodes / failure branches; reuse evidence within one command; no cross-run
provider truth cache. Repo fallback ≠ product_ready.

---

## 7. SSOT closeout transaction (Front/Core)

When a task changes **active formal SSOT** or **include_extra**, product closeout is a
transaction across **committed repo SSOT**, **NotebookLM provider sync/ask hygiene**, and
**Beads task-cache state**. External advisor context copies are **not** a closeout step or gate.

### States

| State | Meaning | product_ready claim? |
|---|---|---|
| `no_ssot_change_product_ready` | No active SSOT/include_extra change; providers current | yes if probe green |
| `ssot_change_committed_sync_required` | Committed SSOT change; bounded sync not yet run / dry-run not green | **no** — `provider_sync_required=true` |
| `ssot_change_committed_sync_pending` | Bounded sync attempted but incomplete/unavailable | **no** |
| `ssot_change_committed_synced_product_ready` | Committed + knowledge synced + ask-clean + task ready | yes |
| `repo_only_degraded` | Repo fallback usable; provider path not ready | **no** |

`waiting_owner_project_sources` is **not** a product closeout state.

### Closeout flow

```text
1. Commit active SSOT / include_extra change
2. Confirm git status --short is empty
3. Prefer: vibe closeout run --dry-run --json
4. If dry-run reports bounded knowledge work: vibe closeout run --apply --json
   (driver-internal sync dry-run preflight; bounded knowledge sync apply only)
5. If task_cache_current=false: explicit Beads convergence under Approval Matrix
   (closeout driver never auto-mutates Beads)
```

Bounded NotebookLM sync is **not** blocked on external advisor context copies.
Owners may refresh those copies at any time (§10); that action is orthogonal to product
closeout.

`vibe closeout run` is the preferred orchestration entry so agents do not hand-assemble
`knowledge sync` / `integration status` / `task reconcile` sequences.

### Bounded sync preconditions (closeout may apply without a second approval ceremony)

```text
- SSOT change is committed
- git status --short is empty before provider apply
- sync --dry-run plan limited to current active SSOT / default inventory expected updates
- no unmanaged delete, broad cleanup, target mismatch, provider unavailable,
  unexpected source, auth/config change, or raw provider ref exposure
```

If any precondition fails → stop before mutation; report next_actions; require explicit owner
approval for any wider NotebookLM mutation.

### Rules

- Sync from fixed local repo state (prefer committed), not unstable drafts.
- Repo committed SSOT is product truth; NotebookLM is derived; Beads provider_task_id is binding only.
- External advisor context copies are advisor-only; CLI must not claim to observe or update them;
  their freshness must not affect `product_ready`, `closeout_complete`, `provider_sync_required`,
  or implementation readiness.
- `query` / `status` / `doctor` never hidden-mutate.
- Does **not** conflict with forward-only knowledge design: closeout only sequences existing
  product layers; ack remains watermark; provider never becomes SSOT truth.

CLI helpers may surface `closeout_state` / `provider_sync_required` on integration/status envelopes (see tests).

---

## 8. Phase 12 — Implementation Prompt Generator (Front/Core contract)

Product capability: turn SSOT + readiness + reconcile/apply summary + selected managed task into a copy-paste coding-agent prompt.

### Command

```text
vibe implementation prompt --task <managed_key|provider_task_id|ssot_anchor> --json
```

Readonly: `mutation=false`.

### Selectors

1. exact `managed_key`
2. exact `ssot_anchor`
3. `provider_task_id` as **lookup only** (binding → managed identity)

Ambiguous / missing → fail closed (`TASK_SELECTOR_NOT_FOUND` / future `TASK_SELECTOR_AMBIGUOUS`). Stale/conflict context may appear as warnings/next_actions; prompt must not treat Beads id as identity.

### JSON envelope (required)

```text
ok, command, project_id, mutation=false, mode
data.task_identity
data.task_context
data.product_readiness
data.knowledge_readiness
data.task_reconcile_summary
data.task_apply_plan_summary
data.prompt
data.prompt_sections
data.prompt_hash
warnings, next_actions
error (if applicable)
```

**Primary envelope fields:** `data.prompt`, `data.prompt_sections`, `data.task_identity`,
`data.task_context`, `data.product_readiness`, `data.knowledge_readiness`,
`data.task_reconcile_summary`, `data.task_apply_plan_summary`.

Compatibility-only aliases (must not be treated as the main contract): `data.prompt_text`,
`data.task`, `data.sections`, `data.readiness`, `data.reconcile_counts`, `data.apply_plan_counts`.

### Required prompt sections (stable order)

1. task goal / implementation target  
2. repo SSOT identity  
3. selected task anchor  
4. product_ready summary  
5. knowledge readiness summary  
6. task reconcile/apply summary  
7. hard boundaries  
8. mutation approvals required / not required  
9. required tests/gates  
10. expected final report fields  
11. safety confirmation (no push / no provider mutation unless approved)  
12. final `git status --short` expectation  

### Redaction

- No raw notebook refs / source IDs / secrets  
- `provider_task_id` absent or hashed in default envelope  
- `managed_key` / `ssot_anchor` / `ssot_path` allowed  

### Source-of-truth in prompt

- Repo SSOT is truth; NotebookLM is not truth; Beads id is not identity; do not prefer chat memory over repo specs.

### Degraded modes → warnings / next_actions (not green PASS)

`product_ready=false`, knowledge unsynced (`drift` / `pending` / `unavailable`), ask unclean,
task unavailable, reconcile mismatch, apply blocked, **task_cache_current=false**,
ambiguous/missing selector, local modifications, `provider_sync_required=true`.

Implementation remains blocked while any of: `provider_sync_required=true`,
`sync_state` in `{drift,pending,unavailable}`, `provider_ask_clean=false`, or
`task_cache_current=false`. External advisor context-copy freshness is **not** a blocker.

When `task_cache_current=false`, the prompt must **not** greenlight next implementation.
It must show task cache state and required convergence/reset next_action first.

Detail: `docs/project/sync/phase12-implementation-prompt-generator-spec.md` + Task spec §9.

---

## 9. Current accepted implementation summary

```text
Phase 8–10.5   knowledge/publish/skills/doctor boundaries — implemented (safe/default)
Phase 8.1      product_ready probe policy — implemented
Phase 11A      readonly reconcile — complete (safe/default)
Phase 11B      fake apply + Option A autonomous managed live path — implemented; dual gate temporary
Phase 12       implementation prompt — local/readonly implemented; contract hardened in v0.9.3
```

---

## 10. External advisor context copies

External advisor context copies are owner-managed copies used only for external advisor
context. They are:

```text
NOT repo state / product truth
NOT NotebookLM sync sources
NOT CLI-observable product state
NOT a product closeout gate or transaction step
```

Owners may manually refresh them when external advisor context needs updating. Suggested copy set
(order is advisory only; not a closeout sequence):

1. `docs/project/vibe-control-spec.md`
2. `docs/project/vibe-control-knowledge-spec.md`
3. `docs/project/vibe-control-task-spec.md`
4. `docs/project/vibe-control-roadmap-state.md`

Do **not** upload `docs/project/sync/*.md` by default.
`DECISION_LOG.md` is optional history (not default inventory / external advisor copy set).

Rules:

- Coding agents must not claim to observe or update external advisor context copies.
- Copy freshness may affect external advisor context only.
- It must not affect `product_ready`, `closeout_complete`, `provider_sync_required`,
  or implementation readiness.
- Product closeout continues with §7 regardless of whether those copies were refreshed.

---

## 11. Agent harness seeds (short)

```text
Prefer Front/Core + Knowledge + Task + roadmap-state specs over chat memory.
Never claim external advisor context copies were observed or updated by the agent.
Never treat external advisor copy freshness as a product closeout / implementation blocker.
Never push / non-bounded NLM mutation / live Beads outside Approval Matrix.
Closeout: prefer `vibe closeout run --dry-run/--apply --json` (committed SSOT + empty
  git status → bounded knowledge apply → task converge if needed).
```

Harness contracts: `docs/harness/*`, `AGENTS.md`.
