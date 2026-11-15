// motion_primitive —— 差速车的运动基元生成与解析积分（纯逻辑，不 include ROS）
//
// 运动模型（ADR-0048）：
//
// ```text
// x_dot   = v cos(yaw)
// y_dot   = v sin(yaw)
// yaw_dot = omega
// ```
//
// 这是 [Fast-Planner](../../../refs/Fast-Planner/fast_planner/path_searching/src/kinodynamic_astar.cpp)
// 的 `stateTransit` 在二维差速车上的重建模：论文里是四旋翼的三维状态 + 加速度输入，
// 这里是 SE(2) 位姿 + 线/角速度输入。**不是代码移植**，是同一套「离散控制输入 → 解析
// 状态转移 → 逐采样点碰撞检查」的结构。
//
// ## 为什么用解析积分而不是欧拉步进
//
// 论文的实现就是解析的（`stateTransit` 直接给闭式解）。差速车的闭式解更简单：
//
// * `omega == 0`：直线，`p(t) = p0 + v*t*(cos yaw0, sin yaw0)`，`yaw = yaw0`
// * `omega != 0`：圆弧，半径 `R = v/omega`，圆心在车体左侧 `R` 处
//
// 用解析解的价值：**采样点严格落在真实轨迹上**。欧拉步进在 `omega=2.0` 时
// （`dt=0.333`，`yaw` 转过 0.67 rad ≈ 38°）会把弧线算成折线，累计误差可达
// 数十厘米 —— 而车宽只有 0.571 m，这个误差足以让碰撞检查结论反向。
//
// ## 为什么不倒车
//
// 第一版 `v >= 0`。ADR-0048：「倒车必须等控制链和验收口径确认后再加入，
// 不通过隐式参数开关在同一主链保留两套实现」。倒车留待后续独立决策。
//
// ## 为什么允许原地旋转
//
// `v == 0, omega != 0` 是差速车的**真实能力**，也是非完整约束下通过窄通道的必要手段。
// ADR-0048 说的是「默认只搜索前进基元」，原地旋转不是「后退」。
// 安全层对纯旋转有专门处理（只限速、不判停，见 `tierFromGeometry` 的 `pure_rotation` 分支）。

#ifndef AGC_GROUND__MOTION_PRIMITIVE_HPP_
#define AGC_GROUND__MOTION_PRIMITIVE_HPP_

#include <algorithm>
#include <cmath>
#include <vector>

#include "agc_ground/planner_types.hpp"

