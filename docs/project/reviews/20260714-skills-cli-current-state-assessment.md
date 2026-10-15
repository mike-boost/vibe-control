# Skills + CLI Current State Assessment

**Document type:** Read-only current-state assessment  
**Date:** 2026-07-14  
**Scope:** skills + CLI boundary, doctor/init/install model, NotebookLM readiness, Beads readiness  
**Method:** inspect repo sources + readonly CLI probes; no implementation; no NotebookLM mutation; no Beads task creation  
**CLI invocation used:** `.venv/bin/python -m vibe_control.cli` (system `python -m vibe_control.cli` fails without editable install / venv)

---

## 1. Executive Judgment

产品模型 `Vibe Control = skills + CLI` 在文档与命名上已经成立，但**skill 路由能力落后于 CLI 能力**。

- CLI（尤其 knowledge / Phase 8–10）已是确定性主表面：status / sync / retry / reindex / query / publish 有实现与测试。
- Skills 已存在且命名正确（`vibe-knowledge` / `vibe-implementation`），内容偏薄、方向正确，但**不是可决策的路由器**：缺少基于 JSON envelope 的 precheck / init-preview / install-guide / sync-state 路由表。
- Doctor / init / install 模型**部分一致、部分分裂**：task 侧有 `install-guide` + `init-preview`；knowledge 侧有 `login-guide` + `sync-preview`，但没有 `knowledge init-preview` / `knowledge doctor` / `task doctor`；顶层 `vibe doctor` 与 `integration doctor` 重叠且仍带 Phase 3 陈旧文案。
- **Phase 10.5 — Skills, Doctor, Init, and CLI Boundary Hardening：建议 required before Phase 11**（小范围 hardening，不是重做 Phase 8–10）。

---

## 2. What Exists Today

| Layer | Exists | Location / evidence |
|---|---|---|
| Project Source v0.8 | yes | `docs/project/vibe-control-spec.md` |
| Phase 8/9/10 specs | yes | `docs/project/sync/*` |
| Harness contracts | yes | `docs/harness/*` |
| Agent rules | yes | `AGENTS.md` — “Keep skills thin; deterministic behavior belongs in CLI” |
| CLI package | yes | `src/vibe_control/cli.py` + knowledge/task/spec modules |
| Packaged skills | yes | `src/vibe_control/skills/{vibe-knowledge,vibe-implementation}/SKILL.md` |
| Skills manager | yes | `src/vibe_control/skills_manager.py` |
| Installed skills | yes (this machine) | `~/.agents/skills/vibe-*` → symlink to package sources; `vibe skills status --json` → `installed: true` |
| Reviews dir | created by this assessment | `docs/project/reviews/`（此前不存在；acceptance 报告在 `acceptance/`） |

产品一句话（与 v0.8 source 一致）：

```text
Repo / git SSOT files     = truth
NotebookLM / provider     = derived read/query layer
Repo fallback             = degraded read/query when provider is not current
Beads                     = implementation task provider (minimal in V1)
vibe CLI                  = deterministic command surface
Skills                    = thin routers to CLI
```

---

## 3. Current CLI Surface

### 3.1 Command classification (assessment checklist)

