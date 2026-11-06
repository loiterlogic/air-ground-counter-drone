#!/usr/bin/env python3
"""G2 round-6：PX4 GPS 自举时序 A/B 运行器。

**为什么需要这个包装**：`scripts/episode_runner.py` 的 `run_episode` 已经支持
`own_px4_delay_s` / `intruder_px4_delay_s` / `px4_warmup`，但 `main()` 的 argparse
**没有暴露**这三个参数（它们只被 worker 路径使用）。本轮需要在不改动公共
脚本的前提下做时序 A/B，故在此复用其函数并透传。

**不做的事**：
 * 不改 `episode_runner.py` 一行；
 * 不改 PX4 toolchain、failsafe、目标模型/高度/轨迹；
  * 只跑 `--mode gui`（用户要求今天全部 GUI），headless 会被直接拒绝。

用法：
    python3 scripts/g2/g2_px4_timing_ab.py \
        --arm baseline --own-delay 25 --intruder-delay 35 --campaign g2-placeholder-path \
        --run-id 20261101-g2-r6-ab-baseline --timeout 420

退出码：0 运行完成；1 运行异常；2 用法错误。
"""

import argparse
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--arm', required=True, help='臂名（仅用于日志/产物标识）')
    ap.add_argument('--scene', default='s08_static_none_nominal_capture')
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--mode', default='gui', choices=['gui'],
                    help='本轮只允许 gui（用户要求今天全部真实仿真带 GUI）')
    ap.add_argument('--command-source', default='baseline',
                    choices=['rl', 'baseline', 'rl_high'])
    ap.add_argument('--backend', default='full', choices=['full', 'lightweight'])
    ap.add_argument('--own-delay', type=float, default=None, help='own_px4_delay_s 覆盖')
    ap.add_argument('--intruder-delay', type=float, default=None,
                    help='intruder_px4_delay_s 覆盖')
    ap.add_argument('--px4-warmup', default=None, choices=['true', 'false'],
                    help='px4_warmup 覆盖（ADR-0027 sacrificial SIH）')
    ap.add_argument('--timeout', type=float, default=420.0)
    ap.add_argument('--wall-watchdog-s', type=float, default=None)
    ap.add_argument('--ready-timeout-s', type=float, default=220.0)
    ap.add_argument('--start-timeout-s', type=float, default=90.0)
    ap.add_argument('--campaign', default='g2-placeholder-path')
    ap.add_argument('--run-id', required=True)
    args = ap.parse_args(argv)

    wall = args.wall_watchdog_s if args.wall_watchdog_s is not None else args.timeout

    import rclpy
    import episode_runner as er

    # `run_episode` 内部会创建 rclpy 节点（用于等待 /agc/task/start 服务），
    # 但 `episode_runner.main` 才负责 `rclpy.init`；本包装直接调函数，故须自行初始化。
    rclpy.init()

    registry = er._registry()
    carriers = er._carriers()
    out_dir = os.path.join(ROOT, 'experiments', args.campaign, args.run_id)
    os.makedirs(out_dir, exist_ok=True)

    print('=== G2 A/B arm=%s scene=%s seed=%d cmd=%s backend=%s mode=%s '
          'own_delay=%s intruder_delay=%s warmup=%s ==='
          % (args.arm, args.scene, args.seed, args.command_source, args.backend,
             args.mode, args.own_delay, args.intruder_delay, args.px4_warmup))

    try:
        r = er.run_episode(
            args.scene, args.seed, registry, args.mode, wall, out_dir, carriers,
            ready_timeout_s=args.ready_timeout_s,
            command_source=args.command_source, shield='true',
            backend=args.backend,
            start_timeout_s=args.start_timeout_s,
            own_px4_delay_s=args.own_delay,
            intruder_px4_delay_s=args.intruder_delay,
            px4_warmup=args.px4_warmup,
            log_tag='ab-%s' % args.arm,
        )
    except Exception as e:                          # noqa: BLE001 - 运行器异常要如实上抛
        print('ERROR: run_episode 抛出异常: %s' % e, file=sys.stderr)
        return 1
    finally:
        rclpy.shutdown()

    print('  terminal=%s reason=%s expected_match=%s pass=%s'
          % (r.get('terminal_state'), r.get('reason_code'),
             r.get('expected_match'), r.get('pass')))
    print('  run_dir=%s' % out_dir)
    return 0


if __name__ == '__main__':
    sys.exit(main())
