<a id="top"></a>
# W8：种子证据、版本边界与测量 P3 派工

## Status

accepted（2026-10-26；证据分类及执行范围已裁定，P3 实施待执行、待 Codex 审查）

<a id="scope"></a>
## 适用范围

承接 [上轮交接审查](../../.coordination/archive/20261026-001-handoff-baseline/review.md#review)；补充 [ADR-0100](0100-full-chain-seed-protocol.md#scope) 的证据边界，以及 [ADR-0065](0065-toolchain-rebuildable-pin-manifest.md#status) 的本地补丁保存和校验覆盖。工具链值仍只归 [pin 清单](../../toolchain/README.md#pins)。P3 指标定义只归 [ADR-0099](0099-w8-fixed-budget-mission-fco-measurement.md#metric)，本 ADR 不另定义指标或契约。项目状态以 [Runbook](../ROS2迁移步骤.md#status) 为准。

<a id="evidence"></a>
## 证据裁定

| 项目 | 此次可核验事实 | 可得结论 / 限制 |
|---|---|---|
| ADR-0100 构建、语法、mixer 性质声明 | 检索 docs、scripts、相关 specs、W8 pilot/P1 重做文本及 JSON，未找到其原始执行记录；文件名检索仅另找到旧 R-038 感知 seed 测试 | 原声明标为未核验；旧 R-038 不能验证此次 PX4/launch 改动；不以检索无命中断言历史没有运行 |
| 种子实现 | 独立读取五个 launch/composition 差异及 PX4 两文件差异 | full 链按实例派生、standalone 直传、GPS 私有流为源码事实，运行生效仍待核验 |
| 工具链现状 | `python3 scripts/toolchain_pin_check.py` 退出码 1，24 PASS / 1 FAIL；唯一失败为 PX4 二进制哈希漂移 | 不能宣称当前工具链通过；二进制存在/mtime 不证明此次构建成功，不证明二进制含补丁 |
| 补丁保存 | 导出 PX4 当前两文件相对 HEAD 的差异，使用基准文件在临时目录应用并逐字节比对，一致 | 已保存可还原的两文件源码差异；尚无完整干净环境构建证据 |
| 历史 P2 审计及 P1 重做 | 上轮核验报告和输入哈希，本轮不重算历史指标 | 保留原结论；不存在可从聚合 summary 精确重建的新固定预算指标 |

本轮只读检查与补丁重建证据目录：`experiments/w8-parity/20261026-w8-p3-boundary-review/`。其中 `config/baseline.json` 记录观察现场，`metrics/pin_check.json` 记录失败项，`metrics/patch_reconstruction.json` 记录重建方法与逐文件哈希；这批记录不是仿真 run。此次未构建、未跑测试、未启动仿真。

<a id="versions"></a>
## 历史与未来版本边界

- 历史科研确证、pilot、测量 P1/P2 保留原件、原 gate 和 verdict。审计表可另加版本归属，不回写历史 manifest，不依据目录时间推定其运行源码。
- 有实际源码/二进制快照能证明旧实现的记录，标 `verified_pre_seed_protocol`；只有历史叙述但缺少足够版本材料的，标 `seed_protocol_not_attested`，不得强标 pre 或 post。
- 本次工作区标 `seed_protocol_candidate_unvalidated`。未来 run 只有同时保存主仓 HEAD + tracked diff + 相关 untracked 文件内容/哈希、配置和安装后实际执行文件指纹、PX4 上游 HEAD/子模块/完整 dirty 清单、补丁、源码及二进制哈希，且运行 manifest 和 own/intruder 的 GPS seed 日志一致，才能标 `seed_protocol_v1_attested`。
- per-instance 派生仅适用于 W6 full；standalone 范围见 [ADR-0100](0100-full-chain-seed-protocol.md#scope)。lightweight 中即便出现 seed_protocol 字段，也不证明运行过 PX4；warmup 值区分计划派生与实际启动。
- 种子噪声流可追溯不等于整链确定性；seed 内调度/执行重复继续作为实验设计的一部分，不能删除重复后称为完全复现。

<a id="preservation"></a>
## 保存与提交边界

采用主仓保存小补丁、工具链 README 保存唯一 pin 清单、外部 PX4 工作树继续忽略的方式。补丁必须能从清单基准还原，不能只保存当前机器绝对路径。校验应覆盖补丁哈希、应用后的源内容、全部意外 dirty/untracked 改动及子模块状态；不能放行额外未登记改动。

建议后续审阅分组：① W8 测量 P1/P2 文档、审计脚本与测试；② 人工交接设施及索引；③ seed launch 改动、PX4 补丁/pin/验证；④ P3 记录器及测试、设计草案。P3 基于显式 dirty 基线执行，无须先提交才能工作；不自动 commit/push/merge/切分已有补丁。同一文件跨组改动需人工审阅后选择性提交。本地 specs 与实验数据继续按 ADR-0081 保留，交接设施沿用用户已同意的入库边界。

<a id="p3"></a>
## P3 本轮执行范围与顺序

1. **先补前置验证**：校验保存的补丁，补齐 seed 派生与 launch 注入、实际 GPS RNG 的同 seed 重启/异 seed/私有状态/非法值/零值验证，保留执行记录；扩展工具链 checker 并验证正常/篡改/额外 dirty 负例。对含补丁 GPS 模块作有可定位编译步骤的构建（必要时只清理该模块的目标产物），禁止用零编译的 no-op 或旧二进制替代。保存输入/产物对应关系后，显式更新 README 的二进制 pin，再重跑校验。
2. **再实现并验证记录器**：先研究同版本 run_logger 状态/episode/目标/包络回调、task_manager 状态发布时间及既有 gtest 结构。新指标独立字段、逐区间账本与完整性审计；ABI 与旧统计字段原语义保留。新实现在正常 ROS 回调链中的端到端验证必须覆盖，不能只测孤立数学函数。
3. **最后两次 GUI 工程验证**：前两项通过且无额外异常后，串行 full / d3d12，P1 s15/p1_coop/seed5 一次、P2 s08/p2_rl_high/seed0 一次，总预算 2 attempts、infra 重试 0。这是工程验证，不是模式 pilot/等价或科研样本；失败尝试不以补跑替代。第一场同时完成 seed 运行证据核对，若缺失或不符，第二场不启动。无 GUI 或渲染后端不符则回报，不改用 headless。
4. **交回新设计草案**：覆盖 [ADR-0099 全部待办](0099-w8-fixed-budget-mission-fco-measurement.md#next)。草案标 `draft_pending_codex_review`，不得自动冻结执行计划。新 seed 网格、seed 内重复与独立单位、缺测识别界、联合等价方法、率类冗余、工程容差、n/成本及可行性都需明确。没有新指标方差不能伪造已校准 n；允许给出保守规划或另列待批准的小 pilot。旧 40/模式和 6h/场景只作历史预算参考，不能据此修改容差使方案“可行”。

草案的缺测处理先采用保守门：任何 mission 的新 FCO 存在未知区间或拒算，正式门不得宣布等价；保留该任务及识别界，不做 available-case 删除。若后续需要识别界上的稳健推断方法，另行审查，不能在结果出现后变更。本轮只预备草案，不执行这一正式门。

细节及预算见 [P3 spec](../../.trae/specs/w8-measurement-p3/spec.md#scope)。前置失败须阻塞后续；需要改变 PX4 RNG/seed 协议或控制行为则交回 Codex，不在本单试改。Gate 仍为 `not_evaluable_as_specified`；正式等价、新 pilot、headless 规模统计、W8-E2 和 W7-c 扩容均须后续独立派工。
