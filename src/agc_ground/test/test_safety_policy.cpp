// 地面安全层纯判定单测（ADR-0045 / 《地面安全层判定与标定》的判定表）
//
// 不启 ROS、不启仿真：`safety_policy.hpp` 的输入输出都是普通 struct。
// 每个用例对应判定表的一行，断言"状态 + 输出速度 + 诊断原因"三件事 ——
// 只断言状态会让"为什么这条不通过"无从查起。

#include <gtest/gtest.h>

#include <cmath>
#include <limits>
#include <string>
#include <vector>

#include "agc_ground/safety_policy.hpp"

namespace agc_ground
{
namespace
{

// 8 m x 8 m @ 0.5 m 的地图，原点 (-4,-4)，全自由。
constexpr int kDim = 16;
constexpr double kRes = 0.5;

struct Fixture
{
  std::vector<int8_t> cells =
    std::vector<int8_t>(static_cast<size_t>(kDim) * static_cast<size_t>(kDim), 0);
  SafetyParams p;
  BodyState body;

  Fixture()
  {
    // 车在原点、朝 +x。
    body.x = 0.0;
    body.y = 0.0;
    body.yaw = 0.0;
    body.valid = true;
    body.finite = true;
    body.stamp_s = 10.0;
  }

  void block(double x, double y)
  {
    const int ix = static_cast<int>(std::floor((x - (-4.0)) / kRes));
    const int iy = static_cast<int>(std::floor((y - (-4.0)) / kRes));
    if (ix < 0 || iy < 0 || ix >= kDim || iy >= kDim) {return;}
    cells[static_cast<size_t>(iy) * kDim + ix] = 100;
  }

  void setCell(double x, double y, int v)
  {
    const int ix = static_cast<int>(std::floor((x - (-4.0)) / kRes));
    const int iy = static_cast<int>(std::floor((y - (-4.0)) / kRes));
    if (ix < 0 || iy < 0 || ix >= kDim || iy >= kDim) {return;}
    cells[static_cast<size_t>(iy) * kDim + ix] = static_cast<int8_t>(v);
  }

  void fillAll(int v)
  {
    for (auto & c : cells) {c = static_cast<int8_t>(v);}
  }

