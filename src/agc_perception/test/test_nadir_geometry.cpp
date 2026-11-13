// nadir_geometry 纯几何单测（L2，不启 ROS / 不启仿真）
//
// 覆盖：像素→地面平面求交、机体姿态（yaw / roll / pitch）对投影的影响、
// 朝上射线失效、连通域→OBB 聚合、以及内参与 PinholeCameraModel 的一致性口径。

#include <cmath>
#include <cstdio>
#include <limits>

#include <gtest/gtest.h>
#include <opencv2/core.hpp>

#include <image_geometry/pinhole_camera_model.hpp>
#include <sensor_msgs/msg/camera_info.hpp>

#include "agc_perception/camera_geometry.hpp"
#include "agc_perception/log_odds_grid.hpp"
#include "agc_perception/nadir_geometry.hpp"
#include "agc_perception/track_association.hpp"

using agc_perception::aggregateObbs;
using agc_perception::associateNearest;
using agc_perception::smoothAngle;
using agc_perception::robustEstimate;
using agc_perception::ShapeWindow;
using agc_perception::robustEstimateAngle;
using agc_perception::smoothScalar;
using agc_perception::TrackState;
using agc_perception::CamIntrinsics;
using agc_perception::CamPose;
using agc_perception::kCamMountZ;
using agc_perception::Obb;
using agc_perception::pixelToGround;
using agc_perception::Quat;
using agc_perception::Vec3;

namespace
{

CamIntrinsics defaultK()
{
  return {268.6, 268.6, 320.0, 240.0};
}

CamPose levelPose(double x, double y, double z)
{
  CamPose p;
  p.body_pos = {x, y, z};
  p.body_q = {0.0, 0.0, 0.0, 1.0};
  return p;
}

Quat yawQuat(double yaw)
{
  return {0.0, 0.0, std::sin(yaw / 2.0), std::cos(yaw / 2.0)};
}

}  // namespace

TEST(CameraGeometry, WorldToGridUsesFloorAtGridLinesAndNegativeCoordinates)
{
  using agc_perception::worldToGrid;
  EXPECT_EQ(worldToGrid(0.0, 0.0, 0.5), 0);
  EXPECT_EQ(worldToGrid(0.499999999, 0.0, 0.5), 0);
  EXPECT_EQ(worldToGrid(0.5, 0.0, 0.5), 1);
  EXPECT_EQ(worldToGrid(-0.000001, 0.0, 0.5), -1);
  EXPECT_EQ(worldToGrid(-0.5, 0.0, 0.5), -1);
  EXPECT_EQ(worldToGrid(-0.500001, 0.0, 0.5), -2);
  EXPECT_EQ(worldToGrid(-1.0, -1.0, 0.25), 0);
  EXPECT_EQ(worldToGrid(-0.76, -1.0, 0.25), 0);
  EXPECT_EQ(worldToGrid(-0.75, -1.0, 0.25), 1);
}

TEST(CameraGeometry, WorldToGridRejectsInvalidResolution)
{
  using agc_perception::worldToGridChecked;
  int index = 42;
  EXPECT_FALSE(worldToGridChecked(1.0, 0.0, 0.0, index));
  EXPECT_EQ(index, 42);
  EXPECT_FALSE(worldToGridChecked(std::numeric_limits<double>::quiet_NaN(), 0.0, 0.5, index));
  EXPECT_EQ(index, 42);
}

TEST(NadirGeometry, CenterPixelHitsNadir)
{
  const CamIntrinsics k = defaultK();
  const double H = 14.0;
  const CamPose pose = levelPose(0.0, 0.0, H);
  Vec3 g;
  ASSERT_TRUE(pixelToGround(k, k.cx, k.cy, pose, g));
  EXPECT_NEAR(g.x, 0.0, 1e-9);
  EXPECT_NEAR(g.y, 0.0, 1e-9);
  EXPECT_NEAR(g.z, 0.0, 1e-9);
}

// 2. 边缘像素对称（轴映射经 gz GUI 实测标定：u↔v 互换 + 双符号反转）
//    +Δu → world −y，+Δv → world −x。
TEST(NadirGeometry, OffCenterPixelsAreSymmetric)
{
  const CamIntrinsics k = defaultK();
  const CamPose pose = levelPose(0.0, 0.0, 14.0);
  const double du = 100.0, dv = 80.0;
  Vec3 a, b, c, d;
  ASSERT_TRUE(pixelToGround(k, k.cx + du, k.cy, pose, a));
  ASSERT_TRUE(pixelToGround(k, k.cx - du, k.cy, pose, b));
  ASSERT_TRUE(pixelToGround(k, k.cx, k.cy + dv, pose, c));
  ASSERT_TRUE(pixelToGround(k, k.cx, k.cy - dv, pose, d));
  EXPECT_NEAR(a.y, -b.y, 1e-9);
  EXPECT_NEAR(a.x, b.x, 1e-9);
  EXPECT_NEAR(c.x, -d.x, 1e-9);
  EXPECT_NEAR(c.y, d.y, 1e-9);
  // 净轴映射：world_x = −H·Δv/f，world_y = −H·Δu/f；
  // H = 机体高度 + 相机安装高（nadir_cam_joint z=+kCamMountZ，相机在机体上方）。
  const double H = 14.0 + kCamMountZ;
  EXPECT_NEAR(a.y, -H * du / k.fx, 1e-6);
  EXPECT_NEAR(c.x, -H * dv / k.fy, 1e-6);
}

// 3. 机体平移直接带到地面交点
TEST(NadirGeometry, BodyTranslationMovesGroundPoint)
{
  const CamIntrinsics k = defaultK();
  const CamPose pose = levelPose(3.0, -2.0, 10.0);
  Vec3 g;
  ASSERT_TRUE(pixelToGround(k, k.cx, k.cy, pose, g));
  EXPECT_NEAR(g.x, 3.0, 1e-9);
  EXPECT_NEAR(g.y, -2.0, 1e-9);
}

// 4. 机体 yaw 90°：新轴映射下 +Δu 对应 body −y；yaw=+90° 把 body −y 转到 world +x
TEST(NadirGeometry, YawRotatesImageFrame)
{
  const CamIntrinsics k = defaultK();
  CamPose pose = levelPose(0.0, 0.0, 14.0);
  pose.body_q = yawQuat(M_PI / 2.0);
  const double du = 100.0;
  Vec3 a;
  ASSERT_TRUE(pixelToGround(k, k.cx + du, k.cy, pose, a));
  EXPECT_NEAR(a.y, 0.0, 1e-6);
  EXPECT_NEAR(a.x, (14.0 + kCamMountZ) * du / k.fx, 1e-6);
}

// 4b. gz GUI 实测靶点复现（最硬判据）：相机 (0,0,14) 正俯视，障碍顶面中心
//     world (2,1,z=1) 落在 labels_map 像素 (299,199)，内参 f=268.6 cx=320 cy=240。
//     因正俯视只看到顶面，投影按 z=0 平面会略有透视差，误差应 < 0.3 m。
TEST(NadirGeometry, GuiMeasuredTargetReproduced)
{
  const CamIntrinsics k = defaultK();
  const CamPose pose = levelPose(0.0, 0.0, 14.0);
  Vec3 g;
  ASSERT_TRUE(pixelToGround(k, 299.0, 199.0, pose, g));
  EXPECT_NEAR(g.x, 2.0, 0.3);
  EXPECT_NEAR(g.y, 1.0, 0.3);
}

// 5. 机体 roll 会让光轴倾斜，中心像素不再落在正下方（验证外参真的参与）
TEST(NadirGeometry, RollTiltsOpticalAxis)
{
  const CamIntrinsics k = defaultK();
  CamPose pose = levelPose(0.0, 0.0, 14.0);
  const double roll = 0.1;
  pose.body_q = {std::sin(roll / 2.0), 0.0, 0.0, std::cos(roll / 2.0)};
  Vec3 g;
  ASSERT_TRUE(pixelToGround(k, k.cx, k.cy, pose, g));
  EXPECT_GT(std::fabs(g.y), 0.5);  // 明显偏离正下方
}

// 6. 相机在地面以下 / 射线朝上 → 无交点
TEST(NadirGeometry, UpwardRayHasNoGroundHit)
{
  const CamIntrinsics k = defaultK();
  CamPose pose = levelPose(0.0, 0.0, 14.0);
  // 把机体翻 180°（roll=π）→ 相机朝上
  pose.body_q = {1.0, 0.0, 0.0, 0.0};
  Vec3 g;
  EXPECT_FALSE(pixelToGround(k, k.cx, k.cy, pose, g));
}

// 7. 内参口径与 image_geometry::PinholeCameraModel 一致
TEST(NadirGeometry, IntrinsicsMatchPinholeModel)
{
  sensor_msgs::msg::CameraInfo info;
  info.width = 640; info.height = 480;
  info.k = {268.6, 0.0, 320.0, 0.0, 268.6, 240.0, 0.0, 0.0, 1.0};
  info.p = {268.6, 0.0, 320.0, 0.0, 0.0, 268.6, 240.0, 0.0, 0.0, 0.0, 1.0, 0.0};
  info.distortion_model = "plumb_bob";
  image_geometry::PinholeCameraModel model;
  ASSERT_TRUE(model.fromCameraInfo(info));
  const auto ray_model = model.projectPixelTo3dRay(cv::Point2d(420.0, 300.0));
  const Vec3 ray = agc_perception::pixelRay(defaultK(), 420.0, 300.0);
  EXPECT_NEAR(ray.x, ray_model.x, 1e-9);
  EXPECT_NEAR(ray.y, ray_model.y, 1e-9);
  EXPECT_NEAR(ray.z, ray_model.z, 1e-9);
}

// 8. 合成矩形 mask → 单 OBB，中心/尺寸/yaw 正确
TEST(NadirGeometry, AggregateObbFromRectMask)
{
  const int W = 200, H = 200;
  cv::Mat mask(H, W, CV_8UC1, cv::Scalar(0));
  cv::Mat xs(H, W, CV_32FC1, cv::Scalar(NAN));
  cv::Mat ys(H, W, CV_32FC1, cv::Scalar(NAN));
  cv::Mat zs(H, W, CV_32FC1, cv::Scalar(NAN));
  // 地面矩形：x∈[2,6], y∈[1,3]，1 px = 0.05 m；z 恒 0（地面障碍）
  for (int v = 20; v < 60; ++v) {
    for (int u = 40; u < 120; ++u) {
      mask.at<uint8_t>(v, u) = 255;
      xs.at<float>(v, u) = static_cast<float>(u * 0.05);
      ys.at<float>(v, u) = static_cast<float>(v * 0.05);
      zs.at<float>(v, u) = 0.0f;
    }
  }
  const auto obbs = aggregateObbs(mask, xs, ys, zs, 4);
  ASSERT_EQ(obbs.size(), 1u);
  const Obb & o = obbs[0];
  EXPECT_NEAR(o.cx, 4.0, 0.1);   // (2+6)/2
  EXPECT_NEAR(o.cy, 2.0, 0.1);   // (1+3)/2
  EXPECT_NEAR(o.sx, 4.0, 0.2);   // 长边
  EXPECT_NEAR(o.sy, 2.0, 0.2);
  // minAreaRect 对轴对齐矩形的 angle 约定可能为 ±90°；OBB 只需长边尺寸正确，
  // yaw 允许 0 / ±π（等价朝向），不锁单一数值。
  const double wrapped = std::fabs(std::atan2(std::sin(o.yaw), std::cos(o.yaw)));
  EXPECT_TRUE(wrapped < 0.1 || std::fabs(wrapped - M_PI) < 0.1)
    << "yaw=" << o.yaw << " wrapped=" << wrapped;
  EXPECT_GT(o.area_px, 1000);
}

// 9. 两个不相连掩码 → 两个 OBB；低于 min_area 的噪声被过滤
TEST(NadirGeometry, AggregateObbSeparatesComponentsAndDropsNoise)
{
  const int W = 120, H = 60;
  cv::Mat mask(H, W, CV_8UC1, cv::Scalar(0));
  cv::Mat xs(H, W, CV_32FC1, cv::Scalar(NAN));
  cv::Mat ys(H, W, CV_32FC1, cv::Scalar(NAN));
  cv::Mat zs(H, W, CV_32FC1, cv::Scalar(NAN));
  for (int i = 0; i < 2; ++i) {
    const int x0 = 10 + i * 60;
    for (int v = 10; v < 40; ++v) {
      for (int u = x0; u < x0 + 30; ++u) {
        mask.at<uint8_t>(v, u) = 255;
        xs.at<float>(v, u) = static_cast<float>(u * 0.1);
        ys.at<float>(v, u) = static_cast<float>(v * 0.1);
        zs.at<float>(v, u) = 0.0f;
      }
    }
  }
  mask.at<uint8_t>(55, 110) = 255;  // 单像素噪声
  xs.at<float>(55, 110) = 11.0f;
  ys.at<float>(55, 110) = 5.5f;
  zs.at<float>(55, 110) = 0.0f;
  const auto obbs = aggregateObbs(mask, xs, ys, zs, 4);
  ASSERT_EQ(obbs.size(), 2u);
}

