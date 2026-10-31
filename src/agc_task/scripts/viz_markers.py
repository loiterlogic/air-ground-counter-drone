#!/usr/bin/env python3
"""viz_markers —— 演示用 RViz 叠加层（R6，2026-10-30）。

**为什么单独一个节点、而不住在 GUI 里**：本机 `ros_gz_bridge` 不映射
`visualization_msgs`（实测：只映射 sensor_msgs / nav_msgs / geometry_msgs / tf2 /
ros_gz_interfaces），所以"在 Gazebo GUI 里叠加"技术上走不通；而 RViz 对
OccupancyGrid / Path / LaserScan / MarkerArray 是原生支持。分工：
  * **GZ GUI** = 纯场景（好看）
  * **RViz**   = 语义层（可读）：栅格 / 路径 / 目标 / 障碍 / 空中安全圆盘 / 8 字轨迹

发布的 marker 全部**由几何真源派生**（经 `agc_sim/launch/world_map.py` 单一清单），
不手写坐标；`/agc/viz/markers` 只读不参与任何决策。
"""
import math

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy

from geometry_msgs.msg import Point
from visualization_msgs.msg import Marker, MarkerArray
from agc_msgs.msg import TargetTrackArray, ObstacleTrackArray


# 8 字（Gerono）参考轨迹：契约 C1，rx=15 / ry=9（**只读引用，不在这里定义**）
FIG8_RX, FIG8_RY = 15.0, 9.0


