// ground_safety_filter —— 地面安全层（自研，ADR-0045）
//
// 唯一职责：把 `/agc/ground/cmd_vel_raw` 的**速度意图**按可停性判据裁剪或归零，
// 输出到契约唯一执行口 `/agc/ground/cmd_vel`。**只裁不造**：不规划、不绕行、不生成目标、
// 不接管任务状态，因而不是第二命令者。
//
// 与 Nav2 collision_monitor 的两处关键差别（ADR-0045 的 #why）：
// ① **启动即发零速**：本节点用定时器**无条件**周期发布，从未收到任何输入时也发零速；
//    旧实现只在 cmd_vel 回调里跑判定，命令源缺失时一条消息都不发。
// ② **输入自身带时效**：命令 / 车体 / 地图 / 任务许可各自独立超时，超时即零速。
//
// 障碍输入**只有** `/agc/map`（任务1 的规划层地图）：不订阅 scan / 点云 / costmap，
// 因此不存在第二份障碍表示。判定逻辑全在 `safety_policy.hpp`（纯类，可脱 ROS 单测）。

#include <chrono>
#include <cmath>
#include <cstring>
#include <memory>
#include <string>
#include <vector>

#include <rclcpp/rclcpp.hpp>
#include <geometry_msgs/msg/twist_stamped.hpp>
#include <nav_msgs/msg/occupancy_grid.hpp>
#include <nav_msgs/msg/odometry.hpp>
#include <std_msgs/msg/bool.hpp>
#include <std_msgs/msg/string.hpp>

#include <agc_msgs/msg/agc_task_state.hpp>

#include "agc_ground/safety_policy.hpp"

namespace
{

double yawFromQuat(const geometry_msgs::msg::Quaternion & q)
{
  return std::atan2(
    2.0 * (q.w * q.z + q.x * q.y),
    1.0 - 2.0 * (q.y * q.y + q.z * q.z));
}

bool finiteQuat(const geometry_msgs::msg::Quaternion & q)
{
  if (!std::isfinite(q.x) || !std::isfinite(q.y) || !std::isfinite(q.z) ||
    !std::isfinite(q.w))
  {
    return false;
  }
  const double n = std::sqrt(q.x * q.x + q.y * q.y + q.z * q.z + q.w * q.w);
  return std::fabs(n - 1.0) <= 1e-2;
}

}  // namespace

