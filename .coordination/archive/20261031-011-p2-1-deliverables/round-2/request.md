# P2-1 · round-2 request（Worker 自写，批次内）

<a id="p2-1-r2-request"></a>

- 任务 ID：`20261031-011-p2-1-deliverables` · round-2 · 2026-10-31
- 来源：**Worker 自写**（批次授权 [N=6 / K=4](../../../README.md#batch) 内，继承 round-1 边界，不改目标/白名单/验收/契约）
- 承接：[round-1 report](../round-1/report.md#p2-1-r1-report) 第 9 节「下一轮建议」

## 本轮唯一目标

**用一次 T2 同时产出三张真实截图 + 一段连续帧序列（供 GIF）**，把派工单步骤 5 的
(b) 取三张截图 与 (c) 录 GIF **合并成一次运行**（派工单预算栏把这两项列为两次 T2；
合并后省 1 次预算，属**更省**而非越界）。

## 为什么合并

round-1 的教训：`run_demo.sh` 跑完即回收进程组，Screenshot 服务随之消失——
**运行结束后再取帧必然失败**（round-1 T2-b 就是这样 0 帧）。
所以取帧必须在**运行期间**由外部驱动轮询完成；既然要在运行期连续取帧，
三张代表帧与 GIF 帧序列自然来自**同一次运行**，没有理由跑两次。

## 假设与判别

| 假设 | 判别实验 | 判别依据 |
|---|---|---|
| H2：`Screenshot` 插件在 Wayland 下能取到真实帧 | `capture_run.py` 取帧 | 产出 PNG 非空且**非纯色**（像素方差 > 阈值，证明有画面而非黑帧） |
| H3：运行期轮询能覆盖启动/跟踪/终态三段 | 同上，检查三图是否各命中 | `capture-manifest.json` 的 `picked` 三项均非 null |
| H4：1 Hz 取帧能做出 10–15 s / 800 px / ≤5 MB 的 GIF | `make_gif.py` | `gif-manifest.json` 的 `spec` 三项全 true |

## 步骤

1. 前置：`./run_demo.sh status` + `ps` 特征进程 + `/dev/shm` 检查（干净才启动）；
2. **T2（1 次）**：`python3 scripts/demo/capture_run.py --out experiments/p2-1/round-2 --duration 110 --interval 1.0`；
3. 三图落 `docs/plan/assets/`（`demo-start.png` / `demo-tracking.png` / `demo-terminal.png`），
   **校验每张非纯色**（黑帧不算取到）；
4. `make_gif.py` 合成 `docs/plan/assets/demo.gif`，核对 800 px / ≤5 MB / 10–15 s；
5. 重跑 `./run_demo.sh test`，确认 `offline` 组因图片到位而恢复全绿；
6. 补 `tests/README` 的冒烟入口说明（白名单内）。

## 预算（本轮）

- **T2：1 次 / ≤600 s**（批次累计将达 **3/4 次**）。
- **T1：0 次**（若取帧失败，改用 T0 离线诊断读日志与 `gz service -i`，不占 T1）。
- 离线只读检查：次数只记账。

## 停止条件（继承首轮 + 本轮追加）

- 若**取帧仍失败**（服务响应 false / 文件不生成 / 帧为纯色）→ **不重跑**，
  转 T0 诊断（读 launch.log、`gz service -i /gui/screenshot`、检查输出路径权限），
  结果写进假设台账，**不消耗第二次 T2**；
- 若 GIF 三项规格降级后仍不满足 → 如实记录实际值，**不宣称**达成；
- 其余继承 [round-1 request](../round-1/request.md#p2-1-r1-request) 的预登记停止条件。

## 不做（本轮明确排除）

- 干净环境验证（round-3）；
- 完整视频（需评估，见 round-1 假设台账 H5）；
- P2-1 出口判据勾选（里程碑达成时统一勾）。
