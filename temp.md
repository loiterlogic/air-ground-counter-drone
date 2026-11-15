# 地面安全层（ADR-0045）落地时遇到、但无法自行解决的问题

> 交接说明：以下每一条都是本轮实测确认过的，不是推测。
> 每条都写清「现象 / 证据出处 / 为什么我不能自己改 / 需要什么裁定」。
> 前置约束（我全程守着）：唯一执行口不变、不引入第二命令者、不新增路线分支。

---

## 一、必须由你裁定才能继续的（阻塞项）

### 1. `max_offset` / 反应窗口 / 实测折扣三者数学上不能同时成立

**现象**：安全层的 `SLOW` 档会把线速度与角速度按同一比例裁剪。实测证明这会削弱横向逃逸能力，
但更严重的是：**即使完全不降速，本车在 2 s 窗口内也做不出 `max_offset = 1.0 m` 的横移。**

**证据**（`experiments/w5-ground-nav-safety/20261113-calib-slow3/metrics/safety_calibration.json`）：

| 条件 | 2 s 横向位移实测 |
|---|---|
| `slow_min_ratio = 0.2`（改造前配置） | 0.0002 / 0.030 / 0.048 m |
| `slow_min_ratio = 1.0`（不降速，对照臂） | 0.956 / 1.153 / **0.769** m |

理想圆弧 `(v/ω)(1−cos ωT)` 在 `v=1.0, ω=0.96, T=2.0` 下是 **1.398 m**；
实测最小值 0.769 m ⇒ 折扣 **0.55**。要求 1.0 m ⇒ 理论需要 1.45 m，**超过上限 1.398 m**。

反解 `slowRatioFloor()`（要求 `L(r)·eff ≥ required`）：

- `eff = 1.0`（无折扣）→ 下限 **0.4777**
- `eff = 0.69` → 下限 **1.0000**（即 SLOW 不得降速）
- `eff = 0.55`（实测最差）→ 下限 **1.0000**

