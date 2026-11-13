<a id="top"></a>
# 包边界、语言选型与运行拓扑

## Status

accepted（2026-11-02 由 ADR-0011 / 0059 / 0061 合并；结论未变）

## 背景

三件事曾被当成同一条规则，导致「边界」既说不清也守不住：

1. **语言划分沿袭自旧树**——《目录与命名规范》隐含「节点包用 `ament_cmake`（C++）、RL / 工具用
   `ament_python`」，但**未经显式论证**。
2. **依赖类别混成一条规则**—— 早期 [包边界](../conventions/包边界.md) 的规则 1「`agc_msgs` 是唯一公共
   依赖」与规则 2「其余包之间不得互相依赖对方的库」照字面会**禁止必要的运行依赖**（如 `agc_task` 在
   launch 中起 `agc_air` / `agc_ground` / `agc_perception`），或促使这些真实运行依赖被隐藏、未在
   manifest 声明；依赖方向图也解释不了现状。
3. **多入口重复组装**——`m0_skeleton` / `w6_task_eval` / `w6_full` 各自内联一份**完全相同**的场景配置
   解析（base / registry / carriers 加载、carrier 校验、参数合并、轴断言、manifest 生成），参数路径
   分叉（`full` 另用 `air.yaml`），`backend` 未贯穿 summary，launch 身份字段与**入口名**分离，关键段
   启动依赖由**绝对时间 `TimerAction`**（12 / 25 / 35 s）承载 ⇒ 配置漂移不易发现，拓扑不是可审查实体。

## 决策

### (a) 语言按域固定
- **C++（`ament_cmake`）**：性能 / 实时敏感域—— 空中链路（高频 uORB）、感知融合（高频点云 / 图像）、
  地面安全层（硬约束的实时逃逸能力）。理由：低延迟、可控内存、无 GIL、可给实时保证。
- **Python（`ament_python`）**：RL 与工具脚本—— 依赖 PyTorch / Stable-Baselines 生态。
- **语言不构成接口耦合**：跨域通信只经 `agc_msgs`（topic / service / action），与实现语言无关。
- 若某域后续需换语言，须先复核本篇与其性能假设。

### (b) 依赖按类别分层
| 类别 | 规则 |
|---|---|
| ① 消息 / 接口 | 跨域一律经 `agc_msgs`（叶依赖） |
| ② 库链接 | 仅 `agc_control` 共享库允许被空中 / 地面两侧链接同一实现；除此禁止业务库互链 |
| ③ 运行组合 / launch | 编排者以 `exec_depend` 声明所起进程之包，**不**据此链接其实现库 |
| ④ 外部设备 / 第三方 | `px4_msgs` / uXRCE-DDS、Nav2、`ros_gz` / gz vendor |

**保留**：禁止环形依赖；禁止包间业务库互链。取证依据：同版本 Nav2 的 `nav2_bringup` 对仅被 launch
起进程的包（`navigation2` / `nav2_minimal_tb3_sim` / `ros_gz_sim` / `ros_gz_bridge`）用
`<exec_depend>` 而**不** `find_package` 链接其库，对编译期使用的库（`nav2_costmap_2d` / `nav2_util`）
用 `<depend>`—— 即 Nav2 自身已把「链接库」与「起进程」分开声明。

现状（`agc_task` 起各域 + 承载 PX4 驱动 / 干扰注入、跨域合理使用 `nav_msgs` / `geometry_msgs`）在新
规则下**合规**，**不**迁包。

### (c) 内部库的公共性：承诺必须与安装产物一致
对照同版本 Nav2：公共库包 `nav2_util` / `nav2_costmap_2d` **同时** `ament_export_include_directories`
（`nav2_util` 另导出库目标 `nav2_util_core`）**与** `install(DIRECTORY include/ ...)`，导出 == 产物；
而纯 launch / config 包 `nav2_bringup` 的生成 CMake **无任何** `ament_cmake_export_*`。