  SafetyInputs inputs(double v, double w) const
  {
    SafetyInputs in;
    in.now_s = 10.0;
    in.has_command = true;
    in.command.v = v;
    in.command.w = w;
    in.command.frame_ok = true;
    in.command.finite = true;
    in.command.holonomic_ok = true;
    in.command.stamp_s = 10.0;

    in.has_body = true;
    in.body = body;

    in.has_map = true;
    in.map.data = cells.data();
    in.map.width = kDim;
    in.map.height = kDim;
    in.map.resolution = kRes;
    in.map.origin_x = -4.0;
    in.map.origin_y = -4.0;
    in.map.frame_ok = true;
    in.map.stamp_s = 10.0;
    in.map_valid_flag = true;

    in.has_permit = true;
    in.permit.state = 3;   // GROUND_APPROACH
    in.permit.stamp_s = 10.0;
    return in;
  }
};

// ---------------------------------------------------------------- 参数闸
TEST(SafetyPolicy, RejectsInvertedTiers)
{
  SafetyParams p;
  p.d_emergency = 3.0;
  p.d_collision = 2.0;
  EXPECT_FALSE(validateParams(p).empty());
  SafetyPolicy pol;
  pol.setParams(p);
  Fixture f;
  const auto d = pol.step(f.inputs(1.0, 0.0));
  EXPECT_EQ(d.state, SafetyState::kParamInvalid);
  EXPECT_DOUBLE_EQ(d.out_v, 0.0);
}

TEST(SafetyPolicy, RejectsRecoverBelowEnter)
{
  SafetyParams p;
  p.d_recover_pass = p.d_safety;   // 必须严格高于
  EXPECT_FALSE(validateParams(p).empty());
}

TEST(SafetyPolicy, ValidDefaultsPass)
{
  EXPECT_EQ(validateParams(SafetyParams{}), "");
}

// ---------------------------------------------------------------- 启动与失源
TEST(SafetyPolicy, StartupWithNoInputsIsExplicitAndZero)
{
  SafetyPolicy pol;
  pol.setParams(SafetyParams{});
  SafetyInputs in;   // 什么都没有
  in.now_s = 10.0;
  const auto d = pol.step(in);
  EXPECT_EQ(d.state, SafetyState::kStartup);
  EXPECT_DOUBLE_EQ(d.out_v, 0.0);
  EXPECT_DOUBLE_EQ(d.out_w, 0.0);
}

TEST(SafetyPolicy, CommandNeverReceivedIsZero)
{
  SafetyPolicy pol;
  pol.setParams(SafetyParams{});
  Fixture f;
  auto in = f.inputs(1.0, 0.0);
  in.has_command = false;
  const auto d = pol.step(in);
  EXPECT_EQ(d.state, SafetyState::kNoCommand);
  EXPECT_DOUBLE_EQ(d.out_v, 0.0);
}

TEST(SafetyPolicy, StaleCommandIsZero)
{
  SafetyPolicy pol;
  pol.setParams(SafetyParams{});
  Fixture f;
  auto in = f.inputs(1.0, 0.0);
  in.command.stamp_s = in.now_s - 5.0;   // 远超 t_cmd_timeout
  const auto d = pol.step(in);
  EXPECT_EQ(d.state, SafetyState::kNoCommand);
  EXPECT_DOUBLE_EQ(d.out_v, 0.0);
}

TEST(SafetyPolicy, StaleMapIsZero)
{
  SafetyPolicy pol;
  pol.setParams(SafetyParams{});
  Fixture f;
  auto in = f.inputs(1.0, 0.0);
  in.map.stamp_s = in.now_s - 10.0;   // 远超 t_map_timeout（2 s）
  const auto d = pol.step(in);
  EXPECT_EQ(d.state, SafetyState::kMapStale);
  EXPECT_DOUBLE_EQ(d.out_v, 0.0);
}

TEST(SafetyPolicy, MissingMapIsZero)
{
  SafetyPolicy pol;
  pol.setParams(SafetyParams{});
  Fixture f;
  auto in = f.inputs(1.0, 0.0);
  in.has_map = false;
  const auto d = pol.step(in);
  EXPECT_EQ(d.state, SafetyState::kMapMissing);
  EXPECT_DOUBLE_EQ(d.out_v, 0.0);
}

TEST(SafetyPolicy, StaleBodyIsZero)
{
  SafetyPolicy pol;
  pol.setParams(SafetyParams{});
  Fixture f;
  auto in = f.inputs(1.0, 0.0);
  in.body.stamp_s = in.now_s - 5.0;
  const auto d = pol.step(in);
  EXPECT_EQ(d.state, SafetyState::kBodyInvalid);
  EXPECT_DOUBLE_EQ(d.out_v, 0.0);
}

TEST(SafetyPolicy, OdomValidFalseIsZero)
{
  SafetyPolicy pol;
  pol.setParams(SafetyParams{});
  Fixture f;
  auto in = f.inputs(1.0, 0.0);
  in.body.valid = false;
  const auto d = pol.step(in);
  EXPECT_EQ(d.state, SafetyState::kBodyInvalid);
  EXPECT_DOUBLE_EQ(d.out_v, 0.0);
}

TEST(SafetyPolicy, FutureStampIsClockAnomalyNotFresh)
{
  SafetyPolicy pol;
  pol.setParams(SafetyParams{});
  Fixture f;
  auto in = f.inputs(1.0, 0.0);
  in.command.stamp_s = in.now_s + 1.0;   // 未来时间戳
  const auto d = pol.step(in);
  EXPECT_EQ(d.state, SafetyState::kClockAnomaly);
  EXPECT_DOUBLE_EQ(d.out_v, 0.0);
}

TEST(SafetyPolicy, NoPermitIsZero)
{
  SafetyPolicy pol;
  pol.setParams(SafetyParams{});
  Fixture f;
  auto in = f.inputs(1.0, 0.0);
  in.permit.state = 0;   // IDLE
  const auto d = pol.step(in);
  EXPECT_EQ(d.state, SafetyState::kNoPermit);
  EXPECT_DOUBLE_EQ(d.out_v, 0.0);
}

// ---------------------------------------------------------------- 一致性闸
TEST(SafetyPolicy, FrameMismatchIsZero)
{
  SafetyPolicy pol;
  pol.setParams(SafetyParams{});
  Fixture f;
  auto in = f.inputs(1.0, 0.0);
  in.map.frame_ok = false;
  EXPECT_EQ(pol.step(in).state, SafetyState::kMapInvalid);

  SafetyPolicy pol2;
  pol2.setParams(SafetyParams{});
  auto in2 = f.inputs(1.0, 0.0);
  in2.command.frame_ok = false;
  EXPECT_EQ(pol2.step(in2).state, SafetyState::kParamInvalid);
}

TEST(SafetyPolicy, EmptyMapIsInvalid)
{
  SafetyPolicy pol;
  pol.setParams(SafetyParams{});
  Fixture f;
  auto in = f.inputs(1.0, 0.0);
  in.map.data = nullptr;
  EXPECT_EQ(pol.step(in).state, SafetyState::kMapInvalid);
}

TEST(SafetyPolicy, MapValidFlagFalseIsInvalid)
{
  SafetyPolicy pol;
  pol.setParams(SafetyParams{});
  Fixture f;
  auto in = f.inputs(1.0, 0.0);
  in.map_valid_flag = false;
  const auto d = pol.step(in);
  EXPECT_EQ(d.state, SafetyState::kMapInvalid);
  EXPECT_DOUBLE_EQ(d.out_v, 0.0);
}

TEST(SafetyPolicy, HolonomicCommandRejectedOnDiffDrive)
{
  SafetyPolicy pol;
  pol.setParams(SafetyParams{});
  Fixture f;
  auto in = f.inputs(1.0, 0.0);
  in.command.holonomic_ok = false;
  EXPECT_EQ(pol.step(in).state, SafetyState::kParamInvalid);
}

// ---------------------------------------------------------------- 空地图 / 全 unknown
TEST(SafetyPolicy, AllUnknownIsNotFree)
{
  SafetyPolicy pol;
  pol.setParams(SafetyParams{});
  Fixture f;
  f.fillAll(-1);
  const auto d = pol.step(f.inputs(1.0, 0.0));
  EXPECT_FALSE(isDrivingState(d.state)) << "全 unknown 不得被当作可通行";
  EXPECT_DOUBLE_EQ(d.out_v, 0.0);
}

TEST(SafetyPolicy, ClearMapPassesAndKeepsCommand)
{
  SafetyPolicy pol;
  pol.setParams(SafetyParams{});
  Fixture f;
  const auto d = pol.step(f.inputs(1.0, 0.5));
  EXPECT_EQ(d.state, SafetyState::kPass);
  EXPECT_DOUBLE_EQ(d.out_v, 1.0);
  EXPECT_DOUBLE_EQ(d.out_w, 0.5);
}

// ---------------------------------------------------------------- 障碍与档位
TEST(SafetyPolicy, ObstacleAheadAtCollisionRangeStops)
{
  SafetyPolicy pol;
  pol.setParams(SafetyParams{});
  Fixture f;
  f.block(1.6, 0.0);   // 车头 0.5 m + 1.1 m
  const auto d = pol.step(f.inputs(1.0, 0.0));
  EXPECT_TRUE(isStopState(d.state) || d.state == SafetyState::kSlow) << d.reason;
  EXPECT_LE(d.diag.d_min_m, 2.0);
}

TEST(SafetyPolicy, SweptBlockedStopsEvenWhenCurrentClearanceIsLarge)
{
  SafetyPolicy pol;
  SafetyParams p;
  p.d_emergency = 0.2;
  p.d_collision = 0.3;
  p.d_safety = 0.6;
  p.d_recover_slow = 0.3;
  p.d_recover_pass = 0.9;
  pol.setParams(p);

  Fixture f;
  // 制动距离**由生产函数算**，不写死数字：标定改 `a_brake` 后写死的期望会静默失真
  // （实测踩过：a 从 0.9 标到 3.2754 后，写死的 2.0 m 落到扫掠区外，测试报"没扫到"）。
  const double sb = pol.brakingDistance(1.5);
  // 障碍放在"净空远大于 d_safety、但落在制动扫掠区内"的位置
  f.block(0.6 + sb * 0.8, 0.0);
  const auto d = pol.step(f.inputs(1.5, 0.0));
  EXPECT_TRUE(d.diag.swept_blocked) << d.reason;
  EXPECT_EQ(d.state, SafetyState::kStopCollision);
  EXPECT_DOUBLE_EQ(d.out_v, 0.0);
}

TEST(SafetyPolicy, SlowBandClipsBothLinearAndAngular)
{
  SafetyPolicy pol;
  SafetyParams p;
  p.d_emergency = 0.5;
  p.d_collision = 1.0;
  p.d_safety = 4.0;
  p.d_recover_slow = 1.0;
  p.d_recover_pass = 4.5;
  // **显式**给一个低于逃逸下限的裁剪比，才能测"裁剪确实同时作用在 ω 上"。
  // 默认值 1.0 表示"实测横向能力贴着要求 ⇒ SLOW 不再降速"，那是对**默认配置**的正确行为，
  // 但会让本用例测不到裁剪逻辑。逃逸下限由 `slowRatioFloor()` 反解。
  p.slow_min_ratio = 0.4;
  p.lateral_reach_required_m = 0.4;   // 相应放宽要求，使 0.4 合规
  pol.setParams(p);
  ASSERT_EQ(pol.paramsError(), "") << "参数校验不该拦住本用例";

  Fixture f;
  f.block(3.0, 0.0);   // 净空约 2.5 m -> 落在 collision..safety 之间
  const auto d = pol.step(f.inputs(1.0, 1.0));
  ASSERT_EQ(d.state, SafetyState::kSlow) << d.reason;
  EXPECT_LT(d.out_v, 1.0);
  EXPECT_GT(d.out_v, 0.0) << "SLOW 不得裁到 0（那是 STOP 的语义）";
  EXPECT_LT(d.out_w, 1.0) << "限速必须**同时**约束角速度，否则原地快转可绕过判据";
  // 同一比例：保持曲率。
  EXPECT_NEAR(d.out_v / 1.0, d.out_w / 1.0, 1e-9);
}

TEST(SafetyPolicy, EmergencyBandStops)
{
  SafetyPolicy pol;
  SafetyParams p;
  p.d_emergency = 1.0;
  p.d_collision = 2.0;
  p.d_safety = 4.0;
  p.d_recover_slow = 2.0;
  p.d_recover_pass = 4.5;
  pol.setParams(p);

  Fixture f;
  // 静止（v=0 ⇒ 扫掠区只有当前 footprint）。障碍必须落在
  //   **footprint + cell_epsilon 之外**（否则判 STOP_COLLISION，那是"已在格内擦碰"）
  //   且净空 < d_emergency=1.0。
  // 车半长 0.5037、cell_epsilon 取半格对角 ⇒ 障碍中心需 > 0.857 m。取 1.1 m。
  // （写死 0.8 会落进膨胀 footprint 内 —— 实测踩过，标定把 epsilon 从 0.05 提到 0.354 后暴露。）
  f.block(1.1, 0.0);
  const auto d = pol.step(f.inputs(0.0, 0.0));
  EXPECT_EQ(d.state, SafetyState::kStopEmergency) << d.reason << " d_min=" << d.diag.d_min_m;
  EXPECT_DOUBLE_EQ(d.out_v, 0.0);
}

TEST(SafetyPolicy, InscribedBandBlocksLikeLethal)
{
  // 99（车心进入即擦碰）与 100 同等阻挡 —— 这是 ADR-0041 风险分档带来的
  // Nav2 二值 lethal 表达不了的一档。若把 99 降级成代价带，车心会擦碰。
  EXPECT_EQ(classifyCellRisk(99), CellRisk::kBlocked);
  EXPECT_EQ(classifyCellRisk(100), CellRisk::kBlocked);
  EXPECT_EQ(classifyCellRisk(120), CellRisk::kBlocked);
  EXPECT_EQ(classifyCellRisk(50), CellRisk::kCost);
  EXPECT_EQ(classifyCellRisk(0), CellRisk::kFree);
  EXPECT_EQ(classifyCellRisk(-1), CellRisk::kUnknown);
}

TEST(SafetyPolicy, CostBandTriggersSlowNotStop)
{
  SafetyPolicy pol;
  SafetyParams p;
  p.d_emergency = 0.5;
  p.d_collision = 1.0;
  p.d_safety = 4.0;
  p.d_recover_slow = 1.0;
  p.d_recover_pass = 4.5;
  pol.setParams(p);

  // 同上：显式给裁剪比，否则默认 1.0（不降速）会让"裁剪"断言测不到。
  p.slow_min_ratio = 0.4;
  p.lateral_reach_required_m = 0.4;
  pol.setParams(p);
  ASSERT_EQ(pol.paramsError(), "") << "参数校验不该拦住本用例";

  Fixture f;
  f.setCell(3.0, 0.0, 50);   // 代价带、非阻挡
  const auto d = pol.step(f.inputs(1.0, 0.0));
  EXPECT_EQ(d.state, SafetyState::kSlow) << d.reason;
  EXPECT_LT(d.out_v, 1.0);
  EXPECT_GT(d.out_v, 0.0);
}

TEST(SafetyPolicy, BackwardMotionSweepsBackwards)
{
  SafetyPolicy pol;
  SafetyParams p;
  p.d_emergency = 0.2;
  p.d_collision = 0.3;
  p.d_safety = 0.5;
  p.d_recover_slow = 0.3;
  p.d_recover_pass = 0.8;
  pol.setParams(p);

  Fixture f;
  const double sb_back = pol.brakingDistance(-1.5);
  f.block(-(0.6 + sb_back * 0.8), 0.0);   // 车后，落在向后制动扫掠区内
  const auto d = pol.step(f.inputs(-1.5, 0.0));
  EXPECT_TRUE(d.diag.swept_blocked) << d.reason;
  EXPECT_EQ(d.state, SafetyState::kStopCollision);
}

TEST(SafetyPolicy, PureRotationIsAlsoConstrained)
{
  SafetyPolicy pol;
  SafetyParams p;
  p.d_emergency = 0.2;
  p.d_collision = 1.2;   // 车角扫掠半径 0.5789 < 1.2
  p.d_safety = 4.0;
  p.d_recover_slow = 1.2;
  p.d_recover_pass = 4.5;
  pol.setParams(p);

  Fixture f;
  f.block(0.0, 0.8);   // 侧后方
  const auto d = pol.step(f.inputs(0.0, 2.0));
  EXPECT_FALSE(isDrivingState(d.state) && d.out_w > 0.0 &&
    d.state == SafetyState::kPass) << "纯旋转不得无条件放行：" << d.reason;
}

// ---------------------------------------------------------------- 逃逸能力（机动性）
// 2026-11-13 实测裁定：SLOW 把 v/ω 同比例裁小之后，横向逃逸能力会**下降**
// （横移 ≈ (v/ω)(1−cos ωT)，比值不变但 (1−cos ωT) 变小）。
// 实测：ratio=0.20 → 2 s 横移 0.0002/0.030/0.048 m（车基本不动）；
//       ratio=1.00 → 0.956/1.153/0.769 m。
// 故"裁多少"有物理下限，**不能凭手感取小值**。
TEST(SafetyPolicy, SlowRatioFloorIsDerivedNotGuessed)
{
  SafetyParams p;
  // 满速下理想圆弧 = (v/ω)(1−cos ωT) = (1/1)(1−cos 2.0) ≈ 1.416（用 v_cap/w_cap）
  p.v_cap = 1.0;
  p.w_cap = 1.0;
  p.lateral_window_s = 2.0;
  p.lateral_eff_ratio = 1.0;          // 先去掉实测折扣，纯看几何
  p.lateral_reach_required_m = 1.0;
  const double floor_ideal = computeSlowRatioFloor(p);
  EXPECT_GT(floor_ideal, 0.0);
  EXPECT_LT(floor_ideal, 1.0);

  // 打实测折扣后，同样的要求需要**更大的** ratio（能力打折 → 不能裁那么多）
  p.lateral_eff_ratio = 0.55;
  const double floor_real = computeSlowRatioFloor(p);
  EXPECT_GE(floor_real, floor_ideal) << "实测折扣只会抬高下限，不会降低";
}

TEST(SafetyPolicy, ParamsRejectRatioBelowEscapeFloor)
{
  SafetyParams p;
  p.slow_min_ratio = 0.2;             // 改造前的值：实测下横向能力归零
  const std::string err = validateParams(p);
  EXPECT_FALSE(err.empty()) << "低于逃逸下限必须拒绝启动，而不是静默少降速";
  EXPECT_NE(err.find("escape-capability floor"), std::string::npos) << err;
}

TEST(SafetyPolicy, RatioOneIsAllowedAndMeansNoSlowdown)
{
  // ratio = 1.0 是**合法**值：它表示"实测横向能力贴着要求 ⇒ SLOW 不再降速"。
  // 那是诚实的表达，不是配置错误 —— 校验只拒绝 >1（放大）与 <=0（等于停车）。
  SafetyParams p;
  p.slow_min_ratio = 1.0;
  EXPECT_EQ(validateParams(p), "");

  SafetyPolicy pol;
  pol.setParams(p);
  Fixture f;
  f.block(3.0, 0.0);
  const auto d = pol.step(f.inputs(1.0, 1.0));
  ASSERT_EQ(d.state, SafetyState::kSlow) << d.reason;
  // 状态仍是 SLOW（净空在带内），但速度不被裁剪
  EXPECT_DOUBLE_EQ(d.out_v, 1.0);
  EXPECT_DOUBLE_EQ(d.out_w, 1.0);
}

// ---------------------------------------------------------------- 预算
TEST(SafetyPolicy, SweepBudgetExceededIsExplicit)
{
  SafetyPolicy pol;
  SafetyParams p;
  p.sweep_cell_limit = 4;   // 故意极小
  pol.setParams(p);
  Fixture f;
  const auto d = pol.step(f.inputs(1.5, 0.0));
  EXPECT_EQ(d.state, SafetyState::kBudgetExceeded);
  EXPECT_DOUBLE_EQ(d.out_v, 0.0);
  EXPECT_NE(d.reason.find("limit"), std::string::npos);
}

TEST(SafetyPolicy, OffMapSweepIsUnknownNotFree)
{
  SafetyPolicy pol;
  pol.setParams(SafetyParams{});
  Fixture f;
  f.body.x = 100.0;   // 整车在地图外
  f.body.y = 100.0;
  const auto d = pol.step(f.inputs(1.0, 0.0));
  EXPECT_FALSE(isDrivingState(d.state)) << "地图外不得被当作自由：" << d.reason;
}

// ---------------------------------------------------------------- 迟滞
TEST(SafetyPolicy, RecoveryRequiresHysteresisTicks)
{
  SafetyParams p;
  p.d_emergency = 0.5;
  p.d_collision = 1.0;
  p.d_safety = 2.0;
  p.d_recover_slow = 1.0;
  p.d_recover_pass = 3.0;
  p.recover_ticks = 3;
  SafetyPolicy pol;
  pol.setParams(p);

  Fixture f;
  f.block(1.2, 0.0);
  auto d = pol.step(f.inputs(0.0, 0.0));
  EXPECT_TRUE(isStopState(d.state)) << d.reason;

  // 障碍移除：净空足够，但**不得**立刻回到 PASS。
  Fixture clear;
  d = pol.step(clear.inputs(0.0, 0.0));
  EXPECT_TRUE(isDegradedState(d.state)) << "第一拍不得放行：" << d.reason;
  d = pol.step(clear.inputs(0.0, 0.0));
  EXPECT_TRUE(isDegradedState(d.state)) << "第二拍不得放行：" << d.reason;
  d = pol.step(clear.inputs(0.0, 0.0));
  EXPECT_EQ(d.state, SafetyState::kPass) << d.reason;
}

TEST(SafetyPolicy, RecoveryResetsWhenConditionBreaks)
{
  SafetyParams p;
  p.d_emergency = 0.5;
  p.d_collision = 1.0;
  p.d_safety = 2.0;
  p.d_recover_pass = 3.0;
  p.recover_ticks = 3;
  SafetyPolicy pol;
  pol.setParams(p);

  Fixture f;
  f.block(1.2, 0.0);
  pol.step(f.inputs(0.0, 0.0));

  Fixture clear;
  pol.step(clear.inputs(0.0, 0.0));       // 1/3
  pol.step(f.inputs(0.0, 0.0));           // 条件破坏 -> 计数清零
  pol.step(clear.inputs(0.0, 0.0));       // 1/3 重新开始
  const auto d = pol.step(clear.inputs(0.0, 0.0));
  EXPECT_TRUE(isDegradedState(d.state)) << "计数必须被清零：" << d.reason;
}

// ---------------------------------------------------------------- 限幅
TEST(SafetyPolicy, PassClampsToModelCap)
{
  SafetyPolicy pol;
  SafetyParams p;
  p.v_cap = 1.2;
  p.w_cap = 1.5;
  pol.setParams(p);
  Fixture f;
  const auto d = pol.step(f.inputs(3.0, 3.0));
  ASSERT_EQ(d.state, SafetyState::kPass);
  EXPECT_DOUBLE_EQ(d.out_v, 1.2);
  EXPECT_DOUBLE_EQ(d.out_w, 1.5);
}

TEST(SafetyPolicy, NonFiniteCommandNeverPasses)
{
  SafetyPolicy pol;
  pol.setParams(SafetyParams{});
  Fixture f;
  auto in = f.inputs(1.0, 0.0);
  in.command.finite = false;
  const auto d = pol.step(in);
  EXPECT_FALSE(isDrivingState(d.state));
  EXPECT_DOUBLE_EQ(d.out_v, 0.0);
}

// ---------------------------------------------------------------- 诊断
TEST(SafetyPolicy, DiagnosticsJsonCarriesRequiredFields)
{
  SafetyPolicy pol;
  pol.setParams(SafetyParams{});
  Fixture f;
  const auto d = pol.step(f.inputs(1.0, 0.0));
  const std::string js = SafetyPolicy::toJson(d, pol.params());
  for (const char * key : {"\"state\"", "\"reason\"", "\"v_raw\"", "\"v_out\"",
      "\"map_age_s\"", "\"cmd_age_s\"", "\"body_age_s\"", "\"s_brake_m\"",
      "\"d_min_m\"", "\"unknown_ratio\"", "\"budget_ms\"", "\"params\""})
  {
    EXPECT_NE(js.find(key), std::string::npos) << "缺少诊断字段 " << key;
  }
  EXPECT_EQ(js.find("nan"), std::string::npos) << "JSON 不得出现 nan（必须写 null）";
}

// ---------------------------------------------------------------- 状态枚举一致性
TEST(SafetyPolicy, OnlyPassAndSlowDrive)
{
  EXPECT_TRUE(isDrivingState(SafetyState::kPass));
  EXPECT_TRUE(isDrivingState(SafetyState::kSlow));
  for (auto s : {SafetyState::kStartup, SafetyState::kNoCommand, SafetyState::kNoPermit,
      SafetyState::kBodyInvalid, SafetyState::kMapMissing, SafetyState::kMapStale,
      SafetyState::kMapInvalid, SafetyState::kClockAnomaly, SafetyState::kParamInvalid,
      SafetyState::kBudgetExceeded, SafetyState::kStopCollision,
      SafetyState::kStopEmergency})
  {
    EXPECT_FALSE(isDrivingState(s)) << toString(s);
  }
}

TEST(SafetyPolicy, BrakingDistanceIsMonotonicAndPhysical)
{
  SafetyPolicy pol;
  SafetyParams p;
  p.a_brake = 0.9;
  p.t_react = 0.3;
  pol.setParams(p);
  // v=1.5：1.5*0.3 + 2.25/1.8 = 0.45 + 1.25 = 1.70 m（与 ADR-0010 的实测标定同量级）。
  EXPECT_NEAR(pol.brakingDistance(1.5), 1.70, 1e-9);
  EXPECT_NEAR(pol.brakingDistance(-1.5), 1.70, 1e-9);
  EXPECT_NEAR(pol.brakingDistance(0.0), 0.0, 1e-12);
  EXPECT_LT(pol.brakingDistance(0.5), pol.brakingDistance(1.0));
}

// =====================================================================================
// 方向化净空（ADR-0047，用户 2026-11-13 裁定）
//
// 判据变更：`d_collision = 2.0 m` 的**数值与停车保证不变**，但它度量的东西从
// "车周围 2 m 内有任何障碍就停"（各向同性圆形禁行区）改为
// "沿当前运动方向、车体宽度带内，进入障碍前够不够停"。
//
// 这组用例守的正是这次变更的**边界**：既证明侧方不再误触发，也证明
// 前方 / 转向 / 旋转三条真正的危险路径**仍然停车**（不得用"放宽"换通行率）。
// =====================================================================================

// 侧方障碍（垂直运动方向、在 2 m 带内）**不得**触发停车 —— 这是本次变更的核心。
TEST(SafetyPolicy, LateralObstacleWithinCollisionRangeDoesNotStop)
{
  SafetyPolicy pol;
  SafetyParams p;
  p.d_emergency = 1.0;
  p.d_collision = 2.0;
  p.d_safety = 4.0;
  p.d_recover_slow = 2.0;
  p.d_recover_pass = 4.5;
  pol.setParams(p);

  Fixture f;
  // 车朝 +x、直行；障碍在正侧方 1.5 m（车体外缘净空约 1.5 - 0.285 = 1.2 m < d_collision）。
  // 各向同性口径下这必然 STOP_COLLISION；方向化口径下它不在走廊带内。
  f.block(0.0, 1.5);
  const auto d = pol.step(f.inputs(1.0, 0.0));
  EXPECT_FALSE(isStopState(d.state))
    << "侧方障碍不应停车（ADR-0047）: " << toString(d.state) << " " << d.reason;
  // 但诊断必须如实记下"侧方有东西"——各向同性净空仍要量出来。
  EXPECT_GE(d.diag.d_min_m, 0.0) << "d_min_m 应仍记录侧向净空";
  EXPECT_LT(d.diag.d_min_m, 2.0) << "本例构造前提：侧向净空确实小于 d_collision";
}

// 前方障碍在碰撞档内**必须**停车（安全保证不变）。
TEST(SafetyPolicy, FrontalObstacleWithinCollisionRangeStillStops)
{
  SafetyPolicy pol;
  SafetyParams p;
  p.d_emergency = 0.5;
  p.d_collision = 2.0;
  p.d_safety = 4.0;
  p.d_recover_slow = 2.0;
  p.d_recover_pass = 4.5;
  pol.setParams(p);

  Fixture f;
  // 低速靠近：障碍在正前方，走廊净空落在 [d_emergency, d_collision) 内。
  // 取小 v 使制动距离很小，确保 swept_blocked 不抢先触发，专测"距离档"这条路径。
  const double sb = pol.brakingDistance(0.3);
  f.block(0.5 + 0.9 + sb + 0.2, 0.0);
  const auto d = pol.step(f.inputs(0.3, 0.0));
  EXPECT_TRUE(isStopState(d.state))
    << "正前方障碍在碰撞档内必须停车: " << toString(d.state) << " " << d.reason;
  EXPECT_GE(d.diag.d_corridor_m, 0.0) << "应量出走廊净空";
}

// 走廊带以车体**半宽**为界（不是半对角）：带外不算前方，带内必须算。
TEST(SafetyPolicy, CorridorBandRespectsFootprintWidth)
{
  SafetyPolicy pol;
  SafetyParams p;
  p.d_emergency = 0.2;
  p.d_collision = 0.6;
  p.d_safety = 1.0;
  p.d_recover_slow = 0.6;
  p.d_recover_pass = 1.2;
  pol.setParams(p);
  const double half_w = p.footprint_half_width;   // 0.28545
  const double eps = p.cell_epsilon;              // 0.3536

  // (a) 障碍中心在车体宽度带**外**：走廊判为无阻挡。
  {
    Fixture f;
    const double y_out = half_w + eps + 0.6;
    f.block(1.2, y_out);
    const auto d = pol.step(f.inputs(0.2, 0.0));
    EXPECT_LT(d.diag.d_corridor_m, 0.0)
      << "带外障碍不应计入走廊净空（y=" << y_out << "）: " << d.reason;
  }
  // (b) 障碍中心在带**内**：走廊判为有阻挡。
  {
    Fixture f;
    f.block(1.2, 0.0);
    const auto d = pol.step(f.inputs(0.2, 0.0));
    EXPECT_GE(d.diag.d_corridor_m, 0.0) << "带内障碍必须计入走廊净空: " << d.reason;
  }
}

// 反向运动：走廊只看**运动方向**那一侧，身后的障碍不算前方。
TEST(SafetyPolicy, CorridorFollowsMotionDirectionNotHeading)
{
  SafetyPolicy pol;
  SafetyParams p;
  p.d_emergency = 0.2;
  p.d_collision = 0.6;
  p.d_safety = 1.0;
  p.d_recover_slow = 0.6;
  p.d_recover_pass = 1.2;
  pol.setParams(p);

  Fixture f;
  f.block(1.5, 0.0);                             // 车头前方 1.5 m
  const auto d = pol.step(f.inputs(-0.2, 0.0));  // 倒车
  EXPECT_LT(d.diag.d_corridor_m, 0.0)
    << "倒车时前方障碍不应计入走廊: " << d.reason;
}

// 原地旋转：车角会扫到侧方障碍 ⇒ 仍必须降档（不得因"没有线速度"就放行）。
TEST(SafetyPolicy, PureRotationIntoNearbyObstacleStillStops)
{
  SafetyPolicy pol;
  SafetyParams p;
  p.d_emergency = 0.5;
  p.d_collision = 2.0;
  p.d_safety = 4.0;
  p.d_recover_slow = 2.0;
  p.d_recover_pass = 4.5;
  pol.setParams(p);

  Fixture f;
  f.block(0.0, 0.7);                    // 紧邻车侧，旋转必然扫到车角
  const auto d = pol.step(f.inputs(0.0, 1.5));
  EXPECT_TRUE(isStopState(d.state) || d.state == SafetyState::kSlow)
    << "原地旋转扫到障碍必须降档: " << toString(d.state) << " " << d.reason;
}

// 穿缝：两侧都有障碍、但走廊带内畅通 ⇒ 不得停车（本次变更要解决的正是这个）。
TEST(SafetyPolicy, PassingThroughGapDoesNotStopOnFlankingObstacles)
{
  SafetyPolicy pol;
  SafetyParams p;
  p.d_emergency = 1.0;
  p.d_collision = 2.0;
  p.d_safety = 4.0;
  p.d_recover_slow = 2.0;
  p.d_recover_pass = 4.5;
  pol.setParams(p);

  Fixture f;
  // 两侧各一列障碍，净缝约 1.5 m（> 车宽 0.571 m），车沿 +x 直行。
  const double y_wall = p.footprint_half_width + p.cell_epsilon + 0.75;
  for (double x = 1.0; x <= 3.0; x += 0.5) {
    f.block(x, y_wall);
    f.block(x, -y_wall);
  }
  const auto d = pol.step(f.inputs(0.3, 0.0));
  EXPECT_FALSE(isStopState(d.state))
    << "走廊畅通时不应因两侧障碍停车（穿缝）: " << toString(d.state) << " " << d.reason;
  EXPECT_LT(d.diag.d_corridor_m, 0.0) << "走廊带内应无阻挡: " << d.reason;
  EXPECT_GE(d.diag.d_min_m, 0.0) << "侧方净空仍应被记录（诊断不丢信息）";
}

// SLOW 比例插值必须用走廊净空：侧方窄不减速，前方窄才减速。
TEST(SafetyPolicy, SlowRatioUsesCorridorNotIsotropic)
{
  SafetyParams p;
  p.d_emergency = 0.5;
  p.d_collision = 1.0;
  p.d_safety = 3.0;
  p.d_recover_slow = 1.0;
  p.d_recover_pass = 3.5;
  // 注意：`slow_min_ratio` 的终值是 1.0（ADR-0046：实测横移能力贴着要求，
  // 降速会取消逃逸能力 ⇒ 不降速才是诚实终值）。所以本用例要显式取一个**低于 1**
  // 的下限才能观察到插值效果；取 1.0 时 SLOW 恒不降速，插值不可见。
  p.slow_min_ratio = 0.2;
  p.lateral_reach_required_m = 0.01;   // 让反解下限很低，避免启动期校验拒绝 0.2

  // (a) 只有侧方障碍：走廊无阻挡 ⇒ 不得降速（比例应为 1.0，而非被侧方距离拉低）。
  {
    SafetyPolicy pol;
    pol.setParams(p);
    ASSERT_TRUE(pol.paramsError().empty()) << pol.paramsError();
    Fixture f;
    f.block(0.0, 1.4);
    const auto d = pol.step(f.inputs(0.5, 0.0));
    EXPECT_FALSE(isStopState(d.state)) << d.reason;
    EXPECT_LT(d.diag.d_corridor_m, 0.0) << "走廊带内应无阻挡: " << d.reason;
    EXPECT_DOUBLE_EQ(d.out_v, 0.5) << "侧方障碍不应导致降速: " << d.reason;
  }

  // (b) 前方障碍落在 SLOW 带内：应按走廊净空降速（低于满速、高于下限）。
  {
    SafetyPolicy pol;
    pol.setParams(p);
    ASSERT_TRUE(pol.paramsError().empty()) << pol.paramsError();
    Fixture f;
    f.block(0.5 + 2.0, 0.0);   // 走廊净空约 2.0 m ∈ [d_collision, d_safety)
    const auto d = pol.step(f.inputs(0.3, 0.0));
    EXPECT_EQ(d.state, SafetyState::kSlow) << d.reason;
    EXPECT_GT(d.diag.d_corridor_m, 0.0) << d.reason;
    EXPECT_LT(d.out_v, 0.3) << "前方窄走廊应降速: " << d.reason;
    EXPECT_GE(d.out_v, 0.3 * p.slow_min_ratio - 1e-9) << "不得低于下限: " << d.reason;
  }
}

// 诊断 JSON 必须带方向化字段（下游 run_logger / 验收脚本要读）。
TEST(SafetyPolicy, DiagnosticsJsonCarriesCorridorFields)
{
  SafetyPolicy pol;
  pol.setParams(SafetyParams{});
  Fixture f;
  f.block(1.6, 0.0);
  const auto d = pol.step(f.inputs(0.5, 0.0));
  const std::string js = SafetyPolicy::toJson(d, pol.params());
  EXPECT_NE(js.find("\"d_corridor_m\""), std::string::npos) << js;
  EXPECT_NE(js.find("\"d_corridor_cell\""), std::string::npos) << js;
}

// **恢复死锁回归**：有运动方向且走廊带内无阻挡（`d_corridor_m < 0` = 无穷净空）时，
// 必须能恢复，**不得**锁在降级态。
//
// 这是实现时真踩过的坑：`d_corridor_m < 0` 被当成"没有走廊数据"，退化去用各向同性的
// `d_min_m`。当 `d_min_m`（如 4.00 m）小于 `d_recover_pass`（4.50 m）时，
// 恢复条件**永远**不满足 ⇒ 车被永久钉在 STOP_COLLISION。
// 实测形态：`dense_map` 新出生位朝 +x（走廊带内无阻挡、侧方 4.0 m 有障碍）。
TEST(SafetyPolicy, RecoveryWorksWhenCorridorIsClearButIsotropicIsClose)
{
  SafetyParams p;
  p.d_emergency = 1.0;
  p.d_collision = 2.0;
  p.d_safety = 4.0;
  p.d_recover_slow = 2.0;
  p.d_recover_pass = 4.5;      // 高于侧方各向同性净空
  p.recover_ticks = 2;
  SafetyPolicy pol;
  pol.setParams(p);

  // 先用"前方有障碍"把状态打到 STOP_COLLISION。
  Fixture blocked;
  blocked.block(0.5 + 1.5, 0.0);
  const auto d0 = pol.step(blocked.inputs(0.3, 0.0));
  ASSERT_TRUE(isDegradedState(d0.state)) << "构造前提：先进入降级态: " << d0.reason;

  // 换成"正侧方有障碍、走廊带内无阻挡"的图：各向同性净空 < d_recover_pass，
  // 但走廊净空是无穷 ⇒ 必须能恢复。
  //
  // **坐标必须在图内**：Fixture 是 8×8 @ 0.5 m、原点 (-4,-4)，即 x,y ∈ [-4, 4)。
  // 第一版写成 `block(0.0, 4.0)` —— 恰好落在图外、格根本没被设置，于是各向同性净空
  // 依然很大，变异测试**抓不住**那个 bug（实测：把恢复逻辑改回"退化用 d_min_m" 后仍全绿）。
  // 现取 y=3.5（图内），使 d_min_m ≈ 3.0 < d_recover_pass = 4.5。
  Fixture side;
  side.block(0.0, 3.5);
  auto d1 = pol.step(side.inputs(0.3, 0.0));
  EXPECT_LT(d1.diag.d_corridor_m, 0.0)
    << "构造前提：走廊带内应无阻挡: " << d1.reason;
  EXPECT_LT(d1.diag.d_min_m, p.d_recover_pass)
    << "构造前提：各向同性净空应低于恢复门槛: " << d1.diag.d_min_m;
  EXPECT_GE(d1.diag.d_min_m, 0.0) << "构造前提：侧方障碍必须真的在图内被设上";

  // 连续满足 recover_ticks 拍后必须回到 PASS（不得永久锁死）。
  bool recovered = (d1.state == SafetyState::kPass);
  for (int i = 0; i < 4 && !recovered; ++i) {
    const auto dn = pol.step(side.inputs(0.3, 0.0));
    if (dn.state == SafetyState::kPass) {recovered = true;}
  }
  EXPECT_TRUE(recovered)
    << "走廊带内无阻挡 = 无穷净空，必须能恢复；锁在降级态说明退化用了各向同性净空";
}

}  // namespace
}  // namespace agc_ground
