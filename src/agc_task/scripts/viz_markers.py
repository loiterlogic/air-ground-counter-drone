#!/usr/bin/env python3
"""viz_markers —— 演示用 RViz 叠加层（R6，2026-10-30）。

**为什么单独一个节点、而不住在 GUI 里**：本机 `ros_gz_bridge` 不映射
`visualization_msgs`（实测：只映射 sensor_msgs / nav_msgs / geometry_msgs / tf2 /
ros_gz_interfaces），所以"在 Gazebo GUI 里叠加"技术上走不通；而 RViz 对
OccupancyGrid / Path / LaserScan / MarkerArray 是原生支持。分工：
 * **GZ GUI** = 纯场景（好看）
 * **RViz** = 语义层（可读）：栅格 / 路径 / 三机 / 障碍
 （三机 = 车 / 己方机 / 目标，统一由 `_body_markers` 画
 「方向箭头 + 机体位置球 + 箭尾定位点」，外观只由类常量控制）
 （**不含 8 字轨迹**——反无人机场景不用预设轨迹，2026-11-04 用户裁定删除）

发布的 marker 全部**由配置文件派生**（经 `agc_sim/launch/world_map.py` 单一清单），
不手写坐标；`/agc/viz/markers` 只读不参与任何决策。
"""
import math

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy

