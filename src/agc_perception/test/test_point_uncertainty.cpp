// point_uncertainty 的单测：**只测可判定的性质**，不测"数值对不对"。
//
// 为什么测性质而不测具体数字：模型里的 σ 参数是**声明值**（不是标定值），
// 断言"σ=0.037 m"等于把声明值固化成一个假精确的结论。可判定的是**单调性与
// 结构**：深度越大越糊、画幅越边缘越糊、正下视比掠射可信、协方差非负定。
// 这些性质错了，模型就是错的；它们对了，数值再调也只是参数标定问题。
#include <gtest/gtest.h>

#include <cmath>

#include "agc_perception/point_uncertainty.hpp"

using agc_perception::CamIntrinsics;
using agc_perception::CamPose;
using agc_perception::Cov2;
using agc_perception::PointUncertaintyParams;
using agc_perception::pointCovariance;
using agc_perception::framePoseSigma;
using agc_perception::viewCosine;

namespace
{

// 正下视相机：光轴沿 -Z（与 `nadir_cam_link` 的 pitch=+90° 同构）。
// 用单位四元数 + 机体不旋转来近似 —— 本文件测的是**协方差传播**，
// 不是轴映射（后者已由 test_nadir_geometry.cpp 的实测标定用例覆盖）。
CamPose levelPose(double z = 14.242)
{
  CamPose p;
  p.body_pos = {0.0, 0.0, z};
  p.body_q = {0.0, 0.0, 0.0, 1.0};
  return p;
}

CamIntrinsics cam() {return CamIntrinsics{268.6, 268.6, 576.0, 576.0};}

}  // namespace

// ---- 结构性性质 ----

TEST(PointUncertainty, DegenerateInputsYieldZeroNotCertainty)
{
  const auto k = cam();
  const auto pose = levelPose();
  const PointUncertaintyParams up;
  // 深度非有限 / 非正 ⇒ 全 0 协方差（"无信息"）。
  // **关键**：0 协方差在 sigmaMajor 下也是 0 —— 调用方必须区分"无信息"与"极准"，
  // 故这里同时断言"退化输入不会给出一个看起来很好的数"这一风险点由调用方承担。
  for (double d : {0.0, -1.0, std::nan(""), std::numeric_limits<double>::infinity()}) {
    const Cov2 c = pointCovariance(k, 576.0, 576.0, d, pose, up);
    EXPECT_DOUBLE_EQ(c.xx, 0.0);
    EXPECT_DOUBLE_EQ(c.xy, 0.0);
    EXPECT_DOUBLE_EQ(c.yy, 0.0);
  }
  // 内参非法同样退化
  CamIntrinsics bad{0.0, 0.0, 0.0, 0.0};
  const Cov2 c2 = pointCovariance(bad, 0.0, 0.0, 10.0, pose, up);
  EXPECT_DOUBLE_EQ(c2.xx, 0.0);
}

TEST(PointUncertainty, CovarianceIsSymmetricPositiveSemidefinite)
{
  const auto k = cam();
  const auto pose = levelPose();
  const PointUncertaintyParams up;
  for (double u : {0.0, 200.0, 576.0, 1000.0, 1151.0}) {
    for (double v : {0.0, 576.0, 1151.0}) {
      const Cov2 c = pointCovariance(k, u, v, 15.0, pose, up);
      // 对角非负
      EXPECT_GE(c.xx, 0.0);
      EXPECT_GE(c.yy, 0.0);
      // 非负定：xx·yy − xy² ≥ 0（2×2 对称矩阵的充要条件）
      EXPECT_GE(c.xx * c.yy - c.xy * c.xy, -1e-12);
      // 主方向 ≥ 次方向
      EXPECT_GE(c.sigmaMajor() + 1e-12, c.sigmaMinor());
      // 迹 = 特征值之和 ≥ 主方向方差
      EXPECT_GE(c.trace() + 1e-12, c.sigmaMajor() * c.sigmaMajor());
    }
  }
}

// ---- 单调性：每一项误差源都必须"更差的条件 ⇒ 更大的不确定度" ----

TEST(PointUncertainty, SigmaGrowsWithDepth)
{
  const auto k = cam();
  const auto pose = levelPose();
  const PointUncertaintyParams up;
  // 同一像素、不同深度：深度越大 ⇒ 像素落位误差 d·σ_px/f 越大，σ_d 也越大。
  double prev = 0.0;
  for (double d : {5.0, 10.0, 15.0, 20.0, 30.0}) {
    const double s = pointCovariance(k, 576.0, 576.0, d, pose, up).sigmaMajor();
    EXPECT_GT(s, prev) << "depth=" << d;
    prev = s;
  }
}

TEST(PointUncertainty, SigmaGrowsTowardImageEdge)
{
  const auto k = cam();
  const auto pose = levelPose();
  const PointUncertaintyParams up;
  // 同一深度、从主点走向画幅边缘：斜距/深度比变大 ⇒ 深度误差摊到地面更长。
  // 这正是 `trustedRadius` 要拦的那种点（画幅最外圈 GSD 恶化 1/cos²）。
  const double center = pointCovariance(k, 576.0, 576.0, 15.0, pose, up).sigmaMajor();
  const double mid = pointCovariance(k, 900.0, 576.0, 15.0, pose, up).sigmaMajor();
  const double edge = pointCovariance(k, 1151.0, 1151.0, 15.0, pose, up).sigmaMajor();
  EXPECT_LT(center, mid);
  EXPECT_LT(mid, edge);
}

