# Roadmap and Beads Readiness Feedback

**Document type:** Technical feedback on roadmap / Beads readiness proposal  
**Status:** Historical feedback — route C accepted into repo roadmap as Phase 11A / 11B; see formal phase spec  
**Date:** 2026-07-14  
**Input proposal:** `docs/project/proposals/20260714-roadmap-and-beads-readiness-proposal.md`  
**Method:** readonly repo inspection + CLI probes; no Beads mutation; no Phase 11 implementation  
**CLI invocation:** `.venv/bin/python -m vibe_control.cli`

---

## 1. Executive Judgment

**选择路线：C — 拆成 Phase 11A / Phase 11B。**

```text
Phase 11A — Beads Identity / Readiness Truthfulness / Readonly Reconcile
Phase 11B — Beads Plan Import / Apply (controlled mutation)
```

核心理由（证据驱动）：

```text
1. Phase 10.5 已把 Beads 拉进 Vibe Control 的 setup/precheck 表面
   （task doctor/status/install-guide/init-preview + skill 路由 + 禁 mutation）。
2. 但 Beads 还不是可安全做 plan import/reconcile 的一等 task provider：
   - 没有 task identity model
   - 没有只读枚举/比对现有 Beads tasks 的能力
   - TASK_READY 判定过浅（bd + .beads 有任意文件即可）
   - task doctor ≈ task status，几乎没有更深 precheck
3. 因此不能选 A（直接整包 Phase 11 import/apply）。
4. 也不优先选 B（再插 Phase 10.6）：doctor/status CLI 已存在；
   真正阻塞 Phase 11 的是 identity + readonly reconcile，不是“缺 doctor 命令”。
   用 11A 吸收剩余 readiness 硬化，避免为已存在表面再发明一个子阶段。
5. 不选 D 作为主路线：Phase 6 acceptance 债是 knowledge SSOT/provider drift，
   不阻塞 Beads 规格设计；可并行小修，不应挡住 11A Test Spec。
```

**一句话：** Phase 10.5 完成了 “Beads 进门”；还没完成 “Beads 可对账”。下一步写 **Phase 11A Test Spec**，不要直接写带 apply 的整包 Phase 11。

---

## 2. Repo Evidence

### 2.1 What Phase 10.5 already proved

| Surface | Evidence | Status |
|---|---|---|
| `vibe task doctor --json` | CLI help + live probe `ok=true mode=readonly readiness=ready` | exists |
| `vibe task status --json` | same readiness payload; no `NOT_IMPLEMENTED` | exists |
| `vibe task install-guide --json` | live probe; note forbids auto install | exists |
| `vibe task init-preview --json` | recommends `bd init --skip-agents`; does not run init | exists |
| structured `next_actions` | `{code,command,mutation,reason}` on task doctor/status | exists |
| `vibe-implementation` routing | doctor/status/install-guide/init-preview; forbid auto `bd init` | exists |
| Project Source | Phase 10.5 complete; Phase 11 pending | accurate |
| Closeout | `docs/project/reviews/20260714-phase10-5-closeout-validation.md` | passed for 10.5 contract |

### 2.2 What is still missing for plan import

| Capability | Evidence | Status |
|---|---|---|
| Task identity model | no `task_id` / managed marker / identity module under `src/vibe_control/task/` | **missing** |
| Readonly list/reconcile of Beads tasks | no `bd list` / import / reconcile CLI; doctor `plan_import.implemented=false` | **missing** |
| Truthful “task status readable” | `status_readable` hard-coded `True` in `build_task_doctor` without probing `bd` task read | **weak / overclaim** |
| Deep `.beads` validation | `beads_initialized()` = dir exists AND (marker file OR **any file**) | **shallow** |
| Config semantics beyond `tasks.provider` | `REQUIRED_TASKS_FIELDS = ("provider",)` only; no beads-specific contract | **minimal** |
| doctor ≠ status | `build_task_doctor` mostly copies `build_task_status` | **weak differentiation** |
| Apply/create/update/delete policy | not specified in code; skill only defers to Phase 11 | **undefined** |

### 2.3 Live CLI probe (this machine, abridged)

```text
task doctor:
  readiness=ready
  task_provider_configured=true
  binary_path present, version present
  beads_dir_present=true initialized=true
  plan_import.implemented=false phase=11
  mutations.bd_init=false task_create=false

task status:
  same readiness model; ok=true; no NOT_IMPLEMENTED

task init-preview:
  recommended_init=bd init --skip-agents (preview only)

task install-guide:
  installed=true; forbids automatic install
```

### 2.4 Dangerous shallow ready (local experiment)

```text
empty .beads/           → initialized=false  (good)
.beads/ with any file   → initialized=true   (too weak for “ready for import”)
```

Code: `src/vibe_control/task/doctor.py` `beads_initialized()`.

### 2.5 Config reality

```text
.config/vibe-control.yaml:
  tasks.provider: beads
  plan_to_tasks: true
  checkpoint_required: true
  do_not_replace: []

validate_config only requires tasks.provider key presence.
It does not validate provider enum, plan_to_tasks meaning, or Beads-specific fields.
```

