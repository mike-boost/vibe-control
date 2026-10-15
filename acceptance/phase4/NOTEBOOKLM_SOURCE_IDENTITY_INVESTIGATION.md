# NotebookLM Source Identity Investigation

## Goal

Explain why Phase 4 OPM-test seed preserved the managed title for Decision Log but not for Spec, determine whether notebooklm-py exposes a dedicated source ready/status check, and recommend Phase 5 identity + verification design **before** any sync mutation work.

## Current Observed Problem

NotebookLM UI / CLI inventory for OPM-test:

| Source | Observed title | Classification by Vibe |
|---|---|---|
| Spec | `VIBE_CONTROL_V0_5_SPEC.md` | unmanaged |
| Decision Log | `[vibe:vibe-control:DECISION_LOG] DECISION_LOG.md` | managed |

Also observed: after CLI add returned success, sources were not immediately visible in UI; they appeared after delay. Current inventory shows both `status=ready` / `status_id=2`.

## Commands Inspected

Read-only only:

- `notebooklm --help`, `--version` (0.8.0a3)
- `notebooklm source --help`
- `notebooklm source list|add|get|wait|stale|rename|delete|clean --help`
- `notebooklm source update --help` → **no such command**
- `notebooklm status|doctor|metadata|auth check --help`
- `notebooklm source list --json` / `source get --json` / `metadata --json` against OPM-test (IDs redacted)
- Phase 4 code: `notebooklm_provider.add_file_source`, `remote_ops.cmd_seed_test_sources`, `managed_titles`, `sync_preview`, `corpus`
- Installed package: `notebooklm-py` under uv tools (`_sources.py`, `_source/upload.py`, `_app/source_add.py`, `rpc/types.SourceStatus`)
- Observed JSON: `acceptance/phase4/observed/seed-allow-add.json`, inventory/preview artifacts

## Current Phase 4 Add Implementation

| Source | Add mode | Title passed? | Expected title | Observed title | Finding |
|---|---|---:|---|---|---|
| Spec | **file upload** (`notebooklm source add <path> --type file --title ... --json`) | Yes | `[vibe:vibe-control:vibe_control_v0_5_spec] Vibe Control v0.5 Spec` | `VIBE_CONTROL_V0_5_SPEC.md` | Same code path as Decision Log; remote kept filename |
| Decision Log | **same file upload form** | Yes | `[vibe:vibe-control:DECISION_LOG] DECISION_LOG.md` | managed title preserved | Same mode; remote kept custom title |

### Confirmed Phase 4 mechanics

1. Exact Vibe command form (both sources):  
   `notebooklm source add <repo-file-path> --notebook <ref> --type file --title <managed-title> --json`
2. Both used the **same** `NotebookLMProvider.add_file_source` path — **not** text mode.
3. No temporary upload filenames; original repo basenames were uploaded.
4. No Vibe-side title normalization beyond template formatting.
5. Seed result records only `ok/code/message`; **discards** provider `result` (so no persisted `source_id` / returned title).
6. **No** post-add wait (`source wait` / poll).
7. **No** local sync receipt.

## Dedicated Source Status / Ready Check

| Check | Finding | Evidence |
|---|---|---|
| Dedicated source status enum | **Yes** | `SourceStatus`: PROCESSING=1, READY=2, ERROR=3, PREPARING=5 (`rpc/types.py`) |
| `source.is_ready` / processing helpers | **Yes** | `_types/sources.py` |
| CLI `source wait` | **Yes** | Polls until ready/fail; exit 0=ready, 1=missing/failed, 2=timeout; `--timeout`, `--interval`, `--json` |
| Library wait APIs | **Yes** | `wait_until_ready`, `wait_until_registered`, `wait_for_sources` |
| Status on list/get | **Yes** | OPM-test list/get show `status`, `status_id` |
| `source stale` | Freshness for URL/Drive refresh only — not general indexing ready | CLI help |
| Notebook `status` | Session context only — not source processing | CLI help |
| `source update` | **Does not exist** | CLI error |
| `source rename` | **Exists** (title-only mutation) | CLI help; not run in this investigation |

