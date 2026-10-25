#!/usr/bin/env python3
"""uxrce_participant_probe —— uXRCE「agent 侧 participant 创建耗时」重复测量探针。

背景：PX4 `uxrce_dds_client` 对 `create entities` 有 **硬编码 1 s 预算**，超时即报
`create entities failed: participant: 255`。本脚本用最小链（一个 MicroXRCEAgent +
一个 PX4 SITL SIH，无 Gazebo world、无整条 ROS 图）重复测量 agent 侧
create_client → establish_session → create_participant 的耗时，判断是否逼近 1 s。

每次 run：
  1. 预检残留 `MicroXRCEAgent` / `px4` 进程（发现即记录并放弃本次 run，不自动清理）；
  2. 记录 /dev/shm 中 fastrtps 段数量（前后各一次，不删除任何段）；
  3. 起 agent（udp4，固定端口），确认日志含 `running...`；
  4. 起 PX4 SIH，轮询日志直到 data writer 成功 / create entities failed / 超时；
  5. 按进程组收尾（先 SIGINT，再 SIGKILL），只杀自己拉起的进程组。

用法：
  source /opt/ros/jazzy/setup.bash
  python3 scripts/uxrce_participant_probe.py --runs 10
"""

import argparse
import json
import os
import re
import signal
import statistics
import subprocess
import sys
import time
from pathlib import Path

CAMPAIGN = 'w7-rl-b'
PROBE = 'uxrce_participant_probe'

RE_CREATE_CLIENT = re.compile(r'\[(\d+\.\d+)\].*create_client')
RE_ESTABLISH = re.compile(r'\[(\d+\.\d+)\].*establish_session')
RE_PARTICIPANT = re.compile(r'\[(\d+\.\d+)\].*create_participant.*participant created')

WRITER_MARK = 'created rt/fmu/out/vehicle_odometry data writer'
FAIL_MARK = 'create entities failed'


class Tail:
    """增量读取一个正在被写入的日志文件（只读，不 truncate）。"""

    def __init__(self, path):
        self.path = Path(path)
        self._fh = open(self.path, 'r', errors='ignore')
        self.text = ''

    def poll(self):
        chunk = self._fh.read()
        if chunk:
            self.text += chunk
        return self.text

    def close(self):
        try:
            self._fh.close()
        except Exception:
            pass


def scan_residual_processes():
    """返回 [(pid, comm)]，只匹配 comm 精确等于 MicroXRCEAgent / px4。"""
    try:
        out = subprocess.run(['ps', '-eo', 'pid=,comm='],
                             capture_output=True, text=True, check=False).stdout
    except OSError as exc:
        return [('ps-error', str(exc))]
    found = []
    for line in out.splitlines():
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        pid, comm = parts[0].strip(), parts[1].strip()
        if comm in ('MicroXRCEAgent', 'px4'):
            found.append((int(pid), comm))
    return found


def count_fastrtps_shm():
    try:
        return sum(1 for name in os.listdir('/dev/shm') if 'fastrtps' in name)
    except OSError:
        return None


def terminate_group(proc, sigint_wait_s):
    """只终止自己拉起的进程组（start_new_session → pgid == pid）。"""
    if proc is None:
        return None
    rc = proc.poll()
    if rc is not None:
        return rc
    pgid = proc.pid
    try:
        os.killpg(pgid, signal.SIGINT)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        return proc.wait(timeout=sigint_wait_s)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        return proc.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        return None


def git_field(repo_root, *args):
    try:
        res = subprocess.run(['git', '-C', str(repo_root), *args],
                             capture_output=True, text=True, check=False)
        return res.stdout.strip()
    except OSError:
        return ''


def first_timestamp(text, regex):
    m = regex.search(text)
    return float(m.group(1)) if m else None


def rel_path(path, repo_root):
    if path is None:
        return None
    try:
        return str(Path(path).resolve().relative_to(Path(repo_root).resolve()))
    except ValueError:
        return str(path)


def parse_agent_log(text):
    t_client = first_timestamp(text, RE_CREATE_CLIENT)
    t_session = first_timestamp(text, RE_ESTABLISH)
    t_participant = first_timestamp(text, RE_PARTICIPANT)
    session_ms = participant_create_ms = total_ms = None
    if t_client is not None and t_session is not None:
        session_ms = round((t_session - t_client) * 1000.0, 3)
    if t_session is not None and t_participant is not None:
        participant_create_ms = round((t_participant - t_session) * 1000.0, 3)
    if t_client is not None and t_participant is not None:
        total_ms = round((t_participant - t_client) * 1000.0, 3)
    return session_ms, participant_create_ms, total_ms


def px4_error_line(text):
    for line in text.splitlines():
        if 'ERROR' in line:
            return line.strip()
    for line in text.splitlines():
        if 'error while loading shared libraries' in line or 'cannot open shared object file' in line:
            return line.strip()
    return None


