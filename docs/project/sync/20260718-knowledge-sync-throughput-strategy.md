# Knowledge sync throughput strategy (post SE measure)

**Date:** 2026-07-18  
**Status:** implemented (API concurrent ingest + stage timers + disclosure)  
**Trigger:** Owner rejected ~9–10s/source wall time on SE ~150–200KB corpus.

## 1. What we actually measured (honest)

Runs on OPM-test with `--batch-size 5 --wait-mode multi`:

| Desired N | New uploads | Wall |
|---|---:|---:|
| 10 | 10 | ~94s |
| 20 | 10 delta | ~95s |
| 40 | 20 delta | ~192s |

≈ **9–10 s per new source**. Failures: 0.

## 2. Did we use “real” parallelism?

**Only partially — and the wrong half.**

Current Vibe path (`phase8_apply` + CLI adapter):

```text
for doc in batch:
    subprocess: notebooklm source add <one file>   # SERIAL upload
collect ids
ThreadPoolExecutor: notebooklm source wait <id>…  # concurrent waits only
```

So:

| Stage | Parallel? | Notes |
|---|---|---|
| File upload (`source add`) | **No** | One CLI process per file, sequential |
| Ready wait (`source wait`) | **Yes (in-process)** | Concurrent single-id waits |
| Native multi-id wait CLI | **No** | CLI accepts one `SOURCE_ID` |

If upload+register dominates (likely for 150–200KB files), parallel wait barely helps.
That matches the flat ~10s/source: **we serialized the expensive part**.

Owner intuition (“not a network problem”) is consistent with this: we paid
repeated CLI process startup + serial upload RPC, not just RTT.

## 3. What notebooklm-py / CLI actually offer

Evidence: Context7 `/teng-lin/notebooklm-py` python-api + local CLI 0.8.0a3.

### Python API (preferred for throughput)

- `sources.add_file(..., wait=False)` — **default does not wait for READY**
- `sources.wait_for_sources(nb_id, ids, timeout=…)` — **parallel multi-id wait**
- `sources.wait_until_registered` — narrower: visible enough for rename/follow-up RPC
- `max_concurrent_uploads` — **default 4**, semaphore-gated file upload streaming
  (FD safety; not unbounded)
- Docs explicitly show: add several URLs/files, then one `wait_for_sources`

### CLI (what Vibe uses today)

- `notebooklm source add` — **one content arg** (no multi-file add)
- `notebooklm source wait SOURCE_ID` — **one id**
- Skill pattern: add with `--json` → spawn waits (even suggests subagent) while main continues

### Product implication

Official library already encodes the right pipeline:

```text
concurrent add_file(wait=False) ≤ max_concurrent_uploads
        ↓
one wait_for_sources(all ids)   # or wait_all_until_ready aggregate
        ↓
verify / receipt
```

Vibe’s CLI-subprocess adapter **cannot** express that without either:

1. switching knowledge apply to **Python API** for file ingest, or
2. launching multiple `source add` CLI processes concurrently (worse than API;
   still N process starts; fights rate limits awkwardly).

## 4. Questions the next retest must answer (instrumented)

Do **not** retest with the same opaque wall clock. Split stages:

| Metric | Meaning |
|---|---|
| `t_add_ms[i]` | time for each `add_file`/`source add` until source id returned |
| `t_wait_ms_batch` | time for one multi-wait until all READY |
| `t_verify_ms` | final list/probe |
| `in_flight` | concurrent uploads used (1 vs 4 vs 8) |

Hypothesis to confirm:

1. Serial CLI add ≈ almost all of the 9–10s/source.
2. Parallel API uploads (4) cut add-phase wall by ~3–4×.
3. Wait-phase for ~200KB markdown is often seconds, not 120s — multi-wait
   should be ≈ max(individual waits), not sum.

## 5. Proposed strategy (next implementation slice)

### A. Provider path (load-bearing)

