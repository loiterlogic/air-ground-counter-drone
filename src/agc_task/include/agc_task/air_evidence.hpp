// air_evidence.hpp —— 空中跟踪误差 / hold / 观测延迟取证（**独立单元**）
//
// 从 `run_logger.cpp` 拆出（原文件 1,664 行，本单元约 250 行）。
// 拆分纪律（plan 的已知坑）：`trackingErrorJson()` 与 `finalize()` 曾共享 16 个成员，
// 故这里把**成员一起搬进本类**，`RunLogger` 只持有一个 `AirEvidence` 实例并通过
// `air_.onOdom()` / `air_.json()` 调用——**不复制状态**（复制即成第二真源）。
//
// 判据 / 口径见 `docs/adr/0006-experiment-artifacts-and-evidence-discipline.md#top`
// 与 `docs/adr/0016-episode-window-and-sample-validity.md#top`；本文件只实现，
// 不复述契约条文。
//
// 本单元**不**依赖 `RunLogger` 的其它状态：构造时由调用方一次性注入三个话题名与
// 配对容差，其余全部自持。

#ifndef AGC_TASK_AIR_EVIDENCE_HPP_
#define AGC_TASK_AIR_EVIDENCE_HPP_

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>
#include <map>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

#include <rclcpp/rclcpp.hpp>
#include <nav_msgs/msg/odometry.hpp>
#include <std_msgs/msg/string.hpp>
#include <trajectory_msgs/msg/multi_dof_joint_trajectory.hpp>

namespace agc_task
{

/// 空中跟踪误差 / hold 边沿 / 观测延迟的**唯一**取证实现。
///
/// * `onOdom` / `onRef` 累积并做仿真时间戳最近邻配对（容差 `pair_max_dt_s`）；
/// * `onStatus` 取 `tracking_status` JSON 的 `frozen` 字段做**边沿**计数；
/// * `json()` 产出 `summary.json` 的 `tracking_error_metrics` 块。
///
/// 全部是**派生诊断**，不参与任何终态 / 安全判定。
class AirEvidence
{
public:
  struct Config
  {
    std::string odom_topic;
    std::string ref_topic;
    std::string status_topic;
    bool enabled{true};
    double pair_max_dt_s{0.02};
  };

  AirEvidence() = default;
  explicit AirEvidence(const Config & cfg) : cfg_(cfg) {}

  const Config & config() const {return cfg_;}

  void onOdom(const nav_msgs::msg::Odometry & m)
  {
    const double t = rclcpp::Time(m.header.stamp).seconds();
    odom_[t] = {m.pose.pose.position.x, m.pose.pose.position.y};
    ++odom_msgs_;
    pairSamples();
    prune(t);
  }

  void onRef(const trajectory_msgs::msg::MultiDOFJointTrajectory & m)
  {
    if (m.points.empty() || m.points.front().transforms.empty()) {return;}
    const auto & tr = m.points.front().transforms.front().translation;
    const double t = rclcpp::Time(m.header.stamp).seconds();
    ref_[t] = {tr.x, tr.y};
    ++ref_msgs_;
  }

  /// `/agc/air/tracking_status`（std_msgs/String，JSON）：取 `frozen` 字段做**边沿**计数。
  void onStatus(const std_msgs::msg::String & m)
  {
    static const std::string key = "\"frozen\"";
    const auto kp = m.data.find(key);
    if (kp == std::string::npos) {return;}
    const auto colon = m.data.find(':', kp + key.size());
    if (colon == std::string::npos) {return;}
    auto vp = colon + 1;
    while (vp < m.data.size() && m.data[vp] == ' ') {++vp;}
    const bool frozen = (m.data.compare(vp, 4, "true") == 0);
    ++status_msgs_;
    if (frozen && !frozen_prev_) {++hold_events_;}
    frozen_prev_ = frozen;
    if (frozen) {++frozen_msgs_;}
  }

