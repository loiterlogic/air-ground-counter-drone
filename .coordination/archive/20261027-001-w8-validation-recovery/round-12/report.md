<a id="round12-report"></a>
# 第12轮执行回报

任务 ID：20261027-001-w8-validation-recovery；轮次12。

执行者：Worker（DSH 子会话 `55d8793e-4916-4045-ac19-5800e167ebfa`，父会话 `session-7bfaaed2-f329-4569-8dae-f795ccdba988`）。复用同一子会话，未新建 Worker。

## 0. 领取配对时钟（本轮第一个动作，先于任何读取/执行）

来源：Worker。在本轮任何文件读取、命令执行之前采样，直接写入本 mutable report。

| 字段 | 值 |
|---|---|
| `claim_mono_before_ns` | `19651591844637` |
| `claim_wall_ns` | `1793166385747353989` |
| `claim_mono_after_ns` | `19651591845827` |
| `claim_pair_gap_ns` | `1190` |

采样方式：`mono_before → wall → mono_after` 三连读（同一进程内），`pair_gap_ns` 是该配对的自噪声上界。

**口径声明**：本表是本轮**唯一**领取时钟依据；**不用文件 mtime 反推**，不把估计值写成实测。预算判定使用**同机 monotonic**；wall/mono 偏移漂移如实报告，不假设原因、不改系统时钟。

## 1. 接单与基线

| 项 | 值 | 结果 |
|---|---|---|
| CURRENT 领取前 | 任务 `20261027-001-w8-validation-recovery`、轮次 `12`、状态 `待返工` | 协议允许接单 |
| HEAD / 分支 | `d5072aaff33276bcd1c5e7d38b5caa75fe45a290` / `main` | 与派工一致 |
| 基线 SHA | `3bc432ad74284dd8f3516bcd1584e2fdf4317b80ee4580ee1a696cf0be529d43` | 与 receipt 一致 |
| 逐项复算 | **1562/1562 相符**，missing 0、changed 0（领取时 + 封存前各一次） | 通过 |
| `git status --porcelain` | 与 baseline `status` 逐行相同 | 通过 |

未 reset/clean/commit/push/切分支；既有 dirty/untracked 全保留。

## 2. 定点修复（只改 `run_attempt_driver.py`，其余原样吸收）

### R12-F1：缺失/非法 expected starttime 一律拒绝信号

第11轮的 `send_signal` 只在 `starttime is not None` 时才比对，因此"预期身份缺失"仍会发信号——这正是审查 mock 复现的那条路径。现在：

```python
if not isinstance(starttime, int) or isinstance(starttime, bool) or starttime <= 0:
    return 'expected_starttime_missing_or_invalid:not_signalled:%d%s' % (pid, note)
```

- **不能用 `read_stat` 当前观察值替代启动时身份**（那正是盲发来源）；`read_stat is None` 与 `starttime` 变化仍分别拒绝。
- `reclaim()` 的**成员清扫**同样被守卫：预期身份缺失时 `group_sweep_skipped_no_identity=true`，完全不进入 `group_members` 循环。
- 成员清扫本身仍是 `pgrp` 匹配 + `starttime >= leader_starttime` 的已披露启发式，本轮不扩大工程。

### R12-F2：helper 启动身份 + 统一有界回收 + 最终核对

- 新增可测原语 `run_helper_bounded(...)`：启动即 `snapshot()` 捕获自有 `PID/PGID/starttime` 与配对时钟；捕获失败 → `identity_capture_ok=false` 且 `reclaim` 因预期身份缺失**零信号**。
- 超时与正常退出**都**保留：真实 `returncode`、`group_alive_after`、完整 `actions`、`stdout/stderr`、`reclaim_complete`。
- 回收记录**不再丢弃**：超时记录同时进 `verdict.reclaim[]` 与 `verdict.helper.reclaim`；`hp` 进入 `procs['helper']`，由 `finish_attempt()` 统一核对。
- 最终核对新增：`helper_identity_capture_failed`、`helper_reclaim_incomplete:no_rc`、`helper_group_alive_after`、`helper_still_alive` 四类 invalid；`verdict.helper.final` 固化 `reclaim_rc` / `group_alive_after` / `still_alive_at_final` / `counted_as_ros_participant=false`。
- **helper 不计为 ROS participant**：它只是本地 `python3` 假脚本，不 import rclpy。

