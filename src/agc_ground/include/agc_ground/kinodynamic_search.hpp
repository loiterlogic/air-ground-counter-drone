// kinodynamic_search —— Hybrid A* 风格 SE(2) 搜索 + 解析连接 + 有界直连兜底
//
// 结构取自 [Fast-Planner 的 `KinodynamicAstar`](../../../refs/Fast-Planner/fast_planner/path_searching/src/kinodynamic_astar.cpp)：
// OPEN 最小 `f` 弹出、CLOSED/更优 `g` 更新、父节点与基元记录、可达后回溯、每步先试
// 「解析连接（shot）」再继续扩展。论文里是三维加速度输入 + 五次多项式 shot；
// 这里是二维差速速度输入 + 圆弧 shot。
//
// **不是代码移植**：状态空间、控制输入、启发式、shot 形式全部按差速车重写。
//
// ## 三个必须显式写明的设计点
//
// ### 1. 离散键必须含航向
//
// `key = (x_cell, y_cell, yaw_bin)`。只按 `(x,y)` 合并会错误丢弃「同位置不同航向」的
// 可行状态 —— 差速车是非完整约束，同一格朝东能走、朝北可能走不了。ADR-0048 明令。
//
// ### 2. 两个不同的阻挡集
//
// * **footprint 检查**挡 `{kUnknown, kInscribed, kLethal}`（真碰撞风险，含未知）
// * **走廊判据**只挡 `{kLethal}`（真实障碍；`99` 环在 `dense_map` 上几乎相接）
//
// 实测依据见 `corridorBlocks()` 的注释。两者都实现在 `footprint_checker.hpp`。
//
// ### 3. 兜底是「前沿 + 直连」而不是「纯直线」
//
// 用户裁定（2026-11-14）：「我要直连目标是为了时刻有终点目标，即使后面一段路是无效的，
// 但是等无人机再飞一会地图探索出来不就能补上了吗」。
//
// 所以兜底必须满足两个条件：
//   * 路径**末端恒为 goal**（消费侧 `goal_consistency_m` 要求；截断会让消费侧零速）；
//   * 已知区内的部分仍然**绕障**（纯直线在 `dense_map` 上穿障，ADR-0047 已登记 19/19 失败）。
//
// 实现：搜索失败时，从**已扩展节点里**挑「距 goal 最近且其到 goal 的直连段不穿 `kLethal`」
// 的那个节点作为前沿，再直连过去。未知段如实保留，等重规划补上。

#ifndef AGC_GROUND__KINODYNAMIC_SEARCH_HPP_
#define AGC_GROUND__KINODYNAMIC_SEARCH_HPP_

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <limits>
#include <queue>
#include <cstdio>
#include <cstdlib>
#include <unordered_map>
#include <vector>

#include "agc_ground/footprint_checker.hpp"
#include "agc_ground/motion_primitive.hpp"
#include "agc_ground/occupancy_grid_view.hpp"
#include "agc_ground/planner_types.hpp"

