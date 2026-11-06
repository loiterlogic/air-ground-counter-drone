// test_safety_shield_vertical_gate.cpp —— ADR-0010「垂直门控」行为验证
//
// 只验证**门控判据**（哪些圆盘生效）与**归因**，**不**复制投影 / 扫掠逻辑自证：
// 圆盘集一律经生产函数 `SafetyShield::deriveRings()` 取得，测试只断言"生效 / 移除 / 归因"。
//
// 覆盖四条出口判据（plan「空中安全层垂直门控」）：
//   ① 高于顶面 + 净空 → 该障碍圆盘**不生效**；
//   ② 低于顶面 + 净空 → **生效**（含"恰好等于"边界：等于时**生效**，保守）；
//   ③ **下降穿越**顶面 → 圆盘在到达之前**复活**（靠下降前视，不靠状态机）；
//   ④ 平行数组 `obstacle_z_top` 长度不一致 / 逐项坏值 → **拒绝启动**；
//   另加：⑤ 目标间距圆盘**永不**被门控（否则抬高即可无限接近目标）。

#include <limits>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

#include <gtest/gtest.h>
#include <rclcpp/rclcpp.hpp>

#include "agc_air/safety_shield.hpp"

using agc_air::RingSet;
using agc_air::SafetyShield;

namespace
{
// 塔：位于原点，安全半径 5 m，顶高 10 m。
constexpr double kTowerRadius = 5.0;
constexpr double kTowerTop = 10.0;
// 与地图同源的垂直净空 c_clear（yard / open_field / minimal 均为 0.5 m）。
constexpr double kClearance = 0.5;
}  // namespace

class VerticalGateTest : public ::testing::Test
{
protected:
  void SetUp() override
  {
    if (!rclcpp::ok()) {
      rclcpp::init(0, nullptr);
      owned_ = true;
    }
    node_ = std::make_shared<rclcpp::Node>("test_safety_shield_vertical_gate");
  }
  void TearDown() override
  {
    node_.reset();
    if (owned_ && rclcpp::ok()) {rclcpp::shutdown();}
  }

  /// 声明一整套参数（`z_tops` 为空 = 整体缺省，模拟 standalone / 旧配置）。
  void declare(const std::vector<double> & z_tops, bool with_target_params = true)
  {
    node_->declare_parameter("safety.obstacle_names", std::vector<std::string>{"tower"});
    node_->declare_parameter("safety.obstacle_x", std::vector<double>{0.0});
    node_->declare_parameter("safety.obstacle_y", std::vector<double>{0.0});
    node_->declare_parameter("safety.obstacle_safety_radius", std::vector<double>{kTowerRadius});
    node_->declare_parameter("safety.obstacle_z_top", z_tops);
    if (with_target_params) {
      node_->declare_parameter("safety.vertical_clearance_m", kClearance);
    }
  }

  SafetyShield shield() const
  {
    SafetyShield s;
    s.configure_parameters(node_->get_node_parameters_interface(), "safety");
    return s;
  }

  static agc_control::Vector3 vec(double x, double y, double z)
  {
    agc_control::Vector3 v;
    v << x, y, z;
    return v;
  }

  rclcpp::Node::SharedPtr node_;
  bool owned_{false};
};

// ① 高于「顶面 + 净空」→ 该障碍圆盘被移除
TEST_F(VerticalGateTest, AboveTopGatesObstacleOff)
{
  declare({kTowerTop});
  const SafetyShield s = shield();
  const RingSet rs = s.deriveRings(vec(0.0, 0.0, kTowerTop + kClearance + 1.0),
      agc_control::Vector3::Zero(), vec(0.0, 0.0, 0.0), false);
  EXPECT_EQ(rs.rings.size(), 0u);
  EXPECT_EQ(rs.gated_off, 1);
  EXPECT_EQ(rs.obstacles, 0);
}

// ② 低于「顶面 + 净空」→ 圆盘仍生效（无限高语义只在顶高未知时保留）
TEST_F(VerticalGateTest, BelowTopKeepsObstacle)
{
  declare({kTowerTop});
  const SafetyShield s = shield();
  const RingSet rs = s.deriveRings(vec(0.0, 0.0, kTowerTop + kClearance - 0.01),
      agc_control::Vector3::Zero(), vec(0.0, 0.0, 0.0), false);
  ASSERT_EQ(rs.rings.size(), 1u);
  EXPECT_EQ(rs.gated_off, 0);
  EXPECT_EQ(rs.rings[0].r, kTowerRadius + s.obstacleMargin() + s.dynamicMargin());
}

