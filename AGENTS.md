# Agent Guide

Vibe Control is an **agent-facing, provider-backed** control product.

- Coding agents are the primary operators via `vibe` CLI + harness rules.
- Humans set high-level boundaries and approvals; they should not need provider implementation details.
- Knowledge half of `product_ready` requires **one** active knowledge provider that is
  synced + ask-clean: `knowledge.provider` ∈ `{local_fts, notebooklm}` (owner-explicit;
  no auto-switch). Beads remains required for the task half.
- Repo fallback (`fallback_provider=repo`) is degraded read only — never claim full product
  readiness when the active provider is unavailable, drifted, or ask-unclean.
- Repo SSOT remains truth; active knowledge provider content is derived; Beads is the task
  provider; provider ids are binding results only (`managed_key` is stable identity).

Before changing knowledge-provider or task-provider behavior, read:

- `docs/harness/knowledge-provider-boundary.md`
- `docs/harness/knowledge-ask-hygiene-contract.md`
- `docs/harness/knowledge-ask-ssot-contract.md`
- `docs/harness/provider-readiness-probe-policy.md`
- `docs/harness/notebooklm-source-lifecycle-contract.md`
- `docs/harness/receipt-state-contract.md`
- `docs/harness/real-integration-mutation-contract.md`
- `docs/harness/phase-execution-contract.md`
- `docs/harness/test-execution-contract.md`
- `docs/harness/ssot-closeout-transaction-contract.md`
- `docs/harness/owner-plain-language-contract.md`
- `docs/project/sync/phase11b-beads-import-apply-spec.md`
- `docs/project/vibe-control-spec.md` (Approval Matrix + product model)
- `docs/project/PRODUCT_THINKING_INDEX.md` (Knowledge/Task polish stance + scenario research index)
- `docs/project/sync/20260717-knowledge-task-polish-strategy.md` (accepted: no new flagship Knowledge/Task features for now)
- `docs/project/sync/20260720-knowledge-multi-notebook-corpus-design.md` (accepted narrow exception: target-scoped corpus / multi-notebook)
- `docs/project/sync/20260721-agent-self-grill-comm-contract.md` (accepted: self-grill via `describe` + Gateway `grill_brief`; not a skill to switch)
- `docs/project/sync/20260721-knowledge-local-fts-provider-spec.md` (accepted: local_fts SQLite FTS5 retrieval provider + provider selection)
- `docs/project/sync/20260722-core-claim-grading-hardening-spec.md` (accepted: operation evidence / mutation_intent+performed)
- `docs/project/sync/20260722-hetu-runtime-mvp-spec.md` (accepted: optional Hetu via codebase-memory-mcp)
- `docs/project/sync/20260722-skill-assay-spec.md` (accepted: host-agnostic skill measurement tool; not a capability)

Active SSOT / include_extra **commit alone is not closeout-complete**. Prefer
`vibe closeout run --dry-run/--apply --json` as the orchestration entry (see
`docs/harness/ssot-closeout-transaction-contract.md`). Do not hand-assemble
knowledge sync → integration status → task cache steps. Do not claim done or
greenlight `implementation prompt` while `provider_sync_required` or
`task_cache_current=false`. ChatGPT Project Sources are owner-manual external
advisor copies only — not a product closeout gate.

## Approval Matrix (summary)

**Agent-autonomous when CLI gates allow (do not ask the user for each op):**

- Readonly knowledge/status/query/reconcile/doctor/integration status
- Fake/local `vibe task apply --apply --provider fake` for tests
- Planned Vibe-managed create/update **policy** when `product_ready=true`, SSOT plan binding
  is current, and the plan contains only safe managed ops
- Bounded knowledge closeout apply when dry-run is limited to current active SSOT /
  default inventory (committed SSOT; empty `git status --short`): NotebookLM sync when
  `provider=notebooklm`, or local FTS index rebuild when `provider=local_fts`

