"""Skill Assay diagnose orchestration."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vibe_control.skill_assay.adapters import HostAdapter, HostRunResult
from vibe_control.skill_assay.adapters.fake import FakeHostAdapter
from vibe_control.skill_assay.checks import run_typed_checks
from vibe_control.skill_assay.comparison import compute_stability
from vibe_control.skill_assay.constants import (
    DEFAULT_RUNS,
    HOST_IDS,
    MAX_RUNS,
    MIN_RUNS,
    SCHEMA_EVIDENCE,
    SCHEMA_TRACE,
)
from vibe_control.skill_assay.errors import SkillAssayError
from vibe_control.skill_assay.scenario import load_scenario, scenario_from_prompt_file
from vibe_control.skill_assay.snapshot import snapshot_skill
from vibe_control.skill_assay.storage import (
    assay_dir,
    new_assay_id,
    write_evidence,
    write_json_atomic,
    write_meta,
)


def default_adapters() -> dict[str, HostAdapter]:
    return {"fake": FakeHostAdapter()}


def _apply_normalized(raw: HostRunResult, normalized: dict[str, Any]) -> HostRunResult:
    return HostRunResult(
        session_id=raw.session_id,
        workspace_path=raw.workspace_path,
        exit_status=raw.exit_status,
        fields=dict(normalized.get("fields") or raw.fields),
        events=list(normalized.get("events") or raw.events),
        artifact_dir=raw.artifact_dir,
        unknowns=list(normalized.get("unknowns") or raw.unknowns),
        error_code=raw.error_code,
        error_message=raw.error_message,
        assistant_text=str(normalized.get("assistant_text") or raw.assistant_text or ""),
        assistant_text_sha256=str(
            normalized.get("assistant_text_sha256") or raw.assistant_text_sha256 or ""
        ),
        model_requested=normalized.get("model_requested", raw.model_requested),
        model_resolved=normalized.get("model_resolved", raw.model_resolved),
        tool_summary=list(normalized.get("tool_summary") or raw.tool_summary),
        skill_invocation=str(
            normalized.get("skill_invocation") or raw.skill_invocation or "unknown"
        ),
        usage=dict(normalized.get("usage") or raw.usage),
        isolation=dict(normalized.get("isolation") or raw.isolation),
    )


def _read_git_diff(workspace: Path) -> str | None:
    diff_path = workspace / "artifact" / "git.diff"
    if diff_path.is_file():
        return diff_path.read_text(encoding="utf-8", errors="replace")
    return None


def _checks_pass_rate(check_batches: list[list[dict[str, Any]]]) -> float | None:
    total = 0
    passed = 0
    for batch in check_batches:
        for item in batch:
            total += 1
            if item.get("pass"):
                passed += 1
    if total == 0:
        return None
    return round(passed / total, 4)


def run_diagnose(
    *,
    repo_root: Path,
    skill_path: Path,
    host_id: str,
    runs: int = DEFAULT_RUNS,
    execute: bool = False,
    scenario_path: Path | None = None,
    prompt_file: Path | None = None,
    baseline_host: str | None = None,
    adapters: dict[str, HostAdapter] | None = None,
) -> dict[str, Any]:
    if baseline_host:
        raise SkillAssayError(
            "SKILL_ASSAY_BASELINE_HOST_NOT_IMPLEMENTED",
            "cross-host --baseline-host is reserved; v1 supports single-host evidence only",
            {"baseline_host": baseline_host},
        )
    if host_id not in HOST_IDS and host_id not in (adapters or {}):
        raise SkillAssayError(
            "SKILL_ASSAY_HOST_UNKNOWN",
            f"unknown host_id: {host_id}",
            {"host_id": host_id, "allowed": sorted(HOST_IDS)},
        )
    if runs < MIN_RUNS or runs > MAX_RUNS:
        raise SkillAssayError(
            "SKILL_ASSAY_RUNS_INVALID",
            f"runs must be between {MIN_RUNS} and {MAX_RUNS}",
            {"runs": runs},
        )
    if scenario_path is None and prompt_file is None:
        raise SkillAssayError(
            "SKILL_ASSAY_SCENARIO_REQUIRED",
            "provide --scenario or --prompt-file",
        )
    if scenario_path is not None and prompt_file is not None:
        raise SkillAssayError(
            "SKILL_ASSAY_SCENARIO_AMBIGUOUS",
            "provide only one of --scenario or --prompt-file",
        )

    scenario = (
        load_scenario(scenario_path)
        if scenario_path is not None
        else scenario_from_prompt_file(prompt_file)  # type: ignore[arg-type]
    )
    adapter_map = adapters if adapters is not None else default_adapters()
    if host_id not in adapter_map:
        raise SkillAssayError(
            "SKILL_ASSAY_ADAPTER_UNAVAILABLE",
            f"no adapter registered for host {host_id}",
            {"host_id": host_id},
        )
    adapter = adapter_map[host_id]
    doctor = adapter.doctor()
    causal_scope = "cross_host" if baseline_host else "single_host"

    plan = {
        "host_id": host_id,
        "baseline_host": baseline_host,
        "planned_runs": runs,
        "skill_path": Path(skill_path).resolve().as_posix(),
        "scenario_prompt_chars": len(str(scenario.get("prompt") or "")),
        "execution_profile": scenario.get("execution_profile", "response_only"),
        "timeout_seconds": scenario.get("timeout_seconds", 300),
        "model": scenario.get("model"),
        "doctor": {
            "ok": doctor.ok,
            "support_state": doctor.support_state,
            "blockers": list(doctor.blockers),
        },
        "causal_scope": causal_scope,
        "dry_run": not execute,
    }
    if not execute:
        return plan

    if not doctor.ok:
        raise SkillAssayError(
            "SKILL_ASSAY_HOST_NOT_READY",
            f"host {host_id} is not ready",
            {"blockers": doctor.blockers, "support_state": doctor.support_state},
        )

    assay_id = new_assay_id(host_id=host_id)
    root = assay_dir(repo_root, assay_id)
    skill_name = Path(skill_path).resolve().name
    snap_dest = root / "snapshot" / skill_name
    snap = snapshot_skill(Path(skill_path), dest=snap_dest)
    work_root = root / "workspaces"
    work_root.mkdir(parents=True, exist_ok=True)
    runs_dir = root / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    write_meta(
        repo_root,
        assay_id,
        {
            "host_id": host_id,
            "baseline_host": baseline_host,
            "runs": runs,
            "skill_id": snap["skill_id"],
            "tree_hash": snap["tree_hash"],
            "execution_profile": scenario.get("execution_profile", "response_only"),
            "timeout_seconds": scenario.get("timeout_seconds", 300),
            "model": scenario.get("model"),
            "created_at": datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
            "causal_scope": causal_scope,
        },
    )

    run_summaries: list[dict[str, Any]] = []
    stability_inputs: list[dict[str, Any]] = []
    all_unknowns: list[str] = []
    check_batches: list[list[dict[str, Any]]] = []
    models_seen: set[str] = set()
    assistant_nonempty_count = 0
    skill_invocation_counts: dict[str, int] = {}

    for run_index in range(runs):
        prepared = adapter.prepare(
            assay_id=assay_id,
            run_index=run_index,
            skill_snapshot=snap_dest,
            work_root=work_root,
            scenario=scenario,
        )
        result: HostRunResult | None = None
        checks: list[dict[str, Any]] = []
        try:
            raw = adapter.run(prepared=prepared, scenario=scenario)
            artifact_dir = Path(raw.artifact_dir)
            normalized = adapter.normalize(
                raw=raw,
                scenario=scenario,
                artifact_dir=artifact_dir,
            )
            result = _apply_normalized(raw, normalized)
            git_diff_text = _read_git_diff(Path(result.workspace_path))
            checks = run_typed_checks(
                list(scenario.get("checks") or []),
                artifact_dir=artifact_dir,
                exit_status=result.exit_status,
                git_diff_text=git_diff_text,
                assistant_text=result.assistant_text,
            )
        finally:
            adapter.cleanup(prepared=prepared)

        if result is None:
            raise SkillAssayError(
                "SKILL_ASSAY_RUN_FAILED",
                f"host run failed before producing a result for run {run_index}",
                {"run_index": run_index, "host_id": host_id},
            )

        check_batches.append(checks)
        all_unknowns.extend(result.unknowns)
        if result.assistant_text.strip():
            assistant_nonempty_count += 1
        if result.model_resolved:
            models_seen.add(str(result.model_resolved))
        inv = result.skill_invocation or "unknown"
        skill_invocation_counts[inv] = skill_invocation_counts.get(inv, 0) + 1

        assistant_path = runs_dir / f"{run_index}.assistant_text"
        assistant_path.write_text(result.assistant_text, encoding="utf-8")

        trace = {
            "schema": SCHEMA_TRACE,
            "assay_id": assay_id,
            "run_index": run_index,
            "host_id": host_id,
            "session_id": result.session_id,
            "workspace_path": result.workspace_path,
            "exit_status": result.exit_status,
            "fields": result.fields,
            "events": result.events,
            "artifact_dir": result.artifact_dir,
            "checks": checks,
            "unknowns": result.unknowns,
            "error_code": result.error_code,
            "error_message": result.error_message,
            "assistant_text_sha256": result.assistant_text_sha256,
            "assistant_text_ref": f"runs/{run_index}.assistant_text",
            "assistant_text_excerpt": (result.assistant_text or "")[:400],
            "model_requested": result.model_requested,
            "model_resolved": result.model_resolved,
            "tool_summary": result.tool_summary,
            "skill_invocation": result.skill_invocation,
            "usage": result.usage,
            "isolation": result.isolation,
            "tree_hash": snap["tree_hash"],
        }
        write_json_atomic(runs_dir / f"{run_index}.json", trace)
        run_summaries.append(
            {
                "run_index": run_index,
                "session_id": result.session_id,
                "exit_status": result.exit_status,
                "fields": result.fields,
                "error_code": result.error_code,
                "assistant_text_sha256": result.assistant_text_sha256,
                "assistant_text_ref": f"runs/{run_index}.assistant_text",
                "model_resolved": result.model_resolved,
                "skill_invocation": result.skill_invocation,
                "isolation": result.isolation,
                "checks_passed": sum(1 for c in checks if c.get("pass")),
                "checks_total": len(checks),
            }
        )
        stability_inputs.append({"fields": result.fields})

    expected_fields = list(scenario.get("expected_fields") or [])
    stability = compute_stability(stability_inputs, expected_fields=expected_fields or None)
    pass_rate = _checks_pass_rate(check_batches)
    distinct_sessions = len({r["session_id"] for r in run_summaries})

    facts = [
        f"host={host_id}",
        f"runs={runs}",
        f"tree_hash={snap['tree_hash']}",
        f"sessions={distinct_sessions}",
        f"assistant_nonempty={assistant_nonempty_count}/{runs}",
        f"models={sorted(models_seen)}",
        f"skill_invocation={skill_invocation_counts}",
        f"checks_pass_rate={pass_rate}",
        f"stable_fields={stability['stable_fields']}",
        f"unstable_fields={stability['unstable_fields']}",
        f"execution_profile={scenario.get('execution_profile', 'response_only')}",
    ]
    unknowns = sorted(set(all_unknowns))
    if causal_scope == "single_host":
        unknowns.append("cross_host_root_cause_not_in_scope")

    evidence = {
        "schema": SCHEMA_EVIDENCE,
        "assay_id": assay_id,
        "host_id": host_id,
        "baseline_host": baseline_host,
        "runs": runs,
        "causal_scope": causal_scope,
        "skill_id": snap["skill_id"],
        "tree_hash": snap["tree_hash"],
        "execution_profile": scenario.get("execution_profile", "response_only"),
        "stability": stability,
        "run_summaries": run_summaries,
        "checks": check_batches,
        "checks_summary": {
            "pass_rate": pass_rate,
            "runs_with_checks": sum(1 for batch in check_batches if batch),
        },
        "facts": facts,
        "unknowns": unknowns,
        "next_actions": [
            {
                "code": "SKILL_ASSAY_FINALIZE_WITH_ANALYSIS",
                "command": (
                    f"vibe skill-assay finalize --assay {assay_id} "
                    "--analysis-file <analysis.json> --json"
                ),
                "mutation": True,
                "reason": "Submit doc-backed hypotheses referencing evidence facts",
            }
        ],
    }
    write_evidence(repo_root, assay_id, evidence)
    return {
        **evidence,
        "dry_run": False,
        "receipt_relative": f"runtime/vibe-skill-assay/{assay_id}",
    }
