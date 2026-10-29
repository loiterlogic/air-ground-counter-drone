<a id="round13-report"></a>
# 第13轮执行回报

任务 ID：20261027-001-w8-validation-recovery；轮次13。

执行者：Worker（DSH 子会话 `55d8793e-4916-4045-ac19-5800e167ebfa`，父会话 `session-7bfaaed2-f329-4569-8dae-f795ccdba988`）。复用同一子会话。

## 0. 领取配对时钟（本轮第一个动作，先于任何读取/执行）

| 字段 | 值 |
|---|---|
| `claim_mono_before_ns` | `20101086476944` |
| `claim_wall_ns` | `1793166845366599286` |
| `claim_mono_after_ns` | `20101086477670` |
| `claim_pair_gap_ns` | `726` |

**口径**：本表为本轮唯一领取时钟依据；不用 mtime 反推。预算以同机 monotonic 判定。

## 1. 接单与基线

| 项 | 值 | 结果 |
|---|---|---|
| CURRENT 领取前 | 轮次 `13`、状态 `待执行` | 协议允许接单 |
| HEAD / 分支 | `d5072aaff33276bcd1c5e7d38b5caa75fe45a290` / `main` | 一致 |
| 基线 SHA | `71bb026daa5cffa31039e2edfc71de7fd13e47fa0ce10ebaead08ad54c9b2528` | 与 receipt 一致 |
| 逐项复算 | **1843/1843**，missing 0、changed 0 | 通过 |
| `git status --porcelain` | 与 baseline `status` 逐行相同 | 通过 |
| 既有运行/冲突 | 无自有或他人 ROS 探针进程；`/tmp/agc-w8-validation-r13-*` 运行前不存在 | 通过 |

**工具只读核对**（与第12轮封存 manifest 逐项一致，未修改、未产生 `__pycache__`）：
`run_attempt_driver.py` `5fd70384…121d`、`probe_endpoint_ready.py` `72c18ceb…38cae`、`validate_gate.py` `844e76a6…3e4e8`。

**运行前静态检查**（`config/static-check-A.json`）：参数指向新根 `--run`、独占 `--scratch /tmp/agc-w8-validation-r13-A1`、`--clean-env`、`--wrap-source /opt/ros/jazzy/setup.bash`、两个 `--dataset`（domain0/LOCALHOST）、`--allow-real-ros --t1-grant 3`、无 `--allow-fake` —— 全部通过。

## 2. 执行结果：A1 invalid，B1/C1 未执行

| 项 | 值 |
|---|---|
| 驱动 exit code | **6** |
| `valid` | **false** |
| `invalid` | `["a_evidence"]` |
| 驱动 span | `0.517311 s`（首方启动→回收完成，有界） |
| 探针 wait RC | **2** |
| **ROS participant** | **0**（`rclpy.init` 从未执行） |
| events / result | **未产生** |
| B1 (pub-first) | **未执行** |
| C1 (sub-first) | **未执行** |
| A1 重跑 | **未执行** |

`problems`：`a:events_missing`、`a:result_missing_or_invalid`、`a:probe_end_missing`、`a:nonzero_probe_rc:2`。

### 根因（我方模板错误，非 ROS 行为）

探针 stderr（关键原件 `cases/A1/probe/a/stderr.txt`）：

```text
probe_endpoint_ready.py: error: unrecognized arguments: --second
```

- 我在编排 `--probe-cmd` 时把第12轮**假探针**测试的 `--second {second}` 占位符带进了**真实探针**命令模板；真实 `probe_endpoint_ready.py` 的 argparse 不接受该参数。
- 失败发生在 argparse 解析阶段，`rclpy.init()` 未执行 → 0 participant、0 事件、无 `result.json`。
- 故这是**编排层 invalid**，不构成任何 ROS/DDS 证据，也不否证 A 步控制语义。
- 运行前静态检查未覆盖"真实探针不接受假探针占位符"这一项——这是我检查清单的缺口，不是驱动/探针/门控器缺陷。

### 按派工执行的停止

派工要求"A 任一不符或 invalid 停止 B/C"、"不现场修改代码或换配置重试"、"无额外重跑预算"。据此：

