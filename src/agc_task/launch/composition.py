#!/usr/bin/env python3
"""composition —— 场景配置解析的**唯一入口**（门面，ADR-0020）。

本模块是顶层 composition 场景配置解析逻辑的**唯一对外入口**，供统一入口
`main.launch.py` 复用（`backend` ∈ `lightweight` | `full`）。实现已按内聚性拆到同级
6 个模块，本文件只做**再导出**，不承载逻辑：

| 模块 | 负责 |
|---|---|
| `scene_common` | 跨域共用小工具（run token） |
| `scene_geometry` | 几何源文件加载与派生量（**算法唯一实现在 `agc_sim/launch/world_map.py`**） |
| `scene_spawn` | 出生布局：读取、校验、四处派生 |
| `scene_loader` | backend 能力表、承载者校验、轴覆盖、场景合并 |
| `scene_altitude` | 飞行高度按地图派生与注入 |
| `scene_assertions` | 启动期轴断言（派生几何 == 配置文件） |
| `scene_manifest` | manifest 构建与产物落盘 |
| `scene_px4` | `full` 的空中参数拼装与 PX4 进程编排 |

**为什么保留这个门面而不是让调用方直接 import 子模块**：调用方（`main.launch.py` 与
`src/agc_task/test/test_scene_config_invariants.py`）需要的是"一个入口拿到全部解析能力"；
让它们各自记 7 个模块名，等于把拆分成本转嫁给所有调用方。

约束类信息（参数入口 / 唯一执行口 / 命名空间 / 硬约束 / 终态语义）**只引用不复述**，
条文见 ADR-0020 的对应锚点（#params / #execution-port / #namespace / #hard-constraints）。
"""

import os
import sys

# 兄弟模块解析：本文件可能被两种方式加载——
# ① 正常 `import composition`（`main.launch.py` 已把本目录放进 sys.path）；
# ② `importlib.util.spec_from_file_location('composition_for_test', <abs path>)`
#    （`test_scene_config_invariants.py` 用它隔离加载，此时**本目录不在 sys.path**）。
# 方式 ② 下 `from scene_geometry import ...` 会 ModuleNotFoundError，
# 故这里显式把本文件所在目录加入 sys.path——与 `main.launch.py` 的既有做法同款。
_HERE = os.path.dirname(os.path.realpath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from scene_common import new_run_token                                    # noqa: E402,F401
from scene_geometry import (                                              # noqa: E402,F401
    DEFAULT_WORLD_MAP,
    GEOMETRY_FILE,
    geometry_ids,
    geometry_path,
    geometry_sha256,
    geometry_safety_radii,
    geometry_xs,
    geometry_ys,
    geometry_z_tops,
    load_geometry,
    obstacle_bbox_size,
    obstacle_footprint_radius,
    obstacle_is_composite,
    obstacle_safety_radius,
    obstacle_shape,
    obstacle_z_top,
    resolve_world_map,
    work_area_bounds,
    world_map_module,
)
from scene_spawn import (                                                 # noqa: E402,F401
    SPAWN_LAYOUT_FILE,
    apply_spawn_layout,
    load_spawn_layout,
    own_uav_pose_string,
    parse_own_pose,
    spawn_layout_distances,
    spawn_layout_sha256,
)
from scene_loader import (                                                # noqa: E402,F401
    BACKENDS,
    EPICYCLE_PARAMS,
    apply_target_motion_override,
    carrier_entry,
    compose_params,
    coverage_status,
    derive_px4_sim_seed,
    load_scene,
    write_derived_map,
    write_derived_obstacles,
)
from scene_altitude import (                                              # noqa: E402,F401
    apply_air_geometry,
    apply_flight_altitude_air,
    apply_flight_altitude_params,
    cruise_altitude_block,
    flight_altitude_block,
    net_params_for_altitude,
)
from scene_assertions import (                                            # noqa: E402,F401
    _flight_altitude_assertions,
    assertions,
)
from scene_manifest import (                                              # noqa: E402,F401
    LAUNCH,
    build_manifest,
    observe_yaw_block,
    spawn_layout_block,
    vision_plane_block,
    write_manifest,
    write_temp_params,
)
from scene_px4 import (                                                   # noqa: E402,F401
    merge_air_params,
    px4_cmd,
    px4_paths,
    require_toolchain,
    seed_px4_run_root,
    spawn_args,
    write_air_params,
)

__all__ = [
    # 常量
    'LAUNCH', 'GEOMETRY_FILE', 'DEFAULT_WORLD_MAP', 'SPAWN_LAYOUT_FILE',
    'BACKENDS', 'EPICYCLE_PARAMS',
    # 工具
    'new_run_token',
    # 几何
    'world_map_module', 'resolve_world_map', 'geometry_path', 'load_geometry',
    'geometry_sha256', 'obstacle_shape', 'obstacle_safety_radius',
    'geometry_safety_radii', 'obstacle_z_top', 'geometry_z_tops',
    'obstacle_bbox_size', 'obstacle_is_composite', 'obstacle_footprint_radius',
    'geometry_ids', 'geometry_xs', 'geometry_ys', 'work_area_bounds',
    # 出生布局
    'load_spawn_layout', 'spawn_layout_sha256', 'own_uav_pose_string',
    'parse_own_pose', 'spawn_layout_distances', 'apply_spawn_layout',
    # 场景
    'derive_px4_sim_seed', 'carrier_entry', 'coverage_status',
    'apply_target_motion_override', 'write_derived_obstacles', 'write_derived_map',
    'load_scene', 'compose_params',
    # 高度
    'apply_air_geometry', 'flight_altitude_block', 'net_params_for_altitude',
    'apply_flight_altitude_params', 'apply_flight_altitude_air',
    # manifest
    'assertions', '_flight_altitude_assertions', 'vision_plane_block', 'build_manifest',
    'observe_yaw_block',
    'cruise_altitude_block', 'spawn_layout_block', 'write_temp_params',
    'write_manifest',
    # PX4
    'merge_air_params', 'write_air_params', 'px4_paths', 'require_toolchain',
    'px4_cmd', 'seed_px4_run_root', 'spawn_args',
]
