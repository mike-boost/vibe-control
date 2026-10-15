"""NotebookLM provider ask persona wiring (no real NotebookLM)."""

from __future__ import annotations

from vibe_control.knowledge.ask_template import SSOT_ASK_PERSONA
from vibe_control.knowledge.notebooklm_provider import NotebookLMProvider


def test_query_applies_persona_before_ask():
    calls: list[list[str]] = []

    def runner(argv, timeout=20.0):
        calls.append(list(argv))
        if "configure" in argv:
            return 0, '{"ok": true}', ""
        if "ask" in argv:
            return 0, '{"answer": "Facts:\\nnone", "sources": []}', ""
        return 1, "", "unexpected"

    provider = NotebookLMProvider(runner=runner)
    provider.which = lambda: "/fake/notebooklm"  # type: ignore[method-assign]

    result = provider.query(
        "wrapped question",
        notebook_ref="nb-ref",
        persona=SSOT_ASK_PERSONA,
        apply_ask_persona=True,
        response_length="shorter",
    )
    assert result["ok"] is True
    assert result["ask_persona"]["ok"] is True
    assert any("configure" in c for c in calls)
    assert any("ask" in c for c in calls)
    configure = next(c for c in calls if "configure" in c)
    assert "--persona" in configure
    assert SSOT_ASK_PERSONA in configure
    assert "--response-length" in configure
    assert "shorter" in configure
    ask = next(c for c in calls if "ask" in c)
    assert "--new" in ask
    assert "--yes" in ask


def test_query_continues_when_persona_configure_fails():
    def runner(argv, timeout=20.0):
        if "configure" in argv:
            return 1, "", "configure failed"
        if "ask" in argv:
            return 0, '{"answer": "ok", "sources": []}', ""
        return 1, "", "unexpected"

    provider = NotebookLMProvider(runner=runner)
    provider.which = lambda: "/fake/notebooklm"  # type: ignore[method-assign]

    result = provider.query(
        "q",
        notebook_ref="nb",
        persona=SSOT_ASK_PERSONA,
        apply_ask_persona=True,
    )
    assert result["ok"] is True
    assert result["answer"] == "ok"
    assert result["ask_persona"]["ok"] is False
    assert result["ask_persona"]["degraded"] is True
