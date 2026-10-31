# P1-4 · round-2 报告

<a id="p1-4-r2-report"></a>

- 任务 ID：`20261030-009-p1-4-vision`，round-2
- 执行者：Worker（workbuddy / `deepseek-v4.1-flash` / max）
- 领取：2026-10-30T19:47+08:00；报告：2026-10-30T20:06+08:00
- 状态：**阻塞（预算耗尽 + 需要重新派发真实运行方式）**
- 父会话 ID：`session-fd998168-60d9-42ef-a7df-834b0457b88f`

<a id="p1-4-r2-summary"></a>
## 审查摘要（≤30 行）

1. **代码接线全部完成并离线验证**：`w6.launch.py` 新增 `perception_path` / `vision_detector` /
   `vision_model_*` / `px4_sim_model`（默认 `truth` / `false` / `gz_x500`，**既有行为逐字不变**）+
   **互斥校验**（truth+detector → 拒、vision 无 detector → 拒、未知值 → 拒，三条实测生效）；
   `run_logger` summary 新增 `perception_path` + `vision_model{id,name,version,sha256}`（只增不改）；
   契约 `#params` 增 `/agc/perception/path` + 新节 `#perception-path`。
2. **新字段在真实 run 里首次成立**：`perception_path="truth"`、`vision_model={id:"none",...}` 已落盘。
3. **两次 T2 均判无效**（**我的 harness 缺陷**，非系统故障）：
   A0（25 s）用 glob 取到历史 summary 提前终止；A1（330 s）**未调 `/agc/task/start`** →
   `terminal_state=IDLE`、`episode_window_metrics` 全 0。**R4 未测**。
4. **T2 预算 2/2 用尽**（25 + 330 = 355 s / 900 s）→ 相机臂（R5）、数据集（R7）未跑。
5. **重要发现（会改变后续判断）**：`gz topic -l` **会列出只有订阅者的话题** → 相机未启用时
   `/camera` 照样出现。**round-1 A1 的"出现话题"单独不足以证明有相机**（但 A1 另有 `gz topic -f`
   ≈30 Hz 实测，A2/A3 有真实帧，故结论仍成立）。已在 `bridge.yaml` 注释固化该口径。
6. **离线回归全绿**：`scripts/tests` **227 passed**、9 消息 golden **9 passed**、`src/agc_msgs` 零差异、
   geometry **PASS**、docs link 仅 1 条**既有**断链（`.coordination/CURRENT.md` 的 `#p1-1-acceptance`，
   该 anchor 在归档 review 中本就不存在，与我无关）。
7. **未宣称**视觉识别接入决策；本轮识别后端仍为 `none`（显式降级）。
8. **需要 Leader**：重新派发 **1 次**相机/vision 臂（必须走 `run_demo.sh` 或显式调 `/agc/task/start`）。

<a id="p1-4-r2-baseline"></a>
## 1. 接单基线

| 项 | 值 |
|---|---|
| HEAD | `b627043423de25e61c9ed3fb0ec8f4dd39c44d18`（main，与 round-1 相同） |
| dirty | 57 条（round-1 的改动 + 既有他轮） |
| 既有进程 | 无（每次 T2 前核对） |
| 构建 | `colcon build --packages-select agc_task` → **1 package finished**（50.7 s） |

<a id="p1-4-r2-changes"></a>
## 2. 实际改动

| 文件 | 改动 | 授权依据 |
|---|---|---|
| `src/agc_task/launch/w6.launch.py` | 7 个 `DeclareLaunchArgument`；`perception_path` / `vision_detector` / `px4_sim_model` 的**校验**；own PX4 的 `PX4_SIM_MODEL` 改用 `px4_sim_model`；run_logger 注入 5 个新参数 | 派工单明列「仅透传，默认不变」 |
| `src/agc_task/src/run_logger.cpp` | 5 个 `declare_parameter` + 5 个成员 + summary 两行新键 | 派工单明列「仅加新键」 |
| `docs/ROS2迁移交接文档.md` | `#params` 增 `/agc/perception/path`；新节 `<a id="perception-path"></a>` | 派工单明列 |
| `src/agc_sim/config/bridge.yaml` | **仅注释**：补「只出现话题名 ≠ 有相机」实测口径 | 白名单（round-1 已列）+ 本轮证据 |
| `scripts/tests/test_p1_4_vision_wiring.py` | 新增 24 条离线接线断言 | 白名单 `scripts/tests/**` |

