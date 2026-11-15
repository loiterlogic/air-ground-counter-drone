#!/usr/bin/env python3
"""地面安全层**整链三档**取证：`PASS → SLOW → STOP_COLLISION`（`backend:=full`）。

## 判据来自安全层自己，不从速度反推

改造前的版本用"速度变小了"判"安全层介入了" —— 那是**归因错误**：安全层限速与命令源
本来就在减速，在 `cmd_vel` 上长得一模一样。本脚本只读
[`/agc/ground/safety_status`](../docs/adr/0045-ground-safety-layer-self-owned.md#top)
（`std_msgs/String`，JSON 心跳）里的 `state`，并且要求**顺序**出现：
`PASS`（起点在安全带宽外）→ `SLOW`（进入 `d_collision..d_safety` 带）→
`STOP_COLLISION`（进入 `d_emergency..d_collision` 带或制动扫掠撞格）。

## 三件事必须分开报（否则失败时会误判成"安全层坏了"）

1. **场景几何是否成立** —— 先跑 `tests/check_safety_scene_geometry.py`（纯静态、秒级）。
   几何不成立时本脚本**直接拒绝**（infra），因为那时"全程 PASS"是**正确行为**，
   不是安全层的缺陷。
2. **地图里到底有没有那根障碍** —— 逐拍的 `d_min_m` 与地图占据格数。
   `occupied=0` 说明感知没画出来（相机 / 资源争抢），与"安全层判错"是两回事。
3. **安全层有没有按顺序定档** —— 这才是本脚本的**唯一**断言。

## 依赖

- `--scene` 只接受**已登记且几何已核查**的场景（默认 `s19_static_static_safety_tiers`）；
- 须在整链运行中执行（独占仿真）：
  `ros2 launch agc_task main.launch.py backend:=full scene:=s19_static_static_safety_tiers …`
- 本脚本**自带**几何闸门；闸门不过直接返回 2，不消耗一次仿真。

退出码：0 = 三档顺序成立；1 = 断言不成立（含 TIMEOUT，**超时也算失败**）；2 = 基础设施 / 几何前提不满足。
"""

import argparse
import json
import math
import os
import subprocess
import sys
import time
from datetime import datetime

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy

from agc_msgs.msg import AgcTaskState
from geometry_msgs.msg import TwistStamped
from nav_msgs.msg import OccupancyGrid, Odometry
from std_msgs.msg import String
from std_srvs.srv import Trigger

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import checklib  # noqa: E402,F401

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
DEFAULT_SCENE = 's19_static_static_safety_tiers'
TIER_ORDER = ('PASS', 'SLOW', 'STOP_COLLISION')


class SafetyChecker(Node):
    """逐拍采：安全层档位 / 净空 / 命令与输出 / 车真值 / 任务状态 / 地图占据数。"""

    def __init__(self):
        super().__init__('safety_tiers_check')
        latched = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                             reliability=ReliabilityPolicy.RELIABLE)
        self.tier = ''
        self.safety = {}
        self.tiers_seen = []          # [(t_monotonic, tier)]
        self.create_subscription(String, '/agc/ground/safety_status', self._on_safety, latched)
        self.v_cmd = self.v_raw = 0.0
        self.create_subscription(TwistStamped, '/agc/ground/cmd_vel', self._on_cmd, 50)
        self.create_subscription(TwistStamped, '/agc/ground/cmd_vel_raw', self._on_raw, 50)
        self.x = self.y = 0.0
        self.create_subscription(Odometry, '/agc/ground/odom', self._on_odom, 50)
        self.state = 0
        self.create_subscription(AgcTaskState, '/agc/task/state', self._on_state, 20)
        self.occupied = None
        self.create_subscription(OccupancyGrid, '/agc/map', self._on_map, latched)
        self.samples = []
        self.cli = self.create_client(Trigger, '/agc/task/start')

    # ---- 回调 ----
    def _on_safety(self, m):
        try:
            d = json.loads(m.data)
        except ValueError:
            return
        self.safety = d
        t = d.get('state')
        if t and t != self.tier:
            self.tier = t
            self.tiers_seen.append((time.monotonic(), t))

    def _on_cmd(self, m):
        self.v_cmd = m.twist.linear.x

    def _on_raw(self, m):
        self.v_raw = m.twist.linear.x

    def _on_odom(self, m):
        self.x = m.pose.pose.position.x
        self.y = m.pose.pose.position.y

    def _on_state(self, m):
        self.state = m.state

    def _on_map(self, m):
        self.occupied = sum(1 for v in m.data if v >= 99)

    # ---- 采样 ----
    def sample(self):
        self.samples.append({
            't': time.monotonic(),
            'tier': self.tier,
            'v_cmd': self.v_cmd, 'v_raw': self.v_raw,
            'x': self.x, 'y': self.y, 'task_state': self.state,
            'd_min_m': self.safety.get('d_min_m'),
            'unknown_ratio': self.safety.get('unknown_ratio'),
            'map_age_s': self.safety.get('map_age_s'),
            'occupied': self.occupied,
        })

    def start_task(self, timeout=20.0):
        if not self.cli.wait_for_service(timeout_sec=timeout):
            return False, '/agc/task/start 不可用'
        fut = self.cli.call_async(Trigger.Request())
        rclpy.spin_until_future_complete(self, fut, timeout_sec=timeout)
        if not fut.done():
            return False, 'start 调用超时'
        r = fut.result()
        return bool(r.success), r.message


