# P1-2 · round-4 最后一次 duration 补证

<a id="p1-2-r4-request"></a>

## 裁定

1. headless `viz=false` **不影响** round-2 GUI↔headless 等价可比性。`gz -s` 才是形态自变量；
   RViz 是额外观看客户端，不是任务测量/控制链。原等价产物保留，不重跑。
2. `--duration 15` 被 13.61 s 终态抢先，属有效判别结果。追加**最后一次** `--duration 8`，
   根据已有 13.61 s 成功样本可在 GROUND_APPROACH 中触达，不是同根因盲试。

## 唯一任务

运行一次 `./run_demo.sh --headless --duration 8`，核对：

- follow 阶段到时前没有任务终态；
- `exit_reason=duration_limit`、`duration_branch_taken=true`、退出码 3；
- 进程组回收 confirmed、无残留；
- summary 存在且保留（主动停不是 TRACKING_SUCCESS，不得包装成成功）；
- headless `viz:=false` 保持。

## 预算与停止

- T2：**1 次 headless attempt / 150 秒**，不跑 GUI，不跑等价，不改容差。
- T1: 0；离线检查 ≤120 秒。
- 白名单同 round-3；若代码无需改动就只写证据和报告。
- 若仍未触达、退出码不对或清理失败，停止并保留为已知缺口，不再追加。
- 完成后写 round-4/report.md、CURRENT 待审查，不开始 P1-3。
