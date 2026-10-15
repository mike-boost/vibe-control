# Spec — Knowledge local FTS provider (SQLite FTS5)

**Status:** Accepted (2026-07-21) — shipped in package `0.5.12` / tag `v0.5.12`  
**Date:** 2026-07-21  
**Document type:** Implementation-ready Knowledge provider spec  
**Audience:** owner + coding agents  
**Language:** Explanation in Chinese where helpful; schemas / commands / field names in English.

**Related:**

- Front/Core: `docs/project/vibe-control-spec.md` (§ Knowledge provider selection)
- Review: `docs/project/sync/20260721-knowledge-local-fts-provider-review.md`
- Knowledge: `docs/project/vibe-control-knowledge-spec.md`
- Ask: `docs/harness/knowledge-ask-ssot-contract.md`, `docs/harness/knowledge-ask-hygiene-contract.md`
- Provider boundary: `docs/harness/knowledge-provider-boundary.md`
- Polish stance: `docs/project/sync/20260717-knowledge-task-polish-strategy.md`
- Multi-notebook: `docs/project/sync/20260720-knowledge-multi-notebook-corpus-design.md`
- Index: `docs/project/PRODUCT_THINKING_INDEX.md`

**Owner review gate:** Accepted with review amendments (P1/P2 + C1–C5 + trigram+LIKE).

---

## 0. One-line verdict

```text
Add knowledge.provider=local_fts (SQLite FTS5) as the zero-cost Knowledge base:
  - index desired corpus into heading/section chunks with line_start/line_end
  - query returns ranked evidence (path + line range + excerpt + score)
  - coding agent reasons and fills Facts/MUST/Uncertainty (A+B)
  - NotebookLM remains an optional synthesis provider (not required for product_ready
    when active provider is local_fts)
  - keyword repo_provider remains last-resort degraded fallback only
```

This is a **mechanism-level** Knowledge extension (accessibility: not everyone has NotebookLM; users do not want paid cloud RAG). It is a narrow, accepted-direction exception to the 2026-07-17 “no new Knowledge flagship” stance — scoped to **local retrieval provider**, not FAQ cache, multi-profile Ask, or cloud RAG.

---

## 1. Problem

1. NotebookLM is not universally available (account / region / org policy).
2. Cloud File Search / OpenAI vector stores require purchase or API spend — rejected for default path.
3. Current `repo` fallback is keyword-only, marked **degraded**, and **never** `product_ready`.
4. Agents need **navigable evidence** (`path` + **line range**), then reason themselves — not another paid synthesizer.

---

## 2. Decisions locked (for review)

| ID | Decision | Value |
|---|---|---|
| D1 | Default free Knowledge engine | **SQLite FTS5** (stdlib; no daemon; no purchase) |
| D2 | Index granularity | **Heading/section chunks** with exact `line_start` / `line_end` (1-based, inclusive) |
| D3 | Query product shape | **Retrieval-only**: return evidence; Vibe does **not** call a local LLM to synthesize Facts/MUST |
| D4 | Agent answer shape | Envelope includes `answer_mode=evidence_retrieval` + short machine summary; agent fills ask template sections from evidence (A+B) |
| D5 | Active provider model | **Exactly one** `knowledge.provider` active; no dual-ask fan-out |
| D6 | NotebookLM role | Optional when `knowledge.provider=notebooklm`; not required for local_fts `product_ready` |
| D7 | `repo` role | `fallback_provider` / emergency only; remains non-`product_ready` |
| D8 | DuckDB / Redis / Meili / Valkey | **Out of v1**; may be future optional providers; not default |
| D9 | Closeout for local_fts | `vibe closeout run --apply` rebuilds local index (no NotebookLM mutation) |
| D10 | Config migration | Existing `provider: notebooklm` keeps working; templates / init recommend `local_fts` |
| D11 | Provider selection (P1) | Owner-explicit `knowledge.provider`; no auto-switch; see Front/Core |
| D12 | Tokenizer (C2) | **trigram** + LIKE fallback for short/CJK terms; probe FTS5 at doctor |
| D13 | Line numbers (C1) | `text.split("\n")` 1-based inclusive; align with Read tool |
| D14 | Scope key (C4) | Reuse `sync_scope_for_corpus` (+ filesystem-safe form); fingerprint via `DesiredSnapshot.snapshot_hash` + `chunking_version` |
| D15 | pending (C5) | local_fts v1 **never** emits `pending`; atomic rebuild transaction only |

