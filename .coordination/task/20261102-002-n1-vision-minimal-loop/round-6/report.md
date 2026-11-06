<a id="report"></a>
# N1 · round-6 GUI 证据与检测指标补证 — Worker 报告

- 任务 ID：`20261102-002-n1-vision-minimal-loop`；轮次：6
- **领取时间**：`2026-11-02T16:15:00+08:00`（Asia/Shanghai）
- **执行者**：`worker`（沿用 round-5 同一会话返工）
- **子会话 ID**：`18d8e00b-995d-413c-93a5-21e5418e2ab2`
- **预算起点**：本轮为用户新授权——总墙钟 **7,200 s**（自 `16:15:00` 起算，截止约 `18:15:00`）；T2 **3,600 s**（单次 ≤900 s）；T1 **0**；静态/离线 **600 s**（单次 ≤30 s）
- **状态**：`阻塞`（仅 A 项：X UNAVAILABLE；B / C 已完成）

## 审查摘要

1. **A（GUI 证据）＝ 阻塞**。开工第一步前置检查即 `X UNAVAILABLE`（16:15:20），按派工单要求立即停，**未**尝试 headless 代替、**未**尝试安装 X server、**未**绕路。原文三条命令输出见 [evidence/gui-feasibility.txt](evidence/gui-feasibility.txt)。
2. **B（检测指标）＝ 完成，且结果对本实现不利，如实报告**：`precision = 0.238`、3D 误差 `p50 = 3.46 m / p95 = 16.31 m`（全样本）、延迟 `p50 = 16.0 ms / p95 = 24.0 ms`。**这不是"指标达标"，是两个真实缺陷的量化**（见 §三）。
3. **C（`detector_backend` 入 summary）＝ 完成**：实跑 summary 出现 `detector_backend: "synthetic_color"`，truth 模式写 `none`，3 个守护测试通过，既有字段零变化。
4. **两个新发现的真实缺陷**（round-5 未暴露，本轮量化）：
   - **任务初期射线杠杆效应**：目标贴近平面法线、相机-目标连线几乎垂直于平面时，`t=(z_plane−p_z)/b_w.z` 的分母趋零 → 交点在数百米外（实测最远 **414 m**，`y=274` 而目标在 `y=−2`）。`precision`、3D 误差被这一小撮极端值主导。
   - **目标实际高度并不在 `plane_z`**：GT `z` 在 t=0–40 s 是 `−0.02`（**地面**）、t>40 s 在 `0.90–1.62` 波动，`|dz|<=0.10 m` 的样本仅占 **3%–5%**。故"单平面 `z=2.0`"假设在**本 run 的绝大部分时长里不成立**。
5. **这两条直接推翻了 round-5 报告里"链路已打通、指标待补"的隐含乐观**：链路确实是通的（`TRACKING_SUCCESS`、`TARGET_FRESH`），但**三维精度远未可用**。

## 一、A · GUI 证据 —— `阻塞`

**执行时间** `2026-11-02T16:15:20+08:00`，原文（完整见 [evidence/gui-feasibility.txt](evidence/gui-feasibility.txt)）：

```text
$ ls -A /mnt/wslg/.X11-unix
(空输出，exit=0；无 socket)

$ ls -A /tmp/.X11-unix
(空输出，exit=0；无 socket)

$ command -v xdpyinfo && xdpyinfo -display :0 >/dev/null 2>&1 && echo "X OK" || echo "X UNAVAILABLE"
/usr/bin/xdpyinfo
X UNAVAILABLE

# 补充（变量存在 != 能连上）
DISPLAY=[:0]

# 补充：X server 进程
(无 Xorg / Xwayland / Xvfb 进程)
```

**判定 `X UNAVAILABLE` → 按 §一/A 立即停。** 未产出任何 GUI 原始帧；帧数 = 0，采集退出码 = 不适用（未启动采集）。

