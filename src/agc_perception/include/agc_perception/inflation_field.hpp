// inflation_field —— 规划层的**米制**安全膨胀（纯逻辑，不 include ROS）
//
// **为什么单独成文件、为什么必须按米**：
//
// 参照实现的两种做法，只有一种能用在本仓：
//   * ego-planner 用 `inf_step = ceil(obstacles_inflation_ / resolution_)`，
//     配置 `obstacles_inflation=0.099` / `resolution=0.1` ⇒ `inf_step = 1` 格。
//     它**恰好**等于一格，所以参数看上去"是米"，实际效果是"一格"。一旦分辨率
//     从 0.1 换成 0.5，同一个参数会静默变成 0.5 m 的余量 —— **2.5 倍**的设计意图，
//     而且没有任何报错。
//   * Nav2 的 `InflationLayer::computeCost(distance)` 是 `f(距离, inscribed_radius)`，
//     与分辨率无关（`distance * resolution_` 才是米）。**这才是能换分辨率的写法。**
//
// 本仓的规划层分辨率将来还会变（0.5 m 只是当前消费格式），因此膨胀必须写成
// **米**：先把"离最近占据格多远（米）"算出来，再按米阈值判风险。
//
// 距离场用 **Felzenszwalb 一维平方距离变换**（沿两轴各一遍，O(N)）。
// 该算法取自 Fast-Planner `plan_env/src/sdf_map.cpp` 的 `fillESDF`（RACER 有一份
// 逐字相同的副本），是本机唯一**零依赖**的精确欧氏距离变换实现：
//   * Nav2 没有 EDT（`inflation_layer` 用缓存的 `hypot` + 四邻域 BFS 传播）；
//   * ego-planner 完全没有距离场（只有占据 + 膨胀两个 buffer）。
//
// **分辨率下限（如实登记，不得外推）**：距离场的取值是"格心到最近占据格心"的
// 欧氏距离，因此在分辨率 r 下**最小非零距离就是 r**。0.5 m 规划层上，距离只能取
// 0 / 0.5 / 0.707 / 1.0 …，没有亚格余量。需要更细的边界度量时，应提高栅格分辨率
// 或在连续几何上直接算，**不是**给这个距离场插值。

#ifndef AGC_PERCEPTION__INFLATION_FIELD_HPP_
#define AGC_PERCEPTION__INFLATION_FIELD_HPP_

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <vector>