  /// `summary.json` 的 `tracking_error_metrics` 块（字段集合与顺序**保持原样**）。
  std::string json() const
  {
    std::ostringstream o;
    const bool has_err = !err_.empty();
    const bool has_lat = !latency_.empty();
    o << "{";
    o << "\"definition_version\": \"n4_tracking_error_v1\", ";
    o << "\"note\": \"派生诊断，非契约硬约束 #hc-1 口径；err_eff = ‖/agc/air/tracking_ref − /agc/air/odom‖"
         "（水平 XY，仿真时间戳最近邻配对，容差 " << cfg_.pair_max_dt_s << " s）。"
         "hold_events 是 frozen 的**边沿**计数（非逐拍 WARN 行数）。\", ";
    // ---- hold ----
    o << "\"hold\": {\"applicable\": " << (status_msgs_ > 0 ? "true" : "false")
      << ", \"events\": " << hold_events_
      << ", \"frozen_msgs\": " << frozen_msgs_
      << ", \"status_msgs\": " << status_msgs_
      << ", \"note\": \"counting false→true edges of tracking_status.frozen\"}, ";
    // ---- 跟踪误差 ----
    o << "\"tracking_error_xy_m\": {"
      << "\"applicable\": " << (has_err ? "true" : "false")
      << ", \"paired_samples\": " << err_.size()
      << ", \"ref_msgs\": " << ref_msgs_
      << ", \"odom_msgs\": " << odom_msgs_;
    if (has_err) {
      o << ", \"p50\": " << quantile(err_, 0.50)
        << ", \"p95\": " << quantile(err_, 0.95)
        << ", \"p99\": " << quantile(err_, 0.99)
        << ", \"mean\": " << mean(err_)
        << ", \"max\": " << *std::max_element(err_.begin(), err_.end());
    } else {
      o << ", \"p50\": null, \"p95\": null, \"p99\": null, \"mean\": null, \"max\": null";
    }
    o << "}, ";
    // ---- 观测延迟（latency 可测）----
    o << "\"target_obs_latency_s\": {"
      << "\"applicable\": " << (has_lat ? "true" : "false")
      << ", \"samples\": " << latency_.size();
    if (has_lat) {
      o << ", \"p50\": " << quantile(latency_, 0.50)
        << ", \"p95\": " << quantile(latency_, 0.95)
        << ", \"max\": " << *std::max_element(
             latency_.begin(), latency_.end());
    } else {
      o << ", \"p50\": null, \"p95\": null, \"max\": null";
    }
    o << ", \"note\": \"now − track.header.stamp（源采样时刻）——即链路交付延迟的实测值\"}";
    o << "}";
    return o.str();
  }

  /// 观测延迟样本（由 `RunLogger::onTargets` 交付：它才是目标话题的唯一订阅者）。
  void addLatency(double lat) {latency_.push_back(lat);}

  /// 分位（线性插值，与 scripts/tracking/track_err_probe.py 的 aggregate 同口径）。
  static double quantile(std::vector<double> v, double q)
  {
    if (v.empty()) {return std::numeric_limits<double>::quiet_NaN();}
    std::sort(v.begin(), v.end());
    const double pos = q * static_cast<double>(v.size() - 1);
    const size_t lo = static_cast<size_t>(std::floor(pos));
    const size_t hi = std::min(lo + 1, v.size() - 1);
    const double frac = pos - static_cast<double>(lo);
    return v[lo] * (1.0 - frac) + v[hi] * frac;
  }

private:
  static double mean(const std::vector<double> & v)
  {
    if (v.empty()) {return std::numeric_limits<double>::quiet_NaN();}
    double sum = 0.0;
    for (double x : v) {sum += x;}
    return sum / static_cast<double>(v.size());
  }

  /// 把 odom 与参考按 stamp 最近邻配对，累积 err_eff。
  void pairSamples()
  {
    if (ref_.empty() || odom_.empty()) {return;}
    for (auto it = odom_.begin(); it != odom_.end(); ) {
      // 找 stamp 最近的参考
      auto lo = ref_.lower_bound(it->first);
      auto best = ref_.end();
      double best_dt = std::numeric_limits<double>::infinity();
      if (lo != ref_.end()) {best = lo; best_dt = std::abs(lo->first - it->first);}
      if (lo != ref_.begin()) {
        auto prev = std::prev(lo);
        const double d = std::abs(prev->first - it->first);
        if (d < best_dt) {best = prev; best_dt = d;}
      }
      if (best == ref_.end() || best_dt > cfg_.pair_max_dt_s) {
        ++it; continue;   // 等后续参考消息（不清缓冲）
      }
      const double dx = best->second.first - it->second.first;
      const double dy = best->second.second - it->second.second;
      err_.push_back(std::sqrt(dx * dx + dy * dy));
      it = odom_.erase(it);
    }
  }

  /// 缓冲上界：避免长时间无参考时无限增长（超出即丢最旧，不静默涨内存）。
  void prune(double t)
  {
    constexpr size_t kMaxBuf = 4000;
    while (odom_.size() > kMaxBuf) {odom_.erase(odom_.begin());}
    while (ref_.size() > kMaxBuf) {ref_.erase(ref_.begin());}
    if (t - last_prune_s_ < 1.0) {return;}
    last_prune_s_ = t;
    const double horizon = t - 60.0;
    while (!odom_.empty() && odom_.begin()->first < horizon) {
      odom_.erase(odom_.begin());
    }
    while (!ref_.empty() && ref_.begin()->first < horizon) {
      ref_.erase(ref_.begin());
    }
  }

  Config cfg_;
  std::map<double, std::pair<double, double>> odom_;   // stamp → (x, y)
  std::map<double, std::pair<double, double>> ref_;    // stamp → (x, y)
  std::vector<double> err_;
  std::vector<double> latency_;   // 交付时刻 − track.header.stamp
  std::uint64_t odom_msgs_{0}, ref_msgs_{0}, status_msgs_{0};
  std::uint64_t hold_events_{0}, frozen_msgs_{0};
  bool frozen_prev_{false};
  double last_prune_s_{0.0};
};

}  // namespace agc_task

#endif  // AGC_TASK_AIR_EVIDENCE_HPP_
