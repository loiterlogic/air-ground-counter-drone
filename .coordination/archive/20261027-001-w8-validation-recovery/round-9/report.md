<a id="round9-report"></a>
# 第9轮执行回报

- 任务 ID：20261027-001-w8-validation-recovery；轮次9。
- 执行者：Worker（DSH 子会话 `55d8793e-4916-4045-ac19-5800e167ebfa`，父会话 `session-7bfaaed2-f329-4569-8dae-f795ccdba988`）。**来源：用户本轮明确授权更换 Worker**（经 Leader 转达）；原 `e3e1d72b-6416-4f72-b66a-a246decef378` 属旧父会话，`send_message` 被拒（`belongs to another parent session`），本轮不再作为执行者。此授权仅调整执行会话，任务 ID/第9轮规格/基线/预算均未变，未新增任务流或实验预算。
- 领取：mono `17417797035601` ns / wall `1793164113469638972` ns（2026-10-28T13:08:33+08:00）；结束：mono `18024595132956` ns / wall `1793164732838265404` ns（2026-10-28T13:18:52+08:00）。整轮 **606.798 s ≈ 10.11 min**，在 45 min 之内。
- 状态：**阻塞**（原因为新探针自身缺陷导致 A 步 invalid，B/C 按停止条件未执行；修复已离线完成但授权内无重跑预算）。**不是**成功，也**不是**被环境否决。
- 交接前的身份更正：本文件原由 Leader 预置、署名为旧 Worker，并记述派发失败。该记述是**换 Worker 前的事实**，原样保留于下方「Leader 派发记录」；本节及以下为换 Worker 后的实际执行记录。

## Leader 派发记录（原文保留，事实不变）

来源：Leader，本次接手。派工/规格已准备，冻结1299保护项并逐项复算通过；尚未执行任何T1或新增工程探针。

向原Worker发送派工时，工具拒绝：`subagent "e3e1d72b-6416-4f72-b66a-a246decef378" belongs to another parent session`。当前Leader是新父会话，无权向旧父会话的子会话投递。按通知失败与同链复用规则，停止派发、保留待执行，不另建Worker绕过。需原父会话派发，或用户明确授权更换Worker。此项不是诊断结果或验收结论。

> 更正（来源：Worker，2026-10-28）：用户随后授权更换 Worker，本条由新执行会话续接；上段的"停止派发"状态已由此授权解除，其余内容为当时事实，不改写。

## 1. 接单与基线核对

| 项 | 值 | 结果 |
|---|---|---|
| CURRENT 领取前 | 任务 `20261027-001-w8-validation-recovery`、轮次 `9`、状态 `待执行` | 属协议允许接单状态 |
| HEAD / 分支 | `d5072aaff33276bcd1c5e7d38b5caa75fe45a290` / `main` | 与派工一致 |
| 基线 SHA | `44d37751f07820f6d4a8fd3439ea203c3842c8e3956140c5bcffee052f8f79f9` | 与 `baseline_receipt.json` 相符 |
| 逐项复算（领取时） | **1299/1299 相符，missing 0、changed 0** | 通过 |
| `git status --porcelain` | 与 baseline `status` 字段逐行完全相同 | 通过 |
| 父基线 | SHA `8454950d…ce2001f` 实测相符；差值 +23 / −0 / ~4 | 4 处为本轮授权文档（round9 三件套、Runbook） |
| `absent_from_parent_or_previous_tree` | `[]` | 无应缺未缺 |
| 封存前再复算 | **1299/1299 相符，missing 0、changed 0**；status 仍逐行相同 | 通过 |

未 reset/clean/commit/push/切分支；全部既有 dirty/untracked 原样保留；未改 spec/request/review/Runbook/契约/src/scripts/toolchain/build/install 及其他协调文档。

## 2. 实际改动

### 2.1 新根（全部新增，首次封存）

`experiments/w8-validation/20261028-endpoint-ready-probe-r1/`

