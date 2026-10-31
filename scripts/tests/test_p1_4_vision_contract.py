#!/usr/bin/env python3
"""离线单测：P1-4 视觉链路的**红线**与取证口径（T0，不启 ROS / 不启仿真）。

断言的是「纪律能在代码层面被证明」，不是"跑起来看着对"：

  1. `vision_detector.py` **不订阅任何 `/agc/gt`**（ADR-0103 红线：vision 不得用真值）；
  2. `vision_detector.py` 在 `perception_path != vision` 时**显式拒绝**（互斥，不混跑）；
  3. `none` 后端 = 空检测 + `degraded=true / reason=no_model`（显式降级，不静默回退 truth）；
  4. `camera_probe.py` 的判定在**无帧**时给 pending/false，而非"通过"（缺值不当 0 也不当通过）；
  5. `record_dataset.py` 的同步规则在超窗时**丢弃并计数**（不伪造标签），标签语义标注明确；
  6. 9 消息 ABI 未被本轮触碰（`src/agc_msgs/` 无 golden / msg 变更由 git 差异另行核对，
     此处只断言视觉接口**不在** 9 消息清单内）；
  7. 录制脚本产出的标签**不回灌**：vision_detector 的订阅集合与 record_dataset 的订阅集合不相交于
     "决策输入"——录制工具与识别节点是**两个进程、两套订阅**。

实现策略：**静态源码检查 + 纯函数调用**，不 import rclpy 的节点去起图。
`vision_detector` 的判定逻辑以源码断言（其节点类在 import 时即绑定 rclpy，避免测试环境依赖）。
"""

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
VISION = REPO / 'scripts' / 'vision'
DETECTOR = VISION / 'vision_detector.py'
PROBE = VISION / 'camera_probe.py'
RECORDER = VISION / 'record_dataset.py'

# 契约 [#messages] 冻结的 9 个消息（**视觉接口不得混入**）
FROZEN_9 = {
    'AgcTaskState', 'AirObservationArray', 'ObstacleObservation', 'ObstacleTrack',
    'ObstacleTrackArray', 'SensorObservation', 'TargetObservation', 'TargetTrack',
    'TargetTrackArray',
}


def _tree(path):
    return ast.parse(path.read_text(encoding='utf-8'))


def _string_constants(tree):
    return {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant)
            and isinstance(n.value, str)}


# --------------------------------------------------------------------------------------
# 1. vision 路径不得订阅真值
# --------------------------------------------------------------------------------------

def test_detector_does_not_subscribe_ground_truth():
    """红线：识别节点**可执行代码**里不得出现任何 `/agc/gt` 话题字符串。

    只查 docstring / 注释以外的地方——文档里**必须**能写"不订阅 /agc/gt"来说明纪律，
    否则这条测试会与"把纪律写清楚"互相打架。
    """
    tree = _tree(DETECTOR)
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, 'body', None) or []
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                docstrings.add(id(body[0].value))
    live_strings = {n.value for n in ast.walk(tree)
                    if isinstance(n, ast.Constant) and isinstance(n.value, str)
                    and id(n) not in docstrings}
    offenders = sorted(s for s in live_strings if '/agc/gt' in s)
    assert not offenders, (
        'vision_detector.py 的可执行代码中出现真值话题 %s —— 违反 ADR-0103' % offenders)


def test_detector_declares_empty_truth_subscription_list():
    """状态话题里 `truth_inputs_subscribed` 恒为空 —— 可被 ros2 node info 复核。"""
    text = DETECTOR.read_text(encoding='utf-8')
    assert "'truth_inputs_subscribed': []" in text


def test_detector_only_subscribes_image_and_camera_info():
    """订阅集合只允许 Image / CameraInfo 两路（没有 PoseStamped 之类真值入口）。"""
    tree = _tree(DETECTOR)
    created = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == 'create_subscription' and node.args:
            arg = node.args[0]
            created.append(arg.id if isinstance(arg, ast.Name) else ast.dump(arg))
    assert created, '未找到 create_subscription（解析失效会导致本测试永远通过）'
    # 订阅的类型必须是 Image / CameraInfo（第一个位置参数是类型）
    type_names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == 'create_subscription' and node.args:
            t = node.args[0]
            type_names.append(t.id if isinstance(t, ast.Name) else None)
    assert set(type_names) == {'Image', 'CameraInfo'}, type_names


# --------------------------------------------------------------------------------------
# 2. 路径互斥
# --------------------------------------------------------------------------------------

def test_detector_rejects_when_perception_path_is_not_vision():
    """`perception_path != vision` → 显式 SystemExit(2)，不是静默继续。"""
    text = DETECTOR.read_text(encoding='utf-8')
    assert "self.declare_parameter('perception_path', 'truth')" in text, (
        '默认值必须是 truth（truth 为默认路径）')
    assert 'raise SystemExit(2)' in text
    assert 'perception_path=%r ≠ vision' in text or 'perception_path=%r' in text


# --------------------------------------------------------------------------------------
# 3. 无模型 = 显式降级
# --------------------------------------------------------------------------------------