## 3. 回归（全部在最终代码上重跑）

| 套件 | 结果 | 说明 |
|---|---|---|
| `test_driver_offline.py`（第11轮全套） | **20/20** | 正常/异常/超时/门控/预算/残留/拒绝授权 |
| `test_helper_paths_offline.py`（本轮新增） | **6/6** | 真实 helper 假进程 |
| `test_signal_identity_offline.py` | **14/14** | 含 6 种非法 expected starttime |
| `test_validate_side_offline.py` | **16/16** | 完成侧证据反例 |
| `test_probe_offline.py` | **11/11** | stub rclpy |

### 3.1 真实 helper 假进程 6 例

| 用例 | helper 行为 | driver rc | 关键断言 |
|---|---|---:|---|
| `helper_fast` | 立即 exit 0 | 0 | 身份三项齐全、`natural_exit_rc=0`、非 participant |
| `helper_hang` | sleep 30 s | 4 | 超时回收 `returncode` 非 None、`group_alive_after=false`、**记录进 `reclaim[]`**、第二方未启动 |
| `helper_fail` | exit 7 | 4 | `natural_exit_rc=7` 被记录 |
| `helper_selfkill` | 自报 /proc 身份后 sleep | 4 | **驱动捕获的 pid/starttime/pgid 与 helper 自报一致**（证明字段真来自 /proc） |
| `helper_tiny_timeout` | 0.05 s 超时 | 4 | 走"预算不足→跳过 helper"合法分支、有界、第二方未启动 |
| `helper_identity_capture_failed` | **mock** | 0 | `identity_capture_ok=false` 时**零 kill / 零 killpg**，`reclaim.returncode=None` 被如实记录 |

### 3.2 信号身份 14 例（含审查 mock 复现）

`expected_starttime` 取 `None`、`0`、`-1`、`'abc'`、`3.5`、`True` 六种非法值，在 `read_stat` **成功返回**的情况下**全部零 kill**；另加 `current_stat_not_used_as_expected_identity` 与 `reclaim_missing_identity_skips_sweep`。全程 `os.kill`/`os.killpg` 被 mock 拦截，**零真实信号**。

## 4. 过程失败与修复（唯一编号，不覆盖）

| 编号 | 问题 | 性质 | 修复 |
|---|---|---|---|
| `it-01` | 失败汇总取 `c['case']` 而元素只有 `c['check']` → `KeyError` | 测试代码错误 | 改为 `c['check']` |
| `it-02` | `helper_tiny_timeout` 断言写死 `helper.reclaim` 必存在 | 断言过窄（该例走合法"跳过 helper"分支） | 接受 two-of 合法形态 + 补第二方未启动断言 |
| `it-03` | mock 用例 `root=None` 时 `os.path.join` 报错 | 测试代码错误 | `case_dir` 计算加判空 |
| `it-04` | `test_driver_offline.py` 的 `ROOT` 仍是第11轮 `/tmp/agc-w8-validation-r11-tests` | 吸收未改常量，产物落到错误前缀 | 改为 `/tmp/agc-w8-validation-r12-tests`，**代码变更后重跑全部五套**并校验 `CODE_UNCHANGED` |

证据：`evidence/iterations/iterations.json`。it-01/02/03 的 `/tmp` 中间产物已被同名重跑覆盖，故仅保留结构化描述，**不冒充原始文件**；it-04 是常量缺陷，修复前后差集即证据。

## 5. 明确未做与限制

- **未执行**真实 A/B/C：T1=0；生产默认入口对真实探针仍 exit 2（`refuse_real`/`refuse_grant` 覆盖）。**未**用 `--allow-real-ros`。
- 未构建、未仿真、未抓包、未读 `/dev/shm`、无共享资源操作、未改系统配置。
- **限制 L1**：注入时限（budget 5 s、term/kill/sweep 各 0.3 s、helper 0.6–2 s）远短于生产默认（26/1/1/1/5 s），只证逻辑有界。
- **限制 L2**：`group_members` 的 `starttime >= leader_starttime` 仍是单调刻度启发式，未读 `/proc/*/task/*/children`；按审查裁定**不**扩大为谱系证明。
- **限制 L3**：假探针不 import rclpy，rclpy 事件顺序/回调时机未验证。
- **限制 L4**：helper 身份捕获失败用例用 mock 制造（真实"进程启动后立刻消失"难以稳定复现），因此该路径的零信号结论是 **mock 级**证据。
- **限制 L5**：`helper_tiny_timeout` 与 `b_helper_budget` 走的是"预算不足跳过/超时"分支，与"身份已捕获但回收失败"不是同一路径；后者由 mock 用例覆盖。

