// planner_types —— 地面 SE(2) 规划器的**纯数据模型**（不 include ROS 消息包）
//
// 按《测试分层与可测性》：数据结构与判定逻辑必须能脱离 ROS 单测。本文件只定义
// struct / enum / 常量，不含任何算法与 ROS 依赖。
//
// **命名口径**：本规划器是「一种」方法（Hybrid A* 在 SE(2) 状态空间上的差速车重建模），
// 不是「地面主方案」。名字里带方法，是为了将来出现第二种算法时它不被当成唯一答案
// （[ADR-0048](../../../../docs/adr/0048-ground-hybrid-astar-se2-planner.md#top)）。
//
// **栅格语义**（本文件是全链唯一的规划侧分类口径）：
//   `/agc/map` 自 [ADR-0041](../../../../docs/adr/0041-geometry-metadata-instances-and-risk-map.md#top)
//   起输出**风险分档**而不是裸占据：`-1` 未知 / `0` 可通行 / `1–98` 有代价可通行 /
//   `99` 车心进入即擦碰 / `100` 格内占据。
//
//   **为什么不复用 `planning_policy.hpp` 的 `classifyCell`**：它把 `1–99` 一律当未知，
//   那是 [ADR-0035](../../../../docs/adr/0035-perception-map-representation-and-unknown-policy.md#top)
//   时代的口径，已被 ADR-0041 取代。实测（`dense_map` 真实几何、footprint 级 Hybrid A*）：
//   按 `classifyCell` 把 `1–99` 全禁，80 s / 33.9 万节点仍**无解**；按 ADR-0041 分档
//   3.3 s / 1.4 万节点到达。两者对 `1–98` 的判定不同，且**不可互换**。
//
//   两个函数各司其职、并存是**有意**的：`classifyCell` 回答「是否已确认」（baseline 对照臂
//   与感知侧引用它），`classifyCellRisk`（安全层）与本文件的 `classifyPlanningCell` 回答
//   「能不能走」。见 ADR-0048 的「双分类函数」一节。

#ifndef AGC_GROUND__PLANNER_TYPES_HPP_
#define AGC_GROUND__PLANNER_TYPES_HPP_

#include <cmath>
#include <cstdint>
#include <limits>
#include <sstream>
#include <string>
#include <vector>

