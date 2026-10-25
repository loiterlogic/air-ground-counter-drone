#!/usr/bin/env python3
"""gui_renderer_evidence —— 逐 run 有界的 GUI 渲染后端证据（W8 P0 / T3）。

共享日志 `~/.gz/rendering/ogre2.log` 是 **全局** 资源：并行 GUI run 或日志轮转时，
“读取最近一次”（读整份文件取最后一条 Device Name）会把别的 run 的 renderer 记到本 run。
本模块用 **snapshot + probe** 把证据绑定到“本 run 开始前的那一版日志”：

  * `snapshot()`：记下 path / inode / size / mtime / 前缀 sha256（最多 4096 字节）；
  * `probe(snapshot)`：只读 **snapshot 之后新增 / 变化** 的那一段（有界），并返回
    `read_mode`（appended / whole_created / whole_replaced / whole_after_truncate / none）
    与本段解析出的 renderer；
  * `combine(startup, final)`：合并启动时与结束后的两次探测（冲突 → ambiguous）。

证据只保留命中行（最多 20 行）+ 段 sha256，**不**保存整份共享日志。纯 stdlib。

用法（tests 内可直接传 path）：
  snap = snapshot('/tmp/ogre2.log')
  ev = probe(snap)
"""

import hashlib
import os
import time

DEFAULT_LOG_PATH = os.path.expanduser('~/.gz/rendering/ogre2.log')
PREFIX_BYTES = 4096
MAX_MATCHED_LINES = 20


def snapshot(path=None):
    """记录当前日志的边界证据；文件不存在时 `exists=False`（其余身份字段为 None）。"""
    path = path or DEFAULT_LOG_PATH
    doc = {
        'path': path,
        'exists': False,
        'inode': None,
        'size': None,
        'mtime_ns': None,
        'prefix_len': 0,
        'prefix_sha256': None,
        'captured_at_unix_s': time.time(),
    }
    try:
        st = os.stat(path)
    except OSError:
        return doc
    doc['exists'] = True
    doc['inode'] = st.st_ino
    doc['size'] = st.st_size
    doc['mtime_ns'] = st.st_mtime_ns
    try:
        with open(path, 'rb') as f:
            prefix = f.read(min(st.st_size, PREFIX_BYTES))
    except OSError:
        return doc
    doc['prefix_len'] = len(prefix)
    doc['prefix_sha256'] = hashlib.sha256(prefix).hexdigest()
    return doc


def _parse_line(line):
    """命中行 → renderer 值；非命中返回 None。"""
    if 'Device Name:' in line:
        value = line.split('Device Name:', 1)[1]
    elif 'GL_RENDERER' in line:
        value = line.split('=', 1)[-1]
    else:
        return None
    value = value.strip()
    return value or None


def _parse_renderers(data):
    """从字节段解析 renderer：去重保序；同时保留命中行（最多 MAX_MATCHED_LINES）。"""
    renderers = []
    matched = []
    for raw in data.decode('utf-8', 'replace').splitlines():
        value = _parse_line(raw)
        if value is None:
            continue
        if value not in renderers:
            renderers.append(value)
        if len(matched) < MAX_MATCHED_LINES:
            matched.append(raw.strip())
    return renderers, matched


def _read_segment(path, offset):
    try:
        with open(path, 'rb') as f:
            if offset:
                f.seek(offset)
            return f.read()
    except OSError:
        return b''


def probe(snap):
    """相对 snapshot 做有界探测：只读新增 / 变化段，返回证据（不含整份日志）。"""
    snap = snap or {}
    path = snap.get('path') or DEFAULT_LOG_PATH
    ev = {
        'path': path,
        'status': 'no_output',
        'renderer': None,
        'renderers': [],
        'read_mode': 'none',
        'offset': None,
        'bytes_read': 0,
        'segment_sha256': None,
        'matched_lines': [],
        'pre': snap,
        'post': None,
        'probed_at_unix_s': time.time(),
    }

    try:
        st = os.stat(path)
    except OSError:
        ev['status'] = 'missing_after' if snap.get('exists') else 'absent'
        ev['post'] = snapshot(path)
        ev['probed_at_unix_s'] = time.time()
        return ev

    size = st.st_size
    if not snap.get('exists'):
        mode, offset = 'whole_created', 0
    elif snap.get('inode') != st.st_ino:
        mode, offset = 'whole_replaced', 0
    elif (size < (snap.get('size') or 0)
          or _prefix_now(path, size, snap.get('prefix_len') or 0)
          != snap.get('prefix_sha256')):
        mode, offset = 'whole_after_truncate', 0
    elif size > (snap.get('size') or 0):
        mode, offset = 'appended', snap.get('size') or 0
    else:
        mode, offset = 'none', None

    ev['read_mode'] = mode
    ev['offset'] = offset
    if mode != 'none':
        data = _read_segment(path, offset)
        ev['bytes_read'] = len(data)
        ev['segment_sha256'] = hashlib.sha256(data).hexdigest()
        renderers, matched = _parse_renderers(data)
        ev['renderers'] = renderers
        ev['matched_lines'] = matched
        if len(renderers) == 1:
            ev['status'] = 'ok'
            ev['renderer'] = renderers[0]
        elif len(renderers) > 1:
            ev['status'] = 'ambiguous'
        else:
            ev['status'] = 'no_output'
    else:
        ev['status'] = 'no_output'

    ev['post'] = snapshot(path)
    ev['probed_at_unix_s'] = time.time()
    return ev


def _prefix_now(path, size, prefix_len):
    """当前文件**同长度前缀**的 sha256（与 snapshot 口径一致；读不到 → None）。"""
    try:
        with open(path, 'rb') as f:
            return hashlib.sha256(f.read(min(size, prefix_len))).hexdigest()
    except OSError:
        return None


def combine(startup, final):
    """合并启动 / 结束两次探测：冲突即 ambiguous；仅启动 ok → ok_at_startup。"""
    out = {'renderer': None, 'status': 'no_output',
           'startup': startup, 'final': final}
    probes = [p for p in (startup, final) if isinstance(p, dict)]
    if not probes:
        return out
    if any(p.get('status') == 'ambiguous' for p in probes):
        out['status'] = 'ambiguous'
        return out

    startup_ok = isinstance(startup, dict) and startup.get('status') == 'ok'
    final_ok = isinstance(final, dict) and final.get('status') == 'ok'
    if final_ok:
        if startup_ok and startup.get('renderer') != final.get('renderer'):
            out['status'] = 'ambiguous'
            return out
        out['renderer'] = final.get('renderer')
        out['status'] = 'ok'
        return out
    if startup_ok:
        out['renderer'] = startup.get('renderer')
        out['status'] = 'ok_at_startup'
        return out

    source = final if isinstance(final, dict) else startup
    out['status'] = source.get('status') or 'no_output'
    return out
