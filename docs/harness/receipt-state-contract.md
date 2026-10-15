# Receipt State Contract

## Role

Receipt is **local provider runtime state**, not repository SSOT.

Default path:

```text
~/.agents/state/vibe-control/<project-id>/knowledge-sync.json
```

## Rules

- Receipt must not be committed.
- Receipt must not be written into repo `.config`.
- Receipt may contain provider source IDs locally.
- Acceptance reports must redact source IDs and notebook refs (hash/fingerprint only).
- Missing receipt is a warning, not failure.
- Corrupted receipt returns a clear error and next action.

## Schema shape

Receipt supports `current` + `history` per `doc_id`.

Replacement:

1. verify new source instance
2. move previous `current` into `history` with `state=superseded`
3. write new `current`

Write receipt **only after** identity verification succeeds.

## Hetu IndexBindingReceipt

Hetu uses a separate local receipt (not Knowledge sync receipt):

```text
~/.agents/state/vibe-control/<project-id>/hetu/codebase_memory/index-binding.json
```

- Schema: `vibe.hetu.index_binding.v1`
- Proves Git HEAD binding + provider project/mode/version; not provider-owned `index_commit`
- Same rules: not committed; corrupt load fails closed; missing → unverifiable when Hetu enabled
- Written only after confirmed reindex apply succeeds (atomic replace)
