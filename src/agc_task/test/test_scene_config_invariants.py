"""场景配置不变量（ADR-0014）——纯配置层测试，不启仿真。

守护的 bug 类别：**配置自相矛盾导致结局永不可达**。
实例：`capture_adjudicator.interception_authorized: true`（授权开火）但
`task_manager.tracking_milestone_is_terminal` 仍为 `true` → 跟踪里程碑先进终态，
交火窗口（GROUND_APPROACH）被关闭 → `INTERCEPT_CONFIRMED/CAPTURE_NET` **永不发生**
（实测 s08 协同臂 20/20 落 `TRACKING_SUCCESS`、`pass=false`）。

测试对象是配置文件文件（`config/scenarios.yaml` + `config/base.yaml`），
与 `main.launch.py` 的 `assertions()` 共用同一判据（此处做**全场景**静态扫描，
启动时只校验当前场景）。
"""

import os

import pytest
import yaml

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'config')


def _load():
    with open(os.path.join(CONFIG_DIR, 'scenarios.yaml')) as f:
        scenarios = yaml.safe_load(f)['scenes']   # 根键为 `scenes`
    with open(os.path.join(CONFIG_DIR, 'base.yaml')) as f:
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
            '→ 捕获结局不可达（ADR-0014）' % scene)
        checked.append(scene)
    # 配置文件里应至少有一个已授权场景（s08）；退化保护：若该轴被误删，测试应失败而非静默通过。
    assert checked, '未找到任何 interception_authorized=true 的场景——场景配置可能被误改（ADR-0014）'


def test_base_default_keeps_existing_behavior():
    """基参必须保持 `true`（既有行为不变）；capture 场景在**场景层**覆盖。"""
    _, base = _load()
    assert base['task_manager']['ros__parameters']['tracking_milestone_is_terminal'] is True


def test_non_capture_scenes_unaffected():
    """非授权场景不得被本次修正波及（否则会破坏既有回归）。"""
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

 守护的 bug 类别：**出生布局改了、任务目标没跟上** → 的"车↔目标 ≤ d_track"永远不成立
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
        # 出生位：场景覆盖优先，否则布局配置文件（与 apply_spawn_layout 同口径）。
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
        '固定任务目标离目标出生位过远 → 「车↔目标 ≤ d_track」不可达，跟踪终态永不可能：\n  '
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
        's04 仍覆盖出生位 %s → 布局文件（spawn_layout.yaml）对它不生效' % sorted(leaked))


if __name__ == '__main__':
    raise SystemExit(pytest.main([os.path.realpath(__file__)]))


