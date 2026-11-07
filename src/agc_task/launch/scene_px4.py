#!/usr/bin/env python3
"""scene_px4 —— `backend:=full` 的空中链路参数拼装与 PX4 进程编排（ADR-0027）。

口径：`main.launch.py` 只做"读 launch 参数 → 调本模块 → 组装 launch actions"；
所有 yaml 读取 / 合并 / 派生 / 落临时文件都在这里。这样"参数拼装只有一条派生链"
（ADR-0007）不会被 launch 编排层的条件分支绕开。

PX4 路径解析 / 命令拼装 / 运行根种子也在此：它们是**进程编排**，不是场景语义。
"""

import os
import shutil
import tempfile
from pathlib import Path

import yaml

from scene_common import new_run_token
from scene_altitude import apply_air_geometry, apply_flight_altitude_air


# --------------------------------------------------------------------------------------
# backend:=full 的**参数拼装**（B2：从 main.launch.py 的 _compose 交回本模块）
#
# 口径：main.launch.py 只做"读 launch 参数 → 调本模块 → 组装 launch actions"；
# 所有 yaml 读取 / 合并 / 派生 / 落临时文件都在这里。这样"参数拼装只有一条派生链"
# （ADR-0007）不会被 launch 编排层的条件分支绕开。
# --------------------------------------------------------------------------------------

def merge_air_params(air_share, scene_params, geometry, sim_share=None):
    """空中链路节点参数 = `air.yaml` 基参 + 场景覆盖 → 几何 / 高度派生（**唯一**合并入口）。

    `main.launch.py` 原先内联做三件事（读 yaml / 合并 / 派生），现全部在此：
    本函数是"配置文件 → 空中参数"的唯一实现，launch 只调它。

    返回合并后的 `{node: {param: value}}`（未包 `ros__parameters`）。
    """
    with open(os.path.join(air_share, 'config', 'air.yaml')) as f:
        air_base = yaml.safe_load(f)
    air_merged = {n: dict(sec.get('ros__parameters', {})) for n, sec in air_base.items()}
    for n, over in (scene_params or {}).items():
        if n in air_merged:
            air_merged[n].update(over)
    # 静态障碍几何由**配置文件**注入空中安全列表（obstacle_names/x/y；半径 / margin 仍来自 air.yaml）。
    apply_air_geometry(air_merged, geometry, sim_share=sim_share)
    # ADR-0007：高度随地图派生注入（空中侧：跟踪高度 / 起飞高度）——与 apply_air_geometry
    # 同款同位置，保证"配置文件 → 空中参数"只有一条派生链。
    apply_flight_altitude_air(air_merged, geometry)
    return air_merged


def write_air_params(air_merged, backend, scene, seed, token=None):
    """把空中参数写入临时 yaml（`w6_<backend>_air_<scene>_<seed>_<token>.yaml`），返回路径。"""
    token = token or new_run_token()
    doc = {n: {'ros__parameters': p} for n, p in air_merged.items()}
    path = os.path.join(
        tempfile.gettempdir(), 'w6_%s_air_%s_%d_%s.yaml' % (backend, scene, seed, token))
    with open(path, 'w') as f:
        yaml.safe_dump(doc, f, allow_unicode=True, sort_keys=True)
    return path


def px4_paths(agc_root):
    """PX4 工具链路径（`px4_dir` / `px4_build` / `px4_bin`）。"""
    px4_dir = str(Path(agc_root) / 'toolchain' / 'PX4-Autopilot')
    px4_build = os.path.join(px4_dir, 'build', 'px4_sitl_default')
    px4_bin = os.path.join(px4_build, 'bin', 'px4')
    return px4_dir, px4_build, px4_bin


def require_toolchain(agc_root, px4_bin):
    """校验工具链二进制存在；缺失即**拒启动**（返回缺失清单，由 launch 抛错）。

    返回 `[]` 表示齐全。判据见 ADR-0005（工具链 pin）。
    """
    required = [Path(agc_root) / 'toolchain' / 'bin' / 'MicroXRCEAgent', Path(px4_bin)]
    return [str(p) for p in required if not p.exists()]


def px4_cmd(px4_bin, px4_build, px4_root, instance=None):
    """PX4 启动命令；`px4_root` 为空时与原命令**逐字一致**（默认路径不变）。

    `px4_root` 非空 = ADR-0024 的 opt-in 每实例可写运行根（`-w` 私有目录 + 私有 etc）。
    """
    if px4_root is None:
        if instance is None:
            return [px4_bin, '-d', '-s', 'etc/init.d-posix/rcS']
        return [px4_bin, '-i', str(instance), '-d', '-s', 'etc/init.d-posix/rcS']
    cmd = [px4_bin]
    if instance is not None:
        cmd += ['-i', str(instance)]
    # `-w` = 可写运行目录（dataman / parameters*.bson / log / eeprom 均落此）；
    # 末尾 positional data_path = 私有 etc 绝对路径（PX4 在 cwd 建 `etc -> data_path` 符号链接，
    # 使相对的 `-s etc/init.d-posix/rcS` 解析到本实例私有 etc）。
    cmd += ['-w', str(Path(px4_root) / ('instance_%d' % (instance or 0)))]
    cmd += ['-d', '-s', 'etc/init.d-posix/rcS', str(Path(px4_root) / 'etc')]
    return cmd


def seed_px4_run_root(px4_root, px4_build, instances=(0, 1, 3)):
    """ADR-0024：为每实例播种参数初态（共享 build 只读，**绝不回写**）。

    2026-11-03 实测：`-w` 指向空目录时 PX4 以**出厂默认**起，`rcS` 的 `AUTOCNF` 分支会重写
    CAL_*，但 accel/gyro 校准值仍缺失 → 4 条 Preflight Fail。播种共享 build 的
    `parameters.bson`（含 SITL 传感器校准真值）后同一命令 0 条 Preflight Fail。
    """
    if px4_root is None:
        return
    root = Path(px4_root)
    if not (root / 'etc').exists():
        shutil.copytree(Path(px4_build) / 'etc', root / 'etc')
    for inst in instances:
        inst_dir = root / ('instance_%d' % inst)
        inst_dir.mkdir(parents=True, exist_ok=True)
        for name in ('parameters.bson', 'parameters_backup.bson'):
            src = Path(px4_build) / name
            dst = inst_dir / name
            # 只在缺省时播种：同一 run 内 PX4 自己写回的参数不得被 launch 覆盖。
            if src.is_file() and not dst.exists():
                shutil.copy2(src, dst)


def spawn_args(effective_spawn):
    """世界 spawn 的 launch 参数 —— **取自 `apply_spawn_layout()` 的返回值**。

    这样"世界 spawn == 复位位置"对**每个场景**都成立（场景覆盖出生位时，两侧一起变），
    而不是只对默认场景成立。`car_z` 用**轮触地**口径（模型几何属性，与复位口径不同）。
    """
    car, tgt = effective_spawn['car'], effective_spawn['target']
    return {
        'car_x': str(car['x']), 'car_y': str(car['y']),
        'car_z': str(car['world_z']), 'car_yaw': str(car['yaw']),
        'target_x': str(tgt['x']), 'target_y': str(tgt['y']),
        'target_z': str(tgt['z']), 'target_yaw': str(tgt['yaw']),
    }
