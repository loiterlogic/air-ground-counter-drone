// hybrid_astar_se2_planner —— 地面全局路径规划器（Hybrid A* on SE(2)）
//
// 职责**只有一件**：把「当前车位 → 任务目标」规划成一条 `/agc/ground/path`
// （`nav_msgs/Path`，`header.frame_id=world`）。它**不发布任何速度**，因此不是第二命令者。
//
// ## 名字为什么这么长
//
// 用户裁定（2026-11-14）：这不会是唯一一种规划算法，所以按**方法特点**命名，
// 不能叫 `ground_path_planner` —— 那会让它占住「地面主方案」的位置。
// 名字里的 `hybrid_astar_se2` 说明「这是搜索式、SE(2) 状态空间的那一种」。
//
// ## 边界（本单明令，不得放宽）
//
// * **不是** Nav2 `planner_server` / `navfn` / costmap；不链接任何 `nav2_*`。
// * **不发速度**：不发布 `/agc/ground/cmd_vel_raw` / `cmd_vel` / Gazebo 速度话题。
// * 不订阅 `scan` / 点云 / costmap —— 唯一障碍输入是 `/agc/map`
//   （与安全层同源，[ADR-0045](../../../docs/adr/0045-ground-safety-layer-self-owned.md#top)）。
// * 不新增 `planner_mode` / `planner_backend` / `path_source` 之类运行时路线开关。
//
// ## 失效语义（ADR-0013）
//
// 发布侧只负责「不发坏的」，判活在消费侧：
// * 无 odom / 无 goal / goal 无效 / 任务未授权 → **不发**（不重发旧路径刷新 stamp）；
// * 规划失败 → **不发**，发诊断；由消费侧的 `path.max_age_s` 过期门把它变成零速
//   （用户裁定 2026-11-14：不发布退化路径，也不发布空 poses 路径 ——
//   后者会用新 stamp 掩盖「本条路径已失效」，违反 ADR-0013 的精神）；
// * 车距 goal ≤ `goal_reached_tol_m` → 发布一条**退化但合法**（2 点同点）的路径，
//   让消费侧能判「已到位」而不是「路径消失」。
//
// ## 执行器为什么是单线程
//
// `rclcpp::spin`：回调与定时器天然串行，因此「规划期间地图不被改」由拓扑保证，
// 不需要深拷贝 4 万格做快照。规划的墙钟预算由 `PlannerParams::search_time_budget_s`
// 硬约束（超时即 `SEARCH_TIMEOUT` 并返回），不会把地图回调饿死太久。
// 若将来改多线程执行器，必须在这里补真拷贝 —— 见 ADR-0048 的「执行器」一节。
//
// ## 时间语义
//
// `header.stamp` 取本节点当前 ROS 时钟（`use_sim_time` 下即 `/clock`），
// 消费侧用同一时钟算年龄；仿真 reset 造成的时跳会在消费侧被判 STALE。

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <memory>
#include <string>
#include <vector>

#include "rclcpp/rclcpp.hpp"
#include "geometry_msgs/msg/pose_stamped.hpp"
#include "nav_msgs/msg/occupancy_grid.hpp"
#include "nav_msgs/msg/odometry.hpp"
#include "nav_msgs/msg/path.hpp"
#include "std_msgs/msg/bool.hpp"
#include "std_msgs/msg/string.hpp"
#include "agc_msgs/msg/agc_task_state.hpp"

#include "agc_ground/planner_engine.hpp"
#include "agc_ground/planner_interface.hpp"
#include "agc_ground/planner_types.hpp"

