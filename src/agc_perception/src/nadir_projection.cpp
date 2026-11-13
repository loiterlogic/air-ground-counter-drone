// nadir_projection —— 机载正下视语义分割 → 地面 2D 占据观测
//
// 职责：把 `/agc/air/nadir/seg/labels_map`（3 通道 8bit，B 通道 = label id）中
// 属于障碍标签的像素，用 `/agc/air/nadir/depth`（rgbd 深度图）反投影成**真实 3D 点**，
// 按连通域聚合成带 yaw 的 OBB（XY 包络 + z 范围），发布
// `agc_msgs/msg/ObstacleTrackArray` 到 `/agc/obstacles`，供 `map_adapter` 的 live_ 槽位消费。
//
// **为什么用深度而不是"投到地面平面"**（2026-11-08 修）：正下视画面里不只有屋顶，
// 还有高层建筑的**侧墙**。把标签像素一律投到 z=0，等于假设"每个像素都落在地面上"，
// 墙像素会被按 H/(H−h) 向外放大 —— yard 实测 admin_block（10.55 m / H=14.24 m）
// 糊成 3.86 倍面积、罐区 2.28 倍、整图 IoU 仅 0.363，视觉上就是"影子"。
// 有深度后每个像素的 3D 位置直接可测，视差误差归零，并顺带得到障碍高度（写入 size.z）。
//
// 为什么不用 TF 查外参：相机固定在 `nadir_cam_link`（相对 base_link z=+0.242、
// pitch=+1.5708），该 frame_id 在本仓 TF 树里没有发布者（见 ADR-0030）。故外参由
// 「机体 odom 的世界位姿（world→body）」+「相机→机体固定旋转」在本节点内合成，
// 全部可标定、可单测，不依赖悬空 TF，也不新增 transform broadcaster。
//
// 内参来自 `/agc/air/nadir/camera_info`（与 RGB 相机共位姿共内参），经
// `image_geometry::PinholeCameraModel::projectPixelTo3dRay` 求相机系射线。
//
// 只做 2D：不输出障碍顶面高度、不改 /agc/map 为三维、不覆盖低/悬空障碍感知。

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <deque>
#include <limits>
#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <vector>
#include <unordered_map>

#include <sensor_msgs/image_encodings.hpp>

#include <opencv2/core.hpp>
#include <opencv2/imgproc.hpp>

#include <cv_bridge/cv_bridge.hpp>
#include <agc_perception/nadir_geometry.hpp>
#include <agc_perception/point_uncertainty.hpp>

#include <rclcpp/rclcpp.hpp>
#include <geometry_msgs/msg/quaternion.hpp>
#include <nav_msgs/msg/odometry.hpp>
#include <sensor_msgs/msg/camera_info.hpp>
#include <sensor_msgs/msg/image.hpp>
#include <agc_msgs/msg/obstacle_track.hpp>
#include <agc_msgs/msg/obstacle_track_array.hpp>
#include <agc_msgs/msg/obstacle_footprint_array.hpp>

