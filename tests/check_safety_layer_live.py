#!/usr/bin/env python3
"""地面安全层三档 / 失效语义的**活节点**核查（L4，需 ROS 图，**不需仿真**）。

## 为什么存在

`test_safety_policy.cpp` 覆盖的是**纯判定类**（45 条），证明不了"节点真的把输入接对了"：
订阅 QoS 不匹配、`frame_id` 写错、定时器没起、时间基准混用——这些都不会让 gtest 变红。
本脚本把 `ground_safety_filter` 当**黑盒**起真节点，喂真 ROS 消息、读它的
`/agc/ground/safety_status`，因此能在**没有 Gazebo** 的机器上回答"节点接线对不对"。

## 判据（逐条断言，全部来自 ADR-0045 的判定表）

| # | 用例 | 期望状态 | 期望输出 |
|---|---|---|---|
| a | 启动后不喂任何输入 | `STARTUP` | 持续发零速（**不断流**）|
| b | 空地图 + `v=1.0` | `PASS` | `v == 1.0` |
| c | 障碍 3.0 m | `SLOW` | `0 < v < 1.0`（线/角同比例）|
| d | 障碍 1.5 m | `STOP_EMERGENCY` 或 `STOP_COLLISION` | `v == 0` |
| e | 障碍 0.6 m | `STOP_*` | `v == 0` |
| f | 地图停更 > `t_map_timeout` | `MAP_STALE` | `v == 0` |
| g | 任务状态撤回 `IDLE` | `NO_PERMIT` | `v == 0` |
| h | 未知格全图 | 非驱动态 | `v == 0` |

## 为什么必须用**独立 domain**

实测踩过：同 `ROS_DOMAIN_ID` 里若残留一个 `map_adapter`（它用**仿真钟**发地图），
安全层的年龄判据会把两个时基混算，表现为**莫名 `MAP_STALE`**。这不是节点的错，
但会让核查假红。故本脚本强制用一个专用 domain，并在退出时回收它起的节点。

## 用法

    python3 tests/check_safety_layer_live.py            # 退出码 0=PASS
    python3 tests/check_safety_layer_live.py --json

归属：`tests/`（断言行为、退出码语义），分类 `needs_sim`（`import rclpy`）。
但**不启 Gazebo** —— 只起一个 `agc_ground` 节点，秒级完成。
"""

import argparse
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import checklib  # noqa: E402

# 专用 domain：避免读到本机残留仿真节点的**仿真钟**时间戳（见文件头）。
PROBE_DOMAIN = '91'
W = H = 40
RES = 0.5
ORIGIN = -10.0


def _env():
    env = dict(os.environ)
    env['ROS_DOMAIN_ID'] = PROBE_DOMAIN
    env.pop('ROS_LOCALHOST_ONLY', None)   # 它与 SUBNET 发现互斥，会让本脚本收不到消息
    return env