// ---------------------------------------------------------------------------------
// 10. 深度反投影（2026-11-08 起的主路径）：轴向深度 → world 3D 点
// ---------------------------------------------------------------------------------

// 正下视：相机在 (0,0,H) 时，中心像素深度 = H ⇒ 落点 (0,0,0)。
// 注意 `body_pos` 是**机体**原点，相机在其上方 kCamMountZ —— 测试必须按真实外参摆位，
// 否则会把"安装高度"误算进结果（第一版就是这么错的）。
TEST(NadirGeometry, DepthCenterPixelHitsGroundBelow)
{
  CamIntrinsics k;
  CamPose pose;
  const double H = 10.0;
  pose.body_pos = {0.0, 0.0, H - agc_perception::kCamMountZ};
  Vec3 p;
  ASSERT_TRUE(pixelDepthToWorld(k, 320.0, 240.0, H, pose, p));
  EXPECT_NEAR(p.x, 0.0, 1e-6);
  EXPECT_NEAR(p.y, 0.0, 1e-6);
  EXPECT_NEAR(p.z, 0.0, 1e-6);
}

// 同一像素给不同深度 ⇒ 落点沿同一条射线移动；深度 = 相机高度 ⇒ 落在地面 z=0。
// 这条把"深度是轴向深度"钉死：若被误当欧氏距离，边缘像素的 z 会偏离 0。
TEST(NadirGeometry, DepthIsAxialNotEuclidean)
{
  CamIntrinsics k;
  CamPose pose;
  const double H = 10.0;
  pose.body_pos = {0.0, 0.0, H - agc_perception::kCamMountZ};
  // 半视场边缘的像素
  const double u = 0.0, v = 240.0;
  // 轴向深度 d 使落点正好在 z=0：光轴朝下 ⇒ 世界 z = H − d
  Vec3 p;
  ASSERT_TRUE(pixelDepthToWorld(k, u, v, H, pose, p));
  EXPECT_NEAR(p.z, 0.0, 1e-6) << "轴向深度 d=H 必须落在 z=0（若按欧氏距离解释会偏离）";
  // 该像素的地面落点应等于 pixelToGround 的结果（两条路径在"平地面"上必须一致）
  Vec3 g;
  ASSERT_TRUE(pixelToGround(k, u, v, pose, g));
  EXPECT_NEAR(p.x, g.x, 1e-6);
  EXPECT_NEAR(p.y, g.y, 1e-6);
}

// **本轮的根因判据**：高层建筑的侧墙点不能被放大到地面上。
// 场景：10 m 高的墙、相机 14.242 m 正上方、墙在 x=+4.7 处。
// 旧做法（投到地面）会把墙顶糊到 x≈H/(H−h)·4.7 之外；新做法用真实深度，
// 落点必须仍在 x=4.7 附近（墙的真实位置）。
TEST(NadirGeometry, WallPointsStayAtWallNotSmearOutward)
{
  CamIntrinsics k;
  CamPose pose;
  const double camH = 14.242;
  pose.body_pos = {0.0, 0.0, camH - agc_perception::kCamMountZ};
  const double wall_x = 4.7;
  const double wall_top = 10.0;
  // 墙顶某点的真实 3D 位置 → 反推它应落在哪个像素、深度是多少
  // （用 pixelToGround 无法反推，这里直接构造：取该点相对相机的向量）
  const Vec3 rel{wall_x, 0.0, wall_top - camH};
  // body_p = rel；p_cam 由实测轴映射的逆：(p_cam.x, p_cam.y, p_cam.z) = (−body.y, −body.x, −body.z)
  const double d = -rel.z;                       // 轴向深度（光轴朝下）
  const double u = k.cx + k.fx * (-rel.y) / d;   // p_cam.x = −body.y
  const double v = k.cy + k.fy * (-rel.x) / d;   // p_cam.y = −body.x
  Vec3 p;
  ASSERT_TRUE(pixelDepthToWorld(k, u, v, d, pose, p));
  EXPECT_NEAR(p.x, wall_x, 1e-6) << "墙点必须留在墙上，不得被放大到地面";
  EXPECT_NEAR(p.z, wall_top, 1e-6);
  // 对照：同像素若投到地面，会跑到明显更远的位置（这就是"影子"）
  Vec3 g;
  ASSERT_TRUE(pixelToGround(k, u, v, pose, g));
  EXPECT_GT(std::fabs(g.x), wall_x + 1.0) << "旧做法应显著外溢（证明根因存在）";
}

// 无效深度必须被拒绝（0 / 负 / NaN / inf），不得产出假点。
TEST(NadirGeometry, InvalidDepthIsRejected)
{
  CamIntrinsics k;
  CamPose pose;
  pose.body_pos = {0.0, 0.0, 10.0};
  Vec3 p;
  EXPECT_FALSE(pixelDepthToWorld(k, 320.0, 240.0, 0.0, pose, p));
  EXPECT_FALSE(pixelDepthToWorld(k, 320.0, 240.0, -1.0, pose, p));
  EXPECT_FALSE(pixelDepthToWorld(k, 320.0, 240.0, std::nan(""), pose, p));
  EXPECT_FALSE(pixelDepthToWorld(k, 320.0, 240.0, std::numeric_limits<double>::infinity(), pose, p));
}

// 3D 点聚合：z 范围被正确记录（高度不再是 0），且 XY 包络不含侧墙外溢。
TEST(NadirGeometry, AggregateObbCarriesHeightFromDepth)
{
  const int W = 100, H = 100;
  cv::Mat mask(H, W, CV_8UC1, cv::Scalar(0));
  cv::Mat xs(H, W, CV_32FC1, cv::Scalar(NAN));
  cv::Mat ys(H, W, CV_32FC1, cv::Scalar(NAN));
  cv::Mat zs(H, W, CV_32FC1, cv::Scalar(NAN));
  // 一个 2×2 m、高 6 m 的柱：XY 恒定，z 从 0 到 6
  for (int v = 10; v < 40; ++v) {
    for (int u = 10; u < 40; ++u) {
      mask.at<uint8_t>(v, u) = 255;
      xs.at<float>(v, u) = 5.0f;
      ys.at<float>(v, u) = 3.0f;
      zs.at<float>(v, u) = static_cast<float>((v - 10) / 29.0 * 6.0);
    }
  }
  const auto obbs = aggregateObbs(mask, xs, ys, zs, 4);
  ASSERT_EQ(obbs.size(), 1u);
  EXPECT_NEAR(obbs[0].cx, 5.0, 0.01);
  EXPECT_NEAR(obbs[0].cy, 3.0, 0.01);
  EXPECT_NEAR(obbs[0].z_min, 0.0, 0.01);
  EXPECT_NEAR(obbs[0].z_max, 6.0, 0.01);
}

// ---------------------------------------------------------------------------------
// 11. 跨帧 id 关联（修「地图一直跳变」的核心判据）
// ---------------------------------------------------------------------------------

// 质心在关联门内抖动 ⇒ 必须继承同一 id（旧"量化格"做法会翻格）。
TEST(NadirGeometry, AssociationKeepsIdWhenCentroidJitters)
{
  std::vector<TrackState> tracks(1);
  tracks[0].x = 10.0;
  tracks[0].y = 5.0;
  // 质心抖 0.3 m（实测量级），远小于 1.5 m 门
  const std::vector<std::pair<double, double>> obs{{10.3, 5.1}};
  const auto a = associateNearest(obs, tracks, 1.5);
  ASSERT_EQ(a.size(), 1u);
  EXPECT_EQ(a[0].index, 0) << "门内抖动必须继承原 id，不得分配新 id";
}

// 超出关联门 ⇒ 判为新目标（避免把两个不同障碍强行合并）。
TEST(NadirGeometry, AssociationRejectsFarObservations)
{
  std::vector<TrackState> tracks(1);
  tracks[0].x = 10.0;
  tracks[0].y = 5.0;
  const std::vector<std::pair<double, double>> obs{{13.0, 5.0}};  // 3 m 远
  const auto a = associateNearest(obs, tracks, 1.5);
  ASSERT_EQ(a.size(), 1u);
  EXPECT_EQ(a[0].index, -1) << "门外必须是新目标，不得继承 id";
}

// 两个观测争同一个旧 track ⇒ 最近的拿到，另一个成为新目标（贪心一对一）。
TEST(NadirGeometry, AssociationIsOneToOneGreedy)
{
  std::vector<TrackState> tracks(1);
  tracks[0].x = 0.0;
  tracks[0].y = 0.0;
  const std::vector<std::pair<double, double>> obs{{0.2, 0.0}, {0.6, 0.0}};
  const auto a = associateNearest(obs, tracks, 1.5);
  ASSERT_EQ(a.size(), 2u);
  EXPECT_EQ(a[0].index, 0) << "更近的观测应拿到旧 track";
  EXPECT_EQ(a[1].index, -1) << "旧 track 已被占用，另一个必须是新目标";
}

// 尺寸平滑：alpha=1 不滤波；alpha<1 抑制跳变；首帧（prev=NaN）直接采用当前值。
TEST(NadirGeometry, SizeSmoothingDampsJitter)
{
  EXPECT_DOUBLE_EQ(smoothScalar(1.0, 3.0, 1.0), 3.0) << "alpha=1 应完全不滤波";
  const double s = smoothScalar(1.0, 3.0, 0.35);
  EXPECT_GT(s, 1.0);
  EXPECT_LT(s, 3.0) << "alpha<1 必须把跳变压向中间";
  EXPECT_DOUBLE_EQ(smoothScalar(std::nan(""), 2.5, 0.35), 2.5) << "首帧直接采用观测值";
}

// 角度平滑必须走最短弧：π−ε 与 −π+ε 是"同一个朝向"，不得绕远路。
TEST(NadirGeometry, AngleSmoothingTakesShortestArc)
{
  const double prev = M_PI - 0.1;
  const double cur = -M_PI + 0.1;
  const double r = smoothAngle(prev, cur, 0.5);
  // 最短弧路径会跨过 ±π，结果应接近 ±π 而非 0
  EXPECT_GT(std::fabs(r), 3.0) << "应跨 ±π 走短弧，而不是穿过 0";
}

// 关联表不变式：tracks 与 id 必须等长，且连续多帧不得膨胀。
// 这条守的是一个**实测崩溃**：next_tracks(size) 预填 + push_back 会让表每帧翻倍、
// 与 id 表错位，越界读到垃圾字符串 → FastCDR 序列化抛
// "The string contains null characters"、节点 abort（表现为"跳变没了，障碍也没了"）。
TEST(NadirGeometry, AssociationTableDoesNotGrowAcrossFrames)
{
  std::vector<TrackState> tracks;
  std::vector<std::string> ids;
  int next_id = 0;
  // 模拟 20 帧、每帧 3 个稳定观测（质心小幅抖动）
  for (int frame = 0; frame < 20; ++frame) {
    const std::vector<std::pair<double, double>> obs{
      {10.0 + 0.05 * frame, 5.0}, {20.0, 8.0}, {30.0, 2.0}};
    const auto assoc = associateNearest(obs, tracks, 1.5);
    std::vector<TrackState> nt;
    std::vector<std::string> ni;
    std::vector<bool> seen(tracks.size(), false);
    for (size_t i = 0; i < obs.size(); ++i) {
      TrackState st;
      std::string id;
      if (assoc[i].index >= 0) {
        st = tracks[assoc[i].index];
        id = ids[assoc[i].index];      // 若两表错位，这里就是越界读
        seen[assoc[i].index] = true;
      } else {
        id = "nadir_" + std::to_string(next_id++);
      }
      st.x = obs[i].first;
      st.y = obs[i].second;
      nt.push_back(st);
      ni.push_back(id);
    }
    for (size_t j = 0; j < tracks.size(); ++j) {
      if (seen[j]) {continue;}
      TrackState st = tracks[j];
      st.misses += 1;
      if (st.misses > 15) {continue;}
      nt.push_back(st);
      ni.push_back(ids[j]);
    }
    ASSERT_EQ(nt.size(), ni.size()) << "第 " << frame << " 帧：两表必须等长";
    tracks = nt;
    ids = ni;
    ASSERT_LE(tracks.size(), 3u) << "第 " << frame << " 帧：表不得膨胀（稳定观测应恒为 3）";
  }
  EXPECT_EQ(tracks.size(), 3u);
  EXPECT_EQ(next_id, 3) << "稳定目标不得被反复分配新 id";
}

// ---------------------------------------------------------------------------------
// 12. 形状稳健估计（修「形状一直在变、偶尔大幅跳再回归」）
// ---------------------------------------------------------------------------------

// 关键判据：一次大幅离群跳变**不得**把估计拉走（这正是用户看到的现象）。
TEST(NadirGeometry, RobustEstimateRejectsSingleOutlier)
{
  // 稳定在 2.0 附近，中间夹一个 5.0 的离群帧（模拟侧墙某帧整片断开）
  const std::vector<double> w{2.0, 2.05, 2.1, 1.95, 5.0, 2.02, 2.08, 1.98, 2.03, 2.06};
  const auto e = robustEstimate(w, 3.0);
  EXPECT_EQ(e.rejected, 1) << "大幅离群帧必须被剔除";
  EXPECT_NEAR(e.median, 2.03, 0.06) << "估计必须留在稳定值附近，不能被 5.0 拉走";
}

