#!/usr/bin/env bash
# Knowledge sync scale measurement helper.
#
# Default: READONLY baseline (status / inventory / sync dry-run / CLI wait capability).
# Never mutates NotebookLM unless BOTH are set:
#   --apply
#   VIBE_KNOWLEDGE_SCALE_MEASURE_APPLY=1
#
# Apply mode times a real sync --apply (owner-authorized only). Results go under
# runtime/vibe-scale-measure/ (gitignored runtime), not acceptance/observed.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON="$ROOT/.venv/bin/python"
else
  PYTHON="python"
fi

APPLY=0
BATCH_SIZE=1
WAIT_MODE=serial
CONTINUE=0
INGEST_PATH=auto
UPLOAD_CONCURRENCY=8
OUT_DIR="${VIBE_SCALE_MEASURE_OUT:-$ROOT/runtime/vibe-scale-measure}"

usage() {
  cat <<'EOF'
Usage: scripts/measure-knowledge-sync-scale.sh [--apply] [--batch-size N] [--wait-mode serial|multi]
       [--ingest-path auto|api|cli] [--upload-concurrency N] [--continue-on-item-error]

Default: readonly baseline only.
Apply timing requires --apply AND VIBE_KNOWLEDGE_SCALE_MEASURE_APPLY=1.
Prefer --ingest-path api --upload-concurrency 8 --batch-size 10 for multi-file throughput.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) APPLY=1; shift ;;
    --batch-size) BATCH_SIZE="${2:?}"; shift 2 ;;
    --wait-mode) WAIT_MODE="${2:?}"; shift 2 ;;
    --ingest-path) INGEST_PATH="${2:?}"; shift 2 ;;
    --upload-concurrency) UPLOAD_CONCURRENCY="${2:?}"; shift 2 ;;
    --continue-on-item-error) CONTINUE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

mkdir -p "$OUT_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BASE="$OUT_DIR/$STAMP"
mkdir -p "$BASE"

echo "scale-measure: readonly baseline → $BASE"
"$PYTHON" -m vibe_control knowledge status --json >"$BASE/status.json"
"$PYTHON" -m vibe_control knowledge inventory --json >"$BASE/inventory.json"
"$PYTHON" -m vibe_control knowledge sync --dry-run --json >"$BASE/sync-dry-run.json" || true
notebooklm --version >"$BASE/notebooklm-version.txt" 2>&1 || echo "notebooklm missing" >"$BASE/notebooklm-version.txt"
notebooklm source wait --help >"$BASE/notebooklm-source-wait-help.txt" 2>&1 || true

"$PYTHON" - <<PY
import json
from pathlib import Path

base = Path("$BASE")
status = json.loads((base / "status.json").read_text())
inv = json.loads((base / "inventory.json").read_text())
dry = {}
dry_path = base / "sync-dry-run.json"
if dry_path.is_file() and dry_path.stat().st_size:
    try:
        dry = json.loads(dry_path.read_text())
    except json.JSONDecodeError:
        dry = {"ok": False, "parse_error": True}

sd = status.get("data") or {}
scale = sd.get("scale") or {}
quota = sd.get("source_quota") or {}
idd = inv.get("data") or {}
dd = dry.get("data") or dry
wait_help = (base / "notebooklm-source-wait-help.txt").read_text(errors="replace")
cli_multi_id = "SOURCE_ID" in wait_help and "SOURCE_IDS" not in wait_help and "source_ids" not in wait_help.lower()