## 6. 封存与取回实测值

首次封存，**未** `--force`；stdout 写 `/tmp/agc-w8-validation-r12-archive/archive.log`。

```
ok     w8-validation/20261028-endpoint-helper-offline-r1 artifacts=274 verify=True files=275 mismatches=0
archived=1 skipped=0 error=0 retrieval_failed=0
```

| 核对项 | 实测值 | 结果 |
|---|---|---|
| manifest artifacts | **274** | 逐个 size/SHA 复算，**0 mismatch** |
| tar 真实根 | `20261028-endpoint-helper-offline-r1/`（唯一） | 正确 |
| tar 成员数 | **275**（274 源文件 + manifest 自引用） | 差集为空 |
| `root_only` / `tar_only` | `[]` / `['config/evidence_manifest.json']` | 符合脚本设计 |
| tar SHA256 | `785a424c651cd6cfac0261e22adf9d2f464395e22f3d35e786cabcf5507f2139` | 与 checksum 一致 |
| retrieval | `verified=true`、`files_checked=275`、`mismatches=0` | 通过 |
| tar vs 源根逐文件 | **0 处不一致** | 通过 |
| 封存后源根写入 | **无** | 合规 |

- 回归原件全在封存内：`cases/driver/`（20 例）+ `cases/helper/`（5 例真实目录 + 1 例 mock 无目录）、`evidence/final/`（5 份套件输出）、`evidence/iterations/`。
- `refuse_real`/`refuse_grant` 目录含 `refuse.json` 与 `ABSENT.json`（显式声明 `command.json`/`drive.json`/`probe/*` **未产生**，不以空文件冒充）。

## 7. 判读与状态

- 本轮只闭合 helper 自有身份与回收证据、缺失预期身份拒绝信号；**不**证明通信行为、不定位根因、不代表 S2/S3/S4 进度、不改 `gate`/headless/科研结论。
- T1 实际 **0/0**；真实 A/B/C 仍未授权。
- CURRENT 置 **待审查**，已 `send_message` 通知父 Leader，不轮询、不接下一单。

## 8. 结束配对时钟

| 字段 | 值 |
|---|---|
| `end_mono_before_ns` | `19895326452564` |
| `end_wall_ns` | `1793166635112230345` |
| `end_mono_after_ns` | `19895326453407` |
| `end_pair_gap_ns` | `843` |

| 口径 | 值 |
|---|---|
| **整轮 mono** | **243.735 s ≈ 4.06 min**（≪ 45 min） |
| wall | 249.365 s |
| 该窗口偏移漂移 | +5.630 s（如实报告，不假设原因） |

## 9. 追加说明（封存后自查，不改状态）

封存后复核本报告的 SHA 引用时确认一处**表述口径**需要澄清（非事实错误）：

- §1 表中的 `3bc432ad74284dd8f3516bcd1584e2fdf4317b80ee4580ee1a696cf0be529d43` 是**本轮派工基线文件** `config/codex_dispatch_baseline.json` 的 SHA（Leader 预置、只读），可在该文件与其 `baseline_receipt.json` 中直接复核；它不出现在 `config/sources.json`（后者只记**代码吸收来源**），故用"是否出现在 sources.json"检索会误判为缺失。
- §6 的 tar SHA `785a424c651cd6cfac0261e22adf9d2f464395e22f3d35e786cabcf5507f2139` 与 `.tar.sha256`、`.retrieval.json.archive_sha256` 三者一致，已独立复核。
- 其余被引用的脚本 SHA 均可在 `config/sources.json` 或封存 `scripts/` 实测复核。
- 本条只补口径，不改任何结论、不改封存源、不改验收状态。
