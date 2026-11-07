<a id="top"></a>
# 实验产物与证据纪律

## Status

accepted（2026-11-02 由 0007 / 0044 / 0045 / 0063 / 0064 合并；结论未变，其中一次真实证据丢失事故的
登记与重做义务一并保留；2026-11-06 增补 (h) 产物保留策略与回收，用户裁定日期 2026-11-06、
`demo/` 定位口径 2026-11-07）

## 背景

实验产物是这类项目的**唯一可复核凭证**：论文数字、验收结论、回归判定都指向 `experiments/` 下的文件。
项目早期吃过两次亏，都是同一个结构问题：**产物没有身份、不可复核**。

- 产物就近散落、固定路径重写：同日同场景同 seed 连跑两次会**覆盖**前次产物（重复失败可覆盖成功，反之亦然），
  config 只存 logger 自身几项参数与 `git HEAD`，**不存**展开参数 / dirty diff / 未跟踪源码 → 无法回答
  「用的是哪份代码 / 参数 / 世界」。
- 证据只写在 `config/` 入库，`bag/` / `log/` / `metrics/` 一律忽略且**无归档 manifest** → clone 不能复核已完成状态，
  重建机器或清临时目录可**永久失去**科研证据。这不是假设：一次清理残留进程时误执行
  `rm -rf experiments/w6-task-eval/20261014-*`，把全部 `20261014-*` 产物（含当次要复核的目标）**永久删除**，
  `git ls-files experiments` 在该目录下为 0 条、无副本无备份。

## 决策

### (a) 唯一落点与目录结构

所有实验产物只落一个根，按 campaign → run 两层组织：

```
experiments/<campaign>/<run_id>/
  ├── config/ 本次参数快照（必需，可复现）
  ├── bag/ ros2 bag
  ├── log/ 运行日志 / run logger 输出
  ├── metrics/ 结构化指标（含 shield_infeasible_rate、reset_failure_rate）
  └── figures/ 出图
```

**禁止**在其它任何位置写实验产物。每次 run 必须落 config 快照 + git commit hash。

