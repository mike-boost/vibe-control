# Review — Knowledge local FTS provider spec

**Date:** 2026-07-21
**Reviewer:** owner
**Reviewed doc:** `docs/project/sync/20260721-knowledge-local-fts-provider-spec.md`
**Verdict:** **Feasible — proceed, with one owner-level prerequisite and a short hard-constraint list.**
**Audience:** coding agent (implement after prerequisite is resolved)
**Language:** 中文为主；字段名 / SQL / 命令保留英文。

---

## 0. 结论

可行。SQLite FTS5 作为 knowledge 的**第二个 provider**（retrieval-only、line range 证据、零采购、无 daemon）方向成立，与现有 provider boundary / ask hygiene / forward-only SSOT 契约不冲突。技术问题（行号语义、tokenizer、SQLite 版本探测）都是实现期细节，不否决。

但本 spec 是**第一个可选 provider**，而 Vibe Control 产品**尚未定义"如何选择 provider"的流程**。这是 owner 级前置缺口，必须先补，否则 coding agent 无法确定 config / doctor / describe / product_ready 在多 provider 下的行为契约。

---

## 1. 前置产品决策（owner 必须先回答，blocking）

### P1. Provider 选择流程未定义 —— 本 spec 是第一个可选 provider，这个流程本身要被定义

当前 `AGENTS.md` 写的是"NotebookLM and Beads are required providers for `product_ready` workflows"。引入 local_fts 后，产品需要回答（并落到 `vibe-control-spec.md` / `describe` / `AGENTS.md`）：

| 问题 | 需要的决策 |
|---|---|
| 谁选 provider？ | owner 手动配 `.config`？还是 agent 按"可用性 + 成本"自动选？v1 建议：owner 手动配，doctor 探测可用性，不自动切换。 |
| 选择依据？ | 探测顺序？NotebookLM 安装+auth 优先，否则 local_fts？还是显式 `provider` 字段唯一决定？v1 建议：`knowledge.provider` 显式唯一决定，不做隐式回退到 local_fts（`fallback_provider=repo` 仍是 degraded 兜底）。 |
| 切换 provider 时？ | corpus / sync_state / receipt 是 per-provider 独立的（local_fts 用 SQLite index，NLM 用 receipt），互不污染。需明确：切 provider 不迁移旧 provider 状态，新 provider 从 `drift` 起步。 |
| `product_ready` 语义？ | knowledge 半在不同 provider 下是否等价？local_fts `synced` + index clean = knowledge 半 green；NLM `synced` + ask-clean = green。需明确两者都满足 product_ready knowledge 半，但**不可混用**（一次只认 active provider）。 |
| `describe` 怎么暴露？ | authority map 已列 local_fts / notebooklm / repo 三档，但"为什么选这个、怎么切"的 guidance 缺失。需加 `knowledge_provider_selection_guidance`。 |

**Action：** owner 先在 `docs/project/vibe-control-spec.md` 增加"Provider selection"小节（哪怕 v1 只是"owner 显式配，不自动选"），再 Accept 本 spec。否则 coding agent 在 config 校验 / doctor / product_ready 三处会猜语义。

### P2. 与 `AGENTS.md` 顶层契约冲突（spec §11.3 漏了）

`AGENTS.md` 第 7 行"NotebookLM and Beads are required providers for `product_ready`"与 spec D6（local_fts 可满足 product_ready knowledge 半）直接矛盾。spec §11.3 的文档更新清单**没有 `AGENTS.md`**。

**Action：** §11.3 必须加 `AGENTS.md` —— 把"required"改为"one of {notebooklm, local_fts} satisfies the knowledge half; Beads remains required for task half"。

---

## 2. 实现期硬约束（coding agent 必须遵守，非可选）

这几条是实现期就会翻车的硬问题，coding agent 落地时必须处理，不是 polish：

### C1. 行号语义必须与 Read 工具对齐（spec §6.3 的 `splitlines()` 错）
`splitlines()` 在"文件以 `\n` 结尾"（POSIX 主流 case）下比 `split("\n")` 少一行，且把 `\v \f \x1c \u2028` 当换行。Cursor Read 工具按 `\n` 切 1-based。**改用 `text.split("\n")`**，显式声明行号 1-based inclusive、与 Read 工具对齐。Slice A 加三类测试：`\r\n` 结尾、末尾换行、含 form-feed。

