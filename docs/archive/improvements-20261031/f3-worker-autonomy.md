<a id="goal"></a>
# F3 · 协作规则优化

来源：用户 2026-10-31 新增要求；[批次入口](README.md#plan-index)。

先读全协作规则和角色文件、ADR-0104 与近期因预算停工的报告，列出矛盾。把预授权从机械次数转为任务目标、资源、总时间和无进展熔断；有证据的明确根因可在同范围完成修复+验证，不因记录轮数停工。保持契约红线、文件边界、仿真独占、总资源上限、失败留痕和独立验收。支持用户授权的独立任务并行，CURRENT 由 Leader 统一维护。

<a id="scope"></a>
## 实施边界

仅 .coordination/README.md、.coordination/roles/leader.md、.coordination/roles/worker.md。本单不动 CURRENT、AGENTS、ADR、计划索引。若需要 ADR，报告中给出草稿建议由 Leader 裁定。

<a id="exit"></a>
## 出口判据

协议与两角色文件一致，无 T1 单轮三次/有效失败即交回/次数预算耗尽必停等互相冲突；用已知根因修复、未知根因空转、总时间耗尽、文件越界、并行资源冲突五种案例走查新规则；明确授权依据与不追溯历史豁免。

验收结果：**已验收**（Leader，2026-10-31）。两轮修订完成协议与角色规则；Leader 修正最后一处 T1 次数残留，并同步 AGENTS 与 ADR-0104 追加适用关系。ADR 索引核查、活跃文档链接核查均 exit 0。限定为文本与五案例边界验收，不宣称真实效率或 token 节省已验证。见[独立审查](../../../.coordination/task/20261031-014-worker-autonomy/round-2/review.md#review)。
