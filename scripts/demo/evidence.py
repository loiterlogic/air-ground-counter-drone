#!/usr/bin/env python3
"""演示回合的**证据采集**（GUI 口径落地）。

Leader 裁定（[ 派工单](../../ADR-0026) 第 3 条）：
 **不要求**通用桌面截图工具，但 GUI 形态必须**同时**取得四类证据：

 | # | 证据 | 本模块怎么取 |
 |---|---|---|
 | 1 | 本 run Gazebo GUI **非 headless** 的进程/launch 证据 | 本 run PGID 的进程成员 + `gz sim` 命令行**无 `-s`** + launch 日志 `gazebo` 行 |
 | 2 | 本 run **OGRE renderer** 证据 | 复用 [`scripts/gui_renderer_evidence.py`](../gui_renderer_evidence.py) 的 `snapshot/probe/combine`（逐 run 有界） |
 | 3 | 本 run **X11 窗口**存在证据 | `xdpyinfo`（连通性）+ `xwininfo -root -tree`（窗口树），**原样保存**原始输出 |
 | 4 | **单个** RViz2 + viz_markers + world_frame_tf 的进程/launch 证据 | 进程组 + launch 日志双源计数，必须各**恰好 1** |

**两段采集**（顺序是判定正确的前提）：
 * `collect_running` —— 进程组**仍在**时拍：进程成员、X11 窗口、launch 日志、renderer 启动探测；
 * `collect_final` —— 回收**之后**拍：renderer 结束探测（与启动探测 `combine`）、补 launch 日志。

纪律：
 * 全部只读（`ps` 等价读 `/proc`、`xwininfo`、读日志），**不**启停任何东西；
 * 取不到就如实标 `missing` / `not_applicable`，**不**用别的东西冒充（尤其**不**把
 无头渲染或历史截图说成本次 GUI 截图）；
 * Gazebo Screenshot 插件**若能**取到真实帧就附上（`screenshot` 字段），取不到则
 `screenshot_present=false`，报告不得称"有截图"。
"""

import json
import os
import re
import shutil
import subprocess
import sys

import common

# `gui_renderer_evidence.py` 在 `scripts/`（顶层长期工具），本模块在 `scripts/demo/`。
# runner 通过 `sys.path.insert(0, scripts/)` 导入它；这里同样显式补路径，**不**假设
# 调用方已经设置好 PYTHONPATH（实测：漏了这一步 → renderer 证据恒 missing）。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

RVIZ_EXE = 'rviz2'
VIZ_MARKERS = 'viz_markers'
TF_STATIC = 'static_transform_publisher'

MISSING, OK, NA = 'missing', 'ok', 'not_applicable'

# 叠加层的 TF 是 **map→world** 恒等变换（`main.launch.py::_viz_actions`，RViz Fixed Frame=map 的前提）。
# world_bringup 另有 2 个 car 相关 static_tf（car/base_link→car/lidar_link 等），**必须排除**，
# 否则"单份"判据会被正常进程污染（实测：按可执行名计数得 3，实为 1 个叠加 + 2 个自带）。
WORLD_TF_FRAMES = ('map world', 'map->world')


def is_world_frame_tf(cmd):
    """该 static_transform_publisher 是否是叠加层的 map→world（新旧两种参数写法都认）。"""
    if 'world_frame_tf' in cmd:                 # 节点名（`-r __node:=world_frame_tf`）
        return True
    low = cmd.replace('"', '').replace("'", '')
    if any(f in low for f in WORLD_TF_FRAMES):
        return True
    # 新式写法：--frame-id map --child-frame-id world
    return ('--frame-id map' in low and '--child-frame-id world' in low)


