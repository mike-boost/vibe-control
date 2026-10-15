#!/usr/bin/env bash
# Compatibility wrapper: full *local* readonly gate only.
# Does NOT call real NotebookLM. For provider smoke use scripts/test-nlm-readonly-smoke.sh.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
echo "NOTE: test-full-readonly.sh now means full LOCAL readonly (no real NotebookLM)."
echo "      Use scripts/test-nlm-readonly-smoke.sh for explicit provider smoke."
exec "$ROOT/scripts/test-full-local-readonly.sh"