namespace agc_ground
{

namespace planner_ros
{

// 从四元数解 yaw（只取 z/w：地面车没有 roll/pitch 自由度）。
inline double yawFromQuat(double z, double w)
{
  return std::atan2(2.0 * w * z, 1.0 - 2.0 * z * z);
}

// `goal_info` 的 `valid=` 解析（`valid=0` 表示失效）。
inline bool parseGoalInfoValid(const std::string & s)
{
  return s.find("valid=0") == std::string::npos;
}

}  // namespace planner_ros

class HybridAstarSe2PlannerNode : public rclcpp::Node
{
public:
  HybridAstarSe2PlannerNode()
  : rclcpp::Node("hybrid_astar_se2_planner")
  {
    // ---- 话题 ----
    map_topic_ = declare_parameter<std::string>("map_topic", "/agc/map");
    map_valid_topic_ = declare_parameter<std::string>("map_valid_topic", "/agc/map/valid");
    odom_topic_ = declare_parameter<std::string>("odom_topic", "/agc/ground/odom");
    odom_valid_topic_ = declare_parameter<std::string>(
      "odom_valid_topic", "/agc/ground/odom_valid");
    goal_topic_ = declare_parameter<std::string>("goal_topic", "/agc/ground/goal");
    goal_info_topic_ = declare_parameter<std::string>(
      "goal_info_topic", "/agc/ground/goal_info");
    state_topic_ = declare_parameter<std::string>("state_topic", "/agc/task/state");
    path_topic_ = declare_parameter<std::string>("path_topic", "/agc/ground/path");
    status_topic_ = declare_parameter<std::string>(
      "status_topic", "/agc/ground/planner_status");
    world_frame_ = declare_parameter<std::string>("world_frame", "world");

    // ---- 时序 ----
    rate_hz_ = declare_parameter<double>("rate_hz", 5.0);
    map_timeout_s_ = declare_parameter<double>("map_timeout_s", 2.0);
    odom_timeout_s_ = declare_parameter<double>("odom_timeout_s", 0.5);
    goal_timeout_s_ = declare_parameter<double>("goal_timeout_s", 2.0);
    require_task_auth_ = declare_parameter<bool>("require_task_auth", true);

    // ---- 重规划判据 ----
    replan_period_s_ = declare_parameter<double>("replan_period_s", 2.0);
    replan_displacement_m_ = declare_parameter<double>("replan_displacement_m", 1.0);
    max_path_age_s_ = declare_parameter<double>("max_path_age_s", 5.0);
    signature_free_delta_cells_ = declare_parameter<int>("signature_free_delta_cells", 200);

    // ---- 路径 ----
    goal_tol_m_ = declare_parameter<double>("goal_reached_tol_m", 0.3);

    // ---- 规划参数 ----
    params_.footprint_half_length = declare_parameter<double>(
      "footprint_half_length", params_.footprint_half_length);
    params_.footprint_half_width = declare_parameter<double>(
      "footprint_half_width", params_.footprint_half_width);
    params_.footprint_margin = declare_parameter<double>(
      "footprint_margin", params_.footprint_margin);
    params_.primitive_dt = declare_parameter<double>("primitive_dt", params_.primitive_dt);
    params_.primitive_max_step_m = declare_parameter<double>(
      "primitive_max_step_m", params_.primitive_max_step_m);
    params_.yaw_bins = declare_parameter<int>("yaw_bins", params_.yaw_bins);
    params_.search_time_budget_s = declare_parameter<double>(
      "search_time_budget_s", params_.search_time_budget_s);
    params_.max_expanded_nodes = declare_parameter<int>(
      "max_expanded_nodes", params_.max_expanded_nodes);
    params_.goal_position_tolerance_m = declare_parameter<double>(
      "goal_position_tolerance_m", params_.goal_position_tolerance_m);
    params_.heuristic_weight = declare_parameter<double>(
      "heuristic_weight", params_.heuristic_weight);
    params_.clearance_target_m = declare_parameter<double>(
      "clearance_target_m", params_.clearance_target_m);
    params_.corridor_enabled = declare_parameter<bool>(
      "corridor_enabled", params_.corridor_enabled);
    params_.corridor_clearance_m = declare_parameter<double>(
      "corridor_clearance_m", params_.corridor_clearance_m);
    params_.corridor_max_scan_m = declare_parameter<double>(
      "corridor_max_scan_m", params_.corridor_max_scan_m);
    params_.optimization_enabled = declare_parameter<bool>(
      "optimization_enabled", params_.optimization_enabled);
    params_.optimization_max_iterations = declare_parameter<int>(
      "optimization_max_iterations", params_.optimization_max_iterations);
    params_.optimization_time_budget_s = declare_parameter<double>(
      "optimization_time_budget_s", params_.optimization_time_budget_s);
    params_.kappa_max = declare_parameter<double>("kappa_max", params_.kappa_max);
    params_.v_cap = declare_parameter<double>("v_cap", params_.v_cap);
    params_.w_cap = declare_parameter<double>("w_cap", params_.w_cap);
    params_.a_lat_max = declare_parameter<double>("a_lat_max", params_.a_lat_max);
    params_.a_acc_max = declare_parameter<double>("a_acc_max", params_.a_acc_max);
    params_.a_brake_max = declare_parameter<double>("a_brake_max", params_.a_brake_max);
    params_.w_acc_max = declare_parameter<double>("w_acc_max", params_.w_acc_max);
    params_.direct_link_enabled = declare_parameter<bool>(
      "direct_link_enabled", params_.direct_link_enabled);
    params_.resample_spacing_m = declare_parameter<double>(
      "resample_spacing_m", params_.resample_spacing_m);
    params_.signature_free_delta_cells = signature_free_delta_cells_;

    // ---- 发布 ----
    path_pub_ = create_publisher<nav_msgs::msg::Path>(path_topic_, 1);
    // 诊断：非命令型，transient_local（与 `/agc/ground/safety_status` 同款）。
    status_pub_ = create_publisher<std_msgs::msg::String>(
      status_topic_, rclcpp::QoS(1).transient_local());

    // ---- 订阅：只更新带时间戳的缓存，**不在回调里规划** ----
    const auto latched = rclcpp::QoS(1).transient_local();
    map_sub_ = create_subscription<nav_msgs::msg::OccupancyGrid>(
      map_topic_, latched,
      [this](nav_msgs::msg::OccupancyGrid::SharedPtr msg) {onMap(msg);});
    map_valid_sub_ = create_subscription<std_msgs::msg::Bool>(
      map_valid_topic_, latched,
      [this](std_msgs::msg::Bool::SharedPtr msg) {
        map_valid_ = msg->data;
        have_map_valid_ = true;
      });
    odom_sub_ = create_subscription<nav_msgs::msg::Odometry>(
      odom_topic_, 20,
      [this](nav_msgs::msg::Odometry::SharedPtr msg) {onOdom(msg);});
    odom_valid_sub_ = create_subscription<std_msgs::msg::Bool>(
      odom_valid_topic_, 10,
      [this](std_msgs::msg::Bool::SharedPtr msg) {
        odom_valid_ = msg->data;
        have_odom_valid_ = true;
      });
    goal_sub_ = create_subscription<geometry_msgs::msg::PoseStamped>(
      goal_topic_, 20,
      [this](geometry_msgs::msg::PoseStamped::SharedPtr msg) {onGoal(msg);});
    goal_info_sub_ = create_subscription<std_msgs::msg::String>(
      goal_info_topic_, latched,
      [this](std_msgs::msg::String::SharedPtr msg) {
        goal_info_valid_ = planner_ros::parseGoalInfoValid(msg->data);
        have_goal_info_ = true;
      });
    state_sub_ = create_subscription<agc_msgs::msg::AgcTaskState>(
      state_topic_, 20,
      [this](agc_msgs::msg::AgcTaskState::SharedPtr msg) {
        state_ = msg->state;
        state_stamp_ = now();
        have_state_ = true;
      });

    planner_ = planner::createPlanner();

    const auto period = std::chrono::duration<double>(1.0 / std::max(rate_hz_, 1e-3));
    timer_ = create_wall_timer(
      std::chrono::duration_cast<std::chrono::nanoseconds>(period),
      std::bind(&HybridAstarSe2PlannerNode::tick, this));

    RCLCPP_INFO(
      get_logger(),
      "%s：map=%s odom=%s goal=%s path=%s frame=%s rate=%.1fHz "
      "corridor=%.2fm(lethal-only) footprint_margin=%.3fm —— 不发速度",
      planner_->name().c_str(), map_topic_.c_str(), odom_topic_.c_str(),
      goal_topic_.c_str(), path_topic_.c_str(), world_frame_.c_str(), rate_hz_,
      params_.corridor_clearance_m, params_.footprint_margin);
  }

private:
  // ---- 回调：只缓存 ----

