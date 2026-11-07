#!/usr/bin/env python3
"""终端状态面板（2 Hz，人眼可读，不刷屏）。

数据**全部**来自既有 `/agc/task/state`（`AgcTaskState`，[#messages]）与既有 `/clock`；
本模块**不新增话题、不发布任何东西**，也不自己算任何指标（配置文件是 `run_logger`）。

两副外观，**判据相同**：

 * 终端（tty）→ 方框原地重绘（`\\r` + 清行，2 Hz）；
 * 非终端（重定向 / 管道 / CI）→ 每 2 Hz 一行 `[mm:ss] 状态 · 说明 · 距离 · 用时`，
 行数受 `max_lines` 限流，避免日志洪水。

**headless 一样可用**：面板不依赖 GUI / RViz / 渲染（计划"不要把可观测性绑死在渲染上"）。
屏幕上的每一格都还会同步落一份 `panel.txt`（同一渲染的纯文本快照），供无终端场景复核。

文案来源**唯一**：全部走 [`status_map`](status_map.py)（"一处映射、多处引用"）。
"""

import os
import time

import status_map

REFRESH_HZ = 2.0                 # 计划要求：2 Hz 足够（人眼可读，不刷屏）
REFRESH_S = 1.0 / REFRESH_HZ

# 方框内宽（字符）；中文按 2 列宽计，`_pad` 负责对齐。
PANEL_WIDTH = 46


