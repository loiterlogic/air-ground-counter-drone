// mission_fco_json.hpp —— ADR-0021 `mission_fco_fixed_budget_v1` 的证据 JSON 序列化
//
// 从 `run_logger.cpp` 拆出（原文件 1,664 行）。本单元只做**序列化**：
// 输入是 `MissionFcoFixedBudget` 的配置与记录，输出是 summary / ledger 里的 JSON 片段。
// **不持有状态**——没有成员、没有缓存，纯函数（`mission_fco_fixed_budget.hpp` 仍是
// 积分器与记录的唯一真源，本文件不复制任何字段语义）。
//
// 口径与判据见 `docs/adr/0021-mission-fco-fixed-budget.md#top`；本文件只实现，不复述条文。

#ifndef AGC_TASK_MISSION_FCO_JSON_HPP_
#define AGC_TASK_MISSION_FCO_JSON_HPP_

#include <limits>
#include <sstream>
#include <string>

#include "agc_task/json_value.hpp"
#include "agc_task/mission_fco_fixed_budget.hpp"

namespace agc_task
{

using agc_task::jsonBool;
using agc_task::jsonNumber;
using agc_task::jsonString;

/// 配置块（`config` 字段）。
inline std::string missionFcoConfigJson(const MissionFcoConfig & cfg, bool config_valid)
{
  std::ostringstream os;
  os << "{\"budget_s\": " << jsonNumber(cfg.budget_s)
     << ", \"visibility_max_age_s\": " << jsonNumber(cfg.visibility_max_age_s)
     << ", \"envelope_max_age_s\": " << jsonNumber(cfg.envelope_max_age_s)
     << ", \"max_gap_s\": " << jsonNumber(cfg.max_gap_s)
     << ", \"config_valid\": " << jsonBool(config_valid) << "}";
  return os.str();
}

/// 单条 mission 记录（`with_intervals` = true 时附带区间账）。
inline std::string missionFcoRecordJson(const MissionFcoRecord & r, bool with_intervals)
{
  std::ostringstream os;
  os << "{\"episode_id\": " << r.episode_id
     << ", \"episode_available\": " << jsonBool(r.episode_available)
     << ", \"episode_assigned_late\": " << jsonBool(r.episode_assigned_late)
     << ", \"t0_seen\": " << jsonBool(r.t0_seen)
     << ", \"t0_verified\": " << jsonBool(r.t0_verified)
     << ", \"t0_backfilled\": " << jsonBool(r.t0_backfilled)
     << ", \"t0_s\": " << jsonNumber(r.t0_s)
     << ", \"t0_source_s\": " << jsonNumber(r.t0_source_s)
     << ", \"t0_receipt_s\": " << jsonNumber(r.t0_receipt_s)
     << ", \"t0_source_stamp_valid\": " << jsonBool(r.t0_source_stamp_valid)
     << ", \"t0_basis\": " << jsonString(r.t0_basis)
     << ", \"terminal_seen\": " << jsonBool(r.terminal_seen)
     << ", \"terminal_within_budget\": " << jsonBool(r.terminal_within_budget)
     << ", \"terminal_unknown_at_budget\": " << jsonBool(r.terminal_unknown_at_budget)
     << ", \"duplicate_terminal\": " << jsonBool(r.duplicate_terminal)
     << ", \"terminal_s\": " << jsonNumber(r.terminal_s)
     << ", \"terminal_source_s\": " << jsonNumber(r.terminal_source_s)
     << ", \"terminal_receipt_s\": " << jsonNumber(r.terminal_receipt_s)
     << ", \"terminal_source_stamp_valid\": " << jsonBool(r.terminal_source_stamp_valid)
     << ", \"terminal_state\": " << jsonString(r.terminal_state)
     << ", \"terminal_reason\": " << jsonString(r.terminal_reason)
     << ", \"measurement_closed\": " << jsonBool(r.measurement_closed)
     << ", \"stopped_early\": " << jsonBool(r.stopped_early)
     << ", \"episode_mismatch\": " << jsonBool(r.episode_mismatch)
     << ", \"clock_regression\": " << jsonBool(r.clock_regression)
     << ", \"bounds_valid\": " << jsonBool(r.bounds_valid)
     << ", \"point_valid\": " << jsonBool(r.point_valid)
     << ", \"budget_s\": " << jsonNumber(r.budget_s)
     << ", \"known_preterminal_s\": " << jsonNumber(r.known_preterminal_s)
     << ", \"missing_preterminal_s\": " << jsonNumber(r.missing_preterminal_s)
     << ", \"post_terminal_budget_s\": " << jsonNumber(r.post_terminal_budget_s)
     << ", \"fco_exposure_s\": " << jsonNumber(r.fco_exposure_s)
     << ", \"mission_fco_fraction\": " << jsonNumber(r.mission_fco_fraction)
     << ", \"identification_lower\": " << jsonNumber(r.identification_lower)
     << ", \"identification_upper\": " << jsonNumber(r.identification_upper)
     << ", \"coverage_residual_s\": " << jsonNumber(r.coverage_residual_s)
     << ", \"unknown_reasons\": [";
  for (size_t i = 0; i < r.unknown_reasons.size(); ++i) {
    if (i > 0) {os << ", ";}
    os << jsonString(r.unknown_reasons[i]);
  }
  os << "]";
  if (with_intervals) {
    os << ", \"intervals\": [";
    for (size_t i = 0; i < r.intervals.size(); ++i) {
      if (i > 0) {os << ", ";}
      const auto & iv = r.intervals[i];
      os << "{\"start_s\": " << jsonNumber(iv.start_s)
         << ", \"end_s\": " << jsonNumber(iv.end_s)
         << ", \"fco\": " << jsonBool(iv.fco)
         << ", \"kind\": " << jsonString(iv.kind)
         << ", \"reason\": " << jsonString(iv.reason) << "}";
    }
    os << "]";
  }
  os << "}";
  return os.str();
}

/// `summary.json` 的 `mission_fco_fixed_budget_v1` 块。
inline std::string missionFcoSummaryJson(
  const MissionFcoFixedBudget & fco, const MissionFcoConfig & cfg, bool config_valid)
{
  const auto & recs = fco.records();
  bool single_valid = false;
  double single = std::numeric_limits<double>::quiet_NaN();
  if (recs.size() == 1 && recs.front().point_valid) {
    single_valid = true;
    single = recs.front().mission_fco_fraction;
  }
  std::ostringstream os;
  os << "{\"definition_version\": \"mission_fco_fixed_budget_v1\""
     << ", \"budget_s\": " << jsonNumber(cfg.budget_s)
     << ", \"config\": " << missionFcoConfigJson(cfg, config_valid)
     << ", \"mission_count\": " << recs.size()
     << ", \"single_mission_fraction\": " << (single_valid ? jsonNumber(single) : "null")
     << ", \"missions\": [";
  for (size_t i = 0; i < recs.size(); ++i) {
    if (i > 0) {os << ", ";}
    os << missionFcoRecordJson(recs[i], false);
  }
  os << "], \"ledger_file\": \"metrics/mission_fco_intervals.json\""
     << ", \"note\": \"ADR-0021：T=60 仿真秒固定任务预算；每 mission 独立积分，不合并跨回合比例；"
        "终态后预算贡献 0；存在未知区间时点估计 null，保留 [known/T,(known+missing)/T] 识别界；"
        "不把 ticks/window_s 当时间积分；旧 visibility_metrics 与 episode_window_metrics 原语义未改\"}";
  return os.str();
}

/// 区间账（`metrics/mission_fco_intervals.json` 全文）。
inline std::string missionFcoLedgerJson(
  const MissionFcoFixedBudget & fco, const MissionFcoConfig & cfg, bool config_valid)
{
  const auto & recs = fco.records();
  std::ostringstream os;
  os << "{\"definition_version\": \"mission_fco_fixed_budget_v1\""
     << ", \"budget_s\": " << jsonNumber(cfg.budget_s)
     << ", \"config\": " << missionFcoConfigJson(cfg, config_valid)
     << ", \"missions\": [";
  for (size_t i = 0; i < recs.size(); ++i) {
    if (i > 0) {os << ", ";}
    os << missionFcoRecordJson(recs[i], true);
  }
  os << "]}\n";
  return os.str();
}

}  // namespace agc_task

#endif  // AGC_TASK_MISSION_FCO_JSON_HPP_
