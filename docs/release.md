# Release (maintainers)

GitHub release runbook for Vibe Control.

## Product facts

| Item | Value |
|---|---|
| Package name | `vibe-control` |
| Console script | `vibe` |
| Version metadata | `pyproject.toml` → `project.version` (currently `0.5.14`) |
| Preferred tag | `v0.5.14` (align with package version) |
| GitHub repo | `mike-boost/vibe-control` |
| Visibility | public |
| Channel | GitHub repo + GitHub Release |
| PyPI | **Out of scope** |
| License | MIT — see `LICENSE` |

## Release notes policy (required)

Every GitHub Release **must** have a **version-scoped** body:

- Source of truth: the matching `## [X.Y.Z]` section in `CHANGELOG.md`
- Format: `scripts/extract-release-notes.py X.Y.Z` → Summary + Install + pointer to CHANGELOG
- **Never** pass the whole `CHANGELOG.md` to `gh release create --notes-file`
  (that dumps other versions into one release and looks empty/broken in the UI)

```bash
# Preview notes for this version
python3 scripts/extract-release-notes.py 0.5.13

# After create, or to repair historical releases:
scripts/gh-sync-release-notes.sh 0.5.13
scripts/gh-sync-release-notes.sh --all          # backfill / repair all CHANGELOG versions
scripts/gh-sync-release-notes.sh --check 0.5.13 # drift check
```

Skipped SemVer holes (e.g. no `v0.5.6` tag) stay skipped — do not invent releases.

## Preconditions

- [ ] `git status --short` clean on the release commit
- [ ] `vibe --version` matches intended release (`vibe-control 0.5.13`)
- [ ] README / CHANGELOG / LICENSE reflect public release intent
- [ ] Remote points at `mike-boost/vibe-control`
- [ ] `scripts/test-full-local-readonly.sh` green (or equivalent maintainer gate)
- [ ] Release notes previewed via `extract-release-notes.py` (not whole CHANGELOG)

## One-time: create company repo + remote

```bash
gh repo create mike-boost/vibe-control \
  --public \
  --description "CLI control layer for coding-agent workflows (knowledge + task + optional hetu + skill-assay)" \
  --source=. \
  --remote=origin \
  --push

gh repo view mike-boost/vibe-control \
  --json nameWithOwner,visibility,defaultBranchRef,url
```

If the remote already exists, skip create and only push.

## Tag + GitHub Release

Use an **annotated** tag matching package SemVer (`v` + `project.version`):

```bash
VER=0.5.13
TAG=v${VER}

python3 scripts/extract-release-notes.py "$VER" > /tmp/vibe-release-notes.md

git tag -a "$TAG" -m "$(cat <<EOF
Vibe Control ${VER}

See CHANGELOG.md [${VER}] and GitHub Release notes.
EOF
)"

git push origin main
git push origin "$TAG"

gh release create "$TAG" \
  --repo mike-boost/vibe-control \
  --title "Vibe Control ${VER}" \
  --notes-file /tmp/vibe-release-notes.md
```

Optional later: attach `sdist`/`wheel` built with `python -m build` — not required
for first `pipx` git-tag install.

## Consumer install / update / verify / uninstall

**Recommended — source checkout + user installer** (no pipx / no PyPI):

```bash
git clone git@github.com:mike-boost/vibe-control.git
cd vibe-control
git checkout v0.5.13
./scripts/install-user.sh
vibe --version
./scripts/install-user.sh --uninstall   # when removing
```

**Optional — pipx** from the GitHub tag:

```bash
# install
pipx install "git+ssh://git@github.com/mike-boost/vibe-control.git@v0.5.13"
vibe --version

# update to a newer tag
pipx install --force "git+ssh://git@github.com/mike-boost/vibe-control.git@vX.Y.Z"
# or, if the same package name is already managed by pipx:
pipx upgrade vibe-control

# rollback: reinstall previous tag
pipx install --force "git+ssh://git@github.com/mike-boost/vibe-control.git@v0.5.10"

# uninstall
pipx uninstall vibe-control
```

## After release: first consumer smoke

1. Install Vibe from the GitHub tag (not from an unrelated local editable unless intentional)
2. `vibe --version`
3. Optional: copy fresh template → `.config/vibe-control.yaml` (default disabled)
4. `vibe doctor` / `vibe doctor --json`
5. Confirm no unexpected provider/secret writes
6. Optionally link the project README to the GitHub repo / release

Do **not** copy this repo’s dogfood `roadmap-state` into the consumer.

## Explicitly not in this runbook

- PyPI upload
- Auto-telemetry
- Mutating NotebookLM / Beads as part of “releasing the CLI”
