// distance_field_2d —— 二维欧氏距离场（纯逻辑，不 include ROS）
//
// 用途：给 B 样条/弹性带优化的离障代价提供「控制点到最近真实障碍的距离」及其梯度。
//
// ## 为什么复用 Felzenszwalb 而不是自己写 BFS
//
// `agc_perception/include/agc_perception/inflation_field.hpp` 已经有一份经过验证的
// 实现（`distanceTransform1D` + `squaredDistanceTransform`），其算法取自
// [Fast-Planner 的 `plan_env/src/sdf_map.cpp`](../../../refs/Fast-Planner/fast_planner/plan_env/src/sdf_map.cpp)
// 的 `fillESDF`（O(N) 精确 EDT）。
//
// 但规划器**不能**直接 include 感知包的头文件：包边界 ② 禁止业务库互链
// （[ADR-0020](../../../../docs/adr/0020-package-boundaries-and-runtime-topology.md#top)）。
// 因此这里**独立实现一份**，算法相同、代码独立。这是刻意的重复，不是疏忽 ——
// 两边的口径差异（感知侧按风险分档、规划侧只要距离）不值得抽公共库。
//
// ## 为什么种子只取**真实障碍**（`kLethal`）
//
// 距离场的语义是「离真东西多远」。若把 `99`/`1–98` 的膨胀带也当种子，距离场就变成
// 「离膨胀边界多远」，优化器会把控制点推得离障碍过远 —— 在 `dense_map` 上直接无解
// （与走廊判据同一个根因，见 `corridorBlocks`）。
//
// ## 未知格不参与
//
// 未知格既不是种子也不是自由空间：优化器不允许把控制点推进未知区（由最终复核兜住），
// 但距离场里它不提供任何「安全」信息。这与 ADR-0035 的三态纪律一致。

#ifndef AGC_GROUND__DISTANCE_FIELD_2D_HPP_
#define AGC_GROUND__DISTANCE_FIELD_2D_HPP_

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <vector>

#include "agc_ground/occupancy_grid_view.hpp"
#include "agc_ground/planner_types.hpp"

namespace agc_ground
{
namespace planner
{

// 无种子哨兵。
//
// **为什么不用 `DBL_MAX`**：`DBL_MAX + q²` 仍是 `DBL_MAX`，`DBL_MAX − DBL_MAX = 0`，
// 靠浮点溢出「恰好不发生」不该是正确性的前提。有界哨兵让这个失效模式不可达。
// （感知侧 `inflation_field.hpp` 的 `kSeedInf` 是同一论证。）
constexpr double kDistSeedInf = 1e18;
constexpr double kDistNoSeedThreshold = 5e17;

// Felzenszwalb 一维平方距离变换（原地）。
inline void distanceTransform1D(std::vector<double> & f)
{
  const int n = static_cast<int>(f.size());
  if (n <= 0) {return;}
  std::vector<int> v(static_cast<size_t>(n));
  std::vector<double> z(static_cast<size_t>(n) + 1);

  int k = 0;
  v[0] = 0;
  z[0] = -std::numeric_limits<double>::infinity();
  z[1] = std::numeric_limits<double>::infinity();

  for (int q = 1; q < n; ++q) {
    double s = 0.0;
    while (true) {
      const int vk = v[static_cast<size_t>(k)];
      const double denom = 2.0 * static_cast<double>(q) - 2.0 * static_cast<double>(vk);
      s = ((f[static_cast<size_t>(q)] + static_cast<double>(q) * q) -
        (f[static_cast<size_t>(vk)] + static_cast<double>(vk) * vk)) / denom;
      if (k > 0 && s <= z[static_cast<size_t>(k)]) {
        --k;
      } else {
        break;
      }
    }
    ++k;
    v[static_cast<size_t>(k)] = q;
    z[static_cast<size_t>(k)] = s;
    z[static_cast<size_t>(k) + 1] = std::numeric_limits<double>::infinity();
  }

  k = 0;
  std::vector<double> out(static_cast<size_t>(n), 0.0);
  for (int q = 0; q < n; ++q) {
    while (z[static_cast<size_t>(k) + 1] < static_cast<double>(q)) {++k;}
    const double dq = static_cast<double>(q) - static_cast<double>(v[static_cast<size_t>(k)]);
    out[static_cast<size_t>(q)] = dq * dq + f[static_cast<size_t>(v[static_cast<size_t>(k)])];
  }
  f.swap(out);
}

// 二维欧氏距离场：每个自由格到最近 `kLethal` 格的**米制**距离。
//
// 未知格与 `99`/`1–98` 格**不参与**（既不当初值 0，也不被当成可查询的自由格）：
// 查询它们时返回 0（= 视为贴障），这样优化器不会把控制点往这些格里推。
class DistanceField2D
{
public:
  void build(const GridView & g)
  {
    width_ = 0;
    height_ = 0;
    resolution_ = 0.0;
    origin_x_ = 0.0;
    origin_y_ = 0.0;
    dist_m_.clear();
    if (!gridGeometryOk(g)) {return;}

    width_ = g.width;
    height_ = g.height;
    resolution_ = g.resolution;
    origin_x_ = g.origin_x;
    origin_y_ = g.origin_y;

    const size_t n = static_cast<size_t>(width_) * static_cast<size_t>(height_);
    std::vector<double> grid(n, kDistSeedInf);
    std::vector<uint8_t> is_free(n, 0);
    for (int iy = 0; iy < height_; ++iy) {
      for (int ix = 0; ix < width_; ++ix) {
        const size_t idx = static_cast<size_t>(iy) * static_cast<size_t>(width_) +
          static_cast<size_t>(ix);
        const CellBand b = cellBandAt(g, ix, iy);
        if (b == CellBand::kLethal) {
          grid[idx] = 0.0;                 // 种子
        } else if (b == CellBand::kFree) {
          is_free[idx] = 1;                // 可查询
        }
      }
    }

    // 两遍可分离：先逐列（竖直），再逐行（水平）。第二遍必须用第一遍的结果。
    std::vector<double> line;
    line.reserve(static_cast<size_t>(std::max(width_, height_)));

    for (int ix = 0; ix < width_; ++ix) {
      line.assign(static_cast<size_t>(height_), 0.0);
      for (int iy = 0; iy < height_; ++iy) {
        line[static_cast<size_t>(iy)] =
          grid[static_cast<size_t>(iy) * static_cast<size_t>(width_) + static_cast<size_t>(ix)];
      }
      distanceTransform1D(line);
      for (int iy = 0; iy < height_; ++iy) {
        grid[static_cast<size_t>(iy) * static_cast<size_t>(width_) + static_cast<size_t>(ix)] =
          line[static_cast<size_t>(iy)];
      }
    }
    for (int iy = 0; iy < height_; ++iy) {
      line.assign(static_cast<size_t>(width_), 0.0);
      for (int ix = 0; ix < width_; ++ix) {
        line[static_cast<size_t>(ix)] =
          grid[static_cast<size_t>(iy) * static_cast<size_t>(width_) + static_cast<size_t>(ix)];
      }
      distanceTransform1D(line);
      for (int ix = 0; ix < width_; ++ix) {
        grid[static_cast<size_t>(iy) * static_cast<size_t>(width_) + static_cast<size_t>(ix)] =
          line[static_cast<size_t>(ix)];
      }
    }

    // 转成米制；非自由格记为 0（= 贴障，优化器不会往里推）。
    dist_m_.assign(n, 0.0f);
    for (size_t i = 0; i < n; ++i) {
      if (!is_free[i]) {dist_m_[i] = 0.0f; continue;}
      if (grid[i] >= kDistNoSeedThreshold) {
        dist_m_[i] = std::numeric_limits<float>::infinity();   // 全图无阻挡
        continue;
      }
      dist_m_[i] = static_cast<float>(resolution_ * std::sqrt(grid[i]));
    }
    built_ = true;
  }

