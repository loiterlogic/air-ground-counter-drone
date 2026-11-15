// safety_policy —— 地面安全层的**纯逻辑**判定（不 include ROS 消息包、不依赖仿真）
//
// 按《测试分层与可测性》：判定逻辑必须能脱离 ROS 单测。
//
// 职责边界（ADR-0045）：只对**已生成的速度**做裁剪或归零，不规划、不绕行、不生成目标、
// 不接管任务状态。判据不是"某区域里有几个点"，而是「**能不能在进入之前停住**」——
// 后者有物理量纲，可被真实差速车标定与重放。
//
// 为什么不用 Nav2 collision_monitor：它的 `process()` 只由 cmd_vel 回调触发、节点无定时器，
// 命令源从未发过命令时**一条速度都不发**；它也不检测自己输入是否陈旧。这两条在本层必须消失。

#ifndef AGC_GROUND__SAFETY_POLICY_HPP_
#define AGC_GROUND__SAFETY_POLICY_HPP_

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>
#include <sstream>
#include <string>
#include <vector>

namespace agc_ground
{

// ---------------------------------------------------------------------------------
// 栅格风险分类
// ---------------------------------------------------------------------------------

// `/agc/map` 的取值按**安全方向**分类（ADR-0010 的档位顺序 + ADR-0041 的风险分档）。
//
// 关键口径：`99`（车心进入即擦碰）与 `100`（格内即占据）**同等阻挡**；
// 未知（负值）**不是已知自由**，放行它等于让车从没看过的地方开进去。
enum class CellRisk
{
  kFree,      // 0：已知自由
  kCost,      // 1..98：有代价但可通行（只影响限速，不单独触发停车）
  kBlocked,   // 99 / >=100：不可通行
  kUnknown,   // <0 或越界：未知（按"不是已知自由"处理）
};

inline CellRisk classifyCellRisk(int value)
{
  if (value == 0) {return CellRisk::kFree;}
  if (value < 0) {return CellRisk::kUnknown;}
  if (value >= 99) {return CellRisk::kBlocked;}
  return CellRisk::kCost;
}

// ---------------------------------------------------------------------------------
// 状态与档位
// ---------------------------------------------------------------------------------

// 失效状态显式化（ADR-0045 的 #fail-states）：任一非 PASS/SLOW 状态一律零速。
enum class SafetyState
{
  kStartup,         // 已运行但尚未收到任何必需输入
  kNoCommand,       // 原始速度意图从未收到 / 已超时
  kNoPermit,        // 任务未处于驱动许可态 / 许可过期
  kBodyInvalid,     // 车体状态缺失 / 超时 / 负年龄 / odom_valid=false / 四元数非法
  kMapMissing,      // 从未收到地图
  kMapStale,        // 地图超时
  kMapInvalid,      // 地图几何 / 坐标系不一致
  kClockAnomaly,    // 任一输入时间戳在本地时钟的未来
  kParamInvalid,    // 参数校验失败（启动期拒绝）
  kBudgetExceeded,  // 单拍判定超预算 / 扫掠格数超上限
  kStopEmergency,   // footprint 已与阻挡格相交，或 d < d_emergency
  kStopCollision,   // d_emergency <= d < d_collision，或制动扫掠区内有阻挡 / 未知
  kSlow,            // d_collision <= d < d_safety，或扫掠区含代价带
  kPass,            // d >= d_safety 且扫掠区全为已知自由
};

inline bool isStopState(SafetyState s)
{
  return s == SafetyState::kStopCollision || s == SafetyState::kStopEmergency;
}

// "降级态" = 不允许直接跳回 PASS（须过更高门槛 + 连续 N 拍迟滞）。
inline bool isDegradedState(SafetyState s)
{
  return isStopState(s) || s == SafetyState::kSlow;
}

// 是否允许按命令驱动车体（只有 PASS/SLOW 允许）。
inline bool isDrivingState(SafetyState s)
{
  return s == SafetyState::kPass || s == SafetyState::kSlow;
}

inline const char * toString(SafetyState s)
{
  switch (s) {
    case SafetyState::kStartup: return "STARTUP";
    case SafetyState::kNoCommand: return "NO_COMMAND";
    case SafetyState::kNoPermit: return "NO_PERMIT";
    case SafetyState::kBodyInvalid: return "BODY_INVALID";
    case SafetyState::kMapMissing: return "MAP_MISSING";
    case SafetyState::kMapStale: return "MAP_STALE";
    case SafetyState::kMapInvalid: return "MAP_INVALID";
    case SafetyState::kClockAnomaly: return "CLOCK_ANOMALY";
    case SafetyState::kParamInvalid: return "PARAM_INVALID";
    case SafetyState::kBudgetExceeded: return "BUDGET_EXCEEDED";
    case SafetyState::kStopEmergency: return "STOP_EMERGENCY";
    case SafetyState::kStopCollision: return "STOP_COLLISION";
    case SafetyState::kSlow: return "SLOW";
    case SafetyState::kPass: return "PASS";
  }
  return "UNKNOWN";
}

// ---------------------------------------------------------------------------------
// 参数（全部为**可标定量**；绝对值的标定责任见配套规范，代码不得自行"调优"）
// ---------------------------------------------------------------------------------

struct SafetyParams
{
  // 三档距离（顺序不变量：emergency < collision < safety，见 ADR-0010）。
  // 缺省值沿用 ADR-0010 已回填的实测标定 1.0 / 2.0 / 4.0 m。
  double d_emergency{1.0};
  double d_collision{2.0};
  double d_safety{4.0};
  // 恢复门槛（**严格高于**进入门槛，否则会在门槛上抖动）。
  double d_recover_slow{2.0};    // 从 STOP* 上浮到 SLOW 的门槛
  double d_recover_pass{4.5};    // 从降级态回到 PASS 的门槛（必须 > d_safety）
  int recover_ticks{3};          // 连续满足恢复门槛的拍数

  // 输入超时（s）。地图是 2 Hz，不能用 0.3 s 那类扫描口径。
  double t_cmd_timeout{0.5};
  double t_body_timeout{0.5};
  double t_map_timeout{2.0};
  double t_permit_timeout{3.0};

  // 速度上限（与车体模型同源）。
  double v_cap{1.5};
  double w_cap{2.0};

  // 车体 footprint（半长 / 半宽，m），来自既有碰撞盒 1.0074 x 0.5709。
  double footprint_half_length{0.5037};
  double footprint_half_width{0.28545};

  // 制动模型：s_brake = |v|·t_react + v²/(2a)。
  // 默认值 = 2026-11-13 实测标定（safety_dynamics_v1），与 `config/ground.yaml` 同值：
  //   a = 3.2754 m/s²（v_max 阶跃到 0，取多次最小值 = 安全方向）
  //   t_react = 0.1841 s（安全层输出零速 → 真值开始减速，p95）
  // 与 YAML 不一致会让"改了配置却没生效"和"没改配置却变了行为"同样难查。
  double a_brake{3.2754};
  double t_react{0.1841};

