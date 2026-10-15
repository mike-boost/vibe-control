"""Local embedded ephemeral task cache mode alignment tests."""

from __future__ import annotations

from pathlib import Path

from vibe_control.closeout import PROJECT_SOURCES_ADVISOR_FILES
from vibe_control.product_readiness import build_probe_from_parts
from vibe_control.task.cache import evaluate_task_cache_state
from vibe_control.task.cache_reset import run_task_cache_reset


def _knowledge_ready_parts():
    from vibe_control.components import resolve_component_runtime

    return dict(
        knowledge_available=True,
        knowledge_target_ok=True,
        sync_state="synced",
        required_updates_count=0,
        candidate_count=0,
        orphan_managed_count=0,
        task_available=True,
        task_mode="readonly",
        task_readable=True,
        ready_queue_available=True,
        components=resolve_component_runtime(
            {"knowledge": {"enabled": True}, "task": {"enabled": True}}
        )["components"],
    )


def test_task_cache_stale_blocks_product_ready_allows_convergence():
    cache = evaluate_task_cache_state(
        reconcile_counts={
            "matched": 0,
            "missing": 0,
            "stale": 5,
            "duplicate": 0,
            "conflict": 0,
            "unmanaged": 0,
        },
        apply_plan_counts={"create": 0, "update": 5, "skip": 0, "blocked": 0},
        knowledge_ready=True,
        task_available=True,
        task_readable=True,
    )
    assert cache["task_cache_current"] is False
    assert cache["safe_task_convergence_allowed"] is True
    assert cache["task_cache_reset_required"] is False
    codes = [a["code"] for a in cache["next_actions"]]
    assert "TASK_CACHE_CONVERGE_MANAGED" in codes

    probe = build_probe_from_parts(
        **_knowledge_ready_parts(),
        task_cache_current=False,
        task_cache=cache,
    )
    assert probe.product_ready is False
    assert "task_cache_not_current" in probe.blocked_reasons


def test_task_cache_missing_allows_safe_create_convergence():
    cache = evaluate_task_cache_state(
        reconcile_counts={
            "matched": 0,
            "missing": 3,
            "stale": 0,
            "duplicate": 0,
            "conflict": 0,
            "unmanaged": 0,
        },
        apply_plan_counts={"create": 3, "update": 0, "skip": 0, "blocked": 0},
        knowledge_ready=True,
        task_available=True,
        task_readable=True,
    )
    assert cache["task_cache_current"] is False
    assert cache["safe_task_convergence_allowed"] is True
    assert any(a["code"] == "TASK_CACHE_CONVERGE_APPLY" for a in cache["next_actions"])


def test_task_cache_clean_product_ready():
    cache = evaluate_task_cache_state(
        reconcile_counts={
            "matched": 5,
            "missing": 0,
            "stale": 0,
            "duplicate": 0,
            "conflict": 0,
            "unmanaged": 0,
        },
        apply_plan_counts={"create": 0, "update": 0, "skip": 4, "blocked": 0},
        knowledge_ready=True,
        task_available=True,
        task_readable=True,
    )
    assert cache["task_cache_current"] is True
    assert cache["task_cache_action_required"] is False
    probe = build_probe_from_parts(
        **_knowledge_ready_parts(),
        task_cache_current=True,
        task_cache=cache,
    )
    assert probe.product_ready is True


def test_task_cache_unmanaged_requires_reset_not_repair():
    cache = evaluate_task_cache_state(
        reconcile_counts={
            "matched": 1,
            "missing": 0,
            "stale": 0,
            "duplicate": 0,
            "conflict": 0,
            "unmanaged": 2,
        },
        apply_plan_counts={"create": 0, "update": 0, "skip": 2, "blocked": 0},
        knowledge_ready=True,
        task_available=True,
        task_readable=True,
    )
    assert cache["task_cache_current"] is False
    assert cache["safe_task_convergence_allowed"] is False
    assert cache["task_cache_reset_required"] is True
    blob = str(cache["next_actions"])
    assert "TASK_CACHE_RESET_DRY_RUN" in blob
    assert "ad hoc" in blob.lower() or "reset/regenerate" in blob.lower()
    assert "adopt" in blob.lower() or "pollution" in blob.lower()


