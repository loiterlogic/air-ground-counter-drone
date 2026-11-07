#!/usr/bin/env python3
"""文档计数一致性 —— 让"1 个事实 4 个版本"不可能再发生。

## 为什么存在

2026-11-06 评估实测：`tests/` 下验收核查实际 **58** 个，但四处文档分别写
57 / 57 / 59 / "6 组"（实际 8 组）。这类漂移不会让任何测试变红，
却正是本仓最忌讳的"同一个事实多份副本"形态——只不过发生在文档层。

本核查把**能机械判定的计数**钉成判据：数字来自目录实况，文档必须与之一致。

## 判据（全部纯静态、秒级、不启进程）

| # | 断言 |
|---|---|
| a | 文档里出现的"N 个 `check_*.py` / 核查"必须等于 `tests/` 实际数量 |
| b | 冒烟组数（`run_smoke.py` 的 `GROUPS` 长度）必须与 `tests/README.md` 声称一致 |
| c | `run_all.py` 的发现结果不得含库文件或 runner（防"假 PASS"回潮） |
| d | ADR 索引里声称的编号上限必须等于 `docs/adr/` 实际最大编号 |
| e | `tests/README.md` 三分类表里的 `static` / `evidence` / `needs_sim` 数量必须等于 `checklib.check_categories()` 实况 |

退出码：0 = PASS；1 = FAIL；2 = 用法/环境错误。

用法：
  python3 tests/check_doc_counts.py [--out DIR]
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import checklib  # noqa: E402  （分类口径的唯一实现，见 tests/README.md#categories）

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
TESTS = os.path.join(ROOT, 'tests')


def _read(path):
    try:
        with open(path, encoding='utf-8') as f:
            return f.read()
    except OSError:
        return None


def actual_check_count():
    return len([n for n in os.listdir(TESTS)
                if n.startswith('check_') and n.endswith('.py')])


def actual_smoke_groups():
    src = _read(os.path.join(TESTS, 'run_smoke.py')) or ''
    m = re.search(r'^GROUPS\s*=\s*\[', src, re.M)
    if not m:
        return None
    depth = 0
    for i in range(m.end() - 1, len(src)):
        if src[i] == '[':
            depth += 1
        elif src[i] == ']':
            depth -= 1
            if depth == 0:
                block = src[m.end() - 1:i + 1]
                # 每组是一个以 ('name', ...) 开头的元组
                return len(re.findall(r"^\s*\('([a-z_]+)',", block, re.M))
    return None


def documented_check_counts():
    """扫描活跃文档里所有"N 个 `check_*.py`"式的计数声明。"""
    hits = []
    targets = [
        'README.md', 'tests/README.md', 'tests/run_smoke.py', 'tests/checklib.py',
        'tests/run_all.py', 'tests/run_full_regression.py', 'tests/run_regression_matrix.py',
    ]
    pat = re.compile(r'(\d+)\s*个\s*[`\s]*check')
    for rel in targets:
        text = _read(os.path.join(ROOT, rel)) or ''
        for i, line in enumerate(text.splitlines(), 1):
            for m in pat.finditer(line):
                hits.append((rel, i, int(m.group(1))))
    return hits


def documented_group_count():
    text = _read(os.path.join(ROOT, 'tests', 'README.md')) or ''
    m = re.search(r'离线冒烟（(\d+)\s*组）', text)
    return int(m.group(1)) if m else None


def run_all_discovery():
    src = _read(os.path.join(TESTS, 'run_all.py')) or ''
    m = re.search(r'NOT_CHECKS\s*=\s*frozenset\(\{([^}]*)\}\)', src, re.S)
    names = set(re.findall(r'"([^"]+)"', m.group(1))) if m else set()
    listed = [n for n in os.listdir(TESTS) if n.endswith('.py')]
    return [n for n in listed if n not in names and not n.startswith('run_')], names


def adr_numbering_ceiling():
    adr_dir = os.path.join(ROOT, 'docs', 'adr')
    nums = [int(n[:4]) for n in os.listdir(adr_dir)
            if re.match(r'^\d{4}-', n) and n.endswith('.md')]
    return max(nums) if nums else None


def claimed_adr_ceiling():
    text = _read(os.path.join(ROOT, 'docs', 'adr', 'README.md')) or ''
    m = re.search(r'现行有效编号只有本表\s*0001[–-](\d{4})', text)
    return int(m.group(1)) if m else None


def documented_categories():
    """从 `tests/README.md` 的三分类表里取三类声称数量。

    只认「`static` | **4**」这一种行式（表里第一列是反引号类名、第二列是加粗数字）；
    取不到就返回 None 让判据 e 失败——**表格被改坏也算漂移**，不能静默放过。
    """
    text = _read(os.path.join(TESTS, 'README.md')) or ''
    claimed = {}
    for cat in checklib.CATEGORIES:
        m = re.search(r'`%s`\s*\|\s*\*\*(\d+)\*\*' % re.escape(cat), text)
        if not m:
            return None
        claimed[cat] = int(m.group(1))
    return claimed


def main(argv=None):
    ap = argparse.ArgumentParser(description='文档计数一致性核查')
    ap.add_argument('--out', default=None, help='证据 JSON 落盘目录（可选）')
    args = ap.parse_args(argv)

    results = {}
    checks_n = actual_check_count()
    results['a1_actual_check_count'] = {'pass': True, 'value': checks_n}

    bad = []
    for rel, line, n in documented_check_counts():
        if n != checks_n:
            bad.append('%s:%d 写 %d，实际 %d' % (rel, line, n, checks_n))
    results['a2_documented_check_counts_match'] = {'pass': not bad, 'problems': bad}

    groups_n = actual_smoke_groups()
    claimed_g = documented_group_count()
    results['b_smoke_group_count_matches'] = {
        'pass': groups_n is not None and claimed_g is not None and groups_n == claimed_g,
        'actual': groups_n, 'documented': claimed_g,
    }

    discovered, not_checks = run_all_discovery()
    leaked = [n for n in discovered if n == 'checklib.py' or n.startswith('run_')]
    results['c_run_all_excludes_lib_and_runners'] = {
        'pass': not leaked and 'checklib.py' in not_checks,
        'leaked': leaked,
    }

    actual_adr = adr_numbering_ceiling()
    claimed_adr = claimed_adr_ceiling()
    results['d_adr_ceiling_matches'] = {
        'pass': actual_adr == claimed_adr,
        'actual': actual_adr, 'documented': claimed_adr,
    }

    # e：三分类口径。数量来自 `checklib.check_categories()`（唯一实现），
    # 文档数字来自 tests/README.md 的表；两者不一致就红——否则"表里写 22、实际 21"
    # 这种漂移会一直绿着，正是本文件要拦的形态。
    actual_cats = {k: len(v) for k, v in checklib.check_categories(TESTS).items()}
    claimed_cats = documented_categories()
    problems_e = []
    if claimed_cats is None:
        problems_e.append('tests/README.md 的三分类表缺失或格式不符（须「`cat` | **N**」）')
    else:
        for cat in checklib.CATEGORIES:
            if claimed_cats[cat] != actual_cats[cat]:
                problems_e.append('%s：文档写 %d，实际 %d'
                                  % (cat, claimed_cats[cat], actual_cats[cat]))
    total_cat = sum(actual_cats.values())
    if total_cat != checks_n:
        problems_e.append('三类合计 %d ≠ check_*.py 实际 %d（分类口径漏了文件）'
                          % (total_cat, checks_n))
    results['e_check_categories_match'] = {
        'pass': not problems_e,
        'actual': actual_cats, 'documented': claimed_cats, 'problems': problems_e,
    }

    all_pass = all(v.get('pass') for v in results.values())
    for name, v in results.items():
        print('%-42s %s' % (name, 'PASS' if v.get('pass') else 'FAIL'))
        for key in ('problems', 'leaked'):
            if v.get(key):
                for item in v[key]:
                    print('      %s' % item)
        for key in ('actual', 'documented', 'value'):
            if key in v and v.get(key) is not None:
                print('      %s = %s' % (key, v[key]))

    if args.out:
        import json
        os.makedirs(args.out, exist_ok=True)
        with open(os.path.join(args.out, 'doc_counts.json'), 'w', encoding='utf-8') as f:
            json.dump({'pass': all_pass, 'checks': results}, f, indent=2, ensure_ascii=False)
        print('%s -> %s' % ('PASS' if all_pass else 'FAIL', args.out))
    return 0 if all_pass else 1


if __name__ == '__main__':
    sys.exit(main())