| 文件 | 大小 | SHA256 |
|---|---:|---|
| `scripts/probe_endpoint_ready.py` | 21793 | `72c18cebc8031b015dd04a2778fc7d90c154b2229ac5c85bc54280a541738cae` |
| `scripts/validate_gate.py` | 8689 | `844e76a6af148234e3e9e3a6a74317de8d02272a7208d29627b09da6e973e4e8` |
| `scripts/summarize_attempt.py` | 8933 | `e7d605a3a030ab78fdae441f16a32a1e5d940f64d3ceabbfcb8821dbfe917a6a` |
| `scripts/selfcheck_gate.py` | 5293 | `350ad4725cbe9da4ecdf82066458ce327c83d1c7d0cb42f40411346d94794caf` |
| `scripts/selfcheck_probe_offline.py` | 4399 | `dc765d9ef20fe0a46cb79ada6672777d8d54f8339bc5a23bdf2d85b84855e114` |
| `config/run_attempt_driver.sh` | 10299 | `14810acb235d7b88704ca74acc83472720dc1dbf754afdad88f69e83e9f7d9d3` |
| `config/run_identity.json` | — | 见 manifest |
| `log/10-attempt-a1.log` | 3329 | `681bbdfd9359071611a455f6b157cce8a6573fff9839bd835ef63231dedac831` |
| `log/a1-a-events.jsonl` | 3684 | `290ed7c7c93f8abbe1e12f71ccbf57d9c50d02576b285bd209257a852c87b223` |
| `report/a1-a-result.json` | 3926 | `20c8ca2d6edb74d59f52b1877ac95f6cb19abdaa52fb82f9da7d413d640fdec0` |
| `report/a1-a-clock.env` | 146 | `b0fa8c618acee674f13e9245a7ed1a5e56a728746d103ffe443c59836b2bfbf3` |
| `report/analysis.md` | — | 见 manifest |
| `report/selfcheck-gate.json`、`report/selfcheck-probe-offline.json` | — | 见 manifest |

（`config/codex_dispatch_baseline.json`、`config/baseline_receipt.json` 为 Leader 预置只读，未改动。）

### 2.2 协调文件（允许写入的两处）

- `.coordination/CURRENT.md`：领取时置 `执行中` 并写入新 Worker 身份与领取时点；结束时置 `阻塞`（见 §8）。
- 本文件 `round-9/report.md`。
- **未**勾选 `.trae/specs/w8-validation-recovery/tasks.md` / `checklist.md` 的 round9 条目：A 未通过、B/C 未执行，语义上不成立，不代填执行事实；预期勾选差异 = 无。

### 2.3 过程性写入与删除（如实计入）

- `/tmp/agc-w8-validation-r9-a1/`（本单独占临时目录：事件、stdout/stderr、ros_home/ros_log）——保留，未清理。
- `/tmp/agc-w8-validation-r9-selfcheck-probe.json`、`/tmp/agc-w8-validation-r9-archive/{archive.log}`——过程输出。
- `scripts/__pycache__/`（由 `py_compile`/import 产生）**删除了 3 次**（每次自检或编译后重建）：均在封存前完成，最终源根不含 `__pycache__`/`*.pyc`。
- 未发生"封存后写源根"。

### 2.4 旧探针与历史证据

`experiments/w8-validation/20261027-layered-matched-probe-r1/scripts/probe_layered.py`（SHA `137eeed3…af389`）**只读、未复制、未修改**；第 1–8 轮源根与 `_archive` 均未写。

## 3. 新增探针与门控（本轮工程交付）

依据本机 rclpy 7.1.12 源码、第 3 轮已验收同进程控制实现：

| 学习来源 | SHA |
|---|---|
| `/opt/ros/jazzy/lib/python3.12/site-packages/rclpy/__init__.py` | `15b5665a97a688645545e704a6111a5be5f5b2d147cfcf099e2f92aabcbdf00f` |
| `…/rclpy/node.py` | `8b7fe0ea64e0de12cc1d5d01ebf56c202fa6e153251eb71dfff93e35eb5b3c80` |
| `…/rclpy/context.py` | `a33eb8a3a7bf4f43b45e7acc3d5efd85a5fbf8da7626c069494215a342df6c77` |
| `…/rclpy/publisher.py` / `subscription.py` / `qos.py` | `2d5fdce9…77ae` / `b21a0f4e…0ef9` / `0fba9cda…45f6` |
| 第 3 轮 `probe_layered.py`（只读） | `137eeed310abd803fbbe27a4339bd7dc126ee5bd3b3e89668b81b08d73baf389` |

