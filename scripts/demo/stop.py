#!/usr/bin/env python3
"""`run_demo.sh stop` —— 按记录的 PID / PGID 回收本次演示（可跨终端；幂等）。

派工单要求（[round-1](../../.coordination/task/20261030-007-p1-2-demo-entry/round-1/request.md#p1-2-r1-request) 第 3 条 /
[round-2](../../.coordination/task/20261030-007-p1-2-demo-entry/round-2/request.md#p1-2-r2-request) 继续交付）：

  * **独立进程组 + PID/PGID 归属**：只回收 `current.json` 里登记的 PGID；
  * **不能 `pkill -f`**、**不清他人进程**、**不删证据**；
  * 幂等：没有实例 / 已退出 / 重复执行 → 都返回 0 并说清楚。

回收顺序（与 `episode_runner._reap_process_group` 同源纪律）：
`SIGINT`（给 launch 与各节点优雅退出的机会，run_logger 借机落 summary）→ 轮询 →
`SIGKILL`（清理忽略 SIGINT 的游离子进程，如 gz sim）→ 轮询确认整组退出。

额外一层保护：回收后**复查**是否还有本项目特征进程落在**本实例**的 PGID 上；
若仍有（极端情况），如实报 `leaked` 并列出 PID，**不**扩大成全局扫描清除。
"""

import os
import signal
import time

import common


def stop(stream=None, force=False):
    import sys
    stream = stream or sys.stdout
    cur = common.current_instance()
    state = cur.get('state')
    pgid = cur.get('launch_pgid')
    sup = cur.get('supervisor_pid')

    def say(text):
        print('[stop] ' + text, file=stream, flush=True)

    if not cur:
        say('没有正在运行的演示（从未启动过，或状态文件已清理）')
        say('提示：若 `ps` 里仍有 gz sim / px4 / MicroXRCEAgent，那是**外部终止**留下的孤儿，'
            '按 PID 清理（禁止 pkill -f）')
        return 0

    sup_alive = common.pid_alive(sup)
    members = common.pgid_members(pgid) if pgid else []
    if state in ('finished', 'failed', 'stopped') and not members and not sup_alive:
        say('上一次演示已结束（state=%s，无进程组成员）—— 幂等返回' % state)
        return 0

    say('实例 %s：状态=%s 监督 pid=%s（%s）进程组=%s'
        % (cur.get('instance_id'), state, sup, '存活' if sup_alive else '已退出', pgid))
    if not members and not sup_alive:
        say('没有存活进程（可能已自行退出）→ 只整理状态文件')
        common.write_json(common.CURRENT_JSON, dict(cur, state='stopped',
                                                    stopped_at=common.now_iso()))
        return 0

    if members:
        say('待回收 %d 个进程：' % len(members))
        for pid, cmd in members[:12]:
            say('  pid %-7d %s' % (pid, cmd[:110]))
        if len(members) > 12:
            say('  …（共 %d 个）' % len(members))
    else:
        say('进程组已空；仅监督进程存活 → 直接终止它')

    t0 = time.monotonic()
    if members and pgid:
        res = common.reap_process_group(
            pgid, on_tick=lambda n, t: say('  仍在退出：%d 个进程（%.1fs）' % (n, t)))
    else:
        res = {'confirmed': True, 'cleaned_count': 0, 'members_after': [],
               'wall_s': 0.0, 'sigint_sent': False, 'sigkill_sent': False,
               'returncode': None, 'members_before': []}

    # 监督进程本身（若它比进程组活得久——例如被 stop 的正是前台 supervisor）
    if common.pid_alive(sup) and sup != os.getpid():
        try:
            os.kill(int(sup), signal.SIGTERM)
            deadline = time.monotonic() + 5.0
            while common.pid_alive(sup) and time.monotonic() < deadline:
                time.sleep(0.1)
            if common.pid_alive(sup):
                os.kill(int(sup), signal.SIGKILL)
            say('监督进程 %s 已终止' % sup)
        except (ProcessLookupError, PermissionError, OSError) as e:
            say('监督进程 %s 终止失败：%s' % (sup, e))

    cleaned = res.get('cleaned_count') or 0
    left = res.get('members_after') or []
    say('已清理 %d 个进程（%.1fs，SIGINT=%s SIGKILL=%s）'
        % (cleaned, res.get('wall_s') or (time.monotonic() - t0),
           '已发' if res.get('sigint_sent') else '不需要',
           '已发' if res.get('sigkill_sent') else '不需要'))
    if left:
        say('⚠ 仍有 %d 个进程未退出：' % len(left))
        for m in left[:12]:
            say('  pid %-7d %s' % (m['pid'], m['cmd'][:110]))
        say('这些进程**可能**忽略 SIGTERM/SIGKILL，或属于其它实例；请按 PID 人工确认。')
    # 证据保留：只更新状态文件，**不删** run_dir
    common.write_json(common.CURRENT_JSON, dict(
        cur, state='stopped' if not left else 'leaked',
        stopped_at=common.now_iso(),
        stop_result={'cleaned_count': cleaned, 'remaining': left,
                     'sigint_sent': res.get('sigint_sent'),
                     'sigkill_sent': res.get('sigkill_sent'),
                     'confirmed': res.get('confirmed')}))
    run_dir = cur.get('run_dir')
    if run_dir:
        note = os.path.join(run_dir, 'stop.txt')
        try:
            with open(note, 'a') as f:
                f.write('%s stop: cleaned=%d remaining=%d sigint=%s sigkill=%s\n' % (
                    common.now_iso(), cleaned, len(left),
                    res.get('sigint_sent'), res.get('sigkill_sent')))
        except OSError:
            pass
    say('证据保留：%s（stop 不删除任何产物）' % (run_dir or '?'))
    return 0 if not left else 3


def status(stream=None):
    """`run_demo.sh status`：当前实例 + 本项目残留进程（只读，不清理）。"""
    import sys
    stream = stream or sys.stdout
    cur = common.current_instance()
    if not cur:
        print('[status] 没有演示实例记录（从未启动，或状态文件已清理）', file=stream)
    else:
        sup = cur.get('supervisor_pid')
        print('[status] 实例=%s 状态=%s 形态=%s 后端=%s'
              % (cur.get('instance_id'), cur.get('state'), cur.get('mode'),
                 cur.get('backend')), file=stream)
        print('[status] 目录=%s' % cur.get('run_dir'), file=stream)
        print('[status] 监督 pid=%s（%s） 启动 pgid=%s'
              % (sup, '存活' if common.pid_alive(sup) else '已退出',
                 cur.get('launch_pgid')), file=stream)
        members = common.pgid_members(cur.get('launch_pgid'))
        print('[status] 进程组成员：%d' % len(members), file=stream)
        for pid, cmd in members[:10]:
            print('[status]   pid %-7d %s' % (pid, cmd[:110]), file=stream)
    procs = common.project_processes()
    print('[status] 本项目特征进程（全机只读扫描）：%d' % len(procs), file=stream)
    for p in procs[:10]:
        print('[status]   pid %-7d [%s] %s' % (p['pid'], p['rule'], p['cmd'][:100]), file=stream)
    if len(procs) > 10:
        print('[status]   …（共 %d 个）' % len(procs), file=stream)
    return 0
