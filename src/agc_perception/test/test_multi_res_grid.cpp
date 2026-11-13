// 多分辨率派生层与米制膨胀的纯逻辑测试（不启 ROS / 不启仿真）。
//
// 守护的核心行为（本仓对 dense_map 小障碍的表示能力上限）：
//   * 0.5 m 粗格能表达"这一格只有 25% 被占"，而不是只能回答 0 或 100；
//   * 规划层用 max-pool（保守），评价层用占据率（精确）—— 两者**不得**混用；
//   * 膨胀按**米**，换分辨率不改变物理余量；
//   * 距离变换在"没有种子"时不产生 NaN。
#include <cmath>
#include <fstream>
#include <regex>
#include <limits>
#include <vector>

#include <gtest/gtest.h>

#include "agc_perception/inflation_field.hpp"
#include "agc_perception/multi_res_grid.hpp"

using agc_perception::classifyRisk;
using agc_perception::distanceFieldMeters;
using agc_perception::InflationParams;
using agc_perception::kNoSeedThreshold;
using agc_perception::maxPoolMap;
using agc_perception::maxPoolOccupied;
using agc_perception::MultiResGeometry;
using agc_perception::occupancyRatio;
using agc_perception::occupancyRatioMap;
using agc_perception::PlanRisk;
using agc_perception::riskField;
using agc_perception::squaredDistanceTransform;

namespace
{

// 构造一个 4×4 细格（0.25 m）→ 2×2 粗格（0.5 m）的几何。
MultiResGeometry make4x4()
{
  MultiResGeometry geo;
  geo.fine_resolution = 0.25;
  geo.fine_width = 4;
  geo.fine_height = 4;
  geo.fine_origin_x = -0.5;
  geo.fine_origin_y = -0.5;
  geo.factor = 2;
  return geo;
}

}  // namespace

// ------------------------------------------------------------------ 几何关系

TEST(MultiRes, CoarseGeometryIsIntegerDerived)
{
  const MultiResGeometry geo = make4x4();
  ASSERT_TRUE(geo.valid());
  EXPECT_EQ(geo.coarseWidth(), 2);
  EXPECT_EQ(geo.coarseHeight(), 2);
  EXPECT_DOUBLE_EQ(geo.coarseResolution(), 0.5);
  // 粗层与细层**同一 origin**：不做重采样，格点严格对齐。
  EXPECT_DOUBLE_EQ(geo.coarseOriginX(), geo.fine_origin_x);
  EXPECT_DOUBLE_EQ(geo.coarseOriginY(), geo.fine_origin_y);
}

// 非整数倍必须被显式拒绝：Nav2 的 factor 是 unsigned int、RACER 用 *=0.5，
// 两者都只能表达整数倍；非整数倍会引入随坐标漂移的半格错位。
TEST(MultiRes, RejectsNonIntegerFactor)
{
  MultiResGeometry geo = make4x4();
  geo.factor = 0;
  EXPECT_FALSE(geo.valid()) << "factor=0 会让 coarseWidth()=0，必须判无效";
  geo.factor = 2;
  EXPECT_TRUE(geo.valid());
}

// 细格数不能被 factor 整除时，多余的行/列**丢弃**，不补 0。
// 补 0 会让"不存在的细格"与"未观测的细格"混为一谈。
TEST(MultiRes, PartialEdgeCellsAreDroppedNotPadded)
{
  MultiResGeometry geo = make4x4();
  geo.fine_width = 5;    // 5 / 2 = 2（余 1 列丢弃）
  geo.fine_height = 3;   // 3 / 2 = 1（余 1 行丢弃）
  EXPECT_EQ(geo.coarseWidth(), 2);
  EXPECT_EQ(geo.coarseHeight(), 1);
}

// ------------------------------------------------------------------ 连续占据率