def run_one(index, args, repo_root, out_dir, agent_bin, px4_cwd):
    run_id = 'run_%04d' % index
    run_dir = out_dir / run_id
    (run_dir / 'log').mkdir(parents=True, exist_ok=True)
    (run_dir / 'metrics').mkdir(parents=True, exist_ok=True)

    agent_log_path = out_dir / 'log' / (run_id + '.agent.log')
    px4_log_path = out_dir / 'log' / (run_id + '.px4.log')

    rec = {
        'run': index,
        'ok': False,
        'session_ms': None,
        'participant_create_ms': None,
        'total_ms': None,
        'px4_writer_ok': False,
        'create_entities_failed': False,
        'px4_exit_code': None,
        'agent_bind_ok': False,
        'shm_before': None,
        'shm_after': None,
        'residual_before': [],
        'agent_log': rel_path(agent_log_path, repo_root),
        'px4_log': rel_path(px4_log_path, repo_root),
        'error': None,
        'px4_error_line': None,
    }

    residual = scan_residual_processes()
    rec['residual_before'] = ['pid %s %s' % (pid, comm) for pid, comm in residual]
    rec['shm_before'] = count_fastrtps_shm()

    # 预检失败：仅记录并放弃本次 run，不自动 kill 任何残留进程。
    if residual:
        rec['error'] = 'residual process(es) present: %s' % ', '.join(rec['residual_before'])
        rec['shm_after'] = count_fastrtps_shm()
        return rec

    agent_proc = None
    px4_proc = None
    agent_fh = None
    px4_fh = None
    agent_tail = None
    px4_tail = None

    try:
        agent_fh = open(agent_log_path, 'w')
        agent_cmd = [str(agent_bin), 'udp4', '-p', str(args.port), '-v', '6']
        agent_proc = subprocess.Popen(
            agent_cmd, stdout=agent_fh, stderr=subprocess.STDOUT,
            start_new_session=True, cwd=str(repo_root))
        agent_fh.flush()

        agent_tail = Tail(agent_log_path)
        started = time.time()
        wait_limit = max(args.agent_settle_s, 0.1) + 5.0
        while time.time() - started < wait_limit:
            text = agent_tail.poll()
            if 'running...' in text or agent_proc.poll() is not None:
                break
            time.sleep(0.05)
        # 按要求至少等待 agent_settle_s
        elapsed = time.time() - started
        if elapsed < args.agent_settle_s:
            time.sleep(args.agent_settle_s - elapsed)
            agent_tail.poll()

        agent_text = agent_tail.poll()
        rec['agent_bind_ok'] = 'running...' in agent_text
        if not rec['agent_bind_ok']:
            rc = agent_proc.poll()
            rec['error'] = ('agent did not log "running..."'
                            + (' (exited rc=%s)' % rc if rc is not None else ''))
            return rec

        env = os.environ.copy()
        env['PX4_SIMULATOR'] = 'sihsim'
        env['PX4_SIM_MODEL'] = 'none'
        env['PX4_UXRCE_DDS_PORT'] = str(args.port)
        env.pop('PX4_GZ_STANDALONE', None)

        px4_fh = open(px4_log_path, 'w')
        px4_proc = subprocess.Popen(
            ['./bin/px4', '-d', '-s', 'etc/init.d-posix/rcS', '-i', '0'],
            stdout=px4_fh, stderr=subprocess.STDOUT,
            start_new_session=True, cwd=str(px4_cwd), env=env)
        px4_fh.flush()

        px4_tail = Tail(px4_log_path)
        deadline = time.time() + args.px4_timeout_s
        while time.time() < deadline:
            text = px4_tail.poll()
            if WRITER_MARK in text:
                break
            if FAIL_MARK in text:
                break
            if px4_proc.poll() is not None:
                break
            time.sleep(0.05)
        rec['px4_exit_code'] = px4_proc.poll()

        if px4_proc.poll() is not None and px4_proc.returncode != 0:
            text = px4_tail.poll()
            if WRITER_MARK not in text and FAIL_MARK not in text:
                err = px4_error_line(text)
                rec['error'] = ('px4 exited early rc=%s' % px4_proc.returncode
                                + (': ' + err if err else ''))

        if px4_proc.poll() is None:
            rec['px4_exit_code'] = None  # 收尾后再填

    except Exception as exc:
        rec['error'] = '%s: %s' % (type(exc).__name__, exc)

    finally:
        # 先 PX4，后 agent；仅清理本轮自己拉起的进程组。
        px4_rc = terminate_group(px4_proc, 3.0)
        if px4_proc is not None:
            rec['px4_exit_code'] = px4_rc
        terminate_group(agent_proc, 2.0)

        for fh in (px4_fh, agent_fh):
            if fh is not None:
                try:
                    fh.flush()
                    fh.close()
                except Exception:
                    pass
        time.sleep(0.2)  # 让 agent 侧最后一行日志落盘

    px4_text = ''
    agent_text = ''
    try:
        if px4_tail is not None:
            px4_text = px4_tail.poll()
    finally:
        if px4_tail is not None:
            px4_tail.close()
    try:
        if agent_tail is not None:
            agent_text = agent_tail.poll()
    finally:
        if agent_tail is not None:
            agent_tail.close()

    rec['px4_writer_ok'] = WRITER_MARK in px4_text
    rec['create_entities_failed'] = FAIL_MARK in px4_text
    if rec['create_entities_failed']:
        for line in px4_text.splitlines():
            if FAIL_MARK in line:
                rec['error'] = line.strip()
                break
    rec['px4_error_line'] = px4_error_line(px4_text)

    (session_ms, participant_ms, total_ms) = parse_agent_log(agent_text)
    rec['session_ms'] = session_ms
    rec['participant_create_ms'] = participant_ms
    rec['total_ms'] = total_ms

    timings_ok = (session_ms is not None
                  and participant_ms is not None
                  and total_ms is not None)
    rec['ok'] = bool(timings_ok
                     and rec['agent_bind_ok']
                     and rec['px4_writer_ok']
                     and not rec['create_entities_failed'])
    if not rec['ok'] and rec['error'] is None:
        if not timings_ok:
            rec['error'] = 'agent log timestamps incomplete'
        elif not rec['px4_writer_ok']:
            rec['error'] = 'px4 did not create vehicle_odometry data writer'
    rec['shm_after'] = count_fastrtps_shm()
    return rec


