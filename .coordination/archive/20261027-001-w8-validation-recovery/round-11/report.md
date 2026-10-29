<a id="round11-report"></a>
# 第11轮执行回报

任务 ID：20261027-001-w8-validation-recovery；轮次11。

执行者：Worker（DSH 子会话 `55d8793e-4916-4045-ac19-5800e167ebfa`，父会话 `session-7bfaaed2-f329-4569-8dae-f795ccdba988`）。复用同一子会话，未新建 Worker。

状态：**待审查**。

结论：第10轮审查第 1–5 条（含其独立反例）已在**新根**定点修复，并用**真实函数**与**真实驱动**双重离线回归验证：`validate_side` 反例 16/16、信号身份反例 6/6、真实驱动端到端 20/20、stub rclpy 探针 11/11。T1 实际 **0/0**，0 ROS / 0 participant / 无构建仿真抓包。

## 0. 领取与结束配对时钟（先于任何动作采样）

### 领取（本轮第一个动作，早于任何文件读取）

来源：Worker，2026-10-28T13:38:23+08:00。

| 字段 | 值 |
|---|---|
| `claim_mono_before_ns` | `19187369103874` |
| `claim_wall_ns` | `1793165911691704623` |
| `claim_mono_after_ns` | `19187369105365` |
| `claim_pair_gap_ns` | `1491` |

### 结束

| 字段 | 值 |
|---|---|
| `end_mono_before_ns` | `19454872249717` |
| `end_wall_ns` | `1793166184668103952` |
| `end_mono_after_ns` | `19454872250919` |
| `end_pair_gap_ns` | `1202` |

### 预算

| 口径 | 值 |
|---|---|
| **整轮 mono** | **267.503 s ≈ 4.46 min**（≪ 45 min） |
| wall | 272.976 s |
| 该窗口 wall/mono 偏移漂移 | +5.473 s（如实报告，**不假设原因**、未改系统时钟） |

**口径声明**：本报告的时点全部是**直接采样的配对数据**，**未用文件 mtime 反推**。第10轮 6.52 min 只能视为估计，本轮不引用其为实测。预算判定以 **monotonic** 为准。

## 1. 接单与基线

| 项 | 值 | 结果 |
|---|---|---|
| CURRENT 领取前 | 任务 `20261027-001-w8-validation-recovery`、轮次 `11`、状态 `待返工` | 协议允许接单 |
| HEAD / 分支 | `d5072aaff33276bcd1c5e7d38b5caa75fe45a290` / `main` | 与派工一致 |
| 基线 SHA | `a4c5f2cf24ff7fc2bfcf5973ebdb8f271c2cdaff2cac8f2f95b44f7bf79171b6` | 与 receipt 一致 |
| 逐项复算 | **1343/1343 相符**，missing 0、changed 0（领取时） | 通过 |
| `git status --porcelain` | 与 baseline `status` 逐行相同 | 通过 |
| 交回前复核 | 1343/1343 相符，missing 0、changed 0；status 仍逐行相同 | 通过 |

未 reset/clean/commit/push/切分支；既有 dirty/untracked 全部保留。

## 2. 实际改动（全部新增，只落本轮新根）

`experiments/w8-validation/20261028-endpoint-driver-offline-r2/`

| 文件 | 大小 | SHA256 |
|---|---:|---|
| `scripts/run_attempt_driver.py` | 45141 | `7d343c8f828165e9b6cf67e18ebe651ea81e8b34f20b1877cee9557c4bb42146` |
| `scripts/validate_gate.py` | 8689 | `844e76a6af148234e3e9e3a6a74317de8d02272a7208d29627b09da6e973e4e8` |
| `scripts/probe_endpoint_ready.py` | 21793 | `72c18cebc8031b015dd04a2778fc7d90c154b2229ac5c85bc54280a541738cae` |
| `scripts/fake_probe.py` | 10777 | `ccfe8def7fc498ad462c94fcdbc759c0138f113286748c14012fff2eae7fdf6e` |
| `scripts/test_driver_offline.py` | 17477 | `3b6ff0f18c548d76e978242b47721327a0b603c9d003c0b27f55a158c2f07a60` |
| `scripts/test_validate_side_offline.py` | 8353 | `181a071732f89b0e1595845880119572d759b54771de77c24fe725523f8ad550` |
| `scripts/test_signal_identity_offline.py` | 7501 | `6f11934c6d8727e560979daf86759c8189214845f25ff0f749d5e977076915e4` |
| `scripts/test_probe_offline.py` | 9690 | `f302456b48ec171a0f0831a8f2db5aa041950e765ba5dbc6d7f4aa90d4cd0cf7` |
| `config/sources.json` | — | 见 manifest |

