# Product thinking index (2026-07 Knowledge / Task / Hetu)

**Purpose:** Keep product research + settled strategy in-repo so agents do not lose
tables that only lived in chat / Cursor Canvas.

**Canvas mirror title (ephemeral UI):** `Vibe — 自解释 + 高频场景`  
→ same content is owned by the files below (Canvas is a view, not SSOT).

| Doc | Role |
|---|---|
| [agent-scenario-research.md](./agent-scenario-research.md) | HF scenarios, self-explain inventory, star products, query-value framing |
| [product-next-paths.html](./product-next-paths.html) | Diagrams + paths (open in browser) |
| [sync/20260717-knowledge-task-polish-strategy.md](./sync/20260717-knowledge-task-polish-strategy.md) | **Accepted** K/T near-term polish (no new K/T flagship) |
| [sync/20260720-knowledge-multi-notebook-corpus-design.md](./sync/20260720-knowledge-multi-notebook-corpus-design.md) | **Accepted design** target-scoped corpus / multi-notebook (impl landed) |
| [sync/20260721-knowledge-local-fts-provider-spec.md](./sync/20260721-knowledge-local-fts-provider-spec.md) | **Accepted** local_fts (SQLite FTS5) retrieval provider + provider selection |
| [sync/20260721-knowledge-local-fts-provider-review.md](./sync/20260721-knowledge-local-fts-provider-review.md) | Owner review that accepted local_fts with P1/P2 + C1–C5 |
| [sync/20260721-self-grill-session-loop-design.md](./sync/20260721-self-grill-session-loop-design.md) | **Accepted** minimal closed loop: local session + Progress pull-back + prompt exit gate |
| [sync/20260722-core-claim-grading-hardening-spec.md](./sync/20260722-core-claim-grading-hardening-spec.md) | **Accepted** core operation-evidence / claim-grading hardening (impl landed) |
| [plans/20260722-core-control-contract-hardening-plan.md](./plans/20260722-core-control-contract-hardening-plan.md) | Executed plan for core control-contract hardening |
| [sync/20260722-hetu-runtime-mvp-spec.md](./sync/20260722-hetu-runtime-mvp-spec.md) | **Accepted** Hetu runtime MVP (fake/unit landed; real reindex optional) |
| [plans/20260722-hetu-runtime-mvp-plan.md](./plans/20260722-hetu-runtime-mvp-plan.md) | Executed plan for Hetu runtime MVP |
| [sync/20260722-skill-assay-spec.md](./sync/20260722-skill-assay-spec.md) | **Accepted** Skill Assay measurement tool (not a capability) |
| [sync/20260722-skill-assay-spec.md](./sync/20260722-skill-assay-spec.md) | **Accepted** Skill Assay (`vibe skill-assay`) — measure any local skill across hosts |
| [sync/20260722-skill-output-diagnostic-system-spec.md](./sync/20260722-skill-output-diagnostic-system-spec.md) | **Superseded** draft (renamed to Skill Assay) |
| [sync/20260719-hetu-capability-decision.md](./sync/20260719-hetu-capability-decision.md) | **Accepted** Hetu strategy / boundary |
| [vibe-control-hetu-spec.md](./vibe-control-hetu-spec.md) | **Accepted design** Hetu formal spec (runtime not shipped) |
| [vibe-control-feedback-spec.md](./vibe-control-feedback-spec.md) | **Accepted** experience-feedback SSOT (pain/dissatisfaction/bright spot; not tasks) |
| [../task-consumer-path.md](../task-consumer-path.md) | Thin path A: when to use `vibe` vs `bd` |
| [../feedback.md](../feedback.md) | Human Issues channel + pointer to feedback spec |
| [DECISION_LOG.md](./DECISION_LOG.md) | Dated decision bullets |

**How to read**

1. Strategy notes = current roadmap stance (K/T polish + Hetu track).  
2. Scenario research = reference catalog (do **not** treat rows as a feature backlog).  
3. HTML = visual layering / install / task path A vs B.  
4. Hetu decision + `vibe-control-hetu-spec.md` = design contract; runtime/CLI later.
