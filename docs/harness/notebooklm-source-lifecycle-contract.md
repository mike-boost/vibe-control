# NotebookLM Source Lifecycle Contract

## Managed naming

- `managed_name`: `vibe__{project_id_slug}__{doc_id_slug}`
- ASCII only; no spaces, colon, or brackets
- `upload_filename`: `{managed_name}__h__{sha12}.md`
- `sha12` is the first 12 hex chars of local content SHA-256

Preferred remote title: `managed_name`  
Acceptable fallback title: `upload_filename`

## Replacement lifecycle

Content changes are **not** blind delete + upload.

Provider-neutral lifecycle:

```text
add-new -> wait-ready -> verify-identity -> switch-receipt -> cleanup-old
```

Cleanup is allowed only for receipt-owned `superseded` managed source IDs, and only after receipt switch succeeds.

## Rename role

Rename is cosmetic, not the identity foundation.

If rename fails but upload filename carries managed identity and status is ready, accept `filename_fallback`.

## Phase 5 allows (gated)

- sync dry-run / apply for desired corpus
- replace via add-new then receipt switch
- cleanup of receipt-owned superseded sources

## Still forbidden

- update-in-place of existing sources
- delete unmanaged sources
- delete by filename heuristic / title prefix
- notebook-wide clean
- repair rename mutations as identity foundation
- auto-delete of `orphan_managed` leftovers (report_only; owner UI cleanup)
- declaring provider-backed ask clean while cleanup candidates remain

## Post-add states

```text
add_requested
source_registered
source_ready
identity_verified
receipt_written
```

CLI add success alone is not `identity_verified`.
