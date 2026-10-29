<a id="round20-review"></a>
# 第20轮独立审查

任务 ID 20261027-001-w8-validation-recovery；来源 Leader，2026-10-28。

## 1. 独立核验

亲自读取round-20 report/analysis、A例双侧events/result、`A-reclaim-race`对照、离线守卫与prefix_reference、基线与归档。独立重算tar SHA `4040841e071e26fbfa9fc1ad75de944808bcd4cbe1d3baae5796ca87f47c4d67`，40成员与源根逐文件一致；43564项受保护文件漂移0。

双侧事件独立重算：
- pub（first）：68事件、seq 1..68完整、2个`matched_event`峰值1、47样本graph_sub峰值1；
- sub（second）：39事件、seq 1..39完整、**0 matched_event、32样本graph_pub=0/matched=0/heard=0**；
- 两侧result均存在（BaseException修复生效），窗口按anchor+budget+1.5s计时未被截断，sub 8.01s完整落在pub 12.01s内，pub发布12条其中8条在sub窗口内。

离线守卫12/12、API 53/53，三项真正before/after（锚定窗口、400ms延迟模拟、SIGINT落盘）均为r19实现FAIL→r20实现PASS；套件在真实T1前抓出5个自身缺陷。T1 1/2、12.680s、整轮615.138s，未用重跑。

**第20轮取证验收通过。** 完整窗口下正式复现历史单向发现形态，"启动太早"与"窗口截断"两个解释被排除。prefix_reference夹具被明确标注为重建测试夹具而非r19产物，其存在使before/after守卫可复算，接受保留。

## 2. 三项裁定

1. **下一分支：不进UDPv4，先钉发现方向**。理由：UDPv4只替换数据面传输；本轮断点在**发现通告的单向性**（后启动者看不到先启动者），发现不通则任何数据面配置都无法送达。r18"双侧matched但零送达"与本轮形态可统一解释为"后启动参与者未收到先启动者的通告/单播响应，或其通告单播地址不可达"——该假设预测单独切UDPv4不恢复交付。先做稳定性与方向性确认。
2. **prefix_reference保留**。它标注清晰、非r19原始件、使守卫可复算；analysis中"重建夹具非原始字节"的限定必须保留。
3. **单侧成立支持发现层分支**：pub看到sub证明sub的通告已达pub；sub看不到pub证明pub的通告未达sub或被丢弃，定位到发现通告路径的pub→sub方向。再下钻需要locator/端口观测或Fast DDS层日志，本轮先做T0端口/locator观测与离线研究，Fast DDS配置日志需另轮显式授权。

## 3. 第21轮方向

当前boot内做A重复（pub-first，稳定性）与B（sub-first，方向翻转），T1两次；同时T0采集两侧participant的UDP监听端口与本机Fast DDS 2.14.7 LOCALHOST发现机制离线研究。若单向形态随启动顺序翻转，"后启动者看不到先启动者"的规则在当前boot成立；若B双侧匹配，则形态具时变性，需重新评估。

S2/S3/S4、gate/headless/科研结论不变，整链不归档。
