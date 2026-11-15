<a id="goal"></a>
## 目标

在三项前置均已完成的基础上，落地地面侧第一条可运行、可单测、可回放、可取证的全局规划算法链。算法思想吸收 Fast-Planner 的三段式结构：先搜索安全且动力学可行的粗路径，再做离障和平滑优化，最后做时间参数化与动力学复核；但将四旋翼三维模型重建为差速小车的二维 SE(2) 规划问题。

最终链路为：

```text
/agc/map + /agc/map/valid + odom + goal + task state
  → 地图快照/未知策略/footprint 视图
  → 差速车运动基元搜索（Hybrid A* 风格）
  → 路径回溯与解析连接
  → 二维距离场 + 三次 B 样条/弹性带优化
  → 曲率/速度/角速度/加速度约束
  → 弧长时间参数化
  → 连续 footprint 扫掠最终复核
  → /agc/ground/path
  → 既有路径消费者
  → cmd_vel_raw → ground_safety_filter → 唯一执行口
```

本轮的成功定义不是“全局最优”，而是：在明确的地图、车体、目标和时间预算下，稳定地产生真实差速车可执行且通过 footprint 复核的路径；找不到路径时可解释地失败并停车。

<a id="scope"></a>
## 实施边界

### 1. 现有工程接入边界

- 替换 `src/agc_ground/src/placeholder_path_planner.cpp` 的占位直连职责；不得在其旁边再起第二个主规划器，也不得增加 `planner_mode` / `planner_backend` / `path_source` 等运行时路线开关。
- 规划器继续由 `src/agc_ground/launch/ground_bringup.launch.py` 统一启动，继续发布唯一的 `/agc/ground/path`；消息类型保持 `nav_msgs/Path`，`header.frame_id` 固定为 `world`。
- 输入固定为：
  - `/agc/map`：唯一规划障碍输入，`nav_msgs/OccupancyGrid`；
  - `/agc/map/valid`：地图知识新鲜/有效性；
  - `/agc/ground/odom`：车体位姿和当前速度；
  - `/agc/ground/goal` 与 `/agc/ground/goal_info`：目标位置和目标有效性；
  - `/agc/task/state`：任务授权状态。