namespace agc_ground
{
namespace planner
{

// ---------------------------------------------------------------------------------
// 栅格分类（规划侧唯一口径，对齐 ADR-0041）
// ---------------------------------------------------------------------------------

enum class CellBand : int8_t
{
  kUnknown = 0,    // <0 或越界：从未被观测 / 证据不足 → **禁入**
  kFree = 1,       // 0：已知可通行
  kCost = 2,       // 1..98：有代价但可通行（贴车半径的膨胀带）
  kInscribed = 3,  // 99：车心进入即擦碰（膨胀内切带）
  kLethal = 4,     // >=100：格内几何占据
};

// 栅格值 → 分档。**越界值按未知处理**（不放行），与安全层 `classifyCellRisk` 的
// 安全方向一致；区别只在 `1–98`：安全层叫它 `kCost`，本文件叫它 `kCost`（同义）。
inline CellBand classifyPlanningCell(int value)
{
  if (value < 0) {return CellBand::kUnknown;}
  if (value == 0) {return CellBand::kFree;}
  if (value >= 100) {return CellBand::kLethal;}
  if (value >= 99) {return CellBand::kInscribed;}
  return CellBand::kCost;
}

// footprint 是否可以压在某一档上。
//
// **为什么 `kCost` 可压、`kInscribed` 不可压**：`99` 的语义是「车心进入即擦碰」——
// 把车体 footprint 放到 `99` 格上就意味着可能擦碰，这是真碰撞风险，必须挡。
// `1–98` 是「有代价但可通行」，它只该影响代价，不该禁止通行。
inline bool footprintBlocks(CellBand b)
{
  return b == CellBand::kUnknown || b == CellBand::kInscribed || b == CellBand::kLethal;
}

// 走廊判据的阻挡档。
//
// **为什么走廊只看 `kLethal`**：走廊是「沿运动方向、车体宽度带内的纵向间隙」，
// 它要回答的是「前方有没有**真东西**」。`99` 是膨胀环——相邻障碍的 `99` 环在
// `dense_map`（间距 2.645 m、膨胀半径 1.0 m）上几乎相接，若把它算进走廊，
// 实测在 `dense_map` 上走廊阈值 ≥1.5 m 即**无解**（1.5/2.0 m 均 100 s 内找不到路径），
// 而只挡 `100` 时 2.0/2.6/3.0 m 全部可达。见 ADR-0048 的「走廊双阻挡集」一节。
inline bool corridorBlocks(CellBand b)
{
  return b == CellBand::kLethal;
}

// 代价带的归一化代价（0..1）。`kCost` 的 1..98 已经按距离指数衰减，
// 这里直接用它自己的数值归一，不引入第二套映射。
inline double cellCostWeight(int value)
{
  if (value <= 0) {return 0.0;}
  if (value >= 99) {return 1.0;}
  return static_cast<double>(value) / 98.0;
}

inline const char * toString(CellBand b)
{
  switch (b) {
    case CellBand::kUnknown: return "unknown";
    case CellBand::kFree: return "free";
    case CellBand::kCost: return "cost";
    case CellBand::kInscribed: return "inscribed";
    case CellBand::kLethal: return "lethal";
  }
  return "?";
}

// 数值格式化（诊断用；`safety_policy.hpp` 有同名的私有静态函数，
// 这里独立一份 —— 包内头文件之间不共享实现细节）。
inline std::string fmt(double v)
{
  if (!std::isfinite(v)) {return "null";}
  std::ostringstream os;
  os.precision(6);
  os << v;
  return os.str();
}

// ---------------------------------------------------------------------------------
// 几何与状态
// ---------------------------------------------------------------------------------

struct Pose2D
{
  double x{0.0};
  double y{0.0};
  double yaw{0.0};
};

struct MotionState
{
  Pose2D pose;
  double linear_velocity{0.0};
  double angular_velocity{0.0};
};

// 差速车的离散控制输入。
struct Control
{
  double v{0.0};      // m/s（第一版 >= 0，不倒车）
  double omega{0.0};  // rad/s
};

// 一条运动基元：从 start_state 施加 control 持续 duration，按 sampled_poses 离散。
struct Primitive
{
  MotionState start_state;
  Control control;
  double duration{0.0};
  std::vector<Pose2D> sampled_poses;  // 含起点与终点
  double length{0.0};                 // 弧长（m）
  double cost{0.0};
  double clearance_min{std::numeric_limits<double>::infinity()};
};

// 搜索节点的离散键：**必须含航向**。
//
// **为什么不能只按 (x_cell, y_cell) 合并**：同一格内不同航向的可达性完全不同
// （差速车非完整约束）。只按位置合并会错误丢弃「同位置不同航向」的可行状态，
// 表现为搜索在某些狭窄通道里假失败。实测（`dense_map`）：仅位置键 vs 含航向键
// 的到达率不同，后者才稳定。
struct DiscreteKey
{
  int x_cell{0};
  int y_cell{0};
  int yaw_bin{0};