// **核心判据**：0.5 m 格能表达"只有一部分被占"。
// 1 个细格被占 / 4 个细格 = 0.25 —— 这正是 temp.md 里"占据比例 0.31"要表达的东西，
// 而旧的二值快照只能说 100 或 0。
TEST(MultiRes, OccupancyRatioExpressesPartialCoverage)
{
  const MultiResGeometry geo = make4x4();
  // 只让粗格 (0,0) 覆盖的细格 (0,0) 被占：占 1/4。
  auto occupied = [](size_t idx) {return idx == 0;};
  EXPECT_DOUBLE_EQ(occupancyRatio(geo, 0, 0, occupied), 0.25);
  // 全占 = 1.0
  auto all = [](size_t) {return true;};
  EXPECT_DOUBLE_EQ(occupancyRatio(geo, 0, 0, all), 1.0);
  // 全不占 = 0.0
  auto none = [](size_t) {return false;};
  EXPECT_DOUBLE_EQ(occupancyRatio(geo, 1, 1, none), 0.0);
}

// 分母固定为 factor×factor，**不是**"已观测的细格数"。
// 若分母只数已观测格，一个只看到 1 格、而那格被占的粗格会得到 1.0 —— 与整格全占
// 无法区分，评价会系统性高估。这条判据防止有人"顺手"改成按观测数归一。
TEST(MultiRes, OccupancyRatioDenominatorIsFixedNotObserved)
{
  const MultiResGeometry geo = make4x4();
  // 只观测 1 个细格且它被占 ⇒ 固定分母下是 0.25，而不是 1.0。
  auto only_first_observed = [](size_t idx) {return idx == 0;};
  const double r = occupancyRatio(geo, 0, 0, only_first_observed);
  EXPECT_DOUBLE_EQ(r, 0.25);
  EXPECT_LT(r, 1.0) << "分母若按已观测数归一，这里会变成 1.0（系统性高估）";
}

// 越界粗格返回 0，不越界读。
TEST(MultiRes, OccupancyRatioOutOfRangeIsZero)
{
  const MultiResGeometry geo = make4x4();
  auto all = [](size_t) {return true;};
  EXPECT_DOUBLE_EQ(occupancyRatio(geo, -1, 0, all), 0.0);
  EXPECT_DOUBLE_EQ(occupancyRatio(geo, 2, 0, all), 0.0);
  EXPECT_DOUBLE_EQ(occupancyRatio(geo, 0, 2, all), 0.0);
}

// 占据率整图与逐格结果一致（防止整图版本与单格版本分叉）。
TEST(MultiRes, RatioMapMatchesPerCellQuery)
{
  const MultiResGeometry geo = make4x4();
  auto occupied = [](size_t idx) {return idx == 0 || idx == 5;};
  const auto map = occupancyRatioMap(geo, occupied);
  ASSERT_EQ(map.size(), 4u);
  EXPECT_FLOAT_EQ(map[0], static_cast<float>(occupancyRatio(geo, 0, 0, occupied)));
  EXPECT_FLOAT_EQ(map[3], static_cast<float>(occupancyRatio(geo, 1, 1, occupied)));
}

// ------------------------------------------------------------------ 规划层 max-pool

// **规划层必须保守**：粗格里只要有一个子格确认占据，整格就是占据。
// 用"占据率过门限"会把 25% 覆盖的小障碍过滤掉 —— 车（半径 0.6 m）照样撞上去。
TEST(MultiRes, PlanningLayerIsConservativeMaxPool)
{
  const MultiResGeometry geo = make4x4();
  auto one_cell = [](size_t idx) {return idx == 0;};
  EXPECT_TRUE(maxPoolOccupied(geo, 0, 0, one_cell))
    << "1/4 覆盖也必须在规划层判为占据（安全优先）";
  EXPECT_FALSE(maxPoolOccupied(geo, 1, 0, one_cell));
}

// 规划层与评价层对**同一个输入**给出不同结论，这正是"两层语义不同"的证据。
// 若有人把规划层改成用占据率，这条会红。
TEST(MultiRes, PlanningAndEvaluationLayersDisagreeByDesign)
{
  const MultiResGeometry geo = make4x4();
  auto one_cell = [](size_t idx) {return idx == 0;};
  const double ratio = occupancyRatio(geo, 0, 0, one_cell);
  const bool planned = maxPoolOccupied(geo, 0, 0, one_cell);
  EXPECT_DOUBLE_EQ(ratio, 0.25);
  EXPECT_TRUE(planned);
  EXPECT_LT(ratio, 0.5) << "几何上只占 1/4";
  EXPECT_TRUE(planned) << "但规划上必须当整格障碍";
}