- `probe_endpoint_ready.py` / `validate_gate.py` / `test_probe_offline.py`：**原样吸收**第10轮，SHA 完全相同（未改）。
- `run_attempt_driver.py` / `fake_probe.py`：在第10轮基础上定点修改（差异见 §3、§4）。
- `fake_probe.py` 新增 3 场景：`tree_normal`（同组子进程）、`late_marker`（迟到标记）、`no_end`（缺 `probe_end`）。

**协调文件**：`CURRENT.md`（执行中 → 待审查）、本 `report.md`。未改 spec/tasks/checklist/Runbook/契约/全局 scripts/src/toolchain/第10轮及更早封存源与历史归档。

**过程性写入/删除（如实计入）**：
- `/tmp/agc-w8-validation-r11-{tests,unit,sig,probe,suite*,pre-final-sha.txt}` 等过程输出；
- `scripts/__pycache__` 多次生成后删除，最终源根无 `__pycache__`/`*.pyc`（已核验）；
- `cases/` 曾一度被 `cp -a` 复制成含外层 wrapper 与 `scratch/` 的形态，已**展平**为 `cases/<case>/…` 并删除 `scratch` 副本（未删除任何已归档原件）；
- 首轮 `evidence/final` 与 `cases/` 在最终全套回归后被**替换**为新一次产物；失败迭代证据单独保留在 `evidence/iterations/`（不覆盖）。

## 3. 针对审查第 1–5 条的修复

### R1 完成事件流严格性（审查第 1 条及其反例）

- `parse_events(path, strict=True)`：**完成侧**破损末行计入 `bad_lines` → 拒绝。仅"活跃门控抓拍"用 `strict=False`，且在证据里标 `snapshot_semantics=active_snapshot_partial_tail_allowed`。
- `check_required()` 对必填字段做**存在性 + 类型**双校验，缺失不等于空：
  - `result.json`：`pid:int`、`pgid:int`、`attempt_id:str`、`mode:str`、`exit_code:int`、`invalid_reasons:list`；
  - `probe_end`：`attempt:str`、`mode:str`、`pid:int`、`exit_code:int`、`invalid_reasons:list`。
- 身份冲突（`pid`/`attempt_id`/`mode` 不符）分别记独立 problem。
- **审查反例已复现并闭合**：`test_validate_side_offline.py` 直接 import 真实 `validate_side`，构造"合法 `probe_end` 后追加坏尾 + result 缺 `invalid_reasons`"——现返回非空 problems（见 §4.2 `bad_tail_rejected` / `result_missing_invalid_reasons`）。

### R2 信号与进程组归属（审查第 2 条及其 mock 反例）

- `send_signal(pid, starttime, sig)`：`read_stat(pid) is None` → **不发信号**，返回 `identity_unknown:not_signalled`；`starttime` 不符 → `identity_changed:not_signalled`。
- **盲 `killpg` 已取消**：`reclaim` 不再对组整体发信号，改为 `group_members()` 枚举成员，逐个 `send_signal`。
- **成员归属证据**：成员须同时满足 `pgrp == pgid` **且** `starttime >= leader_starttime`（组内成员不可能早于 leader 出生）。出现 `pgrp` 匹配但更早出生者 → 判 `foreign`、**立即停止一切信号**、记 `group_sweep_stopped_foreign=true`，并保留该残留事实（最终 invalid）。
- **审查 mock 反例已闭合**：`test_signal_identity_offline.py` 用 `mock.patch` 拦截 `os.kill`/`os.killpg`，`read_stat → None` 时**零 kill 调用**（见 §4.3 `read_stat_none_no_signal` / `reclaim_unknown_identity_no_signal`）。全程**未向任何真实 PID 发信号**。

### R3 共同截止（审查第 3 条）

