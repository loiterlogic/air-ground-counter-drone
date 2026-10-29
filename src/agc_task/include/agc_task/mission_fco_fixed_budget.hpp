// mission_fco_fixed_budget —— ADR-0099 `mission_fco_fixed_budget_v1` 的确定性积分器。
//
// 只做固定 60 仿真秒预算内的任务内 FCO 时间积分与覆盖账；不读写 ROS、不改旧口径。
// 单位：秒（仿真时间）；跨回合不合并比例。
#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>
#include <string>
#include <vector>

namespace agc_task
{

struct MissionFcoConfig
{
  double budget_s{60.0};
  double visibility_max_age_s{0.5};
  double envelope_max_age_s{1.0};
  double max_gap_s{1.0};
};

struct MissionFcoTick
{
  double t_s{0.0};
  bool target_seen{false};
  bool target_present{false};
  double target_stamp_s{0.0};
  bool envelope_seen{false};
  bool envelope_in{false};
  double envelope_rx_s{0.0};
};

struct MissionFcoInterval
{
  double start_s{0.0};
  double end_s{0.0};
  bool fco{false};
  std::string kind;    // known | missing | post_terminal
  std::string reason;
};

struct MissionFcoRecord
{
  int episode_id{-1};
  bool episode_available{false};
  bool episode_assigned_late{false};
  bool t0_seen{false};
  bool t0_verified{false};
  bool t0_backfilled{false};
  double t0_s{0.0};
  double t0_source_s{0.0};
  double t0_receipt_s{0.0};
  bool t0_source_stamp_valid{false};
  std::string t0_basis{"none"};
  bool terminal_seen{false};
  bool terminal_within_budget{false};
  bool terminal_unknown_at_budget{false};
  bool duplicate_terminal{false};
  double terminal_s{0.0};
  double terminal_source_s{0.0};
  double terminal_receipt_s{0.0};
  bool terminal_source_stamp_valid{false};
  std::string terminal_state;
  std::string terminal_reason;
  bool measurement_closed{false};
  bool stopped_early{false};
  bool episode_mismatch{false};
  bool clock_regression{false};
  bool bounds_valid{false};
  bool point_valid{false};
  double budget_s{60.0};
  double known_preterminal_s{0.0};
  double missing_preterminal_s{0.0};
  double post_terminal_budget_s{0.0};
  double fco_exposure_s{0.0};
  double mission_fco_fraction{std::numeric_limits<double>::quiet_NaN()};
  double identification_lower{std::numeric_limits<double>::quiet_NaN()};
  double identification_upper{std::numeric_limits<double>::quiet_NaN()};
  double coverage_residual_s{0.0};
  std::vector<std::string> unknown_reasons;
  std::vector<MissionFcoInterval> intervals;
};

class MissionFcoFixedBudget
{
public:
  MissionFcoFixedBudget() = default;

  void configure(const MissionFcoConfig & cfg)
  {
    cfg_ = cfg;
    cfg_valid_ = cfg.budget_s > 0.0 && cfg.visibility_max_age_s >= 0.0 &&
      cfg.envelope_max_age_s >= 0.0 && cfg.max_gap_s > 0.0;
  }

  const MissionFcoConfig & config() const {return cfg_;}
  bool configValid() const {return cfg_valid_;}
  const std::vector<MissionFcoRecord> & records() const {return records_;}
  bool hasActive() const {return active_ >= 0;}

  void onEpisode(int episode_id, double receipt_s)
  {
    const bool changed = have_episode_ && episode_id != current_episode_;
    current_episode_ = episode_id;
    have_episode_ = true;
    if (active_ < 0) {
      if (changed && last_mission_ >= 0) {
        // 新 episode 已开始：旧 mission 的迟到终态不得改写旧记录或新建伪 mission。
        last_mission_ = -1;
        ignore_terminal_ = true;
      }
      return;
    }
    MissionFcoRecord & r = records_[active_];
    if (!r.episode_available) {
      r.episode_id = episode_id;
      r.episode_available = true;
      r.episode_assigned_late = true;
      return;
    }
    if (r.episode_id != episode_id && !r.measurement_closed) {
      r.episode_mismatch = true;
      r.unknown_reasons.push_back("episode_changed_mid_mission");
      integrateTo(r, receipt_s);
      close(r);
      last_mission_ = -1;
      ignore_terminal_ = true;
      resetActiveState();
    }
  }

