// gt_adapter —— 真值目标适配器（2026-11-03 加不确定性模型）
//
// 消费 真值旁路 `/agc/gt/<target_model>`（world 系 PoseStamped），产出契约
// `/agc/targets`（`agc_msgs/TargetTrackArray`）：
// * `source=gt_adapter`；pose/twist 均在 world 系；不做机体系旋转
// （与 Odometry 的 child-frame twist 约定不同）；
// * 数组 header.stamp = 发布时刻；track.header.stamp = 该样本的**源采样时刻**，
// 本拍无释放样本则 tracks 为空（绝不刷新旧观测时间）。
//
// ## 2026-11-03 裁定：真值链路**不再**是"理想直通"
//
// 背景：本项目主线**不做目标检测**。目标位置由真值直接给出，
// 但**必须带不确定性**，否则"能跟踪"这个结论没有意义——零噪声、零延迟、置信度恒 1 的
// 链路只是把答案抄了一遍。
//
// 因此本节点引入**六类不确定性参数**（原与已退役的 `air_perception` 同名同口径；
// 该节点于 2026-11-06 删除后，本节点是唯一消费者，参数名沿用不改名）：
//
// | 类别 | 参数 | 实现位置 |
// |---|---|---|
// | 位置噪声 | `sigma_xy_m` / `sigma_z_m` | onGt（源采样时刻加噪） |
// | 时间延迟 | `latency_s` | 延迟队列（改交付时刻，不改源采样时刻） |
// | 丢包 | `drop_prob` | onGt（独立同分布） |
// | 成簇丢失 | `drop_burst_prob` / `_mean_s` / `_mean_gap_s` | onGt（两态马尔可夫） |
// | 置信度 | **配置显式声明**（`confidence`，缺省 1.0） | `agc::declaredConfidence`；**不**由 σ 派生 |
// | 速度 | α-β 滤波器 | 由**噪声位置**估计，**不**直接对真值差分 |
//
// ## 置信度与精度是两件事（2026-11-03 语义解耦）
//
// 旧口径 `conf = 1 − exp(−tol²/2σ²)` 把精度与可信度混成一个数，后果是：`tol=0.25 m` 时
// σ 只要 > **0.2123 m**，conf 就跌破下游 `confidence_min=0.5`，**整条航迹被拒**。
// 于是"给真值链路加 0.5 m 噪声"这个完全合理的需求会直接打断链路。
//
// 现口径：
// * `confidence` = **这条航迹是不是真的** → 由配置声明（真值通道恒为真，缺省 1.0）
// * `pose.covariance` = **这条航迹有多准** → 由 σ_xy / σ_z 给出
// 两者不再互相派生。加噪声只影响协方差与融合权重，**不再**导致航迹被拒。
// 详见 `include/agc_perception/confidence.hpp` 文件头。
//
// ## 速度为什么必须走滤波器（关键）
//
// 旧实现用 `diff_window_s=0.15` 窗对**真值**做差分，零噪声下得到精确速度。
// 一旦位置带噪声 σ_p，同一差分窗的速度噪声是：
//
// σ_v = σ_p·√2 / Δt = σ_p·√2/0.15 ≈ 9.43·σ_p
//
// 即 σ_p=0.5 m 时 σ_v≈4.7 m/s，比目标自身速度（0.5 m/s）大一个量级 —— 下游
// `standoff_follower` 的参考速度前馈会被这个噪声直接驱动，跟踪剧烈抖动。
//
// 故本节点用 **α-β 滤波器**（Kalman 稳态形式）估计速度：位置观测喂入，输出平滑速度。
// 增益由**跟踪指数** Λ = σ_w·Δt²/σ_p 解析给出（见 `AlphaBeta::gains`），不是手调魔数。
//
// 发布口径（用户 2026-11-03 裁定「位置加噪 + 滤波器估计速度」）：
// * **位置** = 加噪后的原始观测（噪声可见、可被下游与真值比对测误差）
// * **速度** = α-β 滤波器输出（不被噪声放大）
//
// ## 几何门控：本节点不做
//
// 本节点**不做几何门控**（无量程 / 无 FOV / 无遮挡）——真值目标指示不分远近。
// 原 `air_perception` 曾带几何门控，已于 2026-11-06 随 `perception` 轴退役删除；
// 本节点的不确定性模型沿用当时的参数名，未改名。
//
// ## 目标源互斥
//
// 仅当本节点为选中源（`target_source == "gt_adapter"`）时才发布 `/agc/targets`，
// 避免双发布者。2026-11-04 起 `air_fusion` 与视觉定位路径均已退役，本节点是唯一候选源，
// 但仍保留该判定：参数配错时宁可"不发布并告警"，也不静默顶替。