Leader 已独立验证过该环境不可得（`apt-get download xvfb` + `dpkg-deb -x` 无 root 解包后，Xvfb 内部硬编码 `/usr/bin/xkbcomp` 越不过；`unshare -r -m` 亦不行）。本轮不再重复尝试。

## 二、C · `detector_backend` 入 summary —— 完成

### 差异（**仅新增键**，Leader 授权范围内）

| 文件 | 改动 |
|---|---|
| `src/agc_task/src/run_logger.cpp` | ① 新增参数声明 `detector_backend_ = declare_parameter<std::string>("detector_backend", "none");`（第 126 行）；② summary.json 新增一行 `"detector_backend": "<值>",`（第 392 行，紧随 `vision_model` 之后）；③ 新增成员 `std::string detector_backend_;`（第 1390 行）。**未触碰** `perception_path` / `vision_model*` / 终态 / 安全 / 评估逻辑任何一行。 |
| `src/agc_task/launch/w6.launch.py` | 给 `run_logger` 的 `extra` 参数追加 `'detector_backend': (detector_backend if perception_path == 'vision' else 'none')`。truth 路径恒 `none`。 |
| `scripts/tests/test_n1_run_logger_backend.py`（**新增**） | 3 个守护测试 |

### 实测（真实 vision run，`20261102-s02_linear_none_nominal_track-0-161832-2961`）

```json
"perception_path": "vision",
"vision_model": {"id": "none", "name": "", "version": "", "sha256": ""},
"detector_backend": "synthetic_color",
"terminal_state": "TRACKING_SUCCESS"
```

→ 现在**单看 summary 就能区分**"`synthetic_color` 视觉后端"与"truth 真值链"，满足契约 `#perception-path` 的"证据必须可区分"。

### 守护测试（3 个，全通过）

| 测试 | 断言 |
|---|---|
| `test_detector_backend_defaults_to_none` | 不传参 → summary 写 `none` |
| `test_detector_backend_records_synthetic_color` | 传 `synthetic_color` → 如实记录 |
| `test_detector_backend_is_label_only` | 逐键比较两次运行（仅后端不同）：`perception_path`/`terminal_state`/`terminal_reason_code`/`vision_model`/`seed`/`scenario`/`shield_infeasible_rate`/`reset_failure_rate`/`definition_version` **全部相等**；`vision_model` 形状仍为 `{id,name,version,sha256}` |

测试夹具刻意做得**窄**（直接起 `run_logger` 二进制、不喂消息、SIGINT 收尾），避免与 `test_run_logger_mission_fco.py` 那套完整夹具的 ROS 图发现时序耦合。

## 三、B · 检测指标 —— 完成（结果不利，如实给出）

运行：`20261102-s02_linear_none_nominal_track-0-161832-2961`（headless / seed 0 / s02 / `perception_path=vision` / `detector_backend=synthetic_color`）。

### 3.1 采集侧新增（只加采集，未改任何决策代码）

| 项 | 实现 |
|---|---|
| GT 样本 | 探针订阅 `/agc/gt/intruder_uav`，落 `(stamp, x, y, z)` 共 **5081** 条。**仅落盘供离线评估**；决策侧（`vision_detector`/`vision_target`/`task_manager`/`trajectory_tracker`）仍**无** `/agc/gt/*` 订阅——由各自 `ros2 node info` 与 `test_new_vision_nodes_do_not_subscribe_ground_truth` 守护。ADR-0009 允许真值用于离线评估。 |
| 配对链 | `image_stamps`（4249）→ `detection_stamps`（1263）→ `track_records`（1078）→ `goal_records`（171，含 `src_stamp`）；另记 `rx_epoch` 与 `sim_clock_now`（`/clock`）以便算真实延迟。 |
| `/agc/task/state` 类型 | 已改为 `agc_msgs/AgcTaskState`，**本轮已验证**：采到 **175** 条状态消息（round-5 为 0）。 |

### 3.2 指标数值

