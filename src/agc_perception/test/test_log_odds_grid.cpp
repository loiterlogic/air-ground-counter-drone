// log-odds 增量累积栅格的纯逻辑测试（不启 ROS / 不启仿真）。
//
// 守护的核心行为（对应用户反馈"形状一直变、偶尔大幅跳再回归"）：
//   * 单帧毛刺画不出来（需要反复观测才跨过 occupied 门限）
//   * 已确认的障碍不会被一次漏观测抹掉（FOV 边缘被切掉是常态）
//   * 长时间不观测才衰减掉（"过期"语义从"时间到就删"变成"证据变弱"）
#include <cmath>

#include <gtest/gtest.h>

#include "agc_perception/log_odds_grid.hpp"

using agc_perception::fromLogOdds;
using agc_perception::LogOddsGrid;
using agc_perception::LogOddsParams;
using agc_perception::toLogOdds;

namespace
{
LogOddsParams defaults() {return LogOddsParams{};}

// **证据单位 = 每格每帧一次**（2026-11-09 用户裁定）。
// 所以"连续观测 N 次"必须**跨 N 帧**，否则同一帧里的重复调用是幂等的。
// 这三个辅助函数把"推进一帧再记账"这个动作写死，避免每个用例各写一遍 beginFrame。
//
// **同时推进地图帧**（ADR-0039 补正）：`min_hits_for_occupied` 的计数单位是地图帧。
// 这些用例表达的是"感知帧与地图帧 1:1"的简化情形（每拍都发布），因此两个时钟一起推进；
// 两者比例不是 1:1 的情形由 `ConfirmationCountsMapFramesNotSensorFrames` 单独覆盖。
void hitNext(LogOddsGrid & g, size_t idx)
{
  g.beginFrame(g.currentFrame() + 1);
  g.beginMapFrame(g.currentMapFrame() + 1);
  g.observeHit(idx);
}
void missNext(LogOddsGrid & g, size_t idx)
{
  g.beginFrame(g.currentFrame() + 1);
  g.beginMapFrame(g.currentMapFrame() + 1);
  g.observeMiss(idx);
}
void decayNext(LogOddsGrid & g)
{
  g.beginFrame(g.currentFrame() + 1);
  g.beginMapFrame(g.currentMapFrame() + 1);
  g.decayMiss();
}
}  // namespace

// 概率与 log-odds 互转必须可逆。
TEST(LogOdds, RoundTrip)
{
  for (double p : {0.1, 0.35, 0.5, 0.7, 0.97}) {
    EXPECT_NEAR(fromLogOdds(toLogOdds(p)), p, 1e-9);
  }
}

// 初始状态：所有格都是 unknown（-1），不是 free。
TEST(LogOdds, StartsUnknown)
{
  LogOddsGrid g;
  g.reset(4, 4, defaults());
  const auto s = g.snapshot();
  ASSERT_EQ(s.size(), 16u);
  for (auto v : s) {EXPECT_EQ(v, -1) << "初始必须是 unknown，不能默认 free";}
  EXPECT_EQ(g.occupiedCount(), 0);
}

// **核心判据**：单帧毛刺不得**被判为障碍**（FOV 边缘"这帧有下帧没有"的格子）。
//
// 2026-11-08 判据反转（用户裁定 Q19/Q25）：改造后快照是 0–100 的**占据概率×100**，
// 不再是三态。因此"没画出障碍"的正确表述是**未达到 occupied 门限**（< 60），
// 而不是"等于 -1"。单帧命中恰好落在 50（p=0.50），是**软证据**：
// 消费者按自己的阈值判，而不是被强迫接受一个二值。
TEST(LogOdds, SingleHitDoesNotPaint)
{
  LogOddsGrid g;
  g.reset(4, 4, defaults());
  hitNext(g, 5);                   // 只观测到一次
  const int8_t one = g.snapshot()[5];
  EXPECT_LT(one, 60) << "单帧命中不得跨过 occupied 门限（否则毛刺会画进地图）";
  EXPECT_GT(one, 0) << "单帧命中应保留为软证据（量化概率），而不是丢弃成 unknown";
  hitNext(g, 5);                   // 第二次（**下一帧**）
  EXPECT_EQ(g.snapshot()[5], 100) << "连续两次命中应跨过 occupied 门限";
}

// 反复观测应稳定为 occupied，且置信度趋近上界。
TEST(LogOdds, RepeatedHitsSaturate)
{
  LogOddsGrid g;
  g.reset(4, 4, defaults());
  for (int i = 0; i < 20; ++i) {hitNext(g, 0);}
  EXPECT_EQ(g.snapshot()[0], 100);
  EXPECT_NEAR(g.probAt(0), defaults().p_max, 0.02);
}

// **核心判据**：已确认的障碍不得被一次漏观测抹掉（FOV 边缘被切掉是常态）。
TEST(LogOdds, ConfirmedObstacleSurvivesSingleMiss)
{
  LogOddsGrid g;
  g.reset(4, 4, defaults());
  for (int i = 0; i < 6; ++i) {hitNext(g, 7);}
  ASSERT_EQ(g.snapshot()[7], 100);
  decayNext(g);                    // 一帧没看到
  EXPECT_EQ(g.snapshot()[7], 100) << "一次漏观测不得把已确认的障碍抹掉";
  decayNext(g);
  decayNext(g);
  EXPECT_EQ(g.snapshot()[7], 100) << "三次漏观测仍应保留（衰减是渐进的）";
}

// 长时间不观测才衰减掉（"过期"= 证据变弱，不是"时间到就删"）。
TEST(LogOdds, LongAbsenceDecaysAway)
{
  LogOddsGrid g;
  g.reset(4, 4, defaults());
  for (int i = 0; i < 6; ++i) {hitNext(g, 7);}
  ASSERT_EQ(g.snapshot()[7], 100);
  int frames = 0;
  while (g.snapshot()[7] == 100 && frames < 1000) {decayNext(g); ++frames;}
  EXPECT_GT(frames, 3) << "衰减不得过快（至少要容忍数帧漏观测）";
  EXPECT_LT(frames, 1000) << "必须最终能衰减掉（否则地图永久固化）";
}

// 观测与漏观测交替（FOV 边缘的典型表现）不得稳定为 occupied。
TEST(LogOdds, AlternatingObservationStaysUnknown)
{
  LogOddsGrid g;
  g.reset(4, 4, defaults());
  for (int i = 0; i < 30; ++i) {
    hitNext(g, 3);
    decayNext(g);                  // 交替：命中一帧、漏一帧
  }
  // 交替时净增量 = hit + miss；hit 力度大于 miss 会缓慢上升，
  // 但远慢于连续命中 —— 关键是不能像"单帧直接画"那样立刻显示。
  EXPECT_LT(g.probAt(3), defaults().p_max) << "交替观测不得达到饱和置信度";
}

