// footprint_checker —— 车体 footprint 的栅格碰撞与扫掠（纯逻辑，不 include ROS）
//
// 职责：给定「车体位姿 + 地图视图」，回答三个问题：
//   1. 这个位姿的 footprint 是否压到**不可压**的格？（`collides`）
//   2. 从 A 到 B 的这条折线/圆弧扫掠，整段是否安全？（`sweepCollides`）
//   3. 沿运动方向、车体宽度带内的纵向间隙是多少？（`corridorClearance`）
//
// ## 为什么 footprint 用**真实矩形**而不是外接圆
//
// 外接圆半径 `r_fp = hypot(0.5037, 0.28545) = 0.5789 m`，面积是矩形的 **1.99 倍**
// （`π·0.5789² / (1.0074·0.5709)`）。用它做碰撞检查等于凭空把车放大一倍。
// 实测（`dense_map`，间距 2.645 m）：外接圆口径下走廊阈值 2.0 m 时**无解**，
// 而真实矩形口径下 2.0/2.6/3.0 m 全部可达 —— 差别不是数值调优，是口径对错。
//
// 这与 [ADR-0041](../../../../docs/adr/0041-geometry-metadata-instances-and-risk-map.md#top)
// 登记过的同一类错误一致：障碍用外接圆会把长条 box 放大 3 倍以上，造出「必须移出」的假阳性。
//
// ## 为什么每个采样姿态都要查、而且不能只查中心点
//
// 差速车在窄通道里的失败模式是「中心过得去、车角刮到」。`dense_map` 的最小间隙 0.99 m，
// 车宽 0.571 m —— 中心点检查会放行，而车角会碰。ADR-0048 明令「不能只检查车体中心点或
// 运动基元终点」。
//
// ## 采样密度
//
// footprint 的 9 个探针点（4 角 + 4 边中 + 中心）之间最远相距 `hypot(HL, HW) = 0.5789 m`，
// 而格宽 0.5 m。若只查这 9 点，一个 0.5 m 的障碍格可能整个落在探针之间而漏检。
// 因此探针点按**半格步长**加密：沿长轴与宽轴各 `ceil(2*HL/res)+1` × `ceil(2*HW/res)+1` 个点。
// 在 0.5 m 格下是 5×3 = 15 点，代价可接受，且保证任意格心到最近探针 < 半格对角。

#ifndef AGC_GROUND__FOOTPRINT_CHECKER_HPP_
#define AGC_GROUND__FOOTPRINT_CHECKER_HPP_

#include <algorithm>
#include <cmath>
#include <limits>
#include <vector>

#include "agc_ground/distance_field_2d.hpp"
#include "agc_ground/occupancy_grid_view.hpp"
#include "agc_ground/planner_types.hpp"

