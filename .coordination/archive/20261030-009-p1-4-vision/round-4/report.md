# P1-4 · round-4 报告（最终取证 / 收口）

<a id="p1-4-r4-report"></a>

- 任务 ID：`20261030-009-p1-4-vision`，round-4
- 执行者：Worker（workbuddy / `deepseek-v4.1-flash` / max）
- 领取：2026-10-30T20:14:22+08:00；报告：2026-10-30T20:19+08:00
- 状态：**待审查（收口轮完成）**
- 父会话 ID：`session-fd998168-60d9-42ef-a7df-834b0457b88f`
- 授权：[`evidence/authority.txt`](../../../../experiments/p1-4/round-4/evidence/authority.txt)

<a id="p1-4-r4-summary"></a>
## 审查摘要（≤30 行）

1. **唯一 1 次 T2 有效**（72 s / 180 s，**0 重试**）：`run_demo` 主路径，
   `gz_x500_mono_cam + perception_path:=vision + vision_detector:=true + vision_model_id:=none`。
2. **V4 补齐**：等**真实帧**（不是等话题名）→ `hz` 报出 rate 后取证：
   94 帧 / **11.83 Hz** / mean_luma **174.4** / std 44.7 / rgb8 / 640×480 / 2 张 PNG。
   画面含 yard 场景与橙色目标高亮球（人工复核）。
3. **V5 补齐**：`/agc/vision/detections` 抓到 `detections: []` 且 `header.stamp` **继承源图像**
   （sec=26, nanosec=336000000），`frame_id=x500_mono_cam_0/mono_cam/base_link/imager`；
   `/agc/vision/status` 抓到 `degraded=true / degrade_reason=no_model / detection_frames_out=77 / backend=none`。
4. **V6 补齐**：**10 对** image+label（`dt_ms` 最大 **20 ms**，全部 ≤100 ms 窗口内，丢弃 0）；
   标签标 `ground_truth_for_evaluation_only / forbidden_as_vision_decision_input`。
5. **全链判据同时成立**：`TRACKING_SUCCESS` / `tracking_milestone`、`perception_path="vision"`、
   `vision_model.id="none"`、C9 两项 0、`run_demo exit=0`、回收 33→0（7.1 s）。
6. **纪律遵守**：本轮**零仓库改动**（三个 `scripts/vision/*.py` 的 sha256 与 round-1 记录一致；
   `src/ docs/ scripts/` 下无 20:14 后修改的文件）；预登记 sha256 未变。
7. **两处局限（如实）**：① 数据集落在 `round-4/dataset/`（未按 round-3 预登记的 `vision-dataset/`）；
   ② status 消息被 `ros2 topic echo` 默认截断，未捕获全量 JSON。
8. **未宣称**：视觉识别驱动决策（后端 `none` = 显式降级；决策输入仍是真值派生链）。

<a id="p1-4-r4-verdicts"></a>
## 1. 判据结果

| # | 判据 | 结果 | 证据 |
|---|---|---|---|
| V4 | 相机**真实帧**（帧频 + 像素） | **PASS** | [`v4-hz-at-detection.txt`](../../../../experiments/p1-4/round-4/evidence/v4-hz-at-detection.txt)、[`camera-probe/probe.json`](../../../../experiments/p1-4/round-4/evidence/camera-probe/probe.json)、PNG ×2 |
| V5 | detections/status **消息级** | **PASS** | [`v5-detections.txt`](../../../../experiments/p1-4/round-4/evidence/v5-detections.txt)、[`v5-status.txt`](../../../../experiments/p1-4/round-4/evidence/v5-status.txt) |
| V6 | ≥10 对 image+label | **PASS** | [`dataset/index.jsonl`](../../../../experiments/p1-4/round-4/dataset/index.jsonl)、[`manifest.json`](../../../../experiments/p1-4/round-4/dataset/manifest.json) |
| V2 | summary 标 vision + none | **PASS** | `perception_path="vision"`、`vision_model.id="none"` |
| V3 | 终态 | **PASS** | `TRACKING_SUCCESS` / `tracking_milestone`；C9 0/0；reset 无失败 |
| V7 | ABI 未变 | **PASS** | 本轮零改动；`src/agc_msgs` 干净 |
| V8 | 清理 | **PASS** | 33 进程 → 0（7.1 s）；无残留 |

<a id="p1-4-r4-run"></a>
## 2. 运行事实

