"""agc_rl 地面 RL 推理节点。

链路位置：`ground_policy_rl → cmd_vel_raw → collision_monitor → 唯一执行口 → ground_drive_relay → GZ`。
本节点**只**写中间话题 `cmd_vel_raw`（`/agc/ground/cmd_vel_raw`），**SHALL NOT** 直接写契约
唯一执行口（契约 [唯一执行口](../../../docs/adr/0020-package-boundaries-and-runtime-topology.md#execution-port)）。

- 订阅：`/agc/ground/odom`（world 位姿/速度）、`/agc/ground/scan`（2D LaserScan）、`/agc/ground/goal`、
 `/agc/task/state`（仅 `GROUND_APPROACH` 允许驱动）。
- 输出：`TwistStamped`（车体系）至 `cmd_vel_raw`，定频（默认 20 Hz）。
- 失效语义：四类必需输入（task 授权 / odom / goal / scan）各持**独立寿命**（`rl.yaml`
 `input_timeout.*` 单一注入），任一过期 / 无效即输出**零速**；`scan` 的「未知」（NaN）与
 「合法无回波」（`+inf`）区分见 `agc_rl.interface`；**从未收到 / 全 NaN** 的扫描**不**默认无遮挡。
- 策略由 config `policy_path` 加载（`agc_rl.policy`）；obs/action 语义由 `agc_rl.interface` 冻结。
- **路径消费（ADR-0013）**：另订 `/agc/ground/path`（`nav_msgs/Path`，`frame_id=world`），
 经 `agc_rl.path_consumer` 的五类质量门后算出**确定性参考点**，用它替换原来的 goal 航向参考。
 这是**确定性占位消费者**：路径**不进入** obs（`interface.py` 的 obs/action 空间与冻结口径不变），
  因此"能沿路径走"**不等于**"训练 RL 已具备路径跟踪能力"（ADR-0013(b)）。
  路径任一质量门不过 → **清缓存 + 持续零速**，**不得**静默退回 goal-only（ADR-0013(e)）。
- 语言：Python（RL 域，[ADR-0020](../../docs/adr/0020-package-boundaries-and-runtime-topology.md#top)）。

RL 节点**不写文件**：run 级日志 / 产物归 `agc_run_logger` 与 `experiments/`。
"""

import math
import os
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy

from ament_index_python.packages import get_package_share_directory

from agc_msgs.msg import AgcTaskState
from geometry_msgs.msg import PoseStamped, TwistStamped
from nav_msgs.msg import Odometry, Path
from sensor_msgs.msg import LaserScan

from agc_rl import interface
from agc_rl import path_consumer
from agc_rl.policy import load_policy


def _yaw_from_quat(q):
    return math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))


def _wrap_pi(a):
    while a > math.pi:
        a -= 2.0 * math.pi
    while a < -math.pi:
        a += 2.0 * math.pi
    return a


