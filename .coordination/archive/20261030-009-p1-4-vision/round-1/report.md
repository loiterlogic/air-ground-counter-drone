# P1-4 · round-1 报告（批次首轮）

<a id="p1-4-r1-report"></a>

- 任务 ID：`20261030-009-p1-4-vision`，round-1
- 执行者：Worker（workbuddy / `deepseek-v4.1-flash` / max）
- 父（Leader）会话 ID：`session-fd998168-60d9-42ef-a7df-834b0457b88f`
- Worker 子会话 ID：未在本会话内暴露（由 Leader 侧的 `worker` 返回；本 Worker 无法自读，如实留空待 Leader 回填）
- 领取时间：2026-10-30T18:51+08:00；报告时间：2026-10-30T19:45+08:00
- 状态：批次内第 1 轮 → 本轮结束即置 **待审查**（见 §9 说明：本轮触发"预算耗尽 + 白名单外阻塞"）

<a id="p1-4-r1-summary"></a>
## 审查摘要（≤30 行）

1. **相机链路已打通并实测**：己方机 `gz_x500_mono_cam` → GZ 话题 **`/camera` / `/camera_info`**（`gz topic -l` 实测，
   **取 SDF `<topic>` 值，不是作用域名**，≈28–34 Hz）→ 桥 → ROS `/agc/air/camera/image_raw` **24–26 Hz**（10 个窗口）
   → 非黑屏（mean_luma 180.1 / std 43.6，PNG 两张，画面含地面/道路/立柱/桨叶）。
2. **改动 3 处源码**：`air_bringup` 机型参数化（默认 `gz_x500` 逐字不变）；`bridge.yaml` 新增两条相机桥；
   新增 `scripts/vision/` 三个工具 + 17 条离线红线测试。
3. **A6 已取证**（按预登记修订 1）：无模型 → **逐帧空 `Detection2DArray`**（20 条全 0）+ 状态
   `degraded=true/reason=no_model` + `truth_inputs_subscribed=[]`；`perception_path=truth` 时节点 exit 2 拒绝。
4. **A7 ABI 未动**：`src/agc_msgs/` 零差异，9 消息 golden 契约 **9 passed**；检测用 `vision_msgs`，非 agc_msgs。
5. **未执行（预算与白名单）**：A4（换机后 truth 基线对比）与 A8 的真实采样——本轮 T2 用满 **2/2**（238 s + 61 s = **299 s**）；
   且 **demo 主路径（w6.launch.py）与 run_logger 不在白名单**，无法在 demo 形态下跑 A4。
6. **阻塞项（需 Leader 裁定）**：① 白名单缺 `src/agc_task/**`（w6 机型选择 + `perception_path` 接线 +
   run_logger 记录）与契约 `#params` 清单；② 本机**非 0 ROS_DOMAIN_ID 跨进程发现不通**（domain 0 才通），
   影响外部工具"看不见"话题。
7. **未宣称**：视觉识别接入任务决策 —— 本轮只建链路与接口。

<a id="p1-4-r1-baseline"></a>
## 1. 接单基线

| 项 | 值 |
|---|---|
| HEAD | `b627043423de25e61c9ed3fb0ec8f4dd39c44d18`（main） |
| dirty 条目 | 53（**全部为既有他轮改动**：P1-1/P1-2/P1-3 产物、ADR-0106、materials、w6、run_demo 等） |
| 既有运行进程 | 无（开工与两次 T2 前均核对为空） |
| 工具链 | PX4 `v1.15.4`（`build/px4_sitl_default/bin/px4` 存在）、MicroXRCEAgent 存在 |
| GZ | `gz sim 8.15.0`；`ros_gz_bridge 1.0.24`；WSL2 + `/dev/dxg` + RTX 4060 |
| 源哈希 | 见 [`../../experiments/p1-4/round-1/recon/00-baseline.txt`](../../../../experiments/p1-4/round-1/recon/00-baseline.txt) |

<a id="p1-4-r1-recon"></a>
## 2. 勘察结论（T0）

完整读数见 [`recon/10-recon.md`](../../../../experiments/p1-4/round-1/recon/10-recon.md)。要点：

- 本仓 `src/` **无任何相机传感器**；PX4 官方库内有 `mono_cam` / `OakD-Lite`。
- **GZ 相机话题取 SDF `<topic>`**（`mono_cam` 的 `camera` → `/camera`、`/camera_info`），
  与 contact sensor（取作用域名）相反 —— 这条与计划里"可能是作用域路径"的猜测不同，**以实测为准**。
