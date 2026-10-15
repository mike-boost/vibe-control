#!/usr/bin/env bash
# Tier 3: optional real NotebookLM readonly smoke (serial, network-dependent).
# No provider mutation, no Beads mutation, no push.
# Not part of fast local closeout or full local readonly.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON="$ROOT/.venv/bin/python"
else
  PYTHON="python"
fi

unset VIBE_ACCEPTANCE_LOCAL || true
# Smoke evidence goes to runtime unless UPDATE_ACCEPTANCE_OBSERVED=1 explicitly set by operator.
unset UPDATE_ACCEPTANCE_OBSERVED || true

echo "NLM readonly smoke: knowledge status"
"$PYTHON" -m vibe_control knowledge status --json >/tmp/vibe-nlm-smoke-status.json

echo "NLM readonly smoke: cleanup-candidates"
"$PYTHON" -m vibe_control knowledge cleanup-candidates --json >/tmp/vibe-nlm-smoke-cleanup.json

Q="$(mktemp /tmp/vibe-nlm-smoke-q.XXXXXX)"
printf '%s\n' 'What is the current active SSOT identity?' > "$Q"
echo "NLM readonly smoke: knowledge query"
"$PYTHON" -m vibe_control knowledge query --question-file "$Q" --json >/tmp/vibe-nlm-smoke-query.json
rm -f "$Q"

"$PYTHON" - <<'PY'
import json
from pathlib import Path

status = json.loads(Path("/tmp/vibe-nlm-smoke-status.json").read_text())
clean = json.loads(Path("/tmp/vibe-nlm-smoke-cleanup.json").read_text())
query = json.loads(Path("/tmp/vibe-nlm-smoke-query.json").read_text())
sd = status.get("data") or {}
cd = clean.get("data") or {}
qd = query.get("data") or {}
assert status.get("ok") is True, status
assert clean.get("ok") is True and clean.get("mutation") is False, clean
assert query.get("ok") is True, query
print("sync_state=", sd.get("sync_state"))
print("candidate_count=", cd.get("candidate_count"))
print("required_updates_count=", cd.get("required_updates_count"))
ah = cd.get("ask_hygiene") or {}
print("provider_ask_clean=", ah.get("provider_ask_clean"), "condition=", ah.get("condition"))
print("query_provider=", qd.get("provider"), "ask_template=", qd.get("ask_template_id"), qd.get("ask_template_version"))
print("query_provider_ask_clean=", qd.get("provider_ask_clean"))
PY

echo "NLM READONLY SMOKE PASSED"
