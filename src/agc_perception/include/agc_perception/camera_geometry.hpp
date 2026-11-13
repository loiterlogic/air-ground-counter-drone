// camera_geometry —— 相机世界位姿与像素几何的**唯一来源**（不依赖 OpenCV / ROS）
//
// **为什么单独成头**：`nadir_projection`（投影端）与 `map_adapter`（地图端）必须用
// **同一套**相机几何 —— 世界位置、姿态、轴映射、地面画幅。历史上两边各写一套：
// 投影端按机体姿态投影出障碍点的 world 坐标，地图端只取 odom 的 x/y/z、把画幅当成
// 轴对齐矩形、把相机当成永远正下视无旋转。结果障碍点落在一处、carving 射线从另一处
// 出发，画幅边界与真实视场不符 —— 相机一转向就把障碍区标成 free。
//
// 本头只依赖 `<cmath>`：`nadir_geometry.hpp`（带 OpenCV）与 `map_adapter`
// （刻意不拉 OpenCV）都 include 它，几何不可能再分叉。
//
// 坐标口径：world 为 ENU（+x 东 / +y 北 / +z 上），地面平面 z=0。
// 相机固定在机体上方 `kCamMountZ` 处（nadir_cam_joint z=+0.242），
// 光轴经 pitch=+90° 指向机体 −Z（正下视）。轴映射由 gz GUI 实测靶点标定。

#ifndef AGC_PERCEPTION__CAMERA_GEOMETRY_HPP_
#define AGC_PERCEPTION__CAMERA_GEOMETRY_HPP_

#include <algorithm>
#include <cmath>
#include <limits>
#include <vector>

