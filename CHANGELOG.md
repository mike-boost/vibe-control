# Changelog

All notable releases of Vibe Control are recorded here.
Format follows a simple Keep a Changelog style for releases.

## [0.5.14]

Tag: `v0.5.14`.

### Fixed

- Revived the full test suite: baseline 79 failed / 916 passed → **995 passed,
  0 failed, 2 skipped** (the 2 skips are opt-in real-host tests). All failures
  were environment/test drift; `src/` needed zero changes.
- `tests/test_harness_tiers.py`: fast-marker expression updated to also exclude
  `real_skill_host`, matching the other real-provider markers
- `tests/test_skill_assay_real_host.py`: skip the `cursor` real-host doctor check
  when the `agent` CLI is not installed
- `acceptance/phase2/fixtures/migration-harness-mini`: added the missing
  `.vibe/control.yaml` fixture config required by the acceptance runner

### Changed

- Knowledge: NotebookLM extra now requires `notebooklm-py>=0.8.5`
  (was the `>=0.8.0a3` alpha); matches the actively maintained upstream
- Knowledge: `auth-status` no longer trusts exit code 0 alone — when the
  `notebooklm auth check --json` payload explicitly reports failure
  (`status != "ok"` or `checks.token_fetch` false), it is reported as
  auth failed instead of available (false-positive trap of older CLIs)

### Notes

- Maintenance-revival patch; NotebookLM auth-status hardening (see Changed).
- Verified: `vibe --version` → `vibe-control 0.5.14`, `vibe doctor --json` → `ok: true`.

## [0.5.13]

Tag: `v0.5.13`.

### Added

- Knowledge **format policy per provider**: `local_fts` indexes `.md`/`.markdown`/`.txt`
  only; `notebooklm` (Gemini Notebook) follows Google upload allowlist (docs/images/AV)
- `communication_contracts.owner_plain_language`: agents must talk to the owner without
  unexplained jargon

### Changed

- Sync/index skips unsupported formats with clear warnings (`skip_unsupported_format` /
  `format_skipped`); upload filenames keep the real extension
- Harness docs (`knowledge-provider-boundary`, configuration) document the split

### Evidence

- `tests/test_format_policy.py` covers both providers (dry-run/apply/status + notebooklm plan)
- Focused local_fts / describe communication tests green

## [0.5.12]

Tag: `v0.5.12`.

### Added

- Knowledge provider **`local_fts`** (SQLite FTS5): owner-explicit free evidence
  retrieval with Read-aligned `path` + `line_start`/`line_end`; trigram + LIKE
  for CJK; atomic rebuild; no remote NotebookLM required for knowledge half
- `vibe knowledge fts-purge --dry-run|--apply` (orphan scopes + `*.sqlite.tmp`;
  `--all --confirm-all` wipes project local_fts tree)
- `communication_contracts.git_land` via `vibe describe --json`: local commit/land
  is agent-owned; never ask owner “shall I commit?”

### Changed

- Doctor / readiness / query / sync / retry / cleanup-candidates / remote-inventory
  branch correctly for `local_fts`
- Dirty-tree `COMMIT_OR_CLEAN_LOCAL_STATE` reason + Brief approval line + skills
  + phase/ssot harness docs project git_land ownership
- Template comments recommend `local_fts` (default remains `notebooklm` for compat)

### Evidence

- `tests/test_local_fts_*.py` + git_land describe projection green
- Focused closeout / self-grill communication tests green

## [0.5.11]

Tag: `v0.5.11`.

### Added

- Knowledge **multi-notebook / target-scoped corpus**: per-notebook selectors
  (`path_prefixes` / `include_extra` / `exclude_globs` / `corpus_mode`);
  `--notebook` required when `allow_list` length ≥ 2; no cross-notebook ask;
  non-default `sync --apply` needs `--confirm-non-default-sync`;
  `product_ready` / bounded closeout track `default_alias` only
- Agent **self-grill** communication contract (`describe` + Gateway `grill_brief`);
  local session loop under `runtime/vibe-grill/` (`grill_id` + `round_id` from 0);
  thin CLI `vibe grill status|checkpoint|close`
- Progress/Brief pull-back while grill `IN_PROGRESS`; `implementation prompt`
  fail-closed with `SELF_GRILL_IN_PROGRESS` until close
- Release-notes tooling: `scripts/extract-release-notes.py` +
  `scripts/gh-sync-release-notes.sh` (version-scoped GitHub notes; never dump
  whole CHANGELOG)

### Changed

- `docs/release.md` requires per-version GitHub Release notes forever
- Front-door skills point at `grill_brief` / grill session close path
  (no installable `vibe-self-grill` skill)

### Evidence

- Focused multi-notebook + self-grill session tests green
- `scripts/test-closeout-local-fast.sh` + `scripts/test-full-local-readonly.sh` green

## [0.5.10]

Tag: `v0.5.10`.

### Added

- Knowledge Ask Template `vibe.knowledge.ask.v3` with required **Sources** section
- Query provenance enrichment: NotebookLM citations → receipt-bound `doc_id` / `path` / `title`
- `CHECK_CORPUS_INVENTORY` next_action when Evidence insufficient or repo fallback finds no hits

### Changed

- AGENTS harness: git land/release is agent work — do not ask the owner for commit permission
- Knowledge ask harness / skill docs aligned to v3 + envelope `data.sources[]`

### Fixed

