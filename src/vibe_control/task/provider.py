"""TaskProvider implementations (Phase 11A readonly + Phase 11B fake apply)."""

from __future__ import annotations

from vibe_control.task.models import TaskRecord


class FakeTaskProvider:
    """In-memory provider for tests and local fake apply."""

    name = "fake"

    def __init__(self, tasks: list[TaskRecord] | None = None):
        self._tasks = list(tasks or [])
        self._seq = 0

    def list_tasks(self) -> list[TaskRecord]:
        return list(self._tasks)

    def add(self, task: TaskRecord) -> None:
        """Test helper only — not a product mutation path."""
        self._tasks.append(task)

    def clear(self) -> None:
        """Test/local ephemeral cache clear — not a live Beads path."""
        self._tasks = []

    def create_managed(self, *, title: str, description: str) -> TaskRecord:
        """Phase 11B fake apply: create in-memory managed task."""
        self._seq += 1
        task = TaskRecord(
            provider_task_id=f"fake-{self._seq}",
            title=title,
            description=description,
        )
        self._tasks.append(task)
        return task

    def update_managed(
        self,
        *,
        provider_task_id: str,
        title: str,
        description: str,
    ) -> TaskRecord:
        """Phase 11B fake apply: update in-memory managed task by provider id."""
        for idx, task in enumerate(self._tasks):
            if task.provider_task_id == provider_task_id:
                updated = TaskRecord(
                    provider_task_id=provider_task_id,
                    title=title,
                    description=description,
                    relations=list(task.relations),
                    raw=dict(task.raw),
                )
                self._tasks[idx] = updated
                return updated
        raise KeyError(f"fake provider task not found: {provider_task_id}")