| 指标 | 值 | 口径 |
|---|---|---|
| **recall**（near_plane 档，`abs(dz)<=0.10 m`） | **0.6353**（54/85） | 命中 = 该 GT 源时刻 ±0.10 s 内存在视觉航迹 |
| recall（mid 档 `0.10<abs(dz)<=0.50`） | 0.9575（1217/1271） | 同上 |
| recall（far 档 `abs(dz)>0.50`） | 0.8140（3032/3725） | 同上 |
| recall（全样本） | 0.8469（4303/5081） | 同上 |
| **precision**（空间门 2.0 m） | **0.2384**（257/1078） | 分母 = 时间配对上的航迹；分子 = 其中 3D 距离 ≤2.0 m 者。**仅时间配对不算命中**（GT 30 Hz 连续，任何时刻都有样本） |
| **3D 误差 p50 / p95（全样本）** | **3.464 m / 16.309 m**（n=1078） | 航迹世界坐标 vs 同刻 GT |
| 3D 误差 near_plane 档 | 4.856 / 5.509 m（n=**13**） | 样本极少，见 §3.4 |
| 3D 误差 mid 档 | 4.064 / 13.773 m（n=316） | |
| 3D 误差 far 档 | 3.230 / 16.995 m（n=749） | |
| **图像→航迹延迟 p50 / p95** | **0.0160 s / 0.0240 s**（n=1078，min 0.008 max 0.036） | `delay = 航迹到达时 /clock sim 时刻 − 源图像 sim stamp`（同一 sim 时钟） |

### 3.3 3D 误差的诚实分档（派工单强制要求）

本实现是 **`z = plane_z` 单平面相交**。目标真实高度偏离 `plane_z` 时，交点沿**径向**偏移，
误差主要沿相机-目标连线，**非各向同性**。

**实测：本 run 的目标高度几乎从不落在假设平面上。**

| 时段 | GT `z` min / p50 / max | `abs(dz)<=0.10 m` 占比 |
|---|---|---|
| t 0–40 s | −0.02 / −0.01 / 2.00 | **3%** |
| t 40–80 s | 1.20 / 1.53 / 1.91 | 5% |
| t 80–120 s | 0.93 / 1.13 / 1.60 | **0%** |
| t 120–178 s | 0.90 / 1.30 / 1.62 | **0%** |

→ 所谓 "near_plane 档" 只有 **85 个 GT 样本**（且航迹侧只配上 **13** 条），
**不足以代表检测精度**。全域 3.46 m 的 p50 里含大量单平面假设残差。
**报告不把 3.464 m 说成"检测器精度"**；它只能读作"该假设下的端到端三维偏差"。

### 3.4 两个真实缺陷（本轮新发现，round-5 未暴露）

**缺陷 1 — 射线杠杆：目标贴近平面法线时交点飞到数百米外。**

`t=(z_plane−p_z)/b_w.z`，当相机-目标连线几乎垂直于平面（`b_w.z→0`）分母趋零。实测：

| 源时刻 | 解出的 `P` | 到原点距离 | 真值 |
|---|---|---|---|
| 20.8 s | (20.4, **274.5**, 2.0) | 275 m | (15.0, −2.0, 2.0) |
| 20.9 s | (11.2, **194.2**, 2.0) | 195 m | ≈(15, −2, 2) |
| 172.8 s | — | **414 m** | (30, −2, ~1) |

`|P| > 50 m` 的航迹 **41/1078（4%）**，但它们把 p95 从个位米推到 16 m。
根因：`max_ray_range_m=400` 的门太宽，且缺少"交点在目标合理邻域"的健全性检查。
**这是 `vision_target.cpp` 的实现缺陷，不是单平面假设的必然结果**（同样几何下把
`max_ray_range_m` 收到 ~60 m 即可挡掉绝大部分）。

**缺陷 2 — 高度平面假设在本场景几乎全程失效。**

见 §3.3。`plane_z` 由 `cruise_alt_m=2.0` 派生，但**目标 GT 的实际高度**在 t≤40 s 是地面（`z≈0`）、
之后在 0.9–1.6 m 波动——即 `cruise_alt_m` 描述的是**巡航指令高度**，不是目标在任意时刻的真实高度。
用单一固定平面做视觉测距，在本场景**原理上就会产生系统性径向误差**。

