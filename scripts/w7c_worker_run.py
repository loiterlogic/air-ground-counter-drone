#!/usr/bin/env python3
"""w7c_worker_run —— W7-c 单 worker 启动器（rootless netns + 归属环境）。

ADR-0077：每个 worker 跑在独立的 user+net namespace（`unshare -Urn`），统一
`ROS_DOMAIN_ID=0`；`/dev/shm` 不随 netns 隔离，故所有 worker 进程设
`FASTDDS_BUILTIN_TRANSPORTS=UDPv4`，并用唯一 `GZ_PARTITION` 隔离 gz 话题。
调用方须已 `source /opt/ros/jazzy/setup.bash` 与 `source install/setup.bash`。

用法：
  python3 scripts/w7c_worker_run.py --worker-id 0 --run-id <id> \
      --arm p2_rl_high --scene s08_static_none_nominal_capture --seed 0 --mode headless
"""

import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--worker-id', type=int, required=True)
    ap.add_argument('--run-id', required=True)
    ap.add_argument('--arm', default='p2_rl_high')
    ap.add_argument('--scene', default='s08_static_none_nominal_capture')
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--mode', default='headless', choices=['headless', 'gui'])
    ap.add_argument('--campaign', default='w7-rl-b')
    ap.add_argument('--probe-at-s', type=float, default=70.0,
                    help='在该 worker 内 t=<s> 执行 ros2 node/topic list 与 gz topic -l；0=不做')
    ap.add_argument('--repo-root', default='/home/chen/AGC')
    args = ap.parse_args()

    root = Path(args.repo_root).resolve()
    worker_dir = root / 'experiments' / args.campaign / args.run_id / ('worker_%d' % args.worker_id)
    (worker_dir / 'log').mkdir(parents=True, exist_ok=True)
    (worker_dir / 'metrics').mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.update({
        'AGC_WORKER_ID': str(args.worker_id),
        'GZ_PARTITION': 'agc_w_%d' % args.worker_id,
        'FASTDDS_BUILTIN_TRANSPORTS': 'UDPv4',
        'ROS_DOMAIN_ID': '0',
        'ROS_AUTOMATIC_DISCOVERY_RANGE': 'LOCALHOST',
    })

    runner = [
        sys.executable, str(root / 'scripts' / 'w7b_arms_runner.py'),
        '--arms', args.arm, '--seeds', str(args.seed), '--scene', args.scene,
        '--mode', args.mode, '--campaign', args.campaign, '--run-id', args.run_id,
        '--worker-id', str(args.worker_id), '--infra-retries', '0',
    ]
    q = [shlex.quote(x) for x in runner]
    console = shlex.quote(str(worker_dir / 'log' / 'worker_console.log'))
    node_out = shlex.quote(str(worker_dir / 'metrics' / 'node_list.txt'))
    topic_out = shlex.quote(str(worker_dir / 'metrics' / 'topic_list.txt'))
    gz_out = shlex.quote(str(worker_dir / 'metrics' / 'gz_topic_list.txt'))

    probe = ''
    if args.probe_at_s > 0:
        probe = (
            'sleep %s; '
            'timeout 10 ros2 node list > %s 2>&1 || true; '
            'timeout 10 ros2 topic list > %s 2>&1 || true; '
            'timeout 10 gz topic -l > %s 2>&1 || true; '
            % (args.probe_at_s, node_out, topic_out, gz_out)
        )

    script = (
        'set -e\n'
        # PX4 的 `/tmp/px4_lock-<instance>` 不随 netns 隔离；用 private mount ns + tmpfs /tmp 隔离。
        'mount -t tmpfs tmpfs /tmp\n'
        'ip link set lo up\n'
        '%s > %s 2>&1 &\n'
        'WPID=$!\n'
        '%s'
        'wait $WPID\n'
        'exit $?\n'
        % (' '.join(q), console, probe)
    )

    cmd = ['unshare', '-Urnm', 'bash', '-c', script, 'w7c-worker-%d' % args.worker_id]
    print('[w7c] worker=%d run_id=%s dir=%s' % (args.worker_id, args.run_id, worker_dir), flush=True)
    proc = subprocess.run(cmd, cwd=str(root), env=env)
    print('[w7c] worker=%d exit=%d' % (args.worker_id, proc.returncode), flush=True)
    return proc.returncode


if __name__ == '__main__':
    sys.exit(main())
