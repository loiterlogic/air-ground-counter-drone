<a id="report"></a>
# N1 · round-3 执行报告

- 任务 ID：`20261102-002-n1-vision-minimal-loop`；轮次：3
- 执行者：原 N1 Worker 会话 `5094c3e6-17a3-4ba6-a920-63615762bfce`
- 领取时间：`2026-11-02T12:51:38+08:00`（Asia/Shanghai）
- 状态：**阻塞**
- 本轮目标：使用唯一一次授权 full+GUI 运行判别真实 image/CameraInfo frame 与 H0 允许的自身 odom + SDF 固定相机外参图像时刻 TF 候选；明确不是 vision acceptance。
- 预算：继承 round-1 起点 `2026-11-02T12:28:41+08:00`，硬截止 `16:28:41+08:00`；T1=0；T2 本轮实际消耗约 495 s（约 13:03:19 至 13:11:34；低于单次 900 s），T2 累计约 495/7200 s。未构建；未启动第二次仿真。

## 接单与基线

- 接单时间：`2026-11-02T12:51:38+08:00`。HEAD `49e099ccbead0cd222e06edce29acbf78b8d3c58`，分支 `main`；工作区原有改动保留。round-1/2 的四个 H0 文件按 Leader 裁定只保留，round-3 未触碰实现文件及 H0 内容。
- 接单前 `ps` 未发现 `gz|gazebo|px4|ros2|colcon|rviz|w6.launch|perception_bringup` 进程；未发现资源冲突。T1=0，round-1/2 T2=0。
- 本轮仅更新本报告。临时只读探针位于 `/tmp/agc-n1-r3-probe.py` 与 `/tmp/agc-n1-r3-live-probe.py`，订阅 Image、CameraInfo、`/agc/air/odom`，并在 live probe 中只读查询 TF buffer；不发布 TF、不读取 GT/目标真值。

## 唯一 Full+GUI 诊断运行

- Run 命令：`ros2 launch agc_task w6.launch.py backend:=full scene:=s02_linear_none_nominal_track seed:=0 px4_sim_model:=gz_x500_mono_cam perception_path:=truth vision_detector:=false gui_render_backend:=auto gz_args:="-r -v 3 <installed agc_world.sdf>"`；为满足 launch 环境要求，设置 `GZ_SIM_SYSTEM_PLUGIN_PATH=$PWD/install/agc_sim/lib`。
- **Truth 仅用于硬件/相机诊断，不是 vision acceptance**：没有评估或宣称 N1 的视觉目标决策通过；该启动维持默认 truth 链，仅采己方相机和己方估计 odom。无额外场景、无 headless/lightweight。
- Launch 日志确认 Gazebo Sim Server 与 GUI 均为 8.15.0；full 栈启动双 PX4 与相机模型 `x500_mono_cam_0`。有效图像采样覆盖 sim stamp 302.908–324.720 s（25 s listener 窗口）；后续短暂 listener 仅保存一帧并记录时戳，不重启仿真。
- 采集：Image 461 帧；CameraInfo 664 帧；`/agc/air/odom` 2486 帧。Image 平均 21.09 Hz，区间 0.032–0.264 s（最大间隔含 drop/stall）；CameraInfo 平均 30.30 Hz，区间 0.032–0.036 s。该运行呈现 CameraInfo 与 Image 发布频率不同，但 probe 采集的所有 Image 均有同戳 CameraInfo，最近 stamp 差 min/max/mean 均 0。
- Image：`frame_id=x500_mono_cam_0/mono_cam/base_link/imager`，`640×480`、`rgb8`、step 1920、data 921600 bytes。示例帧 stamp 302.908 s，SHA-256 `6b737b3cec55d5b3bddb9135e137405a9ba15865d3ec6e6a327037ebf1e5767c`，mean 179.661、std 41.565；有非黑像素内容。另保存 PNG 原始取帧供查看。
- CameraInfo：同 frame_id、同 `640×480`；`distortion_model=plumb_bob`，`D=[0,0,0,0,0]`，`K=[269.968166,0,320;0,269.968185,240;0,0,1]`，`R=I`，`P=[269.968166,0,320,0;0,269.968185,240,0;0,0,1,0]`。
- 自机 odom：`header.frame_id=world`，`child_frame_id=drone/base_link`；同图像时间戳最近邻绝对差 1 μs–7.906 ms，平均 3.041 ms。示例 image stamp 302.908 与 odom stamp 302.908193，差 0.193 ms。时间戳可按 nearest sample 对齐，但 `/agc/air/odom` 并非 ROS TF broadcaster。
- 只读 TF buffer 查询：对 461 个 Image stamp 逐个查询 `lookup_transform("world", image.header.frame_id, image.header.stamp)`，0 成功 / 461；异常均指出源 frame 不存在。此查询仅表示图中没有以相机消息实际 frame_id 命名的 TF，不能据此否定用经证明的自机 odom + 固定外参构造候选 TF。
- 运行终止：SIGINT 发给本 Worker 自建 launch；随后按 PPID/PGID 核对并停止该 run 遗留 XRCE agents。最终 `ps` 对 `gz sim|px4|ros2 launch|MicroXRCEAgent|agc_n1_r3` 无匹配。采样 / 探针程序问题：首个试跑在 launch 环境 `COLCON_TRACE` 的 nounset 处失败，未启动仿真；唯一正式 run 的首版 probe 最近邻汇总因误调用 `abs()` 异常，随后在**同一次运行**中用修正的 live probe 得到上列全量统计和 TF 查询。包装 job 清理没有正确等待 ros2 launch，导致仿真实际运行约 495 s 而非预计窗口；仍在单次 900 s 上限内。按原始 `run.txt` probe 退出码 1 记录首版失败，不把它当成数据验收。

