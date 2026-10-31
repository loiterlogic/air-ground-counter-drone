# P1-4 · round-3 报告（收口轮）

<a id="p1-4-r3-report"></a>

- 任务 ID：`20261030-009-p1-4-vision`，round-3
- 执行者：Worker（workbuddy / `deepseek-v4.1-flash` / max）
- 领取：2026-10-30T20:07+08:00；报告：2026-10-30T20:12+08:00
- 状态：**待审查**（本轮为 Leader 批准的**最后一次** T2；完成即收口）
- 父会话 ID：`session-fd998168-60d9-42ef-a7df-834b0457b88f`

<a id="p1-4-r3-summary"></a>
## 审查摘要（≤30 行）

1. **唯一一次 T2 有效执行**（63 s / 450 s，1 次，未重试）：走 `run_demo` 主路径（自带 `/agc/task/start`），
   `px4_sim_model:=gz_x500_mono_cam perception_path:=vision vision_detector:=true vision_model_id:=none`。
2. **全链终态达成**：`TRACKING_SUCCESS` / `tracking_milestone`；`reset_failed=false`、`reset_retries=0`、
   `shield_infeasible_rate=0`、`reset_failure_rate=0`；`run_demo exit=0`；回收 33 进程剩 0。
3. **路径标注在真实 run 里成立**：`summary.perception_path="vision"`、`summary.vision_model={id:"none",...}` ——
   ADR-0103 要求的"证据可区分"首次在 vision 臂落盘。
4. **相机机型确实生效**：`launch.log: model name: x500_mono_cam_0, simulation model: x500_mono_cam`；
   `Ogre2Camera` 初始化；`/camera → /agc/air/camera/image_raw` 桥建立；识别节点 +10 s 看到该话题并启动。
5. **仍缺两项（我的 harness 遗漏，非系统问题）**：
   - **V4 只有部分证据**：未在运行窗口内跑 `ros2 topic hz` / `camera_probe` → **无帧频率、无像素**。
     round-2 已证伪"出现话题名=有相机"，故本轮不据此宣称相机帧已测。
   - **V6 数据集未采**：`record_dataset.py` 写了计划却**没在脚本里启动**，`experiments/vision-dataset/p1-4-r3/` 为空。
6. **V5 降级只有日志级证据**：`vision_detector.log` 有 `path=vision backend=none degraded=True`；
   但没抓 `/agc/vision/detections` 与 `/status` 的实际消息（round-1 的 A6 有完整现场，本轮没有）。
7. **ABI 未动**：本轮零代码改动；`src/agc_msgs` 零差异；回归 **227 passed**。
8. **不宣称**：视觉识别驱动决策（后端仍是 `none`，显式降级；决策输入仍是真值派生链）。

<a id="p1-4-r3-result"></a>
## 1. 判据结果

| # | 判据 | 结果 | 关键证据 |
|---|---|---|---|
| V1 | 唯一 T2 有效（走 run_demo、自带 task/start） | **PASS** | demo 目录 `experiments/demo/20261030-200828`；`run_demo exit=0`；summary 路径由其 `result.json` 报告（**未用 glob**） |
| V2 | summary 标 `vision` + 模型 `none` | **PASS** | [`evidence/v1-v3-v8-verified.txt`](../../../../experiments/p1-4/round-3/evidence/v1-v3-v8-verified.txt) |
| V3 | 终态 `TRACKING_SUCCESS` | **PASS** | 同上（含 C9 两项 0、reset 无失败） |
| V4 | 相机有**真实帧** | **PARTIAL** | 机型/渲染/桥/订阅均成立；**缺 hz 与像素**（[`v4-camera-partial.txt`](../../../../experiments/p1-4/round-3/evidence/v4-camera-partial.txt)） |
| V5 | 无模型显式降级 | **PARTIAL** | 节点日志有 `degraded=True`；未抓检测/状态话题消息 |
| V6 | ≥10 对 image+label | **NOT_RUN** | 脚本未启动录制器（`experiments/vision-dataset/p1-4-r3/` 为空） |
| V7 | ABI 未变 | **PASS** | 本轮零改动；`src/agc_msgs` 干净 |
| V8 | 回收干净 | **PASS** | `progress.log`：33 进程 → 0（6.4 s）；事后 `ps` 无残留 |

