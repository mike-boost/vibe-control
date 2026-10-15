# Knowledge Ask Hygiene Contract

Durable rules for declaring provider-backed ask clean. These are enforced by CLI helpers
and tests (`ask_hygiene.py`, `cleanup-candidates`, query warnings) — not by prompt wording alone.

## Clean state (required)

Provider-backed ask may be declared clean only when **all** are true:

1. `sync_state=synced`
2. `required_updates_count=0` for current SSOT
3. `cleanup-candidates` `candidate_count=0`

`synced` alone is **not** enough if old non-current provider sources remain.

Ask **quality** (structured Facts/Constraints/MUST/Uncertainty) is owned by
`docs/harness/knowledge-ask-ssot-contract.md` and Ask Prompt Policy
`vibe.knowledge.ask.v3` — hygiene clean is a prerequisite, not the answer contract.

## Condition classes (must stay distinct)

| condition | meaning |
|---|---|
| `clean` | synced + zero required updates + zero cleanup candidates |
| `orphan_pollution` | leftover old managed/non-current sources (e.g. `vibe_control_v0_5_spec`) |
| `current_ssot_drift` | current SSOT docs need bounded `sync --apply` |
| `provider_unavailable` | provider probe/list failed |
| `target_mismatch` | wrong ProviderTarget; fail closed |

## Orphan / old-source policy

- Old non-current sources are **ask pollution**, not a long-term harmless warning.
- Owner deletes them manually in the provider UI after confirming they are not current SSOT.
- CLI `cleanup-candidates` is readonly and must never call provider delete.
- CLI must not delete by title / filename / managed_name heuristic alone.
- Broad notebook cleanup remains forbidden.

## Current-SSOT drift recovery

After owner manual orphan cleanup, remaining drift for current SSOT / default inventory docs
(registry active + `include_extra`, currently the four Project Source specs) is fixed by one
bounded:

```text
vibe knowledge sync --dry-run --json
vibe knowledge sync --apply --json
```

Preflight (`preflight_current_ssot_drift_recovery`) must confirm:

- `candidate_count=0`
- `sync_state=drift`
- required updates are exactly current SSOT docs
- dry-run has no orphan cleanup / unmanaged delete
- target alias matches configured notebook

`sync --apply` **and** `retry --apply` must refuse (`APPLY_SCOPE_VIOLATION`) when dry-run ops
are not bounded to current desired SSOT / default inventory docs, or when orphan actions are
not `report_only_no_delete`, or when forbidden ops appear (unmanaged delete, broad cleanup /
notebook clean, auth/config/target change).

`status` / `query` / `doctor` / `inventory` / `sync --dry-run` never call provider apply.

## Redaction

Normal JSON/report output must not include raw notebook refs or raw source IDs.
Use `target_key_hash` / `source_id_hash` / display hints instead.

## Commands

```text
vibe knowledge status --json
vibe knowledge sync --dry-run --json
vibe knowledge cleanup-candidates --json   # includes data.ask_hygiene
vibe knowledge query --question-file ... --json  # may set provider_ask_clean
```
