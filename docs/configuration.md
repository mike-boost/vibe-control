# Configuration

User-facing configuration for Vibe Control.

Primary file: `.config/vibe-control.yaml`  
Packaged template: `src/vibe_control/templates/control.yaml` (via `vibe_control.config.template_path`)

## Principles

- **Default disabled** — omit config, or keep `components.*.enabled: false`
- **No silent auto-enable**
- **Enableable features for this release:** `knowledge`, `task`
- **Not supported yet:** `sdd`, `tdd` (do not enable; fail closed if enabled)
- **No secrets in config** — notebook refs, tokens, cookies stay in local env / gitignored files
- Provider names (`notebooklm`, `beads`) are **not** component IDs

## Discovery order

1. `--config <path>`
2. `VIBE_CONTROL_CONFIG`
3. `.config/vibe-control.yaml`
4. `.vibe/control.yaml` (legacy)

`--config` applies to Capability Profile gates as well (doctor + knowledge/task commands).

## Minimal Capability Profile

```yaml
components:
  knowledge:
    enabled: false
  task:
    enabled: false
```

Copy the packaged template for a full valid skeleton (`project`, `knowledge`,
`specs`, `tasks` sections are required by config validate even when features are
disabled). Then set `project.id` / `project.name` for your repo.

## Default-disabled behavior (verified)

With both capabilities off:

```bash
vibe doctor                 # ok; default_disabled=true; mutation=false
vibe knowledge doctor --json
# data.capability_disabled=true, skipped=true  (no NotebookLM probe)
vibe task doctor --json
# data.capability_disabled=true, skipped=true  (no Beads probe)
```

## Enable knowledge

1. Set `components.knowledge.enabled: true`
2. Ensure `knowledge:` + `specs.registry` exist and match your repo
3. Choose provider (owner-explicit; no auto-switch):
   - **`local_fts`** (recommended free path): local SQLite FTS5 evidence retrieval.
     No NotebookLM binary/auth. Index under
     `~/.agents/state/vibe-control/{project_id}/local_fts/{scope}/index.sqlite`.
     Query returns path + line ranges; the agent reasons (Facts/MUST). Rebuild via
     `vibe knowledge sync --apply` (or `retry`). Purge orphans/tmp with
     `vibe knowledge fts-purge --dry-run|--apply` (`--all --confirm-all` wipes all).
   - **`notebooklm`**: cloud RAG / synthesis. Configure notebook refs **locally**
     (env / gitignored `.config/.env`) — never commit secrets.
4. Validate:

```bash
vibe doctor
vibe doctor --json
vibe knowledge doctor --json
vibe knowledge status --json
```

Expected after enable (before provider is fully ready):

- `capability_profile.knowledge_enabled=true`
- knowledge commands are **not** `skipped`
- doctor / knowledge doctor report gaps via `next_actions`
- **Do not** run `knowledge sync --apply` until dry-run is clean and (for notebooklm) owner approves remote mutation

### local_fts notes

- Switching provider leaves the other provider's state alone (switch starts at drift).
- `--notebook <alias>` scopes the **corpus bucket** (path_prefixes / selectors), not a remote notebook, when `provider=local_fts`.
- `remote-inventory` is N/A; use `inventory` / `status` / `fts-purge`.
- Reload = rebuild: after SSOT edits, `sync --apply` or closeout apply.
- **Formats:** only `.md` / `.markdown` / `.txt` are indexed. Other paths are skipped with a clear warning. Gemini Notebook can accept more formats when `provider=notebooklm` — see `docs/harness/knowledge-provider-boundary.md`.

## Enable task

1. Set `components.task.enabled: true`
2. Ensure `tasks.provider` (typically `beads`) is set
3. Validate:

```bash
vibe doctor
vibe task doctor --json
vibe task status --json
```

Expected after enable:

- `capability_profile.task_enabled=true`
- task commands are **not** `skipped`
- follow `next_actions` for Beads install / init-preview
- **Do not** run live Beads `--apply` without the repo’s live-apply gates

## Enable Hetu (optional codebase structure memory)

1. Set `components.hetu.enabled: true`
2. Keep `hetu.provider: codebase_memory` (default) and `hetu.freshness_policy: strict`
3. Ensure the provider can prove `auto_watch` is effectively **false** before reindex
4. Validate:

```bash
vibe doctor
vibe hetu doctor --json
vibe hetu status --json
```

Expected after enable:

- `capability_profile.hetu_enabled=true`
- non-ready index states block `product_ready` and closeout (closeout never auto-reindexes)
- reindex apply requires `--expect-plan-binding` + `--confirm-hetu-reindex-apply` (no env dual gate)

## Enable both Knowledge and Task

Same as above for each side. Keep `sdd` / `tdd` disabled unless intentionally researching.

## Disable again

Set `components.<id>.enabled: false`. Disabled optional features must not fail engine readiness;
feature commands return to `skipped`.

## Safe preview without editing the project file

```bash
# copy config, flip enabled, pass --config
vibe doctor --config /tmp/vibe-knowledge-on.yaml --json
vibe knowledge doctor --config /tmp/vibe-knowledge-on.yaml --json
```

## What not to put in consumer configs

- This repo’s dogfood `project.id` / migration aliases
- Roadmap-state / `roadmap.*` anchors
- Notebook IDs, tokens, cookies
- Enabling `sdd` / `tdd` “to try them”
