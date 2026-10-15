"""Load and validate Vibe Control config.

Discovery order:
1. explicit --config path
2. VIBE_CONTROL_CONFIG env
3. .config/vibe-control.yaml (primary)
4. .vibe/control.yaml (legacy)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

PRIMARY_CONTROL_RELATIVE = Path(".config") / "vibe-control.yaml"
LEGACY_CONTROL_RELATIVE = Path(".vibe") / "control.yaml"
# Backward-compatible alias used by older call sites / doctor messaging
CONTROL_RELATIVE_PATH = PRIMARY_CONTROL_RELATIVE


class ConfigError(Exception):
    """Raised when config cannot be loaded or is invalid."""

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


# Hetu config (§3 of hetu-runtime-mvp-spec). Parsing does not authorize enablement.
HETU_ALLOWED_PROVIDERS: frozenset[str] = frozenset({"codebase_memory", "fake"})
HETU_ALLOWED_FRESHNESS_POLICIES: frozenset[str] = frozenset({"strict"})
HETU_ALLOWED_INDEX_MODES: frozenset[str] = frozenset({"fast"})
HETU_SEARCH_LIMIT_RANGE = (1, 50)
HETU_TRACE_DEPTH_RANGE = (1, 5)
HETU_IMPACT_DEPTH_RANGE = (1, 5)
HETU_QUERY_TIMEOUT_RANGE = (5, 120)
# Spec default 600; MVP safety clamp (not in YAML comments) for unsafe timeouts.
HETU_REINDEX_TIMEOUT_RANGE = (30, 3600)


@dataclass(frozen=True)
class HetuCodebaseMemoryConfig:
    binary: str = "codebase-memory-mcp"
    project: str | None = None
    index_mode: str = "fast"
    search_limit: int = 20
    trace_depth: int = 3
    impact_depth: int = 2
    query_timeout_sec: int = 30
    reindex_timeout_sec: int = 600

    def to_dict(self) -> dict[str, Any]:
        return {
            "binary": self.binary,
            "project": self.project,
            "index_mode": self.index_mode,
            "search_limit": self.search_limit,
            "trace_depth": self.trace_depth,
            "impact_depth": self.impact_depth,
            "query_timeout_sec": self.query_timeout_sec,
            "reindex_timeout_sec": self.reindex_timeout_sec,
        }


@dataclass(frozen=True)
class HetuConfig:
    provider: str = "codebase_memory"
    freshness_policy: str = "strict"
    codebase_memory: HetuCodebaseMemoryConfig = field(
        default_factory=HetuCodebaseMemoryConfig
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "freshness_policy": self.freshness_policy,
            "codebase_memory": self.codebase_memory.to_dict(),
        }


DEFAULT_HETU_CONFIG = HetuConfig()


@dataclass
class ControlConfig:
    raw: dict[str, Any]
    path: Path
    project_id: str
    project_name: str | None = None
    knowledge: dict[str, Any] = field(default_factory=dict)
    specs: dict[str, Any] = field(default_factory=dict)
    tasks: dict[str, Any] = field(default_factory=dict)
    hetu: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return dict(self.raw)


def template_path() -> Path:
    return Path(__file__).resolve().parent / "templates" / "control.yaml"


def primary_control_path(repo_root: Path | None = None) -> Path:
    root = repo_root if repo_root is not None else Path.cwd()
    return root / PRIMARY_CONTROL_RELATIVE


def legacy_control_path(repo_root: Path | None = None) -> Path:
    root = repo_root if repo_root is not None else Path.cwd()
    return root / LEGACY_CONTROL_RELATIVE


def control_path(repo_root: Path | None = None) -> Path:
    """Preferred display/expected path (primary)."""
    return primary_control_path(repo_root)


def find_project_root(start: Path | None = None) -> Path:
    """Nearest ancestor with a Vibe config file, else git root, else cwd."""
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / PRIMARY_CONTROL_RELATIVE).is_file():
            return candidate
        if (candidate / LEGACY_CONTROL_RELATIVE).is_file():
            return candidate
    from vibe_control.git_repo import find_git_root

    return find_git_root(current) or current


def discover_config_path(
    *,
    repo_root: Path | None = None,
    explicit: str | Path | None = None,
) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get("VIBE_CONTROL_CONFIG")
    if env:
        return Path(env).expanduser().resolve()
    root = (repo_root or find_project_root()).resolve()
    primary = root / PRIMARY_CONTROL_RELATIVE
    if primary.is_file():
        return primary
    legacy = root / LEGACY_CONTROL_RELATIVE
    if legacy.is_file():
        return legacy
    raise ConfigError(
        "CONFIG_NOT_FOUND",
        (
            f"Config not found. Looked for {primary.as_posix()} "
            f"and {legacy.as_posix()}"
        ),
        {
            "primary_path": primary.as_posix(),
            "legacy_path": legacy.as_posix(),
            "template_path": template_path().as_posix(),
            "env_var": "VIBE_CONTROL_CONFIG",
        },
    )


def load_yaml_file(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_config(
    repo_root: Path | None = None,
    *,
    config_path: str | Path | None = None,
) -> ControlConfig:
    try:
        path = discover_config_path(repo_root=repo_root, explicit=config_path)
    except ConfigError:
        raise
    if not path.is_file():
        raise ConfigError(
            "CONFIG_NOT_FOUND",
            f"Config not found at {path.as_posix()}",
            {
                "expected_path": path.as_posix(),
                "template_path": template_path().as_posix(),
            },
        )

    raw = load_yaml_file(path)
    if not isinstance(raw, dict):
        raise ConfigError(
            "CONFIG_INVALID",
            "Config root must be a mapping",
            {"path": path.as_posix()},
        )

    project = raw.get("project")
    if not isinstance(project, dict) or not project.get("id"):
        raise ConfigError(
            "CONFIG_INVALID",
            "Config requires project.id",
            {"path": path.as_posix()},
        )

    return ControlConfig(
        raw=raw,
        path=path,
        project_id=str(project["id"]),
        project_name=project.get("name"),
        knowledge=raw.get("knowledge") if isinstance(raw.get("knowledge"), dict) else {},
        specs=raw.get("specs") if isinstance(raw.get("specs"), dict) else {},
        tasks=raw.get("tasks") if isinstance(raw.get("tasks"), dict) else {},
        hetu=raw.get("hetu") if isinstance(raw.get("hetu"), dict) else {},
    )


REQUIRED_TOP_LEVEL = ("project", "knowledge", "specs", "tasks")
REQUIRED_PROJECT_FIELDS = ("id", "name")
REQUIRED_KNOWLEDGE_FIELDS = (
    "provider",
    "fallback_provider",
    "max_sources",
    "warn_sources",
    "authoritative_statuses",
)
REQUIRED_SPECS_FIELDS = ("registry", "required_fields")
REQUIRED_TASKS_FIELDS = ("provider",)


def validate_config_dict(raw: dict[str, Any]) -> list[str]:
    """Return a list of validation error messages (empty means valid)."""
    errors: list[str] = []

    for key in REQUIRED_TOP_LEVEL:
        if key not in raw or not isinstance(raw[key], dict):
            errors.append(f"missing or invalid top-level section: {key}")

    project = raw.get("project")
    if isinstance(project, dict):
        for field_name in REQUIRED_PROJECT_FIELDS:
            if not project.get(field_name):
                errors.append(f"project.{field_name} is required")

    knowledge = raw.get("knowledge")
    if isinstance(knowledge, dict):
        for field_name in REQUIRED_KNOWLEDGE_FIELDS:
            if field_name not in knowledge:
                errors.append(f"knowledge.{field_name} is required")
        max_sources = knowledge.get("max_sources")
        warn_sources = knowledge.get("warn_sources")
        if isinstance(max_sources, int) and isinstance(warn_sources, int):
            if warn_sources > max_sources:
                errors.append("knowledge.warn_sources must be <= knowledge.max_sources")
        statuses = knowledge.get("authoritative_statuses")
        if statuses is not None and not isinstance(statuses, list):
            errors.append("knowledge.authoritative_statuses must be a list")
        provider = knowledge.get("provider")
        if provider is not None:
            provider_s = str(provider).strip().lower()
            if provider_s not in {"local_fts", "notebooklm"}:
                errors.append(
                    "knowledge.provider must be 'local_fts' or 'notebooklm'"
                )
        local_fts = knowledge.get("local_fts")
        if local_fts is not None and not isinstance(local_fts, dict):
            errors.append("knowledge.local_fts must be a mapping when set")
        elif isinstance(local_fts, dict) and "top_k" in local_fts:
            try:
                top_k = int(local_fts.get("top_k"))
                if top_k < 1 or top_k > 20:
                    errors.append("knowledge.local_fts.top_k must be between 1 and 20")
            except (TypeError, ValueError):
                errors.append("knowledge.local_fts.top_k must be an integer")
        notebooks = knowledge.get("notebooks")
        if notebooks is not None:
            if not isinstance(notebooks, dict):
                errors.append("knowledge.notebooks must be a mapping")
            else:
                default_alias = notebooks.get("default_alias")
                allow_list = notebooks.get("allow_list")
                if not default_alias:
                    errors.append("knowledge.notebooks.default_alias is required when notebooks is set")
                if not isinstance(allow_list, list) or not allow_list:
                    errors.append("knowledge.notebooks.allow_list must be a non-empty list")
                elif isinstance(allow_list, list):
                    aliases = []
                    for idx, item in enumerate(allow_list):
                        if not isinstance(item, dict) or not item.get("alias"):
                            errors.append(f"knowledge.notebooks.allow_list[{idx}] requires alias")
                        else:
                            aliases.append(str(item["alias"]))
                    if default_alias and aliases and str(default_alias) not in aliases:
                        errors.append(
                            "knowledge.notebooks.default_alias must exist in allow_list"
                        )
                    for idx, item in enumerate(allow_list):
                        if not isinstance(item, dict):
                            continue
                        mode = item.get("corpus_mode")
                        if mode is not None:
                            mode_s = str(mode).strip().lower()
                            if mode_s not in ("inherit", "replace"):
                                errors.append(
                                    f"knowledge.notebooks.allow_list[{idx}].corpus_mode "
                                    "must be 'inherit' or 'replace'"
                                )
                        for list_field in ("path_prefixes", "include_extra", "exclude_globs"):
                            if list_field in item and not isinstance(item.get(list_field), list):
                                errors.append(
                                    f"knowledge.notebooks.allow_list[{idx}].{list_field} "
                                    "must be a list"
                                )

    specs = raw.get("specs")
    if isinstance(specs, dict):
        for field_name in REQUIRED_SPECS_FIELDS:
            if field_name not in specs:
                errors.append(f"specs.{field_name} is required")
        required_fields = specs.get("required_fields")
        if required_fields is not None and not isinstance(required_fields, list):
            errors.append("specs.required_fields must be a list")

    tasks = raw.get("tasks")
    if isinstance(tasks, dict):
        for field_name in REQUIRED_TASKS_FIELDS:
            if field_name not in tasks:
                errors.append(f"tasks.{field_name} is required")

    if "hetu" in raw:
        errors.extend(validate_hetu_config_dict(raw.get("hetu")))

    return errors


def _validate_int_in_range(
    value: Any,
    *,
    path: str,
    lo: int,
    hi: int,
    errors: list[str],
) -> None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        errors.append(f"{path} must be an integer")
        return
    if number < lo or number > hi:
        errors.append(f"{path} must be between {lo} and {hi}")


def validate_hetu_config_dict(raw: Any) -> list[str]:
    """Validate optional top-level ``hetu:`` mapping. Empty/absent → ok (defaults).

    Does not authorize ``components.hetu.enabled`` or catalog support.
    """
    errors: list[str] = []
    if raw is None:
        return errors
    if not isinstance(raw, dict):
        errors.append("hetu must be a mapping when set")
        return errors
    if not raw:
        return errors

    provider = raw.get("provider")
    if provider is not None:
        provider_s = str(provider).strip().lower()
        if provider_s not in HETU_ALLOWED_PROVIDERS:
            errors.append(
                "hetu.provider must be 'codebase_memory' (or test-only 'fake')"
            )

    freshness = raw.get("freshness_policy")
    if freshness is not None:
        freshness_s = str(freshness).strip().lower()
        if freshness_s not in HETU_ALLOWED_FRESHNESS_POLICIES:
            errors.append("hetu.freshness_policy must be 'strict'")

    cm = raw.get("codebase_memory")
    if cm is None:
        return errors
    if not isinstance(cm, dict):
        errors.append("hetu.codebase_memory must be a mapping when set")
        return errors

    if "binary" in cm and (cm.get("binary") is None or str(cm.get("binary")).strip() == ""):
        errors.append("hetu.codebase_memory.binary must be a non-empty string")

    if "project" in cm and cm.get("project") is not None:
        if not isinstance(cm.get("project"), str) or not str(cm.get("project")).strip():
            errors.append("hetu.codebase_memory.project must be a non-empty string or null")

    index_mode = cm.get("index_mode")
    if index_mode is not None:
        mode_s = str(index_mode).strip().lower()
        if mode_s not in HETU_ALLOWED_INDEX_MODES:
            errors.append("hetu.codebase_memory.index_mode must be 'fast'")

    if "search_limit" in cm:
        _validate_int_in_range(
            cm.get("search_limit"),
            path="hetu.codebase_memory.search_limit",
            lo=HETU_SEARCH_LIMIT_RANGE[0],
            hi=HETU_SEARCH_LIMIT_RANGE[1],
            errors=errors,
        )
    if "trace_depth" in cm:
        _validate_int_in_range(
            cm.get("trace_depth"),
            path="hetu.codebase_memory.trace_depth",
            lo=HETU_TRACE_DEPTH_RANGE[0],
            hi=HETU_TRACE_DEPTH_RANGE[1],
            errors=errors,
        )
    if "impact_depth" in cm:
        _validate_int_in_range(
            cm.get("impact_depth"),
            path="hetu.codebase_memory.impact_depth",
            lo=HETU_IMPACT_DEPTH_RANGE[0],
            hi=HETU_IMPACT_DEPTH_RANGE[1],
            errors=errors,
        )
    if "query_timeout_sec" in cm:
        _validate_int_in_range(
            cm.get("query_timeout_sec"),
            path="hetu.codebase_memory.query_timeout_sec",
            lo=HETU_QUERY_TIMEOUT_RANGE[0],
            hi=HETU_QUERY_TIMEOUT_RANGE[1],
            errors=errors,
        )
    if "reindex_timeout_sec" in cm:
        _validate_int_in_range(
            cm.get("reindex_timeout_sec"),
            path="hetu.codebase_memory.reindex_timeout_sec",
            lo=HETU_REINDEX_TIMEOUT_RANGE[0],
            hi=HETU_REINDEX_TIMEOUT_RANGE[1],
            errors=errors,
        )

    return errors


def parse_hetu_config(raw: Any = None) -> HetuConfig:
    """Parse Hetu config with exact defaults. Raises ConfigError on invalid input."""
    errors = validate_hetu_config_dict(raw)
    if errors:
        raise ConfigError(
            "CONFIG_INVALID",
            "; ".join(errors),
            {"errors": errors},
        )

    data = raw if isinstance(raw, dict) else {}
    provider = str(data.get("provider") or DEFAULT_HETU_CONFIG.provider).strip().lower()
    freshness = str(
        data.get("freshness_policy") or DEFAULT_HETU_CONFIG.freshness_policy
    ).strip().lower()

    cm_raw = data.get("codebase_memory") if isinstance(data.get("codebase_memory"), dict) else {}
    defaults = DEFAULT_HETU_CONFIG.codebase_memory

    project_val = cm_raw.get("project", defaults.project)
    if project_val is not None:
        project_val = str(project_val).strip() or None

    cm = HetuCodebaseMemoryConfig(
        binary=str(cm_raw.get("binary") or defaults.binary).strip() or defaults.binary,
        project=project_val,
        index_mode=str(cm_raw.get("index_mode") or defaults.index_mode).strip().lower(),
        search_limit=int(cm_raw["search_limit"])
        if "search_limit" in cm_raw
        else defaults.search_limit,
        trace_depth=int(cm_raw["trace_depth"])
        if "trace_depth" in cm_raw
        else defaults.trace_depth,
        impact_depth=int(cm_raw["impact_depth"])
        if "impact_depth" in cm_raw
        else defaults.impact_depth,
        query_timeout_sec=int(cm_raw["query_timeout_sec"])
        if "query_timeout_sec" in cm_raw
        else defaults.query_timeout_sec,
        reindex_timeout_sec=int(cm_raw["reindex_timeout_sec"])
        if "reindex_timeout_sec" in cm_raw
        else defaults.reindex_timeout_sec,
    )
    return HetuConfig(
        provider=provider,
        freshness_policy=freshness,
        codebase_memory=cm,
    )


def validate_config(config: ControlConfig) -> list[str]:
    return validate_config_dict(config.raw)


def load_template() -> dict[str, Any]:
    data = load_yaml_file(template_path())
    if not isinstance(data, dict):
        raise ConfigError("TEMPLATE_INVALID", "Template root must be a mapping")
    return data
