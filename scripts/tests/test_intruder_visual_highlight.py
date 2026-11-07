"""目标视觉高亮的**纯视觉**回归（离线，不启仿真）。

守护两件事，方向相反、缺一不可：

1. **高亮确实存在且够醒目**——否则判据 5 还是没达成（"改了但看不出来"等于没改）；
2. **物理一个字没动**——collision / inertial / mass / plugin / pose / 关节 / PX4 接口
 全部与改动前的展开式**逐字节一致**（派工单 「严格禁止」）。

第 2 点是本文件的主要价值：单看 xacro 源码很难发现"顺手给 base_link 加了个 collision"，
所以判定不看源码，而是把模型**真的展开成 SDF** 再逐项比对基线。

基线怎么来（**不存第二份 SDF 副本**，避免基线本身漂移）：从 git 取改动前的
`intruder_uav.sdf.xacro` 到临时目录展开，与工作区版本对比。

**基线提交是钉死的常量，不是 `HEAD`**（2026-10-31 修正）：
本文件写作时高亮尚未提交，`HEAD` 恰好等于"改动前"；但 步骤 0 的基线卫生提交把高亮
一起入库后，`HEAD` 就变成了"改动后"——拿 `HEAD` 当基线会退化成**自己跟自己比**，
`test_only_highlight_differs_from_baseline` 恒真、`test_x500_core_links_keep_inertial_and_collision`
反而恒假（joint 差从 +1 变 0）。这正是"守卫看似在跑、其实没在守"的典型形状，故改为常量
`BASELINE_REV`（改动前的最后一次提交，即登记的基线 `b627043`）。
该 rev 取不到时**跳过并说明**，不静默通过。

不启任何仿真进程；`xacro` + `gz sdf -p` 都是纯解析（秒级）。若无 ROS 环境则**跳过**并说明原因
（不静默通过）。

运行：
  python3 -m pytest scripts/tests/test_intruder_visual_highlight.py -q
"""

import os
import re
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
XACRO_PATH = os.path.join(ROOT, 'src', 'agc_sim', 'models', 'intruder_uav',
                          'intruder_uav.sdf.xacro')
REL_PATH = 'src/agc_sim/models/intruder_uav/intruder_uav.sdf.xacro'
# 改动前基线（高亮入库前的最后一次提交； 基线卫生提交把高亮入库后
# 若仍用 `HEAD`，比对会退化为"自己跟自己比"——见文件头「基线怎么来」）
BASELINE_REV = 'b627043'
PX4_MODELS = os.path.join(ROOT, 'toolchain', 'PX4-Autopilot', 'Tools', 'simulation', 'gz',
                          'models')
PX4_WORLDS = os.path.join(ROOT, 'toolchain', 'PX4-Autopilot', 'Tools', 'simulation', 'gz',
                          'worlds')
ROS_SETUP = '/opt/ros/jazzy/setup.bash'

# 高亮 link / joint / visual 的名字（改动时同步这三处）
HL_LINK = 'target_highlight'
HL_VISUAL = 'target_highlight_visual'
HL_JOINT = 'target_highlight_joint'


def _have_toolchain():
    if not os.path.isfile(ROS_SETUP) or not os.path.isdir(PX4_MODELS):
        return False
    return shutil.which('xacro') is not None or \
        os.path.exists('/opt/ros/jazzy/bin/xacro')


pytestmark = pytest.mark.skipif(
    not _have_toolchain(),
    reason='需要 ROS 2 Jazzy（xacro）+ 本机 PX4 gz 模型库；本地完整检出才有，'
           '缺失时**跳过**而不是静默通过')


def _env():
    env = dict(os.environ)
    res = PX4_MODELS + ':' + PX4_WORLDS
    env['SDF_PATH'] = res
    env['GZ_SIM_RESOURCE_PATH'] = res
    return env


def _run(cmd):
    return subprocess.run(['bash', '-c', 'source %s >/dev/null 2>&1; %s' % (ROS_SETUP, cmd)],
                          env=_env(), capture_output=True, text=True, cwd=ROOT)


def _expand(xacro_path, workdir, tag, controlled=True):
    """展开 → 返回 `gz sdf -p` 的**解析后**文本（失败直接测试失败，不静默）。"""
    os.makedirs(workdir, exist_ok=True)
    raw = os.path.join(workdir, tag + '.xacro.sdf')
    out = os.path.join(workdir, tag + '.expanded.sdf')
    arg = 'true' if controlled else 'false'
    r = _run('xacro %s controlled:=%s > %s' % (xacro_path, arg, raw))
    assert r.returncode == 0, 'xacro 展开失败：%s' % (r.stderr or r.stdout)
    r = _run('gz sdf -p %s > %s' % (raw, out))
    assert r.returncode == 0, 'gz sdf -p 解析失败：%s' % (r.stderr or r.stdout)
    assert 'Error Code' not in r.stderr, '解析报错：%s' % r.stderr
    with open(out, encoding='utf-8') as f:
        return f.read()


