# Tasks: GUI foolproof — Phase 1 (interactive TUI)

## 1. 交互式主菜单

- [ ] `vibe` 无参数时打印编号菜单（分组：日常 / 知识库 / 维护者），输入数字 dispatch 到对应子命令
- [ ] 菜单支持 `q` 退出；非 TTY 时保持原有报错行为（管道/脚本不被打断）
- [ ] 测试：菜单渲染、数字 dispatch、非 TTY fallback

## 2. 缺参数时给选择器

- [ ] 梳理需要用户"选一个"的参数（notebook alias、provider、skill 名）
- [ ] 缺参数时打印编号列表，用户输入数字即选中；`--json` 模式下保持原行为（报错+机器可读）
- [ ] 测试：选择器列出候选项、选中正确值、--json 不受影响

## 3. doctor 人类仪表盘

- [ ] `vibe doctor`（非 --json）输出：组件状态表 + 一句人话 + 下一步建议
- [ ] 复用现有 doctor 数据结构，只改渲染层
- [ ] 测试：人类输出包含关键行；`--json` 输出字节级不变

## 4. 危险操作确认

- [ ] 列出会产生外部变更的命令（sync run、make、delete 类）
- [ ] 执行前打印将要做的事 + 要求输入 yes 确认；`--yes` 可跳过（给脚本用）
- [ ] 测试：确认流程、--yes 跳过、拒绝时不执行

## 5. 收尾

- [ ] 全量 `pytest -q` 通过（1002 passed / 2 skipped / 0 failed 基线）
- [ ] CHANGELOG `unreleased` 记一笔
- [ ] commit + push（noreply 邮箱，mike-boost 身份）