  // 离散误差：扫掠闭包按半格膨胀后再取格（不得取 0）。
  // 0.3536 = 0.5 m 格的**半格对角**；实测判停净空跨距 ≈ 1 个格，量化误差不得低估。
  double cell_epsilon{0.3536};

  // 判据阈值。
  // SLOW 的最低速度比例。**不得凭手感取小值**（改造前取 0.2）。
  //
  // 为什么：`SLOW` 把 v 与 ω **同比例**裁剪。横移 ≈ (v/ω)(1−cos ωT)：
  // 比值 v/ω 不变，但 ω 变小让 (1−cos ωT) 变小。实测（2026-11-13，max_offset 标定台架）：
  //   ratio=0.20 → 2 s 横移 **0.0002 / 0.030 / 0.048 m**（车基本不动，逃逸能力实质归零）
  //   ratio=1.00 → 0.956 / 1.153 / 0.769 m
  // 即：把速度裁到 20% 等于**取消横向逃逸能力**。对一个"兜底屏障"来说，
  // 那是把"躲开"变成"停死"——安全层的职责是停在障碍前，不是让车失去机动性。
  //
  // 下限由 `slowRatioFloor()` 反解，并在启动期校验（低于下限即拒绝启动）。
  double slow_min_ratio{1.0};

  // —— 逃逸能力标定参数（用于反解 slow_min_ratio 的物理下限）——
  // `lateral_reach_required_m` = `rl.yaml` 的 `control.max_offset`（ADR-0046 裁定 0.65 m）。
  // 两处必须同值：不同就是"策略以为能做 A、安全层按 B 校验"的两套能力口径。
  // `lateral_window_s` = 反应窗口 T（ADR-0010：2.0 s，**未**为迁就能力主张而放宽）。
  // `lateral_eff_ratio` = 实测横移 / 同轮理想圆弧（0.68 / 0.82 / 0.55，取最小值 0.55）。
  double lateral_reach_required_m{0.65};
  double lateral_window_s{2.0};
  double lateral_eff_ratio{0.55};
  double unknown_ratio_limit{0.5};   // 制动扫掠区内未知格占比上限
  int sweep_cell_limit{40000};       // 单拍扫掠格数上限（超限按不可证明安全处理）
  int sweep_pose_samples{24};        // 制动轨迹采样位姿数（离散化制动扫掠）

