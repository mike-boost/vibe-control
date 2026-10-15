# Decision Log

- 2026-07-22: Accepted **Skill Assay (`skill-assay`)** — Engine tool surface
  `vibe skill-assay` measures any local skill across hosts (default 3 fresh
  sessions). Separate from `vibe skills` install. Local receipts under
  `runtime/vibe-skill-assay/`. Not a component / not `product_ready`. Two-stage
  report: CLI evidence → agent analysis → `finalize`. Agent self-explain via
  `communication_contracts.skill_assay` + Gateway
  `skill_assay_brief` (owner utterance: “用 skill-assay 分析 xxx”).
  Cursor/Copilot live adapters remain `unverified` until explicit
  `real_skill_host` smoke. Spec: `docs/project/sync/20260722-skill-assay-spec.md`.
- 2026-07-22: Released **0.5.13** — per-provider Knowledge format policy + owner plain-language contract.
- 2026-07-22: **Knowledge format policy per provider.** `local_fts` indexes
  `.md`/`.markdown`/`.txt` only; `notebooklm` (Gemini Notebook) uses the Google
  upload allowlist. Unsupported paths skipped on sync/index with clear warnings.
  Code: `format_policy.py`. Plan:
  `docs/project/plans/20260722-knowledge-provider-format-policy-plan.md`.
- 2026-07-22: **Harness — owner plain-language contract.** Agents must talk to the
  owner without unexplained jargon (ban opaque “managed” nicknames in owner chat).
  Projected via `communication_contracts.owner_plain_language`; doc
  `docs/harness/owner-plain-language-contract.md`. Also locked: Knowledge format
  limits follow the **active provider** (`local_fts` vs `notebooklm`/Gemini Notebook).
- 2026-07-21: Released **0.5.12** — Knowledge `local_fts` (SQLite FTS5) +
  `fts-purge` + `communication_contracts.git_land` harness projection.
- 2026-07-21: **Harness fix — git_land communication contract.** AGENTS already
  forbade asking owner to commit, but describe/skills/closeout dirty next_actions
  did not project it (agents stalled on `COMMIT_OR_CLEAN_LOCAL_STATE`). Added
  `communication_contracts.git_land`, shared dirty reason, Brief approval line,
  skills one-liner, phase/ssot harness ownership notes.
- 2026-07-21: Accepted Knowledge **`local_fts`** provider (SQLite FTS5 retrieval with
  Read-aligned line ranges; trigram + LIKE for CJK). Owner-explicit
  `knowledge.provider` selection (no auto-switch). `local_fts` OR `notebooklm` can
  satisfy knowledge half of `product_ready`; Beads remains task half. Spec:
  `docs/project/sync/20260721-knowledge-local-fts-provider-spec.md`.
- 2026-07-21: Released **0.5.11** — multi-notebook corpus + self-grill session
  loop; GitHub Release notes policy (extract per-version; backfilled 0.5.0–0.5.10).
- 2026-07-21: **Self-grill session loop** (minimal closed loop) — local
  `runtime/vibe-grill/` receipts (`grill_id` + `round_id` from 0);
  `grill_brief` opens/resumes; Progress/Brief pull-back while `IN_PROGRESS`;
  `implementation prompt` fail-closed (`SELF_GRILL_IN_PROGRESS`);
  thin CLI `vibe grill status|checkpoint|close`. Not SSOT / not closeout gate.
  Design: `docs/project/sync/20260721-self-grill-session-loop-design.md`.
- 2026-07-21: **Amended** self-grill mount — Engine surfaces only
  (`describe.communication_contracts.self_grill`, Gateway `grill_brief` → Brief
  + contract). Removed installable `vibe-self-grill` skill (anti skill-sprawl).
  Contract:
  `docs/project/sync/20260721-agent-self-grill-comm-contract.md`.
- 2026-07-21: Accepted **Option A agent self-grill** as communication contract
  (interrogates agent claims; Knowledge probe-only; not Knowledge mode;
  not HSP-as-capability). Later same-day amendment: Engine mount, not skill.
