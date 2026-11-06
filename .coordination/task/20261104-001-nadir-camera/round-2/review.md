<a id="review"></a>
# 机载俯视相机 · round-2 Leader 独立审查

- 审查时间：`2026-11-04T21:40:00+08:00`（Asia/Shanghai）
- 审查者：Leader
- 被审：`.coordination/task/20261104-001-nadir-camera/round-2/report.md`（轮末状态 `待审查`）
- 审查方式：**不采信自述**，逐条重跑命令、重读原始证据、亲验图像

## 一、独立复验（我亲自执行的命令与读数）

| 判据 | 我执行的核查 | 结果 |
|---|---|---|
| A5 pytest | `pytest scripts/tests/test_nadir_camera_contract.py -q` | **12 passed** |
| A6 索引 | `python3 scripts/adr_index.py --check` | **PASS：与 30 篇一致** |
| A6 链接 | `python3 tests/docs_link_check.py` | **PASS：活跃文档无断链**（本地保留路径 3 条，已单列） |
| A6 plan 删除 | `ls docs/plan/*.md` | `无人机俯视相机.md` **已删**，其余 7 个 plan 未受影响 |
| A1 0 帧 | 读 `20261104-nadir-arm-a-default-probe/probe-stdout.txt` | `frames_received: 0` / `elapsed_s: 45.02` |
| A1 模型 | 该 probe 的 `launch.log` | `model name: x500_0, simulation model: x500` ⇒ **确为默认臂** |
| A1 终态 | 读 `20261104-nadir-arm-a1/metrics/report.md` | `TRACKING_SUCCESS` / `tracking_milestone` / **pass=True** |
| A2 机型解析 | 读 `arm-a1` 与 `arm-b4` 的 `launch.log` | `SYS_AUTOSTART=4001` 两臂均出现；`b4` 为 `model name: agc_x500_nadir_0, simulation model: agc_x500_nadir` |
| A3 出帧 | 读 `arm-b4/probe-stdout.txt` | `frames_received: 144`、`hz_median: 28.4949`、`elapsed_s: 50.05`、`fx=fy=268.6016` |
| A3 PNG | `ls arm-b4/frames/*.png` | **8 张** |
| A4 是地面 | **我亲自 `read_image` 打开 `frame_004.png`** | 目视确认：地面标线、建筑投影、管道、机体自影——**是地面，不是天空** |
| A7 无耦合 | `grep -rn nadir src/ \| grep create_subscription` | **零命中**（nadir 无任何订阅者） |
| A7 发布者 | `pytest -k targets` | 1 passed |
| A8 toolchain | `git status --short toolchain/` + `ls -la` mtime | 仅 `README.md` 显示 M，**mtime 11-03 09:26**，早于本轮（19:08）⇒ 既有脏改动，**非本轮** |
| A8 契约 | mtime 核查 | `docs/ROS2迁移交接文档.md` **mtime 16:20**，早于本轮 ⇒ **未改** |
| A8 launch 参数 | `pytest scripts/tests/test_branch_ledger.py -q` | **4 passed**（无表外分支参数） |
| §7.1 数字 | 读 GSD 表原文 | 表格数字**一个未动**（5.2 / 7.8 / 1.49× 原样） |
| 环境收尾 | `ps -ef \| grep -E "gz sim\|px4\|MicroXRCE"` | **0 个**；`sim.lock` FREE |

## 二、通过项

1. **A1 对照成立且判据正确**。0 帧证据来自默认臂 `x500_0`，且该 run 的 `gz topic -l` **仍列出**
   `/agc/air/nadir*`——Worker **没有**拿话题列表当证据，而是用真实帧数，这正是仓库
   `bridge.yaml` 与 P1-4 记录里反复强调的"话题存在 ≠ 有帧"。判据选择正确。
2. **A3/A4 扎实**。144 帧 / 28.49 Hz / `fx=fy=268.60`（推导 268.51，差 0.03%）三者自洽；
   图像我亲眼看过多张，确为地面。
3. **pitch 符号的纠错闭环完整**。ADR-0030 §3 写清"90° 是下俯量、字段 +1.5708"并留了纠错记录；
   离线闸门**双断言**（数值 + 有效光轴 z≈−1），且 Worker 用**变异测试**证明闸门真会红——
   这是本轮方法论上最有价值的一条。
4. **A8 边界守住**。toolchain / 契约 mtime 均早于本轮，非本轮改动；无新 launch 参数。
5. **如实披露**。主动登记了 3 件对自己不利的事（进程泄漏、B 臂 infra 失败、探针丢失），
   且泄漏后按 PID 清理、**未用 `pkill -f`**、未碰他人的 159340/159341。按
   [协作规则「不因披露而加重」](../../README.md#review)，这属于已履行如实义务，**不扣分**。

## 三、问题（不阻塞验收，但须登记）

| # | 问题 | 影响 | 处置 |
|---|---|---|---|
| P1 | **A1 的"0 帧"与"终态"来自两个不同 run**（probe 是 `run_demo` 风格直启、未发 `/agc/task/start`；终态来自 `episode_runner` 的 a1） | 不构成事实错误——两者本就测不同命题；但**不可合并表述为"同一 run 同时满足"** | 已在 report 第五节如实分开；本审查沿用该分列。**不返工** |
| P2 | **`/dev/shm` 每轮结束 184–200 段，贴阈值** | 连续多轮会越阈、拖慢 DDS 发现 | 已由用户裁定改为**串行**；B 链开跑前须先确认 shm < 200，超阈先报 Leader |
| P3 | `w6.launch.py` 的 150 行 diff 中仅 15 行属本轮 | 审查易误记 | report 已如实登记；本审查确认 |

## 四、结论

**验收通过（A1–A8 全部达成）。** 本链可结档。

**理由**：8 条判据均有我独立复跑或亲验的原始证据支撑；唯一的两处瑕疵（P1 分列、P2 环境）
都不是事实错误或判据削弱，且均已如实登记。

## 五、结档动作（Leader 执行）

1. 合并 Worker 提交的 `README.md`「已知边界」文本（Worker 按约束未改，由 Leader 合并）。
2. `CURRENT.md` 置 A 链 `已验收`，并解冻 B 链。
3. 逐轮台账归档（`task/20261104-001-nadir-camera/` → 删除，结论已进 ADR-0030 / §7.1 / README）。
4. 释放独占资源，通知 B 链进入 T2。
