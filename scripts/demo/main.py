#!/usr/bin/env python3
"""`run_demo.sh` 的 Python 侧入口（shell 负责 source / 参数收敛 / 人话错误的外观）。

子命令：

 * `preflight` —— start 前的**阻断性**检查（轻于 doctor：只查会直接导致失败的环境项）；
 * `doctor` —— 完整预检（14 项，≤30 s，不启任何仿真）；
 * `start` —— 一次完整演示（见 `start.DemoRun`）；
 * `stop` —— 按 PID/PGID 回收（幂等，可跨终端）；
 * `status` —— 只读现状；
 * `compare` —— GUI ↔ headless 等价核验（口径来自预登记文件）。

为什么 shell + Python 分工：预检要 source ROS 环境、管进程组、调 `colcon`，shell 最直接；
预检项与状态轮询逻辑复杂，拆 Python 模块由 shell 调用
（设计原则 1）。
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

import common          # noqa: E402
import doctor          # noqa: E402


def _world_maps():
    """可用地图名——取自 `agc_sim/launch/world_map.py` 的**单一清单**（ADR-0007）。

 为什么不在本文件里自持白名单：`MAP_GEOMETRY_FILES` 是地图登记的唯一家（核查 (m) 守着
 "消费方不得各写一份文件名表"）。此前这里写死 `('yard','open_field','minimal')`，
 每加一张图都要改两处，且漂移不会被任何断言抓到（ADR-0036 起 dense_map 暴露了这一点）。
 解析失败时**退回**旧白名单并如实报错，不静默放行任意字符串。
    """
    import importlib.util
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
    path = os.path.join(root, 'src', 'agc_sim', 'launch', 'world_map.py')
    try:
        spec = importlib.util.spec_from_file_location('_world_map_registry', path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        names = list(mod.WORLD_MAPS)
        if names:
            return names
    except Exception:  # noqa: BLE001
        pass
    return ['minimal', 'yard', 'open_field']


# --------------------------------------------------------------------------------------
# preflight（start 前的阻断性检查）
# --------------------------------------------------------------------------------------

BLOCKING = ('ros', 'ros2', 'workspace', 'sourced', 'toolchain', 'domain', 'residual',
            'ports', 'instance')


def cmd_preflight(args):
    results = doctor.run_checks(want_gui=not args.headless, only=set(BLOCKING))
    failed = [r for r in results if r['status'] == doctor.FAIL]
    for r in results:
        if r['status'] == doctor.FAIL:
            print('[preflight] %s：%s' % (r['name'], r['detail']), file=sys.stderr)
    if failed:
        lines = []
        for r in failed:
            lines.append('%s：%s' % (r['name'], r['detail']))
            lines.extend('  → %s' % h for h in r['hints'])
        print(common.human_block('启动前检查未通过（未启动任何进程）', lines),
              file=sys.stderr, flush=True)
        return 1
    print('[preflight] OK（%d 项阻断性检查通过）' % len(results), flush=True)
    return 0


# --------------------------------------------------------------------------------------
# doctor
# --------------------------------------------------------------------------------------

def cmd_doctor(args):
    import time
    t0 = time.monotonic()
    results = doctor.run_checks(want_gui=not args.headless)
    elapsed = time.monotonic() - t0
    summary = doctor.render(results, elapsed)
    stamp = common.stamp_dir()
    out_dir = os.path.join(common.DEMO_ROOT, stamp + '-doctor')
    common.ensure_dir(out_dir)
    common.write_json(os.path.join(out_dir, 'doctor.json'), {
        'schema': 'demo-doctor-v1', 'stamp': stamp, 'at': common.now_iso(),
        'elapsed_s': round(elapsed, 3), 'budget_s': doctor.DOCTOR_BUDGET_S,
        'headless': bool(args.headless), 'summary': summary, 'results': results,
    })
    print('[doctor] 证据：%s' % os.path.relpath(out_dir, common.ROOT))
    # 预算硬门：doctor 必须 ≤30 s（超时即判失败并报出耗时）
    if elapsed > doctor.DOCTOR_BUDGET_S:
        print('[doctor] 超预算：%.1f s > %.0f s' % (elapsed, doctor.DOCTOR_BUDGET_S),
              file=sys.stderr)
        return 2
    return 0 if summary['ok'] else 1


# --------------------------------------------------------------------------------------
# start
# --------------------------------------------------------------------------------------

def cmd_start(args):
    import start as start_mod
    backend = (args.backend or common.DEFAULT_BACKEND).strip()
    if backend not in ('full', 'lightweight'):
        return common.fail('未知 backend：%s' % backend, ['可用：full（默认）| lightweight'])
    # **空串 = 用户没指定**，必须保持空串往上传（2026-11-11 实测 bug）。
    #
    # 改造前这里把空串折成 `common.DEFAULT_MAP`（yard），于是 `launch_argv` 永远收到
    # 非空值、永远传 `world_map:=yard` —— 场景登记的地图（如 `dense_scene` → `dense_map`）
    # **永远不生效**，而且没有任何提示。实测后果：`--scene dense_scene` 跑在 `yard` 上，
    # 感知帧数 0 而场景名与期望终态看起来都"正常"。
    #
    # 现在空串一路传到底 ⇒ `main.launch.py` 走"场景登记 > 缺省"那两级；
    # 显式给 `--map` 仍然是最高优先级（覆盖场景登记）。
    wmap = (args.map or '').strip()
    _available = _world_maps()
    if wmap and wmap not in _available:
        return common.fail('未知地图：%s' % wmap, ['可用：%s' % ' | '.join(_available)])
    scene = (args.scene or '').strip() or common.DEFAULT_SCENE
    # GUI 渲染后端（ADR-0021(d)）：空 → auto。取值校验交给 gui_render_backend 模块的
    # 配置文件（它 raise ValueError），此处只做早失败，避免把非法值传到 launch 才炸。
    gui_render_backend = (args.gui_render_backend or '').strip() or 'auto'
    if gui_render_backend not in ('auto', 'd3d12', 'software'):
        return common.fail('未知 gui_render_backend：%s' % gui_render_backend,
                           ['可用：auto（默认）| d3d12 | software'])

    extra = list(args.extra or [])
    opts = {
        'headless': bool(args.headless),
        'backend': backend,
        'map': wmap,
        'scene': scene,
        'duration': (args.duration or '').strip() or None,
        'gui_render_backend': gui_render_backend,
        'ready_timeout_s': 180.0,
        'start_timeout_s': 90.0,
        'follow_timeout_s': 300.0,
        'dry_run': False,
        'extra': [],
        '_argv': args.argv.split() if args.argv else [],
    }
    for e in extra:
        if e == 'dry-run':
            opts['dry_run'] = True
        elif e.startswith('ready-timeout:'):
            opts['ready_timeout_s'] = float(e.split(':', 1)[1])
        elif e.startswith('spawn-verify-timeout:'):
            # 世界 spawn 门限（**上界，不是延时**）。密障碍地图（dense_map，数百个）
            # 实测 create 连续超时约 50 s 后才恢复应答，agc_car 需 +68 s。
            opts['spawn_verify_timeout_s'] = float(e.split(':', 1)[1])
        elif e.startswith('reset-max-attempts:'):
            # 复位就绪门次数上界（与 reset-timeout 取先到者）
            opts['startup_reset_max_attempts'] = int(e.split(':', 1)[1])
        elif e.startswith('reset-timeout:'):
            # 复位就绪门时间上界（秒）
            opts['startup_reset_timeout_s'] = float(e.split(':', 1)[1])
        elif e.startswith('start-timeout:'):
            opts['start_timeout_s'] = float(e.split(':', 1)[1])
        elif e.startswith('follow-timeout:'):
            opts['follow_timeout_s'] = float(e.split(':', 1)[1])
        elif e == 'escape':
            # 目标逃逸：只由显式参数触发，默认 static 语义不变。
            # `target_motion:=epicycle` 走 ADR-0031 的漂移轨道（参数由
            # composition.apply_target_motion_override 配置文件补齐 radius_m=1.8 等）；
            # `goal_follow_target:=true` 让任务目标跟随感知目标——否则 s04 的固定 goal
            # 在目标漂移后恒 RANGE_EXCEEDED（d_track=3.0），必然 TIMEOUT。
            # 两者都是既有 launch 参数（数值 / 任务语义），不新增路线分支。
            opts['extra'].append('target_motion:=epicycle')
            opts['extra'].append('goal_follow_target:=true')
        else:
            opts['extra'].append(e)
    if opts['duration']:
        try:
            float(opts['duration'])
        except ValueError:
            return common.fail('--duration 需要秒数：%r' % opts['duration'],
                               ['例：./run_demo.sh --duration 120'])

    # 横幅：**必须**如实打出观测指向臂（实际由场景覆盖决定，不是 CLI 传入）
    print('=' * 74)
    print('[run_demo] AGC 一键演示 · 后端=%s 地图=%s 场景=%s 形态=%s'
          % (backend, wmap or '(场景登记)', scene,
             'headless' if opts['headless'] else 'GUI'))
    print('[run_demo] 形态口径：headless = gz 无渲染客户端（-s）；RViz 语义层两种形态都起（固定）')
    print('[run_demo] 观测指向臂：observe_yaw_mode=%s（场景覆盖值：机头对准 /agc/targets 感知航迹）'
          % common.DEFAULT_OBSERVE_YAW_MODE)
    print('[run_demo]   **非** oracle 臂（不读 /agc/gt/*）；目标测量由 gt_adapter 直取真值')
    print('[run_demo] 停止：Ctrl-C 或另一个终端 ./run_demo.sh stop')
    print('=' * 74, flush=True)

    import rclpy
    rclpy.init()
    try:
        run = start_mod.DemoRun(opts)
        return run.run()
    finally:
        try:
            rclpy.shutdown()
        except Exception:      # noqa: BLE001
            pass


# --------------------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------------------

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(add_help=True)
    sub = ap.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('doctor')
    p.add_argument('--headless', action='store_true')
    p.set_defaults(fn=cmd_doctor)

    p = sub.add_parser('preflight')
    p.add_argument('--headless', default='0')
    p.set_defaults(fn=cmd_preflight)

    p = sub.add_parser('start')
    p.add_argument('--headless', default='0')
    p.add_argument('--map', default='')
    p.add_argument('--scene', default='')
    p.add_argument('--duration', default='')
    p.add_argument('--backend', default='')
    p.add_argument('--gui-render-backend', default='')
    p.add_argument('--argv', default='')
    p.add_argument('extra', nargs='*')
    p.set_defaults(fn=cmd_start)

    sub.add_parser('status').set_defaults(fn=lambda a: _status())

    sub.add_parser('stop').set_defaults(fn=lambda a: _stop())

    p = sub.add_parser('compare')
    p.add_argument('dirs', nargs='*')
    p.set_defaults(fn=lambda a: _compare(a.dirs))

    args = ap.parse_args(argv)

    def norm(v):
        """shell 传 `--headless "$HEADLESS"`（0/1 字面量），这里统一成布尔。"""
        if isinstance(v, str):
            return v.strip().lower() in ('1', 'true', 'yes', 'on')
        return bool(v)

    if args.cmd == 'start' or args.cmd == 'doctor' or args.cmd == 'preflight':
        args.headless = norm(getattr(args, 'headless', '0'))
    return args.fn(args)


def _status():
    import stop as stop_mod
    return stop_mod.status()


def _stop():
    import stop as stop_mod
    return stop_mod.stop()


def _compare(dirs):
    import compare as cmp_mod
    if len(dirs) < 2:
        return common.fail('compare 需要两个 run 目录',
                           ['./run_demo.sh compare experiments/demo/<gui> experiments/demo/<headless>'])
    return cmp_mod.main(['compare'] + list(dirs))


if __name__ == '__main__':
    sys.exit(main())
