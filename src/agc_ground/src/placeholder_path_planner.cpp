// G2 几何/直连占位全局规划器（ADR-0013 当前占位阶段）。
//
// 职责**只有一件**：把"当前车位 → 任务目标"连成一条 `/agc/ground/path`
// （`nav_msgs/Path`，`header.frame_id=world`）。它**不发布任何速度**，因此不是第二命令者。
//
// 边界（本单明令，不得放宽）：
//   * **不是** Navfn / `nav2_navfn_planner`，**不接** Nav2 planner_server，**不起** costmap；
//     路径是"几何直连"——只在无遮挡直达场景成立，**不保证避障**、不追求质量与最优性。
//   * **不是** `ground_baseline`（后者 = Navfn + LQR + 自持 costmap 的离线对照整链）；
//     本节点与其无依赖，也不复用其 costmap 参数。
//   * **不消费**路径（消费端在 `agc_rl` 侧）；除 odom/goal/state 外不引入其它必要输入。
//
// 失效语义（ADR-0013）——发布侧只负责"不发坏的"，判活在消费侧：
//   * 无 odom / 无 goal / goal 过期 / 任务未授权 → **不发**（不重发旧路径刷新 stamp；
//     那等于用 now() 掩盖过期，明令禁止）；
//   * 目标位移 > `replan_displacement_m`、或车位位移 > `replan_displacement_m`、
//     或到达 `replan_period_s` → 重新生成；
//   * 车距 goal ≤ `goal_reached_tol_m` → 发布一条**退化但合法**（2 点、同一点）的路径，
//     让消费侧能判"已到位"而不是"路径消失"。
//
// 时间语义：`header.stamp` 取本节点当前 ROS 时钟（`use_sim_time` 下即 `/clock`），
// 消费侧用同一时钟算年龄；仿真 reset 造成的时跳会在消费侧被判为不可信（STALE），
// 不会被静默当作新鲜。

#include <algorithm>
#include <chrono>
#include <cmath>
#include <memory>
#include <string>

#include "rclcpp/rclcpp.hpp"
#include "geometry_msgs/msg/pose_stamped.hpp"
#include "nav_msgs/msg/odometry.hpp"
#include "nav_msgs/msg/path.hpp"
#include "agc_msgs/msg/agc_task_state.hpp"

namespace agc_ground
{

class PlaceholderPathPlanner : public rclcpp::Node
{
public:
  PlaceholderPathPlanner()
  : rclcpp::Node("placeholder_path_planner")
  {
    odom_topic_ = declare_parameter<std::string>("odom_topic", "/agc/ground/odom");
    goal_topic_ = declare_parameter<std::string>("goal_topic", "/agc/ground/goal");
    state_topic_ = declare_parameter<std::string>("state_topic", "/agc/task/state");
    path_topic_ = declare_parameter<std::string>("path_topic", "/agc/ground/path");
    world_frame_ = declare_parameter<std::string>("world_frame", "world");
    rate_hz_ = declare_parameter<double>("rate_hz", 5.0);
    spacing_m_ = declare_parameter<double>("path_spacing_m", 0.5);
    replan_period_s_ = declare_parameter<double>("replan_period_s", 2.0);
    replan_displacement_m_ = declare_parameter<double>("replan_displacement_m", 1.0);
    goal_tol_m_ = declare_parameter<double>("goal_reached_tol_m", 0.3);
    goal_timeout_s_ = declare_parameter<double>("goal_timeout_s", 2.0);
    odom_timeout_s_ = declare_parameter<double>("odom_timeout_s", 0.5);
    require_task_auth_ = declare_parameter<bool>("require_task_auth", true);

    path_pub_ = create_publisher<nav_msgs::msg::Path>(path_topic_, 1);

    odom_sub_ = create_subscription<nav_msgs::msg::Odometry>(
      odom_topic_, 20,
      [this](nav_msgs::msg::Odometry::SharedPtr msg) {
        car_x_ = msg->pose.pose.position.x;
        car_y_ = msg->pose.pose.position.y;
        have_odom_ = true;
        odom_stamp_ = now();
      });

    goal_sub_ = create_subscription<geometry_msgs::msg::PoseStamped>(
      goal_topic_, 20,
      [this](geometry_msgs::msg::PoseStamped::SharedPtr msg) {
        goal_x_ = msg->pose.position.x;
        goal_y_ = msg->pose.position.y;
        have_goal_ = true;
        goal_stamp_ = now();
      });

    state_sub_ = create_subscription<agc_msgs::msg::AgcTaskState>(
      state_topic_, 20,
      [this](agc_msgs::msg::AgcTaskState::SharedPtr msg) {state_ = msg->state;});

    const auto period = std::chrono::duration<double>(1.0 / std::max(rate_hz_, 1e-3));
    timer_ = create_wall_timer(
      std::chrono::duration_cast<std::chrono::nanoseconds>(period),
      std::bind(&PlaceholderPathPlanner::tick, this));

    RCLCPP_INFO(
      get_logger(),
      "G2 占位规划器：goal=%s odom=%s path=%s frame=%s rate=%.1fHz spacing=%.2fm "
      "replan(period=%.1fs disp=%.2fm) —— 几何直连，非 Navfn、无 costmap",
      goal_topic_.c_str(), odom_topic_.c_str(), path_topic_.c_str(),
      world_frame_.c_str(), rate_hz_, spacing_m_, replan_period_s_, replan_displacement_m_);
  }

private:
  // 输入是否新鲜。**负年龄一律拒绝**：仿真 reset / 时钟回跳后，reset **之前**收到的
  // odom/goal 会得到 `now - t < 0`；若只判 `<= limit`，这些旧输入会在新时刻被"重新包装"
  // 成新鲜数据，进而用旧车位/旧目标发布新路径（round-1 review B3）。
  bool fresh(const rclcpp::Time & t, double limit_s) const
  {
    if (limit_s <= 0.0) {
      return true;
    }
    const double age = (now() - t).seconds();
    return age >= 0.0 && age <= limit_s;
  }

