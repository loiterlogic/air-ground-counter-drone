// point_uncertainty —— 单点的**位置协方差**与**观测视角质量**（纯逻辑，不 include ROS）
//
// **为什么需要它**（temp.md 方向二）：几何层此前只知道"这个点在 (x,y)"，不知道
// "这个点有多准、从哪个方向看到的"。于是一个 14 m 高、画幅最外圈、深度差 3% 的点
// 与一个正下方、深度差 0.1% 的点，在地图里**权重完全相同** —— 都是"一个 hit"。
//
// **参照结论（决定了下面的模型怎么给）**：
//   * `refs/` 里没有任何实现存逐点协方差：ego-planner / Fast-Planner / RACER 的
//     `SDFMap` / `GridMap` 只有**格级**概率（`p_hit_` / `p_miss_` / `prob_hit_log_`）；
//     深度噪声在参照里甚至是**注释掉的**（`sdf_map.cpp` 的 `rand_noise_` 三行）。
//   * ⇒ 没有现成规则可抄，模型必须自己给、自己证（下面每条都配单调性单测）。
//
// **四项独立误差源，方差相加**（线性化传播，各自可单测）：
//   ① 位姿位置   σ_p        —— 世界系各向同性，直接加进 XY 方差
//   ② 位姿偏航   σ_ψ        —— 绕相机原点转，力臂 = 点到相机的水平距离
//   ③ 深度轴向   σ_d        —— 沿**射线方向**推，量级 = σ_d·(斜距/深度)
//   ④ 像素落位   σ_px       —— 沿相机 u/v 轴推，量级 = σ_px·d/f
//
// **为什么不用数值微分**：176k 点 × 6 次重投影 = 每帧上百万次投影。四项都有闭式
// 雅可比（每项是一个秩 1 的 XY 更新），解析算比差分快两个量级，且**精确**。
//
// **为什么存 2×2 而不是 1 个标量**：深度误差沿射线、像素误差垂直于光轴，两者方向
// 不同 ⇒ 协方差非各向同性。存标量等于谎称它是圆。

#ifndef AGC_PERCEPTION__POINT_UNCERTAINTY_HPP_
#define AGC_PERCEPTION__POINT_UNCERTAINTY_HPP_

#include <algorithm>
#include <cmath>

#include "agc_perception/camera_geometry.hpp"

namespace agc_perception
{

// 误差源参数。默认值是**声明值**（不是标定值），含义与 `confidence.hpp` 的
// "声明置信度"同一纪律：它表达"我们假设传感器有多准"，不表达"实测有多准"。
// 改这些值等于改整条链的权重口径，必须走 ADR。
//
// **两类误差必须分开处理（ADR-0042 补正）**：
//
// | 类 | 项 | 帧内是否一致 | 同格多点能否平均掉 | 后果 |
// |---|---|---|---|---|
// | **逐点随机** | 深度轴向、像素落位 | 否，逐点变 | **能** | 用**逐点**协方差表达 |
// | **帧级相关** | 位姿位置、位姿偏航 | **是**，整帧同向 | **不能** | 用**批次级**标量表达 |
//
// **为什么必须分开**：把偏航项塞进逐点门控会让画幅边缘的点全部被拒 ——
// 实测 11 m 力臂 × 0.02 rad = 0.22 m，远超半格 0.125 m，于是**每一格都被拒、
// 整张地图一个 hit 都没有**（实测 `σ拒格` 等于 `弱支持格` 全部候选）。
// 而偏航误差是整帧同向的，逐点门控本来就不该管它 ——
// 那与 ADR-0039 对时间错位的判断是同一条：相关性误差只能靠跨帧抵消，
// 靠"多点一致"是无效的（点都在一起偏）。
struct PointUncertaintyParams
{
  // ① 位姿位置标准差（m）。取 0.10：PX4 EKF 在 GPS 模式下的典型水平位置误差量级；
  // 本仓不做状态估计标定，故按公开典型值声明，并在文档中标注为**声明值**。
  double sigma_pose_m{0.10};
  // ② 位姿偏航标准差（rad）。取 0.02（≈1.15°）。
  double sigma_yaw_rad{0.02};
  // ③ 深度：相对项 + 绝对项，σ_d = hypot(rel·d, abs)。
  //    为什么要两项：结构光/双目在近处误差近似**常数**（绝对项主导），
  //    远处误差近似**正比于距离**（相对项主导）。只留一项会在另一端失真。
  //    rel 取 0.01（1%）、abs 取 0.02 m。
  double sigma_depth_rel{0.01};
  double sigma_depth_abs_m{0.02};
  // ④ 像素落位标准差（px）。取 0.5：分割边界 + 深度图重采样共同造成的半像素级抖动。
  double sigma_pixel_px{0.5};
};

// 2×2 对称协方差（XY 平面，单位 m²）。
struct Cov2
{
  double xx{0.0};
  double xy{0.0};
  double yy{0.0};

