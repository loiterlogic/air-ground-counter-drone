#!/usr/bin/env python3
"""离线单测：基线收尾的两处修复（T0，不启 ROS / 不启仿真）。

断言的是"两个**已定位**的脆弱点不再存在"，不是"跑起来看着对"：

 1. **预热进程必须有确定上界，且上界必须能兑现**：`main.launch.py` 的 prewarm 命令必须是
 `timeout -k <K> <N> …`。**只给 `timeout <N>` 不够**——GNU `timeout` 到点只发 SIGTERM
 然后无限期等子进程； T-B 的失败形态正是该进程 SIGINT 5 s / SIGTERM 10 s 都不退，
 只能 SIGKILL。此时 `timeout` 自身永不返回 → `OnProcessExit` 依旧不触发 → 修复等于没做。
 2. **采集器必须边采边写 + 中断安全**：`track_err_probe.py` 要有周期 flush（**json/samples/txt
 三者全写**，被 SIGKILL 也不留悬空）、SIGINT/SIGTERM handler，且**先写最终结果再 destroy_node**。
 3. **0 样本不得当 0 误差**：采集器在无配对样本时退出码 3，产物标 `NO_SAMPLES`。
 4. **误差口径必须是生效参考**：主指标用 `tracking_ref`（生效参考），标称 8 字只作连续性对照；
 否则量出来的是 standoff 偏置而不是跟踪误差（ 的 mean≈8 m / p95≈18 m 就是证据）。
 5. **不改控制链/ABI**：w6 的修复只动 prewarm 命令，不改任务参数、终态、、安全阈值。
"""

import ast
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
W6 = REPO / 'src' / 'agc_task' / 'launch' / 'main.launch.py'
PROBE = REPO / 'scripts' / 'tracking' / 'track_err_probe.py'

FROZEN_9 = {
    'AgcTaskState', 'AirObservationArray', 'ObstacleObservation', 'ObstacleTrack',
    'ObstacleTrackArray', 'SensorObservation', 'TargetObservation', 'TargetTrack',
    'TargetTrackArray',
}


def _text(p):
    return p.read_text(encoding='utf-8')


# --------------------------------------------------------------------------------------
# 1. 预热进程上界（竞态修复）
# --------------------------------------------------------------------------------------

def _prewarm_cmd():
    """解析出 prewarm ExecuteProcess 的 cmd 源码片段（解析失败即让测试显式失败）。"""
    m = re.search(r'prewarm = ExecuteProcess\(\s*cmd=\[(.*?)\]', _text(W6), re.S)
    assert m, '未找到 prewarm ExecuteProcess（解析失效会让本测试永远通过）'
    return m.group(1)


def test_prewarm_has_hard_timeout():
    """prewarm 必须被 `timeout` 包住 —— 单事件依赖的唯一解药。"""
    assert _prewarm_cmd().strip().startswith("'timeout'"), (
        'prewarm 未加 timeout —— OnProcessExit 可能永不触发（round-5 T-B 失败形态）')
    m2 = re.search(r'prewarm_timeout_s\s*=\s*(\d+)', _text(W6))
    assert m2, '缺少 prewarm_timeout_s 常量'
    assert 0 < int(m2.group(1)) < 180, 'prewarm 超时必须 < run_demo 就绪门 180 s'


def test_prewarm_timeout_has_kill_after():
    """**关键**：`timeout` 必须带 `-k`。只给时长的 `timeout N` 在子进程忽略 SIGTERM 时
    自己永不返回（T1 实测：外层 -k 8 在 10 s 才杀掉它），`OnProcessExit` 仍不触发。"""
    cmd = _prewarm_cmd()
    assert "'-k'" in cmd, (
        'prewarm 的 timeout 缺少 -k —— 子进程忽略 SIGTERM 时 timeout 自身永不返回，'
        'OnProcessExit 依旧不触发（round-5 T-B 正是 SIGTERM 10 s 不退）')
    m = re.search(r'prewarm_kill_after_s\s*=\s*(\d+)', _text(W6))
    assert m, '缺少 prewarm_kill_after_s 常量'
    kill_after = int(m.group(1))
    timeout_s = int(re.search(r'prewarm_timeout_s\s*=\s*(\d+)', _text(W6)).group(1))
    assert 0 < kill_after, 'kill-after 必须为正'
    # 真实上界 = timeout + kill_after，必须仍落在 run_demo 的 180 s 就绪门内
    assert timeout_s + kill_after < 180, (
        'prewarm 真实上界 %d+%d=%d 必须 < 180 s 就绪门'
        % (timeout_s, kill_after, timeout_s + kill_after))


def test_prewarm_event_handler_still_present():
    """修复后仍必须保留 OnProcessExit → lifecycle_manager 的触发关系。"""
    text = _text(W6)
    assert 'OnProcessExit(' in text
    assert 'target_action=prewarm' in text
    assert 'on_exit=[lifecycle_manager]' in text


