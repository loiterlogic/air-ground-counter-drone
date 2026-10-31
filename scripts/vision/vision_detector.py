#!/usr/bin/env python3
"""vision_detector —— 可插拔视觉识别节点 + **显式降级**（P1-4 / ADR-0103）。

定位：把「仿真图像 → 识别结果」这条链的**接入位**定下来。识别算法本身是视觉同学的工作；
本节点提供的是**契约与骨架**：

```text
/agc/air/camera/image_raw  ──┐
/agc/air/camera/camera_info ─┤→ [本节点：backend 可替换] → /agc/vision/detections
                             │                            /agc/vision/status
                             └─ 仅这两路输入；**不订阅任何真值话题**
```

## 三条不能碰的红线（ADR-0103）

1. **不得读真值补齐检测**：本节点**不订阅** `/agc/gt/*`（代码层面没有该订阅；`ros2 node info`
   可直接核对）。位置类信息只能来自图像几何 + `CameraInfo`。
2. **无模型必须显式降级**：`vision_model_id=none` 时发布**空检测数组**（有节拍、不是不发），
   并在 `/agc/vision/status` 标注 `degraded=true, degrade_reason="no_model"`。
   **不得**静默改走 truth 链。
3. **不改 9 消息 ABI**：检测结果用 `vision_msgs/Detection2DArray`（标准消息，**不在** `agc_msgs` 的
   9 个冻结消息内）；状态用 `std_msgs/String`（JSON）。

## `perception_path` 互斥

节点要求 `perception_path=vision` 才工作；`truth` 时**拒绝启动**（退出码 2）——
避免"以为在跑视觉、其实两条路都在跑"的混读。选择由 launch 单一设置，节点不覆写。

## 坐标口径

`bbox` 是**像素框**（`vision_msgs/BoundingBox2D`，`center.position` 为像素坐标，
`size_x/size_y` 为像素宽高），`header.frame_id` 为相机光学系（沿用 `CameraInfo.header.frame_id`）。
**不输出世界坐标**：像素 → 世界需要距离（单目无深度），本项目**不**用真值距离补它。

## 插拔方式

`--backend` / 参数 `detector_backend` 选择实现；新增算法只需在 `BACKENDS` 注册一个
`(node, image_msg) -> list[dict]` 函数。当前内置：

| backend | 语义 |
|---|---|
| `none` | **无模型**：恒返回空列表 + degraded=true（默认值，保证"没模型也能跑"） |

用法：

  ros2 run 无（本仓为脚本）：python3 scripts/vision/vision_detector.py \\
      --ros-args -p perception_path:=vision -p vision_model_id:=none

退出码：0 = 正常退出（SIGINT）；2 = 参数/前置不满足（显式拒绝，不静默降级）。
"""

import json
import sys
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import CameraInfo, Image
from std_msgs.msg import String
from vision_msgs.msg import (BoundingBox2D, Detection2D, Detection2DArray,
                             ObjectHypothesisWithPose)


# --------------------------------------------------------------------------------------
# backend 注册表：识别实现可插拔（新增算法只在这里加一项）
# --------------------------------------------------------------------------------------

def _backend_none(node, image_msg, camera_info):
    """无模型后端：显式返回空检测（**不**读真值、**不**伪造）。"""
    return []


BACKENDS = {
    # name: (callable(node, image_msg, camera_info) -> list[dict], model_required)
    #   dict 字段：class_id(str), score(float), cx,cy,w,h(像素)
    'none': (_backend_none, False),
}