  void onMap(const nav_msgs::msg::OccupancyGrid::SharedPtr msg)
  {
    // **不在回调里规划**：地图 2 Hz 发布，规划可能跑数百毫秒到数秒；
    // 在这里规划会把地图发布线程（以及同执行器里的其它回调）阻塞。
    map_data_ = msg->data;
    map_width_ = static_cast<int>(msg->info.width);
    map_height_ = static_cast<int>(msg->info.height);
    map_resolution_ = msg->info.resolution;
    map_origin_x_ = msg->info.origin.position.x;
    map_origin_y_ = msg->info.origin.position.y;
    map_frame_ = msg->header.frame_id;
    map_stamp_ = rclcpp::Time(msg->header.stamp);
    have_map_ = true;
  }

  void onOdom(const nav_msgs::msg::Odometry::SharedPtr msg)
  {
    car_x_ = msg->pose.pose.position.x;
    car_y_ = msg->pose.pose.position.y;
    car_yaw_ = planner_ros::yawFromQuat(
      msg->pose.pose.orientation.z, msg->pose.pose.orientation.w);
    odom_stamp_ = now();
    have_odom_ = true;
  }

  void onGoal(const geometry_msgs::msg::PoseStamped::SharedPtr msg)
  {
    goal_x_ = msg->pose.position.x;
    goal_y_ = msg->pose.position.y;
    goal_stamp_ = now();
    // **不**因为任意浮点变化就强制重规划：重规划交给 needReplan 的阈值判据
    // （对齐 ADR-0013 (f)：目标变化是离散事件，位移比较用阈值而非浮点相等）。
    if (!have_goal_) {
      have_goal_ = true;
      force_replan_ = true;
    }
  }