#include <algorithm>
#include <array>
#include <cmath>
#include <deque>
#include <random>
#include <stdexcept>
#include <string>

#include <rclcpp/rclcpp.hpp>
#include <geometry_msgs/msg/pose_stamped.hpp>

#include <agc_msgs/msg/target_track.hpp>
#include <agc_msgs/msg/target_track_array.hpp>

#include "agc_perception/alpha_beta.hpp"
#include "agc_perception/confidence.hpp"
#include "agc_perception/math_utils.hpp"

namespace
{
const char * const kSource = "gt_adapter";
/// 延迟队列上限：latency_s 与入站频率共同决定深度；超过即丢最旧（显式计数，不静默）。
const size_t kPendingMax = 2000;

void diagCov(double sxy, double sz, std::array<double, 36> & c)
{
  c.fill(0.0);
  c[0] = c[7] = sxy * sxy;
  c[14] = sz * sz;
}

/// 一条待释放样本（加噪已完成；延迟只改**交付**时刻，不改源采样时刻）。
struct Pending
{
  double t_src{0.0};      ///< 源采样时刻（入站 Header.stamp）
  double release_t{0.0};  ///< 交付时刻 = t_src + latency_s
  double x{0.0}, y{0.0}, z{0.0};
  double yaw{0.0};        ///< 偏航（仅用于角速度差分；不参与位置滤波）
  std::array<double, 4> quat{{0.0, 0.0, 0.0, 1.0}};
};
}  // namespace

