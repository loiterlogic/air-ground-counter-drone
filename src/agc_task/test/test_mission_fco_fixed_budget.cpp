// test_mission_fco_fixed_budget.cpp —— ADR-0099 固定预算任务 FCO 的确定性手算测试。
//
// 每个案例先写手算期望，再断言积分、覆盖账、null/识别界与有效性，不只断言字段存在。

#include <cmath>
#include <string>

#include <gtest/gtest.h>

#include "agc_task/mission_fco_fixed_budget.hpp"

namespace
{

class Fixture
{
public:
  agc_task::MissionFcoFixedBudget recorder;

  void init(double budget = 60.0, double vis_age = 0.5, double env_age = 1.0,
    double max_gap = 1.0, int episode = 7, bool episode_available = true)
  {
    agc_task::MissionFcoConfig cfg;
    cfg.budget_s = budget;
    cfg.visibility_max_age_s = vis_age;
    cfg.envelope_max_age_s = env_age;
    cfg.max_gap_s = max_gap;
    recorder.configure(cfg);
    if (episode_available) {recorder.onEpisode(episode, 0.0);}
  }

  void state(
    bool ground, bool terminal, const std::string & name, const std::string & reason,
    double t, bool stamp_valid = true)
  {
    recorder.onState(ground, terminal, name, reason, t, stamp_valid, t);
  }

  void idle(double t) {state(false, false, "AIR_SEARCH", "idle", t);}
  void ground(double t) {state(true, false, "GROUND_APPROACH", "ground_approach", t);}
  void terminal(const std::string & name, const std::string & reason, double t)
  {
    state(false, true, name, reason, t);
  }

  void tick(double t, bool visible = true, bool envelope = true, double stamp = -1.0)
  {
    if (stamp < 0.0) {stamp = t;}
    recorder.onTick({t, true, visible, stamp, true, envelope, t});
  }

  const agc_task::MissionFcoRecord & rec(size_t i = 0) const
  {
    return recorder.records().at(i);
  }
};

void expectCoverage(const agc_task::MissionFcoRecord & r)
{
  EXPECT_NEAR(r.known_preterminal_s + r.missing_preterminal_s + r.post_terminal_budget_s,
    r.budget_s, 1e-6);
  EXPECT_NEAR(r.coverage_residual_s, 0.0, 1e-6);
}

void expectLedgerCoverage(const agc_task::MissionFcoRecord & r)
{
  double known = 0.0;
  double missing = 0.0;
  double post = 0.0;
  double fco = 0.0;
  double cursor = r.t0_s;
  for (const auto & iv : r.intervals) {
    EXPECT_NEAR(iv.start_s, cursor, 1e-9);
    ASSERT_GE(iv.end_s, iv.start_s);
    if (iv.kind == "known") {
      known += iv.end_s - iv.start_s;
      if (iv.fco) {fco += iv.end_s - iv.start_s;}
    } else if (iv.kind == "missing") {
      missing += iv.end_s - iv.start_s;
    } else if (iv.kind == "post_terminal") {
      post += iv.end_s - iv.start_s;
    }
    cursor = iv.end_s;
  }
  if (!r.intervals.empty()) {
    EXPECT_NEAR(cursor, r.t0_s + r.budget_s, 1e-6);
  }
  EXPECT_NEAR(known, r.known_preterminal_s, 1e-6);
  EXPECT_NEAR(missing, r.missing_preterminal_s, 1e-6);
  EXPECT_NEAR(post, r.post_terminal_budget_s, 1e-6);
  EXPECT_NEAR(fco, r.fco_exposure_s, 1e-6);
}

}  // namespace