def _geometry_ok():
    """先跑纯静态几何闸门；不成立就**拒绝取证**（那时全程 PASS 是正确行为）。"""
    p = subprocess.run([sys.executable,
                        os.path.join(ROOT, 'tests', 'check_safety_scene_geometry.py')],
                       capture_output=True, text=True)
    return p.returncode == 0, ((p.stdout or '') + (p.stderr or ''))[-1500:]


def _tier_sequence(tiers_seen, t0):
    """档位序列：同一档连续重复只记第一次（回退保留 —— 回退本身是证据）。"""
    seq = []
    for t, name in tiers_seen:
        rel = round(t - t0, 2)
        if seq and seq[-1]['tier'] == name:
            continue
        seq.append({'tier': name, 't_rel_s': rel})
    return seq


def _ordered_subsequence(seq):
    """`PASS → SLOW → STOP_COLLISION` 是否按序出现过（允许中间夹别的档位）。"""
    want = list(TIER_ORDER)
    i = 0
    for item in seq:
        if i < len(want) and item['tier'] == want[i]:
            i += 1
    return i == len(want), want[:i]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--scene', default=DEFAULT_SCENE)
    ap.add_argument('--duration', type=float, default=75.0,
                    help='记录时长（s）；须覆盖整条逼近路径（s19 的 t_max_s=60，留余量）')
    ap.add_argument('--warmup', type=float, default=3.0)
    ap.add_argument('--run-id', default=None)
    ap.add_argument('--experiments-root', default=os.path.join(ROOT, 'experiments'))
    ap.add_argument('--skip-geometry-gate', action='store_true',
                    help='跳过几何闸门（**仅**排障用；跳过时产物会如实标注）')
    args = ap.parse_args()

    res = {
        'run_id': args.run_id or (datetime.now().strftime('%Y%m%d-%H%M%S') + '-safety-tiers'),
        'scene': args.scene,
        'scene_geometry_gate': 'skipped' if args.skip_geometry_gate else 'pending',
        'tier_order_required': list(TIER_ORDER),
    }
    if not args.skip_geometry_gate:
        ok, log = _geometry_ok()
        res['scene_geometry_gate'] = 'pass' if ok else 'fail'
        if not ok:
            res['pass'] = False
            res['status'] = 'infra'
            res['error'] = ('场景几何闸门不通过 ⇒ **拒绝取证**：此时"全程 PASS"是安全层的'
                            '正确行为，不是缺陷。先修几何（或换场景），不要去调安全层参数。')
            res['geometry_log_tail'] = log
            _write(args, res)
            print('INFRA：场景几何不成立，拒绝取证')
            print(log)
            return 2

    rclpy.init()
    node = SafetyChecker()
    t_warm = time.monotonic()
    while time.monotonic() - t_warm < args.warmup:
        rclpy.spin_once(node, timeout_sec=0.05)

    start_ok, start_msg = node.start_task()
    # `start` 在任务**已经在跑**时会被门控拒绝（`already_active`）—— 那是正常状态，
    # 不是"任务没起来"。判据改成"本拍任务处于 active 态"，而不是"这次调用成功"。
    already = 'already_active' in (start_msg or '')
    res['start_ok'] = bool(start_ok)
    res['start_already_active'] = already
    res['start_message'] = start_msg
    t0 = time.monotonic()

    while time.monotonic() - t0 < args.duration:
        rclpy.spin_once(node, timeout_sec=0.02)
        node.sample()

    node.destroy_node()
    rclpy.shutdown()

    s = node.samples
    res['samples'] = len(s)
    if not s:
        res['pass'] = False
        res['status'] = 'infra'
        res['error'] = '没有采到任何样本（链路没起 / 话题名错）'
        _write(args, res)
        print('INFRA：没有采到样本')
        return 2

    seq = _tier_sequence(node.tiers_seen, t0)
    ordered, prefix = _ordered_subsequence(seq)
    occupied = [x['occupied'] for x in s if isinstance(x['occupied'], int)]
    gaps = [x['d_min_m'] for x in s if isinstance(x['d_min_m'], (int, float))]
    dmin = min(gaps) if gaps else None

    res.update({
        'tier_sequence': seq,
        'tiers_seen': sorted({x['tier'] for x in s if x['tier']}),
        'ordered_prefix': prefix,
        'tier_order_ok': ordered,
        'map_occupied_min': min(occupied) if occupied else None,
        'map_occupied_max': max(occupied) if occupied else None,
        'd_min_m_min': round(dmin, 3) if dmin is not None else None,
        'v_cmd_max': round(max((x['v_cmd'] for x in s), default=0.0), 3),
        'v_raw_max': round(max((x['v_raw'] for x in s), default=0.0), 3),
        'task_state_final': s[-1]['task_state'],
        'moved_m': round(max((math.hypot(x['x'] - s[0]['x'], x['y'] - s[0]['y']) for x in s),
                             default=0.0), 3),
    })

    # ---- 判据（分开报，失败时才能定位） ----
    problems = []
    # 判据是"窗口内**曾经**处于 active 态"，不是"末拍仍 active"：
    # 本场景 `t_max_s = 60 s`，而记录窗口 110 s ⇒ 任务必然在窗口内到达 `MISSION_FAILED`。
    # 用末拍判会把"任务正常跑完并被时限结算"误报成"任务没起来"（实测踩过）。
    active_states = (1, 2, 3)   # AIR_SEARCH / TARGET_ACQUIRED / GROUND_APPROACH
    active_ticks = sum(1 for x in s if x['task_state'] in active_states)
    res['task_active_ticks'] = active_ticks
    res['task_states_seen'] = sorted({x['task_state'] for x in s})
    if not start_ok and not already and active_ticks == 0:
        problems.append('任务从未进入 active 态：%s（state 序列=%s）'
                        % (start_msg, res['task_states_seen']))
    if active_ticks == 0:
        problems.append('窗口内没有任何 active 拍 ⇒ 车的位移不可能是"任务驱动"的')
    if not occupied or res['map_occupied_max'] == 0:
        problems.append('地图里没有障碍（占据格恒 0）⇒ 感知没画出来，'
                        '这是地图/相机侧的问题，不是安全层判错')
    if not ordered:
        problems.append('档位顺序不成立：需要 %s，实际走到 %s（完整序列见 tier_sequence）'
                        % (' → '.join(TIER_ORDER), ' → '.join(prefix) or '未出现任何档位'))

    # 档位抖动：自研安全层每拍无条件发布，`odom_valid` 抖动会让档位在两态间闪。
    # 这不是"档位顺序"判据的一部分，但**必须报出来** —— 它直接影响"某一档持续了多久"。
    flips = sum(1 for a, b in zip(seq, seq[1:]) if a['tier'] != b['tier'])
    res['tier_flips'] = flips
    res['tier_flips_per_s'] = round(flips / max(1e-6, args.duration), 3)

    res['problems'] = problems
    res['pass'] = not problems
    res['status'] = 'pass' if res['pass'] else 'fail'
    _write(args, res)

    print('\n档位序列：%s' % (' → '.join('%s@%.1fs' % (i['tier'], i['t_rel_s']) for i in seq)
                              or '（空）'))
    print('地图占据格：%s … %s；净空最小 %s m；车位移 %.2f m；active 拍 %s；档位翻转 %s 次'
          % (res['map_occupied_min'], res['map_occupied_max'],
             res['d_min_m_min'], res['moved_m'], res['task_active_ticks'],
             res['tier_flips']))
    for p in problems:
        print('  ✗ %s' % p)
    print('%s（三档整链取证）' % ('PASS' if res['pass'] else 'FAIL'))
    return 0 if res['pass'] else 1


def _write(args, res):
    out_dir = os.path.join(args.experiments_root, 'w5-ground-nav-safety',
                           res['run_id'], 'metrics')
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, 'safety_tiers.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print('写入', path)


if __name__ == '__main__':
    sys.exit(main())
