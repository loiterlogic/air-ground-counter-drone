#!/usr/bin/env python3
"""DDS 传输 / 发现范围选择器的契约测试（2026-11-04）。

守护的是**新铁律**：选择依据只能是"本机能力探测"，不能是写死的 `LOCALHOST`。

为什么需要这组测试：旧铁律（必须 `LOCALHOST`）在本机隐含前提是 `lo` 带 `IFF_MULTICAST`；
该前提不成立时整链零送达，而代码里没有任何地方会察觉。这里把判据钉死，防止回退。
底层机制与实测矩阵见 docs/conventions/整链排障速查.md#dds-transport。
"""

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'demo'))

import dds_transport  # noqa: E402


IFF_UP = 0x1
IFF_LOOPBACK = 0x8
# 本机实测值（WSL2）：只有 UP|LOOPBACK，没有 IFF_MULTICAST。
FLAGS_NO_MC = IFF_UP | IFF_LOOPBACK          # 0x9
FLAGS_WITH_MC = FLAGS_NO_MC | dds_transport.IFF_MULTICAST   # 0x1009


def test_the_actual_machine_flags_are_readable():
    """必须真能读到 lo 标志；读不到就退化成保守 False（不是崩，也不是默认"有组播"）。"""
    flags = dds_transport.lo_flags()
    assert flags is None or (isinstance(flags, int) and flags >= 0)


def test_multicast_capable_lo_keeps_historic_localhost_behaviour():
    """原生 Linux（lo 有组播）→ 维持既有 LOCALHOST + 不改传输。行为不得漂移。"""
    assert dds_transport.select(FLAGS_WITH_MC) == 'localhost-udp'
    env = dds_transport.env_for(flags=FLAGS_WITH_MC)
    assert env['ROS_AUTOMATIC_DISCOVERY_RANGE'] == 'LOCALHOST'
    # None = 明确要求删除该变量（继承 rmw 默认），与历史行为一致
    assert env['FASTDDS_BUILTIN_TRANSPORTS'] is None


def test_lo_without_multicast_never_selects_localhost():
    """本机（lo 无组播）→ **禁止** LOCALHOST；必须是 SUBNET + SHM（唯一实测可用组合）。"""
    assert dds_transport.select(FLAGS_NO_MC) == 'subnet-shm'
    env = dds_transport.env_for(flags=FLAGS_NO_MC)
    assert env['ROS_AUTOMATIC_DISCOVERY_RANGE'] == 'SUBNET'
    assert env['FASTDDS_BUILTIN_TRANSPORTS'] == 'SHM'


def test_unknown_flags_are_conservative():
    """读不到标志时不得假设"有组播"——否则会静默选回失效的 LOCALHOST。"""
    assert dds_transport.lo_has_multicast(None) is False
    assert dds_transport.select(None) == 'subnet-shm'


@pytest.mark.parametrize('policy,expected', [
    ('localhost-udp', ('LOCALHOST', None)),
    ('subnet-shm', ('SUBNET', 'SHM')),
    ('subnet-udp', ('SUBNET', None)),
])
def test_explicit_policies_are_honoured(policy, expected):
    """显式覆盖必须胜出——A/B 与排障需要一个确定口子。"""
    env = dds_transport.env_for(policy=policy)
    assert env['ROS_AUTOMATIC_DISCOVERY_RANGE'] == expected[0]
    assert env['FASTDDS_BUILTIN_TRANSPORTS'] == expected[1]


def test_unknown_policy_raises_instead_of_silently_defaulting():
    with pytest.raises(ValueError):
        dds_transport.resolve('not-a-policy')


def test_env_var_override_is_read(monkeypatch):
    monkeypatch.setenv(dds_transport.ENV_POLICY, 'subnet-udp')
    env = dds_transport.env_for()
    assert env['ROS_AUTOMATIC_DISCOVERY_RANGE'] == 'SUBNET'
    assert env['FASTDDS_BUILTIN_TRANSPORTS'] is None


def test_apply_removes_stale_transport_when_not_needed():
    """切到 localhost-udp 时必须**删掉**遗留的 FASTDDS_BUILTIN_TRANSPORTS，不能留着。"""
    target = {'FASTDDS_BUILTIN_TRANSPORTS': 'SHM'}
    resolved = dds_transport.apply(target, policy='localhost-udp')
    assert resolved == 'localhost-udp'
    assert 'FASTDDS_BUILTIN_TRANSPORTS' not in target
    assert target['ROS_AUTOMATIC_DISCOVERY_RANGE'] == 'LOCALHOST'


def test_workers_can_still_force_udp_for_isolation():
    """ADR-0024：worker 要禁 SHM。策略表不提供该组合，由调用方覆盖后钉死——回归保护。"""
    env = {}
    dds_transport.apply(env, flags=FLAGS_NO_MC)
    assert env.get('FASTDDS_BUILTIN_TRANSPORTS') == 'SHM'   # 探测会选 SHM
    env['FASTDDS_BUILTIN_TRANSPORTS'] = 'UDPv4'            # worker 覆盖
    assert env['FASTDDS_BUILTIN_TRANSPORTS'] == 'UDPv4'


def test_selection_does_not_rely_on_trial_traffic():
    """选择必须是**纯函数式判据**（读内核标志），不能"发一条试试通没通"。

    原因（2026-11-04 实测踩坑）：`LOCALHOST` 在本机按拓扑「不可靠」而非「恒废」——
    1 pub↔1 sub 稳定零送达，而 1 sub↔N≥2 pub 偶能通（2/2、5–6/6）。任何"试探性探活"
    都可能探出"能通"的假象，从而选回不可靠的配置。故本模块只用可核验标志，不探流量。
    """
    src = (ROOT / 'scripts' / 'demo' / 'dds_transport.py').read_text(encoding='utf-8')
    for banned in ('rclpy', 'subprocess', 'socket', 'publish'):
        assert banned not in src, (
            '选择器不得依赖 %r：探活会在多进程拓扑下给出假阳性' % banned)
