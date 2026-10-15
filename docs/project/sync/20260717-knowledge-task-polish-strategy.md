# Decision — Knowledge / Task polish strategy + install debt (2026-07-17)

**Status:** Accepted  
**Audience:** future agents / maintainers  
**Related:**

- Index: `docs/project/PRODUCT_THINKING_INDEX.md`
- Full tables: `docs/project/agent-scenario-research.md`
- Diagrams: `docs/project/product-next-paths.html`
- Canvas view title (ephemeral mirror): **「Vibe — 自解释 + 高频场景」**
  — do not treat Canvas as SSOT; keep markdown/HTML updated.

---

## 1. Product stance (settled)

Vibe Control remains an **agent-facing, provider-backed control plane**.

| Layer | Owns |
|---|---|
| Owner / agent | What corpus to upload, how to organize docs, business questions, task graph discipline |
| Vibe | Sync bounds, ask policy shell, hygiene, capability gates, mutation approvals, CLI envelopes |
| Providers | NotebookLM (knowledge), Beads (task) |

**Not** an SSOT manager, not a scenario product, not a Beads graph engine, not a harness.

---

## 2. Knowledge — what we will / will not do next

### Accepted

- Scenario catalogs (MUST / decisions / runbooks / …) are **valuable as research**, not as hardcoded product features.
- Highest-leverage *idea* was: Ask policies as **selectable mechanisms** — but **do not ship multi-profile Ask as a near-term feature** until there is real multi-profile demand.
- Owner/agent may compile intermediate artifacts (FAQ, decision digests) **into their own corpus**; Vibe only re-answers after sync.
- Query value = **provable answers under source constraints** (logic / linguistics / information), not more scenario names.

### Explicitly deferred (no next important Knowledge feature now)

- Top-N FAQ cache as a Vibe product surface
- Built-in `decisions` / `runbook` scenario types
- `vibe search` / external docs crawl capability
- Replacing NotebookLM or adding parallel knowledge providers

### Near-term Knowledge work

- **Polish existing debt only** (ask v2 / persona / hygiene already landed).
- No new Knowledge capability track until a **mechanism-level** need recurs in real use.

### Narrow exception (2026-07-20)

- **Target-scoped corpus / multi-notebook selectors** accepted as a mechanism-level
  exception — see `docs/project/sync/20260720-knowledge-multi-notebook-corpus-design.md`.
- Does **not** reopen multi-profile Ask, FAQ cache, `vibe search`, or provider replacement.

---

## 3. Task — what we will / will not do next

### Accepted

- Daily path = Beads CLI (`ready` / `show` / `create` / `dep` / `close`); Vibe proves **TASK_READY**.
- Task chains / reorder / reconnect = **Beads data structures** (`bd dep …`); do **not** re-implement in Vibe.
- Managed live apply remains **non-default / gated**.

### Explicitly deferred

- Vibe-side scheduler / replan engine
- Option B (unlock live apply) unless separately accepted

### Near-term Task work

- Docs / doctor clarity only; no new Task subsystem.

---

## 4. Self-explain + skills (the concrete near-term debt)

### Runtime learning model

Agent in a consumer repo has **no** vibe-control git tree. Learn via:

```text
vibe --help
vibe describe --json
vibe doctor --json
thin skills (~/.agents/skills) routing to CLI
```

`vibe readme` does **not** exist; closest is `describe`.

### Skills install

- CLI already: `vibe skills install --dry-run|--apply [--force]`
- **Debt fixed in this closeout:**
  - `scripts/install-user.sh` aligns skills after CLI install/upgrade (`--apply --force`; skip with `VIBE_SKIP_SKILLS=1`)
  - `vibe doctor` / integration doctor surface skills **missing vs mismatch** with a single next_action

---

## 5. Strategy one-liner

> **No new Knowledge/Task flagship features now. Record scenario research for later. Polish install ↔ skills ↔ doctor debt. Keep abstractions mechanism-level; never freeze owner business scenarios into the product.**

**Update (2026-07-19):** A **new** peer capability track — **Hetu** (code-structure
control plane) — was accepted separately. That does **not** reopen Knowledge/Task
flagship work. See `docs/project/sync/20260719-hetu-capability-decision.md`.
