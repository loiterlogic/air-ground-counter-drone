#!/usr/bin/env python3
"""事件时间线——`experiments/demo/<timestamp>/timeline.txt`（P1-3 出口判据 3）。

**人读**的事件流，不替代机器可读的 `metrics/summary.json`（指标真源仍是 `run_logger`）。

记录什么：

  1. **状态跳变**——只在 `state_name` 真的变化时记一行（同一状态反复刷新**不**记，避免刷屏）；
  2. **演示生命周期节点**——启动 / 就绪 / 任务启动 / 终态 / 结果落盘；
  3. **终态后的补充说明**——从 `summary.json` **既有字段**读出来的事实（安全层介入次数、
     复位次数、可见率…），逐条标注来源，**不在展示层自己算指标**。

计数口径（P1-3 计划要求"至少 5 个关键节点"）：关键节点 = 上面 1+2 两类。
不足 5 个时**不凑数**，而是在文件末尾写清实际节点数、以及为什么少——
演示里只观测到 3 个状态跳变是**真实结果**，不是要掩盖的缺陷。
"""

import os
import time

import status_map

# 关键节点 = 状态跳变 + 生命周期节点。
# **不计入**两类：`note`（开场的参数 / 口径声明，是标注不是事件）、
# `summary`（终态后的解释，是结论不是事件）。这样"≥5 个关键节点"才真的在数**发生过什么**。
KIND_STATE = 'state'
KIND_LIFECYCLE = 'lifecycle'
KIND_NOTE = 'note'
KIND_SUMMARY = 'summary'

MIN_KEY_NODES = 5


