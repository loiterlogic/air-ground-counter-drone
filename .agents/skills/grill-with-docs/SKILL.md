---
name: grill-with-docs
description: "深度访谈并在决定定形时同步落文档（ADR + 术语表）。当用户想边访谈边把决定记下来时使用。"
---

# Grill With Docs

依次加载两个技能（都用 `skill` 工具，按名字取）：

1. `grilling` —— 提供访谈流程；
2. `domain-modeling` —— 提供术语表与 ADR 的写法与边界。

按 `grilling` 的轮次做访谈；每当一个术语定形、或一个**难以逆转**的决定落定，就用 `domain-modeling` 的做法**当场**写进：

- 术语 → [GLOSSARY.md](../../../GLOSSARY.md)（只写术语与边界，不写实现细节）；
- 架构/契约级决定 → `docs/adr/`（遵守项目模板：`## Status` 节、稳定锚点、不重写历史），写完跑 `python3 scripts/adr_index.py` 更新索引。

## 边界

- **不是每个决定都要写 ADR**：只有"难以逆转 + 没上下文会奇怪 + 真实取舍"三条都成立才写。普通实现决定留在任务记录里。
- **不要写重复真源**：约束类信息只引用 [契约真源](../../../docs/adr/0020-package-boundaries-and-runtime-topology.md#hard-constraints)，不在 ADR 或术语表里复述一遍。
- **不要循环调用**：`grilling` 和 `domain-modeling` 各自都会查事实（读文件、跑只读命令），不要互相加载；本技能只负责把两者串起来。
- 访谈仍然**不强制**：用户只是要干活、没要求访谈时，不要进入本流程。
- **结束判定**沿用 `grilling`：用户发起的访谈由用户拍板；已有既存授权时由执行者在前沿清空后判定结束并实施，不重复确认。
