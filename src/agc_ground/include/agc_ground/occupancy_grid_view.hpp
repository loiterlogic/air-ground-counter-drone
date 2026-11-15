// occupancy_grid_view —— 规划器的**只读地图视图**与地图签名（纯逻辑，不 include ROS）
//
// 职责只有两件：
//   1. 把 `/agc/map` 的 `data/width/height/resolution/origin/frame` 包成一个只读视图，
//      提供世界↔栅格的确定性转换与边界判定；
//   2. 算出**地图签名**，供重规划判据使用（双判据，见下）。
//
// ## 为什么快照不需要拷贝
//
// 规划节点是**单线程** `rclcpp::spin`：回调与定时器天然串行，规划期间地图回调根本不会执行。
// 因此「快照」的语义由「不跨 tick 持有指针」承载，而不是靠深拷贝 4 万格。
// 这一点必须写清楚，否则后来者会以为漏了 `= map_msg->data` 的拷贝。
// （若将来改多线程执行器，必须在这里补真拷贝 —— 见 ADR-0048 的「执行器」一节。）
//
// ## 地图签名为什么是**双判据**
//
// [ADR-0013](../../../../docs/adr/0013-ground-planning-path-contract.md#top) (b) 的签名口径是
// 「只计 lethal 格」。但那套口径服务的是 costmap 的 `static_layer`，且它有一个**盲点**：
// 未知格被探索成自由格时，lethal 集**完全不变**，签名不动 → 永不触发重规划。
//
// 实测（`dense_map`，UAV 已知半径 10 → 28.28 m 六步推进）：
//
// ```text
// known_r=10.0 → free= 2999  blocked=1448  unknown=35553
// known_r=28.3 → free=13092  blocked=1448  unknown=25460
// ```
//
// `blocked` 从头到尾 **1448 → 1448 不变**，而 `free` 涨了 10,093 格。
// 也就是说：只计阻挡格时，「等地图探索出来就能补上」这件事**永远不会被触发**。
//
// 所以本文件同时给出两个量：
//   * `blocked_signature()` —— 只计阻挡档（`kInscribed` + `kLethal`）的 FNV-1a 哈希；
//   * `free_cell_count()`  —— 已知自由（`kFree`）的格数。
//
// 重规划判据 = 「阻挡签名变」**或**「自由格数变化超过阈值」。后者才感知探索推进。
// 阈值取 200 格：实测探索步进的自由格增量是 +1876 / +2153 / +2228 / +2403 / +1433，
// 而 `publish_deadband=5` 的量化噪声每帧只动几十格 —— 两者差一个数量级，判别力充足。

#ifndef AGC_GROUND__OCCUPANCY_GRID_VIEW_HPP_
#define AGC_GROUND__OCCUPANCY_GRID_VIEW_HPP_

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#include "agc_ground/planner_types.hpp"

