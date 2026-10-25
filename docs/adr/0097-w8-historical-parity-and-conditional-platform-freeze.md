# W8-E1b：ROS1 历史证据对照与条件平台冻结（旧环境不可重建）

## Status

accepted（2026-10-25：ROS1 Noetic 运行时不可用、旧树无运行产物；按评审 F-12 缩为历史证据对照；平台冻结为 conditional）

## Date

2026-10-25

## 背景

W8-E1 原要求“ROS1 / ROS2 同场景、同 seed 行为对照，随后平台冻结”。本机现状：

- `reference/old_ros1/` 存在（源码 + 文档），但 **`/opt/ros` 只有 `jazzy`，无 `rosrun` / `rosversion` / ROS1 Noetic**。
- `reference/old_ros1/` 内**没有旧 run 的 bag / 日志 / metrics**，只有文档与源码；历史结论是文档中的固定样例验收（如 M6 4/4、N5 51/51），不是可重算的总体估计。
- 旧树是 ROS1 Noetic + catkin + Gazebo Classic + MAVROS + PX4 `iris_3d_lidar`；当前是 ROS2 Jazzy + colcon + GZ Harmonic + uXRCE-DDS + `px4_msgs` + `gz_x500`。两者不是同物理 / 同中间件控制变量。

评审 [F-12](../reviews/agc-review-2026-10-14/30-未来.md) 的前提已明确：**若旧环境不可重建，缩为历史证据对照，不建议复活 MAVROS**。本 ADR 据此做范围裁定。

## 决策

### (a) W8-E1 拆分

- **W8-E1a 模式等价**：GUI / headless 等价 pilot + 条件性正式等价。当前 gate `not_evaluated`；性能混杂已修复（GPU-GUI RTF 与 headless 对齐），但 active FCO / 率类散布使 δ≤0.05、n≤40 下正式等价不可行（[ADR-0096](0096-w8-gui-headless-equivalence-design-bounds-and-gate.md)）。
- **W8-E1b 历史证据对照与平台冻结**：不执行 live ROS1 对照；只对照**可比行为事实**，明确列出**不可比项**，对 ROS2 平台做 **conditional freeze**。
- **W8-E2 修复后 P1/P2 科研确证**：仍不进入；须另立新预注册，且不得复用 pre-fix verdict。

### (b) 对照矩阵（详见报告）

完整证据与逐项判定见 `experiments/w8-parity/20261025-w8-historical-parity/report/historical_parity.md` 与 `metrics/comparison_matrix.json`。摘要：

**可比 / 可冻结（行为事实）**

1. `/agc/` 命名空间；`agc_world` 唯一基准；`drone/base_link` / `car/base_link`，禁止裸 `base_link`。
2. `task_manager` 单一任务状态机；`TRACKING_SUCCESS` = “抵近并持续跟踪”，不得表述为“拦截完成”。
3. 超时一律算失败，只有显式完成才算成功。
4. 每 episode 轨迹相位复位到 t=0；`/use_sim_time=true`。
5. 评估报告含 `shield_infeasible_rate` / `reset_failure_rate`。
6. 尝试记账：`attempted = valid_task + infra_failure + aborted`，`valid_task = tracking_success + mission_failure`；固定样例（4/4、51/51）不代表总体成功率。

**不可比 / 变更设计（不得做数值对照）**

1. 中间件 / 仿真器 / 飞控：ROS1 Noetic + Gazebo Classic + MAVROS + `iris_3d_lidar` vs ROS2 Jazzy + GZ Harmonic + uXRCE-DDS + `px4_msgs` + `gz_x500`。
2. 终态集合：旧阶段 A **禁用** `INTERCEPT_CONFIRMED`（无拦截机构）；当前阶段 B **启用** `INTERCEPT_CONFIRMED`（`CAPTURE_NET` / 行为级干扰）。旧“成功率”与当前“捕获率”不是同一口径。
3. 安全阈值绝对值：旧 `0.7 / 0.9 / 2.4 m` 作废；当前 C2 标定 `1.0 / 2.0 / 4.0 m`。顺序不变量可比，绝对值不可比。
4. 出生净空：旧 `2.4 m` 作废；当前按 ADR-0023 可标定下限。
5. RL 栈：旧 `rl_obstacle_avoidance` DQN / 33 维 LiDAR vs 当前 `agc_rl` W7-b；观测、动作、终止不同。
6. 指标：旧六项（避障成功率、最小障碍距离、跟踪误差、路径长度、避障耗时、偏移抖动）与 LiDAR 阈值碰撞 vs 当前 active FCO / active 可见率 / 几何净空 / 捕获 / 超时；只可映射定义，不可对照数值。
7. 场景集：旧 stage2 固定场景 vs 当前 12 场景登记表；只有子集可能共同。
8. 历史 98–100% 成功率是探索性结果（单策略种子、少量布局、LiDAR 代理碰撞），不得与当前正式结果混合汇总。