- 2026-07-20: Accepted **target-scoped Knowledge corpus** (multi-notebook selectors) —
  narrow exception to 2026-07-17 “no new Knowledge flagship”. Design:
  `docs/project/sync/20260720-knowledge-multi-notebook-corpus-design.md`.
  Locked: agent-decided taxonomy; no cross-notebook ask; `--notebook` required when
  allow_list length ≥ 2; `path_prefixes` in v1; non-default `sync --apply` strict
  (`--confirm-non-default-sync`); `corpus_mode: replace` = selector rules (ignore
  global corpus), not filesystem replace. **D1–D4 implemented** same day
  (`resolve_desired_corpus`, confirm gate, describe/skill guidance).
- 2026-07-19: Released **0.5.10** — Ask Template v3 (Sources), citation→path
  enrichment, `CHECK_CORPUS_INVENTORY`; AGENTS: do not ask owner for git land permission.
- 2026-07-19: Knowledge ask polish — bumped Ask Template to `vibe.knowledge.ask.v3`
  (required **Sources** section); provider citations enrich via receipt to
  `doc_id`/`path` when bound; Evidence insufficient / repo no-hit →
  `CHECK_CORPUS_INVENTORY`. No corpus-preview / selection-engine product surface.
- 2026-07-19: Drafted formal **Hetu** design spec v0.1
  (`docs/project/vibe-control-hetu-spec.md`); linked from Front/Core companion map
  + product thinking index. Runtime/CLI/Capability Profile wiring still not shipped;
  Hetu must not gate `product_ready` until accepted runtime.
- 2026-07-19: Accepted **Hetu** as third peer capability (with Knowledge / Task) —
  code-structure understanding control plane; CLI-first; git freshness/impact
  fusion; adopt existing graph installs without wipe; default provider direction
  codebase-memory-mcp; codegraph swappable; no dual-active default; MVP = readonly
  + gated reindex (A+B); brief/prompt compose (C) deferred; not a workflow engine
  and not a second docs-ask. Decision note:
  `docs/project/sync/20260719-hetu-capability-decision.md`. Does not reopen K/T
  flagship features from 2026-07-17 polish strategy.
- 2026-07-18: Released **0.5.9** — knowledge multi-file sync uses notebooklm-py
  API concurrent single-file uploads (`--ingest-path auto|api|cli`,
  `--upload-concurrency` default **8** = in-flight cap, not bulk RPC) +
  `scale.stage_ms`. SE measure: CLI ~94s/N10 → API ~27s; conc 8≈12. Strategy:
  `docs/project/sync/20260718-knowledge-sync-throughput-strategy.md`.
- 2026-07-17: Shipped thin `vibe feedback` CLI (init-preview / draft / validate /
  pack) for experience-signal artifacts under `runtime/vibe-feedback/`;
  redaction.confirmed required; no upload; gitignore path; tests locked.
  Spec acceptance marked shipped in `vibe-control-feedback-spec.md`.
- 2026-07-17: Accepted Feedback companion SSOT — experience-signal capture
  (pain / owner dissatisfaction / bright spot / friction / bug_signal), OS
  crash-reporter analogy; artifacts in consumer `runtime/vibe-feedback/`
  (one/many/zip); mandatory redaction; voluntary share to Vibe team; **not**
  a task system and not knowledge SSOT. Spec:
  `docs/project/vibe-control-feedback-spec.md`. Updated
  `docs/feedback.md` + front spec companion list. (Thin CLI shipped same day.)
- 2026-07-17: Persisted product-thinking tables in-repo (index + expanded
  scenario research + task consumer path A doc) so chat/Canvas content is not
  lost; Canvas title「Vibe — 自解释 + 高频场景」is a view only. Files:
  `docs/project/PRODUCT_THINKING_INDEX.md`, `agent-scenario-research.md`,
  `docs/task-consumer-path.md`.
