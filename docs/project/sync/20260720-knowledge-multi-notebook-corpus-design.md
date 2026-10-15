# Design — Target-scoped Knowledge corpus (multi-notebook)

**Status:** Accepted design (2026-07-20) — mechanism approved; implementation not started  
**Date:** 2026-07-20  
**Audience:** owner + coding agents  
**Owner decisions locked:** see §12  
**Related:**

- Front/Core: `docs/project/vibe-control-spec.md`
- Knowledge: `docs/project/vibe-control-knowledge-spec.md`
- Ask: `docs/harness/knowledge-ask-ssot-contract.md`, `docs/harness/knowledge-ask-hygiene-contract.md`
- Provider boundary: `docs/harness/knowledge-provider-boundary.md`
- Phase 8 multi-target rules: `docs/project/sync/phase8-ssot-snapshot-ack-sync-spec.md` §6
- Scale research: `docs/project/sync/20260718-knowledge-scale-notebooklm-industry-research.md`
- Polish stance: `docs/project/sync/20260717-knowledge-task-polish-strategy.md` (**Accepted**: no new K/T flagship until mechanism-level need)
- Index: `docs/project/PRODUCT_THINKING_INDEX.md`

**Language:** Explanation in Chinese where helpful; schemas / commands / field names in English.

---

## 0. One-line verdict

```text
Today: multi-notebook TARGETS exist; corpus is still ONE global desired set.
Needed: optional per-notebook SSOT selectors + sync/ask against one notebook.
Vibe provides capability + self-explain guidance; the agent decides taxonomy and values.
Hard rules:
  - no cross-notebook ask
  - --notebook optional ONLY when allow_list has exactly one entry;
    when 2+ notebooks are configured, --notebook is required
  - path_prefixes is a v1 first-class selector knob (owner: 2026-07-20)
```

This is a **mechanism-level** Knowledge extension (not polish debt). Accepting it reopens a narrow exception to the 2026-07-17 “no new Knowledge flagship” stance — only for this mechanism, not for multi-profile Ask, FAQ cache, or provider replacement.

---

## 1. Problem (agent-facing)

Projects report that **one NotebookLM notebook is not enough**:

1. **Quantity** — NotebookLM plan caps (~50 / ~100 / … sources per notebook). Large SSOT sets overflow.
2. **Classification** — specs, customer requirement dumps, eng docs, ops constraints often should not share one retrieval pool.
3. **Isolation** — mixed / orphan / stale sources pollute ask; cross-domain hits look like “facts.”

Vibe is **agent-facing**. There is no product subject “human fills taxonomy.” Either:

- a human asks the agent to organize knowledge into multiple notebooks, or
- the agent reads self-explain / docs, sees the capability + guidance, and decides.

Even “specs” may be split across notebooks when the agent judges volume or isolation requires it. **Vibe does not prescribe categories or counts.**

---

## 2. Product principles

| Principle | Meaning |
|---|---|
| Capability, not taxonomy | Expose knobs (`path_prefixes`, `include_extra`, `exclude_globs`, `corpus_mode`, notebook alias). Agent fills values. |
| Self-explain guidance | `vibe describe` / doctor / skill text may **suggest** splitting when corpus is large or ask is contaminated — never force a fixed domain model. |
| One ask → one notebook | **No cross-notebook ask**, no fan-out, no merge of answers across targets. |
| Targets already multi | Reuse `ProviderTarget` / allow_list / `--notebook` / per-target receipt. Do not invent a parallel “plane” product noun for agents. |
| Backward compatible | Absent per-notebook selectors ⇒ behavior equals today (global corpus → `default_alias`). |
| Forward-only SSOT | Repo remains truth; NotebookLM remains derived; sync never recovers SSOT from provider. |

### Naming (align with code)

| Prefer (user + code) | Avoid as primary product noun |
|---|---|
| `notebook` / `notebook_alias` / `allow_list` / `default_alias` | `plane` (internal metaphor only) |
| `ProviderTarget` / `target_key_hash` | `partition` as a new top-level product |
| **target-scoped corpus** / **per-notebook SSOT selector** | “multi-profile Ask”, “auto router” |
| `desired corpus` (internal) / default inventory | Treating notebook content as SSOT |

Internal design notes may say “partition”; **CLI, describe, skills, and config docs should say notebook + selector.**

---

## 3. Architecture check (as of 2026-07-20)

### 3.1 Product layers (unchanged)

```text
Repo / git SSOT          = truth
NotebookLM               = derived knowledge provider (forward sync)
Beads                    = task provider
Repo fallback            = degraded read (not product_ready)
External advisor copies  = owner-manual only (not closeout gate)
Hetu (design)            = code-structure peer; NOT a second docs-ask
```

