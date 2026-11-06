// agc_air/safety_shield.hpp —— 机载安全层（spec R7 + R-033 联合安全屏障）
//
// 职责（不引入 Nav2 运行时进程；ADR-0003 空中域保留 LQR + 自研避障）：
//   ① **联合约束复检**：静态障碍约束 **与** 目标间距约束**同时**满足（不允许后投影重新落入前约束）；
//   ② **扫掠复检**：当前位置 → 参考端点 的直线段不得穿入约束（不只检端点）；
//   ③ **显式不可行路径**（R-033）：无可行参考 → **简单可验证的 hold / 逃逸**（保持当前位置安全 /
//      远离冲突障碍），**不**静默返回可能不可达参考（本批**不**引入 QP / CBF）；
//   ④ 预留 RL 偏移接口（默认零偏，W7 填充；对齐旧 `/rl_planner/local_offset` 的"局部偏移"语义）。
//   ⑤ **垂直门控**（ADR-0010「垂直门控」）：本机实际高度已高于某静态障碍的**顶面 + 垂直净空**时，
//      该障碍的水平圆盘对本机**不生效**（"从楼上飞过去"）；判据含**下降速度前视**，故下降穿越
//      顶面时圆盘在**到达之前**即复活（不依赖状态机 / 滞回）。
//
// ⚠ **限定模型声明（R-033）**：本层是**二维静态圆盘屏障**，仅作**限定实验模型**：
//   - 只处理 XY 平面的静态障碍圆盘 + 目标间距圆盘；
//   - **不含**车 / 动态障碍状态（`/agc/obstacles/source` 动态障碍、他机运动状态**不支持** → 记账 `unsupported`）；
//   - **不**建模三维机体外形 / 载荷外伸 / 网几何。
//   故**不得**据本层把二维立柱世界的结论推广为三维通用安全保证。

#pragma once

#include <limits>
#include <string>
#include <vector>

#include <rclcpp/node_interfaces/node_parameters_interface.hpp>

#include "agc_control/types.hpp"

namespace agc_air
{

struct StaticObstacle
{
  std::string name;
  double x{0.0};
  double y{0.0};
  double safety_radius{2.0};
  /// 顶面高度（世界 ENU，m）。`+inf` = **未知**，等价于"无限高圆柱"（门控永不生效）。
  /// 未注入时用 `+inf` 而非 0：缺省 0 会让所有障碍在正常巡航高度下静默失效（R-038 同类病灶）。
  double z_top{std::numeric_limits<double>::infinity()};
};

/// R-033：安全层输出 —— 联合复检结果 + **显式不可行路径**。
struct SafetyResult
{
  agc_control::Reference ref;   ///< 修正后的参考（世界系 ENU）
  bool modified{false};         ///< 是否被修正（避障 / 间距 / 不可行）
  bool infeasible{false};       ///< 联合约束复检未收敛（无可行参考）→ **显式不可行**
  /// "clear" | "adjusted_obstacle" | "adjusted_target"（**归因**，见 deriveRings）|
  /// "infeasible_joint" | "infeasible_swept"
  std::string reason;
  std::string action;           ///< "" | "hold" | "escape"（不可行时的**明确安全动作**）
  /// 垂直门控诊断（ADR-0010）：生效障碍数 / 被门控移除数 / 目标盘数 / 判定高度。
  std::int32_t rings_obstacles{0};
  std::int32_t rings_gated_off{0};
  std::int32_t rings_target{0};
  double gate_height_m{0.0};
};

/// 单拍约束集构建结果（**纯函数**，供 `apply()` 与单测共用；避免测试复制生产逻辑）。
struct RingSet
{
  struct Ring
  {
    double x;
    double y;
    double r;
    bool is_target;
  };
  std::vector<Ring> rings;
  std::int32_t obstacles{0};   ///< 参与本拍的静态障碍圆盘数
  std::int32_t gated_off{0};   ///< 因**垂直门控**而**移除**的障碍数
  std::int32_t target{0};      ///< 目标间距圆盘（0/1）
  /// 本拍**实际用于判定**的高度 `z_ref − v_z_up·reaction_time_s`（诊断 / 单测可观测）。
  double gate_height_m{0.0};
};

class SafetyShield
{
public:
  /// 读参数（障碍表以**平行数组**给出）；由 launch 单一设置
  void configure_parameters(rclcpp::node_interfaces::NodeParametersInterface::SharedPtr params,
    const std::string & ns);

