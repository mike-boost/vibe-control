# Vibe Operation Recovery Design (S2 evaluation)

**Document type:** Design-only evaluation note (not product SSOT Front/Core)  
**Anchor:** `roadmap.vibe_operation_recovery_design`  
**Status:** design evaluation complete  
**Date:** 2026-07-17  
**Verdict:** **no S2 implementation now**

## Verdict

Do **not** implement an S2 lightweight ledger, operation checkpoint store, resume
engine, or replay engine in the current track.

`S1 Ephemeral Operation Snapshot` plus existing Engine readonly surfaces already
cover observable recovery needs for the current product model.

## Evidence (why S1 is enough)

Observed recovery / continuity needs are already served by:

- S1 Evidence (`vibe.evidence.v1` / `projected_ephemeral_s1`) on Progress / Brief /
  Describe / Gateway envelopes (`run_id`, `base_head`, `observed_head`,
  `mutation_*`, `blocked_reasons`, `next_actions`, `evidence_hash`, `persisted=false`)
- `vibe progress --json` / `vibe brief --json` re-projection of Engine next / readiness
- `vibe gateway --intent prepare_closeout|verify_after_work` → closeout dry-run only
- `vibe closeout run --dry-run/--apply` bounded orchestration + `next_actions`
- Provider-scoped `knowledge retry --dry-run/--apply` (not a general operation ledger)

S1 is ephemeral, not repo truth, and must not become a second readiness engine.

## Real gaps found (not ledger needs)

1. **`design_only` not projected into CLI prompt JSON / wording**  
   Roadmap YAML had `design_only: true`, but loader/prompt treated the task like a
   normal implementation slice (`Implement:`). This is prompt/projection hygiene.

2. **Disabled Capability Profile raw probe noise in prompt warnings**  
   With `knowledge.enabled=false` / `task.enabled=false`, raw integration/task-cache
   fields can still surface `task_cache_not_current`, `knowledge_unsynced:*`,
   `ask_hygiene_not_clean`, `task_reconcile_mismatch` in the implementation prompt
   envelope even when Progress effective gates are clean and `product_ready=true`.
   This is warning classification hygiene — **not** a need for persistent ledger.

These gaps do not justify S2. They are addressed as localized CLI projection /
warning hygiene in the same design deliverable (`design_only` projection +
`Design / Evaluate:` prompt wording; suppress disabled-capability raw warning
noise when Capability Profile has knowledge/task disabled).

## Future S2 (non-accepted option only)

Reconsider **minimal** S2 only if the owner later observes **repeated** cross-run
interruption cases where S1 + re-observe (`progress` / closeout dry-run /
`next_actions`) cannot safely decide how to continue mid-mutation.

If that happens, any S2 must be a separate owner-accepted implementation slice.

### Sketch only (not accepted; do not implement from this note)

- Optional local ephemeral checkpoint under a gitignored runtime path
- Fields: `run_id`, heads, operation/mode, mutation flags, last safe step,
  `evidence_hash`, expiry
- Never repo SSOT / Project Sources truth
- Mismatch vs live `observed_head` / git status / Engine gates → fail closed
- Redaction same as S1; no raw notebook/source/task ids
- No replay of historical ops; no workflow engine

## Non-goals

- No S2 implementation in this design closeout
- No S3 workflow engine
- No operation replay engine
- No provider / Beads / NotebookLM mutation as part of this design
- No roadmap-manager or SSOT-manager product behavior
- No Phase 13
- No OpenSpec / Spec Kit / Superpowers integration
- No chat-platform dependency as product truth