  // 任务许可：允许驱动的 AgcTaskState::state 值（与消息定义同值的本地常量）。
  bool permit_require{true};
  // GROUND_APPROACH=3 / TRACKING_SUCCESS=4（与 `ground.yaml` 同值）。
  // 这里曾写 `{3}`，而节点默认与 YAML 都是 `{3,4}` ⇒ 离线重放把 TRACKING_SUCCESS 判成
  // NO_PERMIT，而线上是 PASS。**同一语义两处默认值不同**，正是重放对拍要抓的静默分叉。
  std::vector<int> permit_states{3, 4};
};

// SLOW 比例的下限：**由逃逸能力反解**，不是手感值（自由函数，供校验与成员共用）。
//
// 理想圆弧横移 L(r) = (v_cap/ω_cap)·(1 − cos(r·ω_cap·T))；`eff` 是实测折扣（侧滑削刮）。
// 要求 L(r)·eff ≥ required，二分求最小 r。换底盘 / 换窗口 / 改 max_offset 时自动跟随，
// 不让一个陈旧常数静默失效。
inline double computeSlowRatioFloor(const SafetyParams & p)
{
  const double v = std::max(1e-6, p.v_cap);
  const double w = std::max(1e-6, p.w_cap);
  const double T = std::max(1e-6, p.lateral_window_s);
  const double eff = std::min(1.0, std::max(1e-6, p.lateral_eff_ratio));
  const double need = p.lateral_reach_required_m / eff;
  auto lateral = [&](double r) {return (v / w) * (1.0 - std::cos(r * w * T));};
  if (lateral(1.0) < need) {return 1.0;}   // 满速也达不到：如实返回 1.0
  double lo = 0.0, hi = 1.0;
  for (int i = 0; i < 60; ++i) {
    const double mid = 0.5 * (lo + hi);
    if (lateral(mid) >= need) {hi = mid;} else {lo = mid;}
  }
  return hi;
}

// 启动期参数校验：返回空串 = 通过；否则为**拒绝启动**的理由。
// 每一条都是"违反了就静默出错"的东西，所以必须显式失败而不是夹到合法区间。
inline std::string validateParams(const SafetyParams & p)
{
  auto finite = [](double v) {return std::isfinite(v);};
  if (!finite(p.d_emergency) || !finite(p.d_collision) || !finite(p.d_safety)) {
    return "distance thresholds must be finite";
  }
  if (!(p.d_emergency > 0.0)) {return "d_emergency must be > 0";}
  if (!(p.d_emergency < p.d_collision && p.d_collision < p.d_safety)) {
    return "tier order violated (need 0 < emergency < collision < safety)";
  }
  if (!(p.d_recover_slow >= p.d_collision)) {
    return "d_recover_slow must be >= d_collision";
  }
  if (!(p.d_recover_pass > p.d_safety)) {
    return "d_recover_pass must be > d_safety (otherwise it chatters on the threshold)";
  }
  if (p.recover_ticks < 1) {return "recover_ticks must be >= 1";}
  if (!(p.t_cmd_timeout > 0.0) || !(p.t_body_timeout > 0.0) ||
    !(p.t_map_timeout > 0.0) || !(p.t_permit_timeout > 0.0))
  {
    return "input timeouts must be > 0";
  }
  if (!(p.v_cap > 0.0) || !(p.w_cap > 0.0)) {return "velocity caps must be > 0";}
  if (!(p.footprint_half_length > 0.0) || !(p.footprint_half_width > 0.0)) {
    return "footprint half sizes must be > 0";
  }
  if (!(p.a_brake > 0.0)) {return "a_brake must be > 0";}
  if (!(p.t_react >= 0.0)) {return "t_react must be >= 0";}
  if (!(p.cell_epsilon >= 0.0)) {return "cell_epsilon must be >= 0";}
  // 允许取 1.0：那表示"实测横向能力贴着要求，SLOW 不再降速"（诚实表达，不是 bug）。
  // 拒绝的是 >1（那会把速度放大，超出"只裁不造"）与 <=0（等于停车，语义应走 STOP）。
  if (!(p.slow_min_ratio > 0.0) || p.slow_min_ratio > 1.0) {
    return "slow_min_ratio must be in (0, 1]";
  }
  // **逃逸能力校验**：裁到 `slow_min_ratio` 后仍必须做得出要求的横向位移。
  // 这一条防的正是"为了早点减速而把车裁成不会动"——它不会体现在任何停车判据里，
  // 只会在真正需要躲开的时刻暴露。
  {
    const double floor_r = computeSlowRatioFloor(p);
    // 用 1e-9 容差：floor 由二分求得，p.slow_min_ratio 是配置值，二者应能相等。
    if (p.slow_min_ratio + 1e-9 < floor_r) {
      std::ostringstream os;
      os << "slow_min_ratio=" << p.slow_min_ratio
         << " is below the escape-capability floor " << floor_r
         << " (required lateral " << p.lateral_reach_required_m
         << " m within " << p.lateral_window_s << " s at eff " << p.lateral_eff_ratio
         << "); clipping that hard removes the ability to dodge";
      return os.str();
    }
  }
  if (!(p.unknown_ratio_limit >= 0.0) || p.unknown_ratio_limit > 1.0) {
    return "unknown_ratio_limit must be in [0, 1]";
  }
  if (p.sweep_cell_limit <= 0) {return "sweep_cell_limit must be > 0";}
  if (p.sweep_pose_samples < 1) {return "sweep_pose_samples must be >= 1";}
  return "";
}

// ---------------------------------------------------------------------------------
// 输入
// ---------------------------------------------------------------------------------

// 地图视图（**不持有**数据；生命周期由调用方保证）。取值语义同 `nav_msgs/OccupancyGrid`。
struct MapView
{
  const int8_t * data{nullptr};
  int width{0};
  int height{0};
  double resolution{0.0};
  double origin_x{0.0};
  double origin_y{0.0};
  bool frame_ok{false};   // frame_id == world
  double stamp_s{0.0};
};

// 车体状态（world 系）。`yaw` 由 odom 四元数解出（调用方负责有限性/单位范数校验）。
struct BodyState
{
  double x{0.0};
  double y{0.0};
  double yaw{0.0};
  bool valid{false};      // /agc/ground/odom_valid
  bool finite{true};
  double stamp_s{0.0};
};

// 原始速度意图（车体系，差速车只消费 linear.x / angular.z）。
struct CommandIntent
{
  double v{0.0};
  double w{0.0};
  bool frame_ok{false};   // frame_id == car/base_link
  bool finite{true};
  bool holonomic_ok{true};  // |linear.y| <= eps
  double stamp_s{0.0};
};

struct PermitInput
{
  int state{0};
  double stamp_s{0.0};
};

// 一拍的全部输入。`present=false` 表示"从未收到"（与"收到但过期"是两件事）。
struct SafetyInputs
{
  double now_s{0.0};
  bool has_command{false};
  CommandIntent command;
  bool has_body{false};
  BodyState body;
  bool has_map{false};
  MapView map;
  bool map_valid_flag{true};   // /agc/map/valid
  bool has_permit{false};
  PermitInput permit;
};

// 判定诊断（进日志与 `/agc/ground/safety_status`，非命令者）。
struct SafetyDiagnostics
{
  double map_age_s{-1.0};
  double cmd_age_s{-1.0};
  double body_age_s{-1.0};
  double permit_age_s{-1.0};
  double s_brake_m{0.0};
  double d_min_m{-1.0};          // 车体外缘到最近阻挡/未知格（**各向同性**；诊断用，不定档）
  int d_min_cell_x{-1};
  int d_min_cell_y{-1};
  // 方向化净空：沿当前运动方向、车体宽度带内的纵向间隙（**定档用**，ADR-0047）。
  // <0 = 运动方向带内无阻挡（= 无穷净空）；原地旋转时同样为 -1（侧方不参与定档）。
  double d_corridor_m{-1.0};
  int d_corridor_cell_x{-1};
  int d_corridor_cell_y{-1};
  long swept_cells{0};
  long swept_blocked{0};
  long swept_unknown{0};
  double unknown_ratio{0.0};
  bool swept_has_cost{false};
  double budget_ms{0.0};
  int sweep_poses{0};
  double v_raw{0.0};
  double w_raw{0.0};
};

// 一拍结论。
struct SafetyDecision
{
  SafetyState state{SafetyState::kStartup};
  double out_v{0.0};
  double out_w{0.0};
  std::string reason;
  SafetyDiagnostics diag;
};

// ---------------------------------------------------------------------------------
// 几何基元（供判定与单测共用，避免测试复制生产逻辑）
// ---------------------------------------------------------------------------------

struct Point2
{
  double x{0.0};
  double y{0.0};
};

// 车体足迹（有向矩形）：中心、朝向、半长、半宽。`extra` 为各向外扩量（离散误差）。
inline bool insideFootprint(
  const Point2 & p, const Point2 & center, double yaw,
  double half_length, double half_width, double extra)
{
  const double c = std::cos(yaw), s = std::sin(yaw);
  const double dx = p.x - center.x, dy = p.y - center.y;
  const double u = dx * c + dy * s;      // 沿车头方向
  const double v = -dx * s + dy * c;     // 车体左侧
  return std::fabs(u) <= half_length + extra && std::fabs(v) <= half_width + extra;
}

// 点到有向矩形外缘的距离（点在内部 → 0）。用于"净空"这一距离量。
inline double distanceToFootprint(
  const Point2 & p, const Point2 & center, double yaw,
  double half_length, double half_width)
{
  const double c = std::cos(yaw), s = std::sin(yaw);
  const double dx = p.x - center.x, dy = p.y - center.y;
  const double u = dx * c + dy * s;
  const double v = -dx * s + dy * c;
  const double du = std::fabs(u) - half_length;
  const double dv = std::fabs(v) - half_width;
  if (du <= 0.0 && dv <= 0.0) {return 0.0;}
  const double au = std::max(du, 0.0), av = std::max(dv, 0.0);
  return std::hypot(au, av);
}

// ---------------------------------------------------------------------------------
// 判定器
// ---------------------------------------------------------------------------------

class SafetyPolicy
{
public:
  void setParams(const SafetyParams & p)
  {
    params_ = p;
    params_error_ = validateParams(p);
    reset();
  }

  const SafetyParams & params() const {return params_;}
  const std::string & paramsError() const {return params_error_;}

  // 每个 episode 起始复位恢复迟滞（不清参数、不清"从未收到"的知识）。
  void reset()
  {
    prev_state_ = SafetyState::kStartup;
    recover_count_ = 0;
    have_ever_driven_ = false;
  }

  SafetyState previousState() const {return prev_state_;}

  // SLOW 比例的下限：**由逃逸能力反解**，不是手感值。
  //
  // 理想圆弧横移：L(r) = (v_max/ω_max)·(1 − cos(r·ω_max·T))，r 是线/角同比例裁剪系数。
  // 实测折扣 `lateral_eff_ratio` 把理想值打折（侧滑削刮）。要求
  //     L(r) · eff ≥ required
  // 的最小 r 就是 `slowRatioFloor()`。二分求解，不写死数字 —— 换底盘 / 换窗口 /
  // 改 max_offset 时它会自动跟随，而不是让一个陈旧常数静默失效。
  double slowRatioFloor() const {return computeSlowRatioFloor(params_);}

