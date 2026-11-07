#!/usr/bin/env python3
"""配置孤儿核查 —— `src/*/config/` 下的每个 YAML 必须被至少一处**非自身**文件引用。

## 为什么存在

2026-11-07 评估实测：`src/agc_task/config/` 有 5 个验收配置
（`timeout` / `safety_trigger` / `reset_failure` / `reset_infeasible` / `spawn_random`）
**全仓零引用**，却仍被 `install(DIRECTORY config ...)` 装进 share、仍被当成"配置目录的一部分"。
它们是一次性验收脚本的伴生文件，脚本结档后配置留了下来——没有任何测试能发现。

死配置的成本不是磁盘，是**误导**：读 `config/` 的人会以为存在对应的活跃场景/判据，
排查时先去改一个没人读的文件。

## 判据（纯静态、秒级、不启进程）

对 `src/<pkg>/config/**/*.yaml` 的每个文件：

| # | 断言 |
|---|---|
| a | 存在**至少一处**引用：在 `src/` `scripts/` `tests/` `docs/` `run_demo.sh` 的文本里出现其**文件名** |
| b | 引用者不得是**它自己**（自引用不算活） |
| c | 例外必须显式登记：`EXEMPT` 表里逐条写理由（如"由 xacro/SDF 间接加载"） |

判据 a 用**文件名**而非完整路径匹配：配置被引用的形态很多
（`os.path.join(share, 'config', 'base.yaml')`、`install(FILES config/x.yaml ...)`、
文档里的 `config/x.yaml`），只匹配完整路径会漏掉绝大多数真实引用。

**已知局限**（如实登记，不假装覆盖）：文件名匹配是**下界**——
同名的不同包文件会互相"作证"。故本核查只在**文件名全局唯一**时才有强判据；
`_duplicate_basenames()` 会把重名情况报出来（重名不判失败，但会列名提醒）。

退出码：0 = PASS；1 = FAIL；2 = 用法/环境错误。

用法：
  python3 tests/check_config_orphans.py
  python3 tests/check_config_orphans.py --verbose
"""

from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

# 扫描"谁在引用"的范围（相对项目根）。
REFERRER_DIRS = ('src', 'scripts', 'tests', 'docs')
REFERRER_ROOT_FILES = ('run_demo.sh', 'README.md', 'AGENTS.md', 'pyproject.toml')
REFERRER_EXTS = ('.py', '.cpp', '.hpp', '.h', '.yaml', '.yml', '.sh', '.md',
                 '.launch.py', '.txt', '.xml', '.xacro', '.sdf', '.cmake')
SKIP_PARTS = {'build', 'install', 'log', 'experiments', 'refs', 'reference',
              'toolchain', '__pycache__', '.git', '.pytest_cache', 'node_modules'}

# 例外：确无文本引用的配置，逐条写理由。**新增条目必须写清"谁在用它"**。
EXEMPT: dict[str, str] = {
    'src/agc_rl/config/mission_fco_equivalence_draft.yaml': (
        'P3 等价设计的**未评审草案**（文件内 `execution_authorized: false`），'
        '按 ADR-0021 该设计仍 `deferred`、须"先实现新记录器再预声明新设计"——'
        '故当前**无消费者是正确状态**，不是遗漏。'
        '保留理由：草案内容尚未评审，删掉等于静默丢弃未决设计；'
        '原文另存于 docs/archive/frozen-prereg-snapshots/（含被清除的过程编号）。'
        '退役条件：P3 立项时要么冻结为新预注册、要么删除并登记退役台账。'
    ),
}


def _iter_config_files():
    """`src/<pkg>/config/**/*.yaml` 的全部配置文件（相对项目根的 posix 路径）。"""
    for pkg in sorted(os.listdir(os.path.join(ROOT, 'src'))):
        cfg_root = os.path.join(ROOT, 'src', pkg, 'config')
        if not os.path.isdir(cfg_root):
            continue
        for dirpath, dirnames, filenames in os.walk(cfg_root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_PARTS]
            for name in sorted(filenames):
                if not name.endswith(('.yaml', '.yml')):
                    continue
                full = os.path.join(dirpath, name)
                yield os.path.relpath(full, ROOT).replace(os.sep, '/'), name