If review changes any Di, update this table before Accept.

---

## 3. Product principles

| Principle | Meaning |
|---|---|
| Repo SSOT remains truth | local_fts indexes committed/desired corpus files; never recovers SSOT from index |
| Forward-only sync | sync = (re)build local index from desired corpus |
| Evidence > synthesis for free path | Precise coordinates beat chatty answers without provenance |
| Provider boundary | SQLite quirks stay in `local_fts` adapter; skills stay thin |
| Fail closed | Missing/stale/corrupt index → not `provider_ask_clean`; do not fake green |
| Thin CLI | Mechanics in Engine; Gateway/skills only route |

---

## 4. Provider roles (after this spec)

```text
knowledge.provider=local_fts     → default free path; can satisfy knowledge half of product_ready
knowledge.provider=notebooklm    → optional derived ask/synthesis; existing behavior
knowledge.fallback_provider=repo → degraded keyword only; NEVER product_ready alone
```

| Capability | local_fts | notebooklm | repo fallback |
|---|---|---|---|
| Zero purchase | yes | NLM account | yes |
| Daemon | no | external CLI/auth | no |
| Line ranges | **yes (MUST)** | no (must not invent) | weak / none |
| LLM synthesis | no | yes | no |
| `product_ready` knowledge half | **yes when index clean** | yes when synced+ask-clean | **no** |

---

## 5. Architecture

```text
DesiredCorpus (registry + include_extra - exclude_globs [+ notebook selectors])
        │
        ▼
local_fts sync/rebuild ──► SQLite file (FTS5 chunks + meta)
        │
        ▼
vibe knowledge query ──► ranked chunk hits (path, lines, excerpt, score)
        │
        ▼
Coding agent reads cited ranges (Read tool) + fills Facts/MUST/Uncertainty
```

### Module ownership (implement here)

| Module | Responsibility |
|---|---|
| `src/vibe_control/knowledge/local_fts/chunking.py` | Markdown → chunks with line ranges |
| `src/vibe_control/knowledge/local_fts/store.py` | SQLite open/migrate/rebuild/query |
| `src/vibe_control/knowledge/local_fts/provider.py` | `LocalFtsProvider` adapter (status/sync/query/doctor) |
| `src/vibe_control/knowledge/local_fts/fingerprint.py` | Corpus + index fingerprint |
| `src/vibe_control/knowledge/query_router.py` | Route by active provider + sync_state |
| `src/vibe_control/knowledge/ask_hygiene.py` | local_fts clean rules (no remote orphans) |
| `src/vibe_control/integration.py` / product readiness | Knowledge half for local_fts |
| `src/vibe_control/config.py` | Allow `provider: local_fts` |
| Skills / `describe` | Document local_fts as free default option |

Do **not** put FTS SQL in skills.

---

## 6. Index design (MUST)

### 6.1 Storage path

```text
~/.agents/state/vibe-control/{project_id}/local_fts/{corpus_scope_key}/index.sqlite
```

- State root matches receipts/acks (`_state_root` under `~/.agents/state/vibe-control`).
- `corpus_scope_key`: filesystem-safe form of `sync_scope_for_corpus(...)`
  (e.g. `ssot_files` or `ssot_files_OPM-test` — replace `:` / `/` with `_`)