namespace
{

using agc_perception::aggregateObbs;
using agc_perception::CamIntrinsics;
using agc_perception::CamPose;
using agc_perception::kObstacleLabel;
using agc_perception::Obb;
using agc_perception::pixelDepthToWorld;
using agc_perception::TrackState;
using agc_perception::ShapeWindow;
using agc_perception::Quat;
using agc_perception::Vec3;

// 从 sensor_msgs/CameraInfo 的 k 矩阵直接取 fx/fy/cx/cy。
// 不经过 PinholeCameraModel：分割图是已渲染、无畸变图像，只需原始针孔内参；
// 且 gz 的 camera_info 是一次性/latched 发布，避免依赖桥转换的完整性。
// k 布局：[fx,0,cx, 0,fy,cy, 0,0,1]；k[0]/k[4]/k[8] 须为正且有限。
bool intrinsicsFrom(const sensor_msgs::msg::CameraInfo & ci, CamIntrinsics & out)
{
  if (ci.k.size() < 9) {return false;}
  const double fx = ci.k[0], fy = ci.k[4], cx = ci.k[2], cy = ci.k[5];
  if (!(std::isfinite(fx) && std::isfinite(fy) && std::isfinite(cx) && std::isfinite(cy))
    || fx <= 0.0 || fy <= 0.0 || ci.k[8] <= 0.0)
  {
    return false;
  }
  out = {fx, fy, cx, cy};
  return true;
}

CamPose poseFrom(const nav_msgs::msg::Odometry & odom)
{
  CamPose p;
  p.body_pos = {odom.pose.pose.position.x, odom.pose.pose.position.y,
    odom.pose.pose.position.z};
  const auto & q = odom.pose.pose.orientation;
  p.body_q = {q.x, q.y, q.z, q.w};
  return p;
}

double stampSeconds(const builtin_interfaces::msg::Time & t)
{
  return static_cast<double>(t.sec) + 1e-9 * static_cast<double>(t.nanosec);
}

class NadirProjection : public rclcpp::Node
{
public:
  NadirProjection()
  : rclcpp::Node("nadir_projection")
  {
    labels_topic_ = declare_parameter<std::string>(
      "labels_topic", "/agc/air/nadir/seg/labels_map");
    depth_topic_ = declare_parameter<std::string>(
      "depth_topic", "/agc/air/nadir/depth");
    info_topic_ = declare_parameter<std::string>(
      "camera_info_topic", "/agc/air/nadir/seg/camera_info");
    // 标签与深度来自**两个不同传感器**（segmentation 与 rgbd），靠时间戳配对。
    // ⚠ 2026-11-08 实测更正：**不是**"同一次渲染就自动对齐"——rgbd 只保证它自己的
    // color 与 depth 对齐；segmentation 是另一个传感器，实测两者时间戳偏差
    // p50=32 ms、p95=196 ms、最大 364 ms，只有约 51% 的帧能精确同戳。
    //
    // 容差由**几何判据**定，不靠感觉：错位造成的地面位移须 < 半个地图格（0.25 m）。
    //   地面 GSD = H/f = 14.242/268.6 = 5.30 cm/px；UAV 最大 2.0 m/s（air.yaml max_speed_mps）
    //   ⇒ dt ≤ 0.25/2.0 = 0.125 s
    // 取 0.10 s：实测配对覆盖率 100%（p95=196 ms 的尾部也被覆盖），
    // 最坏错位 0.20 m = 3.8 px，仍在半格内。
    depth_tol_s_ = declare_parameter<double>("depth_pair_tolerance_s", 0.10);
    // odom 查询容差（2026-11-09）：按**标签时间戳**取相机位姿，超出此时间差即丢帧。
    // 取 0.15 s 与深度配对同量级 —— 位姿错位与深度错位是同一类误差。
    odom_tol_s_ = declare_parameter<double>("odom_pair_tolerance_s", 0.15);
    // odom 环形缓冲长度（条）：30 Hz × 2 s = 60；留一倍余量给突发抖动。
    odom_buffer_n_ = declare_parameter<int>("odom_buffer_n", 120);
    // 深度环形缓冲长度（帧）：用于"按标签时间戳选最近的深度"，而不是"用最新一张"。
    depth_buffer_n_ = declare_parameter<int>("depth_buffer_n", 8);
    // 四元数范数容差（2026-11-09）：偏离单位四元数超过此值即判 odom 非法、丢帧。
    quat_norm_tol_ = declare_parameter<double>("quat_norm_tolerance", 0.01);
    // 深度空间一致性门限（m）：0 = 关闭。与相邻像素轴向深度差超过它即判边缘。
    depth_edge_m_ = declare_parameter<double>("depth_edge_m", 0.5);
    // 碎片合并（2026-11-09）：被深度噪声/遮挡/画幅边缘切碎的大障碍，
    // 每块单独可能低于面积门限。空间邻近 + 高度一致的碎片并入达标母体后再判门限。
    // gap=0 即关闭（与改造前逐字节等价，用于对照）。
    fragment_merge_gap_m_ = declare_parameter<double>("fragment_merge_gap_m", 1.5);
    fragment_merge_dz_m_ = declare_parameter<double>("fragment_merge_dz_m", 1.0);
    odom_topic_ = declare_parameter<std::string>("odom_topic", "/agc/air/odom");
    out_topic_ = declare_parameter<std::string>("obstacles_topic", "/agc/obstacles");
    // 足迹点话题（2026-11-08 Q7/Q28）：与 OBB 话题**并行**发布。
    // 为什么并行而不是替换：OBB 仍被 viz 与跨帧关联使用，替换会让批次 2 与批次 3
    // 耦合；等批次 3 删掉框之后，OBB 话题再一并退役（届时本话题成为唯一障碍输出）。
    footprint_topic_ = declare_parameter<std::string>(
      "footprint_topic", "/agc/obstacle_footprints");
    world_frame_ = declare_parameter<std::string>("world_frame", "world");
    label_id_ = declare_parameter<int>("obstacle_label", kObstacleLabel);
    // 连通域最小尺寸（2026-11-08 用户裁定 Q26：像素 → **物理量**）。
    // **判据**：横截面小于 `min_obstacle_side_m` 的碎片不进地图。
    // 为什么改成物理量：固定像素数会让判据**随飞行高度漂移** —— 飞低了 GSD 变小，
    // 同样的像素门限对应更小的物理尺寸 ⇒ 突然多出一堆 0.05 m 的碎片；
    // 飞高了则反之，细杆被静默吞掉。自主定高一旦上线，固定像素门限就不可解释。
    // 换算：`min_area_px = (min_obstacle_side_m / GSD)²`，GSD 由当前相机高度与焦距实时算。
    // 缺省 0.24 m 沿用改造前的口径（640×480@100°、H=14.24 m 时恰为 20 px）。
    // **代价（已如实登记）**：横截面 < 0.24 m 的细杆（灯杆 0.12、门柱 0.18、消防栓 0.16）
    // 不进 /agc/map；它们由**车的激光**在 20 m 内局部感知（分工，非丢失）。
    min_obstacle_side_m_ = declare_parameter<double>("min_obstacle_side_m", 0.24);
    // 关联门：新观测与上一帧 track 的质心距离 ≤ 此值才认为是同一目标。
    // 取 2.5 m（2026-11-08 由 1.5 提高，用户裁定）：连通域在帧间会**分裂/合并**
    // （实测每帧障碍数在 6/7/8 之间变），碎片与母体的质心差可达 2 m 量级；
    // 门太小会让碎片被判成新目标、每帧新增/消失 1.2 个 id，画面上就是持续跳变。
    gate_m_ = declare_parameter<double>("assoc_gate_m", 2.5);
    // 尺寸平滑系数（0<alpha≤1）；0.35 能把实测 3.14 m 的 sx 跨度压到 ~1 m 量级。
    // **稳健形状估计**（2026-11-08 Q1 丙）：窗口长度与 MAD 离群倍数。
    // window_n=10 帧（30 Hz 下 0.33 s）：足够让中位数稳定，又不至于跟不上真实渐变。
    // mad_k=3.0：|x−中位| > 3·MAD 判离群。选 3 而非 2，避免把正常渐变误杀。
    window_n_ = declare_parameter<int>("shape_window_n", 10);
    mad_k_ = declare_parameter<double>("shape_mad_k", 3.0);
    // 连续丢失多少帧后彻底丢弃该 track（30 Hz 下 15 帧 ≈ 0.5 s）。
    max_misses_ = declare_parameter<int>("max_misses", 15);

    pub_ = create_publisher<agc_msgs::msg::ObstacleTrackArray>(
      out_topic_, rclcpp::QoS(1).transient_local().reliable());
    // 足迹点（2026-11-08 用户裁定 Q7/Q28）：**规划真正需要的是"哪些格被占据"**，
    // 不是"连通域的旋转外接矩形"。OBB 对 L 形/多栋/斜置实体必然包大
    // （实测框面积/真实足迹 1.65×），且框边界随"连通域恰好切在哪"跳变。
    // 直接发点，地面侧按格累积（log_odds + carving），表示误差归零。
    // 这是**新增**的第 10 个消息，不改动契约里 9 个既有消息的字段与顺序。
    footprint_pub_ = create_publisher<agc_msgs::msg::ObstacleFootprintArray>(
      footprint_topic_, rclcpp::QoS(1).transient_local().reliable());

    sub_labels_ = create_subscription<sensor_msgs::msg::Image>(
      labels_topic_, rclcpp::SensorDataQoS(),
      [this](const sensor_msgs::msg::Image::SharedPtr m) {onLabels(m);});
    // 深度图（rgbd 的 depth_image）：R_FLOAT32，值 = 沿光轴的**轴向深度**（米）。
    // **2026-11-09 修正**：改成**环形缓冲**而不是"只存最新一张"。
    // 只存最新一张时，标签帧落后深度半帧（10 Hz 下 50 ms）就配错帧；
    // 现在按标签时间戳选最近的一张，配对误差从"最多一整帧"降到"两帧中较近者"。
    sub_depth_ = create_subscription<sensor_msgs::msg::Image>(
      depth_topic_, rclcpp::SensorDataQoS(),
      [this](const sensor_msgs::msg::Image::SharedPtr m) {
        std::lock_guard<std::mutex> lk(mu_);
        depth_buf_.push_back(m);   // 存 SharedPtr：cv_bridge::toCvShare 要求共享指针（零拷贝）
        while (depth_buf_.size() > static_cast<size_t>(std::max(1, depth_buffer_n_))) {
          depth_buf_.pop_front();
        }
      });
    // camera_info 由 ros_gz_bridge 以 SENSOR_DATA（best-effort）发布；订阅必须同为
    // best-effort，否则 RELIABILITY_QOS_POLICY 不兼容、一条都收不到（实链取证）。
    // 内参直接解析 k 矩阵（instrinsicsFrom），不依赖 fromCameraInfo 的桥转换完整性。
    sub_info_ = create_subscription<sensor_msgs::msg::CameraInfo>(
      info_topic_, rclcpp::SensorDataQoS(),
      [this](const sensor_msgs::msg::CameraInfo::SharedPtr m) {
        std::lock_guard<std::mutex> lk(mu_);
        CamIntrinsics k;
        if (!intrinsicsFrom(*m, k)) {
          RCLCPP_WARN_THROTTLE(
            get_logger(), *get_clock(), 5000,
            "camera_info 的 k 矩阵无效（fx/fy/cx/cy 非有限或非正），投影暂停");
          have_intrinsics_ = false;
          return;
        }
        intrinsics_ = k;
        // **内参必须带图像尺寸**（2026-11-09）：画幅与 GSD 都依赖 width/height，
        // 只存 fx/fy 会让"内参与图像是否同一分辨率"无从校验。
        info_w_ = static_cast<int>(m->width);
        info_h_ = static_cast<int>(m->height);
        have_intrinsics_ = true;
      });
    // 机体位姿：**按时间戳存环形缓冲**（2026-11-09），而不是"只存最新一条"。
    // 图像 10 Hz、odom 30 Hz，拿"最新 odom"服务一张落后 100–200 ms 的标签帧
    // 会产生 0.2–0.4 m 的系统性偏移 —— 接近一个地图格。
    sub_odom_ = create_subscription<nav_msgs::msg::Odometry>(
      odom_topic_, rclcpp::QoS(10),
      [this](const nav_msgs::msg::Odometry::SharedPtr m) {
        std::lock_guard<std::mutex> lk(mu_);
        agc_perception::PoseSample s;
        s.stamp_s = stampSeconds(m->header.stamp);
        s.pose = poseFrom(*m);
        // 非法姿态**不进缓冲**（NaN 会污染插值，比丢一帧危险得多）。
        if (!agc_perception::quatFinite(s.pose.body_q)) {return;}
        if (!std::isfinite(s.pose.body_pos.x) || !std::isfinite(s.pose.body_pos.y) ||
          !std::isfinite(s.pose.body_pos.z))
        {
          return;
        }
        odom_buf_.push_back(s);
        while (odom_buf_.size() > static_cast<size_t>(std::max(2, odom_buffer_n_))) {
          odom_buf_.pop_front();
        }
      });

    RCLCPP_INFO(
      get_logger(),
      "nadir_projection 就绪：labels=%s depth=%s info=%s odom=%s out=%s label=%d "
      "assoc_gate=%.2fm depth_tol=%.3fs",
      labels_topic_.c_str(), depth_topic_.c_str(), info_topic_.c_str(),
      odom_topic_.c_str(), out_topic_.c_str(), label_id_, gate_m_, depth_tol_s_);
  }

private:
  void onLabels(const sensor_msgs::msg::Image::SharedPtr msg)
  {
    // ---- 严格时间同步（2026-11-09 用户裁定 P0）----
    // 标签、深度、odom 是三个独立流。此前只存"最新一条深度"和"最新一条 odom"，
    // 收到标签帧就直接拿缓存 —— 三者可能来自三个不同时刻，最终点不对应任何真实时刻。
    // 现在：深度按**标签时间戳**从环形缓冲里选最近一帧；位姿按**同一时间戳**插值。
    const double t_label = stampSeconds(msg->header.stamp);

    CamIntrinsics k;
    int info_w = 0, info_h = 0;
    sensor_msgs::msg::Image::ConstSharedPtr depth_msg;
    std::vector<agc_perception::PoseSample> odom_samples;
    bool have_intrinsics = false;
    {
      std::lock_guard<std::mutex> lk(mu_);
      k = intrinsics_;
      info_w = info_w_;
      info_h = info_h_;
      have_intrinsics = have_intrinsics_;
      // 选**时间上最近**的深度帧（不是最新一帧）
      double best_dt = std::numeric_limits<double>::infinity();
      for (const auto & d : depth_buf_) {
        const double dt = std::fabs(stampSeconds(d->header.stamp) - t_label);
        if (dt < best_dt) {
          best_dt = dt;
          depth_msg = d;
        }
      }
      odom_samples.assign(odom_buf_.begin(), odom_buf_.end());
    }
    if (!have_intrinsics) {
      RCLCPP_WARN_THROTTLE(
        get_logger(), *get_clock(), 5000,
        "缺少有效 camera_info，跳过本帧（不发布空观测掩盖失效）");
      return;
    }
    // **没有深度就不发观测**（2026-11-08）：退回"投到地面平面"会让高层建筑的侧墙
    // 糊成影子（实测 IoU 0.363、面积膨胀 2.17×），那是**错误的地图**，
    // 比"暂时没有地图"更危险——规划会以为障碍真的伸出去那么远。
    // 故这里如实失败：跳过本帧 + 告警，让 map_adapter 的 source_max_age 判失效。
    if (!depth_msg) {
      RCLCPP_WARN_THROTTLE(
        get_logger(), *get_clock(), 5000,
        "缺少深度图 %s，跳过本帧（无深度时不做地面平面投影——那会把侧墙糊成影子）",
        depth_topic_.c_str());
      return;
    }
    // 标签与深度来自两个传感器，必须时间对齐才能逐像素查深度。
    const double dt = std::fabs(t_label - stampSeconds(depth_msg->header.stamp));
    if (dt > depth_tol_s_) {
      RCLCPP_WARN_THROTTLE(
        get_logger(), *get_clock(), 5000,
        "标签与深度时间差 %.3fs > 容差 %.3fs，跳过本帧（错位会把墙深套到别的像素上）",
        dt, depth_tol_s_);
      return;
    }
    // 位姿按**标签时间戳**查询/插值；超时即丢帧（不拿最近的位姿凑）。
    CamPose pose;
    double odom_dt = 0.0;
    if (!agc_perception::poseAtTime(odom_samples, t_label, odom_tol_s_, pose, &odom_dt)) {
      RCLCPP_WARN_THROTTLE(
        get_logger(), *get_clock(), 5000,
        "标签时刻 %.3f 无可用 odom（容差 %.3fs），跳过本帧", t_label, odom_tol_s_);
      return;
    }
    // 姿态合法性：范数偏离单位四元数即丢帧（投影公式默认单位四元数）。
    if (!agc_perception::quatUnit(pose.body_q, quat_norm_tol_)) {
      RCLCPP_WARN_THROTTLE(
        get_logger(), *get_clock(), 5000,
        "odom 姿态非法（|q|=%.4f，容差 %.3f），跳过本帧",
        agc_perception::quatNorm(pose.body_q), quat_norm_tol_);
      return;
    }
    last_depth_dt_s_ = dt;
    last_odom_dt_s_ = odom_dt;

    // ---- 标签↔深度时间错位的**空间补偿**（ADR-0039）----
    //
    // 标签像素来自「标签时刻」，而它的深度值来自**另一帧**（最近深度帧，可能早/晚
    // ≤`depth_pair_tolerance_s`）。直接反投影等于假设"两帧之间相机没动" —— 2 m/s
    // 时那是 0.30 m 的系统性错位，而 dense_map 的障碍只有 0.6–1.2 m 宽、栅格 0.5 m。
    //
    // 补偿方式：查出**深度时刻**的机体位置，把点从"深度时刻的相机系"平移到
    // "标签时刻的世界系"。两帧只差一个平移（同一台相机、≤0.15 s，姿态变化对
    // 地面点的贡献远小于平移，且姿态已按标签时刻 slerp 插值）。
    //
    // 深度时刻查不到 odom 时**不补偿**（旧行为）并计数 —— 不拿猜的位置去平移，
    // 那会把一个已知的小错位换成未知的大错位。
    agc_perception::Vec3 depth_body_shift;
    {
      const double t_depth = stampSeconds(depth_msg->header.stamp);
      CamPose pose_at_depth;
      double depth_odom_dt = 0.0;
      if (std::fabs(t_depth - t_label) <= 1e-6) {
        // 标签与深度**同戳**（gz 同一次渲染）：不存在错位，无需补偿。
        // 这是实测的常见情形（`dt_depth=0.000s`），**不能**算作"缺位姿" ——
        // 否则诊断会把"不需要补"和"补不了"混成一个数，掩盖真实缺口。
        last_depth_shift_m_ = 0.0;
        ++depth_shift_not_needed_frames_;
      } else if (agc_perception::poseAtTime(
          odom_samples, t_depth, odom_tol_s_, pose_at_depth, &depth_odom_dt))
      {
        depth_body_shift.x = pose_at_depth.body_pos.x - pose.body_pos.x;
        depth_body_shift.y = pose_at_depth.body_pos.y - pose.body_pos.y;
        depth_body_shift.z = pose_at_depth.body_pos.z - pose.body_pos.z;
        last_depth_shift_m_ = std::hypot(depth_body_shift.x, depth_body_shift.y);
        ++depth_shifted_frames_;
      } else {
        // 有时间差但查不到位姿 ⇒ 确实补不了，计数（诊断要能区分这两种情况）
        last_depth_shift_m_ = 0.0;
        ++depth_shift_missing_frames_;
      }
    }

    cv_bridge::CvImageConstPtr cv_ptr;
    try {
      cv_ptr = cv_bridge::toCvShare(msg, sensor_msgs::image_encodings::BGR8);
    } catch (const cv_bridge::Exception & e) {
      RCLCPP_WARN_THROTTLE(
        get_logger(), *get_clock(), 5000, "labels_map cv_bridge 失败：%s", e.what());
      return;
    }
    const cv::Mat & img = cv_ptr->image;
    if (img.channels() < 3) {
      RCLCPP_WARN_THROTTLE(
        get_logger(), *get_clock(), 5000,
        "labels_map 需为 3 通道（B=label id），实际 %d 通道", img.channels());
      return;
    }
    // 深度图：gz rgbd 发布 R_FLOAT32（桥后 32FC1），值是**轴向深度**（米）。
    cv_bridge::CvImageConstPtr depth_ptr;
    try {
      depth_ptr = cv_bridge::toCvShare(depth_msg, sensor_msgs::image_encodings::TYPE_32FC1);
    } catch (const cv_bridge::Exception & e) {
      RCLCPP_WARN_THROTTLE(
        get_logger(), *get_clock(), 5000,
        "depth cv_bridge 失败（期望 32FC1）：%s", e.what());
      return;
    }
    const cv::Mat & depth = depth_ptr->image;
    if (depth.size() != img.size()) {
      RCLCPP_WARN_THROTTLE(
        get_logger(), *get_clock(), 5000,
        "深度图尺寸 %dx%d 与标签图 %dx%d 不一致，跳过本帧",
        depth.cols, depth.rows, img.cols, img.rows);
      return;
    }

    // **内参必须与图像同分辨率**（2026-11-09）：只比深度/标签尺寸还不够 ——
    // 若 camera_info 是另一档分辨率（gz 换档、桥缓存旧值），fx 与像素坐标就不配套，
    // 点会**系统性**偏移（不是随机噪声）。宁可丢帧，也不要发布系统性错误的地图。
    if (info_w > 0 && info_h > 0 && (info_w != img.cols || info_h != img.rows)) {
      RCLCPP_WARN_THROTTLE(
        get_logger(), *get_clock(), 5000,
        "camera_info 尺寸 %dx%d 与图像 %dx%d 不一致，跳过本帧"
        "（内参与像素不配套会让点系统性偏移）",
        info_w, info_h, img.cols, img.rows);
      return;
    }

    cv::Mat mask(img.size(), CV_8UC1, cv::Scalar(0));
    cv::Mat xs(img.size(), CV_32FC1, cv::Scalar(NAN));
    cv::Mat ys(img.size(), CV_32FC1, cv::Scalar(NAN));
    cv::Mat zs(img.size(), CV_32FC1, cv::Scalar(NAN));
    // 深度空间一致性（2026-11-09）：与右/下邻像素的**轴向深度**跳变超过门限即判边缘，
    // 该像素不进点池。深度边缘是"墙深被套到地面像素"的主要来源，其投影点会外扩很远。
    const double depth_edge_m = depth_edge_m_;
    const int step = 1;  // 全分辨率；1152² 在 Jazzy 实机足够
    long edge_rejected = 0;
    for (int v = 0; v < img.rows; v += step) {
      for (int u = 0; u < img.cols; u += step) {
        const cv::Vec3b & px = img.at<cv::Vec3b>(v, u);
        if (static_cast<int>(px[0]) != label_id_) {continue;}
        // **主路径**：查该像素的深度 → 反投影出真实 3D 点。
        const float d = depth.at<float>(v, u);
        if (!std::isfinite(d) || d <= 0.0f) {continue;}
        if (depth_edge_m > 0.0) {
          bool on_edge = false;
          const float dr = (u + 1 < img.cols) ? depth.at<float>(v, u + 1) : d;
          const float dd = (v + 1 < img.rows) ? depth.at<float>(v + 1, u) : d;
          if (std::isfinite(dr) && dr > 0.0f && std::fabs(dr - d) > depth_edge_m) {
            on_edge = true;
          }
          if (std::isfinite(dd) && dd > 0.0f && std::fabs(dd - d) > depth_edge_m) {
            on_edge = true;
          }
          if (on_edge) {++edge_rejected; continue;}
        }
        Vec3 p;
        if (!pixelDepthToWorld(k, u, v, static_cast<double>(d), pose, p)) {continue;}
        // **时间错位补偿**（ADR-0039）：把点从"深度时刻的相机系"平移到标签时刻。
        p = agc_perception::shiftPointByBodyMotion(p, depth_body_shift);
        // 只保留地面以上的点：地面本身不是障碍（分割已排除，但深度噪点可能落到 z<0）。
        if (p.z < -0.5) {continue;}
        mask.at<uint8_t>(v, u) = 255;
        xs.at<float>(v, u) = static_cast<float>(p.x);
        ys.at<float>(v, u) = static_cast<float>(p.y);
        zs.at<float>(v, u) = static_cast<float>(p.z);
      }
    }
    depth_edge_rejected_ = edge_rejected;

    // 运行时把**物理门限**换算成像素门限（2026-11-08 Q26）。
    // GSD = H/f，H = 相机相对地面的高度（机体 z + 相机安装高），f 来自 camera_info。
    // 高度无效（odom 未就绪）时退回"1 像素"——即不额外过滤，让下游按 OBB 尺寸兜底；
    // **不**退回一个猜的高度（那会让门限静默变成另一个物理含义）。
    const double cam_h = pose.body_pos.z + agc_perception::kCamMountZ;
    const double gsd = agc_perception::gsdFromHeightAndFocal(cam_h, k.fx);
    min_area_px_ = (gsd > 0.0)
      ? agc_perception::minAreaPxForPhysicalSize(min_obstacle_side_m_, gsd)
      : 1;

    // ---- 点池（2026-11-09 性能修复）：一次 CC 同时供 OBB 聚合与足迹点发布 ----
    // 改造前这里是 `aggregateObbs(mask,...)` + `publishFootprints(...)`，各自跑一次
    // `connectedComponentsWithStats`，且 aggregateObbs 内部还按连通域**各扫全图两遍**
    // （O(C·N²)，1152² 下 C=30 就要 89 ms，10 Hz 预算 100 ms 的临界点）。
    // 现在 CC 只做一次、全图只扫一次，复杂度与连通域个数解耦。
    // 碎片合并门限（2026-11-09）：大型建筑被深度噪声/遮挡/画幅边缘切成多块时，
    // 每块单独都可能低于面积门限。先按"空间邻近 + 高度一致"并入达标母体，再判门限。
    agc_perception::FragmentMergeParams merge;
    merge.max_gap_m = fragment_merge_gap_m_;
    merge.max_dz_m = fragment_merge_dz_m_;
    const auto comp_points = agc_perception::collectComponentPoints(
      mask, xs, ys, zs, min_area_px_, merge, &depth);
    // `obb_labels[k]` = 第 k 个 OBB 所属的连通域 label（ADR-0041）。
    // **必须显式取**：OBB 下标与 label 不一一对应（有段被跳过），用下标猜会把实例 id
    // 贴到错误的点上，而且错得很安静。
    std::vector<int> obb_labels;
    auto obbs = agc_perception::aggregateObbs(comp_points, min_area_px_, &obb_labels);

    // **足迹点发布移到跨帧关联之后**（ADR-0041）：点要带实例 id，而 id 由下面的
    // `associateNearest` 分配。改造前这里先发点、后关联，于是点永远拿不到实例归属 ——
    // 这正是"几何层不是第一等公民"的具体表现。

    // ---- 每帧诊断（2026-11-09）：把「真实连通域数 / 实际帧率」变成可观测数字 ----
    // 性能临界点是 C ≈ 30（1152²），而 C 由场景决定、不由代码决定。没有这条日志时
    // 只能靠 launch.log 里 map 重建行的疏密去反推，而那个数字是**内容变化率**、
    // 不是帧率（内容收敛后自然掉下来），我据此做过错误推断。这里如实上报。
    reportFrameStats(comp_points, obbs);

    // ---- 跨帧 id 关联 + 尺寸平滑（2026-11-08 修「地图一直跳变」）----
    // 旧做法 id = 质心量化格，质心一抖 id 就翻格 → 下游同一障碍反复画/擦。
    // 现改为最近邻关联：id 一旦分配就随目标走，不随质心漂移。
    // 连通域 label → 实例 id（ADR-0041）。键是 `comp_points.group_of` 的**母体 label**，
    // 这样被并入母体的碎片点也会跟着拿到母体的 id。
    std::unordered_map<int, std::string> label_to_id;
    std::vector<std::pair<double, double>> obs;
    obs.reserve(obbs.size());
    for (const auto & o : obbs) {
      if (o.sx <= 0.0 || o.sy <= 0.0 || o.area_px < min_area_px_) {continue;}
      obs.emplace_back(o.cx, o.cy);
    }
    const auto assoc = agc_perception::associateNearest(obs, tracks_, gate_m_);

    // ⚠ 必须是**空** vector 再 push_back：写成 next_tracks(tracks_.size()) 会预填
    // tracks_.size() 个默认条目，push_back 又追加 → tracks_ 每帧膨胀、与 prev_id_ 长度
    // 错位 → prev_id_[a.index] 越界读垃圾字符串 → FastCDR 序列化抛
    // "The string contains null characters"、节点 abort（2026-11-08 实测崩溃）。
    std::vector<TrackState> next_tracks;
    next_tracks.reserve(obbs.size() + tracks_.size());
    std::vector<std::string> next_ids;
    next_ids.reserve(obbs.size() + tracks_.size());
    std::vector<bool> track_seen(tracks_.size(), false);
    std::vector<agc_perception::ShapeWindow> next_windows;
    next_windows.reserve(obbs.size() + tracks_.size());

    agc_msgs::msg::ObstacleTrackArray arr;
    arr.header.stamp = msg->header.stamp;
    arr.header.frame_id = world_frame_;
    size_t oi = 0;
    for (const auto & o : obbs) {
      if (o.sx <= 0.0 || o.sy <= 0.0 || o.area_px < min_area_px_) {continue;}
      const auto & a = assoc[oi];
      ++oi;

      std::string id;
      TrackState st;
      if (a.index >= 0) {
        // 命中既有目标：继承 id 与平滑后的尺寸
        const auto & prev = tracks_[a.index];
        id = prev_id_[a.index];
        st = prev;
        st.hits += 1;
        st.misses = 0;
        st.x = o.cx;
        st.y = o.cy;
        // **稳健估计**（Q1 丙）：把本帧观测压进该 id 的历史窗口，再用
        // "中位数 + MAD 剔除离群"出尺寸/朝向。这样某帧侧墙整片断开造成的
        // 形状大幅跳变会被 MAD 判为离群**直接丢弃**，不会污染输出；
        // 而真实渐变（UAV 移动导致侧墙可见性缓慢变化）MAD 会跟随，不被误杀。
        auto & win = windows_[a.index];
        win.sx.push_back(o.sx);
        win.sy.push_back(o.sy);
        win.sz.push_back(std::max(0.0, o.z_max - o.z_min));
        win.zc.push_back(0.5 * (o.z_min + o.z_max));
        win.yaw.push_back(o.yaw);
        for (auto * v : {&win.sx, &win.sy, &win.sz, &win.zc, &win.yaw}) {
          if (v->size() > static_cast<size_t>(window_n_)) {v->erase(v->begin());}
        }
        const auto esx = agc_perception::robustEstimate(win.sx, mad_k_);
        const auto esy = agc_perception::robustEstimate(win.sy, mad_k_);
        const auto esz = agc_perception::robustEstimate(win.sz, mad_k_);
        const auto ezc = agc_perception::robustEstimate(win.zc, mad_k_);
        const auto eyaw = agc_perception::robustEstimateAngle(win.yaw, mad_k_, prev.yaw);
        st.sx = esx.median;
        st.sy = esy.median;
        st.sz = esz.median;
        st.zc = ezc.median;
        st.yaw = eyaw.median;
        rejected_total_ += esx.rejected;
        track_seen[a.index] = true;
        // 窗口随 track 一起推进（**同一处 push**，保证两表顺序严格一致）
        next_windows.push_back(win);
      } else {
        // 新目标：分配一个**单调递增**的 id（不再用质心量化格，避免翻格）
        id = "nadir_" + std::to_string(next_id_++);
        st.x = o.cx;
        st.y = o.cy;
        st.sx = o.sx;
        st.sy = o.sy;
        st.sz = std::max(0.0, o.z_max - o.z_min);
        st.zc = 0.5 * (o.z_min + o.z_max);
        st.yaw = o.yaw;
        st.hits = 1;
        st.misses = 0;
        // 新目标：用本帧观测初始化窗口
        agc_perception::ShapeWindow w;
        w.sx.push_back(o.sx);
        w.sy.push_back(o.sy);
        w.sz.push_back(std::max(0.0, o.z_max - o.z_min));
        w.zc.push_back(0.5 * (o.z_min + o.z_max));
        w.yaw.push_back(o.yaw);
        next_windows.push_back(std::move(w));
      }
      next_tracks.push_back(st);
      next_ids.push_back(id);

      // label → 实例 id（ADR-0041）：供足迹点按点填 `point_instance_id`。
      // 用**同一个** id 变量，保证点与 OBB 的实例归属不可能分叉。
      if (oi - 1 < obb_labels.size()) {
        label_to_id[static_cast<size_t>(obb_labels[oi - 1])] = id;
      }
      agc_msgs::msg::ObstacleTrack t;
      t.header.stamp = msg->header.stamp;
      t.header.frame_id = world_frame_;
      t.obstacle_id = id;
      t.pose.position.x = o.cx;
      t.pose.position.y = o.cy;
      // pose.z = 障碍**竖直中心**（底 = z_min，顶 = z_max）；旧版恒 0。
      t.pose.position.z = st.zc;
      t.pose.orientation.w = std::cos(st.yaw / 2.0);
      t.pose.orientation.z = std::sin(st.yaw / 2.0);
      t.size.x = st.sx;
      t.size.y = st.sy;
      // 高度由深度直接观测（不再恒 0）：2026-11-08 用户裁定"以后大概率会用到"。
      // 注意 `/agc/map` 仍是 2D 栅格，map_adapter 只用 sx/sy 做栅格化，
      // 写 z 不改变现有地图行为；它是给将来 3D 消费者（低空避让 / 垂直门控）留的接口。
      t.size.z = st.sz;
      t.confidence = 1.0f;
      t.source = "nadir_segmentation";
      arr.tracks.push_back(t);
    }

    // 保留本轮未命中的旧 track（计入 misses），超过 max_misses 才彻底丢弃。
    for (size_t j = 0; j < tracks_.size(); ++j) {
      if (track_seen[j]) {continue;}
      TrackState st = tracks_[j];
      st.misses += 1;
      if (st.misses > max_misses_) {continue;}
      next_tracks.push_back(st);
      next_ids.push_back(prev_id_[j]);
      next_windows.push_back(j < windows_.size() ? windows_[j] : agc_perception::ShapeWindow{});
    }
    // 不变式：tracks_ 与 prev_id_ 必须**等长**（否则下一次关联会越界读 id）。
    // 用显式检查而非 assert：release 构建下 assert 会被去掉，这个 bug 会静默复活。
    if (next_tracks.size() != next_ids.size() || next_tracks.size() != next_windows.size()) {
      RCLCPP_ERROR(
        get_logger(),
        "内部不变式被破坏：tracks=%zu ids=%zu windows=%zu，清空关联表以防越界",
        next_tracks.size(), next_ids.size(), next_windows.size());
      next_tracks.clear();
      next_ids.clear();
      next_windows.clear();
      next_id_ = 0;
    }
    tracks_ = std::move(next_tracks);
    windows_ = std::move(next_windows);
    prev_id_ = std::move(next_ids);

    pub_->publish(arr);

    // ---- 足迹点发布（2026-11-08 用户裁定 Q7/Q28；ADR-0041 移到此处）----
    // 与 OBB 并行发：OBB 供 viz 与跨帧关联用。
    // 只发**属于有效连通域**的点：孤立噪点（不达物理门限）不得进地图，
    // 否则"最小可测尺寸"的判据在点层就被绕过了。
    publishFootprints(
      msg->header.stamp, comp_points, label_to_id, pose, k,
      stampSeconds(depth_msg->header.stamp) - t_label);

    RCLCPP_DEBUG(
      get_logger(), "labels_map → %zu 个 OBB（label=%d）", arr.tracks.size(), label_id_);
  }

