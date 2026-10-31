#!/usr/bin/env python3
"""record_dataset —— 从仿真相机采 (image, label) 对（P1-4 出口判据 A8）。

定位：给视觉同学的**最小可用采样工具**。它只做一件事：按固定节拍把
`/agc/air/camera/image_raw` 的帧存成 PNG，并在同一条记录里写下能与该帧对齐的标签。

## 同步口径（必须写明，否则数据集不可用）

| 项 | 口径 |
|---|---|
| 图像时间 | `sensor_msgs/Image.header.stamp`（仿真时钟） |
| 标签时间 | **同一采样拍**内最近一次真值位姿的时间；记录 `label_stamp` 与 `dt_ms` |
| 同步方式 | **最近邻 + 窗口**：`|image_stamp − label_stamp| ≤ --max-dt-ms` 才落盘；超窗的帧**丢弃并计数**（不伪造标签） |
| 坐标 | 标签为 `world` 系目标真值位置（ENU）；**它不是检测结果**，只用于离线评分 |

## 与 ADR-0103 的关系（关键）

本工具在**数据集侧**读 `/agc/gt/<entity>` 生成标签——这是**允许的**：ADR-0103 明确
"真值仍可用于评估（ground truth 评分）"。红线是 **`vision` 运行期决策输入不得用真值**：
`scripts/vision/vision_detector.py` 不订阅任何真值话题，本工具产出的标签也**不回灌**给识别节点。

因此：**录制工具不是识别节点的一部分**，即使同机运行也不共享进程、不共享状态。

## 产物（`experiments/vision-dataset/<campaign>/`；不入 git）

```
<out-dir>/
  frames/000123.png
  labels/000123.json          # 单帧标签（含同步证据）
  index.jsonl                 # 每行一条：(png, label, stamps, dt)
  manifest.json               # 本次录制的口径快照（话题 / 实体 / 窗口 / 计数 / 判定）
```

用法：

  python3 scripts/vision/record_dataset.py \\
      --out-dir experiments/vision-dataset/p1-4-r1 --frames 10 --max-dt-ms 100 \\
      --gt-entity intruder_uav

退出码：0 = 达到 --frames 且全部同步在窗内；3 = 产出不足（帧数不够或同步超窗）；
        2 = 参数/前置错误。
"""

import argparse
import json
import os
import sys
import time

import numpy as np

import rclpy
from geometry_msgs.msg import PoseStamped
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Image


def _stamp_s(stamp):
    return float(stamp.sec) + float(stamp.nanosec) * 1e-9


def _save_png(msg, path):
    from PIL import Image as PILImage
    h, w = int(msg.height), int(msg.width)
    buf = np.frombuffer(bytes(msg.data), dtype=np.uint8)
    enc = (msg.encoding or '').lower()
    channels = {'rgb8': 3, 'bgr8': 3, 'rgba8': 4, 'bgra8': 4,
                'mono8': 1, '8uc1': 1, '8uc3': 3, '8uc4': 4}.get(enc)
    if channels is None or buf.size != h * w * channels:
        return None
    arr = buf.reshape(h, w, channels) if channels > 1 else buf.reshape(h, w)
    if channels == 3 and enc in ('bgr8', '8uc3'):
        arr = arr[:, :, ::-1]
    elif channels == 4 and enc in ('bgra8', '8uc4'):
        arr = arr[:, :, [2, 1, 0]]
    elif channels == 4:
        arr = arr[:, :, :3]
    PILImage.fromarray(np.ascontiguousarray(arr)).save(path)
    return enc