TEST(MissionFcoFixedBudget, EarlySuccessPostTerminalParking)
{
  Fixture f;
  f.init();
  f.idle(0.0);
  f.ground(0.0);
  f.tick(0.0);
  for (int i = 1; i <= 100; ++i) {f.tick(i * 0.1);}
  f.terminal("INTERCEPT_CONFIRMED", "CAPTURE_NET", 10.0);

  const auto & r = f.rec();
  EXPECT_TRUE(r.t0_verified);
  EXPECT_NEAR(r.t0_s, 0.0, 1e-9);
  EXPECT_NEAR(r.known_preterminal_s, 10.0, 1e-6);
  EXPECT_NEAR(r.fco_exposure_s, 10.0, 1e-6);
  EXPECT_NEAR(r.post_terminal_budget_s, 50.0, 1e-6);
  EXPECT_NEAR(r.missing_preterminal_s, 0.0, 1e-9);
  EXPECT_TRUE(r.terminal_within_budget);
  EXPECT_TRUE(r.point_valid);
  EXPECT_TRUE(r.bounds_valid);
  EXPECT_NEAR(r.mission_fco_fraction, 1.0 / 6.0, 1e-6);
  EXPECT_NEAR(r.identification_lower, 1.0 / 6.0, 1e-6);
  EXPECT_NEAR(r.identification_upper, 1.0 / 6.0, 1e-6);
  expectCoverage(r);
  expectLedgerCoverage(r);
  ASSERT_EQ(f.recorder.records().size(), 1u);
  ASSERT_EQ(r.intervals.size(), 2u);
  EXPECT_EQ(r.intervals[0].kind, "known");
  EXPECT_TRUE(r.intervals[0].fco);
  EXPECT_EQ(r.intervals[1].kind, "post_terminal");
}

TEST(MissionFcoFixedBudget, TerminalAfterBudgetKeepsFixedWindow)
{
  Fixture f;
  f.init();
  f.idle(0.0);
  f.ground(0.0);
  for (int i = 0; i <= 700; ++i) {f.tick(i * 0.1);}
  f.terminal("MISSION_FAILED", "TIMEOUT", 70.0);

  ASSERT_EQ(f.recorder.records().size(), 1u);
  const auto & r = f.rec();
  EXPECT_TRUE(r.measurement_closed);
  EXPECT_FALSE(r.terminal_within_budget);
  EXPECT_FALSE(r.terminal_unknown_at_budget);
  EXPECT_EQ(r.terminal_state, "MISSION_FAILED");
  EXPECT_NEAR(r.known_preterminal_s, 60.0, 1e-6);
  EXPECT_NEAR(r.fco_exposure_s, 60.0, 1e-6);
  EXPECT_NEAR(r.post_terminal_budget_s, 0.0, 1e-9);
  EXPECT_TRUE(r.point_valid);
  EXPECT_NEAR(r.mission_fco_fraction, 1.0, 1e-6);
  expectCoverage(r);
  expectLedgerCoverage(r);
}

TEST(MissionFcoFixedBudget, TimeoutWithoutTerminalClosesAtBudget)
{
  Fixture f;
  f.init();
  f.idle(0.0);
  f.ground(0.0);
  for (int i = 0; i <= 1200; ++i) {f.tick(i * 0.1);}

  const auto & r = f.rec();
  EXPECT_TRUE(r.measurement_closed);
  EXPECT_FALSE(r.terminal_seen);
  EXPECT_TRUE(r.terminal_unknown_at_budget);
  EXPECT_NEAR(r.known_preterminal_s, 60.0, 1e-6);
  EXPECT_NEAR(r.fco_exposure_s, 60.0, 1e-6);
  EXPECT_TRUE(r.point_valid);
  EXPECT_NEAR(r.mission_fco_fraction, 1.0, 1e-6);
  expectCoverage(r);
  expectLedgerCoverage(r);
}

TEST(MissionFcoFixedBudget, TerminalExactlyAtBudget)
{
  Fixture f;
  f.init();
  f.idle(0.0);
  f.ground(0.0);
  for (int i = 0; i <= 599; ++i) {f.tick(i * 0.1);}
  f.terminal("TRACKING_SUCCESS", "tracking", 60.0);

  const auto & r = f.rec();
  EXPECT_TRUE(r.terminal_within_budget);
  EXPECT_NEAR(r.known_preterminal_s, 60.0, 1e-6);
  EXPECT_NEAR(r.post_terminal_budget_s, 0.0, 1e-9);
  EXPECT_TRUE(r.point_valid);
  EXPECT_NEAR(r.mission_fco_fraction, 1.0, 1e-6);
  expectCoverage(r);
  expectLedgerCoverage(r);
}