class GroundSafetyFilter : public rclcpp::Node
{
public:
  GroundSafetyFilter()
  : Node("ground_safety_filter")
  {
    const auto in_topic = declare_parameter<std::string>(
      "cmd_in_topic", "/agc/ground/cmd_vel_raw");
    const auto out_topic = declare_parameter<std::string>(
      "cmd_out_topic", "/agc/ground/cmd_vel");
    const auto map_topic = declare_parameter<std::string>("map_topic", "/agc/map");
    const auto map_valid_topic = declare_parameter<std::string>(
      "map_valid_topic", "/agc/map/valid");
    const auto odom_topic = declare_parameter<std::string>(
      "odom_topic", "/agc/ground/odom");
    const auto odom_valid_topic = declare_parameter<std::string>(
      "odom_valid_topic", "/agc/ground/odom_valid");
    const auto state_topic = declare_parameter<std::string>(
      "state_topic", "/agc/task/state");
    const auto status_topic = declare_parameter<std::string>(
      "status_topic", "/agc/ground/safety_status");
    expected_cmd_frame_ = declare_parameter<std::string>(
      "expected_cmd_frame", "car/base_link");
    expected_map_frame_ = declare_parameter<std::string>(
      "expected_map_frame", "world");
    rate_hz_ = declare_parameter<double>("rate_hz", 20.0);
    budget_ms_ = declare_parameter<double>("budget_ms", 20.0);
    // 步进式"整拍预算"：实际测量耗时会写进诊断；超过 budget_ms 记 BUDGET_EXCEEDED。
    // 这样"超预算"是一条**显式状态**，不是静默变慢。

    agc_ground::SafetyParams p;
    p.d_emergency = declare_parameter<double>("d_emergency", p.d_emergency);
    p.d_collision = declare_parameter<double>("d_collision", p.d_collision);
    p.d_safety = declare_parameter<double>("d_safety", p.d_safety);
    p.d_recover_slow = declare_parameter<double>("d_recover_slow", p.d_collision);
    p.d_recover_pass = declare_parameter<double>("d_recover_pass", p.d_safety + 0.5);
    p.recover_ticks = declare_parameter<int>("recover_ticks", p.recover_ticks);
    p.t_cmd_timeout = declare_parameter<double>("t_cmd_timeout", p.t_cmd_timeout);
    p.t_body_timeout = declare_parameter<double>("t_body_timeout", p.t_body_timeout);
    p.t_map_timeout = declare_parameter<double>("t_map_timeout", p.t_map_timeout);
    p.t_permit_timeout = declare_parameter<double>("t_permit_timeout", p.t_permit_timeout);
    p.v_cap = declare_parameter<double>("v_cap", p.v_cap);
    p.w_cap = declare_parameter<double>("w_cap", p.w_cap);
    p.footprint_half_length = declare_parameter<double>(
      "footprint_half_length", p.footprint_half_length);
    p.footprint_half_width = declare_parameter<double>(
      "footprint_half_width", p.footprint_half_width);
    p.a_brake = declare_parameter<double>("a_brake", p.a_brake);
    p.t_react = declare_parameter<double>("t_react", p.t_react);
    p.cell_epsilon = declare_parameter<double>("cell_epsilon", p.cell_epsilon);
    p.slow_min_ratio = declare_parameter<double>("slow_min_ratio", p.slow_min_ratio);
    p.unknown_ratio_limit = declare_parameter<double>(
      "unknown_ratio_limit", p.unknown_ratio_limit);
    p.sweep_cell_limit = declare_parameter<int>("sweep_cell_limit", p.sweep_cell_limit);
    p.sweep_pose_samples = declare_parameter<int>(
      "sweep_pose_samples", p.sweep_pose_samples);
    p.permit_require = declare_parameter<bool>("permit_require", p.permit_require);
    const auto permit_states = declare_parameter<std::vector<int64_t>>(
      "permit_states", {3, 4});   // GROUND_APPROACH / TRACKING_SUCCESS
    p.permit_states.clear();
    for (auto s : permit_states) {p.permit_states.push_back(static_cast<int>(s));}

    policy_.setParams(p);
    // **启动期拒绝非法参数**：静默夹到合法区间会让"配置意图"与"实际行为"脱节。
    if (!policy_.paramsError().empty()) {
      RCLCPP_ERROR(
        get_logger(), "参数非法，拒绝启动：%s（ADR-0045）", policy_.paramsError().c_str());
      throw std::runtime_error("ground_safety_filter: " + policy_.paramsError());
    }

    // 输出用**非 latched、非 transient_local**：这是持续的实时命令流，不是状态快照。
    pub_ = create_publisher<geometry_msgs::msg::TwistStamped>(out_topic, 10);
    // 诊断 latched（transient_local）：任何时刻都能读到最近一次判定（非 ABI、非命令者）。
    status_pub_ = create_publisher<std_msgs::msg::String>(
      status_topic, rclcpp::QoS(1).transient_local());

    sub_cmd_ = create_subscription<geometry_msgs::msg::TwistStamped>(
      in_topic, 10,
      [this](geometry_msgs::msg::TwistStamped::SharedPtr m) {onCommand(*m);});
    // 地图是 latched + reliable（map_adapter 的发布 QoS），订阅端必须匹配 durability，
    // 否则晚启动的安全层会一直等不到第一帧（"话题存在 ≠ 有数据"）。
    sub_map_ = create_subscription<nav_msgs::msg::OccupancyGrid>(
      map_topic, rclcpp::QoS(1).transient_local().reliable(),
      [this](nav_msgs::msg::OccupancyGrid::SharedPtr m) {onMap(*m);});
    sub_map_valid_ = create_subscription<std_msgs::msg::Bool>(
      map_valid_topic, rclcpp::QoS(1).transient_local().reliable(),
      [this](std_msgs::msg::Bool::SharedPtr m) {map_valid_ = m->data; have_map_valid_ = true;});
    sub_odom_ = create_subscription<nav_msgs::msg::Odometry>(
      odom_topic, 20,
      [this](nav_msgs::msg::Odometry::SharedPtr m) {onOdom(*m);});
    sub_odom_valid_ = create_subscription<std_msgs::msg::Bool>(
      odom_valid_topic, 10,
      [this](std_msgs::msg::Bool::SharedPtr m) {odom_valid_ = m->data; have_odom_valid_ = true;});
    sub_state_ = create_subscription<agc_msgs::msg::AgcTaskState>(
      state_topic, 10,
      [this](agc_msgs::msg::AgcTaskState::SharedPtr m) {onState(*m);});

    const double hz = (std::isfinite(rate_hz_) && rate_hz_ > 1.0) ? rate_hz_ : 20.0;
    const auto period = std::chrono::duration<double>(1.0 / hz);
    timer_ = create_wall_timer(
      std::chrono::duration_cast<std::chrono::nanoseconds>(period),
      std::bind(&GroundSafetyFilter::tick, this));

    RCLCPP_INFO(
      get_logger(),
      "地面安全层启动：%s → %s；唯一障碍输入 %s（不订阅 scan/costmap）；%.1f Hz；预算 %.1f ms",
      in_topic.c_str(), out_topic.c_str(), map_topic.c_str(), hz, budget_ms_);
  }

private:
  void onCommand(const geometry_msgs::msg::TwistStamped & m)
  {
    cmd_ = m;
    have_cmd_ = true;
    cmd_rx_mono_ = std::chrono::steady_clock::now();
  }