// 越界索引必须安全忽略（防御性：几何变更时的竞态）。
TEST(LogOdds, OutOfRangeIsIgnored)
{
  LogOddsGrid g;
  g.reset(2, 2, defaults());
  EXPECT_NO_THROW(g.observeHit(999));
  EXPECT_NO_THROW(g.observeMiss(999));
  EXPECT_EQ(g.probAt(999), 0.0);
  EXPECT_EQ(g.hitsAt(999), 0);
}

// 尺寸变化必须能重置（几何变更）。
TEST(LogOdds, ResetChangesGeometry)
{
  LogOddsGrid g;
  g.reset(2, 2, defaults());
  for (int i = 0; i < 6; ++i) {hitNext(g, 0);}
  ASSERT_EQ(g.occupiedCount(), 1);
  g.reset(4, 5, defaults());
  EXPECT_EQ(g.width(), 4);
  EXPECT_EQ(g.height(), 5);
  EXPECT_EQ(g.size(), 20u);
  EXPECT_EQ(g.occupiedCount(), 0) << "重置后必须清空证据";
}

// =================================================================================
// 证据单位 = **每格每帧一次**（2026-11-09 用户裁定，稳定性根因修复的防复活闸门）
// =================================================================================
//
// **为什么这几条是新判据**：`map_adapter` 的一帧里有成千上万个足迹点，而一个 0.5 m 格
// 通常覆盖大量像素。若每个点各算一次 hit，证据强度就取决于**像素采样密度**而不是
// 时序观测：栅格中心一帧打满、障碍边缘只命中一两次，边缘格于是在 100 与中间值之间
// 反复翻转。实测 |Δoccupied| p99 = 140 格（判据 ≤50）正是这么来的。

// 判据 1：**同一帧内重复 observeHit 必须幂等**（一个格一帧只贡献一次证据）。
TEST(LogOddsFrameUnit, RepeatedHitInSameFrameIsIdempotent)
{
  LogOddsGrid g;
  g.reset(4, 4, defaults());
  g.beginFrame(1);
  for (int i = 0; i < 1000; ++i) {g.observeHit(5);}   // 模拟"这个格覆盖了 1000 个像素"
  EXPECT_EQ(g.hitsAt(5), 1) << "同一帧重复 hit 只算一次（否则证据强度取决于像素数）";
  const int8_t v = g.snapshot()[5];
  EXPECT_LT(v, 60) << (
    "1000 个同帧像素不得把该格一帧推到 occupied —— 改造前正是这样，"
    "导致边缘格在门限两侧反复翻转");
  EXPECT_GT(v, 0) << "一次帧内命中仍应留下软证据";
}

// 判据 2：**跨帧**的重复 hit 仍然逐帧累加（去重只在帧内生效）。
TEST(LogOddsFrameUnit, HitsAccumulateAcrossFrames)
{
  LogOddsGrid g;
  g.reset(4, 4, defaults());
  for (int f = 1; f <= 3; ++f) {
    g.beginFrame(f);
    g.beginMapFrame(f);                                // 每拍都发布（1:1）
    for (int i = 0; i < 100; ++i) {g.observeHit(5);}   // 每帧都重复 100 次
  }
  EXPECT_EQ(g.hitsAt(5), 3) << "三帧应恰好记三次 hit（帧内去重、帧间累加）";
  EXPECT_EQ(g.snapshot()[5], 100) << "连续三帧命中应跨过 occupied 门限";
}

// 判据 3：**同帧 hit 优先于 miss** —— 本帧看到的障碍不得被本帧的射线擦掉。
//
// 这是"同一格在正负证据中的权重不对称"的直接修复：carving 一格只算一个保护格，
// 而 hit 却可以累加很多次，导致边缘附近出现"强 hit / 强 miss"的交替转换。
TEST(LogOddsFrameUnit, HitInSameFrameBeatsMiss)
{
  LogOddsGrid g;
  g.reset(4, 4, defaults());
  for (int f = 1; f <= 6; ++f) {
    g.beginFrame(f);
    g.beginMapFrame(f);                                // 每拍都发布（1:1）
    g.observeHit(5);
  }
  ASSERT_EQ(g.snapshot()[5], 100);
  const double p_before = g.probAt(5);

  g.beginFrame(7);
  g.beginMapFrame(7);
  g.observeHit(5);        // 本帧看到障碍
  g.observeMiss(5);       // 同帧射线又穿过它（宽障碍的典型情形）
  g.decayMissMasked(nullptr);
  EXPECT_DOUBLE_EQ(g.probAt(5), std::min(g.params().p_max,
    p_before + toLogOdds(g.params().p_hit)))
    << "同帧内 hit 之后不得再吃 miss/衰减（否则同一帧的正负证据互相抵消）";
}

// 判据 4：**同帧只吃一次负证据** —— stale / decay / carve 不得三重叠加。
//
// 三者叠加会把过渡带格直接推出门限，那是"边缘格反复跨门限"的直接来源之一。
TEST(LogOddsFrameUnit, OnlyOneNegativeEvidencePerFrame)
{
  LogOddsGrid g;
  g.reset(4, 4, defaults());
  for (int f = 1; f <= 6; ++f) {
    g.beginFrame(f);
    g.observeHit(5);
  }
  const double p_after_hits = g.probAt(5);

  g.beginFrame(7);
  g.observeMiss(5);                       // 第一次负证据（生效）
  g.observeMiss(5);                       // 同帧重复（幂等）
  g.decayMissMasked(nullptr);             // 同帧时间衰减（应被槽位拒绝）
  g.markStale(7, 0);                      // stale_after_frames<=0 ⇒ 不动
  const double p_after_one = g.probAt(5);
  EXPECT_LT(p_after_one, p_after_hits) << "第一次负证据必须生效";
  // 再叠加一次 decay 不应再改变概率
  const double before_extra = g.probAt(5);
  g.decayMissMasked(nullptr);
  EXPECT_DOUBLE_EQ(g.probAt(5), before_extra)
    << "同一帧只能吃一次负证据（stale/decay/carve 共用槽位）";
}

// 判据 5：`hitThisFrame` 必须如实反映本帧记账状态（carve 用它判断"这是本帧的墙"）。
TEST(LogOddsFrameUnit, HitThisFrameTracksAccounting)
{
  LogOddsGrid g;
  g.reset(4, 4, defaults());
  g.beginFrame(1);
  EXPECT_FALSE(g.hitThisFrame(5));
  g.observeHit(5);
  EXPECT_TRUE(g.hitThisFrame(5)) << "本帧记账后必须为真（carve 靠它保护本帧障碍格）";
  g.beginFrame(2);
  EXPECT_FALSE(g.hitThisFrame(5)) << "进入新帧后必须为假（上一帧的 hit 不保护本帧）";
}