def test_no_model_backend_yields_empty_detections_and_marks_degraded():
    text = DETECTOR.read_text(encoding='utf-8')
    # none 后端函数体恒返回空列表
    assert 'def _backend_none(node, image_msg, camera_info):' in text
    body = text.split('def _backend_none', 1)[1].split('BACKENDS', 1)[0]
    assert 'return []' in body
    # 降级标注
    assert "self.degrade_reason = 'no_model' if self.degraded else ''" in text
    assert "'degraded': bool(degraded)" in text
    assert "'degrade_reason': reason or None" in text


def test_detector_has_no_silent_truth_fallback_branch():
    """不得有"检测为空 → 调真值"的路径：源码里不出现 gt/PoseStamped 导入。"""
    tree = _tree(DETECTOR)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
            for a in node.names:
                imported.add('%s.%s' % (node.module, a.name))
    assert not any('geometry_msgs' in m or 'PoseStamped' in m for m in imported), imported


# --------------------------------------------------------------------------------------
# 4. 探针判据：无帧不是通过
# --------------------------------------------------------------------------------------

def test_camera_probe_verdict_is_false_without_frames():
    """summarize([]) → hz_mean None；verdict 的 A2/A3 均为 False（缺值不得当通过）。"""
    sys.path.insert(0, str(VISION))
    try:
        import camera_probe
    finally:
        sys.path.pop(0)
    s = camera_probe.summarize([], 5.0)
    assert s['frames_received'] == 0
    assert s['hz_mean'] is None
    # 复算 main 里的两个判定表达式（与实现同式）
    a2_ok = s['hz_mean'] is not None and s['hz_mean'] >= 10.0
    a3_stats = s.get('mean_luma_median')
    a3_ok = (a3_stats is not None and a3_stats > 5.0
             and s.get('std_luma_median', 0.0) > 1.0)
    assert a2_ok is False and a3_ok is False


def test_camera_probe_exit_code_semantics_documented():
    text = PROBE.read_text(encoding='utf-8')
    assert '退出码：0' in text and '2 = 一帧未收到' in text


# --------------------------------------------------------------------------------------
# 5. 录制：超窗丢弃、标签语义标注
# --------------------------------------------------------------------------------------

def test_recorder_drops_out_of_window_frames_instead_of_forging_labels():
    text = RECORDER.read_text(encoding='utf-8')
    assert 'self.dropped_out_of_window += 1' in text
    assert 'if dt_ms > self.args.max_dt_ms:' in text
    assert 'drop_and_count' in text or '不伪造标签' in text


def test_recorder_marks_labels_as_evaluation_only():
    text = RECORDER.read_text(encoding='utf-8')
    assert 'ground_truth_for_evaluation_only' in text
    assert 'forbidden_as_vision_decision_input' in text


def test_recorder_and_detector_are_separate_processes():
    """录制工具读 gt、识别节点不读 gt —— 两者不得是同一节点（文件不同且订阅不同）。"""
    det = DETECTOR.read_text(encoding='utf-8')
    rec = RECORDER.read_text(encoding='utf-8')
    assert "PoseStamped" in rec and "PoseStamped" not in det
    assert 'gt_topic' in rec and 'gt_topic' not in det


# --------------------------------------------------------------------------------------
# 6. 视觉接口不在 9 消息 ABI 内
# --------------------------------------------------------------------------------------

def test_vision_interface_is_outside_frozen_abi():
    text = DETECTOR.read_text(encoding='utf-8')
    assert 'vision_msgs' in text
    for name in FROZEN_9:
        # 允许提到名字（注释里说明"不在 9 消息内"），但不得 import agc_msgs 的这 9 个
        assert ('from agc_msgs.msg import %s' % name) not in text
        assert ('agc_msgs/msg/%s' % name) not in text


def test_agc_msgs_sources_unchanged_by_vision_work():
    """`src/agc_msgs/` 的 9 个 .msg 文件与 CMake 清单必须仍只含那 9 个（无新增视觉消息）。"""
    msgs = sorted(p.stem for p in (REPO / 'src' / 'agc_msgs' / 'msg').glob('*.msg'))
    assert set(msgs) == FROZEN_9, (
        '9 消息 ABI 被改动：%s' % sorted(set(msgs) ^ FROZEN_9))
    cmake = (REPO / 'src' / 'agc_msgs' / 'CMakeLists.txt').read_text(encoding='utf-8')
    for name in FROZEN_9:
        assert '"msg/%s.msg"' % name in cmake
    assert 'Detection' not in cmake and 'Vision' not in cmake


# --------------------------------------------------------------------------------------
# 7. 工具自检：脚本可编译、无 __main__ 之外的副作用
# --------------------------------------------------------------------------------------

@pytest.mark.parametrize('path', [DETECTOR, PROBE, RECORDER])
def test_vision_tools_compile(path):
    compile(path.read_text(encoding='utf-8'), str(path), 'exec')


def test_vision_tools_expose_documented_exit_codes():
    for path in (PROBE, RECORDER):
        text = path.read_text(encoding='utf-8')
        assert '退出码' in text, path
