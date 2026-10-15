# Task — consumer path A (agent daily)

**Audience:** coding agents using Vibe in a consumer repo  
**Status:** docs-only (aligned with `sync/20260717-knowledge-task-polish-strategy.md`)  
**Not:** managed live `vibe task apply` (path B — non-default)

## When to use Vibe vs Beads

| Need | Use |
|---|---|
| Is task capability / Beads usable? | `vibe task status --json` / `vibe doctor --json` |
| What can I work on? | `bd ready` |
| Status / links / blockers | `bd show` / `bd list` / `bd blocked` / `bd dep …` |
| Create / claim / close | `bd create` / `bd update --claim` / `bd close` |
| SSOT→Beads managed projection | path B only — do **not** use daily |

## Minimal loop

```text
vibe task status --json          # expect TASK_READY (or follow next_actions)
bd ready
bd update <id> --claim           # or equivalent in_progress flow
# … implement …
bd create "…"                    # if you discover follow-up work mid-flight
bd close <id> --reason "…"
```

## Do not

- Re-implement task graphs inside Vibe (Beads already has `bd dep`)
- Treat `vibe task apply --provider beads` as the default consumer workflow
- Keep the plan only in chat — file discoveries with `bd create`

## See also

- HF scenarios T-A…T-H → `docs/project/agent-scenario-research.md`
- Strategy → `docs/project/sync/20260717-knowledge-task-polish-strategy.md`
- Index → `docs/project/PRODUCT_THINKING_INDEX.md`
