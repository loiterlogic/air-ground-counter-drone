"""R2 node-level test for the production run_logger FCO recorder.

Drives the real `run_logger` executable over synthetic /clock + state + target +
envelope + odom messages (no GZ/PX4).  The run directory is hermetic unless
AGC_TEST_EXPERIMENTS_ROOT is set by the evidence run.
"""
import json
import os
import signal
import subprocess
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
LOGGER = ROOT / 'install/agc_task/lib/agc_task/run_logger'


def _stamp(t):
    from builtin_interfaces.msg import Time
    sec = int(t)
    return Time(sec=sec, nanosec=int(round((t - sec) * 1e9)))


def _wait_for_dir(path, timeout=8.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if path.is_dir():
            return True
        time.sleep(0.05)
    return False


def _run_logger(tmp_path):
    assert LOGGER.is_file(), 'run_logger executable missing; build agc_task first'
    root = Path(os.environ.get('AGC_TEST_EXPERIMENTS_ROOT', str(tmp_path)))
    run_id = 'node-fco-%d' % os.getpid()
    run_dir = root / 'w8-p3-node-test' / run_id
    if run_dir.exists():
        pytest.skip('run dir already exists: %s' % run_dir)

    args = [
        str(LOGGER), '--ros-args', '-p', 'use_sim_time:=true',
        '-p', 'experiments_root:=%s' % root,
        '-p', 'campaign:=w8-p3-node-test',
        '-p', 'scenario:=synthetic',
        '-p', 'seed:=7',
        '-p', 'run_id_override:=%s' % run_id,
        '-p', 'state_topic:=/agc_test/state',
        '-p', 'target_topic:=/agc_test/targets',
        '-p', 'envelope_topic:=/agc_test/envelope',
        '-p', 'ground_odom_topic:=/agc_test/odom',
        '-p', 'odom_valid_topic:=/agc_test/odom_valid',
        '-p', 'scan_topic:=/agc_test/scan',
        '-p', 'collision_monitor_state_topic:=/agc_test/cm_state',
        '-p', 'cmd_topic:=/agc_test/cmd',
        '-p', 'cmd_raw_topic:=/agc_test/cmd_raw',
        '-p', 'episode_topic:=/agc_test/episode',
        '-p', 'contact_topic:=/agc_test/contact',
        '-p', 'mission_fco_budget_s:=60.0',
        '-p', 'mission_fco_max_gap_s:=1.0',
    ]
    env = dict(os.environ)
    env['ROS_AUTOMATIC_DISCOVERY_RANGE'] = 'LOCALHOST'
    env.setdefault('ROS_DOMAIN_ID', '0')
    log_path = tmp_path / 'run_logger.log'
    with open(log_path, 'w', encoding='utf-8') as log_file:
        proc = subprocess.Popen(args, env=env, stdout=log_file, stderr=subprocess.STDOUT)
    if not _wait_for_dir(run_dir):
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        pytest.fail('run_logger did not create %s\n%s' % (run_dir, log_path.read_text()))
    return proc, run_dir, log_path


def _publish_case():
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, DurabilityPolicy
    from rosgraph_msgs.msg import Clock
    from std_msgs.msg import Bool, Int32
    from nav_msgs.msg import Odometry
    from sensor_msgs.msg import LaserScan
    from nav2_msgs.msg import CollisionMonitorState
    from geometry_msgs.msg import TwistStamped
    from agc_msgs.msg import AgcTaskState, TargetTrackArray, TargetTrack

    os.environ['ROS_AUTOMATIC_DISCOVERY_RANGE'] = 'LOCALHOST'
    if not rclpy.ok():
        rclpy.init()
    node = Node('agc_test_publisher_%d' % os.getpid())
    pubs = {
        'clock': node.create_publisher(Clock, '/clock', 10),
        'state': node.create_publisher(AgcTaskState, '/agc_test/state', 10),
        'targets': node.create_publisher(TargetTrackArray, '/agc_test/targets', 20),
        'envelope': node.create_publisher(Bool, '/agc_test/envelope', 10),
        'odom': node.create_publisher(Odometry, '/agc_test/odom', 50),
        'odom_valid': node.create_publisher(Bool, '/agc_test/odom_valid', 10),
        'scan': node.create_publisher(LaserScan, '/agc_test/scan', 10),
        'cm_state': node.create_publisher(CollisionMonitorState, '/agc_test/cm_state', 20),
        'cmd': node.create_publisher(TwistStamped, '/agc_test/cmd', 50),
        'cmd_raw': node.create_publisher(TwistStamped, '/agc_test/cmd_raw', 50),
        'episode': node.create_publisher(
            Int32, '/agc_test/episode', QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)),
        'reset_retries': node.create_publisher(
            Int32, '/agc_test/reset_retries', QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)),
        'reset_failed': node.create_publisher(
            Bool, '/agc_test/reset_failed', QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)),
    }

    def state(t, code, name, reason):
        msg = AgcTaskState()
        msg.header.stamp = _stamp(t)
        msg.header.frame_id = 'world'
        msg.state = code
        msg.state_name = name
        msg.reason_code = reason
        msg.target_id = 'intruder_uav'
        pubs['state'].publish(msg)

    def target(t):
        arr = TargetTrackArray()
        arr.header.stamp = _stamp(t)
        arr.header.frame_id = 'world'
        track = TargetTrack()
        track.header.stamp = _stamp(t)
        track.header.frame_id = 'world'
        track.target_id = 'intruder_uav'
        track.confidence = 0.9
        track.pose.pose.position.x = 1.0
        track.pose.pose.position.y = 0.5
        arr.tracks = [track]
        pubs['targets'].publish(arr)

    def odom(t):
        msg = Odometry()
        msg.header.stamp = _stamp(t)
        msg.twist.twist.linear.x = 0.0
        pubs['odom'].publish(msg)

    def scan(t):
        msg = LaserScan()
        msg.header.stamp = _stamp(t)
        msg.angle_min = -1.0
        msg.angle_max = 1.0
        msg.angle_increment = 0.1
        msg.range_min = 0.1
        msg.range_max = 20.0
        msg.ranges = [float('inf')] * 21
        pubs['scan'].publish(msg)

    def cm_state():
        msg = CollisionMonitorState()
        msg.action_type = 0
        pubs['cm_state'].publish(msg)

    def twist(pub, t):
        msg = TwistStamped()
        msg.header.stamp = _stamp(t)
        pubs[pub].publish(msg)

    end_sim = 6.0
    step = 0.01
    start = time.monotonic()
    for i in range(int(end_sim / step) + 1):
        t = round(i * step, 6)
        pubs['clock'].publish(Clock(clock=_stamp(t)))

        if abs(t - 0.05) < 1e-6:
            pubs['episode'].publish(Int32(data=7))
            pubs['odom_valid'].publish(Bool(data=True))
            pubs['reset_retries'].publish(Int32(data=0))
            pubs['reset_failed'].publish(Bool(data=False))
        if abs(t - 0.2) < 1e-6 or abs(t - 0.25) < 1e-6:
            state(t, AgcTaskState.AIR_SEARCH, 'AIR_SEARCH', 'idle')
        if abs(t - 0.5) < 1e-6 or abs(t - 0.55) < 1e-6:
            state(t, AgcTaskState.TARGET_ACQUIRED, 'TARGET_ACQUIRED', 'target_acquired')
        if abs(t - 1.0) < 1e-6:
            print('publisher matches:', {k: p.get_subscription_count() for k, p in pubs.items()})
        if 0.95 <= t <= 1.05:
            state(t, AgcTaskState.GROUND_APPROACH, 'GROUND_APPROACH', 'ground_approach')
        if 5.0 <= t <= 5.1:
            state(t, AgcTaskState.INTERCEPT_CONFIRMED, 'INTERCEPT_CONFIRMED', 'CAPTURE_NET')
        if 5.5 <= t <= 5.55:
            # 状态定时器会重复发布终态；记录器必须只认一次。
            state(t, AgcTaskState.INTERCEPT_CONFIRMED, 'INTERCEPT_CONFIRMED', 'CAPTURE_NET')

        if t >= 0.5 and t <= 5.0:
            target(t)
            pubs['envelope'].publish(Bool(data=True))

        if abs((t / 0.05) - round(t / 0.05)) < 1e-9:
            odom(t)
            scan(t)
            cm_state()
            twist('cmd', t)
            twist('cmd_raw', t)

        rclpy.spin_once(node, timeout_sec=0)
        due = start + i * step
        sleep = due - time.monotonic()
        if sleep > 0:
            time.sleep(sleep)

    rclpy.spin_once(node, timeout_sec=0)
    node.destroy_node()
    rclpy.shutdown()


