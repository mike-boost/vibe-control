# Decision — Agent self-grill communication contract (Option A)

**Status:** Accepted (2026-07-21); **mount amended same day** (Engine surfaces, not skill sprawl)  
**Audience:** coding agents + maintainers  
**Related:**

- Inspiration (thought only): install-flink `skills/self-grill` — not vendored
- Knowledge multi-notebook: `docs/project/sync/20260720-knowledge-multi-notebook-corpus-design.md`
- Feedback (orthogonal): `docs/project/vibe-control-feedback-spec.md`
- Polish: `docs/project/sync/20260717-knowledge-task-polish-strategy.md`
- Gateway: `src/vibe_control/gateway.py` (`ROUTE_TABLE`)
- Describe / Brief: `src/vibe_control/describe.py`, `src/vibe_control/progress_brief.py`

---

## 0. Amendment (2026-07-21) — product mount

```text
WRONG:  fourth installable skill agents must "switch to"
RIGHT:  communication contract projected by Engine self-explain surfaces
        Gateway thin-routes to Brief with contract attached
        Knowledge remains probe-only (--notebook fail-closed already)
```

| Surface | Role |
|---|---|
| `vibe describe --json` → `communication_contracts.self_grill` | Always-on awareness (learn the product) |
| `vibe gateway --intent grill_brief --json` | Entry when owner asks 审讯 / hard-bug: Brief + required reply shape + next_actions |
| `vibe brief --json` with Engine flag when delegated from Gateway | Same projection; no second state engine |
| Knowledge doctor/query/inventory/`--notebook` | Readonly probes only |
| `vibe feedback` | Optional after-action friction capture — not grill runtime |
| Installable skills | **Do not** ship `vibe-self-grill`; front-door points at Gateway/describe only |

**Persistence:** local session receipts under `runtime/vibe-grill/` (gitignored;
same class as feedback). Not SSOT. Not closeout / `product_ready` gate.
Design: `docs/project/sync/20260721-self-grill-session-loop-design.md`.

**Exit fail-closed:** while active `loop_status=IN_PROGRESS`,
`vibe implementation prompt` returns `SELF_GRILL_IN_PROGRESS`.
Progress/Brief project `self_grill_in_progress` + `CONTINUE_SELF_GRILL`
(closeout/sync/task-cache blockers still own `safe_next` when present).
Engine still does **not** parse agent claim-table prose.

### Known limitations (session loop — 2026-07-21)

```text
self-grill = entry contract + local session + Progress pull-back + prompt exit gate
          ≠ prose claim-table referee
          ≠ multi-active grills
```

| Claim people might over-read | Reality |
|---|---|
| “Agent always stays in grill” | Active `IN_PROGRESS` receipt makes Progress/Brief pull back; must open via `grill_brief` first. |
| “Cannot claim root-cause proven” | Prompt is blocked; chat prose is not parsed. Close with EXHAUSTED/BLOCKED_ON_LIVE. |
| “Agent always discovers grill” | Aware path: `grill_brief` / `describe` / active session — not ambient. |

---

## 1. What we accept

```text
Option A:
  Thin communication contract that interrogates the AGENT's own claims.
  Knowledge is the evidence probe.
  NOT a Knowledge subsystem, NOT a new provider capability, NOT HSP-as-product,
  NOT a user-facing skill to switch to.
```

Owner may open the mode (“用审讯模式” / “loop 到没屎”). Agent never questionnaires the owner for repo-resolvable paths.

---

## 2. Layering (non-negotiable)

| Layer | Owns | Does not own |
|---|---|---|
| **This contract** (docs + Engine projection) | Reply shape, claim statuses, when to invoke, Gateway entry | Sync, ask templates, product_ready computation |
| **Knowledge CLI** | Corpus, sync, single-notebook ask, hygiene, provenance | Grill loops, claim graphs |
| **Gateway** | Intent → Brief (grill_brief); static contract attach | Readiness recompute, mutation |
| **Progress / Brief** | safe_next / next_actions projection | Becoming a second readiness engine |
| **vibe feedback** | Experience-signal artifacts (optional after) | Runtime interrogation |
| **HSP** | Borrow plain-speech ideas only | Not a Vibe Engine capability |
| **Front-door skill `vibe-control`** | Route humans/agents to `describe` / `gateway --intent grill_brief` | Hosting a parallel skill catalog entry for grill |