  // 制动距离：s = |v|·t_react + v²/(2a)。这是"能不能停住"的物理量纲来源。
  double brakingDistance(double v) const
  {
    const double av = std::fabs(v);
    return av * params_.t_react + av * av / (2.0 * params_.a_brake);
  }

  // 一拍判定。纯函数式：除 `prev_state_` / `recover_count_` 的迟滞记忆外不保留其它状态。
  SafetyDecision step(const SafetyInputs & in)
  {
    SafetyDecision out;
    out.diag.v_raw = in.command.v;
    out.diag.w_raw = in.command.w;

    // ① 参数闸：非法即拒绝（节点在启动期已拒绝，这里兜住运行期被改参数的情形）。
    if (!params_error_.empty()) {
      out.state = SafetyState::kParamInvalid;
      out.reason = params_error_;
      return finish(out, in);
    }

    // ② 时钟闸：任一**已收到**输入的 stamp 在未来 → 坏时钟，不得当作新鲜。
    const bool cmd_future = in.has_command && ageOf(in.now_s, in.command.stamp_s) < 0.0;
    const bool body_future = in.has_body && ageOf(in.now_s, in.body.stamp_s) < 0.0;
    const bool map_future = in.has_map && ageOf(in.now_s, in.map.stamp_s) < 0.0;
    const bool permit_future = in.has_permit && ageOf(in.now_s, in.permit.stamp_s) < 0.0;
    out.diag.cmd_age_s = in.has_command ? ageOf(in.now_s, in.command.stamp_s) : -1.0;
    out.diag.body_age_s = in.has_body ? ageOf(in.now_s, in.body.stamp_s) : -1.0;
    out.diag.map_age_s = in.has_map ? ageOf(in.now_s, in.map.stamp_s) : -1.0;
    out.diag.permit_age_s = in.has_permit ? ageOf(in.now_s, in.permit.stamp_s) : -1.0;
    if (cmd_future || body_future || map_future || permit_future) {
      out.state = SafetyState::kClockAnomaly;
      out.reason = "future stamp";
      return finish(out, in);
    }

    // ③ 输入存在性闸：什么都没收到 = 启动期；缺哪一项就报哪一项（不合并成一句"没数据"，
    //    否则补链路的调参方向会被掩盖）。
    if (!in.has_command && !in.has_body && !in.has_map) {
      out.state = SafetyState::kStartup;
      out.reason = "no inputs yet";
      return finish(out, in);
    }
    if (!in.has_map) {
      out.state = SafetyState::kMapMissing;
      out.reason = "map never received";
      return finish(out, in);
    }
    if (!in.has_body) {
      out.state = SafetyState::kBodyInvalid;
      out.reason = "odom never received";
      return finish(out, in);
    }
    if (!in.has_command) {
      out.state = SafetyState::kNoCommand;
      out.reason = "command never received";
      return finish(out, in);
    }

    // ④ 输入时效闸。
    if (out.diag.map_age_s > params_.t_map_timeout) {
      out.state = SafetyState::kMapStale;
      out.reason = "map age=" + fmt(out.diag.map_age_s);
      return finish(out, in);
    }
    if (out.diag.body_age_s > params_.t_body_timeout) {
      out.state = SafetyState::kBodyInvalid;
      out.reason = "body age=" + fmt(out.diag.body_age_s);
      return finish(out, in);
    }
    if (out.diag.cmd_age_s > params_.t_cmd_timeout) {
      out.state = SafetyState::kNoCommand;
      out.reason = "command age=" + fmt(out.diag.cmd_age_s);
      return finish(out, in);
    }

    // ⑤ 一致性闸。
    if (!mapGeometryOk(in.map)) {
      out.state = SafetyState::kMapInvalid;
      out.reason = "map geometry invalid";
      return finish(out, in);
    }
    if (!in.map.frame_ok) {
      out.state = SafetyState::kMapInvalid;
      out.reason = "map frame mismatch";
      return finish(out, in);
    }
    if (!in.map_valid_flag) {
      out.state = SafetyState::kMapInvalid;
      out.reason = "map valid=false";
      return finish(out, in);
    }
    if (!in.body.finite || !in.body.valid) {
      out.state = SafetyState::kBodyInvalid;
      out.reason = in.body.finite ? "odom_valid=false" : "non-finite odom";
      return finish(out, in);
    }
    if (!in.command.finite) {
      out.state = SafetyState::kParamInvalid;
      out.reason = "non-finite command";
      return finish(out, in);
    }
    if (!in.command.frame_ok) {
      out.state = SafetyState::kParamInvalid;
      out.reason = "command frame mismatch";
      return finish(out, in);
    }
    if (!in.command.holonomic_ok) {
      out.state = SafetyState::kParamInvalid;
      out.reason = "linear.y on holonomic=false car";
      return finish(out, in);
    }

    // ⑥ 许可闸：晚于一致性闸——"地图不可用"可能是许可缺失的根因，先报许可会掩盖失效源。
    if (params_.permit_require) {
      if (!in.has_permit) {
        out.state = SafetyState::kNoPermit;
        out.reason = "no task state";
        return finish(out, in);
      }
      if (out.diag.permit_age_s > params_.t_permit_timeout) {
        out.state = SafetyState::kNoPermit;
        out.reason = "permit age=" + fmt(out.diag.permit_age_s);
        return finish(out, in);
      }
      bool permitted = false;
      for (int s : params_.permit_states) {
        if (s == in.permit.state) {permitted = true;}
      }
      if (!permitted) {
        out.state = SafetyState::kNoPermit;
        out.reason = "task state=" + std::to_string(in.permit.state);
        return finish(out, in);
      }
    }

    // ⑦ / ⑧ 可停性闸 + 定档。
    SweepResult sw;
    const std::string sweep_err = evaluateSweep(in, &sw);
    if (!sweep_err.empty()) {
      out.state = SafetyState::kBudgetExceeded;
      out.reason = sweep_err;
      out.diag = sw.diag;
      return finish(out, in);
    }
    out.diag = sw.diag;

    const SafetyState geom = tierFromGeometry(sw, in.command.v, in.command.w, &out.reason);
    out.state = applyHysteresis(geom, sw, &out.reason);
    return finish(out, in);
  }