def _run(cmd, timeout=10):
    """跑一条只读诊断命令，返回 `(rc, stdout, stderr)`；命令不存在 → `(None, '', …)`。"""
    exe = cmd[0]
    path = exe if os.path.isabs(exe) and os.path.exists(exe) else shutil.which(exe)
    if not path:
        return None, '', '命令不存在：%s' % cmd[0]
    try:
        p = subprocess.run([path] + list(cmd[1:]), capture_output=True, text=True,
                           timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, '', '%s: %s' % (type(e).__name__, e)


def _save(run_dir, name, text):
    path = os.path.join(common.ensure_dir(os.path.join(run_dir, 'evidence')), name)
    with open(path, 'w') as f:
        f.write(text)
    return path


def _json(doc):
    return json.dumps(doc, indent=2, ensure_ascii=False, sort_keys=True)


# --------------------------------------------------------------------------------------
# 1. 进程证据
# --------------------------------------------------------------------------------------

def process_evidence(pgid):
    """本 run 进程组成员（绑定 PGID，不是全机扫描）——GUI/headless 的结构性判别在此。"""
    members = common.pgid_members(pgid) if pgid else []
    gz_gui, gz_headless, rviz, viz, tf = [], [], [], [], []
    for pid, cmd in members:
        argv0 = common.proc_argv0(pid)
        joined = argv0 + ' ' + cmd
        if 'gz sim' in cmd and 'agc_world' in cmd:
            if re.search(r'(^|\s)-s(\s|$)', cmd):
                gz_headless.append({'pid': pid, 'cmd': cmd})
            else:
                gz_gui.append({'pid': pid, 'cmd': cmd})
        if RVIZ_EXE in joined:
            rviz.append({'pid': pid, 'cmd': cmd})
        if VIZ_MARKERS in joined:
            viz.append({'pid': pid, 'cmd': cmd})
        if TF_STATIC in joined and is_world_frame_tf(cmd):
            tf.append({'pid': pid, 'cmd': cmd})
    return {
        'pgid': pgid,
        'member_count': len(members),
        'members': [{'pid': p, 'cmd': c} for p, c in members],
        'gz_gui': gz_gui,
        'gz_headless': gz_headless,
        'rviz2': rviz,
        'viz_markers': viz,
        'world_frame_tf': tf,
    }


def launch_log_evidence(run_dir):
    """`launch.log` 里的**本 run** 进程启动行（进程回收后仍可查的"启动过"证据）。"""
    path = os.path.join(run_dir, 'launch.log')
    if not os.path.exists(path):
        return {'status': MISSING, 'note': 'launch.log 不存在'}
    started = {}
    world_tf_indexes = set()
    with open(path, errors='replace') as f:
        for line in f:
            m = re.search(r'\[INFO\] \[([^\]]+)-(\d+)\]: process started with pid \[(\d+)\]', line)
            if m:
                started.setdefault(m.group(1), []).append(
                    {'pid': int(m.group(3)), 'launch_index': int(m.group(2))})
                continue
            # 叠加层 TF 的**内容**判据：日志正文出现 map→world 或节点名 world_frame_tf
            mi = re.match(r'\[([a-z_]+)-(\d+)\]', line)
            if mi and mi.group(1) == 'static_transform_publisher':
                if "from 'map' to 'world'" in line or 'world_frame_tf' in line:
                    world_tf_indexes.add(int(mi.group(2)))
    return {
        'status': OK if started else MISSING,
        'started_counts': {k: len(v) for k, v in sorted(started.items())},
        'gazebo_started': 'gazebo' in started,
        'gazebo_count': len(started.get('gazebo', [])),
        'rviz2_started': started.get('rviz2', []),
        'viz_markers_started': started.get('viz_markers', []),
        # 全部 static_tf 的启动数（含 world_bringup 自带的 car TF，仅供对照，**不是**叠加层判据）
        'all_static_tf_started_count': len(started.get('static_transform_publisher', [])),
        # 叠加层 map→world 的启动数（内容判据；这才是"单份 RViz 叠加"的分子）
        'world_tf_started_count': len(world_tf_indexes),
        'world_tf_launch_indexes': sorted(world_tf_indexes),
    }


# --------------------------------------------------------------------------------------
# 2. renderer 证据（复用 gui_renderer_evidence）
# --------------------------------------------------------------------------------------

def snapshot_renderer_log():
    """启动**之前**拍快照（逐 run 有界证据的起点）。"""
    try:
        import gui_renderer_evidence as gre
    except ImportError:
        return None
    return gre.snapshot()


def renderer_probe(snapshot_doc, run_dir, tag):
    try:
        import gui_renderer_evidence as gre
    except ImportError as e:
        return {'status': MISSING, 'note': '无法 import gui_renderer_evidence：%s' % e}
    if not snapshot_doc:
        return {'status': MISSING, 'note': '未在启动前拍 snapshot'}
    probe = gre.probe(snapshot_doc)
    doc = {'status': probe.get('status'), 'renderer': probe.get('renderer'),
           'read_mode': probe.get('read_mode'), 'bytes_read': probe.get('bytes_read'),
           'segment_sha256': probe.get('segment_sha256'),
           'matched_lines': probe.get('matched_lines'), 'path': probe.get('path'),
           'tag': tag}
    _save(run_dir, 'renderer-%s.json' % tag, _json(doc))
    return doc


def renderer_combine(startup, final):
    try:
        import gui_renderer_evidence as gre
    except ImportError as e:
        return {'status': MISSING, 'note': '无法 import gui_renderer_evidence：%s' % e}
    # combine 的入参是 **probe 文档**；snapshot 文档只在 status=='ok' 时视为启动探测。
    combined = gre.combine(startup if (startup or {}).get('status') == 'ok' else None, final)
    return {'status': combined.get('status'), 'renderer': combined.get('renderer'),
            'startup_status': (startup or {}).get('status'),
            'final_status': (final or {}).get('status')}


# --------------------------------------------------------------------------------------
# 3. X11 窗口证据
# --------------------------------------------------------------------------------------

WINDOW_RE = re.compile(
    r'^\s*(0x[0-9a-fA-F]+)\s+"?([^"]*)"?:?\s+\([^)]*\)\s+(\d+)x(\d+)([+-]\d+[+-]\d+)')


def x11_evidence(run_dir):
    """`xdpyinfo` + `xwininfo -root -tree` 的**原始输出**（原样落盘，不改写）。"""
    display = os.environ.get('DISPLAY', '')
    doc = {'display': display, 'xdpyinfo': {}, 'xwininfo': {}, 'windows': []}
    if not display:
        doc['status'] = NA
        doc['note'] = 'DISPLAY 为空（无图形显示）'
        return doc

    rc, out, err = _run(['xdpyinfo', '-display', display])
    doc['xdpyinfo'] = {'rc': rc, 'ok': rc == 0, 'stderr': (err or '').strip()[:400]}
    if out:
        _save(run_dir, 'x11-xdpyinfo.txt', out)

    rc2, out2, err2 = _run(['xwininfo', '-root', '-tree'])
    doc['xwininfo'] = {'rc': rc2, 'ok': rc2 == 0, 'stderr': (err2 or '').strip()[:400]}
    if out2:
        _save(run_dir, 'x11-xwininfo-tree.txt', out2)
        wins = []
        for line in out2.splitlines():
            m = WINDOW_RE.match(line)
            if m:
                wins.append({'id': m.group(1), 'name': m.group(2),
                             'w': int(m.group(3)), 'h': int(m.group(4)),
                             'pos': m.group(5)})
        doc['windows'] = wins
        doc['window_count'] = len(wins)
        names = ' | '.join(w['name'] for w in wins)
        # GZ 的 Qt 窗口标题形如 "Gazebo Sim"；RViz 形如 "RViz*"
        doc['gazebo_window'] = bool(re.search(r'gazebo|gz sim', names, re.I))
        doc['rviz_window'] = bool(re.search(r'rviz', names, re.I))
    doc['status'] = OK if (doc['xdpyinfo'].get('ok') and doc['xwininfo'].get('ok')) else MISSING
    return doc


# --------------------------------------------------------------------------------------
# 4. 两段采集
# --------------------------------------------------------------------------------------

def collect_running(run_dir, result, pgid, renderer_snapshot):
    """**进程组仍在时**采集（回收后再拍会只剩 launch.log）。"""
    out = {
        'mode': result.get('mode'),
        'collected_while_running': True,
        'proc': process_evidence(pgid),
        'launch_log': launch_log_evidence(run_dir),
        'x11': x11_evidence(run_dir) if result.get('mode') == 'gui'
        else {'status': NA, 'note': 'headless 不需要图形显示'},
        'renderer_startup': renderer_probe(renderer_snapshot, run_dir, 'startup')
        if result.get('mode') == 'gui' else {'status': NA, 'note': 'headless 无渲染客户端'},
        'screenshot_present': False,
        'screenshot_note': ('本 run 未启用 Gazebo Screenshot 插件（世界 SDF 未声明该 GUI 插件）；'
                            '按派工单不为 FAIL，但**不得**称本次有 GUI 截图'),
    }
    _save(run_dir, 'evidence-running.json', _json(out))
    return out


def collect_final(run_dir, result, pre, renderer_snapshot):
    """回收后补：renderer 结束探测 + combine，并按四类证据给出**可判定**结论。"""
    mode = result.get('mode')
    out = dict(pre or {})
    out['collected_while_running'] = False
    log_ev = launch_log_evidence(run_dir)
    out['launch_log'] = log_ev
    proc_ev = (pre or {}).get('proc') or {'member_count': 0, 'gz_gui': [], 'gz_headless': [],
                                          'rviz2': [], 'viz_markers': [], 'world_frame_tf': []}
    out['proc_after_teardown'] = process_evidence(result.get('launch_pgid'))

    if mode == 'headless':
        out['renderer'] = {'status': NA, 'note': 'headless（gz -s）无渲染客户端'}
        out['rviz_singletons'] = {'status': NA, 'note': 'headless 无 RViz 叠加'}
        out['gui_claim'] = {
            'verdict': NA,
            'reason': ('headless 形态：以 gz -s 运行，不产生 GUI / 渲染 / 窗口证据；'
                       '**不得**据此宣称 GUI 通过'),
        }
    else:
        final = renderer_probe(renderer_snapshot, run_dir, 'final')
        out['renderer_final'] = final
        out['renderer'] = renderer_combine((pre or {}).get('renderer_startup'), final)
        rviz_n = max(len(proc_ev.get('rviz2') or []), len(log_ev.get('rviz2_started') or []))
        viz_n = max(len(proc_ev.get('viz_markers') or []),
                    len(log_ev.get('viz_markers_started') or []))
        tf_n = max(len(proc_ev.get('world_frame_tf') or []),
                   int(log_ev.get('world_tf_started_count') or 0))
        out['rviz_singletons'] = {
            'rviz2': rviz_n, 'viz_markers': viz_n, 'world_frame_tf': tf_n,
            'status': OK if (rviz_n == 1 and viz_n == 1 and tf_n == 1) else MISSING,
            'note': '三者必须各**恰好 1**（viz 双注册缺陷的现场判据）',
        }
        gz_gui = list(proc_ev.get('gz_gui') or [])
        gz_headless = list(proc_ev.get('gz_headless') or [])
        gazebo_non_headless = bool(gz_gui) or (
            bool(log_ev.get('gazebo_started')) and not gz_headless)
        checks = {
            'gazebo_non_headless': bool(gazebo_non_headless and not gz_headless),
            'renderer_identified': out['renderer'].get('status') in ('ok', 'ok_at_startup'),
            'x11_windows': (out.get('x11') or {}).get('status') == OK,
            'single_rviz_overlay': out['rviz_singletons']['status'] == OK,
        }
        out['gui_claim'] = {
            'verdict': OK if all(checks.values()) else MISSING,
            'checks': checks,
            'reason': ('四类证据齐备：非 headless gz 进程 + OGRE renderer + X11 窗口 + 单份 RViz 叠加'
                       if all(checks.values())
                       else '缺项：%s' % ', '.join(k for k, v in checks.items() if not v)),
        }
    _save(run_dir, 'evidence.json', _json(out))
    return out