def test_run_logger_fixed_budget(tmp_path):
    proc, run_dir, log_path = _run_logger(tmp_path)
    try:
        _publish_case()
        time.sleep(0.5)
    finally:
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
    log = log_path.read_text(encoding='utf-8', errors='replace')
    assert proc.returncode == 0, log

    summary = json.loads((run_dir / 'metrics' / 'summary.json').read_text())
    block = summary['mission_fco_fixed_budget_v1']
    assert block['definition_version'] == 'mission_fco_fixed_budget_v1'
    assert block['mission_count'] == 1
    mission = block['missions'][0]
    assert mission['t0_verified'] is True
    assert mission['episode_id'] == 7
    assert abs(mission['t0_s'] - 1.0) < 0.1
    assert mission['terminal_seen'] is True
    assert mission['terminal_state'] == 'INTERCEPT_CONFIRMED'
    assert mission['terminal_within_budget'] is True
    assert abs(mission['terminal_s'] - 5.0) < 0.1
    assert abs(mission['known_preterminal_s'] - 4.0) < 0.15
    assert abs(mission['fco_exposure_s'] - 4.0) < 0.15
    assert abs(mission['post_terminal_budget_s'] - 56.0) < 0.15
    assert mission['point_valid'] is True
    assert abs(mission['mission_fco_fraction'] - 4.0 / 60.0) < 0.003
    assert abs(mission['coverage_residual_s']) < 1e-6

    ledger = json.loads((run_dir / 'metrics' / 'mission_fco_intervals.json').read_text())
    assert ledger['definition_version'] == 'mission_fco_fixed_budget_v1'
    rec = ledger['missions'][0]
    intervals = rec['intervals']
    assert intervals[0]['start_s'] == pytest.approx(mission['t0_s'], abs=1e-9)
    assert intervals[-1]['end_s'] == pytest.approx(mission['t0_s'] + 60.0, abs=1e-6)
    known = sum(i['end_s'] - i['start_s'] for i in intervals if i['kind'] == 'known')
    missing = sum(i['end_s'] - i['start_s'] for i in intervals if i['kind'] == 'missing')
    post = sum(i['end_s'] - i['start_s'] for i in intervals if i['kind'] == 'post_terminal')
    fco = sum(i['end_s'] - i['start_s'] for i in intervals if i['kind'] == 'known' and i['fco'])
    assert known == pytest.approx(4.0, abs=0.15)
    assert missing == pytest.approx(0.0, abs=1e-6)
    assert post == pytest.approx(56.0, abs=0.15)
    assert fco == pytest.approx(4.0, abs=0.15)
    assert known + missing + post == pytest.approx(60.0, abs=1e-6)

    # 旧口径字段保留且未改语义。
    assert summary['visibility_metrics']['definition_version'] == 'window_fixed_v1'
    assert summary['visibility_metrics']['window_s'] == 60.0
    assert summary['episode_window_metrics']['window_count'] >= 1
    assert (run_dir / 'config' / 'episode_id.txt').read_text().strip() == '7'
    assert summary['seed'] == 7