// ②边界：恰好等于「顶面 + 净空」→ 判据 `z_gate >= z_top + c` 成立 ⇒ **移除**
//   （语义上正当：净空恰好达到 c_clear 即算"已在障碍之上"）
TEST_F(VerticalGateTest, ExactlyAtTopPlusClearanceGatesOff)
{
  declare({kTowerTop});
  const SafetyShield s = shield();
  const RingSet rs = s.deriveRings(vec(0.0, 0.0, kTowerTop + kClearance),
      agc_control::Vector3::Zero(), vec(0.0, 0.0, 0.0), false);
  EXPECT_EQ(rs.rings.size(), 0u);
  EXPECT_EQ(rs.gated_off, 1);
}

// ③ 下降穿越：恰在顶面之上、但正在以 |v_z| 下降 → 前视后低于门限 → 圆盘**已复活**
TEST_F(VerticalGateTest, DescendingRevivesRingBeforeReachingTop)
{
  declare({kTowerTop});
  const SafetyShield s = shield();
  // 高度：顶面 + 净空 + 0.02 m（静止时会被移除）
  const double z = kTowerTop + kClearance + 0.02;
  ASSERT_EQ(s.deriveRings(vec(0.0, 0.0, z), agc_control::Vector3::Zero(),
      vec(0.0, 0.0, 0.0), false).rings.size(), 0u);
  // 下降 2.0 m/s：0.2 s 后掉 0.4 m → 判定高度 = z − 0.4 < 顶面 + 净空 → 复活
  const RingSet falling = s.deriveRings(vec(0.0, 0.0, z), vec(0.0, 0.0, -2.0),
      vec(0.0, 0.0, 0.0), false);
  ASSERT_EQ(falling.rings.size(), 1u);
  EXPECT_EQ(falling.gated_off, 0);
  EXPECT_NEAR(falling.gate_height_m, z - 2.0 * s.reactionTime(), 1e-12);
  // 上升不改变判定高度（v_z 只取正分量）：同一高度上升时仍被移除。
  const RingSet rising = s.deriveRings(vec(0.0, 0.0, z), vec(0.0, 0.0, 2.0),
      vec(0.0, 0.0, 0.0), false);
  EXPECT_EQ(rising.rings.size(), 0u);
}

// ③补充：下降速度足够大时，**在顶面之上很远**就已复活（前视余量 = reaction_time × |v_z|）
TEST_F(VerticalGateTest, DescendingLookaheadCoversReactionTime)
{
  declare({kTowerTop});
  const SafetyShield s = shield();
  const double z = kTowerTop + kClearance + 0.3;   // 静止时仍被移除
  ASSERT_EQ(s.deriveRings(vec(0.0, 0.0, z), agc_control::Vector3::Zero(),
      vec(0.0, 0.0, 0.0), false).rings.size(), 0u);
  // −2.0 m/s × 0.2 s = −0.4 m > 0.3 m → 判定高度已低于门限
  EXPECT_EQ(s.deriveRings(vec(0.0, 0.0, z), vec(0.0, 0.0, -2.0),
      vec(0.0, 0.0, 0.0), false).rings.size(), 1u);
}

// ④ 顶高数组逐项坏值 → 拒绝启动（0 / NaN / +Inf 一律拒绝：逐项无"未知"语义）
TEST_F(VerticalGateTest, RejectsInvalidZTopValues)
{
  for (double bad : {0.0, -1.0, std::numeric_limits<double>::quiet_NaN(),
      std::numeric_limits<double>::infinity()})
  {
    static int bad_idx = 0;
    rclcpp::Node::SharedPtr n = std::make_shared<rclcpp::Node>(
      "test_gate_bad_" + std::to_string(bad_idx++));
    n->declare_parameter("safety.obstacle_names", std::vector<std::string>{"tower"});
    n->declare_parameter("safety.obstacle_x", std::vector<double>{0.0});
    n->declare_parameter("safety.obstacle_y", std::vector<double>{0.0});
    n->declare_parameter("safety.obstacle_safety_radius", std::vector<double>{kTowerRadius});
    n->declare_parameter("safety.obstacle_z_top", std::vector<double>{bad});
    SafetyShield s;
    EXPECT_THROW(s.configure_parameters(n->get_node_parameters_interface(), "safety"),
      std::runtime_error) << "z_top=" << bad << " 应被拒绝";
  }
}

