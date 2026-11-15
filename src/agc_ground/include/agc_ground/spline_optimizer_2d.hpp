// spline_optimizer_2d —— 二维 B 样条 / 弹性带控制点优化（纯逻辑，不 include ROS）
//
// 目标函数（ADR-0048）：
//
// ```text
// J = lambda_smooth    * Σ||Q[i+1]-2Q[i]+Q[i-1]||²
//   + lambda_clearance * Σ max(0, clearance_target - d(Q[i]))²
//   + lambda_curvature * Σ max(0, |kappa[i]| - kappa_max)²
//   + lambda_length    * path_length
//   + lambda_heading   * terminal_heading_error²
// ```
//
// ## 为什么不用 NLopt（Fast-Planner 的做法）
//
// 论文的实现用 `nlopt::opt` 做梯度下降（`bspline_optimizer.cpp` 的 `optimize()`）。
// 本机**没有 nlopt**（`dpkg -l | grep nlopt` 为空，只有 `libeigen3-dev`），
// 引入新外部依赖需要独立决策。而二维问题只有 `2N` 个变量、代价函数与梯度都可解析写出，
// 一个带 Armijo 线搜索的梯度下降足够 —— 这里**手写**。
//
// ## 优化只是质量改善，不是安全证明
//
// ADR-0048 原话：「B 样条优化只是质量改善，不是安全证明。安全证明来自最终密集采样的
// 真实 footprint 检查」。所以本模块**不**承诺输出无碰撞路径；调用方必须重新复核，
// 失败即回退到搜索原始路径（见 `planner_engine.hpp`）。
//
// ## 为什么固定首尾控制点
//
// 起点必须精确等于当前车位（否则路径第一点与车不符，消费侧前视会跳），终点必须精确
// 等于 goal（否则 `goal_consistent_with_path` 判不一致 → 零速）。只优化内部点。

#ifndef AGC_GROUND__SPLINE_OPTIMIZER_2D_HPP_
#define AGC_GROUND__SPLINE_OPTIMIZER_2D_HPP_

#include <algorithm>
#include <chrono>
#include <functional>
#include <cmath>
#include <limits>
#include <vector>

#include "agc_ground/distance_field_2d.hpp"
#include "agc_ground/motion_primitive.hpp"
#include "agc_ground/planner_types.hpp"

