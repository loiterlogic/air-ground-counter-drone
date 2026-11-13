// 障碍实例层（几何模型 + 生命周期）的纯逻辑测试（不启 ROS / 不启仿真）。
//
// 守护的核心行为（dense_map 小障碍的"实例归属"问题）：
//   * 单帧毛刺不得变成确认实例（与格层的"至少两帧"同一纪律）；
//   * 实例被连续漏检到阈值才死，一次漏检不得撤销确认；
//   * "重新发现"是**上升沿事件**，不是状态本身；
//   * 已死亡实例不得抢走新观测（id 不复用到已不在原处的目标上）。
#include <cmath>
#include <vector>

#include <gtest/gtest.h>

#include "agc_perception/obstacle_instances.hpp"

using agc_perception::classifyShape;
using agc_perception::InstanceObservation;
using agc_perception::InstanceParams;
using agc_perception::InstanceShape;
using agc_perception::InstanceTracker;
using agc_perception::ObstacleInstance;

namespace
{

InstanceObservation obs(double x, double y, double r = 0.3)
{
  InstanceObservation o;
  o.cx = x;
  o.cy = y;
  o.radius_m = r;
  o.half_x_m = r;
  o.half_y_m = r;
  o.radius_sigma_m = 0.05;
  o.support_points = 100;
  o.shape = InstanceShape::kCircle;
  return o;
}

}  // namespace

// ------------------------------------------------------------------ 形状判定

// 两轴接近 ⇒ 圆（不硬报 box）。矩形栅格化是朝向敏感的，强行按 box 处理会让
// 同一障碍的覆盖格数随 yaw 抖动 —— 那正是要修的抖动。
TEST(Instances, RoundShapeIsClassifiedAsCircle)
{
  InstanceParams p;
  EXPECT_EQ(classifyShape(0.30, 0.30, p), InstanceShape::kCircle);
  EXPECT_EQ(classifyShape(0.30, 0.28, p), InstanceShape::kCircle) << "差 7% 应仍是圆";
}

// 明显长方 ⇒ box。
TEST(Instances, ElongatedShapeIsClassifiedAsBox)
{
  InstanceParams p;
  EXPECT_EQ(classifyShape(0.60, 0.30, p), InstanceShape::kBox);
  EXPECT_EQ(classifyShape(0.60, 0.05, p), InstanceShape::kBox);
}

// 零尺度 ⇒ kUnknown（不猜）。
TEST(Instances, ZeroExtentIsUnknown)
{
  InstanceParams p;
  EXPECT_EQ(classifyShape(0.0, 0.0, p), InstanceShape::kUnknown);
}

// box 的保守外接半径是对角半径（与朝向无关、方向安全）。
TEST(Instances, BoxBoundingRadiusIsDiagonal)
{
  ObstacleInstance inst;
  inst.shape = InstanceShape::kBox;
  inst.half_x_m = 0.6;
  inst.half_y_m = 0.3;
  EXPECT_NEAR(inst.boundingRadius(), std::hypot(0.6, 0.3), 1e-12);
  // 圆就用半径本身
  inst.shape = InstanceShape::kCircle;
  inst.radius_m = 0.4;
  EXPECT_DOUBLE_EQ(inst.boundingRadius(), 0.4);
}

// ------------------------------------------------------------------ 生命周期

// **核心判据**：单帧观测不得确认实例（与格层 min_hits_for_occupied=2 同一纪律）。
TEST(Instances, SingleObservationDoesNotConfirm)
{
  InstanceTracker t;
  t.beginFrame();
  t.spawn(obs(1.0, 2.0));
  EXPECT_EQ(t.confirmedCount(), 0u) << "单帧就确认等于让毛刺进地图";
  EXPECT_EQ(t.instances().size(), 1u);
  EXPECT_TRUE(t.instances()[0].alive);
  EXPECT_FALSE(t.instances()[0].confirmed);
}

