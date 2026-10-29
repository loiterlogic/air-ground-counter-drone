<a id="paused"></a>
# 迁移暂停标记（Agent 开关）

- **迁移推进与论文优先暂停**：用户 2026-10-29 裁定；W8 任务链已按「已关闭（非验收）」归档，不再接单。
- 当前执行入口：[项目完成路线](README.md#plan-index)（P0 → P2）。
- [归档 Runbook](../archive/ROS2迁移步骤.md#top)、[契约](../ROS2迁移交接文档.md#hard-constraints)、[历史规格](../archive/specs/README.md#specs-index) 改为**按主题查，不预读**。
- 交接只看 [当前交接](../../.coordination/CURRENT.md#current)；一次循环一个任务。
- 恢复迁移时删除本文件并改回 CURRENT 指针即可，**不需要**恢复叫醒机制（[ADR-0102](../adr/0102-leader-worker-dual-model-handoff.md#decision)）。
- 本文件只作开关，**不承载**第二份进度状态表；进度见本目录各阶段文件的出口判据。
