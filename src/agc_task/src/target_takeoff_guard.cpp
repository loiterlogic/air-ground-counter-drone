// target_takeoff_guard.cpp —— 目标机"是否真的起飞"的启动期守卫（2026-11-03）
//
// ## 为什么需要它
//
// s04 抬高度回归 run（`experiments/demo/20261103-093912`）暴露了一个**静默失败**：
//   * `intruder_driver` 的 odom 订阅 QoS 漏了 `TRANSIENT_LOCAL`（默认 `VOLATILE`），
//     与 PX4 uXRCE 的 `BEST_EFFORT + TRANSIENT_LOCAL` writer **不兼容** → 静默收不到数据；
//   * 于是 `origins_` 恒为 `None`，`_tick` 每拍 `return`，**永不 ARM** → 目标机停在地面；
//   * ⇒ 任务卡在 `AIR_SEARCH` 三分钟，**全程没有任何错误日志**，最后只表现为"超时"。
//
// ## 2026-11-03 更正：旧版赖以暴露该故障的「感知致盲」特征**已失效**
//
// 旧注释写「己方机 14 m，与地面目标垂直差 14 m > `range_max_m=12` ⇒ 感知恒盲」。
// 量程改为 **30.0** 后（原依据 `perception_sensors.yaml` 文件头已随 `perception` 轴
// 于 2026-11-06 退役；现登记处 = `air.yaml` standoff_follower 注释 + 飞行高度规范 K1）：
//     √(26.17² + 14²) = 29.68 m  <  30.0 m      余量仅 0.32 m
// ⇒ 目标停地面时**感知照样能看见**（`gate_ok` 不再恒 0），只是航迹钉在地面某点不动。
// ⚠ 当前 `gt_adapter` 是 `/agc/targets` 唯一发布者且无几何门控，上述"看不见"机制
//   本就不再运行；本守卫订阅真值 z，是唯一独立于任何感知链路的起飞判据。
//
// 后果：那个"响亮、无歧义"的间接信号没了。**因此本守卫不但不能删，反而更重要**——
//   它订阅真值 z，是**唯一**能在启动期把"目标机没起飞"直接报出来的机制。
//   任何人不得因为"感知看起来有数据"就认为目标已起飞：地面目标同样会产生航迹。
//
// 这类失败**必须**在启动期就大声报出来，而不是让使用者去读 3 分钟日志反推。
//
// ## 判据
//
// 订阅**真值** `/agc/gt/intruder_uav`（不依赖感知链路，目标停在地面时照样有值），
// 在 `startup_timeout_s` 内观察其世界 ENU z：
//   * 一旦 `z >= min_takeoff_alt_m` → 记 `ok`，发布 `/agc/task/target_takeoff`（latched，`data=true`），退出；
//   * 超时仍未达到 → **ERROR** 日志 + 发布 `data=false` + **进程非零退出**，
//     让 launch / 上层看到显式失败（不是静默继续）。
//
// ## 边界（不得误读）
//
// * 本节点**只观察不控制**：不写任何 setpoint、不动模型位姿，不是第二命令者。
// * 它**不是**能力声明：看到目标"有高度"不等于"反无人机链路成立"。
// * `min_takeoff_alt_m` 由 launch 从**地图派生高度**给出（与 `flight_altitude` 同源），
//   不在此写死第二份高度真源。
// * 阈值取"目标巡航高度的一半"这类宽松口径的**判断**留给调用方（launch 注入），
//   本节点只管"低于阈值就报错"。

#include <chrono>
#include <memory>

#include "rclcpp/rclcpp.hpp"
#include "std_msgs/msg/bool.hpp"
#include "geometry_msgs/msg/pose_stamped.hpp"