  // 输入是否新鲜。**负年龄一律拒绝**：仿真 reset / 时钟回跳后，reset 之前收到的输入
  // 会得到 `now - t < 0`；若只判 `<= limit`，旧输入会在新时刻被「重新包装」成新鲜数据。
  bool fresh(const rclcpp::Time & t, double limit_s) const
  {
    if (limit_s <= 0.0) {return true;}
    const double age = (now() - t).seconds();
    return age >= 0.0 && age <= limit_s;
  }

  // 与 RL 节点同口径：仅 GROUND_APPROACH 允许规划。
  bool authorized() const
  {
    if (!require_task_auth_) {return true;}
    if (!have_state_) {return false;}
    if (!fresh(state_stamp_, 3.0)) {return false;}
    return state_ == agc_msgs::msg::AgcTaskState::GROUND_APPROACH;
  }

  // 地图视图（**不拷贝**数据：单线程下 map_data_ 在本拍不会被改）。
  planner::GridView gridView() const
  {
    planner::GridView g;
    g.cells = map_data_.empty() ? nullptr : map_data_.data();
    g.width = map_width_;
    g.height = map_height_;
    g.resolution = map_resolution_;
    g.origin_x = map_origin_x_;
    g.origin_y = map_origin_y_;
    g.frame = map_frame_;
    g.stamp_s = map_stamp_.seconds();
    return g;
  }

  bool needReplan(double now_s)
  {
    if (force_replan_) {
      force_replan_ = false;
      replan_reason_ = "first_goal";
      return true;
    }
    const double age = now_s - last_plan_s_;
    if (age < kReplanGuardS) {return false;}
    if (!have_plan_) {
      replan_reason_ = "retry";
      return age >= replan_period_s_;
    }
    // 判据顺序固定：目标变 → 地图变 → 超时 → 周期（ADR-0013 (a)）。
    const double goal_delta = std::hypot(goal_x_ - planned_goal_x_, goal_y_ - planned_goal_y_);
    if (goal_delta > replan_displacement_m_) {
      replan_reason_ = "goal_moved";
      return true;
    }
    const planner::MapSignature sig = planner::computeMapSignature(gridView());
    if (planner::signatureChanged(
        sig, planned_signature_, signature_free_delta_cells_))
    {
      // 双判据：阻挡集变 **或** 已知自由面积变（后者感知探索推进）。
      replan_reason_ = (sig.blocked_hash != planned_signature_.blocked_hash) ?
        "map_blocked_changed" : "map_explored";
      return true;
    }
    if (age > max_path_age_s_) {
      replan_reason_ = "path_age";
      return true;
    }
    if (age >= replan_period_s_) {
      replan_reason_ = "periodic";
      return true;
    }
    return false;
  }