TEST(MultiRes, MaxPoolMapMatchesPerCellQuery)
{
  const MultiResGeometry geo = make4x4();
  auto occupied = [](size_t idx) {return idx == 2;};   // 粗格 (1,0) 的左下子格
  const auto map = maxPoolMap(geo, occupied);
  ASSERT_EQ(map.size(), 4u);
  EXPECT_EQ(map[0], 0);
  EXPECT_EQ(map[1], 1) << "粗格 (1,0) 应被判占据";
  EXPECT_EQ(map[2], 0);
  EXPECT_EQ(map[3], 0);
}

// ------------------------------------------------------------------ 距离变换

// 单种子：距离平方必须等于欧氏格距平方（不是曼哈顿距离）。
TEST(DistanceTransform, SquaredEuclideanNotManhattan)
{
  const int w = 5, h = 5;
  std::vector<uint8_t> seed(static_cast<size_t>(w) * h, 0);
  seed[0] = 1;                                  // 左上角 (0,0)
  const auto sq = squaredDistanceTransform(w, h, seed);
  // (3,4) 的格距平方 = 9 + 16 = 25；曼哈顿距离会是 7（平方 49）。
  EXPECT_DOUBLE_EQ(sq[static_cast<size_t>(4) * w + 3], 25.0);
  // (1,1) = 1 + 1 = 2
  EXPECT_DOUBLE_EQ(sq[static_cast<size_t>(1) * w + 1], 2.0);
  // 种子自身 = 0
  EXPECT_DOUBLE_EQ(sq[0], 0.0);
}

// **精确性判据**：与暴力 O(N³) 逐格对拍。这是距离变换唯一真正重要的性质 ——
// 膨胀半径是米，距离算错就直接变成安全余量算错。
// 覆盖 1×1–9×9 全部尺寸 × 全部单种子位置。
TEST(DistanceTransform, MatchesBruteForceForAllSingleSeedPositions)
{
  for (int w = 1; w <= 9; ++w) {
    for (int h = 1; h <= 9; ++h) {
      for (int sy = 0; sy < h; ++sy) {
        for (int sx = 0; sx < w; ++sx) {
          std::vector<uint8_t> seed(static_cast<size_t>(w) * h, 0);
          seed[static_cast<size_t>(sy) * w + sx] = 1;
          const auto sq = squaredDistanceTransform(w, h, seed);
          for (int y = 0; y < h; ++y) {
            for (int x = 0; x < w; ++x) {
              const double expect = (x - sx) * (x - sx) + (y - sy) * (y - sy);
              ASSERT_NEAR(sq[static_cast<size_t>(y) * w + x], expect, 1e-9)
                << "w=" << w << " h=" << h << " seed=(" << sx << "," << sy
                << ") at (" << x << "," << y << ")";
            }
          }
        }
      }
    }
  }
}

// 多种子（最近者胜）：验证两遍可分离变换确实给出**欧氏**最近距离，
// 而不是"先竖直后水平各自取最近"这种错误组合。
TEST(DistanceTransform, MatchesBruteForceWithMultipleSeeds)
{
  for (int w = 1; w <= 8; ++w) {
    for (int h = 1; h <= 8; ++h) {
      std::vector<uint8_t> seed(static_cast<size_t>(w) * h, 0);
      for (int i = 0; i < w * h; i += 3) {seed[static_cast<size_t>(i)] = 1;}
      const auto sq = squaredDistanceTransform(w, h, seed);
      for (int y = 0; y < h; ++y) {
        for (int x = 0; x < w; ++x) {
          double best = std::numeric_limits<double>::max();
          for (int j = 0; j < h; ++j) {
            for (int i = 0; i < w; ++i) {
              if (!seed[static_cast<size_t>(j) * w + i]) {continue;}
              const double d = (x - i) * (x - i) + (y - j) * (y - j);
              if (d < best) {best = d;}
            }
          }
          ASSERT_NEAR(sq[static_cast<size_t>(y) * w + x], best, 1e-9)
            << "w=" << w << " h=" << h << " at (" << x << "," << y << ")";
        }
      }
    }
  }
}

