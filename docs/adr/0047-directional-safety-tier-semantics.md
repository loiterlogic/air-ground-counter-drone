<a id="top"></a>
# 地面安全层的**方向化**定档：`d_collision` 保留数值，取消"圆形禁行区"语义

## Status

accepted（2026-11-13，用户裁定并给出方案）

> **不取代任何既有安全阈值**：[ADR-0010](0010-safety-thresholds-and-failsafe.md#top) 的三档**绝对值**
> （`1.0 / 2.0 / 4.0 m`）与**顺序不变量**不变；[ADR-0046](0046-lateral-escape-capability-narrowing.md#top)
> 的 `max_offset = 0.65 m`、`T = 2.0 s`、`slow_min_ratio = 1.0` 不变；
> [ADR-0045](0045-ground-safety-layer-self-owned.md#top) 的输入契约、判定顺序、失效语义不变。
>
> **本篇改变的是 `d_collision` 等距离量的「度量对象」**，不是它们的数值：
> 从「车周围 N 米内有任何障碍就停」（各向同性圆形禁行区）改为
> 「沿当前运动方向、车体宽度带内，进入障碍前够不够停」。停车保证**不放宽**。
>
> **不在本篇范围**：真正的全局路径规划（B′ 主链：全局路径参数化 + 局部滚动时域细化）
> 仍未实现，属 [ADR-0032](0032-pending-directions.md#top) 方向 2 与 `docs/plan/` 的主链任务。
> 本篇**不**改占位规划器 `placeholder_path_planner` 的行为（它仍是几何直连）。

## 背景

2026-11-13 的 `dense_map` 排查得出一条**被误读的事实链**，必须先把它拆开：

| 观察 | 当时的读法 | 实际 |
|---|---|---|
| `dense_scene` 20 次实跑 `TRACKING_SUCCESS` = **0/20** | 「地图太密，车过不去」 | **错** |
| `ticks_triggered` 5,420–7,176（几乎每拍都触发） | 「安全层在正常工作」 | 对，但**触发原因是误报** |
| `clearance_min_m` 稳定 1.66–1.74 m | 「车真的贴近障碍了」 | 对，但那是**侧方**净空 |

实测几何（`dense_map`，486 实体，真实 OBB 几何）直接证伪了「太密」：

| 量 | 值 |
|---|---|
| 面积覆盖率 | **7.2%**（354.6 m² / 4900 m²） |
| 相邻障碍边缘间隙 p50 | **4.54 m** |
| 最小边缘间隙 | **0.99 m** |
| 车宽 | **0.57 m** |
| 间隙 ≥ 1.0 m 的相邻对占比 | **100%** |

⇒ **通道本来就在**。真正的原因在判据本身：

`tierFromGeometry` 的 `d` 是「车体外缘到**任意方向**最近阻挡格」，**方向完全不参与判定**。
后果：侧面 2 m 外的柱子，即使车正笔直沿走廊走、永远不会碰到它，也会被判 `STOP_COLLISION`
→ 零速。出生点 `(-34,-6)` 的车心净空只有 **1.75 m**，扣车体半对角 0.58 m ⇒ `d ≈ 1.17 m` < 2.0
⇒ **一启动就是停车档，车一步都不动**。这不是"规划器找不到路"，是"安全层不让走"。

ADR-0044 早已如实登记过征兆（"把 gap 加到 3.6 m，车中心沿直连 goal 的最大净空仍只有约 1.5 m"），
但当时把它归因成"间距还不够"，没有识别出**判据是各向同性**这一层。

## 决策

### (a) 定档改用**方向化走廊净空**，`d_collision` 数值与停车保证不变

新增 `SweepResult::d_corridor_m` / `SafetyDiagnostics::d_corridor_m`：**只量**「沿当前运动方向、
车体宽度带内（`|横向偏移| ≤ footprint_half_width + cell_epsilon`）」的纵向间隙。

| 量 | 改造前 | 改造后 |
|---|---|---|
| 定档输入 | `d_min_m`（各向同性最近距离） | `d_corridor_m`（运动方向走廊净空） |
| 侧方 2 m 内障碍 | **停车** | 不参与定档 |
| 前方 2 m 内障碍 | 停车 | **停车**（不变） |
| 原地旋转扫到车角 | 停车 | **停车**（不变，走 `swept_blocked`） |
| 转向扫到侧方 | 停车 | **停车**（不变，走 `swept_blocked`） |

四条口径必须同时成立，缺一即回到"用安全性换通行率"：

- **前方按运动方向量**：`d_corridor` 只取 `u·sign(v) > 0` 那一侧，倒车时车头前的障碍**不算**前方。
- **侧方只经扫掠生效**：`evaluateSweep` 本来就沿**实际制动轨迹**扫掠（含 `ω` 引起的偏航变化），
  所以"当前转向会不会扫到侧方障碍"已由 `swept_blocked` 覆盖。本次**没有**新增扫掠逻辑，
  只是**停止**用各向同性距离额外判一次停车。
- **原地旋转用全向限速、不用全向停车**：`v≈0 ∧ w≠0` 时没有运动方向，距离档退化为各向同性
  **只用于限速**（`SLOW`），**不得**据此判停车 —— 停车由旋转扫掠兜。
  这一条防的是"原地转向时侧方 2 m 内有柱子就零速，而车根本没在平移"。
  也**不**一律返回 `SLOW`：那会在开阔区旋转时污染 `ticks_triggered` / `shield_infeasible_rate` 口径。
- **静止（`v≈0 ∧ w≈0`）退化为各向同性**：没有运动方向时按最近距离判，保持既有判定表
  （`EmergencyBandStops` / `RecoveryRequiresHysteresisTicks` / `RecoveryResetsWhenConditionBreaks`
  三条既有用例守此）。

### (b) 走廊带内**无阻挡**时，距离档一律不成立（不得退化回各向同性）

`d_corridor_m < 0` 表示"运动方向、车体宽度带内没有任何阻挡" ⇒ 前方净空为**无穷**，
`emergency / collision / slow` 三个距离档都不成立。

这一条是本次变更的**关键实现点**，也是第一次实现时写错的地方：若在 `d_corridor < 0` 时
"退化去用各向同性的 `d_min_m`"，侧方 1.2 m 外的柱子照样会把车判成停车档 —— **变更等于没做**。
实测证据（第一次实现的单测输出）：穿缝用例报 `corridor d=0.866 < emergency`，而 `0.866`
正是**侧方**障碍的各向同性距离。

### (c) SLOW 裁剪比例与恢复迟滞同口径改用 `d_corridor`

- **SLOW 比例**：`ratio = (d_corridor - d_collision) / (d_safety - d_collision)`，走廊无阻挡时
  `ratio = 1.0`（不因侧方障碍降速）。
- **恢复门槛**：`d_recover_pass` 也按 `d_corridor` 判，否则侧方障碍会把车**永久钉在降级态**。

### (d) `dense_map` 车出生位 `(-34,-6)` → `(-40,-6)`

旧出生位的车体外缘净空只有 **1.06 m**，小于 `d_collision = 2.0 m` ⇒ 一启动即停车档。
这**不是判据能修的**：出生位本身就在禁行区里，任何判据都只能判它停。

新出生位实测（规划层 0.5 m 栅格，朝 goal 方向）：

| 量 | 值 | 判据 |
|---|---|---|
| 安全层走廊净空 | **4.55 m** | ≥ `d_collision = 2.0 m` ✓ |
| 车↔目标 | 40.45 m | ≥ 30 m（ADR-0036 设计目标）✓ |
| 己方机↔目标 | 34.06 m | ≥ 25 m ✓ |
| 车↔己方机 | 7.21 m | ∈ [3,8] m ✓ |

出生位仍**随地图派生**（ADR-0036），`spawn_layout.yaml` 是唯一来源。

### (e) 几何前置闸门：出生位不得落在碰撞档内（新增守护）

`test_dense_map_spawn_is_not_inside_collision_tier` 断言：

```text
车心到最近障碍足迹的距离 − 车体半对角 > d_collision + margin_m
```

- 障碍按**真实几何**（box 有向矩形 / cylinder 圆），**不**按外接圆膨胀
  （外接圆会把长条 box 放大 3 倍以上，造出"必须移出生位"的假阳性）。
- 取**半对角**是最保守下界（任意朝向都成立）⇒ 下界过门槛则任何朝向都过。
- 已用**变异测试**验证它会真红：把出生位改回 `(-34,-6)` 时断言失败（`1.06 m <= 2.14 m`）。

**为什么必须有这条闸门**：出生位是**配置**，改它不需要改代码，也没有任何既有断言覆盖
"它与安全层阈值是否自洽"。这次缺陷正是这样产生的 —— 配置合法、启动不报错、
现象却是"车一步都不动"，且被误读成"地图太密"。

## 不做什么

- **不**把 `d_collision` 从 2.0 m 降到 1.0 m。那会破坏已标定的安全停车保证，
  只是用安全性换通行率 —— 用户明确否掉。
- **不**改 `d_emergency` / `d_safety` 的绝对值，**不**改三档顺序不变量。
- **不**让安全层订阅第二份障碍数据（`scan` / 点云 / `costmap` / 真值几何）。
- **不**改占位规划器的行为：真正的全局路径规划**仍未实现**（见下"未决"），
  本篇不越界去占位器里塞一个简化版规划器。
- **不**改 `dense_map` 的间距 / 实体数 / 撒点区（ADR-0044 的结论不变）。
- **不**在场景层覆盖出生位（ADR-0036 的"单一来源"不变）。
- **不**改 `dense_scene` 的 `expected_terminal`（见"未决"）。

## Considered Options

- **全局把 `d_collision` 从 2.0 降到 1.0 m** —— 被否（用户原话）：
  「那会破坏已经标定的安全停车保证，只是用安全性换通行率」。
- **只移出生位、不改判据** —— 被否：出生位只是**一个点**的问题。判据的各向同性语义
  会让车在任何"侧方有障碍"的走廊里都停（`dense_map` 里这种位置到处都是），
  移完出生位车仍然出不去。
- **在占位规划器里实现"间隙选择"（BFS + footprint 膨胀）** —— **已实现并已回退**。
  回退理由：①它既不是 B 样条参数化、也没有滚动时域细化，与主链方向不符，留着会被误读成主链；
  ②它漏了 [ADR-0035](0035-perception-map-representation-and-unknown-policy.md#top) (g) 的
  「终点在未知区走直连兜底」契约，在 `dense_map` 上 19/19 规划失败、车一步不动
  （goal 距己方机 31.56 m > 感知可信半径 28.9 m ⇒ goal 恒在未知区）；
  ③全局路径规划属主链任务，不属本次前置。**如实登记为失败尝试**，不留在代码里。
- **安全层改消费 0.25 m 证据层以分辨 0.99 m 的缝** —— 被否（本轮）：单帧从 40 KB 涨到
  160 KB（4 倍带宽），且要重做 ADR-0040 的分层结论。验收下限按用户裁定取「≥1.5 m 间隙」，
  并把「<1.5 m 的缝在 0.5 m 规划层上不可分辨」登记为已知边界。
- **原地旋转时一律返回 `SLOW`** —— 被否：会在开阔区旋转时污染
  `ticks_triggered` / `shield_infeasible_rate` 口径（那是"安全层介入"的代理量）。

## Consequences

### 正面

- **误停被消除且可判定**：`dense_map` 出生点的走廊净空从 `0.11 m`（各向同性）
  变为 `1.40 m`（方向化，旧出生位）/ `4.55 m`（方向化 + 新出生位）。
- **停车保证不放宽**：前方 / 转向 / 原地旋转三条危险路径仍停车，各有单测守护
  （`FrontalObstacleWithinCollisionRangeStillStops` / `PureRotationIntoNearbyObstacleStillStops` /
  `CorridorFollowsMotionDirectionNotHeading` / `PassingThroughGapDoesNotStopOnFlankingObstacles`）。
- **安全层仍完全脱 ROS 可单测**：`safety_policy.hpp` 由 38 项增至 **46 项 gtest**。
- **出生位与安全阈值的不自洽被闸门挡住**，且闸门经变异测试证明会真红。

### 实测证据（2026-11-13）

**离线核查**（`tests/check_safety_directional_corridor.py`，真实 `dense_map` 几何 →
规划层 0.5 m → 喂**生产判定类**）：5/5 通过。

| 用例 | 状态 | `d_corridor` |
|---|---|---|
| 旧出生位 `(-34,-6)` 朝 +x | **STOP_COLLISION**（正确：它在禁行区内） | 1.393 |
| 新出生位 `(-40,-6)` 朝 +x | **PASS** | −1（带内无阻挡） |
| 新出生位朝 goal | **PASS** | 4.031 |
| 新出生位原地旋转 | **PASS**（不误停） | −1 |

**整链实跑**（`experiments/w5-ground-nav-safety/20261113-dense-dir-safety-1`，
`dense_scene` + `backend:=full` + headless）：

| 项 | 值 |
|---|---|
| 出生位 | `(-40,-6)`（日志实证 `spawn car=(-40.0,-6.0,...)`） |
| 终态 | `MISSION_FAILED / TIMEOUT`（`expected_match=True`） |
| `collision_count` | **0**（没有撞） |
| 安全层状态迁移 | `NO_PERMIT → STOP_EMERGENCY → STOP_COLLISION → SLOW → STOP_COLLISION` |

**如实解读（不得夸大）**：

- `SLOW` 出现过 ⇒ 车**确实被放行过**，方向化判据没有把它钉死在停车档。
  改造前（各向同性 + 旧出生位）的 20 次实跑里，`clearance_min_m` 稳定 1.66–1.74 m、
  `ticks_triggered` 5,420–7,176 —— 那是**持续误报**的形态。
- 但车**仍然没有到达**：`STOP_COLLISION` 最终把它截住。原因是**几何直连路径穿障**
  （`placeholder_path_planner` 只发直线，ADR-0013 (l)），不是安全层判错。
  **「能到达」要等主链规划器落地**，本篇不宣称。
- 本轮 `ticks_triggered = 4337 / 5452` 仍偏高，主要是 `BODY_INVALID` 抖动
  （`ground_odom_adapter` 的微秒级负年龄，ADR-0046 已登记）与穿障停车叠加，
  **不是**方向化判据的误报。

### 代价 / 限制（如实登记，不得据此宣称能力）

- **`d_corridor` 是"当前运动方向"的量**：车在**高速急转**时，走廊带取的是当前朝向，
  而车体实际会扫过更宽的区域。这一点由 `swept_blocked`（制动轨迹扫掠，含 ω 偏航）兜住，
  但**不是**由走廊判据兜住的 —— 不得表述为"走廊判据覆盖转向扫掠"。
- **走廊带是矩形近似**：`|横向偏移| ≤ half_width + cell_epsilon` 是常值带，
  不随车的横向速度收窄。横向漂移大时仍可能有少量低估。
- **0.5 m 规划层分辨不了 < 1.5 m 的缝**：栅格化 + max-pool 会让 0.99 m 的物理缝
  在规划层上只剩 0–1 格，而车宽 0.571 m 装不进 1 格。用户裁定验收下限为
  「≥1.5 m 间隙」；**1.0–1.5 m 的缝属未覆盖区间**，不得据此宣称"能穿 1 m 缝"。
- **方向化只解决"能走"的一半**：判据修好后车**不会**再被误停，但占位规划器仍只发
  **几何直连**（ADR-0013 (l)），在 `dense_map` 上直线穿障 ⇒ **车仍到不了**。
  「能到达」要等主链规划器落地。不得把本篇读成"`dense_map` 上能通行了"。
- **历史 run 的出生位与新 run 不可逐值对照**：`dense_scene` 的 `clearance_min_m` /
  `intervened_ticks` 在出生位变更前后含义不同，引用时须标注。

### 未决（不得靠默认值掩盖）

| # | 未决项 | 归宿 |
|---|---|---|
| 1 | ~~**全局路径规划仍未实现**~~ —— **已实现**（[ADR-0048](0048-ground-hybrid-astar-se2-planner.md#top)，2026-11-14）：`hybrid_astar_se2_planner` 接替占位器 | 已闭合 |
| 2 | `dense_scene` 的 `expected_terminal: MISSION_FAILED` 何时改为 `TRACKING_SUCCESS` | 主链落地任务（依赖 #1） |
| 3 | 是否把安全层改消费 0.25 m 证据层（换取分辨 < 1.5 m 缝的能力） | 新决策；须重做 ADR-0040 的分层结论 |
| 4 | 「边缘直连兜底」（ADR-0035 (g)）在**自研规划器**下的实现 —— **已定**（ADR-0048 (g)）：搜索到已知区前沿后直连 goal，末端恒为 goal，且直连段必须不碰不可压档 | 已闭合 |

## 参考

- 安全口径：[ADR-0010](0010-safety-thresholds-and-failsafe.md#top)（三档顺序不变量）、
  [ADR-0045](0045-ground-safety-layer-self-owned.md#top)（输入契约与失效语义）、
  [ADR-0046](0046-lateral-escape-capability-narrowing.md#top)（能力主张收窄、`slow_min_ratio = 1.0`）
- 规划口径：[ADR-0013](0013-ground-planning-path-contract.md#top)（路径契约与质量门，占位器形态）、
  [ADR-0035](0035-perception-map-representation-and-unknown-policy.md#top) (g)（未知空间策略与直连兜底）、
  [ADR-0032](0032-pending-directions.md#top)（"小车地图全局规划"方向）
- 地图与出生位：[ADR-0036](0036-dense-obstacle-map-and-per-map-spawn.md#top)（按地图派生出生位）、
  [ADR-0040](0040-perception-multi-resolution-evidence-and-planning-layers.md#top)（0.25 / 0.5 m 分层）、
  [ADR-0044](0044-dense-map-second-gap-widening.md#top)（间距 2.645 m、486 实体）
- 规范：[地面安全层判定与标定](../conventions/地面安全层判定与标定.md#top)、
  [测试分层与可测性](../conventions/测试分层与可测性.md#testable)
- 实现：`src/agc_ground/include/agc_ground/safety_policy.hpp`（方向化定档）
- 判据：`src/agc_ground/test/test_safety_policy.cpp`（46 项）、
  `src/agc_task/test/test_scene_config_invariants.py::test_dense_map_spawn_is_not_inside_collision_tier`
