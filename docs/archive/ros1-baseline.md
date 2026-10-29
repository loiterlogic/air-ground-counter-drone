<a id="top"></a>
# ROS1 基线盘点（历史归档）

> **历史归档（2026-10-29 起）**：本文原为契约真源《ROS2 交接文档》的**附录 A**，是迁移前 ROS1(Noetic) 系统的盘点记录。
> **它是历史，不是约束**：只供对照旧系统行为，**不作为代码或规范来源**；契约约束见 [ROS2迁移交接文档](../ROS2迁移交接文档.md#hard-constraints)。
> **归档原因**：历史与活约束混在同一真源里，导致每次开工都读到历史（[P0-3](../plan/p0-3-文档瘦身与入口重构.md#p0-3-goal)）。锚点 `#appendix-a` 在原契约文件留导航兼容。
> **注**：下文命令、路径与版本号是**当时事实**，不追溯改写。

---

<a id="appendix-a-archived"></a>
## 盘点正文（原「附录 A」，非约束）

> **免责**：仅供 W8 行为对照，**不作为代码或规范来源**。

### A.1 运行环境（迁移前）

| 项 | 现状 |
|---|---|
| 操作系统 | Ubuntu 20.04.6 LTS (focal) |
| ROS 发行版 | ROS1 Noetic |
| 构建系统 | catkin_tools（产物 `build/`、`devel/`） |
| 仿真平台 | Gazebo Classic（仓库内 vendored `gazebo_ros_pkgs`） |
| 飞控仿真 | PX4 SITL（机型 `iris_3d_lidar`） |
| 中间件 | MAVROS（`/mavros/*`） |
| 时钟 | 全局 `/use_sim_time=true` |
| 语言分布 | C++ 约 140 个文件；Python 约 87 个文件 |

### A.2 包清单与职责

| 包 | 语言 | 职责 |
|---|---|---|
| `air_ground_core` | C++ | 空地协同核心：感知融合、任务状态机、地面规划/执行、日志与评估 |
| `lqr_trajectory_tracker` | C++ | LQR 轨迹跟踪（linear/circular/helical/8 字/step 悬停） |
| `drone_launch_controller` | C++ | 起飞/解锁/健康检查/模式切换 |
| `car_launch_controller` | C++ | 旧地面控制器（已废弃） |
| `rl_obstacle_avoidance` | Python | 无人机感知 + 规则避障 + A* + DQN 训练 |
| `rl_ground_avoidance` | Python | 地面车 DQN 避障（镜像） |
| `gazebo_ros_pkgs` | C++ | Gazebo Classic ROS 集成（vendored，删除） |
| `velodyne_gazebo_plugins` | C++ | Velodyne Gazebo Classic 插件（删除） |

### A.3 协同核心节点清单（`air_ground_core`，全部 C++）

`air_odom_adapter` / `ground_odom_adapter`、`gt_adapter`、`air_perception` / `air_fusion`、`map_adapter`、`task_manager`、`ground_planner`、`ground_commander` / `ground_drive_adapter`、`intruder_driver`、`scenario_reset`、`agc_run_logger`、`air_control_bridge`、`air_follow`、`car_commander`（已废弃）

### A.4 其余消息与服务

| 包 | 消息 | 服务 |
|---|---|---|
| `drone_launch_controller` | `DroneHealthStatus`、`FlightStatus` | `ArmMotors`、`ConnectionStatus`、`DroneHealthCheck`、`Takeoff` |
| `car_launch_controller` | `CarHealthStatus`、`CarStatus` | `CarHealthCheck`、`ConnectionStatus`、`Drive`、`EnableMotion` |
| `rl_obstacle_avoidance` | `ObstacleFeatures` | `PlanPath` |

### A.5 启动编排（迁移前）

- 唯一 run 入口：`src/air_ground_core/launch/agc_collab.launch`（XML）+ `scripts/start_agc_collab.sh`
- 单体实验入口：`scripts/start_sim.sh`（791 行，sim/takeoff/lqr/perception 四模式）
