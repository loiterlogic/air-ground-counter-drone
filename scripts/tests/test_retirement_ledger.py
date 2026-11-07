#!/usr/bin/env python3
"""退役物总台账核对 —— 治理规范已退役台账 / 保留项的可执行防复活闸门。

见 docs/conventions/路线分支治理.md#current（4.2/4.3/4.4/4.5）。

本文件回答一个问题：**一个产物是活的还是退役的，能不能被机器判定？**
  * 5.2 登记「已删除」的路径 → 必须真的不存在（防"顺手加回来"）；
  * 5.2 登记「保留但固定值」的产物键 → 必须真的带固定值标记（schema 不漂移）；
  * 5.2 登记「删除」的轴 / 参数 / 场景号 → 配置文件里不得再出现；
  * 5.3 的保留项 → 台账必须写全四字段（现状/理由/影响/复核触发条件），
    防止"以后会用"变成无期限的永久占位；
  * 台账与代码常量（`RETIRED_BRANCHES` / manifest 固定值）必须一致，各说各话即失败。

与同类闸门的分工：
  * `test_branch_ledger.py` —— 5.1 活跃分支参数恰好等于台账；
  * `test_dds_contract_guard.py` —— 视觉定位路径 / perception 轴的专项闸门；
  * **本文件** —— 退役物（节点/文件/配置/轴/参数/产物键/保留项）的**总台账**。

进 `tests/run_smoke.py` 的 offline 组，每次提交都跑。
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONVENTION = ROOT / 'docs' / 'conventions' / '路线分支治理.md'
SCENARIOS = ROOT / 'src' / 'agc_task' / 'config' / 'scenarios.yaml'
CARRIERS = ROOT / 'src' / 'agc_task' / 'config' / 'scenario_carriers.yaml'
COMPOSITION = ROOT / 'src' / 'agc_task' / 'launch' / 'composition.py'
PERCEPTION_LAUNCH = ROOT / 'src' / 'agc_perception' / 'launch' / 'perception_bringup.launch.py'
PERCEPTION_YAML = ROOT / 'src' / 'agc_perception' / 'config' / 'perception.yaml'
PERCEPTION_CMAKE = ROOT / 'src' / 'agc_perception' / 'CMakeLists.txt'
M0_LAUNCH = ROOT / 'src' / 'agc_task' / 'launch' / 'skeleton.launch.py'
W6_LAUNCH = ROOT / 'src' / 'agc_task' / 'launch' / 'main.launch.py'

# --------------------------------------------------------------------------------------
# 5.2.2 批次：登记「已删除」的退役物路径（相对 ROOT）
# --------------------------------------------------------------------------------------
DELETED_PATHS = (
    'src/agc_perception/src/air_perception.cpp',
    'src/agc_perception/config/perception_sensors.yaml',
    'src/agc_perception/config/perception_sensors_dropout.yaml',
    'src/agc_perception/config/perception_sensors_fov.yaml',
    'src/agc_perception/config/perception_sensors_no_target.yaml',
    # 5.2.3 批次：评审快照目录（ADR-0033）
    'docs/reviews',
)

# 这些文件仍在，但其中不得再出现已退役标识的**代码形态**。
# 只查代码形态（节点注册 / 参数声明 / 段键 / 解析链），不查注释与文档字符串——
# 退役说明本身必须允许写进注释（否则"删了却不能解释为什么删"）。
ALIVE_FILES_NO_RETIRED_SYMBOLS = {
    PERCEPTION_CMAKE: ('add_executable(air_perception', 'air_perception map_adapter'),
    PERCEPTION_LAUNCH: ("executable='air_perception'", "DeclareLaunchArgument('sensors_file'",
                        "DeclareLaunchArgument('seed'", 'ParameterValue(seed, value_type=str)'),
    PERCEPTION_YAML: ('air_perception:', '/agc/perception/sensors_file  →'),
    M0_LAUNCH: ("DeclareLaunchArgument(\n        'sensors_file'", "'sensors_file': LaunchConfiguration",
                "DeclareLaunchArgument(\n        'seed', default_value='0'"),
    W6_LAUNCH: ("'sensors_file':", "'seed': LaunchConfiguration('seed')"),
    COMPOSITION: ("info['sensors_file", "entries['perception']", 'perception_sensors_file_effective_matches',
                  "res['dz_within_perception_range']", 'def _load_sensors_range(',
                  'def _load_air_baseline('),
}


def _text(path: Path) -> str:
    return path.read_text(encoding='utf-8', errors='replace')


def test_deleted_retired_paths_do_not_exist():
    """5.2：登记为「已删除」的退役物不得复活。"""
    revived = [p for p in DELETED_PATHS if (ROOT / p).exists()]
    assert not revived, (
        '已退役对象又在活跃层出现（违反防复活闸门）：\n  - %s\n'
        '若确需恢复：须按 2.2 节四项重新立项（含用户明确允许 + 退役条件），'
        '并从 5.2 台账移除本条。' % '\n  - '.join(revived))


def test_retired_review_dir_whitelist_not_revived():
    """5.2.3：`docs/reviews/` 退役后，**不得**用"加白名单"的方式让它复活。

    退役的目的之一是缩小例外面：删目录之前，链接检查与引用纪律各有一处
    `docs/reviews/` 白名单；删之后这两处必须消失。把它们加回来 = 复活。
    """
    offenders = []
    for rel, token in (
        ('tests/docs_link_check.py', 'docs/reviews'),
        ('scripts/tests/test_reference_discipline.py', 'docs/reviews'),
    ):
        text = _text(ROOT / rel)
        # ADR-0033 的取回说明只出现在 ADR 里；工具文件出现该 token 即白名单回潮
        if token in text:
            offenders.append(rel)
    assert not offenders, (
        '已退役的 `docs/reviews/` 又被工具加了白名单：%s\n'
        '删除目录的目的就是缩小例外面；若确需恢复，须按 2.2 节四项重新立项。' % ', '.join(offenders))


def test_no_retired_symbols_in_alive_files():
    """5.2：承载物删了，解析/注入链也不许留（不许留读不到值的透传）。"""
    for path, symbols in ALIVE_FILES_NO_RETIRED_SYMBOLS.items():
        text = _text(path)
        for sym in symbols:
            assert sym not in text, (
                '%s 仍含已退役标识 %r：清退未做干净（承载物与解析/注入链须一并删）'
                % (path.relative_to(ROOT), sym))


def test_perception_axis_is_retired_in_configs():
    """5.2：scenarios.yaml 不得声明 perception 轴；carriers 不得登记该轴；s17 不得回来。"""
    scenes = yaml.safe_load(_text(SCENARIOS))['scenes']
    assert 's17_static_none_no_target_timeout' not in scenes, 's17 已随 perception 轴退役，不得重新登记'
    for name, sc in scenes.items():
        assert 'perception' not in (sc.get('axes') or {}), (
            '场景 %s 仍声明已退役的 perception 轴' % name)

    axes = yaml.safe_load(_text(CARRIERS))['axes']
    assert 'perception' not in axes, 'scenario_carriers.yaml 仍登记已退役的 perception 轴'
    assert set(axes) == {'target_motion', 'obstacle', 'outcome'}, (
        '场景轴集合与 5.2 台账不符：%r' % sorted(axes))


def test_manifest_keeps_sensors_file_key_with_fixed_value():
    """4.4 schema 不漂移：manifest 保留 sensors_file 键，值恒为退役标记。"""
    spec = importlib.util.spec_from_file_location('w6c_retirement', str(COMPOSITION))
    w6c = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(w6c)

    obstacles = ROOT / 'src' / 'agc_perception' / 'config' / 'obstacles_none.yaml'
    info = {
        'scene': 's01_static_none_nominal_track', 'seed': 0,
        'axes': {}, 'entries': {}, 'sc': {}, 'support_status': {},
        'world_obstacles': 'none', 'obstacles_file_name': 'obstacles_none.yaml',
        'obstacles_file': str(obstacles), 'world_file': 'world.sdf',
        'geometry': {'work_area': {}, 'obstacles': []},
        'geometry_source': 'world_geometry.yaml', 'geometry_sha256': '0' * 64,
    }
    manifest = w6c.build_manifest('lightweight', info, {}, {})
    eff = manifest['effective_params']
    assert 'sensors_file' in eff, 'manifest 丢了 sensors_file 键（schema 漂移）'
    assert eff['sensors_file'] == 'retired:perception-axis', (
        'sensors_file 必须恒为退役标记，实际 %r' % eff['sensors_file'])
    # 声明轴里不得再出现 perception
    assert 'perception' not in (manifest.get('declared_axes') or {}), 'manifest 仍声明已退役的 perception 轴'


def test_ledger_constants_agree_with_code():
    """台账与代码常量必须一致（防"文档说删了、闸门还留着"或反之）。"""
    # 5.2.1 的 RETIRED_BRANCHES 必须被 branch_ledger 登记
    spec = importlib.util.spec_from_file_location(
        'branch_ledger_retirement', str(ROOT / 'scripts' / 'tests' / 'test_branch_ledger.py'))
    bl = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bl)
    retired = set(bl.RETIRED_BRANCHES)
    for arg in ('perception_path', 'vision_detector', 'detector_backend', 'obstacles_source',
                'observe_yaw_mode', 'shield', 'spawn_randomize', 'standoff_safe_max',
                'air_tracking_ref'):
        assert arg in retired, '5.2.1 台账登记了 %s，但 branch_ledger 未把它列进 RETIRED_BRANCHES' % arg

    # 已退役分支不得在 launch 里复活（与 test_branch_ledger 同口径，这里从台账侧再核一次）
    conv = _text(CONVENTION)
    for arg in sorted(retired):
        assert arg in conv, 'RETIRED_BRANCHES 的 %s 未在治理规范台账登记' % arg


def test_keep_register_entries_have_four_fields():
    """4.5：5.3 保留项必须写全四字段（现状/理由/影响/复核触发条件），不得是空占位。"""
    conv = _text(CONVENTION)
    m = re.search(r'### 5\.3 .*?\n(.*?)(?=\n## 6\.)', conv, re.S)
    assert m, '治理规范缺少 5.3 保留项台账'
    body = m.group(1)
    rows = [l for l in body.splitlines() if l.startswith('|') and not l.startswith('|---')]
    header = rows[0]
    assert all(k in header for k in ('现状', '保留理由', '影响', '复核触发条件')), (
        '5.3 表缺四字段表头：%s' % header)
    for row in rows[2:]:  # 跳过表头与分隔行
        cells = [c.strip() for c in row.strip().strip('|').split('|')]
        assert len(cells) == 5, '5.3 行列数不为 5（项 + 四字段）：%s' % row
        for i, field in ((2, '保留理由'), (3, '影响'), (4, '复核触发条件')):
            assert cells[i], '5.3 项 %r 的「%s」为空（"以后会用"不许变成永久占位）' % (cells[0], field)
        # 复核触发条件必须是可判定事件，不得是"定期看看 / 以后再说"
        assert re.search(r'立项|复核|变更|升版|重命名|发布边界|改 ', cells[4]), (
            '5.3 项 %r 的复核触发条件不可判定：%r' % (cells[0], cells[4]))