| Command | Classification | Evidence |
|---|---|---|
| `vibe doctor --json` | **implemented** | `cmd_doctor`；探针 config / registry / NotebookLM PATH / Beads PATH |
| `vibe config validate --json` | **implemented** | `cmd_config_validate` + tests |
| `vibe integration status --json` | **implemented** | 但 `safe_to_sync` 硬编码 false；next_actions 仍写 “Phase 3” |
| `vibe skills status --json` | **implemented** | `skills_manager.skills_status` + tests |
| `vibe skills install --json` | **implemented** | 默认直接 symlink 写入；`--dry-run` 预览；**无 `--apply` 门闩** |
| `vibe knowledge inventory --json` | **implemented** | 输出 SSOT document 列表（desired corpus inventory）；非完整 `desired_snapshot` hash 对象 |
| `vibe knowledge status --json` | **implemented** | target-scoped `sync_state` / `synced` / reasons / target / ack_persistence |
| `vibe knowledge sync --dry-run --json` | **implemented** | 无 flag → `SYNC_REQUIRES_DRY_RUN_OR_APPLY` |
| `vibe knowledge sync --apply --json` | **implemented** | 显式 `--apply` 才 mutation |
| `vibe knowledge retry --apply --json` | **implemented** | 无 flag 时**默认 dry-run**（与 sync 不同） |
| `vibe knowledge reindex-bindings --json` | **implemented** | `rebuild` = alias only |
| `vibe knowledge query --question-file <file> --json` | **implemented** | status-aware router + repo fallback |
| `vibe knowledge init-preview --json` | **missing** | CLI tree 无此命令；最接近：`sync-preview` / `login-guide` / `auth-status` |
| `vibe knowledge doctor --json` | **missing** | 仅在 `tests/test_phase8_wiring.py` 作为 ack-write 策略字符串出现；非真实 CLI |
| `vibe task status --json` | **partially implemented** | bd 缺失 → `PROVIDER_UNAVAILABLE`；bd 存在 → `NOT_IMPLEMENTED` stub |
| `vibe task install-guide --json` | **implemented** | readonly 安装指引；不执行 install |
| `vibe task init-preview --json` | **implemented** | readonly；推荐 `bd init --skip-agents`；不执行 init |
| `vibe task doctor --json` | **missing** | 不存在 |

### 3.2 Full leaf command tree (discovered)

```text
vibe doctor
vibe config inspect|validate
vibe knowledge inventory|status|query|auth-status|login-guide
vibe knowledge notebook list|status|set-default
vibe knowledge remote-status|remote-inventory|sync-preview|diff|sync-plan
vibe knowledge sync|retry|rebuild|reindex-bindings
vibe knowledge cleanup-phase4-residue|seed-test-sources|smoke replace
vibe knowledge receipt status|inspect|source wait
vibe spec validate|publish
vibe task status|install-guide|init-preview
vibe integration status|doctor
vibe skills status|install
```

### 3.3 Documented-only / stale messaging

- Spec §8.5 列出 task/skills/integration，**未**把 `knowledge init-preview` / `knowledge doctor` / `task doctor` 写成正式产品命令。
- `integration status/doctor` 与 `notebooklm_provider` 仍输出 `safe_to_sync remains false in Phase 3`（Phase 8–10 已落地后的陈旧话术）。

---

## 4. Current Skill Surface

### 4.1 Inventory

| Skill | Defined in repo? | Installed to `~/.agents/skills`? | Planned only? |
|---|---|---|---|
| `vibe-knowledge` | yes — `src/vibe_control/skills/vibe-knowledge/SKILL.md` (~46 lines) | yes — symlink to package source | no |
| `vibe-implementation` | yes — `src/vibe_control/skills/vibe-implementation/SKILL.md` (~42 lines) | yes — symlink to package source | no |

- Install API：`vibe skills status|install`；`SKILL_NAMES = ("vibe-knowledge", "vibe-implementation")`。
- 未发现 `notebooklm-skill` / `beads-skill` 等过时命名；命名与假设一致。
- 职责映射干净：knowledge ↔ NotebookLM/SSOT/query；implementation ↔ Beads/task（Phase 11+）。
- **风格：** thin manuals（禁令 + 少量命令列表），**不是**长静态手册；但也**不是**带决策表的智能路由器。

### 4.2 What skills currently tell the agent to call

`vibe-knowledge` 命令列表：

```bash
vibe knowledge inventory --json
vibe knowledge query --question-file <file> --json
vibe knowledge status --json
vibe config validate --json
vibe doctor --json
```

缺失（相对目标自治路由）：`sync --dry-run/--apply`、`retry`、`reindex-bindings`、`auth-status`、`login-guide`、`sync-preview`、`skills status`、任何 init-preview 等价物。

`vibe-implementation` 命令列表：

```bash
vibe task status --json
vibe doctor --json
vibe config validate --json
```

缺失：`task install-guide`、`task init-preview`、skills install 引导；且 `task status` 在 bd 已安装时返回 `NOT_IMPLEMENTED`。

### 4.3 Skill content debt

