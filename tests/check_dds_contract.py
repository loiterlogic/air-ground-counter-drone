#!/usr/bin/env python3
"""DDS / 消息契约核查（**纯静态，秒级，不启任何仿真**）。

定位：把 2026-11-03 那一轮"目标机永不起飞"排障中**真实确认过的三个缺陷**固化成断言，
防止它们在后续改动里悄悄回归。判据全部来自**实测**，不是推测：

 a) `/agc/gt/**` 的**发布端类型**是 `geometry_msgs/PoseStamped`（配置文件 `gt_bypass`）。
 任何按 `nav_msgs/Odometry` 订阅它的节点都会**静默收 0 条**（DDS 按类型匹配，不报错）。
     实测症状：守卫恒报 `have_gt=0`，而 `ros2 topic hz` 同话题明明有数据。
 b) 仿真磁力计必须开：`SENS_EN_MAGSIM=1` 经 lock yaml → `px4-rc.params` 注入。
 PX4 官方 gz 机型 `x500` 没有 magnetometer 传感器，而该参数**定义默认值就是 0**；
 不开则 `Compass missing` → `Yaw estimate error` → EKF 不发布 odometry → 目标机不 ARM。
 **同时**断言没有退回 `SYS_HAS_MAG=0` / `EKF2_MAG_TYPE=5`——实测那两条会让
 `Ready for takeoff` 从 2 次降到 0 次。
 c) 起飞守卫的超时**不短于**实测标定的启动时长下限。实测目标机 `Armed` 落在 tw≈110 s；
 原 60 s 会在正常时序**之前**判死（实测超时点比 ARM 成功早约 6 s）。

不做：不启动 SITL / 不查 ROS 图 / 不依赖 `/dev/shm` 状态（那些是运行时事实，见
`docs/conventions/整链排障速查.md#orphan-dds`）。本核查只守**代码与配置契约**。

用法：
  python3 tests/check_dds_contract.py            # 退出码 0=PASS
  python3 tests/check_dds_contract.py --json
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import checklib  # noqa: E402  （tests/ 内共用小工具）

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
P = {
    'gt_bypass': os.path.join(ROOT, 'src/agc_perception/src/gt_bypass.cpp'),
    'guard_cpp': os.path.join(ROOT, 'src/agc_task/src/target_takeoff_guard.cpp'),
    'guard_cmake': os.path.join(ROOT, 'src/agc_task/CMakeLists.txt'),
    'lock_yaml': os.path.join(ROOT, 'src/agc_task/config/px4_failsafe_lock.yaml'),
    'lock_sh': os.path.join(ROOT, 'scripts/lock_px4_failsafe_params.sh'),
    'launch': os.path.join(ROOT, 'src/agc_task/launch/main.launch.py'),
}


_read = checklib.read_text_strict


def case_a_gt_type(res):
    """`/agc/gt/**` 发布端 = PoseStamped；守卫订阅端必须同类型。"""
    pub = _read(P['gt_bypass'])
    # 发布端：create_publisher<geometry_msgs::msg::PoseStamped>
    m = re.search(r'create_publisher<\s*geometry_msgs::msg::PoseStamped\s*>', pub)
    res['gt_publisher_is_posestamped'] = bool(m)

    guard = _read(P['guard_cpp'])
    sub_pose = re.search(r'create_subscription<\s*geometry_msgs::msg::PoseStamped\s*>', guard)
    sub_odom = re.search(r'create_subscription<\s*nav_msgs::msg::Odometry\s*>', guard)
    res['guard_subscribes_posestamped'] = bool(sub_pose)
    res['guard_no_longer_subscribes_odometry'] = not bool(sub_odom)
    # 订阅类型必须与发布端一致（这是 DDS 匹配的唯一依据）
    res['guard_type_matches_publisher'] = bool(sub_pose) and bool(m)

    cmake = _read(P['guard_cmake'])
    # 找 target_takeoff_guard 的依赖行
    dep = re.search(r'ament_target_dependencies\(\s*target_takeoff_guard\s+([^)]*)\)', cmake)
    deps = dep.group(1).split() if dep else []
    res['guard_cmake_has_geometry_msgs'] = 'geometry_msgs' in deps
    res['guard_cmake_deps'] = deps
    res['pass'] = all([
        res['gt_publisher_is_posestamped'],
        res['guard_subscribes_posestamped'],
        res['guard_no_longer_subscribes_odometry'],
        res['guard_type_matches_publisher'],
        res['guard_cmake_has_geometry_msgs'],
    ])
    return res


def case_b_magsim(res):
    """仿真磁力计必须开，且不得用 SYS_HAS_MAG=0 / EKF2_MAG_TYPE=5 绕过。"""
    yaml_text = _read(P['lock_yaml'])
    sh = _read(P['lock_sh'])
    launch = _read(P['launch'])

    # 允许行尾注释（配置文件 yaml 的每个键都带说明）
    m = re.search(r'^\s*sensor_en_magsim\s*:\s*(\d+)\s*(?:#.*)?$', yaml_text, re.M)
    res['lock_yaml_sensor_en_magsim'] = int(m.group(1)) if m else None
    res['magsim_is_1'] = (res['lock_yaml_sensor_en_magsim'] == 1)

    # 注入脚本必须真的把它写进 px4-rc.params
    res['lock_sh_emits_magsim'] = bool(
        re.search(r'param set SENS_EN_MAGSIM', sh))
    res['lock_sh_reads_yaml_key'] = 'sensor_en_magsim' in sh

    # BAN：这两种"绕过"做法实测更糟（Ready for takeoff 2 → 0）
    res['no_sys_has_mag_0'] = not bool(
        re.search(r'^\s*sys_has_mag\s*:\s*0\s*(?:#.*)?$', yaml_text, re.M))
    res['no_ekf2_mag_type_5'] = not bool(
        re.search(r'^\s*ekf2_mag_type\s*:\s*5\s*(?:#.*)?$', yaml_text, re.M))
    res['no_sys_has_mag_in_lock_sh'] = 'SYS_HAS_MAG' not in sh
    res['no_ekf2_mag_type_in_lock_sh'] = 'EKF2_MAG_TYPE' not in sh

    # launch 不得把磁力计关掉（覆盖式注入）
    res['launch_does_not_disable_magsim'] = not bool(
        re.search(r'SENS_EN_MAGSIM.*[=:]\s*[\'"]?0', launch))

    res['pass'] = all([
        res['magsim_is_1'],
        res['lock_sh_emits_magsim'],
        res['lock_sh_reads_yaml_key'],
        res['no_sys_has_mag_0'],
        res['no_ekf2_mag_type_5'],
        res['no_sys_has_mag_in_lock_sh'],
        res['no_ekf2_mag_type_in_lock_sh'],
        res['launch_does_not_disable_magsim'],
    ])
    return res


# 实测标定：目标机 Armed 落在 tw≈110 s；60 s 会在正常时序前判死。
GUARD_TIMEOUT_MIN_S = 120.0


def case_c_guard_timeout(res):
    """守卫超时不得短于实测启动时长下限。"""
    launch = _read(P['launch'])
    vals = [float(v) for v in
            re.findall(r"'startup_timeout_s'\s*:\s*([0-9.]+)", launch)]
    # 只取守卫节点那处（launch 里若有多处，要求全部 >= 下限）
    res['guard_timeout_values'] = vals
    res['has_guard_timeout'] = bool(vals)
    res['guard_timeout_min_required_s'] = GUARD_TIMEOUT_MIN_S
    res['guard_timeout_all_ge_min'] = bool(vals) and all(
        v >= GUARD_TIMEOUT_MIN_S for v in vals)
    res['pass'] = res['has_guard_timeout'] and res['guard_timeout_all_ge_min']
    return res


def case_d_no_discovery_range_override(res):
    """launch **不得**自行覆盖 `ROS_AUTOMATIC_DISCOVERY_RANGE`。

 2026-11-03 实测（A/B 各 2 次）：把它设成 SUBNET 或 LOCALHOST 与起飞成败**无因果关系**
 （LOCALHOST 1 败 1 成、SUBNET 2 成）。该变量的口径由入口脚本 + 排障速查#0 统一规定，
 launch 再插一手会制造"两处配置文件"，且本机 SUBNET 在 WSL2 上有已知间歇失效。
    """
    launch = _read(P['launch'])
    hits = re.findall(
        r'SetEnvironmentVariable\(\s*[\'"]ROS_AUTOMATIC_DISCOVERY_RANGE[\'"]', launch)
    res['launch_discovery_range_overrides'] = len(hits)
    res['pass'] = (len(hits) == 0)
    return res


# 允许写死 LOCALHOST 的范围：**历史归档 / 运行证据 / 策略表自身**。
# 其余活跃代码一律禁止——2026-11-04 的教训是"改文字挡不住复发，必须让测试失败"。
_HARDCODE_EXEMPT_DIRS = (
    'scripts/archive/',      # 历史脚本：当时事实，不改写
    'experiments/',          # 运行证据：不回头改
    'build/', 'install/',
    'scripts/demo/dds_transport.py',        # 策略表**自身**（唯一合法出处）
    'scripts/tests/test_dds_transport.py',  # 选择器契约测试
)
_HARDCODE_EXEMPT_FILES = (
    'tests/check_dds_contract.py',        # 本文件：正则与豁免表字面量
    'scripts/tests/test_dds_contract_guard.py',  # 本闸门的**测试夹具**（样本即违规写法）
)

# 只扫"可执行 / 可配置"文件；**文档不算**（文档里讲解 LOCALHOST 是必要的）。
_HARDCODE_SUFFIXES = ('.py', '.sh', '.bash', '.xml', '.yaml', '.yml')

# 覆盖全部真实写法（实测这些才是仓库里出现过的形态）：
# os.environ["…"] = "LOCALHOST" env['…'] = 'LOCALHOST'
# env.update({'…': 'LOCALHOST'}) export …=LOCALHOST
# 容忍：变量名两侧的引号/方括号、赋值号两侧的引号与空格。
_HARDCODED_LOCALHOST = re.compile(
    r"""ROS_AUTOMATIC_DISCOVERY_RANGE['"\]]*\s*(?:=|:)\s*['"]?LOCALHOST""")


