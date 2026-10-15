# Agent 高频场景调研 — Knowledge / Task / 自解释

**目的：** 支撑打磨 knowledge、task、以及「agent 如何学会用 Vibe」——只收**高频 + 有痛点**的场景，**不是**功能 backlog。  
**日期：** 2026-07-17（修订同日：补全对照表 + 与已拍板策略对齐）  
**结论受众：** 产品打磨优先级，不是实现规格。

**Related (must not lose):**

- Settled strategy → [`sync/20260717-knowledge-task-polish-strategy.md`](./sync/20260717-knowledge-task-polish-strategy.md)
- Diagrams → [`product-next-paths.html`](./product-next-paths.html)
- Index → [`PRODUCT_THINKING_INDEX.md`](./PRODUCT_THINKING_INDEX.md)
- Canvas view title (ephemeral): **「Vibe — 自解释 + 高频场景」** — content must stay mirrored here / HTML

---

## 0. 正确分层（纠正）

| 层 | 是什么 | 不是什么 |
|---|---|---|
| Consumer | **Coding agent**（主操作者） | 「网站用户」 |
| Human | 边界 / 审批 / 看 doctor | 日常跑 CLI 的人 |
| **Capability** | `knowledge` / `task`（可 enable；sdd/tdd 占位但无 provider → 不能开） | Repo SSOT 管理产品 |
| **Provider** | NotebookLM / Beads | Vibe 自己 |
| Repo / git 文档 | 今天 knowledge **语料来源**（真源在 git） | **不是** Vibe 功能 |

一句话：knowledge 是能力；NotebookLM 是 provider；SSOT 是 owner 的语料组织方式之一。

---

## 1. Agent 平时怎么「学会」Vibe

### 运行时事实

| 有什么 | 没有什么 |
|---|---|
| 已安装的 `vibe` CLI | 每个 consumer repo 里的 vibe-control 源码树 |
| `~/.agents/skills` 里的**薄 skill** | 把产品 README 整本塞进上下文 |
| consumer 的 `.config/vibe-control.yaml` | 自动拥有产品 git 历史 |

因此：**日常学习契约 = CLI 自解释 + 薄 skill + JSON 信封**，不是「clone 产品 repo 再读 docs」。

「安装并学习 https://github.com/…/vibe-control」只覆盖**第一次把 CLI 装上机器**；装完之后，agent 在任意 consumer 里应靠 CLI 自解释工作。

### 已有自解释（调查结果）

| 表面 | 命令 | 状态 |
|---|---|---|
| help | `vibe --help` / 子命令 `--help` | 有 |
| Describe | `vibe describe --json` | 有 · **控制面自述主入口** |
| Brief / Progress / Gateway | `brief` / `progress` / `gateway --intent` | 有 |
| Doctor | `vibe doctor --json` | 有（含 skills missing/mismatch） |
| Thin skills | `vibe skills status\|install` | 有；install-user 会对齐 |
| `vibe readme` | — | **无**（最接近 describe） |

```text
# agent 在任意项目里的第一反应应是：
vibe --help
vibe describe --json
vibe doctor --json
# 而不是去找 vibe-control 仓库文档
```

### 缺口（仍可记，非本阶段旗舰）

- top-level help 仍混 dogfood（`implementation` / `closeout`），对纯 consumer 不够干净。
- 可考虑极薄的 `vibe readme` → `describe` 别名（未立项）。

---

## 2. 为何不直连 provider？（产品买点）

直连 `notebooklm ask` / `bd …` 当然能用。Vibe 解决的是 agent **规模化踩坑**：

| 直连时 agent 常怎么翻车 | Vibe 适配层做什么 |
|---|---|
| 乱问、聊天记忆当证据、没有固定答案形状 | Ask 政策（persona + template + `--new`）+ Facts/MUST 契约 |
| notebook 里混着旧源 / 孤儿源，答案被污染 | sync inventory、ask hygiene、cleanup-candidates（只读） |
| 不知道该同步哪些文件、乱 add/delete | allow_list / 语料选择 / 审批矩阵 / 默认不突变 |
| provider 挂了仍假装「全绿」 | repo fallback + 诚实 degraded；product_ready 门禁 |
| 每个 repo 自己拼 CLI 参数与登录流程 | 统一 `vibe` 信封：code / next_actions / mutation 标志 |
| 能力默认全开，agent 乱碰 live Beads | Capability Profile 默认关；live 双闸门 |