class GtAdapter : public rclcpp::Node
{
public:
  GtAdapter()
  : Node("gt_adapter")
  {
    world_frame_ = declare_parameter<std::string>("world_frame", "world");
    target_model_ = declare_parameter<std::string>("target_model", "intruder_uav");
    target_id_ = declare_parameter<std::string>("target_id", "intruder_uav");
    gt_topic_ = declare_parameter<std::string>("gt_topic", "/agc/gt/intruder_uav");
    target_topic_ = declare_parameter<std::string>("target_topic", "/agc/targets");
    target_source_ = declare_parameter<std::string>("target_source", kSource);
    rate_hz_ = declare_parameter<double>("rate_hz", 10.0);

    // ---- 不确定性模型（参数名沿用已退役的 air_perception；缺省 = 理想基线，行为等价旧版）----
    sigma_xy_ = declare_parameter<double>("sigma_xy_m", 0.0);
    sigma_z_ = declare_parameter<double>("sigma_z_m", 0.0);
    latency_s_ = declare_parameter<double>("latency_s", 0.0);
    drop_prob_ = declare_parameter<double>("drop_prob", 0.0);
    drop_burst_prob_ = declare_parameter<double>("drop_burst_prob", 0.0);
    drop_burst_mean_s_ = declare_parameter<double>("drop_burst_mean_s", 0.5);
    drop_burst_mean_gap_s_ = declare_parameter<double>("drop_burst_mean_gap_s", 5.0);
    seed_ = declare_parameter<std::string>("seed", "0");
    // 航迹**可信度**：由配置显式声明（2026-11-03 语义解耦，见 confidence.hpp 文件头）。
    // 缺省 1.0 = "真值通道的航迹按定义为真"。**不**由 σ 派生——σ 只表示精度。
    confidence_ = agc::declaredConfidence(declare_parameter<double>("confidence", 1.0));
    // 精度容差（**仅诊断**）：给定 σ，误差落在 tol 内的概率。不参与 confidence 计算。
    tol_m_ = declare_parameter<double>("confidence_tolerance_m", 0.25);
    // α-β 过程噪声：目标机动强度（m/s²）。0.5 m/s² 覆盖本项目目标（≤0.5 m/s 匀速/盘旋）。
    filter_sigma_w_ = declare_parameter<double>("filter_sigma_w_mps2", 0.5);
    filter_enabled_ = declare_parameter<bool>("filter_enabled", true);
    // 兼容旧参数名：`pose_std_m` / `twist_std_m` 曾是"只填协方差"的装饰参数。
    // 现改为：若显式给了 `sigma_xy_m` 则以它为准；否则回退读 `pose_std_m`（旧配置文件不致静默失效）。
    if (sigma_xy_ <= 0.0) {
      const double legacy = declare_parameter<double>("pose_std_m", 0.0);
      if (legacy > 0.0) {sigma_xy_ = legacy;}
    }
    if (sigma_z_ <= 0.0) {sigma_z_ = sigma_xy_;}

    // ---- seed 合法性：整数字面量，否则拒绝启动（口径沿用已退役的 air_perception）----
    {
      unsigned base = 0u;
      if (seed_ == "unseeded") {
        base = std::random_device{}();
      } else {
        try {
          size_t pos = 0;
          const long v = std::stol(seed_, &pos);
          if (pos != seed_.size() || v < 0) {throw std::invalid_argument("bad");}
          base = static_cast<unsigned>(v);
        } catch (const std::exception &) {
          throw std::runtime_error(
            "gt_adapter 非法 seed（拒绝启动）：seed=\"" + seed_ +
            "\"（要求整数字面量或 \"unseeded\"；不静默退回默认基种子）。");
        }
      }
      rng_.seed(base);
    }
    // 诊断量（不是 confidence）：给定 σ，误差落在 tol 内的概率。
    const double coverage_prob = agc::coverageProbability(sigma_xy_, tol_m_);

    if (target_source_ == kSource) {
      pub_ = create_publisher<agc_msgs::msg::TargetTrackArray>(
        target_topic_, rclcpp::QoS(10));
      has_pub_ = true;
    } else {
      RCLCPP_WARN(
        get_logger(), "gt_adapter：/agc/target/source=%s，本节点不发布 %s",
        target_source_.c_str(), target_topic_.c_str());
    }

    gt_sub_ = create_subscription<geometry_msgs::msg::PoseStamped>(
      gt_topic_, 10, std::bind(&GtAdapter::onGt, this, std::placeholders::_1));

    const auto period = std::chrono::duration<double>(1.0 / std::max(rate_hz_, 1e-3));
    timer_ = create_wall_timer(
      std::chrono::duration_cast<std::chrono::nanoseconds>(period),
      std::bind(&GtAdapter::tick, this));

    RCLCPP_INFO(
      get_logger(),
      "gt_adapter：source=%s；真值 %s → %s；%.1f Hz；"
      "σ_xy=%.3f σ_z=%.3f latency=%.3fs drop=%.2f burst=%.2f "
      "conf=%.3f(声明值) 精度覆盖=%.3f(tol=%.2fm, 仅诊断) filter=%s",
      target_source_.c_str(), gt_topic_.c_str(), target_topic_.c_str(), rate_hz_,
      sigma_xy_, sigma_z_, latency_s_, drop_prob_, drop_burst_prob_,
      confidence_, coverage_prob, tol_m_, filterActive() ? "α-β" : "off(差分)");
    if (sigma_xy_ <= 0.0 && latency_s_ <= 0.0 && drop_prob_ <= 0.0 &&
      drop_burst_prob_ <= 0.0)
    {
      RCLCPP_WARN(get_logger(),
        "gt_adapter：**理想基线**（噪声/延迟/丢包全 0）——本 run 的跟踪结论不得用于"
        "宣称鲁棒性（仅作链路连通性基线）");
    }
  }

private:
  // ---------------------------------------------------------------- 入站（加噪 + 丢包）

