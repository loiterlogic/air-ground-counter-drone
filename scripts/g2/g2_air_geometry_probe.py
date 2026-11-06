#!/usr/bin/env python3
"""最小判别探针：记录空中跟踪链的实际几何（**只读**，不发任何命令）。

用途：在 full 场景运行时旁路记录
 * 己方机位置/姿态（`/agc/air/odom`，world ENU）
 * 目标观测位置（`/agc/targets`，world ENU）与真值（`/agc/gt/target` 若存在）
 * 跟踪参考（`/agc/air/tracking_ref`）
 * 由此算出的**机体系方位角** az（按原 `air_perception::gatePoint` 的几何口径；
 该节点已于 2026-11-06 退役，探针独立复算同一几何，不依赖它）

判别目标：区分"目标真的跑到机身后方"（几何/参考问题）与"机体系朝向/坐标变换错"
（姿态问题），二者在 az 序列上的表现不同：
 * 几何问题：`|az|` 平滑增长并越过 ±50°（hfov/2），r 仍 ≤ 12 m；
  * 姿态/变换问题：`fwd = cos(az)` 直接翻负（behind），或 az 在 ±180° 附近跳变。

**只订阅、不发布**，因此不改变被测系统行为；也不写任何实验产物，只打印 CSV 到 stdout。
"""

import argparse
import math
import sys
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy

from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import Odometry

from agc_msgs.msg import TargetTrackArray


def quat_to_R(q):
    x, y, z, w = q.x, q.y, q.z, q.w
    return (
        (1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)),
        (2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)),
        (2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)),
    )


class Probe(Node):
    def __init__(self):
        super().__init__('g2_r3_air_geometry_probe')
        qos = QoSProfile(depth=20)
        qos.reliability = ReliabilityPolicy.BEST_EFFORT
        qos.durability = DurabilityPolicy.VOLATILE
        self.drone = None      # (x,y,z, q)
        self.target = None     # (x,y,z)
        self.ref = None        # (x,y,z)
        self.t_drone = self.t_target = self.t_ref = None

        self.create_subscription(Odometry, '/agc/air/odom', self._on_drone, qos)
        # 注意：/agc/targets 是 agc_msgs/TargetTrackArray（不是 PoseStamped）
        self.create_subscription(TargetTrackArray, '/agc/targets', self._on_target, qos)
        self.create_subscription(PoseStamped, '/agc/air/tracking_ref', self._on_ref, qos)

    def _on_drone(self, m):
        p = m.pose.pose
        self.drone = (p.position.x, p.position.y, p.position.z, p.orientation)
        self.t_drone = time.monotonic()

    def _on_target(self, m):
        # 取第一条 track 的最新位置；空数组 = 本拍无目标
        if not m.tracks:
            return
        p = m.tracks[0].pose.pose.position
        self.target = (p.x, p.y, p.z)
        self.t_target = time.monotonic()

    def _on_ref(self, m):
        p = m.pose.position
        self.ref = (p.x, p.y, p.z)
        self.t_ref = time.monotonic()

    def sample(self):
        """按原 air_perception::gatePoint 口径算 az/el/range（boresight=[1,0,0] 机头；节点已退役，此处独立复算）。"""
        if self.drone is None or self.target is None:
            return None
        dx, dy, dz = self.drone[0], self.drone[1], self.drone[2]
        tx, ty, tz = self.target
        d = (tx - dx, ty - dy, tz - dz)
        r = math.sqrt(sum(c * c for c in d))
        if r < 1e-9:
            return None
        u = tuple(c / r for c in d)
        R = quat_to_R(self.drone[3])
        # boresight [1,0,0] 经姿态旋转
        bore = (R[0][0], R[1][0], R[2][0])
        up = (0.0, 0.0, 1.0)
        right = (bore[1] * up[2] - bore[2] * up[1],
                 bore[2] * up[0] - bore[0] * up[2],
                 bore[0] * up[1] - bore[1] * up[0])
        rn = math.sqrt(sum(c * c for c in right)) or 1.0
        right = tuple(c / rn for c in right)
        up2 = (right[1] * bore[2] - right[2] * bore[1],
               right[2] * bore[0] - right[0] * bore[2],
               right[0] * bore[1] - right[1] * bore[0])
        fwd = sum(u[i] * bore[i] for i in range(3))
        rc = sum(u[i] * right[i] for i in range(3))
        uc = sum(u[i] * up2[i] for i in range(3))
        az = math.degrees(math.atan2(rc, fwd))
        el = math.degrees(math.atan2(uc, math.hypot(fwd, rc)))
        # 机体水平朝向（世界系，从 odom 四元数取 yaw）
        q = self.drone[3]
        yaw = math.degrees(math.atan2(2 * (q.w * q.z + q.x * q.y),
                                      1 - 2 * (q.y * q.y + q.z * q.z)))
        horiz = math.hypot(tx - dx, ty - dy)
        return {
            'drone': (round(dx, 3), round(dy, 3), round(dz, 3)),
            'yaw_deg': round(yaw, 1),
            'target': (round(tx, 3), round(ty, 3), round(tz, 3)),
            'ref': None if self.ref is None else tuple(round(c, 3) for c in self.ref),
            'r3d': round(r, 3),
            'horiz': round(horiz, 3),
            'az_deg': round(az, 1),
            'el_deg': round(el, 1),
            'behind': fwd <= 0.0,
            'age_drone': None if self.t_drone is None else round(time.monotonic() - self.t_drone, 3),
            'age_target': None if self.t_target is None else round(time.monotonic() - self.t_target, 3),
        }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--duration', type=float, default=120.0)
    ap.add_argument('--period', type=float, default=1.0)
    args = ap.parse_args(argv)

    rclpy.init()
    n = Probe()
    t_end = time.monotonic() + args.duration
    print('t,drone_x,drone_y,drone_z,yaw_deg,tgt_x,tgt_y,tgt_z,ref_x,ref_y,ref_z,'
          'r3d,horiz,az_deg,el_deg,behind,age_drone,age_target')
    t0 = time.monotonic()
    last = 0.0
    while time.monotonic() < t_end and rclpy.ok():
        rclpy.spin_once(n, timeout_sec=0.02)
        if time.monotonic() - last >= args.period:
            last = time.monotonic()
            s = n.sample()
            if s:
                ref = s['ref'] or ('', '', '')
                print('%.1f,%.3f,%.3f,%.3f,%.1f,%.3f,%.3f,%.3f,%s,%s,%s,%.3f,%.3f,%.1f,%.1f,%d,%s,%s' % (
                    time.monotonic() - t0, *s['drone'], s['yaw_deg'], *s['target'], *ref,
                    s['r3d'], s['horiz'], s['az_deg'], s['el_deg'], int(s['behind']),
                    s['age_drone'], s['age_target']))
                sys.stdout.flush()
    n.destroy_node()
    rclpy.shutdown()
    return 0


if __name__ == '__main__':
    sys.exit(main())
