<a id="review"></a>
# N1 · round-3 Leader 独立审查

- 任务 ID：`20261102-002-n1-vision-minimal-loop`；轮次：3
- 审查者：Leader；审查时间：`2026-11-02T14:20:00+08:00`（Asia/Shanghai）
- 结论：**诊断成立，round-2 的 TF 阻塞已解除**；授权 round-4 进入最小视觉实现。本审查**不**验收 N1。

## 一、独立核验（不依赖执行者自述）

1. **证据文件存在且哈希与报告一致**（Leader 亲自 `sha256sum`）：
   - `launch.log` = `abc8522a…f5e6df`（报告值一致）
   - `live-probe.json` = `89c4634e…a4000c0e`（一致）
   - `frame-000.png` = `3e356423…1406407`（一致）
   - `original-run.txt` = `ac25f244…7c606f`（一致，内容 `probe_rc=1`，首版探针失败已如实留痕）
2. **真实图像**（Leader 直接读 `live-probe.json` 重算，非引用报告）：461 帧，stamp 302.908–324.720 s，跨度 21.812 s，均值 21.09 Hz，最大间隔 0.264 s；`frame_id` 唯一值 `x500_mono_cam_0/mono_cam/base_link/imager`；`rgb8`、640×480、step 1920、data 921600 B。Leader 亲自查看 `frame-000.png`：可见 yard 地图路面、灰色机体边缘与**橙色目标球**（画面中央偏右）——是真实渲染帧，不是空白/占位。
3. **CameraInfo 与图像同戳**：Leader 重算 461 组 `info_dt_s`，min=max=0.0（全部同戳）；`D=[0,0,0,0,0]`、`K.fx=269.968166`、`cx=320`、`cy=240`、`R=I`、`P` 一致。CameraInfo 独立 664 帧、30.30 Hz，与 Image 频率不同但同戳配对成立。
4. **自机 odom**：2486 帧、100.0 Hz、唯一帧对 `world→drone/base_link`；Leader 重算最近邻 `odom_dt_s`：min 1.0e-6、median 3.601e-3、max 7.906e-3 s。**足以在图像时刻做插值查询**。
5. **现有 TF 不存在**：461/461 查询失败，异常原文 `"x500_mono_cam_0/mono_cam/base_link/imager" passed to lookupTransform argument source_frame does not exist`。Leader 复核 `src/agc_air/src/px4_adapter.cpp` 全文：只 `create_publisher` odom，**无** `TransformBroadcaster`。故"无现成相机 TF"是事实，而非查询写法问题。
6. **frame_id 不等于 optical 轴约定**（本审查新增的关键证据，round-3 报告只到"需独立变换"）：
   - 上游 tag `gz-sensors8_8.2.2` 解析为 commit `9348f9fe8a11b9d50381819f51e17e136aedab8a`（Leader 用 GitHub refs API 核对，非猜测）。
   - Leader 取该 commit 的 `src/CameraSensor.cc` 全文（31809 B，sha256 `610553ec…22de48`）逐行核对：`PopulateInfo()` 第 773–788 行注释原文 *“while Gazebo interprets the camera frame to be looking towards +X, other tools, such as ROS, may interpret this frame as looking towards +Z”*，随后 `opticalFrameId` 在 SDF 未设 `<optical_frame_id>` 时**回退到 `Sensor::FrameId()`**；Image 消息（第 576 行）与 CameraInfo（第 788 行）用的是**同一个** `opticalFrameId`。
   - 因此本机实测的 `…/imager` 是 **sensor 名标签**，不是 ROS optical 轴声明；`optical_frame_id` 只改字符串，不改渲染轴。**轴换基必须显式构造**，不能由 header 推导。这一条把 round-3 的"未证实"变成了"已证实需要独立旋转"。
7. **机体坐标语义**（决定外参能否直接当 FLU 用）：Leader 复核本地 PX4 v1.15.4 `src/modules/simulation/gz_bridge/GZBridge.cpp`：第 655–659 行 position ENU→NED；第 661 行注释 *"gz odometry orientation is body FLU->ENU"*；第 675–684 行 linear/angular velocity 注释 *"in body FLU"* 后才取负转 FRD；第 744–759 行 `rotateQuaternion` 用 `q_FLU_to_FRD=(0,1,0,0)` 只在**送入 PX4** 时换基。结合 `px4_adapter.cpp` 输出 child `drone/base_link`（FLU），结论：**SDF mount 平移可直接作 FLU child 变换，不得再套 FRD↔FLU**。
8. **外参几何**：`x500_mono_cam/model.sdf` 第 7–15 行 `CameraJoint` parent `base_link`、child `mono_cam/base_link`、pose `.12 .03 .242 0 0 0`；`mono_cam/model.sdf` 第 20–21 行 `<sensor name="imager">` pose 为零 → **sensor 帧与 camera link 帧重合**。故实测 `…/imager` 与 `mono_cam/base_link` 是同一物理帧。