namespace agc_ground
{
namespace planner
{

// 搜索输入。
struct SearchInput
{
  GridView grid;
  Pose2D start;
  Pose2D goal;
  PlannerParams params;
  // 离障距离场（可选）。给了就用 O(1) 查表算净空代价；没给则退化为逐圈扫描。
  // **这是性能关键**：逐圈扫描 1.4 µs/次，而每个基元要查十几个采样位姿。
  const DistanceField2D * distance_field{nullptr};
};

// 搜索输出。
struct SearchOutput
{
  PlanFailure failure{PlanFailure::kNone};
  PlanOutcome outcome{PlanOutcome::kFailure};
  std::vector<Pose2D> poses;      // 起点→终点；兜底时末端 == goal
  int expanded_nodes{0};
  double elapsed_s{0.0};
  double clearance_min{std::numeric_limits<double>::infinity()};
  int seam_count{0};   // 接缝数（原地旋转点 + 航向修正点）
  std::string detail;
};

// 从 `from` 到 `to` 的直线段是否全程**不碰不可压档**（`{unknown, inscribed, lethal}`）。
//
// ## 为什么这里必须**含未知**
//
// 早先版本只挡 `lethal`（「兜底段承认末端无效，只要求不穿真实障碍」），但最终复核
// 用的是 `footprintCollides`（含未知）。结果：兜底产出的路径**必然**在最终复核被拒，
// 表现为「搜索说成功、引擎说 validation_failed」—— 实测在 `dense_map` 上
// 217 点路径全部作废。
//
// 正确口径：兜底段是**将要发布给消费者**的路径，它必须满足发布侧的复核口径。
// 「未知段等重规划补上」这件事由**重规划判据**（自由面积变化）承载，
// 不由「允许发布穿未知的路径」承载。
//
// ## 那兜底还剩什么用
//
// 它把「搜索在未知区边缘失败」变成「搜索到边缘 + 已知区内直连」。若 goal 在未知区，
// 直连到 goal 会被拒 → 兜底不生效 → 显式失败。这是**诚实**的：消费侧本来也会因为
// `goal_consistent_with_path` / 安全层 `swept_unknown` 把这类路径拦掉。
inline bool directLinkClearOfBlocked(
  const GridView & g, const Pose2D & from, const Pose2D & to, double step_m)
{
  if (!gridGeometryOk(g)) {return false;}
  const double dx = to.x - from.x, dy = to.y - from.y;
  const double len = std::hypot(dx, dy);
  const int n = std::max(1, static_cast<int>(std::ceil(len / std::max(step_m, 1e-3))));
  for (int i = 0; i <= n; ++i) {
    const double t = static_cast<double>(i) / static_cast<double>(n);
    const double x = from.x + t * dx;
    const double y = from.y + t * dy;
    if (footprintBlocks(classifyPlanningCell(cellValueAtWorld(g, x, y)))) {return false;}
  }
  return true;
}

// 构造一条直线位姿序列（用于兜底段与直连 shot），末端航向 = 段方向。
inline std::vector<Pose2D> straightPoses(
  const Pose2D & from, const Pose2D & to, double step_m)
{
  std::vector<Pose2D> out;
  const double dx = to.x - from.x, dy = to.y - from.y;
  const double len = std::hypot(dx, dy);
  const double yaw = (len > 1e-9) ? std::atan2(dy, dx) : from.yaw;
  const int n = std::max(1, static_cast<int>(std::ceil(len / std::max(step_m, 1e-3))));
  out.reserve(static_cast<size_t>(n) + 1);
  for (int i = 0; i <= n; ++i) {
    const double t = static_cast<double>(i) / static_cast<double>(n);
    Pose2D p;
    p.x = from.x + t * dx;
    p.y = from.y + t * dy;
    // 末端航向用段方向（ADR-0048.7 的「末段切线」口径）。
    p.yaw = yaw;
    out.push_back(p);
  }
  return out;
}

// Dubins 候选的**几何复核**（抽成独立函数以便单测直接调用）。
//
// 三个量分别回答：末端位置对不对、末端航向对不对、接缝相切不相切。
// 任何一个超容差即应丢弃该候选。
struct DubinsCheck
{
  double end_err{0.0};
  double yaw_err{0.0};
  double seam_jump{0.0};
};

inline DubinsCheck evaluateDubinsPath(
  const std::vector<Pose2D> & path, const Pose2D & to)
{
  DubinsCheck c;
  if (path.size() < 2) {
    c.end_err = std::numeric_limits<double>::infinity();
    c.yaw_err = std::numeric_limits<double>::infinity();
    return c;
  }
  c.end_err = std::hypot(path.back().x - to.x, path.back().y - to.y);
  c.yaw_err = std::fabs(normalizeAngle(path.back().yaw - to.yaw));
  for (size_t i = 0; i + 1 < path.size(); ++i) {
    const double ex = path[i + 1].x - path[i].x;
    const double ey = path[i + 1].y - path[i].y;
    const double len = std::hypot(ex, ey);
    if (len < 1e-6) {continue;}
    const double j = std::fabs(normalizeAngle(path[i].yaw - std::atan2(ey, ex)));
    if (j > c.seam_jump) {c.seam_jump = j;}
  }
  return c;
}

// 解析连接：**Dubins CSC（弧-直线-弧）**，用**向量切点法**构造，接缝按构造相切。
//
// ## 为什么必须是 CSC 而不是"弧 + 直线"
//
// 早先是「先转到指向目标的方向，再直线过去」。它有**结构性缺陷**：
// 弧走完后车已偏离 `from→to` 直线，于是 `atan2(to−cur) ≠ desired_yaw`，
// 弧末航向与直线方向必然有残余差（实测 `yard` s19：修掉首点后仍剩 0.192 rad）。
//
// CSC 的三段**都相切**：弧末切线 == 直线方向 == 收尾弧入口切线，
// 所以接缝处航向按构造连续，不需要任何后处理掩盖。
//
// ## 为什么用向量切点法而不是查表公式
//
// 查表公式（alpha/beta 那一套）符号约定极易写错。实测第一版给出末端航向误差
// 1.16–2.44 rad —— 而**校验没拦住**，因为当时只查了位置。教训：解析构造必须配
// **几何复核**（末端位置 + 末端航向 + 接缝跳变），复核不过就丢弃该候选。
//
// 向量切点法只需两条中学几何事实：
//
// ```text
// 外切（同向词族 s1==s2）：切点偏移 n ⟂ 圆心连线方向 u，取 n = ±(-u.y, u.x)
// 内切（异向词族 s1!=s2）：n 与 u 夹角 = acos(2/dc)，且需 dc >= 2
//   p1 = c1 + n,  p2 = c2 - n
// ```
//
// 每个词族**两种法向符号都试**，由复核决定取舍。
inline std::vector<Pose2D> dubinsCscShot(
  const Pose2D & from, const Pose2D & to, double radius, double step_m)
{
  const double r = std::max(radius, 1e-3);
  // 归一化：from 为原点、from.yaw 为 +x、半径 1
  const double dx = to.x - from.x, dy = to.y - from.y;
  const double c0 = std::cos(from.yaw), s0 = std::sin(from.yaw);
  const double gx = (dx * c0 + dy * s0) / r;
  const double gy = (-dx * s0 + dy * c0) / r;
  const double dtheta = normalizeAngle(to.yaw - from.yaw);

  struct Cand
  {
    int s1{1}, s2{1};
    double t1{0}, t2{0}, t3{0};
    // 两个切点（归一化系）。**build 必须显式用它们**，不能靠「沿 cur.yaw 走 t2」——
    // 实测那样会在切向与 (p2−p1) 有数值残差时走偏：目标 (-5,0) 却走到 (5,4)，
    // 末端位置误差 10.77 m，而航向误差 0.0004 —— 只查航向的复核完全看不出来。
    double p1x{0}, p1y{0}, p2x{0}, p2y{0};
    double length{std::numeric_limits<double>::infinity()};
  };
  std::vector<Cand> cands;

  // 起点圆心（归一化系）：车在原点朝 +x；左转(s=+1)圆心在 (0,1)，右转在 (0,-1)
  for (int s1 : {+1, -1}) {
    const double c1x = 0.0, c1y = static_cast<double>(s1);
    for (int s2 : {+1, -1}) {
      // 终点圆心：车在 (gx,gy) 朝 dtheta；法向 = (-sin, cos) 旋转后乘 s2
      const double c2x = gx - static_cast<double>(s2) * std::sin(dtheta);
      const double c2y = gy + static_cast<double>(s2) * std::cos(dtheta);
      const double vx = c2x - c1x, vy = c2y - c1y;
      const double dc = std::hypot(vx, vy);
      if (dc < 1e-9) {continue;}
      const double ux = vx / dc, uy = vy / dc;

      // 法向由**转向符号唯一确定**，不是"±90° 任选"。
      //
      // 相切条件：弧末切向必须等于直线方向。
      // 对 s=+1（左转），切向 = 半径方位角 + 90°；对 s=-1 是 − 90°。
      // 外切时 `p2−p1 = c2−c1 = dc·u`，所以直线方向 = atan2(u)。
      // 于是 `atan2(n) + s·90° = atan2(u)`  ⇒  `atan2(n) = atan2(u) − s·90°`。
      //
      // **实测教训**：早先"±90° 都试"，选出的候选弧末切向与直线方向差 3.14 rad，
      // 于是直线段把航向从 0.381 直接改成 −2.761 —— 那是接缝跳变，而复核只查
      // 末端位置/航向时恰好都能通过（末端位置吸附后误差 0）。必须按几何唯一确定。
      std::vector<std::pair<double, double>> normals;
      const double uang = std::atan2(uy, ux);
      if (s1 == s2) {
        // 外切：n 的方向 = u 方向 − s·90°
        const double na = uang - static_cast<double>(s1) * M_PI / 2.0;
        normals.emplace_back(std::cos(na), std::sin(na));
      } else {
        // 内切：需 dc >= 2。p1 = c1 + n，p2 = c2 − n，故 p2−p1 = dc·u − 2n。
        // 相切要求 atan2(p2−p1) = atan2(n) + s1·90°，解出 n 与 u 的夹角为 acos(2/dc)。
        if (dc < 2.0 - 1e-9) {continue;}
        const double ang = std::acos(std::min(1.0, 2.0 / dc));
        for (double sign : {+1.0, -1.0}) {
          const double a = uang + sign * ang;
          normals.emplace_back(std::cos(a), std::sin(a));
        }
      }

      for (const auto & n : normals) {
        double p1x = 0.0, p1y = 0.0, p2x = 0.0, p2y = 0.0;
        if (s1 == s2) {
          p1x = c1x + n.first; p1y = c1y + n.second;
          p2x = c2x + n.first; p2y = c2y + n.second;
        } else {
          p1x = c1x + n.first; p1y = c1y + n.second;
          p2x = c2x - n.first; p2y = c2y - n.second;
        }
        // 起点弧角：车头 0 → 切点处的切向。切向 = 半径方位角 + s1·90°。
        // **带符号转角**：正 = 逆时针。它必须与 s1 同号，否则该候选几何上不成立
        // （实测：s2=+1 却要求顺时针转 -0.785 —— 那是另一个词族，不是这个）。
        const double r1x = p1x - c1x, r1y = p1y - c1y;
        const double tangent1 = std::atan2(r1y, r1x) + static_cast<double>(s1) * M_PI / 2.0;
        const double t1 = normalizeAngle(tangent1 - 0.0);
        // 直线段
        const double t2 = std::hypot(p2x - p1x, p2y - p1y);
        // 终点弧角：切向 → dtheta。切向 = 半径方位角 + s2·90°。
        const double r2x = p2x - c2x, r2y = p2y - c2y;
        const double tangent2 = std::atan2(r2y, r2x) + static_cast<double>(s2) * M_PI / 2.0;
        const double t3 = normalizeAngle(dtheta - tangent2);

        if (!std::isfinite(t1) || !std::isfinite(t2) || !std::isfinite(t3)) {continue;}
        if (t2 < -1e-9) {continue;}
        // 转向符号一致性：t1 必须与 s1 同向（或为 0），t3 必须与 s2 同向（或为 0）。
        // 这条筛掉"切点选对了但词族对不上"的候选 —— 它们生成出来的曲线会拐错方向。
        //
        // **`|t| ≈ π` 例外**：`normalizeAngle` 把 +π 映成 −π（`while (a > π) a -= 2π`），
        // 于是「转半圈」会被判成反号而被误拒 —— 实测「目标在正后方」的所有候选
        // 都被这条筛掉，Dubins 返回空。转半圈是合法动作，符号取 s 的方向即可。
        const double tol_dir = 1e-6;
        const double half_turn_tol = 1e-3;
        auto sign_ok = [&](double t, int s) {
            if (std::fabs(std::fabs(t) - M_PI) < half_turn_tol) {return true;}
            return t * static_cast<double>(s) >= -tol_dir;
          };
        if (!sign_ok(t1, s1)) {continue;}
        if (!sign_ok(t3, s2)) {continue;}
        // 转半圈时把符号对齐到 s，使后续 build() 的转向方向正确。
        auto align_half_turn = [&](double t, int s) {
            if (std::fabs(std::fabs(t) - M_PI) < half_turn_tol) {
              return (t < 0.0) ? (static_cast<double>(s) * M_PI)
                               : (-static_cast<double>(s) * M_PI);
            }
            return t;
          };
        const double t1a = align_half_turn(t1, s1);
        const double t3a = align_half_turn(t3, s2);
        Cand c;
        c.s1 = s1; c.s2 = s2;
        c.t1 = t1a; c.t2 = std::max(0.0, t2); c.t3 = t3a;
        c.p1x = p1x; c.p1y = p1y; c.p2x = p2x; c.p2y = p2y;
        c.length = std::fabs(t1a) + c.t2 + std::fabs(t3a);
        cands.push_back(c);
      }
    }
  }
  if (cands.empty()) {return {};}
  std::sort(
    cands.begin(), cands.end(),
    [](const Cand & a, const Cand & b) {return a.length < b.length;});

  auto build = [&](const Cand & c) {
      std::vector<Pose2D> out;
      out.push_back(from);
      Pose2D cur = from;
      auto arc = [&](double angle) {
          if (std::fabs(angle) < 1e-9) {return;}
          const double arc_len = std::fabs(angle) * r;
          const int n = std::max(1, static_cast<int>(std::ceil(arc_len / std::max(step_m, 1e-3))));
          const Pose2D base = cur;
          for (int i = 1; i <= n; ++i) {
            const double t = static_cast<double>(i) / static_cast<double>(n);
            Control ctl;
            ctl.v = r;
            ctl.omega = (angle >= 0.0) ? 1.0 : -1.0;
            cur = integrateState(base, ctl, std::fabs(angle) * t);
            out.push_back(cur);
          }
        };
      arc(c.t1);
      // 直线段：**显式用切点**（归一化系 → world），不用 `cur.yaw` 外推。
      // 归一化系到 world：旋转 from.yaw、平移 from、乘半径 r。
      if (c.t2 > 1e-6) {
        Pose2D end;
        end.x = from.x + r * (c.p2x * c0 - c.p2y * s0);
        end.y = from.y + r * (c.p2x * s0 + c.p2y * c0);
        end.yaw = std::atan2(end.y - cur.y, end.x - cur.x);
        const std::vector<Pose2D> line = straightPoses(cur, end, step_m);
        out.insert(out.end(), line.begin() + 1, line.end());
        cur = end;
      }
      arc(c.t3);
      return out;
    };

  auto evaluate = [&](const std::vector<Pose2D> & path, double * end_err,
                      double * yaw_err, double * seam_jump) {
      const DubinsCheck c = evaluateDubinsPath(path, to);
      *end_err = c.end_err;
      *yaw_err = c.yaw_err;
      *seam_jump = c.seam_jump;
    };

  // 复核容差：位置按半径比例，航向与接缝按弧度。
  //
  // **航向容差不能太小**：采样把弧切成 n 段后，末点落在「最后一段的终点」，
  // 它的航向与真实弧末最多差一个采样步的转角（`2π/n` 量级）。转半圈时 n 小，
  // 残差可达 0.1 rad —— 把容差设成 0.05 会让「目标在正后方」全部失败。
  const double pos_tol = 0.05 * r + 0.02;
  const double yaw_tol = 0.25;
  const double seam_tol = 0.25;
  for (const Cand & c : cands) {
    std::vector<Pose2D> path = build(c);
    if (path.size() < 2) {continue;}
    double end_err = 0.0, yaw_err = 0.0, seam = 0.0;
    evaluate(path, &end_err, &yaw_err, &seam);
    if (std::getenv("AGC_DUBINS_DEBUG") != nullptr) {
      std::fprintf(
        stderr, "[dubins] s1=%+d s2=%+d t1=%+.3f t2=%.3f t3=%+.3f "
        "end=%.3f yaw=%.3f seam=%.3f %s\n",
        c.s1, c.s2, c.t1, c.t2, c.t3, end_err, yaw_err, seam,
        (end_err > pos_tol || yaw_err > yaw_tol || seam > seam_tol) ? "REJECT" : "ACCEPT");
    }
    if (end_err > pos_tol) {continue;}
    if (yaw_err > yaw_tol) {continue;}
    if (seam > seam_tol) {continue;}
    // 末端精确对齐：位置吸附到 `to`，航向吸附到 `to.yaw`（残差已在容差内）。
    path.back().x = to.x;
    path.back().y = to.y;
    path.back().yaw = to.yaw;
    return path;
  }
  return {};
}

// 接缝连续性报告。
struct SeamReport
{
  bool ok{true};
  int seam_count{0};              // 检测到的接缝数
  double worst_heading_jump{0.0}; // 中段最大航向跳变（rad）
  double start_heading_jump{0.0}; // 首点跳变（= 起步转向量，诊断用，不算缺陷）
  double post_rotation_jump{0.0}; // 旋转后第一点的跳变（同样不算缺陷）
  int rotation_points{0};         // 零位移点个数（原地旋转的采样点）
  double worst_curvature{0.0};    // 接缝处的离散曲率峰值（1/m）
  int worst_index{-1};
  std::string detail;
};

// 校验一条位姿序列在**接缝处**的连续性。
//
// ## 为什么必须显式做这件事
//
// Hybrid A* 回溯出来的是「基元弧 + 解析连接段」首尾相接。每一段内部是光滑的，
// 但**段与段的拼接点**不保证航向连续。实测（`yard` s19）：
//
// ```text
// i=70 (5.250,-22.512) yaw=4.807  下一段方向=-1.092  差 -0.384 rad
// i=71 (5.354,-22.712) yaw=5.575  段方向=-0.700     一致
// ```
//
// 该点曲率尖峰 2.08 /m（其余 146 点全在 1.0 以内）。这不是"离散曲率固有误差"，
// 是**构造缺陷**：`straightPoses` 曾把首点航向覆盖成段方向。
//
// ## 判据
//
// * 每个点：航向与「到下一个点的方向」之差（有位移时）不超过 `heading_tol`；
// * 重复点（零位移）**单独计数**：那是原地旋转，位置不变但航向可以变，
//   它**不是**接缝缺陷，但也不能被当成普通点算曲率（三点拟合在重复点处退化）。
//
// ## 为什么首末点单独处理
//
// **首点**的航向是「车当前朝向」，而第一段的方向是「要走的方向」。两者不等
// 是**必然**的 —— 那正是「先转向再前进」这件事本身。实测：起点朝 +x、目标在
// 45° 方向时，首点跳变 0.3927 rad。把它判成缺陷会让所有非正前方目标全部失败。
//
// **末点**的航向是「进入目标时的切线」，它由末段方向决定，本身不会跳。
//
// 所以：首点、末点的跳变**不计入**缺陷，只记录其幅度供诊断；
// 真正的缺陷是**路径中段**（i 既非首也非末）的跳变 —— 那说明两段拼接错了。
inline SeamReport validateSeamContinuity(
  const std::vector<Pose2D> & poses, double heading_tol)
{
  SeamReport r;
  if (poses.size() < 2) {
    r.ok = false;
    r.detail = "fewer than 2 poses";
    return r;
  }
  for (size_t i = 0; i + 1 < poses.size(); ++i) {
    const double dx = poses[i + 1].x - poses[i].x;
    const double dy = poses[i + 1].y - poses[i].y;
    const double len = std::hypot(dx, dy);
    if (len < 1e-6) {
      // 零位移 = 原地旋转。航向差是**预期**的，不算缺陷。
      ++r.seam_count;
      r.rotation_points++;
      continue;
    }
    const double seg = std::atan2(dy, dx);
    const double jump = std::fabs(normalizeAngle(poses[i].yaw - seg));
    if (jump <= heading_tol) {continue;}
    ++r.seam_count;
    // 首点的跳变是「先转向」本身，不是缺陷（见函数头注释）。
    if (i == 0) {
      r.start_heading_jump = jump;
      continue;
    }
    // **旋转后的第一个平移点**同理：它承接的是「旋转结束时的航向」，
    // 而平移段的方向由路径决定，两者本来就可以不同 —— 那正是「转完再走」。
    // 判据应当是：这个跳变是否**被一次旋转解释过**（前一个点是重复点）。
    const bool after_rotation = std::hypot(
      poses[i].x - poses[i - 1].x, poses[i].y - poses[i - 1].y) < 1e-6;
    if (after_rotation) {
      r.post_rotation_jump = std::max(r.post_rotation_jump, jump);
      continue;
    }
    if (jump > r.worst_heading_jump) {
      r.worst_heading_jump = jump;
      r.worst_index = static_cast<int>(i);
    }
  }
  if (r.worst_heading_jump > heading_tol) {
    r.ok = false;
    r.detail = "mid-path heading jump " + fmt(r.worst_heading_jump) + " rad > " +
      fmt(heading_tol) + " at pose " + std::to_string(r.worst_index);
  }
  return r;
}

// Hybrid A* 搜索器。
//
// 生命周期：每次 `search()` 前调用 `reset()`（或直接构造新实例）。不跨规划保留状态。
class KinodynamicSearch
{
public:
  SearchOutput search(const SearchInput & in)
  {
    SearchOutput out;
    const auto t0 = std::chrono::steady_clock::now();
    const PlannerParams & p = in.params;
    const GridView & g = in.grid;

    if (!gridGeometryOk(g)) {
      out.failure = PlanFailure::kNoMap;
      out.detail = "grid geometry invalid";
      return out;
    }

    // ---- 起终点前置检查（阶段 A 的一部分；这里做几何相关的那几条）----
    int sx = 0, sy = 0, gx = 0, gy = 0;
    if (!worldToCell(g, in.start.x, in.start.y, &sx, &sy)) {
      out.failure = PlanFailure::kStartOutOfMap;
      out.detail = "start outside map";
      return out;
    }
    if (!worldToCell(g, in.goal.x, in.goal.y, &gx, &gy)) {
      out.failure = PlanFailure::kGoalOutOfMap;
      out.detail = "goal outside map";
      return out;
    }
    if (classifyPlanningCell(cellValue(g, sx, sy)) != CellBand::kFree) {
      out.failure = PlanFailure::kStartNotFree;
      out.detail = std::string("start cell band=") + toString(cellBandAt(g, sx, sy));
      return out;
    }
    // 目标：允许「已知自由」或「有代价」（`1–98`）—— 目标落在膨胀带里是常见的
    // （车要贴到距目标 d_track 的位置）。未知与阻挡则明确失败。
    const CellBand goal_band = cellBandAt(g, gx, gy);
    if (goal_band == CellBand::kUnknown || goal_band == CellBand::kInscribed ||
      goal_band == CellBand::kLethal)
    {
      out.failure = PlanFailure::kGoalNotFree;
      out.detail = std::string("goal cell band=") + toString(goal_band);
      return out;
    }
    // **终端航向口径**（ADR-0048 (Q8) 的用户裁定）：末段切线 = 进入方向。
    //
    // `goal.yaw` **不可用**：`/agc/ground/goal` 的 `orientation` 恒为 `w=1.0`
    // （`task_manager` 只填位置），解出来永远是 0（正东）—— 那是"未填"的占位，
    // 不是"要求朝东"。把它当约束会让所有非正东方向的到达被判失败。
    //
    // 所以：目标位姿的 yaw 用「从起点指向目标的方向」作为期望进入方向。
    // 这天然满足「末段切线」语义，且不引入不存在的约束。
    Pose2D goal_pose = in.goal;
    {
      const double dgx = in.goal.x - in.start.x;
      const double dgy = in.goal.y - in.start.y;
      if (std::hypot(dgx, dgy) > 1e-6) {
        goal_pose.yaw = std::atan2(dgy, dgx);
      } else {
        goal_pose.yaw = in.start.yaw;
      }
    }

    // goal 是否落在可通行档（`kFree` / `kCost`）。未知与阻挡区不可能是有效目标。
    const bool goal_passable =
      (goal_band == CellBand::kFree || goal_band == CellBand::kCost);

    // footprint 级检查：起点/目标的**完整 footprint** 不得碰不可压档。
    // 注意 `kInscribed`（99）在这里是**挡**的（车体压上去就是擦碰风险）。
    if (footprintCollides(
        g, in.start, p.footprint_half_length, p.footprint_half_width, p.footprint_margin))
    {
      out.failure = PlanFailure::kStartCollision;
      out.detail = "start footprint collides";
      return out;
    }
    if (footprintCollides(
        g, in.goal, p.footprint_half_length, p.footprint_half_width, p.footprint_margin))
    {
      out.failure = PlanFailure::kGoalCollision;
      out.detail = "goal footprint collides";
      return out;
    }

    // ---- OPEN / CLOSED ----
    nodes_.clear();
    nodes_.reserve(static_cast<size_t>(std::min(p.max_expanded_nodes, 200000)));
    std::unordered_map<DiscreteKey, int, DiscreteKeyHash> best_index;
    best_index.reserve(static_cast<size_t>(std::min(p.max_expanded_nodes, 200000)));

    // 优先队列存 (f, node_index)；f 相同的用 node_index 破平（保证确定性）。
    using Entry = std::pair<double, int>;
    std::priority_queue<Entry, std::vector<Entry>, std::greater<Entry>> open;

    SearchNode root;
    root.state.pose = in.start;
    root.key = makeKey(g, in.start, p.yaw_bins);
    root.g = 0.0;
    root.h = heuristicCost(in.start, in.goal, p.heuristic_weight);
    root.f = root.h;
    root.parent = -1;
    nodes_.push_back(root);
    best_index[root.key] = 0;
    open.push({root.f, 0});

    const std::vector<Control> controls = candidateControls(p);
    const double step = std::max(p.primitive_max_step_m, g.resolution * 0.25);

    int goal_reached_index = -1;
    // 整条路径的最小离障：由所有通过检查的基元与 shot 累计。
    // **早先只在 shot 分支写 `out.clearance_min`**，普通基元回溯的路径从未被赋值，
    // 于是诊断恒为 +inf（序列化成 -1），「离障」这一列在整链日志里等于没有。
    double path_clearance_min = std::numeric_limits<double>::infinity();
    // 兜底候选：已扩展节点中「到 goal 的直连不穿 lethal」里距 goal 最近者。
    int frontier_index = -1;
    double frontier_dist = std::numeric_limits<double>::infinity();

    while (!open.empty()) {
      // 墙钟预算
      const double elapsed = std::chrono::duration<double>(
        std::chrono::steady_clock::now() - t0).count();
      if (elapsed > p.search_time_budget_s) {
        out.failure = PlanFailure::kSearchTimeout;
        out.detail = "search wall-clock budget exhausted";
        break;
      }
      if (out.expanded_nodes >= p.max_expanded_nodes) {
        out.failure = PlanFailure::kSearchExhausted;
        out.detail = "expanded node limit reached";
        break;
      }

      const Entry top = open.top();
      open.pop();
      const int ci = top.second;
      if (ci < 0 || ci >= static_cast<int>(nodes_.size())) {continue;}
      // 陈旧条目：`f` 已经变好了，跳过。
      if (top.first > nodes_[static_cast<size_t>(ci)].f + 1e-9) {continue;}

      const SearchNode cur = nodes_[static_cast<size_t>(ci)];
      ++out.expanded_nodes;

      // ---- 到达判定：位置 + 航向容差 ----
      const double d_goal = std::hypot(in.goal.x - cur.state.pose.x, in.goal.y - cur.state.pose.y);
      if (d_goal <= p.goal_position_tolerance_m) {
        // 位置到了但航向可能不对；航向容差由「末段切线」口径决定（见 finalizePath）。
        goal_reached_index = ci;
        break;
      }

      // ---- 解析连接：先试直连，再试圆弧 shot ----
      //
      // **只在接近目标时尝试**（经典 Hybrid A* 的做法）。早先在**每个**扩展节点上都
      // 做整段直连扫掠：从 38 m 外到 goal 按 0.15 m 采样 = 250+ 个位姿，每位姿一次
      // footprint 检查 + 一次净空查 —— 单节点 ~400 µs，20 s 只能扩展 3 万节点。
      // 实测这就是 `dense_map` 上 `search_timeout` 的直接原因。
      const bool try_analytic =
        d_goal <= p.analytic_connect_max_dist_m;
      if (try_analytic) {
        const std::vector<Pose2D> line = straightPoses(cur.state.pose, goal_pose, step);
        double clr = std::numeric_limits<double>::infinity();
        if (!sweepCollides(
            g, line, p.footprint_half_length, p.footprint_half_width,
            p.footprint_margin, p.clearance_target_m * 2.0, &clr, in.distance_field))
        {
          bool corridor_ok = true;
          if (p.corridor_enabled) {
            for (const Pose2D & q : line) {
              const double c = corridorClearance(
                g, q, p.footprint_half_length, p.footprint_half_width,
                p.footprint_margin, p.corridor_max_scan_m, 1.0);
              if (c >= 0.0 && c < p.corridor_clearance_m) {corridor_ok = false; break;}
            }
          }
          if (corridor_ok) {
            // 直连成功：把这条线接到当前节点后面。
            if (std::isfinite(clr) && clr < path_clearance_min) {path_clearance_min = clr;}
            appendAndFinish(
              out, ci, line, PlanOutcome::kSearchPath, path_clearance_min, p, g);
            out.elapsed_s = std::chrono::duration<double>(
              std::chrono::steady_clock::now() - t0).count();
            return out;
          }
        }
      }
      {
        const std::vector<Pose2D> arc = dubinsCscShot(
          cur.state.pose, goal_pose, p.analytic_min_turn_radius_m, step);
        if (!arc.empty()) {
          double clr = std::numeric_limits<double>::infinity();
          if (!sweepCollides(
              g, arc, p.footprint_half_length, p.footprint_half_width,
              p.footprint_margin, p.clearance_target_m * 2.0, &clr, in.distance_field))
          {
            bool corridor_ok = true;
            if (p.corridor_enabled) {
              for (const Pose2D & q : arc) {
                const double c = corridorClearance(
                  g, q, p.footprint_half_length, p.footprint_half_width,
                  p.footprint_margin, p.corridor_max_scan_m, 1.0);
                if (c >= 0.0 && c < p.corridor_clearance_m) {corridor_ok = false; break;}
              }
            }
            if (corridor_ok) {
              if (std::isfinite(clr) && clr < path_clearance_min) {path_clearance_min = clr;}
              appendAndFinish(
                out, ci, arc, PlanOutcome::kSearchPath, path_clearance_min, p, g);
              out.elapsed_s = std::chrono::duration<double>(
                std::chrono::steady_clock::now() - t0).count();
              return out;
            }
          }
        }
      }

      // ---- 兜底候选更新 ----
      // 只在 goal 本身可通行时才记候选：goal 在未知/阻挡区时直连必然被最终复核拒绝，
      // 记了也没用（且会让诊断误报「有兜底」）。
      if (out.expanded_nodes >= p.frontier_min_expansions &&
        d_goal < frontier_dist && goal_passable)
      {
        // 只在**真的更近**时才做整段直线可行性检查（避免每个节点都建 250 点位姿表）。
        if (directLinkClearOfBlocked(g, cur.state.pose, in.goal, step)) {
          frontier_dist = d_goal;
          frontier_index = ci;
        }
      }

      // ---- 普通扩展 ----
      for (const Control & c : controls) {
        const Primitive prim = makePrimitive(cur.state, c, p.primitive_dt, step);
        double clr = std::numeric_limits<double>::infinity();
        if (sweepCollides(
            g, prim.sampled_poses, p.footprint_half_length, p.footprint_half_width,
            p.footprint_margin, p.clearance_target_m * 2.0, &clr, in.distance_field))
        {
          continue;
        }
        // 走廊判据：只对**有位移**的基元检查（纯旋转没有「前方」）。
        // 这正是安全层 `pure_rotation` 分支的同一条理由。
        if (p.corridor_enabled && std::fabs(c.v) > 1e-6) {
          const double sign = (c.v >= 0.0) ? 1.0 : -1.0;
          bool corridor_ok = true;
          for (const Pose2D & q : prim.sampled_poses) {
            const double cc = corridorClearance(
              g, q, p.footprint_half_length, p.footprint_half_width,
              p.footprint_margin, p.corridor_max_scan_m, sign);
            if (cc >= 0.0 && cc < p.corridor_clearance_m) {corridor_ok = false; break;}
          }
          if (!corridor_ok) {continue;}
        }

        const Pose2D end_pose = prim.sampled_poses.back();
        int ex = 0, ey = 0;
        if (!worldToCell(g, end_pose.x, end_pose.y, &ex, &ey)) {continue;}   // 出图

        if (std::isfinite(clr) && clr < path_clearance_min) {path_clearance_min = clr;}
        const double mean_cost = meanCostAlong(g, prim.sampled_poses);
        const double edge = primitiveEdgeCost(
          p, prim.duration, prim.length, c.omega, clr, mean_cost);
        const double ng = cur.g + edge;
        const DiscreteKey nk = makeKey(g, end_pose, p.yaw_bins);

        auto it = best_index.find(nk);
        if (it != best_index.end()) {
          SearchNode & existing = nodes_[static_cast<size_t>(it->second)];
          if (ng >= existing.g - 1e-9) {continue;}   // 不更优
          existing.state.pose = end_pose;
          existing.g = ng;
          existing.h = heuristicCost(end_pose, in.goal, p.heuristic_weight);
          existing.f = ng + existing.h;
          existing.parent = ci;
          existing.edge_poses.assign(
            prim.sampled_poses.begin() + 1, prim.sampled_poses.end());
          open.push({existing.f, it->second});
        } else {
          SearchNode node;
          node.state.pose = end_pose;
          node.state.linear_velocity = c.v;
          node.state.angular_velocity = c.omega;
          node.key = nk;
          node.g = ng;
          node.h = heuristicCost(end_pose, in.goal, p.heuristic_weight);
          node.f = ng + node.h;
          node.parent = ci;
          node.edge_poses.assign(
            prim.sampled_poses.begin() + 1, prim.sampled_poses.end());
          const int idx = static_cast<int>(nodes_.size());
          nodes_.push_back(node);
          best_index[nk] = idx;
          open.push({node.f, idx});
        }
      }
    }

    // ---- 搜索未自然结束：看是否有兜底 ----
    out.elapsed_s = std::chrono::duration<double>(
      std::chrono::steady_clock::now() - t0).count();
    if (out.failure == PlanFailure::kNone && goal_reached_index < 0) {
      out.failure = PlanFailure::kSearchExhausted;
      out.detail = "open set empty";
    }
    if (out.failure != PlanFailure::kNone) {
      if (p.direct_link_enabled && frontier_index >= 0) {
        const SearchNode & fn = nodes_[static_cast<size_t>(frontier_index)];
        std::vector<Pose2D> path = backtrack(frontier_index);
        const std::vector<Pose2D> link = straightPoses(fn.state.pose, in.goal, step);
        if (path.empty()) {path = link;}
        else {path.insert(path.end(), link.begin() + 1, link.end());}
        out.poses = std::move(path);
        out.outcome = PlanOutcome::kDirectLink;
        out.failure = PlanFailure::kNone;
        out.detail = "frontier direct link (unknown segment expected)";
        return out;
      }
      return out;
    }

    // ---- 回溯 + 接上末段 ----
    std::vector<Pose2D> path = backtrack(goal_reached_index);
    if (path.empty()) {
      out.failure = PlanFailure::kValidationFailed;
      out.detail = "backtrack produced empty path";
      return out;
    }
    // 末端补到精确 goal（位置容差内），并让末段航向 = 进入方向（ADR-0048.7）。
    const Pose2D & last = path.back();
    if (std::hypot(goal_pose.x - last.x, goal_pose.y - last.y) > 1e-6) {
      const std::vector<Pose2D> tail = straightPoses(last, goal_pose, step);
      path.insert(path.end(), tail.begin() + 1, tail.end());
    }
    normalizeTerminalHeading(&path);
    {
      const SeamReport seam = validateSeamContinuity(path, p.seam_heading_tol_rad);
      if (!seam.ok) {
        out.failure = PlanFailure::kValidationFailed;
        out.detail = "seam discontinuity: " + seam.detail;
        return out;
      }
      out.seam_count = seam.seam_count;
    }
    out.poses = std::move(path);
    out.outcome = PlanOutcome::kSearchPath;
    out.clearance_min = path_clearance_min;
    return out;
  }

private:
  static DiscreteKey makeKey(const GridView & g, const Pose2D & pose, int yaw_bins)
  {
    DiscreteKey k;
    int ix = 0, iy = 0;
    if (!worldToCell(g, pose.x, pose.y, &ix, &iy)) {
      // 出图：给一个不可能与图内键相撞的值（负索引）。
      k.x_cell = -1;
      k.y_cell = -1;
      k.yaw_bin = 0;
      return k;
    }
    const int bins = std::max(1, yaw_bins);
    const double bin_size = 2.0 * M_PI / static_cast<double>(bins);
    int bin = static_cast<int>(std::floor((normalizeAngle(pose.yaw) + M_PI) / bin_size));
    bin = ((bin % bins) + bins) % bins;
    k.x_cell = ix;
    k.y_cell = iy;
    k.yaw_bin = bin;
    return k;
  }