TEST(MissionFcoFixedBudget, TargetFreshnessExpiryTruncatesFco)
{
  Fixture f;
  f.init(60.0, 0.5, 1.0, 1.0);
  f.idle(0.0);
  f.ground(0.0);
  // 目标源时刻固定在 0；可见到 0.5 s 为止；包络每拍刷新。
  f.tick(0.1, true, true, 0.0);
  for (int i = 2; i <= 20; ++i) {f.tick(i * 0.1, true, true, 0.0);}
  f.terminal("INTERCEPT_CONFIRMED", "CAPTURE_NET", 2.0);

  const auto & r = f.rec();
  EXPECT_NEAR(r.known_preterminal_s, 2.0, 1e-6);
  EXPECT_NEAR(r.fco_exposure_s, 0.5, 1e-6);
  EXPECT_NEAR(r.post_terminal_budget_s, 58.0, 1e-6);
  EXPECT_TRUE(r.point_valid);
  EXPECT_NEAR(r.mission_fco_fraction, 0.5 / 60.0, 1e-6);
  expectCoverage(r);
  expectLedgerCoverage(r);
}

TEST(MissionFcoFixedBudget, LoggerGapProducesMissingAndBounds)
{
  Fixture f;
  f.init();
  f.idle(0.0);
  f.ground(0.0);
  for (int i = 0; i <= 20; ++i) {f.tick(i * 0.1);}
  f.tick(10.0);
  f.terminal("INTERCEPT_CONFIRMED", "CAPTURE_NET", 10.0);

  const auto & r = f.rec();
  EXPECT_NEAR(r.known_preterminal_s, 2.0, 1e-6);
  EXPECT_NEAR(r.missing_preterminal_s, 8.0, 1e-6);
  EXPECT_NEAR(r.fco_exposure_s, 2.0, 1e-6);
  EXPECT_NEAR(r.post_terminal_budget_s, 50.0, 1e-6);
  EXPECT_FALSE(r.point_valid);
  EXPECT_TRUE(r.bounds_valid);
  EXPECT_NEAR(r.identification_lower, 2.0 / 60.0, 1e-6);
  EXPECT_NEAR(r.identification_upper, 10.0 / 60.0, 1e-6);
  EXPECT_TRUE(std::isnan(r.mission_fco_fraction));
  expectCoverage(r);
  expectLedgerCoverage(r);
}

TEST(MissionFcoFixedBudget, FinalizeBeforeBudgetMarksMissing)
{
  Fixture f;
  f.init();
  f.idle(0.0);
  f.ground(0.0);
  for (int i = 0; i <= 100; ++i) {f.tick(i * 0.1);}
  f.recorder.finalize(10.0);

  const auto & r = f.rec();
  EXPECT_TRUE(r.stopped_early);
  EXPECT_NEAR(r.known_preterminal_s, 10.0, 1e-6);
  EXPECT_NEAR(r.missing_preterminal_s, 50.0, 1e-6);
  EXPECT_NEAR(r.post_terminal_budget_s, 0.0, 1e-9);
  EXPECT_FALSE(r.point_valid);
  EXPECT_TRUE(r.bounds_valid);
  EXPECT_NEAR(r.identification_lower, 10.0 / 60.0, 1e-6);
  EXPECT_NEAR(r.identification_upper, 1.0, 1e-6);
  expectCoverage(r);
  expectLedgerCoverage(r);
}

TEST(MissionFcoFixedBudget, MissingT0IsNotComputableAndRepeatedTerminalIgnored)
{
  Fixture f;
  f.init();
  f.terminal("INTERCEPT_CONFIRMED", "CAPTURE_NET", 5.0);
  f.terminal("INTERCEPT_CONFIRMED", "CAPTURE_NET", 6.0);

  ASSERT_EQ(f.recorder.records().size(), 1u);
  const auto & r = f.rec();
  EXPECT_FALSE(r.t0_seen);
  EXPECT_TRUE(r.terminal_seen);
  EXPECT_FALSE(r.point_valid);
  EXPECT_FALSE(r.bounds_valid);
  EXPECT_TRUE(std::isnan(r.mission_fco_fraction));
  ASSERT_FALSE(r.unknown_reasons.empty());
}