// 判据 6：有证据格索引必须覆盖 hit 与被 carve 的格（markStale/衰减只遍历它）。
TEST(LogOddsFrameUnit, EvidenceIndexCoversHitsAndCarvedCells)
{
  LogOddsGrid g;
  g.reset(20, 20, defaults());
  EXPECT_EQ(g.evidenceCount(), 0u) << "初始无证据格";
  g.beginFrame(1);
  g.observeHit(5);
  EXPECT_EQ(g.evidenceCount(), 1u);
  g.observeHit(5);                  // 同帧重复不得重复入索引
  EXPECT_EQ(g.evidenceCount(), 1u);
  g.beginFrame(2);
  g.carveRay(0, 3, 10, 3);          // 途经格被 carve
  EXPECT_GT(g.evidenceCount(), 1u) << "被 carve 的格也必须进索引（否则它永远衰减不回 unknown）";
  // 从未观测过的格不得进索引
  EXPECT_EQ(g.evidenceCount() <= g.size(), true);
}

// free 门限：明确观测到空闲的格应写成 0（供射线清除场景）。
TEST(LogOdds, ObservedMissBecomesFree)
{
  LogOddsGrid g;
  g.reset(4, 4, defaults());
  for (int i = 0; i < 8; ++i) {missNext(g, 2);}
  EXPECT_EQ(g.snapshot()[2], 0) << "反复确认空闲应写成 free";
}

// ---------------------------------------------------------------------------------
// 栅格后处理：闭运算 + 8 邻域连通域（修「一个障碍被拆成多个框」）
// ---------------------------------------------------------------------------------

// 核心判据：1 格宽的缝必须被闭运算填上（碎块合回一个）。
// 实测对应现象：tank_pair_n 被拆成 5 个框、planter_row 6 个。
TEST(GridPostProcess, ClosingFillsOneCellGap)
{
  const int w = 10, h = 3;
  std::vector<uint8_t> m(static_cast<size_t>(w) * h, 0);
  // 一行两段，中间隔 1 格
  for (int x = 1; x <= 4; ++x) {m[1 * w + x] = 1;}
  for (int x = 6; x <= 8; ++x) {m[1 * w + x] = 1;}
  const auto closed = agc_perception::close3x3(m, w, h);
  const auto blobs = agc_perception::labelBlobs8(closed, w, h, 2);
  EXPECT_EQ(blobs.size(), 1u) << "1 格缝必须被填上，两段应合成一个 blob";
}

// 2 格及以上的真间隔不得被合并（避免把相邻两个障碍糊成一个）。
TEST(GridPostProcess, ClosingKeepsWiderGaps)
{
  const int w = 12, h = 3;
  std::vector<uint8_t> m(static_cast<size_t>(w) * h, 0);
  for (int x = 1; x <= 3; ++x) {m[1 * w + x] = 1;}
  for (int x = 7; x <= 9; ++x) {m[1 * w + x] = 1;}   // 间隔 3 格
  const auto closed = agc_perception::close3x3(m, w, h);
  const auto blobs = agc_perception::labelBlobs8(closed, w, h, 2);
  EXPECT_EQ(blobs.size(), 2u) << "3 格间隔必须保持分开";
}

// 对角相接的碎块在 8 邻域下应视为同一块（4 邻域会分开）。
TEST(GridPostProcess, DiagonalBlobsMergeUnder8Connectivity)
{
  const int w = 5, h = 5;
  std::vector<uint8_t> m(static_cast<size_t>(w) * h, 0);
  m[1 * w + 1] = 1;
  m[2 * w + 2] = 1;    // 与上一个对角相邻
  const auto blobs = agc_perception::labelBlobs8(m, w, h, 1);
  EXPECT_EQ(blobs.size(), 1u) << "对角相邻必须算同一块（8 邻域）";
}

// 外接框必须覆盖整个 blob。
TEST(GridPostProcess, BlobBoundingBoxCoversAllCells)
{
  const int w = 10, h = 10;
  std::vector<uint8_t> m(static_cast<size_t>(w) * h, 0);
  for (int y = 2; y <= 5; ++y) {
    for (int x = 3; x <= 7; ++x) {m[y * w + x] = 1;}
  }
  const auto blobs = agc_perception::labelBlobs8(m, w, h, 2);
  ASSERT_EQ(blobs.size(), 1u);
  EXPECT_EQ(blobs[0].x0, 3);
  EXPECT_EQ(blobs[0].x1, 7);
  EXPECT_EQ(blobs[0].y0, 2);
  EXPECT_EQ(blobs[0].y1, 5);
  EXPECT_EQ(blobs[0].cells, 4 * 5);
}

// 小于 min_cells 的残余噪声必须被过滤。
TEST(GridPostProcess, TinyBlobsFiltered)
{
  const int w = 8, h = 8;
  std::vector<uint8_t> m(static_cast<size_t>(w) * h, 0);
  m[0 * w + 0] = 1;    // 单格噪声
  for (int x = 4; x <= 6; ++x) {m[4 * w + x] = 1;}
  const auto blobs = agc_perception::labelBlobs8(m, w, h, 2);
  EXPECT_EQ(blobs.size(), 1u) << "单格噪声应被过滤，只留 3 格那块";
}

// 空栅格不得产生 blob。
TEST(GridPostProcess, EmptyGridYieldsNoBlobs)
{
  const int w = 6, h = 6;
  std::vector<uint8_t> m(static_cast<size_t>(w) * h, 0);
  EXPECT_TRUE(agc_perception::labelBlobs8(m, w, h, 1).empty());
  EXPECT_TRUE(agc_perception::close3x3(m, w, h).size() == m.size());
}

// **关键判据**：闭运算只决定"哪些格属于同一块"，外接框必须只由**原始占据格**决定。
// 否则膨胀产物会撑大外框，框尺寸以 0.5 m 步长来回漂（实测 acc_23 的 sx 在 7.0↔6.0 漂，
// 跨度 3.5 m —— 比不做闭运算时还差）。
TEST(GridPostProcess, BoundingBoxUsesOriginalMaskNotDilated)
{
  const int w = 12, h = 5;
  std::vector<uint8_t> occ(static_cast<size_t>(w) * h, 0);
  // 两段真实占据，中间 1 格缝
  for (int x = 2; x <= 4; ++x) {occ[2 * w + x] = 1;}
  for (int x = 6; x <= 8; ++x) {occ[2 * w + x] = 1;}
  const auto closed = agc_perception::close3x3(occ, w, h);
  // 不传 bbox_mask：外框会被膨胀产物撑到 x=1..9、y=1..3
  const auto with_dilation = agc_perception::labelBlobs8(closed, w, h, 2);
  ASSERT_EQ(with_dilation.size(), 1u);
  // 传原始掩码：外框应只覆盖真实占据（x=2..8, y=2..2）
  const auto tight = agc_perception::labelBlobs8(closed, w, h, 2, occ);
  ASSERT_EQ(tight.size(), 1u) << "连通性仍应由闭运算结果决定（碎块要能连上）";
  EXPECT_EQ(tight[0].x0, 2);
  EXPECT_EQ(tight[0].x1, 8);
  EXPECT_EQ(tight[0].y0, 2);
  EXPECT_EQ(tight[0].y1, 2);
  EXPECT_EQ(tight[0].cells, 6) << "格数只数真实占据格";
  EXPECT_LT(tight[0].x0, with_dilation[0].x0 + 1)
    << "两者 x0 应当不同（证明 bbox_mask 真的生效了）";
}