  void onState(
    bool is_ground_approach, bool is_terminal, const std::string & state_name,
    const std::string & reason, double source_s, bool source_stamp_valid,
    double receipt_s)
  {
    const double event_s = source_stamp_valid ? source_s : receipt_s;

    if (is_ground_approach && !prev_is_ground_) {
      terminal_state_latched_ = false;
      if (active_ >= 0) {
        MissionFcoRecord & r = records_[active_];
        if (!r.measurement_closed) {r.unknown_reasons.push_back("duplicate_ground_approach");}
      } else {
        MissionFcoRecord r;
        r.episode_id = have_episode_ ? current_episode_ : -1;
        r.episode_available = have_episode_;
        r.t0_seen = true;
        r.t0_verified = prev_seen_;
        r.t0_source_s = source_s;
        r.t0_receipt_s = receipt_s;
        r.t0_source_stamp_valid = source_stamp_valid;
        r.t0_basis = source_stamp_valid ? "source_stamp" : "receipt";
        r.t0_s = event_s;
        r.budget_s = cfg_.budget_s;
        last_mission_ = -1;
        ignore_terminal_ = false;
        records_.push_back(r);
        active_ = static_cast<int>(records_.size()) - 1;
        last_mission_ = active_;
        resetTickState();
      }
    }

    if (is_terminal) {
      if (active_ < 0 && terminal_state_latched_) {
        // task_manager 的状态定时器会重复发布终态；同一终态只记一次。
      } else if (active_ >= 0) {
        MissionFcoRecord & r = records_[active_];
        if (r.terminal_seen) {
          r.duplicate_terminal = true;
          r.unknown_reasons.push_back("duplicate_terminal_state");
        } else {
          terminal_state_latched_ = true;
          r.terminal_seen = true;
          r.terminal_s = event_s;
          r.terminal_source_s = source_s;
          r.terminal_receipt_s = receipt_s;
          r.terminal_source_stamp_valid = source_stamp_valid;
          r.terminal_state = state_name;
          r.terminal_reason = reason;
          r.terminal_within_budget = r.t0_seen && r.terminal_s >= r.t0_s &&
            r.terminal_s <= r.t0_s + cfg_.budget_s;
          if (r.terminal_s < r.t0_s) {r.unknown_reasons.push_back("terminal_before_t0");}
          if (r.terminal_within_budget) {
            integrateTo(r, r.terminal_s);
            close(r);
            resetActiveState();
          } else if (r.terminal_s > r.t0_s + cfg_.budget_s && !r.measurement_closed) {
            integrateTo(r, r.t0_s + cfg_.budget_s);
            close(r);
            resetActiveState();
          }
        }
      } else if (last_mission_ >= 0 && !records_[last_mission_].terminal_seen &&
        !ignore_terminal_)
      {
        // 测量窗已在 T 关闭（超时/长回合）后到达的终态：补写同一 mission 记录，
        // 不新建伪 mission；若终态仍在预算内，按源时刻回裁并补记 post-terminal。
        terminal_state_latched_ = true;
        MissionFcoRecord & r = records_[last_mission_];
        r.terminal_seen = true;
        r.terminal_s = event_s;
        r.terminal_source_s = source_s;
        r.terminal_receipt_s = receipt_s;
        r.terminal_source_stamp_valid = source_stamp_valid;
        r.terminal_state = state_name;
        r.terminal_reason = reason;
        const double budget_end = r.t0_s + cfg_.budget_s;
        if (r.terminal_s >= r.t0_s && r.terminal_s <= budget_end) {
          trimTo(r, r.terminal_s);
          addPostTerminal(r, r.terminal_s, budget_end);
          r.post_terminal_budget_s = std::max(0.0, r.post_terminal_budget_s);
        }
        r.terminal_within_budget = r.terminal_s >= r.t0_s && r.terminal_s <= budget_end;
        r.terminal_unknown_at_budget = false;
        r.stopped_early = false;
        computeOutcome(r);
      } else if (!ignore_terminal_) {
        terminal_state_latched_ = true;
        MissionFcoRecord r;
        r.episode_id = have_episode_ ? current_episode_ : -1;
        r.episode_available = have_episode_;
        r.terminal_seen = true;
        r.terminal_s = event_s;
        r.terminal_source_s = source_s;
        r.terminal_receipt_s = receipt_s;
        r.terminal_source_stamp_valid = source_stamp_valid;
        r.terminal_state = state_name;
        r.terminal_reason = reason;
        r.unknown_reasons.push_back("missing_t0");
        r.measurement_closed = true;
        r.point_valid = false;
        r.bounds_valid = false;
        records_.push_back(r);
      }
    }

    prev_seen_ = true;
    prev_is_ground_ = is_ground_approach;
  }

