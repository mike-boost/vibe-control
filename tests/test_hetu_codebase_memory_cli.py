"""Unit tests for codebase-memory subprocess CLI adapter (no real binary)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from vibe_control.hetu.codebase_memory_cli import (
    REQUIRED_COMPAT_TOOLS,
    TOOL_MAPPING,
    CliRunResult,
    CodebaseMemoryCliAdapter,
    CodebaseMemoryCliError,
    parse_cli_stdout,
    subprocess_codebase_memory_runner,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "hetu" / "codebase_memory"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class RecordingRunner:
    """Injected runner: scripted responses by argv fingerprint; never shells."""

    def __init__(self, script: dict[str, CliRunResult] | None = None) -> None:
        self.script = script or {}
        self.calls: list[dict[str, Any]] = []

    def _key(self, argv: list[str]) -> str:
        if len(argv) >= 4 and argv[1] == "cli" and argv[2] == "--json":
            return f"tool:{argv[3]}"
        if len(argv) >= 2 and argv[1] == "--version":
            return "version"
        if len(argv) >= 2 and argv[1] == "--help":
            return "help"
        if len(argv) >= 3 and argv[1] == "config" and argv[2] == "list":
            return "config_list"
        return " ".join(argv[1:])

    def __call__(
        self,
        argv: list[str],
        *,
        timeout_sec: float | None = None,
        env: dict[str, str] | None = None,
    ) -> CliRunResult:
        assert isinstance(argv, list)
        assert all(isinstance(x, str) for x in argv)
        self.calls.append(
            {"argv": list(argv), "timeout_sec": timeout_sec, "env": dict(env) if env else None}
        )
        key = self._key(argv)
        if key not in self.script:
            raise AssertionError(f"unexpected runner call key={key!r} argv={argv!r}")
        return self.script[key]


def _adapter(
    script: dict[str, CliRunResult],
    *,
    binary: str = "/opt/codebase-memory-mcp",
    project: str = "demo-project",
    repo_root: str = "/repo/demo",
) -> tuple[CodebaseMemoryCliAdapter, RecordingRunner]:
    runner = RecordingRunner(script)
    adapter = CodebaseMemoryCliAdapter(
        binary=binary,
        project=project,
        repo_root=repo_root,
        runner=runner,
        query_timeout_sec=30,
        reindex_timeout_sec=600,
        which=lambda _name: binary,
    )
    return adapter, runner


# --- parse_cli_stdout ---


def test_parse_v081_direct_json_strips_level_info_prefix():
    parsed = parse_cli_stdout(_load("v081_index_status_log_prefix.txt"))
    assert parsed.ok is True
    assert parsed.payload["project"] == "demo-project"
    assert parsed.payload["status"] == "ready"
    assert parsed.discarded_log_prefixes
    assert parsed.discarded_log_prefixes[0].startswith("level=info")
    assert parsed.is_error is False


def test_parse_v081_search_log_prefix():
    parsed = parse_cli_stdout(_load("v081_search_log_prefix.txt"))
    assert parsed.ok is True
    assert parsed.payload["total"] == 2
    assert parsed.payload["results"][0]["qualified_name"] == "demo.pkg.load_config"
    assert parsed.discarded_log_prefixes


def test_parse_v081_wrapped_with_log_prefix():
    parsed = parse_cli_stdout(_load("v081_index_status_wrapped_log_prefix.txt"))
    assert parsed.ok is True
    assert parsed.payload["nodes"] == 511
    assert parsed.wrapped is True
    assert parsed.discarded_log_prefixes


def test_parse_v09_wrapped_without_log_prefix():
    parsed = parse_cli_stdout(_load("v09_index_status_wrapped.json"))
    assert parsed.ok is True
    assert parsed.payload["nodes"] == 1200
    assert parsed.wrapped is True
    assert parsed.discarded_log_prefixes == []


def test_parse_invalid_json_fails_closed():
    parsed = parse_cli_stdout(_load("invalid_json.txt"))
    assert parsed.ok is False
    assert parsed.error_code == "invalid_json"


def test_parse_trailing_garbage_rejected():
    parsed = parse_cli_stdout(_load("trailing_garbage.txt"))
    assert parsed.ok is False
    assert parsed.error_code == "invalid_json"


def test_parse_unknown_tool_is_error():
    parsed = parse_cli_stdout(_load("unknown_tool_wrapped.txt"))
    assert parsed.ok is True
    assert parsed.is_error is True
    blob = f"{parsed.payload!s} {parsed.error_text or ''}".lower()
    assert "unknown tool" in blob


# --- tool mapping ---


def test_tool_mapping_table_matches_spec():
    assert TOOL_MAPPING["status"] == ("list_projects", "index_status")
    assert TOOL_MAPPING["search"] == "search_graph"
    assert TOOL_MAPPING["trace"] == "trace_path"
    assert TOOL_MAPPING["impact"] == "detect_changes"
    assert TOOL_MAPPING["architecture"] == "get_architecture"
    assert TOOL_MAPPING["reindex"] == "index_repository"
    assert "index_repository" in REQUIRED_COMPAT_TOOLS
    assert "list_projects" in REQUIRED_COMPAT_TOOLS


def test_invoke_uses_argv_list_never_shell_string():
    adapter, runner = _adapter(
        {
            "tool:index_status": CliRunResult(
                returncode=0, stdout=_load("v09_index_status_wrapped.json"), stderr=""
            )
        }
    )
    result = adapter.invoke_tool("index_status", {"project": "demo-project"})
    assert result.ok is True
    assert len(runner.calls) == 1
    argv = runner.calls[0]["argv"]
    assert argv[0] == "/opt/codebase-memory-mcp"
    assert argv[1:4] == ["cli", "--json", "index_status"]
    assert json.loads(argv[4]) == {"project": "demo-project"}
    assert not any("cli --json" in part for part in argv if " " in part and part != argv[4])


def test_stdout_stderr_separation_preserved():
    adapter, _runner = _adapter(
        {
            "tool:index_status": CliRunResult(
                returncode=0,
                stdout=_load("v09_index_status_wrapped.json"),
                stderr="level=warn msg=noise",
            )
        }
    )
    result = adapter.invoke_tool("index_status", {"project": "demo-project"})
    assert result.ok is True
    assert result.stderr == "level=warn msg=noise"
    assert "noise" not in json.dumps(result.payload)


# --- error normalization ---


def test_unavailable_binary():
    runner = RecordingRunner({})
    adapter = CodebaseMemoryCliAdapter(
        binary="codebase-memory-mcp-missing",
        project="demo-project",
        repo_root="/repo/demo",
        runner=runner,
        which=lambda _name: None,
    )
    with pytest.raises(CodebaseMemoryCliError) as exc:
        adapter.probe_compatibility()
    assert exc.value.code == "binary_unavailable"


def test_timeout_normalized():
    adapter, _runner = _adapter(
        {
            "tool:search_graph": CliRunResult(
                returncode=124, stdout="", stderr="timed out", timed_out=True
            )
        }
    )
    with pytest.raises(CodebaseMemoryCliError) as exc:
        adapter.invoke_tool("search_graph", {"project": "demo-project", "query": "x"})
    assert exc.value.code == "provider_timeout"


def test_nonzero_exit_normalized():
    adapter, _runner = _adapter(
        {
            "tool:index_status": CliRunResult(returncode=2, stdout="", stderr="boom")
        }
    )
    with pytest.raises(CodebaseMemoryCliError) as exc:
        adapter.invoke_tool("index_status", {"project": "demo-project"})
    assert exc.value.code == "provider_exit_error"


def test_missing_tool_error():
    adapter, _runner = _adapter(
        {
            "tool:totally_missing_tool": CliRunResult(
                returncode=0, stdout=_load("unknown_tool_wrapped.txt"), stderr=""
            )
        }
    )
    with pytest.raises(CodebaseMemoryCliError) as exc:
        adapter.invoke_tool("totally_missing_tool", {})
    assert exc.value.code == "tool_missing"


def test_invalid_json_error_from_invoke():
    adapter, _runner = _adapter(
        {
            "tool:index_status": CliRunResult(
                returncode=0, stdout=_load("invalid_json.txt"), stderr=""
            )
        }
    )
    with pytest.raises(CodebaseMemoryCliError) as exc:
        adapter.invoke_tool("index_status", {"project": "demo-project"})
    assert exc.value.code == "invalid_json"


def test_provider_error_payload():
    adapter, _runner = _adapter(
        {
            "tool:index_status": CliRunResult(
                returncode=0, stdout=_load("provider_error_wrapped.txt"), stderr=""
            )
        }
    )
    with pytest.raises(CodebaseMemoryCliError) as exc:
        adapter.invoke_tool("index_status", {"project": "demo-project"})
    assert exc.value.code == "provider_error"


def test_provider_degraded_status_maps_indexing():
    adapter, runner = _adapter(
        {
            "tool:list_projects": CliRunResult(
                returncode=0, stdout=_load("v09_list_projects_wrapped.json"), stderr=""
            ),
            "tool:index_status": CliRunResult(
                returncode=0, stdout=_load("provider_degraded_status.txt"), stderr=""
            ),
            "version": CliRunResult(returncode=0, stdout=_load("version_09.txt"), stderr=""),
        }
    )
    status = adapter.status()
    assert status.index_state == "indexing"
    tools = [c["argv"][3] for c in runner.calls if len(c["argv"]) >= 4 and c["argv"][1] == "cli"]
    assert "list_projects" in tools
    assert "index_status" in tools


def test_incompatible_schema_on_status():
    adapter, _runner = _adapter(
        {
            "tool:list_projects": CliRunResult(
                returncode=0, stdout=_load("v09_list_projects_wrapped.json"), stderr=""
            ),
            "tool:index_status": CliRunResult(
                returncode=0, stdout=_load("incompatible_schema.txt"), stderr=""
            ),
            "version": CliRunResult(returncode=0, stdout=_load("version_09.txt"), stderr=""),
        }
    )
    with pytest.raises(CodebaseMemoryCliError) as exc:
        adapter.status()
    assert exc.value.code == "provider_incompatible"


# --- compatibility probe ---


def test_compatibility_probe_ok_without_index_repository_call():
    adapter, runner = _adapter(
        {
            "version": CliRunResult(returncode=0, stdout=_load("version_09.txt"), stderr=""),
            "help": CliRunResult(returncode=0, stdout=_load("help_tools_ok.txt"), stderr=""),
            "config_list": CliRunResult(
                returncode=0, stdout=_load("config_list_auto_watch_false.txt"), stderr=""
            ),
            "tool:list_projects": CliRunResult(
                returncode=0, stdout=_load("v09_list_projects_wrapped.json"), stderr=""
            ),
        }
    )
    probe = adapter.probe_compatibility()
    assert probe.ok is True
    assert probe.compatible is True
    assert probe.provider_version == "0.9.0"
    assert probe.auto_watch_effective is False
    assert set(probe.missing_tools) == set()
    invoked_tools = [
        c["argv"][3] for c in runner.calls if len(c["argv"]) >= 4 and c["argv"][1] == "cli"
    ]
    assert "list_projects" in invoked_tools
    assert "index_repository" not in invoked_tools


def test_compatibility_probe_missing_tools_incompatible():
    adapter, runner = _adapter(
        {
            "version": CliRunResult(returncode=0, stdout=_load("version_081.txt"), stderr=""),
            "help": CliRunResult(returncode=0, stdout=_load("help_tools_missing.txt"), stderr=""),
            "config_list": CliRunResult(
                returncode=0, stdout=_load("config_list_no_auto_watch.txt"), stderr=""
            ),
            "tool:list_projects": CliRunResult(
                returncode=0, stdout=_load("v09_list_projects_wrapped.json"), stderr=""
            ),
        }
    )
    probe = adapter.probe_compatibility()
    assert probe.compatible is False
    assert probe.reason == "provider_incompatible"
    assert "index_repository" in probe.missing_tools
    assert "trace_path" in probe.missing_tools
    assert not any(
        len(c["argv"]) >= 4 and c["argv"][3] == "index_repository" for c in runner.calls
    )


def test_compatibility_probe_unobservable_auto_watch():
    adapter, _runner = _adapter(
        {
            "version": CliRunResult(returncode=0, stdout=_load("version_081.txt"), stderr=""),
            "help": CliRunResult(returncode=0, stdout=_load("help_tools_ok.txt"), stderr=""),
            "config_list": CliRunResult(
                returncode=0, stdout=_load("config_list_no_auto_watch.txt"), stderr=""
            ),
            "tool:list_projects": CliRunResult(
                returncode=0, stdout=_load("v09_list_projects_wrapped.json"), stderr=""
            ),
        }
    )
    probe = adapter.probe_compatibility()
    assert probe.compatible is True
    assert probe.auto_watch_effective is None


# --- mapped operations ---


def test_search_maps_to_search_graph_bm25_query():
    adapter, runner = _adapter(
        {
            "tool:search_graph": CliRunResult(
                returncode=0, stdout=_load("v09_search_wrapped.json"), stderr=""
            ),
            "version": CliRunResult(returncode=0, stdout=_load("version_09.txt"), stderr=""),
        }
    )
    result = adapter.search(query="Alpha", limit=5)
    assert result.returned == 1
    assert result.items[0].qualified_name == "demo.mod.Alpha"
    argv = runner.calls[0]["argv"]
    assert argv[3] == "search_graph"
    args = json.loads(argv[4])
    assert args["query"] == "Alpha"
    assert args["limit"] == 5
    assert "semantic_query" not in args


def test_trace_impact_architecture_mapping():
    adapter, runner = _adapter(
        {
            "tool:trace_path": CliRunResult(
                returncode=0, stdout=_load("v09_trace_wrapped.json"), stderr=""
            ),
            "tool:detect_changes": CliRunResult(
                returncode=0, stdout=_load("v09_detect_changes_wrapped.json"), stderr=""
            ),
            "tool:get_architecture": CliRunResult(
                returncode=0, stdout=_load("v09_architecture_wrapped.json"), stderr=""
            ),
        }
    )
    trace = adapter.trace(symbol="demo.mod.Alpha", direction="both", depth=2)
    assert trace.nodes
    impact = adapter.impact(since="HEAD~1", depth=2)
    assert impact.symbols
    arch = adapter.architecture()
    assert arch.clusters
    tools = [c["argv"][3] for c in runner.calls]
    assert tools == ["trace_path", "detect_changes", "get_architecture"]


def test_reindex_sets_cbm_allowed_root_and_fast_no_persistence():
    adapter, runner = _adapter(
        {
            "tool:index_repository": CliRunResult(
                returncode=0, stdout=_load("v09_reindex_ok_wrapped.json"), stderr=""
            ),
            "version": CliRunResult(returncode=0, stdout=_load("version_09.txt"), stderr=""),
        },
        repo_root="/repo/demo",
    )
    result = adapter.reindex(mode="fast", persistence=False, index_commit="abc123")
    assert result.ok is True
    assert result.mutation_performed is True
    reindex_calls = [
        c for c in runner.calls if len(c["argv"]) >= 4 and c["argv"][3] == "index_repository"
    ]
    assert len(reindex_calls) == 1
    call = reindex_calls[0]
    args = json.loads(call["argv"][4])
    assert args["mode"] == "fast"
    assert args["persistence"] is False
    assert args["repo_path"] == "/repo/demo"
    assert call["env"] is not None
    assert call["env"]["CBM_ALLOWED_ROOT"] == "/repo/demo"
    assert call["timeout_sec"] == 600


def test_default_subprocess_runner_signature_is_argv_only():
    assert callable(subprocess_codebase_memory_runner)


def test_v081_status_via_direct_log_prefix_fixture():
    adapter, runner = _adapter(
        {
            "tool:list_projects": CliRunResult(
                returncode=0,
                stdout=(
                    "level=info msg=mem.init budget_mb=1 total_ram_mb=2\n"
                    + json.dumps(
                        {
                            "projects": [
                                {
                                    "name": "demo-project",
                                    "root_path": "/repo/demo",
                                    "nodes": 511,
                                    "edges": 1047,
                                }
                            ]
                        }
                    )
                ),
                stderr="",
            ),
            "tool:index_status": CliRunResult(
                returncode=0, stdout=_load("v081_index_status_log_prefix.txt"), stderr=""
            ),
            "version": CliRunResult(returncode=0, stdout=_load("version_081.txt"), stderr=""),
        }
    )
    status = adapter.status()
    assert status.provider == "codebase_memory"
    assert status.provider_project == "demo-project"
    assert status.node_count == 511
    assert status.edge_count == 1047
    assert status.index_state == "ready"
    assert status.index_commit is None
    tool_calls = [c["argv"][3] for c in runner.calls if len(c["argv"]) >= 4 and c["argv"][1] == "cli"]
    assert tool_calls == ["list_projects", "index_status"]
