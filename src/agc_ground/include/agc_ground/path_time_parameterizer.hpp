// path_time_parameterizer —— 弧长时间参数化与动力学复核（纯逻辑，不 include ROS）
//
// 结构对应 [Fast-Planner 的 `NonUniformBspline::reallocateTime`](../../../refs/Fast-Planner/fast_planner/bspline/src/non_uniform_bspline.cpp)：
// 论文按控制点速度/加速度超限**拉伸节点向量**（改时间分配），本文件按弧长**传播速度上限**
// （改速度剖面）。两者回答同一个问题：「这条几何路径能不能被这台车按动力学跑出来」。
//
// **不是代码移植**：论文处理四旋翼 snap/thrust 与非均匀 B 样条节点；这里处理差速车的
// 曲率、线/角速度、线/角加速度。
//
// ## 第一版只做诊断，不进消息
//
// ADR-0048：「时间参数化第一版作为规划内部结果和诊断，不立即扩展消息 ABI」；
// ADR-0048 又把「速度剖面进入 Path 消息」列为**明确不做**。
//
// 但它是**硬判据**：得不到可行剖面就返回 `kDynamicsInfeasible`，整次规划失败。
// 结果写进 `PathResult::speed_profile`（诊断），不写进 `/agc/ground/path`。
//
// ## 速度上限的**四条**来源
//
// ```text
// v_i <= v_cap                                     （车体线速度上限）
// v_i <= sqrt(a_lat_max / |kappa_i|)               （横向加速度，过弯）
// v_i <= w_cap / |kappa_i|                         （角速度上限，omega = kappa * v）
// v_i <= 角加速度反解上限                            （见下，**弯前提前减速**的来源）
// ```
//
// ### 第四条为什么必须有
//
// 角加速度不是独立量，它由两部分合成：
//
// ```text
// omega = v * kappa
// domega/dt = (dv/dt) * kappa  +  v^2 * (dkappa/ds)
//              └─ 加减速项 ─┘        └─ 曲率变化项 ─┘
// ```
//
// 只做事后检查（`|dw|/dt > w_acc_max` 就判失败）会让**本来可通过降速救回**的路径
// 被判死：降速使 `dt` 变大、`domega/dt` 变小。实测（`yard` s19）：
// 曲率 0.334 /m 完全合规、线速度/加速度全合规，唯独角加速度 3.01 > 2.0，
// 而按 `v^2 * dkappa/ds` 反解出的速度上限能把它压下去。
//
// 反解（忽略加减速项，保守）：`v^2 * |dkappa/ds| <= w_acc_max`
// ⇒ `v <= sqrt(w_acc_max / |dkappa/ds|)`。
// `dkappa/ds` 用相邻点的曲率差除以弧长估计。
//
// 第三条与第二条形式相似但语义不同：第二条来自「不能侧翻/打滑」，第三条来自
// 「转向机构转不了那么快」。两者都必须有，取更严的那个。
//
// ## 前向/后向传播
//
// ```text
// v_forward[i+1] = min(v_limit[i+1], sqrt(v_forward[i]^2 + 2*a_acc*ds))
// v_backward[i]  = min(v_forward[i],  sqrt(v_backward[i+1]^2 + 2*a_brake*ds))
// ```
//
// 前向保证加速能力，后向保证**能刹住**。只做前向会让车冲到弯道里才发现转不过来。

#ifndef AGC_GROUND__PATH_TIME_PARAMETERIZER_HPP_
#define AGC_GROUND__PATH_TIME_PARAMETERIZER_HPP_

#include <algorithm>
#include <cmath>
#include <limits>
#include <vector>

#include "agc_ground/planner_types.hpp"
#include "agc_ground/spline_optimizer_2d.hpp"

