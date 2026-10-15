# Phase 7 Test Execution Speed Report

## Summary

Added pytest-xdist, pytest markers, and standard gate scripts.
Default gates remain read-only for NotebookLM.

## Timing

| Gate | Result | Wall time (approx) |
|---|---|---|
| Serial pytest before (baseline `pytest -q --durations=25`) | 130 passed | **17.69s** |
| Parallel fast after (`scripts/test-fast.sh`) | 128 passed, 1 skipped | **~2.6s pytest / ~6.1s wall** |
| Serial-only after (`scripts/test-serial.sh`) | 11 passed, 129 deselected | **~12.3s pytest / ~12.9s wall** |
| Plain pytest after (`pytest -q`) | 139 passed, 1 skipped | **~14.0s** |
| Acceptance read-only (Phase 2–6) | all pass | **~63s** |
| Full read-only gate (`scripts/test-full-readonly.sh`) | pass | **~87s wall** |

Fast gate excludes acceptance wrappers; those still run in serial / acceptance gates.

## Slowest tests after optimization (plain pytest sample)

1. `test_phase3_acceptance_script_exits_zero` ~7.8s
2. `test_phase2_acceptance_still_passes` ~1.6s
3. `test_acceptance_command_outputs_parse_as_json` ~1.5s
4. `test_acceptance_script_exits_zero` ~1.4s
5. `test_integration_status_never_safe_to_sync` ~0.6s

## Excluded from parallel (and why)

| Group | Markers | Why serial |
|---|---|---|
| `tests/test_phase2_acceptance.py` | acceptance, serial, slow | subprocess acceptance runners; shared fixture process cost |
| `tests/test_phase3_acceptance.py` | acceptance, serial, slow | same |

No pytest tests are marked `mutation` / `real_notebooklm` yet (real smoke is CLI acceptance opt-in).

## Phase 6 mutation safety

- Default `acceptance/phase6/run_phase6_acceptance.py` is read-only audit.
- Real smoke requires `--real-smoke --apply`.
- `scripts/test-acceptance-readonly.sh` and `scripts/test-full-readonly.sh` never pass those flags.

## Commands

- `scripts/test-fast.sh`
- `scripts/test-serial.sh`
- `scripts/test-acceptance-readonly.sh`
- `scripts/test-full-readonly.sh`

## Remaining bottlenecks

- Phase 2/3 pytest wrappers still pay subprocess acceptance cost (~10–12s serial).
- Phase 4–6 acceptance scripts call real NotebookLM read APIs (~1m total).
- `test_integration_status_never_safe_to_sync` still ~0.6s (candidate for further isolation).

## Mutations this pass

None (read-only).