- `post_init`（`rclpy.init()` 返回后）、`node_created`（`Node(...)` 返回后）、`endpoint_created`（`create_publisher`/`create_subscription` 返回后）三事件均**紧邻 API 成功返回**写出并 `flush`（生命周期事件额外 `fsync`）；`endpoint_created` 含 `attempt`/`pid`/`pgid`/`role`/`kind`/`topic`/QoS 回读/`api`/`create_api_ns` 与配对 `at`(mono→wall→mono)。
- **口径**：`endpoint_created` 只表示创建 API 返回，不表示 DDS 发现/匹配/可消费；`process_entry` 仍是脚本进入标记，不是就绪证据。
- 门控器 `validate_gate.py` 校验唯一性、`attempt`/`pid`/`role`/`kind`/`topic`/`mode` 逐字相符、QoS=RELIABLE/KEEP_LAST/10、`post_init` 与 `node_created` 的 `seq` 与时钟更早、先方未写 `probe_end`；不符即拒绝且**不 fallback**到 `probe_start` 或固定 sleep。
- 驱动在门控通过后**立即**启动后启动方，无额外固定 sleep（`NO_FIXED_SLEEP=true` 写入日志）。

## 4. 命令、退出码与结果

| # | 命令 | 退出码 | 结果 |
|---|---|---|---|
| 1 | `python3 probe_endpoint_ready.py --self-check` | 0 | 离线自检（未 init） |
| 2 | `python3 -m py_compile` / `rm -rf __pycache__` | 0 | 语法通过 |
| 3 | `python3 scripts/selfcheck_gate.py` | 0 | 11 例合成事件**全通过** |
| 4 | `python3 scripts/selfcheck_probe_offline.py`（修复后） | 0 | AST 17 调用点无冲突 + 动态写出 6 行通过 |
| 5 | `bash -n config/run_attempt_driver.sh` | 0 | 驱动语法通过 |
| 6 | **`bash config/run_attempt_driver.sh a a1 10 r9a`（T1 #1）** | 驱动 0 / 探针 **1** | **INVALID：`fatal:TypeError`** |
| 7 | `python3 scripts/evidence_archive.py --campaign w8-validation --run-id 20261028-endpoint-ready-probe-r1` | 0 | `artifacts=16 verify=True files=17 mismatches=0` |

### attempt `a1`（A 同进程控制，T1 第 1 次）

- 环境：`ROS_DOMAIN_ID=0`、`ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST`；未设 `FASTDDS_BUILTIN_TRANSPORTS`/`ROS_STATIC_PEERS`/`RMW_IMPLEMENTATION`/`LD_PRELOAD`/profiles；`env -i` + 仅 `source /opt/ros/jazzy/setup.bash`；`ROS_HOME`/`ROS_LOG_DIR` 独占。
- 进程：1 个 ROS participant（PID 15880 / PGID 15880），`set -m` 独立 PGID，`wait` 取真实 RC。
- 时长：驱动 span **1.540 s**；探针 `wall_s` **0.544059 s**。均 < 30 s。
- 标记：`process_entry` → `post_init`（`init_api_ns=33241970`）→ `node_created`（`node_api_ns=188024793`）已写出；`rmw_implementation=rmw_fastrtps_cpp`；**`endpoint_created` 从未写出**。
- 失败：`TypeError: Recorder.event() got multiple values for argument 'kind'`（`probe_endpoint_ready.py:189`）——`Recorder.event()` 首参名 `kind` 与字段 `kind='pub'` 冲突。属**探针自身缺陷**，与 ROS/DDS 行为无关。
- 回收：探针自行退出，**未发送任何信号**；`RESIDUE=0`、`STRAY=[]`；事后独立扫描无残留。
- invalid：`["fatal:TypeError"]`；无 `incompatible_qos_event`、无任何 `sample` 帧。

## 5. 未执行项（明确标记）

- **B（pub-first）未执行**、**C（sub-first）未执行**：派工单第 20 行"A 全部有效后 B/C"，A 未通过；且第 16 行无额外重跑预算。
- **A 未重跑**：修复后未在授权内二次运行（重跑需 Leader 追加授权）。
- **未执行**：构建、抓包、仿真、GZ/PX4/GUI/headless、额外 observer/daemon、读 `/dev/shm`、共享资源清理、系统/网络/库/时钟改动；未新增/修改 `.trae` 规格勾选。
- 未做任何 fallback（未用 `probe_start`、未用固定 sleep、未改配置、未换 topic/domain）。

## 6. 判读（API / 发现 / 匹配 / 消费严格分开）

- 本轮**没有任何**通信层结论：A 步三阶段一次都没跑起来，`heard`/`matched`/`graph` 全部无样本。
- 已观测到的只有：`rclpy.init()` 返回、`Node(...)` 返回、`rmw_fastrtps_cpp` 被选用。**这不等于** participant 完成发现，也不等于任何 endpoint 创建成功。
- `create_publisher` 是否成功返回在本轮**无证据**：异常发生在调用之后的记录步骤，早于 `return ent`。
- 因此：**探针与同进程控制仍未验证**；按派工单第 26 行，不得据此判定环境整体失效，也不得据此关闭任何既有假设。
- 与第 3–8 轮的关系：本轮**既未支持也未反驳**"初始化时序是候选解释"；旧形态复现证据仍以第 8 轮（及既有审查）为准，本轮不追加样本。

