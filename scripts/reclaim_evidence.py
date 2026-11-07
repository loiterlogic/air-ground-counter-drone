#!/usr/bin/env python3
"""reclaim_evidence —— `experiments/` 与 `log/` 的**保留策略执行器**（默认 dry-run）。

## 为什么有这个文件

`experiments/` 与 `log/` 是**产物**（`.gitignore` 排除），长期只增不减：实测
experiments 4.2 G / 2 100+ run 目录、log 7.1 G / 430+ 目录。`scripts/evidence_archive.py`
里的 `RETENTION` 只是**一段文本**、零调用方——它不是策略，只是注释。

本脚本把策略变成**可执行判据**：哪些可回收、哪些**不可删**、怎么复核。

## 判定规则（ADR-0006 的产物保留策略，逐条可判定）

一个 run 目录**可回收**，当且仅当它命中以下任一规则，**且**不命中任何「不可删」条件：

| 规则 | 范围 | 判据 |
|---|---|---|
| `demo_doctor` | `experiments/demo/*-doctor` | 纯环境预检，无任务判定 |
| `demo_failed` | `experiments/demo/<run>` | `result.json` 的 `state` ∈ {`failed`, `timeout`} 或缺失 |
| `demo_superseded` | `experiments/demo/<run>` | 同类型演示里**非最新一份**（保留最近 1 份） |
| `rl_no_report` | `experiments/w7-rl-b/<run>` | 缺 `metrics/report.json`（不构成完整证据链） |
| `colcon_logs` | `log/build_*` `log/test*` | colcon 构建 / 测试日志（非 run 证据） |

**不可删清单**（任何规则都不得越过）：

1. **被文档引用**：`docs/`、`README.md`、`AGENTS.md`、`GLOSSARY.md`、`tests/`、`scripts/`
   里出现过该 run 路径（`experiments/<campaign>/<run_id>`）→ 证据链的一部分，删了即断链。
2. **在不可删 campaign 里**：`experiments/_archive/`（不可变归档）、`w6-task-eval/`（验收证据）。
3. **带完整证据链**：同时有 `metrics/summary.json` **和** `config/scene_manifest.json`
   的 run（可被证据核查读取，是判据来源）。
4. **非本轮授权 campaign**：本脚本只动 `demo/`、`w7-rl-b/`、`log/`；其余一律不碰。

## 用法

```bash
python3 scripts/reclaim_evidence.py                 # dry-run：只列将删除的，不删（默认）
python3 scripts/reclaim_evidence.py --apply         # 真删（不可逆）
python3 scripts/reclaim_evidence.py --json OUT.json # 把清单落盘（复核 / 留痕）
```

退出码：`0` = 完成（dry-run 亦 0）；`1` = 有被保护项被请求删除（**拒删**，说明命中了不可删清单）；
`2` = 用法 / 环境错误。

## 纪律

* **默认 dry-run**：不加 `--apply` 一个文件都不删（`--dry-run` 与缺省等价，可显式写）。
* **先算后删**：先完整算出清单与总大小并打印，`--apply` 才执行；删除按目录粒度、逐条打印。
* **不猜**：读不到的 `result.json` / 缺字段 → 归入"未完成"，与显式 `failed` 同列（如实标注）。
* **不碰归档**：`experiments/_archive/` 是 ADR-0006 的不可变归档，永不回收。
"""

import argparse
import glob
import re
import json
import os
import shutil
import sys

ROOT = '/home/chen/AGC'
EXPERIMENTS = os.path.join(ROOT, 'experiments')
LOG = os.path.join(ROOT, 'log')

# 本轮用户裁定授权回收的范围（超出即不碰）。
AUTHORIZED_CAMPAIGNS = ('demo', 'w7-rl-b')

# 永不回收的 campaign（不可删清单第 2 条）。
PROTECTED_CAMPAIGNS = ('_archive', 'w6-task-eval')

# 文档 / 代码里出现 run 路径即视为「被引用」→ 不可删（不可删清单第 1 条）。
REFERENCE_ROOTS = ('docs', 'tests', 'scripts', 'src', 'README.md', 'AGENTS.md', 'GLOSSARY.md')

def _size(path):
    """目录 / 文件字节数（读不到按 0，不因单个坏链接中断整轮）。"""
    total = 0
    if os.path.isfile(path) and not os.path.islink(path):
        try:
            return os.path.getsize(path)
        except OSError:
            return 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            p = os.path.join(root, name)
            if os.path.islink(p):
                continue
            try:
                total += os.path.getsize(p)
            except OSError:
                pass
    return total


