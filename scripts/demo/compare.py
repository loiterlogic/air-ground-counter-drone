#!/usr/bin/env python3
"""`run_demo.sh compare <gui-run-dir> <headless-run-dir>` —— GUI ↔ headless 等价核验。

**口径不是本脚本定的**：全部读
[`experiments/p1-2//preregistration/gui-headless-equivalence.json`](../../experiments/p1-2//preregistration/gui-headless-equivalence.json)
（在**任何真实运行之前**落盘的预登记，见 [](../../docs/ROS2迁移交接文档.md#hard-constraints)）。
脚本只做三件事：取值 → 按预登记规则判定 → 输出可引用的判定与逐项明细。

四类结论（与预登记 `verdict_rule` 一一对应）：

 * `EQUIVALENT` —— primary 全过 + secondary 全在容差内；
 * `NOT_EQUIVALENT` —— 任一 primary 不符（**硬失败**）；
 * `NOT_COMPARABLE` —— primary 全过但 secondary 超差；
 * `INCOMPLETE` —— 任一臂缺 summary / 缺必需字段（**不得推断**）。

纪律：缺值一律判失败/不可比，**绝不**把 `None` / `not_applicable` 当作 0 或"相等"。
"""

import json
import os
import sys

import common

PREREG_DEFAULT = os.path.join(common.ROOT, 'experiments', 'p1-2', 'round-2',
                             'preregistration', 'gui-headless-equivalence.json')

NUMERIC = (int, float)


def _is_num(v):
    return isinstance(v, NUMERIC) and not isinstance(v, bool) and v == v   # 排除 NaN


def _dig(run_doc, path):
    """按预登记的**点号路径**取值。

 预登记里的路径是相对 `result.json` 的（`summary.terminal_state`、
 `summary.episode_window_metrics.ticks_total`、`derived.sim_end_minus_sim_start_s`）。
 `summary.*` 落在 `result['summary']`（run_logger summary 的切片），`derived.*` 由本模块派生。
    """
    if path.startswith('derived.'):
        return _derived((run_doc or {}).get('summary') or {}, path[len('derived.'):])
    cur = run_doc
    for part in path.split('.'):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _derived(sum_doc, name):
    if name == 'sim_end_minus_sim_start_s':
        s, e = sum_doc.get('sim_start_s'), sum_doc.get('sim_end_s')
        if _is_num(s) and _is_num(e):
            return e - s
        return None
    return None


def load_run(run_dir):
    """读一臂的 `result.json`（含 summary 切片）。缺文件 → `(None, 原因)`。"""
    path = os.path.join(run_dir, 'result.json')
    doc = common.read_json(path)
    if doc is None:
        return None, '缺少/无法解析 %s' % path
    if not doc.get('summary'):
        return doc, '该 run 没有关联到 metrics/summary.json（summary_error=%r）' % (
            doc.get('summary_error'),)
    return doc, ''


def _rel_ok(a, b, tol):
    if not (_is_num(a) and _is_num(b)):
        return False, '非数值（%r vs %r）' % (a, b)
    base = max(abs(a), abs(b))
    if base == 0:
        return True, '两者均为 0'
    rel = abs(a - b) / base
    return rel <= tol, '相对差 %.3f（容差 %.2f）' % (rel, tol)


def _abs_ok(a, b, tol):
    if not (_is_num(a) and _is_num(b)):
        return False, '非数值（%r vs %r）' % (a, b)
    d = abs(a - b)
    return d <= tol, '绝对差 %.4f（容差 %.2f）' % (d, tol)