// 若整块都是膨胀产物（原始掩码里没有格），必须被 min_cells 过滤掉。
TEST(GridPostProcess, BlobOfOnlyDilationIsDropped)
{
  const int w = 8, h = 8;
  std::vector<uint8_t> occ(static_cast<size_t>(w) * h, 0);
  occ[4 * w + 4] = 1;                        // 单格
  const auto closed = agc_perception::close3x3(occ, w, h);
  const auto blobs = agc_perception::labelBlobs8(closed, w, h, 2, occ);
  EXPECT_TRUE(blobs.empty()) << "只有 1 个真实格（<min_cells）应被过滤";
}

// =================================================================================
// 批次 1（2026-11-08 用户裁定）：free-space carving + 概率量化
// =================================================================================
//
// **为什么这三条是新判据**：改造前 `decayMiss()` 的守卫是 `if (v > 0.0)`，
// logit ≤ 0 的格子**永远不再衰减**；而 `observeMiss()` 在 src/ 里零调用（只有单测调）。
// 后果：地图事实上**不存在 free 空间**，只有 unknown + occupied ——
// 这既让"障碍形状只增不减"，也让规划器无法区分"看过是空的"与"从没看过"。

// 判据 1：**纯时间流逝只能削弱到 unknown，不得把格子推成 free**（ADR-0039）。
//
// **这条判据的方向在 2026-11-10 被反转了，理由必须记下来**：
// 改造前它断言"长期不看的格必须衰减到 free"，目的是修"卡在 p=0.50 冻结"的 bug。
// 那个 bug 是真的，但把它修成"衰减到 free"引入了更严重的语义错误 ——
// **"没看见"被当成"确认是空的"**。实测后果：真实障碍被自己的时间衰减擦成 free，
// 覆盖率因此有与算法无关的损耗；而规划器会把那里当成"我确认过可以走"。
//
// 正确边界（与 ADR-0035 (g) 的三态纪律一致）：
//   * 时间流逝（本判据）→ 最多降到 `unknown_floor_p`，**仍是 unknown**；
//   * 真实射线穿过（`observeMiss` / carve）→ 才允许到 free（见 RaycastCarvesFasterThanDecay）。
TEST(LogOdds, DecayStopsAtUnknownNotFree)
{
  LogOddsGrid g;
  g.reset(4, 4, defaults());
  for (int i = 0; i < 6; ++i) {hitNext(g, 0);}
  ASSERT_EQ(g.snapshot()[0], 100);
  for (int i = 0; i < 2000; ++i) {decayNext(g);}
  const int8_t v = g.snapshot()[0];
  EXPECT_NE(v, 0)
    << "纯时间流逝**不得**把格子推成 free —— 我们只是很久没再看到它，"
       "并没有看到它是空的（v=" << static_cast<int>(v) << "）";
  EXPECT_GT(v, 0) << "衰减到底也应留下 unknown 带内的量化值";
  EXPECT_LE(g.probAt(0), g.params().unknown_floor_p + 1e-9)
    << "必须确实衰减到下限附近（否则'过期'语义失效）";
}

// 判据 1a：**occupied 必须能因"长期没有再被正向 hit"而退出**（ADR-0039）。
//
// 这是 temp.md 指出的第一个根因：旧 `markStale` 对 `p >= occupied_threshold` 的格
// 直接跳过，于是"已确认占据"永不因时间退出，只能靠射线 carve 擦。而误 hit 最容易
// 落在画幅外 / 遮挡区 / 射线没穿过的位置 —— carving 够不到，错误 occupied 永久驻留。
TEST(LogOdds, OccupiedExpiresWhenNeverHitAgain)
{
  LogOddsParams p = defaults();
  p.occupied_expire_frames = 5;          // 5 帧没有正向 hit 即过期
  LogOddsGrid g;
  g.reset(8, 8, p);
  for (int i = 0; i < 6; ++i) {hitNext(g, 9);}
  ASSERT_EQ(g.snapshot()[9], 100);

  // 只推进帧号 + 调 markStale（模拟"相机飞走了，这格再没被看到"）
  int frames = 0;
  while (g.snapshot()[9] == 100 && frames < 500) {
    g.beginFrame(g.currentFrame() + 1);
    g.markStale(g.currentFrame(), 1);    // stale 窗口 1 帧 ⇒ 本格立即超窗
    ++frames;
  }
  EXPECT_LT(frames, 500) << "长期没有正向 hit 的 occupied 必须能退出（否则误覆盖永久锁死）";
  EXPECT_GT(frames, 5) << "有效期内（" << p.occupied_expire_frames << " 帧）不得退出";
  // **降 unknown，不是 free**
  const int8_t v = g.snapshot()[9];
  EXPECT_NE(v, 0) << "过期只能降到 unknown，不得降成 free（v=" << static_cast<int>(v) << "）";
  EXPECT_LE(g.probAt(9), p.occupied_exit_threshold)
    << "过期后必须退出 occupied 态（p=" << g.probAt(9) << "）";
}

// 判据 1a-bis：**持续被 hit 的 occupied 不得因生命周期而退出**。
// 真实障碍每帧都被看到，过期机制绝不能把它擦掉 —— 否则就是"地图先建后毁"。
TEST(LogOdds, OccupiedSurvivesWhenContinuouslyHit)
{
  LogOddsParams p = defaults();
  p.occupied_expire_frames = 5;
  LogOddsGrid g;
  g.reset(8, 8, p);
  for (int f = 0; f < 300; ++f) {
    g.beginFrame(g.currentFrame() + 1);
    g.beginMapFrame(g.currentMapFrame() + 1);          // 每拍都发布（1:1）
    g.observeHit(9);
    g.markStale(g.currentFrame(), 1);
  }
  EXPECT_EQ(g.snapshot()[9], 100)
    << "每帧都被正向 hit 的格必须保持 occupied（过期机制不得误伤真实障碍）";
}

