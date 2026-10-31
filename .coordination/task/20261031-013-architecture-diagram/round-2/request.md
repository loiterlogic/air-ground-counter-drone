<a id="request"></a>
# F2 · 架构图重设计 · round-2（Worker 自写）

- 来源：Leader [round-1 review](../round-1/review.md#review)；Leader `send_message`（2026-10-31 15:40）。
- 执行会话 ID（正确）：**`281e0d62-6650-4ac1-a5d5-f69d447f19f0`**（round-1 report 误写为父 Leader ID `session-67852665-…`，已在 round-2 report 追加纠正）
- 基线：`cedbc0e6c1e0e23aaf5b0effbf42ed9bf405def6`（只读 `git rev-parse` / `git show` 核对）
- 轮次 2 / 状态：执行中 → 待审查

## 本轮范围

| # | Leader 要求 | 本轮做法 |
|---|---|---|
| 1 | stash 事故：确切命令 / 时间 / 影响范围 / 恢复前后哈希清单 + 可复核证据；不可得须明说 | 写 `evidence/stash-incident.md`：命令原文、时间线（git reflog + 对象 mtime）、被触及路径的 blob 哈希对照、**哪些已不可再验**（`git stash drop` 后无 `refs/stash`，仅靠 odb 中悬挂提交 `25958c9` 可复核） |
| 2 | 正文 ≥12 px、包名 ≥15 px；概览与完整边清单**拆独立资产**；不靠缩字、不靠堆长图 | 概览图重排（减少每包文字、加大字号、加大留白）；完整边清单移到 `system-structure-detail.svg` + 文档；不在测试里改阈值 |
| 3 | Mermaid ④ 必须与声明表一致，或明确是简化视图并列省略项 | 逐条对齐 `EXT_RELATIONS`；同时修 round-1 被我写错的「无缩放损失 / 机械证明美观」过度承诺 |
| 4 | 扩授权 `docs/conventions/包边界.md`：仅修现状解释与依赖图 / ④ 承载者清单；保留四类、不加 ④a/b；不动架构规则与契约 | 按 `package.xml` / `CMakeLists` / `launch` 证据补 sim 标准消息、`air→sim`、`ground→rl`、④ 当前承载者 |
| 5 | 红线标注只引用契约稳定锚点，不复述条文 | 改写为纯引用句 |

## 写入白名单（本轮）

原白名单 + Leader 新增：`docs/conventions/包边界.md`（仅现状解释 / 依赖图 / ④ 承载者）、
`docs/plan/assets/system-structure-detail.svg`（及必要 PNG 预览）。仍**不可**改 CURRENT、归档、共享索引；
**禁止再触碰 stash / index / read-tree**，基线只用只读 `git show` / `git diff` / `git rev-parse`。

## 预算与停止

- 离线渲染 / 测试：累计 **600 s**，单次 **≤120 s**；T1=0，T2 仅离线渲染；不装依赖、不构建仿真。
- 零真实仿真。不 commit / push / reset / clean。连续四轮无区分性新证据则停并交假设台账。

## 交回

report 以 ≤30 行审查摘要开头；提供**不依赖图像输入的清晰预览**（因 Leader 当前模型无图像输入，
须给可文本复核的结构化证据 + 稳定 URL/路径，不能以「我已实看」代替 Leader 判断）。
完成时只把自己 report 置「待审查」，send_message 通知 Leader 后结束，不轮询。
