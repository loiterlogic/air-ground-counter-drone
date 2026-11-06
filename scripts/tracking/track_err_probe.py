#!/usr/bin/env python3
"""track_err_probe —— 空中跟踪误差取证（基线收尾）。

定位： baseline closure 的**取证工具**（工具域，ADR-0020），不是控制链的一部分。
它只订阅、只落盘，**不发布任何话题、不写执行口、不读真值**。

## 为什么需要它

`run_logger` 的 summary **没有**跟踪误差字段（它只订阅地面侧话题）。本工具把空中参考与
`/agc/air/odom`（`nav_msgs/Odometry`，PX4 估计）按**仿真时间戳最近邻**配对，算水平位置误差。

## 口径：哪个参考才是"跟踪误差"（本轮修正）

 / 的采集器只订阅 `/agc/air/ref`。那是 `trajectory_tracker.cpp` ⑦ 发布的
**标称 8 字 base_ref**——机体在 standoff 接管后**本来就不在 8 字上**，故量出来的是
"standoff 偏离"（实测 mean≈8 m / p95≈18 m），**不是跟踪误差**，判别力很低。

`trajectory_tracker.cpp` ⑨ 的生效参考裁定是（ / ）：

| `source` | 生效参考 | 对应话题 |
|---|---|---|
| `tracking` | `tracking_ref`（standoff 覆盖） | `/agc/air/tracking_ref` |
| `hold` | 最后有效 `tracking_ref`（冻结） | 仍是 `/agc/air/tracking_ref` 的当前值 |
| `base` | 标称 8 字 `base_ref` | `/agc/air/ref` |

`standoff_follower` 只在**已获目标后**才发 `/agc/air/tracking_ref`（从未获目标时提前 return），
因此"`tracking_ref` 存在且新鲜" ⟺ 生效参考是它（含 hold）。本工具据此定义**主指标**：

```
err_eff  = || ref_eff - odom ||,  ref_eff = tracking_ref（若新鲜）否则 base_ref
err_base = || base_ref  - odom ||   ← 保留，仅作与历史取证的连续性对照
```

`err_base` **不得**表述为跟踪误差（它含 standoff 偏置）。两者都落盘，报告里分别标注。

> **口径声明**：两者都是**派生指标**，不是契约 的跟踪误差口径，也不替代任何既有验收。
> 产物里每个文件都带 `not_a_summary_field: true`。

## 三条设计约束（ 的失败教训）

 的采集器失败于"**等循环结束才写唯一结果**"：被 `run_demo` 回收时 SIGTERM
打断在 `spin_once` 里，JSON 从未落盘。本工具因此：

1. **边采边写**：每 `--flush-period`（默认 2 s）把 json / samples / txt **三者都原子落盘**，
 **任何时刻**都有可用结果（含被 SIGKILL 的情形——最多丢最后一个 flush 周期）；
2. **中断安全**：注册 SIGINT/SIGTERM handler → 置标志 → 主循环优雅收尾并写最终结果；
 且**先写最终结果、再 destroy_node**（ 顺序反了）；
3. **测量窗口与 run 存活解耦**：默认 `--start-on-first-odom`，窗口从**首个 odom 消息**起算
   （两臂同口径），并由 `--duration` 给上界；真实运行里由 harness 在 run 结束后 SIGTERM 收尾，
   故窗口实际 = 任务期，不会因"起早了空转 / 起晚了丢样本"而两臂不等长。

## 产物

```
<out-dir>/track_err.json # 最终统计（中断也会写）
<out-dir>/track_err.samples # 逐拍样本（ts_ns err_eff err_base mode），便于复核
<out-dir>/track_err.txt # 人读摘要
```

## 退出码

- `0`：至少 1 个有效 `err_eff` 配对样本（**有数据**才算成功）
- `3`：0 个配对样本（**不得**当作"误差为 0"；调用方必须显式处理）
- `2`：参数/环境错误
"""

import argparse
import bisect
import json
import os
import signal
import sys
import time

import rclpy
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from rosgraph_msgs.msg import Clock
from std_msgs.msg import String
from trajectory_msgs.msg import MultiDOFJointTrajectory

NOT_SUMMARY_FIELD = True
DISCLAIMER = ('派生指标：参考与 odom 的水平位置差。不是契约 C1 的跟踪误差口径，'
              '也不替代任何既有验收')


def _stamp_ns(msg):
    return int(msg.header.stamp.sec) * 1_000_000_000 + int(msg.header.stamp.nanosec)