- gate helper 改用 `Popen + wait_bounded`，超时 = `min(gate_timeout_helper_s, 剩余 − reserve)`；`helper_timeout <= 0.05` 时**跳过 helper** 并记 `helper_skipped_budget_exhausted`。
- helper 自身被 `reclaim()` 有界回收；其 stdout/stderr 归档。
- **第二方启动前**检查 `remaining_s()`；`<=0` → 不启动、记 `budget:no_remaining_before_second_launch`、有界回收先方、RC=10。
- 回归覆盖：`b_late_marker`（迟到标记，rc 3）、`b_helper_hang`（helper 卡住，rc 4，bounded）、`b_helper_budget`（helper 吃预算，第二方**未启动**）。

### R4 回收后真实 RC 与最终残留（审查第 4 条）

- 所有失败路径（A 超时、门控缺标记、门控拒绝、存活失败、侧超时）在 `reclaim()` **之后**用 `proc.poll()` 写 `wait_rc`，不再传 `None`。
- `finish_attempt()` 直接检查 `procs` 中每个进程 `poll() is None` → `own_leader_still_alive:<side>`；`group_alive(pgid)` → `group_alive_after:<side>`；任一 `reclaim.returncode is None` → `reclaim_failed_no_rc`。三类都进**最终 invalid**，**不**因扫描时排除 PID 而放过（`scan_residue(include_pids=...)` 反而把存活自有 leader 显式报出）。
- 回归：`b_no_marker` / `b_bad_identity` / `b_abrupt_exit` 的 `wait_rc` 现为**真实 0**，不再是 `None` 伪冲突。

### R5 完整原件入新根（审查第 5 条）

每例把完整原件复制进 `cases/<case>/`：

```text
cases/<case>/
├── command.json          # 完整 argv、cwd、scratch、起止配对时钟、注入时限、dataset
├── drive.json            # 驱动判定全文（含 reclaim/invalid/problems/span）
├── report/<case>-drive.json      # 驱动原始落盘位置副本
├── report/<case>-gate.json       # 门控校验器输出（若产生）
├── log/<case>-drive.log          # 逐步 JSON 行日志（含 fsync）
├── helper.stdout/.stderr         # 门控 helper 完整输出（若产生）
└── probe/<side>/{events.jsonl,result.json,clock.env,stdout.txt,stderr.txt}
```

- **未产生的原件显式记缺失**：`refuse_real`/`refuse_grant` 在写任何 attempt 产物前即拒绝，故目录里只有 `refuse.json` 与 `ABSENT.json`（声明 `command.json`/`drive.json`/`probe/*` 未产生，不以空文件冒充）。
- `cases/a_hang`、`b_late_marker` 等超时/迟到例：`result.json` 未产生即不在目录中，由 `drive.json.sides.*.result_file.exists=false` 显式记录。

## 4. 离线回归（全部在最终代码上重跑）

### 4.1 真实驱动端到端 20 例（`test_driver_offline.py`）→ **20/20**

| 用例 | 注入 | rc | span(s) | 关键断言 |
|---|---|---:|---:|---|
| `a_normal` | normal | 0 | 0.688 | valid、RC 三方一致、原件齐全（含 `command.json`/`drive.json`） |
| `a_crash` | crash_after_init | 6 | 0.063 | 非零探针 RC 被标出 |
| `a_hang` | hang | 5 | 3.022 | 有界回收、**回收后有真实 RC**、span 合规 |
| `b_normal` | pub-first | 0 | 1.082 | 门控成立、**helper 超时被夹紧**、第二方启动、存活复核通过 |
| `c_normal` | sub-first | 0 | 1.072 | 先方 sub、第二方 pub、valid |
| `b_no_marker` | no_marker | 3 | 0.122 | 第二方未启动、**先方有真实 RC** |
| `b_bad_identity` | bad_identity | 4 | 0.109 | helper 拒绝、第二方未启动、真实 RC 记录 |
| `b_ended` | ended_after_marker | 4 | 0.108 | 先方已结束被拒 |
| `b_abrupt_exit` | abrupt_exit_after_marker | **8** | 0.100 | 实时存活复核拒绝 |
| `b_second_hang` | hang_second | 6 | 3.018 | 后方超时、span 合规 |
| `b_late_marker` | late_marker(3 s) | **3** | 0.646 | 门控窗口内无标记 → 第二方未启动 |
| `b_helper_hang` | helper +8 s / timeout 0.5 | 4 | 0.590 | **helper 超时**、第二方未启动、helper 输出归档 |
| `b_helper_budget` | helper 吃 6 s / budget 4 s | 4 | 2.728 | **第二方未启动**（预算检查） |
| `a_tree` | tree_normal | 0 | 0.693 | **成员被枚举并逐个回收**、无 `killpg:` 动作、组洁净 |
| `a_no_result` | no_result | 6 | 0.680 | `result_missing_or_invalid` |
| `a_no_end` | no_end | 6 | 0.671 | `probe_end_missing` |
| `a_rc_conflict` | rc_conflict | 6 | 0.680 | RC 冲突被标出 |
| `a_residue` | residue_child | 7 | 0.685 | 逃逸子进程被检出 |
| `refuse_real` | 真实探针无授权 | 2 | — | 拒绝原因正确、无 drive 产物 |
| `refuse_grant` | `--t1-grant 0` | 2 | — | 拒绝原因正确 |