**这两条都应作为 round-7 的输入**，不是本轮能就地修好的（改 `max_ray_range_m` 会改决策侧几何，
且"平面假设失效"需要 Leader 裁定用哪个高度先验，可能涉及 H0 语义边界）。

### 3.5 配对链覆盖率

| 级 | 数值 |
|---|---|
| `detection_stamp` 属于某 `image_stamp` | 1151 / 1263（91.1%） |
| `track_stamp` 等于 `detection_stamp` | **1078 / 1078（100%）** |
| `goal` 的 `TARGET_FRESH` 条数 | 139 / 171 |
| `goal` 的 `src_stamp` 精确命中某 `track_stamp` | **139 / 139（100%）** |

→ **"goal 由视觉航迹驱动"在时间戳层面是 100% 可追溯的**：每一条 `TARGET_FRESH` 的
`src_stamp` 都能一一对上一条视觉航迹的源时刻。

`detection_stamp` 未 100% 命中 `image_stamp` 的原因：检测器 `max_rate_hz=10` 降频
（`frames_skipped_rate_limit` 实测数千），被降频跳过的图像帧不产生检测数组。
"检测 stamp ⊆ 图像 stamp"成立，反向不成立。

## 四、命令与退出码

| # | 命令 | 退出码 |
|---|---|---|
| 1 | GUI 前置检查（`ls` ×2 / `xdpyinfo`） | `X UNAVAILABLE` |
| 2 | `colcon build --packages-select agc_task --symlink-install` | **0**（24.3 s） |
| 3 | `pytest scripts/tests/test_n1_run_logger_backend.py` | **0**（3 passed） |
| 4 | 采集运行 `n1_round5_probe.py --label r6 --headless` | **0**（探针首次因 `trk` 未定义崩 → 修后重跑成功） |
| 5 | `python3 scripts/vision/n1_round6_metrics.py --probe ... --out ...` | **0** |
| 6 | `pytest scripts/tests/test_n1_run_logger_backend.py test_n1_vision_detector.py test_n1_vision_wiring.py test_p1_4_vision_wiring.py` | **0**（58 passed） |
| 7 | `pytest scripts/tests/`（全量） | **0**（**358 passed**） |

## 五、证据路径与哈希

目录：`.coordination/task/20261102-002-n1-vision-minimal-loop/round-6/evidence/`

| 文件 | SHA-256 |
|---|---|
| `gui-feasibility.txt` | `3d3827052860ca0844fbfab0d7d88b7e85d49dc49fa3723f29cffc102a5cbfec` |
| `probe-r6.json`（958 KB，含 5081 GT 样本 + 完整配对链） | `cea0454ea9a1f6f45ed8f9b7c2adf7b939a6710843fcb2173dfc802b058ad491` |
| `metrics-r6.json` | `e3fe8cea44f49b207f7d97248e2103438af737f8df5e67e0ad919be2d401aa12` |
| `metrics-r6.txt`（人读版） | `52bf7ca269c8125b33785f8eaf4e9de25f95f0f33f526e53616b38d2d07b661a` |
| `summary-r6.json` | `ea81a3248321d11866e4e4b2713cab3bd85831c47f6ed83e2c6397426ce5032d` |
| `scene-manifest-r6.json` | `686eb86f52b2906587daf0cf7d66a35cd63fc2f9572a9f48eca7270c54aad4b3` |
| `launch-r6.log`（176 KB） | `f3b3d6ba8cc5dc76996a7ce9af8a054d13db77d79d50206ed39ff3255d7505f2` |
| `run-id.txt` | `713feb286f35e2aa2fa42a4efe97664d3ce10df288c4ff932636d6d8f1163148` |

原始 run 目录（按契约保留）：`experiments/w6-task-eval/20261102-s02_linear_none_nominal_track-0-161832-2961/`

