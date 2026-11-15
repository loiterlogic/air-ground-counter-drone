<a id="top"></a>
# 地面规划：基线路径、重规划策略与外部规划器契约

## Status

accepted（2026-11-02 由 ADR-0027 / 0056 / 0089 / 0092 / 0108 / 0109 合并；路径绑定、重规划触发口径与外部规划器契约的结论均未变，四项外部对接未决仍挂起）；
**补充 by [ADR-0035](0035-perception-map-representation-and-unknown-policy.md#top)（2026-11-09，非取代）**；
**部分补充 by [ADR-0047](0047-directional-safety-tier-semantics.md#top)（2026-11-13）**；
**占位实现已被 [ADR-0048](0048-ground-hybrid-astar-se2-planner.md#top) 替换（2026-11-14）**：
(l) 的 `placeholder_path_planner` 退役，由 `hybrid_astar_se2_planner`（Hybrid A* on SE(2)）接替；
路径契约（话题 / 类型 / `frame_id` / 质量门 / 绑定语义）**不变**。
(l) 的占位规划器**形态不变**（仍是几何直连）—— ADR-0047 只改**安全层**的定档口径。
「在规划层栅格上选间隙」曾在本篇的占位器里试做，**已回退**：全局路径规划属主链任务
（[ADR-0032](0032-pending-directions.md#top) 方向 2），不在占位器里实现（见 ADR-0047 的 Considered Options）

> 本篇 (b) 的地图签名口径（只计 `static_layer` 的 `cost == 254`）**仍然有效**：
> `/agc/map` 现在输出 1–99 的量化概率，但 `static_layer` 按自己的阈值判 lethal，
> 签名只看 `== 254`，**不受影响**。
> "未知空间不可走 + 目标在未知区走直连兜底"由 ADR-0035 (g) 承载
> （落点是 `planning_policy.hpp` 的端点判定，**不**用 Navfn 的私有 `allow_unknown`）。

## 背景

地面侧有两条并存的路径来源：离线对照基线 `ground_baseline`（Nav2 `navfn` 插件 + 自持 costmap + LQR 跟随）与
`command_source=rl` 下由外部独立节点提供的占位规划器；两者共用同一消费接口 `/agc/ground/path`。历史上有三类病灶：① 规划失败只打 warning、不清旧 `path_`，车辆继续驶向旧目标 / 旧通道；② 目标失联时仍发新
时间戳的固定点 goal，把"失联"伪装成"本时刻仍有有效目标"；③ 地图签名把未知格 / 膨胀环 / 移动目标的传感器层
marking 都算作"地图变化"，每回合二十余次伪触发重规划。三者共同后果是**"路径还对不对"无法从产物判定**——
本 ADR 定的就是判定口径本身。

## 决策

### (a) 路径绑定三元组与重规划触发顺序

每次**成功**规划记录绑定三元组，仅在绑定仍有效时继续使用既有路径：**目标身份**（规划时刻 goal，`last_plan_goal_`；
当前 goal 位移 > `replan_displacement_m` → 目标变）、**地图签名**（`last_plan_map_sig_`，见 (b)；不等 → 地图变）、
**有效时限**（`max_path_age_s`；超时 → 强制重规划）。`needReplan` 判定顺序固定为 **目标变 → 地图变 → 超时 → 周期
`replan_period_s`**，任一失效即立即重规划，并受 `kReplanGuardS = 0.2 s` 限流防止同 tick 抖动；无变化时仅按周期刷新。

### (b) 地图签名口径：只计 `static_layer` 的 `LETHAL_OBSTACLE`

签名 = 对 `static_layer` 自身的**尺寸 + 原点 + `cost == 254`（`LETHAL_OBSTACLE`）栅格索引**做 **FNV-1a 64 位**哈希。

- 判据必须 `== 254`：`NO_INFORMATION=255`（未知格翻转）与 `INSCRIBED_INFLATED_OBSTACLE=253`（inflation 内切环）
  语义互不相同，计进去就是伪触发。
- 只读 `static_layer`：obstacle / voxel 层对**移动目标**的 lethal marking 迁移属动态内容，不参与"地图变化"；动态
  障碍仍由规划器在**下一拍周期规划**消费，并在控制 / 安全层即时生效。
- `static_layer` 尚不可用（地图未到 / 尺寸为 0）时回退 master `Costmap2D` 并标 `signature_from_static=false`，可用
  后自动切回；`mapSigInfo` 记 `sig_hard_cells` / `signature_from_static`，保留 `hard_cells` / `layers` 供审计。

### (c) 规划失败 → 失效停车（fail-stop）

`plan` 返回空路径或抛异常时置 `path_valid_ = false` 并记失效日志；`tick` 对失效路径**默认发布零速**，**不再**
`lookaheadRef` 旧路径。既有参数 `stop_on_invalid`（默认 `true`）接线生效；置 `false` 是**显式 opt-out**（回落到旧
路径，仅用于对照实验，默认配置不启用）。先学后做（取证）：本机 Jazzy `NavfnPlanner::createPlan` 在目标不可达 /
出界 / 全被占时 **throw `nav2_core::PlannerException`**，故"目标不可达"实际落在 `catch` 异常分支；`poses.size < 2`
分支是对"返回空而不抛"的其它 planner 的防御分支。

### (d) 目标失效策略：有期限保留最后有效目标（bounded hold-last-valid）

评审风险 **r-041**（目标失效与重规划抖动）的两处病灶即背景 ②③。三选一（立即安全停车 / 保留有期限的最后有效
目标 / 受限搜索）中选**保留有期限的最后有效目标**，窗口 `goal_hold_valid_s`（default 1.0 s）：

- 窗口内：位置 = 最后有效位置、`stamp` = **最后源时刻**（`age` 自然增长）、`valid=true reason=HOLD_LAST_VALID`；
  **不**反射固定点、**不**刷新 stamp。
- 超窗：**显式失效** `valid=false reason=EXPIRED`（从未有效则 `TARGET_LOST`），**不发布**带新时间戳的 goal 位姿。
- `goal_follow_target=false`：固定任务目标恒有效，`valid=true reason=FIXED_GOAL`、`stamp=now`。
- `goal_follow_target=true` 且 `targetFresh`：位置 = 目标 XY、`stamp=`**目标源时刻**（非 `now`）、关联
  `target_id`、`valid=true reason=TARGET_FRESH`，并刷新"最后有效目标"缓存。
- `/agc/task/start` 新 episode **清空**最后有效目标缓存（与既有 episode 隔离一致）。

### (e) 目标身份 / 有效性 / 时刻的带外伴随诊断

`/agc/ground/goal_info`（`std_msgs/String`，**transient_local**，非命令者）承载
`valid=<0|1>;reason=<...>;target_id=<id>;src_stamp=<double 秒>;age=<double 秒>`。`/agc/ground/goal` 仍是
`geometry_msgs/PoseStamped`（`frame_id=world`、`orientation.w=1.0`），类型与语义**冻结**—— 这是"不改冻结接口"的
边界。参数 `goal_hold_valid_s`、`goal_info_topic` 由 launch / config 单一注入。

### (f) 重规划位移阈值化：移除任意浮点强制重规划

**移除** goal 回调里的 `hypot(...) > 1e-6 → force_replan_ = true`；改为始终更新目标坐标，**仅首次**获得 goal
（`!have_goal_`，合法实质绑定）时置 `force_replan_ = true`，后续重规划完全交给 (a) 的判据。依据（同版本 Nav2
惯例）：目标变化以**离散事件**触发重规划（`GoalUpdatedController` / `GoalUpdatedCondition`），位移比较用**阈值化
L2 距离容差**（`xy_goal_tolerance` / `euclidean_distance`）而非任意浮点相等，时限 / 有效性另行参与判据
（`PathExpiringTimerCondition` / `IsPathValidCondition`）。

### (g) 地面失效动作与空中 `freeze` 分别定义

- **地面 = 安全停车**：`ground_baseline` 消费 `/agc/ground/goal_info` 的 `valid=`；`valid=false` 时在 `tick` 顶部
  （`!active_` 检查之后）`publish(0,0); return;`，先于路径跟随 / 重规划。默认 `goal_valid_=true`，无该话题的旧运行
  保持既有行为。
- **空中 = freeze**：[硬约束 hc-10](0020-package-boundaries-and-runtime-topology.md#hc-10) 的 standoff 跟踪在目标失效（`ref_max_age_s=0.5` / 低 `confidence`）时冻结位姿 / 悬停，
  保持参考、不追逐旧目标。
- **不假定两者相同**：地面是"有期限保持最后有效目标后安全停车"，空中是"冻结位姿 / 悬停"。

### (h) 外部规划器契约：`/agc/ground/path` 的 `nav_msgs/Path` 主题

- 话题 `/agc/ground/path`，类型 `nav_msgs/Path`，`header.frame_id = world`（Gazebo world 的 ENU 基准）；整条路径
  一次性发布，新消息**整体替换**旧路径，不做增量拼接、不做分段订阅。
- **这是 AGC 自定义数据接口，不是 Nav2 原生入口**：Nav2 控制器的路径输入是 `FollowPath` action 的 goal 负载
  （`goal.path` → `setPlannerPath`），`controller_server` 全文只有一个订阅（`speed_limit`）；`planner_server` 的
  `plan` 主题确实存在，但源码注释写明用途是可视化、**不驱动控制器**。
- 代价一并登记：主题**没有 action result / error_code**，路径生命周期、失败分类、质量门三件事全由 AGC 自己定义。

### (i) 五类质量门、失效语义与路径 / goal 关系（禁止隐式回退）

消费任何路径之前执行质量门：**从未收到**（启动后未收到过任何一条）/ **空**（`poses.empty`）/ **单点**
（`size < 2`，无法确定行进方向）/ **帧不一致**（`frame_id` 不是 `world`，**不做**静默按同名轴解释）/ **过期**
（距 `header.stamp` 超过有效期）。失效统一处置为**输出零速到既有 `cmd_vel_raw` 链**（`cmd_vel_raw` →
`collision_monitor` → 唯一执行口保持不变）。

**禁止隐式回退**：路径无效 / 缺失时**不得**沿用旧路径，**不得**静默退回 goal-only。路径回答"沿什么线走"，goal
仍回答"目标在哪、到没到"；两者不一致时按绑定失效触发重规划，**不得**静默按 goal 直连。"还能不能靠 goal 走"是
**另一个模式**，必须显式选择并标注。过期阈值取哪个值、是否复用既有键归具体实现，本 ADR **不新增契约参数入口**。

### (j) 启动边界：命令源完全缺失时安全层不会兜底

Nav2 `collision_monitor` 的 `process` **只由 `cmd_vel_in` 回调触发**，文件内没有独立的定时 `process`；
`source_timeout` 的清零发生在 `process` **内部**。因此**启动后从未发出过 `cmd_vel_raw` 时它一个速度消息都不发**。
现有 `stop_pub_timeout: 1.0e9` 只保证"**收到过**命令后持久发零速"，**不覆盖"从没收到"**。要求：消费者在启动后
无路径时**仍须持续输出零速**到 `cmd_vel_raw` 并记录安全链的实际输出；三种情形须分别有行为证据——① 启动后无
路径；② 运行中路径源消失；③ 收到路径但路径失效。**不得**靠"反正有安全层兜底"。

### (k) 路径 → 局部策略输入缝：传输缝 ≠ 模型观测缝

三个东西必须分开宣称：**传输缝**（话题、类型、帧、QoS、质量门）、**占位消费**（一个确定性消费者真的读了路径并
据此出速度）、**模型观测缝**（训练策略的固定维观测里真的含路径信息，且该策略被训练 / 验证过）。

- 传输缝存在**不蕴含**"RL 会跟踪路径"。可宣称"`/agc/ground/path` 被实际消费"当且仅当有运行图 / 行为证据表明某
  消费者读取了它且输出随之改变；**不得**宣称"训练 RL 已具备路径跟踪能力"，除非 obs 空间**已包含**路径且策略
  **经过训练与验证**，二者缺一不可。
- **不得**为让路径"进得去"而静默改变既有 obs / action 维度（会让已加载策略失效或输出错位）。
- 占位消费者是**确定性**逻辑：**不是**学习策略、**不是**新局部策略、**也不等于**复用基线的 LQR 跟随（后者只能记作
  baseline / LQR 证据，不能满足 `agc_rl` 侧路径消费的出口）。
- 裁剪语义（自 MPPI / RPP 的已验证做法提炼，非照搬）：① 限界找最近点（按弧长截出搜索窗口，避免折返时选到后段）；
  ② 前视窗口（只在"最近点 → 前视距离"内取参考，前视距离是"局部策略看多远"的唯一参数）；③ 帧变换在消费端做，且
  **路径点的 `header.stamp` 不被信任**，以当前车体位姿时刻为准；④ 至少 2 点；⑤ 空结果必须显式失败，不能返回空
  序列让下游自己猜。Nav2 的"按 costmap 边界截断"在 `command_source=rl` 下**不适用**（不起 costmap），改用弧长 /
  前视距离截断。

### (l) 地面侧职责分层与当前占位实现事实

- 空中只提供**处理后的数据**（障碍物分布 / 全局 map），全局路径由**地面侧**规划—— 把规划抬到空中会削弱「地面自主
  规划」这一研究点。地面侧占位规划器**只发布路径，不发布速度**；速度仍只由局部策略出，经安全层到唯一执行口。
- ~~占位发布方 `agc_ground/placeholder_path_planner`：几何直连~~ —— **已退役**
  （[ADR-0048](0048-ground-hybrid-astar-se2-planner.md#top)）。现行发布方是
  `agc_ground/hybrid_astar_se2_planner`（Hybrid A* on SE(2)，四阶段链），
  仍非 Navfn / 非 `planner_server` / 无 costmap、只发路径不发速度；
  无授权 / 无目标 / 过期 / **规划失败**时**不发**（**不重发旧路径刷新 `header.stamp`**）。
- 消费方是 `agc_rl` 侧的**确定性占位消费者**（五类质量门 + 限界最近点 + 前视参考），**只替换航向参考**，不改变
  `interface.py` 的 obs / action 空间。运行图证据：`path` 唯一发布者是该规划器、唯一订阅者是 `ground_policy_rl`。
- **本组决策不等于"外部节点到货即可零改动直接替换"**：四项未决未填，上述参数只属当前占位阶段。

<a id="ruling-r1-r3"></a>
### (n) 用户裁定 R1/R3（2026-10-31）：外部独立节点 + 地面自规划

> 本节记录**用户直接裁定**，不是本 ADR 的技术推导。原措辞保留在
> `.coordination/` 历史台账；此处只留决策与边界。

**R1 · 全局路径规划器：先占位跑通，后续接入外部独立节点**

- **终局**：全局路径规划**最终由外部独立节点提供**—— 对方交付形态是**独立 ROS 节点**
  （**不是**本仓内部实现、**不是** Nav2 插件）。本仓须**预留可替换接入缝**，使该节点到货后能在
  **不改任务层、不改 9 消息 ABI、不改唯一执行口**的前提下接入
  （替换口径参照 [ADR-0011](0011-interception-and-fire-control.md#top)："对外零破坏、内部允许演进"）。
- **阶段**：**现在先用简单占位规划顶着位置跑通链路**（几何 / 直连占位，只要能到目标位置即可，
  **不追求路径质量与最优性**），先把"规划器 → 路径 → 小车"这段接口跑成，再等外部算法替换。
- **"外部节点到货即可零改动替换"是被明确否定的表述**：(m) 四项未决未确认前，本 ADR 只约束当前占位阶段。

**R3 · 空地数据流：空中只给"处理后的数据"，地面自己规划全局路径**

- **澄清**：此前"规划算法把路径生成给小车"的说法，实指——**空中只把视觉处理后的数据**
  （障碍物分布 / 全局 map）**交给地面，全局路径由地面车自己规划**。据此，
  [ADR-0001](0001-project-positioning-and-execution-scope.md#top) 对"把规划抬到空中"的**否决继续有效**，
  数据流沿用其"UAV 感知 → 融合 → 全局 map → 地面规划消费"骨架（`/agc/map`）。
- **与 R1 的读法（须同时成立）**：R3 定"规划器住在**地面**侧"；R1 定"地面侧那个规划器**将来由外部独立节点
  实现**、现在先用占位"。二者**不矛盾**——"小车自己规划" = 今天的占位实现；"外部独立节点" = 后续替换目标。

<a id="open"></a>
### (m) 未决项（外部提供方确认前不得视为已定）

| # | 未决内容 | 谁确认 |
|---|---|---|
| 1 | **世界表示**：外部节点消费什么—— 今天规划可用的只有 `z≈0.48 m` 单平面激光与 `/agc/map` 三态栅格 | 外部节点提供方 + 用户 |
| 2 | **最终消息类型与坐标系**：是否仍为 `nav_msgs/Path` + `frame_id=world`，或改为其它类型 / 帧 | 外部节点提供方 |
| 3 | **重规划触发语义**：如何与 (a)(f) 的位移阈值 / 绑定失效口径对齐 | 外部节点提供方 + Leader |
| 4 | **最终 fail-stop 行为**：路径失效 / 规划失败时外部节点与本仓各承担什么 | 外部节点提供方 + 用户 |

四项确认前：(a)–(g)、(j) 是仓内现行口径；(h)(i)(k)(l) 中与占位链路绑定的部分只约束**当前占位阶段**，不构成外部
节点契约。

## 当前生效参数与证据

- 基线（`src/agc_ground/config/baseline.yaml`）：`replan_displacement_m=1.0`、`max_path_age_s=5.0`、`replan_period_s`、`stop_on_invalid=True`、`goal_info_topic=/agc/ground/goal_info`。占位链路（`agc_rl/config/rl.yaml` + `agc_ground/config/ground.yaml`）：`path.max_age_s=5.0`、`lookahead_m=1.0`、`search_dist_m=0.0`、`goal_tol_m=0.3`、`goal_consistency_m=1.0`；`path_spacing_m=0.5`、`rate_hz=5.0`、`replan_period_s=2.0`、`replan_displacement_m=1.0`；`path.enabled` 默认 `true`（`false` 为显式对照，产物须标注）。契约参数入口**未新增**条目。
- 证据：`experiments/w5-ground-nav-safety/20261015-w5-r012-0/metrics/r012.json`（绑定 / 增障重规划 / 不可达停车，`overall_pass=true`）、`experiments/w6-task-eval/20261018-w6-r041-0/r041/bench.json`（目标失效台架）、`experiments/w7-rl-b/20261024-w7-rl-b-p2-replan-audit/metrics/p2_replan_audit.json`（伪触发审计）、`experiments/w7-rl-b/20261024-w7-rl-b-p2-map-trigger-bench/metrics/p2_replan_bench-postfix.json`（–回归）、GUI 双成功 `20261101-g2-r8b-track-gui-baseline` / `-rl`（终态 `TRACKING_SUCCESS`）。
- 关键实测：（未知格 0 ↔ −1 翻转）14 → 0 次、（移动目标 marking 迁移）4 → 0 次、（真实增障 + 动态 marking）
  4 → 1 次、真实增障仍恰好 1 次；增障重规划延迟 0.002 s；审计前该臂每回合 23.7 次重规划。

## 不做什么（边界）

- 不改冻结 9 消息 / 服务 ABI；不改 `/agc/ground/goal` 的类型与语义；不变**唯一执行口语义**；**不新增第二 ROS 命令者**（契约 [#execution-port](0020-package-boundaries-and-runtime-topology.md#execution-port)）。
- 不引入 `bt_navigator` / 行为树；不改 Nav2 planner 插件本体；不改控制律 / 安全层 / 终态语义。
- 不把占位规划器写成"Nav2 原生 Path 订阅"；也不因"自定义"就认为方案不成立。
- 不做"按目标位置排除 lethal 格"、不直接过滤目标点云、不对 voxel 层做去抖、不改用 `/agc/map` 内容身份（属另一
  原因，须另立决策）。
- 不把"确定性占位消费者能沿路径走"写成"RL 局部避障已实现"；局部避障 ≠ 安全层（安全层只裁剪速度、不做绕行规划）。

## Considered Options

- **action 承载路径（同构 `FollowPath`）** —— 暂不采用：能抄到完整错误码，但 RL 侧要引入 action client 与 goal
  handle 生命周期，与"只跑通接口"不匹配；保留为备选。
- **让 RL 成为 `nav2_core::Controller` 插件** —— 被否：与"RL 主控 / Nav2 安全层"冲突，与"外部独立节点"方向相反。
- **`twist_mux` 式运行时仲裁** —— 被否：路径是**数据**不是**命令**，命令源互斥已由拓扑保证。
- **现在就用 Nav2 `planner_server` 当占位** —— 被否：会与离线对照基线混为一谈，且需要 costmap 进程。
- **目标失效即立即安全停车 / 受限搜索** —— 被否：前者误判常态抖动，后者本项目无搜索策略、会产生无依据运动。
- **改 `/agc/ground/goal` 类型携带身份 / 有效性** —— 被否：会动冻结接口；改用带外伴随诊断。
- **保留 `>1e-6` 强制重规划仅加注释 / 接受移动目标触发地图重规划** —— 被否：正是要消除的抖动；实测 3 episodes
  30 次触发、86.67% 改变了路径点数。

## Consequences

- **正面**：路径绑定可判定、失效即停车；目标失联不再被新时间戳掩盖；伪触发重规划被消除（频率可复核）；传输缝与
  模型能力被显式分开，"能跑通接口"不会被误读成"RL 会跟踪路径"。
- **代价 / 限制**：质量门与失效语义全部自研，**没有** Nav2 错误码体系兜底；路径年龄判据属自定策略，**不能**称
  "对齐 Nav2 默认行为"；动态障碍不再造成**立即**重规划（响应受 `replan_period_s` 约束）；`goal_hold_valid_s` 窗口
  内地面仍朝最后有效目标前进（故意，"不丢目标"优先）；`/agc/ground/goal_info` 与 `/agc/ground/goal` 须同源（由
  `task_manager` 单一发布）才能保证有效性一致。
- **未决**：`goal_hold_valid_s` 的最终标定值；`/agc/ground/goal_info` 在 RL 主控侧是否同样接线；外部节点四项 (m)。

## 参考

- 契约真源：[#hard-constraints](0020-package-boundaries-and-runtime-topology.md#hard-constraints)、
  [#execution-port](0020-package-boundaries-and-runtime-topology.md#execution-port)、[#params](0020-package-boundaries-and-runtime-topology.md#params)、
  [#terminal-semantics](0014-task-fsm-and-scenario-transaction.md#terminal-semantics)
- 相关决策：[ADR-0003](0003-nav2-paradigm-absorption.md#top)（按命令源裁剪）、
  [ADR-0004](0004-ground-control-rl-primary-and-nav2-safety.md#top)（RL 主控 + 安全层）、
  [ADR-0007](0007-scene-geometry-single-source-and-layout.md#top)（地图内容身份）、
  [ADR-0009](0009-perception-truth-derived-and-vision-path.md#top)（不得静默回退的同源纪律）、
  [ADR-0010](0010-safety-thresholds-and-failsafe.md#top)（安全阈值与安全层）、
  [ADR-0001](0001-project-positioning-and-execution-scope.md#top)（地面自主规划）
- 术语：`GLOSSARY.md` 的**局部避障**、**安全层**、**全局路径规划**、**路径输入缝**
