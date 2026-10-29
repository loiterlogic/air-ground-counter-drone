<a id="top"></a>
# Full-chain seed protocol for PX4 and perception

## Status

accepted（2026-10-26；协议决策已接受，实施验证未闭合，见 [证据边界](0101-w8-seed-evidence-and-p3-execution-boundary.md#evidence)）

<a id="decision"></a>
## Decision

W6 `seed` is the experiment master seed. `w6_composition.py` derives one
uint32 seed per PX4 process with `agc-px4-sim-seed-v1`; instance 0 is own,
instance 1 is intruder, and instance 3 is the optional warmup process. The
derived values are passed as `AGC_PX4_SIM_SEED` and recorded in the run
manifest under `effective_params.seed_protocol`.

`sensor_gps_sim` uses a module-private xorshift32 plus Box-Muller stream. It
does not use libc's process-global `rand()`. An unset variable remains a
deterministic standalone seed for direct PX4 use; a malformed value rejects
module startup. The GPS noise model and its configured amplitudes are
unchanged.

The same master seed is passed to `air_perception` through the explicit
`perception_bringup` launch argument. Only `air_perception` receives this
parameter; unrelated perception nodes do not receive undeclared parameters.

<a id="scope"></a>
## Scope

This fixes the random-stream provenance that was missing from repeated full
chain runs. It does not alter the estimated-odom contract or replace the
formal W8 measurement gate. Existing historical verdicts remain governed by
the applicable ADRs.

The per-instance derivation applies to the full W6 composition. The W3
standalone `air_bringup.launch.py` currently passes its seed directly to its
single PX4 and perception instance; direct PX4 without this variable uses its
documented fallback. Neither entry point claims the W6 per-instance protocol.
This scope clarification does not require changing standalone code. A seeded
noise stream does not establish deterministic full-chain trajectories.

<a id="evidence"></a>
## Evidence

The two statements below are historical implementation claims. As of the
2026-10-26 review, no locatable build/test record supporting them was found
in the inspected project evidence; they remain **unverified**, not proof that
no such execution ever occurred. New validation must retain its own dated
records and must not be backdated as evidence for these claims.

## Evidence

- PX4 target `px4` builds with the modified GPS simulator.
- Launch Python files pass syntax compilation and the seed mixer is stable,
  distinct across instances, and distinct across master seeds.

## 2026-10-26 R1 验证证据（P3 前置）

以下为可定位的本轮执行记录；不把历史声明回写为当时已验证，也不把 R1 静态/构建测试当作整链运行生效证明。

- **生产 GPS RNG**：`scripts/tests/fixtures/px4_gps_seed/harness_main.cpp` 编译**生产** `SensorGpsSim.cpp`（最小 host 桩，非重写 RNG）；`scripts/tests/test_full_chain_seed_protocol.py` 13 项通过：同 seed 重启一致、异 seed 区分、实例 0/1/3 私有、seed=0 映射 `0x6D2B79F5`、unset=1、非法值拒绝、uint32 边界接受。日志：`experiments/w8-parity/20261026-w8-measurement-p3/log/pytest_r1.log`。
- **checker**：`scripts/toolchain_pin_check.py` 新增 `local_patches`（补丁 sha256、基准可应用、当前工作树=基准+补丁、登记源文件哈希、额外 dirty/untracked、子模块标记/已跟踪内容）；`scripts/tests/test_toolchain_pin_check.py` 7 项正负例通过。
- **GPS 模块构建**：`ninja -C toolchain/PX4-Autopilot/build/px4_sitl_default px4`，退出码 0；日志显示 `Building CXX object .../SensorGpsSim.cpp.o` 与重新链接 `bin/px4`。日志：`experiments/w8-parity/20261026-w8-measurement-p3/log/px4_build.log`。
- **binary pin**：`toolchain/README.md` 的 PX4 artifact 由 `1c990470…` 显式更新为 `0c2be618…`；旧值保留在 `note`。重跑 checker：41 PASS / 0 FAIL / 0 SKIP（`metrics/pin_check_after.json`）。
- **仍待运行生效核验**：本轮 R3 因本机 C++ ROS 节点 DDS 发现故障**未执行**（无 GUI attempt）；因此本 ADR 的 seed 协议仍属 `seed_protocol_candidate_unvalidated`，不是 `seed_protocol_v1_attested`。运行生效（manifest `seed_protocol`、own/intruder GPS seed 日志）须在环境恢复后的 R3 补验。