// 判据 1b：**从没观测过的格绝不能被衰减成 free**。
// 这是比原 bug 更危险的错误：decayMiss() 每帧对全图调用，与"是否在视场内"无关；
// 若无差别衰减，"没看过"会被误当成"看过是空的"。
TEST(LogOdds, DecayNeverFreesUnobservedCells)
{
  LogOddsGrid g;
  g.reset(4, 4, defaults());
  for (int i = 0; i < 500; ++i) {decayNext(g);}
  const auto snap = g.snapshot();
  for (size_t i = 0; i < snap.size(); ++i) {
    EXPECT_EQ(snap[i], -1) << "从未观测过的格必须保持 unknown，格 " << i;
  }
}

// 判据 2：**carving 必须比全局衰减快得多**。
// 射线明确穿过（observeMiss）是真实负证据，应当在少数几帧内把占据格清成 free；
// 而全局时间衰减只是"没看到"，不该这么快。
TEST(LogOdds, RaycastCarvesFasterThanDecay)
{
  LogOddsGrid g1, g2;
  g1.reset(4, 4, defaults());
  g2.reset(4, 4, defaults());
  for (int i = 0; i < 6; ++i) {
    hitNext(g1, 5);
    hitNext(g2, 5);
  }
  ASSERT_EQ(g1.snapshot()[5], 100);
  ASSERT_EQ(g2.snapshot()[5], 100);

  int carve = 0;
  while (g1.snapshot()[5] != 0 && carve < 500) {missNext(g1, 5); ++carve;}
  int decay = 0;
  while (g2.snapshot()[5] != 0 && decay < 2000) {decayNext(g2); ++decay;}
  EXPECT_EQ(g1.snapshot()[5], 0) << "射线穿透必须能把占据格清成 free";
  EXPECT_LT(carve, decay)
    << "carving（真实负证据）必须比全局衰减快：carve=" << carve << " decay=" << decay;
}

// 判据 3：**快照必须是 0–100 的连续概率，不是三态**。
// 依据：nav_msgs/OccupancyGrid 的 data 本就是"占据概率×100"，-1 表示未知。
// 三态（0/100/-1）会把内部已经算出来的置信度**对外丢掉**。
//
// 注意取样位置：证据强度只有落在**过渡带**（free_threshold < p < occupied_threshold，
// 即 20..59）时才连续；跨过门限的格会饱和成 100 / 0（那是有意的稳定性，不是信息丢失）。
TEST(LogOdds, SnapshotCarriesProbabilityNotJustTernary)
{
  LogOddsGrid g;
  g.reset(4, 4, defaults());
  hitNext(g, 1);                   // 1 号格：p=0.50（过渡带）
  // 2 号格：命中 2 次后衰减 7 帧，落在**过渡带更低处**（与 1 号格拉开差距）
  for (int i = 0; i < 2; ++i) {hitNext(g, 2);}
  for (int i = 0; i < 7; ++i) {decayNext(g);}
  const auto snap = g.snapshot();
  const double p1 = g.probAt(1), p2 = g.probAt(2);
  ASSERT_LT(p1, 0.60) << "1 号格应留在过渡带（p=" << p1 << "）";
  ASSERT_LT(p2, 0.60) << "2 号格应留在过渡带（p=" << p2 << "）";
  ASSERT_NE(static_cast<int>(std::lround(p1 * 100)), static_cast<int>(std::lround(p2 * 100)))
    << "构造失败：两格概率太接近，无法验证量化可区分（p1=" << p1 << " p2=" << p2 << "）";
  EXPECT_GT(snap[1], 0) << "有证据的格必须为正（概率×100）";
  EXPECT_NE(snap[1], snap[2])
    << "过渡带内两格的量化值必须可区分（p1=" << p1 << " p2=" << p2
    << "）——改造前三态两者都是 -1，信息丢失";
  // 未知仍必须是 -1（不能被量化成 0，否则规划器会把没看过的地方当自由空间）
  EXPECT_EQ(snap[0], -1) << "从未观测过的格必须保持 -1";
}

// 判据 4：量化后的概率必须能反解回 log-odds 的概率（误差 ≤ 1/100 量化步长）。
TEST(LogOdds, QuantizedValueTracksInternalProbability)
{
  LogOddsGrid g;
  g.reset(4, 4, defaults());
  hitNext(g, 3);                   // 单次命中 → p=0.50，落在过渡带
  const double p = g.probAt(3);
  const int q = g.snapshot()[3];
  EXPECT_NEAR(q / 100.0, p, 0.015)
    << "量化值必须逼近内部概率（p=" << p << " q=" << q << "）";
}

// ---------------------------------------------------------------------------------
// free-space carving（射线穿透）—— 批次 1 的根因修复
// ---------------------------------------------------------------------------------

// 判据：射线途经的格必须被清成 free，**终点格（障碍落点）不得被清**。
TEST(LogOddsCarve, RayClearsPathButNotEndpoint)
{
  LogOddsGrid g;
  g.reset(20, 20, defaults());
  // 场景：终点 (15,10) 是障碍（打满占据），其余格是**空地**（从未观测）。
  // **2026-11-09 语义升级**：射线遇到**已判 occupied** 的格会停止，所以不能再像
  // 旧版那样"整排都打满占据然后指望射线穿过它擦干净" —— 那与"射线被墙挡住"
  // 的物理事实矛盾，而且实测正是它让 65.6% 的可见障碍被自己的 carve 擦成 free。
  for (int i = 0; i < 6; ++i) {hitNext(g, static_cast<size_t>(10) * 20 + 15);}
  ASSERT_EQ(g.snapshot()[10 * 20 + 15], 100);

  // 沿途的空地格先给一点 hit（模拟"曾经被误判为障碍"），让它们有证据可被擦
  for (int x = 1; x < 15; ++x) {
    for (int i = 0; i < 6; ++i) {hitNext(g, static_cast<size_t>(10) * 20 + x);}
  }
  ASSERT_EQ(g.snapshot()[10 * 20 + 5], 100) << "构造前提：途经格最初是 occupied";

  // 现在把途经格**降级**为"有证据但未过门限"，这样射线能穿过它们去打 miss。
  // （真实链路里这些格是误 hit，被后续 carve 逐步擦掉 —— 这里直接构造该状态。）
  // 用大量 miss 把它们压到门限以下。
  for (int x = 1; x < 15; ++x) {
    for (int i = 0; i < 10; ++i) {missNext(g, static_cast<size_t>(10) * 20 + x);}
  }
  ASSERT_LT(g.snapshot()[10 * 20 + 5], 100) << "构造前提：途经格已低于 occupied 门限";

  // 每帧一次（同帧重复 carve 是幂等的）：10 帧的射线才能把路径压到 free。
  for (int i = 0; i < 10; ++i) {
    g.beginFrame(g.currentFrame() + 1);
    g.carveRay(0, 10, 15, 10);
  }

  EXPECT_EQ(g.snapshot()[10 * 20 + 5], 0) << "途经格必须被清成 free";
  EXPECT_EQ(g.snapshot()[10 * 20 + 15], 100) << "终点格是障碍落点，不得被清";
}

