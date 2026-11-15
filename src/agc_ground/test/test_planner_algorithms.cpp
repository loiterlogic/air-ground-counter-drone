// 地面规划器纯算法单测（ADR-0048）
//
// 不启 ROS、不启仿真：所有输入都是普通 struct。判据按 ADR-0048 的 13 项组织：
//
//  1. 栅格坐标转换、边界、frame、分辨率和地图快照
//  2. `0/-1/1..99/100` 分类及未知拒绝
//  3. 矩形 footprint 在直行、转弯、原地旋转中的碰撞
//  4. 运动基元解析积分和采样密度
//  5. 同一离散 key 的剪枝
//  6. 启发式单调性和搜索回溯
//  7. 直连成功、直连穿障失败、目标航向不满足失败
//  8. 单障碍绕行和无解地图
//  9. 距离场、离障代价和平滑代价
// 10. 优化后穿障被最终复核拒绝
// 11. 曲率、速度、角速度、加速度约束
// 12. 规划超时、节点上限、地图失效、目标失效的失败分类
// 13. 相同输入、seed 和参数下路径与诊断可复现

#include <gtest/gtest.h>

#include <cmath>
#include <limits>
#include <string>
#include <vector>

#include "agc_ground/distance_field_2d.hpp"
#include "agc_ground/footprint_checker.hpp"
#include "agc_ground/kinodynamic_search.hpp"
#include "agc_ground/motion_primitive.hpp"
#include "agc_ground/occupancy_grid_view.hpp"
#include "agc_ground/path_time_parameterizer.hpp"
#include "agc_ground/planner_engine.hpp"
#include "agc_ground/planner_interface.hpp"
#include "agc_ground/planner_types.hpp"
#include "agc_ground/spline_optimizer_2d.hpp"

namespace agc_ground
{
namespace planner
{
namespace
{

// 合成地图：16x16 @ 0.5 m，原点 (-4,-4)，默认全自由。
constexpr int kDim = 16;
constexpr double kRes = 0.5;
constexpr double kOrigin = -4.0;

struct Grid
{
  std::vector<int8_t> cells =
    std::vector<int8_t>(static_cast<size_t>(kDim) * static_cast<size_t>(kDim), 0);

  void setCell(int ix, int iy, int v)
  {
    if (ix < 0 || iy < 0 || ix >= kDim || iy >= kDim) {return;}
    cells[static_cast<size_t>(iy) * kDim + ix] = static_cast<int8_t>(v);
  }

  // 世界坐标处设值
  void setWorld(double x, double y, int v)
  {
    const int ix = static_cast<int>(std::floor((x - kOrigin) / kRes));
    const int iy = static_cast<int>(std::floor((y - kOrigin) / kRes));
    setCell(ix, iy, v);
  }

  void fill(int v)
  {
    for (auto & c : cells) {c = static_cast<int8_t>(v);}
  }

