<a id="request"></a>
# N1 · round-5 最小视觉闭环实施（新 Worker 接管）

- 任务 ID：`20261102-002-n1-vision-minimal-loop`；轮次：5；Leader 派发时间 `2026-11-02T14:50:00+08:00`（Asia/Shanghai）。
- **你是新建的 Worker**：上一位执行者 `5094c3e6` 因路由错误（`subagent` 继承 Leader 模型 → `totokens/gpt-6.1-sol`）撞余额不足而中断，未产出报告。它的记录见 [round-4 review](../round-4/review.md#review)，**其残留改动未经审查，不默认正确**。
- **本轮是实施轮，不是验收轮**。N1 是否通过由 Leader 独立审查决定。

## 一、必读（按此顺序，只读这些）

1. `.coordination/CURRENT.md#current` 与 `.coordination/roles/worker.md#startup`。
2. 本文件。
3. [round-3 Leader 审查](../round-3/review.md#review)：相机链证据与**已裁定的坐标事实**。
4. 目标/边界/验收：[round-1 request](../round-1/request.md#request)、[round-2 request](../round-2/request.md#request)、[round-1 review](../round-1/review.md#review)。
5. 任务定义：`docs/plan/N1-视觉驱动最小闭环.md#n1-camera-chain`、`#n1-decision-link`、`#exit`。

## 二、已裁定的坐标事实（**直接采用，不要重新推导**）

以下四条在 [round-3 审查](../round-3/review.md#review) 已逐条给出独立来源：

1. `/agc/air/odom`：`frame_id=world`（ENU）、`child_frame_id=drone/base_link`（FLU）、约 100 Hz、stamp 为源采样时刻。`px4_adapter` **不**广播 TF。
2. 相机 mount（FLU 平移，**禁止**再套 FRD↔FLU）：`drone/base_link → drone/camera_link`，平移 `(0.12, 0.03, 0.242)` m，旋转单位四元数。
3. optical 轴换基：`drone/camera_link → drone/camera_optical_frame`，四元数 `(x,y,z,w)=(-0.5, 0.5, -0.5, 0.5)`（RPY `(-π/2, 0, -π/2)`）。方向已验算：link `+X`（前）= optical `+Z`。
4. Gazebo 实测 frame `x500_mono_cam_0/mono_cam/base_link/imager` **等同** `drone/camera_link`（`<sensor>` pose 为零 + fixed joint）。它是 sensor 名标签，**不是** optical 轴声明。

实测基线（round-3，461 帧）：`rgb8` 640×480、21.09 Hz、每帧 Image 与 CameraInfo **同戳**；`K.fx=fy≈269.968`、`cx=320`、`cy=240`、`D=0`；odom 与图像 stamp 最近邻中位差 3.6 ms；现有 TF 查询 461/461 失败（无发布者）。

高度平面：H0 `cruise_alt_m` 是相对 episode-origin NED 高度；当前 episode origin 在地面（z=0），故世界 ENU 平面 `z = cruise_alt_m`（s02 = 2.0 m）。必须由 launch 注入显式参数承载，manifest/summary 记 `datum=episode_origin_ned`、`world_enu_plane_z`、`stacks_on_spawn_z=false`；**不得**从真值或目标 pose 反推平面高度。

## 三、先修 round-4 残留

`scripts/vision/vision_detector.py` 工作区已有 +94/−2 未审查改动（橙色阈值 + 游程并查集取最大连通域、`fallback_frame`/`camera_frame_map`/`max_info_delta_s`、图像-CameraInfo 同帧同戳校验）。逐行复核后**保留可用部分**。

**必须修的缺陷**：第 263 行在 `_on_image` 回调内重复 `declare_parameter('camera_frame_map')`（第 181 行已声明）。rclpy 抛 `ParameterAlreadyDeclaredException`，被外层 `except` 吞掉后每帧降级为空检测 → "看着在跑、实际零检测"。改为使用 `__init__` 里已解析的 `self.camera_frame_map`。

若你判断该残留整体不可用，可重写同一文件；但不得因此扩大到其它文件。

## 四、实施范围（round-1 白名单内）

### A. TF 广播节点（新增 `src/agc_perception/src/camera_tf.cpp`）

- 订阅 `/agc/air/odom`；`tf2_ros::TransformBroadcaster` 以 **odom 自身 stamp** 发布 `world → drone/base_link`（位姿直接取 odom，不改写、不重采样）。
- `tf2_ros::StaticTransformBroadcaster` 发布第二节第 2、3 条两个静态变换。
- 启动时打印一次生效的平移/四元数。
- **不得**读 `/agc/gt/*`、不得订阅目标话题、不得用真值参与任何变换。
- 参数：`world_frame`、`base_frame`、`camera_frame`、`optical_frame`、`camera_xyz`(3)、`camera_quat_xyzw`(4)、`odom_topic`，由 launch 单一注入。

### B. 视觉目标适配节点（新增 `src/agc_perception/src/vision_target.cpp`）

- 订阅 `/agc/vision/detections`（`vision_msgs/Detection2DArray`）、`/agc/air/camera/camera_info`（`sensor_msgs/CameraInfo`）；`tf2_ros::Buffer` + `TransformListener`。
- 每帧：`stamp = detections.header.stamp`（= 源图像 stamp），用**该 stamp** 查询 `world ← drone/camera_optical_frame`；由 `K` 做像素→光轴系射线（`z≡1`），变换到 `world`，与 `z = plane_z` 求交得目标世界位置。
- 输出 `/agc/targets`（`agc_msgs/TargetTrackArray`，**不改 9 消息字段**）：`source="vision_target"`、`target_id` 取参数、`header.stamp` = 检测 stamp（源时刻，不刷新为 now）、`confidence` 用检测 score（链路启发值，注明未校准）、协方差按像素/内参/平面距离一阶传播给对角。
- 显式跳帧并计数（`/agc/vision/target_status`，`std_msgs/String` JSON，非 ABI）：TF 查询失败/时间跳变清空 buffer、CameraInfo 缺失或 `K` 非法或与检测 stamp 不匹配、射线与平面无正向前向交点（`z_opt<=0` 或交点在本机后方）。跳帧**不得**回退真值、不得补零位姿、不得发上次位置冒充新观测。
- 无检测 → 发**空** `tracks` 数组（有节拍），不产生航迹。
- 仅当参数 `target_source == "vision_target"` 时发布 `/agc/targets`（与 `gt_adapter`/`air_fusion` 同款互斥写法）。

### C. 检测器（`scripts/vision/vision_detector.py`）

- `synthetic_color` 后端：`model_required=False`；`rgb8` → NumPy 橙色阈值掩膜 → 最大连通域外接框；无有效像素 → 空列表。不得引入 OpenCV、模型权重、训练、数据集、多目标关联、KF/DeepSORT、参数搜索。
- score 为链路启发值，**不得**宣称校准置信度。
- `header.stamp` 必须等于源图像 stamp；`header.frame_id` 取 `CameraInfo.header.frame_id` 经映射后的 optical 名（映射表由参数注入，默认把实测 Gazebo 名映射到 `drone/camera_optical_frame`），**不得**硬编码 Gazebo 名当 optical。
- 新增聚焦测试：合成橙图 → 有效 bbox；全黑/纯灰 → 空；stamp 透传；不订阅 `/agc/gt`。

### C2. Leader 裁定 A（2026-11-02 14:57，round-5 追加）

Worker 报告并经 Leader 核实：`scenario_reset.cpp:382-395` 的读回前置**硬性要求车 + 目标两路 GT 都新鲜**（否则 `gt_stale` → return false），而 `/agc/task/start` 对其确定性失败直接 `fail(res, "reset_failed")` → **`INFRA_FAILURE`**（`task_manager.cpp:394-404`）。`gt_bypass.cpp:43-46` 只给 `entities_` 内实体建 publisher。

故原"仅 `agc_car`"会让 vision run **每次必 `INFRA_FAILURE`**。**裁定 A**：

1. vision 模式 `entities: ["agc_car", "intruder_uav"]`。
2. 判据 3 由"无发布者"改写为：**`/agc/gt/intruder_uav` 无任何目标坐标决策消费者**。证据须给 `ros2 node info` 逐节点 + 话题图，明确列出该话题的 publisher 与 subscriber 全集；并写明其**唯一消费者是 `scenario_reset`**（写前读回/回滚目标），不进入目标坐标决策。
3. 报告须核实并记录：s02 场景下 `/agc/gt/intruder_uav` **连空中侧也无消费者** —— `trajectory_tracker.cpp:119-123` 仅在 `observe_yaw_mode == "target"` 时创建该订阅；`air.yaml:63` 默认 `velocity`，s02 场景覆盖只有 `goal_follow_target` 与 `intruder_driver`，**无** `observe_yaw_mode`（`track` 是 s04 场景级设置）。
4. **连带修正**：vision 模式不启 `air_fusion`，而 `obstacles_source` 默认 `air_fusion` 会让 `map_adapter` 的 `knowledge_current()` 恒 false。`placeholder_path_planner.cpp` 与 `path_consumer.py` 均不消费 `/agc/map/valid`（Leader 已核），故不影响本项路径；但 vision 模式须把 `obstacles_source` 显式设 `config`（静态先验走 `obstacles.yaml`）。**truth 模式该值保持现状不变。**

边界不变：仍不得读 `/agc/gt/*` 参与视觉决策；不得改 `scenario_reset`/`task_manager`/契约/9 消息 ABI。

### D. 接线（`perception_bringup.launch.py`、`w6.launch.py`、`w6_composition.py`、`perception.yaml`、`CMakeLists.txt`、`package.xml`）

**vision 模式必须真互斥**，这是本轮最关键的结构性要求：

- `perception_bringup.launch.py` 增 `perception_path` 参数：
  - `truth`：节点集合**与现状逐字等价**（gt_bypass、ground_odom_adapter、gt_adapter、air_perception、air_fusion、map_adapter），默认行为不变。
  - `vision`：只启 `gt_bypass`（**`entities: ["agc_car", "intruder_uav"]`**，见下方"Leader 裁定 A"）、`ground_odom_adapter`、`map_adapter`、新增 `camera_tf`、`vision_target`；**不启** `gt_adapter`、`air_perception`、`air_fusion`。
    → vision run 内 `/agc/targets` 唯一发布者是 `vision_target`；`/agc/gt/intruder_uav` **有发布者但无决策消费者**（详见裁定 A）。
- `w6.launch.py`：vision 且 `vision_detector:=true` 时以 `ExecuteProcess` 起 `scripts/vision/vision_detector.py`（路径由 `agc_root` 派生），注入 `perception_path:=vision`、`detector_backend:=synthetic_color`、`vision_model_id`、各话题与 `fallback_frame`/`camera_frame_map`。truth 时**不**起该进程（既有"truth + vision_detector → 拒绝运行"校验保留）。
- 平面参数 `target_plane_z_m` 由 launch 从场景 `cruise_alt_m` 派生注入 `vision_target`；manifest 增记 `vision_plane:{datum, world_enu_plane_z, source, stacks_on_spawn_z:false}` 并断言 `source=scene`。
- **保留**四个 H0 文件既有语义：`cruise_alt_m`/`alt_m` 注释、`observe_yaw_mode` 与 manifest 字段、H0 startup 断言、s02/s04 的 `cruise_alt_m: 2.0`、s04 场景级 `observe_yaw_mode: track`。report 须逐项列出重叠 diff 并证明行为不变。
- s02 已是 `goal_follow_target: true`，**不改**；不新增场景、不改终态/期望。

## 五、运行与验收（本轮目标）

一次成功即可交回；允许必要重试，全部计入 T2：

1. 构建（必要包）→ `full + GUI`、seed 0、`s02_linear_none_nominal_track`、`px4_sim_model:=gz_x500_mono_cam`、`perception_path:=vision`、`vision_detector:=true`、`detector_backend:=synthetic_color`。
2. 必须产出并留证的判据：
   - `/agc/targets` 的 `source` 全部为 `vision_target`；`header.stamp` 与源图像 stamp 一致（抽样 ≥20 帧核对）；
   - `/agc/ground/goal` 的 `TARGET_FRESH` 序列证明目标来自 `/agc/targets`（`goal_info` 关联 target_id/源时刻）；
   - `/agc/gt/intruder_uav` 在 vision run **无目标坐标决策消费者**（唯一消费者是 `scenario_reset` 的写前读回；见裁定 A）；
   - `vision_detector`/`vision_target`/`camera_tf` 订阅集合**不含** `/agc/gt/*`（节点图证据）；
   - 实际 TF 查询**成功**（不再是 0/461），记录成功/失败计数与失败原因分布；
   - 终态 `TRACKING_SUCCESS`；`summary.json` 含 `perception_path=vision` 与后端标识 `synthetic_color`；
   - 检测指标：recall/precision（离线 truth 评估，**truth 只评估不参与决策**）、3D 误差 p50/p95、图像到航迹延迟 p50/p95；
   - GUI 原始帧按契约保存，帧数与采集退出码**如实记录**（H0 曾出现"8 帧采集冒充完整"，不重演）。
3. 无目标负例：优先用聚焦集成测试 + 运行时接线证据（空检测 → 空 tracks → `goal_info` 无 `TARGET_FRESH`）证明；T2 有余量可加一次短 GUI 负例，但**不得**挤掉主验收运行。
4. 未达项逐条列出，不得包装为通过；不得以 truth 臂替代 vision 臂。

## 六、资源与停止

- **墙钟硬截止 `2026-11-02T16:28:41+08:00`**（用户确认的 N1 批次起点 12:28:41 + 14,400 s）。派发时剩余约 **6,385 s**；到点即停并如实交回完成/未完成项。
- T1 = 0。**T2 剩余 6,705 s**（round-3 已用 495 s），单次构建/运行 ≤900 s。
- 静态/离线累计预算 1,200 s（round-3 用掉少量），单次 ≤30 s。
- 本任务独占构建/ROS/GZ/PX4/GUI；启动前 `ps` 核查占用，有冲突立即阻塞交回；不抢占、不清理他人进程、不清 `/dev/shm`。
- 停止条件：资源耗尽、到点、越白名单/契约、必要证据不可得即停报。**连续 4 轮无区分性新证据**熔断。
- **时间紧**：优先"实现 → 构建 → 一次 full+GUI → 报告"。不要为凑指标加跑；主验收运行一次到位比多次半成品更重要。

## 七、交回

- 接单先核对基线与资源，写 `round-5/report.md` 头部：领取时间、执行者、子会话 ID、预算起点、`执行中`。
- 只写 `round-5/report.md` 与 `round-5/evidence/`；不改 `round-1..4` 记录、不改 CURRENT、不归档、不派 N2/N3、不轮询、不建提醒。
- report 给：差异清单（含与 H0 四文件重叠逐项说明）、命令与退出码、证据路径与哈希、逐条验收结果、T1/T2/墙钟账目、未执行项与假设台账。
- 完成后状态置 `待审查` 并 `send_message` 通知 Leader，然后结束本轮。
