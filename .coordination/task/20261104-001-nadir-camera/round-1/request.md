<a id="request"></a>
# 机载俯视（正下视）相机 —— 批次派工单

- 任务 ID：`20261104-001-nadir-camera`；轮次：1；派发时间 `2026-11-04T18:10:00+08:00`（Asia/Shanghai）。
- 来源：用户 2026-11-04 指示「把 `docs/plan/无人机俯视相机.md` 完成」。本单为该 plan 的实施。
- 你是本链**唯一** Worker；后续轮次复用你会话，不重新创建。

## 一、目标（一句话）

给**己方无人机**装一台**朝正下方**的机载相机，在仿真里能真实出图并桥到 ROS，
供将来视觉测绘用；**默认行为逐字不变**，**不接**感知/任务链（识别仍靠真值 `gt_adapter`）。

## 二、不可越界的口径（先读，违反即停）

1. **识别仍靠真值**：`/agc/targets` 发布者仍是 `gt_adapter`，**不得**新增任何消费者、
   不得把图像接入任务链、不得创建视觉识别节点/参数（视觉定位路径已于 2026-11-04 退役，
   见 [路线分支治理 §5.2](../../../../docs/conventions/路线分支治理.md#current)）。
   相机是**独立取证/测绘能力**，与任务链无耦合。
2. **默认不变**：默认 `px4_sim_model:=gz_x500` 时，己方机**没有**相机，行为逐字不变。
   新能力必须**opt-in**。
3. **不改工具链**：`toolchain/PX4-Autopilot/` 是 pin 的外部依赖（`scripts/toolchain_pin_check.py`
   会核对 HEAD 与文件哈希）。**禁止**在其中新增/修改任何文件（尤其**禁止**新增 airframe
   文件 `ROMFS/.../airframes/`）。新增模型资产只能放本仓 `src/agc_sim/models/`。
4. **不改契约**：`docs/ROS2迁移交接文档.md` 一字不改；C1/C2/C6/C10 不动。
5. **不新增 launch 参数**：不新造 `xxx_model` / `xxx_camera` 之类的开关。
   机型选择复用**已有**的 `px4_sim_model`（[路线分支治理 §2.1](../../../../docs/conventions/路线分支治理.md#rule)
   明确「地图 / 模型文件选择」不是路线分支，选的是**资产**）。
6. **不做**：不推导视觉检测算法、不做障碍物建图、不引入第三方资产、不改飞行高度、
   不改任务场景。

## 三、真源与必读（按此顺序）

- 占位 plan（本单要结档删除）：[无人机俯视相机](../../../../docs/plan/无人机俯视相机.md#top-down-camera)
- 几何事实（**只作约束，不得当方案**）：[飞行高度分层 §7.1](../../../../docs/conventions/飞行高度分层与按地图定高.md#camera-split)
- 决策边界：[ADR-0009](../../../../docs/adr/0009-perception-truth-derived-and-vision-path.md#top)（(a2)(b) 真值识别）、
  [ADR-0007](../../../../docs/adr/0007-scene-geometry-single-source-and-layout.md#top)（几何单一真源）
- 同类实现（**先学后做**，必须逐条对照后再动手）：
  - 本仓 `src/agc_sim/models/intruder_uav/intruder_uav.sdf.xacro` 的 `controlled` 分支：
    `include merge="true"` + 独立 link/fixed joint 的注入范式（并读其注释里"四种写法实测"的坑）。
  - PX4 官方 `toolchain/PX4-Autopilot/Tools/simulation/gz/models/x500_mono_cam/model.sdf`
    与 `x500_depth/model.sdf`（相机通过 `include merge` + fixed joint 挂到 `base_link`）。
  - PX4 机型解析链：`ROMFS/px4fmu_common/init.d-posix/rcS`（`PX4_SYS_AUTOSTART` **优先于**
    `PX4_SIM_MODEL` 的 airframe 名字匹配）与 `ROMFS/px4fmu_common/init.d-posix/px4-rc.simulator`
    （`gz_bridge start -m "${PX4_SIM_MODEL#*gz_}"` → PX4 用**资源路径**找 `<name>/model.sdf`；
    实体名 = `<model_sim>_<instance>`，见 `GZBridge.cpp`）。
  - 相机桥接口径与**踩过的坑**：`src/agc_sim/config/bridge.yaml` 相机段注释、
    `experiments/p1-4/round-2/evidence/camera-ownership-finding.md`（"话题存在 ≠ 有帧"）、
    `experiments/p1-4/round-1/recon/10-recon.md`。
  - 工程规范：[目录与命名规范](../../../../docs/conventions/目录与命名规范.md#10-产物分类与生命周期)、
    [路线分支治理](../../../../docs/conventions/路线分支治理.md#rule)、[ADR-0006](../../../../docs/adr/0006-experiment-artifacts-and-evidence-discipline.md#top)（产物落点）。

## 四、基线

- 分支 `main`，HEAD `49e099c`。
- 工作区**本来就很脏**（592 项未提交改动，含 `docs/adr/*` 为未跟踪新文件）。
  **不得** reset / checkout / stash / clean；只在你自己的白名单内编辑，改动前先记文件哈希。
- 已确认环境：`DISPLAY=:0` 可用（xdpyinfo 通过）、GPU RTX 4060、gz sim 8.15.0、
  PX4 已构建（`toolchain/PX4-Autopilot/build/px4_sitl_default/bin/px4`）。
- **已知遗留**：`/tmp` 侧有 2 个 16:53 起的 `air_perception` / `map_adapter` 孤儿进程（pid 159340/159341），
  **不是你的**，**不得** kill，遇到端口/进程冲突按"阻塞"回报。

## 五、必须交付（按此顺序做）

### 1. 调研（先写结论再动手）

- 机型解析走 `PX4_SYS_AUTOSTART` 覆盖路线是否成立？**用只读证据**（源码行号）写清
  "为什么不需要改工具链"，并写出可判定失败点。
- 模型资源解析：`GZ_SIM_RESOURCE_PATH` 需要怎么给己方 PX4 进程加本仓 models 目录。
- 相机参数：**正下视 = 相对 `base_link` 的 pitch 到底该写 −90° 还是 +90°？**
  必须以 gz/sdf 的相机朝向约定 + 实测出图**证明**，不得凭直觉。给出
  `hfov / 分辨率 / clip / update_rate / <topic>` 的取值与理由。
- 几何：给相机在 `base_link` 上的安装位（参考 mono_cam 的 `.12 .03 .242`），
  并算出在 `yard`（己方 14 m）与 `minimal`（2.5 m）下的**地面足迹、中心 GSD、边缘 GSD**。
  **必须**说明这与 [§7.1](../../../../docs/conventions/飞行高度分层与按地图定高.md#camera-split) 的既有验算是否一致
  （若不一致，如实指出哪一条是错的）。

### 2. 实现

- 新模型资产 `src/agc_sim/models/agc_x500_nadir/`（`model.config` + `model.sdf`），
  `include merge="true"` PX4 `x500`，加一个**独立 link + fixed joint** 承载相机传感器
  （**不得**往 `merge` 里塞 link——会静默丢弃，见 `intruder_uav` 注释）。
  `model.sdf` 的 `<model name>` 必须是 `agc_x500_nadir`（实体名会变成 `agc_x500_nadir_0`）。
- 传感器 `<topic>` 用本仓自有命名，**不要**复用 PX4 的 `camera`
  （避免与将来 mono_cam 冲突；建议 `agc/air/nadir`，最终以你的实测为准）。
- 桥：`src/agc_sim/config/bridge.yaml` 增 `Image` + `CameraInfo` 两条（`SENSOR_DATA` QoS），
  ROS 侧命名建议 `/agc/air/nadir/image_raw` 与 `/agc/air/nadir/camera_info`。
  **必须**在注释里写清"无消费者、仅取证/测绘"，以及"话题存在 ≠ 有帧"的判据。
- 机型选择：复用 `px4_sim_model`，新增取值 `gz_agc_x500_nadir`；己方 PX4 进程环境需要
  把 `src/agc_sim/models`（安装后在 `install/agc_sim/share/agc_sim/models`）加入
  `GZ_SIM_RESOURCE_PATH`，并按调研结论注入 `PX4_SYS_AUTOSTART=4001`。
  未知机型仍由 PX4 拒启（**不要**在本仓另立白名单）。
- 若 `gz_x500_mono_cam` 已零消费者（自行核查全仓），可**同批退休**该取值；
  但**必须**留防复活断言（见第 4 项），并在 ADR 写明"删了什么、为什么"。
  若发现仍有消费者，**保留**并如实登记，不要强删。

### 3. 真实运行验证（T2，占独占资源，必须持锁）

- 每次真实运行必须
  `flock -w 1800 /home/chen/AGC/.coordination/locks/sim.lock -c "<命令>"`
  （另一条链也在用同一把锁；**拿不到锁就等，不要抢、不要 kill 别人的进程**）。
- 至少两次运行：
  1. **默认臂** `px4_sim_model:=gz_x500`：证明**没有**新相机帧（对照），且主场景仍达期望终态。
  2. **新臂** `px4_sim_model:=gz_agc_x500_nadir`：`/agc/air/nadir/image_raw` 有真实帧
     （`ros2 topic hz` ≥10 Hz 且累计 ≥30 帧）、`camera_info` 有内参、落盘 ≥1 张 PNG。
- **必须**证明"看到的是地面而不是天空"：用 PNG 目视 + 位姿/朝向几何核对（写出核对算式）。
- 运行记录写 `experiments/nadir-camera/<run-id>/`（ADR-0006 口径），日志只留路径。

### 4. 离线闸门（可执行判据，缺一不可）

新增 `scripts/tests/test_nadir_camera_contract.py`（纯静态、无进程）至少断言：

- 默认机型 `gz_x500` 的启动路径**不**包含任何相机模型（防"默认偷偷开相机"）；
- `agc_x500_nadir` 模型存在、恰好 1 个 `type="camera"` 传感器、pitch = −90°（容差 1°）、
  `<topic>` 与 bridge 条目**逐字一致**；
- 己方 PX4 进程注入 `PX4_SYS_AUTOSTART=4001`（机型解析不依赖改工具链）；
- `toolchain/PX4-Autopilot/ROMFS/px4fmu_common/init.d-posix/airframes/` 下**没有**新增 airframe
  （防复活"改工具链"的捷径）；
- 已退休的 `gz_x500_mono_cam`（若你判定退休）**不**出现在 launch 默认值与代码活跃路径（防复活）。

### 5. 文档归位（写完即删 plan）

- 新 ADR **`docs/adr/0030-nadir-camera-capability.md`**：Status / 背景 / 决策（含机型解析路线、
  相机姿态与参数、为什么 opt-in、为什么不接任务链）/ 不做什么 / Consequences（含 GSD 数字、
  与 §7.1 的关系、如何回滚）。
- 更新 `docs/conventions/飞行高度分层与按地图定高.md` §7.1：**保留几何事实**，
  把"没有机载俯视"改为"已有 opt-in 正下视相机（ADR-0030），仍不接任务链"。
- 更新根 `README.md` 的「已知边界」：写入"俯视相机仅为取证/测绘，**无消费者**，
  识别仍靠真值"。
- 删除 `docs/plan/无人机俯视相机.md`，并确保**无断链**（`tests/docs_link_check.py` 通过）。
- ADR 索引重生成**必须持文档锁**：
  `flock -w 300 /home/chen/AGC/.coordination/locks/docs.lock -c "python3 scripts/adr_index.py"`。

## 六、白名单（只写这些；其余只读）

```
src/agc_sim/models/agc_x500_nadir/**            # 新建
src/agc_sim/config/bridge.yaml                  # 仅相机条目
src/agc_sim/launch/world_bringup.launch.py      # 仅资源路径（如确需）
src/agc_air/launch/air_bringup.launch.py        # 仅机型/资源路径/描述
src/agc_task/launch/w6.launch.py                # 仅己方 PX4 进程环境 + px4_sim_model 描述
scripts/tests/test_nadir_camera_contract.py     # 新建
docs/adr/0030-*.md                              # 新建
docs/adr/README.md                              # 仅由 adr_index.py 生成
docs/conventions/飞行高度分层与按地图定高.md      # 仅 §7.1 与相关引用
docs/conventions/路线分支治理.md                 # 仅 5.2/5.3 的 px4_sim_model 行（如退休）
README.md                                       # 仅「已知边界」
docs/plan/无人机俯视相机.md                      # 删除
experiments/nadir-camera/**                     # 新建
```

**禁区**：`toolchain/**`、`docs/ROS2迁移交接文档.md`、`src/agc_task/config/**`、
`src/agc_air/config/**`、`src/agc_rl/**`、`src/agc_sim/config/{car,target,world_geometry*}.yaml`、
`.coordination/CURRENT.md`、另一条链（`20261104-002-target-motion-speed`）的任何文件、
`docs/plan/{目标无人机运动规则,速度调研与运行节奏优化}.md`。

## 七、资源授权

- **T0 零运行**：默认自主。
- **T1 微观测**：总墙钟 **1200 s**，单次 ≤30 s、进程 ≤2、独占 `/tmp/20261104-001-*`；
  次数只记账。
- **T2 真实实验**（仿真 / 构建 / GUI / headless）：总墙钟 **3600 s**，次数只记账；
  **未派发不启动**；每次真实进程都计时入账。构建用 `colcon build --symlink-install
  --packages-select agc_sim`（必要时 `agc_air`），构建同样计入 T2。
- GUI 与 headless 均可；相机帧**不要求** GUI（但若 headless 无帧，改用 GUI 并如实记录）。

## 八、验收判据（可判定，缺一不算完成）

| # | 判据 | 证据 |
|---|---|---|
| A1 | 默认 `gz_x500` 下无新相机帧，主场景终态符合预期（与基线一致） | run 目录 + `summary.json` terminal_state |
| A2 | 新臂 `gz_agc_x500_nadir` 起得来：己方机 ARM + 起飞 + 飞行，无 Preflight Fail | launch.log 摘要 |
| A3 | `/agc/air/nadir/image_raw` 真实帧 ≥30 张、≥10 Hz；`camera_info` 内参存在 | `ros2 topic hz/info` 输出原文 + PNG |
| A4 | 图像内容是**地面**（不是天空）且中心射线符合正下视几何 | PNG 目视结论 + 几何核对算式 |
| A5 | 新增离线闸门测试通过；`tests/run_smoke.py` 的 offline / docs / index 组全绿 | pytest 输出 + run_smoke 摘要 |
| A6 | ADR-0030 落盘、索引 `--check` 通过；§7.1 / README 已知边界已更新；plan 文件已删且 `docs_link_check.py` PASS | 命令输出 |
| A7 | 无任务链耦合：`/agc/targets` 发布者仍仅 `gt_adapter`，无新订阅者 | `ros2 node info` / 静态 grep |
| A8 | 未触碰 `toolchain/**`、未改契约、未新增 launch 参数 | `git status --short` 白名单比对 |

## 九、预登记停止条件（强制）

1. **资源/总时间**：T2 总墙钟 **3600 s**、T1 **1200 s** 用尽即停，交回已完成项与未完成项；
2. **无进展**：连续 **4 轮**（K=4）无区分性新证据即熔断并提交假设台账；
3. **根因已锁定时**，允许在同一白名单、同一资源总量内**修完并验完**，不因轮数或建议次数停工；
4. **N=6**：累计第 6 轮写一次"本轮小结 + 资源账目"，**不停止**；
5. 阻塞（需越白名单/契约、缺必要来源、并行资源冲突）→ 立即停并 `send_message` 通知 Leader。

## 十、回报要求

批次末（或四类触发事件）写本轮 `report.md`，**开头 ≤30 行审查摘要**：结论、差异清单、
证据链接、未决项。另须含：假设台账、下一轮建议、累计资源账目（T1/T2 次数与总时长、墙钟）。
`CURRENT.md` 由 Leader 独占写，你**不写**。
