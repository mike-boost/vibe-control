"""codebase-memory-mcp subprocess CLI adapter (no MCP SDK).

Transport: argv list only — never shell=True / string commands.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal

from vibe_control.hetu.models import (
    ArchitectureCluster,
    ArchitectureResult,
    ImpactResult,
    ImpactSymbol,
    ProviderStatusResult,
    SearchHit,
    SearchResult,
    TraceEdge,
    TraceNode,
    TraceResult,
)
from vibe_control.hetu.provider import ReindexResult

TraceDirection = Literal["inbound", "outbound", "both"]

PROVIDER_ID = "codebase_memory"

# Spec §4.3 tool mapping (Hetu op → provider tool).
TOOL_MAPPING: dict[str, str | tuple[str, ...]] = {
    "status": ("list_projects", "index_status"),
    "search": "search_graph",
    "trace": "trace_path",
    "impact": "detect_changes",
    "architecture": "get_architecture",
    "reindex": "index_repository",
}

# Spec §4.2 required tools for compatibility probe.
REQUIRED_COMPAT_TOOLS: frozenset[str] = frozenset(
    {
        "index_status",
        "search_graph",
        "trace_path",
        "detect_changes",
        "get_architecture",
        "index_repository",
        "list_projects",
    }
)

_LOG_PREFIX_RE = re.compile(r"^level=\w+\b")
_VERSION_RE = re.compile(r"(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.]+)?)")


class CodebaseMemoryCliError(Exception):
    """Stable adapter failure with a normalized error code."""

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


@dataclass(frozen=True)
class CliRunResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


@dataclass(frozen=True)
class ParsedCliJson:
    ok: bool
    payload: Any = None
    wrapped: bool = False
    is_error: bool = False
    discarded_log_prefixes: list[str] = field(default_factory=list)
    error_code: str | None = None
    error_text: str | None = None
    outer: Any = None


@dataclass(frozen=True)
class InvokeResult:
    ok: bool
    payload: Any
    stdout: str
    stderr: str
    discarded_log_prefixes: list[str] = field(default_factory=list)
    wrapped: bool = False
    tool: str | None = None


@dataclass(frozen=True)
class CompatibilityProbeResult:
    ok: bool
    compatible: bool
    binary_path: str | None
    provider_version: str | None
    tools_present: dict[str, bool]
    missing_tools: list[str]
    config_values: dict[str, str]
    auto_watch_effective: bool | None
    reason: str | None = None
    projects: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "compatible": self.compatible,
            "binary_path": self.binary_path,
            "provider_version": self.provider_version,
            "tools_present": dict(self.tools_present),
            "missing_tools": list(self.missing_tools),
            "config_values": dict(self.config_values),
            "auto_watch_effective": self.auto_watch_effective,
            "reason": self.reason,
            "projects": list(self.projects),
        }


Runner = Callable[..., CliRunResult]
WhichFn = Callable[[str], str | None]


def subprocess_codebase_memory_runner(
    argv: list[str],
    *,
    timeout_sec: float | None = None,
    env: dict[str, str] | None = None,
) -> CliRunResult:
    """Default runner: argv subprocess only (never shell=True)."""
    if not isinstance(argv, list) or not all(isinstance(x, str) for x in argv):
        raise CodebaseMemoryCliError(
            "invalid_argv",
            "runner requires argv list[str]",
            {"argv_type": type(argv).__name__},
        )
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_sec,
            env=env,
            shell=False,
        )
        return CliRunResult(
            returncode=int(proc.returncode),
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
            timed_out=False,
        )
    except FileNotFoundError:
        return CliRunResult(returncode=127, stdout="", stderr="executable not found", timed_out=False)
    except subprocess.TimeoutExpired as exc:
        stdout = ""
        stderr = "command timed out"
        if exc.stdout:
            stdout = exc.stdout if isinstance(exc.stdout, str) else exc.stdout.decode("utf-8", "replace")
        if exc.stderr:
            stderr = exc.stderr if isinstance(exc.stderr, str) else exc.stderr.decode("utf-8", "replace")
        return CliRunResult(returncode=124, stdout=stdout, stderr=stderr, timed_out=True)


def _try_load_json(text: str) -> Any | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _unwrap_mcp_content(obj: Any) -> tuple[Any, bool, bool, str | None]:
    """Return (payload, wrapped, is_error, error_text)."""
    if not isinstance(obj, dict):
        return obj, False, False, None
    content = obj.get("content")
    is_error = bool(obj.get("isError"))
    if not isinstance(content, list) or not content:
        return obj, False, is_error, None
    texts: list[str] = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text" and item.get("text") is not None:
            texts.append(str(item["text"]))
    if not texts:
        return obj, False, is_error, None
    joined = "\n".join(texts).strip()
    nested = _try_load_json(joined)
    if nested is not None:
        nested_error = isinstance(nested, dict) and bool(nested.get("error"))
        err_text = None
        if nested_error and isinstance(nested, dict):
            err_text = str(nested.get("error"))
        return nested, True, is_error or nested_error, err_text
    # Plain text error (e.g. "unknown tool: ...")
    plain_error = is_error or joined.lower().startswith("unknown tool")
    return joined, True, plain_error, joined if plain_error else None


def parse_cli_stdout(stdout: str) -> ParsedCliJson:
    """Parse direct or wrapped JSON; strip leading level=* log lines.

    Selects the final valid JSON record. Rejects trailing non-whitespace garbage.
    Discarded log prefixes are returned for redacted warnings (never silent).
    """
    text = stdout or ""
    if not text.strip():
        return ParsedCliJson(ok=False, error_code="invalid_json", error_text="empty stdout")

    lines = text.splitlines()
    discarded: list[str] = []
    body_lines: list[str] = []
    for line in lines:
        if not body_lines and _LOG_PREFIX_RE.match(line.strip()):
            discarded.append(line.rstrip("\n"))
            continue
        body_lines.append(line)

    body = "\n".join(body_lines).strip()
    if not body:
        return ParsedCliJson(
            ok=False,
            error_code="invalid_json",
            error_text="no JSON after log prefix",
            discarded_log_prefixes=discarded,
        )

    # Prefer whole-body JSON first (common for --json / direct).
    loaded = _try_load_json(body)
    if loaded is not None:
        payload, wrapped, is_error, error_text = _unwrap_mcp_content(loaded)
        return ParsedCliJson(
            ok=True,
            payload=payload,
            wrapped=wrapped,
            is_error=is_error,
            discarded_log_prefixes=discarded,
            error_text=error_text,
            outer=loaded if wrapped else None,
        )

    # Scan for the final complete JSON value; reject trailing garbage.
    decoder = json.JSONDecoder()
    last_value: Any | None = None
    last_end = -1
    idx = 0
    length = len(body)
    while idx < length:
        while idx < length and body[idx].isspace():
            idx += 1
        if idx >= length:
            break
        try:
            value, end = decoder.raw_decode(body, idx)
        except json.JSONDecodeError:
            break
        last_value = value
        last_end = end
        idx = end

    if last_value is None or last_end < 0:
        return ParsedCliJson(
            ok=False,
            error_code="invalid_json",
            error_text="stdout is not valid JSON",
            discarded_log_prefixes=discarded,
        )

    trailing = body[last_end:].strip()
    if trailing:
        return ParsedCliJson(
            ok=False,
            error_code="invalid_json",
            error_text="trailing garbage after JSON",
            discarded_log_prefixes=discarded,
        )

    payload, wrapped, is_error, error_text = _unwrap_mcp_content(last_value)
    return ParsedCliJson(
        ok=True,
        payload=payload,
        wrapped=wrapped,
        is_error=is_error,
        discarded_log_prefixes=discarded,
        error_text=error_text,
        outer=last_value if wrapped else None,
    )


def parse_version_text(text: str) -> str | None:
    for line in (text or "").splitlines():
        match = _VERSION_RE.search(line)
        if match:
            return match.group(1)
    return None


def parse_tools_from_help(text: str) -> set[str]:
    """Extract tool names from `codebase-memory-mcp --help` Tools: section."""
    tools: set[str] = set()
    capturing = False
    chunks: list[str] = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("Tools:"):
            capturing = True
            chunks.append(stripped[len("Tools:") :].strip())
            continue
        if capturing:
            if not stripped:
                break
            if stripped.startswith("Usage:") or stripped.startswith("UI options:"):
                break
            chunks.append(stripped)
    blob = " ".join(chunks)
    for part in blob.replace("\n", " ").split(","):
        name = part.strip().strip(".")
        if name and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            tools.add(name)
    return tools


def parse_config_list(text: str) -> dict[str, str]:
    """Parse human `config list` output into key→value map."""
    values: dict[str, str] = {}
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.lower().startswith("configuration"):
            continue
        if "=" not in stripped:
            continue
        key, _, raw_val = stripped.partition("=")
        key = key.strip()
        val = raw_val.strip()
        if key:
            values[key] = val
    return values


def effective_auto_watch(config_values: dict[str, str]) -> bool | None:
    """None when unobservable (missing key); else parsed bool. Default true if unset upstream."""
    if "auto_watch" not in config_values:
        return None
    raw = str(config_values["auto_watch"]).strip().lower()
    if raw in {"true", "1", "yes", "on"}:
        return True
    if raw in {"false", "0", "no", "off"}:
        return False
    return None


def build_cli_argv(binary: str, tool_name: str, args: dict[str, Any] | None = None) -> list[str]:
    return [binary, "cli", "--json", tool_name, json.dumps(args or {}, separators=(",", ":"))]


class CodebaseMemoryCliAdapter:
    """Injected-runner adapter for codebase-memory-mcp CLI tools."""

    name = PROVIDER_ID

    def __init__(
        self,
        *,
        binary: str = "codebase-memory-mcp",
        project: str | None = None,
        repo_root: str | Path | None = None,
        runner: Runner | None = None,
        query_timeout_sec: int = 30,
        reindex_timeout_sec: int = 600,
        which: WhichFn | None = None,
    ) -> None:
        self.binary = binary
        self.project = project
        self.repo_root = str(Path(repo_root).resolve()) if repo_root is not None else None
        self._runner = runner or subprocess_codebase_memory_runner
        self.query_timeout_sec = int(query_timeout_sec)
        self.reindex_timeout_sec = int(reindex_timeout_sec)
        self._which = which or shutil.which
        self._cached_version: str | None = None
        self.last_discarded_log_prefixes: list[str] = []

    def resolve_binary(self) -> str:
        configured = str(self.binary or "").strip()
        if not configured:
            raise CodebaseMemoryCliError("binary_unavailable", "binary path is empty")
        path = Path(configured)
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
        found = self._which(configured)
        if found:
            return found
        # Explicit absolute/relative path that exists as file.
        if path.exists() and path.is_file():
            return str(path.resolve())
        raise CodebaseMemoryCliError(
            "binary_unavailable",
            f"codebase-memory binary not found: {configured}",
            {"binary": configured},
        )

    def _run(
        self,
        argv: list[str],
        *,
        timeout_sec: float | None,
        env: dict[str, str] | None = None,
    ) -> CliRunResult:
        if not isinstance(argv, list) or any(not isinstance(x, str) for x in argv):
            raise CodebaseMemoryCliError("invalid_argv", "argv must be list[str]")
        return self._runner(argv, timeout_sec=timeout_sec, env=env)

    def _provider_version(self, binary: str) -> str | None:
        if self._cached_version is not None:
            return self._cached_version
        result = self._run([binary, "--version"], timeout_sec=min(30.0, float(self.query_timeout_sec)))
        if result.timed_out:
            raise CodebaseMemoryCliError("provider_timeout", "version probe timed out")
        if result.returncode != 0:
            raise CodebaseMemoryCliError(
                "provider_exit_error",
                "version probe failed",
                {"returncode": result.returncode},
            )
        version = parse_version_text(result.stdout) or parse_version_text(result.stderr)
        self._cached_version = version
        return version

    def invoke_tool(
        self,
        tool_name: str,
        args: dict[str, Any] | None = None,
        *,
        timeout_sec: float | None = None,
        env: dict[str, str] | None = None,
        allow_error_payload: bool = False,
    ) -> InvokeResult:
        binary = self.resolve_binary()
        argv = build_cli_argv(binary, tool_name, args)
        timeout = float(self.query_timeout_sec if timeout_sec is None else timeout_sec)
        run = self._run(argv, timeout_sec=timeout, env=env)
        if run.timed_out or run.returncode == 124:
            raise CodebaseMemoryCliError(
                "provider_timeout",
                f"tool timed out: {tool_name}",
                {"tool": tool_name, "timeout_sec": timeout},
            )
        if run.returncode == 127:
            raise CodebaseMemoryCliError(
                "binary_unavailable",
                f"binary unavailable while invoking {tool_name}",
                {"tool": tool_name},
            )
        if run.returncode != 0:
            raise CodebaseMemoryCliError(
                "provider_exit_error",
                f"tool exited non-zero: {tool_name}",
                {
                    "tool": tool_name,
                    "returncode": run.returncode,
                    "stderr_redacted": (run.stderr or "")[:200],
                },
            )

        parsed = parse_cli_stdout(run.stdout)
        self.last_discarded_log_prefixes = list(parsed.discarded_log_prefixes)
        if not parsed.ok:
            raise CodebaseMemoryCliError(
                parsed.error_code or "invalid_json",
                parsed.error_text or "invalid provider JSON",
                {"tool": tool_name},
            )

        if parsed.is_error and not allow_error_payload:
            text = (parsed.error_text or "").lower()
            payload_text = str(parsed.payload).lower()
            if "unknown tool" in text or "unknown tool" in payload_text:
                raise CodebaseMemoryCliError(
                    "tool_missing",
                    f"provider tool missing: {tool_name}",
                    {"tool": tool_name, "payload": parsed.payload},
                )
            raise CodebaseMemoryCliError(
                "provider_error",
                f"provider tool error: {tool_name}",
                {"tool": tool_name, "payload": parsed.payload},
            )

        return InvokeResult(
            ok=True,
            payload=parsed.payload,
            stdout=run.stdout,
            stderr=run.stderr,
            discarded_log_prefixes=list(parsed.discarded_log_prefixes),
            wrapped=parsed.wrapped,
            tool=tool_name,
        )

    def probe_compatibility(self) -> CompatibilityProbeResult:
        """Probe binary/version/config/tools without calling index_repository."""
        binary = self.resolve_binary()
        version = self._provider_version(binary)

        help_run = self._run(
            [binary, "--help"],
            timeout_sec=min(30.0, float(self.query_timeout_sec)),
        )
        if help_run.timed_out:
            raise CodebaseMemoryCliError("provider_timeout", "help probe timed out")
        if help_run.returncode != 0:
            raise CodebaseMemoryCliError(
                "provider_exit_error",
                "help probe failed",
                {"returncode": help_run.returncode},
            )
        tools = parse_tools_from_help(help_run.stdout or help_run.stderr)
        tools_present = {name: name in tools for name in sorted(REQUIRED_COMPAT_TOOLS)}
        missing = sorted(name for name, present in tools_present.items() if not present)

        config_run = self._run(
            [binary, "config", "list"],
            timeout_sec=min(30.0, float(self.query_timeout_sec)),
        )
        if config_run.timed_out:
            raise CodebaseMemoryCliError("provider_timeout", "config list timed out")
        if config_run.returncode != 0:
            raise CodebaseMemoryCliError(
                "provider_exit_error",
                "config list failed",
                {"returncode": config_run.returncode},
            )
        config_values = parse_config_list(config_run.stdout or "")
        auto_watch = effective_auto_watch(config_values)

        # Readonly inventory probe — never index_repository.
        projects_payload = self.invoke_tool("list_projects", {}).payload
        projects: list[dict[str, Any]] = []
        if isinstance(projects_payload, dict):
            raw_projects = projects_payload.get("projects")
            if isinstance(raw_projects, list):
                projects = [p for p in raw_projects if isinstance(p, dict)]
        elif isinstance(projects_payload, list):
            projects = [p for p in projects_payload if isinstance(p, dict)]

        compatible = not missing
        return CompatibilityProbeResult(
            ok=True,
            compatible=compatible,
            binary_path=binary,
            provider_version=version,
            tools_present=tools_present,
            missing_tools=missing,
            config_values=config_values,
            auto_watch_effective=auto_watch,
            reason=None if compatible else "provider_incompatible",
            projects=projects,
        )

    def _require_project(self) -> str:
        if not self.project or not str(self.project).strip():
            raise CodebaseMemoryCliError(
                "provider_error",
                "hetu.codebase_memory.project is required for this operation",
            )
        return str(self.project)

    def status(self) -> ProviderStatusResult:
        version = None
        try:
            version = self._provider_version(self.resolve_binary())
        except CodebaseMemoryCliError:
            version = None

        projects_inv = self.invoke_tool("list_projects", {})
        projects_payload = projects_inv.payload
        projects: list[dict[str, Any]] = []
        if isinstance(projects_payload, dict) and isinstance(projects_payload.get("projects"), list):
            projects = [p for p in projects_payload["projects"] if isinstance(p, dict)]

        project = self.project
        if not project and len(projects) == 1:
            project = str(projects[0].get("name") or "") or None
        if not project:
            raise CodebaseMemoryCliError(
                "provider_error",
                "project binding required for status",
                {"project_count": len(projects)},
            )

        status_inv = self.invoke_tool("index_status", {"project": project})
        payload = status_inv.payload
        if not isinstance(payload, dict):
            raise CodebaseMemoryCliError(
                "provider_incompatible",
                "index_status payload is not an object",
                {"payload_type": type(payload).__name__},
            )
        if "status" not in payload or "nodes" not in payload or "edges" not in payload:
            raise CodebaseMemoryCliError(
                "provider_incompatible",
                "index_status missing required fields (status/nodes/edges)",
                {"keys": sorted(payload.keys())},
            )

        raw_status = str(payload.get("status") or "").strip().lower()
        nodes = int(payload.get("nodes") or 0)
        edges = int(payload.get("edges") or 0)
        if raw_status == "indexing":
            index_state: Any = "indexing"
            reason = "provider_degraded"
        elif raw_status == "ready":
            index_state = "ready"
            reason = None
        else:
            index_state = "unavailable"
            reason = f"provider_status:{raw_status or 'unknown'}"

        return ProviderStatusResult(
            provider=PROVIDER_ID,
            provider_version=version,
            provider_project=str(payload.get("project") or project),
            index_state=index_state,
            index_commit=None,  # provider does not return git commit
            node_count=nodes,
            edge_count=edges,
            auto_watch_effective=None,
            freshness_assurance=None,
            reason=reason,
        )

    def search(self, *, query: str, limit: int = 20) -> SearchResult:
        project = self._require_project()
        inv = self.invoke_tool(
            "search_graph",
            {"project": project, "query": query, "limit": int(limit)},
        )
        payload = inv.payload if isinstance(inv.payload, dict) else {}
        results = payload.get("results") if isinstance(payload.get("results"), list) else []
        items: list[SearchHit] = []
        for row in results:
            if not isinstance(row, dict):
                continue
            qn = str(row.get("qualified_name") or row.get("name") or "")
            path = str(row.get("file_path") or row.get("path") or "")
            if not qn and not path:
                continue
            score = row.get("rank", row.get("score"))
            items.append(
                SearchHit(
                    qualified_name=qn,
                    path=path,
                    start_line=_as_optional_int(row.get("start_line")),
                    end_line=_as_optional_int(row.get("end_line")),
                    score=float(score) if isinstance(score, (int, float)) else None,
                )
            )
        total = payload.get("total")
        total_i = int(total) if isinstance(total, int) else (len(items) if total is None else None)
        has_more = bool(payload.get("has_more")) if "has_more" in payload else (
            total_i is not None and total_i > len(items)
        )
        return SearchResult(
            items=items,
            total=total_i,
            returned=len(items),
            has_more=has_more,
            truncated=has_more,
        )

    def trace(
        self,
        *,
        symbol: str,
        direction: TraceDirection = "both",
        depth: int = 3,
    ) -> TraceResult:
        project = self._require_project()
        inv = self.invoke_tool(
            "trace_path",
            {
                "project": project,
                "function_name": symbol,
                "direction": direction,
                "depth": int(depth),
            },
        )
        payload = inv.payload if isinstance(inv.payload, dict) else {}
        paths_raw = payload.get("paths") if isinstance(payload.get("paths"), list) else []
        paths = [list(p) for p in paths_raw if isinstance(p, list)]
        nodes: list[TraceNode] = []
        for row in payload.get("nodes") or []:
            if not isinstance(row, dict):
                continue
            nodes.append(
                TraceNode(
                    qualified_name=str(row.get("qualified_name") or row.get("name") or ""),
                    path=str(row.get("file_path") or row.get("path") or ""),
                    start_line=_as_optional_int(row.get("start_line")),
                    end_line=_as_optional_int(row.get("end_line")),
                )
            )
        edges: list[TraceEdge] = []
        for row in payload.get("edges") or []:
            if not isinstance(row, dict):
                continue
            edges.append(
                TraceEdge(
                    source=str(row.get("source") or ""),
                    target=str(row.get("target") or ""),
                    kind=None if row.get("type") is None and row.get("kind") is None else str(
                        row.get("type") or row.get("kind")
                    ),
                )
            )
        return TraceResult(paths=paths, nodes=nodes, edges=edges, truncated=False)

    def impact(self, *, since: str | None = None, depth: int = 2) -> ImpactResult:
        project = self._require_project()
        args: dict[str, Any] = {"project": project, "depth": int(depth)}
        if since:
            args["since"] = since
        inv = self.invoke_tool("detect_changes", args)
        payload = inv.payload if isinstance(inv.payload, dict) else {}
        symbols: list[ImpactSymbol] = []
        for row in payload.get("impacted_symbols") or []:
            if not isinstance(row, dict):
                continue
            risk = row.get("risk")
            hops = row.get("hops")
            symbols.append(
                ImpactSymbol(
                    qualified_name=str(row.get("qualified_name") or row.get("name") or ""),
                    path=str(row.get("file_path") or row.get("path") or ""),
                    risk=float(risk) if isinstance(risk, (int, float)) else None,
                    hops=int(hops) if isinstance(hops, int) else None,
                )
            )
        edges: list[TraceEdge] = []
        for row in payload.get("edges") or []:
            if not isinstance(row, dict):
                continue
            edges.append(
                TraceEdge(
                    source=str(row.get("source") or ""),
                    target=str(row.get("target") or ""),
                    kind=None if row.get("type") is None and row.get("kind") is None else str(
                        row.get("type") or row.get("kind")
                    ),
                )
            )
        return ImpactResult(symbols=symbols, edges=edges, truncated=False)

    def architecture(self) -> ArchitectureResult:
        project = self._require_project()
        inv = self.invoke_tool("get_architecture", {"project": project})
        payload = inv.payload if isinstance(inv.payload, dict) else {}
        clusters: list[ArchitectureCluster] = []
        for row in payload.get("clusters") or []:
            if not isinstance(row, dict):
                continue
            name = str(row.get("label") or row.get("name") or row.get("id") or "cluster")
            reps: list[TraceNode] = []
            for top in row.get("top_nodes") or []:
                if isinstance(top, str):
                    reps.append(TraceNode(qualified_name=top, path=""))
                elif isinstance(top, dict):
                    reps.append(
                        TraceNode(
                            qualified_name=str(top.get("qualified_name") or top.get("name") or ""),
                            path=str(top.get("file_path") or top.get("path") or ""),
                        )
                    )
            clusters.append(ArchitectureCluster(name=name, representatives=reps))
        return ArchitectureResult(clusters=clusters, truncated=False)

    def reindex(
        self,
        *,
        mode: str = "fast",
        persistence: bool = False,
        index_commit: str | None = None,
    ) -> ReindexResult:
        if str(mode).strip().lower() != "fast":
            return ReindexResult(
                ok=False,
                mutation_performed=False,
                index_mode=str(mode),
                persistence=bool(persistence),
                reason="unsupported_index_mode",
                message="Hetu MVP only supports mode=fast",
            )
        if persistence:
            return ReindexResult(
                ok=False,
                mutation_performed=False,
                index_mode="fast",
                persistence=True,
                reason="unsupported_persistence",
                message="Hetu MVP only supports persistence=false",
            )
        if not self.repo_root:
            raise CodebaseMemoryCliError(
                "provider_error",
                "repo_root is required for reindex (CBM_ALLOWED_ROOT)",
            )

        binary = self.resolve_binary()
        version = self._provider_version(binary)
        env = dict(os.environ)
        env["CBM_ALLOWED_ROOT"] = self.repo_root
        inv = self.invoke_tool(
            "index_repository",
            {
                "repo_path": self.repo_root,
                "mode": "fast",
                "persistence": False,
            },
            timeout_sec=float(self.reindex_timeout_sec),
            env=env,
        )
        payload = inv.payload if isinstance(inv.payload, dict) else {}
        return ReindexResult(
            ok=True,
            mutation_performed=True,
            provider_project=self.project or (
                str(payload.get("project")) if payload.get("project") else None
            ),
            provider_version=version,
            index_commit=index_commit,
            index_mode="fast",
            persistence=False,
            node_count=int(payload.get("nodes") or 0),
            edge_count=int(payload.get("edges") or 0),
        )


def _as_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