  void onTick(const MissionFcoTick & tick)
  {
    if (active_ < 0) {return;}
    MissionFcoRecord & r = records_[active_];
    if (!r.t0_seen || r.measurement_closed) {return;}
    if (tick.t_s < r.t0_s) {return;}

    if (!have_last_) {
      const double start = coveredTo(r);
      if (tick.t_s < start - 1e-9) {
        r.clock_regression = true;
        addReason(r, "clock_regression");
        // 保持 have_last_=false：下一拍仍以 coveredTo 为界，避免与已计入区间重叠。
        return;
      }
      const double gap = tick.t_s - start;
      if (gap > 1e-9) {
        if (gap > cfg_.max_gap_s) {
          addMissing(r, start, tick.t_s,
            start <= r.t0_s + 1e-9 ? "logger_not_ready_at_t0" : "logger_gap");
        } else {
          const Pred p = predicate(tick, tick.t_s);
          integrateWithPredicate(r, start, tick.t_s, p);
          if (start <= r.t0_s + 1e-9) {r.t0_backfilled = true;}
        }
      }
      setLast(tick, tick.t_s);
    } else {
      if (tick.t_s + 1e-9 < last_t_) {
        r.clock_regression = true;
        addReason(r, "clock_regression");
        have_last_ = false;
        // 不把 last_t_ 改到回退时刻；下一拍以 coveredTo 为界续算，避免重叠。
        return;
      }
      const double seg_end = tick.t_s;
      if (seg_end > last_t_) {
        if (seg_end - last_t_ > cfg_.max_gap_s) {
          addMissing(r, last_t_, seg_end, "logger_gap");
        } else {
          integrateWithPredicate(r, last_t_, seg_end, last_pred_, last_expiry_);
        }
      }
      setLast(tick, tick.t_s);
    }

    if (tick.t_s >= r.t0_s + cfg_.budget_s - 1e-9) {
      close(r);
      resetActiveState();
    }
  }

  void finalize(double end_s)
  {
    if (active_ < 0) {return;}
    MissionFcoRecord & r = records_[active_];
    if (!r.t0_seen || r.measurement_closed) {return;}
    integrateTo(r, std::min(end_s, r.t0_s + cfg_.budget_s));
    close(r);
    resetActiveState();
  }

private:
  struct Pred
  {
    bool fco{false};
    double expiry{0.0};
    bool visible{false};
    bool envelope{false};
  };

  Pred predicate(const MissionFcoTick & tick, double t) const
  {
    const bool target_ok = tick.target_seen && tick.target_present &&
      tick.target_stamp_s <= t + 1e-9 &&
      (t - tick.target_stamp_s) <= cfg_.visibility_max_age_s;
    const bool env_ok = tick.envelope_seen && tick.envelope_in &&
      tick.envelope_rx_s <= t + 1e-9 &&
      (t - tick.envelope_rx_s) <= cfg_.envelope_max_age_s;
    Pred p;
    p.visible = target_ok;
    p.envelope = env_ok;
    p.fco = target_ok && env_ok;
    if (p.fco) {
      const double target_expiry = tick.target_stamp_s + cfg_.visibility_max_age_s;
      const double env_expiry = tick.envelope_rx_s + cfg_.envelope_max_age_s;
      p.expiry = std::min(target_expiry, env_expiry);
    } else {
      p.expiry = t;
    }
    return p;
  }

  void setLast(const MissionFcoTick & tick, double t)
  {
    last_pred_ = predicate(tick, t);
    last_expiry_ = last_pred_.expiry;
    last_t_ = t;
    have_last_ = true;
  }