def compare(gui, head, prereg):
    """返回 `{verdict, primary: [...], secondary: [...], report_only: {...}, reasons: [...]}`。"""
    primary, secondary, reasons = [], [], []

    for item in prereg.get('primary_criteria', {}).get('items', []):
        iid = item['id']
        g = _dig(gui, item['path'])
        h = _dig(head, item['path'])
        rule = item['rule']
        ok, why = False, ''
        if rule == 'exact_equal':
            ok = (g is not None and h is not None and g == h)
            why = '完全一致' if ok else '不一致或缺失'
        elif rule == 'both_false':
            ok = (g is False and h is False)
            why = '两臂均 false' if ok else '并非两臂均 false'
        elif rule == 'both_numeric_and_exact_equal':
            ok = (_is_num(g) and _is_num(h) and g == h)
            why = '两臂均为数值且相等' if ok else '缺值 / 非数值 / 不相等（不得把缺值当 0）'
        elif rule == 'relative_tolerance':
            ok, why = _rel_ok(g, h, float(item.get('tolerance') or 0))
        else:
            why = '未知规则 %r' % rule
        req = item.get('required')
        if ok and req is not None and g != req:
            ok, why = False, '值 %r 不等于预登记要求 %r' % (g, req)
        primary.append({'id': iid, 'path': item['path'], 'gui': g, 'headless': h,
                        'rule': rule, 'ok': bool(ok), 'detail': why})
        if not ok:
            reasons.append('primary 未过：%s（%s）' % (iid, why))

    for item in prereg.get('secondary_criteria', {}).get('items', []):
        iid = item['id']
        g = _dig(gui, item['path'])
        h = _dig(head, item['path'])
        rule = item['rule']
        if rule == 'relative_tolerance':
            ok, why = _rel_ok(g, h, float(item.get('tolerance') or 0))
        elif rule == 'absolute_tolerance':
            ok, why = _abs_ok(g, h, float(item.get('tolerance') or 0))
        else:
            ok, why = False, '未知规则 %r' % rule
        secondary.append({'id': iid, 'path': item['path'], 'gui': g, 'headless': h,
                          'rule': rule, 'tolerance': item.get('tolerance'),
                          'ok': bool(ok), 'detail': why})
        if not ok:
            reasons.append('secondary 超差：%s（%s）' % (iid, why))

    rep = {}
    for key in prereg.get('report_only_no_gate', {}).get('items', []):
        rep[key] = {'gui': _dig(gui, key), 'headless': _dig(head, key)}

    if any(not p['ok'] for p in primary):
        verdict = 'NOT_EQUIVALENT'
    elif any(not s['ok'] for s in secondary):
        verdict = 'NOT_COMPARABLE'
    else:
        verdict = 'EQUIVALENT'
    return {'verdict': verdict, 'primary': primary, 'secondary': secondary,
            'report_only': rep, 'reasons': reasons}


def gui_evidence_check(run_doc, expect_mode):
    """GUI 形态的四类证据核对（headless 臂返回 not_applicable，不算通过）。"""
    ev = (run_doc or {}).get('evidence') or {}
    claim = ev.get('gui_claim') or {}
    if expect_mode == 'headless':
        return {'mode': 'headless', 'verdict': 'not_applicable',
                'note': 'headless 臂不产生 GUI 证据，也不得据此宣称 GUI 通过'}
    checks = claim.get('checks') or {}
    return {'mode': 'gui',
            'verdict': claim.get('verdict'),
            'checks': checks,
            'reason': claim.get('reason'),
            'rviz_singletons': ev.get('rviz_singletons')}


def render(doc, stream=None):
    stream = stream or sys.stdout
    w = 34
    out = ['=' * 78,
           '[compare] GUI ↔ headless 等价核验（口径来自预登记文件，不在本脚本里改）',
           '=' * 78]
    for label, rows in (('PRIMARY（硬门）', doc['primary']), ('SECONDARY（容差）', doc['secondary'])):
        out.append('[compare] %s' % label)
        for r in rows:
            mark = 'OK  ' if r['ok'] else 'FAIL'
            out.append('[compare]   %s %-*s gui=%-12s headless=%-12s %s'
                       % (mark, w, r['id'], r['gui'], r['headless'], r['detail']))
    out.append('[compare] REPORT-ONLY（不作等价硬门）')
    for k, v in doc['report_only'].items():
        out.append('[compare]         %-*s gui=%-14s headless=%s' % (w, k, v['gui'], v['headless']))
    g = doc.get('gui_evidence') or {}
    out.append('[compare] GUI 证据核对：%s（%s）' % (g.get('verdict'), g.get('reason') or '-'))
    if g.get('rviz_singletons'):
        rs = g['rviz_singletons']
        out.append('[compare]   RViz 叠加份数：rviz2=%s viz_markers=%s world_frame_tf=%s'
                   % (rs.get('rviz2'), rs.get('viz_markers'), rs.get('world_frame_tf')))
    out.append('[compare] ------ 结论：%s' % doc['verdict'])
    for r in doc.get('reasons') or []:
        out.append('[compare]   · %s' % r)
    out.append('=' * 78)
    print('\n'.join(out), file=stream, flush=True)
    return doc['verdict']