// 对照：指数平均会被同一离群拉走（说明为什么不用 EMA）。
TEST(NadirGeometry, ExponentialAverageIsPulledByOutlier)
{
  double ema = 2.0;
  const double alpha = 0.35;
  for (double x : {2.05, 2.1, 1.95, 5.0}) {ema = alpha * x + (1 - alpha) * ema;}
  EXPECT_GT(ema, 2.4) << "EMA 会被离群显著拉走（这就是不用它的原因）";
}

// 真实尺寸渐变必须被跟随（不能把正常变化误判成离群）。
TEST(NadirGeometry, RobustEstimateFollowsGradualChange)
{
  std::vector<double> w;
  for (int i = 0; i < 10; ++i) {w.push_back(2.0 + 0.1 * i);}   // 2.0..2.9 线性
  const auto e = robustEstimate(w, 3.0);
  EXPECT_EQ(e.rejected, 0) << "渐变不应被剔除";
  EXPECT_NEAR(e.median, 2.45, 0.15) << "中位数应落在窗口中段";
}

// 窗口内全同（MAD=0）时不得剔除任何样本。
TEST(NadirGeometry, RobustEstimateHandlesZeroMad)
{
  const std::vector<double> w{2.0, 2.0, 2.0, 2.0};
  const auto e = robustEstimate(w, 3.0);
  EXPECT_EQ(e.rejected, 0);
  EXPECT_NEAR(e.median, 2.0, 1e-9);
  EXPECT_EQ(e.used, 4);
}

// 角度稳健估计必须跨 ±π 正确解卷绕（矩形朝向 mod π，窗口内可能出现 ±π 两种表示）。
// 判据落在**结果**上：三个"同一朝向"的样本（两个用 +π 侧、一个用 −π 侧表示）
// 必须都保留、且估计值接近该朝向 —— 若不解卷绕，−π 侧会被当成"差 2π"的离群。
TEST(NadirGeometry, RobustAngleUnwrapsAcrossPi)
{
  // 真实朝向 ≈ π（180°）；三个样本分别是它的 +π / −π 等价表示，抖动 ≤0.04 rad
  const double ref = M_PI;
  const std::vector<double> w{M_PI - 0.04, -M_PI + 0.02, M_PI - 0.06};
  const auto e = robustEstimateAngle(w, 3.0, ref);
  EXPECT_EQ(e.rejected, 0) << "同一朝向的 ±π 等价表示不得被判离群";
  EXPECT_EQ(e.used, 3);
  // 结果应接近 π（用环形距离判，避免 ±π 表示差异）
  const double d = std::fabs(std::atan2(std::sin(e.median - M_PI), std::cos(e.median - M_PI)));
  EXPECT_LT(d, 0.1) << "估计值必须接近真实朝向 π，实际 " << e.median;
}

// 三表同步：tracks / ids / windows 必须严格等长且顺序对应。
// 这个 bug 出现过两次（先是 tracks 膨胀导致越界读 id 崩溃，再是 windows 与 tracks
// 顺序错位导致稳健估计拿到别人的窗口、形状抖动修不掉），故用一条测试同时锁两件事。
TEST(NadirGeometry, TrackIdWindowTablesStayAligned)
{
  std::vector<TrackState> tracks;
  std::vector<std::string> ids;
  std::vector<ShapeWindow> wins;
  int next_id = 0;
  // 构造"同帧先命中旧目标、再出现新目标"的场景 —— 正是顺序错位最容易暴露的形态
  for (int frame = 0; frame < 12; ++frame) {
    std::vector<std::pair<double, double>> obs;
    obs.emplace_back(10.0, 5.0);                       // 稳定旧目标
    if (frame >= 3) {obs.emplace_back(30.0 + frame, 20.0);}  // 后来出现的新目标
    const auto assoc = associateNearest(obs, tracks, 2.5);
    std::vector<TrackState> nt; std::vector<std::string> ni; std::vector<ShapeWindow> nw;
    std::vector<bool> seen(tracks.size(), false);
    for (size_t i = 0; i < obs.size(); ++i) {
      TrackState st; std::string id; ShapeWindow w;
      if (assoc[i].index >= 0) {
        st = tracks[assoc[i].index];
        id = ids[assoc[i].index];
        w = wins[assoc[i].index];
        seen[assoc[i].index] = true;
      } else {
        id = "nadir_" + std::to_string(next_id++);
      }
      st.x = obs[i].first; st.y = obs[i].second;
      w.sx.push_back(1.0 + 0.01 * frame);
      if (w.sx.size() > 10) {w.sx.erase(w.sx.begin());}
      nt.push_back(st); ni.push_back(id); nw.push_back(std::move(w));
    }
    for (size_t j = 0; j < tracks.size(); ++j) {
      if (seen[j]) {continue;}
      nt.push_back(tracks[j]); ni.push_back(ids[j]);
      nw.push_back(j < wins.size() ? wins[j] : ShapeWindow{});
    }
    ASSERT_EQ(nt.size(), ni.size()) << "第 " << frame << " 帧";
    ASSERT_EQ(nt.size(), nw.size()) << "第 " << frame << " 帧：窗口表必须与 track 表同步";
    // 每个窗口的样本数不得超过窗口长度
    for (const auto & w : nw) {ASSERT_LE(w.sx.size(), 10u);}
    tracks = nt; ids = ni; wins = nw;
  }
  // 稳定目标应保留满窗口（说明窗口确实在累积，而不是每帧被重置成 1）
  ASSERT_GE(wins.size(), 1u);
  EXPECT_GE(wins[0].sx.size(), 8u) << "窗口必须累积多帧，否则稳健估计退化为单帧";
}

// =================================================================================
// 批次 2（2026-11-08 用户裁定 Q8）：z 直方图剔除侧墙
// =================================================================================
//
// **为什么需要**：正下视画面里一栋楼同时有**屋顶**（稳定、就是它的足迹）与**侧墙**
// （可见高度随深度噪声/视角逐帧变化）。改造前 `aggregateObbs` 把侧墙点也纳入 XY 包络，
// 于是同一物体的 sx 在 2.50..3.05 m 间变（真实屋顶 2.0 m），偶尔某帧侧墙整片断开
// → 形状"大幅跳再回归"。这正是用户反馈"障碍物形状面积还一直在变"的直接来源。
//
// **做法**：只保留 z 接近该连通域**最高点**的那一层点（屋顶），其余（侧墙/立面）丢弃。
// 门限是 `max(kMinRoofBandM, kRoofBandRatio × 高度)`，两个参数都在下方面写死并单测。

// 判据：侧墙点不得把屋顶足迹**撑大**。
//
// 物理构造（正下视看一栋楼）：屋顶是水平面 z=10.0；侧墙从屋顶**边缘正下方**向下延伸，
// XY 与屋顶边缘相同（垂直墙面），z 从 9.9 降到 6.0。
// 关键：墙的 XY 与屋顶**重合**，所以它不会撑大包络；真正撑大包络的是**斜视**下的墙
// （投影外扩），那由 z 过滤处理——本测试只验证"垂直墙不会额外扩边"。
//
// **方法的固有边界（如实登记）**：墙与屋顶在交界处 z 相同、XY 也相同，
// 任何纯 z 判据都无法分开它们。能剔除的是"墙的主体"（z 明显低于屋顶的部分）。
TEST(NadirGeometry, RoofBandDropsSideWallPoints)
{
  cv::Mat mask(40, 40, CV_8UC1, cv::Scalar(0));
  cv::Mat xs(40, 40, CV_32F, cv::Scalar(NAN));
  cv::Mat ys(40, 40, CV_32F, cv::Scalar(NAN));
  cv::Mat zs(40, 40, CV_32F, cv::Scalar(NAN));
  // 屋顶：10×10 像素，z=10.0，XY 跨度 0.9 m
  for (int y = 10; y <= 19; ++y) {
    for (int x = 10; x <= 19; ++x) {
      mask.at<uint8_t>(y, x) = 255;
      xs.at<float>(y, x) = 0.1f * x;
      ys.at<float>(y, x) = 0.1f * y;
      zs.at<float>(y, x) = 10.0f;
    }
  }
  // 侧墙：紧贴屋顶**下沿正下方**向下 20 行，XY 与屋顶列相同（垂直墙面），z 递减
  for (int k = 0; k < 20; ++k) {
    const int y = 20 + k;
    const float z = 9.9f - 0.2f * k;          // 9.9 → 6.1
    for (int x = 10; x <= 19; ++x) {
      mask.at<uint8_t>(y, x) = 255;
      xs.at<float>(y, x) = 0.1f * x;          // XY 与屋顶同列（不扩边）
      ys.at<float>(y, x) = 0.1f * (20 + k);   // 沿墙向下延伸
      zs.at<float>(y, x) = z;
    }
  }
  const auto obbs = aggregateObbs(mask, xs, ys, zs, 4);
  ASSERT_EQ(obbs.size(), 1u) << "应聚成一个连通域";
  const Obb & o = obbs[0];
  // 关键判据：面积与跨度都必须**远小于**含整面墙的情形。
  // 屋顶 10×10 像素（0.9×0.9 m）；含整面墙时跨度会到 2.9 m（沿 y 拉长）。
  // 注：`minAreaRect` 出的是**旋转**矩形，残余斜向点会让 sx/sy 各自略大于 0.9，
  // 故判据看"是否包含整面墙"（跨度上限 + 面积），不对某个边长做精确断言。
  const double span = std::max(o.sx, o.sy);
  EXPECT_LT(span, 1.8)
    << "侧墙主体必须被 z 过滤剔除：跨度=" << span
    << "（屋顶 0.9 m，含整面墙约 2.9 m）";
  EXPECT_LT(o.area_px, 300)
    << "保留像素数应明显少于全部点（全部 " << (10 * 10 + 20 * 10) << "，实际 " << o.area_px << "）";
  EXPECT_NEAR(o.z_max, 10.0, 0.1) << "z_max 必须仍是屋顶高度";
  EXPECT_LT(o.z_min, 7.0) << "障碍真实高度仍由全部点给出（不被屋顶带压平）";
}

// 判据：矮而平的障碍（高度 < 门限）不得被 z 直方图**整片剔掉**。
// 这是"固定 0.3 m 门限"会踩的坑：slab_s 这类薄板高 2.6 m 但顶面薄，固定门限会切掉它。
TEST(NadirGeometry, RoofBandKeepsFlatObstacles)
{
  cv::Mat mask(10, 10, CV_8UC1, cv::Scalar(0));
  cv::Mat xs(10, 10, CV_32F, cv::Scalar(NAN));
  cv::Mat ys(10, 10, CV_32F, cv::Scalar(NAN));
  cv::Mat zs(10, 10, CV_32F, cv::Scalar(NAN));
  for (int y = 2; y <= 6; ++y) {
    for (int x = 2; x <= 6; ++x) {
      mask.at<uint8_t>(y, x) = 255;
      xs.at<float>(y, x) = 0.1f * x;
      ys.at<float>(y, x) = 0.1f * y;
      zs.at<float>(y, x) = 0.20f;   // 极矮（20 cm）
    }
  }
  const auto obbs = aggregateObbs(mask, xs, ys, zs, 4);
  ASSERT_EQ(obbs.size(), 1u) << "矮障碍不得被整片剔掉";
  EXPECT_GT(obbs[0].sx, 0.1) << "矮障碍的足迹必须保留";
}

// 判据：门限是**比例 + 绝对下限**的组合，不是固定 0.3 m。
TEST(NadirGeometry, RoofBandThresholdIsRatioWithFloor)
{
  using agc_perception::kRoofBandFloorM;
  using agc_perception::kRoofBandRatio;
  using agc_perception::roofBandThreshold;
  EXPECT_GT(kRoofBandFloorM, 0.0);
  EXPECT_GT(kRoofBandRatio, 0.0);
  EXPECT_LT(kRoofBandRatio, 1.0);
  // 矮障碍（0.5 m 高）→ 门限应被下限托住
  EXPECT_NEAR(roofBandThreshold(0.5), kRoofBandFloorM, 1e-9);
  // 高建筑（10 m 高）→ 门限按比例
  EXPECT_NEAR(roofBandThreshold(10.0), kRoofBandRatio * 10.0, 1e-9);
}

// =================================================================================
// 批次 2b（2026-11-08 用户裁定 Q26）：min_area 从像素改成**物理尺寸**
// =================================================================================
//
// **为什么**：`min_area_px` 的单位是像素，但它的物理含义是"最小可测障碍尺寸"。
// 一旦相机分辨率或飞行高度可变（Q24 的自主定高），固定像素数会让判据**随高度漂移**：
// 飞低了 GSD 变小，同样的像素门限对应更小的物理尺寸 → 突然多出一堆 0.05 m 的碎片。
// 改成物理量 + 运行时换算，判据才稳定。

