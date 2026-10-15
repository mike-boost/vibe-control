# Vibe Control Roadmap State

**Document type:** Formal current-state SSOT (high-churn roadmap / actionable status)  
**Status:** active  
**Date:** 2026-07-16  
**Front/Core:** `docs/project/vibe-control-spec.md`  
**Rule:** Stable product contracts stay in Front/Core / Knowledge / Task specs.  
**This file owns:** `phase_state`, `actionable`, and `next_actionable_task` only.

```yaml
roadmap_state_version: 1
next_actionable_task: null
no_actionable_next_task: true
current_baseline:
  baseline_state: stable
  last_closeout_verdict: STABLE_BASELINE_ACCEPTED
  baseline_commit: "92699f9"
  git_pushed: false
  status_snapshot:
    product_ready: true
    provider_sync_required: false
    provider_ask_clean: true
    task_cache_mode: local_embedded_ephemeral
    task_cache_current: true
    no_actionable_next_task: true
rules:
  completed_not_default_next: true
  projection_reads_phase_state_here: true
  decision_log_is_history_only: true
  do_not_invent_phase13: true
  component_runtime_one_slice_at_a_time: true
  product_interface_track: Vibe Product Interface & State Contract Track
  engine_is_authoritative: true
  projections_do_not_recompute_readiness: true
anchors:
  - ssot_anchor: roadmap.phase11a
    task_kind: implementation_phase
    title: "Phase 11A — SSOT Specs and Beads Readonly Reconcile"
    phase_state: completed
    actionable: false
  - ssot_anchor: roadmap.phase11b
    task_kind: implementation_phase
    title: "Phase 11B — Beads Import / Apply (local/fake baseline)"
    phase_state: completed
    actionable: false
  - ssot_anchor: roadmap.phase11b.live_apply
    task_kind: implementation_task
    title: "Phase 11B — Beads live apply productization"
    phase_state: completed
    actionable: false
  - ssot_anchor: roadmap.phase11b.post_create_verify
    task_kind: implementation_task
    title: "Phase 11B — Beads apply post-create/readback verification"
    phase_state: completed
    actionable: false
  - ssot_anchor: roadmap.phase11b.update_path_validation
    task_kind: implementation_task
    title: "Phase 11B — Beads managed task update path validation"
    phase_state: completed
    actionable: false
  - ssot_anchor: roadmap.phase11b.provider_closeout
    task_kind: implementation_task
    title: "Phase 11B — provider-backed task apply closeout"
    phase_state: completed
    actionable: false
  - ssot_anchor: roadmap.phase12
    task_kind: implementation_phase
    title: "Phase 12 — Implementation Prompt Generator"
    phase_state: completed
    actionable: false
    completed_scope:
      - implementation prompt generator
      - three-layer spec alignment
      - local embedded task cache mode alignment
      - provider-backed closeout
      - bounded NotebookLM sync
      - task cache convergence
      - Phase 12 sample prompt validated
  - ssot_anchor: roadmap.component_runtime_core_baseline
    task_kind: implementation_task
    title: "Component Runtime Core Baseline Slice 1"
    phase_state: completed
    actionable: false
    completed_scope:
      - fixed component catalog (knowledge, task, sdd, tdd)
      - resolver for components.<component_id>.enabled only
      - config_ok
      - fail-closed unsupported_component_enabled
      - fail-closed required_component_disabled
      - fail-closed unknown_component_configured
      - product_ready requires config_ok=true
      - integration status exposes data.config_ok and data.components
      - TDD matrix from Contract + TDD Framework Freeze
    non_goals:
      - OpenSpec / Spec Kit / Superpowers integration
      - adoption detect
      - provider registry / plugin framework
      - Phase 13
      - NotebookLM / Beads mutation in this task
      - Slice 2+ (doctor/prompt awareness, template guidance, adoption detect, provider integration)
  - ssot_anchor: roadmap.component_runtime_doctor_prompt_awareness
    task_kind: implementation_task
    title: "Component Runtime Slice 2 — Doctor / implementation prompt awareness"
    phase_state: completed
    actionable: false
    completed_scope:
      - vibe doctor surfaces config_ok, components, component blocked_reasons
      - vibe implementation prompt includes component runtime readiness summary
      - "config_ok=false blocks implementation greenlight (no Implement: / equivalent)"
      - surface unsupported_component_enabled, required_component_disabled, unknown_component_configured
      - preserve Slice 1 product_ready / config_ok semantics
      - focused doctor/prompt awareness tests
    non_goals:
      - template/init-preview guidance (Slice 3)
      - adoption detect (Slice 4)
      - provider integration (Slice 5)
      - OpenSpec / Spec Kit / Superpowers
      - Phase 13
      - NotebookLM / Beads mutation as part of Slice 2 implementation
  - ssot_anchor: roadmap.component_runtime_template_init_preview_guidance
    task_kind: implementation_task
    title: "Component Runtime Slice 3 — Template / init-preview guidance"
    phase_state: completed
    actionable: false
    sequence_after: roadmap.component_runtime_doctor_prompt_awareness
    completed_scope:
      - template/init-preview guidance for valid components.<id>.enabled shape
      - safe examples for required supported + disabled optional not_supported_yet
      - invalid config examples diagnostic-only
      - no provider install/adapt/uninstall
      - focused template/init-preview guidance tests
    non_goals:
      - provider mutation
      - adoption detect
      - Phase 13
  - ssot_anchor: roadmap.component_runtime_readonly_adoption_detect
    task_kind: implementation_task
    title: "Component Runtime Slice 4 — readonly adoption detect"
    phase_state: completed
    actionable: false
    sequence_after: roadmap.component_runtime_template_init_preview_guidance
    completed_scope:
      - readonly detection/reporting for component-adjacent tools/surfaces
      - advisory/diagnostic only
      - no local config mutation, install, adopt, or readiness flip by detection alone
      - detected/not_detected/unavailable are diagnostic states only
      - detected candidate is not adopted and not provider-bound
      - focused readonly adoption detection tests
    non_goals:
      - unmanaged adoption
      - provider install/adapt/uninstall
      - Phase 13
  - ssot_anchor: roadmap.component_runtime_future_provider_integration
    task_kind: implementation_task
    title: "Component Runtime Slice 5 — future provider integration"
    phase_state: completed
    actionable: false
    sequence_after: roadmap.component_runtime_readonly_adoption_detect
    completed_scope:
      - minimal provider-boundary preparation
      - explicit fail-closed mutation boundaries
      - no live OpenSpec / Spec Kit / Superpowers / external provider integration
      - provider_hints are not active providers
      - detected candidates are not adopted/provider-bound
      - unsupported provider integration fails closed
    non_goals:
      - registry/plugin framework unless separately accepted
      - live provider mutation in baseline Slice 5 prep
      - Phase 13
  - ssot_anchor: roadmap.vibe_progress_brief_baseline
    task_kind: implementation_task
    title: "Vibe Product Interface Slice 1 — readonly Progress / Brief baseline"
    phase_state: completed
    actionable: false
    completed_scope:
      - vibe progress --json
      - vibe brief --json
      - optional vibe brief --format text
      - Progress projects existing Engine outputs only
      - Brief is short/action-oriented and not a replacement for full implementation prompt
      - Evidence v1 / S1 ephemeral operation snapshot fields (run_id, steps, generated_from, mutation_*=false, deterministic evidence_hash, not persisted)
      - observed_head is current HEAD, separate from recorded baseline commit
      - dirty local modification state fails closed
      - focused Progress / Brief tests
    non_goals:
      - provider mutation
      - task mutation
      - readiness recomputation
      - persistent ledger or workflow engine
      - changes to existing Knowledge or Task runtime semantics
      - sub-agent routing or handoff
      - Phase 13
  - ssot_anchor: roadmap.vibe_gateway_thin_router_contract
    task_kind: implementation_task
    title: "Vibe Product Interface Slice 2 — Gateway thin-router contract"
    phase_state: completed
    actionable: false
    sequence_after: roadmap.vibe_progress_brief_baseline
    completed_scope:
      - vibe gateway --intent ... --json thin intent router
      - routes status, what_next, get_prompt, why_blocked, summary, brief, prepare_closeout, verify_after_work
      - delegates to existing Engine surfaces only (progress, brief, implementation next/prompt, closeout dry-run)
      - source_of_truth=engine and facts_embedded=false
      - default mutation=false; refuses apply/raw-provider/raw-bd intents
      - preserves engine_payload evidence; outer ok mirrors engine_payload.ok
      - why_blocked pass-through of Engine blocked_reasons only
      - focused Gateway thin-router tests and vibe-control skill front-door routes
    non_goals:
      - storing current repo facts
      - computing readiness
      - provider or task mutation owned by Gateway
      - creating tasks or roadmap anchors
      - sub-agent routing
  - ssot_anchor: roadmap.vibe_describe_control_surface
    task_kind: implementation_task
    title: "Vibe Product Interface Slice 3 — Describe control surface"
    phase_state: completed
    actionable: false
    sequence_after: roadmap.vibe_gateway_thin_router_contract
    completed_scope:
      - vibe describe --json
      - readonly control-surface description
      - authority map / command surfaces / mutation classes
      - component catalog / non-goals
      - static/projection-only source policy
      - Engine Progress projection via projected.* / safe_next
      - source_of_truth=engine
      - facts_embedded=false
      - mutation=false
      - S1 projected ephemeral evidence
      - no product health/readiness computation
      - no provider mutation
      - focused Describe tests
    non_goals:
      - product health or readiness computation
      - provider mutation
      - provider registry or plugin framework
  - ssot_anchor: roadmap.vibe_evidence_hardening
    task_kind: implementation_task
    title: "Vibe Product Interface Slice 4 — Evidence hardening"
    phase_state: completed
    actionable: false
    sequence_after: roadmap.vibe_describe_control_surface
    optional: true
    completed_scope:
      - strengthened Vibe Evidence schema/report consistency
      - redaction hardening
      - bounded trajectory fields
      - S1 Ephemeral Operation Snapshot preserved
      - no persistent ledger
      - no workflow replay engine
      - focused evidence tests
    non_goals:
      - persistent ledger
      - workflow replay engine
  - ssot_anchor: roadmap.vibe_operation_recovery_design
    task_kind: implementation_task
    title: "Vibe Product Interface Slice 5 — operation recovery design"
    phase_state: completed
    actionable: false
    sequence_after: roadmap.vibe_capability_profile_doctor_gateway_guidance
    design_only: true
    completed_scope:
      - design evaluation completed
      - no S2 implementation
      - S1 remains sufficient for current observable recovery needs
      - future S2 requires separate owner acceptance
      - design_only prompt/projection hygiene
      - disabled-capability raw warning hygiene
      - design note docs/project/sync/vibe-operation-recovery-design.md
    non_goals:
      - S2 implementation in the current track
      - S3 workflow engine
      - operation replay engine
      - Phase 13
  - ssot_anchor: roadmap.vibe_product_concept_boundary_contract
    task_kind: implementation_task
    title: "Vibe Concept Boundary + Capability Profile — Slice 1 SSOT contract"
    phase_state: completed
    actionable: false
    optional: true
    completed_scope:
      - product concept boundary explicit and test-covered
      - Engine + Gateway + Knowledge + Task + Capability Profile product surface
      - Gateway/Skills thin routers to Engine
      - not an SSOT manager / roadmap manager / workflow engine
      - roadmap-state / roadmap.* documented as dogfood/source-task patterns
      - managed_key / SSOT identity remain stable task identity
      - target Capability Profile contract (all disabled by default)
      - Engine readiness separate from capability readiness
      - knowledge/task enablable; disabled do not fail product readiness
      - sdd/tdd not implemented; fail closed if enabled
      - runtime explicitly unchanged until capability profile runtime slice
      - TDD/contract tests for concept boundary + target profile
      - Project Sources not product gate
    non_goals:
      - capability profile runtime flip
      - workflow engine
      - roadmap manager / SSOT manager product framing
      - operation recovery implementation
      - Phase 13
  - ssot_anchor: roadmap.vibe_capability_profile_runtime
    task_kind: implementation_task
    title: "Vibe Concept Boundary + Capability Profile — Slice 2 runtime profile"
    phase_state: completed
    actionable: false
    sequence_after: roadmap.vibe_product_concept_boundary_contract
    optional: true
    completed_scope:
      - runtime default-disabled capability profile
      - knowledge/task available but disabled by default
      - disabled capabilities do not fail product readiness
      - enabled knowledge checks NotebookLM readiness/sync/ask hygiene
      - enabled task checks Beads/provider/cache readiness
      - sdd/tdd enabled fail closed as not implemented/unsupported
      - unknown/provider-scoped component ids fail closed
      - Engine readiness separate from capability readiness
      - projections do not implement second readiness engine
      - focused capability profile runtime tests
    non_goals:
      - OpenSpec / Spec Kit / Superpowers live integration
      - workflow engine
      - Phase 13
  - ssot_anchor: roadmap.vibe_capability_profile_install_init_guidance
    task_kind: implementation_task
    title: "Vibe Concept Boundary + Capability Profile — Slice 3 install/init guidance"
    phase_state: completed
    actionable: false
    sequence_after: roadmap.vibe_capability_profile_runtime
    optional: true
    completed_scope:
      - fresh/default disabled profile guidance
      - knowledge/task available + enable/config guidance
      - sdd/tdd not_implemented guidance
      - invalid examples diagnostic-only
      - no provider mutation / no install/adapt/uninstall
      - focused install/init/profile guidance tests
    non_goals:
      - silent auto-enable of knowledge/task
      - provider mutation from init guidance
      - Phase 13
  - ssot_anchor: roadmap.vibe_capability_profile_doctor_gateway_guidance
    task_kind: implementation_task
    title: "Vibe Concept Boundary + Capability Profile — Slice 4 doctor/gateway guidance"
    phase_state: completed
    actionable: false
    sequence_after: roadmap.vibe_capability_profile_install_init_guidance
    optional: true
    completed_scope:
      - doctor/gateway/describe surfaces explain Engine vs capability readiness
      - next_actions for enable prerequisites without becoming SSOT/roadmap managers
      - redaction and mutation=false preserved on readonly paths
      - progress/brief expose concise capability guidance
      - gateway thin-routes Engine capability_guidance without recomputation
      - focused doctor/gateway/describe/progress/brief guidance tests
    non_goals:
      - Gateway owning readiness recomputation
      - roadmap-manager UX
      - Phase 13
```