  bool operator==(const DiscreteKey & o) const
  {
    return x_cell == o.x_cell && y_cell == o.y_cell && yaw_bin == o.yaw_bin;
  }
};

struct DiscreteKeyHash
{
  size_t operator()(const DiscreteKey & k) const
  {
    // 三个整数混成一个 64 位再取高位：单纯异或会在网格对齐时大量碰撞。
    const uint64_t a = static_cast<uint64_t>(static_cast<uint32_t>(k.x_cell));
    const uint64_t b = static_cast<uint64_t>(static_cast<uint32_t>(k.y_cell));
    const uint64_t c = static_cast<uint64_t>(static_cast<uint32_t>(k.yaw_bin));
    uint64_t h = a * 0x9E3779B185EBCA87ULL;
    h ^= (b + 0x9E3779B97F4A7C15ULL + (h << 6) + (h >> 2));
    h ^= (c + 0x9E3779B97F4A7C15ULL + (h << 6) + (h >> 2));
    return static_cast<size_t>(h);
  }
};

struct SearchNode
{
  MotionState state;
  DiscreteKey key;
  double g{std::numeric_limits<double>::infinity()};
  double h{0.0};
  double f{std::numeric_limits<double>::infinity()};
  int parent{-1};          // 父节点在 node 池里的下标（-1 = 起点）
  int primitive_id{-1};    // 到达本节点所用的基元（诊断/回溯）
  // 到达本节点的**基元内部采样点**（不含起点，含终点）。
  //
  // **为什么必须存**：回溯若只取节点的终点位姿，基元内部的采样点全部丢失。
  // 对平移基元影响不大（点距 0.15 m），但对**原地旋转**是灾难性的：
  // 一次 0.666 rad 的旋转在回溯后只剩 1 个点，航向跳变全部挤到接缝，
  // 表现为"接缝不连续 0.44 rad" —— 归因完全错位（实测 `yard` s19 pose 18）。
  //
  // 内存代价：每个节点多存 4–8 个 Pose2D（96–192 B）。相对节点本身很小，
  // 且只保留 `max_expanded_nodes` 个节点。
  std::vector<Pose2D> edge_poses;
};

// ---------------------------------------------------------------------------------
// 失败分类（**显式、单一、可归因**；不用裸枚举进日志）
// ---------------------------------------------------------------------------------

enum class PlanFailure
{
  kNone = 0,
  // 阶段 A：输入与地图
  kParamInvalid,   // 参数组合不自洽（如转弯半径 < 1/kappa_max）
  kNoMap,
  kMapInvalid,
  kMapStale,
  kFrameMismatch,
  kNoOdom,
  kNoGoal,
  kGoalInvalid,
  kNotAuthorized,
  kStartOutOfMap,
  kStartNotFree,
  kStartCollision,
  kGoalOutOfMap,
  kGoalNotFree,
  kGoalCollision,
  // 阶段 B：搜索
  kSearchExhausted,
  kSearchTimeout,
  kNoAnalyticConnect,
  // 阶段 C/D：优化与复核
  kOptimizationFailed,
  kOptimizedPathCollision,
  // 阶段 E：动力学
  kDynamicsInfeasible,
  kValidationFailed,
};

inline const char * toString(PlanFailure f)
{
  switch (f) {
    case PlanFailure::kNone: return "none";
    case PlanFailure::kParamInvalid: return "param_invalid";
    case PlanFailure::kNoMap: return "no_map";
    case PlanFailure::kMapInvalid: return "map_invalid";
    case PlanFailure::kMapStale: return "map_stale";
    case PlanFailure::kFrameMismatch: return "frame_mismatch";
    case PlanFailure::kNoOdom: return "no_odom";
    case PlanFailure::kNoGoal: return "no_goal";
    case PlanFailure::kGoalInvalid: return "goal_invalid";
    case PlanFailure::kNotAuthorized: return "not_authorized";
    case PlanFailure::kStartOutOfMap: return "start_out_of_map";
    case PlanFailure::kStartNotFree: return "start_not_free";
    case PlanFailure::kStartCollision: return "start_collision";
    case PlanFailure::kGoalOutOfMap: return "goal_out_of_map";
    case PlanFailure::kGoalNotFree: return "goal_not_free";
    case PlanFailure::kGoalCollision: return "goal_collision";
    case PlanFailure::kSearchExhausted: return "search_exhausted";
    case PlanFailure::kSearchTimeout: return "search_timeout";
    case PlanFailure::kNoAnalyticConnect: return "no_analytic_connect";
    case PlanFailure::kOptimizationFailed: return "optimization_failed";
    case PlanFailure::kOptimizedPathCollision: return "optimized_path_collision";
    case PlanFailure::kDynamicsInfeasible: return "dynamics_infeasible";
    case PlanFailure::kValidationFailed: return "validation_failed";
  }
  return "unknown";
}

// ---------------------------------------------------------------------------------
// 结果
// ---------------------------------------------------------------------------------

// 本次规划是怎么结束的（诊断用；**不是**路线分支开关）。
enum class PlanOutcome
{
  kFailure = 0,
  kSearchPath = 1,     // 搜索路径直接通过复核（优化被放弃或未改善）
  kOptimizedPath = 2,  // 优化后路径通过复核
  kDirectLink = 3,     // 兜底：已知区前沿 + 直连 goal
};

inline const char * toString(PlanOutcome o)
{
  switch (o) {
    case PlanOutcome::kFailure: return "failure";
    case PlanOutcome::kSearchPath: return "search_path";
    case PlanOutcome::kOptimizedPath: return "optimized_path";
    case PlanOutcome::kDirectLink: return "direct_link";
  }
  return "unknown";
}

// 时间参数化结果（第一版**只做诊断**，不进 `/agc/ground/path` 的消息 ABI）。
struct SpeedProfilePoint
{
  double s{0.0};      // 弧长
  double v{0.0};      // 该点允许速度
  double kappa{0.0};  // 曲率
};

struct PathResult
{
  bool success{false};
  PlanFailure failure{PlanFailure::kNone};
  PlanOutcome outcome{PlanOutcome::kFailure};

