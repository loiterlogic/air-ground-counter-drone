# P2-1 · round-1 批次派工单（项目交付物打包）

<a id="p2-1-r1-request"></a>

- 任务 ID：`20261031-011-p2-1-deliverables` · round-1 · 2026-10-31
- 来源：用户 2026-10-31 裁定——对 P1-4 第 4 项**"选 1：认账收口"**（[结档裁定](../../../../docs/plan/p1-4-视觉算法接入.md#p1-4-closure)），随后执行 P2-1。
- 批次授权：**N=6 / K=4**，预登记停止条件见下（[协作规则](../../../README.md#batch)）。

## 目标

按 [P2-1 项目交付物](../../../../docs/plan/p2-1-项目交付物.md#p2-1-goal) 把项目从"能跑"变成"陌生人 10 分钟能看懂并跑起来"：
根 `README.md` + **真实运行**截图/GIF + 系统结构图 + FAQ + 冒烟测试单一入口 + **干净环境验证 ≥1 轮**。
验收以 [P2-1 出口判据](../../../../docs/plan/p2-1-项目交付物.md#p2-1-exit) 10 项为准，缺项即未达成。

## 不可变边界（越界即停止报告）

- 不改契约硬约束、9 消息 ABI、唯一执行口、C3/C8 口径；薄封装纪律照旧（[ADR-0061](../../../../docs/adr/0061-w6-runtime-topology-backend-identity-and-single-parameterized-entry.md)）：`run_demo.sh` 不复制启动编排、不写 `/agc/ground/cmd_vel`、不写模型位姿。
- 不发布 `.trae/`、`experiments/`、`reference/`、`docs/archive/specs/`、`toolchain/` 内容（[ADR-0081](../../../../docs/adr/0081-public-repo-publishing-boundary.md)、[ADR-0105](../../../../docs/adr/0105-retire-trae-and-relocate-specs-skills.md)）；第三方资产按 [ADR-0068](../../../../docs/adr/0068-third-party-asset-provenance-license-and-hash-manifest.md)。
- README **不复述契约**，只引用链接（[ADR-0002](../../../../docs/adr/0002-docs-source-of-truth-layering.md)）。
- **口径**：演示 = `full + yard + s04 + observe_yaw_mode=target`；`target` 是**显式 oracle 指向臂**，README 中**不得**写成真实视觉识别；`vision_model.id=none` 的成功 run 不得当作视觉能力。
- **已知边界清单必须含 4 条**：占位捕获（[ADR-0024](../../../../docs/adr/0024-capture-adjudication-fire-control-window.md)）、真值派生感知（[ADR-0020](../../../../docs/adr/0020-perception-as-truth-derived-simulation.md)）、无实机验证（[ADR-0009](../../../../docs/adr/0009-sim-first-with-hardware-hooks.md)）、视觉可插拔默认无模型（P1-4）；**另加第 5 条**：**换用相机机型对跟踪动力学的量化影响未知**（P1-4 第 4 项以风险登记收口，见 [结档裁定](../../../../docs/plan/p1-4-视觉算法接入.md#p1-4-closure)）。写成"当前能力范围"，不写成自我否定清单。

## 先学后做

先读：P2-1 计划全文、[包边界](../../../../docs/conventions/包边界.md)、[整链排障速查](../../../../docs/conventions/整链排障速查.md#preflight)、
`run_demo.sh` 与 `scripts/demo/*`、[scripts 长期工具索引](../../../../scripts/README.md#top-tools)、
[P1-2 出口判据](../../../../docs/plan/p1-2-一键演示入口.md#p1-2-goal)、[P1-3 出口判据](../../../../docs/plan/p1-3-任务可观测与演示呈现.md#p1-3-goal)。
截图/GIF 的尺寸、体积与 README 里的摆法先看成熟仓库/官方文档的通行做法，再录，不靠自己发明。

## 接单基线

- HEAD `b627043`、分支 `main`、工作区**脏 62 项**（staged 23；未跟踪含 `run_demo.sh`、`scripts/demo/`、`scripts/vision/`、`scripts/tests/test_p1_4_*.py`、`MAP_DESIGN_PLAYBOOK.md`、4 个 `.coordination/archive/` 目录）。
- **P1-1…P1-4 全部产物从未提交**。已有改动不得 reset / 清理 / 覆盖；唯一例外是下方步骤 0 的**已授权提交**与步骤 5 的**已授权 `build/ install/ log/` 清理**。
- 本机 GUI 可用（`DISPLAY=:0`、NVIDIA RTX 4060）；GUI 录制按 [C3](../../../../docs/ROS2迁移交接文档.md#hard-constraints) 口径取证。

## 修改白名单

- `README.md`（根，新增）
- `docs/faq.md`（可选，也可并入 README）
- `docs/conventions/系统结构图.md`（新增；或 README 内嵌 Mermaid）
- `docs/plan/assets/**`（截图 / GIF）
- `run_demo.sh`、`scripts/demo/**`（新增 `test` 子命令所需的最小改动）
- `tests/**`、`scripts/tests/**`（冒烟入口与其测试）
- `.gitignore`（仅在需要排除大文件时）
- `docs/plan/p2-1-项目交付物.md`（勾选判据、记录干净环境验证）
- `.coordination/task/20261031-011-p2-1-deliverables/**`
- 产物目录：`experiments/p2-1/**`（运行证据，**不入 git**）；截图/GIF 落 `docs/plan/assets/`
- **提交**：见步骤 0（本地 `commit`，**禁止** `push` / `reset` / `clean` / 切分支）

## 步骤（批次内自主排序，0 与 1 必须最先）

0. **基线卫生提交（已授权）**：审计 `git status --porcelain` 全量，逐组确认属于 P1-1…P1-4 的已验收产物后，
   分 **2–4 笔**提交（上限 **6 笔**，含 `.coordination/` 记录与 4 个归档目录）；commit message 沿用既有风格（`docs(...)` / `scripts(...)` / `coordination: ...`）。
   提交前必须核对：**没有** `experiments/`、`reference/`、`.trae/`、`docs/archive/specs/`、`toolchain/` 内容入库；
   发现"该入库却漏了"或"不该入库却进来了"→ 先写报告再提交，不擅自取舍。
1. **README.md（最重要）**：一句话定位 / 3 条内快速开始（`./run_demo.sh doctor` → `./run_demo.sh`）/ 顶部真实截图 /
   演示看到什么 + 状态含义（引用 P1-3）/ 系统结构图 / 目录导航（8 包 + 关键目录，各一行）/ 已知边界 ≥5 条 / 文档入口。
   控制在 ~150 行，不写"未来将实现"。
2. **结构图**：Mermaid 优先，含 8 包、GZ↔桥↔感知↔任务↔控制↔执行口、外部依赖（PX4 / uXRCE / Nav2），内容须与 [包边界](../../../../docs/conventions/包边界.md) 一致。
3. **FAQ 5–8 条**：覆盖工具链缺失 / 等待 PX4 错峰 / `ROS_DOMAIN_ID` 与发现 / 残留进程 / 图像黑屏；从 [整链排障速查](../../../../docs/conventions/整链排障速查.md#preflight) 摘，**不**整篇复制。
4. **冒烟测试单一入口**：`./run_demo.sh test`（或 `python3 tests/run_smoke.py`）→ **5 分钟内全绿**；
   建议内容：几何派生链（`tests/w6_geometry_check.py`）、消息定义、文档断链（`tests/docs_link_check.py`）、索引一致（脚本/ADR 索引 `--check`）、离线单元测试。
   **不是**要求 57 个核查全绿。
5. **真实截图 + GIF**：GUI 全链运行取 **启动 / 跟踪中 / 终态** 三张 PNG（真实画面，非示意图）+
   10–15 s GIF（800px 宽、≤5 MB）落 `docs/plan/assets/`。画面须含 P1-3 状态面板与终态说明。
6. **干净环境验证 ≥1 轮**：在清空 `build/ install/ log/`（**已授权**，先确认无运行中实例）后按 README 从零走一遍；
   记录从 `git clone`（或清理后）到看见画面**耗时**、卡在哪一步、README 哪句不清楚 → **修正 README** → 再走一遍。
7. **完整视频（2–3 min，1080p）**：不入 git；本机无法产出就如实记为未达成并写原因，**不得**用示意图/剪辑冒充。

## 预算

- **N=6** 轮上限；**K=4** 熔断。
- **T1**：**24 次 / 累计 900 秒**（单次 ≤30 s、进程 ≤2、不启 GZ/PX4/GUI、不碰共享状态）；批次内自行分配、逐次留痕。
- **T2**：**4 次 / 累计 ≤3600 秒**，单轮 ≤2 次：
  (a) 1 次干净重建（清 `build/ install/ log/` 后 `colcon build`）；
  (b) 1 次 GUI 运行取三张截图；
  (c) 1 次 GUI 运行录 GIF；
  (d) 1 次干净环境按 README 走通。
  启动前查残留（`./run_demo.sh status`）；同机串行，不得终止他人进程。
- 离线只读检查按 [记账口径](../../../README.md#offline-budget)：总墙钟为主，次数只记账。

## 验收判据（逐项，须给证据路径）

对齐 [P2-1 出口判据](../../../../docs/plan/p2-1-项目交付物.md#p2-1-exit) 10 项：README 存在且含 7 要素 / 真实截图或 GIF 在顶部 /
完整视频（或如实记未达成）/ 结构图与包边界一致 / FAQ ≥5 条覆盖 4 症状 / 冒烟入口 5 分钟内全绿 /
干净环境验证 ≥1 轮并已修正 README / 已知边界 ≥5 条 / 无来源不明第三方资产 / 未发布禁发目录。

## 预登记停止条件（强制）

- **若 3 轮内** README 一稿（含一句话定位、≤3 条快速开始、截图位、状态说明、结构图、已知边界 ≥5 条）未落地 → **停止并报告**；
- **若 T2 4 次 / 3600 秒耗尽** → 停止并报告；
- **若 6 轮内** 10 项判据未全达成 → 判定"当前授权下不可全达成"，提交**假设台账 + 缺口清单**（缺哪几项、各需什么最小追加授权）；
- 连续 **4 轮**无区分性新证据 → **熔断**，交台账。
- 不得以"这是收尾"为由自行扩大白名单、预算或口径；需要时唤醒 Leader。

## 报告与收口

- 批次内每轮自写 `request.md`（只写本轮目标/假设/判别实验/预算消耗），状态保持 `执行中`；
- 批次末 `report.md`：**≤30 行审查摘要**开头 + 实际改动 + 命令/退出码 + 证据路径 + 未执行项 + **假设台账** + 下一轮建议 + 累计预算（含提交笔数）；
- 置 `待审查` 并 `send_message` 唤醒 Leader；**不**开始下一任务、**不** push、**不**自行归档。

---

- Worker 子会话 ID：`7eb40b67-31c3-4a50-b313-e084cf01bdd7`（2026-10-31 派出，来源：Leader）