  // 发布足迹点（2026-11-08 用户裁定 Q7/Q28）。
  //
  // **为什么只发"属于有效连通域"的点**：`aggregateObbs` 已按物理门限筛过连通域；
  // 若这里直接把整张 mask 的点全发出去，孤立噪点会绕过最小可测尺寸判据，
  // 让"细杆不进地图"这条能力边界失效。
  //
  // **2026-11-09 性能修复**：改造前这里对同一张 mask **又跑一次 CC + 一次全图扫描**，
  // 与 `aggregateObbs` 里的两次全图扫描叠加。现在直接复用点池 `comp_points`：
  // 点池里只含 `area_px ≥ min_area_px_` 的连通域（门限口径不变），且已是光栅顺序，
  // 连 `labels` / `keep` 都不再需要。
  //
  // 逐点开销：单帧约 1–3 万点（1152²、障碍占比 5%），每点 24 B ⇒ 0.3–0.7 MB/帧，
  // 10 Hz 下 3–7 MB/s —— 比整幅深度图（16.78 MB/帧）小一个量级，这是本设计的收益之一。
  void publishFootprints(
    const builtin_interfaces::msg::Time & stamp,
    const agc_perception::ComponentPoints & comp_points,
    const std::unordered_map<int, std::string> & label_to_id,
    const agc_perception::CamPose & pose,
    const agc_perception::CamIntrinsics & intr,
    double depth_time_offset_s)
  {
    // 空数组 = 本拍无新观测（契约语义），不是"障碍消失"。
    agc_msgs::msg::ObstacleFootprintArray out;
    out.header.stamp = stamp;
    out.header.frame_id = world_frame_;
    out.obstacle_id = "nadir_frame";
    out.confidence = 1.0f;
    out.source = "nadir_segmentation";
    // 预分配：点池点数已知，直接按它 reserve（不再按画幅面积猜）。
    out.points.reserve(comp_points.points.size());
    // **2026-11-09 修复（实测 bug）**：只发**通过屋顶带门限**的点。
    //
    // 改造前这里发的是点池里的**全部**点，而屋顶带过滤只在 `aggregateObbs` 内部
    // 对 OBB 生效 ⇒ **侧墙点被逐点栅格化**。侧墙点投影到地面会外扩 `H/(H−h)` 倍
    // （9 m 高的楼 2.74×、10.55 m 的 3.86×），实测误覆盖散布到离障碍
    // **1–24 格（最大 11.9 m）**，与侧墙外扩量级完全吻合。
    //
    // 现在掩码 `comp_points.kept` 在点池层算一次，OBB 聚合与足迹点发布**共用**它，
    // 两边不可能再分叉。z 已保证有限，这里只需再校验 x/y。
    out.points.reserve(comp_points.points.size());
    // 并行数组与 `points` **同下标**（ADR-0041）：三个数组必须等长，
    // 下游按同一个下标读。长度在下面逐个 push，天然对齐。
    out.point_instance_id.reserve(comp_points.points.size());
    out.point_class.reserve(comp_points.points.size());
    // 逐点不确定度（ADR-0042）：与 `points` 同下标，四条并行数组。
    // **只在点池带了观测几何时才填**（`point_depth` 非空）。不填就留空数组 =
    // "本发布端不提供该信息"，下游按无信息处理 —— 这比填 0 更诚实
    // （0 协方差会被读成"非常准"）。
    const bool have_uncertainty = !comp_points.point_depth.empty();
    if (have_uncertainty) {
      out.point_cov_xx.reserve(comp_points.points.size());
      out.point_cov_xy.reserve(comp_points.points.size());
      out.point_cov_yy.reserve(comp_points.points.size());
      out.point_view_cos.reserve(comp_points.points.size());
    }
    const agc_perception::PointUncertaintyParams up;
    double max_sigma = 0.0;
    // 批次级元数据（ADR-0042）：一次曝光共享，故不逐点存。
    out.depth_time_offset_s = static_cast<float>(depth_time_offset_s);
    const agc_perception::Vec3 cam_world = agc_perception::cameraWorldOrigin(pose);
    out.observer_origin.x = cam_world.x;
    out.observer_origin.y = cam_world.y;
    out.observer_origin.z = cam_world.z;

    // label → 实例 id 的反查：点属于哪个连通域由 `group_of` 给出（母体 label），
    // 再经 `label_to_id` 换成实例 id。两层映射都在点池层就绪，这里不做任何推断。
    std::vector<std::string> id_of_label(static_cast<size_t>(std::max(0, comp_points.labels_n)));
    for (int i = 0; i < comp_points.labels_n; ++i) {
      const auto it = label_to_id.find(i);
      if (it != label_to_id.end()) {id_of_label[static_cast<size_t>(i)] = it->second;}
    }
    long with_id = 0;
    for (size_t k = 0; k < comp_points.points.size(); ++k) {
      if (!comp_points.isKept(k)) {continue;}
      const auto & cp = comp_points.points[k];
      if (!std::isfinite(cp.x) || !std::isfinite(cp.y)) {continue;}
      geometry_msgs::msg::Point p;
      p.x = cp.x; p.y = cp.y; p.z = cp.z;
      out.points.push_back(p);

      // 实例 id：经 `group_of` 找到母体 label，再查 id。查不到就是空串
      // （未归属），**不猜**一个 id 填进去。
      std::string id;
      if (k < comp_points.point_label.size()) {
        const int root = comp_points.point_label[k];   // 已是母体 label
        if (root >= 0 && static_cast<size_t>(root) < id_of_label.size()) {
          id = id_of_label[static_cast<size_t>(root)];
        }
      }
      if (!id.empty()) {++with_id;}
      out.point_instance_id.push_back(id);

      // 类别：直接取点池算好的结果（与 `kept` 同一判据），不在这里重判。
      const uint8_t cls = (k < comp_points.point_class.size())
        ? comp_points.point_class[k]
        : static_cast<uint8_t>(agc_perception::kPointUnclassified);
      out.point_class.push_back(cls);

      // 逐点协方差 + 观测视角（ADR-0042）。
      // **与 `pixelDepthToWorld` 同一组输入**（内参 / 像素 / 深度 / 位姿），
      // 保证"算点的公式"与"算它有多准的公式"不会分裂成两套几何。
      if (have_uncertainty) {
        const double d = static_cast<double>(comp_points.point_depth[k]);
        const double u = static_cast<double>(comp_points.point_u[k]);
        const double v = static_cast<double>(comp_points.point_v[k]);
        const agc_perception::Cov2 cov =
          agc_perception::pointCovariance(intr, u, v, d, pose, up);
        out.point_cov_xx.push_back(static_cast<float>(cov.xx));
        out.point_cov_xy.push_back(static_cast<float>(cov.xy));
        out.point_cov_yy.push_back(static_cast<float>(cov.yy));
        out.point_view_cos.push_back(
          static_cast<float>(agc_perception::viewCosine(intr, u, v, d, pose)));
        max_sigma = std::max(max_sigma, cov.sigmaMajor());
      }
    }
    footprint_pub_->publish(out);
    footprint_points_ = static_cast<long>(out.points.size());
    footprint_with_id_ = with_id;
    footprint_max_sigma_ = max_sigma;
  }

