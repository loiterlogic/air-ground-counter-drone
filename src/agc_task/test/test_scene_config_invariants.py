"""场景配置不变量（ADR-0076）——纯配置层测试，不启仿真。

守护的 bug 类别：**配置自相矛盾导致结局永不可达**。
实例：`capture_adjudicator.interception_authorized: true`（授权开火）但
`task_manager.tracking_milestone_is_terminal` 仍为 `true` → 跟踪里程碑先进终态，
交火窗口（GROUND_APPROACH）被关闭 → `INTERCEPT_CONFIRMED/CAPTURE_NET` **永不发生**
（实测 s08 协同臂 20/20 落 `TRACKING_SUCCESS`、`pass=false`）。

测试对象是真源文件（`config/scenarios.yaml` + `config/w6_base.yaml`），
与 `w6.launch.py` 的 `assertions()` 共用同一判据（此处做**全场景**静态扫描，
启动时只校验当前场景）。
"""

import os

import pytest
import yaml

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'config')


def _load():
    with open(os.path.join(CONFIG_DIR, 'scenarios.yaml')) as f:
        scenarios = yaml.safe_load(f)['scenes']   # 真源根键为 `scenes`
    with open(os.path.join(CONFIG_DIR, 'w6_base.yaml')) as f:
        base = yaml.safe_load(f)
    return scenarios, base


def _param(scenarios, base, scene, node, key, default):
    """按「基参 → 场景覆盖」解析实际生效值（与 launch 的合并口径一致）。"""
    value = (base.get(node, {}).get('ros__parameters', {}) or {}).get(key, default)
    override = ((scenarios.get(scene, {}).get('params') or {}).get(node) or {}).get(key, value)
    return override


def test_capture_authorized_scenes_disable_milestone_terminal():
    """所有授权射击的场景，必须显式关闭「里程碑即终态」。"""
    scenarios, base = _load()
    checked = []
    for scene in scenarios:
        authorized = bool(_param(scenarios, base, scene, 'capture_adjudicator',
                                 'interception_authorized', False))
        if not authorized:
            continue
        terminal = bool(_param(scenarios, base, scene, 'task_manager',
                               'tracking_milestone_is_terminal', True))
        assert not terminal, (
            '场景 %s 已授权射击（interception_authorized=true）但 tracking_milestone_is_terminal=true '
            '→ 捕获结局不可达（ADR-0076）' % scene)
        checked.append(scene)
    # 真源里应至少有一个已授权场景（s08）；退化保护：若该轴被误删，测试应失败而非静默通过。
    assert checked, '未找到任何 interception_authorized=true 的场景——场景真源可能被误改（ADR-0076）'


def test_base_default_keeps_existing_behavior():
    """基参必须保持 `true`（既有行为不变）；capture 场景在**场景层**覆盖。"""
    _, base = _load()
    assert base['task_manager']['ros__parameters']['tracking_milestone_is_terminal'] is True


def test_non_capture_scenes_unaffected():
    """非授权场景不得被本次修正波及（否则会破坏既有 W6 回归）。"""
    scenarios, base = _load()
    affected = [
        scene for scene in scenarios
        if not bool(_param(scenarios, base, scene, 'capture_adjudicator',
                           'interception_authorized', False))
        and not bool(_param(scenarios, base, scene, 'task_manager',
                            'tracking_milestone_is_terminal', True))
    ]
    assert affected == [], (
        '以下非授权场景被关闭了里程碑终态（非预期，会改变既有行为）：%s' % affected)


