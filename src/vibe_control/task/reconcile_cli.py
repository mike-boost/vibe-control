"""Phase 11A readonly task reconcile orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from vibe_control.config import ConfigError, load_config
from vibe_control.json_envelope import attach_operation_result, next_action
from vibe_control.task.beads_readonly import BeadsReadonlyProvider
from vibe_control.task.projection import project_slice1_expected_tasks
from vibe_control.task.provider import FakeTaskProvider
from vibe_control.task.reconcile import reconcile_readonly


def resolve_task_provider(
    *,
    provider_name: str | None,
    config_provider: str | None,
) -> tuple[str, Any, list[str]]:
    """Resolve FakeTaskProvider or BeadsReadonlyProvider.

    Returns (provider_kind, provider_instance, warnings).
    """
    warnings: list[str] = []
    requested = (provider_name or "").strip().lower() or None
    if requested is None:
        cfg = (config_provider or "").strip().lower()
        requested = cfg if cfg in {"fake", "beads"} else "beads"

    if requested == "fake":
        return "fake", FakeTaskProvider([]), warnings
    if requested == "beads":
        provider = BeadsReadonlyProvider()
        return "beads", provider, warnings
    warnings.append(f"unknown provider {requested!r}; falling back to fake")
    return "fake", FakeTaskProvider([]), warnings


def _empty_counts() -> dict[str, int]:
    return {
        "matched": 0,
        "missing": 0,
        "duplicate": 0,
        "stale": 0,
        "conflict": 0,
        "unmanaged": 0,
    }


def run_task_reconcile_dry_run(
    *,
    repo_root: Path,
    provider: Any | None = None,
    provider_name: str | None = None,
) -> dict[str, Any]:
    """Build readonly reconcile report. Never mutates Beads or NotebookLM."""
    root = repo_root
    warnings: list[str] = []
    try:
        config = load_config(root)
        project_id = config.project_id
        config_provider = str((config.tasks or {}).get("provider") or "") or None
    except ConfigError as exc:
        return attach_operation_result(
            {
                "ok": False,
                "code": exc.code or "CONFIG_INVALID",
                "message": exc.message,
                "project_id": None,
                "mode": "unavailable",
                "provider": None,
                "provider_available": False,
                "mutation": False,
                "data": {},
                "warnings": [],
                "next_actions": [
                    next_action(
                        code="CONFIG_REQUIRED",
                        command="vibe config validate --json",
                        mutation=False,
                        reason="Load project config before task reconcile",
                    )
                ],
            },
            mutation_intent=False,
            effects=[],
        )

    expected = project_slice1_expected_tasks(project_id=project_id, repo_root=root)

    if provider is not None:
        use_provider = provider
        provider_kind = str(getattr(provider, "name", "unknown"))
    else:
        provider_kind, use_provider, resolve_warnings = resolve_task_provider(
            provider_name=provider_name,
            config_provider=config_provider,
        )
        warnings.extend(resolve_warnings)

    provider_tasks = list(use_provider.list_tasks())
    provider_available = True
    if isinstance(use_provider, BeadsReadonlyProvider):
        provider_available = bool(use_provider.available)
        warnings.extend(list(use_provider.warnings or []))
    elif provider_kind == "fake":
        provider_available = True
        if provider is None:
            warnings.append(
                "Using FakeTaskProvider (empty in-memory list); pass --provider beads for live readonly bd list"
            )

    # Unavailable: do not treat failed provider read as a real empty Beads inventory.
    if not provider_available:
        if not any("unavailable" in w.lower() or "not found" in w.lower() for w in warnings):
            warnings.append(
                "Task provider unavailable; reconcile diff skipped (not a real empty Beads state)"
            )
        data = {
            "project_id": project_id,
            "expected_count": len(expected),
            "expected_tasks": [item.to_dict() for item in expected],
            "provider_task_count": None,
            "provider_read_ok": False,
            "reconcile_skipped": True,
            "matched": [],
            "missing": [],
            "duplicate": [],
            "stale": [],
            "conflict": [],
            "unmanaged": [],
            "counts": _empty_counts(),
            "mutation": False,
            "provider": provider_kind,
            "provider_available": False,
            "provider_kind": provider_kind,
            "phase": "11A",
            "slice": 2,
            "mode": "unavailable",
            "warnings": list(warnings),
        }
        return attach_operation_result(
            {
                "ok": True,
                "project_id": project_id,
                "mode": "unavailable",
                "provider": provider_kind,
                "provider_available": False,
                "mutation": False,
                "data": data,
                "warnings": warnings,
                "next_actions": [
                    next_action(
                        code="BEADS_PROVIDER_UNAVAILABLE",
                        command="vibe task install-guide --json",
                        mutation=False,
                        reason="Install/configure Beads (bd), then re-run reconcile --provider beads",
                    ),
                    next_action(
                        code="RECONCILE_RETRY_WHEN_AVAILABLE",
                        command="vibe task reconcile --dry-run --json --provider beads",
                        mutation=False,
                        reason="Re-run readonly reconcile after Beads is available",
                    ),
                    next_action(
                        code="RECONCILE_USE_FAKE",
                        command="vibe task reconcile --dry-run --json --provider fake",
                        mutation=False,
                        reason="Use fake provider only for local projection/fixture dry-runs",
                    ),
                ],
            },
            mutation_intent=False,
            effects=[],
        )

    report = reconcile_readonly(
        project_id=project_id,
        expected=expected,
        provider_tasks=provider_tasks,
        provider_kind=provider_kind,
        warnings=warnings,
    )

    data = report.to_dict()
    data["expected_tasks"] = [item.to_dict() for item in expected]
    data["phase"] = "11A"
    data["slice"] = 2
    data["mutation"] = False
    data["provider"] = provider_kind
    data["provider_available"] = True
    data["provider_kind"] = provider_kind
    data["provider_read_ok"] = True
    data["reconcile_skipped"] = False
    data["mode"] = "readonly"

    next_actions: list[dict[str, Any]] = [
        next_action(
            code="TASK_RECONCILE_READONLY",
            command=f"vibe task reconcile --dry-run --json --provider {provider_kind}",
            mutation=False,
            reason="Readonly reconcile only; does not create/update/delete Beads tasks",
        )
    ]
    counts = data.get("counts") or {}
    if (counts.get("missing") or 0) > 0 or (counts.get("stale") or 0) > 0:
        next_actions.append(
            next_action(
                code="PHASE11B_APPLY_PENDING",
                command="vibe task apply --dry-run --json --provider fake",
                mutation=False,
                reason="Review Phase 11B apply plan; use --apply --provider fake for local mutation only",
            )
        )

    return attach_operation_result(
        {
            "ok": True,
            "project_id": project_id,
            "mode": "readonly",
            "provider": provider_kind,
            "provider_available": True,
            "mutation": False,
            "data": data,
            "warnings": warnings,
            "next_actions": next_actions,
        },
        mutation_intent=False,
        effects=[],
    )
