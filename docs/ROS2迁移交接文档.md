# ROS2 交接文档（契约真源）

> **角色**：本项目唯一的**契约真源（Contract Source of Truth）**（见 [GLOSSARY](../GLOSSARY.md)）。承载不可变约束：命名空间与坐标系、唯一执行口、参数入口、接口语义、硬约束、终态语义、不可回退教训。
> **不承载**：路线图、重构步骤、风险与排期 —— 任务在 [`docs/plan/`](plan/README.md#plan-index) 临时立项（**结档即删**）；编排史见 [归档 Runbook](archive/ROS2迁移步骤.md#top)。
> **历史分离**：原附录 A（ROS1 基线盘点）已移入 [归档](archive/ros1-baseline.md#appendix-a-archived)，不在本真源内（[ADR-0025](adr/0025-publishing-boundary-and-retirement.md#top)）。
> **引用约定**：跨文档引用一律用**稳定锚点**（`<文件>#<锚点>`），**禁止** §章节号（见 [ADR-0002](adr/0002-docs-source-of-truth-and-reference-discipline.md#top)）。
> **基线**：ROS1(Noetic) 参考实现曾冻结为只读归档（`reference/old_ros1/`），该归档已于 **2026-10-31 退役删除**（[ADR-0025](adr/0025-publishing-boundary-and-retirement.md#top)）；本仓**无**旧树可用，**不作代码来源**（见 [ADR-0001](adr/0001-project-positioning-and-execution-scope.md#top)）。

---

<a id="namespace"></a>
## 1. 命名空间与坐标系

- 协同层统一命名空间 `/agc/`。
- **坐标系基准**：`agc_world`（Gazebo world，ENU：+x 东、+y 北、+z 上；位置 m、速度 m/s、角度 rad）为唯一基准。
- **机体系命名固定**：`drone/base_link`、`car/base_link`，**禁止裸 `base_link`**。
  > PX4 SITL 会一次性发布 `map` / `odom` / `base_link_frd` 等历史静态帧；协同层不发布裸 `base_link`。
- 含 Header 的协同位置/速度/地图/路径/状态消息 `frame_id=world` 或 Gazebo `world`；`/agc/ground/cmd_vel` 用车体系 `TwistStamped`。

<a id="execution-port"></a>
## 2. 唯一执行口

- **地面唯一执行口**：`/agc/ground/cmd_vel`；**唯一**命令车体运动的通道为地面执行中继（原 `ground_drive_adapter`），任何其它节点**不得**命令车体运动。车体位姿由 GZ Sim 物理引擎产生；**唯一例外**为场景复位的位姿写入（受运行期门控，见 [任务门控](#task-gating)）。
- **空中控制权**：起飞阶段归起飞控制器（原 `drone_launch_controller`）；`release_control` 后由 LQR 轨迹跟踪节点接管。

<a id="params"></a>
## 3. 参数入口

由 launch **单一设置**，节点**不得覆写**：

`/agc/target/source`、`/agc/obstacles/source`、`/agc/air/takeoff_altitude_m`、`/agc/air/follow/*`、`/agc/scenario/dynamic_obstacles`、`/agc/world_file`、`/agc/log/seed`

> `/agc/perception/sensors_file` 已于 **2026-11-06** 随 `perception` 场景轴与 `air_perception`
> 节点退役（用户裁定）：该参数原指向的 4 个 `perception_sensors*.yaml` 通道变体无消费者、
> 运行期行为完全相同，已整体删除。契约不再保留该参数入口；量程 R=30.0 的推导登记处
> 改为 `air.yaml` 的 `standoff_follower` 注释与[飞行高度规范 K1](conventions/飞行高度分层与按地图定高.md#where)。

<a id="perception-path"></a>
**目标源选择（`/agc/target/source`）**：`/agc/targets` 的**唯一发布者**恒为 `gt_adapter`。

| 取值 | 位置来源 | 几何门控 | 用途 |
|---|---|---|---|
| `gt_adapter` | 仿真真值直取 + 噪声/延迟/丢包建模 | **无**（不分远近） | 目标指示链路的不确定性基线 |

- **`air_fusion` 已于 2026-11-04 退役**（用户裁定，见 [ADR-0009](../docs/adr/0009-perception-truth-derived-and-vision-path.md#top)），
  故本参数**只有一个有效取值**，不存在"二选一"也不再存在双发布者风险。
- **`air_perception` 节点与 `/agc/air/obs` 已于 2026-11-06 删除**（用户裁定「彻底删」）：
  它们在 `air_fusion` 退役后没有任何订阅者，`sensors_file` 通道配置不影响 `/agc/targets`。
  即**目标指示不分远近**；不得据任何"传感器量程 / FOV / 丢包"配置宣称本仓当前存在
  感知质量差异或感知量程限制。

- 目标检测/追踪**不是本项目范围**：目标位置**始终由真值给出**，`/agc/targets` 不得由图像识别产生
  （[ADR-0009](../docs/adr/0009-perception-truth-derived-and-vision-path.md#top) (a2)）。
- **视觉定位路径（`perception_path=vision`，含 `camera_tf` / `vision_target` / 像素检测器）已于
  2026-11-04 整体退役**，本契约不再保留该路径的任何接口要求。
- **`/agc/perception/path` 参数随之删除**：不存在"第二条感知路径"，故不存在路径互斥问题。
- **本轮不改变**既有 9 消息 ABI（[#messages](#messages)）与唯一执行口（[#execution-port](#execution-port)）。
- 产物（`summary.json`）仍保留 `perception_path` / `detector_backend` / `vision_model` 三键，
  值恒为 `truth` / `none` / 空 —— **仅为 schema 不漂移**，不表示存在可选路径。

<a id="camera-chain-constraints"></a>
#### 相机链路约束（**已随视觉路径退役，本节仅存历史边界**）

原四条硬性接口（光学系经 tf 变换、时间戳取源图像、时间跳变后 tf 查询可能失败、
`camera_info` 存在性依赖相机机型）的前提是"用像素反推目标位置"。该路径已退役，
四条要求**不再对任何活跃节点生效**。

保留本节的理由只有一个：**将来若重启视觉类需求（如无人机正俯视生成障碍物地图），
必须重新实现并重新裁定这些约束**，不得引用本节当作"已满足"，也不得复用本仓已删代码。

> **适用域（历史记录，同属已退役口径）**：原"射线 × 高度平面求交"仅在固定巡航高度的基准臂
> 成立，且须标注该前提；对**俯视**相机该算法**不成立**（射线近垂直向下，深度信息退化为飞行高度）。
> 这一条对将来做俯视障碍物识别同样有效——**不得**沿用该算法。

<a id="task-gating"></a>
## 4. 任务门控与场景复位

- 任务门控 `/agc/task/start`；状态 `/agc/task/state`（`AgcTaskState`）。
- 场景复位 `/agc/scenario/reset`；`scenario_reset` 受**运行期门控**（非运行期不得写位姿）。

<a id="messages"></a>
## 5. 消息与服务

协同层消息（`air_ground_core`，迁移后独立为 `agc_msgs`）共 9 个，**字段与顺序不得变更**：

`AgcTaskState`、`AirObservationArray`、`ObstacleObservation`、`ObstacleTrack`、`ObstacleTrackArray`、`SensorObservation`、`TargetObservation`、`TargetTrack`、`TargetTrackArray`

> 其余包的消息/服务清单见 [归档的 ROS1 基线盘点](archive/ros1-baseline.md#appendix-a-archived)（A.4）。迁移后**接口语义不得变更**。

<a id="empty-array-semantics"></a>
### 5.1 数组消息的空数组语义（**2026-11-03 新增强化**）

**`TargetTrackArray` 的空数组 = 「本拍无新观测」，不是「目标消失」。**

消费者（`standoff_follower` / `trajectory_tracker` / `task_manager` / `capture_adjudicator`）
**SHALL** 保持上一有效航迹不动，由**年龄**（`ref_max_age_s` / `target_max_age_s`）判定失效——
那才是 [C10](#hard-constraints) 的「过期即冻结」。

**为什么必须写进契约**（2026-11-03 实测，四个消费者**全部**违反过）：

感知侧因**丢包 / 门控拒绝 / 延迟未到期**会发布空数组，这属于**正常节拍**而非故障。
把空数组当作"目标丢失"会让下游在**每一拍丢包**时误判航迹失效，后果分两档：

| 消费者 | 误判后果 |
|---|---|
| `standoff_follower` | 每次丢包即冻结跟踪（`drop_prob=0.1` @10 Hz ⇒ 约每 10 拍一次） |
| `trajectory_tracker` | 同上，且已建立后进入 `hold` |
| `task_manager` | `targetFresh()` 立刻返回 false → **状态机卡在 `AIR_SEARCH` 直到 TIMEOUT** |
| `capture_adjudicator` | 火控误判目标失效，交火窗口关闭 |

**判定口径**：空数组只影响"本拍有没有新数据"，**不影响**"目标是否已失效"；
后者**只**由航迹的 `header.stamp` 年龄决定。

> 该条与 [#perception-path](#perception-path) 的「无模型显式降级」一致：
> 降级 / 丢包都表现为空数组，**不得**让下游把"没数据"读成"没目标"。

<a id="hard-constraints"></a>
## 6. 硬约束（逐条复验）

<a id="hc-1"></a>
1. 8 字轨迹为**真八字**（Gerono，`rx=15` / `ry=9` / `h=2.5 m`），全程恒速、无加减速（线速度 `v=2.0 m/s`，弧长参数化）。
<a id="hc-2"></a>
2. 距离阈值顺序必须满足 紧急 < 碰撞 < 安全。**顺序为不变量**；**绝对值为可标定量**，由地面安全层按 [ADR-0010](adr/0010-safety-thresholds-and-failsafe.md#top) 的 Nav2 时间窗口径、以 W2 实测动力学标定为 `1.0 < 2.0 < 4.0 m`（ADR-0010 已实测回填；旧值 `0.7/0.9/2.4 m` **作废**）。
<a id="hc-3"></a>
3. 实证 / 验收**定性、关键场景**使用**非无头（GUI）**并留记录；**规模数值统计**允许 **headless**，但**须经 GUI ↔ headless 等价核验**（同参数 / 同 seed、关键指标一致），且产物**如实标注** `backend` / `mode`；默认仍无头以向后兼容（[ADR-0018](adr/0018-acceptance-and-coverage-matrix.md#top)）。
<a id="hc-4"></a>
4. 训练与评估成功定义统一：**超时一律算失败**，只有显式完成才算成功。
<a id="hc-5"></a>
5. 每个 episode 起始必须把轨迹相位复位到 t=0。
<a id="hc-6"></a>
6. 安全滤波器参数须用**真实逃逸能力**（如 `lateral_speed = min(max_offset_xy, max_offset_change/dt)`）。
<a id="hc-7"></a>
7. 场景生成须保证**出生净空 ≥ 可标定下限**（按新 C2 安全档 + 实体外伸推导，见 [ADR-0012](adr/0012-spawn-clearance-and-reset-transaction.md#top)；旧值 `2.4 m` **作废**）；复位失败最多重试 3 次且不占 episode 预算。
<a id="hc-8"></a>
8. 状态机终态为"抵近并持续跟踪"，`SUCCESS` **不得**表述为"拦截完成"。
<a id="hc-9"></a>
9. 评估报告须含 `shield_infeasible_rate` 与 `reset_failure_rate`。
<a id="hc-10"></a>
10. **无人机对目标的跟踪常开**（非可选；原"跟随默认关闭"作废）：保持**安全间距**（不紧贴），目的为**不丢失目标**；跟踪要求目标新鲜（`ref_max_age_s=0.5`）且 `confidence≥0.5`，过期即冻结。无人机同时负责**自身飞行安全**（自避障）。

> **回归挂载**：每条约束挂到"首次使其可验证"的 workstream，映射表见归档 Runbook 的 [硬约束挂载表](archive/ROS2迁移步骤.md#hard-constraint-mounting)（历史编排记录，非约束）。

<a id="terminal-semantics"></a>
## 7. 终态语义

- 阶段划分：**阶段 A = 跟踪**；**阶段 B = 拦截**（本轮启用阶段 B）。
- 地面任务**跟踪**终态统一为 `TRACKING_SUCCESS`（"抵近并持续跟踪"）；**不得**表述为"拦截完成"。
- **拦截达成**终态为 **`INTERCEPT_CONFIRMED`**（阶段 B 启用，见 [ADR-0011](adr/0011-interception-and-fire-control.md#top) 的 W6 修订），由 `reason_code` 区分方式：物理捕获 `CAPTURE_NET`（[ADR-0011](adr/0011-interception-and-fire-control.md#top)）/ 行为级干扰 `JAM_RTL|JAM_LAND|JAM_HOLD|JAM_LOST`；**不新增消息枚举**（[#messages](#messages) 字段 / 顺序不得变更）。
- 失败 / 中止终态：`MISSION_FAILED`（超时 / 未达成）、`ABORTED`（外部中止）、`INFRA_FAILURE`（门禁失败）。

<a id="lessons"></a>
## 8. 不可回退教训

- **已知竞态（必须在 ROS2 版修复）**：`/agc/task/start` 门禁先校验 odom 再调 `/agc/scenario/reset`，导致 `odom_valid` 被无条件置 false、`evaluate()` 读到 `ODOM_INVALID`。**必须改为 reset 后再校验。**
- **已修复教训（必须保留门控）**：非运行期写车体位姿会覆盖 `car_start`，必须用 `/agc/task/state` 运行期门控。

<a id="decisions"></a>
## 9. 已决事项

| 议题 | 结论 | 记录 |
|---|---|---|
| PX4 链路 | uXRCE-DDS + `px4_msgs`，弃 MAVROS | [ADR-0005](adr/0005-px4-toolchain-and-link.md#top) |
| 工作空间形态 | 单一项目根 `/home/chen/AGC`；ROS1 只读归档 | [ADR-0001](adr/0001-project-positioning-and-execution-scope.md#top) |
| Nav2 范围 | 模式全覆盖 · 进程按域选用 | [ADR-0003](adr/0003-nav2-paradigm-absorption.md#top) |
| RL 角色 | 地面主控(c2)；Nav2 作安全层与离线基线 | [ADR-0004](adr/0004-ground-control-rl-primary-and-nav2-safety.md#top) |
| 地面驱动 | 真实物理（GZ DiffDrive），弃 `kinematic_sim` | [ADR-0007](adr/0007-scene-geometry-single-source-and-layout.md#top) |
| 节点语言 | C++ 实时域 / Python RL 域 | [ADR-0020](adr/0020-package-boundaries-and-runtime-topology.md#top) |
| PX4 本体形态 | `toolchain/` 外部依赖（pin v1.15.4）；`px4_msgs` 内联 `src/` | [ADR-0005](adr/0005-px4-toolchain-and-link.md#top) |
| Nav2 吸收（代码层） | 交叉原则，W1–W6 吸收矩阵 | [ADR-0003](adr/0003-nav2-paradigm-absorption.md#top) |
| 实机 / 纯仿真 | 纯仿真优先，预留接口 | [ADR-0001](adr/0001-project-positioning-and-execution-scope.md#top) |
| 文档真源分层 | 每类信息一个家 + 稳定锚点引用 | [ADR-0002](adr/0002-docs-source-of-truth-and-reference-discipline.md#top) |
| 执行组织 | 职责域 workstream（W0–W8） | [ADR-0001](adr/0001-project-positioning-and-execution-scope.md#top) |
| 实验产物 | 唯一落点 `experiments/<campaign>/<run_id>/` | [ADR-0006](adr/0006-experiment-artifacts-and-evidence-discipline.md#top) |
| 定位（重写即交付物） | 软著 / 平台；论文产出于纯仿真 | [ADR-0001](adr/0001-project-positioning-and-execution-scope.md#top) |
| 研究主线 | 移动式主动拦截系统（D 主 / A 核）；RL·融合归后续 | [ADR-0001](adr/0001-project-positioning-and-execution-scope.md#top) |
| 拦截范围 | 物理捕获（**发射式网**）+ 行为级电子干扰（EMI 不建模）；入侵者 **PX4 化** | [ADR-0011](adr/0011-interception-and-fire-control.md#top) |
| 执行范围出口 | 到 W6；W7 / W8 归后续；拦截落 W2 / W6 | [ADR-0001](adr/0001-project-positioning-and-execution-scope.md#top) |
| 空地协同口径 | UAV 常开 standoff 跟踪 + 自保；地面自主规划 | [ADR-0001](adr/0001-project-positioning-and-execution-scope.md#top) |
| 通用控制层 / 共享 LQR | `agc_control` 插件化（pluginlib），air / ground 共用 | [ADR-0004](adr/0004-ground-control-rl-primary-and-nav2-safety.md#top) |
| UAV 轨迹 / 跟踪参数 | 真八字 Gerono + 恒速 `v=2.0`；C1 修订 | [ADR-0008](adr/0008-air-trajectory-and-tracking-calibration.md#top) |
| 地面安全阈值 / 平台 | C2 厘清为"顺序不变量 + 可标定绝对值"；地面平台保形换装为差速 UGV（保 DiffDrive） | [ADR-0010](adr/0010-safety-thresholds-and-failsafe.md#top) |
| 物理捕获机制 | 改为**发射式网**；交战包络由网发射物理模型推导；裁决器可插拔 | [ADR-0011](adr/0011-interception-and-fire-control.md#top) |
| 捕获裁决口径 | 现「入包络即命中」为 W6 **闭式占位**（仅产出终态 / 指标）；后续口径 = **火控窗口 + 瞄准提前量** | [ADR-0011](adr/0011-interception-and-fire-control.md#top) |
| C7 出生净空 | 语义拆分；下限改为可标定量（新 C2 + 实体外伸推导），旧值 `2.4 m` 作废 | [ADR-0012](adr/0012-spawn-clearance-and-reset-transaction.md#top) |
| `task_manager` 架构 | **自研确定性 C++ 状态机**（吸收行为树模式，不引入 `bt_navigator`） | [ADR-0014](adr/0014-task-fsm-and-scenario-transaction.md#top) |
| C3 验收范围 | 定性 / 关键场景须 GUI；规模数值统计允许 headless（须 GUI ↔ headless 等价核验 + backend/mode 标注） | [ADR-0018](adr/0018-acceptance-and-coverage-matrix.md#top) |
| 捕获裁决器替换契约 | ADR-0011 的「调用方不改」**范围澄清**：对外视图 / ABI 不变，内部允许 shot 生命周期与异步事件演进 | [ADR-0011](adr/0011-interception-and-fire-control.md#top) |

---

<a id="appendix-a"></a>
## 附录 A：ROS1 基线盘点（已移入归档）

> **历史，不是约束**：原附录 A（迁移前 ROS1 系统盘点）已移至 [ROS1 基线盘点](./archive/ros1-baseline.md#appendix-a-archived)，仅作行为对照，**不作为代码或规范来源**。
> 保留本锚点只为让既有引用 `#appendix-a` 仍能落到导航说明；**活约束仍在本文第 1–9 节**（[硬约束](#hard-constraints)）。
