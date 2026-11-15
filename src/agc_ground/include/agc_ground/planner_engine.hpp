// planner_engine —— 四阶段编排，输出纯 `PathResult`（纯逻辑，不 include ROS）
//
// 阶段（结构见 ADR-0048）：
//
// ```text
// A 地图快照与规划前检查      → 输入合法性、起终点可用性
// B 差速车运动基元搜索        → Hybrid A* + 解析连接 + 有界直连兜底
// C 路径回溯与重采样          → 弧长重采样、删共线点
// D 二维距离场 + 弹性带优化    → 只优化内部控制点
// E 时间参数化与动力学复核      → 曲率/速度/加速度；不可行即失败
// ```
//
// ## 最终复核的顺序是**固定**的（用户裁定）
//
// ```text
// ① footprint 碰撞（阻挡档 {unknown, inscribed, lethal}）
// ② 走廊净空（阻挡档 {lethal}，阈值可标定）
// ③ 曲率 / 角速度
// ④ 时间参数化可行性
// ```
//
// **任一失败即整次规划失败**，不使用上一轮旧路径（ADR-0048）。
// 优化后路径复核失败时先回退到**本次搜索的原始路径**（ADR-0048）；
// 原始路径也不合格才整次失败 —— 这个「回退一层」的语义必须保留，
// 因为优化的本质是质量改善，不该让一次失败的优化毁掉一条本来可用的路径。
//
// ## 为什么优化失败不静默
//
// `PathResult::outcome` 会如实写 `kSearchPath` 还是 `kOptimizedPath`。
// 「优化被放弃」是一个可观测的事实，不是应该藏起来的过程细节。

#ifndef AGC_GROUND__PLANNER_ENGINE_HPP_
#define AGC_GROUND__PLANNER_ENGINE_HPP_

#include <algorithm>
#include <chrono>
#include <cmath>
#include <limits>
#include <string>
#include <vector>

#include "agc_ground/distance_field_2d.hpp"
#include "agc_ground/footprint_checker.hpp"
#include "agc_ground/kinodynamic_search.hpp"
#include "agc_ground/path_time_parameterizer.hpp"
#include "agc_ground/planner_interface.hpp"
#include "agc_ground/planner_types.hpp"
#include "agc_ground/spline_optimizer_2d.hpp"

namespace agc_ground
{
namespace planner
{

// Hybrid A* 在 SE(2) 上的差速车规划器。
class HybridAstarSe2Planner : public IPlanner
{
public:
  std::string name() const override {return "hybrid_astar_se2";}