// 判据：物理尺寸 → 像素门限的换算必须与 GSD 定义一致（面积 = (d/GSD)²）。
TEST(NadirGeometry, MinAreaPxFollowsPhysicalSize)
{
  using agc_perception::minAreaPxForPhysicalSize;
  using agc_perception::gsdFromHeightAndFocal;
  // H=14.242, f=477.5（2048²@130°）⇒ GSD=0.0298 m/px
  const double H = 14.242, f = 477.5;
  const double gsd = gsdFromHeightAndFocal(H, f);
  EXPECT_NEAR(gsd, H / f, 1e-12);
  // d_min=0.24 m ⇒ (0.24/0.0298)² ≈ 65 px
  const int px = minAreaPxForPhysicalSize(0.24, gsd);
  EXPECT_NEAR(px, std::pow(0.24 / gsd, 2), 2.0);
  EXPECT_GT(px, 20) << "2048² 下 GSD 更细，同一物理门限对应更多像素";
}

// 判据：高度升高 ⇒ GSD 变粗 ⇒ 同一物理门限对应的像素数**减少**。
TEST(NadirGeometry, MinAreaPxShrinksWhenFlyingHigher)
{
  using agc_perception::minAreaPxForPhysicalSize;
  using agc_perception::gsdFromHeightAndFocal;
  const double f = 477.5;
  const int low = minAreaPxForPhysicalSize(0.24, gsdFromHeightAndFocal(12.0, f));
  const int high = minAreaPxForPhysicalSize(0.24, gsdFromHeightAndFocal(20.0, f));
  EXPECT_GT(low, high)
    << "飞得高 ⇒ GSD 粗 ⇒ 同样的 0.24 m 障碍只占更少像素（low=" << low << " high=" << high << "）";
}

// 判据：非法输入必须安全（不返回 0 导致"全部通过"，也不崩）。
TEST(NadirGeometry, MinAreaPxRejectsDegenerateInput)
{
  using agc_perception::minAreaPxForPhysicalSize;
  EXPECT_GE(minAreaPxForPhysicalSize(0.24, 0.0), 1) << "GSD=0 时不得返回 0";
  EXPECT_GE(minAreaPxForPhysicalSize(0.24, -1.0), 1) << "GSD<0 时不得返回 0";
  EXPECT_GE(minAreaPxForPhysicalSize(0.0, 0.03), 1) << "尺寸=0 时不得返回 0";
  EXPECT_GE(minAreaPxForPhysicalSize(-1.0, 0.03), 1) << "尺寸<0 时不得返回 0";
}

// ---------------------------------------------------------------------------------
// 点池（2026-11-09 性能修复）：collectComponentPoints + aggregateObbs(ComponentPoints)
// ---------------------------------------------------------------------------------
//
// 背景：改造前 `aggregateObbs` 对**每个连通域各扫全图两遍**，O(C·N²)。
// 640×480 下 C 小、N² 小，掩盖了它；1152² 下实测 C=30 就要 89 ms（10 Hz 预算 100 ms）。
// 修复后一次 CC + 一次全图扫描，成本与 C 解耦。
//
// 这一组测试守两件事：
//   1. **等价性** —— 点池版必须与"逐域扫描"版输出逐字段相同（不能为提速改语义）；
//   2. **不随 C 退化** —— 点池的 raw_pixels 与"所有达标连通域像素之和"一致，
//      且聚合成本不因 C 增大而膨胀（用计数断言，不测时间：单测里计时不可靠）。

namespace
{
// 逐域扫描的参考实现：逐字保留改造前的逻辑，作为等价性基准。
// 刻意**不**重构它 —— 它存在的意义就是"旧口径的原样"，被"优化"掉就失去对拍价值。
std::vector<Obb> referenceAggregateObbs(
  const cv::Mat & mask, const cv::Mat & xs, const cv::Mat & ys, const cv::Mat & zs,
  int min_area)
{
  std::vector<Obb> out;
  cv::Mat labels, stats, centroids;
  const int n = cv::connectedComponentsWithStats(mask, labels, stats, centroids, 8);
  for (int i = 1; i < n; ++i) {
    if (stats.at<int>(i, cv::CC_STAT_AREA) < min_area) {continue;}
    double zlo = std::numeric_limits<double>::infinity();
    double zhi = -std::numeric_limits<double>::infinity();
    std::vector<double> zvals;
    for (int y = 0; y < mask.rows; ++y) {
      for (int x = 0; x < mask.cols; ++x) {
        if (labels.at<int>(y, x) != i) {continue;}
        const float wz = zs.at<float>(y, x);
        if (!std::isfinite(wz)) {continue;}
        zlo = std::min(zlo, static_cast<double>(wz));
        zhi = std::max(zhi, static_cast<double>(wz));
        zvals.push_back(static_cast<double>(wz));
      }
    }
    if (!std::isfinite(zhi)) {continue;}
    const double band = agc_perception::roofBandThreshold(zhi - (std::isfinite(zlo) ? zlo : zhi));
    std::sort(zvals.begin(), zvals.end());
    const double z_cut = agc_perception::roofReferenceHeight(zvals) - band;
    std::vector<cv::Point2f> pts;
    int kept_px = 0;
    for (int y = 0; y < mask.rows; ++y) {
      for (int x = 0; x < mask.cols; ++x) {
        if (labels.at<int>(y, x) != i) {continue;}
        const float wx = xs.at<float>(y, x);
        const float wy = ys.at<float>(y, x);
        const float wz = zs.at<float>(y, x);
        if (!std::isfinite(wx) || !std::isfinite(wy) || !std::isfinite(wz)) {continue;}
        if (wz < z_cut) {continue;}
        pts.emplace_back(wx, wy);
        ++kept_px;
      }
    }
    if (pts.size() < static_cast<size_t>(min_area)) {
      pts.clear();
      for (int y = 0; y < mask.rows; ++y) {
        for (int x = 0; x < mask.cols; ++x) {
          if (labels.at<int>(y, x) != i) {continue;}
          const float wx = xs.at<float>(y, x);
          const float wy = ys.at<float>(y, x);
          const float wz = zs.at<float>(y, x);
          if (!std::isfinite(wx) || !std::isfinite(wy) || !std::isfinite(wz)) {continue;}
          pts.emplace_back(wx, wy);
        }
      }
      kept_px = static_cast<int>(pts.size());
    }
    if (pts.size() < static_cast<size_t>(min_area)) {continue;}
    const cv::RotatedRect rr = cv::minAreaRect(pts);
    Obb o;
    o.cx = rr.center.x;
    o.cy = rr.center.y;
    o.sx = rr.size.width;
    o.sy = rr.size.height;
    o.yaw = rr.angle * static_cast<double>(CV_PI) / 180.0;
    if (o.sy > o.sx) {
      std::swap(o.sx, o.sy);
      o.yaw += CV_PI / 2.0;
    }
    o.yaw = std::atan2(std::sin(o.yaw), std::cos(o.yaw));
    o.z_min = std::isfinite(zlo) ? std::max(0.0, zlo) : 0.0;
    o.z_max = std::isfinite(zhi) ? std::max(o.z_min, zhi) : 0.0;
    o.area_px = kept_px;
    out.push_back(o);
  }
  return out;
}
}  // namespace

// 判据：点池版与逐域扫描版**逐字段相同**（含中心/尺寸/yaw/面积/z 包络）。
TEST(NadirGeometry, PointPoolMatchesPerComponentScan)
{
  const int W = 260, H = 200;
  cv::Mat mask(H, W, CV_8UC1, cv::Scalar(0));
  cv::Mat xs(H, W, CV_32FC1, cv::Scalar(NAN));
  cv::Mat ys(H, W, CV_32FC1, cv::Scalar(NAN));
  cv::Mat zs(H, W, CV_32FC1, cv::Scalar(NAN));
  // 三个连通域：一个纯屋顶、一个带侧墙、一个纯立面（触发"退回全部点"兜底）
  struct Rect {int x0, y0, w, h; bool wall;};
  const Rect rects[] = {
    {10, 10, 60, 40, false},
    {100, 10, 70, 50, true},
    {10, 100, 40, 60, true},
  };
  for (const auto & r : rects) {
    for (int y = r.y0; y < r.y0 + r.h; ++y) {
      for (int x = r.x0; x < r.x0 + r.w; ++x) {
        mask.at<uint8_t>(y, x) = 255;
        xs.at<float>(y, x) = 10.0f + 0.02f * x;
        ys.at<float>(y, x) = 20.0f + 0.02f * y;
        // wall=true 时整片都是低 z（纯立面）；否则左三列当侧墙
        zs.at<float>(y, x) = (r.wall || (x - r.x0) < 3) ? 1.0f : 3.0f;
      }
    }
  }
  const int min_area = 20;
  const auto ref = referenceAggregateObbs(mask, xs, ys, zs, min_area);
  const auto got = aggregateObbs(mask, xs, ys, zs, min_area);
  ASSERT_EQ(got.size(), ref.size()) << "连通域数量口径必须一致";
  for (size_t i = 0; i < ref.size(); ++i) {
    EXPECT_DOUBLE_EQ(got[i].cx, ref[i].cx) << "i=" << i;
    EXPECT_DOUBLE_EQ(got[i].cy, ref[i].cy) << "i=" << i;
    EXPECT_DOUBLE_EQ(got[i].sx, ref[i].sx) << "i=" << i;
    EXPECT_DOUBLE_EQ(got[i].sy, ref[i].sy) << "i=" << i;
    EXPECT_DOUBLE_EQ(got[i].yaw, ref[i].yaw) << "i=" << i;
    EXPECT_EQ(got[i].area_px, ref[i].area_px) << "i=" << i;
    EXPECT_DOUBLE_EQ(got[i].z_min, ref[i].z_min) << "i=" << i;
    EXPECT_DOUBLE_EQ(got[i].z_max, ref[i].z_max) << "i=" << i;
  }
}

// 判据：低于 min_area 的连通域**不占点池内存**，但也不影响达标域的聚合结果。
// 这条守的是"提速不得放宽门限"：细杆/噪点仍必须被拒。
TEST(NadirGeometry, PointPoolSkipsSubThresholdComponents)
{
  const int W = 200, H = 100;
  cv::Mat mask(H, W, CV_8UC1, cv::Scalar(0));
  cv::Mat xs(H, W, CV_32FC1, cv::Scalar(NAN));
  cv::Mat ys(H, W, CV_32FC1, cv::Scalar(NAN));
  cv::Mat zs(H, W, CV_32FC1, cv::Scalar(NAN));
  auto paint = [&](int x0, int y0, int w, int h) {
      for (int y = y0; y < y0 + h; ++y) {
        for (int x = x0; x < x0 + w; ++x) {
          mask.at<uint8_t>(y, x) = 255;
          xs.at<float>(y, x) = 1.0f * x;
          ys.at<float>(y, x) = 1.0f * y;
          zs.at<float>(y, x) = 3.0f;
        }
      }
    };
  paint(10, 10, 20, 20);    // 400 px：达标
  paint(100, 10, 3, 3);     // 9 px：低于门限（细杆）
  paint(150, 60, 2, 2);     // 4 px：低于门限（噪点）

  const int min_area = 20;
  const auto cp = agc_perception::collectComponentPoints(mask, xs, ys, zs, min_area);
  // 点池只收达标域：raw_pixels 必须等于 400，而不是 400+9+4
  EXPECT_EQ(cp.raw_pixels, 400L)
    << "低于门限的连通域不得进入点池（raw_pixels=" << cp.raw_pixels << "）";
  const auto obbs = agc_perception::aggregateObbs(cp, min_area);
  ASSERT_EQ(obbs.size(), 1u) << "细杆与噪点不得产出 OBB";
  // 画的是 u∈[10,29] 共 20 列，world x = u ⇒ 跨度是 29-10 = 19（不是 20）。
  // 断言 19 是**故意的**：它同时钉住"像素索引 → 世界坐标"的换算没被改动。
  EXPECT_NEAR(obbs[0].sx, 19.0, 0.5);
}