  void tick()
  {
    const double now_s = now().seconds();

    // ---- 输入前置：任一不满足就**不发**（不重发旧路径刷新 stamp）----
    //
    // **每一次拒绝都要能归因**：早先这里是一串裸 `return`，结果整链实跑时规划器
    // 一次都没发布，日志里也看不出卡在哪一项 —— 与「失败必须显式可解释」直接冲突。
    // 现在每项拒绝都记一条**节流**诊断（原因变化时才打），既不刷屏也能定位。
    const char * blocked = nullptr;
    if (!have_map_) {blocked = "no_map";}
    else if (!have_odom_) {blocked = "no_odom";}
    else if (!have_goal_) {blocked = "no_goal";}
    else if (!fresh(odom_stamp_, odom_timeout_s_)) {blocked = "odom_stale";}
    else if (!fresh(goal_stamp_, goal_timeout_s_)) {blocked = "goal_stale";}
    else if (have_map_valid_ && !map_valid_) {blocked = "map_valid_false";}
    else if (have_odom_valid_ && !odom_valid_) {blocked = "odom_valid_false";}
    else if (have_goal_info_ && !goal_info_valid_) {blocked = "goal_info_invalid";}
    else if (!authorized()) {blocked = "not_authorized";}
    else if (!fresh(map_stamp_, map_timeout_s_)) {blocked = "map_stale";}
    if (blocked != nullptr) {
      logBlocked(blocked);
      return;
    }
    last_blocked_reason_.clear();

    if (!needReplan(now_s)) {return;}

    // ---- 已到位：发布退化但合法的 2 点同点路径 ----
    const double dist_to_goal = std::hypot(goal_x_ - car_x_, goal_y_ - car_y_);
    if (dist_to_goal <= goal_tol_m_) {
      publishDegeneratePath();
      planned_goal_x_ = goal_x_;
      planned_goal_y_ = goal_y_;
      planned_car_x_ = car_x_;
      planned_car_y_ = car_y_;
      planned_signature_ = planner::computeMapSignature(gridView());
      last_plan_s_ = now_s;
      have_plan_ = true;
      publishStatus(nullptr, "arrived");
      return;
    }

    // ---- 规划（单线程内同步；墙钟预算由参数硬约束）----
    planner::PlannerSnapshot snap;
    snap.grid = gridView();
    snap.start.x = car_x_;
    snap.start.y = car_y_;
    snap.start.yaw = car_yaw_;
    snap.goal.x = goal_x_;
    snap.goal.y = goal_y_;
    snap.goal.yaw = 0.0;   // goal 的 orientation 恒为 w=1.0（未填），不使用它
    snap.goal_valid = have_goal_info_ ? goal_info_valid_ : true;
    snap.authorized = authorized();
    snap.params = params_;
    snap.replan_reason = replan_reason_;

    const planner::PathResult result = planner_->plan(snap);
    last_plan_s_ = now_s;

    if (!result.success) {
      // **规划失败 → 不发布**。由消费侧 `path.max_age_s` 过期门把它变成零速。
      have_plan_ = false;
      ++consecutive_failures_;
      publishStatus(&result, replan_reason_);
      RCLCPP_WARN_THROTTLE(
        get_logger(), *get_clock(), 2000,
        "规划失败 %s（%s）expanded=%d %.0fms 连续失败=%d",
        planner::toString(result.failure), result.detail.c_str(),
        result.expanded_nodes, result.planning_time_s * 1e3, consecutive_failures_);
      return;
    }

    publishPath(result);
    planned_goal_x_ = goal_x_;
    planned_goal_y_ = goal_y_;
    planned_car_x_ = car_x_;
    planned_car_y_ = car_y_;
    planned_signature_ = planner::computeMapSignature(gridView());
    have_plan_ = true;
    consecutive_failures_ = 0;
    publishStatus(&result, replan_reason_);

    RCLCPP_INFO(
      get_logger(),
      "规划成功 %s：%d 点（搜索 %d）%.1f m，%.0f ms，expanded=%d，"
      "离障 %.2f m，最大曲率 %.3f，reason=%s",
      planner::toString(result.outcome), result.final_path_points,
      result.raw_path_points, result.path_length_m, result.planning_time_s * 1e3,
      result.expanded_nodes,
      std::isfinite(result.clearance_min_m) ? result.clearance_min_m : -1.0,
      result.max_curvature, replan_reason_.c_str());
  }

