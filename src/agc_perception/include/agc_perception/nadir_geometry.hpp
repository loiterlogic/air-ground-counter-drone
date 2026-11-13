// nadir_geometry —— 正下视分割 → 地面 2D 占据的**纯几何判定**（不 include ROS 消息包）
//
// 按《测试分层与可测性》：判定逻辑必须能脱离 ROS 单测，输入输出都是普通 struct。
// 节点（nadir_projection.cpp）只负责把 ROS 消息转成这些 struct、调用本头、再发包。
//
// 坐标口径：world 为 ENU（+x 东 / +y 北 / +z 上），地面平面 z=0。
// 相机固定在机体上方 kCamMountZ 处（nadir_cam_joint z=+0.242，实测机体 14m → 相机 14.242m），
// 光轴经 pitch=+90° 指向机体 −Z（正下视）。
// 轴映射由 gz GUI 实测标定，见 pixelToGround 注释：不可再叠加 R_y(+90°)。

#ifndef AGC_PERCEPTION__NADIR_GEOMETRY_HPP_
#define AGC_PERCEPTION__NADIR_GEOMETRY_HPP_

#include <algorithm>
#include <cmath>
#include <limits>
#include <utility>
#include <vector>

#include <opencv2/core.hpp>
#include <opencv2/imgproc.hpp>

#include "agc_perception/camera_geometry.hpp"
#include "agc_perception/footprint_geometry.hpp"
#include "agc_perception/track_association.hpp"