## 7. 偏离与阻塞

**偏离 D1（探针缺陷，已离线修复）**

- 事实：首次执行即因参数名冲突崩溃，这是**可在运行前用离线检查发现**的低级缺陷（同类冲突已在 `selfcheck_gate.py` 中出现过一次并修复，未在探针本体上复查）。
- 处置：用 **T0 纯离线**手段（AST 扫描 + 真实写出路径回归）定位、修复、回归；修复后 SHA `72c18ceb…38cae`。
- 边界：修复**未**重跑验证；`a1` 的运行时 SHA `d40e73d2…1affd` 与最终 SHA 不同，`run_identity.json` 同时记录两者，旧 SHA 与其缺陷一并保留，不覆盖失败记录。
- 未越界：修复与自检均未启动 ROS、无 participant、未消耗 T1。

**阻塞 B1**

- 阻塞条件：A 步无有效结果（探针缺陷），而重跑需额外 T1 授权；派工单明确"无额外重跑预算"，且"有效失败不重跑"。故本轮无法在授权内完成 A 验证，进而 B/C 的门控对照无法执行。
- 现场：探针、门控器、驱动、离线回归证据均已就绪并通过 T0 检查；只要追加 1 次 T1（A）即可继续，A 通过后再走 B/C。
- 待裁定（交 Leader）：① 是否追加 T1 授权重跑 A（及随后 B/C）；② 是否要求先行离线复核探针再放行；③ 本轮是否按"阻塞"记录而不进入返工。

## 8. 证据、封存与取回

- 首次封存（**未**用 `--force`），stdout 落 `/tmp/agc-w8-validation-r9-archive/archive.log`：
  `ok w8-validation/20261028-endpoint-ready-probe-r1 artifacts=16 verify=True files=17 mismatches=0`。
- tar 真实根 `20261028-endpoint-ready-probe-r1/`，成员 **17**；解包后与源根**逐文件 SHA 全等**（`tar_vs_root_hash_mismatches=[]`），`root_only=[]`，`tar_only=['config/evidence_manifest.json']`（自引用，符合脚本设计）。
- tar SHA256 `fa0038fead9b80b67778e34f77f5842c0347a8af5f2a0b55c558dd24771dacc5`，与 `.tar.sha256`、`.retrieval.json` 的 `archive_sha256` 三者一致；retrieval `verified=true`、`files_checked=17`、`mismatches=0`。
- manifest 16 个 artifact 的 size/SHA **独立复算全符**。
- 封存后**未写源根**（拒绝编译/自检产物入库；`__pycache__` 已在封存前清除）。

## 9. 状态

- CURRENT 置 **`阻塞`**，待 Leader 裁定（不自行返工、不开下一任务、不轮询）。
- `S2/S3/S4` 继续关闭；`gate=not_evaluable_as_specified`；headless 规模统计未授权；P1 v5 inconclusive、P2 v3 falsified/保留 c2、W7-c deferred、W8-E2 未预注册 —— 均**未因本轮改变**。
- 整链不归档。

<a id="round9-selfcorrection"></a>
## 10. 追加自查更正（封存后，来源：Worker）

触发：封存完成后复核自身记录的时钟与日志字段时发现两处**我这边的记录不准确**（不是新观测，不改任何结论、不改状态含义、不改封存源）。封存源根按协议保持只读，未写回。

### 更正 C1：`RESIDUE`/`STRAY` 字段只存在于 B/C 路径，A 路径日志没有

- §4 attempt `a1` 写有"`RESIDUE=0`、`STRAY=[]`"，**不准确**。
- 实际：`config/run_attempt_driver.sh` 的 `MODE=a` 分支在 `write_log` 前就 `exit 0`，`EXTRA` 里只有 `WAIT_RC_A`、`ATTEMPT_SPAN_S`、`T1_*` 与摘要 JSON；`RESIDUE`/`STRAY` 只在 pub_first/sub_first 分支写出。所以 `log/10-attempt-a1.log` 中**没有**这两个字段（`grep -c` = 0，已复核）。
- 因此 a1 的"无残留"依据应改为：**§4 所述的事后独立进程扫描**（`pgrep -f probe_endpoint_ready|validate_gate|summarize_attempt` 无匹配）与探针自行退出、`WAIT_RC_A=1`。该结论本身**不变**（确实无残留），但**不能**引用不存在的日志字段。
- 同一处不准确也存在于封存源根的 `report/analysis.md` §8。按封存后只读规则，**不修改该文件**；以本节为准。

