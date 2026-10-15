# Knowledge scale research — NotebookLM-py + industry practice

**Status:** investigation / design input (not accepted product SSOT; not a greenlight)  
**Date:** 2026-07-18  
**Audience:** owner + coding agents  
**Purpose:** Answer how Vibe knowledge behaves at tens–hundreds of SSOT sources, what `notebooklm-py` actually provides, and what industry RAG/ingest practice implies for foundation hardening.

**Rules:** This note does not change runtime. It must not invent Phase 13 or new capabilities.

---

## 1. Executive verdict

```text
Vibe knowledge today is correct for small, curated corpora (dogfood ~2–20 sources).
It is NOT yet a scale-ready ingest product for 50–100+ sources under NotebookLM constraints.

Hard ceiling is primarily NotebookLM plan limits + sequential fail-stop sync,
not Python corpus building.

Industry best practice and notebooklm-py both point to the same next foundation work:
  inventory curation → idempotent micro-batch → partial continue + DLQ → reconcile proof
— not “raise max_sources and pray.”
```

---

## 2. Evidence: current Vibe Control behavior

| Mechanism | Behavior | Scale implication |
|---|---|---|
| Desired corpus | registry `active` + `include_extra`; missing files → warning | Selection matters more than raw count |
| `max_sources` / `warn_sources` | Default 100 / 80; dogfood config **20 / 15**; at max → `SOURCE_LIMIT_EXCEEDED` | Soft product guard; not provider-aware |
| Sync apply | Per-doc: skip if hash match; else replace/add → **wait (~120s)** → receipt | Latency ≈ O(changed docs × wait) |
| Failure | **Stop on first failure**; write `pending-sync`; `retry` continues from latest desired | No “skip bad, finish rest” product path |
| Query path | Prefer NotebookLM when synced+ask-clean; else repo fallback | Large corpora: answer quality/latency owned by provider |
| Identity | `doc_id` + content hash + managed name / upload filename | Aligns with industry idempotent upsert idea |

**Dogfood fact:** `.config/vibe-control.yaml` uses `max_sources: 20`. Product has not been exercised as a 100-source system.

---

## 3. Evidence: notebooklm-py (CLI we depend on)

Installed local CLI observed: `NotebookLM CLI, version 0.8.0a3`.

### 3.1 What it gives us (useful for scale)

From `/teng-lin/notebooklm-py` docs (Context7):

| Capability | Detail | Relevance to Vibe |
|---|---|---|
| Bulk import workflow | Repeated `source add`; CLI **does not enforce** plan source caps | Vibe must enforce / detect caps itself |
| Parallel wait API | `wait_for_sources(nb_id, ids, timeout=…)` | Vibe currently waits **one source at a time** via CLI |
| Rate-limit helpers | HTTP 429 retries; artifact `with_rate_limit_retry` | Artifact-oriented; source upload still needs our own pacing |
| Upload timeout | `upload_timeout` separable from global HTTP timeout | Large files OK; many files still sequential in our adapter |
| Source ops | add / wait / list / get / fulltext / clean / delete / rename | Matches our Phase 8 lifecycle surface |

### 3.2 What it does **not** solve for us

```text
- No durable job queue / checkpoint across process crashes
- No partial-batch “continue after one failure” product semantics in our adapter
- No automatic enforcement of Google per-notebook source quotas
- Ask quality at 100+ sources is still Google retrieval — not guaranteed by CLI
```

### 3.3 Google NotebookLM hard limits (plan-dependent; subject to change)

Public Google help / 2026 plan tables (verify on the live account before shipping scale claims):

| Tier (approx.) | Sources / notebook |
|---|---|
| Standard (free) | **50** |
| Plus | **100** |
| Pro | **300** |
| Ultra | **500–600** |

Also: ~**500k words or 200MB per source** (all plans). Daily chat quotas apply separately.

**Implication for Vibe:**

```text
“Hundreds of SSOT docs in one notebook” is only feasible on higher plans.
Free/Standard cannot hold 100 sources in one notebook.
Raising Vibe max_sources above the account’s notebook cap is a false greenlight.
```