## Camera Frame 与轴向证据

- 当前 SDF [`mono_cam/model.sdf`](../../../../../../toolchain/PX4-Autopilot/Tools/simulation/gz/models/mono_cam/model.sdf) 的 `<sensor name="imager">` pose 为零，未声明 `<optical_frame_id>`；父模型 [`x500_mono_cam/model.sdf`](../../../../../../toolchain/PX4-Autopilot/Tools/simulation/gz/models/x500_mono_cam/model.sdf) 通过 CameraJoint 把相机 link 固定到 base_link，SDF pose `(0.12, 0.03, 0.242, 0, 0, 0)`。此项只证明静态 link 外参来源，不自行证明图像光轴 convention。
- 本机 `ros-jazzy-gz-sensors-vendor` 版本 `0.0.6-1noble.20260905.071631`，安装的 CMake package 报 `gz-sensors 8.2.2`；`ros_gz_bridge` package metadata 为 1.0.24；运行日志 Gazebo Sim 8.15.0。
- 上游 `gz-sensors` tag `gz-sensors8_8.2.2` 对应准备版本 commit [`9348f9f`](https://github.com/gazebosim/gz-sensors/commit/9348f9fe8a11b9d50381819f51e17e136aedab8a)。上游后续提交 [`1bda368`](https://github.com/gazebosim/gz-sensors/commit/1bda368eee9828a6ebf923f2d783d0560023a658) 显式移除 `sdf::Camera::OpticalFrameId` 使用，改由 Image 与 CameraInfo 都用 `Sensor::FrameId()`；官方 [CameraSensor patch](https://github.com/gazebosim/gz-sensors/commit/1bda368eee9828a6ebf923f2d783d0560023a658.patch) 保留说明 Gazebo camera frame 朝 +X，而 ROS 工具常按 +Z，配置 frame ID 本身不改变渲染 convention。该修正提交在 8.2.2 tag 之后，不能当成本机 8.2.2 的实现源码证据；本机只安装 headers/libraries，没有可检查的 `CameraSensor.cc` 源文件。官方 [issue #488](https://github.com/gazebosim/gz-sensors/issues/488) 讨论 rendering sensor +X / ROS optical +Z 与通过单独 static transform 建立 optical child 的 workaround。此项说明来源以官方上游历史为准，本地 runtime frame 仍以实测为准。
- 实测 Image 与 CameraInfo 共有的 frame ID 是 `x500_mono_cam_0/mono_cam/base_link/imager`。当前 SDF 无 optical_frame_id，且 gz-sensors 8.2.2 上游行为未能从本机安装源码直接核实；不能因为 header 同名就把该 frame 认作 ROS optical frame，也不能仅凭 `CameraInfo` 的 frame 字段推导轴旋转。官方后续实现与 issue 的 +X/+Z 说明足以判定轴向需要一个独立、明示的变换；具体旋转矩阵/四元数及 frame 命名仍需对照本机实际 8.2.2 源码/运行渲染约定或权威版本资料后再写进 TF。

## 证据与结论

- 证据目录：`.coordination/task/20261102-002-n1-vision-minimal-loop/round-3/evidence/`
  - `launch.log`（SHA-256 `abc8522ade128f8cf295dc922e2e47b1df539b9cda59d9f67dc20a0ad7f5e6df`）
  - `live-probe.json`（所有 Image/CameraInfo/odom 样本、每张图的 CameraInfo/odom 最近邻、每张图的 TF 查询及异常；SHA-256 `89c4634e183dcc3a2586ae744256d4ca7ad652297afd0c6d4f816949a4000c0e`）
  - `frame-000.png`（stamp 370.36，frame_id 同上；SHA-256 `3e3564233def068641024f0eb167c8ea63f5af05f2beffe057a2388ec1406407`）
  - `original-run.txt`（原首版 probe 退出码 1；SHA-256 `ac25f244ec3072d672a23023d0bf543734a53cdc78e4736bc30a9e85fd7c606f`）
- 判定：运行证实真实 Image、有效且同戳 CameraInfo、可见像素、自机 odom 与图像时间戳可紧密 nearest-align；实际相机 message frame_id 也已实测。但没有现成相机 frame TF，且 optical 轴向与 8.2.2 的 frame_id 解析细节未能由本机源码独立证实。因此本轮只能报告“存在可继续研究的 odom + SDF 外参候选”，不能宣称可合法构造已证实的 `world←optical` TF，也不能进入 detector/投影实现。候选链须补齐 gz-sensors 8.2.2 精确源码/tag 对照与相机渲染轴 convention 的权威来源，明确 optical child frame 名/轴变换，再由 Leader 裁定后实施。GT 只由 truth 硬件诊断场景启动，未被用于目标投影、TF 查询输入或候选变换。
- 本轮预算：T1=0；T2 一次 full+GUI，约 495 s，运行次数 1；未构建、未运行额外仿真。round-1/2 报告未修改；CURRENT 未修改；9 消息 ABI 未触碰。H0 四文件行为未触碰，先前文件状态差异完整保留。
- 结论通知：已通知 Leader，本轮状态阻塞，等待 Leader 审查并确认后续最小取证/实现授权。
