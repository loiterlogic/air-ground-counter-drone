// run_logger.hpp —— RunLogger 的**声明**（实现分在 run_logger.cpp / run_logger_summary.cpp）
//
// 从单文件 1,664 行拆出：本头文件只放**声明与成员**，方法体按职责落到两个 .cpp：
// * `run_logger.cpp` —— 订阅 / 逐拍判定 / 终态锁存 / config 身份（核心）；
// * `run_logger_summary.cpp` —— `finalize()` 与 `summary.json` 的**唯一**发射点。
//
// 拆分纪律：**不复制状态**：成员只有一份、在本头文件里；两个 .cpp 都只是它的成员函数定义。
//
// 判据见 `ADR-0006 的 #top`。

#ifndef AGC_TASK_RUN_LOGGER_HPP_
#define AGC_TASK_RUN_LOGGER_HPP_

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


class RunLogger : public rclcpp::Node
{
public:
  RunLogger();

  bool dirOk() const;

  void finalize();

private:
  // 一次**真实碰撞事件**（GZ contact 真值；独立于 proxy_v1「触发拍代理」计数）。
  struct CollisionEvent
  {
    double t_sim_s{0.0};   // now().seconds()（可能为 0 —— 仿真时间未起步；如实记录）
    std::string other;     // 非车侧碰撞体名（含 pole / 其它实体）
    bool have_depth{false};
    double depth{0.0};     // 该对接触的最小穿透深度（无有效 depth → null）
    bool have_pos{false};
    double pos_x{0.0}, pos_y{0.0}, pos_z{0.0};  // 该对接触的首个接触点（world 系；无 → null）
  };

  // （ADR-0016）：一次 episode 事件窗口（task 进入 active 开窗、离开 active（终态 / IDLE）关窗）。
  // 窗口内以**同时间快照 + 有效样本掩码**逐拍计数（陈旧 scan 一律进 ticks_invalid_scan）。
  struct EpisodeWindow
  {
    int index{0};
    double enter_s{0.0}, leave_s{0.0};   // 开 / 关窗时刻（now().seconds()；可能为 0，仿真未起步）
    bool closed{false};                  // false = finalize 时仍在开窗（显式标注未闭合）
    std::string exit_state, exit_reason; // 关窗时的 state_name / reason_code
    long ticks_total{0}, ticks_valid{0}, ticks_invalid_scan{0}, ticks_invalid_action{0};
    long triggered_ticks{0}, infeasible_ticks{0}, scan_samples{0};
    long ticks_intervened{0};   // 本窗口内 raw≠effective（安全层干预）的拍数
    // ：可见性（分母 = 本窗口拍数）
    long vis_ticks_total{0}, vis_ticks_visible{0}, vis_ticks_opportunity{0};
    double vis_gap_longest_s{0.0}, vis_recovery_last_s{0.0};
    double vis_gap_start_s{-1.0};
    // （T4，ADR-0023 后续诊断；**只增不改**）：窗口级机会 / 包络诊断。
    // 相对时刻一律以**本窗口 enter_s**（既有字段）为起点；-1 = 窗口内未发生。
    double first_fire_control_opportunity_s{-1.0};  // 首次 FCO（visible ∧ envelope_in）相对时刻
    long envelope_in_ticks{0};                      // **无条件**包络占用拍数（env_ok ∧ envelope_in_，不与 visible 取交）
    double first_envelope_in_s{-1.0};               // 首次包络进入相对时刻
  };

  // active / 终态判据（与 task_manager 对齐；active = AIR_SEARCH|TARGET_ACQUIRED|GROUND_APPROACH）。
  static bool isActiveState(uint8_t s);

  static bool isTerminalState(uint8_t s);

  void onScan(const sensor_msgs::msg::LaserScan & m);

  // ：目标观测新鲜度——tgt_age = now − header.stamp。
  void onTargets(const agc_msgs::msg::TargetTrackArray & m);


  // ：按 episode active 窗口逐拍判可见 / 有效火控机会，记最长失联与恢复时长。
  void evaluateVisibility(double t_now);

