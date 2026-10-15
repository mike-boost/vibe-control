# Vibe Control

**Open-source CLI** for coding-agent workflows.

Vibe Control helps a coding agent (and the humans who set boundaries) install one
control layer, optionally enable **knowledge** and/or **task** features, and
validate setup with `vibe doctor` — without turning every repo into a custom
tooling project.

**Status:** open source (MIT) · [github.com/mike-boost/vibe-control](https://github.com/mike-boost/vibe-control)

## Who uses it

- **Primary operator:** coding agents via the `vibe` CLI
- **Humans:** set config boundaries, approvals, and review doctor / feedback output
- **First consumer target:** other coding-agent projects

## What you can enable (this release)

| Feature | Config | Role |
|---|---|---|
| `knowledge` | `components.knowledge.enabled` | Optional knowledge / NotebookLM-backed corpus (when configured) |
| `task` | `components.task.enabled` | Optional Beads-backed task provider (when configured) |

Everything else in the Capability Profile defaults to **disabled**. There is **no
silent auto-enable**. `sdd` / `tdd` are **not supported yet** — do not enable them.

Provider names (`notebooklm`, `beads`) are **not** component IDs.

## Quickstart

### 1. Install

**Recommended (no pipx / no PyPI):** clone the repo (or download a release source
tarball), then run the user installer — it builds an isolated venv and puts
`vibe` on `~/.local/bin`:

```bash
git clone git@github.com:mike-boost/vibe-control.git
cd vibe-control
git checkout v0.5.14   # or stay on main
./scripts/install-user.sh
vibe --version
# expected: vibe-control 0.5.14
```

After `git pull` / local changes, upgrade from the same checkout:

```bash
./scripts/install-user.sh --upgrade
# or simply:
./scripts/install-user.sh
```

If Python changed (e.g. conda env) and the old venv should be rebuilt:

```bash
./scripts/install-user.sh --recreate
```

Status / uninstall:

```bash
./scripts/install-user.sh --status
./scripts/install-user.sh --uninstall
```

Ensure `~/.local/bin` is on your `PATH` (common on macOS/Linux).
Requires **Python 3.11+**. If `python3` is 3.10, activate a newer env first
(`conda activate …`) or set `VIBE_PYTHON=/path/to/python3.13`.

The installer also aligns **thin agent skills** into `~/.agents/skills` (symlink to
the installed package). Skip with `VIBE_SKIP_SKILLS=1`. Check anytime:

```bash
vibe skills status --json
vibe doctor --json   # surfaces skills missing/mismatch + next_actions
```

**Optional — pipx** (if you already use it):

```bash
pipx install "git+ssh://git@github.com/mike-boost/vibe-control.git@v0.5.1"
vibe --version
```

Update with pipx:

```bash
pipx upgrade vibe-control
# or reinstall from a newer tag:
pipx install --force "git+ssh://git@github.com/mike-boost/vibe-control.git@v0.5.1"
```

**Contributors / local editable install** (this repo, for development):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
vibe --version
```

PyPI is **out of scope** for this release.

### 2. Configure (optional)

No config is fine: capabilities stay disabled; `vibe doctor` still validates the
engine / environment.

To add a fresh project config:

```bash
mkdir -p .config
# from an installed package template path, or from this repo:
cp "$(python -c 'from vibe_control.config import template_path; print(template_path())')" \
  .config/vibe-control.yaml
# edit project.id / project.name
```

Discovery order:

1. `--config <path>`
2. `VIBE_CONTROL_CONFIG`
3. `.config/vibe-control.yaml` (primary)
4. `.vibe/control.yaml` (legacy)

Details: [`docs/configuration.md`](docs/configuration.md)
Auth for agents: [`docs/authentication.md`](docs/authentication.md)

### 3. Enable only what you need

In `.config/vibe-control.yaml`:

```yaml
components:
  knowledge:
    enabled: false   # set true only when knowledge is ready
  task:
    enabled: false   # set true only when task/Beads is ready
```

When enabling a feature, also complete that feature’s provider settings (no
secrets in git — use local env / `.config/.env` as documented for providers).

Knowledge provider is owner-explicit (`local_fts` \| `notebooklm`). Prefer
`local_fts` for a free local evidence index; use `notebooklm` only when you want
cloud RAG. Details: [`docs/configuration.md`](docs/configuration.md) and
[`docs/project/sync/20260721-knowledge-local-fts-provider-spec.md`](docs/project/sync/20260721-knowledge-local-fts-provider-spec.md).

### 4. Validate

```bash
vibe doctor
vibe doctor --json   # for coding-agent automation
```

Treat doctor as the **user validation** command. Fix what it reports before
enabling providers in production workflows.

### 5. Feedback

File issues on the [GitHub repo](https://github.com/mike-boost/vibe-control/issues) (bug / feature templates).

Include `vibe --version`, install method, OS/Python, whether knowledge/task are
enabled, and a **redacted** `vibe doctor --json` output.

See [`docs/feedback.md`](docs/feedback.md). **Do not** attach tokens, cookies,
`.env`, or raw private provider refs/IDs.

## Rights

MIT licensed. See [`LICENSE`](LICENSE).

## Maintainer / advanced (not Getting Started)

Dogfood / this-repo-only surfaces (**consumer agents usually skip**):

- `vibe implementation next` / closeout orchestration
- This repo’s `roadmap-state` / historical phase docs under `docs/project/`

Agent-facing control surfaces (readonly; useful after install):

- `vibe describe --json` — control-surface self-explain (preferred over reading product git docs)
- `vibe doctor --json` / `vibe brief` / `vibe progress` / `vibe gateway`

Product thinking (scenario research + settled polish strategy):

- [`docs/project/PRODUCT_THINKING_INDEX.md`](docs/project/PRODUCT_THINKING_INDEX.md)
- Task daily path A: [`docs/task-consumer-path.md`](docs/task-consumer-path.md)

Release process (tag, GitHub Release, install from tag): [`docs/release.md`](docs/release.md)

## Tests (contributors)

```bash
pytest -q
```
