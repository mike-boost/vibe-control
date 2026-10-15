# Spec — Skill Assay (`skill-assay`)

**Status:** Accepted for implementation (2026-07-22)  
**Date:** 2026-07-22  
**Document type:** Implementation-ready Engine tool-surface spec  
**Audience:** owner + coding agents  
**Language:** Explanation in Chinese where helpful; schemas / commands / field names in English.

**Supersedes:** `docs/project/sync/20260722-skill-output-diagnostic-system-spec.md` (draft Path B; renamed and redesigned)

**Related:**

- Self-grill (local receipt class precedent): `docs/project/sync/20260721-agent-self-grill-comm-contract.md`
- Feedback (local receipt class precedent): `docs/project/vibe-control-feedback-spec.md`
- Core claim grading: `docs/project/sync/20260722-core-claim-grading-hardening-spec.md`
- Test tiers: `docs/harness/test-execution-contract.md`
- Product model: `docs/project/vibe-control-spec.md`
- Index: `docs/project/PRODUCT_THINKING_INDEX.md`

**Owner stance:** Path B measurement tool. Do **not** absorb arbitrary skill determinism into vibe-control core. Do **not** add `components.skill_assay`. Do **not** mix with `vibe skills` install surface.

---

## 0. One-line verdict

```text
skill-assay = host-agnostic measurement of any local skill:
  snapshot skill → N independent fresh host sessions (default 3) →
  orchestrator-collected evidence → facts/unknowns package →
  main agent cites current official docs → CLI finalizes report.
```

Not SSOT. Not closeout / `product_ready`. Local receipts only (`runtime/vibe-skill-assay/`).

---

## 1. Naming (locked)

| Layer | Name |
|---|---|
| Product capability | **Skill Assay** |
| CLI resource group | `vibe skill-assay` |
| Python package | `vibe_control.skill_assay` |
| Receipt root | `runtime/vibe-skill-assay/` |
| Schema family | `vibe.skill_assay.*.v1` |

**Not** `vibe skills` (install only). **Not** `vibe diagnostics` (doctor+skills zip helper).

---

## 2. CLI surfaces

| Command | Role | Mutation class |
|---|---|---|
| `vibe gateway --intent skill_assay_brief --skill <dir> [--host <host>] --json` | **Agent entry** (self-explain): contract + next_actions | readonly |
| `vibe skill-assay brief [--skill <dir>] [--host <host>] --json` | Same Engine brief (Gateway delegates here) | readonly |
| `vibe skill-assay doctor --host <host> --json` | Probe SDK/CLI/auth/skill-inject/event capture | readonly |
| `vibe skill-assay diagnose --skill <dir> --host <host> (--scenario <yaml>\|--prompt-file <file>) [--runs 3] [--baseline-host <host>] --dry-run\|--execute --json` | Snapshot + N fresh runs + evidence package | local_runtime_write when `--execute` |
| `vibe skill-assay finalize --assay <id> --analysis-file <json> --json` | Validate agent analysis + emit final report | local_runtime_write |
| `vibe skill-assay report --assay <id> --json` | Re-read stored assay / report | readonly |

**Owner utterance → agent path:** when the owner says roughly “用 vibe skill-assay 分析诊断 xxx”, the agent **must** open via `skill_assay_brief` (Gateway or Engine), then follow `next_actions`. Do not invent a parallel workflow. Learn the contract anytime via `vibe describe --json` → `communication_contracts.skill_assay`.

Defaults: `--runs 3` (allowed 2..5). `--execute` required for live host runs. `--dry-run` shows plan only (no host calls).

---

## 3. Non-goals

- Not a skill mutator / auto-rewriter.
- Not a host introspector (no host internal logs).
- Not a closeout / product_ready / ask_clean gate.
- Not a second readiness engine.
- Not under `vibe skills` install group.
- Not arbitrary shell probes from untrusted skill sidecars.
- Not LLM-as-judge of quality without external checks.
- Not worktree / subagent / best-of-n product defaults.

---

## 4. Architecture

