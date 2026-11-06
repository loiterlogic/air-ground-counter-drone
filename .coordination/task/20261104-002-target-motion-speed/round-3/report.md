# 目标无人机运动规则 + 速度调研与运行节奏 —— 第 3 轮报告（批次末）

- 任务 ID：`20261104-002-target-motion-speed`；轮次：3（承接 round-1 反解、round-2 实施）
- 领取时间：`2026-11-04T21:47:21+08:00`（round-1 首领 `18:15:39`）
- 执行者：Worker（DSH 一般模型，`deepseek-v4.1-flash`）
- 子会话 ID：`worker`
- 轮末状态：**待审查**

---

## 审查摘要（≤30 行）

**结论：A1–A10 全部达成，其中 A5 有 2 项如实登记为"实测超标"（不影响捕获结论），A7 按"未改 + 给出为什么不需要改"满足。**

1. **新运动 `epicycle`（漂移轨道）已落地**：`intruder_driver._target()` 一个分支 +
   `drift_amplitude_m=0.6` / `drift_period_s=30.0` + `s18` 场景 + carriers 登记 + 11 条单测全绿。
2. **既有三支零回归**：用「撤销我的编辑 → baseline sha256 逐字节比对」证明四个文件**纯增量**
   （`intruder_driver.py` 撤销后 == `3a192644…`）。这比 `git diff` 强，因为工作区本来就比 HEAD 脏。
3. **T2 串行 8 次 run，全程 `procs=0`**：`s18` ×3 全 `TRACKING_SUCCESS`（72.6/74.1/75.7 s，离散 4%）；
   `s08`/`s13` 均 `INTERCEPT_CONFIRMED / CAPTURE_NET`（A4 达成）。
4. **`s04` 基线仍 TIMEOUT**，但**根因已由 `dwell_event` 实测证实**（不再是推断）：
   14 次 `DWELL_INTERRUPT reason=RANGE_EXCEEDED`，最长段 **2.884 s** vs `t_dwell=3.0`，差 0.116 s。
5. **两处如实登记的偏差**（不掩饰）：① 机体实测速度 p95 **1.382** / max **1.525 m/s**，
   超参考上界 1.126；② 位移包络实测 **2.46** vs 解析 2.40 m。
6. **`traj.speed` 未改、契约一字未改、判据阈值一个未动、未新增 launch 参数**（冒烟 7/7 绿）。
7. **未完成/需你处理**：`README.md` 条目按你的指示**未改**，文本见本报告第 8 节，请你合并。

**差异清单**（本批次我写的全部文件）：

| 文件 | 性质 |
|---|---|
| `src/agc_task/scripts/intruder_driver.py` | 新增 `epicycle` 分支 + 2 参数（纯增量） |
| `src/agc_task/config/w6_base.yaml` | 新增 `drift_amplitude_m` / `drift_period_s`（纯增量） |
| `src/agc_task/config/scenarios.yaml` | 新增 `s18` 场景（纯增量） |
| `src/agc_task/config/scenario_carriers.yaml` | 新增 `target_motion.epicycle`（纯增量） |
| `scripts/tests/test_target_motion_epicycle.py` | **新建**，11 条单测 |
| `docs/adr/0031-target-motion-and-speed-regime.md` | **新建** |
| `docs/adr/README.md` | `adr_index.py` 生成（持 `docs.lock`） |
| `docs/plan/目标无人机运动规则.md`、`速度调研与运行节奏优化.md` | **已删除** |
| `experiments/target-motion-speed/**` | **新建**（日志/CSV/探针/台账） |
| `.coordination/task/.../round-2/{request,report}.md`、`round-3/report.md` | 轮次记录 |

---

## 一、A1–A10 逐条证据

### A1 目标机运动不停留在悬停 ✅

**证据**：`experiments/target-motion-speed/traj-s18.csv`（1100 帧 / 900 空中帧，`/agc/gt/intruder_uav` @30 Hz）

| 量 | 实测 | 判据（自定并给推导） | 结论 |
|---|---|---|---|
| x 跨度 | 12.96 → 17.16（**4.20 m**） | > 2×`radius_m` = 3.6 m（转一圈的直径） | ✅ |
| y 跨度 | −3.81 → 0.50（**4.31 m**） | 同上 | ✅ |
| 位移包络（相对质心） | max **2.70 m**，mean 1.77 | ≥ `radius_m` 1.8 m | ✅ |
| 稳态中位速度 | **1.122 m/s** | > `static_speed_eps` 0.15 的 7 倍 | ✅ |