TEST(MissionFcoFixedBudget, EpisodeResetDoesNotMixMissions)
{
  Fixture f;
  f.init(60.0, 0.5, 1.0, 1.0, 1);
  f.idle(0.0);
  f.ground(0.0);
  for (int i = 0; i <= 50; ++i) {f.tick(i * 0.1);}
  f.recorder.onEpisode(2, 5.0);
  f.idle(5.5);
  f.ground(6.0);
  f.tick(6.0);
  for (int i = 1; i <= 40; ++i) {f.tick(6.0 + i * 0.1);}
  f.terminal("INTERCEPT_CONFIRMED", "CAPTURE_NET", 10.0);

  ASSERT_EQ(f.recorder.records().size(), 2u);
  const auto & first = f.rec(0);
  EXPECT_TRUE(first.episode_mismatch);
  EXPECT_FALSE(first.point_valid);
  EXPECT_FALSE(first.bounds_valid);
  EXPECT_NEAR(first.known_preterminal_s, 5.0, 1e-6);
  EXPECT_NEAR(first.missing_preterminal_s, 55.0, 1e-6);
  expectLedgerCoverage(first);

  const auto & second = f.rec(1);
  EXPECT_EQ(second.episode_id, 2);
  EXPECT_TRUE(second.t0_verified);
  EXPECT_NEAR(second.t0_s, 6.0, 1e-9);
  EXPECT_NEAR(second.known_preterminal_s, 4.0, 1e-6);
  EXPECT_NEAR(second.fco_exposure_s, 4.0, 1e-6);
  EXPECT_NEAR(second.post_terminal_budget_s, 56.0, 1e-6);
  EXPECT_TRUE(second.point_valid);
  EXPECT_NEAR(second.mission_fco_fraction, 4.0 / 60.0, 1e-6);
  expectCoverage(second);
  expectLedgerCoverage(second);
}

TEST(MissionFcoFixedBudget, ClockRegressionInvalidatesButKeepsLedger)
{
  Fixture f;
  f.init();
  f.idle(0.0);
  f.ground(0.0);
  for (int i = 0; i <= 20; ++i) {f.tick(i * 0.1);}
  f.tick(1.5);   // 时钟回退
  f.tick(3.0);
  f.terminal("INTERCEPT_CONFIRMED", "CAPTURE_NET", 3.0);

  const auto & r = f.rec();
  EXPECT_TRUE(r.clock_regression);
  EXPECT_FALSE(r.point_valid);
  EXPECT_FALSE(r.bounds_valid);
  EXPECT_NEAR(r.known_preterminal_s, 3.0, 1e-6);
  EXPECT_NEAR(r.post_terminal_budget_s, 57.0, 1e-6);
  expectCoverage(r);
  EXPECT_TRUE(std::isnan(r.mission_fco_fraction));
}

TEST(MissionFcoFixedBudget, ReceiptTimeBasisWhenSourceStampMissing)
{
  Fixture f;
  f.init();
  f.state(false, false, "AIR_SEARCH", "idle", 1.0, false);
  f.state(true, false, "GROUND_APPROACH", "ground_approach", 1.0, false);
  for (int i = 0; i <= 40; ++i) {f.tick(1.0 + i * 0.1);}
  f.state(false, true, "ABORTED", "external_abort", 5.0, false);

  const auto & r = f.rec();
  EXPECT_EQ(r.t0_basis, "receipt");
  EXPECT_FALSE(r.t0_source_stamp_valid);
  EXPECT_NEAR(r.t0_s, 1.0, 1e-9);
  EXPECT_EQ(r.terminal_state, "ABORTED");
  EXPECT_TRUE(r.terminal_within_budget);
  EXPECT_NEAR(r.known_preterminal_s, 4.0, 1e-6);
  EXPECT_NEAR(r.post_terminal_budget_s, 56.0, 1e-6);
  EXPECT_TRUE(r.point_valid);
  EXPECT_NEAR(r.mission_fco_fraction, 4.0 / 60.0, 1e-6);
  expectCoverage(r);
  expectLedgerCoverage(r);
}

TEST(MissionFcoFixedBudget, ConfigRejectsNonPositiveBudget)
{
  Fixture f;
  f.init(0.0);
  EXPECT_FALSE(f.recorder.configValid());
}
