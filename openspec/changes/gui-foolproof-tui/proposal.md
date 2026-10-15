# Change: GUI foolproof — Phase 1 (interactive TUI)

## Why

`vibe` 目前是纯 CLI：18 个子命令，靠 `--help` 自学。对 owner（非技术细节导向）不友好，
与"傻瓜化"目标有差距。参考项目：

- **CC-switch 家族**：动词极简（`list`/`current`/`switch`），省参数时弹出可搜索选择器，
  `current` 永远先告诉你"现在是什么状态"。
- **magpie**（13k stars）：同一后端，多种界面（menu bar / TUI / web UI / CLI）任选；
  **Profiles** 把整套配置存成一个名字一键切换（个性化）；Library 写一次、各 agent
  格式自动适配；预设（preset）代替手写 JSON。
- **EasyCLIProxyAPI**（Tauri 桌面）：Home 大盘一眼看清运行状态、一键启停、
  一键复制 endpoint；OAuth 集中授权页；操作前自动备份、可回滚。

共同灵感：**先让人"看见状态"，再让人"一键做事"，最后才暴露底层。**

## What

Phase 1 只做 CLI 内的交互式体验（零新依赖，纯 Python stdlib）：

1. `vibe` 无参数运行时进入交互式菜单（而不是报错+help），按数字选功能。
2. 需要选东西的命令（如 notebook alias、provider）在缺参数时弹出编号列表让用户选，
   而不是直接报错（学 CC-switch 的 selector fallback）。
3. `vibe doctor` 增加人类可读的仪表盘输出（当前只有 `--json` 对 agent 友好，
   对人不友好）：每个组件一行状态 + 一句人话 + 下一步建议。
4. 破坏性/外部变更操作前打印将要做的事并要求确认（学 EasyCLIProxyAPI 的"先备份"思路，
   此处先做确认，将来再做自动备份）。

## Non-Goals

- 不做真正的图形界面（Phase 2 再议：`vibe dashboard` 本地 web 大盘）。
- 不做在线多用户 portal（长期愿景，另立 change）。
- 不改变任何现有命令的参数语义；`--json` 输出保持机器可读不变。
- 不新增第三方依赖（保持 `PyYAML` 唯一核心依赖）。

## Acceptance

- [ ] `vibe` 无参数进入菜单，选择后可达对应命令。
- [ ] `vibe knowledge notebook --json` 等缺参数场景给出可选列表而非裸报错。
- [ ] `vibe doctor` 人类输出包含：每个组件状态、人话解释、下一步建议。
- [ ] 全量测试保持 1002 passed / 2 skipped / 0 failed。
