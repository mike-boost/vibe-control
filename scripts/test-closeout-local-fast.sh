#!/usr/bin/env bash
# Tier 1: fast local closeout — parallel-safe pytest + focused local checks.
# No real NotebookLM, no real Beads, no provider mutation.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON="$ROOT/.venv/bin/python"
else
  PYTHON="python"
fi

"$ROOT/scripts/test-fast.sh"

"$PYTHON" -m vibe_control config validate --json >/dev/null
"$PYTHON" -m vibe_control spec validate docs/project/vibe-control-spec.md --json >/dev/null

# Focused local contracts (already covered by fast markers; re-run for closeout clarity).
"$PYTHON" -m pytest -q \
  tests/test_ask_hygiene.py \
  tests/test_cleanup_candidates.py \
  tests/test_knowledge_ask_template.py \
  tests/test_acceptance_observed_output.py \
  tests/test_harness_tiers.py \
  -m "not real_notebooklm and not real_hetu and not mutation and not real_skill_host"

echo "CLOSEOUT LOCAL FAST PASSED"