### 3.2 What Knowledge already has

| Capability | Status |
|---|---|
| `knowledge.notebooks.allow_list` + `default_alias` | Implemented |
| `--notebook <alias>` on most knowledge commands | Implemented |
| Per-target receipt / pending / ack / `sync_state` | Implemented (A synced ≠ B synced) |
| Ask hygiene / `provider_ask_clean` | Implemented (per probed target) |
| Ask template v3 + persona (“sources in **this** notebook”) | Implemented |
| Global corpus: registry statuses + `include_extra` − `exclude_globs` | Implemented |
| Closeout / `product_ready` knowledge half | Implemented **on `default_alias` only** |
| Scale: quota honesty, partial-continue, batch upload | Partially landed (see scale docs) |

### 3.3 Critical gap

```text
Targets are multi; corpus is singular.
build_desired_corpus(config) has no notebook_alias / ProviderTarget parameter.
Closeout sync uses notebook=None → default_alias with the SAME global desired set.
```

So today an agent can point sync/ask at notebook B, but Vibe still plans the **same** file set as for A — which fails isolation and worsens quota if they “just add notebooks.”

### 3.4 Implementation map (touch points if accepted)

| Area | Path | Today |
|---|---|---|
| Config validate | `src/vibe_control/config.py` | notebooks allow_list; no per-alias corpus |
| Notebooks | `src/vibe_control/knowledge/notebooks.py` | `NotebookEntry` without selector fields |
| Corpus | `src/vibe_control/knowledge/corpus.py` | `build_desired_corpus` global |
| Snapshot | `src/vibe_control/knowledge/snapshot.py` | `sync_scope="ssot_files"`; hash ignores target/selector |
| Target | `src/vibe_control/knowledge/provider_target.py` | alias + ref hash |
| Sync | `phase8_apply.py` / `phase8_runtime.py` | per-target ops, global desired |
| Query | `query_router.py` / `query_provenance.py` | one target; global corpus for provenance |
| Closeout | `closeout_runner.py` | default_alias only |
| Readiness | `product_readiness.py` / `integration.py` | default target probe |
| Self-explain | `describe.py`, skills | no multi-corpus guidance |

**Known footgun:** `Phase8Runtime.resolve_target` may prefer a cached default ref over `--notebook` on some runtime paths; sync CLI resolves alias directly. Any implementation must make **all** knowledge entrypoints honor `--notebook` consistently.

---

## 4. Worked example (agent-configured)

Suppose the consumer repo has ~200 SSOT files the agent groups as:

| Agent’s label (not Vibe’s) | Count | Agent-chosen alias | Agent-chosen selector (example) |
|---|---:|---|---|
| specs | 100 | `spec` | `path_prefixes: ["docs/specs/"]` |
| customer requirements | 50 | `requirements` | `path_prefixes: ["docs/requirements/"]` |
| eng docs | 30 | `dev` | `path_prefixes: ["docs/dev/"]` |
| ops | 20 | `ops` | `path_prefixes: ["docs/ops/"]` |

If later **specs alone** exceed a notebook cap or mix poorly, the agent may split `spec` → `spec-core` / `spec-api` with new prefixes. Vibe only validates config + enforces isolation.

**Illegal product behavior:** sync the full 200 into each of four notebooks.  
**Required product behavior:** each alias syncs only its effective desired set; ask always names one alias.

---

## 5. Proposed mechanism

### 5.1 Global default selector (unchanged)

```text
base_desired =
  specs.registry ∩ knowledge.authoritative_statuses
  ∪ knowledge.include_extra
  − knowledge.exclude_globs
```

Still the default for projects that use a single notebook.

### 5.2 Per-notebook optional selector (new)

Attach optional corpus fields on each `allow_list[]` entry (agent-filled):

```yaml
knowledge:
  provider: notebooklm
  fallback_provider: repo
  max_sources: 50          # soft guard; doctor also warns vs plan caps
  warn_sources: 40
  authoritative_statuses: [active]
  include_extra: []        # global extras
  exclude_globs: []

  notebooks:
    default_alias: spec
    allow_list:
      - alias: spec
        display_name: Specs
        ref_env: NOTEBOOKLM_NOTEBOOK_SPEC
        purpose: "Agent: primary MUST / formal specs"
        allowed_operations: [status, inventory, sync, query, doctor]
        # NEW (all optional):
        corpus_mode: inherit   # inherit | replace
        path_prefixes: ["docs/specs/"]
        include_extra: []      # union with global when inherit
        exclude_globs: []      # union with global when inherit

      - alias: requirements
        display_name: Requirements
        ref_env: NOTEBOOKLM_NOTEBOOK_REQ
        corpus_mode: inherit
        path_prefixes: ["docs/requirements/"]

      - alias: ops
        display_name: Ops
        ref_env: NOTEBOOKLM_NOTEBOOK_OPS
        corpus_mode: replace   # ignore global include/registry filter; use only local knobs
        include_extra:
          - docs/ops/RUNBOOK.md
        path_prefixes: ["docs/ops/"]
```

