#!/usr/bin/env python3
"""intruder_driver —— 入侵者 PX4 脚本化驱动（episode 起点协议见 ADR-0014）。

入侵者为**第二个 PX4 SITL 实例**（attach 到模型 `intruder_uav`）。本节点经 uXRCE / `px4_msgs`
以 Offboard 驱动其运动：`static`（悬停）/ `linear`（匀速直线）/ `maneuver`（圆周机动）/
`epicycle`（**漂移轨道**，ADR-0031：绕 `radius_m` 圆轨道转、圆心以 `drift_amplitude_m` /
`drift_period_s` 缓慢漂移）。
仅命令**入侵者**，不触碰己方机 / 车（契约 [唯一执行口]）。

话题：`/<ns>/fmu/{in,out}/*`（ns 由 launch 单一设置，默认 `px4_1`）。
NED 约定：PX4 本地系为 NED（z 向下），故高度目标用 `-cruise_alt_m`（相对 **episode 原点**，
见 ADR-0014：`origins_` 取 epoch 后首帧 odom；它**不是**世界 ENU 高度）。

H0（2026-11-02）高度语义：`cruise_alt_m` 是**唯一**巡航高度输入，语义 = 相对 episode 原点的
上升量（m，向上为正）。`alt_m` 仅为**弃用别名**；两者同时显式且不等 → 拒绝启动。
**绝对世界巡航高度 = 原点世界高度 + cruise_alt_m**，而原点世界高度由 EKF 初始化决定、
跨 run 不可复现（实测 `gt_z − (−ned_z)` 在 −0.50…+0.44 m 漂移）——故**不得**把本参数当世界高度。
世界放置值见 `config/spawn_layout.yaml` 的 `target.z`（PX4 attach 前的瞬态，不是巡航高度）。

 episode 起点协议（ADR-0014）：
 * **预热独立于 episode 计时**：节点启动即记 `warmup_t0_`；`tw = now - warmup_t0_`，`tw > 1 s` 才请求
    ARM，已解锁且非 OFFBOARD(`14`) 则请求 `SET_NAV_STATE=OFFBOARD`（按 `arm_retry_s` 重试）。
 **预热时间不进入轨迹参数 t**。
 * **episode epoch**：订阅 `<epoch_topic>`（`std_msgs/Int32`，depth1 + RELIABLE + TRANSIENT_LOCAL）。
 **epoch 值变化 = 新 episode**：重锚 `origins_`（下条 odom）、清 `t0_`、清干扰态、解终止、置 `episode_armed_`。
  * **起点协议**：预热 → 进入起始位姿（`_target(0)`）→ 确认稳定（`dist(pos, start) <= start_tol_m`
 且 `speed <= start_vel_eps_mps` 持续 `start_dwell_s`）→ 记 `t0_`（episode t=0）。
 **未进入 episode（`t0_ is None`）setpoint 恒定 = 起始位姿（悬停保持，不推进）**。
 * **切入 / 运行区边界**：`maneuver` 的 t=0 setpoint 落在圆周定义点 `(ox+r, oy)`（不从原点起跳）；
 `epicycle` 的 t=0 setpoint 落在 `(ox+r, oy+A)`（同样是定义点，`sin0=0/cos0=1`）；
 setpoint 水平离原点超过 `run_region_radius_m`（>0 生效）→ 夹持到边界并置 `terminated_`（越界终止，不外推）。
 **起点协议与"切线速度非零"不冲突**（ADR-0031）：`t0_ is None` 期间发的是 `_start_pose`（常量），
 机体收敛到该点后 `speed → 0`，故 `speed <= start_vel_eps_mps` 仍能满足；
 轨迹的切线速度只在 `t0_` 记录**之后**才被真正执行。
 * **CLEAR 重基准**：干扰解除时把暂停时长加回 `t0_`，使参考从干扰发生时刻**连续**续上（不跳变）。

（ADR-0015）：干扰授权收敛到**单一裁决者** `jammer`。本节点**只消费**其产出的**已校验授权事件**
（`/agc/task/jam_state`，`std_msgs/String`）；**不直订**任何原始干扰命令话题（原直订路径已移除）。
`jammed_`（→ 停发 Offboard 流）**仅由该已校验事件驱动**。（ADR-0015）：停发 Offboard 流触发
PX4 的 **offboard-loss** 行为（由运行时锁定的 `COM_OF_LOSS_T` / `COM_OBL_RC_ACT` 决定），**非**
data-link-loss（`NAV_DLL_ACT`）；二者为不同机制，本节点不主张「数据链被切断」。
"""

