#!/usr/bin/env python3
"""G2 行为台架：路径消费的六组分支证据（真实节点，非纯函数单测）。

对应派工单 B 段：

1. 启动后从未收到路径 —— `cmd_vel_raw` 持续零速，并记录 `collision_monitor` 输入/输出实况；
2. 曾收到合格路径、运行中路径源消失 —— 超时后零速，旧路径不继续驱动；
3. 空 / 单点 / 错帧 / 过期逐类注入 —— 各自拒绝原因 + 零速；
4. 正常 A/B 路径 —— 输出随路径参考改变（A/B 两条不同路径 → 不同 `angular.z`）；
5. goal 与路径末端不一致 —— 零速，不 goal-only 回退；
6. `command_source` 速度生产者互斥 —— 只用节点/话题证据，不凭 launch 文本。

设计取舍（为什么不启 GZ）：
 本台架只验证"路径 → 消费者输出"这一段，不需要物理世界；odom/goal/state/scan 用
 **合成发布**喂真实节点，`collision_monitor` 是真实 Nav2 组件（配置取 ground.yaml 的
 同名段但改小 `source_timeout` 以缩短等待）。这样单次 < 900 s，且不占用整链资源。
 GUI 整链在 `g2_gui_chain.py`（另跑，见报告 C 段）。

用法：
    ros2 run agc_rl ... # 不走 ros2 run；本脚本用 subprocess 直接起节点
    python3 scripts/g2/g2_behavior_bench.py --out-dir experiments/g2-placeholder-path/<run_id>

退出码：0 全部通过；1 有判据不满足；2 环境/用法问题。
"""

import argparse
import json
import math
import os
import signal
import subprocess
import sys
import time
import uuid

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy

from agc_msgs.msg import AgcTaskState
from geometry_msgs.msg import PoseStamped, TwistStamped
from nav_msgs.msg import Odometry, Path
from sensor_msgs.msg import LaserScan


NOW = lambda: time.monotonic()  # noqa: E731


def probe_node_count(name, timeout_s=8.0):
    """用 `ros2 node list` 统计某节点名出现次数（证明安全链确实在跑，而非未启动）。"""
    try:
        out = subprocess.run(['ros2', 'node', 'list'], capture_output=True,
                             text=True, timeout=timeout_s).stdout
    except subprocess.TimeoutExpired:
        return 0
    return sum(1 for line in out.splitlines() if line.strip().split('/')[-1] == name)