---

## 3. When to invoke

- Owner distrusts an RCA / fix / “真相”
- Hard bug, non-trivial “one root cause” story
- First-principles / “找关联本质”
- Knowledge degraded but agent still wants to claim readiness
- Owner says keep grilling / loop until no more shit found

Do **not** invoke for routine status / closeout / happy-path sync.

**Agent aware path (guaranteed visibility):**

```text
1. Prefer: vibe gateway --intent grill_brief --json
2. Or:    vibe describe --json  → read communication_contracts.self_grill
3. Then:  Knowledge readonly probes per next_actions / claim table
```

---

## 4. Reply shape (every grill round)

Owner-facing language: Chinese. Claim labels / codes: English.

```text
THESIS: <one sentence under fire>
LOOP_STATUS: IN_PROGRESS | EXHAUSTED | BLOCKED_ON_LIVE

Claim table (frontier):
| id | claim | status | notebook | probe | evidence | next |
|---|---|---|---|---|---|---|

Statuses: PROVEN | FALSIFIED | PARTIAL | OPEN | DEFERRED_SLICE | OWNER_DECISION

Rules:
- PARTIAL / OPEN must spawn children or stay on frontier
- PROVEN requires Knowledge receipt and/or repo paths (never chat memory alone)
- notebook: required when allow_list length ≥ 2; else sole/default; or "n/a" if claim is code-only
- No cross-notebook ask; wrong notebook ⇒ evidence invalid for that claim
- Sufficiency / “safe to retry” only if sufficiency claims are PROVEN
```

Done only when: no OPEN/soft-PARTIAL without deferred tag; a “what else bites next?” pass adds zero claims; sufficiency honest.

---

## 5. Knowledge probe rules

```text
Readonly auto-run OK:
  vibe knowledge doctor [--notebook] --json
  vibe knowledge status [--notebook] --json
  vibe knowledge inventory [--notebook] --json
  vibe knowledge query --question-file … [--notebook] --json

Never auto-run:
  sync/retry --apply (incl. --confirm-non-default-sync)

Record: sync_state, provider_ask_clean, sources paths/doc_ids, degraded or not.
Evidence insufficient → CHECK_CORPUS_INVENTORY → continue grill (do not stop because degraded).
```

Multi-notebook = evidence drawer; choosing `--notebook` is part of first-principles.

---

## 6. Explicit non-goals

- Installable `vibe-self-grill` skill / skill sprawl
- `vibe knowledge grill` / Knowledge `mode=`
- HSP as peer capability beside Knowledge/Task/Hetu
- Owner interview questionnaires
- Baking consumer-domain L1/L2/L3 into Vibe
- Grill artifacts as SSOT or closeout gates
- Gateway-owned grill loop engine or second readiness engine

---

## 7. Implementation discipline

1. Prefer extend `describe` / `brief` / `gateway.ROUTE_TABLE` / Progress pull-back — do not add parallel control planes.
2. Local session receipts live under `runtime/vibe-grill/` per
   `docs/project/sync/20260721-self-grill-session-loop-design.md` (not SSOT / not closeout).
3. Do not weaken existing product_ready / ask_clean / `--notebook` fail-closed behavior.
4. Tests: describe field present; gateway `grill_brief` opens session + contract;
   Progress pull-back; prompt `SELF_GRILL_IN_PROGRESS`; skills install list stays
   front-door trio (+ knowledge/implementation only).

---

## 8. Optional after-action

If the grill exposed product friction, owner may ask to `vibe feedback draft …`.
