# Decision — Hetu capability (third pillar) v0 (2026-07-19)

**Status:** Accepted (product / narrative boundary)  
**Audience:** future agents / maintainers  
**Not yet:** Capability Profile ID wiring in runtime, CLI implementation, roadmap anchor  
**Formal design spec:** `docs/project/vibe-control-hetu-spec.md` (v0.1)  
**Related:**

- Index: `docs/project/PRODUCT_THINKING_INDEX.md`
- Prior stance (K/T polish only): `docs/project/sync/20260717-knowledge-task-polish-strategy.md`
  — still holds for **Knowledge/Task flagship**; Hetu is a **new** capability track
- Front model: `docs/project/vibe-control-spec.md` (Capability Profile today: `knowledge | task | sdd | tdd`)
- Site trailer mid-credits `HETU` = marketing tease only; **product truth lives here**

---

## 1. One-line definition

**Hetu** is Vibe Control’s **code-structure understanding** capability: a gated,
CLI-first surface over a swappable structural provider (code knowledge graph),
so agents get reliable callers / impact / architecture facts — with git
freshness bound in — without rediscovering the repo via grep/Read every session.

> Provider = whether a graph exists.  
> Vibe = agents use it without lying, over-mutating, or ignoring stale indexes.

**Not:** a lightweight agent workflow engine (strengthen **Task** + Beads `dep`
instead). **Not** a third docs-ask surface (that remains **Knowledge**).

---

## 2. Pillar map (peer capabilities)

| Capability | Answers | Default provider direction |
|---|---|---|
| **Knowledge** | What MUST / decisions say | NotebookLM (derived from repo SSOT) |
| **Task** | What to do next / gates | Beads (and future task providers) |
| **Hetu** | How code is wired / what a change hits | codebase-memory-mcp first; codegraph (and peers) swappable |

Shared shell (all three must have):

- Capability Profile: default **disabled**; enable explicitly
- `status` / `doctor` / `describe` self-explain
- Unified JSON envelopes (`ok` / `code` / `mutation` / `next_actions`)
- Readonly default; mutations via dry-run → apply + approval matrix
- Swappable providers; unavailable / unclean → degraded, **never fake green**
- Thin skills → CLI only
- **CLI-first:** deterministic control in CLI; model only where a provider truly needs it (Hetu almost never needs a Vibe-owned LLM step — agent reasons on CLI results)
- **Adopt existing installs:** detect → agent prompts owner choice → if enable, Vibe takes the control plane and **preserves** prior config/data (no wipe)

---

## 3. What Hetu uniquely owns

### Agent pain (why this pillar exists)

Discovery tax: repeated Grep/Read, missed callers / dynamic edges, unknown blast
radius, stale indexes treated as truth, dual-sourcing git + graph by hand.

### Mechanism surfaces (not a scenario menu)

| Mechanism | Intent |
|---|---|
| Index lifecycle | create / refresh / status (missing · indexing · ready · stale) |
| Structural query | search / trace / neighbors (provider-backed) |
| Impact | git diff or ref → affected symbols + radius |
| Architecture | seams / clusters / hubs (provider-backed overview) |
| Freshness binding | `index_commit` ↔ `HEAD` / dirty tree in every serious envelope |
| Hygiene hints | rename/delete drift, half-index (report + next_actions) |

### Git fusion (accepted)

Hetu CLI **may call git** so agents get trustworthy structure+change results
without hand-rolling git for impact/freshness.

| In scope | Out of scope (leave to native `git`) |
|---|---|
| HEAD / index commit binding | push / fetch / rebase / rewrite history |
| Dirty? diff vs chosen ref | interactive conflict resolution |
| Changed paths → graph blast radius | blame narrative / authorship chat |

Canonical provider precedent: codebase-memory `detect_changes(since, base_branch)`
already maps **git diff → symbols**. Hetu elevates that to a default gated CLI.

---

## 4. Relative to direct provider use

Why not only call codebase-memory-mcp / codegraph MCP?