- File is **generated runtime state** — never commit `index.sqlite`.
- Stale scopes / `*.sqlite.tmp` are purged via `vibe knowledge fts-purge` (not auto-deleted on sync).

### 6.2 SQLite schema (v1)

```sql
PRAGMA user_version = 1;

CREATE TABLE meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

-- meta keys (required):
--   schema_version = "1"
--   provider = "local_fts"
--   project_id
--   corpus_scope_key
--   desired_fingerprint   -- hash of desired corpus doc_id+path+content_sha256
--   built_at_iso
--   chunking_version = "heading_v1"

CREATE TABLE documents (
  doc_id TEXT PRIMARY KEY,
  path TEXT NOT NULL,
  title TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  status TEXT NOT NULL,
  kind TEXT NOT NULL
);

CREATE VIRTUAL TABLE chunks USING fts5(
  chunk_id UNINDEXED,
  doc_id UNINDEXED,
  path UNINDEXED,
  title UNINDEXED,
  heading UNINDEXED,
  line_start UNINDEXED,   -- 1-based inclusive
  line_end UNINDEXED,     -- 1-based inclusive
  body,                   -- indexed text
  tokenize = 'trigram'
);
```

**Notes:**

- FTS5 has no native line numbers; line ranges are **UNINDEXED metadata** on each chunk row.
- Rebuild is full replace (transaction: clear → insert → update meta). No incremental patch in v1.
- `user_version` / `schema_version` mismatch → treat index as `drift` and require rebuild.

### 6.3 Chunking algorithm `heading_v1` (normative)

Input: UTF-8 text of one corpus file; path; doc_id.

1. Split file with **`text.split("\n")`** (NOT `splitlines()`). Line numbers are
   **1-based inclusive** and MUST align with Cursor/agent `Read` tool line numbering.
   Tests MUST cover: trailing newline, `\r\n` endings (normalize `\r\n`→`\n` before split),
   and form-feed/`\v` **not** treated as line breaks.
2. Detect ATX headings: line matching `^(#{1,6})\s+.+`.
3. Emit chunks:
   - **Preamble chunk** (if any non-empty content before first heading): heading=`""` or `"(preamble)"`, lines `1..H-1`.
   - **Section chunk** for each heading: from heading line through line before next heading of **same or higher level** (ATX level `#` count), or EOF.
4. Skip empty chunks (only whitespace).
5. If a section exceeds **120 lines**, split into windows of **80 lines** with **16-line overlap**; each window keeps same `heading`, updates `line_start`/`line_end`.
6. `chunk_id` = `sha256(doc_id + "\n" + line_start + "\n" + line_end + "\n" + heading)[:16]` hex.
7. `body` = exact source slice for those lines joined by `\n` (no rewriting).

**Non-markdown files** in corpus (rare): treat whole file as one chunk; if `>120` lines, use same window split with heading=`""`.

### 6.4 Desired fingerprint

Reuse `DesiredSnapshot.snapshot_hash` from `snapshot.py` for the corpus half, then bind
chunking:

```text
index_fingerprint_payload = {
  "snapshot_hash": desired.snapshot_hash,
  "chunking_version": "heading_v1",
  "tokenizer": "trigram",
}
desired_fingerprint = sha256_hex(canonical_json(index_fingerprint_payload))
```

Store as `meta.desired_fingerprint`. Index matches when equal to current rebuild input.

---

## 7. Sync / status semantics (local_fts)

Reuse existing `sync_state` vocabulary where possible:

| State | Meaning for local_fts |
|---|---|
| `synced` | Index exists, schema ok, `desired_fingerprint` matches corpus |
| `drift` | Index missing fingerprint mismatch (SSOT/corpus changed) or chunking_version changed |
| `pending` | **Unused in local_fts v1** — rebuild is a single SQLite transaction; crash leaves prior index or incomplete file treated as `drift`/`unavailable`, never NLM-style pending-sync.json |
| `receipt_missing` | **Not used** for local_fts (no remote receipt). Map absence of index → `drift` |
| `target_mismatch` | **Not used** for local_fts v1. Wrong scope key / corrupt meta → `drift` or `unavailable` |

