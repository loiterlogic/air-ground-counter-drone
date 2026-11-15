<a id="top"></a>
# 地面安全层自研：输入契约、判定模型与失效语义

## Status

accepted（2026-11-13，用户裁定；实施前运行期仍由 Nav2 `collision_monitor` 承担）

> **补充 by [ADR-0047](0047-directional-safety-tier-semantics.md#top)（2026-11-13，非取代）**：
> 本篇 (c) 的**档位判定**里，「按车体外缘到最近阻挡/未知格的距离 `d` 落档」这一条
> 由 ADR-0047 改为**方向化走廊净空** `d_corridor`（只量沿运动方向、车体宽度带内）。
> 三档**绝对值**、**顺序不变量**、输入契约、失效语义、判定顺序**全部不变**。

> **取代范围（部分 supersede）**：本篇取代 [ADR-0003](0003-nav2-paradigm-absorption.md#top) (a)
> 「**地面域**真跑 Nav2 本体组件」中**安全层**这一项，以及 [ADR-0004](0004-ground-control-rl-primary-and-nav2-safety.md#top)
> (a) 的链路「经 Nav2 `collision_monitor` 收敛到唯一执行口」。
> **仍有效的部分**：唯一执行口语义与链路**顺序**（命令源 → 安全层 → `/agc/ground/cmd_vel` →
> 执行中继）不变；RL 主控地位、(c)(d)(e) 的动作方向 / 量纲 / 逃逸标定、
> [ADR-0010](0010-safety-thresholds-and-failsafe.md#top) 的**档位顺序不变量**与末端失效停车均不变。
>
> **实施状态（2026-11-13 更新）**：**已实施**。`ground_safety_filter` 已接入主链并跑通整链
> （headless `full` 后端 + `yard` + `s04`，终态 `TRACKING_SUCCESS`，见「实施回填」），
> Nav2 安全层已退役（台账见[路线分支治理 5.2.6](../conventions/路线分支治理.md#current)）。
> 逐例判定表、标定方案与验收矩阵见
> [地面安全层判定与标定](../conventions/地面安全层判定与标定.md#top)。
> **标定状态（2026-11-13）**：`a_brake` / `t_react` / `cell_epsilon` / `slow_min_ratio`
> **已在真实差速车上重标并写回配置**，且有**可重放的录制输入序列**（974 拍逐拍一致）。
> 三档距离沿用 ADR-0010 的实测值（新制动模型下仍自洽，见「证据 D」）。
> 仍待标定的是**计算预算**与**未知占比阈值**（见「已知未完成项」）。
> 标定方法与可重放链路见[判定与标定](../conventions/地面安全层判定与标定.md#calibration)。

<a id="why"></a>
## 背景

地面主链的职责分层是「局部策略 → 原始速度 → 安全层 → 唯一执行口」。安全层此前**恒为**
Nav2 `collision_monitor`，其判据、参数与失效语义都是 Nav2 的。2026-11-13 的任务裁定要求
「不依赖 Nav2 运行时或 Nav2 私有判据」，因此必须先回答三件事，否则改写只会把同一套假设换个壳：

1. **输入从哪来**。Nav2 安全层的唯一观测源是 `scan`（`z≈0.48 m` 单水平切面、20 m 量程），
   而任务1 已经把障碍真值换成**感知地图链**（`/agc/map`）。若安全层继续订阅激光，
   同一个障碍就会有两套表示（地图 + 扫描），违反「输入同源」。
2. **哪些 Nav2 语义值得留、哪些必须丢**。逐条核对本机安装的 `nav2_collision_monitor`
   （Jazzy 1.3.13）后，有四条语义是**已验证的失败模式**，不得继承：
   - **启动静默**：`process()` 只由 `cmd_vel_in` 回调触发，节点**无定时器**
     ⇒ 命令源从未发过命令时**一个速度消息都不发**（`stop_pub_timeout` 覆盖不到）。
     本仓已把该坑写在 `ground.yaml` 与 `ground_bringup.launch.py` 注释里，但它一直是**已知缺口**。
   - **输入自身不设时效**：`cmd_vel_in` 陈旧**无检测**（源码无 `cmd_vel_timeout` 类判据）。
   - **状态边沿发布**：`state_topic` 仅在 `polygon_name` **变化**时发一条、且消息**无时间戳/header**
     ⇒ 下游必须自锁存。`run_logger` 已为此专门改过口径（`window_valid_v2`）。
   - **停发抑制即活性缺陷**：`stop_pub_timeout` 到期后**停止发布**零速，任何要求周期命令的下游会卡死。
3. **风险图给的新信息要不要用**。`/agc/map` 自 [ADR-0041](0041-geometry-metadata-instances-and-risk-map.md#top)
   起输出**风险分档**（`-1/0/1–98/99/100`），其中 `99 = 车心进入即擦碰` 是 Nav2 的
   二值 lethal 语义**表达不了**的量。自研层如果只按 `100` 判障碍，等于把上游已经算好的
   内切带丢掉，再退回二值。

## 决策

### (a) 安全层**只消费任务1 的规划层地图**，不建第二条障碍链

<a id="inputs"></a>

输入契约固定为**五项必需 + 一项可选**：原始速度意图、车体状态、规划层地图、地图知识时效、
任务许可缺一即零速；逐格元数据只供离线标定与 GUI 取证，**不进实时路径**。

| 输入 | 消息 / 话题 | 是否**必需** | 缺了怎么办 |
|---|---|---|---|
| 原始速度意图 | `geometry_msgs/TwistStamped`，`/agc/ground/cmd_vel_raw`，`frame_id=car/base_link` | 必需 | 零速（`NO_COMMAND`） |
| 车体状态 | `nav_msgs/Odometry`，`/agc/ground/odom`（world）+ `/agc/ground/odom_valid` | 必需 | 零速（`BODY_INVALID`） |
| 规划层地图 | `nav_msgs/OccupancyGrid`，`/agc/map`（`frame_id=world`，transient_local + reliable，**2 Hz**） | 必需 | 零速（`MAP_MISSING` / `MAP_STALE`） |
| 地图知识时效 | `std_msgs/Bool`，`/agc/map/valid` | 必需 | 零速（`MAP_INVALID`） |
| 任务许可 | `agc_msgs/AgcTaskState`，`/agc/task/state`（1 Hz） | 必需 | 零速（`NO_PERMIT`） |
| 逐格元数据 | `agc_msgs/PerceptionCellMeta`，`/agc/map/cell_meta` | **否**（只供离线标定 / GUI 取证） | 不影响判定 |

- **禁止**安全层订阅 `scan` / 点云 / 任何第二份障碍真值，也**禁止**它订阅 `costmap`。
  判据：安全层进程的订阅集合**恰好**是上表的必需项；多一个观测源就是第二真源。
- **为什么 `cell_meta` 不进实时路径**：它是证据层尺寸（`0.25 m`，`400×400 = 16 万格`）
  的六个并行数组，单帧约 3 MB、2 Hz 约 6 MB/s；而安全层每拍只需 4 万个 `int8`
  （`/agc/map` 单帧 40 KB）。把它拖进实时路径是拿带宽换不到任何判定精度的东西。
- **地图新鲜度不能沿用 `source_timeout=0.3 s`**：地图是 **2 Hz**（周期 0.5 s），
  0.3 s 会把正常抖动判成失源。判据改为「**≥3 个发布周期**」，绝对值属可标定量。

<a id="map-semantics"></a>

### (b) 地图取值的**安全语义**由本层自己定义（不借用任何 Nav2 判据）

| `/agc/map` 值 | ADR-0041 语义 | 本层判为 |
|---|---|---|
| `100` | 格内占据 | **阻挡**（格内即有障碍） |
| `99` | 车心进入即擦碰 | **阻挡**（与 `100` 同等对待，`>0` 且 `<=99` 的内切档不降级） |
| `1–98` | 有代价但可通行 | **可通行 + 限速**（进入 `SLOW` 判据的一部分） |
| `0` | 可通行 | **已知自由** |
| `-1` | 未知（从未观测） | **不是已知自由**（不得当作可通行） |

`1–98` 具体推到多慢**不**借用 Nav2 的 `cost_scaling_factor`：本层只用"是否落在
`safety` / `collision` 距离带"来定档，代价数值本身不进判定。

<a id="verdict"></a>

### (c) 判定顺序固定：先证明输入可用，再证明能停住，最后才裁剪速度

1. **输入闸**（`INVALID_INPUT` 及其子原因）：逐项验新鲜度、坐标系、几何一致性、许可、参数合法性。
   任一不过 → **零速**，且**每一拍都发**（不允许"不发"）。
2. **可停性闸**：以当前命令速度为初值算**制动距离**
   `s_brake = v·T_react + v²/(2a)`，把「车体 footprint 沿本拍速度方向扫掠到 `s_brake` 终点」
   覆盖的格集取出，按 (b) 分类。判据是**能停住**：扫掠区内只允许出现**已知自由**；
   出现阻挡格或未知格，说明"按这个速度走，停不住"。
3. **定档**：按「车体外缘到最近阻挡/未知格的距离 `d`」落档（顺序不变量沿用
   [ADR-0010](0010-safety-thresholds-and-failsafe.md#top) 的 `紧急 < 碰撞 < 安全`）：

| 档 | 条件（结构，绝对值待标定） | 输出 |
|---|---|---|
| `PASS` | `d ≥ d_safety` 且扫掠区全为已知自由 | 原命令（仍受 `v_max/ω_max` 限幅） |
| `SLOW` | `d_collision ≤ d < d_safety`，或扫掠区含 `1–98` | 按可停性**同时**裁剪线速度与角速度 |
| `STOP_COLLISION` | `d_emergency ≤ d < d_collision` | 零速 |
| `STOP_EMERGENCY` | `d < d_emergency`，或 footprint 已与阻挡格相交 | 零速 |
| `INVALID_INPUT` | 输入闸任一不过 | 零速 |

- **只裁不造**：输出恒为「输入的收缩」——要么按比例缩小，要么归零。
  安全层**不得**改变运动方向、不得规划绕行、不得生成目标、不得接管任务状态。
- **未知在制动距离之外不算违规**：这是 (c) 的关键取舍——自研层证明的是
  「能在进入之前停住」，不是「前方全部看过」。这样既 fail-closed，
  又不会因为地图只覆盖作业区的一部分而把车永久钉死。
- **`SLOW` 必须同时约束 `ω`**：单独限线速度会让"原地快转"绕过判据
  （车角扫掠半径 `r_fp = 0.5789 m` 远大于零），这是 [ADR-0010](0010-safety-thresholds-and-failsafe.md#top)
  扫掠几何的直接推论，不是新增口味。

<a id="fail-states"></a>

### (d) 失效状态显式化，**启动即发零速**

- 节点进入运行即按固定周期（与命令源同量级，20 Hz）**无条件发布** `TwistStamped`：
  没有可用输入时发零速。这直接消灭 Nav2 的「启动静默」缺口。
- 状态机为**显式枚举**（不是隐式布尔）：`STARTUP` / `NO_COMMAND` / `NO_PERMIT` /
  `BODY_INVALID` / `MAP_MISSING` / `MAP_STALE` / `MAP_INVALID` / `CLOCK_ANOMALY` /
  `PARAM_INVALID` / `BUDGET_EXCEEDED` / `PASS` / `SLOW` / `STOP_COLLISION` / `STOP_EMERGENCY`。
  任一非 `PASS/SLOW` 状态 → 零速。
- **时钟异常不算新鲜**：`stamp` 在未来（`age < 0`）一律判无效，**不**把 `age` 钳到 0
  （沿用 `/agc/ground/odom` 的既有门控口径）。
- **恢复必须带迟滞**：`STOP* → PASS` 要求连续 `N` 拍满足**更高**的净空门槛
  （`d_recover > d_safety`），`SLOW → PASS` 同理。禁止瞬时恢复。
- **计算预算**：单拍判定超过预算 → `BUDGET_EXCEEDED` + 零速。扫掠格数设硬上限，
  超限按"未知"处理（fail-closed），不得静默截断成"没发现障碍"。

<a id="port"></a>

### (e) 唯一执行口与「没有第二命令者」是**可验证**的，不是声明

- 安全层的**唯一**发布者身份是 `/agc/ground/cmd_vel`；下游 `ground_drive_relay` 是
  GZ `/model/agc_car/cmd_vel` 的唯一 ROS 侧写入者（其自身已带看门狗与 Header 校验）。
- 安全层**不写** GZ 话题、不起 `collision_monitor`、不新增旁路速度发布者。
- 验收判据：`ros2 topic info /agc/ground/cmd_vel` 的发布者数 **== 1**，
  且 `ros2 node info` 证明该发布者就是安全层；`/model/agc_car/cmd_vel` 的 ROS 侧发布者
  数 **== 1** 且为 `ground_drive_relay`。
- 诊断走**非命令型**话题 `/agc/ground/safety_status`（`std_msgs/String`，JSON，
  transient_local + reliable）：原始/有效速度、档位、触发原因、地图年龄、输入年龄、
  未知占比、不可行原因、参数版本。**不新增 `agc_msgs` 消息**，因此不触碰消息 ABI
  （[ADR-0020](0020-package-boundaries-and-runtime-topology.md#messages)）；
  结构化消费若将来确有需要，另立决策。

<a id="boundary"></a>

### (f) 代码归属与可测性

- 归属 `agc_ground`（地面域，安全层属实时敏感域 ⇒ C++ `ament_cmake`，
  [ADR-0020](0020-package-boundaries-and-runtime-topology.md#top) (a)）。**不新建包**：
  安全层与执行中继、规划策略同域，新建包只会多一份依赖声明。
- 判定逻辑抽成**纯头文件类** `include/agc_ground/safety_policy.hpp`（输入输出都是普通 struct、
  不 include ROS 消息包），节点只做 `buildInputs() → step() → applyDecision()`——
  与 `planning_policy.hpp` 同一先例，满足
  [测试分层与可测性](../conventions/测试分层与可测性.md#testable) 的判据。
- **不用 lifecycle 门控发布**（Nav2 的 `unconfigured` 期间不发消息，正是要消灭的窗口）。

## 不做什么

- **不**做全局/局部规划、绕行、地图建图、传感器融合、任务 FSM、碰撞裁决、动态障碍预测、
  三维障碍模型；**不**做 Nav2 兼容层。
- **不**订阅第二份障碍数据（`scan` / 点云 / `costmap` / 真值几何）；**不**自建平行栅格。
- **不**新增 `xxx_mode` / `xxx_backend` / `xxx_source` 路线分支：自研层是**唯一**地面安全层，
  Nav2 版本直接退役，不保留"两套实现由开关选择"。
- **不**改唯一执行口语义、不改消息 ABI、不新增第二 ROS 命令者。
- **不**把二维地图与相机可见性边界外推为三维安全保证。
- **不**在标定前把任何数值写成契约：本篇与配套规范里的数值一律标"待标定"。

## Considered Options

- **继续用 Nav2 `collision_monitor`，只换观测源为 `/agc/map`** —— 被否：
  它没有"地图栅格"源类型（`scan` / `pointcloud` / `range` / `polygon`），
  要接地图就得自写 `Source` 子类并链接 `nav2_collision_monitor` 的**私有头**，
  等于把 Nav2 私有接口变成依赖；且启动静默与停发抑制两个坑仍在。
- **保留 Nav2 作对照臂，自研层作主链** —— 被否：同一功能两套实现由开关选择，
  属[路线分支治理](../conventions/路线分支治理.md#rule) 明令禁止；对照属研究期，
  应在独立脚本里做，不进主链 launch。
- **`unknown` 一律放行** —— 被否：把"没看过"读成"可通行"是安全方向的错误，
  与 `planning_policy.hpp` 的 `classifyCell` 口径冲突。
- **`unknown` 一律阻挡（含制动距离之外）** —— 被否：地图只覆盖作业区的一部分，
  这会让车在未知区边缘永久零速，把"覆盖不足"变成"不可通行"。
  (c) 的"能在进入之前停住"是同一保守性下不产生死锁的表述。
- **把 `cell_meta` 拉进实时判定** —— 被否：单帧 3 MB、2 Hz 6 MB/s，换不到判定精度。
- **按 Nav2 的 `stop_pub_timeout` 语义在静止后停发** —— 被否：那是活性缺陷，
  下游看门狗与任务门控都会卡死。
- **用 lifecycle 节点承载安全层** —— 被否：`unconfigured` 期间不发消息，
  等于把"启动静默"制度化。
- **保留 Nav2 的 `source_timeout=0.3 s`** —— 被否：地图是 2 Hz，判据必须按发布周期推导。

## Consequences

### 正面

- 安全层的输入、判据、失效语义**全部归 AGC 自有定义**，可逐条单测；
  不再依赖 Nav2 私有参数、错误码或插件接口。
- 启动静默、输入自身无时效、状态边沿发布、停发抑制四个已验证缺口一并消除。
- 风险图的 `99`（车心进入即擦碰）第一次进入安全判定，比二值 lethal 多一档真实信息。
- 判定从"某区域里有 N 个点"变成"能不能在这个速度下停住"，阈值因此有物理量纲，
  可被真实差速车标定与重放。

### 代价 / 限制（如实登记，不得据此宣称能力）

- **可见性边界整体换成感知地图的边界**：`≥0.24 m` 可测、`~30.5 m` 可信半径、
  有遮挡阴影、以及地图自身的 2 Hz 老化。**细杆（灯杆 0.12 m、门柱 0.18、消防栓 0.16）
  不再进入安全层视野**——这是相对 Nav2 `scan`（`z≈0.48 m` 水平切面能看到细杆）的
  **能力退化**，须在根 README 的已知边界登记，不得表述为"能力等价替换"。
- **不覆盖动态障碍**：`/agc/map` 的障碍内容来自静态几何的感知重建，
  没有动态层；移动障碍（含他机）**不在保证范围内**。
- **不覆盖三维**：二维 footprint + 地面平面，`z≈0.48 m` 的传感可见性边界仍不得外推。
- **判据依赖地图新鲜度**：地图链断流 / `valid=false` / `stale` 期间车只能停。
  这是有意的 fail-closed，但与"感知慢一点也能走"的旧行为**不等价**。
- **指标口径必须换版本**：`run_logger` 现读 `nav2_msgs/CollisionMonitorState`
  的 `action_type` 来判 `triggered`。改判据后 `shield_infeasible_rate` 的分子分母都会变，
  须按 [ADR-0010](0010-safety-thresholds-and-failsafe.md#top) (f) 的先例
  新增 `definition_version` 并标注**不可与旧口径逐值对照**，不得静默重算历史。
- **淘汰 Nav2 依赖不是零成本**：`agc_ground/package.xml` 的 `nav2_collision_monitor` /
  `nav2_lifecycle_manager`、`agc_task` 的 `nav2_msgs`（`run_logger` 读 cm 状态）都要在
  实施任务里同步处置；`scripts/tests/test_g2_wiring.py` 对 `collision_monitor` 的断言
  须改为防复活闸门而不是删除。

### 未决（必须在实施前定型，不得靠默认值掩盖）

| # | 未决项 | 归宿 |
|---|---|---|
| 1 | `d_emergency / d_collision / d_safety`、迟滞 `N` 与 `d_recover` 的绝对值 | 本任务标定阶段 → 回填配套规范 |
| 2 | `a_brake`、`T_react` 的实测重标（沿用 0.9 m/s² 之前须重测） | 同上 |
| 3 | 地图 / 命令 / 车体 / 任务许可的超时绝对值 | 同上（结构与"≥3 发布周期"已定） |
| 4 | 计算预算绝对值与扫掠格数上限 | 同上 |
| 5 | `1–98` 与 `SLOW` 的关系是否需要"代价越高越慢"的单调映射 | 标定后决定；本轮只定"落在距离带即限速" |

### 实施回填（2026-11-13）

落地形态：`src/agc_ground/src/ground_safety_filter.cpp`（节点，20 Hz 定时器）
+ `src/agc_ground/include/agc_ground/safety_policy.hpp`（纯判定类，不 include ROS 消息包）。
**不新建包**：与执行中继 / 规划策略同属 `agc_ground`，不新增依赖声明。

#### 实测证据 A：节点级三档与启动零速（真实 ROS 消息，隔离 domain）

把 `ground_safety_filter` 当黑盒起真节点，喂真实 `OccupancyGrid` / `Odometry` /
`AgcTaskState` / `TwistStamped`，读它的 `/agc/ground/safety_status`：

| 用例 | 期望 | 实测状态 | 实测输出 |
|---|---|---|---|
| 启动后**不喂任何输入** 3 s | 持续发零速 | `STARTUP` | **60 条 @20 Hz，非零 0 条**（旧 Nav2 此处一条都不发）|
| 空地图 + `v=1.0` | 原样放行 | `PASS` | `v=1.0` |
| 障碍 3.0 m | 限速 | `SLOW` | `v=0.2`（线/角同比例）|
| 障碍 1.5 m | 停车 | `STOP_EMERGENCY` | `v=0`（`d=0.893 < 1.0`）|
| 障碍 0.6 m | 停车 | `STOP_COLLISION` | `v=0`（`swept hit`）|
| 地图 3 s 未更新 | 停车 | `MAP_STALE` | `v=0` |
| 任务许可撤回（`IDLE`）| 停车 | `NO_PERMIT` | `v=0` |

> 首次探测时读到 `MAP_STALE` 是**探测方法的错**（同 domain 里残留的 `map_adapter`
> 用仿真钟发地图，与系统钟混算年龄），隔离 domain 后复测正常。**这个坑本身有价值**：
> 安全层的年龄判据要求所有输入**同一时基**；混时基会表现为"莫名超时"。

上表已固化成语料库内的可执行核查
[`tests/check_safety_layer_live.py`](../../tests/check_safety_layer_live.py)（8 项，退出码语义）：
它把节点当黑盒、用专用 `ROS_DOMAIN_ID`（避免上述混时基假红），**不需要 Gazebo**、秒级完成，
因此可以在没有仿真环境的机器上回答"节点接线对不对"——
这是 45 条 gtest 覆盖不到的一层（gtest 只覆盖纯判定类，订阅 QoS / `frame_id` / 定时器都测不到）。
实测 **8/8 PASS**。

#### 实测证据 B：整链（headless `full` 后端 + `yard` + `s04_static_static_obs_track`）

| 项 | 结果 |
|---|---|
| 终态 | `TRACKING_SUCCESS` / `tracking_milestone`（本次一致；同命令另一次停在 `GROUND_APPROACH`，归属见证据 C）|
| 仿真窗口 / RTF | sim 0.12 → 88.80 s，RTF **0.901** |
| 拍数 | `ticks_total = 2786`，窗口内 `ticks_valid = 2050 / 2050`（**0 个无效拍**）|
| 启动期零速 | 日志实证 `STARTUP → BODY_INVALID（odom never received）零速`：无车体状态时**仍每拍发布**，Nav2 的"启动静默"缺口已消除 |
| 失效状态可观测 | 一轮启动共 10 次状态迁移（`BODY_INVALID` / `MAP_INVALID` / `NO_COMMAND` / `NO_PERMIT` / `PASS`），每条都带原因 |
| 唯一执行口 | `/agc/ground/cmd_vel` 的唯一发布者是 `ground_safety_filter`；中继仍是 GZ 侧唯一写入者 |
| 接触真值 | `collision_count = 1`（`apron_center::link::c@t=2.94 s`，**复位瞬间的建模产物**，非障碍碰撞；与既有 run 同现象）|

#### 两处必须分开读的量

`ticks_triggered = 0` 与 `command_attribution.intervened_ticks = 22` **不矛盾，量的不是同一件事**：

- `ticks_triggered` 只统计**安全层因障碍介入**（`SLOW` / `STOP_*`）；
- `intervened_ticks` 统计**原始与有效速度不一致**的拍，其 22 拍全部出现在
  `NO_PERMIT`（任务授权前）与 `SLOW` 段 —— 前者是"任务没授权所以我压成零速"，
  属**正确行为**，与"看到障碍"无关。

如实登记：本次 run **没有触发过任何障碍档**（场景无障碍、路径直达），
因此 `SLOW` / `STOP_COLLISION` / `STOP_EMERGENCY` 的**整链行为**尚无实测证据，
只有 45 条单测覆盖。这属**未完成的验收项**，不得据本次 run 宣称三档已在整链成立。

#### 实测证据 C：整链回归对比（**如实登记一次未达终态**）

同一命令（`--headless --backend full --duration 70`）连跑三次，结果**不稳定**：

| run | 代码 | 终态 | 安全层介入 |
|---|---|---|---|
| ① | 本篇（自研层） | `TRACKING_SUCCESS` | 5 段 / 22 拍 |
| ② | 本篇（自研层） | **`GROUND_APPROACH`**（未达终态） | 2 段 / 33 拍 |
| ③ | **改造前基线**（`git stash` 后同机同命令） | **`GROUND_APPROACH`**（未达终态） | 2 段 / 116 拍 |

**结论（可判定）**：② 的未达终态**不是本次改造引入的回归** —— 把改动 `git stash`
回到改造前，同命令同样停在 `GROUND_APPROACH`。这是**既有的整链间歇性未达终态**
（`tests/README.md` 已登记 `air_hover_timeout` 一类偶发 infra，此处是同一性质的地面侧表现）。

**为什么必须写在这里**：只报 ① 会让读者以为"改完就没问题"；只报 ② 会让读者以为"改坏了"。
三次对照才把归属钉死。**这不能用来宣称改造"无回归"** —— 正确表述是：
在本次可观测到的差异里，未发现由安全层改造引起的回归；终态稳定性问题在改造前已存在。

#### 实测证据 D：动力学标定（2026-11-13，`safety_dynamics_v1`）

台架：[`tests/check_safety_calibration.py`](../../tests/check_safety_calibration.py)（分阶段，
因为任务窗口 `t_max_s=120 s` 装不下四项）。**必须在 `backend:=full` 下做**——安全层只认
`/agc/map`，无相机的台架地图恒空、车根本不动（见下）。

| 量 | 实测 | 原配置值 | 结论 |
|---|---|---|---|
| `a_brake` | **3.6079 / 3.2754 m/s²**（v=1.5 阶跃到 0）| `0.9` | 取**最小** 3.2754 → 写回配置 |
| `t_react` | 零速后 **0.1841 s**（p95）；含 `t_cmd_timeout` 为 0.727 s | `0.3` | 取零速后值 → 写回配置 |
| `cell_epsilon` | 判停净空 2.249 / 2.086 / 1.773 m，**跨距 0.476 m ≈ 1 格** | `0.05` | 取半格对角 **0.3536** → 写回配置 |

**这三项都是"配置值错了"而不是"实现错了"**，且**三个方向不同**，必须分开说：

- `a_brake` 旧值 0.9 只有实测的 **27%** ⇒ `s_brake` 被**高估 2.7 倍**
  （v=1.5 时 1.70 m vs 实测 0.62 m）⇒ 车会在**远未接近**障碍时就停死。方向保守但不可用。
- `t_react` 旧值 0.3 比实测大 **63%** ⇒ 同样保守。
- `cell_epsilon` 旧值 0.05 只有半格对角的 **14%** ⇒ 量化误差被**低估**，
  净空判据系统性**乐观** —— 这一项是**不安全方向**，必须抬高。

**档位距离不需要改**：新模型下 `s_brake(1.5) = 0.620 m`，仍远小于
`d_collision = 2.0 m`（余量 1.38 m）与 `d_emergency = 1.0 m`（余量 0.38 m），
三档语义自洽。**改的只是"能不能停住"这个判据的精度，不是档位本身。**

#### 标定过程本身暴露的三个坑（写下来防重犯）

1. **必须 `backend:=full`**：`safety_scenario` / `lightweight` 无 nadir 相机 ⇒ `/agc/map`
   恒空 ⇒ 安全层严格 fail-closed 只能停。标定必须先看到 `occupied > 200`。
2. **必须让任务进入驱动许可态**：任务在 `IDLE` 时安全层输出零速（正确行为），
   此时测到的是"零"不是"标定失败"。锁存终态（`INFRA_FAILURE` 等）下 `abort` 会被拒、
   `start` 报 `release_control_failed` ⇒ **一次 launch 只能标定一个阶段**。
3. **"开阔区"不能写死坐标**：曾写死 `(20, 25)`，而它在地图里是 `-1`（未知）⇒
   车不出发；也曾取"第一个满足 6 格半径的格"，而它周围仍有障碍落在 `d_safety` 带内
   ⇒ 安全层正确限速到 0.3 m/s，测到的是"0.3 m/s 的制动"。现在按**当前地图**
   现找最大自由区，并要求 `d_safety + 车体对角` 半径内无任何非 free 格。

#### 实测证据 E：`SLOW` 裁剪会**削弱横向逃逸能力**（用户裁定项，发现真实缺陷）

用户 2026-11-13 裁定：不能只靠"同比例裁剪保持曲率"推理，必须**单独实测**证明
`SLOW` 之后车仍能做 `max_offset = 1.0 m` 的横移。实测结果推翻了原设计：

| `slow_min_ratio` | 2 s 横移实测 | 结论 |
|---|---|---|
| **0.20**（改造前配置） | **0.0002 / 0.030 / 0.048 m** | 车基本不动，**逃逸能力实质归零** |
| 1.00（不降速，对照） | 0.956 / 1.153 / 0.769 m | 能力本来就**贴着** 1.0 m |

**数学上为什么不显然**：横移 ≈ `(v/ω)(1−cos ωT)`。同比例裁剪让 `v/ω` 不变，
但 `ω` 变小使 `(1−cos ωT)` 变小 —— **两项方向相反**，净效果必须实测。

**这条缺陷的性质**：它不违反任何停车判据（车仍然停得住），所以**既有 48 条单测全绿也发现不了**。
它只在"真正需要躲开"的时刻暴露：安全层把车裁到 20% 速度，车就失去了躲避能力，
只剩"原地等撞"。对一个兜底屏障来说，这是把"躲开"降级成"停死"。

**修复**：

1. `slow_min_ratio` 的默认值不再是手感值（原 0.2），改由 `slowRatioFloor()` **从物理量反解**：
   要求 `L(r)·eff ≥ required`，其中 `L(r) = (v_cap/ω_cap)(1−cos(r·ω_cap·T))`、
   `eff` 是实测折扣（侧滑削刮：理想 1.398 m vs 实测最小 0.769 m ⇒ 0.55）。
2. **启动期校验**：`slow_min_ratio` 低于反解下限即**拒绝启动**，并给出可读理由。
   这一条防的正是"为了早点减速而把车裁成不会动"——它不会体现在任何停车判据里。
3. 如实承认 `1.0` 是合法取值：当实测能力贴着要求时，正确做法是**不降速**，
   而不是裁一点求安心。校验只拒绝 `>1`（放大）与 `<=0`（等于停车）。

**同时暴露的上游矛盾（不在本篇处置，明示挂起）**：
`max_offset = 1.0 m` / 反应窗口 `T = 2.0 s` / 实测折扣 `0.55–0.69` 三者**不能同时满足** ——
按最小折扣算，即使完全不降速也只有 0.769 m。这不是安全层的错，而是
[ADR-0004](0004-ground-control-rl-primary-and-nav2-safety.md#top) (e) 的 `max_offset` 标定
（当时 4 次采样最小值 1.017 m，余量很薄）与本次实测分布不一致。**须由用户裁定**：
是放宽 `max_offset`、还是延长反应窗口、还是承认"2 s 内横移 1 m"不是本车的能力主张。

#### 实测证据 F：**可重放的录制输入序列**（配套规范的硬要求）

配套规范要求「标定必须能以**录制的输入序列**离线重跑判定类，且**逐拍输出与在线一致**」。
本轮补上了这条链路，并**靠它抓到三处静默分叉**：

| 组件 | 作用 |
|---|---|
| [`tests/record_safety_inputs.py`](../../tests/record_safety_inputs.py) | 录 `SafetyInputs` 每个字段（含**整幅地图快照**，按内容去重：1395 拍只需存 139 幅）；同时存下在线算好的四个输入年龄与在线判定状态 |
| [`src/agc_ground/test/safety_replay.cpp`](../../src/agc_ground/test/safety_replay.cpp) | 离线重放：**`#include` 生产类 `SafetyPolicy`**，逐拍与在线对拍 |

**实测**（`experiments/w5-ground-nav-safety/20261113-calib-replay/`）：
**974 拍，状态一致 974，不一致 0** —— `PASS`。

**三处靠对拍才暴露的分叉**（都属"线上对、离线错"或反之，人工阅读极难发现）：

1. `permit_states` 默认值：头文件 `{3}` vs 节点/`ground.yaml` `{3,4}` ⇒ 重放把
   `TRACKING_SUCCESS` 判成 `NO_PERMIT`。**同一语义三处默认值不一致**，已统一。
2. 录制器 `now_s` 取了系统时钟（1.79e9）而消息 stamp 是仿真时间（~200 s）⇒
   年龄算成 1.79e9 ⇒ 重放全 `MAP_STALE`。**时基不一致**，已改为同域取锚点。
3. `now_s` 只锚在命令 stamp 上：地图（2 Hz）与任务状态（1 Hz）的 stamp 可能**超前**该拍命令
   （实测最多 0.26 s）⇒ 重放判 `CLOCK_ANOMALY`，而线上 `now()` 恒 ≥ 已收到的任何 stamp。
   已改为 `now_s = max(各已收到输入的 stamp)`。

**一致性边界（如实声明，不外推）**：重放能复现的是**判定**（状态 / 输出速度 / 诊断原因），
**不**复现 ROS 的 QoS、发现、时钟同步，也**不**复现节点里 `budget_ms` 的在线实测耗时
（重放跑在空闲机器上，耗时不代表在线）。年龄是**输入**，由录制原样回喂，不重新推导 ——
否则对拍会混入一次采样相位误差。

#### 已知未完成项（不得当作已达标）

1. ~~动力学标定未重做~~ → **已完成**，见「实测证据 D」。
2. ~~`cell_epsilon` 未经离散误差标定~~ → **已完成**（取半格对角 0.3536）。
3. **三档只有节点级证据、没有整链障碍场景证据**：见下行（这是本次暴露的真问题）。
4. **影响指标口径**：`shield_infeasible_rate` 只统计障碍介入；有障碍场景下该值会变，
   `window_valid_v3_self_owned_safety` 已标注不可与 v1/v2 逐值对照。

#### 本次暴露的真问题：`safety_scenario` 在新口径下**没有障碍输入**（仍未解决）

`safety_scenario.launch.py`（车对立柱 5 m、goal 越过立柱）是验证三档的既有台架。
改完后实测它**跑不出三档**，原因不是实现错，而是**输入契约变了**：

- 该台架起的是 `skeleton.launch.py`，**不含空中链路** ⇒ 没有 nadir 相机 ⇒
  `nadir_projection` / `map_adapter` 无观测 ⇒ `/agc/map` 永远 `occupied=0` 且 `valid=false`
  （实测日志：`occupied=0 ... cam_h=0.00 fp=0.0x0.0`）。
- 旧 Nav2 安全层用 `scan`，该台架**有激光**，所以以前能触发；新层**只认地图**，
  于是"障碍在物理世界里、不在我看到的那张图里" ⇒ 严格 fail-closed，只能停。

**这不是可以靠调参绕过的**：绕过它就等于允许安全层去订阅第二份障碍数据，
而那正是本篇 (a) 明令禁止的。

**候选修法只有三条，且每条都有实质代价 —— 须用户裁定，本轮不自行选**：

| 方案 | 做法 | 代价 |
|---|---|---|
| A. 台架改走 `backend:=full` | 用现成的含空中链路入口跑安全场景 | 要拉起 PX4 / 双机 / 相机，台架从"秒级最小场景"变成"整链"，且 `air_present: false` 的既有语义要一并改 |
| B. 给该台架起一个"只为产地图"的感知机 | 在 `safety_scenario.launch.py` 里额外起 PX4 + nadir | 台架复杂性上升；且这是否算"新增路线分支"须按[路线分支治理](../conventions/路线分支治理.md#rule)走四项准入 |
| C. 承认该台架**不再适用**，改用 `full` 整链做三档取证 | 不修台架，直接用证据 A/B 的方式在整链上取证 | 失去"最小场景"的快速回归能力；`tests/check_action_direction_escape.py` 等 5 个 L4 脚本一并作废 |

**重要事实（决定为什么不能"顺手补一张静态地图"）**：`map_adapter` 是 `/agc/map` 的**唯一**发布者，
而它的内容**只能来自** `/agc/obstacles`（感知）。`obstacles_file`（静态先验）已随
[ADR-0035](0035-perception-map-representation-and-unknown-policy.md#top) (b) 退役。
所以"给台架喂一张静态地图"= 复活已退役的第二份障碍来源，**违反本篇 (a)**，不是可选方案。

**用户裁定（2026-11-13）：选 C** —— 承认该台架不再适用于安全层取证，改用 `backend:=full` 整链。

### 按 C 执行的结果（如实登记：**仍未取得三档整链证据**）

已按 C 改造[`tests/check_safety_tiers_escape.py`](../../tests/check_safety_tiers_escape.py)：
不再依赖 `safety_scenario`，改为在 `backend:=full` 上跑，并且**判据改用安全层自己的档位**
（读 `/agc/ground/safety_status` 的 `state`），不再从"速度变小了"反推 —— 后者分不清
"安全层限速"与"命令源本来就在减速"，属归因错误，是改造前的实际缺陷。

**但两次整链实测都没有触发 SLOW / STOP_*，因此三档的整链证据仍未取得**：

| 场景 | 结果 | 为什么没触发 |
|---|---|---|
| `s04`（默认主场景） | 全程 `PASS`，终态 `TRACKING_SUCCESS` | 路径本身无遮挡，安全层**正确地**不需要介入 |
| `s11`（goal 在立柱另一侧） | 感知 `连通域 0`、`障碍像素 0` ⇒ 地图恒空 ⇒ 车不动 | 见下"几何不合" |

**`s11` 为什么拿不到障碍（实测 + 计算，不是猜测）**：

- `pole_1` 尺寸 `0.3×0.3×3.0`，底面 z=0、**顶面 3.0 m**；
- 该场景无人机**低飞**：`map_adapter` 实测 `cam_h = 3.39 m` ⇒ 相机只比柱顶高 **0.39 m**，
  几乎平视；单目正下视在这种掠射角下拿不到柱顶的稳定连通域；
- 即便正上方，`GSD = 0.0126 m/px` ⇒ 柱顶只有 **24 px**，而门限 `min_obstacle_side_m=0.24 m`
  换算为 **19 px** —— 只高出 5 px 的余量。

⇒ **这是几何不合，不是配置错误**：`s11` 的柱 + 低飞无人机这一组合，在"安全层只认感知地图"
的新口径下**无法产出障碍**。改造前它可用，是因为旧 Nav2 安全层用 `z≈0.48 m` 的激光**平扫**，
能打到这根柱子 —— 那正是本篇 (f) 登记过的能力退化，此处得到了独立复现。

**但三档整链证据其实已经拿到了** —— 在**标定**里，不是在上面那两个场景里：

`tests/check_safety_calibration.py --stage cell` 会让车**朝地图里真实存在的障碍开过去**，
实测（`experiments/w5-ground-nav-safety/20261113-calib-cell5/`）：

| trial | 安全层状态 | `d_min_m` | 输出速度 |
|---|---|---|---|
| 0 | `SLOW` | 2.249 | 0.16（被裁剪）|
| 1 | `SLOW` | 2.086 | 0.16 |
| 2 | **`STOP_COLLISION`** | 1.773 | **0** |

即 `PASS → SLOW → STOP_COLLISION` 的**真实递进**已在 `full` 整链 + 真实障碍上成立，
且**判据来自安全层自己的 `state`**，不是从速度反推。

**`STOP_EMERGENCY` 在整链上**没有**被触发，而且这**不是缺陷**：
实测制动距离 `s_brake(0.8) = 0.245 m`，车在 `d≈1.77 m` 就被 `STOP_COLLISION` 的扫掠判据截住，
**不会**再靠近到 `d < d_emergency = 1.0 m`。`STOP_EMERGENCY` 正确的触发条件是
"障碍**单拍突现**在 footprint 内"，那属于故障注入而非"逐渐开近"。
它已由活节点核查 [`tests/check_safety_layer_live.py`](../../tests/check_safety_layer_live.py)
的用例 `d_near` 覆盖（实测 `state=STOP_EMERGENCY, v_out=0`）。

**仍未完成**：`s11` 那条「车被立柱阻隔」的**最小场景回归**能力已因几何不合永久失去
（柱 0.3 m / 相机 3.39 m 近掠射 / 24 px 余量 5 px）。若仍需要它，必须新造一个
"障碍足够大且车必须逼近"的场景，属**新建场景**，须按场景轴登记规则另立 ——
本轮不擅自改 `scenarios.yaml`（会改变回归矩阵的既有格）。

**同一原因的另一处影响**：`tests/` 下 5 个 L4 脚本仍以
`/collision_monitor/get_state` 判断"安全层是否 active"（`check_scan_self_filter` /
`check_scan_source_loss_stop` / `check_action_direction_escape` /
`check_actuation_relay_hardening` / `check_baseline_path_replan`）。该服务已随节点退役，
这些脚本会如实 FAIL。**未修改它们**：它们断言的是旧链路的取证口径，
按产物分类属"历史证据档案"，改写等于伪造历史；需要时按新口径新立判据。

## 参考

- 契约：[#hard-constraints](0020-package-boundaries-and-runtime-topology.md#hard-constraints) /
  [#execution-port](0020-package-boundaries-and-runtime-topology.md#execution-port) /
  [#messages](0020-package-boundaries-and-runtime-topology.md#messages) /
  [#params](0020-package-boundaries-and-runtime-topology.md#params)
- 上游表示：[ADR-0035](0035-perception-map-representation-and-unknown-policy.md#top)（地图表示与
  unknown 策略）、[ADR-0040](0040-perception-multi-resolution-evidence-and-planning-layers.md#top)
  （证据层 / 规划层）、[ADR-0041](0041-geometry-metadata-instances-and-risk-map.md#top)（风险分档）、
  [ADR-0042](0042-point-uncertainty-arbitrary-resolution-and-reachability.md#top)（逐格元数据）
- 安全口径：[ADR-0010](0010-safety-thresholds-and-failsafe.md#top)（档位顺序不变量、末端失效停车、
  不可行率诚实口径）、[ADR-0004](0004-ground-control-rl-primary-and-nav2-safety.md#top)（分层与非变量）
- 规范：[地面安全层判定与标定](../conventions/地面安全层判定与标定.md#top)、
  [测试分层与可测性](../conventions/测试分层与可测性.md#testable)、
  [路线分支治理](../conventions/路线分支治理.md#rule)
