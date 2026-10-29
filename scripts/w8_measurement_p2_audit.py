#!/usr/bin/env python3
"""Read-only evidence audit for W8 measurement P2; never adjudicates research claims."""
import hashlib
import json
from pathlib import Path
import statistics

from scipy.stats import t

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'experiments/w8-parity/20261026-w8-measurement-p2'


def paired_ci(rows):
    # Use unrounded arm values, as in the existing W7 adjudicator.
    values = [r['b'] - r['a'] for r in rows if not r.get('excluded')]
    n = len(values)
    mean = statistics.mean(values)
    half = float(t.ppf(.975, n-1)) * statistics.stdev(values) / n**.5
    return {'n': n, 'mean_delta': mean, 'ci95': [mean-half, mean+half]}


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    (OUT / 'metrics').mkdir()
    inputs = {}

    def read(path):
        path = path.resolve()
        inputs[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
        return json.loads(path.read_text())

    cases = []
    for batch in ['20261025-w8-gui-headless-pilot', '20261025-w8-gui-gpu-pilot']:
        attempts = read(ROOT/'experiments/w8-parity'/batch/'attempts.json')['attempts']
        cases += [('w8-parity', a['run_id'], batch) for a in attempts]
    cases += [('w8-p1-redo', '20261026-w8-p1-redo-r2-%02d' % i, 'p1_redo') for i in range(1, 6)]
    records = []
    for campaign, run_id, group in cases:
        doc = read(ROOT/'experiments'/campaign/run_id/'metrics/arms.json')
        row = doc['arms'][0]
        rec = {'run_id': run_id, 'group': group, 'mode': doc['mode'],
               'terminal': row['terminal_state'], 'outcome_class': row['outcome_class']}
        if row.get('summary_path') and Path(row['summary_path']).exists():
            sm = read(Path(row['summary_path']))
            rec.update(shield_infeasible_rate=sm.get('shield_infeasible_rate'),
                       reset_failure_rate=sm.get('reset_failure_rate'))
            windows = sm.get('episode_windows') or []
            if row['outcome_class'] == 'mission_terminal' and len(windows) == 1:
                w = windows[0]
                rec.update(active_s=w['leave_s']-w['enter_s'],
                           active_ticks=w['vis_ticks_total'],
                           legacy_fixed_ticks=(sm.get('visibility_metrics') or {}).get('ticks_total'),
                           legacy_configured_window_s=(sm.get('visibility_metrics') or {}).get('window_s'))
        records.append(rec)
    mission = [r for r in records if 'active_s' in r]
    durations = [r['active_s'] for r in mission]
    adj_path = ROOT/'experiments/w7-rl-b/20261022-w7-rl-b-v3-n20r/metrics/p2_adjudication.json'
    adj = read(adj_path)
    rows = adj['fco_rate_active']['rows']
    full, clean = paired_ci(rows), paired_ci([r for r in rows if not r.get('degraded')])
    result = {'purpose': 'measurement specification audit, no new scientific verdict',
              'attempts': records, 'window_audit': {'mission_n': len(mission),
              'attempt_n': len(records), 'min_active_s': min(durations),
              'max_active_s': max(durations), 'active_shorter_than_60_n': sum(v < 60 for v in durations)},
              'p2_v3_full': full, 'p2_v3_without_degraded_sensitivity_only': clean,
              'historical_verdicts_changed': False, 'new_metric_reconstructed': False,
              'gate': 'not_evaluable_as_specified', 'inputs_sha256': inputs}
    (OUT/'metrics/audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    text = ['# W8 测量 P2 只读审计', '',
            '40 个历史 pilot attempts + 独立 P1 重做 5 次；无新仿真，不合并计算模式效应。', '',
            '窗口审计：`%s`。' % json.dumps(result['window_audit']), '',
            '| 科研 P2 v3 口径 | n | B−A | 95% CI |', '|---|---:|---:|---|']
    for label, value in [('原 20 对', full), ('剔 degraded（仅敏感性）', clean)]:
        text.append('| %s | %d | %.6f | [%.6f, %.6f] |' % (label, value['n'], value['mean_delta'], *value['ci95']))
    text += ['', '敏感性筛选是事后检查，不替代原预注册判定；两组 CI 上限均低于原 MME=0.10。',
             'active_s 是首个 GROUND_APPROACH 至终态的长度；不能用包含预热的总仿真时长判断 60 秒窗是否在终态前。',
             '既有汇总计数不能精确恢复逐时刻 FCO 积分；未生成新口径值。C9 两项及逐输入 SHA256 见 audit.json。']
    (OUT/'metrics/audit.md').write_text('\n'.join(text)+'\n')
    print(json.dumps({k: result[k] for k in ['window_audit', 'p2_v3_full', 'p2_v3_without_degraded_sensitivity_only']}))


if __name__ == '__main__':
    main()