// 判据：点池的段边界自洽 —— 每段点数之和 == raw_pixels，且每段容量不越界。
// 越界写会静默破坏**相邻**连通域的数据，症状极难归因，所以显式断言。
TEST(NadirGeometry, PointPoolSegmentsAreConsistent)
{
  const int W = 300, H = 300;
  cv::Mat mask(H, W, CV_8UC1, cv::Scalar(0));
  cv::Mat xs(H, W, CV_32FC1, cv::Scalar(NAN));
  cv::Mat ys(H, W, CV_32FC1, cv::Scalar(NAN));
  cv::Mat zs(H, W, CV_32FC1, cv::Scalar(NAN));
  // 20 个互不相连的方块（含大小悬殊的，检验段容量分配）
  for (int k = 0; k < 20; ++k) {
    const int side = 4 + (k * 7) % 20;
    const int x0 = (k % 5) * 58 + 5;
    const int y0 = (k / 5) * 58 + 5;
    for (int y = y0; y < y0 + side; ++y) {
      for (int x = x0; x < x0 + side; ++x) {
        mask.at<uint8_t>(y, x) = 255;
        xs.at<float>(y, x) = 1.0f * x;
        ys.at<float>(y, x) = 1.0f * y;
        zs.at<float>(y, x) = 3.0f;
      }
    }
  }
  const int min_area = 1;
  const auto cp = agc_perception::collectComponentPoints(mask, xs, ys, zs, min_area);
  ASSERT_GT(cp.labels_n, 20) << "应有 20 个前景连通域 + 1 个背景";
  long sum = 0;
  for (int i = 0; i < cp.labels_n; ++i) {
    const size_t li = static_cast<size_t>(i);
    ASSERT_LE(cp.begin[li] + cp.count[li], cp.points.size())
      << "段 i=" << i << " 越出点池末尾（begin=" << cp.begin[li]
      << " count=" << cp.count[li] << " size=" << cp.points.size() << "）";
    sum += static_cast<long>(cp.count[li]);
  }
  EXPECT_EQ(sum, cp.raw_pixels) << "各段点数之和必须等于 raw_pixels";
  EXPECT_EQ(cp.points.size(), static_cast<size_t>(cp.raw_pixels))
    << "点池容量应恰好等于达标像素总数（不浪费、不缺）";
}

// 判据：连通域个数增加时，点池成本**不膨胀**（守 O(N²) 而非 O(C·N²)）。
// 用点池容量做断言（它正比于参与聚合的像素总数，与 C 无关）；不测墙钟时间 ——
// 单测环境里计时不可靠，会变成 flaky 测试。
//
// **构造要点**：两组必须"像素总数相同、切分份数不同"。所以用整数边长配对，
// 让 side² × count 严格相等（20²×20 = 10²×80 = 8000），且间距 > 边长以保证不粘连
// —— 否则相邻方块会合并成一个连通域，切分份数就白改了（第一版就是这么写错的）。
TEST(NadirGeometry, PointPoolCostIndependentOfComponentCount)
{
  const int W = 500, H = 500;
  auto build = [&](int side, int n_comp, int pitch) {
      cv::Mat mask(H, W, CV_8UC1, cv::Scalar(0));
      cv::Mat xs(H, W, CV_32FC1, cv::Scalar(NAN));
      cv::Mat ys(H, W, CV_32FC1, cv::Scalar(NAN));
      cv::Mat zs(H, W, CV_32FC1, cv::Scalar(NAN));
      const int per_row = W / pitch;
      for (int k = 0; k < n_comp; ++k) {
        const int x0 = (k % per_row) * pitch + 1;
        const int y0 = (k / per_row) * pitch + 1;
        for (int y = y0; y < std::min(H, y0 + side); ++y) {
          for (int x = x0; x < std::min(W, x0 + side); ++x) {
            mask.at<uint8_t>(y, x) = 255;
            xs.at<float>(y, x) = 1.0f * x;
            ys.at<float>(y, x) = 1.0f * y;
            zs.at<float>(y, x) = 3.0f;
          }
        }
      }
      return agc_perception::collectComponentPoints(mask, xs, ys, zs, 1);
    };
  // 两组像素总数都是 8000：20 个 20×20 vs 80 个 10×10（间距均 > 边长，不粘连）
  const auto few = build(20, 20, 25);
  const auto many = build(10, 80, 15);
  ASSERT_GT(many.labels_n, few.labels_n) << "对照组必须真的切得更碎";
  EXPECT_EQ(few.raw_pixels, 8000L) << "构造前提：像素总数固定";
  EXPECT_EQ(many.raw_pixels, 8000L) << "构造前提：像素总数固定";
  // 点池容量只取决于**像素总数**，与连通域个数无关（这正是修复的核心）
  EXPECT_EQ(many.points.size(), few.points.size())
    << "点池容量不应随连通域个数变化（few=" << few.points.size()
    << " many=" << many.points.size() << "）";
}

// ---------------------------------------------------------------------------------
// 地面画幅与遮挡阴影（2026-11-09 用户裁定 Q7/Q13/Q14/Q16/Q17）
// ---------------------------------------------------------------------------------
//
// 这一组守两件事：
//   1. **画幅从内参推导**（不写死 hfov）：换分辨率/换相机时边界自动跟随；
//   2. **阴影远边精确算**（不一刀切）：矮障碍后面立刻安全、高楼后面精确留阴影。
// 第 2 条是用户当场否掉我第一版"射线被障碍截断"的地方 —— 一刀切会让
// "能确定安全的"也留成未知，大幅限制规划。

TEST(FootprintGeometry, FootprintDerivesFromIntrinsicsNotHardcodedFov)
{
  using agc_perception::footprintFromCamera;
  // 1152²、fx=fy=268.6、H=14.242 ⇒ 半宽 = 14.242*576/268.6 = 30.54 m
  const auto fp = footprintFromCamera(14.242, 268.6, 268.6, 1152, 1152);
  ASSERT_TRUE(fp.valid);
  EXPECT_NEAR(fp.half_x, 30.54, 0.05);
  EXPECT_NEAR(fp.half_y, 30.54, 0.05);
  EXPECT_TRUE(fp.isSquare()) << "1152² + fx=fy ⇒ 地面覆盖必须是正方形";
  // 换算回去：半宽/H = 576/268.6 ≈ tan(65°)
  // **容差取 1e-4 而非 1e-6**：SDF 里的 `268.6` 是四舍五入值，精确值是
  // `576/tan(65°) = 268.5932`。差 6.8e-3 px ⇒ 半角差 0.0006°、相对 2.5e-5。
  // 这正说明"从内参推导"比"写死 130°"诚实：它报的是相机**实际**报的数，
  // 而不是我们希望它等于的那个数。
  EXPECT_NEAR(fp.half_x / 14.242, std::tan(65.0 * M_PI / 180.0), 1e-4);
}

TEST(FootprintGeometry, FootprintScalesLinearlyWithAltitude)
{
  using agc_perception::footprintFromCamera;
  const auto lo = footprintFromCamera(7.121, 268.6, 268.6, 1152, 1152);
  const auto hi = footprintFromCamera(14.242, 268.6, 268.6, 1152, 1152);
  ASSERT_TRUE(lo.valid);
  ASSERT_TRUE(hi.valid);
  EXPECT_NEAR(hi.half_x / lo.half_x, 2.0, 1e-9)
    << "高度翻倍 ⇒ 画幅翻倍（GSD = H/f 是线性的）";
}

TEST(FootprintGeometry, NonSquareSensorYieldsRectangularFootprint)
{
  using agc_perception::footprintFromCamera;
  // 640×480：4:3 ⇒ 画幅是矩形，不是正方形（旧口径的坑）。
  //
  // **比例是 480/640 = 0.75，不是 640/480**：实测轴映射把图像 u（宽）映到 world
  // **y**、v（高）映到 world **x**（`opticalRayToBody` 的 u↔v 互换，见 GUI 靶点标定）。
  // 改造前的画幅公式直接拿 `width` 当 x 方向半宽，等于**没有套这个轴映射** ——
  // 1152² 时看不出来（宽高相同），换成 4:3 就会把画幅算成转置的。
  const auto fp = footprintFromCamera(14.242, 268.6, 268.6, 640, 480);
  ASSERT_TRUE(fp.valid);
  EXPECT_FALSE(fp.isSquare());
  EXPECT_NEAR(fp.half_x / fp.half_y, 480.0 / 640.0, 1e-9);
}

TEST(FootprintGeometry, DegenerateInputYieldsInvalidNotGuess)
{
  using agc_perception::footprintFromCamera;
  EXPECT_FALSE(footprintFromCamera(0.0, 268.6, 268.6, 1152, 1152).valid)
    << "高度 0 必须 invalid（不猜边界）";
  EXPECT_FALSE(footprintFromCamera(-1.0, 268.6, 268.6, 1152, 1152).valid);
  EXPECT_FALSE(footprintFromCamera(14.0, 0.0, 268.6, 1152, 1152).valid);
  EXPECT_FALSE(footprintFromCamera(14.0, 268.6, 268.6, 0, 1152).valid);
  EXPECT_FALSE(footprintFromCamera(std::nan(""), 268.6, 268.6, 1152, 1152).valid);
}

TEST(FootprintGeometry, EdgeDistanceHitsSquareBoundary)
{
  using agc_perception::footprintFromCamera;
  using agc_perception::footprintEdgeDistance;
  const auto fp = footprintFromCamera(14.242, 268.6, 268.6, 1152, 1152);
  ASSERT_TRUE(fp.valid);
  // 沿 +x：距离 = half_x
  EXPECT_NEAR(footprintEdgeDistance(fp, 1.0, 0.0), fp.half_x, 1e-9);
  // 沿 +y：距离 = half_y
  EXPECT_NEAR(footprintEdgeDistance(fp, 0.0, 1.0), fp.half_y, 1e-9);
  // 沿 45°：正方形时 = half_x * sqrt(2)（到角点）
  EXPECT_NEAR(footprintEdgeDistance(fp, 1.0, 1.0), fp.half_x * std::sqrt(2.0), 1e-9);
  // 退化方向 → 0
  EXPECT_DOUBLE_EQ(footprintEdgeDistance(fp, 0.0, 0.0), 0.0);
}

TEST(FootprintGeometry, ShadowFarEdgeGrowsWithObstacleHeight)
{
  using agc_perception::shadowFarEdge;
  const double H = 14.242, d = 15.0;
  // 矮障碍：阴影几乎为零 ⇒ 后面立刻可见
  const double curb = shadowFarEdge(H, 0.2, d);
  EXPECT_NEAR(curb, d * H / (H - 0.2), 1e-9);
  EXPECT_LT(curb - d, 0.3) << "0.2 m 路缘的阴影必须小于 0.3 m";
  // 高楼：阴影远超画幅边界
  const double tall = shadowFarEdge(H, 10.55, d);
  EXPECT_NEAR(tall, d * H / (H - 10.55), 1e-9);
  EXPECT_GT(tall, 30.5) << "10.55 m 楼在 15 m 处的阴影必须超出 30.5 m 画幅";
  // 单调：越高阴影越远
  EXPECT_LT(shadowFarEdge(H, 0.5, d), shadowFarEdge(H, 5.0, d));
  EXPECT_LT(shadowFarEdge(H, 5.0, d), shadowFarEdge(H, 10.0, d));
}

TEST(FootprintGeometry, ShadowFarEdgeBoundaryCases)
{
  using agc_perception::shadowFarEdge;
  const double H = 14.242;
  // 贴地障碍 ⇒ 无阴影（返回 d_o 本身）
  EXPECT_DOUBLE_EQ(shadowFarEdge(H, 0.0, 10.0), 10.0);
  EXPECT_DOUBLE_EQ(shadowFarEdge(H, -1.0, 10.0), 10.0) << "负高度按 0 处理";
  // 障碍与相机同高 ⇒ 阴影无限远（后面全看不见）
  EXPECT_TRUE(std::isinf(shadowFarEdge(H, H, 10.0)));
  EXPECT_TRUE(std::isinf(shadowFarEdge(H, H + 1.0, 10.0))) << "更高的障碍同样遮蔽到底";
  // 距离非法 ⇒ 0
  EXPECT_DOUBLE_EQ(shadowFarEdge(H, 5.0, 0.0), 0.0);
  EXPECT_DOUBLE_EQ(shadowFarEdge(H, 5.0, -1.0), 0.0);
}

// 判据（用户裁定的核心）：**不能一刀切**。
// 同一个 15 m 处的障碍，矮的后面必须标安全、高的后面必须留阴影。
TEST(FootprintGeometry, LowObstacleLeavesRoomBeyondShadowButTallOneDoesNot)
{
  using agc_perception::shadowFarEdge;
  const double H = 14.242, d = 15.0, edge = 30.5;
  // 矮台 0.5 m：阴影远边 ~15.5 m，之后到 30.5 m 有 ~15 m 可见区应标安全
  const double low_far = shadowFarEdge(H, 0.5, d);
  EXPECT_LT(low_far, edge) << "矮障碍后面必须有可见区（否则就是一刀切）";
  EXPECT_GT(edge - low_far, 10.0) << "矮障碍后面应救回 10 m 以上的可见区";
  // 高楼 10.55 m：阴影远边 ~57.9 m，已超出画幅 ⇒ 后面无可见区
  const double tall_far = shadowFarEdge(H, 10.55, d);
  EXPECT_GT(tall_far, edge) << "高楼后面不应有可见区";
}

