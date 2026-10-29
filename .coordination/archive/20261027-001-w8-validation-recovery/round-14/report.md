<a id="round14-report"></a>
# 第14轮执行回报

任务 ID：20261027-001-w8-validation-recovery；轮次14。

执行者：Worker（DSH 子会话 `55d8793e-4916-4045-ac19-5800e167ebfa`，父会话 `session-7bfaaed2-f329-4569-8dae-f795ccdba988`）。

## 0. 领取配对时钟（本轮第一个动作，先于任何读取/执行）

| 字段 | 值 |
|---|---|
| `claim_mono_before_ns` | `20368472217577` |
| `claim_wall_ns` | `1793167118227612591` |
| `claim_mono_after_ns` | `20368472218303` |
| `claim_pair_gap_ns` | `726` |

**口径**：唯一领取时钟依据；不用 mtime 反推。预算以同机 monotonic 判定。

## 1. 接单与基线

| 项 | 值 | 结果 |
|---|---|---|
| CURRENT 领取前 | 轮次 `14`、状态 `待返工` | 协议允许接单 |
| HEAD / 分支 | `d5072aaff33276bcd1c5e7d38b5caa75fe45a290` / `main` | 一致 |
| 基线 SHA | `77638a506faa3013cfa98963e2f1e67fbd3543095aca88bce44aab4604869e2a` | 与 receipt 一致 |
| 逐项复算 | **1865/1865**，missing 0、changed 0 | 通过 |
| `git status --porcelain` | 与 baseline `status` 逐行相同 | 通过 |
| 运行冲突 | 无自有/他人 ROS 探针进程 | 通过 |
| 被调脚本 SHA | driver `5fd70384…121d`、probe `72c18ceb…38cae`、gate `844e76a6…3e4e8`（与第12轮封存 manifest 一致，只读未改） | 通过 |

## 2. 本轮新增前置：AST 提取真实 parser 的参数契约验证

不靠手写白名单。`config/check_probe_contract.py` 用 `ast.parse` 读真实探针源码，**只提取** `main()` 中 `ArgumentParser(...)` 构造、`add_argument(...)` 序列与 `parse_args()`，在**仅标准库**环境重建等价 parser 并真实调用 `parse_args`：

- 提取参数 **13** 个；`rclpy` **未 import**、`main()` 后续**未执行**、未调用真实 `--help`、**0 participant**。
- 用驱动**同等** `shlex.split`+`format` 展开新根编排器的实际 `--probe-cmd`，`a`/`pub`/`sub` 三种 argv **全部被接受**。
- 负控制：有效 argv 追加 `--second sub` → **拒绝**（exit 2）；追加 `--second {second}` 字面量 → **拒绝**（exit 2）。

证据：`evidence/contract-check.json`、`evidence/contract-check-stdout.txt`；源码 SHA `72c18ceb…38cae` 已记录。

**驱动 argv 静态复核**：`config/static-check-{a,pub_first,sub_first}.json`，三种模式各 **16 项全通过**（`--run` 新根、`--scratch` 独占 r14、`--clean-env`、仅 jazzy wrap-source、domain0/LOCALHOST、`--allow-real-ros --t1-grant 3`、无 `--allow-fake`、默认 budget/reserve/hard-limit 未覆盖、topic/时长同第13轮、`--probe-cmd` 不含 `{second}`）。

## 3. T1 三次执行结果

| attempt | 模式 | 驱动 exit | valid | span | 双侧 wait RC | ROS participant |
|---|---|---:|---|---:|---|---:|
| `R14a` | a（3+2+2 s） | **0** | **true** | 8.147505 s | a=0 | 1 |
| `R14pub_first` | pub 先 8/sub 后 6 | **0** | **true** | 8.811125 s | pub=0, sub=0 | 2 |
| `R14sub_first` | sub 先 8/pub 后 6 | **0** | **true** | 8.855859 s | pub=0, sub=0 | 2 |

`invalid=[]`、`problems=[]`，三次均无重跑。

### 3.1 A 步控制（R14a）

| 阶段 | sent | heard | matched peak(pub/sub) | incompatible |
|---|---:|---:|---|---:|
| pos 同 topic 同 QoS | 14318 | **14316** | **1 / 1** | 0 |
| neg1 QoS 不兼容 | 42 | **0** | **0 / 0** | **1**（事件 2 条） |
| neg2 不同 topic | 40 | **0** | **0 / 0** | 0 |

事件顺序：`process_entry(1) → post_init(2) → node_created(3) → endpoint_created(4,5)…`，**6 个 `endpoint_created` 全部在 post_init/node_created 之后**。**A 通过**（正控制双侧 matched 且 heard>0；QoS 负控制零 matched/零 heard 且有 incompatible；不同 topic 零 matched/零 heard）。

### 3.2 B 步（R14pub_first，pub 先）

- 门控 `mark_found=true`、`checker_rc=0`、`side=pub`；helper 超时 `5.0 s`（`min` 到剩余预算）；第二方启动前剩余预算 **22.298 s**。
- 存活复核 `alive_same_identity=true`、`probe_end_present=false`、`starttime=2044843` 一致。

| 端 | matched 峰值 | matched final | graph pub/sub 峰值 | heard 峰值 |
|---|---:|---:|---|---:|
| pub（先） | **1** | 0 | 1 / **1** | — |
| sub（后） | **0** | 0 | **0** / 1 | **0** |

pub `sent_n=159`、sub `heard_n=0`；pub 侧 2 条 matched 事件（current 0→1，对端退出后回落）。

### 3.3 C 步（R14sub_first，sub 先）

