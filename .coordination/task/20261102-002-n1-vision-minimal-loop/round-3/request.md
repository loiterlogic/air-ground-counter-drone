<a id="request"></a>
# N1 · round-3 运行时相机与图像时间 TF 判别

- 任务 ID：`20261102-002-n1-vision-minimal-loop`；轮次：3；状态：待执行；Leader 交接时间 `2026-11-02T12:46:28+08:00`（Asia/Shanghai）。沿用唯一 Worker 会话。
- 本轮只处理 round-2 提出的阻塞：确认现有相机链是否能通过 **空中自身 odometry + SDF 固定相机外参 + optical 坐标换基**，产生与真实图像时间戳相符的 `world←optical` TF。此授权不预判结果，不允许用 GT/目标真值或目标 pose。
- 完整目标/白名单/验收：[round-1 request](round-1/request.md#request)；H0 文件所有权裁定：[round-1 review](round-1/review.md#review)、[round-2 request](round-2/request.md#request)。

## Leader 对静态拓扑的补充裁定

round-2 观察“源码中没有现成 world→drone/base_link 或 optical TF broadcaster”是事实，但“因此不能构建图像时刻 TF”尚未被证明。当前仓内证据提供了待运行核验的候选输入：

- [契约](../../../../docs/ROS2迁移交接文档.md#namespace)规定统一 `world` ENU 与 `drone/base_link` 帧；[px4_adapter.cpp](../../../../src/agc_air/src/px4_adapter.cpp) 发布 `/agc/air/odom`，其 header 为 world 位姿、child 为 drone/base_link，header stamp 来自经校验 PX4 时间映射。
- PX4 `x500_mono_cam/model.sdf` 的 `CameraJoint` 将 `mono_cam/base_link` 固定装于 `base_link`，pose `(0.12, 0.03, 0.242, 0, 0, 0)`；`mono_cam/model.sdf` 的 sensor pose 在该 link 原点。SDFormat Camera 规范提供可选 `optical_frame_id`，但这不等于已经有 ROS TF，也不单独证明图像的 frame_id 或轴向约定。
- 因此候选链是：同一时刻的 `/agc/air/odom`（仅己方机自身估计）→ `drone/base_link`，叠加经核对的 SDF 固定 sensor transform 与 optical 轴 convention → 实际图像对应的 optical frame。必须用真实 Image 与 CameraInfo header/内参、model/SDF 及官方或当前安装 Gazebo/bridge 行为核实后，才能判定候选是否合法。不得把 `mono_cam/base_link` 直接称为 optical frame，亦不得未经证据硬编码 optical frame_id/旋转。
- 本裁定允许 N1 Worker 在 N1 原白名单内新增基于 `/agc/air/odom` 和静态外参的 TF 广播/查询代码，但**本轮 round-3 先做判别取证，不实现**。若实测或坐标语义仍不能证明等价关系，则维持阻塞，向 Leader 报告所缺的最小证据/接口；不得以伪造 TF 满足验收。

## round-3 单一判别运行

1. 重读关键契约、round-1/2 请求与报告、PX4 同版本模型、现有 bridge 与 PX4 时间映射源码。查官方/已安装同版本实现中 SDF camera sensor frame、CameraInfo `optical_frame_id`、图像 header.frame_id 和 camera optical axes 的真实语义；报告引用精确来源/本地版本，不凭名字猜测。
2. 核对资源空闲、round-2 结束后的 HEAD/branch/status；保留四个 H0 文件现有差异，不重写/回退。T1 仍为 0。
3. 用**一次**授权 `full + GUI`、seed 0、`px4_sim_model:=gz_x500_mono_cam`，运行限时 ≤900 s。仅作相机链诊断：收取真实 Image 和 CameraInfo 多帧，记录 count、stamp/frame_id、分辨率、encoding、帧率、K/P 与匹配性；对图像内容保留像素/哈希/取帧证据。不可仅凭 topic list。
4. 同次运行收取 `/agc/air/odom`。逐帧记录 image stamp 对应的最近里程计 stamp、差值、frame_id，检查 TF buffer 是否能以 image stamp 查询。可写仅供诊断的 request 白名单脚本/节点测试，但本轮不改功能实现、不发布伪造 TF、不读 GT/模型目标 pose。若没有现成 TF，按上一节只在纸面/离线用契约 pose 与实测 header 评估候选刚体变换的来源/方向，不把未发布查询写成通过。
5. 运行可选择 `perception_path=truth` 作为相机硬件诊断，因为只观测自身图像链，不运行/评估 N1 目标决策；必须在 report 显著标记此 run **不是 vision acceptance**。默认 truth 是既有行为。只允许指定的单次 full+GUI，不加第二场景/额外仿真；如运行前发现占用仍先停报。
6. 判定：只有当实际图像与 CameraInfo 有效，真实 frame/optical 语义可核、odom stamp 可与 image stamp 时间对齐（记录误差），且固定外参与轴换基有独立来源时，才向 Leader 报告“可在白名单实现 TF”并列明变换。随后等待 Leader 对判别结论确认/安排；本轮不得直接进入 detector/视觉航迹实现。任一必要证据无法取得，则阻塞并精确报告最小缺口。

## 资源与保留边界

- **沿用 round-1 起点，不重置**：总墙钟始于 `2026-11-02T12:28:41+08:00`，硬截止 `16:28:41+08:00`；T1=0；T2 总量 7,200 s，round-1/2 均为 0，本轮最多 900 s；静态累计≤1,200 s，单次≤30 s。
- 若运行超时/失败如实记时计入唯一一次 T2；不可重跑或升级配置。不得 headless/lightweight，不清理进程/共享状态。所有初始运行风险与协作协议继续有效。
- 本轮只更新本轮 `round-3/report.md`；round-1/2 request/report/review 均为历史记录，不得改写。新增一次性诊断源/证据只可在 round-3 `evidence/` 或 request 允许的 `/tmp/agc-n1-*`。不改 CURRENT/共享索引/ADR/契约/消息 ABI/任务管理器/控制器/模型或 H0 语义。H0 四个已验收文件仍按 N1 视觉最小增量规则保留，但本轮不改任何实现文件。

## 交回

report 写出诊断证据及其局限，轮末状态 `待审查`（判别完成）或 `阻塞`；无论结果都先通知 Leader，不自判最终 N1 通过，不归档、不派 N2/N3、不轮询。
