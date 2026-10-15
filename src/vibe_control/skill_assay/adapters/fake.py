"""In-process fake host adapter for Skill Assay tests."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from vibe_control.skill_assay.adapters import HostDoctorResult, HostRunResult
from vibe_control.skill_assay.adapters.base import inject_skill_tree
from vibe_control.skill_assay.constants import ASSISTANT_TEXT_LIMIT
from vibe_control.skill_assay.normalize import normalize_fields, sha256_text
from vibe_control.skill_assay.redaction import redact_text, truncate_events


class FakeHostAdapter:
    host_id = "fake"

    def __init__(
        self,
        *,
        field_sequence: list[dict[str, Any]] | None = None,
        doctor_ok: bool = True,
        assistant_text_sequence: list[str] | None = None,
    ) -> None:
        self._fields = list(field_sequence or [])
        self._assistant_texts = list(assistant_text_sequence or [])
        self._call = 0
        self._doctor_ok = doctor_ok
        self.prepared_sessions: list[str] = []

    def doctor(self) -> HostDoctorResult:
        if not self._doctor_ok:
            return HostDoctorResult(
                host_id=self.host_id,
                ok=False,
                support_state="unavailable",
                blockers=["FAKE_HOST_DISABLED"],
            )
        return HostDoctorResult(
            host_id=self.host_id,
            ok=True,
            support_state="supported",
            details={"note": "in-process fake"},
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
        del scenario  # unused; keep signature parity with HostAdapter
        session_id = f"fake-session-{uuid.uuid4().hex[:12]}"
        workspace = work_root / f"run-{run_index}"
        workspace.mkdir(parents=True, exist_ok=True)
        skill_dest = inject_skill_tree(
            skill_snapshot=skill_snapshot,
            workspace=workspace,
            layout="cursor",
        )
        artifact = workspace / "artifact"
        artifact.mkdir(parents=True, exist_ok=True)
        self.prepared_sessions.append(session_id)
        return {
            "session_id": session_id,
            "workspace": workspace.as_posix(),
            "artifact_dir": artifact.as_posix(),
            "skill_dest": skill_dest.as_posix(),
            "skill_id": skill_snapshot.name,
            "run_index": run_index,
            "assay_id": assay_id,
        }

    def run(
        self,
        *,
        prepared: dict[str, Any],
        scenario: dict[str, Any],
    ) -> HostRunResult:
        idx = self._call
        self._call += 1
        if idx < len(self._fields):
            fields = dict(self._fields[idx])
        else:
            fields = {"ok": True, "nonce": f"n{idx}"}
        artifact = Path(prepared["artifact_dir"])
        (artifact / "out.json").write_text(
            json.dumps(fields, indent=2) + "\n",
            encoding="utf-8",
        )
        skill_id = str(prepared.get("skill_id") or "skill")
        if idx < len(self._assistant_texts):
            assistant_text = self._assistant_texts[idx]
        else:
            assistant_text = (
                f"Mode: execute\n"
                f"## Status\n"
                f"Loaded /{skill_id}\n"
                f"## Decision\n"
                f"Emitting structured fields for assay.\n"
                f"## Next\n"
                f"Return JSON artifact.\n"
                f"## Open\n"
                f"None.\n\n"
                f"```json\n{json.dumps(fields, indent=2)}\n```\n"
                f"prompt={str(scenario.get('prompt') or '')[:80]}\n"
            )
        return HostRunResult(
            session_id=str(prepared["session_id"]),
            workspace_path=str(prepared["workspace"]),
            exit_status=0,
            fields=fields,
            events=[
                {"type": "session_start", "session_id": prepared["session_id"]},
                {"type": "skill_invoked", "skill_id": skill_id},
                {"type": "assistant", "text": assistant_text},
                {"type": "session_end", "session_id": prepared["session_id"]},
            ],
            artifact_dir=str(artifact),
            unknowns=[],
            assistant_text=assistant_text,
            model_requested=(
                str(scenario["model"]) if scenario.get("model") is not None else None
            ),
            model_resolved="fake-model",
            tool_summary=[],
            skill_invocation="observed",
            usage={"prompt_tokens": 1, "completion_tokens": 1},
            isolation={
                "scope": "full",
                "ambient_user_skills_possible": False,
                "layout": "cursor",
            },
        )

    def normalize(
        self,
        *,
        raw: HostRunResult,
        scenario: dict[str, Any],
        artifact_dir: Path,
    ) -> dict[str, Any]:
        text = redact_text(raw.assistant_text or "", limit=ASSISTANT_TEXT_LIMIT)
        fields = normalize_fields(
            assistant_text=text,
            artifact_dir=Path(artifact_dir),
            scenario=scenario,
            base_fields=raw.fields,
        )
        return {
            "fields": fields,
            "assistant_text": text,
            "assistant_text_sha256": sha256_text(text),
            "events": truncate_events(list(raw.events)),
            "unknowns": list(raw.unknowns),
            "model_requested": raw.model_requested,
            "model_resolved": raw.model_resolved or "fake-model",
            "tool_summary": list(raw.tool_summary),
            "skill_invocation": raw.skill_invocation or "observed",
            "usage": dict(raw.usage),
            "isolation": dict(raw.isolation)
            or {"scope": "full", "ambient_user_skills_possible": False},
        }

    def cleanup(self, *, prepared: dict[str, Any]) -> None:
        # Keep workspace for tests; orchestrator may remove later.
        del prepared
        return None