**不可比 / 无证据**

- 本机无 ROS1 运行时；`reference/old_ros1/` 无 bag / 日志 / metrics；历史结论为文档固定样例验收，不是可重算总体估计。
- 无同物理 / 同中间件控制变量，无法做频率 / 数值 / 终态分布的同条件对照。

### (c) 平台冻结

- **冻结范围**：当前 ROS2 契约（9 消息 / 服务、命名空间、坐标系、终态语义、唯一执行口、安全层、C1–C10、`gui_render_backend=auto`）。
- **冻结状态**：`conditional`。可比行为事实冻结；**live ROS1 parity = not_established**。
- **不做的事**：不冒充“ROS1/ROS2 等价通过”；不把历史固定样例当总体成功率；不复活 MAVROS；不复制旧树代码 / 目录 / 命名。
- **重新开启条件**：若获得可运行的 ROS1 Noetic 环境或可信的旧 run 产物（bag / 日志 / metrics），另立对照任务，按同场景 / 同 seed / 同口径重做，不在本 ADR 内补写。

### (d) 与 W8-E2 的边界

- W8-E2 **仍未预注册**；不得把本 ADR 的 conditional freeze 当作 P1/P2 新证据。
- P1 v5 `inconclusive`、P2 v3 `falsified` / 保留 c2、P2 v2 `confounded` 保持不变。
- v7 未注册；在线 RL 未进入；W7-c 仍 `deferred`。

## 结果

- W8-E1a：模式等价 gate `not_evaluated`；headless 规模统计未授权。
- W8-E1b：历史证据对照报告完成；平台冻结 `conditional`；live ROS1 parity `not_established`。
- W8-E2：未进入。
- 对照报告：`experiments/w8-parity/20261025-w8-historical-parity/`。

## 后果

- **正面**：不再把“旧树可运行”当作隐含前提；W8 的平台冻结有明确可比 / 不可比清单；避免用异构物理 / 终态差异伪造“迁移等价”；W8-E2 的平台边界可引用同一冻结契约。
- **代价**：W8-E1 的原始 live 对照目标未达成；如果后续需要真实新旧数值对照，必须重建 ROS1 环境或取得可信旧产物，成本另计。
- **风险**：conditional freeze 容易被误读成“W8 已通过”；Runbook 与本 ADR 必须显式写 `not_established`，不得写成等价通过。

## 参考

- 当前契约：[`docs/ROS2迁移交接文档.md`](../ROS2迁移交接文档.md#appendix-a)（附录 A ROS1 基线盘点）、[#hard-constraints](../ROS2迁移交接文档.md#hard-constraints)、[#terminal-semantics](../ROS2迁移交接文档.md#terminal-semantics)
- 旧树（只读）：[`reference/old_ros1/docs/ROS2迁移交接文档.md`](../../reference/old_ros1/docs/ROS2迁移交接文档.md)、[`reference/old_ros1/docs/项目指导书/下一阶段任务清单.md`](../../reference/old_ros1/docs/项目指导书/下一阶段任务清单.md)、[`reference/old_ros1/docs/论文指导书/publication_plan_v2_archived.md`](../../reference/old_ros1/docs/论文指导书/publication_plan_v2_archived.md)
- 评审：[F-12](../reviews/agc-review-2026-10-14/30-未来.md)
- 前序：[ADR-0001](0001-greenfield-ros2-rewrite.md)、[ADR-0096](0096-w8-gui-headless-equivalence-design-bounds-and-gate.md)