| 项 | 值 |
|---|---|
| 起止 | 20:15:37 → 20:16:49（**72 s** / 180 s） |
| demo 目录 | `experiments/demo/20261030-201537` |
| summary | `experiments/w6-task-eval/20261030-s04_static_static_obs_track-0-201554-3083/metrics/summary.json` |
| summary 定位 | 读 run_demo 的 `result.json`（**不用 glob**，round-2 教训） |
| 真实帧检出 | **+33 s**（= 自有 PX4 25 s 延迟 + 相机就绪）→ 取证窗口 t≈33–60 s |
| 取证工具 | `camera_probe.py`（8 s / 2 帧）、`record_dataset.py`（10 帧）、`ros2 topic echo` ×2 |
| 终态 / 回收 | 54 s 达终态；69 s 回收完成（33→0） |

<a id="p1-4-r4-limits"></a>
## 3. 两处局限（如实）

### 3.1 数据集落点与 round-3 预登记不一致

- round-3 预登记 `dataset_capture.out_dir` 写的是 `experiments/vision-dataset/p1-4-r3/`；
- 本轮授权**禁止改预登记**，故数据落在 `experiments/p1-4/round-4/dataset/`（本轮证据目录内）；
- 影响：**无判据影响**（ADR-0007 的 `experiments/` 唯一落点仍满足）；若需统一到
  `vision-dataset/`，属后续轮/Leader 裁定的整理动作，我不擅自迁移。

### 3.2 status 消息被默认截断

- `ros2 topic echo` 对 `std_msgs/String` 长串默认 `--truncate-length`（≈128 字符）；
- 已完整可见：`degrade_reason="no_model"`、`degraded=true`、`detection_frames_out=77`、
  `detector_backend="none"`；
- 未捕获全量 JSON（本轮不可重跑）；**同一字段语义**可在 round-1 的
  [`a6/capture-phase1.json`](../../../../experiments/p1-4/round-1/evidence/degrade/a6/capture-phase1.json) 交叉核对。

### 3.3 帧率偏低（11.83 Hz vs round-1 的 24–26 Hz）

- 原因：取证与全链仿真 + 两个采集工具并发，采样被打断（`hz` 自身从 19.7 掉到 11.8）；
- **仍满足 ≥10 Hz 阈值**，但**不得**把本轮 11.8 Hz 当作该机型稳定帧率——稳定值以 round-1 为准。

<a id="p1-4-r4-budget"></a>
## 4. 预算

| 项 | 用量 / 授权 |
|---|---|
| T2 | **1 / 1 次**；**72 s / 180 s**；0 重试 |
| T1 | 0 次（本轮无需微观测；取证全在 T2 窗口内） |
| 离线 | 约 6 次（pytest ×2、geometry、links、index 校验、sha256 核对），均 ≤30 s |
| 仓库改动 | **0**（本轮只写 `experiments/p1-4/round-4/**` 与 `.coordination/` 报告） |

<a id="p1-4-r4-conclusion"></a>
## 5. 结论

P1-4 的**全部取证判据**在真实 run 内齐备：

- 相机链路真实可用（帧频、像素、PNG、画面内容）；
- 视觉路径标注可区分（`perception_path=vision` + `vision_model.id=none`）；
- 无模型显式降级在**消息级**成立（逐帧空 `Detection2DArray` + `degraded=no_model`）；
- 数据集可产出（10 对，同步 ≤20 ms，标签语义明确）；
- 任务终态、C9、回收、ABI 全部未退化。

**建议 Leader**：据此验收 P1-4（把 3.1–3.3 三条局限记为已知缺口）。**我不给验收结论。**

## 6. 状态

- **待审查**；未 commit（派工单禁止）。

<a id="p1-4-r4-addendum"></a>
## 7. 追加自查（发通知前）

| 项 | 事实 |
|---|---|
| round-4 无独立预登记 | **按授权刻意为之**（"不得改预登记"）——判据口径沿用 round-3 的 `prereg-v1.json`（sha256 `8962e86b…0cc3`，未变） |
| harness 脚本 | 只在 `/tmp/p1-4-r4-run.sh`（过程性产物，不入库） |
| 仓库改动 | **0**：`find src docs scripts -newermt "2026-10-30 20:14"` → 空；三个 `scripts/vision/*.py` sha256 与 round-1 记录一致 |
| 残留 | 收尾 `ps`：无 gz / px4 / MicroXRCE / vision_detector |
| 产物规模 | `experiments/p1-4/round-4/` 42 个文件 / 800 KB（含 10 PNG + 10 label + 2 探针 PNG） |
| 指纹 | `evidence/index.json`=`2ea5ea30…2773`、`authority.txt`=`6fe509e3…0c88`、`dataset/manifest.json`=`727ecf36…1746` |
