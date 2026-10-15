# Component Runtime Continuation — TDD-First Design Plan

**Status:** planning / harness detail (not product SSOT; not default knowledge inventory)  
**Date:** 2026-07-16  
**Depends on:** Slice 1 completed (`roadmap.component_runtime_core_baseline`, commits
`8c15d2d` / closeout `d64922e`)  
**Roadmap activation:** `docs/project/vibe-control-roadmap-state.md`  
**Front/Core contract:** `docs/project/vibe-control-spec.md` (Component Runtime section)  
**Language policy:** Explanation in Chinese optional; code, commands, keys, schemas in English.

---

## 0. Positioning

This plan turns Front/Core landing-order Slice 2–5 into an **owner-accepted coding-agent
sequence**. It is **not** automatic CLI progression and **not** Phase 13.

| Layer | Role |
|---|---|
| Roadmap-state | Owns which slice is current (`next_actionable_task` + `actionable`) |
| This file | TDD design / entrypoints / fail-closed cases for implementers |
| Coding agent | Implements **one** current actionable slice after advisor review |
| Closeout | Required after each slice SSOT flip (knowledge + task-cache halves) |

Hard rules:

```text
1. Do not implement Slice 2–5 in the SSOT-activation commit.
2. Do not reuse roadmap.component_runtime_core_baseline.
3. Do not invent Phase 13.
4. Do not greenlight implementation when config_ok=false.
5. No NotebookLM / Beads mutation inside slice feature work unless closeout gates require it.
6. Queued slices use phase_state=accepted + actionable=false until promoted.
```

Schema note (accepted but not current):

```text
phase_state=accepted + actionable=false  → queued sequence (NOT completed)
phase_state=accepted + actionable=true   → current work (Slice 2 only now)
phase_state=completed + actionable=false → truly done (Slice 1)
```

Soft debt: some CLI summaries still put all non-actionable anchors under
`completed_anchors` / apply `skip_completed`. Implementers must not treat that label as
true completion for Slice 3–5.

---

## 1. Shared baseline (Slice 1 already landed)

| Surface | Entrypoint | Contract today |
|---|---|---|
| Resolver | `src/vibe_control/components.py` | fixed catalog; `components.<id>.enabled` only |
| Readiness | `src/vibe_control/product_readiness.py` | `config_ok` gates `product_ready` |
| Integration | `src/vibe_control/integration.py` | `data.config_ok`, `data.components`, blocked_reasons |
| Tests | `tests/test_component_runtime_baseline.py` | matrix for Slice 1 |

Continuation slices **consume** this baseline; they must not weaken fail-closed reasons:

- `required_component_disabled`
- `unsupported_component_enabled`
- `unknown_component_configured`

---

## 2. Slice 2 — Doctor / implementation prompt awareness

**Anchor:** `roadmap.component_runtime_doctor_prompt_awareness`  
**Current:** yes (`actionable=true`, `next_actionable_task`)

### 2.1 Entrypoints to inspect / modify

| Area | Path |
|---|---|
| Doctor CLI | `src/vibe_control/cli.py` → `cmd_doctor` |
| Implementation prompt | `src/vibe_control/implementation/prompt.py` → `build_implementation_prompt` |
| Prompt CLI orchestration | `src/vibe_control/implementation/cli.py` |
| Readiness reuse | `product_readiness.py` / `integration.build_integration_status` / `components.resolve_components_from_repo` |
| Existing doctor/init boundary notes | `docs/project/sync/phase10-5-skills-doctor-init-cli-boundary-spec.md` |

### 2.2 Expected CLI JSON / output contracts

`vibe doctor --json` (additive; keep existing fields):

```text
data.config_ok: bool
data.components: {knowledge,task,sdd,tdd → support_state/enabled/readiness_role/...}
data.component_blocked_reasons: list[str]   # or reuse blocked_reasons subset
# Must NOT expose raw notebook refs / source IDs / secrets
```

`vibe implementation prompt --json`:

```text
data.product_readiness.config_ok (or sibling component_runtime summary)
prompt product_ready / readiness summary includes config_ok + component blocked reasons
when config_ok=false:
  implementation_ready=false
  no "Implement:" greenlight (same family as other readiness blocks)
```

### 2.3 Positive cases

