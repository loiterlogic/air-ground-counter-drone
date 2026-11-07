#!/usr/bin/env python3
"""`composition.py` 门面的**再导出完整性**守护。

## 为什么存在

2026-11-07 把 `composition.py`（1445 行）按内聚性拆成 7 个 `scene_*.py` 后，
门面只剩 `from ... import ...`。这类"纯再导出"文件有一个安静的失效模式：

**拆的时候漏导出一个符号，调用方要到运行期才炸**——而它可能只在一个
`backend:=full` 分支里用到，离线冒烟根本不经过那条路。

## 判据

| # | 断言 |
|---|---|
| a | 每个 `scene_*.py` 里定义的**公开**函数/常量，门面必须能取到（不得漏导出） |
| b | 门面的 `__all__` 与"实际可取的公开符号"一致（不得写进不存在的名字） |
| c | 门面必须能**单文件加载**（`spec_from_file_location`，本目录不在 `sys.path`） |

判据 c 守的是 `test_scene_config_invariants.py` 的加载方式：它用
`spec_from_file_location` 隔离加载 `composition.py`，此时兄弟模块不在 `sys.path`。
门面顶部的 `sys.path` 自举一旦被"整理"掉，那批测试会全部 ModuleNotFoundError。

退出码：0 = PASS；1 = FAIL。

用法：
  python3 -m pytest scripts/tests/test_composition_facade.py -q
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LAUNCH = ROOT / 'src' / 'agc_task' / 'launch'
FACADE = LAUNCH / 'composition.py'

# 门面**不**再导出的私有实现细节（路径常量 / 缓存），逐条写理由。
PRIVATE_EXEMPT = {
    '_SRC_SIM_LAUNCH': '源码树回退路径常量，实现细节；调用方一律传 sim_share',
    '_SRC_AIR_CONFIG': '同上（air.yaml 回退路径）',
    '_WORLD_MAP_CACHE': '按路径缓存，实现细节；不应被外部读',
}


def _load_facade():
    """按 `test_scene_config_invariants` 的方式**隔离**加载门面（不依赖 sys.path 里有本目录）。"""
    sys.path[:] = [p for p in sys.path if str(LAUNCH) not in p]
    spec = importlib.util.spec_from_file_location('composition_under_test', FACADE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _module_public_symbols(path: Path):
    """一个 `scene_*.py` 里定义的公开顶层函数与常量名。"""
    tree = ast.parse(path.read_text(encoding='utf-8'))
    names = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and not node.name.startswith('_'):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and not target.id.startswith('_'):
                    names.add(target.id)
    return names


def test_facade_re_exports_every_public_symbol():
    """判据 a：子模块的公开符号必须都能从门面取到。"""
    facade = _load_facade()
    missing = {}
    for path in sorted(LAUNCH.glob('scene_*.py')):
        absent = sorted(n for n in _module_public_symbols(path) if not hasattr(facade, n))
        if absent:
            missing[path.name] = absent
    assert not missing, (
        '门面漏导出（调用方会到运行期才炸）：\n%s\n'
        '把缺的名字加进 composition.py 的 import 与 __all__。'
        % '\n'.join('  %s: %s' % (k, ', '.join(v)) for k, v in missing.items()))


def test_all_matches_actual_symbols():
    """判据 b：`__all__` 与实况一致（不得写进不存在的名字，也不得漏登记）。"""
    facade = _load_facade()
    declared = set(facade.__all__)
    assert len(facade.__all__) == len(declared), '__all__ 有重复项'
    phantom = sorted(n for n in declared if not hasattr(facade, n))
    assert not phantom, '__all__ 里登记了不存在的名字：%s' % phantom

    actual = {n for n in dir(facade)
              if not n.startswith('_') and n not in ('os', 'sys')}
    undeclared = sorted(actual - declared)
    assert not undeclared, (
        '门面有公开符号未登记进 __all__：%s\n'
        '（要么加进 __all__，要么说明它不该公开）' % undeclared)


def test_facade_loads_without_sibling_on_sys_path():
    """判据 c：门面必须能单文件加载（兄弟模块不在 sys.path）。"""
    facade = _load_facade()          # 内部已把本目录从 sys.path 移除
    assert callable(facade.load_scene)
    assert callable(facade.assertions)
    assert callable(facade.build_manifest)


def test_private_exempt_is_documented():
    """例外必须逐条写理由（防止"加个豁免"变成新的静默失效模式）。"""
    for name, reason in PRIVATE_EXEMPT.items():
        assert reason.strip(), 'PRIVATE_EXEMPT 的 %s 缺理由' % name
