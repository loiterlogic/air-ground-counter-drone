<a id="current"></a>
# 当前交接

来源：Leader 于 2026-11-01 验收归档 G2、2026-11-02 验收归档 H0。用户要求按 N1、N2、N3 顺序推进；2026-11-02 用户另裁定：Leader 派工禁用 `subagent`，`task/` 及时归档，阻塞时结档并开新 Worker。本表由 Leader 独占写入。

- 状态：**两条独立链并行执行中（2026-11-04 18:10 派发）**
- 并行链（用户 2026-11-04 指示「互不影响的任务并行」）：

| 任务 ID | 内容 | 状态 | Worker 子会话 | 派工单 |
|---|---|---|---|---|
| `20261104-001-nadir-camera` | 机载正下视相机（结档 `plan/无人机俯视相机.md`） | 待执行 | `3f1b4d37-43c7-460b-b35c-3f54a96fef09` | [round-1](task/20261104-001-nadir-camera/round-1/request.md#request) |
| `20261104-002-target-motion-speed` | 目标运动规则 + 速度/节奏（结档两个 plan） | 待执行 | `1f2c928a-13a4-43a4-9eb7-6ec65ccf4f9d` | [round-1](task/20261104-002-target-motion-speed/round-1/request.md#request) |

- **并行边界**：独占资源 = 仿真/构建，用 `.coordination/locks/sim.lock`（flock）；
  `docs/adr/README.md` 由 `adr_index.py` 生成，两条链各自持 `.coordination/locks/docs.lock` 后再生成。
  文件白名单互斥（见各自派工单第六节）。
- N1 链（`20261102-002`）**暂停**：本轮不推进，但**不结档**，round-7 的结论与缺口仍有效。
- 上一轮：round-8 第 1、2 步已完成（火控修复 + 抬高度 + 地图派生注入），第 3 步（相机分工）
  已由 `20261104-001` 承接实施。

## 用户裁定（2026-11-02 晚，U1–U5 全部定案）

| # | 裁定 |
|---|---|
| U1 | `c_clear` 不单独定，**跟地图走**（写入各图 `flight_altitude.own_clearance_min_m`） |
| U2 | **抬**。目标 12 m / 己方 14 m，**且与地图绑定**（后续做小障碍高密度/大障碍低密度图） |
| U3 | **双相机分工**：测绘相机正俯视、跟踪相机前视（见规范 §7.1） |
| U4 | **要**做禁用预设轨迹的启动断言，但须配 `purpose: counter_uav\|regression` 豁免 |
| U5 | **采纳**，并进一步删除 `applicable_max_alt_m` 第二真源（改派生） |

裁定原文与依据见 [飞行高度分层与按地图定高](../docs/conventions/飞行高度分层与按地图定高.md#ruling-20261102)。

## round-8 进度

- **第 1 步（已完成，2026-11-02）**：火控修复，见 [ADR-0011](../docs/adr/0011-interception-and-fire-control.md#top)。
  - 交战门改为「预演弹道能命中才开火」（旧式在包络最外沿开火，余量仅 0.18 m / 抬高度后 0.08 m）；
  - 删除 `applicable_max_alt_m`，改由 `(v0·sinθ)²/(2g)` 派生（派生值 2.0092 == 旧硬编码 2.009）；
  - 单测 16/16 绿（新增 3 条门回归锚点）；`test_scene_config_invariants` 31/31；`w6_geometry_check` PASS。
- **第 2 步（已完成，2026-11-02）**：抬高度 + 地图派生注入，见 [ADR-0007](../docs/adr/0007-scene-geometry-single-source-and-layout.md#top)。
  - 三张地图新增 `flight_altitude` 五键块；`yard` 抬到**目标 12 / 己方 14 m**（净空 3.45 m），
    `minimal` / `open_field` **逐值不变**（历史基线不受影响）。
  - `apply_flight_altitude_params` / `_air` 派生注入 + **四条启动断言**（真实启动中 13→16 条全绿）。
  - 网弹道**条件派生**：仅当基线 apex 打不到该高度时重标定（yard → v0=15.81 / θ=85° / timeout=3.51 s）。
  - `air_hover_climb_m` 随起飞高度派生（否则起飞门永不满足）；`jam_envelope_max_alt_m` 只升不降。
  - **capture 场景 goal 必须偏离目标**：网是抛射体，车停在正下方必空（既有缺陷，非本次引入）。
    s08 的 `goal_x` 4.5 → 5.5（偏移 1.0 m，命中余量 0.49 m）。
  - H0 的「vision 平面必须 source=scene」按用户裁定改为 `{map, scene}`（`base` 仍拒绝）。
  - 验证：C++ 单测 16/16、场景不变量 37/37、`scripts/tests/` 358/358、`w6_geometry_check` PASS（三图）。
- **第 3 步（待做）**：相机分工（测绘相机正俯视）——见 [ADR-0007 未决节](../docs/adr/0007-scene-geometry-single-source-and-layout.md#top)。
- 最近结档：`20261102-001-h0-altitude-semantics`（H0 已验收；逐轮台账已于 2026-11-03 删除）

## round-7 成果（Leader 已验收）

- 主交付：`docs/conventions/飞行高度分层与按地图定高.md`（五层高度语义、反无人机场景禁用固定轨迹硬规则、按地图定高推导规则、三图建议值、复用清单）。
- 核心结论：**抬己方机反而降低感知**（K1 `|dz| ≤ 6.32 m`）；**两机同步等量抬升才感知中性**；`traj.height` / `takeoff_altitude_m` / `standoff_follower.height` 是三个**独立键**；**只有改 `traj.height` 才动 C1**。
- 反无人机场景的己方机参考来源 = `/agc/targets → standoff_follower → /agc/air/tracking_ref → trajectory_tracker`，禁用 Figure8 后兜底应换 `HoverTrajectory`。
- 口径纠正：`shield_infeasible_rate` 是**地面** `collision_monitor` 的 proxy_v1，**不是**空中安全层（Leader 已逐行核实 `run_logger.cpp:7-10,15-16,155-157,983-989`）。round-6 审查的"安全层不可行"表述失准，已在本轮记录更正。
- 外部依据 14 条（FAA / UK CAA / EU / CCAR-92 / PX4 / ArduPilot / AirSim），法规仅作量级参照、不构成合规声明。

## 待用户裁定（5 项，Leader 不代决）

| # | 事项 | 关键影响 |
|---|---|---|
| U1 | `c_clear`（垂直净空下限） | `yard` + 目标平移形态是否可行，阈值 **0.35 m** |
| U2 | 是否接受"抬目标机 ⇒ 重标定网弹道" | 触 ADR-0011；Leader 建议**不抬**，保持 2.0 |
| U3 | `yard` 演示要不要"明显高于最高建筑" | 撞 K1；Leader 建议**改相机视角/构图，不改飞行高度** |
| U4 | 是否把"反无人机禁用预设轨迹"做成启动断言 | 会拒绝运行 |
| U5 | 是否采纳 `flight_altitude` 派生注入 + 4 条断言 | 改 `w6_composition` + 三地图文件 |

## N1 仍缺口（未验收原因）

1. **GUI 证据 0 帧** —— 环境无 X display，Leader 已三次独立确认不可得（含无 root 解包 Xvfb 尝试），属环境限制。
2. **视觉精度病根未定位** —— 剔除离群后 p95 仍 12.43 m、x 轴均值 +3.39 m 且随时间恶化；round-7 用同一平面重算残余仍 p50 10.14 m → 方位（像素）侧也有问题，但机制未定位（需原始检测框，T1 级）。
3. **失败率未统计** —— 同配置同 seed 下 2 成功/1 失败，需 ≥10 次运行；且 155603 探针缺 `pairing_chain`，须先统一探针。

## 授权

- round-7 已结算：墙钟 2,729 / 7,200 s，**T1 = 0、T2 = 0**（未跑仿真）。
- round-8 额度待 U1–U5 裁定后另行授权。
- N1 完成前不启动 N2/N3。

## round-2 授权与裁定（Leader，2026-11-04 19:10）

两条链的 round-1 均**只完成 T0 调研、未写代码、未跑仿真**（被中断，非资源耗尽）。
Leader 已**逐条独立复算**其调研结论后原会话续派 round-2：

| 链 | 裁定要点 |
|---|---|
| `20261104-001` | pitch 取 **+1.5708**（Worker 推导正确，纠正了派工单）；§7.1 边缘 GSD **不改**（Leader 复算 `H·sec²θ/f`，35°→7.90 cm/px 与 §7.1 一致，Worker 该条不成立）；`gz_x500_mono_cam` **保留**；ADR 号维持 **0030** |
| `20261104-002` | `traj.speed` **不改**（`HoverTrajectory` 不读 `traj.*`，已核 `trajectory_generators.cpp:214-218`）；判据阈值**全不改**；选定 M2 `epicycle`；否决 M5 规避式（需订 `/agc/air/odom`，破坏确定性）；ADR 号维持 **0031** |

**Leader 自查纠正（如实记录）**：一度把两条链的 ADR 号改判为 `0108`，理由是 `0030/0031` 出现在"合并映射"表。
**该改判错了** —— 先例 `0028`/`0029` 同样是"活文件 + 出现在映射表"，故规则是
「活文件号 = 现有最大活文件号 + 1」，映射表是"旧号→新篇"查询表，二者并行不冲突。已回退为 0030/0031。

**资源**：两链 T1 各 1200 s、T2 分别为 3600 s / 5400 s，round-1 均 0 消耗。

## 20:39 机器重启与串行裁定（2026-11-04）

**用户裁定（20:32 原话）**：「他们的实验环境出问题了，让他们停下来，我重启一下电脑，
然后再让他们**先后跑**，不然环境太脏了」。

**根因（Leader 取证）**：`sim.lock` 只包住"启动命令"、未包住"整轮生命周期"；链 B 的 run 于 20:17
失败退出码 5（`gz sim` + 两个 `MicroXRCEAgent` 同时 -15，`collision_monitor` 心跳丢 4 s 触发
`lifecycle_manager` 关停），但锁未及时释放，链 A 干等 18 分钟。`/dev/shm` 累积到 **361 段**。
⇒ 详情与时间线：[STOP-20261104.md](STOP-20261104.md#stop)。

**重启后状态**：20:39 重启完成；`/dev/shm` **1 段**；仿真进程 0；`sim.lock` FREE；
`doctor` **14/14 PASS**；工作树 **660 项完整保留**（无代码丢失）。

**新执行规则（即日生效，两链共同遵守）**：

1. **严格串行**：同一时刻只允许一条链跑仿真/构建。现行顺序 = **A 链先跑完 → B 链再进 T2**。
2. **锁包整轮**：`flock -w 3600 <sim.lock> -c '<本轮全部 run>'`，不再逐条命令包锁。
3. **拿锁前残留自检**；发现非自己起的残留 → 停并报 Leader，**不得清理**。
4. **单次 run 必须硬超时，且跑后确认进程真退**（`ps` 为空、`/dev/shm` < 200）。

**当前链状态**：

| 任务 ID | 状态 | 说明 |
|---|---|---|
| `20261104-001-nadir-camera` | **已验收（2026-11-04 21:40 结档）** | A1–A8 全部达成，Leader 独立复验（12/12 pytest、索引 PASS、链接 PASS、亲验 `frame_004.png` 为地面、0 帧对照成立）。结论已归位 ADR-0030 / §7.1 / README 边界第 8 条 |
| `20261104-002-target-motion-speed` | **待返工（round-3 验收未通过，2026-11-04 22:20）** | T2 已完成（8 run，procs=0）：s18×3 全 TRACKING_SUCCESS、s08/s13 均 CAPTURE_NET、`RANGE_EXCEEDED` 根因已实测锁定（最长 dwell 段 2.884 s vs 阈值 3.0）。**返工仅限 3 处文档/可复现性，不需重跑仿真**：P1 ADR-0031:98「实测上界 1.063」无来源且与报告 max 1.525 矛盾（阻塞项）；P2 报告的 1.122/1.382/30.9% 不可复现、缺脚本；P3 A2 逐字节证明不可复核 |

## A 链结档（2026-11-04 21:40，Leader）

**验收通过**，审查见 [round-2 review](task/20261104-001-nadir-camera/round-2/review.md#review)。

- **交付**：opt-in 正下视相机 `gz_agc_x500_nadir`（复用已有 `px4_sim_model`，无新 launch 参数）；
  实测 144 帧 / 28.49 Hz、`fx=fy=268.60`（推导 268.51）、图像确为地面。
- **默认臂不变**：`gz_x500` 探针 **0 帧 / 45 s**，主场景仍 `TRACKING_SUCCESS`。
- **关键纠错**：SDF `pitch` 必须 **+1.5708**（−90° 会拍天空）；plan 与 §7.1 原写"−90° 俯角"是把
  **下俯量**当成了**字段值**，已在 ADR-0030 §3 写明并留纠错记录。
- **闸门**：`scripts/tests/test_nadir_camera_contract.py` 12 条，且用**变异测试**证明会真红
  （翻 pitch / 改话题名 / 删 `PX4_SYS_AUTOSTART` 各触发对应断言）。
- **未采纳**：`gz_x500_mono_cam` **保留不退休**（仍有 3 处白名单外引用）。
- **遗留（不阻塞）**：`/dev/shm` 每轮结束 184–200 段贴阈值 ⇒ 后续跑仿真前须先确认 < 200。

## 规则修正：`/dev/shm` 判据（Leader 自查，2026-11-04 21:55）

**原规则错了，现修正。** 我先前写的「`/dev/shm` 必须 < 200 段」是**过严且无依据**的：
它拦的是**段数**，而段数不预测启动失败。

实测（21:50）：

| 项 | 值 |
|---|---|
| 段数 | 200 |
| **实际占用** | **8.9 MB / 3.9 GB = 1%** |
| 被进程持有 | 10（含 `ros2 daemon` pid 3437） |
| 无人持有的陈旧段 | 104 |

`doctor.py:9` 自己写明「`WARN` 不影响退出码，但**必须**打印（例如 `/dev/shm` 段偏多——不阻塞）」，
`SHM_WARN_THRESHOLD = 200` 只是**提示线**，不是阻断线。真正的脏源是**孤儿仿真进程**，而它已为 0。

⇒ **修正后的判据**：`/dev/shm` **实际占用 < 50%** 且**无孤儿仿真进程** ⇒ 通过。
（段数只作记录，不作闸门。）

**这次是 Leader 定错规则，不是 Worker 执行不到位**；B 链按规则停下来报告的行为**正确**。

## B 链 round-3 审查（2026-11-04 22:20，Leader）

**结论：验收不通过 → `待返工`。** 审查见 [round-3 review](task/20261104-002-target-motion-speed/round-3/review.md#review)。

**已达成**：s18×3 `TRACKING_SUCCESS`（72.6/74.1/75.7 s，离散 4.3%）；s08/s13 均 `CAPTURE_NET`；
11 条 epicycle 单测绿；344 offline + 7/7 冒烟；索引 31 篇 PASS；两个 plan 已删；
`traj.speed` 未改；`/dev/shm` 169 段（1%）。

**核心成果（我逐行复核，数字完全吻合）**：`RANGE_EXCEEDED` 根因**从推断升级为实测**——
`dwell-s04b.jsonl` 15 次 `DWELL_START` / 14 次 `DWELL_INTERRUPT` 全为 `RANGE_EXCEEDED`，
最长段 **2.884 s**，距 `t_dwell=3.0` 仅差 **0.116 s**。⇒ `s04` TIMEOUT 根因已锁定。

**阻塞项 P1**：ADR-0031:98 写「实测上界 1.063」，但报告写 max **1.525**、p95 1.382。
我 `grep` 全仓「1.063」只命中该行本身，无脚本无数据；用 1 s 平滑复算得 max 1.193，仍非 1.063。
⇒ **该数字无来源，且方向是"让约束看起来被满足"**，必须删或改成有出处的值。

**返工范围仅 3 处**：P1 删/改该数字；P2 补 `analyze_traj.py` 使数字可复算；
P3 A2 改可判定形式（「无删除行」比哈希更硬）。**不需重跑仿真**（T2 剩 4217 s）。

## B 链 round-4 派工（2026-11-04 22:30，Leader）

**用户裁定（22:27 原话）**：「返工吧，顺便让它跑一下 GUI 我看看效果」。

⇒ round-4 范围 = **3 处文档返工 + 1 次 GUI 演示运行**，**不重跑 T2 的 8 个 run**（结论已成立）。

| # | 项 | 性质 |
|---|---|---|
| P1 | 删/改 ADR-0031:98「实测上界 1.063」（无来源、与报告 max 1.525 矛盾） | **阻塞** |
| P2 | 补 `analyze_traj.py` 使 median/p95/max/超限占比可一条命令复现 | 须补证 |
| P3 | A2 改「无删除行」可判定形式（比哈希更硬） | 须补证 |
| GUI | `./run_demo.sh --scene s18 --duration 200`（**真 GUI，非 headless**），≥3 张截图 + 终态证据 | 用户演示要求 |

**资源**：T2 剩 4217 s；GUI run 约 90–200 s。环境 procs=0、lock FREE、shm 169 段（1%）、`DISPLAY=:0` OK。