def fmt_stamp(seconds):
    """`72.43` → `01:12.4`（相对起始时刻的墙钟；与 `progress.log` 的 `[mm:ss]` 同族）。"""
    s = max(0.0, float(seconds))
    return '%02d:%02d.%d' % (int(s) // 60, int(s) % 60, int((s * 10) % 10))


class Timeline:
    """落盘 + 终端双写的事件流；**只读**输入，不产生任何状态或指标。"""

    def __init__(self, path, stream=None, t0=None):
        self.path = path
        self.stream = stream
        self.t0 = time.monotonic() if t0 is None else t0
        self.nodes = []          # [(kind, t_s, text)] —— 关键节点
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._fh = open(path, 'w', encoding='utf-8')
        self._fh.write('# AGC 演示事件时间线（人读；指标真源是 metrics/summary.json）\n')
        self._fh.write('# 时刻 = 相对演示启动的墙钟，格式 [mm:ss.d]\n#\n')
        self._fh.flush()
        self._closed = False

    # -- 写 --
    def _write(self, line):
        self._fh.write(line + '\n')
        self._fh.flush()
        if self.stream is not None:
            try:
                self.stream.write(line + '\n')
                self.stream.flush()
            except (OSError, ValueError):
                pass

    def elapsed(self):
        return time.monotonic() - self.t0

    def event(self, text, kind=KIND_LIFECYCLE, at=None):
        """记一行事件；`kind` 决定它是否计入关键节点。"""
        t_s = self.elapsed() if at is None else float(at)
        line = '[%s] %s' % (fmt_stamp(t_s), text)
        self._write(line)
        if kind in (KIND_STATE, KIND_LIFECYCLE):
            self.nodes.append((kind, t_s, text))
        return line

    def state(self, state_name, reason_code='', distance_m=None, detail='', at=None):
        """状态跳变：`[00:03.2] 进入 AIR_SEARCH（无人机搜索中）— 原因 …`。

        `at` 是**相对本时间线起点**的秒数（调用方若已在别处算好时刻可直接传入）；
        缺省取写入瞬间。
        """
        entry = status_map.state_by_name(state_name)
        mark = '终态 ' if status_map.is_terminal(entry['name']) else '进入 '
        text = '%s%s（%s）' % (mark, entry['name'], entry['text'])
        bits = []
        if reason_code:
            bits.append('原因 %s/%s' % (reason_code, status_map.reason_text(reason_code)))
        if distance_m is not None and distance_m == distance_m:
            bits.append('目标距离 %.1f m' % float(distance_m))
        if detail:
            bits.append(detail)
        if bits:
            text += ' — ' + '；'.join(bits)
        return self.event(text, kind=KIND_STATE, at=at)

    def note(self, text):
        """开场标注（参数 / 口径 / 指向臂）：写进文件，但**不计入**关键节点。"""
        return self.event(text, kind=KIND_NOTE)

    def summary_note(self, text):
        """终态后的补充说明：明确标注来源，且**不计入**关键节点。"""
        return self.event('[summary.json] %s' % text, kind=KIND_SUMMARY)

    # -- 收尾 --
    def close(self, extra=None, note=''):
        """写脚注：节点计数 + 不足时的原因（**不凑数**）。"""
        if self._closed:
            return self.report()
        self._closed = True
        n_state = sum(1 for k, _t, _x in self.nodes if k == KIND_STATE)
        n_life = sum(1 for k, _t, _x in self.nodes if k == KIND_LIFECYCLE)
        n = len(self.nodes)
        lines = ['', '# ── 汇总 ──',
                 '# 关键节点：%d 个（状态跳变 %d + 生命周期 %d；判据 ≥%d）'
                 % (n, n_state, n_life, MIN_KEY_NODES)]
        if n < MIN_KEY_NODES and not note:
            note = ('本次演示实际只产生 %d 个关键节点：状态机走过的状态就这么多，'
                    '少于此数**不是**漏记，也不为凑数补编事件（观测到什么记什么）' % n)
        if note:
            lines.append('# 说明：%s' % note)
        for key, value in sorted((extra or {}).items()):
            lines.append('# %s：%s' % (key, value))
        for line in lines:
            self._fh.write(line + '\n')
        self._fh.flush()
        self._fh.close()
        return self.report()

    def report(self):
        n_state = sum(1 for k, _t, _x in self.nodes if k == KIND_STATE)
        n_life = sum(1 for k, _t, _x in self.nodes if k == KIND_LIFECYCLE)
        return {'path': self.path, 'key_nodes': len(self.nodes),
                'state_nodes': n_state, 'lifecycle_nodes': n_life,
                'meets_min': len(self.nodes) >= MIN_KEY_NODES,
                'min_required': MIN_KEY_NODES}


# --------------------------------------------------------------------------------------
# 终态后的 summary 补充说明（**只读既有字段，不另算指标**）
# --------------------------------------------------------------------------------------

def summary_notes(doc):
    """把 `summary.json` 的既有字段翻成一句句人话；缺字段就跳过（**不**补 0）。"""
    if not doc:
        return ['无 summary（本次未取得/未解析）——终态解释不可用，如实标注']
    out = []
    if doc.get('terminal_state'):
        out.append('终态 %s / reason %s（来源 %s，锁存 %s）'
                   % (doc.get('terminal_state'), doc.get('terminal_reason_code') or '-',
                      doc.get('terminal_state_source') or '-',
                      '是' if doc.get('terminal_state_latched') else '否'))
    ca = doc.get('command_attribution') or {}
    if ca:
        seg = ca.get('intervention_segments')
        ticks = ca.get('intervened_ticks')
        out.append('安全层介入：%s 段 / %s 拍（shield 层%s）'
                   % ('-' if seg is None else seg, '-' if ticks is None else ticks,
                      '启用' if ca.get('shield_layer_enabled') else '关闭'))
        if ca.get('clearance_min_m') is not None:
            out.append('最小净空 %.2f m（clearance_min_m）' % float(ca['clearance_min_m']))
    if doc.get('reset_retries') is not None:
        out.append('场景复位：重试 %s 次，失败 %s'
                   % (doc.get('reset_retries'), '是' if doc.get('reset_failed') else '否'))
    vis = doc.get('visibility_metrics') or {}
    if vis.get('visibility_rate') is not None:
        out.append('目标可见率 %.3f（%s/%s 拍）'
                   % (float(vis['visibility_rate']), vis.get('ticks_visible'),
                      vis.get('ticks_total')))
    if doc.get('collision_count') is not None:
        n = int(doc['collision_count'])
        detail = ''
        ev = (doc.get('collision_events') or [])[:3]
        if ev:
            detail = '；' + '、'.join('%s@t=%.2fs' % (e.get('other', '?'),
                                                      float(e.get('t_sim') or 0.0)) for e in ev)
        out.append('接触事件 %d 次%s' % (n, detail))
    return out