  bool valid() const {return built_ && width_ > 0 && height_ > 0;}
  int width() const {return width_;}
  int height() const {return height_;}

  // 世界坐标处的离障距离（m）。地图外 / 非自由格 → 0（视为贴障）。
  double distanceAt(double x, double y) const
  {
    if (!valid()) {return 0.0;}
    const double fx = (x - origin_x_) / resolution_;
    const double fy = (y - origin_y_) / resolution_;
    if (!std::isfinite(fx) || !std::isfinite(fy)) {return 0.0;}
    const int ix = static_cast<int>(std::floor(fx));
    const int iy = static_cast<int>(std::floor(fy));
    if (ix < 0 || iy < 0 || ix >= width_ || iy >= height_) {return 0.0;}
    const float d = dist_m_[static_cast<size_t>(iy) * static_cast<size_t>(width_) +
      static_cast<size_t>(ix)];
    return static_cast<double>(d);
  }

  // 离障距离对位置的梯度（有限差分，单位 m/m）。
  //
  // **为什么用中心差分而不是解析**：EDT 的解析梯度要额外存一张「最近种子索引」表，
  // 内存翻倍；而优化器只需要方向，中心差分的精度足够。步长取半格：更细会落在同一个
  // 格上得到 0 梯度，更粗会跨越障碍。
  void distanceGradient(double x, double y, double * gx, double * gy) const
  {
    *gx = 0.0;
    *gy = 0.0;
    if (!valid()) {return;}
    const double h = std::max(resolution_ * 0.5, 1e-3);
    const double dpx = distanceAt(x + h, y);
    const double dmx = distanceAt(x - h, y);
    const double dpy = distanceAt(x, y + h);
    const double dmy = distanceAt(x, y - h);
    if (std::isfinite(dpx) && std::isfinite(dmx)) {*gx = (dpx - dmx) / (2.0 * h);}
    if (std::isfinite(dpy) && std::isfinite(dmy)) {*gy = (dpy - dmy) / (2.0 * h);}
    // 归一化：只保留方向，量级由代价函数自己定。
    const double n = std::hypot(*gx, *gy);
    if (n > 1e-9) {
      *gx /= n;
      *gy /= n;
    }
  }

private:
  bool built_{false};
  int width_{0};
  int height_{0};
  double resolution_{0.0};
  double origin_x_{0.0};
  double origin_y_{0.0};
  std::vector<float> dist_m_;
};

}  // namespace planner
}  // namespace agc_ground

#endif  // AGC_GROUND__DISTANCE_FIELD_2D_HPP_
