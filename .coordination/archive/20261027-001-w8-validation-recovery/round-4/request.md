<a id="round4"></a>
# W8 验证恢复 · 第 4 轮：启动顺序对照

- 任务 ID：20261027-001-w8-validation-recovery；轮次：4；日期：2026-10-27。
- 来源：Codex 根据第 3 轮独立审查派发；同一任务链继续。第 3 轮证据已验收，但 B 的单向 matched 形态需用启动顺序控制区分时序与结构性不对称。
- 依据：[交接协议](../../../README.md#protocol)、[观测分级](../../../README.md#run-tiers)、[第3轮审查](../round-3/review.md#round3-review)、[第3轮分析](../../../../experiments/w8-validation/20261027-layered-matched-probe-r1/report/analysis.md#round3-analysis)。

## 目标与固定条件

复用已验收的 `experiments/w8-validation/20261027-layered-matched-probe-r1/scripts/probe_layered.py`，只改变跨进程启动顺序，观察单向 matched/graph/heard 是否随顺序翻转。A 控制不重做；不改 ROS discovery、transport、topic、QoS、binary pin 或系统配置。

固定：`ROS_DOMAIN_ID=39`、`ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST`、不设 `FASTDDS_BUILTIN_TRANSPORTS`/`RMW_IMPLEMENTATION`/`LD_PRELOAD`/profiles；topic `/agc_probe_order/chatter`、RELIABLE depth10；普通用户。

## 预授权与两次 T1

本单显式预授权 **T1: 2 次**，每次 ≤30 s、累计 ≤90 s、最多2个进程、独占 `/tmp/agc-w8-validation-r4-*`；不读 `/dev/shm`、不清理共享资源、不改系统/网络/库/时钟配置、不构建、不抓包、不启 GZ/PX4/GUI/headless/全链。两次均为有效顺序对照；进程异常才可按协议重试，不能把有效零消费当失败重跑。

1. **C pub-first（attempt-1）**：先启动 pub，约 1.0 s 后启动 sub；让 pub 运行至少覆盖 sub 的完整 6 s 窗口（建议 pub 8 s、sub 6 s）。记录两端 matched/graph/heard 事件及启动时间。
2. **D sub-first（attempt-2）**：先启动 sub，约 1.0 s 后启动 pub；让 sub 运行至少覆盖 pub 的完整 6 s 窗口（建议 sub 8 s、pub 6 s）。记录同样字段。

两次都必须有双端结果；任一 API 异常、关键快照缺失、超时或残留为 invalid，停止并保留现场。不要用第三轮 B1 结果替代本轮任何一侧。

## 判读

- **顺序翻转**：C pub 侧 matched/heard 正常而 D sub 侧 matched/heard 正常，或不对称侧随先启动者改变，支持启动时序/发现握手假说；仍不能定位底层权限或 transport 根因。
- **同一侧持续不对称**：无论 pub-first/sub-first，固定同一方向 matched 而另一侧为0，支持结构性发现/匹配不对称；仍需后续根因取证。
- **双侧 matched>0 且 heard>0**：该探针配置下跨进程通信成立；只能回查第一轮入口时序/配置差异，不能宣称工程恢复。
- **双侧 matched=0** 或结果不一致：记录为新的受限观测；不强行映射为发现、QoS 或 SHM 根因。

## 产物、基线与封存

新产物根：`experiments/w8-validation/20261027-layered-matched-probe-r2/`，只允许新增 `config/`、`log/`、`report/`，复用的探针脚本只读，不复制修改。记录 PID/PGID/starttime、命令、环境、退出码、残留、结果/事件 SHA 与配对 wall/monotonic 时钟。生成 `config/evidence_manifest.json` 后首次封存使用现有 `scripts/evidence_archive.py`，禁止 `--force`；归档输出放源根外，封存后只写本轮 report 或 `_archive` 同级侧车/`/tmp`。

领取时核对新根 `config/codex_dispatch_baseline.json` 和 `baseline_receipt.json`（HEAD/branch、size/SHA、mutable CURRENT/report/review）；未知漂移停止。整轮 45 min monotonic，含两次 T1、报告、首次封存和取回核验。完成后置待审查并按协议叫醒；当前叫醒链已达 4/4，若守卫拒绝必须记录退出码4，不重置、不换任务ID、不自行重试。

本轮只验收通信诊断证据，不开放 S2/S3/S4，不改变 gate、headless 授权或科研结论。
