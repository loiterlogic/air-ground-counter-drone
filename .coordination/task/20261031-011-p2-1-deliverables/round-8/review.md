# P2-1 · round-8 审查（克隆实测）——路径自定位成立；同类缺陷裁定 α+

<a id="p2-1-r8-review"></a>

- 被审：[round-8 report](report.md#p2-1-r8-report) · 审查人：Leader（DSH） · 2026-10-31
- 裁定：**核心目标达成**；`run_logger` 同类缺陷按 **α+（整类修）** 处理；原仓库污染目录**授权迁移**

## 1. 核心证据（我复核）

| 项 | 结果 |
|---|---|
| 任意路径克隆 | `/tmp/agc-r8-clone` ✅ |
| 负向取证（构建前） | `doctor` **exit=1**、报**克隆自己的** `install/setup.bash` ✅（round-6 的误报消失） |
| 克隆内构建 | 9 包 / 308.25 s / exit 0（主仓 308.41 s，一致）✅ |
| 构建后 `doctor` | PASS，`GZ_SIM_SYSTEM_PLUGIN_PATH` 指向克隆 ✅ |
| 默认 GUI 演示 | `TRACKING_SUCCESS`，产物落**克隆自己**的 `experiments/demo/` ✅ |
| 原仓库 `experiments/demo/` | 51 → 51，**未新增** ✅ |

## 2. 新缺陷（我独立复核，确认存在且属同类）

```text
src/agc_task/src/run_logger.cpp:85  experiments_root 默认 "/home/chen/AGC/experiments"
src/agc_task/src/run_logger.cpp:86  git_root         默认 "/home/chen/AGC"
```
`w6.launch.py` 从不设置这两个参数 → 克隆 run 的评测产物写进**原仓库**，克隆侧 `terminal_explanation.txt` 报"未取得本轮 summary.json"。

**我另查出执行者漏报的第二处同源**：`src/agc_task/config/w6_base.yaml:129` 与 `m0.yaml:39` **也**写死
`experiments_root: "/home/chen/AGC/experiments"`（另有 6 个 w5/w6_* 场景 yaml 同款）。
即：**C++ 默认值 + YAML 字面量两条来源都在运行期决定写盘位置** → 只修 launch 不够。

## 3. 裁定：**α+（整类修，不只修一处）**

1. `w6.launch.py` 显式给 `run_logger` 传 `experiments_root=<agc_root>/experiments`、`git_root=<agc_root>`
   （launch 参数在 yaml 之后生效 → 覆盖）。
2. **同时**清掉 YAML 里的绝对字面量（`w6_base.yaml` / `m0.yaml` / 6 个场景 yaml 的
   `experiments_root` / `git_root`）：要么删键、要么改成可派生形式 —— 由执行者选最小手段，**在报告里写明选法与理由**，
   并保证 `test_run_logger_mission_fco.py` 等既有测试仍绿。
3. **整类清扫**（执行者 round-7 的教训制度化）：把 `src/**` 里**所有 C++ `declare_parameter` 的绝对路径默认值**
   与 **YAML 绝对路径字面量**列成分类表（保留/派生/删除），并把 `test_root_self_location.py` 的守护范围
   从"Python/launch"扩到 **C++ 默认值 + YAML**（白名单逐条写理由）。
4. **补充（裁定后代码级复核，追加授权 β 的必要部分）**：**C++ 默认值也必须显式保留**。理由：YAML 删键后，`w6` 之外的独立启动（`m0_skeleton` / 研究 runner / 无 agc_root 的入口）仍会直接落到 C++ 默认值；若删 YAML 又删 C++ 默认值，等于把"写回主仓"的脚枪留在这些入口。故 β 的"改默认值"不在本单范围，**`run_logger.cpp` 的两行默认值作为契约式缺省保留**，由 launch 在交付路径统一覆盖；守护测试须同时断言这两行仍在、且交付 launch 已覆盖它们。
5. **δ 不可接受**（等于承认克隆跑不通）。

## 4. 原仓库污染目录：授权迁移（不是删除）

`experiments/w6-task-eval/20261031-s04_static_static_obs_track-0-121023-3528/` 是**克隆 run 写进原仓库的**：
- 它是**真实产物**（不是伪造），但落点错误，留着会让原仓库历史里出现"本仓从未跑过的一次评测"；
- **授权**：先整体复制到 `experiments/p2-1/round-8/relocated-eval-20261031-121023-3528/`（本地证据区、不入 git），
  核对内容一致（文件数 + md5）后，**再**删除原位置；
- 前后清单与 md5 写进报告；**不得**触碰同日 11:44 / 11:46 那两次（那两次是主仓自己的合法 run）。

## 5. 我接受的两点

1. **round-7 的误判被自己更正**：把 `config/*.yaml` 的 `experiments_root` 归为"不在主路径"，
   而主路径实际走 C++ 默认值。**教训制度化**（见 §3.3）比修一处更重要 —— 这是第二次自我更正，记正面。
2. **偏离如实披露**：`toolchain/` 用软链借用主仓 → 证明的是"**路径自定位成立**"，
   **不是**"新机器 10 分钟可跑"（陌生人仍需按 `toolchain/README` 自建 PX4，成本单列）。这个边界划得对。

## 6. round-9 / round-10

| 轮次 | 目标 | 预算 |
|---|---|---|
| **round-9** | α+ 落地（launch + yaml + 整类清扫 + 回归扩容）+ 污染目录迁移 | **T2 0** |
| **round-10** | 克隆**复验**：重新克隆 → 构建 → `doctor` → 跑到终态 → **summary 落克隆自己**、原仓库零新增 | **T2 ≤2** |

**不再追加 T2**：累计 11/15，余 4 够用（round-10 ≤2）。N=4 用 2 余 2。
**停止条件**：round-10 后克隆仍不能"summary 落克隆 + 读数正常" → 判不可达成，停止交台账。