// 跨两帧观测同一位置 ⇒ 确认。
TEST(Instances, TwoObservationsConfirm)
{
  InstanceTracker t;
  t.beginFrame();
  t.spawn(obs(1.0, 2.0));
  t.beginFrame();
  const int idx = t.associate(1.05, 2.02);
  ASSERT_GE(idx, 0);
  t.absorb(idx, obs(1.05, 2.02));
  EXPECT_EQ(t.confirmedCount(), 1u);
  EXPECT_TRUE(t.instances()[0].confirmed);
}

// 一次漏检**不得**撤销确认（迟滞）。
TEST(Instances, OneMissDoesNotRevokeConfirmation)
{
  InstanceParams p;
  p.expire_misses = 3;
  InstanceTracker t(p);
  t.beginFrame();
  t.spawn(obs(0.0, 0.0));
  t.beginFrame();
  t.absorb(t.associate(0.0, 0.0), obs(0.0, 0.0));
  ASSERT_TRUE(t.instances()[0].confirmed);
  // 一次漏检
  t.beginFrame();
  t.miss(0);
  EXPECT_TRUE(t.instances()[0].alive) << "一次漏检不该判死";
  EXPECT_TRUE(t.instances()[0].confirmed) << "一次漏检不该撤销确认（迟滞）";
}

// 连续漏检到阈值 ⇒ 死亡，且被回收。
TEST(Instances, ConsecutiveMissesKillAndExpire)
{
  InstanceParams p;
  p.expire_misses = 3;
  InstanceTracker t(p);
  t.beginFrame();
  t.spawn(obs(0.0, 0.0));
  t.beginFrame();
  t.absorb(t.associate(0.0, 0.0), obs(0.0, 0.0));
  for (int k = 0; k < 3; ++k) {
    t.beginFrame();
    t.miss(0);
  }
  EXPECT_FALSE(t.instances()[0].alive);
  const size_t removed = t.expire();
  EXPECT_EQ(removed, 1u);
  EXPECT_EQ(t.instances().size(), 0u);
}

// **上升沿才是事件**：confirmed 一旦为真，第二拍 justConfirmed() 必须为假。
// 若把 prev_* 在 absorb 里就地覆盖，这条会红（同一实例一拍内更新两次会丢边沿）。
TEST(Instances, JustConfirmedIsAnEdgeNotAState)
{
  InstanceTracker t;
  t.beginFrame();
  t.spawn(obs(0.0, 0.0));
  EXPECT_FALSE(t.instances()[0].justConfirmed()) << "首拍未确认";
  t.beginFrame();
  t.absorb(t.associate(0.0, 0.0), obs(0.0, 0.0));
  EXPECT_TRUE(t.instances()[0].justConfirmed()) << "确认发生在这一拍 ⇒ 上升沿";
  t.beginFrame();
  t.absorb(t.associate(0.0, 0.0), obs(0.0, 0.0));
  EXPECT_TRUE(t.instances()[0].confirmed);
  EXPECT_FALSE(t.instances()[0].justConfirmed()) << "已确认状态不是事件，不得重复上报";
}

// 死亡后重新出现 ⇒ revived() 上升沿为真（这是"重新发现"，要能区分于持续存在）。
TEST(Instances, RevivalIsDetectedAsRisingEdge)
{
  InstanceParams p;
  p.expire_misses = 2;
  InstanceTracker t(p);
  t.beginFrame();
  t.spawn(obs(0.0, 0.0));
  t.beginFrame();
  t.absorb(t.associate(0.0, 0.0), obs(0.0, 0.0));
  // 让它死掉，但**先不回收**（回收了就查不到 prev_alive 了）
  for (int k = 0; k < 2; ++k) {
    t.beginFrame();
    t.miss(0);
  }
  ASSERT_FALSE(t.instances()[0].alive);
  EXPECT_TRUE(t.instances()[0].justDied()) << "刚死那一拍是下降沿";
  // 重新观测到同一位置：已死实例不参与关联 ⇒ 新建一个实例。
  t.beginFrame();
  const int idx = t.associate(0.02, 0.0);
  EXPECT_EQ(idx, -1) << "已死亡实例不得抢走新观测（否则 id 复活到别处）";
  const int new_id = t.spawn(obs(0.02, 0.0));
  EXPECT_GE(new_id, 0);
  EXPECT_NE(new_id, 0) << "id 单调递增、不复用";
}

