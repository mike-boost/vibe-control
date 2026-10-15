# Redacted codebase-memory-mcp CLI fixtures (Hetu Task 3)

Captured/accepted shapes for unit tests only. Absolute paths and owner project
names are replaced with `/repo/demo` / `demo-project`. Do not commit secrets.

| Fixture | Shape |
|---|---|
| `v081_*_log_prefix.txt` | Observed 0.8.1 leading `level=info` + final JSON |
| `v09_*_wrapped.json` | Accepted 0.9.x `--json` MCP content wrapper (no log prefix) |
| `help_*.txt` | `--help` tool inventory for compatibility probe |
| `config_list_*.txt` | `config list` human text |