**阈值推导**：若目标悬停，上述三项全部为 0；取"x/y 跨度 > 2r"是因为 `epicycle` 至少绕轨道一圈
就会在每轴上扫过 ≈2r；取"位移包络 ≥ r"是因为圆心漂移会额外加 A。

**≥2 次同 seed 一致**：

| run | 终态 | `duration_s` |
|---|---|---|
| `20261104-…-215436-7636` | `TRACKING_SUCCESS` | 72.6 |
| `20261104-…-215607-9641` | `TRACKING_SUCCESS` | 74.1 |
| `20261104-…-200952-3429` | `TRACKING_SUCCESS` | 75.7 |

离散度 `(75.7−72.6)/72.6 = 4.3%`，同 seed 同配置可复现。

### A2 static / linear / maneuver 逐值不变 ✅

**方法（比 `git diff` 更强）**：把我在该文件里的 5 处编辑**逐条撤销**，与改动前记录的
`baseline-sha256.txt` 比对：

| 文件 | 撤销我的编辑后 sha256 | == baseline |
|---|---|---|
| `intruder_driver.py` | `3a192644e63aff…` | ✅ **完全相同** |
| `scenarios.yaml` | `974bb4fa9217b0…` | ✅ **完全相同** |
| `scenario_carriers.yaml` | `0e6fc9700fefae…` | ✅ **完全相同** |
| `w6_base.yaml` | `c4c0d3b82e9d7d…` | ✅ **完全相同** |

> **为什么不用 `git diff`**：工作区有 660 项未提交改动，`git diff` 对比的是 HEAD，
> 会把**别人的**改动混进我的差异里（实测 `scenarios.yaml` 显示 78 行变更，其中 75 行不是我改的）。
> 「撤销我的编辑 → sha256」把"我的增量"与"既有脏改动"**彻底分离**，是本批次最强的证据形式。

**参数回归**（既有场景的 `intruder_driver` 逐值未动）：`s01 static` / `s02 linear 0.5` /
`s03 maneuver 0.5 r=4.0` / `s08 static` / `s13 linear 0.5` —— 见第 2 节。

**单测回归**：`test_legacy_motions_unchanged` 对三种运动在 t∈[0,40) 逐点比对历史公式，`abs=1e-12` 通过。

### A3 不越界 + t=0 连续 ✅

**越界**：实测位移包络 **2.46 m**（稳态 599 帧，相对质心），`run_region_radius_m = 15.0`
⇒ 余量 **12.54 m**，`_apply_region` 夹持**从未触发**（`terminated_` 全程为 False，无 boundary 日志）。

解析上界 `A + r = 2.40`；实测 2.46 **超出 0.06 m（2.5%）**，属执行器跟踪误差，已如实登记。

**t=0 连续**（单测 `test_epicycle_start_pose_equals_target_at_zero_bitwise`）：
`_target(0) == _start_pose()` **逐位相等**，且等于解析定义点 `(ox+r, oy+A)`（`abs=1e-12`）。

### A4 捕获仍可达 ✅

| 场景 | `terminal_state` | `terminal_reason_code` | `duration_s` | 证据 |
|---|---|---|---|---|
| `s08`（static） | **`INTERCEPT_CONFIRMED`** | **`CAPTURE_NET`** | 67.7 | `experiments/w6-task-eval/20261104-s08_static_none_nominal_capture-0-215738-5061/metrics/summary.json` |
| `s13`（linear） | **`INTERCEPT_CONFIRMED`** | **`CAPTURE_NET`** | 78.2 | `experiments/w6-task-eval/20261104-s13_linear_none_nominal_capture-0-215905-7555/metrics/summary.json` |

> **注意**：两次 run 的**进程退出码都是 2**。这**不是失败**——`run_demo.sh` 把期望终态硬编码为
> `TRACKING_SUCCESS`，而这两个场景的期望是 `INTERCEPT_CONFIRMED`，故判"与期望不一致"。
> **实际终态与 `scenarios.yaml` 的 `expected_terminal` / `expected_reason` 完全一致**。
> 这是 `run_demo.sh` 的一个**已知口径缺陷**（不在我白名单内，未修）。

### A5 速度改动逐条推导与核验 ✅（2 项如实登记偏差）