def _iter_referrer_files():
    """可能"引用配置"的全部文本文件（相对项目根的 posix 路径）。"""
    for d in REFERRER_DIRS:
        base = os.path.join(ROOT, d)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [dn for dn in dirnames if dn not in SKIP_PARTS]
            for name in filenames:
                if not name.endswith(REFERRER_EXTS):
                    continue
                full = os.path.join(dirpath, name)
                yield os.path.relpath(full, ROOT).replace(os.sep, '/')
    for name in REFERRER_ROOT_FILES:
        if os.path.isfile(os.path.join(ROOT, name)):
            yield name


def _read(rel):
    try:
        with open(os.path.join(ROOT, rel), encoding='utf-8', errors='replace') as f:
            return f.read()
    except OSError:
        return None


def scan():
    """返回 (orphans, referrers, duplicates)。

    `orphans`: [(配置相对路径, 文件名)] —— 除自身外无人提及；
    `referrers`: {配置相对路径: [引用者相对路径...]}；
    `duplicates`: {文件名: [配置相对路径...]} —— 同名配置（判据的下界局限，列名提醒）。
    """
    referrer_texts = {}
    for rel in _iter_referrer_files():
        text = _read(rel)
        if text is not None:
            referrer_texts[rel] = text

    by_name: dict[str, list[str]] = {}
    orphans, referrers = [], {}
    for cfg_rel, name in _iter_config_files():
        by_name.setdefault(name, []).append(cfg_rel)
        hits = [rel for rel, text in referrer_texts.items()
                if rel != cfg_rel and name in text]
        if hits:
            referrers[cfg_rel] = sorted(hits)
        elif cfg_rel not in EXEMPT:
            orphans.append((cfg_rel, name))

    duplicates = {n: v for n, v in by_name.items() if len(v) > 1}
    return orphans, referrers, duplicates


def main(argv=None):
    ap = argparse.ArgumentParser(description='配置孤儿核查（src/*/config 下的 YAML 必须被引用）')
    ap.add_argument('--verbose', action='store_true', help='逐个列出引用者')
    args = ap.parse_args(argv)

    orphans, referrers, duplicates = scan()

    print('配置孤儿核查')
    print('=' * 68)
    print('配置总数：%d（被引用 %d，孤儿 %d，例外 %d）'
          % (len(referrers) + len(orphans) + len(EXEMPT), len(referrers),
             len(orphans), len(EXEMPT)))

    if args.verbose:
        for cfg_rel in sorted(referrers):
            print('  %s  <- %s' % (cfg_rel, ', '.join(referrers[cfg_rel][:3])))
        for cfg_rel in sorted(EXEMPT):
            print('  %s  <- [EXEMPT] %s' % (cfg_rel, EXEMPT[cfg_rel]))

    if duplicates:
        print('\n同名配置（文件名匹配的下界局限，仅提醒，不判失败）：%d' % len(duplicates))
        for name, paths in sorted(duplicates.items()):
            print('  %s: %s' % (name, ', '.join(paths)))

    if orphans:
        print('\n孤儿配置：%d' % len(orphans))
        for cfg_rel, name in orphans:
            print('  %s' % cfg_rel)
        print('\nFAIL：以下配置全仓零引用。处置二选一：')
        print('  · 删掉（`git rm`），并在 docs/conventions/路线分支治理.md 的退役台账登记；')
        print('  · 确有引用但形态特殊（xacro / SDF 间接加载）→ 加进本文件的 EXEMPT 表并写理由。')
        print('=' * 68)
        return 1

    print('\nPASS：全部配置均有引用（或已登记为例外）')
    print('=' * 68)
    return 0


if __name__ == '__main__':
    sys.exit(main())