  static void closeVisibilityGap(EpisodeWindow & w, double t_close);

  // ：raw 命令快照——纯诊断，不新增命令者。
  void onRaw(const geometry_msgs::msg::TwistStamped & m);

  // ：effective（安全层**输出** = 唯一执行口值）命令快照。
  void onEffective(const geometry_msgs::msg::TwistStamped & m);

  // ：同一 odom 采样拍取 raw / effective 快照 → 干预归因。
  // 「同时间」= **同一采样拍**（两话题各自最近快照均在新鲜窗口内）；另**如实**统计 header.stamp
  // 是否被安全层保持（collision_monitor 可能重打 stamp）——归因**不**以 stamp 相等为前提，
  // 否则重打 stamp 时会漏记（诚实优先）。
  void evaluateAttribution(double t_now);

  // task 状态回调——① 终态锁存（首个终态，之后不得覆写）；② episode 事件窗口分段
  // （进入 active 开窗、离开 active（终态 / IDLE）关窗）。active / 终态定义见
  // [#glossary] …… 与 task_manager 对齐：active = AIR_SEARCH|TARGET_ACQUIRED|GROUND_APPROACH。
  void onState(const agc_msgs::msg::AgcTaskState & m);

  // （ADR-0010）：GZ contact 真值回调——逐帧判定**车↔非车**接触对，按**上升沿去重**计真实碰撞事件。
  // 车侧：名字含 `agc_car`；另一侧：名字非空且不含 `agc_car`（车↔车 / 非车↔非车 / 名缺失不计）。
  void onContacts(const ros_gz_interfaces::msg::Contacts & m);

  // 在 odom 回调时间轴上采到首个非零仿真时间（run 证据 sim_start_s）
  void noteSim();

  // shield_infeasible_rate【proxy_v1，保留历史口径】 + 【gz_contact_v1 真实口径】。
  void evaluateTick();

  // === ADR-0021：mission_fco_fixed_budget_v1 的 JSON 证据 ===
  // 标量序列化（字符串转义 / 非有限 → null / 17 位有效数字）在 json_value.hpp，
  // 那里无 ROS 依赖，可直接 gtest。

  void writeMissionFcoLedger() const;

  std::string makeRunId() const;

  std::string runShellRaw(const std::string & cmd) const;

  std::string runShell(const std::string & cmd) const;

  void writeText(const fs::path & p, const std::string & s) const;

  std::string sha256OfFile(const std::string & path) const;

  std::string sha256OfText(const std::string & text) const;

  std::string envOr(const char * key, const char * fallback) const;

  static size_t countLines(const std::string & s);

  std::string gitCommit() const;

  /// 跟踪误差 / hold / 观测延迟的 JSON 块。
  ///
  /// 三个指标各自的**分母与不适用条件**都显式写出，避免"没有数"被读成"误差为零"：
  /// * `hold_events` —— 来自 tracking_status 的 `frozen` 边沿；无该话题 → `applicable=false`。
  /// * `track_err_*` —— 需要配对样本；`paired_samples==0` → 分位为 null（不是 0）。
  /// * `obs_latency_*` —— 需要 `/agc/targets` 非空样本。
  void writeConfig();

  // episode_id 初值（-1 = 未收到）；收到 /agc/task/episode 后覆写。
  void writeEpisodePlaceholder() const;

  // （ADR-0006）：代码身份 / dirty diff / 未跟踪清单 / 内容指纹 + 工具链与世界模型哈希。
  // 只落 run 的 config/（ADR-0006）；dirty 工作区非禁跑，但 run 可据此重建。
  void writeIdentity() const;

  void copyIntoConfig(const std::string & src, const std::string & dst_name);

