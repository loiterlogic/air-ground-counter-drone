<a id="request"></a>
# F1 · 出生布局 · round-2（Worker 自写，继承 round-1 边界）

来源：Leader [round-1 审查与恢复执行裁定](round-1/review.md#review)；用户已授权四任务并行。
任务 ID 不变 `20261031-012-spawn-layout`；轮次 2；承接 round-1 阻塞交回（状态由 Leader 置回执行）。

## 本轮目标（逐条对账 round-1 审查）

| # | 审查要求 | 本轮动作 |
|---|---|---|
| 1 | 继续以 full+yard+s04+GUI 到期望终态为出口 | 真实 GUI 跑到 `TRACKING_SUCCESS` + 出生帧/终态帧截图 + C9/清理证据 |
| 2 | r014 越界输入由 work_area+车外伸派生，核对**拒绝原因** | 改 `tests/w6_r014_check.py`：从几何真源派生边界，断言 `reason == boundary_out_car` |
| 3 | yard 3.19>0 按既有判据继续；删除"只能改模型"建议；评估候选位置 | 改 `spawn_layout.yaml` 措辞为候选位置评估；不改安全层/footprint 判据 |
| 4 | `load_spawn_layout` 拒绝非有限数（NaN/Inf）；world_bringup 同 | 补 `math.isfinite` + 单测（NaN/Inf/字符串） |
| 5 | manifest 的 own_pose 可被显式覆盖，但距离仍取 layout → 假象 | 距离与设计目标断言改用**实际生效** own pose；记录 own_pose 来源 |
| 6 | 固定 goal 12.5/−2 是第二处关联坐标，需派生或同步守卫 | `spawn_layout.yaml` 增 `goal_offset_m`；默认场景由目标位+偏移派生；保留其它场景覆盖 |
| 7 | GUI 未截图；/tmp 脚本须入本单产物目录 | 截图两组；脚本迁入 `experiments/f1-spawn/scripts/` |
| 8 | CPU→EKF 与"根因不是布局"保留为假设；先学已验证实现 | 见下「学习记录」；不以放宽感知/契约制造成功 |

## 学习记录（先学后做，本轮已做）

1. **本机同版本 PX4 源码**（`toolchain/PX4-Autopilot`，v1.15.4）：
   - `mc_pos_control/MulticopterPositionControl.cpp:522` → `!_control.update(dt)` 时调
     `generateFailsafeSetpoint(..., warn=true)`；
   - 同文件 `:562-590`：`generateFailsafeSetpoint` 打印 `invalid setpoints`，随后
     **若 `states.velocity` 非有限 → 打印 `Failsafe: blind land` 并给 `velocity[2]=mpc_land_speed`**；
   - 同文件 `:280-325`：`states.velocity` 各分量来自 `vehicle_local_position.{vx,vy,vz}` +
     对应 `v_*_valid` 标志；标志为假或非有限即置 `NAN`。
   ⇒ **`blind land` 的直接含义是「EKF 速度估计无效（或非有限）」**，不是"CPU 忙"。
   `PositionControl::update()` 仅在 `_acc_sp` / `_thr_sp` 非有限时返回 false（`PositionControl.cpp:121`）。
2. **PX4 自身如何用 `PX4_GZ_MODEL_POSE`**（`gz_bridge/GZBridge.cpp:81-113`）：只把位姿传给 gz `create`
   请求；`model_pose_v[2] <= 0` 才抬到 0.5。**与 EKF 初始化无关**，故"己方机位姿数值"本身
   不是 `blind land` 的成因而只能是**并发失效的相关项**——仍按假设处理（见台账）。
3. **项目内既有运行证据**（不改写、仅引用）：`experiments/demo/20261031-114349`（TRACKING_SUCCESS）
   的 `blind land` **只出现在 px4-37（入侵者）6 次**；`experiments/demo/20261031-142516`
   （**round-1 改动之前**，own pose 仍是 `0,0,0.2`）已出现 **px4-36（己方）49 次**。
   ⇒ 己方 `blind land` 在本单改动前既已发生；但按裁定仍**只作假设 H1/H4 的证据**，不作结论。
4. **感知量程与站距的结构性冲突**（`agc_perception/config/perception_sensors.yaml` vs
   `agc_air/config/air.yaml`）：`range_max_m=12.0`，而 `standoff_follower.safe_max=15.0`、
   安全层 `target_min_dist=8.0` ⇒ 站距带 [8,15] m 的上沿**超出**量程。排障速查第 4 节已登记
   "`rmax` 属环境边界（量程 12 m < 站距上限 15 m，对两臂对称）"。**本轮不放宽量程**，
   只把它作为 H3 的可达性事实登记。

## 边界（继承 round-1，仅按裁定增补）

- 白名单：原 `src/agc_task/config/`、`src/agc_task/launch/`、`src/agc_sim/launch/`、`src/agc_air/launch/`
  + 相关出生核查测试 + **新增** `src/agc_task/test`、`scripts/tests` 中与出生行为相关的回归。
  `src/agc_task/src/scenario_reset.cpp` 仍仅确有必要才改（本轮暂不改）。
- 产物：`experiments/f1-spawn/`（含 `scripts/`、`shots/`）。
- **禁止**：`/dev/shm` 任何写删、系统/工具链参数修改、他人进程清理、git 写操作、改安全层或
  footprint 判据、改地图障碍、改契约。
- 禁改他人文件：`CURRENT.md`、`review.md`、归档、共享索引由 Leader 写。

## 预算（round-2）

- T2（构建 + 真实运行）**剩余总量 3250 s**，单次运行 ≤300 s；累计（round-1 348 s + 本轮）≤3600 s。
- T1 只读系统观测：追加 120 s，单次 ≤30 s。
- 离线检查：追加 600 s，单次 ≤30 s；完整冒烟单次 ≤120 s（显式授权）。
- 场景固定 yard / s04 / full / seed0 / GUI，`observe_yaw_mode=target`（原默认 oracle 指向臂）。
  若确需旧布局对照，只用**本单临时参数**、产物隔离，不覆盖新真源、不改历史证据。
- 停止条件：连续 4 轮无区分性新证据，或资源边界触发。

## 本轮可判定出口

1. 两个非有限值入口均拒绝并各有测试（NaN/Inf/非数值）。
2. manifest 的 own pose 与距离**同源同值**（显式覆盖时不再用 layout 距离）。
3. 默认场景 goal 由目标位+偏移派生；改 `spawn_layout.yaml` 的 target 后 goal 自动跟随（测试守护）。
4. `w6_geometry_check.py` 三图 PASS；`test_scene_config_invariants.py` 全绿。
5. 真实 GUI 运行到 `TRACKING_SUCCESS`，并留出生帧 + 终态帧 + C9 + 清理证据。