  // 诊断 JSON（单行；进 `/agc/ground/safety_status`）。纯字符串拼接，可单测。
  static std::string toJson(const SafetyDecision & d, const SafetyParams & p)
  {
    const SafetyDiagnostics & g = d.diag;
    std::ostringstream os;
    os << "{"
       << "\"state\":\"" << toString(d.state) << "\","
       << "\"driving\":" << (isDrivingState(d.state) ? "true" : "false") << ","
       << "\"reason\":\"" << escape(d.reason) << "\","
       << "\"v_raw\":" << num(g.v_raw) << ",\"w_raw\":" << num(g.w_raw) << ","
       << "\"v_out\":" << num(d.out_v) << ",\"w_out\":" << num(d.out_w) << ","
       << "\"map_age_s\":" << num(g.map_age_s) << ","
       << "\"cmd_age_s\":" << num(g.cmd_age_s) << ","
       << "\"body_age_s\":" << num(g.body_age_s) << ","
       << "\"permit_age_s\":" << num(g.permit_age_s) << ","
       << "\"s_brake_m\":" << num(g.s_brake_m) << ","
       << "\"d_min_m\":" << num(g.d_min_m) << ","
       << "\"d_min_cell\":[" << g.d_min_cell_x << "," << g.d_min_cell_y << "],"
       << "\"d_corridor_m\":" << num(g.d_corridor_m) << ","
       << "\"d_corridor_cell\":[" << g.d_corridor_cell_x << ","
       << g.d_corridor_cell_y << "],"
       << "\"swept_cells\":" << g.swept_cells << ","
       << "\"swept_blocked\":" << g.swept_blocked << ","
       << "\"swept_unknown\":" << g.swept_unknown << ","
       << "\"unknown_ratio\":" << num(g.unknown_ratio) << ","
       << "\"budget_ms\":" << num(g.budget_ms) << ","
       << "\"params\":{\"d_emergency\":" << num(p.d_emergency)
       << ",\"d_collision\":" << num(p.d_collision)
       << ",\"d_safety\":" << num(p.d_safety)
       << ",\"a_brake\":" << num(p.a_brake)
       << ",\"t_react\":" << num(p.t_react) << "}"
       << "}";
    return os.str();
  }

private:
  struct SweepResult
  {
    double d_min_m{-1.0};
    int d_min_cell_x{-1};
    int d_min_cell_y{-1};
    // 方向化净空：只量「沿当前运动方向、车体宽度带内」的纵向间隙（<0 = 无）。
    // 定档用这个，不用各向同性的 `d_min_m`（ADR-0047）。
    double d_corridor_m{-1.0};
    int d_corridor_cell_x{-1};
    int d_corridor_cell_y{-1};
    // 本拍输入命令（`evaluateSweep` 写入）。恢复迟滞用它判"有没有运动方向"。
    // 用独立字段而不是 `diag.v_raw`：后者属于 `SafetyDecision`，在 `SweepResult` 里恒 0。
    double cmd_v{0.0};
    double cmd_w{0.0};
    bool swept_blocked{false};
    bool swept_unknown{false};
    bool swept_cost{false};
    double unknown_ratio{0.0};
    int poses{0};
    SafetyDiagnostics diag;
  };

  static double ageOf(double now_s, double stamp_s) {return now_s - stamp_s;}

  static std::string fmt(double v)
  {
    std::ostringstream os;
    os << std::fixed;
    os.precision(3);
    os << v;
    return os.str();
  }

  static std::string num(double v)
  {
    if (!std::isfinite(v)) {return "null";}
    std::ostringstream os;
    os.precision(6);
    os << v;
    return os.str();
  }

  static std::string escape(const std::string & s)
  {
    std::string out;
    for (char c : s) {
      if (c == '"' || c == '\\') {out += '\\';}
      if (static_cast<unsigned char>(c) < 0x20) {continue;}
      out += c;
    }
    return out;
  }

  static bool mapGeometryOk(const MapView & m)
  {
    if (m.data == nullptr) {return false;}
    if (m.width <= 0 || m.height <= 0) {return false;}
    if (!(m.resolution > 0.0)) {return false;}
    if (!std::isfinite(m.origin_x) || !std::isfinite(m.origin_y)) {return false;}
    return true;
  }