class GroundPolicyRL(Node):
    def __init__(self):
        super().__init__('ground_policy_rl')

        self.base_frame = self.declare_parameter('base_frame', 'car/base_link').value
        self.rate_hz = self.declare_parameter('rate_hz', 20.0).value

        self.odom_topic = self.declare_parameter('odom_topic', '/agc/ground/odom').value
        self.scan_topic = self.declare_parameter('scan_topic', '/agc/ground/scan').value
        self.goal_topic = self.declare_parameter('goal_topic', '/agc/ground/goal').value
        self.state_topic = self.declare_parameter('state_topic', '/agc/task/state').value
        self.cmd_raw_topic = self.declare_parameter(
            'cmd_raw_topic', '/agc/ground/cmd_vel_raw').value

        self.num_sectors = int(self.declare_parameter('num_sectors', 12).value)
        self.lidar_max_range = self.declare_parameter('lidar_max_range', 10.0).value
        self.pose_norm_m = self.declare_parameter('pose_norm_m', 10.0).value
        self.track_norm_m = self.declare_parameter('track_norm_m', 5.0).value

        # 策略加载路径（config/*.yaml 单一注入；config 给文件名，节点在
        # `agc_rl/policies/` 下解析为绝对路径；空则用内置默认确定性策略。
        self.policy_file = self.declare_parameter('policy_file', '').value

        # action → cmd_vel 映射参数（`interface.action_to_twist`）
        self.control = {
            'reference_speed': self.declare_parameter('control.reference_speed', 1.0).value,
            'fast_speed': self.declare_parameter('control.fast_speed', 1.3).value,
            'min_offset': self.declare_parameter('control.min_offset', 0.3).value,
            'max_offset': self.declare_parameter('control.max_offset', 1.0).value,
            'k_heading': self.declare_parameter('control.k_heading', 1.5).value,
            'k_lateral': self.declare_parameter('control.k_lateral', 0.8).value,
            'max_yaw_rate': self.declare_parameter('control.max_yaw_rate', 1.0).value,
            # 净空参考值（**米**，与车前净空同量纲）； 量纲一致化，动作强度与 lidar_max_range 解耦。
            'clearance_ref_m': self.declare_parameter('control.clearance_ref_m', 1.0).value,
        }

        # 四类必需输入的**独立寿命**（秒，由 config 单一注入）。到达时刻按
        # **单调时钟**记（与 同口径：不受 ROS 时钟冻结 / 回拨影响）。
        self.timeouts = {
            'task_auth': self.declare_parameter('input_timeout.task_auth_s', 2.0).value,
            'odom': self.declare_parameter('input_timeout.odom_s', 0.5).value,
            'goal': self.declare_parameter('input_timeout.goal_s', 2.0).value,
            'scan': self.declare_parameter('input_timeout.scan_s', 0.5).value,
        }

        # 路径消费（ADR-0013/0109）：**确定性占位消费者**，路径不进入 obs。
        # path_enabled=False → 行为与既有版本完全一致（纯 goal 参考），用于对照与回退；
        # path_enabled=True → 路径成为**必要输入**：质量门任一不过即零速，绝不 goal-only 兜底。
        self.path_enabled = bool(self.declare_parameter('path.enabled', True).value)
        self.path_topic = self.declare_parameter(
            'path.topic', '/agc/ground/path').value
        self.path_frame = self.declare_parameter('path.frame_id', 'world').value
        self.path_max_age_s = self.declare_parameter('path.max_age_s', 5.0).value
        self.path_lookahead_m = self.declare_parameter('path.lookahead_m', 1.0).value
        # 最近点搜索的弧长窗口（ADR-0013 的限界语义）。**默认有限界**：
        # 发布侧在车位位移 > replan_displacement_m(1.0 m) 时重发路径，故车距路径起点可达 ~1.0 m；
        # 叠加前视 lookahead_m(1.0 m) -> 2.0 m 覆盖“起点到前视点”的完整相关段。
        # `<= 0` 表示显式不限界，**仅供测试对照**（折返路径会选到后段，不用于生产）。
        self.path_search_m = self.declare_parameter(
            'path.search_dist_m', self.path_lookahead_m * 2.0).value
        self.path_goal_tol_m = self.declare_parameter('path.goal_tol_m', 0.3).value
        self.path_goal_consistency_m = self.declare_parameter(
            'path.goal_consistency_m', 1.0).value

        policy_path = ''
        if self.policy_file:
            policy_path = os.path.join(
                get_package_share_directory('agc_rl'), 'policies', self.policy_file)
        self.policy = load_policy(policy_path)
        self.get_logger().info(
            "agc_rl 推理节点：policy=%s path='%s' obs_dim=%d n_actions=%d"
            % (self.policy.name, policy_path,
               interface.obs_dim(self.num_sectors), interface.N_ACTIONS))

        # 传感器数据用 SENSOR_DATA（best-effort）QoS，对齐 Nav2（ADR-0003 吸收点）
        sensor_qos = QoSProfile(depth=10)
        sensor_qos.reliability = ReliabilityPolicy.BEST_EFFORT
        sensor_qos.durability = DurabilityPolicy.VOLATILE

        self.pub = self.create_publisher(TwistStamped, self.cmd_raw_topic, 10)
        self.create_subscription(Odometry, self.odom_topic, self._on_odom, 20)
        self.create_subscription(LaserScan, self.scan_topic, self._on_scan, sensor_qos)
        self.create_subscription(PoseStamped, self.goal_topic, self._on_goal, 20)
        self.create_subscription(AgcTaskState, self.state_topic, self._on_state, 20)
        if self.path_enabled:
            # QoS depth=1 + VOLATILE：路径是"最新整体替换"语义，不排队重放旧路径。
            self.create_subscription(Path, self.path_topic, self._on_path, 1)

        self.x = self.y = self.yaw = 0.0
        self.goal_x = self.goal_y = 0.0
        self.state = AgcTaskState.IDLE
        self.sectors = [1.0] * self.num_sectors
        self.scan_valid = False
        self.last_action = 0
        # 各输入的**到达时刻**（单调钟）；`None` = 从未收到（独立寿命）。
        self._t_odom = None
        self._t_goal = None
        self._t_state = None
        self._t_scan = None
        # 路径：`None` = 当前无可用路径（收到又失效时会被清成 None，不保留旧值）
        self.path = None
        self._path_ever = False
        self._path_reject_reason = path_consumer.NEVER_RECEIVED
        self._last_gate_log = ''

        self.timer = self.create_timer(1.0 / max(self.rate_hz, 1e-3), self._tick)

    def _on_odom(self, msg):
        self.x = msg.pose.pose.position.x
        self.y = msg.pose.pose.position.y
        self.yaw = _yaw_from_quat(msg.pose.pose.orientation)
        self._t_odom = time.monotonic()

    def _on_scan(self, msg):
        ranges = list(msg.ranges)
        angles = [msg.angle_min + i * msg.angle_increment for i in range(len(ranges))]
        self.sectors = interface.sectors_from_angles(
            angles, ranges, self.num_sectors, self.lidar_max_range)
        # 全 NaN / 非法读数 → 该扫描**无效**（不得据以判「无遮挡」）
        self.scan_valid = interface.scan_has_valid_reading(ranges)
        self._t_scan = time.monotonic()

    def _on_goal(self, msg):
        self.goal_x = msg.pose.position.x
        self.goal_y = msg.pose.position.y
        self._t_goal = time.monotonic()

    def _on_state(self, msg):
        self.state = msg.state
        self._t_state = time.monotonic()

    def _on_path(self, msg):
        """收到新路径：**整体替换**，并立刻做一次质量门判定。

 无效路径**不保留**：缓存清空后按"无路径"处理（持续零速），
 以免出现"最后一条能用的路径继续驱动"（ADR-0013 明令禁止）。
        """
        self._path_ever = True
        gate = self._gate(msg)
        if gate.ok:
            self.path = msg
            self._path_reject_reason = ''
        else:
            self.path = None
            self._path_reject_reason = gate.reason
        self._log_gate(gate.reason)

    def _path_age_s(self, msg):
        """源 stamp 与**本节点 ROS 时钟当前值**之差（秒）。

        用同一时钟相减，所以"重新打 now()"无法伪造新鲜；仿真 reset 导致 stamp 在未来
 （age<0）时由质量门判为不可信。ROS 时钟不可用 / stamp 为 0 时返回 None。
        """
        stamp = msg.header.stamp
        if stamp.sec == 0 and stamp.nanosec == 0:
            return None
        try:
            now_msg = self.get_clock().now()
        except Exception:                                    # noqa: BLE001 - 时钟不可用即不可算
            return None
        return (now_msg - rclpy.time.Time.from_msg(stamp)).nanoseconds / 1e9

    def _gate(self, msg=None):
        """对当前路径跑五类质量门（`msg` 给定时用它的 age，否则用缓存路径的 age）。"""
        target = msg if msg is not None else self.path
        age = self._path_age_s(target) if target is not None else None
        return path_consumer.check_path_gate(
            target, self.path_frame, age, self.path_max_age_s, self._path_ever)

    def _log_gate(self, reason):
        """拒绝原因变化时才打日志，避免 20 Hz 刷屏；原因本身即证据。"""
        shown = reason if reason else 'ok'
        if shown != self._last_gate_log:
            if reason:
                self.get_logger().warn(
                    'G2 路径质量门拒绝：%s（%s）→ 持续零速'
                    % (reason, path_consumer.REASON_TEXT.get(reason, '')))
            else:
                self.get_logger().info('G2 路径质量门通过')
            self._last_gate_log = shown

    def _publish(self, v, w):
        cmd = TwistStamped()
        cmd.header.stamp = self.get_clock().now().to_msg()
        cmd.header.frame_id = self.base_frame
        cmd.twist.linear.x = float(v)
        cmd.twist.angular.z = float(w)
        self.pub.publish(cmd)

    def _fresh(self, t_arrival, limit_s):
        """到达时刻（单调钟）是否在寿命内；`None`（从未收到）恒为 False。"""
        return t_arrival is not None and (time.monotonic() - t_arrival) <= limit_s

    def _authorized(self):
        """任务授权有效：`GROUND_APPROACH` 且状态消息在授权寿命内。"""
        return (self.state == AgcTaskState.GROUND_APPROACH
                and self._fresh(self._t_state, self.timeouts['task_auth']))

    def _stop(self):
        self.last_action = 0
        self._publish(0.0, 0.0)

    def _path_reference(self):
        """路径参考：返回 `(aim_x, aim_y, dist_to_aim)` 或 `None`（路径不可用）。

        路径可用性 = 质量门（含**逐拍重算的过期**，因为 age 随时间增长）通过
 **且**路径末端与当前 goal 一致。任一不满足返回 `None`，调用方据此零速。
        """
        if self.path is None:
            return None
        gate = self._gate()
        if not gate.ok:
            # 过期是随时间演化的，故逐拍复查；失效即清缓存，不留旧路径。
            self.path = None
            self._path_reject_reason = gate.reason
            self._log_gate(gate.reason)
            return None
        if not path_consumer.goal_consistent_with_path(
                self.path, (self.goal_x, self.goal_y), self.path_goal_consistency_m):
            self._path_reject_reason = 'goal_mismatch'
            self._log_gate('goal_mismatch')
            return None

        ref = path_consumer.tracking_reference(
            self.path, (self.x, self.y),
            {'search_dist_m': self.path_search_m,
             'lookahead_m': self.path_lookahead_m,
             'goal_tol_m': self.path_goal_tol_m})
        ax, ay = ref['point']
        return ax, ay, math.hypot(ax - self.x, ay - self.y), ref['finished']

    def _tick(self):
        # task 授权 / odom / goal / scan 各自**独立寿命与无效语义**；
        # 任一必需输入过期 / 无效 → 输出零速（不延续旧状态）。
        # `path.enabled` 时路径也是**必要输入**——启动从未收到路径即持续零速，
        # 不依赖安全层兜底（ADR-0013、 出口 ③①）。
        if not self._authorized():
            self._stop()
            return
        if not self._fresh(self._t_odom, self.timeouts['odom']):
            self._stop()
            return
        if not self._fresh(self._t_goal, self.timeouts['goal']):
            self._stop()
            return
        if not (self.scan_valid and self._fresh(self._t_scan, self.timeouts['scan'])):
            self._stop()
            return

        # obs 的"到目标距离"维**始终是 goal 距离**（`interface.py` 冻结语义，不得改成
        # 到参考点的距离）。路径只影响 `heading_err`（参考/航向），不进 obs。
        dist = math.hypot(self.goal_x - self.x, self.goal_y - self.y)
        if self.path_enabled:
            ref = self._path_reference()
            if ref is None:
                self._stop()
                return
            aim_x, aim_y, _aim_dist, finished = ref
            if finished:
                self._stop()
                return
            heading_err = _wrap_pi(math.atan2(aim_y - self.y, aim_x - self.x) - self.yaw)
        else:
            heading_err = _wrap_pi(
                math.atan2(self.goal_y - self.y, self.goal_x - self.x) - self.yaw)

        obs = interface.build_observation(
            self.sectors, self.x, self.y, dist, self.last_action,
            self.num_sectors, self.pose_norm_m, self.track_norm_m)
        action = self.policy.act(obs, self.num_sectors)
        self.last_action = action

        # 车前净空（米）：扇区为 range / lidar_max_range 的归一值，乘量程还原为米（量纲一致）。
        forward_clearance_m = interface.forward_clearance(
            self.sectors, self.num_sectors, 1) * self.lidar_max_range
        v, w = interface.action_to_twist(
            action, heading_err, forward_clearance_m, self.control)
        self._publish(v, w)


def main(args=None):
    rclpy.init(args=args)
    node = GroundPolicyRL()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