Our current default `max_sources=100` already exceeds Standard’s 50 — a **config/product mismatch** worth fixing as foundation hygiene.

---

## 4. Industry best practice (RAG / knowledge ingest)

Sources consulted (patterns, not dependencies): durable RAG ingest (Temporal-style activities), Unstructured ingest-at-scale guidance, RAG drift/reconciliation practice, commercial KB migrate guides.

### 4.1 Pattern → Vibe mapping

| Industry practice | Meaning | Vibe today | Gap |
|---|---|---|---|
| **Curated inventory / tiers** | Hot vs warm vs archive; not everything in one index | registry + statuses + exclude_globs | Need explicit “product inventory vs archive” guidance for consumers |
| **Stable IDs + content hash** | Idempotent upsert; retry safe | `doc_id` + `content_sha256` + receipt | Strong — keep |
| **Micro-batch + throttle** | Avoid burst → 429; sequential or small concurrency | Fully sequential CLI add+wait | OK for small N; need paced batches + optional parallel wait |
| **Partial failure + DLQ** | One bad file must not kill whole job | Fail-stop + pending-sync | Need per-item fail record + continue policy (owner-accepted) |
| **Checkpoint / durable progress** | Crash mid-run resume | receipt + pending-sync (partial) | Good seed; not full batch job model |
| **Reconcile / drift proof** | Compare desired vs remote; challenge queries | status / ask hygiene / dry-run plan | Keep; add scale metrics (counts, p50 wait, fail codes) |
| **Supersede cleanly** | Old versions must not pollute retrieval | managed replace + cleanup superseded | Aligns; orphan/unmanaged still manual |
| **Provider quota awareness** | Know ceiling before apply | Not wired to NotebookLM plan | Detect/report notebook source count vs configured max |

### 4.2 Anti-patterns to avoid

```text
- “Just raise max_sources to 500”
- Parallel hammering source add without backoff
- Treating sync --apply success as Ask quality proof
- Splitting one logical SSOT across many notebooks without a product rule (multi-notebook is a major design)
- Building a Temporal clone before inventory + partial-continue + quota awareness
```

---

## 5. Gap matrix (scientific priority)

| Gap | Agent / owner pain if ignored | Foundation priority |
|---|---|---|
| `max_sources` vs NotebookLM plan mismatch | Apply fails late / opaque provider errors | **P0 docs + doctor warning** |
| Sequential wait per source | 50 changes ≈ hours of wall time | **P1** paced batch + multi-wait if CLI allows |
| Fail-stop only | One corrupt file blocks closeout of 99 good docs | **P1** partial continue + itemized failures (gated) |
| No scale metrics in status | Cannot prove “sync is healthy at N” | **P1** counts / durations / fail codes in JSON |
| Ask quality at large N | Agent implements from wrong/missing MUST | **P2** ask contract regression on real large inventory |
| Multi-notebook sharding | Only path past ~50–100 on lower plans | **P2 design only** until pain proven |

---

## 6. Recommended foundation slices (not accepted yet)

Keep inside **knowledge hardening** (owner direction: knowledge + task first). No new capability catalog.

| Slice | Mutation | Outcome | Status |
|---|---|---|---|
| A. Quota & config honesty | docs + doctor/status readonly | Surface plan-cap reference; warn when `max_sources` > Standard 50; defaults 50/40 | **Landed 2026-07-18** (`source_quota.py`, doctor/status `source_quota`) |
| B. Scale observability | readonly JSON fields | `desired_count`, apply duration / fail codes | **Landed 2026-07-18** (`scale_observability.py`; status/dry-run `scale`; apply `last-sync-report.json`) |
| C. Partial-continue design | docs/tests first | Spec: continue after non-fatal item failure; DLQ list | **Landed + wired 2026-07-18** (`--continue-on-item-error`, per-item receipt checkpoint, `item_failures` DLQ; default fail_stop) |
| D. Batch apply (bounded) | design → later gated apply | Micro-batch; optional multi-wait; pacing | **Landed 2026-07-18** (`--batch-size`, `--wait-mode multi`; default batch_size=1 serial; in-process multi-wait) |
| E. Large-inventory Ask harness | tests + fixtures | Contract regression with N≫dogfood | **Landed 2026-07-18** (`test_large_inventory_ask_harness.py`, Ask SSOT scenario S7) |
| F. Agent-surface disclosure | foundation TDD | Self-explanatory policy on status/dry-run/help | **Landed 2026-07-18** (`agent_surface.py`, disclosure contract) |

