# P2-1 · round-6 报告（**批次最后一轮**：干净环境验证 + README 回改 + 判据勾选）

<a id="p2-1-r6-report"></a>

- 任务 ID：`20261031-011-p2-1-deliverables`，round-6（**批次最后一轮，N=6 用满**）
- 执行者：Worker（workbuddy / `deepseek-v4.1-flash` / max）
- **Worker 子会话 ID：`7eb40b67-31c3-4a50-b313-e084cf01bdd7`**
- **父（Leader）会话 ID：`session-c1423390-f175-44e8-a382-fa1b564f7ab5`**
- 起止：2026-10-31T11:37 → 11:55（Asia/Shanghai）
- 状态：**执行中**（批次末，**停下报告**——见第 4 节，需 Leader 裁定）
- 派工：[round-6 request](request.md#p2-1-r6-request)（**Worker 自写**）

<a id="p2-1-r6-summary"></a>
## 审查摘要（≤30 行）

1. **干净环境验证成功**：清 `build/ install/ log/` → `colcon build` **9 包 / 308.41 s / exit 0**
   → 按 README 走 `doctor`（**14/14 PASS / 0.02 s**）→ 默认演示到 **`TRACKING_SUCCESS`**。
   **清理→终态总耗时 6.5 分钟**（build 5.4 + 演示 1.1）。
2. **发现 3 个真实卡点并已回改 README**（详见 §3）：toolchain 怎么备、构建耗时预期、
   **脚本路径硬编码**。
3. **最重要的新发现（**需你裁定**）：`run_demo.sh` 与 `scripts/demo/common.py` 硬编码
   `ROOT = '/home/chen/AGC'`（全仓 **68 处**，交付路径约 10 处）。**在别处 clone 后直接跑会操作
   原仓库**，而 `doctor` 会**误报 PASS 14/14**（它查的是那个绝对路径下的 `install/`）。
   → 这是"陌生人照 README 能跑起来"判据的**真实障碍**，**必须改代码**才能修；
   按你的停止条件，我**停下报告**，未擅自改。
4. **P2-1 出口判据已勾选**：**9 项达成、1 项（完整演示视频）如实未勾**
   （注明"由用户录制，路径待提供"）。
5. README 已按你要求补图注（Gazebo 3D 视图 + 状态面板在终端/视频）与**已知边界第 7 条**
   （路径不可移植）。
6. **预算**：T2 **1 次**（批次累计 **10/12**）；T1 0；离线约 18 次。**N=6 已用满**。
7. **本轮未取新图**（按 request 禁令），三图 + GIF 仍为 round-5 定稿版本。

<a id="p2-1-r6-walkthrough"></a>
## 1. 干净环境验证（可复核证据）

证据目录：`experiments/p2-1/round-6/`（`clean-start.txt` / `build.log` / `walkthrough-demo.log` / `walkthrough-start.txt` / `demo-start.txt`）。

### 1.1 耗时表

| 阶段 | 起点 | 耗时 | 说明 |
|---|---|---|---|
| **清理** | 11:38:24 | — | `rm -rf build install log`（先确认无实例、无残留进程） |
| **`colcon build`** | 11:38:24 | **308.41 s（5 min 08 s）** | 9 包全过 / exit 0；`agc_task` 1 处既有 deprecation |
| **`doctor`** | 11:43:42 | **0.02 s** | 14/14 PASS（预算 30 s） |
| **默认演示 → 终态** | 11:43:49 | **~1 min 05 s** | 含 25/35 s PX4 错峰；`TRACKING_SUCCESS` |
| **清理 → 看见画面并到终态** | — | **6.5 分钟（393 s）** | 陌生人从零到"跑完一次"的真实数字 |

> 对比 round-1 的干净重建（6 min 32 s），本次 **5 min 08 s** 略快（ccache/包缓存仍在，非纯冷启动）。
> **纯冷启动（新机器无 ccache）会更慢**，README 已写"首次约 5–6 分钟"作为预期。

### 1.2 验证结果

| 项 | 结果 |
|---|---|
| `colcon build` | **9 packages finished [4min 57s] / exit 0** |
| `./run_demo.sh doctor` | **PASS（0.02 s）/ OK=14** |
| `./run_demo.sh`（默认参数） | **`TRACKING_SUCCESS` / `tracking_milestone`** |
| 回收 | 36 进程 / 残留 **0**（6.7 s） |
| 终态判定说明 | `期望 TRACKING_SUCCESS → 一致`；`reset_failure_rate=0`；`visibility_rate=0.982` |

<a id="p2-1-r6-blockers"></a>
## 2. 三个卡点（README 已回改）

| # | 卡点（陌生人视角） | 证据 | README 回改 |
|---|---|---|---|
| 1 | **`toolchain/` 是空的**，但 README 只说"已备" | 新 clone 实测：`ls toolchain/` → 只有 `README.md`；`.gitignore` 仅放行它 | 前提段改为**三条清单**，第 3 条明确"该目录不纳入版本控制，新 clone 里是空的，按 `toolchain/README` 自行构建" |
| 2 | **不知道构建要多久** | 实测 308 s | 前提第 2 条写明"首次约 5–6 分钟，9 个包" |
| 3 | **路径硬编码，clone 到别处会操作原仓库** | 见 §3 实测 | 前提段加 ⚠ 说明 + **已知边界第 7 条** |

<a id="p2-1-r6-hardcode"></a>
## 3. **关键发现：脚本路径硬编码（需裁定）**

### 3.1 实测（我做了"陌生人克隆"验证）

```bash
git clone /home/chen/AGC /tmp/agc-clone-test
cd /tmp/agc-clone-test && ./run_demo.sh doctor
```

| 观察 | 结果 |
|---|---|
| 克隆目录里有没有 `install/` | **没有**（确认） |
| `doctor` 报什么 | **PASS 14/14**（**误报**） |
| `doctor` 指的路径 | `GZ_SIM_SYSTEM_PLUGIN_PATH = /home/chen/AGC/install/agc_sim/lib`、`世界文件 = install/agc_sim/...` —— **全是原仓库路径** |
| 直接跑 `./run_demo.sh --duration 5` | 启动了**原仓库**的仿真（证据：产物落 `/home/chen/AGC/experiments/demo/20261031-114605`），不是克隆目录的 |

### 3.2 根因

| 文件 | 代码 | 影响 |
|---|---|---|
| `run_demo.sh:32` | `ROOT="/home/chen/AGC"` | 所有子命令（doctor/start/stop/status/test）都指向原仓库 |
| `scripts/demo/common.py:28` | `ROOT = '/home/chen/AGC'` | 产物目录、世界 SDF、插件路径全部固定 |
| 全仓 | **68 处** `'/home/chen/AGC'`（交付路径约 10 处，其余在 `scripts/research/`、`tests/`） | 改一处不够，需统一策略 |

### 3.3 为什么这构成**阻塞**（而不是我自行修）

- **需要改代码**（不是 README 措辞），且**超出本单白名单**：
  `run_demo.sh`、`scripts/demo/**` 在白名单内（可修），但
  `scripts/episode_runner.py`、`scripts/evidence_archive.py`、`tests/*.py` 等**不在**；
- 修法有多种，取舍不同（见下），**属"改变实现口径"**，按 [协作规则](../../../README.md#executor-autonomy)
  应交 Leader 裁定；
- 你的 round-6 停止条件原文：**"若干净环境验证暴露出改代码才能修的问题（不只是 README 措辞），
  先停并报告"** —— 我照此执行。

### 3.4 可选修法（**供裁定**）

| 方案 | 做法 | 改动面 | 风险 |
|---|---|---|---|
| **A** | `run_demo.sh` / `common.py` 改为**自定位**：`ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"`；`common.py` 用 `os.path.dirname(os.path.dirname(os.path.dirname(__file__)))` | 2 处（白名单内） | 最小、最干净；`research/` 与 `tests/` 的 68 处**暂不动**（它们不参与 README 路径） |
| **B** | A + 全仓替换 68 处 | 68 处 | 动到 `tests/` 与 `research/`，回归面大，需重跑验收 |
| **C** | 不改代码，只在 README 写明"必须放 `/home/chen/AGC`" | 0 处代码 | **判据"陌生人能跑起来"实质不成立**——照 README 走仍会踩坑（除非读者恰好也放该路径） |
| **D** | A + 加一条回归：`test_demo_entry.py` 断言 `ROOT` 来自自定位而非字面量 | 3 处 | 防复发，与 A 同批 |

**我的建议**：**A + D**（白名单内、最小改动、可回归）。若你要"彻底可移植"再考虑 B。

> **注意**：方案 C 等于承认判据不达标。当前 README 已如实写明该限制，**不假装可移植**。

<a id="p2-1-r6-readme"></a>
## 4. README 改动摘要

| 位置 | 改动 |
|---|---|
| `## 快速开始` 前提段 | 由 1 句改为**三条清单**（ROS / 构建 / toolchain），并写明构建耗时与 toolchain 不在版本控制 |
| 前提段后 | 新增 ⚠ **路径硬编码**说明（本仓脚本假定 `/home/chen/AGC`；别处 clone 会操作原仓库、doctor 可能误报） |
| `## 演示看到什么` 图注 | 补：图为 **Gazebo 3D 视图**（自然运行、正俯视 85 m）；**状态面板在终端**（2 Hz 面板 + `timeline.txt`/`panel.txt`），完整视频由用户录制；**图里看不到状态不代表系统没报状态** |
| `## 已知边界` | 新增**第 7 条**：脚本路径不可移植（`/home/chen/AGC` 硬编码，全仓 68 处、交付路径约 10 处） |

**未改**：任何契约表述、任何"未来将实现"承诺（0 处）。

<a id="p2-1-r6-exit"></a>
## 5. P2-1 出口判据勾选结果

已写入 [`docs/plan/p2-1-项目交付物.md#p2-1-exit`](../../../docs/plan/p2-1-项目交付物.md#p2-1-exit)：

| # | 判据 | 状态 |
|---|---|---|
| 1 | README 7 要素 | ✅ |
| 2 | 截图/GIF 真实画面、顶部可见 | ✅ |
| 3 | **完整演示视频** | ❌ **未达成**（用户自录、路径待提供；本机无 ffmpeg/gst、GUI 无录制插件） |
| 4 | 结构图与包边界一致 | ✅ |
| 5 | FAQ ≥5 条覆盖 4 症状 | ✅（8 条） |
| 6 | 冒烟集单一入口 ≤5 min 全绿 | ✅（25.45 s） |
| 7 | 干净环境验证 ≥1 轮 + README 已改 | ✅（本轮，6.5 min，3 卡点已回改） |
| 8 | 已知边界 ≥4 条 | ✅（**7 条**） |
| 9 | 无来源不明第三方资产 | ✅（`third_party_asset_check` PASS=26 FAIL=0） |
| 10 | 未发布禁发目录 | ✅（每次提交正则核过，0 命中） |

**9/10 达成**；第 3 项如实留空并注明原因，**未包装成达成**。

<a id="p2-1-r6-budget"></a>
## 6. 预算消耗（批次累计）

| 项 | 授权 | r1 | r2 | r3 | r4 | r5 | r6 | **累计** |
|---|---|---|---|---|---|---|---|---|
| 轮次 | **6** | 1 | 1 | 1 | 1 | 1 | 1 | **6（用满）** |
| **T2 次数** | **12** | 2 | 3 | 1 | 2 | 1 | **1** | **10**（余 2） |
| T2 墙钟 | 7800 s | 8'21" | 6'40" | 1'45" | 4'30" | 2'10" | 6'34" | **30'00"** |
| T1 | 24 / 900 s | 0 | 0 | 0 | 0 | 0 | 0 | **0** |
| 离线只读 | 记账 | ~46 | ~28 | ~14 | ~31 | ~24 | ~18 | **~161** |

**禁令遵守自检**：未清 `/dev/shm` ✅ · 未处置他人进程 ✅ · 未改 SDF ✅ · 未写 `~/.gz` ✅ ·
未取新图（按 request）✅ · 未碰视频 ✅ · **未自行改代码**（按停止条件）✅。

<a id="p2-1-r6-hypotheses"></a>
## 7. 批次末假设台账（H1–H12）

| 假设 | 状态 | 判别实验 | 所需授权 |
|---|---|---|---|
| H1 Wayland 下系统工具无法截 GUI | ✅ 已证实 | 4 类工具 + 2 类 X11 抓屏 | — |
| H2 Gazebo `Screenshot` 插件可取真实帧 | ✅ 已证实 | r2/r4/r5 取到真帧 | — |
| H3 `data`=目录、存盘异步 | ✅ 已证实 | 上游源码 + 实测 | — |
| H4 运行期轮询可覆盖三阶段 | ✅ 已证实 | r4/r5 三图三时刻 | — |
| H5 取的是"场景第一个相机" | ❌ **已证伪**（r3 更正为 H-C） | — | — |
| H-A `--gui-config` 未被解析 | ❌ 已证伪 | r2 有 `Loading config` 行 | — |
| H-B 开关生效但相机选择错 | ❌ 已证伪 | r3 位姿一致 | — |
| H-C 两层配置后加载覆盖视角 | ✅ 已证实（**独立成立**） | r2 两行 `Loading config` | — |
| H-D 自然运行 SDF 无 Screenshot → 0 帧 | ✅ 已证实 → **α 已消除** | r3 → r4 | — |
| H-E α 后自然运行可取帧 | ✅ 已证实 | r4/r5 | — |
| H-F 三图可覆盖三阶段 | ⚠ **部分**（时刻可区分、画面差异 0.02–0.04%） | r5 | — |
| H-G 1 Hz 帧可做合规 GIF | ✅ 已证实 | r4/r5 | — |
| H-H `Screenshot` 取 GUI 实时相机（拖动即变） | ✅ 已证实 | r4 跳变帧差 41.4 | — |
| H-I/J 118→85 m 让作业区更满 | ✅ 已证实生效 | r5 边缘位置对比 | — |
| H-L 收尾崩溃可被静态回归拦住 | ✅ 已证实（反向对照 2 failed） | r5 | — |
| **H-M 脚本路径硬编码阻碍"陌生人跑起来"** | ✅ **已证实**（克隆实测：doctor 误报、产物落原仓库） | r6 | **需裁定 A/B/C/D** |
| H-N 纯冷启动构建耗时 | **未验证**（本机有 ccache；实测 308 s 含缓存） | 需新机器 | — |

<a id="p2-1-r6-next"></a>
## 8. 下一轮建议（**批次已用满 N=6，需追加授权**）

**必须你裁定 H-M（路径硬编码）**，否则"陌生人照 README 能跑起来"这条判据**实质不成立**。

若追加授权，建议 round-7：

1. **修 A + D**（`run_demo.sh` / `common.py` 自定位 + 回归断言不出现字面量）——白名单内 2–3 处；
2. 复跑 `./run_demo.sh test` 全绿 + `scripts/tests` 全绿；
3. **复验**：在 `/tmp/agc-clone-test` 再克隆一次 → `doctor` 应能**正确报告缺 install/**（而非误报 PASS）；
4. 若需要"彻底可移植"再考虑 B（68 处，需重跑全部验收）。

**最小追加授权请求**：**1 轮 / T2 0 次**（纯离线代码改动 + 离线复验，不需要起仿真）。
若你要求"克隆目录能真正跑起来"，则需 **T2 1 次**（在克隆目录起一次演示验证）。

**其余待办**：完整演示视频（用户自录，路径待提供）——**不占轮次、不占 T2**。
