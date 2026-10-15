# Vibe Control Feedback Spec

**Document type:** Formal companion SSOT (product contract)  
**Status:** Accepted — design SSOT + thin CLI shipped (`vibe feedback …`)  
**Date:** 2026-07-17  
**Primary audience:** Coding agents, owners, Vibe maintainers  
**Language policy:** Explanation in Chinese; schemas / paths / commands in English.

**Related:**

- Front/Core → `docs/project/vibe-control-spec.md`
- Human GitHub Issues channel → `docs/feedback.md` (orthogonal; still valid)
- Index → `docs/project/PRODUCT_THINKING_INDEX.md`

---

## 0. What this is / is not

```text
Feedback (this spec)
  = capture of experience signals while using Vibe
  = pain points, owner dissatisfaction, mid-flight bright spots, friction
  = analogy: OS crash / bug reporter that asks for a stack + context bundle
  = artifacts live in the CONSUMER repo
  = sharing with the Vibe Control team is VOLUNTARY

Feedback is NOT:
  - a task system / Beads substitute / path-A work item
  - knowledge SSOT or NotebookLM sync source
  - automatic telemetry / silent upload
  - a product_ready or closeout gate
  - ChatGPT Project Sources
```

**纠正（相对早先讨论）：** Feedback 记录的是「用产品时的体验信号」，不是任务安排、不是任务链。

---

## 1. Why it exists

Coding agents（及背后的 owner）在真实使用中会自然产生高价值信号：

| 信号 | 例子 |
|---|---|
| 痛点 / 摩擦 | doctor 指引不清；skills 漂移；ask 答非所问 |
| Owner 明确不满 | 「这不是我要的控制面行为」 |
| 途中亮点 | 「persona + MUST 形状终于可用」 |
| 类 bug 现场 | 某命令信封误导；降级却假装全绿 |

这些信号若只留在聊天里，会随 session 消失。Feedback 把它们固化成**可脱敏、可携带、可自愿上交**的工件。

内部 / 兄弟团队使用时，反馈意愿通常很高——产品仍保持「自愿上交」，不强制遥测。

---

## 2. Actors & voluntary share

| Actor | Role |
|---|---|
| Coding agent | 主操作者：在 consumer repo 生成 / 更新 feedback 工件 |
| Owner (human) | 可触发（「把这个不满记成 feedback」）、可审阅脱敏、可决定是否分享 |
| Vibe maintainers | 仅在**收到自愿提交**的工件后用于改进产品 |

```text
Generate in consumer repo  →  always local
Share to vibe-control team →  opt-in only (issue / PR / zip attach / other)
Never auto-upload
```

---

## 3. Artifact model

### 3.1 Location (consumer repo)

Recommended root:

```text
runtime/vibe-feedback/
```

Rules:

- 属于 **consumer 工作区**，不是 vibe-control 产品仓的 SSOT 库存。
- 默认视为**本地工件**；consumer 可用 `.gitignore` 忽略（推荐对含 doctor 摘录的目录默认忽略）。
- 内部团队若愿意用 git 保存反馈历史，可自行选择提交——仍非产品强制。

### 3.2 Cardinality

一次捕获可以是：

| 形态 | 说明 |
|---|---|
| 单文件 | 一个 `*.yaml`（或 `*.yml`）记录 |
| 多文件 | 清单 + 附件（如 redacted doctor 片段、命令信封摘录） |
| 压缩包 | `vibe-feedback-<id>.zip` 打包上述内容，便于自愿投递 |

### 3.3 Schema (vibe.feedback.v1)

Machine-oriented YAML. Chinese allowed in human text fields; keys in English.