- 2026-07-17: Knowledge/Task polish strategy accepted — no new Knowledge/Task
  flagship features now; scenario research retained as reference only (do not
  hardcode owner business scenarios); Ask multi-profile / FAQ cache / vibe search
  / Vibe task-graph scheduler deferred; near-term debt = install↔skills↔doctor
  alignment (`scripts/install-user.sh` skills --apply --force; doctor surfaces
  missing/mismatch next_actions). Decision note:
  `docs/project/sync/20260717-knowledge-task-polish-strategy.md`.
- 2026-07-17: Knowledge Ask SSOT polish — upgraded Ask Prompt Policy to
  `vibe.knowledge.ask.v2` (Facts/Constraints/MUST/Uncertainty); wired NotebookLM
  `configure --persona` + `--response-length shorter` before each provider ask
  (NotebookLM has no classical system role; persona is the closest equivalent);
  kept `ask --new` for fresh conversation; added
  `docs/harness/knowledge-ask-ssot-contract.md` (scenarios, question shapes,
  answer requirements). No provider source mutation in this polish.
- 2026-07-17: Vibe operation recovery design closeout — marked
  `roadmap.vibe_operation_recovery_design` completed/actionable=false with
  `completed_scope` (design evaluation completed; no S2 implementation; S1 remains
  sufficient for current observable recovery needs; future S2 requires separate
  owner acceptance; design_only prompt/projection hygiene; disabled-capability raw
  warning hygiene; design note `docs/project/sync/vibe-operation-recovery-design.md`;
  design/hygiene commit `6f5326d`). Set `next_actionable_task=null` /
  `no_actionable_next_task=true`. No S2 ledger/checkpoint/runtime; no S3 workflow
  engine; no replay; no Phase 13; no new anchors.
- 2026-07-17: Vibe capability profile doctor/gateway guidance closeout — marked
  `roadmap.vibe_capability_profile_doctor_gateway_guidance` completed/actionable=false
  with `completed_scope` (doctor/gateway/describe surfaces explain Engine vs
  capability readiness; next_actions for enable prerequisites without becoming
  SSOT/roadmap managers; redaction and mutation=false preserved on readonly paths;
  progress/brief expose concise capability guidance; gateway thin-routes Engine
  capability_guidance without recomputation; focused doctor/gateway/describe/
  progress/brief guidance tests; implementation `27d7ef7`). Promoted
  `roadmap.vibe_operation_recovery_design` as current `next_actionable_task`
  (accepted/design_only/actionable=true). No operation recovery implementation in
  this closeout; no Phase 13; no new anchors; no OpenSpec/Spec Kit/Superpowers.
- 2026-07-17: Vibe capability profile install/init guidance closeout — marked
  `roadmap.vibe_capability_profile_install_init_guidance` completed/actionable=false
  with `completed_scope` (fresh/default disabled profile guidance; knowledge/task
  available + enable/config guidance; sdd/tdd not_implemented guidance; invalid
  examples diagnostic-only; no provider mutation / no install/adapt/uninstall;
  focused install/init/profile guidance tests; implementation `6c46b62`). Promoted
  `roadmap.vibe_capability_profile_doctor_gateway_guidance` as current
  `next_actionable_task`. `roadmap.vibe_operation_recovery_design` remains
  accepted/design_only/non-current. No doctor/gateway guidance implementation in
  this closeout; no Phase 13; no new anchors; no OpenSpec/Spec Kit/Superpowers.
- 2026-07-17: Vibe capability profile runtime closeout — marked
  `roadmap.vibe_capability_profile_runtime` completed/actionable=false with
  `completed_scope` (runtime default-disabled capability profile; knowledge/task
  available but disabled by default; disabled capabilities do not fail product
  readiness; enabled knowledge checks NotebookLM readiness/sync/ask hygiene;
  enabled task checks Beads/provider/cache readiness; sdd/tdd enabled fail closed
  as not implemented/unsupported; unknown/provider-scoped component ids fail
  closed; Engine readiness separate from capability readiness; projections do not
  implement second readiness engine; focused capability profile runtime tests;
  implementation `b9298c0`). Promoted
  `roadmap.vibe_capability_profile_install_init_guidance` as current
  `next_actionable_task`. Queued:
  `roadmap.vibe_capability_profile_doctor_gateway_guidance`.
  `roadmap.vibe_operation_recovery_design` remains accepted/design_only/non-current.
  No install/init guidance implementation in this closeout; no Phase 13; no new
  anchors; no runtime behavior changes in this closeout.