  // 迹 = 总方差（与坐标系旋转无关）。
  double trace() const {return xx + yy;}

  // **主方向 1σ**（m）：最大特征值的平方根，即"最坏方向上的不确定度半径"。
  //
  // **为什么门控用它而不是迹**：门控要回答"这个点最坏可能偏多远"。用迹会把
  // 一个"只在某一方向很糊"的点算成两个方向都糊，从而误拒掉方向性误差大的点
  // （正下视的深度误差正是这种：沿射线糊、垂直方向准）。
  double sigmaMajor() const
  {
    const double half = 0.5 * (xx + yy);
    const double diff = 0.5 * (xx - yy);
    const double rad = std::hypot(diff, xy);
    const double lam_max = half + rad;
    return lam_max > 0.0 ? std::sqrt(lam_max) : 0.0;
  }

  // 最小特征值 1σ（诊断用：与 sigmaMajor 相差越大，方向性越强）。
  double sigmaMinor() const
  {
    const double half = 0.5 * (xx + yy);
    const double diff = 0.5 * (xx - yy);
    const double rad = std::hypot(diff, xy);
    const double lam_min = half - rad;
    return lam_min > 0.0 ? std::sqrt(lam_min) : 0.0;
  }
};

// 累加一个秩 1 贡献 `σ²·(a,b)(a,b)ᵀ`。
inline void addRank1(Cov2 & c, double a, double b, double sigma)
{
  const double s2 = sigma * sigma;
  if (!(s2 > 0.0) || !std::isfinite(s2)) {return;}
  c.xx += s2 * a * a;
  c.xy += s2 * a * b;
  c.yy += s2 * b * b;
}

// 单点的**逐点随机**位置协方差（world XY）—— 只含深度轴向与像素落位两项。
//
// **为什么只含这两项**：它们逐点变化，同格内多个点可以互相平均掉，
// 所以适合做**逐点**门控。位姿位置与偏航是整帧一致的（见上面的表），
// 它们由 `PointUncertaintyParams` 里的 `sigma_pose_*` 单独声明、
// 由消息的批次级字段发布，**不参与逐点门控**。
//
// 输入与 `pixelDepthToWorld` **同一组量**（内参 / 像素 / 深度 / 位姿），
// 保证"算点的公式"与"算它有多准的公式"不会分裂成两套几何。
//
// 退化输入（深度非有限/非正、内参非正）返回全 0 协方差 —— 调用方据此判"无信息"，
// **不要**把它当成"非常准"。
inline Cov2 pointCovariance(
  const CamIntrinsics & k, double u, double v, double depth,
  const CamPose & pose, const PointUncertaintyParams & p = PointUncertaintyParams{})
{
  Cov2 cov;
  if (!std::isfinite(depth) || depth <= 0.0) {return cov;}
  if (!(k.fx > 0.0) || !(k.fy > 0.0)) {return cov;}

  // ---- 与 pixelDepthToWorld 逐式同源 ----
  const Vec3 ray = pixelRay(k, u, v);                 // (Δu, Δv, 1) 光学系
  const Vec3 ray_body = opticalRayToBody(ray);
  const Vec3 ray_world = rotateByQuat(pose.body_q, ray_body);   // 每单位深度的世界位移

  // 位姿位置与偏航**不在这里**：它们是帧级相关误差，逐点门控挡不住，
  // 由批次级字段发布（见文件头那张表）。

  // ③ 深度：沿射线方向。p = origin + d·ray_world ⇒ ∂p/∂d = ray_world，
  //    但其**长度**是 斜距/深度（画幅边缘 > 1）。σ_d 是**轴向**深度误差，
  //    故位移量级 = σ_d · |ray_world|。
  const double slant_per_depth = std::hypot(ray_world.x, ray_world.y, ray_world.z);
  const double sigma_d = std::hypot(
    p.sigma_depth_rel * depth, p.sigma_depth_abs_m);
  if (slant_per_depth > 0.0) {
    addRank1(cov, ray_world.x / slant_per_depth, ray_world.y / slant_per_depth,
             sigma_d * slant_per_depth);
  }

  // ④ 像素落位：u 方向 → 光学系 x̂，v 方向 → ŷ，各经同一轴映射与旋转。
  //    位移量级 = σ_px · d / f。
  const Vec3 du_world = rotateByQuat(pose.body_q, opticalRayToBody(Vec3{1.0, 0.0, 0.0}));
  const Vec3 dv_world = rotateByQuat(pose.body_q, opticalRayToBody(Vec3{0.0, 1.0, 0.0}));
  addRank1(cov, du_world.x, du_world.y, p.sigma_pixel_px * depth / k.fx);
  addRank1(cov, dv_world.x, dv_world.y, p.sigma_pixel_px * depth / k.fy);

  return cov;
}

// 观测视角质量：射线与**水平面法向**夹角的余弦（1 = 正下方直视，→0 = 掠射）。
//
// **为什么用余弦而不是存 3 维视线向量**：对"落位有多可信"起作用的只有入射角
// （掠射时同样的深度误差摊到地面上更长），方向本身已由点的位置隐含。
// 1 个 float 携带了 3 个 float 里唯一有用的信息。
//
// 返回 0 表示无法判定（深度非有限）。
inline double viewCosine(
  const CamIntrinsics & k, double u, double v, double depth, const CamPose & pose)
{
  if (!std::isfinite(depth) || depth <= 0.0) {return 0.0;}
  const Vec3 ray = pixelRay(k, u, v);
  const Vec3 ray_world = rotateByQuat(pose.body_q, opticalRayToBody(ray));
  const double n = std::hypot(ray_world.x, ray_world.y, ray_world.z);
  if (!(n > 0.0)) {return 0.0;}
  // 正下视相机看向 -Z，故与法向 (0,0,1) 的夹角余弦取 |z| 分量
  return std::min(1.0, std::fabs(ray_world.z) / n);
}

// 帧级相关误差的水平位移上界（m）。
//
// **为什么要单独给**：位姿位置与偏航是**整帧同向**的误差，帧内点数再多也抵不掉
// （点都在一起偏）。所以它不进逐点协方差，也不该被逐点门控拿去做判据 ——
// 那会让画幅边缘的点全被拒（实测会拒掉**全部**候选格）。
// 它的正确用法是**批次级**：整帧一起衰减 hit 强度、或让确认依赖更多地图帧，
// 与 ADR-0039 处理时间错位的方式一致。
inline double framePoseSigma(
  double max_range_m, const PointUncertaintyParams & p)
{
  if (!(max_range_m > 0.0) || !std::isfinite(max_range_m)) {return p.sigma_pose_m;}
  // 偏航：力臂取水平距离上界；位置：各向同性直接加。
  const double yaw = p.sigma_yaw_rad * max_range_m;
  return std::hypot(p.sigma_pose_m, yaw);
}

// 一帧的**观测元数据**（批次级，不是逐点）。
//
// **为什么观测时间不逐点存**：一帧正下视是**一次曝光**，176k 个点共享同一个时刻；
// 逐点存 176k 份相同时间戳是纯浪费。真正缺失的信息是"标签帧与深度帧差了多少"，
// 那是**批次级**的 —— 它决定了本帧点是否存在系统性整体位移（ADR-0039 的补偿量）。
struct ObservationMeta
{
  // 观测时刻（秒，ROS 时间）。等于 `ObstacleFootprintArray.header.stamp`，
  // 单独存一份是为了让下游不必依赖 header 语义就能读到。
  double stamp_s{0.0};
  // 标签帧与深度帧的时间差（秒）。非 0 表示做过空间补偿（ADR-0039）。
  double depth_time_offset_s{0.0};
  // 相机世界位置（观测视角的起点）。
  Vec3 camera_origin;
  // 本帧点的**最大**逐点随机项主方向 1σ（m）。供下游判断"本帧整体够不够可信"。
  double max_sigma_m{0.0};
  // **帧级相关**误差（整帧同向，逐点门控管不了）：
  // 位姿位置 σ 与偏航 σ 产生的水平位移上界。
  // 偏航项 = σ_ψ × 到相机的最远水平距离 —— 边缘点最远，故取画幅角。
  double frame_pose_sigma_m{0.0};
};

}  // namespace agc_perception

#endif  // AGC_PERCEPTION__POINT_UNCERTAINTY_HPP_
