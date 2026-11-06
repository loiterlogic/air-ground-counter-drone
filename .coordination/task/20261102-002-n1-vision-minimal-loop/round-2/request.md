<a id="request"></a>
# N1 · round-2 解除文件归属阻塞并继续批次

- 任务 ID：`20261102-002-n1-vision-minimal-loop`；轮次：2；Leader 派发时间：`2026-11-02T12:38:23+08:00`（Asia/Shanghai）。沿用 round-1 同一 Worker。
- 来源：Leader 独立读取 round-1 阻塞报告与 H0 归档证据后的裁定：[round-1 report](round-1/report.md#report)、[round-1 Leader review](round-1/review.md#review)。
- 原始目标、白名单其余部分、验收、协议与停止条件完整继承：[N1 round-1 request](round-1/request.md#request)。它未被本文件显式收窄/替换的内容仍有效。

## 阻塞解除与基线归属

round-1 Worker 正确按并行文件冲突规则停止。Leader 对照 H0 round-3/round-5 report 及 final review，确认四处未提交改动均为已验收 H0 实现，H0 Worker 已交回并归档，不存在活动文件拥有者。因此 Leader 裁定这些差异为本任务可读、可在必要范围最小增量的**已验收 H0 基线**：

- `src/agc_task/launch/w6.launch.py`：保留 H0 `build_manifest()` 输入与场景/CLI 参数合并行为。
- `src/agc_task/launch/w6_composition.py`：保留 `cruise_altitude_block()` / `observe_yaw_block()`、H0 startup assertion 与 manifest 字段/来源语义。
- `src/agc_task/config/scenarios.yaml`：保留 s02/s04 的 `cruise_alt_m: 2.0` 和 s04 场景级 `observe_yaw_mode: track`。
- `src/agc_task/config/w6_base.yaml`：保留 H0 `cruise_alt_m` / `alt_m` 语义及注释。

允许 round-2 在这四个文件中实施 N1 必需的最小视觉接线增量（仅属 round-1 白名单）；实施前先重读当前内容和 Leader 的裁定。不得复写或删除 H0 区域、回退语义、改写历史证据、整理无关 diff。report 须逐项列出与这四处 H0 基线的重叠和 diff，并证明上述行为/字段保持。除本裁定外，round-1 其余白名单与禁止项不变。

## 接单与资源状态

- 接单前读取本文件、round-1 request/report/review 和当前 CURRENT；核对 HEAD/branch/status 与运行资源。Leader review 不等于代码差异消失；发现新增写入者/新资源冲突时仍须按协议停止报告。
- 同一 Worker 在原 round-1 `report.md` 继续追加 `round-2 接单` 小节；勿改造/覆盖 round-1 阻塞事实。更新该 report 轮末状态为 `执行中`，待批次完成再写 `待审查` 或再次阻塞并通知 Leader。
- **资源额度沿用 round-1 起点，不重置**：墙钟自 `2026-11-02T12:28:41+08:00` 起，硬截止 `2026-11-02T16:28:41+08:00`；T1=0；T2 总授权 7,200 s，已用 0 s；静态预算累计 1,200 s。T2 只允许必要构建及工单指定 `full + GUI` 视觉验收，单次 ≤900 s。其它资源/独占与停止要求完整见 [round-1 resources](round-1/request.md#request)。
- 任务链、N1 技术目标与验收不变；仅当 Leader 后续明确裁定追加事项时才修改。真图像、CameraInfo、实际 optical frame 与图像同戳 `world←optical` TF 仍需运行证据；不能用真值替代。

## 交回

由同一 Worker 按 round-1 的单批次节奏完成或按停止条件交回。报告包含全部实施/测试/构建/full+GUI 数据流与资源账、失败与假设；报告置 `待审查` 时通知 Leader。不得修改 CURRENT、不得自行验收归档，不派 N2/N3、不轮询、不创建提醒。