class Recorder(Node):
    def __init__(self, args):
        super().__init__('vision_recorder')
        self.args = args
        self.latest_gt = None       # (stamp_s, frame_id, position xyz)
        self.gt_count = 0
        sensor_qos = QoSProfile(reliability=ReliabilityPolicy.BEST_EFFORT,
                                history=HistoryPolicy.KEEP_LAST, depth=5)
        self.sub_image = self.create_subscription(
            Image, args.image_topic, self._on_image, sensor_qos)
        self.sub_gt = self.create_subscription(
            PoseStamped, args.gt_topic, self._on_gt, 10)
        self.saved = 0
        self.dropped_no_label = 0
        self.dropped_out_of_window = 0
        self.records = []
        self.stop_requested = False

    def _on_gt(self, msg):
        self.gt_count += 1
        p = msg.pose.position
        self.latest_gt = (_stamp_s(msg.header.stamp), msg.header.frame_id,
                          [float(p.x), float(p.y), float(p.z)])

    def _on_image(self, msg):
        if self.saved >= self.args.frames:
            self.stop_requested = True
            return
        img_stamp = _stamp_s(msg.header.stamp)
        if self.latest_gt is None:
            self.dropped_no_label += 1
            return
        gt_stamp, gt_frame, gt_pos = self.latest_gt
        dt_ms = abs(img_stamp - gt_stamp) * 1e3
        if dt_ms > self.args.max_dt_ms:
            # 超窗：**丢弃**并在 manifest 计数（不得用旧标签凑数）
            self.dropped_out_of_window += 1
            return
        idx = self.saved
        png_rel = os.path.join('frames', '%06d.png' % idx)
        enc = _save_png(msg, os.path.join(self.args.out_dir, png_rel))
        if enc is None:
            self.dropped_no_label += 1
            self.get_logger().warn('无法解码 encoding=%r → 丢弃该帧' % (msg.encoding,))
            return
        label = {
            'index': idx,
            'image': png_rel,
            'image_topic': self.args.image_topic,
            'image_stamp_s': img_stamp,
            'label_stamp_s': gt_stamp,
            'dt_ms': round(dt_ms, 3),
            'sync_method': 'nearest_gt_within_window',
            'max_dt_ms': self.args.max_dt_ms,
            'frame_id': gt_frame,          # 标签坐标系（world）
            'camera_frame_id': msg.header.frame_id,
            'target': {
                'entity': self.args.gt_entity,
                'position_xyz': gt_pos,     # 真值位置（评估用，**不是**检测结果）
                'source': 'gz_dynamic_pose_via_gt_bypass',
            },
            'label_semantics': ('ground_truth_for_evaluation_only; '
                                'not_a_detection; forbidden_as_vision_decision_input'),
            'image': {'encoding': enc, 'width': int(msg.width),
                      'height': int(msg.height), 'step': int(msg.step)},
        }
        lab_rel = os.path.join('labels', '%06d.json' % idx)
        with open(os.path.join(self.args.out_dir, lab_rel), 'w') as f:
            json.dump(label, f, indent=1, ensure_ascii=False)
        with open(os.path.join(self.args.out_dir, 'index.jsonl'), 'a') as f:
            f.write(json.dumps({'image': png_rel, 'label': lab_rel,
                                'image_stamp_s': img_stamp,
                                'label_stamp_s': gt_stamp,
                                'dt_ms': label['dt_ms']}, ensure_ascii=False) + '\n')
        self.records.append(label)
        self.saved += 1
        if self.saved >= self.args.frames:
            self.stop_requested = True


def main(argv=None):
    ap = argparse.ArgumentParser(description='仿真相机 (image, label) 采样（P1-4）')
    ap.add_argument('--image-topic', default='/agc/air/camera/image_raw')
    ap.add_argument('--gt-topic', default='/agc/gt/intruder_uav')
    ap.add_argument('--gt-entity', default='intruder_uav')
    ap.add_argument('--out-dir', required=True)
    ap.add_argument('--frames', type=int, default=10)
    ap.add_argument('--max-dt-ms', type=float, default=100.0)
    ap.add_argument('--timeout', type=float, default=60.0,
                    help='最多等多久（s）；超时按已采数量判退出码')
    args, _unknown = ap.parse_known_args(argv)

    os.makedirs(os.path.join(args.out_dir, 'frames'), exist_ok=True)
    os.makedirs(os.path.join(args.out_dir, 'labels'), exist_ok=True)
    # 覆盖式：同名 index.jsonl 追加会串轮次，这里显式清空（目录由调用方保证是本轮独占）
    open(os.path.join(args.out_dir, 'index.jsonl'), 'w').close()

    rclpy.init()
    node = Recorder(args)
    deadline = time.monotonic() + args.timeout
    try:
        while time.monotonic() < deadline and not node.stop_requested:
            rclpy.spin_once(node, timeout_sec=0.2)
    finally:
        saved = node.saved
        records = list(node.records)
        dropped_no_label = node.dropped_no_label
        dropped_window = node.dropped_out_of_window
        gt_count = node.gt_count
        node.destroy_node()
        rclpy.shutdown()

    manifest = {
        'tool': 'scripts/vision/record_dataset.py',
        'recorded_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'image_topic': args.image_topic,
        'gt_topic': args.gt_topic,
        'gt_entity': args.gt_entity,
        'target_frames': args.frames,
        'saved': saved,
        'dropped_no_label': dropped_no_label,
        'dropped_out_of_window': dropped_window,
        'gt_messages_seen': gt_count,
        'max_dt_ms': args.max_dt_ms,
        'sync': {
            'method': 'nearest_gt_within_window',
            'rule': 'accept image only if |image.header.stamp - gt.header.stamp| <= max_dt_ms',
            'out_of_window_policy': 'drop_and_count（不伪造标签）',
        },
        'label_semantics': ('ground truth from gz dynamic_pose (via gt_bypass) for OFFLINE '
                            'evaluation only; not a detection; forbidden as vision decision input '
                            '(ADR-0103)'),
        'coordinate_frames': {'camera': 'CameraInfo/Image frame_id', 'label': 'world (ENU)'},
        'verdict': {
            'enough_frames': saved >= args.frames,
            'all_within_window': dropped_window == 0,
        },
    }
    with open(os.path.join(args.out_dir, 'manifest.json'), 'w') as f:
        json.dump(manifest, f, indent=1, ensure_ascii=False)
    print(json.dumps(manifest, indent=1, ensure_ascii=False))
    if saved < args.frames:
        return 3
    return 0


if __name__ == '__main__':
    sys.exit(main())
