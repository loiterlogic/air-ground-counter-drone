#!/usr/bin/env python3
"""w8_gui_headless_pilot —— W8-E1 GUI / headless 模式等价 pilot 编排与报告（ADR-0096）。

**定位**：本脚本只做 **GUI ↔ headless 模式等价核验**：
  * `run`：按预声明计划 `src/agc_rl/config/w8_gui_headless_plan.yaml` 逐 attempt 调用
    `scripts/w7b_arms_runner.py`（**唯一差异是 `--mode`**），全部尝试保留、不重试、不覆盖；
  * `report`：读取既有 attempt 产物，复用 `scripts/w7b_worker_repeatability.py` 的
    arms / summary / 日志解析，产出 pilot 报告或正式等价报告。

**边界**：
  * 不执行 ROS1/ROS2 对照、不进入 W8-E2、不注册 v7、不重跑 P1/P2 N=20、不启动 W7-c 扩容；
  * pilot 报告结论字段固定为 `pilot_only` / `equivalence_not_determined` /
    `headless_scale_not_authorized`；正式等价只看 95% CI 是否落入 ±δ，不以“不显著”代替“等价”；
  * 缺失产物 / 缺失字段一律记 `null` 并写进 `missing_fields` / `notes`，不崩溃、不插补。

用法：
  python3 scripts/w8_gui_headless_pilot.py run \\
    --plan src/agc_rl/config/w8_gui_headless_plan.yaml --pilot-id <id> --scene all --phase pilot
  python3 scripts/w8_gui_headless_pilot.py run ... --dry-run        # 只打印序列与命令，不落盘
  python3 scripts/w8_gui_headless_pilot.py report \\
    --pilot-id <id> --phase pilot --out-run-id <id>

产物：
  * pilot：`experiments/<campaign>/<pilot_id>/attempts.json` +
    `metrics/gui_headless_pilot.{json,md}`；
  * 正式等价：`.../metrics/gui_headless_equivalence.{json,md}`。
"""

import argparse
import hashlib
import json
import math
import os
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import w7b_worker_repeatability as rep  # noqa: E402 - 同目录复用只读解析，避免两套口径

from scipy import stats as scipy_stats  # noqa: E402

ROOT = '/home/chen/AGC'
DEFAULT_PLAN = 'src/agc_rl/config/w8_gui_headless_plan.yaml'
PLAN_KEY = 'w8_gui_headless_plan'
MODE_TAGS = {'headless': 'h', 'gui': 'g'}
SUCCESS_TERMINALS = rep.OK_TERMINALS          # INTERCEPT_CONFIRMED / TRACKING_SUCCESS
MISSION_TERMINALS = SUCCESS_TERMINALS + ('MISSION_FAILED',)
Z_975 = 1.959964
Z_80 = 0.841621
OBS_HORIZON_FALLBACK_S = 60.0

# 逐 attempt 连续指标（报告里给 n / mean / median / SD / min / max / IQR）
CONTINUOUS_METRICS = [
    'active_fco', 'active_visibility', 'env_occ_given_visible',
    'window_enter_s', 'window_leave_s', 'window_duration_s',
    'first_fco_rel_s', 'first_envelope_rel_s', 'capture_t_s',
    'n_shots', 'first_shot_t_s', 'flight_s', 'min_clearance_m',
    'intervention_segments', 'intervention_duration_s', 'intervention_ticks_ratio',
    'clearance_min_at_intervention_m', 'rtf', 'wall_elapsed_s',
]
KEY_DRIFT_METRICS = [
    'active_fco', 'active_visibility', 'first_fco_rel_s', 'capture_t_s',
    'rtf', 'wall_elapsed_s',
]
# 缺失判定字段：非发生事件（first FCO / capture / shot）不在此列，另行统计 occurrence
MISSING_CHECK_FIELDS = [
    'terminal_state', 'reason_code', 'outcome_class', 'active_fco', 'active_visibility',
    'window_enter_s', 'window_leave_s', 'window_duration_s', 'n_shots', 'rtf',
    'wall_elapsed_s', 'event_identity_rejects', 'lifecycle',
]
LIFECYCLE_FIELDS = (
    'n_fired', 'n_unresolved', 'n_duplicated', 'n_over_bound', 'n_absurd_miss_dist',
)


# --------------------------------------------------------------------------- 通用

def fmt(v, pattern='%.4f'):
    return rep.fmt(v, pattern)


def md_table(headers, rows):
    return rep.md_table(headers, rows)


def safe_div(a, b):
    return rep.safe_div(a, b)


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')


def parse_iso(text):
    try:
        return datetime.fromisoformat(str(text))
    except (TypeError, ValueError):
        return None


def _to_mean(values):
    vals = [float(v) for v in values if v is not None]
    return statistics.fmean(vals) if vals else None


def _to_stdev(values):
    vals = [float(v) for v in values if v is not None]
    return statistics.stdev(vals) if len(vals) >= 2 else None


def _quantile(vals, q):
    """线性插值分位数（避免额外依赖；n==1 返回该值）。"""
    if not vals:
        return None
    if len(vals) == 1:
        return float(vals[0])
    pos = (len(vals) - 1) * q
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(vals) - 1)
    frac = pos - lo
    return float(vals[lo]) * (1.0 - frac) + float(vals[hi]) * frac


def numeric_stats(values):
    vals = sorted(float(v) for v in values if v is not None)
    if not vals:
        return {'n': 0, 'mean': None, 'median': None, 'stdev': None,
                'min': None, 'max': None, 'iqr': None}
    iqr = None
    if len(vals) >= 2:
        iqr = _quantile(vals, 0.75) - _quantile(vals, 0.25)
    return {
        'n': len(vals),
        'mean': statistics.fmean(vals),
        'median': statistics.median(vals),
        'stdev': statistics.stdev(vals) if len(vals) >= 2 else None,
        'min': vals[0],
        'max': vals[-1],
        'iqr': iqr,
    }


def welch_ci(gui_values, head_values):
    """两样本 Welch 均值差的 95% CI（描述性用；正式判定另加 TOST 单侧 p）。"""
    g = [float(v) for v in gui_values if v is not None]
    h = [float(v) for v in head_values if v is not None]
    out = {'n_gui': len(g), 'n_headless': len(h), 'delta': None,
           'ci_low': None, 'ci_high': None, 'se': None, 'df': None, 'note': ''}
    if not g or not h:
        out['note'] = '一侧无可用值'
        return out
    out['delta'] = statistics.fmean(g) - statistics.fmean(h)
    if len(g) < 2 or len(h) < 2:
        out['note'] = '每侧至少 2 个值才能给 CI'
        return out
    vg = statistics.variance(g) / len(g)
    vh = statistics.variance(h) / len(h)
    se = math.sqrt(vg + vh)
    out['se'] = se
    if se == 0.0:
        out['ci_low'] = out['delta']
        out['ci_high'] = out['delta']
        out['df'] = len(g) + len(h) - 2
        out['note'] = 'SE=0，CI 退化为点估计'
        return out
    df = (vg + vh) ** 2 / ((vg ** 2) / (len(g) - 1) + (vh ** 2) / (len(h) - 1))
    tcrit = scipy_stats.t.ppf(0.975, df)
    out['df'] = df
    out['ci_low'] = out['delta'] - tcrit * se
    out['ci_high'] = out['delta'] + tcrit * se
    return out


def required_n(sigma_gui, sigma_headless, delta, delta_pilot):
    """等价检验样本量：n = ceil((z_.975+z_.80)^2 (σ_g^2+σ_h^2) / (δ-|Δ_pilot|)^2)。"""
    if sigma_gui is None or sigma_headless is None or delta is None \
            or delta_pilot is None:
        return None, 'not_computable（σ 或 δ / Δpilot 缺失）'
    if delta <= 0:
        return None, 'not_computable（δ <= 0）'
    if abs(delta_pilot) >= delta:
        return None, 'infeasible（|Δpilot| >= δ，增大 n 不可解）'
    denom = delta - abs(delta_pilot)
    n = math.ceil((Z_975 + Z_80) ** 2 * (sigma_gui ** 2 + sigma_headless ** 2)
                  / (denom ** 2))
    return max(n, 1), None