def _read_json(path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _known_campaigns():
    """`experiments/` 下实际存在的 campaign 目录名（用于识别省略前缀的引用）。"""
    if not os.path.isdir(EXPERIMENTS):
        return ()
    return tuple(sorted(n for n in os.listdir(EXPERIMENTS)
                        if os.path.isdir(os.path.join(EXPERIMENTS, n))
                        and not n.startswith('.')))


def referenced_paths():
    """扫描参考根，返回**被引用过的** `experiments/<campaign>/<run>` 相对路径集合。

    只做字符串匹配（不做链接解析）：文档里写出来的路径就是"引用"，宁可多保护。
    """
    refs = set()
    campaigns = _known_campaigns()
    for rel in REFERENCE_ROOTS:
        base = os.path.join(ROOT, rel)
        if os.path.isfile(base):
            paths = [base]
        elif os.path.isdir(base):
            paths = []
            for root, _dirs, files in os.walk(base):
                paths.extend(os.path.join(root, n) for n in files
                             if n.endswith(('.md', '.py', '.sh', '.yaml', '.yml', '.txt', '.json')))
        else:
            continue
        for p in paths:
            try:
                with open(p, encoding='utf-8', errors='replace') as f:
                    text = f.read()
            except OSError:
                continue
            for campaign, run in _iter_experiment_refs(text, campaigns):
                refs.add('experiments/%s/%s' % (campaign, run))
    return refs


def _iter_experiment_refs(text, campaigns=()):
    """从文本里抽 `<campaign>/<run>`（两段名字各限 `[A-Za-z0-9._-]`）。

    用**字符集**而不是"遇到分隔符才停"：文档里的路径常紧跟全角标点 / 反引号 / 中文，
    按分隔符切会把 `（s08` 之类的尾巴带进来，导致真引用反而匹配不上（实测踩到）。

    也**接受省略 `experiments/` 前缀**的写法（实测踩到）：ADR / 归档里常写
    `run_id w7-rl-b/20261020-w7-rl-b-150408-8486`，若只认带前缀的形式，这条真引用会被
    漏掉、证据被误删。故按**已知 campaign 名**匹配任意位置出现的 `<campaign>/<run>`。
    """
    out = re.findall(r'experiments/([A-Za-z0-9._-]+)/([A-Za-z0-9._-]+)', text)
    for camp in campaigns:
        out.extend((camp, run) for run in
                   re.findall(r'(?<![A-Za-z0-9._-])%s/([A-Za-z0-9._-]+)'
                              % re.escape(camp), text))
    return out


def _has_full_chain(run_dir):
    """完整证据链 = summary.json + scene_manifest.json 都在（可被证据核查读取）。"""
    return (os.path.isfile(os.path.join(run_dir, 'metrics', 'summary.json')) and
            os.path.isfile(os.path.join(run_dir, 'config', 'scene_manifest.json')))


def _demo_failed(run_dir):
    """demo run 是否**失败 / 未完成**——按 `scripts/demo/start.py` 写出的真实 schema 判。

    真实键（实测，此前写错导致误删成功 run）：
    * `verdict` —— `expected_terminal`（达标）或 `not_met`；
    * `terminal_reached` —— 是否观测到终态；
    * `exit_code` —— 进程退出码；
    * `exit_reason` —— 如 `demo_error` / `interrupted(...)` / `duration_limit`。

    判「失败」= 任一条成立：`verdict != expected_terminal`（含 `not_met` / 缺失）、
    `terminal_reached is False`、`exit_code != 0`。读不到 `result.json` → 返回 `'missing'`
    （**不算失败**，见调用处的保守处理：缺文件时进「保护」而不是「回收」）。
    """
    res = _read_json(os.path.join(run_dir, 'result.json'))
    if not isinstance(res, dict):
        return 'missing'
    verdict = res.get('verdict')
    if verdict is None:
        return 'no_verdict'
    if verdict != 'expected_terminal':
        return str(verdict)
    if res.get('terminal_reached') is False:
        return 'terminal_not_reached'
    if res.get('exit_code') not in (0, None):
        return 'exit_%s' % res.get('exit_code')
    return None   # 达标


def collect():
    """算出 (可回收项, 被保护项)，每项是 dict（path / bytes / rule / reason）。"""
    refs = referenced_paths()
    reclaim, protected = [], []

    def consider(path, rule, reason, campaign):
        rel = os.path.relpath(path, ROOT).replace(os.sep, '/')
        item = {'path': rel, 'bytes': _size(path), 'rule': rule, 'reason': reason}
        if campaign in PROTECTED_CAMPAIGNS:
            item['why_protected'] = 'campaign 在不可删清单（%s）' % campaign
            protected.append(item)
        elif rel in refs:
            item['why_protected'] = '被文档 / 代码引用（证据链的一部分）'
            protected.append(item)
        elif _has_full_chain(path):
            item['why_protected'] = '带完整证据链（summary + scene_manifest 均在）'
            protected.append(item)
        else:
            reclaim.append(item)

    # ---- demo：doctor 证据 + 失败 run + 非最新一份 ----
    demo_root = os.path.join(EXPERIMENTS, 'demo')
    demo_runs = sorted(
        d for d in glob.glob(os.path.join(demo_root, '*'))
        if os.path.isdir(d) and not os.path.basename(d).startswith('.')
        and not os.path.basename(d).startswith('_'))
    doctors = [d for d in demo_runs if os.path.basename(d).endswith('-doctor')]
    demos = [d for d in demo_runs if not os.path.basename(d).endswith('-doctor')]

    for d in doctors:
        consider(d, 'demo_doctor', '纯环境预检（无任务判定）', 'demo')

    # 非最新一份：按目录名（时间戳前缀）排序，保留最后 1 个。
    if len(demos) > 1:
        for d in demos[:-1]:
            consider(d, 'demo_superseded', '非最新一份演示（保留最近 1 份）', 'demo')

    for d in demos:
        why = _demo_failed(d)
        # 只有**明确失败**才回收；`missing` / `no_verdict`（读不到 result.json）一律不动——
        # 读不到不等于失败，宁可留着（2026-11-06 实测：按旧键名读，成功 run 被误判成 failed）。
        if why in ('missing', 'no_verdict'):
            continue
        consider(d, 'demo_failed', '未完成 / 失败（verdict=%s）' % why, 'demo')

    # ---- w7-rl-b：缺 report.json ----
    rl_root = os.path.join(EXPERIMENTS, 'w7-rl-b')
    for d in sorted(glob.glob(os.path.join(rl_root, '*'))):
        if not os.path.isdir(d):
            continue
        if not os.path.isfile(os.path.join(d, 'metrics', 'report.json')):
            consider(d, 'rl_no_report', '缺 metrics/report.json（不构成完整证据链）', 'w7-rl-b')

    # ---- log/：colcon 构建 / 测试日志 ----
    for d in sorted(glob.glob(os.path.join(LOG, '*'))):
        name = os.path.basename(d)
        if name in ('COLCON_IGNORE', 'latest', 'latest_build', 'latest_list', 'latest_test',
                    'latest_test-result'):
            continue
        if os.path.isdir(d) and (name.startswith('build_') or name.startswith('test')):
            item = {'path': os.path.relpath(d, ROOT).replace(os.sep, '/'),
                    'bytes': _size(d), 'rule': 'colcon_logs',
                    'reason': 'colcon 构建 / 测试日志（非 run 证据）'}
            reclaim.append(item)

    return reclaim, protected


def _human(n):
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if n < 1024.0:
            return '%.1f %s' % (n, unit)
        n /= 1024.0
    return '%.1f PB' % n


def main(argv=None):
    ap = argparse.ArgumentParser(description='experiments/ 与 log/ 保留策略执行器（默认 dry-run）')
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true', help='只列清单，不删除（**默认**）')
    mode.add_argument('--apply', action='store_true', help='执行删除（不可逆）')
    ap.add_argument('--json', default=None, metavar='OUT', help='把清单落盘为 JSON（复核 / 留痕）')
    args = ap.parse_args(argv)

    if not os.path.isdir(EXPERIMENTS):
        print('ERROR：experiments/ 不存在：%s' % EXPERIMENTS, file=sys.stderr)
        return 2

    reclaim, protected = collect()
    total = sum(i['bytes'] for i in reclaim)

    print('=' * 74)
    print('AGC 产物回收 · %s · 授权范围 %s + log/'
          % ('APPLY（不可逆）' if args.apply else 'DRY-RUN（默认，不删）',
             '/'.join(AUTHORIZED_CAMPAIGNS)))
    print('=' * 74)
    print('可回收 %d 项，合计 %s' % (len(reclaim), _human(total)))
    by_rule = {}
    for i in reclaim:
        by_rule.setdefault(i['rule'], []).append(i)
    for rule in sorted(by_rule):
        items = by_rule[rule]
        print('  %-16s %4d 项  %s' % (rule, len(items),
                                      _human(sum(x['bytes'] for x in items)))
              )
    print()
    print('被保护 %d 项（**不会删**）' % len(protected))
    for i in protected[:20]:
        print('  %-58s %s' % (i['path'], i.get('why_protected', '')))
    if len(protected) > 20:
        print('  … 其余 %d 项见 --json 输出' % (len(protected) - 20))
    print()

    if args.json:
        with open(args.json, 'w', encoding='utf-8') as f:
            json.dump({'apply': bool(args.apply), 'reclaim': reclaim,
                       'protected': protected, 'reclaim_bytes': total},
                      f, indent=2, ensure_ascii=False)
        print('清单 -> %s' % args.json)

    if not args.apply:
        print('DRY-RUN：未删除任何文件（加 --apply 才执行）')
        return 0

    # ---- 真删：逐条、按目录粒度 ----
    removed = 0
    failed = []
    for i in reclaim:
        path = os.path.join(ROOT, i['path'])
        # 再确认一次保护（防御：清单与执行之间不得绕过不可删清单）
        if any(i['path'] == p['path'] for p in protected):
            failed.append((i['path'], '命中不可删清单'))
            continue
        try:
            if os.path.isdir(path) and not os.path.islink(path):
                shutil.rmtree(path)
            elif os.path.isfile(path) or os.path.islink(path):
                os.remove(path)
            else:
                failed.append((i['path'], '不存在'))
                continue
            removed += 1
            print('  removed %-58s %s' % (i['path'], _human(i['bytes'])))
        except OSError as exc:
            failed.append((i['path'], str(exc)))

    print('-' * 74)
    print('已删除 %d / %d 项，回收 %s' % (removed, len(reclaim), _human(total)))
    if failed:
        print('失败 %d 项：' % len(failed))
        for p, why in failed[:10]:
            print('  %s → %s' % (p, why))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