## Notes

- Completed anchors are never default next actionable tasks.
- When `next_actionable_task` is null, agents must report `no_actionable_next_task=true`.
- Do not invent Phase 13 or other anchors here without an accepted repo decision.
- `roadmap.component_runtime_core_baseline` remains completed for Slice 1 only
  (implementation `8c15d2d`, closeout `d64922e`). Do not restart it.
- `roadmap.component_runtime_doctor_prompt_awareness` is completed for Slice 2 only
  (implementation `7fa1f7a`). Do not restart it.
- `roadmap.component_runtime_template_init_preview_guidance` is completed for Slice 3 only
  (implementation `618f2b7`). Do not restart it.
- `roadmap.component_runtime_readonly_adoption_detect` is completed for Slice 4 only
  (implementation `5f3f955`). Do not restart it.
- `roadmap.component_runtime_future_provider_integration` is completed for Slice 5 only
  (implementation `a1144ba`). Do not restart it.
- Component Runtime continuation track (owner-accepted): Slice 2–5 are distinct anchors
  and are all completed. They remain completed/actionable=false and must not be restarted.
- `roadmap.vibe_progress_brief_baseline` is completed for Progress / Brief baseline only
  (implementation `24b511d`). Do not restart it.
- `roadmap.vibe_gateway_thin_router_contract` is completed for Gateway thin-router only
  (implementation `2e9ef5d`, review harden `4293359`). Do not restart it.