  void onGt(const geometry_msgs::msg::PoseStamped & msg)
  {
    const double t = rclcpp::Time(msg.header.stamp).seconds();
    const double dt = has_prev_t_ ? (t - last_t_) : 0.0;
    last_t_ = t;
    has_prev_t_ = true;
    ++received_;

    // ① 丢包：独立同分布 + 两态成簇（实现沿用已退役的 air_perception）
    std::uniform_real_distribution<double> uni(0.0, 1.0);
    const bool indep_hit = (drop_prob_ > 0.0) && (uni(rng_) < std::min(1.0, drop_prob_));
    if (indep_hit || burstThisTick(dt)) {
      ++diag_dropped_;
      return;
    }

    // ② 位置噪声（源采样时刻加噪；真值只用于评估，不进入输出）
    Pending s;
    s.t_src = t;
    s.release_t = t + std::max(0.0, latency_s_);
    s.x = msg.pose.position.x;
    s.y = msg.pose.position.y;
    s.z = msg.pose.position.z;
    if (sigma_xy_ > 0.0 || sigma_z_ > 0.0) {
      std::normal_distribution<double> nx(0.0, sigma_xy_), ny(0.0, sigma_xy_);
      std::normal_distribution<double> nz(0.0, sigma_z_);
      s.x += nx(rng_);
      s.y += ny(rng_);
      s.z += nz(rng_);
    }
    s.quat = {{msg.pose.orientation.x, msg.pose.orientation.y,
      msg.pose.orientation.z, msg.pose.orientation.w}};
    s.yaw = agc::yawFromQuat(msg.pose.orientation);

    pending_.push_back(s);
    // 队列上界：延迟配置过大时丢最旧（显式计数，不静默涨内存）
    while (pending_.size() > kPendingMax) {
      pending_.pop_front();
      ++diag_overflow_;
    }
  }

  bool burstThisTick(double dt)
  {
    if (drop_burst_prob_ <= 0.0) {return false;}
    const double eps = 1e-6;
    std::uniform_real_distribution<double> uni(0.0, 1.0);
    if (burst_state_) {
      const double p_bg = 1.0 - std::exp(-std::max(dt, 0.0) / std::max(drop_burst_mean_s_, eps));
      if (uni(rng_) < p_bg) {burst_state_ = false;}
    } else {
      const double base =
        1.0 - std::exp(-std::max(dt, 0.0) / std::max(drop_burst_mean_gap_s_, eps));
      const double p_gb = std::min(1.0, std::max(0.0, drop_burst_prob_ * base));
      if (uni(rng_) < p_gb) {burst_state_ = true;}
    }
    return burst_state_;
  }

  // ---------------------------------------------------------------- 滤波器

  /// 滤波器是否真正生效：显式开关 **且** 位置确实带噪声。
  /// 零噪声时滤波器无意义且会退化振荡（见 `feedFilter` 说明）。
  bool filterActive() const {return filter_enabled_ && sigma_xy_ > agc::kFilterBypassSigmaM;}

  /// 把一条释放样本喂进 α-β 滤波器（按源采样时刻推进）。
  ///
  /// **零噪声退化保护（必须保留）**：σ_p → 0 时跟踪指数 Λ = σ_w·Δt²/σ_p → ∞，
  /// 解析增益趋于 α=1, β=2 —— 该点滤波器退化为二阶振荡（实测速度序列在
  /// 1.00 / 0.00 之间逐拍翻转，完全不可用）。故 **σ_p ≤ 1e-6 m 时直接旁路滤波器**，
  /// 由调用方回落到短窗差分（零噪声下差分是精确的，见 `diffVelocity`）。
  void feedFilter(const Pending & s)
  {
    if (!filterActive()) {return;}   // 理想基线：不滤波，走差分
    const double dt = has_filter_t_ ? (s.t_src - filter_t_) : 0.0;
    if (!has_filter_t_) {
      // 冷启动：用首帧初始化三轴，速度保持 0（不猜初速）
      fx_.reset();
      fy_.reset();
      fz_.reset();
      fx_.p = s.x;
      fy_.p = s.y;
      fz_.p = s.z;
      fx_.init = fy_.init = fz_.init = true;
      filter_t_ = s.t_src;
      has_filter_t_ = true;
      return;
    }
    if (dt <= 1e-6) {return;}   // 同刻重发：不推进滤波（避免除零与伪速度）
    double a = 0.0, b = 0.0;
    agc::AlphaBeta::gains(filter_sigma_w_, std::max(sigma_xy_, 1e-6), dt, &a, &b);
    fx_.update(s.x, dt, a, b);
    fy_.update(s.y, dt, a, b);
    double az = 0.0, bz = 0.0;
    agc::AlphaBeta::gains(filter_sigma_w_, std::max(sigma_z_, 1e-6), dt, &az, &bz);
    fz_.update(s.z, dt, az, bz);
    filter_t_ = s.t_src;
  }