- 2026-07-17: Vibe product concept boundary contract closeout — marked
  `roadmap.vibe_product_concept_boundary_contract` completed/actionable=false with
  `completed_scope` (product surface Engine+Gateway+Knowledge+Task+Capability Profile;
  Gateway/Skills thin routers; not SSOT/roadmap/workflow product; roadmap.* dogfood
  pattern; managed_key identity; target Capability Profile all-disabled; Engine vs
  capability readiness; runtime unchanged until runtime slice; TDD/contract tests;
  Project Sources not product gate). Promoted
  `roadmap.vibe_capability_profile_runtime` as current `next_actionable_task`.
  No runtime capability default flip in this closeout; no Phase 13; no operation
  recovery implementation.
- 2026-07-17: Vibe Product Concept Boundary + Capability Profile Track accepted —
  product surface is Engine + Gateway + Knowledge + Task + Capability Profile.
  Vibe is not an SSOT manager, roadmap manager, or workflow engine. Repo SSOT /
  roadmap-state / roadmap.* are dogfood/source-task patterns only; stable task
  identity remains managed_key / SSOT identity. Target Capability Profile:
  fresh/default all capabilities disabled; knowledge/task supported/enablable with
  provider checks when enabled; disabled capabilities do not fail product readiness;
  sdd/tdd not implemented and fail closed if enabled. Engine readiness remains
  separate from capability readiness. Activation is SSOT + TDD only (no runtime
  readiness flip). Current `next_actionable_task=
  roadmap.vibe_product_concept_boundary_contract`. Queued:
  `roadmap.vibe_capability_profile_runtime`,
  `roadmap.vibe_capability_profile_install_init_guidance`,
  `roadmap.vibe_capability_profile_doctor_gateway_guidance`.
  `roadmap.vibe_operation_recovery_design` remains accepted/design_only but
  non-current until after this track. TDD plan:
  `docs/project/sync/vibe-product-concept-capability-profile-tdd-plan.md`.
  No Phase 13; no operation recovery implementation in activation.
- 2026-07-16: Vibe Evidence hardening closeout — marked
  `roadmap.vibe_evidence_hardening` completed/actionable=false with accepted
  `completed_scope` (strengthened Vibe Evidence schema/report consistency; redaction
  hardening; bounded trajectory fields; S1 Ephemeral Operation Snapshot preserved;
  no persistent ledger; no workflow replay engine; focused evidence tests;
  implementation `8786048`). Promoted `roadmap.vibe_operation_recovery_design` as
  current `next_actionable_task` (design_only/actionable=true). No operation recovery
  implementation in this closeout; no Phase 13; no new anchors.
- 2026-07-16: Vibe Describe control surface closeout — marked
  `roadmap.vibe_describe_control_surface` completed/actionable=false with accepted
  `completed_scope` (`vibe describe --json`; authority/surfaces/mutation classes;
  component catalog/non-goals; static/projection-only; Engine Progress projection;
  `source_of_truth=engine`; `facts_embedded=false`; `mutation=false`; S1 projected
  evidence; implementation `ac0cf5e`). Promoted
  `roadmap.vibe_evidence_hardening` as current `next_actionable_task`. No Evidence
  hardening implementation in this closeout; no Phase 13; no new anchors.
- 2026-07-16: Vibe Gateway thin-router closeout — marked
  `roadmap.vibe_gateway_thin_router_contract` completed/actionable=false with accepted
  `completed_scope` (`vibe gateway --intent ... --json` thin router; Engine delegation only;
  `source_of_truth=engine`; default `mutation=false`; refuse apply/raw-provider; preserve
  `engine_payload`; outer ok mirrors Engine; implementation `2e9ef5d`, review harden
  `4293359`). Promoted `roadmap.vibe_describe_control_surface` as current
  `next_actionable_task`. No Describe implementation in this closeout; no Phase 13;
  no new anchors.
