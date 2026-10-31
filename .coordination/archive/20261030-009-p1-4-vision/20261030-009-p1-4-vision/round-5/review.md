# P1-4 · Leader 最终审查报告（round-5 收口）

<a id="p1-4-r5-review"></a>

## 裁定

**P1-4 不验收，作为“链路与接口已交付、truth 基线对比未闭环”收口。**

round-5 的 T-A 是有效的默认 `gz_x500` truth 基线；T-B 的 `gz_x500_mono_cam` truth run 因既有 lifecycle prewarm→OnProcessExit 竞态在就绪阶段超时，summary 为 `IDLE` / ticks=0，不构成对照。两臂也均未取得有效的派生 tracking error 文件，因此不能宣称第 4 项通过。

round-5 已消耗本授权的 2/2 T2；不再追加本任务的 T2。P1-4 的相机、接口、显式降级、消息级证据和数据集成果均保留，但不得把 `vision_model.id=none` 的成功 run 说成视觉识别已接管任务决策。

未来如需闭环第 4 项，必须另立任务，先解决采集器边采边写/窗口时序与 prewarm 竞态，再按同一固定场景和 seed 重新预登记。
