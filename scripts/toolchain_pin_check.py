#!/usr/bin/env python3
"""toolchain_pin_check —— S-09（工具链可重建 pin 清单）一致性核查（**只读**）。

真源：`toolchain/README.md` 内的 ```yaml fenced 块（含 `agc_toolchain_pins:`），
由 `yaml.safe_load` 解析。本脚本比对 README 记录值 vs 实测，逐项记 PASS / FAIL / SKIP：

  (a) artifacts：逐条算文件 sha256 与记录比对；文件缺失 -> FAIL（原因 `missing`）。
  (b) git_repos：`git -C <path> rev-parse HEAD` 与 `head`；`describe --tags --exact-match`
      或 `tag --points-at HEAD` 与 `tag`；仓库缺失 -> FAIL `missing`。
  (c) submodules：`git -C <px4> submodule status <path>` 首字符（空格=已初始化 / `-`=未初始化）
      与 SHA 比对；未初始化 -> FAIL `not_initialized`。
  (d) dds_versions：`ros_fastrtps`/`ros_fastcdr` 用 `dpkg-query -W -f='${Version}'`（包
      `ros-jazzy-fastrtps`/`ros-jazzy-fastcdr`）——记录值须为实测版本号的**前缀匹配**；
      `host_spdlog`/`host_fmt` 同理（`libspdlog-dev`/`libfmt-dev`）；`sysroot_spdlog` 从
      `<sysroot>/usr/include/spdlog/version.h` 三段宏拼出；`sysroot_fmt` 从 `fmt/core.h` 的
      `FMT_VERSION` 宏换算（90100 -> 9.1.0）。`dpkg-query` 不可用 -> SKIP（非 FAIL）。
  (e) localdeps_debs：对 `toolchain/localdeps/debs/` 下每个 `.deb` 算 sha256 得实测集合；
      与 README 记录的哈希集合做**集合比对**（双向差集须为空），报告缺失/多余文件。

环境无关：**不** `source /opt/ros/jazzy`，只用 `dpkg-query` 与文件读取。

输出 JSON 摘要（stdout）；`--out <path>` 落盘。用法：`python3 scripts/toolchain_pin_check.py`。
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

import yaml

ROOT = '/home/chen/AGC'

README_REL = os.path.join('toolchain', 'README.md')
DEBS_REL = os.path.join('toolchain', 'localdeps', 'debs')
SYSROOT_SPDLOG_REL = os.path.join('toolchain', 'localdeps', 'sysroot', 'usr', 'include',
                                  'spdlog', 'version.h')
SYSROOT_FMT_REL = os.path.join('toolchain', 'localdeps', 'sysroot', 'usr', 'include',
                               'fmt', 'core.h')

# 期望的 dpkg 包名（README 记录值须为实测版本号前缀）。
DDS_PKG = {
    'ros_fastrtps': 'ros-jazzy-fastrtps',
    'ros_fastcdr': 'ros-jazzy-fastcdr',
    'host_spdlog': 'libspdlog-dev',
    'host_fmt': 'libfmt-dev',
}

FENCED_YAML = re.compile(r'```yaml\n(.*?)```', re.DOTALL)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def _run(cmd, cwd=None):
    """返回 (returncode, stdout.strip())。"""
    try:
        r = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return r.returncode, r.stdout.decode('utf-8', 'replace').strip()
    except OSError:
        return 127, ''


def _raw_run(cmd, cwd=None):
    """返回保留前导空白的 stdout（`git submodule status` 首字符是状态标记）。"""
    try:
        r = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return r.stdout.decode('utf-8', 'replace')
    except OSError:
        return ''


def _check(checks, name, status, expected=None, actual=None, reason=''):
    checks.append({
        'check': name,
        'status': status,
        'expected': expected,
        'actual': actual,
        'reason': reason,
    })


def extract_pins(readme_text):
    """提取含 `agc_toolchain_pins:` 的 ```yaml 块并 safe_load。"""
    for block in FENCED_YAML.findall(readme_text):
        if 'agc_toolchain_pins:' in block:
            return yaml.safe_load(block)
    raise ValueError('README 中未找到含 agc_toolchain_pins: 的 ```yaml 块')


def check_artifacts(pins, checks, root):
    for art in pins.get('artifacts') or []:
        rel = art['path']
        exp = art['sha256']
        abspath = os.path.join(root, rel)
        if not os.path.isfile(abspath):
            _check(checks, 'artifact:%s' % rel, 'FAIL', exp, None, 'missing')
            continue
        got = sha256_file(abspath)
        if got == exp:
            _check(checks, 'artifact:%s' % rel, 'PASS', exp, got, '')
        else:
            _check(checks, 'artifact:%s' % rel, 'FAIL', exp, got, 'sha256_mismatch')