// 判据（2026-11-09 实测 bug 的防复活闸门）：**足迹点必须与 OBB 共用同一份屋顶带掩码**。
//
// 改造前：`aggregateObbs` 内部过滤侧墙（只影响 OBB），而 `publishFootprints`
// 发的是点池里的**全部点** ⇒ 侧墙点被逐点栅格化。侧墙点投影到地面外扩 `H/(H−h)`
// （9 m 高的楼 2.74×、10.55 m 的 3.86×），实测误覆盖散布到离障碍 1–24 格。
TEST(NadirGeometry, PointPoolKeptMaskExcludesSideWall)
{
  const int W = 200, H = 200;
  cv::Mat mask(H, W, CV_8UC1, cv::Scalar(0));
  cv::Mat xs(H, W, CV_32FC1, cv::Scalar(NAN));
  cv::Mat ys(H, W, CV_32FC1, cv::Scalar(NAN));
  cv::Mat zs(H, W, CV_32FC1, cv::Scalar(NAN));
  // 一个 80×80 的连通域：右侧 20 列是"侧墙"（z 从 1 线性升到 3），其余是屋顶（z=3）
  for (int y = 40; y < 120; ++y) {
    for (int x = 40; x < 120; ++x) {
      mask.at<uint8_t>(y, x) = 255;
      xs.at<float>(y, x) = 10.0f + 0.05f * x;
      ys.at<float>(y, x) = 20.0f + 0.05f * y;
      const float z = (x >= 100) ? (1.0f + 0.1f * (x - 100)) : 3.0f;
      zs.at<float>(y, x) = z;
    }
  }
  const int min_area = 20;
  const auto cp = agc_perception::collectComponentPoints(mask, xs, ys, zs, min_area);
  ASSERT_GT(cp.points.size(), 0u);
  ASSERT_EQ(cp.kept.size(), cp.points.size()) << "kept 掩码必须与点池等长";

  // 低 z（侧墙底部）的点必须被剔除
  long kept_low = 0, kept_high = 0, total_low = 0, total_high = 0;
  for (size_t k = 0; k < cp.points.size(); ++k) {
    const bool low = cp.points[k].z < 2.5f;
    if (low) {
      ++total_low;
      if (cp.isKept(k)) {++kept_low;}
    } else {
      ++total_high;
      if (cp.isKept(k)) {++kept_high;}
    }
  }
  EXPECT_GT(total_low, 0) << "构造里必须有侧墙点";
  EXPECT_GT(total_high, 0) << "构造里必须有屋顶点";
  EXPECT_LT(kept_low, total_low / 2) << (
    "侧墙点必须大部分被剔除（实测不剔除会让误覆盖散布到离障碍 1–24 格）");
  // **不要断言"屋顶点全部保留"**：我的构造里侧墙顶那一列 z 恰好也是 3.0
  // （与屋顶同 z），它被保留是**正确的** —— 墙顶与屋顶在交界处 z 相同，
  // 没有纯 z 判据能分开，这是已登记的方法边界（见 ADR-0035 的 (d) 节）。
  // 第一版断言 `kept_high == total_high` 就是这么写错的。
  EXPECT_GT(kept_high, total_high * 9 / 10) << "屋顶点必须基本全部保留";
  EXPECT_LT(cp.kept_pixels, cp.raw_pixels) << "过滤必须真的减少了点数";
}

// 判据：`kept_pixels` 必须等于掩码里 1 的个数（诊断数字不能自相矛盾）。
TEST(NadirGeometry, PointPoolKeptPixelsMatchesMask)
{
  const int W = 120, H = 120;
  cv::Mat mask(H, W, CV_8UC1, cv::Scalar(0));
  cv::Mat xs(H, W, CV_32FC1, cv::Scalar(NAN));
  cv::Mat ys(H, W, CV_32FC1, cv::Scalar(NAN));
  cv::Mat zs(H, W, CV_32FC1, cv::Scalar(NAN));
  for (int k = 0; k < 3; ++k) {
    const int x0 = 10 + k * 35, y0 = 20 + k * 10;
    for (int y = y0; y < y0 + 25; ++y) {
      for (int x = x0; x < x0 + 25; ++x) {
        mask.at<uint8_t>(y, x) = 255;
        xs.at<float>(y, x) = 1.0f * x;
        ys.at<float>(y, x) = 1.0f * y;
        // 前两列是矮侧墙
        zs.at<float>(y, x) = (x - x0 < 2) ? 0.5f : 5.0f;
      }
    }
  }
  const auto cp = agc_perception::collectComponentPoints(mask, xs, ys, zs, 10);
  long n = 0;
  for (size_t k = 0; k < cp.kept.size(); ++k) {
    if (cp.isKept(k)) {++n;}
  }
  EXPECT_EQ(cp.kept_pixels, n) << "kept_pixels 必须等于掩码里 1 的个数";
}

// 判据（2026-11-09 实测 bug 的防复活闸门）：**carve 途经障碍格时不得打 miss**。
//
// 不加这个，宽障碍会被自己的 carve 擦掉：14.5 m 宽的楼在 15 m 处占 51.6°
// （512 箱里 73 个），而每箱只射一条到**最近点**，楼宽方向上的其余格会被射线
// 穿过 ⇒ 实测 **69.6% 的可见真值障碍被标成 free**，覆盖率因此只有 0.29。
TEST(LogOddsCarve, ObstacleCellsAreNotErasedByTheirOwnRay)
{
  agc_perception::LogOddsGrid g;
  agc_perception::LogOddsParams p;
  g.reset(100, 100, p);

  // 构造一堵"墙"：x=50 那一列全部是障碍，先打满 hit
  const int W = 100;
  std::vector<char> obstacle(static_cast<size_t>(W * 100), 0);
  for (int y = 30; y < 70; ++y) {
    // **2026-11-09**：每格每帧一次 ⇒ 打满必须跨帧。
    // **ADR-0039 补正**：确认门按**地图帧**计数，两个时钟必须一起推进，
    // 否则 `map_frame_hits_` 恒为 1，墙永远到不了 occupied（本用例的前提失效）。
    for (int f = 1; f <= 8; ++f) {
      g.beginFrame(f);
      g.beginMapFrame(f);
      g.observeHit(static_cast<size_t>(y) * W + 50);
    }
    obstacle[static_cast<size_t>(y) * W + 50] = 1;
  }
  auto before = g.snapshot();
  int occ_before = 0;
  for (int y = 30; y < 70; ++y) {
    if (before[static_cast<size_t>(y) * W + 50] == 100) {++occ_before;}
  }
  ASSERT_EQ(occ_before, 40) << "构造前提：墙必须已被打满为 occupied";

  // 从 (5,50) 向墙上的 (50,50) 射线，**带障碍掩码**
  for (int rep = 0; rep < 10; ++rep) {
    g.beginFrame(g.currentFrame() + 1);
    g.carveRay(5, 50, 50, 50, false, 0.0, &obstacle);
  }
  auto after = g.snapshot();
  int occ_after = 0;
  for (int y = 30; y < 70; ++y) {
    if (after[static_cast<size_t>(y) * W + 50] == 100) {++occ_after;}
  }
  EXPECT_EQ(occ_after, 40) << (
    "墙上的格不得被穿过它的射线擦掉（实测不修会让 69.6% 的可见障碍变 free）");

  // 反例对照：**不带**掩码时，被射线**斜穿**的障碍格会被打 miss。
  // 注意射线终点那一格本来就不打 miss（Bresenham 到终点即停），所以必须让射线
  // **斜着穿过**墙体才能在"途经"位置命中障碍格 —— 第一版用水平射线打同一行，
  // 途经格全是空地，反例自然不成立。
  agc_perception::LogOddsGrid g2;
  g2.reset(100, 100, p);
  for (int y = 30; y < 70; ++y) {
    for (int f = 1; f <= 8; ++f) {
      g2.beginFrame(f);
      g2.beginMapFrame(f);   // 确认门按地图帧计数（ADR-0039 补正）
      g2.observeHit(static_cast<size_t>(y) * W + 50);
    }
  }
  auto before2 = g2.snapshot();
  int occ_before2 = 0;
  for (int y = 30; y < 70; ++y) {
    if (before2[static_cast<size_t>(y) * W + 50] == 100) {++occ_before2;}
  }
  ASSERT_EQ(occ_before2, 40);
  // 从 (5,20) 斜射到 (95,80)：这条线会**穿过** x=50 的墙体中段
  for (int rep = 0; rep < 10; ++rep) {
    g2.beginFrame(g2.currentFrame() + 1);
    g2.carveRay(5, 20, 95, 80, false, 0.0, nullptr);
  }
  auto a2 = g2.snapshot();
  int occ2 = 0;
  for (int y = 30; y < 70; ++y) {
    if (a2[static_cast<size_t>(y) * W + 50] == 100) {++occ2;}
  }
  // **2026-11-09 行为升级**：现在射线遇到**已判为 occupied** 的格就停
  // （不再依赖外部掩码）。所以这个反例的期望从"会被擦掉"反转为"也不会被擦掉"——
  // 这不是判据放松，而是修复更强了：连历史累积的障碍格也保护住了。
  EXPECT_EQ(occ2, 40) << (
    "射线遇到已判 occupied 的格必须停止；历史障碍不得被穿过它的射线擦掉"
    "（实测不修会让 65.6% 的可见真值障碍变 free）");
}

// 判据：射线必须**被障碍挡住**，不能穿过它去擦后面的格。
// 这是覆盖率的最大杀手 —— 实测覆盖率曲线在 3 s 达峰 0.29 后一路下滑（地图先建后毁）。
TEST(LogOddsCarve, RayStopsAtOccupiedCellAndDoesNotEraseBehind)
{
  agc_perception::LogOddsGrid g;
  agc_perception::LogOddsParams p;
  g.reset(100, 100, p);
  const int W = 100;

  // 墙在 x=50，墙后 x=60 放一个"目标格"（先打满 hit，模拟它曾被观测为障碍）。
  // **2026-11-09**：证据单位改为"每格每帧一次"，打满必须**跨帧**。
  for (int f = 1; f <= 8; ++f) {
    g.beginFrame(f);
    // **ADR-0039 补正**：确认门按**地图帧**计数，两个时钟必须一起推进。
    g.beginMapFrame(f);
    g.observeHit(static_cast<size_t>(50) * W + 50);   // 墙
    g.observeHit(static_cast<size_t>(50) * W + 60);   // 墙后的目标
  }
  auto before = g.snapshot();
  ASSERT_EQ(before[static_cast<size_t>(50) * W + 50], 100) << "墙必须是 occupied";
  ASSERT_EQ(before[static_cast<size_t>(50) * W + 60], 100) << "目标必须是 occupied";

  // 从 (5,50) 射向墙后 (95,50)：墙会挡住，射线不得穿过它去擦 (60,50)
  for (int rep = 0; rep < 10; ++rep) {
    g.beginFrame(g.currentFrame() + 1);   // 每帧一次（同帧重复 carve 是幂等的）
    g.carveRay(5, 50, 95, 50, false, 0.0, nullptr);
  }
  auto after = g.snapshot();
  EXPECT_EQ(after[static_cast<size_t>(50) * W + 50], 100) << "墙不得被擦";
  EXPECT_EQ(after[static_cast<size_t>(50) * W + 60], 100) << (
    "墙后的格不得被擦 —— 射线必须被墙挡住（实测不修会让地图先建后毁）");
}

// =================================================================================
// 2026-11-09：相机几何单一来源 + 时间同步 + 视野外不衰减
// =================================================================================
//
// 这一组守的是"**两个节点不得各算一套相机几何**"这条不变式。
// 改造前投影端按机体姿态反投影，地图端只取 x/y/z 并把画幅当成轴对齐矩形 ——
// 相机一转向，障碍点与 carve 射线就不在同一套几何里。

// 判据：相机世界原点必须包含**姿态旋转后的安装偏移**，不是简单的 z+0.242。
// 机体倾斜 30° 时，安装偏移在 world 的 x/y 分量不再为 0。
TEST(CameraGeometry, CameraOriginIncludesRotatedMountOffset)
{
  using agc_perception::cameraWorldOrigin;
  using agc_perception::CamPose;
  using agc_perception::Quat;

  CamPose level;
  level.body_pos = {1.0, 2.0, 10.0};
  const auto o0 = cameraWorldOrigin(level);
  EXPECT_NEAR(o0.x, 1.0, 1e-12);
  EXPECT_NEAR(o0.y, 2.0, 1e-12);
  EXPECT_NEAR(o0.z, 10.0 + agc_perception::kCamMountZ, 1e-12);

  // 绕 y 轴倾斜 30°：安装偏移 (0,0,h) 旋转后 x 分量 = h·sin30 = h/2
  const double a = 30.0 * M_PI / 180.0;
  CamPose tilted;
  tilted.body_pos = {1.0, 2.0, 10.0};
  tilted.body_q = Quat{0.0, std::sin(a / 2.0), 0.0, std::cos(a / 2.0)};
  const auto o1 = cameraWorldOrigin(tilted);
  EXPECT_NEAR(o1.x, 1.0 + agc_perception::kCamMountZ * std::sin(a), 1e-12)
    << "安装偏移必须经过姿态旋转；只加 z 会让倾斜时的相机位置算错";
  EXPECT_NEAR(o1.y, 2.0, 1e-12);
  EXPECT_NEAR(o1.z, 10.0 + agc_perception::kCamMountZ * std::cos(a), 1e-12);
}

