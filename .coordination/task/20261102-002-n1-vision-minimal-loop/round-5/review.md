<a id="review"></a>
# N1 · round-5 Leader 独立审查

- 任务 ID：`20261102-002-n1-vision-minimal-loop`；轮次：5
- 审查者：Leader；审查时间：`2026-11-02T16:15:00+08:00`（Asia/Shanghai）
- 结论：**视觉决策链路已实证打通，允许作为 N1 主体成果；但 N1 出口判据未全部满足，不得验收归档。** 状态：`待返工`（限 GUI 证据与检测指标两项）。

## 一、Leader 亲自核验（不依赖执行者自述）

### 1. 证据完整性

Leader 亲自跑 `sha256sum -c SHA256SUMS.txt`，6 个文件**全部 OK**；文件大小与内容均为真实产物（`launch-headless.log` 167 KB、`launch-main.log` 452 KB、`probe-headless.json` 36 KB 等），非占位。

### 2. 视觉闭环（主链）

Leader 直接读 `probe-headless.json` / `summary-headless.json` 重算，非引用报告：

| 项 | Leader 实测值 | 判定 |
|---|---|---|
| `/agc/targets` 发布者 | `vision_target`（`Publisher count: 1`，`ros2 topic info -v` 原文） | ✅ 唯一 |
| `targets_sources` | `["vision_target"]` | ✅ 唯一 |
| `goal_info_reasons` | 含 `TARGET_FRESH` | ✅ |
| `track_stamp_matches_detection` | `640/640`（100%） | ✅ stamp 透传 |
| `counts` | images 2302 / detection_arrays 2857 / targets_nonempty **640** / goal_info 393 | ✅ 一致 |
| 终态 | `terminal_state=TRACKING_SUCCESS`、`terminal_reason_code=tracking_milestone`、`terminal_state_latched=true` | ✅ |
| `start_call` | `success: true`，`reset_done=21.216`，odom 与 cmd 均新鲜 | ✅ |

`targets_sample` 逐条 `src="vision_target"`、`target_id="intruder_uav"`、`z=2.0`（= 裁定高度平面），`detection_sample` 的 `frame_id` 为 `drone/camera_optical_frame`（**不是** Gazebo 的 `…/imager`），说明帧映射生效。

### 3. 真互斥

Leader 逐条读 `node_info_*` 原文：

- `/camera_tf` 订阅：`/agc/air/odom`、`/clock`、`/parameter_events` —— **无 GT**；
- `/vision_target` 订阅：`/agc/air/camera/camera_info`、`/agc/vision/detections`、`/clock`、`/parameter_events` —— **无 GT**；
- `/vision_detector` 订阅：`/agc/air/camera/image_raw`、`/agc/air/camera/camera_info` —— **无 GT**。

`node_list` 实测**不含** `gt_adapter` / `air_perception` / `air_fusion`（含 `scenario_reset`、`task_manager` 各出现两次的既有同节点重名告警，与 N1 无关）。

`/agc/gt/intruder_uav` 的 `topic_info` 原文：publisher = `gt_bypass`（1 个），订阅者含 `scenario_reset` 与探针自身；去掉探针后唯一消费者 = `scenario_reset`。**符合 Leader 裁定 A 的口径**（无决策消费者，而非无发布者）。

### 4. TF

`tf_summary = {"queries": 40, "ok": 40, "fail": 0, "fail_reasons": []}`。round-3 的 0/461 已解除，且查询用的是图像 stamp。`tf_frame_list` 出现 `drone/camera_link` / `drone/camera_optical_frame`。

### 5. 源码核对

- `camera_tf.cpp`：平移默认 `{0.12, 0.03, 0.242}`、mount 四元数默认 `{0,0,0,1}`、optical 默认 `{-0.5,0.5,-0.5,0.5}` —— 与 round-3 裁定值逐字一致，且走参数注入而非硬编码。
- `vision_target.cpp`：`create_subscription` 仅 2 处（detections、camera_info），**无** GT 订阅。
- 高度平面 `z=2.0` 与 manifest `vision_plane.world_enu_plane_z=2.0`、`datum=episode_origin_ned`、`stacks_on_spawn_z=false` 一致。

