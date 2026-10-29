<a id="round10-report"></a>
# 第10轮执行回报

- 任务 ID：20261027-001-w8-validation-recovery；轮次10。
- 执行者：Worker（DSH 子会话 `55d8793e-4916-4045-ac19-5800e167ebfa`，父会话 `session-7bfaaed2-f329-4569-8dae-f795ccdba988`）。复用用户授权更换后的同一子会话，未新建 Worker。
- 时间：领取见 §9（含一处口径更正）；结束 mono `18967883582142` ns / wall `1793165688559912542` ns（2026-10-28T13:34:48+08:00）。**整轮 mono 391.06 s ≈ 6.52 min**（wall 393.13 s），远在 45 min 内。
- 状态：**待审查**。
- 结论：**驱动离线返工已交付并通过 15 例真实驱动回归 + 11 项真实调用检查**。第9轮审查第 2–4 条未通过项已在**新根**修复；未执行真实 A/B/C（T1=0，生产默认入口对真实探针 exit 2）。

## 1. 接单与基线

| 项 | 值 | 结果 |
|---|---|---|
| CURRENT 领取前 | 任务 `20261027-001-w8-validation-recovery`、轮次 `10`、状态 `待返工` | 协议允许接单 |
| HEAD / 分支 | `d5072aaff33276bcd1c5e7d38b5caa75fe45a290` / `main` | 与派工一致 |
| 基线 SHA | `2a5100421590ec8362f7a4291560b9fd75585784faeaea2f06654c3fa582a651` | 与 `baseline_receipt.json` 一致 |
| 逐项复算 | **1322/1322 相符**，missing 0、changed 0（领取时 + 封存前各一次） | 通过 |
| `git status --porcelain` | 与 baseline `status` 逐行相同（两次核对均相同） | 通过 |
| mutable 排除 | `CURRENT.md`、`round-10/report.md`、`round-10/review.md` | 未参与冻结 |

未 reset/clean/commit/push/切分支；既有 dirty/untracked 全部保留。

## 2. 实际改动（全部新增，只落本轮新根）

`experiments/w8-validation/20261028-endpoint-driver-offline-r1/`

| 文件 | 大小 | SHA256 | 说明 |
|---|---:|---|---|
| `scripts/run_attempt_driver.py` | 35697 | `c25942e7659221985b3d2f429977140d3b20dbe898a08a5b883899156489efc5` | **核心交付**：有界截止/回收/证据/存活复核 |
| `scripts/probe_endpoint_ready.py` | 21793 | `72c18cebc8031b015dd04a2778fc7d90c154b2229ac5c85bc54280a541738cae` | 第9轮原样吸收（同 SHA，未改） |
| `scripts/validate_gate.py` | 8689 | `844e76a6af148234e3e9e3a6a74317de8d02272a7208d29627b09da6e973e4e8` | 第9轮原样吸收（同 SHA，未改） |
| `scripts/summarize_attempt.py` | 8933 | `e7d605a3a030ab78fdae441f16a32a1e5d940f64d3ceabbfcb8821dbfe917a6a` | 第9轮原样吸收（同 SHA，未改） |
| `scripts/fake_probe.py` | 9635 | `4b6680b66e7e6df735ffdceec75f3d9e3517fcddad09a56e5688c499e1b03dc9` | 假依赖探针替身（12 场景） |
| `scripts/test_driver_offline.py` | 17534 | `6bedc4de721ef2f92cd43558280562450aeee5245b55d3eac0b656b8787aced8` | 真实驱动 15 例回归 |
| `scripts/test_probe_offline.py` | 9690 | `f302456b48ec171a0f0831a8f2db5aa041950e765ba5dbc6d7f4aa90d4cd0cf7` | stub rclpy 下 11 项检查 |
| `config/sources.json` | — | 见 manifest | 来源路径/SHA/用法 |
| `config/run_identity.json` | — | 见 manifest | 领取时钟（**见 §9 更正**）、基线、T1=0、交付物 SHA、测试结果、限制 |
| `report/analysis.md` | — | 见 manifest | 修复说明、回归表、缺陷与限制 |
| `report/selfcheck-driver-suite.json` | 30493 | 见 manifest | 15 例原始输出 |
| `report/selfcheck-probe-suite.json` | 4379 | 见 manifest | 11 项原始输出 |

（`config/codex_dispatch_baseline.json`、`config/baseline_receipt.json` 为 Leader 预置，只读未改。）

**协调文件**：`CURRENT.md`（置执行中→待审查）、本 `report.md`。未改 spec/tasks/checklist/Runbook/契约/全局 scripts/src/toolchain/第9轮及更早封存源。

**过程性写入/删除（如实计入）**：`/tmp/agc-w8-validation-r10-tests/*`（15 例产物）、`/tmp/agc-w8-validation-r10-{dbg,suite.json,probe.json}`、`/tmp/agc-w8-validation-r10-archive/archive.log`；`scripts/__pycache__` 在编译/import 后**删除多次**，最终源根无 `__pycache__`/`*.pyc`。

## 3. 针对审查第 2–4 条的修复