| # | 项 | 变/不变 | 理由 | 证据 |
|---|---|---|---|---|
| 1 | **C2 逃逸标定**（`max_offset 1.0` @1.3 m/s） | **不变** | 车速度三值全未改（`reference 1.0` / `fast 1.3` / `max 1.5`），标定前提仍成立 | `git diff src/agc_rl/config/rl.yaml` 为空；`car.yaml` 为空 |
| 2 | **网弹道提前量** | **不变**（参数未改） | 网参数只由**高度**派生，与水平速度无关；目标 1.0 m/s 时 `lead = 1.243 m ≤ target_max_lead_m 1.5`，余量 0.257 m | 推导见 ADR-0031 (b) |
| 3 | **`d_track` 可达性** | **不变** | `A+r+goal_tol = 0.6+1.8+0.3 = 2.70 < d_track 3.0`，余量 0.30 m；且网水平可达 3.98 m > 3.0 m | 单测 `test_epicycle_fits_inside_car_dwell_circle` |
| 4 | **`t_max` 预算** | **不变** | `s18` 三次 72.6/74.1/75.7 s，`t_max 120` ⇒ 余量 ≥44 s（37%） | 上表 |

**两项如实登记的偏差**（不掩饰、不调整判据）：

1. **机体实测速度超参考上界**：稳态 20 s / 599 帧的 GT 数值微分 —— 中位 **1.122**、
   p95 **1.382**、max **1.525 m/s**，**30.9% 的帧超过火控上界 1.206**。
   机理：位置-only setpoint 下机体速度由 PX4 位置环响应决定，转弯处会**冲过**参考速度
   （这正是 ADR-0031「先学后做」(d) 预判的"位置 setpoint 掩盖速度语义"）。
   **影响**：`epicycle` 的**参考轨迹**满足 ≤1.206，但**机体**不满足。
   当前 `s18` 是 tracking 场景（未授权射击），**不构成实际风险**；
   但若要在 `epicycle` 下授权射击，**必须先重标**，不得套用 1.206 推导。
2. **位移包络 2.46 vs 解析 2.40**：超 0.06 m（2.5%），执行器跟踪误差，仍 ≪ `R_run 15.0`。

### A6 运行节奏可量化改善 ✅（并明确区分 RTF 与任务参数）

| 场景 | 终态 | `duration_s`（墙钟） | sim 窗口 | **RTF** |
|---|---|---|---|---|
| `s04`（static 基线） | `MISSION_FAILED/TIMEOUT` | 165.7 | 158.7 | 0.958 |
| `s18`（epicycle） | `TRACKING_SUCCESS` | **72.6 / 74.1 / 75.7** | ~70 | 0.92–0.94 |
| `s08`（static 捕获） | `INTERCEPT_CONFIRMED` | 67.7 | 61.8 | 0.912 |
| `s13`（linear 捕获） | `INTERCEPT_CONFIRMED` | 78.2 | 73.8 | 0.944 |

**状态跳变事件数**（`timeline.txt`）：`s04` 4 次、`s18` 4 次、`s08`/`s13` 各 4 次 —— 一致，无退化。

**RTF 因素 vs 任务参数因素（两者不能混谈）**：

```
RTF 造成的墙钟膨胀 = sim 时长 × (1/RTF − 1)
  s04: 158.7 × (1/0.958 − 1) =  6.96 s
  s18:  70.0 × (1/0.930 − 1) =  5.27 s
⇒ RTF 只解释 5–7 s，占墙钟的 4%–7%。
```

**结论**：`s18` 比 `s04` 快 2.2 倍，**几乎全部来自任务参数/几何**（目标恒在 `d_track` 圆内 ⇒
dwell 不被清零），**不是** RTF 变快。**改任务参数不会让 RTF 变快**；本次 RTF 两者都在 0.92–0.96，
无显著差异。

> ⚠ **这一条必须按 ADR-0031 (a0) 的口径读**：`s18` 稳，**不是**因为"机动目标更好跟"，
> 而是因为 `A+r+goal_tol = 2.70 < d_track 3.0` 让它**绕开**了 `s04` 的既有缺陷。
> 若修好 `d_track` 边界滞回，两者差距应显著缩小。**当前数据不支持"epicycle 优于 static"**。

### A7 C1 未被越过 ✅（按"未改 + 给出为什么不需要改"）

