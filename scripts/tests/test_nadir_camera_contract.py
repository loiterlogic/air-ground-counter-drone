"""机载正下视（nadir）相机 —— 契约闸门（纯静态，不启任何仿真进程）。

守护相机链的静态不变量。每一条都对应一种**曾经会静默失败**的错法：

1. **默认机型即带相机**（2026-11-08 用户裁定，相机是平台基本能力）：
   两处 launch 的 `px4_sim_model` 默认值须为 `gz_agc_x500_nadir`，且该模型 SDF 含相机传感器。
   历史坑：bridge.yaml 一旦有相机条目，无相机机型下 `ros2 topic list` 也会出现
  `/agc/air/nadir/*`（桥节点自己是订阅者），**看起来有相机、其实一帧都没有**
  （见 experiments/p1-4//evidence/camera-ownership-finding.md）。
  ⇒ 判据必须落在"模型资产与机型注入"上，不能落在"话题是否存在"上。

2. **模型本身**：`agc_x500_nadir` 存在、`<model name>` 正确（决定实体名 `agc_x500_nadir_0`）、
 恰好 1 个 `type="camera"` 传感器、相机挂在**独立 link + fixed joint** 上
 （往 `include merge` 里塞 `<link>` 会被 sdformat 静默丢弃，见 intruder_uav 注释）。

3. **相机朝向**：`pitch == +1.5708`（容差 1e-3 rad）**且**把该 pitch 代进旋转矩阵算出的
 **有效光轴 z ≈ −1**（容差 1e-2）。双断言的理由：只钉数值挡不住"约定变了"，
   只钉语义挡不住"符号写反但按反的约定解读"。`R_y(θ)·x̂ = (cosθ, 0, −sinθ)`：
   θ=+90° → (0,0,−1) 正下方；θ=−90° → (0,0,+1) 拍天空。

4. **话题名逐字一致**：SDF `<topic>` / `<camera_info_topic>` 与 `bridge.yaml` 的
 `gz_topic_name` 必须逐字相同。`camera_info` 若不显式写，gz-sensors 按 `<topic>_info`
 派生（→ `/agc/air/nadir_info`），与桥的 `/agc/air/nadir/camera_info` **不符且静默**。

5. **机型解析不改工具链**：`gz_agc_x500_nadir` 时己方 PX4 进程注入 `PX4_SYS_AUTOSTART=4001`；
 且 `toolchain/PX4-Autopilot/ROMFS/px4fmu_common/init.d-posix/airframes/` 下**没有**本仓新增的
 airframe 文件（防"改工具链"的捷径复活）。PX4 是 pin 的外部依赖，有哈希校验。

**为什么不测"帧率"**：帧率需要真实仿真（T2），不在纯静态闸门里跑；A3 的实测证据在
`experiments/nadir-camera/<run-id>/`，由 report 引用。

运行：
  python3 -m pytest scripts/tests/test_nadir_camera_contract.py -q
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]

MODEL_DIR = ROOT / 'src' / 'agc_sim' / 'models' / 'agc_x500_nadir'
MODEL_SDF = MODEL_DIR / 'model.sdf'
MODEL_CONFIG = MODEL_DIR / 'model.config'
BRIDGE = ROOT / 'src' / 'agc_sim' / 'config' / 'bridge.yaml'
W6_LAUNCH = ROOT / 'src' / 'agc_task' / 'launch' / 'main.launch.py'
AIR_LAUNCH = ROOT / 'src' / 'agc_air' / 'launch' / 'air_bringup.launch.py'
PX4_AIRFRAMES = (ROOT / 'toolchain' / 'PX4-Autopilot' / 'ROMFS' / 'px4fmu_common'
                 / 'init.d-posix' / 'airframes')

MODEL_NAME = 'agc_x500_nadir'
SIM_MODEL = 'gz_' + MODEL_NAME
# rgbd_camera 在 <topic> 后**加后缀**（2026-11-08 实测；旧 camera 是直接用 <topic>）。
GZ_RGBD_BASE = '/agc/air/nadir'
GZ_IMAGE_TOPIC = GZ_RGBD_BASE + '/image'
GZ_DEPTH_TOPIC = GZ_RGBD_BASE + '/depth_image'
GZ_INFO_TOPIC = GZ_RGBD_BASE + '/camera_info'
ROS_IMAGE_TOPIC = '/agc/air/nadir/image_raw'
ROS_DEPTH_TOPIC = '/agc/air/nadir/depth'
ROS_INFO_TOPIC = '/agc/air/nadir/camera_info'
GZ_SEG_TOPIC = '/agc/air/nadir/seg'
ROS_SEG_LABELS_TOPIC = GZ_SEG_TOPIC + '/labels_map'
ROS_SEG_INFO_TOPIC = GZ_SEG_TOPIC + '/camera_info'

PITCH_TOL = 1e-3          # 裁定 1：数值断言容差
AXIS_Z_TOL = 1e-2         # 裁定 1：语义断言容差
EXPECTED_PITCH = 1.5708   # 90° 的**下俯量**；SDF 字段值为 +1.5708（ADR-0030）


def _read(p: Path) -> str:
    return p.read_text(encoding='utf-8')


def _strip_comments(sdf: str) -> str:
    """去掉 XML 注释后再做结构断言。

 **为什么必须去注释**：本模型的注释里**逐字**解释了"往 include merge 里塞 <link> 会被静默丢弃"
 这类坑，注释文本本身含 `<link>` / `<include merge="true">` 字样。若直接对原文跑正则，
 断言会被自己的说明文字绊倒（实测：本文件第一版就是这么红的）。
 注释是给人看的证据，不是 SDF 结构；结构断言必须在去注释后的文本上做。
    """
    return re.sub(r'<!--.*?-->', '', sdf, flags=re.S)


def _sensor_block(sdf: str, sensor_type: str = 'rgbd_camera') -> str:
    """取指定 type 的 `<sensor ...>` 到其 `</sensor>` 之间的整段。

 2026-11-08：主相机由 `camera` 改为 `rgbd_camera`（需要深度来消除侧墙视差）。
    """
    m = re.search(
        r'<sensor\b[^>]*type\s*=\s*"%s"[^>]*>(.*?)</sensor>' % re.escape(sensor_type),
        sdf, re.S)
    assert m, '模型里找不到 type="%s" 的 sensor' % sensor_type
    return m.group(0)


def _pose_of(text: str) -> list[float]:
    m = re.search(r'<pose\b[^>]*>(.*?)</pose>', text, re.S)
    assert m, '找不到 <pose>'
    vals = [float(v) for v in m.group(1).split()]
    assert len(vals) == 6, '<pose> 必须是 6 个数，实际 %r' % (vals,)
    return vals


def _effective_axis_z(pitch: float) -> float:
    """R_y(pitch) · x̂ 的 z 分量。光轴在传感器系为 +X（PX4 mono_cam / OakD-Lite 零位=前视）。"""
    return -math.sin(pitch)


# --------------------------------------------------------------------------------------
# 1. 默认机型即带相机（2026-11-08 用户裁定：相机是平台基本能力）
# --------------------------------------------------------------------------------------
def test_default_model_has_nadir_camera():
    """两处 launch 的 `px4_sim_model` 默认值须为 `gz_agc_x500_nadir`，模型 SDF 含相机传感器。

  相机链的分割标签是 /agc/map 的唯一障碍来源，故默认即带相机、不再 opt-in。
  历史 run 证据按旧机型（gz_agc_x500）封存、不回溯改写；显式可换回旧机型复现。
    """
    for path in (W6_LAUNCH, AIR_LAUNCH):
        src = _read(path)
        m = re.search(r"DeclareLaunchArgument\(\s*['\"]px4_sim_model['\"]\s*,\s*"
                      r"default_value\s*=\s*['\"]([^'\"]+)['\"]", src)
        assert m, '%s 里找不到 px4_sim_model 的 DeclareLaunchArgument' % path.name
        assert m.group(1) == SIM_MODEL, (
            '%s 的 px4_sim_model 默认值应为带相机机型 %s，实际 %r'
            % (path.name, SIM_MODEL, m.group(1)))
        assert 'own_repo_model' in src, (
            '%s 缺少本仓机型条件注入（own_repo_model）——无条件注入会让 PX4 官方臂也走新路径'
            % path.name)
        assert "nadir_sim_model = 'gz_%s'" % MODEL_NAME in src, (
            '%s 的 nadir 机型名应与模型名对齐（gz_%s）' % (path.name, MODEL_NAME))
        assert "highlight_sim_model = 'gz_agc_x500'" in src, (
            '%s 缺少旧机型常量 highlight_sim_model（gz_agc_x500，复现历史 run 用）' % path.name)
    sdf = _strip_comments(_read(MODEL_SDF))
    assert 'type="rgbd_camera"' in sdf, (
        '默认机型对应的 nadir 模型必须是 rgbd_camera（需要深度来消除侧墙视差）')
    assert 'type="segmentation"' in sdf, '默认机型对应的 nadir 模型 SDF 必须含分割传感器'


def test_px4_official_x500_has_no_camera_sensor():
    """PX4 官方 x500/x500_base 里确实没有相机传感器。

  2026-11-08 起默认机型已是本仓 `gz_agc_x500_nadir`，本条不再是"默认臂依据"，
  而是**显式换回官方机型时无相机**的事实依据（换回后感知链无输入，属降级运行）。
  """
    models = ROOT / 'toolchain' / 'PX4-Autopilot' / 'Tools' / 'simulation' / 'gz' / 'models'
    if not models.is_dir():
        import pytest
        pytest.skip('本机无 PX4 gz 模型库（toolchain 未检出）')
    for name in ('x500', 'x500_base'):
        f = models / name / 'model.sdf'
        assert f.is_file(), '缺少 PX4 官方模型 %s' % f
        assert 'type="camera"' not in _read(f) and "type='camera'" not in _read(f), (
            'PX4 官方 %s 不应含相机传感器（显式换官方机型时无相机的事实依据）' % name)


# --------------------------------------------------------------------------------------
# 2. 模型资产
# --------------------------------------------------------------------------------------
def test_model_assets_exist_and_name_matches():
    assert MODEL_CONFIG.is_file(), '缺少 model.config'
    assert MODEL_SDF.is_file(), '缺少 model.sdf'
    cfg = _read(MODEL_CONFIG)
    m = re.search(r'<name>\s*([^<\s]+)\s*</name>', cfg)
    assert m and m.group(1) == MODEL_NAME, (
        'model.config 的 <name> 必须是 %s（gz 按目录名+config 解析），实际 %r'
        % (MODEL_NAME, m and m.group(1)))
    sdf = _strip_comments(_read(MODEL_SDF))
    m = re.search(r'<model\s+name\s*=\s*["\']([^"\']+)["\']', sdf)
    assert m and m.group(1) == MODEL_NAME, (
        '<model name> 必须是 %s —— 实体名由 GZBridge 取 `-m` 的模型名+实例号'
        '（= %s_0），与 SDF 里的 name 不一致会让 IMU/odom 话题对不上而永不 arm'
        % (MODEL_NAME, MODEL_NAME))


def test_exactly_one_rgbd_sensor_and_mounted_on_own_link():
    """恰好 1 个 rgbd 相机（2026-11-08 由 `camera` 改为 `rgbd_camera`）。

 **为什么必须是 rgbd 而不是纯 camera**：分割标签只说"这个像素是障碍"，不说"多高"。
 投到地面平面会把高层建筑的侧墙糊成影子（yard 实测 IoU 0.363、面积膨胀 2.17×）；
 有了深度才能反投影出真实 3D 点。rgbd 的 color 与 depth 同一次渲染 ⇒ 像素严格对齐。
    """
    sdf = _strip_comments(_read(MODEL_SDF))
    n = len(re.findall(r'type\s*=\s*["\']rgbd_camera["\']', sdf))
    assert n == 1, '必须恰好 1 个 type="rgbd_camera" 传感器，实际 %d' % n
    # 不得再残留纯 camera（会与 rgbd 抢 <topic> 后缀，话题名冲突）
    assert not re.search(r'type\s*=\s*["\']camera["\']', sdf), (
        '不得同时保留 type="camera"：rgbd 已提供 RGB，两者会抢同一 <topic> 前缀')
    # 相机必须在**独立 link** 上，且该 link 用 fixed joint 连到 base_link
    assert '<link name="nadir_cam_link">' in sdf, '相机应挂在独立 link nadir_cam_link 上'
    m = re.search(r'<joint\s+name\s*=\s*["\'][^"\']+["\']\s+type\s*=\s*["\']fixed["\']\s*>(.*?)</joint>',
                  sdf, re.S)
    assert m, '缺少 fixed joint'
    j = m.group(1)
    assert '<parent>base_link</parent>' in j, 'fixed joint 的 parent 必须是 base_link'
    assert '<child>nadir_cam_link</child>' in j, 'fixed joint 的 child 必须是 nadir_cam_link'
    # 相机 link 不得带 collision（不参与物理求解）
    link_m = re.search(r'<link\s+name\s*=\s*["\']nadir_cam_link["\']\s*>(.*?)</link>', sdf, re.S)
    assert link_m, '找不到 nadir_cam_link 的 link 段'
    assert '<collision' not in link_m.group(1), (
        'nadir_cam_link 不得含 <collision>（会改变接触/测距物理）')
    # merge include 里**不得**塞 link（sdformat 会静默丢弃）
    inc = re.search(r'<include\b[^>]*merge\s*=\s*["\']true["\'][^>]*>(.*?)</include>', sdf, re.S)
    assert inc, '缺少 include merge="true"'
    assert '<link' not in inc.group(1), (
        'include merge 的子元素只允许 uri/pose/plugin/name/static/placement_frame；'
        '塞 <link> 会被 sdformat **静默丢弃**（展开后 hl 不增加）')


# --------------------------------------------------------------------------------------
# 3. 相机朝向（裁定 1：数值 + 语义 双断言）
# --------------------------------------------------------------------------------------
def test_camera_pitch_is_plus_90_degrees():
    sdf = _strip_comments(_read(MODEL_SDF))
    pose = _pose_of(_sensor_block(sdf))
    pitch = pose[4]
    assert abs(pitch - EXPECTED_PITCH) <= PITCH_TOL, (
        '相机 pitch 必须是 +%.4f rad（90° 下俯量；SDF 字段为正），实际 %.6f。'
        'θ=−90° 会让光轴变成 (0,0,+1) —— 拍天空' % (EXPECTED_PITCH, pitch))


def test_camera_effective_optical_axis_points_down():
    sdf = _strip_comments(_read(MODEL_SDF))
    pitch = _pose_of(_sensor_block(sdf))[4]
    z = _effective_axis_z(pitch)
    assert abs(z - (-1.0)) <= AXIS_Z_TOL, (
        '有效光轴 z 分量应 ≈ −1（正下方），实际 %.6f（pitch=%.6f）' % (z, pitch))


# --------------------------------------------------------------------------------------
# 4. 话题名与桥逐字一致
# --------------------------------------------------------------------------------------
def _bridge_entries():
    data = yaml.safe_load(_read(BRIDGE)) or []
    return {(e.get('ros_topic_name'), e.get('gz_topic_name')): e for e in data}


def test_sdf_topics_match_bridge_verbatim():
    """rgbd 的话题名 = `<topic>` + 固定后缀（实测），桥必须逐字对上。

 与旧 `camera` 的关键差异：旧版必须**显式**写 `<camera_info_topic>`（否则派生成
 `<topic>_info`）；rgbd 实测自己按 `<topic>/camera_info` 派生，正是我们要的名字，
 故**不需要**显式写——这里反过来守"不要写"，避免与派生值冲突。
    """
    sdf = _strip_comments(_read(MODEL_SDF))
    blk = _sensor_block(sdf)
    m = re.search(r'<topic>\s*([^<\s]+)\s*</topic>', blk)
    assert m, 'SDF 缺少 <topic>'
    base = '/' + m.group(1).lstrip('/')
    assert base == GZ_RGBD_BASE, 'gz rgbd 基础话题应为 %s，实际 %s' % (GZ_RGBD_BASE, base)
    assert '<camera_info_topic>' not in blk, (
        'rgbd 不需要显式 <camera_info_topic>：它按 <topic>/camera_info 派生，'
        '写死可能与派生值冲突（实测四话题名见 SDF 注释）')
    gz_image = base + '/image'
    gz_info = base + '/camera_info'
    gz_depth = base + '/depth_image'

    assert gz_image == GZ_IMAGE_TOPIC
    assert gz_info == GZ_INFO_TOPIC
    assert gz_depth == GZ_DEPTH_TOPIC

    entries = _bridge_entries()
    # **2026-11-09 判据反转（用户裁定：退役 RGB 原图桥条目）**：
    # RGB 流**零订阅者**（ADR-0030 的「不接任务链」一节早已登记），却占 1152² 下 3.80 MB/帧 =
    # 感知总带宽的 30%。实测删掉它后 RTF 提升：1152² 0.778→0.853、1536² 0.456→0.567。
    # 故判据从"必须有"反转为"**必须没有**"，防止被"看着少了一条"顺手补回。
    assert (ROS_IMAGE_TOPIC, gz_image) not in entries, (
        'RGB 原图桥条目已于 2026-11-09 退役（零消费者 + 占 30% 带宽），'
        '不得补回；需要取证/测绘时临时加回并同步改本判据。现有配对：%r'
        % (sorted(entries),))
    assert (ROS_INFO_TOPIC, gz_info) in entries, (
        'bridge.yaml 缺少 (%s, %s) 条目' % (ROS_INFO_TOPIC, gz_info))

    assert (ROS_DEPTH_TOPIC, gz_depth) in entries, (
        'bridge.yaml 缺少深度条目 (%s, %s) —— 没有深度就无法反投影，'
        '感知链会退化成"把侧墙糊成影子"' % (ROS_DEPTH_TOPIC, gz_depth))
    # nadir 的 /points 必须**不**桥（纯带宽浪费，本链不用）。
    # 注意只看 nadir 前缀：车的激光点云 /agc/sim/car_points 是合法条目，不能误伤。
    assert not any((r or '').startswith(GZ_RGBD_BASE + '/points') or
                   (g or '').startswith(GZ_RGBD_BASE + '/points')
                   for r, g in entries), (
        '不得桥接 rgbd 的 /points：本链只要 depth，点云是纯带宽浪费')

    info = entries[(ROS_INFO_TOPIC, gz_info)]
    depth = entries[(ROS_DEPTH_TOPIC, gz_depth)]
    for e, ros_t, gz_t in ((info, 'sensor_msgs/msg/CameraInfo', 'gz.msgs.CameraInfo'),
                           (depth, 'sensor_msgs/msg/Image', 'gz.msgs.Image')):
        assert e.get('ros_type_name') == ros_t, '%s 的 ros_type_name 应为 %s' % (ros_t, ros_t)
        assert e.get('gz_type_name') == gz_t, '%s 的 gz_type_name 应为 %s' % (ros_t, gz_t)
        assert e.get('direction') == 'GZ_TO_ROS', '%s 的 direction 应为 GZ_TO_ROS' % ros_t
        assert e.get('qos_profile') == 'SENSOR_DATA', (
            '%s 的 qos_profile 必须 SENSOR_DATA（best-effort）；reliable 会积压引入秒级延迟'
            % ros_t)


def test_bridge_comment_declares_no_consumer_and_topic_vs_frames():
    """注释必须写清口径——这两句是历史踩坑的防复发标记。

  感知地图链立项后：RGB 原图仍仅取证/测绘；**分割标签**由感知地图链消费。
  故断言改为「RGB 仅取证 + 标签消费去向明确」，不再要求「整体无消费者」。
    """
    src = _read(BRIDGE)
    assert ('取证' in src or '测绘' in src), (
        'bridge.yaml 的 nadir 段注释必须写明 RGB 图像仅取证/测绘')
    assert '分割标签' in src and '/agc/obstacles' in src, (
        'bridge.yaml 的 nadir 段注释必须写明分割标签由感知地图链消费（→ /agc/obstacles → /agc/map）')
    assert '话题存在 ≠ 有帧' in src, (
        'bridge.yaml 的 nadir 段注释必须写明"话题存在 ≠ 有帧"的判据')


# --------------------------------------------------------------------------------------
# 5. 机型解析不改工具链
# --------------------------------------------------------------------------------------
def test_own_px4_injects_sys_autostart_4001():
    for path in (W6_LAUNCH, AIR_LAUNCH):
        src = _read(path)
        assert "PX4_SYS_AUTOSTART" in src and "'4001'" in src, (
            '%s 必须为 nadir 机型注入 PX4_SYS_AUTOSTART=4001'
            '（rcS:41-44 优先于按名反查 rcS:52-63，故不需要新增 airframe）' % path.name)
        # 注入必须能传达到 PX4 进程：w6 用 additional_env，air 用 px4_env.update
        assert ('own_px4_env_extra' in src) or ('px4_env_extra' in src), (
            '%s 缺少条件 env 的载体变量' % path.name)


def test_no_new_airframe_in_toolchain():
    if not PX4_AIRFRAMES.is_dir():
        import pytest
        pytest.skip('本机无 PX4 airframes 目录（toolchain 未检出）')
    names = sorted(p.name for p in PX4_AIRFRAMES.iterdir() if p.is_file())
    bad = [n for n in names if 'agc' in n.lower() or 'nadir' in n.lower()]
    assert not bad, (
        'toolchain/PX4-Autopilot 是 pin 的外部依赖，**禁止**在其中新增 airframe：%r。'
        '机型解析应走 PX4_SYS_AUTOSTART（本文件第 5 组断言），不得改工具链' % bad)


def test_no_vision_consumer_of_nadir_image():
    """RGB 原图不得被任何节点订阅（仍仅取证/测绘、不接任务链）。

  注意区分：**RGB 原图**无消费者；**分割标签**（`/agc/air/nadir/seg/labels_map`）
  由感知地图链消费（→ /agc/obstacles → /agc/map），两者是不同的桥条目。

 **判据是"有没有订阅者"，不是"代码里有没有出现 nadir 字样"**：
 机型选择（`nadir_sim_model` / `own_repo_model`）必然出现该词，那不是消费者。
 第一版按"出现即违规"判，把 launch 里的机型开关全判成消费者——过宽的闸门会被人关掉，
 等于没有闸门。故改为查**订阅/回调**形态：
 * C++/Python 里对 `ROS_IMAGE_TOPIC` 字面量的订阅调用；
 * 任何 `create_subscription` / `image_transport` / `rclcpp::Subscription` 附近的该话题；
 * yaml 里把它当 `ros_topic_name` 之外的输入（桥自身条目已排除）。
    """
    topic = ROS_IMAGE_TOPIC
    src_root = ROOT / 'src'
    if not src_root.is_dir():
        import pytest
        pytest.skip('无 src 目录')
    offenders = []
    pats = [
        re.compile(r'create_subscription\s*\([^)]*' + re.escape(topic)),
        re.compile(re.escape(topic) + r'[^\n]{0,80}(subscribe|Subscription|create_subscription)'),
        re.compile(r'image_transport[^\n]{0,120}' + re.escape(topic)),
    ]
    for f in list(src_root.rglob('*.py')) + list(src_root.rglob('*.cpp')) + \
            list(src_root.rglob('*.hpp')):
        try:
            txt = f.read_text(encoding='utf-8', errors='ignore')
        except OSError:
            continue
        if topic not in txt:
            continue
        code = '\n'.join(ln for ln in txt.splitlines() if not ln.lstrip().startswith(('#', '//')))
        for pat in pats:
            if pat.search(code):
                offenders.append(str(f.relative_to(ROOT)))
                break
    assert not offenders, (
        '发现 %s 的订阅者（本相机应无消费者，识别仍靠真值 gt_adapter）：\n  %s'
        % (topic, '\n  '.join(offenders)))


def _strip_code_comments(txt: str, suffix: str) -> str:
    """去注释但保留行结构（便于按行定位），用于"发布者"类结构判定。"""
    if suffix in ('.py',):
        return '\n'.join(re.sub(r'#.*$', '', ln) for ln in txt.splitlines())
    out = []
    for ln in txt.splitlines():
        out.append(re.sub(r'//.*$', '', ln))
    # 块注释 /* ... */
    return re.sub(r'/\*.*?\*/', '', '\n'.join(out), flags=re.S)


def _call_args(code: str, fname: str) -> list[tuple[int, int, list[str]]]:
    """抽出所有 `fname(...)` 调用：(起始位置, 结束位置, **顶层实参**列表)。

 正确处理嵌套括号 / C++ 模板尖括号 / 字符串字面量 —— 不能像第一版那样用 `[^;]{0,N}`
 跨行瞎扫，那会把**相邻的另一次调用**吞进来（实测把 `create_subscription` 的实参
 当成 `create_publisher` 的实参，误判出假的发布者）。
    """
    calls = []
    for m in re.finditer(r'\b' + re.escape(fname) + r'\b', code):
        i = m.end()
        # 跳过模板实参 <...>（C++）
        while i < len(code) and code[i] in ' \t\n':
            i += 1
        if i < len(code) and code[i] == '<':
            depth = 0
            while i < len(code):
                if code[i] == '<':
                    depth += 1
                elif code[i] == '>':
                    depth -= 1
                    if depth == 0:
                        i += 1
                        break
                i += 1
        while i < len(code) and code[i] in ' \t\n':
            i += 1
        if i >= len(code) or code[i] != '(':
            continue
        # 平衡括号取整段实参
        depth, j, in_str = 0, i, None
        while j < len(code):
            c = code[j]
            if in_str:
                if c == in_str and code[j - 1] != '\\':
                    in_str = None
            elif c in '\'"':
                in_str = c
            elif c == '(':
                depth += 1
            elif c == ')':
                depth -= 1
                if depth == 0:
                    break
            j += 1
        inner = code[i + 1:j]
        # 顶层逗号切分
        args, depth2, buf, in_str = [], 0, [], None
        for c in inner:
            if in_str:
                buf.append(c)
                if c == in_str:
                    in_str = None
                continue
            if c in '\'"':
                in_str = c
                buf.append(c)
            elif c in '(<[':
                depth2 += 1
                buf.append(c)
            elif c in ')>]':
                depth2 -= 1
                buf.append(c)
            elif c == ',' and depth2 == 0:
                args.append(''.join(buf).strip())
                buf = []
            else:
                buf.append(c)
        if buf:
            args.append(''.join(buf).strip())
        calls.append((m.start(), j, args))
    return calls


def _topic_defaults(code: str) -> dict[str, str]:
    """`变量 -> /agc/targets`：该变量**在它自己那次 declare_parameter 调用里**取了 /agc/targets。

 **为什么不能用 `[^;]*?` 正则**：那会跨行把**下一条** declare_parameter 的默认值
 （如 `targets_topic`）算到上一行的变量（如 `goal_topic`）头上。实测因此把
 `agc_rl/high_level_node.py` 的 `self.goal_topic` 误认成 /agc/targets 的发布话题。
 ⇒ 必须按**单次调用的实参**判定。
    """
    out = {}
    for start, _end, args in _call_args(code, 'declare_parameter'):
        if not any('/agc/targets' in a for a in args):
            continue
        head = code[max(0, start - 200):start]
        m = re.search(r'([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:self\.)?\s*$', head)
        if m:
            out[m.group(1)] = '/agc/targets'
    return out


def test_targets_publisher_is_still_gt_adapter_only():
    """/agc/targets 的发布者仍是 gt_adapter —— 相机不得改变任务链的数据来源。

 **这条判据写错过两次，记下来防止再犯**（两次都是"判据与真实代码脱节"）：

 1. 第一版在 `create_publisher` 的**同一行**里 grep `/agc/targets`。但该话题在代码里是
 **参数默认值**（`target_topic_`），`create_publisher` 收到的是**变量**，故永远匹配不到
 ⇒ 断言恒空。这比没有断言更糟：它会让"真的多了一个发布者"也照样绿。
 2. 第二版改成"`create_publisher` 附近 200 字符内出现该变量"。但 `[^;]` 会跨行吞掉**下一条**
       `create_subscription(..., self.targets_topic, ...)`，把 `agc_rl/high_level_node.py`
 （它只**订阅** targets、发布的是 goal_topic）误判成发布者。

    **正确做法**：解析 `create_publisher(...)` 的**顶层实参**，只看**话题那个实参**：
 * C++ `create_publisher<Msg>(topic, qos)` → 实参[0] 是话题；
      * Python `self.create_publisher(Msg, topic, qos)` → 实参[1] 是话题。
 再把该实参解析成"字面量 / 已知默认值为 /agc/targets 的变量"，只有后者才算发布者。
 另加**退化保护**：一处发布者都找不到即 FAIL（说明判据已与代码脱节）。
    """
    src_root = ROOT / 'src'
    if not src_root.is_dir():
        import pytest
        pytest.skip('无 src 目录')

    publishers = []   # (file, topic_expr)
    candidates = []   # 把 /agc/targets 作默认值的文件（订阅方也会在此）
    for f in list(src_root.rglob('*.cpp')) + list(src_root.rglob('*.py')):
        try:
            txt = f.read_text(encoding='utf-8', errors='ignore')
        except OSError:
            continue
        if '/agc/targets' not in txt:
            continue
        code = _strip_code_comments(txt, f.suffix)
        defaults = _topic_defaults(code)
        if defaults:
            candidates.append(str(f.relative_to(ROOT)))
        for _s, _e, args in _call_args(code, 'create_publisher'):
            # 话题实参位置：Python 是第 2 个，C++ 是第 1 个
            idx = 1 if f.suffix == '.py' else 0
            if len(args) <= idx:
                continue
            topic_expr = args[idx]
            if '/agc/targets' in topic_expr:
                publishers.append((str(f.relative_to(ROOT)), topic_expr))
                continue
            ident = re.fullmatch(r'(?:self\.)?([A-Za-z_][A-Za-z0-9_]*)', topic_expr.strip())
            if ident and ident.group(1) in defaults:
                publishers.append((str(f.relative_to(ROOT)), topic_expr))

    assert publishers, (
        '没解析出 /agc/targets 的任何发布者 —— 判据已与代码脱节（例如发布方式又变了）。'
        '把 /agc/targets 作默认值的候选文件：%r。'
        '**不得**让它退化成空断言（那会让新增发布者也照样绿）' % (candidates,))
    non_gt = [p for p, _ in publishers if 'gt_adapter' not in p]
    assert not non_gt, (
        '/agc/targets 的发布者必须只有 gt_adapter（识别仍靠真值，ADR-0009 (a2)），另发现：%r。'
        '全部发布点：%r' % (non_gt, publishers))


# --------------------------------------------------------------------------------------
# 6. 感知地图链：分割传感器 / 桥条目 / 障碍标签（立项后新增的正向守护）
# --------------------------------------------------------------------------------------
def test_segmentation_sensor_mounts_with_rgb_camera():
    """分割传感器与 RGB 相机共 link / 共姿态 / 共内参，且只出一个 labels_map 话题。"""
    sdf = _strip_comments(_read(MODEL_SDF))
    n = len(re.findall(r'type\s*=\s*["\']segmentation["\']', sdf))
    assert n == 1, '必须恰好 1 个 type="segmentation" 传感器，实际 %d' % n
    m = re.search(r'<sensor\b[^>]*type\s*=\s*"segmentation"[^>]*>(.*?)</sensor>', sdf, re.S)
    assert m, '找不到 segmentation sensor'
    blk = m.group(0)
    assert '<segmentation_type>semantic</segmentation_type>' in blk, '分割类型应为 semantic'
    assert _pose_of(blk)[4] == _pose_of(_sensor_block(sdf))[4], (
        '分割相机 pitch 必须与 RGB 相机一致（共姿态）')
    t = re.search(r'<topic>\s*([^<\s]+)\s*</topic>', blk)
    assert t and '/' + t.group(1).lstrip('/') == GZ_SEG_TOPIC, (
        '分割相机 gz 话题应为 %s' % GZ_SEG_TOPIC)
    ci = re.search(r'<camera_info_topic>\s*([^<\s]+)\s*</camera_info_topic>', blk)
    assert ci and '/' + ci.group(1).lstrip('/') == ROS_SEG_INFO_TOPIC, (
        '分割相机须显式写 <camera_info_topic>（gz 实测会发布该话题）')
    # 与 RGB 相机同一独立 link（未在别处另起 link）
    link_m = re.search(r'<link\s+name\s*=\s*["\']nadir_cam_link["\']\s*>(.*?)</link>', sdf, re.S)
    assert link_m and 'type="segmentation"' in link_m.group(1), (
        '分割传感器必须与 RGB 相机同挂 nadir_cam_link（保证共位姿/共内参）')


def test_segmentation_labels_bridge_entry():
    """labels_map + 分割 camera_info 桥条目存在且类型 / 方向 / QoS 正确。"""
    entries = _bridge_entries()
    for topic, ros_type, gz_type in (
        (ROS_SEG_LABELS_TOPIC, 'sensor_msgs/msg/Image', 'gz.msgs.Image'),
        (ROS_SEG_INFO_TOPIC, 'sensor_msgs/msg/CameraInfo', 'gz.msgs.CameraInfo'),
    ):
        key = (topic, topic)
        assert key in entries, 'bridge.yaml 缺少 %s 条目' % topic
        e = entries[key]
        assert e.get('ros_type_name') == ros_type, '%s 的 ros_type_name' % topic
        assert e.get('gz_type_name') == gz_type, '%s 的 gz_type_name' % topic
        assert e.get('direction') == 'GZ_TO_ROS'
        assert e.get('qos_profile') == 'SENSOR_DATA'


def test_obstacles_carry_segmentation_label():
    """世界生成链给每个障碍 model 打 gz-sim-label-system 标签（地面/背景不显影）。"""
    src = _read(ROOT / 'src' / 'agc_sim' / 'launch' / 'world_bringup.launch.py')
    assert 'gz-sim-label-system' in src, '障碍 SDF 注入链缺少 label 插件'
    assert 'OBSTACLE_SEG_LABEL' in src and '_label_plugin_sdf' in src, (
        'label 应以单一常量 + 单一辅助函数注入，避免两处重复定义')
    assert 'gz::sim::systems::Label' in src