故障注入的预期失败**不计为测试失败**：断言的是"驱动是否按预期识别并记录"。

### 4.2 `validate_side` 真实函数反例 16 例 → **16/16**

`test_validate_side_offline.py` 直接 import 真实 `validate_side`/`parse_events`/`check_required`：

`positive_control`（期望放行，实际放行）、`bad_tail_rejected`、`result_missing_invalid_reasons`、`result_missing_pid`、`result_bad_type_invalid_reasons`、`result_bad_type_exit_code`、`identity_pid_mismatch`、`identity_attempt_mismatch`、`probe_end_missing_invalid_reasons`、`nonzero_wait_rc_rejected`、`no_real_wait_rc`、`stdout_missing`、`result_file_missing`、`probe_self_reported_invalid`、`middle_bad_line_rejected`、`parse_strict_vs_snapshot` —— **全部按预期拒绝/放行**。

### 4.3 信号与组归属真实函数反例 6 例 → **6/6**

`test_signal_identity_offline.py` 用 `mock.patch` 替换 `os.kill`/`os.killpg`/`read_stat`：

`read_stat_none_no_signal`、`starttime_mismatch_no_signal`、`identity_ok_signals_single_pid_only`、`reclaim_unknown_identity_no_signal`、`group_members_separates_foreign`、`reclaim_stops_on_foreign_member` —— **全部通过**，且**零真实信号**、**零 killpg**。

### 4.4 stub rclpy 探针 11 项 → **11/11**

`test_probe_offline.py`（原样吸收）：真实 `Recorder`/`create_endpoint`/`destroy` 调用，`rclpy.init` 调用数 = 0、`publish` = 0。

## 5. 本轮过程失败与修复（保留失败证据）

**it-01**：首版 `test_driver_offline.py` 把 `--fake-late-s` 传给**驱动**而非假探针 → `b_late_marker` 出现 `run_attempt_driver.py: error: unrecognized arguments: --fake-late-s 3.0`、rc=2。

- 性质：**测试接线错误**（参数归属写错），非驱动缺陷。
- 修复：`fake_cmd(late_s=...)` 把该参数注入假探针命令模板；`run_case` 增加 `late_s` 透传。
- 复验：修复后全套 20 例重跑通过；随后在**最终代码**上再跑一次全套（见 §4 与 §7 的 SHA 比对）。
- 证据：`evidence/iterations/it-01-b_late_marker-refusal.json` 与 `iterations.json`。**如实说明**：该次 `/tmp` 产物已被同名成功重跑覆盖，故该文件记录的是**当时观察到的 stderr 片段**，不是原始文件副本——不冒充原件。

## 6. 明确未做与限制

