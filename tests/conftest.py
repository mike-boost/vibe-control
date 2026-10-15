"""Pytest collection hooks and marker discipline."""

from __future__ import annotations

from pathlib import Path

import pytest


# Modules that wrap acceptance scripts or otherwise share process-heavy subprocesses.
_SERIAL_ACCEPTANCE_MODULES = {
    "test_phase2_acceptance.py",
    "test_phase3_acceptance.py",
    "test_phase8_acceptance.py",
}


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        name = Path(str(item.fspath)).name
        if name in _SERIAL_ACCEPTANCE_MODULES:
            item.add_marker(pytest.mark.acceptance)
            item.add_marker(pytest.mark.serial)
            item.add_marker(pytest.mark.slow)
        # Default unmarked tests are treated as unit/parallel-safe.
        if not any(item.iter_markers()):
            item.add_marker(pytest.mark.unit)