**Do not skip A/B for D.** Industry order is: know the ceiling → observe → then parallelize.

---

## 7. Relation to owner product direction

```text
1) Harden knowledge/task     ← this note is for knowledge scale
2) Maintainable product arch ← quota honesty + observability + contracts
3) New capabilities only with proven agent lift ← deferred (sdd/tdd still not justified)
```

Skill/provider governance reports remain **out of scope** here.

---

## 8. Measured baseline (2026-07-18)

Readonly entry: `scripts/measure-knowledge-sync-scale.sh`  
Live apply measure (owner-authorized): ephemeral project
`~/Documents/tmp/vibe-scale-se` using Standard Ebooks public-domain
corpus `~/Documents/tmp/dataset-200kb` (60 × ~100–200KB markdown).

Target notebook: **OPM-test** (pre-existing 4 vibe-control managed sources).  
Flags: `--continue-on-item-error --batch-size 5 --wait-mode multi`.  
Project id: `vibe-scale-se` (managed titles do not collide with vibe-control SSOT).

| Run | Desired N | New uploads this run | Wall ms | Apply `elapsed_ms` | Batches | Failures | Result |
|---|---:|---:|---:|---:|---:|---:|---|
| n10 | 10 | 10 | **93957** (~1.6 min) | 90628 | 2 | 0 | ok |
| n20 | 20 | 10 | **94846** (~1.6 min) | 88234 | 2 | 0 | ok |
| n40 | 40 | 20 | **192262** (~3.2 min) | 185026 | 4 | 0 | ok |

Observations:

- Effective throughput ≈ **9–10 s per new ~150–200KB source** with batch=5 + multi-wait
  (not O(N×120s) serial worst-case).
- Checkpoint/idempotency worked: n20/n40 only attempted the new deltas
  (`updated_or_attempted` = 10 / 20).
- After n40: remote source count **44** (= 4 prior vibe-control + 40 SE).
- `notebooklm source wait` remains **single-id**; multi is in-process coalescing.
- Account plan still not read from Google UI; **Standard 50** not exceeded (44/50).
- N=50 full greenfield not run (would push OPM-test over Standard if prior 4 remain).

Raw JSON: `~/Documents/tmp/vibe-scale-measure-results/n{10,20,40}-summary.json`

**Cleanup (2026-07-18 later):** deleted all 40 `vibe__vibe-scale-se__*` sources from
OPM-test (4 vibe-control sources remain). See throughput strategy note for why
these timings are **not** accepted as an optimized baseline.

**Follow-up:** `docs/project/sync/20260718-knowledge-sync-throughput-strategy.md`
(diagnosis: uploads were still serial CLI; only waits were concurrent).

---

## 9. Smallest safe next action

```text
1) Decide whether to leave SE sources on OPM-test or owner-clean them
   (managed prefix vibe__vibe-scale-se__…).
2) Optional: measure serial batch_size=1 on a small N for comparison.
3) Optional: confirm Google account plan tier in UI.
Do not claim 100-source readiness — Standard ceiling and Ask quality at N=40
are still separate questions.
```

---

## 10. References (external; not dependencies)

- notebooklm-py docs / SKILL bulk import + sources API (teng-lin/notebooklm-py via Context7)
- Google Gemini Notebook usage limits help (sources per notebook by plan)
- Industry: durable RAG ingest (idempotent activities, backoff), Unstructured ingest-at-scale, RAG index drift reconciliation guidance