namespace agc_ground
{
namespace planner
{

// 按弧长重采样一条位姿序列。航向由相邻点切线决定（末点沿用最后一段）。
//
// ## 旋转段必须被保护（实测驱动的修正）
//
// 朴素实现只在**弧长**上等距取点。这对纯旋转段是灾难性的：
// 旋转基元的弧长 ≈ 0，所以重采样会**整个跨过它**，把一次 0.77 rad 的转向
// 挤成一个接缝跳变。实测（`yard` s19）：i=70→71→72 段长仅 0.115 m，
// 航向却每次跳 0.3849 rad —— 那正是一次被抽稀的旋转基元。
//
// 这正是「原地旋转不能被平滑器悄悄抹掉」的同一条纪律，重采样器犯的是同一个错。
//
// ## 做法
//
// 把序列切成「旋转段」（`ds < rot_eps`）与「平移段」：
// * 旋转段：**原样保留**全部点（它们表达航向变化，不能抽稀）；
// * 平移段：按弧长重采样；
// * 拼接处：保留旋转段的首末点，避免重复。
inline std::vector<Pose2D> resampleByArcLength(
  const std::vector<Pose2D> & in, double spacing_m)
{
  if (in.size() < 2) {return in;}
  const double step = std::max(spacing_m, 1e-3);
  // 判定「旋转点」的位移阈值：远小于格宽，只用来区分"位置不变"与"有位移"。
  constexpr double kRotEps = 1e-3;

  std::vector<Pose2D> out;
  out.reserve(in.size());

  // 分段：连续的有位移点构成一个平移段；位移≈0 的点是旋转点。
  size_t i = 0;
  while (i + 1 < in.size()) {
    const double ds = std::hypot(in[i + 1].x - in[i].x, in[i + 1].y - in[i].y);
    if (ds < kRotEps) {
      // 旋转点：**原样保留**（含航向），不参与弧长重采样。
      if (out.empty() || std::hypot(
          out.back().x - in[i].x, out.back().y - in[i].y) > 1e-9 ||
        std::fabs(out.back().yaw - in[i].yaw) > 1e-9)
      {
        out.push_back(in[i]);
      }
      ++i;
      continue;
    }
    // 平移段：从 i 开始收集连续有位移的点
    size_t j = i;
    std::vector<double> cum;
    cum.push_back(0.0);
    while (j + 1 < in.size()) {
      const double seg = std::hypot(in[j + 1].x - in[j].x, in[j + 1].y - in[j].y);
      if (seg < kRotEps) {break;}
      cum.push_back(cum.back() + seg);
      ++j;
    }
    const double total = cum.back();
    if (total > 1e-9) {
      const int n = std::max(1, static_cast<int>(std::ceil(total / step)));
      size_t seg_idx = 0;
      const size_t first = out.empty() ? i : i;   // 平移段总是从 in[i] 起
      for (int k = 0; k <= n; ++k) {
        const double s = total * static_cast<double>(k) / static_cast<double>(n);
        while (seg_idx + 2 < cum.size() && cum[seg_idx + 1] < s) {++seg_idx;}
        const double span = cum[seg_idx + 1] - cum[seg_idx];
        const double t = (span > 1e-12) ? (s - cum[seg_idx]) / span : 0.0;
        Pose2D q;
        q.x = in[first + seg_idx].x + t * (in[first + seg_idx + 1].x - in[first + seg_idx].x);
        q.y = in[first + seg_idx].y + t * (in[first + seg_idx + 1].y - in[first + seg_idx].y);
        // 与上一个输出点重合则跳过（避免重复点）
        if (!out.empty() && std::hypot(out.back().x - q.x, out.back().y - q.y) < 1e-9) {
          continue;
        }
        out.push_back(q);
      }
    } else {
      if (out.empty() || std::hypot(
          out.back().x - in[i].x, out.back().y - in[i].y) > 1e-9)
      {
        out.push_back(in[i]);
      }
    }
    i = j + 1;
  }
  // 末点
  if (out.empty() || std::hypot(
      out.back().x - in.back().x, out.back().y - in.back().y) > 1e-9 ||
    std::fabs(out.back().yaw - in.back().yaw) > 1e-9)
  {
    out.push_back(in.back());
  }

  // 航向 = 切线（**但旋转点保留原航向**，不覆盖）
  for (size_t k = 0; k + 1 < out.size(); ++k) {
    const double ds = std::hypot(out[k + 1].x - out[k].x, out[k + 1].y - out[k].y);
    if (ds < kRotEps) {continue;}   // 旋转点：航向是它的语义，不改成切线
    out[k].yaw = std::atan2(out[k + 1].y - out[k].y, out[k + 1].x - out[k].x);
  }
  if (out.size() >= 2) {
    const size_t last = out.size() - 1;
    const double ds = std::hypot(
      out[last].x - out[last - 1].x, out[last].y - out[last - 1].y);
    if (ds >= kRotEps) {
      out[last].yaw = std::atan2(
        out[last].y - out[last - 1].y, out[last].x - out[last - 1].x);
    }
  }
  return out;
}

// 删除重复点（位置重合）。**必须做**：优化器把控制点拉到同一位置、
// 或重采样在端点上重复取点，都会产生零长度段；零长度段会让
// 「末点航向 = 末段切线」的归一化失效（段方向无定义，`atan2(0,0)=0`），
// 实测表现为末点航向 0.824 与段方向 0 不符。
inline std::vector<Pose2D> removeDuplicates(
  const std::vector<Pose2D> & in, double eps = 1e-6)
{
  std::vector<Pose2D> out;
  out.reserve(in.size());
  for (size_t i = 0; i < in.size(); ++i) {
    const Pose2D & p = in[i];
    if (!out.empty()) {
      const double d = std::hypot(p.x - out.back().x, p.y - out.back().y);
      if (d < eps) {
        // 位置相同。分两种情形，**不能一刀切**：
        //
        // * **末尾**的重复点 = 数值冗余（优化器把末控制点拉到同一位置、
        //   或重采样在端点重复取点）。必须删 —— 零长度段会让「末段切线」
        //   无定义（`atan2(0,0)=0`），实测让末点航向 0.824 与段方向 0 不符。
        // * **中间**的重复点 = 原地旋转。必须保留 —— 那是语义，不是冗余。
        const bool is_last = (i + 1 == in.size());
        if (is_last) {
          // 用末点的航向覆盖，位置保持（末点必须是 goal）。
          out.back().yaw = p.yaw;
          continue;
        }
        if (std::fabs(normalizeAngle(p.yaw - out.back().yaw)) < 1e-9) {continue;}
      }
    }
    out.push_back(p);
  }
  return out;
}

// 删除冗余共线点（夹角小于 `angle_tol` 视为共线）。
inline std::vector<Pose2D> removeCollinear(
  const std::vector<Pose2D> & in, double angle_tol)
{
  if (in.size() < 3) {return in;}
  std::vector<Pose2D> out;
  out.reserve(in.size());
  out.push_back(in.front());
  for (size_t i = 1; i + 1 < in.size(); ++i) {
    const double a1 = std::atan2(in[i].y - out.back().y, in[i].x - out.back().x);
    const double a2 = std::atan2(in[i + 1].y - in[i].y, in[i + 1].x - in[i].x);
    if (std::fabs(normalizeAngle(a2 - a1)) > angle_tol) {
      out.push_back(in[i]);
    }
  }
  out.push_back(in.back());
  return out;
}

// 保端点的移动平均平滑（弹性带的「松弛」）。
//
// ## 为什么必须有这一步（实测驱动的修正）
//
// Hybrid A* 回溯出来的路径是**分段圆弧的拼接**，曲率在基元边界处**跳变**。
// 时间参数化的角加速度复核（`w_acc = Δω/Δt`）会把它算成几十 rad/s² —— 实测一个
// 「直道接 R=1 m 圆弧」的路径算出 `w_acc = 16.9 rad/s²`，远超 `w_acc_max = 2.0`。
//
// 这不是判据太严，而是**路径本身不可执行**：真实差速车的转向不能瞬变。
// 若不做平滑，搜索路径永远过不了动力学复核，等于「优化失败就没有可用路径」——
// 与 ADR-0048「优化失败回退到搜索原始路径」直接矛盾。
//
// 所以平滑是**路径构造的一部分**，不是优化的可选项。
//
// ## 为什么用移动平均而不是高斯
//
// 移动平均的支撑是有限窗口、实现无参数歧义（窗口宽度即物理长度），且**保端点**
// 是显式的（首尾不参与平均）。高斯核的截断会引入额外的 σ 参数，没有物理依据。
//
// ## 为什么首尾必须不动
//
// 首点 = 当前车位（否则路径第一点与车不符，消费侧前视会跳）；
// 末点 = goal（否则 `goal_consistent_with_path` 判不一致 → 零速）。
inline std::vector<Pose2D> smoothPathMovingAverage(
  const std::vector<Pose2D> & in, int passes, int half_window)
{
  if (in.size() < 3 || passes <= 0) {return in;}
  // 说明见下方 `smoothPathMovingAverageGuarded`：本函数**不检查碰撞**，
  // 直接调用它会让平滑把路径推进障碍（实测 sparse_map：raw/resampled 都无碰撞，
  // smoothed 在 index 106 撞上）。生产路径必须用带守卫的版本。
  const int hw = std::max(1, half_window);
  // 说明：`half_window` 的单位是**点**。调用方按 `smoothing_window_m / resample_spacing_m`
  // 换算，使平滑尺度与点密度解耦（改重采样间距不会静默改变平滑强度）。
  std::vector<Pose2D> cur = in;
  std::vector<Pose2D> next = in;
  for (int pass = 0; pass < passes; ++pass) {
    for (size_t i = 0; i < cur.size(); ++i) {
      // 端点固定：不参与平均，也不被平均移动。
      if (i == 0 || i + 1 == cur.size()) {
        next[i] = cur[i];
        continue;
      }
      double sx = 0.0, sy = 0.0;
      int n = 0;
      const int lo = std::max(0, static_cast<int>(i) - hw);
      const int hi = std::min(static_cast<int>(cur.size()) - 1, static_cast<int>(i) + hw);
      for (int k = lo; k <= hi; ++k) {
        sx += cur[static_cast<size_t>(k)].x;
        sy += cur[static_cast<size_t>(k)].y;
        ++n;
      }
      next[i].x = sx / static_cast<double>(n);
      next[i].y = sy / static_cast<double>(n);
      next[i].yaw = cur[i].yaw;
    }
    cur.swap(next);
  }
  // 航向 = 平滑后位置的切线
  for (size_t i = 0; i + 1 < cur.size(); ++i) {
    cur[i].yaw = std::atan2(cur[i + 1].y - cur[i].y, cur[i + 1].x - cur[i].x);
  }
  if (cur.size() >= 2) {
    cur.back().yaw = cur[cur.size() - 2].yaw;
  }
  return cur;
}

// 带碰撞守卫的平滑：**从原始路径重跑 k 遍，取最后一个无碰撞的 k**。
//
// ## 为什么必须有守卫（实测驱动的修正）
//
// 移动平均会削掉转弯的内角。在窄通道里，被削掉的那一点正好是障碍 ——
// 路径从「绕过去」变成「抄近路穿过障碍」。
//
// 实测（`sparse_map`，车位 `(-34,-6)` → 目标 `(-2.5,0)`）：
//
// ```text
// raw        280 点  first_collision=-1   （搜索路径本身无碰撞）
// resampled  148 点  first_collision=-1
// smoothed   148 点  first_collision=106  at (-10.565,-5.676)   ← 平滑引入的
// ```
//
// ## 为什么「从原始重跑 k 遍」而不是「逐遍累积」
//
// 两者**不等价**（移动平均不满足半群性质：`S(S(x)) != S²(x)` 在边界处不同）。
// 实测（同一条路径）：
//
// ```text
// 从原始重跑:  k=0 maxκ=1.027 | k=1 1.301 | k=2 0.701(无碰撞) | k=3 0.523(碰撞)
// 逐遍累积:    k=1 maxκ=1.301(无碰撞) | k=2 0.701(碰撞)  ← 停在这里
// ```
//
// 累积版本在 k=2 就撞了，于是回退到 k=1 的 1.301（超 kappa_max）；
// 而**从原始重跑**的 k=2 是 0.701 且无碰撞 —— 那才是想要的。
//
// 所以：对 `k = 0..passes` 各算一遍，保留**最后一个无碰撞**的。
// 这既保证不引入碰撞，又尽量拿到最好的平滑度。
//
// `collides` 由调用方提供（规划器传 footprint 检查；单测可传 nullptr 表示不检查）。
// 前向声明：`computeCurvature` 定义在本文件后半部分，但守卫需要它评估曲率。
inline std::vector<double> computeCurvature(const std::vector<Pose2D> & poses);

inline std::vector<Pose2D> smoothPathMovingAverageGuarded(
  const std::vector<Pose2D> & in, int passes, int half_window,
  const std::function<bool(const Pose2D &)> & collides,
  double resample_spacing)
{
  if (in.size() < 3 || passes <= 0) {return in;}
  if (!collides) {return smoothPathMovingAverage(in, passes, half_window);}

  auto worst_kappa = [&](const std::vector<Pose2D> & path) {
      const std::vector<Pose2D> rs = resampleByArcLength(path, resample_spacing);
      const std::vector<double> k = computeCurvature(rs);
      double m = 0.0;
      for (double v : k) {m = std::max(m, std::fabs(v));}
      return m;
    };

  // `best` 是**已知可行**的路径；调用方保证传入的 `in` 通过碰撞检查。
  std::vector<Pose2D> best = in;
  double best_kappa = worst_kappa(in);
  for (int k = 1; k <= passes; ++k) {
    // **从原始 `in` 重跑 k 遍**（移动平均不满足半群性质，逐遍累积不等价）。
    const std::vector<Pose2D> candidate = smoothPathMovingAverage(in, k, half_window);
    bool bad = false;
    for (const Pose2D & q : candidate) {
      if (collides(q)) {bad = true; break;}
    }
    if (bad) {continue;}          // 这一档撞了：跳过
    const double mk = worst_kappa(candidate);
    if (mk < best_kappa) {         // 只接受**曲率更优**的
      best = candidate;
      best_kappa = mk;
    }
  }
  return best;
}

// 曲率：**相邻两段的方向变化 / 弧长**（`κ = Δθ / Δs`）。
//
// ## 为什么不用三点圆拟合（实测驱动的修正）
//
// 三点圆拟合在**基元接缝**处会放大：当曲率从 `+1.0` 跳到 `-1.0` 时，
// 拟合跨过接缝看到的是两段转角之和，报出 2 倍甚至 3 倍的值。
//
// 实测（`sparse_map`，车位 `(-34,-6)` → 目标 `(-2.5,0)`）：
//
// ```text
// 单条基元的曲率（按构造）  : 最大 1.0 /m     ← 合规
// 路径的三点拟合曲率        : 2.928 /m       ← 报"超限"
// ```
//
// 而那个跳变**物理上并不超限**：相邻 0.1 m 内从 `+1.0` 到 `-1.0` 需要
// `dω = 0.6 rad/s`，在 `dt = 0.333 s` 内是 `1.8 rad/s²` —— 在 `w_acc_max = 2.0` 之内。
// 也就是说三点拟合报的「超限」是**度量假象**，真正的物理约束（角加速度）是满足的。
//
// ## 为什么 `Δθ/Δs` 才是对的
//
// 差速车的转向率是 `ω = κ·v`。`κ = Δθ/Δs` 直接就是「每走一米转多少弧度」，
// 与 `ω` 一一对应，没有放大。它也是时间参数化真正需要的量。
//
// **三点圆拟合仍保留**（`computeCurvatureSmooth`），但只用于**优化器的平滑代价**，
// 不进硬判据 —— 那里它衡量的是"弯得顺不顺"，放大反而是有用的信号。
inline std::vector<double> computeCurvature(const std::vector<Pose2D> & poses)
{
  std::vector<double> k(poses.size(), 0.0);
  if (poses.size() < 2) {return k;}
  // κ_i = Δθ_i / Δs_i，其中 Δθ 是「进入 i 的方向」到「离开 i 的方向」之差。
  // 端点用单侧。
  for (size_t i = 0; i < poses.size(); ++i) {
    // 前一段方向（i-1 → i）与后一段方向（i → i+1）
    double th_in = 0.0, th_out = 0.0;
    bool have_in = false, have_out = false;
    double ds_in = 0.0, ds_out = 0.0;
    if (i > 0) {
      ds_in = std::hypot(poses[i].x - poses[i - 1].x, poses[i].y - poses[i - 1].y);
      if (ds_in > 1e-6) {
        th_in = std::atan2(poses[i].y - poses[i - 1].y, poses[i].x - poses[i - 1].x);
        have_in = true;
      }
    }
    if (i + 1 < poses.size()) {
      ds_out = std::hypot(poses[i + 1].x - poses[i].x, poses[i + 1].y - poses[i].y);
      if (ds_out > 1e-6) {
        th_out = std::atan2(poses[i + 1].y - poses[i].y, poses[i + 1].x - poses[i].x);
        have_out = true;
      }
    }
    if (have_in && have_out) {
      const double dth = normalizeAngle(th_out - th_in);
      // 曲率定义在**半段**上：Δθ 跨 ds_in/2 + ds_out/2
      const double ds = 0.5 * (ds_in + ds_out);
      k[i] = (ds > 1e-9) ? (dth / ds) : 0.0;
    } else if (have_out) {
      // 首点：单侧 —— 用「进入方向 = 路径起点航向」与「离开方向」之差
      const double dth = normalizeAngle(th_out - poses[i].yaw);
      k[i] = (ds_out > 1e-9) ? (dth / ds_out) : 0.0;
    } else if (have_in) {
      // **末点**：没有「离开方向」，只能用「进入方向」与「点自己的航向」之差。
      // 但末点航向是由末段切线归一化来的（等于 th_in），于是 dth ≡ 0 —— 那没信息。
      // 正确做法：末点**沿用倒数第二点的曲率**（曲线在端点外是外推，不该凭空造一个
      // 尖峰）。实测：不这样做时末点报 -1.304，而它前一点只有 -0.4 量级 ——
      // 那是 `ds_next = 0` 造成的差分假象，不是真实转向。
      k[i] = (i > 0) ? k[i - 1] : 0.0;
    }
  }
  return k;
}

// 三点圆拟合曲率（**仅供优化器的平滑代价**，不进硬判据）。
inline std::vector<double> computeCurvatureSmooth(const std::vector<Pose2D> & poses)
{
  std::vector<double> k(poses.size(), 0.0);
  if (poses.size() < 3) {return k;}
  for (size_t i = 1; i + 1 < poses.size(); ++i) {
    const double x0 = poses[i - 1].x, y0 = poses[i - 1].y;
    const double x1 = poses[i].x, y1 = poses[i].y;
    const double x2 = poses[i + 1].x, y2 = poses[i + 1].y;
    const double a = std::hypot(x1 - x0, y1 - y0);
    const double b = std::hypot(x2 - x1, y2 - y1);
    const double c = std::hypot(x2 - x0, y2 - y0);
    const double denom = a * b * c;
    if (denom < 1e-12) {k[i] = 0.0; continue;}
    // 有向面积的两倍
    const double cross = (x1 - x0) * (y2 - y0) - (y1 - y0) * (x2 - x0);
    k[i] = 2.0 * cross / denom;
  }
  // 端点单侧
  k.front() = k[1];
  k.back() = k[k.size() - 2];
  return k;
}

// 优化器：把一条折线当作**弹性带**，只移动内部点。
//
// **为什么是弹性带而不是真 B 样条**：ADR-0048 允许「二维三次 B 样条**或等价弹性带**」。
// 弹性带的控制点直接就是路径点，梯度可解析、无需解节点向量、无需处理重节点，
// 且「固定首尾」天然成立。真 B 样条的优势（C² 连续）在这里由「曲率代价项 + 重采样」
// 补足 —— 最终交给时间参数化的是密集采样后的折线，其曲率已被显式约束。
class SplineOptimizer2D
{
public:
  struct Result
  {
    bool ok{false};
    std::vector<Pose2D> poses;
    double final_cost{std::numeric_limits<double>::infinity()};
    int iterations{0};
  };