**一句话买点：** Provider = 有没有能力；Vibe = agent 用这能力时别瞎、别越权、失败别装没事。

---

## 3. 和 Pi / Eve / 明星方案对照

### 痛点矩阵

| 痛点 | Pi | Eve | Vibe |
|---|---|---|---|
| agent 乱改文件 / 可扩展工具 | 强 | 强 | **不做**（交给 harness） |
| 长会话断点续跑 | 弱 | 强 | **不做** |
| 规格 MUST / 决策要可复述 | 弱 | 弱 | **主场**（knowledge） |
| 任务登记 + 突变闸门 | 弱 | 中（HITL） | **主场**（task 就绪 + 闸门） |
| 新 repo 装上能用 | 装 Pi | eve init | install + skills + doctor |

### 明星方向 → 我们怎么用

| 明星方向 | 解决的痛 | 对 Vibe |
|---|---|---|
| NotebookLM 源锚定 | 无出处胡说 | knowledge 主 provider |
| Beads 任务图 | 跨 session 失忆 | task provider；**不重做图引擎** |
| CLAUDE.md / AGENTS.md | 行为漂移 | 薄 skill + describe；知识不进 skill |
| LLM Wiki / 决策笔记 | 知识不累积 | owner 语料形态（K-C/K-D），非 Vibe 内置场景 |
| Knowit / AKB / Engram | 跨会话工程记忆 | 未来可选 provider 形态；接口保持可换 |
| Context7 / docs MCP | API 文档过期 | 未来 `search` 候选（K-F），不塞进今天 SSOT ask |
| Pi | harness 过重 | 借「少默认」；不抢 harness |
| Eve | 生产易断难审 | 借「卡点可见」到 doctor；不抄运行时 |
| RRCE 等全家桶 MCP | 一站式 | **警惕范围膨胀** |

**亮眼空位：** 明星多是 provider / harness / 又一个记忆库。Vibe 的空位是把 provider 接到 agent 时的**控制与适配**——不炫，但对「给 agent 用」是缺口。

---

## 4. Knowledge — 高频场景与痛点

**边界：** agent 已经会 grep / 读文件 / LSP。Knowledge 要解决的是**代码里说不清、或塞进上下文太贵**的东西。

| ID | 高频场景 | Agent 典型问法 | 痛点 | 与今天 Vibe |
|---|---|---|---|---|
| K-A | 合约 / MUST 提取 | 「Footer MUST 有哪些？」 | 瞎实现；漏要求 | 当前主用法（语料 + ask） |
| K-B | 策略 / 门禁 / 审批 | 「默认能不能 live apply？」 | 越权突变 | 同一语料；ask 已部分覆盖 |
| K-C | 决策 / 为何如此 | 「为什么选 NotebookLM？」 | 重复争论 | 语料常是 ADR；**非产品内置类型** |
| K-D | 会话失忆 / 已踩坑 | 「上次 flaky 怎么修的？」 | 每会话重踩 | owner 可写入语料；未产品化 |
| K-E | 跨系统 / 跑书 | 「看哪本 runbook？」 | 乱翻外部文档 | 候选 |
| K-F | 外部 API/SDK 现行文档 | 「这库 vX 怎么调？」 | 训练过期 | 未来 `vibe search`？ |
| K-G | 组织级 / 跨 repo 规范 | 「公司鉴权约定？」 | 复制过期 | 多 notebook / allow_list |
| K-H | 上手架构意图 | 「权威读写路径在哪？」 | 只读代码猜错 | 意图层语料 |

### 明确不该抢

| 非 knowledge 主场 | 原因 |
|---|---|
| 在 repo 里找函数 / 改调用点 | grep / LSP |
| 通用全网爬虫问答 | 噪声大；最多未来独立 search |
| 把整个 codebase 向量化当唯一脑 | 易过期；主流偏结构导航 |

### 查询「有价值」的抽象（机制，不是场景菜单）

