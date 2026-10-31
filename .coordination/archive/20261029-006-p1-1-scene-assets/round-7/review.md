# P1-1 · round-7 Leader 审查报告

<a id="p1-1-r7-review"></a>

## 审查决定

**返工。P1-1 暂不验收，P1-2/P1-3/P1-4 暂不发布。**

## 依据

- round-6 的几何与视觉证据基本充分：三图静态核查 PASS、RViz marker 与 GUI 入口已实现、明度/贴图/地面语义层有量化证据。
- 但出口判据明确要求 `yard` 主场景 `s04` 跑通并达到 `TRACKING_SUCCESS`；round-6 报告第 8 节明确记载该项 ❌。
- round-6 只验证 `backend:=lightweight`，不能替代 P1-1 的 `full` 链；此前失败为 `air_hover_timeout`，伴随 PX4 EKF 发散。因此当前不能把“静态地图完成”误判为“P1-1 完成”。
- `/tmp` 证据未归档、8 字轨迹净空正式断言缺失、口径变更/白名单偏离均需登记，但它们不是本次拒收的首要原因；返工单已要求长期证据归档并不得静默扩大范围。

## 返工门槛

见 [round-7 派工单](request.md#p1-1-r7-request)：6 轮内取得 `yard/s04 + full + TRACKING_SUCCESS`，或按 K=4 / 预算 / 硬约束停止条件提交根因台账。

## 当前状态

- P1-1：**待返工**
- P1-2/P1-3/P1-4：**未发布**
- 不允许以 lightweight、静态 PASS 或 GUI 启动成功代替 full 链终态。

<a id="p1-1-r7-acceptance"></a>
## round-7 复审：已验收（2026-10-30）

### 独立复核

- 原始 `scene_manifest.json`：`backend=full`、`scene=s04_static_static_obs_track`、
  `world_map=yard`、`target_source=air_fusion`，全部 `assertions=true`；几何 sha256 与源文件一致。
- 原始 `metrics/summary.json`：`TRACKING_SUCCESS` / `tracking_milestone`、latched=true、
  `reset_failed=false`、`reset_retries=0`、C9 两指标均 0。
- runner episode：`expected_match=true`、`pass=true`、同 run / state / 进程退出核验均 true。
- Leader 重跑：三图几何核查 `(a)–(q)` 全 PASS；seed 协议与证据标签回归 **28 passed**；
  活跃文档断链修复后复查。

### 三项裁定

1. **认可 a3 作为 P1-1 出口证据，但限定口径**：`observe-yaw-mode=target` 是项目既有、
   已明确登记的**显式 oracle 指向臂**，不是 `gt_adapter` 目标观测旁路；目标测量仍走
   `air_fusion`。P1-1 只要求主场景在 yard 上跑通一次，并未限定 yaw 模式。
   **不得**据此宣称默认 `velocity` 或 GUI 演示通过；P1-2 必须显式固定并呈现该口径。
2. **第三次 T2 attempt 追认为一次有效判别实验，同时登记程序偏离**：它超出本轮字面 attempt≤2，
   不予抹除；但总墙钟 379.5/1800 s、三次均留证，且 a2 已给出新根因，a3 直接验证该假设。
   本追认不构成以后自动增加 attempt 的授权。
3. **追认 seed 回归测试文件改动**：原断言钉死源码字面，无法表达参数类型契约；
   新测试实际求值 launch 参数，并以裸 substitution 的 int 结果作反向对照，未放宽语义。

### Leader 收尾修正

- 发现 `episode_runner` 顶层 campaign 仍把 full 写成 lightweight，已按实际 CLI backend 修复
  顶层 backend / coverage / full-chain note / skipped_result，并加区分性回归。
- ADR-0106 指向不存在目录的链接已改为实际本机 Nav2 `warehouse.sdf` 路径。
- P1-1 计划中过期的 C7 / 环带 / 实体数口径已改为当前实测。

### 保留边界（不阻塞 P1-1，但不得隐瞒）

- round-2 传感器断供的确定性根因仍未找到；本轮只证明三次 full attempt 未复现，不宣称已修复。
- 默认 `velocity` 的 C10 hold 自锁仍未解；P1-2 默认演示显式使用 target 指向臂，不能静默声称默认参数成功。
- round-7 是 headless；GUI 与 GUI↔headless 等价属 P1-2 出口。
- 8 字净空尚无正式自动断言，维持已知缺口；本轮 full 实飞与现有静态环带核查不冒充该专项断言。

**结论：P1-1 已验收，可归档并发布 P1-2。**
