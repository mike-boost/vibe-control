"""Small-debt CLI: readme alias, diagnostics bundle, feedback --attach-doctor."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import yaml

from vibe_control.cli import main
from vibe_control.diagnostics import redact_value


def test_readme_aliases_describe(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    code_d = main(["describe", "--json"])
    describe = json.loads(capsys.readouterr().out)
    code_r = main(["readme", "--json"])
    readme = json.loads(capsys.readouterr().out)
    assert code_d == 0 and code_r == 0
    assert describe["ok"] is True and readme["ok"] is True
    # Same control-surface payload shape
    assert set(describe["data"].keys()) == set(readme["data"].keys())


def test_diagnostics_bundle_requires_redacted(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    code = main(["diagnostics", "bundle", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["error"]["code"] == "DIAGNOSTICS_REDACTED_REQUIRED"


def test_diagnostics_bundle_redacted_local(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    code = main(["diagnostics", "bundle", "--redacted", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["ok"] is True
    assert payload["data"]["upload"] is False
    zip_path = Path(payload["data"]["zip_path"])
    assert zip_path.is_file()
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        assert any(n.endswith("doctor-redacted.json") for n in names)
        assert any(n.endswith("manifest.json") for n in names)


def test_feedback_draft_attach_doctor(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    summary = tmp_path / "s.txt"
    summary.write_text("Doctor snippet attachment check.", encoding="utf-8")
    code = main(
        [
            "feedback",
            "draft",
            "--kind",
            "pain",
            "--title",
            "Attach doctor",
            "--summary-file",
            str(summary),
            "--attach-doctor",
            "--json",
        ]
    )
    draft = json.loads(capsys.readouterr().out)
    assert code == 0
    assert draft["data"]["doctor_attached"] is True
    entry = Path(draft["data"]["entry_dir"])
    snippet = entry / "doctor-redacted.json"
    assert snippet.is_file()
    doc = yaml.safe_load(Path(draft["data"]["path"]).read_text(encoding="utf-8"))
    assert any(a.get("path") == "doctor-redacted.json" for a in doc.get("attachments") or [])
    loaded = json.loads(snippet.read_text(encoding="utf-8"))
    # Sensitive keys should be redacted if present
    blob = json.dumps(loaded)
    assert "Bearer " not in blob


def test_redact_value_masks_sensitive_keys():
    raw = {
        "notebook_ref": "secret-notebook",
        "ok": True,
        "nested": {"source_id": "abc", "status": "ready"},
    }
    out = redact_value(raw)
    assert out["notebook_ref"] == "[REDACTED]"
    assert out["nested"]["source_id"] == "[REDACTED]"
    assert out["nested"]["status"] == "ready"
    assert out["ok"] is True
