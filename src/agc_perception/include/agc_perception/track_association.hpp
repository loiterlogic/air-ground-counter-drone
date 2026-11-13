// track_association —— 跨帧 id 关联（纯逻辑，**不依赖 OpenCV / ROS**）
//
// 从 nadir_geometry.hpp 抽出：`map_adapter` 也需要同一套关联（框 id 稳定性），
// 但它不链接 OpenCV，不能包含 nadir_geometry.hpp。
//
// **为什么不能用量化格**（第一版做法，已废）：id = llround(cx/cell) 时，目标质心只要在
// 格子边界附近抖动，id 就在两格之间来回翻（实测相邻帧 id 集合 Jaccard 仅 0.56、
// 最低 0.08）。下游按 id 键控状态、旧 id 要等过期才清除，于是同一目标在画面上
// 反复出现又消失。**最近邻关联**才让 id 跟着目标走。

#ifndef AGC_PERCEPTION__TRACK_ASSOCIATION_HPP_
#define AGC_PERCEPTION__TRACK_ASSOCIATION_HPP_

#include <algorithm>
#include <cmath>
#include <string>
#include <utility>
#include <vector>

namespace agc_perception
{

struct TrackState
{
  double x{0.0}, y{0.0};   // 上一帧质心（用于下一帧的关联门）
  // 平滑后的几何（抑制单帧 OBB 抖动；实测同 id 的 sx 跨度可达 3.14 m）
  double sx{0.0}, sy{0.0}, sz{0.0}, zc{0.0}, yaw{0.0};
  int hits{0};             // 连续命中次数（供下游判断是否足够可信）
  int misses{0};           // 连续丢失次数；超过上限即从表里移除
};

struct Association
{
  int index{0};   // 匹配到的上一帧 track 下标；-1 = 新目标
  double dist{0.0};
};

// 贪心最近邻关联：对每个观测找**未被占用**的最近旧 track，距离 ≤ gate_m 才匹配。
// observations 是 (x,y) 序列；tracks 是上一帧状态表。
// 返回与 observations 等长的关联结果。
inline std::vector<Association> associateNearest(
  const std::vector<std::pair<double, double>> & observations,
  const std::vector<TrackState> & tracks, double gate_m)
{
  std::vector<Association> out(observations.size(), Association{-1, 0.0});
  std::vector<bool> used(tracks.size(), false);
  // 先把所有 (观测, 旧 track) 对按距离升序排，再贪心取 —— 保证全局较优且确定
  struct Pair {size_t obs; size_t trk; double d;};
  std::vector<Pair> pairs;
  pairs.reserve(observations.size() * tracks.size());
  for (size_t i = 0; i < observations.size(); ++i) {
    for (size_t j = 0; j < tracks.size(); ++j) {
      const double dx = observations[i].first - tracks[j].x;
      const double dy = observations[i].second - tracks[j].y;
      const double d = std::hypot(dx, dy);
      if (d <= gate_m) {pairs.push_back({i, j, d});}
    }
  }
  std::sort(
    pairs.begin(), pairs.end(), [](const Pair & a, const Pair & b) {
      if (a.d != b.d) {return a.d < b.d;}
      if (a.obs != b.obs) {return a.obs < b.obs;}
      return a.trk < b.trk;
    });
  for (const auto & p : pairs) {
    if (out[p.obs].index >= 0 || used[p.trk]) {continue;}
    out[p.obs].index = static_cast<int>(p.trk);
    out[p.obs].dist = p.d;
    used[p.trk] = true;
  }
  return out;
}

}  // namespace agc_perception

#endif  // AGC_PERCEPTION__TRACK_ASSOCIATION_HPP_