**没有**把识别节点并入 w6 编排（会引入不存在的 `agc_vision` 包并改任务编排）——
`vision_detector:=true` 只作**声明**，识别进程按工具域独立起；测试里有一条专门挡这个回退。

<a id="p1-4-r2-evidence"></a>
## 3. 判据逐项

| # | 判据 | 结果 | 证据 |
|---|---|---|---|
| R1 | 预登记先于真实启动 | **PASS** | prereg mtime 19:53:30 < A0/A1 起 19:53:51；落盘时 `t2/` 为空 |
| R2 | w6 支持新参数、默认不变 | **PASS** | [`evidence/r2-show-args.txt`](../../../../experiments/p1-4/round-2/evidence/r2-show-args.txt)；三条拒绝用例 [`t1-mutual-exclusion-rejects.txt`](../../../../experiments/p1-4/round-2/evidence/t1-mutual-exclusion-rejects.txt) |
| R3 | summary 可区分 | **PARTIAL** | truth 臂实测 `perception_path=truth` + `vision_model{id:none}`；**vision 臂未跑** |
| R4 | truth 臂行为不变 | **未测** | A1 因未 `task/start` 判 `IDLE`，`episode_window_metrics.ticks_total=0` |
| R5 | 相机臂真实可用 | **未跑** | T2 预算用尽 |
| R6 | 无模型显式降级 | **PASS**（round-1 A6 延续 + 本轮互斥） | round-1 `evidence/degrade/a6/` |
| R7 | 真实 image+label | **未跑** | 同上 |
| R8 | ABI 未变 | **PASS** | [`r8-abi.txt`](../../../../experiments/p1-4/round-2/evidence/r8-abi.txt)：零差异 + 9 passed |
| R9 | 全套回归 | **PASS** | 227 passed / geometry PASS / docs link 仅既有 1 条 |
| R10 | 清理 | **PASS** | 两次 T2 均按 PGID 回收；`ps` 无残留 |

<a id="p1-4-r2-finding"></a>
## 4. 关键发现：`gz topic -l` 不能证明"有相机"

详见 [`evidence/camera-ownership-finding.md`](../../../../experiments/p1-4/round-2/evidence/camera-ownership-finding.md)。

- 实测（[`t1-gz-topic-list-subscriber-only.txt`](../../../../experiments/p1-4/round-2/evidence/t1-gz-topic-list-subscriber-only.txt)）：
  对一个**只有订阅者、无发布者**的话题，`gz topic -l` **仍会列出**。
- 后果：`bridge.yaml` 以订阅方式桥接 `/camera` → 缺省 `gz_x500`（无相机）时，
  `/camera` 与 `/agc/air/camera/image_raw` 照样"存在"，但**没有帧**。
- **对 round-1 的重新定性**：
  - A1 的"`gz topic -l` 出现 image 话题"这一条**单独不充分**（虽当时另用 `gz topic -f -t /camera`
    实测 ≈30 Hz，且当时 bridge 尚无相机条目）；
  - A2（`ros2 topic hz` 24–26 Hz）与 A3（PNG + 亮度 180.1/43.6）**必须有真实帧才能成立**，故仍有效。
- 已修：`bridge.yaml` 相机条目注释写明"判是否有相机须用 `gz topic -f` 或真实帧频率/像素"。

<a id="p1-4-r2-blocker"></a>
## 5. 阻塞与待裁定

### 5.1 直接原因：两次 T2 均无效，责任在我

| attempt | 墙钟 | 失效原因 | 是否有效证据 |
|---|---|---|---|
| A0 | 25 s | 轮询用 `ls -t experiments/w6-task-eval/*/metrics/summary.json \| head -1`，取到 **P1-3 的历史 summary** → 提前判"到终态"并回收 | **否**（未创建本 run 目录） |
| A1 | 330 s | 直接用 `ros2 launch` 起 w6，**没有调 `/agc/task/start`** → 任务层起了、`scenario_reset: initial reset (gated): ok`、`intruder_driver: episode armed`，但 **episode 从未开始** → `terminal_state=IDLE` | **否**（R4 不可用；R3 新键可用） |