  void onMap(const nav_msgs::msg::OccupancyGrid & m)
  {
    map_ = m;
    have_map_ = true;
    map_stamp_s_ = rclcpp::Time(m.header.stamp).seconds();
    map_frame_ok_ = (m.header.frame_id == expected_map_frame_);
  }

  void onOdom(const nav_msgs::msg::Odometry & m)
  {
    odom_ = m;
    have_odom_ = true;
    odom_stamp_s_ = rclcpp::Time(m.header.stamp).seconds();
    odom_finite_ = finiteQuat(m.pose.pose.orientation) &&
      std::isfinite(m.pose.pose.position.x) && std::isfinite(m.pose.pose.position.y);
  }

  void onState(const agc_msgs::msg::AgcTaskState & m)
  {
    task_state_ = m.state;
    have_permit_ = true;
    permit_stamp_s_ = rclcpp::Time(m.header.stamp).seconds();
  }

  void tick()
  {
    const auto t0 = std::chrono::steady_clock::now();

    agc_ground::SafetyInputs in;
    in.now_s = now().seconds();

    in.has_command = have_cmd_;
    if (have_cmd_) {
      in.command.v = cmd_.twist.linear.x;
      in.command.w = cmd_.twist.angular.z;
      in.command.frame_ok = (cmd_.header.frame_id == expected_cmd_frame_);
      in.command.finite =
        std::isfinite(cmd_.twist.linear.x) && std::isfinite(cmd_.twist.linear.y) &&
        std::isfinite(cmd_.twist.linear.z) && std::isfinite(cmd_.twist.angular.x) &&
        std::isfinite(cmd_.twist.angular.y) && std::isfinite(cmd_.twist.angular.z);
      in.command.holonomic_ok = std::fabs(cmd_.twist.linear.y) <= 1e-6;
      // 命令年龄用**单调钟**量（与 ROS 时钟解耦）：时钟冻结/回拨时 ROS 年龄恒为 0，
      // 会静默把极旧命令当新鲜。stamp 只用于"未来时间戳"这一条显式异常。
      const double mono_age = std::chrono::duration<double>(
        std::chrono::steady_clock::now() - cmd_rx_mono_).count();
      in.command.stamp_s = in.now_s - mono_age;
    }

    in.has_body = have_odom_;
    if (have_odom_) {
      in.body.x = odom_.pose.pose.position.x;
      in.body.y = odom_.pose.pose.position.y;
      in.body.yaw = yawFromQuat(odom_.pose.pose.orientation);
      in.body.valid = have_odom_valid_ ? odom_valid_ : true;
      in.body.finite = odom_finite_;
      in.body.stamp_s = odom_stamp_s_;
    }

    in.has_map = have_map_;
    if (have_map_) {
      in.map.data = map_.data.empty() ? nullptr : map_.data.data();
      in.map.width = static_cast<int>(map_.info.width);
      in.map.height = static_cast<int>(map_.info.height);
      in.map.resolution = map_.info.resolution;
      in.map.origin_x = map_.info.origin.position.x;
      in.map.origin_y = map_.info.origin.position.y;
      in.map.frame_ok = map_frame_ok_;
      in.map.stamp_s = map_stamp_s_;
      // 尺寸自洽：`data.size()` 必须等于 `width*height`，否则逐格读取会越界。
      const size_t expect = static_cast<size_t>(in.map.width) *
        static_cast<size_t>(in.map.height);
      if (in.map.data == nullptr || map_.data.size() != expect ||
        in.map.width <= 0 || in.map.height <= 0)
      {
        in.map.data = nullptr;
      }
    }
    // `/agc/map/valid=false` 才是"知识不新鲜"的权威判据；没收到过就按 null 处理（缺省 true），
    // 因为地图自身的时间戳超时已由 t_map_timeout 兜住。
    in.map_valid_flag = have_map_valid_ ? map_valid_ : true;

    in.has_permit = have_permit_;
    if (have_permit_) {
      in.permit.state = static_cast<int>(task_state_);
      in.permit.stamp_s = permit_stamp_s_;
    }

    auto decision = policy_.step(in);

    const double elapsed_ms = std::chrono::duration<double, std::milli>(
      std::chrono::steady_clock::now() - t0).count();
    decision.diag.budget_ms = elapsed_ms;
    // 超预算是一条**显式状态**：算慢了这个事实必须能进判定结论，否则只会表现为掉帧。
    if (elapsed_ms > budget_ms_ && agc_ground::isDrivingState(decision.state)) {
      decision.state = agc_ground::SafetyState::kBudgetExceeded;
      decision.out_v = 0.0;
      decision.out_w = 0.0;
      decision.reason = "budget " + std::to_string(elapsed_ms) + " ms > " +
        std::to_string(budget_ms_) + " ms";
    }

    publishCommand(decision);
    publishStatus(decision);
  }

