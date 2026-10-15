#!/usr/bin/env bash
# Sync GitHub Release notes from CHANGELOG.md for one or more versions.
# Usage:
#   scripts/gh-sync-release-notes.sh 0.5.5
#   scripts/gh-sync-release-notes.sh --all
#   scripts/gh-sync-release-notes.sh --check 0.5.10
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
REPO="${GH_REPO:-mike-boost/vibe-control}"
EXTRACT=(python3 "$ROOT/scripts/extract-release-notes.py")

usage() {
  cat <<'EOF'
Usage:
  scripts/gh-sync-release-notes.sh <version> [<version>...]
  scripts/gh-sync-release-notes.sh --all
  scripts/gh-sync-release-notes.sh --check <version>
EOF
}

versions_from_changelog() {
  python3 - <<'PY'
import re
from pathlib import Path
text = Path("CHANGELOG.md").read_text(encoding="utf-8")
for m in re.finditer(r"^## \[([^\]]+)\]", text, re.M):
    print(m.group(1))
PY
}

check_one() {
  local ver="$1"
  local tag="v${ver#v}"
  local ver_plain="${tag#v}"
  local tmp
  tmp="$(mktemp)"
  "${EXTRACT[@]}" "$ver_plain" >"$tmp"
  local remote
  remote="$(gh release view "$tag" --repo "$REPO" --json body --jq .body)"
  if [[ "$remote" == "$(cat "$tmp")" ]]; then
    echo "OK  $tag notes match CHANGELOG extract"
    rm -f "$tmp"
    return 0
  fi
  echo "DRIFT  $tag notes differ from CHANGELOG extract" >&2
  rm -f "$tmp"
  return 1
}

sync_one() {
  local ver="$1"
  local tag="v${ver#v}"
  local ver_plain="${tag#v}"
  local tmp
  tmp="$(mktemp)"
  "${EXTRACT[@]}" "$ver_plain" >"$tmp"
  if ! gh release view "$tag" --repo "$REPO" >/dev/null 2>&1; then
    echo "SKIP  $tag — no GitHub Release" >&2
    rm -f "$tmp"
    return 0
  fi
  gh release edit "$tag" --repo "$REPO" --notes-file "$tmp"
  echo "UPDATED  $tag"
  rm -f "$tmp"
}

main() {
  if [[ $# -lt 1 ]]; then
    usage
    exit 2
  fi
  case "$1" in
    --all)
      while IFS= read -r ver; do
        sync_one "$ver"
      done < <(versions_from_changelog)
      ;;
    --check)
      shift
      [[ $# -ge 1 ]] || { usage; exit 2; }
      check_one "$1"
      ;;
    -h|--help)
      usage
      ;;
    *)
      for ver in "$@"; do
        sync_one "$ver"
      done
      ;;
  esac
}

main "$@"
