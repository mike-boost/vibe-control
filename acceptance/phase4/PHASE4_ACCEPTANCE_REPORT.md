# Phase 4 Acceptance Report

## Phase Goal

Prove a real NotebookLM integration path against the allow-listed test notebook `OPM-test`, with dry-run only as a safety preview before optional add-only seed.

## What This Phase Proves

- Vibe config can define allow-listed notebooks and set `OPM-test` as default.
- Notebook ref resolves from env / ignored local `.config/.env` (not committed config).
- Desired corpus drives sync-preview and add-only seed planning.
- Real remote status / inventory / sync-preview / seed dry-run against OPM-test.
- Add-only seed requires explicit `--allow-add` and external approval; approved and executed.
- Fake/dry-run providers remain available for automated regression.

This phase proves real NotebookLM integration against `OPM-test` with notebook ref configured.
This phase proves add-only seed after approval.
This phase does **not** prove full sync lifecycle, update/delete/clean, Spec publish, or Beads task creation.

## Config Path Decision

| Item | Value | Status |
|---|---|---|
| Primary config | `.config/vibe-control.yaml` | PASS |
| Backward compatibility | `.vibe/control.yaml` | PASS |
| Local secrets | `.config/.env` ignored | PASS |

## Notebook Configuration

| Item | Value | Status |
|---|---|---|
| Default alias | OPM-test | PASS |
| Allow list | OPM-test | PASS |
| Notebook ref configured | Yes (`file:.config/.env`) | PASS |
| Notebook ref committed | No | PASS |

## Real NotebookLM Integration

| Check | Result | Status |
|---|---|---|
| Auth | available | PASS |
| Remote status | installed, configured, `can_list_sources=true`, `safe_to_sync=false` | PASS |
| Remote inventory (after seed) | 1 managed + 1 unmanaged title | PASS |
| Seed dry-run | Planned add Spec + Decision Log | PASS |
| Add-only seed | Approved; both adds accepted by NotebookLM CLI | PASS |

## Commands Verified

```bash
python -m vibe_control config validate --json
python -m vibe_control knowledge inventory --json
python -m vibe_control knowledge notebook list --json
python -m vibe_control knowledge notebook status --json
python -m vibe_control knowledge remote-status --notebook OPM-test --json
python -m vibe_control knowledge remote-inventory --notebook OPM-test --json
python -m vibe_control knowledge sync-preview --notebook OPM-test --json
python -m vibe_control knowledge seed-test-sources --notebook OPM-test --dry-run --json
python -m vibe_control knowledge seed-test-sources --notebook OPM-test --allow-add --json
python acceptance/phase4/run_phase4_acceptance.py
pytest -q
python acceptance/phase2/run_phase2_acceptance.py
python acceptance/phase3/run_phase3_acceptance.py
```

Observed JSON under `acceptance/phase4/observed/` (no raw notebook refs committed; fingerprints only).

## Optional Add-only Seed Result

| Action | Approved? | Executed? | Result |
|---|---:|---:|---|
| Add test sources to OPM-test | yes | yes | 2 adds accepted (`OK`) |

Post-seed inventory notes:

- Managed present: `[vibe:vibe-control:DECISION_LOG] DECISION_LOG.md`
- Spec file was accepted, but remote title returned as `VIBE_CONTROL_V0_5_SPEC.md` (no Vibe prefix) — treated as unmanaged for classification; sync-preview still reports one remaining `add` for the Spec managed title

## Spec Alignment

| Vibe Control v0.5 principle | Evidence in this phase | Status |
|---|---|---|
| Repository remains SSOT | Desired corpus drives seed/preview | PASS |
| NotebookLM is derived KB | OPM-test received derived test sources only | PASS |
| Repo fallback remains available | Phase 2/3 acceptance still passes | PASS |
| No broad mutation by default | Add-only seed required approval; `safe_to_sync=false` | PASS |
| Deterministic managed source identity | Title prefix parsed for Decision Log | PASS |
| Notebook allow list controls target | OPM-test configured | PASS |
| Local secrets not committed | Notebook ref uses `.config/.env` | PASS |

## What Is Now Visible / Experiential

- Committed `.config/vibe-control.yaml` with `OPM-test` allow list
- Tiny Vibe Control desired corpus under `docs/project/`
- Local secrets via `.config/.env`
- Real OPM-test remote inventory and approved add-only seed
- Phase 4 acceptance runner + observed artifacts

## What This Phase Does Not Prove

- Full NotebookLM sync lifecycle
- Source update / delete / clean
- Spec publish
- Beads task creation
- Content-hash verification of remote managed sources
- Guaranteed remote title retention for every uploaded file (see Known Gaps)

## Known Gaps

- NotebookLM may store uploaded file sources under the filename instead of the requested `--title` (observed for Spec); Decision Log retained managed title
- Remote content verification remains `already_present_needs_verification`
- No managed rename/update path in this phase to repair title drift

## Next Phase Recommendation

1. Investigate NotebookLM title retention / rename for managed identity
2. Guarded sync planner beyond add-only (still no unmanaged mutation)
3. Beads task surface / Spec publish in later phases
