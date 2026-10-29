<a id="round1-report"></a>
# W8 验证恢复 · 第 1 轮回报（S1 官方通信 ABBA）

- 任务 ID：`20261027-001-w8-validation-recovery`；轮次：1；执行者：DSH（`session-877ee7b5-5e46-45cb-8f85-fec554b77279`）。
- 起止：领取 2026-10-27T18:58:09+08:00（epoch_ns `1793098689528413204` / monotonic_ns `36975102161592`）→ 交接 19:05:26+08:00（monotonic_ns `37376021000340`）。整轮 **400.9 s**，未超 45 min。
- 来源：DSH 实施与回报；Codex 派工与裁定；用户授权目标。验收结论归 Codex，本报告不自行判定通过。

<a id="claim"></a>
## 1. 接单基线与领取核对

| 项 | 实际值 | 结论 |
|---|---|---|
| 任务 ID / 轮次 | `20261027-001-w8-validation-recovery` / 1 | 与 CURRENT、request 一致 |
| 接单状态 | `待执行` | 允许接单 |
| HEAD / 分支 | `d5072aaff33276bcd1c5e7d38b5caa75fe45a290` / `main` | 与派工一致 |
| 基线回执 SHA | `55f394922867d0ae2506a6ef7c632eac4af7cad18fd45fe56d44c8919f90552e` | 与 `baseline_receipt.json` 相符 |
| 基线文件数 | 1052；相符 1048、缺失 0、变化 4 | 见下 |
| 冻结入口/核心 | adapter `91c6b79…`、runner `c3f7d1a…`、test `5c71516…` | 与已验收版本一致 |
| 已有 dirty/untracked | `git status --porcelain` 36 项 | 原样保留，未重置/清理/提交 |

4 项相对旧基线的变化，全部属于本单明确允许的范围，无未知漂移：

1. `.coordination/README.md` → `605f0a47637d0dc5339661fd9296359b5907ecf91227d07af0b1abeb02264b81`（派工补充列明的新 SHA，相符）
2. `.coordination/scripts/coordination_wake.py` → `20be648c5d104ba08be9c108d39116eeb7000d0dac059e0cd2eca703af50120f`（同上，相符）
3. `.coordination/scripts/tests/test_coordination_wake.py` → `be265d499e4ecbcfd34e58bbb263c0a0525fcbd501fb4388c553e9b3db4980b0`（同上，相符）
4. `.coordination/task/20261027-001-w8-validation-recovery/round-1/request.md` → `054505da325cd10a8ca1f9e4740e23cbaa24ad209176a339b28f59870b2129ac`（本 request 自身追加「Codex 基线补充」段，属本单自身变化）

新文件 `.coordination/scripts/start_dsh_web.py` SHA256 `ea0f750a28f6b9a7f8c8f093f956d7df5b6f2fa7336090e762f4403d31018877`，与派工补充相符。

官方来源四份快照 SHA 复算相符：listener-0.33.11.cpp `16ca850…`、fastdds-2.14.7-env.html `23f5b0c…`、fastdds-2.14.7-shm.html `79d58f7…`、jazzy-discovery.html `7f5b116…`。

<a id="preflight"></a>
## 2. 预检（只读）

- 相关活动进程：`demo_nodes_cpp` / `_ros2_daemon` / `fastrtps` 均无。
- 域 39 UDP 端口（17150–17399）：无占用。
- `FASTRTPS_DEFAULT_PROFILES_FILE` / `FASTDDS_DEFAULT_PROFILES_FILE`：均未设；CWD 无 `DEFAULT_FASTRTPS_PROFILES.xml`、`fastdds.xml`。
- 两个独占临时目录 `/tmp/agc-p3-r16-w8transport-20261027-r1-work`、`-ros-home`：运行前不存在。
- 证据根 `experiments/w8-validation/20261027-transport-abba-r1/` 的 `config/codex_dispatch_baseline.json`、`baseline_receipt.json`、`config/sources/previous_current.md` 只读未改。

<a id="run"></a>
## 3. 一次正式运行

唯一一次授权 CLI（未重试、未换 ID）：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -B experiments/ros2-diagnostics/20261027-p3-r16/scripts/runtime_adapter.py \
  --authorize-ros-run \
  --out-root /home/chen/AGC/experiments/w8-validation/20261027-transport-abba-r1/runtime \
  --attempt-id w8transport-20261027-r1