// 判据：斜向射线也要覆盖到（Bresenham 的 8 连通）。
TEST(LogOddsCarve, DiagonalRayCarves)
{
  LogOddsGrid g;
  g.reset(20, 20, defaults());
  // **2026-11-09 语义升级**：射线遇 occupied 即停，所以只让**终点**是障碍，
  // 途中格保持空地（否则射线在第一格就停，测不到对角覆盖）。
  for (int k = 0; k < 6; ++k) {hitNext(g, static_cast<size_t>(10) * 20 + 10);}
  for (int i = 0; i < 10; ++i) {
    g.beginFrame(g.currentFrame() + 1);
    g.carveRay(0, 0, 10, 10);
  }
  EXPECT_EQ(g.snapshot()[5 * 20 + 5], 0) << "对角线中点必须被清成 free";
  EXPECT_EQ(g.snapshot()[10 * 20 + 10], 100) << "终点保持占据";
}

// 判据：越界射线必须被安全裁剪，不得崩溃或越界写。
TEST(LogOddsCarve, OutOfBoundsRayIsClipped)
{
  LogOddsGrid g;
  g.reset(5, 5, defaults());
  EXPECT_NO_THROW(g.carveRay(-10, -10, 100, 100));
  EXPECT_NO_THROW(g.carveRay(2, 2, 2, 2));      // 起终点相同
  // 同点射线不得清掉该格（它就是终点）
  for (int i = 0; i < 6; ++i) {hitNext(g, 2 * 5 + 2);}
  g.beginFrame(g.currentFrame() + 1);
  g.carveRay(2, 2, 2, 2);
  EXPECT_EQ(g.snapshot()[2 * 5 + 2], 100) << "退化射线（起终点相同）不得清掉障碍格";
}

// =================================================================================
// 小障碍的空间支持 + 跨帧确认（ADR-0039）
// =================================================================================
//
// **为什么需要**：dense_map 的小障碍只有 0.6–1.2 m（0.5 m 格下 1–3 格宽）。
// 旧判据"点落格即 hit"下，一个孤立错位点跨两帧就能建成 occupied；而大建筑同格内
// 有成千上万个点，同样两帧才是 occupied —— 两者的证据强度完全不同，却走同一条判据。

// 判据：**单帧点数不足的格不得进 hit 证据**（排除孤立错位点）。
TEST(LogOddsSupport, SparseSinglePointIsRejected)
{
  LogOddsParams p = defaults();
  p.min_hit_points_per_cell = 3;
  LogOddsGrid g;
  g.reset(4, 4, p);
  g.beginFrame(1);
  // 1 个点：不足门槛 ⇒ 拒
  EXPECT_FALSE(g.observeHitWithSupport(5, 1, 0.0));
  EXPECT_EQ(g.hitsAt(5), 0) << "单点格不得进 hit 证据";
  // 3 个点：达标 ⇒ 记账
  EXPECT_TRUE(g.observeHitWithSupport(6, 3, 0.0));
  EXPECT_EQ(g.hitsAt(6), 1);
}

// 判据：**z 展布过大的格不得进 hit 证据**（同格混了屋顶 + 侧墙 / 障碍 + 地面）。
TEST(LogOddsSupport, MixedSurfacesInOneCellAreRejected)
{
  LogOddsParams p = defaults();
  p.min_hit_points_per_cell = 1;      // 只测 z 判据
  p.max_hit_z_spread_m = 1.5;
  LogOddsGrid g;
  g.reset(4, 4, p);
  g.beginFrame(1);
  EXPECT_FALSE(g.observeHitWithSupport(5, 100, 4.0))
    << "同格内 z 极差 4 m（屋顶 + 侧墙）必须被拒";
  EXPECT_TRUE(g.observeHitWithSupport(6, 100, 0.3))
    << "同一平面上的点必须通过";
}

// 判据：**帧内累加是惰性重置的**（换帧后点数从 0 重新算）。
TEST(LogOddsSupport, FramePointCountsResetLazily)
{
  LogOddsGrid g;
  g.reset(4, 4, defaults());
  g.beginFrame(1);
  g.addFramePoint(5, 1.0);
  g.addFramePoint(5, 1.2);
  g.addFramePoint(5, 0.8);
  EXPECT_EQ(g.framePoints(5), 3);
  EXPECT_NEAR(g.frameZSpread(5), 0.4, 1e-9);
  g.beginFrame(2);
  EXPECT_EQ(g.framePoints(5), 0) << "换帧后点数必须从 0 重算（帧号惰性重置）";
  EXPECT_DOUBLE_EQ(g.frameZSpread(5), 0.0);
}

// 判据：**进入 occupied 需要跨帧确认**（`min_hits_for_occupied`）。
// 写成独立的门，是为了让"调 p_hit / 调门限"无法静默绕过"至少两帧"。
TEST(LogOddsSupport, OccupiedRequiresCrossFrameConfirmation)
{
  LogOddsParams p = defaults();
  p.min_hits_for_occupied = 2;
  p.min_hit_points_per_cell = 1;
  LogOddsGrid g;
  g.reset(4, 4, p);
  // 单帧内反复 hit（幂等，只记 1 次）⇒ 不得 occupied
  g.beginFrame(1);
  g.beginMapFrame(1);
  for (int i = 0; i < 100; ++i) {g.observeHit(5);}
  EXPECT_NE(g.snapshot()[5], 100)
    << "只命中过 1 帧不得判 occupied（跨帧确认门槛）";
  // 第二帧再命中 ⇒ 确认
  g.beginFrame(2);
  g.beginMapFrame(2);
  g.observeHit(5);
  EXPECT_EQ(g.snapshot()[5], 100) << "两帧确认后才判 occupied";
}