  /// 偏航角速度：短窗差分（偏航不经位置滤波，故单独估计）。
  double yawRate() const
  {
    if (history_.size() < 2) {return 0.0;}
    const auto & a = history_.back();
    auto b = history_.front();
    for (const auto & e : history_) {
      if (a.t_src - e.t_src <= diff_window_s_) {b = e; break;}
    }
    const double dt = a.t_src - b.t_src;
    if (dt <= 1e-6) {return 0.0;}
    return agc::normalizeAngle(a.yaw - b.yaw) / dt;
  }

  /// 退路：未启用滤波器时按旧口径差分（仅在 filter_enabled=false 时使用）。
  void diffVelocity(std::array<double, 3> & v, double & wz) const
  {
    v = {{0.0, 0.0, 0.0}};
    wz = 0.0;
    if (history_.size() < 2) {return;}
    const auto & a = history_.back();
    auto b = history_.front();
    for (const auto & e : history_) {
      if (a.t_src - e.t_src <= diff_window_s_) {b = e; break;}
    }
    const double dt = a.t_src - b.t_src;
    if (dt <= 1e-6) {return;}
    v = {{(a.x - b.x) / dt, (a.y - b.y) / dt, (a.z - b.z) / dt}};
    wz = agc::normalizeAngle(a.yaw - b.yaw) / dt;
  }

  // ---------------------------------------------------------------- 发布

  agc_msgs::msg::TargetTrack buildTrack(const Pending & s)
  {
    agc_msgs::msg::TargetTrack tr;
    // track.header.stamp = **源采样时刻**（不是交付时刻）：图像/观测到航迹延迟可计算
    tr.header.stamp = rclcpp::Time(static_cast<int64_t>(s.t_src * 1e9), RCL_ROS_TIME);
    tr.header.frame_id = world_frame_;
    tr.target_id = target_id_;

    // 位置：加噪后的**原始观测**（用户裁定「位置加噪」；噪声对下游可见、可被真值比对）
    tr.pose.pose.position.x = s.x;
    tr.pose.pose.position.y = s.y;
    tr.pose.pose.position.z = s.z;
    tr.pose.pose.orientation.x = s.quat[0];
    tr.pose.pose.orientation.y = s.quat[1];
    tr.pose.pose.orientation.z = s.quat[2];
    tr.pose.pose.orientation.w = s.quat[3];
    diagCov(sigma_xy_, sigma_z_, tr.pose.covariance);

    // 速度：α-β 滤波器输出（用户裁定「滤波器估计速度」）；零噪声时回落到精确差分
    std::array<double, 3> v{{0.0, 0.0, 0.0}};
    double wz = 0.0;
    if (filterActive()) {
      v = {{fx_.v, fy_.v, fz_.v}};
      // 角速度仍用短窗差分（偏航不参与位置滤波；静态目标差分为 0）
      wz = yawRate();
    } else {
      diffVelocity(v, wz);
    }
    tr.twist.twist.linear.x = v[0];
    tr.twist.twist.linear.y = v[1];
    tr.twist.twist.linear.z = v[2];
    tr.twist.twist.angular.x = 0.0;
    tr.twist.twist.angular.y = 0.0;
    tr.twist.twist.angular.z = wz;
    // 速度协方差：α-β 稳态速度方差 ≈ β²·σ_p²/(Δt²·(2−β)) 的量级；此处按保守上界报告
    diagCov(sigma_xy_, sigma_z_, tr.twist.covariance);

    tr.confidence = static_cast<float>(confidence_);
    tr.source = kSource;
    return tr;
  }

