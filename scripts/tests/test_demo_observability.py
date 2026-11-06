"""P1-3 可观测与演示呈现的离线回归（**不启任何仿真、不读 ROS 图**）。

守护 的七条出口判据里**可在离线判定**的部分（[ 出口判据]）：

 1. 状态枚举 → 人话映射**单一实现**，9 个枚举 + reason_code 全覆盖；
 2. 表述红线：`TRACKING_SUCCESS` 的任何展示文案都不含"拦截完成"；
 3. 面板：2 Hz 节拍、含状态 / 说明 / 目标距离 / 已用时，headless 不受影响；
 4. 时间线：状态跳变才记一行，关键节点够 5 个或**如实记账**；
 5. 终态解释：指标只来自 `summary.json`，阈值只来自 `params_applied.yaml`，缺就说不缺就编；
 6. 展示层**未新增话题 / 未改 ABI / 未新增命令者**；
 7. `TRACKING_SUCCESS` 不被显示成拦截（与 2 同源，但单独有"文案表被打回"的对照）。

运行：
  python3 -m pytest scripts/tests/test_demo_observability.py -q     # 纯离线，无需 source ROS
"""

import ast
import io
import json
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
DEMO = os.path.join(ROOT, 'scripts', 'demo')
sys.path.insert(0, DEMO)

import panel        # noqa: E402
import status_map   # noqa: E402
import timeline as timeline_mod   # noqa: E402
import verdict      # noqa: E402

P13_MODULES = ('status_map.py', 'panel.py', 'timeline.py', 'verdict.py', 'start.py')

FIELDS = {
    'state_name': 'GROUND_APPROACH', 'reason_code': 'ground_approach', 'distance_m': 8.4,
    'obs_age_s': 0.12, 'air_controller': 'lqr_tracker_node',
    'ground_controller': 'ground_commander', 'elapsed_s': 80.0,
    'tracking_milestone_met': False,
}


def _read(name):
    with open(os.path.join(DEMO, name), encoding='utf-8') as f:
        return f.read()


def _code_only(text):
    """剥掉 docstring 与注释，只留可执行代码（避免"说明里提到"被当成"真的做了"）。"""
    tree = ast.parse(text)
    doc_lines = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, 'body', None) or []
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                doc_lines.update(range(body[0].lineno, body[0].end_lineno + 1))
    out = []
    for idx, line in enumerate(text.splitlines(), start=1):
        if idx in doc_lines or line.strip().startswith('#'):
            continue
        out.append(line)
    return '\n'.join(out)


# --------------------------------------------------------------------------------------
# 1. 状态映射：单一实现 + 全覆盖
# --------------------------------------------------------------------------------------

def test_status_map_covers_all_nine_states():
    rep = status_map.coverage_report()
    assert rep['ok'] is True, rep['problems']
    assert rep['states'] == 9
    for code in range(9):
        entry = status_map.state_by_code(code)
        assert entry['state'] == code
        assert entry['text'], 'state=%d 没有文案' % code


def test_status_map_matches_msg_enum_values():
    """映射的 state 数值必须与 `AgcTaskState.msg` 的常量**逐值一致**。"""
    msg = os.path.join(ROOT, 'src', 'agc_msgs', 'msg', 'AgcTaskState.msg')
    text = open(msg, encoding='utf-8').read()
    declared = {int(m.group(2)): m.group(1)
                for m in re.finditer(r'^uint8\s+([A-Z_]+)=(\d+)\s*(?:#.*)?$', text, re.M)}
    assert len(declared) == 9, 'AgcTaskState.msg 应有 9 个状态常量：%r' % declared
    for code, name in declared.items():
        entry = status_map.state_by_code(code)
        assert entry['name'] == name, (
            'state=%d 映射成 %r，msg 里是 %r' % (code, entry['name'], name))
        assert status_map.state_by_name(name)['state'] == code


def test_status_map_is_the_only_state_mapping():
    """`scripts/demo/` 里不得出现第二份状态文案表（单一实现）。"""
    for name in P13_MODULES:
        text = _read(name)
        if name == 'status_map.py':
            continue
        for phrase in ('拦截完成', '抵近并持续跟踪成功', '地面车前往目标'):
            assert phrase not in text, (
                '%s 里硬编码了状态文案 %r —— 文案必须只存在于 status_map.py' % (name, phrase))