  Result optimize(
    const std::vector<Pose2D> & input, const DistanceField2D & df,
    const GridView & g, const PlannerParams & p) const
  {
    Result res;
    if (input.size() < 3 || !df.valid()) {
      res.poses = input;
      return res;
    }

    // ① 按弧长重采样 ② 删共线点（降低变量数，避免平滑项被密集点主导）
    std::vector<Pose2D> pts = resampleByArcLength(input, p.resample_spacing_m);
    pts = removeCollinear(pts, 0.05);
    if (pts.size() < 3) {
      res.poses = input;
      return res;
    }

    // 固定首尾：首点 = 当前车位，末点 = goal。中间点才是变量。
    const Pose2D first = pts.front();
    const Pose2D last = pts.back();
    std::vector<double> qx, qy;
    qx.reserve(pts.size());
    qy.reserve(pts.size());
    for (const Pose2D & q : pts) {
      qx.push_back(q.x);
      qy.push_back(q.y);
    }

    const double step = std::max(p.resample_spacing_m, 1e-3);
    const auto t0 = std::chrono::steady_clock::now();

    double cost = costOf(qx, qy, df, step, p);
    double lr = 0.05;   // 初始步长（米量级）
    int it = 0;
    for (; it < p.optimization_max_iterations; ++it) {
      const double elapsed = std::chrono::duration<double>(
        std::chrono::steady_clock::now() - t0).count();
      if (elapsed > p.optimization_time_budget_s) {break;}

      // 数值梯度（中心差分）。变量数 = 2*(N-2)，N 通常 < 200。
      const size_t n = qx.size();
      const double eps = 1e-4;
      double max_grad = 0.0;
      std::vector<double> gx(n, 0.0), gy(n, 0.0);
      for (size_t i = 1; i + 1 < n; ++i) {
        const double save_x = qx[i], save_y = qy[i];
        qx[i] = save_x + eps;
        const double cp = costOf(qx, qy, df, step, p);
        qx[i] = save_x - eps;
        const double cm = costOf(qx, qy, df, step, p);
        qx[i] = save_x;
        gx[i] = (cp - cm) / (2.0 * eps);

        qy[i] = save_y + eps;
        const double cp2 = costOf(qx, qy, df, step, p);
        qy[i] = save_y - eps;
        const double cm2 = costOf(qx, qy, df, step, p);
        qy[i] = save_y;
        gy[i] = (cp2 - cm2) / (2.0 * eps);

        max_grad = std::max(max_grad, std::hypot(gx[i], gy[i]));
      }
      if (max_grad < 1e-6) {break;}

      // Armijo 回溯线搜索：保证代价单调下降。
      bool improved = false;
      for (int trial = 0; trial < 8; ++trial) {
        for (size_t i = 1; i + 1 < n; ++i) {
          qx[i] -= lr * gx[i];
          qy[i] -= lr * gy[i];
        }
        // 首尾强制不变（数值上不会动，但显式写出来避免将来改梯度时出错）
        qx.front() = first.x; qy.front() = first.y;
        qx.back() = last.x; qy.back() = last.y;

        const double nc = costOf(qx, qy, df, step, p);
        if (nc < cost - 1e-12) {
          cost = nc;
          improved = true;
          break;
        }
        // 回退并缩小步长
        for (size_t i = 1; i + 1 < n; ++i) {
          qx[i] += lr * gx[i];
          qy[i] += lr * gy[i];
        }
        lr *= 0.5;
      }
      if (!improved) {break;}
      lr = std::min(lr * 1.2, 0.2);   // 成功则略微放大步长
    }

    res.poses.clear();
    res.poses.reserve(qx.size());
    for (size_t i = 0; i < qx.size(); ++i) {
      Pose2D q;
      q.x = qx[i];
      q.y = qy[i];
      res.poses.push_back(q);
    }
    // 航向 = 切线
    for (size_t i = 0; i + 1 < res.poses.size(); ++i) {
      res.poses[i].yaw = std::atan2(
        res.poses[i + 1].y - res.poses[i].y,
        res.poses[i + 1].x - res.poses[i].x);
    }
    if (res.poses.size() >= 2) {
      res.poses.back().yaw = res.poses[res.poses.size() - 2].yaw;
    }
    (void)g;
    res.ok = true;
    res.final_cost = cost;
    res.iterations = it;
    return res;
  }

private:
  // 目标函数（ADR-0048 的 J）。
  static double costOf(
    const std::vector<double> & qx, const std::vector<double> & qy,
    const DistanceField2D & df, double step, const PlannerParams & p)
  {
    const size_t n = qx.size();
    if (n < 3) {return std::numeric_limits<double>::infinity();}
    double smooth = 0.0, clear = 0.0, curv = 0.0, length = 0.0;

    // 平滑：二阶差分平方（弹性带的「弯曲能量」）
    for (size_t i = 1; i + 1 < n; ++i) {
      const double dx = qx[i + 1] - 2.0 * qx[i] + qx[i - 1];
      const double dy = qy[i + 1] - 2.0 * qy[i] + qy[i - 1];
      smooth += dx * dx + dy * dy;
    }

    // 离障：低于目标净空的部分平方惩罚
    for (size_t i = 1; i + 1 < n; ++i) {
      const double d = df.distanceAt(qx[i], qy[i]);
      if (!std::isfinite(d)) {continue;}   // 全图无阻挡
      const double short_fall = std::max(0.0, p.clearance_target_m - d);
      clear += short_fall * short_fall;
    }

    // 曲率：三点圆拟合，超限部分平方
    for (size_t i = 1; i + 1 < n; ++i) {
      const double x0 = qx[i - 1], y0 = qy[i - 1];
      const double x1 = qx[i], y1 = qy[i];
      const double x2 = qx[i + 1], y2 = qy[i + 1];
      const double a = std::hypot(x1 - x0, y1 - y0);
      const double b = std::hypot(x2 - x1, y2 - y1);
      const double c = std::hypot(x2 - x0, y2 - y0);
      const double denom = a * b * c;
      if (denom < 1e-12) {continue;}
      const double cross = (x1 - x0) * (y2 - y0) - (y1 - y0) * (x2 - x0);
      const double kappa = std::fabs(2.0 * cross / denom);
      const double over = std::max(0.0, kappa - p.kappa_max);
      curv += over * over;
    }

    // 曲率**变化率**：相邻三点曲率之差。这一项是「角加速度可行」的直接来源 ——
    // 只罚曲率幅值时，一条处处曲率 0.6 但相邻点从 +0.6 跳到 -0.6 的路径会被放行，
    // 而它对应的角加速度远超上限（实测 2.96 vs 2.0）。
    double curv_rate = 0.0;
    {
      double prev_k = 0.0;
      bool have_prev = false;
      for (size_t i = 1; i + 1 < n; ++i) {
        const double x0 = qx[i - 1], y0 = qy[i - 1];
        const double x1 = qx[i], y1 = qy[i];
        const double x2 = qx[i + 1], y2 = qy[i + 1];
        const double a = std::hypot(x1 - x0, y1 - y0);
        const double b = std::hypot(x2 - x1, y2 - y1);
        const double c = std::hypot(x2 - x0, y2 - y0);
        const double denom = a * b * c;
        if (denom < 1e-12) {continue;}
        const double cross = (x1 - x0) * (y2 - y0) - (y1 - y0) * (x2 - x0);
        const double kappa = 2.0 * cross / denom;
        if (have_prev) {
          const double dk = kappa - prev_k;
          curv_rate += dk * dk;
        }
        prev_k = kappa;
        have_prev = true;
      }
    }

    // 长度
    for (size_t i = 1; i < n; ++i) {
      length += std::hypot(qx[i] - qx[i - 1], qy[i] - qy[i - 1]);
    }

    // 终端航向误差：末段切线 vs 期望（末点航向由调用方在复核阶段再验，这里用
    // 「末段方向与倒数第二段方向一致」的连续项代替，避免引入不存在的目标朝向）。
    double heading = 0.0;
    if (n >= 3) {
      const double a1 = std::atan2(qy[n - 2] - qy[n - 3], qx[n - 2] - qx[n - 3]);
      const double a2 = std::atan2(qy[n - 1] - qy[n - 2], qx[n - 1] - qx[n - 2]);
      const double e = normalizeAngle(a2 - a1);
      heading = e * e;
    }
    (void)step;

    return p.lambda_smooth * smooth
      + p.lambda_clearance * clear
      + p.lambda_curvature * curv
      + p.lambda_curvature_rate * curv_rate
      + p.lambda_length * length
      + p.lambda_heading * heading;
  }
};

}  // namespace planner
}  // namespace agc_ground

#endif  // AGC_GROUND__SPLINE_OPTIMIZER_2D_HPP_
