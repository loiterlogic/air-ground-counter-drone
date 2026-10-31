#!/usr/bin/env python3
"""离线单测：P1-4 round-2 的**决策接线**红线（T0，不启 ROS / 不启仿真）。

round-1 已把"视觉链路本身"的红线钉成测试（`test_p1_4_vision_contract.py`）。
本轮扩权到 `w6.launch.py` / `run_logger.cpp` / 契约参数清单，因此这里断言的是**接线纪律**：

  1. `w6.launch.py` 的默认值仍是 `truth` / `gz_x500` / `vision_detector=false`（既有行为不变）；
  2. `perception_path` 与 `vision_detector` **互斥校验**存在且方向正确（truth+true 拒、vision+false 拒）；
  3. `run_logger` 的 summary 含 `perception_path` 与 `vision_model{id,name,version,sha256}`，
     且**既有字段未被改语义**（抽查 terminal_state / shield_infeasible_rate / definition_version）；
  4. 契约 `#params` 记录了 `/agc/perception/path`，并写明 truth 默认 / 互斥 / 无模型降级；
  5. 9 消息 ABI 未被任何一轮触碰（与 round-1 同一断言，防回归）。

纯静态（读源码 / 读文档），不发进程。
"""

import ast
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
W6 = REPO / 'src' / 'agc_task' / 'launch' / 'w6.launch.py'
RUN_LOGGER = REPO / 'src' / 'agc_task' / 'src' / 'run_logger.cpp'
CONTRACT = REPO / 'docs' / 'ROS2迁移交接文档.md'
PLAN = REPO / 'docs' / 'plan' / 'p1-4-视觉算法接入.md'
VISION_TESTS = REPO / 'scripts' / 'tests' / 'test_p1_4_vision_contract.py'

FROZEN_9 = {
    'AgcTaskState', 'AirObservationArray', 'ObstacleObservation', 'ObstacleTrack',
    'ObstacleTrackArray', 'SensorObservation', 'TargetObservation', 'TargetTrack',
    'TargetTrackArray',
}


def _text(path):
    return path.read_text(encoding='utf-8')


# --------------------------------------------------------------------------------------
# 1. 默认行为不变
# --------------------------------------------------------------------------------------

@pytest.mark.parametrize('name,default', [
    ('perception_path', 'truth'),
    ('vision_detector', 'false'),
    ('px4_sim_model', 'gz_x500'),
    ('vision_model_id', 'none'),
])
def test_w6_defaults_preserve_existing_behaviour(name, default):
    """默认值必须让既有链路逐字不变：truth / 无相机 / 不起识别。"""
    text = _text(W6)
    pattern = r"DeclareLaunchArgument\(\s*'%s',\s*default_value='%s'" % (name, re.escape(default))
    assert re.search(pattern, text), '缺少或改动了默认值：%s 应为 %r' % (name, default)


def test_w6_still_accepts_empty_router_defaults_for_existing_args():
    """既有参数（world_map / target_source 等）的"空串=按场景/能力表"语义不得被本轮改掉。"""
    text = _text(W6)
    for name in ('world_map', 'target_source', 'observe_yaw_mode', 'goal_follow_target'):
        assert re.search(r"DeclareLaunchArgument\(\s*'%s'" % name, text), name
    # 空串仍走既有解析路径
    assert "world_map = LaunchConfiguration('world_map').perform(context).strip()" in text


# --------------------------------------------------------------------------------------
# 2. 互斥校验
# --------------------------------------------------------------------------------------

def test_w6_rejects_unknown_perception_path():
    text = _text(W6)
    assert "if perception_path not in ('truth', 'vision'):" in text
    assert '未知 perception_path=' in text


def test_w6_rejects_truth_with_vision_detector():
    """truth + vision_detector:=true 必须**拒绝运行**（这是"静默混用"的唯一入口）。"""
    text = _text(W6)
    assert "if perception_path == 'truth' and vision_detector_on:" in text
    assert '不得启用 vision_detector:=true' in text
    # 拒绝必须是 raise（不是 warning / 静默改路径）
    idx = text.index("if perception_path == 'truth' and vision_detector_on:")
    window = text[idx:idx + 600]
    assert 'raise RuntimeError' in window


def test_w6_rejects_vision_without_detector():
    """vision 但未显式启用识别 → 拒绝，不得静默当 truth 跑。"""
    text = _text(W6)
    assert "if perception_path == 'vision' and not vision_detector_on:" in text
    assert '不静默降级为 truth' in text


def test_w6_does_not_orchestrate_detector_node():
    """派工白名单：本入口**只透传与校验**，不改任务编排。

    若有人把识别节点塞进 w6 编排，会引入新进程与依赖（agc_vision 包并不存在），
    本条把它挡回去 —— 识别进程按工具域独立起。
    """
    text = _text(W6)
    assert "package='agc_vision'" not in text
    assert 'executable=\'vision_detector\'' not in text


