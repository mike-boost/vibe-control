"""NotebookLM CLI provider adapter (list / add / get / wait / delete)."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class NotebookLMStatus:
    installed: bool
    executable: str | None
    message: str
    version: str | None = None
    auth_checked: bool = False
    auth_state: str = "not_checked"
    auth_details: dict[str, Any] = field(default_factory=dict)
    login_command: str | None = None
    recommended_actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "installed": self.installed,
            "path": self.executable,
            "executable": self.executable,
            "version": self.version,
            "message": self.message,
            "auth_checked": self.auth_checked,
            "auth_state": self.auth_state,
            "auth_details": dict(self.auth_details),
            "login_command": self.login_command,
            "recommended_actions": list(self.recommended_actions),
            "safe_to_sync": False,
        }


class NotebookLMProvider:
    """NotebookLM CLI adapter. Mutation methods are gated by higher-level sync lifecycle."""

    name = "notebooklm"
    command_name = "notebooklm"

    def __init__(self, runner: Any | None = None):
        self._runner = runner or _default_run

    def _invoke(self, argv: list[str], *, timeout: float = 20.0) -> tuple[int, str, str]:
        try:
            return self._runner(argv, timeout=timeout)
        except TypeError:
            return self._runner(argv)

    def which(self) -> str | None:
        return shutil.which(self.command_name)

    def status(self, *, probe_auth: bool = False) -> NotebookLMStatus:
        path = self.which()
        if not path:
            return NotebookLMStatus(
                installed=False,
                executable=None,
                message="notebooklm not found on PATH",
                auth_state="not_checked",
                recommended_actions=[
                    "Install NotebookLM CLI, then run: python -m vibe_control knowledge auth-status --json"
                ],
            )

        version = self._probe_version(path)
        result = NotebookLMStatus(
            installed=True,
            executable=path,
            version=version,
            message="notebooklm found on PATH (mutation not enabled in this pass)",
            login_command="notebooklm login",
            recommended_actions=[
                "Run notebooklm login, then run python -m vibe_control knowledge auth-status --json"
            ],
        )
        if probe_auth:
            auth = self.auth_check()
            result.auth_checked = auth.auth_checked
            result.auth_state = auth.auth_state
            result.auth_details = auth.auth_details
            result.message = auth.message
            if auth.recommended_actions:
                result.recommended_actions = auth.recommended_actions
        return result

    def auth_check(self) -> NotebookLMStatus:
        path = self.which()
        if not path:
            return NotebookLMStatus(
                installed=False,
                executable=None,
                message="notebooklm not found on PATH",
                auth_checked=False,
                auth_state="not_checked",
                recommended_actions=[
                    "Install NotebookLM CLI before checking auth"
                ],
            )

        version = self._probe_version(path)
        # Preferred passive readiness probe from notebooklm auth check --help
        code, stdout, stderr = self._invoke(
            [path, "auth", "check", "--test", "--passive", "--json"]
        )
        if code == 127 or _looks_unsupported(stdout, stderr):
            return NotebookLMStatus(
                installed=True,
                executable=path,
                version=version,
                message="notebooklm auth check is unsupported or unavailable",
                auth_checked=False,
                auth_state="command_unsupported",
                auth_details={"stderr": stderr.strip(), "stdout": stdout.strip()[:500]},
                login_command="notebooklm login",
                recommended_actions=[
                    "Run `notebooklm --help` and inspect auth/session commands.",
                    "Repo fallback remains available via vibe knowledge query",
                ],
            )

        details = _try_parse_json(stdout)
        if code == 0:
            if _payload_refutes_auth(details):
                # Exit code 0 but the payload itself reports failure: the
                # known false-positive trap of older notebooklm CLIs, which
                # could exit 0 without verifying the token. Do not report
                # available when the payload disagrees.
                return NotebookLMStatus(
                    installed=True,
                    executable=path,
                    version=version,
                    message="notebooklm auth check payload reports failure despite exit 0",
                    auth_checked=True,
                    auth_state="auth_failed",
                    auth_details=details or {"raw": stdout.strip()[:500]},
                    login_command="notebooklm login",
                    recommended_actions=[
                        "Run notebooklm login, then re-run python -m vibe_control knowledge auth-status --json",
                        "Repo fallback remains available via vibe knowledge query",
                    ],
                )
            return NotebookLMStatus(
                installed=True,
                executable=path,
                version=version,
                message="notebooklm auth check passed (passive)",
                auth_checked=True,
                auth_state="available",
                auth_details=details or {"raw": stdout.strip()[:500]},
                login_command="notebooklm login",
                recommended_actions=[
                    "Auth looks ready for later dry-run sync planning; "
                    "real provider mutation requires explicit apply approval "
                    "and configured provider readiness"
                ],
            )

        # Non-zero: auth failed or command failed
        state = "auth_failed"
        message = "notebooklm auth check failed"
        if details is None and not stdout.strip():
            state = "command_failed"
            message = "notebooklm auth check command failed"
        return NotebookLMStatus(
            installed=True,
            executable=path,
            version=version,
            message=message,
            auth_checked=True,
            auth_state=state,
            auth_details=details
            or {"stdout": stdout.strip()[:500], "stderr": stderr.strip()[:500], "exit_code": code},
            login_command="notebooklm login",
            recommended_actions=[
                "Run notebooklm login, then re-run python -m vibe_control knowledge auth-status --json",
                "Repo fallback remains available via vibe knowledge query",
            ],
        )

    def login_guide(self) -> dict[str, Any]:
        path = self.which()
        if not path:
            return {
                "installed": False,
                "provider_note": (
                    "NotebookLM CLI provider is unofficial/third-party and may change. "
                    "Repo fallback remains available."
                ),
                "recommended_actions": [
                    "Install NotebookLM CLI first",
                    "Then run: notebooklm login",
                ],
                "help_hint": "Run `notebooklm --help` after install and inspect auth/session commands.",
            }

        code, stdout, stderr = self._invoke([path, "--help"])
        help_text = (stdout or "") + "\n" + (stderr or "")
        has_login = "login" in help_text.lower()
        recommended = []
        if has_login:
            recommended.append(
                "Run notebooklm login, then run python -m vibe_control knowledge auth-status --json"
            )
        else:
            recommended.append(
                "Run `notebooklm --help` and inspect auth/session commands."
            )
        recommended.append(
            "NotebookLM provider is unofficial and may fail or change; repo fallback remains available."
        )
        return {
            "installed": True,
            "path": path,
            "version": self._probe_version(path),
            "detected_login_command": "notebooklm login" if has_login else None,
            "provider_note": (
                "NotebookLM CLI provider is unofficial/third-party and may change. "
                "Repo fallback remains available."
            ),
            "recommended_actions": recommended,
            "help_excerpt": help_text[:800],
        }

    def _probe_version(self, path: str) -> str | None:
        code, stdout, stderr = self._invoke([path, "--version"])
        text = (stdout or stderr or "").strip()
        if code != 0 or not text:
            return None
        return text.splitlines()[0].strip()

    def list_sources(self, *, notebook_ref: str) -> dict[str, Any]:
        path = self.which()
        if not path:
            return {
                "ok": False,
                "code": "NOTEBOOKLM_NOT_INSTALLED",
                "message": "notebooklm not found on PATH",
                "sources": [],
            }
        code, stdout, stderr = self._invoke(
            [path, "source", "list", "--notebook", notebook_ref, "--json"],
            timeout=60.0,
        )
        if _looks_unsupported(stdout, stderr):
            return {
                "ok": False,
                "code": "NOTEBOOKLM_COMMAND_UNSUPPORTED",
                "message": "notebooklm source list is unsupported",
                "sources": [],
                "stderr": stderr.strip()[:500],
            }
        if code != 0:
            return {
                "ok": False,
                "code": "NOTEBOOKLM_COMMAND_FAILED",
                "message": "notebooklm source list failed",
                "sources": [],
                "stderr": stderr.strip()[:500],
                "stdout": stdout.strip()[:500],
                "exit_code": code,
            }
        sources = _parse_source_list(stdout)
        return {"ok": True, "code": "OK", "message": "listed", "sources": sources}

    def add_file_source(
        self,
        *,
        notebook_ref: str,
        file_path: str,
        title: str,
    ) -> dict[str, Any]:
        path = self.which()
        if not path:
            return {
                "ok": False,
                "code": "NOTEBOOKLM_NOT_INSTALLED",
                "message": "notebooklm not found on PATH",
            }
        # Resolve so macOS /var -> /private/var temp paths are concrete files.
        resolved = Path(file_path).resolve()
        code, stdout, stderr = self._invoke(
            [
                path,
                "source",
                "add",
                resolved.as_posix(),
                "--notebook",
                notebook_ref,
                "--type",
                "file",
                "--title",
                title,
                "--follow-symlinks",
                "--json",
            ],
            timeout=120.0,
        )
        if _looks_unsupported(stdout, stderr):
            return {
                "ok": False,
                "code": "NOTEBOOKLM_COMMAND_UNSUPPORTED",
                "message": "notebooklm source add is unsupported",
                "stderr": stderr.strip()[:500],
            }
        if code != 0:
            return {
                "ok": False,
                "code": "NOTEBOOKLM_COMMAND_FAILED",
                "message": "notebooklm source add failed",
                "stderr": stderr.strip()[:500],
                "stdout": stdout.strip()[:500],
                "exit_code": code,
            }
        return {
            "ok": True,
            "code": "OK",
            "message": "source add accepted",
            "result": _try_parse_json(stdout) or {"raw": stdout.strip()[:500]},
        }

    def supports_api_bulk_create(self) -> bool:
        from vibe_control.knowledge.notebooklm_api_ingest import notebooklm_api_available

        return notebooklm_api_available()

    def bulk_create_and_wait(
        self,
        *,
        notebook_ref: str,
        items: list[dict[str, Any]],
        upload_concurrency: int = 8,
        wait_timeout: float = 120.0,
    ) -> dict[str, Any]:
        """Concurrent Python-API creates + multi-id wait (multi-file throughput path).

        ``items``: ``doc_id``, ``file_path``, ``title``. Falls back is caller's job when
        ``supports_api_bulk_create()`` is False.
        """
        from vibe_control.knowledge.notebooklm_api_ingest import (
            bulk_add_files_and_wait,
            notebooklm_api_available,
        )

        if not notebooklm_api_available():
            return {
                "ok": False,
                "code": "NOTEBOOKLM_API_UNAVAILABLE",
                "message": "notebooklm Python package not importable; use CLI ingest path",
                "ingest_path": "api_concurrent",
                "stage_ms": {"add": 0, "wait": 0},
                "results": [],
                "upload_concurrency": upload_concurrency,
            }
        return bulk_add_files_and_wait(
            notebook_id=notebook_ref,
            items=items,
            upload_concurrency=upload_concurrency,
            wait_timeout=wait_timeout,
        )

    def wait_source(
        self,
        *,
        notebook_ref: str,
        source_id: str,
        timeout: float = 120,
        interval: float = 3,
    ) -> dict[str, Any]:
        """Read-only wait using `notebooklm source wait` with get-poll fallback."""
        path = self.which()
        if not path:
            return {
                "ok": False,
                "code": "NOTEBOOKLM_NOT_INSTALLED",
                "status": "unknown",
                "message": "notebooklm not found on PATH",
            }
        code, stdout, stderr = self._invoke(
            [
                path,
                "source",
                "wait",
                source_id,
                "--notebook",
                notebook_ref,
                "--timeout",
                str(int(timeout)),
                "--interval",
                str(max(1, int(interval))),
                "--json",
            ],
            timeout=float(timeout) + 30.0,
        )
        if _looks_unsupported(stdout, stderr):
            # Fallback: poll source get
            return self._poll_get_until_ready(
                notebook_ref=notebook_ref,
                source_id=source_id,
                timeout=timeout,
                interval=interval,
            )
        parsed = _try_parse_json(stdout)
        if code == 0:
            status = "ready"
            if isinstance(parsed, dict):
                status = str(parsed.get("status") or "ready")
            return {"ok": True, "status": status, "result": parsed}
        if code == 2:
            return {
                "ok": False,
                "status": "timeout",
                "code": "SOURCE_WAIT_TIMEOUT",
                "result": parsed,
                "stderr": stderr.strip()[:300],
            }
        # exit 1: missing or processing failed
        status = "error"
        if isinstance(parsed, dict) and parsed.get("status"):
            status = str(parsed.get("status"))
        return {
            "ok": False,
            "status": status,
            "code": "SOURCE_WAIT_FAILED",
            "result": parsed,
            "stderr": stderr.strip()[:300],
        }

    def get_source(self, *, notebook_ref: str, source_id: str) -> dict[str, Any]:
        path = self.which()
        if not path:
            return {"ok": False, "found": False, "status": "unknown"}
        code, stdout, stderr = self._invoke(
            [path, "source", "get", source_id, "--notebook", notebook_ref, "--json"],
            timeout=60.0,
        )
        if code != 0:
            return {
                "ok": False,
                "found": False,
                "status": "not_found",
                "stderr": stderr.strip()[:300],
            }
        parsed = _try_parse_json(stdout)
        source = None
        if isinstance(parsed, dict):
            source = parsed.get("source") if isinstance(parsed.get("source"), dict) else parsed
        if not isinstance(source, dict):
            return {"ok": False, "found": False, "status": "unknown"}
        return {
            "ok": True,
            "found": True,
            "source": source,
            "status": str(source.get("status") or "unknown"),
        }

    def ensure_ask_persona(
        self,
        *,
        notebook_ref: str,
        persona: str,
        response_length: str = "shorter",
    ) -> dict[str, Any]:
        """Apply durable chat persona (closest NotebookLM equivalent to a system prompt).

        NotebookLM has no classical LLM ``system`` role. ``configure --persona`` sets
        notebook-scoped chat policy. Safe to call before each ask (idempotent intent).
        Does not mutate sources.
        """
        path = self.which()
        if not path:
            return {
                "ok": False,
                "code": "NOTEBOOKLM_NOT_INSTALLED",
                "message": "notebooklm not found on PATH",
            }
        code, stdout, stderr = self._invoke(
            [
                path,
                "configure",
                "--notebook",
                notebook_ref,
                "--persona",
                persona,
                "--response-length",
                response_length,
                "--json",
            ],
            timeout=60.0,
        )
        if code != 0:
            return {
                "ok": False,
                "code": "NOTEBOOKLM_CONFIGURE_FAILED",
                "message": "notebooklm configure --persona failed",
                "stderr": stderr.strip()[:500],
                "stdout": stdout.strip()[:500],
                "exit_code": code,
            }
        return {
            "ok": True,
            "code": "OK",
            "message": "persona applied",
            "response_length": response_length,
        }

    def query(self, question: str, *, notebook_ref: str | None = None, **kwargs: Any) -> dict[str, Any]:
        """Readonly NotebookLM ask. Does not add/delete/rename sources."""
        path = self.which()
        if not path:
            return {
                "ok": False,
                "code": "NOTEBOOKLM_NOT_INSTALLED",
                "message": "notebooklm not found on PATH",
                "answer": "",
                "sources": [],
            }
        if not notebook_ref:
            return {
                "ok": False,
                "code": "NOTEBOOKLM_NOTEBOOK_REQUIRED",
                "message": "notebook_ref required for provider query",
                "answer": "",
                "sources": [],
            }
        apply_ask_persona = bool(kwargs.get("apply_ask_persona", True))
        persona = kwargs.get("persona")
        persona_result: dict[str, Any] | None = None
        if apply_ask_persona and persona:
            persona_result = self.ensure_ask_persona(
                notebook_ref=notebook_ref,
                persona=str(persona),
                response_length=str(kwargs.get("response_length") or "shorter"),
            )
            # Persona failure must not block ask; wrapper prompt still carries policy.
            if persona_result.get("ok") is False:
                persona_result = dict(persona_result)
                persona_result["degraded"] = True
        # --new --yes: isolated ask without mutating notebook sources; confirms conversation reset.
        code, stdout, stderr = self._invoke(
            [
                path,
                "ask",
                question,
                "--notebook",
                notebook_ref,
                "--new",
                "--yes",
                "--json",
            ],
            timeout=180.0,
        )
        if _looks_unsupported(stdout, stderr):
            return {
                "ok": False,
                "code": "NOTEBOOKLM_COMMAND_UNSUPPORTED",
                "message": "notebooklm ask is unsupported",
                "answer": "",
                "sources": [],
                "stderr": stderr.strip()[:500],
            }
        if code != 0:
            return {
                "ok": False,
                "code": "NOTEBOOKLM_COMMAND_FAILED",
                "message": "notebooklm ask failed",
                "answer": "",
                "sources": [],
                "stderr": stderr.strip()[:500],
                "stdout": stdout.strip()[:500],
                "exit_code": code,
            }
        parsed = _try_parse_json(stdout)
        answer = ""
        sources: list[dict[str, Any]] = []
        if isinstance(parsed, dict):
            answer = str(
                parsed.get("answer")
                or parsed.get("response")
                or parsed.get("text")
                or ((parsed.get("data") or {}) if isinstance(parsed.get("data"), dict) else {}).get("answer")
                or ""
            )
            raw_sources = parsed.get("sources") or parsed.get("references") or []
            if isinstance(raw_sources, list):
                sources = [s for s in raw_sources if isinstance(s, dict)]
            if not answer and isinstance(parsed.get("data"), dict):
                answer = str(parsed["data"].get("answer") or "")
        if not answer:
            answer = (stdout or "").strip()[:4000]
        out: dict[str, Any] = {
            "ok": True,
            "code": "OK",
            "message": "asked",
            "answer": answer,
            "sources": sources,
        }
        if persona_result is not None:
            out["ask_persona"] = {
                "ok": bool(persona_result.get("ok")),
                "code": persona_result.get("code"),
                "degraded": bool(persona_result.get("degraded")),
                "response_length": persona_result.get("response_length"),
            }
        return out

    def delete_source(self, *, notebook_ref: str, source_id: str) -> dict[str, Any]:
        """Delete a single source by provider source_id (never by title prefix)."""
        path = self.which()
        if not path:
            return {
                "ok": False,
                "code": "NOTEBOOKLM_NOT_INSTALLED",
                "message": "notebooklm not found on PATH",
            }
        if not source_id or not str(source_id).strip():
            return {
                "ok": False,
                "code": "SOURCE_ID_REQUIRED",
                "message": "delete_source requires an exact source_id",
            }
        code, stdout, stderr = self._invoke(
            [
                path,
                "source",
                "delete",
                str(source_id),
                "--notebook",
                notebook_ref,
                "--yes",
                "--json",
            ],
            timeout=60.0,
        )
        if _looks_unsupported(stdout, stderr):
            return {
                "ok": False,
                "code": "NOTEBOOKLM_COMMAND_UNSUPPORTED",
                "message": "notebooklm source delete is unsupported",
                "stderr": stderr.strip()[:500],
            }
        if code != 0:
            return {
                "ok": False,
                "code": "NOTEBOOKLM_COMMAND_FAILED",
                "message": "notebooklm source delete failed",
                "stderr": stderr.strip()[:500],
                "stdout": stdout.strip()[:500],
                "exit_code": code,
            }
        return {
            "ok": True,
            "code": "OK",
            "message": "source deleted",
            "result": _try_parse_json(stdout) or {"raw": stdout.strip()[:500]},
        }

    def _poll_get_until_ready(
        self,
        *,
        notebook_ref: str,
        source_id: str,
        timeout: float,
        interval: float,
    ) -> dict[str, Any]:
        import time

        deadline = time.monotonic() + max(timeout, 0)
        last = "unknown"
        while True:
            got = self.get_source(notebook_ref=notebook_ref, source_id=source_id)
            if not got.get("found"):
                last = "not_found"
            else:
                last = str(got.get("status") or "unknown")
            if last == "ready":
                return {"ok": True, "status": "ready", "via": "get_poll"}
            if last == "error":
                return {"ok": False, "status": "error", "via": "get_poll"}
            if time.monotonic() >= deadline:
                return {
                    "ok": False,
                    "status": "timeout",
                    "code": "SOURCE_WAIT_TIMEOUT",
                    "last_status": last,
                    "via": "get_poll",
                }
            time.sleep(max(interval, 0))


def _default_run(argv: list[str], timeout: float = 20.0) -> tuple[int, str, str]:
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


def _try_parse_json(text: str) -> dict[str, Any] | list[Any] | None:
    text = text.strip()
    if not text:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data


def _payload_refutes_auth(details: dict[str, Any] | list[Any] | None) -> bool:
    """True when a parsed `notebooklm auth check --json` payload explicitly
    reports auth failure, even if the process exit code was 0.

    Older notebooklm CLIs could exit 0 without verifying the token
    (false-positive trap), so explicit payload fields are verified strictly:
    `status` must be "ok" when present, and `checks.token_fetch` must be True
    when present. Payloads without those fields (older CLI format) are not
    refuted and keep the previous exit-code trust behavior.
    """
    if not isinstance(details, dict):
        return False
    status = details.get("status")
    if status is not None and status != "ok":
        return True
    checks = details.get("checks")
    if isinstance(checks, dict) and "token_fetch" in checks:
        return checks["token_fetch"] is not True
    return False


def _parse_source_list(stdout: str) -> list[dict[str, Any]]:
    data = _try_parse_json(stdout)
    if data is None:
        return []
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ("sources", "items", "data"):
            value = data.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
        # single source object
        if "title" in data or "id" in data:
            return [data]
    return []


def _looks_unsupported(stdout: str, stderr: str) -> bool:
    blob = f"{stdout}\n{stderr}".lower()
    if "traceback" in blob:
        return True
    if any(m in blob for m in ("no such command", "unknown command", "invalid choice")):
        return True
    return False
