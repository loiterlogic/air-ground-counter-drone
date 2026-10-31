# P2-1 · round-8 request（Worker 自写，新批次第 2 轮）

<a id="p2-1-r8-request"></a>

- 任务 ID：`20261031-011-p2-1-deliverables` · round-8 · 2026-10-31
- 来源：**Worker 自写**，继承 [round-7 审查](../round-7/review.md#p2-1-r7-review) 第 3 节（克隆实测 + 已知操作前提）
- 承接：[round-7 report](../round-7/report.md#p2-1-r7-report)（A + D 落地）

## 本轮目标

**克隆到任意路径、从零构建后按 README 跑通**——把"陌生人照 README 能跑起来"这条判据从"实质不成立"变成**实测成立**。

## 步骤

1. **克隆到新目录**（`/tmp/agc-r8-clone`），**从含 round-7 修复的 HEAD 克隆**（round-7 教训：
   `git clone` 取 HEAD，改动未提交则测的是旧版）。
2. **工具链借用（**必须如实披露为偏离**）**：`ln -s /home/chen/AGC/toolchain <clone>/toolchain`。
   - 理由：克隆目录**没有 `toolchain/`**（`.gitignore` 排除），而演示依赖 PX4 SITL；
   - **真实陌生人**须按 `toolchain/README` 自建，该成本 README 已写明（"首次约 5–6 分钟"是**构建**成本，
     toolchain 自建另计）——**不得**把借用写成"可复现"。
3. **负向取证（构建前）**：克隆内 `./run_demo.sh doctor` 必须**非零退出**，
   且报的是**克隆自己的** `install/` 路径。
4. 克隆内 `colcon build`（记耗时 / 包数 / 退出码）。
5. `doctor` → PASS；**确认它查的是克隆的 install**（不是 `/home/chen/AGC`）。
6. 按 README **默认形态（GUI）** 跑到终态（记耗时），取证：
   - 产物在 **`<clone>/experiments/demo/<ts>/`**；
   - **原仓库 `experiments/demo/` 前后清单一致**（未新增）；
   - `launch.log` 里 **`agc_root:=<clone>`**（不是 `/home/chen/AGC`）。
7. 证据留存（日志 / 清单 / md5 / launch.log 片段）；**删除克隆目录前必须先回显解析后的绝对路径确认**。
8. `docs/plan/p2-1-项目交付物.md` 判据 7 证据补一条：
   「克隆到任意路径、从零构建后按 README 跑通（YYYY-MM-DD）」。

## 预算

- **T2：≤2 次**（批次累计上限 **15**，已用 10）。
- **T1**：沿用批次余量。
- 离线只读检查：次数只记账。

## 禁止（红线）

- **禁止**碰 `/dev/shm`、**禁止**处置他人进程、**禁止**写 `~/.gz`；
- **禁止**改契约默认值、**禁止**改源码（构建失败要**先停报告**，不顺手修）；
- **禁止**用旧图/示意图、**禁止**包装未达成项；
- **禁止**碰完整视频（用户自录）；
- **禁止**把"借用 toolchain"写成可复现（必须标为偏离）。

## 停止条件

- 若克隆内 `colcon build` **失败或缺依赖** → **先停并报告**，不改源码；
- **round-7/8 两轮内**克隆仍不能"`doctor` 真实 + 跑到终态" → 判**不可达成**，停止交台账；
- 本轮 **T2 用满**（2 次）→ 唤醒 Leader；
- 若克隆实测**通过** → 本轮即**里程碑达成**，唤醒 Leader 带证据收口。

## 不做

- 用户视频接入（round-9，等文件）；
- push / 归档 / 开下一任务。