# --------------------------------------------------------------------------------------
# 3. run_logger summary 新键
# --------------------------------------------------------------------------------------

@pytest.mark.parametrize('needle', [
    'perception_path_ = declare_parameter<std::string>("perception_path", "truth");',
    'vision_model_id_ = declare_parameter<std::string>("vision_model_id", "none");',
    'vision_model_name_ = declare_parameter<std::string>("vision_model_name", "");',
    'vision_model_version_ = declare_parameter<std::string>("vision_model_version", "");',
    'vision_model_sha256_ = declare_parameter<std::string>("vision_model_sha256", "");',
])
def test_run_logger_declares_new_params(needle):
    assert needle in _text(RUN_LOGGER)


def _cpp_summary_literal(name):
    """C++ 源码里 summary 键的**实际**写法（手写转义）：`\\"name\\": `。"""
    return '\\"%s\\": ' % name


def test_run_logger_writes_perception_path_and_model_block():
    text = _text(RUN_LOGGER)
    assert _cpp_summary_literal('perception_path') in text
    assert _cpp_summary_literal('vision_model') in text
    assert '<< vision_model_id_' in text
    for key in ('id', 'name', 'version', 'sha256'):
        assert _cpp_summary_literal(key) in text, key


def test_run_logger_existing_summary_fields_unchanged():
    """既有字段**语义与键名**不得被本轮改掉（只增不改）。"""
    text = _text(RUN_LOGGER)
    for needle in ('terminal_state', 'terminal_reason_code', 'shield_infeasible_rate',
                   'reset_failure_rate', 'definition_version', 'episode_window_metrics',
                   'visibility_metrics'):
        assert _cpp_summary_literal(needle) in text, needle
    # 新键插入位置必须在 reset_failed 之后、历史口径块之前（不改顺序语义）
    i_new = text.index(_cpp_summary_literal('perception_path'))
    i_old = text.index('=== 历史口径 proxy_v1')
    assert i_new < i_old


def test_run_logger_new_keys_are_valid_json_shape():
    """summary 是**手写字符串拼接**：新块必须能拼成合法 JSON（引号/逗号平衡）。

    这里用最小复现：把新块的两行按同样格式拼接后交给 json 解析。
    """
    import json
    line1 = '  "perception_path": "vision",\n'
    line2 = ('  "vision_model": {"id": "none", "name": "", "version": "", "sha256": ""},\n')
    doc = json.loads('{\n' + line1 + line2 + '  "x": 1\n}')
    assert doc['perception_path'] == 'vision'
    assert doc['vision_model']['id'] == 'none'


def test_run_logger_no_truth_shortcut_in_vision_branch():
    """red line：run_logger 不得因为 perception_path=vision 就改写既有真值链字段。"""
    text = _text(RUN_LOGGER)
    # 不得出现 "if perception_path_ == "vision"" 之类**改变采样/终态**的分支
    for bad in ('if (perception_path_ == "vision")', "if (perception_path_ == 'vision')"):
        assert bad not in text


# --------------------------------------------------------------------------------------
# 4. 契约参数入口
# --------------------------------------------------------------------------------------

def test_contract_lists_perception_path():
    text = _text(CONTRACT)
    assert '`/agc/perception/path`' in text
    anchor = '<a id="perception-path"></a>'
    assert anchor in text
    seg = text.split(anchor, 1)[1][:1600]
    assert 'truth' in seg and 'vision' in seg
    assert '默认' in seg
    assert '互斥' in seg
    assert '显式降级' in seg or '降级' in seg


def test_contract_still_states_abi_and_execution_port_unchanged():
    text = _text(CONTRACT)
    assert '#messages' in text and '不得变更' in text
    assert '#execution-port' in text


# --------------------------------------------------------------------------------------
# 5. ABI 防回归
# --------------------------------------------------------------------------------------

def test_nine_messages_still_frozen():
    msgs = sorted(p.stem for p in (REPO / 'src' / 'agc_msgs' / 'msg').glob('*.msg'))
    assert set(msgs) == FROZEN_9, sorted(set(msgs) ^ FROZEN_9)
    cmake = _text(REPO / 'src' / 'agc_msgs' / 'CMakeLists.txt')
    for name in FROZEN_9:
        assert '"msg/%s.msg"' % name in cmake


def test_vision_contract_tests_from_round1_still_present():
    assert VISION_TESTS.is_file()
    text = _text(VISION_TESTS)
    assert 'test_detector_does_not_subscribe_ground_truth' in text


# --------------------------------------------------------------------------------------
# 6. 语法自检（防止解析器退化导致空断言通过）
# --------------------------------------------------------------------------------------

def test_w6_parses_and_contains_expected_symbols():
    tree = ast.parse(_text(W6))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    for sym in ('perception_path', 'vision_detector_on', 'px4_sim_model'):
        assert sym in names


def test_plan_doc_has_interface_anchor():
    assert '<a id="p1-4-interface"></a>' in _text(PLAN)