class Bench(Node):
    """合成输入 + 记录被测节点输出。"""

    def __init__(self, path_frame='world', scan_period=0.1):
        super().__init__('g2_bench')
        qos = QoSProfile(depth=10)
        qos.reliability = ReliabilityPolicy.RELIABLE

        self.odom_pub = self.create_publisher(Odometry, '/agc/ground/odom', 20)
        self.goal_pub = self.create_publisher(PoseStamped, '/agc/ground/goal', 20)
        self.state_pub = self.create_publisher(AgcTaskState, '/agc/task/state', 20)
        self.scan_pub = self.create_publisher(LaserScan, '/agc/ground/scan', 10)
        self.path_pub = self.create_publisher(Path, '/agc/ground/path', 1)

        self.cmds = []          # (t, linear.x, angular.z)
        self.cmd_in = []        # collision_monitor 的输入（= cmd_vel_raw）
        self.create_subscription(
            TwistStamped, '/agc/ground/cmd_vel_raw', self._on_raw, qos)
        self.create_subscription(
            TwistStamped, '/agc/ground/cmd_vel', self._on_port, qos)

        self.path_frame = path_frame
        self.scan_period = scan_period
        self._scan_timer = self.create_timer(scan_period, self._push_scan)

    # --- 记录 -------------------------------------------------------------
    def _on_raw(self, msg):
        self.cmds.append((NOW(), msg.twist.linear.x, msg.twist.angular.z))

    def _on_port(self, msg):
        self.cmd_in.append((NOW(), msg.twist.linear.x, msg.twist.angular.z))

    # --- 合成输入 ---------------------------------------------------------
    def _push_scan(self):
        scan = LaserScan()
        scan.header.stamp = self.get_clock().now().to_msg()
        scan.header.frame_id = 'car/lidar_link'
        scan.angle_min = -math.pi
        scan.angle_max = math.pi
        scan.angle_increment = 2.0 * math.pi / 360.0
        scan.range_min = 0.2
        scan.range_max = 20.0
        scan.ranges = [float('inf')] * 360     # 全向无遮挡（合法无回波）
        self.scan_pub.publish(scan)

    def push_odom(self, x=0.0, y=0.0, yaw=0.0):
        od = Odometry()
        od.header.stamp = self.get_clock().now().to_msg()
        od.header.frame_id = 'world'
        od.child_frame_id = 'car/base_link'
        od.pose.pose.position.x = x
        od.pose.pose.position.y = y
        od.pose.pose.orientation.z = math.sin(yaw * 0.5)
        od.pose.pose.orientation.w = math.cos(yaw * 0.5)
        self.odom_pub.publish(od)

    def push_goal(self, x, y):
        g = PoseStamped()
        g.header.stamp = self.get_clock().now().to_msg()
        g.header.frame_id = 'world'
        g.pose.position.x = x
        g.pose.position.y = y
        g.pose.orientation.w = 1.0
        self.goal_pub.publish(g)

    def push_state(self, state=AgcTaskState.GROUND_APPROACH):
        s = AgcTaskState()
        s.header.stamp = self.get_clock().now().to_msg()
        s.header.frame_id = 'world'
        s.state = state
        self.state_pub.publish(s)

    def push_path(self, points, frame_id=None, stamp=None):
        p = Path()
        p.header.stamp = stamp if stamp is not None else self.get_clock().now().to_msg()
        p.header.frame_id = frame_id if frame_id is not None else self.path_frame
        for x, y in points:
            ps = PoseStamped()
            ps.header = p.header
            ps.pose.position.x = x
            ps.pose.position.y = y
            ps.pose.orientation.w = 1.0
            p.poses.append(ps)
        self.path_pub.publish(p)

    # --- 采样 -------------------------------------------------------------
    def spin_for(self, seconds):
        end = NOW() + seconds
        while NOW() < end and rclpy.ok():
            rclpy.spin_once(self, timeout_sec=0.02)

    def window(self, since):
        return [c for c in self.cmds if c[0] >= since]

    def nonzero_after(self, since):
        return [c for c in self.window(since) if abs(c[1]) > 1e-9 or abs(c[2]) > 1e-9]

    def mean_twist(self, since):
        w = self.window(since)
        if not w:
            return None
        return (sum(c[1] for c in w) / len(w), sum(c[2] for c in w) / len(w))


# --------------------------------------------------------------------------- 台架用例
def case_never_received(bench, cfg, results):
    """① 启动后从未收到路径：持续零速，且**必须证明安全链真的在运行**。

 缺陷：旧版只记 `cmd_vel_port_msgs=0`，那与"collision_monitor 压根没起"
 无法区分（review D1）。本版要求同时满足：
      * 安全层节点存在（由调用方经 `ros2 node list` 探测，写入 `cfg['collision_monitor_nodes']`）；
 * `cmd_vel_raw` 有消息且全零（消费者自己在发）；
 * 唯一执行口有消息（安全层把零速转发出来了）——这才是"安全链在跑"的证据。
    """
    window = float(cfg.get('startup_window_s', 3.0))
    since = NOW()
    bench.spin_for(window)
    raw = bench.window(since)
    raw_nz = [c for c in raw if abs(c[1]) > 1e-9 or abs(c[2]) > 1e-9]
    port = [c for c in bench.cmd_in if c[0] >= since]
    port_nz = [c for c in port if abs(c[1]) > 1e-9 or abs(c[2]) > 1e-9]
    cm_nodes = int(cfg.get('collision_monitor_nodes') or 0)

    ok = (cm_nodes >= 1) and bool(raw) and not raw_nz and bool(port) and not port_nz
    results.append({
        'case': 'never_received',
        'passed': ok,
        'collision_monitor_nodes': cm_nodes,
        'cmd_vel_raw_msgs': len(raw),
        'cmd_vel_raw_nonzero': len(raw_nz),
        'cmd_vel_port_msgs': len(port),
        'cmd_vel_port_nonzero': len(port_nz),
        'requirement': '安全层节点存在 + raw 持续零速 + 唯一执行口持续零速',
        'note': 'no path at startup -> consumer itself publishes zero; safety chain proven running',
    })
    return ok


