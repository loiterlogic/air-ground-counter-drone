#!/usr/bin/env python3
"""在**实际运行**中采集 `/trajectory_tracker` 的订阅清单。

为什么必须实跑采集： 的"无 GT 指向订阅"只有**源码守卫**与**日志免责声明**两类证据，
Leader 要求补**运行拓扑证据**（`ros2 node info` 或等价运行图）。源码守卫可能被条件分支绕过，
日志文本更不是拓扑事实——只有运行时节点自报的订阅清单才是。

判据（可被直接证伪）：
 * `sub_has_gt` —— 订阅列表里**不得**出现 `/agc/gt/...`；
 * `sub_has_targets` —— 应当出现 `/agc/targets`（证明航迹输入缝真的接上了）；
 * `mode_is_track` —— 参数 `observe_yaw_mode` 的实际生效值应为 `track`。

用法：
 # 需先有 GUI track 场景在跑
    python3 scripts/g2/g2_node_topology_probe.py \
        --node /trajectory_tracker --out-dir <证据目录> --run-id <run_id>

退出码：0 采集成功且判据通过；1 采集成功但判据不通过；2 环境/用法问题。
"""

import argparse
import json
import os
import subprocess
import sys
import time


def sh(cmd, timeout=25):
    """执行只读命令，返回 (rc, stdout+stderr)。"""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or '') + (r.stderr or '')
    except subprocess.TimeoutExpired:
        return 124, '<timeout after %ss>' % timeout


def wait_node(node, deadline_s):
    """等节点出现**并且** lifecycle 进入 `active`。

 为什么必须等 active：`trajectory_tracker` 是 lifecycle 节点，**业务订阅全部在
    `on_configure_impl()` 里创建**。首次采集踩过这个坑——在 unconfigured 状态下
    `ros2 node info` 只显示 `/clock` 与 `/parameter_events`，会得出"没有 /agc/targets"的
 错误结论（实际是还没建）。
    """
    end = time.monotonic() + deadline_s
    while time.monotonic() < end:
        rc, out = sh(['ros2', 'node', 'list'], timeout=10)
        if rc == 0 and node in out:
            rc2, st = sh(['ros2', 'lifecycle', 'get', node], timeout=10)
            if rc2 == 0 and 'active' in st.lower():
                return True
        time.sleep(1.0)
    return False


def parse_subscriptions(node_info_text):
    """从 `ros2 node info` 文本里抽订阅名。

 实测格式（rclpy 的 `node info`）：节点名一行，随后是**两空格缩进**的段标题
 ` Subscribers:`，其下的条目再缩进四空格，形如
 ` /agc/targets: agc_msgs/msg/TargetTrackArray`。

 首版按"无缩进=段标题"判定，但段标题其实是**缩进两格**，于是把整个
 Subscribers 段都漏掉、得到空列表——这是解析缺陷，不是拓扑事实。
    """
    subs, in_subs = [], False
    for raw in node_info_text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())
        # 段标题：缩进 <= 2 且以冒号结尾
        if indent <= 2 and stripped.endswith(':'):
            in_subs = stripped.lower().startswith('subscribers')
            continue
        if in_subs and stripped.startswith('/'):
            # 形如 "/agc/targets: agc_msgs/msg/TargetTrackArray" → 取话题名
            subs.append(stripped.split(':', 1)[0].strip())
    return subs


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--node', default='/trajectory_tracker')
    ap.add_argument('--out-dir', required=True)
    ap.add_argument('--run-id', required=True)
    ap.add_argument('--wait-s', type=float, default=180.0,
                    help='等节点出现的最长时间（含启动预热）')
    ap.add_argument('--gt-prefix', default='/agc/gt/')
    ap.add_argument('--targets-topic', default='/agc/targets')
    args = ap.parse_args(argv)

    os.makedirs(args.out_dir, exist_ok=True)
    started = time.strftime('%Y-%m-%dT%H:%M:%S%z')

    if not wait_node(args.node, args.wait_s):
        print('ERROR: 在 %.0fs 内未发现节点 %s（运行可能未起来）' % (args.wait_s, args.node),
              file=sys.stderr)
        return 2

    rc_info, info = sh(['ros2', 'node', 'info', args.node], timeout=30)
    if rc_info != 0:
        print('ERROR: ros2 node info 失败: %s' % info[:400], file=sys.stderr)
        return 2

    rc_plist, plist = sh(['ros2', 'param', 'list', args.node], timeout=20)
    rc_pget, pget = sh(['ros2', 'param', 'get', args.node, 'observe_yaw_mode'], timeout=20)
    rc_plist_all, plist_all = sh(['ros2', 'node', 'list'], timeout=15)

    subs = parse_subscriptions(info)
    gt_subs = [s for s in subs if s.startswith(args.gt_prefix)]
    has_targets = args.targets_topic in subs
    # `ros2 param get` 输出形如：String value is: track
    mode = ''
    for token in ('track', 'target', 'velocity'):
        if pget.rstrip().endswith(token):
            mode = token
            break

    passed = (not gt_subs) and has_targets and (mode == 'track')

    stamp = time.strftime('%Y%m%dT%H%M%S')
    base = os.path.join(args.out_dir, 'node-topology-%s-%s' % (args.run_id, stamp))
    with open(base + '.txt', 'w', encoding='utf-8') as fh:
        fh.write('# G2 运行拓扑证据（只读采集）\n')
        fh.write('# 采集时刻: %s\n' % started)
        fh.write('# run_id: %s\n' % args.run_id)
        fh.write('# 节点: %s\n' % args.node)
        fh.write('# 命令: ros2 node info %s\n\n' % args.node)
        fh.write(info)
        fh.write('\n# ---- ros2 param get %s observe_yaw_mode ----\n' % args.node)
        fh.write(pget)
        fh.write('\n# ---- ros2 node list（全图） ----\n')
        fh.write(plist_all)

    summary = {
        'run_id': args.run_id,
        'collected_at': started,
        'node': args.node,
        'observe_yaw_mode': mode,
        'subscriptions': subs,
        'gt_subscriptions': gt_subs,
        'has_targets_input': has_targets,
        'params_rc': {'list': rc_plist, 'get': rc_pget},
        'passed': passed,
        'evidence_txt': base + '.txt',
    }
    with open(base + '.json', 'w', encoding='utf-8') as fh:
        json.dump(summary, fh, indent=2, ensure_ascii=False)

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
