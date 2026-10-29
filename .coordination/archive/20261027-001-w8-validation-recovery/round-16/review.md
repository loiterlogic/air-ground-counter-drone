<a id="round16-review"></a>
# 第16轮独立审查

任务 ID 20261027-001-w8-validation-recovery；来源 Leader，2026-10-28。

## 1. 独立核验

亲自阅读完整 request/report、源根 analysis、A1/A2 command 与双端原始日志、B 收发 JSON、网络快照、归档 retrieval 和封存后更正侧车；并回看第14轮单向发现证据及第15轮机制核查，不以 Worker 自述替代原始件。

- A1/A2：官方 stock listener 均在 talker 启动时存活，重叠分别 6.331/6.296 s，真实 wait RC 均 0；talker 各发布 5 条；listener 原始输出无 `I heard:`，只有回收时 `signal_handler` 行。干净环境与继承环境均失败，负结果成立。
- B：纯标准库进程在 127.0.0.1:20000 两方向各收到序号 1–5，真实 RC 均 0；UDP 错误/丢包计数无增量。只证明本次 loopback UDP 通路正常，不证明 DDS 正常。
- 基线：HEAD `d5072aaff33276bcd1c5e7d38b5caa75fe45a290` / main，`git status --porcelain` 36 项；Leader 独立逐项重算 `codex_dispatch_baseline.json` **1926/1926，drift 0**。
- 预算：T1 三次 8.334/8.301/0.496 s，总 17.130 s，均最多两个被测进程；整轮 mono 708.568 s，合规。B 首次在启动被测进程前因表头解析失败，未产生通信样本，保留原件后修复一次可接受。
- 封存：retrieval `verified=true`、45 files、mismatches 0；tar SHA 与记录一致。封存后 `analysis.md` 的内容更正及唯一源根差异均已披露，有 `_archive` 侧车；归档本身仍自洽。该写入违反封存后源根只读，保留过程偏离，不宣称流程无瑕疵，也不因主动披露否定原始观测。

## 2. 验收裁定

**第16轮诊断取证验收通过。** Worker 对 `p3-r2` 的两处更正有原始件支持：六例环境是构造的11键而非继承环境；首例空日志是在真实 listener 仍存活时抓取，不能据此排除缓冲假阴性。这些更正不推翻其余五例的阳性。

采纳 `S-不定` 的谨慎结论，但将后续诊断状态明确为：**stock 与自写探针在本轮条件下均失败，故“仅自写探针/驱动失败”不再成立；clean-env 缺失、listener 早退、输出缓冲和本次 loopback UDP 整体不通均不能解释本轮负结果。尚未证明 DDS 整体失效，也未定位 participant discovery / endpoint matching / user data delivery 的断点。**

## 3. Leader 对派工判读树的修正

本轮 request 把“A1/A2 均失败”直接导向“与项目代码、探针形态、DDS 配置无关的 S-环境”，这个定义过宽：官方 stock 失败只能排除“自写探针专属”，不能排除 DDS 实配或本机 Fast DDS 行为。Worker 用 B 结果把它收窄为 `S-不定` 是正确处理；不把该定义缺陷记为 Worker 失职。

更重要的是，Leader 在下一轮设计中必须纠正本轮遗留的可比性缺口：历史 `p3-r2` 的 stock 阳性为 domain 37、构造11键、`ros2 run` 包装；本轮 stock 阴性为 domain 0、7/52键、直接 `exec`。因此“同一 stock 曾成功、现失败”还不是受控复现。**先按历史阳性条件复现，再逐项控制变量，比继续开发新探针更能区分持久故障与配置/时序差异。**

第15轮 endpoint-info 候选保留为后续分层观测，不在没有先处理上述不可比项时立即扩写工具。不得重开无依据的 domain 数字扫描；这里选择37仅因它是项目内已有 stock 阳性锚点，并设置同轮 domain0 负对照。

S2/S3/S4 继续关闭；`gate=not_evaluable_as_specified`、headless 规模统计未授权、科研 P1/P2 结论不变，整链不归档。

下一步仅派 [第17轮历史 stock 阳性复现与受控 domain 对照](../round-17/request.md#round17)，T1 三次、45 min；成功后同域检查既有探针，仍失败则停止本轮而不扩写探针。
