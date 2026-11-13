// multi_res_grid —— 高分辨率感知证据层 → 低分辨率规划层的**派生**规则（纯逻辑，不 include ROS）
//
// **为什么需要它**（本仓实测的表示能力上限）：
// `dense_map` 的障碍是 box 0.6–1.2 m、cylinder r 0.25–0.40 m，而 `/agc/map` 只有 0.5 m 格。
// 于是：
//   * 直径 0.5–0.8 m 的小圆柱只覆盖 1–2 个格；
//   * 边界点稍微偏移，相邻格就被占据（"边界点在不同帧落入不同格"）；
//   * 两个相距几格的障碍互相"借格"；
//   * 观测足迹是连续点集，最终却被压成"这一格算不算占据"的二值决策。
// 面积比已经从 1.801 降到 1.230，误覆盖率却仍是 0.668 —— 这说明剩余误差**不是**
// "地图整体膨胀"，而是**一个 0.5 m 格只能回答 0 或 100，回答不了"这一格只有 31% 被占"**。
//
// **本文件的解法**：让 0.5 m 只做**规划消费格式**，不再同时承担感知表达。
//   * 证据层：更细的格（本仓取 0.25 m），保留 log-odds 证据与连续占据率；
//   * 规划层：0.5 m，由证据层**派生**，规则单一、可单测。
//
// **参照结论（决定了下面对聚合规则的取舍）**：
//   * Nav2 的 `CostmapDownsampler` 只有 `max`（或 `use_min_cost_neighbor` 时的 `min`），
//     且 `downsampling_factor` 是整数 —— 它回答的是"规划器用多粗的图跑得快"，不回答
//     "这一格实际被占了多少"。`max` 规则下，一个 0.25 m 子格（占 0.5 m 格 25% 面积）
//     就能把整格判成致命占据，小障碍因此被**放大到整格**。
//   * RACER 的两级 `UniformGrid` 并**不**做 fine→coarse 聚合：粗级只是 `cidx*2` 的命名，
//     每级各自按感知分辨率重数一遍。所以没有"现成的正确聚合规则"可抄。
//   * 没有任何参照实现存"子格占据比例"（0..1）—— 连续占据率是本仓的新设计，
//     不是移植，因此**必须自己给判据**（见下面各函数的注释与单测）。
//
// **三条语义严格分开**（对齐 Nav2 `cost_values.hpp` 的"占据 vs 代价"分离，
// 并避免 ego-planner 把 `isKnownFree` 定义成"膨胀后为空"那种混淆）：
//   * `occupancyRatio()`   —— 几何：这一格有多少比例被占（连续，评价用）；
//   * `maxPoolOccupied()`  —— 规划：任一子格确认占据 ⇒ 整格占据（保守，规划用）；
//   * 膨胀在 `inflation_field.hpp`，**按米**，不在这里。

#ifndef AGC_PERCEPTION__MULTI_RES_GRID_HPP_
#define AGC_PERCEPTION__MULTI_RES_GRID_HPP_

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <vector>

namespace agc_perception
{

// 两层栅格的几何关系：`factor` 个细格对齐到一个粗格（整数倍）。
//
// **为什么强制整数倍**：Nav2 的 `downsampling_factor` 是 `unsigned int`、RACER 用
// `resolution *= 0.5` 的循环 —— 两者都只能表达整数倍。非整数倍（例如 0.5/0.2 = 2.5）
// 会引入半格错位，聚合时要么重复计入、要么漏计，而且错位量随坐标漂移。
// 本仓因此取 0.25 m → 0.5 m（factor = 2），格点严格对齐。
struct MultiResGeometry
{
  // 细层（证据层）几何
  double fine_resolution{0.25};
  int fine_width{0};
  int fine_height{0};
  double fine_origin_x{0.0};
  double fine_origin_y{0.0};
  // 一个粗格里含 factor×factor 个细格
  int factor{2};

  bool valid() const
  {
    return fine_resolution > 0.0 && fine_width > 0 && fine_height > 0 && factor >= 1;
  }

  // 粗层尺寸（向下取整：多出来的细格不足以构成一个粗格时丢弃，而不是补 0）。
  //
  // **为什么不向上取整**：向上取整会让最外一圈粗格只覆盖部分细格，而聚合按
  // factor×factor 读取 —— 那些"不存在"的细格会被当成未观测，与真实未观测混为一谈。
  // 向下取整的代价是边缘少一行/列粗格，那是**已知且可解释**的边界损失。
  int coarseWidth() const
  {
    return valid() ? fine_width / factor : 0;
  }
  int coarseHeight() const
  {
    return valid() ? fine_height / factor : 0;
  }
  double coarseResolution() const {return fine_resolution * factor;}

