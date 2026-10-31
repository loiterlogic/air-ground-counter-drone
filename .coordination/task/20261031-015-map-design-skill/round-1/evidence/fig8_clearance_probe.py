#!/usr/bin/env python3
"""fig8_clearance_probe —— 只读复核 GATES.md「8 字净空」两条口径（T0 离线，不起进程树）。

口径（与 tests/w6_geometry_check.py 复用同一组函数，避免另写一套）：
  圆盘口径  min_θ [‖p(θ) − anchor‖ − (safety_radius + obstacle_margin + extra)]   ← 安全层同口径
  足迹口径  min_θ [点到实体水平足迹距离 − 足迹外伸]                                ← 纯几何
轨迹：契约 C1 真八字 Gerono，rx/ry 来自 air.yaml 的 traj。

用法：python3 <本文件> [--json out.json]
"""
import importlib.util
import json
import math
import os
import sys

ROOT = '/home/chen/AGC'
spec = importlib.util.spec_from_file_location(
    'geomchk', os.path.join(ROOT, 'tests', 'w6_geometry_check.py'))
chk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(chk)

share = os.path.join(ROOT, 'install', 'agc_sim', 'share', 'agc_sim')
if not os.path.exists(os.path.join(share, 'launch', 'world_map.py')):
    share = os.path.join(ROOT, 'src', 'agc_sim')
air = os.path.join(ROOT, 'install', 'agc_air', 'share', 'agc_air')
if not os.path.exists(os.path.join(air, 'config', 'air.yaml')):
    air = os.path.join(ROOT, 'src', 'agc_air')

wm = chk._resolve_maps(share)
ring = chk._air_ring_params(air)
traj = chk._load_yaml(os.path.join(air, 'config', 'air.yaml'))[
    'trajectory_tracker']['ros__parameters']['traj']
rx, ry = float(traj['rx']), float(traj['ry'])
cx, cy = float(traj['center_x']), float(traj['center_y'])

N = 20000   # 单次 ≤30 s（T0 离线预算）；20000 与 40000 点结论逐值相同（已实测）
out = {'traj': {'rx': rx, 'ry': ry, 'center': [cx, cy]}, 'ring': ring, 'samples': N, 'maps': {}}
for name in wm.WORLD_MAPS:
    _, gp = wm.geometry_path(share, name)
    obs = chk._load_yaml(gp)['obstacles']
    disk_min, fp_min = (float('inf'), None), (float('inf'), None)
    for k in range(N):
        th = 2.0 * math.pi * k / N
        px = cx + rx * math.sin(th)
        py = cy + ry * math.sin(th) * math.cos(th)
        for ob in obs:
            d = math.hypot(px - float(ob['x']), py - float(ob['y'])) - chk._disk_radius(ob, wm, ring)
            if d < disk_min[0]:
                disk_min = (d, ob['id'])
            f = chk._obb_clearance(px, py, ob, wm) - chk._footprint_extent(ob, wm)
            if f < fp_min[0]:
                fp_min = (f, ob['id'])
    out['maps'][name] = {
        'disk_clearance_m': round(disk_min[0], 3), 'disk_nearest': disk_min[1],
        'footprint_clearance_m': round(fp_min[0], 3), 'footprint_nearest': fp_min[1],
    }

if '--json' in sys.argv:
    path = sys.argv[sys.argv.index('--json') + 1]
    with open(path, 'w') as f:
        json.dump(out, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write('\n')
print(json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True))
