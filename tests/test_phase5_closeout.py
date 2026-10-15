"""Phase 5 closeout: mutation contract, execution contract, and audit hardening."""

from __future__ import annotations

import re
from pathlib import Path

from vibe_control.cli import build_parser
from vibe_control.knowledge import sync_lifecycle


REPO = Path(__file__).resolve().parents[1]
UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.I,
)


def test_agents_references_mutation_and_execution_contracts():
    agents = (REPO / "AGENTS.md").read_text(encoding="utf-8")
    assert "docs/harness/real-integration-mutation-contract.md" in agents
    assert "docs/harness/phase-execution-contract.md" in agents


def test_real_integration_mutation_contract_exists_and_is_enforceable():
    path = REPO / "docs/harness/real-integration-mutation-contract.md"
    text = path.read_text(encoding="utf-8")
    assert path.is_file()
    lower = text.lower()
    assert "approved" in lower or "explicitly approved" in lower
    assert "scoped" in lower
    assert "accidental" in lower and "logged" in lower
    assert "broad notebook" in lower or "notebook-wide" in lower or "broad notebook `clean`" in lower
    assert "never delete unmanaged" in lower or "unmanaged sources" in lower
    assert "final inventory" in lower
    assert "stop and report" in lower


def test_phase_execution_contract_exists_and_covers_standard_flow():
    path = REPO / "docs/harness/phase-execution-contract.md"
    text = path.read_text(encoding="utf-8").lower()
    assert path.is_file()
    assert "baseline" in text
    assert "tests first" in text
    assert "acceptance" in text
    assert "mutation" in text
    assert "sensitive" in text
    assert "never push" in text


def test_phase5_report_records_accident_inventory_receipt_and_dry_run():
    report = (REPO / "acceptance/phase5/PHASE5_SYNC_LIFECYCLE_REPORT.md").read_text(
        encoding="utf-8"
    )
    lower = report.lower()
    assert "accidental" in lower and ("debug" in lower or "probe" in lower)
    assert "deleted" in lower
    assert "final inventory" in lower or "final opm-test inventory" in lower
    assert "document_count=2" in report or "document_count = 2" in report
    assert "already_current" in report
    assert "no push" in lower


def test_phase5_committed_reports_have_no_raw_ids():
    roots = [
        REPO / "acceptance/phase5/PHASE5_SYNC_LIFECYCLE_REPORT.md",
        REPO / "acceptance/phase5/PHASE5_CLOSEOUT_AUDIT.md",
    ]
    for path in roots:
        assert path.is_file(), path
        text = path.read_text(encoding="utf-8")
        assert '"notebook_ref"' not in text
        assert "NOTEBOOKLM_NOTEBOOK=" not in text
        assert not UUID_RE.search(text), f"uuid-like raw id in {path}"


def test_cleanup_phase4_residue_is_acceptance_scoped():
    help_text = (REPO / "src/vibe_control/cli.py").read_text(encoding="utf-8")
    assert "cleanup-phase4-residue" in help_text
    assert "--acceptance-cleanup" in help_text
    assert "INTERNAL" in help_text or "acceptance-only" in help_text.lower()

    parser = build_parser()
    # Missing acceptance gate must fail before mutation flags matter.
    ns = parser.parse_args(
        ["knowledge", "cleanup-phase4-residue", "--allow-delete", "--json"]
    )
    assert getattr(ns, "acceptance_cleanup", False) is False

    from types import SimpleNamespace

    from vibe_control.knowledge.remote_ops import cmd_cleanup_phase4_residue

    blocked = cmd_cleanup_phase4_residue(
        REPO,
        SimpleNamespace(
            notebook="OPM-test",
            dry_run=True,
            allow_delete=False,
            acceptance_cleanup=False,
            config=None,
        ),
    )
    assert blocked.get("ok") is False
    assert (blocked.get("error") or {}).get("code") == "ACCEPTANCE_CLEANUP_REQUIRED"


def test_residue_cleanup_only_exact_approved_titles():
    remote = [
        {"id": "a", "title": "VIBE_CONTROL_V0_5_SPEC.md"},
        {"id": "b", "title": "[vibe:vibe-control:DECISION_LOG] DECISION_LOG.md"},
        {"id": "c", "title": "unrelated.md"},
    ]
    plan = sync_lifecycle.plan_phase4_residue_cleanup(remote)
    assert plan["ok"] is True
    titles = {m["title"] for m in plan["matched"]}
    assert titles == set(sync_lifecycle.APPROVED_PHASE4_RESIDUE_TITLES)
    assert "unrelated.md" not in titles


def test_residue_cleanup_refuses_mismatched_set():
    plan = sync_lifecycle.plan_phase4_residue_cleanup(
        [{"id": "a", "title": "VIBE_CONTROL_V0_5_SPEC.md"}]
    )
    assert plan["ok"] is False
    assert plan["code"] == "RESIDUE_SET_MISMATCH"


def test_superseded_cleanup_only_after_receipt_switch_and_never_unmanaged():
    # Candidates require history.state=superseded with a distinct current id.
    receipt = {
        "documents": {
            "doc": {
                "managed_name": "vibe__vibe-control__doc",
                "current": {"provider_source_id": "new"},
                "history": [
                    {"provider_source_id": "old", "state": "superseded"},
                    {"provider_source_id": "also-old", "state": "ready"},  # not superseded
                ],
            }
        }
    }
    cands = sync_lifecycle.superseded_cleanup_candidates(receipt)
    assert {c["provider_source_id"] for c in cands} == {"old"}

    # No receipt => no cleanup candidates (cannot delete unmanaged by heuristic).
    assert sync_lifecycle.superseded_cleanup_candidates(None) == []
    assert sync_lifecycle.superseded_cleanup_candidates({"documents": {}}) == []


def test_phase4f_harness_still_lists_core_docs():
    # Closeout adds docs; older phase4f acceptance only checks the original three.
    for rel in (
        "docs/harness/knowledge-provider-boundary.md",
        "docs/harness/notebooklm-source-lifecycle-contract.md",
        "docs/harness/receipt-state-contract.md",
        "docs/harness/real-integration-mutation-contract.md",
        "docs/harness/phase-execution-contract.md",
    ):
        assert (REPO / rel).is_file()