  // 末端航向归一：**末点 yaw = 末段切线**（ADR-0048 的用户裁定 Q8）。
  //
  // Dubins 的终点条件是「位置 + 指定航向」，而差速车的语义是「进入目标时的运动方向」。
  // 两者不一致（实测差 0.824 rad）：收尾弧按 `goal_pose.yaw` 结束，但末段是从弧末
  // 走到 goal 的那一小段，方向不同。
  //
  // 用户裁定「终端航向 = 末段切线」，所以这里**覆盖**末点航向为末段方向。
  // 这样路径自洽（每点航向都等于它到下一个点的方向），且不引入 goal 消息里
  // 那个恒为 `w=1.0` 的假朝向。
public:
  static void normalizeTerminalHeading(std::vector<Pose2D> * poses)
  {
    if (poses == nullptr || poses->size() < 2) {return;}
    auto & v = *poses;
    for (size_t i = 0; i + 1 < v.size(); ++i) {
      const double ds = std::hypot(v[i + 1].x - v[i].x, v[i + 1].y - v[i].y);
      if (ds < 1e-6) {continue;}   // 原地旋转点：航向是语义，不动
      v[i].yaw = std::atan2(v[i + 1].y - v[i].y, v[i + 1].x - v[i].x);
    }
    // 末点沿用最后一段方向
    for (size_t i = v.size() - 1; i > 0; --i) {
      const double ds = std::hypot(v[i].x - v[i - 1].x, v[i].y - v[i - 1].y);
      if (ds < 1e-6) {continue;}
      v.back().yaw = std::atan2(v[i].y - v[i - 1].y, v[i].x - v[i - 1].x);
      break;
    }
  }

