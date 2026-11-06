<a id="request"></a>
# N1 · 视觉驱动最小闭环 · round-1 批次派工

- 任务 ID：`20261102-002-n1-vision-minimal-loop`；轮次：1；派发时间：`2026-11-02T12:28:41+08:00`（Asia/Shanghai）。
- 来源：用户原始要求“完成 H0 后按顺序完成 N1、N2、N3”；Leader 已独立验收并归档 H0。用户确认 N1 预算：**总墙钟 14,400 s，T2 7,200 s**。
- N1 目标与边界：[N1 任务定义](../../../../docs/plan/N1-视觉驱动最小闭环.md#n1-vision)、[三维与决策链接通](../../../../docs/plan/N1-视觉驱动最小闭环.md#n1-decision-link)、[相机链路硬接口](../../../../docs/plan/N1-视觉驱动最小闭环.md#n1-camera-chain)、[出口判据](../../../../docs/plan/N1-视觉驱动最小闭环.md#exit)。
- 上位约束：[契约真源](../../../../docs/ROS2迁移交接文档.md#hard-constraints)、[感知路径契约](../../../../docs/ROS2迁移交接文档.md#perception-path)、[ADR-0009](../../../../docs/adr/0009-perception-truth-derived-and-vision-path.md#top)、[能力闭环裁定](../../../../docs/plan/能力闭环裁定.md#rulings)。
- 前置与证据：[H0 最终审查](../../../../.coordination/archive/20261102-001-h0-altitude-semantics/round-5/review.md#review)、[H0 s02 full+GUI truth 对照](../../../../experiments/w6-task-eval/20261102-s02_linear_none_nominal_track-0-115556-6514/metrics/summary.json)、[H0 s02 manifest](../../../../experiments/w6-task-eval/20261102-s02_linear_none_nominal_track-0-115556-6514/config/scene_manifest.json)。
- 必读接单协议：[CURRENT](../../../../.coordination/CURRENT.md#current)、[Worker 角色](../../../../.coordination/roles/worker.md#startup)、[协作协议](../../../../.coordination/README.md#protocol)、[本项目开工顺序](../../../../AGENTS.md)。

## 已知基线与问题

- 仓库：`/home/chen/AGC`；派单时 HEAD `49e099ccbead0cd222e06edce29acbf78b8d3c58`，分支 `main`，工作区明显 dirty。接单时必须重新核对 HEAD、分支、`git status --short --branch`、白名单文件状态和运行资源；不得 reset/clean/stash/checkout/提交/覆盖用户及 G1/G2/H0 改动。
- H0 已确定 `cruise_alt_m` 是相对 episode-origin NED 高度；N1 只在此语义下使用高度平面先验，不把它当绝对世界 ENU 高度。s02 的 H0 成功 truth 对照是 seed 0、full、GUI、`TRACKING_SUCCESS`。
- 现有 `scripts/vision/vision_detector.py` 只有 `none` backend，输出像素框；既有 `perception_path=vision` 校验尚未接管 `/agc/targets` 决策链，launch 注释明确称“本轮 vision 不接管决策”。不得把仅启动检测器、仅有图像/检测 topic 或旧参数标记称为视觉闭环。
- 现有 `air_perception` 是真值派生前端。vision 路径中决策目标必须来自真实图像检测与视觉几何，不得经 GT 补齐/筛选/置位/时间戳或坐标；真值仅可被评估工具离线读取。
- 相机候选机型为现有 PX4 `gz_x500_mono_cam`；桥已配置图像和 CameraInfo。仍须在本轮实际验证图像帧、CameraInfo、实际 optical frame 与 TF。只有话题名不算有图像。
- 相机/目标均位于移动 PX4 模型；目前 `px4_adapter` 发布 odometry 但不广播相机 TF。先从本机 PX4 同版本模型与图像/CameraInfo 运行数据核对可行 TF 路径。不得假设存在 `mono_cam_optical` 帧。无法从证据构造图像时间戳对应的 world←optical TF 时，停下报告最小阻塞/追加授权，不得用真值姿态或坐标冒充 TF。

## 目标与实施范围

在 `s02_linear_none_nominal_track` seed 0 的 full 场景中，打通真实相机帧 → 极简检测 → `Detection2D` → 基于图像时间戳的相机光学射线/TF → H0 允许的固定 episode 高度平面交点 → 带可区分 `vision` 来源的 `/agc/targets` 航迹 → `/agc/ground/goal` 实际由该视觉航迹驱动。truth/vision 必须由契约 `perception_path` 互斥选择；vision run 的任务决策图不得消费任何 GT 目标坐标。

极简识别器是链路桩而非算法成果：复用 `intruder_uav` 已有橙色高亮几何，限制为颜色阈值掩膜与有效像素外接框；显式 backend 名 `synthetic_color`，输出 score 仅是链路启发值。优先用现有 Python/NumPy/PIL 能力；不加 OpenCV、模型权重、训练/数据集流程、多目标关联、KF/DeepSORT、参数搜索或复杂检测逻辑。检测器与合成图单测按计划最多 0.5 工作日，达到后停并交回，不升级算法续命。

`Detection2D.header.stamp` 必须等于源图像 stamp；TF 使用同一 stamp。TF 暂不可用、时间跳变清空 buffer、CameraInfo 缺失/不匹配时，跳过该帧并计数/显式标注，绝不静默当成功或回退 truth。无模型/无图像/空画面须输出空检测并标明降级。高度平面先验只对 H0 标定的固定巡航高度场景有效，写明适用域。

## 白名单

Worker 仅可改以下文件/新增同目录内聚焦文件：

- 视觉实现与测试：`scripts/vision/vision_detector.py`、`scripts/vision/` 下本 N1 所需的新视觉投影/航迹适配实现；`scripts/tests/test_p1_4_vision_contract.py`、`scripts/tests/test_p1_4_vision_wiring.py` 及 `scripts/tests/` 下本 N1 聚焦新增测试。
- 视觉运行时/消息接线：`src/agc_task/launch/w6.launch.py`、`src/agc_task/launch/w6_composition.py`；`src/agc_task/config/scenarios.yaml`（仅必要的 N1 验收场景参数）、`src/agc_task/config/w6_base.yaml`（仅必要的视觉路径标识参数）；`src/agc_perception/CMakeLists.txt`、`src/agc_perception/package.xml`、`src/agc_perception/config/perception.yaml`、`src/agc_perception/launch/perception_bringup.launch.py`、`src/agc_perception/src/air_fusion.cpp` 及新增 `src/agc_perception/src/` 的 N1 目标适配器；必要时 `src/agc_sim/config/bridge.yaml` 仅限相机 topic/QoS 修正。
- 计划回填：仅 `docs/plan/N1-视觉驱动最小闭环.md`。
- 过程与证据：仅 `.coordination/task/20261102-002-n1-vision-minimal-loop/round-N/{request.md,report.md,evidence/}`；实验写入 `experiments/n1-vision-minimal-loop/<unique-run-id>/`，GUI 原帧按实际运行目录保留；临时文件 `/tmp/agc-n1-*`。
- T2 构建产物只写现有 `build/`、`install/`、`log/`，运行前核查占用；禁止 clean、清共享状态或删未知产物。

未列文件一律只读。特别禁止：`src/agc_msgs/`、9 消息定义/ABI、`docs/ROS2迁移交接文档.md`、任何 ADR、共享 `docs/plan/README.md` / `docs/plan/能力闭环路线.md` / `.coordination/CURRENT.md`、`.coordination/archive/`、H0/G1/G2/N2/N3 任务与实现、`src/agc_task/src/task_manager.cpp` 及任务终态/任务逻辑、地面/空中控制器与规划器、唯一执行口、安全阈值/顺序、地图/世界几何、PX4 模型与 `intruder_uav` 高亮几何、传感器能力参数（范围/FOV/噪声）、既有 truth 链语义。若需越白名单，停下报告，不自行扩权。

## 资源授权、独占与停止条件

- 总墙钟 **14,400 s**，从本派工时间 `2026-11-02T12:28:41+08:00` 起算，截止 `2026-11-02T16:28:41+08:00`；用尽即停并交回完成/未完成项。
- 静态/离线动作累计预算 **1,200 s**，每次 ≤30 s；按协议记账。
- `T1=0`，不得以 T1 名义启动任何进程/探针。
- `T2` 正向授权总量 **7,200 s**，只限本单必要构建与指定的 `full + GUI` 视觉整链验收；单次构建/runner/真实运行 ≤900 s。禁止 headless、lightweight、额外场景、PX4/GZ 以外的系统级配置更改。次数只记账；失败与重试均计入 T2。H0 已有 s02 seed-0 GUI truth 运行可作同 seed 对照，不必为对照重复占用 T2，除非审查证据证明确需重跑并仍在本预算内。
- 本任务独占构建、ROS/GZ/PX4 与 GUI 仿真资源。启动前核查既有进程/占用；有冲突立即阻塞交回，不等待轮询、不抢占、不终止他人进程、不清 `/dev/shm`。不得并行启动其它仿真/构建任务。
- `N=6` 为记录检查点，`K=4` 为无进展熔断；连续 4 轮无区分性新证据提交假设台账并停。根因锁定且同白名单/预算内时可继续修复重验。资源用尽、总时间到点、契约/白名单越界、必要 TF/相机证据不可得时立即停报；不得以“还没成功”判不可测。
- 仅在目标里程碑完成、阻塞、资源耗尽、契约风险时通知 Leader。完成后 report 状态置 `待审查`，阻塞置 `阻塞`；不自行验收/归档、不写 CURRENT、不派 N2/N3。

## 可判定验收

1. 运行时有真实新鲜相机 Image 帧及同相机 `CameraInfo`；记录帧率/分辨率/encoding/frame_id、相机内参、实际 TF frame 链与检查结果。不得只用 topic list。
2. `synthetic_color` 后端在合成目标图上输出有效 bbox；全黑/无目标负例输出空检测；输出源图像 stamp；无 OpenCV/模型权重/训练/数据集或隐式多目标算法。
3. 三维投影使用对应时间戳的光学系→world TF 和内参；复位/时间跳变、缺 CameraInfo/TF 均可显式跳帧计数；高度平面值取 H0 `cruise_alt_m` 语义、明确固定高度适用域；任何缺值不得以真值补齐。
4. ROS 运行图证明 vision 模式下目标决策 `/agc/targets` 唯一来源为视觉航迹适配器；`gt_adapter` / `air_fusion` 不得同时发布目标决策航迹。视觉节点订阅集合无 `/agc/gt/*`；run manifest/summary 明确 `perception_path=vision`、`synthetic_color` 与模型/后端标识。truth 模式默认既有行为保持不变。
5. 同 seed、同 s02 full+GUI：使用已验收 H0 truth 对照及本轮 vision 臂。实际 ground goal 输入/运行图证据证明 `/agc/ground/goal` 来自 `/agc/targets` 视觉航迹；vision 臂终态满足预期 `TRACKING_SUCCESS`，记录 detection recall/precision、3D error p50/p95、图像到航迹延迟与安全指标。真值只作离线评估。
6. 空检测/无目标负例不产生视觉航迹或视觉地面目标，不得因 GT 旁路成功；可用 full+GUI 负例运行或由等强的运行时接线证据与聚焦集成测试组成，报告须说明所用证据与终态。
7. 按契约保存关键 full+GUI 原始帧、manifest、summary、日志和运行图/节点 topic 证据；相关测试及必要 build 通过，全部失败/重试/资源消耗如实记录。未达项明确列出，不包装为通过。
8. 不改 9 消息 ABI、任务管理器/终态、唯一执行口、规划器、安全顺序/阈值、相机能力范围和现有 truth 默认路径；只对 H0 高度语义中的适用域做视觉地面投影。

## 交回

Worker 接单先核对当前基线与资源，创建本轮 `report.md` 写领取时间、执行者、子会话 ID、预算起点和 `执行中`。里程碑/阻塞/资源耗尽/契约风险时通知 Leader；末轮状态写 `待审查` 或 `阻塞`，附审查摘要、差异、命令退出码、证据路径、假设台账、T1/T2/墙钟账目与未执行项。Worker 不读 review、不改 CURRENT、不自行验收归档、不派发后续任务、不轮询或设置提醒。