  // 给定一拍输入，做制动扫掠并统计；返回非空串表示"无法在预算内证明安全"。
  std::string evaluateSweep(const SafetyInputs & in, SweepResult * out)
  {
    const SafetyParams & p = params_;
    const double v = in.command.v;
    const double w = in.command.w;
    out->cmd_v = v;
    out->cmd_w = w;
    const double s_brake = brakingDistance(v);
    out->diag.s_brake_m = s_brake;

    // 制动轨迹位姿：先按反应时间匀速，再按匀减速到停。位移总长 = s_brake。
    // 朝向按 ω 变化（保守取"一直在以 ω 转向"，不假设 ω 会减小）。
    const int n = std::max(1, p.sweep_pose_samples);
    const double t_stop = (p.t_react + std::fabs(v) / p.a_brake);
    std::vector<Point2> centers;
    std::vector<double> yaws;
    centers.reserve(static_cast<size_t>(n) + 1);
    yaws.reserve(static_cast<size_t>(n) + 1);
    const double dir = (v >= 0.0) ? 1.0 : -1.0;
    for (int k = 0; k <= n; ++k) {
      const double frac = static_cast<double>(k) / static_cast<double>(n);
      const double travelled = s_brake * frac;
      const double psi = in.body.yaw + w * t_stop * frac;
      Point2 c;
      c.x = in.body.x + dir * travelled * std::cos(psi);
      c.y = in.body.y + dir * travelled * std::sin(psi);
      centers.push_back(c);
      yaws.push_back(psi);
    }
    out->poses = static_cast<int>(centers.size());

    // 扫掠闭包：所有位姿 footprint 的轴对齐包围盒（按最大外接半径保守展开）。
    const double r_fp = std::hypot(p.footprint_half_length, p.footprint_half_width);
    double min_x = std::numeric_limits<double>::infinity(), max_x = -min_x;
    double min_y = min_x, max_y = -min_x;
    for (size_t i = 0; i < centers.size(); ++i) {
      min_x = std::min(min_x, centers[i].x - r_fp);
      max_x = std::max(max_x, centers[i].x + r_fp);
      min_y = std::min(min_y, centers[i].y - r_fp);
      max_y = std::max(max_y, centers[i].y + r_fp);
    }
    // **搜索区 = 扫掠闭包 ∪ 当前位姿的 d_safety 邻域**。
    // 只搜扫掠闭包是不够的：距离档（SLOW / STOP_COLLISION / STOP_EMERGENCY）由"车体外缘到
    // 最近障碍的距离"定档，而该距离在低速时**远大于**制动距离 —— 只搜闭包会让"前方 3 m 有柱、
    // 我正慢慢挪"被判成 PASS（实测：v=0.5 时制动距离 0.29 m，柱子根本不在搜索区里）。
    // 两件事必须分开量：**净空**看邻域，**可停性**只看扫掠区。
    const double search_r = p.d_safety + r_fp;
    min_x = std::min(min_x, in.body.x - search_r);
    max_x = std::max(max_x, in.body.x + search_r);
    min_y = std::min(min_y, in.body.y - search_r);
    max_y = std::max(max_y, in.body.y + search_r);

    const MapView & m = in.map;
    const double extra = p.cell_epsilon;
    auto cellOf = [&](double x, double y, int * cx, int * cy) {
        const double fx = (x - m.origin_x) / m.resolution;
        const double fy = (y - m.origin_y) / m.resolution;
        if (fx < 0.0 || fy < 0.0) {return false;}
        const int ix = static_cast<int>(std::floor(fx));
        const int iy = static_cast<int>(std::floor(fy));
        if (ix < 0 || iy < 0 || ix >= m.width || iy >= m.height) {return false;}
        *cx = ix;
        *cy = iy;
        return true;
      };

    // 判据只在**地图内**成立；地图外按未知处理（不是"地图外就安全"）。
    // 先把包围盒换成格索引区间，再与地图求交；**求交为空即不可证明**。
    const double fx0 = (min_x - m.origin_x) / m.resolution;
    const double fy0 = (min_y - m.origin_y) / m.resolution;
    const double fx1 = (max_x - m.origin_x) / m.resolution;
    const double fy1 = (max_y - m.origin_y) / m.resolution;
    int gx0 = std::max(0, static_cast<int>(std::floor(fx0)));
    int gy0 = std::max(0, static_cast<int>(std::floor(fy0)));
    int gx1 = std::min(m.width - 1, static_cast<int>(std::floor(fx1)));
    int gy1 = std::min(m.height - 1, static_cast<int>(std::floor(fy1)));
    if (gx1 < gx0 || gy1 < gy0) {
      // 制动扫掠区完全落在地图外：没有任何已知自由能证明"停得住"。
      out->swept_unknown = true;
      out->unknown_ratio = 1.0;
      out->diag.swept_cells = 0;
      out->diag.swept_unknown = 0;
      out->diag.unknown_ratio = 1.0;
      out->diag.budget_ms = 0.0;
      out->diag.sweep_poses = out->poses;
      return "";
    }
    const long cells = static_cast<long>(gx1 - gx0 + 1) * static_cast<long>(gy1 - gy0 + 1);
    if (cells > p.sweep_cell_limit) {
      out->diag.swept_cells = cells;
      out->diag.sweep_poses = out->poses;
      return "sweep cells=" + std::to_string(cells) + " > limit=" +
             std::to_string(p.sweep_cell_limit);
    }

    long blocked = 0, unknown = 0, cost = 0;
    double d_min = std::numeric_limits<double>::infinity();
    int dmin_x = -1, dmin_y = -1;
    // 净空只按**当前**位姿量（不含制动轨迹）——"我看到它多远"与"我能不能停住"是两件事，
    // 混成一个量会让 STOP/SLOW 的归因分不清（前者是距离档，后者是可停性）。
    const double extra_half_diag = std::hypot(m.resolution * 0.5, m.resolution * 0.5);
    for (int iy = gy0; iy <= gy1; ++iy) {
      for (int ix = gx0; ix <= gx1; ++ix) {
        const size_t idx = static_cast<size_t>(iy) * static_cast<size_t>(m.width) +
          static_cast<size_t>(ix);
        const CellRisk risk = classifyCellRisk(static_cast<int>(m.data[idx]));
        if (risk == CellRisk::kFree) {continue;}
        Point2 pc;
        pc.x = m.origin_x + (static_cast<double>(ix) + 0.5) * m.resolution;
        pc.y = m.origin_y + (static_cast<double>(iy) + 0.5) * m.resolution;
        bool inside_sweep = false;
        for (size_t k = 0; k < centers.size(); ++k) {
          if (insideFootprint(
              pc, centers[k], yaws[k],
              p.footprint_half_length, p.footprint_half_width, extra))
          {
            inside_sweep = true;
            break;
          }
        }
        // 净空：车体外缘到**格中心**的距离再扣半格对角 —— 格的占据范围从它自己的边开始，
        // 用格中心会系统性高估净空（最多半个格对角），安全方向必须扣掉。
        double d0 = distanceToFootprint(
          pc, centers[0], yaws[0], p.footprint_half_length, p.footprint_half_width) -
          extra_half_diag;
        d0 = std::max(0.0, d0);
        if (d0 < d_min) {
          d_min = d0;
          dmin_x = ix;
          dmin_y = iy;
        }
        if (inside_sweep) {
          if (risk == CellRisk::kBlocked) {++blocked;}
          else if (risk == CellRisk::kUnknown) {++unknown;}
          else {++cost;}
        } else if (risk == CellRisk::kCost && d0 <= p.d_safety) {
          ++cost;   // 距离带内的代价格：只影响限速
        }
      }
    }

    out->swept_blocked = blocked > 0;
    out->swept_unknown = unknown > 0;
    out->swept_cost = cost > 0;
    const long seen = blocked + unknown;
    out->unknown_ratio = (seen > 0) ? static_cast<double>(unknown) / static_cast<double>(seen) : 0.0;
    out->d_min_m = std::isfinite(d_min) ? d_min : -1.0;
    out->d_min_cell_x = dmin_x;
    out->d_min_cell_y = dmin_y;

    // —— 方向化净空：只量「沿当前运动方向、车体宽度带内」的阻挡 ——
    //
    // 为什么不能再用各向同性的 `d_min_m` 定档（ADR-0047）：`d_min_m` 是"车体外缘到
    // **任意方向**最近阻挡格"的距离。用它当停车判据等于给车套一个**各向同性的圆形禁行区**：
    // 侧面 2 m 外有个柱子，即使车正笔直沿走廊走、永远不会碰到它，也会被判 `STOP_COLLISION`。
    // 实测后果（`dense_map`，面积覆盖仅 7.2%、相邻间隙中位数 4.54 m、车宽仅 0.57 m）：
    // 出生点侧向净空 1.75 m ⇒ 一启动即零速，整链 0 次到达。**几何上能过，判据不让过。**
    //
    // 口径（用户 2026-11-13 裁定）：
    // * 前方：按**当前运动方向**上的纵向间隙量（车体宽度带内），与 `d_collision` 比；
    // * 侧方：**不参与**定档 —— 它只在"当前转向/旋转会扫到它"时才生效，
    //   而那条路径已由上面的制动扫掠（含 ω 引起的偏航变化与纯旋转）覆盖；
    // * 原地旋转：扫掠位姿里 `psi` 随 ω 变化，纯旋转时 `travelled=0` 但朝向在转，
    //   ⇒ 车角扫到障碍仍判 `swept_blocked`（既有用例 `PureRotationIsAlsoConstrained` 守此）。
    //
    // `d_corridor_m < 0` 表示"运动方向上车体宽度带内没有任何阻挡"（= 无穷净空）。
    double d_corridor = -1.0;
    int cor_x = -1, cor_y = -1;
    const double v_cmd = in.command.v;
    if (std::fabs(v_cmd) > 1e-6 && !centers.empty()) {
      const double dir_sign = (v_cmd >= 0.0) ? 1.0 : -1.0;
      const double yaw0 = yaws[0];
      const double cy = std::cos(yaw0), sy = std::sin(yaw0);
      // 车体宽度带 + 离散误差：落在带外的格**不算**前方障碍。
      const double band = p.footprint_half_width + extra;
      for (int iy = gy0; iy <= gy1; ++iy) {
        for (int ix = gx0; ix <= gx1; ++ix) {
          const size_t idx = static_cast<size_t>(iy) * static_cast<size_t>(m.width) +
            static_cast<size_t>(ix);
          // `kCost`（1..98）是"有代价但可通行"，不是前方阻挡 —— 它只经 `swept_cost`
          // 参与限速，不参与走廊净空定档。
          const CellRisk risk_c = classifyCellRisk(static_cast<int>(m.data[idx]));
          if (risk_c == CellRisk::kFree || risk_c == CellRisk::kCost) {continue;}
          Point2 pc;
          pc.x = m.origin_x + (static_cast<double>(ix) + 0.5) * m.resolution;
          pc.y = m.origin_y + (static_cast<double>(iy) + 0.5) * m.resolution;
          const double dx = pc.x - centers[0].x, dy = pc.y - centers[0].y;
          const double u = dx * cy + dy * sy;    // 沿车头
          const double w_ = -dx * sy + dy * cy;  // 车体左侧
          if (std::fabs(w_) > band) {continue;}  // 侧向带外：不是前方障碍
          // 只取**运动方向**那一侧；反向的格不算前方。
          if (u * dir_sign <= 0.0) {continue;}
          const double gap = std::fabs(u) - p.footprint_half_length - extra_half_diag;
          const double g = std::max(0.0, gap);
          if (d_corridor < 0.0 || g < d_corridor) {
            d_corridor = g;
            cor_x = ix;
            cor_y = iy;
          }
        }
      }
    }
    out->d_corridor_m = d_corridor;
    out->d_corridor_cell_x = cor_x;
    out->d_corridor_cell_y = cor_y;

    out->diag.swept_cells = cells;
    out->diag.swept_blocked = blocked;
    out->diag.swept_unknown = unknown;
    out->diag.unknown_ratio = out->unknown_ratio;
    out->diag.sweep_poses = out->poses;
    out->diag.d_min_m = out->d_min_m;
    out->diag.d_min_cell_x = dmin_x;
    out->diag.d_min_cell_y = dmin_y;
    out->diag.d_corridor_m = out->d_corridor_m;
    out->diag.d_corridor_cell_x = cor_x;
    out->diag.d_corridor_cell_y = cor_y;
    out->diag.swept_has_cost = out->swept_cost;
    return "";
  }

