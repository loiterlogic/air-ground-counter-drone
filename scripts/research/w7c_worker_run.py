#!/usr/bin/env python3
"""w7c_worker_run —— W7-c 单 worker 启动器（rootless netns + 归属环境）。

ADR-0077：每个 worker 跑在独立的 user+net namespace（`unshare -Urn`），统一
`ROS_DOMAIN_ID=0`；`/dev/shm` 不随 netns 隔离，故所有 worker 进程设
`FASTDDS_BUILTIN_TRANSPORTS=UDPv4`，并用唯一 `GZ_PARTITION` 隔离 gz 话题。
调用方须已 `source /opt/ros/jazzy/setup.bash` 与 `source install/setup.bash`。

用法：
  python3 scripts/research/w7c_worker_run.py --worker-id 0 --run-id <id> \
      --arm p2_rl_high --scene s08_static_none_nominal_capture --seed 0 --mode headless
"""

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path


# W7-c 隔离证据口径：共享 build 下 PX4 可写运行文件（存在才计算 sha256，缺失记 null）；
#   log/ 递归统计全部文件（含按日期命名的子目录），记录文件数与最大 mtime。
SHARED_WRITABLE_FILES = (
    'dataman',
    'parameters.bson',
    'parameters_backup.bson',
    'param_import_fail.bson',
    'etc/init.d-posix/px4-rc.params',
)


def _sha256(path):
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _shared_snapshot(build):
    files = {rel: _sha256(build / rel) for rel in SHARED_WRITABLE_FILES}
    log_dir = build / 'log'
    n_files, max_mtime = 0, None
    if log_dir.is_dir():
        for path in log_dir.rglob('*'):
            if path.is_file():
                n_files += 1
                mtime = path.stat().st_mtime
                if max_mtime is None or mtime > max_mtime:
                    max_mtime = mtime
    return {
        'build': str(build),
        'files': files,
        'log': {
            'scope': 'recursive under <build>/log（含按日期命名的子目录）',
            'n_files': n_files,
            'max_mtime': max_mtime,
        },
    }


def _private_snapshot(instance_dir):
    log_dir = instance_dir / 'log'
    return {
        'exists': instance_dir.is_dir(),
        'dataman': (str(instance_dir / 'dataman')
                    if (instance_dir / 'dataman').is_file() else None),
        'parameters_bson': sorted(p.name for p in instance_dir.glob('parameters*.bson')
                                  if p.is_file()) if instance_dir.is_dir() else [],
        'log_files': sorted(str(p.relative_to(instance_dir))
                            for p in log_dir.rglob('*') if p.is_file())
        if log_dir.is_dir() else [],
    }


def _writes_detected(before, after):
    changes = []
    for rel in SHARED_WRITABLE_FILES:
        if before['files'].get(rel) != after['files'].get(rel):
            changes.append('files/%s' % rel)
    if before['log']['n_files'] != after['log']['n_files']:
        changes.append('log/n_files')
    if before['log']['max_mtime'] != after['log']['max_mtime']:
        changes.append('log/max_mtime')
    return {'any': bool(changes), 'changes': changes}


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
    # W7-c（ADR-0095）：PX4 每实例可写运行根；空 = 自动用 <worker_dir>/px4（与共享 build 隔离）。
    ap.add_argument('--px4-run-root', default='')
    args = ap.parse_args()

    root = Path(args.repo_root).resolve()
    worker_dir = root / 'experiments' / args.campaign / args.run_id / ('worker_%d' % args.worker_id)
    (worker_dir / 'log').mkdir(parents=True, exist_ok=True)
    (worker_dir / 'metrics').mkdir(parents=True, exist_ok=True)
    px4_run_root = Path(args.px4_run_root).resolve() if args.px4_run_root else (worker_dir / 'px4')

    env = os.environ.copy()
    env.update({
        'AGC_WORKER_ID': str(args.worker_id),
        'GZ_PARTITION': 'agc_w_%d' % args.worker_id,
        'FASTDDS_BUILTIN_TRANSPORTS': 'UDPv4',
        'ROS_DOMAIN_ID': '0',
        'ROS_AUTOMATIC_DISCOVERY_RANGE': 'LOCALHOST',
    })

    runner = [
        sys.executable, str(root / 'scripts' / 'research' / 'w7b_arms_runner.py'),
        '--arms', args.arm, '--seeds', str(args.seed), '--scene', args.scene,
        '--mode', args.mode, '--campaign', args.campaign, '--run-id', args.run_id,
        '--worker-id', str(args.worker_id), '--infra-retries', '0',
        '--px4-run-root', str(px4_run_root),
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
    print('[w7c] worker=%d run_id=%s dir=%s px4_run_root=%s' % (
        args.worker_id, args.run_id, worker_dir, px4_run_root), flush=True)

    # W7-c（ADR-0095）：共享 build 可写文件前后快照——证明 worker 未写入共享 build。
    shared_build = root / 'toolchain' / 'PX4-Autopilot' / 'build' / 'px4_sitl_default'
    shared_before = _shared_snapshot(shared_build)
    proc = None
    try:
        proc = subprocess.run(cmd, cwd=str(root), env=env)
    finally:
        shared_after = _shared_snapshot(shared_build)
        evidence = {
            'run_id': args.run_id,
            'worker_id': args.worker_id,
            'returncode': None if proc is None else proc.returncode,
            'px4_run_root': str(px4_run_root),
            'shared_before': shared_before,
            'shared_after': shared_after,
            'writes_detected': _writes_detected(shared_before, shared_after),
            'private_dirs': {
                'instance_%d' % inst: _private_snapshot(px4_run_root / ('instance_%d' % inst))
                for inst in (0, 1, 3)
            },
            'env': {
                'AGC_WORKER_ID': env.get('AGC_WORKER_ID'),
                'GZ_PARTITION': env.get('GZ_PARTITION'),
                'FASTDDS_BUILTIN_TRANSPORTS': env.get('FASTDDS_BUILTIN_TRANSPORTS'),
                'ROS_DOMAIN_ID': env.get('ROS_DOMAIN_ID'),
                'ROS_AUTOMATIC_DISCOVERY_RANGE': env.get('ROS_AUTOMATIC_DISCOVERY_RANGE'),
                'px4_run_root': str(px4_run_root),
            },
        }
        (worker_dir / 'metrics' / 'px4_writable_isolation.json').write_text(
            json.dumps(evidence, indent=2, ensure_ascii=False))
    print('[w7c] worker=%d exit=%d' % (args.worker_id, proc.returncode), flush=True)
    return proc.returncode


if __name__ == '__main__':
    sys.exit(main())
