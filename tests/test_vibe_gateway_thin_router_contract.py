"""Vibe Gateway thin-router contract — delegates to Engine; no second readiness engine."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from vibe_control.cli import main
from vibe_control.gateway import (
    FORBIDDEN_INTENTS,
    ROUTE_TABLE,
    normalize_intent,
    route_gateway,
)

GATEWAY = "roadmap.vibe_gateway_thin_router_contract"
DESCRIBE = "roadmap.vibe_describe_control_surface"
RECOVERY = "roadmap.vibe_operation_recovery_design"
CONCEPT = "roadmap.vibe_product_concept_boundary_contract"
CAP_RUNTIME = "roadmap.vibe_capability_profile_runtime"
CAP_INSTALL = "roadmap.vibe_capability_profile_install_init_guidance"
CAP_DOCTOR = "roadmap.vibe_capability_profile_doctor_gateway_guidance"
FORBIDDEN_SECRET_PATTERNS = (
    r"notebooklm://",
    r"Authorization:",
    r"Bearer\s+",
    r"cookie=",
    r"Cookie:",
    r"provider_source_id\s*[:=]",
)


def _assert_no_secrets(blob: str) -> None:
    for pattern in FORBIDDEN_SECRET_PATTERNS:
        assert re.search(pattern, blob, flags=re.IGNORECASE) is None, pattern
    assert "provider_task_id\": \"vibe-control-" not in blob
    assert "\"notebook_ref\"" not in blob


def _engine_envelope(
    *,
    command: str,
    data: dict[str, Any],
    mutation: bool = False,
    next_actions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "ok": True,
        "command": command,
        "mutation": mutation,
        "mode": "readonly_test",
        "data": data,
        "warnings": [],
        "next_actions": list(next_actions or []),
    }


def _progress_payload(**overrides: Any) -> dict[str, Any]:
    base = {
        "schema_version": "vibe.progress.v1",
        "mutation": False,
        "product_ready": True,
        "task_cache_current": True,
        "provider_sync_required": False,
        "provider_ask_clean": True,
        "closeout_complete": True,
        "implementation_ready": True,
        "next_actionable_task": GATEWAY,
        "no_actionable_next_task": False,
        "blocked_reasons": [],
        "safe_next_action": {
            "code": "IMPLEMENTATION_PROMPT",
            "command": f"vibe implementation prompt --task {GATEWAY} --json",
            "mutation": False,
            "reason": "test",
        },
    }
    base.update(overrides)
    return base


def test_normalize_intent_aliases():
    assert normalize_intent("status") == "status"
    assert normalize_intent("readiness") == "status"
    assert normalize_intent("what_next") == "what_next"
    assert normalize_intent("next") == "what_next"
    assert normalize_intent("get_prompt") == "get_prompt"
    assert normalize_intent("prompt") == "get_prompt"
    assert normalize_intent("why_blocked") == "why_blocked"
    assert normalize_intent("summary") == "summary"
    assert normalize_intent("brief") == "brief"
    assert normalize_intent("prepare_closeout") == "prepare_closeout"
    assert normalize_intent("verify_after_work") == "verify_after_work"


def test_route_table_points_only_at_engine_surfaces():
    for route, meta in ROUTE_TABLE.items():
        assert meta["engine_command"].startswith("vibe ")
        assert "--apply" not in meta["engine_command"]
        assert " bd " not in f" {meta['engine_command']} "
        # Ordinary Gateway routes are readonly. grill_brief may open a local
        # self-grill session (local_runtime_write) — never provider apply.
        if route == "grill_brief":
            assert meta["mutation"] is True
        else:
            assert meta["mutation"] is False
        assert meta["engine_surface"]
        assert route not in FORBIDDEN_INTENTS


def test_status_delegates_to_progress_surface(tmp_path: Path):
    calls: list[str] = []

    def progress_fn(**_kwargs: Any) -> dict[str, Any]:
        calls.append("progress")
        return _engine_envelope(
            command="vibe progress",
            data=_progress_payload(product_ready=True),
            next_actions=[
                {
                    "code": "IMPLEMENTATION_PROMPT",
                    "command": f"vibe implementation prompt --task {GATEWAY} --json",
                    "mutation": False,
                    "reason": "test",
                }
            ],
        )

    result = route_gateway(
        intent="status",
        repo_root=tmp_path,
        delegates={"progress": progress_fn},
    )
    assert result["ok"] is True
    assert result["mutation"] is False
    data = result["data"]
    assert data["route"] == "status"
    assert data["engine_surface"] == "progress"
    assert data["engine_command"] == "vibe progress --json"
    assert data["source_of_truth"] == "engine"
    assert data["facts_embedded"] is False
    assert data["engine_payload"]["command"] == "vibe progress"
    assert data["engine_payload"]["data"]["product_ready"] is True
    assert calls == ["progress"]


def test_what_next_delegates_to_implementation_next(tmp_path: Path):
    def next_fn(**_kwargs: Any) -> dict[str, Any]:
        return _engine_envelope(
            command="vibe implementation next",
            data={
                "next_actionable_task": GATEWAY,
                "no_actionable_next_task": False,
                "do_not_invent_phase13": True,
            },
        )

    result = route_gateway(intent="what_next", repo_root=tmp_path, delegates={"next": next_fn})
    data = result["data"]
    assert data["route"] == "what_next"
    assert data["engine_surface"] == "implementation.next"
    assert data["engine_command"] == "vibe implementation next --json"
    assert data["engine_payload"]["data"]["next_actionable_task"] == GATEWAY


def test_get_prompt_delegates_to_implementation_prompt(tmp_path: Path):
    seen: dict[str, str] = {}

    def prompt_fn(*, task_selector: str, **_kwargs: Any) -> dict[str, Any]:
        seen["task"] = task_selector
        return _engine_envelope(
            command="vibe implementation prompt",
            data={
                "task_completed": False,
                "do_not_restart": False,
                "implementation_ready": True,
                "prompt": f"Implement: {task_selector}",
                "task_context": {"provider_task_id_is_identity": False},
            },
        )

    result = route_gateway(
        intent="get_prompt",
        repo_root=tmp_path,
        task=GATEWAY,
        delegates={"prompt": prompt_fn},
    )
    data = result["data"]
    assert data["engine_surface"] == "implementation.prompt"
    assert "implementation prompt" in data["engine_command"]
    assert GATEWAY in data["engine_command"]
    assert seen["task"] == GATEWAY
    assert "Implement:" in data["engine_payload"]["data"]["prompt"]


def test_summary_and_brief_delegate(tmp_path: Path):
    def progress_fn(**_kwargs: Any) -> dict[str, Any]:
        return _engine_envelope(command="vibe progress", data=_progress_payload())

    def brief_fn(**_kwargs: Any) -> dict[str, Any]:
        return _engine_envelope(
            command="vibe brief",
            data={
                "brief_version": "vibe.brief.v1",
                "summary": "Do Gateway next",
                "task": {"ssot_anchor": GATEWAY, "actionable": True},
            },
        )

    summary = route_gateway(
        intent="summary", repo_root=tmp_path, delegates={"progress": progress_fn}
    )
    brief = route_gateway(intent="brief", repo_root=tmp_path, delegates={"brief": brief_fn})
    assert summary["data"]["engine_surface"] == "progress"
    assert brief["data"]["engine_surface"] == "brief"
    assert brief["data"]["engine_payload"]["data"]["summary"] == "Do Gateway next"


def test_gateway_does_not_recompute_product_ready_or_task_cache(tmp_path: Path):
    def progress_fn(**_kwargs: Any) -> dict[str, Any]:
        return _engine_envelope(
            command="vibe progress",
            data=_progress_payload(
                product_ready=False,
                task_cache_current=False,
                blocked_reasons=["task_cache_not_current"],
            ),
        )

    result = route_gateway(
        intent="status", repo_root=tmp_path, delegates={"progress": progress_fn}
    )
    payload = result["data"]["engine_payload"]["data"]
    assert payload["product_ready"] is False
    assert payload["task_cache_current"] is False
    # Gateway must not invent flipped readiness.
    assert result["data"].get("product_ready") is None
    assert result["data"].get("task_cache_current") is None


def test_gateway_does_not_hardcode_roadmap_facts():
    src = Path("src/vibe_control/gateway.py").read_text(encoding="utf-8")
    assert "roadmap.vibe_gateway_thin_router_contract" not in src
    assert "roadmap.phase13" not in src
    assert "next_actionable_task =" not in src


def test_gateway_does_not_derive_identity_from_provider_task_id(tmp_path: Path):
    def prompt_fn(*, task_selector: str, **_kwargs: Any) -> dict[str, Any]:
        return _engine_envelope(
            command="vibe implementation prompt",
            data={
                "prompt": "Implement: x",
                "task_context": {
                    "provider_task_id": "vibe-control-abc",
                    "provider_task_id_is_identity": False,
                    "managed_key": "sha256:deadbeef",
                },
            },
        )

    result = route_gateway(
        intent="get_prompt",
        repo_root=tmp_path,
        task="sha256:deadbeef",
        delegates={"prompt": prompt_fn},
    )
    ctx = result["data"]["engine_payload"]["data"]["task_context"]
    assert ctx["provider_task_id_is_identity"] is False
    # Gateway must not promote provider id to route identity fields.
    assert result["data"].get("ssot_anchor") is None
    assert result["data"].get("task_identity") is None


def test_default_routes_mutation_false(tmp_path: Path):
    def progress_fn(**_kwargs: Any) -> dict[str, Any]:
        return _engine_envelope(command="vibe progress", data=_progress_payload())

    for intent in ("status", "summary", "why_blocked"):
        result = route_gateway(
            intent=intent, repo_root=tmp_path, delegates={"progress": progress_fn}
        )
        assert result["mutation"] is False
        assert result["data"]["mutation"] is False


def test_refuse_raw_provider_and_mutation_intents(tmp_path: Path):
    for intent in (
        "closeout_apply",
        "task_apply",
        "cache_reset_apply",
        "raw_bd",
        "raw_provider",
        "notebooklm_apply",
        "knowledge_sync_apply",
    ):
        result = route_gateway(intent=intent, repo_root=tmp_path)
        assert result["ok"] is False
        assert result.get("mutation") is not True
        err = result["error"]
        assert err["code"] == "GATEWAY_ROUTE_REFUSED"
        blob = json.dumps(result, ensure_ascii=False)
        assert "ChatGPT Project Sources were updated" not in blob
        assert "bd " not in blob.lower() or "raw bd" in (err.get("message") or "").lower()


def test_prepare_closeout_and_verify_are_dry_run_only(tmp_path: Path):
    seen: list[bool] = []

    def closeout_fn(*, apply: bool = False, **_kwargs: Any) -> dict[str, Any]:
        seen.append(apply)
        return _engine_envelope(
            command="vibe closeout run",
            data={"closeout_complete": True, "mutation": False},
            mutation=False,
        )

    for intent in ("prepare_closeout", "verify_after_work"):
        result = route_gateway(
            intent=intent, repo_root=tmp_path, delegates={"closeout": closeout_fn}
        )
        assert result["ok"] is True
        assert result["data"]["engine_command"] == "vibe closeout run --dry-run --json"
        assert "--apply" not in result["data"]["engine_command"]
        assert result["mutation"] is False
    assert seen == [False, False]


def test_gateway_output_includes_engine_evidence_and_safe_next(tmp_path: Path):
    def progress_fn(**_kwargs: Any) -> dict[str, Any]:
        return _engine_envelope(
            command="vibe progress",
            data=_progress_payload(),
            next_actions=[
                {
                    "code": "IMPLEMENTATION_PROMPT",
                    "command": f"vibe implementation prompt --task {GATEWAY} --json",
                    "mutation": False,
                    "reason": "test",
                }
            ],
        )

    result = route_gateway(
        intent="status", repo_root=tmp_path, delegates={"progress": progress_fn}
    )
    data = result["data"]
    assert "engine_payload" in data
    assert data["safe_next"]["code"] == "IMPLEMENTATION_PROMPT"
    assert result["next_actions"]


def test_preserves_completed_do_not_restart_from_prompt(tmp_path: Path):
    def prompt_fn(*, task_selector: str, **_kwargs: Any) -> dict[str, Any]:
        return _engine_envelope(
            command="vibe implementation prompt",
            data={
                "task_completed": True,
                "do_not_restart": True,
                "prompt": "WARNING: selected task is completed — do not restart",
            },
        )

    result = route_gateway(
        intent="get_prompt",
        repo_root=tmp_path,
        task="roadmap.vibe_progress_brief_baseline",
        delegates={"prompt": prompt_fn},
    )
    pdata = result["data"]["engine_payload"]["data"]
    assert pdata["task_completed"] is True
    assert pdata["do_not_restart"] is True
    assert "Implement:" not in pdata["prompt"]


def test_redaction_and_advisor_boundary(tmp_path: Path):
    def progress_fn(**_kwargs: Any) -> dict[str, Any]:
        return _engine_envelope(
            command="vibe progress",
            data=_progress_payload(),
        )

    result = route_gateway(
        intent="status", repo_root=tmp_path, delegates={"progress": progress_fn}
    )
    blob = json.dumps(result, ensure_ascii=False)
    _assert_no_secrets(blob)
    assert result["data"]["source_of_truth"] == "engine"
    assert "ChatGPT Project Sources were updated" not in blob
    # Advisor copies are not product closeout gates.
    assert result["data"].get("chatgpt_project_sources_required") is not True


def test_unknown_intent_fail_closed(tmp_path: Path):
    result = route_gateway(intent="invent_phase13", repo_root=tmp_path)
    assert result["ok"] is False
    assert result["error"]["code"] == "GATEWAY_UNKNOWN_INTENT"


def test_gateway_cli_status_ok_mutation_false(monkeypatch, capsys):
    monkeypatch.chdir(Path.cwd())
    code = main(["gateway", "--intent", "status", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["ok"] is True
    assert payload.get("mutation") is False
    assert payload["command"] == "vibe gateway"
    data = payload["data"]
    assert data["gateway"] is True
    assert data["route"] == "status"
    assert data["engine_surface"] == "progress"
    assert data["source_of_truth"] == "engine"
    assert data["facts_embedded"] is False
    assert "engine_payload" in data
    blob = json.dumps(payload, ensure_ascii=False)
    _assert_no_secrets(blob)


def test_gateway_cli_what_next_and_brief(monkeypatch, capsys):
    monkeypatch.chdir(Path.cwd())
    code = main(["gateway", "--intent", "what_next", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["data"]["engine_surface"] == "implementation.next"
    assert payload["data"]["engine_payload"]["data"]["next_actionable_task"] is None

    code = main(["gateway", "--intent", "brief", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["data"]["engine_surface"] == "brief"
    assert payload.get("mutation") is False


def test_gateway_cli_refuses_closeout_apply_intent(monkeypatch, capsys):
    monkeypatch.chdir(Path.cwd())
    code = main(["gateway", "--intent", "closeout_apply", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["ok"] is False
    assert payload["error"]["code"] == "GATEWAY_ROUTE_REFUSED"


def test_gateway_cli_get_prompt_for_completed_gateway_do_not_restart(monkeypatch, capsys):
    monkeypatch.chdir(Path.cwd())
    code = main(["gateway", "--intent", "get_prompt", "--task", GATEWAY, "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["data"]["engine_surface"] == "implementation.prompt"
    pdata = payload["data"]["engine_payload"]["data"]
    assert pdata.get("task_completed") is True
    assert pdata.get("do_not_restart") is True
    assert "Implement:" not in (pdata.get("prompt") or "")


def test_gateway_mirrors_engine_failure_ok(tmp_path: Path):
    def prompt_fn(*, task_selector: str, **_kwargs: Any) -> dict[str, Any]:
        return {
            "ok": False,
            "command": "vibe implementation prompt",
            "mutation": False,
            "error": {"code": "NOT_READY", "message": "blocked"},
            "data": {"implementation_ready": False},
            "warnings": [],
            "next_actions": [],
        }

    result = route_gateway(
        intent="get_prompt",
        repo_root=tmp_path,
        task=GATEWAY,
        delegates={"prompt": prompt_fn},
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "GATEWAY_ENGINE_FAILED"
    assert result["mutation"] is False
    assert result["data"]["engine_payload"]["ok"] is False


def test_why_blocked_pass_through_engine_blocked_reasons(tmp_path: Path):
    def progress_fn(**_kwargs: Any) -> dict[str, Any]:
        return _engine_envelope(
            command="vibe progress",
            data=_progress_payload(
                product_ready=False,
                blocked_reasons=["provider_sync_required", "task_cache_not_current"],
            ),
        )

    result = route_gateway(
        intent="why_blocked", repo_root=tmp_path, delegates={"progress": progress_fn}
    )
    assert result["ok"] is True
    assert result["data"]["route"] == "why_blocked"
    assert result["data"]["blocked_reasons"] == [
        "provider_sync_required",
        "task_cache_not_current",
    ]
    assert result["data"]["blocked_reasons_source"] == "engine_payload.data.blocked_reasons"
    # Must match Engine payload, not Gateway recomputation.
    assert (
        result["data"]["blocked_reasons"]
        == result["data"]["engine_payload"]["data"]["blocked_reasons"]
    )


def test_doctor_is_not_a_gateway_alias():
    assert normalize_intent("doctor") is None


def test_progress_brief_still_report_capability_runtime_next(monkeypatch, capsys):
    monkeypatch.chdir(Path.cwd())
    code = main(["progress", "--json"])
    progress = json.loads(capsys.readouterr().out)
    assert code == 0
    assert progress["data"]["next_actionable_task"] is None

    code = main(["brief", "--json"])
    brief = json.loads(capsys.readouterr().out)
    assert code == 0
    assert brief["data"].get("task") is None or brief["data"]["next_actionable_task"] is None
    # Dirty working tree fail-closes implementation_ready; projection must still match Progress.
    assert brief["data"]["implementation_ready"] == progress["data"]["implementation_ready"]
    assert brief["data"]["next_actionable_task"] is None
    assert isinstance(brief["data"].get("summary"), str) and brief["data"]["summary"]


def test_skill_documents_gateway_thin_router():
    text = Path("src/vibe_control/skills/vibe-control/SKILL.md").read_text(encoding="utf-8")
    assert "vibe gateway" in text
    assert "thin" in text.lower()
    assert "Engine" in text or "engine" in text
    assert "closeout run --apply" in text
    assert "Never call `bd` directly" in text or "Never call bd directly" in text
