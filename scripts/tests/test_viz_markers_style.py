"""viz_markers 样式契约（L2 静态 + 纯函数，不启 ROS 节点 / 不启仿真）。

守护现行口径不被顺手改坏：
  三机**只画真实模型**（无箭头 / 无文字 / 无位置球，2026-11-08 用户裁定）；
  车路径 colors[] 与 points 等长且非空；
  **障碍框层已整体退役**（2026-11-08 Q2/Q7：只显示 /agc/map 栅格，
   `confidence_color` / `on_obstacles` 不得复活）；三机 RGB 不漂移；
  (ns,id) 唯一；.rviz 分组与机位存在（由 test_rviz_config_contract 另守）。
"""

from __future__ import annotations

import ast
import importlib.util
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
VIZ = os.path.join(ROOT, 'src', 'agc_task', 'scripts', 'viz_markers.py')


def _src():
    return open(VIZ, encoding='utf-8').read()


def _module():
    """真实 import（工作区已 source install 时可用）；不可用则退化为 AST 检查。"""
    spec = importlib.util.spec_from_file_location('viz_markers_style', VIZ)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_confidence_color_is_gone_not_revived():
    """**判据反转**（2026-11-08 用户裁定 Q2/Q7，批次 3）：`confidence_color` 已随框层退役。

    改造前它给障碍框按置信度着色；框删除后这个纯函数**没有消费者**，
    留着就是下次有人"顺手接回来"的入口。本判据从"必须存在且三点不同"
    反转为"**不得存在**"，防止静默复活。
    """
    src = _src()
    assert 'confidence_color' not in src, (
        'confidence_color 已随障碍框层退役（Q2：只显示栅格），不得复活')
    # 依赖它的两条颜色常量也不得残留
    assert '1.0, 0.3, 0.3, 0.5' not in src, '红框色常量不得残留'


def test_vehicle_is_mesh_only_no_arrow_no_label():
    """三机只画模型：**不得**再有箭头 / 文字 / 位置球 / 箭尾点。

  2026-11-08 用户裁定「去掉字和箭头就完美了」。上一版这些叠加物把模型盖住，
  标签还压住机体——所以这里守的是"**没有**它们"，与旧版判据正好相反。
    """
    src = _src()
    for gone, why in (
        ('Marker.ARROW', '箭头已按用户裁定删除'),
        ('Marker.TEXT_VIEW_FACING', '文字标签已按用户裁定删除'),
        ("'_label'", '标签 ns 已删除'),
        ("'_tail'", '箭尾定位点已删除'),
    ):
        assert gone not in src, '%s（不得复活）：%s' % (why, gone)
    assert 'return [body]' in src, '_body_markers 只返回模型一个 marker'
    # 三机 RGB：车绿 / 己方机蓝 / 目标红，逐值锁定（去掉标签后**颜色是唯一辨识手段**）
    for token in ("(0.1, 0.8, 0.2)", "(0.1, 0.3, 1.0)", "(1.0, 0.0, 0.0)"):
        assert token in src, '三机既定配色缺失：%s' % token


def test_body_uses_scene_meshes():
    """机体主路径 = 真实 mesh，资产是**场景里同一批**，带缺失回退。

  四条不变量，每条都对应一种会静默画错的错法：
   ① 车用本仓 Husky `base_link.stl`、机用 PX4 pin 的 x500 机身 `.dae`（不新增第三方资产）；
   ② `MESH_RESOURCE` 且**朝向随 pose**（漏了就横着飞）；
   ③ mesh 不可用时**回退**几何体（缺工具链不得让整层可视化失效）；
   ④ 机身沿用 SDF 的绕 Z π + 抬 2.5 cm（不照抄会与 Gazebo 里朝向相反）。
    """
    src = _src()
    assert 'Marker.MESH_RESOURCE' in src, '机体主路径须为 MESH_RESOURCE'
    assert 'agc_car/meshes/base_link.stl' in src, '车须用本仓 Husky 车体 mesh（场景同一份）'
    assert "'x500_base'" in src and "'NXP-HGD-CF.dae'" in src, (
        '机须用 PX4 pin 的 x500 机身 mesh（场景同一份）')
    assert 'body.pose.orientation = pose.orientation' in src, (
        'mesh 机体朝向必须随 pose（否则横着飞）')
    # 去掉标签后颜色是唯一辨识手段 ⇒ 必须**覆盖**贴图，否则两台 x500 分不清。
    assert 'body.mesh_use_embedded_materials = False' in src, (
        '须用辨识色覆盖 mesh 贴图（否则己方机与目标同为碳纤维色，无法区分）')
    assert 'if mesh_uri:' in src and 'else:' in src, 'mesh 不可用时须有回退分支'
    assert '_mesh_uri' in src and 'use_protocol=False' in src, (
        '资源解析须拿裸路径（resource_retriever 默认返回 file:// 前缀，不可直接当文件用）')
    assert 'UAV_MESH_YAW = math.pi' in src and 'UAV_MESH_OFFSET_Z = 0.025' in src, (
        '机身须照抄 SDF 的绕 Z π + 抬 2.5 cm，否则与 Gazebo 朝向/高度不一致')
    # 不新增第三方资产：两个 mesh 都必须已在本仓或 pin 的工具链里。
    for rel in ('src/agc_sim/models/agc_car/meshes/base_link.stl',
                'toolchain/PX4-Autopilot/Tools/simulation/gz/models/x500_base/meshes/NXP-HGD-CF.dae'):
        assert os.path.isfile(os.path.join(ROOT, rel)), (
            '机体 mesh 必须是仓内既有资产（不得引入新第三方资产）：缺 %s' % rel)


def test_path_gradient_and_ns_uniqueness():
    """car_path 的 colors[] 与 points 等长；机体 marker 有独立 ns。"""
    src = _src()
    assert 'm.colors.append(ColorRGBA(' in src, '车路径须逐点写入 colors 数组实现时间渐变'
    assert 'len(self.car_path)' in src, '渐变须按点数归一化'
    assert "ns + '_body'" in src, '机体 marker 须有独立 ns'


def test_obstacle_box_layer_is_retired():
    """**判据反转**（2026-11-08 用户裁定 Q2/Q7，批次 3）：障碍框层整体退役。

    用户原话："红框其实没有存在的必要，直接显示栅格，这样最真实，车用的是什么就看到什么"。
    因此 viz_markers 不得再订阅任何障碍话题、不得再画障碍 marker；
    障碍**只**以 `/agc/map` 栅格呈现（RViz 的 Map display）。
    """
    src = _src()
    for gone, why in (
            ('on_obstacles', '障碍框回调已删'),
            ('/agc/map/obstacles', '合并后的障碍框话题已退役'),
            ("'/agc/obstacles'", '原始观测话题也不得由 viz 直接消费'),
            ('ObstacleTrackArray', '不再需要障碍消息类型'),
    ):
        assert gone not in src, '%s（不得复活）：%s' % (why, gone)
    # 明确记录"为什么删"——防止后来者以为是遗漏
    assert '车用的是什么就看到什么' in src or '栅格' in src, (
        '必须留下"障碍只以栅格呈现"的口径说明')


def test_static_geometry_recedes_to_background():
    """静态障碍色更冷更淡（Q3 微调），不再用旧的亮蓝灰。"""
    src = _src()
    assert '0.55, 0.62, 0.72, 0.28' in src, '静态障碍须退到背景'
    assert '0.72, 0.76, 0.82, 0.45' not in src
