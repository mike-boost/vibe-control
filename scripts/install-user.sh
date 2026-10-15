#!/usr/bin/env bash
# Install / upgrade / uninstall the `vibe` CLI from this source checkout.
# No pipx and no PyPI required.
#
# Typical local-dev loop (this repo keeps updating):
#   ./scripts/install-user.sh              # install or upgrade from current tree
#   ./scripts/install-user.sh --upgrade    # same as default when already installed
#   ./scripts/install-user.sh --uninstall
#   ./scripts/install-user.sh --status
#
# Override:
#   VIBE_USER_PREFIX   default: ~/.local
#   VIBE_PYTHON        force interpreter (must be 3.11+)

set -euo pipefail

usage() {
  cat <<'EOF'
Install / upgrade / uninstall Vibe Control CLI from this source tree.

  ./scripts/install-user.sh                 # install or upgrade → ~/.local/bin/vibe
  ./scripts/install-user.sh --upgrade       # reinstall from current checkout (same as default)
  ./scripts/install-user.sh --recreate      # wipe user venv, then install with selected Python
  ./scripts/install-user.sh --uninstall     # remove ~/.local/bin/vibe + user venv
  ./scripts/install-user.sh --status        # show link / venv / versions
  ./scripts/install-user.sh --help

Python selection (first match, unless VIBE_PYTHON is set):
  python, python3.13, python3.12, python3.11, python3
  (must be 3.11+; conda activate first if your default python3 is too old)

Does not use PyPI. pipx remains an optional alternative.

After install/upgrade, also aligns thin agent skills into ~/.agents/skills
(symlink to the installed package). Skip with: VIBE_SKIP_SKILLS=1
EOF
}

PREFIX="${VIBE_USER_PREFIX:-${HOME}/.local}"
BIN_DIR="${PREFIX}/bin"
DATA_DIR="${PREFIX}/share/vibe-control"
VENV_DIR="${DATA_DIR}/venv"
LINK_PATH="${BIN_DIR}/vibe"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

ACTION="upgrade"
RECREATE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    "" ) shift || true ;;
    --upgrade | upgrade | install | --install )
      ACTION="upgrade"
      shift
      ;;
    --recreate | recreate )
      ACTION="upgrade"
      RECREATE=1
      shift
      ;;
    --uninstall | uninstall )
      ACTION="uninstall"
      shift
      ;;
    --status | status )
      ACTION="status"
      shift
      ;;
    -h | --help | help )
      usage
      exit 0
      ;;
    * )
      echo "error: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

python_ok() {
  local bin="$1"
  command -v "$bin" >/dev/null 2>&1 || return 1
  "$bin" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null
}

resolve_python() {
  if [[ -n "${VIBE_PYTHON:-}" ]]; then
    if ! python_ok "${VIBE_PYTHON}"; then
      echo "error: VIBE_PYTHON=${VIBE_PYTHON} is missing or < 3.11" >&2
      exit 1
    fi
    echo "${VIBE_PYTHON}"
    return
  fi
  local cand
  # Prefer bare `python` first so `conda activate` / pyenv shims win over stale python3.
  for cand in python python3.13 python3.12 python3.11 python3; do
    if python_ok "$cand"; then
      echo "$cand"
      return
    fi
  done
  echo "error: Python 3.11+ required." >&2
  echo "hint: activate a 3.11+ env (e.g. conda activate py313), or set VIBE_PYTHON=/path/to/python" >&2
  echo "hint: your current python3 may be too old (e.g. 3.10)." >&2
  exit 1
}

venv_python() {
  if [[ -x "${VENV_DIR}/bin/python" ]]; then
    echo "${VENV_DIR}/bin/python"
  else
    return 1
  fi
}

show_status() {
  echo "prefix:   ${PREFIX}"
  echo "link:     ${LINK_PATH}"
  if [[ -L "${LINK_PATH}" ]]; then
    echo "link ->   $(readlink "${LINK_PATH}")"
  elif [[ -e "${LINK_PATH}" ]]; then
    echo "link:     present (not a symlink)"
  else
    echo "link:     missing"
  fi
  echo "venv:     ${VENV_DIR}"
  if vp="$(venv_python 2>/dev/null)"; then
    echo "venv py:  $("$vp" -c 'import sys; print(sys.version.split()[0])') ($vp)"
    if [[ -x "${VENV_DIR}/bin/vibe" ]]; then
      echo "venv vibe:$("${VENV_DIR}/bin/vibe" --version 2>/dev/null || echo 'unavailable')"
    fi
  else
    echo "venv py:  missing"
  fi
  if command -v vibe >/dev/null 2>&1; then
    echo "PATH vibe:$(command -v vibe)"
    echo "PATH ver: $(vibe --version 2>/dev/null || true)"
  else
    echo "PATH vibe: not on PATH"
  fi
}

