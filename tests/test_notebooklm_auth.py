"""NotebookLM auth-status / login-guide tests (no real CLI required)."""

from __future__ import annotations

import json

from vibe_control.cli import main


def test_auth_status_missing_notebooklm(monkeypatch, capsys):
    monkeypatch.setattr(
        "vibe_control.knowledge.notebooklm_provider.shutil.which",
        lambda name: None,
    )
    code = main(["knowledge", "auth-status", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["error"]["code"] == "NOTEBOOKLM_NOT_INSTALLED"


def test_auth_status_success(monkeypatch, capsys):
    monkeypatch.setattr(
        "vibe_control.knowledge.notebooklm_provider.shutil.which",
        lambda name: "/tmp/fake-nlm" if name == "notebooklm" else None,
    )

    def fake_run(argv, timeout=20.0):
        if "--version" in argv:
            return 0, "NotebookLM CLI, version fake\n", ""
        if "auth" in argv and "check" in argv:
            return 0, json.dumps({"ok": True, "auth": "ok"}), ""
        return 0, "", ""

    monkeypatch.setattr(
        "vibe_control.knowledge.notebooklm_provider._default_run",
        fake_run,
    )
    code = main(["knowledge", "auth-status", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["data"]["auth_state"] == "available"
    assert payload["data"]["safe_to_sync"] is False


def test_auth_status_failure(monkeypatch, capsys):
    monkeypatch.setattr(
        "vibe_control.knowledge.notebooklm_provider.shutil.which",
        lambda name: "/tmp/fake-nlm" if name == "notebooklm" else None,
    )

    def fake_run(argv, timeout=20.0):
        if "--version" in argv:
            return 0, "fake\n", ""
        if "auth" in argv:
            return 1, json.dumps({"ok": False, "error": "expired"}), ""
        return 1, "", "fail"

    monkeypatch.setattr(
        "vibe_control.knowledge.notebooklm_provider._default_run",
        fake_run,
    )
    code = main(["knowledge", "auth-status", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["error"]["code"] == "NOTEBOOKLM_AUTH_FAILED"


def test_auth_status_unsupported(monkeypatch, capsys):
    monkeypatch.setattr(
        "vibe_control.knowledge.notebooklm_provider.shutil.which",
        lambda name: "/tmp/fake-nlm" if name == "notebooklm" else None,
    )

    def fake_run(argv, timeout=20.0):
        if "--version" in argv:
            return 0, "fake\n", ""
        return 2, "", "Error: No such command 'auth'."

    monkeypatch.setattr(
        "vibe_control.knowledge.notebooklm_provider._default_run",
        fake_run,
    )
    code = main(["knowledge", "auth-status", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["error"]["code"] == "NOTEBOOKLM_COMMAND_UNSUPPORTED"


def _fake_which(monkeypatch):
    monkeypatch.setattr(
        "vibe_control.knowledge.notebooklm_provider.shutil.which",
        lambda name: "/tmp/fake-nlm" if name == "notebooklm" else None,
    )


def _fake_run_with(monkeypatch, auth_stdout, auth_code=0):
    def fake_run(argv, timeout=20.0):
        if "--version" in argv:
            return 0, "NotebookLM CLI, version fake\n", ""
        if "auth" in argv and "check" in argv:
            return auth_code, auth_stdout, ""
        return 0, "", ""

    monkeypatch.setattr(
        "vibe_control.knowledge.notebooklm_provider._default_run",
        fake_run,
    )


def test_auth_status_exit0_but_payload_error_is_auth_failed(monkeypatch, capsys):
    """Exit 0 with status=error must not be reported as available
    (false-positive trap of older notebooklm CLIs)."""
    _fake_which(monkeypatch)
    _fake_run_with(
        monkeypatch,
        json.dumps({"status": "error", "checks": {"token_fetch": False}}),
        auth_code=0,
    )
    code = main(["knowledge", "auth-status", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["error"]["code"] == "NOTEBOOKLM_AUTH_FAILED"


def test_auth_status_exit0_but_token_fetch_false_is_auth_failed(monkeypatch, capsys):
    _fake_which(monkeypatch)
    _fake_run_with(
        monkeypatch,
        json.dumps({"status": "ok", "checks": {"token_fetch": False}}),
        auth_code=0,
    )
    code = main(["knowledge", "auth-status", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["error"]["code"] == "NOTEBOOKLM_AUTH_FAILED"


def test_auth_status_new_format_ok_with_token_fetch_true(monkeypatch, capsys):
    _fake_which(monkeypatch)
    _fake_run_with(
        monkeypatch,
        json.dumps({"status": "ok", "checks": {"token_fetch": True}}),
        auth_code=0,
    )
    code = main(["knowledge", "auth-status", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["data"]["auth_state"] == "available"