### 第2条：无界 wait 与事后检查 → 统一有界截止（含 A）

- 驱动内**无**裸 `proc.wait()`（`grep '\.wait('` 为空）；全部用 `wait_bounded(proc, deadline_ns)` 轮询 `poll()`。
- 单一 `stage_deadline_ns = t0 + budget_s`（默认 **26 s**，留 4 s 给 30 s 硬上限），回收内每一步用 `min(...)` 继续夹紧。
- **A 与 B/C 共用同一 `finish_attempt()`**：`span` 一律算到"全部回收完成之后"；失败路径不再在回收前截断（这正是第9轮 A 遗漏的点）。
- `reserve_s`（默认 3 s）先扣，保证回收本身有额度。

### 第3条：A 无残留证据 / 驱动 exit 0 不等于有效 → 统一证据核对

`validate_side()` 每侧强制核对：`wait_rc` 非缺失且为 0、`result.json` 存在且 `pid`/`exit_code` 与本次一致、`probe_end.exit_code` 与 `wait_rc` 一致、`invalid_reasons` 为空、`stdout`/`stderr` 文件存在、事件流可解析。任一不符进 `problems` 并判失败。

- 驱动退出码分级：0 通过 / 2 拒绝 / 3 门控超时 / 4 门控身份拒绝 / 5 侧超时 / 6 证据问题 / 7 残留 / 8 存活复核失败 / 9 span 超限。
- **回收状态与诊断结论分开**：`reclaim[]` 只记信号/时长/`group_alive_after`，`problems[]`/`invalid[]` 记判定。

### 第4条：快照里无 `probe_end` 不是实时存活证明 → 门控后实时复核

门控通过后、启动第二方**前**再读 `/proc/<pid>/stat`：比对 `starttime`、排除 `Z`、并检查 `probe_end` 是否已写出。任一不满足 → 记 `liveness_recheck` 证据、**不起第二方**、exit 8、不 fallback。

回归用例 `b_abrupt_exit`（先方写完 `endpoint_created` 立即 `os._exit(0)`）**确定性触发**该分支并返回 rc 8。

## 4. 命令与结果

| # | 命令 | 退出码 | 结果 |
|---|---|---|---|
| 1 | `python3 -m py_compile scripts/*.py` | 0 | 全部通过（随后删除 `__pycache__`） |
| 2 | `python3 scripts/test_driver_offline.py` | **0** | **15/15 通过** |
| 3 | `python3 scripts/test_probe_offline.py` | **0** | **11/11 通过**（`rclpy.init` 调用数 = 0） |
| 4 | `python3 scripts/evidence_archive.py --campaign w8-validation --run-id 20261028-endpoint-driver-offline-r1` | 0 | `artifacts=14 verify=True files=15 mismatches=0` |
| 5 | 独立复核 manifest/tar/checksum/retrieval/源根 | — | 见 §8，全部一致 |

### 4.1 驱动回归 15 例（真实执行 `run_attempt_driver.py`，注入短时限）

| 用例 | 注入 | rc | span(s) | 关键断言 |
|---|---|---:|---:|---|
| `a_normal` | normal | 0 | 0.679 | valid=true；RC 三方一致；stdout/stderr 在场；无残留 |
| `a_crash` | crash_after_init | 6 | 0.060 | 非零 RC 被标出，未误判通过 |
| `a_hang` | hang | 5 | 3.013 | 有界回收；span<硬上限；`a_side_timeout` |
| `b_normal` | pub-first | 0 | 1.084 | 门控成立、checker rc 0、第二方启动、存活复核通过 |
| `c_normal` | sub-first | 0 | 1.075 | 先方=sub、第二方 pub 启动、valid=true |
| `b_no_marker` | no_marker | 3 | 0.112 | 门控超时、**第二方从未启动** |
| `b_bad_identity` | bad_identity | 4 | 0.110 | checker 拒绝、**第二方从未启动** |
| `b_ended` | ended_after_marker | 4 | 0.098 | 先方已结束被拒 |
| `b_abrupt_exit` | abrupt_exit_after_marker | **8** | 0.098 | **实时存活复核**拒绝 |
| `b_second_hang` | hang_second | 6 | 3.017 | 后方超时 + 先方回收 |
| `a_no_result` | no_result | 6 | 0.677 | `result_missing_or_invalid` |
| `a_rc_conflict` | rc_conflict | 6 | 0.679 | `probe_end`=0 vs 真实 RC=1 冲突被标出 |
| `a_residue` | residue_child | 7 | 0.679 | 逃逸子进程被检出 |
| `refuse_real` | 真实探针无授权 | 2 | — | marker 写明 `real_ros_requires_--allow-real-ros`；无 drive 产物 |
| `refuse_grant` | `--allow-real-ros --t1-grant 0` | 2 | — | marker 写明 `...--t1-grant>=1` |

故障注入的**预期失败不计为测试失败**：每例断言的是"驱动是否按预期识别并记录"，例如 `a_crash` 期望 rc≠0 且 `valid=false`。

### 4.2 探针回归 11 项（stub rclpy，真实调用真实函数）

