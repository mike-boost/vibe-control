#!/usr/bin/env bash
# Optional real Hetu readonly smoke (serial). Does NOT reindex / mutate.
# Not part of fast closeout or full local readonly. Marker: real_hetu.
# Prefer fake/unit coverage in normal gates; run this only when validating
# a real codebase-memory-mcp install against an isolated enabled config.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON="$ROOT/.venv/bin/python"
else
  PYTHON="python"
fi

echo "Hetu readonly smoke: doctor (requires components.hetu.enabled in active config)"
"$PYTHON" -m vibe_control hetu doctor --json >/tmp/vibe-hetu-smoke-doctor.json
echo "Hetu readonly smoke: status"
"$PYTHON" -m vibe_control hetu status --json >/tmp/vibe-hetu-smoke-status.json
"$PYTHON" - <<'PY'
import json
from pathlib import Path

doctor = json.loads(Path("/tmp/vibe-hetu-smoke-doctor.json").read_text())
status = json.loads(Path("/tmp/vibe-hetu-smoke-status.json").read_text())
assert "ok" in doctor and "mutation_intent" in doctor
assert doctor.get("mutation_intent") is False
assert doctor.get("mutation_performed") is False
assert status.get("mutation_intent") is False
print("hetu readonly smoke ok")
PY