def _pos(msg):
    """MultiDOFJointTrajectory → 首点平移 (x, y)。"""
    if not msg.points:
        return None
    tf = msg.points[0].transforms
    if not tf:
        return None
    return (float(tf[0].translation.x), float(tf[0].translation.y))


def nearest_key(keys, ts):
    """有序键表里找与 ts 最近的键（返回 (key, |Δ|)；空表返回 (None, None)）。"""
    if not keys:
        return None, None
    i = bisect.bisect_left(keys, ts)
    best = None
    for j in (i - 1, i):
        if 0 <= j < len(keys):
            d = abs(keys[j] - ts)
            if best is None or d < best[1]:
                best = (keys[j], d)
    return best


def aggregate(errs):
    """误差样本聚合（空列表返回 None —— **不得**当作 0）。"""
    if not errs:
        return None
    xs = sorted(errs)
    n = len(xs)
    return {
        'samples': n,
        'mean': round(sum(xs) / n, 4),
        'p50': round(xs[n // 2], 4),
        'p95': round(xs[max(0, int(n * 0.95) - 1)], 4),
        'max': round(xs[-1], 4),
        'min': round(xs[0], 4),
    }


def pair_one(ts, odom_xy, refs, trefs, ref_keys, tref_keys, max_dt_ns):
    """对单个 odom 求 (err_eff, err_base, mode)。

 `refs` / `trefs` 是 ts_ns → (x, y) 的**映射**；`ref_keys` / `tref_keys` 是它们的有序键表。
    两者分开传（不要用 `sorted(dict)` 现算——每拍排序 O(n log n)，2500 拍会拖垮主循环）。

 mode: 'tracking'（生效参考 = tracking_ref）/ 'base'（生效参考 = 标称 8 字）/ None（无参考）。
    """
    bkey, bdt = nearest_key(ref_keys, ts)
    tkey, tdt = nearest_key(tref_keys, ts)
    base_xy = refs[bkey] if bkey is not None and bdt <= max_dt_ns else None
    tref_xy = trefs[tkey] if tkey is not None and tdt <= max_dt_ns else None
    err_base = None
    if base_xy is not None:
        err_base = ((base_xy[0] - odom_xy[0]) ** 2 + (base_xy[1] - odom_xy[1]) ** 2) ** 0.5
    if tref_xy is not None:
        return (((tref_xy[0] - odom_xy[0]) ** 2 + (tref_xy[1] - odom_xy[1]) ** 2) ** 0.5,
                err_base, 'tracking')
    if base_xy is not None:
        return err_base, err_base, 'base'
    return None, err_base, None


class Probe(Node):
    def __init__(self, args):
        super().__init__('track_err_probe')
        self.args = args
        self.refs = {}          # ts_ns -> (x, y)      标称 8 字 base_ref
        self.trefs = {}         # ts_ns -> (x, y)      生效 tracking_ref（standoff）
        self.odoms = {}         # ts_ns -> (x, y)
        self.paired = set()     # 已配对的 odom ts_ns（防重复计数）
        self.samples = []       # (ts_ns, err_eff, err_base, mode)
        self.ref_msgs = 0
        self.tref_msgs = 0
        self.odom_msgs = 0
        self.status_msgs = 0
        self.status_sources = {}    # tracking_status.source 计数（只作旁证）
        self.first_odom_wall = None
        self.sim_first = None
        self.sim_last = None
        self.started = time.monotonic()
        self.stop_requested = False
        self._ref_keys = []
        self._tref_keys = []

        # 参考 / 位姿：两端均为 reliable，默认 QoS 即可
        self.create_subscription(MultiDOFJointTrajectory, args.ref_topic,
                                 self._on_ref, 10)
        self.create_subscription(MultiDOFJointTrajectory, args.tracking_topic,
                                 self._on_tref, 10)
        self.create_subscription(Odometry, args.odom_topic, self._on_odom, 10)
        # 旁证（只读）：生效参考来源；缺失不影响主指标
        self.create_subscription(String, args.status_topic, self._on_status, 10)
        # `/clock` 由 ros_gz_bridge 发布，档位可能 best_effort → 订阅端用 best_effort 才兼容
        # （reliable 订阅 + best_effort 发布 = 不兼容、收不到）。缺 clock 只影响 sim_window 记录。
        self.create_subscription(Clock, args.clock_topic, self._on_clock,
                                 QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT))

    # -- 回调 --
    def _on_ref(self, msg):
        self.ref_msgs += 1
        p = _pos(msg)
        if p is None:
            return
        self.refs[_stamp_ns(msg)] = p
        self._ref_keys = sorted(self.refs)

    def _on_tref(self, msg):
        self.tref_msgs += 1
        p = _pos(msg)
        if p is None:
            return
        self.trefs[_stamp_ns(msg)] = p
        self._tref_keys = sorted(self.trefs)

    def _on_odom(self, msg):
        self.odom_msgs += 1
        if self.first_odom_wall is None:
            self.first_odom_wall = time.monotonic()
        p = msg.pose.pose.position
        self.odoms[_stamp_ns(msg)] = (float(p.x), float(p.y))

    def _on_status(self, msg):
        self.status_msgs += 1
        try:
            src = json.loads(msg.data).get('source', '')
        except (ValueError, TypeError):
            src = 'unparsed'
        self.status_sources[src] = self.status_sources.get(src, 0) + 1

    def _on_clock(self, m):
        t = float(m.clock.sec) + float(m.clock.nanosec) * 1e-9
        if self.sim_first is None:
            self.sim_first = t
        self.sim_last = t

    # -- 配对 --
    def pair(self):
        max_dt = int(self.args.max_dt_ms * 1e6)
        for ots, op in self.odoms.items():
            if ots in self.paired:
                continue
            err_eff, err_base, mode = pair_one(
                ots, op, self.refs, self.trefs, self._ref_keys, self._tref_keys, max_dt)
            self.paired.add(ots)
            if err_eff is not None:
                self.samples.append((ots, err_eff, err_base, mode))

    # -- 统计快照 --
    def snapshot(self, final=False):
        eff = [s[1] for s in self.samples]
        base = [s[2] for s in self.samples if s[2] is not None]
        modes = {}
        for s in self.samples:
            modes[s[3]] = modes.get(s[3], 0) + 1
        return {
            'tool': 'scripts/tracking/track_err_probe.py',
            'not_a_summary_field': NOT_SUMMARY_FIELD,
            'disclaimer': DISCLAIMER,
            'ref_topic': self.args.ref_topic,
            'tracking_ref_topic': self.args.tracking_topic,
            'odom_topic': self.args.odom_topic,
            'pairing': 'nearest reference within %.1f ms of odom stamp' % self.args.max_dt_ms,
            'primary_metric': 'err_eff_xy_m（生效参考：tracking_ref 新鲜时用它，否则 base_ref）',
            'continuity_metric': 'err_base_xy_m（标称 8 字 base_ref；含 standoff 偏置，非跟踪误差）',
            'duration_s': self.args.duration,
            'elapsed_s': round(time.monotonic() - self.started, 2),
            'window_from': 'first_odom' if self.args.start_on_first_odom else 'process_start',
            'final': bool(final),
            'first_odom_after_s': (None if self.first_odom_wall is None
                                   else round(self.first_odom_wall - self.started, 2)),
            'sim_window': {'start_s': self.sim_first, 'end_s': self.sim_last},
            'ref_msgs': self.ref_msgs,
            'tracking_ref_msgs': self.tref_msgs,
            'odom_msgs': self.odom_msgs,
            'status_msgs': self.status_msgs,
            'status_sources': dict(sorted(self.status_sources.items())),
            'paired_samples': len(self.samples),
            'modes': dict(sorted(modes.items())),
            'err_eff_xy_m': aggregate(eff),
            'err_base_xy_m': aggregate(base),
        }


def _atomic_write(path, text):
    """原子写：先写 .tmp 再 replace，避免中断留下半截文件。"""
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _write(out_dir, doc, samples, final):
    """**三者都落盘**（json / samples / txt），每次 flush 全量原子重写。"""
    _atomic_write(os.path.join(out_dir, 'track_err.json'),
                  json.dumps(doc, indent=1, ensure_ascii=False))
    body = ''.join('%d %.6f %s %s\n' % (ts, eff, '-' if base is None else '%.6f' % base, mode)
                   for ts, eff, base, mode in samples)
    _atomic_write(os.path.join(out_dir, 'track_err.samples'), body)
    eff = doc['err_eff_xy_m']
    base = doc['err_base_xy_m']
    lines = ['ref_msgs=%d tracking_ref_msgs=%d odom_msgs=%d paired=%d final=%s'
             % (doc['ref_msgs'], doc['tracking_ref_msgs'], doc['odom_msgs'],
                doc['paired_samples'], doc['final'])]
    if eff:
        lines.append('err_eff_xy_m(生效参考，**跟踪误差**): '
                     'mean=%(mean)s p50=%(p50)s p95=%(p95)s max=%(max)s n=%(samples)s' % eff)
    else:
        lines.append('err_eff_xy_m: NO_SAMPLES（不得当作 0）')
    if base:
        lines.append('err_base_xy_m(标称 8 字，含 standoff 偏置，非跟踪误差): '
                     'mean=%(mean)s p50=%(p50)s p95=%(p95)s max=%(max)s n=%(samples)s' % base)
    else:
        lines.append('err_base_xy_m: NO_SAMPLES（不得当作 0）')
    _atomic_write(os.path.join(out_dir, 'track_err.txt'), '\n'.join(lines) + '\n')


def main(argv=None):
    ap = argparse.ArgumentParser(description='空中跟踪误差取证（P1-4 baseline closure）')
    ap.add_argument('--ref-topic', default='/agc/air/ref')
    ap.add_argument('--tracking-topic', default='/agc/air/tracking_ref')
    ap.add_argument('--odom-topic', default='/agc/air/odom')
    ap.add_argument('--status-topic', default='/agc/air/tracking_status')
    ap.add_argument('--clock-topic', default='/clock')
    ap.add_argument('--out-dir', required=True)
    ap.add_argument('--duration', type=float, default=50.0,
                    help='测量窗口上界（s）；真实运行由 harness 在 run 结束后 SIGTERM 提前收尾')
    ap.add_argument('--flush-period', type=float, default=2.0)
    ap.add_argument('--max-dt-ms', type=float, default=40.0,
                    help='最近邻配对窗（ms）。40 ms 覆盖 standoff 20 Hz 的半周期，'
                         '且其参考位移上界 ≤0.1 m/tick，不引入可辨伪影')
    ap.add_argument('--wait-timeout', type=float, default=150.0,
                    help='等首个 odom 的上界（s）；超时即 0 样本退出码 3')
    ap.add_argument('--start-on-first-odom', action='store_true', default=True)
    ap.add_argument('--no-start-on-first-odom', dest='start_on_first_odom',
                    action='store_false')
    args, _unknown = ap.parse_known_args(argv)

    if args.duration <= 0 or args.flush_period <= 0:
        print('[track_err_probe] --duration / --flush-period 必须为正', file=sys.stderr)
        return 2

    os.makedirs(args.out_dir, exist_ok=True)
    rclpy.init()
    node = Probe(args)

    # 中断安全：SIGINT/SIGTERM 只置标志，由主循环优雅收尾并写最终结果。
    # 注：rclpy.init 已装自己的 handler；此处**覆盖**为只置标志的实现，
    # 使 spin_once 正常返回而不是抛 ExternalShutdownException。
    def _on_signal(_signum, _frame):
        node.stop_requested = True
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, _on_signal)

    # 先落一次空结果：进程即使立刻被杀，目录里也有"明确 0 样本"的产物，不留悬空。
    _write(args.out_dir, node.snapshot(final=False), node.samples, final=False)

    # 等首个 odom（= 空中节点已激活）→ 窗口起点，两臂同口径
    wait_deadline = time.monotonic() + args.wait_timeout
    while (args.start_on_first_odom and node.first_odom_wall is None
           and not node.stop_requested and time.monotonic() < wait_deadline):
        rclpy.spin_once(node, timeout_sec=0.05)

    deadline = None
    if node.first_odom_wall is not None:
        deadline = node.first_odom_wall + args.duration
    last_flush = time.monotonic()
    while not node.stop_requested:
        if deadline is not None and time.monotonic() >= deadline:
            break
        rclpy.spin_once(node, timeout_sec=0.05)
        if time.monotonic() - last_flush >= args.flush_period:
            last_flush = time.monotonic()
            node.pair()
            _write(args.out_dir, node.snapshot(final=False), node.samples, final=False)

    # 收尾：**先落最终结果，再销毁节点**（顺序很关键—— 反了 → 0 输出）
    node.pair()
    doc = node.snapshot(final=True)
    _write(args.out_dir, doc, node.samples, final=True)
    node.destroy_node()
    rclpy.try_shutdown()
    print(json.dumps(doc, indent=1, ensure_ascii=False))
    return 0 if node.samples else 3


if __name__ == '__main__':
    sys.exit(main())