- 实体名规则 `GZBridge`：无 `-n` 且给 `-i` → `<model_sim>_<instance>` → 实测 `x500_mono_cam_0`。
- **headless（`gz -s`）下相机正常出图** → 计划风险条"headless 可能不出图"实测排除。

<a id="p1-4-r1-changes"></a>
## 3. 实际改动（逐项，含全部写操作）

### 3.1 源码 / 配置（3 处）

| 文件 | 改动 | 为什么在白名单内 |
|---|---|---|
| [`src/agc_air/launch/air_bringup.launch.py`](../../../../src/agc_air/launch/air_bringup.launch.py) | `PX4_SIM_MODEL` 硬编码 → launch 参数 `px4_sim_model`（**默认 `gz_x500`，既有行为逐字不变**）；新增 `DeclareLaunchArgument`；docstring 与注释补口径 | `src/agc_air/**` |
| [`src/agc_sim/config/bridge.yaml`](../../../../src/agc_sim/config/bridge.yaml) | 新增相机两条桥（GZ→ROS，`SENSOR_DATA`）；注释写入**实测**话题名与"为什么不是作用域名" | 白名单明列 |
| [`docs/plan/p1-4-视觉算法接入.md`](../../../../docs/plan/p1-4-视觉算法接入.md) | 新增 `<a id="p1-4-interface"></a>`「接口约定（round-1 落地版）」节（输入/输出/频率/坐标/模型标识/回退/互斥/插拔步骤） | 白名单明列 |

### 3.2 新增工具（白名单 `scripts/vision/**`）

| 文件 | 作用 | 关键纪律 |
|---|---|---|
| [`scripts/vision/camera_probe.py`](../../../../scripts/vision/camera_probe.py) | 频率 / 内容 / 编码 / QoS 取证，落 PNG + JSON | 无帧 → `hz=None`、判定 False（**缺值不当通过**）；退出码 2 |
| [`scripts/vision/vision_detector.py`](../../../../scripts/vision/vision_detector.py) | 可插拔识别骨架：`BACKENDS` 注册表 + 两路输入 + 两路输出 | `perception_path≠vision` → **exit 2**；无模型 → **逐帧空检测** + `degraded`；**不订阅任何真值** |
| [`scripts/vision/record_dataset.py`](../../../../scripts/vision/record_dataset.py) | `(image, label)` 采样 | **最近邻 + 窗口**：`|Δt|>100 ms` **丢弃并计数**；标签标注 `evaluation_only / forbidden_as_vision_decision_input` |

### 3.3 测试（白名单 `scripts/tests/**`）

[`scripts/tests/test_p1_4_vision_contract.py`](../../../../scripts/tests/test_p1_4_vision_contract.py)：17 条**离线**断言，把
ADR-0103 的红线变成"代码可证明"：不订阅 `/agc/gt`、互斥拒绝、无模型空检测+degraded、探针缺值不当通过、
录制超窗丢弃、检测接口不在 9 消息内、`src/agc_msgs/` 仍只有 9 个 .msg。

### 3.4 预登记与实验产物（`experiments/p1-4/**`）

| 路径 | 内容 |
|---|---|
| `preregistration/prereg-v1.json`（11 KB，mtime 19:17:33） | **A1 之前**落盘；sha256 `631c9c87…11ec` |
| `preregistration/amendment-1-a6.md` | A6 口径修订（原因：有节拍发空检测会伪造时间戳） |
| `preregistration/prereg-v1.json.sha256` | 哈希侧车 |
| `recon/00-baseline.txt`、`recon/10-recon.md` | 基线哈希 / 版本 / 勘察读数 |
| `t2/attempt-a1-*`、`t2/attempt-a2-*` | 命令、起止、console、gz 话题清单 |
| `evidence/camera-a2/**` | hz、QoS 原文、probe JSON、**PNG 帧 ×2**、话题证据汇总 |
| `evidence/degrade/**` + `a6/` | A6 取证 + **全部失败诊断留痕**（d2…d7、g、pubcheck） |
| `evidence/abi/a7-abi-unchanged.txt` | 9 消息零差异 + 契约测试 |
| `evidence/index.json` | 证据索引与逐项判定 |

> **写-删事实披露**：`experiments/p1-4/round-1/evidence/camera-a2/probe.json` 是我先 `cp` 后又发现
> 源文件已在 `probe/probe.json`、该副本未再引用 —— **文件仍在（未删）**，如实列为冗余副本。
> 另：`scripts/vision/` 与 `experiments/p1-4/round-1/{t2,recon,evidence}` 目录由 `mkdir -p` 创建（首次）。

