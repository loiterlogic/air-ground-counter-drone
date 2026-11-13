<a id="top"></a>
# 启动就绪门：以可观测判据替代固定秒数

## Status

accepted（2026-11-10，用户裁定「完全按这个文件进行修复」并指定 `temp.md` 的审查结论为实施依据）

**修订**：[ADR-0020](0020-package-boundaries-and-runtime-topology.md#top) 的 (f) 与 Consequences
（"gz 引擎 spawn 段仍是计时而非就绪信号"、"不把启动依赖全部改成就绪等待"两处**已不成立**）；
[ADR-0027](0027-uxrce-startup-reproducibility.md#top) (d)(e)(f) 的**实现手段**（错峰改由事件承载，
结论"两个 uXRCE 参与者不得并发创建"不变）；[ADR-0019](0019-lifecycle-and-startup-robustness.md#top)
的预热定位（降级为可选优化，不再是启动正确性前提）。

**相关**：[ADR-0012](0012-spawn-clearance-and-reset-transaction.md#top)（复位事务与读回）、
[ADR-0014](0014-task-fsm-and-scenario-transaction.md#top)（受控复位事务）、
[ADR-0021](0021-gui-headless-equivalence.md#top)（GUI / headless 同一就绪语义）。

## 背景

用户报告："地图加载一会儿后车和目标才出现；之后又过一段时间我方无人机才出现。"

静态审查（`temp.md`）与本次实测确认根因不是"某个秒数不合理"，而是**启动编排整体用固定秒数
代替就绪判据**：

| 位置 | 旧行为 | 后果 |
|---|---|---|
| `world_bringup.launch.py` | `TimerAction(15.0)` 创建车/目标 | 世界 2 s 就绪则白等 13 s；20 s 才就绪则 spawn **失败且无人重试** |
| `main.launch.py` | 己方 PX4 固定 25 s | 与"世界/实体/Agent 是否就绪"无关 |
| `main.launch.py` | 入侵者 PX4 固定 35 s | 与"目标模型是否存在、能否 attach"无关 |
| `air_bringup.launch.py` | 另一套 12 s | 同一 PX4、同一世界，**两个入口两套语义** |
| `scenario_reset.cpp` | 第 4 s 一次性初始复位 | 实体 15 s 才创建 → 复位必然失败 → 定时器已 cancel → **永不重试**，任务层对着"从未复位过"的场景启动 |

`launch` 的动作**注册顺序不等于就绪顺序**：`LaunchDescription` 里 `IncludeLaunchDescription(world)`
写在 `ExecuteProcess(agent)` 之前，表达的只是"先注册这两个动作"，不是"世界就绪后才起 agent"。
当时的实际依赖全压在三串秒数、预热脚本退出、以及各节点内部自行等待上。

更根本的是：**这些秒数在语义上互相污染**。`own_px4_delay_s=25` 同时承担了三件事——
等 gz 世界起来、等 uXRCE 发现图稳定、与入侵者错峰；改小任一项都会破坏另外两项，
于是没人敢动，而机器一换（更慢 / 更快 / 更多 DDS 段）行为就变。

## 决策

<a id="principle"></a>
### (a) 原则：启动依赖只允许由**可观测事实**承载

每个启动阶段必须能回答"它凭什么算就绪"，且答案是**可以查询的事实**，不是"过了 N 秒"。
允许的事实只有五类：

1. **gz 服务被发现**（`create` / `set_pose` 等已在网络上注册）；
2. **gz 实体存在**（`/world/<w>/scene/info` 里出现该模型名）；
3. **世界时钟推进**（`/world/<w>/clock` 连续帧 sim 时间严格增大——排除"暂停的世界"）；
4. **ROS 话题新鲜**（该话题在墙钟窗口内收到过消息）；
5. **ROS 发现图稳定**（节点集合 ≥ N 且连续若干秒不再变化）；
6. **lifecycle / 复位事务的结论**（`get_state` 可发现、复位读回成功）。

固定秒数此后**只允许**作为两种角色，且都不得承载正确性：

* **上界（timeout）**——"愿意等多久"，超时即**显式失败**；
* **可选下限（floor）**——人工加保险，默认 0。

<a id="spawn"></a>
### (b) 实体创建改为**事务式**（`scene_spawn_gate`）

```
create 服务被发现
  → 世界时钟推进（≥2 帧且严格增大）
  → 创建 agc_car        → 校验 scene/info 出现
  → 创建 intruder_uav   → 校验 scene/info 出现
  → 发布 /agc/sim/entities_ready = true（latched）
  → 退出码 0
```

失败路径：任一步超时 / 被拒 → 发布 `false` + **非零退出**。
`allow_renaming=False` 是**语义要求**而非偏好：允许改名时"创建成功"与"我们看到的那个实体"
会分叉，事务就不再可判定。

为什么直接走 gz-transport 而不调 `ros_gz_sim create` 子进程：需要的事实是**服务应答**与
**实体存在**；子进程退出码只说明"它自己退出了"。实测 `ros_gz_sim create` 在服务不可用时
会无限重试打印 `Waiting for service … to become available ...`，无法作为就绪判据。

<a id="px4"></a>
### (c) PX4 启动由事件链承载，两个 uXRCE 参与者**永不并发**

```
/agc/sim/entities_ready（实体已确认存在）
  → 启动己方 PX4
  → 等 /agc/air/odom 新鲜（= 己方参与者已建立、EKF 在发数据）
  → 启动入侵者 PX4（attach 已存在的 intruder_uav）
```

ADR-0027 用 25/35 s 错峰规避的**真实约束**（两个参与者并发创建会让 agent 侧创建落入长尾，
PX4 侧 1 s 硬预算超时 → `create entities failed: participant: 255`）**不变**，只是表达方式
从"错开 10 秒"变成"等前者真的开始发数据"。这条因果链比时间差更准确：它保证的是
**先后**，而不是"大概错开了"。

<a id="graph-stable"></a>
#### (c-1) 实测更正：`own_px4_delay_s=25` 还藏着**第二个**约束

首轮改造把己方 PX4 的就绪门写成"实体存在 + create 服务可用"后，实测（2026-11-10）立刻
复现了旧故障：

```
[startup_gate +12.91s] px4_own_gate：就绪      ← 实体就绪后立刻放行
[px4] INFO  [uxrce_dds_client] init UDP agent IP:127.0.0.1, port:8888
[px4] ERROR [uxrce_dds_client] create entities failed: participant: 255
```

**实体就绪 ≠ 可以起 PX4。** 整链启动时十几个节点 + 两个 uXRCE Agent 同时上线，DDS 发现图在
头几十秒持续变动；此时创建 participant 会撞上发现风暴，agent 侧 `establish_session` 落入长尾，
PX4 侧 1 s 硬预算超时。旧代码的 25 s 恰好把这个窗口躲开了——**它保护的不是"gz 是否起来"，
而是"发现图是否已平息"**。

因此新增第 5 类判据 `graph-stable:<hold_s>:<min_nodes>`：节点数 ≥ `min_nodes` 且连续
`hold_s` 秒**不再变化**才算就绪。实测该门在 `+41.6s` 通过（此前图在 26↔27 节点间抖动），
之后 PX4 一次成功（`successfully created rt/fmu/out/vehicle_odometry data writer`），
两个实例都 `Armed by external command`，空中 lifecycle 四个节点全部 configure 成功。

这条判据取代的是"25 秒"这个**数字**，不是它所保护的**事实**——事实现在可观测了。

<a id="deadlock"></a>
#### (c-2) 实测更正二：就绪门**不得等它自己所门控的链**

首轮改造后实跑暴露一个**循环等待**，代价是每次启动白等 150 s、任务必然 `air_hover_timeout`：

```
air_lifecycle_gate  等 /agc/air/odom 新鲜
  ↳ 但 /agc/air/odom 由 px4_adapter 在 on_activate 之后才发布
    ↳ 而 activate 由 lifecycle_manager 执行
      ↳ 而 manager 排在该门之后启动   ⇒ 循环，必然超时
```

`px4_intruder_gate` 犯同一个错（等 `/agc/air/odom`，而它控制的正是"入侵者 PX4 何时起"）。

**规则**：门的判据必须来自**该门上游**——不能是本门所门控的那条链的产出。
两条门都改用 `/fmu/out/vehicle_odometry`：那是 PX4 经 uXRCE **直发**的话题，不经过任何
lifecycle 节点，因此是"own 参与者已建立且 EKF 在发数据"的**最短可达**证据。
lifecycle 服务本身**不**在门里等——manager 自己会 `wait_for_service`（Nav2 范式），
等不到就是它该报的错，不该由门代为判定。

<a id="qos"></a>
#### (c-3) 实测更正三：探针 QoS 必须取**最弱**

改用 `/fmu/out/vehicle_odometry` 后仍然等不到。原因不是话题不存在（`ros2 topic list` 有、
`Publisher count: 1`），而是 **QoS 不兼容**：

| 发布者 | 订阅者（探针默认） | 结果 |
|---|---|---|
| BEST_EFFORT + TRANSIENT_LOCAL（PX4 uXRCE） | RELIABLE + VOLATILE | **静默收不到** |

ROS 2 的兼容规则是「订阅者不得比发布者**更强**」。`create_subscription` 照样成功、不报错、
不告警——这正是本仓在 `intruder_driver` 上踩过的同一个坑（当时是 durability 漏了
`TRANSIENT_LOCAL`）。探针只需要"有没有消息"，故取**最弱**组合 BEST_EFFORT + VOLATILE，
同时兼容 PX4 与普通节点两类发布者。

修复后实测：`/agc/air/odom` 以 **99.9 Hz** 发布，四个空中节点全部 Activate，两架 PX4 均 Armed。

`own_px4_delay_s` / `intruder_px4_delay_s` 保留为**可选下限**（默认 **0**），仅供极端负载下人工加保险。

<a id="reset"></a>
### (d) 初始复位绑定实体就绪，失败**有界重试**并显式上报

`scenario_reset` 的启动定时器从"4 s 一次性"改为**周期重试直到成功或超限**：

* 每拍仍走**同一门控**（`doReset` 内的 gt 新鲜 / set_pose / 读回校验，不 bypass）；
* 成功 → 发布 `/agc/scenario/ready=true`（latched），取消定时器；
* 超过 `startup_reset_max_attempts` 或 `startup_reset_timeout_s` → 发布 `false` + `RCLCPP_ERROR`
  （"场景未就绪，任务层不得假装正常启动"）；
* 重试窗口内的失败是**正常**状态（实体 / GT 尚未就绪），按 3 s 节流打印，不刷屏。

`task_manager` 的 `/agc/task/start` 事务**先等** `/agc/scenario/ready`：
未就绪（无状态 / false）一律如实拒绝，理由 `scenario_not_ready`。
空话题名 = 不等待，仅用于把 `task_manager` 单独起起来的台架与单测。

<a id="lifecycle"></a>
### (e) prewarm 降级为**可选性能优化**

`air_lifecycle_prewarm` 只证明"lifecycle 服务能被调用到"，**不证明** PX4 就绪 / 模型存在 /
odom 新鲜 / 能进 ACTIVE。旧链路把它当成 `lifecycle_manager` 的**唯一启动条件**（单事件依赖），
于是"prewarm 退出"被误当作"空中链路就绪"。

现在 manager 的启动由**真实信号**决定：`/agc/air/odom` 新鲜 + 被管节点的 `get_state` 服务可发现。
prewarm 仍先跑（暖连接），但**不再**是正确性前提——它失败、超时、甚至不跑，都不影响启动判定。

<a id="entry"></a>
### (f) 两个入口共用同一套就绪语义

`air_bringup.launch.py` 的 12 s `TimerAction` 删除，改用与 `main.launch.py` **同一个**
`startup_gate` 与同一条 `entities_ready` 判据。就绪门脚本装在 **`agc_sim`**（两个入口都已依赖它），
**不**装在 `agc_task`：`agc_air` 依赖 `agc_task` 会形成 `agc_task → agc_air → agc_task` 的环，
违反 [ADR-0020](0020-package-boundaries-and-runtime-topology.md#top) 的包边界。

<a id="time"></a>
### (g) 时间语义：启动用墙钟，任务用仿真时间

* **启动阶段**（进程 / 服务 / 实体 / 话题是否就绪）：一律**墙钟**。启动期 `/clock` 可能尚未出现，
  用仿真时间会让判据在时钟起步前恒假（死等）。
* **仿真任务阶段**（状态新鲜度 / 任务预算）：一律**仿真时间**（`use_sim_time=true`）。
* 同一定时器**不得**同时承担这两类职责。`scenario_reset` 的重试节流用 `RCLCPP_INFO_THROTTLE`
  配节点时钟（仿真时间），而重试的**墙钟上界**用 `steady_clock` —— 两者分工明确。

<a id="visible"></a>
### (h) 启动状态可观测

新增两个 latched 状态话题，让"哪一段还没就绪"可被外部（`run_demo` / 排障）直接读到，
而不是从日志里反推：

| 话题 | 发布者 | 含义 |
|---|---|---|
| `/agc/sim/entities_ready` | `scene_spawn_gate` | 车与目标已创建**并确认存在** |
| `/agc/scenario/ready` | `scenario_reset` | 初始复位事务成功（含 GT 读回） |

两者都**成功与失败都发布**（只发 true 会让下游永远等不到结论）。

## 不做什么

- **不**新增路线分支：不加 `xxx_source` / `xxx_mode` 开关，不提供"计时派 / 就绪派"二选一。
- **不**改契约硬约束、坐标系、终态语义、冻结消息 ABI（新状态用 `std_msgs/Bool`）。
- **不**改 PX4 工具链、failsafe 锁定、目标模型与轨迹、安全阈值。
- **不**把节点内已有门禁（`task_manager` 五门、dwell 判据）改成 sleep —— 那些是**判据**，不是等待。
- **不**删除 `own_px4_delay_s` / `intruder_px4_delay_s` / `px4_warmup`：它们是 A/B 与极端负载回退口，
  只是不再是正确性前提（默认值改为 0 / false）。
- **不**在 `launch` 里自造"等话题"动作：`launch_ros` 无内置能力，且强行在 launch 内阻塞会卡住
  整个 launch 事件循环（其它动作全部停摆）。就绪判定一律在**独立子进程**里做。

## Consequences

**正面**

- 快机器上不再白等：实测车/目标在 **+4.8 s** 就被创建（原实现固定等满 15 s），
  整段事务（含存在校验）在 **+22 s** 内完成。
- 己方 PX4 在 **+41.6 s** 放行（图稳定后立刻起），且**不再**出现
  `create entities failed: participant: 255` —— 旧 25 s 所保护的事实被显式判据接管。
- 慢机器上不再静默失败：spawn / 复位失败会**大声报**并给出未就绪项，而不是让任务层对着空气跑。
- 两个入口行为一致，"同一 PX4 在 `air_bringup` 里 12 s、在 `main` 里 25 s"的矛盾消失。
- 每段等待都有名字（`px4_own_gate` / `px4_intruder_gate` / `air_lifecycle_gate` / `scene_spawn_gate`），
  日志里能直接看出卡在哪一段。
- 启动失败与任务失败可区分：启动期是"没就绪"，任务期才是"没做到"。

**代价 / 限制**

- 多了一个 gz-transport 依赖面（Python `gz.transport13` / `gz.msgs10`）。已在 `agc_sim` 的
  `package.xml` 声明；缺失时 `startup_gate` 的 `entity:` / `gzservice:` 判据恒未就绪并**打印原因**
  （不会静默通过）。
- 就绪门是**独立进程**，每次启动多 2–3 个短命进程；换来的是判定不阻塞 launch 事件循环。
- `scene_spawn_gate` 直接调 `create` 服务，不再经过 `ros_gz_sim create`；两者行为等价（同一服务），
  但**取证脚本**若依赖 `create` 子进程的输出行，需改看 `scene_spawn_gate` 的日志。
- 世界时钟推进判据假设世界以 `-r` 启动（未暂停）。以暂停态启动的世界会**显式超时失败**，
  而不是"创建成功但实体不动"——这是有意的：后者是更坏的静默失败。

**未决**

- 目标机"真正起飞"（ARM / 离地）仍由 `target_takeoff_guard` 以 150 s 上界观察，未纳入本状态机。
  它是**任务级**就绪（依赖 PX4 EKF 收敛与 driver 首帧），与启动级就绪是两件事，分开登记更清楚。
- `run_demo` 的就绪门仍以"话题新鲜"聚合（`start_service` / `gt_*_fresh` / `cmd_vel_fresh` /
  `air_odom_fresh`）。它可以进一步消费 `/agc/sim/entities_ready` 与 `/agc/scenario/ready`
  来**提前**报出"卡在哪一段"，但那是呈现层改造，不在本次范围。

- **已实施的监督层收口**：`run_demo` 将启动阶段写成统一的 `[boot stage=… state=… elapsed_s=… retries=… reason=…]` 事件；监督器在 `ros2 launch` leader 提前退出时立即结束就绪等待，记录原始退出码、未就绪项与最近 launch 日志，避免把 world/spawn/PX4 的真实失败掩盖成整链超时。该监督层仍只消费既有服务、话题与启动进程状态，不改变任务入口或终态语义。


- 同版本可运行实现的边界对照：`refs/ego-planner-swarm-ros2` 的 `run_in_sim.launch.py`
  （launch 只组装组件，连接由 topic / service 建立）、`refs/crazyswarm2` 的 `launch.py`
  （配置解析与动作构造分离、条件用显式 `IfCondition`）——**都不是**用经验秒数模拟依赖。
- Nav2 `nav2_lifecycle_manager`：以 `wait_for_service` + 状态查询承载"被管节点是否就绪"，
  而非固定 sleep（本仓 `lifecycle_manager_air` 沿用该范式，本次只是补上**它之前**那一段）。
