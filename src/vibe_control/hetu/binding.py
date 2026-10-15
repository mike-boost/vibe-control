"""Repo ↔ provider project binding helpers (pure; no provider mutation)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ARTIFACT_GRAPH_RELATIVE = ".codebase-memory/graph.db.zst"
ARTIFACT_DIR_RELATIVE = ".codebase-memory"


@dataclass(frozen=True)
class ProviderProjectCandidate:
    """Normalized provider project row from list_projects (no absolute path in public dict)."""

    name: str
    root_path: str
    nodes: int = 0
    edges: int = 0
    size_bytes: int | None = None
    root_matches: bool = False

    def to_public_dict(self) -> dict[str, Any]:
        """Redacted view: name + match flag + counts; never emits absolute root_path."""
        out: dict[str, Any] = {
            "name": self.name,
            "root_matches": self.root_matches,
            "nodes": self.nodes,
            "edges": self.edges,
        }
        if self.size_bytes is not None:
            out["size_bytes"] = self.size_bytes
        return out


@dataclass(frozen=True)
class ArtifactEvidence:
    """Optional on-disk provider artifact; never proves binding or readiness."""

    present: bool
    relative_path: str | None = None
    kind: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "present": self.present,
            "relative_path": self.relative_path,
            "kind": self.kind,
            "binding": False,
            "note": (
                "Artifact presence is optional evidence only; it does not bind "
                "or prove freshness"
            ),
        }


@dataclass(frozen=True)
class BindingResolution:
    """Result of matching current repo root to list_projects candidates."""

    repo_realpath: str
    repo_realpath_hash: str
    selected_project: str | None
    matching_candidates: list[ProviderProjectCandidate] = field(default_factory=list)
    all_candidates: list[ProviderProjectCandidate] = field(default_factory=list)
    binding_conflict: bool = False
    reason: str | None = None
    message: str | None = None
    configured_project: str | None = None
    artifact: ArtifactEvidence | None = None

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "repo_realpath_hash": self.repo_realpath_hash,
            "selected_project": self.selected_project,
            "matching_candidates": [c.to_public_dict() for c in self.matching_candidates],
            "candidate_count": len(self.matching_candidates),
            "all_candidate_count": len(self.all_candidates),
            "binding_conflict": self.binding_conflict,
            "reason": self.reason,
            "message": self.message,
            "configured_project": self.configured_project,
            "artifact": None if self.artifact is None else self.artifact.to_dict(),
        }


def canonicalize_repo_root(repo_root: Path | str) -> Path:
    """Canonical current-repo resolution via Path.resolve()."""
    return Path(repo_root).resolve()


def compute_repo_realpath_hash(repo_root: Path | str) -> str:
    canonical = str(canonicalize_repo_root(repo_root))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return "sha256:" + digest


def normalize_provider_projects(raw_projects: list[Any]) -> list[ProviderProjectCandidate]:
    out: list[ProviderProjectCandidate] = []
    for row in raw_projects:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or row.get("project") or "").strip()
        root = str(row.get("root_path") or row.get("root") or "").strip()
        if not name or not root:
            continue
        nodes = int(row.get("nodes") or row.get("node_count") or 0)
        edges = int(row.get("edges") or row.get("edge_count") or 0)
        size_raw = row.get("size_bytes")
        size_bytes = int(size_raw) if size_raw is not None else None
        out.append(
            ProviderProjectCandidate(
                name=name,
                root_path=root,
                nodes=nodes,
                edges=edges,
                size_bytes=size_bytes,
            )
        )
    return out


def detect_codebase_memory_artifact(repo_root: Path | str) -> ArtifactEvidence:
    """Report `.codebase-memory/` artifacts without treating them as binding."""
    root = canonicalize_repo_root(repo_root)
    graph = root / ARTIFACT_GRAPH_RELATIVE
    if graph.is_file():
        return ArtifactEvidence(
            present=True,
            relative_path=ARTIFACT_GRAPH_RELATIVE,
            kind="graph.db.zst",
        )
    artifact_dir = root / ARTIFACT_DIR_RELATIVE
    if artifact_dir.is_dir():
        return ArtifactEvidence(
            present=True,
            relative_path=ARTIFACT_DIR_RELATIVE,
            kind="directory",
        )
    return ArtifactEvidence(present=False)


def _roots_equal(left: Path | str, right: Path | str) -> bool:
    try:
        return canonicalize_repo_root(left) == canonicalize_repo_root(right)
    except OSError:
        return False


def resolve_project_binding(
    *,
    repo_root: Path | str,
    projects: list[Any],
    configured_project: str | None = None,
    artifact: ArtifactEvidence | None = None,
) -> BindingResolution:
    """Match list_projects.root_path to the current repo; never silent-adopts HEAD.

    Rules (spec §5):
    - one exact root candidate → selected
    - zero candidates → missing (selected=None, no conflict)
    - multiple exact candidates → conflict_needs_choice
    - configured project must exist and its root must match; else conflict
    """
    canonical = canonicalize_repo_root(repo_root)
    repo_hash = compute_repo_realpath_hash(canonical)
    normalized = normalize_provider_projects(projects)
    annotated: list[ProviderProjectCandidate] = []
    matching: list[ProviderProjectCandidate] = []
    for cand in normalized:
        matches = _roots_equal(cand.root_path, canonical)
        updated = ProviderProjectCandidate(
            name=cand.name,
            root_path=cand.root_path,
            nodes=cand.nodes,
            edges=cand.edges,
            size_bytes=cand.size_bytes,
            root_matches=matches,
        )
        annotated.append(updated)
        if matches:
            matching.append(updated)

    configured = (configured_project or "").strip() or None
    art = artifact if artifact is not None else detect_codebase_memory_artifact(canonical)

    if configured:
        by_name = [c for c in annotated if c.name == configured]
        if not by_name:
            return BindingResolution(
                repo_realpath=str(canonical),
                repo_realpath_hash=repo_hash,
                selected_project=None,
                matching_candidates=matching,
                all_candidates=annotated,
                binding_conflict=True,
                reason="configured_project_not_found",
                message=(
                    f"Configured hetu.codebase_memory.project={configured!r} "
                    "was not found in list_projects"
                ),
                configured_project=configured,
                artifact=art,
            )
        chosen = by_name[0]
        if not chosen.root_matches:
            return BindingResolution(
                repo_realpath=str(canonical),
                repo_realpath_hash=repo_hash,
                selected_project=None,
                matching_candidates=matching,
                all_candidates=annotated,
                binding_conflict=True,
                reason="configured_project_root_mismatch",
                message=(
                    f"Configured project {configured!r} exists but root_path "
                    "does not match the current repo"
                ),
                configured_project=configured,
                artifact=art,
            )
        # Configured project matches current root — even if other root matches exist.
        return BindingResolution(
            repo_realpath=str(canonical),
            repo_realpath_hash=repo_hash,
            selected_project=chosen.name,
            matching_candidates=matching,
            all_candidates=annotated,
            binding_conflict=False,
            reason=None,
            message=None,
            configured_project=configured,
            artifact=art,
        )

    if len(matching) == 0:
        return BindingResolution(
            repo_realpath=str(canonical),
            repo_realpath_hash=repo_hash,
            selected_project=None,
            matching_candidates=[],
            all_candidates=annotated,
            binding_conflict=False,
            reason="provider_project_missing",
            message="No matching provider project/index for the current repo",
            configured_project=None,
            artifact=art,
        )

    if len(matching) > 1:
        return BindingResolution(
            repo_realpath=str(canonical),
            repo_realpath_hash=repo_hash,
            selected_project=None,
            matching_candidates=matching,
            all_candidates=annotated,
            binding_conflict=True,
            reason="multiple_root_matches",
            message=(
                "Multiple provider projects share this repo root_path; "
                "set hetu.codebase_memory.project explicitly"
            ),
            configured_project=None,
            artifact=art,
        )

    only = matching[0]
    return BindingResolution(
        repo_realpath=str(canonical),
        repo_realpath_hash=repo_hash,
        selected_project=only.name,
        matching_candidates=matching,
        all_candidates=annotated,
        binding_conflict=False,
        reason=None,
        message=None,
        configured_project=None,
        artifact=art,
    )


def interpret_auto_watch(
    *,
    config_values: dict[str, str] | None,
    watcher_state_observable: bool,
) -> tuple[bool | None, bool, str | None]:
    """Resolve effective auto_watch for strict readiness.

    Returns ``(auto_watch_effective, watcher_compatible, reason)``.

    - Provider versions that cannot expose watcher state → incompatible
      (``watcher_state_observable=False`` or ``config_values is None``).
    - Absent ``auto_watch`` key in an observable config list → provider default
      ``True`` (spec §6.4).
    - Present key → parsed bool (or ``None`` if unparseable → still compatible
      but unverifiable via state evaluator).
    """
    if not watcher_state_observable or config_values is None:
        return None, False, "watcher_unobservable"

    if "auto_watch" not in config_values:
        # Provider default when unset is true.
        return True, True, None

    raw = str(config_values["auto_watch"]).strip().lower()
    if raw in {"true", "1", "yes", "on"}:
        return True, True, None
    if raw in {"false", "0", "no", "off"}:
        return False, True, None
    return None, True, "watcher_unparseable"
