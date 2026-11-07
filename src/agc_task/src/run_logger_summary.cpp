// run_logger_summary.cpp —— `finalize()` 与 `summary.json` 的**唯一**发射点。
//
// 从 `run_logger.cpp` 拆出（B1：原文件 1,664 行）。为什么单独一个文件：
// `finalize()` 325 行里有 224 行是 summary JSON 的**逐字段序列化**，字段集合与顺序
// 是对外产物 schema（ADR-0006），改动频率与「订阅 / 逐拍判定」完全不同。
//
// 拆分纪律：**不复制状态**。本文件只有成员函数的定义；成员与声明在 `run_logger.hpp`，
// 状态仍只有一份（不新建第二真源）。

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <ctime>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <limits>
#include <map>
#include <memory>
#include <random>
#include <sstream>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

#include <rclcpp/rclcpp.hpp>
#include <agc_msgs/msg/agc_task_state.hpp>
#include <agc_msgs/msg/target_track_array.hpp>
#include <geometry_msgs/msg/twist_stamped.hpp>
#include <nav2_msgs/msg/collision_monitor_state.hpp>
#include <nav_msgs/msg/odometry.hpp>
#include <ros_gz_interfaces/msg/contacts.hpp>
#include <sensor_msgs/msg/laser_scan.hpp>
#include <std_msgs/msg/bool.hpp>
#include <std_msgs/msg/int32.hpp>
#include <std_msgs/msg/string.hpp>
#include <trajectory_msgs/msg/multi_dof_joint_trajectory.hpp>

#include "agc_task/air_evidence.hpp"
#include "agc_task/epoch_seconds.hpp"
#include "agc_task/json_value.hpp"
#include "agc_task/mission_fco_fixed_budget.hpp"
#include "agc_task/mission_fco_json.hpp"

namespace fs = std::filesystem;

// 证据 JSON 的标量序列化（见 agc_task/json_value.hpp）：本类不在 agc_task 命名空间内，
// 故在此做文件级 using，避免每个调用点写全限定名。
using agc_task::jsonBool;
using agc_task::jsonNumber;
using agc_task::jsonString;


#include "agc_task/run_logger.hpp"

