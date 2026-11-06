<a id="request"></a>
# 机载俯视相机 —— round-2 派工（Leader 裁定后执行）

- 任务 ID：`20261104-001-nadir-camera`；轮次：2；派发 `2026-11-04T19:08:45+08:00`。
- 来源：Leader 消息（2026-11-04T19:08），对 round-1 三条调研结论作出裁定。
- 继承 round-1 全部边界（白名单 / 契约 / 停止条件 / 资源总量），本轮只缩小白名单，不扩大。

## 本轮目标

按 Leader 裁定口径，机械执行 round-1 报告第八节的 8 个步骤：
模型资产 → gz 展开验证 → 桥条目 → 条件注入 `PX4_SYS_AUTOSTART` → 静态闸门测试 → ADR/文档 → T2 两次持锁运行。

## Leader 裁定（5 条，覆盖 round-1 报告第三节）

1. **pitch = `+1.5708`**（round-1 C1 采纳）。测试双断言：数值 `+1.5708`（容差 1e-3）+ 有效光轴 z ≈ −1（容差 1e-2）。
2. **§7.1 边缘 GSD 不改**（round-1 C3 不成立）。`H·sec²θ/f` 在 θ=35° 给 7.90 cm/px，与 §7.1 的 7.8 一致；
   35° 是**边界视场**口径、56.1° 是**边角**口径，二者不混用。ADR 里补这一句区分，**不改 §7.1 表格数字**。
3. **`gz_x500_mono_cam` 保留**（round-1 自查正确，3 处白名单外引用）→ 省防复活断言，`路线分支治理.md` 5.2/5.3 **不改**。
4. **ADR 编号 = `0030`**（不用 0108）。
5. **`camera_info` 显式命名采纳**：`<camera_info_topic>agc/air/nadir/camera_info</camera_info_topic>`；拿不到该元素则退回 `<topic>_info` 并登记。

## 白名单（较 round-1 缩小）

```
src/agc_sim/models/agc_x500_nadir/**            # 新建
src/agc_sim/config/bridge.yaml                  # 仅新增 nadir 两条
src/agc_task/launch/w6.launch.py                # 仅己方 PX4 条件注入 + px4_sim_model 描述
src/agc_air/launch/air_bringup.launch.py        # 仅条件注入 + 描述
scripts/tests/test_nadir_camera_contract.py     # 新建
docs/adr/0030-nadir-camera-capability.md        # 新建
docs/adr/README.md                              # 仅由 adr_index.py 生成
docs/conventions/飞行高度分层与按地图定高.md      # 仅 §7.1 补一句（不改数字）
docs/plan/无人机俯视相机.md                      # 删除
experiments/nadir-camera/**                     # 新建
```

**移除**：`README.md`（Leader 合并）、`docs/conventions/路线分支治理.md`（裁定 3 不改）、
`src/agc_sim/launch/world_bringup.launch.py`（资源路径已具备，无需改）。

## 资源

- T1 1200 s（单次 ≤30 s、≤2 进程、独占 `/tmp/20261104-001-*`），次数只记账。
- T2 3600 s 全额仍在（round-1 消耗 0）。构建计入 T2。每次真实运行持 `sim.lock`。
