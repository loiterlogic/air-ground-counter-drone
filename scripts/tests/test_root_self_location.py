#!/usr/bin/env python3
"""`test_root_self_location.py` —— 防复发回归：**运行期解析文件的路径必须自定位**（P2-1 裁定 D）。

## 守护的缺陷（2026-10-31 实测）

`run_demo.sh` 与 `scripts/demo/common.py` 曾写死 `ROOT = '/home/chen/AGC'`。后果（实测，非推理）：

| 观察 | 结果 |
|---|---|
| `git clone /home/chen/AGC /tmp/x` 后 `ls /tmp/x/install` | **不存在** |
| `/tmp/x/run_demo.sh doctor` | **PASS 14/14**（误报） |
| 它报的路径 | `GZ_SIM_SYSTEM_PLUGIN_PATH = /home/chen/AGC/install/...`（**原仓库**） |
| `/tmp/x/run_demo.sh` | **启动了原仓库的仿真**，产物落 `/home/chen/AGC/experiments/demo/` |

即"陌生人照 README 能跑起来"这条判据**实质不成立**。

## 判定口径（**按用途分类，不按字面**）

- **运行期解析类**：脚本用它来**定位真实文件**（读 SDF / 起进程 / 找 install / 写产物）
 → **必须自定位**（`__file__` / `BASH_SOURCE`），**不得**出现字面量根；
- **允许保留**（白名单，每条写理由）：
 1. **契约默认值**：`agc_root` 的 launch 默认值 —— 受 `scripts/toolchain_root_check.py` 保护，
 改它等于改契约口径（ 审查明令**不得改**）；
 2. **注释 / 文档串 / 报错提示**：不参与路径解析，只给人看；
 3. **历史/开发工具**（`scripts/research/**`、`scripts/archive/**`、`docs/**`、`ADR-0026）：
 不在交付/验证路径上，忠实登记为"不可移植"，不在本单范围。

## 扩展（裁定 α+ 整类修，2026-10-31）

 克隆实测暴露：**C++ `declare_parameter` 默认值**与 **YAML 字面量**同样在运行期决定
写盘位置（`run_logger` 的 `experiments_root` / `git_root`），只修 Python/launch 不够。
故守护范围扩到三类来源：

| 来源 | 现状 | 守护 |
|---|---|---|
| Python / shell | 自定位 | 不得出现字面量（注释除外） |
| **YAML `src/**/config/*.yaml`** | **已删键**（16 处） | 不得再出现绝对路径字面量 |
| **C++ `declare_parameter` 默认值** | **保留**（契约式缺省） | 必须**仍在**（见下） |

**为什么 C++ 默认值要"保留"而不是删**：YAML 删键后，`w6` 之外的独立启动
（`m0_skeleton` / 研究 runner / 无 `agc_root` 的入口）仍会落到 C++ 默认值。
若删 YAML 又删 C++ 默认值，等于把"写回主仓"的脚枪留在这些入口 —— 那是**更坏**的结局。
正确做法：**C++ 默认值作为契约式缺省保留**，由**交付 launch 统一覆盖**；
守护测试同时断言"默认值仍在" + "交付 launch 已覆盖"。

## 断言

1. 交付入口 `run_demo.sh` 的 `ROOT=` 必须是自定位（`BASH_SOURCE`），不得是字面量；
2. `scripts/demo/common.py` 的 `ROOT` 必须由 `__file__` 推导；
3. 冒烟/交付路径上的脚本（`tests/run_smoke.py`、`tests/check_scene_geometry.py`、
 `scripts/tests/*.py`）不得出现**字面量赋值**形式的根（注释里提到不算）；
4. `scripts/toolchain_root_check.py` 与 `src/agc_air/launch/air_bringup.launch.py` 的契约默认值
 **仍在**（防止有人"顺手"改掉契约）；
5. **白名单逐条有理由**（本文件 `ALLOWED` 表）。

运行：
  python3 -m pytest scripts/tests/test_root_self_location.py -q
"""