  PathResult plan(const PlannerSnapshot & snap) override
  {
    PathResult res;
    const auto t0 = std::chrono::steady_clock::now();
    const PlannerParams & p = snap.params;
    res.replan_reason = snap.replan_reason;

    // ================= 阶段 A：规划前检查 =================
    // 参数自洽性（**先于**任何几何检查）：参数组合矛盾时，失败现象会伪装成
    // 完全无关的形式（实测：转弯半径 < 1/kappa_max 表现为"接缝不连续"）。
    {
      const std::string perr = validateParams(p);
      if (!perr.empty()) {
        return fail(res, PlanFailure::kParamInvalid, perr);
      }
    }
    if (!gridGeometryOk(snap.grid)) {
      return fail(res, PlanFailure::kNoMap, "grid geometry invalid");
    }
    if (snap.grid.frame != "world") {
      return fail(
        res, PlanFailure::kFrameMismatch,
        "frame='" + snap.grid.frame + "' expected 'world'");
    }
    if (!snap.authorized) {
      return fail(res, PlanFailure::kNotAuthorized, "task state does not permit planning");
    }
    if (!snap.goal_valid) {
      return fail(res, PlanFailure::kGoalInvalid, "goal_info valid=false");
    }

    // ================= 阶段 B：搜索 =================
    // 距离场在这里就建（不只给优化用）：搜索的离障代价查表比逐圈扫描快一个数量级。
    // 实测：逐圈版本 ~1 ms/节点，3 s 预算只够 3 千节点，34 m 绕障路线直接超时。
    DistanceField2D df;
    df.build(snap.grid);

    SearchInput si;
    si.grid = snap.grid;
    si.start = snap.start;
    si.goal = snap.goal;
    si.params = p;
    si.distance_field = df.valid() ? &df : nullptr;
    KinodynamicSearch search;
    const SearchOutput so = search.search(si);
    res.expanded_nodes = so.expanded_nodes;
    if (so.failure != PlanFailure::kNone) {
      res.planning_time_s = elapsed(t0);
      return fail(res, so.failure, so.detail);
    }
    if (so.poses.size() < 2) {
      return fail(res, PlanFailure::kValidationFailed, "search produced <2 poses");
    }
    res.raw_path_points = static_cast<int>(so.poses.size());

    // ================= 阶段 C：重采样 + 平滑 + 去冗余 =================
    // 不能直接把栅格节点中心连成折线交给消费者 —— 那会产生差速车无法执行的尖角
    // （ADR-0048）。重采样让点间距均匀，航向取切线。
    //
    // **平滑是路径构造的一部分，不是可选项**：Hybrid A* 的回溯路径是分段圆弧拼接，
    // 曲率在基元边界处跳变，角加速度复核会把它算成几十 rad/s²（实测 16.9 vs 上限 2.0）。
    // 不平滑则搜索路径永远过不了动力学复核，与 ADR-0048「优化失败回退到搜索
    // 原始路径」矛盾。见 `smoothPathMovingAverage` 的注释。
    std::vector<Pose2D> search_path =
      resampleByArcLength(so.poses, p.resample_spacing_m);
    if (search_path.size() < 2) {search_path = so.poses;}
    const int smooth_hw = std::max(
      1, static_cast<int>(std::lround(p.smoothing_window_m / std::max(p.resample_spacing_m, 1e-3))));
    // **带碰撞守卫**：平滑是质量改善，不得以牺牲可行性为代价。
    // 实测 sparse_map：不带守卫时平滑把路径推进障碍（index 106）。
    search_path = smoothPathMovingAverageGuarded(
      search_path, p.smoothing_passes, smooth_hw,
      [&](const Pose2D & q) {
        return footprintCollides(
          snap.grid, q, p.footprint_half_length, p.footprint_half_width, p.footprint_margin);
      }, p.resample_spacing_m);
    // **平滑后必须再重采样一次**：移动平均把内部点挪动了，但端点固定，
    // 于是首尾附近的弧长间隔变得极不均匀（实测 0.41 m 与 0.11 m 相邻）。
    // 时间参数化用 `dt = 2*ds/(v_i+v_{i-1})` 算角加速度，`ds` 一不均匀，
    // `dω/dt` 就被小 `ds` 放大 —— 实测把 0.23 /m 的曲率算成 5.9 rad/s² 的角加速度，
    // 导致本来可行的路径被判 `kDynamicsInfeasible`。
    // 重采样把点距恢复均匀，这是「平滑」与「时间参数化」之间的必要一步。
    search_path = resampleByArcLength(search_path, p.resample_spacing_m);

    // 搜索路径必须先通过最终复核，否则谈不上「优化失败时回退」。
    const ValidateResult raw_val = validatePath(snap, search_path);
    if (!raw_val.ok) {
      res.planning_time_s = elapsed(t0);
      return fail(res, raw_val.failure, "search path failed validation: " + raw_val.detail);
    }

    // ================= 阶段 D：距离场 + 弹性带优化 =================
    std::vector<Pose2D> chosen = search_path;
    PlanOutcome outcome = PlanOutcome::kSearchPath;
    double clearance = raw_val.clearance_min;
    std::vector<double> curvature = raw_val.curvature;
    TimeParamResult tp = raw_val.time_param;

    if (p.optimization_enabled && df.valid()) {
      SplineOptimizer2D opt;
      const SplineOptimizer2D::Result opt_res = opt.optimize(search_path, df, snap.grid, p);
      if (opt_res.ok && opt_res.poses.size() >= 2) {
        // 优化后必须**重新密集采样**并再走一遍完整复核 —— 优化不是安全证明（ADR-0048）。
        std::vector<Pose2D> dense =
          resampleByArcLength(opt_res.poses, p.resample_spacing_m);
        const int smooth_hw2 = std::max(
          1, static_cast<int>(std::lround(
            p.smoothing_window_m / std::max(p.resample_spacing_m, 1e-3))));
        dense = smoothPathMovingAverageGuarded(
          dense, p.smoothing_passes, smooth_hw2,
          [&](const Pose2D & q) {
            return footprintCollides(
              snap.grid, q, p.footprint_half_length, p.footprint_half_width,
              p.footprint_margin);
          }, p.resample_spacing_m);
        // 同阶段 C：平滑后重采样，恢复均匀点距（否则 dt 被小 ds 放大）。
        dense = resampleByArcLength(dense, p.resample_spacing_m);
        const ValidateResult opt_val = validatePath(snap, dense);
        if (opt_val.ok) {
          chosen = dense;
          outcome = PlanOutcome::kOptimizedPath;
          clearance = opt_val.clearance_min;
          curvature = opt_val.curvature;
          tp = opt_val.time_param;
        }
        // 优化后不合格 → **静默回退**到搜索路径（已在上方验证过），
        // 但 outcome 如实写 kSearchPath，且 detail 记录原因。
        else if (!opt_val.detail.empty()) {
          res.detail = "optimized path rejected: " + opt_val.detail + "; fell back to search path";
        }
      }
    }

    // ================= 阶段 E 已完成（时间参数化在 validatePath 里） =================
    // **发布前的最后一道整理**（与复核入口同一口径）：
    // 删末尾重复点 + 每点航向 = 到下一个点的方向 + 末点 = 末段切线。
    //
    // 为什么必须在这里再做一次：`validatePath` 是在**副本**上做这些整理的，
    // 而真正发布的是 `chosen`。两处口径分叉过一次（实测：复核通过但发布出去
    // 的路径末点航向与末段切线差 0.824 rad）。
    chosen = removeDuplicates(chosen);
    KinodynamicSearch::normalizeTerminalHeading(&chosen);

    res.success = true;
    res.failure = PlanFailure::kNone;
    res.outcome = outcome;
    res.poses = chosen;
    res.curvature = curvature;
    res.speed_profile = tp.profile;
    res.clearance_min_m = clearance;
    res.max_curvature = tp.max_curvature;
    res.final_path_points = static_cast<int>(chosen.size());
    res.map_signature = blockedSignature(snap.grid);
    res.path_length_m = pathLength(chosen);
    res.planning_time_s = elapsed(t0);
    return res;
  }

private:
  struct ValidateResult
  {
    bool ok{false};
    PlanFailure failure{PlanFailure::kValidationFailed};
    std::string detail;
    double clearance_min{std::numeric_limits<double>::infinity()};
    std::vector<double> curvature;
    TimeParamResult time_param;
  };