注入 `rclpy`/`rclpy.node`/`rclpy.qos`/`rclpy.event_handler`/`rclpy.utilities`/`std_msgs.msg` 假模块树后 import **真实** `probe_endpoint_ready.py`：

`recorder_writes_kind_field`、`recorder_seq_strict`、`recorder_all_tagged`、`recorder_event_order`、`create_endpoint_pub_and_sub`、`created_markers_have_identity`、`no_destroy_error`、`no_rclpy_init_called`、`no_demo_publish`、`selfcheck_rc_0`、`selfcheck_reports_no_participant` —— 全部 pass；`rclpy.init` 调用数 **0**、`publish` 调用数 **0**。

## 5. 本轮实测并修复的自身缺陷（如实记录）

**D1 残留扫描误判工具自身** —— `b_abrupt_exit` 首轮命中 `residue` 的是**我自己的 shell 工具进程**（heredoc 文本含 attempt token），导致 rc=7 而非预期 rc=8。根因：`scan_residue` 只匹配 token 子串。修复：收紧为"含 token **且** 含本 attempt `scratch` 路径或探针脚本名"。复验后 15 例全通过，且 `a_residue` 仍能检出**刻意 setsid 逃逸**的子进程（检测力未被削掉）。

**D2 假探针第二方判定不稳** —— 初版靠场景名后缀推断第二方，与驱动参数耦合。修复：驱动新增 `{second}` 占位符显式传入第二方角色，假探针用 `--fake-second-side` 接收；`ended_before_second` 更名为 `ended_after_marker`。

两处均为**本轮测试工具**问题，未触及第9轮封存源。

## 6. 未执行项

- **未执行**真实 A/B/C：T1=0；生产默认入口对真实探针 exit 2（已在 `refuse_real`/`refuse_grant` 用例中验证）。
- 未构建、未仿真、未抓包、未读 `/dev/shm`、未做共享资源操作、未改系统配置、未起 observer/daemon。
- 未改第9轮及更早封存源、历史归档、spec/Runbook/全局 scripts/src。

## 7. 判读

- 本轮只证明**驱动的截止、回收、证据核对、门控后存活复核在假进程下按设计工作**。
- **不**证明通信行为、**不**定位根因、**不**代表 S2/S3/S4 任何进度、**不**改变 `gate`/headless/科研结论。
- 真实 A/B/C 仍需 Leader 另轮显式授权；本轮预算不滚存。

## 8. 封存与取回（首次，未 `--force`）

- 命令 stdout：`ok w8-validation/20261028-endpoint-driver-offline-r1 artifacts=14 verify=True files=15 mismatches=0`。
- tar 真实根 `20261028-endpoint-driver-offline-r1/`，成员 **15**；解包与源根**逐文件 SHA 全等**（`tar_vs_root_mismatches=[]`），`root_only=[]`，`tar_only=['config/evidence_manifest.json']`（自引用，符合脚本设计）。
- tar SHA256 `277e7c7b49f42e142c3bae32c0536d19cd8d7999b8e83bf008f9df6757baa959`，与 `.tar.sha256`、`.retrieval.json.archive_sha256` 三者一致；retrieval `verified=true`、`files_checked=15`、`mismatches=0`。
- manifest 14 个 artifact 的 size/SHA 独立复算全符。
- 封存后未写源根（`__pycache__` 已在封存前清除）。

## 9. 领取时钟口径更正（如实）

`run_identity.json` 中 `claim.mono_ns = 18835500502220` / `wall_ns = 1793165554103182614` 实际是**跑完两套回归之后**的一次配对采样，**不是**领取时点。真实领取时点以 `CURRENT.md` 置"执行中"的 mtime 为准：

| 口径 | 值 |
|---|---|
| 领取 wall（`CURRENT.md` mtime） | `1793165295426264015` |
| 领取 mono（由同时刻 wall/mono 关系反推） | `18576823583612` |
| 该反推的自洽性 | 反推时偏移与后续 mid 采样偏移相差 **−9 ns**（稳定） |
| 结束 mono / wall | `18967883582142` / `1793165688559912542` |
| **整轮 mono** | **391.06 s ≈ 6.52 min** |
| 整轮 wall | 393.13 s（offset 在 mid→end 段漂移 +2.07 s，见下） |

- wall/mono 偏移在本轮窗口内**仍有漂移**（mid→end 段 +2.0737 s），原因未查明，本轮**不假设原因**（审查已明确 NTP 活跃不能证明来源）。
- 预算判定以 **monotonic** 为准：391.06 s ≪ 45 min，合规。
- 该字段位于封存源根内，按"封存后不写源根"规则**未回改**；以本节为准。

## 10. 状态

- CURRENT 置 **待审查**，已 `send_message` 通知当前父 Leader；不轮询、不接下一单。
- S2/S3/S4 关闭；`gate=not_evaluable_as_specified`；headless 规模统计未授权；P1 v5 inconclusive、P2 v3 falsified/保留 c2、W7-c deferred、W8-E2 未预注册 —— 均未因本轮改变。
- 整链不归档。