def main(argv):
    if len(argv) < 3:
        return common.fail('compare 用法：run_demo.sh compare <gui-run-dir> <headless-run-dir>',
                           ['两个参数都是 experiments/demo/<timestamp>/ 目录'])
    gui_dir, head_dir = argv[1], argv[2]
    prereg = common.read_json(PREREG_DEFAULT)
    if prereg is None:
        return common.fail('找不到等价预登记文件', [PREREG_DEFAULT])
    gui, g_err = load_run(gui_dir)
    head, h_err = load_run(head_dir)
    if g_err or h_err:
        for err in (g_err, h_err):
            if err:
                print('[compare] 缺数据：%s' % err, file=sys.stderr)
        # INCOMPLETE 仍然落盘（不推断）
        doc = {'schema': 'demo-equivalence-v1', 'verdict': 'INCOMPLETE',
               'errors': [e for e in (g_err, h_err) if e],
               'gui_run_dir': gui_dir, 'headless_run_dir': head_dir,
               'prereg': PREREG_DEFAULT}
        _emit(doc, prereg)
        render(doc)
        return 4
    doc = compare(gui, head, prereg)
    doc.update({
        'schema': 'demo-equivalence-v1',
        'gui_run_dir': gui_dir,
        'headless_run_dir': head_dir,
        'gui_run_id': ((gui.get('summary') or {}).get('run_id')),
        'headless_run_id': ((head.get('summary') or {}).get('summary_id')
                            or (head.get('summary') or {}).get('run_id')),
        'prereg': PREREG_DEFAULT,
        'prereg_sha256': common.sha256_file(PREREG_DEFAULT),
        'prereg_registered_at': prereg.get('registered_at'),
        'gui_evidence': gui_evidence_check(gui, 'gui'),
        'headless_evidence': gui_evidence_check(head, 'headless'),
    })
    # GUI 证据不齐时**升级**结论（GUI 臂没拿到四类证据 → 不能宣称 GUI 通过）
    if (doc['gui_evidence'].get('verdict') != 'ok'
            and doc['verdict'] in ('EQUIVALENT', 'NOT_COMPARABLE')):
        doc['verdict'] = 'NOT_EQUIVALENT'
        doc['reasons'] = (doc.get('reasons') or []) + [
            'GUI 证据不齐（%s）：%s' % (doc['gui_evidence'].get('verdict'),
                                      doc['gui_evidence'].get('reason'))]
    _emit(doc, prereg)
    render(doc)
    return 0 if doc['verdict'] == 'EQUIVALENT' else (5 if doc['verdict'] == 'NOT_COMPARABLE' else 6)


def _emit(doc, prereg):
    out_dir = os.path.join(common.ROOT, 'experiments', 'p1-2', 'round-2', 'equivalence')
    common.ensure_dir(out_dir)
    path = os.path.join(out_dir, 'gui-headless.json')
    common.write_json(path, doc)
    md = ['# GUI ↔ headless 等价核验', '',
          '- 结论：**%s**' % doc['verdict'],
          '- GUI 臂：`%s`' % doc.get('gui_run_dir'),
          '- headless 臂：`%s`' % doc.get('headless_run_dir'),
          '- run_id：`%s` vs `%s`' % (doc.get('gui_run_id'), doc.get('headless_run_id')),
          '- 预登记：`%s`（sha256 `%s`，注册于 `%s`）' % (
              doc.get('prereg'), (doc.get('prereg_sha256') or '')[:16] + '…',
              doc.get('prereg_registered_at')),
          '', '## Primary（硬门）', '', '| 判据 | GUI | headless | 规则 | 结果 | 说明 |',
          '|---|---|---|---|---|---|']
    for r in doc.get('primary') or []:
        md.append('| `%s` | `%s` | `%s` | %s | %s | %s |' % (
            r['id'], r['gui'], r['headless'], r['rule'],
            'PASS' if r['ok'] else '**FAIL**', r['detail']))
    md += ['', '## Secondary（预登记容差）', '',
           '| 判据 | GUI | headless | 容差 | 结果 | 说明 |', '|---|---|---|---|---|---|']
    for r in doc.get('secondary') or []:
        md.append('| `%s` | `%s` | `%s` | %s | %s | %s |' % (
            r['id'], r['gui'], r['headless'], r.get('tolerance'),
            'PASS' if r['ok'] else '**FAIL**', r['detail']))
    md += ['', '## Report only（不作硬门）', '', '| 字段 | GUI | headless |', '|---|---|---|']
    for k, v in (doc.get('report_only') or {}).items():
        md.append('| `%s` | `%s` | `%s` |' % (k, v['gui'], v['headless']))
    with open(os.path.join(out_dir, 'gui-headless.md'), 'w') as f:
        f.write('\n'.join(md) + '\n')


if __name__ == '__main__':
    sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
    sys.exit(main(sys.argv))
