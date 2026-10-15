"""GitHub Copilot SDK host adapter for Skill Assay."""

from __future__ import annotations

import asyncio
import shutil
import uuid
from pathlib import Path
from typing import Any, Callable

from vibe_control.skill_assay.adapters import HostDoctorResult, HostRunResult
from vibe_control.skill_assay.adapters.base import inject_skill_tree, mount_target_repo, scrub_env, safe_rmtree
from vibe_control.skill_assay.constants import ASSISTANT_TEXT_LIMIT
from vibe_control.skill_assay.errors import SkillAssayError
from vibe_control.skill_assay.normalize import normalize_fields, sha256_text
from vibe_control.skill_assay.redaction import redact_text, truncate_events


class GitHubCopilotHostAdapter:
    host_id = "github-copilot"

    def __init__(
        self,
        *,
        copilot_bin: str = "copilot",
        which: Callable[[str], str | None] | None = None,
        sdk_factory: Callable[..., Any] | None = None,
        import_sdk: Callable[[], Any] | None = None,
    ) -> None:
        self._copilot_bin = copilot_bin
        self._which = which or shutil.which
        self._sdk_factory = sdk_factory
        self._import_sdk = import_sdk or self._default_import_sdk
        self._cleanup_warnings: list[str] = []

    @staticmethod
    def _default_import_sdk() -> Any:
        try:
            import copilot as sdk  # type: ignore[import-not-found]
        except ImportError as exc:
            raise SkillAssayError(
                "SKILL_ASSAY_COPILOT_SDK_MISSING",
                "github-copilot-sdk is not installed; "
                "pip install 'vibe-control[skill-assay-hosts]'",
            ) from exc
        return sdk

    def doctor(self) -> HostDoctorResult:
        blockers: list[str] = []
        details: dict[str, Any] = {}
        resolved = self._which(self._copilot_bin)
        if not resolved:
            return HostDoctorResult(
                host_id=self.host_id,
                ok=False,
                support_state="unavailable",
                blockers=["SKILL_ASSAY_COPILOT_CLI_MISSING"],
                details={"copilot_bin": self._copilot_bin},
            )
        details["copilot_bin"] = resolved

        try:
            sdk = self._import_sdk()
            details["sdk"] = getattr(sdk, "__name__", "copilot")
        except SkillAssayError as exc:
            return HostDoctorResult(
                host_id=self.host_id,
                ok=False,
                support_state="unavailable",
                blockers=[exc.code],
                details={"error": exc.message},
            )

        try:
            probe = self._run_async(
                self._doctor_probe(sdk=sdk, copilot_bin=resolved)
            )
            details.update(probe.get("details") or {})
            blockers.extend(probe.get("blockers") or [])
        except SkillAssayError as exc:
            blockers.append(exc.code)
            details["probe_error"] = exc.message
        except Exception as exc:  # noqa: BLE001 - host boundary
            blockers.append("SKILL_ASSAY_COPILOT_SESSION_ERROR")
            details["probe_error"] = str(exc)

        ok = not blockers
        return HostDoctorResult(
            host_id=self.host_id,
            ok=ok,
            support_state="supported" if ok else "unavailable",
            blockers=blockers,
            details=details,
        )

    async def _doctor_probe(self, *, sdk: Any, copilot_bin: str) -> dict[str, Any]:
        blockers: list[str] = []
        details: dict[str, Any] = {}
        client = self._build_client(sdk=sdk, copilot_bin=copilot_bin, working_directory=None)
        try:
            await client.start()
            models = []
            list_models = getattr(client, "list_models", None) or getattr(client, "models", None)
            if callable(list_models):
                maybe = list_models()
                if asyncio.iscoroutine(maybe):
                    maybe = await maybe
                if isinstance(maybe, list):
                    models = maybe
            details["model_count"] = len(models) if isinstance(models, list) else 0
            if details["model_count"] == 0:
                # Some SDK versions expose models only via session; treat as soft signal.
                details["model_probe"] = "deferred_to_session"
            details["auth"] = "use_logged_in_user"
        except Exception as exc:  # noqa: BLE001
            message = str(exc).lower()
            if "auth" in message or "login" in message or "token" in message:
                blockers.append("SKILL_ASSAY_COPILOT_AUTH_REQUIRED")
            elif "version" in message or "incompatible" in message:
                blockers.append("SKILL_ASSAY_COPILOT_VERSION_INCOMPATIBLE")
            else:
                blockers.append("SKILL_ASSAY_COPILOT_SESSION_ERROR")
            details["error"] = str(exc)
        finally:
            stop = getattr(client, "stop", None)
            if callable(stop):
                maybe = stop()
                if asyncio.iscoroutine(maybe):
                    await maybe
        return {"blockers": blockers, "details": details}

    def prepare(
        self,
        *,
        assay_id: str,
        run_index: int,
        skill_snapshot: Path,
        work_root: Path,
        scenario: dict[str, Any],
    ) -> dict[str, Any]:
        session_id = f"copilot-session-{uuid.uuid4().hex[:12]}"
        workspace = Path(work_root) / f"run-{run_index}"
        workspace.mkdir(parents=True, exist_ok=True)
        skill_dest = inject_skill_tree(
            skill_snapshot=skill_snapshot,
            workspace=workspace,
            layout="copilot_parent",
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
            "skills_parent": skill_dest.parent.as_posix(),
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
        try:
            return self._run_async(self._run_async_impl(prepared=prepared, scenario=scenario))
        except SkillAssayError as exc:
            return HostRunResult(
                session_id=str(prepared["session_id"]),
                workspace_path=str(prepared["workspace"]),
                exit_status=1,
                fields={},
                events=[],
                artifact_dir=str(prepared["artifact_dir"]),
                unknowns=[],
                error_code=exc.code,
                error_message=exc.message,
                assistant_text="",
                skill_invocation="requested",
                isolation=self._isolation(),
            )

    async def _run_async_impl(
        self,
        *,
        prepared: dict[str, Any],
        scenario: dict[str, Any],
    ) -> HostRunResult:
        workspace = Path(prepared["workspace"])
        artifact = Path(prepared["artifact_dir"])
        skill_id = str(prepared.get("skill_id") or "skill")
        timeout = int(scenario.get("timeout_seconds") or 300)
        profile = str(scenario.get("execution_profile") or "response_only")
        model = scenario.get("model")
        prompt = (
            f"Use the /{skill_id} skill for this request. "
            f"Follow the skill instructions exactly.\n\n"
            f"{str(scenario.get('prompt') or '').strip()}\n"
        )

        sdk = self._import_sdk()
        copilot_bin = self._which(self._copilot_bin) or self._copilot_bin
        client = self._build_client(
            sdk=sdk,
            copilot_bin=copilot_bin,
            working_directory=str(workspace),
        )
        events: list[dict[str, Any]] = []
        tool_summary: list[dict[str, Any]] = []
        skill_invocation = "requested"
        assistant_parts: list[str] = []
        model_resolved: str | None = None
        usage: dict[str, Any] = {}
        unknowns: list[str] = []
        error_code: str | None = None
        error_message: str | None = None
        session = None

        try:
            await client.start()
            create_kwargs: dict[str, Any] = {
                "working_directory": str(workspace),
                "skill_directories": [
                    str(prepared["skills_parent"]),
                    str(prepared["skill_dest"]),
                ],
                "enable_skills": True,
                "enable_config_discovery": False,
                "enable_on_demand_instruction_discovery": False,
                "enable_session_store": False,
                "enable_host_git_operations": False,
                "skip_custom_instructions": True,
                "on_permission_request": self._permission_handler(sdk),
            }
            memory_cls = getattr(sdk, "MemoryConfiguration", None)
            if memory_cls is not None:
                try:
                    create_kwargs["memory"] = memory_cls(enabled=False)
                except TypeError:
                    create_kwargs["memory"] = {"enabled": False}
            if model:
                create_kwargs["model"] = str(model)
            if profile == "response_only":
                # Empty tool set blocks skill discovery/read. Allow only skill +
                # readonly filesystem tools; keep shell/edit/network out.
                create_kwargs["available_tools"] = [
                    "builtin:skill",
                    "builtin:read_file",
                    "builtin:list_dir",
                    "builtin:grep",
                    "builtin:glob",
                ]
            else:
                create_kwargs["available_tools"] = [
                    "builtin:skill",
                    "builtin:read_file",
                    "builtin:list_dir",
                    "builtin:grep",
                    "builtin:glob",
                    "builtin:bash",
                    "builtin:shell",
                ]
            if prepared.get("target_repo_mount"):
                prompt = (
                    f"{prompt}\n\n"
                    f"TARGET_REPO_MOUNT={prepared['target_repo_mount']}\n"
                    "Analyze that mounted repository path.\n"
                )
            session = await client.create_session(**create_kwargs)

            def _on_event(event: Any) -> None:
                nonlocal skill_invocation, model_resolved
                payload = self._event_to_dict(event)
                events.append(payload)
                etype = str(payload.get("type") or "").lower()
                data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
                if "assistant" in etype:
                    content = data.get("content") or payload.get("content") or ""
                    if content:
                        assistant_parts.append(str(content))
                if "skill" in etype:
                    skill_invocation = "observed"
                if "tool" in etype:
                    tool_summary.append(
                        {
                            "name": str(data.get("name") or payload.get("name") or "tool"),
                            "ok": "error" not in etype,
                            "summary": redact_text(str(data.get("summary") or "")[:200]),
                        }
                    )
                if data.get("model"):
                    model_resolved = str(data.get("model"))
                if isinstance(data.get("usage"), dict):
                    usage.update(data["usage"])

            unsubscribe = None
            on = getattr(session, "on", None)
            if callable(on):
                unsubscribe = on(_on_event)

            send_and_wait = getattr(session, "send_and_wait", None)
            try:
                if not callable(send_and_wait):
                    raise SkillAssayError(
                        "SKILL_ASSAY_COPILOT_SESSION_ERROR",
                        "Copilot session missing send_and_wait",
                    )
                response = await asyncio.wait_for(send_and_wait(prompt), timeout=timeout)
                text = self._extract_response_text(response)
                if text:
                    assistant_parts.append(text)
                if not assistant_parts:
                    error_code = "SKILL_ASSAY_COPILOT_NO_ASSISTANT_MESSAGE"
                    error_message = "Copilot session returned no assistant message"
            except asyncio.TimeoutError:
                error_code = "SKILL_ASSAY_COPILOT_TIMEOUT"
                error_message = "Copilot session timed out"
                abort = getattr(session, "abort", None)
                if callable(abort):
                    maybe = abort()
                    if asyncio.iscoroutine(maybe):
                        await maybe
            except SkillAssayError:
                raise
            except Exception as exc:  # noqa: BLE001
                error_code = "SKILL_ASSAY_COPILOT_SESSION_ERROR"
                error_message = str(exc)
            finally:
                if callable(unsubscribe):
                    unsubscribe()
        finally:
            stop = getattr(client, "stop", None)
            if callable(stop):
                maybe = stop()
                if asyncio.iscoroutine(maybe):
                    await maybe

        assistant_text = "\n".join(p for p in assistant_parts if p).strip()
        if not assistant_text and not error_code:
            error_code = "SKILL_ASSAY_COPILOT_NO_ASSISTANT_MESSAGE"
            error_message = "Copilot session returned no assistant message"
            unknowns.append("no_assistant_message")

        (artifact / "events.json").write_text(
            __import__("json").dumps(events[:80], indent=2) + "\n",
            encoding="utf-8",
        )

        return HostRunResult(
            session_id=str(prepared["session_id"]),
            workspace_path=str(workspace),
            exit_status=0 if error_code is None else 1,
            fields={},
            events=events,
            artifact_dir=str(artifact),
            unknowns=unknowns,
            error_code=error_code,
            error_message=error_message,
            assistant_text=assistant_text,
            model_requested=str(model) if model else None,
            model_resolved=model_resolved,
            tool_summary=tool_summary,
            skill_invocation=skill_invocation,
            usage=usage,
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
        return {
            "fields": fields,
            "assistant_text": text,
            "assistant_text_sha256": sha256_text(text),
            "events": truncate_events(list(raw.events)),
            "unknowns": list(raw.unknowns),
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

    def _build_client(
        self,
        *,
        sdk: Any,
        copilot_bin: str,
        working_directory: str | None,
    ) -> Any:
        if self._sdk_factory is not None:
            return self._sdk_factory(
                sdk=sdk,
                copilot_bin=copilot_bin,
                working_directory=working_directory,
            )
        import tempfile

        connection_cls = getattr(sdk, "RuntimeConnection", None)
        connection = None
        if connection_cls is not None and hasattr(connection_cls, "for_stdio"):
            connection = connection_cls.for_stdio(path=copilot_bin)
        base_directory = working_directory
        if not base_directory:
            base_directory = tempfile.mkdtemp(prefix="skill-assay-copilot-doctor-")
        kwargs: dict[str, Any] = {
            "mode": "empty",
            "use_logged_in_user": True,
            "env": scrub_env(extra_allow=("HOME",)),
            "base_directory": base_directory,
            "working_directory": working_directory or base_directory,
        }
        if connection is not None:
            kwargs["connection"] = connection
        return sdk.CopilotClient(**kwargs)

    @staticmethod
    def _permission_handler(sdk: Any) -> Any:
        session_mod = getattr(sdk, "session", None)
        handler = getattr(session_mod, "PermissionHandler", None) if session_mod else None
        if handler is not None and hasattr(handler, "approve_all"):
            return handler.approve_all
        approve = getattr(sdk, "PermissionDecisionApproveOnce", None)
        if approve is not None:
            return lambda *_args, **_kwargs: approve()
        return lambda *_args, **_kwargs: True

    @staticmethod
    def _event_to_dict(event: Any) -> dict[str, Any]:
        if isinstance(event, dict):
            return event
        etype = getattr(event, "type", None)
        data = getattr(event, "data", None)
        payload: dict[str, Any] = {
            "type": str(etype) if etype is not None else type(event).__name__,
        }
        if data is None:
            return payload
        if hasattr(data, "__dict__"):
            payload["data"] = {
                k: getattr(data, k)
                for k in ("content", "name", "model", "usage", "summary")
                if hasattr(data, k)
            }
        elif isinstance(data, dict):
            payload["data"] = data
        else:
            payload["data"] = {"content": str(data)}
        return payload

    @staticmethod
    def _extract_response_text(response: Any) -> str:
        if response is None:
            return ""
        if isinstance(response, str):
            return response
        data = getattr(response, "data", None)
        if data is not None and hasattr(data, "content"):
            return str(getattr(data, "content") or "")
        if isinstance(response, dict):
            data = response.get("data")
            if isinstance(data, dict) and data.get("content"):
                return str(data["content"])
            if response.get("content"):
                return str(response["content"])
        content = getattr(response, "content", None)
        return str(content or "")

    @staticmethod
    def _isolation() -> dict[str, Any]:
        return {
            "scope": "session",
            "ambient_user_skills_possible": False,
            "layout": "copilot_parent",
            "mode": "empty",
        }

    @staticmethod
    def _run_async(coro: Any) -> Any:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        # Nested loop (rare in CLI): run in a fresh loop via thread-less fallback.
        new_loop = asyncio.new_event_loop()
        try:
            return new_loop.run_until_complete(coro)
        finally:
            new_loop.close()
