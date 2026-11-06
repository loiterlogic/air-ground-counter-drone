#!/usr/bin/env python3
"""Read-only audit for ADR-0021 `mission_fco_fixed_budget_v1` evidence.

Validates summary block + interval ledger coverage/integrity; never adjudicates
scientific claims and never rewrites inputs.
"""
import argparse
import json
import math
import sys
from pathlib import Path


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v))


def _close(a, b, tol=1e-6):
    return _num(a) and abs(float(a) - float(b)) <= tol


class Audit:
    def __init__(self):
        self.checks = []

    def check(self, name, ok, reason='', expected=None, actual=None):
        self.checks.append({
            'check': name,
            'status': 'PASS' if ok else 'FAIL',
            'reason': reason,
            'expected': expected,
            'actual': actual,
        })

    def failures(self):
        return [c for c in self.checks if c['status'] == 'FAIL']


def _mission_record(summary_block, index):
    missions = summary_block.get('missions') or []
    return missions[index] if index < len(missions) else None


def audit(summary, ledger):
    a = Audit()
    block = summary.get('mission_fco_fixed_budget_v1')
    a.check('summary_block_present', isinstance(block, dict), 'missing block')
    if not isinstance(block, dict):
        return a

    a.check('definition_version',
            block.get('definition_version') == 'mission_fco_fixed_budget_v1',
            'unexpected version', 'mission_fco_fixed_budget_v1',
            block.get('definition_version'))
    budget = block.get('budget_s')
    a.check('budget_positive', _num(budget) and budget > 0, 'budget must be > 0',
            '>0', budget)
    if not (_num(budget) and budget > 0):
        return a

    missions = block.get('missions') or []
    a.check('mission_count_matches', block.get('mission_count') == len(missions),
            'mission_count != len(missions)', len(missions), block.get('mission_count'))

    ledger_missions = (ledger or {}).get('missions') or []
    a.check('ledger_version',
            (ledger or {}).get('definition_version') == 'mission_fco_fixed_budget_v1',
            'ledger definition_version mismatch', 'mission_fco_fixed_budget_v1',
            (ledger or {}).get('definition_version'))
    a.check('ledger_missions_match', len(ledger_missions) == len(missions),
            'ledger mission count mismatch', len(missions), len(ledger_missions))

    # 旧口径字段仍在且版本未被改写。
    vis = summary.get('visibility_metrics') or {}
    a.check('old_visibility_version', vis.get('definition_version') == 'window_fixed_v1',
            'old visibility definition_version changed', 'window_fixed_v1',
            vis.get('definition_version'))
    a.check('old_episode_window_metrics_present',
            isinstance(summary.get('episode_window_metrics'), dict),
            'episode_window_metrics missing')

    for i, m in enumerate(missions):
        name = 'mission[%d]' % i
        known = m.get('known_preterminal_s')
        missing = m.get('missing_preterminal_s')
        post = m.get('post_terminal_budget_s')
        fco = m.get('fco_exposure_s')
        for key, val in (('known', known), ('missing', missing), ('post', post), ('fco', fco)):
            a.check('%s.%s_numeric' % (name, key), _num(val), 'not finite', 'finite', val)
        if not all(_num(v) for v in (known, missing, post, fco)):
            continue

        coverage = known + missing + post
        a.check('%s.coverage' % name, _close(coverage, budget), 'coverage != budget',
                budget, coverage)
        a.check('%s.nonnegative' % name,
                min(known, missing, post, fco) >= -1e-9,
                'negative duration', '>=0', min(known, missing, post, fco))

        point = m.get('point_valid') is True
        bounds = m.get('bounds_valid') is True
        fraction = m.get('mission_fco_fraction')
        lower = m.get('identification_lower')
        upper = m.get('identification_upper')

        if point:
            a.check('%s.point_has_no_missing' % name, missing <= 1e-6,
                    'point_valid with missing interval', '<=0', missing)
            a.check('%s.point_fraction' % name,
                    _close(fraction, fco / budget),
                    'fraction != fco/budget', fco / budget, fraction)
            a.check('%s.point_bounds' % name, bounds, 'point_valid without bounds')
        else:
            a.check('%s.null_fraction_when_invalid' % name, fraction is None,
                    'invalid point must be null', None, fraction)
        if bounds:
            a.check('%s.lower' % name, _close(lower, fco / budget),
                    'lower != fco/budget', fco / budget, lower)
            a.check('%s.upper' % name, _close(upper, (fco + missing) / budget),
                    'upper != (fco+missing)/budget', (fco + missing) / budget, upper)
            a.check('%s.lower_le_upper' % name,
                    _num(lower) and _num(upper) and lower <= upper + 1e-9,
                    'lower > upper', 'lower<=upper', (lower, upper))
        else:
            a.check('%s.null_bounds_when_invalid' % name,
                    lower is None and upper is None,
                    'invalid bounds must be null', (None, None), (lower, upper))

        t0 = m.get('t0_s')
        if m.get('t0_seen') is True and _num(t0):
            if m.get('terminal_seen') is True and m.get('terminal_within_budget') is True:
                tau = m.get('terminal_s')
                a.check('%s.post_terminal' % name,
                        _close(post, budget - (tau - t0)),
                        'post != budget - (terminal-t0)', budget - (tau - t0), post)
            else:
                a.check('%s.post_zero_outside_budget' % name, _close(post, 0.0),
                        'post must be 0 when terminal outside budget', 0.0, post)

        rec = ledger_missions[i] if i < len(ledger_missions) else None
        a.check('%s.ledger_record_present' % name, isinstance(rec, dict), 'missing ledger record')
        if not isinstance(rec, dict):
            continue
        for key in ('t0_s', 'terminal_s', 'fco_exposure_s', 'mission_fco_fraction',
                    'point_valid', 'bounds_valid'):
            a.check('%s.ledger_matches.%s' % (name, key),
                    rec.get(key) == m.get(key),
                    'summary/ledger mismatch', m.get(key), rec.get(key))

        intervals = rec.get('intervals') or []
        if not intervals:
            a.check('%s.intervals_present' % name, m.get('t0_seen') is not True,
                    'no intervals for a measured mission')
            continue
        a.check('%s.intervals_start_t0' % name,
                _close(intervals[0].get('start_s'), t0),
                'first interval != t0', t0, intervals[0].get('start_s'))
        a.check('%s.intervals_end_budget' % name,
                _close(intervals[-1].get('end_s'), t0 + budget),
                'last interval != t0+budget', t0 + budget, intervals[-1].get('end_s'))
        cursor = t0
        sums = {'known': 0.0, 'missing': 0.0, 'post_terminal': 0.0, 'fco': 0.0}
        contiguous = True
        for iv in intervals:
            start, end = iv.get('start_s'), iv.get('end_s')
            if not (_num(start) and _num(end)):
                contiguous = False
                break
            if abs(start - cursor) > 1e-6 or end < start:
                contiguous = False
                break
            kind = iv.get('kind')
            if kind in sums:
                sums[kind] += end - start
            if kind == 'known' and iv.get('fco') is True:
                sums['fco'] += end - start
            cursor = end
        a.check('%s.intervals_contiguous' % name, contiguous, 'interval ledger not contiguous')
        a.check('%s.intervals_known' % name, _close(sums['known'], known),
                'known sum mismatch', known, sums['known'])
        a.check('%s.intervals_missing' % name, _close(sums['missing'], missing),
                'missing sum mismatch', missing, sums['missing'])
        a.check('%s.intervals_post' % name, _close(sums['post_terminal'], post),
                'post sum mismatch', post, sums['post_terminal'])
        a.check('%s.intervals_fco' % name, _close(sums['fco'], fco),
                'fco sum mismatch', fco, sums['fco'])

    return a


