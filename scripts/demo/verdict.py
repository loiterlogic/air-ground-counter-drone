#!/usr/bin/env python3
"""终态"判定说明"——回答"为什么算成功 / 失败"。

两条硬纪律：

 1. **指标全部来自 `metrics/summary.json`**（`run_logger` 是配置文件）；展示层
 **不自己算**成功率、可见率、介入率——只读、只翻译、只标注字段名。
 2. **判定阈值不硬编码**：`d_track_m` / `t_dwell_s` / `t_max_s` 等一律从本 run 的
 `config/params_applied.yaml`（run_logger 落的**实际生效参数**快照）读取；
 读不到就**如实说"阈值来源缺失"**，绝不写死一个数假装知道。

（[#terminal-semantics]）：`TRACKING_SUCCESS` 的判定说明写"抵近并持续跟踪"，
并用 `status_map.PHASE_A_CAVEAT` 讲清它与阶段 B 拦截的区别（阶段 B 由 `INTERCEPT_CONFIRMED` +
`reason_code` 的 `CAPTURE_NET` / `JAM_*` 表达）。**禁词字面量只存在于 `status_map`**，
本模块不复制，避免静态禁词检查被"到处都是例外"绕空。

[#terminal-semantics]: ../../docs/adr/0014-task-fsm-and-scenario-transaction.md#terminal-semantics
"""

import os

import status_map

# 判定阈值在本 run 配置快照里的**所属节点段**（不在展示层写死任何数值）。
THRESHOLD_OWNER = 'task_manager'
THRESHOLD_KEYS = ('d_track_m', 't_dwell_s', 't_max_s',
                  'tracking_milestone_is_terminal', 'confidence_min', 'target_max_age_s')

# 说明块宽度（纯文本，无边框字符，便于粘贴进报告 / 幻灯片）
RULE = '=' * 66


def _fmt(value, unit=''):
    if value is None:
        return '未提供'
    if isinstance(value, bool):
        return '是' if value else '否'
    if isinstance(value, float):
        return ('%.3f' % value).rstrip('0').rstrip('.') + unit
    return '%s%s' % (value, unit)


def load_thresholds(config_path):
    """从 `params_applied.yaml` 的 `task_manager` 段取判定阈值（**唯一**阈值来源）。

 返回 `{'source': path|None, 'values': {...}, 'missing': [...]}`。
 解析用 PyYAML（ROS 环境自带）；不可用时退化为**逐行扫描**同一文件，
 两者都失败 → `source=None` 且 `missing` 列全，调用方必须如实标注。
    """
    out = {'source': None, 'values': {}, 'missing': list(THRESHOLD_KEYS)}
    if not config_path or not os.path.isfile(config_path):
        return out
    doc = None
    try:
        import yaml
        with open(config_path, encoding='utf-8') as f:
            doc = yaml.safe_load(f)
    except Exception:                       # noqa: BLE001 —— 解析失败退化为扫描
        doc = None
    if isinstance(doc, dict):
        section = (doc.get(THRESHOLD_OWNER) or {}).get('ros__parameters') or {}
        vals = {k: section[k] for k in THRESHOLD_KEYS if k in section}
    else:
        vals = _scan_flat_section(config_path, THRESHOLD_OWNER)
    out['source'] = config_path
    out['values'] = vals
    out['missing'] = [k for k in THRESHOLD_KEYS if k not in vals]
    return out


def _scan_flat_section(path, owner):
    """无 PyYAML 时的退化解析：定位 `owner:` 段下的 `ros__parameters:` 平铺键。"""
    vals = {}
    try:
        with open(path, encoding='utf-8') as f:
            lines = f.readlines()
    except OSError:
        return vals
    in_owner = False
    in_params = False
    for raw in lines:
        stripped = raw.strip()
        if not stripped or stripped.startswith('#'):
            continue
        if not raw.startswith(' ') and stripped.startswith(owner + ':'):
            in_owner, in_params = True, False
            continue
        if in_owner and not raw.startswith(' '):
            break                            # 下一个顶层键：本段结束
        if in_owner and stripped.startswith('ros__parameters:'):
            in_params = True
            continue
        if in_owner and in_params and ':' in stripped:
            key, _, value = stripped.partition(':')
            key, value = key.strip(), value.strip().strip('"')
            if key in THRESHOLD_KEYS:
                vals[key] = _coerce(value)
    return vals


def _coerce(text):
    if text in ('true', 'false'):
        return text == 'true'
    for cast in (int, float):
        try:
            return cast(text)
        except ValueError:
            continue
    return text


# --------------------------------------------------------------------------------------
# 判定说明
# --------------------------------------------------------------------------------------