// 关联门：超出门的观测必须新建实例，不得被并入既有障碍。
// dense_map 最小障碍间距 2.3 m，门取 1.5 m 不会把相邻障碍并成一个。
TEST(Instances, AssociationGateKeepsNeighbouringObstaclesSeparate)
{
  InstanceParams p;
  p.associate_gate_m = 1.5;
  InstanceTracker t(p);
  t.beginFrame();
  t.spawn(obs(0.0, 0.0));
  // 2.3 m 外的另一个障碍（dense_map 的最小间距）
  EXPECT_EQ(t.associate(2.3, 0.0), -1) << "超出关联门 ⇒ 必须新建";
  // 门内
  EXPECT_GE(t.associate(1.4, 0.0), 0);
}

// 几何用指数滑动（不是直接覆盖）：单帧跳变不得把实例位置整体带走。
TEST(Instances, GeometryIsSmoothedNotOverwritten)
{
  InstanceTracker t;
  t.beginFrame();
  t.spawn(obs(0.0, 0.0));
  t.beginFrame();
  // 单帧质心跳到 1.0 m（拟合受可见像素集合影响，实测可达此量级）
  t.absorb(t.associate(0.9, 0.0), obs(1.0, 0.0));
  const double cx = t.instances()[0].cx;
  EXPECT_GT(cx, 0.0) << "必须跟随观测";
  EXPECT_LT(cx, 1.0) << "但不得 1:1 传导单帧跳变（直接覆盖会得到 1.0）";
  EXPECT_NEAR(cx, 0.5, 1e-9) << "alpha=0.5 ⇒ 两帧等效";
}

// 朝向插值必须走最短角差：179° → −179° 的中点是 180°，不是 0°。
TEST(Instances, YawInterpolationTakesShortestArc)
{
  InstanceTracker t;
  InstanceObservation a = obs(0.0, 0.0);
  a.yaw = 179.0 * M_PI / 180.0;
  InstanceObservation b = obs(0.0, 0.0);
  b.yaw = -179.0 * M_PI / 180.0;

  t.beginFrame();
  t.spawn(a);
  t.beginFrame();
  t.absorb(t.associate(0.0, 0.0), b);
  const double yaw = t.instances()[0].yaw;
  // 结果应接近 ±180°（即 π），而不是 0
  const double abs_yaw = std::fabs(yaw);
  EXPECT_GT(abs_yaw, M_PI - 0.05) << "最短角差插值应落在 180° 附近，实测 " << yaw;
}

// 置信度随观测次数单调升、封顶 1，且不越界。
TEST(Instances, ConfidenceRisesWithObservationsAndSaturates)
{
  InstanceTracker t;
  t.beginFrame();
  t.spawn(obs(0.0, 0.0));
  const double c1 = t.instances()[0].confidence;
  double prev = c1;
  for (int k = 0; k < 40; ++k) {
    t.beginFrame();
    t.absorb(t.associate(0.0, 0.0), obs(0.0, 0.0));
    const double c = t.instances()[0].confidence;
    EXPECT_GE(c, prev) << "必须单调不减";
    EXPECT_LE(c, 1.0) << "不得越界";
    prev = c;
  }
  EXPECT_GT(prev, c1) << "多次观测后应更高";
  EXPECT_NEAR(prev, 1.0, 1e-3) << "应封顶到 1";
}

// 空 tracker 上的操作必须安全（不崩、不产生实例）。
TEST(Instances, EmptyTrackerIsSafe)
{
  InstanceTracker t;
  t.beginFrame();
  EXPECT_EQ(t.associate(0.0, 0.0), -1);
  t.absorb(-1, obs(0.0, 0.0));
  t.absorb(99, obs(0.0, 0.0));
  t.miss(-1);
  t.miss(99);
  EXPECT_EQ(t.expire(), 0u);
  EXPECT_EQ(t.confirmedCount(), 0u);
  EXPECT_TRUE(t.instances().empty());
}