```

- 起 `epoch_ns 1793098707698208347` / `mono 36990344867166`；止 `epoch_ns 1793098759310020389` / `mono 37039024093105`；**exit_code=0**，耗时 51.6 s。
- batch：`plan=A1,B1,B2,A2`、`stopped_early=false`、`errors.budget/invalid/persist` 全空、`exit_code=0`、墙钟总时长 48.618 s。
- 4 cases / 8 真实端点启动 / 0 retry。

<a id="results"></a>
## 4. 逐例结果

| 例 | 变体 | `FASTDDS_BUILTIN_TRANSPORTS` | 发布唯一编号 | 接收唯一编号 | 分类 | invalid | 残留 |
|---|---|---|---:|---:|---|---|---|
| A1 | A | 未设（null） | 9 | 0 | failure | 无 | 无 |
| B1 | B | `UDPv4`（两端） | 9 | 0 | failure | 无 | 无 |
| B2 | B | `UDPv4`（两端） | 9 | 0 | failure | 无 | 无 |
| A2 | A | 未设（null） | 9 | 0 | failure | 无 | 无 |

四例均 `status=failure`、`receipt_verified=true`、`unreleased=[]`、`invalid_reasons=[]`。listener 日志仅 1 行 SIGTERM 终止记录（71 B），talker 10 行（9 条 `Publishing` + 终止行）；console 与 `ros_log/` 按角色去重后内容一致，`topic_source=command_remap`，两端 namespace/topic 匹配。

**分类口径结果：全失败。** 只支持「仅 UDPv4 在本轮设置与时序下未显示改善」；不支持排除 SHM 问题、不指认 discovery/QoS 根因、不估计长期可靠率、不与历史样本合并。

<a id="identity"></a>
## 5. 端点身份、环境、库与回收

| 例 | listener pid/pgid/starttime | talker pid/pgid/starttime | 回收 |
|---|---|---|---|
| A1 | 281036 / 281036 / 3699040 | 281058 / 281058 / 3699240 | rc=0，无信号，组无残留 |
| B1 | 281091 / 281091 / 3700255 | 281112 / 281112 / 3700454 | rc=0，无信号，组无残留 |
| B2 | 281135 / 281135 / 3701470 | 281156 / 281156 / 3701669 | rc=0，无信号，组无残留 |
| A2 | 281194 / 281194 / 3702685 | 281215 / 281215 / 3702885 | rc=0，无信号，组无残留 |

- 八端点 UID 1000；namespace inode 一致（net `4026531840`、ipc `4026532210`、mnt `4026532221`、user `4026531837`）；cwd 均为私有 work 目录；`env_source=exec_observable`。
- 最终环境：`ROS_DOMAIN_ID=39`、`ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST`、`RMW_IMPLEMENTATION`/`LD_PRELOAD`/profiles 均空；A 例 `FASTDDS_BUILTIN_TRANSPORTS=null`、B 例两端 `UDPv4`。
- 二进制 pin 来源 `r4_dispatch_pin`：listener `f9c3d9c…`、talker `63c40ad…`，与 maps 实际映射一致、无 deleted 段；未从观察值生成 expected。
- canonical 库：`libfastrtps.so.2.14.7` maps `2b80489…`（与磁盘一致）、`librmw_fastrtps_cpp.so` `7b59ab0…`。
- 运行后复查：无 demo/daemon 残留进程，域端口无占用；两个独占临时目录保留（内容为空），未删除、未清场。

<a id="clock"></a>
## 6. 时钟与预算算术（mono/epoch 分列）

- 每例 8 组成对样本，顺序 `monotonic_ns_before → wall_ns → monotonic_ns_after`，`pair_gap_ns` 689–4913 ns。
- **B1 第 3 组**：`wall_minus_mono_ns` 相对前组跳变 +2932585358 ns（约 +2.93 s），同一时刻 talker 日志 `Publishing 3 → 4` 出现 3.93 s 空档；monotonic 连续。仅登记为环境观察，**不用于修补预算或归因通信**。
- 运行期：batch `start_mono_ns 36990384136482` → 预算截止 `37590384136482`（600 s）；实际 48.618 s。每例 `t0 → case_deadline` 恰 20 s，stop 于 t0+12.01–12.02 s，cleanup 于 t0+12.14 s，均未超期。
- 例间：前例 cleanup → 后例 t0 为 0.0099 / 0.0111 / 0.0104 s（串行，无固定 2 s 等待，符合本单接受口径）。
- 整轮：领取 → 交接 `(37376021000340 − 36975102161592)/1e9 = 400.92 s`。
- 交接结束配对时钟（封存外，见 §9）：`mono_before 37376021000340` → `wall 1793099126851400210` → `mono_after 37376021002507`，`pair_gap_ns 2167`。

<a id="evidence"></a>
## 7. 证据路径

- 本轮证据根：`experiments/w8-validation/20261027-transport-abba-r1/`
  - `log/00-preflight-claim.log`（领取/基线/预检原始命令与输出）
  - `log/10-formal-cli.log`（正式 CLI 命令、起止时钟、exit code）
  - `log/20-postrun.log`（运行后残留/端口/目录/逐文件 SHA 清单）
  - `log/baseline_before_archive.json`（封存前基线复算）
  - `log/verification_end_clock.json`（报告定稿前唯一验证结束配对时钟）
  - `log/30-archive.log`（归档命令输出，见 §9 说明）
  - `report/transport_result.md`（源报告）、`report/transport_result.json`（结构化逐例数据）
  - `runtime/w8transport-20261027-r1/`（4 例 case.json、case_receipt.json、events.jsonl、双端 console/ROS 日志、双端 snapshot、batch.json、batch_receipt.json）
  - `config/evidence_manifest.json`（50 artifacts）
- 封存：`experiments/_archive/w8-validation/20261027-transport-abba-r1.tar`（51 条目，SHA256 `e170346a79c7ad3e5e35f03353c69b8d014194673ebdc95185bd210511f719c8`）+ `.tar.sha256` + `.tar.retrieval.json`（`verified=true`、`files_checked=51`、`mismatches=[]`）。

<a id="notexecuted"></a>
## 8. 未执行项与偏离

- **未执行**：S2 / S3 / S4；工程节点与构建、GZ/PX4、GUI/headless、节点合成测试、科研实验（均 0 attempts）；R16 的 152 项既有测试（本轮无代码变化，按派工不重跑）；`reference/` 未读；`/dev/shm` 未扫描未删除；未终止任何他人进程；未改域、daemon、网络、隔离、时钟、库或系统配置；未 git commit/push/merge/reset/clean/切分支。
- **偏离**：无预算、白名单或流程偏离。B1 墙钟跳变见 §6，属观察事实。
- **限制**：本轮不区分「发布失败」与「数据通路失败」（无端点匹配层直接观测）；全失败不等于根因已定位；不自动恢复工程验证。

<a id="seal-note"></a>
## 9. 封存自引用说明（如实登记）

`evidence_archive.py` 在构建 manifest 时遍历证据根，`log/30-archive.log` 已由 `tee` 创建为空文件，因此 manifest 记录该文件 `size=0`、`sha256=e3b0c44…`（空文件哈希）；随后归档命令输出写入同一文件，live 现为 144 B、`sha256=e8303e3…`。

- 已核对：封存件内该文件为空（0 B），live 以封存内容为前缀（`live.startswith(sealed)` 为真），**无覆盖、无删除**；封存后 live 增量仅此一处，证据根内其余 49 个 artifact 与 manifest 逐一相符，无封存外新增文件。
- 处置：不重建归档（未使用 `--force`），不改封存件；本说明与 §6 交接时钟写在本报告与封存外记录中，符合「封存后纠错只追加交接 report 或新侧车」的派工要求。
- 封存外交接记录：`/tmp/agc-w8-validation-r1-handoff/handoff.json`（baseline_handoff 复算、归档 SHA/条目数、上述自引用说明、完整交接结束配对时钟）。该路径属本单允许的 `/tmp/agc-w8-validation-r1-*`。

<a id="status"></a>
## 10. 状态与叫醒

- 本轮按派工完成取证（四例有效且如实分类为 failure），CURRENT 置 `待审查`；本报告不自行验收。
- 已叫醒 Codex，回执：见文末追加行。

- 已叫醒 Codex，回执 `.coordination/wake/20261027T190716.codex.json`（链 753672afe16e 第 3/4 跳，queue-live-thread 投递至 Codex 会话 01a17cd2…，returncode=0）。