## 二、由此确定的候选链（Leader 裁定，round-4 按此实施）

```text
world ──(动态, 来自 /agc/air/odom, 用 odom 自身 stamp)──> drone/base_link
      ──(静态, 平移 (0.12, 0.03, 0.242) m, 旋转 I)──> drone/camera_link
      ──(静态, 轴换基)────────────────────────────> drone/camera_optical_frame
```

- **平移语义**：前 +0.12、左 +0.03、上 +0.242（FLU）；**不**做 FRD 换基。
- **轴换基**（Leader 已用 numpy 独立验算 `det=+1`）：取 optical 基在 camera_link 中的列向量 `x_opt=(0,-1,0)`、`y_opt=(0,0,-1)`、`z_opt=(1,0,0)`，即

  ```text
  R = [[0, 0, 1],
       [-1, 0, 0],
       [0, -1, 0]]
  ```

  等价四元数 `(x,y,z,w) = (-0.5, 0.5, -0.5, 0.5)`，等价 RPY `(-π/2, 0, -π/2)`。验算：`R·ex=(0,-1,0)`、`R·ey=(0,0,-1)`、`R·ez=(1,0,0)`，且 link 的 +X（前）在 optical 中为 `Rᵀ·ex=(0,0,1)=+Z`，符合 REP-103 optical 约定（x 右、y 下、z 前）。
- **帧命名**：`drone/camera_link`、`drone/camera_optical_frame`（禁止裸 `base_link`，沿用契约 `drone/` 前缀）。
- **Gazebo 名 → 契约名的映射**必须写成显式、可审查的一条：`x500_mono_cam_0/mono_cam/base_link/imager` ≡ `drone/camera_link`（依据上文第 8 点 sensor pose 为零 + fixed joint）。检测结果 `Detection2D.header.frame_id` 用 `drone/camera_optical_frame`；**stamp 必须等于源图像 stamp**。

## 三、round-3 报告的偏差与保留

- 报告称 T2 消耗"约 495 s"，与 `launch.log` 首行 `2026-11-02-13-03-19` 到末次 SIGINT `13:11:34` 一致，**采纳**；单次 ≤900 s 未超。
- 报告未把"8.2.2 源码已证 frame_id 回退为 sensor 名"写成结论，只写"未能由本机源码独立证实"。Leader 已代为补齐（上文第 6 点）；**这是补充证据，不改报告既有事实**，也不构成对 Worker 的返工要求。
- 该运行的 launch 尾部有一批 `process has died`（`px4_adapter -6`、`collision_monitor -11` 等）。Leader 对照 H0 已验收的 s04 成功运行日志（`ep_s04_static_static_obs_track_0.log`，同样 14 条 `process has died`，含 `px4_adapter -6`、`trajectory_tracker -6`）确认这是**关停阶段 SIGINT 噪声**，与 H0 成功样本同型，**不影响**本次相机/odom 采样数据的有效性。但 round-4 若把该运行当"视觉验收"，则**不成立**——本运行 `perception_path=truth`，仅相机诊断。

## 四、结论与下一步

- **阻塞解除**：round-2 提出的"无法从证据构造图像时刻 world←optical TF"已被证明**可以构造**，且构造所需的四个要素（同戳 odom、mount 外参、轴换基、sensor≡camera_link 等价）全部有独立来源。
- **授权 round-4**：按 [round-4 request](../round-4/request.md#request) 实施最小视觉闭环。**仍然不是验收**；N1 是否通过由后续 Leader 审查决定。
- 保留边界：N1 未验收前**不**启动 N2/N3。

## 五、证据

- [round-3 report](report.md#report)
- round-3 证据目录：`round-3/evidence/`（4 文件，哈希见第一节）
- 上游源码：`gz-sensors` tag `gz-sensors8_8.2.2` → commit [`9348f9f`](https://github.com/gazebosim/gz-sensors/commit/9348f9fe8a11b9d50381819f51e17e136aedab8a)（`src/CameraSensor.cc` 第 576/773–788 行）
- 机体语义：`toolchain/PX4-Autopilot/src/modules/simulation/gz_bridge/GZBridge.cpp` 第 655–684、744–759 行
- 外参：`toolchain/PX4-Autopilot/Tools/simulation/gz/models/x500_mono_cam/model.sdf` 第 7–15 行；`…/mono_cam/model.sdf` 第 20–21 行
- H0 对照：`.coordination/archive/20261102-001-h0-altitude-semantics/round-5/`（成功 s04 关停噪声同型）
