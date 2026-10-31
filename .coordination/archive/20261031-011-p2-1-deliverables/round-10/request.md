# P2-1 · round-10 request（Worker 自写，**本批次最后一轮**）

<a id="p2-1-r10-request"></a>

- 任务 ID：`20261031-011-p2-1-deliverables` · round-10 · 2026-10-31
- 来源：**Worker 自写**，继承 [round-9 审查](../round-9/review.md#p2-1-r9-review) 与 Leader 本轮派工
- 承接：[round-9 report](../round-9/report.md#p2-1-r9-report)（α+ 整类修）
- **批次状态**：N=4 用满；T2 累计 11/15（本轮 ≤2）

## 本轮目标

**完整证明修复**——不是"再跑通一次"，而是逐项证明三类来源（launch / YAML / C++ 默认值）
在**克隆**环境下都指向克隆自己：

1. 从含 `61374f7` 的 HEAD 克隆到新的 `/tmp/agc-r10-*`；
2. 软链借用主仓 `toolchain`（**继续明确披露**：不代表新机器 toolchain 成本）；
3. 构建前 `doctor` 必须 **FAIL** 且指**克隆路径**；构建后 **PASS**；
4. 默认 GUI 演示跑到终态（**运行期间不要拖动/缩放 Gazebo 窗口**——`Screenshot` 取 GUI 实时相机，
   但本轮不取帧，拖动只影响人工观察，不影响产物落点）；
5. **逐项验证**（每项给原始证据路径与关键字段）：
   - 克隆自己的 `experiments/w6-task-eval/<new-run>/metrics/summary.json` 存在且有效；
   - 该 run 的 `config/params.yaml` 中 `experiments_root` 指向**克隆**；
   - `config/workspace_fingerprint.json` 的 `code_root` 指向**克隆**；
     `config/git_head.txt` 与**克隆 HEAD** 一致；
   - 克隆 demo 的 `terminal_explanation.txt` **正常读取** summary/阈值/终态，
     **不再报"未取得本轮 summary"**；
   - 主仓 `experiments/demo/` 与 `experiments/w6-task-eval/` **前后清单完全一致、零新增**；
6. 报告含：命令、退出码、耗时、克隆与主仓路径、run id、证据文件与关键字段、残留进程核查。

## 预算

- **T2：≤2 次**（批次累计上限 15，已用 11）。
- **T1**：沿用批次余量。
- 离线只读检查：次数只记账。

## 禁止（红线）

- **禁止**碰 `/dev/shm`、处置他人进程、写 `~/.gz`；
- **禁止**改 C++ 默认声明或契约默认值；
- **禁止**用旧图/示意图、**禁止**包装未达成项；
- **禁止**把"借用 toolchain"写成可复现；
- **禁止**碰完整视频（用户自录）；
- 删除克隆目录前**必须先回显解析后的绝对路径确认**。

## 停止条件

- 若复验**失败** / **预算耗尽** / **需改代码或契约** → **立即停止并报告**，
  **不自行开 round-11**（本批次最后一轮）；
- 若复验**通过** → **里程碑达成**，置 `待审查` 并唤醒 Leader。

## 不做

- 用户视频接入（等文件）；
- push / 归档 / 开下一任务。
