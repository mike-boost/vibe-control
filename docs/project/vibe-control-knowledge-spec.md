# Vibe Control Knowledge Spec

**Document type:** Formal provider-layer spec (knowledge / NotebookLM)  
**Status:** v1.2 — aligned with Front/Core v0.10.0 product-interface contract
**Date:** 2026-07-16  
**Primary audience:** Coding agents, repository maintainers  
**Language policy:** Explanation in Chinese; code/commands/schemas in English.  
**Front/Core:** `docs/project/vibe-control-spec.md`  
**Companions:** `docs/project/vibe-control-task-spec.md`,
`docs/project/vibe-control-hetu-spec.md` (code-structure; design)

---

## 1. Role

```text
Repo / git SSOT (committed) = product truth
knowledge.provider          = exactly one of {local_fts, notebooklm} (derived)
  local_fts                 = SQLite FTS5 retrieval (path + line ranges; agent reasons)
  notebooklm                = optional synthesis ask provider
                             (sync reads repo SSOT / default inventory only)
Beads task cache            = task provider half of product closeout
External advisor context copies = owner-managed external copies only
                             (NOT repo state; NOT knowledge sync source;
                              NOT CLI-observable; NOT a product closeout gate)
Repo fallback               = degraded read when active provider not current (NOT product_ready)
```

Coding agents must not claim to observe or update external advisor context copies.

**Sync source rule:** NotebookLM `sync` reads fixed local repo SSOT files selected by
registry + `include_extra` (default inventory). It does **not** sync from external advisor
context copies. Copy freshness may affect external advisor context only and must not
affect `product_ready`, `closeout_complete`, `provider_sync_required`, or implementation
readiness.

---

## 2. Knowledge provider model

- Active provider is owner-explicit `knowledge.provider` ∈ `{local_fts, notebooklm}`.
- First adapters: `local_fts` (SQLite FTS5 retrieval) and NotebookLM CLI.
- Provider content is derived from selected local SSOT files.
- Forward-only sync: local fixed SSOT → provider index/sources. Never provider → repo SSOT recovery.
- `remote_ack` / local mirror = watermark only for notebooklm; local_fts uses index fingerprint meta.
- `status` / `query` / `doctor` / `inventory` / `cleanup-candidates` / `sync --dry-run` are readonly by default.

---

## 3. SSOT selection → desired_snapshot

Selection sources:

```text
specs.registry (authoritative_statuses, typically active)
+ knowledge.include_extra
- knowledge.exclude_globs
```

Current intended active formal specs (registry):

```text
vibe_control_spec           → docs/project/vibe-control-spec.md
vibe_control_knowledge_spec → docs/project/vibe-control-knowledge-spec.md
vibe_control_task_spec      → docs/project/vibe-control-task-spec.md
vibe_control_roadmap_state  → docs/project/vibe-control-roadmap-state.md
```

`include_extra` is empty by default. `DECISION_LOG.md` is optional decision history
(not current actionable state) and is not in default inventory / external advisor copy set.

`docs/project/sync/*.md` are phase/dev detail and **not** default knowledge sync content unless explicitly selected.

Config files are never sync content.

`desired_snapshot` = hashed selection for one ProviderTarget scope.

---

## 4. ProviderTarget / receipt / ack

```text
ProviderTarget     = notebook alias + auth profile scope (default allow-listed OPM-test)
Binding receipt    = per-doc provider_source_id bindings for that target
remote_ack         = watermark that target was verified to a snapshot
local_mirror       = local ack fallback when remote note unavailable
pending-sync       = retry marker when sync could not finish
```

Forbidden recovery:

```text
provider content → local SSOT files
provider ack → invent desired_snapshot
provider metadata → edit registry/config as truth
```

---

## 5. Sync states

`sync_state` values used by implementation JSON:

```text
synced
drift
pending
unavailable
target_mismatch
receipt_missing
```

Ask hygiene is **not** a `sync_state` value. It is reported separately via
`ask_hygiene.condition` and `provider_ask_clean` (boolean).

`provider_ask_clean` requires:

```text
sync_state=synced
AND required_updates_count=0
AND candidate_count=0
AND orphan_managed_count=0 (when probed)
```

Synced alone is insufficient if old sources remain as ask pollution.
When ask hygiene is not clean, reports must say `provider_ask_clean=false` (and the
`ask_hygiene.condition`), not invent `sync_state=ask_unclean`.

---

## 6. Query routing / ask hygiene

- Provider query only when synced + ask-clean (product path).
- Otherwise repo fallback / warn / next_actions (`mode=degraded` when evidence exists).
- Ask template (`vibe.knowledge.ask.v3`) wraps questions; NotebookLM persona carries durable policy; answers require Sources; provider citations enrich to repo `doc_id`/`path` when receipt-bound. See `docs/harness/knowledge-ask-ssot-contract.md`.
- `cleanup-candidates` lists orphan/duplicate/unmanaged guidance; never auto-deletes unmanaged.
- Broad notebook `clean` forbidden.
- Product/default delete path: only receipt-owned superseded managed sources after explicit
  replace flow (`sync --apply` / replace verify). Never unmanaged delete; never title-prefix wipe.
- Acceptance/test helpers may delete exact owner-approved titles for residue cleanup only.
  That helper path is **not** product/default behavior and must not be used by normal agent sync.

---

## 7. Forward-only apply lifecycle

```text
sync --dry-run  → plan only; mutation=false; status/query/doctor never hidden-mutate
sync --apply    → controlled mutation (--apply required)
                  during SSOT closeout: allowed without a second owner-approval ceremony
                  when dry-run is bounded to current active SSOT / default inventory
retry --apply   → explicit owner-approved retry of arbitrary pending provider state
```

Replace path for current SSOT: `replace_required` / add-new → wait → verify receipt → cleanup superseded managed (not orphan/unmanaged).

Do not sync unstable uncommitted drafts as product closeout input. Prefer committed local SSOT
with empty `git status --short` before provider apply.

Still require explicit owner approval for: unmanaged/orphan delete, broad cleanup, target/auth/config
changes, provider mutation outside current active SSOT/default inventory, destructive ops.

---

## 8. product_ready — knowledge half

Knowledge conditions for `product_ready=true`:

```text
knowledge_available=true
knowledge_target_ok=true
sync_state=synced
provider_ask_clean=true
```

Repo fallback never equals product_ready.

Task provider note: Beads default role is local_embedded_ephemeral task cache (see Task spec).
This Knowledge spec does not define team/shared Beads modes.

---

## 9. SSOT closeout — sync half

When Front/Core reports `provider_sync_required=true` after active SSOT / include_extra commit,
the knowledge half of product closeout is:

```text
1. Prefer vibe closeout run --dry-run --json
2. Sync dry-run is a driver-internal safety preflight (not an owner manual confirmation ceremony)
3. If the plan is limited to current active SSOT / default inventory expected updates:
     vibe closeout run --apply --json
     (bounded knowledge sync apply only; not blocked on external advisor context copies)
4. Driver re-checks integration status after apply
5. If task_cache_current=false: Beads convergence/reset is a separate closeout step
   (never auto-mutated by the closeout driver) before implementation greenlight
```

External advisor context copies are **not** a sync-half step. Owner refresh is optional and
orthogonal (§ Front/Core §10).

States (shared with Front/Core):

```text
no_ssot_change_product_ready
ssot_change_committed_sync_required
ssot_change_committed_sync_pending
ssot_change_committed_synced_product_ready
repo_only_degraded
```

`waiting_owner_project_sources` is not a knowledge/product closeout state.

If dry-run is not bounded or provider/target/auth issues appear: stop before mutation; report
next_actions; require explicit owner approval for any wider NotebookLM mutation.

---

## 10. Redaction

Committed reports / JSON must not include:

- raw notebook refs
- raw source IDs
- cookies / tokens / credentials / auth headers

---

## 11. Phase/dev specs

`docs/project/sync/*.md` and harness docs are implementation detail. They are not default
knowledge inventory entries and not the external advisor context copy set.