**Temporary live Beads safety gate (still in force — Option A):**

- Real Beads mutation requires `--apply --provider beads`, `--autonomous-managed`,
  `--confirm-beads-live-apply`, and `VIBE_BEADS_LIVE_APPLY=1`.
- Also requires `product_ready=true` and a safe managed-only executable plan.
- Default gates / CI never set the live env and never mutate Beads.
- Option B (future): unlock live create/update from product_ready + safe-plan alone
  (remove dual gate after stronger tests).

**Explicit owner approval required:**

- NotebookLM mutation outside bounded current-SSOT/default-inventory closeout sync
- NotebookLM unmanaged/orphan delete, broad cleanup, arbitrary `retry --apply`
- provider config / secrets / auth / target changes
- git push
- destructive delete
- unmanaged task adoption
- non-deterministic conflict repair
- any live Beads mutation classified outside safe managed autonomy / local-ephemeral
  cache-reset gates

**Unsafe cases — CLI skip/block/repair-plan + `next_actions`, never ad hoc user Q&A in code:**

- unmanaged → `skip_unmanaged`
- duplicate → `skip_duplicate`
- conflict → `skip_conflict` / `blocked_repair_required`
- delete → `skip_delete_forbidden`

## Rules

- Follow `docs/harness/phase-execution-contract.md` for phase landings.
- Follow `docs/harness/real-integration-mutation-contract.md` for real provider mutation classes.
- Follow `docs/harness/test-execution-contract.md` for evidence tiers / gates.
- Follow `docs/harness/provider-readiness-probe-policy.md` for probe reuse and product_ready.
- On provider failure: diagnose/probe before business-level guessing.
- Run tests before and after changes (`pytest -q` and relevant acceptance scripts).
- Prefer `scripts/test-closeout-local-fast.sh` (or `scripts/test-fast.sh`) for iteration.
- Prefer `scripts/test-full-local-readonly.sh` before landing work (local only; no real NotebookLM).
- Use `scripts/test-nlm-readonly-smoke.sh` only when explicitly validating real provider smoke.
- `scripts/test-full-readonly.sh` is a compatibility wrapper for full **local** readonly only.
- Default gates must not overwrite tracked `acceptance/**/observed/*.json` (runtime → `observed-runtime/`).
- Closeout reports should end with empty `git status --short` (clean local modification state).
- Do not mutate NotebookLM unless the task explicitly requests real integration.
- Do not run NotebookLM `source add` / `delete` / `update` / `rename` / `clean` in ordinary
  implementation work.
- Do not invent ad hoc user questions for unmanaged/duplicate/conflict; use CLI envelopes.
- Keep provider-specific behavior inside provider adapters.
- Keep skills thin; deterministic behavior belongs in CLI code and tests.
- **对 owner 说人话：** 禁止未解释的黑话/绰号（如 managed、ask-clean、product_ready、
  closeout、drift、envelope）。先直接答，必要时一句话解释术语。见
  `docs/harness/owner-plain-language-contract.md` 与
  `vibe describe --json` → `communication_contracts.owner_plain_language`。
- Knowledge 是一个能力、两个 provider（`local_fts` / `notebooklm`）。格式限制应跟
  **当前 provider** 的能力走，不要假装两边一样。见
  `docs/harness/knowledge-provider-boundary.md` 与
  `src/vibe_control/knowledge/format_policy.py`。
- **Git is agent work, not owner Q&A:** never ask the owner whether to land changes, never offer
  “shall I commit?”, never stall a finished task waiting for commit permission. When the task is
  to implement/land/release, perform the git land (and for release: annotated tag + push +
  `gh release` per `docs/release.md`) as part of the job. Still: no force-push; no push for
  pure local exploration with no land/release intent; never update git config.
- Never push unless the task includes land/release (or the owner explicitly required push).
- Coding agents must not claim to update ChatGPT Project Sources; owner uploads
  manually for advisor context only (not a product closeout gate).
