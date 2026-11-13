#!/usr/bin/env python3
"""viz_markers —— 演示用 RViz 叠加层（R6，2026-10-30）。

**为什么单独一个节点、而不住在 GUI 里**：本机 `ros_gz_bridge` 不映射
`visualization_msgs`（实测：只映射 sensor_msgs / nav_msgs / geometry_msgs / tf2 /
ros_gz_interfaces），所以"在 Gazebo GUI 里叠加"技术上走不通；而 RViz 对
OccupancyGrid / Path / LaserScan / MarkerArray 是原生支持。分工：
 * **GZ GUI** = 纯场景（好看）
 * **RViz** = 语义层（可读）：栅格 / 路径 / 三机 / 障碍
 （三机 = 车 / 己方机 / 目标，统一由 `_body_markers` 画**一个真实模型**：
  车用本仓 Husky 车体 mesh、机用 PX4 x500 机身 mesh，与 Gazebo 场景同一批资产；
  **不画箭头、不画文字、不画位置球**——2026-11-08 用户裁定「去掉字和箭头」。
  三机靠**辨识色**区分：车绿 / 己方机蓝 / 目标红）
 （**不含 8 字轨迹**——反无人机场景不用预设轨迹，2026-11-04 用户裁定删除）

发布的 marker 全部**由配置文件派生**（经 `agc_sim/launch/world_map.py` 单一清单），
不手写坐标；`/agc/viz/markers` 只读不参与任何决策。
"""
import math
import os

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy

from geometry_msgs.msg import Point
from std_msgs.msg import ColorRGBA
from visualization_msgs.msg import Marker, MarkerArray
from nav_msgs.msg import Odometry
from agc_msgs.msg import TargetTrackArray


