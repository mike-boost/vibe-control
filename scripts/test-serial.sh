#!/usr/bin/env bash
# Serial / slow / real-provider pytest gate.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ -x "$ROOT/.venv/bin/pytest" ]]; then
  PYTEST="$ROOT/.venv/bin/pytest"
else
  PYTEST="pytest"
fi
exec "$PYTEST" -q -m "serial or real_notebooklm or slow" --durations=20 "$@"
