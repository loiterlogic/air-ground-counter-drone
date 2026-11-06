<a id="request"></a>
# N1 · round-4 最小视觉闭环实施

- 任务 ID：`20261102-002-n1-vision-minimal-loop`；轮次：4；Leader 派发时间 `2026-11-02T14:25:00+08:00`（Asia/Shanghai）。沿用同一 Worker 会话 `5094c3e6-17a3-4ba6-a920-63615762bfce`。
- 依据：[round-3 Leader 审查](../round-3/review.md#review)（TF 阻塞已解除，候选链、平移与轴换基已裁定）。目标/边界/验收完整继承 [round-1 request](../round-1/request.md#request)；H0 文件所有权见 [round-1 review](../round-1/review.md#review) 与 [round-2 request](../round-2/request.md#request)。
- **本轮是实施轮，不是验收轮**。N1 是否通过由 Leader 独立审查决定；未验收前不得启动 N2/N3。

## 一、Leader 已裁定、不得再改的坐标事实

以下四条已在 round-3 review 逐条给出独立来源，实施时**直接采用**，不要重新推导、不要"再验证一次"：

1. `/agc/air/odom`：`header.frame_id=world`（ENU）、`child_frame_id=drone/base_link`（FLU）、100 Hz、stamp 为源采样时刻。`px4_adapter` **不**广播 TF。
2. 相机 mount（FLU 平移，**禁止**再套 FRD↔FLU）：`drone/base_link → drone/camera_link`，平移 `(0.12, 0.03, 0.242)` m，旋转单位四元数。
3. optical 轴换基：`drone/camera_link → drone/camera_optical_frame`，四元数 `(x,y,z,w)=(-0.5, 0.5, -0.5, 0.5)`（RPY `(-π/2, 0, -π/2)`）。方向已验算：link +X（前）= optical +Z。
4. Gazebo 实测 frame `x500_mono_cam_0/mono_cam/base_link/imager` **等同** `drone/camera_link`（`<sensor>` pose 为零 + fixed joint）。它是 sensor 名标签，**不是** optical 轴声明。

高度平面：H0 `cruise_alt_m` 是相对 episode-origin NED 的高度；当前世界 episode origin 在地面（z=0），故世界 ENU 平面 `z = cruise_alt_m`（s02 = 2.0 m）。必须以 launch 注入的显式参数承载（见下），manifest/summary 记录 `datum=episode_origin_ned`、`world_enu_plane_z`、`stacks_on_spawn_z=false`，**不得**从真值或目标 pose 反推平面高度。

## 二、实施范围（按白名单）

### A. TF 广播节点（新增 `src/agc_perception/src/camera_tf.cpp`）

- 订阅 `/agc/air/odom`；用 `tf2_ros::TransformBroadcaster` 以 **odom 自身 stamp** 发布 `world → drone/base_link`（位姿直接取 odom，不改写、不重采样）。
- 用 `tf2_ros::StaticTransformBroadcaster` 发布第 2、3 条两个静态变换。
- 启动时打印一次生效的平移/四元数，便于审查核对。
- **不得**读 `/agc/gt/*`、不得订阅目标话题、不得用目标真值参与任何变换。
- 参数：`world_frame`、`base_frame`、`camera_frame`、`optical_frame`、`camera_xyz`(3)、`camera_quat_xyzw`(4)、`odom_topic`，由 launch 单一注入。

### B. 视觉目标适配节点（新增 `src/agc_perception/src/vision_target.cpp`）

- 订阅：`/agc/vision/detections`（`vision_msgs/Detection2DArray`）、`/agc/air/camera/camera_info`（`sensor_msgs/CameraInfo`）；TF 用 `tf2_ros::Buffer` + `TransformListener`。
- 每帧：`stamp = detections.header.stamp`（= 源图像 stamp），查询 `world ← optical_frame` **用该 stamp**；由 `K` 做像素→光轴系射线（`z≡1`），变换到 `world`，与 `z = plane_z` 平面求交，得目标世界位置。
- 输出 `/agc/targets`（`agc_msgs/TargetTrackArray`，**不改 9 消息字段**）：`source="vision_target"`、`target_id` 沿用参数、`header.stamp` = 检测 stamp（源时刻，不刷新为 now）、`confidence` 用检测 score（链路启发值，注明未校准）、协方差按像素/内参/平面距离一阶传播给对角。
- 显式跳帧并计数（`/agc/vision/target_status`，`std_msgs/String` JSON，非 ABI）：
  - TF 查询失败 / 时间跳变后 buffer 清空；
  - CameraInfo 缺失、`K` 非法、与检测 stamp 不匹配；
  - 射线与平面无正向前向交点（`z_opt<=0` 或交点在本机后方）。
  跳帧**不得**回退真值、不得补零位姿、不得发上次位置冒充新观测。
- 无检测 → 发**空** `tracks` 数组（有节拍），不产生任何目标航迹。
- 仅当参数 `target_source == "vision_target"` 时发布 `/agc/targets`（与 `gt_adapter`/`air_fusion` 同款互斥写法）。

### C. 检测器后端（`scripts/vision/vision_detector.py`）

- 在 `BACKENDS` 注册 `synthetic_color`：`model_required=False`；对 `rgb8` 图像用 NumPy 做橙色阈值掩膜（复用 `intruder_uav` 高亮色 `(1.0, 0.50, 0.05)` 的近似范围），取最大连通域（可用简单的行/列投影或 `scipy`-free 的 BFS/标签）外接框；无有效像素 → 空列表。
- 输出 score 为链路启发值（例如掩膜内像素占比或归一化面积），**不得**宣称校准置信度；不得引入 OpenCV、模型权重、训练、数据集、多目标关联、KF/DeepSORT、参数搜索。
- `header.stamp` 必须等于源图像 stamp（既有代码已如此，保持）；`header.frame_id` 改为取 `CameraInfo.header.frame_id` 的**映射后 optical 名**（若 CameraInfo 缺失则用参数 `fallback_frame`），**不得**硬编码 Gazebo 名当 optical。
- 新增聚焦测试：合成橙图 → 有效 bbox；全黑/纯灰 → 空；stamp 透传；不订阅 `/agc/gt`。

### D. 接线（`perception_bringup.launch.py`、`w6.launch.py`、`w6_composition.py`、`perception.yaml`）

**vision 模式必须真互斥**，这是本轮最关键的结构性要求：

- `perception_bringup.launch.py` 增加 `perception_path` 参数：
  - `truth`：节点集合**与现状逐字等价**（gt_bypass、ground_odom_adapter、gt_adapter、air_perception、air_fusion、map_adapter），默认行为不变。
  - `vision`：只启 `gt_bypass`（**仅** `entities: ["agc_car"]`，只供车体里程计）、`ground_odom_adapter`、`map_adapter`、新增 `camera_tf`、`vision_target`；**不启** `gt_adapter`、`air_perception`、`air_fusion`。
    → 结果：vision run 里 `/agc/gt/intruder_uav` 无发布者，`/agc/targets` 唯一发布者是 `vision_target`。
- `w6.launch.py`：vision 且 `vision_detector:=true` 时，以 `ExecuteProcess` 起 `scripts/vision/vision_detector.py`（路径由 `agc_root` 派生），注入 `perception_path:=vision`、`detector_backend:=synthetic_color`、`vision_model_id`、`image/camera_info/detections/status` 话题与 `fallback_frame`。truth 时**不**起该进程（既有"truth+vision_detector 拒绝运行"校验保留）。
- 平面参数：`target_plane_z_m` 由 launch 从场景 `cruise_alt_m` 派生注入 `vision_target`；manifest 增记 `vision_plane:{datum, world_enu_plane_z, source, stacks_on_spawn_z:false}`，并断言 `source=scene`。
- `perception.yaml`：新增 `camera_tf`、`vision_target` 段；`vision_target` 的 `target_source` 由 launch 注入。
- **保留**四个 H0 文件既有语义：`cruise_alt_m`/`alt_m` 注释、`observe_yaw_mode` 与 manifest 字段、H0 startup 断言、s02/s04 的 `cruise_alt_m: 2.0`、s04 场景级 `observe_yaw_mode: track`。report 须逐项列出重叠 diff 并证明行为不变。
- s02 已是 `goal_follow_target: true`，**不改**；不新增场景、不改终态/期望。

## 三、运行与验收（本轮目标）

一次成功即可交回，允许必要重试，全部计入 T2：

1. 构建（必要包）→ `full + GUI`、seed 0、`s02_linear_none_nominal_track`、`px4_sim_model:=gz_x500_mono_cam`、`perception_path:=vision`、`vision_detector:=true`、`detector_backend:=synthetic_color`。
2. 必须产出并留证的判据：
   - `/agc/targets` 的 `source` 全部为 `vision_target`；`header.stamp` 与源图像 stamp 一致（抽样 ≥20 帧核对）；
   - `/agc/ground/goal` 的 `TARGET_FRESH` 序列证明目标来自 `/agc/targets`（`goal_info` 关联 target_id/源时刻）；
   - `/agc/gt/intruder_uav` 在 vision run **无发布者**（`ros2 topic info` 或节点图证据）；
   - `vision_detector`/`vision_target`/`camera_tf` 节点订阅集合**不含** `/agc/gt/*`（节点图证据）；
   - 实际 TF 查询成功（不再是 round-3 的 0/461），记录成功/失败计数与失败原因分布；
   - 终态 `TRACKING_SUCCESS`；`summary.json` 含 `perception_path=vision`、`vision_model_id=synthetic_color`（或等价后端标识）；
   - 检测指标：detection recall/precision（用离线 truth 对同一 run 评估，**truth 仅评估、不参与决策**）、3D 误差 p50/p95、图像到航迹延迟 p50/p95；
   - GUI 原始帧按契约保存，帧数与采集退出码如实记录（勿重演 H0 的"失败采集冒充完整"）。
3. 无目标负例：优先用聚焦集成测试 + 运行时接线证据（`vision_target` 收到空检测 → 空 tracks → `goal_info` 无 `TARGET_FRESH`）证明；若 T2 有余量可加一次短 GUI 负例，但**不得**为此挤掉主验收运行。
4. 未达项必须逐条列出，不得包装为通过；不得以 truth 臂替代 vision 臂。

## 四、资源

- 墙钟沿用 round-1 起点，硬截止 `2026-11-02T16:28:41+08:00`（派发时剩余约 8000 s）。
- T1 = 0。T2：round-3 已用 495 s；**本轮授权 3600 s**（含构建与 full+GUI 运行），单次构建/运行 ≤900 s；累计不得超 7200 s。
- 静态/离线累计预算 1200 s，单次 ≤30 s。
- 本任务独占构建/ROS/GZ/PX4/GUI；启动前核查占用，有冲突立即阻塞交回；不抢占、不清理他人进程、不清 `/dev/shm`。
- 停止条件不变：资源耗尽、到点、越白名单/契约、必要证据不可得即停报。连续 4 轮无区分性新证据熔断。

## 五、交回

- 只写 `round-4/report.md` 与 `round-4/evidence/`；不改 `round-1/2/3` 记录、不改 CURRENT、不归档、不派 N2/N3、不轮询、不建提醒。
- report 头部写轮末状态（`待审查` 或 `阻塞`）、领取时间、执行者与子会话 ID；正文给：差异清单（含与 H0 四文件的重叠逐项说明）、命令与退出码、证据路径与哈希、逐条验收结果、T1/T2/墙钟账目、未执行项与假设台账。
- 完成后 `send_message` 通知 Leader，然后结束本轮。