### 5.3 Effective corpus resolution

```text
resolve_desired_corpus(config, notebook_alias):

  entry = allow_list[alias]
  mode = entry.corpus_mode or "inherit"

  if mode == "replace":
    docs = registry_slice(entry) ∪ entry.include_extra − entry.exclude_globs
    # registry_slice: either empty unless entry sets authoritative_statuses override
    # v1 recommendation: replace uses ONLY entry.include_extra + path_prefixes filter
    #     on files that exist; do not silently re-pull full global registry
  else:  # inherit
    docs = build_desired_corpus(config)   # today’s global
    docs = docs ∪ entry.include_extra
    docs = docs − entry.exclude_globs

  if entry.path_prefixes is non-empty:
    docs = filter(docs, path startswith any prefix)

  enforce max_sources on THIS effective set (per target apply)
  return docs
```

**`corpus_mode` 人话（owner 2026-07-20 澄清）：**

`inherit` / `replace` 改的是 **「这本 notebook 用哪套规则算出要同步哪些 SSOT」**。  
**不是** 改仓库磁盘文件，也 **不是** 「要不要覆盖远端某一个已上传 source」  
（远端仍走现有 managed add / content-hash replace 生命周期）。

| 模式 | 人话 |
|---|---|
| `inherit`（默认） | 先按项目全局文档规则，再叠这本上的前缀 / 排除 / 额外文件 |
| `replace` | **不算**全局那套；这本只认自己写的 `include_extra` + `path_prefixes` + `exclude_globs` |

- Accepted: `replace` starts from `entry.include_extra` only, then applies `path_prefixes` / `exclude_globs`.
- Typical agent path: **`inherit` + `path_prefixes`** — no need to use `replace`.

**`inherit` + 旋钮全空：**

- Effective corpus == global ⇒ today’s behavior (compat; describe warns identical corpora across notebooks waste quota / do not isolate).

### 5.4 Snapshot / receipt identity

Today `snapshot_hash` uses `project_id` + `sync_scope="ssot_files"` + item hashes — **not** notebook/selector.

**Required change:**

```text
sync_scope = "ssot_files" | f"ssot_files:{notebook_alias}"   # or include corpus_fingerprint
corpus_fingerprint = hash({
  corpus_mode, path_prefixes, include_extra, exclude_globs, effective_doc_ids
})
desired_snapshot identity MUST differ when effective doc sets differ
receipt remains keyed by target_key_hash (already per notebook ref)
```

Never treat equal `snapshot_hash` across aliases as “same sync semantics” unless fingerprint proves same effective set.

### 5.5 `--notebook` resolution (owner: 2026-07-20)

Applies to **query / sync / inventory / status / doctor / cleanup-candidates** (and any other knowledge command that binds a ProviderTarget):

```text
allow_list length == 1  →  --notebook may be omitted; use that sole alias
allow_list length >= 2  →  --notebook is REQUIRED; omit → fail closed
                           (clear next_actions: pass --notebook <alias>)
```

Do **not** silently fall back to `default_alias` when multiple notebooks exist.
`default_alias` still matters for closeout / `product_ready` (which notebook is the product gate) — that is separate from “may omit `--notebook`.”

### 5.6 Ask / query

```text
# single notebook configured:
vibe knowledge query --question-file ... --json

# two or more notebooks configured:
vibe knowledge query --notebook <alias> --question-file ... --json
```

Rules:

1. Resolve `ProviderTarget` per §5.5 (sole alias, or required `--notebook`).
2. Require that target `sync_state=synced` for provider ask; else repo fallback **scoped to the same effective corpus** (not the global set if selectors differ).
3. Hygiene / `provider_ask_clean` evaluated for **that** target only.
4. Provenance maps citations via **that** target’s receipt + **that** effective corpus.
5. **Forbidden:** querying multiple notebooks in one command; merging answers; “search all allow_list.”

Persona text already says “sources in this notebook” — keep; optionally mention alias in wrapper metadata only (no new multi-profile Ask product).

