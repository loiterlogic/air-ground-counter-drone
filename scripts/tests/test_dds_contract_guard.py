#!/usr/bin/env python3
"""`check_dds_contract.py` 的 case e（防复发主闸）自身的行为测试。

为什么需要：闸门如果**静默失效**（正则写窄、豁免放宽、扫描路径剪错），它就会变成
第二份"文档劝告"——看起来有保护，实际不拦。2026-11-04 首次实现时正是一版**漏报**
（`os.environ["…"] = "LOCALHOST"` 未被匹配），靠这里的用例才被抓住。

守护三件事：
 1. 各种**真实写法**都被判为违规（含跨行、yaml、bash export）；
 2. **合法的讲解/断言语境**不误报（反引号文档引用、`'…' in sh` 断言）；
 3. 豁免范围不被悄悄扩大。

见 [ADR-0028](../docs/adr/0028-dds-discovery-range-and-transport.md#guard)。
"""

import importlib.util
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / 'tests' / 'check_dds_contract.py'


def _load():
    spec = importlib.util.spec_from_file_location('dds_contract', str(CHECK))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope='module')
def check():
    return _load()


VIOLATIONS = [
    'os.environ["ROS_AUTOMATIC_DISCOVERY_RANGE"] = "LOCALHOST"',
    "env['ROS_AUTOMATIC_DISCOVERY_RANGE'] = 'LOCALHOST'",
    "\"ROS_AUTOMATIC_DISCOVERY_RANGE\": 'LOCALHOST',",
    'export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST',
    '  ROS_AUTOMATIC_DISCOVERY_RANGE: LOCALHOST',
]

ALLOWED = [
    '# 旧做法曾写 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST，已废弃',
    '`ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST` 是旧铁律',
    "'sh_discovery_localhost': 'ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST' in sh,",
    'ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET',
    "'ROS_AUTOMATIC_DISCOVERY_RANGE=%s' % value",
]


@pytest.mark.parametrize('line', VIOLATIONS)
def test_real_forms_are_flagged(check, line):
    assert check._line_hardcodes_localhost(line), line


@pytest.mark.parametrize('line', ALLOWED)
def test_legitimate_contexts_are_not_flagged(check, line):
    assert not check._line_hardcodes_localhost(line), line


def test_multiline_form_is_flagged(check, tmp_path, monkeypatch):
    """跨行写法（键与值分两行）必须也被抓到——逐行判会漏。"""
    target = ROOT / 'scripts' / '_guard_probe_multiline.py'
    try:
        target.write_text(
            "x = {'ROS_AUTOMATIC_DISCOVERY_RANGE':\n     'LOCALHOST'}\n", encoding='utf-8')
        res = check.case_e_no_hardcoded_localhost({})
        assert res['pass'] is False, '跨行写法未被拦截（闸门失效）'
        assert any('_guard_probe_multiline.py' in o for o in res['hardcoded_localhost'])
    finally:
        target.unlink(missing_ok=True)


def test_clean_repo_passes(check):
    """当前仓库必须干净；万一有人写死，这里会先红，定位比整链失败快得多。"""
    res = check.case_e_no_hardcoded_localhost({})
    assert res['pass'] is True, '活跃代码出现写死 LOCALHOST：%r' % (res['hardcoded_localhost'],)
    assert res['scanned_files'] > 100, '扫描文件数异常少，疑似路径/剪枝写错'


def test_exemptions_stay_narrow(check):
    """豁免只应覆盖归档/证据/策略表自身；不得吃掉活代码目录。"""
    exempt = ' '.join(check._HARDCODE_EXEMPT_DIRS) + ' ' + ' '.join(
        check._HARDCODE_EXEMPT_FILES)
    for must_exempt in ('scripts/archive/', 'experiments/', 'dds_transport.py'):
        assert must_exempt in exempt, must_exempt
    for must_not in ('scripts/demo/start.py', 'scripts/episode_runner.py',
                     'src/agc_task/', 'tests/check_fire_control_lifecycle.py'):
        assert must_not not in exempt, '豁免被放宽到活代码：%s' % must_not


def test_guard_is_in_default_smoke(check):
    """闸门必须在默认冒烟里，否则"每次提交跑一遍"就是空话。"""
    smoke = (ROOT / 'tests' / 'run_smoke.py').read_text(encoding='utf-8')
    assert 'check_dds_contract.py' in smoke, 'DDS 契约闸门未接入默认冒烟'
    assert "('dds'," in smoke, '冒烟里缺少 dds 组'