```yaml
schema: vibe.feedback.v1
id: fb-20260717-001                 # stable within the consumer repo
created_at: 2026-07-17T15:12:00Z
vibe_version: "0.5.8"               # vibe --version
consumer_project_id: site           # from control.yaml when present

# Experience signal — NOT a task kind
kind: pain | owner_dissatisfaction | bright_spot | friction | bug_signal

title: short headline
summary: |
  Clear statement of what happened and why it matters.
  Prefer assertions over narrative essays.

# What the agent/owner believes should change (optional)
desired: |
  Optional: what “better” would look like.

# Structured context (all redacted)
context:
  commands:                         # optional
    - "vibe doctor --json"
  envelope_codes: []                # optional: codes from JSON envelopes
  capability:
    knowledge_enabled: null
    task_enabled: null
  # Optional soft links — for orientation only; feedback is still NOT a task
  related_paths: []                 # repo-relative paths, no secrets
  related_task_ids: []              # optional Beads ids if the pain appeared while working a task

redaction:
  policy: vibe.feedback.redaction.v1
  confirmed: true                   # agent/owner asserts secrets stripped

attachments:                        # optional sibling files or zip members
  - path: doctor-redacted.json
    kind: doctor_snippet
```

`kind` 枚举保持短小稳定；不要把业务场景（MUST / runbook / …）塞进 kind。

---

## 4. Redaction contract (mandatory)

**必须去掉：**

- tokens / cookies / session material  
- `.env` 与任何密钥文件内容  
- raw notebook refs / private provider source IDs  
- 账号密码、PAT、个人邮箱（除非 owner 明确且必要）  
- 未脱敏的完整 doctor / provider 原始 dump  

**必须保留（说清楚事情与逻辑）：**

- vibe 版本、安装方式（若已知）  
- 相关命令与**信封 code**（非秘密）  
- capability 是否 enable（布尔）  
- 失败/不满的因果描述：期望 vs 实际  
- 可复现步骤（无秘密参数）  

规则：

```text
If unsure whether a field is secret → [REDACTED]
Redaction is part of “done”; unredacted bundles must not be shared
```

---

## 5. Relationship to other surfaces

| Surface | Relationship |
|---|---|
| `docs/feedback.md` + GitHub Issues | **对人**的提交通道；可附上本 spec 产出的 zip/YAML |
| Beads / task | 正交。Feedback 不是任务。`related_task_ids` 仅可选定位上下文 |
| Knowledge / NotebookLM | Feedback **不是**语料、**不**自动 sync |
| Doctor / describe | 可提供**脱敏摘录**作为附件，不替代 feedback 正文 |
| Diagnostics bundle（若未来有） | 可与 feedback 打包共存；仍须脱敏与自愿分享 |

---

## 6. Product surface (thin CLI)

```text
vibe feedback init-preview --json     # readonly: where files go + redaction checklist
vibe feedback draft --kind … --title … --summary-file … --json
vibe feedback validate --path <id|file> --json
vibe feedback pack --path <id|file> --json   # local zip only
```

Constraints:

- 默认 **不** 上传、**不** 开 Issue、**不** 突变 provider  
- `draft` / `pack` 只写 consumer 本地 `runtime/vibe-feedback/`  
- `validate` 要求 `redaction.confirmed: true` 且无启发式密钥命中  
- 与 Capability Profile 无关（feedback 不是 knowledge/task 能力开关）
- Feedback **不是** 任务系统

---

## 7. Acceptance criteria

- [x] Feedback 文档与本 spec 一致：**体验信号 ≠ 任务**  
- [x] 工件落在 consumer `runtime/vibe-feedback/`  
- [x] 支持单文件目录 + zip pack  
- [x] redaction checklist；`redaction.confirmed` 缺失则 validate 失败  
- [x] 无任何自动上传路径  
- [x] 测试：schema 校验、拒收疑似密钥、pack 前必须 validate  

Agents may still hand-edit YAML; CLI is the preferred path.

---

## 8. Non-goals

- Telemetry / phone-home  
- Auto-filing GitHub issues  
- Treating feedback as SSOT inventory or closeout evidence  
- Building a second task tracker or knowledge wiki inside feedback  
- Requiring consumer repos to commit feedback artifacts  

---

## 9. One-line contract

> **Feedback = 消费者仓内的、可脱敏的体验信号工件（痛点 / 不满 / 亮点 / 摩擦）；类 OS 崩溃反馈包；自愿分享以改进 Vibe；不是任务，不是遥测，不是知识语料。**