def human_elapsed(seconds):
    """`72.4` → `01:12`；负数 / None → `--:--`（不猜）。"""
    try:
        s = float(seconds)
    except (TypeError, ValueError):
        return '--:--'
    if s < 0 or s != s:          # NaN
        return '--:--'
    s = int(s)
    return '%02d:%02d' % (s // 60, s % 60)


def fmt_distance(m):
    """`8.4 m`；无目标（NaN / None）→ `未获得目标`（**不写 0 m**，那是假数据）。"""
    try:
        v = float(m)
    except (TypeError, ValueError):
        return '未获得目标'
    if v != v:                   # NaN
        return '未获得目标'
    return '%.1f m' % v


def fmt_age(age_s):
    """观测年龄；无观测 → `--`。"""
    try:
        v = float(age_s)
    except (TypeError, ValueError):
        return '--'
    if v != v:
        return '--'
    return '%.2f s' % v


def _display_width(text):
    """粗略显示宽度：CJK / 全角按 2 列（对齐方框用，够用即可）。"""
    width = 0
    for ch in text:
        width += 2 if ('\u1100' <= ch <= '\u115f' or '\u2e80' <= ch <= '\ua4cf'
                       or '\uac00' <= ch <= '\ud7a3' or '\uf900' <= ch <= '\ufaff'
                       or '\ufe30' <= ch <= '\ufe6f' or '\uff00' <= ch <= '\uff60'
                       or '\uffe0' <= ch <= '\uffe6') else 1
    return width


def _pad(text, width):
    return text + ' ' * max(0, width - _display_width(text))


def snapshot(fields):
    """把"当前该显示什么"整理成**与外观无关**的字段表（面板 / 单行 / 落盘共用一份）。"""
    state = status_map.state_by_name(fields.get('state_name'))
    return {
        'state': state['name'],
        'text': state['text'],
        'audience': state['audience'],
        'reason': status_map.reason_text(fields.get('reason_code')),
        'reason_raw': (fields.get('reason_code') or '').strip() or '-',
        'distance': fmt_distance(fields.get('distance_m')),
        'obs_age': fmt_age(fields.get('obs_age_s')),
        'air': fields.get('air_controller') or '--',
        'ground': fields.get('ground_controller') or '--',
        'elapsed': human_elapsed(fields.get('elapsed_s')),
        'terminal': status_map.is_terminal(state['name']),
        'milestone': bool(fields.get('tracking_milestone_met')),
    }


def render_box(fields):
    """方框外观（tty）：固定行高 + 固定列宽，便于 `\\r` 重绘不跳动。"""
    s = snapshot(fields)
    rows = (
        ('状态', s['state']),
        ('说明', s['text']),
        ('原因', s['reason_raw']),
        ('目标距离', s['distance']),
        ('观测年龄', s['obs_age']),
        ('空中控制', s['air']),
        ('地面控制', s['ground']),
        ('已用时', s['elapsed']),
    )
    label_w = 10                     # 显示列宽（CJK 记 2 列）：最长的「目标距离」占 8 列
    body = PANEL_WIDTH - 2
    out = ['┌─ AGC 任务状态 ' + '─' * max(0, PANEL_WIDTH - 12) + '┐']
    for label, value in rows:
        cell = _pad(label, label_w) + value
        out.append('│ ' + _pad(cell, body) + ' │')
    out.append('└' + '─' * body + '┘')
    return out


def render_line(fields):
    """单行外观（非 tty / 落盘）：一行说清"在干什么 + 为什么 + 多远 + 多久"。"""
    s = snapshot(fields)
    tail = '  [终态]' if s['terminal'] else ''
    return '[%s] %s · %s · 距离 %s · 原因 %s · 用时 %s%s' % (
        s['elapsed'], s['state'], s['text'], s['distance'], s['reason'], s['elapsed'],
        tail)


class Panel:
    """2 Hz 面板：`render()` 由跟随循环按节拍调用；**不自己起线程**（不引入第二个时钟）。

    两种外观，同一份 `snapshot()` 数据、同一个 2 Hz 节拍：

 * **终端（tty）**：方框原地重绘，每帧 `1/2 = 0.5 s`（真正 2 Hz，人眼可读、不刷屏）；
 * **非终端（重定向 / 管道 / 日志）**：退化为单行 + `line_every_s` 心跳。理由：
 计划要求"日志文件里只记跳变"，非终端没有"原地刷新"可言，硬刷 2 Hz 只会制造
 日志洪水；状态跳变本身由进度行与 `timeline.txt` 各记一次，这里不重复。
 真正的 2 Hz 节奏记在 `renders`（每帧都计数）与 `panel.txt` 里。

 `snapshot_path` 非空时每 `persist_every_s` 秒落一行 `panel.txt`：
 终端被关掉 / 会话断开后仍有可复核的面板证据。
    """

    def __init__(self, stream=None, snapshot_path=None, min_interval_s=REFRESH_S,
                 persist_every_s=1.0, line_every_s=5.0, max_lines=400):
        import sys
        self.stream = stream or sys.stdout
        self.snapshot_path = snapshot_path
        self.min_interval_s = float(min_interval_s)
        self.persist_every_s = float(persist_every_s)
        self.line_every_s = float(line_every_s)
        self.max_lines = int(max_lines)
        self._last_paint = 0.0
        self._last_persist = 0.0
        self._last_line = 0.0
        self._box_rows = 0
        self._last_state = None
        self._lines = 0
        self._suppressed = 0
        self.renders = 0
        self.mode = 'box' if self._isatty() else 'line'
        if self.snapshot_path:
            parent = os.path.dirname(self.snapshot_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(self.snapshot_path, 'w', encoding='utf-8') as f:
                f.write('# AGC 任务状态面板快照（节拍 %g Hz；与终端同源；%s 外观）\n'
                        % (REFRESH_HZ, self.mode))

    def _isatty(self):
        try:
            return bool(self.stream.isatty())
        except (AttributeError, ValueError):
            return False

    # -- 与其它输出共存 --
    def erase(self):
        """擦掉当前方框，把光标留给别的内容（`progress` 行）；下一次 `render` 重画。

 `line` 外观下是**空操作**（单行本来就只是一行）。
        """
        if self.mode != 'box' or not self._box_rows:
            return
        buf = '\r\033[%dA' % self._box_rows + ('\r\033[K\n' * self._box_rows)
        self._box_rows = 0
        try:
            self.stream.write(buf)
            self.stream.flush()
        except (OSError, ValueError):
            pass

    # -- 绘制 --
    def render(self, fields, force=False, now=None):
        """到 2 Hz 节拍就画一帧；未到节拍直接返回 False（调用方无需自己计时）。"""
        now = time.monotonic() if now is None else now
        if not force and (now - self._last_paint) < self.min_interval_s:
            return False
        self._last_paint = now
        self.renders += 1
        state_changed = fields.get('state_name') != self._last_state
        self._last_state = fields.get('state_name')
        if self.mode == 'box':
            self._paint_box(fields)
        else:
            self._paint_line(fields, force=force, state_changed=state_changed, now=now)
        if self.snapshot_path and (force or (now - self._last_persist) >= self.persist_every_s):
            self._last_persist = now
            self._persist(fields)
        return True

    def _paint_box(self, fields):
        rows = render_box(fields)
        buf = ''
        if self._box_rows:
            buf += '\r\033[%dA' % self._box_rows      # 回到框顶
        for row in rows:
            buf += '\r\033[K' + row + '\n'
        self._box_rows = len(rows)
        try:
            self.stream.write(buf)
            self.stream.flush()
        except (OSError, ValueError):
            pass

    def _paint_line(self, fields, force, state_changed, now):
        # 非 tty：状态跳变**已经**由进度行（`当前状态：…`）与 timeline 各记一次，
        # 这里不再重复整行（实测会出现同一状态连打两遍）；只按心跳 / 强制刷新出单行，
        # 让"距离在缩短"这类**连续变化**仍可读。2 Hz 节拍本身照常计数（`renders`）。
        due = (now - self._last_line) >= self.line_every_s
        if not (force or due):
            return
        if self._lines >= self.max_lines:
            self._suppressed += 1
            return
        self._last_line = now
        self._lines += 1
        try:
            self.stream.write(render_line(fields) + '\n')
            self.stream.flush()
        except (OSError, ValueError):
            pass

    def _persist(self, fields):
        try:
            with open(self.snapshot_path, 'a', encoding='utf-8') as f:
                f.write(render_line(fields) + '\n')
        except OSError:
            pass

    # -- 收尾 --
    def finish(self, extra=None):
        """离开面板：tty 下把光标移到框下方（不擦掉最后一帧，观众还看得见）。"""
        if self.mode == 'box' and self._box_rows:
            try:
                self.stream.write('\n')
                self.stream.flush()
            except (OSError, ValueError):
                pass
        try:
            if self.snapshot_path:
                with open(self.snapshot_path, 'a', encoding='utf-8') as f:
                    f.write('# 面板结束：节拍渲染 %d 帧（%g Hz），单行 %d 行，限流省略 %d 行\n'
                            % (self.renders, REFRESH_HZ, self._lines, self._suppressed))
                    for key, value in sorted((extra or {}).items()):
                        f.write('# %s：%s\n' % (key, value))
        except OSError:
            pass
        return {'renders': self.renders, 'mode': self.mode, 'lines': self._lines,
                'suppressed': self._suppressed, 'refresh_hz': REFRESH_HZ,
                'snapshot': self.snapshot_path}