class VizMarkers(Node):
    def __init__(self):
        super().__init__('viz_markers')
        self.declare_parameter('world_map', '')
        self.declare_parameter('frame_id', 'world')
        self.declare_parameter('safety_obstacle_margin', 2.5)
        self.declare_parameter('safety_extra', 0.7)
        self.frame = self.get_parameter('frame_id').value
        self.static = MarkerArray()
        self.dyn = MarkerArray()
        self._build_static()
        latched = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                             reliability=ReliabilityPolicy.RELIABLE)
        self.pub = self.create_publisher(MarkerArray, '/agc/viz/markers', latched)
        self.create_subscription(TargetTrackArray, '/agc/targets', self.on_targets, 10)
        self.create_subscription(ObstacleTrackArray, '/agc/obstacles', self.on_obstacles, 10)
        # 静态层只在启动后 1 s 发一次（TRANSIENT_LOCAL 会保留给后订阅者），
        # 之后只发动态层 —— 278 个 marker 每秒重发是纯浪费（2026-10-30 内存复盘）。
        self._static_sent = False
        self.create_timer(0.5, self.publish)
        self.get_logger().info('viz_markers 就绪：静态 %d + 动态 %d 组 marker'
                               % (len(self.static.markers), len(self.dyn.markers)))

    # ---------- 静态层：安全圆盘 / 8 字参考 / 作业区边界 ----------
    def _build_static(self):
        wm = self._world_map()
        gi = 0
        if wm:
            sim_share, mod = wm
            name = mod.resolve(self.get_parameter('world_map').value)
            _, path = mod.geometry_path(sim_share, name)
            import yaml
            geom = yaml.safe_load(open(path))
            margin = float(self.get_parameter('safety_obstacle_margin').value)
            extra = float(self.get_parameter('safety_extra').value)
            for ob in geom.get('obstacles') or []:
                r = mod.obstacle_safety_radius(ob) + margin + extra
                m = Marker()
                m.header.frame_id = self.frame
                m.ns = 'safety_disk'
                m.id = gi
                gi += 1
                m.type = Marker.CYLINDER
                m.action = Marker.ADD
                m.pose.position.x = float(ob['x'])
                m.pose.position.y = float(ob['y'])
                m.pose.position.z = 0.05
                m.scale.x = m.scale.y = 2.0 * r
                m.scale.z = 0.02
                m.color.r, m.color.g, m.color.b, m.color.a = 0.9, 0.35, 0.2, 0.12
                self.static.markers.append(m)
            # 静态障碍几何：**把 Gazebo 里的"地图"镜像进 RViz**（RViz 渲染不了 gz 场景，
            # 但可以从同一份真源派生几何 marker）。逐 part 一个半透明立方体。
            bi = 1000
            for ob in geom.get('obstacles') or []:
                for pt in mod.obstacle_parts(ob):
                    sz = mod.obstacle_size(pt, pt)
                    sh = mod.obstacle_shape(pt)
                    if sh == 'cylinder':
                        scale = [2.0 * sz[0], 2.0 * sz[0], sz[2]]
                        mtype = Marker.CYLINDER
                    elif sh == 'sphere':
                        scale = [2.0 * sz[0]] * 3
                        mtype = Marker.SPHERE
                    else:
                        scale = [sz[0], sz[1], sz[2]]
                        mtype = Marker.CUBE
                    comp = mod.is_composite(ob)
                    ox = float(ob['x']) + (float(pt.get('x', 0.0)) if comp else 0.0)
                    oy = float(ob['y']) + (float(pt.get('y', 0.0)) if comp else 0.0)
                    # **必须带 yaw**：围墙等实体绕 Z 旋转过（yaw=π/2），漏掉朝向就会画成
                    # 轴对齐 → 长围墙"方向错了"（2026-10-30 实测）。复合体 part yaw 是相对量，
                    # 总朝向 = 实体 yaw + part yaw（与 world_bringup 的注入口径一致）。
                    yaw = float(pt.get('yaw', 0.0)) + (float(ob.get('yaw', 0.0)) if comp else 0.0)
                    m = Marker()
                    m.header.frame_id = self.frame
                    m.ns = 'obstacle_geometry'
                    m.id = bi
                    bi += 1
                    m.type = mtype
                    m.action = Marker.ADD
                    m.pose.position.x = ox
                    m.pose.position.y = oy
                    m.pose.position.z = float(pt['z'])
                    m.pose.orientation.z = math.sin(yaw / 2.0)
                    m.pose.orientation.w = math.cos(yaw / 2.0)
                    m.scale.x, m.scale.y, m.scale.z = float(scale[0]), float(scale[1]), float(scale[2])
                    m.color.r, m.color.g, m.color.b, m.color.a = 0.72, 0.76, 0.82, 0.45
                    self.static.markers.append(m)
            wa = geom.get('work_area') or {}
            if wa:
                x0 = float(wa['origin_x']); y0 = float(wa['origin_y'])
                x1 = x0 + float(wa['size_x']); y1 = y0 + float(wa['size_y'])
                m = Marker()
                m.header.frame_id = self.frame
                m.ns = 'work_area'; m.id = 0; m.type = Marker.LINE_STRIP
                m.action = Marker.ADD; m.scale.x = 0.15
                m.color.r, m.color.g, m.color.b, m.color.a = 0.2, 0.6, 1.0, 0.9
                for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)):
                    p = Point(); p.x, p.y, p.z = x, y, 0.1
                    m.points.append(p)
                self.static.markers.append(m)
        # 8 字参考轨迹
        m = Marker()
        m.header.frame_id = self.frame
        m.ns = 'figure8'; m.id = 0; m.type = Marker.LINE_STRIP
        m.action = Marker.ADD; m.scale.x = 0.12
        m.color.r, m.color.g, m.color.b, m.color.a = 0.1, 1.0, 0.4, 0.9
        for k in range(121):
            t = 2.0 * math.pi * k / 120.0
            p = Point()
            p.x = FIG8_RX * math.cos(t)
            p.y = FIG8_RY * math.sin(t) * math.cos(t)
            p.z = 2.5
            m.points.append(p)
        self.static.markers.append(m)

    def _world_map(self):
        try:
            import importlib.util
            import os
            from ament_index_python.packages import get_package_share_directory
            share = get_package_share_directory('agc_sim')
            p = os.path.join(share, 'launch', 'world_map.py')
            spec = importlib.util.spec_from_file_location('agc_world_map', p)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return share, mod
        except Exception as exc:  # noqa: BLE001
            self.get_logger().warning('viz_markers：读不到几何真源（%s），静态层跳过' % exc)
            return None

    # ---------- 动态层 ----------
    def on_targets(self, msg):
        ms = [m for m in self.dyn.markers if m.ns != 'target']
        idx = 100
        for t in msg.tracks:
            m = Marker()
            m.header.frame_id = msg.header.frame_id or self.frame
            m.ns = 'target'; m.id = idx; idx += 1
            m.type = Marker.SPHERE; m.action = Marker.ADD
            m.pose.position.x = t.pose.pose.position.x
            m.pose.position.y = t.pose.pose.position.y
            m.pose.position.z = t.pose.pose.position.z
            m.scale.x = m.scale.y = m.scale.z = 1.2
            m.color.r, m.color.g, m.color.b, m.color.a = 1.0, 0.85, 0.1, 1.0
            ms.append(m)
        self.dyn.markers = ms

    def on_obstacles(self, msg):
        ms = [m for m in self.dyn.markers if m.ns != 'obstacle']
        idx = 200
        for o in msg.tracks:
            m = Marker()
            m.header.frame_id = msg.header.frame_id or self.frame
            m.ns = 'obstacle'; m.id = idx; idx += 1
            m.type = Marker.CUBE; m.action = Marker.ADD
            m.pose = o.pose
            m.scale.x = o.size.x
            m.scale.y = o.size.y
            m.scale.z = o.size.z
            m.color.r, m.color.g, m.color.b, m.color.a = 1.0, 0.3, 0.3, 0.5
            ms.append(m)
        self.dyn.markers = ms

    def publish(self):
        now = self.get_clock().now().to_msg()
        if not self._static_sent:
            self._static_sent = True
            first = MarkerArray()
            for m in self.static.markers:
                if m.header.stamp.sec == 0:
                    m.header.stamp = now
                first.markers.append(m)
            self.pub.publish(first)
            return
        out = MarkerArray()
        for m in self.dyn.markers:
            if m.header.stamp.sec == 0:
                m.header.stamp = now
            out.markers.append(m)
        self.pub.publish(out)


def main():
    rclpy.init()
    try:
        rclpy.spin(VizMarkers())
    except KeyboardInterrupt:
        pass
    finally:
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
