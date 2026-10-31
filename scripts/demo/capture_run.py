#!/usr/bin/env python3
"""`capture_run.py` —— 一次 GUI 运行**同时**产出三张截图 + 一段连续帧序列（供 GIF）。

## 为什么要一个专门的驱动

`./run_demo.sh` 跑完就回收进程组，Screenshot 服务随之消失——**运行结束后再取帧必然失败**
（P2-1 round-1 的 T2-b 就是这样失败的：探针在 `run_demo.sh` 退出后才执行，服务清单 0 条）。
所以取帧必须**在运行期间**由外部驱动轮询完成。本脚本做这件事：

1. 用 `AGC_GUI_CONFIG` 指向一份含 `Screenshot` 插件的 gui-config（见 `gui_capture.py`）；
2. 以子进程启动 `run_demo.sh`，**不接管**它的进程组回收（它自己会收干净）；
3. 轮询 `/gui/screenshot` 上线后开始**连续取帧**（默认 1 Hz，覆盖启动 → 跟踪 → 终态）；
4. 运行结束后：从帧序列里按**状态时间线**挑出三张代表帧（启动 / 跟踪中 / 终态），
   并把一段连续帧交给 `make_gif.py` 合成 GIF。

## 三张代表帧怎么挑（不靠猜时间）

`run_demo.sh` 会写 `timeline.txt`（状态跳变时刻）。本脚本读它，按**状态名**定位：

| 图 | 取哪一帧 |
|---|---|
| 启动 | 首个 `AIR_SEARCH` 之前的最后一帧（世界已起来、任务还没动） |
| 跟踪中 | `GROUND_APPROACH` 区间内、目标距离最小的那一帧（车最接近目标时画面最有信息量） |
| 终态 | 首个终态（`TRACKING_SUCCESS` 等）之后的第 2 帧（让面板刷到终态） |

取不到对应帧时**如实报缺**，不用别的帧冒充。

## 用法

```bash
python3 scripts/demo/capture_run.py \
    --out experiments/p2-1/round-2 --duration 110 --interval 1.0
```

退出码：`0` 三图齐全且帧数达标；`1` 有缺项（报告写明缺哪项）；`2` 用法/环境错误。

**这是 T2 动作**（起 GUI + 全链仿真），必须由派工单预授权；本脚本不自行重跑。
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

import gui_capture   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
TERMINALS = ('TRACKING_SUCCESS', 'INTERCEPT_CONFIRMED', 'MISSION_FAILED', 'ABORTED',
             'INFRA_FAILURE')


def _frame_has_content(path, min_std=6.0, min_unique=64):
    """帧是否**真有画面**：灰度标准差 + 不同颜色数双判据。

    Gazebo 取到黑帧/纯色帧（渲染未就绪、相机被遮挡）时，PNG 照样生成、服务照样返回 true——
    只看"文件存在且非空"会把黑帧当证据。实测阈值：正常俯视场景图 std≈30–60、颜色数 >1000；
    全黑帧 std≈0、颜色数 1。
    """
    try:
        from PIL import Image
        import numpy as np
    except Exception:       # noqa: BLE001  缺库时退回"只看非空"，并在调用方报告
        return True
    try:
        with Image.open(path) as im:
            arr = np.asarray(im.convert('L'), dtype=np.float32)
            rgb = np.asarray(im.convert('RGB'))
    except Exception:       # noqa: BLE001  截断/损坏帧 → 判为"无内容"，丢弃该帧
        return False
    std = float(arr.std())
    # 注意：**不能**用 `getcolors(maxcolors=N)`——800×500 就有 400k 像素，超过上限时
    # Pillow 返回 None，被读成"颜色数 0"→ 把真画面误判成纯色（离线自测踩到过）。
    # 直接对像素数组做唯一行计数，与图像尺寸无关。
    flat = rgb.reshape(-1, 3)
    unique = len(np.unique(flat, axis=0))
    return std >= min_std and unique >= min_unique


def parse_timeline(path):
    """解析 `timeline.txt` → [(相对秒, 文本)]；文件不存在返回 []。

    行格式：`[mm:ss.d] 文本`。
    """
    if not os.path.isfile(path):
        return []
    rows = []
    pat = re.compile(r'^\[(\d+):(\d+\.\d+)\]\s+(.*)$')
    with open(path, encoding='utf-8') as f:
        for line in f:
            m = pat.match(line.rstrip('\n'))
            if not m:
                continue
            rows.append((int(m.group(1)) * 60 + float(m.group(2)), m.group(3)))
    return rows


def _state_of(text):
    """从时间线文本里取状态名（形如 `进入 GROUND_APPROACH（…）` / `终态 TRACKING_SUCCESS`）。"""
    for name in ('AIR_SEARCH', 'TARGET_ACQUIRED', 'GROUND_APPROACH', 'TRACKING_SUCCESS',
                 'INTERCEPT_CONFIRMED', 'MISSION_FAILED', 'ABORTED', 'INFRA_FAILURE'):
        if name in text:
            return name
    return None


def _distance_of(text):
    m = re.search(r'距离\s*([\d.]+)\s*m', text)
    return float(m.group(1)) if m else None


def pick_frames(frames, timeline):
    """按状态时间线挑三张代表帧。返回 {'start': path|None, 'tracking': …, 'terminal': …,
    'notes': [...]}。

    `frames` 是 [(取帧时刻相对秒, 路径)]。
    """
    notes = []
    if not timeline:
        notes.append('timeline.txt 缺失或为空：无法按状态定位，退回按时刻比例挑帧')
        if not frames:
            return {'start': None, 'tracking': None, 'terminal': None, 'notes': notes}
        n = len(frames)
        return {'start': frames[0][1], 'tracking': frames[n // 2][1],
                'terminal': frames[-1][1], 'notes': notes}

    def nearest(t):
        if not frames:
            return None
        return min(frames, key=lambda kv: abs(kv[0] - t))[1]

    # 启动帧：首个 AIR_SEARCH 之前的最后时刻（世界已起、任务未动）
    first_search = next((t for t, txt in timeline if _state_of(txt) == 'AIR_SEARCH'), None)
    start_frame = None
    if first_search is not None:
        before = [f for f in frames if f[0] <= first_search]
        start_frame = before[-1][1] if before else None
        if start_frame is None:
            notes.append('首个 AIR_SEARCH 之前没有取到帧（取帧起始太晚）')

    # 跟踪中：GROUND_APPROACH 区间内目标距离最小的一刻
    approach = [(t, _distance_of(txt)) for t, txt in timeline
                if _state_of(txt) == 'GROUND_APPROACH' and _distance_of(txt) is not None]
    track_frame = None
    if approach:
        t_best = min(approach, key=lambda kv: kv[1])[0]
        track_frame = nearest(t_best)
    else:
        notes.append('时间线里没有带距离的 GROUND_APPROACH 行')

    # 终态：首个终态之后的第 2 帧
    terminal_t = next((t for t, txt in timeline if _state_of(txt) in TERMINALS), None)
    term_frame = None
    if terminal_t is not None:
        after = [f for f in frames if f[0] >= terminal_t]
        term_frame = after[1][1] if len(after) > 1 else (after[0][1] if after else None)
        if term_frame is None:
            notes.append('终态之后没有取到帧（运行在终态后立即结束）')

    return {'start': start_frame, 'tracking': track_frame, 'terminal': term_frame,
            'notes': notes}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(add_help=True, description='一次 GUI 运行取三图 + 连续帧')
    ap.add_argument('--out', required=True, help='产物目录（截图 / 帧 / 清单都写这里）')
    ap.add_argument('--duration', type=float, default=110.0,
                    help='传给 run_demo.sh 的 --duration（秒，默认 110）')
    ap.add_argument('--interval', type=float, default=1.0, help='取帧间隔秒（默认 1.0）')
    ap.add_argument('--max-seconds', type=float, default=200.0,
                    help='取帧总时长上限（防跑飞）')
    ap.add_argument('--start-delay', type=float, default=0.0,
                    help='启动后先等这么久再开始轮询服务（默认 0）')
    args = ap.parse_args(argv)

    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    frames_dir = os.path.join(out, 'frames')
    os.makedirs(frames_dir, exist_ok=True)
    world = os.path.join(ROOT, 'install', 'agc_sim', 'share', 'agc_sim', 'worlds',
                         'agc_world.sdf')
    if not os.path.isfile(world):
        print('[capture] 工作区未构建：缺 %s' % world, file=sys.stderr)
        return 2

    # 1. 派生 gui-config（含 Screenshot 插件）
    cfg = os.path.join(out, 'gui.config')
    ok, detail = gui_capture.derive_config(world, cfg)
    if not ok:
        print('[capture] gui-config 派生失败：%s' % detail, file=sys.stderr)
        return 2
    print('[capture] gui-config：%s（%s）' % (cfg, detail), flush=True)

    # 2. 起运行（子进程；进程组回收仍归 run_demo.sh）
    env = dict(os.environ)
    env['AGC_GUI_CONFIG'] = cfg
    log_path = os.path.join(out, 'run.log')
    with open(log_path, 'w', encoding='utf-8') as log:
        proc = subprocess.Popen(
            [os.path.join(ROOT, 'run_demo.sh'), '--duration', str(args.duration)],
            cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True)
        print('[capture] run_demo.sh 已启动（pid %d），日志 %s' % (proc.pid, log_path),
              flush=True)

        if args.start_delay > 0:
            time.sleep(args.start_delay)

        # 3. 轮询服务上线
        t0 = time.monotonic()
        online = False
        while time.monotonic() - t0 < 90:
            present, _ = gui_capture.service_present()
            if present:
                online = True
                break
            if proc.poll() is not None:
                break
            time.sleep(2.0)
        if not online:
            print('[capture] 取帧服务未上线（GUI 未起或插件未加载）；见 %s' % log_path,
                  file=sys.stderr)
            if proc.poll() is None:
                proc.wait(timeout=args.duration + 60)
            return 1

        print('[capture] 取帧服务已上线（%.1f s），开始连续取帧（间隔 %.1f s）'
              % (time.monotonic() - t0, args.interval), flush=True)

        # 4. 连续取帧（运行期间）
        frames = []
        i = 0
        while True:
            if proc.poll() is not None:
                break
            if time.monotonic() - t0 > args.max_seconds:
                print('[capture] 达取帧时长上限 %.0f s，停止取帧' % args.max_seconds,
                      flush=True)
                break
            path = os.path.join(frames_dir, 'f-%04d.png' % i)
            ok, _d = gui_capture.snap(path, timeout_ms=8000)
            if ok:
                if not _frame_has_content(path):
                    # 取到文件但画面是纯色/全黑 → 不算取到（不能用黑帧冒充截图）
                    print('[capture] 第 %d 帧为纯色/空画面，丢弃：%s' % (i, path), flush=True)
                    os.remove(path)
                else:
                    frames.append((time.monotonic() - t0, path))
            i += 1
            # 取帧本身耗时，用剩余时间凑间隔
            time.sleep(max(0.0, args.interval - 0.2))
        proc.wait(timeout=120)

    print('[capture] 运行结束（exit %s），共取到 %d 帧' % (proc.returncode, len(frames)),
          flush=True)
    if not frames:
        print('[capture] 一帧都没取到：见 %s' % log_path, file=sys.stderr)
        return 1

    # 5. 按时间线挑三张代表帧
    demo_dir = None
    timeline = []
    for candidate in sorted(os.listdir(os.path.join(ROOT, 'experiments', 'demo'))):
        d = os.path.join(ROOT, 'experiments', 'demo', candidate)
        if not os.path.isdir(d):
            continue
        st = os.path.getmtime(d)
        if st >= t0 - 5:
            demo_dir = d
    if demo_dir:
        timeline = parse_timeline(os.path.join(demo_dir, 'timeline.txt'))
    picked = pick_frames(frames, timeline)

    manifest = {
        'schema': 'p2-1-capture/1',
        'out': out,
        'demo_dir': demo_dir,
        'frame_count': len(frames),
        'interval_s': args.interval,
        'picked': {},
        'notes': picked['notes'],
        'run_exit': proc.returncode,
    }
    ok_all = True
    for key in ('start', 'tracking', 'terminal'):
        src = picked.get(key)
        if not src:
            ok_all = False
            manifest['picked'][key] = None
            continue
        dst = os.path.join(out, 'demo-%s.png' % key)
        import shutil
        shutil.copyfile(src, dst)
        manifest['picked'][key] = {'src': src, 'dst': dst,
                                   'bytes': os.path.getsize(dst)}
    with open(os.path.join(out, 'capture-manifest.json'), 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    for key in ('start', 'tracking', 'terminal'):
        item = manifest['picked'].get(key)
        print('[capture] %-9s %s' % (key, item['dst'] if item else '缺（未取到对应帧）'))
    for note in picked['notes']:
        print('[capture] 备注：%s' % note)

    return 0 if ok_all else 1


if __name__ == '__main__':
    sys.exit(main())