def test_w6_still_has_lifecycle_manager_with_bond_timeout():
    """R-034/ADR-0019：bond_timeout 不得被置 0（回归保护）。"""
    text = _text(W6)
    assert "'bond_timeout': 5.0" in text
    assert re.search(r"bond_timeout'?\s*:\s*0(\.0+)?\b", text) is None


def test_w6_fix_does_not_touch_task_params():
    """修复只动 prewarm 命令；不得改任务/终态/安全参数（派工单红线）。"""
    text = _text(W6)
    assert 'declare_parameter' not in text, 'w6 是 launch，不该有 declare_parameter'
    # 控制链节点列表不变
    assert ("('px4_adapter', 'takeoff_controller', 'trajectory_tracker', 'standoff_follower')"
            in text)


# --------------------------------------------------------------------------------------
# 2. 采集器：边采边写 + 中断安全 + 先写后销毁
# --------------------------------------------------------------------------------------

def test_probe_flushes_periodically():
    text = _text(PROBE)
    assert '--flush-period' in text
    assert 'last_flush' in text
    assert '_write(' in text
    # 周期写入必须在采样主循环内（不是只在收尾写一次）
    loop = text.split('while not node.stop_requested:', 1)
    assert len(loop) == 2, '缺少采样主循环（解析失效会让本测试永远通过）'
    assert '_write(' in loop[1].split('# 收尾')[0], '周期 flush 必须在主循环内'


def test_probe_writes_all_three_artifacts_each_flush():
    """json / samples / txt **每次 flush 都全写** —— 被 SIGKILL 也不留"只有空 json"的悬空产物。"""
    body = _text(PROBE).split('def _write(', 1)
    assert len(body) == 2, '缺少 _write 定义'
    seg = body[1].split('\ndef ', 1)[0]
    for name in ('track_err.json', 'track_err.samples', 'track_err.txt'):
        assert name in seg, '_write 未落 %s（每周期全量重写才能中断安全）' % name


def test_probe_handles_signals():
    text = _text(PROBE)
    assert 'signal.SIGINT' in text and 'signal.SIGTERM' in text
    assert 'stop_requested' in text


def test_probe_writes_final_before_destroying_node():
    """顺序关键：**先落最终结果，再 destroy_node**（round-5 反了 → 0 输出）。"""
    tail = _text(PROBE).split('# 收尾', 1)
    assert len(tail) == 2, '缺少收尾段'
    seg = tail[1]
    assert seg.index('_write(') < seg.index('node.destroy_node()'), (
        '必须先 _write 再 destroy_node')


def test_probe_exit_code_3_on_no_samples():
    """0 样本不得当 0 误差 —— 退出码 3 + 产物显式 NO_SAMPLES。"""
    text = _text(PROBE)
    assert 'return 0 if node.samples else 3' in text
    assert 'NO_SAMPLES' in text
    assert '不得当作 0' in text


def test_probe_marks_metric_as_not_a_summary_field():
    text = _text(PROBE)
    assert 'not_a_summary_field' in text
    assert '不是契约 C1' in text


def test_probe_uses_atomic_write():
    """原子写（.tmp + replace），避免中断留下半截 JSON。"""
    assert 'os.replace(' in _text(PROBE)


