# Phase 6 Real Replace Smoke Report

## Summary

Proved the real NotebookLM replacement lifecycle on OPM-test with a dedicated
temporary smoke source (`phase6_replace_smoke`), using an isolated smoke receipt.

Final notebook restored to the original 2 production managed sources.
Normal sync dry-run remains `already_current=2`.

## Baseline inventory

Count: `2`

Titles:

- `vibe__vibe-control__decision_log`
- `vibe__vibe-control__vibe_control_v0_5_spec`

## Smoke v1 add / wait / verify

- managed_name: `vibe__vibe-control__phase6_replace_smoke`
- content: `Phase 6 replace smoke v1`
- wait: ready
- identity: verified (`title_state=exact`)
- isolated smoke receipt current written for v1
- source fingerprint (redacted): `6a6124653ffb`

## Smoke v2 add / wait / verify

- content: `Phase 6 replace smoke v2`
- content hash differs from v1
- wait: ready
- identity: verified (`title_state=exact`)
- source fingerprint (redacted): `7ef500f56746`

## Receipt switch

- isolated receipt path:
  `~/.agents/state/vibe-control/vibe-control/smoke/phase6-replace-smoke.json`
- current switched to v2 only after verify
- v1 moved to history with `state=superseded`
- production receipt (`knowledge-sync.json`) unchanged (`document_count=2`)

## Superseded cleanup

- deleted only receipt-owned smoke v1 source id
- verified v1 gone and v2 remained before final cleanup

## Final smoke cleanup

- deleted receipt-owned smoke v2 after evidence capture
- smoke receipt marked `smoke_state=cleaned`
- smoke managed title absent from final inventory

## Final inventory

Count: `2`

Titles:

- `vibe__vibe-control__decision_log`
- `vibe__vibe-control__vibe_control_v0_5_spec`

## Normal sync dry-run

- summary: `already_current=2`
- production receipt: present, `document_count=2`

## Mutation audit

Approved / performed:

1. add temporary smoke v1
2. add temporary smoke v2
3. delete receipt-owned smoke v1 (superseded)
4. delete receipt-owned smoke v2 (final temporary cleanup)

Avoided:

- no delete/update of the two production managed sources
- no broad notebook clean
- no unmanaged deletes
- no title-prefix bulk delete
- no production desired corpus changes
- no push

## Redaction

Committed observed JSON and this report use fingerprints/hashes only.
No raw notebook refs or raw source IDs.

## Remaining risks

- Real replace proven only for the temporary smoke doc, not against production docs
- Isolated smoke receipt is local machine state
- Operator still must keep smoke command INTERNAL (`--apply` / `--cleanup` gated)

## Recommended next phase

Production-doc replace readiness under explicit approval, or receipt portability /
operator UX for replace previews — without expanding mutation defaults.
