<a id="goal"></a>
# F2 · 架构图重设计

来源：用户 2026-10-31 新增要求；[批次入口](README.md#plan-index)。

先学习 C4/成熟架构图分层与布局方法（优先本地非 reference 成功案例，再官方资料），在报告写学习来源、采用原则与布局草图，再修改。对照现有包边界和接口分层，减少全连接线堆叠，概览与细节分层，字体和留白按 README 实际显示宽度设计。

<a id="scope"></a>
## 实施边界

docs/conventions/系统结构图.md、scripts/demo/render_structure_svg.py、scripts/tests/test_structure_diagram.py、docs/plan/assets/system-structure.svg 及同前缀必要 PNG。README.md 仅系统结构图展示区可改。

<a id="exit"></a>
## 出口判据

八包职责、消息/库/运行/外部依赖语义准确；SVG 可重复生成；提供 PNG 预览并实际看图，820px 显示宽度文字清晰、节点不重叠、线不压字、无裁切；相关已有回归通过，避免只凭字符串断言宣称美观。

验收结果：**技术与文档一致性通过，视觉效果待验**（Leader，2026-10-31）。独立生成器自检 exit 0、32 项回归通过；概览 820×804，包名 15px、正文 12px，明细独立 820×839。Leader 当前模型不支持图片输入，不能宣称已亲眼验收视觉效果。见[独立审查](../../../.coordination/task/20261031-013-architecture-diagram/round-2/review.md#review)。

- 可查看[概览](../../plan/assets/system-structure.png)与[依赖明细](../../plan/assets/system-structure-detail.png)。
- 包边界事实修订已随 round-2 扩白名单完成；保留四类关系。
- stash 误操作及恢复证据保留，已独立核实新计划入口与快照一致、索引无冲突，未推定全仓零丢失。
- 既有依赖声明审计告警登记为后续维护，不在本单改包配置。

> **追加（2026-10-31，用户裁定）**："图片我看了没问题" → 视觉项关闭，本任务转为**已验收**。上文"视觉效果待验"是当时 Leader 侧的无图像输入边界，保留不重写。
