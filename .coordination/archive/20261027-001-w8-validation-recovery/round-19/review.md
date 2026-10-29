<a id="round19-review"></a>
# 第19轮独立审查

任务 ID 20261027-001-w8-validation-recovery；来源 Leader，2026-10-28。

## 1. 核验

亲自读取round-19 report/analysis、A例command与events、`A-reclaim-race.txt`、`A-observation-nonauthoritative.json`、离线守卫、基线与归档。独立重算tar SHA `f36e39681fc211bdd98c7fee6739ac748b70207e4837a9ebf9347c7a63b3ad36`，38成员与源根逐文件一致；43520项受保护文件漂移0。

A确实因驱动回收竞态而invalid：sub spawn 7527257611631、真实probe启动晚170.5 ms、驱动按spawn计8s在probe自身窗口结束前17 ms发SIGINT，`KeyboardInterrupt(BaseException)`逃逸、result未写。pub侧47样本matched=1；sub侧30样本跨7.42s graph_pub/matched/heard全0——原始观测可信，但sub窗口被截断，Worker正确标为非权威，未升级为发现。

T1 1/3、12.651s、整轮505.840s，未重跑；B/C依门跳过。离线守卫15/15+52/52，真实T1前抓出4个自身缺陷。maps运行中采集缺陷已修复。封存后源根零写入。

**第19轮流程取证验收通过**：invalid是Worker驱动缺陷而非DDS故障；不以剩余预算静默重跑是正确处置；不把非权威单向观测冒充结论也是正确处置。本轮没有有效数据面或UDPv4结论。

## 2. 四项裁定

1. **回收窗口口径**：下一轮必须先修：驱动的回收期限必须取**probe自身预算+安全余量**（或直接按probe的`process_entry/endpoint_created`时间戳门控），并保留probe捕获`BaseException`仍写result的修复与静态守卫。未修复前不得再跑真实A。
2. **"无result但有events"**：记为**partial观测**，可用于下一轮设计输入，但不能作为该case的有效测量；primary verdict仍为invalid。
3. **A/B/C门顺序**：保持——A invalid即停B/C，防止无效样本混入单变量链。但A的部分原始观测可作为第20轮A的**设计输入**（复现假设），不改变判定语义。
4. **重派A**：批准。第20轮只在修复驱动并离线复现该缺陷后再跑A；若A双侧匹配且heard>0，则rclpy↔rclpy默认数据面在当前boot成立；若复现单向形态且窗口完整，则"rclpy↔rclpy配对专属故障"成为强候选。B/C的UDPv4分支本轮暂不重开，等A给出有效基线后再派。

S2/S3/S4、gate/headless/科研结论不变，整链不归档。
