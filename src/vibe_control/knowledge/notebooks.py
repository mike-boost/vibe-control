"""Notebook allow-list resolution (no secret refs in committed config)."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vibe_control.config import ControlConfig, ConfigError


class NotebookError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


@dataclass
class NotebookEntry:
    alias: str
    display_name: str
    ref_env: str
    purpose: str | None
    allowed_operations: list[str]
    corpus_mode: str = "inherit"
    path_prefixes: list[str] = field(default_factory=list)
    include_extra: list[str] = field(default_factory=list)
    exclude_globs: list[str] = field(default_factory=list)

    def to_public_dict(self, *, ref_configured: bool) -> dict[str, Any]:
        return {
            "alias": self.alias,
            "display_name": self.display_name,
            "ref_env": self.ref_env,
            "purpose": self.purpose,
            "ref_configured": ref_configured,
            "allowed_operations": list(self.allowed_operations),
            "corpus_mode": self.corpus_mode,
            "path_prefixes": list(self.path_prefixes),
            "include_extra": list(self.include_extra),
            "exclude_globs": list(self.exclude_globs),
        }


def notebooks_section(config: ControlConfig) -> dict[str, Any]:
    notebooks = config.knowledge.get("notebooks")
    if not isinstance(notebooks, dict):
        raise NotebookError(
            "NOTEBOOKLM_NOT_CONFIGURED",
            "knowledge.notebooks is not configured",
            {"config_path": config.path.as_posix()},
        )
    return notebooks


def list_notebooks(config: ControlConfig, *, repo_root: Path) -> dict[str, Any]:
    notebooks = notebooks_section(config)
    default_alias = str(notebooks.get("default_alias") or "")
    allow_list_raw = notebooks.get("allow_list") or []
    allow_list: list[dict[str, Any]] = []
    for item in allow_list_raw:
        if not isinstance(item, dict):
            continue
        entry = _parse_entry(item)
        ref, _ = resolve_notebook_ref(config, entry.alias, repo_root=repo_root)
        allow_list.append(entry.to_public_dict(ref_configured=bool(ref)))
    return {"default_alias": default_alias, "allow_list": allow_list}


def get_notebook_entry(config: ControlConfig, alias: str) -> NotebookEntry:
    notebooks = notebooks_section(config)
    for item in notebooks.get("allow_list") or []:
        if isinstance(item, dict) and str(item.get("alias")) == alias:
            return _parse_entry(item)
    raise NotebookError(
        "NOTEBOOK_ALIAS_UNKNOWN",
        f"Notebook alias not in allow list: {alias}",
        {"alias": alias},
    )


def resolve_default_alias(config: ControlConfig, explicit: str | None = None) -> str:
    if explicit:
        return explicit
    notebooks = notebooks_section(config)
    alias = notebooks.get("default_alias")
    if not alias:
        raise NotebookError(
            "NOTEBOOKLM_NOT_CONFIGURED",
            "knowledge.notebooks.default_alias is missing",
        )
    return str(alias)


def allow_list_aliases(config: ControlConfig) -> list[str]:
    notebooks = notebooks_section(config)
    aliases: list[str] = []
    for item in notebooks.get("allow_list") or []:
        if isinstance(item, dict) and item.get("alias"):
            aliases.append(str(item["alias"]))
    return aliases


def resolve_operation_alias(config: ControlConfig, explicit: str | None = None) -> str:
    """Resolve notebook alias for knowledge ops (query/sync/inventory/…).

    - Exactly one allow_list entry: ``explicit`` may be omitted.
    - Two or more entries: ``explicit`` is required (no silent default_alias).
    """
    aliases = allow_list_aliases(config)
    if explicit:
        if explicit not in aliases:
            raise NotebookError(
                "NOTEBOOK_ALIAS_UNKNOWN",
                f"Notebook alias not in allow list: {explicit}",
                {"alias": explicit, "allow_list": aliases},
            )
        return explicit
    if len(aliases) == 1:
        return aliases[0]
    if len(aliases) == 0:
        raise NotebookError(
            "NOTEBOOKLM_NOT_CONFIGURED",
            "knowledge.notebooks.allow_list is empty",
        )
    raise NotebookError(
        "NOTEBOOK_ALIAS_REQUIRED",
        "Multiple notebooks configured; pass --notebook <alias>",
        {
            "allow_list": aliases,
            "default_alias": str(
                (config.knowledge.get("notebooks") or {}).get("default_alias") or ""
            ),
            "next_actions": [
                {
                    "code": "PASS_NOTEBOOK_ALIAS",
                    "command": "vibe knowledge <cmd> --notebook <alias> --json",
                    "mutation": False,
                    "reason": "allow_list has 2+ entries; --notebook is required",
                }
            ],
        },
    )


def resolve_notebook_ref(
    config: ControlConfig,
    alias: str,
    *,
    repo_root: Path,
) -> tuple[str | None, str | None]:
    """Return (ref, source_label) without exposing ref in caller logs unnecessarily."""
    entry = get_notebook_entry(config, alias)
    env_val = os.environ.get(entry.ref_env)
    if env_val and env_val.strip():
        return env_val.strip(), f"env:{entry.ref_env}"

    for rel in local_env_candidates():
        path = repo_root / rel
        if not path.is_file():
            continue
        loaded = _load_env_file(path)
        val = loaded.get(entry.ref_env)
        if val and val.strip():
            return val.strip(), f"file:{rel.as_posix()}"
    return None, None


def local_env_candidates() -> tuple[Path, ...]:
    """Preferred local env files; first match wins for a given key."""
    return (
        Path(".config") / ".env",
        Path(".env"),
        # Backward-compatible names from earlier Phase 4 drafts
        Path(".config") / "vibe-control.local.env",
        Path(".vibe") / "local.env",
    )


def notebook_status(
    config: ControlConfig,
    *,
    repo_root: Path,
    alias: str | None = None,
) -> dict[str, Any]:
    resolved_alias = resolve_default_alias(config, alias)
    entry = get_notebook_entry(config, resolved_alias)
    ref, source = resolve_notebook_ref(config, resolved_alias, repo_root=repo_root)
    return {
        "alias": entry.alias,
        "display_name": entry.display_name,
        "ref_env": entry.ref_env,
        "ref_configured": bool(ref),
        "ref_source": source,
        "ref_fingerprint": _fingerprint(ref) if ref else None,
        "allowed_operations": list(entry.allowed_operations),
        "purpose": entry.purpose,
        "next_actions": []
        if ref
        else [
            f"export {entry.ref_env}=<notebook-id-or-ref>",
            (
                "or: mkdir -p .config && "
                f"printf '{entry.ref_env}=<notebook-id-or-ref>\\n' > .config/.env"
            ),
        ],
    }


def require_notebook_ref(
    config: ControlConfig,
    *,
    repo_root: Path,
    alias: str | None = None,
    require_explicit_when_multi: bool = True,
) -> tuple[NotebookEntry, str]:
    if require_explicit_when_multi:
        resolved_alias = resolve_operation_alias(config, alias)
    else:
        resolved_alias = resolve_default_alias(config, alias)
    entry = get_notebook_entry(config, resolved_alias)
    ref, _ = resolve_notebook_ref(config, resolved_alias, repo_root=repo_root)
    if not ref:
        raise NotebookError(
            "NOTEBOOKLM_NOT_CONFIGURED",
            f"Notebook ref for alias {resolved_alias!r} is not configured",
            {
                "alias": resolved_alias,
                "ref_env": entry.ref_env,
                "next_actions": [
                    f"export {entry.ref_env}=<notebook-id-or-ref>",
                    f"or write ignored file .config/.env with {entry.ref_env}=...",
                ],
            },
        )
    return entry, ref


def set_default_alias_preview(config: ControlConfig, alias: str) -> dict[str, Any]:
    entry = get_notebook_entry(config, alias)
    current = str((config.knowledge.get("notebooks") or {}).get("default_alias") or "")
    return {
        "current_default_alias": current,
        "requested_default_alias": entry.alias,
        "would_change": current != entry.alias,
        "config_path": config.path.as_posix(),
    }


def set_default_alias(config: ControlConfig, alias: str) -> dict[str, Any]:
    preview = set_default_alias_preview(config, alias)
    if not preview["would_change"]:
        return {**preview, "written": False}
    raw = dict(config.raw)
    knowledge = dict(raw.get("knowledge") or {})
    notebooks = dict(knowledge.get("notebooks") or {})
    notebooks["default_alias"] = alias
    knowledge["notebooks"] = notebooks
    raw["knowledge"] = knowledge
    text = _dump_yaml(raw)
    config.path.write_text(text, encoding="utf-8")
    return {**preview, "written": True}


def _parse_entry(item: dict[str, Any]) -> NotebookEntry:
    mode = str(item.get("corpus_mode") or "inherit").strip().lower() or "inherit"
    return NotebookEntry(
        alias=str(item["alias"]),
        display_name=str(item.get("display_name") or item["alias"]),
        ref_env=str(item.get("ref_env") or f"NOTEBOOKLM_NOTEBOOK_{item['alias']}"),
        purpose=None if item.get("purpose") is None else str(item.get("purpose")),
        allowed_operations=[str(x) for x in (item.get("allowed_operations") or [])],
        corpus_mode=mode,
        path_prefixes=[str(x) for x in (item.get("path_prefixes") or [])],
        include_extra=[str(x) for x in (item.get("include_extra") or [])],
        exclude_globs=[str(x) for x in (item.get("exclude_globs") or [])],
    )


def _load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip("'").strip('"')
    return values


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _dump_yaml(data: dict[str, Any]) -> str:
    import yaml

    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


_ = ConfigError
_ = re
