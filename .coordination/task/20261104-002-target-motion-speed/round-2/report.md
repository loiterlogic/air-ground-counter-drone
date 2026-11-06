# 目标无人机运动规则 + 速度调研与运行节奏 —— 第 2 轮报告

- 任务 ID：`20261104-002-target-motion-speed`；轮次：2
- 领取时间：`2026-11-04T19:10:00+08:00`
- 执行者：Worker（DSH 一般模型）
- 子会话 ID：`worker`
- 轮末状态：**执行中 → 被用户停机中断**（20:32 用户裁定"实验环境出问题，停下来重启"）

## 本轮实际完成

1. **实现 M2 `epicycle`**：`intruder_driver._target()` 新增分支（解析式
   `c(t)=o+A(sin,cos)` + `p(t)=c+r(cos,sin)`），参数 `drift_amplitude_m` / `drift_period_s`。
2. **参数反解修正**（单测抓到的真实矛盾）：初值 `A=1.5/T=60` 使
   `A+r+goal_tol = 3.60 > d_track 3.0` ⇒ dwell 会被 `RANGE_EXCEEDED` 反复清零 ⇒ 跟踪终态不可达。
   改为 `A=0.6/T=30` ⇒ `2.70 < 3.0`，峰值速度 `1.126 ≤ 1.206`。
3. **`s18` 场景 + carriers 登记**：`target_motion.epicycle`，活跃消费者
   `s18_epicycle_none_nominal_track`（yard 地图，与 s04 可对照）。
4. **单测 11 条**：`scripts/tests/test_target_motion_epicycle.py`（位移上界 / `_target(0)` 逐位相等 /
   `_start_pose()` 常量 / 峰值速度 / 确定性 / 既有三支回归 / 未知值兜底）。
5. **构建通过**（T2 45 s）。
6. **T2 run 2 次**：`s04` 基线（TIMEOUT）、`s18` 首次（TRACKING_SUCCESS 75.7 s）。

## 本轮 T2 消耗

| run | 墙钟 | 结果 |
|---|---|---|
| `s04` 基线 | 192 s | `MISSION_FAILED/TIMEOUT` |
| `s18` #1 | 1002 s（含环境异常等待） | `TRACKING_SUCCESS` 75.7 s |

> 1002 s 里大部分是环境崩溃（RTF 0.069）后的等待与超时回收，**不是有效计算**。
> 该异常已由 Leader 定位为 `flock` 未包整轮生命周期的机制缺陷，非本单代码问题。

## 本轮发现（已写入 round-3 report 与 ADR-0031）

- **A2 的逐字节证明方法**（撤销编辑 → sha256 比对），比 `git diff` 强。
- **`s04` 既有不稳定**：同 seed 多次 run 在 `TRACKING_SUCCESS` / `TIMEOUT` 间摆动
  （根因在 round-3 才用 `dwell_event` 实测证实）。
- **`s18` 比 `s04` 快 2.2 倍**，但**不能**解读为"机动目标更好跟"（见 ADR-0031 (a0)）。

## 被中断的项（round-3 续做）

`s18` 第 2 次同 seed、`s08`、`s13`、ADR-0031、删两个 plan、索引/链接检查 —— 均已在 round-3 完成。
