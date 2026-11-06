<a id="top"></a>
# 感知口径：真值派生与能力边界（视觉路径已退役）

## Status

accepted（2026-11-02 由 0020 / 0052 / 0053 / 0103 / 0110 合并；2026-11-03 新增 (a2) 真值目标指示的不确定性模型与置信度/精度解耦；**2026-11-04 视觉定位路径整体删除**，本 ADR 由"真值派生 / 视觉并行"改为"只有真值派生一条路径"。能力边界的「不做 / 不承诺」部分一并收窄登记）

## 背景

感知这件事在本项目里同时牵动四个问题：**模拟什么**（真值派生还是真实检测）、**机头朝哪**（观测偏航的指向来源）、
**看得见什么**（传感器安装高度与障碍族边界）、以及**模型与数值假设是否可信**（配置错误会不会静默变成控制错误）。
任何一条含糊，下游整链证据就失去意义：把真值派生的跟踪精度说成视觉能力、把 z=0.48 平面扫描当成任意障碍的
通用避障保证、或让未收敛的增益与漏配的数组静默生效，都会让结论无法复核。同时，外部合作方开发了空对地视觉识别
算法并要求接入任务决策，这直接冲击「真值派生」口径，按铁律「未决事项不得静默假设」必须显式裁定。

## 决策

### (a) 感知 = 真值派生仿真（非真实视觉 / 雷达）

