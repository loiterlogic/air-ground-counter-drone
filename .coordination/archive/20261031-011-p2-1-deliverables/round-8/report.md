# P2-1 · round-8 报告（克隆实测：**路径自定位成立**，但暴露 `run_logger` 同类缺陷）

<a id="p2-1-r8-report"></a>

- 任务 ID：`20261031-011-p2-1-deliverables`，round-8（新批次第 2 轮）
- 执行者：Worker（workbuddy / `deepseek-v4.1-flash` / max）
- **Worker 子会话 ID：`7eb40b67-31c3-4a50-b313-e084cf01bdd7`**
- **父（Leader）会话 ID：`session-c1423390-f175-44e8-a382-fa1b564f7ab5`**
- 起止：2026-10-31T12:03 → 12:18（Asia/Shanghai）
- 状态：**执行中**（**停下报告**：见第 3 节，需裁定）
- 派工：[round-8 request](request.md#p2-1-r8-request)（**Worker 自写**，继承 [round-7 审查](../round-7/review.md#p2-1-r7-review) 第 3 节）

<a id="p2-1-r8-summary"></a>
## 审查摘要（≤30 行）

1. **克隆实测：A 的目标达成**——克隆到 `/tmp/agc-r8-clone`（任意路径）→ 构建 → `doctor` PASS
   → **跑到 `TRACKING_SUCCESS`**，且 `doctor` 报的是**克隆自己的** `install/`。
2. **负向取证成立**：构建前 `doctor` **`exit=1`**，报 **`缺少 /tmp/agc-r8-clone/install/setup.bash`**。
3. **但暴露一个同类新缺陷（**需裁定**）**：`run_logger` 把 `metrics/summary.json` 写到了
   **原仓库** `/home/chen/AGC/experiments/w6-task-eval/...`，**不是克隆自己的**。
   根因：`run_logger.cpp:85` 的 `experiments_root` 默认值硬编码 `"/home/chen/AGC/experiments"`，
   而 `w6.launch.py` **完全没有设置**该参数（grep 计数 0）。
4. **这是我 round-7 分类的误判**：我把 `src/agc_task/config/*.yaml` 里的 `experiments_root` 列为
   "不在 s04 主路径"——实际**主路径走的是 `run_logger.cpp` 的默认值**，同一类问题我漏了一处。
5. **原仓库被污染（如实披露）**：`experiments/demo/` **未新增**（该目录由已修好的 `common.ROOT` 决定）；
   但 `experiments/w6-task-eval/20261031-s04_static_static_obs_track-0-121023-3528/` 是**克隆 run 写的**
   （时间戳 12:10:23 与克隆 run 对应）。**我未删除它**（属原仓库历史产物，删改需授权）。
6. **构建**：克隆内 `colcon build` **9 包 / 308.25 s / exit 0**（与主仓 308.41 s 几乎一致）。
7. **偏离（必须披露）**：`toolchain/` 用符号链接借用主仓已构建工具链
   （`ln -s /home/chen/AGC/toolchain`）——**真实陌生人须按 `toolchain/README` 自建**，成本 README 已写。
8. **预算**：T2 **1 次**（克隆内演示；累计 **11/15**）；T1 0；离线约 20 次。

<a id="p2-1-r8-evidence"></a>
## 1. 克隆实测证据

### 1.1 负向取证（构建前）

```text
/tmp/agc-r8-clone  →  ls install/ 不存在
./run_demo.sh doctor  →  exit=1
  错误：工作区未构建
    缺少 /tmp/agc-r8-clone/install/setup.bash      ← 克隆自己的路径 ✅
    先构建：cd /tmp/agc-r8-clone && colcon build --symlink-install
```

### 1.2 构建与 `doctor`

| 项 | 值 |
|---|---|
| `colcon build` | **9 packages finished / 308.25 s / exit 0** |
| `doctor` | **PASS（0.03 s）/ OK=14** |
| **关键** | `GZ_SIM_SYSTEM_PLUGIN_PATH = /tmp/agc-r8-clone/install/agc_sim/lib` ✅（**克隆自己的**） |

### 1.3 演示跑到终态

| 项 | 值 |
|---|---|
| 终态 | **`TRACKING_SUCCESS` / `tracking_milestone`** ✅ |
| 产物目录 | **`/tmp/agc-r8-clone/experiments/demo/20261031-121006/`** ✅（克隆自己的） |
| 产物内容 | `launch.log` / `panel.txt` / `timeline.txt` / `result.json` / `result.md` / `terminal_explanation.txt` / `evidence/` |
| **原仓库 `experiments/demo/`** | 前后清单**完全一致**（51 → 51，未新增）✅ |

<a id="p2-1-r8-defect"></a>
## 2. 新暴露的缺陷（**需裁定**）

### 2.1 现象

克隆 run 的 `terminal_explanation.txt` 报：

```text
阈值来源  **阈值来源缺失**：未找到 params_applied.yaml 的 task_manager 段
数据缺口  **未取得本 run 的 metrics/summary.json**
```

而 `launch.log` 第 143 行给出真相：

```text
[run_logger] run dir: /home/chen/AGC/experiments/w6-task-eval/20261031-s04_static_static_obs_track-0-121023-3528
```

→ **写到了原仓库**，所以克隆侧的展示层读不到自己 run 的 summary（展示层是对的，它按 `common.ROOT` 找）。

### 2.2 根因

| 位置 | 内容 |
|---|---|
| `src/agc_task/src/run_logger.cpp:85` | `experiments_root_ = declare_parameter<std::string>("experiments_root", "/home/chen/AGC/experiments");` |
| `src/agc_task/launch/w6.launch.py` | **`grep -c experiments_root` = 0** —— 从未设置该参数 → 用 C++ 默认值 |

### 2.3 我 round-7 的误判（如实记）

round-7 报告 §1.3 把 `src/agc_task/config/*.yaml` 的 `experiments_root`（6 处）归为
"不在 s04 主路径上 → 可保留"。**这个判断错了**：那些 yaml 确实不在 s04 主路径，
**但主路径用的是 `run_logger.cpp` 的 C++ 默认值**，同类问题我漏了一处。

> 教训：分类"哪些路径参与运行期解析"时，**不能只看 Python/launch 层**，
> 还要查 **C++ 节点的 `declare_parameter` 默认值**——它同样在运行期决定写盘位置。

### 2.4 修法选项（**供裁定**）

| 方案 | 做法 | 改动面 | 评价 |
|---|---|---|---|
| **α** | `w6.launch.py` 把 `experiments_root` 显式传给 `run_logger`（值来自 `agc_root` 参数） | `w6.launch.py` 1 处（**白名单内**） | **最小**；不改 C++；`agc_root` 已有自定位链路 |
| **β** | `run_logger.cpp` 的默认值改为从环境变量/参数推导 | C++ 1 处（**不在白名单**） | 更彻底，但要改 C++ + 重编 |
| **γ** | 两者都做 | 2 处 | 最稳，成本最高 |
| **δ** | 不改，只在 README 登记"克隆内 summary 会落原仓库" | 0 | **不可接受**：等于承认克隆跑不通 |

**我的建议**：**α**（白名单内 1 处，且 `agc_root` 自定位链路已就绪）。
若你要彻底（β/γ），需追加白名单到 `src/agc_task/src/run_logger.cpp`。

<a id="p2-1-r8-pollution"></a>
## 3. 原仓库污染（如实披露，未自行删除）

| 项 | 事实 |
|---|---|
| 被写目录 | `/home/chen/AGC/experiments/w6-task-eval/20261031-s04_static_static_obs_track-0-121023-3528/`（含 `config/` + `metrics/`） |
| 写入者 | **克隆 run 的 `run_logger`**（时间戳 12:10:23 对应克隆运行） |
| 处置 | **未删除**——它是原仓库历史产物目录，删改需授权；且 `experiments/` 不入 git，不影响仓库完整性 |
| 影响 | 原仓库多一个 run 目录；**不影响任何已验收证据**（该目录是本轮新产生的） |

<a id="p2-1-r8-deviation"></a>
## 4. 偏离（必须披露）

**`toolchain/` 用符号链接借用主仓**：`ln -s /home/chen/AGC/toolchain <clone>/toolchain`。

- **理由**：克隆目录**没有 `toolchain/`**（`.gitignore` 只放行 README），而演示依赖 PX4 SITL；
  Leader 已在 round-7 审查 §3 预判并给出该处置。
- **不可当作可复现**：**真实陌生人**须按 [`toolchain/README`](../../../toolchain/README.md) 自建
  （源码 SHA / 构建配方 / 依赖版本都在那里），成本**另计**（README 只写了 `colcon build` 的 5–6 分钟）。
- 本次克隆实测**证明的是"路径自定位成立"**，**不是**"新机器 10 分钟可跑"（toolchain 自建时间未测）。

<a id="p2-1-r8-budget"></a>
## 5. 预算消耗

| 项 | 授权 | 本轮 | 累计 |
|---|---|---|---|
| 轮次 | N=4 | 2 | 余 2 |
| **T2** | 上限 15 | **1**（克隆内演示） | **11**（余 4） |
| T1 | 批次余量 | 0 | |
| 离线只读 | 记账 | ~20 | |

**红线自检**：未碰 `/dev/shm` ✅ · 未处置他人进程 ✅ · 未写 `~/.gz` ✅ ·
未改契约默认值 ✅ · **未顺手改源码**（发现缺陷即停）✅ · 未用旧图/示意图 ✅ ·
未包装未达成项（summary 缺失已如实报）✅ · 删除克隆前**回显绝对路径确认** ✅。

<a id="p2-1-r8-next"></a>
## 6. 下一轮建议

**先裁定 §2.4 的 α/β/γ/δ**，再执行 round-9：

- 若 **α**：改 `w6.launch.py` 1 处（白名单内）→ 克隆复验（**需 T2 1 次**，重跑一次克隆演示，
  验证 summary 落**克隆自己的** `experiments/w6-task-eval/`）；
- 若 **β/γ**：需**追加白名单** `src/agc_task/src/run_logger.cpp` + 重编（构建 ~5 min）；
- round-9 原计划（用户视频接入 + 判据全勾）**顺延**，且视频文件仍未到。

**最小追加授权请求**：若选 α，**T2 +1 次**（克隆复验）+ **1 轮**；白名单无需扩。
