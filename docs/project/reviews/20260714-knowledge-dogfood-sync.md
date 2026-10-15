# 2026-07-14 — Knowledge dogfood sync for current SSOT

**Scope:** bounded NotebookLM sync/query dogfood (not Phase 11B)  
**Target:** provider=`notebooklm`, alias=`OPM-test`, `target_key_hash=sha256:3552d1cb…` (raw notebook ref redacted)

## Result

- `vibe knowledge status` → `sync_state=synced` for desired SSOT (`vibe_control_spec`, `DECISION_LOG`)
- Phase 8 scoped receipt + local ack mirror updated; `cleanup_pending=[]`
- Provider query path works via `notebooklm ask` + Knowledge Ask Template (`default_ssot_facts` / `vibe.knowledge.ask.v1`)
- After consistency hardening: `sync --dry-run` uses the same Phase 8 planner as status (scoped receipt + desired_snapshot). Current SSOT docs must show `already_current` when status is synced. `orphan_managed(vibe_control_v0_5_spec)` is still present on the provider and is an owner **DELETE MANUALLY** ask-pollution cleanup item (CLI will not auto-delete).

## Mutations performed

- `vibe knowledge sync --apply --json` (initial converge / ack)
- `vibe knowledge retry --apply --json` after `VERIFY_FAILED`

### Why `retry --apply` was needed

1. First `sync --apply` added `vibe_control_spec` and wrote Phase 8 ack as synced.
2. `DECISION_LOG` had been reindexed onto an older remote binding without hashed upload filename identity.
3. A receipt-owned replace was forced for current `DECISION_LOG`. The first replace uploaded via original basename, so NotebookLM titled the source `DECISION_LOG.md`. Final probe could not match managed/`upload_filename` identity → `VERIFY_FAILED` / `missing:DECISION_LOG` and `pending-sync`.
4. After fixing Phase 8 upload-to-hashed-filename, `retry --apply` re-ran forward sync for the **receipt-owned current SSOT binding** (`DECISION_LOG` only among required replaces), verified probe, wrote ack, cleared pending.

### What was cleaned

- Receipt-owned previous `DECISION_LOG` provider source id (exact id from scoped receipt), after new hashed upload verified.
- No unmanaged source delete.
- No broad notebook clean.
- Remote orphan `vibe_control_v0_5_spec` was **not** deleted by CLI (`manual_only` / ask-pollution owner action).

## Manual cleanup candidates (readonly)

Use `vibe knowledge cleanup-candidates --json` to list manual cleanup candidates
(including legacy `vibe_control_v0_5_spec` as `orphan_managed`). The command is
readonly: it does not delete unmanaged/orphan sources, does not run broad notebook
cleanup, and does not call sync/retry `--apply`.

**Important:** leftover old non-current sources are **ask pollution**, not a harmless
long-term warning. Until the owner deletes confirmed non-SSOT leftovers in the
NotebookLM UI (or explicitly accepts the pollution risk), provider-backed
`vibe knowledge query` can cite stale historical content. After UI deletion, re-check
status / sync dry-run / cleanup-candidates / query until `candidate_count=0`.

## Not deleted (awaiting owner UI action)

- Remote orphan `vibe_control_v0_5_spec` (`orphan_managed` / `manual_only`) — **DELETE MANUALLY** in NotebookLM after confirming it is not current SSOT (`vibe_control_spec` / `DECISION_LOG`). CLI does not delete it because it is not receipt-owned for auto-delete.

## Code fixes required for dogfood / consistency

- Phase 8 add/replace uploads via hashed `upload_filename` temp file (identity alignment with probe)
- `NotebookLMProvider.query` + query router auto-wire when synced
- `sync --dry-run` / `retry --dry-run` use Phase 8 planner (`plan_forward_sync_dry_run`) instead of legacy flat-receipt dry-run

## Safety

- No unmanaged deletes
- No broad notebook clean
- No Beads mutation / no `bd init`
- No push
- No ChatGPT Project Sources update
- Committed docs redact raw notebook refs / source ids

## Follow-up (2026-07-14 recovery + harness)

- Owner manually deleted `vibe_control_v0_5_spec` in NotebookLM UI → `candidate_count=0`.
- Bounded `sync --apply` restored current SSOT drift to `synced`.
- Harness now encodes ask-clean rules in `docs/harness/knowledge-ask-hygiene-contract.md` + CLI/tests (`provider_ask_clean` requires synced + required_updates_count=0 + candidate_count=0).
