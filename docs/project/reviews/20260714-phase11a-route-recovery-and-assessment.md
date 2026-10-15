# Phase 11A Route Recovery and Assessment

**Status:** Superseded by accepted roadmap docs / Historical recovery record  
**Note:** Owner accepted Phase 11A / 11B as repo roadmap. Formal scope lives in `docs/project/sync/phase11a-ssot-specs-beads-readonly-reconcile-spec.md` and `docs/project/vibe-control-spec.md` v0.9. This file remains a recovery evidence record, not the authoritative phase contract.  
**Date:** 2026-07-14  
**Document type:** Interrupted-task recovery + route assessment (historical)  
**Does not claim:** Phase 11A / 11B implemented

---

## 1. Recovery Summary

前一个“写入正式 Project Source / commit”任务已被中止。本次优先核查 authoritative 文件是否被误改。

```text
Result: authoritative files were NOT modified.
No revert performed.
Safe to continue with draft-only outputs.
```

Untracked / residual items present (non-authoritative):

```text
?? docs/project/proposals/          (prior roadmap proposal)
?? docs/project/reviews/20260714-roadmap-and-beads-readiness-feedback.md
?? docs/project/plans/              (empty dir from aborted session; used for draft plan below)
```

Committed baseline remains Phase 10.5 closeout:

```text
13495dd Harden skills and CLI boundary for Phase 10.5
```

Authoritative Project Source still lists next as:

```text
Phase 11 — Beads Plan Import / Reconcile Minimal
```

That is the **current accepted roadmap wording**. Any 11A/11B split below is **draft recommendation only**.

---

## 2. Git State

At recovery check:

```text
git status --short:
  ?? docs/project/proposals/
  ?? docs/project/reviews/20260714-roadmap-and-beads-readiness-feedback.md
  (plans/ empty dir may appear once files are added)

git log -8 --oneline:
  13495dd Harden skills and CLI boundary for Phase 10.5
  168be56 docs: update Vibe Control project source to v0.8
  ...
```

No staged or modified tracked files for Project Source / DECISION_LOG / README.

---

## 3. Authoritative File Safety Check

| File | Diff vs HEAD | Action |
|---|---|---|
| `docs/project/vibe-control-spec.md` | none | keep |
| `docs/project/DECISION_LOG.md` | none | keep |
| `README.md` | none | keep |

```text
No revert required.
No authoritative content from aborted task left behind.
```

---

## 4. Executive Judgment

**路线判断：成立（as draft recommendation），无硬 blocker。**

```text
推荐草案路线（NOT accepted until owner approves and Project Source is updated later）：

Phase 11A — SSOT Specs and Beads Readonly Reconcile
Phase 11B — Beads Import / Apply
```

调整点相对先前 feedback（Beads-only 11A）：

```text
先前 draft C：11A = Beads identity / readiness / readonly reconcile
当前草案：11A 应先把 repo-owned SSOT specs 作为 dogfood 主线，
          并用 knowledge sync/query 验证 SSOT → desired_snapshot 路径，
          再基于 repo SSOT 定义 Beads identity + readonly reconcile。
```

**不要**把这条路线写成 Project Source accepted fact。  
**不要**直接实现。  
下一步应是 owner 确认 open decisions，再决定是否授权正式 Test Spec / Project Source 更新。

---

## 5. Repo Evidence

### 5.1 Phase 10.5 baseline (accepted)

```text
skills + CLI boundary
knowledge doctor / init-preview
task doctor / status / install-guide / init-preview
structured next_actions
skills install --apply gate
knowledge retry fail-closed gate
vibe-knowledge / vibe-implementation thin routers
```

Evidence: commit `13495dd`, closeout review, live CLI.

### 5.2 Current SSOT selection (critical dogfood fact)

`vibe knowledge inventory --json` currently returns **2** documents:

```text
vibe_control_v0_5_spec  docs/project/VIBE_CONTROL_V0_5_SPEC.md  active/spec
DECISION_LOG            docs/project/DECISION_LOG.md            curated/extra
```