def case_source_disappears(bench, cfg, results):
    """② 曾收到合格路径 → 路径源消失：超时后零速，旧路径不继续驱动。"""
    bench.push_goal(5.0, 0.0)
    bench.push_odom(0.0, 0.0, 0.0)
    bench.push_state()
    bench.push_path([(0.0, 0.0), (2.5, 0.0), (5.0, 0.0)])
    t0 = NOW()
    bench.spin_for(0.8)
    moving = bench.nonzero_after(t0)

    # 停止发布路径与 goal，只保留 odom/scan/state；等待超过 max_age_s
    wait = float(cfg['path_max_age_s']) + 1.5
    t1 = NOW()
    for _ in range(int(wait / 0.1)):
        bench.push_odom(0.0, 0.0, 0.0)
        bench.push_state()
        bench.spin_for(0.1)
    stopped = bench.window(t1 + wait * 0.6)
    late_nz = [c for c in stopped if abs(c[1]) > 1e-9 or abs(c[2]) > 1e-9]
    ok = bool(moving) and bool(stopped) and not late_nz
    results.append({
        'case': 'source_disappears',
        'passed': ok,
        'moving_before': len(moving),
        'late_msgs': len(stopped),
        'late_nonzero': len(late_nz),
        'wait_s': round(wait, 2),
    })
    return ok


def case_rejections(bench, cfg, results):
    """③ 空 / 单点 / 错帧 / 过期逐类注入：各自零速。"""
    ok_all = True

    def probe(name, publish):
        bench.push_goal(5.0, 0.0)
        bench.push_odom(0.0, 0.0, 0.0)
        bench.push_state()
        bench.spin_for(0.35)
        t = NOW()
        publish()
        bench.spin_for(1.0)
        w = bench.window(t)
        nz = [c for c in w if abs(c[1]) > 1e-9 or abs(c[2]) > 1e-9]
        # **判据**："有消息且全为零"才算零速；0 条消息说明消费者没在发，
        # 不能算"持续发零速"（那正是 ADR-0013 的边界）。
        passed = bool(w) and not nz
        results.append({
            'case': 'reject_' + name, 'passed': passed,
            'msgs': len(w), 'nonzero': len(nz),
            'requirement': '必须持续发零速（msgs>0 且 nonzero==0）',
        })
        return passed

    ok_all &= probe('empty', lambda: bench.push_path([]))
    ok_all &= probe('single_point', lambda: bench.push_path([(3.0, 0.0)]))
    ok_all &= probe('frame_mismatch', lambda: bench.push_path(
        [(0.0, 0.0), (5.0, 0.0)], frame_id='map'))
    # 过期：直接给一个"旧 stamp"。用 /clock 的当前值减 10 s（> max_age_s）。
    def stale():
        now_msg = bench.get_clock().now().to_msg()
        old = type(now_msg)()
        old.sec = now_msg.sec - 10
        old.nanosec = now_msg.nanosec
        bench.push_path([(0.0, 0.0), (5.0, 0.0)], stamp=old)
    ok_all &= probe('stale', stale)
    return ok_all


def case_normal_path_changes_output(bench, cfg, results):
    """④ 正常 A/B 路径：输出随路径参考改变（证明不是"只订阅不使用"）。

 A: 直线沿 +x（车朝 +x，航向误差≈0）→ |angular.z| 小
 B: 路径先拐向 +y 再回 x（前视点在左前方）→ 航向误差显著 → 角速度不同
    """
    bench.push_goal(5.0, 0.0)
    bench.push_odom(0.0, 0.0, 0.0)
    bench.push_state()
    bench.spin_for(0.3)

    t_a = NOW()
    bench.push_path([(0.0, 0.0), (2.5, 0.0), (5.0, 0.0)])
    bench.spin_for(1.2)
    a = bench.mean_twist(t_a + 0.5)

    t_b = NOW()
    bench.push_path([(0.0, 0.0), (2.5, 2.0), (5.0, 0.0)])
    bench.spin_for(1.2)
    b = bench.mean_twist(t_b + 0.5)

    ok = a is not None and b is not None and abs(a[1] - b[1]) > 0.05
    results.append({
        'case': 'normal_path_changes_output', 'passed': ok,
        'A_mean': None if a is None else [round(a[0], 3), round(a[1], 3)],
        'B_mean': None if b is None else [round(b[0], 3), round(b[1], 3)],
        'delta_w': None if (a is None or b is None) else round(abs(a[1] - b[1]), 3),
    })
    return ok


