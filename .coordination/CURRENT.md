<a id="current"></a>
# 当前交接

- 任务 ID：**20261031-011-p2-1-deliverables**
- 轮次：**round-8 完成（新批次 N=4 已用 2，余 2 / K=4）**
- 状态：**执行中**（**停下报告**：克隆实测路径自定位成立，但暴露 `run_logger` 同类缺陷，待裁定 α/β/γ/δ）
- round-5 结论（Leader 复核）：三图统一 831×952、md5 一致、skyband 全 0.0000、GIF 2,661,003 B 且单位写死、崩溃已修且有回归、提交 `c3895ef` 合规。
  **两条局限记档**：① 85 m 下三图两两差异仅 0.022%–0.041%，"三阶段"靠时刻与 `timeline.txt` 区分（未伪造差异）；
  ② 三图是 Gazebo 3D 视图、**不含 P1-3 状态面板**（面板在终端，Wayland 截不了整窗）→ 该要求由**用户自录视频**承担，README 图注须写明。
- 当前派工：[round-1 request](task/20261031-011-p2-1-deliverables/round-1/request.md#p2-1-r1-request)（Leader）
  · round-2…round-5 request 由 Worker 自写（round-5 继承 [round-4 审查](task/20261031-011-p2-1-deliverables/round-4/review.md#p2-1-r4-review) 第 4 节）
- 回报：[round-1](task/20261031-011-p2-1-deliverables/round-1/report.md#p2-1-r1-report) · [round-2](task/20261031-011-p2-1-deliverables/round-2/report.md#p2-1-r2-report) · [round-3](task/20261031-011-p2-1-deliverables/round-3/report.md#p2-1-r3-report) · [round-4](task/20261031-011-p2-1-deliverables/round-4/report.md#p2-1-r4-report)
- **Leader 裁定（round-4 审查）**：
  ① **里程碑达成**：三图 + GIF 达标（我复核 md5 / 自算 skyband 全 **0.0000** / 自跑几何核查 PASS / 断链 0）。
  ② **三处更正**：**"用户拖相机"不能取代 H-C**（两变量独立，round-2 三帧 3 s 内仅差 0.5% 像素）；`camera_pose` 118→85 的**来源待用户追认**（否则回退）；GIF **5,095,380 B** 单位口径未写死 → 须重压 **≤5,000,000 B** 或写明 `5 MiB`（离线，不占 T2）。
  ③ **顺序**：round-5 先用 85 m 重取三图/GIF 并**统一尺寸**；round-6 再做干净环境验证（必须审"照 README 从零走通"，故放最后）。
  ④ 预算 **T2 +2 次 / +1200 s**（累计上限 **12 次 / 7800 s**）；round-5 ≤2、round-6 ≤2。
- **机制定案（我复核过日志）**：`--gui-config` → gz-gui **加载两层**，`~/.gz/sim/8/gui.config` **后加载覆盖**位姿 → 斜视 0.2848（H-C）；**自然运行**走 SDF `<gui>`，位姿为正俯视但 9 插件无 Screenshot → 0 帧（H-D）。H-A/H-B/H5 均证伪。
- **Screenshot 取的是 GUI 实时视图相机** → 用户拖拽/缩放窗口会改变截图内容与尺寸（round-4 实测）。取帧期间**请勿拖动或缩放 Gazebo 窗口**。
- **用户裁定（2026-10-31）**：① 默认运行所见 = **正俯视平面图**（与实测一致）；② **完整演示视频由用户自录**，不装工具、不合成。
- **相机事实**：world SDF `<gui>` `camera_pose = 0 0 85 0 1.5708 1.5708`（**118→85**，纯 GUI 视觉）；
  **用户已追认 85 m**（来源闭合，不回退 118）。skyband：俯视 ≈0.00–0.06、斜视 0.20–0.36。
- **已交付（round-5 定稿）**：`docs/plan/assets/demo-start|tracking|terminal.png`（**统一 831×952**，
  skyband 全 **0.0000**，t≈43.0/55.4/59.5 s；md5 `cd04e0cb…` / `29a552ce…` / `8e7260a4…`）
  + `demo.gif`（9 帧 / 800×916 / **14.4 s** / **2,661,003 B**，十进制 5,000,000 B 口径）+ `demo-manifest.json`；
  SDF `<gui>` 自带 Screenshot（10 插件）；`AGC_GUI_CONFIG` 机制已移除。
  **收尾崩溃已修**（`stable_detail` 使用早于赋值）+ 回归 `test_capture_run_closeout.py`（6 用例，反向对照会变红）。
  报告：[round-5](task/20261031-011-p2-1-deliverables/round-5/report.md#p2-1-r5-report)
- **追加自查更正**：round-1…4 报告把 Worker 子会话 ID 与父会话 ID 写成同一值；真实 Worker =
  `7eb40b67-31c3-4a50-b313-e084cf01bdd7`，父 = `session-c1423390…`（仅记录层，未误投）。
- **当前派工（round-6，最后一轮）**：干净环境验证（清 `build/install/log` → `colcon build` → 照 README 从零走通 ≥1 轮，
  记耗时/卡点、回改 README、README 图注补"状态面板在终端/演示视频"）→ 勾选 P2-1 出口判据（**视频项不勾**，注明待用户录制）。
  T2 ≤2（累计 9/12 余 3）；**若轮次或预算不够 → 必须唤醒 Leader**，不得自行开轮。
- **剩余计划**：round-6 通过后 → 等用户视频文件 → 全项验收并归档（下一任务或 CURRENT 置空闲）。
- **round-6 结果（批次末）**：干净环境验证**成功**——清 `build/install/log` → `colcon build`
  **9 包 / 308.41 s / exit 0** → `doctor` **14/14 PASS / 0.02 s** → 默认演示 **`TRACKING_SUCCESS`**；
  **清理→终态 6.5 分钟**（build 5.4 + 演示 1.1）。README 已回改 3 处卡点（toolchain 怎么备 /
  构建耗时 / 路径硬编码）；P2-1 判据**勾选 9/10**（完整演示视频如实未勾，用户自录待路径）。
  报告：[round-6](task/20261031-011-p2-1-deliverables/round-6/report.md#p2-1-r6-report)
- **Leader 裁定（round-6 审查）→ 新批次 round-7…round-9**：
  ① 干净环境验证通过（6.5 min）；② **路径硬编码是真阻塞** → **A + D**，范围按"是否用于运行期解析文件"判定：
     纳入 `run_demo.sh` / `scripts/demo/**` / `tests/w6_geometry_check.py` / `scripts/tests/**`（21 个，逐个分类）/
     `src/agc_task/launch/w6.launch.py`（3 处，逐个分类）+ 回归断言；
     **不做** `scripts/research/**`、`scripts/archive/**`、`docs/**`、`.coordination/**`、冒烟未调用的 `tests/**`、
     **契约默认值**（`air_bringup.launch.py` 的 `agc_root` 默认值是受 `toolchain_root_check.py` 保护的真源，不得改）；
     ③ 顺带修 `doctor` 误报（克隆无 `install/` 必须 FAIL）；
     ④ **round-8 克隆实测**：未构建先证 `doctor` FAIL（负向取证）→ 克隆内 `colcon build` → `doctor` PASS →
     按 README 默认形态跑到终态，产物必须落**克隆自己的** `experiments/`；
     ⑤ 预算 **T2 +3 / +1800 s**（累计上限 **15 次 / 9000 s**）。
  我复核补充：`tests/run_smoke.py` **已**自定位；`scripts/demo/start.py:114` 已把 `agc_root:=<common.ROOT>` 传给 launch
  → **修 `common.py` 即可让整链用克隆自己的根**；冒烟 5 组里仅 `w6_geometry_check.py` 带 1 处硬编码。
- **round-7 结果**：4 处运行期解析类位置自定位（`run_demo.sh` 用 `BASH_SOURCE`；
  `common.py` / `tests/w6_geometry_check.py` / `scripts/tests/test_w6_viz_registration.py` 用 `__file__`）；
  新增 `scripts/tests/test_root_self_location.py`（**10 用例**，白名单逐条理由，**反向对照 4 failed**）；
  **契约默认值未动**（`air_bringup` 的 `agc_root` + `toolchain_root_check` 校验仍在）。
  `scripts/tests` **276 passed**、冒烟 **5/5**、断链 0。提交 `7fe7814`。
  分类表见 [round-7 报告](task/20261031-011-p2-1-deliverables/round-7/report.md#p2-1-r7-classification)：
  **不做** `research/`(19) / `archive/`(64) / `docs/`(30) / `.coordination/`(21) / 冒烟未调用的 `tests/**`
  → 忠实登记为"开发/历史工具不可移植"。
- **口径更正**：Leader 转述"`scripts/tests/**` 21 个文件"是**含 `.pyc` 的宽口径**；
  实际 `*.py` **18 个**，其中 **17 个本就自定位**，仅 **1 个**需修。
- **round-8 结果**：克隆到 `/tmp/agc-r8-clone`（任意路径）→ 构建 **9 包 / 308.25 s / exit 0**
  → `doctor` **PASS**（报 `/tmp/agc-r8-clone/install/...`）→ **`TRACKING_SUCCESS`**，
  产物落**克隆自己的** `experiments/demo/`，原仓库 `experiments/demo/` **未新增**（51→51）。
  **负向取证**：构建前 `doctor` **exit=1**，报 `缺少 /tmp/agc-r8-clone/install/setup.bash`。
  **但暴露缺陷**：`run_logger` 把 summary 写到**原仓库**（`run_logger.cpp:85` 的 `experiments_root`
  硬编码，`w6.launch.py` 从未设置该参数）；原仓库 `w6-task-eval/…-121023-3528/` 被克隆 run 写入（**未删除**）。
  **这是我 round-7 分类的误判**（只查了 Python/launch 层，漏了 C++ `declare_parameter` 默认值）。
  报告：[round-8](task/20261031-011-p2-1-deliverables/round-8/report.md#p2-1-r8-report)
- **⚠ 待裁定（round-8 §2.4）**：α（`w6.launch.py` 传 `experiments_root`，**白名单内 1 处**，建议）/
  β（改 `run_logger.cpp` 默认值，需扩白名单 + 重编）/ γ（两者）/ δ（不改，不可接受）。
  偏离：`toolchain/` 用符号链接借用主仓（真实陌生人须自建，成本另计）。
- **剩余待办**：完整演示视频（用户自录，路径待提供，不占轮次/T2）。
- **下一轮**：round-7 = A+D 落地 + `doctor` 误报修复 + 归因分类表（**T2 0**）；round-8 = 克隆实测（**T2 ≤2**）；
  round-9 = 用户视频接入 + 判据全勾 + 结档准备（**T2 0**，等用户文件）。
  **停止条件**：round-7/8 两轮内克隆仍不能"`doctor` 真实 + 跑到终态" → 判不可达成，停止交台账。
- 上一任务（已结档）：[20261030-010 P1-4 baseline closure](archive/20261030-010-p1-4-baseline-closure/round-3/review.md#p1-4-baseline-final-review)，结论 **PASS_WITH_NOTE**；P1-4 缺口已在 README「已知边界」登记。
- **基线事实**：HEAD `32c35f2`；P1-1…P1-4 全部产物已入库（`07eda37`）。
- **演示口径**：`full + yard + s04 + observe_yaw_mode=target`；target 是显式 oracle 指向臂，不等于真实视觉识别。

**迁移 workstream 暂停，W8 不再接单**（[PAUSED](../docs/plan/PAUSED.md#paused)）。