- 2026-07-16: Vibe Progress / Brief baseline closeout — marked
  `roadmap.vibe_progress_brief_baseline` completed/actionable=false with accepted
  `completed_scope` (`vibe progress --json`, `vibe brief --json`, optional text format,
  Engine projection only, Evidence v1/S1 ephemeral snapshot, observed_head vs baseline,
  dirty fail-closed; implementation commit `24b511d`). Promoted
  `roadmap.vibe_gateway_thin_router_contract` as current
  `next_actionable_task`. No Gateway implementation in this closeout; no Phase 13;
  no new anchors.
- 2026-07-16: Vibe Product Interface & State Contract Track accepted — primary user is
  the main coding agent; `Vibe Control Engine`, `Vibe Gateway`, `Vibe Progress`,
  `Vibe Describe`, `Vibe Brief`, and `Vibe Evidence` are accepted SSOT terms.
  `S1 Ephemeral Operation Snapshot` is the minimal state-control strategy;
  S2 lightweight ledger is deferred and S3 workflow engine is rejected for current scope.
  No platform-specific product dependency and no sub-agent support. Current
  `next_actionable_task=roadmap.vibe_progress_brief_baseline`; no Phase 13 and no
  Component Runtime slice restart. This activation changes specs/roadmap only, not existing
  Knowledge or Task runtime semantics.
- 2026-07-16: Component Runtime Slice 5 closeout — marked
  `roadmap.component_runtime_future_provider_integration` completed/actionable=false
  with Slice-5 `completed_scope` (provider-boundary preparation; fail-closed
  mutation boundaries; no live OpenSpec / Spec Kit / Superpowers integration;
  implementation commit `a1144ba`). Set `next_actionable_task=null` /
  `no_actionable_next_task=true`. No Phase 13; no new anchors.
- 2026-07-16: Component Runtime Slice 4 closeout — marked
  `roadmap.component_runtime_readonly_adoption_detect` completed/actionable=false
  with Slice-4 `completed_scope` (readonly adoption detection/reporting;
  advisory/diagnostic only; implementation commit `5f3f955`). Promoted Slice 5
  (`roadmap.component_runtime_future_provider_integration`) to current
  `next_actionable_task` / actionable. No Slice 5 implementation in this
  closeout; no Phase 13.
- 2026-07-16: Component Runtime Slice 3 closeout — marked
  `roadmap.component_runtime_template_init_preview_guidance` completed/actionable=false
  with Slice-3 `completed_scope` (template/init-preview guidance; diagnostic-only
  invalid examples; implementation commit `618f2b7`). Promoted Slice 4
  (`roadmap.component_runtime_readonly_adoption_detect`) to current
  `next_actionable_task` / actionable. Slice 5 remains accepted queued
  (`actionable=false`). No Slice 4 implementation in this closeout; no Phase 13.
- 2026-07-16: Component Runtime Slice 2 closeout — marked
  `roadmap.component_runtime_doctor_prompt_awareness` completed/actionable=false
  with Slice-2 `completed_scope` (doctor + implementation prompt awareness;
  implementation commit `7fa1f7a`). Promoted Slice 3
  (`roadmap.component_runtime_template_init_preview_guidance`) to current
  `next_actionable_task` / actionable. Slice 4–5 remain accepted queued
  (`actionable=false`). No Slice 3 implementation in this closeout; no Phase 13.
- 2026-07-16: Component Runtime continuation track accepted — promote Front/Core
  landing-order Slice 2–5 into distinct roadmap-state anchors (not a broad epic;
  not Phase 13; do not reuse `roadmap.component_runtime_core_baseline`). Slice 2
  (`roadmap.component_runtime_doctor_prompt_awareness`) is current
  `next_actionable_task` / actionable. Slice 3–5 are `phase_state=accepted` +
  `actionable=false` (queued sequence; promote one-at-a-time after prior closeout).
  TDD-first plan: `docs/project/sync/component-runtime-continuation-tdd-plan.md`
  (harness detail; not default inventory). This decision activates SSOT only —
  no Slice 2–5 implementation in the activation commit.