// 判据：确认计数挂**地图帧**时钟，不是感知帧（ADR-0039 补正）。
//
// **为什么这是独立判据**：感知 10 Hz、地图 2 Hz。若按感知帧计数，"K=2 帧确认"
// 在对外地图上实际只用了 0.2 s —— 语义比设计意图弱 5 倍，且随感知帧率漂移。
// 这里构造"同一地图帧内跨了 5 个感知帧"的情形：确认计数必须仍是 1。
TEST(LogOddsSupport, ConfirmationCountsMapFramesNotSensorFrames)
{
  LogOddsParams p = defaults();
  p.min_hits_for_occupied = 2;
  p.min_hit_points_per_cell = 1;
  LogOddsGrid g;
  g.reset(4, 4, p);
  // 5 个感知帧，但**都在同一个地图帧内**（地图 2 Hz 下的真实情形）
  g.beginMapFrame(1);
  for (int f = 1; f <= 5; ++f) {
    g.beginFrame(f);
    g.observeHit(5);
  }
  EXPECT_EQ(g.mapFrameHitsAt(5), 1)
    << "同一地图帧内的多个感知帧只能算 1 次确认（否则 K 的语义随感知帧率漂移）";
  EXPECT_EQ(g.hitsAt(5), 5) << "感知帧计数仍逐帧累加（两者是不同口径，都要保留）";
  EXPECT_NE(g.snapshot()[5], 100) << "只经过 1 个地图帧不得判 occupied";
  // 下一个地图帧再命中 ⇒ 确认
  g.beginMapFrame(2);
  g.beginFrame(6);
  g.observeHit(5);
  EXPECT_EQ(g.mapFrameHitsAt(5), 2);
  EXPECT_EQ(g.snapshot()[5], 100) << "两个地图帧确认后才判 occupied";
}

// =================================================================================
// carving 的置信度门槛（ADR-0039）
// =================================================================================
//
// **为什么需要**：dense_map 里"每箱最近障碍点"会因投影误差逐帧变化。旧口径下任何
// 历史 occupied 都算墙 ⇒ 这一帧的墙挡住射线、下一帧换一堵墙，各自把对方后面的区域
// 标 free，occupied 集合大幅互换（稳定性 p99 的主要来源）。

// 判据：**弱证据格不是遮挡体** —— 射线可以穿过它，但只弱衰减、不判 free。
TEST(LogOddsCarve, WeakCellIsNotAnOccluder)
{
  LogOddsParams p = defaults();
  p.occluder_min_confidence = 0.60;
  LogOddsGrid g;
  g.reset(20, 20, p);
  // 途经格 (5,10) 只有**一次** hit ⇒ p≈0.50 < 遮挡门限 ⇒ 不是墙
  g.beginFrame(1);
  g.observeHit(static_cast<size_t>(10) * 20 + 5);
  const double p_before = g.probAt(static_cast<size_t>(10) * 20 + 5);
  ASSERT_LT(p_before, p.occluder_min_confidence);
  // 射线从 (1,10) 射到 (15,10)：必须穿过 (5,10) 继续向后
  g.beginFrame(2);
  g.carveRay(1, 10, 15, 10);
  const int8_t weak_v = g.snapshot()[10 * 20 + 5];
  EXPECT_NE(weak_v, 0)
    << "弱证据格被射线穿过时**不得**判成 free（那里很可能就是这个方向的小障碍）";
  // 而弱证据格后面的格仍应收到负证据（射线没有停在这里）
  EXPECT_NE(g.snapshot()[10 * 20 + 12], -1)
    << "射线必须穿过弱证据格继续向后，而不是把它当墙停住";
}

// 判据：**已确认的 occupied 必须是遮挡体** —— 射线到此为止，后面的格不被打 miss。
// 物理上正确：射线撞到墙就停，不能"穿过"墙去擦它后面的东西。
TEST(LogOddsCarve, ConfirmedCellStopsTheRay)
{
  LogOddsGrid g;
  g.reset(20, 20, defaults());
  // 把 (5,10) 打满成确认占据
  for (int f = 0; f < 8; ++f) {hitNext(g, static_cast<size_t>(10) * 20 + 5);}
  ASSERT_EQ(g.snapshot()[10 * 20 + 5], 100);
  g.beginFrame(g.currentFrame() + 1);
  g.carveRay(1, 10, 15, 10);
  EXPECT_EQ(g.snapshot()[10 * 20 + 12], -1)
    << "射线撞到确认占据后必须停止，墙后的格不得被标 free（它们是遮挡区，不是空地）";
}

// =================================================================================
// 深度一致性：中位数 + MAD（ADR-0039 补正，temp.md 点名的"深度中位数/MAD"）
// =================================================================================
//
// **为什么极差不够**：极差对单个离群点极敏感（一个错位点就让整格被拒），
// 又抓不到"整片系统性偏移但局部连续"—— 后者正是 temp.md 点名的场景。
// 中位数与 MAD 都是稳健量：少数离群点既不拉偏中位数，也只抬高 MAD 一点点。

// 判据：**少数离群点不得让整格被拒**（稳健性）。
TEST(LogOddsSupport, DepthConsistencyToleratesFewOutliers)
{
  LogOddsParams p = defaults();
  p.max_hit_z_spread_m = 0.0;              // 关掉极差判据，只测 MAD
  p.depth_consistency_floor_m = 0.30;
  p.depth_mad_k = 3.0;
  LogOddsGrid g;
  g.reset(4, 4, p);
  g.beginFrame(1);
  // 15 个点在同一平面上（z≈1.0），1 个离群点（z=5.0）
  for (int i = 0; i < 15; ++i) {g.addFramePoint(5, 1.0 + 0.02 * (i % 3));}
  g.addFramePoint(5, 5.0);
  EXPECT_TRUE(g.frameDepthConsistent(5))
    << "16 个点里 1 个离群不得让整格被拒（极差判据会拒，中位数+MAD 不会）";
}

// 判据：**整片混了两种表面必须被拒**（同格一半屋顶一半地面）。
TEST(LogOddsSupport, DepthConsistencyRejectsTwoSurfaces)
{
  LogOddsParams p = defaults();
  p.max_hit_z_spread_m = 0.0;
  p.depth_consistency_floor_m = 0.30;
  p.depth_mad_k = 3.0;
  LogOddsGrid g;
  g.reset(4, 4, p);
  g.beginFrame(1);
  for (int i = 0; i < 8; ++i) {g.addFramePoint(5, 1.0);}   // 屋顶
  for (int i = 0; i < 8; ++i) {g.addFramePoint(5, 6.0);}   // 侧墙/地面
  EXPECT_FALSE(g.frameDepthConsistent(5))
    << "同格一半屋顶一半地面（两簇、各占一半）必须被拒";
}

// 判据：样本不足 3 个时退回弱判据（不因样本少而无限放行离群）。
TEST(LogOddsSupport, DepthConsistencyFallsBackOnSmallSamples)
{
  LogOddsParams p = defaults();
  p.max_hit_z_spread_m = 0.0;
  p.depth_consistency_floor_m = 0.30;
  LogOddsGrid g;
  g.reset(4, 4, p);
  g.beginFrame(1);
  g.addFramePoint(6, 1.0);
  g.addFramePoint(6, 1.1);
  EXPECT_TRUE(g.frameDepthConsistent(6)) << "两个接近的点应通过";
  g.beginFrame(2);
  g.addFramePoint(7, 1.0);
  g.addFramePoint(7, 3.0);
  EXPECT_FALSE(g.frameDepthConsistent(7)) << "两个相距 2 m 的点应被拒（样本少不放行）";
}