### 6. 安全指标与 truth 对照

Leader 对同 seed 的 H0 truth 臂（`20261102-s02_linear_none_nominal_track-0-115556-6514`）与本次 vision 臂逐项比对：

| 指标 | truth | vision |
|---|---|---|
| 终态 | `TRACKING_SUCCESS` | `TRACKING_SUCCESS` |
| `shield_infeasible_rate` | 0 | 0 |
| `true_shield_infeasible` | false | false |
| `collision_count` | 1 | 1 |
| `odom_valid_ratio` | 0.982 | 0.994 |
| `visibility_rate` | 0.927 | 0.880 |

**关键判断**：两臂 `collision_count` 均为 1，且 `collision_events` 完全相同 —— 都是 `t_sim≈13.1` 时车体在出生位撞 `apron_center::link::c`、`depth=0.02975`、坐标 `(-14.4963, 1.28545)`。这是**出生场景的既有碰撞**，不是视觉路径引入的。vision 臂未因视觉而恶化安全指标。

### 7. 探针与测试的独立复跑

- Leader 在 `source` 后的环境复跑 `scripts/tests/test_n1_vision_detector.py` + `test_n1_vision_wiring.py`：**31 passed**（未 source 时 4 个 wiring 用例因 `PackageNotFoundError` 失败 —— 属测试对环境的正常依赖，非缺陷）。
- Leader 全量复跑 `scripts/tests/ src/agc_task/test/`：**387 passed，0 failed**。
- 争议测试 `test_run_logger_mission_fco.py` 单跑 **3 次均 passed**（7.23 / 9.59 / 7.24 s），全量中亦 passed。

**结论：Worker 报的"1 个既有测试失败未定论"在 Leader 独立复跑中不复现**。该测试涉及 ROS 图发现（订阅者需看到 publisher），属时序敏感型；Worker 侧失败更可能是当时图未就绪的偶发。**不成立为回归，无需在干净基线复验**，也不记为 Worker 引入的缺陷。

## 二、`git stash` 违规的裁定

Worker 在 `2026-11-02T15:13` 误用 `git stash push -- src/agc_perception/launch/perception_bringup.launch.py`，同一步内 `pop`。

Leader 独立核实：

- `git stash list` 现为 **0 条**；
- 该文件现为 `180 insertions / 16 deletions`，`grep -c "UnlessCondition(_is_vision)"` = 4，内容完整；
- 他人 dirty 文件（`agc_air`/`agc_ground`/`agc_rl`/`agc_task`）状态未变。

**裁定**：违规事实成立并已如实披露；**未造成数据损失**，路径限定只含自写文件，pop 后完整还原。按"如实披露、无实际损失、已自行纠正"处理：**记录为偏离，不加重处罚，不要求重做**。若今后再犯且未披露，则按未授权破坏处理。

## 三、未达项（决定 N1 不能验收）

| # | 未达项 | Leader 判定 |
|---|---|---|
| 1 | **GUI 原始帧 0 帧** | **实质性未达**。契约硬约束 3 要求"关键场景使用非无头（GUI）并留记录"。Worker 正确拒绝冒充，Leader 独立确认环境确不可用（见第四节）。 |
| 2 | 检测 recall/precision、3D 误差 p50/p95、延迟 p50/p95 | **实质性未达**。N1 出口判据明确要求记录这些数值。探针未采 GT 样本与配对链，属可补的采集缺口。 |
| 3 | `summary.json` 无 `detector_backend` | **需修**。契约 `#perception-path` 要求产物记录 `perception_path` 与视觉模型标识；当前 `vision_model={id:"none",...}` 会让本 run 在两条路径比较时**不可区分**为视觉后端，虽 manifest 有 `synthetic_color`，但契约指 summary。 |
| 4 | GUI 无目标负例 | 未达，但#1 补齐 GUI 时一并可做。 |
| 5 | `state_sequence` 为空 | 探针缺陷，已修未验；不阻塞（终态由 summary 独立证明）。 |

