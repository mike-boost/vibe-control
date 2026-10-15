# Provider Readiness and Probe Policy (Phase 8.1)

**Status:** implemented as core product behavior  
**Surface:** `vibe integration status --json` (primary); also used by `vibe task apply` strict mode

## Product model

Vibe Control is an **agent-facing, provider-backed** control product:

- Coding agents operate through `vibe` CLI + harness; humans set boundaries/approvals.
- Repo / git SSOT remains truth.
- NotebookLM and Beads are **required providers** for `product_ready=true`
  when knowledge/task capabilities are enabled.
- Hetu is **optional**; when `components.hetu.enabled=true`, non-ready Hetu
  index/binding states also block `product_ready` (never auto-reindex).
- Repo fallback is degraded read only — never full product readiness.
- Provider unavailable / drift / unclean ask → blocked or degraded, never green.

## Product readiness meaning

`product_ready=true` means all of:

1. Knowledge provider available and target OK
2. Knowledge sync_state is synced (current SSOT snapshot)
3. Ask hygiene clean (`provider_ask_clean`)
4. Task provider available, readable, and ready-queue available
5. No blocking reasons in `blocked_reasons[]`

It does **not** mean:

- every tiny CLI helper probed providers
- cross-run cached provider truth
- live Beads mutation is automatically executed (see temporary live gate below)

## Probe policy

1. **Important nodes probe** — `integration status`, failed query/apply branches, doctor.
2. **Failure branch probes** — when business path cannot proceed, diagnose provider first.
3. **Do not probe every tiny internal step.**
4. Within one command, reuse a `ProviderProbeResult` / `evidence_hash` (no duplicate list/probe).
5. **Do not cache provider truth across separate command runs.**

## Envelope fields

```text
knowledge_provider.available
knowledge_provider.target_ok
knowledge_provider.sync_state
knowledge_provider.ask_hygiene.condition
knowledge_provider.provider_ask_clean
task_provider.available
task_provider.mode
task_provider.readable
task_provider.ready_queue_available
product_ready
blocked_reasons[]
next_actions[]
```

## Coordination with Phase 11B / agent task autonomy

- Strict `--provider beads` apply requires knowledge readiness (synced + ask clean).
- Apply plans bind to `plan_binding_hash` (SSOT expected-task snapshot identity).
- Stale binding → `STALE_APPLY_PLAN` / regenerate dry-run.
- Fake/local mode may use `--allow-local-without-providers`.
- **Intended product policy:** when `product_ready=true`, plan binding is current, and the
  apply plan contains only safe Vibe-managed create/update (no executable unmanaged /
  duplicate / conflict / delete), agents should not ask the user for each managed op.
- **Option A live Beads gate (still enforced):** real Beads mutation requires dual gates
  (`VIBE_BEADS_LIVE_APPLY=1` and `--confirm-beads-live-apply`) **and** `--autonomous-managed`
  **and** product_ready + safe managed plan. Default gates never set the live env.
- **Option B delta:** remove dual gate after stronger tests; unlock from readiness + safe-plan alone.
- Unsafe reconcile categories → skip / `blocked_repair_required` + structured `next_actions`
  (never ad hoc user questioning inside CLI).

## Non-goals

- Distributed transactions across NotebookLM and Beads
- Cross-run provider caches
- Treating repo fallback as product_ready
- Weakening ask hygiene or closeout tiers
