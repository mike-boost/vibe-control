"""Tests for config load/validate."""

from pathlib import Path

import pytest
import yaml

from vibe_control.cli import main
from vibe_control.config import (
    ConfigError,
    load_config,
    load_template,
    validate_config_dict,
)


def test_template_parses_and_validates():
    raw = load_template()
    assert raw["project"]["id"] == "example-project"
    assert raw["components"]["knowledge"]["enabled"] is False
    assert raw["components"]["task"]["enabled"] is False
    assert validate_config_dict(raw) == []
    # Fresh template must not carry dogfood migration defaults.
    assert raw["project"]["id"] != "migration-harness"
    text = __import__("pathlib").Path(
        __import__("vibe_control.config", fromlist=["template_path"]).template_path()
    ).read_text(encoding="utf-8")
    assert "OPM-test" not in text
    assert "NOTEBOOKLM" not in text


def test_missing_config_returns_config_not_found(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    code = main(["config", "validate", "--json"])
    assert code == 1
    out = capsys.readouterr().out
    payload = __import__("json").loads(out)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "CONFIG_NOT_FOUND"


def test_load_config_success(tmp_path: Path):
    raw = load_template()
    config_dir = tmp_path / ".vibe"
    config_dir.mkdir()
    path = config_dir / "control.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    config = load_config(tmp_path)
    assert config.project_id == "example-project"


def test_load_config_missing_raises(tmp_path: Path):
    with pytest.raises(ConfigError) as exc:
        load_config(tmp_path)
    assert exc.value.code == "CONFIG_NOT_FOUND"
