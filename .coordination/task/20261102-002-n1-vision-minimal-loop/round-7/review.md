<a id="review"></a>
# N1 · round-7 Leader 独立审查

- 任务 ID：`20261102-002-n1-vision-minimal-loop`；轮次：7
- 审查者：Leader；审查时间：`2026-11-02T17:55:00+08:00`（Asia/Shanghai）
- 结论：**调研与定性达标，交付质量超出派工要求；但 N1 本身仍不能验收。** 状态：`已验收（本轮的调研/定性任务）`，N1 转 round-8 待用户裁定 5 项后实施。

## 一、Leader 亲自核验的核心结论

### 1.1 `shield_infeasible_rate` 口径纠正 —— **成立，且是重要纠错**

Worker 称该指标是**地面** `collision_monitor` 的 proxy_v1，不是空中安全层。Leader 逐行读 `run_logger.cpp`：

- 第 7–10 行原文："`shield_infeasible_rate` —— **重定义**：安全层触发（collision_monitor STOP/SLOWDOWN）且"触发时不可行"（前向扫描 ≤ contact_dist_m，或 TTC < ttc_min_s）的事件占比 = `infeasible_ticks / triggered_ticks`"
- 第 15–16 行：标为 `proxy_v1`（历史口径）
- 第 983–989 行：`contact = scan_min_forward_ <= contact_dist_m_`（默认 2.0 m）、`ttc < ttc_min_s_`（默认 1.0 s）→ `++infeasible_ticks_`
- 第 155–157 行：`contact_dist_m_=2.0`、`ttc_min_s_=1.0`、`forward_cone_rad_=0.9`

Leader 独立验算分母：162101 的 `588 / 914 = 0.643326`，与 summary 的 `episode_window_metrics.shield_infeasible_rate` **完全一致**；进程口径 `588 / 920 = 0.63913` 亦一致。

**Leader 裁定**：Worker 的口径纠正是**对的**。round-6 审查中我写的"安全层不可行率 64%"**表述失准** —— 它衡量的是**地面车**在碰撞监控触发拍中"前向扫描过近或 TTC 不足"的占比，不是空中 `safety_shield` 的三维不可行。这不改变"162101 是失败运行"的结论（`MISSION_FAILED/TIMEOUT` 由 summary 独立证明），但**归因表述必须更正**。我已在本审查中记录该更正，round-6 review 的原文按"历史不追溯改写"原则保留。

### 1.2 四次运行配置等同性 —— 成立

Leader 读 `run-config-compare.json`：三 run 的 `params_applied.yaml` 哈希同为 `ddc7d883…`；16 个可比字段（含 `seed_protocol`、`geometry_sha256`、`spawn_layout_sha256`）全为 `true`；唯一差异 `detector_backend` 是 155603 早于该字段落地，属元数据而非配置。

Leader 补充核实：三次 run 的 manifest `target_source` 均为 `air_fusion` —— 但 vision 模式下 `air_fusion` **未启动**，故该字段是 composition 的静态声明，不构成实际数据源。此点 Worker 未指出，**不构成缺陷**（不影响结论），但记录备查。

### 1.3 三个硬约束 —— Leader 独立验算

| 约束 | Worker 值 | Leader 验算 | 结论 |
|---|---|---|---|
| K1 `\|dz\| ≤ √(R²−S²)` | 6.32 m | `√(144 − 10.2²) = √(144−104.04) = √39.96 = 6.321` | ✅ |
| 只抬己方机到 12 m（`dz=10`） | 水平预算 6.63 m | `√(144−100) = √44 = 6.633` | ✅ 且 < 停止点 10.2 → 感知失效 |
| K2 `\|dz\| ≤ S·tan(35°)` | 7.14 m | `10.2 × 0.7002 = 7.142` | ✅（比 K1 松，K1 先绑定） |

`H_max_env` 数据 Leader 亦从 `height-survey.json` 复核：`minimal` 0、`open_field` 0、`yard` 静止 **2.10**（`pipe_rack_e`）/ 移动 **7.975**（`tank_farm_e`）—— 与文档 §6 一致。

### 1.4 "抬高降低可见性" —— 反直觉但成立

这条是本轮最有价值的结构性发现。Leader 认可其推导：K1/K2 只约束 `dz`，故**两机同步等量抬升是感知中性的**；单抬己方机会拉大 `dz` 从而缩小水平预算。这直接否定了"把己方机抬到楼顶高度"这个直觉方案。

### 1.5 外部调研补做情况 —— 合格

Leader 曾指出前期 `web_search`/`web_fetch` 均为 0 次。补做后 `external-references.md` 含 **14 条来源 + 完整检索记录（含无果项）**，覆盖：

- 法规：FAA 14 CFR 107.51（eCFR 原文）、UK CAA UAS.OPEN.040、EU 2019/947、**中国 CCAR-92**（第 92.627 条"统一基准高度设置规则"——这条与本项目"每图一份高度基准"高度契合）
- 飞控：PX4 `TrajectorySetpoint`（`NED local world frame`，无地形字段）、`VehicleLocalPosition`（local origin = EKF2 启动瞬间机位；`dist_bottom` 需测距传感器）
- 地形跟随：ArduPilot（SRTM 精度 ~10 m，"suitable for 60 m or more"）→ 支撑"本项目 3–10 m 尺度不能用 AGL"
- 同类仿真：AirSim（NED、世界原点统一）、Gazebo spawn（`-z` 是世界系，世界文件无"飞行高度"概念）