import math

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)

from px4_msgs.msg import (
    OffboardControlMode,
    TrajectorySetpoint,
    VehicleCommand,
    VehicleOdometry,
    VehicleStatus,
)
from std_msgs.msg import Int32, String

OFFBOARD_NAV_STATE = VehicleStatus.NAVIGATION_STATE_OFFBOARD  # 14


def _qos():
    """PX4 uXRCE-DDS 的 `/fmu/out/*` writer QoS：**BEST_EFFORT + TRANSIENT_LOCAL**。

 ⚠ 2026-11-03 实测定案（H0 回归）：本函数原先**漏了 durability**，默认 `VOLATILE`。
 ROS 2 的 QoS 兼容规则要求「订阅者 durability **不得低于**发布者」，故
 `VOLATILE` 订阅 `TRANSIENT_LOCAL` 发布者是**不兼容**的——**静默收不到任何数据**
 （不报错、不告警，`create_subscription` 照样成功）。

 症状与代价（s04 抬高度 run `20261103-093912`）：
 `px4_1` 的 odom 以 87 Hz 正常发布，话题 `/px4_1/fmu/out/vehicle_odometry` 存在，
 但 `intruder_driver._on_odom` **一次都没触发** → `origins_` 恒 None → `_tick` 每拍
 静默 return → 永不 ARM → 目标机停在地面 → 任务 3 分钟后才以 AIR_SEARCH 暴露。
 （2026-11-03 更正：旧注释写"三维距离恒 ≥ 14 m > `range_max_m=12` → 感知恒盲"，
 该诊断特征**已失效**——量程改为 30.0 后，目标停地面时
 √(26.17² + 14²) = 29.68 m **仍在量程内**（余量仅 0.32 m），感知照样能看见。
 故"目标未起飞"**只能**靠本节点自己的 `have_odom` 日志判定，
 **不得**再指望感知致盲来间接暴露。）

    对照实现：C++ 侧 `px4_adapter` 用 `rclcpp::SensorDataQoS()`（BEST_EFFORT +
 TRANSIENT_LOCAL，已正确），其注释也写明「订阅端必须同档，否则 QoS 不兼容、收不到数据」。
 Python 侧手抄 QoS 时漏了同一项 —— 这就是"两处各写一份"的代价。
    """
    q = QoSProfile(depth=5)
    q.reliability = ReliabilityPolicy.BEST_EFFORT
    q.durability = DurabilityPolicy.TRANSIENT_LOCAL
    q.history = HistoryPolicy.KEEP_LAST
    return q


def _epoch_qos():
    """epoch 订阅 QoS —— depth=1 + RELIABLE + TRANSIENT_LOCAL（对齐 scenario_reset 发布端）。"""
    q = QoSProfile(depth=1)
    q.reliability = ReliabilityPolicy.RELIABLE
    q.history = HistoryPolicy.KEEP_LAST
    q.durability = DurabilityPolicy.TRANSIENT_LOCAL
    return q


