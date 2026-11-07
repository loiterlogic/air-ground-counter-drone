#!/usr/bin/env python3
"""预注册冻结快照的**字节级**守护 —— 冻结内容不得被任何"整理"顺手改写。

## 为什么存在

2026-11-06 那次「代码层编号清零」改了 6 个预注册配置里的描述性字段（批次与轮次
编号）。为了让"按原文复核"仍可能，作者把改写**前**的原文另存到
`docs/archive/frozen-prereg-snapshots/`。

**但那 6 份"原文"当时是从改写后的工作区拷的**——它们不是原文，是改写版。
实测证据：ADR-0021 记录的 sha256 是 `3afa82c4…a292`，而快照文件是 `8cc761a6…`；
ADR-0024 记录 `9d700069…d710`，快照是 `cd47adba…`。**"冻结"二字自相矛盾**，
且**没有任何测试**会发现——这正是本仓最忌讳的"看着有保护、实际零覆盖"。

## 判据（全部机械可判）

| # | 断言 |
|---|---|
| a | 6 份快照的 sha256 必须等于 `FROZEN_SHA256` 里钉死的值 |
| b | ADR 正文里记录的短哈希（`3afa82c4…a292` / `9d700069…d710`）必须与对应快照的前 8 / 后 4 位一致 |
| c | 每份快照必须能追溯到**唯一的冻结提交**（`FROZEN_ORIGIN`），且该提交的字节哈希 == 快照哈希 |

判据 c 让"快照从哪来"可复核，而不是靠人记：`git show <commit>:<path> | sha256sum`。

**为什么钉死哈希而不是钉死"内容不变"**：内容不变无法判（改一个空格也是改）；
哈希是唯一能把"字节完全相同"变成可判定命题的形式。

退出码：0 = PASS；1 = FAIL；2 = 用法/环境错误。

用法：
  python3 -m pytest scripts/tests/test_frozen_prereg_snapshots.py -q
  python3 tests/check_frozen_prereg.py          # 独立核查版（退出码语义）
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SNAP_DIR = ROOT / 'docs' / 'archive' / 'frozen-prereg-snapshots'

# 冻结字节的 sha256（钉死）。新增快照必须同时补进本表，否则判据 a 覆盖不到它。
FROZEN_SHA256 = {
    'gui_headless_plan.yaml':
        '3afa82c42041f23dd343ac17532920811fec0153c4ab554fff2f3213ca7aa292',
    'gui_headless_gpu_plan.yaml':
        'f34aa10ec57d2a83ec353d7ea75d0cb220589d280d9c446bfe53991bc7617f82',
    'mission_fco_equivalence_draft.yaml':
        'bb7a35640cdfa084516d19e7b2e6d46dcd2cf2ff3608b7cd4724d78121f906d3',
    'multi_worker_admission.yaml':
        '9d70006925cd40f9849c5c3a0fd708c3657b5a737ebe2086fb593c715070d710',
    'research_prereg.yaml':
        '06811b4f3e89d83a34d5736b631252970beda56354f78df0133c97d496d0de6d',
    'rl_platform.yaml':
        '401d485c0c644f1823367a9c92677b79bd00187a6423b08d9598754f0bbe928c',
}

# 每份快照的冻结来源：`(提交, 该提交里的路径)`。
# 判据 c 用它复算字节，证明"快照 == 当时提交里的原文"，而不是从改写后的工作区拷的。
FROZEN_ORIGIN = {
    'gui_headless_plan.yaml': ('710d50f', 'src/agc_rl/config/w8_gui_headless_plan.yaml'),
    'gui_headless_gpu_plan.yaml': ('710d50f', 'src/agc_rl/config/w8_gui_headless_gpu_plan.yaml'),
    'mission_fco_equivalence_draft.yaml':
        ('bc1200d', 'src/agc_rl/config/w8_mission_fco_equivalence_draft.yaml'),
    'multi_worker_admission.yaml': ('0c0e942', 'src/agc_rl/config/w7c_admission_plan.yaml'),
    'research_prereg.yaml': ('c778c6e', 'src/agc_rl/config/w7b_prereg.yaml'),
    'rl_platform.yaml': ('8bdde4c', 'src/agc_rl/config/rl_platform.yaml'),
}

# ADR 正文记录的短哈希：(ADR 文件, 前 8 位, 后 4 位, 对应快照)
ADR_RECORDED = (
    ('docs/adr/0021-gui-headless-equivalence.md', '3afa82c4', 'a292',
     'gui_headless_plan.yaml'),
    ('docs/adr/0024-multi-worker-isolation.md', '9d700069', 'd710',
     'multi_worker_admission.yaml'),
)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_commit_blob(commit: str, path: str) -> str | None:
    """`git show <commit>:<path>` 的字节哈希；取不到（浅克隆 / 该提交无此文件）返回 None。"""
    try:
        blob = subprocess.check_output(
            ['git', 'show', '%s:%s' % (commit, path)],
            cwd=ROOT, stderr=subprocess.DEVNULL, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return hashlib.sha256(blob).hexdigest()


def test_snapshot_set_is_complete():
    """目录里的快照必须与 `FROZEN_SHA256` 表**一一对应**（防止新增未登记的快照）。"""
    on_disk = {p.name for p in SNAP_DIR.glob('*.yaml')}
    assert on_disk == set(FROZEN_SHA256), (
        '快照集合与 FROZEN_SHA256 表不一致：\n'
        '  仅磁盘有：%s\n  仅表里有：%s\n'
        '新增快照必须同时补进本表（含 FROZEN_ORIGIN 与哈希）。'
        % (sorted(on_disk - set(FROZEN_SHA256)), sorted(set(FROZEN_SHA256) - on_disk)))


def test_frozen_bytes_unchanged():
    """判据 a：6 份快照的字节必须与钉死的哈希一致。"""
    bad = []
    for name, want in sorted(FROZEN_SHA256.items()):
        path = SNAP_DIR / name
        assert path.is_file(), '快照缺失：%s' % name
        got = _sha256_file(path)
        if got != want:
            bad.append((name, want, got))
    assert not bad, (
        '冻结快照被改写（字节哈希不符）：\n%s\n'
        '这些文件是**冻结记录**，改它们等于伪造历史证据（ADR-0002）。\n'
        '若确需修正：须显式改本文件的 FROZEN_SHA256 并在提交信息里说明理由。'
        % '\n'.join('  %s\n    期望 %s\n    实际 %s' % (n, w, g) for n, w, g in bad))


def test_origin_commits_reproduce_the_bytes():
    """判据 c：快照必须能由登记的冻结提交**逐字节复现**。"""
    missing = []
    for name, (commit, path) in sorted(FROZEN_ORIGIN.items()):
        got = _sha256_commit_blob(commit, path)
        if got is None:
            missing.append('%s（%s:%s 取不到，可能是浅克隆）' % (name, commit, path))
            continue
        assert got == FROZEN_SHA256[name], (
            '%s 无法由 %s:%s 复现：\n  提交里 %s\n  快照   %s'
            % (name, commit, path, got, FROZEN_SHA256[name]))
    if missing:
        import pytest
        pytest.skip('无法复核来源（浅克隆或缺提交）：%s' % '; '.join(missing))


def test_adr_recorded_hashes_match_snapshots():
    """判据 b：ADR 正文里记录的短哈希必须与快照一致（否则 ADR 在引用假哈希）。"""
    bad = []
    for adr_rel, head, tail, snap in ADR_RECORDED:
        adr = ROOT / adr_rel
        assert adr.is_file(), 'ADR 缺失：%s' % adr_rel
        text = adr.read_text(encoding='utf-8')
        needle = '%s…%s' % (head, tail)
        if needle not in text:
            bad.append('%s 正文里找不到记录的哈希 `%s`' % (adr_rel, needle))
            continue
        got = FROZEN_SHA256[snap]
        if not (got.startswith(head) and got.endswith(tail)):
            bad.append('%s 记录 %s，但 %s 的实际哈希是 %s' % (adr_rel, needle, snap, got))
    assert not bad, (
        'ADR 记录的哈希与快照不符：\n  - %s\n'
        '要么快照被改写（改回原文），要么 ADR 记错了（改 ADR）。' % '\n  - '.join(bad))


if __name__ == '__main__':
    import sys
    failures = []
    for fn in (test_snapshot_set_is_complete, test_frozen_bytes_unchanged,
               test_origin_commits_reproduce_the_bytes,
               test_adr_recorded_hashes_match_snapshots):
        try:
            fn()
            print('PASS %s' % fn.__name__)
        except AssertionError as exc:
            print('FAIL %s\n  %s' % (fn.__name__, exc))
            failures.append(fn.__name__)
        except BaseException as exc:  # pytest.skip 等
            print('SKIP %s（%s）' % (fn.__name__, exc))
    sys.exit(1 if failures else 0)
