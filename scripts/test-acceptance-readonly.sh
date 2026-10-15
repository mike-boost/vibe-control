#!/usr/bin/env bash
# Read-only acceptance gate (Phases 2–6 + 8 + 9/10 + 11A + 11B). Never passes mutation apply flags.
# When VIBE_ACCEPTANCE_LOCAL=1, Phase 4/4F/5/6 skip real NotebookLM remote calls.
# Default observed evidence writes to observed-runtime/ (not tracked observed/).
# Phase 11B uses fake/local dry-run only; never real Beads mutation.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON="$ROOT/.venv/bin/python"
else
  PYTHON="python"
fi

"$PYTHON" acceptance/phase2/run_phase2_acceptance.py
"$PYTHON" acceptance/phase3/run_phase3_acceptance.py
"$PYTHON" acceptance/phase4/run_phase4_acceptance.py
"$PYTHON" acceptance/phase4f/run_phase4f_acceptance.py
"$PYTHON" acceptance/phase5/run_phase5_acceptance.py
# Phase 6 default is read-only audit (mutation smoke is opt-in elsewhere).
"$PYTHON" acceptance/phase6/run_phase6_acceptance.py
"$PYTHON" acceptance/phase8/run_phase8_acceptance.py
"$PYTHON" acceptance/phase9_10/run_phase9_10_acceptance.py
"$PYTHON" acceptance/phase11a/run_phase11a_acceptance.py
"$PYTHON" acceptance/phase11b/run_phase11b_acceptance.py
"$PYTHON" acceptance/phase12/run_phase12_acceptance.py
"$PYTHON" acceptance/provider_readiness/run_provider_readiness_acceptance.py

echo "ACCEPTANCE READONLY GATE PASSED"
