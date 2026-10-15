"""Unit tests for Cursor Skill Assay adapter (mocked subprocess)."""

from __future__ import annotations

import json
from pathlib import Path

from vibe_control.skill_assay.adapters.cursor import CursorHostAdapter, parse_agent_stream_json


def test_parse_agent_stream_json_assistant_and_success() -> None:
    stdout = "\n".join(
        [
            json.dumps({"type": "system", "subtype": "init", "model": "composer-2.5"}),
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "content": [{"type": "text", "text": "Mode: execute\n## Status\nok"}]
                    },
                }
            ),
            json.dumps({"type": "result", "subtype": "success", "result": "done"}),
        ]
    )
    parsed = parse_agent_stream_json(stdout)
    assert parsed["result_ok"] is True
    assert "Mode: execute" in parsed["assistant_text"]
    assert parsed["model_resolved"] == "composer-2.5"


def test_cursor_doctor_ready(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def runner(argv, **kwargs):
        del kwargs
        calls.append(list(argv))
        if argv[1] == "--version":
            return {"returncode": 0, "stdout": "1.0.0\n", "stderr": "", "timed_out": False}
        if argv[1] == "status":
            return {
                "returncode": 0,
                "stdout": json.dumps({"status": "authenticated", "isAuthenticated": True}),
                "stderr": "",
                "timed_out": False,
            }
        if argv[1] == "models":
            return {
                "returncode": 0,
                "stdout": "Available models\ncomposer-2.5 - Composer\n",
                "stderr": "",
                "timed_out": False,
            }
        raise AssertionError(argv)

    adapter = CursorHostAdapter(
        agent_bin="agent",
        runner=runner,
        which=lambda _: "/bin/agent",
    )
    result = adapter.doctor()
    assert result.ok is True
    assert result.support_state == "supported"
    assert "CURSOR_API_KEY" not in str(calls)


def test_cursor_run_builds_ask_argv_and_parses(tmp_path: Path) -> None:
    skill = tmp_path / "demo-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("# Demo\n", encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir()

    def runner(argv, **kwargs):
        assert "-p" in argv
        assert "--output-format" in argv
        assert "stream-json" in argv
        assert "--mode" in argv and "ask" in argv
        assert "--sandbox" in argv and "enabled" in argv
        assert any("/demo-skill" in str(a) for a in argv)
        assert "CURSOR_API_KEY" not in (kwargs.get("env") or {})
        stdout = "\n".join(
            [
                json.dumps({"type": "assistant", "text": "hello from cursor"}),
                json.dumps({"type": "result", "subtype": "success"}),
            ]
        )
        return {"returncode": 0, "stdout": stdout, "stderr": "", "timed_out": False}

    adapter = CursorHostAdapter(runner=runner, which=lambda _: "/bin/agent")
    prepared = adapter.prepare(
        assay_id="assay-1",
        run_index=0,
        skill_snapshot=skill,
        work_root=work,
        scenario={"execution_profile": "response_only", "prompt": "ping"},
    )
    assert (Path(prepared["skill_dest"]) / "SKILL.md").is_file()
    raw = adapter.run(
        prepared=prepared,
        scenario={
            "execution_profile": "response_only",
            "prompt": "ping",
            "timeout_seconds": 30,
        },
    )
    assert raw.error_code is None
    assert "hello from cursor" in raw.assistant_text
    normalized = adapter.normalize(
        raw=raw,
        scenario={"expected_fields": []},
        artifact_dir=Path(raw.artifact_dir),
    )
    assert normalized["assistant_text_sha256"]
    assert normalized["isolation"]["scope"] == "partial"


def test_cursor_doctor_auth_required() -> None:
    def runner(argv, **kwargs):
        del kwargs
        if argv[1] == "--version":
            return {"returncode": 0, "stdout": "1.0.0\n", "stderr": "", "timed_out": False}
        if argv[1] == "status":
            return {
                "returncode": 0,
                "stdout": json.dumps({"status": "logged_out", "isAuthenticated": False}),
                "stderr": "",
                "timed_out": False,
            }
        if argv[1] == "models":
            return {"returncode": 0, "stdout": "auto\n", "stderr": "", "timed_out": False}
        raise AssertionError(argv)

    adapter = CursorHostAdapter(runner=runner, which=lambda _: "/bin/agent")
    result = adapter.doctor()
    assert result.ok is False
    assert "SKILL_ASSAY_CURSOR_AUTH_REQUIRED" in result.blockers