// ==================================================================== 点集拟合（ADR-0041）

namespace
{
// 造一个半径 r 的圆形点云（n 个点均匀分布）
void ring(double cx, double cy, double r, int n, double z,
  std::vector<double> & xs, std::vector<double> & ys, std::vector<double> & zs)
{
  for (int i = 0; i < n; ++i) {
    const double a = 2.0 * M_PI * i / n;
    xs.push_back(cx + r * std::cos(a));
    ys.push_back(cy + r * std::sin(a));
    zs.push_back(z);
  }
}
}  // namespace

// 圆形点云拟合：中心与半径必须还原（这是"实例几何"的基本正确性）。
TEST(InstanceFit, RecoversCircleCentreAndRadius)
{
  std::vector<double> xs, ys, zs;
  ring(3.0, -2.0, 0.35, 64, 1.2, xs, ys, zs);
  agc_perception::InstanceObservation obs;
  ASSERT_TRUE(agc_perception::fitInstanceObservation(
      xs, ys, zs, agc_perception::InstanceFitParams{}, obs));
  EXPECT_NEAR(obs.cx, 3.0, 1e-9);
  EXPECT_NEAR(obs.cy, -2.0, 1e-9);
  EXPECT_NEAR(obs.radius_m, 0.35, 0.01);
  EXPECT_NEAR(obs.z_min, 1.2, 1e-9);
  EXPECT_NEAR(obs.z_max, 1.2, 1e-9);
  EXPECT_EQ(obs.support_points, 64);
  // 圆 → kCircle
  EXPECT_EQ(obs.shape, InstanceShape::kCircle);
}

// **半径用 90% 分位，不是最大值**：单个离群点不得把半径撑大。
// 这条区分"保守"与"脆弱"：最大半径对 1 个错位点就失效，而错位点正是本仓的主要噪声。
TEST(InstanceFit, RadiusIgnoresSingleOutlier)
{
  std::vector<double> xs, ys, zs;
  ring(0.0, 0.0, 0.30, 100, 0.0, xs, ys, zs);
  const double clean_radius = [&] {
      agc_perception::InstanceObservation o;
      agc_perception::fitInstanceObservation(
        xs, ys, zs, agc_perception::InstanceFitParams{}, o);
      return o.radius_m;
    }();
  // 加一个 5 m 外的离群点（单个错位投影）
  xs.push_back(5.0);
  ys.push_back(0.0);
  zs.push_back(0.0);
  agc_perception::InstanceObservation o;
  ASSERT_TRUE(agc_perception::fitInstanceObservation(
      xs, ys, zs, agc_perception::InstanceFitParams{}, o));
  EXPECT_LT(o.radius_m, clean_radius * 1.5)
    << "单个离群点不得把半径撑到 5 m（90% 分位应当忽略它）";
  EXPECT_GT(o.radius_m, clean_radius * 0.8) << "但也不得把真实半径算小";
}

// 长方形点云 → kBox，且半长能区分长短边。
TEST(InstanceFit, RecoversBoxExtentsAndShape)
{
  std::vector<double> xs, ys, zs;
  // 沿 x 半长 0.6、沿 y 半长 0.15 的矩形（明显长条）
  for (int i = 0; i < 20; ++i) {
    const double t = -1.0 + 2.0 * i / 19.0;
    xs.push_back(0.6 * t); ys.push_back(0.15); zs.push_back(0.5);
    xs.push_back(0.6 * t); ys.push_back(-0.15); zs.push_back(0.5);
  }
  agc_perception::InstanceObservation o;
  ASSERT_TRUE(agc_perception::fitInstanceObservation(
      xs, ys, zs, agc_perception::InstanceFitParams{}, o));
  EXPECT_EQ(o.shape, InstanceShape::kBox) << "0.6 x 0.15 是明显长条，不得判成圆";
  const double hx = std::max(o.half_x_m, o.half_y_m);
  const double hy = std::min(o.half_x_m, o.half_y_m);
  EXPECT_NEAR(hx, 0.6, 0.02);
  EXPECT_NEAR(hy, 0.15, 0.02);
}

