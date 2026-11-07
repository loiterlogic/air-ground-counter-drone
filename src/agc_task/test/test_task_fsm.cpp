// task_fsm 单元测试 —— 转移条件与 dwell 判据的**逐条**锚点。
//
// 这些判据原先只存在于 911 行的 `task_manager` 节点类里，零单元测试；
// 任何一处放宽都会让"没完成任务"被记成成功。每个 TEST 对应原实现里的一个分支，
// 注释里写明"放宽了会怎样"。

#include <gtest/gtest.h>

#include <fstream>
#include <iterator>
#include <string>

#include "agc_task/task_fsm.hpp"

using agc_task::TaskFsm;
namespace AgcTaskState = agc_task::task_state;
using agc_task::TaskFsmInputs;

namespace
{

// 构造一个"什么都正常"的输入：目标新鲜、车 odom 新鲜、距离在阈值内、无事件。
TaskFsmInputs fresh_inputs(double now_s = 10.0)
{
  TaskFsmInputs in;
  in.now_s = now_s;
  in.start_s = 0.0;
  in.t_max_s = 120.0;
  in.fresh = true;
  in.have_target = true;
  in.target_conf = 0.9;
  in.confidence_min = 0.5;
  in.current_epoch = 1;
  in.target_id = "intruder_uav";
  in.target_x = 1.0;
  in.target_y = 0.0;
  in.have_car = true;
  in.car_age_s = 0.05;
  in.car_x = 0.0;
  in.car_y = 0.0;
  in.d_track_m = 3.0;
  in.t_dwell_s = 3.0;
  in.car_odom_max_age_s = 1.0;
  return in;
}

// 推进到 GROUND_APPROACH（AIR_SEARCH → TARGET_ACQUIRED → GROUND_APPROACH）。
TaskFsm to_ground_approach()
{
  TaskFsm fsm;
  fsm.force_state(AgcTaskState::AIR_SEARCH);
  auto in = fresh_inputs();
  auto d = fsm.step(in);
  EXPECT_EQ(d.next_state, AgcTaskState::TARGET_ACQUIRED);
  fsm.force_state(d.next_state);
  in.have_cmd = true;
  in.cmd_age_s = 0.1;
  d = fsm.step(in);
  EXPECT_EQ(d.next_state, AgcTaskState::GROUND_APPROACH);
  fsm.force_state(d.next_state);
  return fsm;
}

}  // namespace

// ---------------------------------------------------------------- 状态迁移

TEST(TaskFsm, IdleDoesNotTick)
{
  // IDLE 不参与 FSM——否则 start 之前的任何一拍都可能把状态推走。
  TaskFsm fsm;
  fsm.force_state(AgcTaskState::IDLE);
  const auto d = fsm.step(fresh_inputs());
  EXPECT_FALSE(d.state_changed);
  EXPECT_FALSE(d.terminal);
}

TEST(TaskFsm, AirSearchNeedsFreshTarget)
{
  TaskFsm fsm;
  fsm.force_state(AgcTaskState::AIR_SEARCH);

  auto stale = fresh_inputs();
  stale.fresh = false;
  EXPECT_FALSE(fsm.step(stale).state_changed) << "不新鲜的目标不得推进状态";

  auto fresh = fresh_inputs();
  const auto d = fsm.step(fresh);
  ASSERT_TRUE(d.state_changed);
  EXPECT_EQ(d.next_state, AgcTaskState::TARGET_ACQUIRED);
  EXPECT_EQ(d.reason, "target_acquired");
}