  // 每帧诊断（2026-11-09）：把「真实连通域数 / 实际帧率 / 单帧耗时」变成可观测数字。
  //
  // **为什么必须有**：1152² 的聚合成本与连通域个数 C 成正比（改造前 O(C·N²)），
  // 而 C 由场景决定。没有这条日志时，只能拿 launch.log 里 map 重建行的疏密去反推，
  // 而那个数是**地图内容变化率**、不是帧率（内容收敛后自然掉下来）—— 我据此做过错误推断。
  // 现在直接上报实测值，C 一旦接近临界点会立刻在日志里看到，不必再猜。
  void reportFrameStats(
    const agc_perception::ComponentPoints & comp_points,
    const std::vector<Obb> & obbs)
  {
    ++frame_count_;
    const rclcpp::Time now_t = now();
    if (last_frame_t_.nanoseconds() == 0) {
      last_frame_t_ = now_t;
      return;
    }
    const double dt = (now_t - last_frame_t_).seconds();
    if (dt < kStatsPeriodS) {return;}
    const double fps = static_cast<double>(frame_count_) / dt;
    // 同步质量必须可见（2026-11-09）：实际使用的标签↔深度、标签↔odom 时间差，
    // 以及被深度边缘判据剔除的像素数。没有这些数字就只能靠猜。
    RCLCPP_INFO(
      get_logger(),
      "帧统计：%.2f Hz（%d 帧 / %.1fs）| 连通域 %d 个（保留 %zu，碎片并入 %ld）| "
      "障碍像素 %ld | OBB %zu | 足迹点 %ld（带实例 id %ld，最大 1σ=%.2fm）| min_area_px=%d | "
      "同步 dt_depth=%.3fs dt_odom=%.3fs 补偿位移=%.3fm（已补 %ld / 同戳无需补 %ld / 缺位姿 %ld）| "
      "深度边缘剔除 %ld px",
      fps, frame_count_, dt, std::max(0, comp_points.labels_n - 1), obbs.size(),
      comp_points.merged_components, comp_points.raw_pixels, obbs.size(),
      footprint_points_, footprint_with_id_, footprint_max_sigma_, min_area_px_,
      last_depth_dt_s_, last_odom_dt_s_,
      last_depth_shift_m_, depth_shifted_frames_, depth_shift_not_needed_frames_,
      depth_shift_missing_frames_, depth_edge_rejected_);
    frame_count_ = 0;
    last_frame_t_ = now_t;
  }