@pytest.fixture(scope='module')
def expanded(tmp_path_factory):
    """工作区版本 + `HEAD` 基线各展开一次（基线来自 git，不落第二份副本）。"""
    work = str(tmp_path_factory.mktemp('p13r2'))
    base_src = os.path.join(work, 'baseline_model.sdf.xacro')
    r = _run('git -C %s show %s:%s > %s' % (ROOT, BASELINE_REV, REL_PATH, base_src))
    if r.returncode != 0 or not os.path.getsize(base_src):
        pytest.skip('git 里取不到基线 %s 的该模型，无法展开比对' % BASELINE_REV)
    return {
        'new': _expand(XACRO_PATH, work, 'new'),
        'base': _expand(base_src, work, 'base'),
        'passive': _expand(XACRO_PATH, work, 'passive', controlled=False),
        'work': work,
    }


def _strip_highlight(text):
    """剥掉新增的高亮 link + joint（用于"其余部分必须逐字节一致"的比对）。"""
    text = re.sub(r"\n\s*<link name='%s'>.*?\n\s*</link>\n" % HL_LINK, '\n', text, flags=re.S)
    text = re.sub(r"\n\s*<joint name='%s'.*?\n\s*</joint>\n" % HL_JOINT, '\n', text,
                  flags=re.S)
    return text


# --------------------------------------------------------------------------------------
# 1. 高亮存在且醒目（判据 5 的正面证据）
# --------------------------------------------------------------------------------------

def test_controlled_model_has_highlight_link(expanded):
    text = expanded['new']
    assert HL_LINK in text, 'controlled 模型里没有高亮 link'
    assert HL_VISUAL in text, '高亮 link 里没有 visual'
    assert HL_JOINT in text, '高亮 link 没有 fixed joint 挂到 base_link'


def test_highlight_is_visually_conspicuous(expanded):
    """醒目 = 尺寸够大 **且** 颜色够橙/红（尺寸或颜色至少一项，实际两项都满足）。"""
    text = expanded['new']
    block = text[text.index("link name='%s'" % HL_LINK):]
    block = block[:block.index('</link>')]
    # 尺寸：球半径 ≥ 0.5 m（直径 ≥ 1 m），在 100 m 场站俯视下仍明显
    m = re.search(r'<radius>([\d.eE+-]+)</radius>', block)
    assert m, '高亮 visual 不是球（没有 radius）'
    assert float(m.group(1)) >= 0.5, '高亮球半径 %s m 太小，俯视下看不见' % m.group(1)
    # 颜色：橙色/红色档（R 高、G 中低、B 接近 0）
    amb = re.search(r'<ambient>([\d.eE+-]+) ([\d.eE+-]+) ([\d.eE+-]+)', block)
    assert amb, '高亮 visual 没有 ambient 颜色'
    r, g, b = (float(x) for x in amb.groups())
    assert r >= 0.8 and g <= 0.6 and b <= 0.2, (
        '高亮颜色不够醒目（期望橙/红：R≥0.8, G≤0.6, B≤0.2），实际 %s %s %s' % (r, g, b))
    # 自发光：不受场景光照明暗影响
    assert '<emissive>' in block, '高亮 visual 没有 emissive（暗场景下会看不见）'


def test_highlight_has_no_collision(expanded):
    """高亮 link **不得**带 collision —— 否则会参与接触/测距，等于改了物理。"""
    text = expanded['new']
    start = text.index("link name='%s'" % HL_LINK)
    block = text[start:start + text[start:].index('</link>')]
    assert '<collision' not in block, '高亮 link 带了 collision —— 会改变物理与碰撞真值'


def test_highlight_mass_is_negligible_not_zero(expanded):
    """质量必须**极小但非零**（dartsim 对零质量 body 行为未定义）。"""
    text = expanded['new']
    start = text.index("link name='%s'" % HL_LINK)
    block = text[start:start + text[start:].index('</link>')]
    m = re.search(r'<mass>([\d.eE+-]+)</mass>', block)
    assert m, '高亮 link 没有 inertial/mass'
    mass = float(m.group(1))
    assert 0 < mass <= 1e-3, '高亮 link 质量应在 (0, 1e-3] kg，实际 %r' % mass


# --------------------------------------------------------------------------------------
# 2. 物理一个字没动（派工单「严格禁止」的机械守卫）
# --------------------------------------------------------------------------------------