namespace agc_ground
{
namespace planner
{

// 归一化角度到 (-pi, pi]。
inline double normalizeAngle(double a)
{
  while (a > M_PI) {a -= 2.0 * M_PI;}
  while (a <= -M_PI) {a += 2.0 * M_PI;}
  return a;
}

// 从 `start` 施加 `ctrl` 持续 `t` 秒后的解析状态。
//
// 圆弧情形用圆心参数化：圆心 = 起点 + R * (左法向)，其中 `R = v/omega`。
// 注意 `omega` 的符号决定转向：`omega > 0` 是逆时针（车体左侧为圆心）。
inline Pose2D integrateState(const Pose2D & start, const Control & ctrl, double t)
{
  Pose2D out;
  if (std::fabs(ctrl.omega) < 1e-9) {
    // 直线
    out.x = start.x + ctrl.v * std::cos(start.yaw) * t;
    out.y = start.y + ctrl.v * std::sin(start.yaw) * t;
    out.yaw = start.yaw;
    return out;
  }
  const double R = ctrl.v / ctrl.omega;   // 可为 0（原地旋转时 v=0）
  const double yaw1 = start.yaw + ctrl.omega * t;
  // 圆心：车体左侧 R 处（omega>0 时逆时针，圆心在左）
  const double cx = start.x - R * std::sin(start.yaw);
  const double cy = start.y + R * std::cos(start.yaw);
  out.x = cx + R * std::sin(yaw1);
  out.y = cy - R * std::cos(yaw1);
  out.yaw = yaw1;
  return out;
}

// 生成一条基元的采样位姿序列（含起点与终点）。
//
// **采样密度**：按最大空间步长 `max_step_m` 决定采样数。对原地旋转（`v=0`）空间
// 步长为 0，此时改按**角**步长采样（每 0.1 rad 一个点），否则旋转 0.333 s 只采一个点，
// 车角扫过的区域完全没被检查 —— 这正是 ADR-0048「不能只检查终点」要防的。
inline Primitive makePrimitive(
  const MotionState & start, const Control & ctrl, double duration,
  double max_step_m)
{
  Primitive prim;
  prim.start_state = start;
  prim.control = ctrl;
  prim.duration = duration;

  // 弧长与转角
  const double arc_len = std::fabs(ctrl.v) * duration;
  const double turn = std::fabs(ctrl.omega) * duration;
  prim.length = arc_len;

  int n = 1;
  if (arc_len > 1e-9) {
    n = std::max(n, static_cast<int>(std::ceil(arc_len / std::max(max_step_m, 1e-3))));
  }
  if (turn > 1e-9) {
    // 纯旋转 / 大转角：每 0.1 rad 至少一个采样点。
    n = std::max(n, static_cast<int>(std::ceil(turn / 0.1)));
  }
  n = std::min(n, 200);   // 上限：防止病态参数把单条基元采样撑爆

  prim.sampled_poses.reserve(static_cast<size_t>(n) + 1);
  prim.sampled_poses.push_back(start.pose);
  for (int i = 1; i <= n; ++i) {
    const double t = duration * static_cast<double>(i) / static_cast<double>(n);
    prim.sampled_poses.push_back(integrateState(start.pose, ctrl, t));
  }
  return prim;
}

// 全部候选控制输入（含原地旋转，若允许）。
//
// ## 按曲率生成，不按 `(v, ω)` 笛卡尔积
//
// 差速车沿圆弧前进时曲率 `kappa = |omega| / v`。基元集必须与 `kappa_max` **自洽**，
// 否则搜索产出的路径永远过不了最终曲率复核 —— 那是**结构缺陷**，不是调参问题。
//
// 实测教训：早先 `omega_set = {±2, ±1, ±0.5, 0}` × `v_set = {0.3..1.5}`，
// 在 `kappa_max = 1.0` 下 `v=0.3, omega=2.0` 的曲率是 **6.67 /m**（半径 0.15 m）。
// 搜索大量使用它，原始路径曲率 2.44 /m，重采样/优化后仍 2.28 —— 怎么后处理都过不了。
//
// 现在：`omega = kappa * v`，`kappa = fraction * kappa_max`。按构造满足
// `|omega| <= kappa_max * v`，且同一条圆弧不会用多种速度重复表达。
//
// **原地旋转不受此限**：`v=0` 时曲率无定义，且安全层对纯旋转有专门处理
// （只限速、不判停）。
inline std::vector<Control> candidateControls(const PlannerParams & p)
{
  std::vector<Control> out;
  for (double v : p.v_set) {
    for (double frac : p.curvature_fractions) {
      const double kappa = frac * p.kappa_max;
      const double w = kappa * v;                 // omega = kappa * v
      if (std::fabs(w) > p.w_cap + 1e-9) {continue;}   // 角速度上限
      Control c;
      c.v = v;
      c.omega = w;
      out.push_back(c);
    }
  }
  if (p.allow_in_place_rotation) {
    for (double w : p.omega_set) {
      if (std::fabs(w) < 1e-9) {continue;}   // 原地不动没有意义
      if (std::fabs(w) > p.w_cap + 1e-9) {continue;}
      Control c;
      c.v = 0.0;
      c.omega = w;
      out.push_back(c);
    }
  }
  return out;
}

// 基元的边代价（ADR-0048 的建议形式 + 代价带项）。
//
// ```text
// g_edge = w_time   * duration
//        + w_length * primitive_length
//        + w_turn   * |omega| * duration
//        + w_clearance * clearance_penalty
//        + w_cost   * mean_cost_band
// ```
//
// **`clearance_penalty` 的构造**：`max(0, target - clearance)^2`，`clearance` 由调用方
// 传入（基元上的最小离障）。用平方而不是线性：远离目标值时迅速趋零，避免「远处一点点
// 近」把路径推成大绕圈（与 ADR-0041 的指数代价同一条理由）。
//
// **`mean_cost_band` 必须进代价**：`1–98` 是「可通行但有代价」，若不计代价，搜索会
// 贴着 `99` 环走，而走廊判据（只看 `100`）会让这类路径看似合格、实际余量极小。
inline double primitiveEdgeCost(
  const PlannerParams & p, double duration, double length,
  double omega, double clearance, double mean_cost_band)
{
  double cost = p.w_time * duration
    + p.w_length * length
    + p.w_turn * std::fabs(omega) * duration
    + p.w_cost * std::max(0.0, std::min(1.0, mean_cost_band));
  if (std::isfinite(clearance)) {
    const double short_fall = std::max(0.0, p.clearance_target_m - clearance);
    cost += p.w_clearance * short_fall * short_fall;
  }
  return cost;
}

// 启发式：欧氏距离 + 航向误差（ADR-0048 的第一版）。
//
// **为什么不直接用 Dubins 距离**：ADR-0048 明写「后续可替换为 Dubins 距离，但不把该
// 优化作为首条链的前置依赖」。欧氏 + 航向是**可采纳**的下界近似（在忽略障碍时），
// 加权 A* 会牺牲最优性换速度 —— 这与「本轮不承诺全局最优」的出口判据一致。
//
// 航向项乘 `heuristic_heading_scale`：航向误差 1 rad 折合多少米。取 0.5 m/rad 是
// 「宁可多走半米也不要为对齐航向绕一圈」的量级；它只影响搜索效率，不影响可行性。
inline double heuristicCost(
  const Pose2D & from, const Pose2D & goal, double weight)
{
  const double d = std::hypot(goal.x - from.x, goal.y - from.y);
  const double dyaw = std::fabs(normalizeAngle(
      std::atan2(goal.y - from.y, goal.x - from.x) - from.yaw));
  return weight * (d + 0.5 * dyaw);
}

// 基元是否满足「前进 + 不超车体动力学上限」的静态检查。
// 搜索阶段只用参数集本身保证，这里留给最终复核用。
inline bool controlWithinCaps(const Control & c, const PlannerParams & p)
{
  if (c.v < -1e-9) {return false;}                       // 第一版不倒车
  if (std::fabs(c.v) > p.v_cap + 1e-9) {return false;}
  if (std::fabs(c.omega) > p.w_cap + 1e-9) {return false;}
  return true;
}

}  // namespace planner
}  // namespace agc_ground

#endif  // AGC_GROUND__MOTION_PRIMITIVE_HPP_