  std::string experiments_root_, git_root_, campaign_, scenario_, run_id_, git_commit_;
  std::string scene_manifest_file_, params_file_in_;
  std::string world_file_, px4_root_;
  int episode_id_{-1};
  bool have_episode_{false};
  bool dir_ok_{true};
  rclcpp::Subscription<std_msgs::msg::Int32>::SharedPtr episode_sub_;
  int seed_{0};
  // （ADR-0016）：终态锁存——terminal_state_ = **首个**终态 state_name（空=未观测）；
  // last_state_name_ = 最后观测到的 state_name；terminal_latched_ 标注是否已锁存。
  std::string terminal_state_, last_state_name_, terminal_reason_code_, reason_code_;
  bool terminal_latched_{false};
  size_t odom_valid_total_{0}, odom_valid_true_{0}, cmd_count_{0};
  double contact_dist_m_{2.0}, ttc_min_s_{1.0}, forward_cone_rad_{0.9};
  // （ADR-0010）：接触真值话题（空 = 不可用）+ 锁轮制动减速度
  std::string contact_topic_;
  double a_brake_mps2_{0.9};

  // 
  int reset_retries_{0};
  bool reset_failed_{false};
  uint8_t cm_action_{0};
  double vx_body_{0.0}, scan_min_forward_{0.0};
  // 修订（ADR-0016 scan_fresh_v2）：`have_scan_frame_` = **收到过 scan 帧**（有效样本掩码只看帧新鲜度）；
  // `have_scan_` = 前向锥**有有限回波**（无障碍物时全 inf → 无回波 ≠ 无数据）。
  bool have_odom_{false}, have_scan_frame_{false}, have_scan_{false};
  size_t total_ticks_{0}, triggered_ticks_{0}, infeasible_ticks_{0};

  // （gz_contact_v1）：真实接触事件 + 触发事件 / 干预时长 / 剩余停车裕度 / 有效样本掩码
  uint64_t collision_count_{0}, contact_msgs_received_{0}, scan_samples_{0};
  long trigger_events_{0}, infeasible_trigger_events_{0};
  long ticks_triggered_no_scan_{0}, stopping_margin_negative_ticks_{0};
  double intervention_duration_s_{0.0}, stopping_margin_min_m_{0.0};
  bool have_stopping_margin_{false};
  bool prev_triggered_{false}, in_trigger_{false}, current_trigger_has_contact_{false};
  double last_tick_sim_s_{0.0};
  std::vector<CollisionEvent> collision_events_;
  std::unordered_set<std::string> contact_pairs_prev_;

  // （ADR-0016）：有效样本掩码新鲜度阈值（scan 帧 / 安全层存活证据到达时刻）+ episode 事件窗口。
  double scan_max_age_s_{0.5}, action_max_age_s_{0.5};
  double scan_rx_s_{0.0};
  bool have_cm_state_{false};
  std::vector<EpisodeWindow> windows_;
  int current_window_{-1};

  // ：raw / effective 命令归因——同一 odom 拍快照 + 干预量 / 时长 / 净空。
  std::string cmd_raw_topic_;
  double cmd_max_age_s_{0.5}, attr_delta_epsilon_{1e-3}, attr_max_gap_s_{1.0};
  bool shield_layer_enabled_{true};
  // （ADR-0009）：感知路径与视觉模型标识（新键；默认 = truth / none，既有行为不变）
  std::string perception_path_, vision_model_id_, vision_model_name_,
    vision_model_version_, vision_model_sha256_;
  // 识别后端标签：视觉定位路径退役后恒为 none（字段保留仅为 schema 不漂移）
  std::string detector_backend_;
  double raw_v_{0.0}, raw_w_{0.0}, raw_stamp_{0.0}, raw_rx_s_{0.0};
  double eff_v_{0.0}, eff_w_{0.0}, eff_stamp_{0.0}, eff_rx_s_{0.0};
  bool have_raw_{false}, have_eff_{false};
  uint64_t raw_msgs_{0}, eff_msgs_{0};
  uint64_t attr_ticks_total_{0}, attr_ticks_paired_{0}, attr_same_stamp_ticks_{0};
  uint64_t attr_intervened_ticks_{0}, attr_intervention_segments_{0};
  double attr_stamp_delta_abs_max_s_{0.0}, attr_max_abs_dv_{0.0}, attr_max_abs_dw_{0.0};
  double attr_intervention_duration_s_{0.0}, attr_last_intervened_s_{0.0};
  bool have_attr_last_intervened_{false};
  double attr_clearance_min_m_{0.0}, attr_clearance_min_intervened_m_{0.0};
  bool have_attr_clearance_{false}, have_attr_clearance_intervened_{false};
  // 修订（scan_fresh_v2）：净空**已知**拍数（有新鲜 scan 帧）与其**无回波**（范围内无遮挡）子计数。
  uint64_t attr_clearance_ticks_{0}, attr_clearance_no_return_ticks_{0};
  uint64_t attr_clearance_intervened_ticks_{0}, attr_clearance_intervened_no_return_ticks_{0};
  bool attr_clearance_known_{false}, attr_clearance_intervened_known_{false};
  rclcpp::Subscription<geometry_msgs::msg::TwistStamped>::SharedPtr cmd_raw_sub_;

