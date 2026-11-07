#!/usr/bin/env python3
"""闸门**旁路**回归 —— 防"看着有保护、实际零覆盖"。

## 为什么存在

2026-11-06 可维护性复查用临时反例实测了四个闸门，发现三个真实缺口。
这些缺口不会让现有测试变红（现有测试守的是"已登记的东西"），但会让
**攻击面而不是登记面**失守：

  A. `test_branch_ledger.py` 的命名正则只收 `_source|_mode|_backend|_path`，
     漏 `_type` —— 而治理规范明确把它列为路线分支的命名形状。
     实测：加 `evil_type` 时闸门 PASS。
  B. `test_reference_discipline.py` 用"行首前缀"判断注释，**docstring 正文行**
     全部漏扫（那 ~300 处历史编号正是这么活下来的）。
     实测：在 docstring 正文写 `R-031` 时闸门 PASS。
  C. 同文件把 `git diff` 的非 0 退出码吞成 `return`，基线不可达（浅克隆 / squash）
     时闸门**永远绿**。这是最危险的失效：比没有闸门更糟，因为它给假安心。

本文件把三种旁路固化成测试。**每加一条旁路修法，就在这里加一条用例**——
反例写在注释里会腐烂，写成断言才拦得住下一轮。

不启动外部进程（除 C 的 subprocess 探测）、不读 ROS、不联网，纯静态（T0）。

运行：
  python3 -m pytest scripts/tests/test_guard_bypasses.py -q
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, str(ROOT / rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope='module')
def branch_ledger():
    return _load('bl_bypass', 'scripts/tests/test_branch_ledger.py')


@pytest.fixture(scope='module')
def ref_discipline():
    return _load('rd_bypass', 'scripts/tests/test_reference_discipline.py')


# --------------------------------------------------------------------------------------
# 旁路 A：`xxx_type` 也必须被认作路线分支
# --------------------------------------------------------------------------------------
@pytest.mark.parametrize('name', [
    'evil_source', 'evil_mode', 'evil_backend', 'evil_path', 'evil_type',
    'perception_path', 'vision_mode', 'detector_backend', 'target_source',
])
def test_branch_name_shape_covers_all_five_suffixes(branch_ledger, name):
    """规范列出的五种命名形状都必须命中（`_type` 曾漏收）。"""
    assert branch_ledger.BRANCH_NAME_RE.match(name), (
        '%r 应被识别为路线分支命名形状，但正则未命中——'
        '这类参数会被"顺手加进 launch"而不触发闸门' % name)


@pytest.mark.parametrize('name', [
    'px4_sim_model',    # 资产选择（规范明列的排除项）
    'world_map',
    'seed',
    'goal_follow_target',
    'backend',
    'use_sim_time',
])
def test_branch_name_shape_excludes_non_branches(branch_ledger, name):
    """形状不像的普通参数不得误报（否则白名单形同虚设）。"""
    assert not branch_ledger.BRANCH_NAME_RE.match(name), (
        '%r 不是路线分支命名形状，却被正则命中——闸门会误报' % name)


# --------------------------------------------------------------------------------------
# 旁路 B：docstring 正文行与块注释都必须被扫描
# --------------------------------------------------------------------------------------
def test_docstring_body_lines_are_scanned(ref_discipline, tmp_path):
    """docstring **正文行**（不以 # 或三引号开头）必须算作可扫描行。"""
    probe = tmp_path / 'probe.py'
    probe.write_text(
        '"""module docstring.\n'
        '\n'
        'Original R-031 finding lives here, this line has no comment marker.\n'
        '"""\n'
        '\n'
        'VALUE = 1\n',
        encoding='utf-8')
    got = ref_discipline._scanned_line_numbers(probe)
    assert got is not None
    assert 3 in got, 'docstring 正文行未被识别（旁路 B：历史编号可借此复活）'


def test_hash_comments_and_inline_comments_are_scanned(ref_discipline, tmp_path):
    probe = tmp_path / 'probe2.py'
    probe.write_text(
        '# R-031 leading comment\n'
        'VALUE = 1  # R-031 inline comment\n'
        'OTHER = 2\n',
        encoding='utf-8')
    got = ref_discipline._scanned_line_numbers(probe)
    assert got is not None
    assert 1 in got, '行首注释未被识别'
    assert 2 in got, '行尾内联注释未被识别'
    assert 3 not in got, '纯代码行（无注释无字符串）被误判为可扫描行'


def test_single_line_strings_are_scanned(ref_discipline, tmp_path):
    """**2026-11-07 口径变更**：单行字符串也算可扫描行。

    旧口径只收多行 STRING，理由是"单行字符串常量是数据标识"。实测该口径漏掉了
    活跃代码层 127 处命中里的 122 处（`description='…W7-c…'`、`assert` 消息、
    `'proposition': '…F-04…'`）——闸门一行都拦不住，规则说"只能在代码中引用 ADR"
    而机器只查注释。故改为**字符串一律扫描**；数据标识豁免由 `DATA_PATH_RE`
    （`experiments/` 路径行）负责，不在 `_scanned_line_numbers` 层面豁免。
    """
    probe = tmp_path / 'probe3.py'
    probe.write_text('PATTERN = "R-031"\n', encoding='utf-8')
    got = ref_discipline._scanned_line_numbers(probe)
    assert got is not None
    assert 1 in got, '单行字符串未被识别（旁路：单行 docstring / description 可借此复活）'


def test_syntax_error_file_falls_back_to_scanning_all(ref_discipline, tmp_path):
    """非合法 Python（语法错误）时不得静默跳过，应返回 None 交给保守判定。"""
    probe = tmp_path / 'broken.py'
    probe.write_text('def broken(:\n    pass\n', encoding='utf-8')
    assert ref_discipline._scanned_line_numbers(probe) is None, (
        '语法错误文件必须触发保守路径（整文件可疑），不得返回空集放行')


# --------------------------------------------------------------------------------------
# 旁路 C：基线不可达时必须显式失败
# --------------------------------------------------------------------------------------
def test_baseline_unavailable_raises(ref_discipline, monkeypatch):
    """基线不可达（git diff 非 0）时不得静默放行。"""
    real_run = subprocess.run

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args[0] if args else [], 128, stdout='', stderr='fatal: bad object')

    monkeypatch.setattr(ref_discipline.subprocess, 'run', fake_run)
    with pytest.raises(ref_discipline.BaselineUnavailable):
        list(ref_discipline._changed_lines())
    monkeypatch.setattr(ref_discipline.subprocess, 'run', real_run)


def test_baseline_available_still_works(ref_discipline):
    """修完后正常仓库仍能取到改动行（不得把闸门改死）。"""
    lines = list(ref_discipline._changed_lines())
    assert isinstance(lines, list)  # 不抛异常即达标


def test_current_baseline_is_reachable():
    """`BASELINE` 常量必须指向本仓可达的 commit（否则闸门实际零覆盖）。"""
    mod = _load('rd_baseline', 'scripts/tests/test_reference_discipline.py')
    proc = subprocess.run(
        ['git', 'cat-file', '-e', mod.BASELINE + '^{commit}'],
        cwd=ROOT, capture_output=True, text=True)
    assert proc.returncode == 0, (
        'BASELINE=%s 在本仓不可达；闸门会因此零覆盖（见 test_guard_bypasses 旁路 C）'
        % mod.BASELINE)


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
