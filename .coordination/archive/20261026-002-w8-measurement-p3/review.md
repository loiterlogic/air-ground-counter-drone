<a id="review"></a>
# Codex 审查

任务 ID：`20261026-002-w8-measurement-p3`。仅 Codex 追加。

## 第 1 轮

2026-10-26 20:25（Asia/Shanghai），Codex 独立审查阻塞证据；**本轮不验收，转第 2 轮限定取证**。未运行工程代码、构建、节点或仿真。

<a id="round1-evidence"></a>
### 已核实与证据限制

- 实读 `log/pytest_node_run_logger2.log`：13 个 publisher matches 均为 0，断言 `mission_count == 1` 得到 0，测试失败。这只能确认该次测试未建立期望连接，不能单凭此定位到共享内存、DDS 实现或 C++ 运行时。
- 枚举本轮全部产物、搜索 log/config 后，未找到 stock C++ talker/listener 与 Python 对照的原始命令、双端输出、退出码和环境。执行者关于 stock C++ 失败/Python 成功的判断尚不能独立复核；“已排除”UDP、静态 peer、XML 等说法亦缺少逐次证据。应降格为待验证假说，不据此授权清理共享 shm。
- 独立读取 manifest、重算工作目录 48 个条目的 SHA256：47 个相符，`log/evidence_archive_final.log` 不符。manifest 及 tar 中该日志为空，工作目录现在含归档完成输出；这是归档输出文件被打包后继续写入的时序问题。它不使已验证的 tar 内容失效，但不能再宣称当前工作目录逐文件完全匹配 manifest。
- tar SHA256 实测 `9d3b4f4a3c22c3d078cecb194ae1aaa74cd608850bd621cea301e3799c862c46`，与侧车和回报一致。直接在 tar 中重算 48 个条目全部相符，另有 manifest，共 49 个文件；取回侧车 `verified=true`、49 files/0 mismatches。本次只读取 tar，不覆盖归档或历史 manifest。
- `AGENTS.md` 当前 SHA256 与先前 Codex 角色配置时观测一致，确在该次新增角色文件前已偏离派工指纹。执行者保留现场并回报正确；删除入口条款的来源仍未核实。本次不自动恢复、重写历史指纹或归因给执行者。用户在会话中明确提供的项目规则继续有效。
- 本次关注阻塞与交接完整性，R1/R2 实现正确性、R4 方法与可行性尚未完成独立审查；有执行者测试日志不等于已验收。R3 未执行的回报与现有证据相符，不得标为通过。

### 裁定与后续

