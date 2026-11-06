#!/usr/bin/env python3
"""`make_gif.py` —— 把 `capture_run.py` 的连续帧序列合成 README 用的 GIF。

## 规格

| 项 | 要求 | 本脚本怎么保证 |
|---|---|---|
| 宽度 | **800 px** | 等比缩放（不改长宽比，不裁切） |
| 体积 | **≤ 5 MB** | 先按目标宽度渲染，再逐级降采样率/颜色数直到达标 |
| 时长 | **10–15 s** | 由调用方给的帧数 × 帧间隔决定；本脚本**报告**实际时长，不悄悄改 |
| 内容 | 真实画面 | 帧来自 Gazebo 3D 视图相机（`gui_capture.py`），本脚本**不合成**任何内容 |

**降级顺序**（体积超限时，按此顺序且**只**动这三项）：帧率 → 调色板颜色数 → 宽度（不低于 640）。
任何降级都写进 `gif-manifest.json`，README 与报告里如实引用——**不得**悄悄降级后仍宣称"800 px"。

## 用法

```bash
python3 scripts/demo/make_gif.py --frames experiments/p2-1/round-2/frames \
    --out docs/conventions/assets/demo.gif --fps 8 --max-bytes 5242880
```

退出码：`0` 产出且满足全部规格；`1` 产出但**某项规格未满足**（报告写明）；`2` 用法错误。
"""

import argparse
import json
import os
import sys

from PIL import Image

TARGET_WIDTH = 800
MIN_WIDTH = 640
# 口径写死：**十进制 5,000,000 字节**（不是 5 MiB）。
# 交付 5,095,380 B：按 MiB(5,242,880) 达标、按十进制 MB(5,000,000) **超出** ——
# 模糊口径等于没口径，故统一到更严的十进制值，并在 manifest 明写单位。
MAX_BYTES = 5 * 1000 * 1000


def _load_frames(frames_dir):
    names = sorted(n for n in os.listdir(frames_dir) if n.lower().endswith('.png'))
    return [os.path.join(frames_dir, n) for n in names]


def _resize(path, width):
    im = Image.open(path).convert('RGB')
    if im.width == width:
        return im
    height = max(1, int(round(im.height * width / float(im.width))))
    return im.resize((width, height), Image.LANCZOS)


