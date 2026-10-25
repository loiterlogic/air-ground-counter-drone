#!/usr/bin/env python3
"""w7c_ab_series —— W7-c A/B 交替对照系列编排（实验脚本，非生产节点）。

目的：在同一 series 下**交替**运行
  A = 共享 build（既有行为，`px4_run_root` 为空）
  B = worker 私有 PX4 运行根（`w7c_worker_run.py` 自动使用 `<worker>/px4`）
并控制**参数初态**（每个 run 前把 canonical seed 覆盖到对应 `parameters.bson` /
`parameters_backup.bson`、删除 `param_import_fail.bson`），以区分参数初态与隔离机制的影响。

产物：`experiments/<campaign>/<series_id>/`
  * `config/px4_shared_before/`           共享 build 三个参数文件的原始快照
  * `config/px4_canonical_parameters.bson` canonical 参数初态（取自快照的 `parameters.bson`）
  * `ab_series.json`                      计划 / 快照 sha256、逐 run 结果与环境、deviation 列表

纪律：单个 run 非零返回码**不中止**（保留全部尝试并记入 JSON），最终返回 0；
      `parameters.bson` 缺失视为配置错误（返回 2）；不改 PX4 源码、不创建 commit。
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# 共享 build 快照文件（参数初态与恢复范围）。
SNAPSHOT_FILES = ('parameters.bson', 'parameters_backup.bson', 'param_import_fail.bson')
# 共享 build 可写证据文件（存在才计算 sha256，缺失记 null）。
EVIDENCE_FILES = (
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


def _snapshot(build):
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
        'files': {rel: _sha256(build / rel) for rel in EVIDENCE_FILES},
        'log': {
            'scope': 'recursive under <build>/log（含按日期命名的子目录）',
            'n_files': n_files,
            'max_mtime': max_mtime,
        },
    }


def _now():
    return datetime.now().astimezone().isoformat(timespec='seconds')


def _env_record(px4_run_root):
    return {
        'AGC_WORKER_ID': os.environ.get('AGC_WORKER_ID'),
        'GZ_PARTITION': os.environ.get('GZ_PARTITION'),
        'FASTDDS_BUILTIN_TRANSPORTS': os.environ.get('FASTDDS_BUILTIN_TRANSPORTS'),
        'ROS_DOMAIN_ID': os.environ.get('ROS_DOMAIN_ID'),
        'ROS_AUTOMATIC_DISCOVERY_RANGE': os.environ.get('ROS_AUTOMATIC_DISCOVERY_RANGE'),
        'px4_run_root': px4_run_root,
    }


def _seed_params(directory, canonical):
    """把 canonical 参数初态写入 directory（参数 + 备份），并清除 import 失败标记。"""
    directory.mkdir(parents=True, exist_ok=True)
    for name in ('parameters.bson', 'parameters_backup.bson'):
        shutil.copy2(canonical, directory / name)
    for name in ('param_import_fail.bson',):
        target = directory / name
        if target.exists():
            target.unlink()


def _restore_shared(build, snapshot_dir, existed):
    """恢复共享 build 三个参数文件到 series 开始时状态（原不存在则删除）。"""
    for name in SNAPSHOT_FILES:
        target = build / name
        if existed.get(name):
            shutil.copy2(snapshot_dir / name, target)
        elif target.exists():
            target.unlink()


def _write(series_dir, doc, runs):
    doc['runs'] = runs
    (series_dir / 'ab_series.json').write_text(
        json.dumps(doc, indent=2, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--series-id', required=True)
    ap.add_argument('--campaign', default='w7-rl-b')
    ap.add_argument('--scene', default='s08_static_none_nominal_capture')
    ap.add_argument('--arm', default='p2_rl_high')
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--runs', type=int, default=3, help='A/B 各跑几次')
    ap.add_argument('--mode', default='headless')
    ap.add_argument('--repo-root', default='/home/chen/AGC')
    args = ap.parse_args()

    repo = Path(args.repo_root).resolve()
    series_dir = repo / 'experiments' / args.campaign / args.series_id
    config_dir = series_dir / 'config'
    snapshot_dir = config_dir / 'px4_shared_before'
    canonical = config_dir / 'px4_canonical_parameters.bson'
    series_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    shared_build = repo / 'toolchain' / 'PX4-Autopilot' / 'build' / 'px4_sitl_default'
    plan_path = repo / 'src' / 'agc_rl' / 'config' / 'w7c_admission_plan.yaml'

    # 共享 build 原始快照（先于任何修改）；parameters.bson 缺失 = 配置错误。
    existed = {}
    for name in SNAPSHOT_FILES:
        src = shared_build / name
        existed[name] = src.is_file()
        if existed[name]:
            shutil.copy2(src, snapshot_dir / name)
    if not existed['parameters.bson']:
        print('ERROR: 共享 build 缺少 parameters.bson：%s' % (shared_build / 'parameters.bson'))
        return 2
    shutil.copy2(snapshot_dir / 'parameters.bson', canonical)

    canonical_sha = _sha256(canonical)
    doc = {
        'series_id': args.series_id,
        'campaign': args.campaign,
        'scene': args.scene,
        'arm': args.arm,
        'seed': args.seed,
        'mode': args.mode,
        'planned_runs': args.runs,
        'series_dir': str(series_dir),
        'plan_path': str(plan_path),
        'plan_sha256': _sha256(plan_path),
        'canonical_seed_path': str(canonical),
        'canonical_seed_sha256': canonical_sha,
        'shared_build': str(shared_build),
        'shared_build_before_sha256': {rel: _sha256(shared_build / rel)
                                       for rel in EVIDENCE_FILES},
        'shared_snapshot_files': {name: bool(existed.get(name)) for name in SNAPSHOT_FILES},
        'runs': [],
        'deviations': [],
    }
    _write(series_dir, doc, doc['runs'])
    print('[ab] series=%s dir=%s' % (args.series_id, series_dir), flush=True)

    runs = doc['runs']
    try:
        for i in range(1, args.runs + 1):
            for condition in ('A', 'B'):
                run_id = '%s-%s%d' % (args.series_id, condition.lower(), i)
                if condition == 'A':
                    # A：共享 build = 既有行为（px4_run_root 为空）。
                    seed_target = shared_build
                    _seed_params(shared_build, canonical)
                    cmd = [
                        'python3', 'scripts/w7b_arms_runner.py',
                        '--arms', args.arm, '--seeds', str(args.seed),
                        '--scene', args.scene, '--mode', args.mode,
                        '--campaign', args.campaign, '--run-id', run_id,
                        '--infra-retries', '0',
                    ]
                    px4_run_root = None
                else:
                    # B：worker 私有运行根（instance_0 / instance_1 同样注入 canonical 初态）。
                    px4_run_root = (repo / 'experiments' / args.campaign / run_id
                                    / 'worker_0' / 'px4')
                    for inst in (0, 1):
                        _seed_params(px4_run_root / ('instance_%d' % inst), canonical)
                    seed_target = px4_run_root / 'instance_0'
                    cmd = [
                        'python3', 'scripts/w7c_worker_run.py',
                        '--worker-id', '0', '--run-id', run_id,
                        '--arm', args.arm, '--scene', args.scene,
                        '--seed', str(args.seed), '--mode', args.mode,
                        '--campaign', args.campaign,
                        '--px4-run-root', str(px4_run_root),
                    ]

                param_initial_sha = _sha256(seed_target / 'parameters.bson')
                shared_before = _snapshot(shared_build)
                started = _now()
                print('[ab] %s run=%s cmd=%s' % (condition, run_id, ' '.join(cmd)), flush=True)
                proc = subprocess.run(cmd, cwd=str(repo))
                ended = _now()
                shared_after = _snapshot(shared_build)
                row = {
                    'condition': condition,
                    'run_id': run_id,
                    'returncode': proc.returncode,
                    'started': started,
                    'ended': ended,
                    'param_initial_sha256': param_initial_sha,
                    'shared_before': shared_before,
                    'shared_after': shared_after,
                    'env': _env_record(None if px4_run_root is None else str(px4_run_root)),
                }
                runs.append(row)
                _write(series_dir, doc, runs)
                print('[ab] %s run=%s returncode=%d' % (condition, run_id, proc.returncode),
                      flush=True)
    finally:
        _restore_shared(shared_build, snapshot_dir, existed)
        _write(series_dir, doc, runs)

    failed = [r for r in runs if r['returncode'] != 0]
    writes_b = [r['run_id'] for r in runs
                if r['condition'] == 'B' and r['shared_before'] != r['shared_after']]
    print('[ab] summary: runs=%d failed=%d shared_writes_in_B=%d' % (
        len(runs), len(failed), len(writes_b)))
    for r in runs:
        print('  %s %-24s rc=%s' % (r['condition'], r['run_id'], r['returncode']))
    print('[ab] ->', series_dir / 'ab_series.json')
    return 0


if __name__ == '__main__':
    sys.exit(main())