def _line_hardcodes_localhost(line):
    """一行是否把 discovery range 写死成 LOCALHOST。

 额外排除两种**非赋值**语境，避免误报把闸门变噪音：
 * 纯注释/文档行里讲解用法（`# … LOCALHOST`、`：…LOCALHOST`）—— 只在行首是注释符时排除；
 * 形如 `'ROS_AUTOMATIC_DISCOVERY_RANGE=%s'` 的格式化串（值不是字面量 LOCALHOST，
 本正则也不会命中它，因为 `%s` 不是 LOCALHOST）。
    """
    if not _HARDCODED_LOCALHOST.search(line):
        return False
    stripped = line.lstrip()
    # 整行注释（Python/bash/yaml）里允许讲 LOCALHOST，不作为违规
    if stripped.startswith(('#', '//')):
        return False
    # **断言/比较语境**放行：形如 `'…=LOCALHOST' in sh`、`assert … == '…LOCALHOST'`。
    # 这类是"检查历史脚本里有没有这个写法"，本身并不设置环境变量。
    if re.search(r"""['"]ROS_AUTOMATIC_DISCOVERY_RANGE[='"]""", line) and \
            (' in ' in line or 'assert ' in line or '==' in line):
        return False
    # **文档性引用**放行：整段被反引号包住（`…=LOCALHOST`）说明是在讲解，不是赋值。
    if re.search(r'`[^`]*ROS_AUTOMATIC_DISCOVERY_RANGE[^`]*`', line):
        return False
    return True