namespace agc_perception
{

// 距离变换的"无种子"哨兵值。
//
// **为什么不直接用 `std::numeric_limits<double>::max()`**：参照实现（Fast-Planner /
// RACER 的 `fillESDF`）用它。它在本仓的栅格规模下**实测不会**溢出成 `inf`
// （`DBL_MAX + q²` 仍是 `DBL_MAX`，`DBL_MAX − DBL_MAX = 0`，包络不产生 NaN；
// 已用 1×1–9×9 全尺寸单/多种子与暴力 O(N³) 对拍确认数值精确）。
// 之所以仍换成有界哨兵，是因为"靠浮点溢出恰好不发生"不该是正确性的前提：
// 一旦 `q²` 与 `DBL_MAX` 同量级（本仓不会，但规则要能外推），`inf − inf = NaN`，
// 而 NaN 参与比较恒为 false ⇒ 包络静默退化成"照单全收"。
// 有界哨兵让这个失效模式**不可达**，代价只是换一个常量。
constexpr double kSeedInf = 1e18;
// 判定"这一格没有种子"的阈值：哨兵量级的一半，远大于任何真实格距平方
// （200×200 栅格的最远平方距离是 8e4）。
constexpr double kNoSeedThreshold = 5e17;

// Felzenszwalb 一维平方距离变换（单行/单列，原地）。
//
// 输入 `f[q]` 是"这一维上位置 q 的初始代价"，返回后 `f[q] = min_p ( (q−p)² + f_in[p] )`。
//
// 算法：用抛物线（下包络）求交维护候选集 `v[]` 与交点 `z[]`，两遍线性扫描。
// **`z[0] = −inf` 必须保留**：它让第一条抛物线无条件成为包络起点。
// 循环体是 `do { k--; 算交点 s } while (s <= z[k])` —— 先回退再比较，
// 顺序反了会把交点算成自身，包络退化（数值上表现为距离整体偏小）。
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

// 二维平方距离变换：`seed[i] != 0` 的格代价为 0，其余为 `kSeedInf`。
// 返回每格到最近种子的**平方格距**（单位 = 格²；调用方乘 resolution 再开方得米）。
//
// 两遍可分离：先逐列（竖直），再逐行（水平）。顺序无所谓，但第二遍必须用
// **第一遍的结果**当初值 —— 否则等于两次独立的一维距离，不是欧氏距离。
inline std::vector<double> squaredDistanceTransform(
  int width, int height, const std::vector<uint8_t> & seed)
{
  const size_t n = static_cast<size_t>(std::max(0, width)) * std::max(0, height);
  std::vector<double> grid(n, kSeedInf);
  if (width <= 0 || height <= 0) {return grid;}

  for (int y = 0; y < height; ++y) {
    for (int x = 0; x < width; ++x) {
      const size_t idx = static_cast<size_t>(y) * width + x;
      if (idx < seed.size() && seed[idx] != 0) {grid[idx] = 0.0;}
    }
  }

  std::vector<double> line;
  line.reserve(static_cast<size_t>(std::max(width, height)));

  // 逐列（竖直方向）
  for (int x = 0; x < width; ++x) {
    line.assign(static_cast<size_t>(height), 0.0);
    for (int y = 0; y < height; ++y) {
      line[static_cast<size_t>(y)] = grid[static_cast<size_t>(y) * width + x];
    }
    distanceTransform1D(line);
    for (int y = 0; y < height; ++y) {
      grid[static_cast<size_t>(y) * width + x] = line[static_cast<size_t>(y)];
    }
  }

  // 逐行（水平方向）
  for (int y = 0; y < height; ++y) {
    line.assign(static_cast<size_t>(width), 0.0);
    for (int x = 0; x < width; ++x) {
      line[static_cast<size_t>(x)] = grid[static_cast<size_t>(y) * width + x];
    }
    distanceTransform1D(line);
    for (int x = 0; x < width; ++x) {
      grid[static_cast<size_t>(y) * width + x] = line[static_cast<size_t>(x)];
    }
  }
  return grid;
}

// 每格到最近占据格的**米制**距离（无占据格时全为 +inf）。
inline std::vector<float> distanceFieldMeters(
  int width, int height, double resolution, const std::vector<uint8_t> & occupied)
{
  const std::vector<double> sq = squaredDistanceTransform(width, height, occupied);
  const double r = (resolution > 0.0) ? resolution : 0.0;
  std::vector<float> out(sq.size(), std::numeric_limits<float>::infinity());
  for (size_t i = 0; i < sq.size(); ++i) {
    if (sq[i] >= kNoSeedThreshold) {continue;}   // 没有种子
    out[i] = static_cast<float>(r * std::sqrt(sq[i]));
  }
  return out;
}

// 规划风险判定的**米制**参数（与分辨率解耦）。
//
// `robot_radius_m` 与 `inflation_radius_m` 都是**米**。三档语义与 Nav2
// `cost_values.hpp` 的数值序一致（致命 > 内切 > 可通行），但**不借用** Nav2 的
// `lethal_cost_threshold` 等私有参数（ADR-0035 已裁定与 Nav2 解绑）。
struct InflationParams
{
  // 车体外接半径（m）。与 `agc_ground/config/costmap.yaml` 的 `robot_radius: 0.6`
  // 同一口径 —— 两个消费者对"车多大"必须同值，否则规划与安全层的净空不一致。
  double robot_radius_m{0.6};
  // 安全膨胀外半径（m）。必须 ≥ robot_radius_m，否则 `kInflated` 带为空。
  double inflation_radius_m{1.0};
};

enum class PlanRisk : uint8_t
{
  kFree = 0,       // 可通行，无障碍
  kInflated = 1,   // 有代价但可通行
  kInscribed = 2,  // 车心进入即擦碰
  kLethal = 3,     // 格内即占据
};

// 单格风险判定（纯函数，可单测）。
//
// **为什么"距离 = 0"单独一档**：距离场把占据格自身记为 0，而"距离 0.25 m"与
// "距离 0"对规划是两件事 —— 前者是贴边，后者是压上去。合并成一档会让
// "格内占据"与"刚好贴着"不可区分。
inline PlanRisk classifyRisk(double distance_m, const InflationParams & params)
{
  if (!std::isfinite(distance_m)) {return PlanRisk::kFree;}   // 没有占据格 ⇒ 无障碍
  if (distance_m <= 0.0) {return PlanRisk::kLethal;}
  if (distance_m <= params.robot_radius_m) {return PlanRisk::kInscribed;}
  if (distance_m <= params.inflation_radius_m) {return PlanRisk::kInflated;}
  return PlanRisk::kFree;
}

// 风险档 → `nav_msgs/OccupancyGrid.data` 的取值（ADR-0041：`/agc/map` 输出风险图）。
//
// | 值 | 语义 | 判据 |
// |---|---|---|
// | `-1` | 未知 | 该格从未被观测（由调用方填，不由本函数产出） |
// | `0` | 可通行 | 距离 > `inflation_radius_m` |
// | `1–98` | 有代价但可通行 | `robot_radius < d ≤ inflation_radius`，按距离线性衰减 |
// | `99` | 车心进入即擦碰 | `0 < d ≤ robot_radius` |
// | `100` | 格内即占据 | 几何占据 |
//
// **为什么把代价压进 1–98 而不是用 Nav2 的 0–252 代价域**：
// `/agc/map` 的既有语义是 `OccupancyGrid`（-1/0/1–99/100），消费者按这个读；
// 换成 Nav2 的代价域会同时破坏 RViz 的 costmap 着色与本仓 `planning_policy.hpp`
// 的 `classifyCell`。压进 1–98 让"有代价"仍落在既有的"非 0 非 100"区间里。
//
// **代价映射与 Nav2 `InflationLayer::computeCost` 同构**（指数衰减、以 inscribed 为平台边），
// 但不借用它的 `cost_scaling_factor` 参数值 —— 本仓自己给 `cost_scaling`。
// 取指数而非线性：贴近车半径时代价应当陡增，远离时迅速趋于 0，这样规划器
// 不会因为"远处有一点点代价"而绕大圈。
inline int8_t riskToGridValue(
  PlanRisk risk, double distance_m, const InflationParams & params, double cost_scaling = 3.0)
{
  switch (risk) {
    case PlanRisk::kLethal: return static_cast<int8_t>(100);
    case PlanRisk::kInscribed: return static_cast<int8_t>(99);
    case PlanRisk::kFree: return static_cast<int8_t>(0);
    case PlanRisk::kInflated: {
        if (!std::isfinite(distance_m)) {return static_cast<int8_t>(0);}
        const double over = distance_m - params.robot_radius_m;
        const double span = std::max(1e-9, params.inflation_radius_m - params.robot_radius_m);
        const double t = std::min(1.0, std::max(0.0, over / span));   // 0=贴车, 1=外缘
        // 外缘 → 1（几乎无代价），贴车 → 98（几乎不可通行）
        const double factor = std::exp(-std::max(0.0, cost_scaling) * t);
        int v = static_cast<int>(std::lround(98.0 * factor));
        return static_cast<int8_t>(std::min(98, std::max(1, v)));
      }
  }
  return static_cast<int8_t>(0);
}

// 整图风险场（行主序，取值见 `PlanRisk`）。
inline std::vector<uint8_t> riskField(
  int width, int height, double resolution, const std::vector<uint8_t> & occupied,
  const InflationParams & params)
{
  const std::vector<float> dist = distanceFieldMeters(width, height, resolution, occupied);
  std::vector<uint8_t> out(dist.size(), static_cast<uint8_t>(PlanRisk::kFree));
  for (size_t i = 0; i < dist.size(); ++i) {
    out[i] = static_cast<uint8_t>(classifyRisk(dist[i], params));
  }
  return out;
}

// 占据掩码 → `nav_msgs/OccupancyGrid` 的 `data` 语义（0 / 100）。
//
// **注意**：规划层只输出 `{0, 100}`，不输出 1–99。理由：本仓的 `1–99 = unknown`
// 是**有意**不同于 Nav2 的（Nav2 默认 `trinary_costmap=true` 会把 1–99 当 free，
// 见 `static_layer.cpp` 的 `interpretValue`），而 `1–99` 落在规划层会让
// "有证据但未跨门限"与"几何上部分占据"两个完全不同的概念混成一个数。
// 部分占据只在**证据层**表达（`occupancyRatio`），规划层保持二值。
inline std::vector<int8_t> occupiedMaskToGridData(const std::vector<uint8_t> & occupied)
{
  std::vector<int8_t> out(occupied.size(), 0);
  for (size_t i = 0; i < occupied.size(); ++i) {
    out[i] = (occupied[i] != 0) ? static_cast<int8_t>(100) : static_cast<int8_t>(0);
  }
  return out;
}

}  // namespace agc_perception

#endif  // AGC_PERCEPTION__INFLATION_FIELD_HPP_
