#!/usr/bin/env python3
"""w7b_gui_headless_recheck —— **只读**的 GUI / headless 同口径复核（ADR-0024 R5）。

**定位**：只用既有产物复核 GUI / headless，**不**新增 GUI run、**不**改写既有 B 报告、
**不**参与 P1 / P2 判定。全部尝试保留（含 P1 GUI 首跑 `MISSION_FAILED(TIMEOUT)`），
并用 active 窗口口径重新列表；结论固定为“GUI / headless 数值等价未建立 / 证据不足”。

复用 `w7b_worker_repeatability.py` 的 arms / summary / 日志解析函数，避免两套口径。

用法：
  python3 scripts/research/w7b_gui_headless_recheck.py \
    --campaign w7-rl-b --out-run-id 20261025-w7-rl-b-gui-headless-recheck

产物：`experiments/<campaign>/<out_run_id>/metrics/gui_headless.{json,md}`。
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import w7b_worker_repeatability as rep  # noqa: E402 - 同目录复用只读解析

ROOT = '/home/chen/AGC'

# 全部尝试（R5 清单）；label 前缀 P1/P2 仅用于分组表达，不参与 P1/P2 判定
ATTEMPTS = [
    {'label': 'p1-headless', 'run_id': '20261024-w7-rl-b-b-p1-s15-s5-headless',
     'kind': 'headless', 'scene': 's15_static_none_fov_capture',
     'arm': 'p1_coop', 'seed': 5},
    {'label': 'p1-gui-a0', 'run_id': '20261024-w7-rl-b-b-p1-s15-s5-gui',
     'kind': 'gui', 'scene': 's15_static_none_fov_capture',
     'arm': 'p1_coop', 'seed': 5},
    {'label': 'p1-gui-r2', 'run_id': '20261024-w7-rl-b-b-p1-s15-s5-gui-r2',
     'kind': 'gui', 'scene': 's15_static_none_fov_capture',
     'arm': 'p1_coop', 'seed': 5},
    {'label': 'p2-head-s0', 'run_id': '20261024-w7-rl-b-b-p2-s08-s012-headless',
     'kind': 'headless', 'scene': 's08_static_none_nominal_capture',
     'arm': 'p2_rl_high', 'seed': 0},
    {'label': 'p2-head-s1', 'run_id': '20261024-w7-rl-b-b-p2-s08-s012-headless',
     'kind': 'headless', 'scene': 's08_static_none_nominal_capture',
     'arm': 'p2_rl_high', 'seed': 1},
    {'label': 'p2-head-s2', 'run_id': '20261024-w7-rl-b-b-p2-s08-s012-headless',
     'kind': 'headless', 'scene': 's08_static_none_nominal_capture',
     'arm': 'p2_rl_high', 'seed': 2},
    {'label': 'p2-gui-s0', 'run_id': '20261024-w7-rl-b-b-p2-s08-s0-gui',
     'kind': 'gui', 'scene': 's08_static_none_nominal_capture',
     'arm': 'p2_rl_high', 'seed': 0},
]

ATTEMPT_FIELDS = (
    'label', 'run_id', 'kind', 'scene', 'arm', 'seed', 'terminal_state',
    'reason_code', 'outcome_class', 'infra_retries_used',
    'legacy_fixed_fco', 'legacy_fixed_visibility',
    'active_fco', 'active_visibility', 'env_occ_given_visible',
    'window_enter_s', 'window_leave_s', 'window_duration_s',
    'first_fco_rel_s', 'first_envelope_rel_s',
    'n_shots', 'first_shot_t_s', 'capture_t_s', 'flight_s',
    'rtf', 'wall_elapsed_s', 'sim_start_s', 'sim_end_s',
    'target_reject_ratio', 'px4_blind_land_n', 'missing_fields', 'notes',
)


def load_attempt(campaign, spec, repo_root):
    case = rep.load_case(repo_root, campaign, spec['label'], spec['run_id'],
                         worker=None, seed=spec['seed'])
    attempt = {key: case.get(key) for key in ATTEMPT_FIELDS}
    attempt['kind'] = spec['kind']
    attempt['scene'] = spec['scene']
    attempt['arm'] = spec['arm']
    attempt['seed'] = spec['seed']
    attempt['status_note'] = status_note(attempt)
    # wall_elapsed_s 来自 arms.json 行；load_case 未暴露，回读一次（只读）
    attempt['wall_elapsed_s'] = read_wall_elapsed(case, repo_root, campaign)
    return attempt


def read_wall_elapsed(case, repo_root, campaign):
    run_dir = os.path.join(repo_root, 'experiments', campaign, case['run_id'])
    arms_path = os.path.join(run_dir, 'metrics', 'arms.json')
    try:
        with open(arms_path) as f:
            arms = json.load(f).get('arms') or []
        row = rep.select_arm_row(arms, case.get('seed'))
        return (row or {}).get('wall_elapsed_s')
    except Exception:  # noqa: BLE001 - 缺失即 null
        return None


def status_note(attempt):
    terminal = attempt.get('terminal_state')
    if terminal == 'MISSION_FAILED':
        return ('MISSION_FAILED(%s)：mission 终态（契约 C4），**不是 infra**；'
                'infra_retries_used=%s' % (
                    attempt.get('reason_code') or '-',
                    attempt.get('infra_retries_used')))
    if terminal in rep.OK_TERMINALS:
        return 'mission 成功终态 %s(%s)' % (terminal, attempt.get('reason_code') or '-')
    if terminal is None:
        return '终态缺失'
    return '终态 %s(%s)' % (terminal, attempt.get('reason_code') or '-')


def pair_summary(name, head_label, gui_label, attempts):
    by = {a['label']: a for a in attempts}
    h, g = by.get(head_label), by.get(gui_label)
    if not h or not g:
        return {'pair': name, 'status': 'not_evaluated',
                'reason': '缺少 headless 或 GUI 尝试'}
    def d(key):
        a, b = h.get(key), g.get(key)
        return None if (a is None or b is None) else b - a
    return {
        'pair': name,
        'status': 'descriptive',
        'headless': head_label,
        'gui': gui_label,
        'headless_terminal': h.get('terminal_state'),
        'gui_terminal': g.get('terminal_state'),
        'headless_active_fco': h.get('active_fco'),
        'gui_active_fco': g.get('active_fco'),
        'delta_active_fco': d('active_fco'),
        'headless_active_visibility': h.get('active_visibility'),
        'gui_active_visibility': g.get('active_visibility'),
        'delta_active_visibility': d('active_visibility'),
        'delta_env_occ_given_visible': d('env_occ_given_visible'),
        'delta_window_enter_s': d('window_enter_s'),
        'delta_window_duration_s': d('window_duration_s'),
        'delta_first_fco_rel_s': d('first_fco_rel_s'),
        'delta_legacy_fixed_fco': d('legacy_fixed_fco'),
        'note': '单次 GUI 成功 vs 单次 headless；描述性，不构成等价证据',
    }


def build_conclusion(pairs, attempts):
    by = {a['label']: a for a in attempts}
    reasons = []
    a0 = by.get('p1-gui-a0')
    if a0:
        reasons.append(
            'P1 GUI 首跑 terminal=%s(%s)，active FCO=%s、active vis=%s、窗口 %s→%s s；'
            '属 mission 终态（契约 C4），**不是 infra**（infra_retries_used=%s）。' % (
                a0.get('terminal_state'), a0.get('reason_code') or '-',
                fmt(a0.get('active_fco')), fmt(a0.get('active_visibility')),
                fmt(a0.get('window_enter_s'), '%.1f'),
                fmt(a0.get('window_leave_s'), '%.1f'),
                fmt(a0.get('infra_retries_used'), '%d')))
    p1 = next((p for p in pairs if p['pair'] == 'P1'), None)
    if p1 and p1.get('status') == 'descriptive':
        reasons.append(
            'P1：headless active FCO=%s，GUI 重跑=%s；active 可见率 %s vs %s；'
            '窗口 %s→%s vs %s→%s s；两次成功差异远大于可重复性范围。' % (
                fmt(p1['headless_active_fco']), fmt(p1['gui_active_fco']),
                fmt(p1['headless_active_visibility']), fmt(p1['gui_active_visibility']),
                fmt(by['p1-headless'].get('window_enter_s'), '%.1f'),
                fmt(by['p1-headless'].get('window_leave_s'), '%.1f'),
                fmt(by['p1-gui-r2'].get('window_enter_s'), '%.1f'),
                fmt(by['p1-gui-r2'].get('window_leave_s'), '%.1f')))
    p2 = next((p for p in pairs if p['pair'] == 'P2-s08-seed0'), None)
    if p2 and p2.get('status') == 'descriptive':
        reasons.append(
            'P2 s08 seed0：headless active FCO=%s，GUI=%s（约 %s×）；'
            '窗口时长 %s vs %s s；首次 FCO %s vs %s s。' % (
                fmt(p2['headless_active_fco']), fmt(p2['gui_active_fco']),
                fmt((p2['headless_active_fco'] / p2['gui_active_fco'])
                    if p2.get('gui_active_fco') else None, '%.1f'),
                fmt(by['p2-head-s0'].get('window_duration_s'), '%.1f'),
                fmt(by['p2-gui-s0'].get('window_duration_s'), '%.1f'),
                fmt(by['p2-head-s0'].get('first_fco_rel_s'), '%.1f'),
                fmt(by['p2-gui-s0'].get('first_fco_rel_s'), '%.1f')))
    reasons.append('GUI 首跑为 mission 超时（MISSION_FAILED(TIMEOUT)），只有一次成功 GUI 重跑；'
                   'P1 与 P2 各只有 1 次成功 GUI，无法估计 GUI 自身的重复性。')
    reasons.append('B 报告使用 legacy 固定窗指标，且只列成功 GUI；本复核未改写原报告，'
                   '以 active 口径补充。')
    return {
        'verdict': 'not_established',
        'text': 'GUI / headless 数值等价未建立 / 证据不足',
        'reasons': reasons,
    }


def fmt(v, pattern='%.4f'):
    return rep.fmt(v, pattern)


def md_table(headers, rows):
    return rep.md_table(headers, rows)


def render_md(data):
    md = ['# GUI / headless 同口径复核 · %s' % data['out_run_id'], '',
          '> **描述性复核，不参与 P1 / P2 判定。** 只用既有产物；**不**新增 GUI run，'
          '**不**改写既有 B 报告 / checklist / ADR；全部尝试保留（含 P1 GUI 首跑超时）。', '',
          '- campaign: `%s`' % data['campaign'],
          '- generated_by: `scripts/research/w7b_gui_headless_recheck.py`（复用 '
          '`scripts/research/w7b_worker_repeatability.py` 的解析）',
          '- generated_at: `%s`' % data['generated_at'],
          '- 口径：active 窗口 primary；legacy `window_fixed_v1` 仅作描述（含终态后停泊）。',
          '']

    md += ['## 结论', '',
           '**%s**' % data['conclusion']['text'], '']
    md += ['- %s' % r for r in data['conclusion']['reasons']]
    md += ['']

    md += ['## 全部尝试（含失败）', '',
           '| 尝试 | 类型 | scene/arm/seed | terminal | legacy FCO | legacy vis | active FCO | active vis | env_occ\\|vis | window enter→leave (s) | 时长 (s) | 首次 FCO (s) | infra | 备注 |',
           '|---|---|---|---|---|---|---|---|---|---|---|---|---|---|']
    for a in data['attempts']:
        scene = '%s / %s / s%s' % (a.get('scene') or '-', a.get('arm') or '-',
                                   a.get('seed'))
        win = '%s→%s' % (fmt(a.get('window_enter_s'), '%.1f'),
                         fmt(a.get('window_leave_s'), '%.1f'))
        md.append('| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |' % (
            a['label'], a['kind'], scene, a.get('terminal_state') or '-',
            fmt(a.get('legacy_fixed_fco')), fmt(a.get('legacy_fixed_visibility')),
            fmt(a.get('active_fco')), fmt(a.get('active_visibility')),
            fmt(a.get('env_occ_given_visible')), win,
            fmt(a.get('window_duration_s'), '%.2f'),
            fmt(a.get('first_fco_rel_s'), '%.2f'),
            fmt(a.get('infra_retries_used'), '%d'), a.get('status_note') or '-'))
    md += ['', '补充：', '']
    for a in data['attempts']:
        md.append('- **%s**：n_shots=%s，first shot t=%s，capture t=%s，flight=%s，'
                  'RTF=%s，wall=%s s，目标拒绝比例=%s。' % (
                      a['label'], fmt(a.get('n_shots'), '%d'),
                      fmt(a.get('first_shot_t_s'), '%.2f'),
                      fmt(a.get('capture_t_s'), '%.2f'),
                      fmt(a.get('flight_s'), '%.3f'), fmt(a.get('rtf')),
                      fmt(a.get('wall_elapsed_s'), '%.1f'),
                      fmt(a.get('target_reject_ratio'), '%.3f')))
    md += ['']

    md += ['## 同 seed 对照（描述性）', '',
           '| 对照 | headless | GUI | Δactive FCO | Δactive vis | Δenv_occ | Δwindow enter | Δwindow 时长 | Δfirst FCO | Δlegacy FCO |',
           '|---|---|---|---|---|---|---|---|---|---|']
    for p in data['pairs']:
        if p.get('status') != 'descriptive':
            md.append('| %s | - | - | - | - | - | - | - | - | - |' % p['pair'])
            continue
        md.append('| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |' % (
            p['pair'], p['headless'], p['gui'],
            fmt(p['delta_active_fco']), fmt(p['delta_active_visibility']),
            fmt(p['delta_env_occ_given_visible']),
            fmt(p['delta_window_enter_s'], '%.2f'),
            fmt(p['delta_window_duration_s'], '%.2f'),
            fmt(p['delta_first_fco_rel_s'], '%.2f'),
            fmt(p['delta_legacy_fixed_fco'])))
    md += ['', '> 两次成功（P1 重跑、P2 seed0 GUI）只是两次观测，不能证明数值等价；'
           'P1 首跑超时也必须与成功重跑同时保留。', '']

    md += ['## 为 W8 需要的重复数与指标建议', '']
    for line in data['w8_needs']['items']:
        md.append('- %s' % line)
    md += ['']

    md += ['## 缺失 / 备注', '']
    any_missing = False
    for a in data['attempts']:
        if a.get('missing_fields') or a.get('notes'):
            any_missing = True
            md.append('- **%s**：缺失字段 %s；备注：%s' % (
                a['label'], ', '.join(a.get('missing_fields') or []) or '无',
                '；'.join(a.get('notes') or []) or '无'))
    if not any_missing:
        md.append('- 无缺失字段 / 日志。')
    md += ['', '> 证据边界：本报告只重排既有产物；GUI / headless 的等价需要预声明重复设计，'
           '不能在 n=1 的成功对上宣称。']
    return '\n'.join(md) + '\n'


W8_NEEDS = {
    'n_gui': 3,
    'n_headless': 3,
    'recommended_n': 5,
    'items': [
        '每条件至少 3 次（建议 5 次）GUI 与 headless，同 scene / arm / seed，交替执行；'
        '全部尝试保留（含失败），不用重跑成功替代。',
        'primary 指标：active FCO（`ticks_fire_control_opportunity / vis_ticks_total`）、'
        'active 可见率、`env_occ|visible`、active 窗口 enter / leave / 时长、首次 FCO；'
        'legacy 固定窗指标只作描述。',
        '预声明等价判据（示例）：GUI 与 headless 的 active FCO 中位数差 ≤ 0.01，'
        'active 可见率均 ≥ 0.90，窗口 enter 落在对方 [min−5 s, max+5 s]；'
        '并在报告中给出区间 / 散布，而不是只看均值。',
        'GUI 侧额外记录 wall elapsed / RTF / 交互事件；mission 超时与 infra 分列，'
        '不把 GUI 超时读作隔离或任务失败。',
        '至少覆盖 P1 s15 与 P2 s08 两个场景（及多个 seed），否则“等价”不具外推性。',
        '若 GUI 成功率 < 100%，需报告失败率与原因；等价结论仅在成功率可比时成立。',
    ],
}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--campaign', default='w7-rl-b')
    ap.add_argument('--out-run-id', default='20261025-w7-rl-b-gui-headless-recheck')
    ap.add_argument('--repo-root', default=ROOT)
    args = ap.parse_args()

    repo_root = os.path.abspath(args.repo_root)
    attempts = [load_attempt(args.campaign, spec, repo_root) for spec in ATTEMPTS]
    pairs = [
        pair_summary('P1', 'p1-headless', 'p1-gui-r2', attempts),
        pair_summary('P2-s08-seed0', 'p2-head-s0', 'p2-gui-s0', attempts),
    ]
    conclusion = build_conclusion(pairs, attempts)
    data = {
        'kind': 'descriptive_recheck（描述性复核，不参与 P1 / P2 判定）',
        'generated_by': 'scripts/research/w7b_gui_headless_recheck.py',
        'generated_at': datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds'),
        'campaign': args.campaign,
        'out_run_id': args.out_run_id,
        'source_note': '仅重排既有产物；未启动新 GUI run；未改写既有 B 报告',
        'attempts': attempts,
        'pairs': pairs,
        'conclusion': conclusion,
        'w8_needs': W8_NEEDS,
    }

    out_dir = os.path.join(repo_root, 'experiments', args.campaign, args.out_run_id,
                           'metrics')
    os.makedirs(out_dir, exist_ok=True)
    json_path = os.path.join(out_dir, 'gui_headless.json')
    md_path = os.path.join(out_dir, 'gui_headless.md')
    with open(json_path, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    with open(md_path, 'w') as f:
        f.write(render_md(data))
    print('-> %s\n-> %s' % (json_path, md_path))
    print('conclusion: %s' % conclusion['text'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
