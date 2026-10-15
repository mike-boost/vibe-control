"""Unit tests for Skill Assay normalize + redaction."""

from __future__ import annotations

from pathlib import Path

from vibe_control.skill_assay.normalize import extract_json_object, normalize_fields, sha256_text
from vibe_control.skill_assay.redaction import redact_text


def test_redact_bearer_and_home_path() -> None:
    text = "Authorization: Bearer secret-token-value\npath=/Users/example-user/project"
    out = redact_text(text, limit=2000)
    assert "secret-token-value" not in out
    assert "[REDACTED" in out
    assert "example-user" not in out
    assert "/Users/[REDACTED_USER]/project" in out


def test_normalize_fields_prefers_artifact_json(tmp_path: Path) -> None:
    art = tmp_path / "artifact"
    art.mkdir()
    (art / "out.json").write_text('{"ok": true, "nonce": "a"}\n', encoding="utf-8")
    fields = normalize_fields(
        assistant_text='```json\n{"ok": false, "extra": 1}\n```',
        artifact_dir=art,
        scenario={"expected_fields": ["ok", "nonce", "missing"]},
        base_fields={},
    )
    assert fields["ok"] is True
    assert fields["nonce"] == "a"
    assert fields["extra"] == 1
    assert fields["missing"] is None
    assert fields["assistant_nonempty"] is True
    assert fields["assistant_text_sha256"] == sha256_text(
        '```json\n{"ok": false, "extra": 1}\n```'
    )


def test_extract_json_object_plain() -> None:
    assert extract_json_object('hello {"x": 1} world') == {"x": 1}
