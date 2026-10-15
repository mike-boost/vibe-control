# Phase 5 Sync Lifecycle Report

## Summary

Landed end-to-end NotebookLM sync lifecycle for OPM-test:

1. Deleted approved Phase 4 test residue (exact titles only)
2. Sync dry-run planned `add_missing` for desired corpus
3. Sync apply added managed sources, waited ready, verified identity, wrote receipt
4. Post-sync dry-run reported `already_current`
5. Replacement + superseded cleanup covered by fake-provider tests (no real replace smoke)

## Sources deleted (approved)

Exact approved Phase 4 residue titles (resolved title → source_id, then delete by id):

- `VIBE_CONTROL_V0_5_SPEC.md`
- `[vibe:vibe-control:DECISION_LOG] DECISION_LOG.md`

After approved cleanup, remote inventory count was `0`.

## Accidental debug mutation

During symlink-path debugging of `notebooklm source add`:

1. Accidental debug add created managed title `vibe__vibe-control__vibe_control_v0_5_spec`
2. That accidental debug source was deleted immediately
3. Inventory was re-checked empty before the formal sync apply

This was not part of the desired production corpus.

## Sources added (formal sync apply)

Sync apply added 2 managed sources:

| doc_id | managed_name | title_state | verified | receipt_written |
|---|---|---|---|---|
| vibe_control_v0_5_spec | vibe__vibe-control__vibe_control_v0_5_spec | exact | true | true |
| DECISION_LOG | vibe__vibe-control__decision_log | exact | true | true |

## Wait result

Both added sources reached `ready` via provider wait before verification.

## Verification result

Identity verified by managed title (`title_state=exact`) for both docs.
Inventory classification after sync: `managed_by_receipt` for both.

## Final inventory

Final OPM-test inventory contains only the intended managed sources:

- `vibe__vibe-control__vibe_control_v0_5_spec`
- `vibe__vibe-control__decision_log`

Count: `2`. No unmanaged residue remaining from Phase 4 or the debug probe.

## Receipt result

Receipt present after sync:

- path: `~/.agents/state/vibe-control/vibe-control/knowledge-sync.json`
- `document_count=2`
- written only after identity verification

## Dry-run after sync

`python -m vibe_control knowledge sync --notebook OPM-test --dry-run --json`

Operations:

- `already_current` / `vibe_control_v0_5_spec`
- `already_current` / `DECISION_LOG`

Summary: `already_current=2`

## Replacement testing

- Fake-provider coverage: yes (add-new → wait → verify → receipt-switch → cleanup-old)
- Real OPM-test replacement smoke: **skipped** (would risk touching stable synced docs)

## Mutations avoided

- No notebook-wide `clean`
- No delete by title prefix / filename heuristic
- No unmanaged deletes
- No real replace against the synced desired corpus
- No broad update-in-place
- Skills remain thin; provider CLI details stay in NotebookLM adapter

## Git / publish

- Commit created for Phase 5 landing
- **No push was performed**

## Provider fix noted in this phase

`notebooklm source add` required `--follow-symlinks` for macOS temp paths
(`/var` → `/private/var`). Provider now resolves upload paths and passes the flag.

## Observed artifacts

Redacted JSON under `acceptance/phase5/observed/` (no raw source IDs / notebook refs /
cookies / tokens).