// **无种子必须落在哨兵区间，且米制距离是 +inf**（不是 0、不是某个有限小数）。
// 若有人把"无种子"当成"距离 0"，整张没有障碍的图会被判成 kLethal ——
// 车原地不敢动，且原因看不出来。
TEST(DistanceTransform, NoSeedYieldsInfiniteMetersNotZero)
{
  const int w = 4, h = 4;
  std::vector<uint8_t> none(static_cast<size_t>(w) * h, 0);
  const auto sq = squaredDistanceTransform(w, h, none);
  for (size_t i = 0; i < sq.size(); ++i) {
    EXPECT_FALSE(std::isnan(sq[i])) << "无种子时出现 NaN（索引 " << i << "）";
    EXPECT_GE(sq[i], kNoSeedThreshold) << "无种子格必须落在哨兵区间（索引 " << i << "）";
  }
  const auto meters = distanceFieldMeters(w, h, 0.5, none);
  for (float d : meters) {
    EXPECT_FALSE(std::isfinite(d)) << "没有占据格时距离必须是 +inf";
  }
  // 整张空图的风险场必须全自由（无种子 ⇒ 无风险）
  InflationParams p;
  const auto risk = riskField(w, h, 0.5, none, p);
  for (uint8_t r : risk) {
    EXPECT_EQ(r, static_cast<uint8_t>(PlanRisk::kFree));
  }
}

// 米制距离 = 格距 × resolution。这是"膨胀按米"的前提。
TEST(DistanceTransform, MetersScaleWithResolution)
{
  const int w = 5, h = 1;
  std::vector<uint8_t> seed(static_cast<size_t>(w) * h, 0);
  seed[0] = 1;
  const auto at05 = distanceFieldMeters(w, h, 0.5, seed);
  const auto at025 = distanceFieldMeters(w, h, 0.25, seed);
  // 第 4 列：格距 4 ⇒ 0.5 m 栅格上 2.0 m，0.25 m 栅格上 1.0 m。
  EXPECT_FLOAT_EQ(at05[4], 2.0f);
  EXPECT_FLOAT_EQ(at025[4], 1.0f);
}

// ------------------------------------------------------------------ 米制风险分档

// **换分辨率不改变物理余量**：同一个物理场景（占据格 + 车半径 0.6 m）在不同
// 分辨率下，判为 kInscribed 的世界半径必须一致。
TEST(Inflation, RiskBandsAreMetricNotCellCount)
{
  InflationParams p;
  p.robot_radius_m = 0.6;
  p.inflation_radius_m = 1.0;
  // 米制判据本身与分辨率无关
  EXPECT_EQ(classifyRisk(0.0, p), PlanRisk::kLethal);
  EXPECT_EQ(classifyRisk(0.3, p), PlanRisk::kInscribed);
  EXPECT_EQ(classifyRisk(0.6, p), PlanRisk::kInscribed);
  EXPECT_EQ(classifyRisk(0.7, p), PlanRisk::kInflated);
  EXPECT_EQ(classifyRisk(1.0, p), PlanRisk::kInflated);
  EXPECT_EQ(classifyRisk(1.1, p), PlanRisk::kFree);
  EXPECT_EQ(classifyRisk(std::numeric_limits<double>::infinity(), p), PlanRisk::kFree);
}

// 一个占据格在 0.5 m 栅格上的风险场：邻居在 0.5 m ⇒ 内切带（车半径 0.6 m）。
// 若有人把膨胀写成 `ceil(radius/res)` 的格数，0.5 m 栅格会变成 ceil(0.6/0.5)=2 格
// = 1.0 m，比设计意图大 —— 这条判据把"米"钉死。
TEST(Inflation, NeighbourCellRiskFollowsMeters)
{
  const int w = 3, h = 1;
  std::vector<uint8_t> occ(static_cast<size_t>(w) * h, 0);
  occ[1] = 1;                       // 中间格占据
  InflationParams p;
  p.robot_radius_m = 0.6;
  p.inflation_radius_m = 1.0;
  const auto risk = riskField(w, h, 0.5, occ, p);
  EXPECT_EQ(risk[1], static_cast<uint8_t>(PlanRisk::kLethal));
  // 相邻格距 0.5 m ≤ 0.6 m ⇒ 内切（不是"再膨胀 2 格"）
  EXPECT_EQ(risk[0], static_cast<uint8_t>(PlanRisk::kInscribed));
  EXPECT_EQ(risk[2], static_cast<uint8_t>(PlanRisk::kInscribed));
}