### 2.6 Tests vs accidental mutation

| Guard | Evidence | Strength |
|---|---|---|
| Skill forbids auto `bd init` / Phase 11 invent | `vibe-implementation/SKILL.md` + content tests | medium (text contract) |
| Doctor flags `mutations.bd_init/task_create=false` | `test_P10_5_NO_BEADS_TASK_CREATE_001` | medium |
| init-preview does not execute init | bootstrap tests mock `bd init --help` only | good for preview path |
| CLI never calls `bd create` | no positive test asserting argv denylist in doctor/status | **weak** |
| Identity / reconcile | none | missing |

### 2.7 Acceptance debt (proposal Option D)

```text
scripts/test-acceptance-readonly.sh can fail at Phase 6 when SSOT drifts
(e.g. DECISION_LOG) vs provider (expects already_current==2).

This is knowledge-side environment debt, documented in Phase 10.5 closeout.
It does not prove Beads unreadiness, and should not be the primary next phase.
```

---

## 3. Proposal Evaluation

### 3.1 Judgments that are correct

```text
✓ Phase 10.5 progress ≠ automatic green light for Beads plan import.
✓ Beads must enter Vibe via config/CLI/doctor/status/guides/envelopes/skills/tests/gates
  — not as an unmanaged agent-side tool.
✓ Plan import needs foundations: config, doctor/status, .beads detection,
  structured next_actions, skill routing, no default mutation.
✓ Option A is only acceptable if readiness is already strong — it is not.
✓ Option B and C are the serious candidates.
✓ Phase 6 acceptance drift is probably not the Beads blocker (confirmed).
✓ Task identity questions (spec id / plan id / path / hash / marker / beads id)
  are real owner decisions before apply.
✓ Use `.beads`, never `.beeds` (repo compliant).
```

### 3.2 Judgments that are premature, wrong, or incomplete

```text
✗ “Insert Phase 10.6” as the default likely route is premature packaging.
  Evidence shows doctor/status/install-guide/init-preview already exist and
  passed Phase 10.5 closeout. Another 10.x phase that mostly re-lists those
  commands invents a sub-phase without a missing-command blocker
  (see docs/harness/phase-execution-contract.md).

✗ Treating “Beads setup not ready” as the same problem as “missing identity /
  readonly reconcile” conflates two layers:
  - Layer 1 (mostly done): bootstrap/precheck CLI
  - Layer 2 (missing): task identity + readonly inventory/reconcile + truthful ready

✗ Proposal checklist item “task status readable or not” is currently overclaimed
  in code (`status_readable=True` without a real Beads task-read probe).

✗ Proposal understates that TASK_READY can be true with a nearly empty/random
  .beads tree — this is a safety issue for any later import apply.

✗ “Start Phase 11 spec now” (A) would be OK only if Phase 11 is immediately
  split / scoped; an unscoped “Import / Reconcile Minimal” with apply is too broad.
```

### 3.3 Proposal quality

The proposal is a good decision frame. It correctly refuses “automatically start Phase 11 because 10.5 closed.”  
Its main risk is **preferring a new Phase 10.6 by habit** after 10.5, instead of recognizing that remaining work is **Beads domain model (identity + readonly reconcile)**, which belongs in Phase 11 packaging as **11A**, not another doctor-only phase.

---

## 4. Beads Readiness Assessment

### 4.1 Has Beads truly entered Vibe Control?

**Partial yes.**

```text
Entered for:
  - provider detection
  - setup guidance
  - init preview
  - readiness enum (shallow)
  - skill routing for setup failures
  - explicit deferral of plan import

Not entered for:
  - managed task lifecycle
  - identity-stable import/reconcile
  - truthful “can read task state from Beads”
  - apply gates for create/update
```

So: **first-class for setup/precheck; not first-class for implementation workflow.**

### 4.2 Answers to the proposal’s key questions

| # | Question | Answer |
|---|---|---|
| 1 | Is 10.5 enough to call Beads a first-class task provider? | **No** — only setup/precheck class |
| 2 | Does task doctor check enough? | **Barely for bootstrap; not enough for import** |
| 3 | Does task status check enough? | **Same as doctor; no task inventory** |
| 4 | Is `.beads` detection deep enough? | **No** — any-file initialized is too weak |
| 5 | Does config validation cover task provider? | **Only `provider` key required** |
| 6 | Does vibe-implementation route setup safely? | **Yes for setup**; correctly refuses inventing Phase 11 |
| 7 | Are tests strong enough vs accidental bd init/create? | **Partial** — skill/text + flags; weak argv denylist |
| 8 | Is there a task identity model? | **No** |
| 9–13 | Identity keys / import sources / create/update/delete | **Owner decisions; not in repo** |
| 14 | Start 11 / 10.6 / 11A-11B? | **11A then 11B (route C)** |

### 4.3 Enough to start Phase 11 **implementation**?

**No.**

### 4.4 Enough to start Phase 11 **spec writing**?