TEST(TaskFsm, TargetAcquiredNeedsFreshCommand)
{
  TaskFsm fsm;
  fsm.force_state(AgcTaskState::TARGET_ACQUIRED);

  auto no_cmd = fresh_inputs();
  no_cmd.have_cmd = false;
  EXPECT_FALSE(fsm.step(no_cmd).state_changed) << "没收到命令不得进 GROUND_APPROACH";

  auto stale_cmd = fresh_inputs();
  stale_cmd.have_cmd = true;
  stale_cmd.cmd_age_s = 0.6;          // > cmd_fresh_s(0.5)
  EXPECT_FALSE(fsm.step(stale_cmd).state_changed) << "陈旧命令不得进 GROUND_APPROACH";

  auto ok = fresh_inputs();
  ok.have_cmd = true;
  ok.cmd_age_s = 0.1;
  const auto d = fsm.step(ok);
  ASSERT_TRUE(d.state_changed);
  EXPECT_EQ(d.next_state, AgcTaskState::GROUND_APPROACH);
}

// ---------------------------------------------------------------- 超时

TEST(TaskFsm, TimeoutIsFailure)
{
  // 超时**一律**算失败：放宽这里等于把"没完成"记成成功。
  TaskFsm fsm;
  fsm.force_state(AgcTaskState::AIR_SEARCH);
  auto in = fresh_inputs(200.0);
  in.t_max_s = 120.0;
  const auto d = fsm.step(in);
  ASSERT_TRUE(d.terminal);
  EXPECT_EQ(d.next_state, AgcTaskState::MISSION_FAILED);
  EXPECT_EQ(d.reason, "TIMEOUT");
}

TEST(TaskFsm, TimeoutBeatsAnyTransition)
{
  // 同一拍既超时又满足迁移条件 → 必须判超时（顺序不能反）。
  TaskFsm fsm;
  fsm.force_state(AgcTaskState::AIR_SEARCH);
  auto in = fresh_inputs(200.0);
  in.t_max_s = 120.0;
  in.fresh = true;
  const auto d = fsm.step(in);
  EXPECT_EQ(d.next_state, AgcTaskState::MISSION_FAILED);
}

// ---------------------------------------------------------------- dwell 起始

TEST(TaskFsm, DwellStartsOnlyWhenAllConditionsHold)
{
  auto fsm = to_ground_approach();

  auto no_car = fresh_inputs();
  no_car.have_car = false;
  EXPECT_FALSE(fsm.step(no_car).dwell_started) << "车 odom 缺失时不得起 dwell";

  auto far = fresh_inputs();
  far.target_x = 99.0;
  EXPECT_FALSE(fsm.step(far).dwell_started) << "超出 d_track 时不得起 dwell";

  auto ok = fresh_inputs();
  const auto d = fsm.step(ok);
  EXPECT_TRUE(d.dwell_started);
  EXPECT_TRUE(fsm.dwell_active());
  EXPECT_EQ(fsm.dwell_target_id(), "intruder_uav");
}

// ---------------------------------------------------------------- dwell 中断

TEST(TaskFsm, DwellInterruptsOnStaleCarOdom)
{
  auto fsm = to_ground_approach();
  fsm.step(fresh_inputs(10.0));

  auto in = fresh_inputs(11.0);
  in.car_age_s = 2.0;                 // > car_odom_max_age_s(1.0)
  const auto d = fsm.step(in);
  ASSERT_TRUE(d.dwell_interrupted);
  EXPECT_EQ(d.dwell_interrupt_reason, "CAR_ODOM_STALE");
  EXPECT_FALSE(fsm.dwell_active()) << "中断后必须清零，不得继续累计";
}

TEST(TaskFsm, DwellInterruptsOnTargetIdChange)
{
  // 换目标必须重算——否则"追 A 的时间"会被算成"追 B 的时间"。
  auto fsm = to_ground_approach();
  fsm.step(fresh_inputs(10.0));

  auto in = fresh_inputs(11.0);
  in.target_id = "another_target";
  const auto d = fsm.step(in);
  ASSERT_TRUE(d.dwell_interrupted);
  EXPECT_EQ(d.dwell_interrupt_reason, "TARGET_ID_CHANGED");
}