uninstall_user() {
  if [[ -L "${LINK_PATH}" ]] || [[ -f "${LINK_PATH}" ]]; then
    rm -f "${LINK_PATH}"
    echo "removed ${LINK_PATH}"
  else
    echo "no symlink at ${LINK_PATH}"
  fi
  if [[ -d "${VENV_DIR}" ]]; then
    rm -rf "${VENV_DIR}"
    echo "removed ${VENV_DIR}"
  else
    echo "no venv at ${VENV_DIR}"
  fi
  rmdir "${DATA_DIR}" 2>/dev/null || true
  echo "uninstall complete"
}

ensure_venv() {
  local selected="$1"
  local selected_ver
  selected_ver="$("$selected" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"

  if [[ "${RECREATE}" -eq 1 ]] && [[ -d "${VENV_DIR}" ]]; then
    echo "==> recreating venv (requested)"
    rm -rf "${VENV_DIR}"
  fi

  if [[ -x "${VENV_DIR}/bin/python" ]]; then
    local existing_ver
    existing_ver="$("${VENV_DIR}/bin/python" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
    if [[ "${existing_ver}" != "${selected_ver}" ]]; then
      echo "==> recreating venv (was Python ${existing_ver}, selected ${selected_ver})"
      rm -rf "${VENV_DIR}"
    fi
  fi

  if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
    echo "==> creating venv at ${VENV_DIR} with ${selected} (${selected_ver})"
    mkdir -p "${DATA_DIR}"
    "${selected}" -m venv "${VENV_DIR}"
  else
    echo "==> reusing venv at ${VENV_DIR} (Python ${selected_ver})"
  fi
}

upgrade_user() {
  local selected
  selected="$(resolve_python)"
  local selected_full
  selected_full="$("$selected" -c 'import sys; print(sys.version.split()[0])')"
  echo "==> using interpreter: ${selected} (${selected_full})"

  if [[ ! -f "${REPO_ROOT}/pyproject.toml" ]]; then
    echo "error: pyproject.toml not found at ${REPO_ROOT}" >&2
    exit 1
  fi

  mkdir -p "${BIN_DIR}" "${DATA_DIR}"
  ensure_venv "${selected}"

  # shellcheck disable=SC1091
  source "${VENV_DIR}/bin/activate"
  python -m pip install --upgrade pip
  echo "==> upgrading vibe-control from ${REPO_ROOT}"
  python -m pip install --upgrade --force-reinstall "${REPO_ROOT}"
  deactivate || true

  local vibe_bin="${VENV_DIR}/bin/vibe"
  if [[ ! -x "${vibe_bin}" ]]; then
    echo "error: expected executable missing: ${vibe_bin}" >&2
    exit 1
  fi

  ln -sfn "${vibe_bin}" "${LINK_PATH}"
  echo "==> linked ${LINK_PATH} -> ${vibe_bin}"

  if [[ "${VIBE_SKIP_SKILLS:-0}" != "1" ]]; then
    echo "==> aligning thin agent skills (~/.agents/skills → package)"
    if "${vibe_bin}" skills install --apply --force --json >/dev/null; then
      echo "==> skills aligned (check: vibe skills status --json)"
    else
      echo "NOTE: skills align failed; run: vibe skills install --apply --force --json" >&2
    fi
  else
    echo "==> skipped skills align (VIBE_SKIP_SKILLS=1)"
  fi

  if ! command -v vibe >/dev/null 2>&1; then
    echo
    echo "NOTE: ${BIN_DIR} is not on your PATH yet. Add:"
    echo "  export PATH=\"${BIN_DIR}:\$PATH\""
    echo "Then re-open the shell, or run: ${LINK_PATH} --version"
  else
    echo
    vibe --version
  fi
  echo
  echo "Done. Next: vibe doctor"
  echo "Later: ./scripts/install-user.sh --upgrade | --uninstall | --status"
}

case "${ACTION}" in
  status ) show_status ;;
  uninstall ) uninstall_user ;;
  upgrade ) upgrade_user ;;
  * )
    echo "error: internal action ${ACTION}" >&2
    exit 2
    ;;
esac