### 7.1 Ask hygiene for local_fts

```text
provider_ask_clean = true iff
  sync_state == "synced"
  AND index readable
  AND documents.count == desired_corpus.documents.count
  AND required_updates_count == 0
```

- `required_updates_count`: `0` when fingerprints match; else `1` (rebuild required).
- Remote-only concepts (`cleanup-candidates` orphans, `orphan_managed_count`) are **N/A**: report `candidate_count=0`, `orphan_managed_count=0`, `ask_hygiene.condition=clean|rebuild_required|unavailable` with reasons that do not mention NotebookLM UI delete.

### 7.2 CLI sync behavior

| Command | local_fts behavior |
|---|---|
| `vibe knowledge sync --dry-run --json` | Compute fingerprint diff; plan `rebuild_index` op; `mutation=false` |
| `vibe knowledge sync --apply --json` | Rebuild SQLite index; no network |
| `vibe knowledge retry --apply --json` | Same as sync apply for local_fts (idempotent rebuild) |
| `vibe knowledge fts-purge --dry-run/--apply` | Delete orphan scopes + `*.sqlite.tmp` only; `--all --confirm-all` wipes project `local_fts/` |
| `vibe knowledge cleanup-candidates` | Lists local_fts garbage (points to fts-purge); not NLM orphan model |
| `vibe knowledge remote-inventory` | N/A envelope → inventory / fts-purge |
| `vibe closeout run --dry-run/--apply` | Knowledge half uses local rebuild when active provider is local_fts; **must not** call NotebookLM |

Approval matrix: local_fts rebuild is **local_runtime_write** (like grill session), allowed under existing closeout/local apply gates — **not** `knowledge_provider_mutation` remote class. Document in describe/mutation surfaces.

---

## 8. Query contract

### 8.1 Routing

In `route_knowledge_query`:

1. Load config; read `knowledge.provider`.
2. If `provider == "local_fts"`:
   - Resolve status via `LocalFtsProvider.status`.
   - If `provider_ask_clean`: run `LocalFtsProvider.query`.
   - Else: do **not** silently use keyword repo as if clean; return envelope with `mode=degraded` or `blocked`, `next_actions` including rebuild (`vibe knowledge sync --apply --json` or closeout), and optionally include weak repo hits under `data.fallback_sources` with warning — **default v1: no silent keyword merge**; only rebuild guidance. (Simpler, fail-closed.)
3. If `provider == "notebooklm"`: keep existing Phase 10 router (synced → NLM; else repo fallback).
4. Unknown provider → structured error.

**v1 fail-closed query rule (normative):** when local_fts is active but not clean, query returns `ok=true` with `data.mode="degraded"`, empty `sources` or status-only, and `next_actions` to rebuild — do not pretend keyword hits are local_fts evidence.

### 8.2 Query algorithm

1. Tokenize question: reuse/adapt `repo_provider.tokenize_question` (stopwords, len>2).
2. Build FTS5 MATCH query: join tokens with `OR` (v1). If no tokens → no hits.
3. SQL:

```sql
SELECT chunk_id, doc_id, path, title, heading,
       line_start, line_end, body,
       bm25(chunks) AS score,
       snippet(chunks, 7, '>>>', '<<<', ' … ', 32) AS excerpt
FROM chunks
WHERE chunks MATCH ?
ORDER BY rank
LIMIT :top_k;
```

4. Default `top_k=8` (config override `knowledge.local_fts.top_k`, clamp 1..20).
5. Deduplicate by `(doc_id, line_start, line_end)`; keep best score.
6. Optionally merge adjacent hits in same doc if ranges overlap or gap ≤ 2 lines (v1: **yes**, merge for agent readability).