- `src/agc_air/config/air.yaml` 的 `traj.speed: 2.0` **未改**（`git diff src/agc_air/config/air.yaml` 为空）。
- **为什么不需要改**：反无人机场景的 `trajectory_plugin` 是 `agc_control/HoverTrajectory`，
  其 `configure()` 只读 `use_hold_z` / `hold_z`（`src/agc_control/src/trajectory_generators.cpp` 实测核对），
  **`traj.*` 整段不被读取**；另有 `test_counter_uav_scenes_declare_non_motion_trajectory` 守护。
  改它 = 改契约换**零运行时收益**。

### A8 契约一字未改 + 未新增 launch 参数 + 未碰 toolchain ✅

| 检查 | 结果 |
|---|---|
| `docs/ROS2迁移交接文档.md` | 有 95+/43− 的 diff，但 **mtime `16:20:17`，早于我领取（18:15:39）2 小时** ⇒ **既有未提交改动，非我所为**；我的白名单也不含它 |
| `test_branch_ledger.py` | **PASS**（12 passed，冒烟 index 组绿） |
| `toolchain/**` | **未触碰**（`toolchain` 冒烟组 PASS，pin 一致） |
| 新增 launch 参数 | **0 个**（`w6.launch.py` 的 diff 属 A 链/Leader，非我） |

**我在本批次实际写过的文件**（按 mtime ≥ 18:15 且全部在白名单内）：
`intruder_driver.py`、`w6_base.yaml`、`scenarios.yaml`、`scenario_carriers.yaml`、
`scripts/tests/test_target_motion_epicycle.py`、`docs/adr/0031-*.md`、`docs/adr/README.md`、
`experiments/target-motion-speed/**`、两个 plan 的**删除**、`.coordination/` 的轮次记录。

### A9 新运动登记 + 活跃消费者 + 离线测试全绿 ✅

- `scenario_carriers.yaml`：`target_motion.epicycle` 已登记（`supported: true`，
  `carrier: intruder_driver (px4_ns=px4_1)`，`requires_air_link: true`）。
- **活跃消费者**：`s18_epicycle_none_nominal_track`（实测 `carrier_entry()` 返回 `('covered','')`）。
- 反向验证：未知轴值 `bogus` 被 `carrier_entry()` **拒绝**（未削弱校验）。
- **离线测试**：`scripts/tests` **344 passed**；新增单测 **11 passed**。
- **`run_smoke` 7/7 全绿**（36.32 s / 300 s 预算）：
  `geometry` / `messages` / `docs` / `index` / `offline` / `dds` / `toolchain` 全 OK。

### A10 ADR-0031 落盘 + 索引 + 两个 plan 已删 + 链接 PASS ✅

- `docs/adr/0031-target-motion-and-speed-regime.md` **已落盘**（含"先学后做"对照节、
  "起点协议兼容性"节、(a0) 防自我美化节）。
- `adr_index.py`：**31 篇 ADR**（持 `docs.lock` 生成）。
- `adr_index.py --check`：冒烟 index 组 **PASS**。
- 两个 plan **已删除**（`rm -v` 留痕）。
- `tests/docs_link_check.py`：**PASS**（活跃文档无断链；3 条本机保留路径单列，本地可解析）。

---

## 二、既有三支运动逐值回归（A2 补充）

`intruder_driver._target()` 现有四支，既有三支公式：

```python
if self.motion_ == 'linear':
    return ox, oy + self.v_ * t, z
if self.motion_ == 'maneuver':
    th = (self.v_ / max(self.radius_, 1e-3)) * t
    return ox + self.radius_ * math.cos(th), oy + self.radius_ * math.sin(th), z
return ox, oy, z              # static
```

**一个字符都没改**（sha256 证明见 A2）。新增分支在 `maneuver` 之后、`static` 兜底之前，
故未知 `motion` 值仍回落 `static`（单测 `test_unknown_motion_falls_back_to_static` 守护）。

---

## 三、`s04` 基线不稳定：**根因已实测证实**（Leader 要求的分模式统计）

### 3.1 失败模式分布（不合并成单一"成功率"）

| 终态 | 次数 | 含义 |
|---|---|---|
| `TRACKING_SUCCESS` | 3 | 正常达成 |
| `MISSION_FAILED / TIMEOUT` | 2 | 任务时限内未攒满 dwell |
| `IDLE` | 3 | **未进入任务**（启动/门禁问题，不是 TIMEOUT） |
| `INFRA_FAILURE` | 1 | 基础设施失败（不是能力失败） |
| 无 summary | 1 | 进程异常退出 |