  // 粗格 (cx,cy) 覆盖的细格范围 [x0,x1) × [y0,y1)。
  void fineRangeOf(int cx, int cy, int & x0, int & y0, int & x1, int & y1) const
  {
    x0 = cx * factor;
    y0 = cy * factor;
    x1 = x0 + factor;
    y1 = y0 + factor;
  }

  // 粗格 (cx,cy) 左下角的世界坐标（与细层同一 origin 推导，不做重采样）。
  double coarseOriginX() const {return fine_origin_x;}
  double coarseOriginY() const {return fine_origin_y;}
};

// 细层 → 粗层的**几何占据率**（0..1）：粗格内"被判为占据"的细格比例。
//
// **口径（必须与评价脚本一致）**：
//   * 分子：`fine_occupied(fine_idx) == true` 的细格数；
//   * 分母：`factor × factor`（**固定**，不是"已观测的细格数"）。
//
// **为什么分母是固定值而不是"已观测数"**：若分母只数已观测细格，一个只看到 1 个
// 细格、而那 1 格被占的粗格会得到 1.0 —— 与"整格都被占"无法区分，评价会系统性
// 高估。固定分母让"部分观测 + 部分占据"如实表现为中间值，未观测部分按**未占据**
// 计入，是评价口径下最不虚高的选择。
//
// **注意它不是概率**：这是几何比例（面积占比），不是"这里有多可信"。
// 置信度是另一层（`LogOddsGrid::probAt`），两者不得混用 —— 这正是把
// "观测占据"与"可通行占据"分开的核心。
template<typename FineOccupied>
double occupancyRatio(
  const MultiResGeometry & geo, int cx, int cy, FineOccupied && fine_occupied)
{
  if (!geo.valid()) {return 0.0;}
  const int cw = geo.coarseWidth();
  const int ch = geo.coarseHeight();
  if (cx < 0 || cy < 0 || cx >= cw || cy >= ch) {return 0.0;}
  int x0 = 0, y0 = 0, x1 = 0, y1 = 0;
  geo.fineRangeOf(cx, cy, x0, y0, x1, y1);
  int hits = 0;
  for (int y = y0; y < y1; ++y) {
    for (int x = x0; x < x1; ++x) {
      const size_t idx = static_cast<size_t>(y) * geo.fine_width + x;
      if (fine_occupied(idx)) {++hits;}
    }
  }
  const int total = geo.factor * geo.factor;
  return (total > 0) ? (static_cast<double>(hits) / static_cast<double>(total)) : 0.0;
}

// 细层 → 粗层的**规划占据**（max-pool）：任一子格确认占据 ⇒ 粗格占据。
//
// **为什么规划层用 max 而不是占据率过门限**：规划关心的是"车能不能安全通过"。
// 一个 0.5 m 格里只有 25% 被占，车（半径 0.6 m）照样撞上去。用"占据率 > 阈值"
// 会把小障碍过滤掉 —— 那是拿规划安全换指标好看。
// **代价（如实登记）**：max-pool 会把小障碍**放大到整个粗格**，因此规划层的面积比
// 必然 > 1，且误覆盖率在规划层上必然偏高。这不是缺陷，是"规划层不代表真实几何"的
// 直接后果 —— 也正因如此，评价不得在规划层做（见 `occupancyRatio`）。
//
// 与 Nav2 `CostmapDownsampler` 的 `max` 同规则，但**用途不同**：Nav2 用它给规划器
// 提速（同一张代价图的粗版本），本仓用它明确区分"感知几何"与"规划安全"。
template<typename FineOccupied>
bool maxPoolOccupied(
  const MultiResGeometry & geo, int cx, int cy, FineOccupied && fine_occupied)
{
  if (!geo.valid()) {return false;}
  const int cw = geo.coarseWidth();
  const int ch = geo.coarseHeight();
  if (cx < 0 || cy < 0 || cx >= cw || cy >= ch) {return false;}
  int x0 = 0, y0 = 0, x1 = 0, y1 = 0;
  geo.fineRangeOf(cx, cy, x0, y0, x1, y1);
  for (int y = y0; y < y1; ++y) {
    for (int x = x0; x < x1; ++x) {
      const size_t idx = static_cast<size_t>(y) * geo.fine_width + x;
      if (fine_occupied(idx)) {return true;}
    }
  }
  return false;
}

// 粗层整图的占据率数组（0..1，行主序，尺寸 = coarseWidth()*coarseHeight()）。
//
// 供评价 / 可视化：**这是"几何重建"的可读形式**，不是概率、不是规划输入。
template<typename FineOccupied>
std::vector<float> occupancyRatioMap(const MultiResGeometry & geo, FineOccupied && fine_occupied)
{
  const int cw = geo.coarseWidth();
  const int ch = geo.coarseHeight();
  std::vector<float> out(static_cast<size_t>(std::max(0, cw)) * std::max(0, ch), 0.0f);
  if (!geo.valid()) {return out;}
  for (int cy = 0; cy < ch; ++cy) {
    for (int cx = 0; cx < cw; ++cx) {
      out[static_cast<size_t>(cy) * cw + cx] =
        static_cast<float>(occupancyRatio(geo, cx, cy, fine_occupied));
    }
  }
  return out;
}

// 粗层整图的规划占据掩码（0/1，行主序）。
template<typename FineOccupied>
std::vector<uint8_t> maxPoolMap(const MultiResGeometry & geo, FineOccupied && fine_occupied)
{
  const int cw = geo.coarseWidth();
  const int ch = geo.coarseHeight();
  std::vector<uint8_t> out(static_cast<size_t>(std::max(0, cw)) * std::max(0, ch), 0);
  if (!geo.valid()) {return out;}
  for (int cy = 0; cy < ch; ++cy) {
    for (int cx = 0; cx < cw; ++cx) {
      out[static_cast<size_t>(cy) * cw + cx] =
        maxPoolOccupied(geo, cx, cy, fine_occupied) ? 1 : 0;
    }
  }
  return out;
}

// 由 `factor×factor` 个子格值派生一个**规划格**值，保留 `/agc/map` 的四态语义
// （`-1 = unknown` / `0 = free` / `1–99 = 量化概率` / `100 = occupied`）。
//
// **合并优先级（保守序，从高到低）**：占据 > 有证据未跨门限 > 未知 > 自由。
//
// 逐条理由：
//   * **占据最高**：任一子格确认占据 ⇒ 整格占据（与 `maxPoolOccupied` 同一条
//     max-pool 纪律）。规划安全优先，宁可把小障碍放大到整格。
//   * **概率次之**：有子格带证据但未跨门限时，报其中最可能的值。丢掉它会让
//     "差一点就确认"的区域退化成 unknown，规划器失去"这里可疑"的信息。
//   * **未知高于自由**：只要还有子格没看过，就不能对规划器承诺"这格确认安全"。
//     把"部分未观测"折成 free 是对消费者的过度承诺（与 ADR-0035 的三态纪律一致）。
//   * **全自由才报 0**：只有所有子格都确认空闲才写 0。
//
// **注意**：`1–99` 在本仓被消费者当 unknown（`planning_policy.hpp` 的
// `classifyCell`），这是**有意**不同于 Nav2 默认行为的（Nav2 `trinary_costmap=true`
// 会把 1–99 当 free）。派生规则保持这个语义不变，不在这里"顺手对齐 Nav2"。
inline int8_t planningCellValue(const int8_t * children, int n)
{
  if (children == nullptr || n <= 0) {return -1;}
  bool any_occupied = false;
  bool any_unknown = false;
  bool any_positive = false;
  int max_positive = 0;
  for (int i = 0; i < n; ++i) {
    const int v = static_cast<int>(children[i]);
    if (v >= 100) {
      any_occupied = true;
    } else if (v < 0) {
      any_unknown = true;
    } else if (v > 0) {
      any_positive = true;
      if (v > max_positive) {max_positive = v;}
    }
  }
  if (any_occupied) {return static_cast<int8_t>(100);}
  if (any_positive) {return static_cast<int8_t>(std::min(99, std::max(1, max_positive)));}
  if (any_unknown) {return static_cast<int8_t>(-1);}
  return static_cast<int8_t>(0);
}

// 整图派生：细层四态快照 → 粗层四态快照。
//
// `fine` 是细层 `snapshot()` 的输出（尺寸必须等于 fine_width*fine_height）。
// 尺寸不符时返回空 vector（调用方据此走"全 unknown"回退），**不**静默产出半张图。
inline std::vector<int8_t> planningSnapshot(
  const MultiResGeometry & geo, const std::vector<int8_t> & fine)
{
  const int cw = geo.coarseWidth();
  const int ch = geo.coarseHeight();
  if (!geo.valid()) {return {};}
  const size_t expect = static_cast<size_t>(geo.fine_width) * geo.fine_height;
  if (fine.size() != expect) {return {};}
  std::vector<int8_t> out(static_cast<size_t>(cw) * ch, static_cast<int8_t>(-1));
  const int f = geo.factor;
  const int per = f * f;
  std::vector<int8_t> children(static_cast<size_t>(per), -1);
  for (int cy = 0; cy < ch; ++cy) {
    for (int cx = 0; cx < cw; ++cx) {
      int k = 0;
      for (int dy = 0; dy < f; ++dy) {
        const int fy = cy * f + dy;
        for (int dx = 0; dx < f; ++dx) {
          const int fx = cx * f + dx;
          children[static_cast<size_t>(k++)] =
            fine[static_cast<size_t>(fy) * geo.fine_width + fx];
        }
      }
      out[static_cast<size_t>(cy) * cw + cx] = planningCellValue(children.data(), k);
    }
  }
  return out;
}

}  // namespace agc_perception

#endif  // AGC_PERCEPTION__MULTI_RES_GRID_HPP_