  /// 对期望参考施加安全修正（R-033 联合复检 + 显式不可行）：
  ///   - `desired`：期望参考（世界系 ENU）
  ///   - `current_pos`：机体**当前位置**（世界系 ENU；供扫掠复检与 hold / 逃逸）
  ///   - `current_vel`：机体**当前速度**（世界系 ENU）——垂直门控只用其 **z 分量**做下降前视
  ///   - `target_pos` / `target_valid`：目标位置（用于最小间距兜底）
  ///
  /// 注：本层是**参考滤波器**，其输出由 LQR 跟踪，故机体实际位置相对参考存在跟踪滞后。
  /// `obstacle_margin` / `target_margin` 即为该滞后（跟踪误差）预留的余量；**另加**反应时间
  /// （`reaction_time_s × max_speed_mps`）与可达性余量（`reachability_margin`）——三者**分别**
  /// 由配置项承载（R-033：跟踪误差 / 反应时间 / 可达性）。修正后参考边界 = 真实安全半径 + 余量，
  /// 使**机体实际**不侵入真实安全半径（对齐契约 C6 与 C10 自保）。
  SafetyResult apply(const agc_control::Reference & desired,
    const agc_control::Vector3 & current_pos,
    const agc_control::Vector3 & current_vel,
    const agc_control::Vector3 & target_pos, bool target_valid) const;

  /// 单拍约束集构建（**纯函数**）：把障碍表 + 目标间距 + 当前高度/垂直速度 → 生效圆盘集。
  ///
  /// 垂直门控（ADR-0010）：障碍 `o` 被移除 iff
  ///   `z_ref − max(−v_z, 0) · reaction_time_s ≥ z_top(o) + vertical_clearance_m`，
  /// 其中 `z_ref = current_pos.z()`（**实际**高度，不是参考高度——本层是参考滤波器，用参考会提前失效），
  /// `max(−v_z, 0)` = **下降速率**（下降前视：以当前下降速率再看 `reaction_time_s` 秒后的高度；
  /// 上升 / 平飞时该项为 0，判据**不**因上升而放宽）。
  /// ⇒ 下降穿越顶面的瞬间之前，圆盘已复活，**不依赖**状态机 / 滞回。
  ///
  /// `vertical_clearance_m` 与地图 `flight_altitude.own_clearance_min_m` **同源**（K3）。
  /// ⚠ 门控**只作用于静态障碍圆盘**，目标间距圆盘**始终生效**（否则抬高即可无限接近目标）。
  RingSet deriveRings(const agc_control::Vector3 & current_pos,
    const agc_control::Vector3 & current_vel,
    const agc_control::Vector3 & target_pos, bool target_valid) const;

  const std::vector<StaticObstacle> & obstacles() const {return obstacles_;}
  bool enabled() const {return enabled_;}
  double targetMinDist() const {return target_min_dist_;}
  double obstacleMargin() const {return obstacle_margin_m_;}
  double targetMargin() const {return target_margin_m_;}
  // R-033：跟踪误差 / 反应时间 / 可达性余量（配置项承载）
  double reactionTime() const {return reaction_time_s_;}
  double maxSpeed() const {return max_speed_mps_;}
  double reachabilityMargin() const {return reachability_margin_m_;}
  /// 反应 + 可达性合计余量（m）：reaction_time × max_speed + reachability_margin
  double dynamicMargin() const
  {
    return reaction_time_s_ * max_speed_mps_ + reachability_margin_m_;
  }

private:
  std::vector<StaticObstacle> obstacles_;
  bool enabled_{true};
  double target_min_dist_{8.0};
  double obstacle_margin_m_{2.5};      ///< 跟踪误差（LQR 滞后）余量
  double target_margin_m_{1.5};
  // R-033：反应时间 / 可达性余量（配置项承载；绝对值为**可标定量**，见 ADR-0010）
  double reaction_time_s_{0.2};
  double max_speed_mps_{2.0};
  double reachability_margin_m_{0.3};
  /// ADR-0010「垂直门控」：垂直净空下限 c_clear（m）。运行期与地图
  /// `flight_altitude.own_clearance_min_m` **同源注入**；此处缺省值仅作脱机单测兜底。
  double vertical_clearance_m_{0.5};
};

}  // namespace agc_air