- Failure text 仍写缺失 `.vibe/control.yaml`；实际 primary config 是 `.config/vibe-control.yaml`（legacy 兼容仍在）。
- 禁止 mutation 的规则正确，但**没有**“何时先跑 doctor/status/init-preview”的显式决策树。
- Content tests（`tests/test_skills_content.py`）只断言少量字符串存在，不断言路由完备性。

---

## 5. Doctor / Init / Install Model

### 5.1 Intended model vs reality

| Role | Intended | Current reality |
|---|---|---|
| doctor / precheck | readonly health | `vibe doctor` + `integration doctor` 存在；**无** `knowledge doctor` / `task doctor` |
| init-preview | readonly setup plan | **仅** `task init-preview`；knowledge 用 `sync-preview` / `login-guide` 分摊，无统一名 |
| install-guide | readonly human guidance | **仅** `task install-guide`；knowledge 用 `login-guide`；skills 无 install-guide（只有 install） |
| install / init --apply | controlled mutation | knowledge sync/retry：**要** `--apply`；skills install：**不要** `--apply`（`--dry-run` 相反模式）；bd init：**CLI 永不执行**（正确） |

### 5.2 Boundary violations / inconsistencies

1. **`vibe skills install` 默认即 mutation**（写 `~/.agents/skills` symlink），与 knowledge sync 的 “必须 `--apply`” 不一致。`--dry-run` 存在，但不是 `--apply` 门闩模型。
2. **`vibe knowledge retry` 无 flag → 默认 dry-run**；`sync` 无 flag → hard fail。技能若只记 “retry 安全” 会踩坑。
3. **`vibe knowledge status` 的 envelope `next_actions` 是静态三条**，即使 `data.sync_state=drift` / `receipt_missing`。内部 `sync_status` 对 receipt_missing 有更好的 `next_actions`，但 CLI 层未透出。
4. **Doctor 分裂**：顶层 doctor（浅）、integration doctor（深、含 auth probe）、knowledge/task 无专用 doctor。技能难以选单一 precheck 入口。
5. **陈旧 Phase 3 `safe_to_sync=false` 文案**仍出现在 integration / provider 路径，干扰 “auth 已可用但 sync 需显式 apply” 的真实语义。

### 5.3 Can a skill infer failure modes from JSON today?

| Condition | Inferable from current CLI JSON? | Best command(s) |
|---|---|---|
| config missing | yes (`CONFIG_NOT_FOUND`) | `config validate` / `query` / inventory |
| provider unavailable (binary missing) | yes | `doctor` / `knowledge status` / `auth-status` |
| notebook alias unresolved | yes（notebook / remote / sync failures via NotebookError codes） | notebook/remote/sync family |
| auth missing / failed | yes | `knowledge auth-status` / `integration doctor` |
| receipt missing | **partial** — in `data.sync_state` / reasons，但 status envelope `next_actions` 不专指 | `knowledge status`（需读 `data`，勿只信顶层 next_actions） |
| pending sync exists | yes（`sync_state=pending`） | `knowledge status` |
| drift exists | yes（observed `sync_state=drift`） | `knowledge status` |
| Beads not installed | yes | `task status` / `task install-guide` / `doctor` |
| `.beads` not initialized | **no dedicated field** | `BeadsProvider` 不探测 `.beads/`；仅 PATH + init-preview |
| task provider not configured | **ambiguous** | config 可有 task 段，但 `task status` 在 bd 存在时直接 `NOT_IMPLEMENTED` |

---

## 6. Skill Autonomy Assessment

| Desired autonomy | Current skill capability | Verdict |
|---|---|---|
| call doctor before sync/query when readiness unknown | skill 提到 `vibe doctor`，但无 “unknown → doctor first” 决策表 | **weak** |
| call status before query | knowledge skill 列出 status + query，未强制顺序 | **partial**（CLI query 内部已 status-aware，skill 可不重复逻辑） |
| use init-preview when config/setup missing | knowledge：**无** init-preview 命令；task：CLI 有，skill **未列出** | **missing / weak** |
| use install-guide when tool dependency missing | task CLI 有；skill 未列出；knowledge 用 login-guide 但 skill 未列出 | **weak** |
| refuse mutation unless user explicit `--apply` | skill 禁止 agent 直接 mutate NotebookLM；未写清 “只在用户明确要求时调用 sync --apply” | **partial**（规则在 AGENTS/spec 更强） |
| route NotebookLM issues → knowledge commands | 命名与范围正确；命令覆盖不足 | **partial** |
| route Beads/task issues → task commands | 范围正确；`task status` stub + skill 未引用 install-guide/init-preview | **weak** |