- 2026-07-16: Component Runtime Core Baseline Slice 1 closeout — marked
  `roadmap.component_runtime_core_baseline` completed/actionable=false with Slice-1
  `completed_scope` (catalog resolver + config_ok + product_ready gate + integration
  status fields; commit `8c15d2d`). `next_actionable_task=null` /
  `no_actionable_next_task=true`. Later Slice 2–5 remain Front/Core landing order only;
  no new slice anchors; no Phase 13.
- 2026-07-15: Local ephemeral task cache reset — `vibe task cache reset --dry-run|--apply --json --provider beads` clears Vibe-managed Beads namespace then regenerates from actionable roadmap-state projection. Only `local_embedded_ephemeral`. No per-conflict repair; no team/shared mode. Explicit `--apply` is the mutation gate (no raw agent `bd`).
- 2026-07-15: Roadmap State SSOT — added `docs/project/vibe-control-roadmap-state.md` as active high-churn status SSOT (`phase_state` / `actionable` / `next_actionable_task`). Projection + `vibe implementation next` read from it. Phase 11a/11b/12 marked completed/actionable=false; no default next task. `DECISION_LOG.md` demoted from default `include_extra` (history only). Default Project Sources / inventory: Front/Core + Knowledge + Task + roadmap-state. Explicit Phase 12 prompt may return completed warning. No NLM sync --apply; no live Beads; no push.
- 2026-07-15: Default task mode = `local_embedded_ephemeral` — Beads is agent-local stage-scoped task cache (not repo/GitHub/team truth). Stale/missing converge via managed create/update; unmanaged/duplicate/conflict prefer whole-cache reset/regenerate. `product_ready` requires `task_cache_current`. Closeout cannot pass with stale cache as soft debt. Safe convergence allowed when knowledge ready without full product_ready circular dependency. Team/shared/server mode out of scope. CLI: `vibe task cache reset --dry-run|--apply`. No NLM/Beads live mutation in this alignment; no push.
- 2026-07-15: Phase 12 Closeout Pressure Gate — hardened three-layer specs (ChatGPT Project Sources ≠ NotebookLM sync source; ask hygiene separate from sync_state; acceptance-only title deletes; `bd prime` as non-default context helper). Removed superseded `OLD_VIBE_CONTROL_DRAFT.md` and registry entry. Sync dry-run/apply envelopes set explicit `mutation` false/true. No push.
- 2026-07-15: Phase 12 Design Alignment Gate — split formal specs into Front/Core (`vibe-control-spec.md`), Knowledge (`vibe-control-knowledge-spec.md`), Task (`vibe-control-task-spec.md`). Registry activates all three. Added SSOT closeout transaction states + Phase 12 front contract. `docs/project/sync/*.md` remain phase/dev detail, not default Project Sources. Expected knowledge inventory grows to 3 active specs + DECISION_LOG; `provider_sync_required` until owner-approved bounded sync. No NLM/Beads mutation; no push.
- 2026-07-15: Phase 12 Implementation Prompt Generator — `vibe implementation prompt --task <managed_key|provider_task_id|ssot_anchor> --json` builds a readonly copy-paste coding-agent prompt from SSOT identity, readiness, reconcile/apply counts, and selected managed task (provider ids hashed). Spec: `docs/project/sync/phase12-implementation-prompt-generator-spec.md`. No NLM/Beads mutation.
- 2026-07-15: Option A autonomous managed Beads apply — live Vibe-managed create/update requires `product_ready` + safe managed plan + `--autonomous-managed` + temporary dual gate (`VIBE_BEADS_LIVE_APPLY=1` AND `--confirm-beads-live-apply`). No per-op user questions for safe managed ops. Unsafe → skip/block/repair-plan + next_actions. Default gates never live-mutate. Option B delta: remove dual gate after stronger tests. Spec/AGENTS updated. **Live Beads executed in this change:** created 5 managed tasks (`vibe-control-8e9/sgv/jqh/7i2/sxm`) for actionable anchors; post-reconcile `missing=0`.
- 2026-07-15: Product-alignment pass — encode agent-facing + provider-backed model and Approval Matrix in vibe-control-spec / AGENTS / harness. Intended policy: Vibe-managed create/update autonomous when product_ready + current plan binding + safe managed ops only; unsafe cases → skip/block/repair-plan + next_actions (no ad hoc user Q&A). Live Beads dual gate kept as **temporary** harness safety layer (product path still does not execute live bd). Keep status-aware projection (completed 11A / 11B shell not open create). ChatGPT Project Sources: owner uploads manually.
- 2026-07-15: Status-aware expected-task projection — completed/baseline phases (`roadmap.phase11a`, shell `roadmap.phase11b`) are never default open `create_managed`; reported as `skip_completed` + `optional_backfill_completed`. Remaining Phase 11B work projected as concrete actionable anchors (`live_apply`, `post_create_verify`, `update_path_validation`, `provider_closeout`); Phase 12 pending remains actionable. Apply plans expose `plan_by_op_type`. Spec: phase11b + vibe-control-spec roadmap notes. No live Beads / NotebookLM mutation.
- 2026-07-15: Provider readiness + Beads integration hardening — `product_ready` on `vibe integration status`; probe policy (important nodes / failure branches / reuse ProviderProbeResult); Beads readonly allows list/show/ready/status (no --claim); create/update argv use `--metadata` + `--spec-id`; live apply dual-gated (env AND `--confirm-beads-live-apply`); strict beads apply requires knowledge synced+ask-clean; apply plans bind `plan_binding_hash`. Specs: Phase 8.1 harness + phase11b update. No live bd mutation; no sync --apply.
- 2026-07-15: Phase 11B Beads Import / Apply — `vibe task apply --dry-run|--apply --json`; ApplyPlan from Phase 11A ReconcileReport; FakeTaskProvider create/update for local mutation; Beads argv builders + `VIBE_BEADS_LIVE_APPLY` guard (no live `bd create/update/delete` in default gates); acceptance/phase11b wired into readonly acceptance. Spec: `docs/project/sync/phase11b-beads-import-apply-spec.md`.
- 2026-07-14: Harden knowledge cleanup sync harness — after owner UI orphan delete, bounded `sync --apply` restored current SSOT (`vibe_control_spec` + `DECISION_LOG`) to synced with `candidate_count=0`. Added `ask_hygiene` / preflight helpers + tests so provider_ask_clean requires synced + zero required updates + zero cleanup candidates; sync --apply refuses non-SSOT-bounded ops; durable rules in `docs/harness/knowledge-ask-hygiene-contract.md`.
- 2026-07-14: Knowledge cleanup owner action — leftover old non-current provider sources (e.g. `vibe_control_v0_5_spec`) are ask pollution for provider-backed query, not a harmless long-term warning. Owner must DELETE MANUALLY in NotebookLM UI after confirming non-SSOT; CLI still never auto-deletes orphans. Docs clarified accordingly.
- 2026-07-14: Knowledge cleanup candidate listing — prefer `vibe knowledge cleanup-candidates --json` (explicit readonly command; avoids `cleanup --dry-run` sounding like mutation). Reuses Phase 8 planner classification; lists `orphan_managed` / `cleanup_pending` / duplicate extras / unmanaged for owner UI cleanup guidance; never deletes; no broad notebook clean; auto-delete remains out of scope except receipt-owned explicit apply. Legacy `vibe_control_v0_5_spec` may appear as manual cleanup candidate.
- 2026-07-14: Knowledge dogfood consistency — `vibe knowledge sync --dry-run` now uses Phase 8 scoped receipt + same desired_snapshot as status; when status is synced, required updates for current SSOT (`vibe_control_spec`, `DECISION_LOG`) must be empty; `orphan_managed(vibe_control_v0_5_spec)` remains report_only_no_delete. Spec wording cleaned for Phase 11A complete / 11B not started.
- 2026-07-14: Dogfood knowledge sync for current SSOT — `vibe knowledge sync --apply` / `retry --apply` against default OPM-test target brought Phase 8 scoped receipt + ack to `sync_state=synced` for `vibe_control_spec` + `DECISION_LOG`. Fixed Phase 8 upload identity to use hashed `upload_filename` temp files (so provider titles match probe). Wired readonly `notebooklm ask` into `vibe knowledge query` when synced. Legacy `vibe_control_v0_5_spec` remote source remains as report-only orphan (not deleted). No Beads mutation; no ChatGPT Project Sources update; no push.
- 2026-07-14: Phase 11A closeout audit — fixed Phase 4 inventory acceptance (expect `docs/project/vibe-control-spec.md` after V0_5 removal); softened Phase 6 readonly acceptance so env-coupled `already_current==2` / legacy V0_5 remote title equality are not hard blockers (dry-run ok + no mutation still required); added Knowledge Ask Template (`vibe.knowledge.ask.v1` / `default_ssot_facts`) for `vibe knowledge query`; hardened Phase 11A tests/acceptance (fixture unavailable/empty; no real Beads/NotebookLM). Status: complete for readonly/default safe scope. Phase 11B not started.
- 2026-07-14: Phase 11A closeout — provider unavailable reports `mode=unavailable` / `provider_available=false` and does not invent `missing` as a real Beads empty-state diff; empty available provider may report real missing; Phase 11A readonly acceptance wired into `scripts/test-acceptance-readonly.sh`. Status: complete for readonly/default safe scope. Phase 11B not started.
- 2026-07-14: Phase 11A Slice 2 — BeadsReadonlyProvider (`bd list`/`bd show` only), `vibe task reconcile --dry-run --json --provider fake|beads`, package `vibe-control` front-door skill, Superpowers comparison note (adopt front-door + confirmed mandatory workflow; reject worktrees/subagents/skill sprawl). No Beads/NotebookLM mutation.
- 2026-07-14: Phase 11A Slice 1 — landed expected-task projection (roadmap.phase11a/11b), managed_key, vibe.task.v1 marker parse, FakeTaskProvider, readonly reconcile categories, and `vibe task reconcile --dry-run --json`. No Beads/NotebookLM mutation. Real bd list/show deferred.
- 2026-07-14: Phase 11 prep — accepted dogfood path (skills → knowledge readonly → SSOT facts → agent reasoning → task reconcile --dry-run); recommended `vibe-control` front-door skill; TaskProvider abstractions with fake provider tests first; expected-task identity = project_id/ssot_id/ssot_path/ssot_anchor/task_kind → managed_key; marker prefers body/description footer (`vibe.task.v1`); readonly reconcile never fixes; Phase 11A/11B mutation boundary unchanged.
- 2026-07-14: Accepted Phase 11A / 11B split as repo roadmap. Phase 11A focuses on SSOT specs, knowledge dogfood, Beads identity, and readonly reconcile. Phase 11B is reserved for Beads import/apply. Repo SSOT specs are truth; NotebookLM is derived read/query; Beads task id is binding result.
- 2026-07-14: Registry alignment — `docs/project/vibe-control-spec.md` is the active formal SSOT (`vibe_control_spec`); historical `VIBE_CONTROL_V0_5_SPEC.md` removed and no longer active. `DECISION_LOG.md` remains `include_extra`.
- 2026-07-14: Phase 10.5 — skills install uses Option A (`--dry-run` or `--apply`; no silent mutation).
- 2026-07-14: Phase 10.5 — `knowledge retry` fail-closed without `--dry-run`/`--apply` (aligned with sync).
- 2026-07-13: Prefer `.config/vibe-control.yaml` as primary config path.
- 2026-07-13: Phase 4 uses allow-listed NotebookLM notebook alias `OPM-test` for integration smoke.
- 2026-07-13: Skills install defaults to symlink into `~/.agents/skills`.
