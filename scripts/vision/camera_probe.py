#!/usr/bin/env python3
"""camera_probe —— 相机图像链路取证：频率 / 内容 / 编码 / QoS 可用性（P1-4）。

定位：P1-4「仿真图像 → 可插拔识别」链路的**取证工具**（工具域，ADR-0011），不是识别算法。
本工具只订阅、只落盘，**不发布任何话题、不写执行口、不读真值**。

它回答三个问题（对应预登记 A2 / A3）：

  * **A2 频率** —— 采样窗口内的平均 / 最小 / 最大帧间隔与等效 Hz；
  * **A3 非黑屏** —— 逐帧亮度统计（0..255 的 mean / std / 唯一色数），并存一份 PNG 供复核；
  * **口径** —— header.stamp 与 frame_id 原值、encoding、宽高、QoS（订阅端 best-effort 是否够）。

**为什么不用 rqt 截图**：截图无法证明数值（预登记 A3 明确排除），且 rqt 是 GUI 依赖。
本工具纯 rclpy + numpy + PIL，可在 headless 下运行。

用法：

  python3 scripts/vision/camera_probe.py \\
      --image-topic /agc/air/camera/image_raw \\
      --duration 6 --out-dir experiments/p1-4/round-1/evidence/camera-a1

产物：

  <out-dir>/frames/frame-000.png …   原始帧（最多 --max-frames 张，默认 3）
  <out-dir>/probe.json               统计与逐帧指标（含判定字段）
  <out-dir>/probe.txt                人读摘要

退出码：0 = 至少收到一帧且落在采样窗口内；2 = 一帧未收到（**不得**当作通过）。
"""

import argparse
import json
import os
import sys
import time

import numpy as np

import rclpy
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Image


def _luma_stats(msg):
    """把任意常见 encoding 归一到灰度，返回 (mean, std, unique_gray, shape_ok)。"""
    h, w = int(msg.height), int(msg.width)
    buf = np.frombuffer(bytes(msg.data), dtype=np.uint8)
    enc = (msg.encoding or '').lower()
    channels = {
        'rgb8': 3, 'bgr8': 3, 'rgba8': 4, 'bgra8': 4,
        'mono8': 1, '8uc1': 1, '8uc3': 3, '8uc4': 4, 'yuv422': 2,
    }.get(enc)
    if channels is None or buf.size != h * w * channels:
        return None
    img = buf.reshape(h, w, channels) if channels > 1 else buf.reshape(h, w, 1)
    # 亮度：BT.601（整数近似），仅用于"是不是黑屏"的判据，不做色彩学声明
    if channels >= 3:
        # RGB / BGR 的系数差异对黑屏判定无影响，统一按前三个通道加权
        gray = (img[:, :, 0].astype(np.float32) * 0.299
                + img[:, :, 1].astype(np.float32) * 0.587
                + img[:, :, 2].astype(np.float32) * 0.114)
    else:
        gray = img[:, :, 0].astype(np.float32)
    return {
        'mean_luma': float(gray.mean()),
        'std_luma': float(gray.std()),
        'unique_values': int(np.unique(buf).size),
        'shape': [h, w, channels],
    }


def _save_png(msg, path):
    """按 encoding 转 RGB / 灰度并写 PNG（PIL 仅在工具域使用）。"""
    from PIL import Image as PILImage
    h, w = int(msg.height), int(msg.width)
    buf = np.frombuffer(bytes(msg.data), dtype=np.uint8)
    enc = (msg.encoding or '').lower()
    channels = {'rgb8': 3, 'bgr8': 3, 'rgba8': 4, 'bgra8': 4,
                'mono8': 1, '8uc1': 1, '8uc3': 3, '8uc4': 4}.get(enc)
    if channels is None or buf.size != h * w * channels:
        return False
    arr = buf.reshape(h, w, channels) if channels > 1 else buf.reshape(h, w)
    if channels == 3 and enc in ('bgr8', '8uc3'):
        arr = arr[:, :, ::-1]
    elif channels == 4 and enc in ('bgra8', '8uc4'):
        arr = arr[:, :, [2, 1, 0]]
    elif channels == 4:
        arr = arr[:, :, :3]
    PILImage.fromarray(np.ascontiguousarray(arr)).save(path)
    return True


class Probe(Node):
    def __init__(self, topic, qos_depth):
        super().__init__('camera_probe')
        self.topic = topic
        self.frames = []          # (recv_monotonic, header_stamp_s, frame_id, stats)
        self.saved = 0
        self.save_dir = None
        self.max_frames = 3
        qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=qos_depth,
        )
        self.sub = self.create_subscription(Image, topic, self._on_image, qos)

    def _on_image(self, msg):
        stats = _luma_stats(msg)
        stamp = float(msg.header.stamp.sec) + float(msg.header.stamp.nanosec) * 1e-9
        self.frames.append({
            'recv_monotonic_s': time.monotonic(),
            'header_stamp_s': stamp,
            'frame_id': msg.header.frame_id,
            'encoding': msg.encoding,
            'width': int(msg.width),
            'height': int(msg.height),
            'is_bigendian': bool(msg.is_bigendian),
            'step': int(msg.step),
            'stats': stats,
        })
        if stats is not None and self.saved < self.max_frames and self.save_dir:
            path = os.path.join(self.save_dir, 'frames', 'frame-%03d.png' % self.saved)
            if _save_png(msg, path):
                self.frames[-1]['png'] = os.path.relpath(path, self.save_dir)
                self.saved += 1


