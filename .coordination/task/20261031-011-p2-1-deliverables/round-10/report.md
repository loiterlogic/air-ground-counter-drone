# P2-1 · round-10 报告（克隆复验：**里程碑达成**，修复已完整证明）

<a id="p2-1-r10-report"></a>

- 任务 ID：`20261031-011-p2-1-deliverables`，round-10（**本批次最后一轮，N=4 用满**）
- 执行者：Worker（workbuddy / `deepseek-v4.1-flash` / max）
- **Worker 子会话 ID：`7eb40b67-31c3-4a50-b313-e084cf01bdd7`**
- **父（Leader）会话 ID：`session-c1423390-f175-44e8-a382-fa1b564f7ab5`**
- 起止：2026-10-31T14:02 → 14:15（Asia/Shanghai）
- 状态：**待审查**（**里程碑达成**）
- 派工：[round-10 request](request.md#p2-1-r10-request)（**Worker 自写**，继承 [round-9 审查](../round-9/review.md#p2-1-r9-review)）

<a id="p2-1-r10-summary"></a>
## 审查摘要（≤30 行）

1. **结论：克隆复验五项全部通过，修复已完整证明**——不是"再跑通一次"，而是**三类来源都指向克隆**。
2. **克隆**：`/tmp/agc-r10-clone`，HEAD **`61374f7`**（含 α+ 修复），任意路径。
3. **负向取证**：构建前 `doctor` **`exit=1`**，报 **`缺少 /tmp/agc-r10-clone/install/setup.bash`**。
4. **构建**：**9 包 / 359.92 s / exit 0**；之后 `doctor` **PASS（0.03 s）**，
   `GZ_SIM_SYSTEM_PLUGIN_PATH = /tmp/agc-r10-clone/install/agc_sim/lib`。
5. **演示**：默认 GUI → **`TRACKING_SUCCESS` / `tracking_milestone`**；
   `launch.log` 的 **`agc_root:=/tmp/agc-r10-clone`**。
6. **五项验证（逐项原始证据）**：

   | # | 验证项 | 结果 |
   |---|---|---|
   | ① | summary.json 存在于克隆且有效 | ✅ 7916 B，`terminal_state=TRACKING_SUCCESS` / `reason=tracking_milestone`，49 键 |
   | ② | `config/params.yaml` 的 `experiments_root` 指向克隆 | ✅ `/tmp/agc-r10-clone/experiments` |
   | ③ | git 身份指向克隆 | ✅ `fingerprint.git_head` = `git_head.txt` = **克隆 HEAD `61374f77…`** |
   | ④ | `terminal_explanation.txt` 正常读 summary/阈值/终态 | ✅ 阈值来自 `params_applied.yaml`；**不再报"未取得本轮 summary"（0 处）** |
   | ⑤ | 主仓零新增 | ✅ `demo` **51→51**、`w6-task-eval` **1102→1102** |

7. **残留进程**：核查 **0**（`install/agc_` / `MicroXRCEAgent` / `px4_sitl` / `gz sim` / `parameter_bridge` / `rviz2`）。
8. **偏离（继续明确披露）**：`toolchain/` 用软链借用主仓 → 本次证明的是
   **"克隆到任意路径后，写盘根与 Git 身份都跟随克隆"**，**不是**"新机器 10 分钟可跑"
   （陌生人仍须按 [`toolchain/README`](../../../toolchain/README.md) 自建 PX4，成本另计）。
9. **预算**：T2 **1 次**（累计 **12/15**，余 3）；T1 0；离线约 22 次。**N=4 用满**。
10. **证据**：`experiments/p2-1/round-10/`（`verify-evidence.txt` / `neg-doctor-before-build.log` /
    `doctor-after-build.log` / `build.log` / `demo.log` / `terminal_explanation.txt`）。

<a id="p2-1-r10-details"></a>
## 1. 命令、退出码与耗时

| 步骤 | 命令 | 退出码 | 耗时 |
|---|---|---|---|
| 克隆 | `git clone /home/chen/AGC /tmp/agc-r10-clone` | 0 | — |
| 借 toolchain（偏离） | `ln -s /home/chen/AGC/toolchain toolchain` | 0 | — |
| **负向取证** | `cd /tmp/agc-r10-clone && ./run_demo.sh doctor` | **1** | 0.02 s |
| 构建 | `colcon build --symlink-install` | **0** | **359.92 s**（9 包） |
| doctor | `./run_demo.sh doctor` | **0** | 0.03 s |
| 演示 | `./run_demo.sh`（默认 GUI） | **0** | ~1 min 13 s（含 25/35 s 错峰） |

**路径**：克隆 `/tmp/agc-r10-clone`；主仓 `/home/chen/AGC`。
**run id**：`20261031-s04_static_static_obs_track-0-140941-9603`。

<a id="p2-1-r10-five"></a>
## 2. 五项验证（原始证据）

### ① summary.json 存在于**克隆**且有效

```text
-rw-r--r-- 1 chen chen 7916 Oct 31 14:10 \
  /tmp/agc-r10-clone/experiments/w6-task-eval/20261031-s04_static_static_obs_track-0-140941-9603/metrics/summary.json
terminal_state: TRACKING_SUCCESS   reason: tracking_milestone   键数: 49
```

> **对比 round-8 的失败态**：当时该文件落在 `/home/chen/AGC/experiments/w6-task-eval/…`，
> 克隆侧完全取不到 → `terminal_explanation.txt` 报"未取得本轮 summary"。

### ② `config/params.yaml` 的 `experiments_root` 指向**克隆**

```text
experiments_root: /tmp/agc-r10-clone/experiments
```

即 `w6.launch.py` 的 `os.path.join(_agc_root, 'experiments')` 派生链**在真实运行中生效**
（YAML 已删键，C++ 默认值被 launch 覆盖）。

### ③ Git 身份指向**克隆**

```text
config/workspace_fingerprint.json → git_head: 61374f7749ff1eeda42b1b0e9f17d5d086fb2d61
config/git_head.txt              →          61374f7749ff1eeda42b1b0e9f17d5d086fb2d61
克隆 HEAD (git rev-parse HEAD)   →          61374f7749ff1eeda42b1b0e9f17d5d086fb2d61
```

三者**完全一致** → `git_root` 派生（`'git_root': _agc_root`）生效，不再读主仓。

> 说明：`workspace_fingerprint.json` **没有 `code_root` 键**（Leader 派工里写的字段名在本仓实际不存在）；
> 实际可用字段是 `git_head` / `dirty` / `status_entries` / `diff_sha256` / `fingerprint_sha256`。
> 我用 **`git_head` + `git_head.txt` + 克隆 HEAD 三方比对**，比 `code_root` 更直接。

### ④ `terminal_explanation.txt` 正常读取

```text
结果      TRACKING_SUCCESS — 抵近并持续跟踪成功
触发原因  tracking_milestone — 目标在跟踪距离内连续驻留达到判定时长（跟踪里程碑）
判定阈值  d_track_m=3 / t_dwell_s=3 / t_max_s=120 / tracking_milestone_is_terminal=是
阈值来源  params_applied.yaml（task_manager 段，本 run 实际生效参数）
数据源    /tmp/agc-r10-clone/experiments/w6-task-eval/…-140941-9603/metrics/summary.json
```

- 阈值**读到了**（round-8 时是"阈值来源缺失"）；
- 数据源指向**克隆**；
- **"未取得本轮 summary" 出现 0 次**（round-8 有）。

### ⑤ 主仓零新增

| 目录 | 前 | 后 | 结论 |
|---|---|---|---|
| `experiments/demo/` | 51 | 51 | ✅ **零新增** |
| `experiments/w6-task-eval/` | 1102 | 1102 | ✅ **零新增** |

清单用 `ls | sort` 前后 diff，**无差异**。

<a id="p2-1-r10-residual"></a>
## 3. 残留进程核查

```bash
ps -eo pid,cmd | grep -E "[i]nstall/agc_|[M]icroXRCEAgent|[p]x4_sitl|gz sim|[p]arameter_bridge|[r]viz2"
```

→ **0 条**（回收正常）。

<a id="p2-1-r10-deviation"></a>
## 4. 偏离（必须披露）

**`toolchain/` 用符号链接借用主仓**：`ln -s /home/chen/AGC/toolchain <clone>/toolchain`。

- **理由**：克隆目录没有 `toolchain/`（`.gitignore` 只放行 README），而演示依赖 PX4 SITL；
  Leader 在 round-7 审查 §3 预判并给出该处置，round-8 同样处理。
- **本次证明的边界**：**"克隆到任意路径后，写盘根与 Git 身份都跟随克隆"**（这是 P2-1 要修的）；
  **不是**"新机器 10 分钟可跑"——陌生人仍须按 [`toolchain/README`](../../../toolchain/README.md)
  自建 PX4，**这笔成本未在本次测量范围内**。
- 副作用：`workspace_fingerprint.dirty = true`（软链使工作树显示为脏）。这是**软链造成的**，
  不代表克隆仓库有未提交改动（`git status` 只多出那个 `toolchain` 符号链接）。

<a id="p2-1-r10-budget"></a>
## 5. 预算消耗（累计）

| 项 | 授权 | r1–r8 | r9 | r10 | **累计** |
|---|---|---|---|---|---|
| 轮次 | 6 + 4 = 10 | 8 | 1 | 1 | **10（两批次均用满）** |
| **T2 次数** | 15 | 11 | 0 | **1** | **12**（余 3） |
| T2 墙钟 | 9000 s | — | 0 | ~7 min | 约 43 min |
| T1 | 24 / 900 s | 0 | 0 | 0 | **0** |
| 离线只读 | 记账 | ~150 | ~25 | ~22 | **~197** |

**红线自检**：未碰 `/dev/shm` ✅ · 未处置他人进程 ✅ · 未写 `~/.gz` ✅ ·
未改 C++ 默认声明 ✅ · 未改契约默认值 ✅ · 未用旧图/示意图 ✅ · 未包装未达成项 ✅ ·
**删除克隆前回显绝对路径确认** ✅ · 未 push ✅ · 未归档 ✅。

<a id="p2-1-r10-conclusion"></a>
## 6. 结论与待办

**修复已完整证明**：round-6 发现的"陌生人克隆实质不成立"→ round-7 路径自定位 →
round-8 暴露 `run_logger` 同类缺陷 → round-9 三类来源整类修 → **round-10 克隆复验五项全过**。

| 待办 | 状态 |
|---|---|
| 完整演示视频（P2-1 判据第 3 项） | ⏳ **等用户自录文件**（不占轮次/T2） |
| P2-1 判据第 3 项勾选 | ⏳ 待视频到位 |
| 任务结档 / 归档 | ⏳ **Leader 审查后**，Worker 不自行归档 |

**本批次 N=4 已用满**，不再自行开轮。