重要边界现状：**技能没有重实现 sync/receipt/Beads 逻辑**（好事）。缺口是 **CLI JSON → 下一步命令** 的路由契约未产品化到 skill + envelope。

---

## 7. NotebookLM Readiness

| Capability | Support | Notes |
|---|---|---|
| provider config detection | yes | config load + notebook allow_list |
| notebook allow_list / default_alias | yes | `knowledge notebook *` + remote ops |
| env/ref detection | yes | notebook ref resolution；hash 进 ProviderTarget |
| auth/profile detection | yes | `auth-status` / `login-guide`；`auth_profile_hash` 仍 deferred（spec gap） |
| remote inventory/probe | yes | `remote-inventory` / probe path；synced 需 probe 非仅 ack |
| desired_snapshot build | yes（internal） | `build_desired_snapshot` 用于 status/apply/publish；`inventory` 暴露 document 列表而非完整 snapshot envelope |
| status synced/pending/drift/unavailable/target_mismatch | yes | 另有 `receipt_missing`；CLI status 实测 `drift` + `remote_ack missing` |
| pending-sync retry guidance | **partial** | status `data` 可表达 pending；envelope next_actions 偏静态；`retry` 已实现 |
| reindex-bindings guidance | **partial** | CLI 已实现；status 内部对 receipt_missing 有建议，顶层 envelope 未稳定透出 |
| readonly query fallback | yes | Phase 10 router：synced 才走 provider；否则 degraded/pending/drift |

Knowledge 侧 CLI 成熟度：**高于** skill 路由成熟度。Hardening 重点应是 envelope/next_actions + skill decision table，而不是重写 sync 内核。

---

## 8. Beads Readiness

轻量评估（Phase 11 未做）：

| Capability | Support | Notes |
|---|---|---|
| beads binary detection | yes | `BeadsProvider.which()` / doctor / task status |
| `.beads` directory detection | **missing in provider/CLI** | 本仓库已有 `.beads/`（phase35 已 init），但 CLI 不报告 initialized |
| task provider config | minimal / unclear in task status | status stub |
| `task status` | stub | bd missing → fail；bd present → `NOT_IMPLEMENTED` |
| `task init-preview` | yes | readonly；safe modes `skip_agents` / `stealth` / unsafe |
| `task install-guide` | yes | readonly；不自动 install |
| Phase 11 plan import / reconcile hooks | **documented only** | spec roadmap：Phase 11 pending；无 import/reconcile CLI |

结论：Beads **bootstrap 只读面**已有；**任务状态与 plan import** 未就绪。Phase 11 前应先决定 task doctor/status 最小契约，否则 skill 无法安全路由。

---

## 9. Test Coverage

### 9.1 Already covered (evidence)

| Area | Tests / acceptance |
|---|---|
| skills install/status | `tests/test_skills_install.py`（symlink/dry-run/force/unrelated） |
| skills content smoke | `tests/test_skills_content.py`（浅） |
| JSON envelope shape | `tests/test_json_envelope.py` |
| Beads install-guide / init-preview | `tests/test_beads_bootstrap.py` |
| integration status/doctor | `tests/test_integration_status.py` |
| knowledge status/sync/query/reindex | `tests/test_phase8_*.py`, `tests/test_phase10_query.py`, `tests/test_knowledge_query.py` |
| publish + mutation flags | `tests/test_phase9_publish.py` |
| sync requires dry-run or apply | remote_ops + phase8 CLI tests |
| default gates no real NotebookLM mutation | harness + acceptance phase8/9_10 + `scripts/test-*-readonly.sh` |
| no Beads task creation by default | AGENTS + skill do-not-do；无自动 `bd create` 测试路径 |

### 9.2 Missing tests before hardening