### 更正 C2：本轮 wall 时钟与 monotonic 的偏移在窗口内漂移了约 12.6 s，故"整轮 10.11 min"只是 monotonic 口径

- §头与 `run_identity.json` 用 mono 差给出 **606.798 s ≈ 10.11 min**；同时用 wall 差算得 **619.369 s ≈ 10.32 min**。两者**不自洽**，因为本机（WSL2，`System clock synchronized: yes`，NTP 活跃）在该窗口内 wall 被调整过：
  - 领取前配对偏移 `wall-mono = 1793146690.0406 s`；领取时 `1793146695.6726 s`（+5.632 s）；a1 启动 `1793146705.4820 s`（再 +9.809 s）；a1 结束时回到 `+0.000`；结束 `1793146708.2431 s`。
  - 即 **claim→end 期间偏移共漂移 +12.571 s**，与 mono/wall 差 12.371 s 同量级（余差来自我两次独立采样之间的间隔）。
- 口径更正：**45 min 预算以 monotonic 为准**（协议要的就是 wall 硬上限的等价保护）。mono 口径 **606.798 s ≈ 10.11 min**，仍远低于 45 min；wall 口径 619.369 s ≈ 10.32 min 也合规。**预算结论不变**。
- 影响范围：所有跨进程序列（领取、a1 启动/结束、结束时钟）在**mono 轴**上仍严格有序（已逐点核验单调递增），故事件先后与重叠判断**不受影响**；仅"wall 时间点对应关系"在本轮内不可作为高精度依据。
- 该漂移**不影响** a1 的 invalid 判定（由 `TypeError` + `exit_code=1` + 无 `endpoint_created` 决定）。
- `run_identity.json` 的 `claim_to_handoff_min_approx: 12.1` 是封存前估写值，与本更正并存时**以 §10 C2 的两个口径为准**。该文件在封存源根内，按协议不改写。

### 更正后不变的结论

- A 步仍为 **INVALID**（探针自身 `TypeError`），B/C 仍未执行，T1 仍为 **1/3**，本轮仍**无通信层结论**，仍**为阻塞**，S2/S3/S4/gate/headless/科研状态仍不变。
- 未在封存后写入源根；本节只改本轮 `report.md`（mutable 交接文件）。

### 更正 C3：`create_publisher` **确实**成功返回了（此前 §6 与封存 `analysis.md` §7 L3 的表述有误）

- 原表述："`create_publisher` 是否成功返回在本轮**无证据**：异常发生在调用之后的记录步骤，早于 `return ent`。"——**前半句错**。
- 依据（同一份 `report/a1-a-result.json.payload.trace`）：traceback 末帧为
  `line 189, in create_endpoint → rec.event('endpoint_created', ...)`，而 `create_publisher` 在 **line 179–180**，`t1 = time.monotonic_ns()` 在 **line 188**。Python 顺序执行，能到达 189 行即证明 **179–180 行已无异常返回**、188 行已执行。
- 正确表述：**`create_publisher` 已成功返回 `Publisher` 对象**；失败发生在其**之后**的 `rec.event(...)` 记录调用（`Recorder.event()` 首参名 `kind` 与字段 `kind=` 冲突）。即"**endpoint 创建成功但创建标记未能写出**"。
- 该更正**不改变**任何结论方向：
  - A 步仍为 **INVALID**（探针无有效记录、无 `endpoint_created` 事件、三阶段皆未跑）；
  - 仍**不能**据此声明 DDS 已发现/已匹配/可消费 —— 创建 API 返回本来就不等于发现就绪（派工单与探针注释均如此定义）；
  - B/C 仍未执行，T1 仍 1/3，本轮仍**无通信层结论**、仍**为阻塞**。
- 但它**确实**提高了"探针端到端可用"的置信度：a1 已证明 `rclpy.init()` 返回、`Node(...)` 返回、`create_publisher` 返回，仅剩**记录层**缺陷；修复该缺陷后，A 步的主要代码路径尚未跑通的部分是 sub 创建与三阶段观测。
- 封存源根 `report/analysis.md` §7 L3 同处不准确，按封存后只读规则**不修改**；以本节为准。
