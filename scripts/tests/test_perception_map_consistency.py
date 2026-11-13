"""感知地图链：四项一致性判据（L2 静态 + 数值，不启 ROS / 不启仿真）。

四项：与物理世界一致 / 传感器校准 / 感知新鲜 / 规划与安全层同源。

为什么是静态：这四项的「可被顺手改坏」点都在源码与配置口径里（硬编码内参、
恒 true 的时效、第二个 /agc/map 发布者、把动态 marking 塞进 static 层），
用静态断言比活仿真更早、更稳地拦住。数值部分（投影几何）由
src/agc_perception/test/test_nadir_geometry.cpp 的 gtest 覆盖。
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PERCEPTION = ROOT / 'src' / 'agc_perception'
NADIR_GEOM = PERCEPTION / 'include' / 'agc_perception' / 'nadir_geometry.hpp'
# **相机几何的唯一来源**（2026-11-09）：轴映射、位姿、反投影、时间插值都在这里，
# 不依赖 OpenCV，`map_adapter` 与 `nadir_projection` 共用同一份。
CAM_GEOM = PERCEPTION / 'include' / 'agc_perception' / 'camera_geometry.hpp'
FOOTPRINT_GEOM = PERCEPTION / 'include' / 'agc_perception' / 'footprint_geometry.hpp'
NADIR_NODE = PERCEPTION / 'src' / 'nadir_projection.cpp'
MAP_ADAPTER = PERCEPTION / 'src' / 'map_adapter.cpp'
GRID_HPP = PERCEPTION / 'include' / 'agc_perception' / 'log_odds_grid.hpp'
PERC_CFG = PERCEPTION / 'config' / 'perception.yaml'
BRINGUP = PERCEPTION / 'launch' / 'perception_bringup.launch.py'
COSTMAP = ROOT / 'src' / 'agc_ground' / 'config' / 'costmap.yaml'
BASELINE = ROOT / 'src' / 'agc_ground' / 'src' / 'ground_baseline.cpp'


def _text(p: Path) -> str:
    return p.read_text(encoding='utf-8')


def _code(p: Path) -> str:
    """去注释（注释是给人看的证据，结构断言看代码本身）。"""
    txt = _text(p)
    txt = re.sub(r'/\*.*?\*/', '', txt, flags=re.S)
    return '\n'.join(re.sub(r'//.*$', '', ln) for ln in txt.splitlines())


# ---------------------------------------------------------------- ① 与物理世界一致
def test_projection_geometry_is_calibrated_not_guessed():
    """像素→地面净轴映射由 gz GUI 实测靶点标定，且有可执行数值单测守护。"""
    # 净轴映射 (Δu,Δv,1) → (−Δv,−Δu,−1) 必须写死在**唯一来源**里
    # （2026-11-09 起在 camera_geometry.hpp 的 opticalRayToBody；两个节点共用）。
    assert '{-ray.y, -ray.x, -ray.z}' in _code(CAM_GEOM), (
        '净轴映射必须与 GUI 实测靶点一致（u↔v 互换 + 双符号反转）')
    # 两个入口必须都走它 —— 不得各写一套（那正是几何分叉的入口）
    cam = _code(CAM_GEOM)
    assert cam.count('opticalRayToBody(') >= 3, (
        'pixelToGround / pixelDepthToWorld 必须都调用 opticalRayToBody（同一份轴映射）')
    assert 'body_ray{-ray.y' not in _code(NADIR_GEOM), (
        'nadir_geometry.hpp 不得再自己写一遍轴映射（唯一来源是 camera_geometry.hpp）')
    # 实测靶点数值被单测写死
    t = _text(ROOT / 'src' / 'agc_perception' / 'test' / 'test_nadir_geometry.cpp')
    assert 'GuiMeasuredTargetReproduced' in t and '299.0, 199.0' in t, (
        'GUI 实测靶点（像素 299,199 → world 2,1）必须有数值回归单测')
    # 2026-11-08：主路径改为**深度反投影**，高度由深度直接观测并写入 size.z。
    # 判据随之反转：必须用 pixelDepthToWorld（而不是投到地面平面），且必须写 z。
    node = _code(NADIR_NODE)
    assert 'pixelDepthToWorld' in node, (
        '障碍 3D 点必须由**深度反投影**得到（pixelDepthToWorld）；'
        '退回 pixelToGround 会把高层建筑的侧墙糊成影子（yard 实测 IoU 0.363）')
    assert 'pixelToGround' not in node, (
        '主路径不得再用 pixelToGround —— 它假设"每个像素都落在地面"，'
        '正是"影子"的根因。该函数只保留在头文件里作无深度时的对照/回退说明')
    assert 't.size.z = st.sz' in node, (
        '障碍高度必须由深度观测写入 size.z（2026-11-08 用户裁定）；'
        '走平滑后的 st.sz（单帧 sz 实测跨度可达 3 m，直接用会抖）')
    # 跳变防护：id 必须来自跨帧关联，不得退回"质心量化格"
    assert 'associateNearest' in node, (
        'id 必须由跨帧最近邻关联分配；用量化格会让质心一抖就翻格，'
        '下游同一障碍反复画/擦（实测相邻帧 id 集合 Jaccard 仅 0.56）')
    assert 'llround(o.cx / cell_m_)' not in node, (
        '不得退回质心量化格分配 id（这正是跳变的根因）')
    # 参数取值与文档口径必须一致（2026-11-08 用户裁定 2.5 m）。
    #
    # **2026-11-08 判据反转（用户裁定 Q26）**：最小可测尺寸从**像素**改成**物理量**。
    # 原因：固定像素门限会让判据**随飞行高度漂移** —— 飞低了 GSD 变小，同样的像素数
    # 对应更小的物理尺寸 ⇒ 突然多出一堆 0.05 m 碎片；飞高了则细杆被静默吞掉。
    # 自主定高上线后，"20 px" 不再有唯一物理解释。
    assert 'declare_parameter<double>("min_obstacle_side_m", 0.24)' in node, (
        '最小可测尺寸必须是**物理量** min_obstacle_side_m（缺省 0.24 m）：'
        '固定像素门限会随飞行高度漂移，与自主定高冲突')
    assert 'declare_parameter<int>("min_area_px"' not in node, (
        '不得保留固定像素门限 min_area_px —— 它已由物理量 + GSD 实时换算取代')
    assert 'minAreaPxForPhysicalSize' in node, (
        '物理门限必须经 minAreaPxForPhysicalSize 按当前 GSD 换算成像素门限')
    assert 'declare_parameter<double>("assoc_gate_m", 2.5)' in node, (
        'assoc_gate_m 缺省必须是 2.5：连通域帧间分裂/合并时，碎片质心与母体差可达 2 m 量级')
    # 2026-11-08 Q1 丙：指数平滑换成"中位数 + MAD 剔除离群"。
    # 理由：形状抖动的根因是**点集每帧变化**（侧墙可见性），且偶尔出现大幅跳变；
    # 指数平均会被离群帧拉走，中位数不会。
    assert 'robustEstimate' in node and 'robustEstimateAngle' in node, (
        'OBB 尺寸/朝向必须走稳健估计（中位数 + MAD 剔除离群）；'
        '指数平滑会被"偶尔大幅跳一下"的离群帧拉走')
    assert 'smoothScalar' not in node, (
        '不得退回指数平滑——它对离群不稳健（实测一次 5.0 的离群会把估计拉到 2.4 以上）')
    assert 'shape_window_n' in node and 'shape_mad_k' in node, (
        '窗口长度与 MAD 倍数必须是可配参数')
    assert 'minAreaRect' in _text(NADIR_GEOM), '障碍 footprint 应来自连通域外接 OBB'
    # 无深度时必须**跳过**，不得退回地面投影（错误地图比暂时无地图更危险）
    assert 'depth_tol_s_' in node, (
        '必须校验深度存在性与时间对齐：错位会把墙深套到别的像素上')
    # 2026-11-09：深度不再"只存最新一张"，而是环形缓冲 + 按标签时间戳选最近一帧
    assert 'depth_buf_' in node and 'depth_buffer_n' in node, (
        '深度必须按**标签时间戳**从环形缓冲里选最近一帧；'
        '只存最新一张时标签帧落后半帧就会配错帧')
    # 位姿必须按同一时间戳查询/插值，不得用"最新 odom"
    assert 'poseAtTime' in node and 'odom_buf_' in node, (
        '位姿必须按标签时间戳插值（poseAtTime）；用最新 odom 会偏 0.2–0.4 m')
    assert 'quatUnit' in node, '姿态必须校验单位四元数（投影公式默认归一化）'
    assert 'min_obstacle_side_m_' in node, (
        '最小可测尺寸须为物理量 min_obstacle_side_m（Q26 判据反转）')


# ---------------------------------------------------------------- ② 传感器校准
def test_intrinsics_and_extrinsics_are_not_hardcoded():
    """内参来自 CameraInfo 的 k 矩阵、外参来自 odom，均不硬编码为常量。"""
    node = _code(NADIR_NODE)
    assert 'intrinsicsFrom(*m, k)' in node, '内参必须从 sensor_msgs/CameraInfo 的 k 矩阵解析'
    assert 'ci.k[0]' in node and 'ci.k[4]' in node and 'ci.k[2]' in node and 'ci.k[5]' in node, (
        '内参须取 k[0]=fx / k[4]=fy / k[2]=cx / k[5]=cy，不得写死')
    # ros_gz_bridge 以 SENSOR_DATA（best-effort）发布 camera_info；订阅必须同为
    # best-effort，否则 RELIABILITY_QOS_POLICY 不兼容、消息一条都收不到（实链取证）。
    assert 'rclcpp::SensorDataQoS()' in node, (
        'camera_info 订阅必须 SensorDataQoS（对齐桥的 best-effort 发布）')
    # 精确检查 info_topic_ 那次订阅（publisher 用 transient_local 是合理的，别误伤）
    info_sub = re.search(
        r'info_topic_,\s*rclcpp::SensorDataQoS\(\)', node)
    assert info_sub, (
        'info_topic_ 的订阅必须用 SensorDataQoS；不得改 reliable/transient_local'
        '（与 ros_gz_bridge 的 best-effort 发布不兼容，实链取证）')
    assert 'poseFrom(*m)' in node, '外参须从 /agc/air/odom 读取'
    assert 'PoseSample' in node, 'odom 必须以带时间戳的样本存缓冲（按图像时间戳查询）'
    assert 'create_subscription<nav_msgs::msg::Odometry>' in node, (
        '机体位姿必须订阅 odom（相机→机体固定变换 + 机体→world 动态姿态）')
    # 内参话题是分割相机自己的 camera_info（gz 实测发布），且由 config 注入
    cfg = _text(PERC_CFG)
    assert 'camera_info_topic: "/agc/air/nadir/seg/camera_info"' in cfg
    # 安装高只有一个常量来源（2026-11-09 移到 camera_geometry.hpp）
    h = _text(CAM_GEOM)
    assert h.count('kCamMountZ') >= 2, '相机安装高应为单一常量（声明 + 使用）'
    assert '0.242' in h, '安装高 0.242 须与 model.sdf 的 nadir_cam_joint 一致'


# ---------------------------------------------------------------- ③ 感知新鲜
def test_map_validity_depends_on_perception_freshness():
    """/agc/map/valid 不得恒 true；必须依赖感知源时效。"""
    code = _code(MAP_ADAPTER)
    assert 'return true;' not in code.split('bool knowledge_current()')[1].split('}')[0], (
        'knowledge_current 不得恒 true（改造前旧口径）')
    kc = code.split('bool knowledge_current()')[1].split('}')[0]
    assert 'have_source_' in kc and 'source_max_age_s_' in kc, (
        '知识时效须由「收到过感知源 + 源静默不超过上限」共同决定')
    assert 'last_source_s_ = now().seconds()' in code, '收到 /agc/obstacles 须刷新源时效'
    assert 'valid_pub_' in code and 'knowledge_current()' in code
    # 完全替代：不再加载静态先验
    assert 'loadStaticObstacles();' not in code, (
        '感知地图模式下不得加载静态先验（完全替代，无两源回退）')
    assert 'create_subscription<agc_msgs::msg::ObstacleTrackArray>' in code, (
        '必须恢复 /agc/obstacles 订阅（/agc/map 的唯一障碍来源）')


# ---------------------------------------------------------------- ④ 规划与安全层同源
def test_planner_and_safety_share_one_map_source():
    """/agc/map 唯一发布者、costmap static_layer 消费同一话题、无第二发布者。"""
    # 唯一发布者：扫 src 下 create_publisher<nav_msgs::msg::OccupancyGrid>
    pubs = []
    for f in (ROOT / 'src').rglob('*.cpp'):
        code = _code(f)
        if 'nav_msgs::msg::OccupancyGrid' in code and 'create_publisher' in code:
            if re.search(r'create_publisher<nav_msgs::msg::OccupancyGrid>', code):
                pubs.append(str(f.relative_to(ROOT)))
    assert pubs == ['src/agc_perception/src/map_adapter.cpp'], (
        '/agc/map 的 OccupancyGrid 发布者必须只有 map_adapter，实际 %r' % pubs)
    # costmap static_layer 订阅同一话题
    cm = _text(COSTMAP)
    assert 'map_topic: "/agc/map"' in cm and 'static_layer' in cm, (
        'costmap static_layer 须消费 /agc/map（规划与安全层同源）')
    assert 'map_subscribe_transient_local: True' in cm
    # 地图签名仍只计 static_layer 的 LETHAL_OBSTACLE（动态 marking 不触发伪重规划）
    bl = _text(BASELINE)
    assert 'static_layer' in bl and '254' in bl, (
        '重规划签名须只计 static_layer 的 LETHAL_OBSTACLE（254），不含动态 marking / inflation')
    # 感知地图不走「新增分支参数」的旧路：launch 无 obstacles_source 声明
    ld = _text(BRINGUP)
    assert "DeclareLaunchArgument('obstacles_source'" not in ld, (
        '不得把 obstacles_source 复活成 launch 分支参数（路线分支治理）')
    assert "'obstacles_source': 'nadir_segmentation'" in ld, (
        'obstacles_source 应作为节点参数值只折入内容身份 hash')


# ---------------------------------------------------------------- ⑤ 覆盖边界与文档一致
def test_coverage_boundary_matches_documented_numbers():
    """`/agc/map` 的两个覆盖边界必须与根 README 写的一致（改参数必须同步改文档）。

 2026-11-08 用户裁定"小障碍交给车激光"后，这两个数字成了**解读地图数据的前提**：
   * 视场半径 = H·tan(HFOV/2)，决定地图只覆盖 UAV 周边多大；
   * 最小可测尺寸 = min_obstacle_side_m（**物理量**，2026-11-08 Q26 由像素门限改来），
     决定哪些细杆不进地图。
 任一参数被改而文档没跟上，读者就会拿错前提去解读规划结果。
    """
    import math
    # 相机参数从模型 SDF 读取，本文件不复述
    sdf = _text(ROOT / 'src' / 'agc_sim' / 'models' / 'agc_x500_nadir' / 'model.sdf')
    hfov = float(re.search(r'<horizontal_fov>\s*([0-9.]+)\s*</horizontal_fov>', sdf).group(1))
    width = int(re.search(r'<width>\s*(\d+)\s*</width>', sdf).group(1))
    mount = 0.242                      # nadir_cam_link 的 z 偏移（SDF fixed joint）
    own_alt = 14.0                     # yard 的 own_track_m（地图属性，见 maps/yard.yaml）
    H = own_alt + mount
    gsd = H / (width / 2.0 / math.tan(hfov / 2.0))
    radius = H * math.tan(hfov / 2.0)

    cfg = _text(PERC_CFG)
    # 2026-11-08 Q26：最小可测尺寸已改为**物理量**，不再由像素数反算。
    m = re.search(r'^\s*min_obstacle_side_m:\s*([0-9.]+)', cfg, re.M)
    assert m, 'perception.yaml 缺少 min_obstacle_side_m（物理量门限）'
    min_side = float(m.group(1))
    # 反向核对：该物理量在当前相机下换算出的像素门限必须与 README 的能力描述一致。
    #
    # **2026-11-09 定稿（相机 1152²@130°）**：判据改为**按恒等式推导**，不写死数值区间。
    # 原因：写死区间（如"40–120 px"）在每次改相机时都会误报，而那正是相机该变的场合；
    # 真正要守的是"**物理量 ↔ 像素数 ↔ 覆盖半径**三者自洽"，这可以用恒等式表达：
    #
    #   正下视透视：GSD = H/f = 2R/N   ⇒   min_area_px = (min_side/GSD)²
    #   1152²@130°：f=268.6、GSD=5.30 cm/px ⇒ 0.24 m 对应 **20 px**
    #   （恰好回到改造前的 20 px 口径 —— 这是选 1152² 而非 2048² 的核心收益：
    #    精度口径不变，覆盖半径从 12.73 提到 30.5 m）
    min_area_px = (min_side / gsd) ** 2
    # 自洽判据：像素门限必须等于 (min_side·N/(2R))²，与直接算 GSD 的结果一致
    expected_px = (min_side * width / (2.0 * radius)) ** 2
    assert abs(min_area_px - expected_px) < 0.5, (
        'GSD 与"覆盖半径/像素数"两种算法不自洽：%.2f vs %.2f'
        % (min_area_px, expected_px))
    # 精度口径必须保持在改造前的量级（20±3 px）：这是"不因扩覆盖而牺牲精度"的闸门
    assert abs(min_area_px - 20.0) < 3.0, (
        'min_obstacle_side_m=%.2f m 在当前相机下换算成 %.1f px，'
        '偏离改造前 20 px 口径（20±3）——若这是有意的精度变更，须同步改 README'
        % (min_side, min_area_px))

    readme = _text(ROOT / 'README.md')
    # 半径：2026-11-08 Q22 扩覆盖后为 30.5 m（原 17 m 是**水平半宽**，且当时是 4:3 矩形）
    assert abs(radius - 30.5) < 1.0, (
        '视场半径推导值 %.2f m 与 README 的 30.5 m 不符（1152²@130°、H=%.2f m）'
        % (radius, H))
    assert '30.5' in readme, 'README 必须写明保证覆盖半径约 30.5 m'
    # 必须写明"原 17 m 是水平半宽、实际是矩形"这段更正（否则读者会拿旧口径解读）
    assert '水平半宽' in readme, 'README 必须说明旧口径"17 m"是水平半宽而非保证半径'
    # 最小可测尺寸：README 写的是 0.24 m
    assert abs(min_side - 0.24) < 0.02, (
        'min_obstacle_side_m=%.3f m 与 README 的 0.24 m 不符——'
        '改参数必须同步改 README 已知边界' % min_side)
    assert '0.24' in readme, 'README 必须写明最小可测尺寸约 0.24 m'
    # 细杆必须被点名（否则读者不知道"地图里没有灯杆"是设计而非 bug）
    for token in ('灯杆', '激光'):
        assert token in readme, 'README 已知边界必须写明细杆由车激光局部感知（缺 %r）' % token


# ---------------------------------------------------------------- ⑥ 融合归属：地面侧
def test_fusion_belongs_to_ground_side():
    """**判据反转**（2026-11-08 用户裁定 Q7，批次 3）：物体级融合随框层**整体退役**。

    改造前这条判据守的是"碎片合并必须在 map_adapter（地面侧）"。
    但碎片合并的**唯一产出就是那个外接框**；框删除后合并层失去存在理由，
    而且它与"逐点落格 + log-odds 累积"是两套互相冲突的表示
    （合并层喂的是 OBB，累积层要的是点）。

    **不是"融合职责换地方了"，而是这条职责消失了**：
    同帧碎片在栅格层天然合并（落在同一个连通证据里），不需要物体级打包。
    """
    adapter = _code(MAP_ADAPTER)
    for gone, why in (
            ('mergeFragments', '物体级碎片合并随框层退役'),
            ('/agc/map/obstacles', '合并后的框话题已退役'),
            ('merge_gate_m', '合并门参数已退役'),
    ):
        assert gone not in adapter, '%s（不得复活）：%s' % (why, gone)

    # 飞机侧仍不得做物体级融合（这条**不变**，只是对象换成了栅格化）
    node = _code(NADIR_NODE)
    assert 'mergeFragments' not in node, '飞机侧不得做物体级融合'

    # viz 只显示栅格，不再消费任何障碍框话题
    viz = _code(ROOT / 'src' / 'agc_task' / 'scripts' / 'viz_markers.py')
    assert '/agc/map/obstacles' not in viz, 'viz 不得再消费框话题（Q2：只显示栅格）'
    assert '/agc/obstacles' not in viz, 'viz 不得直接读原始观测'
    # 但栅格本身必须被 RViz 打开 —— 否则"只显示栅格"变成"什么都不显示"
    rviz = _text(ROOT / 'src' / 'agc_task' / 'config' / 'agc_demo.rviz')
    assert 'Value: /agc/map' in rviz, 'RViz 必须订阅 /agc/map'
    import yaml as _yaml
    cfg = _yaml.safe_load(rviz)
    def _walk(items):
        for it in items or []:
            yield it
            if it.get('Class') == 'rviz_common/Group':
                yield from _walk(it.get('Displays'))
    # 判据必须**按话题**而不是按 display 类型：`/agc/map` 与 `/agc/map/evidence`
    # 都是 `rviz_default_plugins/Map`（OccupancyGrid），按类型数个数会把诊断层
    # 误判成"重复订阅规划层"。本判据要守的是"规划风险图这一个订阅存在且默认开启"。
    map_disp = [d for d in _walk(cfg['Visualization Manager']['Displays'])
                if d.get('Class') == 'rviz_default_plugins/Map'
                and (d.get('Topic') or {}).get('Value') == '/agc/map']
    assert len(map_disp) == 1, '应恰好一个订阅 /agc/map 的 Map display'
    assert map_disp[0].get('Enabled') is True, (
        'Map display 必须**缺省开启**：障碍的唯一呈现就是这张栅格，'
        '关掉它等于"什么都不显示"（Q2 用户裁定）')
    # 证据层（ADR-0042，另一条话题、语义不同）：允许存在，但必须**缺省关闭**
    # —— 它是评价/诊断用图，不是规划呈现；开着会和风险图叠在一起，读不出风险梯度。
    evidence = [d for d in _walk(cfg['Visualization Manager']['Displays'])
                if (d.get('Topic') or {}).get('Value') == '/agc/map/evidence']
    assert len(evidence) == 1, '证据层必须恰好一个（ADR-0042）'
    assert evidence[0].get('Enabled') is False, (
        '证据层是诊断图层，必须缺省关闭（ADR-0042；避免与规划风险图叠加）')


def test_accumulation_size_comes_from_geometry_not_grid():
    """累积层尺寸必须从**几何参数**算，不能用 `grid_.width/height`。

 2026-11-08 实测踩过：首次 `onObstacles` 时 `grid_` 还没初始化（宽高为 0），
 用 `grid_.width/height` 会把累积层建成 0×0；之后每帧都"尺寸不符"重新 reset 成空，
 表现为**地图永远 occupied=0**（且无任何报错，是静默失败）。
    """
    adapter = _code(MAP_ADAPTER)
    assert 'lround(sx_ / res_)' in adapter, '累积层尺寸须由几何参数（sx_/res_）算'
    assert 'accum_.reset(grid_.width, grid_.height' not in adapter, (
        '不得用 grid_.width/height 初始化累积层（首帧为 0，会导致地图永远空）')


# ---------------------------------------------------------------- ⑦ 逐点表示（Q7/Q28）
def test_footprints_replace_boxes_as_the_map_input():
    """障碍表示必须是**足迹点**，不是外接框（2026-11-08 用户裁定 Q7/Q28）。

    为什么这条判据重要：外接框对 L 形/多栋/斜置实体必然包大（实测框面积/真实足迹
    1.65×，最差把 workshop_w + wall_w 包成 14×35.5 m、fill=0.30），且框边界随
    "连通域恰好切在哪里"跳变 —— 那是**表示误差**，不是障碍本身的属性。
    逐点落到格没有这两重误差。
    """
    node = _code(NADIR_NODE)
    adapter = _code(MAP_ADAPTER)
    cfg = _text(PERC_CFG)

    # 发布侧：必须发足迹点
    assert 'ObstacleFootprintArray' in node, (
        'nadir_projection 必须发布足迹点（ObstacleFootprintArray），'
        '而不是只发外接框')
    assert 'publishFootprints' in node, '必须有足迹点发布函数'
    # 消费侧：必须逐点落到格，不得只按框栅格化
    assert 'ObstacleFootprintArray' in adapter, 'map_adapter 必须订阅足迹点'
    assert 'onFootprints' in adapter, '必须有足迹点消费回调'
    # 逐点落格的关键形态：点坐标直接除格宽取格，不经过任何包络。
    #
    # **ADR-0040 起格宽是证据层分辨率**（`fres`），不是规划层的 `res_` ——
    # 0.5 m 只是规划消费格式，证据累积在 0.25 m 上。因此这里断言**意图**
    # （逐点 floor 取整）而不是某个变量名：变量名会随分层调整而变，
    # "不得先求包络再栅格化"才是要守的性质。
    assert 'worldToGrid(p.x, ox_, fres)' in adapter, (
        '足迹点必须逐点落格，并使用统一 worldToGrid 几何函数')
    assert 'worldToGrid(p.y, oy_, fres)' in adapter, (
        'y 方向同样必须逐点使用统一落格函数')
    # 落格用的格宽必须是**证据层**分辨率（ADR-0040）：若仍是规划层的 res_，
    # 说明证据层没有真的变细，0.5 m 的分辨率上限原样回来了。
    assert 'const double fres = perception_resolution_;' in adapter, (
        '逐点落格必须用证据层分辨率（perception_resolution_），'
        '而不是规划层的 res_ —— 否则 0.5 m 仍在承担感知表达，分层没有发生')
    # 话题必须在配置里单一来源
    assert 'footprint_topic' in cfg, 'footprint_topic 必须可配（单一来源）'
    assert '/agc/obstacle_footprints' in cfg


def test_footprint_points_respect_physical_min_size():
    """足迹点不得绕过"最小可测尺寸"判据。

    若把整张 mask 的点全发出去，孤立噪点会绕过 min_obstacle_side_m，
    让"细杆不进地图"这条已登记的能力边界失效。

    **2026-11-09 判据迁移（性能修复，语义不变）**：过滤位置从 `publishFootprints`
    内部（那里原先再跑一次 CC + `keep[]` 面积表）**前移**到点池
    `collectComponentPoints`。理由：同一张 mask 被跑了两次
    `connectedComponentsWithStats`，而 `aggregateObbs` 还按连通域各扫全图两遍
    （O(C·N²)，1152² 下 C=30 就要 89 ms，10 Hz 预算 100 ms 的临界点）。

    不变式本身没变，只是"在哪执行"变了，所以这里断言**新位置**执行同一件事：
    面积门限必须仍在**像素级**生效，且足迹点只能来自点池（不得回到全 mask 扫描）。
    """
    node = _code(NADIR_NODE)
    geom = _code(NADIR_GEOM)
    # 面积门限现在在点池收集处（头文件 collectComponentPoints）生效
    assert 'CC_STAT_AREA' in geom, (
        '连通域面积门限必须仍然生效；去掉它会让噪点绕过 min_obstacle_side_m')
    assert 'min_area' in geom, '点池必须按面积门限筛选连通域'
    # 2026-11-09：面积门限仍用 CC 的 AREA，但先做碎片合并（big/root 分组）
    assert 'CC_STAT_AREA' in geom and 'big[' in geom, (
        '面积门限必须仍以连通域 AREA 为准（不得因 z 无效点放宽）')
    assert 'FragmentMergeParams' in geom, (
        '必须先把邻近且高度一致的碎片并入母体，再判面积门限')
    assert 'min_area_px_' in node
    # 足迹点必须来自点池（点池只含达标连通域），不得回到"全 mask 再扫一遍"
    assert 'collectComponentPoints' in node, (
        '足迹点必须复用点池 collectComponentPoints（它已按面积门限筛过连通域）')
    assert 'publishFootprints' in node, '必须有足迹点发布函数'
    # 反例闸门：publishFootprints 内部不得再出现第二次 connectedComponents
    fp = node[node.index('void publishFootprints'):]
    fp = fp[:fp.index('footprint_pub_->publish(out);')]
    assert 'connectedComponents' not in fp, (
        'publishFootprints 内不得再跑一次连通域分析 —— 那正是本次修复消掉的重复开销')
    assert 'comp_points' in fp, 'publishFootprints 必须消费点池 comp_points'


# ---------------------------------------------------------------- ⑧ 框层退役（Q2/Q7）
def test_box_layer_fully_retired_no_resurrection_path():
    """障碍框层必须**整体**退役，且不留下任何"顺手接回来"的入口。

    2026-11-08 用户裁定 Q2："红框其实没有存在的必要，直接显示栅格，
    这样最真实，车用的是什么就看到什么"。

    这条判据检查的不是"某个函数名消失"，而是**整条链**都断了：
    产出（extractBoxesFromGrid）→ 话题（/agc/map/obstacles）→ 消费（viz）→ 配置（merge_gate_m）。
    任何一环残留，都会让框以某种形式复活（比如"只发不发都不画"的僵尸话题）。
    """
    adapter = _code(MAP_ADAPTER)
    viz = _code(ROOT / 'src' / 'agc_task' / 'scripts' / 'viz_markers.py')
    cfg = _text(PERC_CFG)

    # 产出侧
    assert 'extractBoxesFromGrid' not in adapter, '框提取已删，不得复活'
    # 话题侧
    assert '/agc/map/obstacles' not in adapter, '框话题已退役'
    assert 'merged_pub_' not in adapter, '框发布者已删'
    # 配置侧
    assert 'merge_gate_m' not in cfg, '合并门参数已从配置删除'
    # 消费侧
    assert 'on_obstacles' not in viz and 'confidence_color' not in viz

    # 但**障碍仍必须可见**：栅格是唯一呈现，且必须开启
    assert 'nav_msgs::msg::OccupancyGrid' in adapter, '栅格发布者必须仍在'


def test_map_grid_is_the_only_obstacle_representation():
    """/agc/map 必须是障碍的**唯一**表示（不是"之一"）。

    判据：全仓只能有一个 OccupancyGrid 发布者；且不存在任何把障碍
    另发成第二份表示的活跃发布者（足迹点是**输入**不是表示，允许存在）。
    """
    pubs = []
    for f in (ROOT / 'src').rglob('*.cpp'):
        code = _code(f)
        if re.search(r'create_publisher<nav_msgs::msg::OccupancyGrid>', code):
            pubs.append(str(f.relative_to(ROOT)))
    assert pubs == ['src/agc_perception/src/map_adapter.cpp'], (
        '/agc/map 的 OccupancyGrid 发布者必须只有 map_adapter，实际 %r' % pubs)


# ---------------------------------------------------------------- ⑨ 聚合复杂度（2026-11-09）
def test_aggregate_cost_independent_of_component_count():
    """`aggregateObbs` 的成本不得随连通域个数线性增长（O(C·N²) 回归闸门）。

    **为什么需要这条**：改造前它对**每个连通域各扫全图两遍**。640×480 时 C 小、N² 小，
    完全看不出来；换到 1152² 后实测 C=30 就要 89 ms，而 10 Hz 的单帧预算是 100 ms。
    2026-11-09 整链运行实测真实连通域数 **25.5 个均值 / 35 个峰值** —— 正好在临界点上。

    这条测的是**源码形态**而非耗时（单测里计时会 flaky，且这台机器 4 vCPU 有噪声）：
    聚合函数体内**不得出现按连通域循环的整幅图扫描**。具体判据：
      1. `aggregateObbs` 的实现里不得出现 `connectedComponents`（CC 只在点池收集时做一次）；
      2. 实现里不得出现"外层按 label 循环 + 内层扫 mask.rows/mask.cols"的嵌套形态。
    """
    geom = _code(NADIR_GEOM)
    # 点池版 aggregateObbs 的实现段（从它的定义到下一个顶层函数定义之间）。
    #
    # **不要用"下一个 aggregateObbs(" 当结束标记**：签名带可选参数后（ADR-0041 加了
    # `out_labels`），函数体内也会出现 `aggregateObbs(` 的文本，截取会切在自己身上。
    # 用"下一个 `inline` 顶层定义"更稳。
    start = geom.index('inline std::vector<Obb> aggregateObbs(')
    nxt = geom.find('\ninline ', start + 10)
    end = nxt if nxt > 0 else len(geom)
    body = geom[start:end]
    assert 'connectedComponents' not in body, (
        'aggregateObbs 内不得再跑连通域分析 —— 那会退回到 O(C·N²)')
    # 反例形态：内层扫整幅图（mask.rows / mask.cols 循环）
    assert 'mask.rows' not in body and 'mask.cols' not in body, (
        'aggregateObbs 内不得扫描整幅图（应只遍历点池的段）；'
        '按连通域扫全图正是本次修复消掉的 O(C·N²)')
    # 正面：必须按段遍历点池
    assert 'cp.count' in body and 'cp.begin' in body, (
        'aggregateObbs 必须按点池的段（begin/count）遍历')
    # 便捷重载只能做"收集 + 聚合"，不得自己再写一套扫描逻辑
    tail = geom[end:]
    overload = tail[:tail.index('inline double smoothScalar')]
    assert 'connectedComponents' not in overload, (
        '便捷重载不得自己再做连通域分析（CC 只在 collectComponentPoints 里做一次）')
    assert 'collectComponentPoints' in overload, '便捷重载必须委托点池'


def test_frame_stats_diagnostic_reports_real_numbers():
    """必须上报**实测**帧率与连通域数，而不是让人从日志疏密去猜。

    **为什么需要这条**：性能临界点 C ≈ 30 由场景决定，不可预知。没有这条日志时，
    只能拿 launch.log 里 map 重建行的疏密反推 —— 而那个数是**地图内容变化率**、
    不是帧率（内容收敛后自然下降）。我据此做过一次错误推断，所以这条判据要钉住
    "帧率、连通域数、障碍像素数"三项都必须是直接测出来的。
    """
    node = _code(NADIR_NODE)
    assert 'reportFrameStats' in node, '必须有每帧统计上报'
    assert '帧统计' in node, '统计日志必须可被 grep（中文标签）'
    # 三项实测值必须都在日志里
    for field in ('Hz', '连通域', '障碍像素'):
        assert field in node, '帧统计必须包含 %r' % field
    # 帧率必须由"帧数 / 实际经过时间"算出，不得写成固定常量
    stats = node[node.index('void reportFrameStats'):]
    stats = stats[:stats.index('frame_count_ = 0;')]
    assert 'frame_count_' in stats and 'dt' in stats, (
        '帧率必须由帧数与实际时间算出（frame_count_ / dt），不得硬编码')


# ---------------------------------------------------------------- ⑩ 画幅/阴影（2026-11-09）
def test_footprint_derives_from_intrinsics_not_hardcoded_hfov():
    """地面画幅必须从 `camera_info` 推导，**不得**写死 hfov/130°。

    **为什么**：写死 hfov 会与 SDF 静默漂移 —— 改分辨率或换相机后，地图边界
    悄悄变错而没有任何报错。从内参推导则自动跟随，且"正方形覆盖"成为**推导结果**
    而非假设（`width/2/fx == height/2/fy` 时才成正方形）。
    """
    adapter = _code(MAP_ADAPTER)
    assert 'footprintFromCamera' in adapter, (
        'map_adapter 必须从 camera_info 推导画幅（footprintFromCamera）')
    assert 'camera_info' in adapter.lower(), '必须订阅 camera_info'
    # 反例：不得在 map_adapter 里写死 fov / 角度
    assert '2.2689' not in adapter, '不得写死 130° 的弧度值（会与 SDF 静默漂移）'
    assert 'hfov' not in adapter.lower(), '不得在 map_adapter 里引入 hfov 常量'
    # 画幅必须按**相机离地高度**算（机体 z + 安装高），不是机体高度
    # 2026-11-09：安装高不再在 map_adapter 本地复制一份，而是共用
    # `camera_geometry.hpp`（唯一来源），因此这里查**引用**而不是字面常量。
    assert 'camera_geometry.hpp' in adapter, (
        'map_adapter 必须 include camera_geometry.hpp（相机几何的唯一来源）')
    assert 'cameraWorldOrigin' in adapter, (
        '画幅/射线起点必须用 cameraWorldOrigin（机体位置 + 姿态旋转后的安装偏移）')


def test_camera_mount_constant_single_source():
    """安装高必须**只有一个定义**，且与 SDF 的 nadir_cam_joint 一致。

    **2026-11-09 判据反转**：改造前 `map_adapter` 本地复制了一份 `kCamMountZ_`
    （理由是不想为常量拉进 OpenCV），靠静态断言守住"两份同值"。
    现在相机几何整体抽到 `camera_geometry.hpp`（不依赖 OpenCV），
    两份变一份 —— 判据从"两份必须同值"改为"**不得有第二份**"。
    """
    cam = _text(CAM_GEOM)
    m = re.search(r'constexpr double kCamMountZ\s*=\s*([0-9.]+)', cam)
    assert m, 'camera_geometry.hpp 必须有 kCamMountZ'
    truth = float(m.group(1))

    # 唯一来源：其它头/源不得再定义同名常量
    for f in (NADIR_GEOM, MAP_ADAPTER, NADIR_NODE):
        code = _code(f)
        assert not re.search(r'constexpr double kCamMountZ\s*=', code), (
            '%s 不得再定义 kCamMountZ（唯一来源是 camera_geometry.hpp）' % f.name)
        assert not re.search(r'kCamMountZ_\s*=\s*[0-9]', code), (
            '%s 不得再本地复制一份安装高' % f.name)

    # 与 SDF 的 fixed joint 一致
    sdf = _text(ROOT / 'src' / 'agc_sim' / 'models' / 'agc_x500_nadir' / 'model.sdf')
    mz = re.search(r'nadir_cam_joint[^>]*>[\s\S]{0,400}?<z>\s*([0-9.]+)\s*</z>', sdf)
    if mz:
        assert abs(float(mz.group(1)) - truth) < 1e-9, (
            'kCamMountZ=%s 与 SDF nadir_cam_joint 的 z=%s 不一致'
            % (truth, mz.group(1)))


def test_carve_produces_negative_evidence_without_obstacles():
    """**没有障碍的方向也必须产生负证据**（用户裁定的核心缺口）。

    **原缺陷**：`observeMiss` 只在射线打到障碍时调用，而射线终点只能是障碍点
    ⇒ 没有障碍的方向零负证据，永远 unknown（灰色）。而 yard 障碍只占作业区 11.5%，
    绝大多数方向没障碍 —— 整张图基本是灰的，规划被大幅限制。
    用户原话："到边缘都没检测到障碍物那就是安全啊"。

    判据：carve 逻辑里必须存在"射到**画幅边界**"的路径，且阴影远边之后仍要打 miss。
    """
    adapter = _code(MAP_ADAPTER)
    assert 'carveNegativeEvidence' in adapter, '必须有负证据生成函数'
    body = adapter[adapter.index('void carveNegativeEvidence'):]
    # 终止符取函数结尾的统计赋值（早期 return 分支里也有 ++carve_calls_）
    body = body[:body.index('last_shadow_skipped_ = shadow_skipped;')]
    # 必须有"无障碍 → 射到画幅边界"的分支
    assert 'footprintEdgeDistance' in body, (
        '必须射到画幅边界（否则无障碍方向零负证据，地图永远灰）')
    assert 'has_obs' in body, '必须区分"有障碍"与"无障碍"两种射线终点'
    # 必须有阴影远边处理（不是一刀切）
    assert 'shadowFarEdge' in body, (
        '必须按实际高度算阴影远边；一刀切会让能确定安全的也留成未知')
    # 按角度分箱（Q9/Q10）：不得对每个足迹点各射一条
    assert 'n_bins' in body, '必须按角度分箱（否则一帧 2 万条射线）'


def test_shadow_region_is_unknown_not_free():
    """阴影区必须保持 **unknown**，不得标 free。

    unknown 在 `planning_policy.hpp` 里**不是障碍**（规划器可以走），
    只是不享受"已确认安全"的待遇。标成 free 等于对规划器承诺"这条路我确认过"，
    那是过度承诺 —— 楼后可能藏着东西，相机永远看不到。
    """
    adapter = _code(MAP_ADAPTER)
    body = adapter[adapter.index('void carveNegativeEvidence'):]
    # 终止符取函数结尾的统计赋值（早期 return 分支里也有 ++carve_calls_）
    body = body[:body.index('last_shadow_skipped_ = shadow_skipped;')]
    # 阴影区靠"不打 miss"实现（而不是显式写 unknown 值）
    assert 'shadow_cells' in body or 'shadow_end' in body, '必须有阴影区参数'
    assert 'observeHit' not in body, (
        '负证据函数里不得打 hit（阴影区不得被标成障碍，也不得被标成自由）')


def test_carve_ray_reaches_boundary_past_obstacle():
    """射线终点必须是 **max(障碍距离, 阴影远边)**，不得只停在障碍点。

    **这是 2026-11-09 我自己写出的 bug 的防复活闸门**：第一版写成
    `has_obs ? dist : dist`（两分支一样），于是"阴影远边之后射到边界"那段根本没射，
    障碍后面的区域既无 hit 也无 miss ⇒ **更早的误 hit 永远擦不掉**。
    实测后果与用户描述完全一致：飞到建筑群时误 hit 累积 → 突然跳变；
    悬停时视野不动、不再新增误 hit，看起来"不错"但旧的还在。
    诊断数字 `carve/hit=0.07` 也印证负证据严重不足。

    判据：终点计算里必须出现 `max(dist, shadow_end)`（或等价形态），
    且不得出现"两分支赋同一个值"的退化写法。
    """
    adapter = _code(MAP_ADAPTER)
    body = adapter[adapter.index('void carveNegativeEvidence'):]
    # 终止符取函数结尾的统计赋值（早期 return 分支里也有 ++carve_calls_）
    body = body[:body.index('last_shadow_skipped_ = shadow_skipped;')]
    # 必须把阴影远边并入终点（矮障碍后面才射得到边界）
    assert re.search(r'end_dist\s*=\s*std::max\(\s*dist\s*,\s*shadow_end\s*\)', body), (
        '射线终点必须是 max(障碍距离, 阴影远边)；'
        '只停在障碍点会让障碍后的误 hit 永远擦不掉（实测导致跳变）')
    # 必须被画幅边界封顶（高楼阴影超出边界时不能射到画幅外）
    assert 'footprintEdgeDistance' in body, '终点必须被画幅边界封顶'
    # 反例闸门：不得出现"两个分支赋同一个值"的退化三元表达式
    assert not re.search(r'has_obs\s*\?\s*(\w+)\s*:\s*\1\b', body), (
        '终点不得写成 has_obs ? X : X（两分支相同 = 阴影段根本没射，这是实测踩过的 bug）')


# ---------------------------------------------------------------- ⑪ 证据单位与职责分离（2026-11-09）
def test_evidence_unit_is_one_per_cell_per_frame():
    """栅格证据必须**按唯一栅格**记账，不是按 footprint 点（用户裁定的稳定性根因）。

    **为什么这条重要**：一帧有成千上万个足迹点，而一个 0.5 m 格通常覆盖大量像素。
    改造前对每个点直接 `observeHit(idx)`：同一格一帧被 hit 数十次 ⇒ 证据强度取决于
    **像素采样密度**而不是时序观测。栅格中心一帧打满、障碍边缘只命中一两次，
    边缘格于是在 100 与中间值之间反复翻转 —— 实测 `|Δoccupied| p99 = 140`（判据 ≤50）。

    判据落在**调用形态**上：`onFootprints` 必须先判"本帧该格是否已记过"再 `observeHit`，
    且网格类必须提供该判定（`hitThisFrame`）与帧内幂等。
    **2026-11-10（ADR-0039）判据升级**：改造后不再用 `hitThisFrame` 当场去重，而是
    先用 `obstacle_mask_` 登记"本帧该格已见过"、把唯一格收进 `candidate_cells_`，
    再对该格**判一次空间支持**（`observeHitWithSupport`）。去重机制仍在，只是从
    "命中后去重"变成"命中前登记 + 逐格判一次"。因此本闸门改判**三条更本质的性质**：
    ① 每格每帧只判一次（有唯一格集合）；② 走的是带空间支持的记账入口；
    ③ 帧内幂等由网格类保证（`hit_frame_`）。
    """
    adapter = _code(MAP_ADAPTER)
    grid = _code(GRID_HPP)
    body = adapter[adapter.index('void onFootprints'):]
    # 截到 `onFootprints` 之后的第一个成员函数（`stale_after_frames` 的定义）
    body = body[:body.index('stale_after_frames() const')]
    # ① 必须有唯一格集合（否则每个点都会记账）
    assert 'candidate_cells_' in body or 'hitThisFrame' in body, (
        'footprint 点必须先归到**唯一格**再记账；'
        '逐点直接 observeHit 会让证据强度取决于像素采样密度')
    assert 'hit_cells_' in body, '去重结果必须收集（诊断与后续复用需要唯一格集合）'
    # ② 必须走带空间支持的记账入口（ADR-0039：小障碍需多个点一致才成候选）
    assert 'observeHitWithSupport' in body, (
        '记账必须经过空间支持门槛；否则孤立错位点跨两帧就能建成 occupied')
    assert 'observeHitWithSupport' in grid, 'LogOddsGrid 必须提供带空间支持的记账入口'
    # 三项诊断口径必须分开，不得把原始点数当 hit 数
    assert 'footprint_points_' in body and 'footprint_dups_' in body, (
        '诊断必须区分 原始点数 / 唯一格数 / 重复点数；'
        '混成一个数会让 carve/hit 的分母随像素密度放大')
    # 网格侧：帧内幂等 + 提供判定
    assert 'hitThisFrame' in grid, 'LogOddsGrid 必须提供 hitThisFrame（调用侧去重判据）'
    assert 'hit_frame_' in grid and 'neg_frame_' in grid, (
        'LogOddsGrid 必须按帧记账（每格每帧一次 hit / 一次负证据）')


def test_snapshot_state_advances_only_on_map_frames():
    """迟滞状态（`occupied_now_`）必须**按地图帧**推进，不得在感知回调里提前推进。

    **为什么**：`rebuild()` 内含 `snapshot()`，而 `snapshot()` 推进 occupied 迟滞记忆。
    改造前感知回调（10 Hz）也调 `rebuild()`，于是"内部迟滞 10 Hz、对外地图 2 Hz"：
    两次发布之间的 occupied→non→occupied 翻转被内部吃掉，对外只留一个状态，
    而稳定性指标是按 `/agc/map` 帧统计的 —— 口径与实现脱节。
    """
    adapter = _code(MAP_ADAPTER)
    body = adapter[adapter.index('void onFootprints'):]
    body = body[:body.index('stale_after_frames() const')]
    assert 'rebuild()' not in body, (
        '感知回调不得调 rebuild()：它内含 snapshot()，会把迟滞状态按感知帧推进；'
        '证据更新与地图拍必须分离（rebuild 只在 tick 里调）')
    assert 'evidence_frames_' in body, '证据更新拍必须单独计数（诊断用）'
    # tick 里必须仍然 rebuild
    tick = adapter[adapter.index('void tick()'):]
    tick = tick[:tick.index('struct Grid')]
    assert 'rebuild()' in tick, '地图拍必须调 rebuild()（快照生成只在这里发生）'


def test_confirmation_gate_counts_map_frames_not_sensor_frames():
    """`min_hits_for_occupied` 必须挂**地图帧**时钟，不是感知帧（ADR-0039 补正）。

    **为什么**：感知回调 10 Hz、`/agc/map` 2 Hz。若确认门槛按感知帧计数，
    "K=2 帧确认"在对外地图上实际只用了 0.2 s —— 语义比设计意图弱 5 倍，
    且随感知帧率漂移。门槛必须与迟滞状态（`occupied_now_`）同一个时钟。

    判据落在**时钟绑定**上：`beginMapFrame` 只能在 `rebuild()`（发布拍）里推进，
    不得在感知回调里推进。
    """
    adapter = _code(MAP_ADAPTER)
    grid = _code(GRID_HPP)
    # 网格侧：必须有独立的地图帧计数，且确认门用它
    assert 'map_frame_hits_' in grid, (
        'LogOddsGrid 必须有**地图帧口径**的确认计数（与 hit_count_ 分开，两者时钟不同）')
    assert 'beginMapFrame' in grid, 'LogOddsGrid 必须提供地图帧推进入口'
    assert 'map_frame_hits_[i] >= need_hits' in grid, (
        '确认门必须读地图帧计数；读 hit_count_ 会让 K 的语义随感知帧率漂移')
    # 调用侧：只在 rebuild（发布拍）里推进，感知回调里不得推进
    body = adapter[adapter.index('void onFootprints'):]
    body = body[:body.index('stale_after_frames() const')]
    assert 'beginMapFrame' not in body, (
        '感知回调不得推进地图帧：那会让确认门槛回到按感知帧计数')
    rebuild = adapter[adapter.index('bool rebuild()'):]
    rebuild = rebuild[:rebuild.index('std::string contentIdentityHash')]
    assert 'beginMapFrame' in rebuild, (
        '地图帧必须在 rebuild()（发布拍）里推进，与 occupied_now_ 同一个时钟')


def test_deadband_is_not_sold_as_stability_fix():
    """`publish_deadband` 只量化 1–99，**不得**被当成稳定性 p99 的手段。

    `perception_quality.py` 把 1–99 一律归为 unknown，只有 99/中间值 ↔ 100 的
    跨门限翻转才影响稳定性。deadband 对 100 本身不做量化 ⇒ 它改善的是消息与 hash
    的更新频率，不是 p99。这条判据防止后来者用"调大 deadband"冒充稳定性修复。
    """
    quality = _text(ROOT / 'scripts' / 'tests' / 'perception_quality.py')
    assert "return 'unknown'    # 1–99 = 有证据但未跨门限 → 未知" in quality, (
        '稳定性口径必须保持"1–99 算 unknown"；改成别的会把 deadband 混进稳定性指标')
    adapter = _code(MAP_ADAPTER)
    assert 'v >= 100' in adapter, (
        'deadband 必须对 0/100/-1 原样保留（只量化 1–99）')


def test_uncertainty_gate_and_missing_covariance_are_explicit():
    """S3：逐点 sigma 门控与缺协方差不拦截语义必须可追溯。"""
    grid = _code(GRID_HPP)
    adapter = _code(MAP_ADAPTER)
    assert 'sigma_reject_ratio' in grid and 'cell_size_m' in grid
    assert 's >= 0.0 && s > params_.sigma_reject_ratio * params_.cell_size_m' in grid
    assert 'sigma_m = -1.0' in adapter
    assert 'const bool have_cov' in adapter
    assert 'sigma_rejected_cells' in adapter


def test_evidence_lifecycle_protects_hits_and_stale_unknown():
    """S4：同帧 hit 保护、终点不 carve、stale 只退 unknown。"""
    grid = _code(GRID_HPP)
    assert 'if (hit_frame_[idx] == current_frame_) {return false;}' in grid
    assert 'while (!(x == x1 && y == y1))' in grid
    assert 'unknown_floor_p' in grid
    assert 'occupied_expire_frames' in grid
    assert 'logodds_[i] = std::max(floor_lo, logodds_[i] + decay_inc_)' in grid


def test_quality_script_keeps_layered_metrics_and_signed_int8():
    """S7：几何、规划、稳定性分层，且地图样本按有符号 int8 解析。"""
    quality = _text(ROOT / 'scripts' / 'tests' / 'perception_quality.py')
    assert "'geometry'" in quality and "'planning'" in quality and "'instance'" in quality
    assert 'dtype=np.int8' in quality
    assert 'false_positive' in quality and 'iou' in quality and 'hausdorff' in quality
    assert 'geometry_source' in quality



    """投影、证据、carve 和实例层必须共享 floor 落格函数。"""
    cam = _code(CAM_GEOM)
    assert 'inline int worldToGrid(double world, double origin, double resolution)' in cam
    assert 'std::floor((world - origin) / resolution)' in cam
    adapter = _code(MAP_ADAPTER)
    assert 'worldToGrid(p.x, ox_, fres)' in adapter
    assert 'worldToGrid(p.y, oy_, fres)' in adapter
    assert 'worldToGrid(ex, ox_, fres)' in adapter
    assert 'worldToGrid(ey, oy_, fres)' in adapter
    assert 'std::floor((p.x - ox_) / fres)' not in adapter
    assert 'std::floor((ex - ox_) / fres)' not in adapter


def test_hit_and_carve_share_observation_pose_and_stamp():
    """足迹消息时间戳查得的同一 pose 必须同时服务 hit 与 carve。"""
    adapter = _code(MAP_ADAPTER)
    start = adapter.index('void onFootprints')
    end = adapter.index('void updateInstances', start)
    body = adapter[start:end]
    assert 'msg.header.stamp' in body and 'poseAtTime' in body
    pose_at = body.index('poseAtTime')
    carve_at = body.index('carveNegativeEvidence(msg.points, pose)')
    assert pose_at < carve_at
    assert 'if (!have_pose)' in body
    no_pose = body[body.index('if (!have_pose)'):body.index('agc_perception::Vec3 cam_origin')]
    assert 'if (carve_enabled_) {carveNegativeEvidence(msg.points, pose);}' not in adapter
    assert '无有效观测时刻位姿' in _text(MAP_ADAPTER)


def test_instances_are_online_rebuild_input_but_not_history_overlay():
    """实例确认必须在 rebuild 当前快照中并入，不得从轨迹历史直接补画。"""
    adapter = _code(MAP_ADAPTER)
    rebuild = adapter[adapter.index('bool rebuild()'):adapter.index('std::string contentIdentityHash')]
    assert 'stampConfirmedInstances' in rebuild
    assert 'fine[idx] = 100' in rebuild
    assert 'planningSnapshot' in rebuild
    assert 'instances_.instances()' not in rebuild, (
        'rebuild 只能消费 stampConfirmedInstances 生成的当前格集合，避免直接读取历史轨迹补画')

def test_evidence_layer_is_finer_than_planning_layer():
    """证据层必须比规划层细，且是整数分之一 —— 否则 0.5 m 仍是感知表达的唯一载体。

    **为什么这条重要**：改造的全部价值在于"0.5 m 只做规划消费格式"。
    若 `perception_resolution` 被配成等于 `resolution`，分层就退化成空转：
    代码结构还在、指标不会变好、而看代码的人会以为已经分层了。
    """
    import yaml
    cfg = yaml.safe_load(_text(PERC_CFG))
    per = cfg['map_adapter']['ros__parameters']['perception_resolution']
    mapyaml = yaml.safe_load(_text(PERCEPTION / 'config' / 'map.yaml'))
    plan = mapyaml['resolution']
    assert per < plan, '证据层必须比规划层细（perception_resolution < resolution）'
    ratio = plan / per
    assert abs(ratio - round(ratio)) < 1e-9, (
        '必须是整数分之一（非整数倍会引入随坐标漂移的半格错位）')


def test_planning_layer_is_derived_from_evidence_layer():
    """规划层必须由证据层**派生**，不得各自独立累积。

    判据落在调用形态上：`rebuild()` 必须先取证据层快照，再经
    `planningSnapshot` 派生；若直接拿 `accum_.snapshotIntoBuffer()` 当发布内容，
    说明 0.5 m 又变回感知表达了。
    """
    adapter = _code(MAP_ADAPTER)
    rebuild = adapter[adapter.index('bool rebuild()'):]
    rebuild = rebuild[:rebuild.index('std::string contentIdentityHash')]
    assert 'planningSnapshot' in rebuild, (
        '规划层必须经 planningSnapshot 派生（max-pool + 保守四态合并）')
    assert 'perception_geo_' in rebuild, '派生需要证据层几何'
    # 累积层必须建在证据分辨率上
    assert 'perception_geo_.fine_width' in adapter, (
        '累积层尺寸必须来自证据层几何，不是规划层的 sx_/res_')


def test_inflation_is_metric_not_cell_count():
    """膨胀半径必须是**米**参数，不得出现 `ceil(radius / res)` 的格数写法。

    **为什么**：参照实现里 ego-planner 的 `inf_step = ceil(0.099/0.1) = 1` 是
    分辨率绑定的；换到 0.5 m 会静默变成 0.5 m 余量（2.5 倍设计意图）。
    Nav2 的 `computeCost(distance)` 才是与分辨率无关的写法。
    """
    adapter = _code(MAP_ADAPTER)
    cfg = _text(PERC_CFG)
    assert 'inflation_radius_m' in cfg, '膨胀半径必须是以 _m 结尾的米制参数'
    assert 'inflation_robot_radius_m' in cfg, '车半径同样必须是米制参数'
    # 不得出现按格数算膨胀的写法
    for bad in ('ceil(inflation_radius_m_ / res_)',
                'ceil(inflation_radius_m_ / perception_resolution_)',
                'inf_step = ceil('):
        assert bad not in adapter, (
            '膨胀不得按格数算（%s）—— 那会随分辨率静默改变物理余量' % bad)
    # 风险分档必须在米制上判
    infl = _text(PERCEPTION / 'include' / 'agc_perception' / 'inflation_field.hpp')
    assert 'classifyRisk(double distance_m' in infl, '风险分档的入参必须是米'


def test_resolution_parameters_are_declared_before_geometry_validation():
    """分辨率参数必须在**启动期几何校验之前**声明。

    **实测踩过**：先声明在 `validateStartupOrThrow()` 之后，校验读到的还是默认值，
    于是 `perception_resolution:=0.2`（非整数倍）**静默通过**校验，
    节点照常启动 —— 那正是"看着有保护、实际零覆盖"。
    """
    adapter = _code(MAP_ADAPTER)
    decl = adapter.index('declare_parameter<double>("perception_resolution"')
    valid = adapter.index('validateStartupOrThrow();')
    assert decl < valid, (
        'perception_resolution 必须在 validateStartupOrThrow() 之前声明，'
        '否则校验读到默认值、非法配置静默通过')
    # 校验里必须真的判整数倍
    body = adapter[valid:]
    body = body[:body.index('void loadMapGeometry')]
    assert 'perception_resolution' in adapter[:valid], '校验函数要能读到它'
    assert '整数分之一' in _text(MAP_ADAPTER), (
        '启动期必须显式拒绝非整数倍分辨率')


# ---------------------------------------------------------------- ⑨ 方向 2/3/4（ADR-0041）
def test_geometry_layer_carries_per_point_metadata():
    """几何层必须是"每个点都有来历"，不是"一批匿名点"（temp.md 方向二）。

    判据落在消息契约与发布形态上：
      ① 消息必须有点级并行数组（实例归属 + 类别）；
      ② 发布端必须真的填它们，且长度与 points 对齐；
      ③ 点必须在**跨帧关联之后**才发布 —— 否则永远拿不到实例 id。
    """
    msg = _text(ROOT / 'src' / 'agc_msgs' / 'msg' / 'ObstacleFootprintArray.msg')
    assert 'string[] point_instance_id' in msg, (
        '几何层必须能回答"这个点属于哪个实例"（temp.md 方向二）')
    assert 'uint8[] point_class' in msg, (
        '几何层必须能回答"这个点是什么（屋顶/墙/边缘/遮挡）"')

    node = _code(NADIR_NODE)
    # ② 发布端必须填两个并行数组
    assert 'point_instance_id.reserve' in node, '发布端必须填实例归属'
    assert 'point_class.reserve' in node, '发布端必须填类别'
    # ③ 发布必须在关联之后
    body = node[node.index('void onFootprints'):] if 'void onFootprints' in node else node
    # 调用签名在 ADR-0042 里扩了（要带位姿/内参算逐点协方差），
    # 判据只关心**位置**，故用前缀匹配而不是完整字面量。
    pub_at = node.index('publishFootprints(')
    assoc_at = node.index('associateNearest(obs, tracks_')
    assert assoc_at < pub_at, (
        '足迹点必须在**跨帧关联之后**发布；先发后关联会让点永远拿不到实例 id')


def test_point_class_uses_same_criterion_as_kept():
    """点类别与 `kept` 必须用**同一判据**，不得各自重判。

    若两处各算一遍 z_cut，任何一处改门限都会让它们给出互相矛盾的说法
    （同一个点既"被保留"又"被标成墙"），而且没人会发现。
    """
    geom = _text(NADIR_GEOM)
    assert 'kPointRoof' in geom and 'kPointWall' in geom
    # **判据用"同一个循环体内"而不是字符偏移**：偏移阈值在重构时会误报
    # （本用例第一版写 600 字符，实际 7093 就红了 —— 那不是缺陷，是判据写错）。
    # 真正的性质是：类别赋值与 kept 赋值必须在**同一个 for 循环**里，
    # 且引用**同一个** z_cut 变量。
    loop_start = geom.index('size_t kept_n = 0;')
    loop_end = geom.index('++kept_n;', loop_start)
    loop = geom[loop_start:loop_end]
    assert 'cp.kept[base + k] = 1;' in loop, 'kept 赋值必须在这个循环里'
    assert 'kPointRoof' in loop and 'kPointWall' in loop, (
        'kept 与 point_class 必须在**同一个循环**里赋值（同一判据）；'
        '分开算会让两者可能互相矛盾')
    assert loop.count('z_cut') >= 2, (
        '类别与 kept 必须引用**同一个** z_cut 变量，不得各算一遍')


def test_instances_are_merged_into_evidence_layer_not_replacing_it():
    """实例层必须与逐点累积**取并集**，不是替换（ADR-0041）。

    为什么不能替换：大建筑被画幅切成碎片时实例会分裂（每片各自成实例），
    而逐点累积天然把它们合并。替换会让覆盖率崩掉。
    为什么必须并：小障碍（1–3 格宽）的边界点会在相邻格之间跳，
    逐点累积拿不到"这些点属于同一个障碍"。
    """
    adapter = _code(MAP_ADAPTER)
    assert 'updateInstances' in adapter, 'map_adapter 必须消费实例层'
    assert 'stampConfirmedInstances' in adapter, '必须把已确认实例栅格化'
    rebuild = adapter[adapter.index('bool rebuild()'):]
    rebuild = rebuild[:rebuild.index('std::string contentIdentityHash')]
    assert 'fine[idx] = 100' in rebuild, (
        '实例格必须写进**证据层**（fine），再与逐点证据一起派生规划层')
    assert 'planningSnapshot' in rebuild, '派生仍必须走 planningSnapshot'
    # 顺序：先并实例，再派生（否则实例格不会进规划层）
    assert rebuild.index('fine[idx] = 100') < rebuild.index('planningSnapshot'), (
        '实例必须在派生**之前**并进证据层')


def test_map_outputs_risk_tiers_not_bare_occupancy():
    """`/agc/map` 必须输出**风险分档**（temp.md 方向四 C，用户指定接入本体）。

    三张逻辑图的分工：几何占据（证据层）/ 置信度（证据层）/ **规划风险**（/agc/map）。
    若 `/agc/map` 仍是裸占据，那"为了安全而膨胀"就没有任何载体。
    """
    adapter = _code(MAP_ADAPTER)
    cfg = _text(PERC_CFG)
    assert 'risk_enabled' in cfg, '风险图必须有显式开关'
    # **默认必须是 true**：主链要的就是风险分档。若默认 false，
    # 那么"忘了配"就会静默退回裸占据 —— 安全膨胀不生效且看不出来。
    import re as _re
    m = _re.search(r'^\s*risk_enabled:\s*(\w+)', cfg, _re.M)
    assert m and m.group(1).lower() == 'true', (
        'risk_enabled 必须默认 true；默认 false 会让"忘了配"静默退回裸占据')
    assert 'riskToGridValue' in adapter, '/agc/map 必须输出风险分档'
    assert 'classifyRisk' in adapter, '风险分档必须按米制距离判'
    assert 'distanceFieldMeters' in adapter, '必须用米制距离场'
    # 未知格必须短路
    assert 'if (geom < 0) {data[i] = -1; continue;}' in adapter, (
        '未知格必须保持 -1，不得按距离判成 free')


def test_costmap_reads_risk_tiers_as_costs_not_free():
    """costmap 必须能读懂 `/agc/map` 的 `1–98`，否则安全膨胀静默失效。

    Nav2 `StaticLayer::interpretValue` 在 `trinary_costmap: true`（默认）下把
    `1–99` 折成 `FREE_SPACE` —— 那会把我们算出来的"贴车半径有代价"读成"完全可通行"。
    """
    cfg = _text(COSTMAP)
    assert 'trinary_costmap: false' in cfg, (
        '必须关掉 trinary，否则 1–98 会被 Nav2 读成 free（安全膨胀静默失效）')
    assert 'lethal_cost_threshold: 100' in cfg, (
        '致命阈值必须是 100，与 planning_policy.hpp 的 classifyCell 同口径')


def test_instance_stamping_does_not_inflate_area():
    """实例栅格化必须用**椭圆/矩形**量级，不得用外接圆（实测回归）。

    **实测教训**：第一版用外接圆（`hypot(wx-cx, wy-cy) <= r`），而
    `boundingRadius()` 是 box 的**对角半径**。对 0.6×0.15 m 的长条 box，
    外接圆面积是矩形的 **3.34 倍**；整图 occupied 实测从 2230 涨到 4622（2.07×）。
    那已经不是"稳定小障碍"，而是凭空造障碍 —— 直接推高误覆盖率。

    判据：栅格化必须是**按朝向的椭圆**（`(u/hx)² + (v/hy)² ≤ 1`），
    不得是各向同性的圆。
    """
    adapter = _code(MAP_ADAPTER)
    body = adapter[adapter.index('void stampConfirmedInstances'):]
    body = body[:body.index('// 空窗帧数') if '// 空窗帧数' in body else len(body)]
    assert 'inst.yaw' in body, (
        '栅格化必须用实例朝向（各向同性圆会让长条 box 膨胀 2–3 倍）')
    assert 'half_x_m' in body and 'half_y_m' in body, (
        '必须用半长而不是单一半径（半径是外接圆半径）')
    # 椭圆判据的形态：两个方向的平方比
    assert '/ (hx * hx)' in body and '/ (hy * hy)' in body, (
        '必须是椭圆判据 (u/hx)²+(v/hy)²≤1')
    assert 'boundingRadius()' not in body, (
        '不得再用 boundingRadius()（那是外接圆，会虚增面积）')


# ---------------------------------------------------------------- ⑩ 逐格元数据（ADR-0042）
def test_cell_meta_message_carries_all_five_quantities():
    """`OccupancyGrid.data` 装不下 temp.md 要的五个量，必须有独立消息承载。

    `int8[]` 每格只能装一个数：要么"算不算占据"（0/100），要么"占多少"（0–100），
    不能同时是"占据率 0.31 / 置信度 0.78 / 最近观测 0.2 s / 来源 17 / 可见 false"。
    这正是 temp.md 指出的表示能力上限本身。
    """
    msg = _text(ROOT / 'src' / 'agc_msgs' / 'msg' / 'PerceptionCellMeta.msg')
    for field in ('float32[] occupancy_ratio',      # A 几何占据图
                  'float32[] confidence',           # B 感知置信图
                  'float32[] last_seen_s',          # 最近观测
                  'int32[] source_instance_id',     # 来源实例
                  'uint8[] fully_visible'):         # 是否完整可见
        assert field in msg, '逐格元数据缺字段：%s' % field
    # 实例可见性（方向三）
    assert 'int32[] visible_instance_id' in msg


def test_cell_meta_publisher_is_wired_into_main_chain():
    """元数据必须**在主链上真发布**，不能只是定义了消息没人填。

    "有消息定义 + 有实现"不等于"接进了链路" —— ADR-0041 阶段就踩过这个：
    `point_instance_id` 先发点、后关联，于是点永远拿不到 id。
    """
    adapter = _code(MAP_ADAPTER)
    assert 'publishCellMeta' in adapter, '必须真有发布函数'
    assert 'cell_meta_pub_->publish' in adapter, '必须有实际 publish 调用'
    # 必须挂在发布拍上（与 /agc/map 同一个时钟），不能是独立 timer
    assert 'publishCellMeta(stamp);' in adapter, (
        '必须在 publishMap 的发布拍里调用（与 /agc/map 同一时刻）')


def test_occupancy_ratio_uses_fixed_denominator():
    """占据率分母必须是 factor²，不是"已观测细格数"。

    后者会让"只看了一角、而那一角有障碍"得到 1.0 —— 与"整格被占"无法区分。
    """
    hpp = _code(PERCEPTION / 'include' / 'agc_perception' / 'multi_res_grid.hpp')
    assert 'const int total = geo.factor * geo.factor;' in hpp, (
        '占据率分母必须固定为 factor²')
    assert 'occupancyRatioMap' in _code(MAP_ADAPTER), (
        '`occupancyRatioMap` 必须被主链消费（此前只有实现没有消费者）')


def test_confidence_is_not_the_same_as_occupancy_probability():
    """置信度与占据概率必须是**两个量**，不得互相顶替。

    一个被看过 50 次、确认是空的格：占据概率很低，但**判断很可靠**。
    拿 `probAt` 当置信度会把"确认空"报成"不可信"。
    """
    hpp = _code(GRID_HPP)
    assert 'double confidenceAt(size_t idx)' in hpp, '必须有独立的置信度访问器'
    # 置信度按**观测次数**升，与概率方向无关
    seg = hpp[hpp.index('double confidenceAt'):]
    seg = seg[:seg.index('\n  }')]
    assert 'hit_count_' in seg, '置信度必须由观测次数给出'
    assert 'logodds_' not in seg, '置信度不得直接取 log-odds（那是占据概率）'


def test_last_seen_is_time_not_frame_count():
    """最近观测必须按**时间**给，不能按帧号。

    帧率实测在 6–10 Hz 之间变：同一句"30 帧前"在 6 Hz 下是 5 s、10 Hz 下是 3 s，
    不是可比较的量。
    """
    msg = _text(ROOT / 'src' / 'agc_msgs' / 'msg' / 'PerceptionCellMeta.msg')
    assert 'float32[] last_seen_s' in msg, '字段必须是秒'
    adapter = _code(MAP_ADAPTER)
    assert 'observed_frame_hz_' in adapter, '换算必须用**实测帧率**，不能写死'


def test_fully_visible_cleared_every_frame():
    """可见性掩码必须**每帧清空**。

    它是"本帧看得见"的集合，不是累积集合。忘了清会让"曾经看过"永远为真，
    `fully_visible` 退化成常量 1 —— 而这个字段的全部价值就在于区分
    "这帧看到了"与"以前看过"。
    """
    adapter = _code(MAP_ADAPTER)
    assert 'visible_mask_' in adapter
    # **判据必须是结构性的**：清空在 `onFootprints` 里，填在它调用的
    # `carveNegativeEvidence` 里 —— 跨函数比两行行号毫无意义（定义总在后面），
    # 那种写法会得出恒真的假闸门（本轮实测踩过）。
    #
    # 真正要守的三件事：
    #   ① 清空在 `onFootprints` 的正常路径里；
    #   ② 清空必须在**调用 carve** 之前（否则本帧的标记立刻被抹掉，visible 恒 0）；
    #   ③ 清空不在 `if (carve_enabled_)` 块内 —— 关掉 carve 时掩码仍须清空，
    #      否则 stale 标记会一直留着，`fully_visible` 报"以前看过"。
    body = adapter[adapter.index('void onFootprints'):]
    body = body[:body.index('void updateInstances')]
    lines = body.split('\n')
    clear_idx = next((i for i, ln in enumerate(lines)
                      if 'std::fill(visible_mask_.begin()' in ln), None)
    assert clear_idx is not None, '清空必须发生在 onFootprints 的正常路径里'
    carve_idx = next((i for i, ln in enumerate(lines)
                      if 'carveNegativeEvidence(msg.points, pose);' in ln
                      and 'carve_enabled_' not in ln), None)
    assert carve_idx is not None, '正常路径必须调用 carve'
    assert clear_idx < carve_idx, (
        '清空必须在调用 carve 之前（顺序反了会让每帧标记立刻被抹掉，visible 恒 0）')
    window = '\n'.join(lines[max(0, clear_idx - 3):clear_idx + 1])
    assert 'if (carve_enabled_)' not in window, (
        '清空不得被 carve 开关包住（关掉 carve 时掩码仍须清空）')
    # 填掩码必须真的存在（在 carve 函数里）
    assert 'markVisibleAlongRay(cx, cy, ix, iy, shadow_cells);' in adapter, (
        '必须真的沿射线填掩码，否则 fully_visible 恒 0')


def test_instance_visibility_is_orthogonal_to_alive():
    """`visible` 必须与 `alive` **正交**，不能是它的同义词。

    alive=true + visible=false 是真实且重要的状态：暂时被遮挡 / 出了画幅，
    实例仍在（靠几何模型撑着）。合成一个布尔就无法区分
    "暂时看不见"与"消失了"——前者不该撤销地图上的障碍，后者该。
    """
    hpp = _code(PERCEPTION / 'include' / 'agc_perception' / 'obstacle_instances.hpp')
    assert 'bool visible{false};' in hpp, '必须有独立可见性字段'
    # beginFrame 必须清空（否则退化成 alive 的同义词）
    seg = hpp[hpp.index('void beginFrame()'):]
    seg = seg[:seg.index('\n  }')]
    assert 'inst.visible = false' in seg, (
        'beginFrame 必须清空 visible，否则它退化成 alive 的同义词')
    # absorb 必须置位
    seg = hpp[hpp.index('void absorb(int index'):]
    seg = seg[:seg.index('\n  }')]
    assert 'inst.visible = true' in seg, 'absorb 必须置 visible=true'
