"""Internal release readiness — fresh template is safe for external projects."""

from __future__ import annotations

from pathlib import Path

import yaml

from vibe_control.config import load_template, template_path, validate_config_dict


def test_fresh_template_is_default_disabled_and_valid():
    raw = load_template()
    assert validate_config_dict(raw) == []
    comps = raw["components"]
    assert comps["knowledge"]["enabled"] is False
    assert comps["task"]["enabled"] is False
    assert comps["sdd"]["enabled"] is False
    assert comps["tdd"]["enabled"] is False


def test_fresh_template_has_no_dogfood_or_secrets():
    text = template_path().read_text(encoding="utf-8")
    forbidden = (
        "migration-harness",
        "install-flink",
        "OPM-test",
        "NOTEBOOKLM_NOTEBOOK",
        "roadmap.",
        "api_key",
        "password:",
        "Bearer ",
    )
    for needle in forbidden:
        assert needle not in text, f"template must not contain {needle!r}"
    # Comments may mention "secrets/tokens" as warnings; real credential values must not appear.
    assert "sk-" not in text


def test_packaged_template_is_shipped_with_package_data():
    # setuptools package-data includes templates/*.yaml
    assert template_path().is_file()
    assert template_path().name == "control.yaml"
    assert "vibe_control" in template_path().as_posix()


def test_user_facing_docs_exist():
    root = Path(__file__).resolve().parents[1]
    for rel in (
        "README.md",
        "LICENSE",
        "CHANGELOG.md",
        "docs/configuration.md",
        "docs/release.md",
        "docs/feedback.md",
        ".github/ISSUE_TEMPLATE/bug_report.yml",
        ".github/ISSUE_TEMPLATE/feature_request.yml",
    ):
        assert (root / rel).is_file(), rel
    readme = (root / "README.md").read_text(encoding="utf-8")
    assert "vibe doctor" in readme
    assert "pipx" in readme
    assert "roadmap.*" not in readme or "should not need" in readme.lower()
    # Quickstart must not push internal control surfaces as primary path
    assert "## Quickstart" in readme
    assert "PyPI" in readme
    # Public release: README must declare the open-source license and must
    # not claim internal-only status anymore.
    assert "mit" in readme.lower()
    assert "internal use only" not in readme.lower()