def summarize(frames, duration_s):
    """按采样窗口统计；**缺值不得当 0**（沿用 P1-2 compare 的纪律）。"""
    out = {
        'frames_received': len(frames),
        'window_s': duration_s,
        'hz_mean': None,
        'dt_min_s': None,
        'dt_max_s': None,
        'dt_mean_s': None,
        'header_stamps_monotonic': None,
        'peer_qos_checked_by': 'ros2 topic info -v（本工具只报订阅端 best-effort）',
    }
    if not frames:
        return out
    recv = [f['recv_monotonic_s'] for f in frames]
    dts = [b - a for a, b in zip(recv, recv[1:]) if b > a]
    if len(recv) > 1:
        span = recv[-1] - recv[0]
        out['hz_mean'] = round((len(recv) - 1) / span, 3) if span > 0 else None
        out['dt_mean_s'] = round(float(np.mean(dts)), 6) if dts else None
        out['dt_min_s'] = round(float(np.min(dts)), 6) if dts else None
        out['dt_max_s'] = round(float(np.max(dts)), 6) if dts else None
    stamps = [f['header_stamp_s'] for f in frames]
    out['header_stamps_monotonic'] = all(b >= a for a, b in zip(stamps, stamps[1:]))
    stats = [f['stats'] for f in frames if f['stats']]
    if stats:
        out['mean_luma_median'] = round(float(np.median([s['mean_luma'] for s in stats])), 3)
        out['std_luma_median'] = round(float(np.median([s['std_luma'] for s in stats])), 3)
        out['unique_values_max'] = int(max(s['unique_values'] for s in stats))
        out['stats_ok_frames'] = len(stats)
    out['encodings'] = sorted({f['encoding'] for f in frames})
    out['frame_ids'] = sorted({f['frame_id'] for f in frames})
    out['shapes'] = sorted({tuple(f['stats']['shape']) if f['stats'] else
                            (f['height'], f['width'], None) for f in frames})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description='相机图像链路取证（P1-4）')
    ap.add_argument('--image-topic', default='/agc/air/camera/image_raw')
    ap.add_argument('--duration', type=float, default=6.0, help='采样窗口（s）')
    ap.add_argument('--out-dir', required=True)
    ap.add_argument('--max-frames', type=int, default=3)
    ap.add_argument('--qos-depth', type=int, default=5)
    # A3 判据（预登记 prereg-v1.A3）：mean_luma > 5 且 std_luma > 1
    ap.add_argument('--min-mean-luma', type=float, default=5.0)
    ap.add_argument('--min-std-luma', type=float, default=1.0)
    args, _unknown = ap.parse_known_args(argv)

    os.makedirs(os.path.join(args.out_dir, 'frames'), exist_ok=True)

    rclpy.init()
    node = Probe(args.image_topic, args.qos_depth)
    node.max_frames = args.max_frames
    node.save_dir = args.out_dir
    deadline = time.monotonic() + float(args.duration)
    try:
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.2)
    finally:
        frames = list(node.frames)
        node.destroy_node()
        rclpy.shutdown()

    summary = summarize(frames, args.duration)
    # 判定字段：**显式 null 语义**——无帧 = 未测，不是"通过"
    a2_hz_ok = summary['hz_mean'] is not None and summary['hz_mean'] >= 10.0
    a3_stats = summary.get('mean_luma_median')
    a3_ok = (a3_stats is not None
             and a3_stats > args.min_mean_luma
             and summary.get('std_luma_median', 0.0) > args.min_std_luma)
    summary['verdict'] = {
        'A2_hz_ge_10': bool(a2_hz_ok),
        'A2_threshold_hz': 10.0,
        'A3_non_black': bool(a3_ok),
        'A3_threshold': {'mean_luma_gt': args.min_mean_luma,
                         'std_luma_gt': args.min_std_luma},
        'note': 'A2/A3 只对**本采样窗口**负责；不得外推为长期稳定',
    }
    doc = {'tool': 'scripts/vision/camera_probe.py',
           'image_topic': args.image_topic,
           'captured_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
           'summary': summary,
           'frames': frames}
    with open(os.path.join(args.out_dir, 'probe.json'), 'w') as f:
        json.dump(doc, f, indent=1, ensure_ascii=False)
    with open(os.path.join(args.out_dir, 'probe.txt'), 'w') as f:
        f.write('image_topic=%s\n' % args.image_topic)
        f.write('frames=%d window=%.1fs hz=%s\n'
                % (summary['frames_received'], args.duration, summary['hz_mean']))
        f.write('encoding=%s frame_id=%s shape=%s\n'
                % (summary.get('encodings'), summary.get('frame_ids'), summary.get('shapes')))
        f.write('mean_luma_median=%s std_luma_median=%s\n'
                % (summary.get('mean_luma_median'), summary.get('std_luma_median')))
        f.write('A2_hz_ge_10=%s A3_non_black=%s\n'
                % (summary['verdict']['A2_hz_ge_10'], summary['verdict']['A3_non_black']))
    print(json.dumps({'summary': summary, 'verdict': summary['verdict']},
                     indent=1, ensure_ascii=False))
    return 0 if frames else 2


if __name__ == '__main__':
    sys.exit(main())