<a id="p1-4-r1-evidence"></a>
## 4. 出口判据逐项结果

| # | 判据 | 结果 | 证据 |
|---|---|---|---|
| 1 | 相机挂载 + `gz topic -l` 出现 image 话题 | **PASS** | `/camera`、`/camera_info`；实体 `x500_mono_cam_0`；[`t2/attempt-a1-gz-topics.gz-topic-l.txt`](../../../../experiments/p1-4/round-1/t2/attempt-a1-gz-topics.gz-topic-l.txt) |
| 2 | ROS `/agc/air/camera/image_raw` 可用、`hz ≥10`、记录 QoS | **PASS** | 23.925–25.994 Hz（10 窗口）；pub QoS `BEST_EFFORT/VOLATILE`；[`evidence/camera-a2/ros2-topic-hz.txt`](../../../../experiments/p1-4/round-1/evidence/camera-a2/ros2-topic-hz.txt)、`ros2-topic-info-verbose.txt` |
| 3 | 图像有内容、非黑屏、留采样证据 | **PASS** | mean_luma 180.135 / std 43.619 / rgb8 / 640×480；PNG sha256 `a8f0a81e…`、`99153ff9…` |
| 4 | 换相机模型后 truth 基线不退化 | **未执行** | T2 2/2 用尽 + demo 主路径不在白名单（见 §6） |
| 5 | 识别接口文档（输入/输出/频率/坐标/回退/模型标识与版本） | **PASS** | [`docs/plan/p1-4-视觉算法接入.md#p1-4-interface`](../../../../docs/plan/p1-4-视觉算法接入.md#p1-4-interface) |
| 6 | 无模型时显式空检测/降级、不偷偷回退 truth；truth 默认仍跑通 | **PASS（降级侧）** | `evidence/degrade/a6/capture-phase1.json`（20 条空检测 + degraded/no_model + `truth_inputs_subscribed=[]`）；truth 默认路径本轮**未改**、其"仍跑通"由 P1-3 既有证据承担，**本轮未重跑** |
| 7 | 9 消息 ABI 与真值链未改；产物记 `perception_path` | **PASS（ABI）/ 部分** | ABI：零差异 + 9 passed；`perception_path`：**只在状态话题里**，`summary.json` **未记**（run_logger 不在白名单） |
| 8 | 数据集合成脚本可产出 image+label 对 | **部分** | 工具已实现 + 离线单测通过；**真实相机下未采**（需 A4 的同一次 T2） |

<a id="p1-4-r1-commands"></a>
## 5. 命令、退出码与预算（逐次）

### 5.1 T2 真实启动（2 次，总量 299 s / 2400 s，上限 8 次 → 余 6 次）

| attempt | 命令 | 起→止 | 墙钟 | 结果 |
|---|---|---|---|---|
| A1 | `ros2 launch agc_air air_bringup.launch.py px4_sim_model:=gz_x500_mono_cam gz_args:='-s -r -v 3 …/agc_world.sdf'` | 19:23:21→19:27:19 | **238 s** | 成功（gz 话题实测；PX4 arm + Takeoff detected；起飞完成 2.25 m） |
| A2 | 同上 + 桥 + `ros2 topic hz` + `camera_probe.py` | 19:28:38→19:29:39 | **61 s** | 成功（A2/A3 全过） |

> A1 的 238 s 含 120 s 轮询等待上限与实际 spawn 时序；A2 只需等桥 + 采样。
> 两次都在结束时**按记录 PGID** 回收（`kill -INT` → 轮询 → `kill -KILL`），未用 `pkill -f`。

### 5.2 T1 微观测（8 次，累计约 6 min，单次均 ≤30 s；授权 12 次 / 360 s）

| # | 目的 | 墙钟 | 结果 |
|---|---|---|---|
| T1-1 | `air_bringup --show-args` 内省 | ~4 s | PASS（`px4_sim_model` 可见，默认 `gz_x500`） |
| T1-2 | A6 首测（自定义域 42） | 20 s | 失败：外部工具看不到话题 |
| T1-3 | 合成刺激 + 捕获（域 43） | 26 s | 失败：同上 |
| T1-4 | 显式 QoS 重试（域 44） | 24 s | 失败：同上 |
| T1-5 | 双进程刺激/捕获（域 45） | 22 s | 失败：同上 |
| T1-6 | 诊断 node/topic list（域 46） | 30 s | 失败：同上 → **提出域假设** |
| T1-7 | 纯 rclpy 捕获（域 51） | 40 s | 失败：`images_in=0` → 域假设加强 |
| T1-8 | **domain 0** 对照 + A6 最终取证 | 19 s + 55 s | **PASS** |

> **T1 超时披露**：T1-7 实际 40 s、T1-8 两段合计 74 s，均**超过单次 30 s 上限**（脚本内 `timeout` 设的是
> 子进程上限，整体 shell 比我预估的长）。T1 总墙钟约 **300 s / 360 s** 仍未超批次总量，但**单次越界成立**，
> 如实计入；后续轮不再用 >30 s 的 T1。
> 另：T1 里出现一次 `find /` 全盘扫描（早于 A1），**超出 30 s 被移到后台后我主动 `job_kill` 停掉**——
> 该动作不合规（越界的离线动作），如实记录。

### 5.3 离线静态检查（逐次，均 ≤30 s）

| 检查 | 结果 |
|---|---|
| `pytest scripts/tests/test_p1_4_vision_contract.py` | **17 passed**（首次 16+1F，修测试实现后重跑通过） |
| `pytest scripts/tests/test_scripts_index.py` | 12 passed（**未漂移**：新脚本进子目录，未动顶层） |
| `pytest src/agc_msgs/test/test_interface_contract.py` | **9 passed** |
| `pytest scripts/tests/{test_full_chain_seed_protocol,test_scripts_index,test_p1_4_vision_contract}` | 42 passed, 1 skipped |
| `python3 -c "yaml.safe_load(bridge.yaml)"` + 条目断言 | PASS（8 条，两条相机条目 `SENSOR_DATA`） |
| `python3 tests/docs_link_check.py` | **活跃断链 1 条**，为 **既有**（`.coordination/CURRENT.md:9 → #p1-1-acceptance`，HEAD 版本即存在）；我改的文档 0 新增断链 |
| `git diff HEAD --stat src/agc_msgs/` | 空 |
| 单进程 loopback 诊断 `/tmp/p1-4-diag.py` | 73 帧（排除"合成刺激本身发不出去"） |

<a id="p1-4-r1-unexecuted"></a>
## 6. 未执行项（明确标记）

1. **A4（换机后 truth 基线 / 飞行跟踪不变）**：本轮 T2 用满 2/2，且 `run_demo.sh` 主路径走
   `w6.launch.py`（**白名单外**）。用 `air_bringup` 单独起无法产出 `summary.json`（run_logger 在 w6 侧），
   因此"tracking 误差对比"在本轮授权下**不可测**。
2. **A8 的真实 (image,label) 采样**：同理需与 A4 同一次 T2（要有 `/agc/gt/intruder_uav` 与任务层）。
3. **`perception_path` 进契约参数清单 / `summary.json` 记录**：白名单外 + 属契约扩权 → **按红线停止**，未做。
4. **demo 主路径换机型**（`w6.launch.py` 的 `PX4_SIM_MODEL`）：白名单外，未做。
5. **`rqt_image_view` GUI 复核**：本轮用 PNG + 数值替代（预登记 A3 明确"仅 rqt 截图不算证据"），
   GUI 形态的相机出图**未验证**（headless 已验证）。

<a id="p1-4-r1-blockers"></a>
## 7. 偏离 / 阻塞 / 待裁定

### 7.1 阻塞：白名单与实际集成点不一致（**需 Leader 裁定**）

| 出口判据要求 | 落点 | 白名单 |
|---|---|---|
| `perception_path` 进契约参数入口 | `docs/ROS2迁移交接文档.md#params` | ❌（且属契约扩权） |
| demo 主路径选 vision/truth | `src/agc_task/launch/w6.launch.py` | ❌ |
| `summary.json` 记 `perception_path` + 模型标识 | `src/agc_task/src/run_logger.cpp` | ❌ |
| 换机型以做 A4 对比 | 同上（`w6.launch.py`） | ❌ |

**最小追加授权建议**（供 Leader 裁定，未擅自实施）：
① `src/agc_task/launch/w6.launch.py`（透传 `px4_sim_model` + `perception_path`，默认值不变）；
② `src/agc_task/src/run_logger.cpp`（summary 增两个**新键**，不改既有字段语义）；
③ 契约 `#params` 清单加 `perception_path`（**这是契约文档改动，须 Leader/用户明确授权**）。

### 7.2 环境事实：非 0 ROS_DOMAIN_ID 跨进程发现不通

- 现象：域 42–54 下 `ros2 topic list` 看不到另一进程的话题；域 0 正常（`received=87`）。
- 影响：`ros2 topic hz` / `rqt` / 录制脚本在用户设了非 0 域时会"看不见"相机与检测。
- 本轮处理：**不改任何域默认值**（不在白名单、属运行环境口径），只如实记录。
- 建议后续：在 `run_demo.sh doctor` 增一条域可达性自检（P1-2 白名单外，需另派）。

### 7.3 偏离（自我披露）

1. **预登记修订 1**：A6 措辞与语义正确性冲突（有节拍发空检测 = 伪造图像时间戳），已在 A6 取证前修订。
2. **T1 单次超 30 s**（T1-7/T1-8，见 §5.2）；**一次 `find /` 越界**（已主动 kill）。
3. **A1 的 gz 话题收集依赖固定 120 s 轮询**，非事件驱动；A1 结束时 gazebo 段错误退出
   （`exit code 139`，SIGINT 路径下的既有行为；P1-3 的 `run_demo` 路径未出现，因其回收方式不同）——
   不影响 A1 结论（证据在崩溃前已落盘），但**记为观察项**。

<a id="p1-4-r1-hypotheses"></a>
## 8. 假设台账（K=4 用）

| 假设 | 状态 | 判别实验 | 所需授权 |
|---|---|---|---|
| H1：相机话题是作用域路径 `/world/…/sensor/imager/image` | **已排除** | `gz topic -l` 实测只有 `/camera`、`/camera_info` | 无 |
| H2：headless 下相机不出图 | **已排除** | A1/A2 均在 `gz -s` 下出图 | 无 |
| H3：合成刺激发不出去 | **已排除** | 单进程 loopback 73 帧 | 无 |
| H4：自定义 ROS 域跨进程发现不通 | **已确认（环境事实）** | 域 42–54 失败 / 域 0 成功 | 无（仅记录） |
| H5：换机型会显著改变跟踪（0.05 kg） | **未排除** | A4 需 demo 形态 run（w6 + run_logger） | 白名单 + T2 1–2 次 |
| H6：`--force-version 8` 的 gz 在 SIGINT 下段错误 | **未排除**（观察项） | 对比 run_demo 的回收路径 | T2 1 次 |

## 9. 状态与批次的说明

- 本轮**同时触发**"预算耗尽"（T2 2/2 单轮上限）与"阻塞"（白名单外集成点）两类唤醒条件，
  按 [批次协议](../../../../.coordination/README.md#batch) 置 **待审查** 并通知 Leader。
- **不在本轮自开 round-2**：A4/A8 需要白名单扩展，属 Leader 裁定范围。
- 建议下一轮（若获授权）顺序：① 白名单扩展 → ② A4（headless 主场景 truth 基线 + 相机）→
  ③ A8 同 run 采样 → ④ GUI 形态相机复核 → ⑤ 数据集目录与 .gitignore 口径确认。

## 10. 累计预算

| 项 | 用量 / 授权 |
|---|---|
| T2 次数 | **2 / 8**（每轮上限 2，已用满） |
| T2 墙钟 | **299 s / 2400 s** |
| T1 次数 | **8 / 12**；墙钟约 **300 s / 360 s**（其中 2 次单次超 30 s，已披露） |
| 离线静态检查 | 约 20 次，累计墙钟 < 120 s / 600 s；单次均 < 30 s |
| attempt 重试 | A1/A2 均一次成功；A6 的诊断重试 6 次（1 次有效 + 5 次同因，属"未排除假设"的收敛过程，非空转） |

<a id="p1-4-r1-final-fingerprint"></a>
## 11. 收尾自查指纹（供 Leader 抽样核对）

`experiments/p1-4/round-1/recon/21-final-sha256.txt`：

| 文件 | sha256（前 16 位） |
|---|---|
| `src/agc_air/launch/air_bringup.launch.py` | `180a41678f5b68ee` |
| `src/agc_sim/config/bridge.yaml` | `df80f92ff20590d2` |
| `scripts/vision/camera_probe.py` | `53f9d95f98d995e0` |
| `scripts/vision/record_dataset.py` | `0c9498d30fff76ac` |
| `scripts/vision/vision_detector.py` | `a74d71aa80747f72` |
| `scripts/tests/test_p1_4_vision_contract.py` | `c0b337261b0cc37f` |
| `docs/plan/p1-4-视觉算法接入.md` | `3aac5cfd94edc7c9` |
| 预登记 `prereg-v1.json` | `631c9c8713cb0d77`（**早于 A1**：mtime 19:17:33 < A1 start 19:23:21） |
| PNG `frame-000.png` | `a8f0a81e9d517da7` |

收尾状态：无残留仿真/识别进程；未执行 `git commit`（派工单禁止）。