def formal_equivalence_decision(gui_values, head_values, delta_bound):
    """等价判定：95% CI 完全落入 ±δ 且两个单侧 p < 0.05（交集-并集）。"""
    g = [float(v) for v in gui_values if v is not None]
    h = [float(v) for v in head_values if v is not None]
    out = {'delta_bound': delta_bound, 'n_gui': len(g), 'n_headless': len(h),
           'delta': None, 'ci_low': None, 'ci_high': None,
           'p_lower': None, 'p_upper': None, 'se': None, 'df': None,
           'status': 'not_evaluable', 'note': ''}
    if delta_bound is None:
        out['note'] = 'δ 缺失，无法判定'
        return out
    if len(g) < 2 or len(h) < 2:
        out['note'] = '每侧至少 2 个值，否则 not_evaluable'
        return out
    ci = welch_ci(g, h)
    for key in ('delta', 'ci_low', 'ci_high', 'se', 'df'):
        out[key] = ci.get(key)
    if out['delta'] is None:
        out['note'] = '均值缺失'
        return out
    if abs(out['delta']) >= delta_bound:
        out['status'] = 'infeasible'
        out['note'] = '|Δ| >= δ，等价不可达（不得靠增大 n 解决）'
        return out
    if out['se'] in (None, 0.0):
        out['p_lower'] = 0.0
        out['p_upper'] = 0.0
    else:
        tdist = scipy_stats.t(out['df'])
        out['p_lower'] = float(1.0 - tdist.cdf((out['delta'] + delta_bound) / out['se']))
        out['p_upper'] = float(tdist.cdf((out['delta'] - delta_bound) / out['se']))
    inside = (out['ci_low'] is not None and out['ci_high'] is not None
              and out['ci_low'] > -delta_bound and out['ci_high'] < delta_bound)
    both_p = (out['p_lower'] is not None and out['p_upper'] is not None
              and out['p_lower'] < 0.05 and out['p_upper'] < 0.05)
    out['status'] = 'equivalent' if (inside and both_p) else 'not_equivalent'
    if not inside:
        out['note'] = '95% CI 未完全落入 ±δ'
    elif not both_p:
        out['note'] = '单侧 p >= 0.05'
    return out


