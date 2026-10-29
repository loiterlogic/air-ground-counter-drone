<a id="p0-1-round1-review"></a>
# P0-1 项目完成定义 · 第 1 轮审查

- 任务 ID：`20261029-001-p0-1-completion-definition`
- 轮次：`1`
- 审查日期：2026-10-29
- 审查者：Leader
- 结论：**已验收（仅 P0-1 书面完成定义，不表示项目闭环已完成）**

## 实际核查

1. 通读交付文档、Worker 报告与 CURRENT；核对白名单、预算和状态流转。
2. 抽样读取主场景登记、代表性 lightweight 成功 run 的 `scene_manifest.json` / `summary.json`；确认后端为 `lightweight`、静态障碍实际生效、终态为 `TRACKING_SUCCESS`、原因与 C9 字段齐全。
3. 对照 `world_bringup.launch.py` 核查 world basename 替换、`GZ_SIM_SYSTEM_PLUGIN_PATH` 前置和 GUI/headless 参数；对照 `task_manager.cpp` 核查 `started: AIR_SEARCH`、`tracking_milestone` 与悬停门；对照 `run_logger.cpp` 核查 SIGINT 后 finalize 的顺序。
4. 独立重算 manifest：当前 glob 命中 1020 个文件，其中 1019 个有效 JSON、1 个空文件；有效记录中 s04 共 10 条且全部 lightweight，s04×full=0，full×static=0。空文件为 `experiments/w6-task-eval/20261020-s08_static_none_nominal_capture-3-225257-1462/config/scene_manifest.json`，不是 s04，故不改变本任务结论。
5. 独立校验文档 41 条本地 Markdown 链接与锚点，错误数 0；复核交付 sha256 为 `fdfbfb68aad30fecfcff649331ca2a709fc5df6b6aa2e33d92acc02e398512ed`。
6. 基线 HEAD/分支与既有工作区修改保持一致；未执行构建、仿真、GUI、ROS 图或测试，未重置、清理、提交任何既有改动。

## 验收条件逐项

| 条件 | 结果 | 依据 |
|---|---|---|
| 主场景 ID、终态、启动命令、参数、时长口径 | PASS | 文档 `#p0-1-main-scenario`；full 墙钟上限明确待实测，未编造 |
| 6 段闭环可观察、可判 PASS/FAIL，三种成功不混淆 | PASS | `#p0-1-demo-loop`；结果落盘顺序已纠正 |
| 完成清单 ≥8 条且可命令化/静态判定 | PASS | D1–D10；当前 FAIL/未执行/部分 PASS 如实区分 |
| 已知缺口 ≥4 条且有现状与处置 | PASS | G1–G8；未承诺未验证能力 |
| 用户范围裁定已确认，契约与主场景决定未改 | PASS | 范围与已定决策节；s04 static 目标口径仅澄清，不换场景 |
| 报告、静态证据与未执行项完整 | PASS | 报告含差异、21 条检查、退出码、证据路径与零 T1/T2 声明 |

## 裁定与后续

- 接受本轮在既有文件内的结构重排；原 `#p0-1-goal` 保留且全部入链有效，无需返工。
- **P0-1 验收范围仅为“完成标准已建立”**。D1/D2/D5/D6/D7/D10 的 FAIL、D8 未执行及 full 主场景零实测均保留，不因本文验收而改判。
- 不在本任务追加 T2。`s04 × backend:=full × static` 的真实验证属于后续 P1-2/验收轮；按已批准路线，下一任务为 P0-2，不跳过基线固定。
- 结档日期：2026-10-29。未完成项去向：完成清单各责任阶段；主场景 full 实测归 P1-2 及后续验收。
