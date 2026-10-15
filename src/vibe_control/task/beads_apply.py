"""Real Beads apply boundary: argv builders + dual-gate guarded executor.

Verified against local ``bd create --help`` / ``bd update --help`` (bd 1.1.0):
- create: --description, --metadata, --spec-id, --silent, --dry-run
- update: --title, --description, --metadata, --spec-id, --claim (FORBIDDEN)

Option A live mutation requires ALL of:
1. --apply --provider beads
2. --autonomous-managed
3. --confirm-beads-live-apply
4. VIBE_BEADS_LIVE_APPLY=1
5. product_ready + safe managed plan (enforced in apply_cli)

Env alone or confirm alone must never unlock live Beads mutation.
Delete / close / claim are never built.
Default local gates never set VIBE_BEADS_LIVE_APPLY.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from typing import Any, Callable

from vibe_control.task.apply_models import ApplyOperation, EXECUTABLE_OP_TYPES

Runner = Callable[[list[str]], Any]

LIVE_APPLY_ENV = "VIBE_BEADS_LIVE_APPLY"
CONFIRM_CLI_FLAG = "--confirm-beads-live-apply"
AUTONOMOUS_MANAGED_FLAG = "--autonomous-managed"


class BeadsApplyBlocked(RuntimeError):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def beads_live_apply_env_ok() -> bool:
    return os.environ.get(LIVE_APPLY_ENV, "").strip() in {"1", "true", "yes"}


def beads_live_apply_approved() -> bool:
    return beads_live_apply_env_ok()


def live_apply_gates_satisfied(*, env_ok: bool | None = None, confirm: bool = False) -> bool:
    """Both env gate and explicit confirm required."""
    env = beads_live_apply_env_ok() if env_ok is None else env_ok
    return bool(env) and bool(confirm)


def build_managed_metadata(op: ApplyOperation) -> str:
    """Stable metadata JSON for bd --metadata (identity + snapshot linkage)."""
    payload = {
        "managed_by": "vibe-control",
        "managed_key": op.managed_key,
        "project_id": op.project_id,
        "ssot_id": op.ssot_id,
        "ssot_path": op.ssot_path,
        "ssot_anchor": op.ssot_anchor,
        "task_kind": op.task_kind,
        "ssot_snapshot_hash": op.ssot_snapshot_hash,
        "source_item_hash": op.source_item_hash,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def build_bd_create_argv(
    op: ApplyOperation,
    *,
    bd_bin: str = "bd",
    dry_run: bool = False,
    silent: bool = False,
) -> list[str]:
    if op.op_type != "create_managed":
        raise BeadsApplyBlocked(
            "BD_CREATE_OP_INVALID",
            f"create argv requires create_managed, got {op.op_type}",
        )
    title = op.title or "untitled"
    description = op.description or ""
    argv = [bd_bin, "create", title, "--description", description]
    if op.ssot_id:
        argv.extend(["--spec-id", op.ssot_id])
    argv.extend(["--metadata", build_managed_metadata(op)])
    if silent:
        argv.append("--silent")
    if dry_run:
        argv.append("--dry-run")
    return argv


def build_bd_update_argv(op: ApplyOperation, *, bd_bin: str = "bd") -> list[str]:
    if op.op_type != "update_managed":
        raise BeadsApplyBlocked(
            "BD_UPDATE_OP_INVALID",
            f"update argv requires update_managed, got {op.op_type}",
        )
    if not op.provider_task_id:
        raise BeadsApplyBlocked("BD_UPDATE_MISSING_ID", "update requires provider_task_id")
    argv = [bd_bin, "update", op.provider_task_id]
    if op.title:
        argv.extend(["--title", op.title])
    if op.description is not None:
        argv.extend(["--description", op.description])
    if op.ssot_id:
        argv.extend(["--spec-id", op.ssot_id])
    argv.extend(["--metadata", build_managed_metadata(op)])
    return argv


def assert_no_forbidden_mutation_argv(argv: list[str]) -> None:
    forbidden = {"delete", "close", "--claim", "claim"}
    for part in argv:
        if part in forbidden or part.startswith("--claim"):
            raise BeadsApplyBlocked(
                "BD_DELETE_OR_CLAIM_FORBIDDEN",
                f"forbidden mutation token in argv: {part}",
                {"argv": argv},
            )


def parse_bd_create_id(stdout: str, stderr: str = "") -> str | None:
    """Extract issue id from bd create --silent or normal create output."""
    text = (stdout or "").strip()
    if text:
        first = text.splitlines()[0].strip()
        if re.fullmatch(r"[A-Za-z0-9._:-]+", first) and " " not in first:
            return first
    combined = f"{stdout}\n{stderr}"
    match = re.search(r"\b((?:bd|beads)-[A-Za-z0-9]+)\b", combined)
    if match:
        return match.group(1)
    return None


def _id_hash(provider_task_id: str | None) -> str | None:
    if not provider_task_id:
        return None
    digest = hashlib.sha256(provider_task_id.encode("utf-8")).hexdigest()[:12]
    return f"sha256:{digest}"


def subprocess_bd_runner(argv: list[str], *, timeout_sec: float = 60.0) -> dict[str, Any]:
    """Run a verified bd argv list. Callers must pass assert_no_forbidden first."""
    assert_no_forbidden_mutation_argv(argv)
    proc = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout_sec,
    )
    provider_task_id = None
    if len(argv) > 1 and argv[1] == "create":
        provider_task_id = parse_bd_create_id(proc.stdout or "", proc.stderr or "")
    return {
        "argv_verb": argv[1] if len(argv) > 1 else None,
        "returncode": proc.returncode,
        "stdout": proc.stdout or "",
        "stderr": proc.stderr or "",
        "provider_task_id": provider_task_id,
    }


def execute_beads_apply_guarded(
    operations: list[ApplyOperation],
    *,
    runner: Runner,
    live_approved: bool | None = None,
    confirm: bool = False,
    silent_create: bool = True,
) -> list[dict[str, Any]]:
    """Build and run bd create/update argv under dual gate.

    Requires env gate AND confirm. Env alone or confirm alone raises.
    Delete/close/claim never executed.
    Returns list of result dicts (argv summary + runner return).
    """
    env_ok = beads_live_apply_env_ok() if live_approved is None else live_approved
    executable = [o for o in operations if o.executable and o.op_type in EXECUTABLE_OP_TYPES]

    if not live_apply_gates_satisfied(env_ok=env_ok, confirm=confirm):
        missing = []
        if not env_ok:
            missing.append(f"{LIVE_APPLY_ENV}=1")
        if not confirm:
            missing.append(CONFIRM_CLI_FLAG)
        raise BeadsApplyBlocked(
            "BEADS_LIVE_APPLY_BLOCKED",
            "Live Beads apply blocked; requires env gate AND explicit confirm "
            f"(missing: {', '.join(missing)})",
            {"operation_count": len(executable), "env_ok": env_ok, "confirm": confirm},
        )

    recorded: list[dict[str, Any]] = []
    for op in executable:
        if op.op_type == "create_managed":
            argv = build_bd_create_argv(op, silent=silent_create)
        elif op.op_type == "update_managed":
            argv = build_bd_update_argv(op)
        else:
            continue
        assert_no_forbidden_mutation_argv(argv)
        result = runner(argv)
        entry: dict[str, Any] = {
            "op_type": op.op_type,
            "managed_key": op.managed_key,
            "ssot_anchor": op.ssot_anchor,
            "argv_verb": argv[1] if len(argv) > 1 else None,
            "has_metadata": "--metadata" in argv,
            "has_spec_id": "--spec-id" in argv,
            "forbidden_tokens": False,
        }
        write_ok = False
        if isinstance(result, dict):
            pid = result.get("provider_task_id")
            rc = result.get("returncode")
            entry.update(
                {
                    "returncode": rc,
                    "provider_task_id": pid,
                    "provider_task_id_hash": _id_hash(str(pid) if pid else None),
                }
            )
            # Only successful provider writes count as completed effects.
            if rc == 0:
                write_ok = True
                if pid and op.op_type == "create_managed":
                    op.provider_task_id = str(pid)
                    op.provider_task_id_hash = _id_hash(str(pid))
        elif result is None:
            # dry construction runner used in tests
            entry["returncode"] = 0
            write_ok = True
        if write_ok:
            op.mutation = True
            # Record completed effect before the next provider call.
            entry["effect"] = {
                "kind": "task_write",
                "target": f"task.{op.op_type}",
                "status": "completed",
            }
        recorded.append(entry)
    return recorded
