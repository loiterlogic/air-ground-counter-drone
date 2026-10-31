"""Full-chain seed protocol: production mixer, launch wiring and production GPS RNG.

The C++ harness compiles the *production* SensorGpsSim translation unit with
minimal host stubs; it does not reimplement the RNG.
"""
import importlib.util
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).parents[2]
FIXTURE = Path(__file__).parent / 'fixtures' / 'px4_gps_seed'
PX4_SRC = REPO / 'toolchain/PX4-Autopilot/src/modules/simulation/sensor_gps_sim'
LAUNCH = REPO / 'src/agc_task/launch'

spec = importlib.util.spec_from_file_location(
    'w6_composition', LAUNCH / 'w6_composition.py')
w6c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w6c)


def _build_harness(tmp_path):
    exe = tmp_path / 'gps_seed_harness'
    compiler = shutil.which('g++')
    assert compiler, 'g++ is required for the production GPS RNG test'
    assert (PX4_SRC / 'SensorGpsSim.cpp').is_file()
    cmd = [compiler, '-std=c++17', '-O2',
           '-I', str(FIXTURE / 'stubs'),
           '-I', str(PX4_SRC),
           str(FIXTURE / 'harness_main.cpp'),
           '-o', str(exe)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return exe


def _run(exe, mode, seed, n=8):
    result = subprocess.run([str(exe), mode, seed, str(n)],
                            capture_output=True, text=True)
    return result


def _seq(exe, seed, n=8):
    result = _run(exe, 'seq', seed, n)
    assert result.returncode == 0, result.stdout + result.stderr
    lines = result.stdout.strip().splitlines()
    state = int(lines[0].split('=', 1)[1])
    return state, lines[1:]


def test_mixer_stable_and_domain():
    seeds = [0, 1, 5, 20, 2 ** 32 - 1]
    instances = [0, 1, 3]
    for seed in seeds:
        for inst in instances:
            value = w6c.derive_px4_sim_seed(seed, inst)
            assert 0 <= value <= 2 ** 32 - 1
            assert value == w6c.derive_px4_sim_seed(seed, inst)
    for seed in seeds:
        values = [w6c.derive_px4_sim_seed(seed, i) for i in instances]
        assert len(set(values)) == len(values), (seed, values)
    for inst in instances:
        values = [w6c.derive_px4_sim_seed(s, inst) for s in seeds]
        assert len(set(values)) == len(values), (inst, values)


def test_launch_injects_derived_seeds_and_perception_seed():
    w6 = (LAUNCH / 'w6.launch.py').read_text()
    air = (REPO / 'src/agc_air/launch/air_bringup.launch.py').read_text()
    perception = (REPO / 'src/agc_perception/launch/perception_bringup.launch.py').read_text()

    for inst in (0, 1, 3):
        assert 'derive_px4_sim_seed(seed, %d)' % inst in w6
    assert "AGC_PX4_SIM_SEED" in w6
    assert "'seed': LaunchConfiguration('seed')" in w6
    assert "'seed': seed" in air
    assert "'AGC_PX4_SIM_SEED': seed" in air
    assert "LaunchConfiguration('seed')" in perception
    # only air_perception gets the seed parameter
    assert perception.count("'seed':") == 1
    # P1-1 round-7：air_perception 的 `seed` 是 **std::string** 参数（节点
    # `declare_parameter<std::string>`；perception.yaml 写 `seed: "0"`）。裸 substitution 会先经
    # launch_ros 的 yaml.safe_load 求值 → `"0"` 变 int 0 → 节点抛
    # InvalidParameterTypeException 并 exit -6（实测：air_perception 死亡 → /agc/air/obs 无发布者
    # → air_fusion 无观测 → 目标永不可见）。故必须以 str 类型标注，不得退回裸 substitution。
    assert "'seed': ParameterValue(seed, value_type=str)" in perception


def test_perception_seed_parameter_is_string_typed(tmp_path):
    """P1-1 round-7 回归：air_perception 的 `seed` 求值后**必须是 str**。

    只用源码字符串断言不够——真正决定成败的是 `launch_ros` 求值后的 Python 类型：
    裸 `LaunchConfiguration` 会经 `yaml.safe_load` 变成 **int**，而节点
    `declare_parameter<std::string>("seed", "unseeded")` 要求 string，于是抛
    `InvalidParameterTypeException` 并 exit -6。本测试在**不启动任何进程**的前提下
    真实执行 launch 的参数求值，并同时给出**反向对照**（裸 substitution → int），
    以证明该断言确实能区分修复前后（否则断言会变成恒真）。

    说明：本测试需要 `source /opt/ros/jazzy/setup.bash`（`perception_bringup.launch.py`
    经 `get_package_share_directory('agc_perception')` 解析包路径）。未 source 时
    **skip** 而非 fail——本仓其余 `scripts/tests/` 测试都不依赖 ROS 环境，
    不能因"环境没 source"把正确代码判红。
    """
    import importlib.util as _ilu

    pytest.importorskip('launch')
    from ament_index_python.packages import get_package_share_directory
    try:
        get_package_share_directory('agc_perception')
    except Exception:  # noqa: BLE001 - PackageNotFoundError / EnvironmentError
        pytest.skip('需 source install/setup.bash 才能解析 agc_perception 包路径')

    from launch import LaunchContext
    from launch.substitutions import LaunchConfiguration
    from launch_ros.utilities import evaluate_parameters, normalize_parameters

    launch_py = REPO / 'src/agc_perception/launch/perception_bringup.launch.py'
    spec = _ilu.spec_from_file_location('perception_bringup_under_test', launch_py)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    ld = mod.generate_launch_description()
    ctx = LaunchContext()
    # 先执行 DeclareLaunchArgument 填默认，再覆盖 seed（模拟 w6 传 seed:=0）
    for action in ld.entities:
        if type(action).__name__ == 'DeclareLaunchArgument':
            action.execute(ctx)
    ctx.launch_configurations['seed'] = '0'

    resolved = []
    for action in ld.entities:
        if type(action).__name__ != 'Node':
            continue
        for param in action._Node__parameters:
            if not isinstance(param, dict):
                continue
            for d in evaluate_parameters(ctx, normalize_parameters([param])):
                if isinstance(d, dict) and 'seed' in d:
                    resolved.append(d['seed'])
    assert len(resolved) == 1, '只有 air_perception 应带 seed 参数，实际 %r' % (resolved,)
    assert isinstance(resolved[0], str), (
        'air_perception 的 seed 必须是 str，实际 %r（%s）——会触发节点 '
        'InvalidParameterTypeException' % (resolved[0], type(resolved[0]).__name__))

    # 反向对照：裸 substitution 确实会退化成 int —— 证明上面的断言有区分度
    bare = evaluate_parameters(
        ctx, normalize_parameters([{'seed': LaunchConfiguration('seed')}]))
    assert isinstance(bare[0]['seed'], int), (
        '反向对照失效：裸 substitution 未退化成 int，说明本测试不再能区分修复前后')


def test_manifest_records_seed_protocol(tmp_path):
    obstacles = tmp_path / 'obstacles.yaml'
    obstacles.write_text('obstacles: []\n')
    info = {
        'scene': 's15_static_none_fov_capture',
        'seed': 5,
        'axes': {},
        'entries': {},
        'sc': {},
        'support_status': {},
        'world_obstacles': 'none',
        'sensors_file_name': 'sensors.yaml',
        'obstacles_file_name': 'obstacles.yaml',
        'sensors_file': 'sensors.yaml',
        'obstacles_file': str(obstacles),
        'world_file': 'world.sdf',
        'geometry': {'work_area': {}, 'obstacles': []},
        'geometry_source': 'world_geometry.yaml',
        'geometry_sha256': '0' * 64,
    }
    manifest = w6c.build_manifest('full', info, {}, {})
    protocol = manifest['effective_params']['seed_protocol']
    assert protocol['name'] == 'agc-px4-sim-seed-v1'
    assert protocol['master_seed'] == 5
    assert protocol['px4_sim_seeds'] == {
        'own': w6c.derive_px4_sim_seed(5, 0),
        'intruder': w6c.derive_px4_sim_seed(5, 1),
        'warmup': w6c.derive_px4_sim_seed(5, 3),
    }


@pytest.fixture(scope='module')
def harness(tmp_path_factory):
    return _build_harness(tmp_path_factory.mktemp('px4_gps_seed'))


def test_same_seed_restarts_identically(harness):
    state_a, seq_a = _seq(harness, '1', 12)
    state_b, seq_b = _seq(harness, '1', 12)
    assert state_a == state_b == 1
    assert seq_a == seq_b


def test_different_seeds_differ(harness):
    _, seq_1 = _seq(harness, '1', 12)
    _, seq_5 = _seq(harness, '5', 12)
    _, seq_20 = _seq(harness, '20', 12)
    assert seq_1 != seq_5
    assert seq_1 != seq_20
    assert seq_5 != seq_20


def test_instances_are_private(harness):
    seed = 5
    sequences = []
    for inst in (0, 1, 3):
        _, seq = _seq(harness, str(w6c.derive_px4_sim_seed(seed, inst)), 12)
        sequences.append(seq)
    assert sequences[0] != sequences[1]
    assert sequences[0] != sequences[2]
    assert sequences[1] != sequences[2]


def test_zero_seed_maps_to_fixed_nonzero_state(harness):
    state, seq_zero = _seq(harness, '0', 8)
    assert state == 0x6D2B79F5
    state_literal, seq_literal = _seq(harness, str(0x6D2B79F5), 8)
    assert state_literal == state
    assert seq_zero == seq_literal


def test_unset_seed_is_deterministic_standalone(harness):
    state, seq_unset = _seq(harness, 'UNSET', 8)
    assert state == 1
    state_one, seq_one = _seq(harness, '1', 8)
    assert state_one == 1
    assert seq_unset == seq_one


@pytest.mark.parametrize('bad', ['abc', '-1', '1x', '4294967296'])
def test_invalid_seed_rejected(harness, bad):
    result = _run(harness, 'invalid', bad, 0)
    assert result.returncode == 3
    assert 'REJECTED' in result.stdout


def test_uint32_boundary_accepted(harness):
    state, _ = _seq(harness, '4294967295', 4)
    assert state == 4294967295
