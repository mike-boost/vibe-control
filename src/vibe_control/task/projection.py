"""Status-aware expected-task projection from roadmap-state SSOT.

Default Beads apply must create only current/future actionable work.
Completed historical phases are projected as non-actionable records for
skip_completed / optional_backfill_completed reporting — never open create_managed.

Primary source: docs/project/vibe-control-roadmap-state.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from vibe_control.task.marker import compute_managed_key, sha256_hex
from vibe_control.task.models import ExpectedTask, PhaseState
from vibe_control.task.roadmap_state import (
    DEFAULT_ROADMAP_STATE_PATH,
    RoadmapStateError,
    load_roadmap_state,
    select_next_actionable_task,
)

# Status/content SSOT (phase_state / actionable / next task).
STATUS_SSOT_ID = "vibe_control_roadmap_state"
STATUS_SSOT_PATH = DEFAULT_ROADMAP_STATE_PATH

# Stable managed_key identity stays on Front/Core-era path so Beads cache keys
# do not churn when high-frequency status moved to roadmap-state.
DEFAULT_SSOT_ID = "vibe_control_spec"
DEFAULT_SSOT_PATH = "docs/project/vibe-control-spec.md"

# Fixture fallback only when roadmap-state file is absent (unit tests).
# Production always uses docs/project/vibe-control-roadmap-state.md.
_FALLBACK_CATALOG: tuple[tuple[str, str, str, PhaseState, bool], ...] = (
    (
        "roadmap.phase11a",
        "implementation_phase",
        "Phase 11A — SSOT Specs and Beads Readonly Reconcile",
        "completed",
        False,
    ),
    (
        "roadmap.phase11b",
        "implementation_phase",
        "Phase 11B — Beads Import / Apply (local/fake baseline)",
        "completed",
        False,
    ),
    (
        "roadmap.phase11b.live_apply",
        "implementation_task",
        "Phase 11B — Beads live apply productization",
        "actionable",
        True,
    ),
    (
        "roadmap.phase11b.post_create_verify",
        "implementation_task",
        "Phase 11B — Beads apply post-create/readback verification",
        "actionable",
        True,
    ),
    (
        "roadmap.phase11b.update_path_validation",
        "implementation_task",
        "Phase 11B — Beads managed task update path validation",
        "actionable",
        True,
    ),
    (
        "roadmap.phase11b.provider_closeout",
        "implementation_task",
        "Phase 11B — provider-backed task apply closeout",
        "actionable",
        True,
    ),
    (
        "roadmap.phase12",
        "implementation_phase",
        "Phase 12 — Implementation Prompt Generator",
        "pending",
        True,
    ),
)


def _catalog_from_state(
    state: dict[str, Any],
) -> list[tuple[str, str, str, PhaseState, bool, bool]]:
    out: list[tuple[str, str, str, PhaseState, bool, bool]] = []
    for item in state.get("anchors") or []:
        out.append(
            (
                str(item["ssot_anchor"]),
                str(item["task_kind"]),
                str(item["title"]),
                str(item["phase_state"]),  # type: ignore[arg-type]
                bool(item["actionable"]),
                bool(item.get("design_only")),
            )
        )
    return out


def _resolve_catalog(
    repo_root: Path,
) -> tuple[list[tuple[str, str, str, PhaseState, bool, bool]], Path]:
    try:
        state = load_roadmap_state(repo_root)
        catalog = _catalog_from_state(state)
        path = repo_root / str(state.get("path") or STATUS_SSOT_PATH)
        return catalog, path
    except RoadmapStateError:
        path = repo_root / STATUS_SSOT_PATH
        return [(*row, False) for row in _FALLBACK_CATALOG], path


def _build_task(
    *,
    project_id: str,
    ssot_id: str,
    ssot_path: str,
    snapshot_hash: str,
    anchor: str,
    task_kind: str,
    title: str,
    phase_state: PhaseState,
    actionable: bool,
    design_only: bool = False,
) -> ExpectedTask:
    managed_key = compute_managed_key(
        project_id=project_id,
        ssot_id=ssot_id,
        ssot_path=ssot_path,
        ssot_anchor=anchor,
        task_kind=task_kind,
    )
    # design_only is projection metadata only — excluded from source_item_hash so
    # managed identity does not churn when design_only flags are added.
    source_item_hash = sha256_hex(
        f"{anchor}\n{task_kind}\n{phase_state}\n{actionable}\n{snapshot_hash}"
    )
    return ExpectedTask(
        project_id=project_id,
        ssot_id=ssot_id,
        ssot_path=ssot_path,
        ssot_anchor=anchor,
        task_kind=task_kind,
        managed_key=managed_key,
        title=title,
        ssot_snapshot_hash=snapshot_hash,
        source_item_hash=source_item_hash,
        phase_state=phase_state,
        actionable=actionable,
        design_only=design_only,
    )


def project_expected_tasks(
    *,
    project_id: str,
    repo_root: Path,
    ssot_id: str | None = None,
    ssot_path: str | None = None,
    actionable_only: bool = False,
) -> list[ExpectedTask]:
    """Project expected tasks from roadmap-state (status-aware)."""
    catalog, status_path = _resolve_catalog(repo_root)
    use_id = ssot_id or DEFAULT_SSOT_ID
    use_path = ssot_path or DEFAULT_SSOT_PATH
    snapshot_hash = (
        sha256_hex(status_path.read_bytes()) if status_path.is_file() else sha256_hex("")
    )

    expected: list[ExpectedTask] = []
    for anchor, task_kind, title, phase_state, actionable, design_only in catalog:
        if actionable_only and not actionable:
            continue
        expected.append(
            _build_task(
                project_id=project_id,
                ssot_id=use_id,
                ssot_path=use_path,
                snapshot_hash=snapshot_hash,
                anchor=anchor,
                task_kind=task_kind,
                title=title,
                phase_state=phase_state,
                actionable=actionable,
                design_only=design_only,
            )
        )
    return expected


def project_actionable_expected_tasks(
    *,
    project_id: str,
    repo_root: Path,
    ssot_id: str | None = None,
    ssot_path: str | None = None,
) -> list[ExpectedTask]:
    """Expected tasks that may become create_managed / update_managed."""
    return project_expected_tasks(
        project_id=project_id,
        repo_root=repo_root,
        ssot_id=ssot_id,
        ssot_path=ssot_path,
        actionable_only=True,
    )


def project_completed_expected_tasks(
    *,
    project_id: str,
    repo_root: Path,
    ssot_id: str | None = None,
    ssot_path: str | None = None,
) -> list[ExpectedTask]:
    """Completed / baseline shells for skip_completed reporting only."""
    return [
        t
        for t in project_expected_tasks(
            project_id=project_id,
            repo_root=repo_root,
            ssot_id=ssot_id,
            ssot_path=ssot_path,
            actionable_only=False,
        )
        if not t.actionable
    ]


def project_slice1_expected_tasks(
    *,
    project_id: str,
    repo_root: Path,
    ssot_id: str | None = None,
    ssot_path: str | None = None,
) -> list[ExpectedTask]:
    """Compatibility alias: actionable expected tasks for reconcile/apply create path."""
    return project_actionable_expected_tasks(
        project_id=project_id,
        repo_root=repo_root,
        ssot_id=ssot_id,
        ssot_path=ssot_path,
    )


def project_all_expected_tasks(
    *,
    project_id: str,
    repo_root: Path,
) -> list[ExpectedTask]:
    """All projected tasks including completed (for explicit prompt selectors)."""
    return project_expected_tasks(
        project_id=project_id,
        repo_root=repo_root,
        actionable_only=False,
    )


def next_actionable_selection(*, repo_root: Path) -> dict[str, Any]:
    """Dogfood/next selection from roadmap-state; never invents Phase 13."""
    try:
        state = load_roadmap_state(repo_root)
    except RoadmapStateError as exc:
        return {
            "no_actionable_next_task": True,
            "next_actionable_task": None,
            "reason": exc.code,
            "message": exc.message,
        }
    return select_next_actionable_task(state)


def projection_rules_summary(*, repo_root: Path | None = None) -> dict[str, Any]:
    if repo_root is not None:
        try:
            state = load_roadmap_state(repo_root)
            anchors = state.get("anchors") or []
            return {
                "completed_not_open_create": True,
                "source": "roadmap_state",
                "actionable_anchors": [
                    a["ssot_anchor"] for a in anchors if a.get("actionable")
                ],
                "completed_anchors": [
                    a["ssot_anchor"] for a in anchors if not a.get("actionable")
                ],
                "next_actionable_task": state.get("next_actionable_task"),
                "no_actionable_next_task": bool(state.get("no_actionable_next_task")),
            }
        except RoadmapStateError:
            pass
    return {
        "completed_not_open_create": True,
        "source": "fallback_catalog",
        "actionable_anchors": [a for a, _, _, _, actionable in _FALLBACK_CATALOG if actionable],
        "completed_anchors": [a for a, _, _, _, actionable in _FALLBACK_CATALOG if not actionable],
        "next_actionable_task": None,
        "no_actionable_next_task": True,
    }