def test_probe_does_not_read_ground_truth():
    """红线：跟踪误差采集器不得读 /agc/gt（那是评估标签，不是 ref）。"""
    tree = ast.parse(_text(PROBE))
    live = {n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    offenders = [s for s in live if '/agc/gt' in s and 'not' not in s.lower()]
    assert not offenders, offenders


# --------------------------------------------------------------------------------------
# 3. 误差口径：主指标必须是生效参考（tracking_ref），不是标称 8 字
# --------------------------------------------------------------------------------------

def test_probe_primary_metric_uses_tracking_ref():
    """主指标必须优先用 `tracking_ref`（生效参考）；标称 8 字只作连续性对照。

 依据 `trajectory_tracker.cpp` ⑨ 的 source 裁定：tracking/hold → tracking_ref；base → base_ref。
 只订 `/agc/air/ref`，量出的 mean≈8 m / p95≈18 m 是 standoff 偏置，不是跟踪误差。
    """
    text = _text(PROBE)
    assert '--tracking-topic' in text
    assert "'/agc/air/tracking_ref'" in text
    assert 'err_eff_xy_m' in text and 'err_base_xy_m' in text
    seg = text.split('def pair_one(', 1)
    assert len(seg) == 2, '缺少 pair_one'
    body = seg[1].split('\ndef ', 1)[0]
    # 判**定**顺序：先 `if tref_xy is not None → 'tracking'`，再退回 `'base'`
    i_track = body.index("'tracking'")
    i_base = body.index("'base'")
    assert i_track < i_base, 'pair_one 必须先判 tracking_ref 再退回 base_ref'
    assert 'if tref_xy is not None' in body, '缺少"tracking_ref 新鲜即用"的判定'


def test_probe_declares_base_metric_is_not_tracking_error():
    """口径诚实性：标称 8 字那条必须显式标注"含 standoff 偏置、非跟踪误差"。"""
    text = _text(PROBE)
    assert 'standoff' in text
    assert '非跟踪误差' in text


# --------------------------------------------------------------------------------------
# 3b. 采集器的**纯函数行为**（真跑，不是读源码）
#
# 教训： 臂 A 的采集器在真实运行里抛 `TypeError: dict is not a sequence` ——
# `pair_one` 被传了 dict 却按序列用。**只读源码的守卫抓不到这种错**，故这里直接导入并调用。
# --------------------------------------------------------------------------------------

def _probe_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location('track_err_probe_mod', PROBE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_pair_one_prefers_tracking_ref_then_falls_back_to_base():
    """生效参考口径：tracking_ref 在配对窗内 → 'tracking'；超窗 → 退回 'base'。"""
    m = _probe_module()
    refs = {1000: (0.0, 0.0)}
    trefs = {1000 + 80_000_000: (5.0, 0.0)}   # tracking_ref 晚 80 ms
    rk, tk = sorted(refs), sorted(trefs)
    odom = (0.0, 0.0)
    # 40 ms 窗：tracking_ref 超窗 → 退回 base_ref（err_eff == err_base == 0）
    eff, base, mode = m.pair_one(1000, odom, refs, trefs, rk, tk, 40_000_000)
    assert mode == 'base' and eff == 0.0 and base == 0.0
    # 100 ms 窗：tracking_ref 入窗 → 生效参考是它（err_eff=5，err_base 仍为 0）
    eff, base, mode = m.pair_one(1000, odom, refs, trefs, rk, tk, 100_000_000)
    assert mode == 'tracking' and eff == 5.0 and base == 0.0


def test_pair_one_returns_none_when_no_reference_in_window():
    """无参考在窗内 → err_eff None（**不得**当作 0）。"""
    m = _probe_module()
    eff, base, mode = m.pair_one(10 ** 12, (0.0, 0.0), {1000: (1.0, 1.0)}, {}, [1000], [],
                                 40_000_000)
    assert eff is None and mode is None


def test_aggregate_empty_is_none_not_zero():
    """空样本聚合必须返回 None（`0.0` 会被读成"误差为零"）。"""
    assert _probe_module().aggregate([]) is None


def test_probe_pair_accepts_mapping_and_key_list():
    """`pair_one` 的签名必须显式收 (refs, trefs, ref_keys, tref_keys) —— 这条正是
    臂 A 崩溃的回归点（传 dict 当序列）。"""
    import inspect
    params = list(inspect.signature(_probe_module().pair_one).parameters)
    assert params == ['ts', 'odom_xy', 'refs', 'trefs', 'ref_keys', 'tref_keys',
                      'max_dt_ns'], params


# --------------------------------------------------------------------------------------
# 4. ABI 防回归（两个修复都不许碰消息）
# --------------------------------------------------------------------------------------

def test_nine_messages_still_frozen():
    msgs = sorted(p.stem for p in (REPO / 'src' / 'agc_msgs' / 'msg').glob('*.msg'))
    assert set(msgs) == FROZEN_9, sorted(set(msgs) ^ FROZEN_9)


# --------------------------------------------------------------------------------------
# 5. 自检：解析器有效性（防"空断言永远通过"）
# --------------------------------------------------------------------------------------

def test_parsers_are_effective():
    """反向验证：故意构造缺失 timeout / 缺 -k 的片段，确认检测逻辑会失败。"""
    fake = "prewarm = ExecuteProcess(\n    cmd=[prewarm_bin, 'a'],\n    output='screen')"
    m = re.search(r'prewarm = ExecuteProcess\(\s*cmd=\[(.*?)\]', fake, re.S)
    assert m and not m.group(1).strip().startswith("'timeout'"), (
        '检测逻辑对"无 timeout"的片段应判失败（若这里通过，说明解析器退化了）')
    fake2 = "prewarm = ExecuteProcess(\n    cmd=['timeout', '45', 'x'],\n)"
    m2 = re.search(r'prewarm = ExecuteProcess\(\s*cmd=\[(.*?)\]', fake2, re.S)
    assert m2 and "'-k'" not in m2.group(1), (
        '检测逻辑对"timeout 无 -k"的片段应判失败（那正是永不返回的形态）')


@pytest.mark.parametrize('path', [W6, PROBE])
def test_files_compile(path):
    compile(_text(path), str(path), 'exec')