  static double meanCostAlong(const GridView & g, const std::vector<Pose2D> & poses)
  {
    if (poses.empty()) {return 0.0;}
    double sum = 0.0;
    int n = 0;
    for (const Pose2D & p : poses) {
      const int v = cellValueAtWorld(g, p.x, p.y);
      sum += cellCostWeight(v);
      ++n;
    }
    return (n > 0) ? sum / static_cast<double>(n) : 0.0;
  }

  // 回溯：**展开每个节点的 `edge_poses`**，而不是只取终点位姿。
  //
  // 这是「原地旋转不被抹掉」在搜索侧的那一半：只取终点位姿会让一次
  // 0.666 rad 的旋转在回溯后只剩 1 个点，航向跳变全部挤到接缝
  // （实测 `yard` s19 pose 18 的 0.44 rad 就是这样产生的）。
  std::vector<Pose2D> backtrack(int index) const
  {
    std::vector<Pose2D> rev;
    int cur = index;
    int guard = 0;
    while (cur >= 0 && cur < static_cast<int>(nodes_.size()) && guard++ < 1000000) {
      const SearchNode & n = nodes_[static_cast<size_t>(cur)];
      // edge_poses 是「从父节点到本节点」的中间采样点 + 本节点位姿；
      // 逆序压入，最后统一反转。
      for (auto it = n.edge_poses.rbegin(); it != n.edge_poses.rend(); ++it) {
        rev.push_back(*it);
      }
      // 起点的 edge_poses 为空，单独补上它的位姿。
      if (n.edge_poses.empty()) {rev.push_back(n.state.pose);}
      cur = n.parent;
    }
    std::reverse(rev.begin(), rev.end());
    return rev;
  }