- Phase 2 / 9-10 / 11A / 11B acceptance seeds enable knowledge (and task when needed) under Capability Profile defaults
- Phase 2 version check accepts `vibe-control 0.*`
- Provider-readiness acceptance probes with capabilities enabled (disabled caps must not false-green)
- `scripts/test-acceptance-readonly.sh` restores `set -euo pipefail` (was glued onto a comment)
- Front/Core concept-boundary test aligned with Hetu peer capability wording

### Evidence

- `scripts/test-full-local-readonly.sh` + `VIBE_ACCEPTANCE_LOCAL=1 scripts/test-acceptance-readonly.sh` green
- Focused ask/provenance tests green
- `acceptance/phase2` + `phase11a` PASSED

## [0.5.9]

Tag: `v0.5.9`.

### Added

- Knowledge multi-file sync throughput path via notebooklm-py API:
  concurrent `add_file(wait=False)` + `wait_for_sources` (`--ingest-path auto|api|cli`)
- `--upload-concurrency N` (default **8**, max 16) — in-flight single-file uploads, not a bulk RPC
- Apply `scale.stage_ms.{add,wait,verify}` for honest timing
- Agent disclosure choices for ingest path + upload concurrency
- Optional dependency: `pip install 'vibe-control[notebooklm]'`

### Changed

- Default multi-file ingest prefers API when `notebooklm` is importable (`ingest_path=auto`)
- Measure script accepts `--ingest-path` / `--upload-concurrency`

### Evidence

- SE corpus N=10 CLI serial ~94s → API concurrent ~27s (~3.5×)
- N=12 concurrency 8 vs 12 ≈ tied (~25s / ~24s); default set to 8

## [0.5.8]

Tag: `v0.5.8`.

### Fixed

- Capability Profile test/config drift after default-disabled gate
- Test seeds that exercise knowledge/task now enable those capabilities
- Dogfood `.config` enables knowledge + task
- Closeout `implementation_ready` aligns with Progress semantics
- Missing control.yaml is reported as `CONFIG_NOT_FOUND` (not silent capability skip)

## [0.5.7]

Tag: `v0.5.7`.

### Added

- `vibe readme` — alias of `vibe describe` (runtime self-explain)
- `vibe feedback draft --attach-doctor` — attach redacted doctor JSON snippet
- `vibe diagnostics bundle --redacted` — local redacted doctor+skills zip
- Packaged `templates/gitignore.consumer.example` for `runtime/vibe-feedback/`

### Changed

- Top-level help labels `implementation` / `closeout` as maintainer/dogfood

## [0.5.5]

Tag: `v0.5.5`.

### Fixed / docs

- `capability_profile.default_disabled` is false when any capability is enabled
- Added `docs/authentication.md` — Vibe reuses provider login; agents use auth-status / login-guide

## [0.5.4]


Tag: `v0.5.4`.

### Fixed

- Capability Profile resolution honors `--config` / `VIBE_CONTROL_CONFIG`
  (doctor + knowledge/task capability gates)
- Enablement smoke no longer silently reads the default project yaml when
  an alternate config is passed

### Docs

- Expanded `docs/configuration.md` enable/disable handbook from first-consumer evidence

## [0.5.3]

Tag: `v0.5.3`.

### Fixed (consumer validation on vibe-control-site)

- When `components.knowledge.enabled=false`, knowledge doctor/status/inventory/query skip provider probes
- When `components.task.enabled=false`, task doctor/status skip provider probes
- Clear `capability_disabled` / `skipped` envelope + enable preview next_action

### Why

First-consumer smoke showed disabled capabilities still ran NotebookLM/Beads diagnostics.
User path expects: doctor for validation; enable features only when intentional.

## [0.5.2]

Tag: `v0.5.2`.

### Added / fixed

- `scripts/install-user.sh` supports `--upgrade` (default), `--uninstall`, `--status`, `--recreate`
- Prefer `python` / 3.11+ candidates; recreate venv when interpreter major.minor changes
- `vibe doctor` default output is a short human summary; `--json` unchanged for agents

### Install / upgrade loop

```bash
cd ~/Documents/repo/ai/vibe-control
./scripts/install-user.sh            # install or upgrade from current tree
./scripts/install-user.sh --upgrade  # explicit
./scripts/install-user.sh --recreate # wipe venv if Python changed
./scripts/install-user.sh --status
./scripts/install-user.sh --uninstall
vibe doctor
```

## [0.5.1]

Tag: `v0.5.1`.

### Added

- `scripts/install-user.sh` — clone/download source → isolated user venv → `~/.local/bin/vibe`
- README primary install path is source installer; pipx remains optional
- No PyPI

### Install

```bash
git clone git@github.com:mike-boost/vibe-control.git
cd vibe-control && git checkout v0.5.1
./scripts/install-user.sh
vibe --version
vibe doctor
```

## [0.5.0]

Repo: `mike-boost/vibe-control`.
Tag: `v0.5.0`.

### Added

- Installable CLI package `vibe-control` with console script `vibe`
- Capability Profile: optional `knowledge` and `task` (default disabled)
- `vibe doctor` / `vibe doctor --json` as the primary user validation surface
- Config template at `src/vibe_control/templates/control.yaml` for fresh projects
- Product README, proprietary LICENSE, GitHub issue forms, maintainer release runbook

### Out of scope

- PyPI publication
- Public open-source license
- User-facing SDD / TDD features
- Marketplace / plugin framework