def run_probe(node_proc):
    """在**子进程**里起 rclpy 侧发布/订阅，避免与节点共用同一 executor。"""
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
    from geometry_msgs.msg import TwistStamped
    from nav_msgs.msg import OccupancyGrid, Odometry
    from std_msgs.msg import Bool, String
    from agc_msgs.msg import AgcTaskState

    latched = QoSProfile(
        depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
        reliability=ReliabilityPolicy.RELIABLE)

    rclpy.init()
    n = Node('safety_layer_probe')
    p_map = n.create_publisher(OccupancyGrid, '/agc/map', latched)
    p_valid = n.create_publisher(Bool, '/agc/map/valid', latched)
    p_cmd = n.create_publisher(TwistStamped, '/agc/ground/cmd_vel_raw', 10)
    p_odom = n.create_publisher(Odometry, '/agc/ground/odom', 20)
    p_ovalid = n.create_publisher(Bool, '/agc/ground/odom_valid', 10)
    p_state = n.create_publisher(AgcTaskState, '/agc/task/state', 10)
    status = []
    n.create_subscription(
        String, '/agc/ground/safety_status', lambda m: status.append(m.data), 20)
    cmd_out = []
    n.create_subscription(
        TwistStamped, '/agc/ground/cmd_vel', lambda m: cmd_out.append(m), 50)

    def stamp(m):
        m.header.stamp = n.get_clock().now().to_msg()
        return m

    def publish_map(blocks, unknown_all=False):
        g = OccupancyGrid()
        g.header.frame_id = 'world'
        g.info.resolution = RES
        g.info.width = W
        g.info.height = H
        g.info.origin.position.x = ORIGIN
        g.info.origin.position.y = ORIGIN
        g.data = [-1 if unknown_all else 0] * (W * H)
        if not unknown_all:
            for bx, by in blocks:
                ix = int((bx - ORIGIN) / RES)
                iy = int((by - ORIGIN) / RES)
                if 0 <= ix < W and 0 <= iy < H:
                    g.data[iy * W + ix] = 100
        p_map.publish(stamp(g))
        p_valid.publish(Bool(data=True))

    def publish_odom():
        o = Odometry()
        stamp(o)
        o.pose.pose.orientation.w = 1.0
        p_odom.publish(o)
        p_ovalid.publish(Bool(data=True))

    def publish_state(code):
        s = AgcTaskState()
        stamp(s)
        s.state = code
        s.state_name = 'GROUND_APPROACH' if code == 3 else 'IDLE'
        p_state.publish(s)

    def publish_cmd(v, w):
        c = TwistStamped()
        stamp(c)
        c.header.frame_id = 'car/base_link'
        c.twist.linear.x = float(v)
        c.twist.angular.z = float(w)
        p_cmd.publish(c)

    def spin(secs):
        t0 = time.monotonic()
        while time.monotonic() - t0 < secs:
            rclpy.spin_once(n, timeout_sec=0.02)

    def last():
        for _ in range(40):
            rclpy.spin_once(n, timeout_sec=0.01)
        if not status:
            return {}
        try:
            return json.loads(status[-1])
        except ValueError:
            return {}

    def case(label, blocks, v, w, task=3, secs=1.4, unknown_all=False):
        status.clear()
        t0 = time.monotonic()
        while time.monotonic() - t0 < secs:
            publish_map(blocks, unknown_all)
            publish_odom()
            publish_state(task)
            publish_cmd(v, w)
            rclpy.spin_once(n, timeout_sec=0.02)
        return last()

    res = {}

    # a) 启动零速：在节点已起、但**一个输入都不发**的窗口里统计输出条数
    cmd_out.clear()
    spin(2.0)
    res['a_startup_publishes_zero'] = {
        'msgs': len(cmd_out),
        'nonzero': sum(
            1 for m in cmd_out
            if abs(m.twist.linear.x) > 1e-9 or abs(m.twist.angular.z) > 1e-9),
        'duration_s': 2.0,
    }

    d = case('b', [], 1.0, 0.0)
    res['b_clear_passes'] = d
    d = case('c', [(3.0, 0.0)], 1.0, 0.0)
    res['c_slow'] = d
    d = case('d', [(1.5, 0.0)], 1.0, 0.0)
    res['d_near'] = d
    d = case('e', [(0.6, 0.0)], 1.0, 0.0)
    res['e_close'] = d
    d = case('h', [], 1.0, 0.0, unknown_all=True)
    res['h_all_unknown'] = d

    # f) 地图停更：只发命令/车体/许可，地图用旧的
    status.clear()
    t0 = time.monotonic()
    while time.monotonic() - t0 < 3.0:
        publish_odom()
        publish_state(3)
        publish_cmd(1.0, 0.0)
        rclpy.spin_once(n, timeout_sec=0.02)
    res['f_map_stale'] = last()

    # g) 许可撤回
    d = case('g', [], 1.0, 0.0, task=0)
    res['g_no_permit'] = d

    n.destroy_node()
    rclpy.shutdown()
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--json', type=str, default=None)
    args = ap.parse_args()

    env = _env()
    # **必须**写回本进程环境：rclpy.init() 读的是进程 env，而不是传给子进程的那份。
    # 少这一步会让探针与节点落在不同 domain —— 表现为"节点明明在跑却一条消息都收不到"。
    os.environ['ROS_DOMAIN_ID'] = PROBE_DOMAIN
    os.environ.pop('ROS_LOCALHOST_ONLY', None)
    node = subprocess.Popen(
        ['ros2', 'run', 'agc_ground', 'ground_safety_filter', '--ros-args',
         '-p', 'use_sim_time:=false'],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(4.0)
        if node.poll() is not None:
            print('FAIL：安全层节点启动即退出（exit=%s）' % node.returncode)
            return 2
        res = run_probe(node)
    finally:
        node.terminate()
        try:
            node.wait(timeout=5)
        except subprocess.TimeoutExpired:
            node.kill()

    checks = {}

    a = res.get('a_startup_publishes_zero', {})
    checks['a_startup_publishes_zero'] = (
        a.get('msgs', 0) >= 30 and a.get('nonzero', 1) == 0,
        '2 s 内 %s 条零速（期望 ≥30 @20Hz），非零 %s 条'
        % (a.get('msgs'), a.get('nonzero')))

    b = res.get('b_clear_passes', {})
    checks['b_clear_passes'] = (
        b.get('state') == 'PASS' and abs((b.get('v_out') or 0.0) - 1.0) < 1e-6,
        'state=%s v_out=%s' % (b.get('state'), b.get('v_out')))

    c = res.get('c_slow', {})
    vout = c.get('v_out')
    # 判据分两半，**都不许放松**：
    # ① 障碍落在 collision..safety 带内时状态必须是 SLOW（这条与配置无关，永远成立）；
    # ② 输出**只裁不造**：0 < v_out <= v_raw。
    #    `v_out == v_raw` 是**合法**的 —— 当实测横向逃逸能力贴着要求时，`slowRatioFloor()`
    #    会反解出 1.0，此时 SLOW 不降速（详见 ADR-0045 的「实测证据 E」）。
    #    旧断言写死"必须 < 1.0"，在标定把 ratio 从 0.2 提到下限之后就成了错的期望。
    checks['c_slow'] = (
        c.get('state') == 'SLOW' and vout is not None and 0.0 < vout <= 1.0 + 1e-9,
        'state=%s v_out=%s d_min=%s（SLOW 状态必须成立；裁剪比由逃逸下限决定）'
        % (c.get('state'), vout, c.get('d_min_m')))

    # `d_near`（障碍 1.5 m ⇒ 落在 d_emergency..d_collision 带内）**必须**是 `STOP_EMERGENCY`
    # 或 `STOP_COLLISION`：哪个档由 `cell_epsilon` 膨胀后的净空决定，不是随便哪个 STOP 都行。
    # 这一条是 [ADR-0046](../docs/adr/0046-lateral-escape-capability-narrowing.md#top) (e)
    # 指定的 `STOP_EMERGENCY` 证据形式（整链"逐渐逼近"里它**不该**自然触发）。
    for key in ('d_near', 'e_close'):
        d = res.get(key, {})
        checks[key] = (
            str(d.get('state', '')).startswith('STOP_') and d.get('v_out') == 0,
            'state=%s v_out=%s' % (d.get('state'), d.get('v_out')))

    # 显式登记"这一档的证据形式"：整链不触发是**设计意图**，不是缺口。
    d = res.get('d_near', {})
    checks['d_near_is_emergency_or_collision'] = (
        d.get('state') in ('STOP_EMERGENCY', 'STOP_COLLISION'),
        'state=%s（`STOP_EMERGENCY` 的正确触发条件是"障碍单拍突现于 footprint 内"，'
        '属故障注入；整链"逐渐逼近"里被 `STOP_COLLISION` 的扫掠判据先截住）'
        % d.get('state'))

    f = res.get('f_map_stale', {})
    checks['f_map_stale'] = (
        f.get('state') == 'MAP_STALE' and f.get('v_out') == 0,
        'state=%s v_out=%s' % (f.get('state'), f.get('v_out')))

    g = res.get('g_no_permit', {})
    checks['g_no_permit'] = (
        g.get('state') == 'NO_PERMIT' and g.get('v_out') == 0,
        'state=%s v_out=%s' % (g.get('state'), g.get('v_out')))

    h = res.get('h_all_unknown', {})
    checks['h_all_unknown'] = (
        h.get('state') not in ('PASS', 'SLOW') and h.get('v_out') == 0,
        'state=%s v_out=%s（未知不得当作可通行）' % (h.get('state'), h.get('v_out')))

    failures = [k for k, (ok, _) in checks.items() if not ok]
    for k, (ok, detail) in checks.items():
        print('  %s  %-24s %s' % ('PASS' if ok else 'FAIL', k, detail))

    payload = {'pass': not failures, 'checks': {k: v[0] for k, v in checks.items()},
               'detail': {k: v[1] for k, v in checks.items()}}
    if args.json:
        with open(args.json, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    if failures:
        print('FAIL：%d/%d 项不通过：%s' % (len(failures), len(checks), ', '.join(failures)))
        return 1
    print('PASS：%d/%d 项（安全层活节点三档 + 失效语义）' % (len(checks), len(checks)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