  // 由几何量定档（不含迟滞）。
  //
  // **定档用方向化净空 `d_corridor`，不用各向同性的 `d_min_m`**（ADR-0047，用户 2026-11-13 裁定）。
  // `d_collision = 2.0 m` 的**数值与安全保证不变**，变的只是它**度量什么**：
  // 从"车周围 2 m 内有任何障碍就停"改为"沿当前运动方向、车体宽度带内，进入障碍前够不够停"。
  // 侧方障碍不再单独触发停车 —— 它只在当前转向/旋转会扫到它时才生效，而那条路径由
  // `swept_blocked` 覆盖（制动扫掠含 ω 引起的偏航变化与纯旋转）。
  SafetyState tierFromGeometry(
    const SweepResult & sw, double v, double w, std::string * reason) const
  {
    const SafetyParams & p = params_;
    // 各向同性净空仅用于**诊断**与"完全没看到东西"的判定；不参与定档。
    const double d_iso = sw.d_min_m;
    // 定档量：运动方向上的纵向间隙。
    // `d_corridor_m < 0` = 车体宽度带内**没有任何阻挡** ⇒ 前方净空为**无穷**，
    // 距离档（emergency / collision / slow）一律不成立。这一点必须显式表达：
    // 若退化去用各向同性的 `d_iso`，侧方 1.2 m 外的柱子照样会把车判成停车档，
    // 本次变更就等于没做（实测：穿缝用例报 `corridor d=0.866 < emergency`，
    // 而 0.866 正是侧方障碍的各向同性距离）。
    const bool corridor_known = (sw.d_corridor_m >= 0.0);
    const bool stationary = std::fabs(v) <= 1e-6 && std::fabs(w) <= 1e-6;
    // 定档量：
    // * 有运动方向且走廊带内有阻挡 → 用走廊净空；
    // * 有运动方向且走廊带内**无**阻挡 → 前方净空无穷，距离档不成立（本次变更的核心）；
    // * **静止**（v≈0 且 w≈0）→ 没有运动方向，退化为各向同性净空（保守，且保持既有判定表）。
    const double d = stationary ?
      ((d_iso < 0.0) ? std::numeric_limits<double>::infinity() : d_iso) :
      (corridor_known ? sw.d_corridor_m : std::numeric_limits<double>::infinity());
    const bool pure_rotation = std::fabs(v) <= 1e-6 && std::fabs(w) > 1e-6;

    // 未知占比超限：能停住的证据不足 ⇒ 不得放行。
    if (sw.unknown_ratio > p.unknown_ratio_limit) {
      *reason = "unknown ratio=" + fmt(sw.unknown_ratio);
      return SafetyState::kStopCollision;
    }
    // 制动扫掠区内有阻挡：**停不住** ⇒ 碰撞档（不是"减速能过"）。
    // 这条同时覆盖：直行撞前方、转向扫到侧方、原地旋转扫到车角。
    if (sw.swept_blocked) {
      *reason = "swept hit@(" + std::to_string(sw.d_min_cell_x) + "," +
        std::to_string(sw.d_min_cell_y) + ") d_iso=" + fmt(d_iso);
      return SafetyState::kStopCollision;
    }
    // 制动扫掠区内有未知：无法证明能停住 ⇒ 同样不得放行。
    if (sw.swept_unknown) {
      *reason = "swept unknown d_iso=" + fmt(d_iso);
      return SafetyState::kStopCollision;
    }
    if (d_iso < 0.0) {
      // 没有任何阻挡/未知格：图上全自由。
      *reason = "clear";
      return SafetyState::kPass;
    }
    // 纯旋转（无位移、只转向）：**碰撞**由旋转扫掠 `swept_blocked` 兜（车角扫到即停，
    // 见 `PureRotationIsAlsoConstrained` / `PureRotationIntoNearbyObstacleStillStops`）。
    // 距离档在这里只用来**限速**（旋转慢一点更安全），**不得**据此判停车 ——
    // 否则「原地转向时侧方 2 m 内有柱子」会变成零速，而车根本没在平移。
    // 也不得一律返回 SLOW：`SLOW` 会计入 `ticks_triggered`，在开阔区旋转会污染
    // `shield_infeasible_rate` 口径（那是"安全层介入"的代理量）。
    if (pure_rotation) {
      const double d_rot = (d_iso < 0.0) ?
        std::numeric_limits<double>::infinity() : d_iso;
      if (d_rot < p.d_safety) {
        *reason = "rotate slow d_iso=" + fmt(d_iso);
        return SafetyState::kSlow;
      }
      *reason = "rotate clear d_iso=" + fmt(d_iso);
      return SafetyState::kPass;
    }
    if (d < p.d_emergency) {
      *reason = "corridor d=" + fmt(d) + " < emergency (d_iso=" + fmt(d_iso) + ")";
      return SafetyState::kStopEmergency;
    }
    if (d < p.d_collision) {
      *reason = "corridor d=" + fmt(d) + " < collision (d_iso=" + fmt(d_iso) + ")";
      return SafetyState::kStopCollision;
    }
    if (d < p.d_safety) {
      *reason = "slow corridor d=" + fmt(d) + " (d_iso=" + fmt(d_iso) + ")";
      return SafetyState::kSlow;
    }
    if (sw.swept_cost) {
      *reason = "cost band";
      return SafetyState::kSlow;
    }
    (void)v;
    (void)w;
    *reason = "clear";
    return SafetyState::kPass;
  }

