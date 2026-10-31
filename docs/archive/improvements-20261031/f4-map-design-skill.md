<a id="goal"></a>
# F4 · 地图设计技能

来源：用户 2026-10-31 新增要求；[批次入口](README.md#plan-index)。

完整读取根目录 MAP_DESIGN_PLAYBOOK.md，学习 .agents 现有技能格式，把可复用流程提炼为 map-design 技能。短主入口+按需资源，历史快照/失效数字不冒充现行约束，动态事实指向代码和正式核查。技能覆盖先学后设计、几何闸门、材质/派生链、真实 GUI 取证与失败处理。

<a id="scope"></a>
## 实施边界

仅 .agents/skills/map-design/**、.agents/README.md、MAP_DESIGN_PLAYBOOK.md（迁入技能资源，原根路径移走，核对绝对目标后移动）。不改其它技能、地图、测试与配置。

<a id="exit"></a>
## 出口判据

frontmatter name/description 有效，项目扫描可发现；所有资源链接有效；主技能按需加载历史，当前规则引用真源；原 Playbook 内容可追溯，无根目录重复入口；给 Leader 可实际调用 skill 的名称与路径，区分静态格式验证和真实加载证据。

<a id="impl-facts"></a>
## 实施事实（Worker 记录，非验收结论）

状态：**待 Leader 独立审查**；Worker 不代写验收。

- **落点**：技能 `.agents/skills/map-design/SKILL.md`（短主入口）+ 四个按需资源：
  `GATES.md`（闸门口径与公式）、`SCHEMA-AND-DERIVATION.md`（yaml schema／材质／五条派生链）、
  `EVIDENCE.md`（取证、GUI、运行与内存陷阱）、`references/MAP_DESIGN_PLAYBOOK.md`（**历史快照**）。
- **迁移**：根目录 `MAP_DESIGN_PLAYBOOK.md` 已移入技能资源后删除。正文逐字符未改
  （仅把相对链接前缀改成所在深度 + 加一段迁移/历史声明）；"迁走前正文"与"迁走后正文"在剥离前缀后
  **逐字符相等**，可复核。
- **数值口径**：主入口与三个现行资源里**不写**易漂移的实测值；当前值统一指向
  `python3 tests/w6_geometry_check.py --out <json>` 与 `src/agc_sim/launch/world_map.py`。
  历史数字只留在标注为历史快照的 Playbook 中。
- **发现但未处理**（不在本单白名单）：`src/agc_sim/config/world_geometry.yaml` 头部注释与
  `tests/w6_geometry_check.py` docstring 仍有已知漂移（实体数、已不存在的函数名、`shape` 取值）；
  技能内改为"以代码为准"表述，不修这两处。
- **round-2 定点修正**（按 Leader 审查六处）：8 字净空负值不再当作"演示必然失败"的判决，
  只表示名义参考轨迹压到当前静态膨胀圆盘；删除"只在演示主地图要求为正"的基线豁免，改为未决；
  演示后端按入口默认与派工（默认 `full`，`lightweight` 不替代验收）；headless 仅限制 GUI 截图、
  不否认相机传感器出图；内存/PX4 结论限定为当时条件；视觉层与障碍的边界改按"是否影响车辆通行或
  接触"判定，新增低矮物体交回裁定；契约只留稳定引用、不转录条文。
- 证据与命令见 [round-1 report](../../../.coordination/task/20261031-015-map-design-skill/round-1/report.md#report)
  与 [round-2 report](../../../.coordination/task/20261031-015-map-design-skill/round-2/report.md#report)。

验收结果：**已验收**（Leader，2026-10-31）。父会话实际 `skill(name=map-design)` 加载成功；六处定点内容修正通过，独立链接核查 exit 0、活跃断链 0。见[独立验收](../../../.coordination/task/20261031-015-map-design-skill/round-2/review.md#review)。

<a id="open-items"></a>
## 后续未决（独立于技能迁移验收）

- 8 字净空正式断言尚未建立；minimal 静态圆盘口径负值须结合实际参考、偏置与安全层路径分析，再设计正式判据。当前不修改基线、不授予例外、不仅凭探针数值判契约违规。
- world_geometry.yaml 头注及 w6_geometry_check.py docstring 的既有漂移待维护；当前代码为事实来源。
- round-1 探针单次 35.6 s 超出 30 s 的偏离保留，不追溯豁免。