import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
HARD = '/home/chen/AGC'

# 白名单：允许出现字面量根的位置 + 理由（**每条必须写理由**）
ALLOWED = {
    'src/agc_air/launch/air_bringup.launch.py': (
        '契约默认值：`agc_root` 的 launch 默认值，受 scripts/toolchain_root_check.py 断言保护；'
        'round-6 审查明令不得改（改它等于改契约口径）'),
    'src/agc_task/launch/main.launch.py': (
        '同上：`agc_root` 的 launch 默认值声明 + 两处报错提示文字（不参与路径解析）'),
    'scripts/toolchain_root_check.py': (
        '工具本身要**校验**这个默认值，故必须知道该字面量'),
    'src/agc_task/src/run_logger.cpp': (
        '**契约式缺省**：`experiments_root` / `git_root` 的 `declare_parameter` 默认值。'
        'round-9 已删 YAML 字面量，若再删这里，`m0_skeleton` / 研究 runner 等不经交付 launch 的'
        '入口会失去缺省；由 `main.launch.py` 在交付路径统一覆盖。守护见 '
        '`test_cpp_defaults_are_preserved`'),
}

# 必须自定位的文件（运行期解析类）
MUST_SELF_LOCATE = [
    'run_demo.sh',
    'scripts/demo/common.py',
    'tests/run_smoke.py',
    'tests/check_scene_geometry.py',
]


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


def _code_lines(text):
    """去掉注释后的真实代码行（注释里提到路径不算违规）。"""
    # 去掉 # 之后的内容（粗糙但足够：本仓没有含 # 的字符串字面量里放路径）
    out = []
    for line in text.splitlines():
        stripped = line.split('#', 1)[0]
        out.append(stripped)
    return '\n'.join(out)


@pytest.mark.parametrize('rel', MUST_SELF_LOCATE)
def test_no_literal_root_in_self_locating_files(rel):
    """运行期解析类文件**不得**用字面量根（注释里提到可以）。"""
    text = _read(rel)
    code = _code_lines(text)
    # 允许出现在"注释/文档串"里；这里只查代码行
    assert HARD not in code, (
        '%s 的**代码**里出现字面量根 %r —— 该文件用于运行期解析，必须自定位'
        '（`__file__` / `BASH_SOURCE`）' % (rel, HARD))


def test_run_demo_root_uses_bash_source():
    """`run_demo.sh` 的 ROOT 必须由 `BASH_SOURCE` 推导。"""
    text = _read('run_demo.sh')
    assert 'BASH_SOURCE' in text, 'run_demo.sh 未用 BASH_SOURCE 自定位'
    m = re.search(r'^ROOT=.*$', text, re.M)
    assert m, 'run_demo.sh 里找不到 ROOT= 赋值'
    assert 'BASH_SOURCE' in m.group(0), (
        'run_demo.sh 的 ROOT 赋值不是自定位：%r' % m.group(0))


def test_common_root_uses_dunder_file():
    """`common.py` 的 ROOT 必须由 `__file__` 推导。"""
    text = _read('scripts/demo/common.py')
    m = re.search(r'^ROOT\s*=.*$', text, re.M)
    assert m, 'common.py 里找不到 ROOT 赋值'
    assert '__file__' in m.group(0), 'common.py 的 ROOT 赋值不是自定位：%r' % m.group(0)


def test_smoke_entry_self_locates():
    """冒烟入口（run_smoke.py）必须自定位（它是"陌生人第一条命令"的入口）。"""
    text = _read('tests/run_smoke.py')
    m = re.search(r'^ROOT\s*=.*$', text, re.M)
    assert m and '__file__' in m.group(0), 'run_smoke.py 的 ROOT 不是自定位'


def test_contract_default_still_intact():
    """契约默认值**必须仍在**（防有人为了"可移植"顺手改掉契约）。"""
    air = _read('src/agc_air/launch/air_bringup.launch.py')
    assert "default_value='/home/chen/AGC'" in air, (
        'air_bringup.launch.py 的 agc_root 契约默认值被改动或删除 —— 那是契约口径，不得改')
    checker = _read('scripts/toolchain_root_check.py')
    assert HARD in checker, 'toolchain_root_check.py 不再校验契约默认值'