def test_full_regression_entry_is_real(check):
    """整链回归入口不得是空壳：必须有场景、有 report 判据、有 INFRA 分类。"""
    path = ROOT / 'tests' / 'run_full_regression.py'
    src = path.read_text(encoding='utf-8')
    assert 'SCENES' in src and src.count("'s") >= 3, '场景表为空或不足 3 个'
    assert 'report.json' in src, '判据必须取 episode_runner 的 report.json'
    assert 'INFRA' in src, '必须区分 infra 与能力失败'
    assert 'expected_terminal' in src or 'expected' in src, '必须按期望终态判定'
    # 入口必须能被 --list 静态列举（不在列举时启动仿真）
    import subprocess
    r = subprocess.run([sys.executable, str(path), '--list'],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    for scene in ('s01_', 's08_', 's10_'):
        assert scene in r.stdout, '缺少场景 %s' % scene


def test_n3_matrix_entry_is_real():
    """回归矩阵入口必须覆盖四类要求，且负例断言不得是只看终态。"""
    import importlib.util
    path = ROOT / 'tests' / 'run_regression_matrix.py'
    spec = importlib.util.spec_from_file_location('n3m', str(path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)

    cats = [c for c, *_ in m.MATRIX]
    # 正向三格必须一直在（它们有有效承载者）。
    for must in ('static-normal', 'dynamic-normal-linear', 'loss-reacquire'):
        assert must in cats, '缺少类别 %s（回归矩阵四类要求）' % must
    # 负例格**当前无承载者**，必须**不在**矩阵里；若被加回，须同时恢复
    # `scenario_carriers.yaml` 的 no_target 承载者与 scenarios.yaml 的 supported 标注。
    assert 'no-target-negative' not in cats, (
        'no-target-negative 当前无有效承载者，不得留在矩阵里冒充有效负例；'
        '恢复须先给 gt_adapter 加可致盲开关（见 scenario_carriers.yaml 的 no_target.reason）')

    # 负例断言逻辑本身仍须保留且不得只看终态（它是恢复该负例后的判据模板）
    fake_ok = {'terminal_state': 'TRACKING_SUCCESS', 'reason_code': 'tracking_milestone',
               'visibility_metrics': {'visibility_rate': 0.9},
               'mission_fco_fixed_budget_v1': {'missions': [{'fco_exposure_s': 4.0}]}}
    probs = m._assert_negative({}, fake_ok)
    assert len(probs) >= 3, '负例断言过弱：假成功只被判出 %d 个问题' % len(probs)

    # 证据缺失时不得算通过
    assert m._assert_negative({}, None), '拿不到 summary 时应判不通过，不能默认放行'


def test_perception_axis_and_no_target_scene_are_retired(check):
    """`perception` 场景轴 + `s17` 无目标负例已于 2026-11-06 整体退役（用户裁定）。

 原 `test_n3_negative_scene_is_registered` 守护的是"诚实标注 s17 不可用"；本次
 「彻底删」后改为守护**不复活**：场景表不得再声明 `perception` 轴、承载者表
 不得再有该轴、`s17` 场景号不得回来。完整清退台账与闸门见
 `scripts/tests/test_retirement_ledger.py` 与治理规范。
    """
    import yaml
    with open(ROOT / 'src/agc_task/config/scenarios.yaml', encoding='utf-8') as f:
        scenes = yaml.safe_load(f)['scenes']
    assert 's17_static_none_no_target_timeout' not in scenes, (
        's17 无目标负例已随 perception 轴退役，不得重新登记')
    for name, sc in scenes.items():
        assert 'perception' not in (sc.get('axes') or {}), (
            '场景 %s 仍声明已退役的 perception 轴' % name)

    with open(ROOT / 'src/agc_task/config/scenario_carriers.yaml', encoding='utf-8') as f:
        car = yaml.safe_load(f)['axes']
    assert 'perception' not in car, 'scenario_carriers.yaml 仍登记已退役的 perception 轴'


def test_vision_localization_path_is_retired():
    """视觉定位路径已于 2026-11-04 退役：不得再被任何活跃代码/配置重新引入。

 用户裁定：项目不做目标识别/追踪，目标位置**始终由真值给出**（ADR-0009 (a2)）。
 本测试是**防回归闸门**——退役后若有人把 `vision_target` / `camera_tf` / `perception_path`
 或 vision 专属 launch 参数加回来，这里立刻失败。
    """
    forbidden_files = [
        ROOT / 'src' / 'agc_perception' / 'src' / 'vision_target.cpp',
        ROOT / 'src' / 'agc_perception' / 'src' / 'camera_tf.cpp',
        ROOT / 'scripts' / 'vision' / 'vision_detector.py',
    ]
    for f in forbidden_files:
        assert not f.exists(), '视觉定位路径已退役，但文件仍在：%s' % f

    # launch 侧：三个 vision 参数不得复活
    w6 = (ROOT / 'src' / 'agc_task' / 'launch' / 'main.launch.py').read_text(encoding='utf-8')
    for arg in ('perception_path', 'vision_detector', 'detector_backend',
                'target_plane_z_m', 'vision_model_id'):
        assert ("'%s', default_value=" % arg) not in w6, \
            'main.launch.py 仍在声明已退役的参数 %s' % arg

    # 矩阵：vision 臂必须已删除（没有"感知代价臂"了）
    import importlib.util
    spec = importlib.util.spec_from_file_location('n3m_retired', str(ROOT / 'tests' / 'run_regression_matrix.py'))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    kinds = [k for *_x, k in m.MATRIX]
    assert 'vision' not in kinds, '回归矩阵里仍有 vision 臂（该路径已退役）'


def test_episode_runner_records_perception_path():
    """report 仍记录感知路径键，但**值固定**为 truth / none（schema 不漂移）。

 视觉退役后这两个键保留是为了让新旧 run 可直接对比（删键会让 schema 漂移）；
 但值不再由 launch 参数驱动，因此不得再出现 `perception_path=vision` 一类的动态透传。
    """
    src = (ROOT / 'scripts' / 'episode_runner.py').read_text(encoding='utf-8')
    assert "'perception_path': 'truth'" in src
    assert "'detector_backend': 'none'" in src
    # 已退役的透传参数不得复活
    assert '--perception-path' not in src
    assert 'vision_detector:=true' not in src
