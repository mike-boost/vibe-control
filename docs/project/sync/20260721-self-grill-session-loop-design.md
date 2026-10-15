# Design — Self-grill session loop (minimal closed loop)

**Status:** Accepted for implementation (2026-07-21) — owner wants usable results  
**Builds on:** `docs/project/sync/20260721-agent-self-grill-comm-contract.md`  
**Supersedes v1 limitation:** mid-course pull-back + exit gate now in scope (thin local session)

---

## 1. Goal

```text
Agent can open a grill, keep being pulled back while IN_PROGRESS,
and cannot take implementation-prompt / “done coding” path until
LOOP_STATUS is EXHAUSTED or BLOCKED_ON_LIVE (closed).
```

Not a Knowledge feature. Not SSOT. Not closeout / product_ready gate.

---

## 2. IDs

| Id | Meaning |
|---|---|
| `grill_id` | One interrogation **session** (e.g. `grill-20260721-110000`) |
| `round_id` | Integer rounds under that session; **first round = 0** |

---

## 3. Local receipt (consumer repo)

```text
runtime/vibe-grill/
  active.json          # pointer: current grill_id or null
  sessions/<grill_id>.json
```

- Same class as `runtime/vibe-feedback/` — local, gitignored, not product SSOT.
- Schema `vibe.grill.session.v1`.

```yaml
schema: vibe.grill.session.v1
grill_id: grill-...
round_id: 0
loop_status: IN_PROGRESS   # IN_PROGRESS | EXHAUSTED | BLOCKED_ON_LIVE
thesis: "..."
opened_at: ...
updated_at: ...
claim_count: 0             # optional counter; full claim table stays in agent reply
```

**One active session** per consumer repo (v1). Opening while another is IN_PROGRESS fails closed unless `--force-new` (closes previous as BLOCKED_ON_LIVE).

---

## 4. Engine surfaces (thin)

| Command | Role |
|---|---|
| `vibe gateway --intent grill_brief` | Open-or-resume: ensure session, attach contract + session ids, CONTINUE next_action |
| `vibe grill status --json` | Readonly active session |
| `vibe grill checkpoint --json` | Advance: set `round_id` and/or `loop_status` (still open if IN_PROGRESS) |
| `vibe grill close --status EXHAUSTED\|BLOCKED_ON_LIVE --json` | End session; clear active |

No Knowledge mutation. Checkpoint/close are **local file writes** only (like feedback draft).

---

## 5. Mid-course pull-back

When `active` session has `loop_status=IN_PROGRESS`:

- `vibe progress` / `vibe brief` (plain or grill):  
  - add `blocked_reasons` entry `self_grill_in_progress`  
  - `safe_next_action` = `CONTINUE_SELF_GRILL` **unless** a higher-priority closeout/sync blocker already owns safe_next (closeout incomplete still wins)

Higher priority (unchanged): closeout / ask_clean / task_cache blockers.

---

## 6. Exit gate (result guarantee)

When active `IN_PROGRESS`:

- `vibe implementation prompt` → **fail closed**  
  `code=SELF_GRILL_IN_PROGRESS`  
  next_actions: `grill status` / `grill checkpoint` / `grill close` / Knowledge probes

When `EXHAUSTED` or `BLOCKED_ON_LIVE` (closed, no active):

- prompt / progress behave as today

**Does not** change `product_ready` or closeout completeness.

---

## 7. Non-goals

- Multi active grills  
- Storing full claim tables as SSOT  
- Auto-spawn claims  
- Parsing agent chat prose  
- Grill gating NotebookLM sync / Beads  

---

## 8. Tests

- open → active.json + session file, round_id=0  
- progress pulls CONTINUE while IN_PROGRESS  
- prompt fails while IN_PROGRESS  
- close EXHAUSTED → prompt allowed again (other blockers notwithstanding)  
- grill_brief resumes same grill_id if already active  