  void integrateWithPredicate(
    MissionFcoRecord & r, double start, double end, const Pred & p)
  {
    if (end <= start + 1e-12) {return;}
    if (!p.fco) {
      addKnown(r, start, end, false, "no_fco");
      return;
    }
    const double fco_end = std::min(end, p.expiry);
    if (fco_end > start) {addKnown(r, start, fco_end, true, "fco");}
    if (fco_end < end) {addKnown(r, fco_end, end, false, "source_expired");}
  }

  void integrateWithPredicate(
    MissionFcoRecord & r, double start, double end, const Pred & p, double expiry)
  {
    Pred adjusted = p;
    adjusted.expiry = expiry;
    integrateWithPredicate(r, start, end, adjusted);
  }

  void integrateTo(MissionFcoRecord & r, double end_s)
  {
    if (!r.t0_seen || r.measurement_closed) {return;}
    const double budget_end = r.t0_s + cfg_.budget_s;
    const double stop = std::min(end_s, budget_end);
    if (stop <= r.t0_s + 1e-12) {return;}

    if (!have_last_) {
      const double start = coveredTo(r);
      if (stop > start + 1e-12) {
        addMissing(r, start, stop,
          start <= r.t0_s + 1e-9 ? "no_tick_evidence" : "logger_gap");
      }
      return;
    }
    if (stop <= last_t_ + 1e-12) {return;}
    if (stop - last_t_ > cfg_.max_gap_s) {
      addMissing(r, last_t_, stop, "logger_gap");
    } else {
      integrateWithPredicate(r, last_t_, stop, last_pred_, last_expiry_);
    }
    last_t_ = stop;
    have_last_ = false;
  }

  void addKnown(
    MissionFcoRecord & r, double start, double end, bool fco, const std::string & reason)
  {
    if (end <= start + 1e-12) {return;}
    r.known_preterminal_s += end - start;
    if (fco) {r.fco_exposure_s += end - start;}
    pushInterval(r, start, end, fco, "known", reason);
  }

  void addMissing(
    MissionFcoRecord & r, double start, double end, const std::string & reason)
  {
    if (end <= start + 1e-12) {return;}
    r.missing_preterminal_s += end - start;
    pushInterval(r, start, end, false, "missing", reason);
  }

  void addPostTerminal(MissionFcoRecord & r, double start, double end)
  {
    if (end <= start + 1e-12) {return;}
    r.post_terminal_budget_s += end - start;
    pushInterval(r, start, end, false, "post_terminal", "mission_terminal");
  }

  static void pushInterval(
    MissionFcoRecord & r, double start, double end, bool fco,
    const std::string & kind, const std::string & reason)
  {
    if (!r.intervals.empty()) {
      MissionFcoInterval & last = r.intervals.back();
      if (std::fabs(last.end_s - start) <= 1e-9 && last.fco == fco &&
        last.kind == kind && last.reason == reason)
      {
        last.end_s = end;
        return;
      }
    }
    MissionFcoInterval interval;
    interval.start_s = start;
    interval.end_s = end;
    interval.fco = fco;
    interval.kind = kind;
    interval.reason = reason;
    r.intervals.push_back(interval);
  }

  double coveredTo(const MissionFcoRecord & r) const
  {
    return r.intervals.empty() ? r.t0_s : r.intervals.back().end_s;
  }

  void trimTo(MissionFcoRecord & r, double end_s)
  {
    while (!r.intervals.empty()) {
      MissionFcoInterval & last = r.intervals.back();
      if (last.start_s >= end_s - 1e-9) {
        subtractInterval(r, last);
        r.intervals.pop_back();
        continue;
      }
      if (last.end_s > end_s) {
        const double removed = last.end_s - std::max(last.start_s, end_s);
        if (last.kind == "known") {
          r.known_preterminal_s -= removed;
          if (last.fco) {r.fco_exposure_s -= removed;}
        } else if (last.kind == "missing") {
          r.missing_preterminal_s -= removed;
        } else if (last.kind == "post_terminal") {
          r.post_terminal_budget_s -= removed;
        }
        last.end_s = end_s;
      }
      break;
    }
  }

  static void subtractInterval(MissionFcoRecord & r, const MissionFcoInterval & interval)
  {
    const double length = interval.end_s - interval.start_s;
    if (interval.kind == "known") {
      r.known_preterminal_s -= length;
      if (interval.fco) {r.fco_exposure_s -= length;}
    } else if (interval.kind == "missing") {
      r.missing_preterminal_s -= length;
    } else if (interval.kind == "post_terminal") {
      r.post_terminal_budget_s -= length;
    }
  }