`docs/project/spec-registry.yml` still marks `vibe_control_v0_5_spec` as **active**.  
`docs/project/vibe-control-spec.md` (v0.8 Project Source) is **not** in inventory.

```text
Implication:
Dogfood is possible, but the selected “active formal spec” is stale relative to
the actual Project Source. Promoting / registering vibe-control-spec.md
(or superseding v0.5) is a Phase 11A planning item, not a Phase 10.5 bug.
```

### 5.3 Knowledge workflow readiness

```text
config validate: ok / valid
knowledge status: sync_state=drift, synced=false, reasons=["remote_ack missing"]
publish/query/sync CLI: implemented in Phase 8–10 safe/default scope
```

Knowledge path can already exercise inventory → status → sync --dry-run → query routing without new product invention. Real `--apply` remains gated and should stay optional for 11A acceptance unless owner requires it.

### 5.4 Beads readiness (from prior assessment + live probe)

```text
task doctor/status: readiness=ready (shallow)
plan_import.implemented=false
no task identity model in code
no readonly Beads task inventory/reconcile CLI
beads_initialized() accepts any file under .beads (weak)
```

Beads is setup/precheck-capable, not import/reconcile-capable.

---

## 6. Route Assessment

### Candidate

```text
Phase 11A — SSOT Specs and Beads Readonly Reconcile   (readonly)
Phase 11B — Beads Import / Apply                      (explicit --apply later)
```

### Why this candidate is better than “jump to plan import”

```text
1. Product model already says repo SSOT is truth; NotebookLM is derived.
2. Beads identity must derive from repo SSOT, not NotebookLM synced state.
3. Knowledge sync/query already exists; dogfooding SSOT selection closes a real gap
   (v0.8 Project Source not selected).
4. Apply without identity/reconcile would force agents to invent Beads ops.
```

### Why not Phase 10.6 as primary

```text
task doctor/status already exist after Phase 10.5.
Remaining work is domain model (SSOT selection + identity + readonly reconcile),
not missing bootstrap commands.
```

### Why not unscoped single Phase 11

```text
Authoritative Project Source still says “Phase 11 Beads Plan Import / Reconcile Minimal”.
Implementing that as one apply-heavy phase is premature without identity + readonly reconcile.
```

---

## 7. SSOT Spec Workflow Assessment

Answers to required questions (draft):

| # | Question | Draft answer |
|---|---|---|
| 1 | Suitable to dogfood Vibe’s own specs as first SSOT? | **Yes**, with registry/Project Source alignment work |
| 2 | Are registry/config selectors enough? | **Yes for V1 selectors** (registry + include_extra); no need for broad dir selectors first |
| 3 | Need formal SSOT directory now? | **No as prerequisite**; keep `docs/project/` + registry; optional later split |
| 4 | Only one main spec — update via draft first? | **Yes** — draft/plan first; **do not** write accepted Project Source until owner approves |
| 5 | Should 11A prioritize SSOT structure + knowledge sync exercise? | **Yes (draft recommendation)** |

Proposed dogfood sequence (draft):

```text
1. Decide which file is the active formal Project Spec (likely vibe-control-spec.md)
2. Update registry draft proposal (active/superseded) — later, with owner approval
3. Keep DECISION_LOG as include_extra or revisit
4. desired_snapshot from selected SSOT files
5. knowledge status / sync --dry-run (and optional bounded --apply only if approved)
6. query status-aware routing check
7. Only then bind Beads identity to those SSOT source ids/paths/hashes
```

---

## 8. Beads Identity / Readonly Reconcile Assessment

| # | Question | Draft answer |
|---|---|---|
| 6 | Beads identity from repo SSOT, not NotebookLM? | **Yes** |
| 7 | Identity fields | see draft plan §8; Beads task id = binding result only |
| 8 | Readonly reconcile minimum output | missing / duplicate / stale / conflict / unmanaged; no mutation |
| 9 | 11B create allowed? | **Likely yes**, only with explicit `--apply` (owner must confirm) |
| 10 | 11B update managed tasks? | **Likely yes**, Vibe-managed only (owner must confirm) |
| 11 | Delete default forbidden? | **Yes (draft default)** |
| 12 | Unmanaged strategy | **Detect + skip/warn; never mutate** (fail-closed only if owner chooses) |
| 13 | Blocker? | **No hard blocker for drafting**; soft prerequisites listed below |

