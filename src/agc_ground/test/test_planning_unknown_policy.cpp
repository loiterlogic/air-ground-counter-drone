// 未知空间规划策略的纯逻辑测试（2026-11-08 用户裁定 Q9/Q11/Q21）。
//
// **为什么需要它**：改造前 `track_unknown_space: true`（unknown→255）看起来是
// "未知区不可走"，但 Navfn 的 `allow_unknown` 默认是 **true** —— 两者互相抵消，
// 实际行为是"未知区随便穿"。而当时的地图**事实上没有 free**（decayMiss 守卫让
// 未知格永不衰减），于是"全图 unknown、规划器随便走"，语义完全落空。
//
// 本测试守护的是**我们自己的判据**，不依赖任何 Navfn 私有参数
// （与 Nav2 解绑：`ADR-0003`）。
#include <string>

#include <gtest/gtest.h>

#include "agc_ground/planning_policy.hpp"

using agc_ground::CellClass;
using agc_ground::classifyCell;
using agc_ground::PlanRejection;
using agc_ground::planRejectionReason;
using agc_ground::toString;

// 分类：0=free / 1..99=过渡带（证据不足，按未知）/ 100=占据 / -1=未知
TEST(PlanningPolicy, CellClassificationMatchesOccupancyGridSemantics)
{
  EXPECT_EQ(classifyCell(0), CellClass::kFree);
  EXPECT_EQ(classifyCell(50), CellClass::kUnknown);      // 过渡带 = 证据不足
  EXPECT_EQ(classifyCell(99), CellClass::kUnknown);
  EXPECT_EQ(classifyCell(100), CellClass::kOccupied);
  EXPECT_EQ(classifyCell(-1), CellClass::kUnknown);
  // 越界/异常值按未知处理（安全方向：不放行）
  EXPECT_EQ(classifyCell(-5), CellClass::kUnknown);
  EXPECT_EQ(classifyCell(127), CellClass::kOccupied);
}

// 起点在未知区 → 明确拒绝，理由可区分。
TEST(PlanningPolicy, UnknownStartIsRejectedWithReason)
{
  EXPECT_EQ(planRejectionReason(CellClass::kUnknown, CellClass::kFree),
            PlanRejection::kStartNotFree);
  EXPECT_NE(planRejectionReason(CellClass::kUnknown, CellClass::kFree),
            PlanRejection::kNone);
}

// 终点在未知区 → 明确拒绝（这是 Q12 边缘直连要处理的场景）。
TEST(PlanningPolicy, UnknownGoalIsRejectedWithReason)
{
  EXPECT_EQ(planRejectionReason(CellClass::kFree, CellClass::kUnknown),
            PlanRejection::kGoalNotFree);
}

// 两端都在已知自由区 → 放行。
TEST(PlanningPolicy, FreeToFreeIsAllowed)
{
  EXPECT_EQ(planRejectionReason(CellClass::kFree, CellClass::kFree),
            PlanRejection::kNone);
}

// 占据必须比未知更"硬"（理由不同，便于诊断）。
TEST(PlanningPolicy, OccupiedIsDistinctFromUnknown)
{
  EXPECT_EQ(planRejectionReason(CellClass::kOccupied, CellClass::kFree),
            PlanRejection::kStartOccupied);
  EXPECT_NE(planRejectionReason(CellClass::kOccupied, CellClass::kFree),
            planRejectionReason(CellClass::kUnknown, CellClass::kFree));
}

// 拒绝理由必须是可读字符串（进日志 / 诊断，不是裸枚举）。
TEST(PlanningPolicy, RejectionReasonIsHumanReadable)
{
  const char * s = toString(PlanRejection::kStartNotFree);
  ASSERT_NE(s, nullptr);
  EXPECT_GT(std::string(s).size(), 3u);
  EXPECT_EQ(std::string(toString(PlanRejection::kNone)), "none");
}

// ---------------------------------------------------------------------------------
// 边缘直连兜底（2026-11-08 用户裁定 Q12）
// ---------------------------------------------------------------------------------
using agc_ground::blocksDirectLink;
using agc_ground::canAnchorDirectLink;

// 判据：只有**已知占据**挡住直连；未知不挡（未知正是要穿过去的部分）。
TEST(PlanningPolicy, DirectLinkIsBlockedOnlyByKnownOccupied)
{
  EXPECT_FALSE(blocksDirectLink(0));     // 自由
  EXPECT_FALSE(blocksDirectLink(-1));    // 未知 —— 不挡
  EXPECT_FALSE(blocksDirectLink(50));    // 过渡带 —— 不挡
  EXPECT_TRUE(blocksDirectLink(100));    // 占据 —— 挡
  EXPECT_TRUE(blocksDirectLink(127));    // 溢出 —— 挡
}

// 判据：直连的两端必须**都是已知自由**。
// 未知端不允许 —— 从没看过的地方连出去，等于凭空造一条路。
TEST(PlanningPolicy, DirectLinkAnchorsMustBeKnownFree)
{
  EXPECT_TRUE(canAnchorDirectLink(0));
  EXPECT_FALSE(canAnchorDirectLink(-1)) << "未知端不得作为锚点";
  EXPECT_FALSE(canAnchorDirectLink(50)) << "过渡带端不得作为锚点";
  EXPECT_FALSE(canAnchorDirectLink(100));
}
