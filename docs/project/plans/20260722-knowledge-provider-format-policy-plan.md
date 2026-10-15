# Plan — Knowledge 按 provider 限制文件格式

**Goal:** Knowledge 一个能力、两个 provider；同步/建索引时按当前 provider 允许的格式放行或拒绝。

**Architecture:** 新增中性的 `format_policy`（扩展名表 + 判定）；corpus 仍列出仓库文档；在 **同步/建索引** 时按 `knowledge.provider` 过滤。不支持的文件：不上传、不进索引，写入 warnings + dry-run 操作说明。

**Tech:** Python，现有 corpus / local_fts / phase8_apply / sync_preview。

---

## 产品规则（人话）

| Provider | 允许进知识库的文件 |
|---|---|
| `local_fts` | 文本：`.md` / `.markdown` / `.txt`（要能当纯文本读） |
| `notebooklm`（Gemini Notebook） | 与 Google 上传提示一致：文档 pdf/txt/md/docx/csv/pptx/epub；常见图片；常见音视频（见代码常量表） |

仓库 registry 仍可登记任意路径；**当前 provider 不支持的格式 = 本次不同步/不索引**，并说清楚。

## 文件

| 文件 | 职责 |
|---|---|
| `src/vibe_control/knowledge/format_policy.py` | 扩展名表、判定、过滤 corpus、人话原因 |
| `managed_names.upload_filename` | 上传名保留真实扩展名（不再一律 `.md`） |
| `local_fts/provider.py` + `store.py` | 建索引前过滤 |
| `phase8_apply.py` / `sync_preview.py` | dry-run/apply 跳过不支持格式 |
| `doctor` / status（薄） | 报告被跳过数量 |
| `docs/harness/knowledge-provider-boundary.md` + configuration | 写清规则 |
| `tests/test_format_policy.py` + 少量接线测 | TDD |

## 任务

1. format_policy + 单测  
2. upload_filename 保留扩展名 + 测  
3. 接到 local_fts sync/rebuild  
4. 接到 notebooklm dry-run/apply  
5. 文档 + 提交  

## 不做（防过度工程）

- 不解析 pdf/图片内容给 local_fts  
- 不自动转换格式  
- 不改 Capability Profile  
- 不把 Google 格式表做成可配置产品面（常量表 + 注释来源即可）
