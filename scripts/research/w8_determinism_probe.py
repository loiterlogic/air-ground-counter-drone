#!/usr/bin/env python3
"""W8 measurement P1: serial fixed-condition probe; immutable inputs, count-based report."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys
from datetime import datetime, timezone

# 本脚本位于 scripts/research/：项目根在上两层（P0-4 迁移；原 `parents[1]`）。
ROOT = Path(__file__).resolve().parents[2]
SCENE = 's15_static_none_fov_capture'
MISSION = {'INTERCEPT_CONFIRMED', 'TRACKING_SUCCESS', 'MISSION_FAILED'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + '\n')


def decision(values):
    if len(values) != 5 or not all(math.isfinite(v) and 0 <= v <= 1 for v in values):
        return 'incomplete'
    spread = max(values) - min(values)
    if spread < .01:
        return 'reproducible_at_probe_resolution'
    if spread <= .27:
        return 'execution_level_variability_observed'
    return 'beyond_reference_range'


def read_attempt(run_dir):
    run_dir = run_dir.resolve()
    path = run_dir / 'metrics/arms.json'
    arms = json.loads(path.read_text())
    assert arms['mode'] == 'headless' and len(arms['arms']) == 1, 'mode/arm mismatch'
    row = arms['arms'][0]
    expected = {'scene': SCENE, 'arm': 'p1_coop', 'seed': 5, 'backend': 'full',
                'air_tracking_ref': 'on', 'observe_yaw_mode': 'target',
                'shield': 'true', 'infra_retries_used': 0}
    assert all(row.get(k) == v for k, v in expected.items()), 'condition mismatch'
    rec = {'run_id': run_dir.name, 'terminal': row['terminal_state'],
           'reason': row.get('reason_code'), 'arms_path': str(path.relative_to(ROOT)),
           'arms_sha256': sha(path), 'episode_run_id': row.get('run_id')}
    rec['is_mission'] = row['terminal_state'] in MISSION and row.get('outcome_class') == 'mission_terminal'
    if not rec['is_mission']:
        return rec
    summary_path = Path(row['summary_path'])
    sm = json.loads(summary_path.read_text())
    ew = sm['episode_window_metrics']
    windows = sm['episode_windows']
    assert len(windows) == 1, 'expected one active window'
    n, fco = ew['vis_ticks_total'], ew['ticks_fire_control_opportunity']
    assert isinstance(n, int) and isinstance(fco, int) and 0 <= fco <= n and n > 0
    duration = windows[0]['leave_s'] - windows[0]['enter_s']
    assert math.isfinite(duration) and duration > 0
    rec.update(summary_path=str(summary_path.relative_to(ROOT)), summary_sha256=sha(summary_path),
               ticks=n, fco_ticks=fco, active_fco=fco/n, window_s=duration,
               shield_infeasible_rate=sm['shield_infeasible_rate'], reset_failure_rate=sm['reset_failure_rate'])
    return rec


def report(batch):
    plan = json.loads((batch / 'config/plan.json').read_text())
    attempts = json.loads((batch / 'attempts.json').read_text())
    records = [read_attempt(ROOT / 'experiments' / plan['campaign'] / a['run_id']) for a in attempts]
    valid = [r for r in records if r['is_mission']]
    values = [r['active_fco'] for r in valid]
    stats = {}
    for key in ('active_fco', 'window_s'):
        vals = [r[key] for r in valid]
        stats[key] = ({'n': len(vals), 'min': min(vals), 'max': max(vals),
                       'spread': max(vals)-min(vals), 'mean': statistics.mean(vals),
                       'sd': statistics.stdev(vals) if len(vals)>1 else None} if vals else {'n': 0})
    result = {'plan_sha256': sha(batch / 'config/plan.json'), 'attempts': records,
              'stats': stats, 'decision': decision(values), 'gate': 'not_evaluable_as_specified',
              'headless_scale_authorized': False, 'scientific_verdicts_changed': False}
    write(batch / 'metrics/probe.json', result)
    lines = ['# W8 测量 P1 确定性探针重做', '',
             '固定 s15 / p1_coop / seed 5 / full / headless；诊断，非科研确证。', '',
             '| run | terminal | FCO ticks / ticks | active FCO | window s | shield_infeasible_rate | reset_failure_rate |',
             '|---|---|---|---|---|---|---|']
    for r in records:
        lines.append('| %s | %s | %s / %s | %s | %s | %s | %s |' % tuple(
            r.get(k, 'null') for k in ('run_id', 'terminal', 'fco_ticks', 'ticks', 'active_fco',
                                      'window_s', 'shield_infeasible_rate', 'reset_failure_rate')))
    lines += ['', '判读：`%s`；有效 mission n=%d，infra=%d。' % (result['decision'], len(valid), len(records)-len(valid)),
              '', '```json', json.dumps(stats, indent=2), '```', '',
              '这是单一条件下的描述性重复性诊断，不能定位调度/物理/感知根因，也不能单凭极差证明等价目标不可能。',
              'gate=`not_evaluable_as_specified`；后续测量规格尚待 P2/P3 裁定。历史科研 verdict 不变。']
    (batch / 'metrics/probe.md').write_text('\n'.join(lines)+'\n')
    return result


def run(batch):
    batch.mkdir(parents=True, exist_ok=False)
    (batch / 'log').mkdir()
    campaign = 'w8-p1-redo'
    plan = {'created_at': datetime.now(timezone.utc).isoformat(), 'campaign': campaign,
            'scene': SCENE, 'seed': 5, 'arm': 'p1_coop', 'mode': 'headless', 'backend': 'full',
            'required_missions': 5, 'max_attempts': 10, 'infra_retries': 0,
            'rule': '<0.01 reproducible; [0.01,0.27] execution variability; >0.27 beyond reference',
            'git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
            'source_sha256': {p: sha(ROOT/p) for p in ['scripts/research/w8_determinism_probe.py',
                'scripts/research/w7b_arms_runner.py', 'scripts/episode_runner.py',
                '.trae/specs/redo-w8-determinism-probe/spec.md']}}
    write(batch / 'config/plan.json', plan)
    attempts, valid = [], 0
    for i in range(1, 11):
        run_id = '%s-%02d' % (batch.name, i)
        cmd = [sys.executable, str(ROOT/'scripts/research/w7b_arms_runner.py'), '--campaign', campaign,
               '--run-id', run_id, '--scene', SCENE, '--seeds', '5', '--arms', 'p1_coop',
               '--mode', 'headless', '--infra-retries', '0', '--timeout', '240',
               '--ready-timeout-s', '180', '--start-timeout-s', '60', '--obs-horizon-s', '60',
               '--own-px4-delay-s', '25', '--intruder-px4-delay-s', '35', '--px4-warmup', 'false']
        attempt = {'run_id': run_id, 'command': cmd, 'started_at': datetime.now(timezone.utc).isoformat()}
        attempts.append(attempt)
        write(batch / 'attempts.json', attempts)
        print('START', run_id, flush=True)
        with (batch / ('log/%02d.console.log' % i)).open('w') as output:
            attempt['returncode'] = subprocess.call(cmd, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT)
        write(batch / 'attempts.json', attempts)
        rec = read_attempt(ROOT/'experiments'/campaign/run_id)
        valid += int(rec['is_mission'])
        print('END', run_id, rec['terminal'], 'valid=%d' % valid, flush=True)
        if valid == 5:
            break
    result = report(batch)
    print(json.dumps(result['stats']), result['decision'], flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['run', 'report'])
    parser.add_argument('--batch-id', required=True)
    args = parser.parse_args()
    if '/' in args.batch_id or args.batch_id in ('.', '..'):
        parser.error('batch-id must be a single directory name')
    directory = ROOT/'experiments/w8-p1-redo'/args.batch_id
    if args.action == 'run':
        run(directory)
    else:
        report(directory)