| Direct-provider failure | Hetu control plane |
|---|---|
| Stale graph still trusted | Freshness gate + doctor next_actions |
| No index / half index still queried | Honest status; fail closed on “ready” claims |
| Tool zoo / ad hoc MCP params | Stable `vibe hetu …` surface |
| Unshaped chat “evidence” | Structural facts + uncertainty in envelopes |
| Reckless full reindex / delete project | Mutation gates (dry-run/apply) |
| Multiple graph tools, conflicting habits | One capability, swappable provider |
| Graph vs SSOT confusion | Explicit split vs Knowledge |
| Re-init destroys existing graph | Detect → choose → adopt, keep data |
| Consumer has no product git tree | Same learn path: help / describe / doctor / skills |

**Do not reimplement** the graph engine. Adapt providers.

---

## 5. Provider policy

### Default / first

- **Primary provider target:** [DeusData/codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp)
  (local structural graph; Hybrid LSP; `detect_changes`; no embedded LLM)

### Swappable (not dual-active by default)

- [colbymchenry/codegraph](https://github.com/colbymchenry/codegraph) — second provider candidate
- Watch list (not MVP): code-review-graph (PR blast-radius niche), Serena (LSP/edit toolkit — different slot), others

### Explicitly not Hetu primary

- **Graphify-class multimodal** (code + docs/PDF/meetings one graph) — collides with **Knowledge**; do not make Hetu a docs graph
- Cursor / Copilot proprietary indexes — not a portable Vibe provider
- Pure vector RAG as the **main** Hetu backend — weak on structure

### Dual install

| Mode | Policy |
|---|---|
| One capability, many providers (pick one active) | **Yes** |
| Default both active, agent asks both | **No** (double truth / double cost) |
| Short eval dual-install | OK if labeled experimental |

---

## 6. Delivery slices

| Slice | Meaning | MVP? |
|---|---|---|
| **A — readonly** | status / doctor / search / trace / impact / architecture | **Yes** |
| **B — gated mutation** | reindex / refresh apply path | **Yes** (with A) |
| **C — cross-surface compose** | feed impact into brief / implementation prompt / progress blocks | **Later** — not Hetu core definition |

Workflow/orchestration remains **Task**, not Hetu.

---

## 7. Non-goals

- Lightweight agent workflow / workflow engine
- Third capability that is “docs ask #2”
- Rebuilding Beads/task graphs inside Hetu
- Swallowing full git UX (blame, conflict UI, remotes)
- Fake product pages or shipped claims before runtime exists
- Freezing owner business scenarios into Hetu menus
- Engine / Gateway / SSOT-manager slogans as the external name of Hetu

---

## 8. Landscape note (research snapshot 2026-07)

Same category (local tree-sitter → graph → MCP) is crowded and high-star
(e.g. Graphify ~90k+, codegraph ~60k+, codebase-memory ~30k+, Serena ~25k+,
code-review-graph ~20k — counts move fast). **Differentiation for Vibe is the
control plane**, not another graph. Stars are market signal, not vendor lock-in.

---

## 9. Relation to site / trailer

Homepage film may flash `HETU` as mid-credits tease. That does **not** define
product scope. Product scope is this decision + `docs/project/vibe-control-hetu-spec.md`.

---

## 10. Next engineering / docs steps (ordered)

1. ~~Draft formal `docs/project/vibe-control-hetu-spec.md`~~ **Done** (v0.1 design).
2. Propose Capability Profile ID (likely `hetu`) vs current catalog `knowledge | task | sdd | tdd`
   — requires Front/Core acceptance; do not silently reuse `sdd`/`tdd`.
3. Roadmap anchor only after owner accepts scope + first CLI surface sketch.
4. Implement A+B behind default-disabled capability; fake/local provider for tests first.
5. Defer C until A+B dogfood proves envelopes + freshness.

**Until then:** no claim of shipped Hetu; no `product_ready` dependency on Hetu.

---

## 11. Summary for agents

```text
Hetu = peer capability to Knowledge/Task
     = code structure control plane over swappable graph providers
     = CLI-first + git freshness/impact fusion + adopt-without-wipe
     ≠ workflow engine ≠ docs ask ≠ second graph product
Default provider direction = codebase-memory-mcp
MVP = readonly + gated reindex (A+B); compose into brief/prompt later (C)
```
