# Skill Assay 产出物与先决条件 — 设计笔记（交接用）

**Date:** 2026-07-23  
**Status:** draft for next-session implementation  
**Trigger:** owner 反馈：HTML/结论看不懂；facts 不对人；缺先决条件就开测；要分清「给人看」vs「给开发者 agent」

## 1. 产品一句话

Skill Assay 是一台**技能模拟器**：在指定宿主（Cursor / GitHub Copilot）上，按**可验收标准**跑一个 skill，产出一份**人先读的 HTML**，以及一份**可交给 skill 维护者 coding agent 的改进包**。

不是：把内部 telemetry 堆给人看。  
不是：只测「会不会套标题」。  
不是：先决条件不满足还假装测过了。

## 2. 每个 assay 文件夹必须有的两类结果

```text
assay-<host>-<timestamp>/
  OWNER_REPORT.html     # 给人：打开就能懂
  AGENT_PACKET.json     # 给开发者 agent：可直接加载改进
  evidence.json / runs/ # 机器证据（人默认不看）
  snapshot/             # 被测 skill 快照
```

可选：整夹 zip 发给同事；若一文件够，只发 `AGENT_PACKET.json`。

## 3. OWNER_REPORT.html 必须回答的四个问题（人话）

1. **测的是哪个 skill？** 名称、路径、一句话它宣称做什么  
2. **验收条件是什么？** 本轮场景要证明什么（条目化；过/不过/部分过）  
3. **效果如何？** 总评一句话 + 每条验收的结果 + 关键阻塞原因  
4. **接下来怎么办？** 人满意 → 打包给维护者；人不满意 → 反馈改 Assay；维护者 → 用 AGENT_PACKET

**禁止**在人读区展示：`tree_hash`、`assistant_nonempty=2/2`、`stable_fields` 等机器事实串。  
这些只留在 `evidence.json`。

建议 HTML 结构：

- 标题：Skill Assay · {host} · {skill名}
- 总评：通过 / 部分通过 / 未通过 / 无法开测（先决条件失败）
- 被测 skill（是什么）
- 本轮验收条件表（条件 | 结果 | 证据一句）
- 关键问题（若有）：环境限制、skill 缺陷、Assay 自身缺陷（三者分开）
- 给维护者：是否建议转发 AGENT_PACKET / zip

## 4. AGENT_PACKET.json 必须给开发者 agent 的内容

- `skill_under_test`：路径、skill_id、宣称能力摘要  
- `acceptance_criteria[]`：每条 id/描述/result/evidence_ref  
- `overall_verdict` + `blocking_issues[]`（分 class：`skill_gap` | `host_env` | `assay_gap`）  
- `improvement_asks[]`：希望 skill 作者改什么（可执行）  
- `do_not_claim[]`：Assay 没证明的东西，禁止 skill 作者据此宣称  
- `artifact_paths`：完整回复、snapshot 等

## 5. 先决条件门禁（不满足禁止 --execute）

按场景档位：

| 档位 | 测什么 | 必须先满足 |
|---|---|---|
| A 装载/路由 | skill 能否被宿主发现并按约定格式起步 | skill 路径有 SKILL.md；host doctor ok；显式 host |
| B 业务质量 | skill 宣称的工程活能否在真实目标上完成 | A 全部 + **显式 target_repo** + 该档允许的执行能力（如 shell/collector）经 doctor/probe 证明可用 |

规则：

- 缺 `target_repo` 却选业务档 → **fail closed**，dry-run/brief 明确列出缺失先决条件，**不得静默降级成装载测还对人说「测过了」**  
- 业务档若 probe 发现 shell/collector 不可用 → **无法开测** 或标 `assay_gap`/`host_env`，不得把「文中提到脚本名」当成「脚本已执行」  
- 主 agent 在 brief/dry-run 阶段就应向 owner 要齐先决条件；禁止开测后再说「没指定仓库」

## 6. 与当前实现的差距（已知债）

- HTML 把机器 facts 给人看；结论两行黑话，没有验收表  
- AGENT_PACKET 建议动作空泛，没有按验收条目的改进清单  
- 曾跑「装载测」却口头混成业务结论；业务测缺 target_repo 时 agent 没先挡  
- Cursor 深测中 Shell 被拦，collector 未跑，但 checks 仍可因「提到标题/脚本名」得 1.0 → **typed check 过 ≠ 业务过**；需区分「格式出现」与「工作流证据」

## 7. 推荐落地切片（下一会话）

1. Spec 增补：owner HTML 大纲 + agent packet schema + prerequisite gate  
2. `brief`/`diagnose --dry-run`：输出 `prerequisites` 块；业务档缺项则拒绝 execute  
3. 重写 `OWNER_REPORT.html` / `AGENT_PACKET.json` 生成器  
4. 回归：用 engineering-power + agent-city 再跑一档 B，HTML 必须人话可读  
5. 可选：`pack` 默认只打人需要的文件 + agent packet（仍可 full zip）

## 8. 参考路径（本机已有实验）

- 装载档（旧）：`runtime/vibe-skill-assay/assay-20260722-090404` / `...090412`  
- 业务档尝试（Cursor，shell 被拦）：`runtime/vibe-skill-assay/assay-cursor-20260722-093121`  
- 代码：`src/vibe_control/skill_assay/`  
- 原 spec：`docs/project/sync/20260722-skill-assay-spec.md`
