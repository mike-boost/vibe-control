#!/usr/bin/env python3
"""Provider readiness local/fake acceptance (no real mutation)."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

PHASE = Path(__file__).resolve().parent
REPO_ROOT = PHASE.parents[1]
sys.path.insert(0, str(REPO_ROOT / "acceptance"))
from lib.observed_output import save_observed  # noqa: E402

sys.path.insert(0, str(REPO_ROOT / "src"))
from vibe_control.product_readiness import build_probe_from_parts  # noqa: E402
from vibe_control.integration import build_integration_status  # noqa: E402
from vibe_control.knowledge.notebooklm_provider import NotebookLMProvider, NotebookLMStatus  # noqa: E402
from vibe_control.task.beads_provider import BeadsProvider, BeadsStatus  # noqa: E402


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


class FakeNLM(NotebookLMProvider):
    def which(self):
        return "/tmp/fake-nlm"

    def status(self, *, probe_auth: bool = False) -> NotebookLMStatus:
        return NotebookLMStatus(installed=True, executable="/tmp/fake-nlm", version="x", message="ok")


class FakeBeads(BeadsProvider):
    def which(self):
        return "/tmp/fake-bd"

    def status(self) -> BeadsStatus:
        return BeadsStatus(installed=True, executable="/tmp/fake-bd", version="x", message="ok")

    def init_preview(self) -> BeadsStatus:
        return self.status()


def main() -> int:
    checks: list[CheckResult] = []
    enabled_components = {
        "knowledge": {"enabled": True, "support_state": "supported"},
        "task": {"enabled": True, "support_state": "supported"},
    }
    unavail = build_probe_from_parts(
        knowledge_available=False,
        knowledge_target_ok=False,
        sync_state="unavailable",
        task_available=False,
        task_mode="unavailable",
        task_readable=False,
        components=enabled_components,
    )
    checks.append(
        CheckResult(
            "unavailable_not_product_ready",
            unavail.product_ready is False,
            str(unavail.blocked_reasons),
        )
    )
    ready = build_probe_from_parts(
        knowledge_available=True,
        knowledge_target_ok=True,
        sync_state="synced",
        task_available=True,
        task_mode="readonly",
        task_readable=True,
        ready_queue_available=True,
        components=enabled_components,
    )
    checks.append(CheckResult("healthy_is_product_ready", ready.product_ready is True, ready.evidence_hash))

    data = build_integration_status(
        repo_root=REPO_ROOT,
        notebooklm=FakeNLM(),
        beads=FakeBeads(),
        probe_product=False,
        knowledge_parts={
            "available": True,
            "target_ok": True,
            "sync_state": "synced",
            "required_updates_count": 0,
            "candidate_count": 0,
            "orphan_managed_count": 0,
        },
        task_parts={
            "available": True,
            "mode": "readonly",
            "readable": True,
            "ready_queue_available": True,
        },
    )
    checks.append(
        CheckResult(
            "fallback_not_product_ready_flag",
            data["repo"]["fallback_is_product_ready"] is False,
            str(data["repo"]),
        )
    )
    checks.append(
        CheckResult(
            "integration_exposes_product_ready",
            "product_ready" in data and "knowledge_provider" in data and "task_provider" in data,
            f"product_ready={data.get('product_ready')}",
        )
    )

    failed = [c for c in checks if not c.ok]
    summary = {
        "ok": not failed,
        "phase": "provider-readiness",
        "checks": [{"name": c.name, "ok": c.ok, "detail": c.detail} for c in checks],
        "mutation": False,
        "real_notebooklm": False,
        "real_beads_mutation": False,
    }
    save_observed(PHASE, "summary.json", summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
