# P2-1 · round-10 最终审查（克隆复验里程碑）

<a id="p2-1-r10-review"></a>

- 被审：[round-10 report](report.md#p2-1-r10-report)
- 审查人：Leader（DSH） · 2026-10-31
- 裁定：**克隆复验通过；P2-1 为 9/10 项达成，暂不整体验收归档，唯一剩余项为用户自录完整演示视频**

## 我亲自核查

1. **原始证据**：`experiments/p2-1/round-10/verify-evidence.txt` 记录 `experiments_root=/tmp/agc-r10-clone/experiments`，fingerprint、`git_head.txt` 与克隆 HEAD 三方一致为 `61374f7749ff…`；`terminal_explanation.txt` 正常给出阈值、终态和克隆侧 summary 数据源。
2. **真实运行**：`demo.log` 到 `TRACKING_SUCCESS / tracking_milestone`，回收 36 进程、剩余 0；不是仅静态检查。
3. **主仓零新增**：报告的前后清单为 demo 51→51、eval 1102→1102。Leader 事后看到 demo 为 52，其原因是 Worker 取证后把本轮 `demo.log` 复制进主仓证据区，**不是克隆运行写回主仓**；eval 仍为 1102。该新增已定位，不否定零新增结论。
4. **提交与回归**：`6ba3f31` 仅 4 个交接文件，无禁发路径；Leader 自跑 `./run_demo.sh test` → **5/5 组、24.36 s 全绿**。
5. **偏离边界成立**：借用主仓 toolchain 只证明任意路径下写盘根和 Git 身份正确，不证明全新机器完整部署耗时。Worker 指出派工中的 `code_root` 字段名不存在，并采用更直接的 HEAD 三方比对，予以接受。

## 收尾修正（Leader）

代码复验通过后发现 README 仍写“只能在 `/home/chen/AGC` 下使用”，P2-1 仍把“脚本路径不可移植”列为现状，均与实测矛盾。已仅修改文档：

- README 改为交付入口、评测产物与 Git 身份支持任意路径克隆，并保留 toolchain 与研究/历史脚本边界；
- P2-1 第 7 项证据升级为 round-10 完整闭环；已知边界第 7 条改写为验证范围，而非未修复缺陷。

不再改代码、不再追加 T2。

## 剩余事项

- **完整演示视频**：用户自录，文件路径待提供。第 3 项判据继续不勾，不得用 GIF 或 PNG 冒充。
- 视频到位后，在本任务新增一轮做文档接入与最终验收，再按交接规则归档；当前不开始新任务。