def check_git_repos(pins, checks, root):
    for repo in pins.get('git_repos') or []:
        rid = repo.get('id', repo.get('path'))
        path = os.path.join(root, repo['path'])
        if _run(['git', '-C', path, 'rev-parse', '--git-dir'])[0] != 0:
            _check(checks, 'git:%s' % rid, 'FAIL', repo.get('head'), None, 'missing')
            continue
        # HEAD
        _, head = _run(['git', '-C', path, 'rev-parse', 'HEAD'])
        if head == repo.get('head'):
            _check(checks, 'git:%s:head' % rid, 'PASS', repo.get('head'), head, '')
        else:
            _check(checks, 'git:%s:head' % rid, 'FAIL', repo.get('head'), head or None,
                   'head_mismatch')
        # tag
        _, desc = _run(['git', '-C', path, 'describe', '--tags', '--exact-match'])
        if desc != repo.get('tag'):
            _, points = _run(['git', '-C', path, 'tag', '--points-at', 'HEAD'])
            tags = points.split('\n') if points else []
            desc = repo.get('tag') if repo.get('tag') in tags else (points or None)
        if desc == repo.get('tag'):
            _check(checks, 'git:%s:tag' % rid, 'PASS', repo.get('tag'), desc, '')
        else:
            _check(checks, 'git:%s:tag' % rid, 'FAIL', repo.get('tag'), desc,
                   'tag_mismatch')
        # submodules（`git submodule status` 首字符是状态标记：空格=已初始化，`-`=未初始化）
        for sm_path, sm_sha in (repo.get('submodules') or {}).items():
            name = 'submodule:%s' % sm_path
            raw = _raw_run(['git', '-C', path, 'submodule', 'status', '--', sm_path])
            line = raw.split('\n', 1)[0]
            m = re.match(r'^([ \-+U])([0-9a-f]{40})\s', line)
            if not m:
                _check(checks, name, 'FAIL', sm_sha, None, 'missing')
                continue
            marker, got = m.group(1), m.group(2)
            if marker == '-':
                _check(checks, name, 'FAIL', sm_sha, got, 'not_initialized')
            elif got != sm_sha:
                _check(checks, name, 'FAIL', sm_sha, got, 'sha_mismatch')
            elif marker != ' ':
                _check(checks, name, 'FAIL', sm_sha, got,
                       'submodule_marker_%s' % marker)
            else:
                _check(checks, name, 'PASS', sm_sha, got, '')

            # 子模块内已跟踪文件被改动同样属于未登记 dirty，不能只看 commit。
            sm_path_abs = os.path.join(path, sm_path)
            rc_content, dirty = _run(['git', '-C', sm_path_abs, 'status', '--porcelain',
                                      '--untracked-files=no'])
            name_dirty = '%s:content' % name
            if rc_content != 0:
                _check(checks, name_dirty, 'FAIL', 'clean', None, 'submodule_unavailable')
            elif dirty:
                _check(checks, name_dirty, 'FAIL', 'clean', dirty, 'submodule_dirty')
            else:
                _check(checks, name_dirty, 'PASS', 'clean', 'clean', '')


def _porcelain_path(line):
    """从 `git status --porcelain` 行提取路径（兼容 rename / quote）。"""
    path = line[3:]
    if ' -> ' in path:
        path = path.split(' -> ', 1)[1]
    if len(path) >= 2 and path[0] == '"' and path[-1] == '"':
        path = path[1:-1]
    return path