### 5.7 Sync / inventory / doctor

| Command | Behavior |
|---|---|
| `sync --dry-run/--apply` (+ `--notebook` per §5.5) | Plan/apply using `resolve_desired_corpus(..., alias)` |
| `inventory` | List effective corpus for resolved alias (JSON: `notebook_alias` + selector summary) |
| `status` / `doctor` | Resolved target + that corpus’s snapshot/counts |
| `cleanup-candidates` | Orphans relative to that alias’s managed set only |

`max_sources` / `warn_sources`: apply to **effective** set per target. Doctor should surface Google plan-cap guidance (already partially present via `source_quota`).

### 5.8 Closeout / `product_ready`

**v1 recommendation (capability-minimal, agent-clear):**

```text
product_ready knowledge half + bounded closeout sync
  bind ONLY to default_alias’s effective corpus + that ProviderTarget.

Other allow_list notebooks are agent-managed side targets:
  sync/ask with --notebook; they do NOT gate product_ready unless
  a future explicit config flag is accepted (e.g. closeout_targets: [...]).
```

Rationale:

- Matches today’s closeout binding (default only).
- Avoids forcing “all four notebooks green” before implementation work.
- Agent that needs ops notebook current for an ops task uses `--notebook ops` explicitly; Gateway/prompt paths that need it must pass the alias (future prompt compose — out of scope unless accepted).

**Non-goal for v1:** auto-closeout every allow_list entry.

**Document clearly in describe:** `product_ready` ≠ “every notebook synced.”

### 5.9 Approval Matrix impact (owner: strict; mechanism by design)

| Op | Gate |
|---|---|
| Readonly status/query/inventory/doctor/`sync --dry-run` for any allow-listed alias | agent-autonomous |
| Bounded closeout `sync --apply` for **`default_alias` only** when dry-run is current-SSOT-bounded | agent-autonomous (existing class) |
| `sync --apply` when resolved alias **≠** `default_alias` | **fail closed** unless explicit confirm flag (below) |
| Adding/removing notebook aliases, `ref_env`, corpus selectors | provider config change → owner approval |
| Cross-notebook delete/clean | still forbidden / owner UI |

**Strict non-default apply (v1 mechanism — owner asked design to decide how):**

```text
vibe knowledge sync --apply --notebook <non-default> ...
  WITHOUT confirm  →  blocked envelope
       code: NON_DEFAULT_NOTEBOOK_APPLY_REQUIRES_CONFIRM
       mutation: true (proposed)
       next_actions: obtain owner approval, then re-run with
         --confirm-non-default-sync

vibe knowledge sync --apply --notebook <non-default> --confirm-non-default-sync
  →  allowed (same apply pipeline as today, target-scoped corpus)

Closeout run --apply  →  never syncs non-default aliases in v1
```

No env var dual-gate required for v1 (unlike Beads live apply). Confirm flag on the CLI is enough: agent cannot “accidentally” upload side notebooks; owner/task must explicitly allow the confirm flag.  
`--dry-run` for non-default remains agent-autonomous.

---

## 6. Self-explain / skills (required with capability)

When this ships, update — not as a taxonomy tutor, but as mechanism disclosure:

**`vibe describe --json` / skill `vibe-knowledge`:**

```text
Guidance (example copy):
- One notebook may be enough for small curated corpora.
- When source count approaches plan caps, or ask mixes unrelated domains,
  configure additional allow_list notebooks with per-notebook SSOT selectors
  (path_prefixes / include_extra / exclude_globs).
- With exactly one allow_list entry, --notebook may be omitted.
  With two or more, --notebook is required for sync/query/status/…
- Vibe does not choose categories; the agent decides aliases and selector values.
- Cross-notebook ask is not supported.
- product_ready tracks default_alias only.
```

Do **not** hardcode “create spec / requirements / dev / ops.”

---

## 7. Explicit non-goals

| Non-goal | Why |
|---|---|
| Cross-notebook ask / fan-out / answer merge | Isolation + provenance contract |
| Automatic notebook routing from question text | Agent owns judgment; avoid silent wrong target |
| Built-in domain taxonomy / scenario types | Deferred polish; not Vibe’s job |
| Multi-profile Ask templates as a product | Deferred 2026-07-17 |
| Replacing NotebookLM / adding parallel knowledge providers | Deferred |
| Splitting one logical MUST set across notebooks **as Vibe’s default advice without agent choice** | Anti-pattern from scale research |
| Temporal-style job platform | Scale foundation is separate |
| Hetu as docs-ask alternative | Hetu = code structure only |

---

## 8. Migration / compatibility