TEST(TaskFsm, DwellInterruptsOnEpochChange)
{
  // 新 episode 必须清零——否则跨 episode 的接近时长会被累计。
  auto fsm = to_ground_approach();
  fsm.step(fresh_inputs(10.0));

  auto in = fresh_inputs(11.0);
  in.current_epoch = 2;
  const auto d = fsm.step(in);
  ASSERT_TRUE(d.dwell_interrupted);
  EXPECT_EQ(d.dwell_interrupt_reason, "EPOCH_CHANGED");
}

TEST(TaskFsm, DwellInterruptsOnRangeExceeded)
{
  auto fsm = to_ground_approach();
  fsm.step(fresh_inputs(10.0));

  auto in = fresh_inputs(11.0);
  in.target_x = 99.0;
  const auto d = fsm.step(in);
  ASSERT_TRUE(d.dwell_interrupted);
  EXPECT_EQ(d.dwell_interrupt_reason, "RANGE_EXCEEDED");
}

TEST(TaskFsm, DwellInterruptDistinguishesLowConfFromStale)
{
  // 低置信度与过期必须**分开报**：前者是感知质量问题，后者是链路/时效问题。
  {
    auto fsm = to_ground_approach();
    fsm.step(fresh_inputs(10.0));
    auto in = fresh_inputs(11.0);
    in.fresh = false;
    in.target_conf = 0.1;             // < confidence_min(0.5)
    EXPECT_EQ(fsm.step(in).dwell_interrupt_reason, "TARGET_LOW_CONF");
  }
  {
    auto fsm = to_ground_approach();
    fsm.step(fresh_inputs(10.0));
    auto in = fresh_inputs(11.0);
    in.fresh = false;
    in.target_conf = 0.9;             // 置信度够，但样本过期
    EXPECT_EQ(fsm.step(in).dwell_interrupt_reason, "TARGET_STALE");
  }
}

TEST(TaskFsm, DwellInterruptDistinguishesMissingFromStaleCarOdom)
{
  {
    auto fsm = to_ground_approach();
    fsm.step(fresh_inputs(10.0));
    auto in = fresh_inputs(11.0);
    in.have_car = false;
    EXPECT_EQ(fsm.step(in).dwell_interrupt_reason, "CAR_ODOM_MISSING");
  }
  {
    auto fsm = to_ground_approach();
    fsm.step(fresh_inputs(10.0));
    auto in = fresh_inputs(11.0);
    in.car_age_s = 5.0;
    EXPECT_EQ(fsm.step(in).dwell_interrupt_reason, "CAR_ODOM_STALE");
  }
}

// ---------------------------------------------------------------- 里程碑

TEST(TaskFsm, MilestoneRequiresContinuousDwell)
{
  // "连续 t_dwell 有效"，**不降级**为"累计接近时长"。
  auto fsm = to_ground_approach();
  fsm.step(fresh_inputs(10.0));                       // dwell 起点 = 10
  EXPECT_FALSE(fsm.step(fresh_inputs(12.9)).state_changed) << "差 0.1 s 不得算成功";

  const auto d = fsm.step(fresh_inputs(13.0));
  ASSERT_TRUE(d.state_changed);
  EXPECT_EQ(d.next_state, AgcTaskState::TRACKING_SUCCESS);
  EXPECT_EQ(d.reason, "tracking_milestone");
  EXPECT_TRUE(fsm.tracking_milestone_met());
}

TEST(TaskFsm, InterruptedDwellRestartsFromZero)
{
  // 中断后必须从 0 重算：10 → 11 中断 → 11 起重算，13.5 才够 3 s（不是 13.0）。
  auto fsm = to_ground_approach();
  fsm.step(fresh_inputs(10.0));

  auto broke = fresh_inputs(11.0);
  broke.target_id = "other";
  ASSERT_TRUE(fsm.step(broke).dwell_interrupted);

  fsm.step(fresh_inputs(11.0));                       // 重新起 dwell
  EXPECT_FALSE(fsm.step(fresh_inputs(13.0)).state_changed)
    << "中断后不得沿用中断前的累计时间";
  const auto d = fsm.step(fresh_inputs(14.0));
  ASSERT_TRUE(d.state_changed);
  EXPECT_EQ(d.next_state, AgcTaskState::TRACKING_SUCCESS);
}