### 8.3 Envelope fields (normative additions)

Successful local_fts query `data` MUST include:

```json
{
  "provider": "local_fts",
  "answer_mode": "evidence_retrieval",
  "mode": "provider",
  "question": "...",
  "answer": "Found N evidence chunk(s). Agent must read cited line ranges and fill Facts/Constraints/MUST/Uncertainty. Vibe did not synthesize policy.",
  "sources": [
    {
      "doc_id": "vibe_control_spec",
      "path": "docs/project/vibe-control-spec.md",
      "title": "Vibe Control Spec",
      "heading": "Approval Matrix",
      "line_start": 120,
      "line_end": 145,
      "excerpt": "… >>>approval<<< …",
      "score": -3.21,
      "matched_terms": ["approval"],
      "chunk_id": "a1b2c3d4e5f67890"
    }
  ],
  "ask_template_id": "vibe.knowledge.ask.v3",
  "ask_template_version": "...",
  "provider_ask_clean": true,
  "sync_state": "synced",
  "index": {
    "path_redacted": true,
    "desired_fingerprint": "sha256:…",
    "chunking_version": "heading_v1",
    "chunk_count": 42,
    "document_count": 4
  }
}
```

**Agent rules (document in skill + ask contract addendum):**

1. Treat `sources[]` as evidence coordinates.
2. Prefer `Read(path)` focusing on `line_start..line_end` before claiming Facts/MUST.
3. Fill Facts/Constraints/MUST/Sources/Uncertainty in agent reasoning (or user-facing reply); Vibe `answer` string is **not** the policy oracle.
4. If no sources → Uncertainty: `Evidence insufficient`; `CHECK_CORPUS_INVENTORY`.

Update `docs/harness/knowledge-ask-ssot-contract.md` § envelope provenance:

- local_fts: `doc_id`, `path`, `title`, `heading`, `line_start`, `line_end`, `excerpt`, `score`, `matched_terms`, `chunk_id`.

Unlike NotebookLM path: **line numbers are allowed and required** when provider is local_fts.

---

## 9. Config

### 9.1 Schema

```yaml
knowledge:
  provider: local_fts          # or notebooklm
  fallback_provider: repo
  local_fts:
    top_k: 8                   # optional, default 8
    chunking_version: heading_v1  # optional; only heading_v1 supported in v1
  # existing fields unchanged: max_sources, notebooks, include_extra, ...
```

Validation:

- `provider` ∈ `{local_fts, notebooklm}` (v1). Reject others with clear error.
- If `provider=local_fts`, `knowledge.notebooks` MAY remain for future/optional NLM switch but is **not required** for doctor green on local_fts.
- Doctor for local_fts: do not fail solely because NotebookLM binary/auth missing.

### 9.2 Init / templates

- `vibe knowledge init-preview` / install templates: recommend `provider: local_fts`.
- This dogfood repo may keep `notebooklm` until owner switches; no forced migration in v1 implement PR unless owner asks.

### 9.3 Capability profile

- `components.knowledge.enabled=true` still gates Knowledge.
- Disabled knowledge → local_fts not probed (same as today).

---

## 10. Doctor / status / describe

### 10.1 `vibe knowledge doctor --json` (local_fts)

Must report:

```json
{
  "provider": {
    "configured": true,
    "name": "local_fts",
    "adapter_import": {"ok": true, "module": "vibe_control.knowledge.local_fts.provider"}
  },
  "local_fts": {
    "index_exists": true,
    "schema_ok": true,
    "sync_state": "synced",
    "desired_fingerprint": "sha256:…",
    "index_fingerprint": "sha256:…",
    "document_count": 4,
    "chunk_count": 42,
    "chunking_version": "heading_v1"
  },
  "auth": {"auth_state": "not_applicable", "message": "local_fts requires no remote auth"}
}
```

### 10.2 `vibe knowledge status --json`

