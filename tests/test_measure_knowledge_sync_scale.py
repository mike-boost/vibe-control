"""Scale measure script gates + readonly contract."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "measure-knowledge-sync-scale.sh"


def test_measure_script_exists_and_is_executable():
    assert SCRIPT.is_file()
    text = SCRIPT.read_text(encoding="utf-8")
    assert "VIBE_KNOWLEDGE_SCALE_MEASURE_APPLY=1" in text
    assert "READONLY" in text or "readonly" in text
    assert "--apply" in text
    assert "runtime/vibe-scale-measure" in text


def test_measure_script_refuses_apply_without_env():
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'VIBE_KNOWLEDGE_SCALE_MEASURE_APPLY:-}" != "1"' in text or "VIBE_KNOWLEDGE_SCALE_MEASURE_APPLY=1" in text
    assert "REFUSED: --apply requires VIBE_KNOWLEDGE_SCALE_MEASURE_APPLY=1" in text
    assert "exit 3" in text