  void publishCommand(const agc_ground::SafetyDecision & d)
  {
    geometry_msgs::msg::TwistStamped out;
    out.header.stamp = now();
    out.header.frame_id = expected_cmd_frame_;
    out.twist.linear.x = d.out_v;
    out.twist.angular.z = d.out_w;
    pub_->publish(out);
    // 状态变化时打一条（节流）：稳态不刷屏，但转变必须可见。
    if (d.state != last_logged_state_) {
      if (agc_ground::isDrivingState(d.state)) {
        RCLCPP_INFO(
          get_logger(), "安全层 %s → %s（%s）v=%.3f w=%.3f",
          agc_ground::toString(last_logged_state_), agc_ground::toString(d.state),
          d.reason.c_str(), d.out_v, d.out_w);
      } else {
        RCLCPP_WARN(
          get_logger(), "安全层 %s → %s（%s）零速",
          agc_ground::toString(last_logged_state_), agc_ground::toString(d.state),
          d.reason.c_str());
      }
      last_logged_state_ = d.state;
    }
  }

  void publishStatus(const agc_ground::SafetyDecision & d)
  {
    std_msgs::msg::String m;
    m.data = agc_ground::SafetyPolicy::toJson(d, policy_.params());
    status_pub_->publish(m);
  }

  std::string expected_cmd_frame_, expected_map_frame_;
  double rate_hz_{20.0}, budget_ms_{20.0};

  agc_ground::SafetyPolicy policy_;
  agc_ground::SafetyState last_logged_state_{agc_ground::SafetyState::kStartup};

  geometry_msgs::msg::TwistStamped cmd_;
  bool have_cmd_{false};
  std::chrono::steady_clock::time_point cmd_rx_mono_{};

  nav_msgs::msg::OccupancyGrid map_;
  bool have_map_{false}, map_frame_ok_{false};
  double map_stamp_s_{0.0};

  bool map_valid_{true}, have_map_valid_{false};

  nav_msgs::msg::Odometry odom_;
  bool have_odom_{false}, odom_finite_{true};
  double odom_stamp_s_{0.0};
  bool odom_valid_{true}, have_odom_valid_{false};

  uint8_t task_state_{0};
  bool have_permit_{false};
  double permit_stamp_s_{0.0};

  rclcpp::Publisher<geometry_msgs::msg::TwistStamped>::SharedPtr pub_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr status_pub_;
  rclcpp::Subscription<geometry_msgs::msg::TwistStamped>::SharedPtr sub_cmd_;
  rclcpp::Subscription<nav_msgs::msg::OccupancyGrid>::SharedPtr sub_map_;
  rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr sub_map_valid_;
  rclcpp::Subscription<nav_msgs::msg::Odometry>::SharedPtr sub_odom_;
  rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr sub_odom_valid_;
  rclcpp::Subscription<agc_msgs::msg::AgcTaskState>::SharedPtr sub_state_;
  rclcpp::TimerBase::SharedPtr timer_;
};

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<GroundSafetyFilter>());
  rclcpp::shutdown();
  return 0;
}
