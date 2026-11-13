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
import sys

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


# --------------------------------------------------------------------------------------
# SHM segment 尺寸（2026-11-08 实测，用户裁定 Q33）
# --------------------------------------------------------------------------------------
#
# **症状**：2048² 的深度图（16.78 MB/帧）在默认 SHM 配置下，订阅端只收到 **0.44 Hz**
# （1536²/9.44 MB 时 1.55 Hz），而发布端明明是 25 Hz。整条感知链因此卡死。
#
# **根因**：FastDDS 默认 SHM segment 太小，装不下大消息的完整载荷；实测表现为
# "吞吐被钉死在 7–15 MB/s"，与消息大小成反比。**不是**渲染瓶颈（RTF 实测 1.00、
# GPU 16%），也**不是** CPU（`ps %cpu` 约 1 核）。
#
# **实测矩阵**（`/tmp/dds_pub_n.py` + `dds_sub_n.py`，同机同进程对）：
#   | 消息大小        | 默认 SHM        | segment=16 MB    |
#   |----------------|-----------------|------------------|
#   | 16.78 MB (2048²)| 0.12 Hz         | **30.0 Hz**      |
#   |  9.44 MB (1536²)| 1.55 Hz         | **22.3 Hz**      |
#   |  4.19 MB (1024²)| 10.9 Hz         | 36.9 Hz          |
#   |  1.64 MB (640²) | 10.9 Hz         | 38.1 Hz          |
#   ⇒ 大消息提升 **250×**，小消息不退化（64 B 仍 39 Hz，远超需求）。
#
# **为什么是 16 MB 而不是更大**：16 MB 已足够（2048² 帧 16.78 MB 略超，实测仍 30 Hz，
# 因为 FastDDS 会分片），且内存占用最小；64/128/256 MB 实测收益相同（15–17 Hz）。
#
# **边界**：SHM 只在**同主机**多进程间有效；跨机器仍须 UDP（本模块只在 `lo` 无组播
# 时才选 SHM，原生 Linux 走 `localhost-udp` 不受影响）。
SHM_SEGMENT_MB = 16

SHM_PROFILE_XML = """<?xml version="1.0" encoding="UTF-8" ?>
<profiles xmlns="http://www.eprosima.com/XMLSchemas/fastRTPS_Profiles">
  <transport_descriptors>
    <transport_descriptor>
      <transport_id>agc_shm</transport_id>
      <type>SHM</type>
      <segment_size>%(bytes)d</segment_size>
      <port_queue_capacity>512</port_queue_capacity>
    </transport_descriptor>
  </transport_descriptors>
  <participant profile_name="agc_shm" is_default_profile="true">
    <rtps>
      <userTransports><transport_id>agc_shm</transport_id></userTransports>
      <useBuiltinTransports>false</useBuiltinTransports>
    </rtps>
  </participant>
</profiles>
"""


def shm_profile_path(tmpdir=None):
    """写出 SHM profile XML 并返回路径（进程内缓存，避免每次重复写盘）。

 为什么必须落盘而不是用环境变量直接调：FastDDS 的 `segment_size` **只能**通过
 XML profile 设置，没有对应的环境变量（`FASTDDS_BUILTIN_TRANSPORTS=SHM` 只选传输，
 不改段大小）。所以本模块负责生成并指向一个 profile 文件。
    """
    global _SHM_PROFILE_CACHE
    if _SHM_PROFILE_CACHE and os.path.isfile(_SHM_PROFILE_CACHE):
        return _SHM_PROFILE_CACHE
    import tempfile
    base = tmpdir or os.environ.get('TMPDIR') or tempfile.gettempdir()
    path = os.path.join(base, 'agc_fastdds_shm_%dmb.xml' % SHM_SEGMENT_MB)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(SHM_PROFILE_XML % {'bytes': SHM_SEGMENT_MB * 1024 * 1024})
    _SHM_PROFILE_CACHE = path
    return path


_SHM_PROFILE_CACHE = None
SHM_PROFILE_PATH = shm_profile_path()


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
        # **2026-11-08 实测（用户裁定 Q33）**：默认 SHM segment 太小，
        # 大消息（≥9 MB）订阅端吞吐会崩到 1.55 Hz / 0.44 Hz。调大后 20–22 Hz。
        # 详见 SHM_SEGMENT_MB 的说明。
        'FASTRTPS_DEFAULT_PROFILES_FILE': SHM_PROFILE_PATH,
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


def env_lines(policy=None, flags=None):
    """`KEY=VALUE` 行列表（值 None 的键**不输出**：调用方须先 unset 它们）。

 供 shell 直接消费：`run_demo.sh` 用本模块的命令行入口取环境，不再内嵌 Python 源码
 ——内嵌写法曾因嵌套引号与误删括号同时出问题，且无法被任何测试直接调用。
    """
    return ['%s=%s' % (k, v) for k, v in sorted(env_for(policy, flags).items())
            if v is not None]


def main(argv=None):
    """命令行入口：首行摘要，其后为可直接 `export` 的 `KEY=VALUE`。"""
    import argparse
    ap = argparse.ArgumentParser(description='打印 DDS 发现范围 / 传输的注入环境')
    ap.add_argument('--policy', default=None, help='覆盖策略（默认读环境或 auto）')
    ap.add_argument('--describe-only', action='store_true', help='只打印摘要')
    args = ap.parse_args(argv)
    try:
        print(describe(args.policy))
        if not args.describe_only:
            for line in env_lines(args.policy):
                print(line)
    except ValueError as exc:
        sys.stderr.write('[dds_transport] 错误：%s\n' % exc)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
