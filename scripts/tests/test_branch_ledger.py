"""路线分支台账核对 —— launch 里出现台账外的路线分支参数即失败。

**为什么存在**：2026-11-04 用户发现 `w6.launch.py` 有 18 个 launch 参数、其中 7 个是
死参数或只服务已结档研究，并追问"为什么会有这种多路线"。根因是研究期开关未随研究结档收口。
规范见 `docs/conventions/路线分支治理.md`。

**本测试断言的是一份"人工判定过的白名单"**（该规范 5.1 节），不是镜像：

  * launch 文件里出现 `xxx_source` / `xxx_mode` / `xxx_backend` / `xxx_path` 形式
    （即"同一功能位置有 ≥2 个实现、由参数选择"）的 `DeclareLaunchArgument`，
  * 必须**恰好**等于台账里的已批准集合；
  * 多一个 = 有人未经批准新增路线分支（须走规范的 2.2 节四项准入）；
  * 少一个 = 有人删了分支却没更新台账（须走 4.2 节清退动作）。

**为什么用白名单而不是"检测到分支就报错"**：数值参数、场景轴、地图选择都不是路线分支，
机械检测会误报。白名单逼迫新增者**先判定、再登记**，这正是规范要的。

不启动外部进程、不读 ROS、不联网，纯静态（T0）。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CONVENTION = ROOT / 'docs' / 'conventions' / '路线分支治理.md'

# --------------------------------------------------------------------------------------
# 第二真源：已批准的路线分支（= 规范 5.1 节「已批准的分支」表）
# --------------------------------------------------------------------------------------
# 判定依据：**今天就有消费者**，且退役条件已写进规范 5.1。
# 新增行必须先满足规范 2.2 节四项（含**用户明确允许**），再改这里。
APPROVED_BRANCHES = frozenset({
    'command_source',       # rl（主控）/ baseline（Navfn+LQR 离线对照）
    'target_source',        # gt_adapter（唯一有效值）
})
# 注：`goal_follow_target` **不在此集合**——它是任务语义参数（目标移动时任务目标是否跟随，
# ADR-0001 / ADR-0013），命名形状也不属本测试检测的 `*_source|_mode|_backend|_path` 家族。
# 它不是"同一功能的两种实现"，因此不受本规范约束（规范 2.1 节的排除项）。

# 已被裁定清退、不得复活的分支（= 规范 5.2 节；每项应有防复活闸门）
RETIRED_BRANCHES = frozenset({
    # 视觉定位路径（2026-11-04）
    'perception_path',
    'vision_detector',
    'detector_backend',
    'vision_model_id',
    'vision_model_name',
    'vision_model_version',
    'vision_model_sha256',
    'target_plane_z_m',
    # W7 研究臂（2026-11-04）
    'observe_yaw_mode',
    'air_tracking_ref',
    'standoff_safe_max',
    'spawn_randomize',
    'shield',
    # air_fusion 退役后无第二取值
    'obstacles_source',
})

# 路线分支的**命名形状**：`<域>_source` / `<域>_mode` / `<域>_backend` / `<域>_path`。
# 故意不收 `xxx_type`（`gz_x500_mono_cam` 之类是文件/模型选择，不是路线分支）。
BRANCH_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*_(source|mode|backend|path)$")

# 环境适配分支（规范 2.1 节明确排除的类别）：
#   这些参数按**运行环境能力**切换（GPU / 渲染器是否可用），不改变业务行为、
#   不改变节点集合语义、不需要"用户批准"——它们是让同一份代码能在不同机器上跑起来。
ENV_ADAPTATION_BRANCHES = frozenset({
    'gui_render_backend',   # auto / d3d12 / software：渲染后端适配（ADR-0021）
})

# 待清退（规范 5.3）：**尚未执行**，因此仍在 launch 里，但必须在台账里可见。
PENDING_RETIREMENT = frozenset()   # 2026-11-04 已全部执行完毕（见规范 5.2）

LAUNCH_GLOBS = ('src/*/launch/*.py',)


def _launch_files() -> list[Path]:
    files: list[Path] = []
    for g in LAUNCH_GLOBS:
        files.extend(sorted(ROOT.glob(g)))
    return files


def _declared_args(path: Path) -> set[str]:
    """从 launch 文件里抽出所有 `DeclareLaunchArgument('<name>'` 的参数名。"""
    text = path.read_text(encoding='utf-8', errors='replace')
    return set(re.findall(r"DeclareLaunchArgument\(\s*'([a-z][a-z0-9_]*)'", text))


def _branch_args() -> dict[str, list[str]]:
    """全仓 launch 里的路线分支参数 → 出现在哪些文件。"""
    found: dict[str, list[str]] = {}
    for f in _launch_files():
        for name in _declared_args(f):
            if BRANCH_NAME_RE.match(name):
                found.setdefault(name, []).append(str(f.relative_to(ROOT)))
    return found


def test_no_unapproved_branch_args():
    """launch 里的路线分支参数必须**恰好**等于已批准集合。

    多一个 = 未经批准新增路线分支（须走 `docs/conventions/路线分支治理.md` 2.2 节四项准入，
    其中第 ① 项是**用户明确允许**）；少一个 = 删了分支却没更新台账。
    """
    found = set(_branch_args())
    unapproved = found - APPROVED_BRANCHES - PENDING_RETIREMENT - RETIRED_BRANCHES \
        - ENV_ADAPTATION_BRANCHES
    missing = APPROVED_BRANCHES - found

    assert not unapproved, (
        'launch 里出现**未批准**的路线分支参数（这是规范禁止的"顺手加分支"）：\n%s\n'
        '若确需该分支：① 先取得用户明确允许；② 在 '
        'docs/conventions/路线分支治理.md 5.1 表登记行并写退役条件；'
        '③ 再把名字加进本测试的 APPROVED_BRANCHES。'
        % '\n'.join('  - %s（出现在 %s）' % (n, ', '.join(_branch_args()[n]))
                    for n in sorted(unapproved)))

    assert not missing, (
        '台账登记了 launch 里不存在的分支（删了分支却没更新台账）：\n%s\n'
        '若确已清退：按规范 4.2 节做完五步（删代码/删测试/改文档/保 schema/写 ADR），'
        '再把名字从 APPROVED_BRANCHES 移到 RETIRED_BRANCHES。'
        % '\n'.join('  - %s' % n for n in sorted(missing)))


def test_retired_branches_have_no_declaration():
    """已清退分支不得在**任何** launch 里复活（规范 4.3 节防复活闸门）。"""
    found = _branch_args()
    alive = sorted(RETIRED_BRANCHES & set(found))
    assert not alive, (
        '已清退的路线分支又被声明了（违反规范 4.3 防复活闸门）：\n%s'
        % '\n'.join('  - %s（出现在 %s）' % (n, ', '.join(found[n])) for n in alive))


def test_retired_branches_documented_in_ledger():
    """每个已清退分支必须在规范 5.2 节有记录（删了不记录 = 下次又会被加回来）。"""
    text = CONVENTION.read_text(encoding='utf-8')
    assert '5.2 已退役台账' in text, '规范缺少 5.2 节「已退役台账」'
    for name in RETIRED_BRANCHES:
        assert name in text, (
            '已清退分支 `%s` 未出现在 docs/conventions/路线分支治理.md 5.2 表里' % name)


def test_convention_forbids_unapproved_branches():
    """规范本身必须含"未经用户允许不得创造分支"的硬规则（防止被悄悄改写）。"""
    text = CONVENTION.read_text(encoding='utf-8')
    for phrase in ('没有用户明确允许，不得创造路线分支',
                   '退役条件',
                   '防复活闸门'):
        assert phrase in text, '规范缺少关键条款：%s' % phrase


def test_every_launch_configuration_is_declared():
    """顶层入口 `w6.launch.py` 的 `LaunchConfiguration('x')` 引用必须都有声明。

    2026-11-05 事故：清退路线分支时把 `goal_follow_target` 的声明连同相邻代码块
    整块删掉，但 `_compose` 仍 `LaunchConfiguration('goal_follow_target').perform(context)`
    → `ros2 launch` 在解析期直接抛
    `launch configuration 'goal_follow_target' does not exist`，整链无法启动，
    而静态测试（只数已声明的分支名）完全看不出来。此处补一道闸门：
    引用未声明的参数 = 必然在 launch 期崩溃，必须在提交前挡住。

    **只查顶层入口**：`m0_skeleton` / `*_bringup` 等被 include 的子文件，其参数由
    父 launch 的 `launch_arguments=` 注入（部分还是 `for _arg in ('car_x', ...)` 循环
    动态声明），不要求在本文件内自证；而 `w6.launch.py` 是 `ros2 launch` 的直接目标，
    它的每个引用都必须由自己声明（事故正是发生在这里）。
    """
    entry = ROOT / 'src' / 'agc_task' / 'launch' / 'w6.launch.py'
    text = entry.read_text(encoding='utf-8', errors='replace')
    referenced = set(re.findall(
        r"LaunchConfiguration\(\s*'([a-z][a-z0-9_]*)'", text))
    undeclared = referenced - _declared_args(entry)
    assert not undeclared, (
        'w6.launch.py 引用了**未声明**的 LaunchConfiguration（ros2 launch 会在解析期抛 '
        '`launch configuration ... does not exist`，整链起不来）：%s\n'
        '补回 `DeclareLaunchArgument`，或删掉对应的 `LaunchConfiguration` 引用。'
        % ', '.join(sorted(undeclared)))


def test_target_motion_override_keeps_declared_axis_in_sync():
    """CLI 覆盖 `target_motion` 时，声明轴 / 承载者 / 生效参数必须一起对齐。

    2026-11-05 事故：`--escape` 传 `target_motion:=epicycle`，实现只改了
    `info['sc'].params.intruder_driver.motion`，没改 `info['axes']` →
    启动期断言 `target_motion_effective_equals_declared`（拿旧声明轴 s04=static 比
    新生效值 epicycle）为 False → 拒绝运行；且 manifest 的 declared_axes / carriers
    会如实写成 static 而实际跑 epicycle，证据链失真。

    闸门：覆盖必须走 `apply_target_motion_override`（同步 sc / axes / entries 三处），
    且调用点在 `load_scene` 之后、两个 backend 分支之前（对 full / lightweight 都生效）。
    """
    comp = (ROOT / 'src' / 'agc_task' / 'launch' /
            'w6_composition.py').read_text(encoding='utf-8', errors='replace')
    w6 = (ROOT / 'src' / 'agc_task' / 'launch' /
          'w6.launch.py').read_text(encoding='utf-8', errors='replace')
    assert 'def apply_target_motion_override(' in comp, \
        '缺少 apply_target_motion_override（CLI 覆盖会与声明轴/证据链脱节）'
    for key in ("info['axes']['target_motion']", "info['entries']['target_motion']",
                "info['sc'].setdefault('params'"):
        assert key in comp, 'apply_target_motion_override 未同步 %s' % key
    # 调用点必须在 load_scene 之后、backend 分支之前，且不在 full 分支里再写第二份。
    pos_scene = w6.find('info = load_scene(')
    pos_call = w6.find('apply_target_motion_override(')
    pos_branch = w6.find("if backend == 'lightweight':")
    assert pos_scene < pos_call < pos_branch, \
        ('apply_target_motion_override 调用位置不对：须在 load_scene 之后、'
         '两个 backend 分支之前（否则 lightweight 或断言链会漏掉）')
    assert w6.count('apply_target_motion_override(') == 1, \
        '只允许一处调用（import 不计），不得在 backend 分支里重复实现第二份'


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