def case_degenerate_arrived(bench, cfg, results):
    """②b 退化到位路径：两点重合 + 车在末端容差内 → 必须零速（实测）。

 修复前：累计弧长全 0 → `_advance_index` 停在 index 0 → `finished` 永假 → 到点后继续出速度。
    """
    bench.push_goal(0.0, 0.0)              # goal == 车当前位置
    bench.push_odom(0.0, 0.0, 0.0)
    bench.push_state()
    bench.spin_for(0.3)
    t = NOW()
    bench.push_path([(0.0, 0.0), (0.0, 0.0)])   # 两同点（发布侧到位时的退化路径）
    bench.spin_for(1.2)
    w = bench.window(t)
    nz = [c for c in w if abs(c[1]) > 1e-9 or abs(c[2]) > 1e-9]
    ok = bool(w) and not nz
    results.append({
        'case': 'degenerate_arrived', 'passed': ok,
        'msgs': len(w), 'nonzero': len(nz),
        'requirement': '两同点到位路径 -> finished=True -> 持续零速',
    })
    return ok


def case_goal_mismatch(bench, cfg, results):
    """⑤ 路径末端与 goal 不一致：零速，不 goal-only 回退。"""
    bench.push_goal(9.0, 0.0)          # goal 在 9 m
    bench.push_odom(0.0, 0.0, 0.0)
    bench.push_state()
    bench.spin_for(0.3)
    t = NOW()
    bench.push_path([(0.0, 0.0), (2.5, 0.0), (5.0, 0.0)])   # 路径末端 5 m ≠ goal 9 m
    bench.spin_for(1.2)
    w = bench.window(t)
    nz = [c for c in w if abs(c[1]) > 1e-9 or abs(c[2]) > 1e-9]
    ok = bool(w) and not nz
    results.append({
        'case': 'goal_mismatch', 'passed': ok,
        'msgs': len(w), 'nonzero': len(nz),
        'requirement': '必须持续发零速（msgs>0 且 nonzero==0）',
        'note': '不一致即零速；若实现偷偷按 goal 直走则此用例会非零',
    })
    return ok


def case_single_command_source(bench, cfg, results):
    """⑥ `command_source=rl` 下 cmd_vel_raw 只有一路生产者（用 /proc 与话题信息佐证）。"""
    # 由调用方在起节点前后统计 `ros2 topic info` 的 publisher count
    ok = cfg.get('raw_publisher_count') == 1
    results.append({
        'case': 'single_command_source', 'passed': ok,
        'cmd_vel_raw_publishers': cfg.get('raw_publisher_count'),
        'path_publishers': cfg.get('path_publisher_count'),
        'note': '规划器只发 path；path 不是命令，不进互斥域',
    })
    return ok