class IntruderDriver(Node):
    def __init__(self):
        super().__init__('intruder_driver')
        self.ns_ = self.declare_parameter('px4_ns', 'px4_1').value
        self.motion_ = self.declare_parameter('motion', 'static').value
        # ---- H0（2026-11-02）：巡航高度**单一权威输入** ----
        # `cruise_alt_m` = 目标相对 **episode 原点** 的巡航高度（m，向上为正）；这是唯一有效来源。
        # `alt_m` 降级为**弃用别名**（旧配置/历史 run 兼容），仅在 `cruise_alt_m` 未显式给出时生效。
        # 二者**同时显式给出且不相等** → 拒绝启动：那正是 H0 要消除的"两个同值参数各自承担语义"。
        self.cruise_alt_m_ = float(self.declare_parameter('cruise_alt_m', float('nan')).value)
        self.alt_m_alias_ = float(self.declare_parameter('alt_m', float('nan')).value)
        self.alt_m_ = self._resolve_cruise_alt()
        self.v_ = self.declare_parameter('speed_mps', 1.0).value
        self.radius_ = self.declare_parameter('radius_m', 6.0).value
        # ---- ADR-0031：`epicycle`（漂移轨道）的两个专有参数 ----
        # ⚠ 命名纪律：`drift_amplitude_m` 是**圆心**的漂移幅度，**不是**轨道半径；
        # 轨道半径仍是 `radius_m`。两者语义不同、量级不同，**不得**混读为一个"半径"。
        # 取 0.6 m / 30 s ⇒ 圆心漂移速度 2πA/T = 0.126 m/s，仅占轨道速度 1.0 m/s 的 13%。
        # 两者只在 `motion == 'epicycle'` 时被读取；其余三种运动**不受影响**（A2 回归）。
        self.drift_amplitude_m_ = float(self.declare_parameter('drift_amplitude_m', 0.6).value)
        self.drift_period_s_ = float(self.declare_parameter('drift_period_s', 30.0).value)
        self.rate_hz_ = self.declare_parameter('rate_hz', 20.0).value
        self.arm_retry_s_ = self.declare_parameter('arm_retry_s', 2.0).value
        # 目标 sys id：入侵者 PX4 实例 1 → MAV_SYS_ID = px4_instance+1 = 2
        self.target_system_ = int(self.declare_parameter('target_system', 2).value)
        # ../../../docs/adr/0020-package-boundaries-and-runtime-topology.md#params 单一注入，节点不得覆写）
        self.start_tol_m_ = float(self.declare_parameter('start_tol_m', 0.4).value)
        self.start_vel_eps_mps_ = float(self.declare_parameter('start_vel_eps_mps', 0.35).value)
        self.start_dwell_s_ = float(self.declare_parameter('start_dwell_s', 0.5).value)
        self.run_region_radius_m_ = float(self.declare_parameter('run_region_radius_m', 15.0).value)
        self.epoch_topic_ = self.declare_parameter('epoch_topic', '/agc/scenario/reset_epoch').value

        p = f'/{self.ns_}/fmu'
        self.pub_ocm_ = self.create_publisher(OffboardControlMode, f'{p}/in/offboard_control_mode', _qos())
        self.pub_sp_ = self.create_publisher(TrajectorySetpoint, f'{p}/in/trajectory_setpoint', _qos())
        self.pub_cmd_ = self.create_publisher(VehicleCommand, f'{p}/in/vehicle_command', _qos())
        self.sub_odom_ = self.create_subscription(VehicleOdometry, f'{p}/out/vehicle_odometry', self._on_odom, _qos())
        self.sub_st_ = self.create_subscription(VehicleStatus, f'{p}/out/vehicle_status', self._on_status, _qos())
        # 只消费 jammer 的**已校验授权事件**（非原始命令）→ 停止 Offboard 流
        # （：停发 Offboard 流 → 触发 PX4 offboard-loss 行为，非 data-link-loss）
        self.jam_state_topic_ = self.declare_parameter(
            'jam_state_topic', '/agc/task/jam_state').value
        self.sub_jam_state_ = self.create_subscription(
            String, self.jam_state_topic_, self._on_jam_state, 10)
        # episode epoch（新 episode 起点 / 时间 / 干扰态复位）
        self.sub_epoch_ = self.create_subscription(Int32, self.epoch_topic_, self._on_epoch, _epoch_qos())

        # 预热时钟：**独立于** episode 计时（节点启动即起算）
        self.warmup_t0_ = self._now_us()
        # episode 状态
        self.origins_ = None
        self.t0_ = None
        self.episode_armed_ = False
        self.last_epoch_ = None
        self.stable_since_ = None
        self.terminated_ = False
        # 观测
        self.have_odom_ = False
        self.pos_ = None
        self.speed_ = None
        self.armed_ = False
        self.nav_state_ = 0
        self.offboard_at_ = None
        self.last_arm_ = None
        # 干扰
        self.jammed_ = False
        self.jam_on_us_ = None
        self.dt_ = 1.0 / self.rate_hz_
        # H0-回归（2026-11-03）：**odom 未到达的静默超时**诊断。
        # 病灶：`_tick` 在 `have_odom_/origins_` 未就绪时**静默 return**，节点看起来"活着"
        # 却从不 ARM——s04 抬高度实测中目标机因此全程停在地面，而日志里**一条错误都没有**
        # （3 分钟 AIR_SEARCH 才被发现）。现改为：超时后周期性 WARN + 一次性 ERROR 说明原因。
        self.odom_deadline_s_ = 20.0      # 超过此秒数仍无 odom → ERROR（不自杀，只大声报）
        self.last_odom_warn_ = None

        self.create_timer(self.dt_, self._tick)
        self.get_logger().info(
            f'intruder_driver: ns={self.ns_} motion={self.motion_} '
            f'cruise_alt={self.alt_m_}m (source={self.cruise_alt_source_}) '
            f'speed={self.v_} radius={self.radius_} R_run={self.run_region_radius_m_}'
            + (f' drift_amp={self.drift_amplitude_m_}m drift_period={self.drift_period_s_}s'
               if self.motion_ == 'epicycle' else ''))

    # ---- callbacks ----
    def _resolve_cruise_alt(self):
        """H0：把 `cruise_alt_m` / `alt_m` 收敛成**唯一**巡航高度，非法即拒绝启动。

 规则（与 `config/scenarios.yaml` 场景覆盖、`base.yaml` 基参的合并口径一致）：
 1. `cruise_alt_m` 显式给出（非 NaN）→ 用它；
 2. 否则 `alt_m` 显式给出（非 NaN）→ 用它（弃用别名，仅兼容）；
 3. 两者都显式且**不相等**（容差 1e-9）→ 拒绝启动（歧义叠加，必须由场景/config 消解）；
 4. 都没有 → 拒绝启动（不静默取缺省值：缺省值会让"没配置"看起来像"配置了 2.0"）。

 返回值必须是**有限正数**；NaN / ±Inf / ≤0 一律拒绝——高度 0 意味着目标贴地，
 在本任务的"空中目标"语义下不是合法巡航高度，且会让感知/火控判据静默失真。
        """
        c, a = self.cruise_alt_m_, self.alt_m_alias_
        c_set, a_set = not math.isnan(c), not math.isnan(a)
        if c_set and a_set:
            if abs(c - a) > 1e-9:
                raise RuntimeError(
                    'cruise_alt_m=%r 与已弃用别名 alt_m=%r 同时给出且不相等 → 拒绝启动'
                    '（H0：巡航高度只能有一个有效来源，见 docs/conventions/飞行高度分层与按地图定高.md#layers）'
                    % (c, a))
            value, source = c, 'cruise_alt_m(+alt_m 一致)'
        elif c_set:
            value, source = c, 'cruise_alt_m'
        elif a_set:
            value, source = a, 'alt_m(弃用别名)'
        else:
            raise RuntimeError(
                'cruise_alt_m / alt_m 均未给出 → 拒绝启动'
                '（H0：巡航高度必须由 config 或场景显式给定，不得静默取缺省）')
        if not math.isfinite(value) or value <= 0.0:
            raise RuntimeError(
                '巡航高度 %r 非有限正数（NaN/±Inf/≤0）→ 拒绝启动（来源 %s）' % (value, source))
        self.cruise_alt_source_ = source
        return float(value)

    def _now_us(self):
        return int(self.get_clock().now().nanoseconds / 1000)

    def _on_odom(self, m: VehicleOdometry):
        self.have_odom_ = True
        self.pos_ = (m.position[0], m.position[1], m.position[2])
        self.speed_ = math.sqrt(m.velocity[0] ** 2 + m.velocity[1] ** 2 + m.velocity[2] ** 2)
        if self.origins_ is None:
            # 新 episode 后**重新锚定**：原点是进入 episode 时的当前位姿（boot 点或复位后的 spawn 位）
            self.origins_ = self.pos_
            self.get_logger().info(f'odom origin (NED) = {self.origins_}')

    def _on_status(self, m: VehicleStatus):
        self.nav_state_ = m.nav_state
        self.armed_ = (m.arming_state == 2)  # ARMING_STATE_ARMED

    def _on_epoch(self, m: Int32):
        """新 episode：epoch 值变化即重开回合（起点 / 时间 / 干扰态复位）。"""
        val = int(m.data)
        if self.last_epoch_ is None or val != self.last_epoch_:
            self.last_epoch_ = val
            self.origins_ = None      # 下一条 odom 重新锚定
            self.t0_ = None
            self.episode_armed_ = True
            self.stable_since_ = None
            self.terminated_ = False
            self.jammed_ = False
            self.jam_on_us_ = None
            self.get_logger().info(f'episode armed (epoch={val})')

    def _on_jam_state(self, m: String):
        """消费 jammer 的**已校验授权事件**（`JAM_*` = 授权，`JAM_NONE`/空 = 释放）。"""
        key = m.data.strip().upper()
        jammed = key not in ('', 'JAM_NONE')
        now = self._now_us()
        if jammed and not self.jammed_:
            self.jam_on_us_ = now
            self.get_logger().warn(
                f'jam event {key}: STOP offboard stream '
                f'(→ PX4 offboard-loss, per COM_OF_LOSS_T/COM_OBL_RC_ACT; NOT data-link-loss NAV_DLL_ACT)')
        elif not jammed and self.jammed_:
            # CLEAR 重基准：把暂停时长加回 t0_，恢复后参考从干扰发生时刻连续续上（不跳变）
            if self.jam_on_us_ is not None and self.t0_ is not None:
                pause = now - self.jam_on_us_
                self.t0_ += pause
                self.get_logger().warn(f'jam CLEAR (rebaseline pause={pause * 1e-6:.3f}s)')
            else:
                self.get_logger().warn(f'jam off ({key}): resume')
            self.jam_on_us_ = None
        self.jammed_ = jammed

    # ---- control ----
    def _send_cmd(self, command, p1=0.0, p2=0.0, p3=0.0, p4=0.0, p5=0.0, p6=0.0, p7=0.0):
        c = VehicleCommand()
        c.timestamp = self._now_us()
        c.command = command
        c.param1, c.param2, c.param3, c.param4 = p1, p2, p3, p4
        c.param5, c.param6, c.param7 = p5, p6, p7
        c.target_system = self.target_system_     # 本实例 sys id（px4_instance+1）
        c.target_component = 1
        c.source_system = 1
        c.source_component = 1
        c.from_external = True
        self.pub_cmd_.publish(c)

    def _target(self, t):
        """返回基于 `origins_` 的 Offboard 位置目标（NED）：static / linear / maneuver / epicycle。

 `epicycle`（ADR-0031）——**漂移轨道**：绕半径 `radius_m` 的圆轨道转，同时**圆心**以幅度
 `drift_amplitude_m`、周期 `drift_period_s` 缓慢漂移。解析式：

            c(t) = o + A·(sin(ω_c·t), cos(ω_c·t))，  ω_c = 2π/T_drift
            p(t) = c(t) + r·(cos(ω_o·t), sin(ω_o·t))，ω_o = v / r

 设计要点（逐条对应验收）：
          * **t=0 恒定起点** `p(0) = (ox + r, oy + A)`——`sin(0)=0, cos(0)=1`，与 `_start_pose`
            同一值，故起点协议（`_start_pose = _target(0)`）**不需要任何特例分支**。
 * **C∞ 连续**：正弦 / 余弦组合处处光滑，无顶点、无速度阶跃（这是它优于多航点折线的根因）。
 * **峰值速度** `|dp/dt| ≤ A·ω_c + r·ω_o`（三角不等式，严格上界）。取 A=1.5 / T=60 s、
            r=1.8、v=1.0 ⇒ 1.063 m/s ≤ 1.206 m/s（火控提前量上界），推导见 ADR-0031。
 * **越界安全** `max|p − o| ≤ A + r`（同一三角不等式）⇒ 恒在 `run_region_radius_m` 内，
 `_apply_region` 的夹持对本运动**永不触发**（它是构造上有界，不是被夹出来的）。

 既有三支（static / linear / maneuver）**逐字未改**——历史基线不得回归（A2）。
        """
        ox, oy, oz = self.origins_
        z = oz - self.alt_m_          # NED 向下 → -alt 表示上升 alt（相对 episode 原点）
        if self.motion_ == 'linear':
            return ox, oy + self.v_ * t, z
        if self.motion_ == 'maneuver':
            th = (self.v_ / max(self.radius_, 1e-3)) * t
            # t=0 落在圆周定义点 (ox+r, oy)——切入连续（不从原点起跳）
            return ox + self.radius_ * math.cos(th), oy + self.radius_ * math.sin(th), z
        if self.motion_ == 'epicycle':
            wc = 2.0 * math.pi / max(self.drift_period_s_, 1e-3)   # 圆心漂移角频率
            wo = self.v_ / max(self.radius_, 1e-3)                 # 轨道角频率
            cx = ox + self.drift_amplitude_m_ * math.sin(wc * t)
            cy = oy + self.drift_amplitude_m_ * math.cos(wc * t)
            return cx + self.radius_ * math.cos(wo * t), cy + self.radius_ * math.sin(wo * t), z
        return ox, oy, z              # static：悬停

    def _apply_region(self, tgt):
        """运行区边界：水平离 `origins_` 超过 R（>0 生效）→ 夹持到边界并置 `terminated_`（仅日志一次）。"""
        R = self.run_region_radius_m_
        if R is None or R <= 0.0:
            return tgt
        ox, oy = self.origins_[0], self.origins_[1]
        dx, dy = tgt[0] - ox, tgt[1] - oy
        d = math.hypot(dx, dy)
        if d > R:
            if not self.terminated_:
                self.terminated_ = True
                self.get_logger().error(f'[boundary] run region reached R={R:.2f} (d={d:.2f})')
            k = R / d
            return ox + dx * k, oy + dy * k, tgt[2]
        return tgt

    def _start_pose(self):
        """起始位姿 = `_target(0)`，并经受同一运行区夹持（保证与推进轨迹一致）。"""
        return self._apply_region(self._target(0.0))

    def _maybe_start(self, ts):
        """起点协议：起始位姿稳定持续 `start_dwell_s` → 记 episode t=0。"""
        if self.pos_ is None or self.speed_ is None:
            return
        sx, sy, sz = self._start_pose()
        d = math.sqrt((self.pos_[0] - sx) ** 2 + (self.pos_[1] - sy) ** 2 + (self.pos_[2] - sz) ** 2)
        if d <= self.start_tol_m_ and self.speed_ <= self.start_vel_eps_mps_:
            if self.stable_since_ is None:
                self.stable_since_ = ts
            elif (ts - self.stable_since_) * 1e-6 >= self.start_dwell_s_:
                self.t0_ = ts
                self.get_logger().info(f'episode t=0 (epoch={self.last_epoch_})')
        else:
            self.stable_since_ = None

    def _tick(self):
        # H0-回归：odom（或 episode 重锚后尚无 odom）未就绪时**不得静默 return**。
        # 实测病灶：`px4_1` 的 uXRCE session 比 `intruder_driver` 启动晚约 3 s，
        # driver 先收到 latched epoch → `origins_=None`，随后在上百拍内收不到 odom，
        # `_tick` 每拍静默返回 → 永不 ARM → 目标机停地面，任务 3 分钟后才以 AIR_SEARCH 超时暴露。
        # 2026-11-03 更正：旧注释以"垂直差 14 m > 量程 12 m ⇒ 感知恒盲"为**诊断特征**；
        # 量程改 30.0 后 √(26.17²+14²)=29.68 m 仍在量程内（余量 0.32 m），该特征**已失效**。
        # 目标未起飞的判定**只能**靠下面的 `have_odom` 错误日志，不得依赖感知致盲。
        if not self.have_odom_ or self.origins_ is None:
            ts = self._now_us()
            tw = (ts - self.warmup_t0_) * 1e-6
            if tw >= self.odom_deadline_s_:
                if self.last_odom_warn_ is None or tw - self.last_odom_warn_ >= 5.0:
                    self.last_odom_warn_ = tw
                    self.get_logger().error(
                        f'[tw={tw:.1f}s] 无可用 odom（have_odom={self.have_odom_}, '
                        f'origins={"set" if self.origins_ is not None else "None"}）→ '
                        f'**未 ARM / 未起飞**。检查 `{self.ns_}` 的 uXRCE 会话与 '
                        f'`/fmu/out/vehicle_odometry` 是否有数据（本节点不会自行恢复）')
            return
        if self.jammed_:
            return  # 干扰授权生效：停发 Offboard → PX4 offboard-loss（非数据链失联；ADR-0010）
        ts = self._now_us()
        tw = (ts - self.warmup_t0_) * 1e-6     # 预热时间（**独立于** episode）

        # ① OffboardControlMode（位置）——切 OFFBOARD 前须持续流 > 1 s
        ocm = OffboardControlMode()
        ocm.timestamp = ts
        ocm.position = True
        self.pub_ocm_.publish(ocm)

        # ② 位置 setpoint：未进入 episode → 恒定悬停保持（不推进）；否则按 episode t 推进
        if self.t0_ is None:
            tgt = self._start_pose()
        else:
            tgt = self._apply_region(self._target((ts - self.t0_) * 1e-6))
        sp = TrajectorySetpoint()
        sp.timestamp = ts
        sp.position = [float(tgt[0]), float(tgt[1]), float(tgt[2])]
        sp.yaw = 0.0
        self.pub_sp_.publish(sp)

        # ③ 起点协议：稳定判定 → episode t=0（未进入 episode 且已武装且未越界终止）
        if self.t0_ is None and self.episode_armed_ and not self.terminated_:
            self._maybe_start(ts)

        # ④ 预热（独立计时）→ arm + 切 OFFBOARD（失败则按 arm_retry_s_ 重试）
        if tw > 1.0 and not self.armed_:
            if self.last_arm_ is None or tw - self.last_arm_ > self.arm_retry_s_:
                self._send_cmd(VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM, p1=1.0)  # ARM
                self.last_arm_ = tw
                self.get_logger().warn(f'[tw={tw:.1f}s] requesting ARM (armed={self.armed_})')
        if self.armed_ and self.nav_state_ != OFFBOARD_NAV_STATE:
            if self.offboard_at_ is None or tw - self.offboard_at_ > self.arm_retry_s_:
                self._send_cmd(VehicleCommand.VEHICLE_CMD_SET_NAV_STATE, p1=float(OFFBOARD_NAV_STATE))
                self.offboard_at_ = tw
                self.get_logger().info(f'[tw={tw:.1f}s] requesting OFFBOARD (nav_state={self.nav_state_})')


def main():
    rclpy.init()
    node = IntruderDriver()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
