<a id="request"></a>
# F2 · 架构图重设计 · 批次派工

- 来源：用户授权四项工作及独立并行；Leader 本单裁定。
- 任务 ID：20261031-013-architecture-diagram；轮次 1；状态：待执行。
- 基线：main / cedbc0e6c1e0e23aaf5b0effbf42ed9bf405def6。Leader 已归档旧计划并修改导航，四单同期改动均为预期，禁止覆盖或回滚。接单记录实际 diff 与指纹。
- 计划：[本单目标](../../../../docs/plan/f2-architecture-diagram.md#goal)；[并行授权](../../../../docs/plan/README.md#parallel)覆盖旧协议冲突。先读 AGENTS、计划、相关契约锚点与规则，不预读无关历史。

## 目标与学习

先学习 C4/成熟架构图分层与布局方法（优先本地非 reference 成功案例，再官方资料），在报告写学习来源、采用原则与布局草图，再修改。对照现有包边界和接口分层，减少全连接线堆叠，概览与细节分层，字体和留白按 README 实际显示宽度设计。

## 写入白名单

docs/conventions/系统结构图.md、scripts/demo/render_structure_svg.py、scripts/tests/test_structure_diagram.py、docs/plan/assets/system-structure.svg 及同前缀必要 PNG。README.md 仅系统结构图展示区可改。
另可写本任务 report/evidence 和本单计划的实施事实，不能代写验收。CURRENT、归档、共享索引由 Leader 写，禁止 Worker 覆盖。各单写入范围隔离，未知冲突先报告。

## 授权与停止

零 ROS/GZ/PX4/构建。授权离线渲染与相关测试累计 900 s，单次 ≤120 s；次数仅记账，可使用已有渲染工具，不安装系统依赖。T1=0，T2 仅此离线渲染授权。产物 experiments/f2-diagram/。
本批次 N=6 是记录检查点而非已知根因修复的机械停止上限；K=4 保留。连续四轮无区分性新证据则停止并提交假设台账；不是“没达成功就不可测”。在资源总量内有区分性进展可继续实施重验，保留所有失败与预算账目。超总时间、契约风险、未知漂移或范围越界立即停报。不得 commit/push/reset/clean，不派孙代。

## 验收

八包职责、消息/库/运行/外部依赖语义准确；SVG 可重复生成；提供 PNG 预览并实际看图，820px 显示宽度文字清晰、节点不重叠、线不压字、无裁切；相关已有回归通过，避免只凭字符串断言宣称美观。

## 交回

报告以 ≤30 行审查摘要开头，写执行会话 ID、基线、文件差异、学习/设计依据、命令/退出码/证据、预算、未执行与未决。完成时只更新自己的 report 状态为待审查，用 send_message 通知 Leader 后结束；不改 CURRENT、不等审查、不轮询。