  // 前置拒绝的原因变化时才打一条（20 Hz 下不刷屏，但转变可见）。
  void logBlocked(const std::string & reason)
  {
    if (reason == last_blocked_reason_) {return;}
    last_blocked_reason_ = reason;
    RCLCPP_WARN(
      get_logger(), "规划前置拒绝：%s（map=%d odom=%d goal=%d state=%d）—— 本拍不发布",
      reason.c_str(), have_map_ ? 1 : 0, have_odom_ ? 1 : 0, have_goal_ ? 1 : 0,
      static_cast<int>(state_));
  }

  void publishPath(const planner::PathResult & result)
  {
    nav_msgs::msg::Path path;
    path.header.stamp = now();
    path.header.frame_id = world_frame_;
    path.poses.reserve(result.poses.size());
    for (const planner::Pose2D & p : result.poses) {
      geometry_msgs::msg::PoseStamped ps;
      ps.header = path.header;
      ps.pose.position.x = p.x;
      ps.pose.position.y = p.y;
      ps.pose.position.z = 0.0;
      ps.pose.orientation.x = 0.0;
      ps.pose.orientation.y = 0.0;
      ps.pose.orientation.z = std::sin(0.5 * p.yaw);
      ps.pose.orientation.w = std::cos(0.5 * p.yaw);
      path.poses.push_back(ps);
    }
    path_pub_->publish(path);
  }

  // 已到位：2 点同点位路径（保持「路径存在且末端==goal」，消费侧据此判完成）。
  void publishDegeneratePath()
  {
    nav_msgs::msg::Path path;
    path.header.stamp = now();
    path.header.frame_id = world_frame_;
    for (int i = 0; i < 2; ++i) {
      geometry_msgs::msg::PoseStamped ps;
      ps.header = path.header;
      ps.pose.position.x = car_x_;
      ps.pose.position.y = car_y_;
      ps.pose.position.z = 0.0;
      ps.pose.orientation.z = std::sin(0.5 * car_yaw_);
      ps.pose.orientation.w = std::cos(0.5 * car_yaw_);
      path.poses.push_back(ps);
    }
    path_pub_->publish(path);
  }

  // 诊断 JSON（非命令型；字段稳定后另立接口决策 —— ADR-0048）。
  void publishStatus(const planner::PathResult * result, const std::string & reason)
  {
    std::string json = "{";
    if (result != nullptr) {
      json += "\"success\":" + std::string(result->success ? "true" : "false");
      json += ",\"failure\":\"" + std::string(planner::toString(result->failure)) + "\"";
      json += ",\"outcome\":\"" + std::string(planner::toString(result->outcome)) + "\"";
      json += ",\"planning_time_ms\":" + std::to_string(result->planning_time_s * 1e3);
      json += ",\"expanded_nodes\":" + std::to_string(result->expanded_nodes);
      json += ",\"raw_path_points\":" + std::to_string(result->raw_path_points);
      json += ",\"final_path_points\":" + std::to_string(result->final_path_points);
      json += ",\"path_length_m\":" + std::to_string(result->path_length_m);
      json += ",\"clearance_min_m\":" + std::to_string(result->clearance_min_m);
      json += ",\"max_curvature\":" + std::to_string(result->max_curvature);
      json += ",\"detail\":\"" + escapeJson(result->detail) + "\"";
    } else {
      json += "\"success\":true,\"failure\":\"none\"";
    }
    json += ",\"replan_reason\":\"" + escapeJson(reason) + "\"";
    json += ",\"consecutive_failures\":" + std::to_string(consecutive_failures_);
    json += ",\"map_signature\":\"" +
      planner::blockedSignature(gridView()) + "\"";
    json += "}";

    std_msgs::msg::String msg;
    msg.data = json;
    status_pub_->publish(msg);
  }

