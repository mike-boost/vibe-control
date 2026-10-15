"""Host adapter protocol for Skill Assay."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass
class HostDoctorResult:
    host_id: str
    ok: bool
    support_state: str  # supported | experimental | unverified | unavailable
    details: dict[str, Any] = field(default_factory=dict)
    blockers: list[str] = field(default_factory=list)


@dataclass
class HostRunResult:
    session_id: str
    workspace_path: str
    exit_status: int
    fields: dict[str, Any]
    events: list[dict[str, Any]]
    artifact_dir: str
    unknowns: list[str] = field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None
    assistant_text: str = ""
    assistant_text_sha256: str = ""
    model_requested: str | None = None
    model_resolved: str | None = None
    tool_summary: list[dict[str, Any]] = field(default_factory=list)
    skill_invocation: str = "unknown"  # requested | observed | unknown
    usage: dict[str, Any] = field(default_factory=dict)
    isolation: dict[str, Any] = field(default_factory=dict)


class HostAdapter(Protocol):
    host_id: str

    def doctor(self) -> HostDoctorResult: ...

    def prepare(
        self,
        *,
        assay_id: str,
        run_index: int,
        skill_snapshot: Path,
        work_root: Path,
        scenario: dict[str, Any],
    ) -> dict[str, Any]: ...

    def run(
        self,
        *,
        prepared: dict[str, Any],
        scenario: dict[str, Any],
    ) -> HostRunResult: ...

    def normalize(
        self,
        *,
        raw: HostRunResult,
        scenario: dict[str, Any],
        artifact_dir: Path,
    ) -> dict[str, Any]: ...

    def cleanup(self, *, prepared: dict[str, Any]) -> None: ...
