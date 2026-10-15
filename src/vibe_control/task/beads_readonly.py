"""Readonly Beads TaskProvider adapter (Phase 11A/11B).

May call only readonly bd subcommands: list / show / ready / status / version.
``prime`` remains in the allowlist as a provider-local context helper (not used by
default reconcile/apply paths; never with --claim).
Never create/update/delete/close/claim. ``bd ready --claim`` is forbidden.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any, Callable

from vibe_control.task.models import TaskRecord

Runner = Callable[[list[str]], tuple[int, str, str]]

ALLOWED_BD_SUBCOMMANDS = frozenset({"list", "show", "ready", "status", "version", "prime"})
FORBIDDEN_BD_SUBCOMMANDS = frozenset(
    {
        "init",
        "create",
        "update",
        "delete",
        "close",
        "reopen",
        "dep",
        "depend",
        "import",
        "export",
        "sync",
        "daemon",
        "assign",
        "claim",
    }
)
FORBIDDEN_BD_FLAGS = frozenset({"--claim", "--allow-add"})


class BeadsReadonlyError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def _default_run(argv: list[str], timeout: float = 30.0) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except FileNotFoundError:
        return 127, "", "executable not found"
    except subprocess.TimeoutExpired:
        return 124, "", "command timed out"


def assert_readonly_bd_argv(argv: list[str]) -> None:
    """Fail closed if a mutation-capable bd subcommand or flag appears."""
    if not argv:
        raise BeadsReadonlyError("BD_ARGV_EMPTY", "empty bd argv")
    for part in argv:
        if part in FORBIDDEN_BD_FLAGS or part.startswith("--claim"):
            raise BeadsReadonlyError(
                "BD_MUTATION_FORBIDDEN",
                f"bd flag not allowed in readonly adapter: {part}",
                {"argv": argv},
            )
    sub = None
    for part in argv[1:]:
        if part.startswith("-"):
            continue
        sub = part
        break
    if sub is None:
        raise BeadsReadonlyError("BD_SUBCOMMAND_MISSING", "bd subcommand missing", {"argv": argv})
    if sub in FORBIDDEN_BD_SUBCOMMANDS or sub not in ALLOWED_BD_SUBCOMMANDS:
        raise BeadsReadonlyError(
            "BD_MUTATION_FORBIDDEN",
            f"bd subcommand not allowed in readonly adapter: {sub}",
            {"argv": argv, "subcommand": sub},
        )


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if isinstance(item, dict):
                for key in ("id", "issue_id", "depends_on", "target", "to"):
                    if item.get(key):
                        out.append(str(item[key]))
                        break
                else:
                    out.append(str(item))
            else:
                out.append(str(item))
        return out
    return [str(value)]


def parse_beads_issue(raw: dict[str, Any]) -> TaskRecord:
    """Map a Beads JSON issue object into TaskRecord (tolerant field names)."""
    provider_task_id = None
    for key in ("id", "issue_id", "key", "name"):
        if raw.get(key) is not None and str(raw.get(key)).strip() != "":
            provider_task_id = str(raw[key])
            break
    title = str(raw.get("title") or raw.get("summary") or raw.get("name") or "")
    description = str(
        raw.get("description")
        or raw.get("body")
        or raw.get("desc")
        or raw.get("content")
        or ""
    )
    relations: list[str] = []
    for key in ("dependencies", "depends_on", "deps", "relations", "blocks", "blocked_by"):
        relations.extend(_as_list(raw.get(key)))
    seen: set[str] = set()
    deduped: list[str] = []
    for item in relations:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return TaskRecord(
        provider_task_id=provider_task_id,
        title=title,
        description=description,
        relations=deduped,
        raw=dict(raw),
    )


def parse_beads_list_json(stdout: str) -> list[TaskRecord]:
    text = (stdout or "").strip()
    if not text:
        return []
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise BeadsReadonlyError(
            "BD_LIST_JSON_INVALID",
            f"bd list/ready --json returned invalid JSON: {exc}",
        ) from exc
    if payload is None:
        return []
    if isinstance(payload, dict):
        for key in ("issues", "items", "data", "results", "ready"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
        else:
            return [parse_beads_issue(payload)]
    if not isinstance(payload, list):
        raise BeadsReadonlyError(
            "BD_LIST_JSON_SHAPE",
            "bd list/ready --json must be a JSON array or object with issues list",
            {"type": type(payload).__name__},
        )
    tasks: list[TaskRecord] = []
    for item in payload:
        if isinstance(item, dict):
            tasks.append(parse_beads_issue(item))
    return tasks


class BeadsReadonlyProvider:
    """Readonly TaskProvider backed by bd list/show/ready (no mutation)."""

    name = "beads"

    def __init__(
        self,
        *,
        runner: Runner | None = None,
        executable: str | None = None,
        enrich_with_show: bool = False,
    ):
        self._runner = runner or _default_run
        self._executable = executable
        self.available = False
        self.last_error: str | None = None
        self.warnings: list[str] = []
        self.enrich_with_show = enrich_with_show
        self.invoked_commands: list[list[str]] = []
        self.ready_queue_ok: bool | None = None
        self._cached_tasks: list[TaskRecord] | None = None
        self._cached_ready: list[TaskRecord] | None = None

    def which(self) -> str | None:
        if self._executable:
            return self._executable
        return shutil.which("bd")

    def _run_readonly(self, argv: list[str]) -> tuple[int, str, str]:
        assert_readonly_bd_argv(argv)
        self.invoked_commands.append(list(argv))
        return self._runner(argv)

    def list_tasks(self) -> list[TaskRecord]:
        """Inventory via ``bd list --json``. Parse failure ⇒ unavailable (not empty)."""
        if self._cached_tasks is not None and self.available:
            return list(self._cached_tasks)

        self.warnings = []
        self.last_error = None
        path = self.which()
        if not path:
            self.available = False
            self.last_error = "bd not found on PATH"
            self.warnings.append("bd not found on PATH; Beads readonly provider unavailable")
            return []
        argv = [path, "list", "--json"]
        code, stdout, stderr = self._run_readonly(argv)
        if code != 0:
            self.available = False
            self.last_error = (stderr or stdout or f"bd list exited {code}").strip()
            self.warnings.append(f"bd list failed: {self.last_error}")
            return []
        try:
            tasks = parse_beads_list_json(stdout)
        except BeadsReadonlyError as exc:
            self.available = False
            self.last_error = exc.message
            self.warnings.append(exc.message)
            return []

        self.available = True
        if self.enrich_with_show:
            enriched: list[TaskRecord] = []
            for task in tasks:
                if task.description.strip() or not task.provider_task_id:
                    enriched.append(task)
                    continue
                show_argv = [path, "show", task.provider_task_id, "--json"]
                scode, sout, serr = self._run_readonly(show_argv)
                if scode != 0:
                    self.warnings.append(
                        f"bd show failed for {task.provider_task_id}: {(serr or sout).strip()}"
                    )
                    enriched.append(task)
                    continue
                try:
                    shown = parse_beads_list_json(sout)
                    enriched.append(shown[0] if shown else task)
                except BeadsReadonlyError as exc:
                    self.warnings.append(exc.message)
                    enriched.append(task)
            tasks = enriched
        self._cached_tasks = list(tasks)
        return list(tasks)

    def list_ready_tasks(self) -> list[TaskRecord]:
        """Ready queue via ``bd ready --json`` (blocker-aware). Never uses --claim."""
        if self._cached_ready is not None and self.ready_queue_ok is True:
            return list(self._cached_ready)

        path = self.which()
        if not path:
            self.ready_queue_ok = False
            self.warnings.append("bd not found; ready queue unavailable")
            return []
        argv = [path, "ready", "--json"]
        code, stdout, stderr = self._run_readonly(argv)
        if code != 0:
            self.ready_queue_ok = False
            self.warnings.append(
                f"bd ready failed: {(stderr or stdout or f'exit {code}').strip()}"
            )
            return []
        try:
            ready = parse_beads_list_json(stdout)
        except BeadsReadonlyError as exc:
            self.ready_queue_ok = False
            self.warnings.append(exc.message)
            return []
        self.ready_queue_ok = True
        self._cached_ready = list(ready)
        return list(ready)