def test_reason_codes_are_translated():
    """`reason_code` 的全部已知取值都要有人话；未知值**如实标注未收录**（不静默吞掉）。"""
    from pathlib import Path
    cpp = Path(ROOT, 'src', 'agc_task', 'src', 'task_manager.cpp').read_text(encoding='utf-8')
    # 从真实实现里抓 reason 字面量（不维护第二份清单：清单本身就是被测对象）。
    # 只扫**单行可执行代码**：注释块里出现的调用名不算调用点（否则头注释会造出假阳性）。
    code_lines = [ln for ln in cpp.splitlines()
                  if ln.strip() and not ln.lstrip().startswith('//')]
    code = '\n'.join(code_lines)
    found = set(re.findall(r'(?:setState|enterTerminal)\([^,()]+,\s*"([a-zA-Z0-9_]+)"\)', code))
    found |= set(re.findall(r'fail\(res,\s*"([a-zA-Z0-9_]+)"', code))
    # 走变量传进来的 reason（`fail(res, reason, evid)`）来自 门禁，见下方显式清单
    found |= set(re.findall(r'reason = "([a-zA-Z0-9_]+)";', code))
    found |= {'TIMEOUT', 'abort', 'tracking_milestone', 'target_acquired', 'ground_approach'}
    for code_name in ('CAPTURE_NET', 'JAM_RTL', 'JAM_LAND', 'JAM_HOLD', 'JAM_LOST'):
        found.add(code_name)
    missing = [c for c in sorted(found) if '未收录' in status_map.reason_text(c)]
    assert not missing, '这些 reason_code 没有人话文案：%s' % missing
    # 未知值：明确标注未收录，并原样回显（可追溯）
    text = status_map.reason_text('SOMETHING_NEW ep=1')
    assert '未收录' in text and 'SOMETHING_NEW' in text


def test_reason_text_handles_event_strings():
    """配套事件串（`CAPTURE_NET ep=3 t=…`）取首 token 翻译，不要求调用方先切串。"""
    assert '物理捕获' in status_map.reason_text('CAPTURE_NET ep=3 t=12.5 target=intruder_uav')
    assert status_map.reason_text('') == '无'


def test_unknown_state_is_reported_not_invented():
    entry = status_map.state_by_name('NOT_A_STATE')
    assert entry['state'] is None
    assert '未识别' in entry['text']
    assert status_map.state_by_code(99)['state'] is None


# --------------------------------------------------------------------------------------
# 2. 表述红线（静态禁词）
# --------------------------------------------------------------------------------------

def test_c8_tracking_success_has_no_intercept_wording():
    tracking = status_map.state_by_name('TRACKING_SUCCESS')
    for bad in status_map.FORBIDDEN_IN_TRACKING:
        assert bad not in tracking['text'], (
            'C8 违规：TRACKING_SUCCESS 文案含 %r（实际 %r）' % (bad, tracking['text']))
    # 语义必须是"跟踪"，且与阶段 B 的拦截**分开**
    assert '跟踪' in tracking['text']
    assert status_map.state_by_name('INTERCEPT_CONFIRMED')['text'] != tracking['text']


def test_c8_all_display_texts_are_clean():
    for text in status_map.display_texts():
        for bad in status_map.FORBIDDEN_ANYWHERE:
            assert bad not in text, 'C8 违规：展示文案含 %r —— %r' % (bad, text)


def test_c8_guard_actually_fires():
    """**区分度**：守卫必须真的能拒绝坏文案，而不是恒 True 的摆设。"""
    with pytest.raises(AssertionError):
        status_map.assert_display_safe(['跟踪成功（拦截完成）'])
    with pytest.raises(AssertionError):
        # 单独构造一条非法 TRACKING_SUCCESS 文案也要被拦
        status_map.assert_display_safe([])
        bad = dict(status_map._BY_NAME)
        bad['TRACKING_SUCCESS'] = dict(bad['TRACKING_SUCCESS'], text='拦截 成功')
        old = status_map._BY_NAME
        try:
            status_map._BY_NAME = bad
            status_map.assert_display_safe([])
        finally:
            status_map._BY_NAME = old


