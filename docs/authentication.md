# Authentication (agent-facing)

Vibe Control does **not** invent a new login system.

## Principle

| Layer | Who owns auth |
|---|---|
| Vibe CLI | Reads provider readiness; never stores Google passwords |
| NotebookLM | `notebooklm login` + local profile under `~/.notebooklm/` |
| Beads | Local `bd` binary; no cloud login for embedded mode |
| Consumer repo | Puts notebook **refs** in gitignored `.config/.env` only |

Coding agents should treat auth as:

1. `vibe knowledge auth-status --json` — is a session already available?
2. If not → `vibe knowledge login-guide --json` → human runs `notebooklm login`
3. Re-check auth-status
4. Never commit cookies, tokens, storage_state, or notebook IDs

## What agents may do autonomously

- Readonly auth-status / login-guide
- Use an **already available** NotebookLM session
- Write notebook ref to **gitignored** `.config/.env`
- Enable `components.knowledge` / `components.task` in committed yaml (no secrets)
- `knowledge sync --dry-run` then `--apply` when dry-run shows only managed add/update for the consumer corpus
- `bd init --skip-agents` when `vibe task init-preview` recommends it for a fresh consumer

## What still needs a human

- First-time `notebooklm login` (browser / interactive)
- Re-login when `auth_state` is failed/expired
- Approving destructive NotebookLM cleanup / unmanaged deletes
- Live Beads apply beyond local init (repo live-apply gates)

## Local files (env)

| Key | Required? | Purpose |
|---|---|---|
| `NOTEBOOKLM_NOTEBOOK_<ALIAS>` | Yes, if knowledge enabled | Notebook id/ref for that alias |
| `VIBE_CONTROL_CONFIG` | Optional | Override control.yaml path |
| NotebookLM profile | Optional | Use `notebooklm -p <profile>`; not required in `.env` today |

Do **not** put Google passwords, cookies, or `storage_state` paths into the repo env file.
Those live under `~/.notebooklm/` after `notebooklm login`.

Preferences that are *nice to have* but are **not** required for v0.5.x:

- default notebook alias override
- agent “no live sync / no live beads apply” policy flags
- doctor always-json preference

Document them in `.config/env.example` as proposals; only ship wiring when an agent
workflow repeatedly needs them.