summary = {
    "schema": "vibe.knowledge.scale_measure.v1",
    "mode": "readonly",
    "mutation": False,
    "status_ok": bool(status.get("ok")),
    "sync_state": sd.get("sync_state"),
    "desired_count": scale.get("desired_count") or idd.get("source_count"),
    "receipt_item_count": scale.get("receipt_item_count"),
    "required_updates_count": dd.get("required_updates_count"),
    "source_quota": {
        "max_sources": quota.get("max_sources"),
        "warn_sources": quota.get("warn_sources"),
        "standard_sources_cap": quota.get("standard_sources_cap"),
        "max_sources_exceeds_standard": quota.get("max_sources_exceeds_standard"),
    },
    "sync_policy_default": (scale.get("sync_policy") or {}).get("default"),
    "sync_policy_choices": [
        c.get("id") for c in ((scale.get("sync_policy") or {}).get("choices") or [])
    ],
    "notebooklm_cli_wait_is_single_id": True,
    "notebooklm_version": (base / "notebooklm-version.txt").read_text(errors="replace").strip(),
    "notes": [
        "Apply wall-clock for N=10/20/50 still requires explicit --apply + env gate",
        "Multi-file throughput: --ingest-path api --upload-concurrency 8 --batch-size N",
        "CLI --wait-mode multi only coalesces waits; uploads stay serial on ingest_path=cli",
    ],
}
(base / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
print(json.dumps(summary, indent=2))
PY

if [[ "$APPLY" -eq 0 ]]; then
  echo "READONLY SCALE MEASURE DONE (no mutation)"
  exit 0
fi

if [[ "${VIBE_KNOWLEDGE_SCALE_MEASURE_APPLY:-}" != "1" ]]; then
  echo "REFUSED: --apply requires VIBE_KNOWLEDGE_SCALE_MEASURE_APPLY=1" >&2
  exit 3
fi

echo "scale-measure: APPLY authorized → timing sync --apply"
APPLY_ARGS=(
  knowledge sync --apply --json
  --batch-size "$BATCH_SIZE"
  --wait-mode "$WAIT_MODE"
  --ingest-path "$INGEST_PATH"
  --upload-concurrency "$UPLOAD_CONCURRENCY"
)
if [[ "$CONTINUE" -eq 1 ]]; then
  APPLY_ARGS+=(--continue-on-item-error)
fi

START_NS="$("$PYTHON" - <<'PY'
import time
print(time.time_ns())
PY
)"
set +e
"$PYTHON" -m vibe_control "${APPLY_ARGS[@]}" >"$BASE/sync-apply.json"
APPLY_RC=$?
set -e
END_NS="$("$PYTHON" - <<'PY'
import time
print(time.time_ns())
PY
)"

"$PYTHON" - <<PY
import json
from pathlib import Path

base = Path("$BASE")
start = int("$START_NS")
end = int("$END_NS")
elapsed_ms = int((end - start) / 1_000_000)
payload = {}
try:
    payload = json.loads((base / "sync-apply.json").read_text())
except Exception as exc:
    payload = {"ok": False, "parse_error": str(exc)}
data = payload.get("data") or payload
summary = json.loads((base / "summary.json").read_text())
summary.update(
    {
        "mode": "apply",
        "mutation": True,
        "apply_exit_code": int("$APPLY_RC"),
        "wall_elapsed_ms": elapsed_ms,
        "batch_size": int("$BATCH_SIZE"),
        "wait_mode": "$WAIT_MODE",
        "ingest_path": "$INGEST_PATH",
        "upload_concurrency": int("$UPLOAD_CONCURRENCY"),
        "continue_on_item_error": bool(int("$CONTINUE")),
        "apply_ok": bool(payload.get("ok")),
        "apply_code": data.get("code") or payload.get("error", {}).get("code") if isinstance(payload.get("error"), dict) else data.get("code"),
        "apply_elapsed_ms_reported": data.get("elapsed_ms"),
        "apply_ingest_path": data.get("ingest_path"),
        "apply_stage_ms": (data.get("scale") or {}).get("stage_ms"),
        "item_failures_count": len(data.get("item_failures") or []),
        "scale": data.get("scale"),
    }
)
(base / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
print(json.dumps(summary, indent=2))
PY

echo "APPLY SCALE MEASURE DONE rc=$APPLY_RC"
exit "$APPLY_RC"