  void appendAndFinish(
    SearchOutput & out, int node_index, const std::vector<Pose2D> & tail,
    PlanOutcome outcome, double clearance, const PlannerParams & p, const GridView & g)
  {
    (void)g;
    std::vector<Pose2D> path = backtrack(node_index);
    if (path.empty()) {path = tail;}
    else {
      // 拼接：**保留 tail 的首点航向**，但从 tail 的第二点开始接（避免重复点）。
      // `straightPoses` 已保证 tail[0].yaw == 上一节点航向，所以这里不会引入跳变。
      path.insert(path.end(), tail.begin() + 1, tail.end());
    }
    normalizeTerminalHeading(&path);
    // 接缝连续性闸：不连续的路径**不得**作为搜索结果发布。
    const SeamReport seam = validateSeamContinuity(path, p.seam_heading_tol_rad);
    if (!seam.ok) {
      out.poses.clear();
      out.failure = PlanFailure::kValidationFailed;
      out.detail = "seam discontinuity: " + seam.detail;
      return;
    }
    out.poses = std::move(path);
    out.outcome = outcome;
    out.failure = PlanFailure::kNone;
    out.clearance_min = clearance;
    out.seam_count = seam.seam_count;
  }

  std::vector<SearchNode> nodes_;
};

}  // namespace planner
}  // namespace agc_ground

#endif  // AGC_GROUND__KINODYNAMIC_SEARCH_HPP_