// 点数不足 ⇒ 返回 false（不硬拟合）。
// 少于 3 个点连方向都定不了，拟合出来的形状是噪声，比不拟合更糟。
TEST(InstanceFit, RejectsTooFewPoints)
{
  std::vector<double> xs{0.0, 1.0}, ys{0.0, 0.0}, zs{0.0, 0.0};
  agc_perception::InstanceObservation o;
  EXPECT_FALSE(agc_perception::fitInstanceObservation(
      xs, ys, zs, agc_perception::InstanceFitParams{}, o));
}

// 位置不确定度用**质心标准误**（σ/√n），不是点的散布。
// 用散布当 σ 会把"大障碍"误判成"中心不确定" —— 两者是不同的事。
TEST(InstanceFit, SigmaIsStandardErrorOfCentreNotPointSpread)
{
  std::vector<double> xs, ys, zs;
  ring(0.0, 0.0, 1.0, 400, 0.0, xs, ys, zs);   // 半径 1 m 的大圆
  agc_perception::InstanceObservation o;
  ASSERT_TRUE(agc_perception::fitInstanceObservation(
      xs, ys, zs, agc_perception::InstanceFitParams{}, o));
  EXPECT_LT(o.radius_sigma_m, 0.1)
    << "半径 1 m 的圆有 400 个点时，中心应当很准（σ/√n 很小）；"
    << "若用点散布当 σ 会得到 ~1.0";
}

// 点数越多，中心不确定度越小（1/√n 关系）。
TEST(InstanceFit, SigmaShrinksWithMorePoints)
{
  std::vector<double> xs1, ys1, zs1, xs2, ys2, zs2;
  ring(0.0, 0.0, 0.5, 20, 0.0, xs1, ys1, zs1);
  ring(0.0, 0.0, 0.5, 200, 0.0, xs2, ys2, zs2);
  agc_perception::InstanceObservation a, b;
  ASSERT_TRUE(agc_perception::fitInstanceObservation(
      xs1, ys1, zs1, agc_perception::InstanceFitParams{}, a));
  ASSERT_TRUE(agc_perception::fitInstanceObservation(
      xs2, ys2, zs2, agc_perception::InstanceFitParams{}, b));
  EXPECT_LT(b.radius_sigma_m, a.radius_sigma_m);
}

// ---------------------------------------------------------------------------
// 实例轨迹历史（ADR-0042）
// ---------------------------------------------------------------------------

namespace
{
agc_perception::InstanceObservation at(double x, double y)
{
  agc_perception::InstanceObservation o;
  o.cx = x;
  o.cy = y;
  o.radius_m = 0.3;
  o.half_x_m = 0.3;
  o.half_y_m = 0.3;
  o.z_min = 0.0;
  o.z_max = 1.0;
  o.support_points = 10;
  o.shape = agc_perception::InstanceShape::kCircle;
  return o;
}
}  // namespace

TEST(InstanceTrack, RecordsOnePointPerFrame)
{
  agc_perception::InstanceParams p;
  p.max_track_points = 10;
  agc_perception::InstanceTracker tr(p);
  tr.setClock(100.0);
  tr.beginFrame();
  tr.spawn(at(0.0, 0.0));
  ASSERT_EQ(tr.instances().size(), 1u);
  EXPECT_EQ(tr.instances()[0].track.size(), 1u);
  EXPECT_DOUBLE_EQ(tr.instances()[0].track[0].stamp_s, 100.0);
}