**Yes, but only as Phase 11A Test Spec first** — not a single Phase 11 that includes apply.

---

## 5. Recommended Route

### Selected: **C**

```text
Phase 11A — Beads Identity / Readiness Truthfulness / Readonly Reconcile
Phase 11B — Beads Plan Import / Apply
```

### Why not the others

| Option | Verdict | Why |
|---|---|---|
| A | Reject as primary | Unscoped import+apply before identity/readonly reconcile |
| B | Reject as primary | Doctor/status already exist; 10.6 would mostly re-harden 10.5 surfaces |
| C | **Accept** | Matches real blocker (identity + readonly reconcile) and keeps apply behind a gate |
| D | Reject as primary | Phase 6 debt is knowledge drift; parallel fix only |
| E | Not needed | C covers the evidence |

### Suggested Phase 11A scope (spec only next; not implementing now)

```text
In scope for 11A Test Spec:
- task identity model (keys, Vibe-managed marker, target scope)
- harden ready/not_ready meaning (deeper .beads / optional readonly bd probe)
- differentiate task doctor vs task status contracts
- readonly reconcile / import dry-run (no create)
- duplicate detection against existing managed tasks
- unmanaged task protection (detect, do not mutate)
- skill routing for readonly reconcile
- tests: no bd init / no bd create on doctor/status/reconcile-dry-run paths

Out of scope for 11A:
- apply create/update
- delete
- broad Beads cleanup
- NotebookLM work
- workflow engine / daemon / SQLite
```

### Suggested Phase 11B scope (later)

```text
- explicit --apply import
- allowed create/update policy (owner decision)
- forbid delete unless separately approved later
- mutation gates + acceptance evidence
```

### Small parallel debt (not the main route)

```text
Optional: soften or environment-gate Phase 6 acceptance already_current==2
so test-acceptance-readonly.sh is not brittle after intentional SSOT edits.
This is D as a side task, not the Beads roadmap.
```

---

## 6. Recommended Immediate Next Step

```text
1. Do NOT implement Beads import/apply.
2. Do NOT create Beads tasks / run bd init.
3. Write Phase 11A Test Spec first (new formal sync/spec doc), including:
   - identity model draft
   - readonly reconcile envelope contract
   - readiness truthfulness requirements
   - explicit non-scope: no apply
4. Update Project Source roadmap only after 11A Test Spec lands:
   Phase 11 → 11A then 11B.
5. Optionally open a tiny separate brief for Phase 6 acceptance assertion debt.
```

Immediate actionable artifact: **Phase 11A Test Spec document** (owner-approved decisions §7 first if blocking).

---

## 7. Decisions Required

项目 owner 需要决定（否则 11A Test Spec 会卡住或猜错）：

```text
1. Task identity 主键应是什么组合？
   candidates: spec id / plan id / repo path / content hash /
               Vibe-managed marker / Beads task id / project_id scope

2. Phase 11 import 输入源：
   formal specs only / implementation plans only / both？

3. Apply（11B）是否允许：
   - create new Beads tasks?
   - update existing Vibe-managed tasks?
   - never delete? (recommended default: forbid delete)

4. Unmanaged Beads tasks：
   detect-and-skip only，还是 fail closed？

5. Ready 的最低标准：
   仅 bd+.beads markers，还是必须通过 readonly bd list/status probe？

6. 是否接受路线 C 的命名（11A/11B），还是坚持改叫 Phase 10.6 + Phase 11？
   （本反馈推荐 11A/11B；若坚持 10.6，范围必须极窄且不包含 import apply。）

7. Phase 6 acceptance 债：现在并行修，还是延后？
```

---

## 8. Evidence Appendix

### 8.1 Key paths

```text
docs/project/proposals/20260714-roadmap-and-beads-readiness-proposal.md
docs/project/reviews/20260714-phase10-5-closeout-validation.md
docs/project/vibe-control-spec.md
docs/harness/phase-execution-contract.md
src/vibe_control/task/doctor.py
src/vibe_control/task/beads_provider.py
src/vibe_control/skills/vibe-implementation/SKILL.md
src/vibe_control/config.py  (REQUIRED_TASKS_FIELDS)
src/vibe_control/templates/control.yaml
.config/vibe-control.yaml
tests/test_phase10_5.py
tests/test_beads_bootstrap.py
```

### 8.2 Commands run (readonly)

```bash
git status --short
.venv/bin/python -m vibe_control.cli task --help
.venv/bin/python -m vibe_control.cli task doctor --json
.venv/bin/python -m vibe_control.cli task status --json
.venv/bin/python -m vibe_control.cli task init-preview --json
.venv/bin/python -m vibe_control.cli task install-guide --json
# local beads_initialized() empty/.beads/any-file experiment
# ripgrep for identity / bd create / reconcile / Phase 11
```

### 8.3 Explicit non-actions

```text
No code implementation.
No Phase 11 spec written in this task.
No Beads task creation.
No bd init.
No Beads mutation commands.
No NotebookLM mutation.
No push.
No dependency install.
No broad cleanup.
```

---

**End of feedback**
