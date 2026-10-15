"""Cursor Agent CLI host adapter for Skill Assay."""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Any, Callable

from vibe_control.skill_assay.adapters import HostDoctorResult, HostRunResult
from vibe_control.skill_assay.adapters.base import (
    inject_skill_tree,
    mount_target_repo,
    run_subprocess,
    safe_rmtree,
    scrub_env,
)
from vibe_control.skill_assay.constants import ASSISTANT_TEXT_LIMIT
from vibe_control.skill_assay.errors import SkillAssayError
from vibe_control.skill_assay.normalize import normalize_fields, sha256_text
from vibe_control.skill_assay.redaction import redact_text, truncate_events

Runner = Callable[..., dict[str, Any]]


def parse_agent_stream_json(stdout: str) -> dict[str, Any]:
    """Parse Cursor `agent -p --output-format stream-json` NDJSON stdout."""
    events: list[dict[str, Any]] = []
    assistant_chunks: list[str] = []
    model_resolved: str | None = None
    result_ok: bool | None = None
    result_event: dict[str, Any] | None = None
    tool_summary: list[dict[str, Any]] = []
    skill_invocation = "unknown"
    unknowns: list[str] = []

    for line in (stdout or "").splitlines():
        raw = line.strip()
        if not raw:
            continue
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            unknowns.append("stream_json_line_invalid")
            continue
        if not isinstance(event, dict):
            unknowns.append("stream_json_line_not_object")
            continue
        events.append(event)
        etype = str(event.get("type") or event.get("event") or "").lower()
        subtype = str(event.get("subtype") or "").lower()

        if etype in {"system", "init"} or subtype == "init":
            model = event.get("model")
            message = event.get("message")
            if model is None and isinstance(message, dict):
                model = message.get("model")
            if isinstance(model, str) and model.strip():
                model_resolved = model.strip()

        if etype in {"assistant", "assistant_message", "message"}:
            text = _extract_assistant_text(event)
            if text:
                assistant_chunks.append(text)
            if "skill" in text.lower() or str(event.get("skill") or ""):
                skill_invocation = "observed"

        if etype in {"tool_call", "tool", "tool_result"}:
            name = (
                str(event.get("name") or event.get("tool") or event.get("toolName") or "tool")
            )
            ok = event.get("success")
            if ok is None:
                ok = str(event.get("status") or "").lower() not in {"error", "failed"}
            tool_summary.append(
                {
                    "name": name,
                    "ok": bool(ok),
                    "summary": redact_text(str(event.get("summary") or event.get("result") or "")[:200]),
                }
            )

        if etype == "result" or subtype in {"success", "error", "failure"}:
            result_event = event
            if event.get("is_error") is True or subtype in {"error", "failure"}:
                result_ok = False
            elif event.get("success") is True or subtype == "success":
                result_ok = True
            elif "result" in event and isinstance(event.get("result"), str):
                result_ok = True
            model = event.get("model")
            if isinstance(model, str) and model.strip():
                model_resolved = model.strip()
            text = _extract_assistant_text(event)
            if text:
                assistant_chunks.append(text)

    assistant_text = "\n".join(chunk for chunk in assistant_chunks if chunk).strip()
    if result_ok is None and result_event is None:
        unknowns.append("missing_terminal_result_event")
    return {
        "events": events,
        "assistant_text": assistant_text,
        "model_resolved": model_resolved,
        "result_ok": result_ok,
        "tool_summary": tool_summary,
        "skill_invocation": skill_invocation,
        "unknowns": sorted(set(unknowns)),
    }


def _extract_assistant_text(event: dict[str, Any]) -> str:
    if isinstance(event.get("text"), str):
        return event["text"]
    if isinstance(event.get("content"), str):
        return event["content"]
    message = event.get("message")
    if isinstance(message, str):
        return message
    if isinstance(message, dict):
        if isinstance(message.get("content"), str):
            return message["content"]
        content = message.get("content")
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif isinstance(item, str):
                    parts.append(item)
            return "".join(parts)
        if isinstance(message.get("text"), str):
            return message["text"]
    result = event.get("result")
    if isinstance(result, str):
        return result
    return ""


