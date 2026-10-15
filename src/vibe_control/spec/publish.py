"""Spec validate + publish orchestration (Phase 9), wired to Phase 8 sync."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Callable

from vibe_control.config import load_config
from vibe_control.knowledge.corpus import build_desired_corpus
from vibe_control.knowledge.managed_names import content_sha256_file
from vibe_control.knowledge.snapshot import SnapshotItem, build_desired_snapshot

# Re-exported for monkeypatch in tests
from vibe_control.knowledge.phase8_apply import apply_forward_sync  # noqa: F401
from vibe_control.knowledge.provider_target import ProviderTarget
from vibe_control.knowledge.remote_ack import FakeAckStore
from vibe_control.spec.registry import load_registry


SPEC_ID_DUPLICATE = "SPEC_ID_DUPLICATE"
CONFIG_FILE_CANNOT_BE_SYNCED = "CONFIG_FILE_CANNOT_BE_SYNCED"
SPEC_PATH_NOT_CANONICAL = "SPEC_PATH_NOT_CANONICAL"
SPEC_NOT_IN_REGISTRY = "SPEC_NOT_IN_REGISTRY"
SPEC_FORBIDDEN_PATH = "SPEC_FORBIDDEN_PATH"
DIRTY_WORKTREE = "DIRTY_WORKTREE"
UNRELATED_DIRTY_WORKTREE = "UNRELATED_DIRTY_WORKTREE"
UNPUSHED_REF = "UNPUSHED_REF"
PUBLISH_REQUIRES_PUSHED_REF = "PUBLISH_REQUIRES_PUSHED_REF"

FORBIDDEN_PREFIXES = (
    "docs/program/plans/",
    "docs/phases/",
    "runtime/",
    "acceptance/",
    ".beads/",
    "tests/",
    "scripts/",
)

CONFIG_NAMES = (
    ".config/vibe-control.yaml",
    ".vibe/control.yaml",
)


def _norm(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def _is_canonical(path: str) -> bool:
    text = path.replace("\\", "/")
    if text.startswith("./") or "/../" in f"/{text}/" or text.startswith("../"):
        return False
    if "//" in text:
        return False
    return text == _norm(text) and not text.endswith("/")


def _git(root: Path, *args: str, runner: Callable | None = None) -> tuple[int, str, str]:
    cmd = ["git", *args]
    run = runner or subprocess.run
    proc = run(cmd, cwd=root, capture_output=True, text=True, check=False)
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def validate_spec_path(repo_root: Path, path: str) -> dict[str, Any]:
    rel = path.replace("\\", "/")
    if any(rel == name or rel.endswith("/" + name.split("/")[-1]) for name in CONFIG_NAMES) or rel in CONFIG_NAMES:
        return {
            "ok": False,
            "code": CONFIG_FILE_CANNOT_BE_SYNCED,
            "message": "Config files select sources and cannot be published as sync content",
            "path": rel,
        }
    if rel in CONFIG_NAMES or rel.endswith("vibe-control.yaml") or rel.endswith("control.yaml"):
        if ".config/" in rel or rel.startswith(".vibe/"):
            return {
                "ok": False,
                "code": CONFIG_FILE_CANNOT_BE_SYNCED,
                "message": "Config files cannot be synced as knowledge content",
                "path": rel,
            }

    if not _is_canonical(rel):
        return {
            "ok": False,
            "code": SPEC_PATH_NOT_CANONICAL,
            "message": "Spec path must be canonical (no ./ or .. segments)",
            "path": rel,
        }

    normalized = _norm(rel)
    for prefix in FORBIDDEN_PREFIXES:
        if normalized.startswith(prefix) or f"/{prefix}" in f"/{normalized}":
            return {
                "ok": False,
                "code": SPEC_FORBIDDEN_PATH,
                "message": f"Path kind is not publishable as sync content by default: {normalized}",
                "path": normalized,
            }

    config = load_config(repo_root)
    registry_rel = config.specs.get("registry") or "docs/project/spec-registry.yml"
    parsed = load_registry(repo_root / str(registry_rel))
    if any("duplicate id" in e for e in parsed.errors):
        # If path maps to a duplicated id, fail specifically
        matches = [e for e in parsed.entries if e.path and _norm(e.path) == normalized]
        if matches or any(True for e in parsed.errors if "duplicate" in e):
            return {
                "ok": False,
                "code": SPEC_ID_DUPLICATE,
                "message": "; ".join(parsed.errors),
                "path": normalized,
            }

    # Detect duplicate ids globally
    ids = [e.id for e in parsed.entries]
    if len(ids) != len(set(ids)):
        return {
            "ok": False,
            "code": SPEC_ID_DUPLICATE,
            "message": "Duplicate spec id in registry",
            "path": normalized,
        }

    file_path = repo_root / normalized
    if not file_path.is_file():
        return {
            "ok": False,
            "code": "SPEC_PATH_MISSING",
            "message": f"Spec file not found: {normalized}",
            "path": normalized,
        }

    entry = next((e for e in parsed.entries if e.path and _norm(e.path) == normalized), None)
    if entry is None:
        return {
            "ok": False,
            "code": SPEC_NOT_IN_REGISTRY,
            "message": "Spec path is not present in registry",
            "path": normalized,
        }

    required = list(config.specs.get("required_fields") or ["id", "status", "path"])
    for field in required:
        if field == "id" and not entry.id:
            return {"ok": False, "code": "SPEC_REQUIRED_FIELD", "message": "missing id"}
        if field == "status" and not entry.status:
            return {"ok": False, "code": "SPEC_REQUIRED_FIELD", "message": "missing status"}
        if field == "path" and not entry.path:
            return {"ok": False, "code": "SPEC_REQUIRED_FIELD", "message": "missing path"}

    sha = content_sha256_file(file_path)
    return {
        "ok": True,
        "spec_id": entry.id,
        "path": normalized,
        "status": entry.status,
        "title": entry.title,
        "content_sha256": SnapshotItem._norm_sha(sha),
    }


def _dirty_paths(repo_root: Path, runner: Callable | None = None) -> list[str]:
    code, out, _ = _git(repo_root, "status", "--porcelain", runner=runner)
    if code != 0:
        return ["?"]
    paths = []
    for line in out.splitlines():
        if not line.strip():
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        paths.append(path.replace("\\", "/"))
    return paths


def _upstream_ref(repo_root: Path, runner: Callable | None = None) -> str | None:
    code, out, _ = _git(repo_root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}", runner=runner)
    if code != 0:
        return None
    return out.strip() or None


def publish_spec(
    repo_root: Path,
    path: str,
    *,
    dry_run: bool = False,
    already_pushed: bool = False,
    allow_provider_sync: bool = False,
    provider: str | None = None,
    home: Path | None = None,
    git_runner: Callable | None = None,
) -> dict[str, Any]:
    validated = validate_spec_path(repo_root, path)
    if not validated.get("ok"):
        return {**validated, "completed": {"validate": False}}

    dirty = _dirty_paths(repo_root, runner=git_runner)
    scoped = {validated["path"]}
    unrelated = [p for p in dirty if _norm(p) not in scoped and p not in scoped]
    if unrelated and not already_pushed:
        return {
            "ok": False,
            "code": UNRELATED_DIRTY_WORKTREE,
            "message": "Dirty worktree has unrelated changes; refuse publish (no auto-stash)",
            "dirty": unrelated,
            "completed": {"validate": True},
        }
    if unrelated and already_pushed:
        # already-pushed still fails closed on unrelated dirty
        return {
            "ok": False,
            "code": DIRTY_WORKTREE,
            "message": "Dirty worktree with unrelated changes; fail closed",
            "dirty": unrelated,
            "completed": {"validate": True},
        }

    upstream = _upstream_ref(repo_root, runner=git_runner)
    if already_pushed:
        if not upstream:
            # allow origin/HEAD style if branch tracking missing but origin exists
            code, out, _ = _git(repo_root, "rev-parse", "origin/HEAD", runner=git_runner)
            if code != 0:
                code2, out2, _ = _git(repo_root, "rev-parse", "origin/main", runner=git_runner)
                if code2 != 0:
                    return {
                        "ok": False,
                        "code": PUBLISH_REQUIRES_PUSHED_REF,
                        "message": "already-pushed requires an upstream/origin ref",
                        "completed": {"validate": True},
                    }
                upstream = "origin/main"
            else:
                upstream = out.strip()
        authoritative = upstream
        committed = False
        pushed = False
    else:
        if not upstream:
            return {
                "ok": False,
                "code": UNPUSHED_REF,
                "message": "Refusing provider sync from unpushed draft; push or use --already-pushed",
                "provider_sync_attempted": False,
                "completed": {"validate": True},
            }
        authoritative = upstream
        committed = False
        pushed = False

    config = load_config(repo_root)
    corpus = build_desired_corpus(config, repo_root=repo_root)
    snapshot = build_desired_snapshot(
        project_id=config.project_id,
        sync_scope="ssot_files",
        documents=[{"doc_id": d.doc_id, "path": d.path} for d in corpus.documents],
        repo_root=repo_root,
    )

    plan = {
        "validate": True,
        "publish": not dry_run,
        "sync": bool(allow_provider_sync and not dry_run),
        "authoritative_ref": authoritative,
        "snapshot_hash": snapshot.snapshot_hash,
        "item_count": snapshot.item_count,
    }

    result: dict[str, Any] = {
        "ok": True,
        "dry_run": dry_run,
        "spec_id": validated["spec_id"],
        "path": validated["path"],
        "content_sha256": validated["content_sha256"],
        "authoritative_ref": authoritative,
        "committed": committed,
        "pushed": pushed,
        "provider_mutated": False,
        "completed": {"validate": True, "publish": not dry_run},
        "plan": plan,
        "desired_snapshot": {
            "snapshot_hash": snapshot.snapshot_hash,
            "item_count": snapshot.item_count,
            "paths": [i.path for i in snapshot.items],
        },
        "next_actions": [],
    }

    if dry_run:
        result["ok"] = True
        return result

    if not allow_provider_sync:
        result["knowledge_sync"] = {"ok": None, "skipped": True}
        result["next_actions"] = ["vibe knowledge sync --apply --json"]
        return result

    # Phase 8 sync path
    try:
        from vibe_control.knowledge.notebooks import require_notebook_ref

        entry, ref = require_notebook_ref(config, repo_root=repo_root, alias=None)
        target = ProviderTarget.from_ref(
            provider="notebooklm", notebook_alias=entry.alias, notebook_ref=ref
        )
    except Exception as exc:
        result["ok"] = False
        result["partial_success"] = True
        result["failed"] = "knowledge_sync"
        result["knowledge_sync"] = {"ok": False, "code": "TARGET_UNRESOLVED", "message": str(exc)}
        result["pending"] = True
        result["next_actions"] = ["vibe knowledge retry --dry-run --json"]
        return result

    class _Unavailable:
        def list_sources(self, *, notebook_ref: str) -> dict[str, Any]:
            raise RuntimeError("NOTEBOOKLM_UNAVAILABLE")

        def add_file_source(self, **kwargs) -> dict[str, Any]:
            return {"ok": False}

        def wait_source(self, **kwargs) -> dict[str, Any]:
            return {"ok": False}

        def get_source(self, **kwargs) -> dict[str, Any]:
            return {"ok": False, "found": False}

        def delete_source(self, **kwargs) -> dict[str, Any]:
            return {"ok": False}

    if provider == "fake":
        # Tests inject apply_forward_sync via monkeypatch; still need a provider object.
        sync_provider: Any = _Unavailable()
    else:
        from vibe_control.knowledge.notebooklm_provider import NotebookLMProvider

        sync_provider = NotebookLMProvider()

    sync_result = apply_forward_sync(
        config,
        repo_root=repo_root,
        target=target,
        notebook_ref=ref,
        provider=sync_provider,
        ack_store=FakeAckStore(),
        home=home,
        command="vibe spec publish",
    )
    result["knowledge_sync"] = sync_result
    result["provider_mutated"] = bool(sync_result.get("ok") and provider != "fake")
    if not sync_result.get("ok"):
        result["ok"] = False
        result["partial_success"] = True
        result["failed"] = "knowledge_sync"
        result["pending"] = True
        result["next_actions"] = ["vibe knowledge retry --dry-run --json"]
        # Ensure pending marker exists via Phase 8 helper when possible
        try:
            from vibe_control.knowledge.pending_sync import write_pending_sync

            write_pending_sync(
                config.project_id,
                target,
                reason=str(sync_result.get("code") or "KNOWLEDGE_SYNC_FAILED"),
                home=home,
                target_ref=authoritative,
            )
        except Exception:
            pass
    return result