def test_task_cache_duplicate_conflict_require_reset():
    for key in ("duplicate", "conflict"):
        counts = {
            "matched": 0,
            "missing": 0,
            "stale": 0,
            "duplicate": 0,
            "conflict": 0,
            "unmanaged": 0,
        }
        counts[key] = 1
        cache = evaluate_task_cache_state(
            reconcile_counts=counts,
            apply_plan_counts={"create": 0, "update": 0, "skip": 1, "blocked": 0},
            knowledge_ready=True,
            task_available=True,
            task_readable=True,
        )
        assert cache["task_cache_reset_required"] is True
        assert cache["safe_task_convergence_allowed"] is False
        assert "bd " not in str(cache["next_actions"]).lower() or "vibe task" in str(
            cache["next_actions"]
        )


def test_phase12_prompt_blocks_when_task_cache_not_current(tmp_path):
    from helpers import minimal_config_dict, write_control_yaml, write_doc
    from vibe_control.implementation.prompt import build_implementation_prompt

    write_control_yaml(
        tmp_path,
        {
            **minimal_config_dict(),
            "project": {"id": "vibe-control", "name": "Vibe"},
            # Enable task so task-cache warnings remain meaningful blockers.
            "components": {
                "knowledge": {"enabled": False},
                "task": {"enabled": True},
                "sdd": {"enabled": False},
                "tdd": {"enabled": False},
            },
        },
    )
    write_doc(tmp_path, "docs/project/vibe-control-spec.md", "# Spec\nPhase 12\n")
    result = build_implementation_prompt(
        repo_root=tmp_path,
        task_selector="roadmap.phase12",
        product_ready=False,
        readiness_summary={
            "product_ready": False,
            "sync_state": "synced",
            "provider_ask_clean": True,
            "blocked_reasons": ["task_cache_not_current"],
        },
        knowledge_readiness={
            "sync_state": "synced",
            "provider_ask_clean": True,
            "available": True,
            "target_ok": True,
        },
        reconcile_counts={
            "matched": 0,
            "missing": 0,
            "stale": 5,
            "duplicate": 0,
            "conflict": 0,
            "unmanaged": 0,
        },
        apply_plan_counts={"create": 0, "update": 5, "skip": 0, "blocked": 0},
    )
    text = result["data"]["prompt"]
    assert "DO NOT start implementation" in text
    assert "Implement:" not in text.split("## Selected task anchor")[0]
    assert result["data"]["product_readiness"]["task_cache_current"] is False
    assert result["data"]["implementation_ready"] is False
    assert result["data"]["closeout_blocking"] is True or result["data"]["task_completed"] is True
    assert "task_cache_not_current" in result["warnings"]
    assert result["next_actions"]


def test_phase12_prompt_clean_cache_greenlights(tmp_path):
    from helpers import minimal_config_dict, write_control_yaml, write_doc
    from vibe_control.implementation.prompt import build_implementation_prompt

    write_control_yaml(
        tmp_path,
        {**minimal_config_dict(), "project": {"id": "vibe-control", "name": "Vibe"}},
    )
    write_doc(tmp_path, "docs/project/vibe-control-spec.md", "# Spec\nPhase 12\n")
    result = build_implementation_prompt(
        repo_root=tmp_path,
        task_selector="roadmap.phase12",
        product_ready=True,
        readiness_summary={
            "product_ready": True,
            "sync_state": "synced",
            "provider_ask_clean": True,
            "blocked_reasons": [],
        },
        knowledge_readiness={
            "sync_state": "synced",
            "provider_ask_clean": True,
            "available": True,
            "target_ok": True,
        },
        reconcile_counts={
            "matched": 5,
            "missing": 0,
            "stale": 0,
            "duplicate": 0,
            "conflict": 0,
            "unmanaged": 0,
        },
        apply_plan_counts={"create": 0, "update": 0, "skip": 4, "blocked": 0},
    )
    assert "Implement:" in result["data"]["prompt"]
    assert result["data"]["product_readiness"]["task_cache_current"] is True
    assert result["mutation"] is False
    assert "task_identity" in result["data"]
    assert "provider_task_id" not in result["data"]["task_identity"]