  rclcpp::Publisher<agc_msgs::msg::ObstacleTrackArray>::SharedPtr pub_;
  rclcpp::Publisher<agc_msgs::msg::ObstacleFootprintArray>::SharedPtr footprint_pub_;
  rclcpp::Subscription<sensor_msgs::msg::Image>::SharedPtr sub_labels_;
  rclcpp::Subscription<sensor_msgs::msg::Image>::SharedPtr sub_depth_;
  rclcpp::Subscription<sensor_msgs::msg::CameraInfo>::SharedPtr sub_info_;
  rclcpp::Subscription<nav_msgs::msg::Odometry>::SharedPtr sub_odom_;

  std::mutex mu_;
  CamIntrinsics intrinsics_;
  bool have_intrinsics_{false};
  int info_w_{0}, info_h_{0};                  // camera_info 声明的图像尺寸
  // 位姿与深度都是**环形缓冲**（2026-11-09 严格同步）：按标签时间戳取用，
  // 不再"只存最新一条"（那会让三者对应三个不同时刻）。
  std::deque<agc_perception::PoseSample> odom_buf_;
  std::deque<sensor_msgs::msg::Image::ConstSharedPtr> depth_buf_;
  // 同步质量（诊断，每帧刷新）
  double last_depth_dt_s_{0.0};
  double last_odom_dt_s_{0.0};
  long depth_edge_rejected_{0};
  // 标签↔深度时间错位补偿（ADR-0039）：实测补偿量与被跳过次数
  double last_depth_shift_m_{0.0};
  long depth_shifted_frames_{0};
  long depth_shift_missing_frames_{0};
  long depth_shift_not_needed_frames_{0};

