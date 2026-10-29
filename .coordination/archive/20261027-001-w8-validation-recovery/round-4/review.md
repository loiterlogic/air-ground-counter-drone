<a id="round4-review"></a>
# 第 4 轮独立审查

任务 ID：20261027-001-w8-validation-recovery；轮次：4；审查者：Codex。

尚未收到本轮回报，未验收。第 3 轮证据已验收；通信和四步任务链仍未完成。

## 本轮独立审查结论

审查日期：2026-10-27；审查者：Codex。回报已收到，以上占位结论由本节替代。

### 核查依据

- 读取本轮 [派工](request.md#round4)、[回报](report.md#round4-report)、`CURRENT.md`、交接协议、[第 3 轮审查](../round-3/review.md#round3-review) 及 round-4 规格；本审查未构建、未启动 ROS/GZ/PX4、未启动仿真或 GUI。
- 独立执行只读证据核对：读取四份 `report/attempt-*-result.json`，逐行解析四份 `log/attempt-*-events.jsonl`，按进程启动 monotonic 时钟重算 matched/graph/heard 峰值和 matched 事件；结果为 C1 pub matched 峰值 1、sub matched 恒 0，D1 sub matched 峰值 1、pub matched 恒 0，四端 `heard_n=0`。
- 独立核对 `log/10-attempt-c1.log` 与 `log/11-attempt-d1.log`：C1/D1 墙钟分别 8.657 s/8.457 s，四个进程退出码均为 0，PID/PGID 均回收，`RESIDUE=0`；两次总计 17.114 s，满足单次 30 s、总计 90 s 和最多 2 进程的 T1 边界。
- 独立核对固定条件与命令参数：两次均使用 domain 39、LOCALHOST、RELIABLE depth10、`/agc_probe_order/chatter`，只读复用 round-3 探针；未见配置、源码或探针复制改动。
- 独立复算 `config/evidence_manifest.json`：15 个源 artifact 的 size/SHA 全部匹配；归档命令日志 `/tmp/agc-w8-r4-archive.log` 记录 `artifacts=15 verify=True files=16 mismatches=0`。tar SHA `d3078b09a1b478acaa65ea570c093f4c935d2102d080eef73cb499b590806ba9` 与 checksum/retrieval sidecar 一致，retrieval 为 `verified=true`、16 files、0 mismatch，源根与 tar 逐文件相等。
- 独立重算派工基线 1157 条受保护路径：当前唯一变化是 `.coordination/wake/targets.json`，其余路径无 missing/changed；该变化已在回报中披露，且当前文件实际为 `codex_thread_id=01a17da4...`、`codex_thread_id_previous=01a17da0...`。

### 验收结果

| 条件 | 结果 |
|---|---|
| 任务 ID/轮次、领取基线、HEAD/branch 与预算 | 通过；HEAD/branch 与派工一致，领取到交接 212.243 s，未超 45 min；T1 2/2 在授权内 |
| pub-first 与 sub-first 双端原始证据 | 通过；四端结果、事件流、启动时间、退出码和残留可相互核对 |
| 顺序判读 | 通过；先启动端在 C1/D1 分别为 pub/sub，后启动端对先启动端 graph 恒 0；两次均零消费。该结果支持启动顺序相关的方向性发现失败，不定位 SHM/UDP/权限/QoS 根因 |
| 范围与停止条件 | 通过；未重做 A、未重跑有效 attempt、未扩展诊断，未构建/抓包/仿真/读取 `/dev/shm`/清理共享资源 |
| 证据封存与取回 | 通过；manifest、tar、checksum、retrieval 均无 mismatch，封存输出在源根外 |
| 交接边界 | 通过；DSH 未把结果宣称为通信恢复、S2 通过或整链完成；叫醒回执 `20261027T215819.codex.json` 为存活会话投递且未绕过守卫 |

### 记录质量问题

回报 §10 D1 首段把 targets 变更写成 `01a17d22... -> 01a17da0...`，而同一回报的封存后追加段和实际 `targets.json` 显示为 `01a17da0... -> 01a17da4...`。这是协调配置历史的文字矛盾，不是实验原始证据矛盾；本审查以实际文件和追加段为准，并要求后续结档或派工引用 `01a17da4...` 当前值，不能复述首段错误值。

## 结论

**第 4 轮启动顺序诊断证据通过。** C1/D1 的顺序翻转和零 `heard` 已由原始事件流独立复算，满足本轮派工的诊断验收口径。本轮不证明通信恢复、不开放 S2/S3/S4、不改变 `gate`、headless 授权或科研结论。

四步任务规格明确要求四步完成或 Codex 明确关闭后才能归档整链；当前真实通信仍未恢复，S1 根因和可用配置尚未确定，且没有新的已写返工派工。因此本任务链**不归档，CURRENT 置为 `阻塞`**，保留第 4 轮原始三件套；后续若继续，须由 Codex 在同一任务 ID 内另写可判定派工后再改为 `待返工`/`待执行`，本轮审查后不自动叫醒 DSH。
