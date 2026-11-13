// footprint_geometry —— 相机地面画幅与遮挡阴影的**纯几何**判定（不依赖 OpenCV / ROS）
//
// **为什么单独成头**：`nadir_geometry.hpp` 引入了 OpenCV（像素反投影、连通域聚合），
// 而 `map_adapter` 只需要"画幅多大、阴影多远"这几个标量函数 —— 为它们拉进整个
// OpenCV 依赖既慢又没必要。按《测试分层与可测性》：判定逻辑与重依赖解耦。
//
// **2026-11-09 修正（用户裁定的 P0 根因）**：画幅此前被当成"以相机地面投影为中心的
// 轴对齐矩形"。那只在机体 yaw=0、roll=pitch=0 时成立；一旦相机转向或倾斜，
// 真实视场是一个**任意四边形**（甚至梯形 —— 倾斜时近边窄、远边宽）。
// 地图端却按轴对齐矩形算边界与边缘区，于是射线终点、carve 的 miss 范围、
// 阴影判定全错，误覆盖随姿态周期变化。
//
// 现在画幅由**四个像素角点经同一套相机几何投影到地面**得到（与投影端逐像素反投影
// 共用 `camera_geometry.hpp`），并用多边形运算给出边界距离与内外判定。

#ifndef AGC_PERCEPTION__FOOTPRINT_GEOMETRY_HPP_
#define AGC_PERCEPTION__FOOTPRINT_GEOMETRY_HPP_

#include <algorithm>
#include <cmath>
#include <limits>

#include "agc_perception/camera_geometry.hpp"

namespace agc_perception
{

// 相机地面画幅：**由相机世界位姿 + 内参投影出的四边形**（凸，可能梯形）。
//
// `corners` 顺序固定为图像四角：左上、右上、右下、左下（见 imageCorners），
// 沿多边形边界绕行。退化（任一角投影不到地面 / 面积为 0）时 valid=false。
struct GroundFootprint
{
  // 图像四角投影到地面的点（world，z=0）。
  Vec3 corners[4];
  // 画幅的**形心**（四角平均）。注意：倾斜时它不等于光轴落点，也不等于机体位置。
  Vec3 centroid;
  // 沿 +x / +y 的半宽（**仅诊断与等轴兼容用**：轴对齐时的半宽；倾斜时是包围盒半宽）。
  double half_x{0.0};
  double half_y{0.0};
  double area{0.0};
  bool valid{false};