def build_summary(runs):
    ok_runs = [r for r in runs if r['ok']]
    p_times = [r['participant_create_ms'] for r in runs
               if r['participant_create_ms'] is not None]
    return {
        'n_ok': len(ok_runs),
        'n_px4_writer_ok': sum(1 for r in runs if r['px4_writer_ok']),
        'participant_create_ms_median': (round(statistics.median(p_times), 3)
                                         if p_times else None),
        'participant_create_ms_max': (round(max(p_times), 3) if p_times else None),
        'n_over_1000ms': sum(1 for v in p_times if v > 1000.0),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Repeat minimal uXRCE agent+PX4(SIH) chain and measure participant creation latency.')
    parser.add_argument('--runs', type=int, default=10)
    parser.add_argument('--out-dir',
                        default='experiments/w7-rl-b/20261024-w7-rl-b-uxrce-probe')
    parser.add_argument('--port', type=int, default=8899)
    parser.add_argument('--px4-timeout-s', type=float, default=12.0)
    parser.add_argument('--agent-settle-s', type=float, default=0.8)
    parser.add_argument('--repo-root', default='/home/chen/AGC')
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    if not repo_root.is_dir():
        print('repo root not found: %s' % repo_root, file=sys.stderr)
        return 2

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = repo_root / out_dir
    out_dir = out_dir.resolve()
    (out_dir / 'log').mkdir(parents=True, exist_ok=True)
    (out_dir / 'metrics').mkdir(parents=True, exist_ok=True)

    agent_bin = repo_root / 'toolchain' / 'bin' / 'MicroXRCEAgent'
    px4_cwd = (repo_root / 'toolchain' / 'PX4-Autopilot' / 'build'
               / 'px4_sitl_default').resolve()
    px4_bin = px4_cwd / 'bin' / 'px4'
    for p in (agent_bin, px4_bin):
        if not p.exists():
            print('missing required binary: %s' % p, file=sys.stderr)
            return 2

    result = {
        'campaign': CAMPAIGN,
        'probe': PROBE,
        'git_head': git_field(repo_root, 'rev-parse', 'HEAD'),
        'git_status_short': git_field(repo_root, 'status', '--short'),
        'port': args.port,
        'runs_requested': args.runs,
        'runs': [],
        'summary': {},
    }

    for i in range(1, args.runs + 1):
        print('[run %d/%d] port=%d' % (i, args.runs, args.port), flush=True)
        try:
            rec = run_one(i, args, repo_root, out_dir, agent_bin, px4_cwd)
        except Exception as exc:  # 任何意外都不能阻止聚合 JSON 落盘
            rec = {
                'run': i, 'ok': False, 'session_ms': None,
                'participant_create_ms': None, 'total_ms': None,
                'px4_writer_ok': False, 'create_entities_failed': False,
                'px4_exit_code': None, 'agent_bind_ok': False,
                'shm_before': None, 'shm_after': None,
                'residual_before': [],
                'agent_log': None, 'px4_log': None,
                'error': '%s: %s' % (type(exc).__name__, exc),
                'px4_error_line': None,
            }
        result['runs'].append(rec)
        print('  ok=%s session_ms=%s participant_create_ms=%s px4_writer_ok=%s error=%s'
              % (rec['ok'], rec['session_ms'], rec['participant_create_ms'],
                 rec['px4_writer_ok'], rec['error']), flush=True)

    result['summary'] = build_summary(result['runs'])
    out_json = out_dir / 'metrics' / 'uxrce_probe.json'
    with open(out_json, 'w') as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
        fh.write('\n')

    print('summary: %s' % json.dumps(result['summary'], ensure_ascii=False), flush=True)
    print('wrote %s' % out_json, flush=True)
    return 0 if result['summary']['n_ok'] == args.runs else 1


if __name__ == '__main__':
    sys.exit(main())