Same sync_state / ask_hygiene fields as today, filled by local_fts rules.

### 10.3 `vibe describe --json`

Authority map MUST say:

- `local_fts`: default-capable free derived retrieval index; not SSOT
- `notebooklm`: optional derived synthesis provider
- `repo`: degraded fallback only

Add surface guidance key `knowledge_local_fts_guidance` (short): when to use local_fts vs notebooklm; query returns line ranges; agent must reason.

---

## 11. product_ready / closeout

### 11.1 Knowledge half when `provider=local_fts`

```text
knowledge_available = adapter import ok + home writable + corpus buildable
knowledge_target_ok = true   # no notebook target required
sync_state = synced
provider_ask_clean = true    # §7.1
```

Repo fallback alone still never sets knowledge half green.

### 11.2 Closeout

When active provider is local_fts:

1. `provider_sync_required` after SSOT change means **local index rebuild required**, not NLM upload.
2. `vibe closeout run --apply` may rebuild local index under bounded closeout rules (clean git, desired inventory only) — **no** NotebookLM `source add/delete`.
3. ChatGPT Project Sources remain non-gates (unchanged).

### 11.3 Formal spec doc updates (same landing PR or immediate follow-up)

MUST update after Accept+impl:

- `docs/project/vibe-control-knowledge-spec.md` — provider model includes local_fts
- `docs/project/vibe-control-spec.md` — product_ready knowledge half wording
- `docs/harness/knowledge-provider-boundary.md` — local_fts owns SQLite/chunking
- `docs/harness/knowledge-ask-ssot-contract.md` — local_fts sources + line ranges
- `docs/harness/knowledge-ask-hygiene-contract.md` — local clean rules
- `docs/project/PRODUCT_THINKING_INDEX.md` — link this spec as Accepted
- `docs/project/sync/20260717-knowledge-task-polish-strategy.md` — note exception landed
- Skills: `vibe-knowledge` routing table row for local_fts

---

## 12. Non-goals (v1)

- Local LLM / DuckDB / Redis / Meili / Valkey / ParadeDB / SurrealDB adapters
- Embedding / vector / hybrid search
- Incremental chunk updates without full rebuild
- Cross-notebook ask
- Treating index as SSOT or writing back to markdown
- Silent dual-ask (local_fts + notebooklm in one query)
- Guaranteeing semantic paraphrase recall equal to NotebookLM
- Committing `index.sqlite` into git
- Changing Beads / Hetu

---

## 13. Implementation slices (ordered, TDD)

Implement only after **Status: Accepted**. Each slice: failing tests → code → green.

### Slice A — Chunking pure functions

**Tests:** `tests/test_local_fts_chunking.py`

- Heading split produces correct line_start/line_end
- Preamble handled
- Nested heading boundaries (H2 stops at next H2, not H3)
- Long section window split 80/16 overlap
- Empty file → no chunks
- Non-md whole-file + window

**Code:** `local_fts/chunking.py`

### Slice B — Store rebuild + fingerprint

**Tests:** `tests/test_local_fts_store.py`

- Rebuild creates schema + meta fingerprint
- Second rebuild idempotent same fingerprint
- Corpus content change → fingerprint change → status drift
- Query BM25 returns expected doc for planted term
- Returns line_start/line_end matching fixture

**Code:** `local_fts/store.py`, `fingerprint.py`

### Slice C — Provider adapter + config

**Tests:** `tests/test_local_fts_provider.py`

- `provider=local_fts` validates
- status synced/drift/unavailable
- sync --dry-run / --apply envelopes (`mutation` flags correct)
- doctor auth_state `not_applicable`

**Code:** `local_fts/provider.py`, `config.py` validation

### Slice D — Query router + ask hygiene + product_ready

**Tests:** `tests/test_local_fts_query_router.py`, extend readiness tests

