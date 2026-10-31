# P1-2 · round-3 小范围补证派工

<a id="p1-2-r3-request"></a>

## 主审查结论

round-2 的核心 8 项证据经 Leader 抽查原始产物后成立，不推倒重做。只补以下两点后验收。

## 必做

1. **补 `--duration` 主动停现场**：仅 **1 次 headless full attempt**，使用 `--duration 15`。
   必须证明到时前没有终态、`exit_reason=duration_limit`、退出码 3、回收无残留、summary 保留；
   不把主动停写成任务成功。
2. **headless 不启动 RViz**：`scripts/demo/start.py` 将 `viz` 改为仅 GUI 时 true，headless 时 false，
   加离线回归。理由：P1-2 自己规定“不要起 RViz 才能看状态”，且 headless 用于经济快跑。
   该改动不影响 round-2 已封存的 GUI↔headless 原始等价证据；不得重跑等价或改写原报告数值。

## 已裁定事项

- `status` / `compare` 两个只读子命令**保留**，属于状态查看与等价核验辅助，不违反薄封装。
- 等价 20% 容差**不重开、不扩样本**。当前 n=1 结果符合预登记；ticks 16.6% 余量小作为已知边界保留，
  不做事后调整。若以后另立稳定性任务再重新预登记。
- T2 超 attempt 属程序偏离，保留记录，不因墙钟低而抹除；round-2 是否追认与本轮补证结论一起在 review 写明。

## 范围与预算

- 白名单：`scripts/demo/start.py`、`scripts/tests/test_demo_entry.py`、本 round 目录、
  `experiments/p1-2/round-3/**`、`experiments/demo/**`、P1-2 plan 的补证说明。
- **T2 仅 1 次 headless attempt / 150 秒**；不跑 GUI，不跑第二组等价，不扩种子。
- T1: 0；离线检查总墙钟 ≤120 秒，单次 ≤30 秒。
- 完成后写 round-3/report.md，更新 CURRENT 待审查；不得开始 P1-3。
- 若 duration 分支仍未触达或有残留，停止报告，不追加 attempt。
