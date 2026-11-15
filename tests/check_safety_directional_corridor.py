#!/usr/bin/env python3
"""方向化走廊判据的**真实地图**核查（ADR-0047）。

## 为什么需要这一层

`src/agc_ground/test/test_safety_policy.cpp` 的 46 项 gtest 用的是**合成** 8×8 小地图，
它们能证明判据逻辑正确，但证明不了"在真实 `dense_map` 上会发生什么"。
本次缺陷正是这种形态：单测全绿，而真实图上出生点一启动就零速、车一步不动。

本脚本用 `dense_map` 的**真实几何**生成规划层（0.5 m，与 `map_adapter` 的 max-pool 同口径），
喂给**生产判定类** `SafetyPolicy::step`，逐点断言档位。

## 判据（全部机械可判）

| # | 断言 |
|---|---|
| a | 旧出生位 `(-34,-6)` 朝 +x 前进 → **停车**（它在禁行区内，判它停是对的） |
| b | 新出生位 `(-40,-6)` 朝 +x 前进 → **PASS**（方向化 + 出生位修正生效） |
| c | 新出生位朝 goal → **PASS** |
| d | 新出生位原地旋转 → **不进入停车档**（侧方 4 m 内无障碍，不该判停） |
| e | 每个用例的 `paramsError()` 为空（参数自洽） |

**注意**：每个用例必须用**独立的** `SafetyPolicy`。`prev_state_` 是迟滞记忆，
跨用例复用会把上一个用例的 STOP 带过来 —— 本脚本第一版就踩了这个坑，
表现为"明明是 PASS 的输入却报 STOP"。

退出码：0 = PASS；1 = FAIL；2 = 环境错误（无 g++ / 无地图 / 编译失败）。
"""

from __future__ import annotations

import math
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
MAP_YAML = os.path.join(ROOT, 'src', 'agc_sim', 'config', 'maps', 'dense_map.yaml')
INC = os.path.join(ROOT, 'src', 'agc_ground', 'include')

# 规划层口径（与 map_adapter 的派生一致）：证据 0.25 m -> 规划 0.5 m（max-pool）。
PLAN_RES = 0.5
EVID_RES = 0.25
EXTENT = 100.0
ORIGIN = -50.0

CPP = r'''
#include <cmath>
#include <cstdio>
#include <cstdint>
#include <fstream>
#include <vector>
#include "agc_ground/safety_policy.hpp"
using namespace agc_ground;
int main(int argc, char ** argv) {
  std::ifstream f(argv[1]);
  double res, ox, oy; int w, h;
  if (!(f >> res >> ox >> oy >> w >> h)) {return 2;}
  std::vector<int8_t> data(static_cast<size_t>(w) * h);
  for (auto & c : data) {int v; f >> v; c = static_cast<int8_t>(v);}
  struct C {const char * name; double x, y, yaw, v, wd;};
  const C cs[] = {
    {"old_spawn_forward", -34.0, -6.0, 0.0, 1.0, 0.0},
    {"new_spawn_forward", -40.0, -6.0, 0.0, 1.0, 0.0},
    {"new_spawn_toward_goal", -40.0, -6.0, std::atan2(6.0, 37.5), 1.0, 0.0},
    {"new_spawn_rotate", -40.0, -6.0, 0.0, 0.0, 1.5},
  };
  for (const auto & c : cs) {
    SafetyPolicy pol;             // 每个用例独立实例：prev_state_ 是迟滞记忆
    pol.setParams(SafetyParams{});
    if (!pol.paramsError().empty()) {
      std::printf("%s PARAM_INVALID %s\n", c.name, pol.paramsError().c_str());
      continue;
    }
    SafetyInputs in; in.now_s = 10.0;
    in.has_command = true; in.command.v = c.v; in.command.w = c.wd;
    in.command.frame_ok = true; in.command.finite = true;
    in.command.holonomic_ok = true; in.command.stamp_s = 10.0;
    in.has_body = true; in.body.x = c.x; in.body.y = c.y; in.body.yaw = c.yaw;
    in.body.valid = true; in.body.finite = true; in.body.stamp_s = 10.0;
    in.has_map = true; in.map.data = data.data();
    in.map.width = w; in.map.height = h;
    in.map.resolution = res; in.map.origin_x = ox; in.map.origin_y = oy;
    in.map.frame_ok = true; in.map.stamp_s = 10.0; in.map_valid_flag = true;
    in.has_permit = true; in.permit.state = 3; in.permit.stamp_s = 10.0;
    const auto d = pol.step(in);
    std::printf("%s %s %.3f %.3f\n", c.name, toString(d.state), d.out_v, d.diag.d_corridor_m);
  }
  return 0;
}
'''