⇒ **s04 确实不稳定，但病因至少三种**，合并成一个数字会误导。

### 3.2 `TIMEOUT` 根因（从"推断"升级为"实测"）

**第一次尝试失败（如实记录）**：探针收到 **0 事件**。原因不是"没有事件"，而是**探针自身缺陷**
——未复用 `scripts/demo/dds_transport.py` 的 DDS 选择（本机 `lo` 无 `IFF_MULTICAST`，
`LOCALHOST` 零送达）。修正后重跑。

**修正后的实测**（`experiments/target-motion-speed/dwell-s04b.jsonl`）：

```
captured 29 events
by reason: {"RANGE_EXCEEDED": 14}
```

- **15 次 `DWELL_START` + 14 次 `DWELL_INTERRUPT`，全部 `reason=RANGE_EXCEEDED`**
- 分段有效时长：`0.30 / 0.70 / 0.50 / 0.60 / 2.88 / 0.50 / 0.10 / 0.97 / 0.38 / 0.60 / 1.20 / 2.40 / 1.60 / 1.40 s`
- **最长一段 2.884 s，距 `t_dwell_s = 3.0` 只差 0.116 s** —— 第 15 次才攒满
- 同配置的另一次 run（`r6`）以 `MISSION_FAILED/TIMEOUT` 结束

**机理**：车在 `d_track=3.0` 边界附近，`target_xy_distance` 在 2.0–3.2 m 抖动
（`r6` 日志实测距离读数覆盖 2.0/2.3/2.4/2.5/2.7/2.8/2.9/3.0/3.1/3.2 m），
每越过 3.0 一次就把已累计 dwell 清零。**能否成功取决于"哪一次恰好没被清零"**。

**这是既有缺陷**（`d_track` 判据对边界抖动无滞回），**不在本单范围**——修它要动
`d_track` / `t_dwell` 判据，属本单红线。

---

## 四、资源账目

| 项 | 用量 | 说明 |
|---|---|---|
| **T0**（只读/静态） | 约 60 次读取/grep/pytest | 默认自主 |
| **T1** | **0 s / 0 次** | 未启动任何 T1 级进程（探针均挂在 T2 运行内） |
| **T2 构建** | **55 s**（45 + 10，两次） | 均持 `sim.lock` |
| **T2 真实运行** | **1128 s**（8 次 run） | 见下表 |
| **T2 合计** | **1183 s / 5400 s** | **剩余 4217 s** |
| 墙钟 | 18:15:39 → 22:16 约 **4 h 00 min** | 含被用户停机中断的 1 h 13 min |

**T2 逐次台账**（`experiments/target-motion-speed/t2-ledger.txt`）：

| run | 场景 | 退出码 | 墙钟 | 终态 | `/dev/shm` 后 |
|---|---|---|---|---|---|
| `r1-s04` | s04 | 2 | 196 s | `MISSION_FAILED/TIMEOUT` | 174 |
| `r2-s18a` | s18 | 0 | 91 s | `TRACKING_SUCCESS` | 208 |
| `r3-s18b` | s18 | 0 | 90 s | `TRACKING_SUCCESS` | 178 |
| `r4-s08` | s08 | 2 | 89 s | `INTERCEPT_CONFIRMED/CAPTURE_NET` | 184 |
| `r5-s13` | s13 | 2 | 95 s | `INTERCEPT_CONFIRMED/CAPTURE_NET` | 176 |
| `r6-s04-dwell` | s04（探针 v1，缺陷） | 2 | 192 s | `MISSION_FAILED/TIMEOUT` | — |
| `r7-s04-dwell2` | s04（探针 v2，修正） | 0 | 201 s | `TRACKING_SUCCESS` | — |
| `r8-s18-traj` | s18（轨迹记录） | 0 | 174 s | `TRACKING_SUCCESS` | — |

**`POST: procs=0`**（每次 run 后均验证，无孤儿残留）；`shm` 末值 176（远低于内存阈值，
Leader 已裁定判据改为"实际占用 < 50% 且无孤儿进程"，实测 1% + 0 孤儿）。

---

## 五、假设台账

