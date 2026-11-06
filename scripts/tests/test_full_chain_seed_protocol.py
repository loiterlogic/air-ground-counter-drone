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
    'composition', LAUNCH / 'composition.py')
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


def test_launch_injects_derived_seeds():
    w6 = (LAUNCH / 'main.launch.py').read_text()
    air = (REPO / 'src/agc_air/launch/air_bringup.launch.py').read_text()
    perception = (REPO / 'src/agc_perception/launch/perception_bringup.launch.py').read_text()

    for inst in (0, 1, 3):
        assert 'derive_px4_sim_seed(seed, %d)' % inst in w6
    assert "AGC_PX4_SIM_SEED" in w6
    assert "'seed': seed" in air
    assert "'AGC_PX4_SIM_SEED': seed" in air
    # 2026-11-06：`air_perception` 与 `perception` 场景轴退役，`perception_bringup`
    # 不再接收任何 seed / sensors_file 透传。查**代码形态**（不查退役说明注释），
    # 防止"顺手加回"死参数。
    assert "DeclareLaunchArgument('seed'" not in perception
    assert "DeclareLaunchArgument('sensors_file'" not in perception
    assert "'seed': LaunchConfiguration('seed')" not in perception
    assert "'sensors_file': LaunchConfiguration" not in perception
    assert 'ParameterValue(seed, value_type=str)' not in perception


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
        'obstacles_file_name': 'obstacles.yaml',
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
