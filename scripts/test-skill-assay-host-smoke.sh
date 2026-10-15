#!/usr/bin/env bash
# Optional live Skill Assay host smoke (NOT part of default gates).
# Usage:
#   scripts/test-skill-assay-host-smoke.sh cursor
#   scripts/test-skill-assay-host-smoke.sh github-copilot
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOST="${1:-}"
if [[ -z "${HOST}" ]]; then
  echo "usage: $0 <cursor|github-copilot>" >&2
  exit 2
fi
cd "${ROOT}"
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"
if [[ -x "${ROOT}/.venv/bin/python" ]]; then
  PY="${ROOT}/.venv/bin/python"
else
  PY="python"
fi

SKILL_DIR="${SKILL_ASSAY_SMOKE_SKILL:-${HOME}/.agents/skills/high-speed-communication}"
if [[ ! -f "${SKILL_DIR}/SKILL.md" ]]; then
  # Common alternate install path used in this workspace.
  ALT="${HOME}/Documents/repo/ai/ai-manager/skills/high-speed-communication"
  if [[ -f "${ALT}/SKILL.md" ]]; then
    SKILL_DIR="${ALT}"
  fi
fi
if [[ ! -f "${SKILL_DIR}/SKILL.md" ]]; then
  echo "skill not found: ${SKILL_DIR}" >&2
  exit 2
fi

SCENARIO="$(mktemp -t skill-assay-scenario.XXXXXX.yaml)"
cleanup() { rm -f "${SCENARIO}"; }
trap cleanup EXIT

cat >"${SCENARIO}" <<'YAML'
schema: vibe.skill_assay.scenario.v1
execution_profile: response_only
timeout_seconds: 180
prompt: |
  Reply using the high-speed-communication skill.
  Include a Mode label and these headings: Status, Decision, Next, Open.
checks:
  - kind: assistant_text_match
    contains: "Mode:"
  - kind: assistant_text_match
    contains: "## Status"
  - kind: assistant_text_match
    contains: "## Decision"
  - kind: assistant_text_match
    contains: "## Next"
  - kind: assistant_text_match
    contains: "## Open"
YAML

echo "Skill Assay live smoke for host=${HOST} skill=${SKILL_DIR}"
"${PY}" - "${HOST}" <<'PY'
import json
import sys
from vibe_control.skill_assay.registry import build_adapter_registry

host = sys.argv[1]
registry = build_adapter_registry(include_fake=False)
if host not in registry:
    print(json.dumps({"ok": False, "error": "unknown_host", "host": host}))
    sys.exit(2)
result = registry[host].doctor()
print(
    json.dumps(
        {
            "host_id": result.host_id,
            "ok": result.ok,
            "support_state": result.support_state,
            "blockers": result.blockers,
            "details": result.details,
        },
        indent=2,
    )
)
if not result.ok or result.support_state != "supported":
    print(
        f"HOST NOT READY: ok={result.ok} support_state={result.support_state} "
        f"blockers={result.blockers}",
        file=sys.stderr,
    )
    sys.exit(1)
PY

echo "Running diagnose --execute (runs=3)…"
"${PY}" -m vibe_control.cli skill-assay diagnose \
  --skill "${SKILL_DIR}" \
  --host "${HOST}" \
  --scenario "${SCENARIO}" \
  --runs 3 \
  --execute \
  --json | tee /tmp/skill-assay-smoke-"${HOST}".json

"${PY}" - "${HOST}" <<'PY'
import json
import sys
from pathlib import Path

host = sys.argv[1]
payload = json.loads(Path(f"/tmp/skill-assay-smoke-{host}.json").read_text())
data = payload.get("data") or payload
assert payload.get("ok", True) is True or data.get("assay_id"), payload
assay_id = data["assay_id"]
root = Path("runtime/vibe-skill-assay") / assay_id
assert (root / "evidence.json").is_file()
sessions = {r["session_id"] for r in data["run_summaries"]}
assert len(sessions) == 3, sessions
assert all((root / "runs" / f"{i}.assistant_text").is_file() for i in range(3))
nonempty = [
    (root / "runs" / f"{i}.assistant_text").read_text(encoding="utf-8").strip()
    for i in range(3)
]
assert all(nonempty), "assistant text must be non-empty"
print(json.dumps({
    "ok": True,
    "assay_id": assay_id,
    "sessions": sorted(sessions),
    "checks_summary": data.get("checks_summary"),
    "assistant_chars": [len(t) for t in nonempty],
}, indent=2))
PY

echo "Smoke OK for host=${HOST}"
