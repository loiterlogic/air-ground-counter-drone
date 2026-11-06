#!/usr/bin/env python3
"""`capture_run.py` —— 一次 GUI 运行**同时**产出三张截图 + 一段连续帧序列（供 GIF）。

## 为什么要一个专门的驱动

`./run_demo.sh` 跑完就回收进程组，Screenshot 服务随之消失——**运行结束后再取帧必然失败**
（P2-1 round-1 的 T2-b 就是这样失败的：探针在 `run_demo.sh` 退出后才执行，服务清单 0 条）。
所以取帧必须**在运行期间**由外部驱动轮询完成。本脚本做这件事：

1. **自然运行**（`./run_demo.sh`，不带 `--gui-config`）——α 之后世界 SDF 的 `<gui>` 块
   自带 `Screenshot` 插件，自然运行即可取帧（见 `gui_capture.py` 文件头）；
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
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

import gui_capture   # noqa: E402
import skyband as skyband_mod   # noqa: E402

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


def pick_frames(frames, timeline, prefer_size=None, stable_median=None, tol=0.02,
                frame_skybands=None):
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

    # 只允许从**视角稳定**的帧里挑：skyband 与中位数偏离 > tol 的帧是"用户拖动/缩放"
    # 造成的，不能作为交付图（round-4b 实测：前 3 帧被拖过，skyband 0.1292 vs 中位 0.0）
    stable_paths = set()
    if stable_median is not None:
        for item in (frame_skybands or []):
            if abs(item['skyband'] - stable_median) <= tol:
                stable_paths.add(item['path'])
        if stable_paths:
            frames = [f for f in frames if f[1] in stable_paths]

    def nearest(t):
        if not frames:
            return None
        pool = frames
        if prefer_size is not None:
            # 优先在同一图像尺寸的帧里挑——否则三图尺寸不一致（round-4b 实测：
            # 终态帧撞上窗口被放大，1539×999 vs 另两张 831×952）
            import os as _os
            from PIL import Image as _Img
            same = []
            for t_i, p_i in frames:
                try:
                    with _Img.open(p_i) as im:
                        if im.size == prefer_size:
                            same.append((t_i, p_i))
                except Exception:      # noqa: BLE001
                    pass
            if same:
                pool = same
        return min(pool, key=lambda kv: abs(kv[0] - t))[1]

    # 启动帧：首个 AIR_SEARCH 之前的最后时刻（世界已起、任务未动）
    first_search = next((t for t, txt in timeline if _state_of(txt) == 'AIR_SEARCH'), None)
    start_frame = None
    if first_search is not None:
        # "启动"= 任务开始**之前**的画面（世界已起来、任务还没动）。
        # 用**严格早于** first_search 的帧，避免与"跟踪中"选到同一帧
        # （round-5 实测：<= 会把任务启动那一刻的帧同时当成启动图与跟踪图）。
        before = [f for f in frames if f[0] < first_search - 0.5]
        if before:
            start_frame = before[-1][1]
        else:
            # 任务启动前的帧全被"用户拖动"污染（不在稳定集里）→ 退回取**最早的稳定帧**，
            # 并如实标注"它不是任务前画面，而是最早的可信画面"。
            start_frame = frames[0][1] if frames else None
            notes.append('首个 AIR_SEARCH 之前没有稳定帧（该段画面被拖动/缩放污染）；'
                         '启动图改用最早的稳定帧（时间上已进入任务）')

    # 跟踪中：GROUND_APPROACH 区间内目标距离最小的一刻
    approach = [(t, _distance_of(txt)) for t, txt in timeline
                if _state_of(txt) == 'GROUND_APPROACH' and _distance_of(txt) is not None]
    track_frame = None
    if approach:
        t_best = min(approach, key=lambda kv: kv[1])[0]
        track_frame = nearest(t_best)
    # 若"跟踪中"离启动太近（<2 s），画面与启动图几乎相同（round-5 实测：仅差 7 个像素），
    # 观众看不出"在动"。改取任务进行中**偏后**的帧（更接近终态、车已明显接近）。
    if track_frame is not None and first_search is not None:
        t_track = next((t for t, p in frames if p == track_frame), None)
        if t_track is not None and abs(t_track - first_search) < 2.0:
            terminal_t2 = next((t for t, txt in timeline if _state_of(txt) in TERMINALS),
                               None)
            if terminal_t2 is not None:
                late = first_search + 0.75 * (terminal_t2 - first_search)
                alt = nearest(late)
                if alt is not None and alt != start_frame:
                    track_frame = alt
                    notes.append('跟踪中离启动太近（画面几乎相同）；改取任务进行中偏后的帧')
    else:
        notes.append('时间线里没有带距离的 GROUND_APPROACH 行')
    # 兜底：若"跟踪中"与"启动"撞成同一帧（任务前无帧可取时会发生），
    # 改取**任务进行中**（first_search 之后、终态之前）的中点帧，保证三图三时刻。
    if track_frame is not None and start_frame is not None and track_frame == start_frame:
        terminal_t_probe = next((t for t, txt in timeline if _state_of(txt) in TERMINALS),
                                None)
        if terminal_t_probe is not None and first_search is not None:
            mid = (first_search + terminal_t_probe) / 2.0
            alt = nearest(mid)
            if alt is not None and alt != start_frame:
                track_frame = alt
                notes.append('跟踪中与启动撞帧；改取任务进行中点的帧')

    # 终态：首个终态之后的第 2 帧
    terminal_t = next((t for t, txt in timeline if _state_of(txt) in TERMINALS), None)
    term_frame = None
    if terminal_t is not None:
        after = [f for f in frames if f[0] >= terminal_t]
        if after:
            # 终态之后第 2 帧（让面板刷到终态）；不足 2 帧则取第 1 帧
            idx = 1 if len(after) > 1 else 0
            term_frame = after[idx][1]
            # 若该帧尺寸与另两张不同（窗口在终态后被改过大小），改取**同尺寸**的最后一帧，
            # 保证三图尺寸一致（round-4b 实测：终态帧撞上 1539×999）
            if prefer_size is not None:
                import os as _os
                from PIL import Image as _Img
                same = []
                for t_i, p_i in after:
                    try:
                        with _Img.open(p_i) as im:
                            if im.size == prefer_size:
                                same.append((t_i, p_i))
                    except Exception:      # noqa: BLE001
                        pass
                if same:
                    term_frame = same[-1][1]
                    notes.append('终态后原选帧尺寸与另两张不一致（窗口被改大小）；'
                                 '改取同尺寸的最后一帧以保证三图一致')
        if term_frame is None:
            notes.append('终态之后没有取到帧（运行在终态后立即结束）')

    return {'start': start_frame, 'tracking': track_frame, 'terminal': term_frame,
            'notes': notes}


def _skyband(path):
    """对一帧算 skyband（预登记口径，见 skyband.py）；失败返回 None。"""
    try:
        import skyband as sb
        return sb.measure(path)
    except Exception as exc:      # noqa: BLE001
        print('[capture] skyband 计算失败 %s：%s' % (path, exc), flush=True)
        return None


def gui_services():
    """只读：列出当前 `/gui/*` 服务。返回 (全部服务列表, /gui/* 子列表, 原始输出)。"""
    gz = shutil.which('gz')
    if not gz:
        return [], [], '找不到 gz 命令'
    try:
        proc = subprocess.run([gz, 'service', '-l'], capture_output=True, text=True,
                              timeout=8)
    except subprocess.TimeoutExpired:
        return [], [], 'gz service -l 超时'
    lines = [ln.strip() for ln in (proc.stdout or '').splitlines() if ln.strip()]
    gui = [ln for ln in lines if ln.startswith('/gui/')]
    return lines, gui, ((proc.stdout or '') + (proc.stderr or '')).strip()


def probe_topdown(out_dir):
    """**只读探针**：查 `/gui/*`，若 `/gui/move_to/pose` 在则强制正俯视位姿并取 2 帧。

    时机要求：**终态之后、进程回收之前**（回收后服务消失，探针必失败）。
    返回 dict（写进 manifest），不抛异常（探针失败不得掩盖主结论）。
    """
    import json as _json
    result = {'at': time.time(), 'attempted': True}
    all_svcs, gui_svcs, raw = gui_services()
    result['service_count'] = len(all_svcs)
    result['gui_services'] = gui_svcs
    result['gui_service_raw_tail'] = '\n'.join(raw.splitlines()[-30:])
    has_move = '/gui/move_to/pose' in all_svcs

    if not has_move:
        result['move_to_pose'] = {
            'present': False,
            'note': ('`/gui/move_to/pose` 不在服务清单里 → "预设俯视能否被强制"'
                     '本机**无法判别**（不是"不能"，是没这个入口）'),
        }
        return result

    gz = shutil.which('gz')
    req = 'pose { position { x: 0 y: 0 z: 118 } orientation { x: 0 y: 0.7071068 w: 0.7071068 } }'
    # 注意：gz.msgs.Pose 的四元数 (x,y,z,w)；pitch=+π/2 → (0, sin(45°)=0.7071068, 0, 0.7071068)
    try:
        proc = subprocess.run(
            [gz, 'service', '-s', '/gui/move_to/pose',
             '--reqtype', 'gz.msgs.Pose', '--reptype', 'gz.msgs.Boolean',
             '--timeout', '8000', '--req', req],
            capture_output=True, text=True, timeout=12)
        call_out = ((proc.stdout or '') + (proc.stderr or '')).strip()
        called = proc.returncode == 0
    except subprocess.TimeoutExpired:
        call_out, called = 'gz service 调用超时', False
    result['move_to_pose'] = {'present': True, 'called': called, 'response': call_out[:400],
                              'request': req}
    if not called:
        return result

    # 等 3 s 让视图切换生效，再取 2 帧
    time.sleep(3.0)
    frames = []
    for i in range(2):
        path = os.path.join(out_dir, 'probe-topdown-%d.png' % i)
        ok, detail = gui_capture.snap(path, timeout_ms=8000)
        if ok:
            sb = _skyband(path)
            frames.append({'path': path, 'ok': True, 'detail': detail, 'skyband': sb})
        else:
            frames.append({'path': path, 'ok': False, 'detail': detail})
        time.sleep(0.6)
    result['move_to_pose']['frames'] = frames
    values = [f['skyband']['skyband'] for f in frames
              if f.get('ok') and f.get('skyband')]
    result['move_to_pose']['skyband_after'] = values
    if values:
        result['move_to_pose']['forced_topdown'] = min(values) <= 0.05
    return result


def stable_skyband(frame_skybands):
    """从逐帧 skyband 求**稳定帧中位数**——排除"用户拖动/缩放窗口"造成的跳变帧。

    为什么需要（round-4b 实测）：`Screenshot` 插件取的是 **GUI 实时视图相机**，
    用户拖一下鼠标或滚一下滚轮，画面就变（第 3 帧作业区 84.7%→99.9%，平均差 41.4）；
    第 21–22 帧窗口被改成 1539×999。若只看首帧，会把**人为操作**误判成**系统视角**。

    规则（可机械复核，不靠眼）：
      1. 只取**出现次数最多**的图像尺寸（主尺寸）——排除窗口缩放帧；
      2. 尺寸内按与前一帧的平均灰度差判"视角跳变"，**跳变帧及其前一帧都丢弃**；
      3. 余下帧取 skyband **中位数**（抗残余抖动）。
    返回 (median, detail_dict)；样本不足 3 帧时 median=None（如实报不可判）。
    """
    if not frame_skybands:
        return None, {'error': '无帧'}

    sizes = {}
    for item in frame_skybands:
        sizes.setdefault(tuple(item['size']) if item.get('size') else None,
                         []).append(item)
    main_size = max(sizes.items(), key=lambda kv: len(kv[1]))[0]
    in_main = [it for it in frame_skybands if (tuple(it['size']) if it.get('size') else None)
               == main_size]

    kept = []
    prev_arr = None
    for it in in_main:
        try:
            import numpy as np
            from PIL import Image
            with Image.open(it['path']) as im:
                arr = np.asarray(im.convert('L'), dtype=np.float32)
        except Exception:      # noqa: BLE001
            kept.append(it)     # 读不出就保留（skyband 已算过）
            prev_arr = None
            continue
        if prev_arr is not None and prev_arr.shape == arr.shape:
            if float(np.abs(arr - prev_arr).mean()) > 5.0:
                prev_arr = arr
                continue        # 视角跳变帧：丢弃
        kept.append(it)
        prev_arr = arr

    if len(kept) < 3:
        return None, {'main_size': main_size, 'in_main': len(in_main),
                      'kept': len(kept), 'error': '稳定帧不足 3，不可判'}

    import statistics
    values = [it['skyband'] for it in kept]
    median = statistics.median(values)
    import skyband as sb
    return median, {
        'main_size': main_size,
        'in_main': len(in_main),
        'kept': len(kept),
        'dropped': len(in_main) - len(kept),
        'min': min(values), 'max': max(values),
        'median': round(median, 4),
        'verdict': sb.classify(median),
    }


def _run_start_unix(demo_dir):
    """从 demo 目录的 `result.json` 取运行起点的 Unix 秒（用于对齐 timeline 的相对时刻）。

    取不到返回 None（调用方据此退回原时刻，并应在报告里说明"时刻未对齐"）。
    """
    import json as _json
    from datetime import datetime
    if not demo_dir:
        return None
    path = os.path.join(demo_dir, 'result.json')
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding='utf-8') as f:
            doc = _json.load(f)
    except Exception:      # noqa: BLE001
        return None
    raw = doc.get('started_at')
    if not raw:
        return None
    for fmt in ('%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%dT%H:%M:%S.%f%z'):
        try:
            return datetime.strptime(raw, fmt).timestamp()
        except ValueError:
            continue
    return None


def _current_timeline():
    """找**本次运行**的 demo 目录并解析 timeline（取 mtime 最新的那个）。"""
    demo_root = os.path.join(ROOT, 'experiments', 'demo')
    try:
        names = sorted(os.listdir(demo_root))
    except OSError:
        return []
    for name in reversed(names):
        path = os.path.join(demo_root, name, 'timeline.txt')
        if os.path.isfile(path):
            return parse_timeline(path)
    return []


def _has_terminal(timeline):
    """时间线里是否已出现终态行（终态 = 回收前的探针窗口开始）。"""
    for _t, text in timeline:
        if _state_of(text) in TERMINALS:
            return True
    return False


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(add_help=True, description='一次 GUI 运行取三图 + 连续帧')
    ap.add_argument('--out', required=True, help='产物目录（截图 / 帧 / 清单都写这里）')
    ap.add_argument('--duration', type=float, default=110.0,
                    help='传给 run_demo.sh 的 --duration（秒，默认 110）')
    ap.add_argument('--scene', default='',
                    help='传给 run_demo.sh 的 --scene（空 = run_demo 默认场景）。'
                         '取证要求场景可达终态：默认场景在 GUI 下可能因 '
                         'air_hover_timeout 不产生状态跳变，三张代表帧会取不到')
    ap.add_argument('--interval', type=float, default=1.0, help='取帧间隔秒（默认 1.0）')
    ap.add_argument('--max-seconds', type=float, default=200.0,
                    help='取帧总时长上限（防跑飞）')
    ap.add_argument('--start-delay', type=float, default=0.0,
                    help='启动后先等这么久再开始轮询服务（默认 0）')
    ap.add_argument('--probe-topdown', action='store_true',
                    help='终态后、回收前做只读探针：记 /gui/* 清单，若 /gui/move_to/pose'
                         ' 在则强制正俯视并取 2 帧测 skyband')
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

    # 1. **固定自然运行**：不带任何 --gui-config。
    #    α 之后世界 SDF 的 <gui> 块自带 Screenshot 插件，自然运行即可取帧；
    #    带 --gui-config 反而会让 gz-gui 再加载 ~/.gz/sim/<ver>/gui.config 覆盖视角 → 图不代表用户所见。
    print('[capture] **自然运行**（不带 --gui-config）；取帧能力来自世界 SDF 的 <gui> 块', flush=True)

    # 2. 起运行（子进程；进程组回收仍归 run_demo.sh）
    env = dict(os.environ)
    env.pop('AGC_GUI_CONFIG', None)      # 防御：即便外部环境残留也不生效
    log_path = os.path.join(out, 'run.log')
    with open(log_path, 'w', encoding='utf-8') as log:
        proc = subprocess.Popen(
            [os.path.join(ROOT, 'run_demo.sh'), '--duration', str(args.duration)]
            + (['--scene', args.scene] if args.scene else []),
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
        first_skyband = None
        frame_skybands = []
        probe_result = None
        i = 0
        while True:
            if proc.poll() is not None:
                break
            if time.monotonic() - t0 > args.max_seconds:
                print('[capture] 达取帧时长上限 %.0f s，停止取帧' % args.max_seconds,
                      flush=True)
                break
            tick_start = time.monotonic()
            path = os.path.join(frames_dir, 'f-%04d.png' % i)
            # 首帧查一次服务（确认在线）；之后跳过——每次 `gz service -l` 要 1–2 s，
            # 会把 1 Hz 拖成 4–6 s（round-4 实测 8 帧 / 34 s，GIF 需 ≥20 帧）
            ok, _d = gui_capture.snap(path, timeout_ms=8000, check_service=(i == 0))
            if ok:
                if not _frame_has_content(path):
                    # 取到文件但画面是纯色/全黑 → 不算取到（不能用黑帧冒充截图）
                    print('[capture] 第 %d 帧为纯色/空画面，丢弃：%s' % (i, path), flush=True)
                    os.remove(path)
                else:
                    frames.append((time.monotonic() - t0, path))
                    sb_one = _skyband(path)
                    if sb_one:
                        try:
                            from PIL import Image as _Img
                            with _Img.open(path) as _im:
                                sb_one['size'] = [_im.width, _im.height]
                        except Exception:      # noqa: BLE001
                            sb_one['size'] = None
                        frame_skybands.append(sb_one)
                    if first_skyband is None:
                        # 预登记：首帧即算 skyband（不挑好看的帧），但**仅作记录**。
                        # 判定改用"稳定帧中位数"（见下方 stable_skyband）——因为
                        # `Screenshot` 插件取的是 **GUI 实时视图相机**，用户拖一下/滚一下滚轮
                        # 画面就变（round-4b 实测：第 3 帧一次跳变，作业区 84.7%→99.9%）。
                        # 单看首帧会把"人为操作"误判成"系统视角"。
                        first_skyband = _skyband(path)
                        if first_skyband:
                            print('[capture] 首帧 skyband=%.4f → %s（预登记判定）'
                                  % (first_skyband['skyband'], first_skyband['verdict']),
                                  flush=True)
                        # 模糊区间（0.10–0.20）：等 ≥2 s 补 1 帧复核，两帧同侧才下结论
                        if first_skyband and first_skyband['verdict'] == 'ambiguous':
                            print('[capture] 首帧落在模糊区间，等 %.1f s 补 1 帧复核'
                                  % skyband_mod.AMBIGUOUS_RECHECK_S, flush=True)
                            time.sleep(skyband_mod.AMBIGUOUS_RECHECK_S)
                            recheck = os.path.join(out, 'skyband-recheck.png')
                            ok2, _d2 = gui_capture.snap(recheck, timeout_ms=8000)
                            if ok2 and _frame_has_content(recheck):
                                sb2 = _skyband(recheck)
                                first_skyband['recheck'] = sb2
                                if sb2:
                                    verdict = skyband_mod.classify_pair(
                                        first_skyband['skyband'], sb2['skyband'])
                                    first_skyband['pair_verdict'] = verdict
                                    print('[capture] 复核帧 skyband=%.4f；两帧联合判定 → %s'
                                          % (sb2['skyband'], verdict), flush=True)
                            else:
                                first_skyband['recheck'] = {
                                    'error': '复核帧取帧失败或为纯色（%s）' % (_d2,)}
            i += 1

            # 终态探针：必须在**回收之前**。start.py 的 _phase_collect 先等 3 s 再回收，
            # 窗口只有约 10 s → 用 timeline.txt 出现终态行即触发（不等循环结束）。
            if args.probe_topdown and probe_result is None:
                tl = _current_timeline()
                if tl and _has_terminal(tl):
                    print('[capture] 检测到终态（timeline），立即执行只读探针'
                          '（回收前窗口）', flush=True)
                    probe_result = probe_topdown(out)

            # 精确节拍：按"上一次取帧开始时刻"补足间隔（原按固定 0.2 s 扣减，
            # snap 实际耗时 1–2 s 时会把节拍拖成 4–6 s）
            elapsed = time.monotonic() - tick_start
            time.sleep(max(0.0, args.interval - elapsed))
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
    # ⚠ 时刻基准对齐（round-4b 踩到的坑）：
    # `timeline.txt` 的 `[mm:ss.d]` 是**相对运行起点**，而取帧记录用的是 `time.monotonic()`
    # 相对**本脚本开始轮询**——两者原点不同，直接比较会把三张图全选到相邻帧。
    # 修法：从 result.json 的 `started_at` 取运行起点，把帧时刻换算成同一零点。
    run_t0_unix = _run_start_unix(demo_dir)
    if run_t0_unix is not None and frames:
        import os as _os
        frames = [(_os.path.getmtime(p) - run_t0_unix, p) for _t, p in frames]

    # 先算稳定帧统计（下面的挑帧要用它过滤"被拖动/缩放"的帧），**不能**放到后面。
    stable_median, stable_detail = stable_skyband(frame_skybands)
    main_size = stable_detail.get('main_size')
    prefer_size = tuple(main_size) if main_size else None

    picked = pick_frames(frames, timeline, prefer_size=prefer_size,
                         stable_median=stable_median, frame_skybands=frame_skybands)

    manifest = {
        'schema': 'p2-1-capture/3',
        'out': out,
        'demo_dir': demo_dir,
        'frame_count': len(frames),
        'interval_s': args.interval,
        'picked': {},
        'notes': picked['notes'],
        'run_exit': proc.returncode,
        'natural_run': True,
        'natural_run_note': ('不带 --gui-config；取帧能力来自世界 SDF 的 <gui> 块自带'
                            ' Screenshot 插件（α，仓库自带、任何 clone 可复现）'),
        'first_frame_skyband': first_skyband,
        'stable_skyband': {'median': stable_median, **stable_detail},
        'frame_skybands': frame_skybands,
        'probe_topdown': probe_result,
    }
    ok_all = True
    for key in ('start', 'tracking', 'terminal'):
        src = picked.get(key)
        if not src:
            ok_all = False
            manifest['picked'][key] = None
            continue
        dst = os.path.join(out, 'demo-%s.png' % key)
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
    if first_skyband:
        print('[capture] 首帧 skyband=%.4f（仅记录；判定用稳定帧中位数）'
              % first_skyband['skyband'])
    else:
        print('[capture] 首帧 skyband：**未算出**（帧不足或读图失败）')
    if stable_median is not None:
        print('[capture] **稳定帧 skyband 中位数=%.4f → %s**（%d/%d 帧参与，丢弃 %d 个跳变/缩放帧；'
              '预登记：≤0.10 俯视 / ≥0.20 斜视）'
              % (stable_median, stable_detail.get('verdict'), stable_detail.get('kept'),
                 stable_detail.get('in_main'), stable_detail.get('dropped')))
    else:
        print('[capture] **稳定帧不可判**：%s' % stable_detail.get('error'))
    if probe_result:
        mv = probe_result.get('move_to_pose') or {}
        print('[capture] 探针：/gui/* 共 %d 条；/gui/move_to/pose 存在=%s'
              % (len(probe_result.get('gui_services') or []), mv.get('present')))
        if mv.get('present') and mv.get('skyband_after'):
            print('[capture] 强制俯视后 skyband=%r → 生效=%s'
                  % (mv['skyband_after'], mv.get('forced_topdown')))
    elif args.probe_topdown:
        print('[capture] 探针：**未执行**（未检测到终态行或运行提前结束）')

    return 0 if ok_all else 1


if __name__ == '__main__':
    sys.exit(main())