def check_local_patches(pins, checks, root):
    """校验本地补丁：补丁哈希、基准可应用、当前源码=基准+补丁、无额外 dirty。

    活动外部树只读；负例由调用方在临时夹具中构造。
    """
    patches = pins.get('local_patches') or []
    if not patches:
        return
    repos = {r.get('id', r.get('path')): r for r in (pins.get('git_repos') or [])}

    for patch in patches:
        pid = patch.get('id', patch.get('path'))
        rel = patch.get('path')
        prefix = 'patch:%s' % pid
        if not rel:
            _check(checks, prefix + ':path', 'FAIL', 'path', None, 'missing_path')
            continue

        patch_path = os.path.join(root, rel)
        if not os.path.isfile(patch_path):
            _check(checks, prefix + ':sha256', 'FAIL', patch.get('sha256'), None, 'missing')
            continue
        got = sha256_file(patch_path)
        if got == patch.get('sha256'):
            _check(checks, prefix + ':sha256', 'PASS', patch.get('sha256'), got, '')
        else:
            _check(checks, prefix + ':sha256', 'FAIL', patch.get('sha256'), got,
                   'sha256_mismatch')

        repo = repos.get(patch.get('repo'))
        if repo is None:
            _check(checks, prefix + ':repo', 'FAIL', patch.get('repo'), None, 'unknown_repo')
            continue
        repo_path = os.path.join(root, repo['path'])
        if not os.path.isdir(repo_path):
            _check(checks, prefix + ':repo', 'FAIL', repo['path'], None, 'missing_repo')
            continue
        _check(checks, prefix + ':repo', 'PASS', repo['path'], repo['path'], '')

        source_files = patch.get('source_files') or {}
        if not source_files:
            _check(checks, prefix + ':source_files', 'FAIL', 'non-empty', None,
                   'missing_source_files')
        for sf, exp in source_files.items():
            name = '%s:source:%s' % (prefix, sf)
            sf_path = os.path.join(repo_path, sf)
            if not os.path.isfile(sf_path):
                _check(checks, name, 'FAIL', exp, None, 'missing')
                continue
            got = sha256_file(sf_path)
            if got == exp:
                _check(checks, name, 'PASS', exp, got, '')
            else:
                _check(checks, name, 'FAIL', exp, got, 'sha256_mismatch')

        # 补丁必须能应用到基准（--cached 只看 index = HEAD，不受工作区脏影响）
        rc, out = _run(['git', '-C', repo_path, 'apply', '--check', '--cached', patch_path])
        if rc == 0:
            _check(checks, prefix + ':applies_to_baseline', 'PASS', 'clean', 'clean', '')
        else:
            _check(checks, prefix + ':applies_to_baseline', 'FAIL', 'clean', None,
                   'apply_check_failed: %s' % out)

        # 当前工作区必须恰好是“基准 + 补丁”：反向应用应干净通过
        rc, out = _run(['git', '-C', repo_path, 'apply', '--check', '--reverse', patch_path])
        if rc == 0:
            _check(checks, prefix + ':worktree_equals_baseline_plus_patch', 'PASS',
                   'clean', 'clean', '')
        else:
            _check(checks, prefix + ':worktree_equals_baseline_plus_patch', 'FAIL',
                   'clean', None, 'reverse_apply_failed: %s' % out)

        # 除登记源文件外，不允许其它 tracked dirty / untracked（非 ignored）
        rc, _ = _run(['git', '-C', repo_path, 'status', '--porcelain=v1',
                      '--untracked-files=normal'])
        out = _raw_run(['git', '-C', repo_path, 'status', '--porcelain=v1',
                        '--untracked-files=normal'])
        if rc != 0:
            _check(checks, prefix + ':extra_dirty', 'FAIL', 'clean', None, 'status_failed')
        else:
            allowed = set(source_files)
            extra = []
            for line in (out or '').splitlines():
                if not line.strip():
                    continue
                if _porcelain_path(line) not in allowed:
                    extra.append(line)
            if extra:
                _check(checks, prefix + ':extra_dirty', 'FAIL', 'none', extra,
                       'unregistered_changes')
            else:
                _check(checks, prefix + ':extra_dirty', 'PASS', 'none', 'none', '')


def _dpkg_version(pkg):
    rc, out = _run(['dpkg-query', '-W', '-f=${Version}', pkg])
    if rc == 0 and out:
        return out
    return None