- `roadmap.vibe_describe_control_surface` is completed for Describe control surface only
  (implementation `ac0cf5e`). Do not restart it.
- `roadmap.vibe_evidence_hardening` is completed for Evidence hardening only
  (implementation `8786048`). Do not restart it.
- Vibe Product Interface & State Contract Track design slice
  `roadmap.vibe_operation_recovery_design` is completed (design evaluation only;
  verdict: no S2 implementation now; S1 remains sufficient). Do not restart it
  and do not implement S2/S3/replay from this closeout.
- Vibe Product Concept Boundary + Capability Profile Track is owner-accepted and
  complete for runtime + install/init + doctor/gateway guidance slices.
  `roadmap.vibe_product_concept_boundary_contract` is completed (SSOT/tests only).
  `roadmap.vibe_capability_profile_runtime` is completed (implementation `b9298c0`).
  `roadmap.vibe_capability_profile_install_init_guidance` is completed
  (implementation `6c46b62`).
  `roadmap.vibe_capability_profile_doctor_gateway_guidance` is completed
  (implementation `27d7ef7`).
  `roadmap.vibe_operation_recovery_design` is completed (design note + hygiene;
  implementation/design commit `6f5326d`). Current state:
  `next_actionable_task=null` / `no_actionable_next_task=true`. Do not invent
  Phase 13.
- This track is not Phase 13 and does not turn Vibe into an SSOT/roadmap/workflow
  product. `roadmap.*` remains dogfood/source-task pattern only.
- Representation for queued accepted work: `phase_state=accepted` + `actionable=false`
  means sequenced/queued — **not** completed. Soft debt: some CLI summaries still label
  non-actionable anchors under `completed_anchors` / `skip_completed`; do not treat that
  label as true completion while still queued.
- TDD-first design for Concept/Capability Profile track:
  `docs/project/sync/vibe-product-concept-capability-profile-tdd-plan.md` (harness detail; not
  default knowledge inventory / Project Sources).
- TDD-first design for historical Component Runtime Slice 2–5:
  `docs/project/sync/component-runtime-continuation-tdd-plan.md` (harness detail; not
  default knowledge inventory / Project Sources).
- `DECISION_LOG.md` remains decision history only; it does not carry current actionable state.