```text
- skill routing contract: given envelope codes/states → allowed next CLI commands
- knowledge status next_actions must vary by sync_state (pending/drift/receipt_missing/...)
- doctor surface matrix: vibe doctor vs integration doctor vs (optional) knowledge/task doctor
- consistency: sync vs retry flag defaults
- skills install mutation gate policy (either adopt --apply, or document exception + test it)
- task status: .beads initialized detection + non-NOT_IMPLEMENTED minimal ready/not-ready
- skill content: primary config path .config/vibe-control.yaml; list install-guide/init-preview
- no accidental claim that knowledge doctor exists (wiring test string vs real CLI)
```

---

## 10. Gaps

| Area | Current state | Evidence | Gap | Recommended action |
|---|---|---|---|---|
| skill inventory | 2 packaged + symlink-installed | `skills_manager.SKILL_NAMES`; `skills status` | 无 | keep |
| skill naming | provider-neutral | `vibe-knowledge` / `vibe-implementation` | 无过时命名 | keep；禁止回退 notebooklm-skill/beads-skill |
| skill routing behavior | thin forbid-lists | SKILL.md 命令子集 | 缺决策表；未覆盖 sync/retry/reindex/guides | Phase 10.5：加 routing table，不搬业务逻辑 |
| CLI command coverage | knowledge 强；task 弱 | CLI help tree | `knowledge init-preview` / `knowledge doctor` / `task doctor` missing；`task status` stub | 决定正式命令集后补齐或明确 alias |
| doctor/precheck | 分裂 | `doctor` + `integration doctor` | 无统一 precheck 契约；Phase 3 文案 | 定义单一 skill 入口或分层 doctor |
| init-preview | task-only | `task init-preview` | knowledge 无同名 setup plan | 新增或把 sync-preview+login-guide 编成 knowledge init-preview |
| install/install-guide | 不一致 | skills install 默认可写；task 仅 guide | `--apply` 语义不统一 | 统一 mutation gate 或文档化例外 |
| NotebookLM readiness | CLI ready | phase8–10 + live status | skill/envelope 路由不足 | harden envelopes + skill |
| Beads readiness | bootstrap only | install-guide/init-preview | `.beads` 探测与 status stub | Phase 10.5 最小 task status；import 留给 11 |
| JSON envelope contract | shape stable | `json_envelope.py` | status next_actions 静态；部分状态靠读 data | status/doctor 输出可机读 next_action codes |
| tests | strong for sync/query；weak for skill autonomy | see §9 | routing / doctor / flag consistency tests | add before claiming 10.5 done |
| documentation/source updates | v0.8 source accurate on phases | vibe-control-spec.md | skill autonomy / doctor matrix 未写入 | 10.5 后更新 Project Source + DECISION_LOG |

---

## 11. Recommended Phase 10.5 Scope

**Recommendation: required before Phase 11**

理由：

1. Phase 11（Beads plan import / reconcile）会扩展 `task` CLI；若 skill 仍只会喊 `task status`（且得到 `NOT_IMPLEMENTED`），agent 会自行发明 Beads 操作，违反 “skills thin / logic in CLI”。
2. Knowledge CLI 已足够强，但 skill + status envelope 不能稳定驱动 “doctor → status → sync-preview/dry-run → 用户批准后 apply”。这是产品模型缺口，不是 Phase 8–10 内核缺口。
3. `docs/harness/phase-execution-contract.md` 要求 “Do not invent sub-phases without a real blocker”。此处 blocker 真实：**skill/CLI 边界与 doctor/init 模型在进入 Beads 实现前不一致**。

### Proposed Phase 10.5 scope (small)

```text
In scope:
- Formalize doctor / init-preview / install-guide / --apply gate matrix in Project Source
- Make knowledge status (and optionally doctor) emit state-specific next_actions / codes
- Upgrade vibe-knowledge / vibe-implementation SKILL.md into thin decision routers (tables only)
- Minimal vibe task status: beads installed? .beads present? ready|not_ready (still no plan import)
- Resolve skills install mutation gate (--apply vs documented exception)
- Remove/replace stale “Phase 3 safe_to_sync” messaging where misleading
- Tests for envelope routing + skill command coverage + flag defaults

Out of scope:
- Phase 11 plan import / reconcile
- Phase 12 prompt generator
- Real NotebookLM mutation smoke
- Native NotebookLM remote note (Phase 8.1)
- Broad cleanup / provider rewrite
```