  static std::string escapeJson(const std::string & s)
  {
    std::string out;
    out.reserve(s.size());
    for (char c : s) {
      if (c == '"' || c == '\\') {
        out += '\\';
        out += c;
      } else if (static_cast<unsigned char>(c) < 0x20) {
        continue;
      } else {
        out += c;
      }
    }
    return out;
  }

  // 重规划限流：刚规划完不立即重规划（对齐 ground_baseline 的 kReplanGuardS）。
  static constexpr double kReplanGuardS = 0.2;

  // ---- 话题 ----
  std::string map_topic_, map_valid_topic_, odom_topic_, odom_valid_topic_;
  std::string goal_topic_, goal_info_topic_, state_topic_, path_topic_, status_topic_;
  std::string world_frame_;

  // ---- 时序 ----
  double rate_hz_{5.0}, map_timeout_s_{2.0}, odom_timeout_s_{0.5}, goal_timeout_s_{2.0};
  bool require_task_auth_{true};
  double replan_period_s_{2.0}, replan_displacement_m_{1.0}, max_path_age_s_{5.0};
  int signature_free_delta_cells_{200};
  double goal_tol_m_{0.3};

  // ---- 输入缓存 ----
  std::vector<int8_t> map_data_;
  int map_width_{0}, map_height_{0};
  double map_resolution_{0.0}, map_origin_x_{0.0}, map_origin_y_{0.0};
  std::string map_frame_;
  rclcpp::Time map_stamp_{0, 0, RCL_ROS_TIME};
  bool have_map_{false};
  bool map_valid_{true}, have_map_valid_{false};
  double car_x_{0.0}, car_y_{0.0}, car_yaw_{0.0};
  rclcpp::Time odom_stamp_{0, 0, RCL_ROS_TIME};
  bool have_odom_{false};
  bool odom_valid_{true}, have_odom_valid_{false};
  double goal_x_{0.0}, goal_y_{0.0};
  rclcpp::Time goal_stamp_{0, 0, RCL_ROS_TIME};
  bool have_goal_{false};
  bool goal_info_valid_{true}, have_goal_info_{false};
  uint8_t state_{agc_msgs::msg::AgcTaskState::IDLE};
  rclcpp::Time state_stamp_{0, 0, RCL_ROS_TIME};
  bool have_state_{false};

  // ---- 绑定 ----
  double planned_goal_x_{0.0}, planned_goal_y_{0.0};
  double planned_car_x_{0.0}, planned_car_y_{0.0};
  planner::MapSignature planned_signature_;
  double last_plan_s_{0.0};
  bool have_plan_{false};
  bool force_replan_{false};
  int consecutive_failures_{0};
  std::string replan_reason_{"first_goal"};
  std::string last_blocked_reason_;

  planner::PlannerParams params_;
  planner::IPlanner::Ptr planner_;

  rclcpp::Publisher<nav_msgs::msg::Path>::SharedPtr path_pub_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr status_pub_;
  rclcpp::Subscription<nav_msgs::msg::OccupancyGrid>::SharedPtr map_sub_;
  rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr map_valid_sub_;
  rclcpp::Subscription<nav_msgs::msg::Odometry>::SharedPtr odom_sub_;
  rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr odom_valid_sub_;
  rclcpp::Subscription<geometry_msgs::msg::PoseStamped>::SharedPtr goal_sub_;
  rclcpp::Subscription<std_msgs::msg::String>::SharedPtr goal_info_sub_;
  rclcpp::Subscription<agc_msgs::msg::AgcTaskState>::SharedPtr state_sub_;
  rclcpp::TimerBase::SharedPtr timer_;
};

}  // namespace agc_ground

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<agc_ground::HybridAstarSe2PlannerNode>());
  rclcpp::shutdown();
  return 0;
}