- Add NotebookLM **Python API ingest adapter** for apply creates
  (keep CLI for doctor/status where fine).
- Pipeline: `add_file(wait=False)` with concurrency = `max_concurrent_uploads`
  (start at 4; make configurable via `--upload-concurrency`).
- Then **one** `wait_for_sources` / `wait_all_until_ready` for the micro-batch
  (or whole run if N small).
- Keep receipt checkpoint after READY (not after add-accepted).

### B. Agent disclosure

Expose on sync_policy:

- `upload_concurrency` (default **8**, how: `--upload-concurrency N`) — in-flight
  single-file uploads gated by notebooklm-py semaphore; **not** one bulk multi-file RPC
- `wait_mode=library_multi` available when API path enabled
- Honest note: CLI path cannot parallelize uploads

### C. Retest protocol (after cleanup — done)

1. OPM-test cleaned of `vibe__vibe-scale-se__*` (2026-07-18: 40 deleted, 4 vibe-control left).
2. Fresh ephemeral project, **N=10** only first.
3. Compare three modes with stage timers:
   - baseline CLI serial (today)
   - API concurrent uploads=4 + multi-wait
   - optional uploads=1 + multi-wait (isolate wait gain)
4. Only then scale to N=20/40.

### D. Explicit non-goals for this slice

- Raising NotebookLM plan caps
- Claiming CLI multi-id wait exists
- Unbounded upload fan-out (`max_concurrent_uploads` exists for a reason)

## 6. Cleanup status

| Item | Status |
|---|---|
| Remote `vibe__vibe-scale-se__*` on OPM-test | **Deleted 40/40** (2026-07-18) |
| Remaining OPM-test sources | 4 × vibe-control managed |
| Local `~/.agents/state/.../vibe-scale-se` | removed |
| Dataset on disk | kept (`~/Documents/tmp/dataset-200kb`) for retest |
| Ephemeral project | kept (`~/Documents/tmp/vibe-scale-se`) |

## 7. Implementation landed (2026-07-18)

| Piece | Location |
|---|---|
| API concurrent ingest | `src/vibe_control/knowledge/notebooklm_api_ingest.py` |
| Provider method | `NotebookLMProvider.bulk_create_and_wait` |
| Apply wiring + stage_ms | `phase8_apply.apply_forward_sync` |
| Flags | `--ingest-path auto\|api\|cli`, `--upload-concurrency N` |
| Disclosure | `agent_surface.knowledge_sync_disclosure` |
| Optional dep | `pip install 'vibe-control[notebooklm]'` / `notebooklm-py` |

### Retest command (N=10, after OPM-test cleanup)

```bash
cd ~/Documents/tmp/vibe-scale-se
# from vibe-control repo python:
python -m vibe_control knowledge sync --apply --json \
  --ingest-path api --upload-concurrency 8 --batch-size 10 \
  --continue-on-item-error
```

### N=10 remeasure (2026-07-18, SE ~150–200KB, OPM-test)

| Mode | Wall | stage add | stage wait | stage verify | Failures |
|---|---:|---:|---:|---:|---:|
| CLI serial + wait multi (prior) | ~94s | (opaque) | (opaque) | (opaque) | 0 |
| **API concurrent uploads=4, batch=10** | **~27s** | **15.6s** | **2.9s** | **3.4s** | 0 |

≈ **3.5× wall improvement**. Add phase still dominates; wait is no longer the story.
Evidence: `~/Documents/tmp/vibe-scale-measure-results/n10-api-concurrent-summary.json`

Compare against `--ingest-path cli --batch-size 5 --wait-mode multi` baseline.
Expect `scale.stage_ms.{add,wait,verify}` in apply JSON — do not judge by opaque wall alone.

## 8. Explicit non-goals (still)

- Raising NotebookLM plan caps
- Claiming CLI multi-id wait exists
- Unbounded upload fan-out