Candidate name（repo 无更好惯例；与 “Phase 8.0 / 8.1” 小数点风格兼容）：

```text
Phase 10.5 — Skills, Doctor, Init, and CLI Boundary Hardening
```

---

## 12. I Need To Decide

- Whether to introduce **Phase 10.5** before Phase 11（本评估建议：是 / required）。
- Whether skill names remain provider-neutral（证据支持保持 `vibe-knowledge` / `vibe-implementation`）。
- Whether `knowledge doctor` and `task doctor` should become **formal CLI commands**，或 skill 固定路由到 `vibe doctor` + `integration doctor` + domain status。
- Whether `knowledge init-preview` should be a real command（聚合 login/auth/notebook/sync-preview），或仅在 skill 中编排现有只读命令。
- Whether **all** mutating installs must require explicit `--apply`（含 `skills install`），或 skills install 作为已批准例外并写进契约。
- Whether skills may **automatically** run readonly `doctor` / `status` / `install-guide` / `init-preview`，但 **never** auto-run `install --apply` / `sync --apply` / `bd init` without explicit user request.
- Whether `task status` must detect `.beads` before Phase 11, or Phase 11 may land CLI import first with skill update in the same phase.

---

## 13. Evidence Appendix

### 13.1 Commands run (readonly)

```bash
git status --short
git log -5 --oneline
.venv/bin/python -m vibe_control.cli --help
.venv/bin/python -m vibe_control.cli knowledge --help
.venv/bin/python -m vibe_control.cli task --help
.venv/bin/python -m vibe_control.cli skills --help
.venv/bin/python -m vibe_control.cli doctor --json
.venv/bin/python -m vibe_control.cli skills status --json
.venv/bin/python -m vibe_control.cli task status --json
.venv/bin/python -m vibe_control.cli task install-guide --json
.venv/bin/python -m vibe_control.cli task init-preview --json
.venv/bin/python -m vibe_control.cli knowledge status --json
.venv/bin/python -m vibe_control.cli knowledge inventory --json
.venv/bin/python -m vibe_control.cli knowledge sync --json          # fail closed
.venv/bin/python -m vibe_control.cli knowledge sync --dry-run --json
.venv/bin/python -m vibe_control.cli integration doctor --json      # auth probe only
```

### 13.2 Key paths

```text
docs/project/vibe-control-spec.md
docs/project/sync/phase8-ssot-snapshot-ack-sync-spec.md
docs/project/sync/phase9-10-publish-query-spec.md
docs/harness/*
AGENTS.md
src/vibe_control/cli.py
src/vibe_control/skills_manager.py
src/vibe_control/skills/vibe-knowledge/SKILL.md
src/vibe_control/skills/vibe-implementation/SKILL.md
src/vibe_control/task/beads_provider.py
src/vibe_control/integration.py
src/vibe_control/knowledge/sync_status.py
src/vibe_control/knowledge/query_router.py
tests/test_skills_install.py
tests/test_skills_content.py
tests/test_beads_bootstrap.py
~/.agents/skills/vibe-knowledge -> .../src/vibe_control/skills/vibe-knowledge
~/.agents/skills/vibe-implementation -> .../src/vibe_control/skills/vibe-implementation
```

### 13.3 Observed envelopes (abridged)

- `skills status`: `installed: true`, preferred symlink, both skills `points_to_source: true`
- `task status` (bd present): `ok: false`, `NOT_IMPLEMENTED`
- `knowledge status`: `sync_state: drift`, `reasons: ["remote_ack missing"]`, static `next_actions`
- `knowledge sync` (no flags): `SYNC_REQUIRES_DRY_RUN_OR_APPLY`
- `task init-preview`: `init_safe_mode: skip_agents`, `recommended_init: bd init --skip-agents`

### 13.4 Explicit non-actions in this assessment

```text
No code/feature implementation beyond writing this report.
No Beads task creation.
No real NotebookLM source add/delete/update/rename/clean.
No push.
No external dependency install.
No broad cleanup.
```

---

**End of assessment**
)
