// agc_air/safety_shield.cpp —— 联合安全屏障（联合约束复检 + 扫掠复检 + 显式不可行路径）

#include "agc_air/safety_shield.hpp"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include "agc_control/param_reader.hpp"

namespace agc_air
{

namespace
{
/// 联合投影迭代预算：足够收敛单盘 / 相容盘组；**不**收敛即判「不可行」（见 非交换投影）。
constexpr int kMaxProjectIters = 64;

/// ：联合约束（XY 圆盘）—— 静态障碍与目标间距**同时**生效的约束项。
/// ADR-0010「垂直门控」起带 `is_target`：仅用于**判定阶段归因**（哪个圆盘导致介入），
/// 不参与几何计算（几何仍只看 `x/y/r`）。
struct Disk
{
  double x;
  double y;
  double r;
  bool is_target;
};

/// `RingSet` → 内部 `Disk` 视图（生产与单测走**同一条**转换，避免测试复制投影逻辑）。
std::vector<Disk> toDisks(const RingSet & rs)
{
  std::vector<Disk> ds;
  ds.reserve(rs.rings.size());
  for (const auto & r : rs.rings) {
    ds.push_back(Disk{r.x, r.y, r.r, r.is_target});
  }
  return ds;
}

/// 点到线段 [a,b] 的最短距离（XY）—— 扫掠净空判据。
double pointSegDist(double px, double py, double ax, double ay, double bx, double by)
{
  const double dx = bx - ax;
  const double dy = by - ay;
  const double len2 = dx * dx + dy * dy;
  double t = 0.0;
  if (len2 > 1e-12) {
    t = ((px - ax) * dx + (py - ay) * dy) / len2;
    t = std::clamp(t, 0.0, 1.0);
  }
  return std::hypot(px - (ax + t * dx), py - (ay + t * dy));
}

/// 端点可行性：点 (x,y) 是否同时位于**全部**约束圆盘之外；可回传最严重违约项下标。
bool feasibleXY(const std::vector<Disk> & ds, double x, double y, std::size_t * worst)
{
  double worst_viol = 0.0;
  std::size_t wi = ds.size();
  for (std::size_t i = 0; i < ds.size(); ++i) {
    const double d = std::hypot(x - ds[i].x, y - ds[i].y);
    if (d < ds[i].r - 1e-9) {
      const double v = ds[i].r - d;
      if (v > worst_viol) {worst_viol = v; wi = i;}
    }
  }
  if (worst) {*worst = wi;}
  return wi == ds.size();
}

/// 单约束径向推出：把点推到距圆心 ≥ r（退化时沿 +x）。
void pushOut(double & x, double & y, double cx, double cy, double r)
{
  const double dx = x - cx;
  const double dy = y - cy;
  const double d = std::hypot(dx, dy);
  if (d >= r) {return;}
  if (d < 1e-6) {x = cx + r; y = cy; return;}
  x = cx + dx / d * r;
  y = cy + dy / d * r;
}

/// 联合投影：反复推出**全部**违约约束，直至同时满足（收敛）或耗尽预算。
/// 与旧实现的差别：**不**做"逐障碍 + 目标"的**单遍**投影即返回——单遍后投影可重新落入前约束
/// （投影不可交换， 病灶）；本函数**重复复检**，耗尽预算仍未同时满足即判不可行。
bool projectJointFeasible(const std::vector<Disk> & ds, double & x, double & y)
{
  for (int it = 0; it < kMaxProjectIters; ++it) {
    bool any_violation = false;
    for (const auto & d : ds) {
      if (std::hypot(x - d.x, y - d.y) < d.r - 1e-9) {
        pushOut(x, y, d.x, d.y, d.r);
        any_violation = true;
      }
    }
    if (!any_violation) {return true;}
  }
  return feasibleXY(ds, x, y, nullptr);
}

/// 端点是否落在**任一**圆盘内（`want_target=true` 只看目标盘，false 只看障碍盘）。
/// 仅用于 `apply` 的**归因**（reason 拆分），不改变任何几何判定。
bool pointInsideAny(const std::vector<Disk> & ds, double x, double y, bool want_target)
{
  for (const auto & d : ds) {
    if (d.is_target != want_target) {continue;}
    if (std::hypot(x - d.x, y - d.y) < d.r - 1e-9) {return true;}
  }
  return false;
}

/// 扫掠复检：当前位置 → 参考端点 的直线段是否穿入任一**起点在外**的约束圆盘。
/// 起点已在圆盘内的约束跳过（那属于"自当前位置逃出"，由不可行路径处理，而非扫掠冲突）。
bool sweptClear(
  const std::vector<Disk> & ds,
  double ax, double ay, double bx, double by, std::size_t * hit)
{
  for (std::size_t i = 0; i < ds.size(); ++i) {
    const double da = std::hypot(ax - ds[i].x, ay - ds[i].y);
    if (da < ds[i].r) {continue;}
    if (pointSegDist(ds[i].x, ds[i].y, ax, ay, bx, by) < ds[i].r - 1e-9) {
      if (hit) {*hit = i;}
      return false;
    }
  }
  return true;
}
}  // namespace

void SafetyShield::configure_parameters(
  rclcpp::node_interfaces::NodeParametersInterface::SharedPtr params, const std::string & ns)
{
  agc_control::NodeParamReader p(std::move(params), ns);

  enabled_ = p.getBool("enabled", true);
  target_min_dist_ = p.getDouble("target_min_dist", 8.0);
  obstacle_margin_m_ = p.getDouble("obstacle_margin", 2.5);
  target_margin_m_ = p.getDouble("target_margin", 1.5);
  // 跟踪误差 / 反应时间 / 可达性余量（配置项承载；绝对值为可标定量）
  reaction_time_s_ = p.getDouble("reaction_time_s", 0.2);
  max_speed_mps_ = p.getDouble("max_speed_mps", 2.0);
  reachability_margin_m_ = p.getDouble("reachability_margin", 0.3);
  // ADR-0010「垂直门控」：c_clear 与地图 `flight_altitude.own_clearance_min_m` 同源注入。
  vertical_clearance_m_ = p.getDouble("vertical_clearance_m", 0.5);
  if (!std::isfinite(vertical_clearance_m_) || vertical_clearance_m_ < 0.0) {
    std::ostringstream oss;
    oss << "安全层垂直净空非法（拒绝启动）：vertical_clearance_m=" << vertical_clearance_m_
        << "（要求有限且 ≥ 0）";
    throw std::runtime_error(oss.str());
  }

  const auto names = p.getStringArray("obstacle_names");
  const auto xs = p.getDoubleArray("obstacle_x");
  const auto ys = p.getDoubleArray("obstacle_y");
  const auto rs = p.getDoubleArray("obstacle_safety_radius");
  // ADR-0010「垂直门控」：第五个平行数组。**缺省为空** = 全部障碍顶高未知 → 门控永不生效
  // （保守退化为无限高圆柱，与旧行为逐值一致）；**不是**缺省 0——那会让所有障碍静默失效。
  const auto zs = p.getDoubleArray("obstacle_z_top");

  // （见 ADR-0009）：障碍表为**平行数组**，五者长度**必须一致**。
  // **删除**旧的 `n=min({...})` 静默按最短长度截断 —— 漏配一个数组会**静默漏障碍**；
  // 改为一律**拒绝**（抛错 → configure 失败 → 生命周期 error 路径接管；**不**静默运行）。
  // `obstacle_z_top` 只在**非空**时参与等长校验（standalone / 单测可不提供 → 门控不生效）。
  if (names.size() != xs.size() || names.size() != ys.size() || names.size() != rs.size() ||
    (!zs.empty() && names.size() != zs.size()))
  {
    std::ostringstream oss;
    oss << "安全层障碍平行数组长度不一致（拒绝启动）：obstacle_names=" << names.size()
        << " obstacle_x=" << xs.size() << " obstacle_y=" << ys.size()
        << " obstacle_safety_radius=" << rs.size() << " obstacle_z_top=" << zs.size()
        << "；五者必须相等（obstacle_z_top 可整体缺省；不静默按最短长度截断）。";
    throw std::runtime_error(oss.str());
  }

  obstacles_.clear();
  for (std::size_t i = 0; i < names.size(); ++i) {
    // 几何合法性 —— 半径必须有限且 > 0，坐标必须有限；非法一律**拒绝**。
    if (!std::isfinite(rs[i]) || rs[i] <= 0.0) {
      std::ostringstream oss;
      oss << "安全层障碍几何非法（拒绝启动）：obstacle_safety_radius[" << i << "]=" << rs[i]
          << "（要求有限且 > 0）";
      throw std::runtime_error(oss.str());
    }
    if (!std::isfinite(xs[i]) || !std::isfinite(ys[i])) {
      std::ostringstream oss;
      oss << "安全层障碍几何非法（拒绝启动）：obstacle_x[" << i << "]=" << xs[i]
          << " obstacle_y[" << i << "]=" << ys[i] << "（要求有限）";
      throw std::runtime_error(oss.str());
    }
    // ADR-0010：顶高必须有限且 > 0（**拒绝** NaN/±Inf 与 ≤0——顶高 0 会让门控在任何高度都生效）。
    double z_top = std::numeric_limits<double>::infinity();
    if (!zs.empty()) {
      if (!std::isfinite(zs[i]) || zs[i] <= 0.0) {
        std::ostringstream oss;
        oss << "安全层障碍几何非法（拒绝启动）：obstacle_z_top[" << i << "]=" << zs[i]
            << "（要求有限且 > 0；顶高未知时**整体省略**该数组，逐项不允许坏值）";
        throw std::runtime_error(oss.str());
      }
      z_top = zs[i];
    }
    obstacles_.push_back(StaticObstacle{names[i], xs[i], ys[i], rs[i], z_top});
  }
}

RingSet SafetyShield::deriveRings(
  const agc_control::Vector3 & current_pos,
  const agc_control::Vector3 & current_vel,
  const agc_control::Vector3 & target_pos, bool target_valid) const
{
  // 垂直门控（ADR-0010）：判据含**下降前视**——以当前垂直速度再看 reaction_time_s 秒。
  // descend_rate = max(−v_z, 0)：下降（v_z < 0）时把判定高度**降到** `τ` 秒后的高度
  // → 圆盘在**到达之前**即复活。上升 / 平飞时 descend_rate = 0（判据不用上升速度）。
  // 用 `current_pos.z`（实际高度）而**不是**参考高度：本层是参考滤波器，参考比实际超前，
  // 用参考会让圆盘在不该失效时失效（LQR 滞后余量已在 dynamicMargin 中）。
  const double descend_rate = std::max(-current_vel.z(), 0.0);
  const double z_gate = current_pos.z() - descend_rate * reaction_time_s_;

  const double extra = dynamicMargin();
  RingSet rs;
  rs.gate_height_m = z_gate;
  rs.rings.reserve(obstacles_.size() + 1);
  for (const auto & ob : obstacles_) {
    // 顶面 + 净空 ≤ 判定高度 ⇒ 本机已在障碍上方 → 该障碍的水平圆盘**不生效**。
    if (z_gate >= ob.z_top + vertical_clearance_m_) {
      ++rs.gated_off;
      continue;
    }
    rs.rings.push_back(RingSet::Ring{ob.x, ob.y, ob.safety_radius + obstacle_margin_m_ + extra,
        false});
  }
  if (target_valid) {
    // ⚠ 目标间距圆盘**不参与门控**：否则抬高高度即可无限接近目标，K1 视场 / 捕获几何会失效。
    rs.rings.push_back(RingSet::Ring{target_pos.x(), target_pos.y(),
        target_min_dist_ + target_margin_m_ + extra, true});
    rs.target = 1;
  }
  rs.obstacles = static_cast<std::int32_t>(rs.rings.size()) - rs.target;
  return rs;
}


SafetyResult SafetyShield::apply(
  const agc_control::Reference & desired,
  const agc_control::Vector3 & current_pos,
  const agc_control::Vector3 & current_vel,
  const agc_control::Vector3 & target_pos, bool target_valid) const
{
  SafetyResult out;
  out.ref = desired;
  out.reason = "clear";
  if (!enabled_) {return out;}

  // 联合约束集（XY 圆盘）：静态障碍约束 **与** 目标间距约束 **同时** 生效。
  // ⚠ 二维静态限定模型（**限实验用途**）：仅含 XY 静态圆盘；**不含**车 / 动态障碍状态
  // （动态障碍状态 = unsupported），**不**建模三维机体外形 / 载荷外伸。
  // 修正后边界 = 真实安全半径 + 跟踪误差 + 反应 + 可达性余量。
  // ADR-0010「垂直门控」：圆盘集由 `deriveRings` 构建（含垂直门控 + 归因），此处不再手搓。
  const RingSet rings = deriveRings(current_pos, current_vel, target_pos, target_valid);
  out.rings_obstacles = rings.obstacles;
  out.rings_gated_off = rings.gated_off;
  out.rings_target = rings.target;
  out.gate_height_m = rings.gate_height_m;
  const std::vector<Disk> disks = toDisks(rings);
  if (disks.empty()) {return out;}

  const double cx = current_pos.x();
  const double cy = current_pos.y();

  // ① 候选参考：期望端点；端点不可行时先做**联合投影**（重复复检，非单遍）
  double qx = desired.pos.x();
  double qy = desired.pos.y();
  const bool endpoint_ok = feasibleXY(disks, qx, qy, nullptr);
  if (!endpoint_ok) {projectJointFeasible(disks, qx, qy);}

  // ② 终检：候选端点**同时**满足全部约束 **且** 当前位置→候选端点 的直线段不穿约束
  std::size_t swept_hit = disks.size();
  const bool final_endpoint_ok = feasibleXY(disks, qx, qy, nullptr);
  const bool final_swept_ok = sweptClear(disks, cx, cy, qx, qy, &swept_hit);

  if (final_endpoint_ok && final_swept_ok) {
    if (std::hypot(qx - desired.pos.x(), qy - desired.pos.y()) > 1e-6) {
      out.modified = true;
      // 归因（**不改语义**，只把 `adjusted` 拆成可分辨的两类）：
      // 期望端点就落在某目标圆盘内 → 目标盘；否则是障碍盘。两者都是"介入"，
      // 但「目标间距盘导致」与「避障导致」的调参方向完全相反，必须能分开看。
      out.reason = pointInsideAny(disks, desired.pos.x(), desired.pos.y(), true) ?
        "adjusted_target" : "adjusted_obstacle";
      out.ref.pos.x() = qx;
      out.ref.pos.y() = qy;
      // 去掉指向各约束中心的速度分量（不再朝里飞）
      for (const auto & d : disks) {
        const double dx = out.ref.pos.x() - d.x;
        const double dy = out.ref.pos.y() - d.y;
        const double dist = std::hypot(dx, dy);
        if (dist > 1e-6 && dist <= d.r + 1e-6) {
          const agc_control::Vector3 inward(-dx / dist, -dy / dist, 0.0);
          const double v_in = out.ref.vel.dot(inward);
          if (v_in > 0.0) {out.ref.vel -= inward * v_in;}
        }
      }
    }
    return out;
  }

  // ③ **显式不可行**：无可行参考 → simple hold / escape（**不**返回可能不可达参考）
  out.modified = true;
  out.infeasible = true;
  out.reason = endpoint_ok ? "infeasible_swept" : "infeasible_joint";

  double hx = cx;
  double hy = cy;
  if (feasibleXY(disks, hx, hy, nullptr)) {
    // hold：当前机体位置本身安全 → 保持当前位置
    out.ref.pos.x() = hx;
    out.ref.pos.y() = hy;
    out.action = "hold";
  } else {
    double ex = hx;
    double ey = hy;
    if (projectJointFeasible(disks, ex, ey)) {
      // escape：自当前机体位置逃到最近可行点（远离冲突障碍）
      out.ref.pos.x() = ex;
      out.ref.pos.y() = ey;
      out.action = "escape";
    } else {
      // 连联合投影亦不收敛：对**最严重违约**约束做单约束径向推出（保证该约束净空）
      std::size_t worst = disks.size();
      feasibleXY(disks, hx, hy, &worst);
      const Disk & d = disks[(worst == disks.size()) ? 0 : worst];
      pushOut(hx, hy, d.x, d.y, d.r);
      out.ref.pos.x() = hx;
      out.ref.pos.y() = hy;
      out.action = "escape";
    }
  }
  // 显式不可行路径：速度 / 加速度前馈清零（安全 hold / 逃逸，不给 LQR 追逐不可达参考）
  out.ref.vel = agc_control::Vector3::Zero();
  out.ref.acc = agc_control::Vector3::Zero();
  return out;
}

}  // namespace agc_air
