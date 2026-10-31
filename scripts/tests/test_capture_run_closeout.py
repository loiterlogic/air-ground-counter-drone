#!/usr/bin/env python3
"""`capture_run.py` 的**收尾路径**回归（T0：不启仿真、不启 GUI）。

## 守护的缺陷（2026-10-31 P2-1 round-5 实测）

一次**成功的** T2 取帧（22 帧已落盘、任务 `TRACKING_SUCCESS`）在**收尾阶段**崩溃：

```text
File "scripts/demo/capture_run.py", line 596, in main
    prefer_size = tuple(stable_detail.get('main_size')) if ...
UnboundLocalError: cannot access local variable 'stable_detail'
```

根因：`stable_median, stable_detail = stable_skyband(...)` 被写在了**使用它的那行之后**。
后果很隐蔽——**帧已经全部取到**，只是三图挑选与 manifest 没生成；如果只看"取到 22 帧"会以为成功。

**为什么这条要有回归**：这类"使用早于赋值"的错，Python 在**函数被调用前**不会报，
而 `main()` 只在真实 T2 收尾时才走到那几行 → 每轮只能靠一次昂贵运行才暴露。
本文件用**静态解析**（不执行 main）把顺序问题钉住，秒级、零副作用。

## 断言

1. `main()` 里对 `stable_detail` / `stable_median` 的**首次使用**必须晚于**赋值**；
2. `main()` 里对 `prefer_size` 的使用必须晚于赋值；
3. `stable_skyband()` 可被导入且行为符合预登记（用合成样本，不读真实帧）；
4. 模块可 `import`（无语法/顶层错误）。

运行：
  python3 -m pytest scripts/tests/test_capture_run_closeout.py -q
"""

import ast
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'scripts', 'demo'))

CAPTURE = os.path.join(ROOT, 'scripts', 'demo', 'capture_run.py')


def _main_fn():
    with open(CAPTURE, encoding='utf-8') as f:
        tree = ast.parse(f.read(), filename=CAPTURE)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == 'main':
            return tree, node
    raise AssertionError('capture_run.py 里找不到 main()')


def _first_lineno(fn, name, *, as_store):
    """返回 `name` 在 fn 内首次**赋值**或**使用**的行号；找不到返回 None。

    - as_store=True → 找 `name = ...`（含 tuple 解包）的赋值位置；
    - as_store=False → 找 `name` 出现在**加载上下文**（读）的位置。
    """
    found = None
    for node in ast.walk(fn):
        lineno = getattr(node, 'lineno', None)
        if lineno is None:
            continue
        if as_store:
            if isinstance(node, ast.Name) and node.id == name and \
                    isinstance(node.ctx, (ast.Store, ast.Del)):
                found = lineno if found is None else min(found, lineno)
        else:
            if isinstance(node, ast.Name) and node.id == name and \
                    isinstance(node.ctx, ast.Load):
                found = lineno if found is None else min(found, lineno)
    return found


@pytest.mark.parametrize('name', ['stable_detail', 'stable_median', 'prefer_size'])
def test_used_after_assigned(name):
    """使用必须晚于赋值——这条直接对应 round-5 的 `UnboundLocalError`。"""
    _tree, fn = _main_fn()
    store = _first_lineno(fn, name, as_store=True)
    load = _first_lineno(fn, name, as_store=False)
    if load is None:
        pytest.skip('main() 里没有使用 %s（可能已重构）' % name)
    assert store is not None, '%s 在 main() 里从未被赋值，却被使用' % name
    assert store < load, (
        '%s 在 main() 里**先使用（第 %d 行）后赋值（第 %d 行）**——'
        '真实 T2 收尾时会抛 UnboundLocalError（round-5 已踩过）' % (name, load, store)
    )


def test_module_imports():
    """模块可导入（无语法/顶层错误）。"""
    import capture_run          # noqa: F401
    assert hasattr(capture_run, 'main')
    assert hasattr(capture_run, 'stable_skyband')
    assert hasattr(capture_run, 'pick_frames')


def test_stable_skyband_classification():
    """`stable_skyband()` 的判定符合预登记：稳定 → 中位数；全跳变 → 不可判。"""
    import capture_run as C

    # 造 5 个"同尺寸、skyband 全 0"的样本 → 中位数 0 → top_down
    items = [{'path': '/nonexistent-%d.png' % i, 'skyband': 0.0, 'size': [831, 952]}
             for i in range(5)]
    median, detail = C.stable_skyband(items)
    assert median == 0.0
    assert detail['verdict'] == 'top_down'
    assert detail['kept'] == 5

    # 混合：4 个 0.0 + 1 个 0.28 → 中位数仍是 0.0（抗单个跳变）
    items2 = list(items) + [{'path': '/nonexistent-x.png', 'skyband': 0.28,
                             'size': [831, 952]}]
    median2, detail2 = C.stable_skyband(items2)
    assert median2 == 0.0, '单个跳变帧不应改变中位数'
    assert detail2['verdict'] == 'top_down'


def test_pick_frames_returns_three_keys():
    """`pick_frames()` 必须返回 start/tracking/terminal 三个键（缺的为 None，不抛异常）。"""
    import capture_run as C
    out = C.pick_frames([], [])
    assert set(out) >= {'start', 'tracking', 'terminal', 'notes'}
    assert out['start'] is None and out['tracking'] is None and out['terminal'] is None
