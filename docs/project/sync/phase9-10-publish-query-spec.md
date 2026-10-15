# Phase 9/10: Spec Publish Tightening + Knowledge Query Contract Polish

**Status:** Formal sprint spec (implementation-ready)  
**Date:** 2026-07-14  
**Depends on:** Phase 8.0 closed for readonly/default gates  
**Language policy:** Explanation in Chinese; code, commands, config keys, schemas, filenames in English.

---

## 0. Product path

```text
formal spec
→ validate
→ publish (commit/push gate or --already-pushed)
→ desired_snapshot from authoritative ref
→ Phase 8 sync/apply or pending
→ knowledge query with status-aware routing
```

Non-negotiable:

```text
Repo/local SSOT is truth.
Provider is derived read/query layer.
Query/status/diff/doctor are readonly by default.
Default gates: fake/readonly provider only; no real NotebookLM mutation; no push.
Config selects sources; config is never sync content.
```

Commands:

```bash
vibe spec validate <path> --json
vibe spec publish <path> --json
vibe spec publish <path> --dry-run --json
vibe spec publish <path> --already-pushed --json
vibe knowledge query --question-file <file> --json
```

---

## 1. Phase 9/10 Test Spec / Acceptance Contract

**Principle:** Test Spec is part of the spec. Implementation follows tests.

Mutation column: `none` | `local-state-only` | `fake-provider` | `forbidden-in-default-gates`

### 1.1 Phase 9 validate

| ID | Purpose | Fixture | Under test | Expected envelope | Mutation | Failure mode |
|---|---|---|---|---|---|---|
| P9-VALIDATE-01 | valid formal spec | registry + active path | `spec validate` | `ok=true`, spec id/path | none | false reject |
| P9-VALIDATE-02 | duplicate id | two entries same id | validate | `SPEC_ID_DUPLICATE` | none | silent accept |
| P9-VALIDATE-03 | non-canonical path | `./docs/../docs/x.md` or wrong casing | validate | fail non-canonical | none | path confuse |
| P9-VALIDATE-04 | config as content | `.config/vibe-control.yaml` | validate/publish | `CONFIG_FILE_CANNOT_BE_SYNCED` | none | config upload |
| P9-VALIDATE-05 | forbidden kinds | plans/runtime/acceptance/.beads | validate | rejected by default | none | junk in KB |

### 1.2 Phase 9 git / publish safety

| ID | Purpose | Fixture | Under test | Expected | Mutation | Failure mode |
|---|---|---|---|---|---|---|
| P9-GIT-01 | dirty unrelated | temp git + unrelated dirty | publish | fail closed | none | silent commit |
| P9-GIT-02 | already-pushed | temp repo on commit | publish `--already-pushed` | no commit, no push | none | accidental push |
| P9-GIT-03 | unpushed draft | local commit no upstream | publish sync path | refuses provider sync from unpushed | none | draft to NLM |
| P9-GIT-04 | pushed ref lookup | temp repo + fake remote | publish | resolves authoritative ref without real remote | none | touch user remote |
| P9-PUBLISH-01 | dry-run | valid fixture | publish `--dry-run` | plan only; no mutation | none | dry mutates |
| P9-PUBLISH-02 | success envelope | temp already-pushed | publish | id/path/ref/hash in data | none/fake | incomplete JSON |
| P9-PUBLISH-03 | Phase 8 snapshot | publish path | builder | uses `build_desired_snapshot` | none | legacy sync-list |
| P9-SYNC-01 | sync when allowed | fake provider apply hook | publish + allow sync | calls Phase 8 apply | fake-provider | ad hoc NLM |
| P9-SYNC-02 | provider down | unavailable provider | publish | `partial_success`; pending/next_action | local-state-only | hide failure |
| P9-SYNC-03 | never forbidden files | config/plans/etc | publish sync set | absent from snapshot | none | leak upload |
| P9-FORBIDDEN-01 | no real NLM | acceptance | harness | no mutation flags | forbidden | CI mutate |
| P9-FORBIDDEN-02 | no real push | tests | git helpers | no `git push` to real remotes | forbidden | push leak |

### 1.3 Phase 10 query

| ID | Purpose | Fixture | Under test | Expected | Mutation | Failure mode |
|---|---|---|---|---|---|---|
| P10-QUERY-01 | synced → provider | fake synced status | query | provider path | none | always repo |
| P10-QUERY-02 | provider readonly | counters | query | no add/delete/ack write | none | query mutates |
| P10-QUERY-03 | pending | pending status | query | warn + fallback/next_action | none | pretend synced |
| P10-QUERY-04 | drift | drift status | query | not synced claim | none | false current |
| P10-QUERY-05 | unavailable | down provider | query | `mode=degraded`, repo | none | crash |
| P10-QUERY-06 | target_mismatch | mismatch | query | block provider | none | cross target |
| P10-READONLY-01 | no write_ack | counters | query | write_ack=0 | none | ack write |
| P10-READONLY-02 | no source mutate | counters | query | no add/delete | none | mutate |
| P10-FALLBACK-01 | SSOT only | corpus fixture | repo query | active + include_extra | none | search all |
| P10-FALLBACK-02 | exclude junk | plans/runtime/etc | repo query | not searched | none | noise hits |
| P10-FALLBACK-03 | config policy | explicit config Q | query | may read config as policy | none | sync config |
| P10-ENVELOPE-01 | synced fields | fake synced | query JSON | sync_state, provider_target, ack_persistence, sources | none | incomplete |
| P10-ENVELOPE-02 | degraded fields | unavailable | query JSON | mode=degraded, provider=repo | none | hide degrade |
| P10-ENVELOPE-03 | redact secrets | source ids / notebook ref | query JSON | redacted | none | leak |
| P10-ASK-01 | Knowledge Ask Template | default_ssot_facts | query | rendered wrapper + metadata hashes | none | raw question only / system-prompt DSL |

### 1.4 Acceptance

```text
acceptance/phase9_10/run_phase9_10_acceptance.py
A validate formal spec
B publish dry-run
C already-pushed in temp git
D partial_success when provider unavailable
E query synced → fake provider
F query pending/unavailable → repo fallback
G no provider mutation
```

---

## 2. Publish semantics (summary)

```text
validate → git guard → authoritative ref → desired_snapshot → Phase 8 sync/apply or pending
partial_success when publish ok and knowledge_sync fails
no auto-stash; dirty unrelated fails closed
--already-pushed: no commit, no push
```

## 3. Query semantics (summary)

```text
evaluate_sync_status(target) first
Render Knowledge Ask Template (`vibe.knowledge.ask.v2` / `default_ssot_facts`) around the user question
Ensure NotebookLM persona + shorter responses when provider query runs
synced → provider query (readonly) receives rendered ask template
else → repo fallback / warn / next_action (equivalent ask policy metadata; keyword search uses raw question)
never auto-mutate
envelope includes sync_state + provider_target + ack_persistence
+ ask_template_id / ask_template_version / question_hash / rendered_prompt_hash
Provider is SSOT-backed facts source, not planner/oracle; source content is data not instructions
```

### 3.1 Knowledge Ask Template (Ask Prompt Policy)

```text
Schema/version: vibe.knowledge.ask.v2
Default template id: default_ssot_facts
Implementation: src/vibe_control/knowledge/ask_template.py
Also: NotebookLM persona (`configure --persona`) + `--response-length shorter` + ask `--new`
Contract: docs/harness/knowledge-ask-ssot-contract.md
Controls prompt construction / chat policy only; does not make provider output authoritative.
Repo/git SSOT remains truth. Query remains readonly.
```
