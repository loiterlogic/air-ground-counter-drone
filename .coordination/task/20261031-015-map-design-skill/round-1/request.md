<a id="request"></a>
# F4 · 地图设计技能 · 批次派工

- 来源：用户授权四项工作及独立并行；Leader 本单裁定。
- 任务 ID：20261031-015-map-design-skill；轮次 1；状态：待执行。
- 基线：main / cedbc0e6c1e0e23aaf5b0effbf42ed9bf405def6。Leader 已归档旧计划并修改导航，四单同期改动均为预期，禁止覆盖或回滚。接单记录实际 diff 与指纹。
- 计划：[本单目标](../../../../docs/plan/f4-map-design-skill.md#goal)；[并行授权](../../../../docs/plan/README.md#parallel)覆盖旧协议冲突。先读 AGENTS、计划、相关契约锚点与规则，不预读无关历史。

## 目标与学习

完整读取根目录 MAP_DESIGN_PLAYBOOK.md，学习 .agents 现有技能格式，把可复用流程提炼为 map-design 技能。短主入口+按需资源，历史快照/失效数字不冒充现行约束，动态事实指向代码和正式核查。技能覆盖先学后设计、几何闸门、材质/派生链、真实 GUI 取证与失败处理。

## 写入白名单

仅 .agents/skills/map-design/**、.agents/README.md、MAP_DESIGN_PLAYBOOK.md（迁入技能资源，原根路径移走，核对绝对目标后移动）。不改其它技能、地图、测试与配置。
另可写本任务 report/evidence 和本单计划的实施事实，不能代写验收。CURRENT、归档、共享索引由 Leader 写，禁止 Worker 覆盖。各单写入范围隔离，未知冲突先报告。

## 授权与停止

T1=0，T2=0；离线文档/格式检查累计 600 s，单次 ≤30 s，次数只记账。产物本单 evidence/。
本批次 N=6 是记录检查点而非已知根因修复的机械停止上限；K=4 保留。连续四轮无区分性新证据则停止并提交假设台账；不是“没达成功就不可测”。在资源总量内有区分性进展可继续实施重验，保留所有失败与预算账目。超总时间、契约风险、未知漂移或范围越界立即停报。不得 commit/push/reset/clean，不派孙代。

## 验收

frontmatter name/description 有效，项目扫描可发现；所有资源链接有效；主技能按需加载历史，当前规则引用真源；原 Playbook 内容可追溯，无根目录重复入口；给 Leader 可实际调用 skill 的名称与路径，区分静态格式验证和真实加载证据。

## 交回

报告以 ≤30 行审查摘要开头，写执行会话 ID、基线、文件差异、学习/设计依据、命令/退出码/证据、预算、未执行与未决。完成时只更新自己的 report 状态为待审查，用 send_message 通知 Leader 后结束；不改 CURRENT、不等审查、不轮询。