namespace agc_ground
{
namespace planner
{

// 匀加速运动学：由「弧长 s、起速 v0、终速 v」反解加速度。
//
// **这是本模块唯一需要单独验证的数学式**：`v² = v0² + 2·a·s` ⇒ `a = (v²−v0²)/(2s)`。
// 抽成独立函数是为了能被单测**直接调用** —— 藏在传播循环里的话，
// 任何"用 a_acc 自限的传播"都会把它掩盖（见 `parameterizeTime` 的注释）。
inline double uniformAccel(double v0, double v, double s)
{
  if (s <= 1e-12) {return 0.0;}
  return (v * v - v0 * v0) / (2.0 * s);
}

// 时间参数化结果。
struct TimeParamResult
{
  bool feasible{false};
  std::string reason;
  std::vector<SpeedProfilePoint> profile;
  double max_curvature{0.0};
  double max_linear_velocity{0.0};
  double max_angular_velocity{0.0};
  double max_linear_accel{0.0};   // 加速（正）
  double max_linear_decel{0.0};   // 制动（负的绝对值）
  double max_angular_accel{0.0};
  double total_time_s{0.0};
};

// 对一条位姿序列做弧长采样 + 速度传播 + 动力学复核。
//
// `start_speed` 是**当前车速**（从 odom 来）。它不是一个可选的装饰：
// 起点速度若被当成「该点上限」，剖面就会凭空假设车已经全速在跑 ——
// 于是加速上限 `a_acc_max` 在整条路径上**永远不生效**（实测：直线路径恒速 1.5，
// 每段加速度 0，把 `a_acc_max` 设成 0.3 也照样判可行）。
// 默认 0 表示「从静止起步」，这是保守方向。
inline TimeParamResult parameterizeTime(
  const std::vector<Pose2D> & poses, const PlannerParams & p, double start_speed = 0.0)
{
  TimeParamResult res;
  if (poses.size() < 3) {
    res.reason = "path too short for time parameterization";
    return res;
  }

  // ---- ① 曲率（与最终复核共用同一个函数，避免两套口径）----
  const std::vector<double> kappa = computeCurvature(poses);

  // ---- ② 弧长与逐点速度上限 ----
  const size_t n = poses.size();
  std::vector<double> ds(n, 0.0);   // ds[i] = 从 i-1 到 i 的弧长
  for (size_t i = 1; i < n; ++i) {
    ds[i] = std::hypot(poses[i].x - poses[i - 1].x, poses[i].y - poses[i - 1].y);
  }

  const double eps = 1e-6;
  std::vector<double> v_limit(n, p.v_cap);
  double max_k = 0.0;
  for (size_t i = 0; i < n; ++i) {
    const double ak = std::fabs(kappa[i]);
    max_k = std::max(max_k, ak);
    // 曲率极大时（近尖角）限速趋零 —— 这不是「走不了」，是「必须慢到接近停」。
    const double kk = std::max(ak, eps);
    const double v_lat = std::sqrt(p.a_lat_max / kk);
    const double v_rot = p.w_cap / kk;
    v_limit[i] = std::min({p.v_cap, v_lat, v_rot});
    if (!std::isfinite(v_limit[i]) || v_limit[i] < 0.0) {v_limit[i] = 0.0;}
  }

  // ---- ④ 角加速度反解的速度上限（**弯前提前减速**的来源）----
  //
  // `domega/dt = a*kappa + v^2 * dkappa/ds`。只保留曲率变化项（保守，忽略 a 项），
  // 得 `v <= sqrt(w_acc_max / |dkappa/ds|)`。
  // `dkappa/ds` 用相邻点差分；退化段（ds≈0，如原地旋转）跳过 —— 那里 v=0。
  for (size_t i = 1; i < n; ++i) {
    if (ds[i] < 1e-9) {continue;}
    const double dkds = std::fabs(kappa[i] - kappa[i - 1]) / ds[i];
    if (dkds < 1e-9) {continue;}
    const double v_wa = std::sqrt(p.w_acc_max / dkds);
    if (std::isfinite(v_wa)) {
      v_limit[i] = std::min(v_limit[i], v_wa);
      v_limit[i - 1] = std::min(v_limit[i - 1], v_wa);
    }
  }

  // ---- ③ 前向传播（加速能力）----
  std::vector<double> v_fwd = v_limit;
  // 起点速度 = **当前车速**，不是该点上限。这是加速约束生效的前提。
  v_fwd[0] = std::min(v_limit[0], std::max(0.0, start_speed));
  for (size_t i = 0; i + 1 < n; ++i) {
    const double reachable = std::sqrt(v_fwd[i] * v_fwd[i] + 2.0 * p.a_acc_max * ds[i + 1]);
    v_fwd[i + 1] = std::min(v_limit[i + 1], reachable);
  }

  // ---- ④ 后向传播（制动能力）----
  std::vector<double> v_bwd = v_fwd;
  for (size_t i = n - 1; i > 0; --i) {
    const double reachable = std::sqrt(v_bwd[i] * v_bwd[i] + 2.0 * p.a_brake_max * ds[i]);
    v_bwd[i - 1] = std::min(v_fwd[i - 1], reachable);
  }

  // ---- ⑤ 复核 ----
  double max_v = 0.0, max_w = 0.0, max_wa = 0.0, total_t = 0.0;
  // 加速与制动**分开累计**：两者的上限不同（`a_acc_max` vs `a_brake_max`），
  // 合并成一个 `max_a` 会让"下坡式"的错误配置无法被发现。
  double max_accel = 0.0, max_decel = 0.0;
  for (size_t i = 0; i < n; ++i) {
    const double v = v_bwd[i];
    const double w = kappa[i] * v;
    max_v = std::max(max_v, std::fabs(v));
    max_w = std::max(max_w, std::fabs(w));

    SpeedProfilePoint sp;
    sp.s = (i == 0) ? 0.0 : 0.0;   // 下面填累计
    sp.v = v;
    sp.kappa = kappa[i];
    res.profile.push_back(sp);

    if (i > 0 && ds[i] > 1e-9) {
      // **匀加速运动学**：v² = v0² + 2·a·s  ⇒  a = (v² − v0²) / (2·s)。
      //
      // 早先写成 `(v − v0)² / (2s)`，那是把「速度差」当成了「速度平方差」——
      // 量纲对但数值系统性错误：v0=1.4、v=1.5、ds=0.25 时真实 0.58，代码算出 0.02
      // （**低估 29 倍**）；v0=0 起步时算出 0，完全看不见加速需求。
      // 后果是加速上限 `a_acc_max` 事实上从未生效。
      //
      // 保留符号：加速为正、减速为负，分别与 `a_acc_max` / `a_brake_max` 比较。
      const double a_signed = uniformAccel(v_bwd[i - 1], v, ds[i]);
      if (a_signed > 0.0) {
        max_accel = std::max(max_accel, a_signed);
      } else {
        max_decel = std::max(max_decel, -a_signed);
      }
      const double dt = (v + v_bwd[i - 1] > 1e-6) ?
        (2.0 * ds[i] / (v + v_bwd[i - 1])) : 0.0;
      total_t += dt;
      if (dt > 1e-9) {
        const double dw = std::fabs(w - kappa[i - 1] * v_bwd[i - 1]);
        max_wa = std::max(max_wa, dw / dt);
      }
    }
  }
  // 累计弧长
  double cum = 0.0;
  for (size_t i = 0; i < n; ++i) {
    if (i > 0) {cum += ds[i];}
    res.profile[i].s = cum;
  }

  res.max_curvature = max_k;
  res.max_linear_velocity = max_v;
  res.max_angular_velocity = max_w;
  res.max_linear_accel = max_accel;
  res.max_linear_decel = max_decel;
  res.max_angular_accel = max_wa;
  res.total_time_s = total_t;

  // 判据顺序：曲率 → 线速度 → 角速度 → 线加速度 → 角加速度。
  // **单一失败原因**（不返回列表）：诊断要能直接归因。
  const double tol = 1e-3;
  // **曲率的离散化容差**：`κ = Δθ/Δs` 是在重采样后的折线上估计的，
  // 而重采样会跨过基元边界（一点在 k=+1 弧上、下一点在 k=-0.5 弧上），
  // 于是估计值可能略超真实曲率。实测（`sparse_map`）：基元真实曲率 1.0 /m，
  // 离散估计 1.029 /m —— 超 2.9%，是**离散化残差**，不是真实转向超限。
  //
  // 容差取 `resample_spacing / (1/kappa_max)` 的 25%（= 一个重采样步内的理论
  // 转角误差量级），再下限 5%：`κ <= kappa_max * (1 + max(0.05, 0.25*ds*κ_max))`。
  // 这个容差只吸收**采样离散**，不吸收真实超限 —— 真实的急转（如 2.0 /m）仍会被抓。
  const double kappa_tol_frac = std::max(0.05, 0.25 * p.resample_spacing_m * p.kappa_max);
  const double kappa_limit = p.kappa_max * (1.0 + kappa_tol_frac);
  if (max_k > kappa_limit + tol) {
    res.reason = "curvature " + fmt(max_k) + " > kappa_max " + fmt(p.kappa_max) +
      " (tolerance " + fmt(kappa_limit) + ")";
    return res;
  }
  if (max_v > p.v_cap + tol) {
    res.reason = "linear velocity " + fmt(max_v) + " > v_cap " + fmt(p.v_cap);
    return res;
  }
  if (max_w > p.w_cap + tol) {
    res.reason = "angular velocity " + fmt(max_w) + " > w_cap " + fmt(p.w_cap);
    return res;
  }
  if (max_accel > p.a_acc_max + tol) {
    res.reason = "linear accel " + fmt(max_accel) + " > a_acc_max " + fmt(p.a_acc_max);
    return res;
  }
  if (max_decel > p.a_brake_max + tol) {
    res.reason = "linear decel " + fmt(max_decel) + " > a_brake_max " + fmt(p.a_brake_max);
    return res;
  }
  if (max_wa > p.w_acc_max + tol) {
    res.reason = "angular accel " + fmt(max_wa) + " > w_acc_max " + fmt(p.w_acc_max);
    return res;
  }
  // 速度剖面必须处处有限且非负。
  for (const SpeedProfilePoint & sp : res.profile) {
    if (!std::isfinite(sp.v) || sp.v < 0.0) {
      res.reason = "non-finite or negative speed in profile";
      return res;
    }
  }

  res.feasible = true;
  return res;
}

}  // namespace planner
}  // namespace agc_ground

#endif  // AGC_GROUND__PATH_TIME_PARAMETERIZER_HPP_