def case_e_no_hardcoded_localhost(res):
    """**活跃代码不得写死 `ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST`**（防复发主闸）。

 为什么这条必须存在（2026-11-04 实测）：本机 `lo` 无 `IFF_MULTICAST`，写死 LOCALHOST
 在 **1 发布 ↔ 1 订阅** 拓扑下**稳定零送达**（≥2 发布进程时偶通 → 这正是历史
 "忽好忽坏"的来源）。本项目已为此浪费过两次整轮定位；文档劝告没挡住，所以把它变成
 **会失败的测试**。

 唯一合法出处：`scripts/demo/dds_transport.py`（策略 `localhost-udp`）。需要 LOCALHOST
    的地方请调 `dds_transport.apply()/env_for()`，不要自己拼字符串。
    """
    offenders = []
    scanned = 0
    for dirpath, dirnames, filenames in os.walk(ROOT):
        rel_dir = os.path.relpath(dirpath, ROOT).replace(os.sep, '/')
        rel_dir = '' if rel_dir == '.' else rel_dir + '/'
        dirnames[:] = [d for d in dirnames
                       if d not in ('.git', '__pycache__', 'node_modules')]
        for fn in filenames:
            if not fn.endswith(_HARDCODE_SUFFIXES):
                continue
            rel = rel_dir + fn
            if any(rel.startswith(d) for d in _HARDCODE_EXEMPT_DIRS):
                continue
            if rel in _HARDCODE_EXEMPT_FILES:
                continue
            path = os.path.join(dirpath, fn)
            try:
                with open(path, encoding='utf-8', errors='replace') as f:
                    text = f.read()
            except OSError:
                continue
            scanned += 1
            # 逐行判（保留精确行号），再做一次**跨行**判，防 `'KEY':\n 'LOCALHOST'` 漏网。
            hits = set()
            for i, line in enumerate(text.splitlines(), 1):
                if _line_hardcodes_localhost(line):
                    hits.add(i)
            for m in re.finditer(
                    r"""ROS_AUTOMATIC_DISCOVERY_RANGE['"]?\s*[=:]\s*['"]?[\s\n]*LOCALHOST""",
                    text):
                # 反引号包裹 = 文档性引用，跳过
                if '`' in text[max(0, m.start() - 2):m.start()]:
                    continue
                line_no = text.count('\n', 0, m.start()) + 1
                # 与逐行判共用同一套语境放行（断言/比较语境不设环境变量）
                first_line = text.splitlines()[line_no - 1] if line_no <= len(
                    text.splitlines()) else ''
                if ' in ' in first_line or 'assert ' in first_line or '==' in first_line:
                    continue
                hits.add(line_no)
            for line_no in sorted(hits):
                offenders.append('%s:%d' % (rel, line_no))

    res['scanned_files'] = scanned
    res['hardcoded_localhost'] = offenders
    res['pass'] = not offenders
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', action='store_true', help='只输出 JSON')
    args = ap.parse_args()

    out = {}
    for name, fn in (
            ('a_gt_type', case_a_gt_type),
            ('b_magsim', case_b_magsim),
            ('c_guard_timeout', case_c_guard_timeout),
            ('d_no_discovery_range_override', case_d_no_discovery_range_override),
            ('e_no_hardcoded_localhost', case_e_no_hardcoded_localhost)):
        try:
            out[name] = fn({})
        except Exception as e:                      # noqa: BLE001
            out[name] = {'pass': False, 'error': '%s: %s' % (type(e).__name__, e)}

    ok = all(v.get('pass') for v in out.values())
    doc = {'pass': ok, 'cases': out}
    if args.json:
        print(json.dumps(doc, indent=2, ensure_ascii=False))
    else:
        for name, v in out.items():
            mark = 'PASS' if v.get('pass') else 'FAIL'
            print('%-32s %s' % (name, mark))
            for k, vv in v.items():
                if k != 'pass':
                    print('    %s = %r' % (k, vv))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