## 四、GUI 环境：Leader 亲自尝试并确认不可得

Worker 的判断我独立复现并**进一步尝试了绕过方案**，均失败：

1. `DISPLAY=:0`、`/mnt/wslg/.X11-unix` 空（0 项），`/tmp/.X11-unix` 亦空；无 `Xorg`/`Xwayland`/`Xvfb` 二进制；`id -u` = 1000，**无 sudo**（`sudo -n true` 失败）。
2. Leader 尝试 `apt-get download xvfb` + `dpkg-deb -x` 到 `/tmp` **无 root 解包**：成功取得 `Xvfb` 与 `xvfb-run`，补 `libxfont2`、`x11-xkb-utils`、`xkb-data` 后 `ldd` 缺失项归零 —— 但启动仍失败于 `Keyboard initialization failed`（Xvfb 内部硬编码 `/usr/bin/xkbcomp`，该路径在命名空间内只读，`mount --bind` 到 `/usr/bin` 会连带遮蔽 `mount`/`sleep`/`ls`）。
3. `unshare -r -m` + 绑定 `/tmp/.X11-unix` 可绕过 socket 目录权限，但越不过 `/usr/bin/xkbcomp` 硬路径。

**结论**：本会话内无法产出 GUI 证据，是环境限制，非实现缺陷。Worker 的判断与处置（不冒充、如实记为未达项）**正确**。

## 五、Worker 修掉的四个 bug —— Leader 认可其证据价值

这四个都属于"看着在跑、其实零输出"型，是 Worker 主动发现而非派工单要求：

1. round-4 残留的重复 `declare_parameter`（我在 round-4 review 已点名）。
2. **round-4 橙色绝对阈值在实测帧命中 0 像素** —— 整帧零检测。Leader 复核 `vision_detector.py` 现为相对色差 `r>=140 & (r-b)>=60 & (g-r)<=0`，默认值走参数。
3. **score 尺度**：整帧面积比使 `confidence` 永远过不了 0.5 门 → "有检测但永远没有新鲜航迹"。现改为 `min(1.0, area / score_ref_area_px)`，`score_ref_area_px` 默认 40。
4. **射线方向判据**误杀俯视帧（相机在平面上方时 `b_w.z<0`）。现改为只拒平行、`t>0` 统一判前后。

Leader 判定：**2、3 属于导致"假绿"的关键缺陷**（若不修，链路会显示"有检测有航迹"却永远不触发 `TARGET_FRESH`，或相反），其发现与修复应记入 N1 成果。

## 六、N1 不能验收的理由汇总

- 出口判据"关键场景留 GUI 证据"**未满足**（0 帧）；
- 出口判据"记录检测率、三维误差 p50/p95、图像到航迹延迟"**未满足**（无值）；
- 契约要求 summary 记录视觉模型标识，当前 `vision_model.id="none"` **不可区分**。

这三项都是**可补的**，不是能力缺口。主体链路（图像 → 检测 → TF → 投影 → 航迹 → goal → 终态）已由 Leader 独立实证。

## 七、下一步

- N1 状态 `待返工`，round-6 由**同一 Worker**继续（该会话仍有有效上下文，符合返工复用）。
- round-6 只做三件事：**（a）补 GUI 证据；（b）补检测指标采集；（c）`detector_backend` 入 summary**。
- 资源：N1 原批次墙钟已于 `16:28:41` 耗尽；GUI 与指标补证需**新授权**，由用户确认。
- N1 未验收前不启动 N2/N3。

## 八、证据

- [round-5 report](report.md#report)
- round-5 证据目录：`round-5/evidence/`（6 文件，`sha256sum -c` 全 OK）
- 原始 run：`experiments/w6-task-eval/20261102-s02_linear_none_nominal_track-0-155603-2790/`
- truth 对照：`experiments/w6-task-eval/20261102-s02_linear_none_nominal_track-0-115556-6514/`
- 上游源码与坐标裁定：[round-3 review](../round-3/review.md#review)