> **入库口径已由 [ADR-0025](0025-publishing-boundary-and-retirement.md#top) 取代**：`/experiments/`
> **整目录**不入库，只有 `experiments/README.md` 例外（本 ADR 早期"放行 `experiments/**/config/`"
> 的说法作废——`.gitignore` 实测是整目录忽略，`.coordination/` 的实验产物同理）。

### (b) run_id 唯一不可覆盖

- `run_id` 生成改为 `<YYYYMMDD>-<scenario>-<seed>-<HHMMSS>-<rand4>`（时刻 + 随机后缀），并**保留**
  `-<scenario>-<seed>` 子串以兼容既有 `*-<scenario>-<seed>-...` glob 定位。
- run 目录以 `fs::create_directory` **独占创建**（已存在即失败）：先建 campaign 父目录，再对 run 目录独占创建；
  失败则置 `dir_ok_ = false` 并报错。`main` 在 `dirOk == false` 时**退出码 2**，**不重写**已有 `summary.json`。
- `run_id_override` 参数**只替换 run 目录名**（供确定性复现「已有目录 → 拒写」的验证 / 审计），
  **独占创建仍拒绝已有目录**，因此**不削弱**唯一性；默认空 = 走 `makeRunId`。
- campaign 的 `run_id` 同样唯一：`<YYYYMMDD>-<campaign>-<HHMMSS>-<rand4>`，同日同 campaign 连跑落到不同目录。
- 临时文件（`write_temp_params` / `write_manifest` 及派生的障碍 / 地图 / 空中参数临时文件）文件名追加**唯一 token**
  （时刻 + 进程 + 随机），避免并发 / 重复 run 互相覆盖。

### (c) 运行身份：episode_id + 展开参数 + 代码身份 + 工具链与世界哈希

- **`episode_id`**：`run_logger` 订 `/agc/task/episode`（`std_msgs/Int32`，`transient_local`，由 `task_manager` 在
  start 成功后发布，**非**命令者、诊断类）；收到后打印日志、把 `config/episode_id.txt` 覆写为实际值、summary 增
  `episode_id` 键。初值 `-1`；未收到时 summary 记 `null`（**不**以 0 冒充）。
- **展开参数**：`params_applied.yaml`（launch **单一注入**的合并后参数文件，含全部节点 `ros__parameters`）拷入
  `config/`；另拷 `scene_manifest.json`。
- **代码身份**：`git_head.txt` / `git_status_porcelain.txt` / `git_diff.patch` / `git_untracked.txt`；
  `workspace_fingerprint.json` 含 `fingerprint_sha256 = sha256(git HEAD + status --porcelain + diff)`、
  `diff_sha256`、`status_entries`、`dirty`。**dirty 工作区非禁跑**，但 run 可据此重建。
- **工具链与世界模型哈希**：`toolchain_world.json` 含 `ROS_DISTRO`、`gz sim --versions`、code root、`git_head`、
  可选 PX4 `px4_root` 及其 `px4_head`、世界模型文件路径与 `world_sha256`（空路径 / 文件缺失记 `null`）。

### (d) runner 以唯一 run_id / 创建时间校验同一 run 关联

`episode_runner` 收集 summary 改为 glob `*-<scenario>-<seed>*/metrics/summary.json`，并以
`mtime >= 本 episode 墙钟起点 − 1.0` 过滤，取最新候选；再以 `run_id` 含 `-<scenario>-<seed>-` 记
`same_run_verified`（**同一 run 关联**）。就绪改为**有界轮询** `wait_ready`（以 `/agc/task/start` 服务就绪为门槛）
替代固定 `time.sleep(18)`，随后仅有界稳定窗口收集 `/clock` 起点。

### (e) campaign 归属：报告归 `metrics/` 并引用每 run

campaign 汇总报告 `report.{json,md}` 落 campaign run 的 **`metrics/`**（不写 run 根，避免与 `config/` / `metrics/`
分工混淆）；报告含 `run_references`，逐 episode 引用其不可变产物（`run_id` + `config/scene_manifest.json` /
`config/params_applied.yaml`）。规范文档与 `experiments/README.md` 同步到唯一 run 身份（**只索引不复述约束**）。

### (f) 证据不可变归档 + 入库 manifest

- **入库 manifest** `experiments/<campaign>/<run_id>/config/evidence_manifest.json`：
  - 逐产物 `path` / `type`（`config` / `metrics` / `log` / `bag` / `figures` / `other`）/ `size` / `sha256`；
  - 运行身份 `campaign` / `run_id` / `episode_id` / `git_commit` / `backend`（缺失记 `null`，**不**以 0 冒充）；
  - 生成器版本 `generator` + `generator_version` + `manifest_version`；
  - 访问位置与保留期 `archive.path` + `archive.checksum_file` + `archive.retrieval_record` + `retention`
    （长期保留，≥对照冻结）。
  - `config/**` 已放行入库，故 manifest 天然入库，**无需**改放行规则；manifest **不含自身哈希**
    （`self_excluded` 显式标注），避免自引用。
- **本地不可变归档** `experiments/_archive/<campaign>/<run_id>.tar`（**只读**）：run 目录打包（**含**
  `config/evidence_manifest.json`），成员路径以 `<run_id>/` 为前缀便于取回还原，`uid/gid/uname/gname` 归一以利确定性；
  归档 `sha256` 记入同名 `.tar.sha256`（`sha256sum` 格式）；归档与侧车生成后置 `0444` 并标 `retention`；
  **大归档不入 git**（`experiments/_archive/` 加忽略规则）。
- **跨路径取回验证**（证明「可取回」而不只写路径）：解包到 `tempfile.mkdtemp` 另一路径并**逐文件哈希比对**
  （含 manifest 自身），结果落 `<run_id>.tar.retrieval.json`（`verified` / `method` / `files_checked` /
  `mismatches` / `archive_sha256` / `verified_at`）；`mismatches` 非空即判失败。
- **保护现有证据**：对现存 run 生成 manifest + 归档是**新增**产物，**不**改写 run 内既有 `params` / `summary` /
  `log` / `metrics`；已存在 manifest + 归档的 run 默认 **skip**（`--force` 可显式重建）。
- **工具**：`scripts/evidence_archive.py`（`--campaign` / `--run-id` 过滤、`--force` 重建、`--no-verify` 跳过取回验证、
  `--list` 枚举）。

### (g) 据实登记，不伪造、不冒充复核

- 证据矛盾与丢失事实**据实登记**，**不**伪造 / 重建已丢失原件，**不**把数字改写成期望值，**不**声称未复核的数字
  「已复核」，**不**以旧路径名新跑一次冒充原件。
- 重做必须在**唯一不可覆盖 run** 下进行，新 run 须**补齐**原始日志（服务应答与拒绝原因）+ 运行配置
  （`params_applied.yaml` + 代码身份 + 工具链与世界哈希）+ **产物身份**（非零指标 + 可独立复核的 summary）。
- **不**凭推断改写完成状态；重做结果与既有声明一致或不一致均**据实记录**，完成状态由证据决定而非由声明决定。

### (h) 产物保留策略与回收（`experiments/` / `log/`）

产物长期只增不减（2026-11-06 实测：`experiments/` 4.2 G / 2 100+ run 目录、`log/` 7.1 G / 430+ 目录），
必须有一条**可执行**的回收规则；`scripts/evidence_archive.py` 的 `RETENTION` 只是**文本**、零调用方，
**不是**策略。策略由 `scripts/reclaim_evidence.py` 执行：**默认 dry-run**，`--apply` 才删。

**可回收（用户 2026-11-06 明确裁定授权）**：

| 规则 | 范围 | 判据 |
|---|---|---|
| `demo_doctor` | `experiments/demo/*-doctor` | 纯环境预检，无任务判定 |
| `demo_failed` | `experiments/demo/<run>` | `result.json` 的 `verdict` ≠ `expected_terminal`、或 `terminal_reached=false`、或 `exit_code≠0` |
| `demo_superseded` | `experiments/demo/<run>` | 同类演示里**非最新一份**（保留最近 1 份） |
| `rl_no_report` | `experiments/w7-rl-b/<run>` | 缺 `metrics/report.json`（不构成完整证据链） |
| `colcon_logs` | `log/build_*` `log/test*` | colcon 构建 / 测试日志（**非** run 证据） |

**不可删清单**（任何规则不得越过；由脚本硬编码并逐项复核）：

1. **被文档 / 代码引用**的 run（`docs/`、`README.md`、`AGENTS.md`、`GLOSSARY.md`、`tests/`、`scripts/` 里出现过
   `<campaign>/<run>`，**含省略 `experiments/` 前缀的写法**）——删了即断证据链；
2. `experiments/_archive/`（不可变归档）与 `w6-task-eval/`（验收证据）；
3. **带完整证据链**的 run（`metrics/summary.json` + `config/scene_manifest.json` 均在）；
4. 未被授权的 campaign——脚本只动 `demo/`、`w7-rl-b/`、`log/`。

**`demo/` 证据的定位**：`experiments/demo/` 是**演示**产物（GUI 截图 / timeline / panel），
判据来源在 `experiments/w6-task-eval/` 的 run 目录（`summary.json`）。故 `demo/` 可回收、**不入不可删清单**；
需要留证时用 `scripts/demo/capture_run.py` 重跑。这一点是用户 2026-11-07 的明确口径。

**一次真实误删（必须据实登记，不得掩盖）**：2026-11-06 首次 `--apply` 时，脚本的 `_demo_state()`
按 `state`/`result`/`status` 三个键读 `result.json`，而 `scripts/demo/start.py` 实际写的是
`verdict` / `terminal_reached` / `exit_code` → 每场演示都读到 `None` → 全部落入 `demo_failed`，
把 151 场**成功**演示（含最新一场）连同 37 个 doctor 目录一并删除（`experiments/demo/` 下 188 个目录）。
**未受影响**：`w6-task-eval/` 1 437 个判定 run 全部存活、文档零断链、无任何文档引用具体 demo 时间戳。
**修法**：改为按真实 schema 判，且**读不到 `result.json` 时归入保护而非回收**（读不到 ≠ 失败）。
修复后 dry-run 为 `可回收 0 项`。这是 (g) 的反面案例：**规则写错就会删掉好证据**，
故回收脚本必须 dry-run 默认 + 先算清单再动手。

## 不做什么（边界）

- **不**在 `experiments/` 之外写实验产物；**不**重写 / 覆盖已有 run 目录（独占创建失败即退出 2）。
- **不**让回收脚本默认删除（必须 dry-run 默认、`--apply` 才删）；**不**让任何规则越过不可删清单。
- **不**把大 `bag/` / `log/` 直接入 git（仓体膨胀、二进制不可 diff）。
- **不**只写归档路径而不验证可取回；**不**让 manifest 含自身哈希或归档哈希（自引用循环，哈希不可闭合）。
- **不**伪造 / 重建已丢失的历史原件，**不**以旧路径名冒充复核；**不**凭推断改写 Runbook 完成状态。
- **不**改契约冻结 9 消息 ABI、**不**改指标语义 / 三层验收、**不**新增第二 ROS 命令者。

## Considered Options

- **产物就近散落（旧项目现状）** —— 被否：旧项目实验目录错乱正是明确要避免的反面教材。
- **继续用固定路径 `<YYYYMMDD>-<scenario>-<seed>`** —— 被否：会覆盖前次产物；改为唯一 id + 独占创建，同时保留
  `-<scenario>-<seed>` 子串兼容 glob。
- **不存 diff（只存 `git HEAD`）** —— 被否：dirty 工作区下无法绑定运行代码（HEAD 不标识未提交实现）。
- **无 `run_id_override`，用真实唯一 id 撞目录** —— 被否：无法确定性复现「已有目录 → 拒写」，验证不可复制。
- **runner 继续固定 `sleep` 当就绪 + 精确路径猜 summary** —— 被否：固定等待既非就绪协议，又易误取旧 summary（缺数据假绿）。
- **把大 `bag/` / `log/` 直接入 git** —— 被否：仓体膨胀、二进制不可 diff。
- **只写归档路径、不验证可取回** —— 被否：「写路径」不等于「能取回」，重建机器时可能发现归档损坏。
- **重建旧 summary 使数字「与声明一致」/ 在旧路径名下新跑一次冒充原件** —— 被否：属伪造历史产物，破坏唯一身份。
- **直接改 tasks / Runbook 完成状态以求自洽** —— 被否：凭推断改写完成状态，掩盖证据丢失。

## Consequences

- **正面**：同日同场景同 seed **不再覆盖**；已有目录**拒写并退出 2**；`episode_id` 与展开参数 / 代码身份 /
  工具链与世界哈希齐备，dirty 亦可重建；runner 以唯一 run_id 与创建时间**校验同一 run 关联**并去掉固定 `sleep`；
  每 run 有**入库 manifest**（逐产物哈希 / 身份 / 访问位置 / 保留期）与**只读本地归档**，「可取回」由跨路径逐文件
  哈希比对**证明**；campaign 与 episode 分层清晰、报告可追溯每 run；临时文件不互相覆盖。
- **代价 / 限制**：`git_diff.patch` / `git_status_porcelain.txt` 在工作区大量未提交时**可能较大**（实测数百 KB，
  属如实保全）；`run_id` 现含时刻 + 随机后缀，依赖 `-<scenario>-<seed>` 子串的既有 glob 仍可匹配，但**精确路径**
  定位会失配；`experiments/_archive/` 为**本地**归档（不随 clone 分发），跨机器复核需另移植；归档是**一次性快照**，
  run 后续追加产物即**非最新**（需 `--force` 重建并**重记哈希**，旧哈希随之失效）；依赖固定临时文件名的既有脚本与
  读 campaign 报告路径的 check 脚本须同步更新。
- **产物回收（(h)）**：`experiments/` 与 `log/` 有了**可执行**的保留策略（dry-run 默认、`--apply` 才删），
  不可删清单含「被文档引用 / 归档与验收 campaign / 完整证据链 / 未授权 campaign」四条；首次 `--apply`
  因 `result.json` 键名读错误删了 `experiments/demo/` 下 188 个目录（151 场成功演示 + 37 个 doctor），
  `w6-task-eval/` 判定证据与文档链接**未受影响**；已按真实 schema 修复，并确立「读不到即保护、不回收」。
- **未决 / 后续**：`fingerprint_sha256` 目前只覆盖 `HEAD + status + diff`，未纳入未跟踪文件**内容**（仅列名）；
  多后端（含 PX4）工具链身份待 `px4_root` 实跑回填；外部（异地）归档与分发属正式冻结项；
  「小审定摘要入 git」按项目裁定另行决定；证据丢失事故的重做一致性结论待据实回填。

## 参考

- 评审：`S-07`、`S-08`、`R-029`、`R-030`（评审快照已于 2026-11-06 退役，见 [ADR-0033](0033-review-snapshot-retirement.md#top)）
- 契约：[#hard-constraints](0020-package-boundaries-and-runtime-topology.md#hard-constraints)、[#params](0020-package-boundaries-and-runtime-topology.md#params)
- 相关决策：[ADR-0016](0016-episode-window-and-sample-validity.md#top)（episode 窗口与有效样本掩码）、
  [ADR-0018](0018-acceptance-and-coverage-matrix.md#top)（验收判定与覆盖矩阵）、
  [ADR-0019](0019-lifecycle-and-startup-robustness.md#top)（生命周期可重建）、
  [ADR-0025](0025-publishing-boundary-and-retirement.md#top)（发布边界与退役清理）
- 实现：`run_logger.cpp` / `episode_runner.py` / `composition.py` / `scripts/evidence_archive.py` / `.gitignore` /
  `experiments/README.md`