// 判据：yaw 旋转后画幅必须跟着转 —— 不能仍是"轴对齐矩形"。
TEST(FootprintGeometry, FootprintRotatesWithCameraYaw)
{
  using agc_perception::footprintFromCamera;
  using agc_perception::CamIntrinsics;
  using agc_perception::CamPose;
  using agc_perception::Quat;

  CamIntrinsics k;
  k.fx = k.fy = 268.6;
  k.cx = k.cy = 320.0;
  CamPose p;
  p.body_pos = {0.0, 0.0, 14.0};

  const auto fp0 = footprintFromCamera(p, k, 640, 640);
  ASSERT_TRUE(fp0.valid);
  // 无 yaw：四角是**轴对齐**的（|x| = half_x、|y| = half_y）。
  // 具体象限由实测轴映射决定（图像左上角 → world +x/+y），这里不假设符号。
  for (int i = 0; i < 4; ++i) {
    EXPECT_NEAR(std::fabs(fp0.corners[i].x), fp0.half_x, 1e-9) << "i=" << i;
    EXPECT_NEAR(std::fabs(fp0.corners[i].y), fp0.half_y, 1e-9) << "i=" << i;
  }

  // yaw=90°：画幅转 90°，角点的 x/y 角色互换
  const double yaw = M_PI / 2.0;
  p.body_q = Quat{0.0, 0.0, std::sin(yaw / 2.0), std::cos(yaw / 2.0)};
  const auto fp90 = footprintFromCamera(p, k, 640, 640);
  ASSERT_TRUE(fp90.valid);
  // 形心仍应在光轴落点上（正下视 + yaw ⇒ 形心不动）
  EXPECT_NEAR(fp90.centroid.x, 0.0, 1e-9);
  EXPECT_NEAR(fp90.centroid.y, 0.0, 1e-9);
  // 转 90° 后，画幅的 x 半宽与 y 半宽互换（等价于把矩形转置）
  EXPECT_NEAR(fp90.half_x, fp0.half_y, 1e-9)
    << "yaw=90° 后 x 方向半宽必须等于原 y 方向半宽";
  EXPECT_NEAR(fp90.half_y, fp0.half_x, 1e-9);
  // 角点确实转了：原 corner[1]（+x,+y 象限）现在落在 (-y,+x) 象限
  EXPECT_NEAR(fp90.corners[1].x, -fp0.corners[1].y, 1e-9);
  EXPECT_NEAR(fp90.corners[1].y, fp0.corners[1].x, 1e-9);
}

// 判据：`footprintContains` 必须与射线边界一致（点在边界内 ⇔ 沿该方向边界距离 > 0）。
TEST(FootprintGeometry, ContainsMatchesEdgeDistance)
{
  using agc_perception::footprintContains;
  using agc_perception::footprintEdgeDistance;
  using agc_perception::footprintFromCamera;
  const auto fp = footprintFromCamera(14.242, 268.6, 268.6, 1152, 1152);
  ASSERT_TRUE(fp.valid);
  EXPECT_TRUE(footprintContains(fp, fp.centroid.x, fp.centroid.y))
    << "形心必须在画幅内";
  EXPECT_TRUE(footprintContains(fp, fp.centroid.x + 1.0, fp.centroid.y))
    << "形心附近必须在画幅内";
  EXPECT_FALSE(footprintContains(fp, fp.centroid.x + fp.half_x + 1.0, fp.centroid.y))
    << "画幅外必须判为外";
  // 沿 +x 的边界距离 = 到 x 方向边界
  EXPECT_NEAR(footprintEdgeDistance(fp, 1.0, 0.0), fp.half_x, 1e-9);
}

// 判据（用户裁定的 P0）：**位姿必须按时间戳插值**，不得用"最新一条"。
TEST(CameraGeometry, PoseInterpolatesBetweenSamples)
{
  using agc_perception::CamPose;
  using agc_perception::PoseSample;
  using agc_perception::poseAtTime;

  std::vector<PoseSample> s(2);
  s[0].stamp_s = 10.0;
  s[0].pose.body_pos = {0.0, 0.0, 14.0};
  s[1].stamp_s = 11.0;
  s[1].pose.body_pos = {10.0, 0.0, 14.0};

  CamPose out;
  double dt = -1.0;
  ASSERT_TRUE(poseAtTime(s, 10.5, 0.15, out, &dt));
  EXPECT_NEAR(out.body_pos.x, 5.0, 1e-9) << "半程必须插值到中点（不是取最新/最早）";
  EXPECT_NEAR(dt, 0.0, 1e-12) << "插值到位后残余错位为 0";

  // 超时：晚于最新样本 1 s，容差 0.15 s ⇒ 必须失败（调用方丢帧）
  EXPECT_FALSE(poseAtTime(s, 12.0, 0.15, out, &dt))
    << "超出容差必须失败，不得拿最近的位姿凑";
  // 边界：恰好落在样本上
  ASSERT_TRUE(poseAtTime(s, 11.0, 0.15, out, &dt));
  EXPECT_NEAR(out.body_pos.x, 10.0, 1e-9);
}

// 判据：位姿插值必须对姿态做**球面**插值（线性插值会让范数偏离 1）。
TEST(CameraGeometry, PoseInterpolatesOrientationOnUnitSphere)
{
  using agc_perception::CamPose;
  using agc_perception::PoseSample;
  using agc_perception::poseAtTime;
  using agc_perception::quatNorm;

  std::vector<PoseSample> s(2);
  s[0].stamp_s = 0.0;
  s[0].pose.body_q = {0.0, 0.0, 0.0, 1.0};
  s[1].stamp_s = 1.0;
  const double yaw = M_PI / 2.0;
  s[1].pose.body_q = {0.0, 0.0, std::sin(yaw / 2.0), std::cos(yaw / 2.0)};

  CamPose out;
  ASSERT_TRUE(poseAtTime(s, 0.5, 0.15, out));
  EXPECT_NEAR(quatNorm(out.body_q), 1.0, 1e-9)
    << "姿态插值必须保持单位范数（线性插值会让投影点缩放）";
  // 半程应转过 45°
  EXPECT_NEAR(out.body_q.z, std::sin(M_PI / 8.0), 1e-9);
}

// 判据：非法四元数必须被识别（投影公式默认单位四元数）。
TEST(CameraGeometry, QuatValidityChecks)
{
  using agc_perception::quatFinite;
  using agc_perception::quatUnit;
  EXPECT_TRUE(quatUnit(agc_perception::Quat{}));
  EXPECT_TRUE(quatUnit(agc_perception::Quat{0.0, 0.0, 0.7071067811865476, 0.7071067811865476}));
  EXPECT_FALSE(quatUnit(agc_perception::Quat{0.0, 0.0, 0.0, 0.5})) << "范数 0.5 必须非法";
  EXPECT_FALSE(quatUnit(agc_perception::Quat{0.0, 0.0, 0.0, 2.0})) << "范数 2 必须非法";
  EXPECT_FALSE(quatUnit(agc_perception::Quat{NAN, 0.0, 0.0, 1.0})) << "NaN 必须非法";
  EXPECT_FALSE(quatFinite(agc_perception::Quat{0.0, INFINITY, 0.0, 1.0}));
}

// 判据（用户裁定 P1）：**视野外的格不得参与每帧时间衰减**。
TEST(LogOdds, MaskedDecayLeavesOutsideCellsAlone)
{
  agc_perception::LogOddsGrid g;
  agc_perception::LogOddsParams p;
  g.reset(10, 1, p);
  for (int f = 1; f <= 6; ++f) {
    g.beginFrame(f);
    // **地图帧必须同步推进**（ADR-0039 补正）：`min_hits_for_occupied` 的计数单位
    // 是**地图帧**，只推感知帧会让 `map_frame_hits_` 停在 1，occupied 永远建不起来。
    // 本用例表达"每拍都发布"的简化情形，故两个时钟 1:1 推进。
    g.beginMapFrame(f);
    g.observeHit(1);
    g.observeHit(8);
  }
  const auto before = g.snapshot();
  ASSERT_EQ(before[1], 100);
  ASSERT_EQ(before[8], 100);
  const double p_before = g.probAt(8);

  // 只有格 1 在视野内
  std::vector<char> inside(10, 0);
  inside[1] = 1;
  for (int k = 0; k < 5; ++k) {
    g.beginFrame(g.currentFrame() + 1);
    g.decayMissMasked(&inside);
  }

  EXPECT_NEAR(g.probAt(8), p_before, 1e-12)
    << "视野外的格必须保持原状 —— 每帧衰减会让'没被看到'被当成'变空了'";
  EXPECT_LT(g.probAt(1), 0.99) << "视野内的格仍必须能衰减";
}

// 判据：`decayMiss()`（无掩码）必须与旧口径逐值等价（单测与对照依赖它）。
TEST(LogOdds, UnmaskedDecayEqualsLegacyBehaviour)
{
  agc_perception::LogOddsGrid a, b;
  agc_perception::LogOddsParams p;
  a.reset(6, 1, p);
  b.reset(6, 1, p);
  for (int f = 1; f <= 6; ++f) {
    a.beginFrame(f);
    b.beginFrame(f);
    a.observeHit(2);
    b.observeHit(2);
  }
  for (int k = 0; k < 4; ++k) {
    a.beginFrame(a.currentFrame() + 1);
    b.beginFrame(b.currentFrame() + 1);
    a.decayMiss();
    b.decayMissMasked(nullptr);
  }
  EXPECT_DOUBLE_EQ(a.probAt(2), b.probAt(2)) << "null 掩码必须等价于全图衰减";
}

// 判据（用户裁定 P2）：**碎片合并**必须把邻近且高度一致的碎片并入母体，
// 但**不得**把孤立噪声或高度不符的碎片拉进来。
TEST(NadirGeometry, FragmentMergeJoinsNearbyConsistentPieces)
{
  const int W = 200, H = 100;
  cv::Mat mask(H, W, CV_8UC1, cv::Scalar(0));
  cv::Mat xs(H, W, CV_32FC1, cv::Scalar(NAN));
  cv::Mat ys(H, W, CV_32FC1, cv::Scalar(NAN));
  cv::Mat zs(H, W, CV_32FC1, cv::Scalar(NAN));
  auto paint = [&](int x0, int y0, int w, int h, float z) {
      for (int y = y0; y < y0 + h; ++y) {
        for (int x = x0; x < x0 + w; ++x) {
          mask.at<uint8_t>(y, x) = 255;
          xs.at<float>(y, x) = 0.05f * x;
          ys.at<float>(y, x) = 0.05f * y;
          zs.at<float>(y, x) = z;
        }
      }
    };
  // 母体：10×10（100 px ≥ min_area=50），z=5
  paint(10, 10, 10, 10, 5.0f);
  // 邻近碎片：3×3（9 px < 50），距母体 ~1 m，同高度 ⇒ 应并入
  paint(34, 10, 3, 3, 5.0f);
  // 高度不符的碎片：紧邻母体，但 z=0.2（矮台）⇒ **不得**并入（否则会借用高楼高度）
  paint(24, 10, 3, 3, 0.2f);
  // 孤立噪声：远处、同高度 ⇒ 无母体可并 ⇒ 丢弃
  paint(150, 60, 3, 3, 5.0f);

  agc_perception::FragmentMergeParams merge;
  merge.max_gap_m = 1.5;
  merge.max_dz_m = 1.0;
  const auto cp = agc_perception::collectComponentPoints(mask, xs, ys, zs, 50, merge);
  // 只有母体那一段有内容；邻近碎片已并入（merged_components ≥ 1）
  EXPECT_GE(cp.merged_components, 1) << "邻近同高度的碎片必须被并入母体";
  EXPECT_EQ(cp.merged_components, 1) << (
    "高度不符的碎片（矮台）与远处孤立噪声都不得被并入");
  EXPECT_GT(cp.points.size(), 100u) << "并入后母体段必须包含碎片点";

  // 关闭合并（gap=0）⇒ 与旧口径一致：碎片与噪声都不进点池
  agc_perception::FragmentMergeParams off;
  off.max_gap_m = 0.0;
  const auto cp_off = agc_perception::collectComponentPoints(mask, xs, ys, zs, 50, off);
  EXPECT_EQ(cp_off.merged_components, 0);
  EXPECT_EQ(cp_off.points.size(), 100u) << "关闭合并后只应有母体的 100 个点";
}

// 判据（2026-11-09 修正的防复活闸门）：**可信测量半径必须由高度+内参派生**，
// 且必须**小于**倾斜画幅的包围盒 —— 否则 carve 会射到视场外去擦真值障碍。
//
// 实测踩过的坑：倾斜 2° 时画幅 bbox 半宽从 30.0 涨到 32.5 m、四角最远 46 m，
// 而真实可信半宽只有 30 m。carve 射到几何画幅边界 ⇒ 911 个真值障碍格被标 free，
// 其中 86% 从未进入过任何一帧画幅。
TEST(FootprintGeometry, TrustedRadiusIsDerivedNotHardcoded)
{
  using agc_perception::trustedRadius;
  const double r = trustedRadius(14.242, 268.6, 1152);
  // 正下视 GSD 恒等式：r = H·(N/2)/f = 14.242·576/268.6 = 30.54 m，再乘 0.95
  EXPECT_NEAR(r, 30.54 * 0.95, 0.05);
  // 随高度线性缩放（自主定高后判据自动跟随，不写死常数）
  const double r2 = trustedRadius(7.121, 268.6, 1152);
  EXPECT_NEAR(r / r2, 2.0, 1e-9) << "高度减半 ⇒ 可信半径减半";
  // 退化输入返回 0（调用方据此不设限或跳过），不返回负值
  EXPECT_DOUBLE_EQ(trustedRadius(0.0, 268.6, 1152), 0.0);
  EXPECT_DOUBLE_EQ(trustedRadius(-1.0, 268.6, 1152), 0.0);
  EXPECT_DOUBLE_EQ(trustedRadius(14.0, 0.0, 1152), 0.0);
  EXPECT_DOUBLE_EQ(trustedRadius(14.0, 268.6, 0), 0.0);
  EXPECT_DOUBLE_EQ(trustedRadius(std::nan(""), 268.6, 1152), 0.0);
}

