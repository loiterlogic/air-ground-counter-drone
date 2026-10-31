# P2-1 · round-9 request（Worker 自写，新批次第 3 轮）

<a id="p2-1-r9-request"></a>

- 任务 ID：`20261031-011-p2-1-deliverables` · round-9 · 2026-10-31
- 来源：**Worker 自写**，继承 [round-8 审查](../round-8/review.md#p2-1-r8-review) 第 3 节（裁定 **α+ 整类修**）
- 承接：[round-8 report](../round-8/report.md#p2-1-r8-report)（`run_logger` 同类缺陷）
- **预算：T2 = 0**（纯离线）

## 本轮目标

**α+ 整类修**：把"运行期决定写盘位置"的**所有来源**（launch 参数 / YAML 字面量 / C++ 默认值）
一次性清扫干净，并把守护范围从"Python/launch"扩到 **C++ `declare_parameter` 默认值 + YAML**。

## 步骤

### 1. `w6.launch.py` 显式传参（**不遗漏 `git_root`**）

给 `run_logger` 显式传：
- `experiments_root=<agc_root>/experiments`
- `git_root=<agc_root>`

**理由**：`git_root` 若漏，Git 身份仍读主仓（`run_logger` 记 `git_commit` 时会错）。
launch 参数在 yaml 之后生效 → **覆盖** YAML 与 C++ 默认值。

**轻量栈 / 相关交付 launch 也要核对同一问题**（`m0_skeleton.launch.py` 等）。

### 2. YAML 绝对字面量清理

清掉这些文件的 `experiments_root` / `git_root`：
`w6_base.yaml` / `m0.yaml` / `w5_scenario.yaml` / `w6_r6_random.yaml` /
`w6_safety_trigger.yaml` / `w6_c4_timeout.yaml` / `w6_c9_resetfail.yaml` / `w6_c9_infeasible.yaml`

- 推荐**删键**，让交付 launch 统一派生；**不要**留不可解析占位；
- 说明独立/研究入口的兼容策略（它们仍会落到 C++ 默认值，见步骤 3）。

### 3. **保留** `run_logger.cpp` 的默认声明（本单不改 C++）

`experiments_root` / `git_root` 的 C++ 默认值**作为契约式缺省保留**：
YAML 删键后，`w6` 之外的独立启动（`m0_skeleton` / 研究 runner / 无 `agc_root` 的入口）
仍会落到它们——若删 YAML 又删 C++ 默认值，等于把"写回主仓"的脚枪留在这些入口。

**守护测试必须同时断言**：① 这两行默认值**仍在**；② 交付 launch **已覆盖**它们。

### 4. 整类清扫 + 扩 `test_root_self_location.py`

- 把 `src/**` 里**所有 C++ `declare_parameter` 的绝对路径默认值**与
  **YAML 绝对路径字面量**列成**分类表**（保留 / 派生 / 删除 + 理由）；
- 把守护范围从"Python/launch"扩到 **C++ 默认值 + YAML**，白名单**逐条写理由**；
- **反向对照**：重新注入硬编码应失败。

### 5. 污染目录迁移（**不是删除**）

仅限 `experiments/w6-task-eval/20261031-s04_static_static_obs_track-0-121023-3528/`：
1. 整体复制到 `experiments/p2-1/round-8/relocated-eval-20261031-121023-3528/`（本地证据区、**不入 git**）；
2. 逐文件**相对路径 + size + md5** 核对一致；
3. **回显并核对两个绝对路径**，确认无误后**再删**原目录；
4. **不得**碰同日 **11:44 / 11:46** 那两次（主仓自己的合法 run）。

### 6. 回归

`scripts/tests`、冒烟、文档断链；**离线可验证 launch 合并参数确为克隆根**。

## 预算

- **T2：0 次**（纯离线）。
- **T1**：沿用批次余量。
- 离线只读检查：次数只记账。

## 禁止（红线）

- **禁止**改 C++ 默认声明（`run_logger.cpp` 两行保留）；
- **禁止**改契约默认值（`air_bringup.launch.py` 的 `agc_root`）；
- **禁止**碰 `/dev/shm`、处置他人进程、写 `~/.gz`；
- **禁止**碰同日 11:44 / 11:46 的合法 run；
- **禁止**用旧图/示意图、**禁止**包装未达成项；
- **禁止**碰完整视频（用户自录）。

## 停止条件

- **若需要改 C++ 默认声明/契约** → **停止报告**；
- **若预算不足** → 停止报告；
- 若删 YAML 键导致既有测试变红 → 先停报告（可能是别的入口依赖该键）。

## 不做

- 克隆复验（round-10，T2 ≤2）；
- 用户视频接入（等文件）；
- push / 归档 / 开下一任务。
