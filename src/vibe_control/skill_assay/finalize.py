"""Finalize Skill Assay analysis into a report."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vibe_control.skill_assay.agent_packet import build_agent_packet, write_agent_packet
from vibe_control.skill_assay.constants import SCHEMA_ANALYSIS, SCHEMA_REPORT
from vibe_control.skill_assay.errors import SkillAssayError
from vibe_control.skill_assay.owner_html import render_owner_report_html, write_owner_report_html
from vibe_control.skill_assay.storage import (
    assay_dir,
    load_evidence,
    write_analysis,
    write_owner_report_markdown,
    write_report,
)

_ALLOWED_VERDICTS = frozenset({"pass", "partial", "fail", "unknown"})
_RUNS_ASSISTANT = re.compile(r"^runs/(\d+)\.assistant_text$")
_RUNS_JSON = re.compile(r"^runs/(\d+)(?:\.json)?(?:\.(.+))?$")


def _lookup_path(data: Any, path: str) -> Any:
    cur: Any = data
    for part in path.split("."):
        if cur is None:
            return None
        indexed = re.fullmatch(r"(\w+)\[(\d+)\]", part)
        if indexed:
            key, idx_s = indexed.group(1), indexed.group(2)
            if not isinstance(cur, dict) or key not in cur:
                return None
            cur = cur[key]
            if not isinstance(cur, list):
                return None
            idx = int(idx_s)
            if idx < 0 or idx >= len(cur):
                return None
            cur = cur[idx]
            continue
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
            continue
        if isinstance(cur, list) and part.isdigit():
            idx = int(part)
            if idx < 0 or idx >= len(cur):
                return None
            cur = cur[idx]
            continue
        return None
    return cur


def resolve_evidence_ref(
    *,
    repo_root: Path,
    assay_id: str,
    evidence: dict[str, Any],
    ref: str,
) -> dict[str, Any]:
    token = str(ref or "").strip()
    if not token:
        raise SkillAssayError(
            "SKILL_ASSAY_ANALYSIS_EVIDENCE_REF_INVALID",
            "evidence_refs entry must be a non-empty string",
        )

    root = assay_dir(repo_root, assay_id)
    assistant_match = _RUNS_ASSISTANT.fullmatch(token)
    if assistant_match:
        path = root / "runs" / f"{assistant_match.group(1)}.assistant_text"
        if not path.is_file():
            raise SkillAssayError(
                "SKILL_ASSAY_ANALYSIS_EVIDENCE_REF_INVALID",
                f"evidence ref not found: {token}",
                {"ref": token},
            )
        return {"kind": "file", "ref": token, "path": path.as_posix()}

    runs_match = _RUNS_JSON.fullmatch(token)
    if runs_match:
        run_index = runs_match.group(1)
        suffix = runs_match.group(2)
        path = root / "runs" / f"{run_index}.json"
        if not path.is_file():
            raise SkillAssayError(
                "SKILL_ASSAY_ANALYSIS_EVIDENCE_REF_INVALID",
                f"evidence ref not found: {token}",
                {"ref": token},
            )
        if not suffix:
            return {"kind": "file", "ref": token, "path": path.as_posix()}
        payload = json.loads(path.read_text(encoding="utf-8"))
        value = _lookup_path(payload, suffix)
        if value is None:
            raise SkillAssayError(
                "SKILL_ASSAY_ANALYSIS_EVIDENCE_REF_INVALID",
                f"evidence ref path missing: {token}",
                {"ref": token},
            )
        return {"kind": "trace_field", "ref": token, "value_type": type(value).__name__}

    # Dotted / indexed paths into evidence.json (facts[0], stability.stable_fields, …)
    value = _lookup_path(evidence, token)
    if value is None:
        raise SkillAssayError(
            "SKILL_ASSAY_ANALYSIS_EVIDENCE_REF_INVALID",
            f"evidence ref path missing: {token}",
            {"ref": token},
        )
    return {"kind": "evidence_field", "ref": token, "value_type": type(value).__name__}


def render_owner_report_markdown(report: dict[str, Any], *, repo_root: Path) -> str:
    """Plain-language markdown for humans (not the JSON receipt)."""
    assay_id = str(report.get("assay_id") or "")
    host = str(report.get("host_id") or "unknown")
    checks = dict(report.get("checks_summary") or {})
    pass_rate = checks.get("pass_rate")
    root = assay_dir(repo_root, assay_id)
    lines = [
        f"# Skill Assay 报告 — {host}",
        "",
        f"- 测试编号：`{assay_id}`",
        f"- 宿主：`{host}`",
        f"- 规则检查通过率：`{pass_rate}`",
        f"- 本地目录：`{root.as_posix()}`",
        "",
        "## 结论（人话）",
        "",
    ]
    hyps = list(report.get("hypotheses") or [])
    if not hyps:
        lines.append("- （无结论条目）")
    for hyp in hyps:
        if not isinstance(hyp, dict):
            continue
        verdict = str(hyp.get("verdict") or "unknown")
        claim = str(hyp.get("claim") or "").strip()
        lines.append(f"- **{verdict}**：{claim}")
    lines.extend(["", "## 已确认的事实", ""])
    for fact in list(report.get("facts") or []):
        lines.append(f"- {fact}")
    lines.extend(["", "## 还不知道的事", ""])
    for unk in list(report.get("unknowns") or []):
        lines.append(f"- {unk}")
    lines.extend(["", "## 回复摘录", ""])
    for excerpt in list(report.get("run_excerpts") or []):
        if not isinstance(excerpt, dict):
            continue
        lines.append(
            f"### 第 {excerpt.get('run_index')} 轮（模型：{excerpt.get('model_resolved')}）"
        )
        lines.append("")
        lines.append("```text")
        lines.append(str(excerpt.get("excerpt") or "").rstrip())
        lines.append("```")
        lines.append("")
    lines.extend(
        [
            "## 怎么打开这些文件",
            "",
            "在 Finder 中打开下面目录，或把路径贴到 Cursor 的文件打开框：",
            "",
            f"`{root.as_posix()}`",
            "",
            "重点文件：",
            "",
            "- `OWNER_REPORT.html`：给人看的报告（优先打开这个）",
            "- `OWNER_REPORT.md`：给人看的 Markdown 副本",
            "- `AGENT_PACKET.json`：给 coding agent / skill 维护者的一页交接材料",
            "- `report.json`：机器可读报告",
            "- `evidence.json`：原始证据汇总",
            "- `runs/0.assistant_text`：第 1 轮完整回复（1、2 同理）",
            "",
            "打包分享：`vibe skill-assay pack --assay <id> --json`",
            "",
        ]
    )
    return "\n".join(lines)


def finalize_assay(
    *,
    repo_root: Path,
    assay_id: str,
    analysis_path: Path,
) -> dict[str, Any]:
    evidence = load_evidence(repo_root, assay_id)
    raw = json.loads(Path(analysis_path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SkillAssayError(
            "SKILL_ASSAY_ANALYSIS_INVALID",
            "analysis file must be a JSON object",
        )
    schema = str(raw.get("schema") or "")
    if schema and schema != SCHEMA_ANALYSIS:
        raise SkillAssayError(
            "SKILL_ASSAY_ANALYSIS_SCHEMA_INVALID",
            f"analysis schema must be {SCHEMA_ANALYSIS}",
            {"schema": schema},
        )
    hypotheses = raw.get("hypotheses") or []
    if not isinstance(hypotheses, list):
        raise SkillAssayError(
            "SKILL_ASSAY_ANALYSIS_INVALID",
            "hypotheses must be a list",
        )
    for index, hyp in enumerate(hypotheses):
        if not isinstance(hyp, dict):
            raise SkillAssayError(
                "SKILL_ASSAY_ANALYSIS_INVALID",
                f"hypotheses[{index}] must be an object",
            )
        claim = str(hyp.get("claim") or "").strip()
        if not claim:
            raise SkillAssayError(
                "SKILL_ASSAY_ANALYSIS_INVALID",
                "each hypothesis must include claim",
                {"hypothesis_index": index},
            )
        verdict = str(hyp.get("verdict") or "unknown").strip()
        if verdict not in _ALLOWED_VERDICTS:
            raise SkillAssayError(
                "SKILL_ASSAY_ANALYSIS_VERDICT_INVALID",
                "hypothesis verdict must be pass|partial|fail|unknown",
                {"hypothesis_index": index, "verdict": verdict},
            )
        hyp["verdict"] = verdict
        refs = hyp.get("evidence_refs") or []
        if not isinstance(refs, list) or not refs:
            raise SkillAssayError(
                "SKILL_ASSAY_ANALYSIS_EVIDENCE_REF_REQUIRED",
                "each hypothesis must cite at least one evidence_refs entry",
                {"hypothesis_index": index},
            )
        for r_index, ref in enumerate(refs):
            if not isinstance(ref, str):
                raise SkillAssayError(
                    "SKILL_ASSAY_ANALYSIS_EVIDENCE_REF_INVALID",
                    "evidence_refs entries must be strings",
                    {"hypothesis_index": index, "ref_index": r_index},
                )
            resolve_evidence_ref(
                repo_root=repo_root,
                assay_id=assay_id,
                evidence=evidence,
                ref=ref,
            )
        citations = hyp.get("doc_citations") or []
        if not isinstance(citations, list) or not citations:
            raise SkillAssayError(
                "SKILL_ASSAY_ANALYSIS_DOC_CITATION_REQUIRED",
                "each hypothesis must include doc_citations",
                {"hypothesis_index": index},
            )
        for c_index, citation in enumerate(citations):
            if not isinstance(citation, dict):
                raise SkillAssayError(
                    "SKILL_ASSAY_ANALYSIS_INVALID",
                    f"doc_citations[{c_index}] must be an object",
                )
            for key in ("source", "ref", "fetch_date"):
                if not str(citation.get(key) or "").strip():
                    raise SkillAssayError(
                        "SKILL_ASSAY_ANALYSIS_DOC_CITATION_INCOMPLETE",
                        f"doc citation missing {key}",
                        {"hypothesis_index": index, "citation_index": c_index},
                    )

    analysis = {
        "schema": SCHEMA_ANALYSIS,
        "assay_id": assay_id,
        "hypotheses": hypotheses,
        "unknowns": list(raw.get("unknowns") or []),
    }
    write_analysis(repo_root, assay_id, analysis)

    excerpts: list[dict[str, Any]] = []
    for summary in list(evidence.get("run_summaries") or [])[:3]:
        if not isinstance(summary, dict):
            continue
        ref = str(summary.get("assistant_text_ref") or "")
        text = ""
        if ref:
            path = assay_dir(repo_root, assay_id) / ref
            if path.is_file():
                text = path.read_text(encoding="utf-8", errors="replace")[:240]
        excerpts.append(
            {
                "run_index": summary.get("run_index"),
                "assistant_text_ref": ref,
                "excerpt": text,
                "model_resolved": summary.get("model_resolved"),
                "skill_invocation": summary.get("skill_invocation"),
            }
        )

    report = {
        "schema": SCHEMA_REPORT,
        "assay_id": assay_id,
        "host_id": evidence.get("host_id"),
        "baseline_host": evidence.get("baseline_host"),
        "causal_scope": evidence.get("causal_scope", "single_host"),
        "execution_profile": evidence.get("execution_profile", "response_only"),
        "facts": list(evidence.get("facts") or []),
        "stability": dict(evidence.get("stability") or {}),
        "checks_summary": dict(evidence.get("checks_summary") or {}),
        "run_excerpts": excerpts,
        "hypotheses": hypotheses,
        "unknowns": sorted(
            set(list(evidence.get("unknowns") or []) + list(analysis["unknowns"]))
        ),
        "finalized_at": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "honesty": {
            "black_box_stays_black": True,
            "docs_support_hypotheses_only": True,
            "single_host_not_cross_host_root_cause": evidence.get("causal_scope")
            == "single_host",
        },
    }
    write_report(repo_root, assay_id, report)
    owner_md = render_owner_report_markdown(report, repo_root=repo_root)
    owner_path = write_owner_report_markdown(repo_root, assay_id, owner_md)
    owner_html_path = write_owner_report_html(
        repo_root,
        assay_id,
        render_owner_report_html(report, repo_root=repo_root),
    )
    packet = build_agent_packet(report, repo_root=repo_root)
    packet_path = write_agent_packet(repo_root, assay_id, packet)
    report["owner_report_relative"] = owner_path.relative_to(Path(repo_root)).as_posix()
    report["owner_html_relative"] = owner_html_path.relative_to(Path(repo_root)).as_posix()
    report["agent_packet_relative"] = packet_path.relative_to(Path(repo_root)).as_posix()
    # Refresh JSON with owner path pointer.
    write_report(repo_root, assay_id, report)
    return report
