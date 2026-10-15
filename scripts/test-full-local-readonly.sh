#!/usr/bin/env bash
# Tier 2: full local readonly gate — no real NotebookLM / Beads / mutation.
# Uses xdist for parallel-safe pytest; serial group excludes real_notebooklm.
# Acceptance runs with VIBE_ACCEPTANCE_LOCAL=1 (no provider network).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON="$ROOT/.venv/bin/python"
  PYTEST="$ROOT/.venv/bin/pytest"
else
  PYTHON="python"
  PYTEST="pytest"
fi

"$ROOT/scripts/test-fast.sh"

# Serial/slow local tests only (exclude real NotebookLM).
"$PYTEST" -q -m "(serial or slow) and not real_notebooklm and not real_hetu and not mutation and not real_skill_host" --durations=20

export VIBE_ACCEPTANCE_LOCAL=1
# Default observed writes go to observed-runtime/ (not tracked observed/).
unset UPDATE_ACCEPTANCE_OBSERVED || true
"$ROOT/scripts/test-acceptance-readonly.sh"

echo "FULL LOCAL READONLY GATE PASSED"