def test_project_sources_advisor_still_four_files():
    assert list(PROJECT_SOURCES_ADVISOR_FILES) == [
        "docs/project/vibe-control-spec.md",
        "docs/project/vibe-control-knowledge-spec.md",
        "docs/project/vibe-control-task-spec.md",
        "docs/project/vibe-control-roadmap-state.md",
    ]
    assert not any("/sync/" in p for p in PROJECT_SOURCES_ADVISOR_FILES)


def test_cache_reset_dry_run_and_fake_apply(tmp_path):
    from helpers import minimal_config_dict, write_control_yaml, write_doc
    from vibe_control.task.models import TaskRecord
    from vibe_control.task.marker import marker_from_expected, render_marker, sha256_hex
    from vibe_control.task.provider import FakeTaskProvider

    write_control_yaml(
        tmp_path,
        {**minimal_config_dict(), "project": {"id": "vibe-control", "name": "Vibe"}},
    )
    write_doc(tmp_path, "docs/project/vibe-control-spec.md", "# Spec\nPhase 12\n")
    write_doc(
        tmp_path,
        "docs/project/vibe-control-roadmap-state.md",
        """# Roadmap State

```yaml
roadmap_state_version: 1
next_actionable_task: null
no_actionable_next_task: true
anchors:
  - ssot_anchor: roadmap.phase12
    task_kind: implementation_phase
    title: "Phase 12"
    phase_state: completed
    actionable: false
```
""",
    )
    dry = run_task_cache_reset(repo_root=tmp_path, apply=False, provider_name="fake")
    assert dry["ok"] is True
    assert dry["mutation"] is False
    assert dry["data"]["task_cache_mode"] == "local_embedded_ephemeral"
    assert dry["data"]["plan"]["reset_scope"] == "vibe_managed_local_ephemeral_cache"
    assert dry["data"]["plan"]["regenerate_managed_count"] == 0

    unsupported = run_task_cache_reset(
        repo_root=tmp_path, apply=False, provider_name="fake", mode="team_shared"
    )
    assert unsupported["ok"] is False
    assert unsupported["error"]["code"] == "TASK_CACHE_MODE_UNSUPPORTED"

    # Fake provider with pollution record → apply clears + regenerates 0
    marker = marker_from_expected(
        project_id="vibe-control",
        ssot_id="vibe_control_spec",
        ssot_path="docs/project/vibe-control-spec.md",
        ssot_anchor="roadmap.phase11b.live_apply",
        task_kind="implementation_task",
        ssot_snapshot_hash=sha256_hex("old"),
        source_item_hash=sha256_hex("old-item"),
    )
    fake = FakeTaskProvider(
        [
            TaskRecord(
                provider_task_id="fake-pollution-1",
                title="old",
                description=render_marker(marker),
            )
        ]
    )
    applied = run_task_cache_reset(
        repo_root=tmp_path, apply=True, provider_name="fake", provider=fake
    )
    assert applied["ok"] is True
    assert applied["mutation"] is True
    assert applied["data"]["cleared"] is True
    assert applied["data"]["cleared_count"] >= 1
    assert applied["data"]["regenerated"] == 0
    assert fake.list_tasks() == []