  void close(MissionFcoRecord & r)
  {
    if (r.measurement_closed) {return;}
    if (!r.t0_seen) {
      r.measurement_closed = true;
      r.point_valid = false;
      r.bounds_valid = false;
      return;
    }

    const double budget_end = r.t0_s + cfg_.budget_s;
    double target_end = budget_end;
    if (r.terminal_seen && r.terminal_s >= r.t0_s && r.terminal_s <= budget_end) {
      target_end = r.terminal_s;
    }

    trimTo(r, target_end);
    const double covered_before = coveredTo(r);
    if (covered_before < target_end - 1e-9) {
      addMissing(r, covered_before, target_end,
        r.terminal_seen ? "terminal_unaccounted" :
        (target_end < budget_end ? "run_ended_before_budget" : "unaccounted"));
    }

    if (r.terminal_seen && r.terminal_s >= r.t0_s && r.terminal_s <= budget_end) {
      addPostTerminal(r, r.terminal_s, budget_end);
    }
    r.post_terminal_budget_s = std::max(0.0, r.post_terminal_budget_s);

    r.terminal_within_budget = r.terminal_seen && r.terminal_s >= r.t0_s &&
      r.terminal_s <= budget_end;
    r.terminal_unknown_at_budget = !r.terminal_seen && covered_before >= budget_end - 1e-9;
    r.stopped_early = !r.terminal_seen && covered_before < budget_end - 1e-9;
    r.measurement_closed = true;
    computeOutcome(r);
  }

  void computeOutcome(MissionFcoRecord & r)
  {
    r.coverage_residual_s = cfg_.budget_s -
      (r.known_preterminal_s + r.missing_preterminal_s + r.post_terminal_budget_s);
    const bool coverage_ok = std::fabs(r.coverage_residual_s) <= 1e-6;
    const bool identity_ok = r.t0_verified && r.episode_available &&
      !r.episode_mismatch && !r.clock_regression;
    const bool finite = std::isfinite(r.fco_exposure_s) &&
      std::isfinite(r.known_preterminal_s) && std::isfinite(r.missing_preterminal_s);

    const double nan = std::numeric_limits<double>::quiet_NaN();
    r.mission_fco_fraction = nan;
    r.identification_lower = nan;
    r.identification_upper = nan;

    r.bounds_valid = identity_ok && coverage_ok && finite && r.t0_seen;
    if (r.bounds_valid) {
      r.identification_lower = r.fco_exposure_s / cfg_.budget_s;
      r.identification_upper = (r.fco_exposure_s + r.missing_preterminal_s) / cfg_.budget_s;
    }
    r.point_valid = r.bounds_valid && r.missing_preterminal_s <= 1e-9;
    if (r.point_valid) {
      r.mission_fco_fraction = r.fco_exposure_s / cfg_.budget_s;
    }
    if (r.terminal_seen && r.terminal_s < r.t0_s) {
      addReason(r, "terminal_before_t0");
      r.point_valid = false;
      r.bounds_valid = false;
    }
  }

  static void addReason(MissionFcoRecord & r, const std::string & reason)
  {
    if (std::find(r.unknown_reasons.begin(), r.unknown_reasons.end(), reason) ==
      r.unknown_reasons.end())
    {
      r.unknown_reasons.push_back(reason);
    }
  }

  void resetTickState()
  {
    have_last_ = false;
    last_t_ = 0.0;
    last_pred_ = Pred{};
    last_expiry_ = 0.0;
  }

  void resetActiveState()
  {
    active_ = -1;
    resetTickState();
  }

  MissionFcoConfig cfg_{};
  bool cfg_valid_{true};
  std::vector<MissionFcoRecord> records_;
  int active_{-1};
  int last_mission_{-1};
  bool ignore_terminal_{false};
  int current_episode_{-1};
  bool have_episode_{false};
  bool prev_seen_{false};
  bool prev_is_ground_{false};
  bool terminal_state_latched_{false};
  bool have_last_{false};
  double last_t_{0.0};
  Pred last_pred_{};
  double last_expiry_{0.0};
};

}  // namespace agc_task
