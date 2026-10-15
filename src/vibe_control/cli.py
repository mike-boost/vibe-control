"""vibe CLI — deterministic command surface for Vibe Control."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

from vibe_control import __version__
from vibe_control.config import (
    ConfigError,
    control_path,
    find_project_root,
    legacy_control_path,
    load_config,
    primary_control_path,
    template_path,
    validate_config,
)
from vibe_control.git_repo import is_git_repo
from vibe_control.json_envelope import (
    attach_operation_result,
    failure_envelope,
    success_envelope,
)
from vibe_control.knowledge.corpus import CorpusError, build_desired_corpus
from vibe_control.knowledge.notebooklm_provider import NotebookLMProvider
from vibe_control.knowledge.repo_provider import RepoProvider
from vibe_control.task.beads_provider import BeadsProvider


CommandHandler = Callable[[argparse.Namespace], dict[str, Any]]


def _emit(envelope: dict[str, Any], *, as_json: bool) -> int:
    text_out = envelope.get("_emit_text")
    if text_out is not None and not as_json:
        sys.stdout.write(str(text_out))
        if not str(text_out).endswith("\n"):
            sys.stdout.write("\n")
        return 0 if envelope.get("ok") else 1
    if as_json:
        # Keep internal emit helpers out of JSON contract.
        public = {k: v for k, v in envelope.items() if not str(k).startswith("_")}
        json.dump(public, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
    else:
        if envelope.get("ok"):
            data = envelope.get("data")
            print(json.dumps(data, indent=2, ensure_ascii=False))
            for warning in envelope.get("warnings") or []:
                if isinstance(warning, dict):
                    print(
                        f"warning [{warning.get('code')}]: {warning.get('message')}",
                        file=sys.stderr,
                    )
                else:
                    print(f"warning: {warning}", file=sys.stderr)
        else:
            err = envelope.get("error") or {}
            print(f"error [{err.get('code')}]: {err.get('message')}", file=sys.stderr)
            for action in envelope.get("next_actions") or []:
                print(f"next: {action}", file=sys.stderr)
    return 0 if envelope.get("ok") else 1


def format_doctor_text(envelope: dict[str, Any]) -> str:
    """Concise human summary for `vibe doctor` (non --json)."""
    data = envelope.get("data") or {}
    profile = data.get("capability_profile") or {}
    comps = data.get("components") or {}
    nlm = data.get("notebooklm") or {}
    beads = data.get("beads") or {}
    skills = data.get("skills") or {}
    lines = [
        f"vibe doctor  ({'ok' if envelope.get('ok') else 'NOT OK'})",
        f"  project:     {envelope.get('project_id') or '(none)'}",
        f"  config_ok:   {data.get('config_ok')}",
        f"  profile:     default_disabled={profile.get('default_disabled')}",
        f"  knowledge:   enabled={bool((comps.get('knowledge') or {}).get('enabled'))} "
        f"available={bool((comps.get('knowledge') or {}).get('available'))}",
        f"  task:        enabled={bool((comps.get('task') or {}).get('enabled'))} "
        f"available={bool((comps.get('task') or {}).get('available'))}",
        f"  notebooklm:  installed={nlm.get('installed')} auth={nlm.get('auth_state')}",
        f"  beads:       installed={beads.get('installed')}",
        f"  skills:      condition={skills.get('condition') or 'unknown'} "
        f"installed={skills.get('installed')}",
        f"  mutation:    {data.get('mutation')}",
    ]
    blocked = data.get("component_blocked_reasons") or []
    if blocked:
        lines.append(f"  blocked:     {', '.join(str(x) for x in blocked)}")
    warnings = envelope.get("warnings") or []
    for w in warnings[:5]:
        lines.append(f"  warning:     {w}")
    lines.append("  tip:         vibe doctor --json  # full machine-readable report")
    lines.append("  tip:         enable only knowledge/task when providers are ready")
    return "\n".join(lines) + "\n"


def _repo_root() -> Path:
    return find_project_root()


def _load_config(args: argparse.Namespace | None = None):
    config_path = getattr(args, "config", None) if args is not None else None
    return load_config(_repo_root(), config_path=config_path)


def _capability_disabled_envelope(
    component_id: str,
    command: str,
    args: argparse.Namespace | None = None,
) -> dict[str, Any] | None:
    """If capability is disabled, return a readonly skip envelope; else None.

    Missing/invalid control.yaml is not capability-disabled — callers must
    surface CONFIG_* errors instead of a silent skip.
    """
    from vibe_control.components import (
        capability_enabled,
        resolve_components_from_repo,
    )
    from vibe_control.json_envelope import next_action

    config_path = getattr(args, "config", None) if args is not None else None
    try:
        _load_config(args)
    except ConfigError:
        return None
    runtime = resolve_components_from_repo(_repo_root(), config_path=config_path)
    comps = runtime.get("components") or {}
    if capability_enabled(comps, component_id):
        return None
    enable_code = (
        "ENABLE_KNOWLEDGE_CONFIG_PREVIEW"
        if component_id == "knowledge"
        else "ENABLE_TASK_CONFIG_PREVIEW"
    )
    return attach_operation_result(
        success_envelope(
            command=command,
            project_id=_project_id_or_none(),
            mode="readonly",
            data={
                "capability_disabled": True,
                "component_id": component_id,
                "skipped": True,
                "mutation": False,
                "message": (
                    f"components.{component_id}.enabled is false. "
                    "Enable it in .config/vibe-control.yaml only when the provider is ready, "
                    "then re-run this command."
                ),
            },
            warnings=[],
            next_actions=[
                next_action(
                    code=enable_code,
                    command="vibe doctor --json",
                    mutation=False,
                    reason=(
                        f"Review enable preview for {component_id}; "
                        "do not auto-enable; edit control.yaml explicitly."
                    ),
                ),
            ],
        ),
        mutation_intent=False,
        effects=[],
    )


def cmd_doctor(args: argparse.Namespace) -> dict[str, Any]:
    envelope = _build_doctor_envelope(args)
    envelope["_emit_text"] = format_doctor_text(envelope)
    return envelope


def _build_doctor_envelope(args: argparse.Namespace) -> dict[str, Any]:
    root = _repo_root()
    primary = primary_control_path(root)
    legacy = legacy_control_path(root)
    cfg_path = primary if primary.is_file() else legacy if legacy.is_file() else primary
    config_exists = primary.is_file() or legacy.is_file()
    project_id: str | None = None
    registry_found = False
    registry_path: str | None = None
    warnings: list[str] = []

    if config_exists:
        try:
            config = _load_config(args)
            project_id = config.project_id
            cfg_path = config.path
            registry_rel = config.specs.get("registry")
            if registry_rel:
                reg = root / str(registry_rel)
                registry_path = reg.as_posix()
                registry_found = reg.is_file()
                if not registry_found:
                    warnings.append(f"spec registry not found: {registry_path}")
        except ConfigError as exc:
            warnings.append(f"config load issue: {exc.message}")

    nlm = NotebookLMProvider().status()
    beads = BeadsProvider().status()

    from vibe_control.components import (
        build_component_adoption_detection,
        build_component_config_guidance,
        build_component_provider_boundaries,
        resolve_components_from_repo,
    )
    from vibe_control.skills_manager import skills_readiness

    component_runtime = resolve_components_from_repo(
        root, config_path=getattr(args, "config", None)
    )
    config_ok = bool(component_runtime.get("config_ok"))
    component_blocked_reasons = list(component_runtime.get("blocked_reasons") or [])
    guidance = build_component_config_guidance()
    adoption = build_component_adoption_detection()
    boundaries = build_component_provider_boundaries()
    skills = skills_readiness()
    if skills.get("warnings"):
        warnings.extend(list(skills["warnings"]))
    if not config_ok:
        warnings.append(
            "component_config_invalid: config_ok=false "
            "(not provider unavailable; fix components.<id>.enabled)"
        )

    next_actions = list(guidance.get("next_actions") or []) if config_exists else [
        f"Create {primary.as_posix()} from template",
        f"Template: {template_path().as_posix()}",
        f"Legacy path still supported: {legacy.as_posix()}",
    ]
    for action in skills.get("next_actions") or []:
        if action not in next_actions:
            next_actions.append(action)

    return attach_operation_result(
        success_envelope(
            command="vibe doctor",
            project_id=project_id,
            data={
                "python_version": sys.version.split()[0],
                "cwd": Path.cwd().as_posix(),
                "repo_root": root.as_posix(),
                "control_yaml_exists": config_exists,
                "control_yaml_path": cfg_path.as_posix(),
                "primary_config_path": primary.as_posix(),
                "legacy_config_path": legacy.as_posix(),
                "git_repo_detected": is_git_repo(root),
                "spec_registry_path": registry_path,
                "spec_registry_found": registry_found,
                "config_ok": config_ok,
                "components": dict(component_runtime.get("components") or {}),
                "capability_profile": dict(component_runtime.get("capability_profile") or {}),
                "component_blocked_reasons": component_blocked_reasons,
                "component_config_example": guidance["component_config_example"],
                "component_config_example_yaml": guidance["component_config_example_yaml"],
                "component_config_guidance": guidance["component_config_guidance"],
                "profile_preview": dict(guidance.get("profile_preview") or {}),
                "capability_guidance": dict(guidance.get("capability_guidance") or {}),
                "enable_examples": list(guidance.get("enable_examples") or []),
                "invalid_examples": guidance["invalid_examples"],
                "component_adoption": adoption["component_adoption"],
                "adoption_performed": False,
                "provider_boundaries": boundaries["provider_boundaries"],
                "live_integration": False,
                "mutation_allowed": False,
                "requires_future_acceptance": True,
                "fail_closed": True,
                "readiness_effect": "none",
                "diagnostic_only": True,
                "mutation": False,
                "auto_enable": False,
                "install_adapt_uninstall": False,
                "notebooklm": nlm.to_dict(),
                "beads": beads.to_dict(),
                "skills": {
                    "installed": skills.get("installed"),
                    "condition": skills.get("condition"),
                    "missing": skills.get("missing"),
                    "mismatch": skills.get("mismatch"),
                    "install_root": skills.get("install_root"),
                },
            },
            warnings=warnings,
            next_actions=next_actions,
        ),
        mutation_intent=False,
        effects=[],
    )


def cmd_config_inspect(args: argparse.Namespace) -> dict[str, Any]:
    root = _repo_root()
    try:
        config = _load_config(args)
    except ConfigError as exc:
        return failure_envelope(
            command="vibe config inspect",
            code=exc.code,
            message=exc.message,
            details=exc.details,
            next_actions=[
                f"Create {control_path(root).as_posix()} from template",
                f"Template: {template_path().as_posix()}",
            ],
        )
    return success_envelope(
        command="vibe config inspect",
        project_id=config.project_id,
        data={
            "path": config.path.as_posix(),
            "config": config.to_dict(),
        },
    )


def cmd_config_validate(args: argparse.Namespace) -> dict[str, Any]:
    root = _repo_root()
    try:
        config = _load_config(args)
    except ConfigError as exc:
        return failure_envelope(
            command="vibe config validate",
            code=exc.code,
            message=exc.message,
            details=exc.details,
            next_actions=[
                f"Create {control_path(root).as_posix()} from template",
                f"Template: {template_path().as_posix()}",
            ],
        )

    errors = validate_config(config)
    if errors:
        return failure_envelope(
            command="vibe config validate",
            code="CONFIG_INVALID",
            message="Config validation failed",
            details={"errors": errors},
            project_id=config.project_id,
            next_actions=["Fix validation errors in .vibe/control.yaml"],
        )

    return success_envelope(
        command="vibe config validate",
        project_id=config.project_id,
        data={"valid": True, "path": config.path.as_posix()},
    )


def cmd_knowledge_inventory(args: argparse.Namespace) -> dict[str, Any]:
    skipped = _capability_disabled_envelope("knowledge", "vibe knowledge inventory", args)
    if skipped is not None:
        return skipped
    root = _repo_root()
    try:
        config = _load_config(args)
    except ConfigError as exc:
        return failure_envelope(
            command="vibe knowledge inventory",
            code=exc.code,
            message=exc.message,
            details=exc.details,
            next_actions=[
                f"Create {control_path(root).as_posix()} from template",
                f"Template: {template_path().as_posix()}",
            ],
        )

    try:
        from vibe_control.knowledge.corpus import resolve_desired_corpus
        from vibe_control.knowledge.notebooks import NotebookError, resolve_operation_alias

        notebook_alias = getattr(args, "notebook", None)
        if isinstance(config.knowledge.get("notebooks"), dict):
            notebook_alias = resolve_operation_alias(config, notebook_alias)
        corpus = resolve_desired_corpus(
            config, notebook_alias=notebook_alias, repo_root=root
        )
    except NotebookError as exc:
        return failure_envelope(
            command="vibe knowledge inventory",
            code=exc.code,
            message=exc.message,
            details=exc.details,
            project_id=config.project_id,
        )
    except CorpusError as exc:
        return failure_envelope(
            command="vibe knowledge inventory",
            code=exc.code,
            message=exc.message,
            details=exc.details,
            project_id=config.project_id,
            next_actions=[
                "Ensure specs.registry exists and is readable",
                "Or reduce include_extra / raise max_sources",
            ],
        )

    return success_envelope(
        command="vibe knowledge inventory",
        project_id=config.project_id,
        data=corpus.to_dict(),
        warnings=corpus.warnings,
    )


def cmd_knowledge_status(args: argparse.Namespace) -> dict[str, Any]:
    skipped = _capability_disabled_envelope("knowledge", "vibe knowledge status", args)
    if skipped is not None:
        return skipped
    from vibe_control.json_envelope import next_action

    root = _repo_root()
    project_id = None
    config = None
    registry_ok = False
    warnings: list[str] = []

    try:
        config = _load_config(args)
        project_id = config.project_id
        registry_rel = config.specs.get("registry")
        if registry_rel and (root / str(registry_rel)).is_file():
            registry_ok = True
        elif registry_rel:
            warnings.append(f"spec registry not found: {(root / str(registry_rel)).as_posix()}")
    except ConfigError as exc:
        warnings.append(exc.message)

    nlm = NotebookLMProvider().status()
    repo = RepoProvider().status(root)
    fallback_ready = bool(config is not None and registry_ok and repo.available)

    sync_data: dict[str, Any] = {
        "sync_state": "unavailable",
        "synced": False,
    }
    if config is not None:
        active = str(config.knowledge.get("provider") or "notebooklm").strip().lower()
        alias = getattr(args, "notebook", None)
        if active == "local_fts":
            from vibe_control.knowledge.local_fts.provider import LocalFtsProvider

            sync_data = LocalFtsProvider().status(
                config, repo_root=root, notebook_alias=alias
            )
            # NotebookLM binary is irrelevant for local_fts status green path.
            nlm = {
                "installed": False,
                "auth_state": "not_applicable",
                "message": "active knowledge.provider=local_fts; NotebookLM not required",
            }
        else:
            from vibe_control.knowledge.phase8_runtime import get_runtime

            runtime = get_runtime(repo_root=root)
            sync_data = runtime.status(config, alias=alias)

    sync_state = str(sync_data.get("sync_state") or "unavailable")
    sync_code = sync_data.get("code")
    next_actions: list[dict[str, Any]] = [
        next_action(
            code="INVENTORY",
            command="vibe knowledge inventory --json",
            mutation=False,
            reason="List selected SSOT files",
        ),
        next_action(
            code="QUERY",
            command="vibe knowledge query --question-file <file> --json",
            mutation=False,
            reason="Readonly query (repo fallback when not synced)",
        ),
    ]

    source_quota: dict[str, Any] | None = None
    scale: dict[str, Any] | None = None
    agent_surface: dict[str, Any] | None = None
    if config is not None:
        from vibe_control.knowledge.source_quota import assess_source_quota
        from vibe_control.knowledge.scale_observability import build_scale_observability
        from vibe_control.knowledge.provider_target import ProviderTarget
        from vibe_control.knowledge.receipt_scope import load_or_migrate_receipt

        desired_count = None
        try:
            from vibe_control.knowledge.corpus import build_desired_corpus

            corpus = build_desired_corpus(config, repo_root=root)
            desired_count = int(corpus.source_count)
            for w in corpus.warnings or []:
                if w not in warnings:
                    warnings.append(w)
        except Exception:
            desired_count = None
        remote_count = sync_data.get("remote_source_count")
        if remote_count is not None:
            remote_count = int(remote_count)
        source_quota = assess_source_quota(
            max_sources=config.knowledge.get("max_sources"),
            warn_sources=config.knowledge.get("warn_sources"),
            desired_count=desired_count,
            remote_source_count=remote_count,
            provider=str(config.knowledge.get("provider") or "notebooklm"),
        )
        for w in source_quota.get("warnings") or []:
            if w not in warnings:
                warnings.append(w)

        target_obj: ProviderTarget | None = None
        target_dict = sync_data.get("target")
        if isinstance(target_dict, dict) and target_dict.get("notebook_ref_hash"):
            target_obj = ProviderTarget(
                provider=str(target_dict.get("provider") or "notebooklm"),
                notebook_alias=str(target_dict.get("notebook_alias") or ""),
                notebook_ref_hash=str(target_dict.get("notebook_ref_hash") or ""),
                auth_profile_hash=target_dict.get("auth_profile_hash"),
            )
        receipt_item_count = None
        if project_id and target_obj is not None:
            receipt_result = load_or_migrate_receipt(str(project_id), target_obj)
            if receipt_result.ok and isinstance(receipt_result.data, dict):
                receipt_item_count = len(dict(receipt_result.data.get("items") or {}))
            elif receipt_result.ok and receipt_result.data is None:
                receipt_item_count = 0
        scale = build_scale_observability(
            project_id=str(project_id) if project_id else None,
            target=target_obj,
            desired_count=desired_count,
            receipt_item_count=receipt_item_count,
            required_updates_count=None,
            probe=sync_data.get("probe") if isinstance(sync_data.get("probe"), dict) else None,
        )
        from vibe_control.agent_surface import knowledge_sync_disclosure

        agent_surface = {
            "schema": "vibe.agent_surface.v1",
            "operations": [knowledge_sync_disclosure(continue_flag_available=True)],
            "mutation": False,
        }

    if sync_state == "receipt_missing" or sync_code == "RECEIPT_MISSING":
        next_actions.insert(
            0,
            next_action(
                code="RECEIPT_MISSING",
                command="vibe knowledge sync --dry-run --json",
                mutation=False,
                reason="Receipt missing; preview sync before any apply",
            ),
        )
    elif sync_state == "pending" or sync_code == "PENDING_SYNC_EXISTS":
        next_actions.insert(
            0,
            next_action(
                code="PENDING_SYNC_EXISTS",
                command="vibe knowledge retry --dry-run --json",
                mutation=False,
                reason="pending-sync present; preview retry before --apply",
            ),
        )
    elif sync_state == "drift":
        next_actions.insert(
            0,
            next_action(
                code="DRIFT_EXISTS",
                command="vibe knowledge sync --dry-run --json",
                mutation=False,
                reason="Drift detected; preview sync plan",
            ),
        )
    elif sync_state == "target_mismatch" or sync_code == "TARGET_MISMATCH":
        next_actions.insert(
            0,
            next_action(
                code="TARGET_MISMATCH",
                command="vibe knowledge doctor --json",
                mutation=False,
                reason="ProviderTarget mismatch; do not mutate wrong notebook",
            ),
        )
    elif not bool(sync_data.get("synced")):
        next_actions.insert(
            0,
            next_action(
                code="NOT_SYNCED",
                command="vibe knowledge doctor --json",
                mutation=False,
                reason="Not synced for resolved ProviderTarget",
            ),
        )

    return attach_operation_result(
        success_envelope(
            command="vibe knowledge status",
            project_id=project_id,
            mode="readonly",
            data={
                "sync_state": sync_data.get("sync_state"),
                "synced": bool(sync_data.get("synced")),
                "code": sync_data.get("code"),
                "reasons": sync_data.get("reasons") or [],
                "target": sync_data.get("target"),
                "probe": sync_data.get("probe"),
                "snapshot_hash": sync_data.get("snapshot_hash"),
                "ack_persistence": sync_data.get("ack_persistence"),
                "source_quota": source_quota,
                "scale": scale,
                "agent_surface": agent_surface,
                "notebooklm": nlm if isinstance(nlm, dict) else nlm.to_dict(),
                "fallback": {
                    **repo.to_dict(),
                    "ready": fallback_ready,
                    "config_loaded": config is not None,
                    "registry_found": registry_ok,
                },
            },
            warnings=warnings,
            next_actions=next_actions,
        ),
        mutation_intent=False,
        effects=[],
    )


def cmd_knowledge_query(args: argparse.Namespace) -> dict[str, Any]:
    skipped = _capability_disabled_envelope("knowledge", "vibe knowledge query", args)
    if skipped is not None:
        return skipped
    root = _repo_root()
    question_path = Path(args.question_file)

    try:
        config = _load_config(args)
    except ConfigError as exc:
        return failure_envelope(
            command="vibe knowledge query",
            code=exc.code,
            message=exc.message,
            details=exc.details,
            next_actions=[
                f"Create {control_path(root).as_posix()} from template",
                f"Template: {template_path().as_posix()}",
            ],
        )

    if not question_path.is_file():
        return failure_envelope(
            command="vibe knowledge query",
            code="QUESTION_FILE_NOT_FOUND",
            message=f"Question file not found: {question_path.as_posix()}",
            details={"path": question_path.as_posix()},
            project_id=config.project_id,
            next_actions=["Pass an existing --question-file path"],
        )

    try:
        question = question_path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError as exc:
        return failure_envelope(
            command="vibe knowledge query",
            code="QUESTION_FILE_UNREADABLE",
            message=f"Could not read question file: {exc}",
            details={"path": question_path.as_posix()},
            project_id=config.project_id,
        )

    if not question:
        return failure_envelope(
            command="vibe knowledge query",
            code="QUESTION_EMPTY",
            message="Question file is empty",
            details={"path": question_path.as_posix()},
            project_id=config.project_id,
            next_actions=["Write a non-empty question into the file"],
        )

    from vibe_control.knowledge.corpus import CorpusError
    from vibe_control.knowledge.query_router import route_knowledge_query

    try:
        routed = route_knowledge_query(
            repo_root=root,
            question=question,
            notebook_alias=getattr(args, "notebook", None),
        )
    except CorpusError as exc:
        return failure_envelope(
            command="vibe knowledge query",
            code=exc.code,
            message=exc.message,
            details=exc.details,
            project_id=config.project_id,
            next_actions=[
                "Ensure specs.registry path exists and is readable",
                "Run vibe doctor --json",
            ],
        )
    mode = routed.get("mode") or "degraded"
    data: dict[str, Any] = {
        "provider": routed.get("provider"),
        "sync_state": routed.get("sync_state"),
        "synced": routed.get("synced"),
        "provider_target": routed.get("provider_target"),
        "ack_persistence": routed.get("ack_persistence"),
        "answer": routed.get("answer"),
        "sources": routed.get("sources") or [],
        "config_as_policy": routed.get("config_as_policy"),
        "config_synced_as_content": False,
        "fallback_reason": routed.get("fallback_reason"),
    }
    for key in (
        "ask_template_id",
        "ask_template_version",
        "question_hash",
        "rendered_prompt_hash",
        "persona_hash",
        "ask_channels",
        "ask_persona",
        "ask_policy",
        "ask_policy_mode",
        "ask_policy_note",
        "ask_hygiene",
        "provider_ask_clean",
    ):
        if key in routed and routed[key] is not None:
            data[key] = routed[key]
    return attach_operation_result(
        success_envelope(
            command="vibe knowledge query",
            project_id=config.project_id,
            mode=mode,
            data=data,
            warnings=list(routed.get("warnings") or []),
            next_actions=list(routed.get("next_actions") or []),
        ),
        mutation_intent=False,
        effects=[],
    )


def cmd_spec_validate(args: argparse.Namespace) -> dict[str, Any]:
    from vibe_control.spec.publish import validate_spec_path

    root = _repo_root()
    try:
        _load_config(args)
    except ConfigError as exc:
        return failure_envelope(
            command="vibe spec validate",
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )
    result = validate_spec_path(root, args.path)
    if not result.get("ok"):
        return failure_envelope(
            command="vibe spec validate",
            code=str(result.get("code") or "SPEC_INVALID"),
            message=str(result.get("message") or "spec validation failed"),
            details=result,
            project_id=_project_id_or_none(),
        )
    return success_envelope(
        command="vibe spec validate",
        project_id=_project_id_or_none(),
        data=result,
    )


def cmd_spec_publish(args: argparse.Namespace) -> dict[str, Any]:
    from vibe_control.spec.publish import publish_spec

    root = _repo_root()
    try:
        config = _load_config(args)
    except ConfigError as exc:
        return failure_envelope(
            command="vibe spec publish",
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )
    dry_run = bool(getattr(args, "dry_run", False))
    already_pushed = bool(getattr(args, "already_pushed", False))
    # Default gates / CLI: do not auto-apply provider mutation unless --sync-apply
    allow_sync = bool(getattr(args, "sync_apply", False))
    result = publish_spec(
        root,
        args.path,
        dry_run=dry_run,
        already_pushed=already_pushed or dry_run,
        allow_provider_sync=allow_sync and not dry_run,
    )
    if result.get("ok"):
        return success_envelope(
            command="vibe spec publish",
            project_id=config.project_id,
            data=result,
            next_actions=list(result.get("next_actions") or []),
        )
    if result.get("partial_success"):
        return success_envelope(
            command="vibe spec publish",
            project_id=config.project_id,
            data=result,
            warnings=["Publish completed with knowledge_sync failure (partial_success)"],
            next_actions=list(result.get("next_actions") or []),
        )
    return failure_envelope(
        command="vibe spec publish",
        code=str(result.get("code") or "PUBLISH_FAILED"),
        message=str(result.get("message") or "publish failed"),
        details=result,
        project_id=config.project_id,
        partial_success=bool(result.get("partial_success")),
        next_actions=list(result.get("next_actions") or []),
    )


def cmd_task_status(args: argparse.Namespace) -> dict[str, Any]:
    skipped = _capability_disabled_envelope("task", "vibe task status", args)
    if skipped is not None:
        return skipped
    from vibe_control.task.doctor import build_task_status

    result = build_task_status(repo_root=_repo_root())
    readiness = str((result.get("data") or {}).get("readiness") or "unavailable")
    if readiness == "unavailable":
        return failure_envelope(
            command="vibe task status",
            code=str(result.get("code") or "BEADS_NOT_INSTALLED"),
            message="Task provider unavailable",
            details=result.get("data") or {},
            project_id=result.get("project_id"),
            next_actions=list(result.get("next_actions") or []),
        )
    return success_envelope(
        command="vibe task status",
        project_id=result.get("project_id"),
        mode="readonly",
        data=result.get("data") or {},
        next_actions=list(result.get("next_actions") or []),
    )


def cmd_task_doctor(args: argparse.Namespace) -> dict[str, Any]:
    skipped = _capability_disabled_envelope("task", "vibe task doctor", args)
    if skipped is not None:
        return skipped
    from vibe_control.task.doctor import build_task_doctor

    result = build_task_doctor(repo_root=_repo_root())
    return success_envelope(
        command="vibe task doctor",
        project_id=result.get("project_id"),
        mode="readonly",
        data=result.get("data") or {},
        warnings=list(result.get("warnings") or []),
        next_actions=list(result.get("next_actions") or []),
    )


def cmd_knowledge_doctor(args: argparse.Namespace) -> dict[str, Any]:
    skipped = _capability_disabled_envelope("knowledge", "vibe knowledge doctor", args)
    if skipped is not None:
        return skipped
    from vibe_control.knowledge.doctor import build_knowledge_doctor

    result = build_knowledge_doctor(
        repo_root=_repo_root(),
        alias=getattr(args, "notebook", None),
        deep=bool(getattr(args, "deep", False)),
    )
    data = result.get("data") or {}
    if not result.get("ok"):
        code = (data.get("codes") or ["KNOWLEDGE_NOT_READY"])[0]
        return failure_envelope(
            command="vibe knowledge doctor",
            code=str(code),
            message="Knowledge doctor found blocking issues",
            details=data,
            project_id=result.get("project_id") or data.get("project_id"),
            warnings=list(result.get("warnings") or []),
            next_actions=list(result.get("next_actions") or []),
        )
    return success_envelope(
        command="vibe knowledge doctor",
        project_id=result.get("project_id") or data.get("project_id"),
        mode="readonly",
        data=data,
        warnings=list(result.get("warnings") or []),
        next_actions=list(result.get("next_actions") or []),
    )


def cmd_knowledge_init_preview(args: argparse.Namespace) -> dict[str, Any]:
    from vibe_control.knowledge.doctor import build_knowledge_init_preview

    result = build_knowledge_init_preview(
        repo_root=_repo_root(),
        alias=getattr(args, "notebook", None),
    )
    return success_envelope(
        command="vibe knowledge init-preview",
        project_id=result.get("project_id"),
        mode="readonly",
        data=result.get("data") or {},
        warnings=list(result.get("warnings") or []),
        next_actions=list(result.get("next_actions") or []),
    )


def cmd_integration_status(args: argparse.Namespace) -> dict[str, Any]:
    from vibe_control.integration import build_integration_status
    from vibe_control.json_envelope import next_action
    from vibe_control.product_readiness import readiness_next_actions, evaluate_product_readiness

    data = build_integration_status(probe_auth=False, probe_product=True)
    assert data["notebooklm"].get("safe_to_sync") is False
    assert data["repo"].get("fallback_is_product_ready") is False

    next_actions = [
        next_action(
            code="INTEGRATION_DOCTOR",
            command="vibe integration doctor --json",
            mutation=False,
            reason="Use integration doctor for auth/init details",
        ),
    ]
    for action in data.get("next_actions") or []:
        if isinstance(action, dict):
            next_actions.append(action)
    if not data.get("product_ready"):
        # Reuse probe evidence already collected in data (no second deep probe).
        next_actions.extend(
            readiness_next_actions(
                evaluate_product_readiness(
                    repo_root=_repo_root(),
                    knowledge={
                        "available": (data.get("knowledge_provider") or {}).get("available"),
                        "target_ok": (data.get("knowledge_provider") or {}).get("target_ok"),
                        "sync_state": (data.get("knowledge_provider") or {}).get("sync_state")
                        or "unavailable",
                        "required_updates_count": (
                            ((data.get("knowledge_provider") or {}).get("ask_hygiene") or {}).get(
                                "required_updates_count"
                            )
                            or 0
                        ),
                        "candidate_count": (
                            ((data.get("knowledge_provider") or {}).get("ask_hygiene") or {}).get(
                                "candidate_count"
                            )
                            or 0
                        ),
                        "orphan_managed_count": (
                            ((data.get("knowledge_provider") or {}).get("ask_hygiene") or {}).get(
                                "orphan_managed_count"
                            )
                            or 0
                        ),
                    },
                    task={
                        "available": (data.get("task_provider") or {}).get("available"),
                        "mode": (data.get("task_provider") or {}).get("mode") or "unavailable",
                        "readable": (data.get("task_provider") or {}).get("readable"),
                        "ready_queue_available": (data.get("task_provider") or {}).get(
                            "ready_queue_available"
                        ),
                    },
                    probe=False,
                )
            )
        )
    next_actions.append(
        next_action(
            code="MUTATION_REQUIRES_APPLY",
            command="vibe knowledge sync --apply --json",
            mutation=True,
            reason=(
                "Real provider mutation requires explicit apply approval "
                "and product_ready providers"
            ),
        )
    )

    envelope = success_envelope(
        command="vibe integration status",
        project_id=data.get("project_id"),
        mode="readonly",
        data=data,
        warnings=list(data.get("warnings") or []),
        next_actions=next_actions,
    )
    envelope["product_ready"] = bool(data.get("product_ready"))
    envelope["blocked_reasons"] = list(data.get("blocked_reasons") or [])
    return attach_operation_result(envelope, mutation_intent=False, effects=[])


def cmd_integration_doctor(args: argparse.Namespace) -> dict[str, Any]:
    from vibe_control.integration import build_integration_doctor

    data = build_integration_doctor()
    return success_envelope(
        command="vibe integration doctor",
        project_id=(data.get("integration") or {}).get("project_id"),
        data=data,
        warnings=data.get("warnings") or [],
        next_actions=data.get("next_actions") or [],
    )


def cmd_knowledge_auth_status(args: argparse.Namespace) -> dict[str, Any]:
    provider = NotebookLMProvider()
    result = provider.auth_check()
    data = result.to_dict()
    data["safe_to_sync"] = False
    if not result.installed:
        return failure_envelope(
            command="vibe knowledge auth-status",
            code="NOTEBOOKLM_NOT_INSTALLED",
            message=result.message,
            details=data,
            next_actions=result.recommended_actions,
        )
    if result.auth_state == "command_unsupported":
        return failure_envelope(
            command="vibe knowledge auth-status",
            code="NOTEBOOKLM_COMMAND_UNSUPPORTED",
            message=result.message,
            details=data,
            project_id=_project_id_or_none(),
            next_actions=result.recommended_actions,
        )
    if result.auth_state == "auth_failed":
        return failure_envelope(
            command="vibe knowledge auth-status",
            code="NOTEBOOKLM_AUTH_FAILED",
            message=result.message,
            details=data,
            project_id=_project_id_or_none(),
            next_actions=result.recommended_actions,
        )
    if result.auth_state == "command_failed":
        return failure_envelope(
            command="vibe knowledge auth-status",
            code="NOTEBOOKLM_COMMAND_FAILED",
            message=result.message,
            details=data,
            project_id=_project_id_or_none(),
            next_actions=result.recommended_actions,
        )
    return success_envelope(
        command="vibe knowledge auth-status",
        project_id=_project_id_or_none(),
        data=data,
        next_actions=result.recommended_actions,
    )


def cmd_knowledge_login_guide(args: argparse.Namespace) -> dict[str, Any]:
    guide = NotebookLMProvider().login_guide()
    return success_envelope(
        command="vibe knowledge login-guide",
        project_id=_project_id_or_none(),
        data=guide,
        next_actions=list(guide.get("recommended_actions") or []),
    )


def cmd_knowledge_notebook_list(args: argparse.Namespace) -> dict[str, Any]:
    from vibe_control.knowledge.remote_ops import cmd_notebook_list

    return cmd_notebook_list(_repo_root(), args)


def cmd_knowledge_notebook_status(args: argparse.Namespace) -> dict[str, Any]:
    from vibe_control.knowledge.remote_ops import cmd_notebook_status

    return cmd_notebook_status(_repo_root(), args)


def cmd_knowledge_notebook_set_default(args: argparse.Namespace) -> dict[str, Any]:
    from vibe_control.knowledge.remote_ops import cmd_notebook_set_default

    return cmd_notebook_set_default(_repo_root(), args)


def cmd_knowledge_remote_status(args: argparse.Namespace) -> dict[str, Any]:
    from vibe_control.knowledge.remote_ops import cmd_remote_status

    return cmd_remote_status(_repo_root(), args)


def cmd_knowledge_remote_inventory(args: argparse.Namespace) -> dict[str, Any]:
    from vibe_control.knowledge.remote_ops import cmd_remote_inventory

    return cmd_remote_inventory(_repo_root(), args)


def cmd_knowledge_sync_preview(args: argparse.Namespace) -> dict[str, Any]:
    from vibe_control.knowledge.remote_ops import cmd_sync_preview

    return cmd_sync_preview(_repo_root(), args)


def cmd_knowledge_seed_test_sources(args: argparse.Namespace) -> dict[str, Any]:
    from vibe_control.knowledge.remote_ops import cmd_seed_test_sources

    return cmd_seed_test_sources(_repo_root(), args)


def cmd_knowledge_receipt_status(args: argparse.Namespace) -> dict[str, Any]:
    from vibe_control.knowledge.remote_ops import cmd_receipt_status

    return cmd_receipt_status(_repo_root(), args)


def cmd_knowledge_receipt_inspect(args: argparse.Namespace) -> dict[str, Any]:
    from vibe_control.knowledge.remote_ops import cmd_receipt_inspect

    return cmd_receipt_inspect(_repo_root(), args)


def cmd_knowledge_source_wait(args: argparse.Namespace) -> dict[str, Any]:
    from vibe_control.knowledge.remote_ops import cmd_source_wait

    return cmd_source_wait(_repo_root(), args)


def cmd_knowledge_fts_purge(args: argparse.Namespace) -> dict[str, Any]:
    skipped = _capability_disabled_envelope("knowledge", "vibe knowledge fts-purge", args)
    if skipped is not None:
        return skipped
    from vibe_control.knowledge.local_fts.purge import run_fts_purge

    dry_run = bool(getattr(args, "dry_run", False))
    apply = bool(getattr(args, "apply", False))
    if not dry_run and not apply:
        from vibe_control.json_envelope import failure_envelope, next_action

        return failure_envelope(
            command="vibe knowledge fts-purge",
            code="FTS_PURGE_REQUIRES_DRY_RUN_OR_APPLY",
            message="Pass --dry-run or --apply",
            next_actions=[
                next_action(
                    code="FTS_PURGE_REQUIRES_DRY_RUN_OR_APPLY",
                    command="vibe knowledge fts-purge --dry-run --json",
                    mutation=False,
                    reason="Preview orphan/tmp purge plan",
                )
            ],
        )
    return run_fts_purge(
        repo_root=_repo_root(),
        apply=apply and not dry_run,
        purge_all=bool(getattr(args, "all", False)),
        confirm_all=bool(getattr(args, "confirm_all", False)),
    )


def cmd_knowledge_cleanup_candidates(args: argparse.Namespace) -> dict[str, Any]:
    from vibe_control.knowledge.remote_ops import cmd_knowledge_cleanup_candidates

    return cmd_knowledge_cleanup_candidates(_repo_root(), args)


def cmd_knowledge_sync(args: argparse.Namespace) -> dict[str, Any]:
    from vibe_control.knowledge.remote_ops import cmd_knowledge_sync

    return cmd_knowledge_sync(_repo_root(), args)


def cmd_knowledge_retry(args: argparse.Namespace) -> dict[str, Any]:
    from vibe_control.knowledge.remote_ops import cmd_knowledge_retry

    return cmd_knowledge_retry(_repo_root(), args)


def cmd_knowledge_rebuild(args: argparse.Namespace) -> dict[str, Any]:
    """Compatibility alias: rebuild == reindex-bindings (never restores SSOT)."""
    return cmd_knowledge_reindex_bindings(args)


def cmd_knowledge_reindex_bindings(args: argparse.Namespace) -> dict[str, Any]:
    from vibe_control.knowledge.remote_ops import cmd_knowledge_reindex_bindings

    return cmd_knowledge_reindex_bindings(_repo_root(), args)


def cmd_knowledge_cleanup_phase4_residue(args: argparse.Namespace) -> dict[str, Any]:
    from vibe_control.knowledge.remote_ops import cmd_cleanup_phase4_residue

    return cmd_cleanup_phase4_residue(_repo_root(), args)


def cmd_knowledge_smoke_replace(args: argparse.Namespace) -> dict[str, Any]:
    from vibe_control.knowledge.remote_ops import cmd_smoke_replace

    return cmd_smoke_replace(_repo_root(), args)


def cmd_task_install_guide(args: argparse.Namespace) -> dict[str, Any]:
    guide = BeadsProvider().install_guide()
    if not guide.get("installed"):
        return success_envelope(
            command="vibe task install-guide",
            project_id=_project_id_or_none(),
            data=guide,
            warnings=["Beads (bd) is not installed"],
            next_actions=list(guide.get("recommended_actions") or []),
        )
    return success_envelope(
        command="vibe task install-guide",
        project_id=_project_id_or_none(),
        data=guide,
        next_actions=list(guide.get("recommended_actions") or []),
    )


def cmd_task_init_preview(args: argparse.Namespace) -> dict[str, Any]:
    from vibe_control.components import build_component_config_guidance

    preview = BeadsProvider().init_preview()
    data = preview.to_dict()
    guidance = build_component_config_guidance()
    data.update(
        {
            "profile_preview": dict(guidance.get("profile_preview") or {}),
            "capability_guidance": dict(guidance.get("capability_guidance") or {}),
            "components": guidance["components"],
            "component_config_example": guidance["component_config_example"],
            "component_config_example_yaml": guidance["component_config_example_yaml"],
            "component_config_guidance": guidance["component_config_guidance"],
            "enable_examples": list(guidance.get("enable_examples") or []),
            "invalid_examples": guidance["invalid_examples"],
            "diagnostic_only": True,
            "mutation": False,
            "auto_enable": False,
            "install_adapt_uninstall": False,
        }
    )
    guidance_actions = list(guidance.get("next_actions") or [])
    if not preview.installed:
        return failure_envelope(
            command="vibe task init-preview",
            code="BEADS_NOT_INSTALLED",
            message=preview.message,
            details=data,
            project_id=_project_id_or_none(),
            next_actions=guidance_actions
            + [
                "Run python -m vibe_control task install-guide --json",
            ],
        )
    if preview.init_safe_mode == "unavailable" and preview.recommended_init is None:
        return failure_envelope(
            command="vibe task init-preview",
            code="BEADS_INIT_UNSAFE",
            message=preview.message,
            details=data,
            project_id=_project_id_or_none(),
            next_actions=guidance_actions
            + [
                "Review `bd init --help` manually before any init",
                "Do not run bd init from vibe CLI automatically",
            ],
        )
    return success_envelope(
        command="vibe task init-preview",
        project_id=_project_id_or_none(),
        data=data,
        next_actions=guidance_actions
        + [
            f"Recommended preview only — do not auto-run: {preview.recommended_init}",
            "User approval required before any real bd init",
        ],
    )


def cmd_implementation_prompt(args: argparse.Namespace) -> dict[str, Any]:
    from vibe_control.implementation.cli import run_implementation_prompt

    selector = getattr(args, "task", None) or ""
    if not str(selector).strip():
        return failure_envelope(
            command="vibe implementation prompt",
            code="TASK_SELECTOR_REQUIRED",
            message="Pass --task <managed_key|provider_task_id|ssot_anchor>",
            next_actions=[
                next_action(
                    code="IMPLEMENTATION_NEXT",
                    command="vibe implementation next --json",
                    mutation=False,
                    reason="Discover next actionable task from roadmap-state",
                )
            ],
        )
    return run_implementation_prompt(
        repo_root=_repo_root(),
        task_selector=str(selector),
        include_provider_probe=not bool(getattr(args, "skip_provider_probe", False)),
    )


def cmd_implementation_next(args: argparse.Namespace) -> dict[str, Any]:
    """Dogfood next selection from roadmap-state (never invents Phase 13)."""
    from vibe_control.implementation.next import build_implementation_next

    return build_implementation_next(
        repo_root=_repo_root(),
        project_id=_project_id_or_none(),
    )


def cmd_progress(args: argparse.Namespace) -> dict[str, Any]:
    """Readonly Vibe Progress projection over Engine outputs."""
    from vibe_control.progress_brief import build_progress

    return build_progress(repo_root=_repo_root())


def cmd_brief(args: argparse.Namespace) -> dict[str, Any]:
    """Readonly Vibe Brief for the primary coding agent."""
    from vibe_control.progress_brief import build_brief, format_brief_text

    envelope = build_brief(repo_root=_repo_root())
    if str(getattr(args, "brief_format", "json") or "json") == "text":
        envelope["_emit_text"] = format_brief_text(envelope)
    return envelope


def cmd_grill_status(args: argparse.Namespace) -> dict[str, Any]:
    from vibe_control.grill_session import status_payload
    from vibe_control.json_envelope import next_action as na
    from vibe_control.self_grill_contract import self_grill_continue_next_action

    data = status_payload(_repo_root())
    next_actions = []
    if data.get("in_progress"):
        next_actions = [
            self_grill_continue_next_action(),
            na(
                code="GRILL_CHECKPOINT",
                command="vibe grill checkpoint --json",
                mutation=True,
                reason="Advance round_id",
            ),
            na(
                code="GRILL_CLOSE_EXHAUSTED",
                command="vibe grill close --status EXHAUSTED --json",
                mutation=True,
                reason="End when frontier empty",
            ),
        ]
    return success_envelope(
        command="vibe grill status",
        project_id=_project_id_or_none(),
        data=data,
        next_actions=next_actions,
    )


def cmd_grill_checkpoint(args: argparse.Namespace) -> dict[str, Any]:
    from vibe_control.grill_session import GrillSessionError, checkpoint_session
    from vibe_control.json_envelope import next_action as na
    from vibe_control.self_grill_contract import self_grill_continue_next_action

    try:
        session = checkpoint_session(
            _repo_root(),
            round_id=getattr(args, "round_id", None),
            loop_status=getattr(args, "loop_status", None),
            claim_count=getattr(args, "claim_count", None),
            note=getattr(args, "note", None),
        )
    except GrillSessionError as exc:
        return failure_envelope(
            command="vibe grill checkpoint",
            code=exc.code,
            message=exc.message,
            details=exc.details,
            project_id=_project_id_or_none(),
        )
    in_progress = str(session.get("loop_status")) == "IN_PROGRESS"
    next_actions = (
        [
            self_grill_continue_next_action(),
            na(
                code="GRILL_CLOSE_EXHAUSTED",
                command="vibe grill close --status EXHAUSTED --json",
                mutation=True,
                reason="End when frontier empty",
            ),
        ]
        if in_progress
        else [
            na(
                code="CHECK_PROGRESS",
                command="vibe progress --json",
                mutation=False,
                reason="Grill closed; resume Engine safe_next",
            )
        ]
    )
    return success_envelope(
        command="vibe grill checkpoint",
        project_id=_project_id_or_none(),
        mode="local_runtime_write",
        data={"session": session, "mutation": True},
        next_actions=next_actions,
    )


def cmd_grill_close(args: argparse.Namespace) -> dict[str, Any]:
    from vibe_control.grill_session import GrillSessionError, close_session
    from vibe_control.json_envelope import next_action as na

    try:
        session = close_session(
            _repo_root(),
            status=str(args.status),
            note=getattr(args, "note", None),
        )
    except GrillSessionError as exc:
        return failure_envelope(
            command="vibe grill close",
            code=exc.code,
            message=exc.message,
            details=exc.details,
            project_id=_project_id_or_none(),
        )
    return success_envelope(
        command="vibe grill close",
        project_id=_project_id_or_none(),
        mode="local_runtime_write",
        data={"session": session, "mutation": True, "active_cleared": True},
        next_actions=[
            na(
                code="CHECK_PROGRESS",
                command="vibe progress --json",
                mutation=False,
                reason="Grill closed; resume Engine safe_next / implementation path",
            )
        ],
    )


def cmd_gateway(args: argparse.Namespace) -> dict[str, Any]:
    """Thin Gateway intent router to existing Engine surfaces (readonly by default)."""
    from vibe_control.gateway import route_gateway
    from vibe_control.json_envelope import next_action

    intent = getattr(args, "gateway_intent", None) or getattr(args, "intent", None) or ""
    if not str(intent).strip():
        return failure_envelope(
            command="vibe gateway",
            code="GATEWAY_INTENT_REQUIRED",
            message=(
                "Pass --intent <status|what_next|get_prompt|why_blocked|summary|brief|"
                "grill_brief|skill_assay_brief|prepare_closeout|verify_after_work>"
            ),
            next_actions=[
                next_action(
                    code="GATEWAY_STATUS",
                    command="vibe gateway --intent status --json",
                    mutation=False,
                    reason="Readonly status route via Engine Progress",
                )
            ],
        )
    return route_gateway(
        intent=str(intent),
        repo_root=_repo_root(),
        task=getattr(args, "task", None),
        skill=getattr(args, "skill", None),
        host=getattr(args, "host", None),
    )


def cmd_describe(args: argparse.Namespace) -> dict[str, Any]:
    """Readonly Vibe Describe control-surface explanation."""
    from vibe_control.describe import build_describe

    return build_describe(repo_root=_repo_root())


def cmd_closeout_run(args: argparse.Namespace) -> dict[str, Any]:
    """High-level SSOT closeout runner (default readonly; --apply for bounded knowledge only)."""
    from vibe_control.closeout_runner import run_closeout

    return run_closeout(repo_root=_repo_root(), apply=bool(getattr(args, "apply", False)))


def cmd_task_apply(args: argparse.Namespace) -> dict[str, Any]:
    from vibe_control.json_envelope import next_action
    from vibe_control.task.apply_cli import run_task_apply

    dry_run = bool(getattr(args, "dry_run", False))
    do_apply = bool(getattr(args, "apply", False))
    if dry_run and do_apply:
        return failure_envelope(
            command="vibe task apply",
            code="APPLY_AMBIGUOUS_FLAGS",
            message="Pass exactly one of --dry-run or --apply",
            next_actions=[
                next_action(
                    code="APPLY_DRY_RUN",
                    command="vibe task apply --dry-run --json --provider fake",
                    mutation=False,
                    reason="Plan without mutation",
                )
            ],
        )
    if not dry_run and not do_apply:
        return failure_envelope(
            command="vibe task apply",
            code="APPLY_REQUIRES_DRY_RUN_OR_APPLY",
            message="Phase 11B task apply requires --dry-run or --apply",
            next_actions=[
                next_action(
                    code="APPLY_DRY_RUN",
                    command="vibe task apply --dry-run --json --provider fake",
                    mutation=False,
                    reason="Default-safe plan; no provider mutation",
                ),
                next_action(
                    code="APPLY_FAKE",
                    command="vibe task apply --apply --json --provider fake",
                    mutation=True,
                    reason="Controlled fake-provider mutation only",
                ),
            ],
        )
    mode = "dry_run" if dry_run else "apply"
    strict: bool | None = None
    if getattr(args, "allow_local_without_providers", False):
        strict = False
    elif getattr(args, "strict_providers", False):
        strict = True
    result = run_task_apply(
        repo_root=_repo_root(),
        mode=mode,  # type: ignore[arg-type]
        provider_name=getattr(args, "provider", None),
        strict_providers=strict,
        expect_plan_binding=getattr(args, "expect_plan_binding", None),
        beads_confirm=bool(getattr(args, "confirm_beads_live_apply", False)),
        autonomous_managed=bool(getattr(args, "autonomous_managed", False)),
    )
    if "command" not in result:
        result["command"] = "vibe task apply"
    return result


def cmd_task_cache_reset(args: argparse.Namespace) -> dict[str, Any]:
    from vibe_control.json_envelope import next_action
    from vibe_control.task.cache_reset import run_task_cache_reset

    dry_run = bool(getattr(args, "dry_run", False))
    apply = bool(getattr(args, "apply", False))
    if not dry_run and not apply:
        return failure_envelope(
            command="vibe task cache reset",
            code="CACHE_RESET_REQUIRES_DRY_RUN_OR_APPLY",
            message="Pass --dry-run or --apply",
            next_actions=[
                next_action(
                    code="CACHE_RESET_REQUIRES_DRY_RUN_OR_APPLY",
                    command="vibe task cache reset --dry-run --json",
                    mutation=False,
                    reason="Preview local ephemeral cache reset/regenerate plan",
                )
            ],
        )
    return run_task_cache_reset(
        repo_root=_repo_root(),
        apply=apply and not dry_run,
        provider_name=str(getattr(args, "provider", None) or "fake"),
    )


def cmd_task_reconcile(args: argparse.Namespace) -> dict[str, Any]:
    from vibe_control.json_envelope import next_action
    from vibe_control.task.reconcile_cli import run_task_reconcile_dry_run

    if not getattr(args, "dry_run", False):
        return failure_envelope(
            command="vibe task reconcile",
            code="RECONCILE_REQUIRES_DRY_RUN",
            message="Phase 11A task reconcile requires --dry-run (readonly; no Beads mutation)",
            next_actions=[
                next_action(
                    code="RECONCILE_REQUIRES_DRY_RUN",
                    command="vibe task reconcile --dry-run --json",
                    mutation=False,
                    reason="Re-run with --dry-run; use vibe task apply for Phase 11B",
                )
            ],
        )
    provider_name = getattr(args, "provider", None)
    result = run_task_reconcile_dry_run(
        repo_root=_repo_root(),
        provider_name=provider_name,
    )
    if not result.get("ok"):
        return failure_envelope(
            command="vibe task reconcile",
            code=str(result.get("code") or "RECONCILE_FAILED"),
            message=str(result.get("message") or "reconcile failed"),
            details=result.get("data") or {},
            project_id=result.get("project_id"),
            warnings=list(result.get("warnings") or []),
            next_actions=list(result.get("next_actions") or []),
        )
    envelope = success_envelope(
        command="vibe task reconcile",
        project_id=result.get("project_id"),
        mode=str(result.get("mode") or "readonly"),
        data=result.get("data") or {},
        warnings=list(result.get("warnings") or []),
        next_actions=list(result.get("next_actions") or []),
    )
    # Stable top-level fields for skill routing / acceptance.
    envelope["provider"] = result.get("provider")
    envelope["provider_available"] = bool(result.get("provider_available"))
    envelope["mutation"] = False
    return envelope


def cmd_skills_status(args: argparse.Namespace) -> dict[str, Any]:
    from vibe_control.skills_manager import skills_readiness, skills_status

    data = skills_status()
    guide = skills_readiness()
    data["condition"] = guide.get("condition")
    data["missing"] = guide.get("missing")
    data["mismatch"] = guide.get("mismatch")
    return success_envelope(
        command="vibe skills status",
        project_id=_project_id_or_none(),
        data=data,
        warnings=list(guide.get("warnings") or []),
        next_actions=list(guide.get("next_actions") or []),
    )


def cmd_feedback_init_preview(args: argparse.Namespace) -> dict[str, Any]:
    from vibe_control.feedback import init_preview
    from vibe_control.json_envelope import next_action as na

    data = init_preview(repo_root=_repo_root())
    return success_envelope(
        command="vibe feedback init-preview",
        project_id=_project_id_or_none(),
        data=data,
        next_actions=[
            na(
                code="FEEDBACK_DRAFT",
                command="vibe feedback draft --kind pain --title '…' --summary-file s.txt --json",
                mutation=True,
                reason="Create a local experience-signal artifact (not a task)",
            )
        ],
    )


def cmd_feedback_draft(args: argparse.Namespace) -> dict[str, Any]:
    from vibe_control.diagnostics import attach_doctor_snippet
    from vibe_control.feedback import FeedbackError, draft_feedback

    summary = (getattr(args, "summary", None) or "").strip()
    summary_file = getattr(args, "summary_file", None)
    if summary_file:
        path = Path(summary_file)
        if not path.is_file():
            return failure_envelope(
                command="vibe feedback draft",
                code="SUMMARY_FILE_NOT_FOUND",
                message=f"Summary file not found: {path.as_posix()}",
                project_id=_project_id_or_none(),
            )
        summary = path.read_text(encoding="utf-8", errors="replace").strip()
    try:
        result = draft_feedback(
            repo_root=_repo_root(),
            kind=str(args.kind),
            title=str(args.title),
            summary=summary,
            desired=str(getattr(args, "desired", "") or ""),
            feedback_id=getattr(args, "id", None),
            related_paths=list(getattr(args, "related_path", None) or []),
            related_task_ids=list(getattr(args, "related_task", None) or []),
            envelope_codes=list(getattr(args, "envelope_code", None) or []),
        )
        if bool(getattr(args, "attach_doctor", False)):
            doctor_env = _build_doctor_envelope(args)
            attached = attach_doctor_snippet(
                entry_dir=Path(result["entry_dir"]),
                feedback_yaml=Path(result["path"]),
                doctor_envelope=doctor_env,
            )
            result = {**result, **attached, "doctor_attached": True}
    except FeedbackError as exc:
        return failure_envelope(
            command="vibe feedback draft",
            code=exc.code,
            message=exc.message,
            details=exc.details,
            project_id=_project_id_or_none(),
        )
    return success_envelope(
        command="vibe feedback draft",
        project_id=_project_id_or_none(),
        data=result,
        warnings=[
            "redaction.confirmed is false until you review; validate will fail until set true",
            *(
                ["doctor-redacted.json attached — review before confirming redaction"]
                if result.get("doctor_attached")
                else []
            ),
        ],
        next_actions=[
            f"Edit {result['path']} and set redaction.confirmed: true",
            f"vibe feedback validate --path {result['id']} --json",
        ],
    )


def cmd_diagnostics_bundle(args: argparse.Namespace) -> dict[str, Any]:
    """Local redacted diagnostics zip (never uploads)."""
    from vibe_control.diagnostics import write_diagnostics_bundle
    from vibe_control.json_envelope import attach_operation_result
    from vibe_control.skills_manager import skills_readiness

    if not bool(getattr(args, "redacted", False)):
        return attach_operation_result(
            failure_envelope(
                command="vibe diagnostics bundle",
                code="DIAGNOSTICS_REDACTED_REQUIRED",
                message="Pass --redacted (only redacted local bundles are supported)",
                project_id=_project_id_or_none(),
                next_actions=["vibe diagnostics bundle --redacted --json"],
            ),
            mutation_intent=True,
            effects=[],
        )
    doctor_env = _build_doctor_envelope(args)
    skills = skills_readiness()
    result = write_diagnostics_bundle(
        repo_root=_repo_root(),
        doctor_envelope=doctor_env,
        skills_status=skills,
    )
    return attach_operation_result(
        success_envelope(
            command="vibe diagnostics bundle",
            project_id=_project_id_or_none(),
            data=result,
            warnings=["Local only; never auto-upload"],
            next_actions=[
                "Review zip contents before any voluntary share",
                "Optional: attach snippets via vibe feedback draft --attach-doctor",
            ],
        ),
        mutation_intent=True,
        effects=[
            {
                "kind": "local_state_write",
                "target": "diagnostics.bundle",
                "status": "completed",
            }
        ],
    )


def cmd_skill_assay_brief(args: argparse.Namespace) -> dict[str, Any]:
    from vibe_control.skill_assay.brief import build_skill_assay_brief
    from vibe_control.skill_assay.errors import SkillAssayError

    try:
        return build_skill_assay_brief(
            repo_root=_repo_root(),
            skill_path=getattr(args, "skill", None),
            host_id=getattr(args, "host", None),
            project_id=_project_id_or_none(),
        )
    except SkillAssayError as exc:
        from vibe_control.json_envelope import attach_operation_result

        return attach_operation_result(
            failure_envelope(
                command="vibe skill-assay brief",
                code=exc.code,
                message=exc.message,
                details=exc.details,
                project_id=_project_id_or_none(),
            ),
            mutation_intent=False,
            effects=[],
        )


def cmd_skill_assay_doctor(args: argparse.Namespace) -> dict[str, Any]:
    from vibe_control.json_envelope import attach_operation_result
    from vibe_control.skill_assay.errors import SkillAssayError
    from vibe_control.skill_assay.registry import build_adapter_registry

    host_id = str(getattr(args, "host", "") or "").strip()
    registry = build_adapter_registry(include_fake=True)
    if host_id not in registry:
        return attach_operation_result(
            failure_envelope(
                command="vibe skill-assay doctor",
                code="SKILL_ASSAY_HOST_UNKNOWN",
                message=f"unknown host_id: {host_id}",
                details={"host_id": host_id, "allowed": sorted(registry)},
                project_id=_project_id_or_none(),
            ),
            mutation_intent=False,
            effects=[],
        )
    try:
        result = registry[host_id].doctor()
    except SkillAssayError as exc:
        return attach_operation_result(
            failure_envelope(
                command="vibe skill-assay doctor",
                code=exc.code,
                message=exc.message,
                details=exc.details,
                project_id=_project_id_or_none(),
            ),
            mutation_intent=False,
            effects=[],
        )
    return attach_operation_result(
        success_envelope(
            command="vibe skill-assay doctor",
            project_id=_project_id_or_none(),
            data={
                "host_id": result.host_id,
                "ok": result.ok,
                "support_state": result.support_state,
                "details": result.details,
                "blockers": result.blockers,
            },
        ),
        mutation_intent=False,
        effects=[],
    )


def cmd_skill_assay_diagnose(args: argparse.Namespace) -> dict[str, Any]:
    from vibe_control.json_envelope import attach_operation_result, next_action as na
    from vibe_control.skill_assay.errors import SkillAssayError
    from vibe_control.skill_assay.orchestrator import run_diagnose
    from vibe_control.skill_assay.registry import build_adapter_registry

    execute = bool(getattr(args, "execute", False))
    dry_run = bool(getattr(args, "dry_run", False))
    if execute == dry_run:
        return attach_operation_result(
            failure_envelope(
                command="vibe skill-assay diagnose",
                code="SKILL_ASSAY_MODE_REQUIRED",
                message="Pass exactly one of --dry-run or --execute",
                project_id=_project_id_or_none(),
            ),
            mutation_intent=True,
            effects=[],
        )
    scenario = getattr(args, "scenario", None)
    prompt_file = getattr(args, "prompt_file", None)
    try:
        data = run_diagnose(
            repo_root=_repo_root(),
            skill_path=Path(str(args.skill)),
            host_id=str(args.host),
            runs=int(getattr(args, "runs", 3) or 3),
            execute=execute,
            scenario_path=Path(scenario) if scenario else None,
            prompt_file=Path(prompt_file) if prompt_file else None,
            baseline_host=getattr(args, "baseline_host", None),
            adapters=build_adapter_registry(include_fake=True),
        )
    except SkillAssayError as exc:
        return attach_operation_result(
            failure_envelope(
                command="vibe skill-assay diagnose",
                code=exc.code,
                message=exc.message,
                details=exc.details,
                project_id=_project_id_or_none(),
            ),
            mutation_intent=True,
            effects=[],
        )
    effects: list[dict[str, Any]] = []
    if execute:
        effects = [
            {
                "kind": "local_state_write",
                "target": "skill_assay.evidence",
                "status": "completed",
            }
        ]
    next_actions = list(data.get("next_actions") or [])
    if not next_actions and not execute:
        next_actions = [
            na(
                code="SKILL_ASSAY_EXECUTE",
                command=(
                    "vibe skill-assay diagnose --skill <dir> --host <host> "
                    "--prompt-file <file> --runs 3 --execute --json"
                ),
                mutation=True,
                reason="Dry-run only; re-run with --execute to collect evidence",
            )
        ]
    return attach_operation_result(
        success_envelope(
            command="vibe skill-assay diagnose",
            project_id=_project_id_or_none(),
            data=data,
            next_actions=next_actions,
        ),
        mutation_intent=True,
        effects=effects,
    )


def cmd_skill_assay_finalize(args: argparse.Namespace) -> dict[str, Any]:
    from vibe_control.json_envelope import attach_operation_result
    from vibe_control.skill_assay.errors import SkillAssayError
    from vibe_control.skill_assay.finalize import finalize_assay

    try:
        report = finalize_assay(
            repo_root=_repo_root(),
            assay_id=str(args.assay),
            analysis_path=Path(str(args.analysis_file)),
        )
    except SkillAssayError as exc:
        return attach_operation_result(
            failure_envelope(
                command="vibe skill-assay finalize",
                code=exc.code,
                message=exc.message,
                details=exc.details,
                project_id=_project_id_or_none(),
            ),
            mutation_intent=True,
            effects=[],
        )
    return attach_operation_result(
        success_envelope(
            command="vibe skill-assay finalize",
            project_id=_project_id_or_none(),
            data=report,
        ),
        mutation_intent=True,
        effects=[
            {
                "kind": "local_state_write",
                "target": "skill_assay.report",
                "status": "completed",
            }
        ],
    )


def cmd_skill_assay_report(args: argparse.Namespace) -> dict[str, Any]:
    from vibe_control.json_envelope import attach_operation_result
    from vibe_control.skill_assay.errors import SkillAssayError
    from vibe_control.skill_assay.storage import load_evidence, load_report

    assay_id = str(args.assay)
    try:
        try:
            data = load_report(_repo_root(), assay_id)
            kind = "report"
        except SkillAssayError:
            data = load_evidence(_repo_root(), assay_id)
            kind = "evidence"
    except SkillAssayError as exc:
        return attach_operation_result(
            failure_envelope(
                command="vibe skill-assay report",
                code=exc.code,
                message=exc.message,
                details=exc.details,
                project_id=_project_id_or_none(),
            ),
            mutation_intent=False,
            effects=[],
        )
    return attach_operation_result(
        success_envelope(
            command="vibe skill-assay report",
            project_id=_project_id_or_none(),
            data={"kind": kind, "payload": data},
        ),
        mutation_intent=False,
        effects=[],
    )


def cmd_skill_assay_pack(args: argparse.Namespace) -> dict[str, Any]:
    from vibe_control.json_envelope import attach_operation_result
    from vibe_control.skill_assay.errors import SkillAssayError
    from vibe_control.skill_assay.pack import pack_assay

    out = Path(str(args.output)).expanduser() if getattr(args, "output", None) else None
    try:
        data = pack_assay(
            repo_root=_repo_root(),
            assay_id=str(args.assay),
            output_path=out,
        )
    except SkillAssayError as exc:
        return attach_operation_result(
            failure_envelope(
                command="vibe skill-assay pack",
                code=exc.code,
                message=exc.message,
                details=exc.details,
                project_id=_project_id_or_none(),
            ),
            mutation_intent=True,
            effects=[],
        )
    return attach_operation_result(
        success_envelope(
            command="vibe skill-assay pack",
            project_id=_project_id_or_none(),
            data=data,
        ),
        mutation_intent=True,
        effects=[
            {
                "kind": "local_state_write",
                "target": "skill_assay.pack_zip",
                "status": "completed",
            }
        ],
    )


def cmd_feedback_validate(args: argparse.Namespace) -> dict[str, Any]:
    from vibe_control.feedback import FeedbackError, validate_feedback
    from vibe_control.json_envelope import next_action as na

    try:
        result = validate_feedback(repo_root=_repo_root(), path_or_id=str(args.path))
    except FeedbackError as exc:
        return failure_envelope(
            command="vibe feedback validate",
            code=exc.code,
            message=exc.message,
            details=exc.details,
            project_id=_project_id_or_none(),
        )
    if not result.get("ok"):
        return failure_envelope(
            command="vibe feedback validate",
            code="FEEDBACK_VALIDATE_FAILED",
            message="Feedback validation failed",
            details=result,
            project_id=_project_id_or_none(),
            next_actions=[
                na(
                    code="FEEDBACK_REDACT",
                    command=f"Edit {result.get('path')} — redact secrets and set redaction.confirmed: true",
                    mutation=True,
                    reason="Validate requires confirmed redaction and no secret hits",
                )
            ],
        )
    return success_envelope(
        command="vibe feedback validate",
        project_id=_project_id_or_none(),
        data=result,
        next_actions=[
            f"vibe feedback pack --path {result.get('id')} --json",
            "Share the zip voluntarily (issue attach / PR) — never auto-upload",
        ],
    )


def cmd_feedback_pack(args: argparse.Namespace) -> dict[str, Any]:
    from vibe_control.feedback import FeedbackError, pack_feedback

    try:
        result = pack_feedback(repo_root=_repo_root(), path_or_id=str(args.path))
    except FeedbackError as exc:
        return failure_envelope(
            command="vibe feedback pack",
            code=exc.code,
            message=exc.message,
            details=exc.details,
            project_id=_project_id_or_none(),
            next_actions=[
                f"vibe feedback validate --path {args.path} --json",
            ],
        )
    return success_envelope(
        command="vibe feedback pack",
        project_id=_project_id_or_none(),
        data=result,
        warnings=["Pack is local only; uploading/sharing is voluntary and out of band"],
        next_actions=[
            "Attach zip to a GitHub Issue only if you choose to share",
        ],
    )


def cmd_skills_install(args: argparse.Namespace) -> dict[str, Any]:
    from vibe_control.json_envelope import next_action
    from vibe_control.skills_manager import SkillsError, install_skills

    dry_run = bool(getattr(args, "dry_run", False))
    apply = bool(getattr(args, "apply", False))
    force = bool(getattr(args, "force", False))
    mode = getattr(args, "mode", "symlink") or "symlink"
    if not dry_run and not apply:
        return failure_envelope(
            command="vibe skills install",
            code="SKILLS_INSTALL_REQUIRES_DRY_RUN_OR_APPLY",
            message="Pass --dry-run or --apply",
            project_id=_project_id_or_none(),
            next_actions=[
                next_action(
                    code="SKILLS_INSTALL_REQUIRES_DRY_RUN_OR_APPLY",
                    command="vibe skills install --dry-run --json",
                    mutation=False,
                    reason="Preview symlink/copy plan",
                ),
                next_action(
                    code="SKILLS_INSTALL_REQUIRES_DRY_RUN_OR_APPLY",
                    command="vibe skills install --apply --json",
                    mutation=True,
                    reason="Apply install only with explicit approval",
                ),
            ],
        )
    try:
        result = install_skills(dry_run=bool(dry_run and not apply), force=force, mode=mode)
    except SkillsError as exc:
        return failure_envelope(
            command="vibe skills install",
            code=exc.code,
            message=exc.message,
            details=exc.details,
            project_id=_project_id_or_none(),
            next_actions=[
                next_action(
                    code=exc.code,
                    command="vibe skills install --dry-run --json",
                    mutation=False,
                    reason="Use --dry-run to preview symlink operations",
                ),
            ],
        )
    warnings = list((result.get("status") or {}).get("warnings") or [])
    return success_envelope(
        command="vibe skills install",
        project_id=_project_id_or_none(),
        mode="dry_run" if (dry_run and not apply) else "mutation",
        data=result,
        warnings=warnings,
        next_actions=[
            next_action(
                code="SKILLS_STATUS",
                command="vibe skills status --json",
                mutation=False,
                reason="Verify installed skill symlinks",
            ),
        ],
    )


def _project_id_or_none() -> str | None:
    try:
        return _load_config().project_id
    except ConfigError:
        return None


def _hetu_raw_enabled(config: Any) -> bool:
    """Read components.hetu.enabled from raw config (catalog may not list hetu yet)."""
    comps = getattr(config, "raw", {}).get("components") if config is not None else None
    if not isinstance(comps, dict):
        return False
    entry = comps.get("hetu")
    if not isinstance(entry, dict):
        return False
    return bool(entry.get("enabled"))


def _hetu_disabled_envelope(command: str, args: argparse.Namespace | None = None) -> dict[str, Any]:
    from vibe_control.json_envelope import next_action

    return attach_operation_result(
        success_envelope(
            command=command,
            project_id=_project_id_or_none(),
            mode="readonly",
            data={
                "capability_disabled": True,
                "component_id": "hetu",
                "skipped": True,
                "mutation": False,
                "message": (
                    "components.hetu.enabled is false (or absent). "
                    "Hetu is optional and default-disabled; enable explicitly in "
                    "control.yaml after codebase-memory prerequisites."
                ),
            },
            next_actions=[
                next_action(
                    code="ENABLE_HETU_CONFIG",
                    command="vibe doctor --json",
                    mutation=False,
                    reason=(
                        "Review Hetu enablement; do not auto-enable; "
                        "edit control.yaml explicitly when ready"
                    ),
                ),
            ],
        ),
        mutation_intent=False,
        effects=[],
    )


def _build_hetu_command_context(args: argparse.Namespace):
    """Build injected HetuCommandContext from repo config + provider (fake or CLI adapter)."""
    from vibe_control.config import parse_hetu_config
    from vibe_control.hetu.binding import canonicalize_repo_root
    from vibe_control.hetu.commands import HetuCommandContext
    from vibe_control.hetu.provider import FakeHetuProvider
    from vibe_control.hetu.receipt import load_index_binding_receipt
    from vibe_control.progress_brief import read_git_status_short, read_observed_head

    root = canonicalize_repo_root(_repo_root())
    config = _load_config(args)
    hetu_cfg = parse_hetu_config(config.hetu if isinstance(config.hetu, dict) else {})
    enabled = _hetu_raw_enabled(config)
    observed_head = read_observed_head(root) or "unknown"
    git_dirty = bool(read_git_status_short(root).strip())

    provider_id = hetu_cfg.provider
    configured_project = hetu_cfg.codebase_memory.project
    provider_version: str | None = None
    provider_available = True
    provider_compatible = True
    watcher_observable = True
    projects: list[dict[str, Any]] = []
    config_values: dict[str, str] | None = {}
    provider: Any = None

    if provider_id == "fake":
        provider = FakeHetuProvider(
            repo_root=root,
            projects=[
                {
                    "name": configured_project or "fake-project",
                    "root_path": str(root),
                    "nodes": 2,
                    "edges": 1,
                }
            ],
        )
        provider_version = provider._status.provider_version
        projects = provider.list_projects()
        config_values = {"auto_watch": "false"}
    else:
        from vibe_control.hetu.codebase_memory_cli import (
            CodebaseMemoryCliAdapter,
            CodebaseMemoryCliError,
        )

        adapter = CodebaseMemoryCliAdapter(
            binary=hetu_cfg.codebase_memory.binary,
            project=configured_project,
            repo_root=root,
            query_timeout_sec=hetu_cfg.codebase_memory.query_timeout_sec,
            reindex_timeout_sec=hetu_cfg.codebase_memory.reindex_timeout_sec,
        )
        provider = adapter
        try:
            probe = adapter.probe_compatibility()
            provider_version = probe.provider_version
            provider_compatible = bool(probe.compatible)
            projects = list(probe.projects or [])
            config_values = probe.config_values
            watcher_observable = probe.config_values is not None
            provider_available = True
        except CodebaseMemoryCliError:
            provider_available = False
            provider_compatible = False
            watcher_observable = False
            config_values = None

    def _list_projects() -> list[dict[str, Any]]:
        if provider is not None and hasattr(provider, "list_projects"):
            return list(provider.list_projects())
        return list(projects)

    def _config_values() -> dict[str, str] | None:
        return None if config_values is None else dict(config_values)

    def _index_status(project: str):
        if provider is None:
            raise RuntimeError("provider missing")
        if hasattr(provider, "project"):
            try:
                provider.project = project  # type: ignore[attr-defined]
            except Exception:
                pass
        return provider.status()

    def _refresh_git() -> tuple[str, bool]:
        return (
            read_observed_head(root) or "unknown",
            bool(read_git_status_short(root).strip()),
        )

    return HetuCommandContext(
        repo_root=root,
        project_id=config.project_id,
        provider_id=provider_id if provider_id != "fake" else "fake",
        provider_version=provider_version,
        index_mode=hetu_cfg.codebase_memory.index_mode,
        configured_project=configured_project,
        hetu_enabled=enabled,
        provider_available=provider_available,
        provider_compatible=provider_compatible,
        watcher_state_observable=watcher_observable,
        list_projects=_list_projects,
        config_values=_config_values,
        load_receipt=lambda: load_index_binding_receipt(
            config.project_id,
            provider=provider_id if provider_id != "fake" else "fake",
        ),
        index_status=_index_status,
        provider=provider,
        observed_head=observed_head,
        git_dirty=git_dirty,
        search_limit_default=hetu_cfg.codebase_memory.search_limit,
        trace_depth_default=hetu_cfg.codebase_memory.trace_depth,
        impact_depth_default=hetu_cfg.codebase_memory.impact_depth,
        refresh_git=_refresh_git,
    )


def _hetu_run(
    args: argparse.Namespace,
    command: str,
    builder,
) -> dict[str, Any]:
    try:
        config = _load_config(args)
    except ConfigError as exc:
        return attach_operation_result(
            failure_envelope(
                command=command,
                code=exc.code,
                message=exc.message,
                details=exc.details,
            ),
            mutation_intent=False,
            effects=[],
        )
    if not _hetu_raw_enabled(config):
        return _hetu_disabled_envelope(command, args)
    ctx = _build_hetu_command_context(args)
    return builder(ctx)


def cmd_hetu_status(args: argparse.Namespace) -> dict[str, Any]:
    from vibe_control.hetu.commands import build_hetu_status

    return _hetu_run(args, "hetu.status", build_hetu_status)


def cmd_hetu_doctor(args: argparse.Namespace) -> dict[str, Any]:
    from vibe_control.hetu.commands import build_hetu_doctor

    return _hetu_run(args, "hetu.doctor", build_hetu_doctor)


def cmd_hetu_search(args: argparse.Namespace) -> dict[str, Any]:
    from vibe_control.hetu.commands import build_hetu_search

    def _builder(ctx):
        return build_hetu_search(
            ctx,
            query=str(getattr(args, "query", "") or ""),
            limit=getattr(args, "limit", None),
        )

    return _hetu_run(args, "hetu.search", _builder)


def cmd_hetu_trace(args: argparse.Namespace) -> dict[str, Any]:
    from vibe_control.hetu.commands import build_hetu_trace

    def _builder(ctx):
        return build_hetu_trace(
            ctx,
            symbol=str(getattr(args, "symbol", "") or ""),
            direction=str(getattr(args, "direction", "both") or "both"),
            depth=getattr(args, "depth", None),
        )

    return _hetu_run(args, "hetu.trace", _builder)


def cmd_hetu_impact(args: argparse.Namespace) -> dict[str, Any]:
    from vibe_control.hetu.commands import build_hetu_impact

    def _builder(ctx):
        return build_hetu_impact(
            ctx,
            since=getattr(args, "since", None),
            depth=getattr(args, "depth", None),
        )

    return _hetu_run(args, "hetu.impact", _builder)


def cmd_hetu_architecture(args: argparse.Namespace) -> dict[str, Any]:
    from vibe_control.hetu.commands import build_hetu_architecture

    return _hetu_run(args, "hetu.architecture", build_hetu_architecture)


def cmd_hetu_reindex(args: argparse.Namespace) -> dict[str, Any]:
    from vibe_control.hetu.commands import (
        build_hetu_reindex_apply,
        build_hetu_reindex_dry_run,
    )

    apply = bool(getattr(args, "apply", False))
    dry_run = bool(getattr(args, "dry_run", False)) or not apply
    if apply and dry_run and bool(getattr(args, "dry_run", False)):
        # Explicit both flags: prefer apply path.
        dry_run = False
    if apply:
        try:
            config = _load_config(args)
        except ConfigError as exc:
            return attach_operation_result(
                failure_envelope(
                    command="hetu.reindex",
                    code=exc.code,
                    message=exc.message,
                    details=exc.details,
                ),
                mutation_intent=True,
                effects=[],
            )
        if not _hetu_raw_enabled(config):
            # Apply still reports mutation_intent=true even when blocked/disabled.
            out = _hetu_disabled_envelope("hetu.reindex", args)
            out["mutation_intent"] = True
            out["mutation_performed"] = False
            out["mutation"] = False
            return out
        ctx = _build_hetu_command_context(args)
        return build_hetu_reindex_apply(
            ctx,
            expect_plan_binding=getattr(args, "expect_plan_binding", None),
            confirm=bool(getattr(args, "confirm_hetu_reindex_apply", False)),
        )
    return _hetu_run(args, "hetu.reindex", build_hetu_reindex_dry_run)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vibe",
        description="Vibe Control — user-level control layer for AI-assisted development",
    )
    parser.add_argument("--version", action="version", version=f"vibe-control {__version__}")

    json_parent = argparse.ArgumentParser(add_help=False)
    json_parent.add_argument(
        "--json",
        action="store_true",
        help="Emit stable JSON envelope",
    )
    json_parent.add_argument(
        "--config",
        default=None,
        help="Explicit path to vibe-control.yaml (overrides discovery)",
    )

    sub = parser.add_subparsers(dest="command")

    doctor = sub.add_parser(
        "doctor",
        parents=[json_parent],
        help="Environment and readiness checks",
    )
    doctor.set_defaults(handler=cmd_doctor)

    progress = sub.add_parser(
        "progress",
        parents=[json_parent],
        help="Readonly Vibe Progress projection (current state + safe next action)",
    )
    progress.set_defaults(handler=cmd_progress)

    brief = sub.add_parser(
        "brief",
        parents=[json_parent],
        help="Readonly Vibe Brief for the primary coding agent",
    )
    brief.add_argument(
        "--format",
        dest="brief_format",
        choices=["json", "text"],
        default="json",
        help="Output format (default: json envelope; text is short human-readable)",
    )
    brief.set_defaults(handler=cmd_brief)

    grill = sub.add_parser(
        "grill",
        help="Local self-grill session receipts (not SSOT; not Knowledge)",
    )
    grill_sub = grill.add_subparsers(dest="grill_command", required=True)
    g_status = grill_sub.add_parser(
        "status",
        parents=[json_parent],
        help="Readonly: active grill session pointer + receipt",
    )
    g_status.set_defaults(handler=cmd_grill_status)
    g_ckpt = grill_sub.add_parser(
        "checkpoint",
        parents=[json_parent],
        help="Advance round_id (or set loop_status); local runtime write only",
    )
    g_ckpt.add_argument(
        "--round-id",
        type=int,
        default=None,
        help="Set absolute round_id (>=0); default increments",
    )
    g_ckpt.add_argument(
        "--loop-status",
        default=None,
        choices=["IN_PROGRESS", "EXHAUSTED", "BLOCKED_ON_LIVE"],
        help="Optional; terminal statuses close the session",
    )
    g_ckpt.add_argument("--claim-count", type=int, default=None, help="Optional claim counter")
    g_ckpt.add_argument("--note", default=None, help="Optional note")
    g_ckpt.set_defaults(handler=cmd_grill_checkpoint)
    g_close = grill_sub.add_parser(
        "close",
        parents=[json_parent],
        help="End session (EXHAUSTED|BLOCKED_ON_LIVE) and clear active",
    )
    g_close.add_argument(
        "--status",
        required=True,
        choices=["EXHAUSTED", "BLOCKED_ON_LIVE"],
        help="Terminal LOOP_STATUS",
    )
    g_close.add_argument("--note", default=None, help="Optional note")
    g_close.set_defaults(handler=cmd_grill_close)

    gateway = sub.add_parser(
        "gateway",
        parents=[json_parent],
        help="Thin Gateway intent router to Engine surfaces (readonly by default)",
    )
    gateway.add_argument(
        "--intent",
        dest="gateway_intent",
        required=True,
        help=(
            "Intent to route: status|what_next|get_prompt|why_blocked|summary|brief|"
            "prepare_closeout|verify_after_work|grill_brief|skill_assay_brief "
            "(mutation/raw-provider intents fail closed)"
        ),
    )
    gateway.add_argument(
        "--task",
        default=None,
        help="Task selector for get_prompt (ssot_anchor|managed_key|provider binding id)",
    )
    gateway.add_argument(
        "--skill",
        default=None,
        help="Local skill directory for skill_assay_brief",
    )
    gateway.add_argument(
        "--host",
        default=None,
        choices=["cursor", "github-copilot", "fake"],
        help="Target host for skill_assay_brief / doctor binding",
    )
    gateway.set_defaults(handler=cmd_gateway)

    describe = sub.add_parser(
        "describe",
        parents=[json_parent],
        help="Readonly Vibe Describe control-surface explanation (authority / surfaces / mutation classes)",
    )
    describe.set_defaults(handler=cmd_describe)
    readme = sub.add_parser(
        "readme",
        parents=[json_parent],
        help="Alias of `vibe describe` (runtime self-explain; not a product README file)",
    )
    readme.set_defaults(handler=cmd_describe)

    config = sub.add_parser("config", help="Config inspect / validate")
    config_sub = config.add_subparsers(dest="config_command", required=True)
    inspect = config_sub.add_parser(
        "inspect",
        parents=[json_parent],
        help="Print parsed config",
    )
    inspect.set_defaults(handler=cmd_config_inspect)
    validate = config_sub.add_parser(
        "validate",
        parents=[json_parent],
        help="Validate config",
    )
    validate.set_defaults(handler=cmd_config_validate)

    knowledge = sub.add_parser("knowledge", help="Knowledge corpus operations")
    knowledge_sub = knowledge.add_subparsers(dest="knowledge_command", required=True)
    inventory = knowledge_sub.add_parser(
        "inventory",
        parents=[json_parent],
        help="Desired corpus inventory",
    )
    inventory.add_argument("--notebook", default=None, help="Notebook alias (required when 2+ allow_list)")
    inventory.set_defaults(handler=cmd_knowledge_inventory)

    spec = sub.add_parser("spec", help="Spec validate / publish")
    spec_sub = spec.add_subparsers(dest="spec_command", required=True)
    svalidate = spec_sub.add_parser(
        "validate",
        parents=[json_parent],
        help="Validate a formal spec path against registry and publish rules",
    )
    svalidate.add_argument("path", help="Spec path relative to repo root")
    svalidate.set_defaults(handler=cmd_spec_validate)
    spublish = spec_sub.add_parser(
        "publish",
        parents=[json_parent],
        help="Validate and publish a formal spec; optionally sync via Phase 8",
    )
    spublish.add_argument("path", help="Spec path relative to repo root")
    spublish.add_argument("--dry-run", action="store_true", help="Plan only; no commit/push/sync mutation")
    spublish.add_argument(
        "--already-pushed",
        action="store_true",
        help="Use current upstream/origin ref; do not commit or push",
    )
    spublish.add_argument(
        "--sync-apply",
        action="store_true",
        help="After publish validation, call Phase 8 knowledge sync --apply path",
    )
    spublish.set_defaults(handler=cmd_spec_publish)

    kstatus = knowledge_sub.add_parser(
        "status",
        parents=[json_parent],
        help="Knowledge sync status (target-scoped; read-only)",
    )
    kstatus.add_argument("--notebook", default=None, help="Notebook alias override")
    kstatus.set_defaults(handler=cmd_knowledge_status)
    kdoctor = knowledge_sub.add_parser(
        "doctor",
        parents=[json_parent],
        help="Knowledge domain readiness precheck (readonly; shallow by default)",
    )
    kdoctor.add_argument("--notebook", default=None, help="Notebook alias override")
    kdoctor.add_argument(
        "--deep",
        action="store_true",
        help="Reserved for future deep remote probes (currently deferred; shallow still runs)",
    )
    kdoctor.set_defaults(handler=cmd_knowledge_doctor)
    kinit = knowledge_sub.add_parser(
        "init-preview",
        parents=[json_parent],
        help="Readonly knowledge setup plan (no mutation)",
    )
    kinit.add_argument("--notebook", default=None, help="Notebook alias override")
    kinit.set_defaults(handler=cmd_knowledge_init_preview)
    kquery = knowledge_sub.add_parser(
        "query",
        parents=[json_parent],
        help="Degraded repo fallback query",
    )
    kquery.add_argument(
        "--question-file",
        required=True,
        help="Path to a text file containing the question",
    )
    kquery.set_defaults(handler=cmd_knowledge_query)
    kauth = knowledge_sub.add_parser(
        "auth-status",
        parents=[json_parent],
        help="Passive NotebookLM auth check",
    )
    kauth.set_defaults(handler=cmd_knowledge_auth_status)
    klogin = knowledge_sub.add_parser(
        "login-guide",
        parents=[json_parent],
        help="NotebookLM login guidance",
    )
    klogin.set_defaults(handler=cmd_knowledge_login_guide)

    notebook = knowledge_sub.add_parser("notebook", help="Notebook allow-list operations")
    notebook_sub = notebook.add_subparsers(dest="notebook_command", required=True)
    nlist = notebook_sub.add_parser("list", parents=[json_parent], help="List allow-listed notebooks")
    nlist.set_defaults(handler=cmd_knowledge_notebook_list)
    nstatus = notebook_sub.add_parser("status", parents=[json_parent], help="Resolve notebook alias")
    nstatus.add_argument("--notebook", default=None, help="Notebook alias override")
    nstatus.set_defaults(handler=cmd_knowledge_notebook_status)
    nset = notebook_sub.add_parser(
        "set-default",
        parents=[json_parent],
        help="Set default notebook alias",
    )
    nset.add_argument("alias", help="Notebook alias from allow list")
    nset.add_argument("--dry-run", action="store_true", help="Preview only")
    nset.set_defaults(handler=cmd_knowledge_notebook_set_default)

    remote_status = knowledge_sub.add_parser(
        "remote-status",
        parents=[json_parent],
        help="NotebookLM remote readiness for allow-listed notebook",
    )
    remote_status.add_argument("--notebook", default=None, help="Notebook alias")
    remote_status.set_defaults(handler=cmd_knowledge_remote_status)

    remote_inv = knowledge_sub.add_parser(
        "remote-inventory",
        parents=[json_parent],
        help="List remote sources and classify managed/unmanaged",
    )
    remote_inv.add_argument("--notebook", default=None, help="Notebook alias")
    remote_inv.set_defaults(handler=cmd_knowledge_remote_inventory)

    sync_preview = knowledge_sub.add_parser(
        "sync-preview",
        parents=[json_parent],
        help="Preview sync operations (no mutation)",
    )
    sync_preview.add_argument("--notebook", default=None, help="Notebook alias")
    sync_preview.set_defaults(handler=cmd_knowledge_sync_preview)

    # Compatibility aliases
    kdiff = knowledge_sub.add_parser(
        "diff",
        parents=[json_parent],
        help="Alias for sync-preview",
    )
    kdiff.add_argument("--notebook", default=None)
    kdiff.add_argument("--dry-run", action="store_true")
    kdiff.set_defaults(handler=cmd_knowledge_sync_preview)
    kplan = knowledge_sub.add_parser(
        "sync-plan",
        parents=[json_parent],
        help="Alias for sync-preview",
    )
    kplan.add_argument("--notebook", default=None)
    kplan.set_defaults(handler=cmd_knowledge_sync_preview)

    cleanup_candidates = knowledge_sub.add_parser(
        "cleanup-candidates",
        parents=[json_parent],
        help="List readonly manual cleanup candidates (never deletes)",
    )
    cleanup_candidates.add_argument("--notebook", default=None, help="Notebook alias")
    cleanup_candidates.set_defaults(handler=cmd_knowledge_cleanup_candidates)

    fts_purge = knowledge_sub.add_parser(
        "fts-purge",
        parents=[json_parent],
        help=(
            "Purge stale local_fts indexes (orphan scopes + tmp). "
            "Use --all --confirm-all to wipe all local_fts for this project."
        ),
    )
    fts_purge.add_argument("--dry-run", action="store_true", help="Plan only")
    fts_purge.add_argument("--apply", action="store_true", help="Delete per plan")
    fts_purge.add_argument(
        "--all",
        action="store_true",
        help="Wipe entire project local_fts/ tree (requires --confirm-all with --apply)",
    )
    fts_purge.add_argument(
        "--confirm-all",
        action="store_true",
        help="Required with --all --apply",
    )
    fts_purge.set_defaults(handler=cmd_knowledge_fts_purge)

    sync = knowledge_sub.add_parser(
        "sync",
        parents=[json_parent],
        help="Sync desired corpus (dry-run or apply)",
    )
    sync.add_argument("--notebook", default=None, help="Notebook alias")
    sync.add_argument("--dry-run", action="store_true", help="Plan only")
    sync.add_argument("--apply", action="store_true", help="Apply add/replace/cleanup")
    sync.add_argument(
        "--confirm-non-default-sync",
        action="store_true",
        help=(
            "Required with --apply when --notebook is not default_alias "
            "(owner/task approval for side-notebook mutation)"
        ),
    )
    sync.add_argument(
        "--continue-on-item-error",
        action="store_true",
        help=(
            "Opt-in partial continue: after item_skippable/retryable failures keep going, "
            "checkpoint successes, emit item_failures (DLQ). Default is fail_stop. "
            "Fatal errors still stop. Never claims synced while failures remain."
        ),
    )
    sync.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help=(
            "Micro-batch size for creates before wait (default 1=legacy serial; max 20). "
            "Replaces stay one-at-a-time."
        ),
    )
    sync.add_argument(
        "--wait-mode",
        choices=["serial", "multi"],
        default=None,
        help=(
            "How to wait for a micro-batch on CLI ingest: serial (default) or multi "
            "(concurrent in-process waits; CLI is still single-id). "
            "Ignored when ingest_path=api (library wait_for_sources)."
        ),
    )
    sync.add_argument(
        "--ingest-path",
        choices=["auto", "api", "cli"],
        default=None,
        help=(
            "Multi-file upload path: auto (API if notebooklm importable else CLI), "
            "api (concurrent add_file + wait_for_sources), cli (serial subprocess add). "
            "API is the throughput path for multi-file sync."
        ),
    )
    sync.add_argument(
        "--upload-concurrency",
        type=int,
        default=None,
        help=(
            "Max in-flight single-file API uploads (default 8, max 16). "
            "Only applies when ingest_path resolves to api. "
            "Use with --batch-size >= concurrency for multi-file throughput."
        ),
    )
    sync.set_defaults(handler=cmd_knowledge_sync)

    retry = knowledge_sub.add_parser(
        "retry",
        parents=[json_parent],
        help="Retry sync from latest desired corpus",
    )
    retry.add_argument("--notebook", default=None, help="Notebook alias")
    retry.add_argument("--dry-run", action="store_true", help="Plan only")
    retry.add_argument("--apply", action="store_true", help="Apply retry")
    retry.add_argument(
        "--confirm-non-default-sync",
        action="store_true",
        help="Required with --apply when --notebook is not default_alias",
    )
    retry.add_argument(
        "--continue-on-item-error",
        action="store_true",
        help=(
            "Same as sync --continue-on-item-error: continue remaining docs after "
            "non-fatal item failures; successes stay checkpointed"
        ),
    )
    retry.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Same as sync --batch-size",
    )
    retry.add_argument(
        "--wait-mode",
        choices=["serial", "multi"],
        default=None,
        help="Same as sync --wait-mode",
    )
    retry.add_argument(
        "--ingest-path",
        choices=["auto", "api", "cli"],
        default=None,
        help="Same as sync --ingest-path",
    )
    retry.add_argument(
        "--upload-concurrency",
        type=int,
        default=None,
        help="Same as sync --upload-concurrency",
    )
    retry.set_defaults(handler=cmd_knowledge_retry)

    rebuild = knowledge_sub.add_parser(
        "rebuild",
        parents=[json_parent],
        help="Alias of reindex-bindings: rebuild local provider binding receipt only",
    )
    rebuild.add_argument("--notebook", default=None, help="Notebook alias")
    rebuild.add_argument("--dry-run", action="store_true", default=False, help="Unused; kept for compat")
    rebuild.set_defaults(handler=cmd_knowledge_rebuild)

    reindex = knowledge_sub.add_parser(
        "reindex-bindings",
        parents=[json_parent],
        help="Reindex provider binding receipt from metadata (never restores SSOT content)",
    )
    reindex.add_argument("--notebook", default=None, help="Notebook alias")
    reindex.set_defaults(handler=cmd_knowledge_reindex_bindings)

    residue = knowledge_sub.add_parser(
        "cleanup-phase4-residue",
        parents=[json_parent],
        help=(
            "INTERNAL/acceptance-only: delete exact approved Phase 4 test residue titles "
            "(requires --acceptance-cleanup; not a normal user workflow)"
        ),
    )
    residue.add_argument("--notebook", default=None, help="Notebook alias")
    residue.add_argument(
        "--acceptance-cleanup",
        action="store_true",
        help="Required gate: acknowledge this is acceptance/test-residue cleanup only",
    )
    residue.add_argument("--dry-run", action="store_true", help="Plan only")
    residue.add_argument(
        "--allow-delete",
        action="store_true",
        help="Explicitly allow delete of the approved title set",
    )
    residue.set_defaults(handler=cmd_knowledge_cleanup_phase4_residue)

    smoke = knowledge_sub.add_parser("smoke", help="INTERNAL/ACCEPTANCE ONLY smoke helpers")
    smoke_sub = smoke.add_subparsers(dest="smoke_command", required=True)
    smoke_replace = smoke_sub.add_parser(
        "replace",
        parents=[json_parent],
        help=(
            "INTERNAL/ACCEPTANCE ONLY: Phase 6 replace lifecycle smoke "
            "(isolated smoke receipt; does not touch production desired corpus)"
        ),
    )
    smoke_replace.add_argument("--notebook", default=None, help="Notebook alias")
    smoke_replace.add_argument("--dry-run", action="store_true", help="Plan only (no mutation)")
    smoke_replace.add_argument("--apply", action="store_true", help="Apply real smoke mutations")
    smoke_replace.add_argument(
        "--cleanup",
        action="store_true",
        help="After replace evidence, delete final temporary smoke source",
    )
    smoke_replace.set_defaults(handler=cmd_knowledge_smoke_replace)

    seed = knowledge_sub.add_parser(
        "seed-test-sources",
        parents=[json_parent],
        help="Add-only seed into allow-listed notebook (approval required)",
    )
    seed.add_argument("--notebook", default=None, help="Notebook alias")
    seed.add_argument("--dry-run", action="store_true", help="Preview planned adds")
    seed.add_argument(
        "--allow-add",
        action="store_true",
        help="Explicitly allow real add-only mutation",
    )
    seed.set_defaults(handler=cmd_knowledge_seed_test_sources)

    receipt = knowledge_sub.add_parser("receipt", help="Local sync receipt status")
    receipt_sub = receipt.add_subparsers(dest="receipt_command", required=True)
    rstatus = receipt_sub.add_parser("status", parents=[json_parent], help="Receipt status")
    rstatus.set_defaults(handler=cmd_knowledge_receipt_status)
    rinspect = receipt_sub.add_parser(
        "inspect", parents=[json_parent], help="Inspect receipt (redacted)"
    )
    rinspect.set_defaults(handler=cmd_knowledge_receipt_inspect)

    source = knowledge_sub.add_parser("source", help="Provider source operations")
    source_sub = source.add_subparsers(dest="source_command", required=True)
    swait = source_sub.add_parser(
        "wait",
        parents=[json_parent],
        help="Wait until a source is ready (read-only)",
    )
    swait.add_argument("--notebook", default=None, help="Notebook alias")
    swait.add_argument("--source-id", required=True, help="Provider source id")
    swait.add_argument("--timeout", type=float, default=120.0)
    swait.add_argument("--interval", type=float, default=3.0)
    swait.set_defaults(handler=cmd_knowledge_source_wait)

    task = sub.add_parser("task", help="Task / Beads operations")
    task_sub = task.add_subparsers(dest="task_command", required=True)
    tstatus = task_sub.add_parser(
        "status",
        parents=[json_parent],
        help="Task provider readiness (ready/not_ready/unavailable)",
    )
    tstatus.set_defaults(handler=cmd_task_status)
    tdoctor = task_sub.add_parser(
        "doctor",
        parents=[json_parent],
        help="Task/Beads domain readiness precheck (readonly)",
    )
    tdoctor.set_defaults(handler=cmd_task_doctor)
    tguide = task_sub.add_parser(
        "install-guide",
        parents=[json_parent],
        help="Beads install guidance (no install)",
    )
    tguide.set_defaults(handler=cmd_task_install_guide)
    tpreview = task_sub.add_parser(
        "init-preview",
        parents=[json_parent],
        help="Preview safe bd init options (no init)",
    )
    tpreview.set_defaults(handler=cmd_task_init_preview)
    trecon = task_sub.add_parser(
        "reconcile",
        parents=[json_parent],
        help="Readonly reconcile expected SSOT tasks vs task provider (Phase 11A)",
    )
    trecon.add_argument(
        "--dry-run",
        action="store_true",
        help="Required for Phase 11A: report only; never mutate Beads",
    )
    trecon.add_argument(
        "--provider",
        choices=("fake", "beads"),
        default=None,
        help="Task provider for readonly reconcile (default: config tasks.provider or beads)",
    )
    trecon.set_defaults(handler=cmd_task_reconcile)
    tapply = task_sub.add_parser(
        "apply",
        parents=[json_parent],
        help="Phase 11B apply/import plan (dry-run or controlled --apply)",
    )
    tapply.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan only; mutation=false",
    )
    tapply.add_argument(
        "--apply",
        action="store_true",
        help="Execute create_managed/update_managed only (fake provider; beads blocked by default)",
    )
    tapply.add_argument(
        "--provider",
        choices=("fake", "beads"),
        default=None,
        help="Task provider (default: config tasks.provider or beads)",
    )
    tapply.add_argument(
        "--confirm-beads-live-apply",
        action="store_true",
        help=(
            "Option A confirm token for live Beads apply "
            "(also requires VIBE_BEADS_LIVE_APPLY=1 and --autonomous-managed)"
        ),
    )
    tapply.add_argument(
        "--autonomous-managed",
        action="store_true",
        help=(
            "Option A: allow live Vibe-managed create/update when product_ready "
            "and plan is safe (still requires dual gate)"
        ),
    )
    tapply.add_argument(
        "--expect-plan-binding",
        default=None,
        help="Block apply if current SSOT plan_binding_hash differs (stale plan guard)",
    )
    tapply.add_argument(
        "--allow-local-without-providers",
        action="store_true",
        help="Disable strict knowledge-provider gate (local/fake dogfood only)",
    )
    tapply.add_argument(
        "--strict-providers",
        action="store_true",
        help="Require knowledge provider readiness before task apply (default for --provider beads)",
    )
    tapply.set_defaults(handler=cmd_task_apply)

    tcache = task_sub.add_parser(
        "cache",
        help="Local embedded ephemeral task cache operations",
    )
    tcache_sub = tcache.add_subparsers(dest="task_cache_command", required=True)
    tcache_reset = tcache_sub.add_parser(
        "reset",
        parents=[json_parent],
        help="Reset/regenerate local ephemeral Vibe-managed task cache",
    )
    tcache_reset.add_argument("--dry-run", action="store_true", help="Plan only; mutation=false")
    tcache_reset.add_argument("--apply", action="store_true", help="Apply reset/regenerate")
    tcache_reset.add_argument(
        "--provider",
        choices=("fake", "beads"),
        default="fake",
        help="Provider for reset (fake or live local embedded Beads)",
    )
    tcache_reset.set_defaults(handler=cmd_task_cache_reset)

    integration = sub.add_parser("integration", help="Local integration bootstrap")
    integration_sub = integration.add_subparsers(dest="integration_command", required=True)
    istatus = integration_sub.add_parser(
        "status",
        parents=[json_parent],
        help="Integration readiness summary",
    )
    istatus.set_defaults(handler=cmd_integration_status)
    idoctor = integration_sub.add_parser(
        "doctor",
        parents=[json_parent],
        help="Detailed integration diagnosis",
    )
    idoctor.set_defaults(handler=cmd_integration_doctor)

    skills = sub.add_parser("skills", help="Vibe agent skills install")
    skills_sub = skills.add_subparsers(dest="skills_command", required=True)
    sstatus = skills_sub.add_parser(
        "status",
        parents=[json_parent],
        help="Show ~/.agents/skills install status",
    )
    sstatus.set_defaults(handler=cmd_skills_status)
    sinstall = skills_sub.add_parser(
        "install",
        parents=[json_parent],
        help="Install thin Vibe skills into ~/.agents/skills (requires --dry-run or --apply)",
    )
    sinstall.add_argument(
        "--dry-run",
        action="store_true",
        help="Show symlink/copy operations without writing",
    )
    sinstall.add_argument(
        "--apply",
        action="store_true",
        help="Apply symlink/copy install (required for mutation)",
    )
    sinstall.add_argument(
        "--force",
        action="store_true",
        help="Replace mismatched vibe-* targets only",
    )
    sinstall.add_argument(
        "--mode",
        choices=["symlink", "copy"],
        default="symlink",
        help="Install mode (default: symlink)",
    )
    sinstall.set_defaults(handler=cmd_skills_install)

    feedback = sub.add_parser(
        "feedback",
        help="Experience-signal capture in consumer repo (not tasks; no upload)",
    )
    feedback_sub = feedback.add_subparsers(dest="feedback_command", required=True)
    fb_init = feedback_sub.add_parser(
        "init-preview",
        parents=[json_parent],
        help="Readonly: feedback root + redaction checklist",
    )
    fb_init.set_defaults(handler=cmd_feedback_init_preview)
    fb_draft = feedback_sub.add_parser(
        "draft",
        parents=[json_parent],
        help="Write a local vibe.feedback.v1 YAML skeleton (redaction.confirmed=false)",
    )
    fb_draft.add_argument(
        "--kind",
        required=True,
        choices=sorted(
            ["pain", "owner_dissatisfaction", "bright_spot", "friction", "bug_signal"]
        ),
        help="Experience signal kind (not a task kind)",
    )
    fb_draft.add_argument("--title", required=True, help="Short headline")
    fb_draft.add_argument("--summary", default="", help="Inline summary text")
    fb_draft.add_argument(
        "--summary-file",
        default=None,
        help="Read summary from file (preferred for long text)",
    )
    fb_draft.add_argument("--desired", default="", help="Optional desired improvement")
    fb_draft.add_argument("--id", default=None, help="Optional feedback id")
    fb_draft.add_argument(
        "--related-path",
        action="append",
        default=[],
        help="Optional repo-relative path (repeatable)",
    )
    fb_draft.add_argument(
        "--related-task",
        action="append",
        default=[],
        help="Optional Beads id for orientation only (repeatable)",
    )
    fb_draft.add_argument(
        "--envelope-code",
        action="append",
        default=[],
        help="Optional envelope code observed (repeatable)",
    )
    fb_draft.add_argument(
        "--attach-doctor",
        action="store_true",
        help="Attach a redacted vibe doctor JSON snippet next to feedback.yaml",
    )
    fb_draft.set_defaults(handler=cmd_feedback_draft)
    fb_validate = feedback_sub.add_parser(
        "validate",
        parents=[json_parent],
        help="Validate schema + redaction.confirmed + basic secret heuristics",
    )
    fb_validate.add_argument(
        "--path",
        required=True,
        help="Feedback id or path to feedback.yaml",
    )
    fb_validate.set_defaults(handler=cmd_feedback_validate)
    fb_pack = feedback_sub.add_parser(
        "pack",
        parents=[json_parent],
        help="Zip a validated feedback entry for voluntary share (local only)",
    )
    fb_pack.add_argument(
        "--path",
        required=True,
        help="Feedback id or path to feedback.yaml",
    )
    fb_pack.set_defaults(handler=cmd_feedback_pack)

    diagnostics = sub.add_parser(
        "diagnostics",
        help="Local diagnostics helpers (redacted; never upload)",
    )
    diag_sub = diagnostics.add_subparsers(dest="diagnostics_command", required=True)
    dbundle = diag_sub.add_parser(
        "bundle",
        parents=[json_parent],
        help="Write a redacted doctor+skills zip under runtime/vibe-feedback/diagnostics/",
    )
    dbundle.add_argument(
        "--redacted",
        action="store_true",
        help="Required: only redacted local bundles are supported",
    )
    dbundle.set_defaults(handler=cmd_diagnostics_bundle)

    skill_assay = sub.add_parser(
        "skill-assay",
        help="Skill Assay: measure any local skill across hosts (not vibe skills install)",
    )
    sa_sub = skill_assay.add_subparsers(dest="skill_assay_command", required=True)
    sa_brief = sa_sub.add_parser(
        "brief",
        parents=[json_parent],
        help="Agent entry: Skill Assay contract + next_actions (readonly)",
    )
    sa_brief.add_argument("--skill", default=None, help="Local skill directory with SKILL.md")
    sa_brief.add_argument(
        "--host",
        default=None,
        choices=["cursor", "github-copilot", "fake"],
        help="Optional host to probe via doctor in the brief",
    )
    sa_brief.set_defaults(handler=cmd_skill_assay_brief)
    sa_doctor = sa_sub.add_parser(
        "doctor",
        parents=[json_parent],
        help="Probe host adapter readiness (SDK/auth/injection)",
    )
    sa_doctor.add_argument(
        "--host",
        required=True,
        choices=["cursor", "github-copilot", "fake"],
        help="Target host runtime",
    )
    sa_doctor.set_defaults(handler=cmd_skill_assay_doctor)
    sa_diag = sa_sub.add_parser(
        "diagnose",
        parents=[json_parent],
        help="Snapshot skill and collect N-run evidence (default 3)",
    )
    sa_diag.add_argument("--skill", required=True, help="Local skill directory with SKILL.md")
    sa_diag.add_argument(
        "--host",
        required=True,
        choices=["cursor", "github-copilot", "fake"],
        help="Target host runtime",
    )
    sa_diag.add_argument("--scenario", default=None, help="Scenario YAML path")
    sa_diag.add_argument("--prompt-file", default=None, help="Prompt text file (shortcut scenario)")
    sa_diag.add_argument("--runs", type=int, default=3, help="Independent runs (2..5; default 3)")
    sa_diag.add_argument(
        "--baseline-host",
        default=None,
        choices=["cursor", "github-copilot", "fake"],
        help="Optional second host for cross-host causal scope",
    )
    sa_diag.add_argument("--dry-run", action="store_true", help="Plan only; no host execute")
    sa_diag.add_argument("--execute", action="store_true", help="Run host sessions and write receipts")
    sa_diag.set_defaults(handler=cmd_skill_assay_diagnose)
    sa_fin = sa_sub.add_parser(
        "finalize",
        parents=[json_parent],
        help="Validate analysis file and write final report",
    )
    sa_fin.add_argument("--assay", required=True, help="Assay id from diagnose")
    sa_fin.add_argument("--analysis-file", required=True, help="Agent analysis JSON path")
    sa_fin.set_defaults(handler=cmd_skill_assay_finalize)
    sa_rep = sa_sub.add_parser(
        "report",
        parents=[json_parent],
        help="Readonly: re-read evidence or finalized report",
    )
    sa_rep.add_argument("--assay", required=True, help="Assay id")
    sa_rep.set_defaults(handler=cmd_skill_assay_report)
    sa_pack = sa_sub.add_parser(
        "pack",
        parents=[json_parent],
        help="Zip an assay folder for sharing with skill maintainers",
    )
    sa_pack.add_argument("--assay", required=True, help="Assay id")
    sa_pack.add_argument(
        "--output",
        default=None,
        help="Optional zip path (default: runtime/vibe-skill-assay/<assay>.zip)",
    )
    sa_pack.set_defaults(handler=cmd_skill_assay_pack)

    implementation = sub.add_parser(
        "implementation",
        help="Maintainer/dogfood: implementation helpers (prompt / next)",
    )
    impl_sub = implementation.add_subparsers(dest="implementation_command", required=True)
    iprompt = impl_sub.add_parser(
        "prompt",
        parents=[json_parent],
        help="Generate a copy-paste coding-agent prompt for a Vibe-managed task (readonly)",
    )
    iprompt.add_argument(
        "--task",
        required=True,
        help="managed_key, provider_task_id, or ssot_anchor (e.g. roadmap.phase12)",
    )
    iprompt.add_argument(
        "--skip-provider-probe",
        action="store_true",
        help="Skip live provider readiness probe (local unit tests)",
    )
    iprompt.set_defaults(handler=cmd_implementation_prompt)
    inext = impl_sub.add_parser(
        "next",
        parents=[json_parent],
        help="Select next actionable task from roadmap-state (readonly; never invents phases)",
    )
    inext.set_defaults(handler=cmd_implementation_next)

    closeout = sub.add_parser(
        "closeout",
        help="Maintainer/dogfood: SSOT closeout orchestration (not first-consumer path)",
    )
    closeout_sub = closeout.add_subparsers(dest="closeout_command", required=True)
    crun = closeout_sub.add_parser(
        "run",
        parents=[json_parent],
        help=(
            "Run SSOT closeout checks; default is readonly dry-run. "
            "Pass --apply only for bounded knowledge sync closeout (never live Beads)."
        ),
    )
    crun.add_argument(
        "--dry-run",
        action="store_true",
        help="Readonly closeout plan (default when --apply is absent)",
    )
    crun.add_argument(
        "--apply",
        action="store_true",
        help="Allow bounded NotebookLM sync --apply as closeout knowledge half only",
    )
    crun.set_defaults(handler=cmd_closeout_run)

    hetu = sub.add_parser(
        "hetu",
        help="Hetu code-structure capability (optional; default disabled)",
    )
    hetu_sub = hetu.add_subparsers(dest="hetu_command", required=True)

    h_status = hetu_sub.add_parser(
        "status",
        parents=[json_parent],
        help="Hetu index binding / freshness status (readonly)",
    )
    h_status.set_defaults(handler=cmd_hetu_status)

    h_doctor = hetu_sub.add_parser(
        "doctor",
        parents=[json_parent],
        help="Hetu doctor (readonly; recommends auto_watch=false, never runs it)",
    )
    h_doctor.set_defaults(handler=cmd_hetu_doctor)

    h_search = hetu_sub.add_parser(
        "search",
        parents=[json_parent],
        help="Bounded BM25 structural search (requires ready index)",
    )
    h_search.add_argument("--query", required=True, help="Search query string")
    h_search.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max hits (default 20, max 50)",
    )
    h_search.set_defaults(handler=cmd_hetu_search)

    h_trace = hetu_sub.add_parser(
        "trace",
        parents=[json_parent],
        help="Bounded call/data-flow trace (requires ready index)",
    )
    h_trace.add_argument("--symbol", required=True, help="Qualified symbol name")
    h_trace.add_argument(
        "--direction",
        default="both",
        choices=["inbound", "outbound", "both"],
        help="Trace direction (default both)",
    )
    h_trace.add_argument(
        "--depth",
        type=int,
        default=None,
        help="Trace depth (default 3, max 5)",
    )
    h_trace.set_defaults(handler=cmd_hetu_trace)

    h_impact = hetu_sub.add_parser(
        "impact",
        parents=[json_parent],
        help="Bounded change impact (ready, or dirty-only degraded vs clean receipt)",
    )
    h_impact.add_argument(
        "--since",
        default=None,
        help="Optional git ref; requires strict ready (not dirty-only degraded)",
    )
    h_impact.add_argument(
        "--depth",
        type=int,
        default=None,
        help="Impact depth (default 2, max 5)",
    )
    h_impact.set_defaults(handler=cmd_hetu_impact)

    h_arch = hetu_sub.add_parser(
        "architecture",
        parents=[json_parent],
        help="Bounded architecture clusters (requires ready index)",
    )
    h_arch.set_defaults(handler=cmd_hetu_architecture)

    h_reindex = hetu_sub.add_parser(
        "reindex",
        parents=[json_parent],
        help="Hetu reindex plan (dry-run) or confirmed apply",
    )
    h_reindex.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview reindex plan and plan_binding (default when --apply absent)",
    )
    h_reindex.add_argument(
        "--apply",
        action="store_true",
        help="Confirmed apply (requires --expect-plan-binding and --confirm-hetu-reindex-apply)",
    )
    h_reindex.add_argument(
        "--expect-plan-binding",
        default=None,
        help="Plan binding hash from prior dry-run (required for --apply)",
    )
    h_reindex.add_argument(
        "--confirm-hetu-reindex-apply",
        action="store_true",
        help="Explicit owner confirmation for reindex apply (no VIBE_HETU_* env dual gate)",
    )
    h_reindex.set_defaults(handler=cmd_hetu_reindex)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    as_json = bool(getattr(args, "json", False))

    handler: CommandHandler | None = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 2

    envelope = handler(args)
    return _emit(envelope, as_json=as_json)


if __name__ == "__main__":
    raise SystemExit(main())