// **判定顺序决定安全性**：`robot_radius` 必须**先于** `inflation_radius` 判。
// 这样即使配置成 `inflation_radius < robot_radius`（`kInflated` 带为空），
// 车半径内的格仍然被判成 `kInscribed` —— 不会因为漏了 `kInflated` 带而放行。
// 若有人把两条判据的顺序对调，0.7 m 处会先命中 `> inflation_radius(0.5)` 而放行，
// 车心（半径 1.0 m）就撞上去了 —— 这条判据把顺序钉死。
TEST(Inflation, RobotRadiusCheckPrecedesInflationRadius)
{
  InflationParams bad;
  bad.robot_radius_m = 1.0;
  bad.inflation_radius_m = 0.5;   // 配置不当：比车半径还小
  // 0.7 m：超过 inflation_radius，但仍在 robot_radius 内 ⇒ 必须仍是 kInscribed。
  EXPECT_EQ(classifyRisk(0.7, bad), PlanRisk::kInscribed)
    << "顺序对调会让这里放行（kFree），车心半径内被当成可通行";
  // 1.0 m 恰好是车半径边界 ⇒ 内切
  EXPECT_EQ(classifyRisk(1.0, bad), PlanRisk::kInscribed);
  // 1.1 m 才自由
  EXPECT_EQ(classifyRisk(1.1, bad), PlanRisk::kFree);
}

// 正常配置下三档必须**同时存在**（不能出现空档）：
// 占据格 → 内切 → 膨胀 → 自由，四档按距离单调。
TEST(Inflation, AllRiskBandsAreReachable)
{
  InflationParams p;
  p.robot_radius_m = 0.6;
  p.inflation_radius_m = 1.0;
  EXPECT_EQ(classifyRisk(0.0, p), PlanRisk::kLethal);
  EXPECT_EQ(classifyRisk(0.5, p), PlanRisk::kInscribed);
  EXPECT_EQ(classifyRisk(0.9, p), PlanRisk::kInflated);
  EXPECT_EQ(classifyRisk(1.5, p), PlanRisk::kFree);
}

// ------------------------------------------------------------------ 四态派生（/agc/map 语义）

// **合并优先级**：占据 > 有证据未跨门限 > 未知 > 自由。
// 这条顺序是"规划安全优先 + 不把未观测折成自由"的直接实现。
TEST(PlanningCell, MergePriorityIsConservative)
{
  using agc_perception::planningCellValue;
  // 任一占据 ⇒ 占据
  const int8_t a[] = {-1, 0, 45, 100};
  EXPECT_EQ(planningCellValue(a, 4), 100);
  // 无占据但有概率 ⇒ 取最大概率
  const int8_t b[] = {-1, 0, 45, 12};
  EXPECT_EQ(planningCellValue(b, 4), 45);
  // 无占据无概率但有未知 ⇒ 未知（不得折成 free）
  const int8_t c[] = {-1, 0, 0, 0};
  EXPECT_EQ(planningCellValue(c, 4), -1) << "部分未观测不得对规划器承诺安全";
  // 全自由 ⇒ free
  const int8_t d[] = {0, 0, 0, 0};
  EXPECT_EQ(planningCellValue(d, 4), 0);
}

// 空/非法输入必须安全（返回 unknown，不是崩溃、不是 free）。
TEST(PlanningCell, DegenerateInputIsUnknownNotFree)
{
  using agc_perception::planningCellValue;
  EXPECT_EQ(planningCellValue(nullptr, 4), -1);
  const int8_t a[] = {0};
  EXPECT_EQ(planningCellValue(a, 0), -1);
}

// 整图派生：与逐格派生一致；尺寸不符返回空（不产出半张图）。
TEST(PlanningCell, PlanningSnapshotMatchesPerCellDerivation)
{
  MultiResGeometry geo = make4x4();
  std::vector<int8_t> fine(16, -1);
  fine[0] = 100;      // 粗格 (0,0) 有一个占据子格
  fine[5] = 0;        // 粗格 (1,0)
  fine[6] = 0;
  fine[7] = 0;
  fine[9] = 0;
  const auto coarse = agc_perception::planningSnapshot(geo, fine);
  ASSERT_EQ(coarse.size(), 4u);
  EXPECT_EQ(coarse[0], 100) << "含占据子格 ⇒ 整格占据";
  EXPECT_EQ(coarse[3], -1) << "仍有未观测子格 ⇒ unknown，不是 free";

  // 尺寸不符 ⇒ 空 vector
  std::vector<int8_t> wrong(9, -1);
  EXPECT_TRUE(agc_perception::planningSnapshot(geo, wrong).empty());
}