# ------------------------------------------------------------------------------
# F1 ：出生布局配置文件的非有限值 / 非法值守卫
# ------------------------------------------------------------------------------
def _layout_with(monkeypatch_tmp, mutate):
    """把布局文件复制到临时目录并按 `mutate` 改写，返回该临时文件的路径。"""
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
        'composition_for_test', os.path.join(launch_dir, 'composition.py'))
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

 守护的 bug 类别：goal 是**第二处**关联坐标，改了 target 忘改 goal → 的
 「车↔目标 ≤ d_track」永不成立 → 跟踪终态不可达。
    """
    import importlib.util

    with open(os.path.join(CONFIG_DIR, 'spawn_layout.yaml')) as f:
        layout = yaml.safe_load(f)['spawn_layout']
    off = layout['goal_offset_m']
    launch_dir = os.path.join(os.path.dirname(CONFIG_DIR), 'launch')
    spec = importlib.util.spec_from_file_location(
        'composition_for_goal', os.path.join(launch_dir, 'composition.py'))
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


# ------------------------------------------------------------------------------
# H0（2026-11-02）：目标巡航高度**单一有效来源**
# ------------------------------------------------------------------------------
def _composition_module(tag='h0'):
    import importlib.util
    launch_dir = os.path.join(os.path.dirname(CONFIG_DIR), 'launch')
    spec = importlib.util.spec_from_file_location(
        'composition_for_%s' % tag, os.path.join(launch_dir, 'composition.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _merged_for(scene):
    """按 launch 的合并口径（base → 场景覆盖）算出某场景的实际生效参数。"""
    scenarios, base = _load()
    merged = {n: dict(sec.get('ros__parameters', {})) for n, sec in base.items()}
    for node, over in ((scenarios[scene].get('params') or {})).items():
        merged.setdefault(node, {}).update(over)
    return merged, scenarios[scene]


# ------------------------------------------------------------------------------
# ADR-0007（2026-11-02）：高度随地图派生——测试侧的最小几何/场景解析辅助
# ------------------------------------------------------------------------------
# CONFIG_DIR = <root>/src/agc_task/config → 上溯三级 = <root>
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(CONFIG_DIR)))
SIM_CONFIG_DIR = os.path.join(_ROOT, 'src', 'agc_sim', 'config')


def _geometry_file(world_map):
    """地图名 → 几何来源文件（**只经 `world_map.MAP_GEOMETRY_FILES`**，不另建第二份表）。"""
    import importlib.util
    path = os.path.join(_ROOT, 'src', 'agc_sim', 'launch', 'world_map.py')
    spec = importlib.util.spec_from_file_location('wm_for_tests', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return os.path.join(SIM_CONFIG_DIR, mod.MAP_GEOMETRY_FILES[world_map])


def _world_maps():
    """全部已登记地图名 —— 取自 `world_map.WORLD_MAPS` 单一清单。

 ADR-0036（2026-11-10）：本文件此前两处写死 `('minimal','yard','open_field')`，
 新地图（`dense_map`）因此**不受这些不变量守护** —— 一个"加了图但没被任何断言覆盖"
 的静默缺口。改为遍历清单后，新增地图自动纳入。
    """
    import importlib.util
    path = os.path.join(_ROOT, 'src', 'agc_sim', 'launch', 'world_map.py')
    spec = importlib.util.spec_from_file_location('wm_for_tests_names', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return list(mod.WORLD_MAPS)


def _map_flight_altitude(world_map):
    """读某地图的 `flight_altitude` 块（缺失即失败——不得静默回落 base）。"""
    with open(_geometry_file(world_map)) as f:
        doc = yaml.safe_load(f)
    fa = doc.get('flight_altitude')
    assert isinstance(fa, dict), '地图 %s 缺 flight_altitude 块（ADR-0007）' % world_map
    return fa


def _scene_info(scene):
    """构造 launch 口径的 `info`（含该场景实际生效的地图几何）。"""
    scenarios, base = _load()
    sc = scenarios[scene]
    wm = sc.get('world_map') or 'minimal'
    with open(_geometry_file(wm)) as f:
        geometry = yaml.safe_load(f)
    return {'base': base, 'sc': sc, 'geometry': geometry, 'world_map': wm}


def test_cruise_altitude_has_single_source_in_base():
    """H0：巡航高度必须有**唯一权威名** `cruise_alt_m`；`alt_m` 只能是**同值**弃用别名。

 守护的 bug 类别：两个参数名各自承担"爬升量 / 巡航高度"语义，数值又恰好相同
 → 读配置的人（和 的分析）会误判成"两个 2.0 叠加成 4 m"。
 权威名缺失或别名与之不等，都说明配置文件被破坏。
    """
    _, base = _load()
    idr = base['intruder_driver']['ros__parameters']
    assert 'cruise_alt_m' in idr, (
        'intruder_driver 缺少权威参数 cruise_alt_m（H0：巡航高度必须有唯一有效来源）')
    cruise = float(idr['cruise_alt_m'])
    assert cruise > 0, 'cruise_alt_m=%r 必须为正（目标在空中，0 会让感知/火控判据静默失真）' % cruise
    if 'alt_m' in idr:
        assert abs(float(idr['alt_m']) - cruise) < 1e-9, (
            'alt_m=%r 与 cruise_alt_m=%r 不等 → 节点会拒绝启动；弃用别名必须与权威值一致'
            % (idr['alt_m'], cruise))


def test_cruise_altitude_manifest_block_reports_source_and_datum():
    """H0：manifest 必须能还原**实际生效巡航高度 + 来源 + 参考基准**。

 判据：`effective_m` / `source` / `datum` 三项齐备，且显式声明
 它**不是**世界 ENU 绝对高度、**不与**世界 spawn 值叠加——避免下游把相对量当绝对量。
    """
    mod = _composition_module('h0_manifest')
    for scene in ('s04_static_static_obs_track', 's02_linear_none_nominal_track'):
        merged, sc = _merged_for(scene)
        blk = mod.cruise_altitude_block(merged, {'sc': sc}, None)
        assert blk['valid'] is True, '%s: 巡航高度非法 %r' % (scene, blk)
        assert blk['effective_m'] == pytest.approx(2.0), '%s: 生效高度 %r' % (scene, blk['effective_m'])
        assert blk['source'] in ('base', 'scene'), '%s: 来源不明 %r' % (scene, blk['source'])
        assert blk['datum'] == 'episode_origin_ned', '%s: 基准未登记 %r' % (scene, blk['datum'])
        assert blk['world_enu_absolute'] is False, (
            '%s: 不得把巡航高度声明为世界 ENU 绝对高度（H0 实测原点跨 run 漂移）' % scene)
        assert blk['stacks_on_spawn_z'] is False, (
            '%s: 不得声明与世界 spawn z 叠加（实测已排除该叠加）' % scene)
        assert blk['alias_conflicts'] is False, '%s: 别名冲突 %r' % (scene, blk)


def test_cruise_altitude_conflicting_alias_is_flagged():
    """H0：`cruise_alt_m` 与 `alt_m` 同时给出且不等 → 必须被标成冲突（节点据此拒绝启动）。"""
    mod = _composition_module('h0_conflict')
    merged, sc = _merged_for('s04_static_static_obs_track')
    merged['intruder_driver'] = dict(merged['intruder_driver'], cruise_alt_m=3.0, alt_m=2.0)
    blk = mod.cruise_altitude_block(merged, {'sc': {}}, None)
    assert blk['alias_conflicts'] is True, '不等的两个高度未标冲突 → 歧义会被静默放过'


def test_cruise_altitude_scene_override_wins_over_base():
    """H0：场景显式覆盖必须优先于基参，且来源记为 `scene`（可还原覆盖关系）。"""
    mod = _composition_module('h0_scene')
    merged, _ = _merged_for('s04_static_static_obs_track')
    merged['intruder_driver'] = dict(merged['intruder_driver'], cruise_alt_m=3.5, alt_m=3.5)
    sc = {'params': {'intruder_driver': {'cruise_alt_m': 3.5, 'alt_m': 3.5}}}
    blk = mod.cruise_altitude_block(merged, {'sc': sc}, None)
    assert blk['source'] == 'scene', '场景覆盖未被记为 scene：%r' % blk['source']
    assert blk['effective_m'] == pytest.approx(3.5)


def test_cruise_altitude_missing_is_invalid_not_defaulted():
    """H0：两个参数都缺失 → 必须判 `missing`（**不得**静默回落缺省 2.0）。

 缺省回落会让"没配置"看起来像"配置了 2.0"，正是 H0 要消除的静默语义。
    """
    mod = _composition_module('h0_missing')
    merged = {'intruder_driver': {}}
    blk = mod.cruise_altitude_block(merged, {'sc': {}}, None)
    assert blk['source'] == 'missing', '缺参未被判 missing：%r' % blk['source']
    assert blk['valid'] is False, '缺参被当作有效值 → 会静默取缺省'


# ------------------------------------------------------------------------------
# H0 （2026-11-02）：s02/s04 显式巡航高度 + standoff 安全窗口
# ------------------------------------------------------------------------------
def test_cruise_altitude_comes_from_map_not_scene():
    """ADR-0007（2026-11-02）：巡航高度**随地图**派生，场景层不再硬编码。

 修订历史（不得静默改写）：
 * H0 原要求「s02/s04 在**场景层**显式声明 `cruise_alt_m`，source=scene」；
 * ADR-0007 依用户裁定「高度和地图绑定，因为后面会做小障碍高密度和大障碍低密度等图」
 把权威来源改为**地图**（`flight_altitude.target_cruise_m`），source=map。
 守护的 bug 类别（两条，方向相反）：
 ① 场景层又冒出硬编码高度 → 换图不换高度，地图绑定被架空；
 ② 地图缺 `flight_altitude` 块 → 会静默回落到 base，抬高度形同虚设。
    """
    scenarios, base = _load()
    for scene in ('s02_linear_none_nominal_track', 's04_static_static_obs_track'):
        idr = (scenarios[scene].get('params') or {}).get('intruder_driver') or {}
        assert 'cruise_alt_m' not in idr, (
            '%s 又在场景层硬编码了 cruise_alt_m（ADR-0007：高度归地图，见地图文件 '
            'flight_altitude.target_cruise_m）' % scene)
        assert 'alt_m' not in idr, (
            '%s 用弃用别名 alt_m 覆盖高度（应删除，改由地图派生）' % scene)
    # 三张地图都必须声明 flight_altitude 且四键齐全（缺块会静默回落 base）。
    for wm in _world_maps():
        fa = _map_flight_altitude(wm)
        for key in ('own_track_m', 'own_takeoff_m', 'target_cruise_m', 'own_clearance_min_m'):
            assert key in fa, '地图 %s 的 flight_altitude 缺键 %r' % (wm, key)


def test_cruise_altitude_source_is_map_for_s02_s04():
    """ADR-0007：`cruise_altitude.source` 对 s02/s04 必须解析为 `map`（不再是 `scene`）。"""
    mod = _composition_module('h0_r4_source')
    for scene in ('s02_linear_none_nominal_track', 's04_static_static_obs_track'):
        merged, sc = _merged_for(scene)
        info = _scene_info(scene)
        mod.apply_flight_altitude_params(merged, info)
        blk = mod.cruise_altitude_block(merged, info, None)
        assert blk['source'] == 'map', '%s: 来源应为 map，实际 %r' % (scene, blk['source'])
        fa = _map_flight_altitude(info['world_map'])
        assert blk['effective_m'] == pytest.approx(fa['target_cruise_m']), (
            '%s: 生效高度 %r != 地图声明 %r' % (scene, blk['effective_m'], fa['target_cruise_m']))
        assert blk['stacks_on_spawn_z'] is False
        assert blk['alias_conflicts'] is False


def test_yard_is_raised_above_tallest_building():
    """ADR-0007：yard 的目标/己方机高度必须**高于全图最高建筑 + c_clear**。

 这是用户 U2 的验收口径：「现实中没无人机会飞这么低」。yard 最高建筑 `admin_block`
 10.55 m，旧配置 2.5 m 比它低 8.05 m；抬到 12/14 后净空 3.45 m。
    """
    fa = _map_flight_altitude('yard')
    h_max_map = float(fa['derived']['h_max_map_m'])
    assert fa['target_cruise_m'] > h_max_map, (
        'yard 目标巡航 %.2f 未高于全图最高建筑 %.2f（用户 U2 要求）'
        % (fa['target_cruise_m'], h_max_map))
    assert fa['own_track_m'] >= h_max_map + fa['own_clearance_min_m'], (
        'yard 己方机跟踪高度 %.2f 未满足 h_o ≥ H_max_map + c_clear = %.2f'
        % (fa['own_track_m'], h_max_map + fa['own_clearance_min_m']))


def test_flight_altitude_keys_are_sane():
    """ADR-0007：三图高度键的基本合理性（正数、己方机不低于目标、净空为正）。"""
    for wm in _world_maps():
        fa = _map_flight_altitude(wm)
        for key in ('own_track_m', 'own_takeoff_m', 'target_cruise_m', 'own_clearance_min_m'):
            assert float(fa[key]) > 0, '地图 %s 的 %s=%r 必须为正' % (wm, key, fa[key])
        assert fa['own_track_m'] >= fa['target_cruise_m'], (
            '地图 %s 的己方机跟踪高度 %.2f 低于目标巡航 %.2f（视线需向下看目标）'
            % (wm, fa['own_track_m'], fa['target_cruise_m']))


def test_standoff_safe_max_respects_safety_floor_and_sensor_range():
    """`safe_max` 必须同时满足**安全层下界**与**三维感知量程上界**。

 判据（两条件缺一不可）：
 ① 停止趋近点 `safe_max − hysteresis` ≥ 安全层目标圆盘下界
 `target_min_dist + target_margin + reaction_time×max_speed + reachability`
 ——否则 standoff 会把参考推进安全圆盘内，与安全层互相拉扯（实测缺陷）。
      ② 量程上界 `sqrt(range_max² − dz²)` ≥ `safe_max`，dz = 己方跟踪高度 − 目标巡航高度
 ——否则收敛点落在三维量程外，感知无输出。

 这两条都是**几何硬约束**，不是可调口径；本测试不弱化任何既有断言。
    """
    import math

    with open(os.path.join(CONFIG_DIR, 'base.yaml')) as f:
        base = yaml.safe_load(f)['intruder_driver']['ros__parameters']
    air_path = os.path.join(os.path.dirname(os.path.dirname(CONFIG_DIR)), 'agc_air', 'config', 'air.yaml')
    with open(air_path) as f:
        air = yaml.safe_load(f)
    sf = air['standoff_follower']['ros__parameters']
    safety = air['trajectory_tracker']['ros__parameters']['safety']
    # 2026-11-06：`perception_sensors*.yaml` 随 `perception` 轴退役，量程 R 的登记处
    # 改为 `air.yaml` 的 standoff_follower 注释与飞行高度规范 K1（30.0 m）。本测试用
    # 该常量做**配置自洽性验算**（`gt_adapter` 不做几何门控，R 不是运行期限制），
    # 不读已退役文件、不新建第二份数值配置文件。
    range_max = 30.0

    safe_max = float(sf['safe_max'])
    safe_min = float(sf['safe_min'])
    hyst = float(sf['hysteresis'])
    own_h = float(sf['height'])
    target_z = float(base['cruise_alt_m'])

    floor = (float(safety['target_min_dist']) + float(safety['target_margin'])
             + float(safety['reaction_time_s']) * float(safety['max_speed_mps'])
             + float(safety['reachability_margin']))
    dz = own_h - target_z
    ceil = math.sqrt(range_max ** 2 - dz ** 2)

    # ① 停止趋近点不得侵入安全圆盘
    stop_point = safe_max - hyst
    assert stop_point >= floor - 1e-9, (
        '停止趋近点 safe_max−hysteresis = %.3f 低于安全层下界 %.3f → standoff 与安全层冲突'
        % (stop_point, floor))
    # ② 收敛点必须在三维量程内
    assert safe_max <= ceil + 1e-9, (
        'safe_max = %.3f 超出三维量程上界 %.3f（dz=%.2f）→ 收敛点落在量程外'
        % (safe_max, ceil, dz))
    # ③ 带本身合法（下沿 < 上沿），且下沿不高于安全层下界之外太多
    assert safe_min < safe_max, 'safe_min=%r 必须 < safe_max=%r' % (safe_min, safe_max)
    assert safe_min <= floor + 1e-9, (
        'safe_min = %.3f 高于安全层下界 %.3f → 距离带整体落在安全圆盘内' % (safe_min, floor))


def test_standoff_stop_point_matches_safety_floor_minimally():
    """本项取**最小几何修复**——停止点应恰在安全层下界（不多留、不少留）。

 这不是"必须等于"的硬约束（多留余量也合法），而是防止有人把 safe_max 一路调大、
 用扩大距离换来"看起来不冲突"而牺牲量程裕度。允许区间 [floor, ceil]。
    """
    import math

    with open(os.path.join(CONFIG_DIR, 'base.yaml')) as f:
        base = yaml.safe_load(f)['intruder_driver']['ros__parameters']
    air_path = os.path.join(os.path.dirname(os.path.dirname(CONFIG_DIR)), 'agc_air', 'config', 'air.yaml')
    with open(air_path) as f:
        air = yaml.safe_load(f)
    sf = air['standoff_follower']['ros__parameters']
    safety = air['trajectory_tracker']['ros__parameters']['safety']
    # 见 test_standoff_safe_max_respects_safety_floor_and_sensor_range：量程 R=30.0
    # 由飞行高度规范 K1 / air.yaml 注释登记，随 perception 轴退役不再读 sensors 文件。
    range_max = 30.0
    safe_max = float(sf['safe_max'])
    hyst = float(sf['hysteresis'])
    dz = float(sf['height']) - float(base['cruise_alt_m'])
    ceil = math.sqrt(range_max ** 2 - dz ** 2)
    floor = (float(safety['target_min_dist']) + float(safety['target_margin'])
             + float(safety['reaction_time_s']) * float(safety['max_speed_mps'])
             + float(safety['reachability_margin']))

    stop_point = safe_max - hyst
    assert floor - 1e-9 <= stop_point <= floor + 1.0, (
        '停止点 %.3f 应贴近安全层下界 %.3f（最小几何修复），当前偏离 %.3f m'
        % (stop_point, floor, stop_point - floor))
    assert safe_max < ceil, 'safe_max 须严格小于量程上界（保留裕度）'


# ------------------------------------------------------------------------------
# H0 （2026-11-02）：s04 场景级 observe_yaw_mode=track + CLI 覆盖优先
# ------------------------------------------------------------------------------
def _air_merged_for(scene):
    """按 `main.launch.py` 的真实合并路径（air.yaml 基参 → 场景覆盖）构造 air_merged。"""
    scenarios, _ = _load()
    air_path = os.path.join(os.path.dirname(os.path.dirname(CONFIG_DIR)),
                            'agc_air', 'config', 'air.yaml')
    with open(air_path) as f:
        air = yaml.safe_load(f)
    merged = {n: dict(sec.get('ros__parameters', {})) for n, sec in air.items()}
    for n, over in ((scenarios[scene].get('params') or {})).items():
        if n in merged:
            merged[n].update(over)
    return merged, scenarios[scene]


def test_s04_scene_default_observe_yaw_is_track():
    """s04 场景级默认 `observe_yaw_mode` 必须是 `track`（用户授权项）。

 走**真实合并路径**（air.yaml → 场景覆盖），不是只看 YAML 字面：
 合并后 `trajectory_tracker.observe_yaw_mode` 必须真的变成 `track`，
 且 manifest 块来源记为 `scene`（而非 `air_yaml`）。
    """
    mod = _composition_module('h0_r5_s04')
    air_merged, sc = _air_merged_for('s04_static_static_obs_track')
    assert air_merged['trajectory_tracker']['observe_yaw_mode'] == 'track', (
        's04 合并后 observe_yaw_mode=%r，期望 track（场景默认未生效）'
        % air_merged['trajectory_tracker']['observe_yaw_mode'])
    blk = mod.observe_yaw_block({'sc': sc}, air_merged, '')
    assert blk['source'] == 'scene', 's04 来源应为 scene，实际 %r' % blk['source']
    assert blk['effective'] == 'track'
    assert blk['scene_default'] == 'track'
    assert blk['cli_override'] is None


def test_other_scenes_do_not_inherit_track():
    """s02 及其余场景**不得**被隐式改成 track（只授权了 s04）。

 判据：除 s04 外，任何场景合并后的 `observe_yaw_mode` 必须仍是 air.yaml 缺省 `velocity`。
    """
    mod = _composition_module('h0_r5_others')
    scenarios, _ = _load()
    offenders = []
    for scene in scenarios:
        if scene == 's04_static_static_obs_track':
            continue
        air_merged, sc = _air_merged_for(scene)
        val = air_merged['trajectory_tracker']['observe_yaw_mode']
        if val != 'velocity':
            offenders.append((scene, val))
        blk = mod.observe_yaw_block({'sc': sc}, air_merged, '')
        if blk['source'] != 'air_yaml':
            offenders.append((scene, 'source=%s' % blk['source']))
    assert not offenders, '以下场景被隐式改变了观测偏航：%r' % offenders


def test_cli_observe_yaw_overrides_scene_default():
    """显式 CLI `observe_yaw_mode:=<mode>` **优先于**场景默认。

 守护的 bug 类别：把场景默认写成"无条件生效"，使历史对照臂/消融实验无法用 CLI 强制回
 `velocity` 复现旧行为。`main.launch.py` 的顺序是「先合并场景 → 再用非空 CLI 覆盖」，
 本测试按同一顺序验证，并检查 manifest 来源记为 `cli`。
    """
    mod = _composition_module('h0_r5_cli')
    air_merged, sc = _air_merged_for('s04_static_static_obs_track')
    # 模拟 main.launch.py 的 CLI 覆盖步骤（非空才覆盖）
    for cli in ('velocity', 'target', 'track'):
        simulated = dict(air_merged)
        simulated['trajectory_tracker'] = dict(air_merged['trajectory_tracker'])
        simulated['trajectory_tracker']['observe_yaw_mode'] = cli
        blk = mod.observe_yaw_block({'sc': sc}, simulated, cli)
        assert blk['effective'] == cli, 'CLI=%r 未生效，实际 %r' % (cli, blk['effective'])
        assert blk['source'] == 'cli', 'CLI 覆盖时来源应为 cli，实际 %r' % blk['source']
        assert blk['scene_default'] == 'track', '场景默认值应仍被记录（便于复核被覆盖）'
    # 空 CLI = 不覆盖 → 回到场景默认
    blk = mod.observe_yaw_block({'sc': sc}, air_merged, '')
    assert blk['effective'] == 'track' and blk['source'] == 'scene'


def test_air_yaml_global_observe_yaw_unchanged():
    """`air.yaml` 的**全局**默认不得被改成 track（只授权场景级）。"""
    air_path = os.path.join(os.path.dirname(os.path.dirname(CONFIG_DIR)),
                            'agc_air', 'config', 'air.yaml')
    with open(air_path) as f:
        air = yaml.safe_load(f)
    val = air['trajectory_tracker']['ros__parameters']['observe_yaw_mode']
    assert val == 'velocity', (
        'air.yaml 全局 observe_yaw_mode=%r，应为 velocity（本轮只授权 s04 场景级）' % val)


# ------------------------------------------------------------------------------
# ADR-0007：派生注入与四条启动断言（与 composition._flight_altitude_assertions 同判据）
# ------------------------------------------------------------------------------
def test_apply_flight_altitude_injects_map_values():
    """派生注入必须把地图值写进**任务侧**与**空中侧**参数（两侧同源，不各写一份）。"""
    mod = _composition_module('adr0112_inject')
    merged, sc = _merged_for('s04_static_static_obs_track')
    info = _scene_info('s04_static_static_obs_track')
    mod.apply_flight_altitude_params(merged, info)
    air = {'standoff_follower': {}, 'takeoff_controller': {}}
    mod.apply_flight_altitude_air(air, info['geometry'])
    fa = _map_flight_altitude(info['world_map'])
    assert merged['intruder_driver']['cruise_alt_m'] == pytest.approx(fa['target_cruise_m'])
    assert air['standoff_follower']['height'] == pytest.approx(fa['own_track_m'])
    assert air['takeoff_controller']['takeoff_altitude_m'] == pytest.approx(fa['own_takeoff_m'])


def test_air_hover_climb_tracks_takeoff_altitude():
    """`air_hover_climb_m`（起飞完成判据）必须跟着抬——否则整链卡在 air_hover_timeout。

 守护的 bug 类别：只抬 `takeoff_altitude_m` 而忘了起飞完成判据，任务管理器永远等不到
 「爬升量 ≥ 阈值」，如实拒绝 start（INFRA_FAILURE）——表现为"仿真起不来"而非配置报错。
    """
    mod = _composition_module('adr0112_hover')
    for scene in ('s04_static_static_obs_track', 's02_linear_none_nominal_track'):
        merged, _ = _merged_for(scene)
        info = _scene_info(scene)
        mod.apply_flight_altitude_params(merged, info)
        fa = _map_flight_altitude(info['world_map'])
        climb = float(merged['task_manager']['air_hover_climb_m'])
        assert climb < fa['own_takeoff_m'], (
            '%s: air_hover_climb_m=%.2f 必须小于 takeoff_altitude=%.2f（否则永不满足）'
            % (scene, climb, fa['own_takeoff_m']))
        assert climb >= fa['own_takeoff_m'] - 0.5, (
            '%s: air_hover_climb_m=%.2f 与起飞高度 %.2f 差距过大（会在没爬到位时就判完成）'
            % (scene, climb, fa['own_takeoff_m']))


def test_net_params_derived_only_when_base_cannot_reach():
    """网弹道只在**基线打不到**该高度时才重标定——否则 minimal 的历史基线会被改写。"""
    mod = _composition_module('adr0112_net')
    base_cap = {'v0': 6.5, 'angle_deg': 75.0, 'g': 9.81}
    # 目标 2.0 m，基线 apex=2.009 → 打得到 → 不派生
    assert mod.net_params_for_altitude(2.0, base_cap) is None, (
        '目标 2.0 m 在基线包络内，不得重标定（会改写 minimal 历史证据基线）')
    # 目标 12.0 m，基线 apex=2.009 → 打不到 → 必须派生
    d = mod.net_params_for_altitude(12.0, base_cap)
    assert d is not None, '目标 12.0 m 超出基线包络，必须重标定网弹道'
    # 派生后 apex 必须覆盖目标高度（否则 capture 场景仍全 TIMEOUT）
    import math as _m
    vy = d['net_v0_mps'] * _m.sin(_m.radians(d['net_angle_deg']))
    apex = vy * vy / (2.0 * base_cap['g'])
    assert apex > 12.0, '派生后 apex=%.3f 未覆盖目标 12.0 m' % apex
    # 飞行超时必须大于落地时刻（否则网还没落就先判超时失手）
    t_land = 2.0 * vy / base_cap['g']
    assert d['net_flight_timeout_s'] > t_land, (
        'net_flight_timeout_s=%.2f 必须 > 落地时刻 %.2f' % (d['net_flight_timeout_s'], t_land))


def test_flight_altitude_assertions_pass_for_all_scenes():
    """四条启动断言必须对**全部场景**成立（全场景静态扫描，不只当前场景）。"""
    mod = _composition_module('adr0112_assert')
    scenarios, base = _load()
    for scene in scenarios:
        merged, _ = _merged_for(scene)
        info = _scene_info(scene)
        mod.apply_flight_altitude_params(merged, info)
        air = {'standoff_follower': dict(
                   (base.get('standoff_follower') or {}).get('ros__parameters') or {}),
               'takeoff_controller': dict(
                   (base.get('takeoff_controller') or {}).get('ros__parameters') or {})}
        # air.yaml 的 standoff/takeoff 段不在 base 里，从 air.yaml 取真实基线
        import yaml as _yaml
        air_doc = _yaml.safe_load(open(os.path.join(
            _ROOT, 'src', 'agc_air', 'config', 'air.yaml')))
        air = {n: dict(s.get('ros__parameters', {})) for n, s in air_doc.items()
               if n in ('standoff_follower', 'takeoff_controller')}
        for n, over in ((scenarios[scene].get('params') or {})).items():
            if n in air:
                air[n].update(over)
        mod.apply_flight_altitude_air(air, info['geometry'])
        res = mod._flight_altitude_assertions(merged, info, air, info['geometry'])
        bad = [k for k, v in res.items() if not v]
        assert not bad, '场景 %s 的高度断言失败：%s' % (scene, bad)


# ------------------------------------------------------------------------------
# 2026-11-03：反无人机场景禁用固定轨迹 —— **从文档变成测试**
#
# 背景：`docs/conventions/飞行高度分层与按地图定高.md#no-fixed-trajectory` 在 2026-11-02
# 17:12 就写死了硬规则（用户原话「各种无人机固定轨迹是用来确定之前流程的，反无人机场景
# 直接禁止使用」），但**从未落地**：`air.yaml` 仍是 `Figure8Trajectory`，
# `scenarios.yaml` 零覆盖，且没有任何测试守护。
# 实测后果：已退役的 `air_fusion` 路径长期靠「八字偶然扫进量程」看见目标（占空比 42%），
# 把一条**已被否决**的机制当成了主线依赖。
#
# 本测试把该规则变成可执行判据。**注意它的适用边界**（写在这里以免误读）：
# * 规则针对**反无人机（counter-UAV）场景**的己方机参考来源；
# * `Figure8Trajectory` 等预设轨迹**插件本身保留**（流程验证 / 回归基线仍可用），
# 禁止的是「在反无人机场景里把它选为参考来源」；
# * 2026-11-03 用户已裁定搜索能力取消、主线转真值目标指示 ——
# 因此本测试的**要求方向**是「显式声明」，不是「必须用 Hover」。
# `HoverTrajectory` 与其它"不产生运动"的实现同等合法。
# ------------------------------------------------------------------------------

# 「不产生运动」的实现白名单：接管后保持位置、无速度前馈。
# HoverTrajectory = 保持接管位置（`hold_ = initial.pos`）
# 若日后新增同类实现（如保持当前姿态的插件），在此登记即可。
_NO_MOTION_PLUGINS = frozenset({
    'agc_control/HoverTrajectory',
})

# 反无人机场景的**判定口径**：场景名或 axes 表明它是 counter-UAV 任务。
# 本仓的 `sNN_*` 场景族全部属反无人机任务（目标机 + 己方机 + 地面车协同）。
# 排除的是「流程验证」用途的显式标注场景（见规范 规范 第二条）。
_COUNTER_UAV_SCENE_PREFIX = 's'


def _is_counter_uav_scene(scene_id, scene_cfg):
    """反无人机场景判定：`sNN_*` 命名族 + 未被显式标注为流程验证。

 规范 规范：「新增流程验证场景（需要八字/圆周等预设轨迹做基线）：可以选预设插件，
 但**场景名与产物必须标注**其用途是流程验证」。
 ⇒ 显式标注位 = `params.run_logger.usage` 或场景级 `usage` 字段，值为 `flow_validation`。
    """
    usage = ((scene_cfg.get('params') or {}).get('run_logger') or {}).get('usage') \
        or scene_cfg.get('usage')
    if usage == 'flow_validation':
        return False
    return scene_id.startswith(_COUNTER_UAV_SCENE_PREFIX)


def _effective_trajectory_plugin(scene_cfg):
    """该场景**实际生效**的 `trajectory_plugin`（场景覆盖 > air.yaml 缺省）。"""
    air_doc = yaml.safe_load(open(os.path.join(
        os.path.dirname(os.path.dirname(CONFIG_DIR)), 'agc_air', 'config', 'air.yaml')))
    base_plugin = air_doc['trajectory_tracker']['ros__parameters'].get(
        'trajectory_plugin', '')
    over = (scene_cfg.get('params') or {}).get('trajectory_tracker') or {}
    return over.get('trajectory_plugin', base_plugin)


def test_counter_uav_scenes_declare_non_motion_trajectory():
    """反无人机场景必须**显式声明**一个"不产生运动"的兜底轨迹插件。

 为什么这条重要（实测证据，不是理论洁癖）：
 `Figure8Trajectory` 作为兜底时，一旦 `tracking_ref` 超时 0.5 s，飞机会按八字飞走。
 在 `air_fusion` 路径下这曾表现为「八字偶然扫进量程 → 看见一帧 → 长期 TIMEOUT」，
 把任务成败绑在一个**已被用户否决**的机制上（`20261103-n1-stag70` 三次全败）。
    """
    scenarios, _base = _load()
    violations = []
    for scene_id, scene_cfg in scenarios.items():
        if not _is_counter_uav_scene(scene_id, scene_cfg):
            continue
        plugin = _effective_trajectory_plugin(scene_cfg)
        if plugin not in _NO_MOTION_PLUGINS:
            violations.append((scene_id, plugin))
    assert not violations, (
        '反无人机场景的 trajectory_plugin 必须是"不产生运动"的实现（白名单：%s），'
        '违反：%s。\n规则来源：docs/conventions/飞行高度分层与按地图定高.md#no-fixed-trajectory\n'
        '修法：在 scenarios.yaml 的该场景 params 里显式写 '
        'trajectory_tracker: {trajectory_plugin: "agc_control/HoverTrajectory"}'
        % (sorted(_NO_MOTION_PLUGINS), violations))


def test_air_yaml_default_plugin_is_not_a_preset_motion_trajectory():
    """`air.yaml` 的**全局缺省**不得是预设运动轨迹（否则每个场景都静默继承它）。

 与上一条的区别：上一条查「场景实际生效值」，本条查「缺省值本身」。
 缺省是预设轨迹时，任何**忘记覆盖**的新场景都会自动违反规则——
 这类"沉默继承"正是原规则落地失败的直接原因。
    """
    air_doc = yaml.safe_load(open(os.path.join(
        os.path.dirname(os.path.dirname(CONFIG_DIR)), 'agc_air', 'config', 'air.yaml')))
    plugin = air_doc['trajectory_tracker']['ros__parameters'].get('trajectory_plugin', '')
    assert plugin in _NO_MOTION_PLUGINS, (
        'air.yaml 的 trajectory_plugin 缺省值 = %r，属预设运动轨迹。\n'
        '反无人机场景禁用固定轨迹（docs/conventions/飞行高度分层与按地图定高.md'
        '#no-fixed-trajectory）⇒ 缺省必须是"不产生运动"的实现（白名单：%s）。\n'
        '预设轨迹插件**保留**（流程验证场景可显式选用），只是不得作为缺省。'
        % (plugin, sorted(_NO_MOTION_PLUGINS)))


def test_flow_validation_scene_may_use_preset_trajectory():
    """反向守护：显式标注 `usage=flow_validation` 的场景**允许**用预设轨迹。

 若把规则写成"所有场景一律禁止"，流程验证 / 回归基线就没了载体——
 规则本身会被绕过（写死为 Hover 后再无对照臂）。
 本测试确保「显式标注即放行」这条出口**真的存在且可用**。
    """
    scenarios, _base = _load()
    # 构造一个显式标注为流程验证的合成场景，验证判定函数确实放行
    fake = {'usage': 'flow_validation',
            'params': {'trajectory_tracker': {'trajectory_plugin':
                'agc_control/Figure8Trajectory'}}}
    assert not _is_counter_uav_scene('s99_figure8_flow', fake), (
        '显式 usage=flow_validation 的场景应被排除在反无人机规则之外')
    # 同一场景去掉标注后必须重新落入规则范围
    fake2 = dict(fake)
    fake2.pop('usage')
    assert _is_counter_uav_scene('s99_figure8_flow', fake2), (
        '去掉 usage 标注后必须重新受规则约束（否则标注就成了万能豁免）')


# ------------------------------------------------------------------------------
# ADR-0036（2026-11-10）：出生位是**地图属性**（`spawn_layout.per_map`）
# ------------------------------------------------------------------------------
def _spawn_layout_raw():
    with open(os.path.join(CONFIG_DIR, 'spawn_layout.yaml')) as f:
        return yaml.safe_load(f)['spawn_layout']


def test_spawn_layout_per_map_covers_every_registered_map_or_falls_back():
    """`per_map` 的每个键必须是**已登记地图**；未登记的地图必须回落顶层（逐值不变）。

 守护的 bug 类别（两条，方向相反）：
 ① `per_map` 写了拼错的地图名 → 覆盖静默失效，换图不换出生位（正是 ADR-0036 要消灭的病灶）；
 ② 顶层坐标被顺手改掉 → 三张旧图的出生位与全部历史证据基线一起漂移。
    """
    layout = _spawn_layout_raw()
    per_map = layout.get('per_map') or {}
    registered = set(_world_maps())
    unknown = sorted(set(per_map) - registered)
    assert not unknown, (
        'spawn_layout.per_map 含未登记的地图 %s（可用：%s）—— 拼错地图名会让覆盖静默失效'
        % (unknown, sorted(registered)))
    # 未在 per_map 登记的图 → 必须与顶层逐值相同
    for wm in registered:
        if wm in per_map:
            continue
        eff = _load_spawn_layout_for(wm)
        for entity, keys in (('car', ('x', 'y')), ('target', ('x', 'y')),
                             ('own_uav', ('x', 'y'))):
            for k in keys:
                assert float(eff[entity][k]) == float(layout[entity][k]), (
                    '地图 %s 未在 per_map 登记，%s.%s 却与顶层不一致（%r != %r）'
                    % (wm, entity, k, eff[entity][k], layout[entity][k]))


def _load_spawn_layout_for(world_map):
    import importlib.util
    launch_dir = os.path.join(os.path.dirname(CONFIG_DIR), 'launch')
    spec = importlib.util.spec_from_file_location(
        'scene_spawn_for_test', os.path.join(launch_dir, 'scene_spawn.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.load_spawn_layout(os.path.dirname(CONFIG_DIR), world_map=world_map)


def test_spawn_layout_rejects_unknown_entity_in_per_map(tmp_path):
    """`per_map` 里拼错实体段（如 `cars`）必须**拒绝运行**，不得静默忽略。

 为什么必须拒绝：拼错实体名时覆盖**看起来生效**（文件合法、launch 不报错），
 实际车仍从顶层坐标出发 —— 这类"静默不生效"比报错昂贵得多。
    """
    path = _layout_with(None, lambda d: d.__setitem__(
        'per_map', {'yard': {'cars': {'x': 1.0}}}))
    with pytest.raises(RuntimeError, match='未知实体段'):
        _load_spawn_layout_from(path)


def test_spawn_layout_per_map_applies_for_dense_map():
    """`dense_map` 的出生位必须是"目标居中、车与己方机在西边缘"，且满足设计目标。

 这是用户 2026-11-10 的布局裁定（Q6）：目标 (0,0)、车在西边缘、己方机 (-34,-2)。
 判据（与 `scene_assertions.spawn_design_goals_met` 同口径）：
 车↔目标 ≥30 m、己方机↔目标 ≥25 m、车↔己方机 ∈[3,8] m。

 **车的具体坐标不是本测试的判据**（2026-11-13 ADR-0047 把它从 (-34,-6) 移到 (-40,-6)）：
 出生位必须满足"出发即不被安全层误停"这一**几何前置闸门**，见
 `test_dense_map_spawn_is_not_inside_collision_tier`。
    """
    import math
    if 'dense_map' not in _world_maps():
        pytest.skip('dense_map 未登记')
    eff = _load_spawn_layout_for('dense_map')
    car, tgt, own = eff['car'], eff['target'], eff['own_uav']
    assert (tgt['x'], tgt['y']) == (0.0, 0.0), (
        'dense_map 目标应在作业区正中 (0,0)，实际 (%g,%g)' % (tgt['x'], tgt['y']))
    d_ct = math.hypot(car['x'] - tgt['x'], car['y'] - tgt['y'])
    d_ot = math.hypot(own['x'] - tgt['x'], own['y'] - tgt['y'])
    d_co = math.hypot(car['x'] - own['x'], car['y'] - own['y'])
    assert d_ct >= 30.0, 'dense_map 车↔目标 %.2f < 30 m（F1 设计目标）' % d_ct
    assert d_ot >= 25.0, 'dense_map 己方机↔目标 %.2f < 25 m（F1 设计目标）' % d_ot
    assert 3.0 <= d_co <= 8.0, 'dense_map 车↔己方机 %.2f 不在 [3,8] m（F1 设计目标）' % d_co


def test_dense_map_spawn_is_not_inside_collision_tier():
    """车出生位到最近障碍的净空必须 **> `d_collision` + 余量**，否则一启动就被判停车。

 ## 为什么需要这条（ADR-0047，2026-11-13）

 旧出生位 `(-34,-6)` 的车心到最近障碍只有 **1.75 m**，而安全层 `d_collision = 2.0 m`
 ⇒ 整链 20 次实跑 `TRACKING_SUCCESS` = **0/20**、`ticks_triggered` 5,420–7,176。
 这个"车一步都不动"被误读成"地图太密、车过不去"，而实测面积覆盖只有 7.2%、
 相邻间隙 p50 = 4.54 m、车宽 0.57 m —— **通道本来就在**，问题在出生位。

 ## 判据口径（与 `safety_policy.hpp` 的 `distanceToFootprint` 同构）

 净空 = 车体矩形（半长 0.5037 / 半宽 0.28545）外缘到最近障碍**足迹**的距离。
 障碍按真实几何（box 用有向矩形、cylinder 用圆），**不**按外接圆膨胀 ——
 外接圆会把长条 box 放大 3 倍以上，那会造出"看起来必须移出生位"的假阳性。

 门槛取 `d_collision` 再加 `margin_m` 余量：只判 `>= d_collision` 会让出生位
 贴着门槛，实跑抖动一次就掉进停车档。车体伸出取**半对角**（任意朝向都成立的保守下界），
 下界都过门槛 ⇒ 任何朝向都过。

 `margin_m` 是**本判据自己的**余量常量（0.14 m ≈ 0.5 m 规划层半格对角），
 不是任何节点的运行参数 —— 它只影响"出生位要离障碍多远才算合格"这一静态检查。
    """
    import math
    if 'dense_map' not in _world_maps():
        pytest.skip('dense_map 未登记')

    maps_path = os.path.join(
        _ROOT, 'src', 'agc_sim', 'config', 'maps', 'dense_map.yaml')
    with open(maps_path) as f:
        obstacles = yaml.safe_load(f).get('obstacles') or []
    assert obstacles, 'dense_map 没有障碍，判据失去意义'

    eff = _load_spawn_layout_for('dense_map')
    car = eff['car']
    cx, cy = float(car['x']), float(car['y'])

    # 车体半长 / 半宽与安全层参数同源（同一碰撞盒，不是复制约束）。
    with open(os.path.join(_ROOT, 'src', 'agc_ground', 'config', 'ground.yaml')) as f:
        ground = yaml.safe_load(f)
    fp = (ground.get('ground_safety_filter') or {}).get('ros__parameters') or {}
    half_l = float(fp.get('footprint_half_length', 0.5037))
    half_w = float(fp.get('footprint_half_width', 0.28545))
    d_collision = float(fp.get('d_collision', 2.0))
    # 本判据自己的余量常量（0.5 m 规划层半格对角）；不是节点运行参数。
    margin = 0.14

    def clearance(x, y):
        """点到障碍足迹的最小距离（点在内部 → 0）。"""
        best = float('inf')
        for ob in obstacles:
            ox, oy = float(ob['x']), float(ob['y'])
            size = ob['size']
            if ob.get('shape') == 'box':
                hl, hw = float(size[0]) / 2.0, float(size[1]) / 2.0
                yaw = float(ob.get('yaw', 0.0))
                c, s = math.cos(yaw), math.sin(yaw)
                dx, dy = x - ox, y - oy
                u, v = dx * c + dy * s, -dx * s + dy * c
                du = max(abs(u) - hl, 0.0)
                dv = max(abs(v) - hw, 0.0)
                best = min(best, math.hypot(du, dv))
            else:
                r = float(size[0])
                best = min(best, max(0.0, math.hypot(x - ox, y - oy) - r))
        return best

    car_clearance = clearance(cx, cy) - math.hypot(half_l, half_w)
    need = d_collision + margin
    assert car_clearance > need, (
        'dense_map 车出生位 (%.1f,%.1f) 的车体外缘净空 %.2f m <= d_collision+margin %.2f m；'
        '一启动就会进停车档而零速（ADR-0047 的原始缺陷形态）'
        % (cx, cy, car_clearance, need))


def test_dense_map_scene_is_registered_and_points_to_dense_map():
    """`dense_map` 必须有**当前消费者**场景（路线分支治理 准入②），且指向该图。

 同时守护期望终态：该图不留走廊 ⇒ 跟踪终态不可达是**设计意图**，
 场景必须声明 `MISSION_FAILED`；把它写成 `TRACKING_SUCCESS` 会让回归永远红着。
    """
    scenarios, _base = _load()
    consumers = [s for s, v in scenarios.items() if v.get('world_map') == 'dense_map']
    assert consumers, (
        'dense_map 没有任何场景消费者 —— 新地图必须有当前消费者，否则是空登记')
    for s in consumers:
        sc = scenarios[s]
        assert str(sc.get('expected_terminal')) == 'MISSION_FAILED', (
            '%s 期望终态应为 MISSION_FAILED（该图不留走廊，车到不了目标）' % s)
        # 出生位随地图派生（ADR-0036）——场景层不得再覆盖出生位（第二来源）
        sr = ((sc.get('params') or {}).get('scenario_reset') or {})
        leaked = {'car_x', 'car_y', 'target_x', 'target_y'} & set(sr)
        assert not leaked, (
            '%s 覆盖了出生位 %s —— ADR-0036 起出生位随地图派生（spawn_layout.per_map）'
            % (s, sorted(leaked)))