**为什么我不能自己改**：这三个量分属不同决策域 ——
`max_offset = 1.0` 是 [ADR-0004 (e)](docs/adr/0004-ground-control-rl-primary-and-nav2-safety.md#top)
的标定结论（当时 4 次采样最小值 1.017 m，余量只有 1.7%），`T = 2.0 s` 是
[ADR-0010](docs/adr/0010-safety-thresholds-and-failsafe.md#top) 的反应窗口，
实测折扣是我新测的物理事实。改任何一个都动到上游契约。

**需要你选**：

- (a) 放宽 `max_offset` 到实测可达值（0.75–0.8 m），承认"2 s 横移 1 m"不是本车能力；
- (b) 延长反应窗口 `T`（如 2.5–3.0 s），代价是三档距离要跟着重标；
- (c) 承认"逃逸能力"这个主张对本车不成立，从契约里去掉它，
      安全层只承诺"停在障碍前"，不承诺"横向躲开"。

**当前代码的临时状态**（为避免静默错值）：`slow_min_ratio = 1.0`、`lateral_eff_ratio = 0.55`，
即"SLOW 状态成立但不再降速"。这是诚实的表达，不是终态 —— 我在
[ADR-0045](docs/adr/0045-ground-safety-layer-self-owned.md#top) 的「实测证据 E」里如实标了。

---

### 2. 需要一个"障碍足够大、且车必须逼近它"的场景

**现象**：`safety_scenario`（原安全层取证台架）在新口径下**无法产出障碍**，
`tests/check_safety_tiers_escape.py` 已按你的裁定改到 `backend:=full` 整链，
但 `s04`（主场景）路径无遮挡、全程 `PASS`，`s11`（goal 在立柱后）拿不到障碍。

**`s11` 为什么拿不到 —— 计算得出的硬几何约束**：

- `pole_1`：尺寸 `0.3 × 0.3 × 3.0`，底面 z=0，**顶面 3.0 m**；
- 该场景无人机低飞：`map_adapter` 实测 `cam_h = 3.39 m`
  ⇒ 相机只比柱顶高 **0.39 m**，单目正下视在掠射角下拿不到稳定连通域；
- 即便正上方：`GSD = 0.0126 m/px` ⇒ 柱顶只有 **24 px**，
  而 `min_obstacle_side_m = 0.24 m` 换算为 **19 px** —— 余量只有 5 px。

实测佐证（`/tmp/s11.log`，本轮）：`nadir_projection` 稳定 `5.1–6.4 Hz`、
`carve = 2,738,906`、`rays[hit=0 edge=236]`、`连通域 0 个`、`障碍像素 0`。

**为什么我不能自己改**：新建场景要动 `src/agc_task/config/scenarios.yaml`，
而那是**回归矩阵的既有格**，改它会改变历史 run 的可比性；按场景轴登记规则须另立。

**需要你做**：确认是否新建一个场景（如 `yard` 的 8 m 高建筑 + goal 置于其后），
或明确"三档整链回归"用标定台架（`--stage cell`）承担即可、不再单独立场景。

> 补充事实：三档在整链上其实**已经有证据**了 —— 在标定里。
> `20261113-calib-cell5` 让车朝地图真实障碍开：`SLOW(2.249) → SLOW(2.086) → STOP_COLLISION(1.773)`，
> 判据取自安全层自己的 `state`。缺的只是"最小场景的秒级回归"这种**形式**。

---

## 二、已确认存在、但我不该擅自动的（非阻塞）

### 3. 5 个历史 L4 脚本因 Nav2 安全层退役而失效

`tests/` 下这 5 个脚本仍在查 `/collision_monitor/get_state`（该服务随节点一同退役）：

- `check_scan_self_filter.py`
- `check_scan_source_loss_stop.py`
- `check_action_direction_escape.py`
- `check_actuation_relay_hardening.py`
- `check_baseline_path_replan.py`

它们现在会如实 FAIL。我**没有改**：它们断言的是旧链路的取证口径，
按产物分类属"历史证据档案"，改写等于伪造历史。

**需要你定**：是 (a) 按新口径重写判据，还是 (b) 移入 `scripts/archive/` 并在台账登记"引用已退役对象"。

### 4. `STOP_EMERGENCY` 档在整链上从未触发

**这不是缺陷**：实测制动距离 `s_brake(0.8) = 0.245 m`，车在 `d ≈ 1.77 m` 就被
`STOP_COLLISION` 的扫掠判据截住，**不会**再靠近到 `d < d_emergency = 1.0 m`。
该档的正确触发条件是"障碍单拍突现"，属故障注入。现由活节点核查
`tests/check_safety_layer_live.py` 的 `d_near` 用例覆盖（实测 `STOP_EMERGENCY, v_out=0`）。

**需要你确认**：接受"整链不触发、仅活节点核查覆盖"这一取证形式，还是必须补一个故障注入用例。

---

## 三、排查时反复踩的环境坑（建议写进排障速查，不是我一个人能改的）

### 5. 残留进程会把整链压垮，且症状伪装成"感知坏了"

**现象**：我自己的多轮实验留下 5 个 `parameter_bridge` + 多个 `gz sim`，
系统 load 冲到 **27.84**（32 核），然后：

- `nadir_projection` 掉到 **0.16 Hz**（正常 10 Hz）；
- 标签帧与深度帧时间差漂到 **6.5–20 s**（容差 0.15 s）⇒ 每帧都被丢弃；
- `/agc/map` 恒 `occupied=0` ⇒ 安全层正确地拒绝驱动 ⇒ 车不动。

**误判风险很高**：这个症状和"相机没配好""感知链坏了"完全一样。
我花了不少轮次才定位到是资源争抢。

**建议**：`./run_demo.sh stop` 只清本项目记录的 PGID，清不到我手工起的
`ros2 launch`（没有经过编排器）。建议在 `doctor` 里加一条**
"检查是否存在未登记的 `gz sim` / `parameter_bridge` 残留"**。

### 6. 任务锁存终态后无法恢复，一次 launch 只能标定一个阶段

**现象**：任务进 `INFRA_FAILURE`（`air_hover_timeout`，低负载时 45 s 不够）后：

- `/agc/task/abort` → `abort rejected: not_active state=INFRA_FAILURE`
- `/agc/task/start` → `start rejected: release_control_failed`

**后果**：标定一次要跑 4 个阶段（brake / reaction / cell / slow），
每阶段 40–90 s，合计远超 `t_max_s = 120 s`（`src/agc_task/config/base.yaml`），
必须**每个阶段单独起一次整链**（每次约 2 分钟启动）。我已按此实现分阶段，
但这是**结构性限制**，不是我的选择。

**建议**：要么允许标定台架把 `t_max_s` 调大（属参数，但要确认不影响回归），
要么提供一个"终态后可重置以便复跑"的路径。

---

## 四、已确认的事实（写下来避免重复劳动）

| 事实 | 值 | 出处 |
|---|---|---|
| `a_brake` | **3.2754 m/s²**（取多次最小值，安全方向） | `calib-brake3` |
| `t_react` | **0.1841 s**（安全层输出零速后 p95） | `calib-react2` |
| `cell_epsilon` | **0.3536 m**（半格对角；实测判停净空跨距 0.476 ≈ 1 格） | `calib-cell5` |
| 可重放一致性 | **974 拍，一致 974，不一致 0** | `calib-replay/safety_trace6.jsonl` |
| 旧 `a_brake = 0.9` 的后果 | `s_brake` 被高估 2.7 倍，车远未接近就停死 | 计算 |
| 三档距离在新模型下 | 仍自洽（`s_brake(1.5)=0.62` < `d_emergency=1.0`） | 计算 |

**标定台架**：`tests/check_safety_calibration.py`，分阶段：
`--stage brake|reaction|cell|vsafe|slow`。必须在 `backend:=full` 下跑
（无相机 ⇒ 无地图 ⇒ 车不动）。**必须先看到 `occupied > 200`**，否则测得全是零速。

**可重放链路**：`tests/record_safety_inputs.py`（录制）→
`./build/agc_ground/safety_replay <trace.jsonl>`（离线重放，调用生产类）。
三条口径纪律已写进
[地面安全层判定与标定](docs/conventions/地面安全层判定与标定.md#replay)，违反任一条对拍必失真。

---

## 五、我建议的处理顺序

1. **先定第 1 条**（`max_offset` 三方矛盾）—— 它决定安全层"逃逸"这个承诺是否存在，
   影响 `slow_min_ratio` 的终值，也可能连带改三档距离。
2. 第 2 条（场景）可以缓，因为三档已有标定证据；但如果要长期回归，早晚要建。
3. 第 3、4 条是文档/归档层面的处置，不阻塞功能。
4. 第 5、6 条建议进排障速查，否则下一个人会重踩。