class CursorHostAdapter:
    host_id = "cursor"

    def __init__(
        self,
        *,
        agent_bin: str = "agent",
        runner: Runner | None = None,
        which: Callable[[str], str | None] | None = None,
    ) -> None:
        self._agent_bin = agent_bin
        self._runner = runner or run_subprocess
        self._which = which or shutil.which
        self._cleanup_warnings: list[str] = []

    def doctor(self) -> HostDoctorResult:
        blockers: list[str] = []
        details: dict[str, Any] = {}
        resolved = self._which(self._agent_bin)
        if not resolved:
            return HostDoctorResult(
                host_id=self.host_id,
                ok=False,
                support_state="unavailable",
                blockers=["SKILL_ASSAY_CURSOR_CLI_MISSING"],
                details={"agent_bin": self._agent_bin},
            )
        details["agent_bin"] = resolved

        version = self._runner(
            [resolved, "--version"],
            cwd=Path.cwd(),
            env=scrub_env(),
            timeout_seconds=30,
        )
        details["version"] = (version.get("stdout") or "").strip() or (
            version.get("stderr") or ""
        ).strip()
        if version.get("timed_out") or int(version.get("returncode") or 0) != 0:
            blockers.append("SKILL_ASSAY_CURSOR_CLI_MISSING")

        status = self._runner(
            [resolved, "status", "--format", "json"],
            cwd=Path.cwd(),
            env=scrub_env(),
            timeout_seconds=30,
        )
        auth_ok = False
        try:
            payload = json.loads((status.get("stdout") or "").strip() or "{}")
        except json.JSONDecodeError:
            payload = {}
        if isinstance(payload, dict):
            auth_ok = bool(
                payload.get("isAuthenticated")
                or payload.get("authenticated")
                or str(payload.get("status") or "").lower() == "authenticated"
            )
            details["auth_status"] = {
                "status": payload.get("status"),
                "isAuthenticated": payload.get("isAuthenticated"),
                "email": (payload.get("userInfo") or {}).get("email")
                if isinstance(payload.get("userInfo"), dict)
                else None,
            }
        if not auth_ok:
            blockers.append("SKILL_ASSAY_CURSOR_AUTH_REQUIRED")

        models = self._runner(
            [resolved, "models"],
            cwd=Path.cwd(),
            env=scrub_env(),
            timeout_seconds=60,
        )
        model_text = (models.get("stdout") or "") + "\n" + (models.get("stderr") or "")
        model_lines = [
            line.strip()
            for line in model_text.splitlines()
            if line.strip() and not line.lower().startswith("available models")
        ]
        details["model_count"] = len(model_lines)
        if not model_lines:
            blockers.append("SKILL_ASSAY_CURSOR_MODEL_UNAVAILABLE")

        ok = not blockers
        return HostDoctorResult(
            host_id=self.host_id,
            ok=ok,
            support_state="supported" if ok else "unavailable",
            blockers=blockers,
            details=details,
        )

    def prepare(
        self,
        *,
        assay_id: str,
        run_index: int,
        skill_snapshot: Path,
        work_root: Path,
        scenario: dict[str, Any],
    ) -> dict[str, Any]:
        session_id = f"cursor-session-{uuid.uuid4().hex[:12]}"
        workspace = Path(work_root) / f"run-{run_index}"
        workspace.mkdir(parents=True, exist_ok=True)
        skill_dest = inject_skill_tree(
            skill_snapshot=skill_snapshot,
            workspace=workspace,
            layout="cursor",
        )
        artifact = workspace / "artifact"
        artifact.mkdir(parents=True, exist_ok=True)
        target_repo = scenario.get("target_repo")
        mounted = None
        if target_repo:
            mounted = mount_target_repo(
                workspace=workspace,
                target_repo=Path(str(target_repo)),
            ).as_posix()
        return {
            "session_id": session_id,
            "workspace": workspace.as_posix(),
            "artifact_dir": artifact.as_posix(),
            "skill_dest": skill_dest.as_posix(),
            "skill_id": skill_snapshot.name,
            "target_repo_mount": mounted,
            "run_index": run_index,
            "assay_id": assay_id,
        }

    def run(
        self,
        *,
        prepared: dict[str, Any],
        scenario: dict[str, Any],
    ) -> HostRunResult:
        workspace = Path(prepared["workspace"])
        artifact = Path(prepared["artifact_dir"])
        skill_id = str(prepared.get("skill_id") or "skill")
        profile = str(scenario.get("execution_profile") or "response_only")
        timeout = int(scenario.get("timeout_seconds") or 300)
        prompt = self._build_prompt(skill_id=skill_id, scenario=scenario)

        resolved = self._which(self._agent_bin) or self._agent_bin
        argv = [
            resolved,
            "-p",
            "--output-format",
            "stream-json",
            "--workspace",
            str(workspace),
            "--trust",
        ]
        if profile == "response_only":
            argv.extend(["--mode", "ask", "--sandbox", "enabled"])
        else:
            # Business-quality runs need script execution against mounted target.
            argv.extend(["--sandbox", "disabled"])
        model = scenario.get("model")
        if model:
            argv.extend(["--model", str(model)])
        if prepared.get("target_repo_mount"):
            prompt = (
                f"{prompt}\n\n"
                f"TARGET_REPO_MOUNT={prepared['target_repo_mount']}\n"
                "Analyze that mounted repository path.\n"
            )
        argv.append(prompt)

        env = scrub_env()
        proc = self._runner(
            argv,
            cwd=workspace,
            env=env,
            timeout_seconds=timeout,
        )
        (artifact / "stdout.ndjson").write_text(proc.get("stdout") or "", encoding="utf-8")
        (artifact / "stderr.txt").write_text(proc.get("stderr") or "", encoding="utf-8")
        (artifact / "argv.json").write_text(
            json.dumps({"argv": argv[:-1] + ["<prompt>"], "prompt_chars": len(prompt)}, indent=2)
            + "\n",
            encoding="utf-8",
        )

        if proc.get("timed_out"):
            return HostRunResult(
                session_id=str(prepared["session_id"]),
                workspace_path=str(workspace),
                exit_status=int(proc.get("returncode") or -1),
                fields={},
                events=[{"type": "timeout"}],
                artifact_dir=str(artifact),
                unknowns=["timeout"],
                error_code="SKILL_ASSAY_CURSOR_TIMEOUT",
                error_message="Cursor agent timed out",
                assistant_text="",
                model_requested=str(model) if model else None,
                skill_invocation="requested",
                isolation=self._isolation(),
            )

        parsed = parse_agent_stream_json(proc.get("stdout") or "")
        exit_status = int(proc.get("returncode") or 0)
        result_ok = parsed.get("result_ok")
        success = exit_status == 0 and result_ok is True
        error_code = None
        error_message = None
        if not success:
            if result_ok is False:
                error_code = "SKILL_ASSAY_CURSOR_RUN_FAILED"
                error_message = "Cursor agent terminal result reported failure"
            elif result_ok is None:
                error_code = "SKILL_ASSAY_CURSOR_OUTPUT_INVALID"
                error_message = "Cursor agent stream-json missing success result"
            else:
                error_code = "SKILL_ASSAY_CURSOR_RUN_FAILED"
                error_message = f"Cursor agent exited with code {exit_status}"

        assistant_text = str(parsed.get("assistant_text") or "")
        return HostRunResult(
            session_id=str(prepared["session_id"]),
            workspace_path=str(workspace),
            exit_status=exit_status if success else (exit_status or 1),
            fields={},
            events=list(parsed.get("events") or []),
            artifact_dir=str(artifact),
            unknowns=list(parsed.get("unknowns") or []),
            error_code=error_code,
            error_message=error_message,
            assistant_text=assistant_text,
            model_requested=str(model) if model else None,
            model_resolved=parsed.get("model_resolved"),
            tool_summary=list(parsed.get("tool_summary") or []),
            skill_invocation=(
                "observed"
                if parsed.get("skill_invocation") == "observed"
                else "requested"
            ),
            usage={},
            isolation=self._isolation(),
        )

    def normalize(
        self,
        *,
        raw: HostRunResult,
        scenario: dict[str, Any],
        artifact_dir: Path,
    ) -> dict[str, Any]:
        text = redact_text(raw.assistant_text or "", limit=ASSISTANT_TEXT_LIMIT)
        fields = normalize_fields(
            assistant_text=text,
            artifact_dir=Path(artifact_dir),
            scenario=scenario,
            base_fields=raw.fields,
        )
        unknowns = list(raw.unknowns)
        unknowns.append("ambient_user_skills_possible")
        return {
            "fields": fields,
            "assistant_text": text,
            "assistant_text_sha256": sha256_text(text),
            "events": truncate_events(list(raw.events)),
            "unknowns": sorted(set(unknowns)),
            "model_requested": raw.model_requested,
            "model_resolved": raw.model_resolved,
            "tool_summary": list(raw.tool_summary),
            "skill_invocation": raw.skill_invocation or "requested",
            "usage": dict(raw.usage),
            "isolation": dict(raw.isolation) or self._isolation(),
        }

    def cleanup(self, *, prepared: dict[str, Any]) -> None:
        workspace = prepared.get("workspace")
        if workspace:
            self._cleanup_warnings.extend(safe_rmtree(Path(workspace)))

    @staticmethod
    def _isolation() -> dict[str, Any]:
        return {
            "scope": "partial",
            "ambient_user_skills_possible": True,
            "layout": "cursor",
            "sandbox": "enabled",
        }

    @staticmethod
    def _build_prompt(*, skill_id: str, scenario: dict[str, Any]) -> str:
        body = str(scenario.get("prompt") or "").strip()
        return (
            f"/{skill_id}\n"
            f"Use the /{skill_id} skill for this request. "
            f"Follow the skill instructions exactly.\n\n"
            f"{body}\n"
        )