TEST(TaskFsm, CaptureSceneDoesNotLatchTrackingSuccess)
{
  // capture 场景（tracking_milestone_is_terminal=false）下**不**锁存 TRACKING_SUCCESS——
  // 否则 capture_adjudicator 的交火窗口被提前关闭，捕获永远不发生（ADR-0014）。
  auto fsm = to_ground_approach();
  auto in = fresh_inputs(10.0);
  in.tracking_milestone_is_terminal = false;
  fsm.step(in);

  auto later = fresh_inputs(13.0);
  later.tracking_milestone_is_terminal = false;
  const auto d = fsm.step(later);
  EXPECT_FALSE(d.state_changed) << "capture 场景不得锁存 TRACKING_SUCCESS";
  EXPECT_TRUE(d.milestone_met_now) << "里程碑仍须如实记录，供指标使用";
  EXPECT_TRUE(fsm.tracking_milestone_met());
}

// ---------------------------------------------------------------- 捕获 / 干扰结算

TEST(TaskFsm, CaptureAloneConfirmsIntercept)
{
  auto fsm = to_ground_approach();
  auto in = fresh_inputs(10.0);
  in.capture_reason = "CAPTURE_NET";
  in.capture_rx_s = 9.5;
  const auto d = fsm.step(in);
  ASSERT_TRUE(d.terminal);
  EXPECT_EQ(d.next_state, AgcTaskState::INTERCEPT_CONFIRMED);
  EXPECT_EQ(d.reason, "CAPTURE_NET");
}

TEST(TaskFsm, JamAloneConfirmsIntercept)
{
  auto fsm = to_ground_approach();
  auto in = fresh_inputs(10.0);
  in.jam_reason = "JAM_RTL";
  in.jam_rx_s = 9.5;
  const auto d = fsm.step(in);
  ASSERT_TRUE(d.terminal);
  EXPECT_EQ(d.reason, "JAM_RTL");
}

TEST(TaskFsm, JamNoneIsNotAConfirmation)
{
  // `JAM_NONE` 是"干扰无效果"的占位值，**不是**命中——判成命中会把失败记成成功。
  auto fsm = to_ground_approach();
  auto in = fresh_inputs(10.0);
  in.jam_reason = "JAM_NONE";
  EXPECT_FALSE(fsm.step(in).terminal);
}

TEST(TaskFsm, FirstArrivalWinsBetweenCaptureAndJam)
{
  // 先命中者胜按**事件到达时刻**定序，不固定 capture 优先。
  {
    auto fsm = to_ground_approach();
    auto in = fresh_inputs(10.0);
    in.capture_reason = "CAPTURE_NET";
    in.jam_reason = "JAM_LAND";
    in.capture_rx_s = 9.0;            // capture 先到
    in.jam_rx_s = 9.5;
    EXPECT_EQ(fsm.step(in).reason, "CAPTURE_NET");
  }
  {
    auto fsm = to_ground_approach();
    auto in = fresh_inputs(10.0);
    in.capture_reason = "CAPTURE_NET";
    in.jam_reason = "JAM_LAND";
    in.capture_rx_s = 9.6;            // jam 先到
    in.jam_rx_s = 9.5;
    EXPECT_EQ(fsm.step(in).reason, "JAM_LAND");
  }
}

// ---------------------------------------------------------------- 常量一致性