TEST(InstanceTrack, HistoryIsBoundedAndDropsOldest)
{
  // 有界 + 丢头部（照 RACER `ObjHistory` 的 pop_front 纪律）。
  // 若实现成丢尾部，留下的会是"最早的 5 个点" —— 历史就再也不会更新，
  // 而症状是"位移总量一直不涨"，极难归因。
  agc_perception::InstanceParams p;
  p.max_track_points = 5;
  p.expire_misses = 100;
  agc_perception::InstanceTracker tr(p);
  for (int i = 0; i < 20; ++i) {
    tr.setClock(100.0 + i);
    tr.beginFrame();
    if (tr.instances().empty()) {
      tr.spawn(at(0.0, 0.0));
    } else {
      // 每拍只挪 0.1 m：滑动平均的稳态滞后 = v(1−α)/α = 0.1 m，
      // 远小于关联门 1.5 m。若每拍挪 1 m，滞后就是 1 m，加上门限余量会断关联
      // —— 那是**关联门**的性质，不是轨迹历史的性质，不该混进本用例。
      const double x = 0.1 * static_cast<double>(i);
      const int idx = tr.associate(x, 0.0);
      ASSERT_GE(idx, 0) << "第 " << i << " 拍断关联（x=" << x << "）";
      tr.absorb(idx, at(x, 0.0));
    }
  }
  ASSERT_EQ(tr.instances().size(), 1u);
  const auto & inst = tr.instances()[0];
  EXPECT_EQ(inst.track.size(), 5u) << "历史必须有界";
  // **最新**的点必须在末尾：时间戳单调递增且等于最后一拍
  EXPECT_DOUBLE_EQ(inst.track.back().stamp_s, 119.0)
    << "必须保留最近的，不是最早的";
  EXPECT_DOUBLE_EQ(inst.track.front().stamp_s, 115.0);
  for (size_t i = 1; i < inst.track.size(); ++i) {
    EXPECT_GE(inst.track[i].stamp_s, inst.track[i - 1].stamp_s) << "时间戳必须单调";
  }
}

TEST(InstanceTrack, PathLengthAccumulatesNotEndToEnd)
{
  // 来回抖动：0 → 0.2 → 0 → 0.2 → 0。
  // **这条是"为什么不用首尾距离"的直接判据**：首尾都是 0，首尾距离 = 0，
  // 而实际走过 4 段。若实现用首尾距离，会得到 0 而不是 ~0.75。
  //
  // **注意历史存的是"实例的稳定位置"（滑动平均后），不是原始观测**：
  // 实例层的存在意义就是稳定，把原始抖动原样记进历史等于放弃这一层。
  // 因此位移量是**下界**（平滑会吃掉一部分单拍抖动），这与
  // `trackPathLength` 的用途（"实例模型动了多少"）一致，不是缺陷。
  agc_perception::InstanceParams p;
  p.max_track_points = 100;
  p.expire_misses = 100;
  agc_perception::InstanceTracker tr(p);
  const double xs[] = {0.0, 0.2, 0.0, 0.2, 0.0};
  for (int i = 0; i < 5; ++i) {
    tr.setClock(100.0 + i);
    tr.beginFrame();
    if (tr.instances().empty()) {
      tr.spawn(at(xs[i], 0.0));
    } else {
      tr.absorb(0, at(xs[i], 0.0));
    }
  }
  ASSERT_EQ(tr.instances().size(), 1u);
  const auto & inst = tr.instances()[0];
  // 首尾距离远小于逐段累加 —— 这是"来回抖动"的定义性差别。
  const double end_to_end = std::hypot(
    inst.track.back().x - inst.track.front().x,
    inst.track.back().y - inst.track.front().y);
  EXPECT_GT(inst.trackPathLength(), 3.0 * end_to_end)
    << "逐段累加(" << inst.trackPathLength() << ") 必须远大于首尾距离("
    << end_to_end << ")；若两者相等，说明实现只算了首尾";
  EXPECT_GT(inst.trackPathLength(), 0.2) << "必须有非零位移";
  EXPECT_NEAR(inst.trackSpanSeconds(), 4.0, 1e-9);
}

