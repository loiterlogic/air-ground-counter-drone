# P1-2 · round-1 批次派工单

<a id="p1-2-r1-request"></a>

## 目标与前置

P1-1 已验收归档。实现并验证 [P1-2 一键演示入口](../../../../docs/plan/p1-2-一键演示入口.md#p1-2-goal)：
一条命令启动、一条命令停止、失败人话、退出无残留，产物完整。

## 已验证口径（必须显式承接）

- 主场景 `s04_static_static_obs_track`、默认 `backend=full`、默认 `world_map=yard`、seed 0。
- P1-1 成功样本使用 `observe_yaw_mode=target`，属**显式 oracle 指向臂**；测量仍走 `air_fusion`。
  默认 `run_demo.sh` 必须显式传 `observe_yaw_mode:=target`，不得依赖默认 velocity 后宣称成功。
  启动/界面/文档必须能说明这一点，不能把 target 指向包装成真实视觉识别。
- 保持 C10、唯一执行口、9 消息 ABI、终态、8 字与安全阈值不变；不新增命令者。
- round-7 已修复 `air_perception.seed` 类型和 runner 顶层 backend 标注，不得回退。

## 先学后做

先完整阅读 P1-2 plan、`scripts/episode_runner.py` 的进程组启动/回收/状态监测做法、
`docs/conventions/整链排障速查.md`、现有 `w6.launch.py` 与 `viz` 参数；对照本机已验证实现后再设计。
薄封装底层 launch，不复制编排，不替代 episode_runner。

## 交付范围（白名单）

- `run_demo.sh`
- `scripts/demo/**`（可按需新增）
- `scripts/tests/test_demo*.py`、`tests/demo*.py`（按需）
- `scripts/episode_runner.py`、`scripts/tests/test_episode_runner_labels.py`（仅证据标签/复用接口的必要小修）
- `docs/plan/p1-2-一键演示入口.md`
- `.coordination/task/20261030-007-p1-2-demo-entry/**`
- `experiments/demo/**`、`experiments/p1-2/**`

如确需改 `w6.launch.py` / RViz / 其他包，先停下报告，不自行扩白名单。

## 必须实现

1. `run_demo.sh` 默认 GUI/full/yard/s04，`--headless`、`--map`、`--scene`、`--duration`、`--backend`、`stop`、`doctor`。
2. doctor ≤30 秒、逐行 OK/FAIL，无仿真；故意缺环境/占端口/有残留时人话失败。
3. 独立进程组、PID/PGID 归属，start/stop/Ctrl-C 幂等；不能 `pkill -f`，不能清他人进程，不删证据。
4. PX4 等待有进度提示；从现有 `/agc/task/state` 呈现状态，自动调 `/agc/task/start`，跟到终态；summary 落盘并校验 run_id。
5. 默认 GUI 含 Gazebo；复用 P1-1 的 RViz 叠加能力，保证 demonstrable，不新增第二命令者。
6. 同 seed GUI/headless 各取得一次 full 成功；预登记关键指标容差并比较，不能只用“不显著”代替等价。
7. 失败启动、stop、Ctrl-C 均有真实测试证据；测试顺序串行。

## 预算与授权

- 批次 **N=6**，熔断 **K=4**；批次内 Worker 自写后续轮 request，仅四类事件唤醒。
- T0 静态/离线检查自主；离线检查总墙钟预算 600 秒，单次 ≤30 秒。
- **T1: 12 次 / 360 秒总墙钟**，仅用于 doctor/端口/进程标签等微观测；单轮 ≤3 次/90 秒，不启 GZ/PX4/GUI/full。
- **T2 总墙钟 2400 秒**，真实 full/GUI/构建总 attempt ≤8；同机串行，每轮真实 full attempt ≤2。
  其中必须保留：GUI 成功 1、headless 成功 1、stop 清理 1、Ctrl-C 清理 1、故障注入至少 1。
- 所有真实运行证据归档到 `experiments/p1-2/round-N/` 或 `experiments/demo/<timestamp>/`，报告链接，不只放 /tmp。

## 验收与停止

以 P1-2 plan 出口判据逐项验收，任何一项没有证据不得写 PASS。

- 若 6 轮内未同时取得默认 GUI/full 成功、同 seed headless 成功、两种停止干净、doctor/故障提示和完整产物：停止并提交缺口与假设台账。
- 连续 4 轮无区分性新证据立即熔断。
- 触及契约、需要超白名单/预算、或发现硬约束不满足，立即停止报告。
- 不 commit/push/reset/clean，不启动 P1-3/P1-4。