from geometry_msgs.msg import Point
from visualization_msgs.msg import Marker, MarkerArray
from nav_msgs.msg import Odometry
from agc_msgs.msg import TargetTrackArray, ObstacleTrackArray


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
        self.create_subscription(Odometry, '/agc/ground/odom', self.on_car_odom, 10)
        self.create_subscription(Odometry, '/agc/air/odom', self.on_own_odom, 10)
        self.car_path = []
        self.car_pose = None
        self.own_pose = None
        # 静态层只在启动后 1 s 发一次（TRANSIENT_LOCAL 会保留给后订阅者），
        # 之后只发动态层 —— 278 个 marker 每秒重发是纯浪费（2026-10-30 内存复盘）。
        self._static_sent = False
        self.create_timer(0.5, self.publish)
        self.get_logger().info('viz_markers 就绪：静态 %d + 动态 %d 组 marker'
                               % (len(self.static.markers), len(self.dyn.markers)))

    # ---------- 静态层： 作业区边界 / 障碍几何 ----------
    def _build_static(self):
        wm = self._world_map()
        if wm:
            sim_share, mod = wm
            name = mod.resolve(self.get_parameter('world_map').value)
            _, path = mod.geometry_path(sim_share, name)
            import yaml
            geom = yaml.safe_load(open(path))
            # 静态障碍几何：**把 Gazebo 里的"地图"镜像进 RViz**（RViz 渲染不了 gz 场景，
            # 但可以从同一份配置文件派生几何 marker）。逐 part 一个半透明立方体。
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
                    a = float(ob.get('yaw', 0.0)) if comp else 0.0
                    px = float(pt.get('x', 0.0)) if comp else 0.0
                    py = float(pt.get('y', 0.0)) if comp else 0.0
                    ox = float(ob['x']) + px * math.cos(a) - py * math.sin(a)
                    oy = float(ob['y']) + px * math.sin(a) + py * math.cos(a)
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
        # ---- 2026-11-04（用户裁定）：**删除 8 字参考轨迹 marker** ----
        # 原实现在此无条件绘制 `rx=15 / ry=9` 的 Gerono 8 字（`ns='figure8'`），
        # 画的是**己方机的参考轨迹**。但反无人机场景的 `trajectory_plugin` 已于
        # 2026-11-03 改为 `agc_control/HoverTrajectory`（用户裁定「反无人机场景直接禁止
        # 使用固定轨迹」，见 docs/conventions/飞行高度分层与按地图定高.md#no-fixed-trajectory），
        # 该插件**不读 `traj.*` 段** ⇒ 8 字**根本不会被执行**。
        #
        # 后果不是"多画了一条线"，而是**误导**：RViz 里那条大 8 字会让人以为
        # 己方机按 8 字飞（契约 的八字），而实际行为是悬停/跟踪。
        # 用户 2026-11-04 实测看到该 marker 并质询「那玩意不是早就不用了吗」——据此删除。
        #
        # 保留说明：`agc_control/Figure8Trajectory` 插件本身**仍然存在**（流程验证场景
        # 可显式选用，见 ADR-0031 / 场景不变量测试的 `usage=flow_validation` 出口）；
        # 本篇只删**演示叠加层**里对它的无条件绘制，不删插件、不改 契约值。

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

    def on_car_odom(self, msg):
        p = msg.pose.pose.position
        q = msg.pose.pose.orientation
        self.car_pose = msg.pose.pose
        self.car_path.append((p.x, p.y, p.z))
        self.car_path = self.car_path[-500:]

    def on_own_odom(self, msg):
        self.own_pose = msg.pose.pose

    # ---- 三机外观（集中在这里调，别散落在各回调里）----
    # 车 / 己方机 / 目标**共用这一组参数**：改任意一个，三机同时变。
    ARROW_LENGTH = 2.50      # scale.x：箭头长度
    ARROW_SHAFT  = 0.40      # scale.y：箭杆宽度（加粗改这里）
    ARROW_HEAD   = 0.70      # scale.z：箭头头部尺寸
    BODY_DOT     = 1.20      # 机体位置球直径（画在机体位置，三机统一）
    TAIL_DOT     = 0.45      # 箭尾定位点直径（三机统一）
    TAIL_OFFSET  = 0.90      # 定位点沿机体 -X 后退量，避免被 BODY_DOT 球盖住

    @staticmethod
    def _rot_x(q, v):
        """把机体局部向量 (v, 0, 0) 按四元数 q 旋到世界系（只需旋转矩阵第一列）。"""
        x, y, z, w = q.x, q.y, q.z, q.w
        return (v * (1.0 - 2.0 * (y * y + z * z)),
                v * 2.0 * (x * y + w * z),
                v * 2.0 * (x * z - w * y))

    def _body_markers(self, ns, pose, color):
        """一台机体 = 方向箭头 + 机体位置球 + 箭尾定位点。

 三机（车 / 己方机 / 目标）**统一走本方法**，外观只由本类常量控制，
 不再有目标专属的手写球体。改 BODY_DOT / TAIL_DOT 会让三机**同时**变化。
 ARROW 的 pivot 在尾部、沿 +X ⇒ pose.position 即机体位置（也是箭尾）。
 各 marker 必须用不同 ns，否则 RViz 按 (ns, id) 唯一标识，会互相覆盖。
        """
        r, g, b = color

        a = Marker()
        a.header.frame_id = self.frame
        a.ns = ns; a.id = 0
        a.type = Marker.ARROW; a.action = Marker.ADD
        a.pose = pose
        a.scale.x = self.ARROW_LENGTH
        a.scale.y = self.ARROW_SHAFT
        a.scale.z = self.ARROW_HEAD
        a.color.r, a.color.g, a.color.b, a.color.a = r, g, b, 1.0

        body = Marker()
        body.header.frame_id = self.frame
        body.ns = ns + '_body'; body.id = 0
        body.type = Marker.SPHERE; body.action = Marker.ADD
        body.pose.position.x = pose.position.x
        body.pose.position.y = pose.position.y
        body.pose.position.z = pose.position.z
        body.pose.orientation.w = 1.0
        body.scale.x = body.scale.y = body.scale.z = self.BODY_DOT
        body.color.r, body.color.g, body.color.b, body.color.a = r, g, b, 1.0

        tail = Marker()
        tail.header.frame_id = self.frame
        tail.ns = ns + '_tail'; tail.id = 0
        tail.type = Marker.SPHERE; tail.action = Marker.ADD
        dx, dy, dz = self._rot_x(pose.orientation, -self.TAIL_OFFSET)
        tail.pose.position.x = pose.position.x + dx
        tail.pose.position.y = pose.position.y + dy
        tail.pose.position.z = pose.position.z + dz
        tail.pose.orientation.w = 1.0
        tail.scale.x = tail.scale.y = tail.scale.z = self.TAIL_DOT
        tail.color.r, tail.color.g, tail.color.b, tail.color.a = r, g, b, 1.0

        return [a, body, tail]

    def _path_marker(self):
        m = Marker(); m.header.frame_id = self.frame; m.ns = 'car_path'; m.id = 1
        m.type = Marker.LINE_STRIP; m.action = Marker.ADD; m.scale.x = 0.12
        m.color.r, m.color.g, m.color.b, m.color.a = 0.1, 0.8, 0.2, 1.0
        for x, y, z in self.car_path:
            p = Point(); p.x, p.y, p.z = x, y, z + 0.08; m.points.append(p)
        return m

    def on_targets(self, msg):
        # 目标与车 / 己方机**同一套画法**：_body_markers 产出箭头 / 位置球 / 箭尾点。
        # 用 startswith('target') 过滤，覆盖 'target_*' / 'target_*_body' / 'target_*_tail'。
        ms = [m for m in self.dyn.markers if not m.ns.startswith('target')]
        idx = 100
        for t in msg.tracks:
            # p.orientation 在 gt_adapter 里有填（世界 ENU yaw）
            ms.extend(self._body_markers('target_%d' % idx, t.pose.pose, (1.0, 0.0, 0.0)))
            idx += 1
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
        if self.car_path:
            out.markers.append(self._path_marker())
        if self.car_pose is not None:
            out.markers.extend(self._body_markers('car', self.car_pose, (0.1, 0.8, 0.2)))
        if self.own_pose is not None:
            out.markers.extend(self._body_markers('own_uav', self.own_pose, (0.1, 0.3, 1.0)))
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