def test_spawn_layout_reaches_tracking_range():
    """F1（2026-10-31）：固定任务目标必须落在目标的 `d_track` 可达范围内。

    守护的 bug 类别：**出生布局改了、任务目标没跟上** → C8 的"车↔目标 ≤ d_track"永远不成立
    → GROUND_APPROACH 的有效拍永不出现 → 终态只能 TIMEOUT（主场景"跟踪成功"变成不可达）。
    判据对**每个 `goal_follow_target=false` 且期望终态为 `TRACKING_SUCCESS`** 的场景逐条检查：
      `dist(固定任务目标, 目标出生位) ≤ d_track`

    排除两类（它们的不达成功是**设计意图**，不是缺陷）：
      * `expected_terminal: MISSION_FAILED`（s10 目标置远 → 必然超时；s11 被立柱阻隔 → 不可达）；
      * `goal_follow_target: true`（任务目标由感知目标位实时决定，不存在固定点）；
      * `capture` 场景（自带配套 goal 与 `target_x/y`，关系由各自用例覆盖）。
    旧布局实测基线 2.55 m / d_track 3.0 m，故本判据在当时即成立，不是新放宽。
    """
    import math

    scenarios, base = _load()
    layout_path = os.path.join(CONFIG_DIR, 'spawn_layout.yaml')
    with open(layout_path) as f:
        layout = yaml.safe_load(f)['spawn_layout']
    base_tm = base['task_manager']['ros__parameters']
    d_track = float(base_tm.get('d_track_m', 3.0))
    base_gx = float(base_tm['goal_x'])
    base_gy = float(base_tm['goal_y'])

    checked = []
    violations = []
    for scene in scenarios:
        sc = scenarios.get(scene, {})
        params = sc.get('params') or {}
        tm = params.get('task_manager') or {}
        sr = params.get('scenario_reset') or {}
        # 设计上不追求 TRACKING_SUCCESS 的场景：不按本规则判（见 docstring）。
        if str(sc.get('expected_terminal')) != 'TRACKING_SUCCESS':
            continue
        if bool((params.get('capture_adjudicator') or {}).get('interception_authorized', False)):
            continue
        follow = bool(tm.get('goal_follow_target', base_tm.get('goal_follow_target', False)))
        if follow:
            continue
        # 出生位：场景覆盖优先，否则布局真源（与 apply_spawn_layout 同口径）。
        tx = float(sr.get('target_x', layout['target']['x']))
        ty = float(sr.get('target_y', layout['target']['y']))
        gx = float(tm.get('goal_x', base_gx))
        gy = float(tm.get('goal_y', base_gy))
        dist = math.hypot(gx - tx, gy - ty)
        checked.append(scene)
        if dist > d_track:
            violations.append('%s: goal=(%g,%g) target=(%g,%g) d=%.2f > d_track=%.2f'
                              % (scene, gx, gy, tx, ty, dist, d_track))
    assert not violations, (
        '固定任务目标离目标出生位过远 → C8「车↔目标 ≤ d_track」不可达，跟踪终态永不可能：\n  '
        + '\n  '.join(violations))
    # 退化保护：本规则至少覆盖到默认演示场景 s04，否则说明判据被架空了。
    assert 's04_static_static_obs_track' in checked, (
        's04 未被本判据覆盖（其 goal_follow_target / capture 设置可能被误改）：checked=%s' % checked)


def test_s04_spawn_comes_from_layout():
    """F1：默认演示场景 **不得**再覆盖出生位（否则改了布局、演示仍跑旧坐标）。"""
    scenarios, _ = _load()
    s04 = scenarios['s04_static_static_obs_track']
    overrides = ((s04.get('params') or {}).get('scenario_reset') or {})
    spawn_keys = {'car_x', 'car_y', 'target_x', 'target_y'}
    leaked = spawn_keys & set(overrides)
    assert not leaked, (
        's04 仍覆盖出生位 %s → 布局真源（spawn_layout.yaml）对它不生效' % sorted(leaked))


if __name__ == '__main__':
    raise SystemExit(pytest.main([os.path.realpath(__file__)]))


# ------------------------------------------------------------------------------
# F1 round-2：出生布局真源的非有限值 / 非法值守卫
# ------------------------------------------------------------------------------
def _layout_with(monkeypatch_tmp, mutate):
    """把真源复制到临时目录并按 `mutate` 改写，返回该临时文件的路径。"""
    import tempfile
    with open(os.path.join(CONFIG_DIR, 'spawn_layout.yaml')) as f:
        doc = yaml.safe_load(f)
    mutate(doc['spawn_layout'])
    fd, path = tempfile.mkstemp(suffix='.yaml')
    os.close(fd)
    with open(path, 'w') as f:
        yaml.safe_dump(doc, f, allow_unicode=True, sort_keys=True)
    return path