- **未执行**真实 A/B/C：T1=0；生产默认入口对真实探针 exit 2（`refuse_real`/`refuse_grant` 已验证）。本轮**未**使用 `--allow-real-ros` 启动真实探针。
- 未构建、未仿真、未抓包、未读 `/dev/shm`、未做共享资源操作、未改系统/网络/库/时钟配置。
- **限制 L1**：注入时限（budget 4 s、term/kill/sweep 各 0.3 s、helper 2 s）远短于生产默认（26 s / 1 s / 1 s / 5 s），只证明**逻辑有界**，未证明生产预算下时序足够。
- **限制 L2**：`group_members` 的归属判据依赖 `starttime >= leader_starttime`；这是**单调时钟刻度的启发式**，不能证明同组谱系（未读 `/proc/<pid>/task/*/children`）。PID 复用 + 同 PGID 复用 + 更晚 starttime 的极端组合仍可能被误判为成员。
- **限制 L3**：假探针不 import rclpy，故 rclpy 真实事件顺序/回调时机未被验证。
- **限制 L4**：`run_mode_a` 三阶段完整流程未在 stub 下跑通（仅 `Recorder`/`create_endpoint`/`destroy`）。
- **限制 L5**：`b_helper_budget` 的 rc=4 由 helper 超时触发，与"预算耗尽"分支在本次注入下未分离验证；`pre_second_budget` 记录显示第二方确未启动。

## 7. 封存与取回

首次封存，**未** `--force`，stdout 落 `/tmp/agc-w8-validation-r11-archive/`。

- 命令输出：见 §10 的结果行。
- tar 真实根、成员数、checksum/retrieval、源根逐文件一致性：见 §10。
- 封存前对**最终代码**做了最后一次全套回归（`evidence/final/*`），并核对驱动/假探针 SHA 在回归前后未变（`CODE_UNCHANGED_DURING_FINAL_RUN`）。

## 8. 判读

- 本轮只证明**离线驱动/记录边界**在假进程与 mock 系统调用下的行为符合派工要求。
- **不**证明通信行为、**不**定位根因、**不**代表任何 S2/S3/S4 进度、**不**改变 `gate`/headless/科研结论。
- 真实 A/B/C 仍需 Leader 另轮显式授权；第 9/10/11 轮预算均不滚存。

## 9. 状态

- CURRENT 置 **待审查**，已 `send_message` 通知当前父 Leader；不轮询、不接下一单。
- S2/S3/S4 关闭；`gate=not_evaluable_as_specified`；headless 规模统计未授权；P1 v5 inconclusive、P2 v3 falsified/保留 c2、W7-c deferred、W8-E2 未预注册 —— 均未因本轮改变。
- 整链不归档。

## 10. 封存与取回实测值

首次封存，**未** `--force`；命令 stdout 写 `/tmp/agc-w8-validation-r11-archive/archive.log`。

```
ok     w8-validation/20261028-endpoint-driver-offline-r2 artifacts=212 verify=True files=213 mismatches=0
archived=1 skipped=0 error=0 retrieval_failed=0
```

| 核对项 | 实测值 | 结果 |
|---|---|---|
| manifest artifacts | **212** | 逐个 size/SHA 独立复算，**mismatches = 0** |
| tar 真实根 | `20261028-endpoint-driver-offline-r2/`（唯一根） | 正确 |
| tar 成员数 | **213**（212 源文件 + `config/evidence_manifest.json` 自引用） | 与源根差集为空 |
| `root_only` | `[]` | 无遗漏 |
| `tar_only` | `['config/evidence_manifest.json']` | 该文件按脚本设计不参与源文件清单 |
| tar SHA256 | `74c3709129f21b28074f412f061378ff515786fc60c39aac4f0cafc96affc2c1` | 与 checksum 一致 |
| `.tar.sha256` | 同值（`74c37091…c2c1`） | 一致 |
| retrieval | `verified=true`、`files_checked=213`、`mismatches=0`、`archive_sha256` 同值 | 通过 |
| tar vs 源根逐文件 SHA | **0 处不一致** | 通过 |
| 封存后源根写入 | **无**（`__pycache__` 等已在封存前清除） | 合规 |

- 回归原件（20 例 `cases/`、4 份 `evidence/final/`、失败迭代 `evidence/iterations/`）**全部在封存内**，不只留 `/tmp` 引用。
- 封存前对最终代码跑完整套回归，并核对驱动/假探针 SHA 回归前后未变（`CODE_UNCHANGED_DURING_FINAL_RUN`）。
- 封存后本 report 与 `CURRENT.md` 仍可追加更正（mutable 交接文件），但**未**再写源根。