// 判据：**倾斜时可信半径必须明显小于画幅包围盒** —— 这是本修正的存在理由。
// 若两者相等（或不加约束），说明"几何视场"又被当成了"可信测量范围"。
TEST(FootprintGeometry, TrustedRadiusIsSmallerThanTiltedFootprintBbox)
{
  using agc_perception::CamIntrinsics;
  using agc_perception::CamPose;
  using agc_perception::footprintFromCamera;
  using agc_perception::Quat;
  using agc_perception::trustedRadius;

  CamIntrinsics k;
  k.fx = k.fy = 268.6;
  k.cx = k.cy = 576.0;
  const double H = 14.0;
  CamPose p;
  p.body_pos = {0.0, 0.0, H};
  // pitch = 2°（实测悬停姿态量级）
  const double th = 2.0 * M_PI / 180.0;
  p.body_q = Quat{0.0, std::sin(th / 2.0), 0.0, std::cos(th / 2.0)};

  const auto fp = footprintFromCamera(p, k, 1152, 1152);
  ASSERT_TRUE(fp.valid);
  const double r = trustedRadius(H + agc_perception::kCamMountZ, k.fx, 1152);
  ASSERT_GT(r, 0.0);
  // 倾斜让 bbox 变大；可信半径不受姿态影响 ⇒ 必须更小
  EXPECT_LT(r, std::max(fp.half_x, fp.half_y))
    << "可信半径必须小于倾斜画幅包围盒（否则 carve 会射到视场外擦真值障碍）";
  // 正下视时两者应当接近（可信半径只差 edge_ratio 的余量）
  CamPose level;
  level.body_pos = {0.0, 0.0, H};
  const auto fp0 = footprintFromCamera(level, k, 1152, 1152);
  ASSERT_TRUE(fp0.valid);
  EXPECT_NEAR(fp0.half_x, r / 0.95, 0.1)
    << "正下视时画幅半宽应等于可信半径/edge_ratio（同一恒等式）";
}

// 判据（2026-11-09 修正的防复活闸门）：**大前倾/退化画幅必须被判为不可信**。
//
// 实测踩过的坑：过渡段无人机大幅前倾时画幅算出 123.9×188.2 m（俯仰约 18°），
// 甚至 0.0×0.0。此时若继续拿它圈定负证据/边缘区，射线会射到根本不存在的"边界"上。
TEST(FootprintGeometry, ImplausibleFootprintRejected)
{
  using agc_perception::CamIntrinsics;
  using agc_perception::CamPose;
  using agc_perception::footprintFromCamera;
  using agc_perception::footprintPlausible;
  using agc_perception::Quat;

  CamIntrinsics k;
  k.fx = k.fy = 268.6;
  k.cx = k.cy = 576.0;
  const double H = 14.0;
  const double cam_h = H + agc_perception::kCamMountZ;

  // 正下视：必须可信
  CamPose level;
  level.body_pos = {0.0, 0.0, H};
  const auto fp0 = footprintFromCamera(level, k, 1152, 1152);
  ASSERT_TRUE(fp0.valid);
  EXPECT_TRUE(footprintPlausible(fp0, cam_h, k.fx, 1152))
    << "正下视画幅必须判为可信";

  // 轻微倾斜（2°，实测悬停量级）：仍应可信
  const double t2 = 2.0 * M_PI / 180.0;
  CamPose tilt2;
  tilt2.body_pos = {0.0, 0.0, H};
  tilt2.body_q = Quat{0.0, std::sin(t2 / 2.0), 0.0, std::cos(t2 / 2.0)};
  const auto fp2 = footprintFromCamera(tilt2, k, 1152, 1152);
  ASSERT_TRUE(fp2.valid);
  EXPECT_TRUE(footprintPlausible(fp2, cam_h, k.fx, 1152))
    << "2° 悬停倾斜是正常的，不得判为不可信（否则正常帧全被丢）";

  // 大前倾（20°）：必须判为不可信
  const double t20 = 20.0 * M_PI / 180.0;
  CamPose tilt20;
  tilt20.body_pos = {0.0, 0.0, H};
  tilt20.body_q = Quat{0.0, std::sin(t20 / 2.0), 0.0, std::cos(t20 / 2.0)};
  const auto fp20 = footprintFromCamera(tilt20, k, 1152, 1152);
  ASSERT_TRUE(fp20.valid) << "构造前提：20° 时四角仍能投影到地面";
  EXPECT_FALSE(footprintPlausible(fp20, cam_h, k.fx, 1152))
    << "大前倾把画幅拉到数倍正下视口径时必须判为不可信"
       "（实测算出过 123.9x188.2 m，射线会射到不存在的边界）";

  // 退化输入：invalid 画幅一律不可信
  EXPECT_FALSE(footprintPlausible(
      agc_perception::GroundFootprint{}, cam_h, k.fx, 1152));
  EXPECT_FALSE(footprintPlausible(fp0, 0.0, k.fx, 1152)) << "高度 0 必须不可信";
  EXPECT_FALSE(footprintPlausible(fp0, cam_h, 0.0, 1152)) << "焦距 0 必须不可信";
}

// 判据：可信半径同时约束 **hit（正证据）** 与 carve（负证据）—— 同一道闸。
// 上一轮的缺陷就是只约束了 carve，导致 1502 个真值格被标 occupied 却从未进过画幅。
TEST(FootprintGeometry, TrustedRadiusBoundsBothHitAndCarve)
{
  using agc_perception::trustedRadius;
  const double cam_h = 14.242, fx = 268.6;
  const double r = trustedRadius(cam_h, fx, 1152);
  ASSERT_GT(r, 0.0);
  // 可信半径必须严格小于正下视画幅半宽（留 edge_ratio 余量）
  const double base_half = cam_h * 576.0 / fx;
  EXPECT_LT(r, base_half) << "可信半径必须小于画幅半宽（余量留给边缘弱证据）";
  EXPECT_GT(r, 0.9 * base_half) << "余量不应过大（否则丢掉可用视场）";
}

// =================================================================================
// ADR-0041：点级元数据（实例归属 + 类别）
// =================================================================================
//
// 判据核心：几何层不再是"一批没有来历的点"。每个点必须能回答"我属于哪个实例"
// 与"我是什么（屋顶/墙/边缘/遮挡）"。

// `aggregateObbs` 必须能给出每个 OBB 所属的**连通域 label**。
// 为什么重要：OBB 下标 ≠ label（有段被跳过），用下标猜会把实例 id 贴到错误的点上，
// 而且错得很安静（点还是那些点，只是归属错了）。
TEST(NadirGeometry, AggregateObbsExposesComponentLabels)
{
  const int W = 100, H = 100;
  cv::Mat mask(H, W, CV_8UC1, cv::Scalar(0));
  cv::Mat xs(H, W, CV_32FC1, cv::Scalar(NAN));
  cv::Mat ys(H, W, CV_32FC1, cv::Scalar(NAN));
  cv::Mat zs(H, W, CV_32FC1, cv::Scalar(NAN));
  // 两个不相连的方块
  for (int v = 10; v < 20; ++v) {
    for (int u = 10; u < 20; ++u) {
      mask.at<uint8_t>(v, u) = 255;
      xs.at<float>(v, u) = static_cast<float>(u * 0.05);
      ys.at<float>(v, u) = static_cast<float>(v * 0.05);
      zs.at<float>(v, u) = 0.0f;
    }
  }
  for (int v = 60; v < 70; ++v) {
    for (int u = 60; u < 70; ++u) {
      mask.at<uint8_t>(v, u) = 255;
      xs.at<float>(v, u) = static_cast<float>(u * 0.05);
      ys.at<float>(v, u) = static_cast<float>(v * 0.05);
      zs.at<float>(v, u) = 0.0f;
    }
  }
  agc_perception::FragmentMergeParams merge;   // 不合并
  const auto cp = agc_perception::collectComponentPoints(mask, xs, ys, zs, 4, merge);
  std::vector<int> labels;
  const auto obbs = agc_perception::aggregateObbs(cp, 4, &labels);
  ASSERT_EQ(obbs.size(), 2u);
  ASSERT_EQ(labels.size(), obbs.size()) << "labels 必须与 OBB 等长";
  // label 必须是**真实存在的连通域编号**（>0 且 < labels_n）
  for (int l : labels) {
    EXPECT_GT(l, 0);
    EXPECT_LT(l, cp.labels_n);
  }
  EXPECT_NE(labels[0], labels[1]) << "两个 OBB 不得共用一个 label";
}

// 点类别必须与 `kept` 用**同一个判据**（同一次 z_cut），不得互相矛盾：
//   * kept==1 且 class==roof  —— 屋顶带内，正常；
//   * kept==1 且 class==wall  —— 立面兜底（被保留但确实是墙）；
//   * kept==0 且 class==wall  —— 带外，正常；
//   * **kept==0 且 class==roof 不可能**（带内就一定被 kept）。
TEST(NadirGeometry, PointClassAgreesWithKeptMask)
{
  const int W = 60, H = 60;
  cv::Mat mask(H, W, CV_8UC1, cv::Scalar(0));
  cv::Mat xs(H, W, CV_32FC1, cv::Scalar(NAN));
  cv::Mat ys(H, W, CV_32FC1, cv::Scalar(NAN));
  cv::Mat zs(H, W, CV_32FC1, cv::Scalar(NAN));
  // 一个"楼"：左半 z=5（屋顶），右半 z=1（侧墙），高度差 4 m 远超屋顶带门限
  for (int v = 10; v < 40; ++v) {
    for (int u = 10; u < 40; ++u) {
      mask.at<uint8_t>(v, u) = 255;
      xs.at<float>(v, u) = static_cast<float>(u * 0.05);
      ys.at<float>(v, u) = static_cast<float>(v * 0.05);
      zs.at<float>(v, u) = (u < 25) ? 5.0f : 1.0f;
    }
  }
  agc_perception::FragmentMergeParams merge;
  auto cp = agc_perception::collectComponentPoints(mask, xs, ys, zs, 4, merge);
  ASSERT_EQ(cp.point_class.size(), cp.points.size())
    << "point_class 必须与 points 等长（同下标纪律）";

  int roof = 0, wall = 0, inconsistent = 0;
  for (size_t k = 0; k < cp.points.size(); ++k) {
    const uint8_t cls = cp.point_class[k];
    const bool kept = cp.isKept(k);
    if (cls == agc_perception::kPointRoof) {++roof;}
    if (cls == agc_perception::kPointWall) {++wall;}
    if (!kept && cls == agc_perception::kPointRoof) {++inconsistent;}
  }
  EXPECT_GT(roof, 0) << "高处的屋顶点必须被标为 roof";
  EXPECT_GT(wall, 0) << "低处的侧墙点必须被标为 wall";
  EXPECT_EQ(inconsistent, 0)
    << "kept==0 却被标成 roof 是不可能的（同一判据）";
}

// `point_label` 必须与 `points` 等长，且指向合法的连通域编号。
// 它是"点 → 实例"的唯一桥：长度错位会让实例 id 贴到错误的点上。
TEST(NadirGeometry, PointLabelParallelToPoints)
{
  const int W = 60, H = 60;
  cv::Mat mask(H, W, CV_8UC1, cv::Scalar(0));
  cv::Mat xs(H, W, CV_32FC1, cv::Scalar(NAN));
  cv::Mat ys(H, W, CV_32FC1, cv::Scalar(NAN));
  cv::Mat zs(H, W, CV_32FC1, cv::Scalar(NAN));
  for (int v = 10; v < 30; ++v) {
    for (int u = 10; u < 30; ++u) {
      mask.at<uint8_t>(v, u) = 255;
      xs.at<float>(v, u) = static_cast<float>(u * 0.05);
      ys.at<float>(v, u) = static_cast<float>(v * 0.05);
      zs.at<float>(v, u) = 0.0f;
    }
  }
  agc_perception::FragmentMergeParams merge;
  const auto cp = agc_perception::collectComponentPoints(mask, xs, ys, zs, 4, merge);
  ASSERT_EQ(cp.point_label.size(), cp.points.size());
  for (int l : cp.point_label) {
    EXPECT_GT(l, 0);
    EXPECT_LT(l, cp.labels_n);
  }
}