- `air_perception` 以**世界真值**为输入、以**通道模型**产出观测：丢包 / 突发丢失 / 几何门控（量程 + FOV）/
  遮挡 / 高斯噪声与偏置，并给出**已标定** `confidence` 与观测序号 `obs_seq`。
  ⚠ **2026-11-04 起该输出无消费者**：原消费者 `air_fusion` 已退役，`/agc/air/obs` 在整链里
  没有任何订阅者。故上句描述的通道模型是**保留能力**，**不**在当前运行的整链中生效；
  `/agc/targets` 由 `gt_adapter` 发布且**无几何门控**（见 (a2)）。
  通道定义与噪声 / 置信度模型由 `/agc/perception/sensors_file` **单一注入**（契约
  [#params](0020-package-boundaries-and-runtime-topology.md#params)），节点不得覆写。
- **不做**真实视觉 / 雷达检测算法（点云聚类、图像识别等）；感知**不**消费-full 点云（点云属地面 costmap 输入）。
- **表述纪律**：文档 / 报告 / 论文**不得**把本感知表述为「真实视觉 / 雷达检测」或「目标识别」；涉及「跟踪精度」
  等指标必须限定为**仿真口径**。

### (a2) 真值目标指示的**不确定性模型**（2026-11-03 新增）

**背景**：2026-11-03 用户裁定—— 目标检测/追踪不再是项目重点，目标位置此后**一直由真值给出**，
项目重点转为"检测到目标之后"的工作。若真值链路**零噪声、零延迟、置信度恒 1**，
"能跟踪"这个结论只是把答案抄了一遍，**不成立**。

**决策**：`gt_adapter` 引入**六类不确定性**，参数名与 `air_perception` 通道**同名同口径**
（换源时下游一行不改）：

| 类别 | 参数 | 语义 |
|---|---|---|
| 位置噪声 | `sigma_xy_m` / `sigma_z_m` | 高斯，源采样时刻加噪 |
| 时间延迟 | `latency_s` | 改**交付**时刻，不改源采样时刻（延迟可测） |
| 丢包 | `drop_prob` | 单拍独立同分布 |
| 成簇丢失 | `drop_burst_prob` / `_mean_s` / `_mean_gap_s` | 两态马尔可夫 |
| 链路可信度 | `confidence` | **配置声明值**，非精度 |
| 速度 | α-β 滤波器 | 由**噪声位置**估计 |

**唯一与 `air_perception` 的差别**：真值链路**不做几何门控**（无量程 / 无 FOV / 无遮挡）——
目标指示不分远近。

#### 置信度与精度**必须解耦**（本次修订的核心理由）

旧口径把两者混成一个数：`conf = 1 − exp(−tol²/(2σ²))`。
**实测后果**：`tol=0.25 m` 时 σ 只要超过 **0.2123 m**，conf 就跌破下游 `confidence_min=0.5`，
**整条航迹被拒收**——"给真值链路加 0.5 m 噪声"这个完全合理的需求会**直接打断链路**。
而目标机体本身就有 0.32 m。这不是模型不准，是**两个语义被塞进一个字段**。

| 字段 | 回答的问题 | 来源 | 消费者 |
|---|---|---|---|
| `TargetTrack.confidence` | **这条航迹是不是真的** | 通道配置显式声明（缺省 1.0） | `confidence_min` 门 |
| `TargetTrack.pose.covariance` | **这条航迹有多准** | `sigma_xy_m` / `sigma_z_m` | 融合权重、误差评估 |

两者**不再互相派生**。σ 变大只影响协方差与融合权重，**不再**导致航迹被拒。
要检验 `confidence_min` 门本身，把通道 `confidence` 配到 0.5 以下即可，
**不得**靠调大 σ 冒充（那是在用精度问题冒充可信度问题）。
载体：`agc_perception/include/agc_perception/confidence.hpp`（文件头写明理由）；
旧函数改名 `coverageProbability`，保留但**只作诊断**（"给定 σ，误差落在 tol 内的概率"）。

#### 速度必须走滤波器（否则噪声被放大 ~9.4 倍）

旧实现用 `diff_window_s=0.15` 对**真值**差分，零噪声下精确。一旦位置带噪 σ_p：
`σ_v = σ_p·√2/Δt ≈ 9.43·σ_p` —— σ_p=0.5 m 时 σ_v≈4.7 m/s，比目标自身速度（0.5 m/s）大一个量级，
会直接驱动 `standoff_follower` 的速度前馈 → 跟踪剧烈抖动。

采用 **α-β 滤波器**（Kalman 稳态等价形式），增益由跟踪指数解析给出、**不手调**：
`Λ = σ_w·Δt²/σ_p`；`α = 1 − r²`，`β = 2(2−α) − 4√(1−α)`（Kalata 关系式）。

实测（2026-11-04 可复跑产物，σ_w=0.5 m/s²；`scripts/tracking/alpha_beta_mc.py`）：

| σ_p | α | β | σ_v（差分，窗 0.15 s） | σ_v（差分，单拍 0.1 s） | σ_v（α-β） |
|---|---|---|---|---|---|
| 0.25 m | 0.181 | 0.018 | 2.357 m/s | 3.535 m/s | **0.079 m/s** |
| 0.50 m | 0.132 | 0.009 | 4.714 m/s | 7.071 m/s | **0.095 m/s** |
| 1.00 m | 0.095 | 0.005 | 9.428 m/s | 14.142 m/s | **0.114 m/s** |

> **口径纪律**：差分 σ_v 有**两种**算法（窗长 vs 单拍），旧文里的"42.8×/65.2×/110.9×"
> 把两者混用了、与任一列都对不上。现行产物**分开列**：
> 按窗 0.15 s 是 29.9×/49.7×/82.6×，按单拍 0.1 s 是 44.8×/74.6×/123.9×。
> 引用时必须写明用的哪一列。产物：`experiments/n4-tracking-metrics/20261104-alpha-beta-0/metrics/alpha_beta_mc.json`；
> 同口径的 C++ 单测见 `src/agc_perception/test/test_alpha_beta.cpp`。

**退化保护（必须保留）**：σ_p → 0 时 Λ → ∞，解析增益趋于 α=1, β=2，该点滤波器退化为**二阶振荡**
（实测速度序列在 1.00/−0.00 间逐拍翻转）。故 **σ_p ≤ 1e-6 m 时旁路滤波器**，回落短窗差分
（零噪声下差分精确）。载体：`gt_adapter.cpp` 的 `filterActive`。

#### 档位与能力边界

**2026-11-04 验收实测**（s04 / seed 0 / full / `target_source=gt_adapter`）：

| 档位 | 终态 | hold 事件 | 跟踪误差 p50 / p95 | 观测延迟 p50 / p95 |
|---|---|---|---|---|
| `ideal` | TRACKING_SUCCESS | 0 | 0.0020 / 0.1024 m | 0.012 / 0.024 s |
| `nominal` | TRACKING_SUCCESS | 1 | 0.0013 / 0.1003 m | 0.224 / 0.256 s |
| `stress` | MISSION_FAILED (TIMEOUT) | 23 | 0.0081 / 0.1038 m | 0.316 / 0.372 s |

> **p95 无判别力**：三档都饱和在 ≈0.10 m（`standoff_follower.max_step_m=0.1` 限幅所致）。
> 有效判据是 **hold 次数**与**观测延迟**—— 延迟实测 p50 = 0.012/0.224/0.316 s，与配置的
> 0.0/0.2/0.3 s 逐档对齐，证明 `latency_s` **确实可测**（出口判据 2）。
> 产物：`experiments/n4-tracking-metrics/20261104-n4-acceptance/metrics/n4_acceptance.json`。

| 档位 | `sigma_xy_m` | `latency_s` | `drop_prob` | `drop_burst_prob` | 用途 |
|---|---|---|---|---|---|
| `ideal` | 0.0 | 0.0 | 0.0 | 0.0 | 链路连通性基线（**不得**据此宣称鲁棒性） |
| `nominal` | 0.3 | 0.2 | 0.1 | 0.0 | 主口径（**必须**达 `TRACKING_SUCCESS`） |
| `stress` | 1.0 | 0.3 | 0.3 | 0.1 | 只用于**失效恢复**验证，**不要求**达 `TRACKING_SUCCESS` |

**`stress` 档为什么"允许失败"**（用户 2026-11-03 裁定）：
抵近判据是 `|target − car| ≤ d_track=3.0 m` 且要求**连续 `t_dwell=3.0 s`**。
σ=1.0 m 下 `x_est ~ N(15, 1.0)`，单拍满足概率 0.690，**连续 30 拍（3 s @10 Hz）概率 1.47e-05**
⇒ **结构性不可达**。这不是"系统不鲁棒"，是**任务尺度与不确定性尺度不匹配**（σ 相对判据带宽占 33%）。
被否决的两个替代：① 把 σ 降到 0.5（连续 30 拍仍只有 1.5%，只是把"不可达"换成"极难"，**没解决尺度不匹配**）；
② 放宽的 `d_track`/`t_dwell`（**改契约口径**，且"放宽判据让测试通过"是自欺）。
若日后要提高 σ 上限，须先解决"判据带宽 vs 噪声尺度"匹配（例如把改成**带不确定性的概率判据**），
那是**新决策**，不得在现有下悄悄放宽。

**`latency_s` 必须 < `target_max_age_s`（否则零余量）**：
`target_max_age_s=0.5 s`；latency 0.2/0.3/0.4/0.5 对应余量 0.30/0.20/0.10/0.00 s，
可容忍连续空拍 3/2/1/**0** 拍。同理 `drop_burst_mean_s` 也必须 < 该余量，
否则每次 burst 必然打断 tracking（原 0.5 已改为 0.1）。

<a id="perception-path"></a>
<a id="b"></a>
### (b) 视觉驱动路径：**已于 2026-11-04 整体退役**

**2026-11-04 用户裁定：删除视觉定位路径。** 项目不做目标识别/追踪，目标位置**始终由真值给出**，
因此不再需要"从像素反推位置"的第二条感知路径。

**删除范围（可复核）**：

| 项 | 处置 |
|---|---|
| `camera_tf` / `vision_target`（`agc_perception`） | 源文件删除，CMake / package.xml 依赖（`vision_msgs`）移除 |
| `scripts/vision/`（检测器桩、数据集采样、相机探针、N1 探针与指标） | 目录删除 |
| `perception_path` / `vision_detector` / `detector_backend` / `vision_model_*` / `target_plane_z_m` | 7 个 launch 参数删除 |
| `/agc/perception/path` 契约参数 | 契约[参数入口](0020-package-boundaries-and-runtime-topology.md#params)清单中删除 |
| `perception.yaml` 的 `camera_tf` / `vision_target` 两段 | 删除 |
| N3 回归矩阵的 `vision-cost` 臂 | 删除（矩阵不再有"感知代价臂"） |
| 5 个视觉专项测试 | 删除；替换为**防复活闸门** `test_vision_localization_path_is_retired` |

**保留项（重要，不是遗漏）**：

- `summary.json` / manifest 里的 `perception_path` / `detector_backend` / `vision_model` / `vision_plane`
  字段**保留、值固定**（`truth` / `none` / 空 / `applied=false`）。理由：这些是对外产物 schema，
  历史 run 都带；删键会让新旧 run 不可直接对比。**保留不表示存在可选路径**。
- `scripts/tracking/track_err_probe.py`（原在 `scripts/vision/`）**保留并迁移**：它是空中跟踪误差
  取证工具，与视觉无关，N4 出口判据 1 的 p50/p95 依赖它。

**对将来"正俯视相机 → 障碍物地图"需求的口径**（防止误读）：

- 那是**另一条需求**（障碍物分布识别），当年 (b2) R2 已写明"今天**无任务承载**"，本次删除**不涉及**它；
- 它与被删的"视觉目标定位"**无代码共用**—— 后者只处理单个高亮球的坐标，不处理障碍物几何；
- 将来实现时**不得**复用本文删除的任何代码或结论，相机 TF / 标定 / 障碍物几何都须重新做。

<a id="b2"></a>
### (b2) 历史裁定 R2/R7（2026-10-31，**R7 已被 (b) 取代**）

- **R2 · 无人机识别"地面障碍物分布"：先真值仿生，后换真视觉**
  - **裁定（2026-10-31）**：视觉算法到货前**继续用真值仿生**（沿用本篇 (a) 口径）；到货后再换**真视觉算法**。
  - ⚠ **2026-11-04 用户裁定：「没有双相机分工，识别靠真值」**—— 本条的"换真视觉"**没有**任何已批准
    的路线（无相机、无方案、无排期）。它至多说明"若将来有视觉算法，职责边界如何"，**不得**读成
    "项目计划实现视觉识别"。现行与可预见范围：**识别一律靠真值**。
  - **现状**：地面障碍地图的静态先验来自配置 `obstacles_file`（`map_adapter.cpp`）；
    空中障碍观测同样来自配置 YAML + 几何遮挡判定（`air_perception.cpp`）—— 即"真值仿生"**已是现状**。
  - **边界（不得混淆）**：障碍物分布的真视觉化是**另一条后端需求**（今天**无任务承载**）。
    原用于它的"橙色高亮目标"检测桩已随 (b) 一并删除—— 它本来也**不是**障碍物识别。
- **R7 · 目标位置识别仍用真值仿生，后续再换视觉** —— **已被 (b) 取代并终结**
  - 2026-11-03 曾裁定"视觉后端降为可选分支、代码保留"；**2026-11-04 进一步裁定：直接删除**。
  - 因此 `/agc/targets` 的发布者恒为 `gt_adapter`（**无门控，不分远近**）——**没有第二条路**。
    `air_fusion` 同日退役；`air_perception` 于 **2026-11-06 整体删除**（届时其 30 m 量程 / FOV 门控
    本就已**不影响** `/agc/targets`）。

### (c) 传感器高度与障碍族可见性边界（如实登记、收窄声明）

- **传感器高度**：`car/lidar_link` **`z=0.48 m`**（**车顶水平面**）。模型为 `gpu_lidar` 3D（H 360 束 / V 16 束
  ±15°、`range [0.2,20]`、10 Hz），但安全层 / costmap 消费的 `/agc/ground/scan_filtered`（经 `scan_self_filter`）
  **等价于 z≈0.48 m 的 2D 水平面**扫描 → 安全层可见性 = 单一平面。
- **障碍族可见性边界（如实）**：① **低障碍**（顶面低于扫描面 / 不入水平光束）→ **不可见**；② **悬空**结构
  （在 z=0.48 之上、非扫掠高度）→ **不可见**；③ **薄障碍**（细柱 / 薄板）→ 受**束间距**限制（距离 `D` 处相邻
  束间距 `≈ 0.01745·D m`，三档 `velocity_polygon` 用 `min_points=2`）；④ 自体遮挡 / 自滤后仅未被车体遮挡的方向可见。
- **收窄声明**：把「立柱 world 达标」限定为「在 `z≈0.48 m` 处有**足够水平截面**且**进入光束**」的障碍族，**明确不得外推**为任意障碍的通用保证。
- **参照依据（取证）**：同版本 `nav2_collision_monitor` 的 `scan` 源**没有**高度带参数（`pointcloud` 源才有
  `min_height` / `max_height` / `use_global_height`）→ 用 `scan` 即隐含「只覆盖扫描平面那一层」；`min_points`
  决定进入 zone 所需最少点数；失效源 `getData` 返回 false（**封锁机器人**，非静默透传）。落点为本 ADR +
  `agc_car.sdf.xacro` / `ground.yaml` 的**注释登记**（**不改物理**）。

### (d) 载荷外伸与碰撞口径一致化（显式声明各自适用域）

「一侧计入、另一侧不计」：出生净空**计入**载荷外伸 `1.0 m`，而 `car/capture_net`（@ `(0.55,0,1.60)` 半径 1.0）与
`car/jammer`（@ `(-0.20,0,0.30)`）**无 collision**、`mass 0.05`、位于 z=1.60（高于 0.48 扫描面）→ 碰撞 / 安全层
**不计**。裁定为**显式分层**：

- **净空（布局约束）**：载荷外伸 `1.0 m` **仅**作为出生净空推导的外伸登记（见 [ADR-0012](0012-spawn-clearance-and-reset-transaction.md#top)），约束场景随机化不得使其侵入他实体初始包络；
- **安全层（2D 视野）**：载荷位于 z=1.60、**不**在 z=0.48 扫描面 → **不**进安全层视野（显式声明）；
- **物理碰撞**：载荷**无 collision** → 捕获 / 干扰**行为级**以外的物理接触验证**不适用**（登记 `unsupported`）；
- **重标定义务**：载荷**物理启用（加 collision）后**，/与本外伸 / 碰撞口径**必须重新标定**，不得借旧标定维持。

### (e) 能力标定：换装后车体的制动 / 转向（优先真跑 gz 取真值 / 接触证据）

四轮外观、后两轮驱动 + 前自由从动 **≠** 原 Husky 滑移动力学，「视觉上像真实平台」不等于「相同制动 / 转向能力」，
故必须从**换装后模型**单独标定：

- **证据源**：gz 真值 `/agc/gt/agc_car`（`gt_bypass` 直读 gz `/world/agc_world/dynamic_pose/info`）；接触证据 `/agc/ground/contact`（`gz.msgs.Contacts` → `ros_gz_interfaces/Contacts`）。
- **满速制动**：经**唯一执行口** `/agc/ground/cmd_vel` 命令至 `v_max=1.5 m/s` **稳态**（真值速度判稳），再命令零，
  测真值**制动距离**与**制动耗时**（**不**只看「发布零命令」）。**转弯扫掠 / 摩擦敏感性**：命令 `ω_max=2.0 rad/s`
  （原地）测实际**偏航率**；命令 `(v,ω)` 组合测实际**转向半径 / 扫掠净空**；真值速度 vs 命令速度差记**滑移敏感性**。
- **实测（`experiments/w6-task-eval/20261017-w6-r037-0/r037/bench.json`）**：满速制动**距离 `0.281 m`**、
  **耗时 `0.384 s`** → 等效减速度 `a = v²/(2s) ≈ 4.0 m/s²`，**显著大于**旧假设 `a ≈ 0.9 m/s²`（碰撞档 `2.0 m`
  对本模型**偏保守**，绝对值不变、重标须批准）；原地 `ω=2.0` → 偏航率 **`1.734 rad/s`**（比值 0.867）；
  弧线 `(1.0, 1.0)` → 转向半径 **`1.126 m`**、外扫掠半径 **≈ `1.705 m`**、滑移比 ≈ 0；满速逼近 `pole_1`
  → **1 次接触事件**（`t≈2.98 s`，接触位 gt ≈ `(−0.03, −5.31)`）。
- **若本环境无法稳定实跑 gz**（GUI 库缺失 / DDS 发现 / lifecycle 卡死）→ **如实标 `unsupported`** + 失败证据（日志），
  **不**伪造、**不**借旧标定维持/。

### (f) 数值健全与配置合法性：启动期拒绝，不静默兜底

对齐 Nav2 的守法「启动期声明 → 校验 → 非法即 FATAL / 抛错」，改掉四处静默行为（**取证** = 同版本 Nav2 头文件的
启动期校验惯例 + 本机真实二进制台架实跑）：

- **LQR 精确离散化**：`Ad = I + A·dt + 0.5·A²·dt²`（A 幂零 → 高阶项为零 → **恰为精确**）；
  `Bd = B·dt + 0.5·A·B·dt²` → **`Bd = [[0.5·dt²·I],[dt·I]]`**（补上旧实现漏掉的位置 `0.5·dt²` 项）。
  适用频率 = `1/dt`（air `dt=0.02` → **50 Hz**；ground `dt=0.05` → **20 Hz**）。
- **DARE 收敛 / 有限性**：记录迭代次数与残差 `max|P_next − P|`；迭代结束若**残差 ≥ `tol_`** 或 `P` / `S` / `K_`
  含非有限值 → **抛 `std::runtime_error`**（`configure` 失败，由生命周期 error 路径接管），**不静默使用**。
  默认 `max_iter` 由 **200 提为 2000**：实测 `tol=1e-10` 需**约 559 次**迭代（旧默认 200 次时残差 ≈ **0.0088**，
  即旧实现一直在用**未收敛**增益）。暴露只读诊断 `converged` / `residual` / `iterations` / `dt` /
  `appliedFrequencyHz`（非 ABI）。
- **集中合法性校验** `validateParameters`：`q_pos_ / q_vel_ / r_ / dt_ / tol_ > 0` 且全为**有限**，`max_iter_ > 0`，
  `acc_max_` 有限；**删除** `dt<=0 → 0.02` / `r<=0 → 1.0` 的静默兜底 → 改为**拒绝并报出字段与值**。
- **安全层平行数组**：`obstacle_names/x/y/safety_radius` 四数组长度**必须相等**（删除 `n=min({...})` 静默截断，
  否则报出各数组长度并抛错）；`safety_radius > 0` 且有限、坐标有限；「磁盘联合约束」语义**不变**。
- **地图与 `seed` 启动期校验**：`map_adapter` 新增 `validateStartupOrThrow`（构造末调用）校验
  `resolution/size_x/size_y > 0` 且有限、`origin_x/y` 有限、障碍 `x/y` 有限、`size`（`sx/sy > 0`）有限、`yaw` 有限，
  非法即**拒绝启动**（运行期 `rebuild` 守卫保留）；`scenario_reset.spawn_seed` / `run_logger.seed` 为强类型
  `int`，由 ROS 参数类型系统在启动期拒绝（登记为「已覆盖（类型安全）」）。
  （`air_perception.seed` 的同类校验随该节点于 2026-11-06 删除，不再有消费者。）
- **ground 映射的适用性标注**：共享 LQR 输出 3 自由度 holonomic 世界加速度，`ground_baseline` 仅取前进分量
  `lin = clamp(bx, 0, v_max)`（**丢弃倒车**）+ `ang = k_yaw·atan2(by, max(bx, 0.1))`（**丢弃纯横向自由度**）
  → 可达集 ⊊ 世界系 holonomic 参考集。**不**本批重写为完整差速动力学，只加**适用性注释**并做**独立解析对拍**：
  `ground_frac_desired_tracked_within_10pct ≈ 0.042`（72 个方向仅前向窄扇区 3 个可跟踪）vs `air = 1.0`，
  **不**假定 air 与 ground 同等闭环。

### (g) 观测偏航的指向来源与冷启动

`trajectory_tracker` 的 `observe_yaw_mode` 有三档，`track` 为新增的**非 oracle** 协同观测臂：

| 模式 | 机头朝向 | 指向源 |
|---|---|---|
| `velocity`（默认） | 随速度方向 | 无（固连前视相机不保证对准目标） |
| `target` | 对准目标 | `/agc/gt/intruder_uav`（**真值**，显式 oracle 臂，须标注） |
| `track`（新增） | 对准感知航迹 | `/agc/targets`（`agc_msgs/TargetTrackArray`） |

- **指向来源 = 既有感知航迹缝** `/agc/targets`，复用节点已有的 `target_sub_` / `target_pos_` / `target_stamp_` /
  `target_confidence_`；**不新增**消息、话题或 ABI；**不创建、不读取** `/agc/gt/*` 指向订阅（GT 订阅仍只存在于
  `target` 分支，由 `observe_yaw_mode_ == "target"` 守卫）。
- **新鲜门** `track_aim_fresh` 复用口径（源时间窗 + `confidence_min`），并**额外**拒绝 NaN/Inf 航迹。
- **冷启动不自锁**：无 fresh 航迹时**不**退回 `velocity`、**不**用真值播种，而是执行**确定性偏航搜索**：以
  `yaw_search_rate_dps` 匀速扫过 `±yaw_search_amplitude_deg` 扇区、到边界**折返**（三角波）；基准是**接管瞬间的
  机头朝向** `search_center_yaw_`（**不是**目标方位）；相位只由接管后经过时间决定（`fmod`），同起点必得同一朝向。
  **只改偏航**：平移仍由 `effective`（八字 + 恒速 + 高度基准）给出，搜索分支**不触碰**轨迹、`z_offset_` 或参考位置。
- **失效与复位**：航迹为空 / 过期 / 低 confidence / 非有限 → 视为无 fresh 航迹，回到确定性搜索，**不**无限期沿用旧航迹；`/agc/air/reset_phase` 与接管**同时**重置 `search_center_yaw_` 与「已指向 / 已搜索」日志锁。
- **生效参数（节点本地 config，未进契约参数清单）**：`yaw_search_rate_dps=25.0`、`yaw_search_amplitude_deg=120.0`；
  由 `episode_runner --observe-yaw-mode track` 显式启用并记入产物；`velocity` / `target` / `run_demo` 的选择**均不改**。
- **实测**：full baseline GUI `20261101-g2-r8b-track-gui-baseline` 与 full RL GUI `20261101-g2-r8b-track-gui-rl`
  （均 `s04` / seed 0 / GUI / full / `track`）→ **`TRACKING_SUCCESS`**；冷启动扫掠约 3.4 s 后指向生效
  （`desired_yaw≈-26°`）；同一次 `track` 运行读 `ros2 node info /trajectory_tracker`，订阅含 `/agc/targets` 且
  **无任何 `/agc/gt/*`**（`20261101-g2-r9-track-rl-v4`，须在 lifecycle `active` 之后采集）。
- **证据口径（不得外推）**：只证明「真值派生航迹驱动指向 + 无直接 GT 指向旁路」，**不**证明任何视觉感知 /
  识别能力。视觉定位路径已于 2026-11-04 退役，不再存在"切到 vision"的选项。

## 不做什么（边界）

- **不**做真实视觉 / 雷达检测算法；**不**把真值派生结果表述为视觉能力或真实识别能力。
  视觉定位路径（`camera_tf` / `vision_target` / 像素检测器）已于 2026-11-04 **整体删除**，
  不得以任何方式重新引入"从像素反推目标位置"的链路。
- **不**把 `target`（oracle）当默认验收臂；**不**通过降低 `air_perception` 的 FOV / 新鲜门让 `behind` 通过；
  **不**为迁就观测而改平移轨迹。
- **不**改冻结 9 消息 / 服务 ABI，**不**变唯一执行口语义（`/agc/ground/cmd_vel` 仍是唯一命令车体通道），
  **不**新增**第二 ROS 命令者**；**不**回退 `kinematic_sim`、**不**改车体物理 / 惯性 / 驱动插件 ——
  保留 **DiffDrive** 真实物理路线。
- **不**启用载荷物理（不加 collision），因此物理接触验证保持 `unsupported`；低障碍 / 悬空障碍的实测可见性
  （ray / scan 记录）为后续可加证据，本批不测。
- **不**本批把 ground 控制律重写为完整差速动力学；ground 与 air 的闭环差异**不**外推。

## Considered Options

- **真实传感器感知（消费点云做聚类检测）** —— 被否：改变研究口径与工作量级；激光链路挂在车体（costmap 消费方
  在地面侧），己方无人机无检测传感器；且会与旧树对照口径脱节。
- **纯视觉替代真值派生 / 视觉仅展示不接决策** —— 被否：前者一次性作废既有证据与可对照基线，后者不满足需求。
- **视觉定位路径保留为可选分支（2026-11-03 曾裁定的"代码保留"）** —— **2026-11-04 改为删除**：保留意味着
  每次改感知都要同时维护两条路、测试要覆盖两份、产物要带路径标识；而项目已明确不做识别，
  分支永远不会被用到的收益抵不过维护成本。
- **不加声明、只在报告文字里提模型限制** —— 被否：限制不落真源，下游仍会外推。
- **把 `capture_net` 降至扫描面 / 加 collision 使口径物理一致** —— 本批不取：会重新遮挡激光前向视野（网面在正前方
  恒返回 `0.50 m`）、改变捕获几何且需重标/；改为显式声明各自适用域。
- **仅凭旧标定 `a≈0.9` 断言制动能力 / 实跑困难时伪造数值** —— 被否：前者未从换装后模型验证，后者违「不伪造」红线。
- **保持 `Bd=B·dt` 近似 + 不报告未收敛 / 未收敛时只记 WARN 并沿用末次 P** —— 被否：仍静默使用不可靠增益；
  改明确失败（默认预算提为 2000 使合法配置可达）。
- **地图 / `seed` 非法仅记 ERROR 继续运行** —— 被否：会静默漏障碍 / 静默退回种子；改启动期拒绝。
- **`velocity` 直接接受 `behind` / 改 FOV 与新鲜门让 `behind` 通过** —— 被否：前者使 full GUI 任务永远停在
  `AIR_SEARCH`、出口无法闭合，后者是降低观测门来假装目标可见。
- **航迹指向 + 确定性搜索** —— **采纳**：不引入 GT、不改平移、不降门，且能打破冷启动自锁。

## Consequences

- **正面**：感知口径、视觉路径、机头指向三者边界清楚且**互不冒充**；传感器高度（z=0.48）与障碍族可见性边界
  （低 / 悬空 / 薄）落真源，安全声明**收窄**；载荷**外伸（净空）**与**碰撞（物理 / 安全层）**口径显式分层；
  换装后车体的制动 / 转向 / 摩擦以真值 / 接触证据标定；数值缺陷（`Bd` 缺项、未收敛增益、平行数组截断、
  `seed` 静默兜底）被暴露并改为显式失败；多一个非 oracle 观测臂且冷启动不自锁。
- **代价 / 限制**：「立柱 world 达标」仅对限定障碍族成立，安全结论适用范围**变窄**（如实）；载荷物理接触验证
  `unsupported`；//的绝对值重标须另行批准；搜索是**开环扫掠**，不保证任一时刻对准目标（只能「扫到就看见」），
  幅度外仍可能长时间不可见，属**有意取舍**；`track` 的指向质量受 `/agc/targets` 新鲜度与 confidence 限制；
  ground 控制律未换为完整差速动力学，对拍为**解析分析**（非整链仿真）。
- **未决 / 后续**：载荷物理启用后**必须重标**/与外伸 / 碰撞口径；容限、视觉模型检测性能与
  `DetectionArray` 消息形态、相机挂载点在实现批闭合；ground 完整差速动力学 / 可达集实测后续批次。

## 参考

- 评审：[10-风险](../reviews/agc-review-2026-10-14/10-风险.md#r-037)（传感器 / 车体能力）、
  [10-风险](../reviews/agc-review-2026-10-14/10-风险.md#r-038)（数值模型与配置边界）；契约：
  [#hard-constraints](0020-package-boundaries-and-runtime-topology.md#hard-constraints)、[#execution-port](0020-package-boundaries-and-runtime-topology.md#execution-port)、
  [#params](0020-package-boundaries-and-runtime-topology.md#params)、[#messages](0020-package-boundaries-and-runtime-topology.md#messages)
- 相关决策：[ADR-0010](0010-safety-thresholds-and-failsafe.md#top)（安全阈值与接触真值）、
  [ADR-0011](0011-interception-and-fire-control.md#top)（拦截与火控）、
  [ADR-0012](0012-spawn-clearance-and-reset-transaction.md#top)（出生净空）、
  [ADR-0008](0008-air-trajectory-and-tracking-calibration.md#top)（空中轨迹与跟踪标定）、
  [ADR-0014](0014-task-fsm-and-scenario-transaction.md#top)（任务 FSM）、
  [ADR-0020](0020-package-boundaries-and-runtime-topology.md#top)（包边界与语言选型）、
  [ADR-0006](0006-experiment-artifacts-and-evidence-discipline.md#top)（产物纪律）、
  [ADR-0003](0003-nav2-paradigm-absorption.md#top)（Nav2 范式吸收）
- Nav2 参照：`nav2_collision_monitor` 的 zone vs footprint（`polygon.hpp`）、`velocity_polygon` 子区、source 覆盖声明
  （`scan` 无高度带 vs `pointcloud` 的 `min_height` / `max_height`）、`min_points`、失效源封锁（`source.hpp`）；
  `nav2_util::validateMsg` / `node_utils` / `twist_subscriber` 的「非法即抛错」惯例
- 实现：`agc_car.sdf.xacro` / `car.yaml` / `ground.yaml` / `lqr_controller.{hpp,cpp}` / `ground_baseline.cpp` /
  `safety_shield.cpp` / `map_adapter.cpp` / `air_perception.cpp` / `trajectory_tracker.cpp`
