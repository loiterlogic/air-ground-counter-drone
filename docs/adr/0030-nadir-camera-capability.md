<a id="top"></a>
# ADR-0030：机载正下视（nadir）相机能力

- **Status**：accepted（2026-11-04）
- **来源**：用户 2026-11-04 指示「把 `docs/plan/无人机俯视相机.md` 完成」。本 ADR 是该 plan 的结档结论。
- **相关**：[ADR-0009](0009-perception-truth-derived-and-vision-path.md#top)（真值识别 / 视觉路径退役）、
  [ADR-0007](0007-scene-geometry-single-source-and-layout.md#top)（几何单一真源）、
  [路线分支治理](../conventions/路线分支治理.md#rule)（"地图 / 模型文件选择"不是路线分支）、
  [飞行高度分层 ](../conventions/飞行高度分层与按地图定高.md#camera-split)（GSD 验算）。

## 背景

`gz_x500`（默认己方机型）**不带相机**；PX4 官方可选的 `gz_x500_mono_cam` 挂的是**前视**单目相机，
不是俯视。项目此前**没有任何机载俯视相机**，`docs/plan/无人机俯视相机.md` 一直是"未立项占位"。

2026-11-04 用户裁定「**没有双相机分工，识别靠真值**」—— 识别路径**不变**（`gt_adapter`），
但"将来做视觉测绘需要一台朝下的相机"这个能力缺口仍然存在。本 ADR 只补**能力**，不动识别路径。

## 决策

### 1. 能力是 **opt-in**，默认行为逐字不变

新增机型取值 `gz_agc_x500_nadir`（复用**已有** launch 参数 `px4_sim_model`，**不新增 launch 参数**）。
默认 `gz_x500` 时：不加相机、不注入任何新环境变量、rcS 走原路径 —— 与改动前完全一致。

> 为什么复用 `px4_sim_model` 而不是新造 `nadir_camera:=true`：机型/模型文件选择属于**资产选择**，
> [路线分支治理](../conventions/路线分支治理.md#rule) 明确它不是路线分支；而"同一功能两套实现由开关选择"
> 才是路线分支。`scripts/tests/test_branch_ledger.py` 的注释也把 `gz_x500_mono_cam` 之类列为
> "文件/模型选择，不是路线分支"，本条沿用同一判定。

### 2. 机型解析**不改工具链**（`PX4_SYS_AUTOSTART` 覆盖路线）

`toolchain/PX4-Autopilot/` 是 pin 的外部依赖（`scripts/toolchain_pin_check.py` 校验 HEAD 与文件哈希），
**禁止**在其中新增 airframe。本能力走两条**既有**机制，工具链零改动：

| 环节 | 机制 | 证据（行号为当前 pin） |
|---|---|---|
| 选 airframe | 注入 `PX4_SYS_AUTOSTART=4001` | `ROMFS/px4fmu_common/init.d-posix/rcS:41-44` 该分支**优先于**按 `PX4_SIM_MODEL` 文件名反查（`:52-63`）；`:42` 打印 `env SYS_AUTOSTART: 4001` |
| 实际生效 | rcS 仍 source 官方 `4001_gz_x500` | `rcS:136` `param set SYS_AUTOSTART` → `rcS:208-213` 按 `SYS_AUTOSTART_*` 选文件 ⇒ 旋翼/参数集与默认臂**完全相同** |
| spawn 名 | `gz_bridge start -m "${PX4_SIM_MODEL#*gz_}"` | `ROMFS/px4fmu_common/init.d-posix/px4-rc.simulator:117` ⇒ `-m agc_x500_nadir` |
| 找模型文件 | 相对路径 `agc_x500_nadir/model.sdf`，由 **gz 服务器**按 `GZ_SIM_RESOURCE_PATH` 解析 | `src/modules/simulation/gz_bridge/GZBridge.cpp:73-77`；`world_bringup.launch.py` 已追加 `install/agc_sim/share/agc_sim/models` |
| 实体名 | 无 `-n` 且有 `-i` ⇒ `<model_sim>_<instance>` = `agc_x500_nadir_0` | `GZBridge.cpp:313-320`；运行期日志 `model name: agc_x500_nadir_0, simulation model: agc_x500_nadir` |

**未知机型仍由 PX4 拒启**：`rcS:52-63` 查不到即 `ERROR [init] Unknown model ...` + `exit 1`。
本仓**不另立白名单**（避免第二份真源）。

### 3. 相机姿态：SDF `pitch` = **+1.5708 rad**

"90°" 是**下俯量**；SDF `pitch` **字段值**是 **+1.5708**。推导（不靠直觉）：

- gz 相机光学轴 = 传感器系 **+X**（PX4 官方 `mono_cam` / `OakD-Lite` 的 `<pose>` 全为 `0 0 0 0 0 0`，
  而二者被用作**前视**相机 ⇒ 零位 = 前视 = 机体 +X）；
- SDF 纯 pitch 旋转 `R_y(θ)·x̂ = (cosθ, 0, −sinθ)`：
  θ = **+90°** → `(0,0,−1)` = **正下方**；θ = −90° → `(0,0,+1)` = 正上方（**拍天空**）。

> **纠错记录**：`docs/plan/无人机俯视相机.md` 与 曾写"加 −90° 俯角"，那是把**下俯量**当成了
> **字段值**。二者不是同一件事：下俯 90° ⇔ pitch = +1.5708。本 ADR 明确此区分，防止后人照字面改符号。
>
> 离线闸门**双断言**钉死这一点（`scripts/tests/test_nadir_camera_contract.py`）：
> ① 数值 `pitch == +1.5708`（容差 1e-3）；② 把 pitch 代进旋转矩阵，断言**有效光轴 z ≈ −1**（容差 1e-2）。
> 只钉数值挡不住"约定变了"，只钉语义挡不住"符号写反但按反的约定解读"。

### 4. 相机参数与安装位

| 项 | 取值 | 理由 |
|---|---|---|
| 安装位（相对 `base_link`） | `0 0 0.242` | x/y 取 0 使**足迹居中于机体**（mono_cam 的 `.12 .03` 是为前视避让机头）；z 沿用 mono_cam 的 `0.242 m` 高度面 |
| `horizontal_fov` | `1.745` rad（≈100°） | 与 的 GSD 验算**同一口径**（HFOV 100°、640×480）；换视场会让既有验算失效 |
| 分辨率 | `640×480` | 与 mono_cam 同档；`f = (640/2)/tan(50°) = 268.6 px`（实测内参 `fx=fy=268.60`，与推导一致） |
| `clip` | near `0.1` / far `3000` | near 取 mono_cam 同值（14 m 高度下 0.1 m 足够近）；far 覆盖地平线以远，正下视实际用不到 |
| `update_rate` | `30` | 与 mono_cam 同档；实测桥侧中位 **25.7 Hz**（渲染受限，仍 ≥10 Hz 判据） |
| `<topic>` | `agc/air/nadir` | **不复用** PX4 的 `camera`（避免与将来 mono_cam 冲突） |
| `<camera_info_topic>` | `agc/air/nadir/camera_info` | **必须显式写**（见下） |

**`camera_info` 必须显式命名**：gz-sensors 默认按 `<topic>_info` 派生 ⇒ 会得到 `/agc/air/nadir_info`，
与桥期望的 `/agc/air/nadir/camera_info` **不符且静默**（话题照样出现，但桥订阅的是另一条 ⇒ 永远无内参）。
sdformat14 的该元素在 **`<camera>` 下**（不是 `<sensor>` 下），写错位置会被当作"未定义元素"复制保留而不生效。

### 5. 挂载范式：独立 link + fixed joint（不往 `include merge` 里塞 link）

照 PX4 官方 `x500_mono_cam` / `x500_depth`，并遵循本仓 `intruder_uav` 注释记录的**四种失败写法**实测结论：

- `<include merge="true">` 的子元素**只允许** `uri/pose/plugin/name/static/placement_frame`；
  塞 `<link>` 会被 sdformat **静默丢弃**（展开后 hl 不增加，只留一条
  `XML Element[link], child of element[include], not defined in SDF` 警告）；
- include 之后再写同名 `<link name="base_link">` 会**硬失败**（`link with name[base_link] already exists.`）；
- ⇒ 唯一可行注入点是**新增独立 link + fixed joint**。

相机 link `nadir_cam_link`：**无 `<collision>`**（不参与接触/测距/物理求解）、
`mass 0.050 kg` + `inertia 4e-5`（同 mono_cam）。相对 `x500_base` 的 2.0 kg 机体占 2.5%。

### 6. 为什么 **不接**任务链

识别**仍靠真值**（`gt_adapter` → `/agc/targets`），视觉定位路径已于 2026-11-04 退役
（[ADR-0009](0009-perception-truth-derived-and-vision-path.md#top)）。本相机：

- **零消费者**：没有任何节点订阅 `/agc/air/nadir/image_raw`（离线闸门静态守护）；
- 不新增识别/定位节点、不新增参数、不改任务数据来源；
- 桥条目注释明写"无消费者、仅取证/测绘"与"话题存在 ≠ 有帧"的判据。

> **"话题存在 ≠ 有帧"**（实测，`experiments/p1-4//evidence/camera-ownership-finding.md`）：
> `gz topic -l` 会列出**只有订阅者**的话题，而 `bridge.yaml` 正是以订阅方式桥接。
> 故默认臂（无相机）里 `/agc/air/nadir*` **照样出现在话题列表**，但一帧都没有（本轮实测 **0 帧**，见下）。
> 判"相机是否真的在发布"必须看 `ros2 topic hz` / 累计帧数 / 真实像素。

## 几何：地面足迹与 GSD

相机离地 `H = h_o + 0.242`（`h_o` 为地图派生飞行高度，[ADR-0007](0007-scene-geometry-single-source-and-layout.md#top)）。
`f = 268.6 px`；足迹 `= 2H·tan(HFOV/2) × 2H·(240/f)`；中心 GSD `= H/f`。

| 地图 | `h_o` | `H` | 地面足迹 | 中心 GSD | ±35° 边界视场 GSD |
|---|---|---|---|---|---|
| `yard` | 14.0 | 14.242 | **33.9 × 25.5 m** | **5.30 cm/px** | 7.90 cm/px |
| `minimal` | 2.5 | 2.742 | **6.54 × 4.90 m** | **1.02 cm/px** | 1.52 cm/px |

**与 的关系（一致，且需区分两个"边缘"口径）**：

- 中心 GSD 与 的 5.2 cm/px 一致（差 1.7% = 多算的 0.242 m 安装高）。
- 的"边缘 GSD 7.8 cm/px、不均匀度 1.49×"= `H·sec²θ/f` 在 **θ = 35°** 的取值
  （`5.30 × sec²35° = 7.90`，差 1.3% 为取整）。**该数字正确，本 ADR 不改它。**
- **两个"边缘"不要混用**： 的"边缘"指 **±35° 边界视场**（沿用 K2 的 `vfov/2 = 35°` 口径）；
  640×480 + HFOV 100° 的**画幅角**则是 `atan(400/268.6) = 56.1°`，该处径向放大 `sec²56.1° = 3.22×`。
  两者都对，只是**不是同一个量**—— 引用时必须说明用的是哪一个。

## 不做什么

- 不推导视觉检测算法、不做障碍物建图、不引入第三方资产；
- 不改飞行高度、不改任务场景、不改契约（///全不动）；
- 不新增 launch 参数、不新增 airframe、不改 `toolchain/**`；
- **不退休** `gz_x500_mono_cam`（见下）。

## Consequences

### 可回滚

单点回滚：把 `px4_sim_model` 改回 `gz_x500`（默认值）即完全回到旧行为——
相机模型资产、桥条目、条件注入都**不参与**默认路径。彻底删除 = 删
`src/agc_sim/models/agc_x500_nadir/` + `bridge.yaml` 的两条 + 两个 launch 里的
`nadir_enabled` 分支 + 本 ADR 与闸门测试。

### `gz_x500_mono_cam` **保留**（不退休）

派工单允许"若已零消费者则同批退休"。**核查结论：仍有白名单外消费者** ⇒ 按"发现仍有消费者则保留并登记"
处理，**不退休**、不加防复活断言。命中文件（`grep -rl gz_x500_mono_cam`，排除 `toolchain/`、
`experiments/`、`.git/`）：

- `docs/conventions/系统结构图.md`
- `docs/temp/11_1.md`
- `scripts/tests/test_branch_ledger.py`（注释里作为"非路线分支"的例子）

### 验证（本轮实测，T2）

| 判据 | 结果 |
|---|---|
| 默认臂 `gz_x500` 有相机帧？ | **0 帧 / 45 s**（实体 `x500_0`，`simulation model: x500`） |
| 新臂 `gz_agc_x500_nadir` 帧数 | **812 帧 / 45.0 s**，中位 **25.7 Hz** |
| `camera_info` | `640×480`，`fx=fy=268.60`，`cx=320 cy=240`，`plumb_bob` |
| 实体名 | `agc_x500_nadir_0`（与 GZBridge 规则一致） |
| `PX4_SYS_AUTOSTART` | 日志 `env SYS_AUTOSTART: 4001` |
| 图像内容是地面 | 目视：可见建筑投影、地面车辆、油桶、无人机自身影子（非天空） |

证据：`experiments/nadir-camera/20261104-nadir-arm-b-nadir/`（PNG + `probe.json` + `launch.log`）、
`experiments/nadir-camera/20261104-nadir-arm-a-default-probe/`（0 帧对照）。

### 与 的关系（结档后）

 保留全部几何事实（含"正俯视看不见目标"的约束）；"没有机载俯视"一句改为
"已有 opt-in 正下视相机（本 ADR），**仍不接任务链**"。 的**数字一个不改**。
