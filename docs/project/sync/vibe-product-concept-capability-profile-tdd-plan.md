# Vibe Product Concept Boundary + Capability Profile — TDD-First Design Plan

**Status:** planning / harness detail (not product SSOT; not default knowledge inventory)  
**Date:** 2026-07-17  
**Front/Core contract:** `docs/project/vibe-control-spec.md`  
  (Product concept boundary + Capability Profile target contract)  
**Roadmap activation:** `docs/project/vibe-control-roadmap-state.md`  
**Language policy:** Explanation in Chinese optional; code, commands, keys, schemas in English.

---

## 0. Positioning

This plan turns the owner-accepted Concept Boundary + Capability Profile track into a
coding-agent sequence. It is **not** automatic CLI progression and **not** Phase 13.

| Layer | Role |
|---|---|
| Roadmap-state | Owns which slice is current (`next_actionable_task` + `actionable`) |
| This file | TDD design / entrypoints / fail-closed cases for implementers |
| Coding agent | Implements **one** current actionable slice after greenlight |
| Closeout | Required after each slice SSOT flip (knowledge + task-cache halves) |

Hard rules:

```text
1. Slice 1 is SSOT/tests only — no runtime readiness flip.
2. Vibe product ≠ SSOT manager ≠ roadmap manager ≠ workflow engine.
3. roadmap.* / roadmap-state remain dogfood/source-task patterns only.
4. managed_key / SSOT identity remain stable task identity (not roadmap.* prefix).
5. Operation recovery stays design-only and non-current until this track completes.
6. No Phase 13. No OpenSpec / Spec Kit / Superpowers live integration.
7. Queued slices use phase_state=accepted + actionable=false until promoted.
8. ChatGPT Project Sources are not a product gate.
```

---

## 1. Slices

| Slice | Anchor | Intent |
|---|---|---|
| 1 (completed) | `roadmap.vibe_product_concept_boundary_contract` | SSOT/tests for concept boundary + target profile; runtime unchanged |
| 2 (current) | `roadmap.vibe_capability_profile_runtime` | Runtime defaults: all disabled; enabled knowledge/task gate providers |
| 3 | `roadmap.vibe_capability_profile_install_init_guidance` | Install/init-preview guidance + enable prerequisites |
| 4 | `roadmap.vibe_capability_profile_doctor_gateway_guidance` | Doctor/gateway/describe guidance; Engine vs capability readiness |
| later | `roadmap.vibe_operation_recovery_design` | Design-only S2 evaluation (sequenced after Slice 4) |

---

## 2. Shared entrypoints (inspect before coding)

| Area | Path |
|---|---|
| Front/Core | `docs/project/vibe-control-spec.md` |
| Roadmap SSOT | `docs/project/vibe-control-roadmap-state.md` |
| Component catalog / resolver | `src/vibe_control/components.py` |
| Product readiness | `src/vibe_control/product_readiness.py` |
| Integration status | `src/vibe_control/integration.py` |
| Doctor / CLI | `src/vibe_control/cli.py` |
| Describe / Progress / Brief / Gateway | `describe.py`, `progress_brief.py`, `gateway.py` |
| Skills | `src/vibe_control/skills/` |
| Implementation prompt | `src/vibe_control/implementation/prompt.py` |
| Existing baseline tests | `tests/test_component_runtime_*.py`, `tests/test_roadmap_state_ssot.py` |

---

## 3. Required named cases (track-wide)

Implementers MUST cover these named cases across Slice 2–4 (Slice 1 documents them):

| Case id | Intent |
|---|---|
| `fresh_default_profile` | All capabilities disabled; Engine can remain healthy; disabled do not fail product_ready |
| `enable_knowledge` | Enabling knowledge adds NotebookLM readiness / sync / ask-hygiene gates |
| `enable_task` | Enabling task adds Beads provider / task-cache readiness gates |
| `unsupported_sdd_tdd` | Enabling sdd or tdd fails closed (not implemented) |
| `gateway_skills_thin_routing` | Gateway/Skills route to Engine only; no second readiness engine |
| `init_profile_preview` | Install/init-preview shows target disabled-by-default + enable prerequisites |
| `project_sources_not_product_gate` | ChatGPT Project Sources are advisor copies only; never closeout/product_ready gate |
| `provider_unavailable` | Enabled+unavailable fails closed with provider codes; disabled+unavailable does not fail solely for that provider |

---

## 4. Slice 1 — Concept boundary contract (completed)

### 4.1 CLI JSON assertions (readonly)