## 六、未达项

| # | 未达项 | 原因 |
|---|---|---|
| 1 | **GUI 原始帧**（帧数 0，采集未启动） | **X UNAVAILABLE**（环境不可得，已由 Leader 独立确认） |
| 2 | GUI 无目标负例 | 同上 |
| 3 | near_plane 档 3D 误差不具代表性（n=13 航迹 / 85 GT） | 目标实际高度几乎不落在 `plane_z`（§3.3）——属假设失效，非采样不足可解 |
| 4 | 3D 误差含未剥离的实现缺陷残差 | 射线杠杆缺陷（§3.4 缺陷 1）：`|P|>50 m` 的 4% 航迹把 p95 推到 16.3 m。修它需改决策侧几何，超本轮范围 |

## 七、T1 / T2 / 墙钟账目

| 项 | 值 |
|---|---|
| **T1** | **0 s**（0 次） |
| **T2 本轮** | **≈ 900 s**：colcon build 24 s + 采集运行 ≈ 420 s（含启动/PX4 起飞/终态/证据采集）+ 失败重试前的一次启动 ≈ 30 s；另加测试夹具起 `run_logger` 若干次（每次 ≈3 s） |
| T2 单次最长 | **≈ 420 s** ≤ 900 s ✅ |
| **T2 占额度** | **≈ 900 / 3,600 s（25%）** |
| 静态/离线 | ≈ **120 s**（pytest 358 个用例 ≈10 s × 3 轮 + 指标计算与日志分析），单次均 < 30 s ✅ |
| **墙钟** | 领取 `16:15:00` → 交回 `≈16:27`，**≈ 720 s / 7,200 s（10%）** |
| 结论 | 未耗尽任何额度；A 阻塞后按指示立即停，未空转 |

## 八、假设台账

| 假设 | 状态 | 判别实验 | 结果 |
|---|---|---|---|
| 本轮 GUI 可用 | **已排除** | 前置检查三条命令 | `X UNAVAILABLE`（无 socket、无 X server 进程） |
| round-5 探针 `state` 空是任务没进状态机 | **已排除** | 改用 `AgcTaskState` | 采到 175 条，状态机正常 |
| `precision` 可用"时间配对率"代表 | **已排除** | 加空间门重算 | 时间配对 1078/1078（100%，无信息量）→ 空间门后 **0.238** |
| 三维误差主要来自检测器精度 | **已排除** | 按 `abs(dz)` 分档 + 逐条查最差样本 | 主因是①单平面假设失效（目标 `z` 几乎不在 2.0）②射线杠杆缺陷（`|P|` 达 414 m） |
| `detector_backend` 改动会波及评估口径 | **已排除** | `test_detector_backend_is_label_only` 逐键比对 | 既有键零变化 |

## 九、下一轮建议

1. **GUI 仍是唯一硬缺口**：需在**有 X display 的会话**（或 Leader 有 root 的环境）跑一次 full+GUI。建议派工单前置检查继续保留。
2. **修射线杠杆缺陷**（`vision_target.cpp`）：在 `t>0` 之外增加"交点须在相机前方合理距离内"的门（例如 `max_ray_range_m` 从 400 收到 60，或按 `|b_w.z|` 下限拒绝近法线几何）。这会**改决策侧几何**，需 Leader 授权。预计可显著改善 p95。
3. **裁定高度先验**：单平面 `z=cruise_alt_m` 在本场景**原理性失效**（目标 `z` 实际在 0–1.6 m）。可选方向：① 用 `/agc/targets` 的 z 由 H0 语义另定；② 接受"固定高度平面只对固定高度目标有效"并在验收口径里限定适用域；③ 引入第二视角/测距。这是**目标/口径问题，需 Leader 定**，不是 Worker 能自行选的。
4. 若要继续量化检测器本身精度，应在**目标确实贴合平面**的专门实验里测（例如把目标锁定在 2.0 m 的场景），否则测到的是假设失效而非检测精度。