Draft identity orientation:

```text
source_type = "spec" | "extra_doc" | (later "plan")
source_id   = registry id / stable doc id
repo_path   = canonical path
content_hash = SSOT content hash
vibe_managed_marker = deterministic marker string in Beads fields
beads_task_id = binding result only (not truth)
```

---

## 9. Blockers and Non-Blockers

### Hard blockers to drafting? 

```text
None.
```

### Soft prerequisites / risks (not blockers to draft)

```text
1. Active registry still points at VIBE_CONTROL_V0_5_SPEC.md, not vibe-control-spec.md
2. knowledge status is drift (remote_ack missing) — expected until intentional sync
3. TASK_READY is shallow — must be tightened before claiming Beads “ready for import”
4. Phase 6 acceptance already_current==2 can fail under SSOT drift — parallel debt
5. No Beads task inventory API in vibe CLI yet — required for reconcile implementation later
```

### Non-blockers

```text
- Phase 10.5 closeout is complete for its contract
- task install-guide / init-preview exist and stay readonly
- skills already forbid auto bd init / inventing Phase 11 apply
```

---

## 10. Recommended Route

**Draft recommendation (awaiting owner acceptance):**

```text
Phase 11A — SSOT Specs and Beads Readonly Reconcile
Phase 11B — Beads Import / Apply
```

Immediate next **process** step (still no authoritative write unless owner asks later):

```text
1. Owner reviews this assessment + draft plan
2. Owner decides open questions (§11)
3. Only then authorize:
   - formal Phase 11A Test Spec, and/or
   - Project Source roadmap update
4. Do not implement apply; do not create Beads tasks
```

Do **not** treat prior feedback’s “write Phase 11A Test Spec now” as automatic license to update Project Source.

---

## 11. Decisions Required From Project Owner

```text
1. Accept draft 11A/11B split naming?
2. Promote docs/project/vibe-control-spec.md as active registry formal spec?
3. Keep VIBE_CONTROL_V0_5_SPEC.md as superseded / archive / remove from inventory?
4. Keep DECISION_LOG in include_extra for knowledge sync?
5. Task identity primary key combination?
6. 11A import input scope: formal specs only, or specs + plans?
7. Vibe-managed marker format?
8. Confirm Beads task id is binding-only?
9. Duplicate / stale / conflict definitions?
10. Unmanaged: skip+warn vs fail-closed?
11. 11B: allow create? allow update managed? forbid delete?
12. Must readonly reconcile require live bd list probe?
13. Is NotebookLM sync --apply a required 11A acceptance gate, or dry-run+status enough?
14. Fix Phase 6 acceptance drift debt now or later?
15. When (if ever) authorize Project Source update for this route?
```

---

## 12. Evidence Appendix

### Commands run (readonly)

```bash
git status --short
git log -8 --oneline
git diff -- docs/project/vibe-control-spec.md
git diff -- docs/project/DECISION_LOG.md
git diff -- README.md
.venv/bin/python -m vibe_control.cli config validate --json
.venv/bin/python -m vibe_control.cli knowledge inventory --json
.venv/bin/python -m vibe_control.cli knowledge status --json
.venv/bin/python -m vibe_control.cli task doctor --json
rg -n "Phase 11" docs/project README.md src tests | head
```

### Key facts

```text
inventory active formal spec = VIBE_CONTROL_V0_5_SPEC.md (not vibe-control-spec.md)
knowledge sync_state = drift
task plan_import.implemented = false
authoritative Project Source still says Phase 11 (unsplit) pending
```

### Explicit non-actions

```text
No Project Source update
No DECISION_LOG / README update
No code implementation
No Beads task create / bd init
No NotebookLM mutation
No commit
No push
```

---

**End of draft assessment**