  // 轴对齐近似：只在 yaw≈0 且 roll=pitch≈0 时才有意义（保留给既有单测与诊断）。
  bool isSquare(double tol_ratio = 0.02) const
  {
    if (!valid || half_x <= 0.0) {return false;}
    return std::fabs(half_x - half_y) / half_x <= tol_ratio;
  }
};

// 图像四角（像素坐标）：左上、右上、右下、左下。
//
// 取**主点 ± 半幅**，而不是 `[0, w−1]`：这样正下视无倾斜时半宽恰好等于
// `H·(w/2)/fx`，与 `GSD = H/f` 恒等式逐字一致（既有单测与文档都钉这个数）。
// `[0, w−1]` 会引入半个像素的偏差（575.5 vs 576），让恒等式悄悄失真 ——
// 半像素是光栅约定，不是几何事实。
inline void imageCorners(const CamIntrinsics & k, int img_w, int img_h, double u[4], double v[4])
{
  const double hw = 0.5 * static_cast<double>(img_w);
  const double hh = 0.5 * static_cast<double>(img_h);
  u[0] = k.cx - hw;  v[0] = k.cy - hh;
  u[1] = k.cx + hw;  v[1] = k.cy - hh;
  u[2] = k.cx + hw;  v[2] = k.cy + hh;
  u[3] = k.cx - hw;  v[3] = k.cy + hh;
}

// 由相机位姿 + 内参 + 图像宽高算地面画幅（**带姿态**）。
//
// 恒等式（正下视透视，地面与像面平行）：`GSD = H/f` ⇒ 地面半宽 = `H·(width/2)/fx`。
// **为什么从内参推导而不是写死 hfov**：`camera_info` 是相机自己报的，换机型 / 改分辨率
// 会自动跟随；写死 `hfov` 会与 SDF **静默漂移**（地图边界悄悄变错，没人会发现）。
//
// 高度/内参非法时返回 invalid —— **不**退回猜测值：
// 猜出来的边界会让"看不见"与"看得见"混淆，那是安全问题，不是精度问题。
inline GroundFootprint footprintFromCamera(
  const CamPose & pose, const CamIntrinsics & k, int img_w, int img_h)
{
  GroundFootprint out;
  if (img_w <= 0 || img_h <= 0) {return out;}
  if (!(k.fx > 0.0) || !(k.fy > 0.0) || !std::isfinite(k.fx) || !std::isfinite(k.fy)) {
    return out;
  }
  if (!quatUnit(pose.body_q)) {return out;}
  const Vec3 cam_origin = cameraWorldOrigin(pose);
  if (!(cam_origin.z > 0.0) || !std::isfinite(cam_origin.z)) {return out;}

  double u[4], v[4];
  imageCorners(k, img_w, img_h, u, v);
  double xmin = std::numeric_limits<double>::infinity(), xmax = -xmin;
  double ymin = xmin, ymax = -xmin;
  for (int i = 0; i < 4; ++i) {
    Vec3 p;
    if (!pixelToGround(k, u[i], v[i], pose, p)) {return out;}
    out.corners[i] = p;
    xmin = std::min(xmin, p.x); xmax = std::max(xmax, p.x);
    ymin = std::min(ymin, p.y); ymax = std::max(ymax, p.y);
  }
  // 多边形面积（鞋带公式，取绝对值）；退化（三点共线等）视为无效。
  double a2 = 0.0;
  for (int i = 0; i < 4; ++i) {
    const int j = (i + 1) % 4;
    a2 += out.corners[i].x * out.corners[j].y - out.corners[j].x * out.corners[i].y;
  }
  out.area = std::fabs(a2) * 0.5;
  if (!(out.area > 1e-9) || !std::isfinite(out.area)) {return out;}
  out.centroid = {
    0.25 * (out.corners[0].x + out.corners[1].x + out.corners[2].x + out.corners[3].x),
    0.25 * (out.corners[0].y + out.corners[1].y + out.corners[2].y + out.corners[3].y),
    0.0};
  out.half_x = 0.5 * (xmax - xmin);
  out.half_y = 0.5 * (ymax - ymin);
  out.valid = std::isfinite(out.half_x) && std::isfinite(out.half_y) &&
    out.half_x > 0.0 && out.half_y > 0.0;
  return out;
}

// 画幅**合理性**判定（2026-11-09）：几何画幅在姿态正常时不应远超正下视口径。
//
// **为什么需要**：实测过渡段（无人机大幅前倾追赶目标）画幅算出过
// `123.9 x 188.2 m`、以及 `0.0 x 0.0`。前者是俯仰约 18° 时四角投影发散的结果，
// 后者是投影退化的结果 —— 两者都让"视场边界"这个前提失效。
// 此时**不应**继续用它去圈定负证据或边缘区：那不是"看得更广"，而是几何已不可信。
//
// 判据：包围盒半宽不得超过正下视半宽的 `max_ratio` 倍。
// 取 1.6：实测正常悬停（1–2° 倾斜）时比值约 1.10–1.15，留足余量；
// 而 18° 前倾时比值可达 4 倍以上，会被明确拦下。
constexpr double kFootprintMaxTiltRatio = 1.6;

inline bool footprintPlausible(
  const GroundFootprint & fp, double cam_height_m, double focal_px, int img_w,
  double max_ratio = kFootprintMaxTiltRatio)
{
  if (!fp.valid) {return false;}
  if (!(cam_height_m > 0.0) || !(focal_px > 0.0) || img_w <= 0) {return false;}
  const double base = cam_height_m * (static_cast<double>(img_w) / 2.0) / focal_px;
  if (!(base > 0.0) || !std::isfinite(base)) {return false;}
  const double m = std::max(fp.half_x, fp.half_y);
  if (!std::isfinite(m) || m <= 0.0) {return false;}
  return m <= max_ratio * base;
}

// 轴对齐退化入口：只有"相机严格正下视、无 yaw"时才有唯一含义。
// 保留它是为了让**单测与诊断**能在不构造四元数的情况下验算 GSD 恒等式；
// 生产路径必须用带位姿的重载（`map_adapter` 只用带位姿的）。
inline GroundFootprint footprintFromCamera(
  double cam_height_m, double fx, double fy, int img_w, int img_h)
{
  CamPose pose;
  pose.body_pos = {0.0, 0.0, cam_height_m - kCamMountZ};
  pose.body_q = Quat{};
  CamIntrinsics k;
  k.fx = fx;
  k.fy = fy;
  k.cx = (img_w - 1) * 0.5;
  k.cy = (img_h - 1) * 0.5;
  return footprintFromCamera(pose, k, img_w, img_h);
}

// 点到线段的距离（2D）。
inline double pointSegmentDistance(
  double px, double py, double ax, double ay, double bx, double by)
{
  const double vx = bx - ax, vy = by - ay;
  const double wx = px - ax, wy = py - ay;
  const double len2 = vx * vx + vy * vy;
  double t = (len2 > 1e-18) ? (wx * vx + wy * vy) / len2 : 0.0;
  t = std::min(1.0, std::max(0.0, t));
  return std::hypot(px - (ax + t * vx), py - (ay + t * vy));
}

// 点是否在画幅多边形内（凸四边形：所有边同号即在内）。
inline bool footprintContains(const GroundFootprint & fp, double x, double y)
{
  if (!fp.valid) {return false;}
  int pos = 0, neg = 0;
  for (int i = 0; i < 4; ++i) {
    const int j = (i + 1) % 4;
    const double ex = fp.corners[j].x - fp.corners[i].x;
    const double ey = fp.corners[j].y - fp.corners[i].y;
    const double c = ex * (y - fp.corners[i].y) - ey * (x - fp.corners[i].x);
    if (c > 1e-12) {++pos;} else if (c < -1e-12) {++neg;}
  }
  return pos == 0 || neg == 0;
}

// 从画幅**形心**沿方向 (dx,dy) 走到画幅边界的距离（m）。
//
// 与旧实现的差异：旧版假设轴对齐矩形、从相机地面投影出发。倾斜时那个边界根本不是
// 视场边界（真实视场是梯形），射线会射到画幅外或提前停住。
// 现在用**多边形射线求交**：逐边求交，取最小的正参数。
//
// 方向退化（0,0）或画幅无效时返回 0（调用方据此跳过）。
inline double footprintEdgeDistance(
  const GroundFootprint & fp, double dx, double dy)
{
  if (!fp.valid) {return 0.0;}
  const double len = std::hypot(dx, dy);
  if (!(len > 0.0) || !std::isfinite(len)) {return 0.0;}
  const double ux = dx / len, uy = dy / len;
  const double ox = fp.centroid.x, oy = fp.centroid.y;
  double best = std::numeric_limits<double>::infinity();
  for (int i = 0; i < 4; ++i) {
    const int j = (i + 1) % 4;
    const double ax = fp.corners[i].x, ay = fp.corners[i].y;
    const double bx = fp.corners[j].x, by = fp.corners[j].y;
    const double ex = bx - ax, ey = by - ay;
    // 解 o + t·u = a + s·e
    const double den = ux * ey - uy * ex;
    if (std::fabs(den) < 1e-12) {continue;}      // 平行
    const double wx = ax - ox, wy = ay - oy;
    const double t = (wx * ey - wy * ex) / den;
    const double s = (wx * uy - wy * ux) / den;
    if (t > 1e-9 && s >= -1e-9 && s <= 1.0 + 1e-9) {best = std::min(best, t);}
  }
  if (!std::isfinite(best) || best <= 0.0) {return 0.0;}
  return best;
}

// ---------------------------------------------------------------------------------
// 可信测量半径（2026-11-09 修正：carve 射程必须有物理上界）
// ---------------------------------------------------------------------------------
//
// **问题**：`footprintFromCamera` 给出的是**几何视场边界**（四角投影的四边形）。
// 它随相机姿态变化：机体悬停时约有 1–2° 倾斜，倾斜把画幅沿该方向拉长
// （实测 2° 时 bbox 半宽从 30.0 m 涨到 32.5 m，四角最远 46 m）。
// 若 carve 射到**这个**边界，射线就会穿过"几何上在视场内、但实际测不准"的区域
// —— 实测后果：911 个真值障碍格被标成 free，其中 **86% 从未进入过任何一帧画幅**；
// 它们距相机 40–50 m，而真实可信半宽只有 30 m。
//
// **判据**：可信半径由**正下视 GSD 恒等式**给出（与姿态无关）：
//   `r_trust = cam_h · (N/2) / f`
// 这就是"地面像素尺寸 = 格宽量级"的半径。超出它，单个像素对应的地面尺寸已大于
// 地图格，射线方向与落点都不可信。
//
// **为什么不用固定常数**：`carve_max_range_m` 是手填值，飞行高度一变就失真
// （与 ADR-0035 (e) 把 `min_area_px` 改成物理量是同一条理由）。
// 这里由**相机自己的高度与内参**派生，自主定高上线后判据自动跟随。
//
// `edge_ratio` 是安全余量：边缘处 GSD 按 `1/cos²` 恶化，取 0.95 表示
// "只信到可信半径的 95%"，把画幅最外圈留给弱证据。
constexpr double kTrustedRadiusRatio = 0.95;

inline double trustedRadius(
  double cam_height_m, double focal_px, int img_w, double edge_ratio = kTrustedRadiusRatio)
{
  if (!(cam_height_m > 0.0) || !std::isfinite(cam_height_m)) {return 0.0;}
  if (!(focal_px > 0.0) || !std::isfinite(focal_px)) {return 0.0;}
  if (img_w <= 0) {return 0.0;}
  const double r = cam_height_m * (static_cast<double>(img_w) / 2.0) / focal_px;
  if (!std::isfinite(r) || r <= 0.0) {return 0.0;}
  const double ratio = std::min(1.0, std::max(0.1, edge_ratio));
  return r * ratio;
}

// 遮挡阴影的**远边**距离（从相机地面投影算起，单位 m）。
//
// 相机高 H、障碍高 h、障碍水平距 d_o ⇒ 阴影远边 = `d_o · H / (H − h)`。
//
// **为什么必须精确算而不是一刀切**（用户否掉了"射线被障碍截断"的第一版）：
// 沿一条射线，遮挡是**三段**的：
//   ① 相机 → d_o          ：可见（障碍前面）
//   ② d_o → d_o·H/(H−h)   ：**真看不见**（阴影区，楼后）
//   ③ d_o·H/(H−h) → 边界  ：**又可见**（视线从楼顶掠过）
// 矮障碍（路缘 0.2 m、矮台 0.5 m）的阴影只有 0.2–0.5 m，后面**应该**标安全；
// 高楼（admin_block 10.55 m）在 15 m 处的阴影到 57.9 m，已超出 30.5 m 边界。
// ⇒ 一刀切会让"能确定安全的"也留成未知，大幅限制规划。
//
// 边界情形：
//   * `h <= 0`（贴地物体）→ 无阴影，返回 `d_o`（后面全可见）；
//   * `h >= H`（障碍与相机同高或更高）→ 阴影无限远，返回 `inf`（后面全看不见）；
//   * `d_o <= 0` → 返回 0。
// 调用方须把 `inf` 当"该方向无可见区"处理。
inline double shadowFarEdge(double cam_height_m, double obstacle_height_m, double obstacle_dist_m)
{
  if (!(obstacle_dist_m > 0.0) || !std::isfinite(obstacle_dist_m)) {return 0.0;}
  if (!(cam_height_m > 0.0) || !std::isfinite(cam_height_m)) {return obstacle_dist_m;}
  const double h = std::max(0.0, obstacle_height_m);
  if (h <= 0.0) {return obstacle_dist_m;}          // 贴地：无阴影
  const double margin = cam_height_m - h;
  if (margin <= 1e-6) {return std::numeric_limits<double>::infinity();}
  return obstacle_dist_m * cam_height_m / margin;
}

// 画幅边缘判定：该地面点到画幅**边界**的距离小于 `(1−edge_ratio)` × 该方向边界距离
// 即视为"边缘区"（用弱负证据）。
// 理由：65° 画幅角处 GSD 恶化 `1/cos² = 5.6×`，那里的"没看到"确实不如中心可信
// —— 但也不该完全不采信。
constexpr double kFootprintEdgeRatio = 0.90;

inline bool isFootprintEdge(
  const GroundFootprint & fp, double dx, double dy, double dist_m,
  double edge_ratio = kFootprintEdgeRatio)
{
  const double edge = footprintEdgeDistance(fp, dx, dy);
  if (!(edge > 0.0)) {return false;}
  return dist_m > edge_ratio * edge;
}

// 判定一个地面点是否落在画幅的**边缘带**内（点到多边形边界的距离 vs 该点方向边界距离）。
// 供"射线终点是否在边缘"这类**已知点**的判定用（旧签名只能沿方向从中心算）。
inline bool isFootprintEdgeAt(
  const GroundFootprint & fp, double x, double y, double edge_ratio = kFootprintEdgeRatio)
{
  if (!fp.valid || !footprintContains(fp, x, y)) {return false;}
  double dmin = std::numeric_limits<double>::infinity();
  for (int i = 0; i < 4; ++i) {
    const int j = (i + 1) % 4;
    dmin = std::min(dmin, pointSegmentDistance(
        x, y, fp.corners[i].x, fp.corners[i].y, fp.corners[j].x, fp.corners[j].y));
  }
  const double dx = x - fp.centroid.x, dy = y - fp.centroid.y;
  const double edge = footprintEdgeDistance(fp, dx, dy);
  if (!(edge > 0.0) || !std::isfinite(dmin)) {return false;}
  // 边缘带宽度 = (1−ratio) × 该方向的画幅半径
  return dmin < (1.0 - edge_ratio) * edge;
}

}  // namespace agc_perception

#endif  // AGC_PERCEPTION__FOOTPRINT_GEOMETRY_HPP_