- No `components:` section → `config_ok=true`; doctor/prompt green path unchanged aside from explicit component summary defaults
- `components.sdd.enabled=false` + `components.tdd.enabled=false` → still `config_ok=true`
- Existing knowledge/task readiness still drives product_ready when config_ok=true

### 2.4 Negative / fail-closed cases

- `components.knowledge.enabled=false` → doctor shows `config_ok=false` + `required_component_disabled`; prompt refuses greenlight
- `components.task.enabled=false` → same
- `components.sdd.enabled=true` / `tdd.enabled=true` → `unsupported_component_enabled`
- unknown key under `components` (enabled true or false) → `unknown_component_configured`
- failures classified as **config invalid**, never as provider unavailable / do not trigger install/fallback recovery

### 2.5 Focused tests to add/update

- New: `tests/test_component_runtime_doctor_prompt_awareness.py` (preferred) or extend
  `tests/test_component_runtime_baseline.py` + `tests/test_phase12_implementation_prompt.py`
- Cover doctor JSON fields + prompt Implement: omission matrix
- Keep redaction assertions (no raw provider IDs / secrets)

### 2.6 Existing suites to run

```bash
pytest -q tests/test_component_runtime_baseline.py tests/test_phase12_implementation_prompt.py \
  tests/test_product_readiness.py tests/test_integration_status.py
scripts/test-closeout-local-fast.sh   # while iterating
# before claim: scripts/test-full-local-readonly.sh
```

### 2.7 Provider mutation boundaries

- Slice 2 implementation: **no** NotebookLM apply, **no** Beads mutation
- Closeout after Slice 2 SSOT completion: only via `vibe closeout run` + explicit task next_actions

### 2.8 Non-goals

- Template/init-preview (Slice 3)
- Adoption detect (Slice 4)
- Provider integration (Slice 5)
- Phase 13 / OpenSpec / Spec Kit / Superpowers

### 2.9 Closeout expectations

After Slice 2 code lands and roadmap marks Slice 2 completed / promotes Slice 3:

1. commit clean tree  
2. `vibe closeout run --dry-run/--apply` if bounded  
3. task cache converge/reset only via CLI next_actions (expect possible create for newly actionable Slice 3, and/or conflict/reset for completed Slice 2 managed task)

### 2.10 Risks / coding-agent recommendations

- **Risk:** doctor today does not call product readiness; wire via `resolve_components_from_repo` without duplicating resolver logic.
- **Risk:** prompt already blocks on product_ready=false; ensure `config_ok=false` is visible in prompt text even when other reasons also block.
- **Tighten before coding if needed:** define exact doctor field names in a short contract snippet in this file once advisor picks `component_blocked_reasons` vs embedding in `blocked_reasons`.
- **Do not** expand Slice 2 into template or adoption work.

---

## 3. Slice 3 — Template / init-preview guidance

**Anchor:** `roadmap.component_runtime_template_init_preview_guidance`  
**Current:** queued (`accepted`, `actionable=false`)

### 3.1 Entrypoints

| Area | Path |
|---|---|
| Control template | `src/vibe_control/templates/control.yaml` |
| Template path helper | `vibe_control.config.template_path` |
| Doctor next_actions referencing template | `cli.cmd_doctor` |
| Knowledge init-preview | `cli.cmd_knowledge_init_preview` / `knowledge/doctor.py` |
| Task init-preview | `cli.cmd_task_init_preview` |
| Phase 10.5 boundary | `docs/project/sync/phase10-5-skills-doctor-init-cli-boundary-spec.md` |

### 3.2 Expected contracts

- Template and/or init-preview JSON includes **commented or documented** valid
  `components.<id>.enabled` examples
- Default guidance: knowledge/task enabled (or omitted = default true); sdd/tdd disabled
- Invalid examples appear only as diagnostic text / examples — never applied to live config

### 3.3 Positive / negative

- Positive: preview shows safe shape; unsupported components shown disabled by default
- Negative: no install/adapt/uninstall; no writing `.config/vibe-control.yaml` without explicit user action

### 3.4 Tests

- Template content assertions (components examples present; no enabled=true for sdd/tdd by default)
- init-preview envelope assertions if guidance is emitted there
- Regression: existing phase10.5 / beads bootstrap tests still pass

### 3.5 Suites

```bash
pytest -q tests/test_phase10_5.py tests/test_beads_bootstrap.py
# plus new focused template/init-preview tests
```