  std::string labels_topic_, depth_topic_, info_topic_, odom_topic_, out_topic_, world_frame_;
  int label_id_{kObstacleLabel};
  std::string footprint_topic_;
  long footprint_points_{0};          // 上一帧发布的足迹点数（诊断）
  long footprint_with_id_{0};         // 其中带实例 id 的点数（ADR-0041 诊断）
  double footprint_max_sigma_{0.0};   // 本帧最大主方向 1σ（m，ADR-0042 诊断）
  double min_obstacle_side_m_{0.24};   // 物理门限（m）；像素门限由 GSD 实时换算
  int min_area_px_{20};               // 本帧换算结果（诊断 / 内部用）
  double depth_tol_s_{0.05};
  double odom_tol_s_{0.15};
  int odom_buffer_n_{120};
  int depth_buffer_n_{8};
  double quat_norm_tol_{0.01};
  // 深度边缘门限（m）：与相邻像素轴向深度差超过它即视为边缘像素、不进点池。
  // 0.5 m 是"半个地图格"的同量级 —— 深度台阶小于它不会显著改变落点。
  double depth_edge_m_{0.5};
  // 碎片合并（2026-11-09）：空间邻近 + 高度一致，把被切碎的大障碍并回母体。
  double fragment_merge_gap_m_{1.5};
  double fragment_merge_dz_m_{1.0};
  double gate_m_{2.5};
  int window_n_{10};
  double mad_k_{3.0};
  std::vector<agc_perception::ShapeWindow> windows_;
  int rejected_total_{0};
  int max_misses_{15};
  // 跨帧关联状态：tracks_ 与 prev_id_ 一一对应；next_id_ 单调递增（id 不再翻格）。
  std::vector<agc_perception::TrackState> tracks_;
  std::vector<std::string> prev_id_;
  int next_id_{0};
  // 帧统计（2026-11-09）：把实际帧率 / 连通域数变成可观测数字。
  // 周期取 5 s：足够看出趋势，又不会在 90 s 的 demo 里刷屏。
  static constexpr double kStatsPeriodS = 5.0;
  int frame_count_{0};
  rclcpp::Time last_frame_t_{0, 0, RCL_ROS_TIME};
};

}  // namespace

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<NadirProjection>());
  rclcpp::shutdown();
  return 0;
}
