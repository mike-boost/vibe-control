# Phase 4F Source Lifecycle Report

## Phase Goal

Harden provider-neutral source identity, receipt, wait/verification, and sync-preview classification before any Phase 5 sync/update/delete work.

Encode safety rules in harness docs + executable tests so chat prompts need not repeat them.

## Why File Upload Title Is Unreliable

notebooklm-py file add has no native title slot. `--title` is applied via post-upload `UPDATE_SOURCE` rename. Rename may fail or delay; CLI can still return success while remote title remains the upload basename.

## Naming Decision

- `managed_name`: `vibe__{project_id_slug}__{doc_id_slug}`
- `upload_filename`: `{managed_name}__h__{sha12}.md`
- Preferred title: `managed_name`
- Acceptable identity: upload filename (`filename_fallback`)
- Rename is cosmetic, not identity foundation

## Receipt

- Path: `~/.agents/state/vibe-control/<project-id>/knowledge-sync.json`
- Local runtime state only; not repo SSOT; not committed
- current + history; write only after verification
- Reports redact provider source IDs

## Source Lifecycle

```text
add-new -> wait-ready -> verify-identity -> switch-receipt -> later-cleanup
```

Phase 4F forbids update/delete/clean/broad sync/repair rename.

## Current OPM-test Classification (read-only)

At acceptance time:

- Decision Log legacy managed title remains recognized as `legacy_managed`
- Spec plain filename `VIBE_CONTROL_V0_5_SPEC.md` is `possible_managed_by_legacy_filename` / `possible_managed_needs_review`
- No delete/update planned for legacy Spec
- Duplicate add for Spec is blocked by possible-legacy rule

## Harness Docs

- `AGENTS.md`
- `docs/harness/knowledge-provider-boundary.md`
- `docs/harness/notebooklm-source-lifecycle-contract.md`
- `docs/harness/receipt-state-contract.md`

## Mutations Performed

None (acceptance runner never runs `--allow-add`).

## Mutations Avoided

- source add/delete/update/rename/clean
- broad sync
- Spec publish
- Beads tasks

## What Remains for Phase 5

- controlled replace lifecycle execution (still no blind delete)
- optional cleanup of superseded instances
- optional approved repair of legacy Spec title/filename
- full sync planner beyond add-only seed