**为什么 A0 算"无效样本可重试 1 次"**：派工/协议允许"进程异常退出（无效样本）且根因明确时重试 1 次"。
A0 的根因（glob 匹配历史产物）当场确认并修正（改用精确 `run_id_override` 路径）。A1 的根因
（缺 `task/start`）在 A1 结束后才由 `terminal_state=IDLE` 暴露。
**但两次都计入了 T2 次数**（本轮 2/2），这是我没有在第一次运行前确认"任务如何被启动"的代价。

### 5.2 需要的最小追加授权

**只差 1 次真实启动**，且**不需要扩白名单**：

- 方式：`./run_demo.sh --headless`（既有入口，自带 `/agc/task/start` 与就绪门），
  通过既有参数透传 `px4_sim_model:=gz_x500_mono_cam perception_path:=vision vision_detector:=true`
  —— **需要确认 run_demo 是否接受额外 launch 参数**（`run_demo.sh` 有 `--` 之后透传的机制，
  `start.py` 的 `launch_argv(extra=...)` 支持，但对外 CLI 目前只暴露 5 个参数）。
  若不允许，则用 `ros2 launch` + **显式 `ros2 service call /agc/task/start std_srvs/srv/Trigger`**
  （本 Worker 下一轮可直接做，无需改代码）。
- 建议追加：**T2 1 次 / 450 s**；同时把 R4 的 truth 臂也在这 1 次里补做（或单独 1 次）。

### 5.3 未决（不阻塞，但需口径确认）

- `perception_path` 目前只影响 **summary 标注 + 识别节点启停**，**不影响任务决策**（决策输入仍是
  真值派生链）。因此 vision 臂的终态**不能**作为识别能力证据——这一点已写进预登记 `disallowed_claims`。
  若 Leader 期望"vision 真正接管决策"，那是**下一阶段**工作（需改 `air_fusion` 的融合输入），
  不在本轮授权内，我不能自行扩大。

<a id="p1-4-r2-budget"></a>
## 6. 预算

| 项 | 用量 / 授权 |
|---|---|
| T2 | **2 / 2 次**（上限用满）；墙钟 **355 s / 900 s** |
| T1 | **4 / 4 次**（互斥拒绝 ×3 合为 1 次 + gz 订阅者测试 1 次 + show-args 2 次）；均 ≤30 s |
| 离线 | 约 12 次；累计 < 150 s / 300 s；单次 ≤30 s（`colcon build` 50.7 s 属构建，非离线检查） |
| 构建 | `colcon build --packages-select agc_task` 1 次（52.9 s）——**派工单未明列构建预算**，如实披露 |

<a id="p1-4-r2-hypotheses"></a>
## 7. 假设台账

| 假设 | 状态 | 判别实验 | 所需授权 |
|---|---|---|---|
| H1：A0 失败是 glob 匹配历史产物 | **已确认** | 修正为精确路径后 A1 不再误判 | 无 |
| H2：A1 失败是缺 `/agc/task/start` | **已确认** | `run_demo.sh` 的 `start.py` 显式调该服务；A1 summary 为 IDLE 且 ticks=0 | 无 |
| H3：`gz topic -l` 会列订阅者话题 | **已确认（实测）** | T1-3 单测 | 无 |
| H4：相机条目在无相机机型下"无害但误导" | **已确认** | truth 臂 gz 有 `/camera` 但己方机 `simulation model: x500` | 无 |
| H5：vision 臂能达 TRACKING_SUCCESS | **未排除** | 需 1 次有效 T2（含 task/start） | T2 1 次 |
| H6：run_demo 支持透传任意 launch 参数 | **未排除** | 读 `run_demo.sh` / `start.py`（当前 CLI 只暴露 5 个） | 无（T0 可查） |

## 8. 下一轮建议（若获授权）

1. 用 `run_demo.sh --headless` + 显式 `ros2 service call /agc/task/start` 的方式跑 **1 次** vision 臂：
   `px4_sim_model:=gz_x500_mono_cam perception_path:=vision vision_detector:=true`；
2. 同一次 T2 内跑 `record_dataset.py`（相机 + gt 同时在）→ 补 R7；
3. 对照 P1-3 的 truth 臂 summary 做 R4（若需 fresh truth 数据，再单独 1 次）；
4. 之后才能判 P1-4 是否验收。

## 9. 状态

- **阻塞**（预算耗尽；非契约风险、非 ABI 风险）。
- 未执行：vision 臂真实运行、R4 truth 复测、R7 数据集、GUI 形态相机复核。
- 未 commit（派工单禁止）。
