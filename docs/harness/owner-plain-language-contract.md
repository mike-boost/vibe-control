# Owner plain-language contract

**Audience:** coding agents talking to the product owner  
**Surface:** `vibe describe --json` → `communication_contracts.owner_plain_language`

## Rule

对 owner 说话用正常人能听懂的话。不要用内部黑话、未解释的英文绰号、或让人猜的缩写。

## Do

- 先直接回答问题
- 用「上传 / 同步 / 索引 / 格式 / 限制 / 两个 provider」这类词
- 第一次出现必须解释：例如「SSOT（仓库里作为正式规格的那份文档）」
- 两个 provider 不同时，分开说各自能做什么、不能做什么

## Don't（未解释就禁止）

- managed / managed sync / Vibe managed
- ask-clean / product_ready / closeout / drift / envelope / next_actions（除非当场一句话解释）
- 自创黑话代号

## Knowledge 格式（对齐产品模型）

```text
Knowledge = 一个能力
  ├── provider: local_fts     → 按它的能力限制格式（现在实质是文本/Markdown）
  └── provider: notebooklm   → 按 Gemini Notebook（原 NotebookLM）能力限制格式
```

格式限制应跟**当前选用的 provider**走，而不是假装两边一样，也不是把 Google 网页上的全部格式表硬套到 local_fts。