### C2. Tokenizer 不能用 `porter`；必须探测 SQLite 版本 + FTS5 编译（spec §6.2 / §10.1 缺）
- `porter` 是英文 stemmer，CJK 整段不透明 token —— 本仓库 SSOT 大量中英混合，dogfood 自己跑不起来。
- `unicode61` 也不支持 CJK 子串（无空格 → 整段一个 token）。
- 正确选择：**`trigram` tokenizer（SQLite ≥ 3.34）**，但 trigram query < 3 字符命中不了（中文短术语"批准""任务"是 2 字符）→ 需 LIKE fallback。
- doctor **必须** probe `sqlite3.sqlite_version` + `PRAGMA compile_options` 含 `ENABLE_FTS5`，不满足 → `unavailable`，fail-closed，不假装 green。
- 若 owner 不想 v1 做 CJK，则把"CJK 语义召回"显式列进 Non-goals，tokenizer 用 `unicode61 remove_diacritics 2`，并在 describe 警告。

**coding agent 决策点：** trigram + LIKE fallback 是推荐路径；若评估后选 unicode61-only，必须在 spec Non-goals 显式声明 CJK 不支持，不能静默。

### C3. local_fts 走独立 status 路径，不塞进 `evaluate_sync_status`
现有 `evaluate_sync_status`（`sync_status.py`）硬依赖 `provider.list_sources(notebook_ref=...)`，local_fts 无此概念。local_fts 的 status 直接读 SQLite meta + 算 fingerprint 对比。**不要**把 local_fts 塞进 NLM 的 status 评估路径。spec §5 列了 `LocalFtsProvider.status` 但没交代它与 `phase8_runtime.status` 的关系 —— coding agent 需引入 provider dispatch，让 status/query 都按 active provider 分支。

### C4. 复用已 landed 的多 notebook corpus scope，不自造命名
`corpus.py:sync_scope_for_corpus()` 已返回 `ssot_files` / `ssot_files:<alias>`。spec §6.1 自造的 `default` / `notebook-{alias}` 与之并行，会造成两套 scope 命名。**复用 `sync_scope_for_corpus` 输出**（或其 hash）作 index 目录 key。同理，`desired_fingerprint`（§6.4）评估是否复用现有 `DesiredSnapshot.snapshot_hash`，避免并行 fingerprint 体系。

### C5. `pending` 语义不自造
spec §7 自定义 `pending = "crash mid-rebuild"`，与现有 `pending_sync_exists()`（pending-sync.json）语义冲突。local_fts rebuild 用单事务原子提交（clear→insert→commit），crash 不留 pending，**v1 不产生 `pending`**，避免与 NLM 的 pending 机制混淆。

---

## 3. 给 coding agent 的落地建议

1. **先等 P1 / P2 解决再动代码。** P1 是 owner 决策，coding agent 不要替 owner 决定 provider 选择流程。
2. spec 的 Slice A–F 顺序可保留，但 Slice A 必须含 C1 的三类行号测试，Slice B 必须含 C2 的 SQLite 版本探测 + CJK 召回测试（或显式 xfail + Non-goal 声明）。
3. §14 touch list 补 `product_readiness.py`（grep 显示它引用 sync_state，spec 漏列）。
4. FTS5 MATCH query 的 token 必须双引号包裹并剥离 `*"-():` 元字符（spec §8.2 没规范转义）。
5. `matched_terms` 从 `snippet()` 的 `>>>...<<<` 标记解析，零额外查询（spec §8.3 有字段、§8.2 没提取路径）。
6. 核实 `.gitignore` 覆盖 `local_fts/` + `*.sqlite`（vibe_home 可能在 repo 内）。
7. `AGENTS.md` / `vibe-control-spec.md` / `knowledge-ask-ssot-contract.md`（加 `answer_mode=evidence_retrieval` 例外分支）必须同 PR 或紧随更新。

---

## 4. 不否决的理由（给 owner 的信心）

- 方向与 provider boundary / ask hygiene / forward-only SSOT 契约一致。
- retrieval-only + line range 证据是 agent 真正需要的，不引入第二个 synthesizer。
- 零采购 + 无 daemon，作为默认 provider 候选合理。
- 技术问题（C1–C5）都是实现期可解的确定性工作，不是设计风险。
- 真正的设计风险只有一个：**provider 选择流程（P1）** —— 这是产品级缺口，不是本 spec 的错，但本 spec 作为第一个可选 provider 触发了它，必须一并补上。

---

## 5. 一句话给 coding agent

> 方向可行。先等 owner 解决 P1（provider 选择流程）+ P2（AGENTS.md 措辞），再按 spec Slice A–F 落地，实现期守住 C1–C5 五条硬约束。CJK 召回是唯一需要 owner 在实现前再拍板的点（trigram+LIKE fallback vs. unicode61-only + Non-goal 声明）。