namespace agc_perception
{

// 相机安装高（m）：与 model.sdf 的 nadir_cam_joint z 偏移**同值**，全仓唯一常量。
constexpr double kCamMountZ = 0.242;

struct Vec3
{
  double x{0.0}, y{0.0}, z{0.0};
};

// 机体→world 的旋转（四元数 xyzw，普通 struct，不依赖 geometry_msgs）。
struct Quat
{
  double x{0.0}, y{0.0}, z{0.0}, w{1.0};
};

// 机体位姿：`body_pos` 是**机体**原点，相机在其上方 `kCamMountZ`。
struct CamPose
{
  Vec3 body_pos;
  Quat body_q;
};

struct CamIntrinsics
{
  double fx{268.6}, fy{268.6}, cx{320.0}, cy{240.0};
};

// 世界点 → 栅格坐标：唯一的 floor((p-origin)/resolution) 实现。
//
// floor 而不是向零截断是负坐标地图的硬语义：origin 左侧的点必须落入
// -1 等更小索引；恰在格线上的点归入右侧/上侧格。所有感知层必须调用
// 该函数，避免投影、证据和规划派生各自复制一套边界规则。
inline int worldToGrid(double world, double origin, double resolution)
{
  if (!std::isfinite(world) || !std::isfinite(origin) ||
    !(resolution > 0.0) || !std::isfinite(resolution))
  {
    return 0;
  }
  return static_cast<int>(std::floor((world - origin) / resolution));
}

inline bool worldToGridChecked(
  double world, double origin, double resolution, int & index)
{
  if (!std::isfinite(world) || !std::isfinite(origin) ||
    !(resolution > 0.0) || !std::isfinite(resolution))
  {
    return false;
  }
  const double q = (world - origin) / resolution;
  if (!std::isfinite(q) || q < static_cast<double>(std::numeric_limits<int>::min()) ||
    q > static_cast<double>(std::numeric_limits<int>::max()))
  {
    return false;
  }
  index = static_cast<int>(std::floor(q));
  return true;
}


// ---------------------------------------------------------------------------------
// 四元数合法性（2026-11-09）：odom 的四元数此前被直接使用，没有校验。
// 旋转公式默认它是**单位四元数**：范数偏离 1 会让投影点整体缩放/偏移，
// NaN 会让整帧障碍点变成 NaN（静默丢点）。不合法时调用方应**丢帧**，不要继续投影。
// ---------------------------------------------------------------------------------
inline bool quatFinite(const Quat & q)
{
  return std::isfinite(q.x) && std::isfinite(q.y) && std::isfinite(q.z) &&
         std::isfinite(q.w);
}

inline double quatNorm(const Quat & q)
{
  return std::sqrt(q.x * q.x + q.y * q.y + q.z * q.z + q.w * q.w);
}

// 范数容差取 1e-2：gz/odom 的量化误差远小于此，而真正坏掉的姿态偏差是量级级的。
inline bool quatUnit(const Quat & q, double tol = 1e-2)
{
  if (!quatFinite(q)) {return false;}
  return std::fabs(quatNorm(q) - 1.0) <= tol;
}

inline Quat normalizeQuat(const Quat & q)
{
  const double n = quatNorm(q);
  if (!(n > 0.0) || !std::isfinite(n)) {return Quat{};}
  return {q.x / n, q.y / n, q.z / n, q.w / n};
}

// 四元数旋转向量：q · v · q⁻¹（用旋转矩阵展开，避免引入 tf2 依赖）。
inline Vec3 rotateByQuat(const Quat & q, const Vec3 & v)
{
  const double x2 = q.x + q.x, y2 = q.y + q.y, z2 = q.z + q.z;
  const double xx = q.x * x2, xy = q.x * y2, xz = q.x * z2;
  const double yy = q.y * y2, yz = q.y * z2, zz = q.z * z2;
  const double wx = q.w * x2, wy = q.w * y2, wz = q.w * z2;
  return {
    (1.0 - (yy + zz)) * v.x + (xy - wz) * v.y + (xz + wy) * v.z,
    (xy + wz) * v.x + (1.0 - (xx + zz)) * v.y + (yz - wx) * v.z,
    (xz - wy) * v.x + (yz + wx) * v.y + (1.0 - (xx + yy)) * v.z};
}

// 像素 (u,v) → 相机系射线（z=1 归一化），与给定内参一致于
// image_geometry::PinholeCameraModel::projectPixelTo3dRay。
inline Vec3 pixelRay(const CamIntrinsics & k, double u, double v)
{
  return {(u - k.cx) / k.fx, (v - k.cy) / k.fy, 1.0};
}

// 相机光学系射线 → 机体系：**净轴映射**（实测标定，见 pixelToGround 注释）。
// 两个入口（pixelToGround / pixelDepthToWorld / 画幅四角）必须都走这一个函数，
// 否则轴映射会出现第二套写法。
inline Vec3 opticalRayToBody(const Vec3 & ray)
{
  return {-ray.y, -ray.x, -ray.z};
}

// 相机原点（world）：机体位置 + 姿态旋转后的安装偏移。
inline Vec3 cameraWorldOrigin(const CamPose & pose)
{
  const Vec3 mount = rotateByQuat(pose.body_q, Vec3{0.0, 0.0, kCamMountZ});
  return {pose.body_pos.x + mount.x, pose.body_pos.y + mount.y, pose.body_pos.z + mount.z};
}

// 像素 + **深度** → 该像素对应的真实 3D 点（world 系）。这是 2026-11-08 起的**主路径**。
//
// `depth` 是 gz rgbd 深度图的原始值 = **沿光轴的轴向深度**（米），不是欧氏距离。
// 实测判据（平坦地面、相机高 10 m）：画面各处恒为 10.0000；欧氏距离则应从 10.0
// （中心）变到 15.55（半视场边缘）——故必须按轴向深度解释。
//
// 反投影（相机光学系 z-forward）：
//   p_cam = ((u−cx)/fx · d, (v−cy)/fy · d, d)
// 再套**同一个**实测轴映射，最后经 body→world 旋转并加上相机世界位置。
//
// 返回 false 表示深度无效（<=0、NaN、inf，或超出 clip）。
inline bool pixelDepthToWorld(
  const CamIntrinsics & k, double u, double v, double depth,
  const CamPose & pose, Vec3 & out)
{
  if (!std::isfinite(depth) || depth <= 0.0) {return false;}
  const Vec3 ray = pixelRay(k, u, v);            // (Δu, Δv, 1)
  const Vec3 p_cam{ray.x * depth, ray.y * depth, ray.z * depth};
  const Vec3 body_p = opticalRayToBody(p_cam);   // 实测轴映射
  const Vec3 world_p = rotateByQuat(pose.body_q, body_p);
  const Vec3 origin = cameraWorldOrigin(pose);
  out = {origin.x + world_p.x, origin.y + world_p.y, origin.z + world_p.z};
  return true;
}

// ---- 标签↔深度时间错位的**空间补偿**（ADR-0039）----
//
// **为什么必须有**：标签（分割）与深度来自两个传感器，按时间戳配对，容差
// `depth_pair_tolerance_s`（0.15 s）。最坏情况下标签像素对应的地面位置与深度帧
// 拍到的位置相差 `v · Δt`。UAV 2 m/s 时 = 0.30 m，而 dense_map 的障碍水平尺寸
// 只有 0.6–1.2 m（cylinder 直径 0.5–0.8 m）、栅格 0.5 m —— 0.30 m 足以把点推到
// 相邻格，密集排列下相邻障碍/边缘/空隙互相污染。这不是"深度噪声"，是**系统性
// 错位**：它每帧同向、可算，因此**应当补偿**，而不是当成随机误差靠过滤吸收。
//
// 做法：用「标签时刻」与「深度时刻」之间的机体位移，把反投影出来的点从
// **深度时刻的相机系**平移到**标签时刻的世界系**。两者只差一个平移（同一台相机、
// 相隔 ≤0.15 s，姿态变化对该时长的贡献远小于平移，且姿态已有 slerp 插值）。
//
// `body_shift` = 深度时刻机体位置 − 标签时刻机体位置（world 系，米）。
// 由调用方从 odom 缓冲按两个时间戳查得；缺一侧就给零（= 不补偿，旧行为）。
inline Vec3 shiftPointByBodyMotion(const Vec3 & p, const Vec3 & body_shift)
{
  return {p.x - body_shift.x, p.y - body_shift.y, p.z - body_shift.z};
}

// 时间错位造成的**水平不确定度半径**（米）：`speed · |Δt|`。
//
// **用途（ADR-0039 补正）**：这是"这个点最多可能偏了多少"的**上界**，用来判断
// 单个点是否足以单独确认一个栅格。小障碍在 0.5 m 格下只有 1–3 格宽，而不确定度
// 可能就接近半格 —— 此时**单个点不足以确认任何格**，必须靠多个点一致（见
// `min_hit_points_per_cell`）。这是 temp.md「按运动速度和不确定度给每个点加空间
// 误差半径」与「不要把单个错位后的像素直接当作确定 hit」两条要求的实现点。
inline double timeMisalignmentRadius(double speed_mps, double dt_s)
{
  return std::fabs(speed_mps) * std::fabs(dt_s);
}

// 从相邻两个位姿样本估机体水平速度（m/s）。`dt` 过小或非有限时返回 0（= 未知）。
//
// **为什么不订阅 twist**：odom 的 `twist` 在 gz/PX4 链路上有独立的噪声与延迟，
// 而这里只需要"这两个时间戳之间机体走了多快"—— 位置差分与补偿用的位移**同源**，
// 不会出现"速度取自 twist、位移取自位置"的口径分裂。
inline double bodySpeedBetween(
  const Vec3 & a, double t_a, const Vec3 & b, double t_b)
{
  const double dt = t_b - t_a;
  if (!(std::fabs(dt) > 1e-6)) {return 0.0;}
  const double dx = b.x - a.x, dy = b.y - a.y;
  const double d = std::hypot(dx, dy);
  if (!std::isfinite(d)) {return 0.0;}
  return d / std::fabs(dt);
}

// 像素 → 地面平面 z=0 交点。返回 false 表示射线平行/朝上/交点在相机背后。
//
// **2026-11-08 起不再用于障碍足迹**：它把「看到的像素」当成「地面上的点」，
// 对高层建筑的侧墙会按 H/(H−h) 向外放大（yard 实测整图 IoU 仅 0.363、面积膨胀 2.17×）。
// 现在只用于**无深度时的回退**与**画幅四角**（画幅边界确实定义在地面上）。
//
// 轴映射由 gz GUI 实测靶点标定（/tmp/agc_nadir_probe.sdf：相机 (0,0,14) 正俯视、
// 障碍顶面中心 world (2,1,z=1) 落在像素 (299,199)，内参 f=268.6 cx=320 cy=240）：
// 净变换为 (Δu,Δv,1)_ROS光学 → (−Δv, −Δu, −1)_机体 → 再经 body→world 姿态。
// 成因：gz 相机光学系是 x-forward，SDF pitch=+90° 已把它旋成朝下；而
// PinholeCameraModel::projectPixelTo3dRay 返回的是 z-forward 的 ROS 光学系射线。
// 两者不可再叠加一次 R_y(+90°)（那会让光轴变水平、与地面平行）。
inline bool pixelToGround(
  const CamIntrinsics & k, double u, double v, const CamPose & pose, Vec3 & out)
{
  const Vec3 ray = pixelRay(k, u, v);  // (Δu, Δv, 1)，z-forward ROS 光学系
  const Vec3 body_ray = opticalRayToBody(ray);   // 净轴映射（实测标定）
  const Vec3 world_ray = rotateByQuat(pose.body_q, body_ray);
  const Vec3 cam_origin = cameraWorldOrigin(pose);
  if (std::fabs(world_ray.z) < 1e-9) {return false;}
  const double t = -cam_origin.z / world_ray.z;
  if (t <= 0.0) {return false;}
  out = {cam_origin.x + t * world_ray.x, cam_origin.y + t * world_ray.y, 0.0};
  return true;
}

// 相机**光轴与地面的交点**（world）。这是 carving 射线的正确起点：
// 机体姿态一倾斜，光轴落点就不再等于机体 x/y，而从机体位置发射线会让整束射线偏转。
inline bool cameraGroundPoint(const CamPose & pose, Vec3 & out)
{
  const Vec3 world_ray = rotateByQuat(pose.body_q, Vec3{0.0, 0.0, -1.0});
  const Vec3 cam_origin = cameraWorldOrigin(pose);
  if (std::fabs(world_ray.z) < 1e-9) {return false;}
  const double t = -cam_origin.z / world_ray.z;
  if (t <= 0.0) {return false;}
  out = {cam_origin.x + t * world_ray.x, cam_origin.y + t * world_ray.y, 0.0};
  return true;
}

// ---------------------------------------------------------------------------------
// 位姿按时间查询（2026-11-09）：标签帧、深度帧、odom 是三个独立流，
// 必须按**标签时间戳**取相机位姿，而不是拿"最新一条 odom"。
// ---------------------------------------------------------------------------------
struct PoseSample
{
  double stamp_s{0.0};
  CamPose pose;
};

inline Quat slerpQuat(const Quat & a_in, const Quat & b_in, double t)
{
  Quat b = b_in;
  double d = a_in.x * b.x + a_in.y * b.y + a_in.z * b.z + a_in.w * b.w;
  if (d < 0.0) {                 // 取最短弧（四元数双覆盖）
    b = Quat{-b.x, -b.y, -b.z, -b.w};
    d = -d;
  }
  const double u = std::min(1.0, std::max(0.0, t));
  if (d > 0.9995) {              // 夹角极小：线性插值再归一化，避免除零
    return normalizeQuat(Quat{
      a_in.x + u * (b.x - a_in.x), a_in.y + u * (b.y - a_in.y),
      a_in.z + u * (b.z - a_in.z), a_in.w + u * (b.w - a_in.w)});
  }
  const double th = std::acos(std::min(1.0, std::max(-1.0, d)));
  const double s = std::sin(th);
  const double wa = std::sin((1.0 - u) * th) / s;
  const double wb = std::sin(u * th) / s;
  return Quat{
    wa * a_in.x + wb * b.x, wa * a_in.y + wb * b.y,
    wa * a_in.z + wb * b.z, wa * a_in.w + b.w * wb};
}

// 取 `stamp_s` 时刻的机体位姿：夹在两侧样本之间就插值（位置线性 / 姿态球面插值），
// 否则用最近的样本。`max_gap_s` 是允许的最大时间差；超出即返回 false（调用方丢帧）。
//
// **为什么必须插值**：UAV 2 m/s、odom 30 Hz，但图像 10 Hz；直接取"最新 odom"
// 在标签帧落后 odom 半帧（50 ms）时就偏 0.10 m，落后 3 帧（300 ms）就偏 0.6 m
// —— 超过一个地图格。插值把这个误差压到 odom 采样间隔内（33 ms ⇒ 6.6 cm）。
inline bool poseAtTime(
  const std::vector<PoseSample> & samples, double stamp_s, double max_gap_s,
  CamPose & out, double * used_dt_s = nullptr)
{
  if (samples.empty() || !(max_gap_s >= 0.0)) {return false;}
  // 样本按时间递增；二分找第一个 >= stamp 的样本。
  size_t lo = 0, hi = samples.size();
  while (lo < hi) {
    const size_t mid = lo + (hi - lo) / 2;
    if (samples[mid].stamp_s < stamp_s) {lo = mid + 1;} else {hi = mid;}
  }
  auto report = [used_dt_s](double dt) {
      if (used_dt_s != nullptr) {*used_dt_s = dt;}
    };
  if (lo == 0) {                 // 早于最早样本：只能外推（用最早样本）
    const double dt = samples.front().stamp_s - stamp_s;
    if (dt > max_gap_s) {return false;}
    out = samples.front().pose;
    report(dt);
    return true;
  }
  if (lo >= samples.size()) {    // 晚于最新样本：用最新样本
    const double dt = stamp_s - samples.back().stamp_s;
    if (dt > max_gap_s) {return false;}
    out = samples.back().pose;
    report(dt);
    return true;
  }
  const PoseSample & hi_s = samples[lo];
  const PoseSample & lo_s = samples[lo - 1];
  const double span = hi_s.stamp_s - lo_s.stamp_s;
  if (!(span > 1e-9)) {          // 同戳：取较新的一条
    out = hi_s.pose;
    report(0.0);
    return true;
  }
  // **不做"间隔太大就拒绝"的判断**：两侧样本都落在查询时刻附近时，插值本身是可靠的
  // —— 真实风险是"缓冲里只剩很远的历史"，而那种情况已经被上下的 dt 判据挡住。
  // 早先版本在这里加了 `span > 2*max_gap` 就返回 false，会把**正常的低频样本**
  // （例如 1 Hz 测试数据、或 odom 掉帧后恢复）误判成不可用。
  const double a = std::min(1.0, std::max(0.0, (stamp_s - lo_s.stamp_s) / span));
  out.body_pos = {
    lo_s.pose.body_pos.x + a * (hi_s.pose.body_pos.x - lo_s.pose.body_pos.x),
    lo_s.pose.body_pos.y + a * (hi_s.pose.body_pos.y - lo_s.pose.body_pos.y),
    lo_s.pose.body_pos.z + a * (hi_s.pose.body_pos.z - lo_s.pose.body_pos.z)};
  out.body_q = slerpQuat(lo_s.pose.body_q, hi_s.pose.body_q, a);
  report(0.0);                   // 插值到位，无残余错位
  return true;
}

}  // namespace agc_perception

#endif  // AGC_PERCEPTION__CAMERA_GEOMETRY_HPP_
