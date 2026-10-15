"""Stub adapters for real hosts until live smoke marks them supported."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from vibe_control.skill_assay.adapters import HostDoctorResult, HostRunResult
from vibe_control.skill_assay.errors import SkillAssayError


class _UnverifiedHostAdapter:
    """Placeholder: doctor reports unverified; execute fails closed."""

    def __init__(self, host_id: str) -> None:
        self.host_id = host_id

    def doctor(self) -> HostDoctorResult:
        return HostDoctorResult(
            host_id=self.host_id,
            ok=False,
            support_state="unverified",
            details={
                "note": (
                    "Live adapter not verified in this environment. "
                    "Install optional SDK deps and run real_skill_host smoke."
                )
            },
            blockers=["HOST_ADAPTER_UNVERIFIED"],
        )

    def prepare(
        self,
        *,
        assay_id: str,
        run_index: int,
        skill_snapshot: Path,
        work_root: Path,
        scenario: dict[str, Any],
    ) -> dict[str, Any]:
        raise SkillAssayError(
            "SKILL_ASSAY_ADAPTER_UNVERIFIED",
            f"host {self.host_id} adapter is unverified; refuse execute",
            {"host_id": self.host_id},
        )

    def run(
        self,
        *,
        prepared: dict[str, Any],
        scenario: dict[str, Any],
    ) -> HostRunResult:
        raise SkillAssayError(
            "SKILL_ASSAY_ADAPTER_UNVERIFIED",
            f"host {self.host_id} adapter is unverified; refuse execute",
            {"host_id": self.host_id},
        )

    def normalize(
        self,
        *,
        raw: HostRunResult,
        scenario: dict[str, Any],
        artifact_dir: Path,
    ) -> dict[str, Any]:
        raise SkillAssayError(
            "SKILL_ASSAY_ADAPTER_UNVERIFIED",
            f"host {self.host_id} adapter is unverified; refuse execute",
            {"host_id": self.host_id},
        )

    def cleanup(self, *, prepared: dict[str, Any]) -> None:
        return None


def cursor_adapter() -> _UnverifiedHostAdapter:
    return _UnverifiedHostAdapter("cursor")


def github_copilot_adapter() -> _UnverifiedHostAdapter:
    return _UnverifiedHostAdapter("github-copilot")