- Clean index → query sources with line ranges
- Drift → degraded + next_action rebuild; no fake clean
- `integration status` knowledge half green for local_fts synced
- notebooklm path regression still passes

**Code:** `query_router.py`, `ask_hygiene.py`, `integration.py` / readiness helpers

### Slice E — Closeout + CLI wiring + describe/skills/docs

**Tests:** closeout dry-run/apply with local_fts fixture repo; describe key present

**Code:** closeout driver branch; CLI; skills; harness/formal docs listed in §11.3

### Slice F — Acceptance

- Extend readonly acceptance or add `acceptance/local_fts/` script: init fixture corpus → sync apply → query known term → assert line range → product_ready knowledge half true (task half may remain separate).
- Prefer `scripts/test-closeout-local-fast.sh` / unit path; no real NotebookLM.

---

## 14. Concrete file touch list

| Path | Action |
|---|---|
| `src/vibe_control/knowledge/local_fts/__init__.py` | add |
| `src/vibe_control/knowledge/local_fts/chunking.py` | add |
| `src/vibe_control/knowledge/local_fts/fingerprint.py` | add |
| `src/vibe_control/knowledge/local_fts/store.py` | add |
| `src/vibe_control/knowledge/local_fts/provider.py` | add |
| `src/vibe_control/knowledge/query_router.py` | modify |
| `src/vibe_control/knowledge/ask_hygiene.py` | modify |
| `src/vibe_control/knowledge/doctor.py` | modify |
| `src/vibe_control/config.py` | modify |
| `src/vibe_control/integration.py` (+ readiness helpers as needed) | modify |
| `src/vibe_control/product_readiness.py` | modify |
| `src/vibe_control/closeout_runner.py` | modify |
| `src/vibe_control/describe.py` | modify |
| `src/vibe_control/skills/vibe-knowledge/SKILL.md` | modify |
| `AGENTS.md` | modify |
| tests listed in §13 | add |
| docs listed in §11.3 | modify |
| `.config` templates / `docs/configuration.md` / `.gitignore` | modify |

---

## 15. Acceptance criteria (done when)

1. With `knowledge.provider=local_fts` and empty index: `sync --dry-run` shows rebuild; `query` is not ask-clean.
2. After `sync --apply`: `status` → `synced` + `provider_ask_clean=true`.
3. Query for a known heading term returns ≥1 source with correct `path` and **accurate** `line_start`/`line_end` for a fixture file.
4. Changing one SSOT file content → `drift` until rebuild.
5. `product_ready` knowledge half can be true **without** NotebookLM installed/auth.
6. `provider=notebooklm` regression: existing unit tests still pass.
7. No NotebookLM network calls when provider is local_fts (assert in tests via no provider binary invoke).
8. Docs/skills/describe updated; this spec Status → **Accepted** and dated.

---

## 16. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Paraphrase miss vs NLM | Document ask shapes that use SSOT vocabulary; agent may `inventory` + Read |
| Huge markdown files | Window split 80/16 |
| Agents trust `answer` string as policy | `answer_mode=evidence_retrieval` + explicit non-oracle wording |
| Dogfood still on notebooklm | No forced cutover; owner switches when ready |
| Closeout accidentally hits NLM | Provider branch tests; mutation class split |

---

## 17. Review checklist (owner)

- [ ] Accept D1–D10 as stated, or list deltas
- [ ] Confirm fail-closed query when dirty (no keyword merge) — §8.1
- [ ] Confirm closeout may auto-rebuild local index under bounded rules — §7.2 / §11.2
- [ ] Confirm dogfood `.config` may stay on notebooklm until explicit switch — §9.2
- [ ] After Accept: agent implements slices A→F without redesign

---

## 18. Status history

| Date | Status | Note |
|---|---|---|
| 2026-07-21 | Proposed | Written for owner review |
| 2026-07-21 | Accepted | Review incorporated (P1/P2, C1–C5, trigram+LIKE); implementation starts |