// ------------------------------------------------------------------ 风险图 → /agc/map 取值（ADR-0041）

// **风险分档到栅格值的映射必须单调、且不越界**：
// 几何占据 100 > 内切 99 > 有代价 1–98 > 自由 0。这个数值序是下游
// `classifyCell`（`>=100` 才算 occupied）与 Nav2 比例代价共同依赖的。
TEST(RiskGridValue, MonotonicAndInRange)
{
  using agc_perception::classifyRisk;
  using agc_perception::riskToGridValue;
  InflationParams p;
  p.robot_radius_m = 0.6;
  p.inflation_radius_m = 1.0;

  // 占据 → 100
  EXPECT_EQ(riskToGridValue(classifyRisk(0.0, p), 0.0, p), 100);
  // 内切带 → 99（不是 100：格内没有占据，只是车心会擦碰）
  EXPECT_EQ(riskToGridValue(classifyRisk(0.5, p), 0.5, p), 99);
  // 膨胀带 → 1..98
  const int near = riskToGridValue(classifyRisk(0.65, p), 0.65, p);
  const int far = riskToGridValue(classifyRisk(0.95, p), 0.95, p);
  EXPECT_GE(near, 1); EXPECT_LE(near, 98);
  EXPECT_GE(far, 1);  EXPECT_LE(far, 98);
  // 贴车半径处代价更高（数值更大）
  EXPECT_GT(near, far) << "越靠近车半径代价必须越高（否则规划器不会避让）";
  // 外缘外 → 0
  EXPECT_EQ(riskToGridValue(classifyRisk(1.5, p), 1.5, p), 0);
}

// 有代价档**不得**产出 0 或 100：那会把"有代价"读成"自由"或"致命"。
TEST(RiskGridValue, InflatedBandNeverCollapsesToEndpoints)
{
  using agc_perception::classifyRisk;
  using agc_perception::riskToGridValue;
  InflationParams p;
  p.robot_radius_m = 0.6;
  p.inflation_radius_m = 1.0;
  for (double d = 0.61; d < 1.0; d += 0.01) {
    const int v = riskToGridValue(classifyRisk(d, p), d, p);
    ASSERT_GE(v, 1) << "d=" << d << " 被压成 0（会被读成可通行）";
    ASSERT_LE(v, 98) << "d=" << d << " 被压成 100（会被读成致命占据）";
  }
}

// 未知格必须保持 -1：距离场只对有占据的图有意义。
// 若把未观测区按距离判成 free，就是对规划器的过度承诺（ADR-0035 三态纪律）。
TEST(RiskGridValue, UnknownStaysUnknownNotFree)
{
  // 这一条由 map_adapter 的 `if (geom < 0) {data[i] = -1; continue;}` 保证。
  // 在源码层钉住它，防止有人"顺手"把未知也过一遍风险分档。
  // **必须用 ifstream 读全文**：`std::string(const char*)` 会在第一个 NUL 处截断，
  // 而源文件不是 C 字符串。用错会得到"永远找不到"的假失败（本用例踩过）。
  std::ifstream in(AGC_MAP_ADAPTER_SRC);
  ASSERT_TRUE(in.good()) << "读不到 map_adapter.cpp：" << AGC_MAP_ADAPTER_SRC;
  const std::string src((std::istreambuf_iterator<char>(in)),
                        std::istreambuf_iterator<char>());
  EXPECT_NE(src.find("if (geom < 0) {data[i] = -1; continue;}"), std::string::npos)
    << "未知格必须在风险分档之前短路成 -1，不得按距离判成 free";
}

// ---------------------------------------------------------------------------
// 任意 factor（ADR-0042）：不只 2
// ---------------------------------------------------------------------------
//
// **为什么必须测**：改造前 `perception_resolution` 只验证过 0.25→0.5（factor=2），
// 而 temp.md 要的 0.1 m 评价图需要 factor=5。factor=3 / 5 若在某个角落写死了 2
// （例如 `2*2` 的分母、`cx*2` 的索引），只会在大图上表现为"偶发错位"，极难归因。
// 这里用**小尺寸穷举**把所有 factor 都跑一遍。