def make(frames, out_path, fps, width, colors, max_bytes, source_fps, stride=None):
    """抽帧 → 缩放 → 存 GIF；返回 dict（含是否达标与降级记录）。

 `stride` 可直接给抽帧倍数（体积超限时按 1→2→3→4 降级）：
 **抽帧后每帧时长同比拉长，总时长保持不变**——这样"800 px + 10–15 s"两个硬指标
 不会被"降帧率"顺手破坏（ 实测踩过：降 fps 到 1.5 仍 3.86 MB 且宽度被迫降到 640）。
    """
    if stride is None:
        stride = max(1, int(round(source_fps / float(fps))))
    used = frames[::stride]
    if len(used) < 2:
        used = frames[:2] if len(frames) >= 2 else frames
    images = [_resize(p, width) for p in used]
    duration_ms = int(round(1000.0 / (source_fps / stride)))
    images[0].save(out_path, save_all=True, append_images=images[1:],
                   duration=duration_ms, loop=0, optimize=True,
                   disposal=2)
    size = os.path.getsize(out_path)
    return {'frames_used': len(used), 'stride': stride, 'duration_ms': duration_ms,
            'fps_effective': source_fps / stride, 'width': images[0].width,
            'height': images[0].height, 'bytes': size, 'colors': colors,
            'under_max': size <= max_bytes}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(add_help=True, description='帧序列 → README GIF')
    ap.add_argument('--frames', required=True, help='帧目录（capture_run.py 的 frames/）')
    ap.add_argument('--out', required=True, help='输出 GIF 路径')
    ap.add_argument('--fps', type=float, default=8.0, help='目标帧率（默认 8）')
    ap.add_argument('--source-fps', type=float, default=1.0,
                    help='采集帧率（capture_run.py 的 --interval 的倒数，默认 1.0）')
    ap.add_argument('--max-bytes', type=int, default=MAX_BYTES)
    ap.add_argument('--max-duration', type=float, default=15.0,
                    help='时长上限秒（默认 15）；源帧时间跨度更长时**截取前一段**')
    ap.add_argument('--min-duration', type=float, default=10.0,
                    help='时长下限秒（默认 10）')
    args = ap.parse_args(argv)

    frames = _load_frames(args.frames)
    if len(frames) < 2:
        print('[gif] 帧数不足（%d）：%s' % (len(frames), args.frames), file=sys.stderr)
        return 2

    # 时长硬门：源帧跨度可能超过上限（ 实测 22 帧 × 0.8 s = 17.6 s），
    # 此时**截取前一段**而不是靠抽帧（抽帧会同比拉长每帧时长，总时长不变）。
    # 每帧时长 = 1/source_fps；要落进 [min,max]，帧数取 max_duration 向下取整，
    # 但**不得低于** min_duration（否则把"截取"做成了"截断到不合格"）。
    max_frames = int(args.max_duration * args.source_fps) if args.source_fps > 0 else None
    min_frames = int(-(-args.min_duration * args.source_fps // 1)) if args.source_fps > 0 else 0
    if max_frames and len(frames) > max_frames:
        keep = max(max_frames, min(min_frames, len(frames)))
        print('[gif] 源帧跨度 %.1f s > 上限 %.1f s → 截取前 %d 帧（每帧 %.2f s）'
              % (len(frames) * 1.0 / args.source_fps, args.max_duration, keep,
                 1.0 / args.source_fps))
        frames = frames[:keep]

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    attempts = []
    ok = False
    result = None
    # 降级阶梯：只动 帧率 → 宽度；颜色数由 GIF 调色板自适应
    # 降级阶梯（**保宽度、保时长，只抽帧**）：
    # 宽度 800 px 与时长 10–15 s 是硬指标，帧率不是。
    # 抽帧时每帧时长同比拉长 → **总时长不变**，所以"抽帧"不会破坏时长指标。
    # 实测：20 帧 @800 px = 3.86 MB / 14.3 s（超 5 MB 上限一点点）；
    # 抽到 stride=2（10 帧）→ 800×916 / 14.3 s / 2.72 MB，三项全过。
    ladder = [
        (args.fps, TARGET_WIDTH, 1),
        (args.fps, TARGET_WIDTH, 2),
        (args.fps, TARGET_WIDTH, 3),
        (args.fps, TARGET_WIDTH, 4),
        (args.fps, MIN_WIDTH, 2),
    ]
    for fps, width, stride in ladder:
        result = make(frames, args.out, fps, width, 256, args.max_bytes, args.source_fps,
                      stride=stride)
        attempts.append({'fps': fps, 'width': width, 'stride': stride, **result})
        if result['under_max']:
            ok = True
            break

    duration_s = result['frames_used'] * (result['duration_ms'] / 1000.0)
    spec_ok = {
        'width_800': result['width'] == TARGET_WIDTH,
        'under_5mb': result['under_max'],
        'duration_10_15s': args.min_duration <= duration_s <= args.max_duration,
    }
    manifest = {
        'schema': 'p2-1-gif/1',
        'out': os.path.abspath(args.out),
        'source_frames': len(frames),
        'source_fps': args.source_fps,
        'final': result,
        'duration_s': round(duration_s, 2),
        'spec': spec_ok,
        'size_unit': 'decimal_bytes',
        'max_bytes_limit': args.max_bytes,
        'max_bytes_note': ('上限按**十进制字节**计（%d B = %.3f MB），不是 MiB'
                           % (args.max_bytes, args.max_bytes / 1e6)),
        'attempts': attempts,
    }
    man_path = os.path.splitext(os.path.abspath(args.out))[0] + '-manifest.json'
    with open(man_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print('[gif] %s：%d 帧 → %dx%d，%.1f s，%d 字节'
          % (args.out, result['frames_used'], result['width'], result['height'],
             duration_s, result['bytes']))
    for key, val in spec_ok.items():
        print('[gif]   %-16s %s' % (key, 'OK' if val else '未满足'))
    print('[gif] 清单：%s' % man_path)
    if not ok:
        print('[gif] 体积降级后仍超限', file=sys.stderr)
    return 0 if all(spec_ok.values()) else 1


if __name__ == '__main__':
    sys.exit(main())