TEST(PointUncertainty, ViewCosineIsOneAtCenterAndDropsAtEdge)
{
  const auto k = cam();
  const auto pose = levelPose();
  const double c_center = viewCosine(k, 576.0, 576.0, 15.0, pose);
  const double c_edge = viewCosine(k, 1151.0, 1151.0, 15.0, pose);
  EXPECT_NEAR(c_center, 1.0, 1e-9);          // 主点处射线垂直向下
  EXPECT_LT(c_edge, c_center);
  EXPECT_GT(c_edge, 0.0);
  // 深度无效 ⇒ 0（"无法判定"，不是"很好"）
  EXPECT_DOUBLE_EQ(viewCosine(k, 576.0, 576.0, 0.0, pose), 0.0);
}

TEST(PointUncertainty, ViewCosineMatchesPinholeGeometry)
{
  const auto k = cam();
  const auto pose = levelPose();
  // 解析值：射线 (Δu/fx, Δv/fy, 1)，与法向夹角余弦 = 1/|ray|
  const double du = (900.0 - k.cx) / k.fx;
  const double dv = (700.0 - k.cy) / k.fy;
  const double expected = 1.0 / std::sqrt(du * du + dv * dv + 1.0);
  EXPECT_NEAR(viewCosine(k, 900.0, 700.0, 12.0, pose), expected, 1e-12);
}

TEST(PointUncertainty, PoseSigmaDoesNotEnterPerPointCovariance)
{
  // **位姿误差是帧级相关误差，不得进逐点协方差**（ADR-0042 补正）。
  //
  // 为什么：它整帧同向，帧内点数再多也抵不掉，所以逐点门控拿它当判据
  // 会把画幅边缘的点**全部**拒掉 —— 实测 11 m 力臂 × 0.02 rad = 0.22 m，
  // 远超半格 0.125 m，结果整张地图一个 hit 都没有。
  //
  // 正确做法：它由 `framePoseSigma()` 单独给，按批次级使用。
  const auto k = cam();
  const auto pose = levelPose();
  PointUncertaintyParams a;
  a.sigma_pose_m = 0.0;
  a.sigma_yaw_rad = 0.0;
  PointUncertaintyParams b;
  b.sigma_pose_m = 5.0;        // 荒谬的大值，若渗进逐点协方差必然爆掉
  b.sigma_yaw_rad = 5.0;
  for (auto px : {std::pair<double, double>{576.0, 576.0}, {1151.0, 100.0}}) {
    const Cov2 ca = pointCovariance(k, px.first, px.second, 15.0, pose, a);
    const Cov2 cb = pointCovariance(k, px.first, px.second, 15.0, pose, b);
    EXPECT_DOUBLE_EQ(cb.xx, ca.xx) << '位姿误差不得进逐点协方差';
    EXPECT_DOUBLE_EQ(cb.xy, ca.xy);
    EXPECT_DOUBLE_EQ(cb.yy, ca.yy);
  }
}

TEST(PointUncertainty, FramePoseSigmaGrowsWithRange)
{
  // 帧级误差随力臂增长（偏航项），且在 0 距离处退化为位姿位置项。
  PointUncertaintyParams p;
  p.sigma_pose_m = 0.10;
  p.sigma_yaw_rad = 0.02;
  const double at0 = framePoseSigma(0.0, p);
  EXPECT_NEAR(at0, 0.10, 1e-12) << '零距离时只剩位姿位置项';
  const double at10 = framePoseSigma(10.0, p);
  const double at30 = framePoseSigma(30.0, p);
  EXPECT_GT(at10, at0);
  EXPECT_GT(at30, at10) << '力臂越大，偏航项越大';
  // 30 m 处偏航项 0.6 m 占主导
  EXPECT_NEAR(at30, std::hypot(0.10, 0.6), 1e-9);
}

TEST(PointUncertainty, ZeroParamsGiveZeroCovariance)
{
  // 所有 σ 置 0 ⇒ 协方差恒 0。这是"模型不凭空造不确定度"的判据：
  // 若某项实现漏乘了 σ（例如把 lever 当位移用），这里就会非 0。
  const auto k = cam();
  const auto pose = levelPose();
  PointUncertaintyParams z;
  z.sigma_pose_m = 0.0;
  z.sigma_yaw_rad = 0.0;
  z.sigma_depth_rel = 0.0;
  z.sigma_depth_abs_m = 0.0;
  z.sigma_pixel_px = 0.0;
  for (double u : {0.0, 576.0, 1151.0}) {
    const Cov2 c = pointCovariance(k, u, 576.0, 15.0, pose, z);
    EXPECT_DOUBLE_EQ(c.xx, 0.0);
    EXPECT_DOUBLE_EQ(c.xy, 0.0);
    EXPECT_DOUBLE_EQ(c.yy, 0.0);
  }
}

TEST(PointUncertainty, DepthSigmaAloneIsRankOne)
{
  // 只有深度误差时，协方差是秩 1 的（沿射线方向），
  // 因此 次方向 σ 必须为 0、主方向 σ 必须 > 0。
  // 这是"深度误差沿射线、不各向同性"这一模型假设的直接判据 ——
  // 若实现把它写成了各向同性，次方向会跟着变大，本用例立刻红。
  const auto k = cam();
  const auto pose = levelPose();
  PointUncertaintyParams d;
  d.sigma_pose_m = 0.0;
  d.sigma_yaw_rad = 0.0;
  d.sigma_depth_rel = 0.02;
  d.sigma_depth_abs_m = 0.0;
  d.sigma_pixel_px = 0.0;
  const Cov2 c = pointCovariance(k, 900.0, 400.0, 15.0, pose, d);
  EXPECT_GT(c.sigmaMajor(), 0.0);
  EXPECT_NEAR(c.sigmaMinor(), 0.0, 1e-9);
  // 行列式 = 0（秩 1 的直接判据）
  EXPECT_NEAR(c.xx * c.yy - c.xy * c.xy, 0.0, 1e-18);
}
