"""Stability comparison across Skill Assay runs."""

from __future__ import annotations

from typing import Any


def compute_stability(
    runs: list[dict[str, Any]],
    *,
    expected_fields: list[str] | None = None,
) -> dict[str, list[str]]:
    """Compare per-run ``fields`` maps.

    - stable: present in all runs with identical normalized values
    - unstable: present in some runs and/or values disagree
    - absent: listed in expected_fields but missing from every run
    """
    if not runs:
        return {"stable_fields": [], "unstable_fields": [], "absent_fields": []}

    field_sets = [set((r.get("fields") or {}).keys()) for r in runs]
    all_keys = set().union(*field_sets) if field_sets else set()
    if expected_fields:
        all_keys.update(expected_fields)

    stable: list[str] = []
    unstable: list[str] = []
    absent: list[str] = []

    for key in sorted(all_keys):
        values: list[Any] = []
        present_count = 0
        for run in runs:
            fields = run.get("fields") or {}
            if key in fields:
                present_count += 1
                values.append(_normalize(fields[key]))
            else:
                values.append(_MISSING)

        if present_count == 0:
            absent.append(key)
            continue
        if present_count < len(runs):
            unstable.append(key)
            continue
        # All present: check value agreement
        first = values[0]
        if all(v == first for v in values):
            stable.append(key)
        else:
            unstable.append(key)

    return {
        "stable_fields": stable,
        "unstable_fields": unstable,
        "absent_fields": absent,
    }


class _Missing:
    def __repr__(self) -> str:
        return "<MISSING>"


_MISSING = _Missing()


def _normalize(value: Any) -> Any:
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _normalize(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)