| 端 | matched 峰值 | matched final | graph pub/sub 峰值 | heard 峰值 |
|---|---:|---:|---|---:|
| sub（先） | **1** | 0 | 1 / 1 | **0** |
| pub（后） | **0** | 0 | 1 / **0** | — |

sub `heard_n=0`、pub `sent_n=119`。

## 4. 判读

落在派工第 25 行第 3 种：**旧"随启动顺序翻转的单向匹配+零消费"形态仍在**，即 **`endpoint_created` 创建返回门控仍未消除该形态**。

- **B/C 都复现**：先启动方 matched=1 且看得到对端 graph，**后启动方 graph/matched 恒 0**，双侧**零消费**；换成 sub 先起后**方向翻转**到 sub 侧。
- **A 有效**，故不是探针失效造成的观测。
- **唯一新增排除项**："只是启动太早"这一简单解释被排除——本轮等待条件（先方 endpoint 创建返回 + 身份/QoS/时序校验 + 实时存活复核）已强于"脚本启动后约 1 s"。
- **仍不能定位根因**：无法区分 participant 发现子进程时序、SPDP/SEDP、共享内存可见性、rmw 实现差异等；**不主张** SHM/UDP/权限/domain 任一为根因。
- `endpoint_created` 只表示 **API 返回**，不是 DDS 发现就绪；本轮所有表述按此口径。matched≠送达，heard=0 与 matched=1 并存的断点未解释。

## 5. 预算

| 口径 | 值 | 限 |
|---|---|---|
| T1 使用 | **3/3**，无重跑 | 3 |
| 单次最大 span | **8.855859 s** | ≤30 s |
| 累计 span | **25.814489 s** | ≤90 s |
| ROS participant 峰值 | **2** | ≤2 |
| **整轮 mono** | **143.440 s ≈ 2.39 min** | ≤45 min |

wall 145.458 s；该窗口偏移漂移 **+2.017 s**（如实报告，不假设原因、未改时钟）。算术见 `evidence/budget-arithmetic.json`（封存前独立复算）。

## 6. 证据与原件

每例 `cases/<attempt>/` 均含：`command.json`（完整 argv）、`drive.json`、`report/*-drive.json`、`log/*-drive.log`、`helper.stdout/.stderr`、`probe/<side>/{events.jsonl,result.json,clock.env,stdout.txt,stderr.txt}`。三次共 **35 个原件文件**，全部在封存内。

- 无失败/无效 attempt，故无失败编号。
- **未产生项**：无（所有 attempt 都产生了 events/result）。
- 未写第12轮源根、未产生 `__pycache__`（已核验）。

## 7. 判读边界（不夸大）

- 不构成通信恢复、不是 S2 通过、不开放 S3/S4、不改 `gate`/`headless`/P1/P2/W7-c/W8-E2。
- B/C 各仅 1 次、无重复；matched/graph 为本进程视角，不证明对端对称。
- 本轮**未**换 domain/discovery/transport 配置（派工禁止），故不构成对配置分支的新证据。
- A 是同进程控制，不能替代跨进程阳性对照。

## 8. 状态

- CURRENT 置 **待审查**，已 `send_message` 通知父 Leader；不轮询、不接下一单。
- S2/S3/S4 关闭；`gate=not_evaluable_as_specified`；headless 未授权；整链不归档。

## 9. 封存与取回实测值

首次封存，**未** `--force`；stdout 写 `/tmp/agc-w8-validation-r14-archive/archive.log`。

```
ok     w8-validation/20261028-endpoint-gated-probe-r2 artifacts=55 verify=True files=56 mismatches=0
archived=1 skipped=0 error=0 retrieval_failed=0
```

| 核对项 | 实测值 | 结果 |
|---|---|---|
| manifest artifacts | **55** | 逐个 size/SHA 复算，**0 mismatch** |
| tar 真实根 | `20261028-endpoint-gated-probe-r2/`（唯一） | 正确 |
| tar 成员数 | **56**（55 源文件 + manifest 自引用） | 差集为空 |
| `root_only` / `tar_only` | `[]` / `['config/evidence_manifest.json']` | 符合脚本设计 |
| tar SHA256 | `9c6b4bda754f8e0c2f54b19c17c230d292a1b7e3e0652595450d107b7cf2d082` | 与 checksum 一致 |
| retrieval | `verified=true`、`files_checked=56`、`mismatches=0` | 通过 |
| tar vs 源根逐文件 | **0 处不一致** | 通过 |
| 封存后源根写入 | **无** | 合规 |

**过程性偏差（如实）**：`check_probe_contract.py` 首次运行时 `import build_cmd` 在 `config/` 下产生了 `__pycache__`（派工要求"不写 pycache"）。已**删除**该目录，并把加载方式改为 `importlib` + `sys.dont_write_bytecode=True`，重跑契约验证（`ok=True`）；封存前确认源根无 `__pycache__`/`*.pyc`。另：核对 argv 一致性时最初直接比较 `sys.executable` 起始的 argv，与 `command.json` 记录的 `argv[1:]` 错位，已按对齐口径重核 → 三次 **argv_identical=True**、**probe-cmd 不含 `--second`**（`evidence/argv-consistency.json`）。

## 10. 结束配对时钟

| 字段 | 值 |
|---|---|
| `end_mono_before_ns` | `20511912596058` |
| `end_wall_ns` | `1793167263685355642` |
| `end_mono_after_ns` | `20511912596868` |
| `end_pair_gap_ns` | `810` |

整轮 **mono 143.440 s ≈ 2.39 min**；wall 145.458 s；偏移漂移 +2.017 s。