namespace agc_perception
{

constexpr int kObstacleLabel = 10;

// 相机位姿 / 内参 / 四元数 / 轴映射 / 反投影全部来自 `camera_geometry.hpp` ——
// 那个头不依赖 OpenCV，`map_adapter` 也用同一份，几何不可能再分叉。
// 这里只把名字带进本命名空间，**不重新定义**（第二份定义正是分叉的入口）。



struct Obb
{
  double cx{0.0}, cy{0.0}, sx{0.0}, sy{0.0}, yaw{0.0};
  // 高度（2026-11-08 新增）：障碍点的 z 包络。**只由深度给出**，不做任何假设。
  double z_min{0.0}, z_max{0.0};
  int area_px{0};
};

// ---------------------------------------------------------------------------------
// 屋顶带门限（2026-11-08 用户裁定 Q8）：剔除侧墙点
// ---------------------------------------------------------------------------------
//
// **为什么**：正下视画面里一栋楼同时有**屋顶**（稳定，就是它的足迹）与**侧墙**
// （可见高度随深度噪声 / 视角逐帧变化）。把侧墙纳入 XY 包络后，同一物体的 sx
// 实测在 2.50..3.05 m 间变（真实屋顶 2.0 m），偶尔某帧侧墙整片断开 → "大幅跳再回归"。
//
// **做法**：只保留 z ≥ z_max − threshold 的点。门限取
//   `max(kRoofBandFloorM, kRoofBandRatio × 该连通域高度)`
// 两个分量各有其职：
//   * 绝对下限（0.25 m）托住**矮障碍**：薄板/矮台只有十几厘米高，按比例会算出 0
//     门限、把整个顶面剔掉（实测 slab_s 这类会消失）；
//   * 比例项（0.15）自适应**高建筑**：10 m 楼允许 1.5 m 的屋顶起伏（女儿墙、设备间），
//     比固定 0.3 m 更合理——固定门限对高楼的屋顶细节过于苛刻、对矮障碍又过于宽松。
// **2026-11-09 收紧（用户实测：误覆盖在画幅内占 80%，周期性随 standoff 环绕涨落）**：
// 0.25/0.15 → 0.15/0.08。理由：误覆盖集中在障碍边缘 1–3 格（实测 50% 在 1 格内、
// 75% 在 3.6 m 内），而女儿墙 / 屋顶设备 / 屋檐都落在旧门限内，它们的**投影位置**
// 比屋顶本体靠外。门限放宽 = 把这些边缘点也当屋顶点收进来 = 外扩。
// 收紧后只保留真正贴近 z 高分位的点。绝对下限仍保留 0.15 m 以托住矮障碍
// （薄板按比例会算出 0 门限、把顶面剔光 —— 这个失败模式实测过）。
// **2026-11-09 实测回滚**：曾试收紧到 0.15/0.08，结果覆盖率 0.462→0.406、
// 误覆盖 0.528→0.625（都变差）—— 收紧把**真实屋顶点**也砍掉了，而不只是边缘残余。
// 结论：误覆盖的主因**不是**屋顶带太宽，收紧不是正确的杠杆。恢复原值。
constexpr double kRoofBandFloorM = 0.25;
constexpr double kRoofBandRatio = 0.15;

inline double roofBandThreshold(double height_m)
{
  return std::max(kRoofBandFloorM, kRoofBandRatio * std::max(0.0, height_m));
}

// 屋顶带的**参考高度**：不用 z_max，而用 z 的**高分位**（默认 90%）。
//
// **为什么不用 z_max**（实测踩过）：z_max 只有极少数点能达到，而侧墙**最顶一行**
// 与屋顶只差一个深度噪声的量级（实测构造里 9.90 vs 10.00）。以 z_max 为基准时，
// 那一行墙顶稳稳落在门限内，它的 XY 已经外扩，足以把包络从 1.0 m 撑到 2.0 m
// —— 过滤形同虚设。用高分位当基准，等价于"承认屋顶是一个面而不是一个峰"：
// 只有确实处在该平面上的点才留下，贴边的那一行墙顶被排除。
//
// 分位取 90%：屋顶点通常占连通域的大多数（正下视看得见屋顶面积），
// 90% 分位落在屋顶平面内；若连通域主要是立面（斜视看墙），90% 分位也会落在墙的上部，
// 此时下方 `pts.size() < min_area` 的兜底会退回全部点，不会把观测丢光。
constexpr double kRoofReferenceQuantile = 0.90;

inline double roofReferenceHeight(const std::vector<double> & zs_sorted)
{
  if (zs_sorted.empty()) {return 0.0;}
  size_t idx = static_cast<size_t>(kRoofReferenceQuantile * (zs_sorted.size() - 1));
  idx = std::min(idx, zs_sorted.size() - 1);
  return zs_sorted[idx];
}

// ---------------------------------------------------------------------------------
// 最小可测尺寸：像素门限 ↔ 物理尺寸的换算（2026-11-08 用户裁定 Q26）
// ---------------------------------------------------------------------------------
//
// **为什么不再用固定像素数**：`min_area_px` 的单位是像素，但它的**物理含义**是
// "最小可测障碍尺寸"。一旦相机分辨率或飞行高度可变（自主定高），固定像素数会让判据
// **随高度漂移**：飞低了 GSD 变小，同样的像素门限对应更小的物理尺寸 ⇒ 突然多出
// 一堆 0.05 m 的碎片；飞高了则反之，细杆被静默吞掉。
//
// 改成"物理量 + 运行时换算"后，判据在任何高度/分辨率下都是同一个意思。
//
// 恒等式（正下视透视，地面与像面平行）：GSD = H / f，全场均匀。
inline double gsdFromHeightAndFocal(double height_m, double focal_px)
{
  if (!(focal_px > 0.0) || !std::isfinite(focal_px)) {return 0.0;}
  return std::max(0.0, height_m) / focal_px;
}

// 物理边长 d（m）对应的最小连通域**像素数**。GSD 非法时返回 1（不放行 0 ——
// 返回 0 会让所有碎片都通过门限，是危险方向）。
inline int minAreaPxForPhysicalSize(double min_side_m, double gsd_m_per_px)
{
  if (!(gsd_m_per_px > 0.0) || !std::isfinite(gsd_m_per_px)) {return 1;}
  if (!(min_side_m > 0.0) || !std::isfinite(min_side_m)) {return 1;}
  const double side_px = min_side_m / gsd_m_per_px;
  const double area = side_px * side_px;
  if (!std::isfinite(area) || area < 1.0) {return 1;}
  return static_cast<int>(std::lround(area));
}

// ---------------------------------------------------------------------------------
// 单帧连通域点池（2026-11-09 性能修复：O(C·N²) → O(N²)）
// ---------------------------------------------------------------------------------
//
// **问题**：`aggregateObbs` 原实现对**每个连通域各扫全图两遍**，复杂度 O(C·N²)。
// 640×480 时 C 小、N² 小，掩盖了它；换到 1152² 后，实测（本机 4 vCPU，障碍像素占 5%）：
//   C=10 → 31 ms，C=13 → 37 ms，C=16 → 44 ms，C=30 → 89 ms，C=100 → 276 ms。
// 10 Hz 的单帧预算是 100 ms，即 **C ≈ 30 就是临界点**。
//
// **临界点不是假设，是实测命中的**（2026-11-09 整链运行，`帧统计` 日志）：
//   真实连通域数 **25.5 个均值 / 35 个峰值**，障碍像素 17 万（16.8% of 1152²）。
//   按这组实测参数复算旧实现：C=33 时 **71 ms/帧（14.0 Hz）** —— 10 Hz 预算只剩 29% 余量，
//   场景再密一点（更多 part 被分割开、或 UAV 飞到建筑群中心）就会跌破 10 Hz。
//   新实现同参数 **15 ms/帧（66 Hz）**，余量 85%，且与 C 基本解耦。
// ⇒ 修复前是"靠场景碰巧不密集"才没出事，不是设计保证。
//
// **做法**：把"扫全图"从 C 次降到 **1 次**。一次 CC + 一次光栅扫描，把每个连通域的
// 3D 点按段存进**扁平数组**；下游按段读取，总复杂度 O(N²)，与 C 无关。
// 同一份点池同时供 OBB 聚合与足迹点发布使用，顺带消掉原先的**第二次 CC**
// （`publishFootprints` 曾对同一张 mask 再跑一遍 connectedComponentsWithStats）。
//
// **为什么不会改变结果**：段内保持**光栅顺序**，与原实现逐像素扫描的推进顺序一致；
// 段内只存 `z` 有限的像素，也正好是原实现两遍循环里唯一会被累加的那批
// （第一遍取 z 分布时只看 z，第二遍才额外要求 x/y 有限）。
// ⇒ `minAreaRect` 的输入点序列逐元素相同，输出可逐字段复现
//   （单测 `PointPoolMatchesPerComponentScan` 逐字段对拍 + 离线 200 组随机用例）。
struct ComponentPoint
{
  float x, y, z;
};

// 足迹点的**语义类别**（ADR-0041）。与 `ObstacleFootprintArray.point_class` 的取值一一对应。
//
// **为什么需要它**（temp.md 方向二）：原来的几何层只知道"这个点在屋顶带内/外"，
// 不知道它是屋顶、墙、边缘还是遮挡区。四类点的**可信度完全不同**：
//   * 屋顶（顶面）就是障碍的足迹 —— 投影到地面位置正确；
//   * 墙 / 侧墙 —— 投影到地面会外扩 `H/(H−h)` 倍（9 m 楼 2.74×、10.55 m 楼 3.86×），
//     实测误覆盖散布到离障碍 1–24 格，就是它造成的；
//   * 边缘 —— 深度/分割边界，落位不可信；
//   * 遮挡区 —— 被挡住，不能当作"看到是空的"（也不能当作占据）。
// 把类别标出来，下游才能按类别决定"信多少"，而不是把所有点一视同仁。
enum PointClass : uint8_t
{
  kPointUnclassified = 0,   // 未分类（旧发布端 / 无法判定）
  kPointRoof = 1,           // 屋顶 / 顶面 —— 真实足迹
  kPointWall = 2,           // 墙 / 侧墙 —— 投影外扩，不应作为地面足迹
  kPointEdge = 3,           // 边缘 —— 落位不可信
  kPointOccluded = 4,       // 遮挡区 —— 既非占据也非自由
};

struct ComponentPoints
{
  std::vector<ComponentPoint> points;   // 按连通域分段拼接
  std::vector<size_t> begin;            // 长度 = labels_n；第 i 段起始下标
  std::vector<size_t> count;            // 长度 = labels_n；第 i 段实际点数
  // **屋顶带过滤结果**（2026-11-09 修复）：`kept[k]==1` 表示第 k 个点通过屋顶带门限
  // （即属于屋顶/顶面，不是侧墙）。与 `points` 等长。
  //
  // **为什么放在点池层**：侧墙点投影到地面会外扩 `H/(H−h)` 倍（9 m 高的楼 2.74×、
  // 10.55 m 的 3.86×）。改造前只有 OBB 用了屋顶带过滤，而**足迹点直接发了全部点** ——
  // 于是侧墙点被逐点栅格化，实测误覆盖散布到离障碍 1–24 格（最大 11.9 m），
  // 与侧墙外扩量级完全吻合。过滤必须与点池同源，两边才不可能再次分叉。
  std::vector<char> kept;
  // 每个点的**类别**（ADR-0041，与 `points` 等长）。取值见 `PointClass`。
  //
  // **为什么与 `kept` 并存而不是取代它**：`kept` 是"要不要进几何足迹"的**布尔判定**
  // （屋顶带 + 立面兜底的结果），而 `class` 是"这个点是什么"的**语义标注**。
  // 两者的兜底逻辑不同：立面为主时 `kept` 会全部置 1，但那些点的类别仍是"墙" ——
  // 下游（评价 / 诊断）需要知道"我用了墙点"，不能因为被保留就谎称它们是屋顶。
  std::vector<uint8_t> point_class;
  // 每个点所属的**母体连通域 label**（与 `points` 等长）。
  //
  // **为什么不塞进 `ComponentPoint`**：那个结构是热路径上的紧凑数组
  // （`ComponentPoint{x,y,z}` 三 float，24 B/点，10 Hz 下 3–7 MB/s）。
  // 加字段会把它撑大，而 label 只在**发布时**用一次。并行数组沿用本类既有的
  // "同下标"纪律（与 `kept` / `point_class` 一致），不引入搬点风险。
  std::vector<int> point_label;
  // 每个点的**观测几何**（与 `points` 等长）：轴向深度与像素坐标。
  //
  // **为什么点池要带它**（ADR-0042）：逐点协方差由「内参 + 像素 + 深度 + 位姿」
  // 解析给出，而 `points` 里只有世界坐标 —— 从世界坐标反推深度/像素等于把
  // `pixelDepthToWorld` 求逆，既有数值误差又会出现第二套几何写法。
  // 点池是唯一同时知道"世界位置"与"它是从哪个像素、多深看来的"的地方。
  //
  // 并行数组沿用本类既有的同下标纪律（与 `kept` / `point_class` / `point_label` 一致）：
  // 不塞进 `ComponentPoint`，因为那个结构是热路径紧凑数组（24 B/点），
  // 而这两个量只在**发布时**用一次。多 12 B/点 ≈ 2.1 MB/帧，可接受。
  std::vector<float> point_depth;       // 轴向深度（m）
  std::vector<float> point_u;           // 像素列
  std::vector<float> point_v;           // 像素行
  int labels_n{0};                      // 连通域总数（含背景 label 0）
  long raw_pixels{0};                   // 参与聚合的像素总数（诊断：与 count 之和一致）
  long kept_pixels{0};                  // 通过屋顶带门限的像素数（诊断）
  long merged_components{0};            // 被并入母体的碎片数（诊断）
  // label → 所属段（合并后 = 母体 label；未合并 = 自身）。长度 = labels_n。
  // **合并只改归属，不搬点**：`points` 与 `kept` 的下标始终一一对应，
  // 因此屋顶带掩码不会与点错位（搬点最容易在这里出错）。
  std::vector<int> group_of;