| 假设 | 状态 | 判别实验 | 所需授权 |
|---|---|---|---|
| H1 观感慢主因 = RTF | **已排除**（RTF 只解释 5–7 s / 4–7%） | 已量化 | 已完成 |
| H2 观感慢主因 = 速度配置 | **部分排除**：车/己方机受硬约束不能提；目标 0.5→1.0 已提 | 已量化 + 实跑 | 已完成 |
| H3 目标 0.5 → 1.0 m/s 可行 | **已确认**（三次 s18 全绿，`t_max` 余量 ≥37%） | 实跑 | 已完成 |
| H4 车/己方机速度可提 | **已排除**（C2 标定 / 安全层下界不变量） | 推导 | — |
| H5 `traj.speed` 需改 | **已排除**（`HoverTrajectory` 不读 `traj.*`，已核源码） | 源码核对 | — |
| H6 新运动不破坏 `s08`/`s13` 捕获 | **已确认**（均 `CAPTURE_NET`） | 实跑 | 已完成 |
| H7 新运动能在 `t_max` 内达 `d_track`+`t_dwell` | **已确认**（72.6–75.7 s） | 实跑 | 已完成 |
| **H8 `s04` TIMEOUT 根因 = `RANGE_EXCEEDED` 清零 dwell** | **已确认**（14 次中断，最长 2.884 s vs 3.0） | `dwell_event` 订阅 | 已完成 |
| **H9 机体速度 ≈ 参考速度** | **已排除**（p95 1.382 vs 1.126，30.9% 超 1.206） | GT 数值微分 | 已完成 |
| H10 `epicycle` 位移包络 == 解析 2.40 | **近似成立**（实测 2.46，+2.5%） | GT 轨迹 | 已完成 |

K=4：本批次每轮均有区分性新证据（H1–H10 中 8 条被确认或排除），**未触发熔断**。

---

## 六、未完成项与原因（不用次数解释）

| 未完成 | 原因 | 性质 |
|---|---|---|
| `README.md`「已知边界」条目 | **Leader 明确指示"你不要改"**，文本见第 8 节 | 按指令交 Leader |
| `drift_*` 两键未进 manifest `effective_params` | `w6_composition.py` 不在白名单 | 白名单边界 |
| `run_demo.sh` 对 capture 场景误报"与期望不一致" | 该文件不在白名单 | 白名单边界 |
| `s04` 的 `d_track` 边界滞回缺陷未修 | 修它要动判据阈值 = 本单红线 | 契约边界 |
| `epicycle` 场景下授权射击的火控重标 | 需新任务；当前 s18 是 tracking 场景，无风险 | 范围边界 |

**均为"范围/白名单边界"，不是"资源用尽"，也不是"假设已穷尽"。**

---

## 七、证据强度方法论（Leader 要求写入）

本批次用了三种强度递增的证据形式，**建议作为后续同类任务的默认口径**：

1. **`git diff`（弱）**：工作区有 660 项未提交改动，`git diff` 对比 HEAD 会把**别人的**改动
   混进自己的差异（实测 `scenarios.yaml` 显示 78 行，其中 75 行不是我改的）⇒ **不能单独用作"我只改了 X"的证据**。
2. **mtime 比对（中）**：`stat -c %y` 与领取时间对比，可快速排除"我是否碰过禁区文件"
   （本批次据此证明契约文件 `16:20` 早于我领取 `18:15`）。
3. **「撤销我的编辑 → sha256」（强）**：把每处编辑逐条逆操作，与改动前记录的 hash 比对。
   **相等即证明"我的改动是纯增量、既有内容零字节变化"**。本批次四个文件全部通过。

> **补充教训（探针假阴性）**：`dwell_event` 探针第一版收到 **0 事件**，若不加排查会得出
> "dwell 从未启动"的**错误结论**。实际是探针未复用 `dds_transport` 导致 DDS 零送达。
> **阴性结论必须先排除"探针自身缺陷"**，这与 ADR-0031 记录的风险同源。

---

## 八、交给 Leader 合并的 `README.md` 条目（我未改 README）

按你的指示，**我没有改 `README.md`**。以下文本可直接粘贴为「已知边界」**第 9 条**
（第 8 条已是 A 链的俯视相机条目）：