namespace agc_ground
{
namespace planner
{

// footprint 探针点（相对车体的局部坐标 (u, v)：u 沿车头，v 沿车体左侧）。
//
// 按半格步长加密；`res` 是地图分辨率。返回的局部坐标不含 `margin`，
// 由调用方在判定时统一加外扩（这样同一组探针可复用于不同 margin 的判定）。
inline std::vector<Pose2D> footprintProbes(double half_length, double half_width, double res)
{
  std::vector<Pose2D> out;
  const double step = std::max(res * 0.5, 1e-3);
  const int nu = std::max(1, static_cast<int>(std::ceil(2.0 * half_length / step)));
  const int nv = std::max(1, static_cast<int>(std::ceil(2.0 * half_width / step)));
  out.reserve(static_cast<size_t>(nu + 1) * static_cast<size_t>(nv + 1));
  for (int i = 0; i <= nu; ++i) {
    const double u = -half_length + (2.0 * half_length) * static_cast<double>(i) /
      static_cast<double>(nu);
    for (int j = 0; j <= nv; ++j) {
      const double v = -half_width + (2.0 * half_width) * static_cast<double>(j) /
        static_cast<double>(nv);
      Pose2D p;
      p.x = u;
      p.y = v;
      out.push_back(p);
    }
  }
  return out;
}

// 局部 (u,v) → world。
inline Pose2D localToWorld(const Pose2D & pose, double u, double v)
{
  const double c = std::cos(pose.yaw), s = std::sin(pose.yaw);
  Pose2D out;
  out.x = pose.x + u * c - v * s;
  out.y = pose.y + u * s + v * c;
  out.yaw = pose.yaw;
  return out;
}

// 位姿的 footprint 是否与「不可压档」相交。
//
// `margin` 是全向外扩（半格量化 + 定位/跟踪误差）。**不是** `d_collision=2.0`：
// 那会造出全向 2 m 禁行区，`dense_map` 上直接无解（ADR-0047 的教训）。
//
// **探针必须覆盖完整的「外扩后矩形」**（不是「未外扩矩形 + 8 个外扩角」）。
// 这是实测抓到的缺陷：只查 8 个外扩角时，一个 0.5 m 的障碍格可以整个落在
// 角点之间（实测用例：障碍格心在局部 (0.75, 0.05)，距最近的角点 (0.857,0) 有 0.12 m，
// 而格只有 0.1 m 宽 ⇒ 漏检）。这与「不能只检查中心点」是同一条纪律的另一半。
//
// 返回 true 表示**碰撞**（含未知与越界）。
inline bool footprintCollides(
  const GridView & g, const Pose2D & pose,
  double half_length, double half_width, double margin)
{
  if (!gridGeometryOk(g)) {return true;}   // 没有地图 = 无法证明安全
  const double hl = half_length + margin;
  const double hw = half_width + margin;
  // 直接在外扩后的矩形上按半格步长布点 —— 覆盖是完整的，不留缝。
  const std::vector<Pose2D> probes = footprintProbes(hl, hw, g.resolution);
  for (const Pose2D & pr : probes) {
    const Pose2D w = localToWorld(pose, pr.x, pr.y);
    const int v = cellValueAtWorld(g, w.x, w.y);
    if (footprintBlocks(classifyPlanningCell(v))) {return true;}
  }
  return false;
}

// footprint 到最近**阻挡格**的距离（m）；无阻挡时返回 +inf。
//
// **实现用距离场查表，不是逐圈扫描**。早先的逐圈版本对每个位姿要做
// `ceil(max_scan/step) × 16` 次栅格查询；实测 1.4 µs/次看似便宜，但搜索里每个基元
// 有十几个采样位姿、每个位姿在扩展循环里被反复查，累计把单次规划推到秒级。
// 距离场是 O(1) 查表（0.0 µs 量级）。
//
// 语义差异（**如实登记**）：距离场给的是「车心到最近阻挡格心」的距离，而本函数的
// 契约是「车体外缘到最近阻挡格」。两者差一个车体外接半径，因此这里减去
// `max(half_length, half_width)` 作为保守近似 —— 只用于**代价项**与诊断，
// 不用于硬判据（硬判据是 `footprintCollides`，它逐探针精确判定）。
inline double footprintClearanceFromField(
  const DistanceField2D & df, const Pose2D & pose,
  double half_length, double half_width)
{
  const double d = df.distanceAt(pose.x, pose.y);
  if (!std::isfinite(d)) {return d;}
  // 车体外缘比车心更靠近障碍：扣掉外接半径（保守方向 = 净空更小）。
  const double r = std::hypot(half_length, half_width);
  return std::max(0.0, d - r);
}

// 旧接口保留（逐圈扫描），供不构距离场的调用方（单测/一次性诊断）使用。
inline double footprintClearance(
  const GridView & g, const Pose2D & pose,
  double half_length, double half_width, double margin, double max_scan_m)
{
  if (!gridGeometryOk(g)) {return 0.0;}
  const double hl = half_length + margin;
  const double hw = half_width + margin;
  // 从外缘向外逐圈扩，找到第一圈有阻挡即返回该圈距离。
  // 圈步长取格宽的一半：比格宽细，但不会把开销放大到不可接受。
  const double step = std::max(g.resolution * 0.5, 1e-3);
  for (double d = 0.0; d <= max_scan_m; d += step) {
    // 只查该圈的**外边界**：8 个方向足够（矩形外缘到格心的距离判定不需要更密）。
    for (int k = 0; k < 16; ++k) {
      const double a = 2.0 * M_PI * static_cast<double>(k) / 16.0;
      const double u = (hl + d) * std::cos(a);
      const double v = (hw + d) * std::sin(a);
      const Pose2D w = localToWorld(pose, u, v);
      const int val = cellValueAtWorld(g, w.x, w.y);
      if (footprintBlocks(classifyPlanningCell(val))) {return d;}
    }
  }
  return std::numeric_limits<double>::infinity();
}

// 沿位姿的**运动方向**、车体宽度带内的纵向间隙（m）；带内无阻挡返回 -1。
//
// 语义与安全层 `d_corridor` **同构**（同一条几何定义），但**阻挡档不同**：
// 这里只看 `kLethal`（真实障碍），安全层看 `{99,100}`。
// 这个差异是**有意**的，理由见 `corridorBlocks()` 的注释与 ADR-0048 的「走廊双阻挡集」。
//
// **为什么间隙从车体外缘量起而不是车心**：`gap = |u| - half_length - margin`。
// 用「车心到障碍」会把车长算成净空，系统性乐观 0.5 m（半个车长）。
// 再扣半格对角：格心到格边还有半个格对角的不确定（与安全层 `extra_half_diag` 同口径）。
inline double corridorClearance(
  const GridView & g, const Pose2D & pose,
  double half_length, double half_width, double margin,
  double max_scan_m, double direction_sign)
{
  if (!gridGeometryOk(g)) {return 0.0;}
  const double c = std::cos(pose.yaw), s = std::sin(pose.yaw);
  const double band = half_width + margin;
  const double half_diag = std::hypot(g.resolution * 0.5, g.resolution * 0.5);
  const double dir = (direction_sign >= 0.0) ? 1.0 : -1.0;

  // 沿前进轴从**车体外缘**走到 `max_scan_m`，每步只查带宽内的 5 个横向点。
  //
  // **为什么不再扫方框**：早先取 `±(max_scan + half_length)` 的方框（29×29 = 841 格）
  // 再逐格过滤「是否在带内」。但真正关心的只是「宽 ~3 格 × 长 ~12 格」的带。
  // 实测这是搜索的主要瓶颈：每基元 4 采样位姿 × 34 控制量 × 841 格 ⇒ 单节点 ~924 µs，
  // 3 s 预算只够 3 千节点，`s19` 那种 34 m 绕障路线直接超时。
  // 沿带步进后总量降到 ~60 格，快一个数量级。
  const double step = std::max(g.resolution * 0.5, 1e-3);
  const double u_start = half_length + margin;
  const double u_end = u_start + std::max(0.0, max_scan_m);
  double best = -1.0;
  for (double u = u_start; u <= u_end + 1e-9; u += step) {
    for (int k = 0; k < 5; ++k) {
      const double v = -band + 2.0 * band * static_cast<double>(k) / 4.0;
      const double lu = dir * u;      // `dir` 把前进方向翻到 +u
      const double px = pose.x + lu * c - v * s;
      const double py = pose.y + lu * s + v * c;
      if (!corridorBlocks(classifyPlanningCell(cellValueAtWorld(g, px, py)))) {continue;}
      const double gap = std::max(0.0, u - half_length - half_diag);
      if (best < 0.0 || gap < best) {best = gap;}
      // 同一步上已有阻挡：更远的都不会更近，直接返回。
      return best;
    }
  }
  return best;
}

// 一段位姿序列的整段扫掠检查（每个位姿都查 footprint）。
//
// **为什么不在两个采样位姿之间插值**：调用方（基元/解析连接/最终复核）已经按
// `primitive_max_step_m` 或格宽量级采样，位姿之间没有空隙；再插值只是重复劳动。
// 但「采样是否足够密」这件事必须由调用方保证 —— 这里只检查给定的位姿。
inline bool sweepCollides(
  const GridView & g, const std::vector<Pose2D> & poses,
  double half_length, double half_width, double margin, double max_scan_m,
  double * clearance_min, const DistanceField2D * df = nullptr)
{
  double worst = std::numeric_limits<double>::infinity();
  for (const Pose2D & p : poses) {
    if (footprintCollides(g, p, half_length, half_width, margin)) {
      if (clearance_min != nullptr) {*clearance_min = 0.0;}
      return true;
    }
    // **有距离场就查表**（O(1)），否则退化为逐圈扫描。
    // 实测逐圈版本是搜索的主要瓶颈：每基元 5 位姿 × ~160 次栅格查询，
    // 34 个控制量 ⇒ 单节点近 1 ms，3 s 预算只够 3 千节点。
    const double cl = (df != nullptr && df->valid()) ?
      footprintClearanceFromField(*df, p, half_length + margin, half_width + margin) :
      footprintClearance(g, p, half_length, half_width, margin, max_scan_m);
    if (cl < worst) {worst = cl;}
  }
  if (clearance_min != nullptr) {*clearance_min = worst;}
  return false;
}

}  // namespace planner
}  // namespace agc_ground

#endif  // AGC_GROUND__FOOTPRINT_CHECKER_HPP_
