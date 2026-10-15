# Test Execution Contract

Short rules for local and agent test gates.

## Evidence tiers

### 1. Fast local closeout

`scripts/test-closeout-local-fast.sh`

- Local only: pytest-xdist parallel-safe tests + config/spec validate + focused ask/cleanup contracts
- No real NotebookLM
- No real Beads
- No provider mutation
- Final `git status --short` for closeout reports must be empty (no tracked modifications)

Underlying parallel gate: `scripts/test-fast.sh`

### 2. Full local readonly gate

`scripts/test-full-local-readonly.sh`

- Full local / fixture regression
- Sets `VIBE_ACCEPTANCE_LOCAL=1` so acceptance skips real NotebookLM network calls
- Parallel: `test-fast.sh` (xdist)
- Serial local: `pytest -m "(serial or slow) and not real_notebooklm and not real_hetu and not mutation"`
- Acceptance: `scripts/test-acceptance-readonly.sh` under local mode
- No real NotebookLM / Beads / Hetu reindex / mutation by default
- Final `git status --short` must be empty

Compatibility wrapper: `scripts/test-full-readonly.sh` → calls full **local** readonly only.
It does **not** run provider smoke.

### 3. Optional real NotebookLM readonly smoke

`scripts/test-nlm-readonly-smoke.sh`

- Explicit real provider (status + cleanup-candidates + query)
- Serial / network-dependent
- No provider mutation, no Beads mutation, no push
- Not part of fast closeout or full local readonly
- Evidence written under `/tmp` (not tracked acceptance observed)

### 3b. Optional real Hetu readonly smoke

`scripts/test-hetu-readonly-smoke.sh`

- Explicit real codebase-memory-mcp doctor/status (no reindex)
- Marker: `real_hetu`
- Not part of fast closeout or full local readonly

`scripts/test-hetu-reindex-smoke.sh` is owner-gated mutation documentation only;
default land relies on fake/unit `tests/test_hetu_reindex.py`.

## Optional real host Skill Assay smoke

`scripts/test-skill-assay-host-smoke.sh` (when present)

- Explicit Cursor / GitHub Copilot host verification for `vibe skill-assay`
- Marker: `real_skill_host` (serial; network / paid host SDKs)
- Not part of fast closeout or full local readonly
- Evidence under `/tmp` or `runtime/vibe-skill-assay/` (gitignored)

## pytest-xdist / parallel policy

- Dependency: `pytest-xdist` in `pyproject.toml` `[project.optional-dependencies] dev`
- Fast gate already uses `-n auto --dist=loadscope`
- Markers (`pyproject.toml` / `tests/conftest.py`):
  - parallel-safe default: unmarked → `unit`
  - must stay serial: `serial`, `acceptance`, `slow`, `real_notebooklm`, `real_hetu`, `mutation`, `real_skill_host`
- Why xdist looked “unused” before: it **was** used in `test-fast.sh`, but
  `test-full-readonly.sh` then ran serial acceptance + **real NotebookLM** probes that
  dominated wall time, so parallel unit speed was masked.

## Must remain serial

- `real_notebooklm` — shared provider target / network
- `real_hetu` — real codebase-memory-mcp
- `real_skill_host` — Cursor / Copilot Skill Assay live smoke
- `mutation` — remote side effects
- `acceptance` wrappers / subprocess acceptance scripts
- `serial` — shared receipt/ack/home state or fixed output paths
- `slow` — intentionally heavy local subprocess suites

## Observed output policy

Phase 4/4F/5/6/8 acceptance `save()` uses `acceptance/lib/observed_output.py`:

- Default → `acceptance/*/observed-runtime/` (gitignored)
- Opt-in tracked update → `UPDATE_ACCEPTANCE_OBSERVED=1` → `acceptance/*/observed/`
- Default gates must not overwrite tracked `observed/*.json`

## Mutation / Beads / push

- Default gates: no NotebookLM mutation, no Beads mutation, no push
- Real mutation smoke requires explicit phase approval + CLI flags (see real-integration-mutation-contract)
- Live Beads dual gate is a **temporary** harness safety layer; product path does not execute
  live `bd create/update` in default automation. Intended autonomy for safe Vibe-managed ops
  is encoded in Approval Matrix / `autonomy_policy` — do not remove gates without focused tests.
- Closeout requires clean local modification state (`git status --short` empty)

## Debugging

Rerun the specific failing test serially (no xdist) first.

## Dependencies

`pytest-xdist` is a **dev/test** dependency only, not a runtime dependency.