```text
After Slice 1 closeout:
  vibe implementation next --json
    → roadmap.vibe_capability_profile_runtime

  vibe implementation prompt --task roadmap.vibe_product_concept_boundary_contract --json
    → task_completed / do_not_restart / no Implement:

  vibe progress|brief|describe|gateway --json
    → mutation=false; project Engine next without recomputing readiness
```

### 4.2 Positive / negative (SSOT)

Positive: product surface, thin Gateway/Skills, dogfood roadmap.*, managed_key identity,
target all-disabled profile, Engine vs capability readiness, Project Sources not gate.

Negative: no runtime flip in Slice 1; no provider/Beads mutation; no Phase 13;
no SSOT/roadmap/workflow product framing.

---

## 5. Slice 2 — Capability profile runtime (current)

### 5.1 Expected behavior

```text
fresh_default_profile:
  knowledge/task/sdd/tdd disabled → Engine can still be healthy
  disabled capabilities do not fail product_ready

enable_knowledge:
  requires NotebookLM readiness / sync / provider_ask_clean gates

enable_task:
  requires Beads/provider/task_cache_current gates

unsupported_sdd_tdd:
  enabled=true → fail closed (unsupported / not implemented)
```

### 5.2 Provider unavailable (`provider_unavailable`)

- Enabled knowledge + NotebookLM unavailable → fail closed with provider codes (not install auto-recovery)
- Disabled knowledge + NotebookLM unavailable → must not fail solely because knowledge provider is down
- Same symmetry for task/Beads when disabled vs enabled

### 5.3 Mutation boundaries

- Runtime slice may change resolver/readiness classification only
- No raw provider commands; no live Beads without Option A gates
- No closeout apply inside feature work unless closeout required after SSOT flip

### 5.4 Install/config next_actions

```text
When enable is desired but prerequisites missing:
  next_actions point at config validate / doctor / bounded closeout dry-run
  never silent auto-enable
  never raw nlm / bd
```

### 5.5 Redaction

- Status/doctor/prompt JSON must not expose raw notebook refs, source IDs, secrets, cookies

### 5.6 Tests

- Focused matrix for all required named cases above that are runtime-relevant
- Regression: existing Component Runtime fail-closed reasons still coherent where applicable

---

## 6. Slice 3 — Install / init profile guidance

### 6.1 Expected (`init_profile_preview`)

```text
init-preview / template guidance shows target disabled-by-default shape
next_actions for enabling knowledge/task list config prerequisites only
invalid examples are diagnostic-only
no silent auto-enable
```

### 6.2 Tests

- Template/init guidance examples match target profile
- Enabling guidance does not claim providers were mutated

---

## 7. Slice 4 — Doctor / Gateway guidance

### 7.1 Expected (`gateway_skills_thin_routing`)

```text
doctor/gateway/describe explain Engine readiness vs capability readiness
readonly paths mutation=false
Gateway/Skills remain thin routers (no second readiness engine)
next_actions never become roadmap-manager / SSOT-manager UX
project_sources_not_product_gate remains explicit
```

### 7.2 Tests

- Doctor JSON fields for capability profile summary
- Gateway status/what_next still pass through Engine
- Redaction suite still green

---

## 8. Closeout expectations (every slice)

```text
1. Commit SSOT/code for the single current slice
2. vibe closeout run --dry-run --json
3. If bounded sync required: vibe closeout run --apply --json
4. If task_cache pollution: follow explicit vibe task cache reset next_actions only
5. Confirm next promotes exactly one queued anchor (or recovery after Slice 4)
6. Empty git status --short after closeout convergence
```

---

## 9. Risks

| Risk | Mitigation |
|---|---|
| Confusing target contract with current runtime | Front/Core labels CURRENT vs TARGET; Slice 1 forbids runtime flip |
| Agents treat roadmap.* as product feature | Concept boundary text + Describe/non-goals |
| Premature operation recovery | Recovery stays actionable=false until after Slice 4 |
| Collapsing Engine + capability readiness | Explicit separation in contract + Slice 2 tests |
| Accidental SDD/TDD enable | Keep fail-closed; no OpenSpec/Spec Kit/Superpowers |
| Project Sources treated as truth | Explicit advisor-only + named case |

---

## 10. Do-not-do list

```text
- No workflow engine
- No roadmap manager / SSOT manager product
- No Phase 13
- No operation recovery implementation in this track
- No install/adapt/uninstall product flows beyond guidance text
- No push from coding agents unless explicitly requested
- Do not claim ChatGPT Project Sources were updated
```