  std::vector<Pose2D> poses;             // world 系，起点→终点，末端 == goal
  std::vector<double> curvature;         // 与 poses 等长（端点用单侧差分）
  std::vector<SpeedProfilePoint> speed_profile;

  double planning_time_s{0.0};
  int expanded_nodes{0};
  double clearance_min_m{-1.0};   // <0 = 无阻挡格
  double max_curvature{0.0};
  double path_length_m{0.0};

  int raw_path_points{0};    // 搜索原始路径点数
  int final_path_points{0};  // 最终发布点数

  std::string map_signature;   // 规划时刻的地图签名
  std::string replan_reason;   // 本次触发的理由（首规划 / 目标变 / 地图变 / 超时 / 周期）
  std::string detail;          // 失败细节（人读；不进判据）
};

// ---------------------------------------------------------------------------------
// 参数（全部为**可标定量**；在回放与真实动力学取证前不得写成永久契约）
// ---------------------------------------------------------------------------------

struct PlannerParams
{
  // ---- 车体（与 `ground.yaml` 的安全层 footprint 同源）----
  double footprint_half_length{0.5037};
  double footprint_half_width{0.28545};
  // footprint 的**全向**外扩量：半格对角（量化）+ 定位/跟踪误差。
  // **不是** `d_collision=2.0` —— 那会造出全向 2 m 禁行区（ADR-0047 的教训）。
  double footprint_margin{0.3536};

  // ---- 运动基元：按**曲率档**生成，而不是按 omega 档 ----
  //
  // 几何搜索回答「沿哪条线走」，时间参数化回答「多快走」。所以基元应当用
  // **曲率 κ** 表达方向，而不是用 `(v, ω)` 的笛卡尔积 —— 后者会让同一条圆弧
  // 被多种速度重复表达，而且极易与 `kappa_max` 冲突。
  //
  // 实测教训：早先 `omega_set = {±2, ±1, ±0.5, 0}` 配 `v_set = {0.3..1.5}`，
  // 在 `kappa_max = 1.0` 下 `v=0.3, ω=2.0` 的曲率是 6.67 /m（半径 0.15 m），
  // 这条基元**永远**过不了曲率复核。搜索却大量使用它，产出的路径曲率 2.44 /m。
  //
  // 现在：`κ ∈ {±κ_max, ±κ_max/2, 0}` × `v ∈ v_set`，`ω = κ·v` 自动满足
  // `|ω| <= κ_max·v`。`candidateControls()` 仍会按 `kappa_max` 过滤，
  // `validateParams()` 会拒绝不自洽的组合。
  std::vector<double> v_set{0.3, 0.6, 1.0, 1.5};
  // 曲率档（相对 kappa_max 的比例）：-1, -1/2, 0, +1/2, +1
  std::vector<double> curvature_fractions{-1.0, -0.5, 0.0, 0.5, 1.0};
  // **仅**用于原地旋转基元的角速度档（`v=0`，曲率无定义，不受 kappa_max 约束）。
  std::vector<double> omega_set{-2.0, -1.0, -0.5, 0.5, 1.0, 2.0};
  bool allow_in_place_rotation{true};   // 差速车真实能力；安全层对纯旋转特殊处理
  double primitive_dt{0.333};
  double primitive_max_step_m{0.15};    // 采样最大空间步长（不能只查终点）