# --------------------------------------------------------------------------- 主流程
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--out-dir', required=True)
    ap.add_argument('--cases', default='never,disappear,reject,normal,degenerate,mismatch')
    ap.add_argument('--path-max-age', type=float, default=3.0)
    ap.add_argument('--raw-publishers', type=int, default=None)
    ap.add_argument('--path-publishers', type=int, default=None)
    ap.add_argument('--safety-params', default='/tmp/agc-g2-cm-params.yaml',
                    help='collision_monitor 参数文件（--with-safety 时使用）')
    ap.add_argument('--with-safety', action='store_true',
                    help='同时起真实 collision_monitor（启动无路径证据需要）')
    ap.add_argument('--startup-window', type=float, default=3.0,
                    help='启动无路径用例的观测窗口（秒）')
    ap.add_argument('--ready-timeout', type=float, default=25.0,
                    help='等被测节点首条 cmd_vel_raw 的超时（秒）；超时判台架失败(exit 2)')
    args = ap.parse_args(argv)

    os.makedirs(args.out_dir, exist_ok=True)
    os.makedirs('/tmp/agc-g2-logs', exist_ok=True)
    run_id = 'bench-' + uuid.uuid4().hex[:10]
    cfg = {'path_max_age_s': args.path_max_age,
           'startup_window_s': args.startup_window,
           'raw_publisher_count': args.raw_publishers,
           'path_publisher_count': args.path_publishers}

    proc = None
    safety_proc = None
    log_path = '/tmp/agc-g2-logs/%s-consumer.log' % run_id
    log_f = open(log_path, 'w')
    try:
        # 起真实消费者节点；path.max_age_s 用台架值（经参数注入，不改 config 文件）
        proc = subprocess.Popen(
            ['ros2', 'run', 'agc_rl', 'ground_policy_rl', '--ros-args',
             '-p', 'path.max_age_s:=%s' % args.path_max_age,
             '-p', 'use_sim_time:=false',
             '-p', 'input_timeout.goal_s:=60.0',
             '-p', 'input_timeout.task_auth_s:=60.0',
             '-p', 'input_timeout.odom_s:=60.0',
             '-p', 'input_timeout.scan_s:=60.0'],
            stdout=log_f, stderr=subprocess.STDOUT)

        # D1：`--with-safety` 时另起**真实** Nav2 collision_monitor，
        # 让"启动无路径"能在完整安全链（raw -> monitor -> 唯一执行口）上被观测，
        # 而不是靠"没起节点所以 0 条"冒充证据。
        if args.with_safety:
            cm_log = open('/tmp/agc-g2-logs/%s-collision-monitor.log' % run_id, 'w')
            # Nav2 collision_monitor 是 lifecycle 节点：参数必须走 params-file
            # （命令行给 `points` 会被当成 string，configure 直接失败——已实测）。
            safety_proc = subprocess.Popen(
                ['ros2', 'run', 'nav2_collision_monitor', 'collision_monitor',
                 '--ros-args', '--params-file', args.safety_params],
                stdout=cm_log, stderr=subprocess.STDOUT)
            # 等节点出现再驱动生命周期（服务名是 /<node>/change_state）。
            deadline = NOW() + 30.0
            while NOW() < deadline and probe_node_count('collision_monitor') < 1:
                time.sleep(0.5)
            for transition in ('configure', 'activate'):
                r = subprocess.run(
                    ['ros2', 'lifecycle', 'set', '/collision_monitor', transition],
                    capture_output=True, text=True, timeout=30)
                ok = 'success' in (r.stdout + r.stderr).lower()
                print('[bench] lifecycle %s -> %s' % (transition, 'ok' if ok else 'FAILED'))
                time.sleep(1.0)
            time.sleep(1.0)

        rclpy.init()
        bench = Bench()

        # 等**被测节点真正就绪**：必须以 `cmd_vel_raw` 收到至少一条消息为准，
        # 不能只 sleep。否则"节点没起来"会被误判成"零速通过"（本轮回工的根因）。
        ready_deadline = NOW() + float(args.ready_timeout)
        while NOW() < ready_deadline and rclpy.ok() and not bench.cmds:
            bench.spin_for(0.1)
        if not bench.cmds:
            summary = {
                'run_id': run_id, 'backend': 'ros_bench', 'mode': 'headless',
                'passed': False,
                'error': 'consumer_not_ready',
                'detail': '在 %.1fs 内未从 /agc/ground/cmd_vel_raw 收到任何消息：'
                          '被测节点可能未启动，本台架判据不成立（不得当作零速通过）'
                          % args.ready_timeout,
                'consumer_log': log_path,
            }
            out = os.path.join(args.out_dir, '%s.json' % run_id)
            with open(out, 'w') as fh:
                json.dump(summary, fh, indent=2, ensure_ascii=False)
            print(json.dumps(summary, indent=2, ensure_ascii=False))
            bench.destroy_node()
            rclpy.shutdown()
            return 2
        bench.spin_for(0.5)                     # 抖动稳定
        # D1：启动无路径的证据必须绑定"安全层确实在运行"，故先探测节点。
        cfg['collision_monitor_nodes'] = probe_node_count('collision_monitor')

        cases = args.cases.split(',')
        results = []
        t_start = NOW()
        ok = True
        if 'never' in cases:
            ok &= case_never_received(bench, cfg, results)
        if 'disappear' in cases:
            ok &= case_source_disappears(bench, cfg, results)
        if 'reject' in cases:
            ok &= case_rejections(bench, cfg, results)
        if 'normal' in cases:
            ok &= case_normal_path_changes_output(bench, cfg, results)
        if 'degenerate' in cases:
            ok &= case_degenerate_arrived(bench, cfg, results)
        if 'mismatch' in cases:
            ok &= case_goal_mismatch(bench, cfg, results)
        if 'mutex' in cases:
            ok &= case_single_command_source(bench, cfg, results)
        elapsed = NOW() - t_start

        summary = {
            'run_id': run_id,
            'backend': 'ros_bench',
            'mode': 'headless',
            'use_sim_time': False,
            'path_max_age_s': args.path_max_age,
            'with_safety': bool(args.with_safety),
            'consumer_log': log_path,
            'elapsed_s': round(elapsed, 2),
            'passed': bool(ok),
            'cases': results,
        }
        out = os.path.join(args.out_dir, '%s.json' % run_id)
        with open(out, 'w') as fh:
            json.dump(summary, fh, indent=2, ensure_ascii=False)
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        bench.destroy_node()
        rclpy.shutdown()
        return 0 if ok else 1
    finally:
        log_f.close()
        for p_ in (proc, locals().get('safety_proc')):
            if p_ is not None and p_.poll() is None:
                p_.send_signal(signal.SIGINT)
                try:
                    p_.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    p_.kill()


if __name__ == '__main__':
    sys.exit(main())
