# P0-4 脚本系统瘦身 · 批次首轮

任务 `20261029-004-p0-4-script-curation` / round-1；来源Leader，用户已授权连续完成P0-3/P0-4/P0-5。根 `/home/chen/AGC`，main，HEAD `00f700a`；预期Leader改动：P0-3任务归档/最终review、CURRENT与本派工，其他产品基线干净。

## 目标

完成 [P0-4](../../../../docs/plan/p0-4-脚本系统瘦身.md#p0-4-goal)。P0-3已验收：[审查](../../../archive/20261029-003-p0-3-docs-and-skills/round-2/review.md#review)。遵守[协议](../../../README.md#protocol)、[路线](../../../../docs/plan/README.md#plan-index)。先看现有索引/测试/路径实现，再移动。

## 边界与白名单

- `scripts/`顶层目标≤12个执行脚本：现有8长期工具+新增adr_index=9；逐一按实际用途/依赖判定，别照旧32个统计硬搬。
- 允许 `scripts/research/`、`scripts/archive/` 接收计划内迁移，`git mv`保持历史；已有archive内容冻结（仅其README导航可改），绝不删除脚本。
- 可改被移动脚本的项目根推导、导入、子进程脚本路径等同根因路径问题，不能改算法/指标/判定行为。顶层长期脚本仅调整引用被移动脚本的路径。
- 可改 `scripts/tests/**`、`tests/**` 的必要路径适配/索引核对与小型离线测试；不得重构整个tests体系。
- `scripts/README.md`、research/archive README、`docs/plan/p0-4*.md`、路线README、`tests/docs_link_check.py`扫描范围、相关活跃文档/技能/包README仅必要引用调整。
- 既有ADR/历史命令证据不重写，只给明确迁移导航。**experiments、reference、toolchain实体树、src工程代码/配置禁止写入**；实验只可用限定文件名/glob的只读引用检索，不扫巨量日志/二进制。
- 本任务交接记录、CURRENT；Leader刚归档P0-3的纯路径修正和一笔结档提交也授权本次顺带提交，不改其历史结论。

## 验收

1. 顶层执行脚本≤12；README顶层表与实际精确一致；research README全量准确；必要时archive新增迁移表。
2. 索引自动核对测试有效（新增/漏记应失败），不仅镜像实现；移动脚本的导入/根定位/互相调用路径经过静态检查及有意义离线验证。
3. 活跃引用全部新路径，历史原命令保留且有迁移映射；文档检查通过，无新坏链。
4. 所有脚本保留git历史，不改研究行为，不运行真实ROS/仿真/捕获等实验。
5. 报告迁移前后清单、实际分类理由、完整命令退出码/测试结果/未执行项；记录工程轮数、通知次数、返工与连续无新证据次数供P0-5。

## 授权与预算

N=6/K=4；允许离线检查/pytest（仅确认不启动外部真实进程的测试）最多18次，每次≤60s，总≤900s；输出写 `/tmp/agc-p0-4-*` 或任务evidence。可用py_compile/AST与假依赖测试，不source启动ROS图、不执行research CLI猜测其安全性。若现有测试会构建/启动ROS，明确跳过并列未验证，不能假装通过。
T1系统观测=0，T2真实实验/构建=0。允许明确路径本地git add/commit（不push/reset/clean/stash/amend）。最多3笔实质主题+1笔回报提交，避免记录自增提交。
**若3轮内不能完成路径归位与离线验证，停止报告具体缺口；K=4无新证据熔断；N上限必停。** 需越白名单/预算、未知漂移、硬约束风险立即停。范围内自主修复，无需逐个询问。

## 回报

先≤30行审查摘要，附证据路径、预算/未决项。CURRENT置待审查，send_message给Leader后结束，不归档/验收/开P0-5。本任务只创建一次Worker，返工同会话复用。