TEST(TaskFsm, StateConstantsMatchMsgDefinition)
{
  // `task_fsm.hpp` 刻意不 include 消息头（为了不依赖 ROS，能在纯 gtest 里编译）。
  // 代价是常量值可能与 `AgcTaskState.msg` 漂移——这里把它钉住。
  // 改 `.msg` 的常量值必须同步改头文件，否则本测试失败。
  const std::string msg_path =
    std::string(AGC_TASK_SOURCE_DIR) + "/../agc_msgs/msg/AgcTaskState.msg";
  std::ifstream f(msg_path);
  ASSERT_TRUE(f.good()) << "读不到 " << msg_path;
  std::string text((std::istreambuf_iterator<char>(f)), std::istreambuf_iterator<char>());

  struct Expect {const char * name; uint8_t value;};
  const Expect expects[] = {
    {"IDLE", AgcTaskState::IDLE},
    {"AIR_SEARCH", AgcTaskState::AIR_SEARCH},
    {"TARGET_ACQUIRED", AgcTaskState::TARGET_ACQUIRED},
    {"GROUND_APPROACH", AgcTaskState::GROUND_APPROACH},
    {"TRACKING_SUCCESS", AgcTaskState::TRACKING_SUCCESS},
    {"MISSION_FAILED", AgcTaskState::MISSION_FAILED},
    {"ABORTED", AgcTaskState::ABORTED},
    {"INTERCEPT_CONFIRMED", AgcTaskState::INTERCEPT_CONFIRMED},
    {"INFRA_FAILURE", AgcTaskState::INFRA_FAILURE},
  };
  for (const auto & e : expects) {
    const std::string needle = std::string("uint8 ") + e.name + "=" +
      std::to_string(static_cast<int>(e.value));
    EXPECT_NE(text.find(needle), std::string::npos)
      << "头文件的 " << e.name << "=" << static_cast<int>(e.value)
      << " 与 .msg 定义不一致（应为 `" << needle << "`）";
  }
}

// ---------------------------------------------------------------- 状态分类

TEST(TaskFsm, ActiveAndTerminalPartition)
{
  // active 与 terminal 必须**互斥且完备**：漏一个终态会让迟到 abort 覆写结果。
  EXPECT_TRUE(TaskFsm::is_active(AgcTaskState::AIR_SEARCH));
  EXPECT_TRUE(TaskFsm::is_active(AgcTaskState::TARGET_ACQUIRED));
  EXPECT_TRUE(TaskFsm::is_active(AgcTaskState::GROUND_APPROACH));
  EXPECT_FALSE(TaskFsm::is_active(AgcTaskState::IDLE));
  EXPECT_FALSE(TaskFsm::is_active(AgcTaskState::TRACKING_SUCCESS));

  EXPECT_TRUE(TaskFsm::is_terminal(AgcTaskState::TRACKING_SUCCESS));
  EXPECT_TRUE(TaskFsm::is_terminal(AgcTaskState::INTERCEPT_CONFIRMED));
  EXPECT_TRUE(TaskFsm::is_terminal(AgcTaskState::MISSION_FAILED));
  EXPECT_TRUE(TaskFsm::is_terminal(AgcTaskState::ABORTED));
  EXPECT_TRUE(TaskFsm::is_terminal(AgcTaskState::INFRA_FAILURE));
  EXPECT_FALSE(TaskFsm::is_terminal(AgcTaskState::GROUND_APPROACH));
  EXPECT_FALSE(TaskFsm::is_terminal(AgcTaskState::IDLE));

  for (uint8_t s = 0; s < 16; ++s) {
    EXPECT_FALSE(TaskFsm::is_active(s) && TaskFsm::is_terminal(s))
      << "state=" << static_cast<int>(s) << " 同时被判为 active 与 terminal";
  }
}

TEST(TaskFsm, EnteringNonActiveStateResetsDwell)
{
  // 进终态必须清 dwell，否则下一个 episode 会带着上一段的计时。
  auto fsm = to_ground_approach();
  fsm.step(fresh_inputs(10.0));
  ASSERT_TRUE(fsm.dwell_active());
  fsm.force_state(AgcTaskState::TRACKING_SUCCESS);
  EXPECT_FALSE(fsm.dwell_active());
}

int main(int argc, char ** argv)
{
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