| Existing config | Behavior after change |
|---|---|
| No `notebooks` | Unchanged (repo-only / fixtures) |
| `notebooks` without per-entry corpus fields | Unchanged: all aliases share global desired (compat; describe warns) |
| Add selectors on some aliases | Only those aliases change effective sets |
| Switch `default_alias` | Closeout/`product_ready` follow new default; other receipts untouched |

Large selector changes ⇒ many replace ops ⇒ may exit **bounded** closeout → owner approval path (existing matrix).

---

## 9. Acceptance criteria (design-level)

1. Config validates optional per-`allow_list` corpus fields; unknown aliases still fail closed.
2. `build_desired_corpus` (or successor) is **target-scoped**; tests lock different aliases → different doc_id sets when selectors differ.
3. Snapshot identity includes corpus fingerprint / scoped sync_scope.
4. `query` with `--notebook A` never reads B’s sources; no API for multi-target ask.
5. Repo fallback for A uses A’s effective corpus.
6. Closeout/`product_ready` documented + tested for **default_alias only** (v1).
7. Describe/skill text includes guidance + non-goals above.
8. Fake-provider tests: multi-notebook different corpora; A synced ≠ B synced; ask isolation.
9. No raw notebook refs / source ids in JSON envelopes (existing redaction).
10. `--notebook` omit allowed iff `allow_list` length == 1; length >= 2 omit → fail closed.
11. `path_prefixes` is validated and applied in v1 effective-corpus resolution.
12. Non-default `sync --apply` without `--confirm-non-default-sync` fails closed with
    `NON_DEFAULT_NOTEBOOK_APPLY_REQUIRES_CONFIRM`.

---

## 10. Phased delivery (design accepted; impl pending)

| Phase | Scope | Mutation | Status |
|---|---|---|---|
| D0 | Accept design + DECISION_LOG + polish narrow exception | docs only | **done 2026-07-20** |
| D1 | Schema + `resolve_desired_corpus` + inventory/status/doctor readonly | none | **landed 2026-07-20** |
| D2 | Sync dry-run/apply + snapshot fingerprint + non-default confirm gate + tests | fake provider first | **landed 2026-07-20** |
| D3 | Query/provenance scoped + hygiene | fake + optional real readonly | **landed 2026-07-20** |
| D4 | Describe/skills/AGENTS guidance | docs | **landed 2026-07-20** (AGENTS pointer optional follow-up) |
| D5 | (Optional later) `closeout_targets` multi-default gate | separate accept | deferred |

Prefer `scripts/test-closeout-local-fast.sh` / full local readonly before claim.

---

## 11. Relation to prior decisions

| Prior | Relation |
|---|---|
| 2026-07-17 polish: no new K/T flagship | **Narrow exception accepted 2026-07-20** for target-scoped corpus only (this doc) |
| 2026-07-18 scale: multi-notebook sharding P2 | Pain now articulated (quantity + isolation); this is the product rule that research said was missing |
| Phase 8 multi-notebook sync state | Preserved and extended (corpus becomes per-target too) |
| Ask hygiene / SSOT ask contracts | Preserved; still one notebook per ask |
| Hetu | Unrelated; must not become docs multi-corpus |

---

## 12. Owner decisions (all locked 2026-07-20)

| Topic | Decision |
|---|---|
| Do this mechanism? | **Yes** — narrow exception to 2026-07-17 polish |
| `--notebook` omit | Only when `allow_list` length == 1; **2+ → required** |
| `path_prefixes` | **v1 first-class** |
| Non-default `sync --apply` | **Strict** — blocked unless `--confirm-non-default-sync`; closeout never applies non-default in v1 |
| `corpus_mode: replace` | Means **selector rules**, not “replace a file on disk”: ignore global corpus rules; only this entry’s `include_extra` + prefixes + excludes. Default path remains `inherit` + prefixes. |

### Implementation status

```text
Design: ACCEPTED
Code: D1–D4 landed 2026-07-20 (target-scoped corpus, --notebook multi rule,
      non-default confirm gate, describe/skill guidance). D5 still deferred.
```

Phased delivery §10: D0 = this accept + DECISION_LOG; D1–D4 = implement.

---

## 13. Summary for reviewers

**Do:** per-notebook SSOT selectors (incl. `path_prefixes`); single-target ask; require `--notebook` when 2+ notebooks; strict confirm for non-default apply; product_ready on `default_alias` only.  
**Don’t:** auto-route, cross-ask, invent domain categories, sync full global corpus into every notebook, silent default when multi-notebook.  
**Gap today:** multi-target plumbing exists; multi-corpus does not.