TEST(MultiResArbitrary, AllFactorsDeriveConsistentGeometry)
{
  for (int f : {1, 2, 3, 4, 5, 7}) {
    MultiResGeometry geo;
    geo.fine_resolution = 0.1;
    geo.fine_width = 10 * f;      // 保证整除
    geo.fine_height = 10 * f;
    geo.fine_origin_x = 0.0;
    geo.fine_origin_y = 0.0;
    geo.factor = f;
    ASSERT_TRUE(geo.valid()) << "factor=" << f;
    EXPECT_EQ(geo.coarseWidth(), 10) << "factor=" << f;
    EXPECT_EQ(geo.coarseHeight(), 10) << "factor=" << f;
    // 粗分辨率 = 细分辨率 × factor（**不是**写死的 0.5）
    EXPECT_DOUBLE_EQ(geo.coarseResolution(), 0.1 * f) << "factor=" << f;
  }
}

TEST(MultiResArbitrary, OccupancyRatioDenominatorIsFactorSquared)
{
  // 只有**一格**细格被占时，占据率必须是 1/factor²。
  // 分母写死 4（factor=2 的值）会让 factor=5 时报 0.25 而不是 0.04 —— 4 倍虚高。
  for (int f : {1, 2, 3, 5}) {
    MultiResGeometry geo;
    geo.fine_resolution = 0.1;
    geo.fine_width = f;
    geo.fine_height = f;
    geo.factor = f;
    // 只有 (0,0) 占据
    auto occupied = [f](size_t idx) {return idx == 0;};
    const double r = occupancyRatio(geo, 0, 0, occupied);
    EXPECT_NEAR(r, 1.0 / (f * f), 1e-12) << "factor=" << f;
  }
}

TEST(MultiResArbitrary, MaxPoolSeesEverySubCell)
{
  // max-pool 必须扫描**全部** factor² 个子格。若只扫了 2×2（写死），
  // 那么"占据落在第 3 行/列"的格会被漏判成 free —— 规划安全直接失效。
  const int f = 5;
  MultiResGeometry geo;
  geo.fine_resolution = 0.1;
  geo.fine_width = f;
  geo.fine_height = f;
  geo.factor = f;
  // 逐个位置放一个占据格，每次都必须被 max-pool 看到
  for (int y = 0; y < f; ++y) {
    for (int x = 0; x < f; ++x) {
      const size_t seed = static_cast<size_t>(y) * f + x;
      auto occupied = [seed](size_t idx) {return idx == seed;};
      EXPECT_TRUE(maxPoolOccupied(geo, 0, 0, occupied))
        << "子格 (" << x << "," << y << ") 被漏掉（max-pool 未覆盖全部 factor²）";
      // 占据率同步：单格 = 1/f²
      EXPECT_NEAR(occupancyRatio(geo, 0, 0, occupied), 1.0 / (f * f), 1e-12);
    }
  }
}

TEST(MultiResArbitrary, PlanningSnapshotPreservesFourStateSemantics)
{
  // factor=3 下的四态合并：占据 > 概率 > 未知 > 自由。
  // 逐条独立验证，避免"顺序对了但某一档没生效"。
  const int f = 3;
  MultiResGeometry geo;
  geo.fine_resolution = 0.1;
  geo.fine_width = f;
  geo.fine_height = f;
  geo.factor = f;
  const size_t n = static_cast<size_t>(f) * f;

  auto run = [&](std::vector<int8_t> fine) {
      const auto out = planningSnapshot(geo, fine);
      EXPECT_EQ(out.size(), 1u);
      return out.empty() ? int8_t(-2) : out[0];
    };

  // 全自由 ⇒ 0
  EXPECT_EQ(run(std::vector<int8_t>(n, 0)), 0);
  // 全未知 ⇒ -1
  EXPECT_EQ(run(std::vector<int8_t>(n, -1)), -1);
  // 一个占据 + 其余未知 ⇒ 100（占据压过未知）
  {
    std::vector<int8_t> v(n, -1);
    v[4] = 100;
    EXPECT_EQ(run(v), 100);
  }
  // 一个概率 + 其余未知 ⇒ 概率（概率压过未知）
  {
    std::vector<int8_t> v(n, -1);
    v[8] = 42;
    EXPECT_EQ(run(v), 42);
  }
  // 概率取**最大**：3 与 77 ⇒ 77
  {
    std::vector<int8_t> v(n, 0);
    v[0] = 3;
    v[1] = 77;
    EXPECT_EQ(run(v), 77);
  }
  // 全自由 + 一个未知 ⇒ 未知（不得对规划器承诺"确认安全"）
  {
    std::vector<int8_t> v(n, 0);
    v[7] = -1;
    EXPECT_EQ(run(v), -1);
  }
}

