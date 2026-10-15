# Phase 12 — Implementation Prompt Generator

**Status:** design-aligned (local/readonly default); Front/Core contract in `vibe-control-spec.md` §7  
**Depends on:** Phase 11A reconcile + Phase 11B apply baseline + three-layer formal specs  
**Acceptance:** focused unit tests (+ optional local acceptance)  
**Language policy:** Explanation in Chinese; code/commands/schemas in English.

## 1. Goal

Produce a **repo-owned, copy-paste-ready coding-agent prompt** from:

- current SSOT facts / expected-task identity
- provider readiness summary (`product_ready`, blocked reasons)
- knowledge readiness + task reconcile/apply plan summary
- selected Vibe-managed Beads task context (binding only)

Agents should start implementation work from `vibe` CLI evidence, not chat memory or NotebookLM inventiveness.

## 2. CLI surface

```text
vibe implementation prompt --task <managed_key|provider_task_id|ssot_anchor> --json
```

Selector resolves:

1. exact `managed_key`
2. exact `ssot_anchor`
3. `provider_task_id` as **lookup only** (binding via readonly reconcile when provider available)

Ambiguous / missing → fail closed. Readonly only: `mutation=false`. No Beads/NotebookLM mutation.

## 3. JSON envelope

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
```

Compatibility aliases: `data.prompt_text`, `data.task`, `data.sections`.

## 4. Required prompt sections (stable order)

1. task goal  
2. repo SSOT identity  
3. selected task anchor  
4. product_ready summary  
5. knowledge readiness summary  
6. task reconcile/apply summary  
7. hard boundaries  
8. mutation approvals required / not required  
9. required tests/gates  
10. expected final report fields  
11. safety confirmation  
12. final `git status --short`  

## 5. Redaction / identity

- No raw notebook refs / source IDs / secrets  
- `provider_task_id` absent or hashed; never identity  
- `managed_key` / `ssot_anchor` / `ssot_path` allowed  

## 6. Degraded modes

`product_ready=false`, knowledge unsynced, ask unclean, reconcile mismatch, apply blocked, ambiguous/missing selector, local modifications, `provider_sync_required`, missing Project Sources handoff → warnings / next_actions, not green PASS.

## 7. Non-goals / forbidden

- Treat NotebookLM output as truth  
- Use Beads task id as source identity  
- Auto-run live Beads apply / NLM sync  
- Claim ChatGPT Project Sources were updated  

## 8. Test IDs

| ID | Behavior |
|---|---|
| P12-SPEC-01 | phase12 spec exists with CLI + boundaries |
| P12-GEN-01 | resolve by ssot_anchor roadmap.phase12 |
| P12-GEN-02 | resolve by managed_key |
| P12-GEN-03 | prompt contains SSOT path, hard boundaries, gates |
| P12-GEN-04 | prompt does not treat NLM as truth; managed_key present; raw notebook ref absent |
| P12-GEN-05 | provider_task_id redacted to hash in envelope by default |
| P12-GEN-06 | unknown selector → fail closed |
| P12-GEN-07 | contract envelope fields + degraded warnings |
| P12-GEN-08 | provider_task_id is not identity |
| P12-CLI-01 | `vibe implementation prompt --task … --json` readonly |

## 9. Default gates

Local only. No real NotebookLM mutation. No Beads mutation from this command.