def test_cache_reset_beads_apply_uses_adapter_runner(tmp_path):
    from helpers import minimal_config_dict, write_control_yaml, write_doc
    from vibe_control.task.models import TaskRecord
    from vibe_control.task.marker import marker_from_expected, render_marker, sha256_hex
    from vibe_control.task import cache_reset as cr
    from vibe_control.task.beads_readonly import BeadsReadonlyProvider

    write_control_yaml(
        tmp_path,
        {**minimal_config_dict(), "project": {"id": "vibe-control", "name": "Vibe"}},
    )
    write_doc(tmp_path, "docs/project/vibe-control-spec.md", "# Spec\n")
    write_doc(
        tmp_path,
        "docs/project/vibe-control-roadmap-state.md",
        """# Roadmap State

```yaml
roadmap_state_version: 1
next_actionable_task: null
no_actionable_next_task: true
anchors:
  - ssot_anchor: roadmap.phase12
    task_kind: implementation_phase
    title: "Phase 12"
    phase_state: completed
    actionable: false
```
""",
    )
    marker = marker_from_expected(
        project_id="vibe-control",
        ssot_id="vibe_control_spec",
        ssot_path="docs/project/vibe-control-spec.md",
        ssot_anchor="roadmap.phase12",
        task_kind="implementation_phase",
        ssot_snapshot_hash=sha256_hex("x"),
        source_item_hash=sha256_hex("y"),
    )
    pollution = [
        TaskRecord(
            provider_task_id="vibe-control-abc",
            title="old p12",
            description=render_marker(marker),
        )
    ]

    class _StubReadonly(BeadsReadonlyProvider):
        def list_tasks(self):  # type: ignore[override]
            self.available = True
            return list(pollution)

    calls: list[list[str]] = []

    def _runner(argv: list[str]) -> dict:
        calls.append(list(argv))
        return {"ok": True, "returncode": 0, "argv_verb": "delete"}

    original = cr.BeadsReadonlyProvider
    cr.BeadsReadonlyProvider = _StubReadonly  # type: ignore[misc]
    try:
        result = run_task_cache_reset(
            repo_root=tmp_path,
            apply=True,
            provider_name="beads",
            bd_runner=_runner,
        )
    finally:
        cr.BeadsReadonlyProvider = original  # type: ignore[misc]

    assert result["ok"] is True
    assert result["mutation"] is True
    assert result["data"]["cleared_count"] == 1
    assert result["data"]["regenerated"] == 0
    for row in result["data"].get("cleared_records") or []:
        assert "provider_task_id" not in row
        assert row.get("provider_task_id_hash", "").startswith("sha256:")
    assert calls and "delete" in calls[0]
    assert "--force" in calls[0]
    blob = str(result)
    assert "vibe-control-abc" not in blob


def test_conflict_requires_reset_and_blocks_product_ready():
    cache = evaluate_task_cache_state(
        reconcile_counts={
            "matched": 0,
            "missing": 0,
            "stale": 0,
            "duplicate": 0,
            "conflict": 5,
            "unmanaged": 0,
        },
        apply_plan_counts={"create": 0, "update": 0, "skip": 0, "blocked": 0},
        knowledge_ready=True,
        task_available=True,
        task_readable=True,
    )
    assert cache["task_cache_mode"] == "local_embedded_ephemeral"
    assert cache["task_cache_current"] is False
    assert cache["task_cache_reset_required"] is True
    assert any(a["code"] == "TASK_CACHE_RESET_DRY_RUN" for a in cache["next_actions"])
    probe = build_probe_from_parts(
        **_knowledge_ready_parts(),
        task_cache_current=False,
        task_cache=cache,
    )
    assert probe.product_ready is False


def test_post_reset_empty_actionable_is_cache_current():
    cache = evaluate_task_cache_state(
        reconcile_counts={
            "matched": 0,
            "missing": 0,
            "stale": 0,
            "duplicate": 0,
            "conflict": 0,
            "unmanaged": 0,
        },
        apply_plan_counts={"create": 0, "update": 0, "skip": 0, "blocked": 0},
        knowledge_ready=True,
        task_available=True,
        task_readable=True,
    )
    assert cache["task_cache_current"] is True
    assert cache["task_cache_reset_required"] is False
    probe = build_probe_from_parts(
        **_knowledge_ready_parts(),
        task_cache_current=True,
        task_cache=cache,
    )
    assert probe.product_ready is True


def test_spec_mentions_local_embedded_ephemeral():
    front = Path("docs/project/vibe-control-spec.md").read_text(encoding="utf-8")
    task = Path("docs/project/vibe-control-task-spec.md").read_text(encoding="utf-8")
    assert "local_embedded_ephemeral" in front
    assert "local_embedded_ephemeral" in task
    assert "task_cache_current" in front
    assert "soft debt" in front.lower() or "soft debt" in task.lower()