  // 恢复迟滞：从降级态回到 PASS 必须**连续** N 拍满足更高的门槛。
  SafetyState applyHysteresis(
    SafetyState geom, const SweepResult & sw, std::string * reason)
  {
    const SafetyParams & p = params_;
    if (isDegradedState(prev_state_) && geom == SafetyState::kPass) {
      // 恢复门槛用**方向化**净空（ADR-0047）：侧方障碍不应把车永久钉在降级态。
      //
      // `d_corridor_m < 0` 有**两个**互斥含义，必须区分，否则会造出"永远恢复不了"的死锁
      // （实测踩过：新出生位朝 +x 时走廊带内无阻挡 ⇒ -1，而旧代码把它当成"没有走廊数据"
      //  退化去用 `d_min_m = 4.00`，永远达不到 `d_recover_pass = 4.5` ⇒ 状态锁在 STOP_COLLISION）：
      // * 有运动方向时：**走廊带内无阻挡** = 前方净空**无穷** ⇒ 直接满足恢复门槛；
      // * 静止时（v≈0 ∧ w≈0）：走廊无定义，退化为各向同性 `d_min_m`。
      // **不要用 `sw.diag.v_raw` 判静止**：那是 `SafetyDecision::diag` 的字段，
      // `SweepResult::diag` 里**从未被赋值**（恒 0）⇒ `stationary` 恒为 true ⇒
      // 恢复永远退化用各向同性（实测：变异测试抓不住、真实图上锁死）。
      // 静止判据取 `sw.cmd_v` / `sw.cmd_w`（`evaluateSweep` 写入的输入命令）。
      const bool stationary = std::fabs(sw.cmd_v) <= 1e-6 && std::fabs(sw.cmd_w) <= 1e-6;
      double d = 0.0;
      if (sw.d_corridor_m >= 0.0) {
        d = sw.d_corridor_m;
      } else if (!stationary) {
        d = std::numeric_limits<double>::infinity();   // 走廊内无阻挡 = 无穷净空
      } else {
        d = (sw.d_min_m < 0.0) ? std::numeric_limits<double>::infinity() : sw.d_min_m;
      }
      const bool clean = !sw.swept_blocked && !sw.swept_unknown &&
        sw.unknown_ratio <= p.unknown_ratio_limit;
      if (clean && d >= p.d_recover_pass) {
        ++recover_count_;
        if (recover_count_ < p.recover_ticks) {
          *reason = "recover pending " + std::to_string(recover_count_) + "/" +
            std::to_string(p.recover_ticks);
          return prev_state_;
        }
      } else {
        recover_count_ = 0;
        return prev_state_;
      }
    } else {
      recover_count_ = 0;
    }
    return geom;
  }

  // 统一出口：非驱动态一律零速；驱动态做限幅与 SLOW 裁剪。
  SafetyDecision finish(SafetyDecision d, const SafetyInputs & in)
  {
    const SafetyParams & p = params_;
    if (!isDrivingState(d.state)) {
      d.out_v = 0.0;
      d.out_w = 0.0;
      prev_state_ = d.state;
      // **不得**在这里清恢复计数：`applyHysteresis` 返回的"仍在降级态"本身就带着
      // "已连续满足 N 拍"的进度，在这里清零会让恢复永远停在 1/N（实测过）。
      // 计数只在 `applyHysteresis` 的 else 分支（条件不成立 / 已不在降级态）里复位。
      return d;
    }
    const double v = clamp(in.command.v, p.v_cap);
    const double w = clamp(in.command.w, p.w_cap);
    if (d.state == SafetyState::kPass) {
      d.out_v = v;
      d.out_w = w;
    } else {
      // SLOW：线速度与角速度按**同一比例**收缩（保持曲率），比例由**方向化**净空线性插值。
      // 必须用 `d_corridor_m` 而不是各向同性的 `d_min_m`：否则侧方 2 m 外的柱子会让
      // 车在开阔直道上无故减速（ADR-0047）。走廊带内无阻挡（<0）时视为满速。
      const double dcorr = d.diag.d_corridor_m;
      const double dmin = (dcorr >= 0.0) ? dcorr : d.diag.d_min_m;
      double ratio = p.slow_min_ratio;
      if (dmin >= 0.0) {
        const double span = std::max(1e-6, p.d_safety - p.d_collision);
        ratio = (dmin - p.d_collision) / span;
        ratio = std::min(1.0, std::max(p.slow_min_ratio, ratio));
      } else {
        ratio = 1.0;   // 走廊内无阻挡：不因侧方障碍降速
      }
      d.out_v = clamp(v * ratio, p.v_cap);
      d.out_w = clamp(w * ratio, p.w_cap);
      if (d.reason.empty() || d.reason == "clear") {d.reason = "slow";}
    }
    prev_state_ = d.state;
    have_ever_driven_ = true;
    return d;
  }

  static double clamp(double v, double cap)
  {
    if (!std::isfinite(v)) {return 0.0;}
    return std::max(-cap, std::min(cap, v));
  }

  SafetyParams params_;
  std::string params_error_;
  SafetyState prev_state_{SafetyState::kStartup};
  int recover_count_{0};
  bool have_ever_driven_{false};
};

}  // namespace agc_ground

#endif  // AGC_GROUND__SAFETY_POLICY_HPP_