class VisionDetector(Node):
    def __init__(self):
        super().__init__('vision_detector')
        # ---- 路径互斥（ADR-0103）----
        self.perception_path = self.declare_parameter('perception_path', 'truth').value
        if str(self.perception_path) != 'vision':
            # 显式拒绝：**不**在此节点里跑 truth，避免两条路径混读
            self.get_logger().fatal(
                'perception_path=%r ≠ vision → 本节点拒绝启动（truth 路径由既有真值派生链承担；'
                '两条路径互斥，不得同一 run 内混跑，见 ADR-0103）' % (self.perception_path,))
            raise SystemExit(2)

        self.image_topic = self.declare_parameter(
            'image_topic', '/agc/air/camera/image_raw').value
        self.camera_info_topic = self.declare_parameter(
            'camera_info_topic', '/agc/air/camera/camera_info').value
        self.detections_topic = self.declare_parameter(
            'detections_topic', '/agc/vision/detections').value
        self.status_topic = self.declare_parameter(
            'status_topic', '/agc/vision/status').value
        self.detector_backend = str(self.declare_parameter(
            'detector_backend', 'none').value)
        # 模型标识（预登记 model_contract）：**空模型必须有显式标识**，不得留空冒充"有模型"
        self.model_id = str(self.declare_parameter('vision_model_id', 'none').value)
        self.model_name = str(self.declare_parameter('vision_model_name', '').value)
        self.model_version = str(self.declare_parameter('vision_model_version', '').value)
        self.model_sha256 = str(self.declare_parameter('vision_model_sha256', '').value)
        self.max_rate_hz = float(self.declare_parameter('max_rate_hz', 10.0).value)
        self.image_timeout_s = float(self.declare_parameter('image_timeout_s', 1.0).value)
        self.min_confidence = float(self.declare_parameter('min_confidence', 0.0).value)
        self.status_period_s = float(self.declare_parameter('status_period_s', 1.0).value)

        if self.detector_backend not in BACKENDS:
            self.get_logger().fatal(
                '未知 detector_backend=%r（可用：%s）→ 拒绝启动'
                % (self.detector_backend, sorted(BACKENDS)))
            raise SystemExit(2)
        _, model_required = BACKENDS[self.detector_backend]
        if model_required and (not self.model_id or self.model_id == 'none'):
            self.get_logger().fatal(
                'backend=%r 需要模型，但 vision_model_id=%r → 拒绝启动（不静默回退 truth/none）'
                % (self.detector_backend, self.model_id))
            raise SystemExit(2)

        # 无模型 = 显式降级（唯一允许的"跑不动"形态：空检测 + 标注）
        self.degraded = (self.detector_backend == 'none') or self.model_id == 'none'
        self.degrade_reason = 'no_model' if self.degraded else ''

        sensor_qos = QoSProfile(reliability=ReliabilityPolicy.BEST_EFFORT,
                                history=HistoryPolicy.KEEP_LAST, depth=5)
        self.sub_image = self.create_subscription(Image, self.image_topic,
                                                  self._on_image, sensor_qos)
        self.sub_info = self.create_subscription(CameraInfo, self.camera_info_topic,
                                                 self._on_info, sensor_qos)
        self.pub_det = self.create_publisher(Detection2DArray, self.detections_topic, 10)
        self.pub_status = self.create_publisher(String, self.status_topic, 10)

        self.camera_info = None
        self.last_image_mono = None
        self.images_in = 0
        self.detections_out = 0
        self.frames_skipped_rate = 0
        self.last_emit_mono = 0.0
        self.started_mono = time.monotonic()
        self.create_timer(self.status_period_s, self._publish_status)
        self.get_logger().info(
            'vision_detector: path=%s backend=%s model=%s/%s degraded=%s image=%s'
            % (self.perception_path, self.detector_backend, self.model_name or '-',
               self.model_id, self.degraded, self.image_topic))

    # ---- 输入 -------------------------------------------------------------------
    def _on_info(self, msg):
        self.camera_info = msg

    def _on_image(self, msg):
        self.images_in += 1
        now = time.monotonic()
        self.last_image_mono = now
        # 降频：识别通常慢于采集（接口约定 ≤10 Hz）
        if self.max_rate_hz > 0 and (now - self.last_emit_mono) < (1.0 / self.max_rate_hz):
            self.frames_skipped_rate += 1
            return
        self.last_emit_mono = now

        fn, _ = BACKENDS[self.detector_backend]
        try:
            raw = fn(self, msg, self.camera_info)
        except Exception as exc:            # noqa: BLE001 —— 后端异常必须显式降级，不得带病发布
            raw = []
            self.degraded, self.degrade_reason = True, 'backend_error'
            self.get_logger().error('backend %s 异常 → 空检测 + degraded: %s'
                                    % (self.detector_backend, exc))

        frame_id = (self.camera_info.header.frame_id if self.camera_info is not None
                    else 'drone/mono_cam_optical')
        out = Detection2DArray()
        # 检测结果**继承源图像时间戳**（下游可用近似同步器对齐图像；不另造时间）
        out.header.stamp = msg.header.stamp
        out.header.frame_id = frame_id
        for d in raw:
            if float(d.get('score', 0.0)) < self.min_confidence:
                continue
            det = Detection2D()
            det.header = out.header
            hyp = ObjectHypothesisWithPose()
            hyp.hypothesis.class_id = str(d.get('class_id', 'target'))
            hyp.hypothesis.score = float(d.get('score', 0.0))
            det.results.append(hyp)
            det.bbox.center.position.x = float(d.get('cx', 0.0))
            det.bbox.center.position.y = float(d.get('cy', 0.0))
            det.bbox.center.theta = 0.0
            det.bbox.size_x = float(d.get('w', 0.0))
            det.bbox.size_y = float(d.get('h', 0.0))
            out.detections.append(det)
        self.pub_det.publish(out)
        self.detections_out += 1

    # ---- 状态（可区分性证据）-----------------------------------------------------
    def _publish_status(self):
        now = time.monotonic()
        image_age = (None if self.last_image_mono is None
                     else round(now - self.last_image_mono, 3))
        no_image = (image_age is None) or (image_age > self.image_timeout_s)
        degraded = self.degraded
        reason = self.degrade_reason
        if no_image and not degraded:
            degraded, reason = True, 'no_image'
        doc = {
            'perception_path': self.perception_path,
            'detector_backend': self.detector_backend,
            'vision_model_id': self.model_id,
            'vision_model_name': self.model_name,
            'vision_model_version': self.model_version,
            'vision_model_sha256': self.model_sha256,
            'degraded': bool(degraded),
            'degrade_reason': reason or None,
            'image_topic': self.image_topic,
            'image_age_s': image_age,
            'images_in': self.images_in,
            'detection_frames_out': self.detections_out,
            'frames_skipped_rate_limit': self.frames_skipped_rate,
            'uptime_s': round(now - self.started_mono, 3),
            'truth_inputs_subscribed': [],   # 恒为空：本节点不订阅真值（可被 ros2 node info 复核）
        }
        m = String()
        m.data = json.dumps(doc, ensure_ascii=False, sort_keys=True)
        self.pub_status.publish(m)


def main(argv=None):
    rclpy.init(args=argv)
    try:
        node = VisionDetector()
    except SystemExit as exc:
        rclpy.shutdown()
        return int(exc.code or 2)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
    return 0


if __name__ == '__main__':
    sys.exit(main())