def main():
    ap = argparse.ArgumentParser(description='只读审核 mission_fco_fixed_budget_v1 证据')
    ap.add_argument('--run-dir', help='run 目录（含 metrics/summary.json 与 mission_fco_intervals.json）')
    ap.add_argument('--summary', help='summary.json 路径（与 --ledger 同用）')
    ap.add_argument('--ledger', help='mission_fco_intervals.json 路径')
    ap.add_argument('--out', help='JSON 审核结果落盘路径（可选）')
    args = ap.parse_args()

    if args.run_dir:
        run_dir = Path(args.run_dir)
        summary_path = run_dir / 'metrics' / 'summary.json'
        ledger_path = run_dir / 'metrics' / 'mission_fco_intervals.json'
    else:
        if not (args.summary and args.ledger):
            ap.error('需要 --run-dir 或 --summary + --ledger')
        summary_path = Path(args.summary)
        ledger_path = Path(args.ledger)

    summary = json.loads(summary_path.read_text())
    ledger = json.loads(ledger_path.read_text()) if ledger_path.is_file() else None
    audit_result = audit(summary, ledger)
    failures = audit_result.failures()
    result = {
        'ok': not failures,
        'summary_path': str(summary_path),
        'ledger_path': str(ledger_path),
        'checks': audit_result.checks,
        'failures': failures,
    }
    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    if args.out:
        Path(args.out).write_text(text + '\n')
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