<a id="p1-4-r3-run"></a>
## 2. 运行事实

| 项 | 值 |
|---|---|
| 起止 | 20:08:28 → 20:09:31（**63 s** / 预算 450 s） |
| 命令 | `python3 scripts/demo/main.py start --headless 1 --map yard --scene s04... --backend full` + 4 个透传参数 |
| 透传 argv（实测） | `px4_sim_model:=gz_x500_mono_cam perception_path:=vision vision_detector:=true vision_model_id:=none` |
| 外部进程 | `vision_detector.py`（+10 s 起，见日志）；**`record_dataset.py` 未起（漏）** |
| 终态 | `TRACKING_SUCCESS` / `tracking_milestone`，仿真窗口 12.30→44.62 s，RTF 0.824 |
| 回收 | 33 进程 → 0，6.4 s |

<a id="p1-4-r3-gaps"></a>
## 3. 缺口与原因（不掩饰）

| 缺口 | 直接原因 | 本可避免吗 |
|---|---|---|
| V4 无帧频率/像素 | 只起了识别节点，**没起 `camera_probe.py`** | 是——预登记 V4 写了要 hz，脚本里漏了 |
| V6 无数据样本 | 只起了识别节点，**没起 `record_dataset.py`** | 是——预登记 `dataset_capture` 写了，脚本里漏了 |
| V5 无消息级证据 | 没跑 `ros2 topic echo /agc/vision/{detections,status}` | 是 |

**性质**：三处都是同一类错误——**把"要测的东西"写进了预登记，却没写进执行脚本**。
根因是我在 round-2 两次失败后把注意力放在"让 run 必须有效"（终态/路径/回收），
反而漏了**取证**这一半。这不是预算或授权问题。

<a id="p1-4-r3-budget"></a>
## 4. 预算（本轮）

| 项 | 用量 / 授权 |
|---|---|
| T2 | **1 / 1 次**；63 s / 450 s |
| T1 | 1 / 4 次（`main.py start --dry-run` 校验 argv 透传；未起仿真进程） |
| 离线 | 约 8 次（pytest ×3、summary 解析、链接/指纹），均 ≤30 s |
| 重试 | **0**（符合"完成即收口，不再追加"） |

<a id="p1-4-r3-conclusion"></a>
## 5. 结论与建议

**本轮达成**：vision 路径的**端到端接线**在真实 run 里成立——相机机型、路径标注、summary 可区分、终态、回收，全部在一次运行内同时为真。

**本轮未达成**：帧级相机证据（V4）、消息级降级证据（V5）、数据集样本（V6）。

**建议 Leader 二选一**：

- **（A）以现有证据验收 P1-4 的"链路与接口"部分**：round-1 的 A2/A3（24–26 Hz、真实 PNG、mean_luma 180.1）
  已证明相机出图；本轮的 V1/V2/V3/V7/V8 证明决策接线与路径标注；V4/V5/V6 记为**已知缺口**并挂到 P2-1 或后续轮。
- **（B）再批 1 次 T2（约 150 s 足够）**：只需把 `camera_probe.py` 与 `record_dataset.py` 加进同一脚本
  （两者都已存在、已单测、无需开发），即可补齐 V4/V5/V6。

我不自行追加启动（裁定明确"完成即收口"）。

## 6. 状态

- **待审查**。
- 未 commit（派工单禁止）。

<a id="p1-4-r3-addendum"></a>
## 7. 追加自查记录（报告落盘后、发通知前）

| 项 | 事实 |
|---|---|
| `experiments/vision-dataset/p1-4-r3/` | 我在脚本里 `mkdir -p` 建了它却**从未写入**；报告落盘后已 `rmdir`（空目录）——如实记录这次"建了没用"的写操作 |
| `experiments/demo/20261030-200738` | round-3 之前的 **dry-run** 产物（只落证据、未起进程）；为保持证据干净已删除，不是真实 run |
| 残留进程 | 收尾核对：无 gz / px4 / MicroXRCE / vision_detector |
| 代码改动 | round-3 **零改动**（`git status` 与 round-2 结束时一致） |
| 指纹 | `prereg-v1.json` = `8962e86b…0cc3`（mtime 20:08:06 < T2 起 20:08:28）；`evidence/index.json` = `3f8bf728…467d` |
