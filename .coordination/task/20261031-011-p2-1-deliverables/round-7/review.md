# P2-1 · round-7 审查（新批次首轮，离线）——A + D 落地

<a id="p2-1-r7-review"></a>

- 被审：[round-7 report](report.md#p2-1-r7-report) · 审查人：Leader（DSH） · 2026-10-31
- 裁定：**通过**；派 round-8 = 克隆实测

## 1. 我亲自复核

| 项 | 手段 | 结果 |
|---|---|---|
| 提交 | `git show --stat 7fe7814` / `2b07d8e` | 8 + 2 文件，`run_demo.sh` / `scripts/demo/common.py` / `tests/w6_geometry_check.py` / `scripts/tests/test_w6_viz_registration.py` + 新回归 ✅ |
| 入口自定位 | 读 `run_demo.sh:36` | `ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"` ✅ |
| 新回归 | **自跑** `pytest -q scripts/tests/test_root_self_location.py` | **10 passed** ✅（执行者称反向注入 4 failed） |
| 契约未被改 | `git show 7fe7814` 未见 `air_bringup.launch.py` | `agc_root` 默认值仍在 ✅ |

## 2. 我接受的两处更正

1. **"21 个文件"是我给宽了**：我用 `grep -rl` 把 `.pyc` 等也算进去了；实际 `*.py` **18 个**，**17 个本就自定位**，只需修 1 个。执行者没有顺着我的数字做无谓改动，而是先核事实再动手 —— 对。
2. **"克隆验证必须先把改动提交"**：第一次克隆实测仍 PASS，是因为 `git clone` 取的是 HEAD（旧代码）→ 测的是旧版。
   这是"实测取证"的通用陷阱，执行者自己发现并记档 ✅。

## 3. round-8 的已知操作前提（我已探明）

- 克隆目录**没有 `toolchain/`**（`.gitignore` 排除），而演示依赖 PX4 SITL → 必须显式处理，否则"跑不通"会被误判成路径问题。
- 处置：`ln -s /home/chen/AGC/toolchain <clone>/toolchain`（借用已构建工具链，**必须如实披露为偏离**：
  真实陌生人得按 `toolchain/README` 自行构建，这笔成本 README 已写明）。
- 其余（`install/` 由克隆内构建、`agc_root` 由克隆的 `run_demo.sh` 透传）闭环。

## 4. 未做（忠实登记，我认可）

`scripts/research/**`(19) / `scripts/archive/**`(64) / `docs/**`(30) / `.coordination/**`(21) / 冒烟未调用的 `tests/**`
→ 保持"开发/历史工具不可移植"，**未假装修好**。