class VizMarkers(Node):
    def __init__(self):
        super().__init__('viz_markers')
        self.declare_parameter('world_map', '')
        self.declare_parameter('frame_id', 'world')
        # 机体 mesh 的资源根：PX4 工具链的 gz 模型目录（launch 从 px4_paths 派生后传入）。
        # 空 = 找不到工具链 ⇒ 机体退回几何体，可视化照常工作。
        self.declare_parameter('px4_models_dir', '')
        self.frame = self.get_parameter('frame_id').value
        self.static = MarkerArray()
        self.dyn = MarkerArray()
        self._build_static()
        latched = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                             reliability=ReliabilityPolicy.RELIABLE)
        self.pub = self.create_publisher(MarkerArray, '/agc/viz/markers', latched)
        self.create_subscription(TargetTrackArray, '/agc/targets', self.on_targets, 10)
        # **2026-11-08 用户裁定 Q2/Q7（批次 3）**：障碍框层已整体退役。
        # 障碍**只以 `/agc/map` 栅格呈现**（RViz 的 Map display）——"车用的是什么就看到什么"。
        # 为什么删：框是"连通域的轴对齐外接矩形"，不是障碍本身
        # （实测框面积/真实足迹 1.65×，最差 14×35.5 m、fill=0.30），
        # 而且它与栅格是**两份表示**，必须保持同源却永远对不齐。
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
                    # 静态几何退到背景：更冷更淡，让 /agc/map 栅格与三机更突出。
                    m.color.r, m.color.g, m.color.b, m.color.a = 0.55, 0.62, 0.72, 0.28
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
            self.get_logger().warning('viz_markers：读不到几何文件（%s），静态层跳过' % exc)
            return None

    def on_car_odom(self, msg):
        p = msg.pose.pose.position
        self.car_pose = msg.pose.pose
        self.car_path.append((p.x, p.y, p.z))
        self.car_path = self.car_path[-500:]

    def on_own_odom(self, msg):
        self.own_pose = msg.pose.pose

    # ---- 三机外观：真实 mesh（2026-11-08，用户裁定「三机模型太丑」→「去掉字和箭头」）----
    # 用的都是**场景里正在渲染的同一批资产**，不新增第三方资产、不复制外部项目代码：
    #   车 = 本仓 Husky `base_link.stl`（与 Gazebo 里 agc_car 车体同一份，见第三方资产清单）
    #   机 = PX4 pin 的 x500 机身 `NXP-HGD-CF.dae`（与 Gazebo 里 x500 机身同一份，BSD）
    # 两者原生单位都是**米**（实测包围盒：车 0.81×0.57×0.23 m，机身 0.40×0.40×0.28 m）。
    GROUND_MESH = 'package://agc_sim/models/agc_car/meshes/base_link.stl'
    UAV_MESH = ('x500_base', 'meshes', 'NXP-HGD-CF.dae')
    # 机身 mesh 在 SDF 里是 `base_link_visual` 的 `<pose>0 0 .025 0 0 3.141592654</pose>`
    # ⇒ 相对 base_link 绕 Z 转了 π、抬了 2.5 cm。marker 必须施加**同一个**变换，
    # RViz 才与 Gazebo 一致（朝向反了会看起来"倒着飞"）。
    UAV_MESH_OFFSET_Z = 0.025
    UAV_MESH_YAW = math.pi
    # **显示放大**（不是物理尺寸）：真实车长 0.81 m、机身 0.40 m，在 RViz 默认 150 m 视距下
    # 只有几像素——那正是"看不见"的原始症状。**只影响 RViz 语义层，不碰 Gazebo 物理**。
    GROUND_MESH_SCALE = 2.0     # 车 → 约 1.6 m 长
    UAV_MESH_SCALE = 4.0        # 机 → 约 1.6 m 轴距
    # 回退几何体的尺寸（mesh 不可用时才用）。
    BODY_DOT = 1.20      # 机体位置球直径

    def _mesh_uri(self, is_ground):
        """机体 mesh 的 `file://` URI；不可用（缺文件 / 未配工具链目录）→ None。

  返回 None 时 `_body_markers` 回退到原来的 CUBE / 扁球——**可视化不得因缺资产而整体失效**，
  这是「取不到就报失败、不拿示意图冒充」的同一口径：回退后仍能看出机体位置与朝向。
        """
        if is_ground:
            import resource_retriever as rr
            try:
                return 'file://' + rr.get_filename(self.GROUND_MESH, use_protocol=False)
            except Exception:  # noqa: BLE001 —— 缺包 / 未 source 都只降级，不崩
                return None
        base = (self.get_parameter('px4_models_dir').value or '').strip()
        if not base:
            return None
        path = os.path.join(base, *self.UAV_MESH)
        return 'file://' + path if os.path.isfile(path) else None

    def _body_markers(self, ns, pose, color, is_ground=False):
        """一台机体 = **一个模型**（车 Husky 车体 / 机 x500 机身），不带箭头与文字。

  2026-11-08 用户裁定：「去掉字和箭头就完美了」—— 上一版箭头 + 球 + 尾点 + 标签
  把模型盖住了，且标签压住机体。现在只画模型本身，位置/朝向全由 mesh 的位姿表达。

  颜色**仍按三机辨识色给 mesh 上色**（车绿 / 己方机蓝 / 目标红）：
  去掉箭头和标签后，己方机与目标都是同一款 x500 机身，若不染色就完全分不清是谁
  （车是 Husky 底盘，外形本就不同）。这是**语义层**的辨识手段，不改变模型形状。

  mesh 不可用时回退几何体（车 CUBE 带朝向 / 机扁球），保证任何环境下都看得见。
  各 marker 必须用不同 ns，否则 RViz 按 (ns, id) 唯一标识，会互相覆盖。
        """
        r, g, b = color
        mesh_uri = self._mesh_uri(is_ground)

        body = Marker()
        body.header.frame_id = self.frame
        body.ns = ns + '_body'; body.id = 0
        body.action = Marker.ADD
        body.pose.position.x = pose.position.x
        body.pose.position.y = pose.position.y
        body.pose.position.z = pose.position.z
        if mesh_uri:
            # MESH_RESOURCE：朝向必须与机体一致（车的车头、机的机头都沿 +X），
            # 否则 mesh 会"横着走"。机身在 SDF 里额外绕 Z 转了 π、抬 2.5 cm，照抄。
            body.type = Marker.MESH_RESOURCE
            body.pose.orientation = pose.orientation
            s = self.GROUND_MESH_SCALE if is_ground else self.UAV_MESH_SCALE
            body.scale.x = body.scale.y = body.scale.z = s
            body.mesh_resource = mesh_uri
            # **不用**自带贴图：车身是深灰、机身是碳纤维，两者在深色背景上几乎看不出区别，
            # 且无法表达"谁是我方/谁是目标"。改为用辨识色覆盖（mesh.color 在
            # mesh_use_embedded_materials=false 时生效）。
            body.mesh_use_embedded_materials = False
            body.color.r, body.color.g, body.color.b, body.color.a = r, g, b, 1.0
            if not is_ground:
                # 机身 SDF 变换：绕 Z π + 抬 2.5 cm（随显示缩放同步抬高）。
                q = pose.orientation
                yaw = math.atan2(2.0 * (q.w * q.z + q.x * q.y),
                                 1.0 - 2.0 * (q.y * q.y + q.z * q.z))
                yaw += self.UAV_MESH_YAW
                body.pose.orientation.z = math.sin(yaw / 2.0)
                body.pose.orientation.w = math.cos(yaw / 2.0)
                body.pose.position.z = pose.position.z + self.UAV_MESH_OFFSET_Z * s
        else:
            body.type = Marker.CUBE if is_ground else Marker.SPHERE
            if is_ground:
                body.pose.orientation = pose.orientation
            else:
                body.pose.orientation.w = 1.0
            if is_ground:
                body.scale.x = self.BODY_DOT * 1.4
                body.scale.y = self.BODY_DOT
                body.scale.z = self.BODY_DOT * 0.45
            else:
                body.scale.x = body.scale.y = self.BODY_DOT
                body.scale.z = self.BODY_DOT * 0.55   # 扁球，区别于车
            body.color.r, body.color.g, body.color.b, body.color.a = r, g, b, 1.0

        # 只有模型一个 marker：箭头 / 文字 / 位置球 / 箭尾点**全部不再画**。
        # 用户 2026-11-08 裁定「去掉字和箭头就完美了」——那些叠加物把模型盖住了。
        # 机体位置与朝向由 mesh 的 pose 直接表达，不需要额外图形去"指"。
        return [body]

    def _path_marker(self):
        m = Marker(); m.header.frame_id = self.frame; m.ns = 'car_path'; m.id = 1
        m.type = Marker.LINE_STRIP; m.action = Marker.ADD; m.scale.x = 0.12
        m.color.r, m.color.g, m.color.b, m.color.a = 0.1, 0.8, 0.2, 1.0
        n = max(1, len(self.car_path))
        for i, (x, y, z) in enumerate(self.car_path):
            p = Point(); p.x, p.y, p.z = x, y, z + 0.08; m.points.append(p)
            # 时间渐变：越新越亮越暖（老点冷绿半透明 → 新点黄绿不透明）。
            # colors[] 长度必须与 points 一致，否则 RViz 按点索引取色会越界。
            t = i / float(n - 1) if n > 1 else 1.0
            m.colors.append(ColorRGBA(
                r=0.10 + 0.75 * t, g=0.35 + 0.55 * t, b=0.20 - 0.10 * t,
                a=0.35 + 0.65 * t))
        return m

    def on_targets(self, msg):
        # 目标与车 / 己方机**同一套画法**：_body_markers 只产出一个模型 marker。
        # 用 startswith('target') 过滤覆盖 'target_*' 全部 ns。
        ms = [m for m in self.dyn.markers if not m.ns.startswith('target')]
        idx = 100
        for t in msg.tracks:
            # p.orientation 在 gt_adapter 里有填（世界 ENU yaw）。
            # 目标保持既定纯红（证据载体，不漂移）；confidence 只作用于感知障碍。
            ms.extend(self._body_markers(
                'target_%d' % idx, t.pose.pose, (1.0, 0.0, 0.0)))
            idx += 1
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
            out.markers.extend(self._body_markers(
                'car', self.car_pose, (0.1, 0.8, 0.2), is_ground=True))
        if self.own_pose is not None:
            out.markers.extend(self._body_markers(
                'own_uav', self.own_pose, (0.1, 0.3, 1.0)))
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