// ④ 顶高数组长度与其余四个不一致 → 拒绝启动（R-038 五数组等长）
TEST_F(VerticalGateTest, RejectsMismatchedZTopLength)
{
  node_->declare_parameter("safety.obstacle_names", std::vector<std::string>{"a", "b"});
  node_->declare_parameter("safety.obstacle_x", std::vector<double>{0.0, 6.0});
  node_->declare_parameter("safety.obstacle_y", std::vector<double>{0.0, 6.0});
  node_->declare_parameter("safety.obstacle_safety_radius", std::vector<double>{2.0, 2.0});
  node_->declare_parameter("safety.obstacle_z_top", std::vector<double>{5.0});   // 1 ≠ 2
  SafetyShield s;
  EXPECT_THROW(s.configure_parameters(node_->get_node_parameters_interface(), "safety"),
    std::runtime_error);
}

// ④补充：**整体缺省**顶高数组 → 合法（门控不生效，退化为无限高圆柱 = 旧行为）
TEST_F(VerticalGateTest, AbsentZTopArrayMeansNoGating)
{
  declare({});
  const SafetyShield s = shield();
  const RingSet rs = s.deriveRings(vec(0.0, 0.0, 999.0), agc_control::Vector3::Zero(),
      vec(0.0, 0.0, 0.0), false);
  ASSERT_EQ(rs.rings.size(), 1u);
  EXPECT_EQ(rs.gated_off, 0);
}

// ⑤ 目标间距圆盘**不参与**门控：再高也生效，且不计入障碍盘数
TEST_F(VerticalGateTest, TargetRingIsNeverGated)
{
  declare({kTowerTop});
  const SafetyShield s = shield();
  const RingSet rs = s.deriveRings(vec(0.0, 0.0, 999.0), agc_control::Vector3::Zero(),
      vec(30.0, 30.0, 0.0), true);
  ASSERT_EQ(rs.rings.size(), 1u);
  EXPECT_TRUE(rs.rings[0].is_target);
  EXPECT_EQ(rs.target, 1);
  EXPECT_EQ(rs.obstacles, 0);
  EXPECT_EQ(rs.gated_off, 1);
  EXPECT_NEAR(rs.rings[0].r, s.targetMinDist() + s.targetMargin() + s.dynamicMargin(), 1e-12);
}

// ⑥ 归因：门控后"期望端点在障碍盘内"→ adjusted_obstacle；"在目标盘内"→ adjusted_target。
//    这里用 apply() 端到端断言 reason 字段（不复制投影逻辑）。
TEST_F(VerticalGateTest, ReasonAttributesObstacleVsTarget)
{
  declare({kTowerTop});
  const SafetyShield s = shield();
  agc_control::Reference desired;
  desired.pos = vec(0.0, 0.0, 12.0);          // 直接在塔心正上方（塔盘被门控移除）
  // 高度 12 > 10 + 0.5 ⇒ 塔盘不生效 ⇒ 无障碍介入
  const agc_air::SafetyResult high =
    s.apply(desired, vec(0.0, 0.0, 12.0), agc_control::Vector3::Zero(),
    vec(0.0, 0.0, 0.0), false);
  EXPECT_FALSE(high.modified);
  EXPECT_EQ(high.reason, "clear");
  EXPECT_EQ(high.rings_gated_off, 1);

  // 同一期望端点，但高度 5 m（低于顶面 + 净空）⇒ 塔盘生效 ⇒ 必须被推开
  const agc_air::SafetyResult low =
    s.apply(desired, vec(0.0, 0.0, 5.0), agc_control::Vector3::Zero(),
    vec(0.0, 0.0, 0.0), false);
  EXPECT_TRUE(low.modified);
  EXPECT_EQ(low.reason, "adjusted_obstacle");
  EXPECT_EQ(low.rings_gated_off, 0);

  // 目标盘：期望端点**穿入**目标圆盘（而当前位置在其外边界上）⇒ 可投影到边界 → 归因
  //   adjusted_target。用目标盘半径作参考，避免"两端都在盘内 → 不可行"。
  const double tr = s.targetMinDist() + s.targetMargin() + s.dynamicMargin();
  agc_control::Reference near_target;
  near_target.pos = vec(30.0 - tr * 0.5, 30.0, 12.0);   // 盘中（距目标 0.5·tr）
  const agc_air::SafetyResult tgt =
    s.apply(near_target, vec(30.0 - tr, 30.0, 12.0),   // 恰在盘边界外（起点不在盘内）
    agc_control::Vector3::Zero(), vec(30.0, 30.0, 0.0), true);
  EXPECT_TRUE(tgt.modified);
  EXPECT_EQ(tgt.reason, "adjusted_target");
  EXPECT_EQ(tgt.rings_target, 1);
}