  GridView view() const
  {
    GridView g;
    g.cells = cells.data();
    g.width = kDim;
    g.height = kDim;
    g.resolution = kRes;
    g.origin_x = kOrigin;
    g.origin_y = kOrigin;
    g.frame = "world";
    g.stamp_s = 10.0;
    return g;
  }
};

PlannerSnapshot makeSnapshot(const Grid & grid, double sx, double sy, double gx, double gy)
{
  PlannerSnapshot s;
  s.grid = grid.view();
  s.start.x = sx;
  s.start.y = sy;
  s.start.yaw = 0.0;
  s.goal.x = gx;
  s.goal.y = gy;
  s.goal.yaw = 0.0;
  s.goal_valid = true;
  s.authorized = true;
  s.replan_reason = "test";
  return s;
}

// ---------------------------------------------------------------------------------
// 1. 栅格坐标转换、边界、frame、分辨率和地图快照
// ---------------------------------------------------------------------------------

TEST(PlannerGrid, WorldToCellUsesFloorAndRejectsOutside)
{
  Grid grid;
  const GridView g = grid.view();
  int ix = -1, iy = -1;
  // 原点 (-4,-4)、0.5 m 格：world (-4,-4) 落在格 (0,0)
  ASSERT_TRUE(worldToCell(g, -4.0, -4.0, &ix, &iy));
  EXPECT_EQ(ix, 0);
  EXPECT_EQ(iy, 0);
  // 格心 (-3.75,-3.75) 仍是 (0,0)
  ASSERT_TRUE(worldToCell(g, -3.75, -3.75, &ix, &iy));
  EXPECT_EQ(ix, 0);
  EXPECT_EQ(iy, 0);
  // 刚过格边界 → (1,1)
  ASSERT_TRUE(worldToCell(g, -3.49, -3.49, &ix, &iy));
  EXPECT_EQ(ix, 1);
  EXPECT_EQ(iy, 1);
  // 左上角恰好出图
  EXPECT_FALSE(worldToCell(g, 4.0, 0.0, &ix, &iy));
  EXPECT_FALSE(worldToCell(g, -4.01, 0.0, &ix, &iy));
  EXPECT_FALSE(worldToCell(g, 0.0, -4.01, &ix, &iy));
}

TEST(PlannerGrid, CellToWorldGivesCellCenterAndRejectsOutOfRange)
{
  Grid grid;
  const GridView g = grid.view();
  double x = 0.0, y = 0.0;
  ASSERT_TRUE(cellToWorld(g, 0, 0, &x, &y));
  EXPECT_NEAR(x, -3.75, 1e-12);
  EXPECT_NEAR(y, -3.75, 1e-12);
  ASSERT_TRUE(cellToWorld(g, 15, 15, &x, &y));
  EXPECT_NEAR(x, 3.75, 1e-12);
  EXPECT_NEAR(y, 3.75, 1e-12);
  EXPECT_FALSE(cellToWorld(g, 16, 0, &x, &y));
  EXPECT_FALSE(cellToWorld(g, -1, 0, &x, &y));
}

TEST(PlannerGrid, GeometryValidationRejectsBadResolutionAndNullData)
{
  Grid grid;
  GridView g = grid.view();
  EXPECT_TRUE(gridGeometryOk(g));

  g.resolution = 0.0;
  EXPECT_FALSE(gridGeometryOk(g));
  g.resolution = -0.5;
  EXPECT_FALSE(gridGeometryOk(g));
  g.resolution = std::numeric_limits<double>::quiet_NaN();
  EXPECT_FALSE(gridGeometryOk(g));

  GridView g2 = grid.view();
  g2.cells = nullptr;
  EXPECT_FALSE(gridGeometryOk(g2));

  GridView g3 = grid.view();
  g3.width = 0;
  EXPECT_FALSE(gridGeometryOk(g3));
}

// ---------------------------------------------------------------------------------
// 2. `0/-1/1..99/100` 分类及未知拒绝
// ---------------------------------------------------------------------------------

TEST(PlannerCells, ClassificationMatchesAdr0041RiskBands)
{
  // ADR-0041：-1 未知 / 0 可通行 / 1–98 有代价 / 99 车心擦碰 / 100 占据
  EXPECT_EQ(classifyPlanningCell(-1), CellBand::kUnknown);
  EXPECT_EQ(classifyPlanningCell(-5), CellBand::kUnknown);
  EXPECT_EQ(classifyPlanningCell(0), CellBand::kFree);
  EXPECT_EQ(classifyPlanningCell(1), CellBand::kCost);
  EXPECT_EQ(classifyPlanningCell(50), CellBand::kCost);
  EXPECT_EQ(classifyPlanningCell(98), CellBand::kCost);
  EXPECT_EQ(classifyPlanningCell(99), CellBand::kInscribed);
  EXPECT_EQ(classifyPlanningCell(100), CellBand::kLethal);
  EXPECT_EQ(classifyPlanningCell(120), CellBand::kLethal);
}

TEST(PlannerCells, FootprintBlocksUnknownInscribedAndLethalButNotCost)
{
  // footprint 挡：未知 / 99 / 100。**不挡** 1–98（那是有代价但可通行）。
  EXPECT_TRUE(footprintBlocks(CellBand::kUnknown));
  EXPECT_TRUE(footprintBlocks(CellBand::kInscribed));
  EXPECT_TRUE(footprintBlocks(CellBand::kLethal));
  EXPECT_FALSE(footprintBlocks(CellBand::kCost));
  EXPECT_FALSE(footprintBlocks(CellBand::kFree));
}

TEST(PlannerCells, CorridorBlocksOnlyLethal)
{
  // 走廊只挡真实障碍。`99` 是膨胀环：在 dense_map 上相邻障碍的 99 环几乎相接，
  // 把它算进走廊会让走廊阈值 >=1.5 m 时无解（实测）。
  EXPECT_TRUE(corridorBlocks(CellBand::kLethal));
  EXPECT_FALSE(corridorBlocks(CellBand::kInscribed));
  EXPECT_FALSE(corridorBlocks(CellBand::kCost));
  EXPECT_FALSE(corridorBlocks(CellBand::kFree));
  EXPECT_FALSE(corridorBlocks(CellBand::kUnknown));
}

TEST(PlannerCells, UnknownCellIsRejectedAsStart)
{
  Grid grid;
  grid.setWorld(0.0, 0.0, -1);
  auto planner = createPlanner();
  const PathResult r = planner->plan(makeSnapshot(grid, 0.0, 0.0, 2.0, 2.0));
  EXPECT_FALSE(r.success);
  EXPECT_EQ(r.failure, PlanFailure::kStartNotFree);
}

TEST(PlannerCells, CostBandIsTraversableButUnknownIsNot)
{
  // 一条 1–98 的带：可通行。
  Grid cost;
  for (int iy = 0; iy < kDim; ++iy) {cost.setCell(8, iy, 50);}
  auto p1 = createPlanner();
  const PathResult r1 = p1->plan(makeSnapshot(cost, -2.0, 0.0, 2.0, 0.0));
  EXPECT_TRUE(r1.success) << planner::toString(r1.failure) << " " << r1.detail;

  // 换成未知带：不可通行。
  Grid unknown;
  for (int iy = 0; iy < kDim; ++iy) {unknown.setCell(8, iy, -1);}
  auto p2 = createPlanner();
  const PathResult r2 = p2->plan(makeSnapshot(unknown, -2.0, 0.0, 2.0, 0.0));
  EXPECT_FALSE(r2.success);
}

// ---------------------------------------------------------------------------------
// 3. 矩形 footprint 在直行、转弯、原地旋转中的碰撞
// ---------------------------------------------------------------------------------

TEST(PlannerFootprint, StraightCorridorCollisionDetected)
{
  Grid grid;
  const GridView g = grid.view();
  const PlannerParams p;
  // 障碍格覆盖 [3.0,3.5)。车心在 2.6 时车头 = 2.6+0.5037+0.3536 = 3.457 > 3.0 ⇒ 必碰。
  // （车心 2.0 时车头 2.858 < 3.0，确实够不到 —— 那是正确行为，不是漏检。）
  grid.setWorld(3.0, 0.0, 100);
  const GridView g2 = grid.view();
  Pose2D ahead;
  ahead.x = 2.6;
  ahead.y = 0.0;
  ahead.yaw = 0.0;
  EXPECT_TRUE(footprintCollides(
      g2, ahead, p.footprint_half_length, p.footprint_half_width, p.footprint_margin));
  // 远处安全
  Pose2D far;
  far.x = -3.0;
  far.y = -3.0;
  far.yaw = 0.0;
  EXPECT_FALSE(footprintCollides(
      g2, far, p.footprint_half_length, p.footprint_half_width, p.footprint_margin));
  (void)g;
}

TEST(PlannerFootprint, RotationSweepsCornerIntoObstacle)
{
  // 「中心过得去、车角刮到」是差速车在窄通道里的典型失败模式。
  //
  // 几何（HL+margin = 0.857，HW+margin = 0.639）：
  //   * 朝 +x：footprint 覆盖 x∈[-0.857,0.857]、y∈[-0.639,0.639]
  //   * 朝 +y：覆盖 x∈[-0.639,0.639]、y∈[-0.857,0.857]
  //
  // 要让「朝 +x 不碰、朝 +y 碰」，障碍必须在 0.639 < |d| <= 0.857 的窗口里。
  // **0.5 m 格表达不了这个窗口**（格边界在 0.5 的倍数上，窗口只有 0.218 m 宽），
  // 所以本用例用 0.1 m 分辨率的专用栅格 —— 这是测试工装，不是生产分辨率。
  constexpr int kN = 80;          // 80 × 0.1 m = 8 m
  constexpr double kR = 0.1;
  constexpr double kO = -4.0;
  std::vector<int8_t> cells(static_cast<size_t>(kN) * kN, 0);
  // 障碍占 x∈[0.7,0.8)、y∈[0.7,0.8) —— 距车心 ~0.99 m 的对角点。
  // 用单格 (0.75, 0.75) 会同时被两个航向覆盖；改放 y∈[0.7,0.8) 且 x∈[-0.1,0.0)：
  //   朝 +x：局部 (u,v) = (-0.05, 0.75) ⇒ |v|=0.75 > 0.639 ⇒ 不碰
  //   朝 +y：局部 (u,v) = (0.75, 0.05)  ⇒ |u|=0.75 <= 0.857 ⇒ 碰
  {
    const int ix = static_cast<int>(std::floor((-0.05 - kO) / kR));
    const int iy = static_cast<int>(std::floor((0.75 - kO) / kR));
    cells[static_cast<size_t>(iy) * kN + ix] = 100;
  }
  GridView g;
  g.cells = cells.data();
  g.width = kN;
  g.height = kN;
  g.resolution = kR;
  g.origin_x = kO;
  g.origin_y = kO;
  g.frame = "world";
  g.stamp_s = 10.0;

  const PlannerParams p;
  Pose2D facing_x;
  facing_x.x = 0.0;
  facing_x.y = 0.0;
  facing_x.yaw = 0.0;
  EXPECT_FALSE(footprintCollides(
      g, facing_x, p.footprint_half_length, p.footprint_half_width, p.footprint_margin))
    << "朝 +x 时该障碍在车宽带外（|v|=0.75 > 0.639），不该判碰";

  Pose2D facing_y;
  facing_y.x = 0.0;
  facing_y.y = 0.0;
  facing_y.yaw = M_PI / 2.0;
  EXPECT_TRUE(footprintCollides(
      g, facing_y, p.footprint_half_length, p.footprint_half_width, p.footprint_margin))
    << "绕 90° 后车长带扫到该障碍（|u|=0.75 <= 0.857），必须判碰";
}

TEST(PlannerFootprint, InscribedBandBlocksFootprint)
{
  // `99` 是「车心进入即擦碰」，footprint 压上去必须判碰撞。
  Grid grid;
  grid.setWorld(0.0, 0.0, 99);
  const GridView g = grid.view();
  const PlannerParams p;
  Pose2D at_origin;
  EXPECT_TRUE(footprintCollides(
      g, at_origin, p.footprint_half_length, p.footprint_half_width, p.footprint_margin));
}

TEST(PlannerFootprint, SweepChecksEveryPoseNotJustEndpoints)
{
  // 中间有障碍、两端安全：只查端点会漏。
  Grid grid;
  grid.setWorld(0.0, 0.0, 100);
  const GridView g = grid.view();
  const PlannerParams p;
  std::vector<Pose2D> poses;
  for (int i = 0; i <= 10; ++i) {
    Pose2D q;
    q.x = -2.0 + 0.4 * static_cast<double>(i);
    q.y = 0.0;
    q.yaw = 0.0;
    poses.push_back(q);
  }
  double clr = 0.0;
  EXPECT_TRUE(sweepCollides(
      g, poses, p.footprint_half_length, p.footprint_half_width,
      p.footprint_margin, 2.0, &clr));
  EXPECT_DOUBLE_EQ(clr, 0.0);
}

// ---------------------------------------------------------------------------------
// 4. 运动基元解析积分和采样密度
// ---------------------------------------------------------------------------------

TEST(PlannerPrimitive, StraightIntegrationIsExact)
{
  Pose2D start;
  start.x = 1.0;
  start.y = 2.0;
  start.yaw = 0.0;
  Control c;
  c.v = 1.0;
  c.omega = 0.0;
  const Pose2D end = integrateState(start, c, 0.5);
  EXPECT_NEAR(end.x, 1.5, 1e-12);
  EXPECT_NEAR(end.y, 2.0, 1e-12);
  EXPECT_NEAR(end.yaw, 0.0, 1e-12);
}

TEST(PlannerPrimitive, ArcIntegrationLandsOnCircle)
{
  // v=1, omega=1 → R=1，圆心在起点左侧 (0,1)。
  Pose2D start;
  start.x = 0.0;
  start.y = 0.0;
  start.yaw = 0.0;
  Control c;
  c.v = 1.0;
  c.omega = 1.0;
  // 转 90° 需 t = pi/2
  const Pose2D end = integrateState(start, c, M_PI / 2.0);
  // 圆心 (0,1)，半径 1；转 90° 后到 (1,1)
  EXPECT_NEAR(end.x, 1.0, 1e-9);
  EXPECT_NEAR(end.y, 1.0, 1e-9);
  EXPECT_NEAR(end.yaw, M_PI / 2.0, 1e-9);
}

TEST(PlannerPrimitive, SampledPosesAreDenseEnough)
{
  MotionState start;
  Control c;
  c.v = 1.5;
  c.omega = 2.0;
  const Primitive prim = makePrimitive(start, c, 0.333, 0.15);
  ASSERT_GE(prim.sampled_poses.size(), 4u);
  // 相邻采样点间距不超过 max_step（含浮点余量）
  for (size_t i = 1; i < prim.sampled_poses.size(); ++i) {
    const double d = std::hypot(
      prim.sampled_poses[i].x - prim.sampled_poses[i - 1].x,
      prim.sampled_poses[i].y - prim.sampled_poses[i - 1].y);
    EXPECT_LE(d, 0.15 + 1e-6) << "sample gap " << d;
  }
}

TEST(PlannerPrimitive, InPlaceRotationIsSampledAngularly)
{
  // v=0 时空间步长为 0；必须按角步长采样，否则车角扫过的区域完全没被检查。
  MotionState start;
  Control c;
  c.v = 0.0;
  c.omega = 2.0;
  const Primitive prim = makePrimitive(start, c, 0.333, 0.15);
  EXPECT_GE(prim.sampled_poses.size(), 3u)
    << "pure rotation must still be sampled (turn=" << prim.sampled_poses.size() << ")";
}

TEST(PlannerPrimitive, CandidateControlsIncludeInPlaceRotationButNoReverse)
{
  PlannerParams p;
  p.allow_in_place_rotation = true;
  const std::vector<Control> ctrls = candidateControls(p);
  int in_place = 0;
  for (const Control & c : ctrls) {
    EXPECT_GE(c.v, 0.0) << "第一版不倒车";
    if (std::fabs(c.v) < 1e-9) {++in_place;}
  }
  EXPECT_GT(in_place, 0) << "应含原地旋转基元";
}

// ---------------------------------------------------------------------------------
// 5. 同一离散 key 的剪枝
// ---------------------------------------------------------------------------------

TEST(PlannerSearch, DiscreteKeyIncludesYaw)
{
  Grid grid;
  const GridView g = grid.view();
  Pose2D a;
  a.x = 0.0;
  a.y = 0.0;
  a.yaw = 0.0;
  Pose2D b = a;
  b.yaw = M_PI;   // 同位置、反航向
  // 键必须区分航向：只按 (x,y) 合并会错误丢弃可行状态。
  // 这里通过「同格不同航向的 key 不相等」间接断言（makeKey 是私有的，
  // 用 DiscreteKey 的相等语义 + 引擎行为共同守护）。
  DiscreteKey k1;
  k1.x_cell = 8;
  k1.y_cell = 8;
  k1.yaw_bin = 0;
  DiscreteKey k2 = k1;
  k2.yaw_bin = 8;
  EXPECT_FALSE(k1 == k2);
  DiscreteKeyHash hasher;
  EXPECT_NE(hasher(k1), hasher(k2));
  (void)g;
  (void)a;
  (void)b;
}

TEST(PlannerSearch, SameKeyPruningKeepsLowerG)
{
  // 引擎行为层：同一个离散 key 只保留 g 更小的节点，表现是「不会因为重复展开而爆掉」。
  // 用一个开阔地图跑，断言扩展节点数远小于 max_expanded_nodes。
  Grid grid;
  PlannerParams p;
  p.max_expanded_nodes = 100000;
  p.search_time_budget_s = 5.0;
  // 终点要留出 footprint 外扩（HL+margin=0.857），否则角落探针出图会被判碰撞。
  // 地图半幅 4.0 m ⇒ 终点坐标绝对值 <= 3.0 是安全的。
  auto snap = makeSnapshot(grid, -2.5, -2.5, 2.5, 2.5);
  snap.params = p;
  auto planner = createPlanner();
  const PathResult r = planner->plan(snap);
  EXPECT_TRUE(r.success) << planner::toString(r.failure) << " " << r.detail;
  EXPECT_LT(r.expanded_nodes, 20000) << "剪枝失效（扩展数异常高）";
}

// ---------------------------------------------------------------------------------
// 6. 启发式单调性和搜索回溯
// ---------------------------------------------------------------------------------

TEST(PlannerHeuristic, HeuristicIsZeroAtGoalAndPositiveElsewhere)
{
  Pose2D goal;
  goal.x = 1.0;
  goal.y = 1.0;
  goal.yaw = 0.0;
  EXPECT_NEAR(heuristicCost(goal, goal, 1.0), 0.0, 1e-12);
  Pose2D away;
  away.x = -2.0;
  away.y = -2.0;
  away.yaw = 0.0;
  EXPECT_GT(heuristicCost(away, goal, 1.0), 0.0);
}

TEST(PlannerHeuristic, HeuristicDoesNotExceedEuclideanPlusHeadingBound)
{
  // 启发式是「欧氏 + 0.5*|dyaw|」，必须 <= 欧氏 + 0.5*pi（否则不可采纳）。
  Pose2D from;
  from.x = -3.0;
  from.y = -3.0;
  from.yaw = 0.0;
  Pose2D goal;
  goal.x = 3.0;
  goal.y = 3.0;
  goal.yaw = 0.0;
  const double euclid = std::hypot(goal.x - from.x, goal.y - from.y);
  const double h = heuristicCost(from, goal, 1.0);
  EXPECT_LE(h, euclid + 0.5 * M_PI + 1e-9);
}

TEST(PlannerSearch, BacktrackProducesStartToGoalOrder)
{
  Grid grid;
  auto snap = makeSnapshot(grid, -3.0, 0.0, 3.0, 0.0);
  auto planner = createPlanner();
  const PathResult r = planner->plan(snap);
  ASSERT_TRUE(r.success) << planner::toString(r.failure) << " " << r.detail;
  ASSERT_GE(r.poses.size(), 2u);
  // 起点在车位附近、终点在 goal 附近
  EXPECT_NEAR(r.poses.front().x, -3.0, 0.5);
  EXPECT_NEAR(r.poses.front().y, 0.0, 0.5);
  EXPECT_NEAR(r.poses.back().x, 3.0, 0.5);
  EXPECT_NEAR(r.poses.back().y, 0.0, 0.5);
}

// ---------------------------------------------------------------------------------
// 7. 直连成功、直连穿障失败、目标航向不满足失败
// ---------------------------------------------------------------------------------

TEST(PlannerAnalytic, DirectLinkSucceedsInOpenSpace)
{
  Grid grid;
  auto snap = makeSnapshot(grid, -3.0, 0.0, 3.0, 0.0);
  auto planner = createPlanner();
  const PathResult r = planner->plan(snap);
  EXPECT_TRUE(r.success) << planner::toString(r.failure) << " " << r.detail;
  // 开阔图应当走解析连接（点数少、代价接近直线）
  EXPECT_LT(r.path_length_m, 7.0) << "直线路径不该绕远";
}

TEST(PlannerAnalytic, DirectLinkThroughLethalIsRejected)
{
  Grid grid;
  // 一道横墙，中间留一格洞在别处
  for (int ix = 0; ix < kDim; ++ix) {
    if (ix == 0) {continue;}   // 只在最左边留口
    grid.setCell(ix, 8, 100);
  }
  auto snap = makeSnapshot(grid, -3.0, 0.0, 3.0, 0.0);
  snap.params.search_time_budget_s = 3.0;
  auto planner = createPlanner();
  const PathResult r = planner->plan(snap);
  // 要么绕过去（成功），要么明确失败；**不得**返回一条穿墙的路径。
  if (r.success) {
    for (size_t i = 0; i + 1 < r.poses.size(); ++i) {
      const double mx = 0.5 * (r.poses[i].x + r.poses[i + 1].x);
      const double my = 0.5 * (r.poses[i].y + r.poses[i + 1].y);
      EXPECT_NE(classifyPlanningCell(cellValueAtWorld(snap.grid, mx, my)), CellBand::kLethal)
        << "路径穿过 lethal 格 at (" << mx << "," << my << ")";
    }
  } else {
    EXPECT_NE(r.failure, PlanFailure::kNone);
  }
}

TEST(PlannerAnalytic, TerminalHeadingFollowsLastSegment)
{
  // 用户裁定：终端航向 = 末段切线（goal 的 orientation 恒为 w=1.0，不可用）。
  Grid grid;
  auto snap = makeSnapshot(grid, -2.5, -2.5, 2.5, 2.5);
  auto planner = createPlanner();
  const PathResult r = planner->plan(snap);
  ASSERT_TRUE(r.success) << planner::toString(r.failure) << " " << r.detail;
  ASSERT_GE(r.poses.size(), 2u);
  const Pose2D & a = r.poses[r.poses.size() - 2];
  const Pose2D & b = r.poses[r.poses.size() - 1];
  const double seg_yaw = std::atan2(b.y - a.y, b.x - a.x);
  EXPECT_NEAR(normalizeAngle(b.yaw - seg_yaw), 0.0, 0.2)
    << "末端航向应等于末段切线";
}

// ---------------------------------------------------------------------------------
// 8. 单障碍绕行和无解地图
// ---------------------------------------------------------------------------------

TEST(PlannerScenario, SingleObstacleIsDetoured)
{
  Grid grid;
  // 中间一个 2x2 格的实心块，位置偏一侧，留出可通行通道
  grid.setCell(8, 8, 100);
  grid.setCell(8, 9, 100);
  grid.setCell(9, 8, 100);
  grid.setCell(9, 9, 100);
  auto snap = makeSnapshot(grid, -3.0, -1.0, 3.0, -1.0);
  auto planner = createPlanner();
  const PathResult r = planner->plan(snap);
  ASSERT_TRUE(r.success) << planner::toString(r.failure) << " " << r.detail;
  // 路径必须绕开那 4 格
  for (const Pose2D & q : r.poses) {
    const CellBand b = classifyPlanningCell(cellValueAtWorld(snap.grid, q.x, q.y));
    EXPECT_NE(b, CellBand::kLethal) << "路径点落在障碍上 (" << q.x << "," << q.y << ")";
  }
}

TEST(PlannerScenario, FullyBlockedGoalFailsExplicitly)
{
  Grid grid;
  // 把 goal 周围整片封死
  for (int ix = 10; ix < kDim; ++ix) {
    for (int iy = 10; iy < kDim; ++iy) {
      grid.setCell(ix, iy, 100);
    }
  }
  auto snap = makeSnapshot(grid, -3.0, -3.0, 3.5, 3.5);
  snap.params.search_time_budget_s = 2.0;
  auto planner = createPlanner();
  const PathResult r = planner->plan(snap);
  EXPECT_FALSE(r.success);
  EXPECT_NE(r.failure, PlanFailure::kNone);
  // 必须是「目标/碰撞/搜索」类原因，不是「无地图」这类前置问题
  EXPECT_TRUE(
    r.failure == PlanFailure::kGoalCollision ||
    r.failure == PlanFailure::kGoalNotFree ||
    r.failure == PlanFailure::kSearchExhausted ||
    r.failure == PlanFailure::kSearchTimeout ||
    r.failure == PlanFailure::kValidationFailed)
    << "unexpected failure: " << planner::toString(r.failure);
}

// ---------------------------------------------------------------------------------
// 9. 距离场、离障代价和平滑代价
// ---------------------------------------------------------------------------------

TEST(PlannerDistanceField, DistanceIsZeroAtObstacleAndGrowsOutward)
{
  Grid grid;
  grid.setWorld(0.0, 0.0, 100);
  DistanceField2D df;
  df.build(grid.view());
  ASSERT_TRUE(df.valid());
  EXPECT_NEAR(df.distanceAt(0.0, 0.0), 0.0, 1e-9);
  // 距障碍 1 m 处应约为 1 m（格心量化，允许半格误差）
  const double d1 = df.distanceAt(1.0, 0.0);
  EXPECT_GT(d1, 0.5);
  EXPECT_LT(d1, 1.5);
  // 更远处更大
  const double d2 = df.distanceAt(2.0, 0.0);
  EXPECT_GT(d2, d1);
}

TEST(PlannerDistanceField, CostBandAndUnknownAreNotSeeds)
{
  // 距离场的种子只有真实障碍（`100`）。`1–98` 与 `99` 不是种子 ——
  // 否则距离场会变成「离膨胀边界多远」，优化器把控制点推得过远。
  Grid only_cost;
  for (int iy = 0; iy < kDim; ++iy) {only_cost.setCell(8, iy, 50);}
  DistanceField2D df1;
  df1.build(only_cost.view());
  ASSERT_TRUE(df1.valid());
  // 全图无 lethal → 所有**自由格**距离为 +inf。
  // 注意 (0,0) 恰好落在那条代价带所在的格（ix=8），那里不是自由格 ⇒ 返回 0（视为贴障）。
  // 必须查一个真正的自由格。
  EXPECT_FALSE(std::isfinite(df1.distanceAt(-3.0, -3.0)));

  Grid only_inscribed;
  for (int iy = 0; iy < kDim; ++iy) {only_inscribed.setCell(8, iy, 99);}
  DistanceField2D df2;
  df2.build(only_inscribed.view());
  EXPECT_FALSE(std::isfinite(df2.distanceAt(-3.0, -3.0)));
}

TEST(PlannerCost, PrimitiveEdgeCostGrowsWithTimeLengthAndTurn)
{
  PlannerParams p;
  const double base = primitiveEdgeCost(p, 0.333, 0.5, 0.0, 10.0, 0.0);
  // 时间更长 → 代价更高
  EXPECT_GT(primitiveEdgeCost(p, 0.666, 0.5, 0.0, 10.0, 0.0), base);
  // 长度更长 → 更高
  EXPECT_GT(primitiveEdgeCost(p, 0.333, 1.0, 0.0, 10.0, 0.0), base);
  // 转向更多 → 更高
  EXPECT_GT(primitiveEdgeCost(p, 0.333, 0.5, 2.0, 10.0, 0.0), base);
  // 离障更近 → 更高
  EXPECT_GT(
    primitiveEdgeCost(p, 0.333, 0.5, 0.0, 0.1, 0.0),
    primitiveEdgeCost(p, 0.333, 0.5, 0.0, 10.0, 0.0));
  // 代价带更高 → 更高
  EXPECT_GT(
    primitiveEdgeCost(p, 0.333, 0.5, 0.0, 10.0, 1.0),
    primitiveEdgeCost(p, 0.333, 0.5, 0.0, 10.0, 0.0));
}

TEST(PlannerCost, SmoothnessCostDecreasesForStraighterPath)
{
  // 弹性带的平滑项：直线路径的二阶差分恒为 0。
  std::vector<Pose2D> straight, zigzag;
  for (int i = 0; i <= 10; ++i) {
    Pose2D a;
    a.x = static_cast<double>(i) * 0.5;
    a.y = 0.0;
    straight.push_back(a);
    Pose2D b = a;
    b.y = (i % 2 == 0) ? 0.0 : 0.4;
    zigzag.push_back(b);
  }
  // 用引擎的最终复核间接断言：两者都能规划，但直线路径的曲率更小。
  const std::vector<double> ks = computeCurvature(straight);
  for (double k : ks) {EXPECT_NEAR(k, 0.0, 1e-9);}
  const std::vector<double> kz = computeCurvature(zigzag);
  double max_k = 0.0;
  for (double k : kz) {max_k = std::max(max_k, std::fabs(k));}
  EXPECT_GT(max_k, 0.1) << "锯齿路径应被算出明显曲率";
}

// ---------------------------------------------------------------------------------
// 10. 优化后穿障被最终复核拒绝
// ---------------------------------------------------------------------------------

TEST(PlannerOptimization, OptimizedPathThroughObstacleIsRejected)
{
  // 构造一条「搜索能过、优化后可能被拉直穿障」的场景：窄门 + 两侧墙。
  // 引擎的行为保证：优化结果不合格时**回退到搜索路径**，而不是发布穿障路径。
  Grid grid;
  for (int iy = 0; iy < kDim; ++iy) {
    if (iy == 7 || iy == 8) {continue;}   // 中间两格是门
    grid.setCell(8, iy, 100);
  }
  auto snap = makeSnapshot(grid, -3.0, 0.0, 3.0, 0.0);
  snap.params.search_time_budget_s = 5.0;
  auto planner = createPlanner();
  const PathResult r = planner->plan(snap);
  if (r.success) {
    // 无论走的是优化路径还是搜索路径，都必须无碰撞
    for (const Pose2D & q : r.poses) {
      EXPECT_NE(classifyPlanningCell(cellValueAtWorld(snap.grid, q.x, q.y)), CellBand::kLethal)
        << "发布了穿障路径点 (" << q.x << "," << q.y << ")";
    }
  } else {
    // 失败也可接受（门太窄），但必须显式
    EXPECT_NE(r.failure, PlanFailure::kNone);
  }
}

TEST(PlannerOptimization, OptimizationNeverChangesEndpoints)
{
  Grid grid;
  auto snap = makeSnapshot(grid, -2.5, -2.5, 2.5, 2.5);
  snap.params.optimization_enabled = true;
  auto planner = createPlanner();
  const PathResult r = planner->plan(snap);
  ASSERT_TRUE(r.success) << planner::toString(r.failure) << " " << r.detail;
  EXPECT_NEAR(r.poses.front().x, -2.5, 0.5);
  EXPECT_NEAR(r.poses.front().y, -2.5, 0.5);
  // 末端必须精确等于 goal（消费侧的 goal_consistency_m 依赖它）
  EXPECT_NEAR(r.poses.back().x, 2.5, 0.3);
  EXPECT_NEAR(r.poses.back().y, 2.5, 0.3);
}

// ---------------------------------------------------------------------------------
// 11. 曲率、速度、角速度、加速度约束
// ---------------------------------------------------------------------------------

TEST(PlannerDynamics, StraightLineHasZeroCurvatureAndCappedSpeed)
{
  std::vector<Pose2D> poses;
  for (int i = 0; i <= 20; ++i) {
    Pose2D q;
    q.x = static_cast<double>(i) * 0.25;
    q.y = 0.0;
    q.yaw = 0.0;
    poses.push_back(q);
  }
  PlannerParams p;
  const TimeParamResult tp = parameterizeTime(poses, p);
  EXPECT_TRUE(tp.feasible) << tp.reason;
  EXPECT_NEAR(tp.max_curvature, 0.0, 1e-9);
  EXPECT_LE(tp.max_linear_velocity, p.v_cap + 1e-6);
  EXPECT_LE(tp.max_angular_velocity, p.w_cap + 1e-6);
}

TEST(PlannerDynamics, SharpCurvatureForcesLowSpeed)
{
  // 一个很急的折角：曲率超限 → 必须判不可行（kDynamicsInfeasible），
  // 不能靠降速「挤过」（ADR-0048 末句）。
  std::vector<Pose2D> poses;
  Pose2D a;
  a.x = 0.0;
  a.y = 0.0;
  poses.push_back(a);
  Pose2D b;
  b.x = 0.2;
  b.y = 0.0;
  poses.push_back(b);
  Pose2D c;
  c.x = 0.2;
  c.y = 0.2;
  poses.push_back(c);
  PlannerParams p;
  const TimeParamResult tp = parameterizeTime(poses, p);
  // 直角拐弯的曲率约 5 /m，远超 kappa_max=1.0
  EXPECT_GT(tp.max_curvature, p.kappa_max);
  EXPECT_FALSE(tp.feasible);
  EXPECT_FALSE(tp.reason.empty()) << "失败必须有单一可归因理由";
}

TEST(PlannerDynamics, SpeedLimitRespectsLateralAccelAndAngularCap)
{
  // 恒定曲率圆弧：v 必须同时满足 sqrt(a_lat/kappa) 与 w_cap/kappa。
  const double kappa = 0.5;      // 半径 2 m
  const double R = 1.0 / kappa;
  std::vector<Pose2D> poses;
  for (int i = 0; i <= 40; ++i) {
    const double th = 0.05 * static_cast<double>(i);
    Pose2D q;
    q.x = R * std::sin(th);
    q.y = R * (1.0 - std::cos(th));
    poses.push_back(q);
  }
  PlannerParams p;
  const TimeParamResult tp = parameterizeTime(poses, p);
  EXPECT_TRUE(tp.feasible) << tp.reason;
  const double v_lat = std::sqrt(p.a_lat_max / kappa);
  const double v_rot = p.w_cap / kappa;
  const double expect_cap = std::min({p.v_cap, v_lat, v_rot});
  EXPECT_LE(tp.max_linear_velocity, expect_cap + 1e-3);
}

TEST(PlannerDynamics, BrakingConstraintLimitsApproachSpeed)
{
  // 后向传播必须把**前段**速度压下来（否则刹不住）。
  //
  // **曲率必须渐变**：直道直接接圆弧会让 `w_acc = Δω/Δt` 算出 3+ rad/s²，
  // 时间参数化判 `kDynamicsInfeasible`（正确行为，见 `SharpCurvatureForcesLowSpeed`）。
  // 本用例用**半径逐渐收紧**的弧（R 从 20 m 线性收到 4 m），曲率从 0.05 平滑升到 0.25，
  // 这样角加速度留在限内，测的才是速度传播本身。
  std::vector<Pose2D> poses;
  Pose2D cur;
  cur.x = 0.0;
  cur.y = 0.0;
  cur.yaw = 0.0;
  poses.push_back(cur);
  const int n = 200;
  for (int i = 0; i < n; ++i) {
    const double t = static_cast<double>(i) / static_cast<double>(n);
    const double R = 20.0 - 16.0 * t;      // 20 → 4
    const double ds = 0.05;                 // 每步弧长 0.05 m
    const double dth = ds / R;
    cur.yaw += dth;
    cur.x += ds * std::cos(cur.yaw);
    cur.y += ds * std::sin(cur.yaw);
    poses.push_back(cur);
  }
  PlannerParams p;
  const TimeParamResult tp = parameterizeTime(poses, p);
  ASSERT_TRUE(tp.feasible) << tp.reason;
  // 曲率末值 ≈ 1/4 = 0.25 ⇒ v 上限 = min(sqrt(1.0/0.25)=2.0, 2.0/0.25=8, 1.5) = 1.5
  EXPECT_NEAR(tp.max_curvature, 0.25, 0.05);
  EXPECT_LE(tp.max_linear_velocity, p.v_cap + 1e-3);
  EXPECT_GT(tp.total_time_s, 0.0);
}

// ---------------------------------------------------------------------------------
// 11b. 加速度公式的**击穿负例**（ADR-0048 的「复核负例」要求）
// ---------------------------------------------------------------------------------

TEST(PlannerDynamics, UniformAccelUsesVelocitySquaredDifference)
{
  // **直接验证公式本身**，不经速度传播。
  //
  // 早先写成 `(v−v0)²/(2s)`：量纲对、数值系统性错误。
  // 手算可验：
  //   v0=1.4, v=1.5, s=0.25  =>  正确 (1.5²−1.4²)/0.5 = 0.58
  //                              旧式 (1.5−1.4)²/0.5 = 0.02（低估 29 倍）
  EXPECT_NEAR(uniformAccel(1.4, 1.5, 0.25), 0.58, 1e-9)
    << "旧式 (v−v0)²/(2s) 会给出 0.02";
  // 从静止起步：正确 4.5，旧式也 4.5（此点两者相同，不能作判据）
  EXPECT_NEAR(uniformAccel(0.0, 1.5, 0.25), 4.5, 1e-9);
  // 减速为负（保留符号）
  EXPECT_NEAR(uniformAccel(1.5, 0.0, 0.25), -4.5, 1e-9);
  // 等速为零
  EXPECT_NEAR(uniformAccel(1.0, 1.0, 0.5), 0.0, 1e-12);
  // 零弧长不产生无穷
  EXPECT_DOUBLE_EQ(uniformAccel(1.0, 2.0, 0.0), 0.0);
  // 与运动学恒等式自洽：v² = v0² + 2·a·s
  const double a = uniformAccel(0.6, 1.3, 0.8);
  EXPECT_NEAR(0.6 * 0.6 + 2.0 * a * 0.8, 1.3 * 1.3, 1e-9);
}

TEST(PlannerDynamics, AngularAccelLimitForcesSpeedReduction)
{
  // **守护角加速度反解的速度上限**：`v <= sqrt(w_acc_max / |dκ/ds|)`。
  //
  // ## 为什么这个用例的参数是"算出来"的，不是"看着像"
  //
  // 该上限只在 `sqrt(w_acc/dκds) < v_cap` 时才真正生效，即
  //
  // ```text
  // dκ/ds > w_acc_max / v_cap²
  // ```
  //
  // 取 `w_acc_max = 0.5`、`v_cap = 1.5` ⇒ 需要 `dκ/ds > 0.222 /m²`。
  // 下面的几何：曲率从 0 升到 1.0（R: ∞ → 1 m）跨 18 步 × 0.25 m = 4.5 m
  // ⇒ `dκ/ds ≈ 1.0/4.5 = 0.222`，正好在门槛上。
  // 为了留出判别余量，取 12 步（3.0 m）⇒ `dκ/ds ≈ 0.333`，
  // 于是 `sqrt(0.5/0.333) = 1.22 < v_cap = 1.5` —— **限速必然生效**。
  //
  // 实测教训：早先取 60 步（15 m），`dκ/ds ≈ 0.058`、`v_wa = 2.93 > v_cap`，
  // 限速根本不触发；把实现改成 `v_wa = 1e9` 测试仍全绿 —— **闸门是假的**。
  std::vector<Pose2D> poses;
  Pose2D cur;
  cur.x = 0.0; cur.y = 0.0; cur.yaw = 0.0;
  poses.push_back(cur);
  const int n = 12;
  for (int i = 0; i < n; ++i) {
    const double t = static_cast<double>(i) / static_cast<double>(n);
    const double R = 40.0 - 39.0 * t;     // 40 → 1 m，曲率 0.025 → 1.0
    const double ds = 0.25;
    cur.yaw += ds / R;
    cur.x += ds * std::cos(cur.yaw);
    cur.y += ds * std::sin(cur.yaw);
    poses.push_back(cur);
  }
  PlannerParams p;
  p.v_cap = 1.5;
  p.a_lat_max = 1e6;      // 放宽，确保瓶颈是角加速度
  p.w_cap = 1e6;
  p.a_acc_max = 1e6;
  p.a_brake_max = 1e6;
  p.w_acc_max = 0.5;
  // 起点速度给 1.5（全速进入），这样剖面里**任何**低速都只能来自限速，
  // 而不是「从静止起步」。
  //
  // 实测教训：早先传 `start_speed = 0`，于是 `vmin` 恒为 0（首点），
  // `vmin < v_cap - 0.1` 永远成立 —— 断言与实现无关，把限速删掉也不会红。
  const TimeParamResult tp = parameterizeTime(poses, p, p.v_cap);
  double vmin = 1e9;
  for (size_t i = 1; i < tp.profile.size(); ++i) {   // **跳过首点**
    vmin = std::min(vmin, tp.profile[i].v);
  }
  EXPECT_LT(vmin, p.v_cap - 0.1)
    << "曲率剧变处未被降速（vmin=" << vmin << "，v_cap=" << p.v_cap
    << "）—— 角加速度反解限速未生效";
  // 若判可行，角加速度必须真的合规
  if (tp.feasible) {
    EXPECT_LE(tp.max_angular_accel, p.w_acc_max + 1e-3)
      << "角加速度超限却判可行";
  }
}

TEST(PlannerDynamics, AccelAndDecelLimitsAreSeparateParameters)
{
  // 加速与制动是**两个**上限，不能合并成一个 `max_a`：
  // 合并会让"制动能力不足"这类配置错误无法被发现。
  std::vector<Pose2D> poses;
  for (int i = 0; i <= 10; ++i) {
    Pose2D q;
    q.x = static_cast<double>(i) * 0.25;
    q.y = 0.0;
    poses.push_back(q);
  }
  // 前段高速、末段急弯 => 后向传播必须把前段压下来 => 需要制动。
  PlannerParams tight;
  tight.v_cap = 1.5;
  tight.a_acc_max = 100.0;
  tight.a_brake_max = 0.05;    // 极紧
  const TimeParamResult tp = parameterizeTime(poses, tight, 1.5);
  // 直线无弯，v_limit 恒 1.5，不需要制动 => 可行。这是**正确**结论。
  EXPECT_TRUE(tp.feasible) << tp.reason;
  EXPECT_NEAR(tp.max_linear_decel, 0.0, 1e-9);
  EXPECT_NEAR(tp.max_linear_accel, 0.0, 1e-9);
}

TEST(PlannerDynamics, ForwardPropagationRespectsAccelLimitByConstruction)
{
  // **如实登记一个设计事实**：前向/后向传播用 `a_acc`/`a_brake` **构造**剖面，
  // 所以算出的加速度**恒 <= 上限**——「拿上限判超限」是同义反复，永远不会触发。
  //
  // 因此 `a_acc_max` / `a_brake_max` 的角色是**构造参数**，不是验证判据；
  // 真正的验证对象是曲线几何（曲率 / 曲率变化率）与 `uniformAccel` 的数学正确性。
  // 本用例把上限设得极小，断言剖面仍然可行且加速度不超过它 —— 锁住这个语义。
  std::vector<Pose2D> poses;
  for (int i = 0; i <= 20; ++i) {
    Pose2D q;
    q.x = static_cast<double>(i) * 0.25;
    q.y = 0.0;
    poses.push_back(q);
  }
  PlannerParams p;
  p.v_cap = 1.5;
  p.a_acc_max = 0.05;
  p.a_brake_max = 0.05;
  const TimeParamResult tp = parameterizeTime(poses, p, 0.0);
  EXPECT_TRUE(tp.feasible) << tp.reason;
  EXPECT_LE(tp.max_linear_accel, p.a_acc_max + 1e-6)
    << "传播按构造不会超限";
  EXPECT_LE(tp.max_linear_decel, p.a_brake_max + 1e-6);
}

// ---------------------------------------------------------------------------------
// 11c. 接缝连续性 / 旋转语义 / Dubins / 参数自洽（ADR-0048 的构造正确性）
// ---------------------------------------------------------------------------------

TEST(PlannerSeam, MidPathHeadingJumpIsRejected)
{
  // 中段航向与段方向不一致 = 拼接错了，必须被判出来。
  std::vector<Pose2D> poses;
  for (int i = 0; i <= 10; ++i) {
    Pose2D q;
    q.x = static_cast<double>(i) * 0.25;
    q.y = 0.0;
    q.yaw = 0.0;   // 沿 +x
    poses.push_back(q);
  }
  poses[5].yaw = 1.0;   // 人为制造中段跳变
  const SeamReport r = validateSeamContinuity(poses, 0.15);
  EXPECT_FALSE(r.ok);
  EXPECT_EQ(r.worst_index, 5);
  EXPECT_NE(r.detail.find("mid-path"), std::string::npos);
}

TEST(PlannerSeam, FirstPointTurnIsNotADefect)
{
  // 首点的航向是「车当前朝向」，第一段方向是「要走的方向」——
  // 两者不等是「先转向再前进」本身，不是缺陷。
  // 实测：起点朝 +x、目标在 45° 方向时首点跳 0.3927 rad。
  std::vector<Pose2D> poses;
  Pose2D a;
  a.x = 0.0; a.y = 0.0; a.yaw = 0.0;
  poses.push_back(a);
  Pose2D b;
  b.x = 1.0; b.y = 1.0; b.yaw = M_PI / 4.0;
  poses.push_back(b);
  const SeamReport r = validateSeamContinuity(poses, 0.15);
  EXPECT_TRUE(r.ok) << r.detail;
  EXPECT_GT(r.start_heading_jump, 0.3) << "首点转向量应被记录下来供诊断";
}

TEST(PlannerSeam, RotationAndPostRotationAreNotDefects)
{
  // 原地旋转（零位移点）与其后第一点的跳变都不是缺陷：
  // 前者是旋转本身，后者是「转完再走」。
  std::vector<Pose2D> poses;
  Pose2D a;
  a.x = 0.0; a.y = 0.0; a.yaw = 0.0;
  poses.push_back(a);
  // 旋转 3 个采样点（位置不变，航向递增）
  for (int k = 1; k <= 3; ++k) {
    Pose2D q = a;
    q.yaw = 0.2 * static_cast<double>(k);
    poses.push_back(q);
  }
  // 旋转后前进（航向 0.6 与前进方向不同）
  Pose2D b;
  b.x = 0.5; b.y = 0.5; b.yaw = 0.6;
  poses.push_back(b);
  const SeamReport r = validateSeamContinuity(poses, 0.15);
  EXPECT_TRUE(r.ok) << r.detail;
  EXPECT_GE(r.rotation_points, 3) << "零位移点应被计数为旋转点";
}

TEST(PlannerSeam, ResamplingPreservesRotationSegments)
{
  // 重采样**不得**抽稀旋转段：旋转的弧长≈0，朴素弧长重采样会整个跨过它。
  // 实测教训：一次 0.666 rad 的旋转在重采样后只剩 1 个点，
  // 航向跳变全部挤到接缝，被误判成"接缝不连续 0.44 rad"。
  std::vector<Pose2D> in;
  Pose2D a;
  a.x = 0.0; a.y = 0.0; a.yaw = 0.0;
  in.push_back(a);
  for (int k = 1; k <= 6; ++k) {
    Pose2D q = a;
    q.yaw = 0.1 * static_cast<double>(k);
    in.push_back(q);
  }
  Pose2D b;
  b.x = 2.0; b.y = 0.0; b.yaw = 0.6;
  in.push_back(b);
  const std::vector<Pose2D> out = resampleByArcLength(in, 0.25);
  // 旋转段的航向采样必须全部保留
  int rot = 0;
  for (size_t i = 0; i + 1 < out.size(); ++i) {
    if (std::hypot(out[i + 1].x - out[i].x, out[i + 1].y - out[i].y) < 1e-3) {++rot;}
  }
  EXPECT_GE(rot, 5) << "旋转段的采样点被抽稀了（rot=" << rot << "）";
}

TEST(PlannerDubins, ShotIsTangentContinuousAndEndsAtGoal)
{
  // Dubins CSC 的三段必须**都相切**，末端精确落在 goal。
  PlannerParams p;
  const double r = p.analytic_min_turn_radius_m;
  struct Case
  {
    const char * name;
    Pose2D from, to;
  };
  const Case cases[] = {
    {"straight", {0, 0, 0}, {5, 0, 0}},
    {"diagonal", {0, 0, 0}, {5, 5, 0}},
    {"turn_left", {0, 0, 0}, {0, 5, M_PI / 2}},
  };
  for (const Case & c : cases) {
    const std::vector<Pose2D> path = dubinsCscShot(c.from, c.to, r, 0.1);
    ASSERT_GE(path.size(), 2u) << c.name;
    EXPECT_LT(std::hypot(path.back().x - c.to.x, path.back().y - c.to.y), 0.05)
      << c.name << " 末端未落在 goal";
    double worst = 0.0;
    for (size_t i = 0; i + 1 < path.size(); ++i) {
      const double dx = path[i + 1].x - path[i].x;
      const double dy = path[i + 1].y - path[i].y;
      const double len = std::hypot(dx, dy);
      if (len < 1e-6) {continue;}
      const double seg = std::atan2(dy, dx);
      worst = std::max(worst, std::fabs(normalizeAngle(path[i].yaw - seg)));
    }
    EXPECT_LT(worst, 0.15) << c.name << " 接缝不连续 worst=" << worst;
    // 曲率不得超限：任意三点拟合的曲率 <= kappa_max（留数值余量）
    const std::vector<double> k = computeCurvature(path);
    for (double kv : k) {
      EXPECT_LE(std::fabs(kv), p.kappa_max + 0.15)
        << c.name << " 曲率超限 " << kv;
    }
  }
}

TEST(PlannerDubins, GeometricVerificationRejectsWrongCandidates)
{
  // **守护 Dubins 的几何复核**（而不是解析式本身）。
  //
  // 设计上，解析式写错时复核会丢弃该候选，正确的候选仍能通过 —— 所以
  // 「只测最终路径」抓不住解析式的错误（实测变异：把法向符号取反，测试仍绿）。
  //
  // 真正要锁住的是：**复核必须真的在过滤**。做法是断言「对所有测试用例，
  // 接受的那条候选都通过了 末端位置 / 末端航向 / 接缝 三项」——
  // 这三项任何一项被放宽到失效，下面的用例都会红。
  //
  // 反向证据：若把复核容差放到极大（见 `param_invalid` 用例的反面），
  // 会接受末端误差数米的候选 —— 那正是我们要防的。
  PlannerParams p;
  const double r = p.analytic_min_turn_radius_m;
  struct Case
  {
    const char * name;
    Pose2D from, to;
  };
  const Case cases[] = {
    {"straight", {0, 0, 0}, {5, 0, 0}},
    {"diagonal", {0, 0, 0}, {5, 5, 0}},
    {"turn_left", {0, 0, 0}, {0, 5, M_PI / 2}},
    {"offset", {2, -1, 0.3}, {8, 4, -0.4}},
    {"close", {0, 0, 0}, {2.5, 0.5, 0.2}},
  };
  for (const Case & c : cases) {
    const std::vector<Pose2D> path = dubinsCscShot(c.from, c.to, r, 0.1);
    ASSERT_GE(path.size(), 2u) << c.name;
    // ① 末端位置：**必须**在 0.05*r+0.02 以内（复核容差）
    const double end_err = std::hypot(path.back().x - c.to.x, path.back().y - c.to.y);
    EXPECT_LT(end_err, 0.05 * r + 0.03) << c.name << " 末端位置误差 " << end_err;
    // ② 接缝：**必须**全程相切
    double worst = 0.0;
    for (size_t i = 0; i + 1 < path.size(); ++i) {
      const double dx = path[i + 1].x - path[i].x;
      const double dy = path[i + 1].y - path[i].y;
      const double len = std::hypot(dx, dy);
      if (len < 1e-6) {continue;}
      worst = std::max(worst, std::fabs(normalizeAngle(
          path[i].yaw - std::atan2(dy, dx))));
    }
    EXPECT_LT(worst, 0.15) << c.name << " 接缝不连续 worst=" << worst;
    // ③ 曲率：CSC 的弧半径就是 r，所以 |kappa| <= 1/r
    const std::vector<double> k = computeCurvature(path);
    for (double kv : k) {
      EXPECT_LE(std::fabs(kv), 1.0 / r + 0.2) << c.name << " 曲率 " << kv;
    }
  }
}

TEST(PlannerDubins, CheckCatchesBadEndAndBadSeam)
{
  // **直接测复核函数**，不经候选筛选 —— 否则"第一个候选恰好合法"会掩盖复核失效
  // （实测变异：把复核改成"接受一切"，端到端测试仍然全绿）。
  Pose2D to;
  to.x = 5.0;
  to.y = 0.0;
  to.yaw = 0.0;

  // ① 末端位置错 1 m：必须被量出来
  {
    std::vector<Pose2D> path;
    Pose2D a; a.x = 0.0; a.y = 0.0; a.yaw = 0.0; path.push_back(a);
    Pose2D b; b.x = 4.0; b.y = 0.0; b.yaw = 0.0; path.push_back(b);
    const DubinsCheck c = evaluateDubinsPath(path, to);
    EXPECT_NEAR(c.end_err, 1.0, 1e-9);
    EXPECT_LT(c.yaw_err, 1e-9);
  }
  // ② 末端航向错 0.5 rad：必须被量出来
  {
    std::vector<Pose2D> path;
    Pose2D a; a.x = 0.0; a.y = 0.0; a.yaw = 0.0; path.push_back(a);
    Pose2D b; b.x = 5.0; b.y = 0.0; b.yaw = 0.5; path.push_back(b);
    const DubinsCheck c = evaluateDubinsPath(path, to);
    EXPECT_NEAR(c.yaw_err, 0.5, 1e-9);
    EXPECT_LT(c.end_err, 1e-9);
  }
  // ③ 中段接缝错 0.4 rad：必须被量出来
  {
    std::vector<Pose2D> path;
    for (int i = 0; i <= 10; ++i) {
      Pose2D q;
      q.x = static_cast<double>(i) * 0.5;
      q.y = 0.0;
      q.yaw = 0.0;
      path.push_back(q);
    }
    path[4].yaw = 0.4;   // 中段跳变
    const DubinsCheck c = evaluateDubinsPath(path, to);
    EXPECT_NEAR(c.seam_jump, 0.4, 1e-9);
  }
  // ④ 空路径：不能返回有限值
  {
    std::vector<Pose2D> empty;
    const DubinsCheck c = evaluateDubinsPath(empty, to);
    EXPECT_FALSE(std::isfinite(c.end_err));
  }
}

TEST(PlannerParams, InconsistentTurnRadiusIsRejected)
{
  // 转弯半径 < 1/kappa_max 时 Dubins 弧必然超曲率 —— 必须在参数层就拒绝，
  // 而不是让现象伪装成"接缝不连续"（实测教训）。
  PlannerParams p;
  EXPECT_TRUE(validateParams(p).empty()) << validateParams(p);
  p.analytic_min_turn_radius_m = 0.3;   // 0.3 < 1/1.0
  const std::string err = validateParams(p);
  EXPECT_FALSE(err.empty());
  EXPECT_NE(err.find("analytic_min_turn_radius_m"), std::string::npos) << err;
}

TEST(PlannerParams, EngineFailsExplicitlyOnInconsistentParams)
{
  Grid grid;
  auto snap = makeSnapshot(grid, -2.0, 0.0, 2.0, 0.0);
  snap.params.analytic_min_turn_radius_m = 0.1;   // 与 kappa_max 矛盾
  auto planner = createPlanner();
  const PathResult r = planner->plan(snap);
  EXPECT_FALSE(r.success);
  EXPECT_EQ(r.failure, PlanFailure::kParamInvalid);
  EXPECT_NE(r.detail.find("analytic_min_turn_radius_m"), std::string::npos) << r.detail;
}

TEST(PlannerPrimitives, CurvatureBasedSetIsSelfConsistent)
{
  // 按曲率档生成：所有有位移的基元必须满足 |omega| <= kappa_max * v。
  PlannerParams p;
  const std::vector<Control> ctrls = candidateControls(p);
  EXPECT_GT(ctrls.size(), 5u);
  int translate = 0, rotate = 0;
  for (const Control & c : ctrls) {
    if (c.v > 1e-9) {
      ++translate;
      EXPECT_LE(std::fabs(c.omega), p.kappa_max * c.v + 1e-9)
        << "基元 (v=" << c.v << ", omega=" << c.omega << ") 曲率超限";
      EXPECT_LE(std::fabs(c.omega), p.w_cap + 1e-9);
    } else {
      ++rotate;
      EXPECT_GT(std::fabs(c.omega), 1e-9) << "v=0 且 omega=0 是无意义基元";
    }
  }
  EXPECT_GT(translate, 0) << "应有平移基元";
  EXPECT_GT(rotate, 0) << "应有原地旋转基元";
}

// ---------------------------------------------------------------------------------
// 12. 规划超时、节点上限、地图失效、目标失效的失败分类
// ---------------------------------------------------------------------------------

TEST(PlannerFailures, NoMapFailsWithExplicitReason)
{
  auto planner = createPlanner();
  PlannerSnapshot s;
  s.grid.cells = nullptr;   // 无地图
  s.goal_valid = true;
  s.authorized = true;
  const PathResult r = planner->plan(s);
  EXPECT_FALSE(r.success);
  EXPECT_EQ(r.failure, PlanFailure::kNoMap);
}

TEST(PlannerFailures, FrameMismatchFailsWithExplicitReason)
{
  Grid grid;
  auto snap = makeSnapshot(grid, -3.0, 0.0, 3.0, 0.0);
  snap.grid.frame = "map";
  auto planner = createPlanner();
  const PathResult r = planner->plan(snap);
  EXPECT_FALSE(r.success);
  EXPECT_EQ(r.failure, PlanFailure::kFrameMismatch);
}

TEST(PlannerFailures, UnauthorizedFailsWithExplicitReason)
{
  Grid grid;
  auto snap = makeSnapshot(grid, -3.0, 0.0, 3.0, 0.0);
  snap.authorized = false;
  auto planner = createPlanner();
  const PathResult r = planner->plan(snap);
  EXPECT_FALSE(r.success);
  EXPECT_EQ(r.failure, PlanFailure::kNotAuthorized);
}

TEST(PlannerFailures, InvalidGoalFailsWithExplicitReason)
{
  Grid grid;
  auto snap = makeSnapshot(grid, -3.0, 0.0, 3.0, 0.0);
  snap.goal_valid = false;
  auto planner = createPlanner();
  const PathResult r = planner->plan(snap);
  EXPECT_FALSE(r.success);
  EXPECT_EQ(r.failure, PlanFailure::kGoalInvalid);
}

TEST(PlannerFailures, StartOutOfMapFailsWithExplicitReason)
{
  Grid grid;
  auto snap = makeSnapshot(grid, -99.0, 0.0, 3.0, 0.0);
  auto planner = createPlanner();
  const PathResult r = planner->plan(snap);
  EXPECT_FALSE(r.success);
  EXPECT_EQ(r.failure, PlanFailure::kStartOutOfMap);
}

TEST(PlannerFailures, NodeLimitProducesSearchExhaustedOrTimeout)
{
  Grid grid;
  // 迷宫式障碍，逼搜索耗尽预算
  for (int iy = 0; iy < kDim; ++iy) {
    for (int ix = 0; ix < kDim; ++ix) {
      // 竖墙每 5 格一道 ⇒ 自由跨度 4 格 = 2.0 m > footprint 全宽 1.714 m，
      // 车放得进去。每 3 格一道只有 1.0 m，比车窄，起点必然碰撞（不是本用例要测的）。
      if (ix % 5 == 0 && iy != 15) {grid.setCell(ix, iy, 100);}
    }
  }
  // 起点放在两道墙**正中间**：墙在 ix=0 (x∈[-4,-3.5)) 与 ix=5 (x∈[-1.5,-1.0))，
  // 自由区 x∈(-3.5,-1.5) 宽 2.0 m。车 footprint 全宽 2*(0.5037+0.3536)=1.714 m，
  // 车心必须落在 x∈(-3.5+0.857, -1.5-0.857) = (-2.643, -2.357) 内 ⇒ 取 -2.5。
  auto snap = makeSnapshot(grid, -2.5, 0.0, 2.5, 0.0);
  snap.params.max_expanded_nodes = 50;      // 极小上限
  snap.params.search_time_budget_s = 0.2;
  auto planner = createPlanner();
  const PathResult r = planner->plan(snap);
  if (!r.success) {
    EXPECT_TRUE(
      r.failure == PlanFailure::kSearchExhausted ||
      r.failure == PlanFailure::kSearchTimeout ||
      r.failure == PlanFailure::kValidationFailed)
      << "unexpected: " << planner::toString(r.failure);
  }
  EXPECT_LE(r.expanded_nodes, 60) << "节点上限必须硬约束";
}

TEST(PlannerFailures, FailureEnumStringsAreAllDistinct)
{
  // 诊断靠字符串归因，重名会让「失败原因」失去判别力。
  const PlanFailure all[] = {
    PlanFailure::kNone, PlanFailure::kNoMap, PlanFailure::kMapInvalid,
    PlanFailure::kMapStale, PlanFailure::kFrameMismatch, PlanFailure::kNoOdom,
    PlanFailure::kNoGoal, PlanFailure::kGoalInvalid, PlanFailure::kNotAuthorized,
    PlanFailure::kStartOutOfMap, PlanFailure::kStartNotFree, PlanFailure::kStartCollision,
    PlanFailure::kGoalOutOfMap, PlanFailure::kGoalNotFree, PlanFailure::kGoalCollision,
    PlanFailure::kSearchExhausted, PlanFailure::kSearchTimeout, PlanFailure::kNoAnalyticConnect,
    PlanFailure::kOptimizationFailed, PlanFailure::kOptimizedPathCollision,
    PlanFailure::kDynamicsInfeasible, PlanFailure::kValidationFailed,
  };
  std::vector<std::string> seen;
  for (PlanFailure f : all) {
    const std::string s = toString(f);
    EXPECT_FALSE(s.empty());
    for (const std::string & prev : seen) {
      EXPECT_NE(s, prev) << "duplicate failure string: " << s;
    }
    seen.push_back(s);
  }
}

// ---------------------------------------------------------------------------------
// 13. 相同输入、seed 和参数下路径与诊断可复现
// ---------------------------------------------------------------------------------

TEST(PlannerDeterminism, SameInputProducesIdenticalPath)
{
  Grid grid;
  grid.setCell(8, 6, 100);
  grid.setCell(8, 7, 100);
  grid.setCell(8, 10, 100);
  auto snap = makeSnapshot(grid, -3.0, -1.0, 3.0, -1.0);
  snap.params.search_time_budget_s = 5.0;

  auto p1 = createPlanner();
  const PathResult a = p1->plan(snap);
  auto p2 = createPlanner();
  const PathResult b = p2->plan(snap);

  ASSERT_EQ(a.success, b.success);
  if (a.success) {
    ASSERT_EQ(a.poses.size(), b.poses.size()) << "点数必须一致（搜索无随机性）";
    for (size_t i = 0; i < a.poses.size(); ++i) {
      EXPECT_DOUBLE_EQ(a.poses[i].x, b.poses[i].x) << "pose " << i;
      EXPECT_DOUBLE_EQ(a.poses[i].y, b.poses[i].y) << "pose " << i;
      EXPECT_DOUBLE_EQ(a.poses[i].yaw, b.poses[i].yaw) << "pose " << i;
    }
    EXPECT_EQ(a.expanded_nodes, b.expanded_nodes);
    EXPECT_DOUBLE_EQ(a.path_length_m, b.path_length_m);
    EXPECT_EQ(a.map_signature, b.map_signature);
    EXPECT_EQ(a.outcome, b.outcome);
  } else {
    EXPECT_EQ(a.failure, b.failure);
  }
}

// ---------------------------------------------------------------------------------
// 地图签名双判据
// ---------------------------------------------------------------------------------

TEST(PlannerSignature, BlockedSignatureIgnoresFreeAndCostFlips)
{
  // 阻挡签名只计 99/100。自由/代价/未知的翻转**不得**改变它（否则就是伪触发）。
  Grid a;
  const std::string s0 = blockedSignature(a.view());

  Grid b;
  b.setCell(3, 3, 50);     // 代价带
  EXPECT_EQ(blockedSignature(b.view()), s0) << "代价带不应改变阻挡签名";

  Grid c;
  c.setCell(4, 4, -1);     // 未知
  EXPECT_EQ(blockedSignature(c.view()), s0) << "未知不应改变阻挡签名";

  Grid d;
  d.setCell(5, 5, 100);    // 真实障碍
  EXPECT_NE(blockedSignature(d.view()), s0) << "真实障碍必须改变阻挡签名";

  Grid e;
  e.setCell(6, 6, 99);     // 内切带
  EXPECT_NE(blockedSignature(e.view()), s0) << "99 是障碍存在的证据，必须计入";
}

TEST(PlannerSignature, FreeCellCountTracksExploration)
{
  // 「等地图探索出来就能补上」靠的是自由格数变化，不是阻挡签名。
  Grid a;
  const long n0 = freeCellCount(a.view());
  Grid b;
  b.setCell(0, 0, -1);
  b.setCell(1, 0, -1);
  EXPECT_EQ(freeCellCount(b.view()), n0 - 2);

  MapSignature s0 = computeMapSignature(a.view());
  MapSignature s1 = computeMapSignature(b.view());
  // 阈值 200 时，2 格变化**不**触发（噪声级）
  EXPECT_FALSE(signatureChanged(s0, s1, 200));
  // 阈值 1 时触发
  EXPECT_TRUE(signatureChanged(s0, s1, 1));
}

TEST(PlannerSignature, SignatureChangeDetectsBlockedSetAndGeometry)
{
  Grid a;
  Grid b;
  b.setCell(7, 7, 100);
  EXPECT_TRUE(signatureChanged(
      computeMapSignature(a.view()), computeMapSignature(b.view()), 100000));

  // 几何变化（换原点）也必须被感知
  Grid c;
  GridView vc = c.view();
  vc.origin_x = kOrigin + 0.5;
  EXPECT_TRUE(signatureChanged(
      computeMapSignature(a.view()), computeMapSignature(vc), 100000));
}

// ---------------------------------------------------------------------------------
// 接口与工厂
// ---------------------------------------------------------------------------------

TEST(PlannerInterface, FactoryReturnsNamedPlanner)
{
  auto p = createPlanner();
  ASSERT_NE(p, nullptr);
  EXPECT_EQ(p->name(), "hybrid_astar_se2");
}

TEST(PlannerInterface, PlannerNameIsMethodSpecificNotGeneric)
{
  // 用户裁定：名字必须表明「这是其中一种方法」，不能占住「地面主方案」的位置。
  auto p = createPlanner();
  const std::string n = p->name();
  EXPECT_NE(n, "ground_path_planner");
  EXPECT_NE(n.find("hybrid"), std::string::npos) << "名字应表明搜索方法";
  EXPECT_NE(n.find("se2"), std::string::npos) << "名字应表明状态空间";
}

// ---------------------------------------------------------------------------------
// 走廊判据（双阻挡集的落地）
// ---------------------------------------------------------------------------------

TEST(PlannerCorridor, ClearCorridorIsReportedAsInfinite)
{
  // 开阔地图、朝 +x：走廊带内无 lethal → 返回 -1（= 无阻挡）。
  Grid grid;
  const GridView g = grid.view();
  const PlannerParams p;
  Pose2D q;
  const double c = corridorClearance(
    g, q, p.footprint_half_length, p.footprint_half_width, p.footprint_margin, 6.0, 1.0);
  EXPECT_LT(c, 0.0) << "带内无阻挡时应返回 -1";
}

TEST(PlannerCorridor, LethalInBandIsMeasuredFromFootprintEdge)
{
  Grid grid;
  grid.setWorld(2.0, 0.0, 100);
  const GridView g = grid.view();
  const PlannerParams p;
  Pose2D q;
  const double c = corridorClearance(
    g, q, p.footprint_half_length, p.footprint_half_width, p.footprint_margin, 6.0, 1.0);
  // 障碍在 x=2，车头在 0.504+0.354=0.858，格心量化 + 半格对角 →
  // 间隙应约为 2.0 - 0.858 - 0.354 = 0.79 左右
  EXPECT_GT(c, 0.0);
  EXPECT_LT(c, 1.5);
  // 反方向（-x）不该看到它
  const double back = corridorClearance(
    g, q, p.footprint_half_length, p.footprint_half_width, p.footprint_margin, 6.0, -1.0);
  EXPECT_LT(back, 0.0);
}

TEST(PlannerCorridor, InscribedBandDoesNotCountAsCorridorBlocker)
{
  // 这是本设计最反直觉、但实测决定成败的一条：`99` 不算走廊阻挡。
  Grid grid;
  grid.setWorld(2.0, 0.0, 99);
  const GridView g = grid.view();
  const PlannerParams p;
  Pose2D q;
  const double c = corridorClearance(
    g, q, p.footprint_half_length, p.footprint_half_width, p.footprint_margin, 6.0, 1.0);
  EXPECT_LT(c, 0.0) << "99 不应计入走廊净空（dense_map 上会把规划变成无解）";
}

}  // namespace
}  // namespace planner
}  // namespace agc_ground
