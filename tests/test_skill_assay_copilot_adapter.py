"""Unit tests for GitHub Copilot Skill Assay adapter (mocked SDK)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from vibe_control.skill_assay.adapters.github_copilot import GitHubCopilotHostAdapter
from vibe_control.skill_assay.errors import SkillAssayError


class _FakeSession:
    def __init__(self, *, text: str = "Mode: execute\n## Status\nok", timeout: bool = False):
        self._text = text
        self._timeout = timeout
        self._handlers: list[Any] = []
        self.aborted = False

    def on(self, handler):  # noqa: ANN001
        self._handlers.append(handler)

        def _unsub() -> None:
            return None

        return _unsub

    async def send_and_wait(self, prompt: str):
        del prompt
        if self._timeout:
            import asyncio

            await asyncio.sleep(10)
        event = SimpleNamespace(
            type="assistant.message",
            data=SimpleNamespace(content=self._text, model="gpt-4.1", usage={"total": 1}),
        )
        for handler in self._handlers:
            handler(event)
        return event

    async def abort(self) -> None:
        self.aborted = True


class _FakeClient:
    def __init__(self, *, session: _FakeSession | None = None, fail_start: bool = False):
        self._session = session or _FakeSession()
        self._fail_start = fail_start
        self.started = False
        self.stopped = False
        self.create_kwargs: dict[str, Any] = {}

    async def start(self) -> None:
        if self._fail_start:
            raise RuntimeError("auth required: please login")
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def create_session(self, **kwargs):
        self.create_kwargs = kwargs
        return self._session

    async def list_models(self):
        return ["gpt-4.1"]


def test_copilot_doctor_sdk_missing() -> None:
    def missing():
        raise SkillAssayError("SKILL_ASSAY_COPILOT_SDK_MISSING", "missing")

    adapter = GitHubCopilotHostAdapter(
        which=lambda _: "/bin/copilot",
        import_sdk=missing,
    )
    result = adapter.doctor()
    assert result.ok is False
    assert "SKILL_ASSAY_COPILOT_SDK_MISSING" in result.blockers


def test_copilot_doctor_and_run_with_fake_sdk(tmp_path: Path) -> None:
    client = _FakeClient()

    class _Sdk:
        class RuntimeConnection:
            @staticmethod
            def for_stdio(*, path: str):
                return SimpleNamespace(path=path)

        class CopilotClient:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            async def start(self):
                await client.start()

            async def stop(self):
                await client.stop()

            async def create_session(self, **kwargs):
                return await client.create_session(**kwargs)

            async def list_models(self):
                return await client.list_models()

        class session:
            class PermissionHandler:
                approve_all = object()

    def factory(*, sdk, copilot_bin, working_directory):
        del sdk, copilot_bin, working_directory
        return client

    adapter = GitHubCopilotHostAdapter(
        which=lambda _: "/opt/homebrew/bin/copilot",
        import_sdk=lambda: _Sdk,
        sdk_factory=factory,
    )
    doctor = adapter.doctor()
    assert doctor.ok is True
    assert doctor.support_state == "supported"

    skill = tmp_path / "demo-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("# Demo\n", encoding="utf-8")
    prepared = adapter.prepare(
        assay_id="a1",
        run_index=0,
        skill_snapshot=skill,
        work_root=tmp_path / "work",
        scenario={},
    )
    assert Path(prepared["skill_dest"]).name == "demo-skill"
    raw = adapter.run(
        prepared=prepared,
        scenario={
            "prompt": "ping",
            "execution_profile": "response_only",
            "timeout_seconds": 5,
        },
    )
    assert raw.error_code is None
    assert "Mode: execute" in raw.assistant_text
    tools = client.create_kwargs.get("available_tools") or []
    assert "builtin:skill" in tools
    assert client.create_kwargs.get("skill_directories") == [
        prepared["skills_parent"],
        prepared["skill_dest"],
    ]
    assert client.stopped is True


def test_copilot_timeout_aborts(tmp_path: Path) -> None:
    session = _FakeSession(timeout=True)
    client = _FakeClient(session=session)

    def factory(*, sdk, copilot_bin, working_directory):
        del sdk, copilot_bin, working_directory
        return client

    adapter = GitHubCopilotHostAdapter(
        which=lambda _: "/bin/copilot",
        import_sdk=lambda: SimpleNamespace(CopilotClient=object),
        sdk_factory=factory,
    )
    skill = tmp_path / "demo-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("# Demo\n", encoding="utf-8")
    prepared = adapter.prepare(
        assay_id="a1",
        run_index=0,
        skill_snapshot=skill,
        work_root=tmp_path / "work",
        scenario={},
    )
    raw = adapter.run(
        prepared=prepared,
        scenario={"prompt": "ping", "timeout_seconds": 0.01, "execution_profile": "response_only"},
    )
    assert raw.error_code == "SKILL_ASSAY_COPILOT_TIMEOUT"
    assert session.aborted is True