def _load_spawn_layout_from(path):
    import importlib.util
    launch_dir = os.path.join(os.path.dirname(CONFIG_DIR), 'launch')
    spec = importlib.util.spec_from_file_location(
        'w6_composition_for_test', os.path.join(launch_dir, 'w6_composition.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.load_spawn_layout(os.path.dirname(CONFIG_DIR), path=path)


@pytest.mark.parametrize('bad', [float('nan'), float('inf'), float('-inf'), 'nan', 'inf'])
def test_spawn_layout_rejects_non_finite(bad, tmp_path):
    """NaN / ±Inf 必须**拒绝运行**——否则区间比较恒假，越界与净空拒绝分支会静默失效。

    `float('nan')` / `float('inf')` 都能通过 `float()` 转换，所以只查 `float()` 是不够的。
    这里覆盖两种来源：① Python 侧已是 NaN/Inf 的浮点（经 `float()` 通过、须由 `isfinite` 拦）；
    ② 文本形式 `'nan'` / `'inf'`（`float()` 同样通过）。两者都必须拒绝。
    """
    def mutate(layout):
        layout['car']['x'] = bad

    path = _layout_with(tmp_path, mutate)
    with pytest.raises(RuntimeError) as exc:
        _load_spawn_layout_from(path)
    assert '非有限值' in str(exc.value)
    assert 'car.x' in str(exc.value)


@pytest.mark.parametrize('bad', ['.nan', '.inf', '-.inf', 'NaN', 'Infinity'])
def test_spawn_layout_rejects_non_numeric_text(bad, tmp_path):
    """YAML 风格 / 大小写变体同样拒绝（`float()` 直接抛 ValueError 的那一类）。

    两条路径的错误信息不同（"非数值" vs "非有限值"），但**都必须拒绝**——
    判据是"启动前挡住"，不是"用哪条分支挡住"。
    """
    def mutate(layout):
        layout['car']['x'] = bad

    path = _layout_with(tmp_path, mutate)
    with pytest.raises(RuntimeError) as exc:
        _load_spawn_layout_from(path)
    assert 'car.x' in str(exc.value)
    assert ('非有限值' in str(exc.value)) or ('非数值' in str(exc.value))


def test_spawn_layout_rejects_non_numeric(tmp_path):
    """非数值（字符串 / None）同样拒绝，且错误信息点明是哪一字段。"""
    def mutate(layout):
        layout['target']['y'] = 'east'

    path = _layout_with(tmp_path, mutate)
    with pytest.raises(RuntimeError) as exc:
        _load_spawn_layout_from(path)
    assert 'target.y' in str(exc.value)


def test_spawn_layout_goal_offset_rejects_non_finite(tmp_path):
    """派生偏移也必须是有限值（它直接决定固定任务目标位）。"""
    def mutate(layout):
        layout['goal_offset_m'] = {'dx': float('nan'), 'dy': 0.0}

    path = _layout_with(tmp_path, mutate)
    with pytest.raises(RuntimeError) as exc:
        _load_spawn_layout_from(path)
    assert 'goal_offset_m.dx' in str(exc.value)


def test_goal_derived_from_target_and_offset():
    """默认场景的任务目标 = 目标出生位 + goal_offset_m；改 target 时 goal 自动跟随。

    守护的 bug 类别：goal 是**第二处**关联坐标，改了 target 忘改 goal → C8 的
    「车↔目标 ≤ d_track」永不成立 → 跟踪终态不可达。
    """
    import importlib.util

    with open(os.path.join(CONFIG_DIR, 'spawn_layout.yaml')) as f:
        layout = yaml.safe_load(f)['spawn_layout']
    off = layout['goal_offset_m']
    launch_dir = os.path.join(os.path.dirname(CONFIG_DIR), 'launch')
    spec = importlib.util.spec_from_file_location(
        'w6_composition_for_goal', os.path.join(launch_dir, 'w6_composition.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    full = mod.load_spawn_layout(os.path.dirname(CONFIG_DIR))
    # 默认场景（无 goal 覆盖、goal_follow_target=false、无 target 覆盖）
    merged = {'task_manager': {'goal_follow_target': False}}
    eff = mod.apply_spawn_layout(merged, full, {})
    assert eff['goal_source'] == 'derived'
    assert eff['goal_x'] == pytest.approx(full['target']['x'] + off['dx'])
    assert eff['goal_y'] == pytest.approx(full['target']['y'] + off['dy'])
    # 改 target → goal 必须跟着走（同一规则，不需手工同步）
    moved = dict(full)
    moved['target'] = dict(full['target'], x=full['target']['x'] - 3.0)
    merged2 = {'task_manager': {'goal_follow_target': False}}
    eff2 = mod.apply_spawn_layout(merged2, moved, {})
    assert eff2['goal_x'] == pytest.approx(moved['target']['x'] + off['dx'])
    assert eff2['goal_x'] != eff['goal_x']