  bool empty() const {return points.empty();}
  bool isKept(size_t k) const {return k < kept.size() && kept[k] != 0;}
};

// ---------------------------------------------------------------------------------
// 碎片合并门限（2026-11-09 用户裁定：面积门限不得吞掉同一障碍的碎片）
// ---------------------------------------------------------------------------------
//
// **问题**：`min_area_px` 按"单个连通域的像素面积"判定。大型建筑被深度噪声 /
// 遮挡 / 画幅边缘切成多块时，每一块都可能**单独**低于门限，于是整块真实障碍被丢掉
// —— 覆盖率因此有一个与算法无关的天花板。
//
// **做法**：门限分两步 —— 先把"**空间邻近 + 高度一致**"的碎片并入最近的达标母体，
// 仍不达标的连通域才按原口径丢弃。
// 邻近判据用**地面 XY 距离**而不是像素距离：像素距离随飞行高度漂移（GSD 变），
// 物理距离不漂。高度一致判据防止把"贴着高楼的矮台"并进高楼 —— 那会让矮台借用
// 高楼的高度、把阴影算长。
//
// **不合并孤立噪声**：只并入**已达门限**的母体；孤立碎片没有母体可并，仍被丢弃。
struct FragmentMergeParams
{
  // 碎片形心到母体形心的最大水平距离（m）。0.5 m 格下 1.5 m ≈ 3 格：
  // 足以跨过深度噪声造成的 1–2 格断口，又不会把相邻两个独立障碍并成一个。
  // 0 或负 ⇒ **关闭合并**（与旧口径逐字节等价，单测靠它做对照）。
  double max_gap_m{1.5};
  // 高度一致性：碎片与母体的 z 包络间隙不得超过此值（m）。
  double max_dz_m{1.0};
};

// 前向声明：点池收集完就调用它算屋顶带掩码（定义在下方，因为它需要 ComponentPoints 完整）。
inline void applyRoofBandFilter(ComponentPoints & cp, int min_area);

// 一次 CC + 两次全图扫描：把每个连通域的 3D 点按段收集起来。
//
// 第一遍只累加"每段的点数/形心/z 包络"（不写点），用于**合并判据**；
// 合并定稿后第二遍才写点。两遍都是 O(N)，与连通域个数无关。
// 面积 < min_area 且**没有母体可并**的连通域不占内存（与原口径一致）。
//
// `depth` 可选（ADR-0042）：给了就同时记录每点的轴向深度与像素坐标，
// 供下游算逐点协方差。**像素坐标由循环下标直接给出**（`u=x` / `v=y`），
// 不需要额外传图。不给则三个并行数组留空，下游按"无信息"处理 ——
// 这样既有单测与旧调用点逐字不变，不必为了新字段重写全部用例。
inline ComponentPoints collectComponentPoints(
  const cv::Mat & mask, const cv::Mat & xs, const cv::Mat & ys, const cv::Mat & zs,
  int min_area, const FragmentMergeParams & merge = FragmentMergeParams{},
  const cv::Mat * depth = nullptr)
{
  ComponentPoints cp;
  if (mask.empty() || mask.size() != xs.size() || mask.size() != ys.size() ||
    mask.size() != zs.size())
  {
    return cp;
  }
  // 深度图尺寸必须与掩码一致，否则 (v,u) 索引会越界读。
  const bool have_depth = (depth != nullptr) && !depth->empty() &&
    depth->size() == mask.size() && depth->type() == CV_32FC1;
  cv::Mat labels, stats, centroids;
  const int n = cv::connectedComponentsWithStats(mask, labels, stats, centroids, 8);
  cp.labels_n = n;
  const size_t nn = static_cast<size_t>(std::max(0, n));
  cp.begin.assign(nn, 0);
  cp.count.assign(nn, 0);
  cp.group_of.assign(nn, 0);

  // ---- 第一遍：每段的点数 / 形心 / z 包络 ----
  std::vector<size_t> cnt(nn, 0);
  std::vector<double> sumx(nn, 0.0), sumy(nn, 0.0);
  std::vector<double> zlo(nn, std::numeric_limits<double>::infinity());
  std::vector<double> zhi(nn, -std::numeric_limits<double>::infinity());
  for (int y = 0; y < mask.rows; ++y) {
    const int * lrow = labels.ptr<int>(y);
    const float * xrow = xs.ptr<float>(y);
    const float * yrow = ys.ptr<float>(y);
    const float * zrow = zs.ptr<float>(y);
    for (int x = 0; x < mask.cols; ++x) {
      const int l = lrow[x];
      if (l <= 0) {continue;}
      const float wz = zrow[x];
      if (!std::isfinite(wz)) {continue;}   // 与原实现一致：z 非有限的像素不进 z 分布
      const size_t li = static_cast<size_t>(l);
      ++cnt[li];
      sumx[li] += xrow[x];
      sumy[li] += yrow[x];
      const double wz_d = static_cast<double>(wz);
      zlo[li] = std::min(zlo[li], wz_d);
      zhi[li] = std::max(zhi[li], wz_d);
    }
  }

  // ---- 合并判据：碎片（面积 < min_area）并入最近的达标母体 ----
  // 面积门限仍用 CC 的 AREA（与改造前口径逐字一致：不因 z 无效点而放宽）。
  std::vector<char> big(nn, 0);
  for (int i = 1; i < n; ++i) {
    const size_t li = static_cast<size_t>(i);
    cp.group_of[li] = i;
    if (cnt[li] == 0) {continue;}
    if (stats.at<int>(i, cv::CC_STAT_AREA) >= min_area) {big[li] = 1;}
  }
  auto findRoot = [&cp](int l) {
      int r = l;
      while (cp.group_of[static_cast<size_t>(r)] != r) {
        r = cp.group_of[static_cast<size_t>(r)];
      }
      // 路径压缩（只压一层也够：合并深度最多 1）
      int cur = l;
      while (cp.group_of[static_cast<size_t>(cur)] != r) {
        const int nxt = cp.group_of[static_cast<size_t>(cur)];
        cp.group_of[static_cast<size_t>(cur)] = r;
        cur = nxt;
      }
      return r;
    };
  if (merge.max_gap_m > 0.0) {
    const double gap2 = merge.max_gap_m * merge.max_gap_m;
    for (int i = 1; i < n; ++i) {
      const size_t li = static_cast<size_t>(i);
      if (cnt[li] == 0 || big[li]) {continue;}
      const double cxi = sumx[li] / static_cast<double>(cnt[li]);
      const double cyi = sumy[li] / static_cast<double>(cnt[li]);
      int best = 0;
      double best_d2 = std::numeric_limits<double>::infinity();
      for (int j = 1; j < n; ++j) {
        const size_t lj = static_cast<size_t>(j);
        if (j == i || !big[lj]) {continue;}
        // 高度一致性：两段 z 包络的**间隙**（重叠时为 0）
        const double dz = std::max(
          0.0, std::max(zlo[li], zlo[lj]) - std::min(zhi[li], zhi[lj]));
        if (dz > merge.max_dz_m) {continue;}
        const double cxj = sumx[lj] / static_cast<double>(cnt[lj]);
        const double cyj = sumy[lj] / static_cast<double>(cnt[lj]);
        const double d2 = (cxi - cxj) * (cxi - cxj) + (cyi - cyj) * (cyi - cyj);
        if (d2 > gap2) {continue;}
        if (d2 < best_d2) {best_d2 = d2; best = j;}
      }
      if (best == 0) {continue;}            // 没有母体可并 ⇒ 仍按原口径丢弃
      cp.group_of[li] = best;
      ++cp.merged_components;
    }
  }

  // ---- 定段：只保留"达标母体 + 已并入它的碎片" ----
  size_t total = 0;
  std::vector<size_t> root_total(nn, 0);
  for (int i = 1; i < n; ++i) {
    const size_t li = static_cast<size_t>(i);
    if (cnt[li] == 0) {continue;}
    const int r = findRoot(i);
    if (!big[static_cast<size_t>(r)]) {continue;}   // 无母体的碎片：丢弃
    root_total[static_cast<size_t>(r)] += cnt[li];
  }
  for (int i = 1; i < n; ++i) {
    const size_t li = static_cast<size_t>(i);
    if (root_total[li] == 0) {continue;}
    cp.begin[li] = total;
    cp.count[li] = root_total[li];
    total += root_total[li];
  }
  if (total == 0) {return cp;}
  cp.points.resize(total);
  cp.point_label.assign(total, 0);
  if (have_depth) {
    cp.point_depth.assign(total, 0.0f);
    cp.point_u.assign(total, 0.0f);
    cp.point_v.assign(total, 0.0f);
  }

  // ---- 第二遍：按段写入点（段内保持光栅顺序）----
  std::vector<size_t> fill(nn, 0);
  for (int y = 0; y < mask.rows; ++y) {
    const int * lrow = labels.ptr<int>(y);
    const float * xrow = xs.ptr<float>(y);
    const float * yrow = ys.ptr<float>(y);
    const float * zrow = zs.ptr<float>(y);
    const float * drow = have_depth ? depth->ptr<float>(y) : nullptr;
    for (int x = 0; x < mask.cols; ++x) {
      const int l = lrow[x];
      if (l <= 0) {continue;}
      const float wz = zrow[x];
      if (!std::isfinite(wz)) {continue;}
      const int r = findRoot(l);
      const size_t ri = static_cast<size_t>(r);
      if (cp.count[ri] == 0) {continue;}
      const size_t idx = cp.begin[ri] + fill[ri];
      // 段容量 = 该根下所有成员的点数之和 ⇒ 理论上不会越界。
      // 仍然显式守护：越界写会静默破坏**相邻**段的数据，症状极难归因。
      if (idx >= cp.points.size()) {continue;}
      cp.points[idx] = ComponentPoint{xrow[x], yrow[x], wz};
      cp.point_label[idx] = r;   // 母体 label（合并后）
      if (have_depth) {
        // 深度无效时记 0（"无信息"），**不**记 NaN —— 下游按 0 判退化，
        // 与 `pointCovariance` 的退化返回一致，不必两处都判 NaN。
        const float d = drow[x];
        cp.point_depth[idx] = (std::isfinite(d) && d > 0.0f) ? d : 0.0f;
        cp.point_u[idx] = static_cast<float>(x);
        cp.point_v[idx] = static_cast<float>(y);
      }
      ++fill[ri];
      ++cp.raw_pixels;
    }
  }
  applyRoofBandFilter(cp, min_area);
  return cp;
}

// 在点池上一次性算好**屋顶带门限**，结果写进 `cp.kept`（与 `points` 等长）。
//
// **为什么必须在点池层做**（2026-11-09 修复，实测 bug）：
// 改造前屋顶带过滤只在 `aggregateObbs` 内部对 OBB 生效，而 `publishFootprints`
// 直接发了**点池里的全部点** ⇒ 侧墙点被逐点栅格化。侧墙点投影到地面会外扩
// `H/(H−h)` 倍（9 m 高的楼 2.74×、10.55 m 的 3.86×），实测误覆盖散布到离障碍
// **1–24 格（最大 11.9 m）**，与侧墙外扩量级完全吻合。
// 放在点池层后，OBB 聚合与足迹点发布**共用同一份掩码**，不可能再分叉。
//
// 语义与 `aggregateObbs` 原有逻辑逐条一致（含"立面为主则退回全部点"的兜底）：
//   * 门限 = `max(0.25 m, 0.15 × 该连通域高度)`；
//   * 基准 = z 的 90% 分位（不是 z_max，理由见 roofReferenceHeight）；
//   * 带内点数 < min_area ⇒ 该连通域**全部点**都算保留（斜视看墙的兜底）。
inline void applyRoofBandFilter(ComponentPoints & cp, int min_area)
{
  cp.kept.assign(cp.points.size(), 0);
  // 类别初值 = 未分类：没有跑过滤时（空点池 / 单连通域）下游能看出"没标过"，
  // 而不是误读成"这些都是屋顶"。
  cp.point_class.assign(cp.points.size(), static_cast<uint8_t>(kPointUnclassified));
  if (cp.labels_n <= 1 || cp.points.empty()) {return;}
  std::vector<double> zvals;
  for (int i = 1; i < cp.labels_n; ++i) {
    const size_t li = static_cast<size_t>(i);
    const size_t m = cp.count[li];
    if (m == 0) {continue;}
    const size_t base = cp.begin[li];
    const ComponentPoint * seg = cp.points.data() + base;

    double zlo = std::numeric_limits<double>::infinity();
    double zhi = -std::numeric_limits<double>::infinity();
    zvals.clear();
    zvals.reserve(m);
    for (size_t k = 0; k < m; ++k) {
      const double wz = static_cast<double>(seg[k].z);
      zlo = std::min(zlo, wz);
      zhi = std::max(zhi, wz);
      zvals.push_back(wz);
    }
    const double band = roofBandThreshold(zhi - zlo);
    std::sort(zvals.begin(), zvals.end());
    const double z_cut = roofReferenceHeight(zvals) - band;

    size_t kept_n = 0;
    for (size_t k = 0; k < m; ++k) {
      // **类别与 kept 用同一个 z_cut**（同一判据，不另立一套）：带内 = 屋顶，带外 = 墙。
      // 这样 `point_class` 永远不会与 `kept` 给出互相矛盾的说法。
      if (static_cast<double>(seg[k].z) < z_cut) {
        cp.point_class[base + k] = static_cast<uint8_t>(kPointWall);
        continue;
      }
      cp.point_class[base + k] = static_cast<uint8_t>(kPointRoof);
      cp.kept[base + k] = 1;
      ++kept_n;
    }
    // 带内点数不足：该连通域主要是立面（斜视看墙）⇒ 退回全部点。
    // 丢弃会让地图开洞，而"以墙面当足迹"虽不精确但方向安全（障碍只会被高估）。
    if (kept_n < static_cast<size_t>(min_area)) {
      for (size_t k = 0; k < m; ++k) {cp.kept[base + k] = 1;}
      // **类别不改**：这些点仍然是"墙"。`kept` 表达"我用了它们"（因为丢弃会让地图
      // 开洞），`point_class` 表达"它们其实是墙"（因为评价与诊断需要知道这一点）。
      // 若在这里把类别也改成屋顶，就等于用一次兜底把语义抹掉。
      kept_n = m;
    }
    cp.kept_pixels += static_cast<long>(kept_n);
  }
}

// 从点池聚合 OBB 列表（每段内的逻辑与逐连通域扫描版逐条等价）。
// `out_labels`（可选）：与返回值**等长**，第 k 项是第 k 个 OBB 所属的**连通域 label**。
//
// **为什么必须显式给**：本函数按 `i in [1, labels_n)` 顺序遍历，但会跳过
// `count==0` 的段与"保留点数不足"的段 ⇒ **OBB 下标 ≠ label**。
// 下游若用下标去猜 label（例如 `i+1`），一旦有段被跳过就会把实例 id 贴到错误的点上，
// 而且错得很安静（点还是那些点，只是归属错了）。显式输出让这个假设无处藏身。
inline std::vector<Obb> aggregateObbs(
  const ComponentPoints & cp, int min_area, std::vector<int> * out_labels = nullptr)
{
  std::vector<Obb> out;
  if (out_labels != nullptr) {out_labels->clear();}
  if (cp.labels_n <= 1 || cp.points.empty()) {return out;}

  std::vector<double> zvals;
  std::vector<cv::Point2f> pts;
  for (int i = 1; i < cp.labels_n; ++i) {
    const size_t li = static_cast<size_t>(i);
    const size_t m = cp.count[li];
    if (m == 0) {continue;}   // 等价于原实现 `!std::isfinite(zhi) → continue`
    const ComponentPoint * seg = cp.points.data() + cp.begin[li];

    // ---- z 包络（高度是"楼有多高"，用整片连通域）----
    double zlo = std::numeric_limits<double>::infinity();
    double zhi = -std::numeric_limits<double>::infinity();
    for (size_t k = 0; k < m; ++k) {
      const double wz = static_cast<double>(seg[k].z);
      zlo = std::min(zlo, wz);
      zhi = std::max(zhi, wz);
    }

    // ---- 只取屋顶带内的点（掩码已在点池层算好，与足迹点发布共用）----
    // **2026-11-09 修复**：这里原来自己再算一遍屋顶带，而 `publishFootprints`
    // 发的是**未过滤的全部点** ⇒ 侧墙点被直接栅格化（外扩 H/(H−h)，实测误覆盖
    // 散布到离障碍 1–24 格）。现在两边共用 `cp.kept`，不可能再分叉。
    pts.clear();
    pts.reserve(m);
    for (size_t k = 0; k < m; ++k) {
      if (!cp.isKept(cp.begin[li] + k)) {continue;}
      if (!std::isfinite(seg[k].x) || !std::isfinite(seg[k].y)) {continue;}
      pts.emplace_back(seg[k].x, seg[k].y);
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
    // z 包络仍用**整片连通域**的值（屋顶带只是剔除侧墙对 XY 的污染，
    // 障碍真实高度仍由全部点给出 —— 高度是"楼有多高"，不是"屋顶有多厚"）。
    o.z_min = std::max(0.0, zlo);
    o.z_max = std::max(o.z_min, zhi);
    o.area_px = static_cast<int>(pts.size());
    out.push_back(o);
    if (out_labels != nullptr) {out_labels->push_back(static_cast<int>(li));}
  }
  return out;
}

// 便捷重载：掩码 + 逐像素世界点 → OBB 列表（内部收集点池后聚合）。
//
// 2026-11-08 起输入是**真实 3D 点**（由深度反投影得到），不再是"投到地面的 XY"：
//   * XY 包络 = 该障碍所有 3D 点的 XY 范围 → 高层建筑的侧墙不再向外糊（视差归零）；
//   * z_min/z_max = 同一批点的 z 范围 → 高度直接可观测，无需"已知地面"假设。
// xs/ys/zs 与 mask 同尺寸；无效像素用 NaN。min_area 为连通域最小像素数。
inline std::vector<Obb> aggregateObbs(
  const cv::Mat & mask, const cv::Mat & xs, const cv::Mat & ys, const cv::Mat & zs,
  int min_area)
{
  return aggregateObbs(collectComponentPoints(mask, xs, ys, zs, min_area), min_area);
}



// 观测尺寸的指数滑动平均：抑制单帧 OBB 抖动（实测同 id 的 sx 跨度可达 3.14 m）。
// alpha=1 表示不滤波（沿用本帧）；alpha 越小越平滑、滞后越大。
inline double smoothScalar(double prev, double current, double alpha)
{
  if (!std::isfinite(prev)) {return current;}
  const double a = std::min(1.0, std::max(0.0, alpha));
  return a * current + (1.0 - a) * prev;
}

// 角度平滑：先按最短弧求差再插值，避免 ±π 处跳变（OBB 的 yaw 常在 ±π 附近翻转）。
inline double smoothAngle(double prev, double current, double alpha)
{
  if (!std::isfinite(prev)) {return current;}
  const double a = std::min(1.0, std::max(0.0, alpha));
  double d = std::atan2(std::sin(current - prev), std::cos(current - prev));
  const double r = prev + a * d;
  return std::atan2(std::sin(r), std::cos(r));
}
// ---------------------------------------------------------------------------------
// 形状的稳健估计（2026-11-08 修「障碍形状一直在变、偶尔大幅跳再回归」）
// ---------------------------------------------------------------------------------
//
// **根因（实测，不是 OBB 算法的问题）**：形状抖动的来源是**参与聚合的点集每帧不同**。
// 正俯视画面里一个建筑同时有**屋顶**（稳定）与**侧墙**（可见高度随深度噪声/遮挡逐帧变化），
// 侧墙每多算一截，minAreaRect 的外接框就变长。实测同一物体 sx 在 2.50..3.05 m 间变
// （真实屋顶 2.0 m），偶尔某帧侧墙整片断开 → 形状"大幅变化、下一帧又回归"。
// 对照实验：给固定点集加边界噪声，minAreaRect 的尺寸/yaw 都很稳（yaw 最大跳 7°）；
// 只有**点集本身变化**才会让形状大幅跳 —— 故修法必须在时间维度，不在几何算法。
//
// **为什么用中位数 + MAD 而不是指数平均**：指数平均会被离群帧带偏（一次大幅跳变会
// 把估计拉走，需要多帧才回来）；中位数对离群免疫，MAD（中位绝对偏差）是稳健的离散度，
// 用它判离群不会像 σ 那样被离群点自己撑大。
//
// 参照：ego-planner `plan_env/src/grid_map.cpp` 用 log-odds 多帧累积（p_hit=0.7 /
// p_miss=0.35）也是"不信单帧"的同一思路；本仓需要的是**物体级**稳健估计而非栅格概率。

// 一个目标的形状历史窗口（每维度一个环形缓冲，由节点裁剪到 N 帧）。
struct ShapeWindow
{
  std::vector<double> sx, sy, sz, zc, yaw;
};

// 一个标量观测窗口的稳健估计结果。
struct RobustEstimate
{
  double median{0.0};      // 窗口内位数
  double mad{0.0};         // 中位绝对偏差（稳健离散度）
  int used{0};             // 实际参与估计的样本数
  int rejected{0};         // 被判为离群剔除的样本数
};

inline double medianOf(std::vector<double> v)
{
  if (v.empty()) {return 0.0;}
  const size_t n = v.size() / 2;
  std::nth_element(v.begin(), v.begin() + n, v.end());
  const double hi = v[n];
  if (v.size() % 2 == 1) {return hi;}
  std::nth_element(v.begin(), v.begin() + n - 1, v.end());
  return 0.5 * (v[n - 1] + hi);
}

// 稳健估计：先取中位与 MAD，再剔除 |x−median| > k·MAD 的离群样本，对剩余样本重取中位。
// MAD 为 0（窗口内全同）时不做剔除——否则任何微小变化都会被判离群。
inline RobustEstimate robustEstimate(const std::vector<double> & window, double k)
{
  RobustEstimate out;
  if (window.empty()) {return out;}
  const double med = medianOf(window);
  std::vector<double> dev;
  dev.reserve(window.size());
  for (double x : window) {dev.push_back(std::fabs(x - med));}
  const double mad = medianOf(dev);

  std::vector<double> kept;
  kept.reserve(window.size());
  for (double x : window) {
    if (mad > 1e-9 && std::fabs(x - med) > k * mad) {
      ++out.rejected;
      continue;
    }
    kept.push_back(x);
  }
  out.used = static_cast<int>(kept.size());
  out.mad = mad;
  out.median = kept.empty() ? med : medianOf(kept);
  return out;
}

// 角度的稳健估计：矩形朝向是 mod π 的，必须先"解卷绕"再取中位，否则 ±π 处会算错。
// reference 用作解卷绕的基准（通常是上一帧的估计值）。
inline RobustEstimate robustEstimateAngle(
  const std::vector<double> & window, double k, double reference)
{
  RobustEstimate out;
  if (window.empty()) {return out;}
  std::vector<double> unwrapped;
  unwrapped.reserve(window.size());
  for (double a : window) {
    double d = std::atan2(std::sin(a - reference), std::cos(a - reference));
    unwrapped.push_back(reference + d);
  }
  out = robustEstimate(unwrapped, k);
  out.median = std::atan2(std::sin(out.median), std::cos(out.median));
  return out;
}

}  // namespace agc_perception

#endif  // AGC_PERCEPTION__NADIR_GEOMETRY_HPP_