TEST(MultiResArbitrary, SnapshotRejectsWrongSizeInsteadOfHalfMap)
{
  // 细层尺寸不符时必须返回空（调用方据此走"全 unknown"回退），
  // **不得**静默产出一张半对的图 —— 半对的图会被当成真实几何消费。
  MultiResGeometry geo;
  geo.fine_resolution = 0.1;
  geo.fine_width = 3;
  geo.fine_height = 3;
  geo.factor = 3;
  EXPECT_TRUE(planningSnapshot(geo, std::vector<int8_t>(8, 0)).empty());
  EXPECT_TRUE(planningSnapshot(geo, std::vector<int8_t>(10, 0)).empty());
  EXPECT_EQ(planningSnapshot(geo, std::vector<int8_t>(9, 0)).size(), 1u);
}

// ---------------------------------------------------------------------------
// 源码层闸门：声明过的参数必须真的生效（ADR-0042）
// ---------------------------------------------------------------------------
//
// **为什么需要这条**：实测发现 `instance_confirm_hits` / `instance_expire_misses` /
// `instance_associate_gate_m` 三个参数只被 `declare_parameter` 读了、**从未**传给
// `InstanceTracker` —— 于是改配置毫无效果，而且没有任何提示。
// 这类"参数存在即完成"的假象比缺参数更危险：它让调参变成自我安慰。
//
// 判据：每个 `xxx_ = declare_parameter<T>("xxx", ...)` 的参数名，其成员 `xxx_`
// 必须在**别处**（非声明行）至少再出现一次。只出现一次 = 声明了但没用。
TEST(ParamWiring, EveryDeclaredParameterIsActuallyUsed)
{
  std::ifstream in(AGC_MAP_ADAPTER_SRC);
  ASSERT_TRUE(in.good()) << "读不到 map_adapter.cpp：" << AGC_MAP_ADAPTER_SRC;
  const std::string src((std::istreambuf_iterator<char>(in)),
                        std::istreambuf_iterator<char>());

  // 找出所有 "成员_ = declare_parameter<...>("参数名"" 的行
  const std::regex decl(
    "([A-Za-z_][A-Za-z0-9_]*_)\\s*=\\s*declare_parameter<[^>]*>\\s*\\(\\s*\"([^\"]+)\"",
    std::regex::ECMAScript);
  std::vector<std::pair<std::string, std::string>> declared;
  for (auto it = std::sregex_iterator(src.begin(), src.end(), decl);
    it != std::sregex_iterator(); ++it)
  {
    declared.emplace_back((*it)[1].str(), (*it)[2].str());
  }
  ASSERT_FALSE(declared.empty()) << "一个参数声明都没找到（正则失效？）";

  std::vector<std::string> dead;
  for (const auto & [member, pname] : declared) {
    // 统计该成员名在全文出现的次数（含声明行本身）
    size_t count = 0;
    for (size_t pos = src.find(member); pos != std::string::npos;
      pos = src.find(member, pos + member.size()))
    {
      ++count;
    }
    // 只出现 1 次 = 只有声明行 = 声明了从未使用。
    // 2 次可能是"声明 + 成员定义"，那仍然**没有消费者** ⇒ 也判死。
    if (count <= 2) {dead.push_back(pname + " (" + member + ", " + std::to_string(count) + " 次)");}
  }
  std::string report;
  for (const auto & d : dead) {report += "\n  - " + d;}
  EXPECT_TRUE(dead.empty())
    << "以下参数声明了但从未被消费（改配置不会有任何效果）：" << report;
}