namespace
{
using namespace std::chrono_literals;

class TargetTakeoffGuard : public rclcpp::Node
{
public:
  TargetTakeoffGuard()
  : Node("target_takeoff_guard")
  {
    gt_topic_ = declare_parameter<std::string>("target_gt_topic", "/agc/gt/intruder_uav");
    out_topic_ = declare_parameter<std::string>("result_topic", "/agc/task/target_takeoff");
    min_alt_ = declare_parameter<double>("min_takeoff_alt_m", 5.0);
    timeout_s_ = declare_parameter<double>("startup_timeout_s", 45.0);
    poll_hz_ = declare_parameter<double>("rate_hz", 10.0);

    // latched：让晚到的消费者也能读到结论（与 `capture_hit` 等同款口径）。
    pub_ = create_publisher<std_msgs::msg::Bool>(
      out_topic_, rclcpp::QoS(1).transient_local());

    // **类型必须与发布方一致**：`/agc/gt/<entity>` 由 `gt_bypass` 以
    // `geometry_msgs/PoseStamped` 发布（见 `src/agc_perception/src/gt_bypass.cpp`）。
    // 2026-11-03：本节点此前按 `nav_msgs/Odometry` 订阅 → 同一话题上出现**两种类型**，
    // DDS 类型不匹配 → 回调**永不触发** → `have_gt_` 恒 false → 守卫只会误报"目标机未起飞"
    // （实测 `ros2 topic info` 显示 Type 为 `[PoseStamped, Odometry]` 两个）。
    sub_ = create_subscription<geometry_msgs::msg::PoseStamped>(
      gt_topic_, rclcpp::QoS(10),
      [this](geometry_msgs::msg::PoseStamped::SharedPtr m) {
        have_gt_ = true;
        last_z_ = m->pose.position.z;
        if (last_z_ >= min_alt_) {
          ok_ = true;
        }
      });

    RCLCPP_INFO(
      get_logger(),
      "目标机起飞守卫就绪：gt=%s 阈值 z≥%.2f m 超时 %.1fs（仅观察，不控制）",
      gt_topic_.c_str(), min_alt_, timeout_s_);

    started_ = now();
    timer_ = create_wall_timer(
      std::chrono::duration<double>(1.0 / std::max(poll_hz_, 1e-3)),
      [this]() {tick();});
  }

  /// 守卫是否通过（`main` 据此决定退出码）。通过 = 观测到 gt_z ≥ 阈值。
  bool passed() const {return ok_;}

private:
  void tick()
  {
    if (ok_) {
      publish(true);
      RCLCPP_INFO(
        get_logger(), "目标机已起飞：gt_z=%.2f m ≥ 阈值 %.2f m（守卫通过）", last_z_, min_alt_);
      rclcpp::shutdown();
      return;
    }
    const double elapsed = (now() - started_).seconds();
    if (elapsed < timeout_s_) {return;}
    // 超时：大声报，并让进程以非零码退出（launch 侧可见）。
    publish(false);
    RCLCPP_ERROR(
      get_logger(),
      "目标机**未起飞**：%.1fs 内 gt_z 始终 < %.2f m（最后 gt_z=%.2f m，have_gt=%d）。"
      "常见原因：`intruder_driver` 未收到 odom（QoS durability 不匹配）/ 未 ARM / uXRCE 会话未建立。"
      "继续跑下去只会得到 AIR_SEARCH 超时，故在此显式失败。",
      timeout_s_, min_alt_, last_z_, have_gt_ ? 1 : 0);
    rclcpp::shutdown();
  }

  void publish(bool ok)
  {
    std_msgs::msg::Bool m;
    m.data = ok;
    pub_->publish(m);
  }

  rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr pub_;
  rclcpp::Subscription<geometry_msgs::msg::PoseStamped>::SharedPtr sub_;
  rclcpp::TimerBase::SharedPtr timer_;
  rclcpp::Time started_{0, 0, RCL_ROS_TIME};
  std::string gt_topic_, out_topic_;
  double min_alt_{5.0}, timeout_s_{45.0}, poll_hz_{10.0};
  bool have_gt_{false}, ok_{false};
  double last_z_{0.0};
};

}  // namespace

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  auto node = std::make_shared<TargetTakeoffGuard>();
  rclcpp::spin(node);
  // 未达成 → 非零退出码，让 launch / 上层显式看到失败（不静默继续）。
  // 达成则 `shutdown` 前已置位 `ok_`；此处经成员读取（节点在 spin 结束后仍存活）。
  return node->passed() ? 0 : 1;
}