  // ：可见性口径
  std::string envelope_topic_;
  double visibility_max_age_s_{0.5};
  // （ADR-0022）：固定观测时长窗口（自首个 active 拍起）；口径版本 `window_fixed_v1`
  double obs_window_s_{60.0};
  double obs_start_s_{-1.0};            // 首个 active 拍时刻（<0 = 未开始）
  long obs_vis_total_{0}, obs_vis_visible_{0}, obs_vis_opportunity_{0};
  double obs_gap_start_s_{-1.0}, obs_gap_longest_{0.0}, obs_recovery_last_{0.0};
  rclcpp::Subscription<agc_msgs::msg::TargetTrackArray>::SharedPtr target_sub_;
  rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr envelope_sub_;
  bool target_have_{false}, target_present_{false};
  double target_last_stamp_s_{0.0};
  float target_confidence_{0.0f};
  uint64_t target_msgs_{0};
  bool envelope_in_{false}, have_envelope_{false};
  double envelope_rx_s_{0.0};

  // ---- 空中跟踪误差 / hold / 观测延迟取证 ----
  // 空中跟踪误差 / hold / 观测延迟取证（状态与算法在 AirEvidence，不在此复制）。
  agc_task::AirEvidence air_;
  rclcpp::Subscription<nav_msgs::msg::Odometry>::SharedPtr air_odom_sub_;
  rclcpp::Subscription<trajectory_msgs::msg::MultiDOFJointTrajectory>::SharedPtr air_ref_sub_;
  rclcpp::Subscription<std_msgs::msg::String>::SharedPtr air_status_sub_;

  // ADR-0021：新固定预算任务 FCO（独立组件；不参与旧 visibility_metrics）
  agc_task::MissionFcoConfig mission_fco_cfg_;
  agc_task::MissionFcoFixedBudget mission_fco_;

  std::chrono::steady_clock::time_point start_wall_;
  // 起止事件 + RTF（sim 缺省 -1.0；have_sim_ 标注是否采到仿真时间）
  double sim_start_s_{-1.0}, sim_end_s_{-1.0};
  bool have_sim_{false};
  double wall_start_unix_s_{0.0}, wall_end_unix_s_{0.0};
  fs::path run_dir_;
  rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr odom_valid_sub_, reset_failed_sub_;
  rclcpp::Subscription<geometry_msgs::msg::TwistStamped>::SharedPtr cmd_sub_;
  rclcpp::Subscription<agc_msgs::msg::AgcTaskState>::SharedPtr state_sub_;
  rclcpp::Subscription<nav_msgs::msg::Odometry>::SharedPtr odom_sub_;
  rclcpp::Subscription<sensor_msgs::msg::LaserScan>::SharedPtr scan_sub_;
  rclcpp::Subscription<nav2_msgs::msg::CollisionMonitorState>::SharedPtr cm_sub_;
  rclcpp::Subscription<std_msgs::msg::Int32>::SharedPtr reset_retries_sub_;
  // 接触真值订阅（contact_topic 为空时不创建）
  rclcpp::Subscription<ros_gz_interfaces::msg::Contacts>::SharedPtr contact_sub_;
};

#endif  // AGC_TASK_RUN_LOGGER_HPP_
