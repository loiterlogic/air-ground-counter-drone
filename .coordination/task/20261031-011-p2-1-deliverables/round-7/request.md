# P2-1 · round-7 request（Worker 自写，**新批次首轮 N=4 / K=4**）

<a id="p2-1-r7-request"></a>

- 任务 ID：`20261031-011-p2-1-deliverables` · round-7 · 2026-10-31
- 来源：**Worker 自写**，继承 [round-6 审查](../round-6/review.md#p2-1-r6-review) 第 2/3 节（裁定 **A + D**，范围扩到交付/验证路径）
- 承接：[round-6 report](../round-6/report.md#p2-1-r6-report)（路径硬编码阻塞）

## 本轮目标（**离线，T2 = 0**）

**A + D 落地**：让"交付/验证路径"自定位，并加回归防复发；**同时修 `doctor` 误报**（实测取证）。

## 范围（按"是否用于运行期解析文件"判定，**不是按字面**）

| 范围 | 处置 |
|---|---|
| `run_demo.sh` | `ROOT` 用 `BASH_SOURCE` 自定位 |
| `scripts/demo/common.py` | `ROOT` 用 `__file__` 自定位（`start.py` 已把 `agc_root:=<common.ROOT>` 透传 launch → 修这一处即让整链用克隆自己的根） |
| `tests/w6_geometry_check.py` | 该 1 处自定位化（它在冒烟 `geometry` 组里） |
| `tests/run_smoke.py` | **已是自定位**（只核验，不改） |
| `scripts/tests/**`（21 个含该串） | **逐个分类**：运行期解析文件 → 自定位；注释/文档串/规范部署根期望值 → 保留。**分类表写进报告** |
| `src/agc_task/launch/w6.launch.py`（3 处） | 同样分类；仅默认值声明可保留 |
| **不做** | `scripts/research/**`、`scripts/archive/**`、`docs/**`、`.coordination/**`、冒烟未调用的 `tests/**`、**契约默认值**（`src/agc_air/launch/air_bringup.launch.py` 的 `agc_root` 受 `toolchain_root_check.py` 保护 → **不得改**） |

> **不做**的部分忠实登记为"开发/历史工具不可移植"，**不假装修好**。

## D（防复发回归）

新增回归，断言**运行期解析类**位置不再出现硬编码根；允许**显式白名单**（契约默认值 / 注释 / 历史文档），
**白名单每条写清理由**。

## 同时修 `doctor` 误报

克隆里**没有 `install/`** 时必须 **FAIL**（根因随 A 解决，但**必须实测取证**，不只靠推理）：
用 `/tmp` 下临时目录构造"无 install"情形，断言 `doctor` 退出码非 0 且报的是**该目录自己的路径**。

## 预算

- **T2：0 次**（纯离线代码改动 + 离线复验）。
- **T1**：沿用批次余量。
- 离线只读检查：次数只记账。

## 禁止（红线）

- **禁止**改**契约默认值**（`air_bringup.launch.py` 的 `agc_root`；受 `toolchain_root_check.py` 保护）；
- **禁止**清 `/dev/shm`、**禁止**处置他人进程、**禁止**写 `~/.gz`；
- **禁止**碰 `scripts/research/**`、`scripts/archive/**`、`docs/**`、`.coordination/**`；
- **禁止**用旧图/示意图、**禁止**包装未达成项；
- **禁止**碰完整视频（用户自录）。

## 停止条件

- **round-7/8 两轮内**克隆仍不能"`doctor` 真实 + 跑到终态" → 判**不可达成**，停止交台账；
- 达 **N=4** 或预算耗尽 → 必须唤醒 Leader；
- 若修 `common.py` 后**任何**已验收路径回归变红 → 立即停并报告（可能触及白名单/契约）。

## 不做

- 克隆实测（round-8）；
- 用户视频接入（round-9，等文件）；
- push / 归档 / 开下一任务。