**纪律执行正确**：文件开头有明确声明"法规条目只作量级参照，不构成合规声明"，且每条都标了"对本项目哪条结论有支撑"。E12 主动标注为"弱证据、数值未取得、不用于定量结论" —— 这是诚实的做法。

### 1.6 证据纪律 —— 这次做对了

`round-7/evidence/` 采用**一 run 一目录**（`run-155603-2790` / `run-161832-2961` / `run-162101-7315`），每目录含 `OWNERSHIP.md` 标 `run_id` + `launch_pid` + 起跑墙钟 + 源文件绝对路径 + 源 sha256。跨 run 比对集中在 `../run-config-compare.json` 与 `../b-causal-chain.json` 且逐项带 run_id。

Leader 校验：`sha256sum -c SHA256SUMS.txt` 19 项**全 OK**。round-6 的混装问题**已纠正**。

### 1.7 两处自我纠错 —— 认可

1. **时钟映射**：弃用 `summary.wall_start − sim_start` 常数偏移（实测漂移 15.365 s、隐含 RTF 0.9114、会错位约 19 s），改用探针成对 `(rx_epoch, track_stamp)` 分段内插，最长停止段由 27.888 s 修正为 **24.93 s**，并记录了拒绝另一口径的理由。这是**主动发现并修正自己的错**，证据价值高。
2. **包络算法**：AABB 外扩 → 精确胶囊/矩形距离（Liang–Barsky）。修正方向正确（前者过度保守会把 15.8 m 外的角部障碍算进来）。

## 二、对 round-6 两个缺陷结论的更新

Worker 本轮**用同一平面 z=2.0 重算**，发现报告点与真值射线交点仍差 **p50 10.14 m**，据此认为"方位（像素侧）也有问题"，推翻了 round-6 把主因归于平面假设的判断。

**Leader 判断**：这条**方向正确但未闭环**。它证明了"平面假设不能解释全部误差"（我已独立验证过：剔除离群后 p95 仍 12.43 m、x 轴均值 +3.39 m），但**没有定位方位误差的机制**（Worker 自述"需原始检测框，T1=0 取不到"）。这与 round-6 审查我给出的"误差几乎全在 x 轴且随时间恶化"是同一现象的两个侧面。

**结论**：视觉精度的病根**仍未定位**，这是 N1 的实质缺口，不是本轮调研该解决的。

## 三、本轮未达与保留

| 项 | 状态 | 说明 |
|---|---|---|
| GUI 证据 | **仍未取得** | 环境无 X display，Leader 已于 round-5/6 两次独立确认不可得。**环境限制，非授权问题** |
| 视觉精度病根 | **未定位** | 需原始检测框，属离线 T1 级工作（V2） |
| 失败率统计 | **未做** | 需 ≥10 次运行 ≈1,800 s T2（V1）；且 155603 探针缺 `pairing_chain`，须先统一探针 |
| 禁用 Figure8 整链验证 | **未做** | 需实施授权 + T2（V3） |
| 5 项用户裁定 | **待定** | U1–U5，见第四节 |

## 四、需用户裁定的 5 项（Leader 不代决）

| # | 事项 | 为什么必须用户定 |
|---|---|---|
| **U1** | `c_clear`（垂直净空下限）取多少 | 决定 `yard` + 目标平移形态是否可行（阈值 **0.35 m**）。本仓当前**无任何层守护垂直净空**，属新标定量 |
| **U2** | 是否接受"抬目标机 ⇒ 必须重标定网弹道" | 触 ADR-0011 包络口径（`applicable_max_alt_m=2.009` 由 `(v0sinθ)²/2g` 解出）。Leader 建议**不抬**，保持 2.0 |
| **U3** | `yard` 演示要不要"明显高于最高建筑" | 会撞 K1（`dz≈9 > 6.32`），需要同时抬目标机 + 重标定。**Leader 建议改相机视角/构图，不改飞行高度** |
| **U4** | 是否把"反无人机场景禁用预设轨迹"做成启动断言 | 会**拒绝运行**，影响既有流程验证场景写法 |
| **U5** | 是否采纳 `flight_altitude` 派生注入（地图文件 + `apply_flight_altitude` + 4 条断言） | 改 `w6_composition` + 三个地图文件，属实施授权 |

**Leader 对 U3 的额外意见**：用户说"当前高度太低了"，但本轮证明**工程上抬高反而降低感知能力**。若用户的诉求是"演示画面里飞机要高于楼"，那是**视觉构图问题**（相机视角、GUI 跟随距离），不该用飞行高度去凑。这一点请用户在裁定 U3 时明确区分：是要"看起来高"还是"工程上真需要更高"。

## 五、结论

- **本轮调研与定性任务：验收通过**，方法文档 `docs/conventions/飞行高度分层与按地图定高.md` 质量达标，可作为后续地图的复用规则。
- **N1 本身：不验收。** 仍有 GUI 证据、视觉精度病根、失败率三项实质缺口。
- round-8 的派工**取决于用户对 U1–U5 的裁定**；未裁定前不派实施轮。

## 六、证据

- [round-7 report](report.md#report)
- 主交付：`docs/conventions/飞行高度分层与按地图定高.md`
- 证据：`round-7/evidence/`（19 项 `sha256sum -c` 全 OK，一 run 一目录）
- 外部参考：`round-7/evidence/external-references.md`（14 源 + 检索记录）
- [round-6 review](../round-6/review.md#review)｜[round-5 review](../round-5/review.md#review)