def write_json_atomic(path, doc):
    """临时文件 + os.replace，避免半写 attempts.json。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.tmp-', suffix='.json', dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


# --------------------------------------------------------------------------- 计划 / 编排

def load_plan_doc(repo_root, plan_path):
    path = plan_path if os.path.isabs(plan_path) else os.path.join(repo_root, plan_path)
    with open(path, 'rb') as f:
        raw = f.read()
    sha = hashlib.sha256(raw).hexdigest()
    doc = yaml.safe_load(raw.decode('utf-8')) or {}
    plan = doc.get(PLAN_KEY)
    if not isinstance(plan, dict):
        raise ValueError('计划缺少 %s 根键：%s' % (PLAN_KEY, path))
    return plan, {'path': path, 'sha256': sha}


def resolve_n_per_mode(formal):
    """n_per_mode 可为 int 或 metric→int；多 co-primary 时取最大。"""
    raw = (formal or {}).get('n_per_mode')
    if isinstance(raw, bool) or raw is None:
        return None
    if isinstance(raw, (int, float)):
        return int(raw)
    if isinstance(raw, dict):
        vals = [int(v) for v in raw.values() if isinstance(v, (int, float))]
        return max(vals) if vals else None
    return None


def build_mode_sequence(plan, scene_tag, phase):
    """按预声明顺序返回 mode 列表；pilot 原样使用，formal 优先用 v2 alternation。"""
    pilot = plan.get('pilot') or {}
    base = (pilot.get('alternation') or {}).get(scene_tag)
    if not isinstance(base, list) or not base:
        raise ValueError('计划缺少 pilot.alternation.%s' % scene_tag)
    base = list(base)
    if phase == 'pilot':
        return base

    formal = plan.get('formal_equivalence') or {}
    defined = (formal.get('alternation') or {}).get(scene_tag)
    if isinstance(defined, list) and defined:
        return list(defined)

    n = resolve_n_per_mode(formal)
    if n is None:
        raise ValueError('formal_equivalence.n_per_mode 缺失，无法生成正式序列')
    if not all(m in MODE_TAGS for m in base):
        raise ValueError('pilot.alternation.%s 含未知 mode：%r' % (scene_tag, base))
    if 'headless' not in base or 'gui' not in base:
        raise ValueError('pilot.alternation.%s 未同时含 gui / headless，无法扩展到 n' % scene_tag)

    seq, counts, guard = [], {'headless': 0, 'gui': 0}, 0
    while counts['headless'] < n or counts['gui'] < n:
        mode = base[guard % len(base)]
        seq.append(mode)
        counts[mode] += 1
        guard += 1
        if guard > 100000:
            raise ValueError('formal 序列生成超限（alternation 可能不平衡）')
    return seq


def build_command(campaign, run_id, mode, arm, seed, scene_name, fixed):
    backend = fixed.get('gui_render_backend')
    if backend == 'mesa_d3d12_x11':
        backend_arg = 'd3d12'
    elif backend in ('auto', 'd3d12', 'software'):
        backend_arg = backend
    else:
        # base plan v1 的 GUI 条件 = 软件渲染；保持其可复现性，不因项目默认 auto 而漂移。
        backend_arg = 'software'
    return [
        'python3', 'scripts/w7b_arms_runner.py',
        '--campaign', str(campaign),
        '--run-id', str(run_id),
        '--mode', str(mode),
        '--gui-render-backend', backend_arg,
        '--arms', str(arm),
        '--seeds', str(seed),
        '--scene', str(scene_name),
        '--infra-retries', str(int(fixed['infra_retries'])),
        '--obs-horizon-s', str(fixed['obs_horizon_s']),
        '--timeout', str(fixed['timeout_s']),
        '--ready-timeout-s', str(fixed['ready_timeout_s']),
        '--start-timeout-s', str(fixed['start_timeout_s']),
    ]


def make_attempt_plan(plan, pilot_id, phase, scene_tags):
    """把预声明序列展开为逐 attempt 计划（顺序不改）。"""
    campaign = plan.get('campaign') or 'w8-parity'
    conditions = (plan.get('pilot') or {}).get('conditions') or {}
    fixed = plan.get('fixed_conditions') or {}
    for key in ('infra_retries', 'obs_horizon_s', 'timeout_s',
                'ready_timeout_s', 'start_timeout_s'):
        if key not in fixed:
            raise ValueError('fixed_conditions.%s 缺失' % key)

    items = []
    for tag in scene_tags:
        cond = conditions.get(tag)
        if not cond:
            raise ValueError('计划缺少 pilot.conditions.%s' % tag)
        modes = build_mode_sequence(plan, tag, phase)
        counts = {'headless': 0, 'gui': 0}
        for order, mode in enumerate(modes, start=1):
            if mode not in MODE_TAGS:
                raise ValueError('未知 mode：%r' % (mode,))
            counts[mode] += 1
            run_id = '%s-%s-%s-%02d' % (pilot_id, tag, MODE_TAGS[mode], counts[mode])
            items.append({
                'phase': phase,
                'scene': tag,
                'scene_name': cond['scene'],
                'arm': cond['arm'],
                'seed': cond['seed'],
                'mode': mode,
                'order': order,
                'run_id': run_id,
                'attempt_dir': os.path.join('experiments', campaign, run_id),
                'command': build_command(campaign, run_id, mode, cond['arm'],
                                         cond['seed'], cond['scene'], fixed),
            })
    return campaign, items


# --------------------------------------------------------------------------- run

def load_attempts(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        doc = json.load(f)
    if isinstance(doc, list):
        return doc
    return doc.get('attempts') or []


def read_arms_row(run_dir, seed):
    path = os.path.join(run_dir, 'metrics', 'arms.json')
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            arms = (json.load(f).get('arms') or [])
    except Exception:  # noqa: BLE001 - 缺失 / 损坏一律按缺失处理
        return None
    return rep.select_arm_row(arms, seed)


def collect_environment():
    keys = ('DISPLAY', 'WAYLAND_DISPLAY', 'XDG_SESSION_TYPE', 'XDG_CURRENT_DESKTOP')
    return {k: os.environ.get(k) for k in keys}


def read_ogre2_renderer():
    """读取最近一次 GUI 运行的 Ogre2 渲染器设备名（验证 D3D12 是否生效）。"""
    path = os.path.expanduser('~/.gz/rendering/ogre2.log')
    if not os.path.exists(path):
        return None
    try:
        with open(path, errors='ignore') as f:
            lines = f.read().splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        if 'Device Name:' in line:
            return line.split('Device Name:', 1)[1].strip()
        if 'GL_RENDERER' in line:
            return line.split('=', 1)[-1].strip()
    return None


def print_dry_run(meta, pilot_id, phase, scene_tags, campaign, items):
    print('[dry-run] phase=%s pilot_id=%s campaign=%s' % (phase, pilot_id, campaign))
    print('[dry-run] plan=%s sha256=%s' % (meta['path'], meta['sha256']))
    for tag in scene_tags:
        sub = [it for it in items if it['scene'] == tag]
        print('\nscene %s（%s）：%d attempts' % (tag, sub[0]['scene_name'], len(sub)))
        print('  预声明顺序：' + ' -> '.join('%s%s' % (MODE_TAGS[it['mode']], it['order'])
                                             for it in sub))
        for it in sub:
            print('  [%02d] %-8s run_id=%-52s %s' % (
                it['order'], it['mode'], it['run_id'], ' '.join(it['command'])))
    print('\n[dry-run] 合计 %d attempts（%s）；未创建任何目录 / 未启动任何子进程。' % (
        len(items), '，'.join('%s %d' % (t, sum(1 for it in items if it['scene'] == t))
                             for t in scene_tags)))


def cmd_run(args):
    repo_root = os.path.abspath(args.repo_root)
    try:
        plan, meta = load_plan_doc(repo_root, args.plan)
    except Exception as exc:  # noqa: BLE001 - 计划不可读即拒绝运行
        print('拒绝运行：计划读取失败：%r' % (exc,), file=sys.stderr)
        return 2

    phase = args.phase
    if phase == 'pilot':
        if plan.get('status') != 'frozen_before_runs':
            print('拒绝运行：phase=pilot 要求 status=frozen_before_runs（当前 %r）'
                  % plan.get('status'), file=sys.stderr)
            return 2
    else:
        formal = plan.get('formal_equivalence') or {}
        try:
            version = int(plan.get('version') or 0)
        except (TypeError, ValueError):
            version = 0
        if version < 2 or formal.get('status') != 'frozen_before_runs':
            print('拒绝运行：phase=formal 要求 plan version>=2 且 '
                  'formal_equivalence.status=frozen_before_runs（当前 version=%s status=%r）'
                  % (version, formal.get('status')), file=sys.stderr)
            return 2

    scene_tags = ['p1', 'p2'] if args.scene == 'all' else [args.scene]
    try:
        campaign, items = make_attempt_plan(plan, args.pilot_id, phase, scene_tags)
    except ValueError as exc:
        print('拒绝运行：%s' % exc, file=sys.stderr)
        return 2

    if args.dry_run:
        print_dry_run(meta, args.pilot_id, phase, scene_tags, campaign, items)
        return 0

    pilot_root = os.path.join(repo_root, 'experiments', campaign, args.pilot_id)
    attempts_path = os.path.join(pilot_root, 'attempts.json')
    existing = load_attempts(attempts_path)
    if args.resume:
        # 机器中断恢复：只补跑 attempts.json 中缺失的预声明 attempt，不重复已完成的 attempt。
        existing_ids = {a.get('run_id') for a in existing if a.get('phase') == phase}
        items = [it for it in items if it['run_id'] not in existing_ids]
        if not items:
            print('无缺失 attempt：phase=%s scene=%s' % (phase, ','.join(scene_tags)))
            return 0
    else:
        duplicates = [a for a in existing
                      if a.get('phase') == phase and a.get('scene') in scene_tags]
        if duplicates:
            print('拒绝运行：attempts.json 已有同 (phase=%s, scene=%s) 的 attempt，'
                  '不允许覆盖 / 续跑：%s' % (
                      phase, ','.join(scene_tags),
                      ', '.join(str(a.get('run_id')) for a in duplicates)), file=sys.stderr)
            print('提示：机器中断恢复请加 --resume（仅补跑缺失 attempt）。', file=sys.stderr)
            return 2
    for it in items:
        if os.path.exists(os.path.join(repo_root, it['attempt_dir'])):
            print('拒绝运行：attempt 目录已存在，不允许覆盖：%s' % it['attempt_dir'],
                  file=sys.stderr)
            return 2

    for sub in ('config', 'log', 'metrics'):
        os.makedirs(os.path.join(pilot_root, sub), exist_ok=True)
    fixed = plan.get('fixed_conditions') or {}
    gui_render_backend = fixed.get('gui_render_backend') or 'default'
    gui_render_env = {str(k): str(v) for k, v in (fixed.get('gui_render_env') or {}).items()}
    env_doc = {'captured_at': now_iso(), 'plan': meta['path'],
               'plan_sha256': meta['sha256'],
               'gui_render_backend': gui_render_backend,
               'gui_render_env': gui_render_env,
               'graphics': collect_environment()}
    env_path = os.path.join(pilot_root, 'config', 'environment.json')
    if not os.path.exists(env_path):
        # 首次 run 捕获的图形环境作为基准；后续 phase 另存，避免覆盖基线
        with open(env_path, 'w') as f:
            json.dump(env_doc, f, ensure_ascii=False, indent=2)
    with open(os.path.join(pilot_root, 'config',
                           'environment-%s.json' % phase), 'w') as f:
        json.dump(env_doc, f, ensure_ascii=False, indent=2)

    attempts = list(existing)
    n_exec_errors = 0
    for it in items:
        console_rel = os.path.join('experiments', campaign, args.pilot_id,
                                   'log', it['run_id'] + '.console.log')
        console_abs = os.path.join(repo_root, console_rel)
        record = {
            'run_id': it['run_id'], 'phase': phase, 'scene': it['scene'],
            'scene_name': it['scene_name'], 'arm': it['arm'], 'seed': it['seed'],
            'mode': it['mode'], 'order': it['order'],
            'render_backend': 'default', 'render_env': {}, 'renderer': None,
            'started_at': now_iso(), 'ended_at': None,
            'wall_elapsed_s': None, 'subprocess_elapsed_s': None,
            'exit_code': None, 'command': list(it['command']),
            'console_log': console_rel, 'attempt_dir': it['attempt_dir'],
            'terminal_state': None, 'reason_code': None, 'outcome_class': None,
            'infra_retries_used': None, 'rtf': None, 'note': None,
        }
        run_env = dict(os.environ)
        if it['mode'] == 'gui' and gui_render_backend == 'mesa_d3d12_x11':
            for key, val in gui_render_env.items():
                run_env[key] = val
            record['render_backend'] = gui_render_backend
            record['render_env'] = {k: run_env.get(k) for k in gui_render_env}
        t0 = time.monotonic()
        try:
            with open(console_abs, 'w') as fh:
                proc = subprocess.run(it['command'], cwd=repo_root, shell=False,
                                      stdout=fh, stderr=subprocess.STDOUT, timeout=900,
                                      env=run_env)
            record['exit_code'] = proc.returncode
            if proc.returncode != 0:
                record['note'] = 'runner 退出码 %d' % proc.returncode
        except subprocess.TimeoutExpired:
            record['note'] = '子进程超过 900 s 被终止'
            n_exec_errors += 1
        except OSError as exc:
            record['note'] = '子进程启动失败：%r' % (exc,)
            n_exec_errors += 1
        record['subprocess_elapsed_s'] = round(time.monotonic() - t0, 3)
        record['wall_elapsed_s'] = record['subprocess_elapsed_s']
        record['ended_at'] = now_iso()
        if it['mode'] == 'gui':
            record['renderer'] = read_ogre2_renderer()

        row = read_arms_row(os.path.join(repo_root, it['attempt_dir']), it['seed'])
        if row:
            record['terminal_state'] = row.get('terminal_state')
            record['reason_code'] = row.get('reason_code')
            record['outcome_class'] = row.get('outcome_class')
            record['infra_retries_used'] = row.get('infra_retries_used')
            record['rtf'] = row.get('rtf')
            if row.get('wall_elapsed_s') is not None:
                record['wall_elapsed_s'] = row.get('wall_elapsed_s')
        else:
            note = 'arms.json 缺失，终态 / 指标记 null'
            record['note'] = ('%s；%s' % (record['note'], note)
                              if record['note'] else note)

        attempts.append(record)
        write_json_atomic(attempts_path, {
            'generated_by': 'scripts/w8_gui_headless_pilot.py',
            'pilot_id': args.pilot_id, 'campaign': campaign,
            'updated_at': now_iso(), 'attempts': attempts,
        })
        print('[%02d] %s scene=%s mode=%-8s terminal=%s outcome=%s exit=%s wall=%s s' % (
            it['order'], it['run_id'], it['scene'], it['mode'],
            record['terminal_state'], record['outcome_class'],
            record['exit_code'], fmt(record['wall_elapsed_s'], '%.1f')))

    new_ids = {i['run_id'] for i in items}
    new_records = [a for a in attempts if a.get('run_id') in new_ids]
    print('\n=== %s 完成：attempts=%d；%s；infra=%d、timeout=%d、执行错误=%d ===' % (
        phase, len(items),
        '，'.join('%s=%d' % (tag, sum(1 for i in items if i['scene'] == tag))
                 for tag in scene_tags),
        sum(1 for a in new_records if a.get('outcome_class') == 'infra'),
        sum(1 for a in new_records if a.get('terminal_state') == 'MISSION_FAILED'
            and a.get('reason_code') == 'TIMEOUT'),
        n_exec_errors))
    return 0


# --------------------------------------------------------------------------- 逐 attempt 记录

def classify_attempt(rec):
    """写入 infra / timeout / mission_attempt 三个判定字段。"""
    terminal = rec.get('terminal_state')
    reason = rec.get('reason_code')
    outcome = rec.get('outcome_class')
    is_infra = bool(outcome == 'infra' or terminal == 'INFRA_FAILURE')
    rec['is_infra'] = is_infra
    rec['is_timeout'] = bool(terminal == 'MISSION_FAILED' and reason == 'TIMEOUT')
    rec['mission_attempt'] = bool((not is_infra) and terminal in MISSION_TERMINALS)
    return rec


def read_summary(run_dir, case):
    path = case.get('summary_path')
    if not path or not os.path.exists(path):
        local = os.path.join(run_dir, 'metrics', 'summary.json')
        path = local if os.path.exists(local) else None
    if not path:
        return {}
    try:
        with open(path) as f:
            return json.load(f) or {}
    except Exception:  # noqa: BLE001
        return {}


def build_attempt_record(repo_root, campaign, attempt):
    """逐 attempt 报告记录：复用 load_case，再从 arms / summary 直读解析器未暴露字段。"""
    run_id = attempt.get('run_id')
    seed = attempt.get('seed')
    case = rep.load_case(repo_root, campaign, label=run_id, run_id=run_id,
                         worker=None, seed=seed)
    run_dir = os.path.join(repo_root, 'experiments', campaign, run_id)
    row = read_arms_row(run_dir, seed) or {}
    summary = read_summary(run_dir, case)
    attr = summary.get('command_attribution') or {}
    ew = summary.get('episode_window_metrics') or {}
    lifecycle = case.get('lifecycle') or {}

    terminal = case.get('terminal_state') or attempt.get('terminal_state')
    reason = case.get('reason_code') or attempt.get('reason_code')
    outcome = case.get('outcome_class') or attempt.get('outcome_class')

    first_fco = case.get('first_fco_rel_s')
    capture_t = case.get('capture_t_s')
    min_clearance = row.get('min_clearance_m')
    if min_clearance is None:
        min_clearance = attr.get('clearance_min_m')
    intervention_duration = attr.get('intervention_duration_s')
    if intervention_duration is None:
        intervention_duration = summary.get('intervention_duration_s')
    wall = row.get('wall_elapsed_s')
    if wall is None:
        wall = attempt.get('wall_elapsed_s')

    rec = {
        'label': run_id, 'run_id': run_id,
        'phase': attempt.get('phase'), 'scene': attempt.get('scene'),
        'scene_name': attempt.get('scene_name') or case.get('scene'),
        'arm': attempt.get('arm') or case.get('arm'),
        'seed': (attempt.get('seed') if attempt.get('seed') is not None
                 else case.get('seed')),
        'mode': attempt.get('mode'), 'order': attempt.get('order'),
        'render_backend': attempt.get('render_backend'),
        'renderer': attempt.get('renderer'),
        'terminal_state': terminal, 'reason_code': reason, 'outcome_class': outcome,
        'active_fco': case.get('active_fco'),
        'active_visibility': case.get('active_visibility'),
        'env_occ_given_visible': case.get('env_occ_given_visible'),
        'window_enter_s': case.get('window_enter_s'),
        'window_leave_s': case.get('window_leave_s'),
        'window_duration_s': case.get('window_duration_s'),
        'first_fco_rel_s': first_fco,
        'first_fco_occurred': first_fco is not None,
        'first_fco_occurrence': int(first_fco is not None),
        'first_envelope_rel_s': case.get('first_envelope_rel_s'),
        'capture_t_s': capture_t,
        'capture_occurred': capture_t is not None,
        'capture_success': int(terminal == 'INTERCEPT_CONFIRMED'),
        'n_shots': case.get('n_shots'), 'first_shot_t_s': case.get('first_shot_t_s'),
        'flight_s': case.get('flight_s'), 'min_clearance_m': min_clearance,
        'intervention_segments': attr.get('intervention_segments'),
        'intervention_duration_s': intervention_duration,
        'intervention_ticks_ratio': ew.get('intervention_ticks_ratio'),
        'clearance_min_at_intervention_m': attr.get('clearance_min_at_intervention_m'),
        'rtf': (case.get('rtf') if case.get('rtf') is not None
                else attempt.get('rtf')),
        'wall_elapsed_s': wall,
        'event_identity_rejects': case.get('event_identity_rejects'),
        'lifecycle': ({k: lifecycle.get(k) for k in LIFECYCLE_FIELDS}
                      if lifecycle else None),
        'notes': list(attempt.get('notes') or []) + list(case.get('notes') or []),
    }
    classify_attempt(rec)
    missing = set(case.get('missing_fields') or [])
    missing |= {f for f in MISSING_CHECK_FIELDS if rec.get(f) is None}
    rec['missing_fields'] = sorted(missing)
    return rec


# --------------------------------------------------------------------------- 汇总

def metric_value(rec, metric):
    if metric == 'timeout_rate':
        return 1.0 if rec.get('is_timeout') else 0.0
    if metric == 'capture_success_rate':
        return float(rec.get('capture_success') or 0)
    if metric == 'first_fco_occurrence_rate':
        return 1.0 if rec.get('first_fco_occurred') else 0.0
    return rec.get(metric)


def summarize_records(records):
    mission = [r for r in records if r.get('mission_attempt')]
    n_mission = len(mission)
    n_infra = sum(1 for r in records if r.get('is_infra'))
    n_timeout = sum(1 for r in mission if r.get('is_timeout'))
    n_capture = sum(1 for r in mission if r.get('capture_success') == 1)
    n_success = sum(1 for r in mission if r.get('terminal_state') in SUCCESS_TERMINALS)
    n_fco = sum(1 for r in mission if r.get('first_fco_occurred'))
    return {
        'n_attempts': len(records), 'n_mission': n_mission, 'n_infra': n_infra,
        'n_timeout': n_timeout, 'n_capture_success': n_capture,
        'mission_success_rate': safe_div(n_success, n_mission),
        'timeout_rate': safe_div(n_timeout, n_mission),
        'capture_success_rate': safe_div(n_capture, n_mission),
        'first_fco_occurrence_rate': safe_div(n_fco, n_mission),
        'metrics': {m: numeric_stats([metric_value(r, m) for r in mission])
                    for m in CONTINUOUS_METRICS},
    }


def build_summaries(records):
    scenes = sorted({r.get('scene') for r in records if r.get('scene')})
    out = {}
    for scene in scenes:
        by_mode = {}
        for mode in ('gui', 'headless'):
            subset = [r for r in records
                      if r.get('scene') == scene and r.get('mode') == mode]
            if subset:
                by_mode[mode] = summarize_records(subset)
        out[scene] = by_mode
    return out


def mission_values(records, scene, mode, metric):
    return [metric_value(r, metric) for r in records
            if r.get('scene') == scene and r.get('mode') == mode
            and r.get('mission_attempt') and metric_value(r, metric) is not None]


def build_mode_differences(records):
    """描述性 Δ = mean(GUI) − mean(headless)；不作等价判定。"""
    scenes = sorted({r.get('scene') for r in records if r.get('scene')})
    out = {}
    for scene in scenes:
        per = {}
        for metric in CONTINUOUS_METRICS:
            g = mission_values(records, scene, 'gui', metric)
            h = mission_values(records, scene, 'headless', metric)
            ci = welch_ci(g, h) if g and h else None
            median_diff = None
            if g and h:
                median_diff = statistics.median(g) - statistics.median(h)
            per[metric] = {
                'n_gui': len(g), 'n_headless': len(h),
                'mean_gui': _to_mean(g), 'mean_headless': _to_mean(h),
                'delta': ci['delta'] if ci else None,
                'median_difference': median_diff,
                'ci_low': ci['ci_low'] if ci else None,
                'ci_high': ci['ci_high'] if ci else None,
                'se': ci['se'] if ci else None,
                'df': ci['df'] if ci else None,
                'note': (ci['note'] if ci else '一侧无可用值'),
            }
        out[scene] = per
    return out


def build_cost(records):
    scenes = sorted({r.get('scene') for r in records if r.get('scene')})
    out = {'per_scene_mode': {}, 'total': {}}
    for scene in scenes:
        per = {}
        for mode in ('gui', 'headless'):
            subset = [r for r in records
                      if r.get('scene') == scene and r.get('mode') == mode]
            per[mode] = {
                'n': len(subset),
                'wall_elapsed_s': numeric_stats([r.get('wall_elapsed_s') for r in subset]),
                'rtf': numeric_stats([r.get('rtf') for r in subset]),
            }
        gui_wall = per['gui']['wall_elapsed_s']['median']
        head_wall = per['headless']['wall_elapsed_s']['median']
        per['gui_over_headless_wall_ratio'] = safe_div(gui_wall, head_wall)
        out['per_scene_mode'][scene] = per

    starts = [parse_iso(r.get('started_at')) for r in records]
    ends = [parse_iso(r.get('ended_at')) for r in records]
    starts = [s for s in starts if s]
    ends = [e for e in ends if e]
    span = None
    if starts and ends:
        span = (max(ends) - min(starts)).total_seconds()
    out['total'] = {
        'sum_attempt_wall_s': sum(r.get('wall_elapsed_s') or 0.0 for r in records),
        'pilot_span_wall_s': span,
        'n_attempts': len(records),
    }
    return out


def build_drift(records):
    """attempt order 与关键指标的 Spearman 相关（每 scene × mode，n>=3）。"""
    scenes = sorted({r.get('scene') for r in records if r.get('scene')})
    out = {}
    for scene in scenes:
        per = {}
        for mode in ('gui', 'headless'):
            subset = [r for r in records
                      if r.get('scene') == scene and r.get('mode') == mode]
            metrics = {}
            for metric in KEY_DRIFT_METRICS:
                pairs = [(r.get('order'), metric_value(r, metric)) for r in subset]
                pairs = [(o, v) for o, v in pairs if o is not None and v is not None]
                if len(pairs) < 3 or len({v for _, v in pairs}) < 2:
                    metrics[metric] = {'n': len(pairs), 'rho': None, 'p': None,
                                       'note': 'n<3 或值恒定，不评估'}
                    continue
                res = scipy_stats.spearmanr([p[0] for p in pairs],
                                            [p[1] for p in pairs])
                metrics[metric] = {'n': len(pairs), 'rho': float(res.statistic),
                                   'p': float(res.pvalue), 'note': ''}
            per[mode] = metrics
        out[scene] = per
    return out


def build_non_occurrence(records, obs_horizon_s):
    mission = [r for r in records if r.get('mission_attempt')]
    counts = {
        'n_mission': len(mission),
        'first_fco_missing': sum(1 for r in mission if not r.get('first_fco_occurred')),
        'capture_missing': sum(1 for r in mission if not r.get('capture_occurred')),
        'shot_missing': sum(1 for r in mission if not r.get('n_shots')),
    }
    per = {}
    for scene in sorted({r.get('scene') for r in records if r.get('scene')}):
        for mode in ('gui', 'headless'):
            sub = [r for r in mission
                   if r.get('scene') == scene and r.get('mode') == mode]
            if not sub:
                continue
            per.setdefault(scene, {})[mode] = {
                'n_mission': len(sub),
                'first_fco_missing': sum(1 for r in sub if not r.get('first_fco_occurred')),
                'capture_missing': sum(1 for r in sub if not r.get('capture_occurred')),
                'shot_missing': sum(1 for r in sub if not r.get('n_shots')),
            }
    first_sentinel = [r.get('first_fco_rel_s') if r.get('first_fco_rel_s') is not None
                      else r.get('window_duration_s') for r in mission]
    capture_sentinel = [r.get('capture_t_s') if r.get('capture_t_s') is not None
                        else obs_horizon_s for r in mission]
    return {
        'scope': 'mission attempts（infra 不参与）',
        'counts': counts,
        'per_scene_mode': per,
        'itt_sensitivity': {
            'label': 'ITT 敏感性（仅敏感性，不作主判定）',
            'first_fco_sentinel_rule': '未发生 -> active 窗口时长（上界）',
            'capture_t_sentinel_rule': '未发生 -> obs horizon（%.1f s）' % obs_horizon_s,
            'first_fco_sentinel': numeric_stats(first_sentinel),
            'capture_t_sentinel': numeric_stats(capture_sentinel),
        },
    }


def build_formal_design_inputs(records, plan):
    formal = plan.get('formal_equivalence') or {}
    co_primary = (plan.get('metrics') or {}).get('co_primary') or [
        'active_fco', 'active_visibility', 'timeout_rate', 'capture_success_rate']
    anchors = formal.get('delta_anchors') or {}
    cap = formal.get('cost_cap') or {}
    max_attempts = cap.get('max_attempts_per_mode_per_scene')
    max_wall_h = cap.get('max_formal_wall_per_scene_h')

    scenes = sorted({r.get('scene') for r in records if r.get('scene')})
    out = {'formula': 'n = ceil((z_0.975 + z_0.80)^2 * (σ_gui^2 + σ_headless^2) '
                      '/ (δ - |Δpilot|)^2)', 'z': [Z_975, Z_80],
           'scenes': {}, 'overall': {}}
    overall_reasons = []
    for scene in scenes:
        metrics = {}
        scene_reasons = []
        for metric in co_primary:
            g = mission_values(records, scene, 'gui', metric)
            h = mission_values(records, scene, 'headless', metric)
            sg = _to_stdev(g)
            sh = _to_stdev(h)
            dp = (statistics.fmean(g) - statistics.fmean(h)) if g and h else None
            delta = anchors.get(metric)
            n, reason = required_n(sg, sh, delta, dp)
            metrics[metric] = {
                'sigma_gui': sg, 'sigma_headless': sh,
                'delta_pilot': dp, 'delta_candidate': delta,
                'n_required': n, 'reason': reason,
            }
            if reason:
                scene_reasons.append('%s：%s' % (metric, reason))
        ns = [m['n_required'] for m in metrics.values() if m['n_required'] is not None]
        max_n = max(ns) if ns else None
        wall_h = None
        if max_n is not None:
            gui_med = numeric_stats([r.get('wall_elapsed_s') for r in records
                                     if r.get('scene') == scene
                                     and r.get('mode') == 'gui'])['median']
            head_med = numeric_stats([r.get('wall_elapsed_s') for r in records
                                      if r.get('scene') == scene
                                      and r.get('mode') == 'headless'])['median']
            base = (gui_med or 0.0) + (head_med or 0.0)
            if base > 0:
                wall_h = max_n * base / 3600.0
        feasible = True
        infeasible_metrics = [m for m, v in metrics.items() if v['n_required'] is None]
        if infeasible_metrics:
            feasible = False
            scene_reasons.append('co-primary 无法计算 n（含不可行 / 缺散布）：%s'
                                 % ', '.join(infeasible_metrics))
        if max_n is None:
            feasible = False
            scene_reasons.append('无法计算所需 n')
        if max_attempts is not None and max_n is not None and max_n > max_attempts:
            feasible = False
            scene_reasons.append('所需 n=%d 超过 max_attempts_per_mode_per_scene=%s'
                                 % (max_n, max_attempts))
        if max_wall_h is not None and wall_h is not None and wall_h > max_wall_h:
            feasible = False
            scene_reasons.append('预计墙钟 %.2f h 超过 max_formal_wall_per_scene_h=%s'
                                 % (wall_h, max_wall_h))
        out['scenes'][scene] = {
            'metrics': metrics, 'max_n_required': max_n,
            'max_attempts_cap': max_attempts, 'wall_estimate_h': wall_h,
            'max_wall_cap_h': max_wall_h, 'feasible': feasible,
            'reasons': scene_reasons,
        }
        if not feasible:
            overall_reasons.extend('%s：%s' % (scene, r) for r in scene_reasons)
    out['overall'] = {'feasible': bool(scenes) and all(
        v['feasible'] for v in out['scenes'].values()), 'reasons': overall_reasons}
    return out


# --------------------------------------------------------------------------- pilot 报告

def build_pilot_report(records, plan, meta, pilot_root, obs_horizon_s):
    data = {
        'kind': 'pilot（描述性；等价未判定）',
        'generated_by': 'scripts/w8_gui_headless_pilot.py',
        'generated_at': now_iso(),
        'campaign': plan.get('campaign') or 'w8-parity',
        'phase': 'pilot',
        'plan': {'path': meta['path'], 'sha256': meta['sha256'],
                 'version': plan.get('version'),
                 'status': plan.get('status')},
        'conclusion': {
            'pilot_only': True,
            'equivalence_not_determined': True,
            'headless_scale_not_authorized': True,
            'text': 'pilot 完成；等价未判定；headless 规模统计未授权。',
        },
        'attempts': records,
        'summaries': build_summaries(records),
        'mode_differences': build_mode_differences(records),
        'cost': build_cost(records),
        'drift': build_drift(records),
        'non_occurrence': build_non_occurrence(records, obs_horizon_s),
        'obs_horizon_s': obs_horizon_s,
        'formal_design_inputs': build_formal_design_inputs(records, plan),
        'graphics_environment': read_environment(pilot_root),
        'missing': _missing_summary(records),
    }
    return data


def read_environment(pilot_root):
    path = os.path.join(pilot_root, 'config', 'environment.json')
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return None


def _missing_summary(records):
    rows = []
    for r in records:
        if r.get('missing_fields') or r.get('notes'):
            rows.append({'run_id': r.get('run_id'),
                         'missing_fields': r.get('missing_fields') or [],
                         'notes': r.get('notes') or []})
    return rows


def render_pilot_md(data):
    md = ['# W8 GUI/headless 模式等价 pilot · %s' % data['campaign'], '',
          '> **pilot 报告：只作描述，不作等价判定。** 结论字段固定为 '
          '`pilot_only` / `equivalence_not_determined` / `headless_scale_not_authorized`；'
          '不参与 P1 / P2 判定，不授权 headless 规模统计。', '',
          '- plan: `%s`' % data['plan']['path'],
          '- plan sha256: `%s`' % data['plan']['sha256'],
          '- plan version / status: `%s` / `%s`' % (data['plan']['version'],
                                                    data['plan']['status']),
          '- generated_at: `%s`' % data['generated_at'], '']
    md += ['## 结论', '', '**%s**' % data['conclusion']['text'], '']

    env = data.get('graphics_environment')
    md += ['## 图形环境（pilot 期间不变化方可外推）', '']
    if env:
        graphics = env.get('graphics') or {}
        md += md_table(['项', '值'], [['captured_at', env.get('captured_at') or '-']]
                       + [[k, v if v is not None else '-'] for k, v in graphics.items()])
    else:
        md += ['- `config/environment.json` 缺失（未执行 run 或已删除）。']
    md += ['']

    md += ['## 逐 attempt（含 infra / 超时 / 缺失）', '',
           '| # | scene | mode | arm/seed | terminal | reason | outcome | mission | timeout | '
           'active FCO | active vis | env_occ\\|vis | first FCO(s) | capture t(s) | n shots | '
           'min clearance(m) | intr seg | intr ratio | RTF | wall(s) |',
           '|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|']
    for r in sorted(data['attempts'], key=lambda x: (x.get('scene') or '',
                                                     x.get('order') or 0)):
        md.append('| %s | %s | %s | %s/s%s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | '
                  '%s | %s | %s | %s | %s | %s |' % (
                      r.get('order'), r.get('scene'), r.get('mode'),
                      r.get('arm'), r.get('seed'), r.get('terminal_state') or '-',
                      r.get('reason_code') or '-', r.get('outcome_class') or '-',
                      'yes' if r.get('mission_attempt') else 'no',
                      'yes' if r.get('is_timeout') else 'no',
                      fmt(r.get('active_fco')), fmt(r.get('active_visibility')),
                      fmt(r.get('env_occ_given_visible')),
                      fmt(r.get('first_fco_rel_s'), '%.2f'),
                      fmt(r.get('capture_t_s'), '%.2f'),
                      fmt(r.get('n_shots'), '%d'), fmt(r.get('min_clearance_m'), '%.3f'),
                      fmt(r.get('intervention_segments'), '%d'),
                      fmt(r.get('intervention_ticks_ratio')),
                      fmt(r.get('rtf')), fmt(r.get('wall_elapsed_s'), '%.1f')))
    md += ['', '## 渲染后端（GUI attempts）', '']
    render_rows = [[r.get('run_id'), r.get('render_backend') or '-',
                    r.get('renderer') or '-']
                   for r in data['attempts'] if r.get('mode') == 'gui']
    if render_rows:
        md += md_table(['run_id', 'render_backend', 'renderer'], render_rows)
    else:
        md += ['- 本次报告无 GUI attempt。']
    md += ['']

    md += ['## 按场景 × 模式汇总', '',
           '| scene | mode | n | mission | infra | timeout | mission success | timeout rate | '
           'capture rate | first FCO rate |',
           '|---|---|---|---|---|---|---|---|---|---|']
    for scene, modes in data['summaries'].items():
        for mode, s in modes.items():
            md.append('| %s | %s | %d | %d | %d | %d | %s | %s | %s | %s |' % (
                scene, mode, s['n_attempts'], s['n_mission'], s['n_infra'],
                s['n_timeout'], fmt(s['mission_success_rate']),
                fmt(s['timeout_rate']), fmt(s['capture_success_rate']),
                fmt(s['first_fco_occurrence_rate'])))
    md += ['', '分母：`timeout_rate` / `capture_success_rate` / `first_fco_occurrence_rate` '
           '均为 **mission attempts**（成功 + MISSION_FAILED）；infra 单列、不进分母。', '']

    md += ['## 连续指标（mission attempts；n / mean / median / SD / min–max / IQR）', '',
           '| scene | mode | metric | n | mean | median | SD | min | max | IQR |',
           '|---|---|---|---|---|---|---|---|---|---|']
    for scene, modes in data['summaries'].items():
        for mode, s in modes.items():
            for metric in CONTINUOUS_METRICS:
                st = s['metrics'][metric]
                if st['n'] == 0:
                    continue
                md.append('| %s | %s | %s | %d | %s | %s | %s | %s | %s | %s |' % (
                    scene, mode, metric, st['n'], fmt(st['mean']),
                    fmt(st['median']), fmt(st['stdev']), fmt(st['min']),
                    fmt(st['max']), fmt(st['iqr'])))
    md += ['']

    md += ['## 模式间描述性差（Δ = GUI − headless；**描述性，不作等价判定**）', '',
           '| scene | metric | n gui | n headless | mean gui | mean headless | Δ | 95% CI | median Δ |',
           '|---|---|---|---|---|---|---|---|---|']
    for scene, metrics in data['mode_differences'].items():
        for metric, d in metrics.items():
            if d['n_gui'] == 0 and d['n_headless'] == 0:
                continue
            ci = ('[%s, %s]' % (fmt(d['ci_low']), fmt(d['ci_high']))
                  if d['ci_low'] is not None else '-')
            md.append('| %s | %s | %d | %d | %s | %s | %s | %s | %s |' % (
                scene, metric, d['n_gui'], d['n_headless'],
                fmt(d['mean_gui']), fmt(d['mean_headless']), fmt(d['delta']),
                ci, fmt(d['median_difference'])))
    md += ['', '> Welch 标准误 + Welch–Satterthwaite df；任一侧 n<2 时 CI 记 `null`。'
           '本表**不**构成等价证据，等价须正式 plan v2 的 ±δ 判定。', '']

    md += ['## 成本', '',
           '| scene | mode | n | median wall(s) | IQR wall | median RTF | IQR RTF |',
           '|---|---|---|---|---|---|---|']
    for scene, per in data['cost']['per_scene_mode'].items():
        for mode in ('gui', 'headless'):
            st = per[mode]
            md.append('| %s | %s | %d | %s | %s | %s | %s |' % (
                scene, mode, st['n'], fmt(st['wall_elapsed_s']['median'], '%.1f'),
                fmt(st['wall_elapsed_s']['iqr'], '%.1f'),
                fmt(st['rtf']['median']), fmt(st['rtf']['iqr'])))
        md.append('- %s GUI / headless 墙钟中位数倍数：%s' % (
            scene, fmt(per.get('gui_over_headless_wall_ratio'), '%.2f')))
    total = data['cost']['total']
    md += ['', '- attempt 墙钟合计：%s s；pilot 墙钟跨度：%s s；attempts=%d' % (
        fmt(total['sum_attempt_wall_s'], '%.1f'),
        fmt(total['pilot_span_wall_s'], '%.1f'), total['n_attempts']), '']

    md += ['## 时间顺序漂移（Spearman：attempt order vs 指标）', '',
           '| scene | mode | metric | n | rho | p | 备注 |',
           '|---|---|---|---|---|---|---|']
    for scene, modes in data['drift'].items():
        for mode, metrics in modes.items():
            for metric, st in metrics.items():
                md.append('| %s | %s | %s | %d | %s | %s | %s |' % (
                    scene, mode, metric, st['n'], fmt(st['rho'], '%.3f'),
                    fmt(st['p'], '%.3f'), st['note'] or '-'))
    md += ['']

    no = data['non_occurrence']
    md += ['## 非发生计数（mission attempts）', '']
    md += md_table(['项', '值'], [
        ['mission attempts', no['counts']['n_mission']],
        ['first FCO 未发生', no['counts']['first_fco_missing']],
        ['capture 未发生', no['counts']['capture_missing']],
        ['shot 未发生', no['counts']['shot_missing']],
    ])
    md += ['', '### ITT 敏感性（**仅敏感性**，不作主判定）', '',
           '- first FCO：未发生赋 active 窗口时长（上界）；mean=%s，n=%d' % (
               fmt(no['itt_sensitivity']['first_fco_sentinel']['mean']),
               no['itt_sensitivity']['first_fco_sentinel']['n']),
           '- capture：未发生赋 obs horizon（%.1f s）；mean=%s，n=%d' % (
               data['obs_horizon_s'], fmt(no['itt_sensitivity']['capture_t_sentinel']['mean']),
               no['itt_sensitivity']['capture_t_sentinel']['n']),
           '']

    design = data['formal_design_inputs']
    md += ['## 正式等价设计输入（按 pilot 散布规划；δ 为候选锚点）', '',
           '`%s`；z=%.6f / %.6f。' % (design['formula'], Z_975, Z_80), '']
    for scene, s in design['scenes'].items():
        md += ['### %s' % scene, '']
        md += md_table(['metric', 'σ gui', 'σ headless', 'Δ pilot', 'δ 候选', 'n 需求', '状态'],
                       [[m, fmt(v['sigma_gui']), fmt(v['sigma_headless']),
                         fmt(v['delta_pilot']), fmt(v['delta_candidate']),
                         (v['n_required'] if v['n_required'] is not None else '-'),
                         v['reason'] or 'ok'] for m, v in s['metrics'].items()])
        md += ['', '- max n：%s；成本上限（attempts/mode/scene）：%s；'
               '预计墙钟：%s h（上限 %s h）；**feasible=%s**' % (
                   s['max_n_required'], s['max_attempts_cap'],
                   fmt(s['wall_estimate_h'], '%.2f'), s['max_wall_cap_h'],
                   s['feasible']), '']
        if s['reasons']:
            md += ['- 原因：%s' % '；'.join(s['reasons'])]
            md += ['']
    md += ['- 设计输入总体 feasible：**%s**' % design['overall']['feasible']]
    if design['overall']['reasons']:
        md += ['- %s' % r for r in design['overall']['reasons']]
    md += ['', '> pilot 的 Δ 与 SD 只用于**样本量规划**；不得据此宣称等价或授权 headless 规模统计。', '']

    md += ['## 缺失 / 备注', '']
    if data['missing']:
        for row in data['missing']:
            md.append('- **%s**：缺失字段 %s；备注：%s' % (
                row['run_id'], ', '.join(row['missing_fields']) or '无',
                '；'.join(row['notes']) or '无'))
    else:
        md.append('- 无缺失字段 / 日志。')
    md += ['', '> 证据边界：pilot 是描述性；等价未判定。']
    return '\n'.join(md) + '\n'


# --------------------------------------------------------------------------- 正式等价报告

def build_formal_report(records, plan, meta, obs_horizon_s, n_per_mode):
    formal = plan.get('formal_equivalence') or {}
    deltas = formal.get('delta') or {}
    co_primary = (plan.get('metrics') or {}).get('co_primary') or list(deltas)
    secondary = (plan.get('metrics') or {}).get('secondary') or []
    secondary_rules = formal.get('secondary_rules') or {}

    co = {}
    for metric in co_primary:
        g = mission_values(records, 'p1', 'gui', metric) + \
            mission_values(records, 'p2', 'gui', metric)
        h = mission_values(records, 'p1', 'headless', metric) + \
            mission_values(records, 'p2', 'headless', metric)
        co[metric] = formal_equivalence_decision(g, h, deltas.get(metric))

    sec = {}
    for metric in secondary:
        g = mission_values(records, 'p1', 'gui', metric) + \
            mission_values(records, 'p2', 'gui', metric)
        h = mission_values(records, 'p1', 'headless', metric) + \
            mission_values(records, 'p2', 'headless', metric)
        ci = welch_ci(g, h)
        rule = secondary_rules.get(metric)
        entry = {'rule': rule, 'delta': ci['delta'],
                 'ci_low': ci['ci_low'], 'ci_high': ci['ci_high'],
                 'n_gui': ci['n_gui'], 'n_headless': ci['n_headless'],
                 'status': 'descriptive', 'note': ci['note']}
        bound = rule.get('delta') if isinstance(rule, dict) else None
        if bound is not None and ci['ci_low'] is not None:
            non_inferior = ci['ci_low'] >= -bound
            entry['status'] = 'non_inferior' if non_inferior else 'material_difference'
            entry['non_inferiority_bound'] = -bound
        sec[metric] = entry

    mission = [r for r in records if r.get('mission_attempt')]
    n_by_mode = {'gui': sum(1 for r in mission if r.get('mode') == 'gui'),
                 'headless': sum(1 for r in mission if r.get('mode') == 'headless')}
    infra = {
        'n_infra': sum(1 for r in records if r.get('is_infra')),
        'n_attempts': len(records),
        'rate': safe_div(sum(1 for r in records if r.get('is_infra')), len(records)),
    }
    hard = check_hard_invariants(records)

    infra_max = formal.get('infra_rate_max')
    if infra_max is None:
        infra_max = formal.get('max_infra_rate')
    if infra_max is None:
        gate_cfg = (plan.get('gates') or {}).get('equivalence_pass') or {}
        if isinstance(gate_cfg, dict):
            infra_max = gate_cfg.get('infra_rate_max')
    infra_ok = None if infra_max is None else bool(
        (infra['rate'] is not None) and infra['rate'] <= infra_max)

    n_ok = n_per_mode is not None and n_by_mode['gui'] >= n_per_mode \
        and n_by_mode['headless'] >= n_per_mode
    status, reasons = decide_formal_gate(co, sec, infra_ok, hard['pass'], n_ok,
                                         n_by_mode, n_per_mode)
    fallback = ((plan.get('gates') or {}).get('equivalence_fail_action')
                or formal.get('equivalence_fail_action')
                or '未通过：不授权 headless 规模统计；定位模式差异或改用 GUI 并记录成本。')
    data = {
        'kind': 'formal_equivalence',
        'generated_by': 'scripts/w8_gui_headless_pilot.py',
        'generated_at': now_iso(),
        'campaign': plan.get('campaign') or 'w8-parity',
        'phase': 'formal',
        'plan': {'path': meta['path'], 'sha256': meta['sha256'],
                 'version': plan.get('version'),
                 'status': plan.get('status')},
        'rule': formal.get('rule'),
        'delta': deltas,
        'n_per_mode': n_per_mode,
        'n_mission_by_mode': n_by_mode,
        'n_ok': n_ok,
        'co_primary': co,
        'all_co_primary_equivalent': all(v['status'] == 'equivalent' for v in co.values()),
        'secondary': sec,
        'infra': dict(infra, infra_rate_max=infra_max, passed=infra_ok),
        'hard_invariants': hard,
        'pooling_note': 'co-primary 的 GUI / headless 值跨 p1 + p2 合并（两样本 Welch）；'
                        '逐场景汇总见 summaries。',
        'gate': {'status': status, 'reasons': reasons, 'fallback': fallback,
                 'headless_scale_authorized': status == 'passed'},
        'summaries': build_summaries(records),
        'attempts': records,
        'non_occurrence': build_non_occurrence(records, obs_horizon_s),
        'missing': _missing_summary(records),
    }
    return data


def check_hard_invariants(records):
    """每发唯一终局 / 事件身份 / lifecycle 计数；缺失证据记 not_evaluable。"""
    per = {}
    defects = []
    missing = []
    for r in records:
        lc = r.get('lifecycle') or {}
        event_rejects = r.get('event_identity_rejects')
        problems = []
        if lc.get('n_unresolved'):
            problems.append('lifecycle unresolved=%s' % lc.get('n_unresolved'))
        if lc.get('n_duplicated'):
            problems.append('lifecycle duplicated=%s' % lc.get('n_duplicated'))
        if lc.get('n_over_bound'):
            problems.append('lifecycle over_bound=%s' % lc.get('n_over_bound'))
        if lc.get('n_absurd_miss_dist'):
            problems.append('lifecycle absurd_miss_dist=%s' % lc.get('n_absurd_miss_dist'))
        if event_rejects:
            problems.append('event identity rejects=%s' % event_rejects)
        per[r.get('run_id')] = {'problems': problems,
                                'evidence_missing': event_rejects is None
                                or not r.get('lifecycle')}
        if problems:
            defects.append(r.get('run_id'))
        elif per[r.get('run_id')]['evidence_missing']:
            missing.append(r.get('run_id'))
    if defects:
        status = False
    elif missing:
        status = None
    else:
        status = True
    return {'pass': status, 'defects': defects, 'missing_evidence': missing,
            'per_attempt': per}


def decide_formal_gate(co, sec, infra_ok, hard_ok, n_ok, n_by_mode, n_per_mode):
    reasons = []
    if not n_ok:
        reasons.append('mission attempts 未达 plan n_per_mode=%s（gui=%d, headless=%d）'
                       % (n_per_mode, n_by_mode['gui'], n_by_mode['headless']))
        return 'not_evaluable', reasons
    statuses = {m: v['status'] for m, v in co.items()}
    if not co:
        return 'not_evaluable', ['无 co-primary 指标']
    if any(s == 'not_evaluable' for s in statuses.values()):
        reasons.extend('%s：not_evaluable（%s）' % (m, v.get('note'))
                       for m, v in co.items() if v['status'] == 'not_evaluable')
        return 'not_evaluable', reasons
    if any(s in ('not_equivalent', 'infeasible') for s in statuses.values()):
        reasons.extend('%s：%s' % (m, v.get('note') or v['status'])
                       for m, v in co.items() if v['status'] != 'equivalent')
        return 'failed', reasons
    sec_material = [m for m, v in sec.items() if v['status'] == 'material_difference']
    if sec_material:
        reasons.extend('%s：secondary material difference' % m for m in sec_material)
        return 'failed', reasons
    if infra_ok is None:
        reasons.append('infra 率阈值缺失，无法评估')
        return 'not_evaluable', reasons
    if infra_ok is False:
        reasons.append('infra 率超过计划阈值')
        return 'failed', reasons
    if hard_ok is None:
        reasons.append('硬不变量证据缺失')
        return 'not_evaluable', reasons
    if hard_ok is False:
        reasons.append('硬不变量存在缺陷')
        return 'failed', reasons
    return 'passed', ['全部 co-primary 等价；secondary 无未解释 material difference；'
                      'infra / 硬不变量均通过']


def render_formal_md(data):
    gate = data['gate']
    md = ['# W8 正式 GUI/headless 等价判定 · %s' % data['campaign'], '',
          '> 规则：等价 iff Δ=GUI−headless 的 95% 双侧 CI 完全落入 `[-δ, +δ]`，'
          '且两个单侧 p < 0.05；**不以“不显著”代替“等价”**。', '',
          '- plan: `%s`' % data['plan']['path'],
          '- plan sha256: `%s`' % data['plan']['sha256'],
          '- plan version / status: `%s` / `%s`' % (data['plan']['version'],
                                                    data['plan']['status']),
          '- generated_at: `%s`' % data['generated_at'], '',
          '## 执行闸门', '',
          '- status: **%s**' % gate['status'],
          '- headless 规模统计授权：**%s**' % gate['headless_scale_authorized'],
          '- 原因：%s' % ('；'.join(gate['reasons']) or '-'),
          '- 回退：%s' % (gate['fallback'] or '-'), '',
          '- n_per_mode：%s；mission attempts：gui=%d、headless=%d' % (
              data['n_per_mode'], data['n_mission_by_mode']['gui'],
              data['n_mission_by_mode']['headless']), '']

    md += ['## co-primary（全部须通过，交集-并集）', '',
           '| metric | δ | n gui | n headless | Δ | 95% CI | p(H0: Δ<=-δ) | p(H0: Δ>=+δ) | 判定 |',
           '|---|---|---|---|---|---|---|---|---|']
    for metric, d in data['co_primary'].items():
        ci = ('[%s, %s]' % (fmt(d['ci_low']), fmt(d['ci_high']))
              if d['ci_low'] is not None else '-')
        md.append('| %s | %s | %d | %d | %s | %s | %s | %s | **%s** |' % (
            metric, fmt(d['delta_bound']), d['n_gui'], d['n_headless'],
            fmt(d['delta']), ci, fmt(d['p_lower'], '%.4f'),
            fmt(d['p_upper'], '%.4f'), d['status']))
    md += ['', '- 全部 co-primary 等价：**%s**' % data['all_co_primary_equivalent'], '']

    md += ['## secondary（报告 / 预设非劣规则）', '',
           '| metric | n gui | n headless | Δ | 95% CI | rule | 判定 |',
           '|---|---|---|---|---|---|---|']
    for metric, d in data['secondary'].items():
        ci = ('[%s, %s]' % (fmt(d['ci_low']), fmt(d['ci_high']))
              if d['ci_low'] is not None else '-')
        md.append('| %s | %d | %d | %s | %s | %s | %s |' % (
            metric, d['n_gui'], d['n_headless'], fmt(d['delta']), ci,
            str(d['rule']) if d['rule'] is not None else 'descriptive', d['status']))
    md += ['']

    infra = data['infra']
    hard_pass = data['hard_invariants']['pass']
    hard_text = ('pass' if hard_pass is True
                 else 'fail' if hard_pass is False else 'not_evaluable')
    md += ['## infra 与硬不变量', '',
           '- infra：n=%d / attempts=%d（rate=%s；阈值=%s；判定=%s）' % (
               infra['n_infra'], infra['n_attempts'], fmt(infra['rate']),
               infra['infra_rate_max'], infra['passed']),
           '- 硬不变量：**%s**；缺陷 %s；缺证据 %s' % (
               hard_text, data['hard_invariants']['defects'] or '无',
               data['hard_invariants']['missing_evidence'] or '无'), '']

    md += ['## 逐 attempt', '',
           '| run_id | scene | mode | terminal | outcome | active FCO | active vis | '
           'first FCO(s) | capture t(s) | min clearance(m) | RTF | wall(s) |',
           '|---|---|---|---|---|---|---|---|---|---|---|---|']
    for r in sorted(data['attempts'], key=lambda x: (x.get('scene') or '',
                                                     x.get('order') or 0)):
        md.append('| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |' % (
            r.get('run_id'), r.get('scene'), r.get('mode'),
            r.get('terminal_state') or '-', r.get('outcome_class') or '-',
            fmt(r.get('active_fco')), fmt(r.get('active_visibility')),
            fmt(r.get('first_fco_rel_s'), '%.2f'), fmt(r.get('capture_t_s'), '%.2f'),
            fmt(r.get('min_clearance_m'), '%.3f'), fmt(r.get('rtf')),
            fmt(r.get('wall_elapsed_s'), '%.1f')))
    md += ['']

    no = data['non_occurrence']
    md += ['## 非发生计数 / ITT 敏感性', '',
           '- mission attempts=%d；first FCO 未发生=%d；capture 未发生=%d；shot 未发生=%d' % (
               no['counts']['n_mission'], no['counts']['first_fco_missing'],
               no['counts']['capture_missing'], no['counts']['shot_missing']),
           '- ITT first FCO sentinel mean=%s；capture sentinel mean=%s（仅敏感性）' % (
               fmt(no['itt_sensitivity']['first_fco_sentinel']['mean']),
               fmt(no['itt_sensitivity']['capture_t_sentinel']['mean'])), '']

    md += ['## 缺失 / 备注', '']
    if data['missing']:
        for row in data['missing']:
            md.append('- **%s**：缺失字段 %s；备注：%s' % (
                row['run_id'], ', '.join(row['missing_fields']) or '无',
                '；'.join(row['notes']) or '无'))
    else:
        md.append('- 无缺失字段 / 日志。')
    md += ['', '> 本报告不写 P1 / P2 adjudication；不参与 P1 / P2 判定。']
    return '\n'.join(md) + '\n'


# --------------------------------------------------------------------------- report 命令

def cmd_report(args):
    repo_root = os.path.abspath(args.repo_root)
    try:
        plan, meta = load_plan_doc(repo_root, args.plan)
    except Exception as exc:  # noqa: BLE001
        print('拒绝生成报告：计划读取失败：%r' % (exc,), file=sys.stderr)
        return 2
    campaign = plan.get('campaign') or 'w8-parity'
    pilot_root = os.path.join(repo_root, 'experiments', campaign, args.pilot_id)
    attempts_path = os.path.join(pilot_root, 'attempts.json')
    attempts = [a for a in load_attempts(attempts_path) if a.get('phase') == args.phase]
    if not attempts:
        print('拒绝生成报告：attempts.json 不存在或无 phase=%s 的 attempt：%s'
              % (args.phase, attempts_path), file=sys.stderr)
        return 2

    fixed = plan.get('fixed_conditions') or {}
    obs_horizon_s = fixed.get('obs_horizon_s')
    if obs_horizon_s is None:
        obs_horizon_s = OBS_HORIZON_FALLBACK_S
    records = [build_attempt_record(repo_root, campaign, a) for a in attempts]

    out_dir = os.path.join(repo_root, 'experiments', campaign, args.out_run_id, 'metrics')
    if args.phase == 'pilot':
        data = build_pilot_report(records, plan, meta, pilot_root, obs_horizon_s)
        json_name, md_name = 'gui_headless_pilot.json', 'gui_headless_pilot.md'
        render = render_pilot_md
    else:
        formal = plan.get('formal_equivalence') or {}
        deltas = formal.get('delta')
        n_per_mode = resolve_n_per_mode(formal)
        try:
            version = int(plan.get('version') or 0)
        except (TypeError, ValueError):
            version = 0
        if version < 2 or not isinstance(deltas, dict) or not deltas or n_per_mode is None:
            print('拒绝生成正式报告：plan v2 缺少 formal_equivalence.delta 或 '
                  'n_per_mode（version=%s）' % version, file=sys.stderr)
            return 2
        data = build_formal_report(records, plan, meta, obs_horizon_s, n_per_mode)
        json_name, md_name = 'gui_headless_equivalence.json', 'gui_headless_equivalence.md'
        render = render_formal_md

    os.makedirs(out_dir, exist_ok=True)
    json_path = os.path.join(out_dir, json_name)
    md_path = os.path.join(out_dir, md_name)
    with open(json_path, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    with open(md_path, 'w') as f:
        f.write(render(data))
    print('-> %s\n-> %s' % (json_path, md_path))
    print('phase=%s attempts=%d' % (args.phase, len(records)))
    if args.phase == 'formal':
        print('gate: %s' % data['gate']['status'])
    return 0


# --------------------------------------------------------------------------- CLI

def build_parser():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='command', required=True)

    run = sub.add_parser('run', help='按预声明序列逐 attempt 运行')
    run.add_argument('--plan', default=DEFAULT_PLAN)
    run.add_argument('--pilot-id', required=True)
    run.add_argument('--scene', choices=['p1', 'p2', 'all'], default='all')
    run.add_argument('--phase', choices=['pilot', 'formal'], default='pilot')
    run.add_argument('--dry-run', action='store_true')
    run.add_argument('--resume', action='store_true',
                     help='仅补跑 attempts.json 中缺失的预声明 attempt（机器中断恢复）')
    run.add_argument('--repo-root', default=ROOT)
    run.set_defaults(func=cmd_run)

    report = sub.add_parser('report', help='生成 pilot / 正式等价报告')
    report.add_argument('--plan', default=DEFAULT_PLAN)
    report.add_argument('--pilot-id', required=True)
    report.add_argument('--phase', choices=['pilot', 'formal'], default='pilot')
    report.add_argument('--out-run-id', default=None)
    report.add_argument('--repo-root', default=ROOT)
    report.set_defaults(func=cmd_report)
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.command == 'report' and args.out_run_id is None:
        args.out_run_id = args.pilot_id
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
