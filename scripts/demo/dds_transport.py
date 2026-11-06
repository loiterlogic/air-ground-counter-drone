#!/usr/bin/env python3
"""DDS 传输与发现范围选择（唯一决定点，2026-11-04 新增）。

**为什么需要它**：原先"铁律"要求 `ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST`，该做法隐含
一个未写出的前提——**`lo` 带 `IFF_MULTICAST`**。本机 WSL2 内核上 `lo` 只有 `UP|LOOPBACK`
（`/sys/class/net/lo/flags == 0x9`），于是：

* `LOCALHOST` 让 Fast DDS 把发现绑到 `lo` 且往 `224.0.0.1` 发包；`lo` 无组播能力 →
 **无论用哪种传输都零送达**（实测 `SHM` / `UDPv4` / 默认三组全 0）；
* `SUBNET` + 默认传输 → 发现成功（`get_subscription_count` 会到 1）、但 **UDP 数据面
 零送达**（`0x9` 无组播时 `IP_MULTICAST_LOOP` 的组播包不被回环反射）；
* `SUBNET` + `FASTDDS_BUILTIN_TRANSPORTS=SHM` → **238/238 条送达**，唯一可用组合。

补充（2026-11-04 二次实测，纠正"LOCALHOST 彻底不能用"的说法）：`LOCALHOST` 在本机是
**按拓扑不可靠**，不是恒废——1 发布进程 ↔ 1 订阅进程（也就是 `test_run_logger_mission_fco`
的形状）稳定零送达；而 1 订阅 ↔ N≥2 发布偶能通（实测 2/2、5–6/6）。也就是说"探一下能不能通"
这种自检本身就会骗人，**必须用 1:1 拓扑**探。本模块因此不依赖"试探性发一条看通没通"，
只用可核验的内核标志做判据。

所以"必须 LOCALHOST"在本机是**不可依赖**的。本模块把选择依据从"信仰"改成"探测"：

 * 显式覆盖（`AGC_DDS_TRANSPORT_POLICY`）优先——给 A/B 与排障留一个确定口子；
 * 否则按**探测到的能力**选：`lo` 有组播 → `LOCALHOST` + 默认传输（原生 Linux 的既有
 行为**完全不变**）；`lo` 无组播 → `SUBNET` + `SHM`（本机唯一可用）。

刻意**不**用 `FASTDDS_BUILTIN_TRANSPORTS=UDPv4` 当本机修复：实测零送达，且项目已有
"UDPv4 不是修复"的记录。

`SHM` 的边界：只在**同主机**多进程间有效，跨机器仍须 UDP。故本模块只在探测到 `lo` 无
组播时才选 `SHM`；反过来， worker 那种"必须关 SHM 防跨 worker 互发现"的场景，请用
显式覆盖把它钉死（见 `episode_runner.py`）。

调用方：`run_demo.sh`（导出主流程环境）、`scripts/episode_runner.py`（launch 环境）、
`src/agc_task/test/test_run_logger_mission_fco.py`（发布/订阅两侧一致）。
"""

import os

# 策略取值：auto（按探测）/ localhost-udp / subnet-shm / subnet-udp / 自定义 dict 不走这里
POLICIES = ('auto', 'localhost-udp', 'subnet-shm', 'subnet-udp')

ENV_POLICY = 'AGC_DDS_TRANSPORT_POLICY'

LO_FLAGS = '/sys/class/net/lo/flags'
IFF_MULTICAST = 0x1000


def lo_flags(path=LO_FLAGS):
    """读 `lo` 的接口标志位；读不到返回 None（不等于"无组播"，只表示未知）。"""
    try:
        with open(path, 'r') as f:
            return int((f.read() or '').strip(), 16)
    except (OSError, ValueError):
        return None


def lo_has_multicast(flags=None):
    """`lo` 是否具备组播能力（`IFF_MULTICAST`）。未知按 False 处理（保守）。"""
    if flags is None:
        flags = lo_flags()
    if flags is None:
        return False
    return bool(flags & IFF_MULTICAST)


# 策略 → 要注入的环境变量。值为 None 表示**删除**该变量（继承 rmw 默认）。
#
# `subnet-shm` 是**本机唯一可用**组合（2026-11-04 实测：SUBNET+默认/UDPv4 均零送达，
# SUBNET+SHM 238/238）。`localhost-udp` 保留为 `lo` 有组播时的既有行为（原生 Linux）。
_POLICY_ENV = {
    'localhost-udp': {
        'ROS_AUTOMATIC_DISCOVERY_RANGE': 'LOCALHOST',
        'FASTDDS_BUILTIN_TRANSPORTS': None,   # 不干预：与历史行为一致
    },
    'subnet-shm': {
        'ROS_AUTOMATIC_DISCOVERY_RANGE': 'SUBNET',
        'FASTDDS_BUILTIN_TRANSPORTS': 'SHM',
    },
    'subnet-udp': {
        'ROS_AUTOMATIC_DISCOVERY_RANGE': 'SUBNET',
        'FASTDDS_BUILTIN_TRANSPORTS': None,
    },
}


def select(flags=None):
    """按探测结果返回策略名（`auto` 已解析成具体策略）。

 ``flags`` 仅供测试注入；生产走 `/sys/class/net/lo/flags`。
    """
    return 'localhost-udp' if lo_has_multicast(flags) else 'subnet-shm'


def resolve(policy=None, flags=None):
    """把策略（含 `auto`）解析成具体策略名，并做合法性校验。"""
    policy = (policy or os.environ.get(ENV_POLICY) or 'auto').strip().lower()
    if policy == 'auto':
        return select(flags)
    if policy not in POLICIES:
        raise ValueError('未知 DDS 传输策略 %r（可用：%s；来自 %s）'
                         % (policy, ' | '.join(POLICIES), ENV_POLICY))
    return policy


def env_for(policy=None, flags=None):
    """返回要注入的环境 dict（值 None = 需从环境中删除）。

 供 shell（`run_demo.sh`）与 Python（`episode_runner` / 测试）共用，
 保证"谁选都一样"。
    """
    return dict(_POLICY_ENV[resolve(policy, flags)])


def apply(target=None, policy=None, flags=None):
    """把选择结果**就地**写入给定环境 dict（默认 `os.environ`）。返回策略名。"""
    resolved = resolve(policy, flags)
    env = os.environ if target is None else target
    for key, value in _POLICY_ENV[resolved].items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    return resolved


def describe(policy=None, flags=None):
    """人类可读摘要（用于启动日志 / doctor）。"""
    resolved = resolve(policy, flags)
    env = _POLICY_ENV[resolved]
    if flags is None:
        flags = lo_flags()
    mc = 'unknown' if flags is None else ('yes' if flags & IFF_MULTICAST else 'no')
    transport = env.get('FASTDDS_BUILTIN_TRANSPORTS') or 'default'
    return ('dds policy=%s (lo multicast=%s, flags=%s) -> '
            'ROS_AUTOMATIC_DISCOVERY_RANGE=%s FASTDDS_BUILTIN_TRANSPORTS=%s'
            % (resolved, mc, '?' if flags is None else hex(flags),
               env.get('ROS_AUTOMATIC_DISCOVERY_RANGE'), transport))