void RunLogger::finalize()
  {
    const double dur = std::chrono::duration<double>(std::chrono::steady_clock::now() - start_wall_).count();
    wall_end_unix_s_ = std::chrono::duration<double>(
      std::chrono::system_clock::now().time_since_epoch()).count();
    if (now().seconds() > 0.0) {sim_end_s_ = now().seconds(); have_sim_ = true;}
    // ADR-0021：在写 summary 前闭合新固定预算记录器并落独立区间账。
    mission_fco_.finalize(have_sim_ ? sim_end_s_ : now().seconds());
    writeMissionFcoLedger();
    const double sim_delta = have_sim_ ? (sim_end_s_ - sim_start_s_) : 0.0;
    const double ratio = odom_valid_total_ > 0 ?
      static_cast<double>(odom_valid_true_) / odom_valid_total_ : 0.0;
    const double rate = dur > 0.0 ? cmd_count_ / dur : 0.0;
    const double shield_rate = triggered_ticks_ > 0 ?
      static_cast<double>(infeasible_ticks_) / triggered_ticks_ : 0.0;
    const double reset_rate = reset_failed_ ? 1.0 : 0.0;
    // （ADR-0010）：诚实口径量 + 有效样本掩码
    const bool scan_derived_na = (total_ticks_ == 0) || (scan_samples_ == 0);
    const bool trigger_derived_na = (trigger_events_ == 0);
    const bool collision_truth_na = contact_topic_.empty();
    // 若 episode 在**仍处于触发期**时结束且该触发期内已发生真实接触，则未发生下降沿——
    // 此处补记一次「真实安全不可行」，避免漏报（honest 优先）。
    const long infeasible_events_total = infeasible_trigger_events_ +
      ((in_trigger_ && current_trigger_has_contact_) ? 1 : 0);
    const bool true_shield_infeasible = infeasible_events_total > 0;

    // （ADR-0016）：finalize 时若仍有开窗 → 关闭它，closed=false（显式标注未闭合）。
    if (current_window_ >= 0) {
      EpisodeWindow & w = windows_[current_window_];
      w.leave_s = have_sim_ ? sim_end_s_ : last_tick_sim_s_;
      w.closed = false;
      w.exit_state = last_state_name_;
      w.exit_reason = reason_code_;
      closeVisibilityGap(w, w.leave_s);
      current_window_ = -1;
    }
    // 终态锁存输出（首个终态；无则回落到最后 state_name；再空则回退 IDLE）。
    const std::string terminal_state_out = !terminal_state_.empty() ? terminal_state_ :
      (!last_state_name_.empty() ? last_state_name_ : std::string("IDLE"));
    const std::string terminal_state_source = terminal_latched_ ? "first_terminal_latched" :
      (!last_state_name_.empty() ? "last_state_no_terminal" : "none");
    // episode 窗口聚合 + 拒绝可用评价（无任务 / 无 scan / 无 odom 拍 → 不以 0 冒充）。
    const bool has_window = !windows_.empty();
    long agg_ticks_total = 0, agg_ticks_valid = 0;
    long agg_ticks_invalid_scan = 0, agg_ticks_invalid_action = 0;
    long agg_triggered_ticks = 0, agg_infeasible_ticks = 0, agg_scan_samples = 0;
    long agg_ticks_intervened = 0;   // 安全层干预拍数累计
    long agg_vis_total = 0, agg_vis_visible = 0, agg_vis_opportunity = 0;
    double agg_vis_gap_longest = 0.0, agg_vis_recovery_last = 0.0;
    // （T4）：窗口级新诊断的聚合（只增不改；相对时刻取各窗口最早值，窗口起点仍为各自 enter_s）。
    long agg_envelope_in = 0;
    double agg_first_fco_s = -1.0, agg_first_envelope_in_s = -1.0;
    for (const auto & w : windows_) {
      agg_ticks_total += w.ticks_total;
      agg_ticks_valid += w.ticks_valid;
      agg_ticks_invalid_scan += w.ticks_invalid_scan;
      agg_ticks_invalid_action += w.ticks_invalid_action;
      agg_triggered_ticks += w.triggered_ticks;
      agg_infeasible_ticks += w.infeasible_ticks;
      agg_scan_samples += w.scan_samples;
      agg_ticks_intervened += w.ticks_intervened;
      agg_vis_total += w.vis_ticks_total;
      agg_vis_visible += w.vis_ticks_visible;
      agg_vis_opportunity += w.vis_ticks_opportunity;
      agg_envelope_in += w.envelope_in_ticks;
      if (w.first_fire_control_opportunity_s >= 0.0 &&
        (agg_first_fco_s < 0.0 || w.first_fire_control_opportunity_s < agg_first_fco_s))
      {
        agg_first_fco_s = w.first_fire_control_opportunity_s;
      }
      if (w.first_envelope_in_s >= 0.0 &&
        (agg_first_envelope_in_s < 0.0 || w.first_envelope_in_s < agg_first_envelope_in_s))
      {
        agg_first_envelope_in_s = w.first_envelope_in_s;
      }
      if (w.vis_gap_longest_s > agg_vis_gap_longest) {agg_vis_gap_longest = w.vis_gap_longest_s;}
      if (w.vis_recovery_last_s > agg_vis_recovery_last) {agg_vis_recovery_last = w.vis_recovery_last_s;}
    }
    std::vector<std::string> na_reasons;
    if (!has_window) {
      na_reasons.push_back("no_episode_window");
    } else {
      if (agg_ticks_total == 0) {na_reasons.push_back("no_odom_ticks_in_window");}
      if (agg_scan_samples == 0) {na_reasons.push_back("no_scan_in_window");}
    }
    const bool evaluation_applicable = na_reasons.empty();
    const bool episode_window_na = !has_window;
    const bool window_scan_na = has_window && (agg_scan_samples == 0);
    const bool window_action_na = has_window && (agg_ticks_total > 0) && (agg_ticks_valid == 0);
    const std::string ratio_scan = agg_ticks_total > 0 ?
      std::to_string(static_cast<double>(agg_ticks_invalid_scan) / agg_ticks_total) : std::string("null");
    const std::string ratio_action = agg_ticks_total > 0 ?
      std::to_string(static_cast<double>(agg_ticks_invalid_action) / agg_ticks_total) : std::string("null");
    const std::string window_rate = (evaluation_applicable && agg_triggered_ticks > 0) ?
      std::to_string(static_cast<double>(agg_infeasible_ticks) / agg_triggered_ticks) : std::string("null");
    // ：窗口内干预拍占比（raw≠effective）——分母 = 窗口有效拍数（无有效拍 → null）。
    const std::string window_intervention_ratio =
      (evaluation_applicable && agg_ticks_total > 0) ?
      std::to_string(static_cast<double>(agg_ticks_intervened) / agg_ticks_total) : std::string("null");

    std::ofstream out(run_dir_ / "metrics" / "summary.json");
    out << "{\n"
        << "  \"run_id\": \"" << run_id_ << "\",\n"
        << "  \"episode_id\": " << (have_episode_ ? std::to_string(episode_id_) : std::string("null")) << ",\n"
        << "  \"git_commit\": \"" << git_commit_ << "\",\n"
        << "  \"seed\": " << seed_ << ",\n"
        << "  \"scenario\": \"" << scenario_ << "\",\n"
        << "  \"terminal_state\": \"" << terminal_state_out << "\",\n"
        << "  \"terminal_state_latched\": " << (terminal_latched_ ? "true" : "false") << ",\n"
        << "  \"terminal_state_source\": \"" << terminal_state_source << "\",\n"
        << "  \"terminal_reason_code\": \"" << terminal_reason_code_ << "\",\n"
        << "  \"reason_code\": \"" << reason_code_ << "\",\n"
        << "  \"duration_s\": " << dur << ",\n"
        << "  \"odom_valid_ratio\": " << ratio << ",\n"
        << "  \"cmd_vel_rate_hz\": " << rate << ",\n"
        << "  \"reset_retries\": " << reset_retries_ << ",\n"
        << "  \"reset_failed\": " << (reset_failed_ ? "true" : "false") << ",\n"
        // === 感知路径与视觉模型标识：**值固定**（视觉定位路径已退役，见构造器注释）===
        // 保留键是为了 schema 不漂移、新旧 run 可直接对比。
        << "  \"perception_path\": \"" << perception_path_ << "\",\n"
        << "  \"vision_model\": {\"id\": \"" << vision_model_id_ << "\", \"name\": \""
        << vision_model_name_ << "\", \"version\": \"" << vision_model_version_
        << "\", \"sha256\": \"" << vision_model_sha256_ << "\"},\n"
        << "  \"detector_backend\": \"" << detector_backend_ << "\",\n"
        // === 历史口径 proxy_v1（**保留不动**，仅加定义版本标注）===
        << "  \"shield_infeasible_rate\": " << shield_rate << ",\n"
        << "  \"reset_failure_rate\": " << reset_rate << ",\n"
        << "  \"ticks_total\": " << total_ticks_ << ",\n"
        << "  \"ticks_triggered\": " << triggered_ticks_ << ",\n"
        << "  \"ticks_infeasible\": " << infeasible_ticks_ << ",\n"
        // 时间口径标注 + 起止事件 + RTF（新增键；duration_s 语义不变）
        << "  \"duration_kind\": \"process_wall_incl_warmup_shutdown\",\n"
        << "  \"wall_start_unix_s\": " << agc_task::formatEpochSeconds(wall_start_unix_s_) << ",\n"
        << "  \"wall_end_unix_s\": " << agc_task::formatEpochSeconds(wall_end_unix_s_) << ",\n"
        << "  \"sim_start_s\": " << (have_sim_ ? std::to_string(sim_start_s_) : std::string("null")) << ",\n"
        << "  \"sim_end_s\": " << (have_sim_ ? std::to_string(sim_end_s_) : std::string("null")) << ",\n"
        << "  \"rtf\": " << (have_sim_ && dur > 0.0 ? std::to_string(sim_delta / dur) : std::string("null")) << ",\n"
        // === 新增：口径版本 + 真实接触证据（gz_contact_v1）===
        << "  \"definition_version\": {\"shield_infeasible_rate\": \"proxy_v1\", "
           "\"collision_truth\": \"gz_contact_v1\", \"true_shield_infeasible\": \"gz_contact_v1\", "
           "\"shield_infeasible_rate_window\": \"window_valid_v2\", "
           "\"terminal_state\": \"first_terminal_latch_v1\", "
           "\"scan_valid_mask\": \"scan_frame_fresh_v2\"},\n"
        << "  \"metrics_comparability\": \"proxy_v1（进程全时长）与 window_valid_v2（episode 窗口）"
           "及 gz_contact_v1 三口径互不冒充，均不与旧 RL 安全集指标直接对照（口径/分母不同）；"
           "scan 有效样本掩码为 scan_frame_fresh_v2（帧新鲜即有效，**不**要求前向锥有回波）"
           "——无障碍场景的 ticks_invalid_scan 因此由 100% 降为 ~0，与 v1 不可逐值对照；"
           "action 档自 window_valid_v2 起为『状态已知 + 安全层存活』（**不**要求 state 话题逐拍新鲜，"
           "该话题是边沿发布）——动作长期不变的场景 ticks_invalid_action 因此由 100% 降为 ~0，"
           "与 window_valid_v1 不可逐值对照\",\n"
        << "  \"collision_count\": " << collision_count_ << ",\n"
        << "  \"collision_events\": [";
    for (size_t i = 0; i < collision_events_.size(); ++i) {
      const auto & ev = collision_events_[i];
      if (i > 0) {out << ", ";}
      out << "{\"t_sim\": " << ev.t_sim_s << ", \"other\": " << jsonString(ev.other)
          << ", \"depth\": "
          << (ev.have_depth ? std::to_string(ev.depth) : std::string("null")) << ", \"position\": ";
      if (ev.have_pos) {
        out << "{\"x\": " << ev.pos_x << ", \"y\": " << ev.pos_y << ", \"z\": " << ev.pos_z << "}";
      } else {
        out << "null";
      }
      out << "}";
    }
    out << "],\n"
        << "  \"contact_msgs_received\": " << contact_msgs_received_ << ",\n"
        << "  \"trigger_events\": " << trigger_events_ << ",\n"
        << "  \"intervention_duration_s\": " << intervention_duration_s_ << ",\n"
        << "  \"stopping_margin_min_m\": "
        << (have_stopping_margin_ ? std::to_string(stopping_margin_min_m_) : std::string("null")) << ",\n"
        << "  \"stopping_margin_negative_ticks\": " << stopping_margin_negative_ticks_ << ",\n"
        << "  \"ticks_triggered_no_scan\": " << ticks_triggered_no_scan_ << ",\n"
        << "  \"true_shield_infeasible\": " << (true_shield_infeasible ? "true" : "false") << ",\n"
        << "  \"true_shield_infeasible_rate\": "
        << (trigger_events_ > 0 ?
            std::to_string(static_cast<double>(infeasible_events_total) / trigger_events_) :
            std::string("null")) << ",\n"
        << "  \"not_applicable\": {\"scan_derived\": " << (scan_derived_na ? "true" : "false")
        << ", \"trigger_derived\": " << (trigger_derived_na ? "true" : "false")
        << ", \"collision_truth\": " << (collision_truth_na ? "true" : "false")
        << ", \"episode_window\": " << (episode_window_na ? "true" : "false")
        << ", \"window_scan\": " << (window_scan_na ? "true" : "false")
        << ", \"window_action\": " << (window_action_na ? "true" : "false") << "},\n"
        // === 新增：episode 窗口统计 / 有效样本掩码 / 拒绝可用评价 ===
        << "  \"evaluation_applicable\": " << (evaluation_applicable ? "true" : "false") << ",\n"
        << "  \"evaluation_na_reasons\": [";
    for (size_t i = 0; i < na_reasons.size(); ++i) {
      if (i > 0) {out << ", ";}
      out << "\"" << na_reasons[i] << "\"";
    }
    out << "],\n"
        << "  \"episode_window_metrics\": {\"window_count\": " << windows_.size()
        << ", \"ticks_total\": " << agg_ticks_total
        << ", \"ticks_valid\": " << agg_ticks_valid
        << ", \"ticks_invalid_scan\": " << agg_ticks_invalid_scan
        << ", \"ticks_invalid_action\": " << agg_ticks_invalid_action
        << ", \"ticks_missing_ratio_scan\": " << ratio_scan
        << ", \"ticks_missing_ratio_action\": " << ratio_action
        << ", \"triggered_ticks\": " << agg_triggered_ticks
        << ", \"infeasible_ticks\": " << agg_infeasible_ticks
        << ", \"scan_samples\": " << agg_scan_samples
        << ", \"ticks_intervened\": " << agg_ticks_intervened
        << ", \"vis_ticks_total\": " << agg_vis_total
        << ", \"vis_ticks_visible\": " << agg_vis_visible
        << ", \"ticks_fire_control_opportunity\": " << agg_vis_opportunity
        // === （T4，ADR-0023 后续诊断）：窗口级机会 / 包络（**只增不改**）===
        // first_* 为**相对窗口 enter_s** 的时刻（s）；-1 = 窗口内未发生（输出 null）。
        // envelope_in_* 为**无条件**包络占用（env_ok ∧ envelope_in_，**不**与 visible 取交）；
        // 分母沿用同窗口逐拍计数 agg_vis_total（与 visibility_rate 分母同源）。
        << ", \"first_fire_control_opportunity_s\": "
        << (agg_first_fco_s >= 0.0 ? std::to_string(agg_first_fco_s) : std::string("null"))
        << ", \"envelope_in_ticks\": " << agg_envelope_in
        << ", \"envelope_in_rate\": " << (agg_vis_total > 0 ?
            std::to_string(static_cast<double>(agg_envelope_in) / agg_vis_total) : std::string("null"))
        << ", \"first_envelope_in_s\": "
        << (agg_first_envelope_in_s >= 0.0 ? std::to_string(agg_first_envelope_in_s) : std::string("null"))
        << ", \"visibility_rate\": "
        << (agg_vis_total > 0 ? std::to_string(static_cast<double>(agg_vis_visible) / agg_vis_total) : std::string("null"))
        << ", \"intervention_ticks_ratio\": " << window_intervention_ratio
        << ", \"shield_infeasible_rate\": " << window_rate << "},\n"
        << "  \"episode_windows\": [";
    for (size_t i = 0; i < windows_.size(); ++i) {
      const auto & w = windows_[i];
      if (i > 0) {out << ", ";}
      out << "{\"index\": " << w.index
          << ", \"enter_s\": " << w.enter_s
          << ", \"leave_s\": " << w.leave_s
          << ", \"closed\": " << (w.closed ? "true" : "false")
          << ", \"exit_state\": \"" << w.exit_state << "\""
          << ", \"exit_reason\": \"" << w.exit_reason << "\""
          << ", \"ticks_total\": " << w.ticks_total
          << ", \"ticks_valid\": " << w.ticks_valid
          << ", \"ticks_invalid_scan\": " << w.ticks_invalid_scan
          << ", \"ticks_invalid_action\": " << w.ticks_invalid_action
          << ", \"triggered_ticks\": " << w.triggered_ticks
          << ", \"infeasible_ticks\": " << w.infeasible_ticks
          << ", \"scan_samples\": " << w.scan_samples
          << ", \"ticks_intervened\": " << w.ticks_intervened
          << ", \"vis_ticks_total\": " << w.vis_ticks_total
          << ", \"vis_ticks_visible\": " << w.vis_ticks_visible
          << ", \"ticks_fire_control_opportunity\": " << w.vis_ticks_opportunity
          << ", \"vis_gap_longest_s\": " << w.vis_gap_longest_s
          // （T4）：窗口级机会 / 无条件包络（相对本窗口 enter_s；-1 → null）。
          << ", \"first_fire_control_opportunity_s\": "
          << (w.first_fire_control_opportunity_s >= 0.0 ?
              std::to_string(w.first_fire_control_opportunity_s) : std::string("null"))
          << ", \"envelope_in_ticks\": " << w.envelope_in_ticks
          << ", \"envelope_in_rate\": " << (w.vis_ticks_total > 0 ?
              std::to_string(static_cast<double>(w.envelope_in_ticks) / w.vis_ticks_total) :
              std::string("null"))
          << ", \"first_envelope_in_s\": "
          << (w.first_envelope_in_s >= 0.0 ?
              std::to_string(w.first_envelope_in_s) : std::string("null"))
          << ", \"shield_infeasible_rate\": "
          << (w.triggered_ticks > 0 ?
              std::to_string(static_cast<double>(w.infeasible_ticks) / w.triggered_ticks) :
              std::string("null"))
          << "}";
    }
    out << "],\n"
        // === raw / effective 命令归因（策略原动作 vs 安全修正）===
        << "  \"command_attribution\": {\n"
        << "    \"definition_version\": \"raw_effective_v2\",\n"
        << "    \"semantics\": \"raw = 安全层输入（命令源原创）；effective = 安全层输出（唯一执行口值）；"
           "同拍=同一 odom 采样拍两话题快照均新鲜；净空可'已知'= 该拍有新鲜 scan 帧（无回波 = 范围内无遮挡）\",\n"
        << "    \"shield_layer_enabled\": " << (shield_layer_enabled_ ? "true" : "false") << ",\n"
        << "    \"raw_msgs_received\": " << raw_msgs_ << ",\n"
        << "    \"effective_msgs_received\": " << eff_msgs_ << ",\n"
        << "    \"ticks_total\": " << attr_ticks_total_ << ",\n"
        << "    \"ticks_paired\": " << attr_ticks_paired_ << ",\n"
        << "    \"same_stamp_ticks\": " << attr_same_stamp_ticks_ << ",\n"
        << "    \"stamp_delta_abs_max_s\": " << attr_stamp_delta_abs_max_s_ << ",\n"
        << "    \"intervened_ticks\": " << attr_intervened_ticks_ << ",\n"
        << "    \"intervention_segments\": " << attr_intervention_segments_ << ",\n"
        << "    \"intervention_duration_s\": " << attr_intervention_duration_s_ << ",\n"
        << "    \"max_abs_delta_v_mps\": " << attr_max_abs_dv_ << ",\n"
        << "    \"max_abs_delta_w_radps\": " << attr_max_abs_dw_ << ",\n"
        << "    \"clearance_min_m\": "
        << (have_attr_clearance_ ? std::to_string(attr_clearance_min_m_) : std::string("null")) << ",\n"
        << "    \"clearance_min_at_intervention_m\": "
        << (have_attr_clearance_intervened_ ?
            std::to_string(attr_clearance_min_intervened_m_) : std::string("null")) << ",\n"
        // 修订（scan_fresh_v2）：净空**已知**拍数 + 其中**无回波**（前向锥全 inf = 范围内无遮挡）子计数；
        // 全窗无回波时 clearance_min_m 为 null 但 `clearance` **仍 applicable**（已知 = ∞，非缺数据）。
        << "    \"clearance_ticks\": " << attr_clearance_ticks_ << ",\n"
        << "    \"clearance_no_return_ticks\": " << attr_clearance_no_return_ticks_ << ",\n"
        << "    \"clearance_at_intervention_ticks\": " << attr_clearance_intervened_ticks_ << ",\n"
        << "    \"clearance_at_intervention_no_return_ticks\": "
        << attr_clearance_intervened_no_return_ticks_ << ",\n"
        << "    \"not_applicable\": {\"raw\": " << (raw_msgs_ == 0 ? "true" : "false")
        << ", \"effective\": " << (eff_msgs_ == 0 ? "true" : "false")
        << ", \"paired_ticks\": " << (attr_ticks_paired_ == 0 ? "true" : "false")
        << ", \"clearance\": " << (attr_clearance_known_ ? "false" : "true") << "},\n"
        << "    \"note\": \"无 shield 臂（shield_layer_enabled=false）时 effective≡raw → intervened_ticks=0；"
           "纯仿真对照臂，**不**用于实际部署（ADR-0022）；净空口径 scan_fresh_v2（ADR-0016 修订）："
           "无回波拍记入 clearance_no_return_ticks（范围内无遮挡），clearance_min_m 仅取有限回波最小值\"\n"
        << "  },\n"
        // === ADR-0022 修订：可见性度量按**固定观测时长**（自首个 active 拍起
        // `obs_window_s` 秒；**不**随终态截断）——分母与"是否早成功"解耦（消除饱和 / 选择效应）===
        << "  \"visibility_metrics\": {\n"
        << "    \"definition_version\": \"window_fixed_v1\",\n"
        << "    \"window_s\": " << obs_window_s_ << ",\n"
        << "    \"visibility_max_age_s\": " << visibility_max_age_s_ << ",\n"
        << "    \"ticks_total\": " << obs_vis_total_ << ",\n"
        << "    \"ticks_visible\": " << obs_vis_visible_ << ",\n"
        << "    \"visibility_rate\": "
        << (obs_vis_total_ > 0 ? std::to_string(static_cast<double>(obs_vis_visible_) / obs_vis_total_) : std::string("null")) << ",\n"
        << "    \"ticks_fire_control_opportunity\": " << obs_vis_opportunity_ << ",\n"
        << "    \"fire_control_opportunity_rate\": "
        << (obs_vis_total_ > 0 ? std::to_string(static_cast<double>(obs_vis_opportunity_) / obs_vis_total_) : std::string("null")) << ",\n"
        << "    \"longest_outage_s\": " << obs_gap_longest_ << ",\n"
        << "    \"recovery_time_last_s\": " << obs_recovery_last_ << ",\n"
        << "    \"not_applicable\": {\"target_truth\": " << (target_msgs_ == 0 ? "true" : "false") << ", \"episode_window\": " << (episode_window_na ? "true" : "false") << ", \"envelope\": " << (have_envelope_ ? "false" : "true") << "},\n"
        << "    \"note\": \"ADR-0022：可见率分母 = **自首个 active 拍起固定 window_s 秒内的拍数**（不随终态截断；"
           "消除早成功臂的饱和 / 选择效应）；tgt_age = 该拍时刻 − 目标 header.stamp。\"\n"
        << "  },\n"
        << "  \"tracking_error_metrics\": " << air_.json() << ",\n"
        << "  \"mission_fco_fixed_budget_v1\": " << agc_task::missionFcoSummaryJson(
           mission_fco_, mission_fco_cfg_, mission_fco_.configValid()) << ",\n"
        << "  \"process_metrics_note\": \"duration_s / odom_valid_ratio / cmd_vel_rate_hz / ticks_* / "
           "shield_infeasible_rate 为**进程全时长**口径（含预热 / 关闭），与 episode_window_metrics 的 "
           "episode 窗口口径互不冒充。\"\n"
        << "}\n";
    RCLCPP_INFO(get_logger(), "summary written: %s", (run_dir_ / "metrics" / "summary.json").c_str());
  }