  // ---- 搜索 ----
  int yaw_bins{16};
  double search_time_budget_s{3.0};     // 墙钟预算；超时 → kSearchTimeout
  int max_expanded_nodes{60000};
  double goal_position_tolerance_m{0.4};
  double goal_heading_tolerance_rad{0.35};
  // 启发式权重（>1 是加权 A*，换取速度；不承诺最优）
  double heuristic_weight{1.0};

  // ---- 代价权重 ----
  double w_time{1.0};
  double w_length{0.5};
  double w_turn{0.3};
  double w_clearance{0.4};
  double w_cost{0.6};          // `1–98` 代价带
  double clearance_target_m{1.2};   // 离障目标（代价项；不是硬约束）

  // ---- 走廊判据（**质量偏好**，不是安全证明）----
  // 走廊 = 沿运动方向、车体宽度带内的纵向间隙；阻挡档 = `kLethal`（见 corridorBlocks）。
  bool corridor_enabled{true};
  double corridor_clearance_m{2.0};
  double corridor_max_scan_m{6.0};

  // ---- 解析连接 ----
  // Dubins shot 的转弯半径。**必须 >= 1/kappa_max**，否则 shot 产出的弧曲率超限。
  //
  // 实测教训：早先取 0.3（= v_min/ω_cap），而 `kappa_max = 1.0` 要求半径 >= 1.0。
  // 于是 Dubins 弧的曲率是 3.33 /m，必然违反曲率上限；表现为接缝处航向跳变
  // 0.3849 rad（弦长 0.1148 → `2·asin(0.1148/0.6) = 0.385`，精确吻合 R=0.3 的弧），
  // 归因完全错位成"接缝不连续"。
  //
  // 取 `1.0` 而不是 `0.3`：与 `kappa_max` 自洽。`validateParams` 会强制校验。
  double analytic_min_turn_radius_m{1.0};
  // 只在距目标这么近时才尝试解析连接。
  // **性能关键**：每个扩展节点都做整段直连扫掠会退化成 O(距离/步长) 的位姿表构建，
  // 实测把 `dense_map` 的单次规划推到 20 s 超时。经典 Hybrid A* 同样只在接近时尝试。
  double analytic_connect_max_dist_m{4.0};
  // 接缝航向容差（rad）。超过即判该路径无效（**不靠平滑掩盖**）。
  // 取 0.15 rad ≈ 8.6°：小于它是"可接受的跟踪误差"，大于它是构造缺陷。
  double seam_heading_tol_rad{0.15};

  // ---- 优化（B 样条/弹性带）----
  bool optimization_enabled{true};
  double resample_spacing_m{0.25};
  // 移动平均平滑（**路径构造的一部分**，不是优化可选项）：
  // Hybrid A* 回溯路径在基元边界曲率跳变，不平滑则角加速度复核必然失败。
  // 窗口按点数（= 弧长 / resample_spacing_m），3 点 × 3 遍 ≈ 有效平滑长度 0.75 m。
  int smoothing_passes{3};
  int smoothing_half_window{2};
  // 平滑窗口按**物理长度**标定，不按点数：`smoothing_window_m / resample_spacing_m`。
  // 实测（`yard` 的 s19 路线，34 m、需绕障）：窗口 0.5 m 时曲率 0.66 /m 虽在限内，
  // 但**曲率变化率**过大 ⇒ 角加速度 2.96 rad/s² 超限 2.0。
  // 差速车的转向不能瞬变，所以平滑窗口必须够长（默认 1.0 m ≈ 2 个车长）。
  double smoothing_window_m{1.0};
  double bspline_interval{0.5};
  int optimization_max_iterations{200};
  double optimization_time_budget_s{0.5};
  double lambda_smooth{1.0};
  double lambda_clearance{1.0};
  double lambda_curvature{0.5};
  // 曲率**变化率**代价。只罚「曲率超限」不够：实测 s19 的曲率 0.66 /m 在限内，
  // 但曲率在相邻点间跳变 ⇒ 角加速度 2.96 rad/s² 超限 2.0。
  // 差速车的转向不能瞬变，所以「曲率平滑」与「曲率幅值」必须分别罚。
  double lambda_curvature_rate{2.0};
  double lambda_length{0.1};
  double lambda_heading{0.5};
  double kappa_max{1.0};   // 1/m（≈ 最小转弯半径 1 m）