本仓事实：`agc_air` 的 `agc_air_lib` 为 `STATIC`、仅本包节点 / 测试使用；`agc_air` 只
`install(TARGETS <node>)` + `install(DIRECTORY launch config)`、**不**安装 `include/`，却曾
`ament_export_include_directories(include)` + `ament_export_dependencies` + `$<INSTALL_INTERFACE:include>`
⇒ 生成的 extras 指向**不存在**的 `install/include`（下游 `find_package(agc_air)` 会报 "exports the
include directory … which doesn't exist" 警告），而全仓**无** `find_package(agc_air)` 消费者。

裁定：`agc_air_lib` 为**纯内部实现**，`agc_air` **不**对外承诺公共接口—— 移除上述导出与
`$<INSTALL_INTERFACE:include>`、不安装 `include/`（对齐「内部 / 仅 launch 包零导出」）。共享通用控制
继续以 `agc_control`（`INTERFACE` + 安装 `include/` + `ament_export_*`）为**唯一**公共库家
（见 [ADR-0004](0004-ground-control-rl-primary-and-nav2-safety.md#top)）。**未**为修 export 新建任何
跨域链接；将来某 helper 若需**真正公共**，须经包边界批准并**同时**安装头文件与正确导出。

### (d) 单一参数化入口与 backend 能力表
`agc_task` 顶层入口**统一为** `main.launch.py`（`backend` ∈ `lightweight` | `full`，默认
`lightweight`）。原 `w6_task_eval.launch.py` / `w6_full.launch.py` **退役**；`skeleton.launch.py`
**保留**为骨架基座（被 `backend:=lightweight` include）。共享配置解析抽取为单一真源
`composition.py`（`load_scene` / `carrier_entry` / `coverage_status` / `compose_params` /
`assertions` / `build_manifest` / `write_temp_params` / `write_manifest`），入口**不复述**解析逻辑；
约束类信息只引用不复述。

**2026-11-06 收口**：`_compose` 曾内联 533 行（含 `yaml.safe_load` 读 `air.yaml`、空中参数合并、
PX4 可写运行根播种、命令拼装），与本条"入口不复述解析逻辑"**不符**。已把参数拼装全部交回本模块
（`merge_air_params` / `write_air_params` / `px4_paths` / `require_toolchain` / `px4_cmd` /
`seed_px4_run_root` / `spawn_args`），入口只剩 `_resolve` → `_compose_lightweight` / `_compose_full`
→ `_air_and_task_actions` 的**编排**（`_compose` 6 行，最大函数 144 行）。这是**对齐既有决策**，
不是新决策；两个 backend 的起法行为不变（实测同达 `TRACKING_SUCCESS`、manifest 字段集合同为 14 键）。

`BACKENDS` 能力表为每 backend 声明 `air_link` / `px4` / `target_source` / `required_nodes`（完整展开
节点）/ `supported_axes`；`not_carried` 状态由能力表**派生**（`entry.requires_air_link and not
BACKENDS[backend].air_link`），**不再**逐文件硬编码「轻量栈无空中链路」。

| backend | air_link / px4 | target_source | 支持轴 |
|---|---|---|---|
| `lightweight` | `false` / `false` | `gt_adapter` | 仅 `obstacle` / `outcome` |
| `full` | `true` / `true` | `gt_adapter` ⚠ | 全部 4 轴（含空中链路 4 节点与 `intruder_driver`） |

> ⚠ **2026-11-04 修正**：原表 `full` 行的 `target_source` 写作 `air_fusion`，该节点已退役
> （[ADR-0009](0009-perception-truth-derived-and-vision-path.md#top) (b)），两 backend 现均为 `gt_adapter`。
> 同时 `air_perception` 的 `/agc/air/obs` **无订阅者**，故 `perception` 轴在运行期**不再有区分力**。
> **2026-11-06 续**：该节点连同 `perception` 场景轴、传感器通道文件与 `s17`（`no_target` 负例）
> 已整体删除（台账见 [路线分支治理](../../docs/conventions/路线分支治理.md#rule)）；
> 本条保留为"该轴为何没有区分力"的记录（见 [ADR-0018](0018-acceptance-and-coverage-matrix.md#top) (g)）。

### (e) 入口名 == 报告身份
manifest 记 `launch='main.launch.py'` + 实际 `backend` + `nodes`（完整展开节点名）+ 生效参数（`scene` /
`seed` / `support_status` / `declared_axes` / `expected_terminal` / `expected_reason` / `carriers` /
`effective_params` / `assertions`）；runner / probe 报告的 `launch` 字段同步为 `main.launch.py`。
临时参数 / manifest 文件名含 backend 与唯一性（`w6_<backend>_<scene>_<seed>.yaml` /
`w6_<backend>_manifest_<scene>_<seed>.json`）。

### (f) 就绪依赖替代盲计时
`intruder_driver` 由 **`OnProcessStart(target_action=<入侵者 PX4 ExecuteProcess>)`** 事件驱动（其自身
已有就绪门控：无 odom 先 no-op），**移除** 35 s `TimerAction`。

> **2026-11-10 续（[ADR-0038](0038-startup-readiness-gates.md#top)）**：本条原先保留的「己方 / 入侵者
> PX4 用 `TimerAction` 计时、本层无可达就绪信号」**已不成立**——当时认为不可达的就绪信号，实际上
> 由 gz `create` 服务发现、`scene/info` 实体存在、世界时钟推进、`/agc/air/odom` 新鲜这几类
> **可查询事实**给出。车/目标的 15 s spawn 定时器、PX4 的 25/35 s、`air_bringup` 的 12 s 与
> `scenario_reset` 的 4 s 初始复位**全部**改为就绪门驱动；固定秒数此后只作**上界**（超时即显式失败）
> 与**可选下限**（默认 0）。判据与实现见 ADR-0038。

### (g) 命名空间与坐标系

<a id="namespace"></a>

- 协同层统一命名空间 `/agc/`。
- **坐标系基准**：`agc_world`（Gazebo world，ENU：+x 东、+y 北、+z 上；位置 m、速度 m/s、角度 rad）为唯一基准。
- **机体系命名固定**：`drone/base_link`、`car/base_link`，**禁止裸 `base_link`**。
  > PX4 SITL 会一次性发布 `map` / `odom` / `base_link_frd` 等历史静态帧；协同层不发布裸 `base_link`。
- 含 Header 的协同位置/速度/地图/路径/状态消息 `frame_id=world` 或 Gazebo `world`；
  `/agc/ground/cmd_vel` 用车体系 `TwistStamped`。

### (h) 唯一执行口

<a id="execution-port"></a>

- **地面唯一执行口**：`/agc/ground/cmd_vel`；**唯一**命令车体运动的通道为地面执行中继
  （原 `ground_drive_adapter`），任何其它节点**不得**命令车体运动。车体位姿由 GZ Sim 物理引擎产生；
  **唯一例外**为场景复位的位姿写入（受运行期门控，见 [ADR-0014](0014-task-fsm-and-scenario-transaction.md#top)）。
- **空中控制权**：起飞阶段归起飞控制器（原 `drone_launch_controller`）；`release_control` 后由
  LQR 轨迹跟踪节点接管（见 [ADR-0010](0010-safety-thresholds-and-failsafe.md#top) (h) 的控制许可）。

### (i) 参数入口

<a id="params"></a>

由 launch **单一设置**，节点**不得覆写**：

`/agc/target/source`、`/agc/obstacles/source`、`/agc/air/takeoff_altitude_m`、`/agc/air/follow/*`、
`/agc/scenario/dynamic_obstacles`、`/agc/world_file`、`/agc/log/seed`

> `/agc/perception/sensors_file` 已于 **2026-11-06** 随 `perception` 场景轴与 `air_perception`
> 节点退役（用户裁定）：该参数原指向的 4 个 `perception_sensors*.yaml` 通道变体无消费者、
> 运行期行为完全相同，已整体删除。不再保留该参数入口；量程 R=30.0 的推导登记处
> 改为 `air.yaml` 的 `standoff_follower` 注释与[飞行高度规范 K1](../conventions/飞行高度分层与按地图定高.md#where)。

目标源选择（`/agc/target/source`）：`/agc/targets` 的**唯一发布者**恒为 `gt_adapter`，详见
[ADR-0009](0009-perception-truth-derived-and-vision-path.md#top)。

### (j) 消息与服务

<a id="messages"></a>

协同层消息（`air_ground_core`，迁移后独立为 `agc_msgs`）共 9 个，**字段与顺序不得变更**：

`AgcTaskState`、`AirObservationArray`、`ObstacleObservation`、`ObstacleTrack`、`ObstacleTrackArray`、
`SensorObservation`、`TargetObservation`、`TargetTrack`、`TargetTrackArray`

> 其余包的消息/服务清单见 [归档的 ROS1 基线盘点](../archive/ros1-baseline.md#appendix-a-archived)（A.4）。
> 迁移后**接口语义不得变更**。

<a id="empty-array-semantics"></a>

**数组消息的空数组语义**：`TargetTrackArray` 的空数组 = 「本拍无新观测」，不是「目标消失」。
消费者（`standoff_follower` / `trajectory_tracker` / `task_manager` / `capture_adjudicator`）
**SHALL** 保持上一有效航迹不动，由**年龄**判定失效——即硬约束「过期即冻结」（见 (k) 第 10 条）。
判定口径与四个消费者的误判后果见 [ADR-0017](0017-time-budget-and-clock-sources.md#top) (g)。

### (k) 硬约束（逐条复验）

<a id="hard-constraints"></a>

<a id="hc-1"></a>
1. 8 字轨迹为**真八字**（Gerono，`rx=15` / `ry=9` / `h=2.5 m`），全程恒速、无加减速（线速度 `v=2.0 m/s`，弧长参数化）。
<a id="hc-2"></a>
2. 距离阈值顺序必须满足 紧急 < 碰撞 < 安全。**顺序为不变量**；**绝对值为可标定量**，由地面安全层按 [ADR-0010](0010-safety-thresholds-and-failsafe.md#top) 的 Nav2 时间窗口径、以实测动力学标定为 `1.0 < 2.0 < 4.0 m`（ADR-0010 已实测回填；旧值 `0.7/0.9/2.4 m` **作废**）。
<a id="hc-3"></a>
3. 实证 / 验收**定性、关键场景**使用**非无头（GUI）**并留记录；**规模数值统计**允许 **headless**，但**须经 GUI ↔ headless 等价核验**（同参数 / 同 seed、关键指标一致），且产物**如实标注** `backend` / `mode`；默认仍无头以向后兼容（[ADR-0018](0018-acceptance-and-coverage-matrix.md#top)）。
<a id="hc-4"></a>
4. 训练与评估成功定义统一：**超时一律算失败**，只有显式完成才算成功。
<a id="hc-5"></a>
5. 每个 episode 起始必须把轨迹相位复位到 t=0。
<a id="hc-6"></a>
6. 安全滤波器参数须用**真实逃逸能力**（如 `lateral_speed = min(max_offset_xy, max_offset_change/dt)`）。
<a id="hc-7"></a>
7. 场景生成须保证**出生净空 ≥ 可标定下限**（按安全档 + 实体外伸推导，见 [ADR-0012](0012-spawn-clearance-and-reset-transaction.md#top)；旧值 `2.4 m` **作废**）；复位失败最多重试 3 次且不占 episode 预算。
<a id="hc-8"></a>
8. 状态机终态为"抵近并持续跟踪"，`SUCCESS` **不得**表述为"拦截完成"。
<a id="hc-9"></a>
9. 评估报告须含 `shield_infeasible_rate` 与 `reset_failure_rate`。
<a id="hc-10"></a>
10. **无人机对目标的跟踪常开**（非可选；原"跟随默认关闭"作废）：保持**安全间距**（不紧贴），目的为**不丢失目标**；跟踪要求目标新鲜（`ref_max_age_s=0.5`）且 `confidence≥0.5`，过期即冻结。无人机同时负责**自身飞行安全**（自避障）。

> **回归挂载**：每条约束挂到"首次使其可验证"的 workstream，映射表见归档 Runbook 的
> [硬约束挂载表](../archive/ROS2迁移步骤.md#hard-constraint-mounting)（历史编排记录，非约束）。

### (l) 不可回退教训

<a id="lessons"></a>

- **已知竞态（必须在 ROS2 版修复）**：`/agc/task/start` 门禁先校验 odom 再调 `/agc/scenario/reset`，
  导致 `odom_valid` 被无条件置 false、`evaluate()` 读到 `ODOM_INVALID`。**必须改为 reset 后再校验。**
- **已修复教训（必须保留门控）**：非运行期写车体位姿会覆盖 `car_start`，必须用 `/agc/task/state`
  运行期门控。

## 不做什么（边界）
- **不**允许任意包互依赖（无类别区分即退化为无架构）。
- **不**把 `agc_air_lib` 升格为公共库、**不**为修 export 新建跨域链接。
- **不**引入 `bt_navigator` / 行为树；**不**新增第二 ROS 命令者。
- **不**在 `launch` 内自造阻塞式「等话题 / 服务」动作（`launch_ros` 无内置能力，且在 launch 里
  阻塞会卡住整个事件循环）。**就绪判定一律在独立子进程里做**，结论经**退出码 / 事件**回传
  （见 [ADR-0038](0038-startup-readiness-gates.md#top)）——这不违反本条，反而正是它的落点。
- **不**把 `backend` 只作顶层变量而不落能力表（否则覆盖状态退回逐文件硬编码）。
- **不**改冻结 9 消息 / 服务 ABI、唯一执行口语义、硬约束–。

## Considered Options
- **全域 Python / 全域 C++** —— 被否：前者点云处理与安全层实时性 / 吞吐不足，后者 RL 生态在 Python、
  重写代价高。
- **维持单一依赖规则（「唯一公共依赖」）** —— 被否：与真实运行拓扑不符，会误禁必要运行依赖或催生
  隐藏依赖。
- **只按 build / exec / test 三分** —— 被否：不解释「起进程 vs 链接库」的本质差异。
- **保留多入口、仅各自抽共享 helper** —— 被否：仍有第二份入口组装与 `backend` 身份分叉。
- **继续用绝对时间承载 `intruder_driver`** —— 被否：该依赖有**可达就绪信号**，盲计时引入不必要的
  时序脆弱。

## Consequences
- **正面**：语言选型有据可依；依赖方向图区分「链接」与「运行组合」，真实运行依赖不再被隐藏；
  导出承诺与安装产物一致；拓扑成为单一可审查实体，`backend` 贯穿身份与报告，`intruder_driver`
  随实际就绪启动（不早于入侵者 PX4 ≈25 s，与旧 35 s 相比**不晚**）。
- **代价 / 限制**：`lightweight` / `full` 除入口名 / 身份 / 就绪改动外**等价**；gz 引擎 spawn 段
  已于 2026-11-10 改由就绪门承载（[ADR-0038](0038-startup-readiness-gates.md#top)），不再是计时；引用旧入口名的脚本与核查器（`scripts/run_w6_*.sh` /
  `episode_runner.py` / `w6_r0*_check.py` / `w6_r025_full_probe.py` / `check_full_chain_dual_px4.py`）与 config
  注释须同步更新。
- **未决**：① `intruder_driver` / `jammer` 是否应归入独立「设备域」—— 本轮**不**迁移，后续若迁按
  ③关系调整 `exec_depend`、**不**引入库链接；② gz 引擎 spawn 段**已**回归就绪依赖（ADR-0038）；③ `intruder_driver` 事件驱动的实跑时序以整链实跑证据复核。

## 参考
- [ADR-0003](0003-nav2-paradigm-absorption.md#top)（Nav2 范式吸收：模式全覆盖、按命令源裁剪）
- [ADR-0004](0004-ground-control-rl-primary-and-nav2-safety.md#top)（共享控制库 `agc_control`）
- [ADR-0019](0019-lifecycle-and-startup-robustness.md#top)（生命周期可重建与启动健壮性）
- [ADR-0021](0021-gui-headless-equivalence.md#top)（backend 与 GUI / headless 等价）
- 规范真源：[包边界](../conventions/包边界.md)、[目录与命名规范](../conventions/目录与命名规范.md#10-产物分类与生命周期)