| 视角 | 查询在干什么 | 对 Vibe |
|---|---|---|
| 逻辑 | 在给定前提（源）下求可证结论；证不出就说推不出 | Uncertainty / Evidence insufficient |
| 语言学 | Agent 要 **断言提取**，不是生成叙事 | Ask 政策约束言语行为 |
| 信息论 | 在源集合上降低不确定性 | 脏源 = 假增益 → hygiene |
| 拓扑直觉 | 答案落在源覆盖内，不飞出流形 | 不发明覆盖外的点 |

**Ask 分型**若做成可切换**政策旋钮**（机制）有价值；若做成内置业务场景菜单则越界。  
**已拍板：** 现阶段 **不** 上多 profile / FAQ 缓存 / vibe search 旗舰功能。Owner 把中间编译物写进自己的语料即可。

---

## 5. Task — 高频场景与痛点

**边界：** 跨会话、可查询的工作记忆；不是人用的 Jira UI。

| ID | 高频场景 | Agent 动作 | 痛点 | 与今天 Vibe |
|---|---|---|---|---|
| T-A | 开干前有什么能做 | `bd ready` / list | 不知从哪继续 | 路径 A；Vibe → TASK_READY |
| T-B | 查状态 / 关联 | `bd show` / list | 复杂查询 | **说明书必覆盖** |
| T-C | 认领 / 防抢跑 | `bd update --claim` | 双写 | Beads 原生 |
| T-D | 干中发现新活 | `bd create` | 只在聊天里 | 极高频 |
| T-E | 阻塞链 | `bd dep` / `blocked` | 错序 | Beads 已有图能力 |
| T-F | 收工证据 | `close` + reason | 假完成 | 路径 A |
| T-G | 长周期跨 session | ready→claim→close | markdown 计划腐烂 | 路径 A 主价值 |
| T-H | SSOT 投影托管 | `vibe task apply` | 规格漂移 | **路径 B 非常规** |

### 路径 A vs B（勿混）

| | 路径 A（日常） | 路径 B（非常规） |
|---|---|---|
| 谁干活 | Agent ↔ `bd` | `vibe task apply` → live Beads |
| Vibe 职责 | enable / doctor / TASK_READY | 闸门内的托管投影 |
| 图 / 重排 | **`bd dep`**（已有） | 不要在 Vibe 重做 |

### Agent 病（反复出现）

1. 假完成  
2. 仪式衰减（不再 `bd ready`）  
3. 卡死的 `in_progress`  
4. markdown 计划爆炸  

**已拍板：** 不做 Vibe 侧调度 / 重排引擎；链条能力交给 Beads。

---

## 6. 安装一条线（装机 ≠ 每项目 clone）

```text
GitHub URL（装机一次）
  → ./scripts/install-user.sh
  → ~/.local/bin/vibe
  → skills align（默认；VIBE_SKIP_SKILLS=1 可跳过）
  → vibe describe / doctor

之后在任意 consumer：
  config → doctor → enable knowledge/task → query 或 bd …
```

---

## 7. 已拍板顺序（与 strategy 一致）

```text
SETTLED 2026-07-17 — sync/20260717-knowledge-task-polish-strategy.md

1) install ↔ skills ↔ doctor（已做）
2) Knowledge / Task：暂不开新旗舰功能；本表仅供参考，不固化场景
3) 明确不做（现阶段）：Ask 多 profile、FAQ 缓存、vibe search、Vibe 任务重排、Option B
```

**边界重申：** Owner/agent 决定语料与业务问法；Vibe 只提供同步 / 问法壳 / 闸门。中间编译物由他们写入语料后再 sync。

---

## 8. 参考（调研入口）

- Vibe：`vibe describe --json`，`src/vibe_control/describe.py`，薄 skills  
- Beads：Yegge Beads；`bd dep` / `ready` / `claim`  
- Knowledge 失忆与 wiki：Karpathy LLM Wiki；Claude Code memory  
- 外部文档接地：Context7 / documentation-grounding MCP  
- 代码导航 ≠ knowledge：Anthropic large-codebase 实践  
- Harness / 运行时：Pi.dev；Vercel Eve（对照用，不跟做）