def explain(summary, thresholds=None, terminal_state=None, terminal_reason=None,
            summary_path=None, expected_terminal=None):
    """返回 `{'lines': [...], 'fields': {...}}`——`lines` 直接打印 / 写进 result.json。

 `summary` 为 `None` 时不猜：明确写"summary 缺失，判定说明不可用"，并给出已观测到的
 终态（来自 `/agc/task/state`）与缺口，供审查者区分"没跑成"与"没记录"。
    """
    th = thresholds or {'source': None, 'values': {}, 'missing': list(THRESHOLD_KEYS)}
    doc = summary or {}
    state_name = (doc.get('terminal_state') or terminal_state or 'UNKNOWN')
    reason = (doc.get('terminal_reason_code') or terminal_reason or '')
    entry = status_map.state_by_name(state_name)
    lines = [RULE, 'AGC 终态判定说明（数据源：metrics/summary.json + config/params_applied.yaml）', RULE]

    # 1) 结果
    lines.append('结果      %s — %s' % (entry['name'], entry['text']))
    if entry['name'] == status_map.PHASE_A_SUCCESS:
        lines.append(status_map.PHASE_A_CAVEAT)
    elif entry['name'] == status_map.PHASE_B_INTERCEPT:
        lines.append(status_map.PHASE_B_CAVEAT)
    elif status_map.is_terminal(entry['name']):
        lines.append('口径      任务未成功；原因见下（判定不改写：超时一律算失败，C4）。')
    else:
        lines.append('口径      未观测到任务终态（当前 %s）；本次**不能**作为成功证据。'
                     % entry['name'])
    lines.append('触发原因  %s — %s' % (reason or '（无）', status_map.reason_text(reason)))

    # 2) 阈值（来自本 run 的生效参数快照，不硬编码）
    vals = th.get('values') or {}
    src = th.get('source')
    if vals:
        src_txt = os.path.basename(str(src)) if src else '未知'
        lines.append('判定阈值  %s' % ' / '.join(
            '%s=%s' % (k, _fmt(vals[k])) for k in THRESHOLD_KEYS if k in vals))
        lines.append('阈值来源  %s（%s 段，本 run 实际生效参数）'
                     % (src_txt, THRESHOLD_OWNER))
        if th.get('missing'):
            lines.append('阈值缺口  %s 未在本 run 快照中出现（**不猜**，按缺省语义理解）'
                         % ', '.join(th['missing']))
    else:
        lines.append('判定阈值  **阈值来源缺失**：未找到 %s 的 %s 段；'
                     '本说明**不**给出任何硬编码阈值' % (
                         os.path.basename(str(src)) if src else 'params_applied.yaml',
                         THRESHOLD_OWNER))
        lines.append('阈值缺口  %s' % ', '.join(th.get('missing') or THRESHOLD_KEYS))

    # 3) 用时 / 预算
    if doc:
        lines.append('用时      duration_s=%s s（进程墙钟，含预热/关闭；duration_kind=%s）'
                     % (_fmt(doc.get('duration_s')), doc.get('duration_kind') or '-'))
        if doc.get('sim_start_s') is not None and doc.get('sim_end_s') is not None:
            lines.append('仿真窗口  sim %.2f → %.2f s（%.2f s），RTF %s'
                         % (float(doc['sim_start_s']), float(doc['sim_end_s']),
                            float(doc['sim_end_s']) - float(doc['sim_start_s']),
                            _fmt(doc.get('rtf'))))
        if doc.get('ticks_total') is not None:
            lines.append('拍数      ticks_total=%s / ticks_triggered=%s'
                         % (doc.get('ticks_total'), doc.get('ticks_triggered')))

    # 4) 安全 / 复位（ 两指标）
    ca = doc.get('command_attribution') or {}
    if doc:
        lines.append('安全      shield_infeasible_rate=%s；介入 %s 段 / %s 拍（shield 层%s）'
                     % (_fmt(doc.get('shield_infeasible_rate')),
                        _fmt(ca.get('intervention_segments')), _fmt(ca.get('intervened_ticks')),
                        '启用' if ca.get('shield_layer_enabled') else '关闭'))
        if doc.get('true_shield_infeasible') is not None:
            lines.append('安全真值  true_shield_infeasible=%s（gz_contact_v1）'
                         % _fmt(doc.get('true_shield_infeasible')))
        lines.append('复位      reset_failure_rate=%s（reset_retries=%s，reset_failed=%s）'
                     % (_fmt(doc.get('reset_failure_rate')), _fmt(doc.get('reset_retries')),
                        _fmt(doc.get('reset_failed'))))

    # 5) 观测 / 接触（只在有值时打印，缺值不补 0）
    vis = doc.get('visibility_metrics') or {}
    if vis.get('visibility_rate') is not None:
        lines.append('目标可见  visibility_rate=%s（%s/%s 拍，窗口 %s s）'
                     % (_fmt(vis.get('visibility_rate')), vis.get('ticks_visible'),
                        vis.get('ticks_total'), _fmt(vis.get('window_s'))))
    if doc.get('collision_count') is not None:
        detail = ''
        ev = doc.get('collision_events') or []
        if ev:
            detail = '；' + '、'.join('%s@t=%.2fs' % (e.get('other', '?'),
                                                      float(e.get('t_sim') or 0.0))
                                     for e in ev[:3])
        lines.append('接触真值  collision_count=%s%s' % (doc.get('collision_count'), detail))

    # 6) 与期望终态的一致性（**只对照**，不改判定）
    if expected_terminal:
        same = state_name == expected_terminal
        lines.append('期望对照  期望 %s → %s'
                     % (expected_terminal, '一致' if same else '**不一致**'))

    # 7) 数据缺口（如实；不假装有）
    if not doc:
        lines.append('数据缺口  **未取得本 run 的 metrics/summary.json**：'
                     '上面只有 /agc/task/state 观测到的终态，全部指标缺失')
    if summary_path and doc:
        lines.append('数据源    %s' % summary_path)
    lines.append(RULE)
    return {'lines': lines,
            'fields': {'terminal_state': state_name, 'terminal_reason_code': reason,
                       'threshold_source': src, 'thresholds': vals,
                       'threshold_missing': th.get('missing') or [],
                       'summary_path': summary_path,
                       'c8_note': status_map.C8_NOTICE}}


if __name__ == '__main__':      # 离线自检：拿一个已有 run 的 summary 演示（纯读，T0）
    import json
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else ''
    doc = json.load(open(path, encoding='utf-8')) if path and os.path.isfile(path) else None
    cfg = os.path.join(os.path.dirname(os.path.dirname(path)), 'config', 'params_applied.yaml')
    print('\n'.join(explain(doc, load_thresholds(cfg), summary_path=path)['lines']))