namespace agc_ground
{
namespace planner
{

// 地图视图（**不持有**数据；生命周期由调用方保证）。
struct GridView
{
  const int8_t * cells{nullptr};
  int width{0};
  int height{0};
  double resolution{0.0};
  double origin_x{0.0};
  double origin_y{0.0};
  std::string frame;      // 必须是 `world`
  double stamp_s{0.0};
};

// 视图自洽性：数据指针、尺寸、分辨率、原点都必须合法。
//
// **为什么单列一个函数**：规划器的阶段 A 要按顺序报出**具体**哪一项不合格
// （`kMapInvalid` vs `kFrameMismatch` vs `kNoMap`），合并成一句「地图不可用」
// 会让补链路的方向被掩盖。
inline bool gridGeometryOk(const GridView & g)
{
  if (g.cells == nullptr) {return false;}
  if (g.width <= 0 || g.height <= 0) {return false;}
  if (!(g.resolution > 0.0) || !std::isfinite(g.resolution)) {return false;}
  if (!std::isfinite(g.origin_x) || !std::isfinite(g.origin_y)) {return false;}
  if (!std::isfinite(g.stamp_s)) {return false;}
  return true;
}

// 世界坐标 → 栅格索引。返回 false 表示**在地图外**（不是「返回最近格」）。
//
// 用 `floor` 而不是 `round`：`OccupancyGrid` 的格 `i` 覆盖
// `[origin + i*res, origin + (i+1)*res)`，格心在 `+0.5*res`。
// 用 `round` 会把格边界两侧各半格都算进相邻格，与地图语义差半格。
inline bool worldToCell(const GridView & g, double x, double y, int * ix, int * iy)
{
  if (!gridGeometryOk(g)) {return false;}
  const double fx = (x - g.origin_x) / g.resolution;
  const double fy = (y - g.origin_y) / g.resolution;
  if (!std::isfinite(fx) || !std::isfinite(fy)) {return false;}
  if (fx < 0.0 || fy < 0.0) {return false;}
  const int cx = static_cast<int>(std::floor(fx));
  const int cy = static_cast<int>(std::floor(fy));
  if (cx < 0 || cy < 0 || cx >= g.width || cy >= g.height) {return false;}
  *ix = cx;
  *iy = cy;
  return true;
}

// 栅格索引 → 格心世界坐标。越界时返回 false（不静默夹取）。
inline bool cellToWorld(const GridView & g, int ix, int iy, double * x, double * y)
{
  if (!gridGeometryOk(g)) {return false;}
  if (ix < 0 || iy < 0 || ix >= g.width || iy >= g.height) {return false;}
  *x = g.origin_x + (static_cast<double>(ix) + 0.5) * g.resolution;
  *y = g.origin_y + (static_cast<double>(iy) + 0.5) * g.resolution;
  return true;
}

// 取格值；越界按**未知**处理（`-1`），不放行。
//
// 「地图外按未知」是安全方向：地图外没有证据，既不能当自由也不能当阻挡。
// 判据与安全层 `evaluateSweep` 的同名注释一致。
inline int cellValue(const GridView & g, int ix, int iy)
{
  if (!gridGeometryOk(g)) {return -1;}
  if (ix < 0 || iy < 0 || ix >= g.width || iy >= g.height) {return -1;}
  return static_cast<int>(g.cells[static_cast<size_t>(iy) * static_cast<size_t>(g.width) +
           static_cast<size_t>(ix)]);
}

inline CellBand cellBandAt(const GridView & g, int ix, int iy)
{
  return classifyPlanningCell(cellValue(g, ix, iy));
}

// 世界坐标处的地图格值（越界 = 未知）。
inline int cellValueAtWorld(const GridView & g, double x, double y)
{
  int ix = 0, iy = 0;
  if (!worldToCell(g, x, y, &ix, &iy)) {return -1;}
  return cellValue(g, ix, iy);
}

// FNV-1a 64 位字节哈希（对 int8_t 序列），输出 16 进制串。
//
// 与 `agc_perception/src/map_adapter.cpp` 的 `hashBytes` **算法相同但实现独立**：
// 规划器不能链接感知实现库（包边界 ②：禁止业务库互链），且这里要的只是「同一输入同
// 一输出」，不需要与感知侧 hash 可比。
inline std::string fnv1aBytes(const std::vector<int8_t> & data)
{
  uint64_t h = 1469598103934665603ULL;
  for (int8_t v : data) {
    h ^= static_cast<uint8_t>(v);
    h *= 1099511628211ULL;
  }
  char buf[17];
  std::snprintf(buf, sizeof(buf), "%016llx", static_cast<unsigned long long>(h));
  return std::string(buf);
}

// 阻挡签名：**只计阻挡档**（`kInscribed` + `kLethal`）的格索引 + 地图几何。
//
// **为什么把 `kInscribed`（99）也算进阻挡签名**：`99` 是「车心进入即擦碰」，
// 它是障碍真实存在的证据（膨胀环由真实障碍派生）。把它排除会让「小障碍出现」
// 只在 `100` 上体现，而 0.5 m 格里小障碍可能只占 1 格、且可能落在 `99` 档 ——
// 那类变化对规划是**实质**的，不该被签名忽略。
//
// **为什么不计 `kCost` / `kFree` / `kUnknown`**：这三档的翻转是探索与量化的常态，
// 计进去就是 ADR-0013 当年实测的「每回合 23.7 次伪触发重规划」。
// 探索推进由 `free_cell_count()` 单独承载（见文件头）。
inline std::string blockedSignature(const GridView & g)
{
  std::vector<int8_t> blob;
  if (!gridGeometryOk(g)) {return std::string("invalid");}
  blob.reserve(static_cast<size_t>(64));
  // 几何先入哈希：分辨率/原点/尺寸变化必须被感知（换了地图但障碍一样也要重规划）。
  auto appendStr = [&blob](const std::string & s) {
      for (char c : s) {blob.push_back(static_cast<int8_t>(c));}
      blob.push_back(0);
    };
  auto appendDouble = [&blob](double v) {
      uint8_t b[8];
      std::memcpy(b, &v, sizeof(b));
      for (size_t i = 0; i < sizeof(b); ++i) {blob.push_back(static_cast<int8_t>(b[i]));}
    };
  appendStr(g.frame);
  appendDouble(g.resolution);
  appendDouble(g.origin_x);
  appendDouble(g.origin_y);
  appendDouble(static_cast<double>(g.width));
  appendDouble(static_cast<double>(g.height));
  // 阻挡格的**扁平索引**（不是逐格值）：同一障碍换分辨率后索引变了，hash 也该变。
  for (int iy = 0; iy < g.height; ++iy) {
    for (int ix = 0; ix < g.width; ++ix) {
      const CellBand b = cellBandAt(g, ix, iy);
      if (b != CellBand::kInscribed && b != CellBand::kLethal) {continue;}
      const int32_t idx = iy * g.width + ix;
      const uint8_t * raw = reinterpret_cast<const uint8_t *>(&idx);
      for (size_t k = 0; k < sizeof(idx); ++k) {blob.push_back(static_cast<int8_t>(raw[k]));}
    }
  }
  return fnv1aBytes(blob);
}

// 已知自由（`kFree`）格数。用于「探索推进」判据。
inline long freeCellCount(const GridView & g)
{
  if (!gridGeometryOk(g)) {return 0;}
  long n = 0;
  const size_t total = static_cast<size_t>(g.width) * static_cast<size_t>(g.height);
  for (size_t i = 0; i < total; ++i) {
    if (g.cells[i] == 0) {++n;}
  }
  return n;
}

// 地图签名快照（规划器每拍比较它决定是否重规划）。
struct MapSignature
{
  std::string blocked_hash;
  long free_cells{0};

  bool valid() const {return !blocked_hash.empty() && blocked_hash != "invalid";}
};

inline MapSignature computeMapSignature(const GridView & g)
{
  MapSignature s;
  if (!gridGeometryOk(g)) {return s;}
  s.blocked_hash = blockedSignature(g);
  s.free_cells = freeCellCount(g);
  return s;
}

// 重规划判据：阻挡集变 **或** 已知自由面积变化超阈值。
//
// **阈值为什么必须存在**：`publish_deadband=5` 的量化 + 单帧毛刺会让自由格数抖动
// 几十格；不设阈值就是伪触发重规划。实测探索步进的增量是 +1433..+2403 格，
// 与噪声差一个数量级（见文件头）。
inline bool signatureChanged(
  const MapSignature & a, const MapSignature & b, int free_delta_cells)
{
  if (!a.valid() || !b.valid()) {return true;}
  if (a.blocked_hash != b.blocked_hash) {return true;}
  const long delta = std::labs(b.free_cells - a.free_cells);
  return delta > static_cast<long>(free_delta_cells < 0 ? 0 : free_delta_cells);
}

}  // namespace planner
}  // namespace agc_ground

#endif  // AGC_GROUND__OCCUPANCY_GRID_VIEW_HPP_