TEST(InstanceTrack, ZeroMaxPointsDisablesHistory)
{
  // 0 = 关闭（退回"只存当前几何"的旧行为）。守的是"新功能必须能关"：
  // 关不掉的新增行为在内存/带宽受限时会变成无解的死负担。
  agc_perception::InstanceParams p;
  p.max_track_points = 0;
  agc_perception::InstanceTracker tr(p);
  tr.setClock(100.0);
  tr.beginFrame();
  tr.spawn(at(0.0, 0.0));
  ASSERT_EQ(tr.instances().size(), 1u);
  EXPECT_TRUE(tr.instances()[0].track.empty());
  EXPECT_DOUBLE_EQ(tr.instances()[0].trackPathLength(), 0.0);
  EXPECT_DOUBLE_EQ(tr.instances()[0].trackSpanSeconds(), 0.0);
}

TEST(InstanceTrack, NoClockMeansNoHistory)
{
  // 未注入时钟 ⇒ 不记录。守的是"没有时刻的历史不该被凭空造出来"：
  // 那些点无法算跨度、也无法判断是否同一拍，写进去只会污染位移总量。
  agc_perception::InstanceParams p;
  p.max_track_points = 10;
  agc_perception::InstanceTracker tr(p);
  tr.beginFrame();          // 没有 setClock
  tr.spawn(at(0.0, 0.0));
  ASSERT_EQ(tr.instances().size(), 1u);
  EXPECT_TRUE(tr.instances()[0].track.empty()) << "无时钟不得记录历史";
}

TEST(InstanceTrack, MinIntervalSuppressesSameFrameDuplicates)
{
  // 同一拍内多次 absorb（多个观测落到同一实例）不得重复记点 ——
  // 否则"位移总量"会把同一拍的抖动重复计入。
  agc_perception::InstanceParams p;
  p.max_track_points = 100;
  p.min_track_interval_s = 0.05;
  p.expire_misses = 100;
  agc_perception::InstanceTracker tr(p);
  tr.setClock(100.0);
  tr.beginFrame();
  tr.spawn(at(0.0, 0.0));
  tr.absorb(0, at(0.1, 0.0));      // 同一时刻，间隔 0 < 0.05 ⇒ 不记
  tr.absorb(0, at(0.2, 0.0));      // 同上
  EXPECT_EQ(tr.instances()[0].track.size(), 1u) << "同一拍只记一个点";
  // 时间推进足够后应当记录
  tr.setClock(100.1);
  tr.beginFrame();
  tr.absorb(0, at(0.3, 0.0));
  EXPECT_EQ(tr.instances()[0].track.size(), 2u);
}

TEST(InstanceTrack, HistoryDoesNotAffectCurrentGeometry)
{
  // **关键纪律**：历史绝不参与栅格化。栅格化读的是当前几何，
  // 若历史被混进 `cx/cy`，那就等于"它曾经在哪"决定"现在哪格被占"。
  // 判据：走过一条弯路径后，当前中心必须等于最后一拍的观测（经滑动平均），
  // 与历史里的任何早期点都不同。
  agc_perception::InstanceParams p;
  p.max_track_points = 100;
  p.expire_misses = 100;
  agc_perception::InstanceTracker tr(p);
  for (int i = 0; i < 10; ++i) {
    tr.setClock(100.0 + i);
    tr.beginFrame();
    const double x = 5.0 + static_cast<double>(i);
    if (tr.instances().empty()) {
      tr.spawn(at(x, 0.0));
    } else {
      tr.absorb(0, at(x, 0.0));
    }
  }
  ASSERT_EQ(tr.instances().size(), 1u);
  const auto & inst = tr.instances()[0];
  // 中心必须靠近最后的观测（14.0），而不是历史均值或起点
  EXPECT_GT(inst.cx, 13.0) << "当前中心必须跟随最新观测";
  EXPECT_LT(inst.cx, 14.1);
  // 且历史里确实有更早的位置（证明历史存在但没污染几何）
  EXPECT_LT(inst.track.front().x, 6.0);
  EXPECT_NEAR(inst.track.back().x, inst.cx, 1e-9) << "最后一点应等于当前中心";
}
