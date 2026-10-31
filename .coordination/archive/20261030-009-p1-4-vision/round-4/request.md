# P1-4 · round-4 最后一次取证补证

<a id="p1-4-r4-request"></a>

## 裁定

round-3 的有效 vision run 证明了相机机型、路径标注、summary、终态和清理，但 V4/V5/V6 未取得现场证据，因此 P1-4 不验收。

## 唯一允许操作

追加**最后一次且仅一次 T2 / 180 秒**，不改代码、不改配置、不改预登记口径、不重跑已有无效实验：

- 使用现有 `run_demo` vision 主路径：`gz_x500_mono_cam + perception_path=vision + vision_detector=true + vision_model_id=none`；
- 同一次有效运行中实际启动已有 `camera_probe.py`、`record_dataset.py`；
- 采集并保存：
  1. 真实 `/agc/air/camera/image_raw` 帧频率/像素证据（V4）；
  2. `/agc/vision/detections` 与 `/agc/vision/status` 的实际消息，明确空检测、`degraded=true`、`reason=no_model`（V5）；
  3. 至少 10 个真实 image+label 样本，写明同步窗口与 evaluation-only 标签来源（V6）。
- 必须核对本次 run 的 summary 路径、终态、回收和无残留；失败也要如实收口。
- 只允许使用已存在工具和已授权参数。若现有入口无法在不改代码的条件下同时启动工具，立即停止报告，不自行修改。

## 收口

本轮完成后无论 V4/V5/V6 是否成功，均置待审查并结束 P1-4；不再追加任何 T2，不开始后续任务。