### Source Status / Ready Check Findings

**Dedicated source status exists?** Yes.

**Evidence**

- Command: `notebooklm source wait SOURCE_ID [--timeout] [--interval] [--json]`
- List/get JSON fields observed: `id`, `title`, `type`, `url`, `status`, `status_id`, `created_at`
- Package: `SourceStatus` + `wait_until_ready` / `wait_until_registered`

**If not available** — N/A; dedicated wait exists and should be used in Phase 5.

## Title Preservation Findings

### Confirmed facts

- Phase 4 did **not** use different add modes for Spec vs Decision Log.
- Both were `--type file` with `--title`.
- notebooklm-py documents that **file-add RPC has no title slot**; custom title is applied via a **follow-up `UPDATE_SOURCE` rename** after upload.
- If rename fails (`RPCError`/`NetworkError`), library **logs a warning and keeps the filename title**, and still returns the uploaded source (CLI can still exit success).
- Text sources embed title in `add_text` RPC directly (different path; more title-native).
- Spec created ~8s earlier than Decision Log (`created_at` 07:20:12 vs 07:20:20 UTC); both now `ready`.
- Brackets `[]` and colon `:` alone cannot fully explain failure: Decision Log title contains them and survived.
- Vibe did not verify returned title against requested title after add.

### Likely inference

- Spec remote title equals basename ⇒ post-upload rename for Spec **did not stick** (failed or no-op), while Decision Log rename succeeded.
- `--title` for file uploads is **best-effort / unreliable** unless Vibe verifies post-rename title (and preferably waits for registration/ready).
- UI delay matches documented async processing (`PROCESSING` → `READY`) and Phase 4 not calling `source wait`.

### Unknowns

- Exact rename failure reason for Spec (transient registration race vs title character rejection vs silent no-op).
- Whether spaces / `.` in `Vibe Control v0.5 Spec` contributed.
- Whether text-mode add would preserve title more reliably for markdown corpus (Hypothesis B not yet tested).
- Whether renaming Spec now via `source rename` would succeed (not tested; mutating).

## Special Character Assessment

| Character / pattern | In Spec title | In Decision title | Alone sufficient to explain mismatch? |
|---|---|---|---|
| `[` `]` `:` | yes | yes | **No** (Decision survived) |
| spaces | yes (after `]` and in display title) | yes (after `]`) | Unclear; display-part spaces differ |
| `.` in `v0.5` | yes | no | Unknown |
| filename fallback | Spec basename used | N/A (rename kept) | Matches library failure mode |

**Recommendation:** avoid spaces, colon, and brackets in managed titles going forward — not because they are proven fatal, but because file-title reliability is weak and identity should survive **filename fallback**.

## Recommended Managed Title Format

Prefer **Option C** (identity-only, no human prose):

```text
vibe__vibe-control__vibe_control_v0_5_spec
```

Evaluation:

| Option | Readable | Stable parse | No space/colon/brackets | Collision-resistant | Works as filename fallback | Notes |
|---|---|---|---|---|---|---|
| A `vibe__...__Human_Title` | medium | yes | mostly | medium | yes if used as filename | Extra human segment redundant if filename carries id |
| B hyphen-only | weaker parse | weaker | yes | medium | yes | Ambiguous segment splits |
| **C `vibe__project__doc_id`** | enough | **best** | **yes** | high | **yes** | Recommended |
| D `VIBE__...` | similar | yes | yes | high | yes | Case shouting; prefer lowercase `vibe__` |

Parse rule: split on `__`, require `parts[0]=="vibe"`, `parts[1]==project_id`, `parts[2]==doc_id`.

## Recommended Upload Filename Format

Because file upload defaults to basename and rename may fail:

```text
vibe__{project_id}__{doc_id}.md
```

Example:

```text
vibe__vibe-control__vibe_control_v0_5_spec.md
```

Phase 5 should upload via a **temp copy/symlink with managed basename**, still passing the same managed string as `--title`, then verify remote title **or** basename matches the convention.

## Recommended Phase 5 Identity Model

```text
Recommended Phase 5 identity model:
- Authoritative local identity: doc_id + canonical repo path (+ content hash when available)
- Remote managed proof: local sync receipt mapping doc_id -> provider source_id (fingerprint in reports)
- Receipt role: primary association after any successful verified add/rename
- What counts as managed:
    1) receipt source_id match, or
    2) exact managed title/filename convention match for same project_id+doc_id (bootstrap only)
- What counts as possible managed: filename/title heuristic weak match without receipt → manual review, never auto-delete/update
- What must never be deleted automatically: unmanaged sources; possible-managed without receipt; anything not allow-listed notebook
```

Aligns with user preference: **receipt-first**; convention as bootstrap/rebuild aid; filename-only without receipt = possible managed.

## Recommended Post-add Verification Loop

```yaml
post_add_verification:
  poll_interval_seconds: 2
  timeout_seconds: 120
  required_checks:
    - capture source_id from add JSON result (fail closed if missing)
    - notebooklm source wait <source_id> until ready (or library wait_until_ready)
    - remote get/list shows source
    - associate to doc_id via:
        a) receipt write after verified title/filename convention match, or
        b) exact managed title OR managed upload basename
  optional_checks:
    - source status == ready (already implied by wait)
    - fulltext/ask smoke only in later phases if needed
  failure_state:
    - add_requested_but_not_verified  # CLI ok but title/id/ready not confirmed
    - needs_manual_review             # possible managed / ambiguous
  safeguards_before_any_real_sync:
    - notebook allow list only
    - dry-run preview first
    - explicit approval for add/update/delete
    - never delete unmanaged
    - never mutate on filename heuristic alone
    - max batch size + add-only default until verified
    - redact refs/ids in committed reports
```

## Risks

- Treating CLI add exit 0 as “title applied” is false (observed).
- Title-only identity without receipt breaks when NotebookLM keeps filename.
- `source rename` / `delete` / `clean` are powerful; Phase 5 must gate them.
- Unofficial notebooklm-py may change RPC/title behavior.
- Re-adding Spec without repair creates duplicates under different titles.

## Open Questions

1. Did Spec rename fail due to race (first upload) or title content?
2. Would text-mode add preserve title better for markdown bodies?
3. Should Phase 5 repair existing Spec via approved `source rename` to managed format, or leave as possible-managed?
4. Where should receipts live (`.config/` ignored vs `.vibe/` ignored)?

## Next Recommended Implementation Step

Do **not** implement broad sync yet.

1. User decides title/filename Option C (or variant) + receipt location.
2. Optional **approved** micro-experiment (max 2 `vibe__title_test__*` sources) to compare file+safe-title vs text+safe-title — only if needed to close open question #1/#2.
3. Then Phase 5 design: receipt store + add-with-managed-basename + `source wait` verification + verify-title-or-mark-unverified.

### Optional experiment (NOT run; awaiting approval if desired)

```text
## Approval Request: NotebookLM Title Preservation Experiment

I propose to add at most 2 tiny test sources into OPM-test to compare title behavior.

Experiment sources:
1. file upload with managed basename + safe title: vibe__title_test__file_safe
2. text source with safe title: vibe__title_test__text_safe (if supported)

Safety:
- add-only
- max 2 sources
- names start with vibe__title_test__
- no update/delete/clean
- can be manually removed later from NotebookLM UI

Please reply:
- approve
- skip
- change: <instruction>
```

Evidence is already strong enough on **file-title-via-rename** mechanics; experiment is optional to isolate Spec-specific failure mode.
