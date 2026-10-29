<a id="current"></a>
# 当前交接

- 任务 ID：**20261029-003-p0-3-docs-and-skills**
- 轮次：**1**
- 状态：**执行中**
- 来源：用户授权继续 P0-3，新增退役 Trae、迁出 specs 并适配 skills；Leader 已裁定历史规格保留本地发布边界。
- 当前派工：[第1轮 request](task/20261029-003-p0-3-docs-and-skills/round-1/request.md)；只做文档迁移与指定离线检查，不构建/仿真。
- 最近结档：[P0-2 第1轮 review](archive/20261029-002-p0-2-pause-and-baseline/round-1/review.md#p0-2-round1-review)；6 个内容主题提交，工作区干净，无活跃自动接续机制。
- 上轮：[W8 第24轮](archive/20261027-001-w8-validation-recovery/round-24/review.md#round24-review)：**已关闭（非验收）**；迁移 workstream 保持暂停。
- 当前方向：[项目完成路线](../docs/plan/README.md#plan-index)——P0（暂停/瘦身）→ P1（地图/入口/呈现/视觉）→ P2（交付物）。
- 协作规则：批次授权 N=6 / 熔断 K=4（[ADR-0104](../docs/adr/0104-batch-authorization-and-stall-circuit-breaker.md)）——Leader 不再逐轮审查。
- 已定决策：主场景 `s04_static_static_obs_track`；演示后端 `backend:=full`；视觉识别**接入任务决策**（替代真值感知，见 [ADR-0103](../docs/adr/0103-vision-perception-decision-path.md)）。

**迁移 workstream 暂停，W8 不再接单**（暂停开关见 [PAUSED](../docs/plan/PAUSED.md#paused)）。恢复迁移时改回本指针即可，无需恢复叫醒机制（[ADR-0102](../docs/adr/0102-leader-worker-dual-model-handoff.md) 已退役跨进程叫醒）。

进度见[项目完成路线](../docs/plan/README.md#plan-index)，交接依[协议](README.md#protocol)。