  // ---- 时间参数化 ----
  double v_cap{1.5};
  double w_cap{2.0};
  double a_lat_max{1.0};
  double a_acc_max{0.8};
  double a_brake_max{1.0};
  double w_acc_max{2.0};

  // ---- 兜底（有界直连）----
  // 意图：**时刻有终点目标**。搜索到已知区前沿后直连 goal，末端恒为 goal
  // （消费侧的 `goal_consistency_m` 要求路径末端与 goal 一致）。
  // 未知段由后续重规划补上（重规划由「已知自由面积变化」触发）。
  bool direct_link_enabled{true};
  int frontier_min_expansions{200};   // 至少扩展这么多节点后才允许兜底（避免一开始就偷懒）

  // ---- 地图签名 ----
  int signature_free_delta_cells{200};   // 已知自由格数变化超过它 → 触发重规划
};

// 参数自洽性校验。返回空串表示合法，否则是**人读的**具体原因。
//
// 为什么必须有这一层：本仓已有过一次同类事故（`inflation_radius < robot_radius`
// 让膨胀带静默为空）。参数各自合法、组合起来不自洽时，现象会以**完全无关的形式**
// 出现 —— 本次是"接缝不连续"，实际是"转弯半径与曲率上限矛盾"。
inline std::string validateParams(const PlannerParams & p)
{
  if (p.footprint_half_length <= 0.0 || p.footprint_half_width <= 0.0) {
    return "footprint half sizes must be positive";
  }
  if (p.footprint_margin < 0.0) {return "footprint_margin must be >= 0";}
  if (!(p.kappa_max > 0.0) || !std::isfinite(p.kappa_max)) {
    return "kappa_max must be positive and finite";
  }
  // **核心自洽性**：解析连接的转弯半径不得小于曲率上限允许的最小半径。
  const double min_radius = 1.0 / p.kappa_max;
  if (p.analytic_min_turn_radius_m < min_radius - 1e-9) {
    std::ostringstream os;
    os.precision(4);
    os << "analytic_min_turn_radius_m (" << p.analytic_min_turn_radius_m
       << ") < 1/kappa_max (" << min_radius
       << "); Dubins arcs would violate kappa_max";
    return os.str();
  }
  // 曲率档与角速度上限的自洽：`omega = frac*kappa_max*v` 必须不超 `w_cap`。
  // 超了会被 `candidateControls` 静默跳过 —— 那是"少给基元"，应当显式报出来。
  for (double v : p.v_set) {
    for (double frac : p.curvature_fractions) {
      const double w = frac * p.kappa_max * v;
      if (std::fabs(w) > p.w_cap + 1e-9) {
        std::ostringstream os;
        os.precision(3);
        os << "primitive (v=" << v << ", curvature_frac=" << frac
           << ") needs omega=" << w << " > w_cap=" << p.w_cap;
        return os.str();
      }
    }
  }
  // 原地旋转档不得超 `w_cap`。
  for (double w : p.omega_set) {
    if (std::fabs(w) > p.w_cap + 1e-9) {
      std::ostringstream os;
      os.precision(3);
      os << "in-place rotation omega=" << w << " > w_cap=" << p.w_cap;
      return os.str();
    }
  }
  if (p.v_cap <= 0.0 || p.w_cap <= 0.0) {return "v_cap / w_cap must be positive";}
  if (p.corridor_clearance_m < 0.0) {return "corridor_clearance_m must be >= 0";}
  if (p.seam_heading_tol_rad <= 0.0 || p.seam_heading_tol_rad > M_PI) {
    return "seam_heading_tol_rad must be in (0, pi]";
  }
  return "";
}

}  // namespace planner
}  // namespace agc_ground

#endif  // AGC_GROUND__PLANNER_TYPES_HPP_