  // 与 RL 节点同口径：仅 GROUND_APPROACH 允许规划。
  bool authorized() const
  {
    return !require_task_auth_ || state_ == agc_msgs::msg::AgcTaskState::GROUND_APPROACH;
  }

  void tick()
  {
    if (!have_odom_ || !have_goal_ || !authorized()) {
      return;
    }
    if (!fresh(odom_stamp_, odom_timeout_s_) || !fresh(goal_stamp_, goal_timeout_s_)) {
      return;
    }

    const rclcpp::Time t = now();
    const double goal_moved = std::hypot(goal_x_ - planned_goal_x_, goal_y_ - planned_goal_y_);
    const double car_moved = std::hypot(car_x_ - planned_car_x_, car_y_ - planned_car_y_);
    const bool need =
      !have_plan_ ||
      goal_moved > replan_displacement_m_ ||
      car_moved > replan_displacement_m_ ||
      (replan_period_s_ > 0.0 && (t - last_plan_time_).seconds() >= replan_period_s_);
    if (!need) {
      return;
    }

    publishPath(t);
    planned_goal_x_ = goal_x_;
    planned_goal_y_ = goal_y_;
    planned_car_x_ = car_x_;
    planned_car_y_ = car_y_;
    last_plan_time_ = t;
    have_plan_ = true;
  }

  void publishPath(const rclcpp::Time & stamp)
  {
    const double dx = goal_x_ - car_x_;
    const double dy = goal_y_ - car_y_;
    const double dist = std::hypot(dx, dy);
    const bool arrived = dist <= goal_tol_m_;
    const double step = std::max(spacing_m_, 1e-3);

    // 已到位：发布 2 点同点位路径（保持"路径存在且末端==goal"，消费侧据此判完成）。
    // 未到位：按 spacing 等距采样直线段，末点精确落在 goal 上（不因取整丢末端）。
    int n = static_cast<int>(std::ceil(dist / step));
    if (arrived) {
      n = 1;
    }
    n = std::max(1, n);

    nav_msgs::msg::Path path;
    path.header.stamp = stamp;
    path.header.frame_id = world_frame_;
    path.poses.reserve(static_cast<size_t>(n) + 1);
    for (int i = 0; i <= n; ++i) {
      const double f = static_cast<double>(i) / static_cast<double>(n);
      geometry_msgs::msg::PoseStamped ps;
      ps.header = path.header;
      ps.pose.position.x = car_x_ + f * dx;
      ps.pose.position.y = car_y_ + f * dy;
      ps.pose.position.z = 0.0;
      // 朝向取路径切线方向（末端沿用最后一段），供消费侧做航向参考。
      ps.pose.orientation.x = 0.0;
      ps.pose.orientation.y = 0.0;
      ps.pose.orientation.z = std::sin(0.5 * std::atan2(dy, dx));
      ps.pose.orientation.w = std::cos(0.5 * std::atan2(dy, dx));
      path.poses.push_back(ps);
    }
    path_pub_->publish(path);
  }

  std::string odom_topic_, goal_topic_, state_topic_, path_topic_, world_frame_;
  double rate_hz_{5.0}, spacing_m_{0.5}, replan_period_s_{2.0}, replan_displacement_m_{1.0};
  double goal_tol_m_{0.3}, goal_timeout_s_{2.0}, odom_timeout_s_{0.5};
  bool require_task_auth_{true};

  double car_x_{0.0}, car_y_{0.0}, goal_x_{0.0}, goal_y_{0.0};
  double planned_car_x_{0.0}, planned_car_y_{0.0}, planned_goal_x_{0.0}, planned_goal_y_{0.0};
  bool have_odom_{false}, have_goal_{false}, have_plan_{false};
  uint8_t state_{agc_msgs::msg::AgcTaskState::IDLE};
  rclcpp::Time odom_stamp_{0, 0, RCL_ROS_TIME};
  rclcpp::Time goal_stamp_{0, 0, RCL_ROS_TIME};
  rclcpp::Time last_plan_time_{0, 0, RCL_ROS_TIME};

  rclcpp::Publisher<nav_msgs::msg::Path>::SharedPtr path_pub_;
  rclcpp::Subscription<nav_msgs::msg::Odometry>::SharedPtr odom_sub_;
  rclcpp::Subscription<geometry_msgs::msg::PoseStamped>::SharedPtr goal_sub_;
  rclcpp::Subscription<agc_msgs::msg::AgcTaskState>::SharedPtr state_sub_;
  rclcpp::TimerBase::SharedPtr timer_;
};

}  // namespace agc_ground

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<agc_ground::PlaceholderPathPlanner>());
  rclcpp::shutdown();
  return 0;
}
