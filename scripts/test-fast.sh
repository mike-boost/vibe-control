#!/usr/bin/env bash
# Fast parallel-safe pytest gate (no serial / real NotebookLM / acceptance / slow / mutation).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# Prefer project venv when present.
if [[ -x "$ROOT/.venv/bin/pytest" ]]; then
  PYTEST="$ROOT/.venv/bin/pytest"
else
  PYTEST="pytest"
fi
exec "$PYTEST" -q -n auto --dist=loadscope \
  -m "not serial and not real_notebooklm and not real_hetu and not acceptance and not slow and not mutation and not real_skill_host" \
  "$@"