```text
skill path + scenario + host
  → secure snapshot (hash, refuse unsafe links)
  → HostAdapter.doctor / prepare / run × N (sequential fresh sessions)
  → orchestrator evidence (events, artifacts, diffs)
  → comparison (stability + typed checks)
  → evidence package (facts + unknowns)
  → main agent analysis file (hypotheses + citations)
  → finalize (validate) → report
```

`HostAdapter` protocol: `doctor`, `prepare`, `run`, `normalize`, `cleanup`.

v1 adapters:

| host_id | Injection | Notes |
|---|---|---|
| `github-copilot` | SDK `skill_directories` | session hooks / events |
| `cursor` | temp workspace `.cursor/skills/<id>/` | fresh local Agent; isolation partial → `unknowns` |
| `fake` | in-process | tests only |

Isolation: sequential runs, independent temp workspaces + fresh sessions. No shared chat context.

---

## 5. Evidence honesty

| Bucket | Meaning |
|---|---|
| `facts` | Orchestrator-measured (hashes, fields present/absent, probe results, session IDs) |
| `hypotheses` | Doc-supported explanations submitted via `finalize` |
| `unknowns` | Insufficient evidence / partial isolation / inconclusive runs |

Without `--baseline-host`, `causal_scope=single_host` — never claim host root-cause vs another host.

Agent self-narration is optional supplemental only; orchestrator capture is authoritative.

---

## 6. Security

- `--skill` must contain `SKILL.md`; refuse path escape / out-of-tree symlinks / special files.
- Typed acceptance checks only: `file_exists`, `json_schema`, `text_match`, `git_diff`, `exit_status`.
- No arbitrary shell from skill sidecars.
- Temp env scrubbed; keep only host auth vars needed.
- Redact secrets from receipts; capacity + retention + cleanup contract.

---

## 7. Schemas (summary)

- `vibe.skill_assay.scenario.v1` — prompt, timeouts, model, typed checks
- `vibe.skill_assay.trace.v1` — one run evidence record
- `vibe.skill_assay.evidence.v1` — batch facts/unknowns after diagnose
- `vibe.skill_assay.analysis.v1` — agent hypotheses + citations
- `vibe.skill_assay.report.v1` — finalized report

Receipt layout:

```text
runtime/vibe-skill-assay/<assay-id>/
  meta.json
  snapshot/
  runs/<run_index>/
  evidence.json
  analysis.json   # after finalize
  report.json     # after finalize
```

---

## 8. Two-stage report (locked)

1. **CLI diagnose** → machine evidence only (`facts` / `unknowns` / stability / checks).
2. **Main agent** queries current official docs (ctx7 / official fetch; never training memory alone).
3. **CLI finalize** validates analysis cites evidence + docs, then writes report.

---

## 9. Test tiers

- Default gates: fake + mocked host adapters only; no network; no real Cursor/Copilot execute.
- Marker `real_skill_host`: explicit serial smoke (`scripts/test-skill-assay-host-smoke.sh`); not in fast/full-local-readonly.
- Cursor adapter reuses local `agent login` (no `CURSOR_API_KEY`). Copilot adapter reuses CLI/gh login via `use_logged_in_user` and optional extra `skill-assay-hosts`.
- Never silent-fallback to `fake` when a real host fails.

---

## 10. Implementation slices

1. Package + models + storage + snapshot/scenario security
2. Comparison (stability + typed checks)
3. Fake HostAdapter + orchestrator
4. CLI: doctor / diagnose / finalize / report
5. Cursor + Copilot adapters (lazy optional deps)
6. Docs + describe/operation-evidence + gitignore + front-door route
7. Live smoke scripts

---

## 11. Amendment notes vs prior draft

| Prior draft | This spec |
|---|---|
| Mount under `vibe skills` | Separate `vibe skill-assay` |
| Agent-written `vibe skill trace` as primary | Orchestrator-collected evidence |
| Arbitrary shell probes | Typed checks only |
| Reuse nonexistent worktree/best-of-n | Sequential temp workspaces + fresh sessions |
| Single-command auto diagnosis | Two-stage: evidence CLI + agent analysis + finalize |
| Skill Diagnostics naming | Skill Assay / skill-assay |