def check_dds_versions(pins, checks, root):
    dds = pins.get('dds_versions') or {}
    dpkg_ok = _run(['dpkg-query', '--version'])[0] == 0
    for key, pkg in DDS_PKG.items():
        if key not in dds:
            continue
        exp = dds[key]
        if not dpkg_ok:
            _check(checks, 'dds:%s' % key, 'SKIP', exp, None, 'dpkg_query_unavailable')
            continue
        got = _dpkg_version(pkg)
        if got is None:
            _check(checks, 'dds:%s' % key, 'SKIP', exp, None, 'package_not_installed')
            continue
        if got.startswith(exp):
            _check(checks, 'dds:%s' % key, 'PASS', exp, got, '')
        else:
            _check(checks, 'dds:%s' % key, 'FAIL', exp, got, 'version_prefix_mismatch')

    # sysroot spdlog
    if 'sysroot_spdlog' in dds:
        exp = dds['sysroot_spdlog']
        p = os.path.join(root, SYSROOT_SPDLOG_REL)
        if not os.path.isfile(p):
            _check(checks, 'dds:sysroot_spdlog', 'FAIL', exp, None, 'missing')
        else:
            with open(p, encoding='utf-8', errors='replace') as f:
                txt = f.read()
            m = re.search(r'#define\s+SPDLOG_VER_MAJOR\s+(\d+)', txt)
            mi = re.search(r'#define\s+SPDLOG_VER_MINOR\s+(\d+)', txt)
            pa = re.search(r'#define\s+SPDLOG_VER_PATCH\s+(\d+)', txt)
            if m and mi and pa:
                got = '%s.%s.%s' % (m.group(1), mi.group(1), pa.group(1))
                if got == exp:
                    _check(checks, 'dds:sysroot_spdlog', 'PASS', exp, got, '')
                else:
                    _check(checks, 'dds:sysroot_spdlog', 'FAIL', exp, got,
                           'version_mismatch')
            else:
                _check(checks, 'dds:sysroot_spdlog', 'FAIL', exp, None,
                       'macro_not_found')

    # sysroot fmt
    if 'sysroot_fmt' in dds:
        exp = dds['sysroot_fmt']
        p = os.path.join(root, SYSROOT_FMT_REL)
        if not os.path.isfile(p):
            _check(checks, 'dds:sysroot_fmt', 'FAIL', exp, None, 'missing')
        else:
            with open(p, encoding='utf-8', errors='replace') as f:
                txt = f.read()
            m = re.search(r'#define\s+FMT_VERSION\s+(\d+)', txt)
            if m:
                v = int(m.group(1))
                got = '%d.%d.%d' % (v // 10000, (v // 100) % 100, v % 100)
                if got == exp:
                    _check(checks, 'dds:sysroot_fmt', 'PASS', exp, got, '')
                else:
                    _check(checks, 'dds:sysroot_fmt', 'FAIL', exp, got,
                           'version_mismatch')
            else:
                _check(checks, 'dds:sysroot_fmt', 'FAIL', exp, None, 'macro_not_found')


def check_localdeps_debs(pins, checks, root):
    recorded = pins.get('localdeps_debs') or {}
    recorded_hashes = set(recorded.values())
    debs_dir = os.path.join(root, DEBS_REL)
    if not os.path.isdir(debs_dir):
        _check(checks, 'localdeps_debs', 'FAIL', sorted(recorded_hashes), [], 'missing_dir')
        return
    measured = {}   # sha256 -> [filename]
    for fn in sorted(os.listdir(debs_dir)):
        if not fn.endswith('.deb'):
            continue
        measured.setdefault(sha256_file(os.path.join(debs_dir, fn)), []).append(fn)
    measured_hashes = set(measured)
    missing = sorted(recorded_hashes - measured_hashes)   # 记录有、磁盘无
    extra = sorted(measured_hashes - recorded_hashes)     # 磁盘有、记录无
    if not missing and not extra:
        _check(checks, 'localdeps_debs', 'PASS',
               '%d debs' % len(measured_hashes), '%d debs' % len(measured_hashes), '')
    else:
        detail = []
        if missing:
            detail.append('missing=%s' % [recorded.get(h) for h in missing])
        if extra:
            detail.append('extra=%s' % [measured[h] for h in extra])
        _check(checks, 'localdeps_debs', 'FAIL',
               sorted(recorded_hashes), sorted(measured_hashes),
               'set_mismatch; ' + '; '.join(detail))


def main():
    ap = argparse.ArgumentParser(description='toolchain pin 清单一致性核查（只读）')
    ap.add_argument('--root', default=ROOT, help='项目根（默认 %s）' % ROOT)
    ap.add_argument('--out', default=None, help='JSON 摘要落盘路径（可选）')
    args = ap.parse_args()

    root = args.root

    checks = []
    readme_path = os.path.join(root, README_REL)
    err = None
    try:
        with open(readme_path, encoding='utf-8') as f:
            pins = extract_pins(f.read())['agc_toolchain_pins']
    except Exception as e:  # noqa: BLE001
        pins = None
        err = '%s: %s' % (type(e).__name__, e)

    if pins is None:
        _check(checks, 'readme_pins_block', 'FAIL', 'agc_toolchain_pins', None, err)
    else:
        _check(checks, 'readme_pins_block', 'PASS', 'agc_toolchain_pins',
               'schema=%s' % pins.get('schema'), '')
        check_artifacts(pins, checks, root)
        check_local_patches(pins, checks, root)
        if 'local_patches' not in pins:
            _check(checks, 'local_patches', 'FAIL', 'present', None,
                   'missing_local_patches')
        check_git_repos(pins, checks, root)
        check_dds_versions(pins, checks, root)
        check_localdeps_debs(pins, checks, root)

    summary = {
        'pass': sum(1 for c in checks if c['status'] == 'PASS'),
        'fail': sum(1 for c in checks if c['status'] == 'FAIL'),
        'skip': sum(1 for c in checks if c['status'] == 'SKIP'),
    }
    result = {
        'ok': summary['fail'] == 0,
        'checks': checks,
        'summary': summary,
    }

    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=False)
    print(text)
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            f.write(text + '\n')

    return 0 if result['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