def test_c8_wording_table_matches_plan_document():
    """文案表与 [演示可观测性与产物语义] 文档逐行一致（防止代码与文档各说各话）。

 配置文件：`docs/conventions/演示可观测性与产物语义.md` 的「状态文案表」。
 该计划文件原先在 `ADR-0032，2026-10-31 归档、2026-11-03 随归档清理删除；
 语义已迁到上述 convention（结论未变），本测试随之改指现役配置文件。
    """
    path = os.path.join(ROOT, 'docs', 'conventions', '演示可观测性与产物语义.md')
    assert os.path.exists(path), '找不到语义真源文档：%s' % path
    doc = open(path, encoding='utf-8').read()
    for _n, name, text, _audience in status_map.STATE_ROWS:
        assert '`%s`' % name in doc or name in doc, 'P1-3 文档缺状态 %s' % name
        assert text in doc, 'P1-3 文档与代码文案不一致：%r 不在文档里' % text


def test_no_intercept_completion_anywhere_in_demo_layer():
    """展示层代码里**不得**出现"拦截完成"（C8 的唯一例外是守卫自己的禁词表）。"""
    for name in P13_MODULES:
        if name == 'status_map.py':
            continue
        code = _code_only(_read(name))
        assert '拦截完成' not in code, '%s 出现 C8 禁词"拦截完成"' % name


# --------------------------------------------------------------------------------------
# 3. 面板：2 Hz + 四要素 + headless 无关
# --------------------------------------------------------------------------------------

def test_panel_refresh_rate_is_2hz():
    assert panel.REFRESH_HZ == 2.0
    assert panel.REFRESH_S == 0.5


def test_panel_box_contains_required_fields():
    box = '\n'.join(panel.render_box(FIELDS))
    for label in ('状态', '说明', '目标距离', '已用时'):
        assert label in box, '方框缺 %r：\n%s' % (label, box)
    assert 'GROUND_APPROACH' in box
    assert '地面车前往目标' in box
    assert '8.4 m' in box
    assert '01:20' in box


def test_panel_line_contains_required_fields_and_is_one_line():
    line = panel.render_line(FIELDS)
    assert '\n' not in line
    for token in ('GROUND_APPROACH', '地面车前往目标', '8.4 m', '01:20'):
        assert token in line, '单行面板缺 %r：%s' % (token, line)


def test_panel_shows_missing_target_as_absent_not_zero():
    """无目标时**不得**显示 `0.0 m`（那是假数据）。"""
    fields = dict(FIELDS, distance_m=float('nan'), obs_age_s=float('nan'))
    line = panel.render_line(fields)
    assert '0.0 m' not in line
    assert '未获得目标' in line


def test_panel_tty_redraws_at_2hz_and_throttles_lines():
    """tty：每个 0.5 s 节拍画一帧；非 tty：同一节拍只计数，按事件/心跳出单行。"""
    tty = io.StringIO()
    tty.isatty = lambda: True                     # 冒充终端
    p_tty = panel.Panel(stream=tty)
    assert p_tty.mode == 'box'
    base = 1000.0                                 # 用与真实 monotonic 同量级的基准时刻
    for i in range(5):
        assert p_tty.render(FIELDS, now=base + i * 0.5) is True
    assert p_tty.renders == 5
    # 同一节拍内再来一次：未到节拍，不画
    assert p_tty.render(FIELDS, now=base + 2.4) is False

    plain = io.StringIO()
    p_plain = panel.Panel(stream=plain)
    assert p_plain.mode == 'line'
    for i in range(10):
        p_plain.render(dict(FIELDS, elapsed_s=i * 0.5), now=base + i * 0.5)
    assert p_plain.renders == 10
    assert p_plain._lines <= 1 + 1, '非 tty 每帧刷一行会制造日志洪水（实际 %d 行）' % p_plain._lines


