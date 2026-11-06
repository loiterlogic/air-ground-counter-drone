<a id="request"></a>
# 目标无人机运动规则 + 速度调研与运行节奏 —— round-2 派工（Leader 裁定后）

- 任务 ID：`20261104-002-target-motion-speed`；轮次：2；自写时间 `2026-11-04T19:22:00+08:00`。
- 继承 round-1 的**全部边界**（白名单 / 契约 / 判据 / 资源总量 / 停止条件），本文件只记本轮增量。

## 一、Leader 已裁定（round-1 反解，逐条独立复算通过）

| # | 裁定 | 结果 |
|---|---|---|
| 1 | `traj.speed` **不改** | 反无人机场景走 `HoverTrajectory`，`traj.*` 整段不读 ⇒ 改它零收益。**A7 按「未改 + 给出为什么不需要改」满足** |
| 2 | 判据阈值**全不改** | `d_track` / `t_dwell` / C2 / `safe_max` / 网弹道 四项「不变 + 有推导」 |
| 3 | **不进**「目标快过 2.0 m/s」分支 | 取 `v_t = 1.0 m/s` |
| 4 | **M2「漂移轨道 epicycle」选定** | M1/M3/M4/M5 否决理由被逐条认同；**M5（规避式需订 `/agc/air/odom`）明确否决**（引入非确定性 + 新耦合，与 C4/C5 可复现纪律冲突） |
| 5 | `README.md` **Worker 不改** | 文本已交 Leader，待 ADR-0031 落地后由 Leader 合并 |

## 二、Leader 收严的两处（本轮必须照做）

1. **参数命名**：`drift_amplitude_m`（1.5）/ `drift_period_s`（60.0）；`w6_base.yaml` 须注明
   「这是**圆心**的漂移幅度，不是轨道半径；轨道半径仍是 `radius_m`」。
2. **起点连续性必须证明**：单测显式断言 `_target(0)` 与 `_start_pose()` 逐位相等、`dp/dt(0)` 有限且非零、
   **且 `_start_pose()` 对 t 是常量**（防将来有人把它改成依赖 t）。
   推理链（Leader 复核补充）：`t0_ is None` 时 `_tick` 发的是 `_start_pose()`（恒定）⇒ 机体收敛到起点、
   `speed → 0` ⇒ `_maybe_start` 的 `start_vel_eps 0.35` 能通过；故「起点切线速度非零」**不是**障碍。
   该链条须写进 ADR-0031 的「起点协议兼容性」一节。

## 三、本轮目标

1. 「先学后做」补课 → ADR-0031「对照」节。
2. 实现 M2：`_target()` 一个分支 + `drift_amplitude_m`/`drift_period_s` + `w6_base` 缺省 + `s18` + carriers 登记。
3. 单测 5 条（位移上界 / `_target(0)` 逐位相等 / `_start_pose()` 常量 / 峰值速度 ≤ 1.206 / 确定性）。
4. T2 五次持锁运行：`s04` 基线 → `s18` ×2 同 seed → `s08` → `s13`。
5. ADR-0031 → 删两个 plan → 持 `docs.lock` 跑 `adr_index.py` → `docs_link_check.py`。

## 四、资源（继承，未消耗）

- T1：1200 s（单次 ≤30 s、进程 ≤2、独占 `/tmp/20261104-002-*`）。
- T2：**5400 s 全额仍在**；构建与仿真均计入；单次 launch ≤420 s。
- 独占资源：`flock -w 1800 /home/chen/AGC/.coordination/locks/sim.lock`。

## 五、停止条件（继承 round-1 第九节，不重写）

资源/总时间耗尽即停；K=4 无区分性新证据即熔断；根因已锁定允许同范围修完验完；
三件须停报事项（`traj.speed` / 判据阈值 / 超 2.0 m/s）**本轮已由 Leader 裁定，不再触发**。