1. 保留第一轮全部成果和失败证据，不归档当前交接任务为已完成。
2. 第 2 轮仅做通用 ROS 2 stock demo 通信诊断及证据补全，具体预算与白名单见 [追加派工](request.md#round2)。不得据此恢复工程节点、原任务 GUI 或后续实验。
3. 共享内存残留不是已证实根因，**不授权**清理 `/dev/shm`、停止共享 daemon/他人进程、切换系统 RMW、安装升级或全局配置修改。
4. 历史归档保持不变；归档日志漂移用第二轮新侧车报告原始哈希与当前哈希，不回填历史 manifest。
5. 根因尚未确定。先补齐同版本官方 demo、同一执行环境与同一进程配置的对照，再决定是否需要进一步修复。

## 第 2 轮

<a id="round2-evidence"></a>
### 独立核查（2026-10-26，Codex）

同一任务 ID，第 2 轮：**部分观察成立，执行协议不合格，整轮不验收；转第 3 轮限定返工**。本次只读日志、重算哈希、读取本机 ros2run 实现，未运行节点、构建或仿真。

- 直接核对六组双端日志：五组有匹配 Hello World 文本，包括 underlay Python→C++ 与 overlay C++→C++。这些观察不支持“C++ 整体无法通信”；首例 underlay C++→C++ 未观察到接收，原因仍未知。顺序、环境、进程重叠混杂，不能据此归因 overlay 或预热。
- **进程生命周期违规已证实**：`log/post_case_cleanup.json` 记录六个真实 listener 最后才统一回收。`ros2 run` PID 并非实际 demo PID；本机 `ros2run/api/__init__.py` 的 `run_executable()` 明确另建 `subprocess.Popen(cmd)`。首例 listener 189875 的 ROS 日志文件名起始时间与 SIGTERM 日志相距约 191.890 秒，py_cpp 的 190087 约 163.567 秒，overlay_cpp_cpp 的 190308 约 132.130 秒，均超过每例 20 秒；包装器退出不能证明实际端点已退出。独立话题可防串收，不能消除进程重叠混杂。
- 首例 listener 最终为 **71 字节，仅终止日志**，不是最终仍为零字节。`log/cases.json` 与各 `case.json` 的三组 C++ listener 哈希在真实进程退出前计算，现已过期；须保留原始元数据，另留更正侧车。不能把此时序问题解释为 DDS 根因。
- 归档 SHA256 实测 `540f6f962f949776d0879d71c5e6735bd175600eb0db2e1b2fa6d5ca64e36fed`，与 checksum/retrieval 相符。tar 共 43 文件，其中 42 artifacts 与 manifest 全部匹配；当前工作目录也全部匹配最终 manifest。**最终归档完整性通过，过期的是内部 case 元数据，不是最终 manifest 或 tar。**
- 重算派工基线 692 个路径：仅三个获准 spec/tasks/checklist 文件发生变化；HEAD/分支仍为派工值。工程文件未出现本轮新增变化。回收后进程清单未列 demo/daemon，支持已清场，但不补足逐例真实退出码。
- 20:32–20:55 是领取到回报时间；六组包装器耗时之和 85.4 秒不能证明诊断墙钟符合 12 分钟上限。因未分列取证与整理阶段，完整墙钟合规无法独立确认；已确认的逐例超限足以拒绝整轮验收。
- 历史归档日志漂移的新侧车可作为说明保留；前两轮成果和历史归档不得改写。工程实现/设计仍未独立验收，P3 继续阻塞。

### 裁定

第 3 轮只允许更正证据口径、修复独立诊断脚本的进程生命周期，并最多执行 **1 次官方 underlay C++→C++** 对照；不重跑语言矩阵，不据一次结果宣布定位根因。范围见 [第 3 轮派工](request.md#round3)。日志关闭后计算哈希，记录真实端点退出并核对无残留。清理共享内存、改变系统配置及恢复项目节点/仿真均未授权。


<a id="round3-evidence"></a>
## 第 3 轮独立审查（2026-10-26，Codex）

同一任务 ID，第 3 轮：**进程生命周期修正与最终证据完整性核查通过；协议偏离保留，整轮不作无条件验收，P3 继续阻塞。** 本次只读脚本、原始日志、元数据、规格与归档并重算哈希，未运行节点、构建或仿真。

### 已核实

- 实际脚本直接 exec 官方二进制、各自独立 session/PGID；case.json 保存端点 cmdline、相关环境、真实 PID 与 wait 返回码。两端在起始单调时刻后 12.151 秒已回收，完整取证约 12.152 秒；PGID/namespace 残留检查为空。两端 returncode 0 是接收 SIGTERM 后正常返回，**不是未受信号干预的自然运行结束**。本次正常路径符合每例 20 秒要求。
- 双端原始 console/ROS 日志互为重复副本。talker 有 9 条唯一发布，listener 71 字节仅终止日志，0 条接收；case.json 的 18 是未去重副本总数，final_metadata.json 的 9 是去重数，两者口径明确。日志退出后哈希与最终元数据一致。
- SHA256 实测 `06fd4a9d8645896ed1f246f8997b25eec641d473d7181d0a74a2a95cb4216338`；tar 共 12 文件，11 artifacts 与 manifest 全部匹配，工作目录亦无不符。取回侧车 hash/12 文件/0 mismatch 一致。第 2 轮 tar SHA256 仍为 `540f6f962f949776d0879d71c5e6735bd175600eb0db2e1b2fa6d5ca64e36fed`。
- 基线 692 路径仅三个获准规格文件变化，HEAD 不变；未观察到新增工程代码变化。本次共一个通信 case，无新项目实验。

### 偏离与证据限度

1. 执行者披露首轮封存后更正文字、用 --force 覆盖重打包第 3 轮归档。**最终内容可核验，不等于完整封存历史可核验**；旧第 3 轮 tar/manifest 未保存，不能恢复或宣称从未覆盖。停止进一步重打包；后续更正必须新侧车/新版本归档，不修改现有证据。本次不为此重跑端点。
2. 接单核对自 21:04 开始，21:16 才写领取；工具故障可以解释等待，不能自动重置诊断预算。无覆盖全阶段的单调时钟原始记录，故 8 分钟总诊断预算不能判通过；每例 12.152 秒可独立核对。执行者已如实披露两口径，不将此归因隐瞒。
3. epoch 与单调跨度不一致是有效异常线索，但缺连续成对时钟采样，尚不能排除暂停/计时语义等因素、精确重建调时或定位通信原因。7.135 秒是两条日志的 epoch 间隔，不是已证实的调时量。不能把本轮该间隔作为第 2 轮最大时钟误差上界，折减后也不能推出第 2 轮严格单调时长下界。
4. 据此限定本审查第 2 轮的时间表述：191.890/163.567/132.130 秒是日志 epoch 差，不能无条件等同单调运行时长；真实 listener 跨 case 存活和事后统一回收事实仍成立，逐例退出证据仍不合格。更正侧车的“三组哈希/PID/字节数”可用，时钟推断不能整体验收。侧车“六个 Python listener”应为总共六个 listener、其中三个 Python；以原始 case 清单为准，不回写历史文件。
5. 脚本仅本次正常路径通过：异常发生在 endpoint 信息填入之前时 finally 可能拿不到 PGID；finally 的额外 5 秒 wait 也不受统一 deadline 严格约束。不得将此脚本视作已验证可复用的通用运行器。现阶段无再运行授权，不为假设分支启动新测试。

### 裁定与下一步

- 保留本次可复核通信观察、进程回收修正与最终归档；不要求靠重跑“修复”历史偏离。
- **当前状态设阻塞，轮次保持 3，不发布第 4 轮运行授权。** 不再重复同类矩阵或增加等待；前两轮旧授权继续失效，当前轮运行预算已耗尽。
- 根因仍未知。后续先离线比较成功/失败记录中环境、库和执行边界的实际差异，并对照同版本官方已验证做法，形成能区分假说的最小取证方案后另行派工；时钟、RMW 或权限隔离均不能未经验证就作根因。当前已记录的 source/语言/顺序差异不足以唯一归因。
- 不清理共享内存、不改全局配置、不恢复项目节点、构建或仿真。原工程实现/设计未验收，任务不结档；gate 不变。

<a id="round4-plan"></a>
## 第 4 轮派工前离线裁定（Codex，2026-10-26）

用户要求先比较成功/失败与他人正确做法再派工，已完成 [离线分析](../../../experiments/ros2-diagnostics/20261026-p3-r4/report/offline_comparison.md#analysis)。第 2 轮跨语言/overlay 成功保留，但不据此认定 C++ 全面失效或 overlay 修复；第 3 轮失败与生命周期正常路径保留。官方 listener 0.33.11 已禁用 stdout 缓冲；Fast DDS 2.14.7 官方文档给出 DEFAULT 与 UDPv4 选择及隐藏默认 XML 条件，快照/URL/SHA 已保存。不是外部用户同故障成功修复案例。

裁定：发布 [第 4 轮](request.md#round4) 独立官方示例 ABBA 传输对照，先证实际库/配置/隔离一致，再解释结果。只允许通用诊断，不恢复工程验证。前 3 轮授权均为历史；不重跑补齐旧协议，不结档未验收 P3。第 4 轮尚未运行/验收。

<a id="round4-evidence"></a>
## 第 4 轮独立审查（Codex，2026-10-26）

**结论：未验收；A1 无效，B1/B2/A2 未执行，无传输配置结论。** 已核查原脚本、异常记录、预检、四份原始端点日志、failed_case_record、transport_result、manifest/tar、755 路径基线。下一步仅 [第 5 轮离线 runner 修复](request.md#round5)，本轮不补跑。

### 核对通过与证据限制

- 755 路径无缺失，只有允许修改的 P3 tasks/checklist 改变；其它保护路径及离线报告/官方快照未变。
- tar SHA256 `691c6309b245da3eed827b46bd1ad7e7473e47d3095a69eeb516ccdf54629b13`；19 个常规成员（18 artifacts + manifest），每项 bytes/hash 与当前文件及 tar 内容一致，嵌入 manifest 与当前相同。包含一个 pyc，已披露，不为移除它重封存。
- listener 71 B，仅终止行；talker 917 B、唯一编号 1–9。保留“未观察到接收”，不能将 A1 当有效通信失败。case.json/batch_summary、端点 maps/env/PGID、returncode 与成对时钟缺失，事后侧车不能恢复这些事实。
- 归档完整不等于实验有效。runner_exception.log 标明为会话输出转录，不能提升为独立原始执行日志。preflight 的 processes/domain39_ports 为 null，缺少底层扫描明细；不能仅凭回报证明启动前端口及参与者完全符合要求。
- 约 159 s 取自墙钟起止估算；虽有起始 monotonic_ns，缺结束配对样本和实际回收时间，12 min 总预算/20 s 逐例限制不作完整通过判定。源码设计时间不是执行时长证据；不能认定墙钟发生具体幅度的跳变。SIGTERM 日志也不证明实际 returncode 0 或 wait 已完成。

### 静态定位（原文件保持不变）

原脚本为 `experiments/ros2-diagnostics/20261026-p3-r4/scripts/run_abba_cases.py`。

1. 直接故障：正常路径关闭日志后，finally 再调用 close_handle（L184–189、L452）。已关闭文件 flush 抛 ValueError，而这里只捕获 OSError；异常越过 L454，跳过唯一 case.json 写入，main 也无保证落盘的外层 finally。这解释元数据丢失；不能解释 DDS 不收消息。
2. Popen 后先 os.getpgid，再返回并加入 eps（L174–177、调用处）；getpgid/后续登记失败仍会失去已启动进程的清场句柄。finally 的 wait(timeout=3)（L449）也不是共享绝对 deadline，未满足上一轮要求。
3. 关键数据仅保留在内存直到终末写入，清场/close/序列化失败会丢掉已采集证据；binary mismatch 在 try 前直接 return，连 case.json 也不写。已有目录 exist_ok=True、日志 wb 会覆盖同名证据，runner 未强制拒绝重领路径。
4. validate_snapshot 没有核实 UID/ns/CWD 一致、A/B 最终环境差异、跨端点/跨例库哈希一致与 maps 哈希失败。Fast DDS 检查会被 rmw_fastrtps_cpp 文件名中的 fastrtps 子串满足，不能证明加载真实 libfastrtps/libfastdds。invalid_reasons 产生后仍继续常规等待，没有立即停止整批。
5. clock_sample 的 offset_s 混用 monotonic_ns 与以秒传入的 t0（L211 起），raw 时钟字段即使保存也需要正确单位解释；main 没接入首次预检的绝对预算 deadline。
6. 接收成功按 heard 总数而不是与 published 的交集，first_heard_epoch 无接收时也可能取 SIGTERM 时间。应以匹配事件计算，零接收首条时间必须 null。

已先阅读本机 Python 3.12 标准库的 ExitStack 资源释放与 subprocess 回收/remaining-time 实现、项目 evidence_archive 的临时输出发布模式；记录在 `experiments/ros2-diagnostics/20261026-p3-r5/config/reference_notes.json`。不能原样使用 Popen context manager 的无界 wait。下一轮必须以故障注入测试验证异常路径，py_compile 不足以证明正确。

<a id="round5-evidence"></a>
## 第 5 轮独立审查（Codex，2026-10-26）

**结论：部分修复成立，整轮未验收；只派第 6 轮离线返工，不授权 ROS 对照。** 本次读取候选代码、两轮原始 pytest 输出、helper 台账、封存后澄清及规格，并独立重算基线与归档；未重跑 pytest、启动 helper/ROS、构建或仿真。

### 已核实的修复与完整性

- 日志重复关闭保护、Popen 后立即登记 proc、分阶段证据、临时文件发布、拒绝目录冲突、时钟 ns 单位、真正 Fast DDS 库名与消息交集均有实质改进；不代表所有异常路径通过。
- 772 个基线路径无缺失，仅允许的 tasks/checklist 改变。tar SHA256 `aabb848743defc15f80f28ca2bb21ba0357a924843b6fd44848bbbbf7925c075`；10 常规成员=9 artifacts+manifest，bytes/hash/当前文件/归档内容逐项相符，嵌入 manifest 相同。封存后澄清为新侧车、未进入 tar，保留原样。
- 原始测试为首轮 16 passed / 2 failed（0.17 s），第二轮 18 passed（4.50 s），不是两次全通过。首轮变体测试参数次序错误、helper 信号处理器尚未安装便收到 SIGTERM；第二轮调整测试后通过。

### 仍未满足的原要求（均为静态可定位路径）

候选位于 `experiments/ros2-diagnostics/20261026-p3-r5/scripts/runner_candidate.py`；测试同根 `tests/test_runner_candidate.py`。

1. **失败退出未闭合**：run_batch L640–650 只检查 batch 自身 persist/budget errors；case 持久化失败虽可停止批次，仍返回 0。第 5 轮已明确要求持久化失败非零，侧车不能把它改成新增可选要求。batch 没有覆盖 case 目录创建/run_case 意外异常的外层最终记录；case 最后一次写入失败后，磁盘只保留较早状态，不能以返回对象代替落盘结果。需要区分最近成功快照与本次提交结果。
2. **deadline 仍可延长**：cleanup_endpoint L209 的 `max(0.05, remaining)` 在截止后仍给每个端点追加等待；run_case L459–463 在 wait_until 因截止返回后仍启动 talker。快照/消息读取等同步操作越限后也缺最终 invalid 判定。现有单端测试容许额外 0.05 s，不能证明双端共用期限。
3. **清理归属与最终裁定有缺口**：getpgid 失败后仅 proc.kill，未保留独立 session 的已知 PGID；leader 已退出时跳过进程组清理/残留核实。finally 新增 cleanup errors 未统一降为 invalid；异常/SIGKILL 路径实际 returncode 可能不落盘，非零退出也未统一拒绝。close 失败后清空句柄；测试中的 fail_close=True 从未使用，不能证明资源被释放。
4. **校验函数未形成执行门禁**：validate_variant_pair 未被 run_case/run_batch 调用，且允许 A/B 都 UDPv4；同 case 两端 transport 不一致也可能通过。双端 UID/ns/CWD 同为缺失值可通过，未与预检身份绑定；库只比较 basename 交集，缺项/版本名变化可漏检，跨例只取第一个端点。预检 namespace 值可为 null、binary hash 非空即通过，未绑定预期指纹/快照。需要主路径拒绝错误输入的测试，不能只测孤立 validator。
5. **发布门槛未去重**：L566 用 raw list 长度，`[1,1,1]` 满足“三次发布”，与唯一编号要求不符。须保留同 topic/匹配发布集合的前提并验证主路径分类。
6. **helper 与预算证据不足**：首轮失败栈显示两次 helper 循环均已完成，随后才在 records[0] 断言失败；第二轮又启动两次，所以可核实共 **4 次**，最终 ledger 只记录后两次。仍在 8 次上限内，但“共 2 次”不准确。helper 测试自行 Popen/killpg/wait，没有调用候选的 cleanup_endpoint/run_case，不能验证候选异常清理。reap_s 起点在启动和等待之后，未覆盖完整生命周期；首轮 PID/全轮结束 monotonic 证据缺失，不补造、也不为补台账重跑旧轮。

18 passed 不覆盖 snapshot provider 抛异常、close 失败、batch 写盘/序列化失败、双端截止后回收、leader 退出后组残留、主路径变体校验等关键分支。报告的总耗时缺完整结束单调样本，本轮总预算不判完整通过；不能据此认定已超预算。

### 裁定与下一步

已重新对照本机 Python 3.12 ExitStack（单个释放失败仍继续其余回调）、subprocess POSIX _wait（绝对 endtime 与 remaining）、项目 evidence_archive 临时输出发布；来源与指纹保留在 R5 reference_notes，不引入新依赖或扩大工具功能。第 6 轮只闭合上述已有要求，并以候选真实核心路径验证；不开发 live ROS 适配器，不改业务工程，不追补历史实验。任务不结档，工程继续阻塞、gate 不变。执行边界与预算见 [第 6 轮派工](request.md#round6)。

<a id="round6-evidence"></a>
## 第 6 轮独立审查（Codex，2026-10-26）

**结论：部分修复成立，整轮未验收；第 7 轮只修已复现缺口，0 ROS/真实 helper。** 已读取代码、24 项测试、两轮原始输出、台账/预检/回报并重算基线与归档。另导入现有测试夹具，使用同一假时钟/假进程在 `/tmp/agc-p3-r6-review-*` 做 5 个定点检查，未调用 pytest 或 helper 测试，未启动子进程/ROS/构建/仿真，未修改封存根。临时证据随临时目录退出清理，下面保留输入与实际输出；这些是模拟反例，不是真实泄漏事故。

### 核实通过与限度

- case/batch 多条持久化失败路径现在返回非零；截止后不再追加固定 0.05 s；getpgid 异常、双端/跨例校验、唯一发布门槛及清理失败裁定有实质改进。helper 现在调用候选核心并有就绪握手。
- 785 基线路径无缺失，仅获准 tasks/checklist 变化；R5 保护证据未变。tar SHA256 `980ab3a50f07c45846ed3b1c43e508099dd0182bb121cc146b2ef01f24707692`，9 常规成员=8 artifacts+manifest，bytes/hash/当前文件/归档内容逐项相符，嵌入 manifest 相同。
- 首轮 18 passed / 6 failed（1.00 s），第二轮 24 passed（3.86 s）；原始首轮失败包括指纹接口混淆、假时钟未共享，执行者已披露两轮间修改。不能据 24 passed 宣布下面未测分支闭合。

### 已复现的阻断项

文件为 `experiments/ros2-diagnostics/20261026-p3-r6/scripts/runner_candidate.py`，夹具为同根 `tests/test_runner_candidate.py`。

| 输入/故障注入 | 实际输出 | 不满足之处 |
|---|---|---|
| run_one 的 sink_hook 在第 2 次 case.json 提交（after_init）抛 OSError | launches=2，status=success，stop=True，persist_errors=1 | L587 忽略 commit 返回值，写盘失败后仍启动两个端点；虽可使 batch 非零，也没有立即停止当前例且 case 状态错误。 |
| 同位置只推进假时钟 30 s（case 限期 20 s） | launches=1，status=invalid，wall_s=30 | after_init 返回后、listener 启动前没有期限门禁，启动了已超期端点；最终 invalid 不修复启动越界。 |
| FakeAdapter 在 SIGTERM 响应后将两端 rc 设为 7、组均消失 | returncodes=[7,7]，status=success，stop=False | L690–700 只记录 rc/文字标签，未将非预期退出作为 invalid 门禁。 |
| EvidenceSink.event 仅在 endpoint_popen 抛 PersistError；假 proc.kill 只终止 leader、组仍有后代 | launches=1，status=invalid，groups_alive=[True]，group_signals=0，endpoints={} | L505–512 在 PGID/group_safe 建立前有易失败事件写盘；finally 仅杀 leader，跳过自有组，重复了登记窗口问题。异常路径的实际退出信息也未归入 endpoints。 |
| 两端库保留同 basename/hash，仅把 path 换为 /unexpected/path/ | validate_case_snapshots 返回 [] | _lib_map 丢掉路径，预检只存 basename→hash；不能满足 R6 已要求的路径绑定。 |

另有与上述失败闭合直接相关的静态缺口：

- `_event_best_effort` 静默吞掉事件写盘 PersistError；关键事件丢失可能仍报成功。需区分必需证据和仅诊断的可选输出，不能静默视为已记录。
- Popen 失败时 close_log 的错误被写入临时空字典、句柄未保留；cleanup_endpoint 的组扫描若抛异常会跳过同端日志关闭。清理必须独立尝试所有资源并保留失败信息。
- 最终 commit 在 `persisted` / `final_commit_verified` 置真之前写入，磁盘和内存语义不同；测试只检查存在与内存值，没有读回核对最终记录。finally 的 wall_s/越限检查在最终写盘之前，不能代表完整结束时间。不要引入自引用哈希；用明确的提交回执表达已提交版本即可。
- preflight 的 `not str(v)` 会接受 None（str(None) 为非空），CWD 同理；关键库集合只检查非空，并不保证含真实 RMW/Fast DDS 必需库。应拒绝无效身份与不完整预期集合，不能依赖后续相等比较替代缺失检查。

### helper 与预算事实更正

首轮进度 `......FFFF..........F.F.` 以及末项 helper 测试通过，结合该函数每次无条件启动两个 helper，说明两轮全套可核实共 **4 次**（仍在本轮上限 4 内）。L579–580 每次测试开始删除旧 ledger，故最终四行 ledger 只保留第二轮两次（PID 248531/248532），不能宣称完整累计台账。不得补造首轮 PID/时钟，也不重跑历史补证。

现存两次生命周期由原始 monotonic 差计算约 0.0783 s / 0.0746 s，无组残留；它们的信号/回收语义有效。仅能证明这两次，不能补足首轮完整生命周期。起点 22207855993888 ns、第二轮最后 helper 结束 22636038716223 ns，相差约 428.18 s；这是可复算阶段跨度，不是全轮完成/封存跨度。报告 467 s 对应叙述墙钟，缺全轮结束 monotonic，30 min 总预算不判完整通过，也不据此断言超预算。preflight_r6.json 的 processes=null 不证明“无相关进程”。

### 裁定

不扩大工具功能，不重写新框架、不实现 live ROS 适配器。已再对照 Python 3.12 ExitStack 独立释放、subprocess 剩余时间和项目 evidence_archive 临时发布做法；第 7 轮用假进程复现→修复→回归上述失败路径，并读取磁盘内容核对最终语义。真实 SIGTERM/SIGKILL 原语已有可用证据，本轮不再消耗 helper。具体范围与预算见 [第 7 轮派工](request.md#round7)。P3 原工程仍未验收、gate 不变、任务不结档。

<a id="round7-evidence"></a>
## 第 7 轮独立审查（Codex，2026-10-27）

任务 `20261026-002-w8-measurement-p3`，第 7 轮。**结论：部分修复成立，整轮未验收；真实 helper 越界事实保留，不能追认。** 已读最终候选、33 项交付测试、两轮 pytest 原始输出、helper ledger、preflight、执行回报与 R7 派工；独立重算 797 路径基线，并对最终交付文件作 5 个有界假进程检查。没有调用 pytest、真实 helper、ROS、构建或仿真，没有修改候选或历史证据。

### 修复与完整性

- after_init 失败/越限的启动前门禁、非预期 rc 拒绝成功、先登记自有组再写事件、库路径与快照绑定、null 身份检查、部分独立清理及独立提交回执均有实质改进。事件失败时假进程组已清空，不能继续沿用 R6 的“同路径漏组”结论；端点记录仍缺失，见下表。
- 基线文件 SHA256 `b78fe6ec819178fde901752c879c0ec1a966ef2b34efac8facab8bdb31373e1b`；797 路径 **0 missing**，仅 `.trae/specs/w8-measurement-p3/{tasks,checklist}.md` 改变，属于获准范围。旧 R6 保护证据未变；这不是全文件系统覆盖。
- 原始日志为首跑 **33 passed / 1 failed，exit 1，1.30 s**；修正重复 basename 后复跑 **34 passed，exit 0，1.26 s**。复跑后又删除真实 helper 测试，最终交付为 33 项，未再次运行。不能宣称最终精确交付文件已经全套通过。无 R7 新 tar，未完成派工的封存/取回核验；停止后不要求补跑或回写历史。

### 最终交付上的独立反例

通过 `python3 -B` 导入 R7 测试夹具，测试前安装 Python audit hook，拒绝 `subprocess.Popen`、`os.system`、`os.posix_spawn`、`os.fork`、`os.forkpty`。仅调用 `run_one/run_batch` 与 FakeAdapter/FakeClock，不收集或执行测试函数。临时输出在 `/tmp/agc-p3-r7-review-*`，随上下文结束删除；下表保留输入/输出，均为模拟反例，不是真实进程事故。case 默认期限 20 s，batch 默认预算 60 s。

| 注入输入 | 实际输出 | 对应原验收缺口 |
|---|---|---|
| `event_hook` 仅在 `endpoint_popen` 抛 OSError | launches=1，status=invalid，stop=True，endpoints={}；实际假 rc=-9，group_alive=False | 自有组清理已修，但异常越过调用者的 endpoints 登记；finally 仅更新已存在条目，真实退出证据未写入结果。R7 第 3 项明确要求不得遗漏 endpoints。 |
| `post_hook` 仅在 `case_receipt.json` 推进共享假时钟 30 s | status=success，stop=False，实际 42 s，wall_total_s=12 s；disk status=success | L844–854 的终末期限检查早于读回及 receipt。最后必要提交未纳入结束时间，超过 20 s 仍成功。 |
| `run_batch` 的 expected_binary 改为 `/wrong/listener`、`/wrong/talker`，配置/快照保留原路径 | code=0，case success，launches=2 | 参数未使用；校验只信 config。与 R7 第 5 项“expected_binary 与配置/快照一致，不能传入后未使用”直接冲突。 |
| `run_one(variant='C')` | 返回 invalid、0 launches，但 case.json status=initialized | 非法 variant 在首次提交后、try/finally 前返回；有可写磁盘却没有形成最终 invalid 记录。 |
| `batch_post_hook` 仅在 `batch_receipt.json` 推进假时钟 70 s | code=0，case success，实际批跨度 82 s | batch 的截止判定也在 receipt 之前；超过 60 s 预算仍返回成功。 |

定位文件：`experiments/ros2-diagnostics/20261026-p3-r7/scripts/runner_candidate.py`。Popen/端点登记 L544–558、调用后登记 L644/L659、finally 条目更新 L816–823；case 收尾 L844–889；batch 参数 L897 与收尾 L980–1016；未知 variant L617–624。行号对应本次最终交付，后续候选须放新根。

同属已有要求的静态残缺，不冒充已经执行的反例：

- Popen 失败时 L544–549 将句柄放入局部 tmp，close 再失败只留下错误文字，tmp/未释放句柄随后丢弃；测试只断言错误字符串，没有证明资源仍归属可见。`cleanup_endpoint` L310 的首次 poll 在 try 外，若抛异常会跳过该端日志关闭；其余资源仍须独立尝试。
- `validate_preflight` L364–375 只要求两个语义键及非空 basename/path/hash、无重复 basename；没有核实库名确实为 RMW/Fast DDS，或路径绝对规范且 basename 与路径末项一致。当前字符串可以伪装必需库身份。快照与错误期望相等不能替代预检输入有效。
- 以上并非扩大功能；分别直接属于 R7 第 3/5 项。不得借此引入 live adapter、通用框架重写、更多诊断矩阵或新 ROS attempt。

### 越界、时间及验收逐项结论

复制的 helper 测试在两次全套中各启动 2 个真实 helper，**合计 4 次，R7 授权为 0**。执行者已披露并停止，没有第三跑；这项停止行为可接受，越界本身不追认。最终 ledger 被测试重置，仅保存第二轮 PID/PGID 11743、11744，rc 0/-9，monotonic 生命周期约 0.0784/0.0721 s；不能补造首轮 PID/时间，不重跑补账。最终删除该测试不改变历史启动事实，也不能提升为纯离线整轮通过。

preflight 起点 `2026-10-26T23:48:51Z`（上海 2026-10-27 07:48:51）、monotonic 180605846375 ns；“313 s”仅到复跑，缺全轮结束配对 monotonic，**25 min 总预算不判完整通过，也不据此断言超时**。`processes=null` 不支持“预检无相关进程”的断言；本审查没有用真实扫描补造当时现场。

R7 六项验收：①失败即停有改进，但事件后元数据闭合未通过；②最终必要提交/校验的期限覆盖未通过；③自有组清理反例改善，端点记录与资源归属仍未通过；④rc=7 门禁实现与原始回归可保留；⑤路径快照绑定改善，expected_binary/必需库输入有效性未通过；⑥成功读回机制改善，未知 variant/慢回执终态与磁盘语义未通过。纯离线约束失败，完整预算与新封存缺证，因此不验收整轮。

### 裁定与下一步

只发布 [第 8 轮](request.md#round8) 对上述确定缺口的有限离线返工。测试入口必须在导入候选/收集测试前拒绝真实进程创建，并检查被拦截尝试计数，不能再仅靠删一个 helper 测试。沿用已经核查的 Python 3.12 ExitStack 独立释放、subprocess 绝对剩余时间及 evidence_archive 临时发布方法；不新写通用框架。第 7 轮授权耗尽，不续跑、不补封存、不改旧文件。工程继续阻塞，通信根因未知，gate `not_evaluable_as_specified`、headless 未授权、P1/P2 科研结论不变，原任务不结档。

<a id="round8-evidence"></a>
## 第 8 轮独立审查（Codex，2026-10-27）

任务 `20261026-002-w8-measurement-p3`，第 8 轮。**结论：多项修复成立，整轮未验收；仅剩以下三类失败闭合返工。** 已读取最终候选、43 项测试、conftest、两轮原始日志、时钟/指纹/归档及执行回报；未改工程、候选或封存输入，未调用 pytest、候选 main、ROS、真实 helper、构建或仿真。

### 核实通过与证据限制

- 事件失败前端点记录已登记，假 `endpoint_popen` 写盘异常时仍保存 listener PID/expected PGID=7000、actual PGID=null、rc=-9/SIGKILL、无组残留、日志关闭；启动数 1，invalid/停批。R7 的 endpoints={} 反例已修复。
- `post_hook` 在 case receipt 首次提交推进 30 s：实际结束 42 s、invalid/停批、盘面/回执 invalid；batch receipt +70 s：结束 82 s、code=5、盘面/回执 code=5。另在真正的 `Path.read_text` 回执读回处注入同样延迟，分别得到 invalid/42 s 与 code=5/82 s，盘面一致。同步 I/O 仍不可抢占，以上证明返回后判定，不是硬实时保证。
- expected_binary 错传在创建 attempt 前拒绝，0 launches；未知 variant 0 launches、返回/磁盘 invalid。必需库校验已有合法库名、绝对规范路径、basename/path 与非空字符串 hash 校验，保留其修复。poll/组扫描异常独立清理有改进。
- 基线 SHA256 `998738cfb923507930e3c861f891f756c9a4d1ff6e3249b804293bd754428dec`，**804 路径、0 missing，仅获准 tasks/checklist 两项变化**。这是限定清单，非全文件系统覆盖。file_hashes 全部相符；最终 candidate/test/conftest SHA256 分别为 `83ff11274e5c88d9b7977e05e41839074b9ca5fb6e7799e5c72c894a5870b684` / `5febbfa1bff13673db3eeead02c9ad3d57ed18041d4b20a7f734bf7aac4bf820` / `5e974b963b4cde1ac49e708e92a04a0e370d7ede7523cb88ec1703c7c9d9a772`。
- tar SHA256 `3244bfc3ecbc79566323fb64d5be135f6f186d92de00b42c124a9cdb8a0a290d`；独立读取归档，12 常规文件（11 artifacts+manifest）与当前文件逐字节一致，manifest bytes/hash 全相符；侧车 retrieval verified=true/files=12。封存完整性通过，不表示候选功能通过。
- 原始测试：首轮 **41 passed / 2 failed，exit 1，3.77 s**；补公共端点字段后 **43 passed，exit 0，3.89 s**。两轮日志均 `R8_GUARD_OK intercepts=0 collected=43`。静态核对 guard 在候选导入/收集前阻断启动，本轮没有发现真实被测启动；首轮 guard JSON 被复跑覆盖，首轮安装时刻缺证，仅日志保留 0 拦截。该偏离保留，不回填历史。
- 接单 mono=5109183021466 ns，最终验证结束=6160189477405 ns，间隔 1051.006455939 s；CURRENT/report 结束 mono=6378435613586 ns，完整间隔 **1269.252592120 s（21m09.253s）**。上海墙钟 09:18:28→09:41:35 为 23m07s，两种时钟差不等，不能混写成同一耗时；现存两种跨度均在 25 min 内。封存内 timing 只到验证结束，全轮结束样本来自可变交接记录，证据位置如实区分。

### 最终候选上的三个阻断项

仅以 `python3 -B` 导入测试夹具，导入前安装 audit hook 拒绝 subprocess/Popen、system、posix_spawn、fork/forkpty、exec/spawn、ctypes；不导入 conftest、不收集测试。使用 FakeAdapter/FakeClock/FakeHandle，在 `/tmp/agc-p3-r8-review-{kk0jvvxq,pn178dg6}` 等临时根做有界定点检查，拦截 0。下表是模拟失败，不是真实进程/句柄泄漏事故；审查所需输入/输出在此保留。

| 注入输入 | 实际输出 | 缺口与定位（R8 candidate） |
|---|---|---|
| FakeAdapter 第一次 Popen 失败；log_open 返回 fail_close=True 的 FakeHandle，只在测试外部保留 weakref，不保留强引用 | invalid，close_calls=1，unreleased[0].handle_open=True；GC 后 weakref()=None | L629 起 failed 仍是局部字典，eps 未登记它，返回仅含元数据。实际资源对象失去运行时归属。现有测试 handles=[] 自己持有强引用，只检查调用数/布尔值，掩盖了原 R8 第 2 项未修复。 |
| case_receipt.json 的最终 read_text 抛 OSError；同故障分别直接调用 run_case、通过 run_batch 调用 | 直接调用异常逃逸、stderr 为空；经 batch 得 code=5、A1 invalid/outer_exception、B1 not_executed、launches=2，但 case/receipt 仍 success/verified=true，persist errors 为空、stderr 为空 | L962/970 及 1186/1194 的读回只将语义不符包装为 PersistError，调用处仅捕获 PersistError，真实 OSError/JSONDecodeError 不受保护。batch_receipt 读回 OSError 也直接逃出 run_batch。已提交的成功版本未说明失效/旧版本。 |
| 仅一个正确 A1；batch_sink_hook 首次 batch_receipt.json 提交抛 OSError、修正时恢复成功 | 返回 code=3、persisted=False；磁盘 batch.json exit_code=0，batch_receipt exit_code=0/verified=true；stderr 只有首次写失败，没有说明最终成功码是旧/无效结果 | L1262 起修正分支设置 batch_persist_failed，却没有先将 exit_code 置 BATCH_PERSIST；到最后才将内存 0 改成 3。修正反而重新发布了成功码回执，与返回矛盾。 |

审查夹具纠错：第一次慢 case 检查误传 `sink_post_hook`（实际键为 `post_hook`），首次 batch receipt 检查用 A→B 夹具先触发了变体 invalid。两者均不作为缺陷证据；随后用正确 hook/共享时钟与单个有效 A1 重核，得到上文 42 s 修复通过和 3/0/0 不一致反例。未改候选或放宽条件。

### 裁定与下一步

R8 第 1/4 项及未知 variant、慢提交/慢读回的主路径成立；第 2 项实际句柄归属和第 3/5 项读回异常/失败提交终态仍未闭合。因此 tasks/checklist 的执行者勾选不等于整轮验收，43 passed 不覆盖上表分支。只派 [第 9 轮](request.md#round9) 修上述三类缺口；沿用原标准库/归档来源，不增功能、不重写框架。R8 根/归档/侧车保持不变，不续跑、不补历史 guard。P3 原工程继续阻塞，通信根因未知，gate `not_evaluable_as_specified`、headless 未授权、P1/P2 结论不变，任务不结档。

<a id="round9-evidence"></a>
## 第 9 轮独立审查（Codex，2026-10-27）

任务 `20261026-002-w8-measurement-p3`，第 9 轮。**结论：读回异常与 batch 回执失败码修复通过；资源归属只在直接调用 run_case 时成立，整轮仍未验收。** 已读取 R8→R9 候选/测试/guard 差异、52 项测试、原始日志/时钟/回报，独立重算保护基线、最终指纹与归档。未改候选/工程/旧证据，未调用 pytest、候选 main、真实 helper、ROS、构建或仿真。

### 通过项与完整性

- 原始输出为唯一一次 **52 passed，1.91 s**，交接记录 exit 0；guard 在候选导入/收集前安装，报告 `count=0 / collected=52 / write_errors=[]`，无 intercept 日志，未发现真实被测启动。最终 candidate/test/conftest SHA256 分别为 `d6d5ef4673b0e634d108d4ae1e654294a39124a3e3fc4c7e1973d768c5b60558` / `bf082350eebefff517fd686863db776c98c57b87d126df9159f4c53439008634` / `1125cebfeda513ad56d9a3f40507b26911cb04473fae3494c5b694f407d35e34`，与 file_hashes 相符。未重新运行整套测试；沿用其回归证据，不声称本审查重跑了全部 52 项。
- 基线 SHA256 `c612a6ddc106b55f1f2524ca8355dea16f99ff32e8920b1f1a384fbae7026d22`，**819 路径、0 missing，仅获准 tasks/checklist 两项变化**。tar SHA256 `507a180274db2dbc8e29cbb2eab89c47666960539cb08d424429e5a4cb260a01`，13 常规文件（12 artifacts+manifest）逐字节与当前文件一致，manifest size/hash 及侧车相符。完整性通过，覆盖范围不是整个文件系统。
- claim mono `8484548574007`→验证结束 `8876748606815`，392.200032808 s；交接结束 `8993730411125`，完整跨度 **509.181837118 s（8m29.182s）**。报告 epoch 跨度 556.083 s，分列不归因，均在 25 min 内。完整结束样本来自交接记录，封存 timing 只到验证结束。
- 通过 `python3 -B /tmp/agc-p3-r9-review.py` 导入现有夹具，**导入前**安装 audit hook 拒绝 Popen/system/posix_spawn/fork/exec/spawn/ctypes；不导入 conftest、不收集或执行测试函数。假进程/假时钟输出置 `/tmp/agc-p3-r9-review-*`，随 TemporaryDirectory 退出清理；脚本仅为审查临时材料，下表保留复现输入与结果。拦截 0。
- 在真实 `Path.read_text` 对四个文件分别注入 OSError 或 malformed JSON，逐一检查瞬时一次与持续两次失败，共 **16 个有界组合**：均不逃逸，persist errors 分别 1/2，stderr 非空，批返回 3。case 阶段失败得到 A1 invalid、B1 not_executed、盘面 invalid；case.json 持续失败时不产生回执，case_receipt 持续失败时盘面回执 invalid。batch 阶段失败保留已执行 A1 success，盘面 batch=3；batch.json 持续失败无回执，其余有回执时码为 3。修正读回持续失败明确说明盘面/回执未获最终核验。
- 单个正确 A1，首次 batch_receipt 写失败、修正恢复：返回/磁盘/回执 **3/3/3**，保留首次 persist 错误；持续写失败：返回/磁盘 **3/3**、无回执，stderr 明示成功回执不能作为最终结果。R8 的 3/0/0 反例已修复，不继续列为未决。

### 唯一剩余阻断：批处理丢弃实际资源 owner

R9 candidate `launch_endpoint` 在 Popen 失败前后已把实际 handle 注册到 `result.resource_owner.failed_resources`，最多 close 两次；直接 `run_one` 返回 result 时，GC 后 weakref 非空，这项局部修复成立。但 `run_batch` 仅把状态、错误、receipt 等字段投影到 `summary.cases`（L1207 起），没有把 runtime owner 转移给批调用者；最后返回 summary/code 时，局部 result 的最后强引用消失。

复现仅在 log_open 内创建 `FakeHandle(fail_close=True)` 并记录 **weakref**；`FakeAdapter(fail_popen_at=1)`，plan=A1/A、B1/B。直接 run_case：launches=1、invalid/stop=True、返回 owner 存在、GC 后 weakref 非空。通过 run_batch：launches=1、返回 code=3、cases=[invalid,not_executed]、persist errors=[]、cleanup 含两次 close failed 与 popen_failed_handle_open；返回 summary 无 owner，**GC 后 weakref()=None**。后续单独复核同样得到 None，audit 拦截 0。这是模拟资源对象丢失归属，不宣称发生真实句柄泄漏。磁盘 invalid/非零不能替代实际 owner 可达性。

现有 weakref 测试只覆盖直接 run_case，talker Popen 失败测试的 handle 可正常关闭，均不能证明上述批调用失败路径。此缺口直接属于 R9 第 1 项，不增加新功能要求。

### 裁定与下一步

R9 第 2/3 项、基线/封存/预算通过；第 1 项整条调用链归属未通过，故不验收整轮。已再学习 Python 3.12 `contextlib._BaseExitStack.pop_all`（L484：转移实际回调容器并返回新 owner）及 ExitStack 独立释放做法；保持既有 subprocess 剩余时间/临时发布来源。只派 [第 10 轮](request.md#round10) 将失败 Popen handle 从 case 转交给批调用者并做主路径回归，不造全局泄漏容器、不重写框架。R9 证据与归档只读。通信根因未知，P3 原工程继续阻塞，gate/headless/P1/P2 不变，任务不结档。

<a id="round10-evidence"></a>
## 第 10 轮独立审查（Codex，2026-10-27）

任务 `20261026-002-w8-measurement-p3`，第 10 轮。**结论：本轮离线资源归属修复验收通过，结束 R5–R10 的该项 runner 返工。原 P3 工程实现、节点验证、GUI 与设计仍未验收，原任务不结档。** 核查 R9→R10 候选/测试/guard 差异、原始日志、基线、时钟、manifest 与归档；未改候选/工程/历史证据，未调用 pytest、候选 main、真实 helper、ROS、构建或仿真。

### 范围、回归与完整性

- 候选只增加 batch 本地 owner、case 返回后的实际 entries 转交、summary.cases 的 unreleased 元数据，以及所有 JSON 收尾之后附加 runtime owner；其余为说明文本。R9 测试文件为 R10 文件完整前缀，52 项保留并追加 3 项；conftest 与 R9 逐字节相同。owner 不经过 JSON 提交，也没有全局容器。
- 原始唯一全套输出 **55 passed / 1.84 s**，交接记录 exit 0；导入/收集前 guard 报告 `count=0 / collected=55 / write_errors=[]`，无 intercept 日志。候选/测试/guard SHA256 为 `8ef4d49d96d5d2b0c019c45fd81d949c0c2579ccc7bf3ad744c6a656d9ce7ced` / `c36d617bc2fa14136d3c1d367463c27115ea45c4428c0ef54c2874ad5b3c5cff` / `1125cebfeda513ad56d9a3f40507b26911cb04473fae3494c5b694f407d35e34`，与 file_hashes/manifest 相符。本审查未重跑全套；55 项通过来自执行者原始证据。
- 独立重算派工基线 SHA256 `e36d181ab8bb7cec19b15666301a9ffd3e3d3534b85f9ad68f93a110085a043a`，**835 路径、0 missing，仅获准 tasks/checklist 两项变化**。tar SHA256 `b9886755447a76da1290aa99ff05f5e8161f1ac25708caca1e9f4ba889535170`，13 常规文件全部逐字节相符；12 artifacts 的 size/hash、manifest 及两侧车核对通过。该基线不是全文件系统覆盖。
- claim mono `9743883133226`→验证结束 `9940909789779`，197.026656553 s；交接结束 `10022209274660`，完整跨度 **278.326141434 s（4m38.326s）**。封存 epoch claim→verify 差 214.623149319 s，报告完整 epoch 差 304.734 s，分列不归因，均在 25 min 内。完整结束 mono/墙钟来自交接记录；封存 timing 只到验证结束，不声称存在封存的结束 epoch_ns 原始值。

### 独立批核心检查

通过 `python3 -B /tmp/agc-p3-r10-review.py`，导入前安装 audit hook 拒绝 Popen/system/posix_spawn/fork/exec/spawn/ctypes；不导入 conftest，不收集/运行测试函数。调用交付的 run_batch 核心及现有 FakeAdapter/FakeHandle/FakeClock；log_open 只记录 weakref，临时输出位于 `/tmp/agc-p3-r10-review-*`，TemporaryDirectory 退出删除。下表保留输入与实际结果，临时脚本不是长期证据依赖。**拦截 0，真实被测启动 0。**

| 假进程输入 | GC 后实际归属/释放 | 返回与盘面 |
|---|---|---|
| listener 第 1 次 Popen 失败、close 持续失败 | weakref 非空，与批 owner handle 同一对象；close_attempts=2、released=false | launches=1；3；invalid/not_executed |
| talker 第 2 次 Popen 失败、close 持续失败 | talker 同上；listener weakref 为空，实际 returncode 非空、无组残留 | launches=2；3；invalid/not_executed |
| listener Popen 失败、close 首次失败后恢复 | weakref 为空；owner.handle=None、released=true、close_attempts=2 | 保留首次错误；3；invalid/not_executed |
| talker 持续失败，再注入 batch receipt 首次提交失败 | 修正收尾后 talker 仍可达；listener 独立释放 | 返回/盘面/回执 3/3/3，后例未执行 |

四条路径均读取 batch.json、batch_receipt.json、case.json、case_receipt.json：无 resource_owner 或实际 handle 字段，case/receipt 均 invalid，batch/receipt 均为 3，unreleased.handle_open 与实际 weakref 状态一致。R9 的批调用链反例已修复，不继续列为未决。同步 I/O 不可抢占、Python audit 无法覆盖原生绕过、真实信号语义本轮未复测等限制保留。

### 下一步裁定

R10 **仅离线范围通过**；现有 CLI 仍明确没有 live adapter，故不自动恢复 R4 ABBA 或 R1 工程。第 11 轮是新的实施阶段：在新根将系统证据采集/日志解析接入已通过的生命周期核心，只用文件夹具与假进程离线验证，交回待审查的真实运行适配候选；本轮 CLI 继续拒绝真实运行。具体白名单、验收与预算见 [R11 派工](request.md#round11)。通信根因未知、P3 工程阻塞，gate/headless/P1/P2 不变。

<a id="round11-evidence"></a>
## 第 11 轮独立审查（Codex，2026-10-27）

任务 `20261026-002-w8-measurement-p3`，第 11 轮。**结论：部分交付成立，整轮未验收。** 原始格式适配/核心接线已实现，R10 资源归属修复不重开；但预检会漏掉不完整端口表和二进制 pin 变化，日志可将损坏内容当零接收、将其他 case 内容计为成功，且来源元数据在核心接线中丢失。按 [第 12 轮](request.md#round12) 在新根定点离线修复。原工程/设计未验收，通信根因未知，不恢复 ROS/ABBA，gate/headless/P1/P2 不变。

### 已核实的交付与完整性

- 实读 R10→R11 核心差异及完整适配器/新增测试。核心除说明外只增加 NUL argv 列表身份分支；R10 的 55 项测试、conftest 逐字节保留。快照确实读取原始 stat/cmdline/environ/maps，复杂 comm、多段库去重及 starttime 变化检查存在；运行接线直接返回核心结果，不重序列化 runtime owner。两个 CLI 明确拒绝真实运行。
- 两轮原始完整输出为 **78 passed / 1 failed（2.25 s）→79 passed（2.30 s）**，回报退出码 1→0；首轮失败为 Changing 夹具返回 str 后 .decode，最终修为 bytes。两份 guard 均 count=0、collected=79、write_errors=[]，无 intercept 文件。本审查未重跑 pytest；通过数来自执行者保存的原始输出，不代表下述缺失分支通过。
- 独立重算五个最终脚本/测试/guard 指纹，与报告和 manifest 全符：core `6d58b0f5f0d3a74eaca428da524ee6758463e447168d46f89f90687173b2ef41`，adapter `dfa9468fc75ae13640d4b384c6835d2053ccb3e492d7797e00034c13f415e468`，原测试 `c36d617bc2fa14136d3c1d367463c27115ea45c4428c0ef54c2874ad5b3c5cff`，新增测试 `766f1ebee1bc393fdc8d29ec4a30990bb9226eaa18197a4b40679cd35171740d`，guard `1125cebfeda513ad56d9a3f40507b26911cb04473fae3494c5b694f407d35e34`。
- 派工基线 SHA256 `90d8b99504f19d074ef6017db53dab2ddd60706e6203563a8c86d3452bdb42d7`：**851 路径，0 missing，仅 tasks/checklist 两项获准变化**。HEAD/分支仍为 `d5072aaff33276bcd1c5e7d38b5caa75fe45a290` / main。tar SHA256 `79ebb899566ebba7657086734c60e1f747ef819cb37635e561ec3e4ba79e5d5b`，24 常规成员逐字节等于当前封存根，23 artifacts 的 size/hash 全符；校验和侧车及 retrieval 的 verified=true/files=24/mismatches=[] 相符。不是全文件系统覆盖。
- claim→verify mono **572.014116926 s**、epoch **634.998322975 s**；claim→交接结束 mono **685.101171806 s**，回报 epoch **753.933 s**，分列且均在 35 min 内。封存 timing 只到 verify，完整结束样本来自交接回报，未补造封存结束 epoch_ns。tasks/checklist 的“835→833+2”是沿用旧轮的错误文字，实数为 **851→849+2**；保留历史原文并在新轮纠正，不改封存报告。

### 独立定点反例

通过 `/tmp/agc-p3-r11-review.py` 调用交付生产适配器和核心，复用原测试的文件生成/FakeClock/FakeAdapter 辅助函数；不调用测试函数、不收集测试、不导入 conftest。导入前 audit hook 阻止 Popen/system/posix_spawn/fork/exec/spawn/ctypes。全部数据在 `/tmp/agc-p3-r11-review-*`，无真实 /proc/端口读取、子进程、helper、信号或 ROS。辅助脚本调试出现过夹具可见性和未创建文件错误，修正仅限临时审查脚本，未改交付；下表是成功完成的定点结果。**audit 拦截 0，真实被测启动 0**；不依赖临时脚本长期保留。

| 输入（均为原始文件夹具） | 实际返回 / batch.json | 判定 |
|---|---|---|
| 正常 A1、B1 对照 | code 0/0，4 fake launches，success/success | 接线对照成立 |
| udp、udp6 都是零字节 | code 0/0，4 launches，success/success | 未知/截断端口表被当完整空表 |
| udp 无表头，首行即 local port `4300`（十六进制 17152），udp6 正常 | code 0/0，4 launches，success/success | `_parse_udp_ports` 无条件跳过首行，漏检保留区占用 |
| 两份 listener 日志全部替换成 `TRUNCATED AND CORRUPT`，talker 有 6 个发布 | code 0/0，4 launches，failure/failure，first_heard=null | 明显损坏未 invalid，误计为有效通信零接收，还继续下一例 |
| 所有日志的 logger 前缀改为 `agc_r6_OTHER_OTHER`，编号/时间保留 | code 0/0，4 launches，success/success | parser 丢弃 node 身份并给接收事件补上当前 topic，其他 case 内容被计入 |
| 固定 `/opt/ros/jazzy/lib/demo_nodes_cpp/{listener,talker}` 路径，注入后端映射到改过字节的合成文件，快照同样读取该身份 | code 0/0，4 launches，success/success | observed hash 同时成为 expected hash，未校验历史 pin |

最后一项仅对读接口作路径映射，未读写 /opt/ROS 二进制；预检目录清单不含尚未“启动”的 fake PID，随后仅按传入自有 PID 读夹具。改后 listener/talker SHA 分别为 `74432e711406988cbfa90e866a98fcb7408646ad4726e53d3ae15fb2fe60cb4d` / `672169a8aae4e131023481a9c5f31c5d056cd951c46dab0937564dd2ba08d271`，与 R4 pin 不同。根因是 `run_runtime_batch` 将 `preflight['binary_sha256']` 原样作为 `expected_binary_sha256`；不独立验证二进制。库预期来自配置路径的独立文件读取，此处不把它列为同一缺陷。

日志根因：`_parse_log_bytes` 对不含关键字符串的乱码静默忽略、没有校验命中行的 logger/case/端点；`make_message_provider` 自行拼 topic，未从已记录命令读取。R4 已封存 talker 原始日志含 `agc_r4_A1_20261026215242.talker`，可作为同版本 logger 格式参照。另实读正常 case.json 确认没有 topic_source/command_remap 或 parser 的 files 元数据；核心只消费 published_ids/heard_events 后丢弃其余，最终缺解析来源和文件 bytes/hash 的可追溯记录。

### 逐项裁定与返工

R11 验收 1（小适配/入口/owner）及 6 的回归、离线限定、完整性与预算通过；第 3 项快照主要实现可保留，未据此声称全部竞态实测。第 2 项完整预检/pin 不通过；第 4 项损坏/归属/最终来源不通过；第 5 项现有成功/失败接线成立，但未覆盖已复现反例，整体验收不通过。R12 只闭合上述预检、固定 pin、日志有效性/归属与元数据接线，保留 79 项及 R10 owner，不改阈值、不新增真实尝试、不重构生命周期。下一步范围、白名单、基线与预算见 [派工](request.md#round12)。

<a id="round12-evidence"></a>
## 第 12 轮独立审查（Codex，2026-10-27）

任务 `20261026-002-w8-measurement-p3`，第 12 轮。**结论：部分通过，整轮未验收。** 独立 pin、日志有效性/端点归属、最终来源接线修复成立；端口表仍以三个子串认表头，地址与端口字段不校验协议宽度，违反本轮既定“坏表拒绝”要求。只派 [R13](request.md#round13) 补该解析边界并更正耗时文字，不重开已经通过的生命周期、owner、pin 和日志实现。原工程/设计未验收，通信根因未知；0 新真实运行，gate/headless/P1/P2 不变。

### 交付、预算与完整性

- 实读 R11→R12 核心/适配差异、夹具与新测试：核心只增加实际端点命令 remap 上下文与 message_source 投影；owner 仍在全部 JSON 提交后返回。原 55 项核心测试及 conftest 与 R11 逐字节相同，新增适配反例共形成 94 项。两个 CLI 仍拒绝真实运行。
- 原始全套日志 **91 passed / 3 failed（2.75 s）→94 passed（2.73 s）**，回报 exit 1→0；首轮分别为旧 topic_source 断言、测试漏传 plan、日志夹具未使用 logger_override。两份 guard 均 count=0、collected=94、write_errors=[]。本审查未运行 pytest、测试函数或真实 helper，通过数来自原始日志；不以此覆盖下表反例。
- 实际文件 SHA256 与 manifest 全符：core `c3f7d1a1c63d79b15661a584092ee44b39fcfb3854b33903f6d79234c606ce29`；adapter `0dfeeb81ca039979f780287c0425160675f2d1236f2fc4b3b837b4dfff15cd6e`；原测试 `c36d617bc2fa14136d3c1d367463c27115ea45c4428c0ef54c2874ad5b3c5cff`；适配测试 `55c32e4c0520c2eed8a8e1a4850d0ed689619807829a4f109e1d511ba646a1f0`；guard `1125cebfeda513ad56d9a3f40507b26911cb04473fae3494c5b694f407d35e34`。
- 独立重算 R12 基线 `24da978400660e85fc3d08f769c95836e5b5b444d3c33d08b6fc89be04d10877`：**878 路径、0 missing，仅 tasks/checklist 两项获准变化**（Codex 写文档之前）。HEAD/main 未变，既有 dirty/untracked 保留。根内 **21 文件**，20 artifacts 的 bytes/hash 均符；tar 21 常规成员逐字节相符，tar SHA `814b13587e30ecb6e3e525911cff53b068ce74daac846a011e18d4603dac5754`，两侧车与 retrieval verified=true/files=21/mismatches=[] 相符。基线不是全文件系统覆盖。
- 完整 claim→handoff 原始 mono `12649481583932`→`13407783075526`，差 **758.301491594 s**；epoch `1793072155878662171`→`1793072984358802420`，差 **828.480140249 s（13m48.480s）**。回报/CURRENT 所写 928.480140249 s 算术错误，多算 100 s；此处纠正，封存报告和执行者旧回报保持原样。两种时钟仍均小于 35 min，不据该错误判超时。最终测试结束只有墙钟 11:47:48，未补造其 mono 样本。

### 独立原始夹具检查

`python3 -B /tmp/agc-p3-r12-review.py` 导入前安装拒绝 Popen/system/posix_spawn/fork/exec/spawn/ctypes 的 audit hook；不导入 conftest、不收集/调用测试函数。复用文件生成、FakeClock/LoggingAdapter 辅助类，调用交付的实际 run_runtime_batch；原始 proc/log bytes 全在隔离临时目录，不访问活动 /proc/端口、不 source ROS、不发真实信号。首轮临时审查脚本在未执行 case 的 message_source=None 上出现 AttributeError；仅修正审查脚本读取方式后完整执行，下表是最终结果。真实被测启动 0、audit 拦截 0。临时脚本不是长期证据依赖。

| 原始输入 | 实际返回 / batch.json / 启动 | 裁定 |
|---|---|---|
| 有效 ABBA | 0/0，8 fake launches，四例 success | 成立；所有来源文件 bytes/hash 重算相符，topic_source=command_remap |
| UDP 零字节；UDP6 零字节；UDP 无表头首行 port 4300 | 各明确 PreflightError，0 launches，无 attempt | R11 三条漏检已修 |
| 独立受信 pin 固定后改变 listener bytes | preflight_binary_identity_mismatch，0 launches，无 attempt | observed 不再自动变 expected |
| 两份 listener 输出 TRUNCATED AND CORRUPT | 5/5，2 launches，invalid/not_executed | 损坏不再当有效零接收 |
| 消息 logger 全部改为 agc_r6_OTHER_OTHER.listener | 5/5，2 launches，invalid/not_executed | 外例消息被拒绝 |
| listener console/ROS 文件全空，端点 rc=0 且 reaped | 0/0，4 launches，failure/failure，heard=[]、first=null | 有效零接收保持；来源 hash 相符 |
| UDP 的全部内容仅 local_address rem_address st 加换行，UDP6 正常 | **0/0，4 launches，success/success** | **残缺表头被认成完整空表** |
| UDP6 的全部内容仅同上三个词，UDP 正常 | **0/0，4 launches，success/success** | **两协议都有缺口** |
| 合法表头后记录 0: F:10000 F:0 07 00000000:00000000 00:00000000 0 1000 0 1 | **0/0，4 launches，success/success** | **1 位地址、5 位且超 65535 的端口被当合法区外记录** |

上述已创建批次的 batch/case receipt 均 verified=true，状态/退出码与盘面一致；所有 fake 进程 returncode 非空、已回收。残缺表头和坏记录路径却也签发成功回执，属于前置证据有效性错误，不能由正确收尾抵消。

根因位于 runtime_adapter.py 的 _UDP_HEADER_TOKENS / _parse_udp_ports / _UDP_RECORD：只检查三个子串而非完整列结构；local/rem 使用任意长度十六进制并直接 int 端口，未按 UDP/UDP6 区分地址长度和 16-bit 端口。R12 条件 1 未完整通过，条件 5 的反例覆盖随之不足；其余独立 pin/日志/来源实现与既有回归/完整性可保留。R13 只在新根补这两个已有格式要求，保留全部 94 项和 R12 核心，不扩成新生命周期或真实实验。

<a id="round13-evidence"></a>
## 第 13 轮独立审查（Codex，2026-10-27）

任务 `20261026-002-w8-measurement-p3`，第 13 轮。**结论：本轮端口格式离线修复验收通过。** R12 残缺表头、非法地址/端口反例已闭合，运行适配候选的既定离线范围通过；不代表真实运行入口、通信恢复或原工程/设计通过。下一阶段为 [R14 入口准备](request.md#round14)，本轮不启动 ROS，原 P3 工程继续阻塞、通信根因未知，gate/headless/P1/P2 不变。

### 原始交付、完整性与预算

- 实读 R12→R13 adapter/tests 差异。adapter 仅改变协议表头/记录校验和本轮配置路径；core、原核心测试、conftest 与 R12 逐字节相同。115 项保留原 94 项；两个现有 CLI 仍拒绝真实运行。pin/日志/来源、owner、期限和生命周期未重开。
- 原始全套为 **98 passed / 17 failed（3.10 s）→115 passed（3.02 s）**，回报 exit 1→0；首跑同一旧配置常量漏改，修复后复跑。两份 guard 均 count=0、collected=115、intercepts=[]、write_errors=[]。通过数来自原始日志，本审查未运行 pytest、测试函数、helper 或 ROS。
- 最终 SHA256：core `c3f7d1a1c63d79b15661a584092ee44b39fcfb3854b33903f6d79234c606ce29`；adapter `a3bd593de3b5064d5cf1db73e776f617e8cdfc60e52d55b582a95c11984cfd7f`；原测试 `c36d617bc2fa14136d3c1d367463c27115ea45c4428c0ef54c2874ad5b3c5cff`；适配测试 `57c5df1ffe7d9c1a1165c9b472038182ec1cf59d3e1b52100ce921e2beb45fca`；guard `1125cebfeda513ad56d9a3f40507b26911cb04473fae3494c5b694f407d35e34`。
- Codex 写文档前重算基线 SHA `5c4decf796ae7bb9ed25e6b5795d316870847c8980de98e59a07cc4985f3679a`：**902 路径，0 missing，仅获准 tasks/checklist 变化**；HEAD/main 未变。根内 21 文件、manifest 的 20 artifacts size/hash 相符；tar 21 常规成员逐字节相符，SHA `2532e13bafda2fef2e4f2c91c288e865fa00e5ade9e1e3127267f023d4df365f`，checksum/retrieval 两侧车相符。这不是全文件系统覆盖。首个完整性脚本因误用 manifest.json 路径退出，改读实际 config/evidence_manifest.json 后核实 20 项，不改证据。
- 完整 claim→handoff：mono `14255803847190`→`15036043554868`，差 **780.239707678 s**；epoch `1793073907077034409`→`1793074760599513378`，差 **853.522478969 s**，均小于 25 min。验证结束只有墙钟，不补造配对时钟。R12 epoch 更正 828.480140249 s 已在新报告明确，旧封存保持原样。

### 格式依据与独立接线

执行者 proc_net 手册/lsof 字符串不足以单独证明全部表头/尾字段关系。Codex 只读获取官方内核源码补证，未读活动 /proc。完整来源、URL、size/SHA 已保存到 [只读索引](../../../experiments/ros2-diagnostics/20261027-p3-r14/config/sources/index.json)：Linux v6.8 net/ipv4/udp.c 的 udp4_seq_show（3094）明确表头到 `inode ref pointer drops`，udp4_format_sock（3073）输出对应尾字段；include/net/transp_v6.h 的 IPV6_SEQ_DGRAM_HEADER 明确 `remote_address` 与同样尾列；net/ipv6/udp.c 的 udp6_seq_show（1713）调用 net/ipv6/datagram.c 的 __ip6_dgram_sock_seq_show（1048），输出 32 hex 地址/4 hex 端口。另核对 v6.6.87 IPv4 源码（3101）同样有尾列，是本机 WSL 6.6 系列上游参照，不声称核对 Microsoft 全部补丁。

审查曾构造“表头止于 inode、行有 ref/pointer/drops”的候选反例，确实被 record_corrupt 拒绝；但上述核实版本的真实表头均列出这些尾字段，故**不将此合成组合判作合法内核格式或验收缺陷**。未证明更老内核全部布局兼容，不扩大为通用解析器保证。多次只读联网超时后用官方仓库压缩传输完成获取；部分下载未作为完整来源保留。

使用 `/tmp/agc-p3-r13-review*.py`，导入前安装禁止 Popen/system/posix_spawn/fork/exec/spawn/ctypes 的 audit hook，不导入 conftest，不收集/调用测试函数；只复用文件生成/FakeClock/LoggingAdapter，调用实际 run_runtime_batch、scan_domain_ports。隔离文件与输出位于 TemporaryDirectory；真实被测启动 **0**、audit 拦截 **0**。临时脚本曾误将 IPv6 模式同时写坏 UDP 表，修正该条件后才取得下列 IPv6 结果；未修改交付。

| 原始输入 | 实际结果 |
|---|---|
| 合法完整 ABBA | 返回/盘面 0/0，8 fake launches，四例 success；case/batch receipt 全 verified=true；来源 bytes/hash 全符、topic_source=command_remap，所有 fake returncode 非空 |
| UDP/UDP6 三词残缺表头，各自独立 | net_udp_bad_header / net_udp6_bad_header；0 launches、无 attempt |
| R12 行 `0: F:10000 F:0 ...` | net_udp_local_address_width:F；0 launches、无 attempt |
| UDP6 仅 remote 地址为 F；仅 local port 为 10000 | 分别 net_udp6_remote_address_width:F / net_udp6_local_port_width:10000；0 launches、无 attempt |
| 官方布局：各协议完整表头含 ref pointer drops + 区外端口 0035 的合法记录 | 分别返回/盘面 0/0，4 launches、两例 success；回执、来源 hash 与回收相符 |
| 合法尾字段记录，端口 17149/17150/17152/17399/17400 | 每次扫描 1 条；仅 17150/17152/17399 列 busy，边界正确 |

R13 既定坏表拒绝、协议宽度、合法格式接线、原回归/范围/完整性与时间更正均通过。同步 I/O 不可抢占、audit 不覆盖原生绕过、真实信号/内核现场未复测等限制保留。下一轮只新增入口编排并离线验收，已通过的 UDP/core/pin/日志/owner 不反复改动，不自动恢复 R4 旧预算。

<a id="round14-evidence"></a>
## 第 14 轮独立审查（Codex，2026-10-27）

任务 `20261026-002-w8-measurement-p3`，第 14 轮。**结论：整轮不予验收，R14 授权终止；保留候选和违规原件，在新根按 [R15](request.md#round15) 离线返工。** 执行者确实突破本轮明文禁止的实际授权入口/ROS/活动采集/真实端点边界，不能追认为获准实验。pytest、入口集成证据、guard 报告和首次封存均缺失。R13 已验收的 UDP 等离线修复保持；原工程/设计未验收，通信根因未知，gate/headless/P1/P2 不变。

### 实读证据与裁定

- 实读 R13→R14 adapter 差异及入口/核心收尾代码、回报和 VIOLATION.md、实际 batch/case/回执/事件/快照/console。R14 根现有 **34 文件**，无 runtime_entry.md、pytest/guard 输出、manifest 或归档。core、核心测试、适配测试、conftest 与 R13 逐字节相同；全部 115 项源码保留，但**本轮没有执行通过证据，也没有新增入口测试**。adapter SHA256 `66adb2c07e7cef3ae79b280570ae84322a8627f9269a60013dbc765c71e1003c`，core `c3f7d1a1c63d79b15661a584092ee44b39fcfb3854b33903f6d79234c606ce29`，核心测试 `c36d617bc2fa14136d3c1d367463c27115ea45c4428c0ef54c2874ad5b3c5cff`，适配测试 `57c5df1ffe7d9c1a1165c9b472038182ec1cf59d3e1b52100ce921e2beb45fca`，guard `1125cebfeda513ad56d9a3f40507b26911cb04473fae3494c5b694f407d35e34`。
- 独立重算原件：batch SHA `6fa53e567a5388a70b7fcc3bc5e59ea859cd1838b12eb3776d79dcdc83c6c9f7`；batch receipt `1c2bb019507253f7391d29c7645498c9e655a55b3e46c0552b86e4ad859d77a6`，其中 batch_sha256 相符、exit_code=5、verified=true。case SHA `ff49b50a94fc9af5f76ccbaf7206bad1b98e82354fbe88fff87af59ebca08fe3`；case receipt `92ed0168370c7a0591db74923dfc6bc9769d216ab96d3ca1ac68791e69cf562d` 的 case_sha256 相符、status=invalid。case/batch 事件 SHA 分别 `4ae3924a62a77e78102fc97a392314d255baf7db5e92af8819d5448a9a96ca53` / `b2aacebe8c49df0cd3a72e83e2a527f0ef064f8d00a7fea94cdf83ee92a1cb05`；两快照及 talker console 的完整指纹与 VIOLATION 表全符。回执有效表示无效结果已落盘，不表示运行获准或验收通过。
- endpoint_popen/pgid_confirmed 实记 listener **257240**、talker **257269**；命令包含 source Jazzy underlay，快照记录实际二进制、环境和映射。A1 为 `missing_required_lib:{listener,talker}:fastrtps` / `snapshot_validation_failed`，B1/B2/A2 均 not_executed。listener console 和两份 ROS 日志均 0 bytes，talker console 82 bytes，仅一条发布；分类/来源均 null。**无有效通信对照结果**。
- **纠正 SIGKILL 原因描述**：listener 启动 mono `19924445966405`，cleanup_done `19928502113473`，相差 **4.056147068 s**；两端 rc=-9、reaped、group_residue=false、handle_open=false，case overrun=false。核心 finally 的 cleanup_endpoint 对存活自有端点直接 SIGKILL；与快照无效后的提前收尾相符，**不支持自报“t=15 s 硬超时”**。这仅是封存现场状态，不证明审查时系统无残留。本审查未扫描当前进程或共享内存。

### 基线、时钟与称谓变更

Codex 写文档前重算 R14 基线（SHA `151066330f948c331bf8413271ab23d30e40dc36f61e5cfd22aee61cf0cfeebe`）：**932 路径，0 missing、4 changed**，恰为 `.coordination/README.md`、`roles/{README,codex,deepseek}.md`；HEAD/main 未变。领取记录 0/0 与当前不同。回报后附记明确记录 13:56 后执行方改称 DSH，并将 baseline_end.json 改写为 13:58 的 4 changed；因此原回报“结束仍 0/0”已不代表当前文件，**原始结束 0/0 的完整记录现不可从该路径核实，不补造**。

已完整阅读四份现行协调文本，职责、白名单、人工唤醒和审查权仍相同；更名来源是执行者关于用户指示的附记，本审查没有独立对话凭证。Codex 在自身协调文档维护权限内接受现行 **DSH（dsh）称谓**并显式纳入下一基线，不把保护路径变化归为工程实施成果，不回改历史署名/旧基线。本轮不扩大为根入口/全仓更名。

审查期间又观察到外部协调写入：`AGENTS.override.md` 同步改称 DSH，Runbook 用法第 5 条同样更名；report/CURRENT 附记说明获得追加用户授权，baseline_end 再次改写为 14:03:46 / **6 changed**（四份协调文件、根 override、Runbook）。本审查完整读取根 override 和用法行，只有称谓同步、入口/职责链接及语义不变，Codex 同样接受现行字节；不声称独立见证另一会话授权，不追溯改旧记录。Codex 已并行写入的 Runbook 状态/进度段复读保持，未遭覆盖。上述“4 changed/13:58”是本审查早先实际读到的阶段状态；最终保护基线前相对 R14 共 **9 changed**：5 份称谓协调/入口文件、Runbook（兼含称谓和 Codex 进度更新）、spec/tasks/checklist。此处显式记录变化，不能把新的 6 changed 记录误当原始技术交接结束证据。

最初 claim→handoff 配对原数：mono `18631221549667`→`20075675933404`，整数差 `1444454383737 ns` = **1444.454383737 s**；epoch `1793078681849526376`→`1793080256709087061`，整数差 `1574859560685 ns` = **1574.859560685 s**（回报 1574.859558069 算术有 2616 ns 偏差）。初次技术交接 mono 小于 25 min；不能仅据 epoch 差断言实际耗时超限，也不据此挽回违规。后续更名/改写结束记录的 13:58 样本 mono `20500629893586` 对 claim 已是 **1869.408343919 s**，单列为交接后协调附记，不冒充初次交接结束。故不宣告本轮完整预算/证据验收通过。

最新 14:03:46 附记样本 mono `20782933496776` / epoch `1793081026950638562`，相对领取 mono **2151.711947109 s**，同样只代表后续协调活动。基线生成首次尝试因检测到新增根 override 变化主动中止（未生成文件），核对上段后重新生成；不是忽略不匹配。

### 入口缺口与返工边界

1. **生产库配置错误已独立核实**。两快照都映射 `/opt/ros/jazzy/lib/libfastrtps.so.2.14.7`，SHA `2b80489f57d87ce4832766371c5e9f4b0c6b035dc850b284b9f6afcad4962929`；只读文件核对确认 `.so.2.14` 是指向该文件的符号链接，二者文件 hash 相同。核心按精确 basename/path/hash 检验，默认配置却用链接名，故拒绝。文件依据保存于 [library_identity.json](../../../experiments/ros2-diagnostics/20261027-p3-r15/config/sources/library_identity.json)。R15 只修固定配置的 canonical path/basename；不弱化匹配、不从运行 maps 自动生成 expected、不改核心。
2. **默认 pin 来源标签错接**。`_default_dependency_factory` 把默认 PINNED_BINARY 作为显式 trusted_binary 传入，既有 run_runtime_batch 因参数非 None 而记录 synthetic_injection。R15 入口工厂保留默认 None，让既有解析路径标 r4_dispatch_pin；真实 pin 值不改，显式夹具仍 synthetic。不重写已通过 pin 检查。
3. **main 的 runtime owner 没有接收方**。run_entry 返回 summary 保留 owner，但 main 仅取 code，局部 summary 随返回丢弃；对持续失败 handle 分支没有完成入口级归属证明。R15 在入口层明确保留/转交 owner，并以假句柄 weakref/GC 证明 main 返回后仍可达、可后续释放；不把 owner 写 JSON，不重构已通过核心。
4. 导入/默认拒绝、目录冲突、固定配置、完整 ABBA、坏预检和运行中 invalid 的入口测试/guard 均未完成。自报的两个手动 main 拒绝调用属于**候选行为验证**，不能以“不是测试”规避只允许完整命令的限制。R15 候选导入/行为检查全部在带 guard 的完整 pytest 进程内进行，禁止手工冒烟/真实入口。

R14 验收项 1 的字节保留部分成立；其余入口行为未完整验证，0 真实运行条件明确失败，整轮不验收。保留未验收入口作为 R15 参考，不要求无意义重写。R14 全部 34 文件加入新保护清单，后续不再修改该根（包括 baseline_end/VIOLATION），目前**未封存**，不伪称已归档。`log/x/`、专用 /tmp 目录继续保留；共享内存归属仅有自报，时间戳不足以证明所有权，不授权扫描、删除或 kill，离线返工不依赖清场。将来真实实验如需共享资源处置，单独取证/派工。Codex 此次只读分析/重算及维护文档，没有运行 pytest、导入候选、启动 helper/ROS 或清理现场。

<a id="round15-evidence"></a>
## 第 15 轮独立审查（Codex，2026-10-27）

任务 `20261026-002-w8-measurement-p3`，第 15 轮。**部分通过，入口整体未验收；R16 仅补两处入口 owner 缺陷。** canonical 库配置、默认 pin 来源、入口主要接线与完整假进程 ABBA 通过；不因历史局部测试次数限制单独要求返工。用户本次明确要求适度放宽 DSH 权限，已写入 [自主权限](../../README.md#executor-autonomy)，从 R16 生效，不追溯改写 R15 要求。原 P3 工程/设计仍阻塞，真实通信根因未知，gate/headless/P1/P2 不变。

### 已核实的技术交付

读取 R15 回报、adapter 相对 R14 的差异、新增测试、原始 run2 stdout/guard、基线、manifest/tar/两侧车。核心/核心测试/conftest SHA 与 R13/R14 完全相同，分别 `c3f7d1a1…`、`c36d617b…`、`1125cebf…`；adapter `5c4080e1e2b95a1a5ddb1b19d6d0bd18bce0e11aa13411ccd3041ece39863ab7`，adapter test `b71f40241e475ca816cc9e46e31e75c2544c3dd8ea4aba09a8b897960bc4efe9`。原 115 项保留，原始最终日志 **146 passed / 2.97 s**，guard collected=146、count=0、write_errors=[]。退出码 0 为执行回报，与原始通过日志相符；本次未重跑 pytest。

- 固定 `libfastrtps.so.2.14.7` canonical path/basename 与已有独立文件依据相符，未弱化精确匹配。默认工厂保留 trusted_binary=None；既有 run_runtime_batch 因此记录 r4_dispatch_pin，显式夹具仍 synthetic_injection，pin 值未变。
- 静态核实参数/授权在依赖构造之前、保护根含软链、独占目录/碰撞保留、部分失败路径报告。新增测试中的 `test_entry_main_refusals_do_not_construct` 创建了 factory 却未传入 main，factory.calls=0 的断言本身不能证明生产工厂未被调用；代码顺序及其他入口测试支持拒绝行为，R16 顺手修正测试接线即可。
- 独立脚本在导入前安装进程/信号/socket/ctypes 与活动 /proc 读取阻断，只复用文件生成函数/FakeClock/假适配器，不收集或调用测试函数。脚本及观察记录存于 [R16 审查来源](../../../experiments/ros2-diagnostics/20261027-p3-r16/config/sources/codex_r15_review.json)，临时脚本 `/tmp/agc-p3-r15-review.py`。完整 main→run_entry→run_runtime_batch→生产解析→核心的 ABBA 返回/盘面 0，四例 success、8 fake launches，逐项 case/batch 回执 hash、message_source bytes/hash 相符，全部假进程回收。损坏日志返回 5，invalid/not_executed、2 fake launches。audit 拦截 0、真实被测/helper/ROS/活动扫描 0。

### 必须修复的两处入口缺陷

1. **持续关闭失败时显式释放抛 TypeError。** `EntryResult.release_failed_resources()` 把列表 errors 传给 `rc.release_owner_handle`，但核心 `close_log` 期望 `errors['cleanup']`。独立真实批核心+假 Popen 失败路径返回 3，main/GC 后句柄可达；保持 fail_close=True 调用释放即 `TypeError('list indices must be integers or slices, not str')`，pending=1。恢复句柄后可 released=1/remaining=0，解释了现有测试为何全绿。入口应适配核心既有错误容器，并返回有界失败结果且保留 owner，不能靠关闭恢复才正常。
2. **下一次 main 覆盖未释放 owner。** main 无条件 `EntryResult.last = result`。独立同进程两次 main：第一次假 Popen/close 持续失败返回 3，弱引用非空；不另持有 result，第二次成功批返回 0，GC 后旧 weakref=None，last_pending=0。旧 owner 被覆盖丢失，尚未完成入口归属保证。可在新 main 创建路径/构造依赖前拒绝未处理 owner，或显式保留多个 owner；方案由 DSH 在入口范围内决定，不改核心，不隐式清场。

### 证据完整性、预算与历史偏离

Codex 改文档前重算：HEAD `d5072aaff33276bcd1c5e7d38b5caa75fe45a290` / main；基线 SHA `06e65e82cf68b022ae0963787622ac3ea72f4af6cb40948e8badc58704820279`，**961 路径 / 0 missing / 仅 tasks、checklist 两项获准变化**。结束 0/0 是早于这两份事实更新的采样，不代表交付后全路径仍零变化。mono 差 **770.562244146 s**、epoch 差 **837.212956002 s**，整数重算相符；但原始结束文件已被覆盖后重建，不能独立认证原始结束时刻与内容，当前文件另有 restored_note，不能称原文件逐字节恢复。后续附记应另计，不用此时点覆盖全部修订。

tar SHA **fe566577e1f6d502c5c0a7611064ba0cc1b1b81f2773cb1bfa4db6c11314146b**，两侧车相符；21 常规成员，manifest 的 20 artifacts size/hash 全符。**当前根不是完整归档同版**：磁盘 report 比 tar 多一段 baseline_end 覆写披露；两个结束样本在归档后生成，均不在 tar。其余归档成员与磁盘逐字节相符。保持 tar、旧报告及当前修订各自原样，后续保护并明确索引，不重建旧封存。回报“未改封存输入”只适用于 tar 本体未改，不能用于声称源 report 未改。

首跑 138/6 仅有自述，完整 stdout 缺失；guard_run1 collected=2 已被局部运行覆盖，guard_diag collected=27 不代表所有局部尝试。**不能由最终 run2 推断首跑或全部五次诊断的 guard 均干净**；无已记录拦截不等于完整证明全程零真实动作。保留如实披露，历史次数/留证项仍未满足。以上不是再次重复整轮的理由；R16 只针对实际技术反例，所有新增验证用唯一日志/guard。Codex 未修改候选、未运行 pytest/工程/仿真、未扫描或清理共享资源。

<a id="round16-evidence"></a>
## 第 16 轮独立审查（Codex，2026-10-27）

任务 `20261026-002-w8-measurement-p3`，第 16 轮。**部分通过，入口 owner 收口仍未验收；要求 R17 仅修 flush 错误后的注册表收敛。** 本审查只读核对 R16 新根、报告、最终日志、guard、manifest/tar/取回记录及 R15→R16 差异；未启动 ROS、helper、真实进程、活动扫描、构建或仿真。

### 已核实

- R16 仅修改新根 `experiments/ros2-diagnostics/20261027-p3-r16/scripts/runtime_adapter.py` 与对应测试；`runner_candidate.py`、原核心测试和 `conftest.py` 指纹与 R13/R15 相同，R15 的 146 项保留。
- `release_failed_resources()` 已改用核心 `{'cleanup': [], 'persist': [], 'primary': []}` 容器；持续 close 失败时调用有界、错误被返回、`remaining=1` 且 owner 保持可达，恢复后可释放。`owners` 注册表也确实避免第二次 `main` 覆盖首个未释放 owner；现有 150 passed、最终 guard `count=0`/`collected=150`/`write_errors=[]`、25 文件 tar 与取回记录自洽。
- R16 的基线、归档前样本、tar 与交接后附记分开保存；交接时长及 0 真实动作边界与回报相符。以上部分通过不代表真实 ROS 通信、原工程/设计或 gate/headless/P1/P2 通过。

### 必须返工

1. **flush 错误导致已释放结果不从 `owners` 注销。** 在 `runtime_adapter.py:959-963`，注销条件是 `not errors['cleanup'] and not self.pending_failed_resources()`。但核心 `close_log()` 先记录 `flush:` 错误，再继续 `close()`；因此 flush 抛错、close 成功时，返回确实为 `released=1`、`remaining=0`，却因 `errors['cleanup']` 非空跳过 `_forget()`。R16 测试 `test_release_flush_failure_does_not_block_other_resources` 只断言返回值和句柄关闭，没有断言 `EntryResult.pending_results()` 已清除。
2. 这使 `pending_results()` 返回一个没有 pending 句柄的结果，违反其文档“仍有未释放资源”的语义，并让模块级 `owners` 长期保留已完成结果；重复 `release_all()` 会继续枚举它，长期调用可形成强引用累积。该缺陷与 R16 的“释放完成即注销/注册表收敛”实现承诺直接冲突，不能按测试全绿追认。

### R17 返工边界

- 只在 R16 新根修改 `runtime_adapter.py` 与 `test_runtime_adapter.py`：当所有句柄已释放（`pending_failed_resources()==[]`）时，即使 `errors['cleanup']` 含 flush 错误，也必须 `_forget(self)`；错误仍须原样返回。不得放宽核心错误语义、吞错或改 `runner_candidate.py`。
- 增加针对 flush 失败的注册表断言，并覆盖 `release_all()` 后注册表为空；保留现有持续 close、跨 `main`、ABBA 和 146 项回归。最终必须重新执行完整 tests、保存唯一 guard/日志和新 tar/取回核验；不得启动真实运行或扫描共享资源。

### 结论

R16 的持续 close 释放和跨 main owner 保留两项主体修复成立，但 flush 错误路径的 owner 注册表泄漏使入口整体不能验收。CURRENT 转为 `待返工`，下一轮只处理上述缺陷；原 P3 工程/设计仍阻塞，通信根因未知，gate/headless/P1/P2 不变。

<a id="round17-evidence"></a>
## 第 17 轮独立审查（Codex，2026-10-27）

任务 `20261026-002-w8-measurement-p3`，第 17 轮。**R17 通过；入口 owner 收口完成。** 本审查只读核对 R17 与 R16 的逐行差异、源码/测试、最终日志、guard、基线样本、manifest、tar、checksum 和取回记录；未启动 ROS、helper、真实进程、活动扫描、构建或仿真。

### 已核实

- R17 仅修改 R16 新根的 `scripts/runtime_adapter.py` 与 `tests/test_runtime_adapter.py`；`runner_candidate.py`、`test_runner_candidate.py`、`conftest.py` 仍分别为 R13/R15/R16 的既有 SHA，未改核心。
- 生产改动仅将 `_forget()` 条件改为 `not self.pending_failed_resources()`。`flush:` 错误仍从核心错误容器返回；当 close 已成功且没有 pending handle 时，结果会从 `EntryResult.owners` 注销。
- `test_release_flush_error_converges_owner_registry` 通过实际 `main → run_entry → run_runtime_batch`、假 Popen 失败和 flush/close 组合路径验证 `released=1`、`remaining=0`、错误保留、句柄关闭、`pending_results()==[]`。`test_release_all_empties_registry_after_flush_errors` 验证批量释放后注册表为空。临时还原 R16 条件的负向对照使两项测试失败，证明新增断言能捕获原缺陷。
- R17 最终完整回归为 **152 passed / exit 0**；最终 guard `count=0`、`collected=152`、`intercepts=[]`、`write_errors=[]`。三份日志/guard 独立留存，未发生真实进程、ROS、活动扫描或共享资源操作。
- 证据 manifest 的 21 个 artifacts 全部 size/SHA 匹配；tar 共 22 个成员，磁盘与 tar 逐字节一致。tar SHA `be2ab483f0bf23acb4132cf4c4bd84ec4a65797a7df8d220c1087aa887292f72` 与 checksum、取回记录 `verified=true/files_checked=22/mismatches=[]` 相符。988 路径基线仅含派工允许的 tasks/checklist 变化；领取、归档前后样本一致。

### 限定与结论

R17 只验收离线入口 owner 注册表收敛，不代表真实 ROS 官方 demo、通信根因、原 P3 工程/设计或 gate/headless/P1/P2 已通过。`owners` 长期压测、真实系统可用性和同步 I/O 可抢占性仍未证明，按回报保留。

**结论：R17 验收通过。** CURRENT 改为 `已验收`，随后按协议将当前任务整体移入归档；未启动下一任务。原 P3 工程/设计继续阻塞，通信根因未知。
