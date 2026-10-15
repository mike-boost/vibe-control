"""Purge stale local_fts indexes — prevent garbage without a full GC product.

Policy (v1):
- Expected scopes = current config corpus scopes (per allow_list alias, or global).
- When knowledge.provider != local_fts, expected is empty → all on-disk local_fts
  dirs for this project are orphans (leftover after switching away).
- Default apply deletes: orphan scope dirs + ``*.sqlite.tmp`` only.
- ``--all`` deletes the entire project ``local_fts/`` tree (requires ``--confirm-all``).
- Never auto-deletes during sync; sync may *report* orphans + next_action.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vibe_control.config import ControlConfig
from vibe_control.json_envelope import next_action
from vibe_control.knowledge.corpus import resolve_corpus_for_target
from vibe_control.knowledge.local_fts.fingerprint import scope_key_for_fs
from vibe_control.knowledge.notebooks import allow_list_aliases
from vibe_control.knowledge.receipt_scope import _state_root


@dataclass
class ScopeEntry:
    scope_key: str
    path: str
    bytes: int
    kind: str  # active | orphan | tmp
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope_key": self.scope_key,
            "path": self.path,
            "bytes": self.bytes,
            "kind": self.kind,
            "note": self.note,
        }


@dataclass
class PurgePlan:
    project_id: str
    local_fts_root: str
    provider: str
    expected_scope_keys: list[str] = field(default_factory=list)
    entries: list[ScopeEntry] = field(default_factory=list)
    mode: str = "orphans"  # orphans | all
    total_orphan_bytes: int = 0
    total_tmp_bytes: int = 0
    total_active_bytes: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "local_fts_root": self.local_fts_root,
            "provider": self.provider,
            "expected_scope_keys": list(self.expected_scope_keys),
            "mode": self.mode,
            "entries": [e.to_dict() for e in self.entries],
            "total_orphan_bytes": self.total_orphan_bytes,
            "total_tmp_bytes": self.total_tmp_bytes,
            "total_active_bytes": self.total_active_bytes,
            "delete_count": sum(
                1 for e in self.entries if e.kind in {"orphan", "tmp"} or self.mode == "all"
            ),
        }


def local_fts_root(project_id: str, *, home: Path | None = None) -> Path:
    return _state_root(home) / project_id / "local_fts"


def _dir_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    total = 0
    for child in path.rglob("*"):
        if child.is_file():
            try:
                total += child.stat().st_size
            except OSError:
                continue
    return total


def expected_scope_keys(
    config: ControlConfig,
    *,
    repo_root: Path,
) -> list[str]:
    """Scopes that current config would rebuild for."""
    active = str(config.knowledge.get("provider") or "").strip().lower()
    if active != "local_fts":
        return []

    notebooks = config.knowledge.get("notebooks")
    aliases: list[str] = []
    if isinstance(notebooks, dict):
        aliases = allow_list_aliases(config)

    keys: list[str] = []
    if not aliases:
        _corpus, scope = resolve_corpus_for_target(
            config, notebook_alias=None, repo_root=repo_root
        )
        keys.append(scope_key_for_fs(scope))
        return keys

    seen: set[str] = set()
    for alias in aliases:
        _corpus, scope = resolve_corpus_for_target(
            config, notebook_alias=alias, repo_root=repo_root
        )
        key = scope_key_for_fs(scope)
        if key not in seen:
            seen.add(key)
            keys.append(key)
    return keys


def build_purge_plan(
    config: ControlConfig,
    *,
    repo_root: Path,
    home: Path | None = None,
    purge_all: bool = False,
) -> PurgePlan:
    root = local_fts_root(config.project_id, home=home)
    provider = str(config.knowledge.get("provider") or "").strip().lower()
    expected = expected_scope_keys(config, repo_root=repo_root)
    expected_set = set(expected)
    entries: list[ScopeEntry] = []

    if root.is_dir():
        for child in sorted(root.iterdir(), key=lambda p: p.name):
            if child.name.endswith(".sqlite.tmp") or child.suffix == ".tmp":
                entries.append(
                    ScopeEntry(
                        scope_key=child.name,
                        path=str(child),
                        bytes=_dir_bytes(child),
                        kind="tmp",
                        note="leftover temp from interrupted rebuild",
                    )
                )
                continue
            if not child.is_dir():
                # stray files under local_fts/
                if child.name.endswith(".tmp") or ".sqlite.tmp" in child.name:
                    kind = "tmp"
                else:
                    kind = "orphan"
                entries.append(
                    ScopeEntry(
                        scope_key=child.name,
                        path=str(child),
                        bytes=_dir_bytes(child),
                        kind=kind,
                        note="stray file under local_fts",
                    )
                )
                continue

            # Also catch tmp sqlite inside scope dirs
            for tmp in child.glob("*.sqlite.tmp"):
                entries.append(
                    ScopeEntry(
                        scope_key=f"{child.name}/{tmp.name}",
                        path=str(tmp),
                        bytes=_dir_bytes(tmp),
                        kind="tmp",
                        note="leftover temp from interrupted rebuild",
                    )
                )

            kind = "active" if child.name in expected_set else "orphan"
            note = (
                "current config scope"
                if kind == "active"
                else (
                    "not in current expected scopes "
                    "(removed notebook/selector, or provider is not local_fts)"
                )
            )
            entries.append(
                ScopeEntry(
                    scope_key=child.name,
                    path=str(child),
                    bytes=_dir_bytes(child),
                    kind=kind,
                    note=note,
                )
            )

    plan = PurgePlan(
        project_id=config.project_id,
        local_fts_root=str(root),
        provider=provider or "(unset)",
        expected_scope_keys=expected,
        entries=entries,
        mode="all" if purge_all else "orphans",
        total_orphan_bytes=sum(e.bytes for e in entries if e.kind == "orphan"),
        total_tmp_bytes=sum(e.bytes for e in entries if e.kind == "tmp"),
        total_active_bytes=sum(e.bytes for e in entries if e.kind == "active"),
    )
    return plan


def apply_purge_plan(plan: PurgePlan, *, purge_all: bool = False) -> dict[str, Any]:
    deleted: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    if purge_all:
        root = Path(plan.local_fts_root)
        if root.exists():
            try:
                bytes_before = _dir_bytes(root)
                shutil.rmtree(root)
                deleted.append(
                    {
                        "scope_key": "(all)",
                        "path": str(root),
                        "bytes": bytes_before,
                        "kind": "all",
                    }
                )
            except OSError as exc:
                errors.append({"path": str(root), "error": str(exc)})
        return {"deleted": deleted, "errors": errors, "mode": "all"}

    # Delete orphans and tmp only. Sort so files inside dirs go first if both listed.
    targets = [e for e in plan.entries if e.kind in {"orphan", "tmp"}]
    targets.sort(key=lambda e: len(Path(e.path).parts), reverse=True)
    for entry in targets:
        path = Path(entry.path)
        try:
            if path.is_dir():
                shutil.rmtree(path)
            elif path.exists():
                path.unlink()
            deleted.append(entry.to_dict())
        except OSError as exc:
            errors.append({"path": str(path), "error": str(exc)})
    return {"deleted": deleted, "errors": errors, "mode": "orphans"}


def orphan_report_for_status(
    config: ControlConfig,
    *,
    repo_root: Path,
    home: Path | None = None,
) -> dict[str, Any]:
    """Readonly orphan summary for status/sync envelopes."""
    plan = build_purge_plan(config, repo_root=repo_root, home=home, purge_all=False)
    orphans = [e for e in plan.entries if e.kind in {"orphan", "tmp"}]
    out: dict[str, Any] = {
        "orphan_count": sum(1 for e in orphans if e.kind == "orphan"),
        "tmp_count": sum(1 for e in orphans if e.kind == "tmp"),
        "orphan_bytes": plan.total_orphan_bytes + plan.total_tmp_bytes,
        "active_bytes": plan.total_active_bytes,
        "local_fts_root": plan.local_fts_root,
    }
    if orphans:
        out["next_actions"] = [
            next_action(
                code="LOCAL_FTS_PURGE_ORPHANS",
                command="vibe knowledge fts-purge --dry-run --json",
                mutation=False,
                reason="Stale local_fts index dirs/tmp found; review then purge",
            )
        ]
    return out


def run_fts_purge(
    *,
    repo_root: Path,
    apply: bool,
    purge_all: bool = False,
    confirm_all: bool = False,
    home: Path | None = None,
) -> dict[str, Any]:
    from vibe_control.config import ConfigError, load_config
    from vibe_control.json_envelope import failure_envelope, success_envelope

    try:
        config = load_config(repo_root)
    except ConfigError as exc:
        return failure_envelope(
            command="vibe knowledge fts-purge",
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )

    if purge_all and apply and not confirm_all:
        return failure_envelope(
            command="vibe knowledge fts-purge",
            code="FTS_PURGE_ALL_REQUIRES_CONFIRM",
            message="--all --apply requires --confirm-all (deletes every local_fts index for project)",
            project_id=config.project_id,
            next_actions=[
                next_action(
                    code="FTS_PURGE_ALL_REQUIRES_CONFIRM",
                    command="vibe knowledge fts-purge --all --apply --confirm-all --json",
                    mutation=True,
                    reason="Explicit confirm for full project local_fts wipe",
                ),
                next_action(
                    code="FTS_PURGE_ORPHANS_ONLY",
                    command="vibe knowledge fts-purge --dry-run --json",
                    mutation=False,
                    reason="Prefer orphan/tmp-only purge unless full wipe is intended",
                ),
            ],
        )

    plan = build_purge_plan(
        config, repo_root=repo_root, home=home, purge_all=purge_all
    )
    data: dict[str, Any] = {
        "provider": plan.provider,
        "dry_run": not apply,
        "plan": plan.to_dict(),
    }

    if not apply:
        data["mutation"] = False
        next_actions = []
        if any(e.kind in {"orphan", "tmp"} for e in plan.entries) or purge_all:
            cmd = "vibe knowledge fts-purge --apply --json"
            if purge_all:
                cmd = "vibe knowledge fts-purge --all --apply --confirm-all --json"
            next_actions.append(
                next_action(
                    code="LOCAL_FTS_PURGE_APPLY",
                    command=cmd,
                    mutation=True,
                    reason="Apply purge after reviewing plan",
                )
            )
        env = success_envelope(
            command="vibe knowledge fts-purge",
            project_id=config.project_id,
            data=data,
            next_actions=next_actions,
        )
        env["mutation"] = False
        return env

    result = apply_purge_plan(plan, purge_all=purge_all)
    data["mutation"] = True
    data["result"] = result
    data["ok"] = not result.get("errors")
    env = success_envelope(
        command="vibe knowledge fts-purge",
        project_id=config.project_id,
        data=data,
        warnings=(
            [f"purge error: {err}" for err in (result.get("errors") or [])]
            if result.get("errors")
            else []
        ),
    )
    env["mutation"] = True
    env["ok"] = bool(data["ok"])
    return env