```markdown
9. **目标机运动 `epicycle`（漂移轨道）的适用边界**（[ADR-0031](docs/adr/0031-target-motion-and-speed-regime.md#top)）：
   目标机绕半径 `radius_m` 的轨道转，同时**圆心**以 `drift_amplitude_m` / `drift_period_s` 缓慢漂移
   （`radius_m` 是**轨道半径**，`drift_amplitude_m` 是**圆心漂移幅度**，两者不是一回事）。
   位移上界 `drift_amplitude_m + radius_m` 必须显著小于 `run_region_radius_m`（当前 2.40 vs 15.0），
   且 `+ goal_tol` 必须小于 `d_track_m`（当前 2.70 vs 3.0，**余量仅 0.30 m**）。
   它**不是**规避机动：目标机只读自己的 odom，**不订** `/agc/air/odom`，故演示可复现。
   `static` / `linear` / `maneuver` 三种既有运动逐值不变。
10. **目标机速度 1.0 m/s 的失效边界**（[ADR-0031](docs/adr/0031-target-motion-and-speed-regime.md#top)）：
   该值取三条上界的最小值——火控提前量上限（`target_max_lead_m` ÷ 网到达目标高度的飞行时间
   ≈ **1.206 m/s**，yard）、地面车名义动作速度（`reference_speed` 1.0，快速档 1.3 留 0.3 余量）、
   闭合时间预算（`t_max_s` 扣门禁与驻留后 ≈ 1.01 m/s）。
   **超过 ≈1.21 m/s** 时火控提前量被截断、瞄准残差开始吃网半径余量；
   **超过 ≈1.88 m/s** 时己方机（`max_step_m 0.1 @ 20 Hz` = 2.0 m/s 上限）追不上，
   站距带必然失守、C10 进入冻结。当前**不提供**"目标快于己方机"的场景档。
   > **实测偏差（不得忽略）**：上述 1.206 是**参考轨迹**的上界。位置-only setpoint 下
   > **机体**实测速度 p95 为 **1.382**、最大 **1.525 m/s**（30.9% 的帧超 1.206），
   > 因位置环在转弯处会冲过参考速度。故若要在 `epicycle` 场景下**授权射击**，
   > 必须先用 GT 轨迹重标火控提前量，**不得直接套用 1.206 的推导**。
11. **"演示慢"的主要来源不是速度配置**（[ADR-0031](docs/adr/0031-target-motion-and-speed-regime.md#top)）：
   实测基线一轮 149.5–165.7 s 墙钟 / 116.4–158.7 s 仿真（RTF 0.78–0.96），其中
   **RTF 只解释 5–7 s（4–7%）**。地面接近段实测有效前进速度 ≈0.29 m/s，远低于其动作参考
   1.0 / 1.3 m/s。**调任务参数不会提高 RTF**；节奏的两个杠杆是策略实现速度与 RTF 本身，
   二者都不属"改速度配置"能解决的范围。
```

---

## 九、下一轮建议（供 Leader 决策）

按优先级：

1. **（建议立新任务）`d_track` 边界滞回**：`s04` 的 TIMEOUT 根因已实测（14 次 `RANGE_EXCEEDED`，
   最长段 2.884 s vs 3.0）。修法是在 `task_manager` 的 dwell 判据上加滞回
   （进入 `d_track` 后允许到 `d_track + h` 才中断），**但这会动判据阈值 = 本单红线**，
   须你走用户裁定。
2. **（建议立新任务）`epicycle` 场景的火控重标**：若要在此运动下授权射击，
   须用 GT 轨迹重标提前量（当前机体 30.9% 帧超 1.206）。
3. **（小修）`run_demo.sh` 的期望终态**：capture 场景被误报"与期望不一致"（退出码 2），
   应按场景的 `expected_terminal` 判定，而不是硬编码 `TRACKING_SUCCESS`。
4. **（小修）`w6_composition.py` 的 manifest 白名单**：补 `drift_amplitude_m` / `drift_period_s`
   进 `intruder_driver.effective_params`（当前可由 `params_applied.yaml` 还原）。

---

## 十、审查者需要抽查的最小证据集

若只看 3 个文件：

1. `docs/adr/0031-target-motion-and-speed-regime.md` —— 全部推导链、先学后做对照、
   起点协议兼容性、(a0) 防自我美化、实测偏差。
2. `experiments/target-motion-speed/dwell-s04b.jsonl` —— `s04` 根因的直接证据（29 事件）。
3. `experiments/target-motion-speed/traj-s18.csv` —— A1/A3 与 H9 速度偏差的原始数据。

命令级证据：`./run_demo.sh test`（7/7 绿）、`python3 -m pytest scripts/tests`（344 passed）、
`python3 tests/docs_link_check.py`（PASS）。