def build_planning_layer():
    """真实几何 -> 证据层 0.25 m -> 规划层 0.5 m（max-pool）。"""
    import yaml
    with open(MAP_YAML) as f:
        obstacles = yaml.safe_load(f)['obstacles']
    ne = int(EXTENT / EVID_RES)
    ev = [[0] * ne for _ in range(ne)]
    for o in obstacles:
        x, y, yaw = float(o['x']), float(o['y']), float(o['yaw'])
        size = o['size']
        if o['shape'] == 'box':
            hx, hy = float(size[0]) / 2.0, float(size[1]) / 2.0
        else:
            hx = hy = float(size[0])
        reach = math.hypot(hx, hy)
        i0 = int((x - ORIGIN) / EVID_RES)
        j0 = int((y - ORIGIN) / EVID_RES)
        ri = int(math.ceil(reach / EVID_RES)) + 1
        c, s = math.cos(-yaw), math.sin(-yaw)
        for a in range(max(0, i0 - ri), min(ne, i0 + ri + 1)):
            for b in range(max(0, j0 - ri), min(ne, j0 + ri + 1)):
                px = (a + 0.5) * EVID_RES + ORIGIN - x
                py = (b + 0.5) * EVID_RES + ORIGIN - y
                lx, ly = c * px - s * py, s * px + c * py
                if o['shape'] == 'box':
                    hit = abs(lx) <= hx and abs(ly) <= hy
                else:
                    hit = lx * lx + ly * ly <= hx * hx
                if hit:
                    ev[a][b] = 100
    nw = ne // 2
    pl = [[0] * nw for _ in range(nw)]
    for j in range(nw):
        for i in range(nw):
            pl[j][i] = max(ev[2 * j][2 * i], ev[2 * j][2 * i + 1],
                           ev[2 * j + 1][2 * i], ev[2 * j + 1][2 * i + 1])
    return pl, nw


def main():
    if not os.path.exists(MAP_YAML):
        print('FAIL: 找不到 %s' % MAP_YAML)
        return 2
    gxx = shutil.which('g++')
    if not gxx:
        print('FAIL: 找不到 g++（本核查需要编译生产判定类）')
        return 2

    try:
        pl, nw = build_planning_layer()
    except ImportError:
        print('FAIL: 需要 PyYAML')
        return 2

    with tempfile.TemporaryDirectory() as td:
        map_txt = os.path.join(td, 'plan.txt')
        with open(map_txt, 'w') as f:
            f.write('%g %g %g %d %d\n' % (PLAN_RES, ORIGIN, ORIGIN, nw, nw))
            f.write(' '.join(str(v) for row in pl for v in row))
        src = os.path.join(td, 'v.cpp')
        with open(src, 'w') as f:
            f.write(CPP)
        exe = os.path.join(td, 'v')
        r = subprocess.run(
            [gxx, '-std=c++17', '-O2', '-I', INC, src, '-o', exe],
            capture_output=True, text=True)
        if r.returncode != 0:
            print('FAIL: 编译失败\n%s' % r.stderr[-2000:])
            return 2
        r = subprocess.run([exe, map_txt], capture_output=True, text=True)
        if r.returncode != 0:
            print('FAIL: 运行失败 rc=%d\n%s' % (r.returncode, r.stderr[-1000:]))
            return 2
        rows = {}
        for line in r.stdout.strip().splitlines():
            parts = line.split()
            # 正常行：<name> <STATE> <v_out> <d_corridor>（4 段）
            if len(parts) == 4:
                try:
                    rows[parts[0]] = {'state': parts[1], 'v_out': float(parts[2]),
                                      'd_corridor': float(parts[3])}
                except ValueError:
                    pass
            # 参数非法行：<name> PARAM_INVALID <原因...>
            elif len(parts) >= 3 and parts[1] == 'PARAM_INVALID':
                rows[parts[0]] = {'state': 'PARAM_INVALID', 'reason': ' '.join(parts[2:])}

    checks = []

    def add(name, ok, detail=''):
        checks.append({'name': name, 'pass': bool(ok), 'detail': detail})

    old = rows.get('old_spawn_forward', {})
    add('old_spawn_stops', old.get('state') in ('STOP_COLLISION', 'STOP_EMERGENCY'),
        'old spawn should be stopped (inside forbidden zone): %s' % old.get('state'))

    new_f = rows.get('new_spawn_forward', {})
    add('new_spawn_forward_passes', new_f.get('state') == 'PASS',
        'new spawn forward should PASS: %s' % new_f.get('state'))

    new_g = rows.get('new_spawn_toward_goal', {})
    add('new_spawn_toward_goal_passes', new_g.get('state') == 'PASS',
        'new spawn toward goal should PASS: %s' % new_g.get('state'))

    rot = rows.get('new_spawn_rotate', {})
    add('rotate_not_stopped', rot.get('state') not in ('STOP_COLLISION', 'STOP_EMERGENCY'),
        'pure rotation in open area must not stop: %s' % rot.get('state'))

    add('params_self_consistent',
        all(v.get('state') != 'PARAM_INVALID' for v in rows.values()),
        'paramsError must be empty for production defaults')

    n_pass = sum(1 for c in checks if c['pass'])
    print('方向化走廊判据 · 真实 dense_map 核查（ADR-0047）')
    print('=' * 70)
    for c in checks:
        print('  [%s] %-30s %s' % ('PASS' if c['pass'] else 'FAIL', c['name'], c['detail']))
    print('-' * 70)
    print('%d/%d 项通过' % (n_pass, len(checks)))
    for k, v in sorted(rows.items()):
        print('  %-24s state=%-15s d_corridor=%s' % (k, v.get('state'), v.get('d_corridor')))
    if n_pass != len(checks):
        print('FAIL：方向化判据未达预期')
        return 1
    print('PASS：方向化判据在真实 dense_map 上成立')
    return 0


if __name__ == '__main__':
    sys.exit(main())
