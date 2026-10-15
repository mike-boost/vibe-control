"""Experience feedback CLI — local artifacts only (not tasks)."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import yaml

from vibe_control.cli import main
from vibe_control.feedback import (
    FEEDBACK_KINDS,
    draft_feedback,
    find_secret_hits,
    validate_feedback_document,
)


def test_feedback_init_preview(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    code = main(["feedback", "init-preview", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["ok"] is True
    assert payload["data"]["not_a_task"] is True
    assert payload["data"]["share_policy"] == "voluntary_only_never_auto_upload"
    assert "runtime/vibe-feedback" in payload["data"]["feedback_root_relative"]
    assert set(payload["data"]["kinds"]) == FEEDBACK_KINDS


def test_feedback_draft_validate_pack_roundtrip(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    summary = tmp_path / "s.txt"
    summary.write_text("Doctor next_actions were unclear after skills mismatch.", encoding="utf-8")

    code = main(
        [
            "feedback",
            "draft",
            "--kind",
            "friction",
            "--title",
            "Skills mismatch UX",
            "--summary-file",
            str(summary),
            "--json",
        ]
    )
    draft = json.loads(capsys.readouterr().out)
    assert code == 0
    assert draft["data"]["upload"] is False
    fid = draft["data"]["id"]
    path = Path(draft["data"]["path"])
    assert path.is_file()
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert doc["schema"] == "vibe.feedback.v1"
    assert doc["redaction"]["confirmed"] is False
    assert doc["kind"] == "friction"

    code = main(["feedback", "validate", "--path", fid, "--json"])
    bad = json.loads(capsys.readouterr().out)
    assert code == 1
    assert bad["error"]["code"] == "FEEDBACK_VALIDATE_FAILED"

    doc["redaction"]["confirmed"] = True
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")

    code = main(["feedback", "validate", "--path", fid, "--json"])
    ok = json.loads(capsys.readouterr().out)
    assert code == 0
    assert ok["data"]["ok"] is True

    code = main(["feedback", "pack", "--path", fid, "--json"])
    packed = json.loads(capsys.readouterr().out)
    assert code == 0
    assert packed["data"]["upload"] is False
    zip_path = Path(packed["data"]["zip_path"])
    assert zip_path.is_file()
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        assert any(n.endswith("feedback.yaml") for n in names)


def test_feedback_rejects_secret_like_summary(tmp_path):
    doc = draft_feedback(
        repo_root=tmp_path,
        kind="bug_signal",
        title="leak",
        summary="api_key=super-secret-value-here",
    )["document"]
    doc["redaction"]["confirmed"] = True
    hits = find_secret_hits(doc)
    assert hits
    result = validate_feedback_document(doc)
    assert result["ok"] is False
    assert any("secrets" in e for e in result["errors"])


def test_feedback_pack_requires_validate(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    result = draft_feedback(
        repo_root=tmp_path,
        kind="pain",
        title="x",
        summary="y",
        feedback_id="fb-test-1",
    )
    code = main(["feedback", "pack", "--path", result["id"], "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["error"]["code"] == "FEEDBACK_VALIDATE_FAILED"