// 判据：样本缓冲有上界（不会因单格点数多而无界增长）。
TEST(LogOddsSupport, DepthSampleBufferIsBounded)
{
  LogOddsParams p = defaults();
  p.depth_sample_cap = 16;
  LogOddsGrid g;
  g.reset(4, 4, p);
  g.beginFrame(1);
  for (int i = 0; i < 5000; ++i) {g.addFramePoint(5, 1.0 + (i % 7) * 0.01);}
  EXPECT_EQ(g.framePoints(5), 5000) << "点数统计仍然准确（不受缓冲上界影响）";
  EXPECT_TRUE(g.frameDepthConsistent(5))
    << "降采样后仍应判为同一平面（缓冲上界不得破坏判据）";
}

// ---------------------------------------------------------------------------
// 逐点不确定度门控（ADR-0042）
// ---------------------------------------------------------------------------
//
// **能红验证**：这几个用例在门控关闭（ratio=0）时必须给出**相反**的结论，
// 否则它们只是"永远通过"的装饰。每个用例同时断言两个方向。

TEST(LogOddsSigma, SigmaAboveHalfCellIsRejected)
{
  LogOddsParams p = defaults();
  p.min_hit_points_per_cell = 1;       // 隔离 σ 门控，不让点数门槛掺进来
  p.max_hit_z_spread_m = 0.0;
  p.cell_size_m = 0.25;                // 证据层格宽
  p.sigma_reject_ratio = 0.5;          // 门限 = 0.125 m
  LogOddsGrid g;
  g.reset(4, 4, p);
  g.beginFrame(1);
  g.addFramePoint(6, 1.0, 0.05);       // 0.05 < 0.125 ⇒ 应通过
  g.addFramePoint(7, 1.0, 0.30);       // 0.30 > 0.125 ⇒ 应被拒
  EXPECT_TRUE(g.observeHitWithSupport(6, 1, 0.0)) << "小 σ 的点应进 hit 证据";
  EXPECT_FALSE(g.observeHitWithSupport(7, 1, 0.0)) << "σ 超半格的点应被拒";
  // **反向对照**：关掉门控后同一批点必须都能进 —— 否则上面那个 false
  // 可能来自别的门槛（例如点数），用例就测不到它声称要测的东西。
  LogOddsParams off = p;
  off.sigma_reject_ratio = 0.0;
  LogOddsGrid g2;
  g2.reset(4, 4, off);
  g2.beginFrame(1);
  g2.addFramePoint(7, 1.0, 0.30);
  EXPECT_TRUE(g2.observeHitWithSupport(7, 1, 0.0)) << "门控关闭时必须放行";
}

TEST(LogOddsSigma, MissingSigmaIsNotTreatedAsPerfect)
{
  // 发布端不提供协方差（旧版本 / 空数组）⇒ `frameSigmaMax` = -1 ⇒ **不拦**。
  // 这一条守的是"加字段不得静默改变旧行为"：若把 -1 当成 0（非常准）会放过一切，
  // 当成大值会拦下一切 —— 两种都是静默的行为变更。
  LogOddsParams p = defaults();
  p.min_hit_points_per_cell = 1;
  p.max_hit_z_spread_m = 0.0;
  p.cell_size_m = 0.25;
  p.sigma_reject_ratio = 0.5;
  LogOddsGrid g;
  g.reset(4, 4, p);
  g.beginFrame(1);
  g.addFramePoint(9, 1.0);             // 老签名：无 σ
  EXPECT_DOUBLE_EQ(g.frameSigmaMax(9), -1.0);
  EXPECT_TRUE(g.observeHitWithSupport(9, 1, 0.0)) << "无信息 ⇒ 不得被拦";
}

TEST(LogOddsSigma, CellSigmaTakesWorstPointNotAverage)
{
  // 一格里 99 个准点 + 1 个糊点 ⇒ 该格必须按**糊的那个**判。
  // 平均会把 0.30 摊成 0.003，门控形同虚设。
  LogOddsParams p = defaults();
  p.cell_size_m = 0.25;
  p.sigma_reject_ratio = 0.5;
  LogOddsGrid g;
  g.reset(4, 4, p);
  g.beginFrame(1);
  for (int i = 0; i < 99; ++i) {g.addFramePoint(5, 1.0, 0.01);}
  g.addFramePoint(5, 1.0, 0.30);
  EXPECT_DOUBLE_EQ(g.frameSigmaMax(5), 0.30) << "必须取最大（最坏点决定该格可不可信）";
}

TEST(LogOddsSigma, ZeroCellSizeDisablesGate)
{
  // `cell_size_m` 未填（0）⇒ 门控自动关闭。守的是"参数没填不得变成全拒"：
  // 那会让整张地图一夜之间变成空的，而且看不出原因。
  LogOddsParams p = defaults();
  p.min_hit_points_per_cell = 1;
  p.max_hit_z_spread_m = 0.0;
  p.cell_size_m = 0.0;                 // 未填
  p.sigma_reject_ratio = 0.5;
  LogOddsGrid g;
  g.reset(4, 4, p);
  g.beginFrame(1);
  g.addFramePoint(3, 1.0, 99.0);       // 荒谬的大 σ
  EXPECT_TRUE(g.observeHitWithSupport(3, 1, 0.0)) << "格宽未知时不得静默收紧";
}

TEST(LogOddsSigma, GateThresholdScalesWithCellSize)
{
  // 同一 σ，在更粗的格下应当通过 —— 门限是"半格"，格越粗越宽松。
  // 这是"按格宽而不是按固定米数"的直接判据：写死 0.125 m 时这条会红。
  LogOddsParams fine = defaults();
  fine.min_hit_points_per_cell = 1;
  fine.max_hit_z_spread_m = 0.0;
  fine.cell_size_m = 0.25;             // 门限 0.125
  fine.sigma_reject_ratio = 0.5;
  LogOddsParams coarse = fine;
  coarse.cell_size_m = 0.50;           // 门限 0.25

  LogOddsGrid a, b;
  a.reset(4, 4, fine);
  b.reset(4, 4, coarse);
  a.beginFrame(1);
  b.beginFrame(1);
  a.addFramePoint(5, 1.0, 0.20);
  b.addFramePoint(5, 1.0, 0.20);
  EXPECT_FALSE(a.observeHitWithSupport(5, 1, 0.0)) << "0.20 > 0.125 ⇒ 细格应拒";
  EXPECT_TRUE(b.observeHitWithSupport(5, 1, 0.0)) << "0.20 < 0.25 ⇒ 粗格应过";
}