def test_only_highlight_differs_from_baseline(expanded):
    """剥掉高亮元素后，展开式必须与改动前**逐字节一致**。

 这是本单最强的守卫：任何"顺手"改了 collision / inertial / pose / plugin / 关节，
 都会在这里暴露（包括缩进与字段顺序）。
    """
    new, base = _strip_highlight(expanded['new']), _strip_highlight(expanded['base'])
    if new != base:
        import difflib
        diff = '\n'.join(list(difflib.unified_diff(
            base.splitlines(), new.splitlines(),
            'baseline(%s)' % BASELINE_REV, 'working', lineterm=''))[:60])
        pytest.fail('除高亮外模型发生了变化（物理字段不得改动）：\n' + diff)


def test_x500_core_links_keep_inertial_and_collision(expanded):
    """x500 原有 link 的 inertial / collision 数量与质量值不变。"""
    new, base = expanded['new'], expanded['base']

    def counts(text):
        return {
            'collision': len(re.findall(r'<collision name=', text)),
            'inertial': len(re.findall(r'<inertial>', text)),
            'mass': sorted(re.findall(r'<mass>([\d.eE+-]+)</mass>', text)),
            'plugin': len(re.findall(r'<plugin ', text)),
            'joint': len(re.findall(r'<joint name=', text)),
        }

    c_new, c_base = counts(new), counts(base)
    # 高亮 link 自带 1 个 inertial + 1 个 fixed joint，二者各允许 +1；其余必须完全相同
    assert c_new['joint'] == c_base['joint'] + 1, (c_new['joint'], c_base['joint'])
    assert c_new['inertial'] == c_base['inertial'] + 1, (
        'inertial 只应多出高亮 link 那一个：基线 %r → 现在 %r'
        % (c_base['inertial'], c_new['inertial']))
    for key in ('collision', 'plugin'):
        assert c_new[key] == c_base[key], (
            '%s 发生了变化：基线 %r → 现在 %r' % (key, c_base[key], c_new[key]))
    # 质量集合：基线原样保留 + 恰好多一个可忽略的极小值（x500 的 5 个质量一个不少）
    extra = [m for m in c_new['mass'] if m not in c_base['mass']]
    assert len(extra) == 1, '质量值只应多出高亮那一个，实际多出 %r' % extra
    assert float(extra[0]) <= 1e-3, '新增质量必须是可忽略量级：%r' % extra
    for m in c_base['mass']:
        assert c_base['mass'].count(m) <= c_new['mass'].count(m), (
            'x500 原有质量值 %r 变少了' % m)


def test_no_px4_interface_change(expanded):
    """PX4 接口零改动：plugin 名、motor_speed 话题、模型名都要原样。"""
    new, base = expanded['new'], expanded['base']
    for pattern in (r'MulticopterMotorModel', r'command/motor_speed',
                    r'<model name=.intruder_uav.>'):
        assert re.findall(pattern, new) == re.findall(pattern, base), (
            'PX4 接口字段 %r 发生了变化' % pattern)


def test_passive_branch_unchanged(expanded):
    """passive 分支（controlled=false）行为不回退：仍是红方块 + VelocityControl。"""
    text = expanded['passive']
    assert '<diffuse>1 0 0 1</diffuse>' in text, 'passive 分支的红色方块丢了'
    assert 'VelocityControl' in text, 'passive 分支的 VelocityControl 插件丢了'
    assert HL_LINK not in text, 'passive 分支不应出现演示高亮（只在 controlled 分支）'


# --------------------------------------------------------------------------------------
# 3. 源码层面的纪律（不依赖展开也能查）
# --------------------------------------------------------------------------------------

def _code_lines_of(text):
    """去掉 XML 注释后的**真实元素行**（注释里解释"无 collision"不算有 collision）。"""
    text = re.sub(r'<!--.*?-->', '', text, flags=re.S)
    return [ln for ln in text.splitlines() if ln.strip()]


def test_xacro_source_only_touches_visual_structure():
    """源码里新增的是 link/visual/joint；**不得**出现 collision 或改 plugin。

 只看**代码**不看注释：注释要解释"这里刻意没有 collision"，那是对的，不该被当成违规。
    """
    with open(XACRO_PATH, encoding='utf-8') as f:
        text = f.read()
    start = text.index('<xacro:if value="$(arg controlled)">')
    block = '\n'.join(_code_lines_of(text[start:]))
    assert '<collision' not in block, 'controlled 分支出现了 collision'
    assert '<plugin' not in block, 'controlled 分支出现了 plugin（PX4 接口不得改）'
    assert '<contact' not in block and '<surface' not in block, '出现了接触/表面参数'


def test_highlight_disabled_when_not_controlled():
    """高亮必须写在 `xacro:if controlled` 之内（不污染 M0/W5 的 passive 路径）。"""
    with open(XACRO_PATH, encoding='utf-8') as f:
        text = f.read()
    cond = text.index('<xacro:if value="$(arg controlled)">')
    end = text.index('</xacro:if>', cond)
    assert HL_LINK in text[cond:end], '高亮不在 controlled 分支内'