### 3.6 Boundaries / non-goals

- No provider mutation; no adoption detect; no plugin registry

### 3.7 Risks / recommendations

- Prefer documenting components in template comments + doctor/init-preview guidance text
  over inventing a new mutation command.
- Keep examples synchronized with `COMPONENT_CATALOG` in `components.py` (single source or generated comment).

---

## 4. Slice 4 — readonly adoption detect

**Anchor:** `roadmap.component_runtime_readonly_adoption_detect`  
**Current:** queued

### 4.1 Entrypoints (inspect first; design after)

| Area | Path |
|---|---|
| Doctor | `cli.cmd_doctor` (natural home for readonly diagnostics) |
| Integration status | `integration.py` (optional advisory section only) |
| Existing provider status | NotebookLMProvider / BeadsProvider `status()` |
| Spec language | Front/Core component vs provider distinction |

### 4.2 Expected contracts

```text
readonly adoption / adjacency report (exact key TBD at implementation design freeze):
  - detected surfaces (advisory)
  - missing/unavailable tools reported as unavailable — NOT empty inventory
  - does NOT flip product_ready by itself unless a later accepted SSOT says so
```

### 4.3 Positive / negative

- Positive: reports presence/absence of adjacent tools without changing config
- Negative: no unmanaged adoption; no install; unavailable ≠ empty

### 4.4 Tests

- Fake missing binary → unavailable classification
- Detection call leaves config files / git status unchanged
- product_ready unchanged when only detection runs

### 4.5 Boundaries

- Readonly only; no Beads/NotebookLM mutation

### 4.6 Risks / recommendations

- **Do not** invent a broad scanner. Freeze a minimal adjacency list from Front/Core
  (e.g. knowledge/task providers only) before coding.
- Keep detection out of `product_ready` unless explicitly accepted later.

---

## 5. Slice 5 — future provider integration (boundary prep)

**Anchor:** `roadmap.component_runtime_future_provider_integration`  
**Current:** queued

### 5.1 Entrypoints

| Area | Path |
|---|---|
| Component catalog / readiness roles | `components.py`, Front/Core status language |
| Provider adapters | `knowledge/*`, `task/*` |
| Mutation contracts | `docs/harness/real-integration-mutation-contract.md` |
| Approval matrix | `docs/project/vibe-control-spec.md`, `AGENTS.md` |

### 5.2 Expected contracts

- Document / encode **boundary preparation only**: how a future provider would bind to a
  component without becoming a component ID
- Fail closed on unsupported component/provider combinations
- No live OpenSpec / Spec Kit / Superpowers / external provider integration unless a
  later accepted repo spec says so

### 5.3 Tests

- Unit tests for fail-closed mapping stubs / allowlists
- Assert no live mutation paths are introduced by Slice 5 prep
- No plugin registry/framework unless SSOT explicitly requires it

### 5.4 Risks / recommendations

- Keep Slice 5 **thin**. Prefer harness + spec + fail-closed stubs over shipping a registry.
- If scope threatens to become a plugin framework, stop and re-accept a narrower slice.

---

## 6. Recommended acceptance commands (all slices)

```bash
# Focused (per slice)
pytest -q tests/test_component_runtime_*.py

# Iteration
scripts/test-closeout-local-fast.sh

# Before closeout claim
scripts/test-full-local-readonly.sh

# Readonly product gates
vibe integration status --json
vibe closeout run --dry-run --json
vibe implementation next --json
vibe implementation prompt --task <current_slice_anchor> --json
```

Promotion rule after a slice completes:

```text
1. Mark completed slice completed/actionable=false (+ completed_scope)
2. Set next slice actionable=true and next_actionable_task=<that slice>
3. Leave later slices accepted + actionable=false
4. Run closeout transaction (knowledge then task-cache next_actions)
```

---

## 7. Coding-agent recommendation (before Slice 2 implementation)

1. Implement **only Slice 2** from this plan.  
2. Prefer reusing `resolve_components_from_repo` over a second resolver.  
3. Freeze doctor JSON field names in the first Slice 2 PR description / tests.  
4. Do not promote Slice 3–5 to actionable in the same PR as Slice 2 implementation.  
5. After Slice 2 lands, expect Beads `missing` for the Slice 2 managed task (or conflict on
   later completion) — follow closeout CLI next_actions; do not improvise raw `bd`.