- B1、C1 **未执行**；A1 **未重跑**；未现场改任何被调用的脚本，未换 domain/discovery/QoS/topic。
- 仅在**执行结束后**修正了 `config/build_cmd.py`（编排器，非被调用的第12轮脚本）的模板用于留痕，`config/static-check-A-corrected.json` 记录修正后静态检查通过，**该修正版本未被运行**。

## 3. 预算

| 口径 | 值 |
|---|---|
| T1 使用 | **1/3**（仅 A1）；B1/C1 各 0 |
| A1 单次 span | `0.517311 s` ≪ 30 s |
| 累计 T1 span | `0.517311 s` ≪ 90 s |
| ROS participant 峰值 | **0** ≤ 2 |
| **整轮 mono** | **94.141 s ≈ 1.57 min**（≪ 45 min） |
| wall | 95.598 s（该窗口偏移漂移 +1.457 s，如实报告、不假设原因） |

## 4. 过程性写入与原件

- 新根 `experiments/w8-validation/20261028-endpoint-gated-probe-r1/`：`config/`（baseline、build_cmd.py、两份静态检查）、`log/`、`report/`（`A1-drive.json`、`analysis.md`）、`cases/A1/`（command、drive、probe/a/stdout+stderr、scratch 副本）、`evidence/A1-failure-record.json`。
- `/tmp/agc-w8-validation-r13-{A1,static-a.json,static-a2.json,cmd-A.json}` 过程输出。
- **未产生**：`cases/A1/probe/a/events.jsonl`、`cases/A1/probe/a/result.json` —— 已在 `evidence/A1-failure-record.json` 显式声明为未产生，不以空文件冒充。
- `__pycache__`：新根内**无**；第12轮源根复算 manifest 274 项仍全符、无 `__pycache__`、mtime 均早于本轮 claim → **未污染只读源根**。

## 5. 判读

- 本轮**无任何** `heard`/`matched`/`graph` 样本，**不能**判断通信是否成立，也**不能**判断旧"随启动顺序翻转的单向匹配+零消费"形态在 endpoint 门控下是否仍在。
- **不能**把本次失败读作"环境失效"或"endpoint 门控无效"——失败点在命令行解析，早于任何 ROS 调用。
- `endpoint_created` 语义（API 返回 ≠ DDS 发现就绪）本轮**未被观测到**（0 事件）。
- A 步真实控制有效性仍未验证；该缺口需在修复模板后另轮授权。

## 6. 状态

- CURRENT 置 **阻塞**（A invalid、B/C 未执行、无重跑预算，需 Leader 裁定是否追加/另派）。
- S2/S3/S4 关闭；`gate=not_evaluable_as_specified`；headless 未授权；P1/P2/W7-c/W8-E2 状态不变；整链不归档。

## 7. 封存与取回实测值

首次封存，**未** `--force`；stdout 写 `/tmp/agc-w8-validation-r13-archive/archive.log`。

```
ok     w8-validation/20261028-endpoint-gated-probe-r1 artifacts=15 verify=True files=16 mismatches=0
archived=1 skipped=0 error=0 retrieval_failed=0
```

| 核对项 | 实测值 | 结果 |
|---|---|---|
| manifest artifacts | **15** | 逐个 size/SHA 复算，**0 mismatch** |
| tar 真实根 | `20261028-endpoint-gated-probe-r1/`（唯一） | 正确 |
| tar 成员数 | **16**（15 源文件 + manifest 自引用） | 差集为空 |
| `root_only` / `tar_only` | `[]` / `['config/evidence_manifest.json']` | 符合脚本设计 |
| tar SHA256 | `09788d6564d3ef5c890fc5e9a445d07e5d0a3fc65ad40bf037d282ddba4192ff` | 与 checksum 一致 |
| retrieval | `verified=true`、`files_checked=16`、`mismatches=0` | 通过 |
| tar vs 源根逐文件 | **0 处不一致** | 通过 |
| 封存后源根写入 | **无** | 合规 |

## 8. 结束配对时钟

| 字段 | 值 |
|---|---|
| `end_mono_before_ns` | `20195227849602` |
| `end_wall_ns` | `1793166940964544446` |
| `end_mono_after_ns` | `20195227850239` |
| `end_pair_gap_ns` | `637` |

整轮 **mono 94.141 s ≈ 1.57 min**；wall 95.598 s；偏移漂移 +1.457 s。