- 规划器只发布路径和非命令型诊断，不发布 `/agc/ground/cmd_vel_raw`、`/agc/ground/cmd_vel` 或 Gazebo 速度话题。速度仍由既有局部消费者、安全层和唯一执行口链路产生。
- 路径绑定、地图签名、重规划触发、路径过期、无效即停车沿用 [ADR-0013](../adr/0013-ground-planning-path-contract.md#top)。本轮不修改冻结消息 ABI、任务终态、安全层判据或 RL 的 obs/action 维度。

### 2. Fast-Planner 迁移边界

只迁移以下方法思想：

| 论文模块 | 本项目实现 | 不直接照搬的部分 |
|---|---|---|
| 动力学路径搜索 | 差速车 SE(2) 运动基元的 Hybrid A* 风格搜索 | 四旋翼三维状态与三维控制 |
| 离障优化 | 二维占据栅格距离场 + 控制点斥力 | 三维 EDF / 点云梯度 |
| B 样条优化 | 二维三次 B 样条或等价弹性带控制点优化 | 飞行器 snap/thrust 约束 |
| 时间调整 | 基于曲率、线/角速度、线/角加速度的弧长速度规划 | 四旋翼非均匀节点的原式推导 |
| 滚动规划 | 地图/目标/车位绑定失效或周期到达时重规划 | 未知空间探索式飞行重规划 |

不得把本方案描述为论文算法的代码移植；它是将论文的“搜索—优化—时间调整”架构重新建模为地面差速车规划器。

### 3. 地图、未知和碰撞口径

- `/agc/map` 的规划层值按现有 `planning_policy.hpp` 语义处理：`0 = 已知自由`，`1..99 = 证据不足/未知`，`100 = 已知占据`，负值也按未知处理。
- 新规划器中，未知格一律不可进入、不可穿越、不可作为安全路径的一部分；不能调用或复用基线专用的“已知边缘到目标直连”作为新规划器的隐式兜底。目标或起点不满足已知自由条件时，产生明确失败原因。
- 碰撞不能只检查车体中心点或运动基元终点。每个基元的离散采样姿态都要将真实车体 footprint 变换到地图中，并检查整个 footprint 是否接触占据/未知格。
- 规划余量不复用安全层的 `d_collision=2.0 m`。规划余量由 footprint 几何、地图半格量化误差、定位误差、路径跟踪误差和必要的最小离障要求组成；具体数值必须经回放和动力学实验确定。
- `dense_map` 的窄缝判定必须以 footprint 扫掠为准，不能用“最近障碍距离大于 2 m”替代通行性判断。优化后的曲线必须再次连续采样并做 footprint 复核。

### 4. 纯算法模块与数据结构

新增模块应放在 `src/agc_ground/include/agc_ground/` 与 `src/agc_ground/src/`，核心逻辑不依赖 ROS 消息，便于 gtest 和离线回放。建议模块如下：

```text
planner_types.hpp          # 纯数据结构、枚举、规划结果和诊断
occupancy_grid_view.hpp    # 从 OccupancyGrid 转成只读规划视图
footprint_checker.hpp      # 车体 footprint、姿态变换、栅格碰撞/扫掠
motion_primitive.hpp       # 差速车 v/ω 基元与离散采样
distance_field_2d.hpp      # 已知占据到自由格的二维距离场
kinodynamic_search.hpp     # OPEN/CLOSED、剪枝、启发式、回溯、解析连接
spline_optimizer_2d.hpp    # 控制点、平滑/离障/曲率优化
path_time_parameterizer.hpp# 曲率、速度传播、加速度和角速度检查
planner_engine.hpp         # 四阶段编排，输出纯 PathResult
```

核心数据至少包括：

```text
GridView:
  frame, resolution, origin, width, height, cells, map_stamp, map_signature

Pose2D:
  x, y, yaw

MotionState:
  pose, linear_velocity, angular_velocity

Primitive:
  start_state, control(v, omega), duration, sampled_poses, length, cost

SearchNode:
  state, discrete_key(x_cell, y_cell, yaw_bin), g, h, f, parent, primitive_id

PathResult:
  success, failure_reason, poses, curvature, speed_profile,
  planning_time, expanded_nodes, clearance_min, map_signature
```

### 5. 阶段 A：地图快照与规划前检查

每次需要规划时先复制一个不可变地图快照，规划期间不读取正在被 ROS 回调修改的数组。按以下顺序检查：

1. `/agc/map` 已收到且尺寸、分辨率、原点、frame 合法；
2. `/agc/map/valid=true` 且地图年龄未超过规划器地图超时；
3. odom、goal、goal_info、task state 均满足现有新鲜度和授权语义；
4. 起点和目标均在地图边界内；
5. 起点和目标中心格为已知自由；
6. 起点与目标的完整 footprint 均不与占据/未知格相交；
7. 对目标姿态缺失的情况，使用目标方向或最后一段路径方向生成候选终端航向，但不得静默改变既有 goal 语义；
8. 任一步失败都返回显式 `PlanFailure`，本拍不发布新可用路径。

建议的失败枚举：

```text
NO_MAP, MAP_INVALID, MAP_STALE, FRAME_MISMATCH,
NO_ODOM, NO_GOAL, GOAL_INVALID, NOT_AUTHORIZED,
START_OUT_OF_MAP, START_NOT_FREE, START_COLLISION,
GOAL_OUT_OF_MAP, GOAL_NOT_FREE, GOAL_COLLISION,
SEARCH_EXHAUSTED, SEARCH_TIMEOUT, NO_ANALYTIC_CONNECT,
OPTIMIZATION_FAILED, OPTIMIZED_PATH_COLLISION,
DYNAMICS_INFEASIBLE, VALIDATION_FAILED
```

### 6. 阶段 B：差速车运动基元搜索

第一版采用二维差速运动模型：

```text
x_dot   = v cos(yaw)
y_dot   = v sin(yaw)
yaw_dot = omega
```

每个节点扩展一组离散控制输入。具体离散值不能直接写成契约，先作为配置参数并在回放中标定；建议初始候选为：

```text
v     ∈ {0.3, 0.6, 1.0, 1.5} m/s
omega ∈ {-2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0} rad/s
```

第一版默认只搜索前进基元；倒车必须等控制链和验收口径确认后再加入，不通过隐式参数开关在同一主链保留两套实现。

基元生成要求：

- 固定持续时间 `primitive_dt`，对每个基元按最大空间步长采样，不能只检查终点；
- 对 `omega=0` 使用直线积分，对非零 `omega` 使用圆弧解析积分或足够小步长积分；
- 每个采样姿态执行 footprint 碰撞检查；任一采样点落入未知或占据即拒绝；
- 检查基元末端是否超出地图边界；
- 记录长度、时间、转向量、最小离障距离，用于代价和诊断。

搜索状态离散为：

```text
key = (floor((x-origin_x)/resolution),
       floor((y-origin_y)/resolution),
       yaw_bin)
```

同一 `(x_cell, y_cell, yaw_bin)` 只保留当前 `g` 最小的节点；不能只按 `(x,y)` 合并，否则会错误丢弃同位置不同航向的可行状态。

建议代价：

```text
g_edge = w_time * duration
        + w_length * primitive_length
        + w_turn * abs(omega) * duration
        + w_clearance * clearance_penalty
```

启发式第一版使用欧氏距离加航向误差；后续可替换为 Dubins 距离，但不把该优化作为首条链的前置依赖。搜索循环必须有：

- OPEN 最小 `f=g+h` 弹出；
- CLOSED / 更优 g 值更新；
- 最大扩展节点数和墙钟时间预算；
- 目标位置容差与终端航向容差；
- 每次扩展的父节点和基元记录，支持确定性回溯。

### 7. 阶段 C：解析连接与路径回溯

每次弹出节点后按成本较低的顺序尝试：

1. 当前状态到目标的直线/圆弧连接；
2. 由有限转弯半径组成的 Dubins 风格连接；
3. 连接全程做 footprint 扫掠、未知检查、曲率和角速度检查。

只有整段通过才提前结束搜索；解析连接失败时继续扩展普通基元。搜索成功后从终点沿 parent 回溯，反转为起点到目标顺序，删除重复点并按弧长重采样。不能直接把栅格节点中心连成折线后交给消费者，因为那会产生差速车无法执行的尖角。

### 8. 阶段 D：二维距离场与 B 样条/弹性带优化

距离场只由已知占据格生成；未知格不能作为自由空间距离场的安全来源。可先使用二维 BFS/欧氏近似距离场，后续再替换为精确 EDT，不改变接口。

优化流程：

1. 将搜索路径按弧长重采样；
2. 删除冗余共线点；
3. 固定起点、终点以及必要的边界切向方向；
4. 生成三次 B 样条控制点；
5. 只优化内部控制点；
6. 每轮计算平滑、离障、曲率和长度代价；
7. 采用固定最大迭代数和墙钟预算；
8. 优化结束后对曲线密集采样，重新做 footprint 扫掠；
9. 任一碰撞、未知、曲率或数值异常即放弃优化结果，使用本次搜索得到的原始可行路径；
10. 若原始路径也不满足最终验证，则整次规划失败，不能使用上一轮旧路径。

建议目标函数：

```text
J = lambda_smooth    * Σ||Q[i+1]-2Q[i]+Q[i-1]||²
  + lambda_clearance * Σ max(0, clearance_target-d(Q[i]))²
  + lambda_curvature * Σ max(0, |kappa[i]|-kappa_max)²
  + lambda_length    * path_length
  + lambda_heading   * terminal_heading_error²
```

B 样条优化只是质量改善，不是安全证明。安全证明来自最终密集采样的真实 footprint 检查。

### 9. 阶段 E：时间参数化与动力学复核

`/agc/ground/path` 仍是几何路径；时间参数化第一版作为规划内部结果和诊断，不立即扩展消息 ABI。

对最终路径按弧长采样，计算每个点曲率 `kappa`。速度上限取：

```text
v_i <= v_cap
v_i <= sqrt(a_lat_max / max(abs(kappa_i), epsilon))
v_i <= w_cap / max(abs(kappa_i), epsilon)
```

再进行前向/后向传播：

```text
v_forward[i+1] = min(v_limit[i+1],
                     sqrt(v_forward[i]^2 + 2*a_acc*ds))

v_backward[i] = min(v_forward[i],
                    sqrt(v_backward[i+1]^2 + 2*a_brake*ds))
```

最后计算 `omega = kappa * v`，检查线速度、角速度、线加速度、角加速度均不超限。若无法得到可行速度剖面，返回 `DYNAMICS_INFEASIBLE`，不能只降低安全层阈值来“挤过”路径。

### 10. ROS 节点编排

节点 tick 只负责输入快照、触发判定和发布，不把搜索细节写进 ROS 回调。建议结构：

```text
on_map() / on_odom() / on_goal() / on_goal_info() / on_state()
    → 仅更新带时间戳的输入缓存

tick()
    → fresh/authorized/needReplan
    → snapshotInputs()
    → PlannerEngine::plan(snapshot)
    → 结果验证
    → 成功发布整条 Path 并更新绑定
    → 失败清除 path_valid，发布诊断并持续 fail-stop
```

不得在地图回调里直接规划，避免地图发布线程被搜索阻塞。规划器需要记录：

```text
plan_seq, map_signature, goal, start_pose,
result, failure_reason, planning_time_ms,
expanded_nodes, raw_path_points, final_path_points,
clearance_min, max_curvature, replan_reason
```

可先用现有非命令型 `std_msgs/String` 诊断话题承载 JSON，不新增消息 ABI；若字段稳定后再另立接口决策。

### 11. 构建与文件落点

- 在 `src/agc_ground/CMakeLists.txt` 中为纯算法单测增加 `ament_add_gtest`，纯算法头文件不链接 ROS；
- 规划节点作为单一可执行目标安装到 `lib/agc_ground`，替换占位目标的 launch 引用；
- 配置放入现有 `src/agc_ground/config/ground.yaml` 的规划器段，由既有 launch 单一注入；不新增顶层契约参数清单；
- 不复用 `ground_baseline` 的 Nav2 costmap 作为主链运行时规划器；baseline 继续只是离线对照臂；
- 不修改 `planning_policy.hpp` 的现有未知分类语义。新规划器内部应直接使用相同分类函数或等价纯逻辑，避免规划层出现第二套未知口径。

### 12. 测试与取证分层

纯单测至少覆盖：

1. 栅格坐标转换、边界、frame、分辨率和地图快照；
2. `0/-1/1..99/100` 分类及未知拒绝；
3. 矩形 footprint 在直行、转弯、原地旋转中的碰撞；
4. 运动基元解析积分和采样密度；
5. 同一离散 key 的剪枝；
6. 启发式单调性和搜索回溯；
7. 直连成功、直连穿障失败、目标航向不满足失败；
8. 单障碍绕行和无解地图；
9. 距离场、离障代价和平滑代价；
10. 优化后穿障被最终复核拒绝；
11. 曲率、速度、角速度、加速度约束；
12. 规划超时、节点上限、地图失效、目标失效的失败分类；
13. 相同输入、seed 和参数下路径与诊断可复现。

整链至少取证：

- 空旷地图直达；
- 单障碍绕行；
- `dense_map` 多障碍绕行；
- 约 `0.99 m` 间隙的 footprint 可行性；
- 不可达目标和起点/目标占据；
- 地图 stale / unknown；
- 规划成功后地图签名变化触发重规划；
- 规划失败后不沿用旧路径且车辆经安全层停车；
- GUI 中同时看到 `/agc/map` 和 `/agc/ground/path`，并验证车辆确实通过既有路径消费者运动；
- 记录 backend、seed、规划耗时、规划次数、路径长度、最小离障、最大曲率、失败原因和最终终态。

超时一律失败；GUI 证据与 headless 规模统计不得混写，分别标注 backend/mode。

### 13. 明确不做与风险控制

- 不做全局最优性或完备性承诺；离散基元、剪枝和时间预算决定的是工程可行性，不是理论保证。
- 不把安全层改造成规划器；安全层仍只裁剪/归零速度，不主动绕行。
- 不把规划器的路径消费证据写成 RL 已具备局部避障能力；路径传输、确定性消费和 RL 训练能力分开验收。
- 不使用 `d_collision=2.0 m` 作为全向规划膨胀半径。
- 不把未知格当自由，不通过过滤障碍或修改地图来制造可行路径。
- 不在优化失败时静默使用旧路径或几何直连。
- 倒车、精确 Dubins/Reeds-Shepp、速度剖面进入 Path 消息、动态障碍预测均留待后续独立决策，不在第一条链中静默加入。

<a id="exit"></a>
## 出口判据

- 纯算法库、节点和配置均能构建；核心算法不依赖 ROS，可由 gtest 和离线回放直接验证。
- 规划成功时：起点/终点绑定有效，路径 frame 正确，路径所有采样姿态通过 footprint 碰撞和未知格检查，动力学复核通过，且 `/agc/ground/path` 由唯一规划器发布。
- 规划失败时：有明确失败枚举和诊断，不发布新的可用旧路径，不隐式直连；既有路径消费者最终输出零速，经安全层和唯一执行口停止。
- `dense_map`、单障碍、窄缝、不可达、地图失效、重规划绑定等场景均有离线判据和至少一项整链证据。
- 真实运行证据能同时证明地图被规划器消费、路径被既有消费者消费、速度未绕过安全层、GUI 下车辆按规划路径运行。
- 稳定结论归入 ADR/工程规范/测试后，按 [任务计划规则](README.md#plan-index) 删除本计划文件；未定参数在定标前不得写成永久契约。

<a id="deps"></a>
## 依赖与并行

- 三项前置已完成：感知地图传递链、安全层判定与新预注册均已有用户确认的完成状态；因此本任务允许修改 `src/`，但仍须对每次真源变更跑对应测试。
- 顺序依赖不可交换：纯数据模型与碰撞核验 → 搜索与离线回放 → 优化/时间参数化 → ROS 节点接入 → 路径消费和安全层回归 → GUI/规模实验 → 永久归档。
- 纯算法单测、距离场和文档整理可以并行；ROS 整链 GUI/仿真资源独占，不能与其它会改地图、车体或安全层参数的任务并行。
- 规划器与安全层继续消费同一 `/agc/map`，不创建第二份静态障碍真源，不订阅 scan/点云/costmap 作为规划安全替代输入。
- 外部规划器四项接口未决不阻塞本轮仓内首条链；后续算法只能通过既有 `/agc/ground/path` 接入缝另立任务确认。
- 运动基元离散集与步长、规划余量、优化预算、是否支持倒车、是否把速度剖面加入路径接口，均属于待标定实现参数；在回放与真实动力学证据完成前不得宣称最优、完备或已支持倒车。