  // 最终复核：① footprint → ② 走廊 → ③ 曲率 → ④ 时间参数化。
  //
  // **顺序是固定的**（用户裁定）：几何失败率远高于动力学失败率，先算动力学是浪费；
  // 且顺序固定让失败原因**单一可归因**。
  static ValidateResult validatePath(
    const PlannerSnapshot & snap, const std::vector<Pose2D> & poses_in)
  {
    ValidateResult v;
    // **发布前统一航向口径**：每点 yaw = 到下一个点的方向，末点 = 末段切线。
    // 这是 ADR-0048 的用户裁定（终端航向 = 末段切线）。放在复核入口而不是搜索出口，
    // 是为了让「搜索路径」与「优化路径」走**同一条**口径 —— 否则两者对末点航向的
    // 处理会分叉（实测优化路径继承 Dubins 的 to.yaw，与末段切线差 0.824 rad）。
    // 先删重复点（零长度段会让「末段切线」无定义），再归一化航向。
    std::vector<Pose2D> poses = removeDuplicates(poses_in);
    KinodynamicSearch::normalizeTerminalHeading(&poses);
    const PlannerParams & p = snap.params;
    const GridView & g = snap.grid;

    if (poses.size() < 2) {
      v.failure = PlanFailure::kValidationFailed;
      v.detail = "fewer than 2 poses";
      return v;
    }

    // ---- ⓪ 接缝连续性（**最先判**：它是几何构造缺陷，不是"参数太严"）----
    // 早先没有这一闸，接缝处的航向跳变被后处理（重采样/平滑）掩盖成曲率尖峰，
    // 表现为"动力学不可行"，归因完全错位。实测 s19 只有 2 个尖峰点，全在接缝。
    {
      const SeamReport seam = validateSeamContinuity(poses, p.seam_heading_tol_rad);
      if (!seam.ok) {
        v.failure = PlanFailure::kValidationFailed;
        v.detail = "seam discontinuity: " + seam.detail;
        return v;
      }
    }

    // ---- ① footprint 碰撞（阻挡档含 unknown / inscribed / lethal）----
    double clr = std::numeric_limits<double>::infinity();
    if (sweepCollides(
        g, poses, p.footprint_half_length, p.footprint_half_width,
        p.footprint_margin, p.clearance_target_m * 2.0, &clr))
    {
      v.failure = PlanFailure::kValidationFailed;
      v.detail = "footprint collision";
      return v;
    }
    v.clearance_min = clr;

    // ---- ② 走廊净空（阻挡档只含 lethal）----
    if (p.corridor_enabled) {
      for (size_t i = 0; i + 1 < poses.size(); ++i) {
        const double dx = poses[i + 1].x - poses[i].x;
        const double dy = poses[i + 1].y - poses[i].y;
        if (std::hypot(dx, dy) < 1e-6) {continue;}   // 原地旋转段没有「前方」
        const double c = corridorClearance(
          g, poses[i], p.footprint_half_length, p.footprint_half_width,
          p.footprint_margin, p.corridor_max_scan_m, 1.0);
        if (c >= 0.0 && c < p.corridor_clearance_m) {
          v.failure = PlanFailure::kValidationFailed;
          v.detail = "corridor clearance " + fmt(c) + " < " + fmt(p.corridor_clearance_m) +
            " at pose " + std::to_string(i);
          return v;
        }
      }
    }

    // ---- ③ 曲率 + ④ 时间参数化 ----
    v.curvature = computeCurvature(poses);
    v.time_param = parameterizeTime(poses, p, snap.start_speed);
    if (!v.time_param.feasible) {
      v.failure = PlanFailure::kDynamicsInfeasible;
      v.detail = v.time_param.reason;
      return v;
    }

    v.ok = true;
    return v;
  }

  static double pathLength(const std::vector<Pose2D> & poses)
  {
    double len = 0.0;
    for (size_t i = 1; i < poses.size(); ++i) {
      len += std::hypot(poses[i].x - poses[i - 1].x, poses[i].y - poses[i - 1].y);
    }
    return len;
  }

  static double elapsed(const std::chrono::steady_clock::time_point & t0)
  {
    return std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
  }

  static PathResult fail(PathResult & res, PlanFailure f, const std::string & detail)
  {
    res.success = false;
    res.failure = f;
    res.outcome = PlanOutcome::kFailure;
    if (!detail.empty()) {res.detail = detail;}
    return res;
  }
};

// 工厂实现：**当前唯一**的实现。
inline IPlanner::Ptr createPlanner()
{
  return IPlanner::Ptr(new HybridAstarSe2Planner());
}

}  // namespace planner
}  // namespace agc_ground

#endif  // AGC_GROUND__PLANNER_ENGINE_HPP_