def test_panel_works_without_gui_dependency():
    """面板模块**不得** import 任何 rclpy / GUI / 渲染相关包（headless 与服务器场景可用）。"""
    for name in ('panel.py', 'status_map.py', 'timeline.py', 'verdict.py'):
        tree = ast.parse(_read(name))
        mods = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods.update(a.name.split('.')[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods.add(node.module.split('.')[0])
        for banned in ('rclpy', 'agc_msgs', 'PyQt5', 'tkinter', 'gz', 'rviz2'):
            assert banned not in mods, '%s 导入了 %r（面板必须与渲染/ROS 解耦）' % (name, banned)


def test_panel_persists_snapshot_file(tmp_path):
    path = str(tmp_path / 'panel.txt')
    p = panel.Panel(stream=io.StringIO(), snapshot_path=path, persist_every_s=0.0)
    p.render(FIELDS, force=True, now=1000.0)
    p.finish({'终态': 'TRACKING_SUCCESS'})
    text = open(path, encoding='utf-8').read()
    assert 'GROUND_APPROACH' in text
    assert '终态：TRACKING_SUCCESS' in text


def test_panel_erase_is_noop_for_line_mode():
    plain = panel.Panel(stream=io.StringIO())
    plain.render(FIELDS, force=True, now=1000.0)
    plain.erase()                                  # 不得抛异常
    assert plain.mode == 'line'


# --------------------------------------------------------------------------------------
# 4. 时间线：只记跳变 + 关键节点记账
# --------------------------------------------------------------------------------------

def test_timeline_records_state_changes_and_counts_nodes(tmp_path):
    path = str(tmp_path / 'timeline.txt')
    tl = timeline_mod.Timeline(path)
    tl.event('启动')
    tl.state('AIR_SEARCH', 'ok', 11.9)
    tl.state('TARGET_ACQUIRED', 'target_acquired', 11.9)
    tl.state('GROUND_APPROACH', 'ground_approach', 12.0)
    tl.state('TRACKING_SUCCESS', 'tracking_milestone', 2.3)
    tl.summary_note('terminal_state=TRACKING_SUCCESS')
    rep = tl.close()
    assert rep['key_nodes'] == 5, rep                 # 4 跳变 + 1 生命周期
    assert rep['state_nodes'] == 4
    assert rep['meets_min'] is True
    text = open(path, encoding='utf-8').read()
    assert '进入 AIR_SEARCH' in text
    assert '终态 TRACKING_SUCCESS' in text
    assert '[summary.json]' in text


def test_timeline_counts_short_runs_honestly(tmp_path):
    """节点不足 5 个时**不凑数**：如实记数并写清原因。"""
    path = str(tmp_path / 'timeline.txt')
    tl = timeline_mod.Timeline(path)
    tl.event('启动')
    tl.state('AIR_SEARCH', 'ok')
    rep = tl.close()
    assert rep['key_nodes'] == 2 and rep['meets_min'] is False
    text = open(path, encoding='utf-8').read()
    assert '关键节点：2 个' in text
    assert '不为凑数补编事件' in text


def test_timeline_notes_are_not_key_nodes(tmp_path):
    """开场参数 / 口径声明是**标注**，不是事件——不得把节点数灌到 5。"""
    tl = timeline_mod.Timeline(str(tmp_path / 'timeline.txt'))
    for i in range(6):
        tl.note('口径 %d' % i)
    rep = tl.close()
    assert rep['key_nodes'] == 0, rep


def test_timeline_stamp_format():
    assert timeline_mod.fmt_stamp(0) == '00:00.0'
    assert timeline_mod.fmt_stamp(72.43) == '01:12.4'
    assert timeline_mod.fmt_stamp(-3) == '00:00.0'


def test_timeline_summary_notes_only_read_existing_fields():
    """补充说明只翻译既有字段；字段缺失不补 0。"""
    notes = timeline_mod.summary_notes({'terminal_state': 'MISSION_FAILED',
                                        'terminal_reason_code': 'TIMEOUT'})
    joined = ' '.join(notes)
    assert 'MISSION_FAILED' in joined
    assert '0 段' not in joined and '0 拍' not in joined, '缺字段不得补 0：%s' % joined
    assert timeline_mod.summary_notes(None) == [
        '无 summary（本次未取得/未解析）——终态解释不可用，如实标注']


# --------------------------------------------------------------------------------------
# 5. 终态判定说明：指标来自 summary、阈值来自配置
# --------------------------------------------------------------------------------------

SUMMARY = {
    'terminal_state': 'TRACKING_SUCCESS', 'terminal_reason_code': 'tracking_milestone',
    'terminal_state_latched': True, 'terminal_state_source': 'first_terminal_latched',
    'duration_s': 41.86, 'duration_kind': 'process_wall_incl_warmup_shutdown',
    'sim_start_s': 9.58, 'sim_end_s': 48.46, 'rtf': 0.93,
    'ticks_total': 1185, 'ticks_triggered': 0,
    'shield_infeasible_rate': 0.0, 'reset_failure_rate': 0.0,
    'reset_retries': 0, 'reset_failed': False,
    'true_shield_infeasible': False, 'collision_count': 1,
    'collision_events': [{'t_sim': 10.652, 'other': 'apron_center::link::c'}],
    'command_attribution': {'shield_layer_enabled': True, 'intervened_ticks': 238,
                            'intervention_segments': 2, 'clearance_min_m': 4.97},
    'visibility_metrics': {'visibility_rate': 0.988, 'ticks_visible': 493,
                           'ticks_total': 499, 'window_s': 60},
}

THRESHOLDS = {'source': '/x/config/params_applied.yaml',
              'values': {'d_track_m': 3.0, 't_dwell_s': 3.0, 't_max_s': 120.0,
                         'tracking_milestone_is_terminal': True},
              'missing': ['confidence_min', 'target_max_age_s']}


def test_verdict_states_c8_wording():
    out = verdict.explain(SUMMARY, THRESHOLDS)
    text = '\n'.join(out['lines'])
    assert '抵近并持续跟踪' in text
    assert '拦截完成' not in text
    assert 'INTERCEPT_CONFIRMED' in text            # 把阶段 B 的存在讲清，避免混用


def test_verdict_metrics_come_from_summary():
    text = '\n'.join(verdict.explain(SUMMARY, THRESHOLDS)['lines'])
    for token in ('41.86', '0.988', 'reset_failure_rate', 'shield_infeasible_rate',
                  'collision_count=1', 'apron_center'):
        assert token in text, '判定说明缺 summary 字段 %r' % token


def test_verdict_thresholds_come_from_config_not_code():
    text = '\n'.join(verdict.explain(SUMMARY, THRESHOLDS)['lines'])
    assert 'd_track_m=3' in text and 't_dwell_s=3' in text
    assert 'params_applied.yaml' in text
    # 缺配置时**不得**回落到硬编码阈值
    no_th = {'source': None, 'values': {}, 'missing': list(verdict.THRESHOLD_KEYS)}
    text2 = '\n'.join(verdict.explain(SUMMARY, no_th)['lines'])
    assert '阈值来源缺失' in text2
    assert 'd_track_m=3' not in text2


def test_verdict_without_summary_is_honest():
    out = verdict.explain(None, {'source': None, 'values': {}, 'missing': []},
                          terminal_state='GROUND_APPROACH',
                          terminal_reason='ground_approach')
    text = '\n'.join(out['lines'])
    assert '未取得本 run 的 metrics/summary.json' in text
    assert '不能**作为成功证据' in text
    assert out['fields']['terminal_state'] == 'GROUND_APPROACH'


def test_verdict_flags_expectation_mismatch_but_does_not_rewrite():
    out = verdict.explain(dict(SUMMARY, terminal_state='MISSION_FAILED',
                               terminal_reason_code='TIMEOUT'),
                          THRESHOLDS, expected_terminal='TRACKING_SUCCESS')
    text = '\n'.join(out['lines'])
    assert '**不一致**' in text
    assert out['fields']['terminal_state'] == 'MISSION_FAILED'


def test_verdict_loads_thresholds_from_real_params_file(tmp_path):
    """用一份与真实 run 同构的 `params_applied.yaml` 验证解析路径（含退化扫描）。"""
    path = tmp_path / 'params_applied.yaml'
    path.write_text(
        'task_manager:\n'
        '  ros__parameters:\n'
        '    d_track_m: 2.5\n'
        '    t_dwell_s: 4.0\n'
        '    t_max_s: 90.0\n'
        '    tracking_milestone_is_terminal: true\n'
        '    other_param: 1\n'
        'run_logger:\n'
        '  ros__parameters:\n'
        '    d_track_m: 99.0\n', encoding='utf-8')
    got = verdict.load_thresholds(str(path))
    assert got['values']['d_track_m'] == 2.5, '只认 task_manager 段，不得被别的段覆盖'
    assert got['values']['t_dwell_s'] == 4.0
    assert got['values']['t_max_s'] == 90.0
    assert got['values']['tracking_milestone_is_terminal'] is True
    assert 'confidence_min' in got['missing']
    # 退化扫描（无 PyYAML）必须给出同一组值
    assert verdict._scan_flat_section(str(path), 'task_manager')['d_track_m'] == 2.5


def test_verdict_missing_config_file_is_reported(tmp_path):
    got = verdict.load_thresholds(str(tmp_path / 'nope.yaml'))
    assert got['source'] is None and got['values'] == {}
    assert set(got['missing']) == set(verdict.THRESHOLD_KEYS)


# --------------------------------------------------------------------------------------
# 6. 未新增话题 / 未改 ABI / 未新增命令者
# --------------------------------------------------------------------------------------

def test_no_new_topics_in_presentation_layer():
    """展示层只读既有 `/agc/task/state`；**不得**出现展示层自己起的任何话题订阅。"""
    allowed = {'/agc/task/state'}
    for name in P13_MODULES:
        text = _read(name)
        topics = set(re.findall(r"'(/[A-Za-z0-9_/]+)'", text))
        for topic in topics:
            assert topic in allowed or name == 'start.py', (
                '%s 出现了话题 %r —— 展示层不得新增话题' % (name, topic))
    # start.py 允许的订阅集合必须与 一致（只多不少地列清，防止偷加）
    start_text = _read('start.py')
    subs = set(re.findall(r'create_subscription\([^,]+,\s*\'([^\']+)\'', start_text))
    assert subs == {'/agc/task/state', '/clock', '/agc/gt/agc_car', '/agc/gt/intruder_uav',
                    '/agc/ground/cmd_vel', '/agc/ground/odom_valid', '/agc/air/odom'}, subs


def test_presentation_modules_never_publish():
    for name in P13_MODULES:
        code = _code_only(_read(name))
        assert 'create_publisher' not in code, '%s 建了发布者 —— 展示层不得发布' % name
        assert 'create_service' not in code, '%s 建了服务 —— 展示层不得新增命令者' % name


def test_msg_abi_untouched():
    """9 消息 ABI 的字段与顺序不得变更：核对 `AgcTaskState.msg` 的字段序。"""
    msg = open(os.path.join(ROOT, 'src', 'agc_msgs', 'msg', 'AgcTaskState.msg'),
               encoding='utf-8').read()
    # 只取**字段声明行**：`<type> <name> [# 注释]`，且排除 `uint8 IDLE=0` 这类常量行
    fields = [m.group(1) for m in re.finditer(
        r'^(?:std_msgs/Header|uint8|string|float32|bool)\s+(\w+)(?:\s+#.*)?$', msg, re.M)]
    assert fields == ['header', 'state', 'state_name', 'reason_code', 'air_controller',
                      'ground_controller', 'target_id', 'target_xy_distance_m',
                      'target_obs_age_s', 'tracking_milestone_met'], fields


def test_display_layer_reads_only_documented_state_fields():
    """面板只读 `AgcTaskState` 的既有字段（读新字段就是改契约的前兆）。"""
    text = _read('start.py')
    used = set(re.findall(r'\bm\.(\w+)', text))
    allowed = {'state', 'state_name', 'reason_code', 'target_xy_distance_m',
               'target_obs_age_s', 'air_controller', 'ground_controller',
               'tracking_milestone_met', 'header', 'data'}
    unknown = {u for u in used if u not in allowed and not u.startswith('clock')}
    assert not unknown, '面板读了未在契约里登记的字段：%s' % sorted(unknown)


# --------------------------------------------------------------------------------------
# 7. 接线与默认口径（不回归 的既有约束）
# --------------------------------------------------------------------------------------

def test_start_wires_all_three_presentation_artifacts():
    text = _read('start.py')
    for artifact in ('timeline.txt', 'panel.txt', 'terminal_explanation.txt'):
        assert artifact in text, 'start.py 未落盘 %s' % artifact


def test_terminal_set_is_single_sourced():
    """`TERMINALS` 只能来自 `status_map`（P1-3 收敛了 start.py 里的第二份副本）。"""
    text = _read('start.py')
    assert 'TERMINALS = status_map.TERMINAL_NAMES' in text
    assert not re.search(r'^TERMINALS\s*=\s*\{', text, re.M)


def test_default_arm_unchanged_and_annotated():
    """默认演示口径仍是 full + yard + s04；指向臂由场景覆盖（track），不经 launch 参数。"""
    import common
    import start as demo_start
    # 2026-11-04：指向臂如实反映**场景覆盖值** `track`（原写 target 与实际生效值不符）
    assert (common.DEFAULT_BACKEND, common.DEFAULT_MAP, common.DEFAULT_SCENE,
            common.DEFAULT_OBSERVE_YAW_MODE) == (
        'full', 'yard', 's04_static_static_obs_track', 'track')
    joined = ' '.join(demo_start.launch_argv(backend=common.DEFAULT_BACKEND,
                                             scene=common.DEFAULT_SCENE,
                                             world_map=common.DEFAULT_MAP, headless=False))
    assert 'observe_yaw_mode:=' not in joined, (
        '该 launch 参数已清退，不得再传（会被静默忽略）')
    assert 'oracle' in _read('start.py') or '指向臂' in _read('start.py')


# --------------------------------------------------------------------------------------
# 8. 呈现层不得成为单点故障（ 实测教训的回归）
# --------------------------------------------------------------------------------------

def test_presentation_failure_degrades_instead_of_killing_the_run():
    """面板 / 时间线抛异常时，跟随循环**必须**继续（只记 `presentation_errors`）。

    round-1 实测缺陷：`Timeline.state() got an unexpected keyword argument 'at'` 冒到
    `run()` 之外 → 监督进程崩溃、仿真进程组仍在跑，一场真实实验白跑。
    """
    import start as demo_start
    import types

    calls = {'paint': 0}

    class Boom:
        def state(self, *a, **k):
            raise TypeError("Timeline.state() got an unexpected keyword argument 'at'")

        def event(self, *a, **k):
            raise RuntimeError('timeline boom')

        def close(self, **k):
            raise RuntimeError('close boom')

    class CountingPanel:
        def render(self, *a, **k):
            calls['paint'] += 1
            return True

        def erase(self):
            pass

        def finish(self, **k):
            return {'renders': calls['paint']}

    run = demo_start.DemoRun.__new__(demo_start.DemoRun)
    run.result = {}
    run.progress = None
    run.monitor = None
    run.panel = CountingPanel()
    run.timeline = Boom()
    run._disabled = set()
    run.opts = {'headless': True}

    # 1) 时间线炸了 → 记账并返回 None，调用方照常继续
    assert run._safe('timeline', lambda: run.timeline.state('AIR_SEARCH')) is None
    assert run.result['presentation_errors'][0]['component'] == 'timeline'
    # 2) 同一组件只在**首次**降级时提示一次（不刷屏）
    run._safe('timeline', lambda: run.timeline.state('AIR_SEARCH'))
    assert len(run.result['presentation_errors']) == 2
    # 3) 面板仍在正常渲染（互不牵连）
    assert run._paint(force=True) is True
    assert calls['paint'] == 1


def test_timeline_state_accepts_at_kwarg(tmp_path):
    """`Timeline.state(..., at=...)` 是跟随循环的调用形态，签名必须支持。"""
    tl = timeline_mod.Timeline(str(tmp_path / 'timeline.txt'))
    line = tl.state('AIR_SEARCH', 'ok', 11.9, at=3.2)
    assert '[00:03.2]' in line
    tl.close()