  void tick()
  {
    const double now_s = now().seconds();

    // 释放到期的延迟样本（按源采样时刻顺序喂滤波器；只把**最新**一条用于发布）
    bool released = false;
    Pending newest;
    while (!pending_.empty() && pending_.front().release_t <= now_s) {
      newest = pending_.front();
      pending_.pop_front();
      feedFilter(newest);
      history_.push_back(newest);
      if (history_.size() > 500) {history_.pop_front();}
      released = true;
    }

    agc_msgs::msg::TargetTrackArray arr;
    arr.header.stamp = now();
    arr.header.frame_id = world_frame_;
    if (released) {
      arr.tracks.push_back(buildTrack(newest));
      has_pose_ = true;
      ++published_;
    } else if (has_pose_) {
      // **显式**发空数组：本拍无新样本（丢包 / 延迟未到）→ 下游按"无目标"处理，
      // 绝不重发上次位置冒充新观测（出口判据：不确定性可观测）。
      ++empty_pubs_;
    }
    if (has_pub_) {pub_->publish(arr);}

    // 诊断（不确定性必须**可观测**，不得静默计数）：
    // 每 5 s 汇总一次：入站数 / 丢包 / 队列溢出 / 已发布 / 空发布 / 延迟队列深度。
    if (diag_period_s_ > 0.0 && (now_s - last_diag_s_) >= diag_period_s_) {
      last_diag_s_ = now_s;
      RCLCPP_INFO(get_logger(),
        "gt_adapter 诊断(%.0fs)：入站=%llu 丢包=%llu(%.1f%%) 溢出=%llu "
        "已发布=%llu 空发布=%llu 延迟队列=%zu",
        diag_period_s_,
        static_cast<unsigned long long>(received_),
        static_cast<unsigned long long>(diag_dropped_),
        received_ > 0 ? 100.0 * static_cast<double>(diag_dropped_) /
          static_cast<double>(received_) : 0.0,
        static_cast<unsigned long long>(diag_overflow_),
        static_cast<unsigned long long>(published_),
        static_cast<unsigned long long>(empty_pubs_),
        pending_.size());
    }
  }

  std::string world_frame_, target_model_, target_id_, gt_topic_, target_topic_, target_source_;
  std::string seed_;
  double rate_hz_{10.0};
  // 不确定性
  double sigma_xy_{0.0}, sigma_z_{0.0}, latency_s_{0.0}, drop_prob_{0.0};
  double drop_burst_prob_{0.0}, drop_burst_mean_s_{0.5}, drop_burst_mean_gap_s_{5.0};
  double tol_m_{0.25}, confidence_{1.0};
  // 滤波器
  double filter_sigma_w_{0.5}, diff_window_s_{0.15};
  bool filter_enabled_{true};
  agc::AlphaBeta fx_, fy_, fz_;
  double filter_t_{0.0};
  bool has_filter_t_{false};

  bool has_pub_{false}, has_pose_{false};
  double last_t_{0.0};
  bool has_prev_t_{false};
  bool burst_state_{false};
  // 诊断计数（不确定性必须可观测，不得静默累加）
  unsigned long long received_{0}, diag_dropped_{0}, diag_overflow_{0};
  unsigned long long published_{0}, empty_pubs_{0};
  double diag_period_s_{5.0}, last_diag_s_{0.0};

  std::mt19937 rng_;
  std::deque<Pending> pending_;
  std::deque<Pending> history_;

  rclcpp::Publisher<agc_msgs::msg::TargetTrackArray>::SharedPtr pub_;
  rclcpp::Subscription<geometry_msgs::msg::PoseStamped>::SharedPtr gt_sub_;
  rclcpp::TimerBase::SharedPtr timer_;
};

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<GtAdapter>());
  rclcpp::shutdown();
  return 0;
}