def test_allowed_entries_have_reason():
    """白名单每条都必须写理由（空理由等于没白名单）。"""
    for rel, reason in ALLOWED.items():
        assert reason and len(reason.strip()) >= 8, '白名单 %s 缺理由' % rel
        assert os.path.isfile(os.path.join(ROOT, rel)), '白名单文件不存在：%s' % rel


def test_yaml_configs_have_no_absolute_root():
    """`src/**/config/*.yaml` 里不得再有绝对路径字面量（round-9 已删 16 处）。

 YAML 字面量会在**运行期**决定写盘位置（ 实测：克隆 run 的 summary 写回原仓库），
 且它比 C++ 默认值更"隐蔽"——launch 不显式传参时它就生效。
    """
    config_dir = os.path.join(ROOT, 'src', 'agc_task', 'config')
    offenders = []
    for name in sorted(os.listdir(config_dir)):
        if not name.endswith('.yaml'):
            continue
        with open(os.path.join(config_dir, name), encoding='utf-8') as f:
            text = f.read()
        if HARD in text:
            offenders.append(name)
    assert not offenders, (
        'YAML 里仍有绝对路径字面量 %r —— 运行期会写回该路径（round-9 已清理，勿回退）'
        % offenders)


def test_cpp_defaults_are_preserved():
    """C++ 的 `experiments_root` / `git_root` 默认声明**必须仍在**（契约式缺省）。

 这是**反向**守护： 删了 YAML 键，若有人"顺手"把 C++ 默认值也删了，
 `m0_skeleton` / 研究 runner 等**不经交付 launch** 的入口会失去缺省 → 行为变成未定义。
    """
    src = _read('src/agc_task/src/run_logger.cpp')
    assert 'declare_parameter<std::string>("experiments_root"' in src, (
        'run_logger.cpp 的 experiments_root 默认声明被删除 —— 它是契约式缺省，不得删')
    assert 'declare_parameter<std::string>("git_root"' in src, (
        'run_logger.cpp 的 git_root 默认声明被删除 —— 它是契约式缺省，不得删')
    # 且默认值必须是那个字面量（与 air_bringup 的 agc_root 同源）
    assert HARD + '/experiments' in src, 'experiments_root 默认值被改成了别的路径'
    assert '"git_root", "%s"' % HARD in src or '"git_root", "' + HARD + '"' in src, \
        'git_root 默认值被改成了别的路径'


def test_delivery_launch_overrides_both_keys():
    """交付 launch（`main.launch.py`）必须**显式覆盖**两个键（否则 C++ 默认值生效 → 写回主仓）。"""
    src = _read('src/agc_task/launch/main.launch.py')
    assert "'experiments_root'" in src, (
        'main.launch.py 未显式传 experiments_root —— 克隆跑会把评测产物写回主仓')
    assert "'git_root'" in src, (
        'main.launch.py 未显式传 git_root —— 克隆跑的 summary 里 git 身份仍读主仓')
    # 且值必须由 agc_root 派生，而不是另一个字面量
    assert "os.path.join(_agc_root, 'experiments')" in src, (
        'experiments_root 不是由 agc_root 派生（可能又写成了字面量）')
    assert "'git_root': _agc_root" in src, 'git_root 不是由 agc_root 派生'


def test_doctor_reports_clone_path_not_hardcoded():
    """`common.ROOT` 必须等于**本仓实际位置**（而不是字面量），这是 doctor 不误报的前提。"""
    sys.path.insert(0, os.path.join(ROOT, 'scripts', 'demo'))
    import common
    assert os.path.realpath(common.ROOT) == os.path.realpath(ROOT), (
        'common.ROOT (%r) != 本仓实际位置 (%r) —— doctor 会误报' % (common.ROOT, ROOT))
